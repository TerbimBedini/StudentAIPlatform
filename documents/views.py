import json
import logging
import mimetypes
import random
import re
import threading
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections, models
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .ai import (
    AIError,
    ask_document_ai,
    generate_exam,
    generate_flashcards,
    generate_quiz,
    generate_summary,
)
from .forms import CommunityMessageForm, DocumentForm, LibraryDocumentForm
from .models import (
    Activity,
    CommunityMessage,
    Document,
    FlashcardAttempt,
    LibraryDocument,
    QuizAttempt,
    StudySession,
)
from .rag import (
    create_document_index,
    get_random_document_chunks,
    search_document_chunks,
    search_multiple_documents,
)
from .utils import TextExtractionError, extract_text_from_document


AI_RATE_LIMIT = 10
AI_RATE_LIMIT_WINDOW_SECONDS = 60
logger = logging.getLogger(__name__)


def consume_ai_request_quota(user):
    cache_key = f'ai_rate_limit:user:{user.id}'

    if cache.add(cache_key, 1, AI_RATE_LIMIT_WINDOW_SECONDS):
        return True

    try:
        current_count = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, AI_RATE_LIMIT_WINDOW_SECONDS)
        return True

    return current_count <= AI_RATE_LIMIT


def ai_rate_limit_message():
    return 'Ke bere shume kerkesa AI brenda nje minute. Provo perseri pas pak.'


def get_selected_documents(request, document_ids):
    return Document.objects.filter(
        id__in=document_ids,
        uploaded_by=request.user
    ).order_by('title')


def combine_documents_text(documents):
    text_parts = []

    for document in documents:
        text = extract_text_from_document(document.file.path)
        if text:
            text_parts.append(
                f'Dokumenti: {document.title}\n{text}'
            )

    return '\n\n---\n\n'.join(text_parts)


def record_activity(user, activity_type, document_title):
    Activity.objects.create(
        user=user,
        activity_type=activity_type,
        document_title=document_title
    )


def get_previous_quiz_questions(user, documents=None, limit=25):
    attempts = QuizAttempt.objects.filter(user=user).order_by('-created_at')

    if documents is not None:
        attempts = attempts.filter(document__in=documents)

    questions = []

    for attempt in attempts[:limit]:
        for mistake in getattr(attempt, 'mistakes', []) or []:
            question = mistake.get('question') if isinstance(mistake, dict) else None
            if question:
                questions.append(question)

    return questions[:limit]


def process_uploaded_document_ai(document_id, user_id):
    try:
        close_old_connections()
        try:
            document = Document.objects.get(
                id=document_id,
                uploaded_by_id=user_id
            )
        except Document.DoesNotExist:
            return

        if not document.file.name.lower().endswith(('.pdf', '.docx')):
            return

        document.summary_status = Document.STATUS_PROCESSING
        document.processing_error = ''
        document.save(
            update_fields=[
                'summary_status',
                'processing_error',
            ]
        )

        try:
            text = extract_text_from_document(document.file.path)
            document.summary = generate_summary(text)
            document.ai_processed = True
            document.summary_status = Document.STATUS_COMPLETED
            document.processing_error = ''
            document.save(
                update_fields=[
                    'summary',
                    'ai_processed',
                    'summary_status',
                    'processing_error',
                ]
            )

            if document.file.name.lower().endswith('.pdf'):
                create_document_index(document)

            record_activity(
                document.uploaded_by,
                'summary',
                document.title
            )
        except (AIError, TextExtractionError) as exc:
            document.ai_processed = False
            document.summary_status = Document.STATUS_FAILED
            document.processing_error = str(exc)
            document.save(
                update_fields=[
                    'ai_processed',
                    'summary_status',
                    'processing_error',
                ]
            )
        except Exception:
            logger.exception(
                'Unexpected error while processing uploaded document %s',
                document_id
            )
            document.ai_processed = False
            document.summary_status = Document.STATUS_FAILED
            document.processing_error = (
                'Dokumenti u ngarkua, por perpunimi AI deshtoi papritur.'
            )
            document.save(
                update_fields=[
                    'ai_processed',
                    'summary_status',
                    'processing_error',
                ]
            )
    finally:
        close_old_connections()


def schedule_uploaded_document_processing(document, user):
    if not document.file.name.lower().endswith(('.pdf', '.docx')):
        return

    document.summary_status = Document.STATUS_PROCESSING
    document.processing_error = ''
    document.save(
        update_fields=[
            'summary_status',
            'processing_error',
        ]
    )

    if settings.STUDENTAI_SYNC_UPLOAD_PROCESSING:
        process_uploaded_document_ai(document.id, user.id)
        return

    thread = threading.Thread(
        target=process_uploaded_document_ai,
        args=(document.id, user.id),
        daemon=True
    )
    thread.start()


def get_library_field_choices():
    return LibraryDocument.FIELD_CHOICES


@login_required(login_url='login')
def library_home(request):
    selected_field = request.GET.get('field', '')
    selected_type = request.GET.get('type', '')
    query = request.GET.get('q', '').strip()

    documents = LibraryDocument.objects.filter(
        moderation_status=LibraryDocument.STATUS_APPROVED,
        is_public=True
    ).select_related('uploaded_by')

    if selected_field:
        documents = documents.filter(field=selected_field)

    if selected_type:
        documents = documents.filter(document_type=selected_type)

    if query:
        documents = documents.filter(
            models.Q(title__icontains=query)
            | models.Q(course_name__icontains=query)
            | models.Q(description__icontains=query)
        )

    field_cards = [
        {
            'key': key,
            'label': label,
            'count': LibraryDocument.objects.filter(
                field=key,
                moderation_status=LibraryDocument.STATUS_APPROVED,
                is_public=True
            ).count(),
        }
        for key, label in LibraryDocument.FIELD_CHOICES
    ]

    pending_count = LibraryDocument.objects.filter(
        uploaded_by=request.user,
        moderation_status=LibraryDocument.STATUS_PENDING
    ).count()

    community_messages = CommunityMessage.objects.filter(
        is_hidden=False
    ).select_related('user')[:8]

    context = {
        'documents': documents[:60],
        'field_cards': field_cards,
        'field_choices': LibraryDocument.FIELD_CHOICES,
        'type_choices': LibraryDocument.DOCUMENT_TYPE_CHOICES,
        'selected_field': selected_field,
        'selected_type': selected_type,
        'query': query,
        'pending_count': pending_count,
        'community_messages': community_messages,
    }

    return render(
        request,
        'documents/library.html',
        context
    )


@login_required(login_url='login')
def library_upload(request):
    if request.method == 'POST':
        form = LibraryDocumentForm(request.POST, request.FILES)

        if form.is_valid():
            library_document = form.save(commit=False)
            library_document.uploaded_by = request.user
            library_document.moderation_status = LibraryDocument.STATUS_PENDING
            library_document.is_public = False
            library_document.safety_scan_notes = (
                'Student confirmation received. File extension, size, and content type checks passed. '
                'Waiting for staff moderation before public release.'
            )
            library_document.save()

            return redirect('library_submissions')
    else:
        form = LibraryDocumentForm()

    return render(
        request,
        'documents/library_upload.html',
        {'form': form}
    )


@login_required(login_url='login')
def library_submissions(request):
    submissions = LibraryDocument.objects.filter(
        uploaded_by=request.user
    ).order_by('-uploaded_at')

    return render(
        request,
        'documents/library_submissions.html',
        {'submissions': submissions}
    )


@login_required(login_url='login')
def community_chat(request):
    if request.method == 'POST':
        form = CommunityMessageForm(request.POST)

        if form.is_valid():
            message = form.save(commit=False)
            message.user = request.user
            message.save()

            return redirect('community_chat')
    else:
        form = CommunityMessageForm()

    selected_field = request.GET.get('field', '')
    messages = CommunityMessage.objects.filter(
        is_hidden=False
    ).select_related('user')

    if selected_field:
        messages = messages.filter(field=selected_field)

    return render(
        request,
        'documents/community_chat.html',
        {
            'form': form,
            'messages': messages[:80],
            'field_choices': LibraryDocument.FIELD_CHOICES,
            'selected_field': selected_field,
        }
    )


@staff_member_required
def library_moderation(request):
    submissions = LibraryDocument.objects.exclude(
        moderation_status=LibraryDocument.STATUS_APPROVED,
        is_public=True
    ).select_related('uploaded_by', 'reviewed_by')

    return render(
        request,
        'documents/library_moderation.html',
        {'submissions': submissions}
    )


@staff_member_required
def moderate_library_document(request, document_id, action):
    library_document = get_object_or_404(
        LibraryDocument,
        id=document_id
    )

    if request.method == 'POST':
        note = request.POST.get('moderation_notes', '').strip()

        if action == 'approve':
            library_document.moderation_status = LibraryDocument.STATUS_APPROVED
            library_document.is_public = True
        elif action == 'reject':
            library_document.moderation_status = LibraryDocument.STATUS_REJECTED
            library_document.is_public = False
        elif action == 'flag':
            library_document.moderation_status = LibraryDocument.STATUS_FLAGGED
            library_document.is_public = False
        else:
            raise Http404

        if note:
            library_document.moderation_notes = note

        library_document.reviewed_by = request.user
        library_document.reviewed_at = timezone.now()
        library_document.save(
            update_fields=[
                'moderation_status',
                'is_public',
                'moderation_notes',
                'reviewed_by',
                'reviewed_at',
            ]
        )

    return redirect('library_moderation')


@login_required(login_url='login')
def documents_list(request):
    documents = Document.objects.filter(
        uploaded_by=request.user
    ).order_by('-uploaded_at')

    return render(
        request,
        'documents/documents.html',
        {'documents': documents}
    )


@login_required(login_url='login')
def start_study_session(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )

    session = StudySession.objects.filter(
        user=request.user,
        document=document,
        status=StudySession.STATUS_STARTED
    ).order_by('-started_at').first()

    if session is None:
        session = StudySession.objects.create(
            user=request.user,
            document=document
        )

    return redirect(
        'study_session_detail',
        session_id=session.id
    )


@login_required(login_url='login')
def complete_study_session(request, session_id):
    session = get_object_or_404(
        StudySession,
        id=session_id,
        user=request.user
    )

    quiz_score = request.POST.get('quiz_score')
    total_questions = request.POST.get('total_questions')
    latest_quiz_attempt = QuizAttempt.objects.filter(
        user=request.user,
        document=session.document,
        created_at__gte=session.started_at
    ).order_by('-created_at').first()

    if quiz_score is not None:
        try:
            session.quiz_score = int(quiz_score)
        except (TypeError, ValueError):
            session.quiz_score = 0
    elif latest_quiz_attempt:
        session.quiz_score = latest_quiz_attempt.score

    if total_questions is not None:
        try:
            session.total_questions = int(total_questions)
        except (TypeError, ValueError):
            session.total_questions = 0
    elif latest_quiz_attempt:
        session.total_questions = latest_quiz_attempt.total_questions

    if session.total_questions > 0:
        session.session_score = round(
            (session.quiz_score / session.total_questions) * 100
        )
    else:
        session.session_score = 0

    session.status = StudySession.STATUS_COMPLETED
    session.completed_at = timezone.now()
    session.save(
        update_fields=[
            'quiz_score',
            'total_questions',
            'session_score',
            'status',
            'completed_at',
        ]
    )

    return redirect(
        'study_session_detail',
        session_id=session.id
    )


@login_required(login_url='login')
def study_session_detail(request, session_id):
    session = get_object_or_404(
        StudySession,
        id=session_id,
        user=request.user
    )

    return render(
        request,
        'documents/session_detail.html',
        {'session': session}
    )


def parse_quiz_response(raw_quiz):
    raw_quiz = raw_quiz.strip()
    raw_quiz = re.sub(r'^```(?:json)?\s*', '', raw_quiz, flags=re.IGNORECASE)
    raw_quiz = re.sub(r'\s*```$', '', raw_quiz)
    text_questions = parse_text_quiz_response(raw_quiz)

    if text_questions:
        return clean_quiz_questions(text_questions)

    try:
        if '[' in raw_quiz and ']' in raw_quiz:
            start = raw_quiz.index('[')
            end = raw_quiz.rindex(']') + 1
            questions = json.loads(raw_quiz[start:end])
        else:
            parsed = json.loads(raw_quiz)
            questions = parsed.get('questions', []) if isinstance(parsed, dict) else parsed
    except (ValueError, json.JSONDecodeError):
        questions = parse_text_quiz_response(raw_quiz)

    return clean_quiz_questions(questions)


def parse_exam_response(raw_exam):
    raw_exam = raw_exam.strip()
    raw_exam = re.sub(r'^```(?:json)?\s*', '', raw_exam, flags=re.IGNORECASE)
    raw_exam = re.sub(r'\s*```$', '', raw_exam)

    try:
        if '[' in raw_exam and ']' in raw_exam:
            start = raw_exam.index('[')
            end = raw_exam.rindex(']') + 1
            return clean_exam_questions(json.loads(raw_exam[start:end]))
    except (ValueError, json.JSONDecodeError):
        pass

    return clean_exam_questions(parse_text_exam_response(raw_exam))


def parse_text_exam_response(raw_exam):
    blocks = re.split(r'\n\s*(?=\d+[\).]\s+)', raw_exam.strip())
    questions = []

    for block in blocks:
        question_match = re.search(r'^\s*\d+[\).]\s*(.+)', block, re.MULTILINE)
        if not question_match:
            continue

        options = {}
        for key in ['A', 'B', 'C', 'D']:
            option_match = re.search(
                rf'^\s*{key}[\).:-]\s*(.+)',
                block,
                re.MULTILINE
            )
            if option_match:
                options[key] = option_match.group(1).strip()

        answer_match = re.search(
            r'(?:pergjigj(?:ja|e)|answer|correct|sakte)\D*([ABCD])',
            block,
            re.IGNORECASE
        )
        explanation_match = re.search(
            r'(?:shpjegim|explanation|arsye)\s*[:.-]\s*(.+)',
            block,
            re.IGNORECASE | re.DOTALL
        )
        explanation = explanation_match.group(1).strip() if explanation_match else ''
        explanation = re.sub(r'\n\s*\d+[\).].*$', '', explanation, flags=re.DOTALL)

        questions.append({
            'question': question_match.group(1).strip(),
            'options': options,
            'answer': answer_match.group(1).upper() if answer_match else '',
            'explanation': explanation,
        })

    return questions


def clean_exam_questions(questions):
    cleaned_questions = []

    for item in questions:
        if not isinstance(item, dict):
            continue

        options = item.get('options') or item.get('alternatives') or {}
        answer = (
            item.get('answer')
            or item.get('correct_answer')
            or item.get('correct')
            or item.get('sakte')
            or ''
        )
        answer = str(answer).strip().upper()[:1]

        if isinstance(options, list):
            options = {
                key: options[index] if index < len(options) else ''
                for index, key in enumerate(['A', 'B', 'C', 'D'])
            }

        cleaned_options = {
            key: str(options.get(key, '')).strip()
            for key in ['A', 'B', 'C', 'D']
        }

        if answer not in {'A', 'B', 'C', 'D'}:
            continue

        if not item.get('question') or not all(cleaned_options.values()):
            continue

        explanation = str(item.get('explanation', '')).strip()
        if not explanation:
            explanation = 'The correct answer is supported by the document context.'

        cleaned_questions.append({
            'question': str(item['question']).strip(),
            'options': cleaned_options,
            'answer': answer,
            'explanation': explanation,
        })

    return cleaned_questions[:10]


def clean_quiz_questions(questions):
    normalized_questions = []
    for item in questions:
        if not isinstance(item, dict):
            continue

        options = item.get('options') or item.get('alternatives') or {}
        answer = (
            item.get('answer')
            or item.get('correct_answer')
            or item.get('correct')
            or item.get('sakte')
            or ''
        )
        answer = str(answer).strip().upper()[:1]

        if answer not in {'A', 'B', 'C', 'D'}:
            continue

        if isinstance(options, list):
            options = {
                key: options[index] if index < len(options) else ''
                for index, key in enumerate(['A', 'B', 'C', 'D'])
            }

        cleaned_options = {
            key: str(options.get(key, '')).strip()
            for key in ['A', 'B', 'C', 'D']
        }

        if not item.get('question') or not all(cleaned_options.values()):
            continue

        if is_visually_obvious_quiz_item(cleaned_options, answer):
            continue

        normalized_questions.append({
            'question': str(item['question']).strip(),
            'options': cleaned_options,
            'answer': answer
        })

    random.shuffle(normalized_questions)
    normalized_questions = normalized_questions[:10]
    answer_key = build_balanced_answer_key(len(normalized_questions))
    cleaned_questions = []

    for item, target_answer in zip(normalized_questions, answer_key):
        shuffled_options, shuffled_answer = place_correct_answer(
            item['options'],
            item['answer'],
            target_answer
        )

        cleaned_questions.append({
            'question': item['question'],
            'options': shuffled_options,
            'answer': shuffled_answer
        })

    return cleaned_questions


def build_balanced_answer_key(question_count):
    answer_keys = ['A', 'B', 'C', 'D']

    if question_count <= 0:
        return []

    answer_key = [
        answer_keys[index % len(answer_keys)]
        for index in range(question_count)
    ]

    for _ in range(20):
        random.shuffle(answer_key)
        if not has_three_same_answers_in_a_row(answer_key):
            return answer_key

    return answer_key


def has_three_same_answers_in_a_row(answer_key):
    return any(
        answer_key[index] == answer_key[index + 1] == answer_key[index + 2]
        for index in range(len(answer_key) - 2)
    )


def place_correct_answer(options, answer, target_answer):
    answer_keys = ['A', 'B', 'C', 'D']
    correct_text = options[answer]
    distractors = [
        options[key]
        for key in answer_keys
        if key != answer
    ]

    random.shuffle(distractors)

    shuffled_options = {}
    distractor_index = 0

    for key in answer_keys:
        if key == target_answer:
            shuffled_options[key] = correct_text
        else:
            shuffled_options[key] = distractors[distractor_index]
            distractor_index += 1

    return shuffled_options, target_answer


def is_visually_obvious_quiz_item(options, answer):
    option_lengths = {
        key: len(value.split())
        for key, value in options.items()
    }
    correct_length = option_lengths[answer]
    distractor_lengths = [
        length
        for key, length in option_lengths.items()
        if key != answer
    ]
    longest_distractor = max(distractor_lengths)
    shortest_distractor = min(distractor_lengths)
    generic_distractor_count = sum(
        1
        for key, value in options.items()
        if key != answer and is_generic_quiz_distractor(value)
    )

    return (
        correct_length >= longest_distractor * 2
        and correct_length - shortest_distractor >= 6
    ) or generic_distractor_count >= 2


def is_generic_quiz_distractor(option):
    normalized = option.lower()
    generic_phrases = [
        'nuk permendet',
        'nuk ka lidhje',
        'informacion i pergjithshem',
        'jashte dokumentit',
        'e kunderta',
        'asnjera',
        'te gjitha',
    ]

    return any(phrase in normalized for phrase in generic_phrases)


def parse_text_quiz_response(raw_quiz):
    blocks = re.split(r'\n\s*(?=\d+[\).]\s+)', raw_quiz.strip())
    questions = []

    for block in blocks:
        question_match = re.search(r'^\s*\d+[\).]\s*(.+)', block, re.MULTILINE)
        if not question_match:
            continue

        options = {}
        for key in ['A', 'B', 'C', 'D']:
            option_match = re.search(
                rf'^\s*{key}[\).:-]\s*(.+)',
                block,
                re.MULTILINE
            )
            if option_match:
                options[key] = option_match.group(1).strip()

        answer_match = re.search(
            r'(?:pergjigj(?:ja|e)|answer|correct|sakte)\D*([ABCD])',
            block,
            re.IGNORECASE
        )

        questions.append({
            'question': question_match.group(1).strip(),
            'options': options,
            'answer': answer_match.group(1).upper() if answer_match else ''
        })

    return questions


def parse_flashcards_response(raw_flashcards):
    blocks = re.split(r'\n\s*(?=\d+[\).]\s*)', raw_flashcards.strip())
    flashcards = []

    for block in blocks:
        question_match = re.search(
            r'Pyetje\s*:\s*(.+)',
            block,
            re.IGNORECASE
        )
        answer_match = re.search(
            r'Pergjigje\s*:\s*(.+)',
            block,
            re.IGNORECASE | re.DOTALL
        )

        if not question_match or not answer_match:
            continue

        answer = answer_match.group(1).strip()
        answer = re.sub(r'\n\s*\d+[\).].*$', '', answer, flags=re.DOTALL)

        flashcards.append({
            'question': question_match.group(1).strip(),
            'answer': answer.strip()
        })

    return flashcards[:10]


def normalize_answer_words(text):
    common_words = {
        'dhe', 'ose', 'ne', 'te', 'per', 'nga', 'me', 'pa', 'qe', 'si',
        'eshte', 'jane', 'nje', 'kjo', 'ky', 'ajo', 'ai', 'tek', 'mbi',
        'nuk', 'duhet', 'mund', 'ka', 'kane', 'duke', 'shume', 'menyre'
    }
    words = re.findall(r'[a-zA-ZçÇëË]{3,}', text.lower())
    return {
        word
        for word in words
        if word not in common_words
    }


def evaluate_flashcard_answer(expected_answer, user_answer):
    expected_words = normalize_answer_words(expected_answer)
    user_words = normalize_answer_words(user_answer)
    weak_words = {
        'shfaqet', 'shfaqen', 'tregohet', 'tregohen', 'jepet', 'jepen',
        'ruhet', 'ruhen', 'krijohet', 'krijohen', 'perdoret', 'perdoren',
        'gjendet', 'gjenden', 'behet', 'behen', 'permban', 'lidhet',
        'permbledhja', 'permbledhje', 'permbledhur', 'tekst', 'teksti',
        'studenti', 'studentet', 'pergjigjja', 'pergjigje'
    }

    if not user_words:
        return {
            'score': 0,
            'label': 'Pa pergjigje',
            'feedback': 'Shkruaj nje pergjigje per te marre vleresim.'
        }

    if not expected_words:
        return {
            'score': 0,
            'label': 'Nuk u vleresua',
            'feedback': 'Pergjigjja model nuk ka fjale kyce te mjaftueshme.'
        }

    matched_words = expected_words & user_words
    base_score = round((len(matched_words) / len(expected_words)) * 100)
    strong_matches = matched_words - weak_words
    user_precision = len(matched_words) / len(user_words)

    important_match_count = len(matched_words)
    short_answer_bonus = (
        len(user_words) <= 4
        and len(strong_matches) >= 1
        and user_precision >= 0.5
    )

    if not strong_matches and base_score < 70:
        score = min(base_score, 30)
    elif short_answer_bonus:
        score = max(base_score, 75)
    elif len(strong_matches) >= 2 or (
        important_match_count >= 3
        and user_precision >= 0.5
    ):
        score = max(base_score, 60)
    else:
        score = base_score

    if score >= 70:
        label = 'Shume mire'
        feedback = 'Thelbi i pergjigjes eshte kapur mire.'
    elif score >= 40:
        label = 'Pjeserisht mire'
        feedback = 'Ke kapur nje pjese te pergjigjes, por duhet te shtosh disa fjale kyce.'
    else:
        label = 'Duhet perseritur'
        feedback = 'Pergjigjja ka pak lidhje me pergjigjen model. Rilexo kete pjese te dokumentit.'

    return {
        'score': score,
        'label': label,
        'feedback': feedback,
        'matched_words': sorted(matched_words),
        'strong_matched_words': sorted(strong_matches)
    }


def quiz_category(score, total):
    percentage = (score / total) * 100 if total else 0

    if percentage >= 90:
        return 'Ekselent'
    if percentage >= 75:
        return 'Super'
    if percentage >= 55:
        return 'Shume mire'
    if percentage >= 35:
        return 'Mire'
    return 'Dobet'


def quiz_study_advice(score, total, mistakes):
    category = quiz_category(score, total)

    if not mistakes:
        return (
            'Ke rezultat shume te forte. Per testin tjeter perserit shpejt '
            'pikat kryesore dhe provo nje quiz te ri per te ruajtur ritmin.'
        )

    if category == 'Dobet':
        return (
            'Rilexo materialin nga fillimi dhe fokusohu te konceptet baze. '
            'Pastaj provo perseri quiz-in me ritme me te ngadalta.'
        )
    if category == 'Mire':
        return (
            'Je ne drejtimin e duhur, por disa koncepte kane nevoje per perseritje. '
            'Rishiko pyetjet ku gabove dhe kerko shembuj konkrete ne dokument.'
        )
    if category == 'Shume mire':
        return (
            'Ke kuptim te mire te materialit. Per te dale me mire, perserit vetem '
            'temat ku gabove dhe krahasoji me permbledhjen AI.'
        )
    return (
        'Rezultat shume i mire. Rishiko gabimet e pakta dhe provo nje quiz te ri '
        'per te synuar nivelin Ekselent.'
    )


@login_required(login_url='login')
def upload_document(request):
    if request.method == 'POST':
        form = DocumentForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():
            document = form.save(
                commit=False
            )
            document.uploaded_by = request.user
            document.save()

            schedule_uploaded_document_processing(
                document,
                request.user
            )

            return redirect('dashboard')

    else:
        form = DocumentForm()

    return render(
        request,
        'documents/upload.html',
        {'form': form}
    )


@login_required(login_url='login')
def document_chat(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )

    answer = None
    question = ""
    error_message = None

    if request.method == "POST":
        question = request.POST.get("question", "").strip()

        if not question:
            error_message = 'Shkruaj nje pyetje per dokumentin.'
        else:
            try:
                if not consume_ai_request_quota(request.user):
                    raise AIError(ai_rate_limit_message())

                relevant_text = search_document_chunks(
                    document,
                    question,
                    n_results=8
                )

                if not relevant_text.strip():
                    error_message = 'Nuk u gjet tekst i lexueshem ne kete dokument.'
                else:
                    answer = ask_document_ai(relevant_text, question)
                    record_activity(request.user, 'chat', document.title)
            except TextExtractionError as exc:
                error_message = str(exc)
            except AIError as exc:
                error_message = str(exc)


    return render(
        request,
        "documents/chat.html",
        {
            "document": document,
            "question": question,
            "answer": answer,
            "error_message": error_message,
        }
    )


@login_required(login_url='login')
def document_chat_ask(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )

    if request.method != 'POST':
        return JsonResponse(
            {'error': 'Kerkesa duhet te jete POST.'},
            status=405
        )

    question = request.POST.get('question', '').strip()
    if not question:
        return JsonResponse(
            {'error': 'Shkruaj nje pyetje per dokumentin.'},
            status=400
        )

    try:
        if not consume_ai_request_quota(request.user):
            return JsonResponse(
                {'error': ai_rate_limit_message()},
                status=429
            )

        relevant_text = search_document_chunks(
            document,
            question,
            n_results=8
        )

        if not relevant_text.strip():
            return JsonResponse(
                {'error': 'Nuk u gjet tekst i lexueshem ne kete dokument.'},
                status=400
            )

        answer = ask_document_ai(relevant_text, question)
        record_activity(request.user, 'chat', document.title)

        return JsonResponse({
            'question': question,
            'answer': answer
        })
    except TextExtractionError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except AIError as exc:
        return JsonResponse({'error': str(exc)}, status=503)


@login_required(login_url='login')
def study_document(request, document_id):
    return document_study(request, document_id)


@login_required(login_url='login')
def document_study(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )
    quiz_session_key = f'study_quiz_{document.id}'
    raw_quiz_session_key = f'study_raw_quiz_{document.id}'
    flashcard_session_key = f'study_flashcards_{document.id}'
    raw_flashcard_session_key = f'study_raw_flashcards_{document.id}'
    chat_session_key = f'study_chat_{document.id}'
    active_tab = request.POST.get('active_tab', 'document')
    file_extension = document.file.name.rsplit('.', 1)[-1].lower()

    chat_messages = request.session.get(chat_session_key, [])
    latest_chat = chat_messages[-1] if chat_messages else {}
    chat_question = ''
    chat_answer = latest_chat.get('answer')
    questions = request.session.get(quiz_session_key)
    quiz = request.session.get(raw_quiz_session_key)
    quiz_result = None
    flashcards = request.session.get(flashcard_session_key)
    raw_flashcards = request.session.get(raw_flashcard_session_key)
    flashcard_results = None
    error_message = None
    active_study_session = StudySession.objects.filter(
        user=request.user,
        document=document,
        status=StudySession.STATUS_STARTED
    ).order_by('-started_at').first()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action in ('chat', 'ask_ai'):
            active_tab = 'chat'
            chat_question = request.POST.get('question', '').strip()
            if not chat_question:
                error_message = 'Shkruaj nje pyetje per dokumentin.'
            else:
                try:
                    if not consume_ai_request_quota(request.user):
                        raise AIError(ai_rate_limit_message())

                    relevant_text = search_document_chunks(
                        document,
                        chat_question,
                        n_results=8
                    )

                    chat_answer = ask_document_ai(relevant_text, chat_question)
                    chat_messages.append({
                        'question': chat_question,
                        'answer': chat_answer
                    })
                    request.session[chat_session_key] = chat_messages
                    record_activity(request.user, 'chat', document.title)
                    chat_question = ''
                except TextExtractionError as exc:
                    error_message = str(exc)
                except AIError as exc:
                    error_message = str(exc)

        elif action == 'generate_quiz':
            active_tab = 'quiz'
            request.session.pop(quiz_session_key, None)
            request.session.pop(raw_quiz_session_key, None)
            try:
                if not consume_ai_request_quota(request.user):
                    raise AIError(ai_rate_limit_message())

                text = extract_text_from_document(document.file.path)
                raw_quiz = generate_quiz(
                    text,
                    previous_questions=get_previous_quiz_questions(
                        request.user,
                        documents=[document]
                    ),
                    context_chunks=get_random_document_chunks(document)
                )
                quiz = raw_quiz
                questions = parse_quiz_response(raw_quiz)
                random.shuffle(questions)
                if questions:
                    request.session[quiz_session_key] = questions
                    request.session[raw_quiz_session_key] = raw_quiz
                    record_activity(request.user, 'quiz', document.title)
                else:
                    error_message = 'AI nuk arriti te gjeneroje quiz te vlefshem.'
                    questions = []
            except TextExtractionError as exc:
                error_message = str(exc)
                questions = []
            except AIError as exc:
                error_message = str(exc)
                questions = []

        elif action == 'submit_quiz':
            active_tab = 'quiz'
            if not questions:
                error_message = 'Gjenero nje quiz para se te besh submit.'
            else:
                score = 0
                submitted_questions = []
                mistakes = []

                for index, question in enumerate(questions):
                    selected = request.POST.get(f'question_{index}', '')
                    is_correct = selected == question['answer']

                    if is_correct:
                        score += 1

                    submitted_questions.append({
                        **question,
                        'selected': selected,
                        'is_correct': is_correct
                    })

                    if not is_correct:
                        mistakes.append({
                            'number': index + 1,
                            'question': question['question'],
                            'selected': selected or 'Pa pergjigje',
                            'answer': question['answer']
                        })

                quiz_result = {
                    'score': score,
                    'total': len(questions),
                    'category': quiz_category(score, len(questions)),
                    'advice': quiz_study_advice(score, len(questions), mistakes),
                    'mistakes': mistakes
                }
                QuizAttempt.objects.create(
                    document=document,
                    user=request.user,
                    score=score,
                    total=len(questions),
                    category=quiz_result['category'],
                    mistakes=mistakes
                )
                questions = submitted_questions

        elif action == 'generate_flashcards':
            active_tab = 'flashcards'
            request.session.pop(flashcard_session_key, None)
            request.session.pop(raw_flashcard_session_key, None)
            try:
                if not consume_ai_request_quota(request.user):
                    raise AIError(ai_rate_limit_message())

                text = extract_text_from_document(document.file.path)
                raw_flashcards = generate_flashcards(text)
                flashcards = parse_flashcards_response(raw_flashcards)
                random.shuffle(flashcards)
                if flashcards:
                    request.session[flashcard_session_key] = flashcards
                    request.session[raw_flashcard_session_key] = raw_flashcards
                    record_activity(request.user, 'flashcards', document.title)
                else:
                    error_message = 'AI nuk arriti te gjeneroje flashcards te vlefshme.'
                    flashcards = []
            except TextExtractionError as exc:
                error_message = str(exc)
                flashcards = []
            except AIError as exc:
                error_message = str(exc)
                flashcards = []

        elif action == 'submit_flashcards':
            active_tab = 'flashcards'
            if not flashcards:
                error_message = 'Gjenero flashcards para se te kontrollosh pergjigjet.'
            else:
                cards = []
                total_score = 0

                for index, flashcard in enumerate(flashcards):
                    user_answer = request.POST.get(f'answer_{index}', '').strip()
                    evaluation = evaluate_flashcard_answer(
                        flashcard['answer'],
                        user_answer
                    )
                    total_score += evaluation['score']
                    cards.append({
                        **flashcard,
                        'user_answer': user_answer,
                        'evaluation': evaluation
                    })

                average_score = round(total_score / len(flashcards), 1) if flashcards else 0
                if average_score >= 70:
                    overall_label = 'Shume mire'
                elif average_score >= 40:
                    overall_label = 'Mire, por ka vend per perseritje'
                else:
                    overall_label = 'Duhet perseritur'

                flashcard_results = {
                    'cards': cards,
                    'average_score': average_score,
                    'overall_label': overall_label
                }
                FlashcardAttempt.objects.create(
                    document=document,
                    user=request.user,
                    average_score=average_score,
                    category=overall_label,
                    cards=cards
                )
                flashcards = cards

    return render(
        request,
        'documents/study.html',
        {
            'document': document,
            'file_extension': file_extension,
            'is_pdf': file_extension == 'pdf',
            'active_tab': active_tab,
            'chat_question': chat_question,
            'chat_answer': chat_answer,
            'question': chat_question,
            'ai_answer': chat_answer,
            'chat_messages': chat_messages,
            'active_study_session': active_study_session,
            'quiz': quiz,
            'questions': questions,
            'quiz_result': quiz_result,
            'flashcards': raw_flashcards or flashcards,
            'flashcard_items': flashcards,
            'flashcard_results': flashcard_results,
            'error_message': error_message
        }
    )


@login_required(login_url='login')
def exam_simulator(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )

    questions = []
    raw_exam = ''
    error_message = None

    try:
        if not consume_ai_request_quota(request.user):
            raise AIError(ai_rate_limit_message())

        text = extract_text_from_document(document.file.path)
        if not text.strip():
            error_message = 'Nuk u gjet tekst i lexueshem ne kete dokument.'
        else:
            raw_exam = generate_exam(text)
            questions = parse_exam_response(raw_exam)
            if not questions:
                error_message = 'AI nuk arriti te gjeneroje simulim provimi nga ky dokument.'
            else:
                record_activity(request.user, 'quiz', document.title)
    except TextExtractionError as exc:
        error_message = str(exc)
    except AIError as exc:
        error_message = str(exc)

    return render(
        request,
        'documents/exam_simulator.html',
        {
            'document': document,
            'questions': questions,
            'raw_exam': raw_exam,
            'error_message': error_message,
        }
    )


@login_required(login_url='login')
def multi_document_chat(request):
    documents = Document.objects.filter(
        uploaded_by=request.user
    )

    question = ''
    answer = None
    error_message = None

    if request.method == 'POST':
        question = request.POST.get('question', '').strip()

        if not question:
            error_message = 'Shkruaj nje pyetje.'
        else:
            try:
                if not consume_ai_request_quota(request.user):
                    raise AIError(ai_rate_limit_message())

                relevant_text = search_multiple_documents(
                    documents,
                    question
                )

                if not relevant_text.strip():
                    relevant_text = combine_documents_text(documents)

                if not relevant_text.strip():
                    error_message = 'Nuk u gjet tekst i lexueshem nga dokumentet e tua.'
                else:
                    answer = ask_document_ai(
                        relevant_text,
                        question
                    )
            except AIError as exc:
                error_message = str(exc)

    return render(
        request,
        'documents/multi_document_chat.html',
        {
            'documents': documents,
            'question': question,
            'answer': answer,
            'error_message': error_message,
        }
    )


@login_required(login_url='login')
def multi_document_study(request):
    documents = Document.objects.filter(
        uploaded_by=request.user
    ).order_by('-uploaded_at')
    selected_documents = []
    selected_document_ids = []
    action = ''
    question = ''
    answer = None
    questions = None
    quiz_result = None
    flashcards = None
    flashcard_results = None
    error_message = None

    if request.method == 'POST':
        action = request.POST.get('action', '')
        selected_document_ids = request.POST.getlist('documents')
        selected_documents = list(
            get_selected_documents(request, selected_document_ids)
        )

        if action == 'submit_quiz':
            questions = request.session.get('multi_document_quiz', [])
            score = 0
            submitted_questions = []
            mistakes = []

            for index, item in enumerate(questions):
                selected = request.POST.get(f'question_{index}', '')
                is_correct = selected == item['answer']

                if is_correct:
                    score += 1

                submitted_questions.append({
                    **item,
                    'selected': selected,
                    'is_correct': is_correct
                })

                if not is_correct:
                    mistakes.append({
                        'number': index + 1,
                        'question': item['question'],
                        'selected': selected or 'Pa pergjigje',
                        'answer': item['answer']
                    })

            quiz_result = {
                'score': score,
                'total': len(questions),
                'category': quiz_category(score, len(questions)),
                'advice': quiz_study_advice(score, len(questions), mistakes),
                'mistakes': mistakes
            }
            questions = submitted_questions

        elif action == 'submit_flashcards':
            flashcards = request.session.get('multi_document_flashcards', [])
            cards = []
            total_score = 0

            for index, item in enumerate(flashcards):
                user_answer = request.POST.get(f'answer_{index}', '').strip()
                evaluation = evaluate_flashcard_answer(
                    item['answer'],
                    user_answer
                )
                total_score += evaluation['score']
                cards.append({
                    **item,
                    'user_answer': user_answer,
                    'evaluation': evaluation
                })

            average_score = round(total_score / len(flashcards), 1) if flashcards else 0
            if average_score >= 70:
                overall_label = 'Shume mire'
            elif average_score >= 40:
                overall_label = 'Mire, por ka vend per perseritje'
            else:
                overall_label = 'Duhet perseritur'

            flashcard_results = {
                'cards': cards,
                'average_score': average_score,
                'overall_label': overall_label
            }
            flashcards = []

        elif not selected_documents:
            error_message = 'Zgjidh te pakten nje dokument.'

        else:
            try:
                combined_text = combine_documents_text(selected_documents)

                if not combined_text.strip():
                    error_message = 'Nuk u gjet tekst i lexueshem ne dokumentet e zgjedhura.'
                elif action == 'chat':
                    question = request.POST.get('question', '').strip()
                    if not question:
                        error_message = 'Shkruaj nje pyetje per Chat AI.'
                    else:
                        if not consume_ai_request_quota(request.user):
                            raise AIError(ai_rate_limit_message())

                        answer = ask_document_ai(combined_text, question)
                        record_activity(
                            request.user,
                            'chat',
                            ', '.join(document.title for document in selected_documents)
                        )
                elif action == 'quiz':
                    if not consume_ai_request_quota(request.user):
                        raise AIError(ai_rate_limit_message())

                    raw_quiz = generate_quiz(
                        combined_text,
                        previous_questions=get_previous_quiz_questions(
                            request.user,
                            documents=selected_documents
                        )
                    )
                    questions = parse_quiz_response(raw_quiz)
                    random.shuffle(questions)
                    request.session['multi_document_quiz'] = questions
                    if not questions:
                        error_message = 'AI nuk arriti te gjeneroje quiz nga dokumentet e zgjedhura.'
                    else:
                        record_activity(
                            request.user,
                            'quiz',
                            ', '.join(document.title for document in selected_documents)
                        )
                elif action == 'flashcards':
                    if not consume_ai_request_quota(request.user):
                        raise AIError(ai_rate_limit_message())

                    raw_flashcards = generate_flashcards(combined_text)
                    flashcards = parse_flashcards_response(raw_flashcards)
                    random.shuffle(flashcards)
                    request.session['multi_document_flashcards'] = flashcards
                    if not flashcards:
                        error_message = 'AI nuk arriti te gjeneroje flashcards nga dokumentet e zgjedhura.'
                    else:
                        record_activity(
                            request.user,
                            'flashcards',
                            ', '.join(document.title for document in selected_documents)
                        )
            except TextExtractionError as exc:
                error_message = str(exc)
            except AIError as exc:
                error_message = str(exc)

    return render(
        request,
        'documents/multi_study.html',
        {
            'documents': documents,
            'selected_document_ids': [str(id_value) for id_value in selected_document_ids],
            'selected_documents': selected_documents,
            'action': action,
            'question': question,
            'answer': answer,
            'questions': questions,
            'quiz_result': quiz_result,
            'flashcards': flashcards,
            'flashcard_results': flashcard_results,
            'error_message': error_message
        }
    )


@login_required(login_url='login')
def document_quiz(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )

    session_key = f'document_quiz_{document.id}'
    questions = request.session.get(session_key)
    result = None
    error_message = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'new':
            request.session.pop(session_key, None)
            return redirect('document_quiz', document_id=document.id)

        if not questions:
            return redirect('document_quiz', document_id=document.id)

        score = 0
        submitted_questions = []
        mistakes = []

        for index, question in enumerate(questions):
            selected = request.POST.get(f'question_{index}', '')
            is_correct = selected == question['answer']

            if is_correct:
                score += 1

            submitted_questions.append({
                **question,
                'selected': selected,
                'is_correct': is_correct
            })

            if not is_correct:
                mistakes.append({
                    'number': index + 1,
                    'question': question['question'],
                    'selected': selected or 'Pa pergjigje',
                    'answer': question['answer']
                })

        result = {
            'score': score,
            'total': len(questions),
            'category': quiz_category(score, len(questions)),
            'advice': quiz_study_advice(score, len(questions), mistakes),
            'mistakes': mistakes
        }

        QuizAttempt.objects.create(
            document=document,
            user=request.user,
            score=score,
            total=len(questions),
            category=result['category'],
            mistakes=mistakes
        )
        questions = submitted_questions

    if request.method == 'GET' and not questions:
        try:
            if not consume_ai_request_quota(request.user):
                raise AIError(ai_rate_limit_message())

            text = extract_text_from_document(document.file.path)
            if not text.strip():
                error_message = 'Nuk u gjet tekst i lexueshem ne kete dokument.'
                questions = []
            else:
                raw_quiz = generate_quiz(
                    text,
                    previous_questions=get_previous_quiz_questions(
                        request.user,
                        documents=[document]
                    ),
                    context_chunks=get_random_document_chunks(document)
                )
                questions = parse_quiz_response(raw_quiz)

                if not questions:
                    error_message = (
                        'AI nuk arriti te gjeneroje nje quiz te vlefshem nga teksti i ketij dokumenti. '
                        'Provo perseri ose ngarko nje dokument me tekst me te qarte.'
                    )
                    questions = []
                else:
                    record_activity(request.user, 'quiz', document.title)

            request.session[session_key] = questions
        except TextExtractionError as exc:
            error_message = str(exc)
            questions = []
        except AIError as exc:
            error_message = str(exc)
            questions = []

    return render(
        request,
        'documents/quiz.html',
        {
            'document': document,
            'questions': questions,
            'result': result,
            'error_message': error_message
        }
    )


@login_required(login_url='login')
def document_flashcards(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )

    session_key = f'document_flashcards_{document.id}'
    flashcards = request.session.get(session_key)
    results = None
    error_message = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'new':
            request.session.pop(session_key, None)
            return redirect('document_flashcards', document_id=document.id)

        if not flashcards:
            return redirect('document_flashcards', document_id=document.id)

        results = []
        total_score = 0

        for index, flashcard in enumerate(flashcards):
            user_answer = request.POST.get(f'answer_{index}', '').strip()
            evaluation = evaluate_flashcard_answer(
                flashcard['answer'],
                user_answer
            )
            total_score += evaluation['score']
            results.append({
                **flashcard,
                'user_answer': user_answer,
                'evaluation': evaluation
            })

        average_score = round(total_score / len(flashcards), 1) if flashcards else 0
        if average_score >= 70:
            overall_label = 'Shume mire'
        elif average_score >= 40:
            overall_label = 'Mire, por ka vend per perseritje'
        else:
            overall_label = 'Duhet perseritur'

        results = {
            'cards': results,
            'average_score': average_score,
            'overall_label': overall_label
        }
        FlashcardAttempt.objects.create(
            document=document,
            user=request.user,
            average_score=average_score,
            category=overall_label,
            cards=results['cards']
        )

    if request.method == 'GET' and not flashcards:
        try:
            if not consume_ai_request_quota(request.user):
                raise AIError(ai_rate_limit_message())

            text = extract_text_from_document(document.file.path)
            if not text.strip():
                error_message = 'Nuk u gjet tekst i lexueshem ne kete dokument.'
                flashcards = []
            else:
                raw_flashcards = generate_flashcards(text)
                flashcards = parse_flashcards_response(raw_flashcards)
                random.shuffle(flashcards)
                if not flashcards:
                    error_message = (
                        'AI nuk arriti te gjeneroje flashcards te vlefshme. '
                        'Provo perseri.'
                    )
                    flashcards = []
                else:
                    record_activity(request.user, 'flashcards', document.title)
            request.session[session_key] = flashcards
        except TextExtractionError as exc:
            error_message = str(exc)
            flashcards = []
        except AIError as exc:
            error_message = str(exc)
            flashcards = []

    return render(
        request,
        'documents/flashcards.html',
        {
            'document': document,
            'flashcards': flashcards,
            'results': results,
            'error_message': error_message
        }
    )


@login_required(login_url='login')
def quiz_history(request):
    attempts = QuizAttempt.objects.filter(
        user=request.user
    ).select_related('document').order_by('-created_at')

    total_attempts = attempts.count()
    best_attempt = attempts.order_by('-score', 'total', '-created_at').first()
    latest_attempt = attempts.first()

    total_score = sum(attempt.score for attempt in attempts)
    total_questions = sum(attempt.total for attempt in attempts)
    average_percentage = round(
        (total_score / total_questions) * 100
    ) if total_questions else 0
    chart_attempts = list(reversed(list(attempts[:10])))
    chart_labels = [
        attempt.created_at.strftime('%d/%m')
        for attempt in chart_attempts
    ]
    chart_scores = [
        attempt.percentage
        for attempt in chart_attempts
    ]

    if total_attempts == 0:
        progress_message = 'Ende nuk ke kryer quiz-e.'
    elif total_attempts == 1:
        progress_message = 'Ke kryer quiz-in e pare. Vazhdo me disa teste te tjera per te pare ecurine.'
    elif latest_attempt and best_attempt and latest_attempt.id == best_attempt.id:
        progress_message = 'Rezultati yt i fundit eshte edhe me i miri deri tani.'
    else:
        progress_message = 'Shiko pyetjet ku ke gabuar me shpesh dhe perserit ato tema para quiz-it tjeter.'

    return render(
        request,
        'documents/quiz_history.html',
        {
            'attempts': attempts,
            'total_attempts': total_attempts,
            'best_attempt': best_attempt,
            'latest_attempt': latest_attempt,
            'average_percentage': average_percentage,
            'progress_message': progress_message,
            'chart_labels': chart_labels,
            'chart_scores': chart_scores
        }
    )


@login_required(login_url='login')
def flashcard_history(request):
    attempts = FlashcardAttempt.objects.filter(
        user=request.user
    ).select_related('document').order_by('-created_at')

    total_attempts = attempts.count()
    latest_attempt = attempts.first()
    best_attempt = attempts.order_by('-average_score', '-created_at').first()
    average_percentage = round(
        sum(attempt.average_score for attempt in attempts) / total_attempts
    ) if total_attempts else 0

    chart_attempts = list(reversed(list(attempts[:10])))
    chart_labels = [
        attempt.created_at.strftime('%d/%m')
        for attempt in chart_attempts
    ]
    chart_scores = [
        attempt.average_score
        for attempt in chart_attempts
    ]

    if total_attempts == 0:
        progress_message = 'Ende nuk ke kryer flashcards.'
    elif total_attempts == 1:
        progress_message = 'Ke kryer setin e pare te flashcards. Vazhdo per te pare progresin.'
    elif latest_attempt and best_attempt and latest_attempt.id == best_attempt.id:
        progress_message = 'Rezultati yt i fundit eshte edhe me i miri deri tani.'
    else:
        progress_message = 'Perserit flashcards ku rezultati ishte me i ulet dhe provo perseri.'

    return render(
        request,
        'documents/flashcard_history.html',
        {
            'attempts': attempts,
            'total_attempts': total_attempts,
            'latest_attempt': latest_attempt,
            'best_attempt': best_attempt,
            'average_percentage': average_percentage,
            'progress_message': progress_message,
            'chart_labels': chart_labels,
            'chart_scores': chart_scores
        }
    )


@login_required(login_url='login')
def document_detail(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )

    file_extension = document.file.name.rsplit('.', 1)[-1].lower()
    show_extracted_text = request.GET.get('view') == 'text'
    extracted_text = ''
    error_message = None

    if show_extracted_text:
        try:
            extracted_text = extract_text_from_document(document.file.path)
            if not extracted_text:
                error_message = 'Nuk u gjet tekst ne kete dokument.'
        except TextExtractionError as exc:
            error_message = str(exc)

    return render(
        request,
        'documents/detail.html',
        {
            'document': document,
            'file_extension': file_extension,
            'is_pdf': file_extension == 'pdf',
            'show_extracted_text': show_extracted_text,
            'extracted_text': extracted_text,
            'error_message': error_message
        }
    )


@login_required(login_url='login')
@xframe_options_sameorigin
def document_file(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )
    file_path = document.file.path
    if not Path(file_path).exists():
        raise Http404('Dokumenti nuk u gjet.')

    content_type, _ = mimetypes.guess_type(file_path)

    return FileResponse(
        open(file_path, 'rb'),
        as_attachment=False,
        filename=Path(document.file.name).name,
        content_type=content_type or 'application/octet-stream'
    )

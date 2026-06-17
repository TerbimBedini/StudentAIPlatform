import json
import mimetypes
import random
import re
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .ai import (
    AIError,
    ask_document_ai,
    generate_flashcards,
    generate_quiz,
    generate_summary,
)
from .forms import DocumentForm
from .models import Activity, Document, FlashcardAttempt, QuizAttempt
from .utils import TextExtractionError, extract_text_from_document


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


def clean_quiz_questions(questions):
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

        cleaned_questions.append({
            'question': str(item['question']).strip(),
            'options': cleaned_options,
            'answer': answer
        })

    return cleaned_questions[:10]


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
        'nuk', 'duhet', 'mund', 'ka', 'kane', 'duke'
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

    important_match_count = len(matched_words)
    short_answer_bonus = (
        len(user_words) <= 4
        and important_match_count >= 1
    )

    if short_answer_bonus:
        score = max(base_score, 75)
    elif important_match_count >= 2:
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
        'matched_words': sorted(matched_words)
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

            if document.file.name.lower().endswith(('.pdf', '.docx')):
                try:
                    text = extract_text_from_document(document.file.path)
                    document.summary = generate_summary(text)
                    document.ai_processed = True
                    document.save(update_fields=['summary', 'ai_processed'])
                    record_activity(request.user, 'summary', document.title)
                except (AIError, TextExtractionError):
                    document.ai_processed = False
                    document.save(update_fields=['ai_processed'])

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
                text = extract_text_from_document(document.file.path)
                if not text:
                    error_message = 'Nuk u gjet tekst i lexueshem ne kete dokument.'
                else:
                    answer = ask_document_ai(text, question)
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
        text = extract_text_from_document(document.file.path)
        if not text:
            return JsonResponse(
                {'error': 'Nuk u gjet tekst i lexueshem ne kete dokument.'},
                status=400
            )

        answer = ask_document_ai(text, question)
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
def document_study(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )
    quiz_session_key = f'study_quiz_{document.id}'
    flashcard_session_key = f'study_flashcards_{document.id}'
    active_tab = request.POST.get('active_tab', 'document')
    file_extension = document.file.name.rsplit('.', 1)[-1].lower()

    chat_question = ''
    chat_answer = None
    questions = request.session.get(quiz_session_key)
    quiz_result = None
    flashcards = request.session.get(flashcard_session_key)
    flashcard_results = None
    error_message = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'chat':
            active_tab = 'chat'
            chat_question = request.POST.get('question', '').strip()
            if not chat_question:
                error_message = 'Shkruaj nje pyetje per dokumentin.'
            else:
                try:
                    text = extract_text_from_document(document.file.path)
                    chat_answer = ask_document_ai(text, chat_question)
                    record_activity(request.user, 'chat', document.title)
                except TextExtractionError as exc:
                    error_message = str(exc)
                except AIError as exc:
                    error_message = str(exc)

        elif action == 'generate_quiz':
            active_tab = 'quiz'
            request.session.pop(quiz_session_key, None)
            try:
                text = extract_text_from_document(document.file.path)
                raw_quiz = generate_quiz(text)
                questions = parse_quiz_response(raw_quiz)
                random.shuffle(questions)
                if questions:
                    request.session[quiz_session_key] = questions
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
            try:
                text = extract_text_from_document(document.file.path)
                raw_flashcards = generate_flashcards(text)
                flashcards = parse_flashcards_response(raw_flashcards)
                random.shuffle(flashcards)
                if flashcards:
                    request.session[flashcard_session_key] = flashcards
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

                average_score = round(total_score / len(flashcards)) if flashcards else 0
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
            'questions': questions,
            'quiz_result': quiz_result,
            'flashcards': flashcards,
            'flashcard_results': flashcard_results,
            'error_message': error_message
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

            average_score = round(total_score / len(flashcards)) if flashcards else 0
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
                        answer = ask_document_ai(combined_text, question)
                        record_activity(
                            request.user,
                            'chat',
                            ', '.join(document.title for document in selected_documents)
                        )
                elif action == 'quiz':
                    raw_quiz = generate_quiz(combined_text)
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
            text = extract_text_from_document(document.file.path)
            if not text.strip():
                error_message = 'Nuk u gjet tekst i lexueshem ne kete dokument.'
                questions = []
            else:
                raw_quiz = generate_quiz(text)
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

        average_score = round(total_score / len(flashcards)) if flashcards else 0
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

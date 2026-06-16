import json
import mimetypes
import re
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .ai import AIError, ask_document_ai, generate_quiz, generate_summary
from .forms import DocumentForm
from .models import Document, QuizAttempt
from .utils import TextExtractionError, extract_text_from_document, extract_text_from_pdf


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

            if document.file.name.endswith('.pdf'):
                try:
                    text = extract_text_from_pdf(document.file.path)
                    document.summary = generate_summary(text)
                    document.ai_processed = True
                    document.save(update_fields=['summary', 'ai_processed'])
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
            text = extract_text_from_pdf(document.file.path)
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
            'progress_message': progress_message
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

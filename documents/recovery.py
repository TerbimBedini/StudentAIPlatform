from django.apps import apps

from .models import Document, QuizAttempt
from .progress import get_completed_sessions_count, get_flashcard_activity


def _get_model(model_name):
    try:
        return apps.get_model('documents', model_name)
    except LookupError:
        return None


def _attempt_percentage(attempt):
    percentage = getattr(attempt, 'percentage', None)

    if percentage is not None:
        return percentage

    total = getattr(attempt, 'total_questions', 0) or getattr(attempt, 'total', 0)
    score = getattr(attempt, 'score', 0)

    if not total:
        return 0

    return (score / total) * 100


def _clamp_score(value):
    return max(0, min(100, value))


def _document_performance(user):
    attempts = QuizAttempt.objects.filter(
        user=user
    ).select_related('document')

    performance = {}

    for attempt in attempts:
        document = getattr(attempt, 'document', None)
        if document is None:
            continue

        performance.setdefault(document.id, {
            'document': document,
            'topic': document.title,
            'scores': [],
        })
        performance[document.id]['scores'].append(_attempt_percentage(attempt))

    topics = []

    for item in performance.values():
        scores = item['scores']
        if not scores:
            continue

        topics.append({
            'document': item['document'],
            'topic': item['topic'],
            'average_score': round(sum(scores) / len(scores), 1),
            'attempts_count': len(scores),
        })

    return topics


def _weakness_level(score):
    if score < 40:
        return 'Critical'
    if score < 50:
        return 'High'
    return 'Moderate'


def _recovery_action(score):
    if score < 40:
        return 'Start a study session, review the summary, then retry with flashcards.'
    if score < 50:
        return 'Practice flashcards first, then take a focused recovery quiz.'
    return 'Review missed ideas and retake a short quiz for this topic.'


def _quiz_improvement_score(user):
    attempts = list(
        QuizAttempt.objects.filter(user=user).order_by('created_at')
    )

    if len(attempts) < 2:
        return 0

    split_index = max(1, len(attempts) // 2)
    early_attempts = attempts[:split_index]
    recent_attempts = attempts[split_index:]

    if not recent_attempts:
        recent_attempts = attempts[-1:]

    early_average = sum(
        _attempt_percentage(attempt)
        for attempt in early_attempts
    ) / len(early_attempts)

    recent_average = sum(
        _attempt_percentage(attempt)
        for attempt in recent_attempts
    ) / len(recent_attempts)

    improvement = max(0, recent_average - early_average)
    return _clamp_score(improvement * 5)


def get_recovery_score(user):
    quiz_improvement = _quiz_improvement_score(user)
    flashcard_accuracy = _clamp_score(get_flashcard_activity(user))
    study_activity = _clamp_score(get_completed_sessions_count(user) * 20)

    recovery_score = (
        quiz_improvement * 0.4
        + flashcard_accuracy * 0.35
        + study_activity * 0.25
    )

    return int(round(_clamp_score(recovery_score)))


def get_recovery_plan(user):
    if not Document.objects.filter(uploaded_by=user).exists():
        return []

    weak_topics = [
        topic
        for topic in _document_performance(user)
        if topic['average_score'] < 60
    ]

    recovery_plan = []

    for topic in sorted(weak_topics, key=lambda item: item['average_score']):
        document = topic['document']
        average_score = topic['average_score']

        recovery_plan.append({
            'document': document,
            'document_id': document.id,
            'topic': topic['topic'],
            'average_score': average_score,
            'weakness_level': _weakness_level(average_score),
            'recovery_action': _recovery_action(average_score),
            'recommended_quiz': f'Generate a focused quiz for {topic["topic"]}.',
            'recommended_flashcards': f'Practice flashcards for {topic["topic"]}.',
            'recommended_study_session': f'Start a recovery study session for {topic["topic"]}.',
        })

    return recovery_plan

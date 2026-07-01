from django.apps import apps

from .models import Document, QuizAttempt
from .progress import calculate_knowledge_score, get_quiz_accuracy


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


def _document_topic_scores(user):
    attempts = QuizAttempt.objects.filter(
        user=user
    ).select_related('document')

    topic_scores = {}

    for attempt in attempts:
        document = getattr(attempt, 'document', None)
        if document is None:
            continue

        topic_scores.setdefault(document.id, {
            'document': document,
            'topic': document.title,
            'scores': [],
        })
        topic_scores[document.id]['scores'].append(
            _attempt_percentage(attempt)
        )

    topic_averages = []

    for item in topic_scores.values():
        scores = item['scores']
        if not scores:
            continue

        topic_averages.append({
            'document': item['document'],
            'topic': item['topic'],
            'average_score': round(sum(scores) / len(scores), 1),
            'attempts_count': len(scores),
        })

    return topic_averages


def get_strong_topics(user):
    topics = [
        topic
        for topic in _document_topic_scores(user)
        if topic['average_score'] >= 80
    ]

    return sorted(
        topics,
        key=lambda item: item['average_score'],
        reverse=True
    )


def get_weak_topics(user):
    topics = [
        topic
        for topic in _document_topic_scores(user)
        if topic['average_score'] < 60
    ]

    return sorted(
        topics,
        key=lambda item: item['average_score']
    )


def _completed_sessions_count(user):
    StudySession = _get_model('StudySession')

    if StudySession is None:
        return 0

    sessions = StudySession.objects.filter(user=user)

    if hasattr(StudySession, 'STATUS_COMPLETED'):
        return sessions.filter(status=StudySession.STATUS_COMPLETED).count()

    if any(field.name == 'completed_at' for field in StudySession._meta.fields):
        return sessions.exclude(completed_at__isnull=True).count()

    if any(field.name == 'status' for field in StudySession._meta.fields):
        return sessions.filter(status='completed').count()

    return 0


def get_exam_readiness(user):
    quiz_accuracy = _clamp_score(get_quiz_accuracy(user))
    knowledge_score = _clamp_score(calculate_knowledge_score(user))
    study_activity = _clamp_score(_completed_sessions_count(user) * 20)

    readiness = (
        quiz_accuracy * 0.4
        + knowledge_score * 0.4
        + study_activity * 0.2
    )

    return round(_clamp_score(readiness), 1)


def get_recommended_document(user):
    topic_scores = _document_topic_scores(user)

    if topic_scores:
        weakest_topic = sorted(
            topic_scores,
            key=lambda item: item['average_score']
        )[0]
        return weakest_topic['document']

    return Document.objects.filter(
        uploaded_by=user
    ).order_by('-uploaded_at').first()


def get_recommended_action(user):
    documents = Document.objects.filter(uploaded_by=user)

    if not documents.exists():
        return 'Upload your first document.'

    if not QuizAttempt.objects.filter(user=user).exists():
        return 'Generate your first quiz.'

    if get_weak_topics(user):
        return 'Review weak topics using flashcards and summaries.'

    if get_exam_readiness(user) < 60:
        return 'Complete more quizzes before taking an exam simulation.'

    if get_exam_readiness(user) >= 80:
        return 'You are ready for an exam simulation.'

    return 'Continue practicing quizzes and study sessions.'

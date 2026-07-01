from datetime import timedelta

from django.utils import timezone

from .learning_diagnosis import (
    get_exam_readiness,
    get_recommended_action,
    get_recommended_document,
    get_strong_topics,
    get_weak_topics,
)
from .models import QuizAttempt, StudySession
from .progress import calculate_knowledge_score, get_quiz_accuracy


def _attempt_percentage(attempt):
    total = getattr(attempt, 'total', 0) or getattr(attempt, 'total_questions', 0)
    if not total:
        return 0
    return (getattr(attempt, 'score', 0) / total) * 100


def get_study_consistency(user, days=7):
    since = timezone.now() - timedelta(days=days)
    sessions = StudySession.objects.filter(
        user=user,
        status=StudySession.STATUS_COMPLETED,
        completed_at__gte=since
    )
    active_days = {
        session.completed_at.date()
        for session in sessions
        if session.completed_at
    }
    return round((len(active_days) / days) * 100, 1)


def get_most_improved_topic(user):
    attempts = QuizAttempt.objects.filter(
        user=user
    ).select_related('document').order_by('created_at')
    grouped_attempts = {}

    for attempt in attempts:
        document = getattr(attempt, 'document', None)
        if document is None:
            continue
        grouped_attempts.setdefault(document.id, {
            'topic': document.title,
            'scores': [],
        })
        grouped_attempts[document.id]['scores'].append(
            _attempt_percentage(attempt)
        )

    improvements = []
    for item in grouped_attempts.values():
        scores = item['scores']
        if len(scores) < 2:
            continue
        improvements.append({
            'topic': item['topic'],
            'improvement': round(scores[-1] - scores[0], 1),
            'latest_score': round(scores[-1], 1),
        })

    if not improvements:
        return None

    return max(improvements, key=lambda item: item['improvement'])


def get_recommended_study_duration(user):
    readiness = get_exam_readiness(user)
    weak_topics = get_weak_topics(user)

    if not QuizAttempt.objects.filter(user=user).exists():
        return 25
    if weak_topics or readiness < 60:
        return 45
    if readiness < 80:
        return 35
    return 25


def get_daily_study_goal(user):
    weak_topics = get_weak_topics(user)
    duration = get_recommended_study_duration(user)

    if not QuizAttempt.objects.filter(user=user).exists():
        primary_task = 'Complete your first quiz'
    elif weak_topics:
        primary_task = f'Review {weak_topics[0]["topic"]}'
    else:
        primary_task = 'Maintain your progress with a mixed quiz'

    return {
        'duration_minutes': duration,
        'primary_task': primary_task,
        'quiz_target': 1,
        'flashcard_target': 5 if weak_topics else 3,
    }


def get_learning_coach_report(user):
    weak_topics = get_weak_topics(user)
    strong_topics = get_strong_topics(user)
    recommended_document = get_recommended_document(user)
    most_improved_topic = get_most_improved_topic(user)
    exam_readiness = get_exam_readiness(user)
    knowledge_score = calculate_knowledge_score(user)
    quiz_accuracy = get_quiz_accuracy(user)
    study_consistency = get_study_consistency(user)
    daily_goal = get_daily_study_goal(user)

    weakest_topic = weak_topics[0] if weak_topics else None
    strongest_topic = strong_topics[0] if strong_topics else None

    if weakest_topic:
        today_focus = weakest_topic['topic']
    elif recommended_document:
        today_focus = recommended_document.title
    else:
        today_focus = 'Upload a document'

    if weakest_topic:
        recommendation = f'Review {weakest_topic["topic"]}, then complete one focused quiz.'
    else:
        recommendation = get_recommended_action(user)

    return {
        'study_consistency': study_consistency,
        'knowledge_score': knowledge_score,
        'quiz_accuracy': round(quiz_accuracy, 1),
        'weak_topics': weak_topics,
        'strong_topics': strong_topics,
        'weakest_topic': weakest_topic,
        'strongest_topic': strongest_topic,
        'recommended_next_lesson': recommended_document,
        'recommended_study_duration': daily_goal['duration_minutes'],
        'daily_study_goal': daily_goal,
        'exam_readiness': exam_readiness,
        'exam_probability': exam_readiness,
        'most_improved_topic': most_improved_topic,
        'today_focus': today_focus,
        'today_recommendation': recommendation,
    }

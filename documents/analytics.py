from datetime import timedelta

from django.utils import timezone

from .learning_diagnosis import get_exam_readiness, get_strong_topics, get_weak_topics
from .models import Document, FlashcardAttempt, QuizAttempt, StudySession
from .progress import calculate_knowledge_score, get_quiz_accuracy


def _attempt_percentage(attempt):
    total = getattr(attempt, 'total', 0) or getattr(attempt, 'total_questions', 0)
    if not total:
        return 0
    return (getattr(attempt, 'score', 0) / total) * 100


def _completed_sessions(user):
    return StudySession.objects.filter(
        user=user,
        status=StudySession.STATUS_COMPLETED
    )


def get_weekly_study_hours(user):
    since = timezone.now() - timedelta(days=7)
    sessions = _completed_sessions(user).filter(completed_at__gte=since)
    minutes = sessions.count() * 30
    return round(minutes / 60, 1)


def get_monthly_progress(user):
    since = timezone.now() - timedelta(days=30)
    documents_count = Document.objects.filter(
        uploaded_by=user,
        uploaded_at__gte=since
    ).count()
    quizzes_count = QuizAttempt.objects.filter(
        user=user,
        created_at__gte=since
    ).count()
    flashcards_count = FlashcardAttempt.objects.filter(
        user=user,
        created_at__gte=since
    ).count()
    sessions_count = _completed_sessions(user).filter(
        completed_at__gte=since
    ).count()

    activity_score = min(
        100,
        documents_count * 10
        + quizzes_count * 15
        + flashcards_count * 10
        + sessions_count * 10
    )

    return {
        'documents': documents_count,
        'quizzes': quizzes_count,
        'flashcards': flashcards_count,
        'study_sessions': sessions_count,
        'activity_score': activity_score,
    }


def get_quiz_accuracy_trend(user):
    attempts = list(
        QuizAttempt.objects.filter(user=user).order_by('created_at')
    )
    trend = [
        {
            'label': attempt.created_at.strftime('%d/%m'),
            'value': round(_attempt_percentage(attempt), 1),
        }
        for attempt in attempts[-6:]
    ]
    current = round(get_quiz_accuracy(user), 1)
    previous = trend[-2]['value'] if len(trend) >= 2 else 0

    return {
        'current': current,
        'change': round(current - previous, 1) if trend else 0,
        'points': trend,
    }


def get_flashcard_success_rate(user):
    attempts = FlashcardAttempt.objects.filter(user=user)
    if not attempts.exists():
        return {
            'current': 0,
            'attempts': 0,
            'points': [],
        }

    scores = [
        max(0, min(100, attempt.average_score or 0))
        for attempt in attempts.order_by('created_at')
    ]

    return {
        'current': round(sum(scores) / len(scores), 1),
        'attempts': len(scores),
        'points': [
            {
                'label': attempt.created_at.strftime('%d/%m'),
                'value': round(max(0, min(100, attempt.average_score or 0)), 1),
            }
            for attempt in attempts.order_by('created_at')[:6]
        ],
    }


def get_knowledge_growth(user):
    attempts = list(
        QuizAttempt.objects.filter(user=user).order_by('created_at')
    )
    current = calculate_knowledge_score(user)
    if len(attempts) < 2:
        return {
            'current': current,
            'growth': 0,
        }

    first_score = _attempt_percentage(attempts[0])
    latest_score = _attempt_percentage(attempts[-1])
    return {
        'current': current,
        'growth': round(latest_score - first_score, 1),
    }


def get_exam_readiness_trend(user):
    readiness = get_exam_readiness(user)
    return {
        'current': readiness,
        'points': [
            {'label': 'Now', 'value': readiness},
        ],
    }


def get_weak_topics_chart(user):
    return [
        {
            'topic': topic['topic'],
            'value': topic['average_score'],
        }
        for topic in get_weak_topics(user)[:5]
    ]


def get_strong_topics_chart(user):
    return [
        {
            'topic': topic['topic'],
            'value': topic['average_score'],
        }
        for topic in get_strong_topics(user)[:5]
    ]


def get_learning_streak(user):
    sessions = _completed_sessions(user).exclude(
        completed_at__isnull=True
    ).order_by('-completed_at')
    active_dates = {
        session.completed_at.date()
        for session in sessions
        if session.completed_at
    }

    streak = 0
    current_day = timezone.localdate()
    while current_day in active_dates:
        streak += 1
        current_day -= timedelta(days=1)

    return streak


def get_dashboard_analytics(user):
    return {
        'weekly_study_hours': get_weekly_study_hours(user),
        'monthly_progress': get_monthly_progress(user),
        'quiz_accuracy_trend': get_quiz_accuracy_trend(user),
        'flashcard_success_rate': get_flashcard_success_rate(user),
        'knowledge_growth': get_knowledge_growth(user),
        'exam_readiness_trend': get_exam_readiness_trend(user),
        'weak_topics_chart': get_weak_topics_chart(user),
        'strong_topics_chart': get_strong_topics_chart(user),
        'learning_streak': get_learning_streak(user),
    }

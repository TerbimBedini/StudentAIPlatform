from datetime import timedelta

from django.utils import timezone

from .learning_diagnosis import get_exam_readiness
from .models import Achievement, Document, FlashcardAttempt, QuizAttempt, StudySession
from .progress import calculate_knowledge_score


def _completed_sessions(user):
    return StudySession.objects.filter(
        user=user,
        status=StudySession.STATUS_COMPLETED
    )


def _learning_streak(user):
    active_dates = {
        session.completed_at.date()
        for session in _completed_sessions(user).exclude(completed_at__isnull=True)
        if session.completed_at
    }
    streak = 0
    current_day = timezone.localdate()

    while current_day in active_dates:
        streak += 1
        current_day -= timedelta(days=1)

    return streak


def _flashcard_cards_count(user):
    total = 0
    for attempt in FlashcardAttempt.objects.filter(user=user):
        cards = attempt.cards or []
        total += len(cards) if isinstance(cards, list) else 0
    return total


def _perfect_quiz_count(user):
    return QuizAttempt.objects.filter(
        user=user,
        total__gt=0,
        score=models_f('total')
    ).count()


def models_f(field_name):
    from django.db.models import F

    return F(field_name)


def get_available_achievements():
    return [
        {
            'badge_type': 'first_upload',
            'title': 'First Upload',
            'description': 'Uploaded your first study document.',
            'target': 1,
            'metric': 'documents',
            'icon': 'bi-file-earmark-arrow-up',
        },
        {
            'badge_type': 'first_quiz',
            'title': 'First Quiz',
            'description': 'Completed your first quiz.',
            'target': 1,
            'metric': 'quizzes',
            'icon': 'bi-patch-question',
        },
        {
            'badge_type': 'first_flashcards',
            'title': 'First Flashcards',
            'description': 'Completed your first flashcard review.',
            'target': 1,
            'metric': 'flashcard_attempts',
            'icon': 'bi-card-checklist',
        },
        {
            'badge_type': 'study_10',
            'title': '10 Study Sessions',
            'description': 'Completed 10 focused study sessions.',
            'target': 10,
            'metric': 'completed_sessions',
            'icon': 'bi-journal-check',
        },
        {
            'badge_type': 'flashcards_100',
            'title': '100 Flashcards',
            'description': 'Reviewed 100 flashcards.',
            'target': 100,
            'metric': 'flashcard_cards',
            'icon': 'bi-stack',
        },
        {
            'badge_type': 'perfect_quiz',
            'title': 'Perfect Quiz',
            'description': 'Scored 100% on a quiz.',
            'target': 1,
            'metric': 'perfect_quizzes',
            'icon': 'bi-trophy',
        },
        {
            'badge_type': 'streak_7',
            'title': '7 Day Streak',
            'description': 'Studied for 7 days in a row.',
            'target': 7,
            'metric': 'learning_streak',
            'icon': 'bi-fire',
        },
        {
            'badge_type': 'streak_30',
            'title': '30 Day Streak',
            'description': 'Studied for 30 days in a row.',
            'target': 30,
            'metric': 'learning_streak',
            'icon': 'bi-calendar-heart',
        },
        {
            'badge_type': 'exam_master',
            'title': 'Exam Master',
            'description': 'Reached at least 80% exam readiness.',
            'target': 80,
            'metric': 'exam_readiness',
            'icon': 'bi-mortarboard',
        },
        {
            'badge_type': 'ai_scholar',
            'title': 'AI Scholar',
            'description': 'Reached a knowledge score of 90.',
            'target': 90,
            'metric': 'knowledge_score',
            'icon': 'bi-stars',
        },
        {
            'badge_type': 'consistent_learner',
            'title': 'Consistent Learner',
            'description': 'Completed 3 study sessions in the last week.',
            'target': 3,
            'metric': 'weekly_sessions',
            'icon': 'bi-repeat',
        },
        {
            'badge_type': 'knowledge_builder',
            'title': 'Knowledge Builder',
            'description': 'Reached a knowledge score of 50.',
            'target': 50,
            'metric': 'knowledge_score',
            'icon': 'bi-graph-up-arrow',
        },
    ]


def _achievement_metrics(user):
    now = timezone.now()
    weekly_sessions = _completed_sessions(user).filter(
        completed_at__gte=now - timedelta(days=7)
    ).count()

    return {
        'documents': Document.objects.filter(uploaded_by=user).count(),
        'quizzes': QuizAttempt.objects.filter(user=user).count(),
        'flashcard_attempts': FlashcardAttempt.objects.filter(user=user).count(),
        'completed_sessions': _completed_sessions(user).count(),
        'flashcard_cards': _flashcard_cards_count(user),
        'perfect_quizzes': _perfect_quiz_count(user),
        'learning_streak': _learning_streak(user),
        'exam_readiness': get_exam_readiness(user),
        'knowledge_score': calculate_knowledge_score(user),
        'weekly_sessions': weekly_sessions,
    }


def check_and_award_achievements(user):
    metrics = _achievement_metrics(user)
    awarded = []

    for definition in get_available_achievements():
        current = metrics.get(definition['metric'], 0)
        if current < definition['target']:
            continue

        achievement, created = Achievement.objects.get_or_create(
            user=user,
            badge_type=definition['badge_type'],
            defaults={
                'title': definition['title'],
                'description': definition['description'],
            }
        )
        if created:
            awarded.append(achievement)

    return awarded


def get_user_achievements(user):
    return Achievement.objects.filter(user=user).order_by('-created_at')


def get_achievement_progress(user):
    metrics = _achievement_metrics(user)
    earned_types = set(
        Achievement.objects.filter(user=user).values_list('badge_type', flat=True)
    )
    progress = []

    for definition in get_available_achievements():
        current = metrics.get(definition['metric'], 0)
        target = definition['target']
        percentage = 100 if target <= 0 else min(100, round((current / target) * 100, 1))
        progress.append({
            **definition,
            'current': current,
            'percentage': percentage,
            'earned': definition['badge_type'] in earned_types,
        })

    return progress

from django.apps import apps

from .learning_diagnosis import get_exam_readiness, get_weak_topics
from .models import QuizAttempt
from .progress import calculate_knowledge_score, get_completed_sessions_count


EXAM_MODES = (
    'adaptive',
    'easy',
    'medium',
    'hard',
    'mixed',
    'weak_topics',
)


def normalize_exam_mode(value):
    value = (value or 'adaptive').strip().lower().replace('-', '_').replace(' ', '_')
    if value in {'weak_topic_focus', 'weak_topics_focus'}:
        value = 'weak_topics'
    if value not in EXAM_MODES:
        return 'adaptive'
    return value


def _flashcard_attempts_count(user):
    try:
        FlashcardAttempt = apps.get_model('documents', 'FlashcardAttempt')
    except LookupError:
        return 0
    return FlashcardAttempt.objects.filter(user=user).count()


def get_exam_strategy(user, document, requested_mode='adaptive'):
    requested_mode = normalize_exam_mode(requested_mode)
    weak_topics = get_weak_topics(user)
    knowledge_score = calculate_knowledge_score(user)
    exam_readiness = get_exam_readiness(user)
    completed_sessions = get_completed_sessions_count(user)
    quiz_attempts = QuizAttempt.objects.filter(
        user=user,
        document=document
    ).count()
    flashcard_attempts = _flashcard_attempts_count(user)

    if requested_mode == 'adaptive':
        if weak_topics or knowledge_score < 45 or exam_readiness < 55:
            difficulty = 'easy'
        elif knowledge_score >= 80 and exam_readiness >= 80 and completed_sessions >= 3:
            difficulty = 'hard'
        else:
            difficulty = 'medium'
        mode = 'adaptive'
    elif requested_mode == 'weak_topics':
        difficulty = 'medium'
        mode = 'weak_topics'
    elif requested_mode == 'mixed':
        difficulty = 'mixed'
        mode = 'mixed'
    else:
        difficulty = requested_mode
        mode = requested_mode

    focus_topics = [
        topic['topic']
        for topic in weak_topics[:3]
    ] or [document.title]

    if mode == 'weak_topics':
        instruction = 'Prioritize weak topics and common mistakes from previous attempts.'
    elif difficulty == 'easy':
        instruction = 'Use foundational questions that check basic understanding.'
    elif difficulty == 'hard':
        instruction = 'Use challenging questions that require reasoning and concept explanation.'
    elif mode == 'mixed':
        instruction = 'Mix question types and difficulty levels across the document context.'
    else:
        instruction = 'Use balanced mock-exam questions across the main document concepts.'

    if requested_mode == 'adaptive':
        instruction += (
            ' Adaptive mode uses knowledge score, weak topics, quiz attempts, '
            'flashcard attempts, study sessions, and exam readiness.'
        )

    return {
        'requested_mode': requested_mode,
        'mode': mode,
        'difficulty': difficulty,
        'focus_topics': focus_topics,
        'instruction': instruction,
        'knowledge_score': knowledge_score,
        'exam_readiness': exam_readiness,
        'completed_sessions': completed_sessions,
        'quiz_attempts': quiz_attempts,
        'flashcard_attempts': flashcard_attempts,
        'estimated_minutes': 15,
    }

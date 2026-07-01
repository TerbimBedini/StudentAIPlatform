from .learning_diagnosis import get_exam_readiness, get_weak_topics
from .models import QuizAttempt
from .progress import calculate_knowledge_score, get_completed_sessions_count


DIFFICULTY_LEVELS = ('easy', 'medium', 'hard', 'adaptive')


def normalize_quiz_difficulty(value):
    value = (value or 'adaptive').strip().lower()
    if value not in DIFFICULTY_LEVELS:
        return 'adaptive'
    return value


def get_quiz_strategy(user, document, requested_difficulty='adaptive'):
    requested_difficulty = normalize_quiz_difficulty(requested_difficulty)
    weak_topics = get_weak_topics(user)
    knowledge_score = calculate_knowledge_score(user)
    exam_readiness = get_exam_readiness(user)
    completed_sessions = get_completed_sessions_count(user)
    previous_attempts = QuizAttempt.objects.filter(
        user=user,
        document=document
    ).count()

    if requested_difficulty == 'adaptive':
        if weak_topics or knowledge_score < 45 or exam_readiness < 55:
            difficulty = 'easy'
        elif knowledge_score >= 80 and exam_readiness >= 80 and completed_sessions >= 3:
            difficulty = 'hard'
        else:
            difficulty = 'medium'
    else:
        difficulty = requested_difficulty

    if weak_topics:
        focus_topics = [
            topic['topic']
            for topic in weak_topics[:3]
        ]
    else:
        focus_topics = [document.title]

    if difficulty == 'easy':
        instruction = (
            'Use clear foundational questions. Test key ideas and basic understanding.'
        )
    elif difficulty == 'hard':
        instruction = (
            'Use challenging analytical questions that require comparison, reasoning, and application.'
        )
    else:
        instruction = (
            'Use balanced questions that test understanding, application, and important concepts.'
        )

    if requested_difficulty == 'adaptive':
        instruction += (
            ' Adaptive mode: prioritize weak topics, previous mistakes, study activity, '
            'knowledge score, and exam readiness.'
        )

    return {
        'requested_difficulty': requested_difficulty,
        'difficulty': difficulty,
        'focus_topics': focus_topics,
        'instruction': instruction,
        'knowledge_score': knowledge_score,
        'exam_readiness': exam_readiness,
        'completed_sessions': completed_sessions,
        'previous_attempts': previous_attempts,
    }

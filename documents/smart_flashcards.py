from .learning_diagnosis import get_exam_readiness, get_weak_topics
from .models import QuizAttempt
from .progress import calculate_knowledge_score, get_completed_sessions_count


FLASHCARD_MODES = (
    'adaptive',
    'definitions',
    'concepts',
    'true_false',
    'fill_blank',
    'memory',
)


def normalize_flashcard_mode(value):
    value = (value or 'adaptive').strip().lower().replace('-', '_')
    if value in {'truefalse', 'true_false'}:
        value = 'true_false'
    if value in {'fill_blank', 'fill_in_blank', 'fill_in_the_blank'}:
        value = 'fill_blank'
    if value not in FLASHCARD_MODES:
        return 'adaptive'
    return value


def get_flashcard_strategy(user, document, requested_mode='adaptive'):
    requested_mode = normalize_flashcard_mode(requested_mode)
    weak_topics = get_weak_topics(user)
    knowledge_score = calculate_knowledge_score(user)
    exam_readiness = get_exam_readiness(user)
    completed_sessions = get_completed_sessions_count(user)
    previous_attempts = QuizAttempt.objects.filter(
        user=user,
        document=document
    ).count()

    if requested_mode == 'adaptive':
        if weak_topics:
            mode = 'concepts'
        elif knowledge_score < 45 or exam_readiness < 55:
            mode = 'definitions'
        elif knowledge_score >= 80 and completed_sessions >= 3:
            mode = 'memory'
        else:
            mode = 'fill_blank'
    else:
        mode = requested_mode

    focus_topics = [
        topic['topic']
        for topic in weak_topics[:3]
    ] or [document.title]

    instructions = {
        'definitions': 'Create definition-focused cards for key terms and concise meanings.',
        'concepts': 'Create concept cards that test understanding, relationships, and important ideas.',
        'true_false': 'Create true/false cards. The question should start with "True or False:" and the answer should explain briefly.',
        'fill_blank': 'Create fill-in-the-blank cards using one important missing term or phrase.',
        'memory': 'Create memory cards that help recall facts, causes, steps, and core details.',
    }

    instruction = instructions.get(mode, instructions['concepts'])
    if requested_mode == 'adaptive':
        instruction += (
            ' Adaptive mode: prioritize weak topics, previous quiz attempts, '
            'knowledge score, study sessions, and exam readiness.'
        )

    return {
        'requested_mode': requested_mode,
        'mode': mode,
        'focus_topics': focus_topics,
        'instruction': instruction,
        'knowledge_score': knowledge_score,
        'exam_readiness': exam_readiness,
        'completed_sessions': completed_sessions,
        'previous_attempts': previous_attempts,
    }

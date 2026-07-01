from .learning_diagnosis import (
    get_exam_readiness,
    get_recommended_action,
    get_recommended_document,
    get_strong_topics,
    get_weak_topics,
)
from .models import Document, QuizAttempt
from .progress import (
    calculate_knowledge_score,
    get_completed_sessions_count,
    get_quiz_accuracy,
)
from .recovery import get_recovery_score


def _clamp_score(value):
    return max(0, min(100, value))


def _study_activity_score(user):
    return _clamp_score(get_completed_sessions_count(user) * 20)


def get_exam_prediction(user):
    quiz_score = _clamp_score(get_quiz_accuracy(user))
    recovery_score = _clamp_score(get_recovery_score(user))
    knowledge_score = _clamp_score(calculate_knowledge_score(user))
    study_activity = _study_activity_score(user)

    prediction = (
        quiz_score * 0.4
        + recovery_score * 0.2
        + knowledge_score * 0.3
        + study_activity * 0.1
    )

    return int(round(_clamp_score(prediction)))


def get_exam_risk(user):
    prediction = get_exam_prediction(user)

    if prediction >= 80:
        return 'LOW'
    if prediction >= 60:
        return 'MEDIUM'
    return 'HIGH'


def get_exam_strengths(user):
    return get_strong_topics(user)


def get_exam_weaknesses(user):
    return get_weak_topics(user)


def _recommended_actions(user, prediction, risk):
    if not Document.objects.filter(uploaded_by=user).exists():
        return ['Upload your first document to begin exam preparation.']

    if not QuizAttempt.objects.filter(user=user).exists():
        return ['Generate your first quiz to unlock an exam prediction.']

    weaknesses = get_exam_weaknesses(user)

    if weaknesses:
        return [
            'Review weak topics with summaries and flashcards.',
            'Complete a focused recovery quiz for your lowest scoring document.',
            'Start a study session before taking the exam simulator.',
        ]

    if risk == 'HIGH':
        return [
            'Complete more quizzes before taking an exam simulation.',
            'Use flashcards to build recall on core concepts.',
        ]

    if risk == 'MEDIUM':
        return [
            'Take one more practice quiz and review any missed concepts.',
            'Try a short exam simulation after a study session.',
        ]

    return [
        'You are ready for an exam simulation.',
        'Use the simulator to confirm timing and question readiness.',
    ]


def get_exam_report(user):
    prediction = get_exam_prediction(user)
    readiness = get_exam_readiness(user)
    recovery_score = get_recovery_score(user)
    risk = get_exam_risk(user)
    recommended_document = get_recommended_document(user)

    return {
        'predicted_exam_score': prediction,
        'exam_readiness': readiness,
        'recovery_score': recovery_score,
        'knowledge_score': calculate_knowledge_score(user),
        'quiz_accuracy': round(get_quiz_accuracy(user), 1),
        'study_activity': _study_activity_score(user),
        'strong_topics': get_exam_strengths(user),
        'weak_topics': get_exam_weaknesses(user),
        'exam_risk': risk,
        'recommended_document': recommended_document,
        'recommended_action': get_recommended_action(user),
        'recommended_actions': _recommended_actions(user, prediction, risk),
    }

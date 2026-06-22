from django.apps import apps

from .models import Achievement, Document, QuizAttempt


def _get_model(model_name):
    try:
        return apps.get_model('documents', model_name)
    except LookupError:
        return None


def _attempt_percentage(attempt):
    percentage = getattr(attempt, 'percentage', None)

    if percentage is not None:
        return percentage

    total_questions = getattr(attempt, 'total_questions', 0)
    if not total_questions:
        total_questions = getattr(attempt, 'total', 0)

    if not total_questions:
        return 0

    return (getattr(attempt, 'score', 0) / total_questions) * 100


def _clamp_score(value):
    return max(0, min(100, value))


def get_quiz_accuracy(user):
    attempts = QuizAttempt.objects.filter(user=user)

    if not attempts.exists():
        return 0

    scores = [
        _attempt_percentage(attempt)
        for attempt in attempts
    ]

    return sum(scores) / len(scores)


def get_completed_sessions_count(user):
    StudySession = _get_model('StudySession')

    if StudySession is None:
        return 0

    queryset = StudySession.objects.filter(user=user)

    if hasattr(StudySession, 'STATUS_COMPLETED'):
        return queryset.filter(
            status=StudySession.STATUS_COMPLETED
        ).count()

    if any(field.name == 'completed_at' for field in StudySession._meta.fields):
        return queryset.exclude(completed_at__isnull=True).count()

    if any(field.name == 'status' for field in StudySession._meta.fields):
        return queryset.filter(status='completed').count()

    return 0


def get_flashcard_activity(user):
    FlashcardAttempt = _get_model('FlashcardAttempt')

    if FlashcardAttempt is None:
        return 0

    attempts = FlashcardAttempt.objects.filter(user=user)

    if not attempts.exists():
        return 0

    if any(field.name == 'average_score' for field in FlashcardAttempt._meta.fields):
        scores = [
            getattr(attempt, 'average_score', 0) or 0
            for attempt in attempts
        ]
        return _clamp_score(sum(scores) / len(scores))

    return _clamp_score(attempts.count() * 20)


def calculate_knowledge_score(user):
    quiz_accuracy = _clamp_score(get_quiz_accuracy(user))
    session_activity = _clamp_score(get_completed_sessions_count(user) * 20)
    flashcard_activity = _clamp_score(get_flashcard_activity(user))

    score = (
        quiz_accuracy * 0.5
        + session_activity * 0.3
        + flashcard_activity * 0.2
    )

    return int(round(_clamp_score(score)))


def get_learning_level(score):
    score = _clamp_score(score)

    if score <= 20:
        return 'Beginner'
    if score <= 40:
        return 'Learner'
    if score <= 60:
        return 'Intermediate'
    if score <= 80:
        return 'Advanced'

    return 'Expert'


def get_next_study_recommendation(user):
    documents = Document.objects.filter(uploaded_by=user)

    if not documents.exists():
        return 'Upload your first document to start learning.'

    if not QuizAttempt.objects.filter(user=user).exists():
        return 'Generate and complete a quiz to measure your understanding.'

    quiz_accuracy = get_quiz_accuracy(user)

    if quiz_accuracy < 60:
        return 'Review your weak topics using summaries and flashcards.'

    if quiz_accuracy < 80:
        return 'Continue practicing quizzes to improve your Knowledge Score.'

    return 'Great progress. Try an advanced exam simulation or a new document.'


def calculate_average_quiz_score(user):
    return get_quiz_accuracy(user)


def calculate_improvement_rate(user):
    attempts = list(
        QuizAttempt.objects.filter(user=user).order_by('created_at')
    )

    if len(attempts) < 6:
        return 0

    first_three = attempts[:3]
    last_three = attempts[-3:]

    first_average = sum(
        _attempt_percentage(attempt)
        for attempt in first_three
    ) / 3

    last_average = sum(
        _attempt_percentage(attempt)
        for attempt in last_three
    ) / 3

    return last_average - first_average


def analyze_student_strengths(user):
    attempts = QuizAttempt.objects.filter(
        user=user
    ).select_related('document')

    if not attempts.exists():
        return {
            'strong_areas': [],
            'weak_areas': [],
            'recommendation': 'Generate your first quiz from a document to unlock a learning diagnosis.',
        }

    topic_scores = {}

    for attempt in attempts:
        topic_name = attempt.document.title
        topic_scores.setdefault(topic_name, []).append(
            _attempt_percentage(attempt)
        )

    topic_averages = [
        {
            'topic': topic_name,
            'average_score': round(sum(scores) / len(scores), 1),
        }
        for topic_name, scores in topic_scores.items()
    ]

    strong_areas = [
        topic
        for topic in topic_averages
        if topic['average_score'] >= 80
    ]
    weak_areas = [
        topic
        for topic in topic_averages
        if topic['average_score'] < 60
    ]

    strong_areas = sorted(
        strong_areas,
        key=lambda item: item['average_score'],
        reverse=True
    )
    weak_areas = sorted(
        weak_areas,
        key=lambda item: item['average_score']
    )

    if weak_areas:
        weakest_topic = weak_areas[0]['topic']
        recommendation = (
            f'Review "{weakest_topic}" first, then generate a new quiz to check progress.'
        )
    elif strong_areas:
        recommendation = (
            'Your quiz results are strong. Keep practicing with mixed quizzes and flashcards to maintain momentum.'
        )
    else:
        recommendation = (
            'Your results are developing. Complete more quizzes so StudentAI can identify clearer strengths and weak areas.'
        )

    return {
        'strong_areas': strong_areas,
        'weak_areas': weak_areas,
        'recommendation': recommendation,
    }


def get_next_study_action(user):
    documents = Document.objects.filter(uploaded_by=user)

    if not documents.exists():
        return 'Upload your first document to start learning.'

    summaries_count = documents.exclude(
        summary__isnull=True
    ).exclude(
        summary=''
    ).count()

    if summaries_count == 0:
        return 'Generate AI summaries for your uploaded materials.'

    if not QuizAttempt.objects.filter(user=user).exists():
        return 'Take your first quiz to measure your understanding.'

    average_quiz_score = calculate_average_quiz_score(user)

    if average_quiz_score < 60:
        return 'Review your weak topics and practice with flashcards.'

    if average_quiz_score < 80:
        return 'Continue practicing quizzes to improve your knowledge score.'

    return 'Great progress! Try advanced quizzes or start a new study session.'


def check_and_award_achievements(user):
    average_quiz_score = calculate_average_quiz_score(user)
    knowledge_score = calculate_knowledge_score(user)

    badge_definitions = [
        {
            'badge_type': Achievement.BADGE_FIRST_UPLOAD,
            'title': 'First Upload',
            'description': 'Uploaded your first study document.',
            'earned': Document.objects.filter(uploaded_by=user).exists(),
        },
        {
            'badge_type': Achievement.BADGE_FIRST_QUIZ,
            'title': 'First Quiz',
            'description': 'Completed your first AI-generated quiz.',
            'earned': QuizAttempt.objects.filter(user=user).exists(),
        },
        {
            'badge_type': Achievement.BADGE_QUIZ_MASTER,
            'title': 'Quiz Master',
            'description': 'Reached at least 85% average quiz accuracy.',
            'earned': average_quiz_score >= 85,
        },
        {
            'badge_type': Achievement.BADGE_KNOWLEDGE_100,
            'title': 'Knowledge 100',
            'description': 'Reached a knowledge score of 100.',
            'earned': knowledge_score >= 100,
        },
        {
            'badge_type': Achievement.BADGE_KNOWLEDGE_500,
            'title': 'Knowledge 500',
            'description': 'Reached a knowledge score of 500.',
            'earned': knowledge_score >= 500,
        },
        {
            'badge_type': Achievement.BADGE_KNOWLEDGE_1000,
            'title': 'Knowledge 1000',
            'description': 'Reached a knowledge score of 1000.',
            'earned': knowledge_score >= 1000,
        },
    ]

    awarded = []

    for badge in badge_definitions:
        if not badge['earned']:
            continue

        achievement, created = Achievement.objects.get_or_create(
            user=user,
            badge_type=badge['badge_type'],
            defaults={
                'title': badge['title'],
                'description': badge['description'],
            }
        )

        if created:
            awarded.append(achievement)

    return awarded

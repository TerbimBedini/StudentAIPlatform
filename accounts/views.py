from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from .forms import RegisterForm
from documents.models import (
    Achievement,
    Activity,
    Document,
    QuizAttempt,
    StudySession,
)
from documents.progress import (
    analyze_student_strengths,
    calculate_average_quiz_score,
    calculate_improvement_rate,
    calculate_knowledge_score,
    check_and_award_achievements,
    get_completed_sessions_count,
    get_flashcard_activity,
    get_learning_level,
    get_next_study_recommendation,
    get_next_study_action,
    get_quiz_accuracy,
)


def home(request):
    return render(request, 'accounts/home.html')


@sensitive_post_parameters('password')
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    error_message = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect('dashboard')

        error_message = 'Username ose password gabim.'

    return render(
        request,
        'accounts/login.html',
        {'error_message': error_message}
    )


@sensitive_post_parameters('password1', 'password2')
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':

        form = RegisterForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('login')

    else:
        form = RegisterForm()

    return render(
        request,
        'accounts/register.html',
        {'form': form}
    )



@login_required(login_url='login')
def dashboard(request):
    check_and_award_achievements(request.user)

    documents = Document.objects.filter(
        uploaded_by=request.user
    ).order_by('-uploaded_at')

    activities = Activity.objects.filter(
        user=request.user
    ).order_by('-created_at')

    summaries_count = documents.exclude(
        summary__isnull=True
    ).exclude(
        summary=''
    ).count()

    quizzes_count = QuizAttempt.objects.filter(
        user=request.user
    ).count()

    study_sessions = StudySession.objects.filter(
        user=request.user
    )

    active_study_sessions = study_sessions.filter(
        status=StudySession.STATUS_STARTED
    )

    completed_study_sessions = study_sessions.filter(
        status=StudySession.STATUS_COMPLETED
    )

    achievements = Achievement.objects.filter(
        user=request.user
    ).order_by('-created_at')

    learning_diagnosis = analyze_student_strengths(request.user)
    quiz_accuracy = get_quiz_accuracy(request.user)
    completed_sessions_count = get_completed_sessions_count(request.user)
    flashcard_activity = get_flashcard_activity(request.user)
    knowledge_score = calculate_knowledge_score(request.user)

    context = {
        'documents': documents,
        'documents_count': documents.count(),
        'summaries_count': summaries_count,
        'quizzes_count': quizzes_count,
        'flashcards_count': flashcard_activity,
        'average_quiz_score': round(calculate_average_quiz_score(request.user), 1),
        'improvement_rate': round(calculate_improvement_rate(request.user), 1),
        'quiz_accuracy': round(quiz_accuracy, 1),
        'completed_sessions_count': completed_sessions_count,
        'flashcard_activity': round(flashcard_activity, 1),
        'knowledge_score': knowledge_score,
        'learning_level': get_learning_level(knowledge_score),
        'next_study_recommendation': get_next_study_recommendation(request.user),
        'quiz_attempts_count': quizzes_count,
        'flashcard_attempts_count': flashcard_activity,
        'total_study_sessions': study_sessions.count(),
        'completed_study_sessions': completed_study_sessions.count(),
        'active_study_sessions': active_study_sessions.count(),
        'last_study_sessions': study_sessions.order_by('-started_at')[:5],
        'recent_achievements': achievements[:5],
        'achievements_count': achievements.count(),
        'activities': activities[:10],
        'summary_count': summaries_count,
        'chat_count': activities.filter(activity_type='chat').count(),
        'quiz_count': quizzes_count,
        'total_points': sum(activity.points for activity in activities),
        'strong_areas': learning_diagnosis['strong_areas'],
        'weak_areas': learning_diagnosis['weak_areas'],
        'learning_recommendation': learning_diagnosis['recommendation'],
        'next_study_action': get_next_study_action(request.user),
    }

    return render(
        request,
        'accounts/dashboard.html',
        context
    )


@login_required(login_url='login')
def study_plan(request):
    documents = Document.objects.filter(
        uploaded_by=request.user
    ).order_by('-uploaded_at')
    learning_diagnosis = analyze_student_strengths(request.user)
    weak_areas = learning_diagnosis['weak_areas']
    knowledge_score = calculate_knowledge_score(request.user)
    first_document = documents.first()
    has_documents = documents.exists()

    plan_days = [
        {
            'day': 1,
            'title': 'Review weak areas',
            'description': 'Start with the topics where your quiz scores need the most attention.',
        },
        {
            'day': 2,
            'title': 'Read summaries',
            'description': 'Go through AI summaries and mark the concepts that still feel unclear.',
        },
        {
            'day': 3,
            'title': 'Generate flashcards',
            'description': 'Turn important ideas into flashcards and practice active recall.',
        },
        {
            'day': 4,
            'title': 'Take quizzes',
            'description': 'Use quizzes to measure what you remember without looking at notes.',
        },
        {
            'day': 5,
            'title': 'Review wrong and weak topics',
            'description': 'Revisit mistakes and compare your answers with the document material.',
        },
        {
            'day': 6,
            'title': 'Multi-document chat practice',
            'description': 'Ask cross-topic questions and connect ideas across your uploaded materials.',
        },
        {
            'day': 7,
            'title': 'Final quiz and review',
            'description': 'Finish with a final quiz, then review the weak areas that remain.',
        },
    ]

    return render(
        request,
        'accounts/study_plan.html',
        {
            'documents': documents,
            'has_documents': has_documents,
            'weak_areas': weak_areas,
            'knowledge_score': knowledge_score,
            'plan_days': plan_days,
            'first_document': first_document,
            'empty_message': 'Upload documents first to generate your study plan.',
        }
    )


@login_required(login_url='login')
def leaderboard(request):
    User = get_user_model()
    user_ids = set(
        QuizAttempt.objects.values_list('user_id', flat=True)
    )
    user_ids.update(
        Document.objects.values_list('uploaded_by_id', flat=True)
    )

    if StudySession is not None:
        user_ids.update(
            StudySession.objects.values_list('user_id', flat=True)
        )

    users = User.objects.filter(id__in=user_ids)
    rankings = [
        {
            'rank': index,
            'user': user,
            'knowledge_score': calculate_knowledge_score(user),
        }
        for index, user in enumerate(users, start=1)
    ]

    rankings = sorted(
        rankings,
        key=lambda item: item['knowledge_score'],
        reverse=True
    )[:10]

    for index, item in enumerate(rankings, start=1):
        item['rank'] = index

    return render(
        request,
        'accounts/leaderboard.html',
        {'rankings': rankings}
    )


@login_required(login_url='login')
def profile(request):
    return render(
        request,
        'accounts/profile.html'
    )


@login_required(login_url='login')
@require_POST
def logout_view(request):
    logout(request)
    return redirect('home')

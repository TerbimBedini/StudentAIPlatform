from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .forms import RegisterForm
from documents.models import Activity, Document, FlashcardAttempt, QuizAttempt


def home(request):
    return render(request, 'accounts/home.html')


def login_view(request):
    error_message = None

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
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


def register_view(request):

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
    documents = Document.objects.filter(
        uploaded_by=request.user
    ).order_by('-uploaded_at')
    activities = Activity.objects.filter(
        user=request.user
    ).order_by('-created_at')


    context = {
        'documents': documents,
        'documents_count': documents.count(),
        'quiz_attempts_count': QuizAttempt.objects.filter(user=request.user).count(),
        'flashcard_attempts_count': FlashcardAttempt.objects.filter(user=request.user).count(),
        'activities': activities[:10],
        'summary_count': activities.filter(activity_type='summary').count(),
        'chat_count': activities.filter(activity_type='chat').count(),
        'quiz_count': activities.filter(activity_type='quiz').count(),
        'flashcards_count': activities.filter(activity_type='flashcards').count(),
        'total_points': sum(activity.points for activity in activities),
    }

    return render(
        request,
        'accounts/dashboard.html',
        context
    )

def logout_view(request):
    logout(request)
    return redirect('home')

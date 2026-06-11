from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from .forms import RegisterForm
from documents.models import Document


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



def dashboard(request):

    documents_count = Document.objects.filter(
        uploaded_by=request.user
    ).count()

    context = {
        'documents_count': documents_count
    }

    return render(
        request,
        'accounts/dashboard.html',
        context
    )

def logout_view(request):
    logout(request)
    return redirect('home')

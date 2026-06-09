from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.shortcuts import render



def home(request):
    return render(request, 'accounts/home.html')


class AccountLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = AuthenticationForm
    redirect_authenticated_user = True


login_view = AccountLoginView.as_view()


def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()

    return render(request, 'accounts/register.html', {'form': form})

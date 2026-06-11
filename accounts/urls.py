from django.urls import path
from .views import (
    home,
    login_view,
    register_view,
    dashboard,
    logout_view
)

urlpatterns = [
    path('', home, name='home'),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('dashboard/', dashboard, name='dashboard'),
    path('logout/', logout_view, name='logout'),
]

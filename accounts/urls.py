from django.urls import path
from .views import (
    home,
    login_view,
    register_view,
    dashboard,
    exam_preparation,
    leaderboard,
    profile,
    study_plan,
    logout_view
)

urlpatterns = [
    path('', home, name='home'),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('dashboard/', dashboard, name='dashboard'),
    path('exam-preparation/', exam_preparation, name='exam_preparation'),
    path('study-plan/', study_plan, name='study_plan'),
    path('leaderboard/', leaderboard, name='leaderboard'),
    path('profile/', profile, name='profile'),
    path('logout/', logout_view, name='logout'),
]

from django.urls import path

from .views import (
    document_chat,
    document_chat_ask,
    document_detail,
    document_flashcards,
    document_file,
    document_quiz,
    flashcard_history,
    multi_document_study,
    quiz_history,
    upload_document,
)

urlpatterns = [
    path('upload/', upload_document, name='upload_document'),
    path('multi-study/', multi_document_study, name='multi_document_study'),
    path('quiz-history/', quiz_history, name='quiz_history'),
    path('flashcard-history/', flashcard_history, name='flashcard_history'),
    path('chat/<int:document_id>/', document_chat, name='document_chat'),
    path('chat/<int:document_id>/ask/', document_chat_ask, name='document_chat_ask'),
    path('quiz/<int:document_id>/', document_quiz, name='document_quiz'),
    path('flashcards/<int:document_id>/', document_flashcards, name='document_flashcards'),
    path('<int:document_id>/', document_detail, name='document_detail'),
    path('<int:document_id>/file/', document_file, name='document_file'),
]

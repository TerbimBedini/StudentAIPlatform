from django.urls import path

from .views import document_chat, document_detail, document_file, upload_document

urlpatterns = [
    path('upload/', upload_document, name='upload_document'),
    path('chat/<int:document_id>/', document_chat, name='document_chat'),
    path('<int:document_id>/', document_detail, name='document_detail'),
    path('<int:document_id>/file/', document_file, name='document_file'),
]

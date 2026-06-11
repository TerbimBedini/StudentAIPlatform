from django.urls import path
from .views import upload_document

urlpatterns = [
    path('upload/', upload_document, name='upload_document'),
]
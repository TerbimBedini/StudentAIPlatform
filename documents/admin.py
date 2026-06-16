from django.contrib import admin
from .models import Document, QuizAttempt


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('title', 'uploaded_by__username', 'uploaded_by__email')


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'score', 'total', 'category', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('document__title', 'user__username', 'user__email')

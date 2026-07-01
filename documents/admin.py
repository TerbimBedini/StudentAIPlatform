from django.contrib import admin
from django.utils import timezone
from .models import (
    Achievement,
    CommunityMessage,
    Document,
    LibraryDocument,
    Notification,
    QuizAttempt,
    StudySession,
)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'uploaded_by',
        'summary_status',
        'quiz_status',
        'flashcards_status',
        'uploaded_at',
    )
    list_filter = (
        'summary_status',
        'quiz_status',
        'flashcards_status',
        'uploaded_at',
    )
    search_fields = ('title', 'uploaded_by__username')


@admin.register(LibraryDocument)
class LibraryDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'field',
        'document_type',
        'course_name',
        'moderation_status',
        'is_public',
        'uploaded_by',
        'uploaded_at',
    )
    list_filter = (
        'field',
        'document_type',
        'moderation_status',
        'is_public',
        'uploaded_at',
    )
    search_fields = (
        'title',
        'course_name',
        'description',
        'uploaded_by__username',
    )
    actions = (
        'approve_documents',
        'reject_documents',
        'flag_documents',
    )

    def approve_documents(self, request, queryset):
        queryset.update(
            moderation_status=LibraryDocument.STATUS_APPROVED,
            is_public=True,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    approve_documents.short_description = 'Approve selected library documents'

    def reject_documents(self, request, queryset):
        queryset.update(
            moderation_status=LibraryDocument.STATUS_REJECTED,
            is_public=False,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    reject_documents.short_description = 'Reject selected library documents'

    def flag_documents(self, request, queryset):
        queryset.update(
            moderation_status=LibraryDocument.STATUS_FLAGGED,
            is_public=False,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    flag_documents.short_description = 'Flag selected library documents'


@admin.register(CommunityMessage)
class CommunityMessageAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'user',
        'field',
        'kind',
        'is_hidden',
        'created_at',
    )
    list_filter = (
        'field',
        'kind',
        'is_hidden',
        'created_at',
    )
    search_fields = (
        'title',
        'message',
        'user__username',
    )


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'document',
        'score',
        'total_questions',
        'percentage',
        'created_at',
    )

    list_filter = (
        'created_at',
    )

    search_fields = (
        'user__username',
        'document__title',
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'title',
        'notification_type',
        'is_read',
        'created_at',
    )
    list_filter = (
        'notification_type',
        'is_read',
        'created_at',
    )
    search_fields = (
        'user__username',
        'title',
        'message',
    )


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'document',
        'status',
        'quiz_score',
        'total_questions',
        'session_score',
        'started_at',
        'completed_at',
    )
    list_filter = (
        'status',
        'started_at',
        'completed_at',
    )
    search_fields = (
        'user__username',
        'document__title',
    )


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'title',
        'badge_type',
        'created_at',
    )
    list_filter = (
        'badge_type',
        'created_at',
    )
    search_fields = (
        'user__username',
        'title',
        'description',
    )

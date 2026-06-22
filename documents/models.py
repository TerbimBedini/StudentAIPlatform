from django.db import models
from django.contrib.auth.models import User

class Document(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    PROCESSING_STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    )

    title = models.CharField(max_length=255)

    file = models.FileField(
        upload_to='documents/'
    )

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    summary = models.TextField(blank=True, null=True)

    summary_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS_CHOICES,
        default=STATUS_PENDING
    )

    quiz_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS_CHOICES,
        default=STATUS_PENDING
    )

    flashcards_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS_CHOICES,
        default=STATUS_PENDING
    )

    processing_error = models.TextField(
        blank=True,
        null=True
    )

    extracted_text = models.TextField(blank=True, null=True)

    ai_processed = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class LibraryDocument(models.Model):
    FIELD_MEDICINE = 'medicine'
    FIELD_ENGINEERING = 'engineering'
    FIELD_ECONOMICS = 'economics'
    FIELD_COMPUTER_SCIENCE = 'computer_science'
    FIELD_LAW = 'law'
    FIELD_BUSINESS = 'business'
    FIELD_SCIENCE = 'science'
    FIELD_OTHER = 'other'

    FIELD_CHOICES = (
        (FIELD_MEDICINE, 'Medicine'),
        (FIELD_ENGINEERING, 'Engineering'),
        (FIELD_ECONOMICS, 'Economics'),
        (FIELD_COMPUTER_SCIENCE, 'Computer Science'),
        (FIELD_LAW, 'Law'),
        (FIELD_BUSINESS, 'Business'),
        (FIELD_SCIENCE, 'Science'),
        (FIELD_OTHER, 'Other'),
    )

    TYPE_LECTURE = 'lecture'
    TYPE_EXAM = 'exam'
    TYPE_NOTES = 'notes'
    TYPE_BOOK = 'book'
    TYPE_OTHER = 'other'

    DOCUMENT_TYPE_CHOICES = (
        (TYPE_LECTURE, 'Lecture'),
        (TYPE_EXAM, 'Old Exam'),
        (TYPE_NOTES, 'Notes'),
        (TYPE_BOOK, 'Book / Chapter'),
        (TYPE_OTHER, 'Other'),
    )

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_FLAGGED = 'flagged'

    MODERATION_STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_FLAGGED, 'Flagged'),
    )

    title = models.CharField(max_length=255)

    field = models.CharField(
        max_length=40,
        choices=FIELD_CHOICES
    )

    document_type = models.CharField(
        max_length=30,
        choices=DOCUMENT_TYPE_CHOICES
    )

    course_name = models.CharField(max_length=160)

    academic_year = models.CharField(
        max_length=20,
        blank=True
    )

    description = models.TextField(blank=True)

    file = models.FileField(
        upload_to='library/'
    )

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='library_uploads'
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default=STATUS_PENDING
    )

    moderation_notes = models.TextField(blank=True)

    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='reviewed_library_documents'
    )

    reviewed_at = models.DateTimeField(
        blank=True,
        null=True
    )

    safety_scan_notes = models.TextField(blank=True)

    is_public = models.BooleanField(default=False)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title


class CommunityMessage(models.Model):
    KIND_REQUEST = 'request'
    KIND_OFFER = 'offer'
    KIND_DISCUSSION = 'discussion'

    KIND_CHOICES = (
        (KIND_REQUEST, 'Request lectures'),
        (KIND_OFFER, 'Offer material'),
        (KIND_DISCUSSION, 'Discussion'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='community_messages'
    )

    field = models.CharField(
        max_length=40,
        choices=LibraryDocument.FIELD_CHOICES
    )

    kind = models.CharField(
        max_length=20,
        choices=KIND_CHOICES
    )

    title = models.CharField(max_length=180)

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.title}'


class Activity(models.Model):
    ACTIVITY_TYPES = (
        ('summary', 'Summary'),
        ('chat', 'Chat'),
        ('quiz', 'Quiz'),
        ('flashcards', 'Flashcards'),
    )

    POINTS = {
        'summary': 5,
        'chat': 2,
        'quiz': 10,
        'flashcards': 5,
    }

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='activities'
    )

    activity_type = models.CharField(
        max_length=20,
        choices=ACTIVITY_TYPES
    )

    document_title = models.CharField(max_length=255)

    points = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def icon(self):
        return {
            'summary': 'Summary',
            'chat': 'Chat',
            'quiz': 'Quiz',
            'flashcards': 'Flashcards',
        }.get(self.activity_type, 'Activity')

    def save(self, *args, **kwargs):
        if not self.points:
            self.points = self.POINTS.get(self.activity_type, 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user} - {self.activity_type}'


class QuizAttempt(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='quiz_attempts'
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='quiz_attempts'
    )

    score = models.PositiveIntegerField(default=0)

    total = models.PositiveIntegerField(default=0)

    category = models.CharField(max_length=50, blank=True)

    mistakes = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_questions(self):
        return self.total

    @property
    def percentage(self):
        if not self.total:
            return 0
        return round((self.score / self.total) * 100, 2)

    def __str__(self):
        return f'{self.user} - {self.document.title} - {self.score}/{self.total}'


class StudySession(models.Model):
    STATUS_STARTED = 'started'
    STATUS_COMPLETED = 'completed'

    STATUS_CHOICES = (
        (STATUS_STARTED, 'Started'),
        (STATUS_COMPLETED, 'Completed'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='study_sessions'
    )

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='study_sessions'
    )

    started_at = models.DateTimeField(auto_now_add=True)

    completed_at = models.DateTimeField(
        blank=True,
        null=True
    )

    quiz_score = models.IntegerField(default=0)

    total_questions = models.IntegerField(default=0)

    session_score = models.IntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_STARTED
    )

    def __str__(self):
        return f'{self.user} - {self.document.title} - {self.status}'


class Achievement(models.Model):
    BADGE_FIRST_UPLOAD = 'first_upload'
    BADGE_FIRST_QUIZ = 'first_quiz'
    BADGE_QUIZ_MASTER = 'quiz_master'
    BADGE_STUDY_STREAK = 'study_streak'
    BADGE_KNOWLEDGE_100 = 'knowledge_100'
    BADGE_KNOWLEDGE_500 = 'knowledge_500'
    BADGE_KNOWLEDGE_1000 = 'knowledge_1000'

    BADGE_TYPE_CHOICES = (
        (BADGE_FIRST_UPLOAD, 'First Upload'),
        (BADGE_FIRST_QUIZ, 'First Quiz'),
        (BADGE_QUIZ_MASTER, 'Quiz Master'),
        (BADGE_STUDY_STREAK, 'Study Streak'),
        (BADGE_KNOWLEDGE_100, 'Knowledge 100'),
        (BADGE_KNOWLEDGE_500, 'Knowledge 500'),
        (BADGE_KNOWLEDGE_1000, 'Knowledge 1000'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='achievements'
    )

    title = models.CharField(max_length=120)

    description = models.TextField()

    badge_type = models.CharField(
        max_length=30,
        choices=BADGE_TYPE_CHOICES
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'badge_type'],
                name='unique_user_achievement_badge'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.title}'


class FlashcardAttempt(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='flashcard_attempts'
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='flashcard_attempts'
    )

    average_score = models.FloatField()

    category = models.CharField(max_length=100)

    cards = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.document.title} - {self.average_score}%'


from django.db import models
from django.contrib.auth.models import User

class Document(models.Model):
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

    extracted_text = models.TextField(blank=True, null=True)

    ai_processed = models.BooleanField(default=False)

    def __str__(self):
        return self.title


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

    score = models.PositiveIntegerField()

    total = models.PositiveIntegerField()

    category = models.CharField(max_length=50)

    mistakes = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def percentage(self):
        if not self.total:
            return 0
        return round((self.score / self.total) * 100)

    def __str__(self):
        return f'{self.document.title} - {self.score}/{self.total}'


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

    average_score = models.PositiveIntegerField()

    category = models.CharField(max_length=100)

    cards = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.document.title} - {self.average_score}%'


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

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

    ai_processed = models.BooleanField(default=False)

    def __str__(self):
        return self.title

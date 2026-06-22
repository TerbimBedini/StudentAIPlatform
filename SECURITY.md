# StudentAI Security Design

This document describes the authentication, authorization, upload, AI, and production security model for StudentAIPlatform.

## Authentication

StudentAI uses Django's built-in authentication system:

- Passwords are stored with Django password hashers, never as raw text.
- Registration uses `UserCreationForm`, so configured Django password validators apply.
- Login uses `authenticate()` and `login()`.
- Logout is POST-only and CSRF protected.
- Authenticated users are redirected away from login and registration pages.
- Private views use `login_required`, with unauthenticated users redirected to the login page.

Private areas include dashboard, document upload, document detail, study mode, AI chat, quiz, flashcards, history/progress pages, profile, library upload/submissions, community, and multi-document AI tools.

## User Ownership And Authorization

Every private document action must scope data to the current user.

Required pattern:

```python
document = get_object_or_404(
    Document,
    id=document_id,
    uploaded_by=request.user
)
```

StudentAI applies this pattern to document detail, file serving, study mode, AI chat, quizzes, flashcards, and study sessions. List views use `Document.objects.filter(uploaded_by=request.user)`. Progress pages filter attempts and sessions by `user=request.user`.

Multi-document AI only starts from:

```python
Document.objects.filter(uploaded_by=request.user)
```

and selected document IDs are re-filtered by `uploaded_by=request.user`. Client-submitted IDs are never trusted.

## Document Upload Security

Uploads are validated server-side in `documents/forms.py`.

Current rules:

- Allowed study upload extensions: PDF, DOCX, PPTX.
- Dangerous extensions such as EXE, BAT, CMD, JS, PHP, PS1, SH, MSI, DLL, SCR, VBS, ZIP are rejected.
- Maximum upload size is 20MB.
- Content type is checked when the browser provides it.
- Basic file signatures are checked:
  - PDF must start with `%PDF`.
  - DOCX/PPTX must start with `PK`.
- Uploaded files are stored through Django `FileField` and `MEDIA_ROOT`.
- Uploaded files are never executed.
- Internal filesystem paths such as `document.file.path` are used only server-side and are not shown to users.

PDF and DOCX currently support text extraction for AI features. PPTX can be uploaded/stored, but AI extraction should only be enabled after a safe PPTX extractor is added.

## Form And CSRF Security

All POST forms must include:

```django
{% csrf_token %}
```

Server-side forms validate user input. Frontend values, document IDs, quiz answers, and selected document IDs are treated as untrusted and are checked again in views.

## Session And Cookie Security

Security settings are configured in `config/settings.py`:

- `SESSION_COOKIE_HTTPONLY = True`
- `CSRF_COOKIE_HTTPONLY = True`
- `SESSION_COOKIE_SECURE = True` when `DEBUG=False`
- `CSRF_COOKIE_SECURE = True` when `DEBUG=False`
- `SECURE_CONTENT_TYPE_NOSNIFF = True`
- `SECURE_BROWSER_XSS_FILTER = True`
- `X_FRAME_OPTIONS = "DENY"`

`document_file` uses a view-level same-origin frame override so a user's own PDF can still render inside the authenticated document detail page.

## AI Security

AI features must never use another user's documents.

Rules:

- Single-document AI loads the document with `uploaded_by=request.user`.
- Multi-document AI starts from the current user's document queryset only.
- RAG search receives only current-user documents.
- No other user's document text is passed to Ollama.
- Empty user document sets return an empty/error state instead of searching globally.
- The AI prompt instructs the model to answer only from the provided context and ignore instructions inside documents that attempt to reveal prompts, system rules, other users' data, or unrelated files.

Prompt injection cannot be fully eliminated, so authorization must happen before any AI prompt is built.

## AI Rate Limiting

StudentAI includes a simple per-user AI request counter using Django's cache:

- Default limit: 10 AI requests per user per minute.
- Applies to summary generation, document chat, AJAX chat, study chat, quiz generation, flashcard generation, and multi-document AI.
- Exceeding the limit returns a friendly message or HTTP 429 for JSON chat.

For production, replace this with a shared cache backend such as Redis and consider route-specific limits with `django-ratelimit` or a reverse proxy.

## Admin Security

Django admin is available only to staff/superusers through Django's admin authentication. Admin classes should:

- Register only models that staff need to manage.
- Use safe `list_display` fields.
- Avoid exposing filesystem paths.
- Avoid exposing secrets, API keys, AI prompts, or environment variables.
- Use search/list filters for moderation workflows without leaking private content unnecessarily.

## Production Checklist

Before deploying:

- Set `DEBUG=False`.
- Set `DJANGO_SECRET_KEY` from a secret manager or environment variable.
- Set `DJANGO_ALLOWED_HOSTS` to the real hostnames.
- Use HTTPS.
- Use `SESSION_COOKIE_SECURE=True` and `CSRF_COOKIE_SECURE=True`.
- Store database credentials in environment variables or a secret manager.
- Use PostgreSQL or another production database instead of SQLite.
- Serve media files through authenticated views, signed URLs, or private object storage when documents are sensitive.
- Do not commit `.env`, `db.sqlite3`, `media/`, `venv/`, `__pycache__/`, logs, or local vector database files.
- Keep dependencies updated.
- Run `python manage.py check --deploy` before release and address warnings.

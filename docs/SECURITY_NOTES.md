# StudentAI v1.0 Security Notes

StudentAI v1.0 is prepared for a stable local demo. These notes describe the current safety posture and the recommended path for production hardening.

## Authentication

StudentAI uses Django authentication for registration, login, logout, and authenticated pages. Views that require a student account use Django's login protection so unauthenticated users are redirected before accessing private learning workflows.

Recommended production actions:

- Use a strong `SECRET_KEY`.
- Set `DEBUG=False`.
- Use HTTPS.
- Use secure session and CSRF cookies.
- Review password policy for the deployment environment.

## Permissions

Core private workflows filter data by `request.user`. A user should only see their own:

- Uploaded documents
- Quiz attempts
- Flashcard attempts
- Study sessions
- Achievements
- Notifications

Staff-only moderation pages should remain protected by Django staff checks.

## User Document Isolation

Document views and AI actions should always fetch documents with both:

```text
id=document_id
uploaded_by=request.user
```

This prevents one authenticated user from opening another user's document by changing the URL.

Multi-document study flows should also filter selected document IDs by the current user.

## Upload Validation

StudentAI validates uploaded files through Django forms. The current project supports learning document formats such as PDF, DOCX, and PPTX depending on the workflow.

Recommended production actions:

- Enforce file size limits.
- Store media outside the code repository.
- Scan uploads if deployed beyond local/demo usage.
- Keep MIME/type validation and extension validation aligned.
- Avoid serving untrusted uploads inline when not necessary.

## Environment Variables

Sensitive and environment-specific values should be configured through environment variables:

```env
SECRET_KEY=change-me
DEBUG=False
ALLOWED_HOSTS=example.com
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_MODEL=gemma3:4b
OLLAMA_KEEP_ALIVE=30m
```

Do not commit:

- `.env`
- local secrets
- local databases
- uploaded media
- ChromaDB runtime data
- virtual environments

## SQLite Local Usage

SQLite is appropriate for the v1.0 local demo because it is simple and portable. It is not the recommended database for multi-user production deployments.

For production, use PostgreSQL.

Recommended PostgreSQL benefits:

- Better concurrent write behavior
- Stronger operational tooling
- Managed backups
- Better scalability
- More predictable deployment behavior

## Ollama Local AI Privacy Notes

StudentAI is designed around local Ollama inference. In the local demo setup, document context is sent to the local Ollama server, not to an external hosted AI API.

Privacy implications:

- Uploaded document snippets remain on the local machine during AI generation.
- Ollama model files and runtime stay local.
- RAG chunks are stored in local ChromaDB data.

Recommended operational notes:

- Do not expose Ollama publicly without authentication/network controls.
- Keep Ollama bound to trusted local interfaces.
- Treat uploaded documents and ChromaDB data as private local data.
- Clear `media/` and `chroma_db/` before sharing a demo machine or repository snapshot.

## Local Demo Security Checklist

- `.env` is ignored by Git.
- `db.sqlite3` is ignored by Git.
- `media/` is ignored by Git.
- `chroma_db/` is ignored by Git.
- `venv/` is ignored by Git.
- Demo data is safe to show before presentation.
- Ollama is running locally before AI workflows are demonstrated.

## Production Hardening Roadmap

- Move to PostgreSQL.
- Add background job processing with Celery and Redis.
- Add rate limiting at the application or reverse proxy layer.
- Add upload size limits and file scanning.
- Add structured logging and monitoring.
- Add backups for database and media storage.
- Add HTTPS and production security headers.
- Review staff moderation permissions.

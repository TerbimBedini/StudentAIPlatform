# StudentAI

StudentAI is a Django-based AI study coach for local learning workflows. It helps students upload study material, chat with their documents, generate quizzes and flashcards, simulate exams, track progress, and review recommendations powered by local Ollama models and RAG search.

## Features

- User authentication and dashboard
- PDF/DOCX/PPTX document uploads
- Cached document text extraction
- AI summaries, document chat, and multi-document chat
- ChromaDB-backed RAG for grounded answers
- Quiz generator, flashcards, and exam simulator
- Study sessions, study plans, and progress analytics
- Knowledge Score, learning diagnosis, weak topic recovery, and exam preparation
- Achievements, notifications, community chat, and shared AI library
- Django test coverage for core learning flows

## Tech Stack

- Python 3.14
- Django 6
- SQLite for local development
- Ollama for local LLM inference
- ChromaDB for vector storage
- Sentence Transformers for embeddings
- PyMuPDF for PDF text extraction
- Bootstrap-style Django templates

## Setup

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create local environment settings:

```powershell
copy .env.example .env
```

The current settings read Django values from environment variables. If you use `.env`, load it through your shell or development tooling before running Django.

## Ollama Setup

Install and start Ollama, then pull the local model used by StudentAI:

```powershell
ollama serve
ollama pull gemma3:4b
```

Default AI settings:

```env
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_MODEL=gemma3:4b
OLLAMA_KEEP_ALIVE=30m
```

## Environment Variables

```env
SECRET_KEY=change-me-for-local-development
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_MODEL=gemma3:4b
OLLAMA_KEEP_ALIVE=30m
```

## Database

Run migrations:

```powershell
python manage.py migrate
```

Create an admin user:

```powershell
python manage.py createsuperuser
```

Create polished local demo data without Ollama:

```powershell
python manage.py create_demo_data
```

Demo login:

```text
username: demo
password: demo12345
```

## Run Locally

```powershell
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

## Deployment Notes

StudentAI v1.0 is prepared for local demo use first. Before deploying beyond a local machine:

- Set `DEBUG=False`.
- Set a long, random `SECRET_KEY`.
- Configure `ALLOWED_HOSTS` for the real domain.
- Enable HTTPS at the proxy/platform level.
- Set `DJANGO_SECURE_SSL_REDIRECT=True` when HTTPS is ready.
- Set `DJANGO_SESSION_COOKIE_SECURE=True` and `DJANGO_CSRF_COOKIE_SECURE=True`.
- Set a non-zero `DJANGO_SECURE_HSTS_SECONDS` only after HTTPS is confirmed.
- Run `python manage.py collectstatic`.
- Use PostgreSQL instead of SQLite for production traffic.
- Keep Ollama private on a trusted network and do not expose it publicly.

## Tests

Run Django checks and tests:

```powershell
python manage.py check
python manage.py test
```

## Documentation

- [Demo Guide](DEMO_GUIDE.md)
- [Architecture Notes](docs/ARCHITECTURE.md)
- [Mermaid Diagrams](docs/DIAGRAMS.md)
- [Security Notes](docs/SECURITY_NOTES.md)

## Screenshots

Add final demo screenshots here before publishing:

- Dashboard
- Document Study Mode
- AI Chat
- Quiz Generator
- Flashcards
- Exam Simulator
- AI Library
- Community

## Local Data and Security

The following are local runtime files and should not be committed:

- `.env`
- `db.sqlite3`
- `media/`
- `chroma_db/`
- `venv/`
- log files

Use strong secrets and `DEBUG=False` before any non-local deployment.

## Future Improvements

- Celery/Redis background AI jobs
- Streaming AI responses
- PostgreSQL for production deployments
- Better moderation workflow for shared library content
- Exportable study reports
- More detailed analytics charts

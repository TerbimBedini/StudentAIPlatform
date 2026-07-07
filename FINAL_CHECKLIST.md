# StudentAI v1.0 Final Demo Checklist

Use this checklist on presentation day before opening StudentAI live.

## 1. Pre-Demo Setup

### Activate virtual environment

```powershell
cd C:\Users\User\Desktop\StudentAIPlatform
.\venv\Scripts\activate
```

### Check Python version

```powershell
python --version
```

Expected:

```text
Python 3.14.x
```

### Install requirements

```powershell
pip install -r requirements.txt
```

### Run migrations

```powershell
python manage.py migrate
```

### Create demo data

```powershell
python manage.py create_demo_data
```

Demo login:

```text
username: demo
password: demo12345
```

### Start Ollama

Open a separate terminal:

```powershell
ollama serve
```

### Verify model

```powershell
ollama list
```

Confirm this model exists:

```text
gemma3:4b
```

If missing:

```powershell
ollama pull gemma3:4b
```

### Start Django server

In the project terminal:

```powershell
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

## 2. Health Checks

Run Django check:

```powershell
python manage.py check
```

Run tests:

```powershell
python manage.py test
```

Manual checks:

- Open dashboard.
- Upload a small test PDF or DOCX.
- Open Study Mode.
- Ask AI Tutor one simple document-based question.
- Generate Smart Quiz.
- Generate Flashcards 2.0.
- Generate Exam Simulator 2.0.
- Confirm Analytics section loads.
- Confirm Achievements section loads.
- Open Community.
- Open AI Library.

## 3. Demo Flow Order

Recommended presentation order:

1. Login
2. Dashboard
3. Upload document
4. Study Mode
5. AI Tutor
6. Smart Quiz
7. Flashcards 2.0
8. Exam Simulator 2.0
9. Analytics
10. Achievements
11. Community
12. AI Library
13. Database diagram

## 4. Backup Plan

If Ollama is slow:

- Show cached AI Summary.
- Show fallback quiz behavior.
- Show saved screenshots.
- Explain that StudentAI uses local AI through Ollama.
- Explain that first model response can be slow because the model is loading.
- Continue demo using dashboard analytics, saved attempts, achievements, community, and library.

Suggested explanation:

> StudentAI uses local AI instead of a cloud API. That improves privacy because document context stays on the machine, but the first response can be slower while the model loads.

## 5. Common Errors and Fixes

### Ollama not running

Symptom:

```text
AI nuk u lidh dot me Ollama
```

Fix:

```powershell
ollama serve
```

### Model missing

Symptom:

```text
model not found
```

Fix:

```powershell
ollama pull gemma3:4b
ollama list
```

### Port 8000 already used

Symptom:

```text
Error: That port is already in use.
```

Fix:

```powershell
python manage.py runserver 8001
```

Open:

```text
http://127.0.0.1:8001/
```

### Database modified

Symptom:

```text
git status shows db.sqlite3
```

Fix:

```powershell
git restore db.sqlite3
git status
```

Note:

`db.sqlite3` should not be committed.

### Migrations pending

Symptom:

```text
You have unapplied migration(s)
```

Fix:

```powershell
python manage.py migrate
python manage.py check
```

### Git branch confusion

Check current branch:

```powershell
git branch
```

Check latest commits:

```powershell
git log --oneline -5
```

Check uncommitted files:

```powershell
git status
```

## 6. Final Git Commands

Before presentation:

```powershell
git status
git log --oneline -5
git branch
```

Push latest work:

```powershell
git push
```

If pushing a specific branch:

```powershell
git push origin integrate-lovable-ui
```

Optional release tag:

```powershell
git tag v1.0
git push origin v1.0
```

## 7. Presentation Talking Points

### Problem

Students often upload or receive long study materials but do not know what to review, how to practice, or how ready they are for exams.

### Solution

StudentAI turns uploaded documents into an interactive AI study coach with summaries, tutor chat, quizzes, flashcards, exam simulation, analytics, recommendations, achievements, and community learning.

### Architecture

StudentAI uses Django for the backend, SQLite for local demo storage, ChromaDB for RAG/vector search, and Ollama for local AI generation.

### Database

The database stores users, documents, extracted text, quiz attempts, flashcard attempts, study sessions, achievements, notifications, community messages, and library documents.

### AI/RAG

StudentAI extracts and caches document text, splits it into chunks, uses ChromaDB for retrieval, and sends only relevant document context to Ollama.

### Testing

The project includes Django tests for authentication, upload, quiz, flashcards, exam simulator, analytics, achievements, community, and library flows.

### Future Improvements

- Celery and Redis for background AI generation
- Streaming AI responses
- PostgreSQL for production
- Better chart visualizations
- Teacher/admin dashboard
- More moderation tools
- Exportable student progress reports

## Final Reminder

Before starting the live demo:

- Ollama is running.
- Django server is running.
- Browser is already open.
- Demo user is ready.
- Test document is ready.
- Screenshots are available as backup.
- DB Browser is ready if showing database tables.

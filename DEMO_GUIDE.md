# StudentAI v1.0 Demo Guide

This guide is a presentation script for demonstrating StudentAI as a local AI study coach.

## 1. Project Overview

StudentAI is an AI-powered study platform built for students who want to learn from their own documents. A user can upload study material, generate summaries, ask questions, create quizzes and flashcards, simulate exams, track progress, and receive learning recommendations.

The main idea is simple:

```text
Upload document -> Extract text -> Use RAG/context -> Generate study tools -> Track learning progress
```

StudentAI v1.0 is designed as a stable local demo using Django, SQLite, ChromaDB, and Ollama.

## 2. Tech Stack

- Backend: Django
- Database: SQLite
- AI model runtime: Ollama
- Local model: Gemma via Ollama
- RAG/vector database: ChromaDB
- Embeddings: Sentence Transformers
- PDF extraction: PyMuPDF
- Frontend: Django templates with Bootstrap-style UI
- Testing: Django test suite

## 3. Database Overview

Important database tables to mention:

- `auth_user`: registered users
- `documents_document`: uploaded documents and extracted text
- `documents_quizattempt`: quiz history and scores
- `documents_flashcardattempt`: flashcard activity and performance
- `documents_studysession`: completed study sessions
- `documents_achievement`: awarded achievements
- `documents_notification`: dashboard notifications
- `documents_communitymessage`: community chat messages
- `documents_librarydocument`: shared AI library documents

Main relationship:

```text
User -> Documents
User -> Quiz Attempts
User -> Flashcard Attempts
User -> Study Sessions
User -> Achievements
User -> Notifications
```

## 4. Step-by-Step Demo Flow

### 1. Login

Open the local app:

```text
http://127.0.0.1:8000/
```

Log in with a demo user.

What to say:

> StudentAI starts with a normal authenticated dashboard. Every learning metric and recommendation is tied to the logged-in student.

### 2. Dashboard

Show the dashboard first.

Point out:

- AI Mentor
- Today's goals
- Notifications
- Knowledge Score
- Learning diagnosis
- Recovery plan
- Exam preparation
- Advanced analytics
- Achievements
- Community and library previews

What to say:

> The dashboard acts as the student's AI study coach. It does not only show uploaded files, it summarizes learning progress and recommends what to do next.

### 3. Upload Document

Upload a PDF or DOCX study document.

Point out:

- The document is stored in the database
- Extracted text is cached
- The platform avoids re-reading the PDF repeatedly
- The document becomes available for AI Summary, Chat, Quiz, Flashcards, and Exam Simulator

What to say:

> After upload, StudentAI extracts the document text once and reuses the cached text for future AI workflows. This improves speed and keeps the AI grounded in the uploaded material.

### 4. AI Summary

Open the uploaded document and show the summary.

What to say:

> The AI Summary gives the student a fast overview of the material before practicing. If a summary already exists, the platform can reuse it instead of regenerating it every time.

### 5. AI Tutor

Ask a question about the document.

Example questions:

- "Explain the main idea of this document."
- "What should I focus on for an exam?"
- "Can you explain this topic more simply?"

What to say:

> The AI Tutor uses document context instead of answering freely. If the answer is not in the document, the system is designed to say that the document does not contain enough information.

### 6. Smart Quiz

Generate a quiz from the uploaded document.

Point out:

- Questions are generated from sampled document chunks
- Quiz generation avoids sending the full document
- The final quiz always gives the user usable questions
- Quiz attempts are saved for analytics

What to say:

> StudentAI uses quiz attempts as real learning data. Scores are later used for Knowledge Score, weak topics, strong topics, exam readiness, and recommendations.

### 7. Flashcards 2.0

Open Flashcards.

Show the mode selector:

- Adaptive
- Definitions
- Concepts
- True/False
- Fill in blank
- Memory

What to say:

> Flashcards 2.0 supports different study styles. Adaptive mode uses the student's progress data to focus practice where it is most useful.

### 8. Exam Simulator 2.0

Open Exam Simulator.

Show the mode selector:

- Adaptive
- Easy
- Medium
- Hard
- Mixed
- Weak Topics Focus

Submit the exam and show the review.

Point out:

- Score
- Answer key
- Wrong answer review
- Explanations or correct answers

What to say:

> The Exam Simulator is a mock exam experience. It mixes question types and gives review feedback so the student can see what went wrong and where to improve.

### 9. Learning Coach

Return to the dashboard and show:

- Study consistency
- Today's focus
- Today's recommendation
- Weakest topic
- Most improved topic
- Recommended study duration

What to say:

> The Learning Coach turns activity data into guidance. It helps the student decide what to study next instead of only showing raw scores.

### 10. Analytics

Show the Advanced Analytics section.

Point out:

- Weekly study hours
- Quiz accuracy trend
- Flashcard success rate
- Knowledge growth
- Exam readiness
- Learning streak
- Weak and strong topics

What to say:

> These analytics are calculated from actual activity: quiz attempts, flashcard attempts, study sessions, and uploaded documents.

### 11. Achievements

Show achievements on the dashboard.

Examples:

- First Upload
- First Quiz
- Perfect Quiz
- Consistent Learner
- Knowledge Builder

What to say:

> Achievements add motivation. They are awarded from real milestones and duplicates are prevented.

### 12. Community

Open Community Chat.

Post a short message.

Point out:

- Authenticated users can post
- Empty messages are rejected
- Messages show author and timestamp
- User content is displayed safely

What to say:

> The community area adds a shared learning layer where students can communicate and support each other.

### 13. AI Library

Open AI Library.

Show:

- Approved shared documents
- Search
- Detail page
- AI actions if linked to a study document

What to say:

> The AI Library turns shared documents into reusable learning material. Approved resources can become starting points for summaries, quizzes, flashcards, and exam simulations.

## 5. Screenshots to Take

Recommended screenshots for GitHub or presentation slides:

1. Login page
2. Dashboard full view
3. Document upload page
4. AI Summary page
5. AI Tutor response
6. Smart Quiz generated questions
7. Quiz result/review
8. Flashcards 2.0 mode selector
9. Exam Simulator 2.0 mode selector
10. Exam result and wrong answer review
11. Advanced Analytics dashboard section
12. Achievements section
13. Community Chat
14. AI Library list
15. AI Library detail page

## 6. SQL Queries to Show in DB Browser

Use DB Browser for SQLite and open:

```text
db.sqlite3
```

Useful queries:

Show users:

```sql
SELECT id, username, email, date_joined
FROM auth_user;
```

Show uploaded documents:

```sql
SELECT id, title, uploaded_by_id, uploaded_at, status
FROM documents_document
ORDER BY uploaded_at DESC;
```

Show cached extracted text length:

```sql
SELECT id, title, LENGTH(extracted_text) AS extracted_text_length
FROM documents_document;
```

Show quiz attempts:

```sql
SELECT id, user_id, document_id, score, total_questions, percentage, created_at
FROM documents_quizattempt
ORDER BY created_at DESC;
```

Show flashcard attempts:

```sql
SELECT id, user_id, document_id, average_score, created_at
FROM documents_flashcardattempt
ORDER BY created_at DESC;
```

Show study sessions:

```sql
SELECT id, user_id, document_id, duration_minutes, completed, created_at
FROM documents_studysession
ORDER BY created_at DESC;
```

Show achievements:

```sql
SELECT id, user_id, name, category, created_at
FROM documents_achievement
ORDER BY created_at DESC;
```

Show notifications:

```sql
SELECT id, user_id, title, notification_type, is_read, created_at
FROM documents_notification
ORDER BY created_at DESC;
```

Show community messages:

```sql
SELECT id, user_id, message, created_at
FROM documents_communitymessage
ORDER BY created_at DESC;
```

Show library documents:

```sql
SELECT id, title, uploaded_by_id, status, created_at
FROM documents_librarydocument
ORDER BY created_at DESC;
```

## 7. What to Say During Presentation

Short version:

> StudentAI is a local AI study coach. A student uploads documents, and the platform turns them into summaries, tutor chat, quizzes, flashcards, and mock exams. The important part is that StudentAI also tracks real learning activity and converts it into Knowledge Score, Learning Diagnosis, Weak Topic Recovery, Exam Readiness, Analytics, Achievements, and personalized recommendations.

Architecture explanation:

> The backend is Django. Documents are stored in SQLite, extracted text is cached, and ChromaDB stores document chunks for retrieval. Ollama runs the local AI model. The platform tries to keep answers grounded by sending only selected document context to the model.

Performance explanation:

> Instead of sending full documents to the model, StudentAI uses cached text and selected chunks. Quiz, flashcards, and exams use small sampled context windows, while chat uses vector search for grounded answers.

Learning intelligence explanation:

> StudentAI is not just generating content. It saves student attempts and uses that activity to calculate progress, weak topics, strong topics, readiness, goals, and recommendations.

Closing line:

> The result is a complete local AI learning assistant that can be demonstrated, tested, and extended toward a production-ready study platform.

## 8. Future Improvements

- Add Celery and Redis for background AI jobs
- Add streaming AI responses
- Move from SQLite to PostgreSQL for production
- Add richer charts for analytics
- Improve moderation tools for the shared library
- Add teacher/admin dashboards
- Add course-level organization
- Add exportable study reports
- Add mobile-first UI refinements
- Add multi-language study modes

## 9. Troubleshooting Notes for Ollama

Check that Ollama is running:

```powershell
ollama serve
```

Check installed models:

```powershell
ollama list
```

Pull the expected model:

```powershell
ollama pull gemma3:4b
```

Confirm `.env` or environment variables:

```env
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_MODEL=gemma3:4b
OLLAMA_KEEP_ALIVE=30m
```

Common issues:

- If AI responses fail, confirm Ollama is running.
- If the first request is slow, the model may still be loading.
- If generation times out, use a smaller model or restart Ollama.
- If answers seem unrelated, re-upload or re-index the document.
- If ChromaDB behaves strangely during local testing, stop the server and clear only local generated `chroma_db/` data when safe.

Demo tip:

> Start Ollama before opening the presentation, and generate one AI response before the live demo so the model is already warm.

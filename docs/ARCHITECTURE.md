# StudentAI v1.0 Architecture

StudentAI is a local AI study coach built with Django, SQLite, Ollama, and ChromaDB. The platform turns uploaded learning documents into summaries, tutor conversations, quizzes, flashcards, mock exams, progress analytics, achievements, and shared learning resources.

The v1.0 architecture favors local demo stability:

- Django handles routing, authentication, templates, forms, and persistence.
- SQLite stores users, documents, attempts, sessions, notifications, achievements, community posts, and library records.
- Uploaded document text is extracted and cached on the `Document` record.
- ChromaDB stores indexed document chunks for semantic retrieval.
- Ollama runs the local language model for AI generation.
- Dashboard analytics are calculated from existing student activity.

## High-Level Architecture

```text
Browser
  -> Django views
  -> Django models / SQLite
  -> Document text cache
  -> RAG helpers / ChromaDB
  -> Ollama AI helper
  -> Templates and dashboard analytics
```

StudentAI uses two main app areas:

- `accounts`: authentication, dashboard, profile, leaderboard, study plan, exam preparation.
- `documents`: uploads, document study, summaries, tutor/chat, quizzes, flashcards, exam simulator, RAG, analytics helpers, achievements, notifications, community, and library.

## Django Apps

### accounts

The `accounts` app owns user-facing account pages and the main dashboard. It gathers learning metrics from helper modules in `documents`, then renders the dashboard as a unified study coach.

Key responsibilities:

- Login, register, logout, profile
- Dashboard context assembly
- Study plan
- Leaderboard
- Exam preparation page

### documents

The `documents` app owns the learning workflow. It stores uploaded files, extracts text, prepares AI context, tracks attempts and study sessions, and powers shared learning features.

Key responsibilities:

- Upload and document management
- Text extraction and caching
- RAG and ChromaDB indexing/search
- AI Summary
- AI Tutor and document chat
- Quiz, flashcards, and exam simulator
- Learning diagnosis, analytics, recovery, achievements
- Community chat and AI library

## Authentication Flow

1. A visitor opens the home page.
2. The user registers or logs in.
3. Django authenticates the session.
4. Authenticated pages use `login_required`.
5. User-owned records are queried with `request.user` to keep data isolated.

Important principle:

```text
Authenticated user -> request.user -> filtered documents/activity only for that user
```

## Document Upload Flow

1. User uploads a supported file.
2. Django validates the file type through forms.
3. A `Document` record is created.
4. Text extraction runs for supported formats.
5. Clean extracted text is saved to `document.extracted_text`.
6. Summary or AI preparation can use the cached text later.

The platform avoids repeated PDF parsing by using the cached extracted text when available.

## AI Summary Flow

1. User uploads or opens a document.
2. StudentAI loads cached document text.
3. A concise summary prompt is sent to Ollama.
4. The generated summary is saved on the document.
5. Future page loads show the cached summary unless regeneration is requested.

## AI Tutor Flow

1. User asks a question from Study Mode or chat.
2. The system retrieves relevant document context.
3. Single-document chat uses document chunk search.
4. Multi-document chat uses vector/search chunks from selected documents and capped fallback chunks.
5. The prompt instructs the AI to answer only from provided context.
6. The response is displayed in the tutor/chat UI.

Grounding rule:

```text
Question + selected document chunks -> Ollama -> grounded answer
```

## Smart Quiz Flow

1. User chooses quiz difficulty or adaptive mode.
2. The view samples a small set of document chunks.
3. AI generates a compact JSON quiz pack.
4. Local fallback fills missing questions if needed.
5. Question order and answer choices are shuffled.
6. User submits answers.
7. A `QuizAttempt` is saved and used by analytics.

Quiz attempts feed:

- Quiz accuracy
- Knowledge Score
- Strong topics
- Weak topics
- Exam readiness
- Leaderboard

## Flashcards 2.0 Flow

1. User chooses a flashcard mode.
2. Adaptive mode uses existing learning signals.
3. The system samples document chunks.
4. AI generates a small flashcard pack.
5. Local fallback fills missing cards if needed.
6. User answers cards.
7. A `FlashcardAttempt` is saved for progress analytics.

Supported modes:

- Adaptive
- Definitions
- Concepts
- True/False
- Fill in the blank
- Memory

## Exam Simulator 2.0 Flow

1. User chooses an exam mode.
2. Adaptive mode considers score, weak topics, flashcards, sessions, and readiness.
3. The simulator samples document chunks.
4. AI generates a 5-question mock exam.
5. Fallback guarantees a usable exam if AI output is incomplete.
6. User submits answers.
7. The result page shows score, answer key, and wrong answer review.

Supported modes:

- Adaptive
- Easy
- Medium
- Hard
- Mixed
- Weak Topics Focus

## RAG / ChromaDB Flow

1. Text is loaded from `document.extracted_text`.
2. Text is split into chunks.
3. Chunks are embedded with Sentence Transformers.
4. Embeddings and chunks are stored in ChromaDB.
5. Chat searches top relevant chunks.
6. Generated answers use only retrieved/capped context.

Performance rule:

```text
Do not send full documents to AI generation when chunks are enough.
```

## Analytics Flow

Dashboard analytics are calculated from existing activity:

- `QuizAttempt`
- `FlashcardAttempt`
- `StudySession`
- `Document`
- Knowledge Score helpers
- Learning diagnosis helpers

The dashboard shows:

- Weekly study hours
- Monthly progress
- Quiz accuracy trend
- Flashcard success rate
- Knowledge growth
- Exam readiness
- Weak topics
- Strong topics
- Learning streak

## Achievements Flow

1. User performs learning actions.
2. Achievement helper checks milestones.
3. Existing achievements are checked to prevent duplicates.
4. New achievements are saved and displayed on the dashboard.

Examples:

- First Upload
- First Quiz
- Perfect Quiz
- 10 Study Sessions
- Consistent Learner
- Knowledge Builder

## Community / AI Library Flow

### Community

1. Authenticated users post requests or offers.
2. Empty messages are rejected.
3. Messages are listed safely through Django templates.
4. Dashboard shows recent community activity.

### AI Library

1. Users submit shared learning documents.
2. Submissions can be moderated.
3. Approved resources appear in the library.
4. Library detail pages show metadata and AI actions when linked to a study document.

The AI Library is designed as a shared learning layer on top of the personal document study workflow.

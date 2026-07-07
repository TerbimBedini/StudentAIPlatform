# StudentAI v1.0 Diagrams

This file contains Mermaid diagrams for GitHub and presentation slides.

## System Architecture Diagram

```mermaid
flowchart LR
    User[Student Browser] --> Django[Django App]
    Django --> Accounts[accounts app]
    Django --> Documents[documents app]
    Accounts --> SQLite[(SQLite)]
    Documents --> SQLite
    Documents --> Media[Uploaded Files]
    Documents --> TextCache[Cached extracted_text]
    Documents --> RAG[RAG Helpers]
    RAG --> Chroma[(ChromaDB)]
    RAG --> Embeddings[Sentence Transformers]
    Documents --> AI[AI Helper]
    AI --> Ollama[Ollama Local Model]
    Documents --> Templates[Django Templates]
    Accounts --> Templates
```

## Database ER Overview

```mermaid
erDiagram
    AUTH_USER ||--o{ DOCUMENTS_DOCUMENT : uploads
    AUTH_USER ||--o{ DOCUMENTS_QUIZATTEMPT : completes
    AUTH_USER ||--o{ DOCUMENTS_FLASHCARDATTEMPT : practices
    AUTH_USER ||--o{ DOCUMENTS_STUDYSESSION : studies
    AUTH_USER ||--o{ DOCUMENTS_ACHIEVEMENT : earns
    AUTH_USER ||--o{ DOCUMENTS_NOTIFICATION : receives
    AUTH_USER ||--o{ DOCUMENTS_COMMUNITYMESSAGE : posts
    AUTH_USER ||--o{ DOCUMENTS_LIBRARYDOCUMENT : submits

    DOCUMENTS_DOCUMENT ||--o{ DOCUMENTS_QUIZATTEMPT : has
    DOCUMENTS_DOCUMENT ||--o{ DOCUMENTS_FLASHCARDATTEMPT : has
    DOCUMENTS_DOCUMENT ||--o{ DOCUMENTS_STUDYSESSION : has

    AUTH_USER {
        int id
        string username
        string email
    }

    DOCUMENTS_DOCUMENT {
        int id
        string title
        string file
        text extracted_text
        text summary
        datetime uploaded_at
    }

    DOCUMENTS_QUIZATTEMPT {
        int id
        int score
        int total
        float percentage
        datetime created_at
    }

    DOCUMENTS_FLASHCARDATTEMPT {
        int id
        float average_score
        string category
        datetime created_at
    }

    DOCUMENTS_STUDYSESSION {
        int id
        string status
        datetime started_at
        datetime completed_at
    }
```

## Upload to Extract Text to Summary to RAG Index Flow

```mermaid
flowchart TD
    Upload[User uploads document] --> Validate[Validate file]
    Validate --> SaveDoc[Create Document record]
    SaveDoc --> Extract[Extract text]
    Extract --> Clean[Clean text]
    Clean --> Cache[Save extracted_text]
    Cache --> Summary[Generate or show AI Summary]
    Cache --> Chunk[Split text into chunks]
    Chunk --> Embed[Create embeddings]
    Embed --> Store[Store chunks in ChromaDB]
```

## AI Chat / AI Tutor Flow

```mermaid
flowchart TD
    Question[User asks question] --> SelectDoc[Select document or documents]
    SelectDoc --> Search[Search relevant chunks]
    Search --> Context[Build capped document context]
    Context --> Prompt[Grounded AI prompt]
    Prompt --> Ollama[Ollama generate]
    Ollama --> Answer[Answer shown in Tutor or Chat]
    Search --> Fallback[Safe lexical or sample chunk fallback]
    Fallback --> Context
```

## Quiz / Flashcards / Exam Generation Flow

```mermaid
flowchart TD
    Start[User clicks generate] --> Mode[Read mode or difficulty]
    Mode --> Sample[Sample small document chunks]
    Sample --> Prompt[JSON-only AI prompt]
    Prompt --> Ollama[Ollama generate]
    Ollama --> Parse[Parse JSON safely]
    Parse --> Complete[Fill missing items with fallback]
    Complete --> Shuffle[Shuffle questions or choices]
    Shuffle --> Render[Render study pack]
    Render --> Submit[User submits answers]
    Submit --> Save[Save attempt]
    Save --> Analytics[Update dashboard analytics]
```

## Dashboard Analytics Flow

```mermaid
flowchart LR
    Quiz[QuizAttempt] --> Analytics[documents.analytics]
    Flashcards[FlashcardAttempt] --> Analytics
    Sessions[StudySession] --> Analytics
    Docs[Document] --> Analytics
    Analytics --> Score[Knowledge Score]
    Analytics --> Diagnosis[Strong and Weak Topics]
    Analytics --> Readiness[Exam Readiness]
    Analytics --> Dashboard[Dashboard Context]
    Dashboard --> Cards[Analytics Cards]
    Dashboard --> Charts[Chart.js Visuals]
```

## Community / Library Flow

```mermaid
flowchart TD
    User[Authenticated user] --> CommunityPost[Post community message]
    CommunityPost --> ValidateMessage[Strip and validate message]
    ValidateMessage --> CommunityList[Show latest messages]
    User --> LibraryUpload[Submit library document]
    LibraryUpload --> Pending[Pending moderation]
    Pending --> StaffReview[Staff review]
    StaffReview --> Approved[Approved library document]
    Approved --> LibraryList[Visible in AI Library]
    LibraryList --> Detail[Library detail page]
    Detail --> Actions[AI actions if linked to study document]
```

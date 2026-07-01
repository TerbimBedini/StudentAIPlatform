import random
import re

from django.conf import settings

from .utils import get_document_text


model = None
client = None


def get_rag_client():
    global client

    if client is not None:
        return client

    try:
        import chromadb
    except ImportError:
        return None

    try:
        client = chromadb.PersistentClient(
            path=str(settings.BASE_DIR / 'chroma_db')
        )
    except Exception:
        return None

    return client


def get_embedding_model():
    global model

    if model is not None:
        return model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None

    try:
        model = SentenceTransformer(
            "all-MiniLM-L6-v2",
            local_files_only=True
        )
    except Exception:
        return None

    return model


def warmup_rag_models():
    rag_client = get_rag_client()
    embedding_model = get_embedding_model()

    if embedding_model is not None:
        embedding_model.encode("studentai warmup")

    return {
        'rag_client_loaded': rag_client is not None,
        'embedding_model_loaded': embedding_model is not None,
    }


def split_text(text, chunk_size=800, overlap=150):
    chunks = []

    start = 0

    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap

    return chunks


def get_sample_document_chunks(document, chunk_count=3):
    text = get_document_text(document)
    chunks = [
        chunk.strip()
        for chunk in split_text(text)
        if chunk and chunk.strip()
    ]

    if not chunks:
        return []

    if len(chunks) <= chunk_count:
        selected_chunks = chunks[:]
    else:
        selected_chunks = random.sample(chunks, chunk_count)

    random.shuffle(selected_chunks)
    return selected_chunks[:chunk_count]


def _referenced_point_number(question):
    normalized_question = question.lower()
    word_numbers = {
        'pare': 1,
        'parë': 1,
        'dyte': 2,
        'dytë': 2,
        'trete': 3,
        'tretë': 3,
        'katert': 4,
        'katërt': 4,
        'peste': 5,
        'pestë': 5,
    }

    digit_match = re.search(
        r'\b(?:pika|piken|pik[aë]n|numri|nr\.?|point|pika\s+nr\.?)\s*(\d{1,2})\b',
        normalized_question
    )

    if digit_match:
        return int(digit_match.group(1))

    for word, number in word_numbers.items():
        if re.search(rf'\b(?:pika|piken|pik[aë]n|point)\s+(?:e\s+)?{word}\b', normalized_question):
            return number

    return None


def _extract_numbered_point_context(text, point_number, max_chars=5000):
    if not point_number:
        return ''

    escaped_number = re.escape(str(point_number))
    next_number = re.escape(str(point_number + 1))

    numbered_patterns = [
        rf'(?ms)(^|\n|\n\n)\s*{escaped_number}\s*[\).\:-]\s+(.+?)(?=(\n\s*{next_number}\s*[\).\:-]\s+)|(\n\s*\d{{1,2}}\s*[\).\:-]\s+)|\Z)',
        rf'(?mis)(^|\n|\n\n)\s*(?:pika|point)\s*{escaped_number}\s*[\).\:-]?\s+(.+?)(?=(\n\s*(?:pika|point)\s*{next_number}\b)|(\n\s*(?:pika|point)\s*\d{{1,2}}\b)|\Z)',
    ]

    for pattern in numbered_patterns:
        match = re.search(pattern, text)
        if match:
            point_text = match.group(2).strip()
            return f'Pika {point_number}:\n{point_text[:max_chars]}'

    if point_number == 1:
        return text[:max_chars]

    return ''


def _question_terms(question):
    stopwords = {
        'cfare', 'cila', 'cili', 'cilat', 'cilet', 'eshte', 'jane', 'jan',
        'ne', 'nga', 'te', 'dhe', 'ose', 'per', 'me', 'pa', 'si', 'ku',
        'kur', 'pse', 'a', 'e', 'i', 'u', 'kjo', 'ky', 'keto', 'ato',
        'dokumenti', 'dokument', 'pika', 'piken', 'pike', 'thuaj',
        'shpjego', 'trego', 'ma', 'mi', 'nje', 'disa', 'eshte'
    }
    normalized = question.lower()
    normalized = normalized.replace('\u00eb', 'e').replace('\u00e7', 'c')
    terms = re.findall(r'[a-z0-9]{3,}', normalized)

    return [
        term
        for term in terms
        if term not in stopwords
    ]


def _lexical_relevant_chunks(text, question, max_chunks=4):
    terms = _question_terms(question)

    if not terms:
        return []

    chunks = split_text(text, chunk_size=1200, overlap=180)
    scored_chunks = []

    for index, chunk in enumerate(chunks):
        normalized_chunk = chunk.lower()
        normalized_chunk = normalized_chunk.replace('\u00eb', 'e').replace('\u00e7', 'c')
        score = sum(
            normalized_chunk.count(term)
            for term in terms
        )

        if score:
            scored_chunks.append((score, index, chunk))

    scored_chunks.sort(key=lambda item: (-item[0], item[1]))
    selected = sorted(scored_chunks[:max_chunks], key=lambda item: item[1])

    return [
        chunk
        for _, _, chunk in selected
    ]


def _combine_contexts(*parts, max_chars=12000):
    combined_parts = []
    seen = set()

    for part in parts:
        if not part:
            continue

        for block in part if isinstance(part, list) else [part]:
            cleaned = block.strip()
            if not cleaned:
                continue

            key = cleaned[:160]
            if key in seen:
                continue

            seen.add(key)
            combined_parts.append(cleaned)

    return '\n\n---\n\n'.join(combined_parts)[:max_chars]


def _fallback_chunks(document, chunk_count=5):
    chunks = split_text(get_document_text(document))
    if not chunks:
        return []

    random.shuffle(chunks)
    return chunks[:chunk_count]


def get_document_collection(document):
    rag_client = get_rag_client()

    if rag_client is None:
        return None

    return rag_client.get_or_create_collection(
        name=f"document_{document.id}"
    )


def create_document_index(document, force=False):
    rag_client = get_rag_client()
    embedding_model = get_embedding_model()
    collection_name = f"document_{document.id}"

    if rag_client is None or embedding_model is None:
        return 0

    if not force:
        try:
            collection = get_document_collection(document)
            existing_count = collection.count() if collection else 0
            if existing_count > 0:
                return existing_count
        except Exception:
            return 0

    if force:
        try:
            rag_client.delete_collection(name=collection_name)
        except Exception:
            pass

    try:
        collection = get_document_collection(document)
    except Exception:
        return 0

    if collection is None:
        return 0

    text = get_document_text(document)
    chunks = split_text(text)

    for i, chunk in enumerate(chunks):
        embedding = embedding_model.encode(chunk).tolist()

        collection.add(
            ids=[f"{document.id}_{i}"],
            embeddings=[embedding],
            documents=[chunk],
            metadatas=[
                {
                    "document_id": document.id,
                    "chunk_index": i,
                }
            ],
        )

    return len(chunks)


def document_index_exists(document):
    try:
        collection = get_document_collection(document)
        if collection is None:
            return False
        return collection.count() > 0
    except Exception:
        return False


def ensure_document_index(document):
    if document_index_exists(document):
        return True

    return create_document_index(document) > 0


def search_document_chunks(document, question, n_results=4):
    full_text = get_document_text(document)
    point_number = _referenced_point_number(question)
    numbered_context = _extract_numbered_point_context(
        full_text,
        point_number
    )
    lexical_contexts = _lexical_relevant_chunks(
        full_text,
        question
    )

    rag_client = get_rag_client()
    embedding_model = get_embedding_model()
    fallback_context = _combine_contexts(
        numbered_context,
        lexical_contexts,
        _fallback_chunks(document, chunk_count=n_results),
        full_text[:5000]
    )

    if rag_client is None or embedding_model is None:
        return fallback_context

    try:
        if not ensure_document_index(document):
            return fallback_context
        collection = get_document_collection(document)
        if collection is None:
            return fallback_context
        collection_count = collection.count()
    except Exception:
        return fallback_context

    if collection_count == 0:
        return fallback_context

    try:
        question_embedding = embedding_model.encode(question).tolist()

        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=min(n_results, collection_count),
        )

        chunks = results["documents"][0]
    except Exception:
        return fallback_context

    relevant_text = "\n\n".join(chunks)

    if not relevant_text.strip():
        return fallback_context

    return _combine_contexts(
        numbered_context,
        lexical_contexts,
        relevant_text
    )


def search_multiple_documents(documents, question, n_results=8):
    rag_client = get_rag_client()
    embedding_model = get_embedding_model()

    if rag_client is None or embedding_model is None:
        return ""

    question_embedding = embedding_model.encode(question).tolist()
    gathered_chunks = []

    for document in documents:
        if len(gathered_chunks) >= n_results:
            break

        try:
            ensure_document_index(document)
            collection = get_document_collection(document)
            if collection is None:
                continue
        except Exception:
            continue

        remaining = n_results - len(gathered_chunks)

        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=remaining,
        )

        chunks = results.get("documents", [[]])[0]
        gathered_chunks.extend(chunks[:remaining])

    return "\n\n".join(gathered_chunks[:n_results])


def get_random_document_chunks(document, chunk_count=5):
    rag_client = get_rag_client()
    embedding_model = get_embedding_model()

    if rag_client is None or embedding_model is None:
        return _fallback_chunks(document, chunk_count=chunk_count)

    try:
        if not ensure_document_index(document):
            return _fallback_chunks(document, chunk_count=chunk_count)
        collection = get_document_collection(document)
        if collection is None:
            return _fallback_chunks(document, chunk_count=chunk_count)
    except Exception:
        return _fallback_chunks(document, chunk_count=chunk_count)

    try:
        results = collection.get(include=['documents'])
    except Exception:
        return _fallback_chunks(document, chunk_count=chunk_count)

    chunks = [
        chunk
        for chunk in results.get('documents', [])
        if chunk
    ]

    if not chunks:
        return _fallback_chunks(document, chunk_count=chunk_count)

    random.shuffle(chunks)
    return chunks[:chunk_count]

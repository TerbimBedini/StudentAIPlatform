import random
import re

from django.conf import settings

from .utils import extract_text_from_document


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


def create_document_index(document):
    rag_client = get_rag_client()
    embedding_model = get_embedding_model()

    if rag_client is None or embedding_model is None:
        return 0

    text = extract_text_from_document(document.file.path)

    chunks = split_text(text)

    collection_name = f"document_{document.id}"

    try:
        rag_client.delete_collection(name=collection_name)
    except Exception:
        pass

    collection = rag_client.get_or_create_collection(
        name=collection_name
    )

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


def search_document_chunks(document, question, n_results=4):
    full_text = extract_text_from_document(document.file.path)
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

    if rag_client is None or embedding_model is None:
        return _combine_contexts(
            numbered_context,
            lexical_contexts,
            full_text[:5000]
        )

    collection_name = f"document_{document.id}"

    try:
        collection = rag_client.get_collection(name=collection_name)
    except Exception:
        created_chunks = create_document_index(document)
        if not created_chunks:
            return _combine_contexts(
                numbered_context,
                lexical_contexts,
                full_text[:5000]
            )

        try:
            collection = rag_client.get_collection(name=collection_name)
        except Exception:
            return _combine_contexts(
                numbered_context,
                lexical_contexts,
                full_text[:5000]
            )

    collection_count = collection.count()

    if collection_count == 0:
        created_chunks = create_document_index(document)
        if not created_chunks:
            return _combine_contexts(
                numbered_context,
                lexical_contexts,
                full_text[:5000]
            )

        try:
            collection = rag_client.get_collection(name=collection_name)
            collection_count = collection.count()
        except Exception:
            return _combine_contexts(
                numbered_context,
                lexical_contexts,
                full_text[:5000]
            )

    if collection_count == 0:
        return _combine_contexts(
            numbered_context,
            lexical_contexts,
            full_text[:5000]
        )

    question_embedding = embedding_model.encode(question).tolist()

    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=min(n_results, collection_count),
    )

    chunks = results["documents"][0]

    relevant_text = "\n\n".join(chunks)

    if not relevant_text.strip():
        return _combine_contexts(
            numbered_context,
            lexical_contexts,
            full_text[:5000]
        )

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

        collection_name = f"document_{document.id}"

        try:
            collection = rag_client.get_collection(
                name=collection_name
            )
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
        return []

    collection_name = f"document_{document.id}"

    try:
        collection = rag_client.get_collection(name=collection_name)
    except Exception:
        created_chunks = create_document_index(document)
        if not created_chunks:
            return []

        try:
            collection = rag_client.get_collection(name=collection_name)
        except Exception:
            return []

    try:
        results = collection.get(include=['documents'])
    except Exception:
        return []

    chunks = [
        chunk
        for chunk in results.get('documents', [])
        if chunk
    ]

    if not chunks:
        return []

    random.shuffle(chunks)
    return chunks[:chunk_count]

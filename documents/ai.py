import logging
import os
import random
import re
import time


OLLAMA_URL = os.environ.get(
    'OLLAMA_URL',
    'http://127.0.0.1:11434/api/generate'
)
OLLAMA_MODEL = os.environ.get(
    'OLLAMA_MODEL',
    'gemma3:4b'
)
OLLAMA_KEEP_ALIVE = os.environ.get(
    'OLLAMA_KEEP_ALIVE',
    '30m'
)
logger = logging.getLogger(__name__)


class AIError(Exception):
    pass


def ollama_generate(payload, timeout):
    try:
        import requests
    except ImportError as exc:
        raise AIError(
            'Paketa requests mungon. Instalo dependencies me: pip install -r requirements.txt'
        ) from exc

    try:
        payload.setdefault('model', OLLAMA_MODEL)
        payload.setdefault('keep_alive', OLLAMA_KEEP_ALIVE)

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=(5, timeout)
        )
        if not response.ok:
            logger.warning(
                'Ollama request failed with status %s: %s',
                response.status_code,
                response.text[:200]
            )
        response.raise_for_status()
        return response.json().get('response', '')
    except requests.Timeout as exc:
        logger.warning(
            'Ollama request timed out after %s seconds for %s',
            timeout,
            OLLAMA_URL
        )
        raise AIError(
            f'Ollama nuk u pergjigj brenda {timeout} sekondash. Provo perseri ose perdor nje kontekst me te shkurter.'
        ) from exc
    except requests.RequestException as exc:
        response = getattr(exc, 'response', None)
        if response is not None:
            logger.warning(
                'Ollama request exception with status %s: %s',
                response.status_code,
                response.text[:200]
            )
        raise AIError(
            f'AI nuk u lidh dot me Ollama. Kontrollo qe Ollama te jete hapur dhe modeli {OLLAMA_MODEL} te jete i ngarkuar.'
        ) from exc
    except ValueError as exc:
        raise AIError('Ollama ktheu nje pergjigje te pavlefshme.') from exc


def call_ollama(
    label,
    prompt,
    temperature=0.4,
    num_predict=700,
    timeout=90,
    top_p=0.86,
    num_ctx=2048,
    keep_alive=None
):
    started_at = time.perf_counter()

    try:
        payload = {
            'prompt': prompt,
            'stream': False,
            'options': {
                'num_predict': num_predict,
                'num_ctx': num_ctx,
                'temperature': temperature,
                'top_p': top_p,
                'seed': random.randint(1, 2_147_483_647),
            }
        }
        if keep_alive is not None:
            payload['keep_alive'] = keep_alive

        response = ollama_generate(payload, timeout=timeout)
        logger.info('%s: %.1f seconds', label, time.perf_counter() - started_at)
        return response
    except AIError as exc:
        logger.warning(
            '%s failed after %.1f seconds: %s',
            label,
            time.perf_counter() - started_at,
            exc
        )
        raise AIError(
            'AI nuk u pergjigj dot tani. Provo perseri pas pak ose kontrollo qe Ollama eshte hapur.'
        ) from exc


def warmup_ollama_model():
    return call_ollama(
        'Ollama warmup',
        'ping',
        temperature=0.1,
        num_predict=1,
        timeout=30
    )


def unload_ollama_model():
    return call_ollama(
        'Ollama unload',
        '',
        temperature=0.1,
        num_predict=1,
        timeout=30,
        keep_alive='0'
    )


def generate_summary(text):
    prompt = f'''
Permblidhe tekstin ne shqip me pika te shkurtra.
Perdor vetem informacion nga teksti.

Teksti:
{text[:2600]}
'''
    return call_ollama(
        'Summary',
        prompt,
        temperature=0.2,
        num_predict=420,
        timeout=75
    )


def _contextual_fallback_answer(document_text, question, max_sentences=3):
    stopwords = {
        'cfare', 'cila', 'cili', 'cilat', 'cilet', 'eshte', 'jane', 'jan',
        'nga', 'per', 'dhe', 'ose', 'me', 'pa', 'kjo', 'ky', 'keto', 'ato',
        'dokumenti', 'dokument', 'shpjego', 'trego', 'pse', 'kur', 'si',
        'what', 'which', 'why', 'how', 'the', 'and', 'for', 'with'
    }
    normalized_question = question.lower()
    normalized_question = normalized_question.replace('e', 'e').replace('c', 'c')
    terms = [
        term
        for term in re.findall(r'[a-z0-9]{3,}', normalized_question)
        if term not in stopwords
    ]
    sentences = [
        sentence.strip()
        for sentence in re.split(r'(?<=[.!?])\s+|\n+', document_text)
        if len(sentence.strip()) >= 30
    ]

    if not sentences:
        return 'Dokumenti nuk permban informacion te mjaftueshem per kete pyetje.'

    if not terms:
        selected = sentences[:max_sentences]
    else:
        scored_sentences = []
        for index, sentence in enumerate(sentences):
            normalized_sentence = sentence.lower()
            score = sum(normalized_sentence.count(term) for term in terms)
            if score:
                scored_sentences.append((score, index, sentence))

        if not scored_sentences:
            return 'Dokumenti nuk permban informacion te mjaftueshem per kete pyetje.'

        scored_sentences.sort(key=lambda item: (-item[0], item[1]))
        selected = [
            sentence
            for _, _, sentence in sorted(
                scored_sentences[:max_sentences],
                key=lambda item: item[1]
            )
        ]

    return 'Sipas dokumentit, ' + ' '.join(selected)


def ask_document_ai(document_text, question):
    prompt = f'''
Pergjigju vetem nga konteksti i dokumentit. Nese pergjigjja mungon, thuaj:
"Dokumenti nuk permban informacion te mjaftueshem per kete pyetje."
Pergjigju shkurt dhe qarte ne shqip.

Konteksti:
{document_text[:3000]}

Pyetja:
{question}
'''
    try:
        return call_ollama(
            'AI Chat',
            prompt,
            temperature=0.1,
            num_predict=220,
            timeout=60,
            top_p=0.8
        )
    except AIError:
        return _contextual_fallback_answer(document_text, question)


def select_quiz_source_text(document_text, target_chars=1000, window_chars=600):
    cleaned_text = document_text.strip()
    if len(cleaned_text) <= target_chars:
        return cleaned_text

    windows = []
    step = max(300, window_chars // 2)
    for start in range(0, len(cleaned_text), step):
        window = cleaned_text[start:start + window_chars].strip()
        if len(window) >= 180:
            windows.append(window)

    if not windows:
        max_start = max(0, len(cleaned_text) - target_chars)
        start = random.randint(0, max_start)
        return cleaned_text[start:start + target_chars]

    random.shuffle(windows)
    return '\n\n---\n\n'.join(windows[:2])[:target_chars]


def _select_context(document_text, context_chunks=None, target_chars=1000):
    chunks = [str(chunk).strip() for chunk in (context_chunks or []) if str(chunk).strip()]
    if chunks:
        random.shuffle(chunks)
        return '\n\n---\n\n'.join(chunks[:3])[:target_chars]
    return select_quiz_source_text(document_text, target_chars=target_chars)


def generate_quiz(
    document_text,
    previous_questions=None,
    context_chunks=None,
    difficulty=None,
    quiz_style=None,
    focus_topics=None,
    strategy_instruction=''
):
    selected_text = _select_context(document_text, context_chunks, target_chars=1000)
    previous_questions = previous_questions or []
    random.shuffle(previous_questions)
    previous_question_text = '\n'.join(
        f'- {question}'
        for question in previous_questions[:5]
        if str(question).strip()
    ) or 'No previous questions.'

    difficulty = difficulty or random.choice(["easy", "medium", "hard"])
    quiz_style = quiz_style or random.choice([
        "exam-style",
        "analytical",
        "conceptual",
        "practical"
    ])
    focus_text = ', '.join(focus_topics or []) or 'main document concepts'
    strategy_instruction = strategy_instruction or (
        'Create useful document-grounded questions for studying.'
    )

    prompt = (
        'Krijo deri ne 5 pyetje quiz vetem nga konteksti. '
        'Pyet per kuptim, jo per fraza te shkeputura. '
        'Kthe vetem JSON valid pa markdown me formen: '
        '[{"question":"...","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"A"}]\n'
        f'Seed: {time.time_ns()}-{random.randint(1000, 999999)}\n'
        f'Difficulty: {difficulty}\n'
        f'Style: {quiz_style}\n'
        f'Focus topics: {focus_text}\n'
        f'Strategy: {strategy_instruction}\n'
        f'Avoid: {previous_question_text}\n'
        f'Context:\n{selected_text}'
    )

    try:
        return call_ollama(
            'Quiz',
            prompt,
            temperature=0.7,
            num_predict=220,
            timeout=12,
            top_p=0.9
        )
    except AIError:
        return generate_fast_document_quiz(selected_text, max_questions=5)


def generate_exam(document_text):
    selected_text = select_quiz_source_text(
        document_text,
        target_chars=1200,
        window_chars=600
    )
    prompt = f'''
Krijo 3 pyetje provimi vetem nga konteksti.
Kthe vetem JSON valid pa markdown.
Schema:
[{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"answer":"A","explanation":"shkurt"}}]
Context:
{selected_text}
'''
    try:
        return call_ollama(
            'Exam',
            prompt,
            temperature=0.6,
            num_predict=280,
            timeout=40,
            top_p=0.84
        )
    except AIError:
        return generate_fast_document_quiz(selected_text, max_questions=3)


def generate_mixed_exam(document_text):
    selected_text = select_quiz_source_text(
        document_text,
        target_chars=1200,
        window_chars=600
    )
    prompt = f'''
Krijo exam simulator me 3 items vetem nga konteksti.
Kthe vetem JSON valid pa markdown.
Schema:
{{"quiz":[{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"answer":"A","explanation":"shkurt"}}],"flashcards":[{{"question":"...","answer":"..."}}]}}
Krijo 2 quiz dhe 1 flashcard.
Context:
{selected_text}
'''
    try:
        return call_ollama(
            'Exam Simulator',
            prompt,
            temperature=0.6,
            num_predict=280,
            timeout=40,
            top_p=0.86
        )
    except AIError:
        return '\n\n'.join([
            'QUIZ',
            generate_fast_document_quiz(selected_text, max_questions=2),
            'FLASHCARDS',
            generate_fast_flashcards(selected_text, max_cards=1),
        ])


def build_text_based_options(correct_answer, correct_key):
    correct_answer = ' '.join(str(correct_answer).split()[:18])
    distractors = [
        'Kjo alternative lidhet me temen, por ndryshon thelbin e shpjegimit ne dokument.',
        'Kjo alternative e trajton idene si shembull anesor, jo si perfundim kryesor.',
        'Kjo alternative nxjerr nje perfundim qe nuk mbeshtetet drejt nga dokumenti.',
    ]
    random.shuffle(distractors)

    options = {}
    distractor_index = 0
    for key in ['A', 'B', 'C', 'D']:
        if key == correct_key:
            options[key] = correct_answer
        else:
            options[key] = distractors[distractor_index]
            distractor_index += 1
    return options


def generate_fast_document_quiz(document_text, max_questions=5):
    sentences = [
        sentence.strip()
        for sentence in re.split(r'(?<=[.!?])\s+|\n+', document_text)
        if len(sentence.strip()) >= 35
    ]

    if not sentences:
        cleaned = document_text.strip()
        if cleaned:
            sentences = [cleaned[:240]]

    if not sentences:
        return ''

    if len(sentences) > max_questions:
        selected_sentences = random.sample(sentences, max_questions)
    else:
        selected_sentences = sentences[:]
        while len(selected_sentences) < max_questions:
            selected_sentences.append(random.choice(sentences))

    random.shuffle(selected_sentences)
    quiz_lines = []

    for index, sentence in enumerate(selected_sentences, start=1):
        short_sentence = sentence[:220].strip()
        question = random.choice([
            'Cili eshte kuptimi kryesor i kesaj pjese te dokumentit?',
            'Cila alternative e shpjegon me sakte idene ne kete pjese?',
            'Cfare duhet te kuptoje studenti nga kjo pjese e materialit?',
        ])
        correct_key = random.choice(['A', 'B', 'C', 'D'])
        options = build_text_based_options(short_sentence, correct_key)
        quiz_lines.append(f'{index}. {question}')
        for key in ['A', 'B', 'C', 'D']:
            quiz_lines.append(f'{key}) {options[key]}')
        quiz_lines.extend([f'Pergjigjja e sakte: {correct_key}', ''])

    return '\n'.join(quiz_lines)


def generate_fast_flashcards(document_text, max_cards=3):
    sentences = [
        sentence.strip()
        for sentence in re.split(r'(?<=[.!?])\s+|\n+', document_text)
        if len(sentence.strip()) >= 35
    ]

    if not sentences:
        cleaned = document_text.strip()
        if cleaned:
            sentences = [cleaned[:240]]

    selected_sentences = random.sample(sentences, min(max_cards, len(sentences))) if sentences else []
    flashcard_lines = []

    for index, sentence in enumerate(selected_sentences, start=1):
        short_sentence = sentence[:240].strip()
        question = random.choice([
            'Cila eshte ideja kryesore qe duhet mbajtur mend nga kjo pjese?',
            'Si do ta shpjegoje kete koncept me fjalet e tua?',
            'Cfare kuptimi ka kjo pjese ne materialin e dokumentit?',
        ])
        flashcard_lines.extend([
            f'{index}. Pyetje: {question}',
            f'   Pergjigje: {short_sentence}',
            ''
        ])

    return '\n'.join(flashcard_lines)


def generate_flashcards(document_text):
    focus = random.choice([
        'konceptet kryesore',
        'perkufizimet',
        'shembujt dhe zbatimet',
        'shkaqet dhe pasojat',
    ])
    selected_text = select_quiz_source_text(
        document_text,
        target_chars=1000,
        window_chars=550
    )
    prompt = f'''
Krijo 3 flashcards vetem nga teksti. Fokus: {focus}.
Kthe vetem JSON valid pa markdown.
Schema:
[{{"question":"...","answer":"..."}}]
Teksti:
{selected_text}
'''
    try:
        return call_ollama(
            'Flashcards',
            prompt,
            temperature=0.6,
            num_predict=200,
            timeout=30,
            top_p=0.86
        )
    except AIError:
        return generate_fast_flashcards(selected_text, max_cards=3)

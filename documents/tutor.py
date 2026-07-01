import logging
import random
import re

from .ai import AIError, call_ollama


logger = logging.getLogger(__name__)


NOT_ENOUGH_CONTEXT = (
    'Dokumenti nuk permban informacion te mjaftueshem per kete pyetje.'
)


def _clean_context(context, max_chars=2600):
    return ' '.join((context or '').split())[:max_chars]


def _extract_sentences(context, limit=3):
    sentences = [
        sentence.strip()
        for sentence in re.split(r'(?<=[.!?])\s+|\n+', context or '')
        if len(sentence.strip()) >= 35
    ]
    return sentences[:limit]


def _fallback_tutor_turn(context, student_message, tutor_state=None):
    sentences = _extract_sentences(context)
    if not sentences:
        return (
            NOT_ENOUGH_CONTEXT,
            {'last_question': None}
        )

    previous_question = (tutor_state or {}).get('last_question')
    explanation = ' '.join(sentences)
    follow_up = random.choice([
        'Si do ta shpjegoje kete ide me fjalet e tua?',
        'Cili eshte elementi me i rendesishem ne kete pjese?',
        'Pse mendon se kjo ide ka rendesi ne material?',
    ])

    if previous_question:
        reply = (
            f'Veleresim: E mora pergjigjen tende per pyetjen "{previous_question}". '
            'Krahasoje me shpjegimin kryesor nga dokumenti me poshte.\n\n'
            f'Shpjegim: {explanation}\n\n'
            f'Pyetje: {follow_up}'
        )
    else:
        reply = (
            f'Shpjegim: {explanation}\n\n'
            f'Pyetje: {follow_up}'
        )

    return reply, {'last_question': follow_up}


def _extract_follow_up_question(reply):
    if not reply:
        return None

    patterns = [
        r'Pyetje\s*:\s*(.+?)(?:\n|$)',
        r'Pyetja\s*(?:tjeter|pasuese)?\s*:\s*(.+?)(?:\n|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, reply, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()

    question_lines = [
        line.strip()
        for line in reply.splitlines()
        if line.strip().endswith('?')
    ]
    return question_lines[-1] if question_lines else None


def generate_tutor_turn(context, student_message, tutor_state=None):
    context = _clean_context(context)
    student_message = (student_message or '').strip()
    tutor_state = tutor_state or {}

    if not context:
        return NOT_ENOUGH_CONTEXT, {'last_question': None}

    previous_question = tutor_state.get('last_question') or ''
    if previous_question:
        task = (
            'Studenti po i pergjigjet pyetjes tende te fundit. '
            'Vlereso pergjigjen, korrigjo gabimet me informacion nga konteksti, '
            'pastaj bej nje pyetje tjeter.'
        )
    else:
        task = (
            'Studenti kerkon shpjegim. Shpjego konceptin si tutor, '
            'pastaj bej nje pyetje kontrolluese.'
        )

    prompt = f'''
Je StudentAI Tutor. Perdor vetem kontekstin e dokumentit.
Nese konteksti nuk mjafton, thuaj: "{NOT_ENOUGH_CONTEXT}"
Mos jep pergjigje te gjata. Meso studentin hap pas hapi.

Detyra:
{task}

Kthe pergjigjen ne kete forme:
Shpjegim: ...
Vleresim: ...  (vetem kur studenti po i pergjigjet pyetjes se fundit)
Pyetje: ...

Konteksti:
{context}

Pyetja e fundit e tutorit:
{previous_question or 'Asnje'}

Mesazhi i studentit:
{student_message}
'''

    try:
        reply = call_ollama(
            'AI Tutor',
            prompt,
            temperature=0.35,
            num_predict=260,
            timeout=45,
            top_p=0.84
        ).strip()
    except AIError:
        logger.warning('AI Tutor fallback used after Ollama failure.')
        return _fallback_tutor_turn(context, student_message, tutor_state)

    follow_up_question = _extract_follow_up_question(reply)
    return reply, {'last_question': follow_up_question}

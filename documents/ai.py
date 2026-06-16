import os
import random
import requests


OLLAMA_URL = os.environ.get(
    'OLLAMA_URL',
    'http://localhost:11434/api/generate'
)


class AIError(Exception):
    pass


def ollama_generate(payload, timeout):
    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=timeout
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except requests.RequestException as exc:
        raise AIError(
            'AI nuk u lidh dot me Ollama. Kontrollo qe Ollama te jete hapur dhe modeli gemma3:4b te jete i ngarkuar.'
        ) from exc
    except ValueError as exc:
        raise AIError('Ollama ktheu nje pergjigje te pavlefshme.') from exc


def generate_summary(text):
    prompt = f"""
Ti je asistent akademik per studente shqiptare.

Permblidhe tekstin me poshte ne shqip te paster.
Perdor fjali te qarta, pika kryesore dhe stil universitar.

Teksti:
{text[:4000]}
"""

    return ollama_generate(
        {
            "model": "gemma3:4b",
            "prompt": prompt,
            "stream": False
        },
        timeout=300
    )


def ask_document_ai(document_text, question):
    prompt = f"""
Ti je asistent akademik per studente shqiptare.

Pergjigju pyetjes vetem duke u bazuar ne tekstin e dokumentit.
Nese pergjigjja nuk gjendet ne tekst, thuaj:
"Ky informacion nuk gjendet qarte ne dokument."

Teksti i dokumentit:
{document_text[:2500]}

Pyetja:
{question}
"""

    return ollama_generate(
        {
            "model": "gemma3:4b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 140
            }
        },
        timeout=600
    )


def generate_quiz(document_text):
    prompt = f"""
Ti je pedagog universitar.

Krijo 10 pyetje me alternativa VETEM nga teksti i dokumentit me poshte.
Mos perdor njohuri te pergjithshme.
Mos shpik tema, emra, fakte ose pyetje qe nuk mbeshteten ne tekst.
Nese teksti nuk mjafton per 10 pyetje, krijo aq pyetje sa mbeshteten qarte ne tekst.
Cdo pyetje duhet te lidhet drejtpersedrejti me nje fakt, koncept ose fjali nga dokumenti.

Formati:

1. Pyetja
A) Alternativa
B) Alternativa
C) Alternativa
D) Alternativa
Pergjigjja e sakte: A

Teksti:
{document_text[:3000]}
"""

    return ollama_generate(
        {
            "model": "gemma3:4b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 600
            }
        },
        timeout=300
    )


def generate_flashcards(document_text):
    focus_options = [
        'konceptet kryesore',
        'perkufizimet',
        'shembujt dhe zbatimet',
        'shkaqet dhe pasojat',
        'detajet qe studenti mund t\'i harroje',
        'krahasimet mes ideve'
    ]
    focus = random.choice(focus_options)

    text_limit = 2500
    if len(document_text) > text_limit:
        max_start = max(0, len(document_text) - text_limit)
        start = random.randint(0, max_start)
        selected_text = document_text[start:start + text_limit]
    else:
        selected_text = document_text

    prompt = f"""
Ti je asistent akademik per studente shqiptare.

Bazuar ne tekstin me poshte, krijo 10 flashcards per perseritje.
Perdor vetem informacion nga teksti.
Per kete set fokusohu te: {focus}.
Krijo pyetje te ndryshme dhe mos perdor gjithmone te njejten renditje.

Formati:
1. Pyetje: ...
   Pergjigje: ...

Teksti:
{selected_text}
"""

    return ollama_generate(
        {
            "model": "gemma3:4b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 500
            }
        },
        timeout=300
    )

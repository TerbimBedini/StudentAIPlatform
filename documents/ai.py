import requests


def generate_summary(text):
    prompt = f"""
Ti je asistent akademik për studentë shqiptarë.

Përmblidhe tekstin më poshtë në shqip të pastër.
Përdor fjali të qarta, pika kryesore dhe stil universitar.

Teksti:
{text[:4000]}
"""

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "gemma3:4b",
            "prompt": prompt,
            "stream": False
        },
        timeout=300
    )

    return response.json()["response"]


def ask_document_ai(document_text, question):
    prompt = f"""
Ti je asistent akademik për studentë shqiptarë.

Përgjigju pyetjes vetëm duke u bazuar në tekstin e dokumentit.
Nëse përgjigjja nuk gjendet në tekst, thuaj:
"Ky informacion nuk gjendet qartë në dokument."

Teksti i dokumentit:
{document_text[:4000]}

Pyetja:
{question}
"""

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "gemma3:4b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 200
            }
        },
        timeout=600
    )

    return response.json().get("response", "")

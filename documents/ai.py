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
        timeout=120
    )

    return response.json()["response"]
import os
import requests
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_URL = os.getenv("EVOLUTION_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")


def enviar_whatsapp(mensagem: str):
    try:
        url = f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}"
        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        payload = {"number": WHATSAPP_NUMBER, "text": mensagem}
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code not in (200, 201):
            print(f"Aviso: WhatsApp retornou status {response.status_code}")
    except Exception as e:
        print(f"Erro ao enviar WhatsApp: {e}")

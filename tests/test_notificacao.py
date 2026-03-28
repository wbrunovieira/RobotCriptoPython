import pytest
import requests
from unittest.mock import MagicMock, patch
from notificacao import enviar_whatsapp, EVOLUTION_URL, EVOLUTION_INSTANCE, EVOLUTION_API_KEY, WHATSAPP_NUMBER


def test_enviar_whatsapp_sucesso():
    mock_response = MagicMock()
    mock_response.status_code = 201

    with patch("notificacao.requests.post", return_value=mock_response) as mock_post:
        enviar_whatsapp("Teste de mensagem")

        mock_post.assert_called_once_with(
            f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
            json={"number": WHATSAPP_NUMBER, "text": "Teste de mensagem"},
            headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"},
            timeout=10,
        )


def test_enviar_whatsapp_falha_conexao_nao_lanca_excecao():
    with patch("notificacao.requests.post", side_effect=requests.exceptions.ConnectionError):
        enviar_whatsapp("Teste")  # não deve lançar exceção


def test_enviar_whatsapp_status_erro_nao_lanca_excecao():
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("notificacao.requests.post", return_value=mock_response):
        enviar_whatsapp("Teste")  # não deve lançar exceção


def test_enviar_whatsapp_timeout_nao_lanca_excecao():
    with patch("notificacao.requests.post", side_effect=requests.exceptions.Timeout):
        enviar_whatsapp("Teste")  # não deve lançar exceção

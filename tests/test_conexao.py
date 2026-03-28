import pytest
from unittest.mock import MagicMock, patch
from conexao import calcular_offset_tempo, criar_cliente_sincronizado


def test_offset_quando_servidor_adiantado():
    # Servidor 3000ms na frente do local → offset positivo
    assert calcular_offset_tempo(tempo_servidor_ms=1000003000, tempo_local_ms=1000000000) == 3000


def test_offset_quando_servidor_atrasado():
    # Servidor 2000ms atrás do local → offset negativo
    assert calcular_offset_tempo(tempo_servidor_ms=1000000000, tempo_local_ms=1000002000) == -2000


def test_offset_zero_quando_sincronizado():
    assert calcular_offset_tempo(tempo_servidor_ms=1000000000, tempo_local_ms=1000000000) == 0


def test_criar_cliente_sincronizado_aplica_offset():
    mock_client = MagicMock()
    mock_client.get_server_time.return_value = {"serverTime": 1000003000}

    with patch("conexao.Client") as MockClient, \
         patch("conexao.time") as mock_time:

        MockClient.return_value = mock_client
        mock_time.time.return_value = 1000000.0  # 1000000000 ms

        cliente = criar_cliente_sincronizado("key", "secret")

        assert mock_client.timestamp_offset == 3000


def test_criar_cliente_sincronizado_offset_negativo():
    mock_client = MagicMock()
    mock_client.get_server_time.return_value = {"serverTime": 999998000}

    with patch("conexao.Client") as MockClient, \
         patch("conexao.time") as mock_time:

        MockClient.return_value = mock_client
        mock_time.time.return_value = 1000000.0  # 1000000000 ms

        cliente = criar_cliente_sincronizado("key", "secret")

        assert mock_client.timestamp_offset == -2000


def test_criar_cliente_sincronizado_retorna_cliente():
    mock_client = MagicMock()
    mock_client.get_server_time.return_value = {"serverTime": 1000000000}

    with patch("conexao.Client") as MockClient, \
         patch("conexao.time") as mock_time:

        MockClient.return_value = mock_client
        mock_time.time.return_value = 1000000.0

        cliente = criar_cliente_sincronizado("key", "secret")

        assert cliente is mock_client

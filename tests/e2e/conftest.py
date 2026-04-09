"""Configuração dos testes E2E.

Testes marcados com @pytest.mark.e2e só rodam quando KEY_BINANCE e
SECRET_BINANCE estão disponíveis no ambiente. Caso contrário, são skipados
automaticamente com uma mensagem explicativa.

Para rodar:
    pytest tests/e2e/ -v                   # pula se sem credenciais
    pytest tests/e2e/ -v -m e2e            # idem
    KEY_BINANCE=... SECRET_BINANCE=... pytest tests/e2e/ -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def pytest_collection_modifyitems(config, items):
    """Adiciona skip automático em testes e2e sem credenciais Binance."""
    tem_credenciais = bool(os.getenv("KEY_BINANCE") and os.getenv("SECRET_BINANCE"))
    if tem_credenciais:
        return
    skip_e2e = pytest.mark.skip(
        reason="Teste E2E ignorado: KEY_BINANCE/SECRET_BINANCE não definidos no ambiente."
    )
    for item in items:
        if item.get_closest_marker("e2e"):
            item.add_marker(skip_e2e)


@pytest.fixture(scope="session")
def binance_cliente():
    """Cria cliente Binance real para os testes E2E (sessão inteira)."""
    from dotenv import load_dotenv
    load_dotenv()
    from infra.binance_client import criar_cliente_sincronizado
    api_key = os.getenv("KEY_BINANCE")
    secret_key = os.getenv("SECRET_BINANCE")
    if not api_key or not secret_key:
        pytest.skip("Credenciais Binance não disponíveis.")
    return criar_cliente_sincronizado(api_key, secret_key)


@pytest.fixture(scope="session")
def dados_solbrl_30d(binance_cliente):
    """Candles SOLBRL 1h dos últimos 30 dias — compartilhado entre testes."""
    from analysis.backtest_real import buscar_candles
    return buscar_candles(binance_cliente, "SOLBRL", "1h", 30)


@pytest.fixture(scope="session")
def dados_btcbrl_4h_30d(binance_cliente):
    """Candles BTCBRL 4h dos últimos 30 dias — compartilhado entre testes."""
    from analysis.backtest_real import buscar_candles
    return buscar_candles(binance_cliente, "BTCBRL", "4h", 30)

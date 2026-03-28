import pytest
import json
import os
from fastapi.testclient import TestClient
from unittest.mock import patch


# Token de teste — em produção vem do .env
TEST_TOKEN = "test-token-seguro"
AUTH_HEADER = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Cliente de teste com diretório isolado e token fixo."""
    monkeypatch.setenv("API_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("STATS_DIR", str(tmp_path / "stats"))
    monkeypatch.setenv("POSICAO_DIR", str(tmp_path))
    monkeypatch.setenv("RESERVA_FILE", str(tmp_path / "reserva.json"))
    monkeypatch.setenv("STATUS_FILE", str(tmp_path / "status.json"))

    from api.main import app
    return TestClient(app)


def _criar_stats(tmp_path, data, operacoes):
    stats_dir = tmp_path / "stats"
    stats_dir.mkdir(exist_ok=True)
    arquivo = stats_dir / f"{data}.json"
    arquivo.write_text(json.dumps({
        "data": data, "saldo_inicial_brl": 1000.0, "operacoes": operacoes
    }))


def _criar_posicao(tmp_path, simbolo, posicao, preco_entrada=None, preco_maximo=None, stop_price=None):
    arquivo = tmp_path / f"posicao_{simbolo}.json"
    arquivo.write_text(json.dumps({
        "posicao": posicao,
        "preco_entrada": preco_entrada,
        "preco_maximo": preco_maximo,
        "stop_price": stop_price,
    }))


def _criar_status(tmp_path, ultimo_ciclo, rodando=True):
    arquivo = tmp_path / "status.json"
    arquivo.write_text(json.dumps({
        "ultimo_ciclo": ultimo_ciclo,
        "rodando": rodando,
        "versao": "1.0.0",
    }))


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------

def test_sem_token_retorna_401(client):
    response = client.get("/status")
    assert response.status_code == 401


def test_token_invalido_retorna_401(client):
    response = client.get("/status", headers={"Authorization": "Bearer errado"})
    assert response.status_code == 401


def test_token_correto_retorna_200(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATUS_FILE", str(tmp_path / "status.json"))
    _criar_status(tmp_path, "2026-03-28 14:55:00")
    response = client.get("/status", headers=AUTH_HEADER)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

def test_status_retorna_campos_esperados(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATUS_FILE", str(tmp_path / "status.json"))
    _criar_status(tmp_path, "2026-03-28 14:55:00")
    response = client.get("/status", headers=AUTH_HEADER)
    data = response.json()
    assert "ultimo_ciclo" in data
    assert "rodando" in data


def test_status_sem_arquivo_retorna_bot_parado(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATUS_FILE", str(tmp_path / "nao_existe.json"))
    response = client.get("/status", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["rodando"] is False


# ---------------------------------------------------------------------------
# GET /posicoes
# ---------------------------------------------------------------------------

def test_posicoes_retorna_todos_os_pares(client, tmp_path, monkeypatch):
    monkeypatch.setenv("POSICAO_DIR", str(tmp_path))
    _criar_posicao(tmp_path, "SOLBRL", False)
    _criar_posicao(tmp_path, "BTCBRL", True, 351168.0, 351636.0, 334054.20)
    _criar_posicao(tmp_path, "ETHBRL", True, 10620.52, 10625.55, 10094.27)

    response = client.get("/posicoes", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert "SOLBRL" in data
    assert "BTCBRL" in data
    assert "ETHBRL" in data


def test_posicoes_btc_comprado_tem_campos_corretos(client, tmp_path, monkeypatch):
    monkeypatch.setenv("POSICAO_DIR", str(tmp_path))
    _criar_posicao(tmp_path, "BTCBRL", True, 351168.0, 351636.0, 334054.20)
    for s in ["SOLBRL", "ETHBRL"]:
        _criar_posicao(tmp_path, s, False)

    response = client.get("/posicoes", headers=AUTH_HEADER)
    btc = response.json()["BTCBRL"]
    assert btc["posicao"] is True
    assert btc["preco_entrada"] == pytest.approx(351168.0)
    assert btc["stop_price"] == pytest.approx(334054.20)


def test_posicoes_sem_arquivo_retorna_nao_comprado(client, tmp_path, monkeypatch):
    monkeypatch.setenv("POSICAO_DIR", str(tmp_path))
    response = client.get("/posicoes", headers=AUTH_HEADER)
    data = response.json()
    for par in ["SOLBRL", "BTCBRL", "ETHBRL"]:
        assert data[par]["posicao"] is False


# ---------------------------------------------------------------------------
# GET /stats/dia
# ---------------------------------------------------------------------------

def test_stats_dia_retorna_resumo(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DIR", str(tmp_path / "stats"))
    _criar_stats(tmp_path, "2026-03-28", [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "timestamp": "09:00"},
        {"tipo": "VENDA", "preco": 460.0, "quantidade": 2.0, "total_brl": 920.0,
         "lucro_brl": 40.0, "lucro_pct": 4.5, "timestamp": "15:00"},
    ])
    response = client.get("/stats/dia?data=2026-03-28", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["total_operacoes"] == 1
    assert data["lucro_total_brl"] == pytest.approx(40.0)
    assert data["taxa_acerto_pct"] == pytest.approx(100.0)


def test_stats_dia_sem_data_usa_hoje(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DIR", str(tmp_path / "stats"))
    from datetime import date
    hoje = date.today().strftime("%Y-%m-%d")
    _criar_stats(tmp_path, hoje, [])
    response = client.get("/stats/dia", headers=AUTH_HEADER)
    assert response.status_code == 200


def test_stats_dia_inexistente_retorna_zerado(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DIR", str(tmp_path / "stats"))
    response = client.get("/stats/dia?data=2099-01-01", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["total_operacoes"] == 0


# ---------------------------------------------------------------------------
# GET /stats/mes
# ---------------------------------------------------------------------------

def test_stats_mes_agrega_dias(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DIR", str(tmp_path / "stats"))
    _criar_stats(tmp_path, "2026-03-01", [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "timestamp": "09:00"},
        {"tipo": "VENDA", "preco": 460.0, "quantidade": 2.0, "total_brl": 920.0,
         "lucro_brl": 40.0, "lucro_pct": 4.5, "timestamp": "15:00"},
    ])
    _criar_stats(tmp_path, "2026-03-15", [
        {"tipo": "COMPRA", "preco": 450.0, "quantidade": 2.0, "total_brl": 900.0, "timestamp": "09:00"},
        {"tipo": "VENDA", "preco": 470.0, "quantidade": 2.0, "total_brl": 940.0,
         "lucro_brl": 40.0, "lucro_pct": 4.4, "timestamp": "15:00"},
    ])
    response = client.get("/stats/mes?mes=2026-03", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["total_operacoes"] == 2
    assert data["lucro_total_brl"] == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# GET /operacoes
# ---------------------------------------------------------------------------

def test_operacoes_retorna_lista(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DIR", str(tmp_path / "stats"))
    _criar_stats(tmp_path, "2026-03-28", [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "timestamp": "09:00"},
        {"tipo": "VENDA", "preco": 460.0, "quantidade": 2.0, "total_brl": 920.0,
         "lucro_brl": 40.0, "lucro_pct": 4.5, "timestamp": "15:00"},
    ])
    response = client.get("/operacoes?data=2026-03-28", headers=AUTH_HEADER)
    assert response.status_code == 200
    ops = response.json()
    assert len(ops) == 2
    assert ops[0]["tipo"] == "COMPRA"
    assert ops[1]["tipo"] == "VENDA"


def test_operacoes_sem_dados_retorna_lista_vazia(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DIR", str(tmp_path / "stats"))
    response = client.get("/operacoes?data=2099-01-01", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /reserva
# ---------------------------------------------------------------------------

def test_reserva_retorna_estado(client, tmp_path, monkeypatch):
    monkeypatch.setenv("RESERVA_FILE", str(tmp_path / "reserva.json"))
    arquivo = tmp_path / "reserva.json"
    arquivo.write_text(json.dumps({
        "lucro_acumulado_brl": 22.50,
        "reserva_usdc": 4.83,
        "historico_conversoes": [],
    }))
    response = client.get("/reserva", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["lucro_acumulado_brl"] == pytest.approx(22.50)
    assert data["reserva_usdc"] == pytest.approx(4.83)


def test_reserva_sem_arquivo_retorna_zerado(client, tmp_path, monkeypatch):
    monkeypatch.setenv("RESERVA_FILE", str(tmp_path / "nao_existe.json"))
    response = client.get("/reserva", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["lucro_acumulado_brl"] == 0.0
    assert data["reserva_usdc"] == 0.0


# ---------------------------------------------------------------------------
# GET /fiscal/csv
# ---------------------------------------------------------------------------

def test_fiscal_csv_retorna_arquivo(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STATS_DIR", str(tmp_path / "stats"))
    _criar_stats(tmp_path, "2026-03-28", [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "timestamp": "09:00"},
        {"tipo": "VENDA", "preco": 460.0, "quantidade": 2.0, "total_brl": 920.0,
         "lucro_brl": 40.0, "lucro_pct": 4.5, "timestamp": "15:00"},
    ])
    response = client.get("/fiscal/csv?mes=2026-03", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "COMPRA" in response.text
    assert "VENDA" in response.text

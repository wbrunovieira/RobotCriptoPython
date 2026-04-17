"""Testes da lógica de reserva/isolamento do Bot Meme."""
import json
import os
import pytest
from unittest.mock import patch

import bots.meme.robo as robo_mod
from bots.meme.robo import (
    _carregar_reserva,
    _salvar_reserva,
    _reserva_isolada_usdt,
    _verificar_reserva_usdt,
    _saldo_para_bot,
    _saldo_para_bot_com_posicao,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_files(tmp_path, monkeypatch):
    """Redireciona RESERVA_FILE e APORTES_FILE para tmp_path."""
    reserva = str(tmp_path / "reserva_meme.json")
    aportes = str(tmp_path / "aportes.json")
    monkeypatch.setattr(robo_mod, "RESERVA_FILE", reserva)
    monkeypatch.setattr(robo_mod, "APORTES_FILE", aportes)
    return reserva, aportes


@pytest.fixture(autouse=True)
def silence_whatsapp(monkeypatch):
    monkeypatch.setattr(robo_mod, "enviar_whatsapp", lambda msg: None)


def _write_aportes(tmp_path, confirmados):
    path = str(tmp_path / "aportes.json")
    with open(path, "w") as f:
        json.dump({"confirmados": confirmados, "rejeitados": []}, f)


# ---------------------------------------------------------------------------
# _carregar_reserva — campos padrão e backward-compat
# ---------------------------------------------------------------------------

def test_carregar_reserva_campos_padrao(tmp_path):
    reserva = _carregar_reserva()
    assert reserva["pnl_liquido_pendente_usdt"] == 0.0
    assert reserva["reserva_isolada_usdt"] == 0.0
    assert reserva["capital_reinvestido_usdt"] == 0.0
    assert reserva["historico"] == []


def test_carregar_reserva_compat_formato_antigo(tmp_path, monkeypatch):
    """Arquivo no formato antigo (pnl_total_usdt) deve ser lido sem erro."""
    reserva_path = str(tmp_path / "reserva_meme.json")
    monkeypatch.setattr(robo_mod, "RESERVA_FILE", reserva_path)
    with open(reserva_path, "w") as f:
        json.dump({"pnl_total_usdt": 9.48, "entradas": []}, f)

    reserva = _carregar_reserva()
    assert reserva["pnl_liquido_pendente_usdt"] == 0.0
    assert reserva["reserva_isolada_usdt"] == 0.0


# ---------------------------------------------------------------------------
# _reserva_isolada_usdt
# ---------------------------------------------------------------------------

def test_reserva_isolada_zero_sem_arquivo():
    assert _reserva_isolada_usdt() == 0.0


def test_reserva_isolada_retorna_valor_salvo():
    dados = {
        "pnl_liquido_pendente_usdt": 0.0,
        "reserva_isolada_usdt": 5.5,
        "capital_reinvestido_usdt": 5.5,
        "historico": [],
    }
    _salvar_reserva(dados)
    assert _reserva_isolada_usdt() == pytest.approx(5.5)


# ---------------------------------------------------------------------------
# _verificar_reserva_usdt — sem split (condições não atendidas)
# ---------------------------------------------------------------------------

def test_sem_split_pnl_abaixo_minimo(tmp_path):
    """P&L pendente < $3 — nada acontece."""
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 118.79, "fonte": "manual"}])
    _verificar_reserva_usdt(lucro_usdt=2.0, saldo_pos_venda=120.0, timestamp="2026-04-17 10:00:00")

    reserva = _carregar_reserva()
    assert reserva["pnl_liquido_pendente_usdt"] == pytest.approx(2.0)
    assert reserva["reserva_isolada_usdt"] == 0.0


def test_sem_split_portfolio_abaixo_do_investido(tmp_path):
    """Portfolio ainda não recuperou o investido."""
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 118.79, "fonte": "manual"}])
    _verificar_reserva_usdt(lucro_usdt=5.0, saldo_pos_venda=113.82, timestamp="2026-04-17 10:00:00")

    reserva = _carregar_reserva()
    assert reserva["pnl_liquido_pendente_usdt"] == pytest.approx(5.0)
    assert reserva["reserva_isolada_usdt"] == 0.0


def test_split_portfolio_igual_ao_investido(tmp_path):
    """Portfolio igual ao investido já permite o split (capital não está em perda)."""
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])
    _verificar_reserva_usdt(lucro_usdt=5.0, saldo_pos_venda=100.0, timestamp="2026-04-17 10:00:00")

    reserva = _carregar_reserva()
    assert reserva["reserva_isolada_usdt"] == pytest.approx(2.5)
    assert reserva["capital_reinvestido_usdt"] == pytest.approx(2.5)


def test_sem_split_lucro_negativo_acumula_pendente(tmp_path):
    """Prejuízo acumula no pnl_pendente quando o primeiro trade não disparou o split."""
    # saldo_pos_venda=90 < total_investido=100 → primeiro trade não dispara split
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])
    _verificar_reserva_usdt(lucro_usdt=5.0, saldo_pos_venda=90.0, timestamp="2026-04-17 10:00:00")
    _verificar_reserva_usdt(lucro_usdt=-3.0, saldo_pos_venda=88.0, timestamp="2026-04-18 10:00:00")

    reserva = _carregar_reserva()
    assert reserva["pnl_liquido_pendente_usdt"] == pytest.approx(2.0)
    assert reserva["reserva_isolada_usdt"] == 0.0


# ---------------------------------------------------------------------------
# _verificar_reserva_usdt — com split (condições atendidas)
# ---------------------------------------------------------------------------

def test_split_50_50_quando_condicoes_atendidas(tmp_path):
    """Portfolio > investido E pnl >= $3 → split 50/50."""
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])
    _verificar_reserva_usdt(lucro_usdt=10.0, saldo_pos_venda=110.0, timestamp="2026-04-17 10:00:00")

    reserva = _carregar_reserva()
    assert reserva["reserva_isolada_usdt"] == pytest.approx(5.0)
    assert reserva["capital_reinvestido_usdt"] == pytest.approx(5.0)
    assert reserva["pnl_liquido_pendente_usdt"] == 0.0


def test_split_adiciona_aporte_reinvestido(tmp_path):
    """A metade reinvestida vira aporte confirmado com fonte lucro_reinvestido."""
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])
    _verificar_reserva_usdt(lucro_usdt=10.0, saldo_pos_venda=110.0, timestamp="2026-04-17 10:00:00")

    aportes_path = robo_mod.APORTES_FILE
    with open(aportes_path) as f:
        dados = json.load(f)
    reinvests = [a for a in dados["confirmados"] if a.get("fonte") == "lucro_reinvestido"]
    assert len(reinvests) == 1
    assert reinvests[0]["valor_usdt"] == pytest.approx(5.0)
    assert reinvests[0]["data"] == "2026-04-17"


def test_split_acumula_multiplas_vendas(tmp_path):
    """Dois trades com lucro, cada um acima do threshold, geram dois splits."""
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])

    _verificar_reserva_usdt(lucro_usdt=6.0, saldo_pos_venda=106.0, timestamp="2026-04-15 10:00:00")
    _verificar_reserva_usdt(lucro_usdt=8.0, saldo_pos_venda=114.0, timestamp="2026-04-17 10:00:00")

    reserva = _carregar_reserva()
    # Primeiro split: 6.0 → 3.0 + 3.0 (aporte vira 103.0)
    # Segundo split: 8.0 → 4.0 + 4.0
    assert reserva["reserva_isolada_usdt"] == pytest.approx(7.0)
    assert reserva["capital_reinvestido_usdt"] == pytest.approx(7.0)
    assert len(reserva["historico"]) == 2


def test_split_zera_pnl_e_nao_carrega_proximo_trade(tmp_path):
    """Após o split, o pnl_pendente zera e o próximo trade começa do zero."""
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])
    _verificar_reserva_usdt(lucro_usdt=6.0, saldo_pos_venda=106.0, timestamp="2026-04-15 10:00:00")

    # Próximo trade com prejuízo pequeno — não deve herdar o pnl anterior
    _verificar_reserva_usdt(lucro_usdt=-1.0, saldo_pos_venda=108.0, timestamp="2026-04-16 10:00:00")

    reserva = _carregar_reserva()
    assert reserva["pnl_liquido_pendente_usdt"] == pytest.approx(-1.0)


def test_split_historico_registrado(tmp_path):
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])
    _verificar_reserva_usdt(lucro_usdt=10.0, saldo_pos_venda=110.0, timestamp="2026-04-17 10:00:00")

    reserva = _carregar_reserva()
    assert len(reserva["historico"]) == 1
    h = reserva["historico"][0]
    assert h["timestamp"] == "2026-04-17 10:00:00"
    assert h["pnl_processado"] == pytest.approx(10.0)
    assert h["reserva_usdt"] == pytest.approx(5.0)
    assert h["reinvestido_usdt"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# _saldo_para_bot — desconta reserva do capital máximo
# ---------------------------------------------------------------------------

def test_saldo_para_bot_sem_reserva(tmp_path):
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])
    resultado = _saldo_para_bot(saldo_usdt=120.0)
    assert resultado == pytest.approx(100.0)


def test_saldo_para_bot_com_reserva_reduz_capital(tmp_path):
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])
    _salvar_reserva({
        "pnl_liquido_pendente_usdt": 0.0,
        "reserva_isolada_usdt": 5.0,
        "capital_reinvestido_usdt": 5.0,
        "historico": [],
    })
    # aportes = 100, reserva = 5 → capital_max = 95
    resultado = _saldo_para_bot(saldo_usdt=120.0)
    assert resultado == pytest.approx(95.0)


def test_saldo_para_bot_capital_nao_fica_negativo(tmp_path):
    """Reserva maior que aportes → capital = 0, nunca negativo."""
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 10.0, "fonte": "manual"}])
    _salvar_reserva({
        "pnl_liquido_pendente_usdt": 0.0,
        "reserva_isolada_usdt": 20.0,
        "capital_reinvestido_usdt": 20.0,
        "historico": [],
    })
    resultado = _saldo_para_bot(saldo_usdt=120.0)
    assert resultado == 0.0


def test_saldo_para_bot_com_posicao_desconta_reserva_e_posicao(tmp_path):
    _write_aportes(tmp_path, [{"data": "2026-04-01", "valor_usdt": 100.0, "fonte": "manual"}])
    _salvar_reserva({
        "pnl_liquido_pendente_usdt": 0.0,
        "reserva_isolada_usdt": 5.0,
        "capital_reinvestido_usdt": 5.0,
        "historico": [],
    })
    # capital_max = 95, em posição = 80 → disponível = 15
    resultado = _saldo_para_bot_com_posicao(saldo_usdt=120.0, capital_em_pos=80.0)
    assert resultado == pytest.approx(15.0)

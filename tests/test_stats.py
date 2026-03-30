import pytest
import json
from datetime import date
from stats import (
    iniciar_stats_do_dia,
    registrar_compra,
    registrar_venda,
    carregar_stats_do_dia,
    calcular_resumo,
)


def test_iniciar_stats_cria_arquivo(tmp_path):
    hoje = date.today().strftime("%Y-%m-%d")
    arquivo = str(tmp_path / "stats" / f"{hoje}.json")
    stats = iniciar_stats_do_dia(saldo_inicial_brl=1000.0, arquivo=arquivo)
    assert stats["data"] == hoje
    assert stats["saldo_inicial_brl"] == 1000.0
    assert stats["operacoes"] == []
    assert "parametros" in stats


def test_iniciar_stats_nao_sobrescreve_se_ja_existe(tmp_path):
    arquivo = str(tmp_path / "2026-03-28.json")
    iniciar_stats_do_dia(saldo_inicial_brl=1000.0, arquivo=arquivo)
    # Segunda chamada não deve sobrescrever o saldo inicial
    stats = iniciar_stats_do_dia(saldo_inicial_brl=999.0, arquivo=arquivo)
    assert stats["saldo_inicial_brl"] == 1000.0


def test_registrar_compra(tmp_path):
    arquivo = str(tmp_path / "2026-03-28.json")
    iniciar_stats_do_dia(1000.0, arquivo=arquivo)
    stats = registrar_compra(
        preco=440.0,
        quantidade=2.045,
        total_brl=900.0,
        timestamp="2026-03-28 09:00:00",
        arquivo=arquivo,
    )
    assert len(stats["operacoes"]) == 1
    op = stats["operacoes"][0]
    assert op["tipo"] == "COMPRA"
    assert op["preco"] == 440.0
    assert op["quantidade"] == 2.045
    assert op["total_brl"] == 900.0
    assert op["timestamp"] == "2026-03-28 09:00:00"


def test_registrar_venda(tmp_path):
    arquivo = str(tmp_path / "2026-03-28.json")
    iniciar_stats_do_dia(1000.0, arquivo=arquivo)
    registrar_compra(440.0, 2.045, 900.0, "2026-03-28 09:00:00", arquivo=arquivo)
    stats = registrar_venda(
        preco=454.0,
        quantidade=2.045,
        total_brl=928.43,
        preco_entrada=440.0,
        timestamp="2026-03-28 15:23:00",
        arquivo=arquivo,
    )
    assert len(stats["operacoes"]) == 2
    op = stats["operacoes"][1]
    assert op["tipo"] == "VENDA"
    assert op["preco"] == 454.0
    assert op["lucro_brl"] == pytest.approx(28.43, abs=0.01)
    assert op["lucro_pct"] == pytest.approx(3.15, abs=0.1)


def test_registrar_venda_com_prejuizo(tmp_path):
    arquivo = str(tmp_path / "2026-03-28.json")
    iniciar_stats_do_dia(1000.0, arquivo=arquivo)
    registrar_compra(440.0, 2.045, 900.0, "2026-03-28 09:00:00", arquivo=arquivo)
    stats = registrar_venda(
        preco=418.0,
        quantidade=2.045,
        total_brl=854.81,
        preco_entrada=440.0,
        timestamp="2026-03-28 10:00:00",
        arquivo=arquivo,
    )
    op = stats["operacoes"][1]
    assert op["lucro_brl"] < 0
    assert op["lucro_pct"] < 0


def test_carregar_stats_do_dia(tmp_path):
    arquivo = str(tmp_path / "2026-03-28.json")
    iniciar_stats_do_dia(1000.0, arquivo=arquivo)
    registrar_compra(440.0, 2.045, 900.0, "2026-03-28 09:00:00", arquivo=arquivo)
    stats = carregar_stats_do_dia(arquivo=arquivo)
    assert stats["saldo_inicial_brl"] == 1000.0
    assert len(stats["operacoes"]) == 1


def test_carregar_stats_inexistente_retorna_none(tmp_path):
    arquivo = str(tmp_path / "nao_existe.json")
    assert carregar_stats_do_dia(arquivo=arquivo) is None


def test_calcular_resumo_com_lucro(tmp_path):
    arquivo = str(tmp_path / "2026-03-28.json")
    iniciar_stats_do_dia(1000.0, arquivo=arquivo)
    registrar_compra(440.0, 2.045, 900.0, "2026-03-28 09:00:00", arquivo=arquivo)
    registrar_venda(454.0, 2.045, 928.43, 440.0, "2026-03-28 15:00:00", arquivo=arquivo)
    stats = carregar_stats_do_dia(arquivo=arquivo)
    resumo = calcular_resumo(stats)
    assert resumo["total_operacoes"] == 1  # 1 ciclo completo (compra+venda)
    assert resumo["operacoes_lucrativas"] == 1
    assert resumo["lucro_total_brl"] == pytest.approx(28.43, abs=0.01)
    assert resumo["maior_ganho"] == pytest.approx(28.43, abs=0.01)
    assert resumo["maior_perda"] == 0.0
    assert resumo["taxa_acerto_pct"] == 100.0


def test_calcular_resumo_misto(tmp_path):
    arquivo = str(tmp_path / "2026-03-28.json")
    iniciar_stats_do_dia(1000.0, arquivo=arquivo)
    # Ciclo 1: lucro
    registrar_compra(440.0, 2.045, 900.0, "09:00:00", arquivo=arquivo)
    registrar_venda(454.0, 2.045, 928.43, 440.0, "15:00:00", arquivo=arquivo)
    # Ciclo 2: prejuízo
    registrar_compra(450.0, 2.0, 900.0, "16:00:00", arquivo=arquivo)
    registrar_venda(418.0, 2.0, 836.0, 450.0, "17:00:00", arquivo=arquivo)
    stats = carregar_stats_do_dia(arquivo=arquivo)
    resumo = calcular_resumo(stats)
    assert resumo["total_operacoes"] == 2
    assert resumo["operacoes_lucrativas"] == 1
    assert resumo["taxa_acerto_pct"] == 50.0
    assert resumo["maior_ganho"] == pytest.approx(28.43, abs=0.01)
    assert resumo["maior_perda"] < 0


def test_registrar_venda_cross_par_nao_cruza_custo(tmp_path):
    """Venda de SOLBRL não deve usar custo de XRPBRL comprado no mesmo dia."""
    arquivo = str(tmp_path / "2026-03-29.json")
    iniciar_stats_do_dia(300.0, arquivo=arquivo)

    # Compra e venda de XRP no mesmo dia
    registrar_compra(7.012, 24.0, 168.29, "06:54", arquivo=arquivo, par="XRPBRL")
    registrar_venda(7.029, 24.0, 168.70, 7.012, "08:13", arquivo=arquivo, par="XRPBRL")
    registrar_compra(7.034, 23.9, 168.11, "08:56", arquivo=arquivo, par="XRPBRL")

    # Venda de SOL — compra foi em outro dia, fallback usa preco_entrada × quantidade
    stats = registrar_venda(
        preco=416.2, quantidade=0.207, total_brl=86.15,
        preco_entrada=437.5,
        timestamp="19:50", arquivo=arquivo, par="SOLBRL",
    )

    venda_sol = next(op for op in stats["operacoes"] if op.get("par") == "SOLBRL" and op["tipo"] == "VENDA")
    # custo correto = 437.5 * 0.207 = 90.5625
    assert venda_sol["lucro_brl"] == pytest.approx(-4.41, abs=0.05)
    assert venda_sol["lucro_pct"] == pytest.approx(-4.87, abs=0.1)


def test_calcular_resumo_sem_operacoes(tmp_path):
    arquivo = str(tmp_path / "2026-03-28.json")
    iniciar_stats_do_dia(1000.0, arquivo=arquivo)
    stats = carregar_stats_do_dia(arquivo=arquivo)
    resumo = calcular_resumo(stats)
    assert resumo["total_operacoes"] == 0
    assert resumo["lucro_total_brl"] == 0.0
    assert resumo["taxa_acerto_pct"] == 0.0

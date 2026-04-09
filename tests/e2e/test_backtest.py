"""Testes E2E de backtesting com dados reais da Binance.

Estes testes:
  1. Buscam candles reais (Binance API)
  2. Simulam o bot candle a candle com a estratégia real
  3. Validam a integridade dos resultados (sem assertivas de lucro — o mercado decide)
  4. Comparam COM e SEM filtro BTC para medir o impacto

Para rodar:
    pytest tests/e2e/ -v -s
    pytest tests/e2e/ -v -s -k "solbrl"
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from analysis.backtest_real import (
    buscar_candles,
    simular_par,
    calcular_metricas,
    ConfigBacktest,
)
from pares import listar_pares

PARES_BRL = [p["simbolo"] for p in listar_pares()]
DIAS = 30


# ─── Fixtures locais ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def dados_btc(binance_cliente):
    return buscar_candles(binance_cliente, "BTCBRL", "4h", DIAS)


@pytest.fixture(scope="module")
def dados_por_par(binance_cliente):
    """Busca os candles 1h de todos os pares BRL uma única vez."""
    return {
        simbolo: buscar_candles(binance_cliente, simbolo, "1h", DIAS)
        for simbolo in PARES_BRL
    }


# ─── Testes de sanidade dos candles ─────────────────────────────────────────

@pytest.mark.e2e
def test_candles_btc_tem_dados_suficientes(dados_btc):
    """BTC 4h deve ter ao menos 50 candles para a MA50 funcionar."""
    assert len(dados_btc) >= 50, f"Apenas {len(dados_btc)} candles BTC — insuficiente para MA50."


@pytest.mark.e2e
@pytest.mark.parametrize("simbolo", PARES_BRL)
def test_candles_par_tem_dados_suficientes(simbolo, dados_por_par):
    """Cada par BRL deve ter ao menos 60 candles 1h."""
    dados = dados_por_par[simbolo]
    assert len(dados) >= 60, f"{simbolo}: apenas {len(dados)} candles."


@pytest.mark.e2e
@pytest.mark.parametrize("simbolo", PARES_BRL)
def test_candles_sem_valores_nulos(simbolo, dados_por_par):
    dados = dados_por_par[simbolo]
    assert dados[["fechamento", "maxima", "minima"]].isnull().sum().sum() == 0


@pytest.mark.e2e
@pytest.mark.parametrize("simbolo", PARES_BRL)
def test_maxima_sempre_maior_que_minima(simbolo, dados_por_par):
    dados = dados_por_par[simbolo]
    assert (dados["maxima"] >= dados["minima"]).all()


# ─── Testes de integridade da simulação ─────────────────────────────────────

@pytest.mark.e2e
@pytest.mark.parametrize("simbolo", PARES_BRL)
def test_simulacao_nao_gera_capital_negativo(simbolo, dados_por_par, dados_btc):
    """O capital nunca deve ficar negativo durante a simulação."""
    cfg = ConfigBacktest()
    resultado = simular_par(simbolo, dados_por_par[simbolo], dados_btc, cfg)
    assert resultado["capital_final"] > 0
    assert all(v >= 0 for v in resultado["equity_curve"])


@pytest.mark.e2e
@pytest.mark.parametrize("simbolo", PARES_BRL)
def test_operacoes_alternadas_compra_venda(simbolo, dados_por_par, dados_btc):
    """Não pode haver duas compras seguidas sem uma venda no meio."""
    cfg = ConfigBacktest()
    resultado = simular_par(simbolo, dados_por_par[simbolo], dados_btc, cfg)
    ops = resultado["operacoes"]
    ultimo_tipo = None
    for op in ops:
        if op["tipo"] == "COMPRA":
            assert ultimo_tipo != "COMPRA", f"{simbolo}: duas compras seguidas — lógica de posição quebrada."
        ultimo_tipo = op["tipo"]


@pytest.mark.e2e
@pytest.mark.parametrize("simbolo", PARES_BRL)
def test_todas_vendas_tem_lucro_calculado(simbolo, dados_por_par, dados_btc):
    """Toda venda deve ter campo lucro_brl calculado."""
    cfg = ConfigBacktest()
    resultado = simular_par(simbolo, dados_por_par[simbolo], dados_btc, cfg)
    vendas = [op for op in resultado["operacoes"] if op["tipo"] == "VENDA"]
    for v in vendas:
        assert "lucro_brl" in v, f"{simbolo}: venda sem lucro_brl: {v}"


@pytest.mark.e2e
@pytest.mark.parametrize("simbolo", PARES_BRL)
def test_metricas_retornam_estrutura_completa(simbolo, dados_por_par, dados_btc):
    cfg = ConfigBacktest()
    resultado = simular_par(simbolo, dados_por_par[simbolo], dados_btc, cfg)
    m = calcular_metricas(resultado)

    campos_obrigatorios = [
        "simbolo", "capital_inicial", "capital_final", "retorno_pct",
        "total_operacoes", "taxa_acerto_pct", "lucro_total_brl",
        "maior_ganho_brl", "maior_perda_brl", "drawdown_maximo_pct",
        "saidas_por_motivo",
    ]
    for campo in campos_obrigatorios:
        assert campo in m, f"Campo ausente nas métricas: {campo}"


# ─── Testes de comparação COM vs SEM filtro BTC ─────────────────────────────

@pytest.mark.e2e
@pytest.mark.parametrize("simbolo", PARES_BRL)
def test_comparar_com_e_sem_filtro_btc(simbolo, dados_por_par, dados_btc, capsys):
    """Roda a simulação com e sem o filtro BTC e imprime o comparativo."""
    dados = dados_por_par[simbolo]

    cfg_com = ConfigBacktest(filtro_btc=True)
    cfg_sem = ConfigBacktest(filtro_btc=False)

    m_com = calcular_metricas(simular_par(simbolo, dados, dados_btc, cfg_com))
    m_sem = calcular_metricas(simular_par(simbolo, dados, dados_btc, cfg_sem))

    diff = m_com["capital_final"] - m_sem["capital_final"]

    print(f"\n{'─'*50}")
    print(f"  {simbolo} — {DIAS} dias")
    print(f"  {'':28} {'COM BTC':>10} {'SEM BTC':>10}")
    print(f"  {'─'*28} {'─'*10} {'─'*10}")
    print(f"  {'Retorno (%)':<28} {m_com['retorno_pct']:>10} {m_sem['retorno_pct']:>10}")
    print(f"  {'Capital final (R$)':<28} {m_com['capital_final']:>10.2f} {m_sem['capital_final']:>10.2f}")
    print(f"  {'Operações':<28} {m_com['total_operacoes']:>10} {m_sem['total_operacoes']:>10}")
    print(f"  {'Acerto (%)':<28} {m_com['taxa_acerto_pct']:>10} {m_sem['taxa_acerto_pct']:>10}")
    print(f"  {'Drawdown máx (%)':<28} {m_com['drawdown_maximo_pct']:>10} {m_sem['drawdown_maximo_pct']:>10}")
    print(f"  Impacto filtro BTC: {'+'if diff>=0 else ''}R$ {diff:.2f}")

    # Sem assertiva de lucro — o mercado decide. Validamos apenas a integridade.
    assert m_com["capital_final"] > 0
    assert m_sem["capital_final"] > 0


# ─── Teste de resumo consolidado ────────────────────────────────────────────

@pytest.mark.e2e
def test_resumo_todos_pares(dados_por_par, dados_btc):
    """Roda backtest em todos os pares e imprime um resumo consolidado."""
    cfg = ConfigBacktest(filtro_btc=True)
    resultados = []
    for simbolo in PARES_BRL:
        r = simular_par(simbolo, dados_por_par[simbolo], dados_btc, cfg)
        resultados.append(calcular_metricas(r))

    total_inicial = sum(m["capital_inicial"] for m in resultados)
    total_final = sum(m["capital_final"] for m in resultados)
    retorno = (total_final - total_inicial) / total_inicial * 100
    total_ops = sum(m["total_operacoes"] for m in resultados)
    total_lucr = sum(m["operacoes_lucrativas"] for m in resultados)
    acerto = total_lucr / total_ops * 100 if total_ops else 0

    print(f"\n{'═'*52}")
    print(f"  RESUMO CONSOLIDADO — {DIAS} dias — COM filtro BTC")
    print(f"{'═'*52}")
    for m in resultados:
        sinal = "+" if m["retorno_pct"] >= 0 else ""
        print(
            f"  {m['simbolo']:<12} R${m['capital_final']:>8.2f}  "
            f"{sinal}{m['retorno_pct']:>6.2f}%  "
            f"ops={m['total_operacoes']}  acerto={m['taxa_acerto_pct']}%"
        )
    print(f"{'─'*52}")
    print(f"  TOTAL        R${total_final:>8.2f}  {'+' if retorno>=0 else ''}{retorno:.2f}%  ops={total_ops}  acerto={acerto:.1f}%")
    print(f"{'═'*52}")

    assert total_final > 0

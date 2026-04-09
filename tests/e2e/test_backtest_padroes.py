"""Testes E2E — comparativo de resultados COM e SEM padrões gráficos.

Roda o backtest em 3 configurações e compara resultados:
  A) Estratégia atual (MA crossover + filtro BTC)
  B) Estratégia atual + padrões gráficos (cunha + bandeira)
  C) Somente padrões (sem MA crossover) — para isolar o impacto

Para rodar:
    pytest tests/e2e/test_backtest_padroes.py -v -s
"""
import os
import sys

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


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def dados_btc(binance_cliente):
    return buscar_candles(binance_cliente, "BTCBRL", "4h", DIAS)


@pytest.fixture(scope="module")
def dados_por_par(binance_cliente):
    return {
        simbolo: buscar_candles(binance_cliente, simbolo, "1h", DIAS)
        for simbolo in PARES_BRL
    }


# ─── Testes de comparativo por par ───────────────────────────────────────────

@pytest.mark.e2e
@pytest.mark.parametrize("simbolo", PARES_BRL)
def test_comparar_estrategias_por_par(simbolo, dados_por_par, dados_btc):
    """Compara as 3 configurações para cada par e imprime o resultado."""
    dados = dados_por_par[simbolo]

    cfg_a = ConfigBacktest(filtro_btc=True, usar_padroes=False)
    cfg_b = ConfigBacktest(filtro_btc=True, usar_padroes=True)

    m_a = calcular_metricas(simular_par(simbolo, dados, dados_btc, cfg_a))
    m_b = calcular_metricas(simular_par(simbolo, dados, dados_btc, cfg_b))

    diff = m_b["capital_final"] - m_a["capital_final"]
    ops_extras = m_b["total_operacoes"] - m_a["total_operacoes"]

    print(f"\n{'═'*62}")
    print(f"  {simbolo} — {DIAS} dias")
    print(f"{'═'*62}")
    print(f"  {'Métrica':<30} {'A: atual':>10} {'B: +padrões':>10}")
    print(f"  {'─'*30} {'─'*10} {'─'*10}")

    campos = [
        ("Retorno (%)",         "retorno_pct",        lambda v: f"{v:+.2f}%"),
        ("Capital final (R$)",  "capital_final",       lambda v: f"R${v:.2f}"),
        ("Operações",           "total_operacoes",     str),
        ("Acerto (%)",          "taxa_acerto_pct",     lambda v: f"{v}%"),
        ("Lucro total (R$)",    "lucro_total_brl",     lambda v: f"R${v:+.2f}"),
        ("Drawdown máx (%)",    "drawdown_maximo_pct", lambda v: f"{v}%"),
    ]
    for label, key, fmt in campos:
        print(f"  {label:<30} {fmt(m_a[key]):>10} {fmt(m_b[key]):>10}")

    print(f"  {'─'*30} {'─'*10} {'─'*10}")
    print(f"  {'Entradas por padrão':<30} {'—':>10} {m_b['entradas_por_padrao']:>10}")
    print(f"  {'Lucro entradas padrão (R$)':<30} {'—':>10} {m_b['lucro_entradas_padrao']:>+10.2f}")
    print(f"  {'Lucro entradas MA (R$)':<30} {m_a['lucro_entradas_ma']:>+10.2f} {m_b['lucro_entradas_ma']:>+10.2f}")

    sinal_diff = "+" if diff >= 0 else ""
    print(f"\n  Impacto dos padrões: {sinal_diff}R$ {diff:.2f} | {ops_extras:+d} operações extras")
    if diff > 0:
        print("  → Padrões MELHORARAM o resultado neste período.")
    elif diff < 0:
        print("  → Padrões PIORARAM o resultado (entradas ruins).")
    else:
        print("  → Padrões não alteraram o resultado.")

    # Integridade
    assert m_a["capital_final"] > 0
    assert m_b["capital_final"] > 0
    assert m_b["total_operacoes"] >= m_a["total_operacoes"]


# ─── Resumo consolidado ───────────────────────────────────────────────────────

@pytest.mark.e2e
def test_resumo_consolidado_padroes(dados_por_par, dados_btc):
    """Resumo de todos os pares com e sem padrões."""
    resultados_a = []
    resultados_b = []

    for simbolo in PARES_BRL:
        dados = dados_por_par[simbolo]
        cfg_a = ConfigBacktest(filtro_btc=True, usar_padroes=False)
        cfg_b = ConfigBacktest(filtro_btc=True, usar_padroes=True)
        resultados_a.append(calcular_metricas(simular_par(simbolo, dados, dados_btc, cfg_a)))
        resultados_b.append(calcular_metricas(simular_par(simbolo, dados, dados_btc, cfg_b)))

    def totais(rs):
        ci = sum(r["capital_inicial"] for r in rs)
        cf = sum(r["capital_final"] for r in rs)
        ops = sum(r["total_operacoes"] for r in rs)
        lucr = sum(r["operacoes_lucrativas"] for r in rs)
        return ci, cf, (cf - ci) / ci * 100, ops, (lucr / ops * 100 if ops else 0)

    ci_a, cf_a, ret_a, ops_a, ac_a = totais(resultados_a)
    ci_b, cf_b, ret_b, ops_b, ac_b = totais(resultados_b)
    total_entradas_padrao = sum(r["entradas_por_padrao"] for r in resultados_b)
    total_lucro_padrao = sum(r["lucro_entradas_padrao"] for r in resultados_b)

    print(f"\n{'═'*62}")
    print(f"  RESUMO CONSOLIDADO — {DIAS} dias — todos os pares")
    print(f"{'═'*62}")
    print(f"  {'Métrica':<30} {'A: atual':>12} {'B: +padrões':>12}")
    print(f"  {'─'*30} {'─'*12} {'─'*12}")
    print(f"  {'Capital final total (R$)':<30} {cf_a:>12.2f} {cf_b:>12.2f}")
    print(f"  {'Retorno consolidado (%)':<30} {ret_a:>+11.2f}% {ret_b:>+11.2f}%")
    print(f"  {'Total de operações':<30} {ops_a:>12} {ops_b:>12}")
    print(f"  {'Taxa de acerto geral (%)':<30} {ac_a:>11.1f}% {ac_b:>11.1f}%")
    print(f"  {'─'*30} {'─'*12} {'─'*12}")
    print(f"  {'Entradas via padrão':<30} {'—':>12} {total_entradas_padrao:>12}")
    print(f"  {'Lucro das entradas padrão (R$)':<30} {'—':>12} {total_lucro_padrao:>+12.2f}")

    diff_total = cf_b - cf_a
    print(f"\n  Impacto total dos padrões: {'+' if diff_total >= 0 else ''}R$ {diff_total:.2f}")
    if diff_total > 0:
        print("  → Os padrões gráficos GERARAM VALOR neste período.")
    elif diff_total < 0:
        print("  → Os padrões introduziram mais entradas ruins do que boas.")
    else:
        print("  → Os padrões não tiveram impacto líquido.")
    print(f"{'═'*62}\n")

    assert cf_a > 0
    assert cf_b > 0

"""CLI para rodar backtesting com dados reais da Binance.

Uso:
    python analysis/backtest_runner.py --dias 30
    python analysis/backtest_runner.py --par SOLBRL --dias 60
    python analysis/backtest_runner.py --dias 30 --sem-filtro-btc
    python analysis/backtest_runner.py --dias 30 --comparar
    python analysis/backtest_runner.py --dias 30 --salvar fixtures/

    --comparar: roda COM e SEM filtro BTC e exibe os dois resultados lado a lado
    --salvar:   salva os candles em JSON para uso nos testes E2E (sem chamada Binance)
"""
import argparse
import json
import logging
import os
import sys

import pandas as pd
from dotenv import load_dotenv

# Envia todos os logs para stderr para não poluir o relatório no stdout
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from infra.binance_client import criar_cliente_sincronizado
from analysis.backtest_real import (
    buscar_candles,
    buscar_candles_periodo,
    simular_par,
    calcular_metricas,
    ConfigBacktest,
)
from pares import listar_pares

PARES_BRL = [p["simbolo"] for p in listar_pares()]
SIMBOLO_BTC = "BTCBRL"
INTERVALO_PAR = "1h"
INTERVALO_BTC = "4h"


# ─── Formatação ─────────────────────────────────────────────────────────────

def _sinal(valor: float) -> str:
    return f"+{valor}" if valor >= 0 else str(valor)


def _linha(label: str, valor: str, largura: int = 28) -> str:
    return f"  {label:<{largura}} {valor}"


def imprimir_metricas(m: dict, titulo: str = "") -> None:
    sep = "─" * 52
    print(f"\n{sep}")
    if titulo:
        print(f"  {titulo}")
        print(sep)
    print(_linha("Par:", m["simbolo"]))
    print(_linha("Capital inicial:", f"R$ {m['capital_inicial']:.2f}"))
    print(_linha("Capital final:", f"R$ {m['capital_final']:.2f}"))
    print(_linha("Retorno:", f"{_sinal(m['retorno_pct'])}%"))
    print(_linha("Operações fechadas:", str(m["total_operacoes"])))
    print(_linha("Taxa de acerto:", f"{m['taxa_acerto_pct']}%"))
    print(_linha("Lucro total:", f"R$ {_sinal(m['lucro_total_brl'])}"))
    print(_linha("Maior ganho:", f"R$ {m['maior_ganho_brl']:.2f}"))
    print(_linha("Maior perda:", f"R$ {m['maior_perda_brl']:.2f}"))
    print(_linha("Drawdown máximo:", f"{m['drawdown_maximo_pct']}%"))
    if m["saidas_por_motivo"]:
        motivos = ", ".join(f"{k}={v}" for k, v in m["saidas_por_motivo"].items())
        print(_linha("Saídas por motivo:", motivos))
    print(sep)


def imprimir_comparativo(m_com: dict, m_sem: dict) -> None:
    sep = "═" * 60
    print(f"\n{sep}")
    print(f"  COMPARATIVO — COM filtro BTC  vs  SEM filtro BTC")
    print(f"  Par: {m_com['simbolo']}")
    print(sep)
    print(f"  {'Métrica':<28} {'COM BTC':>12} {'SEM BTC':>12}")
    print(f"  {'─'*28} {'─'*12} {'─'*12}")

    campos = [
        ("Retorno (%)", "retorno_pct", lambda v: f"{_sinal(v)}%"),
        ("Capital final (R$)", "capital_final", lambda v: f"R${v:.2f}"),
        ("Operações", "total_operacoes", str),
        ("Acerto (%)", "taxa_acerto_pct", lambda v: f"{v}%"),
        ("Lucro total (R$)", "lucro_total_brl", lambda v: f"R${_sinal(v)}"),
        ("Drawdown máx (%)", "drawdown_maximo_pct", lambda v: f"{v}%"),
    ]
    for label, key, fmt in campos:
        v_com = fmt(m_com[key])
        v_sem = fmt(m_sem[key])
        print(f"  {label:<28} {v_com:>12} {v_sem:>12}")
    print(sep)

    diff = m_com["capital_final"] - m_sem["capital_final"]
    sinal_diff = "+" if diff >= 0 else ""
    print(f"\n  Impacto do filtro BTC: {sinal_diff}R$ {diff:.2f} no capital final")
    if diff > 0:
        print("  → Filtro BTC AJUDOU a preservar capital neste período.")
    elif diff < 0:
        print("  → Filtro BTC BLOQUEOU entradas lucrativas neste período.")
    else:
        print("  → Filtro BTC não teve impacto neste período.")
    print()


def imprimir_comparativo_padroes(m_a: dict, m_b: dict) -> None:
    """Comparativo: A) estratégia atual  vs  B) estratégia + padrões gráficos."""
    sep = "═" * 62
    print(f"\n{sep}")
    print(f"  COMPARATIVO — Estratégia atual  vs  + Padrões gráficos")
    print(f"  Par: {m_a['simbolo']}")
    print(sep)
    print(f"  {'Métrica':<30} {'A: atual':>12} {'B: +padrões':>12}")
    print(f"  {'─'*30} {'─'*12} {'─'*12}")

    campos = [
        ("Retorno (%)",        "retorno_pct",        lambda v: f"{v:+.2f}%"),
        ("Capital final (R$)", "capital_final",       lambda v: f"R${v:.2f}"),
        ("Operações",          "total_operacoes",     str),
        ("Acerto (%)",         "taxa_acerto_pct",     lambda v: f"{v}%"),
        ("Lucro total (R$)",   "lucro_total_brl",     lambda v: f"R${v:+.2f}"),
        ("Drawdown máx (%)",   "drawdown_maximo_pct", lambda v: f"{v}%"),
    ]
    for label, key, fmt in campos:
        print(f"  {label:<30} {fmt(m_a[key]):>12} {fmt(m_b[key]):>12}")

    print(f"  {'─'*30} {'─'*12} {'─'*12}")
    print(f"  {'Entradas via padrão':<30} {'—':>12} {m_b['entradas_por_padrao']:>12}")
    print(f"  {'Lucro entradas padrão (R$)':<30} {'—':>12} {m_b['lucro_entradas_padrao']:>+12.2f}")

    diff = m_b["capital_final"] - m_a["capital_final"]
    print(f"\n  Impacto dos padrões: {'+' if diff >= 0 else ''}R$ {diff:.2f}")
    if diff > 0:
        print("  → Padrões MELHORARAM o resultado.")
    elif diff < 0:
        print("  → Padrões PIORARAM o resultado (entradas ruins).")
    else:
        print("  → Padrões não alteraram o resultado.")
    print()


def imprimir_resumo_geral(resultados: list[dict]) -> None:
    sep = "═" * 52
    print(f"\n{sep}")
    print("  RESUMO GERAL — TODOS OS PARES")
    print(sep)
    capital_total_inicial = sum(m["capital_inicial"] for m in resultados)
    capital_total_final = sum(m["capital_final"] for m in resultados)
    retorno_total = (capital_total_final - capital_total_inicial) / capital_total_inicial * 100
    total_ops = sum(m["total_operacoes"] for m in resultados)
    total_lucr = sum(m["operacoes_lucrativas"] for m in resultados)
    acerto_geral = total_lucr / total_ops * 100 if total_ops else 0

    print(_linha("Capital inicial total:", f"R$ {capital_total_inicial:.2f}"))
    print(_linha("Capital final total:", f"R$ {capital_total_final:.2f}"))
    print(_linha("Retorno consolidado:", f"{_sinal(round(retorno_total, 2))}%"))
    print(_linha("Total de operações:", str(total_ops)))
    print(_linha("Taxa de acerto geral:", f"{round(acerto_geral, 1)}%"))
    print(sep)


# ─── Runner principal ────────────────────────────────────────────────────────

def _buscar_dados(cliente, simbolo: str, intervalo: str, dias: int,
                  inicio: str | None, fim: str | None) -> pd.DataFrame:
    """Escolhe entre busca por dias recentes ou por período histórico."""
    if inicio and fim:
        return buscar_candles_periodo(cliente, simbolo, intervalo, inicio, fim)
    return buscar_candles(cliente, simbolo, intervalo, dias)


def run(
    pares: list[str],
    dias: int,
    comparar_btc: bool,
    comparar_padroes: bool,
    filtro_btc: bool,
    salvar: str | None,
    inicio: str | None,
    fim: str | None,
) -> None:
    api_key = os.getenv("KEY_BINANCE")
    secret_key = os.getenv("SECRET_BINANCE")
    if not api_key or not secret_key:
        print("ERRO: KEY_BINANCE e SECRET_BINANCE precisam estar no .env")
        sys.exit(1)

    cliente = criar_cliente_sincronizado(api_key, secret_key)
    periodo_label = f"{inicio} → {fim}" if inicio and fim else f"{dias} dias"

    print(f"\nBuscando BTCBRL 4h ({periodo_label})...")
    dados_btc = _buscar_dados(cliente, SIMBOLO_BTC, INTERVALO_BTC, dias, inicio, fim)
    print(f"  {len(dados_btc)} candles BTC obtidos.")

    if salvar:
        os.makedirs(salvar, exist_ok=True)
        btc_path = os.path.join(salvar, "BTCBRL_4h.json")
        dados_btc.to_json(btc_path, orient="records", date_format="iso")
        print(f"  BTC salvo em {btc_path}")

    todos_resultados = []

    for simbolo in pares:
        print(f"\nBuscando {simbolo} 1h ({periodo_label})...")
        dados = _buscar_dados(cliente, simbolo, INTERVALO_PAR, dias, inicio, fim)
        print(f"  {len(dados)} candles obtidos.")

        if salvar:
            par_path = os.path.join(salvar, f"{simbolo}_1h.json")
            dados.to_json(par_path, orient="records", date_format="iso")
            print(f"  {simbolo} salvo em {par_path}")

        cfg_a = ConfigBacktest(filtro_btc=filtro_btc, usar_padroes=False)
        m_a = calcular_metricas(simular_par(simbolo, dados, dados_btc, cfg_a))
        todos_resultados.append(m_a)

        if comparar_btc:
            cfg_sem_btc = ConfigBacktest(filtro_btc=False, usar_padroes=False)
            m_sem_btc = calcular_metricas(simular_par(simbolo, dados, dados_btc, cfg_sem_btc))
            imprimir_comparativo(m_a, m_sem_btc)
        elif comparar_padroes:
            cfg_b = ConfigBacktest(filtro_btc=filtro_btc, usar_padroes=True)
            m_b = calcular_metricas(simular_par(simbolo, dados, dados_btc, cfg_b))
            imprimir_comparativo_padroes(m_a, m_b)
        else:
            imprimir_metricas(m_a)

    if len(pares) > 1 and not (comparar_btc or comparar_padroes):
        imprimir_resumo_geral(todos_resultados)
    elif len(pares) > 1:
        # Resumo consolidado para comparativos
        ci = sum(m["capital_inicial"] for m in todos_resultados)
        cf = sum(m["capital_final"] for m in todos_resultados)
        ops = sum(m["total_operacoes"] for m in todos_resultados)
        ret = (cf - ci) / ci * 100
        print(f"\n  ─── CONSOLIDADO {periodo_label} ───")
        print(f"  Capital final: R${cf:.2f} | Retorno: {ret:+.2f}% | Ops: {ops}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtesting com dados reais da Binance — estratégia BRL"
    )
    parser.add_argument("--par", default=None,
        help="Par específico (ex: SOLBRL). Padrão: todos os 5 pares BRL.")
    parser.add_argument("--dias", type=int, default=30,
        help="Dias de histórico recente (padrão: 30). Ignorado se --inicio/--fim.")
    parser.add_argument("--inicio", default=None, metavar="YYYY-MM-DD",
        help="Data de início do período histórico (ex: 2023-10-01).")
    parser.add_argument("--fim", default=None, metavar="YYYY-MM-DD",
        help="Data de fim do período histórico (ex: 2024-01-31).")
    parser.add_argument("--sem-filtro-btc", action="store_true",
        help="Desativa o filtro BTC MA50 4h.")
    parser.add_argument("--comparar", action="store_true",
        help="COM vs SEM filtro BTC.")
    parser.add_argument("--comparar-padroes", action="store_true",
        help="Estratégia atual vs estratégia + padrões gráficos.")
    parser.add_argument("--salvar", default=None, metavar="DIR",
        help="Salva candles em JSON para testes E2E.")
    args = parser.parse_args()

    pares = [args.par] if args.par else PARES_BRL
    filtro_btc = not args.sem_filtro_btc

    periodo = f"{args.inicio} → {args.fim}" if args.inicio else f"{args.dias} dias"
    print(f"Backtesting — {', '.join(pares)} | {periodo} | filtro_btc={filtro_btc}")

    run(
        pares=pares, dias=args.dias,
        comparar_btc=args.comparar, comparar_padroes=args.comparar_padroes,
        filtro_btc=filtro_btc, salvar=args.salvar,
        inicio=args.inicio, fim=args.fim,
    )


if __name__ == "__main__":
    main()

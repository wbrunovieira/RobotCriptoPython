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
import os
import sys

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from infra.binance_client import criar_cliente_sincronizado
from analysis.backtest_real import (
    buscar_candles,
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

def run(pares: list[str], dias: int, comparar: bool, filtro_btc: bool, salvar: str | None) -> None:
    api_key = os.getenv("KEY_BINANCE")
    secret_key = os.getenv("SECRET_BINANCE")
    if not api_key or not secret_key:
        print("ERRO: KEY_BINANCE e SECRET_BINANCE precisam estar no .env")
        sys.exit(1)

    cliente = criar_cliente_sincronizado(api_key, secret_key)

    print(f"\nBuscando BTCBRL 4h ({dias} dias)...")
    dados_btc = buscar_candles(cliente, SIMBOLO_BTC, INTERVALO_BTC, dias)
    print(f"  {len(dados_btc)} candles BTC obtidos.")

    if salvar:
        os.makedirs(salvar, exist_ok=True)
        btc_path = os.path.join(salvar, "BTCBRL_4h.json")
        dados_btc.to_json(btc_path, orient="records", date_format="iso")
        print(f"  BTC salvo em {btc_path}")

    todos_resultados_com = []

    for simbolo in pares:
        print(f"\nBuscando {simbolo} 1h ({dias} dias)...")
        dados = buscar_candles(cliente, simbolo, INTERVALO_PAR, dias)
        print(f"  {len(dados)} candles obtidos.")

        if salvar:
            par_path = os.path.join(salvar, f"{simbolo}_1h.json")
            dados.to_json(par_path, orient="records", date_format="iso")
            print(f"  {simbolo} salvo em {par_path}")

        cfg_com = ConfigBacktest(filtro_btc=True)
        resultado_com = simular_par(simbolo, dados, dados_btc, cfg_com)
        m_com = calcular_metricas(resultado_com)
        todos_resultados_com.append(m_com)

        if comparar:
            cfg_sem = ConfigBacktest(filtro_btc=False)
            resultado_sem = simular_par(simbolo, dados, dados_btc, cfg_sem)
            m_sem = calcular_metricas(resultado_sem)
            imprimir_comparativo(m_com, m_sem)
        else:
            imprimir_metricas(m_com, titulo=f"{'COM' if filtro_btc else 'SEM'} filtro BTC")

    if len(pares) > 1:
        imprimir_resumo_geral(todos_resultados_com)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtesting com dados reais da Binance — estratégia BRL"
    )
    parser.add_argument(
        "--par", default=None,
        help="Par específico (ex: SOLBRL). Padrão: todos os 5 pares BRL."
    )
    parser.add_argument(
        "--dias", type=int, default=30,
        help="Quantos dias de histórico buscar (padrão: 30)."
    )
    parser.add_argument(
        "--sem-filtro-btc", action="store_true",
        help="Desativa o filtro BTC MA50 4h."
    )
    parser.add_argument(
        "--comparar", action="store_true",
        help="Roda COM e SEM filtro BTC e exibe comparativo lado a lado."
    )
    parser.add_argument(
        "--salvar", default=None, metavar="DIR",
        help="Salva os candles em JSON no diretório informado (para testes E2E)."
    )
    args = parser.parse_args()

    pares = [args.par] if args.par else PARES_BRL
    filtro_btc = not args.sem_filtro_btc

    print(f"Backtesting — {', '.join(pares)} | {args.dias} dias | filtro_btc={filtro_btc}")
    run(pares, args.dias, args.comparar, filtro_btc, args.salvar)


if __name__ == "__main__":
    main()

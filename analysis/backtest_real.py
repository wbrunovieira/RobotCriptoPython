"""Motor de backtesting usando a estratégia real do bot BRL.

Usa avaliar_sinal(), btc_acima_ma50(), trailing stop, take-profit e break-even
exatamente como o bot de produção — sem simplificações.

Uso:
    from analysis.backtest_real import simular_par, calcular_metricas, ConfigBacktest
"""
import logging
from dataclasses import dataclass

import pandas as pd

from core.sinais import avaliar_sinal, btc_acima_ma50
from core.risco import (
    stop_pct_por_atr,
    atualizar_trailing_stop,
    verificar_trailing_stop,
    verificar_take_profit,
    verificar_breakeven,
    verificar_lucro_minimo,
)

logger = logging.getLogger(__name__)

TAXA_OPERACAO = 0.001  # 0.1% por lado (taker fee Binance BRL)
MIN_CANDLES = 55       # suficiente para MA50 + ADX + RSI


@dataclass
class ConfigBacktest:
    capital_inicial: float = 1000.0
    stop_pct: float = 0.015
    take_profit_pct: float = 0.02
    percentual_compra: float = 0.90
    filtro_btc: bool = True
    bloqueio_quinta: bool = True


def buscar_candles(cliente, simbolo: str, intervalo: str, dias: int) -> pd.DataFrame:
    """Busca candles históricos da Binance e retorna DataFrame padronizado."""
    if intervalo == "1h":
        limit = min(1000, dias * 24)
    elif intervalo == "4h":
        limit = min(1000, dias * 6 + 50)
    else:
        limit = 1000

    candles = cliente.get_klines(symbol=simbolo, interval=intervalo, limit=limit)
    df = pd.DataFrame(candles)
    df.columns = [
        "tempo_abertura", "abertura", "maxima", "minima", "fechamento", "volume",
        "tempo_fechamento", "moedas_negociadas", "numero_trades",
        "volume_ativo_base_compra", "volume_ativo_cotacao", "-",
    ]
    df["tempo_fechamento"] = (
        pd.to_datetime(df["tempo_fechamento"], unit="ms")
        .dt.tz_localize("UTC")
        .dt.tz_convert("America/Sao_Paulo")
    )
    for col in ("maxima", "minima", "fechamento", "volume"):
        df[col] = df[col].astype(float)
    return df[["tempo_fechamento", "maxima", "minima", "fechamento", "volume"]].reset_index(drop=True)


def _btc_janela_ate(dados_btc: pd.DataFrame, timestamp: pd.Timestamp) -> pd.DataFrame:
    """Retorna candles BTC disponíveis até o timestamp — evita look-ahead bias."""
    if dados_btc.empty:
        return dados_btc
    return dados_btc[dados_btc["tempo_fechamento"] <= timestamp].reset_index(drop=True)


def simular_par(
    simbolo: str,
    dados: pd.DataFrame,
    dados_btc: pd.DataFrame,
    cfg: ConfigBacktest,
) -> dict:
    """Simula a estratégia candle a candle para um par BRL.

    Lógica por candle:
      1. Verifica take-profit usando a máxima do candle
      2. Verifica trailing stop usando a mínima do candle
      3. Atualiza break-even e trailing stop se em posição
      4. Avalia sinal com avaliar_sinal() real (inclui ADX, MA50, volume, RSI)
      5. Aplica filtro BTC (se ativo)
      6. Executa compra ou venda simulada

    Taxas: 0.1% por lado (taker fee Binance), descontadas em cada operação.
    """
    operacoes = []
    equity_curve = []
    capital = cfg.capital_inicial
    posicao = False
    quantidade = 0.0
    preco_entrada = None
    preco_maximo = None
    stop_price = None
    stop_pct_atual = cfg.stop_pct

    for i in range(MIN_CANDLES, len(dados)):
        janela = dados.iloc[: i + 1].copy()
        candle = dados.iloc[i]
        preco_fechamento = float(candle["fechamento"])
        minima_candle = float(candle["minima"])
        maxima_candle = float(candle["maxima"])
        ts = candle["tempo_fechamento"]

        # ── 1. Take-profit: verifica se máxima do candle atingiu o alvo ──
        if posicao and preco_entrada is not None:
            if verificar_take_profit(maxima_candle, preco_entrada, cfg.take_profit_pct):
                preco_saida = round(preco_entrada * (1 + cfg.take_profit_pct), 8)
                taxa = preco_saida * quantidade * TAXA_OPERACAO
                custo_entrada = preco_entrada * quantidade * (1 + TAXA_OPERACAO)
                total_venda = round(preco_saida * quantidade - taxa, 2)
                lucro = round(total_venda - custo_entrada, 2)
                capital += total_venda
                operacoes.append({
                    "tipo": "VENDA", "motivo": "take_profit", "simbolo": simbolo,
                    "timestamp": str(ts), "preco_entrada": preco_entrada,
                    "preco": preco_saida, "quantidade": quantidade,
                    "total_brl": total_venda, "lucro_brl": lucro,
                })
                posicao = False
                quantidade = 0.0
                preco_entrada = preco_maximo = stop_price = None
                equity_curve.append(round(capital, 2))
                continue

        # ── 2. Trailing stop: verifica se mínima atingiu o stop ──
        if posicao and stop_price is not None:
            if verificar_trailing_stop(minima_candle, stop_price):
                taxa = stop_price * quantidade * TAXA_OPERACAO
                custo_entrada = preco_entrada * quantidade * (1 + TAXA_OPERACAO)
                total_venda = round(stop_price * quantidade - taxa, 2)
                lucro = round(total_venda - custo_entrada, 2)
                capital += total_venda
                operacoes.append({
                    "tipo": "VENDA", "motivo": "trailing_stop", "simbolo": simbolo,
                    "timestamp": str(ts), "preco_entrada": preco_entrada,
                    "preco": stop_price, "quantidade": quantidade,
                    "total_brl": total_venda, "lucro_brl": lucro,
                })
                posicao = False
                quantidade = 0.0
                preco_entrada = preco_maximo = stop_price = None
                equity_curve.append(round(capital, 2))
                continue

        # ── 3. Atualiza break-even e trailing stop se em posição ──
        if posicao and preco_entrada is not None and stop_price is not None:
            novo_be = verificar_breakeven(preco_fechamento, preco_entrada, stop_price)
            if novo_be and novo_be > stop_price:
                stop_price = novo_be
                logger.debug("[%s][be] Break-even ativado: stop → %.4f", simbolo, stop_price)

            preco_maximo, stop_price = atualizar_trailing_stop(
                maxima_candle, preco_maximo, stop_price, stop_pct_atual
            )

        # ── 4. Avalia sinal com a estratégia real ──
        agora = ts
        sinal = avaliar_sinal(
            janela,
            posicao,
            pares_abertos=1 if posicao else 0,
            max_posicoes=1,
            agora=agora,
            bloqueio_quinta=cfg.bloqueio_quinta,
        )

        # ── 5. Compra: verifica filtro BTC antes de entrar ──
        if sinal == "COMPRAR" and not posicao:
            if cfg.filtro_btc:
                btc_janela = _btc_janela_ate(dados_btc, ts)
                if not btc_acima_ma50(btc_janela):
                    logger.debug("[%s][filtro_btc] Entrada bloqueada (BTC < MA50 4h).", simbolo)
                    equity_curve.append(round(capital, 2))
                    continue

            stop_pct_atual = stop_pct_por_atr(janela, stop_pct_min=cfg.stop_pct)
            quantidade = round((capital * cfg.percentual_compra) / preco_fechamento, 8)
            taxa_compra = preco_fechamento * quantidade * TAXA_OPERACAO
            custo = round(preco_fechamento * quantidade + taxa_compra, 2)
            if custo > capital:
                equity_curve.append(round(capital, 2))
                continue
            capital -= custo
            preco_entrada = preco_fechamento
            preco_maximo, stop_price = atualizar_trailing_stop(
                preco_fechamento, None, None, stop_pct_atual
            )
            posicao = True
            operacoes.append({
                "tipo": "COMPRA", "simbolo": simbolo,
                "timestamp": str(ts), "preco": preco_fechamento,
                "quantidade": quantidade, "total_brl": custo,
                "stop_pct": round(stop_pct_atual * 100, 2),
            })

        # ── 6. Venda por sinal MA ──
        elif sinal == "VENDER" and posicao:
            if verificar_lucro_minimo(preco_fechamento, preco_entrada):
                taxa = preco_fechamento * quantidade * TAXA_OPERACAO
                custo_entrada = preco_entrada * quantidade * (1 + TAXA_OPERACAO)
                total_venda = round(preco_fechamento * quantidade - taxa, 2)
                lucro = round(total_venda - custo_entrada, 2)
                capital += total_venda
                operacoes.append({
                    "tipo": "VENDA", "motivo": "sinal_ma", "simbolo": simbolo,
                    "timestamp": str(ts), "preco_entrada": preco_entrada,
                    "preco": preco_fechamento, "quantidade": quantidade,
                    "total_brl": total_venda, "lucro_brl": lucro,
                })
                posicao = False
                quantidade = 0.0
                preco_entrada = preco_maximo = stop_price = None

        valor_posicao = round(quantidade * preco_fechamento, 2) if posicao else 0.0
        equity_curve.append(round(capital + valor_posicao, 2))

    # ── Fecha posição aberta no fim do período ──
    if posicao and quantidade and preco_entrada is not None:
        preco_final = float(dados["fechamento"].iloc[-1])
        taxa = preco_final * quantidade * TAXA_OPERACAO
        custo_entrada = preco_entrada * quantidade * (1 + TAXA_OPERACAO)
        total_venda = round(preco_final * quantidade - taxa, 2)
        lucro = round(total_venda - custo_entrada, 2)
        capital += total_venda
        operacoes.append({
            "tipo": "VENDA", "motivo": "fim_periodo", "simbolo": simbolo,
            "timestamp": str(dados["tempo_fechamento"].iloc[-1]),
            "preco_entrada": preco_entrada, "preco": preco_final,
            "quantidade": quantidade, "total_brl": total_venda, "lucro_brl": lucro,
        })

    return {
        "simbolo": simbolo,
        "operacoes": operacoes,
        "equity_curve": equity_curve,
        "capital_final": round(capital, 2),
        "capital_inicial": cfg.capital_inicial,
    }


def calcular_metricas(resultado: dict) -> dict:
    """Calcula métricas de desempenho a partir do resultado de simular_par."""
    operacoes = resultado["operacoes"]
    capital_inicial = resultado["capital_inicial"]
    capital_final = resultado["capital_final"]
    equity = resultado["equity_curve"]

    vendas = [op for op in operacoes if op["tipo"] == "VENDA" and "lucro_brl" in op]
    lucros = [v["lucro_brl"] for v in vendas]
    lucrativas = [l for l in lucros if l > 0]

    drawdown_max = 0.0
    if equity:
        pico = equity[0]
        for v in equity:
            if v > pico:
                pico = v
            if pico > 0:
                dd = (pico - v) / pico * 100
                if dd > drawdown_max:
                    drawdown_max = dd

    retorno_pct = (capital_final - capital_inicial) / capital_inicial * 100 if capital_inicial else 0.0

    motivos = {}
    for v in vendas:
        m = v.get("motivo", "?")
        motivos[m] = motivos.get(m, 0) + 1

    return {
        "simbolo": resultado["simbolo"],
        "capital_inicial": capital_inicial,
        "capital_final": capital_final,
        "retorno_pct": round(retorno_pct, 2),
        "total_operacoes": len(vendas),
        "operacoes_lucrativas": len(lucrativas),
        "taxa_acerto_pct": round(len(lucrativas) / len(vendas) * 100, 1) if vendas else 0.0,
        "lucro_total_brl": round(sum(lucros), 2) if lucros else 0.0,
        "maior_ganho_brl": round(max(lucros), 2) if lucros else 0.0,
        "maior_perda_brl": round(min(lucros), 2) if lucros else 0.0,
        "drawdown_maximo_pct": round(drawdown_max, 2),
        "saidas_por_motivo": motivos,
    }

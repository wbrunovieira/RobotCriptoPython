"""Lógica de sinais para meme coins (USDT).

Funções puras — sem I/O, sem Binance.
"""
import logging

import pandas as pd

from core.indicadores import calcular_rsi, calcular_adx, calcular_atr
from core.risco import verificar_breakeven, atualizar_trailing_stop, verificar_trailing_stop
from bots.meme.config import (
    SEP_MA_MINIMA_PCT,
    RSI_MIN,
    RSI_MAX,
    RSI_SOBREVENDIDO,
    ADX_MINIMO,
    VOLUME_MULTIPLICADOR,
    TAKE_PROFIT_PCT,
    STOP_PCT_MIN,
    ATR_MULTIPLICADOR,
    BREAKEVEN_GATILHO,
    BREAKEVEN_FOLGA,
)

logger = logging.getLogger(__name__)


def calcular_score(dados: pd.DataFrame) -> dict:
    """Calcula o score de entrada para uma meme coin (0-10 pontos).

    Critérios:
    - MA9 > MA21 e separação > 0.5%: +2
    - Preço > MA50: +1
    - RSI 50-65: +2; RSI 45-50: +1
    - ADX > 25: +2; ADX 20-25: +1
    - Volume >= 2x média: +2; Volume 1.5-2x: +1
    - Variação último candle > +0.5%: +1
    """
    score = 0
    detalhes = {}

    fechamento = dados["fechamento"].astype(float)
    preco_atual = float(fechamento.iloc[-1])

    # MA9 / MA21
    ma9 = float(fechamento.rolling(window=9).mean().iloc[-1])
    ma21 = float(fechamento.rolling(window=21).mean().iloc[-1])
    sep_pct = (ma9 - ma21) / ma21 * 100 if ma21 != 0 else 0.0

    if ma9 > ma21 and sep_pct > SEP_MA_MINIMA_PCT:
        score += 2
        detalhes["ma_crossover"] = f"+2 (sep={sep_pct:.2f}%)"
    else:
        detalhes["ma_crossover"] = f"0 (sep={sep_pct:.2f}%)"

    # Preço > MA50
    ma50_val = 0.0
    if len(fechamento) >= 50:
        ma50_val = float(fechamento.rolling(window=50).mean().iloc[-1])
        if preco_atual > ma50_val:
            score += 1
            detalhes["preco_acima_ma50"] = f"+1 (preco={preco_atual:.6f}, ma50={ma50_val:.6f})"
        else:
            detalhes["preco_acima_ma50"] = f"0 (preco={preco_atual:.6f}, ma50={ma50_val:.6f})"
    else:
        detalhes["preco_acima_ma50"] = "0 (dados insuficientes)"

    # RSI
    rsi = calcular_rsi(fechamento, periodo=14)
    if RSI_MIN <= rsi <= RSI_MAX:
        score += 2
        detalhes["rsi"] = f"+2 (rsi={rsi:.1f})"
    elif 45 <= rsi < RSI_MIN:
        score += 1
        detalhes["rsi"] = f"+1 (rsi={rsi:.1f})"
    else:
        detalhes["rsi"] = f"0 (rsi={rsi:.1f})"

    # ADX
    adx = calcular_adx(dados)
    if adx > 25:
        score += 2
        detalhes["adx"] = f"+2 (adx={adx:.1f})"
    elif ADX_MINIMO <= adx <= 25:
        score += 1
        detalhes["adx"] = f"+1 (adx={adx:.1f})"
    else:
        detalhes["adx"] = f"0 (adx={adx:.1f})"

    # Volume
    volume_ratio = 0.0
    if "volume" in dados.columns and len(dados) >= 21:
        vol = dados["volume"].astype(float)
        vol_media = float(vol.rolling(20).mean().iloc[-1])
        vol_atual = float(vol.iloc[-1])
        volume_ratio = vol_atual / vol_media if vol_media > 0 else 0.0
        if volume_ratio >= VOLUME_MULTIPLICADOR:
            score += 2
            detalhes["volume"] = f"+2 (ratio={volume_ratio:.2f}x)"
        elif volume_ratio >= 1.5:
            score += 1
            detalhes["volume"] = f"+1 (ratio={volume_ratio:.2f}x)"
        else:
            detalhes["volume"] = f"0 (ratio={volume_ratio:.2f}x)"
    else:
        detalhes["volume"] = "0 (dados insuficientes)"

    # Variação do último candle
    if len(fechamento) >= 2:
        preco_anterior = float(fechamento.iloc[-2])
        variacao_pct = (preco_atual - preco_anterior) / preco_anterior * 100 if preco_anterior != 0 else 0.0
        if variacao_pct > 0.5:
            score += 1
            detalhes["variacao_candle"] = f"+1 (var={variacao_pct:.2f}%)"
        else:
            detalhes["variacao_candle"] = f"0 (var={variacao_pct:.2f}%)"
    else:
        detalhes["variacao_candle"] = "0 (dados insuficientes)"

    return {"score": min(score, 10), "detalhes": detalhes}


def calcular_stop_inicial(dados: pd.DataFrame) -> float:
    """Retorna o percentual de stop baseado no ATR do ativo."""
    atr = calcular_atr(dados, periodo=14)
    if atr == 0.0:
        return STOP_PCT_MIN
    preco = float(dados["fechamento"].iloc[-1])
    if preco == 0:
        return STOP_PCT_MIN
    atr_pct = atr / preco
    return max(STOP_PCT_MIN, atr_pct * ATR_MULTIPLICADOR)


def _volume_acima_media(dados: pd.DataFrame, multiplicador: float = 2.0) -> bool:
    """Retorna True se o volume do último candle está acima de multiplicador vezes a média."""
    if "volume" not in dados.columns or len(dados) < 21:
        return True  # sem dados de volume, não bloqueia
    vol = dados["volume"].astype(float)
    return float(vol.iloc[-1]) > float(vol.rolling(20).mean().iloc[-1]) * multiplicador


def _detectar_reversao_rsi(fechamento: pd.Series, periodo: int = 14) -> bool:
    """Retorna True se RSI estava abaixo de RSI_SOBREVENDIDO e começou a subir."""
    if len(fechamento) < periodo + 2:
        return False
    rsi_atual = calcular_rsi(fechamento, periodo)
    rsi_anterior = calcular_rsi(fechamento.iloc[:-1], periodo)
    return rsi_anterior < RSI_SOBREVENDIDO and rsi_atual > rsi_anterior


def avaliar_sinal_meme(
    dados: pd.DataFrame,
    posicao: bool,
    preco_entrada: float | None,
    stop_price: float | None,
    preco_maximo: float | None,
) -> str | None:
    """Avalia sinal de compra ou venda para meme coins.

    Compra:
      Sinal 1 — MA9 > MA21 sep > 0.5%, RSI 50-65, ADX > 20, volume > 2x, preco > MA50
      Sinal 2 — RSI < 30 revertendo para cima, volume > 2x

    Venda:
      - Take-profit atingido (preco >= entrada * (1 + TAKE_PROFIT_PCT))
      - Trailing stop disparado (preco <= stop_price)
      - Crossover baixista (MA9 < MA21 e sep > 0.5%)
    """
    fechamento = dados["fechamento"].astype(float)
    preco_atual = float(fechamento.iloc[-1])

    ma9 = float(fechamento.rolling(window=9).mean().iloc[-1])
    ma21 = float(fechamento.rolling(window=21).mean().iloc[-1])
    rsi = calcular_rsi(fechamento, periodo=14)

    if posicao:
        # Verificar take-profit
        if preco_entrada is not None and preco_atual >= preco_entrada * (1 + TAKE_PROFIT_PCT):
            variacao = (preco_atual / preco_entrada - 1) * 100
            logger.info("[meme] TAKE-PROFIT! Preco: %.8f (+%.2f%%)", preco_atual, variacao)
            return "VENDER"

        # Verificar trailing stop
        if verificar_trailing_stop(preco_atual, stop_price):
            logger.info("[meme] TRAILING STOP! Preco: %.8f <= stop: %.8f", preco_atual, stop_price)
            return "VENDER"

        # Crossover baixista
        if ma9 < ma21:
            sep_baixa_pct = (ma21 - ma9) / ma21 * 100 if ma21 != 0 else 0.0
            if sep_baixa_pct > SEP_MA_MINIMA_PCT:
                logger.info("[meme] Crossover baixista (sep=%.2f%%). Vendendo.", sep_baixa_pct)
                return "VENDER"

        return None

    # Sem posição — avaliar entradas

    # Sinal 1: MA crossover
    if ma9 > ma21:
        sep_pct = (ma9 - ma21) / ma21 * 100 if ma21 != 0 else 0.0
        if sep_pct >= SEP_MA_MINIMA_PCT and RSI_MIN <= rsi <= RSI_MAX:
            # ADX
            adx = calcular_adx(dados)
            if adx < ADX_MINIMO:
                logger.info("[meme] Sinal 1 bloqueado: ADX=%.1f < %d (lateral).", adx, ADX_MINIMO)
                return None
            # Volume
            if not _volume_acima_media(dados, multiplicador=VOLUME_MULTIPLICADOR):
                logger.info("[meme] Sinal 1 bloqueado: volume < %.1fx da média.", VOLUME_MULTIPLICADOR)
                return None
            # Preço > MA50
            if len(fechamento) >= 50:
                ma50 = float(fechamento.rolling(window=50).mean().iloc[-1])
                if preco_atual < ma50:
                    logger.info("[meme] Sinal 1 bloqueado: preco (%.8f) < MA50 (%.8f).", preco_atual, ma50)
                    return None
            logger.info("[meme] Sinal 1: MA crossover confirmado. RSI=%.1f, ADX=%.1f", rsi, calcular_adx(dados))
            return "COMPRAR"

    # Sinal 2: RSI sobrevendido revertendo
    if _detectar_reversao_rsi(fechamento):
        if not _volume_acima_media(dados, multiplicador=VOLUME_MULTIPLICADOR):
            logger.info("[meme] Sinal 2 bloqueado: volume < %.1fx da média.", VOLUME_MULTIPLICADOR)
            return None
        logger.info("[meme] Sinal 2: RSI revertendo de sobrevendido.")
        return "COMPRAR"

    return None

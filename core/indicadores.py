"""Indicadores técnicos puros.

Funções matemáticas sem efeitos colaterais — sem I/O, sem Binance.
Reutilizáveis por qualquer bot ou estratégia.
"""
import pandas as pd
import numpy as np


def calcular_rsi(precos: pd.Series, periodo: int = 14) -> float:
    """Calcula o RSI usando suavização exponencial de Wilder."""
    delta = precos.astype(float).diff()
    ganhos = delta.clip(lower=0)
    perdas = (-delta).clip(lower=0)
    alpha = 1 / periodo
    media_ganhos = ganhos.ewm(alpha=alpha, adjust=False).mean()
    media_perdas = perdas.ewm(alpha=alpha, adjust=False).mean()
    rs = media_ganhos / media_perdas
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def calcular_atr(dados: pd.DataFrame, periodo: int = 14) -> float:
    """Calcula o Average True Range (ATR) dos últimos `periodo` candles.

    Requer colunas 'maxima', 'minima' e 'fechamento'.
    Retorna 0.0 se os dados forem insuficientes ou as colunas estiverem ausentes.
    """
    if "maxima" not in dados.columns or "minima" not in dados.columns:
        return 0.0
    if len(dados) < periodo + 1:
        return 0.0

    high  = dados["maxima"].astype(float)
    low   = dados["minima"].astype(float)
    close = dados["fechamento"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(span=periodo, adjust=False).mean().iloc[-1]
    return float(atr)


def calcular_adx(dados: pd.DataFrame, periodo: int = 14) -> float:
    """Calcula o ADX (Average Directional Index) com suavização de Wilder.

    ADX > 25 — tendência forte (favorável ao MA crossover)
    ADX 20-25 — tendência fraca
    ADX < 20 — mercado lateral/chop (desfavorável ao MA crossover)
    Retorna 25.0 quando dados insuficientes para não bloquear entrada.
    """
    if "maxima" not in dados.columns or "minima" not in dados.columns:
        return 25.0
    if len(dados) < periodo * 2 + 1:
        return 25.0

    high  = dados["maxima"].astype(float)
    low   = dados["minima"].astype(float)
    close = dados["fechamento"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    up_move   = high.diff()
    down_move = -low.diff()

    dm_plus  = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    dm_minus = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    alpha    = 1 / periodo
    atr_s    = tr.ewm(alpha=alpha, adjust=False).mean()
    di_plus  = 100 * dm_plus.ewm(alpha=alpha, adjust=False).mean() / atr_s
    di_minus = 100 * dm_minus.ewm(alpha=alpha, adjust=False).mean() / atr_s

    di_sum = (di_plus + di_minus).replace(0, np.nan)
    dx     = (100 * (di_plus - di_minus).abs() / di_sum).fillna(0)
    adx    = dx.ewm(alpha=alpha, adjust=False).mean()

    return float(adx.iloc[-1])

"""Scanner de meme coins — busca o melhor candidato para entrada."""
import logging

import pandas as pd

from bots.meme.config import (
    MEME_UNIVERSE,
    PERIODO_CANDLE,
    CANDLES_HISTORICO,
    SCORE_MINIMO,
    VOLUME_MULTIPLICADOR,
)
from bots.meme.estrategia import calcular_score
from core.indicadores import calcular_rsi, calcular_adx

logger = logging.getLogger(__name__)


def _buscar_dados(cliente, simbolo: str) -> pd.DataFrame:
    """Busca candles do símbolo e retorna DataFrame padronizado."""
    candles = cliente.get_klines(symbol=simbolo, interval=PERIODO_CANDLE, limit=CANDLES_HISTORICO)
    df = pd.DataFrame(candles)
    df.columns = [
        "tempo_abertura", "abertura", "maxima", "minima", "fechamento", "volume",
        "tempo_fechamento", "moedas_negociadas", "numero_trades",
        "volume_ativo_base_compra", "volume_ativo_cotacao", "-",
    ]
    df = df[["maxima", "minima", "fechamento", "volume"]]
    for col in ("maxima", "minima", "fechamento", "volume"):
        df[col] = df[col].astype(float)
    return df


def scan_todos(cliente) -> list[dict]:
    """Faz scan de todos os símbolos do universo meme e retorna lista ordenada por score.

    Cada item: {"simbolo": str, "score": int, "preco": float, "rsi": float,
                "adx": float, "volume_ratio": float, "variacao_pct": float, "detalhes": dict}
    Símbolos com erro de API são ignorados silenciosamente.
    """
    resultados = []

    for simbolo in MEME_UNIVERSE:
        try:
            dados = _buscar_dados(cliente, simbolo)
            if dados.empty or len(dados) < 30:
                logger.warning("[scanner] %s: dados insuficientes (%d candles).", simbolo, len(dados))
                continue

            resultado_score = calcular_score(dados)
            score = resultado_score["score"]
            detalhes = resultado_score["detalhes"]

            fechamento = dados["fechamento"].astype(float)
            preco_atual = float(fechamento.iloc[-1])
            rsi = calcular_rsi(fechamento, periodo=14)
            adx = calcular_adx(dados)

            # Calcular volume_ratio
            volume_ratio = 0.0
            if "volume" in dados.columns and len(dados) >= 21:
                vol = dados["volume"].astype(float)
                vol_media = float(vol.rolling(20).mean().iloc[-1])
                vol_atual = float(vol.iloc[-1])
                volume_ratio = vol_atual / vol_media if vol_media > 0 else 0.0

            # Variação do último candle
            variacao_pct = 0.0
            if len(fechamento) >= 2:
                preco_anterior = float(fechamento.iloc[-2])
                variacao_pct = (preco_atual - preco_anterior) / preco_anterior * 100 if preco_anterior != 0 else 0.0

            resultados.append({
                "simbolo": simbolo,
                "score": score,
                "preco": preco_atual,
                "rsi": round(rsi, 2),
                "adx": round(adx, 2),
                "volume_ratio": round(volume_ratio, 2),
                "variacao_pct": round(variacao_pct, 4),
                "detalhes": detalhes,
            })

        except Exception as e:
            logger.warning("[scanner] %s: erro ao buscar dados — %s. Pulando.", simbolo, e)

    # Ordenar por score desc, volume_ratio desc (desempate)
    resultados.sort(key=lambda x: (x["score"], x["volume_ratio"]), reverse=True)
    return resultados


def scan_melhor(cliente) -> dict | None:
    """Retorna o símbolo com maior score se >= SCORE_MINIMO, senão None."""
    todos = scan_todos(cliente)
    if not todos:
        return None
    melhor = todos[0]
    if melhor["score"] >= SCORE_MINIMO:
        logger.info("[scanner] Melhor candidato: %s (score=%d)", melhor["simbolo"], melhor["score"])
        return melhor
    logger.info("[scanner] Nenhum símbolo atingiu score mínimo %d. Melhor: %s (score=%d).",
                SCORE_MINIMO, melhor["simbolo"], melhor["score"])
    return None

import pandas as pd
import numpy as np

from persistencia import carregar_posicao


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


def verificar_stop_loss(preco_atual: float, preco_entrada: float, limite_pct: float = 0.05) -> bool:
    """Retorna True se o preço caiu mais do que limite_pct em relação ao preço de entrada."""
    if preco_entrada is None:
        return False
    return preco_atual < preco_entrada * (1 - limite_pct)


def calcular_quantidade(saldo_brl: float, preco_atual: float, percentual: float = 0.90) -> float:
    """Calcula a quantidade de ativo a comprar com base no saldo disponível."""
    return round((saldo_brl * percentual) / preco_atual, 4)


def avaliar_sinal(
    dados: pd.DataFrame,
    posicao: bool,
    rsi_sobrecomprado: int = 70,
    rsi_sobrevendido: int = 30,
) -> str | None:
    """Avalia o sinal de compra ou venda com base em médias móveis e RSI."""
    fechamento = dados["fechamento"].astype(float)

    media_rapida = fechamento.rolling(window=7).mean().iloc[-1]
    media_devagar = fechamento.rolling(window=40).mean().iloc[-1]
    rsi = calcular_rsi(fechamento, periodo=14)

    print(f"Média Rápida (7): {media_rapida:.4f} | Média Devagar (40): {media_devagar:.4f} | RSI: {rsi:.2f}")

    if posicao:
        if media_rapida < media_devagar:
            return "VENDER"
        return None

    if media_rapida > media_devagar and rsi_sobrevendido < rsi < rsi_sobrecomprado:
        return "COMPRAR"

    return None

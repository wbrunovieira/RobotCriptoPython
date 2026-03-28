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


def atualizar_trailing_stop(
    preco_atual: float,
    preco_maximo: float,
    stop_atual: float,
    stop_pct: float = 0.05,
) -> tuple:
    """Atualiza o trailing stop conforme o preço sobe.
    Se o preço superar o máximo histórico, sobe o stop junto.
    O stop nunca recua — só avança quando o preço bate novo topo."""
    if preco_maximo is None or preco_atual > preco_maximo:
        novo_maximo = preco_atual
        novo_stop = preco_atual * (1 - stop_pct)
        return novo_maximo, novo_stop
    return preco_maximo, stop_atual


def verificar_trailing_stop(preco_atual: float, stop_price: float) -> bool:
    """Retorna True se o preço caiu até ou abaixo do trailing stop."""
    if stop_price is None:
        return False
    return preco_atual <= stop_price


def verificar_take_profit(preco_atual: float, preco_entrada: float, take_pct: float = 0.05) -> bool:
    """Retorna True se o preço atingiu ou superou o alvo de lucro take_pct acima do preço de entrada."""
    if preco_entrada is None:
        return False
    return preco_atual >= preco_entrada * (1 + take_pct)


def verificar_lucro_minimo(preco_atual: float, preco_entrada: float, taxa_pct: float = 0.001) -> bool:
    """Retorna True se o lucro cobre as taxas de compra + venda (round trip = 2 * taxa_pct).
    Se preco_entrada for None, permite a venda por segurança."""
    if preco_entrada is None:
        return True
    return preco_atual > preco_entrada * (1 + 2 * taxa_pct)


def detectar_reversao_rsi(
    precos: pd.Series,
    periodo: int = 14,
    limite_sobrevendido: int = 30,
) -> bool:
    """Retorna True se o RSI estava abaixo do limite sobrevendido e começou a subir.
    Sinal de reentrada após queda brusca — detecta o início da recuperação."""
    if len(precos) < periodo + 2:
        return False
    rsi_atual = calcular_rsi(precos, periodo)
    rsi_anterior = calcular_rsi(precos.iloc[:-1], periodo)
    return rsi_anterior < limite_sobrevendido and rsi_atual > rsi_anterior


def calcular_quantidade(saldo_brl: float, preco_atual: float, percentual: float = 0.90) -> float:
    """Calcula a quantidade de ativo a comprar com base no saldo disponível."""
    return round((saldo_brl * percentual) / preco_atual, 3)


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

    # Sinal 1: cruzamento de médias em zona neutra de RSI
    if media_rapida > media_devagar and rsi_sobrevendido < rsi < rsi_sobrecomprado:
        return "COMPRAR"

    # Sinal 2: reversão de RSI sobrevendido (reentrada após queda brusca)
    if detectar_reversao_rsi(fechamento, periodo=14, limite_sobrevendido=rsi_sobrevendido):
        print(f"Sinal de reversao RSI detectado (RSI subindo de sobrevendido)")
        return "COMPRAR"

    return None

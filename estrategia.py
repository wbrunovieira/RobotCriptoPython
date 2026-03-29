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
    stop_pct: float = 0.015,
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


def verificar_take_profit(preco_atual: float, preco_entrada: float, take_pct: float = 0.03) -> bool:
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


def _volume_acima_media(dados: pd.DataFrame, periodos: int = 20) -> bool:
    """Retorna True se o volume do último candle está acima da média dos últimos N candles."""
    if "volume" not in dados.columns or len(dados) < periodos + 1:
        return True  # sem dados de volume, não bloqueia
    vol = dados["volume"].astype(float)
    return float(vol.iloc[-1]) > float(vol.rolling(periodos).mean().iloc[-1])


def _horario_permitido(agora: pd.Timestamp = None) -> bool:
    """Bloqueia entradas de sexta 18h até segunda 09h (horário SP).
    Fins de semana têm volume baixo e spreads maiores."""
    if agora is None:
        agora = pd.Timestamp.now(tz="America/Sao_Paulo")
    dia = agora.dayofweek  # 0=seg, 4=sex, 5=sab, 6=dom
    hora = agora.hour
    if dia == 4 and hora >= 18:   # sexta após 18h
        return False
    if dia == 5:                   # sábado
        return False
    if dia == 6:                   # domingo
        return False
    if dia == 0 and hora < 9:     # segunda antes das 9h
        return False
    return True


def contar_posicoes_abertas(pares: list) -> int:
    """Conta quantos pares estão com posição aberta no momento."""
    from pares import arquivo_posicao
    abertas = 0
    for par in pares:
        estado = carregar_posicao(arquivo=arquivo_posicao(par["simbolo"]))
        if estado.get("posicao"):
            abertas += 1
    return abertas


def avaliar_sinal(
    dados: pd.DataFrame,
    posicao: bool,
    rsi_sobrecomprado: int = 70,
    rsi_sobrevendido: int = 30,
    pares_abertos: int = 0,
    max_posicoes: int = 2,
    agora: pd.Timestamp = None,
) -> str | None:
    """Avalia o sinal de compra ou venda com base em médias móveis e RSI.

    Filtros de entrada (apenas para COMPRAR):
    - MA9 > MA21 (crossover)
    - RSI entre 50 e rsi_sobrecomprado (momentum confirmado, sem sobrecompra)
    - Volume do candle atual acima da média de 20 candles
    - Horário permitido (bloqueia fins de semana)
    - Número de posições abertas abaixo do limite
    """
    fechamento = dados["fechamento"].astype(float)

    media_rapida = fechamento.rolling(window=9).mean().iloc[-1]
    media_devagar = fechamento.rolling(window=21).mean().iloc[-1]
    rsi = calcular_rsi(fechamento, periodo=14)

    print(f"Média Rápida (9): {media_rapida:.4f} | Média Devagar (21): {media_devagar:.4f} | RSI: {rsi:.2f}")

    if posicao:
        if media_rapida < media_devagar:
            return "VENDER"
        return None

    # Filtro: limite de posições simultâneas
    if pares_abertos >= max_posicoes:
        print(f"Filtro: {pares_abertos}/{max_posicoes} posições abertas. Entrada bloqueada.")
        return None

    # Filtro: horário (sem fins de semana)
    if not _horario_permitido(agora):
        print("Filtro: horário fora da janela operacional (fim de semana). Entrada bloqueada.")
        return None

    # Filtro de regime: não entra se preço abaixo da MA50 (tendência baixista)
    if len(fechamento) >= 50:
        ma50 = fechamento.rolling(window=50).mean().iloc[-1]
        preco_atual_val = float(fechamento.iloc[-1])
        if preco_atual_val < ma50:
            print(f"Filtro de regime: preço ({preco_atual_val:.2f}) abaixo da MA50 ({ma50:.2f}). Entrada bloqueada.")
            return None

    # Sinal 1: cruzamento MA9 > MA21 com RSI confirmando momentum (> 50)
    if media_rapida > media_devagar and 50 < rsi < rsi_sobrecomprado:
        if not _volume_acima_media(dados):
            print("Filtro: volume abaixo da média. Entrada bloqueada.")
            return None
        return "COMPRAR"

    # Sinal 2: reversão de RSI sobrevendido (reentrada após queda brusca)
    if detectar_reversao_rsi(fechamento, periodo=14, limite_sobrevendido=rsi_sobrevendido):
        if not _horario_permitido(agora):
            return None
        if pares_abertos >= max_posicoes:
            return None
        if not _volume_acima_media(dados):
            print("Filtro: volume abaixo da média (reversão RSI). Entrada bloqueada.")
            return None
        print(f"Sinal de reversao RSI detectado (RSI subindo de sobrevendido)")
        return "COMPRAR"

    return None

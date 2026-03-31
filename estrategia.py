import pandas as pd
import numpy as np

from persistencia import carregar_posicao

_MIN_CROSSOVER_SEPARATION_PCT = 0.5   # % mínimo de separação MA9/MA21
_MA50_SLOPE_MAX_QUEDA_PCT     = -0.2  # % queda da MA50 em 3 candles para bloquear


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


def stop_pct_por_atr(
    dados: pd.DataFrame,
    stop_pct_min: float = 0.015,
    multiplicador: float = 2.2,
    periodo: int = 14,
) -> float:
    """Retorna o percentual de stop baseado no ATR do ativo.

    stop = max(stop_pct_min, ATR_pct * multiplicador)
    Garante que o stop nunca seja menor que stop_pct_min.
    """
    atr = calcular_atr(dados, periodo)
    if atr == 0.0:
        return stop_pct_min
    preco = float(dados["fechamento"].iloc[-1])
    if preco == 0:
        return stop_pct_min
    atr_pct = atr / preco
    return max(stop_pct_min, atr_pct * multiplicador)


def verificar_breakeven(
    preco_atual: float,
    preco_entrada: float,
    stop_price: float,
    ativacao_pct: float = 0.015,
    margem_pct: float = 0.001,
) -> float | None:
    """Retorna o novo stop de break-even quando o lucro atinge `ativacao_pct`.

    Move o stop para preco_entrada * (1 + margem_pct) — eliminando risco de perda.
    Retorna None se:
    - preco_entrada ou stop_price forem None
    - o lucro ainda não atingiu o threshold
    - o stop já está acima do nível de break-even (já foi ativado)
    """
    if preco_entrada is None or stop_price is None:
        return None
    nivel_breakeven = preco_entrada * (1 + margem_pct)
    if stop_price >= nivel_breakeven:
        return None  # já está em break-even ou melhor
    if preco_atual >= preco_entrada * (1 + ativacao_pct):
        return nivel_breakeven
    return None


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
    reentrada: bool = False,
) -> str | None:
    """Avalia o sinal de compra ou venda com base em médias móveis e RSI.

    Sinal 1 — Crossover MA9/MA21 (trend-following):
      - MA9 > MA21, RSI 50–70, volume ok
      - Filtros: preço > MA50, MA50 não caindo, separação mínima do crossover

    Sinal 2 — Reversão RSI sobrevendido (counter-trend):
      - RSI estava abaixo de 30 e começou a subir
      - Sem filtros de regime (por design — é entrada contra-tendência)
    """
    fechamento = dados["fechamento"].astype(float)

    media_rapida = fechamento.rolling(window=9).mean().iloc[-1]
    media_devagar = fechamento.rolling(window=21).mean().iloc[-1]
    rsi = calcular_rsi(fechamento, periodo=14)

    print(f"Média Rápida (9): {media_rapida:.4f} | Média Devagar (21): {media_devagar:.4f} | RSI: {rsi:.2f}")

    if posicao:
        if media_rapida < media_devagar:
            separacao_venda_pct = (media_devagar - media_rapida) / media_devagar * 100
            if separacao_venda_pct < 0.3:
                print(f"Filtro de saída: crossover fraco ({separacao_venda_pct:.2f}% < 0.3%). Aguardando trailing stop.")
                return None
            return "VENDER"
        return None

    # Filtros comuns a todos os sinais de compra
    if pares_abertos >= max_posicoes:
        print(f"Filtro: {pares_abertos}/{max_posicoes} posições abertas. Entrada bloqueada.")
        return None

    if not _horario_permitido(agora):
        print("Filtro: horário fora da janela operacional (fim de semana). Entrada bloqueada.")
        return None

    # --- Sinal 1: Crossover MA9 > MA21 (trend-following) ---
    if media_rapida > media_devagar and 50 < rsi < rsi_sobrecomprado:
        # Filtro de regime: preço vs MA50
        if len(fechamento) >= 50:
            ma50_series = fechamento.rolling(window=50).mean()
            ma50 = ma50_series.iloc[-1]
            preco_atual_val = float(fechamento.iloc[-1])
            if preco_atual_val < ma50:
                print(f"Filtro de regime: preço ({preco_atual_val:.2f}) abaixo da MA50 ({ma50:.2f}). Entrada bloqueada.")
                return None
            # Slope da MA50: bloqueia se estiver caindo (ignorado em reentradas — slope lento demais)
            if not reentrada and len(fechamento) >= 53:
                ma50_3h_atras = ma50_series.iloc[-4]
                slope_pct = (ma50 - ma50_3h_atras) / ma50_3h_atras * 100
                if slope_pct < _MA50_SLOPE_MAX_QUEDA_PCT:
                    print(f"Filtro: MA50 caindo ({slope_pct:.2f}%). Entrada bloqueada.")
                    return None
        # Força mínima do crossover — limiar reduzido em reentradas imediatas
        limiar_separacao = 0.2 if reentrada else _MIN_CROSSOVER_SEPARATION_PCT
        separacao_pct = (media_rapida - media_devagar) / media_devagar * 100
        if separacao_pct < limiar_separacao:
            print(f"Filtro: crossover fraco ({separacao_pct:.2f}% < {limiar_separacao}%). Entrada bloqueada.")
            return None
        if not _volume_acima_media(dados):
            print("Filtro: volume abaixo da média. Entrada bloqueada.")
            return None
        # Filtro de regime: ADX confirma que o mercado está em tendência
        # MA crossover tem EV negativo em mercado lateral (ADX < 20)
        adx = calcular_adx(dados)
        if adx < 20:
            print(f"Filtro: mercado lateral (ADX={adx:.1f} < 20). Entrada Signal 1 bloqueada.")
            return None
        print(f"ADX={adx:.1f} — tendência confirmada.")
        return "COMPRAR"

    # --- Sinal 2: Reversão RSI sobrevendido (counter-trend) ---
    if detectar_reversao_rsi(fechamento, periodo=14, limite_sobrevendido=rsi_sobrevendido):
        if not _volume_acima_media(dados):
            print("Filtro: volume abaixo da média (reversão RSI). Entrada bloqueada.")
            return None
        print("Sinal de reversao RSI detectado (RSI subindo de sobrevendido)")
        return "COMPRAR"

    return None

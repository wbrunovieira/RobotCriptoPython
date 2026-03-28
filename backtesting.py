import pandas as pd

from estrategia import (
    calcular_quantidade,
    calcular_rsi,
    detectar_reversao_rsi,
    atualizar_trailing_stop,
    verificar_trailing_stop,
    verificar_lucro_minimo,
)


def _avaliar_sinal_backtest(
    dados: pd.DataFrame,
    posicao: bool,
    ma_rapida: int = 7,
    ma_devagar: int = 40,
    rsi_periodo: int = 14,
    rsi_sobrecomprado: int = 70,
    rsi_sobrevendido: int = 30,
) -> str | None:
    """Versão silenciosa do avaliar_sinal para uso interno no backtesting."""
    fechamento = dados["fechamento"].astype(float)
    if len(fechamento) < ma_devagar:
        return None

    media_rapida = fechamento.rolling(window=ma_rapida).mean().iloc[-1]
    media_devagar = fechamento.rolling(window=ma_devagar).mean().iloc[-1]
    rsi = calcular_rsi(fechamento, periodo=rsi_periodo)

    if posicao:
        return "VENDER" if media_rapida < media_devagar else None

    if media_rapida > media_devagar and rsi_sobrevendido < rsi < rsi_sobrecomprado:
        return "COMPRAR"

    if detectar_reversao_rsi(fechamento, periodo=rsi_periodo, limite_sobrevendido=rsi_sobrevendido):
        return "COMPRAR"

    return None


def simular_estrategia(
    dados: pd.DataFrame,
    capital_inicial: float = 1000.0,
    stop_pct: float = 0.05,
    percentual_saldo: float = 0.90,
    ma_rapida: int = 7,
    ma_devagar: int = 40,
    rsi_periodo: int = 14,
    rsi_sobrecomprado: int = 70,
    rsi_sobrevendido: int = 30,
) -> dict:
    """Simula a estratégia completa em dados históricos.

    Retorna dict com:
      - operacoes: lista de compras e vendas realizadas
      - equity_curve: valor total da carteira a cada candle
      - capital_final: capital ao final da simulação (incluindo posição aberta)
    """
    min_candles = ma_devagar + rsi_periodo
    if len(dados) < min_candles:
        return {"operacoes": [], "equity_curve": [capital_inicial], "capital_final": capital_inicial}

    operacoes = []
    equity_curve = [capital_inicial]
    capital = capital_inicial
    posicao = False
    quantidade = 0.0
    preco_entrada = None
    preco_maximo = None
    stop_price = None

    for i in range(min_candles, len(dados)):
        janela = dados.iloc[: i + 1]
        preco_atual = float(janela["fechamento"].iloc[-1])

        # Trailing stop check
        if posicao and stop_price and verificar_trailing_stop(preco_atual, stop_price):
            total_venda = round(quantidade * preco_atual, 2)
            lucro = round(total_venda - preco_entrada * quantidade, 2)
            capital += total_venda
            operacoes.append({
                "tipo": "VENDA", "motivo": "trailing_stop",
                "preco": preco_atual, "quantidade": quantidade,
                "total_brl": total_venda, "lucro_brl": lucro, "indice": i,
            })
            posicao = False
            quantidade = 0.0
            preco_entrada = preco_maximo = stop_price = None
            equity_curve.append(capital)
            continue

        # Atualiza trailing stop se em posição
        if posicao:
            preco_maximo, stop_price = atualizar_trailing_stop(
                preco_atual, preco_maximo, stop_price, stop_pct
            )

        sinal = _avaliar_sinal_backtest(
            janela, posicao, ma_rapida, ma_devagar,
            rsi_periodo, rsi_sobrecomprado, rsi_sobrevendido,
        )

        if sinal == "COMPRAR" and not posicao:
            quantidade = calcular_quantidade(capital, preco_atual, percentual_saldo)
            custo = round(quantidade * preco_atual, 2)
            capital -= custo
            preco_entrada = preco_atual
            preco_maximo, stop_price = atualizar_trailing_stop(preco_atual, None, None, stop_pct)
            posicao = True
            operacoes.append({
                "tipo": "COMPRA",
                "preco": preco_atual, "quantidade": quantidade,
                "total_brl": custo, "indice": i,
            })

        elif sinal == "VENDER" and posicao:
            if verificar_lucro_minimo(preco_atual, preco_entrada):
                total_venda = round(quantidade * preco_atual, 2)
                lucro = round(total_venda - preco_entrada * quantidade, 2)
                capital += total_venda
                operacoes.append({
                    "tipo": "VENDA", "motivo": "sinal",
                    "preco": preco_atual, "quantidade": quantidade,
                    "total_brl": total_venda, "lucro_brl": lucro, "indice": i,
                })
                posicao = False
                quantidade = 0.0
                preco_entrada = preco_maximo = stop_price = None

        valor_posicao = quantidade * preco_atual if posicao else 0.0
        equity_curve.append(capital + valor_posicao)

    capital_final = capital + (quantidade * float(dados["fechamento"].iloc[-1]) if posicao else 0.0)
    return {"operacoes": operacoes, "equity_curve": equity_curve, "capital_final": round(capital_final, 2)}


def calcular_metricas(operacoes: list, capital_inicial: float = 1000.0) -> dict:
    """Calcula métricas de desempenho a partir das operações simuladas."""
    vendas = [op for op in operacoes if op["tipo"] == "VENDA"]

    if not vendas:
        return {
            "total_operacoes": 0,
            "operacoes_lucrativas": 0,
            "lucro_total_brl": 0.0,
            "maior_ganho": 0.0,
            "maior_perda": 0.0,
            "taxa_acerto_pct": 0.0,
            "drawdown_maximo_pct": 0.0,
        }

    lucros = [v["lucro_brl"] for v in vendas]
    lucrativas = [l for l in lucros if l > 0]

    return {
        "total_operacoes": len(vendas),
        "operacoes_lucrativas": len(lucrativas),
        "lucro_total_brl": round(sum(lucros), 2),
        "maior_ganho": max(lucros),
        "maior_perda": min(lucros) if min(lucros) < 0 else 0.0,
        "taxa_acerto_pct": round(len(lucrativas) / len(vendas) * 100, 1),
        "drawdown_maximo_pct": 0.0,
    }


def calcular_drawdown_maximo(equity_curve: list) -> float:
    """Calcula o drawdown máximo (%) a partir da curva de equity."""
    if not equity_curve:
        return 0.0
    max_dd = 0.0
    peak = equity_curve[0]
    for val in equity_curve:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 2)


def comparar_periodos(
    dados: pd.DataFrame,
    capital_inicial: float = 1000.0,
    combinacoes: list | None = None,
) -> list:
    """Simula a estratégia com diferentes combinações de MA e retorna resultados
    ordenados por lucro total decrescente."""
    if combinacoes is None:
        combinacoes = [(5, 20), (7, 40), (10, 50)]

    resultados = []
    for ma_r, ma_d in combinacoes:
        resultado = simular_estrategia(dados, capital_inicial, ma_rapida=ma_r, ma_devagar=ma_d)
        metricas = calcular_metricas(resultado["operacoes"], capital_inicial)
        metricas["drawdown_maximo_pct"] = calcular_drawdown_maximo(resultado["equity_curve"])
        metricas["ma_rapida"] = ma_r
        metricas["ma_devagar"] = ma_d
        metricas["capital_final"] = resultado["capital_final"]
        resultados.append(metricas)

    return sorted(resultados, key=lambda r: r["lucro_total_brl"], reverse=True)


def baixar_dados_historicos(
    cliente,
    simbolo: str = "SOLBRL",
    intervalo: str = "1h",
    data_inicio: str = "1 jan, 2026",
    data_fim: str | None = None,
) -> pd.DataFrame:
    """Baixa candles históricos da Binance e retorna DataFrame no mesmo formato
    de pegando_dados() em robo_cripto.py."""
    klines = cliente.get_historical_klines(simbolo, intervalo, data_inicio, data_fim)
    if not klines:
        return pd.DataFrame()

    df = pd.DataFrame(klines, columns=[
        "tempo_abertura", "abertura", "maxima", "minima", "fechamento", "volume",
        "tempo_fechamento", "moedas_negociadas", "numero_trades",
        "volume_ativo_base_compra", "volume_ativo_cotacao", "-",
    ])
    df = df[["fechamento", "tempo_fechamento"]]
    df["tempo_fechamento"] = (
        pd.to_datetime(df["tempo_fechamento"], unit="ms")
        .dt.tz_localize("UTC")
        .dt.tz_convert("America/Sao_Paulo")
    )
    df["fechamento"] = df["fechamento"].astype(float)
    return df

import json
import os
from itertools import product

from backtesting import simular_estrategia, calcular_metricas, calcular_drawdown_maximo

# Valores padrão para o grid search
_MA_RAPIDAS_PADRAO = [5, 7, 10]
_MA_DEVAGAR_PADRAO = [20, 40, 50]
_RSI_SC_PADRAO = [65, 70, 75]
_RSI_SV_PADRAO = [25, 30, 35]
_STOP_PCTS_PADRAO = [0.03, 0.05, 0.07]

ARQUIVO_CONFIG = "config/melhor_configuracao.json"


def gerar_combinacoes(
    ma_rapidas: list = None,
    ma_devagar: list = None,
    rsi_sobrecomprado: list = None,
    rsi_sobrevendido: list = None,
    stop_pcts: list = None,
) -> list:
    """Gera todas as combinações válidas de parâmetros para o grid search.

    Regras de validação:
      - ma_rapida < ma_devagar
      - rsi_sobrevendido < rsi_sobrecomprado
    """
    ma_r = ma_rapidas if ma_rapidas is not None else _MA_RAPIDAS_PADRAO
    ma_d = ma_devagar if ma_devagar is not None else _MA_DEVAGAR_PADRAO
    rsi_sc = rsi_sobrecomprado if rsi_sobrecomprado is not None else _RSI_SC_PADRAO
    rsi_sv = rsi_sobrevendido if rsi_sobrevendido is not None else _RSI_SV_PADRAO
    stops = stop_pcts if stop_pcts is not None else _STOP_PCTS_PADRAO

    combinacoes = []
    for r, d, sc, sv, stop in product(ma_r, ma_d, rsi_sc, rsi_sv, stops):
        if r >= d:
            continue
        if sv >= sc:
            continue
        combinacoes.append({
            "ma_rapida": r,
            "ma_devagar": d,
            "rsi_sobrecomprado": sc,
            "rsi_sobrevendido": sv,
            "stop_pct": stop,
        })
    return combinacoes


def otimizar(dados, capital_inicial: float = 1000.0, combinacoes: list = None) -> list:
    """Executa o backtesting para cada combinação e retorna resultados ordenados
    por lucro total decrescente."""
    if not combinacoes:
        return []

    resultados = []
    for combo in combinacoes:
        resultado = simular_estrategia(
            dados,
            capital_inicial=capital_inicial,
            stop_pct=combo["stop_pct"],
            ma_rapida=combo["ma_rapida"],
            ma_devagar=combo["ma_devagar"],
            rsi_sobrecomprado=combo["rsi_sobrecomprado"],
            rsi_sobrevendido=combo["rsi_sobrevendido"],
        )
        metricas = calcular_metricas(resultado["operacoes"], capital_inicial)
        metricas["drawdown_maximo_pct"] = calcular_drawdown_maximo(resultado["equity_curve"])
        metricas["capital_final"] = resultado["capital_final"]
        metricas.update(combo)
        resultados.append(metricas)

    return sorted(resultados, key=lambda r: r["lucro_total_brl"], reverse=True)


def melhor_configuracao(resultados: list) -> dict | None:
    """Retorna a configuração com melhor resultado (primeiro da lista ordenada)."""
    if not resultados:
        return None
    return resultados[0]


def salvar_configuracao(config: dict, arquivo: str = ARQUIVO_CONFIG):
    """Persiste a melhor configuração encontrada em JSON."""
    os.makedirs(os.path.dirname(arquivo) or ".", exist_ok=True)
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def carregar_configuracao(arquivo: str = ARQUIVO_CONFIG) -> dict | None:
    """Carrega a melhor configuração salva. Retorna None se não existir."""
    if not os.path.exists(arquivo):
        return None
    with open(arquivo, "r", encoding="utf-8") as f:
        return json.load(f)

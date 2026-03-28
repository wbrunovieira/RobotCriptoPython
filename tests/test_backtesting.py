import pytest
import pandas as pd
from unittest.mock import MagicMock
from backtesting import (
    simular_estrategia,
    calcular_metricas,
    calcular_drawdown_maximo,
    comparar_periodos,
    baixar_dados_historicos,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gerar_dados(n: int, preco_base: float = 400.0, variacao: float = 0.0) -> pd.DataFrame:
    """Gera n candles com preço estável (variacao=0) ou crescente (variacao>0)."""
    precos = [preco_base + variacao * i for i in range(n)]
    return pd.DataFrame({"fechamento": precos, "tempo_fechamento": pd.date_range("2026-01-01", periods=n, freq="h")})


def _gerar_dados_alternados(n: int, preco_base: float = 400.0) -> pd.DataFrame:
    """Gera dados com subidas e descidas alternadas — mantém RSI em zona neutra."""
    precos = [preco_base]
    for i in range(n - 1):
        if i % 3 == 0:
            precos.append(precos[-1] * 1.012)
        elif i % 3 == 1:
            precos.append(precos[-1] * 0.993)
        else:
            precos.append(precos[-1] * 1.008)
    return pd.DataFrame({"fechamento": precos, "tempo_fechamento": pd.date_range("2026-01-01", periods=n, freq="h")})


def _operacoes_com_lucro():
    return [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "indice": 50},
        {"tipo": "VENDA", "motivo": "sinal", "preco": 460.0, "quantidade": 2.0, "total_brl": 920.0, "lucro_brl": 40.0, "indice": 60},
    ]


def _operacoes_com_prejuizo():
    return [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "indice": 50},
        {"tipo": "VENDA", "motivo": "trailing_stop", "preco": 418.0, "quantidade": 2.0, "total_brl": 836.0, "lucro_brl": -44.0, "indice": 60},
    ]


# ---------------------------------------------------------------------------
# simular_estrategia — estrutura e casos extremos
# ---------------------------------------------------------------------------

def test_simular_retorna_estrutura_correta():
    dados = _gerar_dados(200)
    resultado = simular_estrategia(dados, capital_inicial=1000.0)
    assert "operacoes" in resultado
    assert "equity_curve" in resultado
    assert "capital_final" in resultado


def test_simular_sem_dados_suficientes_retorna_vazio():
    dados = _gerar_dados(30)  # menos que ma_devagar(40) + rsi_periodo(14)
    resultado = simular_estrategia(dados, capital_inicial=1000.0)
    assert resultado["operacoes"] == []
    assert resultado["capital_final"] == 1000.0


def test_simular_mercado_lateral_nao_gera_operacoes():
    """Preço completamente flat → sem cruzamento de médias → sem operações."""
    dados = _gerar_dados(200, preco_base=400.0, variacao=0.0)
    resultado = simular_estrategia(dados, capital_inicial=1000.0)
    assert resultado["operacoes"] == []
    assert resultado["capital_final"] == pytest.approx(1000.0)


def test_simular_equity_curve_tem_comprimento_correto():
    dados = _gerar_dados(200)
    resultado = simular_estrategia(dados, capital_inicial=1000.0)
    # equity_curve deve ter ao menos 1 entrada (capital inicial) + entradas por candle
    assert len(resultado["equity_curve"]) >= 1
    assert resultado["equity_curve"][0] == pytest.approx(1000.0)


def test_simular_capital_final_nunca_negativo():
    dados = _gerar_dados_alternados(300)
    resultado = simular_estrategia(dados, capital_inicial=1000.0)
    assert resultado["capital_final"] >= 0


def test_simular_aceita_periodos_customizados():
    dados = _gerar_dados(300)
    resultado = simular_estrategia(dados, capital_inicial=1000.0, ma_rapida=5, ma_devagar=20)
    assert "operacoes" in resultado


# ---------------------------------------------------------------------------
# calcular_metricas
# ---------------------------------------------------------------------------

def test_metricas_sem_operacoes():
    metricas = calcular_metricas([], capital_inicial=1000.0)
    assert metricas["total_operacoes"] == 0
    assert metricas["lucro_total_brl"] == 0.0
    assert metricas["taxa_acerto_pct"] == 0.0
    assert metricas["drawdown_maximo_pct"] == 0.0


def test_metricas_com_uma_venda_lucrativa():
    metricas = calcular_metricas(_operacoes_com_lucro())
    assert metricas["total_operacoes"] == 1
    assert metricas["operacoes_lucrativas"] == 1
    assert metricas["lucro_total_brl"] == pytest.approx(40.0)
    assert metricas["maior_ganho"] == pytest.approx(40.0)
    assert metricas["maior_perda"] == 0.0
    assert metricas["taxa_acerto_pct"] == 100.0


def test_metricas_com_prejuizo():
    metricas = calcular_metricas(_operacoes_com_prejuizo())
    assert metricas["total_operacoes"] == 1
    assert metricas["operacoes_lucrativas"] == 0
    assert metricas["lucro_total_brl"] == pytest.approx(-44.0)
    assert metricas["maior_perda"] == pytest.approx(-44.0)
    assert metricas["taxa_acerto_pct"] == 0.0


def test_metricas_misto_calcula_taxa_acerto():
    ops = _operacoes_com_lucro() + _operacoes_com_prejuizo()
    metricas = calcular_metricas(ops)
    assert metricas["total_operacoes"] == 2
    assert metricas["taxa_acerto_pct"] == 50.0
    assert metricas["lucro_total_brl"] == pytest.approx(-4.0)


def test_metricas_ignora_compras_no_total():
    """total_operacoes conta ciclos (vendas), não compras."""
    ops = _operacoes_com_lucro()
    metricas = calcular_metricas(ops)
    assert metricas["total_operacoes"] == 1  # 1 venda, não 2 (compra+venda)


# ---------------------------------------------------------------------------
# calcular_drawdown_maximo
# ---------------------------------------------------------------------------

def test_drawdown_equity_crescente_e_zero():
    equity = [1000.0, 1010.0, 1020.0, 1030.0]
    assert calcular_drawdown_maximo(equity) == 0.0


def test_drawdown_queda_simples():
    # Sobe para 1100, cai para 990 → dd = (1100-990)/1100 * 100 ≈ 10%
    equity = [1000.0, 1050.0, 1100.0, 1050.0, 990.0]
    dd = calcular_drawdown_maximo(equity)
    assert dd == pytest.approx((1100 - 990) / 1100 * 100, abs=0.01)


def test_drawdown_lista_vazia_retorna_zero():
    assert calcular_drawdown_maximo([]) == 0.0


def test_drawdown_captura_pior_queda():
    # Queda 1: de 1000 para 900 → 10%
    # Queda 2: de 1200 para 1000 → 16.7%  ← deve ser esta
    equity = [1000.0, 900.0, 1200.0, 1000.0]
    dd = calcular_drawdown_maximo(equity)
    assert dd == pytest.approx((1200 - 1000) / 1200 * 100, abs=0.1)


# ---------------------------------------------------------------------------
# comparar_periodos
# ---------------------------------------------------------------------------

def test_comparar_periodos_retorna_um_resultado_por_combinacao():
    dados = _gerar_dados(300)
    combinacoes = [(5, 20), (7, 40)]
    resultados = comparar_periodos(dados, capital_inicial=1000.0, combinacoes=combinacoes)
    assert len(resultados) == 2


def test_comparar_periodos_resultados_tem_campos_esperados():
    dados = _gerar_dados(300)
    combinacoes = [(5, 20)]
    resultado = comparar_periodos(dados, combinacoes=combinacoes)[0]
    assert "ma_rapida" in resultado
    assert "ma_devagar" in resultado
    assert "lucro_total_brl" in resultado
    assert "taxa_acerto_pct" in resultado
    assert "drawdown_maximo_pct" in resultado
    assert "capital_final" in resultado
    assert resultado["ma_rapida"] == 5
    assert resultado["ma_devagar"] == 20


def test_comparar_periodos_ordenado_por_lucro_decrescente():
    dados = _gerar_dados_alternados(300)
    combinacoes = [(5, 20), (7, 40), (10, 50)]
    resultados = comparar_periodos(dados, capital_inicial=1000.0, combinacoes=combinacoes)
    lucros = [r["lucro_total_brl"] for r in resultados]
    assert lucros == sorted(lucros, reverse=True)


def test_comparar_periodos_usa_combinacoes_padrao_se_nao_informado():
    dados = _gerar_dados(300)
    resultados = comparar_periodos(dados, capital_inicial=1000.0)
    assert len(resultados) == 3  # (5,20), (7,40), (10,50)


# ---------------------------------------------------------------------------
# baixar_dados_historicos
# ---------------------------------------------------------------------------

def test_baixar_dados_retorna_dataframe_formatado():
    klines = [
        [1700000000000, "390.0", "395.0", "385.0", "392.0", "1000",
         1700003600000, "392000.0", 200, "600", "234000", "0"],
    ]
    cliente = MagicMock()
    cliente.get_historical_klines.return_value = klines

    df = baixar_dados_historicos(cliente, simbolo="SOLBRL", intervalo="1h", data_inicio="1 jan, 2026")
    assert not df.empty
    assert "fechamento" in df.columns
    assert "tempo_fechamento" in df.columns
    assert df["fechamento"].iloc[0] == pytest.approx(392.0)


def test_baixar_dados_sem_resultado_retorna_dataframe_vazio():
    cliente = MagicMock()
    cliente.get_historical_klines.return_value = []
    df = baixar_dados_historicos(cliente)
    assert df.empty


def test_baixar_dados_chama_cliente_com_parametros_corretos():
    cliente = MagicMock()
    cliente.get_historical_klines.return_value = []
    baixar_dados_historicos(cliente, simbolo="BTCBRL", intervalo="4h", data_inicio="1 fev, 2026")
    cliente.get_historical_klines.assert_called_once_with("BTCBRL", "4h", "1 fev, 2026", None)

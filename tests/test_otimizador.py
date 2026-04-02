import pytest
import json
import os
import pandas as pd
from analysis.otimizador import (
    gerar_combinacoes,
    otimizar,
    melhor_configuracao,
    salvar_configuracao,
    carregar_configuracao,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gerar_dados(n: int = 300, preco_base: float = 400.0) -> pd.DataFrame:
    precos = [preco_base] * n  # mercado flat — sem operações, mas suficiente para rodar
    return pd.DataFrame(
        {"fechamento": precos, "tempo_fechamento": pd.date_range("2026-01-01", periods=n, freq="h")}
    )


def _resultado(lucro: float, ma_r: int = 7, ma_d: int = 40, stop: float = 0.05,
               rsi_sc: int = 70, rsi_sv: int = 30) -> dict:
    return {
        "ma_rapida": ma_r, "ma_devagar": ma_d,
        "rsi_sobrecomprado": rsi_sc, "rsi_sobrevendido": rsi_sv,
        "stop_pct": stop,
        "lucro_total_brl": lucro,
        "taxa_acerto_pct": 60.0,
        "drawdown_maximo_pct": 5.0,
        "total_operacoes": 10,
        "capital_final": 1000.0 + lucro,
    }


# ---------------------------------------------------------------------------
# gerar_combinacoes
# ---------------------------------------------------------------------------

def test_gerar_combinacoes_produto_cartesiano():
    combos = gerar_combinacoes(
        ma_rapidas=[5, 7],
        ma_devagar=[20, 40],
        rsi_sobrecomprado=[70],
        rsi_sobrevendido=[30],
        stop_pcts=[0.05],
    )
    assert len(combos) == 4  # 2 × 2 × 1 × 1 × 1


def test_gerar_combinacoes_exclui_ma_rapida_maior_que_devagar():
    combos = gerar_combinacoes(
        ma_rapidas=[10, 20],
        ma_devagar=[15],
        rsi_sobrecomprado=[70],
        rsi_sobrevendido=[30],
        stop_pcts=[0.05],
    )
    # ma_rapida=20 com ma_devagar=15 é inválido — deve ser excluído
    assert all(c["ma_rapida"] < c["ma_devagar"] for c in combos)
    assert len(combos) == 1  # só (10, 15)


def test_gerar_combinacoes_exclui_rsi_sobrevendido_maior_que_sobrecomprado():
    combos = gerar_combinacoes(
        ma_rapidas=[7],
        ma_devagar=[40],
        rsi_sobrecomprado=[60],
        rsi_sobrevendido=[65],  # inválido: sv > sc
        stop_pcts=[0.05],
    )
    assert combos == []


def test_gerar_combinacoes_campos_corretos():
    combos = gerar_combinacoes(
        ma_rapidas=[7],
        ma_devagar=[40],
        rsi_sobrecomprado=[70],
        rsi_sobrevendido=[30],
        stop_pcts=[0.05],
    )
    assert len(combos) == 1
    c = combos[0]
    assert c["ma_rapida"] == 7
    assert c["ma_devagar"] == 40
    assert c["rsi_sobrecomprado"] == 70
    assert c["rsi_sobrevendido"] == 30
    assert c["stop_pct"] == pytest.approx(0.05)


def test_gerar_combinacoes_valores_padrao_gera_lista_nao_vazia():
    combos = gerar_combinacoes()
    assert len(combos) > 0
    assert all(c["ma_rapida"] < c["ma_devagar"] for c in combos)
    assert all(c["rsi_sobrevendido"] < c["rsi_sobrecomprado"] for c in combos)


# ---------------------------------------------------------------------------
# otimizar
# ---------------------------------------------------------------------------

def test_otimizar_retorna_lista_com_uma_entrada_por_combinacao():
    dados = _gerar_dados()
    combos = gerar_combinacoes(
        ma_rapidas=[5, 7],
        ma_devagar=[20],
        rsi_sobrecomprado=[70],
        rsi_sobrevendido=[30],
        stop_pcts=[0.05],
    )
    resultados = otimizar(dados, capital_inicial=1000.0, combinacoes=combos)
    assert len(resultados) == 2


def test_otimizar_resultados_tem_todos_os_campos():
    dados = _gerar_dados()
    combos = gerar_combinacoes(
        ma_rapidas=[7], ma_devagar=[40],
        rsi_sobrecomprado=[70], rsi_sobrevendido=[30],
        stop_pcts=[0.05],
    )
    resultado = otimizar(dados, capital_inicial=1000.0, combinacoes=combos)[0]
    campos_esperados = [
        "ma_rapida", "ma_devagar", "rsi_sobrecomprado", "rsi_sobrevendido",
        "stop_pct", "lucro_total_brl", "taxa_acerto_pct",
        "drawdown_maximo_pct", "total_operacoes", "capital_final",
    ]
    for campo in campos_esperados:
        assert campo in resultado, f"Campo ausente: {campo}"


def test_otimizar_ordenado_por_lucro_decrescente():
    dados = _gerar_dados()
    combos = gerar_combinacoes(
        ma_rapidas=[5, 7, 10],
        ma_devagar=[20, 40],
        rsi_sobrecomprado=[70],
        rsi_sobrevendido=[30],
        stop_pcts=[0.05],
    )
    resultados = otimizar(dados, capital_inicial=1000.0, combinacoes=combos)
    lucros = [r["lucro_total_brl"] for r in resultados]
    assert lucros == sorted(lucros, reverse=True)


def test_otimizar_sem_combinacoes_retorna_lista_vazia():
    dados = _gerar_dados()
    resultados = otimizar(dados, capital_inicial=1000.0, combinacoes=[])
    assert resultados == []


# ---------------------------------------------------------------------------
# melhor_configuracao
# ---------------------------------------------------------------------------

def test_melhor_configuracao_retorna_primeiro_da_lista():
    resultados = [_resultado(100.0), _resultado(50.0), _resultado(-10.0)]
    melhor = melhor_configuracao(resultados)
    assert melhor["lucro_total_brl"] == pytest.approx(100.0)


def test_melhor_configuracao_lista_vazia_retorna_none():
    assert melhor_configuracao([]) is None


def test_melhor_configuracao_lista_unitaria():
    resultados = [_resultado(42.0)]
    melhor = melhor_configuracao(resultados)
    assert melhor["lucro_total_brl"] == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# salvar_configuracao / carregar_configuracao
# ---------------------------------------------------------------------------

def test_salvar_e_carregar_configuracao(tmp_path):
    arquivo = str(tmp_path / "config.json")
    config = _resultado(150.0, ma_r=5, ma_d=20, stop=0.03)
    salvar_configuracao(config, arquivo=arquivo)
    carregado = carregar_configuracao(arquivo=arquivo)
    assert carregado["ma_rapida"] == 5
    assert carregado["ma_devagar"] == 20
    assert carregado["lucro_total_brl"] == pytest.approx(150.0)


def test_salvar_configuracao_cria_arquivo(tmp_path):
    arquivo = str(tmp_path / "subdir" / "config.json")
    salvar_configuracao(_resultado(10.0), arquivo=arquivo)
    assert os.path.exists(arquivo)


def test_carregar_configuracao_retorna_none_se_nao_existe(tmp_path):
    arquivo = str(tmp_path / "nao_existe.json")
    assert carregar_configuracao(arquivo=arquivo) is None

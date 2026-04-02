import pytest
import json
import os
from reserva import (
    carregar_estado_reserva,
    registrar_lucro,
    calcular_conversao,
    registrar_conversao,
    estado_inicial,
    registrar_resultado,
    deve_converter,
    calcular_split,
    registrar_reinvestimento,
    registrar_conversao_completa,
)


# ---------------------------------------------------------------------------
# estado_inicial / carregar_estado_reserva
# ---------------------------------------------------------------------------

def test_estado_inicial_retorna_estrutura_correta():
    estado = estado_inicial()
    assert estado["lucro_acumulado_brl"] == 0.0
    assert estado["reserva_usdc"] == 0.0
    assert estado["historico_conversoes"] == []


def test_carregar_estado_reserva_cria_arquivo_se_nao_existe(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    estado = carregar_estado_reserva(arquivo)
    assert estado["lucro_acumulado_brl"] == 0.0
    assert os.path.exists(arquivo)


def test_carregar_estado_reserva_le_arquivo_existente(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    dados = {"lucro_acumulado_brl": 45.0, "reserva_usdc": 4.5, "historico_conversoes": []}
    with open(arquivo, "w") as f:
        json.dump(dados, f)

    estado = carregar_estado_reserva(arquivo)
    assert estado["lucro_acumulado_brl"] == 45.0
    assert estado["reserva_usdc"] == 4.5


# ---------------------------------------------------------------------------
# registrar_lucro
# ---------------------------------------------------------------------------

def test_registrar_lucro_acumula_valor(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    estado = registrar_lucro(lucro_brl=20.0, arquivo=arquivo)
    assert estado["lucro_acumulado_brl"] == pytest.approx(20.0)


def test_registrar_lucro_acumula_multiplas_chamadas(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_lucro(lucro_brl=15.0, arquivo=arquivo)
    estado = registrar_lucro(lucro_brl=18.0, arquivo=arquivo)
    assert estado["lucro_acumulado_brl"] == pytest.approx(33.0)


def test_registrar_lucro_negativo_nao_acumula(tmp_path):
    """Prejuízo não desconta do acumulado (já foi absorvido na operação)."""
    arquivo = str(tmp_path / "reserva.json")
    registrar_lucro(lucro_brl=25.0, arquivo=arquivo)
    estado = registrar_lucro(lucro_brl=-10.0, arquivo=arquivo)
    assert estado["lucro_acumulado_brl"] == pytest.approx(25.0)


def test_registrar_lucro_persiste_no_arquivo(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_lucro(lucro_brl=22.0, arquivo=arquivo)

    with open(arquivo) as f:
        dados = json.load(f)
    assert dados["lucro_acumulado_brl"] == pytest.approx(22.0)


# ---------------------------------------------------------------------------
# calcular_conversao
# ---------------------------------------------------------------------------

def test_conversao_zero_abaixo_do_minimo():
    valor = calcular_conversao(lucro_acumulado_brl=29.99)
    assert valor == 0.0


def test_conversao_50_pct_quando_atinge_minimo():
    valor = calcular_conversao(lucro_acumulado_brl=30.0)
    assert valor == pytest.approx(15.0)


def test_conversao_50_pct_com_lucro_maior():
    valor = calcular_conversao(lucro_acumulado_brl=80.0)
    assert valor == pytest.approx(40.0)


def test_conversao_percentual_customizavel():
    valor = calcular_conversao(lucro_acumulado_brl=100.0, percentual=0.3)
    assert valor == pytest.approx(30.0)


def test_conversao_minimo_customizavel():
    valor = calcular_conversao(lucro_acumulado_brl=20.0, minimo=50.0)
    assert valor == 0.0

    valor = calcular_conversao(lucro_acumulado_brl=50.0, minimo=50.0)
    assert valor == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# registrar_conversao
# ---------------------------------------------------------------------------

def test_registrar_conversao_atualiza_reserva_usdc(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_lucro(30.0, arquivo=arquivo)
    estado = registrar_conversao(
        valor_brl=15.0,
        valor_usdc=2.9,
        taxa_cambio=5.17,
        timestamp="2026-03-28 10:00:00",
        arquivo=arquivo,
    )
    assert estado["reserva_usdc"] == pytest.approx(2.9)


def test_registrar_conversao_desconta_lucro_acumulado(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_lucro(50.0, arquivo=arquivo)
    estado = registrar_conversao(
        valor_brl=25.0,
        valor_usdc=4.83,
        taxa_cambio=5.17,
        timestamp="2026-03-28 10:00:00",
        arquivo=arquivo,
    )
    assert estado["lucro_acumulado_brl"] == pytest.approx(25.0)


def test_registrar_conversao_acumula_reserva_usdc(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_lucro(100.0, arquivo=arquivo)
    registrar_conversao(50.0, 9.67, 5.17, "2026-03-28 10:00:00", arquivo=arquivo)
    registrar_lucro(60.0, arquivo=arquivo)
    estado = registrar_conversao(30.0, 5.8, 5.17, "2026-03-29 10:00:00", arquivo=arquivo)
    assert estado["reserva_usdc"] == pytest.approx(9.67 + 5.8)


def test_registrar_conversao_adiciona_historico(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_lucro(30.0, arquivo=arquivo)
    estado = registrar_conversao(15.0, 2.9, 5.17, "2026-03-28 10:00:00", arquivo=arquivo)
    assert len(estado["historico_conversoes"]) == 1
    h = estado["historico_conversoes"][0]
    assert h["valor_brl"] == pytest.approx(15.0)
    assert h["valor_usdc"] == pytest.approx(2.9)
    assert h["taxa_cambio"] == pytest.approx(5.17)
    assert h["timestamp"] == "2026-03-28 10:00:00"


def test_registrar_conversao_persiste_no_arquivo(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_lucro(30.0, arquivo=arquivo)
    registrar_conversao(15.0, 2.9, 5.17, "2026-03-28 10:00:00", arquivo=arquivo)

    with open(arquivo) as f:
        dados = json.load(f)
    assert dados["reserva_usdc"] == pytest.approx(2.9)
    assert len(dados["historico_conversoes"]) == 1


# ---------------------------------------------------------------------------
# registrar_resultado — net P&L (positivo e negativo)
# ---------------------------------------------------------------------------

def test_registrar_resultado_positivo_acumula(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    estado = registrar_resultado(15.0, arquivo=arquivo)
    assert estado["pnl_liquido_pendente_brl"] == pytest.approx(15.0)


def test_registrar_resultado_negativo_desconta(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_resultado(20.0, arquivo=arquivo)
    estado = registrar_resultado(-8.0, arquivo=arquivo)
    assert estado["pnl_liquido_pendente_brl"] == pytest.approx(12.0)


def test_registrar_resultado_pode_ficar_negativo(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_resultado(5.0, arquivo=arquivo)
    estado = registrar_resultado(-20.0, arquivo=arquivo)
    assert estado["pnl_liquido_pendente_brl"] == pytest.approx(-15.0)


def test_registrar_resultado_acumula_multiplas_chamadas(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_resultado(10.0, arquivo=arquivo)
    registrar_resultado(15.0, arquivo=arquivo)
    estado = registrar_resultado(-5.0, arquivo=arquivo)
    assert estado["pnl_liquido_pendente_brl"] == pytest.approx(20.0)


def test_registrar_resultado_persiste(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_resultado(25.0, arquivo=arquivo)
    with open(arquivo) as f:
        dados = json.load(f)
    assert dados["pnl_liquido_pendente_brl"] == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# deve_converter — condições para disparar conversão
# ---------------------------------------------------------------------------

def test_deve_converter_true_quando_todas_condicoes_ok():
    assert deve_converter(pnl_liquido=50.0, portfolio_brl=1700.0, capital_investido=1672.0) is True


def test_deve_converter_false_pnl_abaixo_minimo():
    assert deve_converter(pnl_liquido=20.0, portfolio_brl=1700.0, capital_investido=1672.0) is False


def test_deve_converter_false_portfolio_menor_que_investido():
    assert deve_converter(pnl_liquido=50.0, portfolio_brl=1650.0, capital_investido=1672.0) is False


def test_deve_converter_false_portfolio_igual_ao_investido():
    assert deve_converter(pnl_liquido=50.0, portfolio_brl=1672.0, capital_investido=1672.0) is False


def test_deve_converter_false_pnl_negativo():
    assert deve_converter(pnl_liquido=-10.0, portfolio_brl=1700.0, capital_investido=1672.0) is False


def test_deve_converter_minimo_customizavel():
    assert deve_converter(pnl_liquido=25.0, portfolio_brl=1700.0, capital_investido=1672.0, minimo=25.0) is True
    assert deve_converter(pnl_liquido=24.99, portfolio_brl=1700.0, capital_investido=1672.0, minimo=25.0) is False


# ---------------------------------------------------------------------------
# calcular_split — divisão 50/50 do P&L
# ---------------------------------------------------------------------------

def test_calcular_split_divide_igualmente():
    resultado = calcular_split(60.0)
    assert resultado["usdc_brl"] == pytest.approx(30.0)
    assert resultado["reinvest_brl"] == pytest.approx(30.0)


def test_calcular_split_valor_impar():
    resultado = calcular_split(31.0)
    assert resultado["usdc_brl"] == pytest.approx(15.5)
    assert resultado["reinvest_brl"] == pytest.approx(15.5)


def test_calcular_split_soma_igual_ao_total():
    pnl = 47.38
    resultado = calcular_split(pnl)
    assert resultado["usdc_brl"] + resultado["reinvest_brl"] == pytest.approx(pnl)


# ---------------------------------------------------------------------------
# registrar_reinvestimento — adiciona aporte automático em aportes.json
# ---------------------------------------------------------------------------

def test_registrar_reinvestimento_cria_aporte(tmp_path):
    arquivo_aportes = str(tmp_path / "aportes.json")
    with open(arquivo_aportes, "w") as f:
        json.dump({"confirmados": [], "rejeitados": []}, f)

    registrar_reinvestimento(30.0, "2026-04-01", arquivo_aportes=arquivo_aportes)

    with open(arquivo_aportes) as f:
        dados = json.load(f)
    assert len(dados["confirmados"]) == 1
    a = dados["confirmados"][0]
    assert a["valor_brl"] == pytest.approx(30.0)
    assert a["fonte"] == "lucro_reinvestido"
    assert a["data"] == "2026-04-01"


def test_registrar_reinvestimento_preserva_aportes_existentes(tmp_path):
    arquivo_aportes = str(tmp_path / "aportes.json")
    with open(arquivo_aportes, "w") as f:
        json.dump({"confirmados": [{"data": "2026-03-28", "valor_brl": 1672.05, "fonte": "manual"}], "rejeitados": []}, f)

    registrar_reinvestimento(30.0, "2026-04-01", arquivo_aportes=arquivo_aportes)

    with open(arquivo_aportes) as f:
        dados = json.load(f)
    assert len(dados["confirmados"]) == 2
    assert dados["confirmados"][0]["valor_brl"] == pytest.approx(1672.05)
    assert dados["confirmados"][1]["valor_brl"] == pytest.approx(30.0)


def test_registrar_reinvestimento_arquivo_inexistente_nao_quebra(tmp_path):
    arquivo_aportes = str(tmp_path / "aportes.json")
    # arquivo não existe ainda
    registrar_reinvestimento(30.0, "2026-04-01", arquivo_aportes=arquivo_aportes)
    with open(arquivo_aportes) as f:
        dados = json.load(f)
    assert len(dados["confirmados"]) == 1


# ---------------------------------------------------------------------------
# registrar_conversao_completa — transação completa 50/50
# ---------------------------------------------------------------------------

def test_registrar_conversao_completa_zera_pnl_pendente(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_resultado(60.0, arquivo=arquivo)
    estado = registrar_conversao_completa(
        valor_usdc_brl=30.0,
        valor_reinvest_brl=30.0,
        valor_usdc=5.78,
        taxa_cambio=5.19,
        timestamp="2026-04-01 10:00:00",
        arquivo=arquivo,
    )
    assert estado["pnl_liquido_pendente_brl"] == pytest.approx(0.0)


def test_registrar_conversao_completa_atualiza_reserva_usdc(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_resultado(60.0, arquivo=arquivo)
    estado = registrar_conversao_completa(
        valor_usdc_brl=30.0, valor_reinvest_brl=30.0,
        valor_usdc=5.78, taxa_cambio=5.19,
        timestamp="2026-04-01 10:00:00", arquivo=arquivo,
    )
    assert estado["reserva_usdc"] == pytest.approx(5.78)


def test_registrar_conversao_completa_acumula_capital_reinvestido(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_resultado(60.0, arquivo=arquivo)
    estado = registrar_conversao_completa(
        valor_usdc_brl=30.0, valor_reinvest_brl=30.0,
        valor_usdc=5.78, taxa_cambio=5.19,
        timestamp="2026-04-01 10:00:00", arquivo=arquivo,
    )
    assert estado["capital_reinvestido_brl"] == pytest.approx(30.0)


def test_registrar_conversao_completa_historico(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_resultado(60.0, arquivo=arquivo)
    estado = registrar_conversao_completa(
        valor_usdc_brl=30.0, valor_reinvest_brl=30.0,
        valor_usdc=5.78, taxa_cambio=5.19,
        timestamp="2026-04-01 10:00:00", arquivo=arquivo,
    )
    assert len(estado["historico_conversoes"]) == 1
    h = estado["historico_conversoes"][0]
    assert h["valor_usdc_brl"] == pytest.approx(30.0)
    assert h["valor_reinvest_brl"] == pytest.approx(30.0)
    assert h["valor_usdc"] == pytest.approx(5.78)
    assert h["timestamp"] == "2026-04-01 10:00:00"


def test_registrar_conversao_completa_acumula_multiplas(tmp_path):
    arquivo = str(tmp_path / "reserva.json")
    registrar_resultado(60.0, arquivo=arquivo)
    registrar_conversao_completa(30.0, 30.0, 5.78, 5.19, "2026-04-01 10:00:00", arquivo=arquivo)
    registrar_resultado(60.0, arquivo=arquivo)
    estado = registrar_conversao_completa(30.0, 30.0, 5.80, 5.19, "2026-04-02 10:00:00", arquivo=arquivo)
    assert estado["reserva_usdc"] == pytest.approx(5.78 + 5.80)
    assert estado["capital_reinvestido_brl"] == pytest.approx(60.0)
    assert len(estado["historico_conversoes"]) == 2

import pytest
import json
import os
from reserva import (
    carregar_estado_reserva,
    registrar_lucro,
    calcular_conversao,
    registrar_conversao,
    estado_inicial,
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

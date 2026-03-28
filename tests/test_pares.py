import pytest
from pares import (
    listar_pares,
    arquivo_posicao,
    calcular_saldo_disponivel,
    pares_sem_posicao,
    consolidar_resumo,
)


# ---------------------------------------------------------------------------
# listar_pares
# ---------------------------------------------------------------------------

def test_listar_pares_retorna_solbrl_btcbrl_ethbrl():
    pares = listar_pares()
    simbolos = [p["simbolo"] for p in pares]
    assert "SOLBRL" in simbolos
    assert "BTCBRL" in simbolos
    assert "ETHBRL" in simbolos


def test_listar_pares_campos_obrigatorios():
    for par in listar_pares():
        assert "simbolo" in par
        assert "ativo" in par
        assert "step_size" in par


def test_listar_pares_step_sizes_corretos():
    pares = {p["simbolo"]: p for p in listar_pares()}
    assert pares["SOLBRL"]["step_size"] == "0.001"
    assert pares["BTCBRL"]["step_size"] == "0.00001"
    assert pares["ETHBRL"]["step_size"] == "0.0001"


# ---------------------------------------------------------------------------
# arquivo_posicao
# ---------------------------------------------------------------------------

def test_arquivo_posicao_inclui_simbolo():
    assert "SOLBRL" in arquivo_posicao("SOLBRL")
    assert "BTCBRL" in arquivo_posicao("BTCBRL")


def test_arquivo_posicao_extensao_json():
    assert arquivo_posicao("SOLBRL").endswith(".json")


def test_arquivo_posicao_pares_diferentes_geram_arquivos_diferentes():
    assert arquivo_posicao("SOLBRL") != arquivo_posicao("BTCBRL")


# ---------------------------------------------------------------------------
# calcular_saldo_disponivel — teto de 60% por par
# ---------------------------------------------------------------------------

def test_saldo_disponivel_60pct_padrao():
    disponivel = calcular_saldo_disponivel(saldo_brl=1000.0)
    assert disponivel == pytest.approx(600.0)


def test_saldo_disponivel_respeita_teto_pct():
    disponivel = calcular_saldo_disponivel(saldo_brl=1000.0, teto_pct=0.40)
    assert disponivel == pytest.approx(400.0)


def test_saldo_disponivel_saldo_zero_retorna_zero():
    assert calcular_saldo_disponivel(saldo_brl=0.0) == 0.0


def test_saldo_disponivel_reflete_brl_disponivel_atual():
    """Após SOL comprar R$600, sobram R$400. BTC pode usar até 60% de R$400 = R$240."""
    disponivel_apos_sol = calcular_saldo_disponivel(saldo_brl=400.0)
    assert disponivel_apos_sol == pytest.approx(240.0)


def test_saldo_disponivel_teto_pct_customizado():
    disponivel = calcular_saldo_disponivel(saldo_brl=500.0, teto_pct=0.5)
    assert disponivel == pytest.approx(250.0)


# ---------------------------------------------------------------------------
# pares_sem_posicao
# ---------------------------------------------------------------------------

def test_pares_sem_posicao_todos_livres():
    estados = {
        "SOLBRL": {"posicao": False},
        "BTCBRL": {"posicao": False},
        "ETHBRL": {"posicao": False},
    }
    livres = pares_sem_posicao(estados)
    assert set(livres) == {"SOLBRL", "BTCBRL", "ETHBRL"}


def test_pares_sem_posicao_um_comprado():
    estados = {
        "SOLBRL": {"posicao": True},
        "BTCBRL": {"posicao": False},
        "ETHBRL": {"posicao": False},
    }
    livres = pares_sem_posicao(estados)
    assert "SOLBRL" not in livres
    assert "BTCBRL" in livres
    assert "ETHBRL" in livres


def test_pares_sem_posicao_todos_comprados():
    estados = {
        "SOLBRL": {"posicao": True},
        "BTCBRL": {"posicao": True},
        "ETHBRL": {"posicao": True},
    }
    assert pares_sem_posicao(estados) == []


def test_pares_sem_posicao_dicionario_vazio():
    assert pares_sem_posicao({}) == []


# ---------------------------------------------------------------------------
# consolidar_resumo
# ---------------------------------------------------------------------------

def test_consolidar_resumo_sem_pares():
    resumo = consolidar_resumo([])
    assert resumo["total_operacoes"] == 0
    assert resumo["lucro_total_brl"] == 0.0
    assert resumo["taxa_acerto_pct"] == 0.0


def test_consolidar_resumo_um_par():
    resumos = [
        {"par": "SOLBRL", "total_operacoes": 3, "operacoes_lucrativas": 2,
         "lucro_total_brl": 45.0, "taxa_acerto_pct": 66.7},
    ]
    resumo = consolidar_resumo(resumos)
    assert resumo["total_operacoes"] == 3
    assert resumo["lucro_total_brl"] == pytest.approx(45.0)
    assert resumo["taxa_acerto_pct"] == pytest.approx(66.7, abs=0.1)


def test_consolidar_resumo_multiplos_pares_soma_operacoes():
    resumos = [
        {"par": "SOLBRL", "total_operacoes": 3, "operacoes_lucrativas": 2, "lucro_total_brl": 45.0},
        {"par": "BTCBRL", "total_operacoes": 2, "operacoes_lucrativas": 1, "lucro_total_brl": -10.0},
        {"par": "ETHBRL", "total_operacoes": 1, "operacoes_lucrativas": 1, "lucro_total_brl": 20.0},
    ]
    resumo = consolidar_resumo(resumos)
    assert resumo["total_operacoes"] == 6
    assert resumo["lucro_total_brl"] == pytest.approx(55.0)
    assert resumo["operacoes_lucrativas"] == 4
    assert resumo["taxa_acerto_pct"] == pytest.approx(4 / 6 * 100, abs=0.1)


def test_consolidar_resumo_inclui_breakdown_por_par():
    resumos = [
        {"par": "SOLBRL", "total_operacoes": 3, "operacoes_lucrativas": 2, "lucro_total_brl": 45.0},
        {"par": "BTCBRL", "total_operacoes": 1, "operacoes_lucrativas": 0, "lucro_total_brl": -5.0},
    ]
    resumo = consolidar_resumo(resumos)
    assert "por_par" in resumo
    assert "SOLBRL" in resumo["por_par"]
    assert "BTCBRL" in resumo["por_par"]
    assert resumo["por_par"]["SOLBRL"]["lucro_total_brl"] == pytest.approx(45.0)


def test_consolidar_resumo_taxa_acerto_zero_operacoes():
    resumos = [
        {"par": "SOLBRL", "total_operacoes": 0, "operacoes_lucrativas": 0, "lucro_total_brl": 0.0},
    ]
    resumo = consolidar_resumo(resumos)
    assert resumo["taxa_acerto_pct"] == 0.0

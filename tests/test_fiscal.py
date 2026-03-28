import pytest
import csv
import json
import os
from fiscal import (
    carregar_stats_do_mes,
    calcular_resumo_mensal,
    calcular_imposto,
    exportar_csv_mensal,
    verificar_alerta_volume,
)


def _criar_stats_dia(tmp_path, data: str, operacoes: list) -> str:
    """Helper: cria um arquivo stats/YYYY-MM-DD.json para testes."""
    arquivo = str(tmp_path / f"{data}.json")
    dados = {
        "data": data,
        "saldo_inicial_brl": 1000.0,
        "operacoes": operacoes,
    }
    with open(arquivo, "w") as f:
        json.dump(dados, f)
    return arquivo


# ---------------------------------------------------------------------------
# carregar_stats_do_mes
# ---------------------------------------------------------------------------

def test_carregar_stats_do_mes_retorna_lista(tmp_path):
    _criar_stats_dia(tmp_path, "2026-03-01", [])
    _criar_stats_dia(tmp_path, "2026-03-15", [])
    _criar_stats_dia(tmp_path, "2026-04-01", [])  # outro mês — deve ser ignorado

    stats = carregar_stats_do_mes("2026-03", diretorio=str(tmp_path))
    assert len(stats) == 2


def test_carregar_stats_do_mes_sem_arquivos_retorna_lista_vazia(tmp_path):
    stats = carregar_stats_do_mes("2026-03", diretorio=str(tmp_path))
    assert stats == []


def test_carregar_stats_do_mes_ordena_por_data(tmp_path):
    _criar_stats_dia(tmp_path, "2026-03-20", [])
    _criar_stats_dia(tmp_path, "2026-03-01", [])
    _criar_stats_dia(tmp_path, "2026-03-10", [])

    stats = carregar_stats_do_mes("2026-03", diretorio=str(tmp_path))
    datas = [s["data"] for s in stats]
    assert datas == sorted(datas)


# ---------------------------------------------------------------------------
# calcular_imposto
# ---------------------------------------------------------------------------

def test_imposto_zero_quando_volume_abaixo_isencao():
    # Vendas totais < R$35.000 → isento
    imposto = calcular_imposto(lucro_total_brl=500.0, volume_vendas_brl=20000.0)
    assert imposto == 0.0


def test_imposto_zero_quando_lucro_negativo_acima_isencao():
    # Prejuízo mesmo com volume alto → sem imposto
    imposto = calcular_imposto(lucro_total_brl=-200.0, volume_vendas_brl=40000.0)
    assert imposto == 0.0


def test_imposto_15_pct_quando_volume_acima_isencao():
    # Volume > R$35.000 e lucro positivo → 15% sobre o lucro
    imposto = calcular_imposto(lucro_total_brl=1000.0, volume_vendas_brl=40000.0)
    assert imposto == pytest.approx(150.0)


def test_imposto_exatamente_no_limite_de_isencao():
    # Exatamente R$35.000 em vendas → ainda isento (limite exclusivo)
    imposto = calcular_imposto(lucro_total_brl=500.0, volume_vendas_brl=35000.0)
    assert imposto == 0.0


def test_imposto_um_centavo_acima_do_limite():
    imposto = calcular_imposto(lucro_total_brl=500.0, volume_vendas_brl=35000.01)
    assert imposto == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# calcular_resumo_mensal
# ---------------------------------------------------------------------------

def test_resumo_mensal_sem_operacoes(tmp_path):
    stats_list = [
        {"data": "2026-03-01", "saldo_inicial_brl": 1000.0, "operacoes": []},
        {"data": "2026-03-02", "saldo_inicial_brl": 1000.0, "operacoes": []},
    ]
    resumo = calcular_resumo_mensal(stats_list)
    assert resumo["total_operacoes"] == 0
    assert resumo["volume_vendas_brl"] == 0.0
    assert resumo["lucro_total_brl"] == 0.0
    assert resumo["imposto_devido_brl"] == 0.0


def test_resumo_mensal_com_lucro_abaixo_isencao(tmp_path):
    operacoes_dia1 = [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "timestamp": "2026-03-01 09:00:00"},
        {"tipo": "VENDA", "preco": 460.0, "quantidade": 2.0, "total_brl": 920.0, "lucro_brl": 40.0, "lucro_pct": 4.5, "timestamp": "2026-03-01 15:00:00"},
    ]
    stats_list = [{"data": "2026-03-01", "saldo_inicial_brl": 1000.0, "operacoes": operacoes_dia1}]
    resumo = calcular_resumo_mensal(stats_list)

    assert resumo["total_operacoes"] == 1  # conta ciclos completos (vendas)
    assert resumo["volume_vendas_brl"] == pytest.approx(920.0)
    assert resumo["lucro_total_brl"] == pytest.approx(40.0)
    assert resumo["imposto_devido_brl"] == 0.0  # abaixo do limite de isenção


def test_resumo_mensal_com_volume_acima_isencao():
    # Simula mês com muitas operações passando de R$35k em vendas
    operacoes = []
    for i in range(40):
        operacoes.append({
            "tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0,
            "total_brl": 880.0, "timestamp": f"2026-03-{(i % 28) + 1:02d} 09:00:00"
        })
        operacoes.append({
            "tipo": "VENDA", "preco": 460.0, "quantidade": 2.0,
            "total_brl": 920.0, "lucro_brl": 40.0, "lucro_pct": 4.5,
            "timestamp": f"2026-03-{(i % 28) + 1:02d} 15:00:00"
        })

    stats_list = [{"data": "2026-03-01", "saldo_inicial_brl": 1000.0, "operacoes": operacoes}]
    resumo = calcular_resumo_mensal(stats_list)

    assert resumo["volume_vendas_brl"] == pytest.approx(40 * 920.0)  # 36.800
    assert resumo["lucro_total_brl"] == pytest.approx(40 * 40.0)  # 1.600
    assert resumo["imposto_devido_brl"] == pytest.approx(40 * 40.0 * 0.15)  # 15% do lucro


def test_resumo_mensal_agrega_multiplos_dias():
    dia1 = [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "timestamp": "09:00"},
        {"tipo": "VENDA", "preco": 460.0, "quantidade": 2.0, "total_brl": 920.0, "lucro_brl": 40.0, "lucro_pct": 4.5, "timestamp": "15:00"},
    ]
    dia2 = [
        {"tipo": "COMPRA", "preco": 450.0, "quantidade": 2.0, "total_brl": 900.0, "timestamp": "09:00"},
        {"tipo": "VENDA", "preco": 470.0, "quantidade": 2.0, "total_brl": 940.0, "lucro_brl": 40.0, "lucro_pct": 4.4, "timestamp": "15:00"},
    ]
    stats_list = [
        {"data": "2026-03-01", "saldo_inicial_brl": 1000.0, "operacoes": dia1},
        {"data": "2026-03-02", "saldo_inicial_brl": 1000.0, "operacoes": dia2},
    ]
    resumo = calcular_resumo_mensal(stats_list)
    assert resumo["total_operacoes"] == 2
    assert resumo["volume_vendas_brl"] == pytest.approx(920.0 + 940.0)
    assert resumo["lucro_total_brl"] == pytest.approx(80.0)


def test_resumo_mensal_inclui_taxa_acerto():
    operacoes = [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "timestamp": "09:00"},
        {"tipo": "VENDA", "preco": 460.0, "quantidade": 2.0, "total_brl": 920.0, "lucro_brl": 40.0, "lucro_pct": 4.5, "timestamp": "10:00"},
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "timestamp": "11:00"},
        {"tipo": "VENDA", "preco": 420.0, "quantidade": 2.0, "total_brl": 840.0, "lucro_brl": -40.0, "lucro_pct": -4.5, "timestamp": "12:00"},
    ]
    stats_list = [{"data": "2026-03-01", "saldo_inicial_brl": 1000.0, "operacoes": operacoes}]
    resumo = calcular_resumo_mensal(stats_list)
    assert resumo["total_operacoes"] == 2
    assert resumo["taxa_acerto_pct"] == 50.0


# ---------------------------------------------------------------------------
# verificar_alerta_volume
# ---------------------------------------------------------------------------

def test_alerta_volume_nao_disparado_abaixo_80pct():
    assert verificar_alerta_volume(volume_atual=27000.0) is False


def test_alerta_volume_disparado_em_80pct():
    assert verificar_alerta_volume(volume_atual=28000.0) is True  # 28000/35000 = 80%


def test_alerta_volume_disparado_acima_limite():
    assert verificar_alerta_volume(volume_atual=40000.0) is True


def test_alerta_volume_limite_customizavel():
    assert verificar_alerta_volume(volume_atual=8000.0, limite=10000.0, pct_alerta=0.8) is True
    assert verificar_alerta_volume(volume_atual=7000.0, limite=10000.0, pct_alerta=0.8) is False


# ---------------------------------------------------------------------------
# exportar_csv_mensal
# ---------------------------------------------------------------------------

def test_exportar_csv_cria_arquivo(tmp_path):
    operacoes = [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.0, "total_brl": 880.0, "timestamp": "2026-03-01 09:00:00"},
        {"tipo": "VENDA", "preco": 460.0, "quantidade": 2.0, "total_brl": 920.0, "lucro_brl": 40.0, "lucro_pct": 4.5, "timestamp": "2026-03-01 15:00:00"},
    ]
    stats_list = [{"data": "2026-03-01", "saldo_inicial_brl": 1000.0, "operacoes": operacoes}]
    arquivo = str(tmp_path / "relatorio_2026-03.csv")

    caminho = exportar_csv_mensal(stats_list, arquivo=arquivo)
    assert os.path.exists(caminho)


def test_exportar_csv_contem_cabecalho_e_linhas(tmp_path):
    operacoes = [
        {"tipo": "COMPRA", "preco": 440.0, "quantidade": 2.045, "total_brl": 900.0, "timestamp": "2026-03-01 09:00:00"},
        {"tipo": "VENDA", "preco": 460.0, "quantidade": 2.045, "total_brl": 940.0, "lucro_brl": 40.0, "lucro_pct": 4.4, "timestamp": "2026-03-01 15:00:00"},
    ]
    stats_list = [{"data": "2026-03-01", "saldo_inicial_brl": 1000.0, "operacoes": operacoes}]
    arquivo = str(tmp_path / "relatorio_2026-03.csv")

    exportar_csv_mensal(stats_list, arquivo=arquivo)

    with open(arquivo, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    assert len(reader) == 2
    assert reader[0]["tipo"] == "COMPRA"
    assert reader[1]["tipo"] == "VENDA"
    assert float(reader[1]["lucro_brl"]) == pytest.approx(40.0)


def test_exportar_csv_sem_operacoes_cria_arquivo_vazio(tmp_path):
    stats_list = [{"data": "2026-03-01", "saldo_inicial_brl": 1000.0, "operacoes": []}]
    arquivo = str(tmp_path / "relatorio_2026-03.csv")

    exportar_csv_mensal(stats_list, arquivo=arquivo)

    with open(arquivo, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    assert reader == []


def test_exportar_csv_retorna_caminho_do_arquivo(tmp_path):
    arquivo = str(tmp_path / "relatorio.csv")
    caminho = exportar_csv_mensal([], arquivo=arquivo)
    assert caminho == arquivo

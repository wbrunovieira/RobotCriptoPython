"""Cálculos fiscais e exportação de relatórios mensais."""
import csv
import json
import os
from glob import glob

LIMITE_ISENCAO_BRL = 35_000.0
PCT_ALERTA_PADRAO = 0.80
ALIQUOTA_IR = 0.15
CSV_CAMPOS = ["data", "tipo", "par", "preco", "quantidade", "total_brl", "lucro_brl", "lucro_pct", "timestamp"]


def carregar_stats_do_mes(ano_mes: str, diretorio: str = "stats") -> list:
    """Carrega todos os arquivos de stats do mês informado (formato 'YYYY-MM')."""
    padrao = os.path.join(diretorio, f"{ano_mes}-*.json")
    arquivos = sorted(glob(padrao))
    resultado = []
    for arq in arquivos:
        with open(arq, "r", encoding="utf-8") as f:
            resultado.append(json.load(f))
    return resultado


def calcular_imposto(lucro_total_brl: float, volume_vendas_brl: float) -> float:
    """Calcula imposto devido conforme regra brasileira de cripto:
    - Isento se volume mensal de vendas <= R$35.000
    - 15% sobre o lucro se volume > R$35.000 (e lucro positivo)
    """
    if volume_vendas_brl <= LIMITE_ISENCAO_BRL:
        return 0.0
    if lucro_total_brl <= 0:
        return 0.0
    return round(lucro_total_brl * ALIQUOTA_IR, 2)


def calcular_resumo_mensal(stats_list: list) -> dict:
    """Agrega todas as operações do mês e retorna resumo fiscal."""
    vendas = []
    for stats in stats_list:
        for op in stats.get("operacoes", []):
            if op["tipo"] == "VENDA":
                vendas.append(op)

    if not vendas:
        return {
            "total_operacoes": 0,
            "operacoes_lucrativas": 0,
            "volume_vendas_brl": 0.0,
            "lucro_total_brl": 0.0,
            "maior_ganho": 0.0,
            "maior_perda": 0.0,
            "taxa_acerto_pct": 0.0,
            "imposto_devido_brl": 0.0,
        }

    volume_vendas = sum(v["total_brl"] for v in vendas)
    lucros = [v.get("lucro_brl", 0.0) for v in vendas]
    lucro_total = round(sum(lucros), 2)
    lucrativas = [l for l in lucros if l > 0]
    taxa_acerto = round(len(lucrativas) / len(vendas) * 100, 1) if vendas else 0.0

    return {
        "total_operacoes": len(vendas),
        "operacoes_lucrativas": len(lucrativas),
        "volume_vendas_brl": round(volume_vendas, 2),
        "lucro_total_brl": lucro_total,
        "maior_ganho": max(lucros) if lucros else 0.0,
        "maior_perda": min(lucros) if min(lucros) < 0 else 0.0,
        "taxa_acerto_pct": taxa_acerto,
        "imposto_devido_brl": calcular_imposto(lucro_total, volume_vendas),
    }


def verificar_alerta_volume(
    volume_atual: float,
    limite: float = LIMITE_ISENCAO_BRL,
    pct_alerta: float = PCT_ALERTA_PADRAO,
) -> bool:
    """Retorna True se o volume atual atingiu ou superou pct_alerta do limite de isenção."""
    return volume_atual >= limite * pct_alerta


def exportar_csv_mensal(stats_list: list, arquivo: str = None, par: str = "SOLBRL") -> str:
    """Exporta todas as operações do mês em CSV para declaração do IR."""
    if arquivo is None:
        os.makedirs("relatorios", exist_ok=True)
        arquivo = "relatorios/relatorio_fiscal.csv"

    linhas = []
    for stats in stats_list:
        data = stats.get("data", "")
        for op in stats.get("operacoes", []):
            linhas.append({
                "data": data,
                "tipo": op.get("tipo", ""),
                "par": par,
                "preco": op.get("preco", ""),
                "quantidade": op.get("quantidade", ""),
                "total_brl": op.get("total_brl", ""),
                "lucro_brl": op.get("lucro_brl", ""),
                "lucro_pct": op.get("lucro_pct", ""),
                "timestamp": op.get("timestamp", ""),
            })

    os.makedirs(os.path.dirname(arquivo) or ".", exist_ok=True)
    with open(arquivo, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_CAMPOS)
        writer.writeheader()
        writer.writerows(linhas)

    return arquivo

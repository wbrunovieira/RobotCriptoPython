import json
import os
from datetime import date


def _caminho_padrao():
    hoje = date.today().strftime("%Y-%m-%d")
    os.makedirs("stats", exist_ok=True)
    return f"stats/{hoje}.json"


def _salvar(dados: dict, arquivo: str):
    os.makedirs(os.path.dirname(arquivo) or ".", exist_ok=True)
    with open(arquivo, "w") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def _carregar(arquivo: str) -> dict:
    with open(arquivo, "r") as f:
        return json.load(f)


def iniciar_stats_do_dia(
    saldo_inicial_brl: float,
    arquivo: str = None,
    parametros: dict = None,
) -> dict:
    """Cria o arquivo de stats do dia. Se já existir, retorna sem sobrescrever."""
    if arquivo is None:
        arquivo = _caminho_padrao()
    if os.path.exists(arquivo):
        return _carregar(arquivo)
    hoje = date.today().strftime("%Y-%m-%d")
    dados = {
        "data": hoje,
        "saldo_inicial_brl": saldo_inicial_brl,
        "parametros": parametros or {},
        "operacoes": [],
    }
    _salvar(dados, arquivo)
    return dados


def registrar_compra(
    preco: float,
    quantidade: float,
    total_brl: float,
    timestamp: str,
    arquivo: str = None,
    par: str = None,
    bot_id: str = None,
    order_id: str = None,
) -> dict:
    """Registra uma operação de compra no stats do dia."""
    if arquivo is None:
        arquivo = _caminho_padrao()
    dados = _carregar(arquivo)
    op = {
        "tipo": "COMPRA",
        "preco": preco,
        "quantidade": quantidade,
        "total_brl": total_brl,
        "timestamp": timestamp,
    }
    if par:
        op["par"] = par
    if bot_id:
        op["bot_id"] = bot_id
    if order_id:
        op["order_id"] = order_id
    dados["operacoes"].append(op)
    _salvar(dados, arquivo)
    return dados


def registrar_venda(
    preco: float,
    quantidade: float,
    total_brl: float,
    preco_entrada: float,
    timestamp: str,
    arquivo: str = None,
    par: str = None,
    bot_id: str = None,
    order_id: str = None,
) -> dict:
    """Registra uma operação de venda com cálculo de lucro/prejuízo."""
    if arquivo is None:
        arquivo = _caminho_padrao()
    dados = _carregar(arquivo)

    custo_brl = next(
        (op["total_brl"] for op in reversed(dados["operacoes"])
         if op["tipo"] == "COMPRA" and (par is None or op.get("par") == par)),
        preco_entrada * quantidade if preco_entrada else total_brl,
    )
    lucro_brl = round(total_brl - custo_brl, 2)
    lucro_pct = round((lucro_brl / custo_brl) * 100, 2) if custo_brl else 0.0

    op = {
        "tipo": "VENDA",
        "preco": preco,
        "quantidade": quantidade,
        "total_brl": total_brl,
        "lucro_brl": lucro_brl,
        "lucro_pct": lucro_pct,
        "timestamp": timestamp,
    }
    if par:
        op["par"] = par
    if bot_id:
        op["bot_id"] = bot_id
    if order_id:
        op["order_id"] = order_id
    dados["operacoes"].append(op)
    _salvar(dados, arquivo)
    return dados


def carregar_stats_do_dia(arquivo: str = None) -> dict | None:
    """Carrega os stats do dia atual. Retorna None se não existir."""
    if arquivo is None:
        arquivo = _caminho_padrao()
    if not os.path.exists(arquivo):
        return None
    return _carregar(arquivo)


def calcular_resumo(stats: dict) -> dict:
    """Calcula resumo das operações: acerto, lucro total, maior ganho/perda."""
    vendas = [op for op in stats["operacoes"] if op["tipo"] == "VENDA"]

    if not vendas:
        return {
            "total_operacoes": 0,
            "operacoes_lucrativas": 0,
            "lucro_total_brl": 0.0,
            "maior_ganho": 0.0,
            "maior_perda": 0.0,
            "taxa_acerto_pct": 0.0,
        }

    lucrativas = [v for v in vendas if v["lucro_brl"] > 0]
    lucros = [v["lucro_brl"] for v in vendas]

    return {
        "total_operacoes": len(vendas),
        "operacoes_lucrativas": len(lucrativas),
        "lucro_total_brl": round(sum(lucros), 2),
        "maior_ganho": max(lucros),
        "maior_perda": min(lucros) if min(lucros) < 0 else 0.0,
        "taxa_acerto_pct": round(len(lucrativas) / len(vendas) * 100, 1),
    }

import json
import os

ARQUIVO_RESERVA = "reserva/estado.json"
ARQUIVO_APORTES = "stats/aportes.json"
MINIMO_CONVERSAO_BRL = 30.0
PERCENTUAL_CONVERSAO = 0.50


def estado_inicial() -> dict:
    return {
        "lucro_acumulado_brl": 0.0,
        "pnl_liquido_pendente_brl": 0.0,
        "reserva_usdc": 0.0,
        "capital_reinvestido_brl": 0.0,
        "historico_conversoes": [],
    }


def _salvar(estado: dict, arquivo: str):
    os.makedirs(os.path.dirname(arquivo) or ".", exist_ok=True)
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def carregar_estado_reserva(arquivo: str = ARQUIVO_RESERVA) -> dict:
    """Carrega o estado da reserva. Cria arquivo com estado inicial se não existir."""
    if not os.path.exists(arquivo):
        estado = estado_inicial()
        _salvar(estado, arquivo)
        return estado
    with open(arquivo, "r", encoding="utf-8") as f:
        return json.load(f)


def registrar_lucro(lucro_brl: float, arquivo: str = ARQUIVO_RESERVA) -> dict:
    """Adiciona lucro positivo ao acumulado. Prejuízo é ignorado."""
    estado = carregar_estado_reserva(arquivo)
    if lucro_brl > 0:
        estado["lucro_acumulado_brl"] = round(estado["lucro_acumulado_brl"] + lucro_brl, 2)
    _salvar(estado, arquivo)
    return estado


def calcular_conversao(
    lucro_acumulado_brl: float,
    percentual: float = PERCENTUAL_CONVERSAO,
    minimo: float = MINIMO_CONVERSAO_BRL,
) -> float:
    """Retorna o valor em BRL a converter para USDC.
    Zero se lucro acumulado não atingiu o mínimo."""
    if lucro_acumulado_brl < minimo:
        return 0.0
    return round(lucro_acumulado_brl * percentual, 2)


def registrar_conversao(
    valor_brl: float,
    valor_usdc: float,
    taxa_cambio: float,
    timestamp: str,
    arquivo: str = ARQUIVO_RESERVA,
) -> dict:
    """Registra uma conversão BRL → USDC: desconta do acumulado, soma à reserva."""
    estado = carregar_estado_reserva(arquivo)
    estado["lucro_acumulado_brl"] = round(estado["lucro_acumulado_brl"] - valor_brl, 2)
    estado["reserva_usdc"] = round(estado["reserva_usdc"] + valor_usdc, 4)
    estado["historico_conversoes"].append({
        "valor_brl": valor_brl,
        "valor_usdc": valor_usdc,
        "taxa_cambio": taxa_cambio,
        "timestamp": timestamp,
    })
    _salvar(estado, arquivo)
    return estado


def registrar_resultado(lucro_brl: float, arquivo: str = ARQUIVO_RESERVA) -> dict:
    """Acumula o P&L líquido do trade (positivo = lucro, negativo = prejuízo)."""
    estado = carregar_estado_reserva(arquivo)
    if "pnl_liquido_pendente_brl" not in estado:
        estado["pnl_liquido_pendente_brl"] = 0.0
    estado["pnl_liquido_pendente_brl"] = round(
        estado["pnl_liquido_pendente_brl"] + lucro_brl, 2
    )
    _salvar(estado, arquivo)
    return estado


def deve_converter(
    pnl_liquido: float,
    portfolio_brl: float,
    capital_investido: float,
    minimo: float = MINIMO_CONVERSAO_BRL,
) -> bool:
    """Retorna True se as condições para conversão estiverem satisfeitas:
    1. P&L líquido acumulado >= mínimo (R$30 por padrão)
    2. Portfólio atual > capital investido"""
    return pnl_liquido >= minimo and portfolio_brl > capital_investido


def calcular_split(pnl_liquido: float) -> dict:
    """Divide o P&L líquido em 50% para USDC e 50% para reinvestimento."""
    metade = round(pnl_liquido / 2, 2)
    return {"usdc_brl": metade, "reinvest_brl": metade}


def registrar_reinvestimento(
    valor_brl: float,
    data: str,
    arquivo_aportes: str = ARQUIVO_APORTES,
) -> None:
    """Adiciona um aporte automático em aportes.json com fonte 'lucro_reinvestido'."""
    if os.path.exists(arquivo_aportes):
        with open(arquivo_aportes, "r", encoding="utf-8") as f:
            dados = json.load(f)
    else:
        dados = {"confirmados": [], "rejeitados": []}

    dados["confirmados"].append({
        "data": data,
        "valor_brl": round(valor_brl, 2),
        "fonte": "lucro_reinvestido",
    })

    os.makedirs(os.path.dirname(arquivo_aportes) or ".", exist_ok=True)
    with open(arquivo_aportes, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def registrar_conversao_completa(
    valor_usdc_brl: float,
    valor_reinvest_brl: float,
    valor_usdc: float,
    taxa_cambio: float,
    timestamp: str,
    arquivo: str = ARQUIVO_RESERVA,
) -> dict:
    """Registra a transação completa após o split 50/50."""
    estado = carregar_estado_reserva(arquivo)
    if "pnl_liquido_pendente_brl" not in estado:
        estado["pnl_liquido_pendente_brl"] = 0.0
    if "capital_reinvestido_brl" not in estado:
        estado["capital_reinvestido_brl"] = 0.0

    estado["pnl_liquido_pendente_brl"] = 0.0
    estado["reserva_usdc"] = round(estado["reserva_usdc"] + valor_usdc, 4)
    estado["capital_reinvestido_brl"] = round(
        estado["capital_reinvestido_brl"] + valor_reinvest_brl, 2
    )
    estado["historico_conversoes"].append({
        "valor_usdc_brl": valor_usdc_brl,
        "valor_reinvest_brl": valor_reinvest_brl,
        "valor_usdc": valor_usdc,
        "taxa_cambio": taxa_cambio,
        "timestamp": timestamp,
    })
    _salvar(estado, arquivo)
    return estado

import json
import os

ARQUIVO_RESERVA = "reserva/estado.json"
MINIMO_CONVERSAO_BRL = 30.0
PERCENTUAL_CONVERSAO = 0.50


def estado_inicial() -> dict:
    return {
        "lucro_acumulado_brl": 0.0,
        "reserva_usdc": 0.0,
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

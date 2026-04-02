"""Rotas de gestão de aportes de capital."""
from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import (
    _verificar_token,
    _carregar_aportes,
    _carregar_dados_aportes,
    _salvar_dados_aportes,
    _buscar_depositos_binance,
)

router = APIRouter()


@router.get("/portfolio/aportes", dependencies=[Depends(_verificar_token)])
def get_aportes():
    return _carregar_aportes()


@router.get("/portfolio/aportes/pendentes", dependencies=[Depends(_verificar_token)])
def get_aportes_pendentes():
    """Retorna depósitos BRL da Binance ainda não classificados."""
    try:
        depositos = _buscar_depositos_binance()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro Binance: {e}")

    dados = _carregar_dados_aportes()
    order_nos_vistos = (
        {a.get("order_no") for a in dados["confirmados"] if a.get("order_no")}
        | set(dados["rejeitados"])
    )
    pendentes = [d for d in depositos if d["order_no"] not in order_nos_vistos]
    return pendentes


@router.post("/portfolio/aporte/confirmar", dependencies=[Depends(_verificar_token)])
def confirmar_aporte(body: dict):
    order_no = body.get("order_no")
    data_str = body.get("data")
    valor_brl = body.get("valor_brl")
    if not order_no or not data_str or not valor_brl:
        raise HTTPException(status_code=400, detail="order_no, data e valor_brl são obrigatórios")
    dados = _carregar_dados_aportes()
    if order_no not in {a.get("order_no") for a in dados["confirmados"]}:
        dados["confirmados"].append({
            "data": data_str,
            "valor_brl": round(float(valor_brl), 2),
            "order_no": order_no,
            "fonte": "binance",
        })
    _salvar_dados_aportes(dados)
    return {"ok": True}


@router.post("/portfolio/aporte/rejeitar", dependencies=[Depends(_verificar_token)])
def rejeitar_aporte(body: dict):
    order_no = body.get("order_no")
    if not order_no:
        raise HTTPException(status_code=400, detail="order_no é obrigatório")
    dados = _carregar_dados_aportes()
    if order_no not in dados["rejeitados"]:
        dados["rejeitados"].append(order_no)
    _salvar_dados_aportes(dados)
    return {"ok": True}


@router.post("/portfolio/aporte", dependencies=[Depends(_verificar_token)])
def post_aporte(body: dict):
    data_str = body.get("data")
    valor_brl = body.get("valor_brl")
    if not data_str or not valor_brl or float(valor_brl) <= 0:
        raise HTTPException(status_code=400, detail="data e valor_brl são obrigatórios")
    dados = _carregar_dados_aportes()
    dados["confirmados"].append({
        "data": data_str,
        "valor_brl": round(float(valor_brl), 2),
        "fonte": "manual",
    })
    _salvar_dados_aportes(dados)
    return {"ok": True}


@router.delete("/portfolio/aporte", dependencies=[Depends(_verificar_token)])
def delete_aporte(order_no: str = Query(default=""), data: str = Query(default=""), valor_brl: float = Query(default=0)):
    dados = _carregar_dados_aportes()
    for i, a in enumerate(dados["confirmados"]):
        if order_no and a.get("order_no") == order_no:
            dados["confirmados"].pop(i)
            _salvar_dados_aportes(dados)
            return {"ok": True}
        if not order_no and a["data"] == data and abs(a["valor_brl"] - valor_brl) < 0.01:
            dados["confirmados"].pop(i)
            _salvar_dados_aportes(dados)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Aporte não encontrado")


@router.patch("/portfolio/aporte", dependencies=[Depends(_verificar_token)])
def patch_aporte(body: dict):
    order_no = body.get("order_no", "")
    data_antiga = body.get("data_antiga", "")
    valor_brl = float(body.get("valor_brl", 0))
    nova_data = body.get("nova_data")
    if not nova_data:
        raise HTTPException(status_code=400, detail="nova_data é obrigatório")
    dados = _carregar_dados_aportes()
    for a in dados["confirmados"]:
        if order_no and a.get("order_no") == order_no:
            a["data"] = nova_data
            _salvar_dados_aportes(dados)
            return {"ok": True}
        if not order_no and a["data"] == data_antiga and abs(a["valor_brl"] - valor_brl) < 0.01:
            a["data"] = nova_data
            _salvar_dados_aportes(dados)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Aporte não encontrado")

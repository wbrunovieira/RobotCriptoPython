"""Rotas fiscais — exportação CSV e resumo mensal."""
import csv
import io
import json
import os
import sys

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _ROOT)

from infra.fiscal import carregar_stats_do_mes, calcular_resumo_mensal
from api.deps import _verificar_token, _stats_dir

router = APIRouter()


@router.get("/stats/mes", dependencies=[Depends(_verificar_token)])
def get_stats_mes(mes: str = Query(..., description="Formato: YYYY-MM")):
    stats_list = carregar_stats_do_mes(mes, diretorio=_stats_dir())
    resumo = calcular_resumo_mensal(stats_list)
    resumo["mes"] = mes
    return resumo


@router.get("/fiscal/csv", dependencies=[Depends(_verificar_token)])
def get_fiscal_csv(mes: str = Query(..., description="Formato: YYYY-MM")):
    stats_list = carregar_stats_do_mes(mes, diretorio=_stats_dir())

    output = io.StringIO()
    campos = ["data", "tipo", "par", "preco", "quantidade", "total_brl", "lucro_brl", "lucro_pct", "timestamp"]
    writer = csv.DictWriter(output, fieldnames=campos)
    writer.writeheader()
    for stats in stats_list:
        data_dia = stats.get("data", "")
        for op in stats.get("operacoes", []):
            writer.writerow({
                "data": data_dia,
                "tipo": op.get("tipo", ""),
                "par": op.get("par", ""),
                "preco": op.get("preco", ""),
                "quantidade": op.get("quantidade", ""),
                "total_brl": op.get("total_brl", ""),
                "lucro_brl": op.get("lucro_brl", ""),
                "lucro_pct": op.get("lucro_pct", ""),
                "timestamp": op.get("timestamp", ""),
            })

    output.seek(0)
    filename = f"relatorio_fiscal_{mes}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

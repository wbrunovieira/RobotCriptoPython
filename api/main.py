import csv
import io
import json
import os
import sys
from datetime import date
from dotenv import load_dotenv

# Permite importar módulos da raiz do projeto (stats, fiscal, etc.)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
from fastapi import FastAPI, Depends, HTTPException, Query

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from stats import carregar_stats_do_dia, calcular_resumo
from fiscal import carregar_stats_do_mes, calcular_resumo_mensal, exportar_csv_mensal
from persistencia import carregar_posicao
from pares import listar_pares, arquivo_posicao
from reserva import estado_inicial

app = FastAPI(title="Cripto Robot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_security = HTTPBearer()


def _verificar_token(credentials: HTTPAuthorizationCredentials = Depends(_security)):
    token_esperado = os.getenv("API_TOKEN", "")
    if not token_esperado or credentials.credentials != token_esperado:
        raise HTTPException(status_code=401, detail="Token inválido")
    return credentials.credentials


def _stats_dir() -> str:
    return os.getenv("STATS_DIR", "stats")


def _posicao_dir() -> str:
    return os.getenv("POSICAO_DIR", ".")


def _reserva_file() -> str:
    return os.getenv("RESERVA_FILE", "reserva/estado.json")


def _status_file() -> str:
    return os.getenv("STATUS_FILE", "status.json")


def _arquivo_posicao_par(simbolo: str) -> str:
    base = _posicao_dir()
    return os.path.join(base, f"posicao_{simbolo}.json")


def _arquivo_stats(data: str) -> str:
    return os.path.join(_stats_dir(), f"{data}.json")


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

@app.get("/status", dependencies=[Depends(_verificar_token)])
def get_status():
    arquivo = _status_file()
    if not os.path.exists(arquivo):
        return {"rodando": False, "ultimo_ciclo": None, "versao": None}
    with open(arquivo) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# GET /posicoes
# ---------------------------------------------------------------------------

@app.get("/posicoes", dependencies=[Depends(_verificar_token)])
def get_posicoes():
    resultado = {}
    for par in listar_pares():
        simbolo = par["simbolo"]
        arq = _arquivo_posicao_par(simbolo)
        if os.path.exists(arq):
            with open(arq) as f:
                estado = json.load(f)
        else:
            estado = {"posicao": False, "preco_entrada": None, "preco_maximo": None, "stop_price": None}
        resultado[simbolo] = estado
    return resultado


# ---------------------------------------------------------------------------
# GET /stats/dia
# ---------------------------------------------------------------------------

@app.get("/stats/dia", dependencies=[Depends(_verificar_token)])
def get_stats_dia(data: str = Query(default=None)):
    if data is None:
        data = date.today().strftime("%Y-%m-%d")
    arquivo = _arquivo_stats(data)
    if not os.path.exists(arquivo):
        return {
            "data": data, "total_operacoes": 0, "operacoes_lucrativas": 0,
            "lucro_total_brl": 0.0, "maior_ganho": 0.0, "maior_perda": 0.0,
            "taxa_acerto_pct": 0.0,
        }
    with open(arquivo) as f:
        stats = json.load(f)
    resumo = calcular_resumo(stats)
    resumo["data"] = data
    return resumo


# ---------------------------------------------------------------------------
# GET /stats/mes
# ---------------------------------------------------------------------------

@app.get("/stats/mes", dependencies=[Depends(_verificar_token)])
def get_stats_mes(mes: str = Query(..., description="Formato: YYYY-MM")):
    stats_list = carregar_stats_do_mes(mes, diretorio=_stats_dir())
    resumo = calcular_resumo_mensal(stats_list)
    resumo["mes"] = mes
    return resumo


# ---------------------------------------------------------------------------
# GET /operacoes
# ---------------------------------------------------------------------------

@app.get("/operacoes", dependencies=[Depends(_verificar_token)])
def get_operacoes(data: str = Query(default=None)):
    if data is None:
        data = date.today().strftime("%Y-%m-%d")
    arquivo = _arquivo_stats(data)
    if not os.path.exists(arquivo):
        return []
    with open(arquivo) as f:
        stats = json.load(f)
    return stats.get("operacoes", [])


# ---------------------------------------------------------------------------
# GET /reserva
# ---------------------------------------------------------------------------

@app.get("/reserva", dependencies=[Depends(_verificar_token)])
def get_reserva():
    arquivo = _reserva_file()
    if not os.path.exists(arquivo):
        return estado_inicial()
    with open(arquivo) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# GET /fiscal/csv
# ---------------------------------------------------------------------------

@app.get("/fiscal/csv", dependencies=[Depends(_verificar_token)])
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
                "par": "SOLBRL",
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

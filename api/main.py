"""API principal — cria o app FastAPI e registra os routers por domínio."""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.rotas.brl import router as brl_router
from api.rotas.aportes import router as aportes_router
from api.rotas.fiscal import router as fiscal_router
from api.rotas.meme import router as meme_router

app = FastAPI(title="Cripto Robot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(brl_router)
app.include_router(aportes_router)
app.include_router(fiscal_router)
app.include_router(meme_router)

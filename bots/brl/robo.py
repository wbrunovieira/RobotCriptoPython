"""Bot BRL — orquestrador principal (MA crossover + RSI + trailing stop)."""
import logging
import os
import time
import signal
import tempfile
import threading
import json as _json
from decimal import Decimal, ROUND_DOWN

import pandas as pd
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET
from dotenv import load_dotenv

from infra.binance_client import criar_cliente_sincronizado
from infra.persistencia import salvar_posicao, carregar_posicao
from infra.stats_store import (
    iniciar_stats_do_dia,
    registrar_compra,
    registrar_venda,
    calcular_resumo,
    carregar_stats_do_dia,
)
from infra.reserva_store import (
    registrar_lucro,
    calcular_conversao,
    registrar_conversao,
    registrar_resultado,
    deve_converter,
    calcular_split,
    registrar_reinvestimento,
    registrar_conversao_completa,
)
from infra.notificacao import enviar_whatsapp
from core.indicadores import calcular_rsi
from core.risco import (
    stop_pct_por_atr,
    verificar_breakeven,
    atualizar_trailing_stop,
    verificar_trailing_stop,
    verificar_take_profit,
    verificar_lucro_minimo,
)
from core.sinais import avaliar_sinal, calcular_quantidade
from pares import listar_pares, arquivo_posicao, calcular_saldo_disponivel, consolidar_resumo, contar_posicoes_abertas
from bots.brl.config import (
    BOT_ID, PERIODO_CANDLE, STOP_PCT, TAKE_PROFIT_PCT, TETO_SALDO_PCT,
    MAX_POSICOES, PERCENTUAL_COMPRA, STOP_PORTFOLIO_PCT, BLOQUEIO_PORTFOLIO_FILE,
    MAX_TENTATIVAS, INTERVALO_MONITORAMENTO, INTERVALO_ESTRATEGIA,
    _intervalo_estrategia_min, BLOQUEIO_QUINTA_FEIRA, COOLDOWN_STOP_HORAS,
)

load_dotenv()

logger = logging.getLogger(__name__)

api_key = os.getenv("KEY_BINANCE")
secret_key = os.getenv("SECRET_BINANCE")


def _saldo_para_bot(saldo_brl: float, saldos: dict) -> float:
    """Limita o saldo BRL disponível para compras ao total de aportes confirmados."""
    stats_dir = os.path.join(os.path.dirname(__file__), "..", "..", "stats")
    aportes_file = os.path.join(stats_dir, "aportes.json")
    if not os.path.exists(aportes_file):
        return saldo_brl
    try:
        with open(aportes_file) as f:
            dados = _json.load(f)
        confirmados = dados.get("confirmados", [])
        if not confirmados:
            return saldo_brl
        total_aportes = sum(float(a.get("valor_brl", a.get("valor", 0))) for a in confirmados)
    except Exception as e:
        logger.error("[aporte] Erro ao ler aportes: %s. Usando saldo real.", e)
        return saldo_brl

    capital_em_posicoes = 0.0
    for par in listar_pares():
        simbolo = par["simbolo"]
        ativo = par["ativo"]
        estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
        if not estado.get("posicao") or not estado.get("preco_entrada"):
            continue
        saldo_ativo = saldos.get(ativo, 0.0)
        if saldo_ativo > 0:
            capital_em_posicoes += estado["preco_entrada"] * saldo_ativo

    disponivel_aporte = max(0.0, total_aportes - capital_em_posicoes)
    saldo_limitado = min(saldo_brl, disponivel_aporte)
    if saldo_limitado < saldo_brl:
        logger.info(
            "[aporte] Saldo BRL: R$%.2f | Aportes: R$%.2f | Em posições: R$%.2f | Disponível para bot: R$%.2f",
            saldo_brl, total_aportes, capital_em_posicoes, saldo_limitado,
        )
    return saldo_limitado


def _params_atuais() -> dict:
    return {
        "bot_id": BOT_ID,
        "take_profit_pct": TAKE_PROFIT_PCT,
        "stop_pct": STOP_PCT,
        "teto_saldo_pct": TETO_SALDO_PCT,
        "percentual_compra": PERCENTUAL_COMPRA,
        "periodo_candle": PERIODO_CANDLE,
        "intervalo_monitoramento_s": INTERVALO_MONITORAMENTO,
        "intervalo_estrategia_min": _intervalo_estrategia_min,
        "max_posicoes": MAX_POSICOES,
    }


def criar_cliente():
    return criar_cliente_sincronizado(api_key, secret_key)


def pegando_dados(cliente, codigo, intervalo):
    try:
        candles = cliente.get_klines(symbol=codigo, interval=intervalo, limit=1000)
        precos = pd.DataFrame(candles)
        precos.columns = [
            "tempo_abertura", "abertura", "maxima", "minima", "fechamento", "volume",
            "tempo_fechamento", "moedas_negociadas", "numero_trades",
            "volume_ativo_base_compra", "volume_ativo_cotacao", "-",
        ]
        precos = precos[["maxima", "minima", "fechamento", "tempo_fechamento"]]
        precos["tempo_fechamento"] = (
            pd.to_datetime(precos["tempo_fechamento"], unit="ms")
            .dt.tz_localize("UTC")
            .dt.tz_convert("America/Sao_Paulo")
        )
        for col in ("maxima", "minima", "fechamento"):
            precos[col] = precos[col].astype(float)
        return precos
    except Exception as e:
        logger.error("[%s] Erro ao pegar dados: %s", codigo, e)
        return pd.DataFrame()


def obter_preco_atual(cliente, codigo):
    ticker = cliente.get_symbol_ticker(symbol=codigo)
    return float(ticker["price"])


def obter_saldos(cliente, ativos_extras=None):
    """Retorna saldo BRL e um dict {ativo: saldo} para cada ativo monitorado."""
    conta = cliente.get_account()
    ativos_monitorados = {"BRL"} | {p["ativo"] for p in listar_pares()}
    if ativos_extras:
        ativos_monitorados |= set(ativos_extras)

    saldos = {a: 0.0 for a in ativos_monitorados}
    for item in conta["balances"]:
        if item["asset"] in ativos_monitorados:
            saldos[item["asset"]] = float(item["free"])

    saldo_brl = saldos.pop("BRL", 0.0)
    return saldo_brl, saldos


def obter_posicao_real_par(cliente, ativo, step_size):
    """Verifica se há saldo real do ativo acima do step_size mínimo."""
    conta = cliente.get_account()
    minimo = float(step_size)
    for item in conta["balances"]:
        if item["asset"] == ativo:
            return float(item["free"]) >= minimo
    return False


def log_operacao(tipo, simbolo, quantidade, preco):
    try:
        os.makedirs("logs", exist_ok=True)
        with open("logs/log_operacoes.txt", "a") as f:
            timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {tipo} {simbolo} | Qtd: {quantidade} | Preco: R${preco:.2f}\n")
    except Exception as e:
        logger.error("Erro ao gravar log de operação: %s", e)


def _portfolio_bloqueado() -> bool:
    """Retorna True se o stop de portfolio foi acionado nas últimas 24h."""
    if not os.path.exists(BLOQUEIO_PORTFOLIO_FILE):
        return False
    try:
        with open(BLOQUEIO_PORTFOLIO_FILE) as f:
            dados = _json.load(f)
        bloqueio_ate = pd.Timestamp(dados["bloqueio_ate"])
        agora = pd.Timestamp.now(tz="America/Sao_Paulo")
        if bloqueio_ate.tzinfo is None:
            bloqueio_ate = bloqueio_ate.tz_localize("America/Sao_Paulo")
        if agora < bloqueio_ate:
            logger.warning("[portfolio] Bloqueado até %s.", bloqueio_ate.strftime("%Y-%m-%d %H:%M"))
            return True
        return False
    except Exception as e:
        logger.error("[portfolio] Erro ao ler arquivo de bloqueio: %s", e)
        return False


def _bloquear_portfolio(horas: int = 24):
    bloqueio_ate = (pd.Timestamp.now(tz="America/Sao_Paulo") + pd.Timedelta(hours=horas)).isoformat()
    dados = {"bloqueio_ate": bloqueio_ate}
    dir_ = os.path.dirname(BLOQUEIO_PORTFOLIO_FILE)
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            _json.dump(dados, f)
        os.replace(tmp, BLOQUEIO_PORTFOLIO_FILE)
    except Exception:
        os.unlink(tmp)
        raise


_COOLDOWN_FILE = "run/cooldown_pares.json"


def _registrar_cooldown(simbolo: str, horas: int = COOLDOWN_STOP_HORAS) -> None:
    """Registra cooldown de re-entrada para o par após trailing stop.

    Impede re-entradas no mesmo par por `horas` horas, evitando múltiplos
    stops consecutivos em tendências de baixa (ex: 3 stops BNB em 9h no Apr 2).
    """
    try:
        os.makedirs("run", exist_ok=True)
        cooldowns: dict = {}
        if os.path.exists(_COOLDOWN_FILE):
            with open(_COOLDOWN_FILE) as f:
                cooldowns = _json.load(f)
        bloqueio_ate = (pd.Timestamp.now(tz="America/Sao_Paulo") + pd.Timedelta(hours=horas)).isoformat()
        cooldowns[simbolo] = bloqueio_ate
        fd, tmp = tempfile.mkstemp(dir="run", prefix=".tmp_cd_")
        try:
            with os.fdopen(fd, "w") as f:
                _json.dump(cooldowns, f)
            os.replace(tmp, _COOLDOWN_FILE)
        except Exception:
            os.unlink(tmp)
            raise
        logger.info("[%s][cooldown] Cooldown de %dh registrado até %s.", simbolo, horas,
                    pd.Timestamp(bloqueio_ate).strftime("%Y-%m-%d %H:%M"))
    except Exception as e:
        logger.error("[%s][cooldown] Erro ao registrar cooldown: %s", simbolo, e)


def _par_em_cooldown(simbolo: str) -> bool:
    """Retorna True se o par ainda está em período de cooldown pós stop-loss."""
    if not os.path.exists(_COOLDOWN_FILE):
        return False
    try:
        with open(_COOLDOWN_FILE) as f:
            cooldowns = _json.load(f)
        if simbolo not in cooldowns:
            return False
        bloqueio_ate = pd.Timestamp(cooldowns[simbolo])
        agora = pd.Timestamp.now(tz="America/Sao_Paulo")
        if bloqueio_ate.tzinfo is None:
            bloqueio_ate = bloqueio_ate.tz_localize("America/Sao_Paulo")
        if agora < bloqueio_ate:
            logger.info("[%s][cooldown] Bloqueado até %s.", simbolo, bloqueio_ate.strftime("%Y-%m-%d %H:%M"))
            return True
        return False
    except Exception as e:
        logger.error("[%s][cooldown] Erro ao verificar cooldown: %s", simbolo, e)
        return False


def _limite_diario_atingido() -> bool:
    """Retorna True se o prejuízo do dia ultrapassou 2% do capital inicial."""
    stats = carregar_stats_do_dia()
    if not stats:
        return False
    capital_inicial = stats.get("saldo_inicial_brl", 0.0)
    if capital_inicial <= 0:
        return False
    resumo = calcular_resumo(stats)
    lucro = resumo.get("lucro_total_brl", 0.0)
    limite = capital_inicial * 0.02
    if lucro < -limite:
        logger.warning("[risco] Limite diário atingido: R$%.2f (%.1f%%). Novas entradas bloqueadas.",
                       lucro, lucro / capital_inicial * 100)
        return True
    return False


def _verificar_alta_forte(cliente, simbolo: str, preco_atual: float) -> bool:
    """Retorna True se MA9 > MA21, preço acima da MA50, RSI > 55 e volume acima da média."""
    try:
        dados = pegando_dados(cliente, simbolo, PERIODO_CANDLE)
        if dados.empty or len(dados) < 50:
            return False
        fech = dados["fechamento"].astype(float)
        ma9 = fech.rolling(9).mean().iloc[-1]
        ma21 = fech.rolling(21).mean().iloc[-1]
        ma50 = fech.rolling(50).mean().iloc[-1]
        rsi = calcular_rsi(fech)
        volume_forte = True
        if "volume" in dados.columns and len(dados) >= 21:
            vol = dados["volume"].astype(float)
            volume_forte = float(vol.iloc[-1]) > float(vol.rolling(20).mean().iloc[-1]) * 1.3
        return bool(ma9 > ma21 and preco_atual > ma50 and rsi > 55 and volume_forte)
    except Exception as e:
        logger.error("[%s][tp] Erro ao verificar alta forte: %s", simbolo, e)
        return False


def verificar_stop_portfolio(cliente) -> bool:
    """Calcula o drawdown não-realizado. Se exceder STOP_PORTFOLIO_PCT, fecha tudo."""
    pares = listar_pares()
    saldo_brl, saldos = obter_saldos(cliente)
    pnl_total = 0.0
    capital_total = saldo_brl

    for par in pares:
        simbolo = par["simbolo"]
        ativo = par["ativo"]
        estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
        if not estado["posicao"] or not estado.get("preco_entrada"):
            continue
        saldo_ativo = saldos.get(ativo, 0.0)
        if saldo_ativo <= 0:
            continue
        try:
            preco_atual = obter_preco_atual(cliente, simbolo)
        except Exception:
            continue
        preco_entrada = estado["preco_entrada"]
        capital_total += saldo_ativo * preco_atual
        pnl_total += saldo_ativo * (preco_atual - preco_entrada)

    if capital_total <= 0:
        return False

    drawdown_pct = pnl_total / capital_total
    logger.info("[portfolio] P&L não-realizado: R$%.2f (%.2f%% do capital)",
                pnl_total, drawdown_pct * 100)

    if drawdown_pct < -STOP_PORTFOLIO_PCT:
        msg = (
            f"STOP DE PORTFOLIO\n"
            f"Drawdown: {drawdown_pct*100:.1f}% (limite: -{STOP_PORTFOLIO_PCT*100:.0f}%)\n"
            f"Fechando todas as posições. Bloqueio por 24h."
        )
        logger.warning(msg)
        enviar_whatsapp(msg)
        for par in pares:
            simbolo = par["simbolo"]
            ativo = par["ativo"]
            estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
            if estado["posicao"]:
                try:
                    preco_atual = obter_preco_atual(cliente, simbolo)
                    saldo_ativo = saldos.get(ativo, 0.0)
                    if saldo_ativo > 0:
                        executar_venda(cliente, par, saldo_ativo, preco_atual, motivo="Stop de Portfolio")
                except Exception as e:
                    logger.error("[%s][portfolio] Erro ao fechar: %s", simbolo, e)
        _bloquear_portfolio(horas=24)
        return True

    return False


def executar_compra(cliente, par, saldo_brl, preco_atual, stop_pct: float = None):
    simbolo = par["simbolo"]
    ativo = par["ativo"]
    step_size = par["step_size"]

    stop_pct = stop_pct if stop_pct is not None else STOP_PCT

    saldo_disponivel = calcular_saldo_disponivel(saldo_brl, TETO_SALDO_PCT)
    valor_a_usar = saldo_disponivel * PERCENTUAL_COMPRA
    quantidade_fmt = float(
        Decimal(str(valor_a_usar / preco_atual)).quantize(Decimal(step_size), rounding=ROUND_DOWN)
    )

    client_order_id = f"{BOT_ID}-{simbolo}-{int(time.time() * 1000)}"
    ordem = cliente.create_order(
        symbol=simbolo,
        side=SIDE_BUY,
        type=ORDER_TYPE_MARKET,
        quantity=quantidade_fmt,
        newClientOrderId=client_order_id,
    )
    total_brl = round(quantidade_fmt * preco_atual, 2)
    timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
    log_operacao("COMPRA", simbolo, quantidade_fmt, preco_atual)
    registrar_compra(
        preco_atual, quantidade_fmt, total_brl, timestamp,
        par=simbolo, bot_id=BOT_ID, order_id=client_order_id,
    )
    preco_maximo, stop_price = atualizar_trailing_stop(preco_atual, None, None, stop_pct)
    salvar_posicao(True, preco_atual, preco_maximo=preco_maximo, stop_price=stop_price,
                   arquivo=arquivo_posicao(simbolo))
    msg = (
        f"COMPRA {ativo}\n"
        f"Qtd: {quantidade_fmt} {ativo}\n"
        f"Preco: R${preco_atual:.2f}\n"
        f"Stop inicial: R${stop_price:.2f} ({stop_pct*100:.1f}% ATR)\n"
        f"Total: R${total_brl:.2f} (teto: R${saldo_disponivel:.2f})"
    )
    logger.info(msg)
    enviar_whatsapp(msg)
    return True


def executar_venda(cliente, par, saldo_ativo, preco_atual, motivo="Sinal de venda"):
    simbolo = par["simbolo"]
    ativo = par["ativo"]
    step_size = par["step_size"]

    quantidade_fmt = Decimal(str(saldo_ativo)).quantize(Decimal(step_size), rounding=ROUND_DOWN)
    client_order_id = f"{BOT_ID}-{simbolo}-{int(time.time() * 1000)}"
    cliente.create_order(
        symbol=simbolo,
        side=SIDE_SELL,
        type=ORDER_TYPE_MARKET,
        quantity=float(quantidade_fmt),
        newClientOrderId=client_order_id,
    )
    total_brl = round(float(quantidade_fmt) * preco_atual, 2)
    timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
    estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
    preco_entrada = estado.get("preco_entrada")
    log_operacao("VENDA", simbolo, float(quantidade_fmt), preco_atual)
    registrar_venda(
        preco_atual, float(quantidade_fmt), total_brl, preco_entrada, timestamp,
        par=simbolo, bot_id=BOT_ID, order_id=client_order_id,
    )
    salvar_posicao(False, None, arquivo=arquivo_posicao(simbolo))

    stats = carregar_stats_do_dia()
    resumo = calcular_resumo(stats) if stats else {}
    lucro_op = total_brl - (preco_entrada * float(quantidade_fmt)) if preco_entrada else 0

    msg = (
        f"VENDA {ativo} ({motivo})\n"
        f"Qtd: {quantidade_fmt} {ativo}\n"
        f"Preco: R${preco_atual:.2f}\n"
        f"Lucro op: R${lucro_op:.2f}\n"
        f"Lucro dia: R${resumo.get('lucro_total_brl', 0):.2f} ({resumo.get('taxa_acerto_pct', 0):.0f}% acerto)"
    )
    logger.info(msg)
    enviar_whatsapp(msg)

    saldo_brl_pos_venda, _ = obter_saldos(cliente)
    capital_investido = _saldo_para_bot(saldo_brl_pos_venda, {})
    _verificar_reserva_usdc(cliente, lucro_op, timestamp, saldo_brl_pos_venda, capital_investido)
    return False


def _verificar_reserva_usdc(
    cliente,
    lucro_op: float,
    timestamp: str,
    portfolio_brl: float,
    capital_investido: float,
):
    try:
        estado = registrar_resultado(lucro_op)
        pnl = estado["pnl_liquido_pendente_brl"]

        if not deve_converter(pnl, portfolio_brl, capital_investido):
            status = "aguardando portfólio subir" if portfolio_brl <= capital_investido else f"aguardando R${30 - pnl:.2f} mais"
            logger.info("[reserva] P&L líquido: R$%.2f (%s)", pnl, status)
            return

        split = calcular_split(pnl)
        valor_usdc_brl = split["usdc_brl"]
        valor_reinvest_brl = split["reinvest_brl"]

        ticker = cliente.get_symbol_ticker(symbol="USDCBRL")
        taxa_cambio = float(ticker["price"])
        quantidade_usdc = round(valor_usdc_brl / taxa_cambio, 4)
        cliente.create_order(symbol="USDCBRL", side="BUY", type="MARKET", quoteOrderQty=valor_usdc_brl)

        data_str = timestamp[:10]
        registrar_reinvestimento(valor_reinvest_brl, data_str)

        estado_novo = registrar_conversao_completa(
            valor_usdc_brl, valor_reinvest_brl, quantidade_usdc, taxa_cambio, timestamp
        )

        msg = (
            f"LUCRO PROCESSADO\n"
            f"P&L líquido: R${pnl:.2f}\n"
            f"→ USDC: R${valor_usdc_brl:.2f} = {quantidade_usdc:.4f} USDC\n"
            f"→ Capital: +R${valor_reinvest_brl:.2f} (reinvestido)\n"
            f"Reserva total: {estado_novo['reserva_usdc']:.4f} USDC\n"
            f"Capital total reinvestido: R${estado_novo['capital_reinvestido_brl']:.2f}"
        )
        logger.info(msg)
        enviar_whatsapp(msg)
    except Exception as e:
        logger.error("[reserva] Erro na conversão USDC: %s", e)


def monitorar_stop_par(cliente, par):
    """Checagem de take-profit e trailing stop para um par específico."""
    simbolo = par["simbolo"]
    estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
    if not estado["posicao"]:
        return

    try:
        preco_atual = obter_preco_atual(cliente, simbolo)
        preco_maximo = estado["preco_maximo"]
        stop_price = estado["stop_price"]
        preco_entrada = estado["preco_entrada"]

        if verificar_take_profit(preco_atual, preco_entrada, TAKE_PROFIT_PCT):
            variacao = ((preco_atual / preco_entrada) - 1) * 100

            if _verificar_alta_forte(cliente, simbolo, preco_atual):
                logger.info("[%s][tp] TP +%.2f%% atingido | alta forte — trailing stop continua.", simbolo, variacao)
                return

            logger.info("[%s][tp] TAKE-PROFIT! Preco: R$%.2f (+%.2f%%)", simbolo, preco_atual, variacao)
            enviar_whatsapp(
                f"TAKE-PROFIT {simbolo}\n"
                f"Entrada: R${preco_entrada:.2f} | Atual: R${preco_atual:.2f}\n"
                f"Ganho: +{variacao:.2f}%"
            )
            _, saldos = obter_saldos(cliente)
            saldo_ativo_venda = saldos.get(par["ativo"], 0.0)
            capital_posicao_tp = saldo_ativo_venda * preco_atual
            executar_venda(cliente, par, saldo_ativo_venda, preco_atual, motivo="Take-Profit")

            saldo_brl, saldos_re = obter_saldos(cliente)
            if _portfolio_bloqueado() or _limite_diario_atingido():
                return
            dados = pegando_dados(cliente, simbolo, PERIODO_CANDLE)
            if not dados.empty:
                sinal = avaliar_sinal(dados, posicao=False, reentrada=True, bloqueio_quinta=BLOQUEIO_QUINTA_FEIRA)
                if sinal == "COMPRAR":
                    stop_atr = stop_pct_por_atr(dados, stop_pct_min=STOP_PCT)
                    saldo_reentrada = min(
                        _saldo_para_bot(saldo_brl, saldos_re),
                        capital_posicao_tp / (TETO_SALDO_PCT * PERCENTUAL_COMPRA),
                    )
                    logger.info("[%s][tp] Reentrada após take-profit (capital: R$%.2f).", simbolo, capital_posicao_tp)
                    executar_compra(cliente, par, saldo_reentrada, preco_atual, stop_pct=stop_atr)
            return

        novo_maximo, novo_stop = atualizar_trailing_stop(preco_atual, preco_maximo, stop_price, STOP_PCT)

        dist_stop = ((preco_atual / novo_stop) - 1) * 100 if novo_stop else 0
        dist_tp = ((preco_entrada * (1 + TAKE_PROFIT_PCT)) / preco_atual - 1) * 100 if preco_entrada else 0
        variacao_entrada = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
        logger.info(
            "[%s] R$%.2f | entrada %+.2f%% | stop R$%.2f (%.1f%% acima) | tp em %.1f%%",
            simbolo, preco_atual, variacao_entrada, novo_stop, dist_stop, dist_tp,
        )

        novo_stop_be = verificar_breakeven(preco_atual, preco_entrada, novo_stop)
        if novo_stop_be is not None and novo_stop_be > novo_stop:
            novo_stop = novo_stop_be
            salvar_posicao(True, preco_entrada, preco_maximo=novo_maximo, stop_price=novo_stop,
                           arquivo=arquivo_posicao(simbolo))
            logger.info("[%s][be] Break-even ativado! Stop → R$%.2f", simbolo, novo_stop)
        elif novo_maximo != preco_maximo or novo_stop != stop_price:
            salvar_posicao(True, preco_entrada, preco_maximo=novo_maximo, stop_price=novo_stop,
                           arquivo=arquivo_posicao(simbolo))
            logger.info("[%s][stop] ▲ Novo topo R$%.2f → stop atualizado R$%.2f", simbolo, novo_maximo, novo_stop)

        if verificar_trailing_stop(preco_atual, novo_stop):
            variacao = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
            logger.info("[%s][stop] TRAILING STOP! Preco: R$%.2f (%.2f%%)", simbolo, preco_atual, variacao)
            enviar_whatsapp(
                f"TRAILING STOP {simbolo}\n"
                f"Topo: R${novo_maximo:.2f} | Stop: R${novo_stop:.2f}\n"
                f"Atual: R${preco_atual:.2f} | Variacao: {variacao:.2f}%"
            )
            _, saldos = obter_saldos(cliente)
            saldo_ativo_venda = saldos.get(par["ativo"], 0.0)
            executar_venda(cliente, par, saldo_ativo_venda, preco_atual, motivo="Trailing Stop")
            _registrar_cooldown(simbolo)

    except Exception as e:
        logger.error("[%s][stop] Erro: %s", simbolo, e)


def monitorar_stop(cliente):
    try:
        if verificar_stop_portfolio(cliente):
            return
    except Exception as e:
        logger.error("[portfolio][stop] Erro ao verificar stop de portfolio (rede?): %s. Continuando stops individuais.", e)
    for par in listar_pares():
        monitorar_stop_par(cliente, par)


def ciclo_par(cliente, par, saldo_brl, saldo_ativo):
    """Avaliação completa de estratégia para um par."""
    simbolo = par["simbolo"]
    ativo = par["ativo"]
    step_size = par["step_size"]

    estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
    posicao = estado["posicao"]
    preco_entrada = estado["preco_entrada"]
    preco_maximo = estado["preco_maximo"]
    stop_price = estado["stop_price"]

    posicao_real = obter_posicao_real_par(cliente, ativo, step_size)
    if posicao_real != posicao:
        logger.warning("[%s] Divergência: real=%s salvo=%s. Corrigindo.", simbolo, posicao_real, posicao)
        posicao = posicao_real
        if not posicao_real:
            preco_entrada = preco_maximo = stop_price = None
        salvar_posicao(posicao, preco_entrada, preco_maximo=preco_maximo, stop_price=stop_price,
                       arquivo=arquivo_posicao(simbolo))

    status_posicao = "COMPRADO" if posicao else "NAO COMPRADO"
    if preco_entrada:
        logger.info("[%s] %s | Entrada: R$%.2f | Stop: R$%.2f", simbolo, status_posicao, preco_entrada, stop_price)
    else:
        logger.info("[%s] %s", simbolo, status_posicao)

    dados = pegando_dados(cliente, simbolo, PERIODO_CANDLE)
    if dados.empty:
        logger.warning("[%s] Sem dados. Pulando.", simbolo)
        return

    preco_atual = float(dados["fechamento"].iloc[-1])
    logger.info("[%s] Preco: R$%.2f", simbolo, preco_atual)

    pares_abertos = contar_posicoes_abertas(listar_pares())
    sinal = avaliar_sinal(dados, posicao, pares_abertos=pares_abertos, max_posicoes=MAX_POSICOES,
                          bloqueio_quinta=BLOQUEIO_QUINTA_FEIRA)

    if sinal == "COMPRAR":
        if _par_em_cooldown(simbolo):
            pass  # log já emitido dentro de _par_em_cooldown
        elif _portfolio_bloqueado():
            logger.info("[%s] Compra bloqueada: stop de portfolio ativo.", simbolo)
        elif _limite_diario_atingido():
            logger.info("[%s] Compra bloqueada: limite de perda diária atingido.", simbolo)
        else:
            stop_atr = stop_pct_por_atr(dados, stop_pct_min=STOP_PCT)
            logger.info("[%s] Stop ATR calculado: %.2f%%", simbolo, stop_atr * 100)
            executar_compra(cliente, par, saldo_brl, preco_atual, stop_pct=stop_atr)
    elif sinal == "VENDER":
        if verificar_lucro_minimo(preco_atual, preco_entrada):
            executar_venda(cliente, par, saldo_ativo, preco_atual)
        else:
            variacao = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
            logger.info("[%s] Venda ignorada: lucro %.2f%% não cobre taxas.", simbolo, variacao)
    else:
        logger.info("[%s] Sem sinal.", simbolo)


def _gravar_status(rodando: bool = True):
    timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs("run", exist_ok=True)
        dados = {"rodando": rodando, "pid": os.getpid(), "ultimo_ciclo": timestamp, "versao": "1.0.0"}
        fd, tmp = tempfile.mkstemp(dir="run", prefix=".tmp_")
        with os.fdopen(fd, "w") as f:
            _json.dump(dados, f)
        os.replace(tmp, "run/status.json")
    except Exception as e:
        logger.error("[status] Erro ao gravar status: %s", e)


def ciclo(cliente):
    _gravar_status()
    logger.info("=== %s ===", pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S"))

    saldo_brl, saldos = obter_saldos(cliente)
    logger.info("BRL disponível: R$%.2f", saldo_brl)
    for ativo, saldo in saldos.items():
        if saldo > 0:
            logger.info("  %s: %.6f", ativo, saldo)

    iniciar_stats_do_dia(saldo_inicial_brl=saldo_brl, parametros=_params_atuais())

    stats = carregar_stats_do_dia()
    if stats:
        resumo = calcular_resumo(stats)
        logger.info("Dia: %d ops | Lucro: R$%.2f | Acerto: %.0f%%",
                    resumo["total_operacoes"], resumo["lucro_total_brl"], resumo["taxa_acerto_pct"])

    for par in listar_pares():
        saldo_ativo = saldos.get(par["ativo"], 0.0)
        saldo_para_bot = _saldo_para_bot(saldo_brl, saldos)
        ciclo_par(cliente, par, saldo_para_bot, saldo_ativo)
        saldo_brl, saldos = obter_saldos(cliente)


_parar = threading.Event()


def _handler_sinal(signum, frame):
    if not _parar.is_set():
        logger.info("Soft stop solicitado. Aguardando fim do ciclo atual...")
        _parar.set()


def _aguardar(segundos: int) -> bool:
    for _ in range(segundos):
        if _parar.is_set():
            return True
        time.sleep(1)
    return False


def _validar_env():
    ausentes = [v for v in ("KEY_BINANCE", "SECRET_BINANCE") if not os.getenv(v)]
    if ausentes:
        raise EnvironmentError(f"Variáveis de ambiente obrigatórias não definidas: {', '.join(ausentes)}")
    if STOP_PCT >= TAKE_PROFIT_PCT:
        raise ValueError(
            f"Configuração inválida: BOT_STOP_PCT ({STOP_PCT}) deve ser menor que "
            f"BOT_TAKE_PROFIT_PCT ({TAKE_PROFIT_PCT})"
        )
    if not (0 < TETO_SALDO_PCT <= 1.0):
        raise ValueError(f"BOT_TETO_SALDO_PCT ({TETO_SALDO_PCT}) deve estar entre 0 e 1")
    if MAX_POSICOES < 1:
        raise ValueError(f"BOT_MAX_POSICOES ({MAX_POSICOES}) deve ser >= 1")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _validar_env()
    signal.signal(signal.SIGINT, _handler_sinal)
    signal.signal(signal.SIGTERM, _handler_sinal)

    tentativas = 0
    cliente = criar_cliente()

    while not _parar.is_set():
        try:
            ciclo(cliente)
            tentativas = 0

            checks = INTERVALO_ESTRATEGIA // INTERVALO_MONITORAMENTO
            for i in range(checks):
                if _aguardar(INTERVALO_MONITORAMENTO):
                    break
                logger.info("[%d/%d] %s checando stops...",
                            i + 1, checks,
                            pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%H:%M:%S"))
                monitorar_stop(cliente)

        except Exception as e:
            tentativas += 1
            espera = min(60 * tentativas, 300)
            logger.error("Erro (%d/%d): %s. Reconectando em %ds...", tentativas, MAX_TENTATIVAS, e, espera)
            if tentativas >= MAX_TENTATIVAS:
                enviar_whatsapp(f"Bot com erros consecutivos: {e}")
                tentativas = 0
            if _aguardar(espera):
                break
            try:
                cliente = criar_cliente()
            except Exception as ce:
                logger.error("Falha ao reconectar: %s. Tentando novamente no próximo ciclo.", ce)

    logger.info("Encerrando bot...")
    _gravar_status(rodando=False)
    try:
        enviar_whatsapp("Bot encerrado manualmente.")
    except Exception:
        pass
    logger.info("Robô encerrado.")

import pandas as pd
import os
import time
from binance.client import Client
from binance.enums import *
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv

from persistencia import salvar_posicao, carregar_posicao
from conexao import criar_cliente_sincronizado
from estrategia import (
    calcular_quantidade,
    avaliar_sinal,
    verificar_lucro_minimo,
    atualizar_trailing_stop,
    verificar_trailing_stop,
)
from notificacao import enviar_whatsapp

load_dotenv()

api_key = os.getenv("KEY_BINANCE")
secret_key = os.getenv("SECRET_BINANCE")

CODIGO_OPERADO = "SOLBRL"
ATIVO_OPERADO = "SOL"
PERIODO_CANDLE = Client.KLINE_INTERVAL_1HOUR
STOP_PCT = 0.05
PERCENTUAL_SALDO = 0.90
MAX_TENTATIVAS = 3
INTERVALO_MONITORAMENTO = 60       # segundos entre cada checagem de stop
INTERVALO_ESTRATEGIA = 60 * 60    # 1 hora entre avaliações completas


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
        precos = precos[["fechamento", "tempo_fechamento"]]
        precos["tempo_fechamento"] = (
            pd.to_datetime(precos["tempo_fechamento"], unit="ms")
            .dt.tz_localize("UTC")
            .dt.tz_convert("America/Sao_Paulo")
        )
        precos["fechamento"] = precos["fechamento"].astype(float)
        return precos
    except Exception as e:
        print(f"Erro ao pegar dados: {e}")
        return pd.DataFrame()


def obter_preco_atual(cliente, codigo):
    ticker = cliente.get_symbol_ticker(symbol=codigo)
    return float(ticker["price"])


def obter_saldos(cliente):
    conta = cliente.get_account()
    saldo_brl, saldo_sol = 0.0, 0.0
    for ativo in conta["balances"]:
        if ativo["asset"] == "BRL":
            saldo_brl = float(ativo["free"])
        if ativo["asset"] == ATIVO_OPERADO:
            saldo_sol = float(ativo["free"])
    return saldo_brl, saldo_sol


def obter_posicao_real(cliente, quantidade_minima=0.001):
    conta = cliente.get_account()
    for ativo in conta["balances"]:
        if ativo["asset"] == ATIVO_OPERADO:
            return float(ativo["free"]) >= quantidade_minima
    return False


def log_operacao(tipo, quantidade, preco):
    try:
        with open("log_operacoes.txt", "a") as f:
            timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {tipo} {ATIVO_OPERADO} | Qtd: {quantidade} | Preco: R${preco:.2f}\n")
    except Exception as e:
        print(f"Erro ao gravar log: {e}")


def executar_compra(cliente, saldo_brl, preco_atual):
    quantidade = calcular_quantidade(saldo_brl, preco_atual, PERCENTUAL_SALDO)
    cliente.create_order(
        symbol=CODIGO_OPERADO,
        side=SIDE_BUY,
        type=ORDER_TYPE_MARKET,
        quantity=quantidade,
    )
    log_operacao("COMPRA", quantidade, preco_atual)
    preco_maximo, stop_price = atualizar_trailing_stop(preco_atual, None, None, STOP_PCT)
    salvar_posicao(True, preco_atual, preco_maximo=preco_maximo, stop_price=stop_price)
    msg = (
        f"COMPRA SOL\n"
        f"Qtd: {quantidade} SOL\n"
        f"Preco: R${preco_atual:.2f}\n"
        f"Stop inicial: R${stop_price:.2f}\n"
        f"Total: R${quantidade * preco_atual:.2f}"
    )
    print(msg)
    enviar_whatsapp(msg)
    return True


def executar_venda(cliente, saldo_sol, preco_atual, motivo="Sinal de venda"):
    quantidade_formatada = Decimal(str(saldo_sol)).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
    cliente.create_order(
        symbol=CODIGO_OPERADO,
        side=SIDE_SELL,
        type=ORDER_TYPE_MARKET,
        quantity=float(quantidade_formatada),
    )
    log_operacao("VENDA", float(quantidade_formatada), preco_atual)
    salvar_posicao(False, None)
    msg = (
        f"VENDA SOL ({motivo})\n"
        f"Qtd: {quantidade_formatada} SOL\n"
        f"Preco: R${preco_atual:.2f}"
    )
    print(msg)
    enviar_whatsapp(msg)
    return False


def monitorar_stop(cliente):
    """Checagem rápida a cada 1 minuto: atualiza trailing stop e vende se ativado."""
    estado = carregar_posicao()
    if not estado["posicao"]:
        return

    try:
        preco_atual = obter_preco_atual(cliente, CODIGO_OPERADO)
        preco_maximo = estado["preco_maximo"]
        stop_price = estado["stop_price"]
        preco_entrada = estado["preco_entrada"]

        novo_maximo, novo_stop = atualizar_trailing_stop(preco_atual, preco_maximo, stop_price, STOP_PCT)

        if novo_maximo != preco_maximo or novo_stop != stop_price:
            salvar_posicao(True, preco_entrada, preco_maximo=novo_maximo, stop_price=novo_stop)
            print(f"[stop] Novo topo R${novo_maximo:.2f} → stop atualizado para R${novo_stop:.2f}")

        if verificar_trailing_stop(preco_atual, novo_stop):
            variacao = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
            print(f"[stop] TRAILING STOP ativado! Preco: R${preco_atual:.2f} | Stop: R${novo_stop:.2f} ({variacao:.2f}%)")
            enviar_whatsapp(
                f"TRAILING STOP ATIVADO\n"
                f"Topo: R${novo_maximo:.2f}\n"
                f"Stop: R${novo_stop:.2f}\n"
                f"Atual: R${preco_atual:.2f}\n"
                f"Variacao desde entrada: {variacao:.2f}%"
            )
            _, saldo_sol = obter_saldos(cliente)
            executar_venda(cliente, saldo_sol, preco_atual, motivo="Trailing Stop")

    except Exception as e:
        print(f"[stop] Erro no monitoramento: {e}")


def ciclo(cliente):
    print(f"\n--- {pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d %H:%M:%S')} ---")

    saldo_brl, saldo_sol = obter_saldos(cliente)
    print(f"Saldo: BRL R${saldo_brl:.2f} | SOL {saldo_sol:.4f}")

    estado = carregar_posicao()
    posicao = estado["posicao"]
    preco_entrada = estado["preco_entrada"]
    preco_maximo = estado["preco_maximo"]
    stop_price = estado["stop_price"]

    posicao_real = obter_posicao_real(cliente)
    if posicao_real != posicao:
        print(f"Divergencia detectada. Real: {posicao_real} | Salvo: {posicao}. Usando posicao real.")
        posicao = posicao_real
        if not posicao_real:
            preco_entrada = preco_maximo = stop_price = None
        salvar_posicao(posicao, preco_entrada, preco_maximo=preco_maximo, stop_price=stop_price)

    print(f"Posicao: {'COMPRADO' if posicao else 'NAO COMPRADO'}")
    if preco_entrada:
        print(f"Entrada: R${preco_entrada:.2f} | Topo: R${preco_maximo:.2f} | Stop: R${stop_price:.2f}")

    dados = pegando_dados(cliente, CODIGO_OPERADO, PERIODO_CANDLE)
    if dados.empty:
        print("Sem dados. Aguardando proximo ciclo.")
        return

    preco_atual = float(dados["fechamento"].iloc[-1])
    print(f"Preco atual: R${preco_atual:.2f}")

    sinal = avaliar_sinal(dados, posicao)

    if sinal == "COMPRAR":
        executar_compra(cliente, saldo_brl, preco_atual)
    elif sinal == "VENDER":
        if verificar_lucro_minimo(preco_atual, preco_entrada):
            executar_venda(cliente, saldo_sol, preco_atual)
        else:
            variacao = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
            print(f"Sinal de venda ignorado: lucro ({variacao:.2f}%) nao cobre as taxas (0.20%). Aguardando.")
    else:
        print("Sem sinal. Aguardando.")


def main():
    tentativas = 0
    cliente = criar_cliente()
    try:
        while True:
            try:
                ciclo(cliente)
                tentativas = 0

                # Monitoramento a cada 1 minuto durante 1 hora
                checks = INTERVALO_ESTRATEGIA // INTERVALO_MONITORAMENTO
                for i in range(checks):
                    time.sleep(INTERVALO_MONITORAMENTO)
                    print(f"[{i+1}/{checks}] {pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%H:%M:%S')} checando stop...")
                    monitorar_stop(cliente)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                tentativas += 1
                espera = min(60 * tentativas, 300)
                print(f"Erro ({tentativas}/{MAX_TENTATIVAS}): {e}. Reconectando em {espera}s...")
                if tentativas >= MAX_TENTATIVAS:
                    enviar_whatsapp(f"Bot com erros consecutivos: {e}")
                    tentativas = 0
                time.sleep(espera)
                cliente = criar_cliente()
    except KeyboardInterrupt:
        print("Robo encerrado pelo usuario.")
        enviar_whatsapp("Bot encerrado manualmente.")


if __name__ == "__main__":
    main()

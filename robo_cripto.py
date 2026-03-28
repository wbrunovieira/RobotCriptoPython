import pandas as pd
import os
import time
from binance.client import Client
from binance.enums import *
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv

from persistencia import salvar_posicao, carregar_posicao
from estrategia import calcular_quantidade, avaliar_sinal, verificar_stop_loss, verificar_lucro_minimo
from notificacao import enviar_whatsapp

load_dotenv()

api_key = os.getenv("KEY_BINANCE")
secret_key = os.getenv("SECRET_BINANCE")

CODIGO_OPERADO = "SOLBRL"
ATIVO_OPERADO = "SOL"
PERIODO_CANDLE = Client.KLINE_INTERVAL_1HOUR
STOP_LOSS_PCT = 0.05
PERCENTUAL_SALDO = 0.90
MAX_TENTATIVAS = 3


def criar_cliente():
    return Client(api_key, secret_key)


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
    msg = (
        f"COMPRA SOL\n"
        f"Qtd: {quantidade} SOL\n"
        f"Preco: R${preco_atual:.2f}\n"
        f"Total: R${quantidade * preco_atual:.2f}"
    )
    print(msg)
    enviar_whatsapp(msg)
    salvar_posicao(True, preco_atual)
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
    msg = (
        f"VENDA SOL ({motivo})\n"
        f"Qtd: {quantidade_formatada} SOL\n"
        f"Preco: R${preco_atual:.2f}"
    )
    print(msg)
    enviar_whatsapp(msg)
    salvar_posicao(False, None)
    return False


def ciclo(cliente):
    print(f"\n--- {pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d %H:%M:%S')} ---")

    saldo_brl, saldo_sol = obter_saldos(cliente)
    print(f"Saldo: BRL R${saldo_brl:.2f} | SOL {saldo_sol:.4f}")

    estado = carregar_posicao()
    posicao = estado["posicao"]
    preco_entrada = estado["preco_entrada"]

    posicao_real = obter_posicao_real(cliente)
    if posicao_real != posicao:
        print(f"Divergencia detectada. Real: {posicao_real} | Salvo: {posicao}. Usando posicao real.")
        posicao = posicao_real
        preco_entrada = preco_entrada if posicao_real else None
        salvar_posicao(posicao, preco_entrada)

    print(f"Posicao: {'COMPRADO' if posicao else 'NAO COMPRADO'}")
    if preco_entrada:
        print(f"Preco de entrada: R${preco_entrada:.2f}")

    dados = pegando_dados(cliente, CODIGO_OPERADO, PERIODO_CANDLE)
    if dados.empty:
        print("Sem dados. Aguardando proximo ciclo.")
        return

    preco_atual = float(dados["fechamento"].iloc[-1])
    print(f"Preco atual: R${preco_atual:.2f}")

    if posicao and verificar_stop_loss(preco_atual, preco_entrada, STOP_LOSS_PCT):
        variacao = ((preco_atual / preco_entrada) - 1) * 100
        print(f"STOP LOSS ativado! Entrada: R${preco_entrada:.2f} | Atual: R${preco_atual:.2f} ({variacao:.2f}%)")
        enviar_whatsapp(
            f"STOP LOSS ATIVADO\n"
            f"Entrada: R${preco_entrada:.2f}\n"
            f"Atual: R${preco_atual:.2f}\n"
            f"Variacao: {variacao:.2f}%"
        )
        executar_venda(cliente, saldo_sol, preco_atual, motivo="Stop Loss")
        return

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
                print(f"Aguardando 1 hora...")
                time.sleep(60 * 60)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                tentativas += 1
                espera = min(60 * tentativas, 300)
                print(f"Erro no ciclo ({tentativas}/{MAX_TENTATIVAS}): {e}. Reconectando em {espera}s...")
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

import time
from binance.client import Client


def calcular_offset_tempo(tempo_servidor_ms: int, tempo_local_ms: int) -> int:
    """Calcula a diferença em ms entre o servidor da Binance e o relógio local."""
    return tempo_servidor_ms - tempo_local_ms


def criar_cliente_sincronizado(api_key: str, secret_key: str) -> Client:
    """Cria o cliente Binance com o timestamp ajustado ao horário do servidor.
    Resolve o erro -1022 causado por dessincronização de relógio."""
    cliente = Client(api_key, secret_key)
    tempo_servidor = cliente.get_server_time()["serverTime"]
    tempo_local = int(time.time() * 1000)
    cliente.timestamp_offset = calcular_offset_tempo(tempo_servidor, tempo_local)
    print(f"Offset de tempo aplicado: {cliente.timestamp_offset}ms")
    return cliente

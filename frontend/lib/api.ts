const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("api_token") ?? "";
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${getToken()}`,
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (res.status === 401) throw new Error("401");
  if (!res.ok) throw new Error(`Erro ${res.status}`);
  return res.json();
}

// --- Tipos ---

export interface Status {
  rodando: boolean;
  ultimo_ciclo: string | null;
  versao: string | null;
}

export interface Posicao {
  posicao: boolean;
  preco_entrada: number | null;
  preco_maximo: number | null;
  stop_price: number | null;
}

export interface ResumoStats {
  data?: string;
  mes?: string;
  total_operacoes: number;
  operacoes_lucrativas: number;
  lucro_total_brl: number;
  maior_ganho: number;
  maior_perda: number;
  taxa_acerto_pct: number;
  imposto_devido_brl?: number;
  volume_vendas_brl?: number;
}

export interface Operacao {
  tipo: "COMPRA" | "VENDA";
  par?: string;
  preco: number;
  quantidade: number;
  total_brl: number;
  lucro_brl?: number;
  lucro_pct?: number;
  timestamp: string;
}

export interface Reserva {
  lucro_acumulado_brl: number;
  reserva_usdc: number;
  historico_conversoes: Array<{
    valor_brl: number;
    valor_usdc: number;
    taxa_cambio: number;
    timestamp: string;
  }>;
}

// --- Funções de API ---

export const fetchStatus = () => apiFetch<Status>("/status");

export const fetchPosicoes = () =>
  apiFetch<Record<string, Posicao>>("/posicoes");

export const fetchStatsDia = (data?: string) => {
  const q = data ? `?data=${data}` : "";
  return apiFetch<ResumoStats>(`/stats/dia${q}`);
};

export const fetchStatsMes = (mes: string) =>
  apiFetch<ResumoStats>(`/stats/mes?mes=${mes}`);

export const fetchOperacoes = (data?: string) => {
  const q = data ? `?data=${data}` : "";
  return apiFetch<Operacao[]>(`/operacoes${q}`);
};

export const fetchReserva = () => apiFetch<Reserva>("/reserva");

export const fetchCotacao = () => apiFetch<{ usd_brl: number }>("/cotacao");

export interface AtivoSaldo {
  quantidade: number;
  valor_brl: number;
  valor_usd: number;
  preco_brl?: number;
}

export interface Saldos {
  total_brl: number;
  total_usd: number;
  ativos: Record<string, AtivoSaldo>;
}

export const fetchSaldos = () => apiFetch<Saldos>("/saldos");

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export const fetchCandles = (simbolo: string, limite = 100) =>
  apiFetch<Candle[]>(`/candles/${simbolo}?limite=${limite}`);

export const downloadFiscalCsv = async (mes: string) => {
  const res = await fetch(`${API_URL}/fiscal/csv?mes=${mes}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error("Erro ao baixar CSV");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `relatorio_fiscal_${mes}.csv`;
  a.click();
  URL.revokeObjectURL(url);
};

export interface PerfPonto { data: string; pct: number }

export interface Performance {
  periodo: string;
  saldo_inicial: number;
  series: {
    bot: PerfPonto[];
    cdi_115: PerfPonto[];
    ibovespa: PerfPonto[];
    btc: PerfPonto[];
  };
}

export const fetchPerformance = (periodo = "mes") =>
  apiFetch<Performance>(`/performance?periodo=${periodo}`);

export interface BotParams {
  bot_id: string;
  take_profit_pct: number;
  stop_pct: number;
  teto_saldo_pct: number;
  periodo_candle: string;
  intervalo_monitoramento: number;
  intervalo_estrategia_min: number;
  max_posicoes: number;
}

export interface BotInfo {
  rodando: boolean;
  pid: number | null;
}

export const fetchBotInfo = () => apiFetch<BotInfo>("/bot/info");

export const iniciarBot = (params: BotParams) =>
  apiFetch<{ ok: boolean; pid: number }>("/bot/iniciar", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const pararBot = () =>
  apiFetch<{ ok: boolean }>("/bot/parar", { method: "POST" });

export const fetchBotLogs = (linhas = 100) =>
  apiFetch<{ linhas: string[] }>(`/bot/logs?linhas=${linhas}`);

export function botLogsStreamUrl(historico = 100): string {
  const token = getToken();
  return `${API_URL}/bot/logs/stream?token=${encodeURIComponent(token)}&historico=${historico}`;
}

export interface PontoPortfolio {
  data: string;
  valor_brl: number;
  capital_acumulado: number;
  variacao_brl: number;
  variacao_pct: number;
  a_mercado: boolean;
}

export interface EvolucaoPortfolio {
  capital_inicial: number;
  total_investido: number;
  pontos: PontoPortfolio[];
}

export const fetchEvolucaoPortfolio = () =>
  apiFetch<EvolucaoPortfolio>("/portfolio/evolucao");

export interface Aporte {
  data: string;
  valor_brl: number;
  order_no?: string;
  fonte?: "binance" | "manual";
}

export interface AportePendente {
  order_no: string;
  data: string;
  valor_brl: number;
}

export const fetchAportes = () => apiFetch<Aporte[]>("/portfolio/aportes");

export const fetchAportesPendentes = () =>
  apiFetch<AportePendente[]>("/portfolio/aportes/pendentes");

export const confirmarAporte = (p: AportePendente) =>
  apiFetch<{ ok: boolean }>("/portfolio/aporte/confirmar", {
    method: "POST",
    body: JSON.stringify(p),
  });

export const rejeitarAporte = (order_no: string) =>
  apiFetch<{ ok: boolean }>("/portfolio/aporte/rejeitar", {
    method: "POST",
    body: JSON.stringify({ order_no }),
  });

export const registrarAporte = (data: string, valor_brl: number) =>
  apiFetch<{ ok: boolean }>("/portfolio/aporte", {
    method: "POST",
    body: JSON.stringify({ data, valor_brl }),
  });

export const deletarAporte = (order_no?: string, data?: string, valor_brl?: number) =>
  apiFetch<{ ok: boolean }>(
    `/portfolio/aporte?order_no=${encodeURIComponent(order_no ?? "")}&data=${encodeURIComponent(data ?? "")}&valor_brl=${valor_brl ?? 0}`,
    { method: "DELETE" }
  );

export const corrigirSaldoDia = (data: string, saldo_inicial_brl: number) =>
  apiFetch<{ ok: boolean }>(`/stats/${data}/saldo`, {
    method: "PATCH",
    body: JSON.stringify({ saldo_inicial_brl }),
  });

export const atualizarDataAporte = (a: Aporte, nova_data: string) =>
  apiFetch<{ ok: boolean }>("/portfolio/aporte", {
    method: "PATCH",
    body: JSON.stringify({
      order_no: a.order_no ?? "",
      data_antiga: a.data,
      valor_brl: a.valor_brl,
      nova_data,
    }),
  });

export function salvarToken(token: string) {
  localStorage.setItem("api_token", token);
}

export function removerToken() {
  localStorage.removeItem("api_token");
}

export function tokenSalvo(): boolean {
  return !!getToken();
}

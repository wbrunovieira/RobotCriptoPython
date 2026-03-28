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

export function salvarToken(token: string) {
  localStorage.setItem("api_token", token);
}

export function removerToken() {
  localStorage.removeItem("api_token");
}

export function tokenSalvo(): boolean {
  return !!getToken();
}

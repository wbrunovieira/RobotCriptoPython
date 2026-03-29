"use client";
import { useEffect, useRef, useState } from "react";
import {
  BotInfo, BotParams,
  fetchBotInfo, iniciarBot, pararBot, botLogsStreamUrl,
} from "@/lib/api";

const DEFAULTS: BotParams = {
  bot_id: "MACross1",
  take_profit_pct: 0.03,
  stop_pct: 0.015,
  teto_saldo_pct: 0.60,
  periodo_candle: "1h",
  intervalo_monitoramento: 60,
  intervalo_estrategia_min: 60,
  max_posicoes: 2,
};

type SseStatus = "desconectado" | "conectando" | "conectado" | "erro";

export default function PainelControle() {
  const [aberto, setAberto] = useState(false);
  const [params, setParams] = useState<BotParams>(DEFAULTS);
  const [info, setInfo] = useState<BotInfo | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [sseStatus, setSseStatus] = useState<SseStatus>("desconectado");
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  // busca status ao montar para o botão no canto mostrar estado correto
  useEffect(() => {
    fetchBotInfo().then(setInfo).catch(() => {});
  }, []);

  // polling leve de status enquanto painel está aberto
  useEffect(() => {
    if (!aberto) return;
    const timer = setInterval(() => {
      fetchBotInfo().then(setInfo).catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [aberto]);

  // SSE — abre quando painel abre, fecha quando fecha
  useEffect(() => {
    if (!aberto) {
      esRef.current?.close();
      esRef.current = null;
      setSseStatus("desconectado");
      return;
    }

    setSseStatus("conectando");
    setLogs([]);

    const url = botLogsStreamUrl(200);
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setSseStatus("conectado");

    es.onmessage = (e) => {
      if (e.data === "") return; // keepalive vazio
      setLogs((prev) => {
        const next = [...prev, e.data];
        return next.length > 500 ? next.slice(-500) : next;
      });
    };

    es.onerror = () => {
      setSseStatus("erro");
      es.close();
      esRef.current = null;
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [aberto]);

  // auto-scroll para o fim
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  async function handleIniciar() {
    setCarregando(true);
    setErro(null);
    try {
      await iniciarBot(params);
      const res = await fetchBotInfo();
      setInfo(res);
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : "Erro ao iniciar");
    } finally {
      setCarregando(false);
    }
  }

  async function handleParar() {
    setCarregando(true);
    setErro(null);
    try {
      await pararBot();
      const res = await fetchBotInfo();
      setInfo(res);
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : "Erro ao parar");
    } finally {
      setCarregando(false);
    }
  }

  function set<K extends keyof BotParams>(key: K, value: BotParams[K]) {
    setParams((p) => ({ ...p, [key]: value }));
  }

  const rodando = info?.rodando ?? false;

  const sseDot: Record<SseStatus, string> = {
    desconectado: "bg-gray-600",
    conectando:   "bg-yellow-400 animate-pulse",
    conectado:    "bg-blue-400",
    erro:         "bg-red-500",
  };

  return (
    <>
      {/* Botão fixo canto superior direito */}
      <button
        onClick={() => setAberto(true)}
        className="fixed top-4 right-4 z-40 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-white text-sm px-3 py-2 rounded-lg shadow-lg transition-colors flex items-center gap-2"
        title="Controlar bot"
      >
        <span className={`w-2 h-2 rounded-full ${rodando ? "bg-green-400 animate-pulse" : "bg-gray-500"}`} />
        Bot
      </button>

      {/* Overlay */}
      {aberto && (
        <div
          className="fixed inset-0 z-40 bg-black/40"
          onClick={() => setAberto(false)}
        />
      )}

      {/* Drawer lateral */}
      <div
        className={`fixed top-0 right-0 z-50 h-full w-full max-w-md bg-gray-950 border-l border-gray-800 shadow-2xl flex flex-col transition-transform duration-300 ${
          aberto ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <div className="flex items-center gap-3">
            <span className={`w-2.5 h-2.5 rounded-full ${rodando ? "bg-green-400 animate-pulse" : "bg-gray-500"}`} />
            <h2 className="font-semibold text-white">Controle do Bot</h2>
            {info?.pid && (
              <span className="text-xs text-gray-500 font-mono">PID {info.pid}</span>
            )}
          </div>
          <button
            onClick={() => setAberto(false)}
            className="text-gray-500 hover:text-white text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Parâmetros */}
          <section className="space-y-3">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Parâmetros</h3>
            <div className="grid grid-cols-2 gap-3">
              <label className="space-y-1 col-span-2">
                <span className="text-xs text-gray-400">ID do Bot</span>
                <input
                  type="text"
                  value={params.bot_id}
                  onChange={(e) => set("bot_id", e.target.value)}
                  disabled={rodando}
                  placeholder="ex: CRv1, bot-agressivo"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
                />
                <span className="text-xs text-gray-600">Aparece como prefixo nas ordens da Binance</span>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-gray-400">Take Profit (%)</span>
                <input
                  type="number" step="0.001" min="0"
                  value={params.take_profit_pct * 100}
                  onChange={(e) => set("take_profit_pct", parseFloat(e.target.value) / 100)}
                  disabled={rodando}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-gray-400">Stop Trailing (%)</span>
                <input
                  type="number" step="0.001" min="0"
                  value={params.stop_pct * 100}
                  onChange={(e) => set("stop_pct", parseFloat(e.target.value) / 100)}
                  disabled={rodando}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-gray-400">Teto por par (%)</span>
                <input
                  type="number" step="1" min="1" max="100"
                  value={params.teto_saldo_pct * 100}
                  onChange={(e) => set("teto_saldo_pct", parseFloat(e.target.value) / 100)}
                  disabled={rodando}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-gray-400">Período candle</span>
                <select
                  value={params.periodo_candle}
                  onChange={(e) => set("periodo_candle", e.target.value)}
                  disabled={rodando}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
                >
                  {["1m", "5m", "15m", "30m", "1h", "4h"].map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-gray-400">Monitoramento (s)</span>
                <input
                  type="number" step="10" min="10"
                  value={params.intervalo_monitoramento}
                  onChange={(e) => set("intervalo_monitoramento", parseInt(e.target.value))}
                  disabled={rodando}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-gray-400">Estratégia (min)</span>
                <input
                  type="number" step="1" min="1"
                  value={params.intervalo_estrategia_min}
                  onChange={(e) => set("intervalo_estrategia_min", parseInt(e.target.value))}
                  disabled={rodando}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-gray-400">Máx. posições</span>
                <input
                  type="number" step="1" min="1" max="5"
                  value={params.max_posicoes}
                  onChange={(e) => set("max_posicoes", parseInt(e.target.value))}
                  disabled={rodando}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
                />
              </label>
            </div>
            {!rodando && (
              <button
                onClick={() => setParams(DEFAULTS)}
                className="text-xs text-gray-500 hover:text-gray-300 underline"
              >
                Restaurar padrões
              </button>
            )}
          </section>

          {/* Botão iniciar/parar */}
          <div className="space-y-2">
            {erro && (
              <p className="text-xs text-red-400 bg-red-900/20 rounded px-3 py-2">{erro}</p>
            )}
            {rodando ? (
              <button
                onClick={handleParar}
                disabled={carregando}
                className="w-full bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition-colors"
              >
                {carregando ? "Parando..." : "⏹ Parar Bot"}
              </button>
            ) : (
              <button
                onClick={handleIniciar}
                disabled={carregando}
                className="w-full bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition-colors"
              >
                {carregando ? "Iniciando..." : "▶ Iniciar Bot"}
              </button>
            )}
          </div>

          {/* Terminal SSE */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Terminal</h3>
              <span className={`w-1.5 h-1.5 rounded-full ${sseDot[sseStatus]}`} title={sseStatus} />
              <span className="text-xs text-gray-600">{sseStatus}</span>
              <span className="ml-auto text-xs text-gray-600">{logs.length} linhas</span>
            </div>
            <div className="bg-gray-900 rounded-xl p-3 h-96 overflow-y-auto font-mono text-xs border border-gray-800">
              {logs.length === 0 ? (
                <p className="text-gray-600">
                  {sseStatus === "conectando" ? "Conectando ao stream..." : "Sem logs ainda."}
                </p>
              ) : (
                logs.map((linha, i) => (
                  <div
                    key={i}
                    className={`leading-relaxed whitespace-pre-wrap break-all ${
                      linha.includes("COMPRA")
                        ? "text-green-400"
                        : linha.includes("VENDA") || linha.includes("Take-Profit") || linha.includes("Stop")
                        ? "text-red-400"
                        : linha.includes("Erro") || linha.includes("erro") || linha.includes("ERROR")
                        ? "text-yellow-400"
                        : "text-gray-400"
                    }`}
                  >
                    {linha || "\u00a0"}
                  </div>
                ))
              )}
              <div ref={logEndRef} />
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

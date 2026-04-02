"use client";
import { useEffect, useRef, useState } from "react";
import { BotInfo, BotParams, fetchBotInfo, iniciarBot, pararBot, botLogsStreamUrl } from "@/lib/api";
import BotParamsForm from "./BotParamsForm";
import TerminalLogs from "./TerminalLogs";

const DEFAULTS: BotParams = {
  bot_id: "MACross1",
  take_profit_pct: 0.02,
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
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    fetchBotInfo().then(setInfo).catch(() => {});
  }, []);

  useEffect(() => {
    if (!aberto) return;
    const timer = setInterval(() => {
      fetchBotInfo().then(setInfo).catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [aberto]);

  useEffect(() => {
    if (!aberto) {
      esRef.current?.close();
      esRef.current = null;
      setSseStatus("desconectado");
      return;
    }

    let reconectarTimer: ReturnType<typeof setTimeout> | null = null;
    let ativo = true;

    function conectar() {
      if (!ativo) return;
      setSseStatus("conectando");
      const es = new EventSource(botLogsStreamUrl(200));
      esRef.current = es;

      es.onopen = () => { if (ativo) setSseStatus("conectado"); };
      es.onmessage = (e) => {
        if (!ativo || e.data === "") return;
        setLogs((prev) => {
          const next = [...prev, e.data];
          return next.length > 500 ? next.slice(-500) : next;
        });
      };
      es.onerror = () => {
        if (!ativo) return;
        setSseStatus("erro");
        es.close();
        esRef.current = null;
        reconectarTimer = setTimeout(conectar, 3000);
      };
    }

    conectar();
    return () => {
      ativo = false;
      if (reconectarTimer) clearTimeout(reconectarTimer);
      esRef.current?.close();
      esRef.current = null;
    };
  }, [aberto]);

  function set<K extends keyof BotParams>(key: K, value: BotParams[K]) {
    setParams((p) => ({ ...p, [key]: value }));
  }

  async function handleIniciar() {
    setCarregando(true);
    setErro(null);
    try {
      await iniciarBot(params);
      setInfo(await fetchBotInfo());
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
      setInfo(await fetchBotInfo());
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : "Erro ao parar");
    } finally {
      setCarregando(false);
    }
  }

  const rodando = info?.rodando ?? false;

  return (
    <>
      <button
        onClick={() => setAberto(true)}
        className="fixed top-4 right-4 z-40 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-white text-sm px-3 py-2 rounded-lg shadow-lg transition-colors flex items-center gap-2"
        title="Controlar bot"
      >
        <span className={`w-2 h-2 rounded-full ${rodando ? "bg-green-400 animate-pulse" : "bg-gray-500"}`} />
        Bot
      </button>

      {aberto && (
        <div className="fixed inset-0 z-40 bg-black/40" onClick={() => setAberto(false)} />
      )}

      <div
        className={`fixed top-0 right-0 z-50 h-full w-full max-w-md bg-gray-950 border-l border-gray-800 shadow-2xl flex flex-col transition-transform duration-300 ${
          aberto ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <div className="flex items-center gap-3">
            <span className={`w-2.5 h-2.5 rounded-full ${rodando ? "bg-green-400 animate-pulse" : "bg-gray-500"}`} />
            <h2 className="font-semibold text-white">Controle do Bot</h2>
            {info?.pid && <span className="text-xs text-gray-500 font-mono">PID {info.pid}</span>}
          </div>
          <button onClick={() => setAberto(false)} className="text-gray-500 hover:text-white text-xl leading-none">×</button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          <BotParamsForm
            params={params}
            rodando={rodando}
            onChange={set}
            onReset={() => setParams(DEFAULTS)}
          />

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

          <TerminalLogs logs={logs} sseStatus={sseStatus} />
        </div>
      </div>
    </>
  );
}

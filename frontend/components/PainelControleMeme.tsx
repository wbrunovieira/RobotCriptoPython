'use client';
import { useEffect, useRef, useState } from 'react';
import {
  MemeStatus,
  MemeAporte,
  fetchMemeStatus,
  fetchMemeAportes,
  registrarMemeAporte,
  deletarMemeAporte,
  iniciarMemeBot,
  pararMemeBot,
  memeBotLogsStreamUrl,
} from '@/lib/api';
import TerminalLogs from './TerminalLogs';

type SseStatus = 'desconectado' | 'conectando' | 'conectado' | 'erro';

export default function PainelControleMeme() {
  const [aberto, setAberto] = useState(false);
  const [status, setStatus] = useState<MemeStatus | null>(null);
  const [aportes, setAportes] = useState<MemeAporte[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [sseStatus, setSseStatus] = useState<SseStatus>('desconectado');
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Aporte form state
  const [novaData, setNovaData] = useState(() => new Date().toISOString().slice(0, 10));
  const [novoValor, setNovoValor] = useState('');
  const [adicionando, setAdicionando] = useState(false);

  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    fetchMemeStatus()
      .then(setStatus)
      .catch(() => {});
    fetchMemeAportes()
      .then(setAportes)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!aberto) return;
    const timer = setInterval(() => {
      fetchMemeStatus()
        .then(setStatus)
        .catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [aberto]);

  useEffect(() => {
    if (!aberto) {
      esRef.current?.close();
      esRef.current = null;
      setSseStatus('desconectado');
      return;
    }

    let reconectarTimer: ReturnType<typeof setTimeout> | null = null;
    let ativo = true;

    function conectar() {
      if (!ativo) return;
      setSseStatus('conectando');
      const es = new EventSource(memeBotLogsStreamUrl(200));
      esRef.current = es;

      es.onopen = () => {
        if (ativo) setSseStatus('conectado');
      };
      es.onmessage = e => {
        if (!ativo || e.data === '') return;
        setLogs(prev => {
          const next = [...prev, e.data];
          return next.length > 500 ? next.slice(-500) : next;
        });
      };
      es.onerror = () => {
        if (!ativo) return;
        setSseStatus('erro');
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

  async function handleIniciar() {
    setCarregando(true);
    setErro(null);
    try {
      await iniciarMemeBot();
      setStatus(await fetchMemeStatus());
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : 'Erro ao iniciar');
    } finally {
      setCarregando(false);
    }
  }

  async function handleParar() {
    setCarregando(true);
    setErro(null);
    try {
      await pararMemeBot();
      setStatus(await fetchMemeStatus());
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : 'Erro ao parar');
    } finally {
      setCarregando(false);
    }
  }

  async function handleAdicionarAporte() {
    const valor = parseFloat(novoValor);
    if (!novaData || isNaN(valor) || valor <= 0) return;
    setAdicionando(true);
    try {
      await registrarMemeAporte(novaData, valor);
      const lista = await fetchMemeAportes();
      setAportes(lista);
      setNovoValor('');
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : 'Erro ao adicionar aporte');
    } finally {
      setAdicionando(false);
    }
  }

  async function handleDeletarAporte(a: MemeAporte) {
    try {
      await deletarMemeAporte(a.data, a.valor_usdt);
      const lista = await fetchMemeAportes();
      setAportes(lista);
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : 'Erro ao deletar aporte');
    }
  }

  const rodando = status?.rodando ?? false;
  const totalAportes = aportes.reduce((acc, a) => acc + a.valor_usdt, 0);

  return (
    <>
      <button
        onClick={() => setAberto(true)}
        className="fixed top-16 right-4 z-40 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-white text-sm px-3 py-2 rounded-lg shadow-lg transition-colors flex items-center gap-2"
        title="Controlar bot meme"
      >
        <span className={`w-2 h-2 rounded-full ${rodando ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
        Meme
      </button>

      {aberto && <div className="fixed inset-0 z-40 bg-black/40" onClick={() => setAberto(false)} />}

      <div
        className={`fixed top-0 right-0 z-50 h-full w-full max-w-md bg-gray-950 border-l border-gray-800 shadow-2xl flex flex-col transition-transform duration-300 ${
          aberto ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <div className="flex items-center gap-3">
            <span className={`w-2.5 h-2.5 rounded-full ${rodando ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
            <h2 className="font-semibold text-white">Controle Bot Meme</h2>
            {status?.pid && <span className="text-xs text-gray-500 font-mono">PID {status.pid}</span>}
          </div>
          <button onClick={() => setAberto(false)} className="text-gray-500 hover:text-white text-xl leading-none">
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Status */}
          <section className="space-y-3">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Status</h3>
            <div className="bg-gray-900 rounded-xl p-4 grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-gray-400">Saldo USDT</p>
                <p className="text-lg font-bold font-mono text-blue-400">
                  {status ? `${(status.saldo_usdt ?? 0).toFixed(4)} USDT` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Aportes confirmados</p>
                <p className="text-lg font-bold font-mono text-green-400">{totalAportes.toFixed(2)} USDT</p>
              </div>
              {status?.pnl_aberto !== undefined && (
                <div className="col-span-2">
                  <p className="text-xs text-gray-400">P&L aberto</p>
                  <p
                    className={`text-lg font-bold font-mono ${status.pnl_aberto >= 0 ? 'text-green-400' : 'text-red-400'}`}
                  >
                    {status.pnl_aberto >= 0 ? '+' : ''}
                    {status.pnl_aberto.toFixed(2)}%
                  </p>
                </div>
              )}
              {status?.ultimo_ciclo && (
                <div className="col-span-2">
                  <p className="text-xs text-gray-400">Último ciclo</p>
                  <p className="text-xs font-mono text-gray-300">{status.ultimo_ciclo}</p>
                </div>
              )}
            </div>
          </section>

          {/* Aportes USDT */}
          <section className="space-y-3">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Aportes USDT</h3>
            <div className="flex gap-2">
              <input
                type="date"
                value={novaData}
                onChange={e => setNovaData(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white flex-1"
              />
              <input
                type="number"
                value={novoValor}
                onChange={e => setNovoValor(e.target.value)}
                placeholder="USDT"
                min="0"
                step="0.01"
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white w-28"
              />
              <button
                onClick={handleAdicionarAporte}
                disabled={adicionando}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm px-3 py-2 rounded-lg transition-colors"
              >
                {adicionando ? '...' : '+'}
              </button>
            </div>
            {aportes.length > 0 ? (
              <div className="bg-gray-900 rounded-xl overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-800">
                      <th className="px-3 py-2">Data</th>
                      <th className="px-3 py-2 text-right">USDT</th>
                      <th className="px-3 py-2 text-right">Fonte</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {aportes.map((a, i) => (
                      <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/40">
                        <td className="px-3 py-2 font-mono text-gray-300">{a.data}</td>
                        <td className="px-3 py-2 text-right font-mono text-white">{a.valor_usdt.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right text-gray-500">{a.fonte ?? 'manual'}</td>
                        <td className="px-3 py-2 text-right">
                          <button
                            onClick={() => handleDeletarAporte(a)}
                            className="text-red-500 hover:text-red-400 text-xs"
                          >
                            ×
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-gray-600">Nenhum aporte registrado.</p>
            )}
          </section>

          {/* Controle */}
          <section className="space-y-2">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Controle</h3>
            {erro && <p className="text-xs text-red-400 bg-red-900/20 rounded px-3 py-2">{erro}</p>}
            {rodando ? (
              <button
                onClick={handleParar}
                disabled={carregando}
                className="w-full bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition-colors"
              >
                {carregando ? 'Parando...' : 'Parar Bot'}
              </button>
            ) : (
              <button
                onClick={handleIniciar}
                disabled={carregando}
                className="w-full bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition-colors"
              >
                {carregando ? 'Iniciando...' : 'Iniciar Bot'}
              </button>
            )}
          </section>

          {/* Terminal */}
          <TerminalLogs logs={logs} sseStatus={sseStatus} />
        </div>
      </div>
    </>
  );
}

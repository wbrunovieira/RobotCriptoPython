"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  tokenSalvo,
  fetchMemeStatus,
  fetchMemeScanner,
  fetchMemeOperacoes,
  fetchMemeStatsDia,
  fetchMemeStatsMes,
  fetchMemeOperacoesMes,
  fetchMemeReserva,
  MemeStatus,
  MemeScore,
  MemeReserva,
  Operacao,
  ResumoStats,
} from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import PainelControleMeme from "@/components/PainelControleMeme";
import MemePosicaoCard from "@/components/MemePosicaoCard";
import MemeScannerTabela from "@/components/MemeScannerTabela";
import StatsResumo from "@/components/StatsResumo";
import TabelaOperacoes from "@/components/TabelaOperacoes";
import GraficoEvolucaoMeme from "@/components/GraficoEvolucaoMeme";
import ReservaLucros from "@/components/ReservaLucros";

export default function MemePage() {
  const router = useRouter();
  const [precoAtual, setPrecoAtual] = useState<number | undefined>(undefined);
  const [mesAtual] = useState(() => new Date().toISOString().slice(0, 7));

  useEffect(() => {
    if (!tokenSalvo()) router.push("/login");
  }, [router]);

  const { data: memeStatus } = usePolling<MemeStatus>(
    "meme-status",
    fetchMemeStatus,
    15000
  );

  const { data: scannerScores } = usePolling<MemeScore[]>(
    "meme-scanner",
    fetchMemeScanner,
    30000
  );

  const { data: operacoes } = usePolling<Operacao[]>(
    "meme-operacoes",
    fetchMemeOperacoes,
    15000
  );

  const { data: statsDia } = usePolling<ResumoStats>(
    "meme-stats-dia",
    fetchMemeStatsDia,
    15000
  );

  const { data: statsMes } = usePolling<ResumoStats>(
    `meme-stats-mes-${mesAtual}`,
    () => fetchMemeStatsMes(mesAtual),
    60000
  );

  const { data: operacoesMes } = usePolling<Operacao[]>(
    `meme-operacoes-mes-${mesAtual}`,
    () => fetchMemeOperacoesMes(mesAtual),
    60000
  );

  const { data: reserva } = usePolling<MemeReserva>(
    "meme-reserva",
    fetchMemeReserva,
    60000
  );

  // Derive precoAtual from scanner scores when in position
  useEffect(() => {
    if (memeStatus?.posicao?.posicao && memeStatus.posicao.simbolo && scannerScores) {
      const match = scannerScores.find((s) => s.simbolo === memeStatus.posicao.simbolo);
      if (match) setPrecoAtual(match.preco);
    }
  }, [memeStatus, scannerScores]);

  const rodando = memeStatus?.rodando ?? false;

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <PainelControleMeme />

      <header className="bg-gray-900 border-b border-gray-800 px-4 py-3">
        <div className="max-w-6xl mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold">Bot Meme</h1>
          <div className="flex items-center gap-3">
            <span className={`badge ${rodando ? "badge-ok" : "badge-parado"}`}>
              {rodando ? "● Rodando" : "○ Parado"}
            </span>
            {memeStatus?.ultimo_ciclo && (
              <span className="text-xs text-gray-400">
                Último ciclo: {memeStatus.ultimo_ciclo}
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 space-y-6">

        {/* Evolução do Portfolio */}
        <section>
          <GraficoEvolucaoMeme />
        </section>

        {/* Proteção de Lucros */}
        {reserva && (
          <ReservaLucros
            reserva_label="Reserva isolada USDT"
            reserva_valor={reserva.reserva_isolada_usdt}
            reserva_moeda="USDT"
            reinvestido_valor={reserva.capital_reinvestido_usdt}
            reinvestido_moeda="USDT"
            pnl_pendente={reserva.pnl_liquido_pendente_usdt}
            pnl_moeda="USDT"
            minimo_conversao={3}
            historico={reserva.historico.map((e) => ({
              timestamp: e.timestamp,
              pnl_processado: e.pnl_processado,
              valor_reserva: e.reserva_usdt,
              valor_reinvestido: e.reinvestido_usdt,
            }))}
          />
        )}

        {/* Posição atual */}
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
            Posição Atual
          </h2>
          {memeStatus ? (
            <MemePosicaoCard posicao={memeStatus.posicao ?? { posicao: false }} precoAtual={precoAtual} />
          ) : (
            <div className="rounded-xl bg-gray-800 animate-pulse h-24" />
          )}
        </section>

        {/* Scanner */}
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
            Scanner — Meme Coins
          </h2>
          <div className="bg-gray-900 rounded-xl p-4">
            {scannerScores ? (
              <MemeScannerTabela scores={scannerScores} />
            ) : (
              <div className="rounded-xl bg-gray-800 animate-pulse h-48" />
            )}
          </div>
        </section>

        {/* Stats do dia */}
        {statsDia && (
          <StatsResumo stats={statsDia} titulo={`Hoje — ${statsDia.data ?? ""}`} moeda="USDT" />
        )}

        {/* Stats do mês */}
        {statsMes && (
          <StatsResumo stats={statsMes} titulo={`Mês — ${mesAtual}`} moeda="USDT" />
        )}

        {/* Operações de hoje */}
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
            Operações de hoje
          </h2>
          <div className="bg-gray-900 rounded-xl p-4">
            <TabelaOperacoes operacoes={operacoes ?? []} moeda="USDT" />
          </div>
        </section>

        {/* Operações do mês */}
        {operacoesMes && operacoesMes.length > 0 && (
          <section>
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
              Operações do mês — {mesAtual}
            </h2>
            <div className="bg-gray-900 rounded-xl p-4">
              <TabelaOperacoes operacoes={operacoesMes} moeda="USDT" />
            </div>
          </section>
        )}

      </main>
    </div>
  );
}

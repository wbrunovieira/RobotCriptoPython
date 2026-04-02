"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  tokenSalvo,
  fetchMemeStatus,
  fetchMemeScanner,
  fetchMemeOperacoes,
  fetchMemeStatsDia,
  MemeStatus,
  MemeScore,
  Operacao,
  ResumoStats,
} from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import PainelControleMeme from "@/components/PainelControleMeme";
import MemePosicaoCard from "@/components/MemePosicaoCard";
import MemeScannerTabela from "@/components/MemeScannerTabela";
import StatsResumo from "@/components/StatsResumo";
import TabelaOperacoes from "@/components/TabelaOperacoes";

export default function MemePage() {
  const router = useRouter();
  const [precoAtual, setPrecoAtual] = useState<number | undefined>(undefined);

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
          <StatsResumo stats={statsDia} titulo={`Hoje — ${statsDia.data ?? ""}`} />
        )}

        {/* Operações de hoje */}
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
            Operações de hoje
          </h2>
          <div className="bg-gray-900 rounded-xl p-4">
            <TabelaOperacoes operacoes={operacoes ?? []} />
          </div>
        </section>

      </main>
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  tokenSalvo, fetchPosicoes, fetchStatsDia, fetchOperacoes, fetchReserva,
  fetchStatsMes, downloadFiscalCsv, fetchSaldos,
  Posicao, ResumoStats, Operacao, Reserva, Saldos,
} from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import StatusBadge from "@/components/StatusBadge";
import PosicaoCard from "@/components/PosicaoCard";
import StatsResumo from "@/components/StatsResumo";
import TabelaOperacoes from "@/components/TabelaOperacoes";
import SaldoTotal from "@/components/SaldoTotal";
import PainelControle from "@/components/PainelControle";
import GraficoPerformance from "@/components/GraficoPerformance";
import GraficoEvolucao from "@/components/GraficoEvolucao";
import NotificacaoAportes from "@/components/NotificacaoAportes";

export default function Dashboard() {
  const router = useRouter();
  const [mesAtual] = useState(() => new Date().toISOString().slice(0, 7));
  const [csvLoading, setCsvLoading] = useState(false);
  const [evolucaoKey, setEvolucaoKey] = useState(0);

  useEffect(() => {
    if (!tokenSalvo()) router.push("/login");
  }, [router]);

  const { data: posicoes } = usePolling<Record<string, Posicao>>(
    "posicoes", fetchPosicoes, 15000
  );
  const { data: statsDia } = usePolling<ResumoStats>(
    "stats-dia", () => fetchStatsDia(), 15000
  );
  const { data: statsMes } = usePolling<ResumoStats>(
    `stats-mes-${mesAtual}`, () => fetchStatsMes(mesAtual), 60000
  );
  const { data: operacoes } = usePolling<Operacao[]>(
    "operacoes", () => fetchOperacoes(), 15000
  );
  const { data: reserva } = usePolling<Reserva>(
    "reserva", fetchReserva, 30000
  );
  const { data: saldos } = usePolling<Saldos>(
    "saldos", fetchSaldos, 30000
  );

  async function handleDownloadCsv() {
    setCsvLoading(true);
    try {
      await downloadFiscalCsv(mesAtual);
    } finally {
      setCsvLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <PainelControle />
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-3">
        <div className="max-w-6xl mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold">Cripto Robot</h1>
          <StatusBadge />
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 space-y-6">

        <NotificacaoAportes onAlterado={() => setEvolucaoKey((k) => k + 1)} />

        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Posições</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {posicoes
              ? Object.entries(posicoes).map(([simbolo, pos]) => (
                  <PosicaoCard key={simbolo} simbolo={simbolo} posicao={pos} operacoes={operacoes ?? []} />
                ))
              : ["SOLBRL", "BTCBRL", "ETHBRL", "XRPBRL", "BNBBRL"].map((s) => (
                  <div key={s} className="rounded-xl bg-gray-800 animate-pulse h-28" />
                ))}
          </div>
        </section>

        {saldos && <SaldoTotal saldos={saldos} />}

        {reserva && (
          <section className="bg-gray-900 rounded-xl p-4 grid grid-cols-2 gap-6 sm:grid-cols-4">
            <div>
              <p className="text-xs text-gray-400">Reserva USDC</p>
              <p className="text-xl font-bold font-mono text-blue-400">
                {reserva.reserva_usdc.toFixed(4)} USDC
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Capital reinvestido</p>
              <p className="text-xl font-bold font-mono text-green-400">
                R$ {(reserva.capital_reinvestido_brl ?? 0).toFixed(2)}
              </p>
              <p className="text-xs text-gray-600">adicionado ao capital via lucros</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">P&L líquido pendente</p>
              {(() => {
                const pnl = reserva.pnl_liquido_pendente_brl ?? 0;
                const pos = pnl >= 0;
                return (
                  <>
                    <p className={`text-xl font-bold font-mono ${pnl === 0 ? "text-gray-500" : pos ? "text-yellow-400" : "text-red-400"}`}>
                      {pnl >= 0 ? "+" : ""}R$ {pnl.toFixed(2)}
                    </p>
                    <p className="text-xs text-gray-600">
                      {pnl < 30 && pnl >= 0 ? `faltam R$ ${(30 - pnl).toFixed(2)} para converter` : pnl >= 30 ? "aguardando portfólio subir" : "acumulando"}
                    </p>
                  </>
                );
              })()}
            </div>
            <div>
              <p className="text-xs text-gray-400">Histórico conversões</p>
              <p className="text-xl font-bold font-mono text-gray-300">
                {reserva.historico_conversoes.length}x
              </p>
              <p className="text-xs text-gray-600">operações realizadas</p>
            </div>
          </section>
        )}

        <GraficoEvolucao key={evolucaoKey} />

        <GraficoPerformance />

        {statsDia && <StatsResumo stats={statsDia} titulo={`Hoje — ${statsDia.data ?? ""}`} />}

        {statsMes && (
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
                Mês — {mesAtual}
              </h2>
              <button
                onClick={handleDownloadCsv}
                disabled={csvLoading}
                className="text-xs bg-gray-800 hover:bg-gray-700 px-3 py-1 rounded-lg text-gray-300 transition-colors disabled:opacity-50"
              >
                {csvLoading ? "Gerando..." : "↓ CSV Fiscal"}
              </button>
            </div>
            <StatsResumo stats={statsMes} titulo="No mês" />
          </div>
        )}

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

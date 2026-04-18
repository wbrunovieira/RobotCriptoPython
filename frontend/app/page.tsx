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
import ReservaLucros, { ReservaEntradaNormalizada } from "@/components/ReservaLucros";

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
          <ReservaLucros
            reserva_label="Reserva USDC"
            reserva_valor={reserva.reserva_usdc}
            reserva_moeda="USDC"
            reinvestido_valor={reserva.capital_reinvestido_brl ?? 0}
            reinvestido_moeda="BRL"
            pnl_pendente={reserva.pnl_liquido_pendente_brl ?? 0}
            pnl_moeda="BRL"
            minimo_conversao={30}
            historico={(reserva.historico_conversoes ?? []).map((e): ReservaEntradaNormalizada => ({
              timestamp: e.timestamp,
              pnl_processado: (e.valor_usdc_brl ?? e.valor_brl ?? 0) + (e.valor_reinvest_brl ?? 0),
              valor_reserva: e.valor_usdc_brl ?? e.valor_brl ?? 0,
              valor_reinvestido: e.valor_reinvest_brl ?? 0,
              info_extra: e.taxa_cambio ? `câmbio R$ ${e.taxa_cambio.toFixed(2)}` : undefined,
            }))}
          />
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

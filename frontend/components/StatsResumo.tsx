"use client";
import { ResumoStats } from "@/lib/api";

interface Props {
  stats: ResumoStats;
  titulo?: string;
}

function Metrica({ label, valor, destaque }: { label: string; valor: string; destaque?: "verde" | "vermelho" }) {
  const cor = destaque === "verde" ? "text-green-400" : destaque === "vermelho" ? "text-red-400" : "text-white";
  return (
    <div className="flex flex-col items-center bg-gray-800 rounded-lg p-3">
      <span className="text-xs text-gray-400 mb-1">{label}</span>
      <span className={`text-lg font-bold font-mono ${cor}`}>{valor}</span>
    </div>
  );
}

export default function StatsResumo({ stats, titulo = "Hoje" }: Props) {
  const lucroDestaque = stats.lucro_total_brl > 0 ? "verde" : stats.lucro_total_brl < 0 ? "vermelho" : undefined;

  return (
    <div className="space-y-3">
      {titulo && <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">{titulo}</h2>}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metrica label="Operações" valor={String(stats.total_operacoes)} />
        <Metrica
          label="Lucro"
          valor={`R$ ${stats.lucro_total_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`}
          destaque={lucroDestaque}
        />
        <Metrica label="Acerto" valor={`${stats.taxa_acerto_pct.toFixed(0)}%`} />
        <Metrica
          label="Maior ganho"
          valor={`R$ ${stats.maior_ganho.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`}
          destaque={stats.maior_ganho > 0 ? "verde" : undefined}
        />
      </div>
      {stats.imposto_devido_brl !== undefined && stats.imposto_devido_brl > 0 && (
        <div className="bg-yellow-900/40 border border-yellow-700 rounded-lg p-2 text-sm text-yellow-300">
          ⚠ Imposto estimado: R$ {stats.imposto_devido_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
        </div>
      )}
    </div>
  );
}

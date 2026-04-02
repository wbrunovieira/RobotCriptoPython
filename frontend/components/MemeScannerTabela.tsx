"use client";
import { MemeScore } from "@/lib/api";

interface Props {
  scores: MemeScore[];
}

function scoreBadge(score: number): string {
  if (score >= 8) return "bg-green-900 text-green-300";
  if (score >= 6) return "bg-yellow-900 text-yellow-300";
  return "bg-gray-800 text-gray-400";
}

function rsiColor(rsi: number): string {
  if (rsi > 65 || rsi < 30) return "text-red-400";
  if (rsi >= 50 && rsi <= 65) return "text-green-400";
  return "text-gray-400";
}

function volRatioColor(ratio: number): string {
  if (ratio >= 2.0) return "text-green-400";
  if (ratio >= 1.5) return "text-yellow-400";
  return "text-gray-400";
}

export default function MemeScannerTabela({ scores }: Props) {
  const sorted = [...(scores ?? [])].sort((a, b) => b.score - a.score);

  if (sorted.length === 0) {
    return (
      <p className="text-gray-500 text-sm text-center py-8">
        Nenhum dado do scanner disponível.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-400 border-b border-gray-700">
            <th className="pb-2 pr-4">Símbolo</th>
            <th className="pb-2 pr-4">Score</th>
            <th className="pb-2 pr-4 text-right">Preço</th>
            <th className="pb-2 pr-4 text-right">RSI</th>
            <th className="pb-2 pr-4 text-right">ADX</th>
            <th className="pb-2 pr-4 text-right">Vol ratio</th>
            <th className="pb-2 text-right">Δ candle</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => (
            <tr key={s.simbolo} className="border-b border-gray-800 hover:bg-gray-800/50">
              <td className="py-2 pr-4">
                <span className="font-mono font-semibold text-white">
                  {s.simbolo.replace("USDT", "")}
                </span>
              </td>
              <td className="py-2 pr-4">
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${scoreBadge(s.score)}`}>
                  {s.score}
                </span>
              </td>
              <td className="py-2 pr-4 text-right font-mono text-gray-300">
                {s.preco < 0.01
                  ? s.preco.toFixed(8)
                  : s.preco < 1
                  ? s.preco.toFixed(4)
                  : s.preco.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </td>
              <td className={`py-2 pr-4 text-right font-mono ${rsiColor(s.rsi)}`}>
                {s.rsi.toFixed(1)}
              </td>
              <td className="py-2 pr-4 text-right font-mono text-gray-300">
                {s.adx.toFixed(1)}
              </td>
              <td className={`py-2 pr-4 text-right font-mono ${volRatioColor(s.volume_ratio)}`}>
                {s.volume_ratio.toFixed(2)}x
              </td>
              <td className={`py-2 text-right font-mono ${s.variacao_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                {s.variacao_pct >= 0 ? "+" : ""}{s.variacao_pct.toFixed(2)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

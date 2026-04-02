"use client";
import { MemePosicao } from "@/lib/api";

interface Props {
  posicao: MemePosicao;
  precoAtual?: number;
}

export default function MemePosicaoCard({ posicao, precoAtual }: Props) {
  if (!posicao.posicao) {
    return (
      <div className="bg-gray-900 rounded-xl p-4">
        <p className="text-sm text-gray-500">Sem posição aberta</p>
      </div>
    );
  }

  const pnlPct =
    precoAtual && posicao.preco_entrada
      ? ((precoAtual - posicao.preco_entrada) / posicao.preco_entrada) * 100
      : null;

  function fmtUsdt(val: number | undefined) {
    if (val == null) return "—";
    return `$ ${val.toLocaleString("en-US", { minimumFractionDigits: val < 0.01 ? 8 : 4, maximumFractionDigits: val < 0.01 ? 8 : 4 })}`;
  }

  return (
    <div className="bg-gray-900 border border-green-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-2xl font-bold text-white">
          {posicao.simbolo ? posicao.simbolo.replace("USDT", "") : "—"}
        </h3>
        <span className="px-2 py-1 text-xs font-bold rounded bg-green-900 text-green-300">COMPRADO</span>
      </div>

      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-400">Entrada</span>
          <span className="font-mono text-white">{fmtUsdt(posicao.preco_entrada)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Stop</span>
          <span className="font-mono text-red-400">{fmtUsdt(posicao.stop_price)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Max atingido</span>
          <span className="font-mono text-green-400">{fmtUsdt(posicao.preco_maximo)}</span>
        </div>
        {pnlPct !== null && (
          <div className="flex justify-between border-t border-gray-700 pt-1 mt-1">
            <span className="text-gray-400">P&L atual</span>
            <span className={`font-mono font-bold ${pnlPct >= 0 ? "text-green-400" : "text-red-400"}`}>
              {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

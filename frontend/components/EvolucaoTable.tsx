"use client";
import { useState } from "react";
import { PontoPortfolio, corrigirSaldoDia } from "@/lib/api";

function fmt(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface Props {
  pontos: PontoPortfolio[];
  capitalInicial: number;
  onReload: () => void;
}

export default function EvolucaoTable({ pontos, capitalInicial, onReload }: Props) {
  const [editandoSaldo, setEditandoSaldo] = useState<string | null>(null);
  const [editSaldoValor, setEditSaldoValor] = useState("");

  async function handleSalvarSaldo(data: string) {
    const valor = parseFloat(editSaldoValor.replace(",", "."));
    if (isNaN(valor) || valor <= 0) return;
    await corrigirSaldoDia(data, valor);
    setEditandoSaldo(null);
    onReload();
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs text-gray-400">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="text-left py-1 font-medium">Data</th>
            <th className="text-right py-1 font-medium">Valor total</th>
            <th className="text-right py-1 font-medium">Investido</th>
            <th className="text-right py-1 font-medium">Lucro R$</th>
            <th className="text-right py-1 font-medium">Lucro %</th>
            <th className="text-right py-1 font-medium">Δ dia</th>
          </tr>
        </thead>
        <tbody>
          {pontos.map((p, i) => {
            const pos = p.variacao_brl >= 0;
            const editandoEste = editandoSaldo === p.data;
            const prev = i > 0 ? pontos[i - 1] : null;
            const deltaDia = prev !== null ? p.valor_brl - prev.valor_brl : null;
            const deltaPos = deltaDia !== null ? deltaDia >= 0 : null;
            return (
              <tr key={p.data} className="border-b border-gray-800/50">
                <td className="py-1.5 text-gray-300">
                  {p.data}
                  {p.a_mercado && <span className="ml-1 text-gray-600">(atual)</span>}
                </td>
                <td className="text-right font-mono text-gray-200">
                  {editandoEste ? (
                    <div className="flex gap-1 items-center justify-end">
                      <input
                        type="text"
                        defaultValue={p.valor_brl.toFixed(2).replace(".", ",")}
                        onChange={(e) => setEditSaldoValor(e.target.value)}
                        className="bg-gray-700 text-white text-xs rounded px-1 py-0.5 border border-gray-500 w-24 text-right"
                      />
                      <button onClick={() => handleSalvarSaldo(p.data)} className="text-green-400 hover:text-green-300 font-bold">✓</button>
                      <button onClick={() => setEditandoSaldo(null)} className="text-gray-500 hover:text-gray-400">✕</button>
                    </div>
                  ) : (
                    <span
                      className={`cursor-pointer hover:text-white ${!p.a_mercado ? "underline decoration-dotted" : ""}`}
                      title={!p.a_mercado ? "Clique para corrigir o saldo do dia" : ""}
                      onClick={() => { if (!p.a_mercado) { setEditandoSaldo(p.data); setEditSaldoValor(p.valor_brl.toFixed(2)); } }}
                    >
                      R$ {fmt(p.valor_brl)}
                    </span>
                  )}
                </td>
                <td className="text-right font-mono text-gray-500">
                  R$ {fmt(p.capital_acumulado ?? capitalInicial)}
                </td>
                <td className={`text-right font-mono ${pos ? "text-green-400" : "text-red-400"}`}>
                  {pos ? "+" : ""}R$ {fmt(p.variacao_brl)}
                </td>
                <td className={`text-right font-mono ${pos ? "text-green-400" : "text-red-400"}`}>
                  {pos ? "+" : ""}{p.variacao_pct.toFixed(2)}%
                </td>
                <td className={`text-right font-mono ${deltaPos === null ? "text-gray-600" : deltaPos ? "text-green-400" : "text-red-400"}`}>
                  {deltaDia === null ? "—" : `${deltaPos ? "+" : ""}R$ ${fmt(Math.abs(deltaDia))}`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

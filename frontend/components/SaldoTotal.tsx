"use client";
import { useState } from "react";
import { Saldos } from "@/lib/api";

const ORDEM = ["BTC", "ETH", "SOL", "BNB", "XRP", "USDC", "USDT", "BRL"];

interface Props {
  saldos: Saldos;
}

export default function SaldoTotal({ saldos }: Props) {
  const [emDolar, setEmDolar] = useState(false);
  const [expandido, setExpandido] = useState(false);

  const ativos = Object.entries(saldos.ativos).sort(([a], [b]) => {
    const ia = ORDEM.indexOf(a);
    const ib = ORDEM.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });

  function fmtBrl(v: number) {
    return `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function fmtUsd(v: number) {
    return `US$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  return (
    <div className="bg-gray-900 rounded-xl p-4 space-y-3">
      {/* Header — sempre visível */}
      <div
        className="flex justify-between items-center cursor-pointer"
        onClick={() => setExpandido((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Carteira Binance</h2>
          <span className="text-gray-600 text-xs">{expandido ? "▲" : "▼"}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono font-bold text-white">
            {emDolar ? fmtUsd(saldos.total_usd) : fmtBrl(saldos.total_brl)}
          </span>
          <button
            onClick={(e) => { e.stopPropagation(); setEmDolar((v) => !v); }}
            className="text-xs font-mono text-gray-500 hover:text-gray-300 transition-colors"
          >
            {emDolar ? "US$" : "R$"}
          </button>
        </div>
      </div>

      {/* Detalhes — recolhível */}
      {expandido && (
        <>
          <div className="flex justify-between items-end border-b border-gray-700 pb-3">
            <span className="text-gray-400 text-sm">Total</span>
            <div className="text-right">
              <p className="text-2xl font-bold font-mono text-white">
                {emDolar ? fmtUsd(saldos.total_usd) : fmtBrl(saldos.total_brl)}
              </p>
              <p className="text-xs text-gray-500">
                {emDolar ? fmtBrl(saldos.total_brl) : fmtUsd(saldos.total_usd)}
              </p>
            </div>
          </div>

          <div className="space-y-2">
            {ativos.map(([ativo, dados]) => (
              <div key={ativo} className="flex justify-between items-center text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-gray-200 w-10">{ativo}</span>
                  <span className="text-gray-500 font-mono text-xs">
                    {dados.quantidade.toLocaleString("pt-BR", { maximumFractionDigits: 6 })}
                  </span>
                </div>
                <div className="text-right">
                  <p className="font-mono text-gray-200">
                    {emDolar ? fmtUsd(dados.valor_usd) : fmtBrl(dados.valor_brl)}
                  </p>
                  <p className="font-mono text-xs text-gray-500">
                    {emDolar ? fmtBrl(dados.valor_brl) : fmtUsd(dados.valor_usd)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

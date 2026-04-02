"use client";
import { useState } from "react";
import { Aporte, registrarAporte, deletarAporte, atualizarDataAporte } from "@/lib/api";

function fmt(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function aporteKey(a: Aporte, i: number) {
  return a.order_no ?? `manual_${i}`;
}

interface Props {
  aportes: Aporte[];
  onReload: () => void;
}

export default function AportesPanel({ aportes, onReload }: Props) {
  const [novoData, setNovoData] = useState(() => new Date().toISOString().slice(0, 10));
  const [novoValor, setNovoValor] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [editandoData, setEditandoData] = useState<string | null>(null);
  const [editDataValor, setEditDataValor] = useState("");

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const valor = parseFloat(novoValor.replace(",", "."));
    if (!novoData || isNaN(valor) || valor <= 0) return;
    setSalvando(true);
    try {
      await registrarAporte(novoData, valor);
      setNovoValor("");
      onReload();
    } finally {
      setSalvando(false);
    }
  }

  async function handleDelete(a: Aporte) {
    await deletarAporte(a.order_no, a.data, a.valor_brl);
    onReload();
  }

  async function handleSalvarData(a: Aporte) {
    if (!editDataValor) return;
    await atualizarDataAporte(a, editDataValor);
    setEditandoData(null);
    onReload();
  }

  return (
    <div className="bg-gray-800 rounded-lg p-3 space-y-3">
      <p className="text-xs text-gray-400">
        Registre cada depósito feito na Binance. A variação % mostrará apenas o lucro de trades.
      </p>
      <form onSubmit={handleAdd} className="flex gap-2 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Data</label>
          <input
            type="date"
            value={novoData}
            onChange={(e) => setNovoData(e.target.value)}
            className="bg-gray-700 text-white text-sm rounded px-2 py-1 border border-gray-600"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Valor (R$)</label>
          <input
            type="text"
            placeholder="1000,00"
            value={novoValor}
            onChange={(e) => setNovoValor(e.target.value)}
            className="bg-gray-700 text-white text-sm rounded px-2 py-1 border border-gray-600 w-28"
          />
        </div>
        <button
          type="submit"
          disabled={salvando}
          className="text-xs bg-blue-700 hover:bg-blue-600 px-3 py-1.5 rounded text-white disabled:opacity-50"
        >
          {salvando ? "..." : "+ Adicionar"}
        </button>
      </form>

      {aportes.length > 0 && (
        <table className="w-full text-xs text-gray-400">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="text-left py-1">Data</th>
              <th className="text-right py-1">Valor</th>
              <th className="text-right py-1">Fonte</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {aportes.map((a, i) => {
              const key = aporteKey(a, i);
              const editando = editandoData === key;
              return (
                <tr key={key} className="border-b border-gray-700/50">
                  <td className="py-1.5 text-gray-300">
                    {editando ? (
                      <div className="flex gap-1 items-center">
                        <input
                          type="date"
                          defaultValue={a.data}
                          onChange={(e) => setEditDataValor(e.target.value)}
                          className="bg-gray-600 text-white text-xs rounded px-1 py-0.5 border border-gray-500"
                        />
                        <button
                          onClick={() => handleSalvarData(a)}
                          className="text-green-400 hover:text-green-300 px-1 font-bold"
                        >
                          ✓
                        </button>
                        <button
                          onClick={() => setEditandoData(null)}
                          className="text-gray-500 hover:text-gray-400 px-1"
                        >
                          ✕
                        </button>
                      </div>
                    ) : (
                      <span
                        className="cursor-pointer hover:text-white underline decoration-dotted"
                        title="Clique para corrigir a data"
                        onClick={() => { setEditandoData(key); setEditDataValor(a.data); }}
                      >
                        {a.data}
                      </span>
                    )}
                  </td>
                  <td className="text-right font-mono text-gray-200">R$ {fmt(a.valor_brl)}</td>
                  <td className="text-right text-gray-600">{a.fonte ?? "manual"}</td>
                  <td className="text-right">
                    <button
                      onClick={() => handleDelete(a)}
                      className="text-red-500 hover:text-red-400 px-1"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              );
            })}
            <tr>
              <td className="py-1 text-gray-500 text-xs">Total</td>
              <td className="text-right font-mono font-bold text-gray-200">
                R$ {fmt(aportes.reduce((s, a) => s + a.valor_brl, 0))}
              </td>
              <td colSpan={2} />
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}

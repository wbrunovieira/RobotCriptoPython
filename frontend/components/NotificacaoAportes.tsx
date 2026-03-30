"use client";
import { useEffect, useState } from "react";
import { AportePendente, fetchAportesPendentes, confirmarAporte, rejeitarAporte } from "@/lib/api";

function fmt(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function NotificacaoAportes({ onAlterado }: { onAlterado?: () => void }) {
  const [pendentes, setPendentes] = useState<AportePendente[]>([]);
  const [processando, setProcessando] = useState<string | null>(null);

  function verificar() {
    fetchAportesPendentes().then(setPendentes).catch(() => {});
  }

  useEffect(() => {
    verificar();
    const id = setInterval(verificar, 60_000);
    return () => clearInterval(id);
  }, []);

  if (pendentes.length === 0) return null;

  async function handleConfirmar(p: AportePendente) {
    setProcessando(p.order_no);
    try {
      await confirmarAporte(p);
      setPendentes((prev) => prev.filter((x) => x.order_no !== p.order_no));
      onAlterado?.();
    } finally {
      setProcessando(null);
    }
  }

  async function handleRejeitar(p: AportePendente) {
    setProcessando(p.order_no);
    try {
      await rejeitarAporte(p.order_no);
      setPendentes((prev) => prev.filter((x) => x.order_no !== p.order_no));
    } finally {
      setProcessando(null);
    }
  }

  return (
    <div className="space-y-2">
      {pendentes.map((p) => (
        <div
          key={p.order_no}
          className="bg-yellow-950 border border-yellow-700 rounded-xl px-4 py-3 flex items-center justify-between gap-4"
        >
          <div>
            <p className="text-sm text-yellow-200 font-medium">
              Depósito detectado na Binance em {p.data}
            </p>
            <p className="text-xl font-bold font-mono text-yellow-300">
              R$ {fmt(p.valor_brl)}
            </p>
            <p className="text-xs text-yellow-600 mt-0.5">
              Esse valor é para esta automação?
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => handleConfirmar(p)}
              disabled={processando === p.order_no}
              className="bg-green-700 hover:bg-green-600 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              Sim
            </button>
            <button
              onClick={() => handleRejeitar(p)}
              disabled={processando === p.order_no}
              className="bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm font-semibold px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              Não
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

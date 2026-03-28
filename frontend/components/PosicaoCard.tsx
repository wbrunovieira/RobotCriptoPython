"use client";
import { useState } from "react";
import { Posicao, fetchCandles, fetchCotacao, Candle } from "@/lib/api";
import GraficoPreco from "./GraficoPreco";

interface Props {
  simbolo: string;
  posicao: Posicao;
  operacoes?: import("@/lib/api").Operacao[];
}

export default function PosicaoCard({ simbolo, posicao, operacoes = [] }: Props) {
  const par = simbolo.replace("BRL", "");
  const comprado = posicao.posicao;
  const [mostrarGrafico, setMostrarGrafico] = useState(false);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loadingCandles, setLoadingCandles] = useState(false);
  const [emDolar, setEmDolar] = useState(false);
  const [cotacao, setCotacao] = useState<number | null>(null);

  const variacaoPct =
    comprado && posicao.preco_entrada && posicao.preco_maximo
      ? (((posicao.preco_maximo - posicao.preco_entrada) / posicao.preco_entrada) * 100).toFixed(2)
      : null;

  async function toggleGrafico() {
    if (mostrarGrafico) {
      setMostrarGrafico(false);
      return;
    }
    setLoadingCandles(true);
    try {
      const data = await fetchCandles(simbolo, 100);
      setCandles(data);
      setMostrarGrafico(true);
    } finally {
      setLoadingCandles(false);
    }
  }

  async function toggleMoeda() {
    if (!emDolar && !cotacao) {
      const data = await fetchCotacao();
      setCotacao(data.usd_brl);
    }
    setEmDolar((v) => !v);
  }

  function fmt(brl: number | null | undefined) {
    if (brl == null) return "—";
    const valor = emDolar && cotacao ? brl / cotacao : brl;
    const moeda = emDolar ? "US$" : "R$";
    return `${moeda} ${valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  const opsDoPar = operacoes.filter((op) => op.par === simbolo);

  const ultimaCompra = opsDoPar.filter((op) => op.tipo === "COMPRA").at(-1);
  const valorInvestido = ultimaCompra?.total_brl ?? null;

  return (
    <div className={`card ${comprado ? "card-comprado" : "card-livre"}`}>
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-lg font-bold">{par}</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleMoeda}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors font-mono"
            title={emDolar ? "Mostrar em Reais" : "Mostrar em Dólar"}
          >
            {emDolar ? "US$" : "R$"}
          </button>
          <button
            onClick={toggleGrafico}
            disabled={loadingCandles}
            className="text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-50"
            title={mostrarGrafico ? "Fechar gráfico" : "Ver gráfico"}
          >
            {loadingCandles ? "..." : mostrarGrafico ? "▲ Fechar" : "📈 Gráfico"}
          </button>
          <span className={`badge ${comprado ? "badge-ok" : "badge-neutro"}`}>
            {comprado ? "COMPRADO" : "LIVRE"}
          </span>
        </div>
      </div>

      {comprado && posicao.preco_entrada ? (
        <div className="space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Entrada</span>
            <span className="font-mono">{fmt(posicao.preco_entrada)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Topo</span>
            <span className="font-mono text-green-400">
              {fmt(posicao.preco_maximo)}
              {variacaoPct && <span className="ml-1 text-xs">(+{variacaoPct}%)</span>}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Stop</span>
            <span className="font-mono text-red-400">{fmt(posicao.stop_price)}</span>
          </div>
          {valorInvestido !== null && (
            <div className="flex justify-between border-t border-gray-700 pt-1 mt-1">
              <span className="text-gray-400">Investido</span>
              <span className="font-mono text-yellow-400">{fmt(valorInvestido)}</span>
            </div>
          )}
        </div>
      ) : (
        <p className="text-sm text-gray-500">Aguardando sinal de compra</p>
      )}

      {mostrarGrafico && candles.length > 0 && (
        <div className="mt-3 -mx-4 -mb-4">
          <GraficoPreco
            simbolo={simbolo}
            candles={candles}
            operacoes={opsDoPar}
            stopAtual={posicao.stop_price}
            precoEntrada={posicao.preco_entrada}
            takeProfitPct={0.01}
          />
        </div>
      )}
    </div>
  );
}

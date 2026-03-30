"use client";
import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, AreaSeries, LineSeries } from "lightweight-charts";
import { EvolucaoPortfolio, PontoPortfolio, fetchEvolucaoPortfolio } from "@/lib/api";

function toTimestamp(data: string): number {
  return Math.floor(new Date(data + "T12:00:00Z").getTime() / 1000);
}

function fmt(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function GraficoEvolucao() {
  const [data, setData] = useState<EvolucaoPortfolio | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchEvolucaoPortfolio().then(setData).catch(() => {});
  }, []);

  useEffect(() => {
    if (!containerRef.current || !data || data.pontos.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#111827" },
        textColor: "#9CA3AF",
      },
      grid: {
        vertLines: { color: "#1F2937" },
        horzLines: { color: "#1F2937" },
      },
      width: containerRef.current.clientWidth,
      height: 220,
      timeScale: { timeVisible: false, secondsVisible: false },
      rightPriceScale: { borderColor: "#1F2937" },
      localization: {
        priceFormatter: (v: number) => `R$ ${fmt(v)}`,
      },
    });

    // Linha de referência (capital inicial)
    const refSeries = chart.addSeries(LineSeries, {
      color: "#4B5563",
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      title: "Capital",
    });
    refSeries.setData(
      data.pontos.map((p) => ({
        time: toTimestamp(p.data) as unknown as import("lightweight-charts").Time,
        value: data.capital_inicial,
      }))
    );

    // Área do portfolio
    const positivo = data.pontos[data.pontos.length - 1]?.variacao_brl >= 0;
    const cor = positivo ? "#10B981" : "#EF4444";
    const corFundo = positivo ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)";

    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor: cor,
      topColor: corFundo,
      bottomColor: "rgba(0,0,0,0)",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerRadius: 4,
    });
    areaSeries.setData(
      data.pontos.map((p) => ({
        time: toTimestamp(p.data) as unknown as import("lightweight-charts").Time,
        value: p.valor_brl,
      }))
    );

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current)
        chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [data]);

  const ultimo = data?.pontos[data.pontos.length - 1];
  const positivo = (ultimo?.variacao_brl ?? 0) >= 0;

  return (
    <div className="bg-gray-900 rounded-xl p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
          Evolução do Portfolio
        </h2>
        {ultimo?.a_mercado && (
          <span className="text-xs text-gray-500">preço de mercado</span>
        )}
      </div>

      {/* Cards resumo */}
      {data && ultimo && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-800 rounded-lg px-3 py-2">
            <p className="text-xs text-gray-500 mb-1">Capital inicial</p>
            <p className="text-base font-bold font-mono text-gray-200">
              R$ {fmt(data.capital_inicial)}
            </p>
          </div>
          <div className="bg-gray-800 rounded-lg px-3 py-2">
            <p className="text-xs text-gray-500 mb-1">Valor atual</p>
            <p className="text-base font-bold font-mono text-white">
              R$ {fmt(ultimo.valor_brl)}
            </p>
          </div>
          <div className="bg-gray-800 rounded-lg px-3 py-2">
            <p className="text-xs text-gray-500 mb-1">Resultado</p>
            <p className={`text-base font-bold font-mono ${positivo ? "text-green-400" : "text-red-400"}`}>
              {positivo ? "+" : ""}R$ {fmt(ultimo.variacao_brl)}
              <span className="text-xs ml-1 font-normal">
                ({positivo ? "+" : ""}{ultimo.variacao_pct.toFixed(2)}%)
              </span>
            </p>
          </div>
        </div>
      )}

      {/* Tabela por dia */}
      {data && data.pontos.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-gray-400">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left py-1 font-medium">Data</th>
                <th className="text-right py-1 font-medium">Valor total</th>
                <th className="text-right py-1 font-medium">Variação R$</th>
                <th className="text-right py-1 font-medium">Variação %</th>
              </tr>
            </thead>
            <tbody>
              {data.pontos.map((p) => {
                const pos = p.variacao_brl >= 0;
                return (
                  <tr key={p.data} className="border-b border-gray-800/50">
                    <td className="py-1.5 text-gray-300">
                      {p.data}
                      {p.a_mercado && (
                        <span className="ml-1 text-gray-600">(atual)</span>
                      )}
                    </td>
                    <td className="text-right font-mono text-gray-200">
                      R$ {fmt(p.valor_brl)}
                    </td>
                    <td className={`text-right font-mono ${pos ? "text-green-400" : "text-red-400"}`}>
                      {pos ? "+" : ""}R$ {fmt(p.variacao_brl)}
                    </td>
                    <td className={`text-right font-mono ${pos ? "text-green-400" : "text-red-400"}`}>
                      {pos ? "+" : ""}{p.variacao_pct.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Gráfico */}
      <div ref={containerRef} className="rounded-lg overflow-hidden" />

      <p className="text-xs text-gray-700">
        Dias históricos: BRL + posições ao custo de entrada · Dia atual: preço de mercado Binance
      </p>
    </div>
  );
}

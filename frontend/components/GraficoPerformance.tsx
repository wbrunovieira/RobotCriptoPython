"use client";
import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, LineSeries } from "lightweight-charts";
import { Performance, PerfPonto, fetchPerformance } from "@/lib/api";

type Periodo = "dia" | "semana" | "mes";

const SERIES_CONFIG = [
  { key: "bot",       label: "Bot MACross1", color: "#10B981" },
  { key: "cdi_115",  label: "CDI 115%",     color: "#FBBF24" },
  { key: "ibovespa", label: "IBOVESPA",     color: "#60A5FA" },
  { key: "btc",      label: "BTC",          color: "#A78BFA" },
] as const;

function toTimestamp(data: string): number {
  return Math.floor(new Date(data + "T12:00:00Z").getTime() / 1000);
}

function formatPct(v: number) {
  const sinal = v >= 0 ? "+" : "";
  return `${sinal}${v.toFixed(2)}%`;
}

export default function GraficoPerformance() {
  const [periodo, setPeriodo] = useState<Periodo>("mes");
  const [data, setData] = useState<Performance | null>(null);
  const [carregando, setCarregando] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setCarregando(true);
    fetchPerformance(periodo)
      .then(setData)
      .catch(() => {})
      .finally(() => setCarregando(false));
  }, [periodo]);

  useEffect(() => {
    if (!containerRef.current || !data) return;

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
      height: 280,
      timeScale: { timeVisible: false, secondsVisible: false },
      rightPriceScale: {
        borderColor: "#1F2937",
      },
      localization: {
        priceFormatter: (v: number) => formatPct(v),
      },
    });

    // linha de zero
    const zeroSeries = chart.addSeries(LineSeries, {
      color: "#374151",
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const allDates = data.series.bot.map((p) => p.data);
    zeroSeries.setData(
      allDates.map((d) => ({
        time: toTimestamp(d) as unknown as import("lightweight-charts").Time,
        value: 0,
      }))
    );

    for (const cfg of SERIES_CONFIG) {
      const pontos: PerfPonto[] = data.series[cfg.key];
      if (!pontos.length) continue;

      const serie = chart.addSeries(LineSeries, {
        color: cfg.color,
        lineWidth: 2,
        title: cfg.label,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerRadius: 4,
      });

      serie.setData(
        pontos.map((p) => ({
          time: toTimestamp(p.data) as unknown as import("lightweight-charts").Time,
          value: p.pct,
        }))
      );
    }

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

  // resumo: último valor de cada série
  function ultimo(key: keyof Performance["series"]): number {
    const arr = data?.series[key];
    if (!arr?.length) return 0;
    return arr[arr.length - 1].pct;
  }

  return (
    <div className="bg-gray-900 rounded-xl p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
          Performance vs. Mercado
        </h2>
        <div className="flex gap-1">
          {(["dia", "semana", "mes"] as Periodo[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriodo(p)}
              className={`text-xs px-3 py-1 rounded-lg transition-colors ${
                periodo === p
                  ? "bg-gray-700 text-white"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {p === "dia" ? "Hoje" : p === "semana" ? "7d" : "30d"}
            </button>
          ))}
        </div>
      </div>

      {/* Cards resumo */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {SERIES_CONFIG.map((cfg) => {
            const pct = ultimo(cfg.key);
            const positivo = pct >= 0;
            return (
              <div key={cfg.key} className="bg-gray-800 rounded-lg px-3 py-2">
                <p className="text-xs text-gray-500 mb-1">{cfg.label}</p>
                <p
                  className={`text-lg font-bold font-mono ${
                    positivo ? "text-green-400" : "text-red-400"
                  }`}
                  style={{ color: pct === 0 ? cfg.color : undefined }}
                >
                  {formatPct(pct)}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* Gráfico */}
      {carregando ? (
        <div className="h-64 flex items-center justify-center">
          <span className="text-gray-600 text-sm">Carregando benchmarks...</span>
        </div>
      ) : (
        <div ref={containerRef} className="rounded-lg overflow-hidden" />
      )}

      {/* Legenda */}
      <div className="flex flex-wrap gap-4">
        {SERIES_CONFIG.map((cfg) => (
          <div key={cfg.key} className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 rounded inline-block" style={{ backgroundColor: cfg.color }} />
            <span className="text-xs text-gray-500">{cfg.label}</span>
          </div>
        ))}
      </div>

      <p className="text-xs text-gray-700">
        CDI sintético 13,75% a.a. × 115% · IBOVESPA e BTC via Yahoo Finance
      </p>
    </div>
  );
}

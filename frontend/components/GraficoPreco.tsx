"use client";
import { useEffect, useRef } from "react";
import { createChart, ColorType, CrosshairMode, CandlestickSeries, LineSeries, createSeriesMarkers } from "lightweight-charts";
import { Operacao } from "@/lib/api";

interface CandleData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface Props {
  simbolo: string;
  candles: CandleData[];
  operacoes: Operacao[];
  stopAtual?: number | null;
  precoEntrada?: number | null;
  takeProfitPct?: number;
}

export default function GraficoPreco({ simbolo, candles, operacoes, stopAtual, precoEntrada, takeProfitPct = 0.05 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#111827" },
        textColor: "#9CA3AF",
      },
      grid: {
        vertLines: { color: "#1F2937" },
        horzLines: { color: "#1F2937" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      width: containerRef.current.clientWidth,
      height: 320,
      timeScale: { timeVisible: true, secondsVisible: false },
    });

    // Série de candles (API v5)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10B981",
      downColor: "#EF4444",
      borderVisible: false,
      wickUpColor: "#10B981",
      wickDownColor: "#EF4444",
    });
    candleSeries.setData(
      candles.map((c) => ({ ...c, time: c.time as unknown as import("lightweight-charts").Time }))
    );

    // Marcadores compra/venda
    const markers = operacoes
      .filter((op) => op.timestamp)
      .map((op) => {
        const ts = Math.floor(new Date(op.timestamp).getTime() / 1000);
        const isCompra = op.tipo === "COMPRA";
        return {
          time: ts as unknown as import("lightweight-charts").Time,
          position: isCompra ? ("belowBar" as const) : ("aboveBar" as const),
          color: isCompra ? "#3B82F6" : "#8B5CF6",
          shape: isCompra ? ("arrowUp" as const) : ("arrowDown" as const),
          text: isCompra ? `C R$${op.preco.toFixed(0)}` : `V R$${op.preco.toFixed(0)}`,
        };
      });
    createSeriesMarkers(candleSeries, markers);

    // Linha de stop loss
    if (stopAtual && candles.length > 0) {
      const stopSeries = chart.addSeries(LineSeries, {
        color: "#EF4444",
        lineWidth: 1,
        lineStyle: 2,
        title: `Stop R$${stopAtual.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`,
      });
      stopSeries.setData(
        candles.map((c) => ({
          time: c.time as unknown as import("lightweight-charts").Time,
          value: stopAtual,
        }))
      );
    }

    // Linha de take-profit
    if (precoEntrada && candles.length > 0) {
      const takeProfitPrice = precoEntrada * (1 + takeProfitPct);
      const tpSeries = chart.addSeries(LineSeries, {
        color: "#10B981",
        lineWidth: 1,
        lineStyle: 2,
        title: `TP +${(takeProfitPct * 100).toFixed(0)}% R$${takeProfitPrice.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`,
      });
      tpSeries.setData(
        candles.map((c) => ({
          time: c.time as unknown as import("lightweight-charts").Time,
          value: takeProfitPrice,
        }))
      );
    }

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [candles, operacoes, stopAtual, precoEntrada, takeProfitPct]);

  return (
    <div className="space-y-1">
      <h3 className="text-sm font-semibold text-gray-400">{simbolo}</h3>
      <div ref={containerRef} className="rounded-lg overflow-hidden" />
    </div>
  );
}

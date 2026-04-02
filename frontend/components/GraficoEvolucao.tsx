"use client";
import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, AreaSeries, LineSeries } from "lightweight-charts";
import { EvolucaoPortfolio, PontoPortfolio, fetchEvolucaoPortfolio, Aporte, fetchAportes } from "@/lib/api";
import AportesPanel from "./AportesPanel";
import EvolucaoTable from "./EvolucaoTable";
import MarcosCapital from "./MarcosCapital";

function toTimestamp(data: string): number {
  return Math.floor(new Date(data + "T12:00:00Z").getTime() / 1000);
}

function fmt(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function SummaryCards({ data, ultimo }: { data: EvolucaoPortfolio; ultimo: PontoPortfolio }) {
  const lr = data.lucro_realizado_brl ?? 0;
  const pa = data.pnl_aberto_brl ?? 0;
  const total = lr + pa;
  const investido = data.total_investido ?? data.capital_inicial;
  const pct = investido > 0 ? (total / investido) * 100 : 0;
  const pos = total >= 0;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      <div className="bg-gray-800 rounded-lg px-3 py-2">
        <p className="text-xs text-gray-500 mb-1">Total investido</p>
        <p className="text-base font-bold font-mono text-gray-200">R$ {fmt(investido)}</p>
      </div>
      <div className="bg-gray-800 rounded-lg px-3 py-2">
        <p className="text-xs text-gray-500 mb-1">Valor atual</p>
        <p className="text-base font-bold font-mono text-white">R$ {fmt(ultimo.valor_brl)}</p>
      </div>
      <div className="bg-gray-800 rounded-lg px-3 py-2">
        <p className="text-xs text-gray-500 mb-1">Lucro realizado</p>
        <p className={`text-base font-bold font-mono ${lr >= 0 ? "text-green-400" : "text-red-400"}`}>
          {lr >= 0 ? "+" : ""}R$ {fmt(lr)}
        </p>
        <p className="text-xs text-gray-600 mt-0.5">trades fechados</p>
      </div>
      <div className="bg-gray-800 rounded-lg px-3 py-2">
        <p className="text-xs text-gray-500 mb-1">P&L aberto</p>
        <p className={`text-base font-bold font-mono ${pa === 0 ? "text-gray-500" : pa >= 0 ? "text-green-400" : "text-red-400"}`}>
          {pa === 0 ? "—" : `${pa >= 0 ? "+" : ""}R$ ${fmt(pa)}`}
        </p>
        <p className="text-xs text-gray-600 mt-0.5">posições abertas</p>
      </div>
      <div className={`rounded-lg px-3 py-2 ${pos ? "bg-green-950 border border-green-800" : "bg-red-950 border border-red-800"}`}>
        <p className="text-xs text-gray-400 mb-1">Resultado total</p>
        <p className={`text-base font-bold font-mono ${pos ? "text-green-400" : "text-red-400"}`}>
          {pos ? "+" : ""}R$ {fmt(Math.abs(total))}
        </p>
        <p className={`text-xs font-mono font-semibold ${pos ? "text-green-500" : "text-red-500"}`}>
          {pos ? "+" : ""}{pct.toFixed(2)}%
        </p>
      </div>
    </div>
  );
}

export default function GraficoEvolucao() {
  const [data, setData] = useState<EvolucaoPortfolio | null>(null);
  const [aportes, setAportes] = useState<Aporte[]>([]);
  const [showAportes, setShowAportes] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  function reload() {
    fetchEvolucaoPortfolio().then(setData).catch(() => {});
    fetchAportes().then(setAportes).catch(() => {});
  }

  useEffect(() => { reload(); }, []);

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
      localization: { priceFormatter: (v: number) => `R$ ${fmt(v)}` },
    });

    const refSeries = chart.addSeries(LineSeries, {
      color: "#4B5563",
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      title: "Investido",
    });
    refSeries.setData(
      data.pontos.map((p) => ({
        time: toTimestamp(p.data) as unknown as import("lightweight-charts").Time,
        value: p.capital_acumulado ?? data.capital_inicial,
      }))
    );

    const ultimo = data.pontos[data.pontos.length - 1];
    const positivo = (ultimo?.variacao_brl ?? 0) >= 0;
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

    chart.subscribeCrosshairMove((param) => {
      const tooltip = tooltipRef.current;
      if (!tooltip) return;
      if (!param.time || !param.seriesData.has(areaSeries) || !param.point) {
        tooltip.style.display = "none";
        return;
      }
      const barData = param.seriesData.get(areaSeries) as { value: number };
      const ts = param.time as number;
      const ponto = data.pontos.find(
        (p) => Math.floor(new Date(p.data + "T12:00:00Z").getTime() / 1000) === ts
      );
      if (!ponto) { tooltip.style.display = "none"; return; }
      const pos = ponto.variacao_brl >= 0;
      tooltip.style.display = "block";
      tooltip.style.left = (param.point.x + 14) + "px";
      tooltip.style.top = Math.max(0, param.point.y - 60) + "px";
      tooltip.innerHTML = `
        <div class="text-xs text-gray-400 mb-0.5">${ponto.data}</div>
        <div class="text-sm font-bold font-mono text-white">R$ ${fmt(barData.value)}</div>
        <div class="text-xs font-mono ${pos ? "text-green-400" : "text-red-400"}">
          ${pos ? "+" : ""}R$ ${fmt(ponto.variacao_brl)} (${pos ? "+" : ""}${ponto.variacao_pct.toFixed(2)}%)
        </div>
      `;
    });

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

  return (
    <div className="bg-gray-900 rounded-xl p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
          Evolução do Portfolio
        </h2>
        <div className="flex items-center gap-3">
          {ultimo?.a_mercado && (
            <span className="text-xs text-gray-500">preço de mercado</span>
          )}
          <button
            onClick={() => setShowAportes((v) => !v)}
            className="text-xs bg-gray-800 hover:bg-gray-700 px-3 py-1 rounded-lg text-gray-300 transition-colors"
          >
            {showAportes ? "Fechar aportes" : "Aportes"}
          </button>
        </div>
      </div>

      {showAportes && <AportesPanel aportes={aportes} onReload={reload} />}

      {data && ultimo && <SummaryCards data={data} ultimo={ultimo} />}

      {data && data.pontos.length > 0 && (
        <EvolucaoTable
          pontos={data.pontos}
          capitalInicial={data.capital_inicial}
          onReload={reload}
        />
      )}

      <MarcosCapital aportes={aportes} />

      <div className="relative">
        <div ref={containerRef} className="rounded-lg overflow-hidden" />
        <div
          ref={tooltipRef}
          className="absolute pointer-events-none bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 shadow-lg z-10"
          style={{ display: "none" }}
        />
      </div>

      <p className="text-xs text-gray-700">
        Dias históricos: BRL + posições ao custo de entrada · Dia atual: preço de mercado Binance
      </p>
    </div>
  );
}

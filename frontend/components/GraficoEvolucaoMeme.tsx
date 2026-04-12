"use client";
import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, AreaSeries, LineSeries } from "lightweight-charts";
import {
  EvolucaoMeme,
  PontoMeme,
  MemeAporte,
  fetchEvolucaoMeme,
  fetchMemeAportes,
  registrarMemeAporte,
  deletarMemeAporte,
  atualizarDataMemeAporte,
} from "@/lib/api";

function toTimestamp(data: string): number {
  return Math.floor(new Date(data + "T12:00:00Z").getTime() / 1000);
}

function fmt(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function SummaryCards({ data, ultimo }: { data: EvolucaoMeme; ultimo: PontoMeme }) {
  const lr = data.lucro_realizado_usdt ?? 0;
  const pa = data.pnl_aberto_usdt ?? 0;
  const total = lr + pa;
  const investido = data.total_investido ?? data.capital_inicial;
  const pct = investido > 0 ? (total / investido) * 100 : 0;
  const pos = total >= 0;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      <div className="bg-gray-800 rounded-lg px-3 py-2">
        <p className="text-xs text-gray-500 mb-1">Total investido</p>
        <p className="text-base font-bold font-mono text-gray-200">$ {fmt(investido)}</p>
      </div>
      <div className="bg-gray-800 rounded-lg px-3 py-2">
        <p className="text-xs text-gray-500 mb-1">Valor atual</p>
        <p className="text-base font-bold font-mono text-white">$ {fmt(ultimo.valor_usdt)}</p>
      </div>
      <div className="bg-gray-800 rounded-lg px-3 py-2">
        <p className="text-xs text-gray-500 mb-1">Lucro realizado</p>
        <p className={`text-base font-bold font-mono ${lr >= 0 ? "text-green-400" : "text-red-400"}`}>
          {lr >= 0 ? "+" : ""}$ {fmt(lr)}
        </p>
        <p className="text-xs text-gray-600 mt-0.5">trades fechados</p>
      </div>
      <div className="bg-gray-800 rounded-lg px-3 py-2">
        <p className="text-xs text-gray-500 mb-1">P&L aberto</p>
        <p className={`text-base font-bold font-mono ${pa === 0 ? "text-gray-500" : pa >= 0 ? "text-green-400" : "text-red-400"}`}>
          {pa === 0 ? "—" : `${pa >= 0 ? "+" : ""}$ ${fmt(pa)}`}
        </p>
        <p className="text-xs text-gray-600 mt-0.5">posição aberta</p>
      </div>
      <div className={`rounded-lg px-3 py-2 ${pos ? "bg-green-950 border border-green-800" : "bg-red-950 border border-red-800"}`}>
        <p className="text-xs text-gray-400 mb-1">Resultado total</p>
        <p className={`text-base font-bold font-mono ${pos ? "text-green-400" : "text-red-400"}`}>
          {pos ? "+" : ""}$ {fmt(Math.abs(total))}
        </p>
        <p className={`text-xs font-mono font-semibold ${pos ? "text-green-500" : "text-red-500"}`}>
          {pos ? "+" : ""}{pct.toFixed(2)}%
        </p>
      </div>
    </div>
  );
}

function AportesMemePanel({ aportes, onReload }: { aportes: MemeAporte[]; onReload: () => void }) {
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
      await registrarMemeAporte(novoData, valor);
      setNovoValor("");
      onReload();
    } finally {
      setSalvando(false);
    }
  }

  async function handleDelete(a: MemeAporte) {
    await deletarMemeAporte(a.data, a.valor_usdt);
    onReload();
  }

  async function handleSalvarData(a: MemeAporte) {
    if (!editDataValor) return;
    await atualizarDataMemeAporte(a, editDataValor);
    setEditandoData(null);
    onReload();
  }

  const keyOf = (a: MemeAporte, i: number) => `${a.data}_${i}`;

  return (
    <div className="bg-gray-800 rounded-lg p-3 space-y-3">
      <p className="text-xs text-gray-400">
        Registre cada depósito USDT feito na Binance. A variação % mostrará apenas o lucro de trades.
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
          <label className="text-xs text-gray-500 block mb-1">Valor (USDT)</label>
          <input
            type="text"
            placeholder="100.00"
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
              const key = keyOf(a, i);
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
                        <button onClick={() => handleSalvarData(a)} className="text-green-400 hover:text-green-300 px-1 font-bold">✓</button>
                        <button onClick={() => setEditandoData(null)} className="text-gray-500 hover:text-gray-400 px-1">✕</button>
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
                  <td className="text-right font-mono text-gray-200">$ {fmt(a.valor_usdt)}</td>
                  <td className="text-right text-gray-600">{a.fonte ?? "manual"}</td>
                  <td className="text-right">
                    <button onClick={() => handleDelete(a)} className="text-red-500 hover:text-red-400 px-1">×</button>
                  </td>
                </tr>
              );
            })}
            <tr>
              <td className="py-1 text-gray-500 text-xs">Total</td>
              <td className="text-right font-mono font-bold text-gray-200">
                $ {fmt(aportes.reduce((s, a) => s + a.valor_usdt, 0))}
              </td>
              <td colSpan={2} />
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}

function EvolucaoMemeTable({ pontos, capitalInicial }: { pontos: PontoMeme[]; capitalInicial: number }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs text-gray-400">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="text-left py-1 font-medium">Data</th>
            <th className="text-right py-1 font-medium">Valor total</th>
            <th className="text-right py-1 font-medium">Investido</th>
            <th className="text-right py-1 font-medium">Lucro $</th>
            <th className="text-right py-1 font-medium">Lucro %</th>
            <th className="text-right py-1 font-medium">Δ dia</th>
          </tr>
        </thead>
        <tbody>
          {pontos.map((p, i) => {
            const pos = p.variacao_usdt >= 0;
            const prev = i > 0 ? pontos[i - 1] : null;
            const deltaDia = prev !== null ? p.valor_usdt - prev.valor_usdt : null;
            const deltaPos = deltaDia !== null ? deltaDia >= 0 : null;
            return (
              <tr key={p.data} className="border-b border-gray-800/50">
                <td className="py-1.5 text-gray-300">
                  {p.data}
                  {p.a_mercado && <span className="ml-1 text-gray-600">(atual)</span>}
                </td>
                <td className="text-right font-mono text-gray-200">$ {fmt(p.valor_usdt)}</td>
                <td className="text-right font-mono text-gray-500">
                  $ {fmt(p.capital_acumulado ?? capitalInicial)}
                </td>
                <td className={`text-right font-mono ${pos ? "text-green-400" : "text-red-400"}`}>
                  {pos ? "+" : ""}$ {fmt(p.variacao_usdt)}
                </td>
                <td className={`text-right font-mono ${pos ? "text-green-400" : "text-red-400"}`}>
                  {pos ? "+" : ""}{p.variacao_pct.toFixed(2)}%
                </td>
                <td className={`text-right font-mono ${deltaPos === null ? "text-gray-600" : deltaPos ? "text-green-400" : "text-red-400"}`}>
                  {deltaDia === null ? "—" : `${deltaPos ? "+" : ""}$ ${fmt(Math.abs(deltaDia))}`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function GraficoEvolucaoMeme() {
  const [data, setData] = useState<EvolucaoMeme | null>(null);
  const [aportes, setAportes] = useState<MemeAporte[]>([]);
  const [showAportes, setShowAportes] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  function reload() {
    fetchEvolucaoMeme().then(setData).catch(() => {});
    fetchMemeAportes().then(setAportes).catch(() => {});
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
      localization: { priceFormatter: (v: number) => `$ ${fmt(v)}` },
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
    const positivo = (ultimo?.variacao_usdt ?? 0) >= 0;
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
        value: p.valor_usdt,
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
      const pos = ponto.variacao_usdt >= 0;
      tooltip.style.display = "block";
      tooltip.style.left = (param.point.x + 14) + "px";
      tooltip.style.top = Math.max(0, param.point.y - 60) + "px";
      tooltip.innerHTML = `
        <div class="text-xs text-gray-400 mb-0.5">${ponto.data}</div>
        <div class="text-sm font-bold font-mono text-white">$ ${fmt(barData.value)}</div>
        <div class="text-xs font-mono ${pos ? "text-green-400" : "text-red-400"}">
          ${pos ? "+" : ""}$ ${fmt(ponto.variacao_usdt)} (${pos ? "+" : ""}${ponto.variacao_pct.toFixed(2)}%)
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

      {showAportes && <AportesMemePanel aportes={aportes} onReload={reload} />}

      {data && ultimo && <SummaryCards data={data} ultimo={ultimo} />}

      {data && data.pontos.length > 0 && (
        <EvolucaoMemeTable pontos={data.pontos} capitalInicial={data.capital_inicial} />
      )}

      <div className="relative">
        <div ref={containerRef} className="rounded-lg overflow-hidden" />
        <div
          ref={tooltipRef}
          className="absolute pointer-events-none bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 shadow-lg z-10"
          style={{ display: "none" }}
        />
      </div>

      <p className="text-xs text-gray-700">
        Dias históricos: USDT + posições ao custo de entrada · Dia atual: preço de mercado Binance
      </p>
    </div>
  );
}

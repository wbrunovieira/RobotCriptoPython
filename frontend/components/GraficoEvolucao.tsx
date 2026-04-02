"use client";
import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, AreaSeries, LineSeries } from "lightweight-charts";
import {
  EvolucaoPortfolio, PontoPortfolio, fetchEvolucaoPortfolio,
  Aporte, fetchAportes, registrarAporte, deletarAporte, atualizarDataAporte,
  corrigirSaldoDia,
} from "@/lib/api";

function toTimestamp(data: string): number {
  return Math.floor(new Date(data + "T12:00:00Z").getTime() / 1000);
}

function fmt(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function GraficoEvolucao() {
  const [data, setData] = useState<EvolucaoPortfolio | null>(null);
  const [aportes, setAportes] = useState<Aporte[]>([]);
  const [showAportes, setShowAportes] = useState(false);
  const [novoAporteData, setNovoAporteData] = useState(() => new Date().toISOString().slice(0, 10));
  const [novoAporteValor, setNovoAporteValor] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [editandoData, setEditandoData] = useState<string | null>(null); // order_no ou "manual_<i>"
  const [editDataValor, setEditDataValor] = useState("");
  const [editandoSaldo, setEditandoSaldo] = useState<string | null>(null); // data do ponto
  const [editSaldoValor, setEditSaldoValor] = useState("");
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
      localization: {
        priceFormatter: (v: number) => `R$ ${fmt(v)}`,
      },
    });

    // Linha de referência (capital acumulado)
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

    // Área do portfolio
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
  const positivo = (ultimo?.variacao_brl ?? 0) >= 0;

  async function handleAddAporte(e: React.FormEvent) {
    e.preventDefault();
    const valor = parseFloat(novoAporteValor.replace(",", "."));
    if (!novoAporteData || isNaN(valor) || valor <= 0) return;
    setSalvando(true);
    try {
      await registrarAporte(novoAporteData, valor);
      setNovoAporteValor("");
      reload();
    } finally {
      setSalvando(false);
    }
  }

  async function handleDeleteAporte(a: Aporte) {
    await deletarAporte(a.order_no, a.data, a.valor_brl);
    reload();
  }

  function aporteKey(a: Aporte, i: number) {
    return a.order_no ?? `manual_${i}`;
  }

  async function handleSalvarData(a: Aporte) {
    if (!editDataValor) return;
    await atualizarDataAporte(a, editDataValor);
    setEditandoData(null);
    reload();
  }

  async function handleSalvarSaldo(data: string) {
    const valor = parseFloat(editSaldoValor.replace(",", "."));
    if (isNaN(valor) || valor <= 0) return;
    await corrigirSaldoDia(data, valor);
    setEditandoSaldo(null);
    reload();
  }

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

      {/* Painel de aportes */}
      {showAportes && (
        <div className="bg-gray-800 rounded-lg p-3 space-y-3">
          <p className="text-xs text-gray-400">
            Registre cada depósito feito na Binance. A variação % mostrará apenas o lucro de trades.
          </p>
          <form onSubmit={handleAddAporte} className="flex gap-2 items-end">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Data</label>
              <input
                type="date"
                value={novoAporteData}
                onChange={(e) => setNovoAporteData(e.target.value)}
                className="bg-gray-700 text-white text-sm rounded px-2 py-1 border border-gray-600"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Valor (R$)</label>
              <input
                type="text"
                placeholder="1000,00"
                value={novoAporteValor}
                onChange={(e) => setNovoAporteValor(e.target.value)}
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
                          onClick={() => handleDeleteAporte(a)}
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
      )}

      {/* Cards resumo */}
      {data && ultimo && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="bg-gray-800 rounded-lg px-3 py-2">
            <p className="text-xs text-gray-500 mb-1">Total investido</p>
            <p className="text-base font-bold font-mono text-gray-200">
              R$ {fmt(data.total_investido ?? data.capital_inicial)}
            </p>
          </div>
          <div className="bg-gray-800 rounded-lg px-3 py-2">
            <p className="text-xs text-gray-500 mb-1">Valor atual</p>
            <p className="text-base font-bold font-mono text-white">
              R$ {fmt(ultimo.valor_brl)}
            </p>
          </div>
          <div className="bg-gray-800 rounded-lg px-3 py-2">
            <p className="text-xs text-gray-500 mb-1">Lucro realizado</p>
            {(() => {
              const lr = data.lucro_realizado_brl ?? 0;
              const lrPos = lr >= 0;
              return (
                <p className={`text-base font-bold font-mono ${lrPos ? "text-green-400" : "text-red-400"}`}>
                  {lrPos ? "+" : ""}R$ {fmt(lr)}
                </p>
              );
            })()}
            <p className="text-xs text-gray-600 mt-0.5">trades fechados</p>
          </div>
          <div className="bg-gray-800 rounded-lg px-3 py-2">
            <p className="text-xs text-gray-500 mb-1">P&L aberto</p>
            {(() => {
              const pa = data.pnl_aberto_brl ?? 0;
              const paPos = pa >= 0;
              return (
                <p className={`text-base font-bold font-mono ${pa === 0 ? "text-gray-500" : paPos ? "text-green-400" : "text-red-400"}`}>
                  {pa === 0 ? "—" : `${paPos ? "+" : ""}R$ ${fmt(pa)}`}
                </p>
              );
            })()}
            <p className="text-xs text-gray-600 mt-0.5">posições abertas</p>
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
                <th className="text-right py-1 font-medium">Investido</th>
                <th className="text-right py-1 font-medium">Lucro R$</th>
                <th className="text-right py-1 font-medium">Lucro %</th>
                <th className="text-right py-1 font-medium">Δ dia</th>
              </tr>
            </thead>
            <tbody>
              {data.pontos.map((p, i) => {
                const pos = p.variacao_brl >= 0;
                const editandoEste = editandoSaldo === p.data;
                const prev = i > 0 ? data.pontos[i - 1] : null;
                const deltaDia = prev !== null ? p.valor_brl - prev.valor_brl : null;
                const deltaPos = deltaDia !== null ? deltaDia >= 0 : null;
                return (
                  <tr key={p.data} className="border-b border-gray-800/50">
                    <td className="py-1.5 text-gray-300">
                      {p.data}
                      {p.a_mercado && (
                        <span className="ml-1 text-gray-600">(atual)</span>
                      )}
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
                      R$ {fmt(p.capital_acumulado ?? data.capital_inicial)}
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
      )}

      {/* Gráfico */}
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

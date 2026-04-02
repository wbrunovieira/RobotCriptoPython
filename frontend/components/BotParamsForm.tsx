import { BotParams } from "@/lib/api";

interface Props {
  params: BotParams;
  rodando: boolean;
  onChange: <K extends keyof BotParams>(key: K, value: BotParams[K]) => void;
  onReset: () => void;
}

const CANDLE_OPTIONS = ["1m", "5m", "15m", "30m", "1h", "4h"];

export default function BotParamsForm({ params, rodando, onChange, onReset }: Props) {
  return (
    <section className="space-y-3">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Parâmetros</h3>
      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1 col-span-2">
          <span className="text-xs text-gray-400">ID do Bot</span>
          <input
            type="text"
            value={params.bot_id}
            onChange={(e) => onChange("bot_id", e.target.value)}
            disabled={rodando}
            placeholder="ex: CRv1, bot-agressivo"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
          />
          <span className="text-xs text-gray-600">Aparece como prefixo nas ordens da Binance</span>
        </label>
        <label className="space-y-1">
          <span className="text-xs text-gray-400">Take Profit (%)</span>
          <input
            type="number" step="0.001" min="0"
            value={params.take_profit_pct * 100}
            onChange={(e) => onChange("take_profit_pct", parseFloat(e.target.value) / 100)}
            disabled={rodando}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-gray-400">Stop Trailing (%)</span>
          <input
            type="number" step="0.001" min="0"
            value={params.stop_pct * 100}
            onChange={(e) => onChange("stop_pct", parseFloat(e.target.value) / 100)}
            disabled={rodando}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-gray-400">Teto por par (%)</span>
          <input
            type="number" step="1" min="1" max="100"
            value={params.teto_saldo_pct * 100}
            onChange={(e) => onChange("teto_saldo_pct", parseFloat(e.target.value) / 100)}
            disabled={rodando}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-gray-400">Período candle</span>
          <select
            value={params.periodo_candle}
            onChange={(e) => onChange("periodo_candle", e.target.value)}
            disabled={rodando}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
          >
            {CANDLE_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs text-gray-400">Monitoramento (s)</span>
          <input
            type="number" step="10" min="10"
            value={params.intervalo_monitoramento}
            onChange={(e) => onChange("intervalo_monitoramento", parseInt(e.target.value))}
            disabled={rodando}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-gray-400">Estratégia (min)</span>
          <input
            type="number" step="1" min="1"
            value={params.intervalo_estrategia_min}
            onChange={(e) => onChange("intervalo_estrategia_min", parseInt(e.target.value))}
            disabled={rodando}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-gray-400">Máx. posições</span>
          <input
            type="number" step="1" min="1" max="5"
            value={params.max_posicoes}
            onChange={(e) => onChange("max_posicoes", parseInt(e.target.value))}
            disabled={rodando}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white disabled:opacity-50"
          />
        </label>
      </div>
      {!rodando && (
        <button onClick={onReset} className="text-xs text-gray-500 hover:text-gray-300 underline">
          Restaurar padrões
        </button>
      )}
    </section>
  );
}

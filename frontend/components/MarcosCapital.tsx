import { Aporte } from "@/lib/api";

function fmt(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface Marco {
  data: string;
  capital: number;
  delta: number;
  pct: number;
  tipo: "lucro" | "aporte";
}

interface Props {
  aportes: Aporte[];
}

export default function MarcosCapital({ aportes }: Props) {
  if (aportes.length === 0) return null;

  const sorted = [...aportes].sort((a, b) => a.data.localeCompare(b.data));
  const marcos: Marco[] = [];
  let acumulado = 0;

  for (const a of sorted) {
    const anterior = acumulado;
    acumulado = Math.round((acumulado + a.valor_brl) * 100) / 100;
    const delta = Math.round(a.valor_brl * 100) / 100;
    const pct = anterior > 0 ? (delta / anterior) * 100 : 0;
    marcos.push({
      data: a.data,
      capital: acumulado,
      delta,
      pct,
      tipo: a.fonte === "lucro_reinvestido" ? "lucro" : "aporte",
    });
  }

  return (
    <div>
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
        Marcos de capital
      </p>
      <div className="flex flex-col gap-1">
        {marcos.map((m, i) => (
          <div key={i} className="flex items-center gap-3 text-xs">
            <span className="text-gray-500 w-24 shrink-0">{m.data}</span>
            <span className={`w-2 h-2 rounded-full shrink-0 ${m.tipo === "lucro" ? "bg-green-500" : "bg-blue-500"}`} />
            <span className="font-mono text-gray-200 w-28 shrink-0">R$ {fmt(m.capital)}</span>
            {i > 0 && (
              <span className={`font-mono font-semibold ${m.delta >= 0 ? "text-green-400" : "text-red-400"}`}>
                +R$ {fmt(m.delta)}
                <span className="text-gray-500 ml-1">({m.pct.toFixed(2)}%)</span>
              </span>
            )}
            <span className={`text-xs px-1.5 py-0.5 rounded ${m.tipo === "lucro" ? "bg-green-900 text-green-400" : "bg-blue-900 text-blue-400"}`}>
              {m.tipo === "lucro" ? "lucro reinvestido" : "aporte"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

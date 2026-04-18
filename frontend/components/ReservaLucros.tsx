"use client";

export interface ReservaEntradaNormalizada {
  timestamp: string;
  pnl_processado: number;
  valor_reserva: number;
  valor_reinvestido: number;
  info_extra?: string;
}

interface Props {
  reserva_label: string;
  reserva_valor: number;
  reserva_moeda: string;
  reinvestido_valor: number;
  reinvestido_moeda: string;
  pnl_pendente: number;
  pnl_moeda: string;
  minimo_conversao: number;
  historico: ReservaEntradaNormalizada[];
}

function fmt(v: number, moeda: string) {
  const simbolo = moeda === "BRL" ? "R$" : "$";
  return `${simbolo} ${v.toFixed(moeda === "USDC" ? 4 : 2)} ${moeda === "BRL" ? "" : moeda}`.trim();
}

export default function ReservaLucros({
  reserva_label,
  reserva_valor,
  reserva_moeda,
  reinvestido_valor,
  reinvestido_moeda,
  pnl_pendente,
  pnl_moeda,
  minimo_conversao,
  historico,
}: Props) {
  const pnlPositivo = pnl_pendente >= 0;
  const faltam = minimo_conversao - pnl_pendente;

  return (
    <section className="bg-gray-900 rounded-xl p-4 space-y-4">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
        Proteção de Lucros
      </h2>

      {/* Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="bg-gray-800 rounded-lg p-3">
          <p className="text-xs text-gray-400 mb-1">{reserva_label}</p>
          <p className="text-xl font-bold font-mono text-blue-400">
            {reserva_moeda === "USDC"
              ? `${reserva_valor.toFixed(4)} USDC`
              : `$ ${reserva_valor.toFixed(2)} ${reserva_moeda}`}
          </p>
          <p className="text-xs text-gray-600 mt-1">isolado, fora do capital do bot</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-3">
          <p className="text-xs text-gray-400 mb-1">Reinvestido no capital</p>
          <p className="text-xl font-bold font-mono text-green-400">
            {reinvestido_moeda === "BRL"
              ? `R$ ${reinvestido_valor.toFixed(2)}`
              : `$ ${reinvestido_valor.toFixed(2)} ${reinvestido_moeda}`}
          </p>
          <p className="text-xs text-gray-600 mt-1">adicionado ao capital via lucros</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-3">
          <p className="text-xs text-gray-400 mb-1">P&L pendente</p>
          <p className={`text-xl font-bold font-mono ${
            pnl_pendente === 0 ? "text-gray-500" : pnlPositivo ? "text-yellow-400" : "text-red-400"
          }`}>
            {pnlPositivo ? "+" : ""}
            {pnl_moeda === "BRL"
              ? `R$ ${pnl_pendente.toFixed(2)}`
              : `$ ${pnl_pendente.toFixed(2)} ${pnl_moeda}`}
          </p>
          <p className="text-xs text-gray-600 mt-1">
            {pnl_pendente < minimo_conversao && pnlPositivo
              ? `faltam ${pnl_moeda === "BRL" ? "R$" : "$"} ${faltam.toFixed(2)} para próximo split`
              : pnl_pendente >= minimo_conversao
              ? "aguardando portfólio superar investido"
              : "acumulando"}
          </p>
        </div>
      </div>

      {/* Histórico */}
      {historico.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="text-gray-500 border-b border-gray-700">
                <th className="py-2 pr-4 font-medium">Data</th>
                <th className="py-2 pr-4 font-medium text-right">P&L processado</th>
                <th className="py-2 pr-4 font-medium text-right">→ Reserva</th>
                <th className="py-2 pr-4 font-medium text-right">→ Reinvestido</th>
                {historico.some((e) => e.info_extra) && (
                  <th className="py-2 font-medium text-right">Info</th>
                )}
              </tr>
            </thead>
            <tbody>
              {[...historico].reverse().map((e, i) => (
                <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                  <td className="py-2 pr-4 text-gray-400 whitespace-nowrap">
                    {e.timestamp.slice(0, 16)}
                  </td>
                  <td className="py-2 pr-4 font-mono text-right text-yellow-400">
                    +{fmt(e.pnl_processado, pnl_moeda)}
                  </td>
                  <td className="py-2 pr-4 font-mono text-right text-blue-400">
                    {fmt(e.valor_reserva, reserva_moeda)}
                  </td>
                  <td className="py-2 pr-4 font-mono text-right text-green-400">
                    {fmt(e.valor_reinvestido, reinvestido_moeda)}
                  </td>
                  {historico.some((h) => h.info_extra) && (
                    <td className="py-2 font-mono text-right text-gray-500">
                      {e.info_extra ?? "—"}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs text-gray-600 italic">
          Nenhum split realizado ainda — acumulando P&L pendente.
        </p>
      )}
    </section>
  );
}

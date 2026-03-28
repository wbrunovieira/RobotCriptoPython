"use client";
import { Operacao } from "@/lib/api";

interface Props {
  operacoes: Operacao[];
}

export default function TabelaOperacoes({ operacoes }: Props) {
  if (operacoes.length === 0) {
    return <p className="text-gray-500 text-sm text-center py-8">Nenhuma operação registrada.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-400 border-b border-gray-700">
            <th className="pb-2 pr-4">Hora</th>
            <th className="pb-2 pr-4">Tipo</th>
            <th className="pb-2 pr-4 text-right">Preço</th>
            <th className="pb-2 pr-4 text-right">Qtd</th>
            <th className="pb-2 pr-4 text-right">Total</th>
            <th className="pb-2 text-right">Lucro</th>
          </tr>
        </thead>
        <tbody>
          {operacoes.map((op, i) => {
            const isCompra = op.tipo === "COMPRA";
            const lucroColor = op.lucro_brl
              ? op.lucro_brl > 0 ? "text-green-400" : "text-red-400"
              : "";
            return (
              <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="py-2 pr-4 text-gray-400 font-mono text-xs">{op.timestamp}</td>
                <td className="py-2 pr-4">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${isCompra ? "bg-blue-900 text-blue-300" : "bg-purple-900 text-purple-300"}`}>
                    {op.tipo}
                  </span>
                </td>
                <td className="py-2 pr-4 text-right font-mono">
                  R$ {op.preco.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </td>
                <td className="py-2 pr-4 text-right font-mono">{op.quantidade}</td>
                <td className="py-2 pr-4 text-right font-mono">
                  R$ {op.total_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </td>
                <td className={`py-2 text-right font-mono ${lucroColor}`}>
                  {op.lucro_brl !== undefined
                    ? `R$ ${op.lucro_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

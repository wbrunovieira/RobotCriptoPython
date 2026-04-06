"use client";
import { Operacao } from "@/lib/api";

interface Props {
  operacoes: Operacao[];
  moeda?: "BRL" | "USDT";
}

function fmtPreco(valor: number, moeda: "BRL" | "USDT"): string {
  if (moeda === "USDT") {
    // Preços de meme coins podem ter muitas casas decimais
    if (valor < 0.0001) return `$ ${valor.toFixed(8)}`;
    if (valor < 0.01)   return `$ ${valor.toFixed(6)}`;
    if (valor < 1)      return `$ ${valor.toFixed(4)}`;
    return `$ ${valor.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
  }
  return `R$ ${valor.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;
}

function fmtValor(valor: number, moeda: "BRL" | "USDT"): string {
  if (moeda === "USDT") {
    return `$ ${valor.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  }
  return `R$ ${valor.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;
}

function fmtPar(par: string, moeda: "BRL" | "USDT"): string {
  return moeda === "USDT" ? par.replace("USDT", "") : par.replace("BRL", "");
}

export default function TabelaOperacoes({ operacoes, moeda = "BRL" }: Props) {
  if (operacoes.length === 0) {
    return <p className="text-gray-500 text-sm text-center py-8">Nenhuma operação registrada.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-400 border-b border-gray-700">
            <th className="pb-2 pr-4">Hora</th>
            <th className="pb-2 pr-4">Par</th>
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
            const lucroColor = op.lucro_brl != null
              ? op.lucro_brl > 0 ? "text-green-400" : op.lucro_brl < 0 ? "text-red-400" : ""
              : "";
            return (
              <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="py-2 pr-4 text-gray-400 font-mono text-xs">{op.timestamp}</td>
                <td className="py-2 pr-4">
                  {op.par ? (
                    <span className="text-xs font-mono font-semibold text-gray-300">
                      {fmtPar(op.par, moeda)}
                    </span>
                  ) : "—"}
                </td>
                <td className="py-2 pr-4">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${isCompra ? "bg-blue-900 text-blue-300" : "bg-purple-900 text-purple-300"}`}>
                    {op.tipo}
                  </span>
                </td>
                <td className="py-2 pr-4 text-right font-mono text-xs">
                  {fmtPreco(op.preco, moeda)}
                </td>
                <td className="py-2 pr-4 text-right font-mono">{op.quantidade}</td>
                <td className="py-2 pr-4 text-right font-mono">
                  {fmtValor(op.total_brl, moeda)}
                </td>
                <td className={`py-2 text-right font-mono ${lucroColor}`}>
                  {op.lucro_brl != null ? fmtValor(op.lucro_brl, moeda) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

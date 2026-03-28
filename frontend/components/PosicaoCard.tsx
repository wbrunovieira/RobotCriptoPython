"use client";
import { Posicao } from "@/lib/api";

interface Props {
  simbolo: string;
  posicao: Posicao;
}

export default function PosicaoCard({ simbolo, posicao }: Props) {
  const par = simbolo.replace("BRL", "");
  const comprado = posicao.posicao;

  const variacaoPct =
    comprado && posicao.preco_entrada && posicao.preco_maximo
      ? (((posicao.preco_maximo - posicao.preco_entrada) / posicao.preco_entrada) * 100).toFixed(2)
      : null;

  return (
    <div className={`card ${comprado ? "card-comprado" : "card-livre"}`}>
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-lg font-bold">{par}</h3>
        <span className={`badge ${comprado ? "badge-ok" : "badge-neutro"}`}>
          {comprado ? "COMPRADO" : "LIVRE"}
        </span>
      </div>

      {comprado && posicao.preco_entrada ? (
        <div className="space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Entrada</span>
            <span className="font-mono">R$ {posicao.preco_entrada.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Topo</span>
            <span className="font-mono text-green-400">
              R$ {posicao.preco_maximo?.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
              {variacaoPct && <span className="ml-1 text-xs">(+{variacaoPct}%)</span>}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Stop</span>
            <span className="font-mono text-red-400">
              R$ {posicao.stop_price?.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
            </span>
          </div>
        </div>
      ) : (
        <p className="text-sm text-gray-500">Aguardando sinal de compra</p>
      )}
    </div>
  );
}

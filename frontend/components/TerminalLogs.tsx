import { useRef, useEffect } from "react";

type SseStatus = "desconectado" | "conectando" | "conectado" | "erro";

const sseDot: Record<SseStatus, string> = {
  desconectado: "bg-gray-600",
  conectando:   "bg-yellow-400 animate-pulse",
  conectado:    "bg-blue-400",
  erro:         "bg-red-500",
};

function lineColor(linha: string): string {
  if (linha.includes("COMPRA")) return "text-green-400";
  if (linha.includes("VENDA") || linha.includes("Take-Profit") || linha.includes("Stop")) return "text-red-400";
  if (linha.includes("Erro") || linha.includes("erro") || linha.includes("ERROR")) return "text-yellow-400";
  return "text-gray-400";
}

interface Props {
  logs: string[];
  sseStatus: SseStatus;
}

export default function TerminalLogs({ logs, sseStatus }: Props) {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Terminal</h3>
        <span className={`w-1.5 h-1.5 rounded-full ${sseDot[sseStatus]}`} title={sseStatus} />
        <span className="text-xs text-gray-600">{sseStatus}</span>
        <span className="ml-auto text-xs text-gray-600">{logs.length} linhas</span>
      </div>
      <div className="bg-gray-900 rounded-xl p-3 h-96 overflow-y-auto font-mono text-xs border border-gray-800">
        {logs.length === 0 ? (
          <p className="text-gray-600">
            {sseStatus === "conectando" ? "Conectando ao stream..." : "Sem logs ainda."}
          </p>
        ) : (
          logs.map((linha, i) => (
            <div key={i} className={`leading-relaxed whitespace-pre-wrap break-all ${lineColor(linha)}`}>
              {linha || "\u00a0"}
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </section>
  );
}

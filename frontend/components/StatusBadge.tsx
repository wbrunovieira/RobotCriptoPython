"use client";
import { usePolling } from "@/hooks/usePolling";
import { fetchStatus, Status } from "@/lib/api";

export default function StatusBadge() {
  const { data, error } = usePolling<Status>("status", fetchStatus, 30000);

  if (error) return <span className="badge badge-erro">Erro de conexão</span>;
  if (!data) return <span className="badge badge-neutro">Carregando...</span>;

  return (
    <div className="flex items-center gap-3">
      <span className={`badge ${data.rodando ? "badge-ok" : "badge-parado"}`}>
        {data.rodando ? "● Bot rodando" : "○ Bot parado"}
      </span>
      {data.ultimo_ciclo && (
        <span className="text-xs text-gray-400">
          Último ciclo: {data.ultimo_ciclo}
        </span>
      )}
    </div>
  );
}

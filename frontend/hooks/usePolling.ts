import useSWR from "swr";

/**
 * Hook genérico de polling — chama fetcher a cada `intervalMs` ms.
 * Usa SWR para cache, deduplicação e revalidação automática.
 */
export function usePolling<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  intervalMs = 15000
) {
  return useSWR<T>(key, fetcher, {
    refreshInterval: intervalMs,
    revalidateOnFocus: true,
    shouldRetryOnError: false,
  });
}

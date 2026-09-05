import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { GamesQuery, MistakesQuery, QueueFilters, Settings } from "./types";

export const keys = {
  status: ["status"] as const,
  dashboard: ["dashboard"] as const,
  settings: ["settings"] as const,
  games: (q: GamesQuery) => ["games", q] as const,
  game: (id: string) => ["game", id] as const,
  mistakes: (q: MistakesQuery) => ["mistakes", q] as const,
  queue: (f: QueueFilters) => ["queue", f] as const,
  leeches: ["leeches"] as const,
  puzzle: (id: string) => ["puzzle", id] as const,
};

export const useStatus = () =>
  useQuery({
    queryKey: keys.status,
    queryFn: api.status,
    refetchInterval: (q) => (q.state.data?.job.state === "running" ? 2000 : false),
  });
export const useDashboard = () => useQuery({ queryKey: keys.dashboard, queryFn: api.dashboard });
export const useSettings = () => useQuery({ queryKey: keys.settings, queryFn: api.settings });
export const useGames = (q: GamesQuery) => useQuery({ queryKey: keys.games(q), queryFn: () => api.games(q) });
export const useGame = (id: string) => useQuery({ queryKey: keys.game(id), queryFn: () => api.game(id) });
export const useMistakes = (q: MistakesQuery) => useQuery({ queryKey: keys.mistakes(q), queryFn: () => api.mistakes(q) });
export const useQueue = (f: QueueFilters, enabled = true) => useQuery({ queryKey: keys.queue(f), queryFn: () => api.queue(f), enabled });
export const useLeeches = () => useQuery({ queryKey: keys.leeches, queryFn: api.leeches });
export const usePuzzleQuery = (id: string | null) =>
  useQuery({ queryKey: keys.puzzle(id ?? ""), queryFn: () => api.puzzle(id!), enabled: !!id });

/**
 * Invalida os dados derivados de um job quando ele termina.
 *
 * `useStatus` faz polling a cada 2 s enquanto o job roda; na transição
 * running -> idle|error o restante do app (dashboard, partidas, erros, fila)
 * continuaria mostrando dados antigos. Montar uma vez em `App`.
 */
export function useJobWatcher() {
  const qc = useQueryClient();
  const { data } = useStatus();
  const prev = useRef<string | undefined>(undefined);
  const state = data?.job.state;
  useEffect(() => {
    const before = prev.current;
    prev.current = state;
    if (before === "running" && state !== undefined && state !== "running") {
      for (const k of [["status"], ["dashboard"], ["queue"], ["games"], ["game"], ["mistakes"], ["leeches"]]) {
        void qc.invalidateQueries({ queryKey: k });
      }
    }
  }, [state, qc]);
}

function useInvalidate(extra: readonly (readonly unknown[])[] = []) {
  const qc = useQueryClient();
  return () => {
    for (const k of [keys.status, keys.dashboard, ["queue"], ["game"], ...extra]) void qc.invalidateQueries({ queryKey: k });
  };
}

export function useStartJob() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (p: { kind: "import" | "analyze" | "regenerate"; limit?: number; game_id?: string }) =>
      p.kind === "import" ? api.importGames() : p.kind === "analyze" ? api.analyze({ limit: p.limit, game_id: p.game_id }) : api.regenerate(),
    onSettled: invalidate,
  });
}
export function useCancelJob() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.cancelJob, onSettled: invalidate });
}
export function useSaveSettings() {
  const invalidate = useInvalidate([keys.settings]);
  return useMutation({ mutationFn: (body: Partial<Settings>) => api.saveSettings(body), onSettled: invalidate });
}
export function useUnleech() {
  const invalidate = useInvalidate([keys.leeches, ["mistakes"]]);
  return useMutation({ mutationFn: (id: string) => api.unleech(id), onSettled: invalidate });
}

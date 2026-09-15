import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  ChapterIn,
  ChapterOut,
  ChapterSaveIn,
  GamesQuery,
  MistakesQuery,
  OpeningsDb,
  QueueFilters,
  SaveTacticIn,
  SettingsIn,
  StudyImportIn,
  StudyIn,
  StudyUpdateIn,
} from "./types";

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
  studies: ["studies"] as const,
  study: (id: string) => ["studies", id] as const,
  chapter: (id: string, cid: string) => ["studies", id, "chapters", cid] as const,
  tacticsStatus: ["tactics", "status"] as const,
  tacticThemes: ["tactics", "themes"] as const,
  themeStats: (days: number) => ["stats", "themes", days] as const,
  progress: (days: number) => ["stats", "progress", days] as const,
  coachStatus: ["coach", "status"] as const,
  coachExplanation: (id: string) => ["coach", "explanation", id] as const,
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
/** Contagem/itens da fila com esses filtros; meio minuto de cache basta para mexer nos filtros sem consultar a cada clique. */
export const useQueue = (f: QueueFilters, enabled = true) =>
  useQuery({ queryKey: keys.queue(f), queryFn: () => api.queue(f), enabled, staleTime: 30_000 });
export const useLeeches = () => useQuery({ queryKey: keys.leeches, queryFn: api.leeches });
export const usePuzzleQuery = (id: string | null) =>
  useQuery({ queryKey: keys.puzzle(id ?? ""), queryFn: () => api.puzzle(id!), enabled: !!id });
export const useStudies = (enabled = true) =>
  useQuery({ queryKey: keys.studies, queryFn: api.studies, enabled });
export const useStudy = (id: string | null) =>
  useQuery({ queryKey: keys.study(id ?? ""), queryFn: () => api.study(id!), enabled: !!id });
export const useChapter = (id: string | null, cid: string | null) =>
  useQuery({
    queryKey: keys.chapter(id ?? "", cid ?? ""),
    queryFn: () => api.chapter(id!, cid!),
    enabled: !!id && !!cid,
  });
export const useTacticsStatus = (enabled = true) =>
  useQuery({ queryKey: keys.tacticsStatus, queryFn: api.tacticsStatus, enabled });
export const useTacticThemes = () =>
  useQuery({ queryKey: keys.tacticThemes, queryFn: api.tacticThemes });
export const useThemeStats = (days = 30) =>
  useQuery({ queryKey: keys.themeStats(days), queryFn: () => api.themeStats(days) });
export const useProgress = (days = 90) =>
  useQuery({ queryKey: keys.progress(days), queryFn: () => api.progress(days) });
/**
 * Livro de aberturas da posição. O explorador do Lichess é limitado por IP e a
 * resposta de uma FEN não muda: guardamos para sempre e não reintentamos.
 */
/** Estado do treinador: quem manda no cartão aparecer ou não, e muda pouco. */
export const useCoachStatus = () =>
  useQuery({ queryKey: keys.coachStatus, queryFn: api.coachStatus, staleTime: 30_000 });
/** Explicação já guardada do exercício (`null` quando ainda não pediram uma). */
export const useCoachExplanation = (puzzleId: string, enabled: boolean) =>
  useQuery({ queryKey: keys.coachExplanation(puzzleId), queryFn: () => api.coachExplanation(puzzleId), enabled });
/** Pede a explicação ao treinador; a resposta já entra no cache do exercício. */
export function useExplain() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { puzzle_id: string; review_id?: string }) => api.coachExplain(body),
    onSuccess: (exp) => qc.setQueryData(keys.coachExplanation(exp.puzzle_id), exp),
  });
}

export const useOpenings = (fen: string | null, db: OpeningsDb) =>
  useQuery({
    queryKey: ["openings", db, fen],
    queryFn: () => api.openings(fen!, db),
    enabled: !!fen,
    staleTime: Infinity,
    retry: 0,
    retryOnMount: false,
  });

export const useAnalyse = (fen: string | null) =>
  useQuery({
    queryKey: ["analyse", fen],
    queryFn: () => api.analyse(fen!),
    enabled: !!fen,
    staleTime: Infinity,
    retry: 0,
  });

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
      for (const k of [["status"], ["dashboard"], ["queue"], ["games"], ["game"], ["mistakes"], ["leeches"], ["tactics"], ["stats"], ["studies"], ["puzzle"]]) {
        void qc.invalidateQueries({ queryKey: k });
      }
    }
  }, [state, qc]);
}

function useInvalidate(extra: readonly (readonly unknown[])[] = []) {
  const qc = useQueryClient();
  return () => {
    for (const k of [keys.status, keys.dashboard, ["queue"], ["game"], ["tactics"], ...extra]) void qc.invalidateQueries({ queryKey: k });
  };
}

export function useStartJob() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (p: { kind: "import" | "analyze" | "regenerate" | "extend_puzzles" | "import_lichess" | "import_study" | "coach_reindex"; limit?: number; game_id?: string; avoidOnly?: boolean; study?: StudyImportIn }) =>
      p.kind === "import" ? api.importGames()
        : p.kind === "analyze" ? api.analyze({ limit: p.limit, game_id: p.game_id })
        : p.kind === "import_lichess" ? api.importTactics()
        : p.kind === "import_study" ? api.importStudy(p.study ?? {})
        : p.kind === "coach_reindex" ? api.coachReindex()
        : p.kind === "extend_puzzles" ? api.extendPuzzles()
        : api.regenerate(p.avoidOnly ? "avoid" : undefined),
    onSettled: invalidate,
  });
}
export function useCancelJob() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.cancelJob, onSettled: invalidate });
}
export function useSaveSettings() {
  const invalidate = useInvalidate([keys.settings]);
  return useMutation({ mutationFn: (body: SettingsIn) => api.saveSettings(body), onSettled: invalidate });
}
export function useUnleech() {
  const invalidate = useInvalidate([keys.leeches, ["mistakes"]]);
  return useMutation({ mutationFn: (id: string) => api.unleech(id), onSettled: invalidate });
}

/** Tirar/voltar um exercício da repetição espaçada. */
export function useSetQueue() {
  const invalidate = useInvalidate([["puzzle"], ["mistakes"], keys.leeches, keys.studies]);
  return useMutation({
    mutationFn: (p: { id: string; in_queue: boolean }) => api.setQueue(p.id, p.in_queue),
    onSettled: invalidate,
  });
}

/** Guardar uma tática do Lichess como exercício da repetição (com o resultado
 *  da tentativa, quando há um: aí ela já entra agendada). */
export function useSaveTactic() {
  const invalidate = useInvalidate([["puzzle"]]);
  return useMutation({
    mutationFn: (p: { id: string; body?: SaveTacticIn }) => api.saveTactic(p.id, p.body),
    onSettled: invalidate,
  });
}

/** Importar um estudo do Lichess (URL ou PGN colado): job assíncrono. */
export function useImportStudy() {
  const start = useStartJob();
  return {
    mutate: (study: StudyImportIn) => start.mutate({ kind: "import_study", study }),
    isPending: start.isPending,
    error: start.error,
    reset: start.reset,
  };
}

/** Criar e renomear estudos locais (o editor também reordena capítulos por aqui). */
export function useStudyEditor() {
  const invalidate = useInvalidate([keys.studies]);
  const create = useMutation({ mutationFn: (body: StudyIn) => api.createStudy(body), onSettled: invalidate });
  const update = useMutation({
    mutationFn: (p: { id: string; body: StudyUpdateIn }) => api.updateStudy(p.id, p.body),
    onSettled: invalidate,
  });
  return { create, update };
}

/** Criar, salvar, duplicar e remover capítulos. */
export function useChapterActions(studyId: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    for (const k of [keys.studies, keys.study(studyId), keys.dashboard, ["queue"], ["puzzle"]])
      void qc.invalidateQueries({ queryKey: k });
  };
  const create = useMutation({
    mutationFn: (body: ChapterIn) => api.createChapter(studyId, body),
    onSettled: invalidate,
  });
  const save = useMutation({
    mutationFn: (p: { cid: string; body: ChapterSaveIn }) => api.saveChapter(studyId, p.cid, p.body),
    onSuccess: (ch) => qc.setQueryData(keys.chapter(studyId, ch.id), ch),
    onSettled: invalidate,
  });
  const duplicate = useMutation({
    mutationFn: (cid: string) => api.duplicateChapter(studyId, cid),
    onSettled: invalidate,
  });
  const remove = useMutation({
    mutationFn: (cid: string) => api.deleteChapter(studyId, cid),
    onSettled: invalidate,
  });
  return { create, save, duplicate, remove };
}

/**
 * Vira um capítulo de leitura em exercício (ou volta pra leitura): busca a
 * árvore atual e salva de novo só trocando o modo. Se não sobrar exercício
 * (sem lances), quem chama decide o que mostrar a partir do `puzzle_id` da
 * resposta.
 */
export function useToggleChapterMode(studyId: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    for (const k of [keys.studies, keys.study(studyId), keys.dashboard, ["queue"], ["puzzle"]])
      void qc.invalidateQueries({ queryKey: k });
  };
  return useMutation({
    mutationFn: async (p: { cid: string; mode: ChapterOut["mode"] }) => {
      const ch = await api.chapter(studyId, p.cid);
      return api.saveChapter(studyId, p.cid, {
        name: ch.name,
        mode: p.mode,
        orientation: ch.orientation,
        tree: ch.tree,
      });
    },
    onSuccess: (ch) => qc.setQueryData(keys.chapter(studyId, ch.id), ch),
    onSettled: invalidate,
  });
}

/** Reimportar, tirar/voltar da repetição e remover um estudo. */
export function useStudyActions() {
  const invalidate = useInvalidate([keys.studies, ["puzzle"], ["mistakes"], keys.leeches]);
  const reimport = useMutation({ mutationFn: (id: string) => api.reimportStudy(id), onSettled: invalidate });
  const setQueue = useMutation({
    mutationFn: (p: { id: string; in_queue: boolean }) => api.setStudyQueue(p.id, p.in_queue),
    onSettled: invalidate,
  });
  const remove = useMutation({ mutationFn: (id: string) => api.deleteStudy(id), onSettled: invalidate });
  return { reimport, setQueue, remove };
}

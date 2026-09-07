import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AnalyseOut } from "../api/types";
import { classifyMove } from "./classify";
import type { Classification } from "./classify";
import { fenAt } from "./moveTree";
import type { Tree, TreeNode } from "./moveTree";

/** Teto de meios-lances classificados por caminho. */
export const MAX_LANCES = 60;

const NENHUMA: Map<string, Classification> = new Map();

export interface MoveClassificationOptions {
  /** Configuração `classify_moves`: desligada, nada é consultado. */
  enabled: boolean;
  thresholds: { mistake: number; blunder: number };
  /** Ids dos nós que estão no livro de mestres (`useBookMoves`). */
  bookIds: Set<string>;
}

/**
 * Classificação de cada lance do caminho atual (raiz → nó atual).
 *
 * Cada posição do caminho é analisada uma vez: a inicial e a de depois de
 * cada lance. A análise de um lance usa a posição de onde ele parte e a
 * posição a que ele leva, então uma consulta serve a dois lances.
 *
 * As consultas são as mesmas de `useAnalyse` (mesma chave e mesmo cache,
 * guardado para sempre), então navegar pela árvore não repete trabalho. Não
 * há escalonamento: a engine do servidor tem lock e serializa as chamadas
 * sozinha. Os lances vão sendo classificados conforme as respostas chegam.
 */
export function useMoveClassification(
  tree: Tree,
  path: TreeNode[],
  { enabled, thresholds, bookIds }: MoveClassificationOptions,
): Map<string, Classification> {
  const nos = useMemo(() => path.slice(0, MAX_LANCES), [path]);
  const fens = useMemo(
    () => (nos.length === 0 ? [] : [fenAt(tree, null), ...nos.map((n) => fenAt(tree, n.id))]),
    [tree, nos],
  );

  const results = useQueries({
    queries: fens.map((fen) => ({
      queryKey: ["analyse", fen],
      queryFn: () => api.analyse(fen),
      enabled,
      staleTime: Infinity,
      retry: 0,
      // consulta que deu erro (engine indisponível) não volta a rodar quando o nó reaparece
      retryOnMount: false,
    })),
  });

  const dados: (AnalyseOut | undefined)[] = results.map((r) => r.data);

  // A resposta de uma FEN não muda, então basta saber quais já chegaram para
  // saber se o mapa mudou; assim ele mantém a identidade entre renderizações.
  const assinatura = [
    thresholds.mistake,
    thresholds.blunder,
    nos.map((n) => `${n.id}${bookIds.has(n.id) ? "*" : ""}`).join(","),
    dados.map((d) => (d ? "1" : "0")).join(""),
  ].join("|");

  return useMemo(() => {
    const mapa = new Map<string, Classification>();
    for (let i = 0; i < nos.length; i++) {
      const parent = dados[i];
      if (!parent) continue;
      const c = classifyMove({
        parent,
        child: dados[i + 1] ?? null,
        uci: nos[i].uci,
        isBook: bookIds.has(nos[i].id),
        thresholds,
      });
      if (c) mapa.set(nos[i].id, c);
    }
    return mapa.size === 0 ? NENHUMA : mapa;
    // `assinatura` resume tudo que entra no cálculo (ver acima)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assinatura]);
}

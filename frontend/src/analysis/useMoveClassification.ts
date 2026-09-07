import { useMemo } from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { api } from "../api/client";
import type { AnalyseOut } from "../api/types";
import { uciToMove } from "../board/line";
import { classifyMove } from "./classify";
import type { Classification } from "./classify";
import type { Tree, TreeNode } from "./moveTree";

/** Teto de meios-lances classificados por caminho (os últimos do caminho). */
export const MAX_LANCES = 60;

/**
 * Quantas posições sem resposta podem estar sendo consultadas ao mesmo tempo.
 * A engine do servidor tem lock e resolve uma consulta por vez, então uma fila
 * maior só ocuparia as conexões do navegador sem adiantar nada.
 */
export const MAX_EM_VOO = 2;

const NENHUMA: ReadonlyMap<string, Classification> = new Map();

export interface MoveClassificationOptions {
  /** Configuração `classify_moves`: desligada, nada é consultado. */
  enabled: boolean;
  thresholds: { mistake: number; blunder: number };
  /** Ids dos nós que estão no livro de mestres (`useBookMoves`). */
  bookIds: Set<string>;
}

/**
 * Classificação de cada lance do caminho atual (os `MAX_LANCES` últimos, até
 * o nó atual).
 *
 * Cada posição do caminho é analisada uma vez: a de onde parte o primeiro
 * lance classificado e a de depois de cada lance. A análise de um lance usa a
 * posição de onde ele parte e a posição a que ele leva, então uma consulta
 * serve a dois lances.
 *
 * As consultas são as mesmas de `useAnalyse` (mesma chave e mesmo cache: a
 * resposta não envelhece e fica guardada enquanto a posição estiver em uso,
 * mais os 5 minutos de `gcTime` do React Query), então navegar pela árvore não
 * repete trabalho. Elas saem da posição atual para trás, poucas por vez
 * (`MAX_EM_VOO`): a engine do servidor tem lock e serializa tudo, então quem
 * sai antes é resolvido antes — e o que interessa primeiro é o lance que está
 * na tela. Os lances vão sendo classificados conforme as respostas chegam.
 */
export function useMoveClassification(
  tree: Tree,
  path: TreeNode[],
  { enabled, thresholds, bookIds }: MoveClassificationOptions,
): ReadonlyMap<string, Classification> {
  // O teto corta a cabeça do caminho, não a cauda: o que interessa é o lance
  // na tela e os que vieram logo antes dele.
  const inicio = Math.max(0, path.length - MAX_LANCES);
  const nos = useMemo(() => path.slice(inicio), [path, inicio]);
  // uma caminhada só, desde a raiz: a posição de onde parte o primeiro lance
  // classificado e a de depois de cada um deles
  const fens = useMemo(() => {
    if (nos.length === 0) return [];
    const chess = new Chess(tree.fen);
    const out: string[] = [];
    for (const [k, n] of path.entries()) {
      // na raiz vale a FEN da árvore, como em `fenAt`: a normalização do
      // chess.js daria outra chave de cache para a mesma posição
      if (k === inicio) out.push(inicio === 0 ? tree.fen : chess.fen());
      try {
        chess.move(uciToMove(n.uci));
      } catch {
        break;
      }
      if (k >= inicio) out.push(chess.fen());
    }
    return out;
  }, [tree, path, nos, inicio]);

  // Da posição atual para trás: é esta a ordem em que as consultas saem.
  const ordem = useMemo(() => fens.map((_, i) => fens.length - 1 - i), [fens]);

  const client = useQueryClient();
  const janela = new Set<number>();
  for (const i of ordem) {
    if (janela.size >= MAX_EM_VOO) break;
    // resposta ou erro já em mãos: a posição não ocupa vaga (erro não repete,
    // então segurar a vaga dele travaria o resto do caminho para sempre)
    const estado = client.getQueryState(["analyse", fens[i]]);
    if (estado?.status === "success" || estado?.status === "error") continue;
    janela.add(i);
  }

  const results = useQueries({
    queries: ordem.map((i) => ({
      queryKey: ["analyse", fens[i]],
      queryFn: () => api.analyse(fens[i]),
      enabled: enabled && janela.has(i),
      staleTime: Infinity,
      retry: 0,
      // consulta que deu erro (engine indisponível) não volta a rodar quando o nó reaparece
      retryOnMount: false,
    })),
  });

  // de volta à ordem do caminho: `dados[i]` é a análise de `fens[i]`
  const dados: (AnalyseOut | undefined)[] = [];
  ordem.forEach((i, k) => {
    dados[i] = results[k].data;
  });

  // A resposta de uma FEN não muda, então basta saber quais já chegaram para
  // saber se o mapa mudou; assim ele mantém a identidade entre renderizações.
  // As FENs entram na conta: dois capítulos podem repetir os ids dos nós.
  const assinatura = [
    thresholds.mistake,
    thresholds.blunder,
    nos.map((n) => `${n.id}${bookIds.has(n.id) ? "*" : ""}`).join(","),
    fens.join(","),
    fens.map((_, i) => (dados[i] ? "1" : "0")).join(""),
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

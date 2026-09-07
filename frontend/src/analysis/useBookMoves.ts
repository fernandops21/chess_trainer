import { useMemo } from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { OpeningsOut } from "../api/types";
import { fenAt } from "./moveTree";
import type { Tree, TreeNode } from "./moveTree";

const NENHUM: Set<string> = new Set();

const chaveDe = (fen: string) => ["openings", "masters", fen] as const;

/**
 * Quais lances do caminho atual aparecem no livro de mestres.
 *
 * Cada lance é olhado na posição de onde ele parte (a posição inicial da
 * árvore, no primeiro). Fora do livro (posição sem partidas ou consulta que
 * falhou) as posições seguintes não são consultadas: elas não teriam como
 * estar no livro por este caminho, e cada consulta é uma chamada ao Lichess.
 * Por isso as posições entram uma de cada vez, conforme a anterior responde.
 *
 * A resposta de uma FEN não muda: as consultas são as mesmas de
 * `useOpenings` (mesma chave e mesmo cache, guardado para sempre).
 *
 * Sem token o proxy responde 400; aqui isso só significa "nenhum símbolo",
 * sem aviso na tela — quem quiser o livro tem a aba Aberturas explicando.
 */
export function useBookMoves(tree: Tree, path: TreeNode[]): Set<string> {
  const qc = useQueryClient();
  const fens = useMemo(
    () => path.map((_, i) => fenAt(tree, i === 0 ? null : path[i - 1].id)),
    [tree, path],
  );

  // Até onde já dá para consultar: o cache diz o que as posições anteriores
  // responderam. A primeira que ainda não respondeu (ou que saiu do livro)
  // é a última habilitada; as de trás dela só ligam quando ela responder.
  let limite = fens.length;
  for (let i = 0; i < fens.length; i++) {
    const estado = qc.getQueryState<OpeningsOut>(chaveDe(fens[i]));
    if (estado?.status !== "success" || estado.data === undefined || estado.data.total === 0) {
      limite = i + 1;
      break;
    }
  }

  const results = useQueries({
    queries: fens.map((fen, i) => ({
      queryKey: chaveDe(fen),
      queryFn: () => api.openings(fen, "masters"),
      enabled: i < limite,
      staleTime: Infinity,
      retry: 0,
      // consulta que deu erro (sem token) não volta a rodar quando o nó reaparece no caminho
      retryOnMount: false,
    })),
  });

  const ids: string[] = [];
  for (let i = 0; i < path.length; i++) {
    const r = results[i];
    if (!r || r.isError || r.data === undefined || r.data.total === 0) break;
    if (r.data.moves.some((m) => m.uci === path[i].uci)) ids.push(path[i].id);
  }

  // conjunto estável enquanto os ids forem os mesmos (ids não têm espaço)
  const marca = ids.join(" ");
  return useMemo(() => (marca === "" ? NENHUM : new Set(marca.split(" "))), [marca]);
}

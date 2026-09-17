import type { SaveTacticIn, TacticOut } from "../api/types";
import type { Bloco } from "./BlocoContext";
import type { SessionConfig } from "./SessionStart";

/** O item i do bloco, ou nulo quando acabou. */
export const itemDoBloco = (bloco: Bloco, i: number): TacticOut | null => bloco.itens[i] ?? null;

/** O que se manda para `saveTactic` depois de uma tentativa do bloco: o irmão entra na fila com
 *  o vínculo para o exercício de origem (só quando a âncora é exercício próprio) e o degrau da
 *  cascata que o trouxe (`sibling_tier`, sempre que conhecido — independe da âncora ser própria
 *  ou do Lichess). `tacticId` é o item do bloco que acabou de ser tentado. */
export function corpoDoSalvamento(
  bloco: Bloco,
  r: { correct: boolean; used_hint: boolean; duration_ms: number; session_id?: string | null },
  tacticId: string,
): SaveTacticIn {
  return { correct: r.correct, used_hint: r.used_hint, duration_ms: r.duration_ms, session_id: r.session_id ?? undefined,
           sibling_of: bloco.anchorOrigem === "own" ? bloco.anchorId : undefined,
           sibling_tier: bloco.tiers[tacticId] };
}

/** A configuração de sessão que o cartão abre: sem tempo — repetir os irmãos não é contra o
 *  relógio (`plannedMinutes: 0` deixaria o relógio sempre "esgotado" e abriria o modal de
 *  tempo a cada "Próximo"; `null` é o mesmo "sem tempo" que a tela de início usa). */
export const configDoBloco = (bloco: Bloco): SessionConfig =>
  ({ source: "tactics", mode: "bloco", filters: {}, plannedMinutes: null, themes: [], bloco });

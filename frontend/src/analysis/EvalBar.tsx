import type { Color } from "../api/types";
import { formatEval } from "../lib/format";

const MATE_MIN = 90_000;

/** Fração da barra que é das brancas (0 a 1) a partir do score em centipeões, ponto de vista das brancas. */
export function fracaoBrancas(cpBrancas: number): number {
  if (cpBrancas >= MATE_MIN) return 1;
  if (cpBrancas <= -MATE_MIN) return 0;
  // mesma curva do Lichess: chance de vitória em função dos centipeões
  const chance = 2 / (1 + Math.exp(-0.00368208 * cpBrancas)) - 1;
  return Math.min(0.97, Math.max(0.03, (1 + chance) / 2));
}

/**
 * Barra de vantagem ao lado do tabuleiro, como no chess.com: branca cresce
 * quando as brancas estão melhor. `score` é o da engine (ponto de vista de
 * quem joga em `turn`); `terminal` cobre mate/afogamento/empate na posição.
 */
export function EvalBar({ score, turn, orientation, terminal }:
  { score: number | null | undefined; turn: Color; orientation: Color; terminal?: string | null }) {
  let cp: number | null = null;
  if (terminal === "checkmate") cp = turn === "white" ? -MATE_MIN : MATE_MIN;
  else if (terminal) cp = 0;
  else if (score != null) cp = turn === "white" ? score : -score;
  const fracao = cp == null ? 0.5 : fracaoBrancas(cp);
  // com as pretas embaixo a barra vira: a parte branca fica em cima
  const brancasEmbaixo = orientation === "white";
  const rotulo = cp == null ? "…" : terminal === "checkmate" ? (cp > 0 ? "1-0" : "0-1") : terminal ? "½" : formatEval(cp);
  return (
    <div className={`eval-bar${brancasEmbaixo ? "" : " eval-bar--invertida"}`} role="img"
      aria-label={cp == null ? "avaliação indisponível" : `avaliação ${rotulo}`} title={`avaliação ${rotulo}`}>
      <div className="eval-bar__brancas" style={{ height: `${(fracao * 100).toFixed(1)}%` }} />
      <span className={`eval-bar__rotulo${cp != null && cp < 0 ? " eval-bar__rotulo--pretas" : ""}`}>{rotulo}</span>
    </div>
  );
}

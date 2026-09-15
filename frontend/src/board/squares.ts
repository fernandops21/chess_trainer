import type { Key } from "chessground/types";

/** Lado de uma casa em porcentagem do tabuleiro (8 casas = 100%). */
export const CASA_PCT = 12.5;

/**
 * Posição de uma casa em porcentagem, conforme a orientação; `topo`/`direita`
 * dizem se ela encosta na borda de cima ou da direita (selos e seletores que
 * saem da casa precisam saber para não vazar do tabuleiro).
 */
export function squarePercent(square: Key, orientation: "white" | "black"): { left: number; top: number; topo: boolean; direita: boolean } {
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]) - 1;
  const col = orientation === "white" ? file : 7 - file;
  const row = orientation === "white" ? 7 - rank : rank;
  return { left: col * CASA_PCT, top: row * CASA_PCT, topo: row === 0, direita: col === 7 };
}

import type { Color, PuzzleKind } from "../api/types";

const MATE_THRESHOLD = 90_000;
const MATE_SCORE = 100_000;

export function formatEval(cp: number): string {
  if (Math.abs(cp) >= MATE_THRESHOLD) {
    const n = MATE_SCORE - Math.abs(cp);
    return cp > 0 ? `#${n}` : `#-${n}`;
  }
  if (cp === 0) return "0.00";
  const v = (cp / 100).toFixed(2);
  return cp > 0 ? `+${v}` : v;
}

export function formatDate(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export const colorName = (c: Color) =>
  c === "white" ? "Brancas" : "Pretas";

export const kindLabel = (k: PuzzleKind) =>
  k === "punish" ? "punir o erro" : "evitar o erro";

const THEMES: Record<string, string> = {
  hanging_piece: "peça pendurada",
  fork: "garfo",
  pin: "cravada",
  discovered_attack: "ataque descoberto",
  tactic: "tática",
};

export function themeLabel(theme: string): string {
  if (theme.startsWith("mate_in_")) return `mate em ${theme.slice(8)}`;
  return THEMES[theme] ?? theme;
}

export function resultLabel(result: string, myColor: Color): string {
  if (result === "1/2-1/2") return "empate";
  const iWon =
    (result === "1-0" && myColor === "white") ||
    (result === "0-1" && myColor === "black");
  if (result === "1-0" || result === "0-1") return iWon ? "vitória" : "derrota";
  return result;
}

export const levelLabel = (level: string | null) =>
  level === "blunder" ? "blunder" : level === "mistake" ? "erro" : "";

import type { Color, PuzzleKind, PuzzleOut } from "../api/types";

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

/** Temas do banco do Lichess (cópia de `core/tactics/themes.py: THEME_LABELS`). */
export const LICHESS_THEMES: Record<string, string> = {
  fork: "garfo", pin: "cravada", skewer: "espeto", discoveredAttack: "ataque descoberto",
  doubleCheck: "xeque duplo", hangingPiece: "peça pendurada", trappedPiece: "peça presa",
  deflection: "desvio", attraction: "atração", clearance: "limpeza", interference: "interferência",
  intermezzo: "lance intermediário", sacrifice: "sacrifício", xRayAttack: "raio X",
  capturingDefender: "captura do defensor", backRankMate: "mate na última fileira",
  smotheredMate: "mate sufocado", anastasiaMate: "mate de Anastasia", arabianMate: "mate árabe",
  bodenMate: "mate de Boden", doubleBishopMate: "mate dos dois bispos", dovetailMate: "mate cauda de andorinha",
  hookMate: "mate do gancho", killBoxMate: "mate da caixa", vukovicMate: "mate de Vukovic",
  promotion: "promoção", underPromotion: "subpromoção", advancedPawn: "peão avançado",
  exposedKing: "rei exposto", kingsideAttack: "ataque na ala do rei", queensideAttack: "ataque na ala da dama",
  attackingF2F7: "ataque a f2/f7", quietMove: "lance quieto", defensiveMove: "lance defensivo",
  zugzwang: "zugzwang", enPassant: "en passant", castling: "roque",
  mateIn1: "mate em 1", mateIn2: "mate em 2", mateIn3: "mate em 3", mateIn4: "mate em 4", mateIn5: "mate em 5",
  mate: "mate", crushing: "esmagador", advantage: "vantagem", equality: "igualdade",
  opening: "abertura", middlegame: "meio-jogo", endgame: "final",
  pawnEndgame: "final de peões", rookEndgame: "final de torres", bishopEndgame: "final de bispos",
  knightEndgame: "final de cavalos", queenEndgame: "final de damas", queenRookEndgame: "final de dama e torre",
  oneMove: "um lance", short: "curto", long: "longo", veryLong: "muito longo",
  master: "partida de mestre", masterVsMaster: "mestre contra mestre", superGM: "super GM",
  tactic: "tática",
  discoveredCheck: "xeque descoberto",
  operaMate: "mate da ópera",
  pillsburysMate: "mate de Pillsbury",
  epauletteMate: "mate de dragonas",
  cornerMate: "mate no canto",
  triangleMate: "mate do triângulo",
  collinearMove: "lance na mesma linha",
  morphysMate: "mate de Morphy",
  swallowstailMate: "mate cauda de andorinha (torre)",
  blindSwineMate: "mate dos porcos cegos",
  balestraMate: "mate da balestra",
};

export function themeLabel(theme: string): string {
  if (theme.startsWith("mate_in_")) return `mate em ${theme.slice(8)}`;
  return THEMES[theme] ?? LICHESS_THEMES[theme] ?? theme;
}

export function resultLabel(result: string, myColor: Color): string {
  if (result === "1/2-1/2") return "empate";
  const iWon =
    (result === "1-0" && myColor === "white") ||
    (result === "0-1" && myColor === "black");
  if (result === "1-0" || result === "0-1") return iWon ? "vitória" : "derrota";
  return result;
}

/** Nome curto do exercício, conforme a fonte: partida, capítulo do estudo ou tática guardada. */
export function puzzleTitle(p: PuzzleOut): string {
  if (p.game && p.ply != null) return `${p.game.white} × ${p.game.black}, lance ${Math.ceil(p.ply / 2)}`;
  if (p.study) return `${p.study.title} · ${p.study.chapter_name}`;
  if (p.source === "lichess") return "tática do Lichess guardada";
  return "exercício";
}

export const levelLabel = (level: string | null) =>
  level === "blunder" ? "blunder" : level === "mistake" ? "erro" : "";

import { novoChess } from "../lib/chess";
import type { Color, Key, Piece, Role } from "chessground/types";

/**
 * Montagem de posição: as peças de cada casa, o lado a jogar e os roques,
 * traduzidos de e para FEN. Tudo aqui é função pura — quem guarda o estado é
 * o `PositionEditor`.
 */

/** Peças por casa; é o mesmo formato que o chessground usa por dentro. */
export type EditorBoard = Map<Key, Piece>;

/** Os quatro roques da FEN: brancas rei/dama, pretas rei/dama. */
export interface Castling {
  K: boolean;
  Q: boolean;
  k: boolean;
  q: boolean;
}

export const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const FILES = "abcdefgh";
const ROLE_OF: Record<string, Role> = {
  p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king",
};
const LETTER_OF: Record<Role, string> = {
  pawn: "p", knight: "n", bishop: "b", rook: "r", queen: "q", king: "k",
};

/** Peças de uma FEN (ou só da parte das peças, que é o que o chessground devolve). */
export function boardFromFen(fen: string): EditorBoard {
  const board: EditorBoard = new Map();
  const rows = fen.trim().split(" ")[0].split("/");
  for (let i = 0; i < rows.length && i < 8; i++) {
    const rank = 8 - i;
    let file = 0;
    for (const ch of rows[i]) {
      const vazias = Number(ch);
      if (!Number.isNaN(vazias)) {
        file += vazias;
        continue;
      }
      const role = ROLE_OF[ch.toLowerCase()];
      if (role && file < 8) {
        board.set(`${FILES[file]}${rank}` as Key, { role, color: ch === ch.toUpperCase() ? "white" : "black" });
      }
      file++;
    }
  }
  return board;
}

/** FEN completa da posição montada: en passant vazio, meio-lance 0, lance 1. */
export function fenFromBoard(board: EditorBoard, turn: Color, castling: Castling): string {
  const rows: string[] = [];
  for (let rank = 8; rank >= 1; rank--) {
    let row = "";
    let vazias = 0;
    for (const file of FILES) {
      const p = board.get(`${file}${rank}` as Key);
      if (!p) {
        vazias++;
        continue;
      }
      if (vazias > 0) {
        row += vazias;
        vazias = 0;
      }
      const letra = LETTER_OF[p.role];
      row += p.color === "white" ? letra.toUpperCase() : letra;
    }
    if (vazias > 0) row += vazias;
    rows.push(row);
  }
  const roques =
    (castling.K ? "K" : "") + (castling.Q ? "Q" : "") + (castling.k ? "k" : "") + (castling.q ? "q" : "");
  return `${rows.join("/")} ${turn === "white" ? "w" : "b"} ${roques || "-"} - 0 1`;
}

/** Lado a jogar de uma FEN (brancas quando o campo falta). */
export function turnFromFen(fen: string): Color {
  return fen.trim().split(" ")[1] === "b" ? "black" : "white";
}

/** Roques marcados numa FEN. */
export function castlingFromFen(fen: string): Castling {
  const campo = fen.trim().split(" ")[2] ?? "-";
  return {
    K: campo.includes("K"),
    Q: campo.includes("Q"),
    k: campo.includes("k"),
    q: campo.includes("q"),
  };
}

const ehPeca = (board: EditorBoard, key: string, role: Role, color: Color) => {
  const p = board.get(key as Key);
  return !!p && p.role === role && p.color === color;
};

/**
 * Quais roques a posição permite: só existem com o rei na casa de origem e a
 * torre no canto. Os que não cabem ficam desmarcados e desabilitados na tela.
 */
export function castlingAvailable(board: EditorBoard): Castling {
  const reiBranco = ehPeca(board, "e1", "king", "white");
  const reiPreto = ehPeca(board, "e8", "king", "black");
  return {
    K: reiBranco && ehPeca(board, "h1", "rook", "white"),
    Q: reiBranco && ehPeca(board, "a1", "rook", "white"),
    k: reiPreto && ehPeca(board, "h8", "rook", "black"),
    q: reiPreto && ehPeca(board, "a8", "rook", "black"),
  };
}

/** Só os roques que a posição permite (o resto sai da FEN). */
export function keepAvailable(castling: Castling, board: EditorBoard): Castling {
  const pode = castlingAvailable(board);
  return { K: castling.K && pode.K, Q: castling.Q && pode.Q, k: castling.k && pode.k, q: castling.q && pode.q };
}

/** A parte das peças tem oito fileiras de oito casas, com letras conhecidas. */
function placementOk(fen: string): boolean {
  const rows = fen.trim().split(" ")[0].split("/");
  if (rows.length !== 8) return false;
  return rows.every((row) => {
    let casas = 0;
    for (const ch of row) {
      const vazias = Number(ch);
      if (!Number.isNaN(vazias)) {
        if (vazias < 1 || vazias > 8) return false;
        casas += vazias;
      } else if (ROLE_OF[ch.toLowerCase()]) casas++;
      else return false;
    }
    return casas === 8;
  });
}

/** Posição montada: o que o editor guarda. */
export interface Position {
  board: EditorBoard;
  turn: Color;
  castling: Castling;
}

/**
 * Lê uma FEN colada pelo usuário. Devolve `null` quando o texto nem chega a
 * ser um tabuleiro — aí o editor avisa e fica na posição anterior. Posições
 * que existem mas são impossíveis (dois reis, peão na oitava) entram: quem
 * reclama delas é o `validatePosition`, com o erro na tela.
 */
export function parseFen(fen: string): Position | null {
  if (!placementOk(fen)) return null;
  return { board: boardFromFen(fen), turn: turnFromFen(fen), castling: castlingFromFen(fen) };
}

const COR = { white: "brancas", black: "pretas" } as const;
const REI = { white: "branco", black: "preto" } as const;

/**
 * O que impede a posição de virar uma partida, em português. Lista vazia quer
 * dizer que dá para usar. O chess.js recusa parte disso com exceção, então as
 * regras vêm daqui — a mensagem dele não serviria para mostrar na tela.
 */
export function validatePosition(fen: string): string[] {
  // Texto que nem chega a ser um tabuleiro (FEN colada pela metade, por
  // exemplo): um aviso só, senão sairia "falta o rei" para cada cor.
  if (!placementOk(fen)) return ["Posição inválida."];
  const board = boardFromFen(fen);
  const turn = turnFromFen(fen);
  const erros: string[] = [];

  const cores: Color[] = ["white", "black"];
  const pecas = { white: 0, black: 0 };
  const peoes = { white: 0, black: 0 };
  const reis = { white: 0, black: 0 };
  let peaoNaBorda = false;
  for (const [key, p] of board) {
    pecas[p.color]++;
    if (p.role === "king") reis[p.color]++;
    if (p.role === "pawn") {
      peoes[p.color]++;
      const rank = key[1];
      if (rank === "1" || rank === "8") peaoNaBorda = true;
    }
  }

  for (const c of cores) {
    if (reis[c] === 0) erros.push(`Falta o rei ${REI[c]}.`);
    else if (reis[c] > 1) erros.push(`Há mais de um rei ${REI[c]}.`);
  }
  if (peaoNaBorda) erros.push("Há peões na primeira ou na última fileira.");
  for (const c of cores) {
    if (pecas[c] > 16) erros.push(`As ${COR[c]} têm mais de 16 peças.`);
    if (peoes[c] > 8) erros.push(`As ${COR[c]} têm mais de 8 peões.`);
  }

  // Rei de quem não joga em xeque: seria uma posição impossível (o lance
  // anterior deixaria o rei atacado). O chess.js não checa isso, então
  // carregamos a mesma posição com o outro lado a jogar e perguntamos.
  if (reis.white === 1 && reis.black === 1 && !peaoNaBorda) {
    const parado: Color = turn === "white" ? "black" : "white";
    try {
      const campos = fen.trim().split(" ");
      campos[1] = parado === "white" ? "w" : "b";
      campos[3] = "-";
      if (novoChess(campos.join(" ")).inCheck()) {
        erros.push(`O rei ${REI[parado]} está em xeque e é a vez das ${COR[turn]}.`);
      }
    } catch {
      // FEN que o chess.js não carrega: o aviso geral abaixo cobre
    }
  }

  if (erros.length > 0) return erros;
  try {
    novoChess(fen);
  } catch {
    return ["Posição inválida."];
  }
  return [];
}

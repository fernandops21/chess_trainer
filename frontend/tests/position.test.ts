import { expect, test } from "vitest";
import type { Key } from "chessground/types";
import {
  START_FEN,
  boardFromFen,
  castlingAvailable,
  castlingFromFen,
  fenFromBoard,
  parseFen,
  turnFromFen,
  validatePosition,
} from "../src/analysis/position";

const TODOS = { K: true, Q: true, k: true, q: true };
const NENHUM = { K: false, Q: false, k: false, q: false };

test("a posição inicial vai e volta sem mudar", () => {
  const board = boardFromFen(START_FEN);
  expect(board.size).toBe(32);
  expect(board.get("e1" as Key)).toEqual({ role: "king", color: "white" });
  expect(board.get("d8" as Key)).toEqual({ role: "queen", color: "black" });
  expect(fenFromBoard(board, "white", TODOS)).toBe(START_FEN);
});

test("a FEN sai com casas vazias contadas e sem roques quando não há nenhum", () => {
  const fen = "4k3/8/8/8/8/8/4P3/4K3 b - - 0 1";
  const board = boardFromFen(fen);
  expect(board.size).toBe(3);
  expect(fenFromBoard(board, "black", NENHUM)).toBe(fen);
});

test("boardFromFen aceita só a parte das peças (é o que o chessground devolve)", () => {
  const board = boardFromFen("4k3/8/8/8/8/8/8/4K3");
  expect(board.size).toBe(2);
  expect(board.get("e8" as Key)).toEqual({ role: "king", color: "black" });
});

test("a FEN montada sempre tem en passant vazio, meio-lance 0 e lance 1", () => {
  const board = boardFromFen("4k3/8/8/8/4P3/8/8/4K3 w - e3 3 27");
  expect(fenFromBoard(board, "white", NENHUM).split(" ").slice(3)).toEqual(["-", "0", "1"]);
});

test("lado a jogar e roques saem da FEN colada", () => {
  expect(turnFromFen(START_FEN)).toBe("white");
  expect(turnFromFen("4k3/8/8/8/8/8/8/4K3 b - - 0 1")).toBe("black");
  expect(castlingFromFen(START_FEN)).toEqual(TODOS);
  expect(castlingFromFen("r3k3/8/8/8/8/8/8/4K2R w Kq - 0 1")).toEqual({ K: true, Q: false, k: false, q: true });
});

// --- roques disponíveis -------------------------------------------------

test("na posição inicial os quatro roques são possíveis", () => {
  expect(castlingAvailable(boardFromFen(START_FEN))).toEqual(TODOS);
});

test("sem rei ou torre na casa de origem o roque some", () => {
  // rei branco em e2, torres brancas nos lugares; pretas só com a torre de a8
  const board = boardFromFen("r3k3/8/8/8/8/8/4K3/R6R w - - 0 1");
  expect(castlingAvailable(board)).toEqual({ K: false, Q: false, k: false, q: true });
});

test("peça errada na casa da torre não vale roque", () => {
  const board = boardFromFen("4k2r/8/8/8/8/8/8/4K2B w - - 0 1");
  expect(castlingAvailable(board)).toEqual({ K: false, Q: false, k: true, q: false });
});

// --- validação ----------------------------------------------------------

test("a posição inicial é válida", () => {
  expect(validatePosition(START_FEN)).toEqual([]);
});

test("falta de rei e rei repetido são apontados", () => {
  expect(validatePosition("4k3/8/8/8/8/8/8/8 w - - 0 1")).toEqual(["Falta o rei branco."]);
  expect(validatePosition("8/8/8/8/8/8/8/4K3 w - - 0 1")).toEqual(["Falta o rei preto."]);
  expect(validatePosition("4k3/8/8/8/8/8/8/K3K3 w - - 0 1")).toEqual(["Há mais de um rei branco."]);
  expect(validatePosition("k3k3/8/8/8/8/8/8/4K3 w - - 0 1")).toEqual(["Há mais de um rei preto."]);
});

test("peão na primeira ou na última fileira é apontado", () => {
  expect(validatePosition("P3k3/8/8/8/8/8/8/4K3 w - - 0 1")).toContain(
    "Há peões na primeira ou na última fileira.",
  );
  expect(validatePosition("4k3/8/8/8/8/8/8/3pK3 w - - 0 1")).toContain(
    "Há peões na primeira ou na última fileira.",
  );
});

test("mais de 16 peças ou mais de 8 peões de um lado é apontado", () => {
  expect(validatePosition("4k3/8/8/NNNNNNNN/NNNNNNNN/8/8/4K3 w - - 0 1")).toContain(
    "As brancas têm mais de 16 peças.",
  );
  expect(validatePosition("4k3/nnnnnnnn/nnnnnnnn/8/8/8/8/4K3 w - - 0 1")).toContain(
    "As pretas têm mais de 16 peças.",
  );
  expect(validatePosition("4k3/8/8/8/8/P7/PPPPPPPP/4K3 w - - 0 1")).toEqual([
    "As brancas têm mais de 8 peões.",
  ]);
  expect(validatePosition("4k3/pppppppp/p7/8/8/8/8/4K3 w - - 0 1")).toEqual([
    "As pretas têm mais de 8 peões.",
  ]);
});

test("o rei de quem não joga não pode estar em xeque", () => {
  expect(validatePosition("4k3/4R3/8/8/8/8/8/4K3 w - - 0 1")).toEqual([
    "O rei preto está em xeque e é a vez das brancas.",
  ]);
  expect(validatePosition("4k3/8/8/8/8/8/4r3/4K3 b - - 0 1")).toEqual([
    "O rei branco está em xeque e é a vez das pretas.",
  ]);
  // quem joga em xeque é normal: nada a apontar
  expect(validatePosition("4k3/4R3/8/8/8/8/8/4K3 b - - 0 1")).toEqual([]);
});

test("FEN que o xadrez não entende vira um aviso só", () => {
  expect(validatePosition("nada disso é uma FEN")).toEqual(["Posição inválida."]);
});

test("parseFen aceita a FEN colada e recusa o que não é tabuleiro", () => {
  const p = parseFen("r3k3/8/8/8/8/8/8/4K2R b Kq - 0 1");
  expect(p?.turn).toBe("black");
  expect(p?.castling).toEqual({ K: true, Q: false, k: false, q: true });
  expect(p?.board.size).toBe(4);
  // posição impossível ainda entra: quem reclama é a validação, na tela
  expect(parseFen("4k3/8/8/8/8/8/8/K3K3 w - - 0 1")).not.toBeNull();
  expect(parseFen("isso não é uma FEN")).toBeNull();
  expect(parseFen("4k3/8/8/8/8/8/4K3 w - - 0 1")).toBeNull();
});

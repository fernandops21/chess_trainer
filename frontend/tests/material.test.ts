import { expect, test } from "vitest";
import { materialCapturado } from "../src/board/material";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
/** Brancas sem um cavalo (g1), pretas sem dois peões (b7 e c7). */
const TROCAS = "rnbqkbnr/p2ppppp/8/8/8/8/PPPPPPPP/RNBQKB1R w KQkq - 0 1";
/** Brancas com duas damas (uma veio de promoção) e nenhum peão. */
const PROMOVIDA = "1k6/8/8/8/8/8/1Q6/1K1Q4 w - - 0 1";

test("posição inicial: ninguém capturou nada e o saldo é zero", () => {
  const m = materialCapturado(START);
  expect(m.capturadasPor.white).toEqual({ p: 0, n: 0, b: 0, r: 0, q: 0 });
  expect(m.capturadasPor.black).toEqual({ p: 0, n: 0, b: 0, r: 0, q: 0 });
  expect(m.saldo).toBe(0);
});

test("as peças que faltam contam como capturadas pelo outro lado", () => {
  const m = materialCapturado(TROCAS);
  // o cavalo que falta às brancas foi capturado pelas pretas
  expect(m.capturadasPor.black.n).toBe(1);
  expect(m.capturadasPor.white.p).toBe(2);
  expect(m.capturadasPor.black.p).toBe(0);
  expect(m.capturadasPor.white.n).toBe(0);
  // brancas perderam 3 e pretas 2: as pretas estão com um ponto a mais
  expect(m.saldo).toBe(-1);
});

test("peça a mais por promoção não vira captura negativa", () => {
  const m = materialCapturado(PROMOVIDA);
  expect(m.capturadasPor.black.q).toBe(0);
  expect(m.capturadasPor.black.p).toBe(8);
  expect(m.saldo).toBe(18);
});

test("FEN inválida devolve tudo zerado", () => {
  const m = materialCapturado("lixo");
  expect(m.capturadasPor.white).toEqual({ p: 0, n: 0, b: 0, r: 0, q: 0 });
  expect(m.capturadasPor.black).toEqual({ p: 0, n: 0, b: 0, r: 0, q: 0 });
  expect(m.saldo).toBe(0);
});

test("diagrama de estudo sem rei também é contado", () => {
  // o `novoChess` aceita esses diagramas; a barra não pode zerar por causa deles
  const m = materialCapturado("r1r5/8/1N6/8/8/8/5N2/3k3q w - - 0 1");
  expect(m.capturadasPor.white.p).toBe(8);
  expect(m.capturadasPor.black.b).toBe(2);
  expect(m.saldo).toBe(6 - 19);
});

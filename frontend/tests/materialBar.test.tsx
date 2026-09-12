import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { MaterialBar } from "../src/board/MaterialBar";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
/** Pretas sem dois peões (b7 e c7): as brancas capturaram os dois. */
const DOIS_PEOES = "rnbqkbnr/p2ppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

test("as peças capturadas aparecem na cor do adversário", () => {
  const { container } = render(<MaterialBar fen={DOIS_PEOES} lado="white" />);
  expect(container.querySelectorAll("piece.pawn.black").length).toBe(2);
  expect(container.querySelectorAll("piece.pawn.white").length).toBe(0);
});

test("o `+N` fica só do lado que está na frente", () => {
  const brancas = render(<MaterialBar fen={DOIS_PEOES} lado="white" />);
  expect(brancas.container.textContent).toContain("+2");
  const pretas = render(<MaterialBar fen={DOIS_PEOES} lado="black" />);
  expect(pretas.container.textContent).not.toContain("+2");
  expect(pretas.container.querySelectorAll("piece").length).toBe(0);
});

test("a leitura de tela diz quem capturou o quê", () => {
  const { container } = render(<MaterialBar fen={DOIS_PEOES} lado="white" />);
  expect(container.querySelector(".material-bar")!.getAttribute("aria-label"))
    .toBe("brancas capturaram: 2 peões; +2");
});

test("sem captura a barra continua no lugar, vazia", () => {
  const { container } = render(<MaterialBar fen={START} lado="white" />);
  const barra = container.querySelector(".material-bar")!;
  expect(barra).toBeTruthy();
  // a altura mínima é do CSS; aqui basta que nada tenha sido desenhado
  expect(barra.textContent).toBe("");
  expect(barra.querySelectorAll("piece").length).toBe(0);
});

test("na frente sem ter capturado nada, a leitura de tela diz de quê", () => {
  // brancas promoveram um peão (duas damas, sete peões) e não capturaram nada
  const { container } = render(<MaterialBar fen="rnbqkbnr/pppppppp/8/8/Q7/8/1PPPPPPP/RNBQKBNR w KQkq - 0 1" lado="white" />);
  expect(container.querySelectorAll("piece").length).toBe(0);
  expect(container.querySelector(".material-bar")!.getAttribute("aria-label"))
    .toBe("brancas: +8 de material");
});

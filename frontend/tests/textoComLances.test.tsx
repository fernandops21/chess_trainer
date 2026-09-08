import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { TextoComLances } from "../src/analysis/TextoComLances";
import type { LanceDaLinha } from "../src/analysis/moveText";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

/** Os SANs da linha que chegou no `onPrevia` da última vez. */
const ultimaLinha = (spy: ReturnType<typeof vi.fn>) =>
  (spy.mock.calls.at(-1)![0] as LanceDaLinha[]).map((l) => l.san);

test("os lances viram botões e a prosa fica como está", () => {
  const onPrevia = vi.fn();
  const { container } = render(<TextoComLances texto="Melhor é 1. e4 e5, e não Bh8." fen={START} onPrevia={onPrevia} />);
  expect(container.textContent).toBe("Melhor é 1. e4 e5, e não Bh8.");
  const botoes = screen.getAllByRole("button");
  expect(botoes.map((b) => b.textContent)).toEqual(["1. e4", "e5"]);
  expect(botoes[0].getAttribute("title")).toBe("mostrar no tabuleiro");
  expect(botoes[0].getAttribute("type")).toBe("button");
  expect(botoes[0].className).toBe("lance-no-texto");
});

test("clicar num lance manda a linha da âncora até ele", () => {
  const onPrevia = vi.fn();
  render(<TextoComLances texto="e4 e5 Nf3" fen={START} onPrevia={onPrevia} />);

  fireEvent.click(screen.getByRole("button", { name: "e4" }));
  expect(ultimaLinha(onPrevia)).toEqual(["e4"]);

  fireEvent.click(screen.getByRole("button", { name: "Nf3" }));
  expect(ultimaLinha(onPrevia)).toEqual(["e4", "e5", "Nf3"]);
  // a linha traz a posição a que o lance leva
  const linha = onPrevia.mock.calls.at(-1)![0] as LanceDaLinha[];
  expect(linha[2].uci).toBe("g1f3");
  expect(linha[2].lastMove).toEqual(["g1", "f3"]);
});

test("texto sem lance nenhum não tem botão", () => {
  const { container } = render(<TextoComLances texto="As brancas ganham a peça." fen={START} onPrevia={vi.fn()} />);
  expect(screen.queryAllByRole("button")).toEqual([]);
  expect(container.textContent).toBe("As brancas ganham a peça.");
});

test("com `apenasLances` sai só a fila de botões", () => {
  const { container } = render(<TextoComLances texto="Melhor é 1. e4 e5, e não Bh8." fen={START} onPrevia={vi.fn()} apenasLances />);
  expect(container.textContent).toBe("1. e4 e5");
  expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["1. e4", "e5"]);
});

import { fireEvent, render } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { Tree, TreeNode } from "../src/analysis/moveTree";
import { BookView } from "../src/studies/BookView";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const node = (id: string, uci: string, san: string, over: Partial<TreeNode> = {}): TreeNode => ({
  id, uci, san, comment: "", shapes: [], nags: [], children: [], ...over,
});

const SOBRE_BC4 = "O bispo mira f7, o ponto mais fraco da posição preta.";
const SOBRE_BC5 = "As pretas respondem no mesmo tom e ocupam a diagonal oposta.";
const SOBRE_NF6 = "A defesa dos dois cavalos, bem mais aguda.";

/**
 * 1. e4 e5 2. Nf3 Nc6 3. Bc4 {comentário} Bc5! {comentário} (3... Nf6 {comentário})
 *
 * Os quatro primeiros lances não têm comentário: são a corrida. O terceiro das
 * brancas e o das pretas são comentados, e o irmão de Bc5 é a variação.
 */
const arvore: Tree = {
  fen: START,
  orientation: "white",
  intro: "As brancas abrem com a Italiana.",
  root: {
    children: [
      node("n1", "e2e4", "e4", {
        children: [
          node("n2", "e7e5", "e5", {
            children: [
              node("n3", "g1f3", "Nf3", {
                children: [
                  node("n4", "b8c6", "Nc6", {
                    children: [
                      node("n5", "f1c4", "Bc4", {
                        comment: SOBRE_BC4,
                        children: [
                          node("n6", "f8c5", "Bc5", { nags: [1], comment: SOBRE_BC5 }),
                          node("n7", "g8f6", "Nf6", { comment: SOBRE_NF6 }),
                        ],
                      }),
                    ],
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
    ],
  },
};

/** Texto de um elemento com os espaços normalizados. */
const texto = (el: Element | null): string => (el?.textContent ?? "").replace(/\s+/g, " ").trim();

function renderLivro(over: Partial<Parameters<typeof BookView>[0]> = {}) {
  const onGoTo = vi.fn();
  const r = render(<BookView tree={arvore} currentId={null} onGoTo={onGoTo} {...over} />);
  return { ...r, onGoTo };
}

test("o enunciado é o primeiro parágrafo do livro", () => {
  const { container } = renderLivro();
  expect(texto(container.querySelectorAll("p")[0])).toBe("As brancas abrem com a Italiana.");
});

test("lances sem comentário saem juntos num parágrafo só", () => {
  const { container } = renderLivro();
  const corridas = container.querySelectorAll(".livro-lances");
  expect(corridas.length).toBe(1);
  expect(texto(corridas[0])).toBe("1. e4 e5 2. Nf3 Nc6");
});

test("lance comentado das brancas abre parágrafo com o número inteiro", () => {
  const { container } = renderLivro();
  const pars = Array.from(container.querySelectorAll(".livro-par"));
  const bc4 = pars.find((p) => texto(p).startsWith("3. Bc4"));
  expect(texto(bc4 ?? null)).toBe(`3. Bc4 ${SOBRE_BC4}`);
});

test("lance comentado das pretas abre parágrafo com reticências e o NAG colado", () => {
  const { container } = renderLivro();
  const pars = Array.from(container.querySelectorAll(".livro-par"));
  const bc5 = pars.find((p) => texto(p).startsWith("3...Bc5"));
  expect(texto(bc5 ?? null)).toBe(`3...Bc5! ${SOBRE_BC5}`);
  // o NAG fica dentro do botão, colado no SAN
  expect(texto(bc5!.querySelector(".livro-lance"))).toBe("3...Bc5!");
});

test("a variação sai recuada logo depois do lance principal", () => {
  const { container } = renderLivro();
  const livro = container.querySelector(".livro")!;
  const blocos = Array.from(livro.children);
  const bc5 = blocos.findIndex((el) => texto(el).startsWith("3...Bc5"));
  const variacao = blocos.findIndex((el) => el.classList.contains("livro-variacao"));
  expect(bc5).toBeGreaterThan(-1);
  expect(variacao).toBe(bc5 + 1);
  // o primeiro lance da variação sempre traz o número, mesmo sendo das pretas
  expect(texto(blocos[variacao])).toBe(`3...Nf6 ${SOBRE_NF6}`);
});

test("o lance atual ganha a classe atual", () => {
  const { container } = renderLivro({ currentId: "n6" });
  const atuais = container.querySelectorAll(".livro-lance.atual");
  expect(atuais.length).toBe(1);
  expect(texto(atuais[0])).toBe("3...Bc5!");
});

test("clicar num lance navega até ele", () => {
  const { container, onGoTo } = renderLivro();
  const lances = Array.from(container.querySelectorAll(".livro-lance"));
  fireEvent.click(lances.find((b) => texto(b) === "2. Nf3")!);
  expect(onGoTo).toHaveBeenCalledWith("n3");
});

test("clicar num lance escrito no comentário pede a prévia, não a navegação", () => {
  const onPrevia = vi.fn();
  const comLance: Tree = { ...arvore, intro: "A ideia é chegar a 4. d3 sem pressa." };
  const { container, onGoTo } = renderLivro({ tree: comLance, onPrevia });
  const noTexto = container.querySelector(".lance-no-texto")!;
  expect(texto(noTexto)).toBe("4. d3");
  fireEvent.click(noTexto);
  expect(onPrevia).toHaveBeenCalledTimes(1);
  expect(onGoTo).not.toHaveBeenCalled();
});

test("sem lances e sem enunciado, o livro avisa que a linha está vazia", () => {
  const vazio: Tree = { fen: START, orientation: "white", intro: "", root: { children: [] } };
  const { container } = renderLivro({ tree: vazio });
  expect(texto(container.querySelector(".livro"))).toContain("Nenhum lance ainda");
});

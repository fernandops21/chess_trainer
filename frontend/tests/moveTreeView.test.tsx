import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { Classification } from "../src/analysis/classify";
import type { Tree, TreeNode } from "../src/analysis/moveTree";
import { MoveTreeView } from "../src/analysis/MoveTreeView";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const node = (id: string, uci: string, san: string, over: Partial<TreeNode> = {}): TreeNode => ({
  id, uci, san, comment: "", shapes: [], nags: [], children: [], ...over,
});

/** 1. e4 e5! {melhor resposta} (1... c5) 2. Nf3 */
const tree: Tree = {
  fen: START,
  orientation: "white",
  intro: "",
  root: {
    children: [
      node("n1", "e2e4", "e4", {
        children: [
          node("n2", "e7e5", "e5", {
            nags: [1],
            comment: "melhor resposta",
            children: [node("n4", "g1f3", "Nf3")],
          }),
          node("n3", "c7c5", "c5"),
        ],
      }),
    ],
  },
};

/** Texto da árvore com os espaços normalizados. */
function treeText(el: HTMLElement): string {
  return (el.textContent ?? "").replace(/\s+/g, " ").trim();
}

test("mostra a linha principal com números, NAG e comentário", () => {
  const { container } = render(<MoveTreeView tree={tree} currentId={null} onGoTo={() => {}} />);
  const txt = treeText(container);
  expect(txt).toMatch(/1\. e4/);
  expect(txt).toMatch(/e5!/);
  expect(txt).toMatch(/melhor resposta/);
  expect(txt).toMatch(/2\. Nf3/);
});

test("mostra as variações entre parênteses, recuadas", () => {
  const { container } = render(<MoveTreeView tree={tree} currentId={null} onGoTo={() => {}} />);
  const varia = container.querySelector(".variation");
  expect(varia).toBeTruthy();
  expect(treeText(varia as HTMLElement)).toMatch(/\(\s*1\.\.\. c5\s*\)/);
});

test("trunca o comentário longo a 80 caracteres", () => {
  const longo = "a".repeat(200);
  const t: Tree = { ...tree, root: { children: [node("n1", "e2e4", "e4", { comment: longo })] } };
  const { container } = render(<MoveTreeView tree={t} currentId={null} onGoTo={() => {}} />);
  const c = container.querySelector(".comment") as HTMLElement;
  expect(c.textContent!.length).toBeLessThanOrEqual(81);
  expect(c.textContent).toMatch(/…$/);
});

test("destaca o nó atual", () => {
  render(<MoveTreeView tree={tree} currentId="n2" onGoTo={() => {}} />);
  const atual = document.querySelector('[aria-current="true"]') as HTMLElement;
  expect(atual.textContent).toMatch(/e5/);
  expect(screen.getByText(/^1\. e4$/).getAttribute("aria-current")).toBe(null);
});

test("clique num lance chama onGoTo com o id do nó", () => {
  const onGoTo = vi.fn();
  render(<MoveTreeView tree={tree} currentId={null} onGoTo={onGoTo} />);
  fireEvent.click(screen.getByText(/^1\. e4$/));
  expect(onGoTo).toHaveBeenCalledWith("n1");
});

test("botão direito num lance abre o menu do nó", () => {
  const onContextMenu = vi.fn();
  render(<MoveTreeView tree={tree} currentId={null} onGoTo={() => {}} onContextMenu={onContextMenu} />);
  fireEvent.contextMenu(screen.getByText(/^1\.\.\. c5$/), { clientX: 30, clientY: 40 });
  expect(onContextMenu).toHaveBeenCalledWith("n3", { x: 30, y: 40 });
});

test("marca com o símbolo do livro os lances de bookIds, na principal e nas variações", () => {
  const { container } = render(
    <MoveTreeView tree={tree} currentId={null} onGoTo={() => {}} bookIds={new Set(["n1", "n3"])} />,
  );
  const livros = container.querySelectorAll(".book");
  expect(livros.length).toBe(2);
  expect(livros[0].textContent).toBe("📖");
  expect(livros[0].getAttribute("title")).toBe("lance de livro (base de mestres)");
  expect(livros[0].getAttribute("aria-label")).toBe("lance de livro (base de mestres)");
  // o símbolo fica junto do lance, dentro do botão dele
  // getByText olha só o texto direto do botão: o símbolo fica num span dentro dele
  expect(screen.getByText(/^1\. e4$/).querySelector(".book")).toBeTruthy();
  // n3 é o lance da variação
  expect((container.querySelector(".variation") as HTMLElement).querySelector(".book")).toBeTruthy();
  // e5 não está no livro: sem símbolo
  expect(screen.getByText(/^e5!$/).querySelector(".book")).toBeNull();
});

test("sem bookIds nenhum lance ganha símbolo", () => {
  const { container } = render(<MoveTreeView tree={tree} currentId={null} onGoTo={() => {}} />);
  expect(container.querySelectorAll(".book").length).toBe(0);
});

test("árvore vazia mostra um aviso", () => {
  const vazia: Tree = { fen: START, orientation: "white", intro: "", root: { children: [] } };
  const { container } = render(<MoveTreeView tree={vazia} currentId={null} onGoTo={() => {}} />);
  expect(treeText(container)).toMatch(/Nenhum lance/);
});

// --- selo da classificação ----------------------------------------------

const classe = (kind: string, label: string, symbol: string): Classification =>
  ({ kind, label, symbol, loss: 0 }) as Classification;

test("mostra o selo da classificação depois do lance, com o nome no title", () => {
  const classes = new Map([
    ["n1", classe("brilhante", "brilhante", "!!")],
    ["n3", classe("blunder", "blunder", "??")],
  ]);
  const { container } = render(
    <MoveTreeView tree={tree} currentId={null} onGoTo={() => {}} classes={classes} />,
  );
  const selo = screen.getByText(/^1\. e4$/).querySelector(".class") as HTMLElement;
  expect(selo.textContent).toBe("!!");
  expect(selo.getAttribute("title")).toBe("brilhante");
  // leitura de tela: o símbolo sozinho não diz nada
  expect(selo.getAttribute("role")).toBe("img");
  expect(selo.getAttribute("aria-label")).toBe("brilhante");
  expect(selo.className).toContain("class-brilhante");
  // também nas variações
  const naVariacao = (container.querySelector(".variation") as HTMLElement).querySelector(".class") as HTMLElement;
  expect(naVariacao.className).toContain("class-blunder");
  // lance sem classificação não ganha selo
  expect(screen.getByText(/^e5!$/).querySelector(".class")).toBeNull();
});

test("no lance de livro o símbolo do livro vence a classificação", () => {
  const classes = new Map([["n1", classe("melhor", "melhor", "★")]]);
  render(
    <MoveTreeView
      tree={tree}
      currentId={null}
      onGoTo={() => {}}
      classes={classes}
      bookIds={new Set(["n1"])}
    />,
  );
  const lance = screen.getByText(/^1\. e4$/);
  expect(lance.querySelector(".book")).toBeTruthy();
  expect(lance.querySelector(".class")).toBeNull();
});

test("sem `classes` nenhum lance ganha selo", () => {
  const { container } = render(<MoveTreeView tree={tree} currentId={null} onGoTo={() => {}} />);
  expect(container.querySelectorAll(".class").length).toBe(0);
});

import { useState, type ReactNode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Key } from "chessground/types";
import type { BoardProps } from "../src/board/Board";
import { api } from "../src/api/client";
import type { AnalyseOut } from "../src/api/types";

// O chessground não é reproduzível no jsdom: o dublê guarda o que o
// AnalysisBoard manda e devolve o `onMove` para o teste jogar um lance.
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

import { emptyTree, findNode, insertLine } from "../src/analysis/moveTree";
import type { Tree } from "../src/analysis/moveTree";
import { AnalysisBoard } from "../src/analysis/AnalysisBoard";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const last = () => boardProps.at(-1) as unknown as BoardProps;
const play = (uci: string) =>
  act(() => { last().onMove!(uci.slice(0, 2) as Key, uci.slice(2, 4) as Key); });

const analyse: AnalyseOut = {
  fen: START,
  turn: "white",
  terminal: null,
  lines: [{ move: "e2e4", san: "e4", score: 30, pv: ["e2e4", "e7e5", "g1f3"], pv_san: ["e4", "e5", "Nf3"] }],
};

function renderBoard(props: Partial<Parameters<typeof AnalysisBoard>[0]> = {}) {
  const onTreeChange = vi.fn();
  const onSave = vi.fn();
  const r = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <AnalysisBoard tree={emptyTree(START)} onTreeChange={onTreeChange} onSave={onSave} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...r, onTreeChange, onSave };
}

/** Última árvore que o componente devolveu. */
const lastTree = (spy: ReturnType<typeof vi.fn>): Tree => spy.mock.calls.at(-1)![0] as Tree;

beforeEach(() => {
  boardProps.length = 0;
  vi.spyOn(api, "analyse").mockResolvedValue(analyse);
});
afterEach(() => vi.restoreAllMocks());

test("joga lances pelo tabuleiro e avisa a árvore nova", () => {
  const { container, onTreeChange } = renderBoard();
  play("e2e4");
  play("e7e5");
  expect(container.textContent).toMatch(/1\. e4/);
  expect(container.textContent).toMatch(/e5/);
  const t = lastTree(onTreeChange);
  expect(t.root.children[0].san).toBe("e4");
  expect(t.root.children[0].children[0].san).toBe("e5");
});

test("navega pelo teclado: setas e Home", () => {
  renderBoard();
  play("e2e4");
  play("e7e5");
  const depois = last().fen;
  fireEvent.keyDown(window, { key: "ArrowLeft" });
  expect(last().fen).not.toBe(depois);
  fireEvent.keyDown(window, { key: "ArrowRight" });
  expect(last().fen).toBe(depois);
  fireEvent.keyDown(window, { key: "Home" });
  expect(last().fen).toBe(START);
});

test("clicar num lance da árvore vai para a posição dele", () => {
  renderBoard();
  play("e2e4");
  play("e7e5");
  const depois = last().fen;
  fireEvent.click(screen.getByText(/^1\. e4$/));
  expect(last().fen).not.toBe(depois);
});

test("a caixa de comentário só aparece no modo edição e guarda no nó atual", () => {
  const semEdicao = renderBoard();
  expect(screen.queryByLabelText("Comentário")).toBe(null);
  semEdicao.unmount();

  const { onTreeChange } = renderBoard({ editable: true });
  play("e2e4");
  const caixa = screen.getByLabelText("Comentário");
  fireEvent.change(caixa, { target: { value: "avanço central" } });
  const t = lastTree(onTreeChange);
  const id = t.root.children[0].id;
  expect(findNode(t, id)!.comment).toBe("avanço central");
});

test("Ctrl+S dispara onSave", () => {
  const { onSave } = renderBoard({ editable: true });
  fireEvent.keyDown(window, { key: "s", ctrlKey: true });
  expect(onSave).toHaveBeenCalled();
});

test("a linha do motor entra como variação", async () => {
  const { container, onTreeChange } = renderBoard();
  const botao = await screen.findByText("adicionar como variação");
  fireEvent.click(botao);
  await waitFor(() => expect(container.textContent).toMatch(/2\. Nf3/));
  const t = lastTree(onTreeChange);
  expect(t.root.children[0].san).toBe("e4");
  expect(t.root.children[0].children[0].children[0].san).toBe("Nf3");
});

test("clicar na linha do motor joga só o primeiro lance", async () => {
  const { onTreeChange } = renderBoard();
  fireEvent.click(await screen.findByRole("button", { name: /\+0\.30 e4 e5 Nf3/ }));
  const t = lastTree(onTreeChange);
  expect(t.root.children[0].san).toBe("e4");
  expect(t.root.children[0].children).toEqual([]);
});

test("mostra o link Voltar quando recebe backTo", () => {
  renderBoard({ backTo: "/erros" });
  expect(screen.getByText("Voltar").getAttribute("href")).toBe("/erros");
});

// --- vaivém da árvore com o pai ----------------------------------------

/** Pai que guarda a árvore e devolve ela pelo `tree` (como o editor de capítulo). */
function Pai({ inicial }: { inicial: Tree }) {
  const [t, setT] = useState(inicial);
  return <AnalysisBoard editable tree={t} onTreeChange={setT} />;
}

/** Renderiza com os provedores e deixa trocar as props sem remontar. */
function comProvedores(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const envolver = (n: ReactNode) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>{n}</MemoryRouter>
    </QueryClientProvider>
  );
  const r = render(envolver(node));
  return { ...r, trocar: (n: ReactNode) => r.rerender(envolver(n)) };
}

test("a árvore que volta do pai não reinicia a navegação", () => {
  comProvedores(<Pai inicial={emptyTree(START)} />);
  play("e2e4");
  play("e7e5");
  const fen = last().fen;

  fireEvent.change(screen.getByLabelText("Comentário"), { target: { value: "simétrico" } });
  expect(last().fen).toBe(fen);
  expect(screen.getByText("e5").getAttribute("aria-current")).toBe("true");
});

test("uma árvore de fora sem o lance atual volta ao começo", () => {
  const { trocar } = comProvedores(<AnalysisBoard editable tree={emptyTree(START)} />);
  play("e2e4");
  expect(last().fen).not.toBe(START);

  const outra = emptyTree("8/8/8/8/8/8/8/K6k w - - 0 1");
  trocar(<AnalysisBoard editable tree={outra} />);
  expect(last().fen).toBe(outra.fen);
});

test("uma árvore de fora com o mesmo caminho mantém o lance atual", () => {
  const { trocar } = comProvedores(<AnalysisBoard editable tree={emptyTree(START)} />);
  play("e2e4");
  const fen = last().fen;

  // mesma linha, outro enunciado (é o que o editor manda ao salvar): o lance fica
  const mesma = insertLine(emptyTree(START), null, ["e2e4"]).tree;
  trocar(<AnalysisBoard editable tree={{ ...mesma, intro: "novo enunciado" }} />);
  expect(last().fen).toBe(fen);
  expect(screen.getByText(/^1\. e4$/).getAttribute("aria-current")).toBe("true");
});

// --- menu do lance ------------------------------------------------------

test("o menu do lance promove, marca NAG e apaga", () => {
  const { onTreeChange } = renderBoard({ editable: true });
  play("e2e4");
  fireEvent.keyDown(window, { key: "Home" });
  play("d2d4");

  // depois do NAG o texto do lance vira "1. d4!": o nome casa pelo começo
  const abrir = () => fireEvent.contextMenu(screen.getByRole("button", { name: /^1\. d4/ }), { clientX: 20, clientY: 20 });

  abrir();
  fireEvent.click(screen.getByRole("menuitem", { name: "Promover a linha principal" }));
  expect(lastTree(onTreeChange).root.children[0].san).toBe("d4");

  abrir();
  fireEvent.click(screen.getByRole("menuitem", { name: "marcar !" }));
  expect(lastTree(onTreeChange).root.children[0].nags).toEqual([1]);

  abrir();
  fireEvent.click(screen.getByRole("menuitem", { name: "Apagar daqui" }));
  expect(lastTree(onTreeChange).root.children.map((n) => n.san)).toEqual(["e4"]);
});

test("no modo edição a seta do motor é azul (o verde fica para as marcações do autor)", async () => {
  const semEdicao = renderBoard();
  await waitFor(() => expect(last().arrows?.[0]?.brush).toBe("green"));
  semEdicao.unmount();

  renderBoard({ editable: true });
  await waitFor(() => expect(last().arrows?.[0]?.brush).toBe("blue"));
});

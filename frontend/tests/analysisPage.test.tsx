import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Key } from "chessground/types";
import type { BoardProps } from "../src/board/Board";
import { api } from "../src/api/client";
import type { AnalyseOut } from "../src/api/types";

// O chessground não roda no jsdom: o dublê guarda as props e devolve o `onMove`.
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

import { AnalysisPage } from "../src/pages/AnalysisPage";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const analyse: AnalyseOut = { fen: START, turn: "white", terminal: null, lines: [] };

const last = () => boardProps.at(-1) as unknown as BoardProps;
const play = (uci: string) =>
  act(() => { last().onMove!(uci.slice(0, 2) as Key, uci.slice(2, 4) as Key); });

function renderPage(rota = "/analise") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[rota]}>
        <Routes>
          <Route path="/analise" element={<AnalysisPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  boardProps.length = 0;
  vi.spyOn(api, "analyse").mockResolvedValue(analyse);
});
afterEach(() => vi.restoreAllMocks());

test("a análise é o editor completo: comentário e marcações antes de salvar", () => {
  renderPage();
  play("e2e4");
  // caixa de comentário e marcações do usuário só existem no modo edição
  expect(screen.getByLabelText("Comentário")).toBeTruthy();
  expect(last().onShapesChange).toBeTypeOf("function");
  expect(screen.getByRole("button", { name: "Salvar como capítulo" })).toBeTruthy();
});

test("o menu do lance abre com o botão direito na árvore", () => {
  renderPage();
  play("e2e4");
  const lance = screen.getByText(/^1\. e4$/);
  act(() => { lance.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })); });
  expect(screen.getByRole("menu", { name: "Ações do lance" })).toBeTruthy();
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { BoardProps } from "../src/board/Board";
import { api } from "../src/api/client";
import { TacticResultPanel } from "../src/train/TacticResultPanel";
import type { AnalyseOut, AttemptOut, TacticOut } from "../src/api/types";

// o chessground não roda no jsdom: o dublê guarda as props do tabuleiro
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

const last = () => boardProps.at(-1) as unknown as BoardProps;

// o painel traz o botão "Guardar para repetir", que é uma mutation
function renderPanel(tactic: TacticOut, extra: { attempt?: AttemptOut; durationMs?: number } = {}) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter>
        <TacticResultPanel tactic={tactic} {...extra} onRetry={() => {}} onNext={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const analyse: AnalyseOut = {
  fen: "4k3/8/8/3N4/8/8/7P/4K3 b - - 0 1",
  turn: "black",
  terminal: null,
  // ponto de vista de quem joga (pretas): a tela mostra a avaliação das brancas
  lines: [{ move: "e8d7", san: "Kd7", score: -300, pv: ["e8d7"], pv_san: ["Kd7"] }],
};

beforeEach(() => {
  boardProps.length = 0;
  localStorage.clear();
  vi.spyOn(api, "analyse").mockResolvedValue(analyse);
  vi.spyOn(api, "openings").mockRejectedValue(new Error("sem livro"));
  vi.spyOn(api, "settings").mockRejectedValue(new Error("sem configurações"));
});
afterEach(() => vi.restoreAllMocks());

const baseTactic = (over: Partial<TacticOut> = {}): TacticOut => ({
  id: "t1",
  kind: "tactic",
  fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1",
  side_to_move: "white",
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: [] }], explanation_pv: [] },
  end_reason: "material_gain",
  theme: "fork",
  themes: ["fork"],
  category: "lichess",
  rating: 1500,
  solver_moves: 1,
  lichess_url: "https://lichess.org/training/t1",
  popularity: 90,
  nb_plays: 300,
  opening_tags: [],
  saved: false,
  ...over,
});

test("a solução vira o tabuleiro de análise, aberto no último lance", () => {
  renderPanel(baseTactic());
  const lance = screen.getByRole("button", { name: /^1\. Nxd5$/ });
  expect(lance.getAttribute("aria-current")).toBe("true");
  expect(last().lastMove).toEqual(["c3", "d5"]);
  // dá para navegar: a seta esquerda volta à posição do exercício
  fireEvent.keyDown(window, { key: "ArrowLeft" });
  expect(last().fen).toBe("4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1");
});

test("com o lance do adversário a linha começa por ele", () => {
  renderPanel(baseTactic({
    fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 1 2",
    fen_before: "4k3/8/8/8/3q4/2N5/7P/4K3 b - - 0 1",
    last_move: "d4d5",
  }));
  expect(screen.getByRole("button", { name: /^1\.\.\. Qd5$/ })).toBeTruthy();
  const lance = screen.getByRole("button", { name: /^2\. Nxd5$/ });
  expect(lance.getAttribute("aria-current")).toBe("true");
});

test("brancas a jogar no lance 12 mostra '12.' antes do primeiro lance", () => {
  renderPanel(baseTactic({ fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 12" }));
  expect(screen.getByRole("button", { name: /^12\. Nxd5$/ })).toBeTruthy();
});

test("pretas a jogar no lance 24 mostra '24...' antes do primeiro lance", () => {
  renderPanel(baseTactic({
    fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 b - - 0 24",
    side_to_move: "black",
    solution: { moves: [{ uci: "d5d1", by: "solver", alternatives: [] }], explanation_pv: [] },
  }));
  expect(screen.getByRole("button", { name: /^24\.\.\. Qd1\+$/ })).toBeTruthy();
});

test("a engine fica desligada até o botão ser apertado", async () => {
  renderPanel(baseTactic());
  expect(api.analyse).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Analisar com a engine" }));
  expect(await screen.findByRole("button", { name: /\+3\.00 Kd7/ })).toBeTruthy();
});

test("o resultado guarda o rating, o link do Lichess e o Explorar", () => {
  const attempt: AttemptOut = {
    id: "a1", puzzle_id: "t1", correct: true, used_hint: false,
    rating_before: 1200, rating_after: 1216, delta: 16, puzzle_rating: 1500,
  };
  renderPanel(baseTactic(), { attempt });
  expect(screen.getByText("Rating 1200 → 1216 (+16)")).toBeTruthy();
  expect(screen.getByText("Resolvido sem erro.")).toBeTruthy();
  expect(screen.getByText("ver no Lichess").getAttribute("href")).toBe("https://lichess.org/training/t1");
  expect(screen.getByText("Explorar")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Próximo" })).toBeTruthy();
});

test("guardar para repetir manda o resultado da tentativa mostrada", async () => {
  const save = vi.spyOn(api, "saveTactic").mockResolvedValue({} as never);
  const attempt: AttemptOut = {
    id: "a1", puzzle_id: "t1", correct: true, used_hint: false,
    rating_before: 1200, rating_after: 1216, delta: 16, puzzle_rating: 1500,
  };
  renderPanel(baseTactic(), { attempt, durationMs: 2400 });
  fireEvent.click(screen.getByText("Guardar para repetir"));
  await waitFor(() => expect(save).toHaveBeenCalledWith("t1", { correct: true, used_hint: false, duration_ms: 2400 }));
});

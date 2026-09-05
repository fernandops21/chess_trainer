import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ApiError, api } from "../src/api/client";
import type { AttemptOut, SessionOut, TacticOut, TacticsStatus } from "../src/api/types";
import type { PuzzleCtl } from "../src/train/usePuzzle";
import { TacticSession, type TacticSummaryData } from "../src/train/TacticSession";
import { TacticSummary } from "../src/train/TacticSummary";
import type { SessionConfig } from "../src/train/SessionStart";

// A view real usa chessground (arrastar peça não é reproduzível no jsdom);
// aqui basta um botão que joga o lance da solução pelo mesmo `ctl`.
vi.mock("../src/train/PuzzleView", () => ({
  PuzzleView: ({ puzzle, ctl, orderInfo }: { puzzle: TacticOut; ctl: PuzzleCtl<unknown>; orderInfo?: string }) => (
    <div>
      <div>{orderInfo}</div>
      <button onClick={() => { const u = puzzle.solution.moves[0].uci; ctl.tryMove(u.slice(0, 2) as never, u.slice(2, 4) as never); }}>resolver</button>
    </div>
  ),
}));

const tactic = (id: string): TacticOut => ({
  id,
  kind: "tactic",
  fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1",
  side_to_move: "white",
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: [] }], explanation_pv: [] },
  end_reason: "material_gain",
  theme: "fork",
  themes: ["fork", "hangingPiece"],
  category: "lichess",
  rating: 1500,
  solver_moves: 1,
  lichess_url: `https://lichess.org/training/${id}`,
  popularity: 90,
  nb_plays: 300,
  opening_tags: [],
});

const session: SessionOut = { id: "s1", started_at: "2026-01-01T00:00:00Z", ended_at: null, planned_minutes: 25, filters: {}, reviews: 0, correct: 0, total_duration_ms: 0 };

const attempt = (over: Partial<AttemptOut> = {}): AttemptOut => ({
  id: "a1", puzzle_id: "t1", correct: true, used_hint: false,
  rating_before: 1200, rating_after: 1216, delta: 16, puzzle_rating: 1500, ...over,
});

const status: TacticsStatus = {
  imported: true, count: 100, imported_at: null, source_rows: null, rating: 1200, window: 200,
  attempts_total: 0, attempts_today: 0, attempts_30d: 0, correct_30d: 0,
};

const config: SessionConfig = { source: "tactics", filters: {}, plannedMinutes: 25, themes: ["fork"] };

function Host() {
  const [sum, setSum] = useState<TacticSummaryData | null>(null);
  return sum ? <TacticSummary {...sum} onNew={() => setSum(null)} /> : <TacticSession config={config} onFinish={setSum} />;
}

function renderSession() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><Host /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(status);
  vi.spyOn(api, "createSession").mockResolvedValue(session);
  vi.spyOn(api, "endSession").mockResolvedValue({ ...session, ended_at: "2026-01-01T00:25:00Z" });
  vi.spyOn(api, "attempt").mockResolvedValue(attempt());
});
afterEach(() => vi.restoreAllMocks());

test("cria a sessão de táticas e busca a primeira com os temas", async () => {
  const next = vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  renderSession();
  expect(await screen.findByText("resolver")).toBeTruthy();
  expect(api.createSession).toHaveBeenCalledWith({ planned_minutes: 25, filters: { source: "tactics", themes: ["fork"] } });
  expect(next).toHaveBeenCalledWith({ themes: ["fork"], exclude: [] });
  expect(screen.getByText("1ª tática · rating 1200")).toBeTruthy();
});

test("resolver mostra o rating novo e o link do Lichess", async () => {
  vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  renderSession();
  fireEvent.click(await screen.findByText("resolver"));
  expect(await screen.findByText("Rating 1200 → 1216 (+16)")).toBeTruthy();
  expect(screen.getByText("Resolvido sem erro.")).toBeTruthy();
  expect(screen.getByText("ver no Lichess").getAttribute("href")).toBe("https://lichess.org/training/t1");
  expect(api.attempt).toHaveBeenCalledWith(expect.objectContaining({ puzzle_id: "t1", session_id: "s1", correct: true }));
});

test("próximo exclui as táticas já vistas e o 404 encerra com o motivo", async () => {
  const next = vi.spyOn(api, "nextTactic")
    .mockResolvedValueOnce(tactic("t1"))
    .mockRejectedValueOnce(new ApiError(404, "Nenhuma tática nova com esses temas."));
  renderSession();
  fireEvent.click(await screen.findByText("resolver"));
  fireEvent.click(await screen.findByText("Próximo"));
  expect(next).toHaveBeenLastCalledWith({ themes: ["fork"], exclude: ["t1"] });
  expect(await screen.findByText("Nenhuma tática nova com esses temas.")).toBeTruthy();
  expect(screen.getByText("Rating 1200 → 1216")).toBeTruthy();
});

test("404 logo no começo encerra a sessão com o motivo", async () => {
  vi.spyOn(api, "nextTactic").mockRejectedValue(new ApiError(404, "Banco de táticas vazio."));
  renderSession();
  expect(await screen.findByText("Banco de táticas vazio.")).toBeTruthy();
  expect(screen.getByText("Nova sessão")).toBeTruthy();
});

test("encerrar sessão sai pelo resumo", async () => {
  vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  renderSession();
  fireEvent.click(await screen.findByText("Encerrar sessão"));
  expect(await screen.findByText("Sessão encerrada.")).toBeTruthy();
  expect(api.endSession).toHaveBeenCalledWith("s1");
});

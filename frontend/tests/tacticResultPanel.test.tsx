import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import { TacticResultPanel } from "../src/train/TacticResultPanel";
import type { AttemptOut, TacticOut } from "../src/api/types";

// o painel traz o botão "Guardar para repetir", que é uma mutation
function renderPanel(tactic: TacticOut, extra: { attempt?: AttemptOut; durationMs?: number } = {}) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <TacticResultPanel tactic={tactic} {...extra} onRetry={() => {}} onNext={() => {}} />
    </QueryClientProvider>,
  );
}

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

test("brancas a jogar no lance 12 mostra '12.' antes do primeiro lance", () => {
  const tactic = baseTactic({ fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 12" });
  renderPanel(tactic);
  expect(screen.getByText(/^12\. /)).toBeTruthy();
});

test("pretas a jogar no lance 24 mostra '24…' antes do primeiro lance", () => {
  const tactic = baseTactic({
    fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 b - - 0 24",
    side_to_move: "black",
    solution: { moves: [{ uci: "d5d1", by: "solver", alternatives: [] }], explanation_pv: [] },
  });
  renderPanel(tactic);
  expect(screen.getByText(/^24… /)).toBeTruthy();
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

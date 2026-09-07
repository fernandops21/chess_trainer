import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test } from "vitest";
import { TacticResultPanel } from "../src/train/TacticResultPanel";
import type { TacticOut } from "../src/api/types";

// o painel traz o botão "Guardar para repetir", que é uma mutation
function renderPanel(tactic: TacticOut) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <TacticResultPanel tactic={tactic} onRetry={() => {}} onNext={() => {}} />
    </QueryClientProvider>,
  );
}

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

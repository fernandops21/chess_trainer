import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test } from "vitest";
import type { PuzzleOut } from "../src/api/types";
import { ResultPanel } from "../src/train/ResultPanel";

const base: PuzzleOut = {
  id: "p1",
  kind: "punish",
  fen_start: "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 12",
  side_to_move: "white",
  solution: {
    moves: [
      { uci: "e1e8", by: "solver", alternatives: [] },
      { uci: "c8e8", by: "engine", alternatives: [] },
    ],
    explanation_pv: [],
  },
  end_reason: "material_gain",
  theme: "study",
  category: "study",
  solver_moves: 1,
  is_leech: false,
  srs: { ease: 2.5, interval_days: 0, lapses: 0, due_at: null, last_reviewed_at: null },
  source: "own",
  in_queue: true,
  fen_before: null,
  last_move: null,
  game: { id: "g1", white: "eu", black: "ele", played_at: "2026-01-01T00:00:00Z", source_id: "https://chess.com/g1", my_color: "white" },
  ply: 23,
  move_played: "Re2",
  mistake: { ply: 23, move_played: "Re2", move_uci: "e1e2", eval_before: 30, eval_after: -200, mistake_level: "mistake", mistake_by: "me" },
  study: null,
  siblings: [],
};

const study = (over: Partial<PuzzleOut> = {}): PuzzleOut => ({
  ...base,
  source: "study",
  game: null,
  ply: null,
  move_played: null,
  mistake: null,
  study: { id: "s1", title: "Finais de torre", chapter_id: "c1", chapter_name: "Ponte de Lucena", lichess_url: "https://lichess.org/study/aaa/bbb" },
  ...over,
});

function renderPanel(puzzle: PuzzleOut) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter>
        <ResultPanel puzzle={puzzle} onRetry={() => {}} onNext={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("puzzle de estudo não mostra links de partida e leva ao capítulo no Lichess", () => {
  renderPanel(study());
  expect(screen.queryByText("partida no chess.com")).toBeNull();
  expect(screen.queryByText("partida no app")).toBeNull();
  expect(screen.getByText("ver no Lichess").getAttribute("href")).toBe("https://lichess.org/study/aaa/bbb");
  expect(screen.getByText("Finais de torre · Ponte de Lucena")).toBeTruthy();
});

test("puzzle próprio continua com os dois links da partida", () => {
  renderPanel(base);
  expect(screen.getByText("partida no chess.com").getAttribute("href")).toBe("https://chess.com/g1");
  expect(screen.getByText("partida no app").getAttribute("href")).toBe("/partidas/g1?ply=23");
});

test("comentário do autor aparece na posição corrente da linha", () => {
  renderPanel(study({ solution: { ...base.solution, comments: { "0": "A torre entra pela oitava.", "1": "e o rei está preso." } } }));
  expect(screen.getByText("e o rei está preso.")).toBeTruthy();
  fireEvent.click(screen.getByLabelText("anterior"));
  expect(screen.getByText("A torre entra pela oitava.")).toBeTruthy();
});

test("resultado traz o botão de tirar da repetição", () => {
  renderPanel(study());
  expect(screen.getByText("Tirar da repetição")).toBeTruthy();
});

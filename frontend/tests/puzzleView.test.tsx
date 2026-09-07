import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import type { AttemptOut, PuzzleOut, TacticOut } from "../src/api/types";
import { PuzzleView } from "../src/train/PuzzleView";
import { usePuzzle } from "../src/train/usePuzzle";

const tactic: TacticOut = {
  id: "00sHx",
  kind: "tactic",
  fen_start: "q5nr/1ppknQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 w - - 1 18",
  side_to_move: "white",
  solution: {
    moves: [
      { uci: "a2e6", by: "solver", alternatives: [] },
      { uci: "d7d8", by: "engine", alternatives: [] },
      { uci: "f7f8", by: "solver", alternatives: [] },
    ],
    explanation_pv: [],
  },
  end_reason: "mate",
  theme: "mateIn2",
  themes: ["mate", "mateIn2"],
  category: "lichess",
  rating: 1760,
  solver_moves: 2,
  lichess_url: "https://lichess.org/training/00sHx",
  popularity: 83,
  nb_plays: 720,
  opening_tags: [],
  saved: false,
};

const own: PuzzleOut = {
  id: "p1",
  kind: "punish",
  fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1",
  side_to_move: "white",
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: [] }], explanation_pv: [] },
  end_reason: "material_gain",
  theme: "hanging_piece",
  category: "rapid",
  solver_moves: 1,
  is_leech: false,
  srs: { ease: 2.5, interval_days: 0, lapses: 0, due_at: null, last_reviewed_at: null },
  source: "own",
  in_queue: true,
  fen_before: null,
  last_move: null,
  game: { id: "g", white: "eu", black: "ela", played_at: "2026-09-04T12:00:00", source_id: "https://x", my_color: "white" },
  ply: 21,
  move_played: "Nb1",
  mistake: { ply: 21, move_played: "Nb1", move_uci: "c3b1", eval_before: 20, eval_after: -300, mistake_level: "blunder", mistake_by: "me" },
  study: null,
  siblings: [],
};

const saved: PuzzleOut = {
  ...own,
  id: "p2",
  source: "lichess",
  category: "lichess",
  theme: "mateIn2",
  game: null,
  ply: null,
  move_played: null,
  mistake: null,
};

const chapter: PuzzleOut = {
  ...own,
  id: "p3",
  source: "study",
  category: "study",
  theme: "study",
  game: null,
  ply: null,
  move_played: null,
  mistake: null,
  study: { id: "s1", title: "Finais de torre", chapter_id: "c1", chapter_name: "Ponte de Lucena", lichess_url: "https://lichess.org/study/aaa/bbb" },
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: [] }], explanation_pv: [], intro: "As brancas ganham a peça. Como?" },
};

function TacticHost() {
  const ctl = usePuzzle<AttemptOut>(tactic, { sessionId: null, submit: async () => ({}) as never });
  return <PuzzleView puzzle={tactic} ctl={ctl} />;
}

function OwnHost() {
  const ctl = usePuzzle(own, { sessionId: null, submit: async () => ({}) as never });
  return <PuzzleView puzzle={own} ctl={ctl} />;
}

test("mostra cabeçalho de tática com rating e tema traduzido", () => {
  render(<TacticHost />);
  expect(screen.getByText(/Brancas jogam · tática/)).toBeTruthy();
  expect(screen.getByText("mate em 2")).toBeTruthy();
  expect(screen.getByText(/rating 1760/)).toBeTruthy();
  expect(screen.getByText(/2 lance\(s\) seu\(s\)/)).toBeTruthy();
});

test("cabeçalho dos puzzles próprios não muda", () => {
  render(<OwnHost />);
  expect(screen.getByText(/Brancas jogam · punir o erro/)).toBeTruthy();
  expect(screen.getByText("peça pendurada")).toBeTruthy();
  expect(screen.getByText(/eu × ela, lance 11 · 1 lance\(s\) seu\(s\) · novo/)).toBeTruthy();
});

function Host({ puzzle }: { puzzle: PuzzleOut }) {
  const ctl = usePuzzle(puzzle, { sessionId: null, submit: async () => ({}) as never });
  return <PuzzleView puzzle={puzzle} ctl={ctl} />;
}

test("tática guardada do Lichess se identifica no cabeçalho", () => {
  render(<Host puzzle={saved} />);
  expect(screen.getByText(/tática do Lichess guardada/)).toBeTruthy();
  expect(screen.getByText("mate em 2")).toBeTruthy();
  expect(screen.queryByText(/eu × ela/)).toBeNull();
});

test("exercício de estudo mostra estudo, capítulo e enunciado", () => {
  render(<Host puzzle={chapter} />);
  expect(screen.getByText(/Finais de torre · Ponte de Lucena/)).toBeTruthy();
  expect(screen.getByText("As brancas ganham a peça. Como?")).toBeTruthy();
  expect(screen.queryByText(/eu × ela/)).toBeNull();
});

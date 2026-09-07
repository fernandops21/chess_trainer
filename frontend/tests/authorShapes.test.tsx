import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { BoardProps } from "../src/board/Board";
import type { PuzzleOut } from "../src/api/types";

// Dublê do tabuleiro: as setas/casas do autor são um detalhe do chessground,
// então o que interessa testar é o que os componentes mandam para o Board.
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

import { LineViewer } from "../src/train/LineViewer";
import { PuzzleView } from "../src/train/PuzzleView";
import { usePuzzle } from "../src/train/usePuzzle";

const last = () => boardProps.at(-1) as unknown as BoardProps;

beforeEach(() => { boardProps.length = 0; });

const chapter: PuzzleOut = {
  id: "p1",
  kind: "punish",
  fen_start: "2r1R1k1/5ppp/8/8/Q7/8/8/6K1 b - - 1 24",
  side_to_move: "black",
  solution: {
    moves: [{ uci: "c8e8", by: "solver", alternatives: [] }, { uci: "a4e8", by: "engine", alternatives: [] }],
    explanation_pv: [],
    shapes: {
      start: [{ orig: "c8", dest: "e8", brush: "green" }, { orig: "g8", brush: "red" }],
      "0": [{ orig: "a4", dest: "e8", brush: "blue" }],
    },
  },
  end_reason: "material_gain",
  theme: "study",
  category: "study",
  solver_moves: 1,
  is_leech: false,
  srs: { ease: 2.5, interval_days: 0, lapses: 0, due_at: null, last_reviewed_at: null },
  source: "study",
  in_queue: true,
  fen_before: "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 24",
  last_move: "e1e8",
  game: null,
  ply: null,
  move_played: null,
  mistake: null,
  study: { id: "s1", title: "Finais", chapter_id: "c1", chapter_name: "Um", lichess_url: null },
  siblings: [],
};

function Host() {
  const ctl = usePuzzle(chapter, { sessionId: null, submit: async () => ({}) as never, introDelayMs: 0 });
  return <PuzzleView puzzle={chapter} ctl={ctl} />;
}

test("o tabuleiro do puzzle desenha as marcações do autor da posição inicial", () => {
  render(<Host />);
  const p = last();
  expect(p.drawable).toBe(true);
  expect(p.arrows).toEqual([{ orig: "c8", dest: "e8", brush: "green" }]);
  expect(p.squares).toEqual([{ orig: "g8", brush: "red" }]);
});

test("a linha do resultado mostra as marcações do autor da posição corrente", () => {
  render(
    <LineViewer fenStart={chapter.fen_start} ucis={["c8e8", "a4e8"]} orientation="black" startPly={48}
      shapes={chapter.solution.shapes} initialPos={0} keyboard={false} />,
  );
  expect(last().drawable).toBe(true);
  expect(last().arrows).toEqual([{ orig: "c8", dest: "e8", brush: "green" }]);
  expect(last().squares).toEqual([{ orig: "g8", brush: "red" }]);

  fireEvent.click(screen.getByLabelText("próximo"));
  expect(last().arrows).toEqual([{ orig: "a4", dest: "e8", brush: "blue" }]);
  expect(last().squares).toEqual([]);
});

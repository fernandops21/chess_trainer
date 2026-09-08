import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { PuzzleOut } from "../src/api/types";
import type { BoardProps } from "../src/board/Board";

// o chessground não roda no jsdom: o dublê guarda as props do tabuleiro
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

import { MistakeCard } from "../src/train/MistakeCard";

const last = () => boardProps.at(-1) as unknown as BoardProps;

const FEN_ANTES = "4k3/8/8/3q4/8/2N5/7P/4K3 b - - 0 20";
const FEN_INICIO = "4k3/8/8/8/8/2Nq4/7P/4K3 w - - 0 21";

const punir: PuzzleOut = {
  id: "p1",
  kind: "punish",
  fen_start: FEN_INICIO,
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
  fen_before: FEN_ANTES,
  last_move: "d5d3",
  game: { id: "g1", white: "eu", black: "ela", played_at: "2026-01-01T00:00:00Z", source_id: "https://chess.com/g1", my_color: "white" },
  ply: 40,
  move_played: "Qd3",
  mistake: { ply: 40, move_played: "Qd3", move_uci: "d5d3", eval_before: 20, eval_after: -300, mistake_level: "mistake", mistake_by: "opponent" },
  study: null,
  siblings: [],
};

const evitar: PuzzleOut = {
  ...punir,
  id: "p2",
  kind: "avoid",
  ply: 41,
  move_played: "Nb1",
  mistake: { ply: 41, move_played: "Nb1", move_uci: "c3b1", eval_before: 20, eval_after: -300, mistake_level: "blunder", mistake_by: "me" },
};

function renderCard(puzzle: PuzzleOut) {
  boardProps.length = 0;
  return render(<MemoryRouter><MistakeCard puzzle={puzzle} /></MemoryRouter>);
}

test("evitar mostra a posição do exercício com o lance que você jogou", () => {
  const { container } = renderCard(evitar);
  expect(last().fen).toBe(FEN_INICIO);
  expect(last().lastMove).toEqual(["c3", "b1"]);
  expect(container.textContent).toMatch(/Na partida você jogou\s*Nb1\s*\(\+0\.20 → -3\.00\)/);
  expect(screen.getByText("blunder")).toBeTruthy();
});

test("punir mostra a posição de antes do lance do adversário", () => {
  const { container } = renderCard(punir);
  expect(last().fen).toBe(FEN_ANTES);
  expect(last().lastMove).toEqual(["d5", "d3"]);
  expect(container.textContent).toMatch(/Na partida o adversário jogou\s*Qd3/);
  expect(screen.getByText("erro")).toBeTruthy();
});

test("sem a posição de antes, punir cai na posição do exercício", () => {
  renderCard({ ...punir, fen_before: null });
  expect(last().fen).toBe(FEN_INICIO);
});

test("os links levam à partida e à revisão de erros", () => {
  renderCard(evitar);
  expect(screen.getByText("partida no app").getAttribute("href")).toBe("/partidas/g1?ply=41");
  expect(screen.getByText("revisão de erros").getAttribute("href")).toBe(`/erros?position=${encodeURIComponent(FEN_INICIO)}`);
});

test("no punir, a revisão de erros abre pela posição de antes do lance do adversário", () => {
  renderCard(punir);
  expect(screen.getByText("revisão de erros").getAttribute("href")).toBe(`/erros?position=${encodeURIComponent(FEN_ANTES)}`);
});

// --- punir com a resposta da partida -------------------------------------

const RESPOSTA = { ply: 41, move_played: "Ne4", move_uci: "c3e4", eval_before: 300, eval_after: 20 };
const punirComResposta: PuzzleOut = { ...punir, mistake: { ...punir.mistake!, my_reply: RESPOSTA } };

test("punir com a resposta mostra a posição do exercício e o lance que você jogou", () => {
  const { container } = renderCard(punirComResposta);
  expect(last().fen).toBe(FEN_INICIO);
  expect(last().lastMove).toEqual(["c3", "e4"]);
  expect(container.textContent).toMatch(/Na partida o adversário jogou\s*Qd3/);
  expect(container.textContent).toMatch(/Você respondeu\s*Ne4\s*\(\+3\.00 → \+0\.20\)\s*e deixou passar\s*Nd5/);
  // o link da revisão continua na posição de antes do lance do adversário
  expect(screen.getByText("revisão de erros").getAttribute("href")).toBe(`/erros?position=${encodeURIComponent(FEN_ANTES)}`);
});

test("quando a resposta foi a própria solução, o cartão diz que você achou", () => {
  const { container } = renderCard({
    ...punir,
    mistake: { ...punir.mistake!, my_reply: { ...RESPOSTA, move_played: "Nd5", move_uci: "c3d5" } },
  });
  expect(container.textContent).toMatch(/Você achou\s*Nd5\s*na partida\./);
  expect(container.textContent).not.toMatch(/deixou passar/);
});

test("a alternativa da solução também conta como achada", () => {
  const alternativa: PuzzleOut = {
    ...punir,
    solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: ["c3e4"] }], explanation_pv: [] },
    mistake: { ...punir.mistake!, my_reply: RESPOSTA },
  };
  // o lance mostrado é o que o usuário jogou de fato (a alternativa), não o principal da solução
  expect(renderCard(alternativa).container.textContent).toMatch(/Você achou\s*Ne4\s*na partida\./);
});

test("evitar não usa a resposta da partida nem com ela na API", () => {
  const { container } = renderCard({ ...evitar, mistake: { ...evitar.mistake!, my_reply: RESPOSTA } });
  expect(last().lastMove).toEqual(["c3", "b1"]);
  expect(container.textContent).toMatch(/Na partida você jogou\s*Nb1/);
  expect(container.textContent).not.toMatch(/Você respondeu/);
});

test("sem erro ou sem partida o cartão não aparece", () => {
  const { container } = renderCard({ ...evitar, mistake: null });
  expect(container.textContent).toBe("");
  const semPartida = renderCard({ ...evitar, game: null });
  expect(semPartida.container.textContent).toBe("");
});

import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import type { AnalyseOut, AttemptOut, PuzzleOut, TacticOut } from "../src/api/types";
import type { BoardProps } from "../src/board/Board";

// Dublê do tabuleiro: o desenho das setas/casas é detalhe do chessground, então
// o que dá para inspecionar aqui é o que a `PuzzleView` manda para o Board.
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

import { PuzzleView } from "../src/train/PuzzleView";
import { usePuzzle } from "../src/train/usePuzzle";

const last = () => boardProps.at(-1) as unknown as BoardProps;

beforeEach(() => { boardProps.length = 0; });

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

test("dica em dois estágios: rótulo muda e o botão segue habilitado", () => {
  render(<Host puzzle={own} />);
  const btn = screen.getByRole("button", { name: "Dica" }) as HTMLButtonElement;
  expect(btn.textContent).toBe("Mostrar peça");
  expect(btn.disabled).toBe(false);
  fireEvent.click(btn);
  expect(btn.textContent).toBe("Jogar o lance");
  expect(btn.disabled).toBe(false);
  expect(screen.getByText(/Clique de novo para jogar o lance/)).toBeTruthy();
});

test("o botão Pular só aparece quando onSkip é passado", () => {
  const { unmount } = render(<Host puzzle={own} />);
  expect(screen.queryByRole("button", { name: "Pular" })).toBeNull();
  unmount();

  const onSkip = vi.fn();
  function SkipHost() {
    const ctl = usePuzzle(own, { sessionId: null, submit: async () => ({}) as never });
    return <PuzzleView puzzle={own} ctl={ctl} onSkip={onSkip} />;
  }
  render(<SkipHost />);
  const btn = screen.getByRole("button", { name: "Pular" }) as HTMLButtonElement;
  expect(btn.disabled).toBe(false);
  fireEvent.click(btn);
  expect(onSkip).toHaveBeenCalledTimes(1);
});

test("o botão Pular pode vir desabilitado", () => {
  function SkipHost() {
    const ctl = usePuzzle(own, { sessionId: null, submit: async () => ({}) as never });
    return <PuzzleView puzzle={own} ctl={ctl} onSkip={() => {}} skipDisabled />;
  }
  render(<SkipHost />);
  expect((screen.getByRole("button", { name: "Pular" }) as HTMLButtonElement).disabled).toBe(true);
});

// --- cartão "Meu erro" --------------------------------------------------

function comRotas(node: ReactNode) {
  return render(<MemoryRouter>{node}</MemoryRouter>);
}

test("o cartão do erro fica escondido atrás do botão 'Meu erro'", () => {
  const { container } = comRotas(<Host puzzle={own} />);
  const botao = screen.getByRole("button", { name: /Meu erro|Erro do adversário/ });
  expect(container.textContent).not.toMatch(/Na partida/);
  fireEvent.click(botao);
  expect(container.textContent).toMatch(/Na partida você jogou\s*Nb1/);
  expect(screen.getByText("partida no app")).toBeTruthy();
  fireEvent.click(botao);
  expect(container.textContent).not.toMatch(/Na partida/);
});

test("no 'evitar' o botão avisa que revela o lance a não jogar", () => {
  comRotas(<Host puzzle={{ ...own, kind: "avoid" }} />);
  expect(screen.getByRole("button", { name: "Meu erro (revela o lance que não jogar)" })).toBeTruthy();
});

test("sem erro de partida não há botão 'Meu erro'", () => {
  const { unmount } = comRotas(<Host puzzle={chapter} />);
  expect(screen.queryByRole("button", { name: /Meu erro/ })).toBeNull();
  unmount();
  comRotas(<TacticHost />);
  expect(screen.queryByRole("button", { name: /Meu erro/ })).toBeNull();
});

// --- refutação do lance errado ------------------------------------------

// `h2h3` é legal e errado na posição de `own`; a engine dublê responde `Qg2`.
const FEN_ERRO = "4k3/8/8/3q4/8/2N4P/8/4K3 b - - 0 1";
const analiseOut = (fen: string, move: string, san: string, score: number): AnalyseOut =>
  ({ fen, turn: fen.split(" ")[1] === "b" ? "black" : "white", terminal: null, lines: [{ move, san, score, pv: [move], pv_san: [san] }] });
const engine = async (fen: string) => (fen === own.fen_start
  ? analiseOut(fen, "c3d5", "Nxd5", 900)
  : analiseOut(FEN_ERRO, "d5g2", "Qg2", 500));

function RefutaHost({ retry }: { retry?: () => void }) {
  const ctl = usePuzzle(own, { sessionId: null, submit: async () => ({}) as never, refute: true, analyse: engine });
  return (
    <>
      <button onClick={() => ctl.tryMove("h2", "h3")}>errar</button>
      <PuzzleView puzzle={own} ctl={retry ? { ...ctl, retryMove: retry } : ctl} onSkip={() => {}} />
    </>
  );
}

test("com o lance errado no tabuleiro a dica dá lugar ao 'Tentar de novo'", async () => {
  render(<RefutaHost />);
  expect(screen.getByRole("button", { name: "Dica" })).toBeTruthy();
  fireEvent.click(screen.getByText("errar"));
  expect(await screen.findByRole("button", { name: "Tentar de novo" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Dica" })).toBeNull();
  // o "Pular" continua onde estava
  expect(screen.getByRole("button", { name: "Pular" })).toBeTruthy();
  expect(screen.getByText("h3? Qg2 — avaliação cai de +9.00 para -5.00")).toBeTruthy();
});

test("clicar em 'Tentar de novo' chama retryMove", async () => {
  const retry = vi.fn();
  render(<RefutaHost retry={retry} />);
  fireEvent.click(screen.getByText("errar"));
  fireEvent.click(await screen.findByRole("button", { name: "Tentar de novo" }));
  expect(retry).toHaveBeenCalledTimes(1);
});

// exercício de estudo com marcações do autor na posição inicial
const comSetas: PuzzleOut = { ...chapter, id: "p4",
  solution: { ...chapter.solution, shapes: { start: [{ orig: "c3", dest: "d5", brush: "green" }, { orig: "e1", brush: "red" }] } } };

function SetasHost() {
  const ctl = usePuzzle(comSetas, { sessionId: null, submit: async () => ({}) as never, refute: true, analyse: engine });
  return (
    <>
      <button onClick={() => ctl.tryMove("h2", "h3")}>errar</button>
      <PuzzleView puzzle={comSetas} ctl={ctl} />
    </>
  );
}

test("as marcações do autor somem enquanto a refutação está no tabuleiro", async () => {
  render(<SetasHost />);
  expect(last().arrows).toEqual([{ orig: "c3", dest: "d5", brush: "green" }]);
  expect(last().squares).toEqual([{ orig: "e1", brush: "red" }]);

  // com o lance errado (e depois a réplica) no tabuleiro as peças marcadas já
  // saíram das casas: as setas do autor apontariam para o lugar errado
  fireEvent.click(screen.getByText("errar"));
  expect(last().arrows).toEqual([]);
  expect(last().squares).toEqual([]);
  const voltar = await screen.findByRole("button", { name: "Tentar de novo" });
  expect(last().arrows).toEqual([]);
  expect(last().squares).toEqual([]);

  // de volta à posição inicial elas voltam
  fireEvent.click(voltar);
  expect(last().arrows).toEqual([{ orig: "c3", dest: "d5", brush: "green" }]);
  expect(last().squares).toEqual([{ orig: "e1", brush: "red" }]);
});

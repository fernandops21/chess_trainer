import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { PuzzleOut, TacticOut } from "../src/api/types";
import { QueueButtons } from "../src/train/QueueButtons";

const puzzle = (over: Partial<PuzzleOut> = {}): PuzzleOut => ({
  id: "p1",
  kind: "punish",
  fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1",
  side_to_move: "white",
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: [] }], explanation_pv: [] },
  end_reason: "material_gain",
  theme: "fork",
  category: "rapid",
  solver_moves: 1,
  is_leech: false,
  srs: { ease: 2.5, interval_days: 0, lapses: 0, due_at: null, last_reviewed_at: null },
  source: "own",
  in_queue: true,
  fen_before: null,
  last_move: null,
  game: null,
  ply: null,
  move_played: null,
  mistake: null,
  study: null,
  siblings: [],
  ...over,
});

const tactic = (over: Partial<TacticOut> = {}): TacticOut => ({
  id: "00sHx",
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
  lichess_url: "https://lichess.org/training/00sHx",
  popularity: 90,
  nb_plays: 300,
  opening_tags: [],
  saved: false,
  ...over,
});

function renderButtons(node: React.ReactNode) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      {node}
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

test("puzzle na fila oferece tirar da repetição e troca o rótulo", async () => {
  const setQueue = vi.spyOn(api, "setQueue").mockResolvedValue(puzzle({ in_queue: false }));
  renderButtons(<QueueButtons puzzle={puzzle()} />);
  fireEvent.click(screen.getByText("Tirar da repetição"));
  expect(await screen.findByText("Voltar para a repetição")).toBeTruthy();
  expect(setQueue).toHaveBeenCalledWith("p1", false);
});

test("puzzle fora da fila oferece voltar para a repetição", async () => {
  const setQueue = vi.spyOn(api, "setQueue").mockResolvedValue(puzzle({ in_queue: true }));
  renderButtons(<QueueButtons puzzle={puzzle({ in_queue: false })} />);
  fireEvent.click(screen.getByText("Voltar para a repetição"));
  expect(await screen.findByText("Tirar da repetição")).toBeTruthy();
  expect(setQueue).toHaveBeenCalledWith("p1", true);
});

test("erro ao tirar volta o rótulo ao estado anterior", async () => {
  vi.spyOn(api, "setQueue").mockRejectedValue(new Error("falhou"));
  renderButtons(<QueueButtons puzzle={puzzle()} />);
  fireEvent.click(screen.getByText("Tirar da repetição"));
  expect(screen.getByText("Voltar para a repetição")).toBeTruthy();
  await waitFor(() => expect(screen.getByText("Tirar da repetição")).toBeTruthy());
});

test("tática ainda não guardada guarda e vira Guardado", async () => {
  const save = vi.spyOn(api, "saveTactic").mockResolvedValue(puzzle({ source: "lichess" }));
  renderButtons(<QueueButtons puzzle={tactic()} />);
  fireEvent.click(screen.getByText("Guardar para repetir"));
  expect(await screen.findByText("Guardado ✓")).toBeTruthy();
  expect(save).toHaveBeenCalledWith("00sHx");
});

test("tática já guardada mostra o botão desabilitado", () => {
  renderButtons(<QueueButtons puzzle={tactic({ saved: true })} />);
  const b = screen.getByText("Guardado ✓") as HTMLButtonElement;
  expect(b.disabled).toBe(true);
});

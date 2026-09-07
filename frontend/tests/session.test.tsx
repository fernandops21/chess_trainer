import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { TrainPage } from "../src/train/TrainPage";

const puzzle = {
  id: "p1",
  kind: "punish",
  fen_start: "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1",
  side_to_move: "white",
  solution: { moves: [{ uci: "e1e8", by: "solver", alternatives: [] }], explanation_pv: [] },
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
  study: null,
  game: { id: "g1", white: "eu", black: "ele", played_at: "2026-01-01T00:00:00Z", source_id: "s", my_color: "white" },
  ply: 40,
  move_played: "Re2",
  mistake: { ply: 40, move_played: "Re2", move_uci: "e1e2", eval_before: 30, eval_after: -200, mistake_level: "mistake", mistake_by: "me" },
  siblings: [],
};

const outro = { ...puzzle, id: "p2", game: { ...puzzle.game, id: "g2", white: "outro" } };

const bodies: Record<string, unknown> = {
  "/api/sessions": { id: "s1", started_at: "2026-01-01T00:00:00Z", ended_at: null, planned_minutes: 25, filters: {}, reviews: 0, correct: 0, total_duration_ms: 0 },
  "/api/queue": { due_count: 1, new_available: 0, new_remaining_today: 0, items: [puzzle] },
  "/api/dashboard": { due_today: 1, new_available: 0, new_remaining_today: 0, streak_days: 0, reviews_today: 0, last_import_at: null, games_total: 0, games_analyzed: 0, puzzles_total: 0, leeches: 0 },
  "/api/status": { engine: { available: true, path: null }, job: { state: "idle", job: null, stage: "", done: 0, total: 0, message: "", error: null, finished_at: null }, games_total: 0, games_pending: 0, last_import_at: null, local_url: "" },
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  bodies["/api/queue"] = { due_count: 1, new_available: 0, new_remaining_today: 0, items: [puzzle] };
  fetchMock = vi.fn(async (url: string) => {
    const path = String(url).split("?")[0];
    const body = bodies[path];
    if (body === undefined) throw new Error(`sem stub para ${url}`);
    return { ok: true, status: 200, json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

test("a sessão inicia sob StrictMode e cria apenas uma sessão", async () => {
  render(
    <React.StrictMode>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <TrainPage />
        </MemoryRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  );

  fireEvent.click(screen.getByText("Começar"));

  expect(await screen.findByText(/jogam/)).toBeTruthy();
  const sessionCalls = fetchMock.mock.calls.filter((c) => String(c[0]) === "/api/sessions");
  expect(sessionCalls.length).toBe(1);
});

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <TrainPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("pular manda o puzzle para o fim da lista e mostra o próximo", async () => {
  bodies["/api/queue"] = { due_count: 2, new_available: 0, new_remaining_today: 0, items: [puzzle, outro] };
  renderPage();
  fireEvent.click(screen.getByText("Começar"));

  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Pular" }));
  expect(await screen.findByText(/outro × ele/)).toBeTruthy();
  expect(screen.getByText(/1 pulado\(s\)/)).toBeTruthy();
  // o pulado não conta como resolvido: a ordem da sessão continua no 1º
  expect(screen.getByText(/1º da sessão/)).toBeTruthy();

  // pulando o último, o que foi para o fim volta a aparecer
  fireEvent.click(screen.getByRole("button", { name: "Pular" }));
  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  expect(screen.getByText(/2 pulado\(s\)/)).toBeTruthy();
});

test("pular não registra revisão", async () => {
  bodies["/api/queue"] = { due_count: 2, new_available: 0, new_remaining_today: 0, items: [puzzle, outro] };
  renderPage();
  fireEvent.click(screen.getByText("Começar"));

  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Pular" }));
  await screen.findByText(/outro × ele/);
  expect(fetchMock.mock.calls.some((c) => String(c[0]).startsWith("/api/reviews"))).toBe(false);
});

test("com um único puzzle na lista o botão Pular fica desabilitado", async () => {
  renderPage();
  fireEvent.click(screen.getByText("Começar"));

  await screen.findByText(/jogam/);
  expect((screen.getByRole("button", { name: "Pular" }) as HTMLButtonElement).disabled).toBe(true);
});

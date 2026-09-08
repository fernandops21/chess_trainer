import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ReviewPage } from "../src/train/ReviewPage";
import { SETTINGS } from "./fixtures/settings";

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

const SESSION = { id: "s1", started_at: "2026-01-01T00:00:00Z", ended_at: null, planned_minutes: null, filters: {}, reviews: 0, correct: 0, total_duration_ms: 0 };

const bodies: Record<string, unknown> = {
  "/api/sessions": SESSION,
  "/api/sessions/s1/end": { ...SESSION, ended_at: "2026-01-01T00:10:00Z" },
  "/api/reviews": { id: "r1", puzzle_id: "p1", result: "correct", used_hint: true, ease: 2.5, interval_days: 1, due_at: "2026-01-02T00:00:00Z", lapses: 0, is_leech: false },
  "/api/queue": { mode: "review", due_count: 1, new_available: 0, new_remaining_today: 0, items: [puzzle] },
  "/api/dashboard": { due_today: 1, new_available: 0, new_remaining_today: 0, streak_days: 0, reviews_today: 0, last_import_at: null, games_total: 0, games_analyzed: 0, puzzles_total: 0, leeches: 0 },
  "/api/settings": SETTINGS,
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  localStorage.clear();
  bodies["/api/queue"] = { mode: "review", due_count: 1, new_available: 0, new_remaining_today: 0, items: [puzzle] };
  fetchMock = vi.fn(async (url: string) => {
    const path = String(url).split("?")[0];
    const body = bodies[path];
    if (body === undefined) throw new Error(`sem stub para ${url}`);
    return { ok: true, status: 200, json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
});
// desmonta antes de tirar o dublê do `fetch`: o encerramento agendado na saída da
// tela roda no próximo tique e não pode vazar para o teste seguinte
afterEach(async () => {
  cleanup();
  await new Promise((r) => setTimeout(r, 0));
  vi.unstubAllGlobals();
});

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><ReviewPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const urls = (prefixo: string) => fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.startsWith(prefixo));
/** Só a criação de sessão (`/api/sessions/<id>/end` também começa com o mesmo prefixo). */
const criacoes = () => fetchMock.mock.calls.filter((c) => String(c[0]) === "/api/sessions").length;

test("abre direto na sessão de vencidos, sem tela de início e sem outros filtros", async () => {
  renderPage();
  expect(screen.getByRole("heading", { name: "Revisar", level: 1 })).toBeTruthy();
  // nada de escolher modo, fontes ou tempo
  expect(screen.queryByText("Começar")).toBeNull();

  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  expect(criacoes()).toBe(1);
  expect(urls("/api/queue")).toEqual(["/api/queue?mode=review"]);
});

test("a sessão vai até acabar a fila, sem tempo planejado", async () => {
  renderPage();
  await screen.findByText(/eu × ele/);
  const criada = fetchMock.mock.calls.find((c) => String(c[0]) === "/api/sessions")!;
  expect(JSON.parse(String((criada[1] as RequestInit).body))).toEqual({ planned_minutes: null, filters: { mode: "review" } });
});

test("fila vazia manda fazer novos ou treinar um estudo", async () => {
  bodies["/api/queue"] = { mode: "review", due_count: 0, new_available: 4, new_remaining_today: 0, items: [] };
  renderPage();
  expect(await screen.findByText("Nada vencido. Faça novos ou treine um estudo.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Fazer novos" }).getAttribute("href")).toBe("/treinar?mode=new");
  expect(screen.getByRole("link", { name: "Estudos" }).getAttribute("href")).toBe("/estudos");
  expect(screen.queryByText("Analisar mais partidas")).toBeNull();
});

test("terminada a fila, o resumo abre outra sessão de vencidos", async () => {
  renderPage();
  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Dica" }));
  fireEvent.click(screen.getByRole("button", { name: "Dica" }));
  fireEvent.click(await screen.findByRole("button", { name: "Próximo puzzle" }));
  expect(await screen.findByText("Fila vazia por hoje.")).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "Nova sessão" }));
  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  expect(criacoes()).toBe(2);
});

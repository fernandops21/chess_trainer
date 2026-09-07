import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { TrainPage } from "../src/train/TrainPage";
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

const outro = { ...puzzle, id: "p2", game: { ...puzzle.game, id: "g2", white: "outro" } };

const bodies: Record<string, unknown> = {
  "/api/sessions": { id: "s1", started_at: "2026-01-01T00:00:00Z", ended_at: null, planned_minutes: 25, filters: {}, reviews: 0, correct: 0, total_duration_ms: 0 },
  "/api/reviews": { id: "r1", puzzle_id: "p1", result: "correct", used_hint: true, ease: 2.5, interval_days: 1, due_at: "2026-01-02T00:00:00Z", lapses: 0, is_leech: false },
  "/api/queue": { mode: "review", due_count: 1, new_available: 0, new_remaining_today: 0, items: [puzzle] },
  "/api/studies": [{ id: "s1", title: "Finais de torre", author: "", source_url: "", lichess_id: null, imported_at: null, chapter_count: 2, exercise_count: 2, in_queue: 2, due_today: 0 }],
  "/api/studies/s1": { id: "s1", title: "Finais de torre", author: "", source_url: "", lichess_id: null, imported_at: null, chapter_count: 2, exercise_count: 2, in_queue: 2, due_today: 0, chapters: [] },
  "/api/dashboard": { due_today: 1, new_available: 0, new_remaining_today: 0, streak_days: 0, reviews_today: 0, last_import_at: null, games_total: 0, games_analyzed: 0, puzzles_total: 0, leeches: 0 },
  "/api/settings": SETTINGS,
  "/api/status": { engine: { available: true, path: null }, job: { state: "idle", job: null, stage: "", done: 0, total: 0, message: "", error: null, finished_at: null }, games_total: 0, games_pending: 0, last_import_at: null, local_url: "" },
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
  bodies["/api/queue"] = { mode: "review", due_count: 2, new_available: 0, new_remaining_today: 0, items: [puzzle, outro] };
  renderPage();
  fireEvent.click(screen.getByText("Começar"));

  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Pular" }));
  expect(await screen.findByText(/outro × ele/)).toBeTruthy();
  expect(screen.getByText(/1 pulado\b/)).toBeTruthy();
  // o pulado não conta como resolvido: a ordem da sessão continua no 1º
  expect(screen.getByText(/1º da sessão/)).toBeTruthy();

  // pulando o último, o que foi para o fim volta a aparecer
  fireEvent.click(screen.getByRole("button", { name: "Pular" }));
  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  expect(screen.getByText(/2 pulados/)).toBeTruthy();
});

/** Resolve o puzzle na tela pela dica (dois cliques) e clica em Próximo. */
async function resolverEAvancar() {
  fireEvent.click(screen.getByRole("button", { name: "Dica" }));
  fireEvent.click(screen.getByRole("button", { name: "Dica" }));
  fireEvent.click(await screen.findByRole("button", { name: "Próximo puzzle" }));
}

test("pular o último não devolve um puzzle já resolvido", async () => {
  bodies["/api/queue"] = { mode: "review", due_count: 2, new_available: 0, new_remaining_today: 0, items: [puzzle, outro] };
  renderPage();
  fireEvent.click(screen.getByText("Começar"));

  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  await resolverEAvancar();
  expect(await screen.findByText(/outro × ele/)).toBeTruthy();

  // só resta um por resolver: pular não teria para onde ir sem repetir o resolvido
  const pular = screen.getByRole("button", { name: "Pular" }) as HTMLButtonElement;
  expect(pular.disabled).toBe(true);
  fireEvent.click(pular);
  expect(screen.queryByText(/eu × ele/)).toBeNull();
  expect(screen.getByText(/outro × ele/)).toBeTruthy();
  expect(fetchMock.mock.calls.filter((c) => String(c[0]) === "/api/reviews").length).toBe(1);
});

test("pular pula quem já foi resolvido e devolve o pulado depois", async () => {
  const terceiro = { ...puzzle, id: "p3", game: { ...puzzle.game, id: "g3", white: "terceiro" } };
  bodies["/api/queue"] = { mode: "review", due_count: 3, new_available: 0, new_remaining_today: 0, items: [puzzle, outro, terceiro] };
  renderPage();
  fireEvent.click(screen.getByText("Começar"));

  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  await resolverEAvancar();

  // pula o segundo: vai para o terceiro, nunca de volta ao resolvido
  expect(await screen.findByText(/outro × ele/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Pular" }));
  expect(await screen.findByText(/terceiro × ele/)).toBeTruthy();
  expect(screen.queryByText(/eu × ele/)).toBeNull();

  // resolvido o terceiro, o pulado volta — e aí não há mais o que pular
  await resolverEAvancar();
  expect(await screen.findByText(/outro × ele/)).toBeTruthy();
  expect((screen.getByRole("button", { name: "Pular" }) as HTMLButtonElement).disabled).toBe(true);
  expect(fetchMock.mock.calls.filter((c) => String(c[0]) === "/api/reviews").length).toBe(2);
});

test("pular não registra revisão", async () => {
  bodies["/api/queue"] = { mode: "review", due_count: 2, new_available: 0, new_remaining_today: 0, items: [puzzle, outro] };
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

const queueUrls = () => fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.startsWith("/api/queue"));

test("a repetição espaçada manda mode=review e mostra o título do modo", async () => {
  renderPage();
  fireEvent.click(screen.getByText("Começar"));

  await screen.findByText(/jogam/);
  expect(queueUrls()[0]).toContain("mode=review");
  expect(screen.getByRole("heading", { name: "Repetição espaçada" })).toBeTruthy();
});

test("os novos mandam mode=new e mostram o título do modo", async () => {
  renderPage();
  fireEvent.click(screen.getByLabelText("Novos (meus erros)"));
  fireEvent.click(screen.getByText("Começar"));

  await screen.findByText(/jogam/);
  expect(queueUrls()[0]).toContain("mode=new");
  expect(screen.getByRole("heading", { name: "Novos (meus erros)" })).toBeTruthy();
});

test("o estudo escolhido manda mode=study, o título do estudo e o capítulo atual", async () => {
  bodies["/api/queue"] = { mode: "study", due_count: 0, new_available: 0, new_remaining_today: 0, items: [puzzle, outro] };
  renderPage();
  await screen.findByRole("option", { name: "Finais de torre" });
  fireEvent.change(screen.getByLabelText("Estudo"), { target: { value: "s1" } });
  fireEvent.click(screen.getByText("Começar"));

  await screen.findByText(/jogam/);
  expect(queueUrls()[0]).toContain("mode=study");
  expect(queueUrls()[0]).toContain("study_id=s1");
  expect(await screen.findByRole("heading", { name: "Finais de torre" })).toBeTruthy();
  expect(screen.getByText(/capítulo 1 de 2/)).toBeTruthy();
});

test("fila vazia na repetição espaçada manda fazer novos ou treinar um estudo", async () => {
  bodies["/api/queue"] = { mode: "review", due_count: 0, new_available: 4, new_remaining_today: 0, items: [] };
  renderPage();
  fireEvent.click(screen.getByText("Começar"));
  expect(await screen.findByText("Nada vencido. Faça novos ou treine um estudo.")).toBeTruthy();
});

test("fila vazia nos novos diz quantos esperam amanhã", async () => {
  bodies["/api/queue"] = { mode: "new", due_count: 0, new_available: 7, new_remaining_today: 0, items: [] };
  renderPage();
  fireEvent.click(screen.getByLabelText("Novos (meus erros)"));
  fireEvent.click(screen.getByText("Começar"));
  expect(await screen.findByText("Sem erros novos (ou limite diário atingido: 7 esperando amanhã).")).toBeTruthy();
});

test("estudo sem exercícios na repetição avisa", async () => {
  bodies["/api/queue"] = { mode: "study", due_count: 0, new_available: 0, new_remaining_today: 0, items: [] };
  renderPage();
  await screen.findByRole("option", { name: "Finais de torre" });
  fireEvent.change(screen.getByLabelText("Estudo"), { target: { value: "s1" } });
  fireEvent.click(screen.getByText("Começar"));
  expect(await screen.findByText("Este estudo não tem exercícios na repetição.")).toBeTruthy();
});

test("fila vazia nos novos sem previsão futura não menciona amanhã", async () => {
  bodies["/api/queue"] = { mode: "new", due_count: 0, new_available: 0, new_remaining_today: 0, items: [] };
  renderPage();
  fireEvent.click(screen.getByLabelText("Novos (meus erros)"));
  fireEvent.click(screen.getByText("Começar"));
  expect(await screen.findByText("Sem erros novos.")).toBeTruthy();
});

// a fila do estudo é fixa (o backend sempre devolve o estudo inteiro): resolver o
// último exercício não pode recarregar a fila, senão os mesmos exercícios voltam
test("estudo com dois exercícios termina ao resolver o último, sem recarregar a fila", async () => {
  bodies["/api/queue"] = { mode: "study", due_count: 0, new_available: 0, new_remaining_today: 0, items: [puzzle, outro] };
  renderPage();
  await screen.findByRole("option", { name: "Finais de torre" });
  fireEvent.change(screen.getByLabelText("Estudo"), { target: { value: "s1" } });
  fireEvent.click(screen.getByText("Começar"));

  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  await resolverEAvancar();
  expect(await screen.findByText(/outro × ele/)).toBeTruthy();
  await resolverEAvancar();

  expect(await screen.findByText("Estudo concluído.")).toBeTruthy();
  expect(fetchMock.mock.calls.filter((c) => String(c[0]) === "/api/reviews").length).toBe(2);
  expect(queueUrls().length).toBe(1);
});

test("capítulo mostrado depois de pular usa a posição original no estudo", async () => {
  bodies["/api/queue"] = { mode: "study", due_count: 0, new_available: 0, new_remaining_today: 0, items: [puzzle, outro] };
  renderPage();
  await screen.findByRole("option", { name: "Finais de torre" });
  fireEvent.change(screen.getByLabelText("Estudo"), { target: { value: "s1" } });
  fireEvent.click(screen.getByText("Começar"));

  expect(await screen.findByText(/eu × ele/)).toBeTruthy();
  expect(screen.getByText(/capítulo 1 de 2/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Pular" }));
  expect(await screen.findByText(/outro × ele/)).toBeTruthy();
  expect(screen.getByText(/capítulo 2 de 2/)).toBeTruthy();
});

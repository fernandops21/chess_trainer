import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { DashboardOut, StatusOut, TacticsStatus, ThemeStat } from "../src/api/types";
import { DashboardPage } from "../src/pages/DashboardPage";

const DASH: DashboardOut = {
  due_today: 3, new_available: 5, new_remaining_today: 2, streak_days: 4, reviews_today: 7,
  last_import_at: null, games_total: 10, games_analyzed: 8, puzzles_total: 20, leeches: 1,
};

const STATUS: StatusOut = {
  engine: { available: true, path: "stockfish" },
  job: { state: "idle", job: null, stage: "", done: 0, total: 0, message: "", error: null, finished_at: null, cancel_requested: false },
  games_total: 10, games_pending: 2, last_import_at: null, local_url: "http://192.168.0.2:8000",
};

const tactics = (over: Partial<TacticsStatus> = {}): TacticsStatus => ({
  imported: true, count: 1000, imported_at: null, source_rows: null, rating: 1350, window: 150,
  attempts_total: 90, attempts_today: 6, attempts_30d: 20, correct_30d: 13, ...over,
});

const stat = (over: Partial<ThemeStat>): ThemeStat => ({
  theme: "fork", label: "garfo", attempts: 10, correct: 8, accuracy: 0.8, own: 0, lichess: 10, ...over,
});

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><DashboardPage /><Where /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "dashboard").mockResolvedValue(DASH);
  vi.spyOn(api, "status").mockResolvedValue(STATUS);
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(tactics());
  vi.spyOn(api, "themeStats").mockResolvedValue([
    stat({}),
    stat({ theme: "pin", label: "cravada", attempts: 4, correct: 1, accuracy: 0.25 }),
    stat({ theme: "skewer", label: "espeto", attempts: 2, correct: 0, accuracy: 0 }),
  ]);
});
afterEach(() => vi.restoreAllMocks());

test("com banco importado mostra o rating, o acerto e o botão de treinar táticas", async () => {
  renderPage();
  expect(await screen.findByText("1350")).toBeTruthy();
  expect(screen.getByText("6")).toBeTruthy();
  expect(screen.getByText("65%")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Treinar táticas" })).toBeTruthy();
});

test("mostra o tema mais fraco com pelo menos 3 tentativas", async () => {
  renderPage();
  expect(await screen.findByText(/Tema mais fraco: cravada \(25%\)/)).toBeTruthy();
  expect(screen.getByText("8/10")).toBeTruthy();
});

test("sem tentativas no período o acerto vira travessão", async () => {
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(tactics({ attempts_30d: 0, correct_30d: 0 }));
  vi.spyOn(api, "themeStats").mockResolvedValue([]);
  renderPage();
  expect(await screen.findByText("—")).toBeTruthy();
  expect(screen.queryByText(/Por tema/)).toBeNull();
});

test("sem banco importado mostra o aviso com link para as configurações", async () => {
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(tactics({ imported: false, count: 0 }));
  renderPage();
  const link = await screen.findByRole("link", { name: /baixar em Configurações/ });
  expect(link.getAttribute("href")).toBe("/config");
  expect(screen.getByText(/Banco de táticas não importado/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Treinar táticas" })).toBeNull();
});

test("com by_source o cartão Estado mostra a contagem por fonte", async () => {
  vi.spyOn(api, "dashboard").mockResolvedValue({
    ...DASH,
    by_source: { own: { in_queue: 12, due: 3 }, lichess: { in_queue: 4, due: 1 }, study: { in_queue: 7, due: 0 } },
  });
  renderPage();
  expect(await screen.findByText("12 dos seus erros · 4 do Lichess · 7 de estudos")).toBeTruthy();
});

test("sem by_source o cartão Estado não mostra a linha por fonte", async () => {
  renderPage();
  expect(await screen.findByText(/8 de 10 partidas analisadas/)).toBeTruthy();
  expect(screen.queryByText(/dos seus erros/)).toBeNull();
});

test("Revisar leva à tela de revisar com a contagem de vencidos", async () => {
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Revisar (3)" }));
  expect(screen.getByTestId("where").textContent).toBe("/revisar");
});

test("Fazer novos leva à sessão de novos", async () => {
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Fazer novos" }));
  expect(screen.getByTestId("where").textContent).toBe("/treinar?mode=new");
});

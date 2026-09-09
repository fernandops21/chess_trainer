import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { ProgressOut, ThemeStat } from "../src/api/types";
import { ProgressPage } from "../src/pages/ProgressPage";

const PROGRESSO: ProgressOut = {
  reviews_per_day: [
    { day: "2026-09-06", correct: 1, wrong: 1 },
    { day: "2026-09-07", correct: 0, wrong: 1 },
    { day: "2026-09-08", correct: 2, wrong: 0 },
  ],
  tactics_rating: [
    { at: "2026-09-06T10:00:00", rating: 1500 },
    { at: "2026-09-07T10:00:00", rating: 1532 },
    { at: "2026-09-08T10:00:00", rating: 1520 },
  ],
  by_source: {
    own: { reviews: 3, correct: 2 },
    lichess: { reviews: 0, correct: 0 },
    study: { reviews: 2, correct: 1 },
  },
  streak_days: 3,
  totals: { reviews: 5, correct: 3, puzzles_in_queue: 12 },
};

const VAZIO: ProgressOut = {
  reviews_per_day: [], tactics_rating: [], by_source: {}, streak_days: 0,
  totals: { reviews: 0, correct: 0, puzzles_in_queue: 0 },
};

const tema = (over: Partial<ThemeStat>): ThemeStat => ({
  theme: "fork", label: "garfo", attempts: 10, correct: 8, accuracy: 0.8, own: 0, lichess: 10, ...over,
});

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><ProgressPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Linha da tabela cuja primeira célula é `nome`, em texto. */
function linha(nome: string): string[] {
  const celula = screen.getAllByRole("cell").find((c) => c.textContent === nome);
  if (!celula) throw new Error(`linha "${nome}" não encontrada`);
  return [...celula.parentElement!.children].map((c) => c.textContent ?? "");
}

beforeEach(() => {
  vi.spyOn(api, "progress").mockResolvedValue(PROGRESSO);
  vi.spyOn(api, "themeStats").mockResolvedValue([tema({}), tema({ theme: "pin", label: "cravada", attempts: 4, correct: 1 })]);
});
afterEach(() => vi.restoreAllMocks());

test("mostra os totais do período e os dois gráficos", async () => {
  renderPage();
  expect(await screen.findByRole("heading", { name: "Progresso" })).toBeTruthy();
  expect(await screen.findByText("dias seguidos")).toBeTruthy();
  // dias seguidos, revisões no período e exercícios na fila
  expect([...document.querySelectorAll(".stat")].map((e) => e.textContent)).toEqual(["3", "5", "12"]);
  expect(screen.getByText("3 certas · 60% de acerto")).toBeTruthy();
  const graficos = screen.getAllByRole("img").map((g) => g.getAttribute("aria-label"));
  expect(graficos).toEqual([
    "Revisões por dia: 3 dia(s), 3 certa(s) e 2 errada(s).",
    "Rating de táticas: 3 ponto(s), de 1500 a 1520, mínimo 1500 e máximo 1532.",
  ]);
});

test("a tabela por fonte traz o acerto em porcentagem, com travessão sem revisões", async () => {
  renderPage();
  expect(await screen.findByText("Por fonte")).toBeTruthy();
  expect(linha("meus erros")).toEqual(["meus erros", "3", "2", "67%"]);
  expect(linha("estudos")).toEqual(["estudos", "2", "1", "50%"]);
  expect(linha("Lichess")).toEqual(["Lichess", "0", "0", "—"]);
  expect(linha("garfo")).toEqual(["garfo", "10", "8", "80%"]);
  expect(linha("cravada")).toEqual(["cravada", "4", "1", "25%"]);
});

test("sem revisões no período mostra o aviso e nenhum gráfico", async () => {
  vi.spyOn(api, "progress").mockResolvedValue(VAZIO);
  vi.spyOn(api, "themeStats").mockResolvedValue([]);
  renderPage();
  expect(await screen.findByText("Ainda não há revisões neste período.")).toBeTruthy();
  expect(screen.queryAllByRole("img")).toEqual([]);
  expect(screen.queryByText("Por tema")).toBeNull();
  // a tabela por fonte continua, zerada
  expect(linha("meus erros")).toEqual(["meus erros", "0", "0", "—"]);
});

test("trocar o período refaz as consultas com os novos dias", async () => {
  renderPage();
  await screen.findByText("Por fonte");
  expect(api.progress).toHaveBeenCalledWith(90);
  expect(api.themeStats).toHaveBeenCalledWith(90);
  const botao = screen.getByRole("button", { name: "365 dias" });
  expect(botao.getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(botao);
  await waitFor(() => expect(api.progress).toHaveBeenCalledWith(365));
  expect(api.themeStats).toHaveBeenCalledWith(365);
  expect(screen.getByRole("button", { name: "365 dias" }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByRole("button", { name: "90 dias" }).getAttribute("aria-pressed")).toBe("false");
});

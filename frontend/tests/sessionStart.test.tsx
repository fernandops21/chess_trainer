import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { TacticsStatus, ThemeCount } from "../src/api/types";
import { SessionStart } from "../src/train/SessionStart";

const THEMES: ThemeCount[] = [
  { theme: "fork", label: "garfo", count: 120 },
  { theme: "pin", label: "cravada", count: 80 },
];

const status = (over: Partial<TacticsStatus> = {}): TacticsStatus => ({
  imported: true, count: 100, imported_at: null, source_rows: null, rating: 1200, window: 200,
  attempts_total: 0, attempts_today: 0, attempts_30d: 0, correct_30d: 0, ...over,
});

function renderStart(entry = "/treinar") {
  const onStart = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <SessionStart onStart={onStart} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onStart;
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(api, "tacticThemes").mockResolvedValue(THEMES);
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(status());
  vi.spyOn(api, "studies").mockResolvedValue([]);
});
afterEach(() => vi.restoreAllMocks());

test("o modo padrão é a repetição espaçada", () => {
  const onStart = renderStart();
  expect((screen.getByLabelText("Repetição espaçada") as HTMLInputElement).checked).toBe(true);
  expect(screen.getByLabelText("Tipo")).toBeTruthy();
  fireEvent.click(screen.getByText("Começar"));
  expect(onStart).toHaveBeenCalledWith(expect.objectContaining({ source: "own", mode: "review", themes: [] }));
  expect(onStart.mock.calls[0][0].filters).toMatchObject({ mode: "review" });
});

test("escolher os novos manda mode=new e esconde as fontes", () => {
  const onStart = renderStart();
  fireEvent.click(screen.getByLabelText("Novos (meus erros)"));
  expect(screen.queryByText("Lichess guardados")).toBeNull();
  // os filtros de tipo/cor/categoria continuam valendo nos novos
  expect(screen.getByLabelText("Tipo")).toBeTruthy();
  fireEvent.click(screen.getByText("Começar"));
  expect(onStart).toHaveBeenCalledWith(expect.objectContaining({ source: "own", mode: "new" }));
  expect(onStart.mock.calls[0][0].filters).toMatchObject({ mode: "new" });
  expect(onStart.mock.calls[0][0].filters.sources).toBe(undefined);
  expect(localStorage.getItem("train.mode")).toBe(JSON.stringify("new"));
});

test("?mode=new já vem selecionado", () => {
  const onStart = renderStart("/treinar?mode=new");
  expect((screen.getByLabelText("Novos (meus erros)") as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByText("Começar"));
  expect(onStart).toHaveBeenCalledWith(expect.objectContaining({ mode: "new" }));
});

test("o modo guardado em train.mode volta selecionado", () => {
  localStorage.setItem("train.mode", JSON.stringify("new"));
  renderStart();
  expect((screen.getByLabelText("Novos (meus erros)") as HTMLInputElement).checked).toBe(true);
});

test("escolher táticas mostra os temas e devolve os selecionados", async () => {
  const onStart = renderStart();
  fireEvent.click(screen.getByLabelText("Táticas do Lichess"));
  const fork = await screen.findByText("garfo");
  expect(screen.queryByLabelText("Tipo")).toBeNull();
  expect(screen.queryByLabelText("Estudo")).toBeNull();
  fireEvent.click(fork);
  expect(fork.getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(screen.getByText("Começar"));
  expect(onStart).toHaveBeenCalledWith(expect.objectContaining({ source: "tactics", themes: ["fork"] }));
  expect(localStorage.getItem("train.themes")).toBe(JSON.stringify(["fork"]));
  expect(localStorage.getItem("train.mode")).toBe(JSON.stringify("tactics"));
});

test("source=tactics na URL já vem selecionado", async () => {
  renderStart("/treinar?source=tactics");
  expect(await screen.findByText("cravada")).toBeTruthy();
});

test("banco não importado avisa e bloqueia o começar", async () => {
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(status({ imported: false, count: 0 }));
  renderStart("/treinar?source=tactics");
  expect(await screen.findByText(/não importado/)).toBeTruthy();
  expect(screen.getByText("baixar em Configurações").getAttribute("href")).toBe("/config");
  expect((screen.getByText("Começar") as HTMLButtonElement).disabled).toBe(true);
});

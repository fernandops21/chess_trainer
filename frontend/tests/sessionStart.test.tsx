import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { DashboardOut, TacticsStatus, ThemeCount } from "../src/api/types";
import { SessionStart } from "../src/train/SessionStart";

const THEMES: ThemeCount[] = [
  { theme: "fork", label: "garfo", count: 120 },
  { theme: "pin", label: "cravada", count: 80 },
];

const DASH: DashboardOut = {
  due_today: 4, new_available: 0, new_remaining_today: 0, streak_days: 0, reviews_today: 0,
  last_import_at: null, games_total: 0, games_analyzed: 0, puzzles_total: 0, leeches: 0,
};

const status = (over: Partial<TacticsStatus> = {}): TacticsStatus => ({
  imported: true, count: 100, imported_at: null, source_rows: null, rating: 1200, window: 200,
  attempts_total: 0, attempts_today: 0, attempts_30d: 0, correct_30d: 0, ...over,
});

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

function renderStart(entry = "/treinar") {
  const onStart = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <SessionStart onStart={onStart} /><Where />
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
  vi.spyOn(api, "dashboard").mockResolvedValue(DASH);
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

test("nos novos, a marca de ignorar o limite vai nos filtros e daí para a URL", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ mode: "new", due_count: 0, new_available: 3, new_remaining_today: 3, items: [] }),
      { status: 200, headers: { "content-type": "application/json" } }),
  );
  const onStart = renderStart();
  fireEvent.click(screen.getByLabelText("Novos (meus erros)"));
  const marca = screen.getByLabelText("ignorar o limite diário hoje") as HTMLInputElement;
  expect(marca.checked).toBe(false);
  expect(screen.getByText(/ou sem limite, se marcado/)).toBeTruthy();

  fireEvent.click(marca);
  fireEvent.click(screen.getByText("Começar"));

  const filtros = onStart.mock.calls[0][0].filters;
  expect(filtros).toMatchObject({ mode: "new", ignore_limit: true });
  await api.queue(filtros);
  expect((fetchSpy.mock.calls[0] as unknown as [string])[0]).toBe("/api/queue?mode=new&ignore_limit=1");
  // a marca não fica guardada: a próxima sessão começa sem ela
  expect(localStorage.getItem("train.ignore_limit")).toBeNull();
});

test("sem marcar, os filtros dos novos não levam ignore_limit", () => {
  const onStart = renderStart();
  fireEvent.click(screen.getByLabelText("Novos (meus erros)"));
  fireEvent.click(screen.getByText("Começar"));
  expect(onStart.mock.calls[0][0].filters.ignore_limit).toBe(undefined);
});

test("a marca de ignorar o limite só aparece nos novos", () => {
  renderStart();
  expect(screen.queryByLabelText("ignorar o limite diário hoje")).toBeNull();
  fireEvent.click(screen.getByLabelText("Novos (meus erros)"));
  const marca = screen.getByLabelText("ignorar o limite diário hoje") as HTMLInputElement;
  fireEvent.click(marca);
  expect(marca.checked).toBe(true);
  fireEvent.click(screen.getByLabelText("Repetição espaçada"));
  expect(screen.queryByLabelText("ignorar o limite diário hoje")).toBeNull();
  // trocar de modo zera a marca: voltar aos novos começa sem ela
  fireEvent.click(screen.getByLabelText("Novos (meus erros)"));
  expect((screen.getByLabelText("ignorar o limite diário hoje") as HTMLInputElement).checked).toBe(false);
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

test("abrir por código leva ao exercício, com ou sem o # na frente", () => {
  renderStart();
  const campo = screen.getByLabelText("Código do exercício");
  // sem nada digitado não há o que abrir
  expect((screen.getByText("Abrir") as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(campo, { target: { value: " #ff466803 " } });
  fireEvent.click(screen.getByText("Abrir"));
  expect(screen.getByTestId("where").textContent).toBe("/treinar?puzzle=ff466803");
});

test("Enter no campo do código abre do mesmo jeito", () => {
  renderStart();
  fireEvent.change(screen.getByLabelText("Código do exercício"), { target: { value: "ff466803" } });
  fireEvent.keyDown(screen.getByLabelText("Código do exercício"), { key: "Enter" });
  expect(screen.getByTestId("where").textContent).toBe("/treinar?puzzle=ff466803");
});

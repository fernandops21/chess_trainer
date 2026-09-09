import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// só o `play` vira dublê: a preferência (isEnabled/setEnabled) continua a de verdade
vi.mock("../src/lib/sound", async (original) => ({
  ...(await original<typeof import("../src/lib/sound")>()),
  play: vi.fn(),
}));

import { play, setEnabled } from "../src/lib/sound";
import { api } from "../src/api/client";
import type { DashboardOut } from "../src/api/types";
import { Nav } from "../src/components/Nav";

const dash = (due_today: number): DashboardOut => ({
  due_today, new_available: 0, new_remaining_today: 0, streak_days: 0, reviews_today: 0,
  last_import_at: null, games_total: 0, games_analyzed: 0, puzzles_total: 0, leeches: 0,
});

function renderNav() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><Nav /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  setEnabled(true);
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  vi.mocked(play).mockClear();
  vi.spyOn(api, "dashboard").mockResolvedValue(dash(0));
});
afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  vi.restoreAllMocks();
});

test("Progresso vem entre o Painel e o Revisar", () => {
  renderNav();
  const rotulos = screen.getAllByRole("link").map((a) => a.textContent);
  expect(rotulos[0]).toContain("Painel");
  expect(rotulos[1]).toContain("Progresso");
  expect(rotulos[2]).toContain("Revisar");
  expect(screen.getByText("Progresso").closest("a")!.getAttribute("href")).toBe("/progresso");
  expect(screen.getByText("Revisar").closest("a")!.getAttribute("href")).toBe("/revisar");
});

test("o badge de vencidos fica em Revisar, explicado, e não em Treinar", async () => {
  vi.spyOn(api, "dashboard").mockResolvedValue(dash(3));
  renderNav();
  const badge = await screen.findByText("3");
  expect(badge.className).toBe("badge");
  expect(badge.getAttribute("title")).toBe("3 vencidos na repetição");
  expect(badge.getAttribute("aria-label")).toBe("3 vencidos na repetição");
  expect(badge.closest("a")!.getAttribute("href")).toBe("/revisar");
  expect(screen.getByText("Treinar").closest("a")!.querySelector(".badge")).toBeNull();
  expect(screen.getByText("Progresso").closest("a")!.querySelector(".badge")).toBeNull();
});

test("um vencido só fala no singular", async () => {
  vi.spyOn(api, "dashboard").mockResolvedValue(dash(1));
  renderNav();
  expect((await screen.findByText("1")).getAttribute("title")).toBe("1 vencido na repetição");
});

test("sem vencidos não há badge nenhum", async () => {
  const { container } = renderNav();
  await screen.findByText("Revisar");
  expect(container.querySelector(".badge")).toBeNull();
});

test("o botão de som começa ligado", () => {
  renderNav();
  const botao = screen.getByRole("button", { name: "Som ligado" });
  expect(botao.getAttribute("aria-pressed")).toBe("true");
  expect(botao.textContent).toContain("🔊");
});

test("clicar desliga o som e guarda a preferência", () => {
  renderNav();
  fireEvent.click(screen.getByRole("button", { name: "Som ligado" }));
  const botao = screen.getByRole("button", { name: "Som desligado" });
  expect(botao.getAttribute("aria-pressed")).toBe("false");
  expect(botao.textContent).toContain("🔇");
  expect(localStorage.getItem("sound.enabled")).toBe("false");
  expect(play).not.toHaveBeenCalled();
});

test("clicar de novo religa o som e toca um lance de retorno", () => {
  renderNav();
  fireEvent.click(screen.getByRole("button", { name: "Som ligado" }));
  fireEvent.click(screen.getByRole("button", { name: "Som desligado" }));
  expect(screen.getByRole("button", { name: "Som ligado" }).getAttribute("aria-pressed")).toBe("true");
  expect(localStorage.getItem("sound.enabled")).toBe("true");
  expect(play).toHaveBeenCalledWith("move");
});

test("os botões vêm depois dos itens de navegação", () => {
  const { container } = renderNav();
  const nav = container.querySelector("nav.nav")!;
  const filhos = Array.from(nav.children);
  const som = screen.getByRole("button", { name: "Som ligado" });
  const tema = screen.getByRole("button", { name: "Tema claro" });
  const links = filhos.filter((el) => el.tagName === "A");
  expect(links.length).toBeGreaterThan(0);
  expect(filhos.indexOf(som)).toBe(filhos.length - 2);
  expect(filhos.indexOf(tema)).toBe(filhos.length - 1);
  expect(filhos.indexOf(som)).toBeGreaterThan(filhos.indexOf(links.at(-1)!));
});

// --------------------------------------------------------------- tema escuro

test("o botão de tema começa no claro (o jsdom não tem prefers-color-scheme)", () => {
  renderNav();
  const botao = screen.getByRole("button", { name: "Tema claro" });
  expect(botao.getAttribute("aria-pressed")).toBe("false");
  expect(botao.textContent).toContain("☀️");
  expect(document.documentElement.getAttribute("data-theme")).toBeNull();
});

test("clicar liga o tema escuro, troca o rótulo e guarda a escolha", () => {
  renderNav();
  fireEvent.click(screen.getByRole("button", { name: "Tema claro" }));
  const botao = screen.getByRole("button", { name: "Tema escuro" });
  expect(botao.getAttribute("aria-pressed")).toBe("true");
  expect(botao.textContent).toContain("🌙");
  expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  expect(localStorage.getItem("tema")).toBe('"escuro"');
});

test("clicar de novo volta ao claro e limpa o atributo", () => {
  renderNav();
  fireEvent.click(screen.getByRole("button", { name: "Tema claro" }));
  fireEvent.click(screen.getByRole("button", { name: "Tema escuro" }));
  expect(screen.getByRole("button", { name: "Tema claro" }).getAttribute("aria-pressed")).toBe("false");
  expect(document.documentElement.getAttribute("data-theme")).toBe("");
  expect(localStorage.getItem("tema")).toBe('"claro"');
});

test("duas telas com o botão de tema ficam em sincronia", () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><Nav /><Nav /></MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getAllByRole("button", { name: "Tema claro" })[0]);
  expect(screen.getAllByRole("button", { name: "Tema escuro" }).length).toBe(2);
});

test("duas telas com o botão ficam em sincronia", () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><Nav /><Nav /></MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getAllByRole("button", { name: "Som ligado" })[0]);
  expect(screen.getAllByRole("button", { name: "Som desligado" }).length).toBe(2);
});

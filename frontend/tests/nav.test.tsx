import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// só o `play` vira dublê: a preferência (isEnabled/setEnabled) continua a de verdade
vi.mock("../src/lib/sound", async (original) => ({
  ...(await original<typeof import("../src/lib/sound")>()),
  play: vi.fn(),
}));

import { play, setEnabled } from "../src/lib/sound";
import { Nav } from "../src/components/Nav";

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
  vi.mocked(play).mockClear();
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

test("o botão vem depois dos itens de navegação", () => {
  const { container } = renderNav();
  const nav = container.querySelector("nav.nav")!;
  const filhos = Array.from(nav.children);
  const botao = screen.getByRole("button", { name: "Som ligado" });
  const links = filhos.filter((el) => el.tagName === "A");
  expect(links.length).toBeGreaterThan(0);
  expect(filhos.indexOf(botao)).toBe(filhos.length - 1);
  expect(filhos.indexOf(botao)).toBeGreaterThan(filhos.indexOf(links.at(-1)!));
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

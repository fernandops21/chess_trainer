import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { MistakeOut, PuzzleRef } from "../src/api/types";
import { MistakesPage } from "../src/pages/MistakesPage";

const erro = (puzzles: PuzzleRef[]): MistakeOut => ({
  position_id: "p1",
  game_id: "g1",
  ply: 12,
  fen: "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",
  move_played: "Ra2",
  move_uci: "a1a2",
  best_move: "a1a8",
  eval_before: 300,
  eval_after: -100,
  mistake_level: "blunder",
  mistake_by: "me",
  category: "rapid",
  played_at: "2026-09-01T10:00:00",
  white: "eu",
  black: "outro",
  my_color: "white",
  puzzles,
});

const puzzle = (over: Partial<PuzzleRef> = {}): PuzzleRef => ({
  id: "z1", kind: "punish", theme: "fork", is_leech: false, in_queue: true, ...over,
});

function renderPage(entry = "/erros") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <MistakesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "leeches").mockResolvedValue([]);
});
afterEach(() => vi.restoreAllMocks());

test("basta um exercício fora da repetição para o erro ganhar a etiqueta", async () => {
  vi.spyOn(api, "mistakes").mockResolvedValue([
    erro([puzzle({ id: "z1", kind: "punish", in_queue: true }),
          puzzle({ id: "z2", kind: "avoid", in_queue: false })]),
  ]);
  renderPage();
  // com dois exercícios a etiqueta diz qual deles saiu
  expect(await screen.findByText("fora da repetição (evitar)")).toBeTruthy();
  expect(screen.queryByText("fora da repetição (punir)")).toBeNull();
});

test("com um exercício só, a etiqueta não precisa nomear o tipo", async () => {
  vi.spyOn(api, "mistakes").mockResolvedValue([erro([puzzle({ in_queue: false })])]);
  renderPage();
  expect(await screen.findByText("fora da repetição")).toBeTruthy();
});

test("com tudo na repetição não há etiqueta", async () => {
  vi.spyOn(api, "mistakes").mockResolvedValue([erro([puzzle()])]);
  renderPage();
  await screen.findByText("Ra2");
  expect(screen.queryByText(/fora da repetição/)).toBeNull();
});

// --- ?position=<fen> abre o erro daquela posição -------------------------

/** A mesma posição do erro, com outro contador de lances: os 4 primeiros campos é que valem. */
const OUTRO_CONTADOR = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 7 21";

test("?position=<fen> abre o modal do erro daquela posição", async () => {
  vi.spyOn(api, "mistakes").mockResolvedValue([erro([])]);
  renderPage(`/erros?position=${encodeURIComponent(OUTRO_CONTADOR)}`);
  // o título do modal traz o lance do erro
  expect(await screen.findByText("Lance 6: Ra2")).toBeTruthy();
  // fechar não reabre
  fireEvent.click(screen.getByText("Fechar"));
  await waitFor(() => expect(screen.queryByText("Lance 6: Ra2")).toBeNull());
});

test("?position= de uma posição fora da lista não abre nada", async () => {
  vi.spyOn(api, "mistakes").mockResolvedValue([erro([])]);
  renderPage("/erros?position=8%2F8%2F8%2F8%2F8%2F8%2F8%2F4K2k%20w%20-%20-%200%201");
  await screen.findByText("Ra2");
  expect(screen.queryByText("Lance 6: Ra2")).toBeNull();
});

test("sem ?position= nenhum modal abre sozinho", async () => {
  vi.spyOn(api, "mistakes").mockResolvedValue([erro([])]);
  renderPage();
  await screen.findByText("Ra2");
  expect(screen.queryByText("Lance 6: Ra2")).toBeNull();
});

test("o melhor lance sai em notação, não em UCI", async () => {
  renderPage();
  await waitFor(() => expect(document.body.textContent).toContain("melhor Ra8#"));
  expect(document.body.textContent).not.toContain("a1a8");
});

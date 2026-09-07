import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api, ApiError } from "../src/api/client";
import type { OpeningsOut } from "../src/api/types";
import { OpeningsPanel } from "../src/analysis/OpeningsPanel";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const RESP: OpeningsOut = {
  opening: { eco: "C50", name: "Abertura Italiana" },
  total: 11000,
  white: 4500,
  draws: 3250,
  black: 3250,
  moves: [
    { uci: "e2e4", san: "e4", games: 10000, white: 4000, draws: 3000, black: 3000, avg_rating: 2456 },
    { uci: "d2d4", san: "d4", games: 1000, white: 500, draws: 250, black: 250, avg_rating: null },
  ],
};

const vazio: OpeningsOut = { opening: null, total: 0, white: 0, draws: 0, black: 0, moves: [] };

function montar(fen = START) {
  const onPlay = vi.fn();
  const r = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <OpeningsPanel fen={fen} onPlay={onPlay} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...r, onPlay };
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(api, "openings").mockResolvedValue(RESP);
});
afterEach(() => vi.restoreAllMocks());

test("lista os lances com partidas, barra de resultado e rating médio", async () => {
  const { container } = montar();
  expect(await screen.findByRole("button", { name: "e4" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "d4" })).toBeTruthy();
  expect(container.textContent).toMatch(/10\.000/);
  expect(container.textContent).toMatch(/1\.000/);
  // rating médio só quando a base devolve
  expect(container.textContent).toMatch(/2\.456/);
  // barra: três faixas com o resumo acessível
  expect(screen.getByLabelText("brancas 40%, empates 30%, pretas 30%")).toBeTruthy();
  expect(screen.getByLabelText("brancas 50%, empates 25%, pretas 25%")).toBeTruthy();
  // nome da abertura e total da posição
  expect(screen.getByText("C50 · Abertura Italiana")).toBeTruthy();
  expect(container.textContent).toMatch(/11\.000 partidas/);
});

test("clicar num lance joga ele no tabuleiro", async () => {
  const { onPlay } = montar();
  fireEvent.click(await screen.findByRole("button", { name: "e4" }));
  expect(onPlay).toHaveBeenCalledWith("e2e4");
});

test("sem lances mostra o aviso de posição sem partidas", async () => {
  vi.spyOn(api, "openings").mockResolvedValue(vazio);
  montar();
  expect(await screen.findByText("Sem partidas nesta posição.")).toBeTruthy();
});

test("sem token mostra a orientação com link para Configurações", async () => {
  vi.spyOn(api, "openings").mockRejectedValue(
    new ApiError(400, "configure o token do Lichess em Configurações"),
  );
  montar();
  expect(await screen.findByText(/configure o token do Lichess/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Configurações" }).getAttribute("href")).toBe("/config");
});

test("token recusado também leva para Configurações", async () => {
  vi.spyOn(api, "openings").mockRejectedValue(
    new ApiError(400, "token do Lichess recusado; gere outro em Configurações"),
  );
  montar();
  expect(await screen.findByText(/token do Lichess recusado/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Configurações" }).getAttribute("href")).toBe("/config");
});

test("limite do Lichess mostra a mensagem do servidor sem link", async () => {
  vi.spyOn(api, "openings").mockRejectedValue(new ApiError(503, "limite do Lichess; tente em instantes"));
  montar();
  expect(await screen.findByText("limite do Lichess; tente em instantes")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Configurações" })).toBeNull();
});

test("a base começa em mestres, troca para jogadores e fica guardada", async () => {
  montar();
  await waitFor(() => expect(api.openings).toHaveBeenCalledWith(START, "masters"));
  const base = screen.getByLabelText("Base de partidas") as HTMLSelectElement;
  expect(base.value).toBe("masters");
  fireEvent.change(base, { target: { value: "lichess" } });
  await waitFor(() => expect(api.openings).toHaveBeenCalledWith(START, "lichess"));
  expect(localStorage.getItem("analysis.openingsDb")).toBe('"lichess"');
});

test("a base guardada volta na próxima montagem", async () => {
  localStorage.setItem("analysis.openingsDb", '"lichess"');
  montar();
  await waitFor(() => expect(api.openings).toHaveBeenCalledWith(START, "lichess"));
  expect((screen.getByLabelText("Base de partidas") as HTMLSelectElement).value).toBe("lichess");
});

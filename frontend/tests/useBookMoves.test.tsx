import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api, ApiError } from "../src/api/client";
import type { OpeningsOut } from "../src/api/types";
import { fenAt, pathTo } from "../src/analysis/moveTree";
import type { Tree, TreeNode } from "../src/analysis/moveTree";
import { useBookMoves } from "../src/analysis/useBookMoves";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const node = (id: string, uci: string, san: string, filhos: TreeNode[] = []): TreeNode => ({
  id, uci, san, comment: "", shapes: [], nags: [], children: filhos,
});

/** 1. e4 e5 2. Nf3 Nc6 */
const tree: Tree = {
  fen: START,
  orientation: "white",
  intro: "",
  root: {
    children: [
      node("n1", "e2e4", "e4", [
        node("n2", "e7e5", "e5", [
          node("n3", "g1f3", "Nf3", [node("n4", "b8c6", "Nc6")]),
        ]),
      ]),
    ],
  },
};

/** Posições que são o pai de cada lance do caminho. */
const FEN0 = tree.fen;
const FEN1 = fenAt(tree, "n1");
const FEN2 = fenAt(tree, "n2");
const FEN3 = fenAt(tree, "n3");

const VAZIO: OpeningsOut = { opening: null, total: 0, white: 0, draws: 0, black: 0, moves: [] };

function livro(...ucis: string[]): OpeningsOut {
  return {
    opening: null,
    total: 1000,
    white: 400,
    draws: 300,
    black: 300,
    moves: ucis.map((uci) => ({ uci, san: uci, games: 100, white: 40, draws: 30, black: 30, avg_rating: 2400 })),
  };
}

function porFen(mapa: Record<string, OpeningsOut>) {
  vi.spyOn(api, "openings").mockImplementation(async (fen: string) => mapa[fen] ?? VAZIO);
}

function montar(id: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useBookMoves(tree, pathTo(tree, id)), { wrapper });
}

beforeEach(() => vi.restoreAllMocks());
afterEach(() => vi.restoreAllMocks());

test("marca os lances do caminho que estão no livro de mestres", async () => {
  porFen({ [FEN0]: livro("e2e4", "d2d4"), [FEN1]: livro("e7e5", "c7c5"), [FEN2]: VAZIO });
  const { result } = montar("n3");
  await waitFor(() => expect(result.current.size).toBe(2));
  expect([...result.current].sort()).toEqual(["n1", "n2"]);
  // a posição depois de 1. e4 e5 não tem partidas: Nf3 não é lance de livro
  await waitFor(() => expect(api.openings).toHaveBeenCalledTimes(3));
});

test("um lance fora do livro não impede os seguintes (transposição)", async () => {
  porFen({ [FEN0]: livro("d2d4"), [FEN1]: livro("e7e5"), [FEN2]: livro("g1f3") });
  const { result } = montar("n3");
  await waitFor(() => expect(result.current.size).toBe(2));
  expect([...result.current].sort()).toEqual(["n2", "n3"]);
});

test("para de consultar depois da primeira posição sem partidas", async () => {
  porFen({ [FEN0]: livro("e2e4"), [FEN1]: VAZIO, [FEN2]: livro("g1f3"), [FEN3]: livro("b8c6") });
  const { result } = montar("n4");
  await waitFor(() => expect(result.current.size).toBe(1));
  expect([...result.current]).toEqual(["n1"]);
  await waitFor(() => expect(api.openings).toHaveBeenCalledTimes(2));
  // as posições seguintes nunca são consultadas
  expect(api.openings).not.toHaveBeenCalledWith(FEN2, "masters");
  expect(api.openings).not.toHaveBeenCalledWith(FEN3, "masters");
});

test("sem token o conjunto fica vazio, sem consultar o resto do caminho", async () => {
  vi.spyOn(api, "openings").mockRejectedValue(
    new ApiError(400, "configure o token do Lichess em Configurações"),
  );
  const { result } = montar("n3");
  await waitFor(() => expect(api.openings).toHaveBeenCalledTimes(1));
  expect(result.current.size).toBe(0);
  await waitFor(() => expect(api.openings).toHaveBeenCalledTimes(1));
});

test("caminho vazio (posição inicial) não consulta nada", () => {
  porFen({ [FEN0]: livro("e2e4") });
  const { result } = montar("");
  expect(result.current.size).toBe(0);
  expect(api.openings).not.toHaveBeenCalled();
});

/** Diagrama do estudo do Basso ("Ataque duplo - Cavalo"): sem rei branco. */
const SEM_REIS: Tree = {
  fen: "r1r5/8/1N6/8/8/8/5N2/3k3q w - - 0 1",
  orientation: "white",
  intro: "",
  root: { children: [node("d1", "b6c8", "Nxc8+")] },
};

test("diagrama sem os dois reis não consulta o livro", () => {
  // posição que não vem de partida nenhuma: o livro de mestres não teria o que dizer
  porFen({});
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useBookMoves(SEM_REIS, pathTo(SEM_REIS, "d1")), { wrapper });
  expect(result.current.size).toBe(0);
  expect(api.openings).not.toHaveBeenCalled();
});

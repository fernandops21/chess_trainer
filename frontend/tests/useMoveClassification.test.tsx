import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { AnalyseOut, Color } from "../src/api/types";
import { fenAt, pathTo } from "../src/analysis/moveTree";
import type { Tree, TreeNode } from "../src/analysis/moveTree";
import { useMoveClassification } from "../src/analysis/useMoveClassification";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const LIMIARES = { mistake: 100, blunder: 200 };

const node = (id: string, uci: string, san: string, filhos: TreeNode[] = []): TreeNode => ({
  id, uci, san, comment: "", shapes: [], nags: [], children: filhos,
});

/** 1. e4 e5 2. Nf3 */
const tree: Tree = {
  fen: START,
  orientation: "white",
  intro: "",
  root: {
    children: [node("n1", "e2e4", "e4", [node("n2", "e7e5", "e5", [node("n3", "g1f3", "Nf3")])])],
  },
};

const FEN0 = tree.fen;
const FEN1 = fenAt(tree, "n1");
const FEN2 = fenAt(tree, "n2");
const FEN3 = fenAt(tree, "n3");

function analise(fen: string, turn: Color, move: string, score: number): AnalyseOut {
  return {
    fen,
    turn,
    terminal: null,
    lines: [{ move, san: move, score, pv: [move], pv_san: [] }],
  };
}

/**
 * e4 é o melhor lance; e5 perde 15 cp (excelente); Nf3 perde 70 cp
 * (imprecisão, com o limiar em 100).
 */
const RESPOSTAS: Record<string, AnalyseOut> = {
  [FEN0]: analise(FEN0, "white", "e2e4", 30),
  [FEN1]: analise(FEN1, "black", "c7c5", 20),
  [FEN2]: analise(FEN2, "white", "d2d4", -5),
  [FEN3]: analise(FEN3, "black", "b8c6", 75),
};

function mockar() {
  return vi.spyOn(api, "analyse").mockImplementation(async (fen: string) => {
    const out = RESPOSTAS[fen];
    if (!out) throw new Error(`FEN inesperado: ${fen}`);
    return out;
  });
}

function montar(id: string, enabled: boolean, bookIds: Set<string> = new Set()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(
    () => useMoveClassification(tree, pathTo(tree, id), { enabled, thresholds: LIMIARES, bookIds }),
    { wrapper },
  );
}

beforeEach(() => vi.restoreAllMocks());
afterEach(() => vi.restoreAllMocks());

test("classifica os lances do caminho com uma análise por posição", async () => {
  mockar();
  const { result } = montar("n3", true);
  await waitFor(() => expect(result.current.size).toBe(3));
  expect(result.current.get("n1")?.kind).toBe("melhor");
  expect(result.current.get("n2")?.kind).toBe("excelente");
  expect(result.current.get("n3")?.kind).toBe("imprecisao");
  expect(result.current.get("n3")?.loss).toBe(70);
  // as três posições do caminho mais a inicial
  expect(api.analyse).toHaveBeenCalledTimes(4);
  expect(api.analyse).toHaveBeenCalledWith(FEN0);
  expect(api.analyse).toHaveBeenCalledWith(FEN3);
});

test("desligado nas configurações não consulta a engine", async () => {
  mockar();
  const { result } = montar("n3", false);
  await waitFor(() => expect(api.analyse).not.toHaveBeenCalled());
  expect(result.current.size).toBe(0);
});

test("caminho vazio não consulta nada", () => {
  mockar();
  const { result } = montar("", true);
  expect(result.current.size).toBe(0);
  expect(api.analyse).not.toHaveBeenCalled();
});

test("lance de livro vira selo de livro sem depender da engine", async () => {
  mockar();
  const { result } = montar("n3", true, new Set(["n1", "n2"]));
  await waitFor(() => expect(result.current.size).toBe(3));
  expect(result.current.get("n1")?.kind).toBe("livro");
  expect(result.current.get("n2")?.kind).toBe("livro");
  expect(result.current.get("n3")?.kind).toBe("imprecisao");
});

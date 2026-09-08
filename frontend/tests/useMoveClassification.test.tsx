import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { AnalyseOut, Color } from "../src/api/types";
import { fenAt, mainline, pathTo } from "../src/analysis/moveTree";
import type { Tree, TreeNode } from "../src/analysis/moveTree";
import { MAX_EM_VOO, MAX_LANCES, janelaEmVoo, useMoveClassification } from "../src/analysis/useMoveClassification";

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

/** Mesmos ids da árvore acima, outros lances: 1. d4 d5 2. c4 */
const OUTRA: Tree = {
  fen: START,
  orientation: "white",
  intro: "",
  root: {
    children: [node("n1", "d2d4", "d4", [node("n2", "d7d5", "d5", [node("n3", "c2c4", "c4")])])],
  },
};

const OFEN1 = fenAt(OUTRA, "n1");
const OFEN2 = fenAt(OUTRA, "n2");
const OFEN3 = fenAt(OUTRA, "n3");

/** d4 não é o melhor lance e perde 50 cp (bom), ao contrário do e4 da outra árvore. */
Object.assign(RESPOSTAS, {
  [OFEN1]: analise(OFEN1, "black", "g8f6", 20),
  [OFEN2]: analise(OFEN2, "white", "c2c4", -5),
  [OFEN3]: analise(OFEN3, "black", "e7e6", 75),
});

const NENHUM: Set<string> = new Set();

/** FENs da linha principal, da posição inicial até o último lance. */
function fensDe(t: Tree): string[] {
  return [t.fen, ...mainline(t).map((n) => fenAt(t, n.id))];
}

/** Árvore de uma linha só, com ids `n1`, `n2`, ... na ordem dos lances. */
function arvoreLinear(ucis: string[]): Tree {
  let filhos: TreeNode[] = [];
  for (let i = ucis.length - 1; i >= 0; i--) filhos = [node(`n${i + 1}`, ucis[i], ucis[i], filhos)];
  return { fen: START, orientation: "white", intro: "", root: { children: filhos } };
}

/** Monta o hook com a árvore dada; `semear` põe as análises no cache antes. */
function montarArvore(arvore: Tree, id: string, semear: Tree[] = []) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const t of semear) {
    for (const fen of fensDe(t)) client.setQueryData(["analyse", fen], RESPOSTAS[fen]);
  }
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(
    ({ t }: { t: Tree }) =>
      useMoveClassification(t, pathTo(t, id), { enabled: true, thresholds: LIMIARES, bookIds: NENHUM }),
    { wrapper, initialProps: { t: arvore } },
  );
}

test("árvore diferente com os mesmos ids recalcula o mapa", async () => {
  mockar();
  const { result, rerender } = montarArvore(tree, "n3", [tree, OUTRA]);
  await waitFor(() => expect(result.current.get("n1")?.kind).toBe("melhor"));
  rerender({ t: OUTRA });
  expect(result.current.get("n1")?.kind).toBe("bom");
  expect(result.current.get("n3")?.kind).toBe("melhor");
});

// 1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7
const RUY = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7"];

test("poucas posições sem resposta em voo, começando pela atual", async () => {
  const espia = vi.spyOn(api, "analyse").mockImplementation(() => new Promise<AnalyseOut>(() => {}));
  const arvore = arvoreLinear(RUY);
  const fens = fensDe(arvore);
  const { result } = montarArvore(arvore, `n${RUY.length}`);
  await waitFor(() => expect(espia).toHaveBeenCalledTimes(MAX_EM_VOO));
  // as últimas posições do caminho, da atual para trás
  expect(espia.mock.calls.map((c) => c[0])).toEqual(fens.slice(-MAX_EM_VOO).reverse());
  expect(result.current.size).toBe(0);
});

// Nf3 Nf6 Ng1 Ng8 repetidos: 70 meios-lances legais, todos com FEN diferente.
const CAVALOS = Array.from({ length: 70 }, (_, i) => ["g1f3", "g8f6", "f3g1", "f6g8"][i % 4]);

test("classifica os 60 últimos meios-lances do caminho", async () => {
  const espia = vi.spyOn(api, "analyse").mockImplementation(async (fen: string) =>
    analise(fen, fen.split(" ")[1] === "w" ? "white" : "black", "a2a3", 0),
  );
  const arvore = arvoreLinear(CAVALOS);
  const { result } = montarArvore(arvore, `n${CAVALOS.length}`);
  await waitFor(() => expect(result.current.size).toBe(MAX_LANCES), { timeout: 20000 });
  // o teto corta a cabeça do caminho: o lance na tela é sempre classificado
  expect(result.current.get(`n${CAVALOS.length}`)).toBeDefined();
  expect(result.current.get(`n${CAVALOS.length - MAX_LANCES + 1}`)).toBeDefined();
  expect(result.current.get(`n${CAVALOS.length - MAX_LANCES}`)).toBeUndefined();
  expect(result.current.get("n1")).toBeUndefined();
  // uma consulta por posição: os 60 lances mais a de onde o primeiro deles parte
  expect(espia).toHaveBeenCalledTimes(MAX_LANCES + 1);
}, 30000);

test("consulta que dá erro libera a vaga para a próxima posição do caminho", async () => {
  const arvore = arvoreLinear(RUY);
  const fens = fensDe(arvore);
  const ultima = fens[fens.length - 1];
  // a posição na tela falha (engine fora do ar); as outras ficam sem resposta
  const espia = vi.spyOn(api, "analyse").mockImplementation((fen: string) =>
    fen === ultima ? Promise.reject(new Error("engine indisponível")) : new Promise<AnalyseOut>(() => {}),
  );
  montarArvore(arvore, `n${RUY.length}`);
  await waitFor(() => expect(espia).toHaveBeenCalledTimes(MAX_EM_VOO + 1));
  // a vaga do erro não fica presa: a próxima posição do caminho é consultada
  expect(espia.mock.calls.map((c) => c[0])).toEqual([
    ...fens.slice(-MAX_EM_VOO).reverse(),
    fens[fens.length - 1 - MAX_EM_VOO],
  ]);
});

// --- janela das consultas em voo ----------------------------------------

test("FENs repetidas no caminho contam uma vaga só", () => {
  // a mesma posição em dois pontos do caminho é uma consulta só no React Query
  const fens = ["A", "B", "A"];
  const ordem = [2, 1, 0];
  expect([...janelaEmVoo(fens, ordem, () => false)]).toEqual([2, 1, 0]);
  expect(MAX_EM_VOO).toBe(2);
});

test("a janela para em MAX_EM_VOO posições diferentes e pula as já resolvidas", () => {
  const fens = ["A", "B", "C", "D"];
  const ordem = [3, 2, 1, 0];
  expect([...janelaEmVoo(fens, ordem, () => false)]).toEqual([3, 2]);
  // "D" já tem resposta (ou erro): não ocupa vaga
  expect([...janelaEmVoo(fens, ordem, (f) => f === "D")]).toEqual([2, 1]);
});

test("estado parcial: só entram os lances cujas análises já chegaram", async () => {
  vi.spyOn(api, "analyse").mockImplementation((fen: string) =>
    fen === FEN2 || fen === FEN3 ? Promise.resolve(RESPOSTAS[fen]) : new Promise<AnalyseOut>(() => {}),
  );
  const { result } = montar("n3", true);
  await waitFor(() => expect(result.current.size).toBe(1));
  // as consultas saem da posição atual para trás: o lance na tela é o primeiro
  expect(result.current.get("n3")?.kind).toBe("imprecisao");
  expect(result.current.get("n2")).toBeUndefined();
  expect(result.current.get("n1")).toBeUndefined();
});

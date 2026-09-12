import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { CoachExplanation, CoachStatus, PuzzleOut } from "../src/api/types";
import { api } from "../src/api/client";
import { ApiError } from "../src/api/client";
import { CoachCard } from "../src/train/CoachCard";
import { PreviaContext } from "../src/analysis/previaContext";

const FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4";
const puzzle: PuzzleOut = {
  id: "p1", kind: "punish", fen_start: FEN, side_to_move: "white",
  solution: { moves: [{ uci: "h5f7", by: "solver", alternatives: [] }], explanation_pv: [] },
  end_reason: "mate", theme: "mate_in_1", category: "rapid", solver_moves: 1, is_leech: false,
  srs: { ease: 2.5, interval_days: 0, lapses: 0, due_at: null, last_reviewed_at: null },
  source: "own", in_queue: true, fen_before: null, last_move: null, game: null, ply: null, move_played: null, mistake: null, study: null, siblings: [],
};
const status = (over: Partial<CoachStatus> = {}): CoachStatus => ({
  configured: true, model: "claude-opus-5", effort: "high", embeddings_ready: true, index_chunks: 3, index_model: "m",
  index_stale: 0, vector_backend: "sqlite-vec", langfuse_configured: false, ...over,
});
const explicacao = (over: Partial<CoachExplanation> = {}): CoachExplanation => ({
  id: "e1", puzzle_id: "p1", created_at: "2026-09-11T10:00:00", model: "claude-opus-5", prompt_version: "v1",
  text: "A dama e o bispo miram f7: Qxf7# encerra. [c:ab12] Treine mates rápidos.",
  lines: [], citations: [{ chunk_id: "ab12", study_id: "s1", estudo: "Táticas", chapter_id: "c1", capitulo: "Mates", node_id: "n1", caminho_san: "1.e4", texto: "t", url: "/estudos/s1/capitulos/c1?lance=n1" }],
  verification: { ok: true, issues: [] }, status: "ok", repaired: false, cost_usd: 0.0421,
  tokens: { input: 5000, output: 400, cache_read: 3000, cache_write: 0 }, duration_ms: 12000, trace_url: "http://localhost:3000/trace/x", ...over,
});

function renderCard(previa = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter>
        <PreviaContext.Provider value={previa}><CoachCard puzzle={puzzle} reviewId="r1" /></PreviaContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return previa;
}

beforeEach(() => {
  vi.spyOn(api, "coachStatus").mockResolvedValue(status());
  vi.spyOn(api, "coachExplanation").mockResolvedValue(null);
  vi.spyOn(api, "coachExplain").mockResolvedValue(explicacao());
});
afterEach(() => vi.restoreAllMocks());

test("sem treinador configurado o cartão não aparece", async () => {
  vi.spyOn(api, "coachStatus").mockResolvedValue(status({ configured: false }));
  renderCard();
  await waitFor(() => expect(api.coachStatus).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: "Explicar" })).toBeNull();
});

test("o botão não aparece enquanto a explicação guardada não chega", async () => {
  // sem isso um clique durante a carga pediria uma explicação nova (e paga) para
  // um exercício que talvez já tenha uma guardada
  let responder = (_: CoachExplanation | null) => {};
  vi.spyOn(api, "coachExplanation").mockReturnValue(new Promise<CoachExplanation | null>((r) => { responder = r; }));
  renderCard();
  expect(await screen.findByText("Treinador")).toBeTruthy();  // o cartão está lá
  expect(screen.queryByRole("button", { name: "Explicar" })).toBeNull();
  expect(api.coachExplain).not.toHaveBeenCalled();
  responder(null);
  const botao = (await screen.findByRole("button", { name: "Explicar" })) as HTMLButtonElement;
  expect(botao.disabled).toBe(false);
});

test("Explicar chama a API com o exercício e mostra o texto com lance clicável, citação e selo", async () => {
  // a resposta só chega quando o teste manda: é o que deixa ver o aviso da espera
  let responder = (_: CoachExplanation) => {};
  vi.spyOn(api, "coachExplain").mockReturnValue(new Promise<CoachExplanation>((r) => { responder = r; }));
  const previa = renderCard();
  fireEvent.click(await screen.findByRole("button", { name: "Explicar" }));
  expect(await screen.findByText(/leva de 10 a 40 s/)).toBeTruthy();
  await waitFor(() => expect(api.coachExplain).toHaveBeenCalledWith({ puzzle_id: "p1", review_id: "r1" }));
  responder(explicacao());
  expect(await screen.findByText(/A dama e o bispo miram f7/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Qxf7#" }));
  expect(previa).toHaveBeenCalled();
  const link = screen.getByRole("link", { name: /Táticas › Mates/ });
  expect(link.getAttribute("href")).toBe("/estudos/s1/capitulos/c1?lance=n1");
  expect(screen.queryByText("[c:ab12]")).toBeNull();
  expect(screen.getByText("verificado pela engine")).toBeTruthy();
  expect(screen.getByText(/claude-opus-5 · US\$ 0,04 · 12 s/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "trace" }).getAttribute("href")).toBe("http://localhost:3000/trace/x");
  expect(screen.getByRole("button", { name: "Explicar de novo" })).toBeTruthy();
});

test("explicação já existente abre direto", async () => {
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao({ status: "warnings", verification: { ok: true, issues: [{ tipo: "lance_fora_das_principais", gravidade: "aviso", detalhe: "'a3' não está entre as três melhores", linha_idx: 0 }] } }));
  renderCard();
  expect(await screen.findByText(/A dama e o bispo/)).toBeTruthy();
  expect(screen.getByText("com ressalvas")).toBeTruthy();
  expect(screen.getByText(/'a3' não está entre as três melhores/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Explicar de novo" })).toBeTruthy();
});

test("erro da API aparece e o botão volta", async () => {
  vi.spyOn(api, "coachExplain").mockRejectedValue(new ApiError(502, "limite de uso da API atingido"));
  renderCard();
  fireEvent.click(await screen.findByRole("button", { name: "Explicar" }));
  expect(await screen.findByText(/limite de uso da API atingido/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Explicar" })).toBeTruthy();
});

test("status errors mostra 'não verificado' com os erros", async () => {
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao({ status: "errors", verification: { ok: false, issues: [{ tipo: "lance_ilegal", gravidade: "erro", detalhe: "'Qxf8' não é legal", linha_idx: 0 }] } }));
  renderCard();
  expect(await screen.findByText("não verificado")).toBeTruthy();
  expect(screen.getByText(/'Qxf8' não é legal/)).toBeTruthy();
});

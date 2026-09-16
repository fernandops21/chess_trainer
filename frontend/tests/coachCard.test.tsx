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
  enabled: true, configured: true, model: "claude-opus-5", effort: "high", embeddings_ready: true, index_chunks: 3, index_model: "m",
  index_stale: 0, vector_backend: "sqlite-vec", langfuse_configured: false, ...over,
});
const NA_PARTIDA = "Na partida a dama e o bispo já miravam a casa mais fraca.";
const POR_QUE = "A dama e o bispo miram f7: Qxf7# encerra. [c:ab12] Treine mates rápidos.";
const explicacao = (over: Partial<CoachExplanation> = {}): CoachExplanation => ({
  id: "e1", puzzle_id: "p1", created_at: "2026-09-11T10:00:00", model: "claude-opus-5", prompt_version: "v3",
  text: `${NA_PARTIDA}\n\n${POR_QUE}`,
  na_partida: NA_PARTIDA, por_que: POR_QUE, padrao: "mate do pastor",
  treinar: ["mates com dama e bispo", "conferir a casa f7 antes de mover"],
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
  expect(await screen.findByText(/costuma levar cerca de um minuto/)).toBeTruthy();
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

test("explicação já existente abre direto; os avisos ficam no banco, o selo é um só", async () => {
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao({ status: "warnings", verification: { ok: true, issues: [{ tipo: "lance_fora_das_principais", gravidade: "aviso", detalhe: "'a3' não está entre as três melhores", linha_idx: 0 }] } }));
  renderCard();
  expect(await screen.findByText(/A dama e o bispo/)).toBeTruthy();
  // sem contagem, sem lista: o vocabulário do verificador não entra no produto
  expect(screen.getByText("verificado pela engine").textContent).toBe("verificado pela engine");
  expect(screen.queryByText(/ressalvas/)).toBeNull();
  expect(screen.queryByText(/'a3' não está entre as três melhores/)).toBeNull();
  expect(document.querySelector("details")).toBeNull();
  expect(screen.getByRole("button", { name: "Explicar de novo" })).toBeTruthy();
});

test("erro da API aparece e o botão volta", async () => {
  vi.spyOn(api, "coachExplain").mockRejectedValue(new ApiError(502, "limite de uso da API atingido"));
  renderCard();
  fireEvent.click(await screen.findByRole("button", { name: "Explicar" }));
  expect(await screen.findByText(/limite de uso da API atingido/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Explicar" })).toBeTruthy();
});

test("status errors: nenhuma explicação, só a frase e o 'Explicar de novo'", async () => {
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao({ status: "errors", verification: { ok: false, issues: [{ tipo: "lance_ilegal", gravidade: "erro", detalhe: "'Qxf8' não é legal", linha_idx: 0 }] } }));
  renderCard();
  expect(await screen.findByText("Não consegui uma explicação que passe na verificação da engine para este exercício.")).toBeTruthy();
  // nada da prosa, dos blocos nem do verificador chega ao aluno
  expect(screen.queryByText(/A dama e o bispo/)).toBeNull();
  expect(screen.queryByText(NA_PARTIDA)).toBeNull();
  expect(screen.queryByText("Na partida")).toBeNull();
  expect(screen.queryByText("Por que")).toBeNull();
  expect(screen.queryByText("Padrão")).toBeNull();
  expect(screen.queryByText("mate do pastor")).toBeNull();
  expect(screen.queryByText("Treinar")).toBeNull();
  expect(screen.queryByText(/'Qxf8' não é legal/)).toBeNull();
  expect(screen.queryByText(/verificado/)).toBeNull();
  expect(screen.getByRole("button", { name: "Explicar de novo" })).toBeTruthy();
  // o rodapé com modelo, custo e tempo fica
  expect(screen.getByText(/claude-opus-5 · US\$ 0,04 · 12 s/)).toBeTruthy();
});

// --- leitura em blocos --------------------------------------------------

test("a explicação sai em blocos com rótulo, padrão e o que treinar", async () => {
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao());
  renderCard();
  expect(await screen.findByText("Na partida")).toBeTruthy();
  expect(screen.getByText(NA_PARTIDA)).toBeTruthy();
  expect(screen.getByText("Por que")).toBeTruthy();
  expect(screen.getByText("Padrão")).toBeTruthy();
  expect(screen.getByText("mate do pastor")).toBeTruthy();
  expect(screen.getByText("Treinar")).toBeTruthy();
  const itens = screen.getAllByRole("listitem").map((li) => li.textContent);
  expect(itens).toEqual(["mates com dama e bispo", "conferir a casa f7 antes de mover"]);
  // o lance do bloco "por que" segue clicável e a citação segue virando link
  expect(screen.getByRole("button", { name: "Qxf7#" })).toBeTruthy();
  expect(screen.getByRole("link", { name: /Táticas › Mates/ })).toBeTruthy();
});

test("o bloco 'Na partida' também tem os lances clicáveis", async () => {
  // o lance que o aluno jogou aparece aqui: tem de dar para ver no tabuleiro.
  // (o lance precisa ser legal na posição do exercício para virar botão)
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao({ na_partida: "Você jogou Bxf7+ e devolveu a vantagem." }));
  const previa = renderCard();
  fireEvent.click(await screen.findByRole("button", { name: "Bxf7+" }));
  expect(previa).toHaveBeenCalled();
});

test("explicação antiga, sem blocos, cai no texto corrido", async () => {
  vi.spyOn(api, "coachExplanation").mockResolvedValue(
    explicacao({ na_partida: null, por_que: null, padrao: null, treinar: [], text: POR_QUE }));
  renderCard();
  expect(await screen.findByText(/A dama e o bispo miram f7/)).toBeTruthy();
  expect(screen.queryByText("Na partida")).toBeNull();
  expect(screen.queryByText("Por que")).toBeNull();
  expect(screen.queryByText("Treinar")).toBeNull();
  // o texto antigo mantém os lances clicáveis e as citações
  expect(screen.getByRole("button", { name: "Qxf7#" })).toBeTruthy();
  expect(screen.getByRole("link", { name: /Táticas › Mates/ })).toBeTruthy();
});

// --- rodapé -------------------------------------------------------------

test("o rodapé leva o custo, o botão de repetir e o aviso do índice vazio", async () => {
  vi.spyOn(api, "coachStatus").mockResolvedValue(status({ index_chunks: 0 }));
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao());
  renderCard();
  const botao = await screen.findByRole("button", { name: "Explicar de novo" });
  // secundário, no rodapé, junto do custo e do aviso do índice
  expect(botao.className).not.toContain("primary");
  const rodape = botao.parentElement as HTMLElement;
  expect(rodape.textContent).toMatch(/claude-opus-5 · US\$ 0,04 · 12 s/);
  expect(rodape.textContent).toMatch(/sem estudos indexados \(Configurações → Recriar índice\)/);
  // o cabeçalho não repete o botão principal quando já existe explicação
  expect(screen.queryByRole("button", { name: "Explicar" })).toBeNull();
});

test("com índice cheio o rodapé não fala de estudos indexados", async () => {
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao());
  renderCard();
  expect(await screen.findByText("Na partida")).toBeTruthy();
  expect(screen.queryByText(/sem estudos indexados/)).toBeNull();
});

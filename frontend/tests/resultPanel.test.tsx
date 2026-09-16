import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { AnalyseOut, CoachStatus, PuzzleOut } from "../src/api/types";
import type { BoardProps } from "../src/board/Board";
import { api } from "../src/api/client";
import { ResultPanel } from "../src/train/ResultPanel";

// o chessground não roda no jsdom: o dublê guarda as props do tabuleiro
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

const last = () => boardProps.at(-1) as unknown as BoardProps;

const FEN = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 12";

const base: PuzzleOut = {
  id: "p1",
  kind: "punish",
  fen_start: FEN,
  side_to_move: "white",
  solution: {
    moves: [
      { uci: "e1e8", by: "solver", alternatives: [] },
      { uci: "c8e8", by: "engine", alternatives: [] },
    ],
    explanation_pv: [],
  },
  end_reason: "material_gain",
  theme: "study",
  category: "study",
  solver_moves: 1,
  is_leech: false,
  srs: { ease: 2.5, interval_days: 0, lapses: 0, due_at: null, last_reviewed_at: null },
  source: "own",
  in_queue: true,
  fen_before: null,
  last_move: null,
  game: { id: "g1", white: "eu", black: "ele", played_at: "2026-01-01T00:00:00Z", source_id: "https://chess.com/g1", my_color: "white" },
  ply: 23,
  move_played: "Re2",
  mistake: { ply: 23, move_played: "Re2", move_uci: "e1e2", eval_before: 30, eval_after: -200, mistake_level: "mistake", mistake_by: "me" },
  study: null,
  siblings: [],
};

const study = (over: Partial<PuzzleOut> = {}): PuzzleOut => ({
  ...base,
  source: "study",
  game: null,
  ply: null,
  move_played: null,
  mistake: null,
  study: { id: "s1", title: "Finais de torre", chapter_id: "c1", chapter_name: "Ponte de Lucena", lichess_url: "https://lichess.org/study/aaa/bbb" },
  ...over,
});

const coachStatus = (over: Partial<CoachStatus> = {}): CoachStatus => ({
  enabled: true, configured: true, model: "claude-opus-5", effort: "high", embeddings_ready: false,
  index_chunks: 0, index_model: "", index_stale: 0, vector_backend: "numpy", langfuse_configured: false, ...over,
});

const analyse: AnalyseOut = {
  fen: FEN,
  turn: "white",
  terminal: null,
  lines: [{ move: "e1e8", san: "Re8+", score: 900, pv: ["e1e8"], pv_san: ["Re8+"] }],
};

beforeEach(() => {
  boardProps.length = 0;
  localStorage.clear();
  vi.spyOn(api, "analyse").mockResolvedValue(analyse);
  vi.spyOn(api, "openings").mockRejectedValue(new Error("sem livro"));
  vi.spyOn(api, "settings").mockRejectedValue(new Error("sem configurações"));
  // treinador desligado (o padrão): o cartão dele não entra; estes testes são sobre o resultado
  vi.spyOn(api, "coachStatus").mockResolvedValue(coachStatus({ enabled: false, configured: false }));
});
afterEach(() => vi.restoreAllMocks());

function renderPanel(puzzle: PuzzleOut) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter>
        <ResultPanel puzzle={puzzle} onRetry={() => {}} onNext={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("a solução vira o tabuleiro de análise, aberto no último lance", () => {
  renderPanel(study());
  expect(screen.getByRole("button", { name: /^12\. Re8\+$/ })).toBeTruthy();
  // lance das pretas no meio da linha: a árvore não repete o número
  const ultimo = screen.getByRole("button", { name: "Rxe8" });
  expect(ultimo.getAttribute("aria-current")).toBe("true");
  expect(last().lastMove).toEqual(["c8", "e8"]);
  fireEvent.keyDown(window, { key: "ArrowLeft" });
  expect(last().lastMove).toEqual(["e1", "e8"]);
});

test("a engine fica desligada até o botão ser apertado", async () => {
  renderPanel(study());
  expect(api.analyse).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Analisar com a engine" }));
  expect(await screen.findByRole("button", { name: /\+9\.00 Re8\+/ })).toBeTruthy();
});

test("puzzle de estudo não mostra links de partida e leva ao capítulo no Lichess", () => {
  renderPanel(study());
  expect(screen.queryByText("partida no chess.com")).toBeNull();
  expect(screen.queryByText("partida no app")).toBeNull();
  expect(screen.getByText("ver no Lichess").getAttribute("href")).toBe("https://lichess.org/study/aaa/bbb");
  expect(screen.getByText("Finais de torre · Ponte de Lucena")).toBeTruthy();
});

test("puzzle próprio traz a partida e o cartão do erro", () => {
  renderPanel(base);
  expect(screen.getByText("partida no chess.com").getAttribute("href")).toBe("https://chess.com/g1");
  // o cartão "Meu erro" já vem aberto e é ele que leva à partida no app
  expect(screen.getByText("partida no app").getAttribute("href")).toBe("/partidas/g1?ply=23");
  expect(screen.getByText("revisão de erros")).toBeTruthy();
});

test("o resultado e o cartão do erro ficam na coluna da direita", () => {
  const { container } = renderPanel(base);
  const lateral = container.querySelector(".painel-lateral");
  expect(lateral).toBeTruthy();
  // o cartão do resultado (com o botão de explorar) e o do erro, os dois no painel
  expect(lateral!.textContent).toMatch(/Explorar/);
  expect(lateral!.textContent).toMatch(/Na partida você jogou/);
  expect(lateral!.querySelector("a[href='/partidas/g1?ply=23']")).toBeTruthy();
});

test("estudo não tem cartão de erro", () => {
  renderPanel(study());
  expect(screen.queryByText("revisão de erros")).toBeNull();
});

test("comentário do autor aparece no lance corrente da árvore", () => {
  renderPanel(study({ solution: { ...base.solution, comments: { "0": "A torre entra pela oitava.", "1": "e o rei está preso." } } }));
  // o texto aparece duas vezes: resumido na árvore e inteiro no cartão de leitura
  expect(screen.getByText("Comentário de Rxe8")).toBeTruthy();
  expect(screen.getAllByText("e o rei está preso.").length).toBeGreaterThan(0);
  fireEvent.keyDown(window, { key: "ArrowLeft" });
  expect(screen.getByText("Comentário de Re8+")).toBeTruthy();
  expect(screen.getAllByText("A torre entra pela oitava.").length).toBeGreaterThan(0);
});

test("resultado traz o botão de tirar da repetição", () => {
  renderPanel(study());
  expect(screen.getByText("Tirar da repetição")).toBeTruthy();
});

test("o cartão do resultado traz o código do exercício", () => {
  renderPanel(study());
  expect(screen.getByTitle("clique para copiar").textContent).toBe("#p1");
});

test("no 'evitar' o lance da partida entra como variação com a refutação", async () => {
  vi.spyOn(api, "puzzle").mockResolvedValue({
    ...base,
    id: "p2",
    kind: "punish",
    fen_start: "2r3k1/5ppp/8/8/Q7/8/4R3/6K1 b - - 1 12",
    side_to_move: "black",
    solution: { moves: [{ uci: "c8c1", by: "solver", alternatives: [] }], explanation_pv: [] },
  });
  renderPanel({ ...base, kind: "avoid", siblings: [{ id: "p2", kind: "punish" }] });

  const jogado = await screen.findByRole("button", { name: /^12\. Re2$/ });
  expect(await screen.findByRole("button", { name: "Rc1+" })).toBeTruthy();
  fireEvent.click(jogado);
  expect(screen.getByText("Comentário de Re2")).toBeTruthy();
  expect(screen.getAllByText("Na partida você jogou Re2").length).toBeGreaterThan(0);
});

test("resolvido por uma alternativa: o tabuleiro abre no lance jogado e a principal vira variação", () => {
  // a solução guarda Re8+ ... ; o usuário fechou com Qa8+ (alternativa aceita)
  const puzzle: PuzzleOut = { ...base, solution: { ...base.solution, moves: [{ ...base.solution.moves[0], alternatives: ["a4a8"] }, ...base.solution.moves.slice(1)] } };
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ResultPanel puzzle={puzzle} played={["a4a8"]} review={{ id: "r", puzzle_id: "p1", result: "correct", used_hint: false, ease: 2.6, interval_days: 1, due_at: "2026-09-09T00:00:00", lapses: 0, is_leech: false }} onRetry={() => {}} onNext={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const jogado = screen.getByRole("button", { name: /Qa8+/ });
  expect(jogado.getAttribute("aria-current")).toBe("true");
  // a principal continua na árvore
  expect(screen.getByRole("button", { name: /^12\. Re8\+$/ })).toBeTruthy();
  expect(screen.getByText(/uma alternativa aceita/).textContent).toContain("Qa8");
});

// --- treinador (IA) ------------------------------------------------------

test("treinador desligado (o padrão): nada dele no resultado, nem com chave configurada", async () => {
  vi.spyOn(api, "coachStatus").mockResolvedValue(coachStatus({ enabled: false, configured: true }));
  vi.spyOn(api, "coachExplanation").mockResolvedValue(null);
  renderPanel(study());
  await waitFor(() => expect(api.coachStatus).toHaveBeenCalled());
  expect(screen.queryByRole("heading", { name: "Treinador" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Explicar" })).toBeNull();
  expect(api.coachExplanation).not.toHaveBeenCalled();
});

test("treinador ligado e configurado: o cartão entra com o botão Explicar", async () => {
  vi.spyOn(api, "coachStatus").mockResolvedValue(coachStatus());
  vi.spyOn(api, "coachExplanation").mockResolvedValue(null);
  renderPanel(study());
  expect(await screen.findByRole("heading", { name: "Treinador" })).toBeTruthy();
  expect(await screen.findByRole("button", { name: "Explicar" })).toBeTruthy();
});

test("resolvido pela linha principal: nada muda no resultado", () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ResultPanel puzzle={base} played={base.solution.moves.map((m) => m.uci)} onRetry={() => {}} onNext={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.queryByText(/alternativa aceita/)).toBeNull();
});

import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ApiError, api } from "../src/api/client";
import type { AttemptOut, SessionOut, TacticOut, TacticsStatus } from "../src/api/types";
import type { PuzzleCtl } from "../src/train/usePuzzle";
import { TacticSession, type TacticSummaryData } from "../src/train/TacticSession";
import { TacticSummary } from "../src/train/TacticSummary";
import type { SessionConfig } from "../src/train/SessionStart";

// O relógio real só expira depois dos minutos planejados; este flag deixa o teste
// pedir "tempo esgotado" sem mexer em temporizadores (o resto do relógio é o de verdade,
// inclusive `continueSession`, que liga `overtime` e desliga `expired`).
const expired = { on: false };
vi.mock("../src/train/useSessionClock", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/train/useSessionClock")>();
  return {
    ...actual,
    useSessionClock: (planned: number | null) => {
      const real = actual.useSessionClock(planned);
      return { ...real, expired: expired.on ? !real.overtime && !real.stopped : real.expired };
    },
  };
});

// A view real usa chessground (arrastar peça não é reproduzível no jsdom);
// aqui basta um botão que joga o lance da solução pelo mesmo `ctl`.
vi.mock("../src/train/PuzzleView", () => ({
  PuzzleView: ({ puzzle, ctl, orderInfo }: { puzzle: TacticOut; ctl: PuzzleCtl<unknown>; orderInfo?: string }) => (
    <div>
      <div>{orderInfo}</div>
      <div>{`fen:${ctl.state.fen}`}</div>
      <button onClick={() => { const u = puzzle.solution.moves[0].uci; ctl.tryMove(u.slice(0, 2) as never, u.slice(2, 4) as never); }}>resolver</button>
    </div>
  ),
}));

// a tática abre na posição de antes do lance do adversário (`fen_before`) e o
// chessground anima `last_move` antes de liberar as peças
const FEN_BEFORE = "4k3/8/8/8/3q4/2N5/7P/4K3 b - - 0 1";
const FEN_START = "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 1 2";

const tactic = (id: string): TacticOut => ({
  id,
  kind: "tactic",
  fen_start: FEN_START,
  fen_before: FEN_BEFORE,
  last_move: "d4d5",
  side_to_move: "white",
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: [] }], explanation_pv: [] },
  end_reason: "material_gain",
  theme: "fork",
  themes: ["fork", "hangingPiece"],
  category: "lichess",
  rating: 1500,
  solver_moves: 1,
  lichess_url: `https://lichess.org/training/${id}`,
  popularity: 90,
  nb_plays: 300,
  opening_tags: [],
  saved: false,
});

const session: SessionOut = { id: "s1", started_at: "2026-01-01T00:00:00Z", ended_at: null, planned_minutes: 25, filters: {}, reviews: 0, correct: 0, total_duration_ms: 0 };

const attempt = (over: Partial<AttemptOut> = {}): AttemptOut => ({
  id: "a1", puzzle_id: "t1", correct: true, used_hint: false,
  rating_before: 1200, rating_after: 1216, delta: 16, puzzle_rating: 1500, ...over,
});

const status: TacticsStatus = {
  imported: true, count: 100, imported_at: null, source_rows: null, rating: 1200, window: 200,
  attempts_total: 0, attempts_today: 0, attempts_30d: 0, correct_30d: 0,
};

const config: SessionConfig = { source: "tactics", mode: "review", filters: {}, plannedMinutes: 25, themes: ["fork"] };

function Host() {
  const [sum, setSum] = useState<TacticSummaryData | null>(null);
  return sum ? <TacticSummary {...sum} onNew={() => setSum(null)} /> : <TacticSession config={config} onFinish={setSum} />;
}

/** O lance do usuário só vale depois da introdução: espera o tabuleiro chegar em `fen_start`. */
async function solve() {
  await screen.findByText(`fen:${FEN_START}`);
  fireEvent.click(screen.getByText("resolver"));
}

function renderSession() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><Host /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(status);
  vi.spyOn(api, "createSession").mockResolvedValue(session);
  vi.spyOn(api, "endSession").mockResolvedValue({ ...session, ended_at: "2026-01-01T00:25:00Z" });
  vi.spyOn(api, "attempt").mockResolvedValue(attempt());
});
afterEach(() => { vi.restoreAllMocks(); expired.on = false; localStorage.clear(); });

test("cria a sessão de táticas e busca a primeira com os temas", async () => {
  const next = vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  renderSession();
  expect(await screen.findByText("resolver")).toBeTruthy();
  expect(api.createSession).toHaveBeenCalledWith({ planned_minutes: 25, filters: { source: "tactics", themes: ["fork"] } });
  expect(next).toHaveBeenCalledWith({ themes: ["fork"], exclude: [] });
  expect(screen.getByText("1ª tática · rating 1200")).toBeTruthy();
});

test("resolver mostra o rating novo e o link do Lichess", async () => {
  vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  renderSession();
  await solve();
  expect(await screen.findByText("Rating 1200 → 1216 (+16)")).toBeTruthy();
  expect(screen.getByText("Resolvido sem erro.")).toBeTruthy();
  // a linha do resultado também começa no lance do adversário, com a numeração recuada
  expect(screen.getByText(/^1… Qd5$/)).toBeTruthy();
  expect(screen.getByText(/^2\. Nxd5$/)).toBeTruthy();
  expect(screen.getByText("ver no Lichess").getAttribute("href")).toBe("https://lichess.org/training/t1");
  expect(api.attempt).toHaveBeenCalledWith(expect.objectContaining({ puzzle_id: "t1", session_id: "s1", correct: true }));
});

test("próximo exclui as táticas já vistas e o 404 encerra com o motivo", async () => {
  const next = vi.spyOn(api, "nextTactic")
    .mockResolvedValueOnce(tactic("t1"))
    .mockRejectedValueOnce(new ApiError(404, "Nenhuma tática nova com esses temas."));
  renderSession();
  await solve();
  fireEvent.click(await screen.findByText("Próximo"));
  expect(next).toHaveBeenLastCalledWith({ themes: ["fork"], exclude: ["t1"] });
  expect(await screen.findByText("Nenhuma tática nova com esses temas.")).toBeTruthy();
  expect(screen.getByText("Rating 1200 → 1216")).toBeTruthy();
});

test("404 logo no começo encerra a sessão com o motivo", async () => {
  vi.spyOn(api, "nextTactic").mockRejectedValue(new ApiError(404, "Banco de táticas vazio."));
  renderSession();
  expect(await screen.findByText("Banco de táticas vazio.")).toBeTruthy();
  expect(screen.getByText("Nova sessão")).toBeTruthy();
});

test("404 logo no começo usa o rating do status mesmo se ele chegar depois do início da sessão", async () => {
  // O efeito de início da sessão roda (e chama `nextTactic`) antes do `tacticsStatus` do
  // react-query resolver. Aqui deixamos o status resolver e re-renderizar primeiro, e só então
  // rejeitamos `nextTactic` com 404 — o resumo final deve refletir o rating do status (1350),
  // não o `DEFAULT_RATING` (1200) capturado pelo efeito na primeira renderização.
  vi.spyOn(api, "tacticsStatus").mockResolvedValue({ ...status, rating: 1350 });
  let rejectNext!: (e: unknown) => void;
  vi.spyOn(api, "nextTactic").mockReturnValue(new Promise((_resolve, reject) => { rejectNext = reject; }));
  renderSession();
  await new Promise((r) => setTimeout(r, 10));
  rejectNext(new ApiError(404, "Banco de táticas vazio."));
  expect(await screen.findByText("Banco de táticas vazio.")).toBeTruthy();
  expect(screen.getByText("Rating 1350 → 1350")).toBeTruthy();
});

test("encerrar sessão sai pelo resumo", async () => {
  vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  renderSession();
  fireEvent.click(await screen.findByText("Encerrar sessão"));
  expect(await screen.findByText("Sessão encerrada.")).toBeTruthy();
  expect(api.endSession).toHaveBeenCalledWith("s1");
});


test("Continuar do tempo esgotado bloqueia o Próximo até a próxima tática chegar", async () => {
  expired.on = true;
  let resolveNext!: (t: TacticOut) => void;
  const next = vi.spyOn(api, "nextTactic")
    .mockResolvedValueOnce(tactic("t1"))
    .mockImplementationOnce(() => new Promise<TacticOut>((res) => { resolveNext = res; }));
  renderSession();
  await solve();
  fireEvent.click(await screen.findByText("Próximo"));
  // com o tempo esgotado o avanço vira o modal; Continuar é que busca a próxima
  fireEvent.click(await screen.findByText("Continuar"));
  const loading = await screen.findByText("Carregando…");
  expect((loading as HTMLButtonElement).disabled).toBe(true);
  // segundo clique durante a busca não pode disparar outra tentativa nem duplicar o resultado
  fireEvent.click(loading);
  expect(next).toHaveBeenCalledTimes(2);
  resolveNext(tactic("t2"));
  expect(await screen.findByText("2ª tática · rating 1216")).toBeTruthy();
});

test("sem candidatos, o resumo oferece uma nova sessão sem temas", () => {
  localStorage.setItem("train.themes", JSON.stringify(["fork"]));
  const onNew = vi.fn();
  render(
    <TacticSummary done={[]} elapsedLabel="00:10" reason="nenhuma tática disponível com esses filtros"
      ratingStart={1200} ratingEnd={1200} onNew={onNew} />,
  );
  fireEvent.click(screen.getByText("Nova sessão sem temas"));
  expect(localStorage.getItem("train.themes")).toBe("[]");
  expect(onNew).toHaveBeenCalledTimes(1);
});

test("resumo com outro motivo não oferece a nova sessão sem temas", () => {
  render(
    <TacticSummary done={[]} elapsedLabel="00:10" reason="Sessão encerrada."
      ratingStart={1200} ratingEnd={1200} onNew={() => {}} />,
  );
  expect(screen.queryByText("Nova sessão sem temas")).toBeNull();
});

test("a tática abre na posição de antes do lance do adversário e depois anima até a do puzzle", async () => {
  vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  renderSession();
  expect(await screen.findByText(`fen:${FEN_BEFORE}`)).toBeTruthy();
  expect(await screen.findByText(`fen:${FEN_START}`)).toBeTruthy();
});

test("guardar a tática resolvida manda o resultado da tentativa", async () => {
  vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  const save = vi.spyOn(api, "saveTactic").mockResolvedValue({} as never);
  renderSession();
  await solve();
  fireEvent.click(await screen.findByText("Guardar para repetir"));
  expect(await screen.findByText("Guardado ✓")).toBeTruthy();
  expect(save).toHaveBeenCalledWith("t1", expect.objectContaining({ correct: true, used_hint: false }));
  expect(typeof (save.mock.calls[0][1] as { duration_ms?: number }).duration_ms).toBe("number");
});

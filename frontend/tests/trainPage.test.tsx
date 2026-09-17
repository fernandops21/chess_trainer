import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { AttemptOut, IrmaosOut, SessionOut, TacticOut, TacticsStatus } from "../src/api/types";
import type { PuzzleCtl } from "../src/train/usePuzzle";
import { TrainPage } from "../src/train/TrainPage";
import { SETTINGS } from "./fixtures/settings";

// A view real usa chessground (não roda no jsdom); um botão que joga o lance da
// solução pelo mesmo `ctl` basta para percorrer a máquina de estados do puzzle.
vi.mock("../src/train/PuzzleView", () => ({
  PuzzleView: ({ puzzle, ctl, orderInfo }: { puzzle: TacticOut; ctl: PuzzleCtl<unknown>; orderInfo?: string }) => (
    <div>
      <div>{orderInfo}</div>
      <div>{`fen:${ctl.state.fen}`}</div>
      <button onClick={() => { const u = puzzle.solution.moves[0].uci; ctl.tryMove(u.slice(0, 2) as never, u.slice(2, 4) as never); }}>resolver</button>
    </div>
  ),
}));

const FEN_START = "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 1 2";

const tactic = (id: string): TacticOut => ({
  id,
  kind: "tactic",
  fen_start: FEN_START,
  side_to_move: "white",
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: [] }], explanation_pv: [] },
  end_reason: "material_gain",
  theme: "fork",
  themes: ["fork"],
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

const status: TacticsStatus = {
  imported: true, count: 100, imported_at: null, source_rows: null, rating: 1200, window: 200,
  attempts_total: 0, attempts_today: 0, attempts_30d: 0, correct_30d: 0,
};

// a tática errada (correct: false) é o que faz o cartão "Repetir o golpe" oferecer o bloco
const attempt = (over: Partial<AttemptOut> = {}): AttemptOut => ({
  id: "a1", puzzle_id: "t1", correct: false, used_hint: false,
  rating_before: 1200, rating_after: 1190, delta: -10, puzzle_rating: 1500, ...over,
});

const irmaos: IrmaosOut = { assinatura: "Ke8 | Q xP f7 #", itens: [{ tier: "mesmo", tactic: tactic("a") }, { tier: "mesmo", tactic: tactic("b") }] };

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><TrainPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(status);
  vi.spyOn(api, "settings").mockResolvedValue(SETTINGS);
  vi.spyOn(api, "createSession").mockResolvedValue(session);
  vi.spyOn(api, "endSession").mockResolvedValue({ ...session, ended_at: "2026-01-01T00:25:00Z" });
  vi.spyOn(api, "attempt").mockResolvedValue(attempt());
  vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  vi.spyOn(api, "golpesStatus").mockResolvedValue({ enabled: true, versao: 1, assinados: 1, total: 1, cobertura: null, rotulagem: false, trechos: 0 });
  vi.spyOn(api, "golpesIrmaos").mockResolvedValue(irmaos);
});
afterEach(async () => {
  // o encerramento agendado na saída da tela roda no próximo tique
  await new Promise((r) => setTimeout(r, 0));
  vi.restoreAllMocks();
  localStorage.clear();
});

test("o cartão do golpe troca a sessão em andamento pelo bloco de irmãos, dentro da mesma tela", async () => {
  const next = vi.spyOn(api, "nextTactic").mockResolvedValue(tactic("t1"));
  renderPage();
  fireEvent.click(screen.getByLabelText("Táticas do Lichess"));
  fireEvent.click(screen.getByText("Começar"));

  await screen.findByText("resolver");
  fireEvent.click(screen.getByText("resolver"));

  const treinar = await screen.findByRole("button", { name: "Treinar 2 parecidos" });
  fireEvent.click(treinar);

  expect(await screen.findByText("Repetir o golpe")).toBeInTheDocument();
  expect(screen.getByText("1 de 2")).toBeTruthy();
  // a lista fixa não bate na fila do Lichess: só a busca da sessão original chamou `nextTactic`
  expect(next).toHaveBeenCalledTimes(1);
});

test("ao fim do bloco, 'Voltar ao treino' retoma a sessão que estava em andamento (achado 4)", async () => {
  const next = vi.spyOn(api, "nextTactic")
    .mockResolvedValueOnce(tactic("t1"))
    .mockResolvedValueOnce(tactic("t2"));
  renderPage();
  fireEvent.click(screen.getByLabelText("Táticas do Lichess"));
  fireEvent.click(screen.getByText("Começar"));

  await screen.findByText("resolver");
  fireEvent.click(screen.getByText("resolver"));

  const treinar = await screen.findByRole("button", { name: "Treinar 2 parecidos" });
  fireEvent.click(treinar);

  // resolve os dois irmãos do bloco (a e b) para o bloco terminar e mostrar o resumo
  await screen.findByText("Repetir o golpe");
  fireEvent.click(screen.getByText("resolver"));
  fireEvent.click(await screen.findByRole("button", { name: "Próximo" }));
  await screen.findByText("2 de 2");
  fireEvent.click(screen.getByText("resolver"));
  fireEvent.click(await screen.findByRole("button", { name: "Próximo" }));

  const voltar = await screen.findByRole("button", { name: "Voltar ao treino" });
  expect(screen.queryByRole("button", { name: "Nova sessão" })).toBeNull();
  fireEvent.click(voltar);

  // a sessão original volta a pedir da fila do Lichess (segunda chamada de nextTactic)
  await screen.findByText("resolver");
  expect(next).toHaveBeenCalledTimes(2);
});

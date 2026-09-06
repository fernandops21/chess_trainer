import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { Settings, StatusOut, TacticsStatus } from "../src/api/types";
import { SettingsPage } from "../src/pages/SettingsPage";

const SETTINGS: Settings = {
  chesscom_username: "eu", categories: ["rapid"], stockfish_path: "", analysis_depth: 18, puzzle_depth: 20,
  mistake_threshold_cp: 100, blunder_threshold_cp: 200, avoid_gap_cp: 150, new_per_day: 10, leech_lapses: 5,
  analysis_seconds: 15, puzzle_search_seconds: 20, puzzle_reply_seconds: 10,
  tactics_rating: 1200, tactics_window: 150, lichess_min_plays: 2000, lichess_min_popularity: 90,
};

const STATUS: StatusOut = {
  engine: { available: true, path: "stockfish" },
  job: { state: "idle", job: null, stage: "", done: 0, total: 0, message: "", error: null, finished_at: null, cancel_requested: false },
  games_total: 0, games_pending: 0, last_import_at: null, local_url: "http://192.168.0.2:8000",
};

const tactics = (over: Partial<TacticsStatus> = {}): TacticsStatus => ({
  imported: false, count: 0, imported_at: null, source_rows: null, rating: 1200, window: 150,
  attempts_total: 0, attempts_today: 0, attempts_30d: 0, correct_30d: 0, ...over,
});

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "settings").mockResolvedValue(SETTINGS);
  vi.spyOn(api, "status").mockResolvedValue(STATUS);
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(tactics());
  vi.spyOn(api, "importTactics").mockResolvedValue({ queued: true, job: "import_lichess" });
});
afterEach(() => vi.restoreAllMocks());

test("sem banco importado mostra 'não importado' e o botão dispara a importação", async () => {
  renderPage();
  expect(await screen.findByText(/não importado/)).toBeTruthy();
  const button = await screen.findByRole("button", { name: "Baixar e importar" });
  fireEvent.click(button);
  await waitFor(() => expect(api.importTactics).toHaveBeenCalled());
});

test("com banco importado mostra a contagem, a data e as tentativas", async () => {
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(
    tactics({ imported: true, count: 1000000, imported_at: "2026-09-01T10:00:00", attempts_total: 42 }),
  );
  renderPage();
  expect(await screen.findByText(/1\.000\.000 táticas · importado em 01\/09\/2026/)).toBeTruthy();
  expect(screen.getByText(/42 tentativas/)).toBeTruthy();
});

test("os campos do filtro e do rating aparecem no formulário", async () => {
  renderPage();
  const rating = (await screen.findByLabelText("Rating inicial de táticas")) as HTMLInputElement;
  expect(rating.value).toBe("1200");
  expect((screen.getByLabelText("Janela de rating (±)") as HTMLInputElement).value).toBe("150");
  expect((screen.getByLabelText("Mínimo de partidas jogadas") as HTMLInputElement).value).toBe("2000");
  expect((screen.getByLabelText("Popularidade mínima (−100 a 100)") as HTMLInputElement).value).toBe("90");
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { Settings, StatusOut, TacticsStatus } from "../src/api/types";
import { SettingsPage } from "../src/pages/SettingsPage";

const SETTINGS: Settings = {
  chesscom_username: "eu", categories: ["rapid"], stockfish_path: "", analysis_depth: 18, puzzle_depth: 20,
  mistake_threshold_cp: 100, blunder_threshold_cp: 200, avoid_gap_cp: 150, unique_gap_cp: 150, new_per_day: 10, new_order: "random", leech_lapses: 5,
  analysis_seconds: 15, puzzle_search_seconds: 20,
  tactics_rating: 1200, tactics_window: 150, lichess_min_plays: 2000, lichess_min_popularity: 90,
  classify_moves: true, refute_wrong_moves: true, lichess_token_set: false,
  anthropic_api_key_set: false, coach_model: "claude-opus-5", coach_effort: "high",
  langfuse_public_key: "", langfuse_secret_key_set: false, langfuse_host: "",
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
  vi.spyOn(api, "saveSettings").mockImplementation(async (body) => {
    const s = { ...SETTINGS, ...body } as Settings;
    // Como o backend real: mandar o segredo (mesmo vazio) atualiza o "_set"; campo ausente mantém o guardado.
    if ("lichess_token" in body) s.lichess_token_set = body.lichess_token !== "";
    if ("anthropic_api_key" in body) s.anthropic_api_key_set = body.anthropic_api_key !== "";
    if ("langfuse_secret_key" in body) s.langfuse_secret_key_set = body.langfuse_secret_key !== "";
    return s;
  });
  vi.spyOn(api, "coachStatus").mockResolvedValue({
    configured: false, model: "claude-opus-5", effort: "high", embeddings_ready: false,
    index_chunks: 0, index_model: "", index_stale: 2, vector_backend: "sqlite-vec", langfuse_configured: false,
  });
  vi.spyOn(api, "coachReindex").mockResolvedValue({ queued: true, job: "coach_reindex" });
  vi.spyOn(api, "extendPuzzles").mockResolvedValue({ queued: true, job: "extend_puzzles" });
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
  const rating = (await screen.findByLabelText("Rating de táticas (ajustado automaticamente)")) as HTMLInputElement;
  expect(rating.value).toBe("1200");
  expect((screen.getByLabelText("Janela de rating (±)") as HTMLInputElement).value).toBe("150");
  expect((screen.getByLabelText("Mínimo de partidas jogadas") as HTMLInputElement).value).toBe("2000");
  expect((screen.getByLabelText("Popularidade mínima (−100 a 100)") as HTMLInputElement).value).toBe("90");
});

// --- token do Lichess ---------------------------------------------------

test("o campo do token vem vazio e é de senha, com a ajuda de onde criar", async () => {
  renderPage();
  const campo = (await screen.findByLabelText("Token do Lichess")) as HTMLInputElement;
  expect(campo.type).toBe("password");
  expect(campo.value).toBe("");
  const aviso = screen.getByText(/Necessário só para o livro de aberturas/);
  expect(aviso.textContent).toContain("https://lichess.org/account/oauth/token");
  expect(aviso.textContent).toContain("Fica só no seu banco");
  // sem token guardado não há aviso nem botão de remover
  expect(screen.queryByText("token configurado")).toBeNull();
  expect(screen.queryByRole("button", { name: "Remover" })).toBeNull();
});

test("com token guardado o campo continua vazio e aparece o aviso", async () => {
  vi.spyOn(api, "settings").mockResolvedValue({ ...SETTINGS, lichess_token_set: true });
  renderPage();
  expect(await screen.findByText("token configurado")).toBeTruthy();
  expect((screen.getByLabelText("Token do Lichess") as HTMLInputElement).value).toBe("");
});

test("salvar sem digitar o token não manda o campo (não apagaria o guardado)", async () => {
  vi.spyOn(api, "settings").mockResolvedValue({ ...SETTINGS, lichess_token_set: true });
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalled());
  const body = vi.mocked(api.saveSettings).mock.calls[0][0];
  expect("lichess_token" in body).toBe(false);
});

test("salvar com o token digitado manda o valor e limpa o campo", async () => {
  renderPage();
  const campo = await screen.findByLabelText("Token do Lichess");
  fireEvent.change(campo, { target: { value: "lip_abc123" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalled());
  expect(vi.mocked(api.saveSettings).mock.calls[0][0].lichess_token).toBe("lip_abc123");
  await waitFor(() => expect((campo as HTMLInputElement).value).toBe(""));
});

test("Remover apaga o token guardado mandando string vazia", async () => {
  vi.spyOn(api, "settings").mockResolvedValue({ ...SETTINGS, lichess_token_set: true });
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Remover" }));
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ lichess_token: "" }));
});

// --- classificação de lances na Análise ---------------------------------

test("a caixa de classificar lances vem do servidor e vai no salvamento", async () => {
  renderPage();
  const caixa = (await screen.findByLabelText("Classificar lances na Análise (usa a engine)")) as HTMLInputElement;
  expect(caixa.type).toBe("checkbox");
  expect(caixa.checked).toBe(true);
  fireEvent.click(caixa);
  expect(caixa.checked).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalled());
  expect(vi.mocked(api.saveSettings).mock.calls[0][0].classify_moves).toBe(false);
});

test("a caixa de refutar o lance errado vem do servidor e vai no salvamento", async () => {
  renderPage();
  const caixa = (await screen.findByLabelText("Refutar o lance errado com a engine")) as HTMLInputElement;
  expect(caixa.type).toBe("checkbox");
  expect(caixa.checked).toBe(true);
  fireEvent.click(caixa);
  expect(caixa.checked).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalled());
  expect(vi.mocked(api.saveSettings).mock.calls[0][0].refute_wrong_moves).toBe(false);
});

test("a ordem dos novos aparece e vai no salvamento", async () => {
  renderPage();
  const select = await screen.findByLabelText("Ordem dos novos") as HTMLSelectElement;
  expect(select.value).toBe("random");
  fireEvent.change(select, { target: { value: "recent" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith(expect.objectContaining({ new_order: "recent" })));
});

// --- Treinador (IA) ------------------------------------------------------

test("a seção do treinador tem chave em campo de senha, modelo, esforço e LangFuse", async () => {
  renderPage();
  const chave = (await screen.findByLabelText("Chave da API da Anthropic")) as HTMLInputElement;
  expect(chave.type).toBe("password");
  expect(chave.placeholder).toBe("cole a chave aqui");
  expect((screen.getByLabelText("Modelo") as HTMLSelectElement).value).toBe("claude-opus-5");
  expect((screen.getByLabelText("Esforço") as HTMLSelectElement).value).toBe("high");
  expect((screen.getByLabelText("Chave secreta do LangFuse") as HTMLInputElement).type).toBe("password");
  expect(screen.getByText(/modelo de embeddings ainda não baixado/)).toBeTruthy();
  expect(screen.getByText(/2 capítulos desatualizados/)).toBeTruthy();
});

test("salvar manda a chave só quando digitada e nunca os campos _set", async () => {
  vi.spyOn(api, "settings").mockResolvedValue({ ...SETTINGS, anthropic_api_key_set: true });
  renderPage();
  expect((await screen.findByLabelText("Chave da API da Anthropic")).getAttribute("placeholder")).toBe("guardada; digite para trocar");
  fireEvent.change(screen.getByLabelText("Modelo"), { target: { value: "claude-sonnet-5" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalled());
  const body = vi.mocked(api.saveSettings).mock.calls[0][0];
  expect(body.coach_model).toBe("claude-sonnet-5");
  expect("anthropic_api_key" in body).toBe(false);
  expect("anthropic_api_key_set" in body).toBe(false);
  expect("langfuse_secret_key_set" in body).toBe(false);
});

test("a chave digitada vai no PUT e o campo esvazia; Remover manda vazio", async () => {
  vi.spyOn(api, "settings").mockResolvedValue({ ...SETTINGS, anthropic_api_key_set: true });
  renderPage();
  const campo = await screen.findByLabelText("Chave da API da Anthropic");
  fireEvent.change(campo, { target: { value: "sk-ant-nova" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(vi.mocked(api.saveSettings).mock.calls[0][0].anthropic_api_key).toBe("sk-ant-nova"));
  await waitFor(() => expect((campo as HTMLInputElement).value).toBe(""));
  fireEvent.click(screen.getByRole("button", { name: "Remover chave" }));
  await waitFor(() => expect(vi.mocked(api.saveSettings).mock.calls.at(-1)![0]).toEqual({ anthropic_api_key: "" }));
});

test("Recriar índice dispara o job", async () => {
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Recriar índice" }));
  await waitFor(() => expect(api.coachReindex).toHaveBeenCalled());
});

test("Estender exercícios dispara o job sem pedir confirmação", async () => {
  renderPage();
  const botao = await screen.findByRole("button", { name: "Estender exercícios" });
  expect(screen.getByText(/Alonga os exercícios existentes enquanto o lance for único/)).toBeTruthy();
  fireEvent.click(botao);
  await waitFor(() => expect(api.extendPuzzles).toHaveBeenCalled());
  // não apaga nada: nenhum modal de confirmação no caminho
  expect(screen.queryByRole("button", { name: "Recriar" })).toBeNull();
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { StatusOut, StudyOut } from "../src/api/types";
import { StudiesPage } from "../src/pages/StudiesPage";

const STATUS: StatusOut = {
  engine: { available: true, path: "stockfish" },
  job: { state: "idle", job: null, stage: "", done: 0, total: 0, message: "", error: null, finished_at: null, cancel_requested: false },
  games_total: 0, games_pending: 0, last_import_at: null, local_url: "http://192.168.0.2:8000",
};

const study = (over: Partial<StudyOut> = {}): StudyOut => ({
  id: "s1",
  title: "Finais de torre",
  author: "Mestre X",
  source_url: "https://lichess.org/study/abc12345",
  lichess_id: "abc12345",
  imported_at: "2026-09-01T10:00:00",
  chapter_count: 3,
  exercise_count: 2,
  in_queue: 2,
  due_today: 1,
  ...over,
});

/** Mostra a rota atual para conferir a navegação dos botões. */
function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/estudos"]}>
        <StudiesPage />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "status").mockResolvedValue(STATUS);
  vi.spyOn(api, "studies").mockResolvedValue([study()]);
  vi.spyOn(api, "importStudy").mockResolvedValue({ queued: true, job: "import_study" });
  vi.spyOn(api, "reimportStudy").mockResolvedValue({ queued: true, job: "import_study" });
  vi.spyOn(api, "setStudyQueue").mockResolvedValue(study({ in_queue: 0 }));
  vi.spyOn(api, "deleteStudy").mockResolvedValue(undefined);
  vi.spyOn(api, "settings").mockResolvedValue({ chesscom_username: "fernando" } as never);
});
afterEach(() => vi.restoreAllMocks());

test("lista os estudos com autor e contagens", async () => {
  renderPage();
  expect(await screen.findByText("Finais de torre")).toBeTruthy();
  expect(screen.getByText(/Mestre X/)).toBeTruthy();
  expect(screen.getByText("3 capítulos · 2 na repetição · 1 vencido hoje")).toBeTruthy();
});

test("sem estudos mostra o estado vazio com a dica da URL", async () => {
  vi.spyOn(api, "studies").mockResolvedValue([]);
  renderPage();
  expect(await screen.findByText("Nenhum estudo importado ainda.")).toBeTruthy();
  expect(screen.getByText(/lichess\.org\/study/)).toBeTruthy();
});

test("importar pela URL chama a API com a url", async () => {
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.change(screen.getByLabelText("URL do estudo no Lichess"), {
    target: { value: "https://lichess.org/study/abc12345" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Importar" }));
  await waitFor(() => expect(api.importStudy).toHaveBeenCalledWith({ url: "https://lichess.org/study/abc12345" }));
});

test("colar PGN mostra a área de texto e importa o PGN", async () => {
  renderPage();
  await screen.findByText("Finais de torre");
  expect(screen.queryByLabelText("PGN do estudo")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "colar PGN" }));
  fireEvent.change(screen.getByLabelText("PGN do estudo"), { target: { value: '[Event "Cap"]\n1. e4 *' } });
  fireEvent.click(screen.getByRole("button", { name: "Importar PGN" }));
  await waitFor(() => expect(api.importStudy).toHaveBeenCalledWith({ pgn: '[Event "Cap"]\n1. e4 *' }));
});

test("escolher um arquivo PGN importa com o nome do arquivo como título", async () => {
  renderPage();
  await screen.findByText("Finais de torre");
  const pgn = '[Event "Linares"]\n\n1. e4 e5 *';
  fireEvent.change(screen.getByLabelText("Arquivo PGN"), {
    target: { files: [new File([pgn], "livro.pgn", { type: "text/plain" })] },
  });
  await waitFor(() => expect(api.importStudy).toHaveBeenCalledWith({ pgn, title: "livro" }));
});

test("remover pede confirmação antes de apagar", async () => {
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Remover" }));
  expect(screen.getByText(/Apaga o estudo, os capítulos, os exercícios e o histórico deles\./)).toBeTruthy();
  expect(api.deleteStudy).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Remover mesmo assim" }));
  await waitFor(() => expect(api.deleteStudy).toHaveBeenCalledWith("s1"));
});

test("treinar este estudo abre Treinar com o estudo escolhido", async () => {
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Treinar este estudo" }));
  expect(screen.getByTestId("where").textContent).toBe("/treinar?mode=study&study=s1");
});

test("com capítulos na repetição o botão tira da repetição", async () => {
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Tirar da repetição" }));
  await waitFor(() => expect(api.setStudyQueue).toHaveBeenCalledWith("s1", false));
});

test("estudo colado como PGN não oferece reimportar e volta para a repetição", async () => {
  vi.spyOn(api, "studies").mockResolvedValue([study({ lichess_id: null, source_url: "", in_queue: 0 })]);
  renderPage();
  await screen.findByText("Finais de torre");
  expect(screen.queryByRole("button", { name: "Reimportar" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Voltar para a repetição" }));
  await waitFor(() => expect(api.setStudyQueue).toHaveBeenCalledWith("s1", true));
});

test("reimportar chama a API do estudo", async () => {
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Reimportar" }));
  await waitFor(() => expect(api.reimportStudy).toHaveBeenCalledWith("s1"));
});

test("o título leva ao detalhe do estudo", async () => {
  renderPage();
  const link = await screen.findByRole("link", { name: "Finais de torre" });
  expect(link.getAttribute("href")).toBe("/estudos/s1");
});

test("estudo só de leitura não oferece o botão da repetição", async () => {
  vi.spyOn(api, "studies").mockResolvedValue([study({ exercise_count: 0, in_queue: 0, due_today: 0 })]);
  renderPage();
  await screen.findByText("Finais de torre");
  expect(screen.queryByRole("button", { name: /repetição/ })).toBeNull();
  expect(screen.getByText("sem exercícios: só capítulos de leitura")).toBeTruthy();
});

test("com uma tarefa em andamento, importar e reimportar ficam desligados", async () => {
  vi.spyOn(api, "status").mockResolvedValue({
    ...STATUS,
    job: { ...STATUS.job, state: "running", job: "import_study", message: "2/5 capítulos" },
  });
  renderPage();
  await screen.findByText("Finais de torre");
  await waitFor(() => expect((screen.getByRole("button", { name: "Reimportar" }) as HTMLButtonElement).disabled).toBe(true));
  fireEvent.change(screen.getByLabelText("URL do estudo no Lichess"), {
    target: { value: "https://lichess.org/study/abc12345" },
  });
  expect((screen.getByRole("button", { name: "Importar" }) as HTMLButtonElement).disabled).toBe(true);
});

test("novo estudo cria e abre o detalhe, com o autor do nome configurado", async () => {
  vi.spyOn(api, "createStudy").mockResolvedValue(study({ id: "s9", title: "Meu estudo", origin: "local" }));
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Novo estudo" }));
  await waitFor(() => expect((screen.getByLabelText("Autor") as HTMLInputElement).value).toBe("fernando"));
  fireEvent.change(screen.getByLabelText("Título do estudo"), { target: { value: "Meu estudo" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar estudo" }));
  await waitFor(() => expect(api.createStudy).toHaveBeenCalledWith({ title: "Meu estudo", author: "fernando" }));
  await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/estudos/s9"));
});

test("o autor sugerido continua editável", async () => {
  vi.spyOn(api, "createStudy").mockResolvedValue(study({ id: "s9", title: "Meu estudo", origin: "local" }));
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Novo estudo" }));
  await waitFor(() => expect((screen.getByLabelText("Autor") as HTMLInputElement).value).toBe("fernando"));
  fireEvent.change(screen.getByLabelText("Autor"), { target: { value: "Outra pessoa" } });
  fireEvent.change(screen.getByLabelText("Título do estudo"), { target: { value: "Meu estudo" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar estudo" }));
  await waitFor(() =>
    expect(api.createStudy).toHaveBeenCalledWith({ title: "Meu estudo", author: "Outra pessoa" }),
  );
});

test("novo estudo sem título não deixa criar", async () => {
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Novo estudo" }));
  expect((screen.getByRole("button", { name: "Criar estudo" }) as HTMLButtonElement).disabled).toBe(true);
});

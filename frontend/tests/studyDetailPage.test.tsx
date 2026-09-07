import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { ChapterDetail, ChapterOut, StudyDetail } from "../src/api/types";
import { StudyDetailPage } from "../src/pages/StudyDetailPage";

const chapter = (over: Partial<ChapterOut> = {}): ChapterOut => ({
  id: "c1",
  order: 1,
  name: "Torre atrás do peão",
  lichess_url: "https://lichess.org/study/abc12345/cap00001",
  mode: "gamebook",
  in_queue: true,
  puzzle_id: "p1",
  intro_comment: "Brancas jogam e ganham.",
  updated_at: null,
  ...over,
});

const detail = (over: Partial<StudyDetail> = {}): StudyDetail => ({
  id: "s1",
  title: "Finais de torre",
  author: "Mestre X",
  source_url: "https://lichess.org/study/abc12345",
  lichess_id: "abc12345",
  imported_at: "2026-09-01T10:00:00",
  chapter_count: 2,
  exercise_count: 2,
  in_queue: 1,
  due_today: 0,
  chapters: [
    chapter(),
    chapter({ id: "c2", order: 2, name: "Ponte de Lucena", mode: "read", in_queue: false, puzzle_id: null, intro_comment: "" }),
  ],
  ...over,
});

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/estudos/s1"]}>
        <Routes>
          <Route path="/estudos/:id" element={<StudyDetailPage />} />
          <Route path="*" element={null} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "study").mockResolvedValue(detail());
});
afterEach(() => vi.restoreAllMocks());

test("mostra o cabeçalho com autor e o link do estudo no Lichess", async () => {
  renderPage();
  expect(await screen.findByText("Finais de torre")).toBeTruthy();
  expect(screen.getByText(/Mestre X/)).toBeTruthy();
  const links = screen.getAllByRole("link", { name: "ver no Lichess" });
  expect(links[0].getAttribute("href")).toBe("https://lichess.org/study/abc12345");
  expect(api.study).toHaveBeenCalledWith("s1");
});

test("lista os capítulos em ordem, com modo e enunciado", async () => {
  renderPage();
  expect(await screen.findByText("Torre atrás do peão")).toBeTruthy();
  expect(screen.getByText("Ponte de Lucena")).toBeTruthy();
  expect(screen.getByText("1.")).toBeTruthy();
  expect(screen.getByText("2.")).toBeTruthy();
  expect(screen.getByText("exercício")).toBeTruthy();
  expect(screen.getByText("leitura (sem exercício)")).toBeTruthy();
  expect(screen.getByText("Brancas jogam e ganham.")).toBeTruthy();
});

test("capítulo com exercício abre o treino daquele exercício; sem exercício não tem botão", async () => {
  renderPage();
  await screen.findByText("Torre atrás do peão");
  const treinar = screen.getAllByRole("button", { name: "Treinar este" });
  expect(treinar.length).toBe(1);
  fireEvent.click(treinar[0]);
  expect(screen.getByTestId("where").textContent).toBe("/treinar?puzzle=p1");
});

test("capítulo fora da repetição ganha a etiqueta", async () => {
  renderPage();
  await screen.findByText("Ponte de Lucena");
  expect(screen.getByText("fora da repetição")).toBeTruthy();
});

test("capítulo sem link no Lichess não mostra o link", async () => {
  vi.spyOn(api, "study").mockResolvedValue(
    detail({ source_url: "", lichess_id: null, chapters: [chapter({ lichess_url: null })] }),
  );
  renderPage();
  await screen.findByText("Torre atrás do peão");
  expect(screen.queryByRole("link", { name: "ver no Lichess" })).toBeNull();
});

// --- edição do estudo (ciclo B2) ---

const detalheCapitulo = (over: Partial<ChapterDetail> = {}): ChapterDetail => ({
  ...chapter(),
  id: "c9",
  name: "Capítulo 3",
  fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  orientation: "white",
  tree: { fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", orientation: "white", intro: "", root: { children: [] } },
  pgn: "",
  updated_at: null,
  ...over,
});

test("editar título e autor manda o PUT do estudo", async () => {
  vi.spyOn(api, "updateStudy").mockResolvedValue({ ...detail(), title: "Torres" });
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Editar título" }));
  fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Torres" } });
  fireEvent.change(screen.getByLabelText("Autor"), { target: { value: "Mestre Y" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() =>
    expect(api.updateStudy).toHaveBeenCalledWith("s1", { title: "Torres", author: "Mestre Y" }),
  );
});

test("novo capítulo cria e abre o editor", async () => {
  vi.spyOn(api, "createChapter").mockResolvedValue(detalheCapitulo());
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Novo capítulo" }));
  fireEvent.change(screen.getByLabelText("Nome do capítulo"), { target: { value: "Capítulo 3" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar capítulo" }));
  await waitFor(() =>
    expect(api.createChapter).toHaveBeenCalledWith("s1", {
      name: "Capítulo 3",
      orientation: "white",
      mode: "gamebook",
    }),
  );
  await waitFor(() =>
    expect(screen.getByTestId("where").textContent).toBe("/estudos/s1/capitulos/c9/editar"),
  );
});

test("novo capítulo com FEN colada manda a FEN e recusa uma inválida", async () => {
  vi.spyOn(api, "createChapter").mockResolvedValue(detalheCapitulo());
  renderPage();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Novo capítulo" }));
  fireEvent.click(screen.getByLabelText("FEN colada"));
  fireEvent.change(screen.getByLabelText("FEN"), { target: { value: "posição inventada" } });
  expect((screen.getByRole("button", { name: "Criar capítulo" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText("FEN inválido.")).toBeTruthy();

  fireEvent.change(screen.getByLabelText("FEN"), { target: { value: "8/8/8/8/8/5k2/8/7K b - - 0 1" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar capítulo" }));
  await waitFor(() =>
    expect(api.createChapter).toHaveBeenCalledWith("s1", {
      name: "Capítulo 3",
      fen: "8/8/8/8/8/5k2/8/7K b - - 0 1",
      orientation: "black",
      mode: "gamebook",
    }),
  );
});

test("reordenar manda a nova ordem dos capítulos", async () => {
  vi.spyOn(api, "updateStudy").mockResolvedValue(detail());
  renderPage();
  await screen.findByText("Ponte de Lucena");
  fireEvent.click(screen.getByRole("button", { name: 'mover "Ponte de Lucena" para cima' }));
  await waitFor(() => expect(api.updateStudy).toHaveBeenCalledWith("s1", { chapter_order: ["c2", "c1"] }));
});

test("o primeiro capítulo não sobe e o último não desce", async () => {
  renderPage();
  await screen.findByText("Ponte de Lucena");
  expect((screen.getByRole("button", { name: 'mover "Torre atrás do peão" para cima' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: 'mover "Ponte de Lucena" para baixo' }) as HTMLButtonElement).disabled).toBe(true);
});

test("duplicar chama a API do capítulo", async () => {
  vi.spyOn(api, "duplicateChapter").mockResolvedValue(detalheCapitulo());
  renderPage();
  await screen.findByText("Torre atrás do peão");
  fireEvent.click(screen.getByRole("button", { name: 'duplicar "Torre atrás do peão"' }));
  await waitFor(() => expect(api.duplicateChapter).toHaveBeenCalledWith("s1", "c1"));
});

test("apagar pede confirmação antes de remover o capítulo", async () => {
  vi.spyOn(api, "deleteChapter").mockResolvedValue(undefined);
  renderPage();
  await screen.findByText("Torre atrás do peão");
  fireEvent.click(screen.getByRole("button", { name: 'apagar "Torre atrás do peão"' }));
  expect(screen.getByText("Apaga o capítulo, o exercício e o histórico dele. Não pode ser desfeito.")).toBeTruthy();
  expect(api.deleteChapter).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Apagar mesmo assim" }));
  await waitFor(() => expect(api.deleteChapter).toHaveBeenCalledWith("s1", "c1"));
});

test("links de edição, leitura e exportação de PGN", async () => {
  renderPage();
  await screen.findByText("Torre atrás do peão");
  expect(screen.getByRole("link", { name: 'ver "Torre atrás do peão"' }).getAttribute("href")).toBe(
    "/estudos/s1/capitulos/c1",
  );
  expect(screen.getByRole("link", { name: 'editar "Torre atrás do peão"' }).getAttribute("href")).toBe(
    "/estudos/s1/capitulos/c1/editar",
  );
  expect(screen.getByRole("link", { name: 'PGN de "Torre atrás do peão"' }).getAttribute("href")).toBe(
    "/api/studies/s1/chapters/c1/pgn",
  );
  expect(screen.getByRole("link", { name: "Exportar PGN" }).getAttribute("href")).toBe("/api/studies/s1/pgn");
});

test("estudo importado avisa que reimportar sobrescreve as edições", async () => {
  vi.spyOn(api, "study").mockResolvedValue(detail({ origin: "lichess" }));
  renderPage();
  await screen.findByText("Finais de torre");
  expect(screen.getByText("Estudo importado: reimportar sobrescreve as edições feitas aqui.")).toBeTruthy();
});

test("estudo local não mostra o aviso de reimportação", async () => {
  vi.spyOn(api, "study").mockResolvedValue(detail({ origin: "local", lichess_id: null, source_url: "" }));
  renderPage();
  await screen.findByText("Finais de torre");
  expect(screen.queryByText(/reimportar sobrescreve/)).toBeNull();
});

test("capítulo fora da repetição não oferece treinar, mesmo tendo exercício", async () => {
  vi.spyOn(api, "study").mockResolvedValue(
    detail({ chapters: [chapter({ id: "c3", name: "Fora da fila", in_queue: false, puzzle_id: "p3" })] }),
  );
  renderPage();
  await screen.findByText("Fora da fila");
  expect(screen.queryByRole("button", { name: "Treinar este" })).toBeNull();
});

test("capítulo de leitura não oferece treinar, mesmo com exercício guardado", async () => {
  // virar leitura tira o exercício da repetição sem apagá-lo: o botão levaria a
  // um exercício que não está mais na fila
  vi.spyOn(api, "study").mockResolvedValue(
    detail({ chapters: [chapter({ id: "c4", name: "Virou leitura", mode: "read", puzzle_id: "p4" })] }),
  );
  renderPage();
  await screen.findByText("Virou leitura");
  expect(screen.queryByRole("button", { name: "Treinar este" })).toBeNull();
});

test("reordenar de novo só libera depois de a lista voltar do servidor", async () => {
  let liberar!: () => void;
  let vezes = 0;
  vi.spyOn(api, "study").mockImplementation(() => {
    vezes += 1;
    if (vezes === 1) return Promise.resolve(detail());
    return new Promise((res) => { liberar = () => res(detail()); });
  });
  vi.spyOn(api, "updateStudy").mockResolvedValue(detail());
  renderPage();
  await screen.findByText("Ponte de Lucena");

  const subir = () => screen.getByRole("button", { name: 'mover "Ponte de Lucena" para cima' }) as HTMLButtonElement;
  fireEvent.click(subir());
  await waitFor(() => expect(api.updateStudy).toHaveBeenCalledTimes(1));
  // a lista ainda é a antiga: um segundo clique mandaria a ordem errada
  await waitFor(() => expect(subir().disabled).toBe(true));

  await act(async () => { liberar(); });
  await waitFor(() => expect(subir().disabled).toBe(false));
});

test("apagar avisa que não pode ser desfeito e trava o botão enquanto apaga", async () => {
  let liberar!: () => void;
  vi.spyOn(api, "deleteChapter").mockReturnValue(new Promise((res) => { liberar = () => res(undefined); }));
  renderPage();
  await screen.findByText("Torre atrás do peão");
  fireEvent.click(screen.getByRole("button", { name: 'apagar "Torre atrás do peão"' }));
  expect(screen.getByText(/Não pode ser desfeito\./)).toBeTruthy();

  const confirmar = () => screen.getByRole("button", { name: "Apagar mesmo assim" }) as HTMLButtonElement;
  fireEvent.click(confirmar());
  await waitFor(() => expect(confirmar().disabled).toBe(true));

  await act(async () => { liberar(); });
  await waitFor(() => expect(screen.queryByText(/Não pode ser desfeito\./)).toBeNull());
  expect(api.deleteChapter).toHaveBeenCalledWith("s1", "c1");
});

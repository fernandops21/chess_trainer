import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { ChapterDetail, StudyOut } from "../src/api/types";
import { emptyTree, insertLine } from "../src/analysis/moveTree";
import { SaveChapterModal } from "../src/analysis/SaveChapterModal";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const tree = insertLine(emptyTree(START), null, ["e2e4", "e7e5"]).tree;

const study = (over: Partial<StudyOut> = {}): StudyOut => ({
  id: "s9", title: "Novo estudo", author: "", source_url: "", lichess_id: null,
  imported_at: null, chapter_count: 0, exercise_count: 0, in_queue: 0, due_today: 0,
  origin: "local", updated_at: null, ...over,
});

const chapter = (over: Partial<ChapterDetail> = {}): ChapterDetail => ({
  id: "c9", order: 0, name: "Capítulo 1", lichess_url: null, mode: "gamebook",
  in_queue: true, puzzle_id: null, intro_comment: "",
  fen: START, orientation: "white", tree, pgn: "", updated_at: null, ...over,
});

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname}</div>;
}

function renderModal(onClose = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/analise"]}>
        <SaveChapterModal tree={tree} onClose={onClose} />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onClose;
}

beforeEach(() => {
  vi.spyOn(api, "studies").mockResolvedValue([study({ id: "s1", title: "Finais de torre" })]);
  vi.spyOn(api, "settings").mockResolvedValue({ chesscom_username: "fernando" } as never);
  vi.spyOn(api, "createStudy").mockResolvedValue(study());
  vi.spyOn(api, "createChapter").mockResolvedValue(chapter());
  vi.spyOn(api, "saveChapter").mockResolvedValue(chapter());
});
afterEach(() => vi.restoreAllMocks());

test("novo estudo: cria o estudo, o capítulo, salva a árvore e abre o editor", async () => {
  const onClose = renderModal();
  fireEvent.click(screen.getByLabelText("novo estudo"));
  // o autor sai do nome configurado: espera as configurações chegarem
  await waitFor(() => expect((screen.getByLabelText("Autor") as HTMLInputElement).value).toBe("fernando"));
  fireEvent.change(screen.getByLabelText("Título do estudo"), { target: { value: "Aberturas" } });
  fireEvent.change(screen.getByLabelText("Nome do capítulo"), { target: { value: "Ruy López" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(api.createStudy).toHaveBeenCalledWith({ title: "Aberturas", author: "fernando" }));
  await waitFor(() =>
    expect(api.createChapter).toHaveBeenCalledWith("s9", {
      name: "Ruy López", fen: START, orientation: "white", mode: "gamebook",
    }),
  );
  await waitFor(() =>
    expect(api.saveChapter).toHaveBeenCalledWith("s9", "c9", {
      name: "Ruy López", mode: "gamebook", orientation: "white", tree,
    }),
  );
  await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/estudos/s9/capitulos/c9/editar"));
  expect(onClose).toHaveBeenCalled();
});

test("estudo existente: usa o id escolhido e não cria estudo", async () => {
  renderModal();
  await screen.findByText("Finais de torre");
  fireEvent.change(screen.getByLabelText("Estudo"), { target: { value: "s1" } });
  fireEvent.change(screen.getByLabelText("Nome do capítulo"), { target: { value: "Torre e peão" } });
  fireEvent.change(screen.getByLabelText("Modo"), { target: { value: "read" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(api.createChapter).toHaveBeenCalledWith("s1", {
    name: "Torre e peão", fen: START, orientation: "white", mode: "read",
  }));
  expect(api.createStudy).not.toHaveBeenCalled();
});

test("mostra o erro do servidor sem fechar", async () => {
  vi.spyOn(api, "saveChapter").mockRejectedValue(new Error("lance ilegal"));
  const onClose = renderModal();
  fireEvent.click(screen.getByLabelText("novo estudo"));
  fireEvent.change(screen.getByLabelText("Título do estudo"), { target: { value: "Aberturas" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveChapter).toHaveBeenCalled());
  expect(await screen.findByText("lance ilegal")).toBeTruthy();
  expect(onClose).not.toHaveBeenCalled();
});

test("o campo do nome começa vazio e o padrão vem do placeholder", async () => {
  renderModal();
  const nome = screen.getByLabelText("Nome do capítulo") as HTMLInputElement;
  expect(nome.value).toBe("");
  expect(nome.placeholder).toBe("Capítulo 1");
  await screen.findByText("Finais de torre");
  fireEvent.change(nome, { target: { value: "Francesa" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(api.createChapter).toHaveBeenCalledWith("s1", {
    name: "Francesa", fen: START, orientation: "white", mode: "gamebook",
  }));
});

test("nome em branco vira o padrão", async () => {
  renderModal();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(api.createChapter).toHaveBeenCalledWith("s1", {
    name: "Capítulo 1", fen: START, orientation: "white", mode: "gamebook",
  }));
});

test("erro ao salvar a árvore desfaz o capítulo e o estudo recém-criados", async () => {
  vi.spyOn(api, "saveChapter").mockRejectedValue(new Error("lance ilegal"));
  const apagarCapitulo = vi.spyOn(api, "deleteChapter").mockResolvedValue(undefined as never);
  const apagarEstudo = vi.spyOn(api, "deleteStudy").mockResolvedValue(undefined as never);
  renderModal();
  fireEvent.click(screen.getByLabelText("novo estudo"));
  fireEvent.change(screen.getByLabelText("Título do estudo"), { target: { value: "Aberturas" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(apagarCapitulo).toHaveBeenCalledWith("s9", "c9"));
  await waitFor(() => expect(apagarEstudo).toHaveBeenCalledWith("s9"));
  expect(await screen.findByText("lance ilegal")).toBeTruthy();
});

test("em estudo existente o rollback apaga só o capítulo", async () => {
  vi.spyOn(api, "saveChapter").mockRejectedValue(new Error("lance ilegal"));
  const apagarCapitulo = vi.spyOn(api, "deleteChapter").mockResolvedValue(undefined as never);
  const apagarEstudo = vi.spyOn(api, "deleteStudy").mockResolvedValue(undefined as never);
  renderModal();
  await screen.findByText("Finais de torre");
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(apagarCapitulo).toHaveBeenCalledWith("s1", "c9"));
  expect(apagarEstudo).not.toHaveBeenCalled();
});

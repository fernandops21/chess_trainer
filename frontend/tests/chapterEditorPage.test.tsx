import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Key } from "chessground/types";
import type { BoardProps } from "../src/board/Board";
import { ApiError, api } from "../src/api/client";
import type { AnalyseOut, ChapterDetail, ChapterSaveIn } from "../src/api/types";

// O chessground não roda no jsdom: o dublê guarda as props e devolve o `onMove`.
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

import { emptyTree, insertLine } from "../src/analysis/moveTree";
import { ChapterEditorPage } from "../src/pages/ChapterEditorPage";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const arvore = insertLine(emptyTree(START), null, ["e2e4", "e7e5"]).tree;

const last = () => boardProps.at(-1) as unknown as BoardProps;
const play = (uci: string) =>
  act(() => { last().onMove!(uci.slice(0, 2) as Key, uci.slice(2, 4) as Key); });

const analyse: AnalyseOut = { fen: START, turn: "white", terminal: null, lines: [] };

const capitulo = (over: Partial<ChapterDetail> = {}): ChapterDetail => ({
  id: "c1",
  order: 1,
  name: "Torre atrás do peão",
  lichess_url: null,
  mode: "gamebook",
  in_queue: true,
  puzzle_id: "p1",
  intro_comment: "Brancas jogam e ganham.",
  fen: START,
  orientation: "white",
  tree: { ...arvore, intro: "Brancas jogam e ganham." },
  pgn: "",
  updated_at: null,
  ...over,
});

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/estudos/s1/capitulos/c1/editar"]}>
        <Routes>
          <Route path="/estudos/:id/capitulos/:cid/editar" element={<ChapterEditorPage />} />
          <Route path="*" element={null} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Último corpo mandado ao `PUT`. */
const corpo = (): ChapterSaveIn => vi.mocked(api.saveChapter).mock.calls.at(-1)![2];

beforeEach(() => {
  boardProps.length = 0;
  vi.spyOn(api, "analyse").mockResolvedValue(analyse);
  vi.spyOn(api, "chapter").mockResolvedValue(capitulo());
  vi.spyOn(api, "saveChapter").mockResolvedValue(capitulo());
});
afterEach(() => vi.restoreAllMocks());

test("carrega o capítulo no cabeçalho e na árvore", async () => {
  renderPage();
  expect((await screen.findByLabelText("Nome do capítulo") as HTMLInputElement).value).toBe("Torre atrás do peão");
  expect((screen.getByLabelText("Modo") as HTMLSelectElement).value).toBe("gamebook");
  expect((screen.getByLabelText("Orientação") as HTMLSelectElement).value).toBe("white");
  expect((screen.getByLabelText("Enunciado") as HTMLTextAreaElement).value).toBe("Brancas jogam e ganham.");
  expect(screen.getByText(/^1\. e4$/)).toBeTruthy();
  expect(api.chapter).toHaveBeenCalledWith("s1", "c1");
});

test("Salvar manda nome, modo, orientação e árvore", async () => {
  renderPage();
  const nome = await screen.findByLabelText("Nome do capítulo");
  fireEvent.change(nome, { target: { value: "Torre por trás" } });
  fireEvent.change(screen.getByLabelText("Modo"), { target: { value: "read" } });
  fireEvent.change(screen.getByLabelText("Orientação"), { target: { value: "black" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(api.saveChapter).toHaveBeenCalled());
  const calls = vi.mocked(api.saveChapter).mock.calls.at(-1)!;
  expect(calls[0]).toBe("s1");
  expect(calls[1]).toBe("c1");
  const body = corpo();
  expect(body.name).toBe("Torre por trás");
  expect(body.mode).toBe("read");
  expect(body.orientation).toBe("black");
  expect(body.tree.root.children[0].san).toBe("e4");
  expect(body.tree.orientation).toBe("black");
});

test("o enunciado editado no cabeçalho vai na árvore salva", async () => {
  renderPage();
  const enunciado = await screen.findByLabelText("Enunciado");
  fireEvent.change(enunciado, { target: { value: "Pretas jogam e empatam." } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveChapter).toHaveBeenCalled());
  expect(corpo().tree.intro).toBe("Pretas jogam e empatam.");
});

test("um lance novo marca alterações não salvas; salvar mostra a hora", async () => {
  renderPage();
  await screen.findByLabelText("Nome do capítulo");
  expect(screen.queryByText("alterações não salvas")).toBeNull();
  play("g1f3");
  expect(screen.getByText("alterações não salvas")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(screen.getByText(/salvo às \d{2}:\d{2}/)).toBeTruthy());
  expect(screen.queryByText("alterações não salvas")).toBeNull();
});

test("erro 422 lista as mensagens do servidor", async () => {
  vi.spyOn(api, "saveChapter").mockRejectedValue(
    new ApiError(422, "lance ilegal no nó n3: e2e5; comentário longo demais", ["lance ilegal no nó n3: e2e5", "comentário longo demais"]),
  );
  renderPage();
  await screen.findByLabelText("Nome do capítulo");
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("lance ilegal no nó n3: e2e5")).toBeTruthy();
  expect(screen.getByText("comentário longo demais")).toBeTruthy();
});

test("voltar ao estudo pede confirmação quando há alterações não salvas", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  renderPage();
  await screen.findByLabelText("Nome do capítulo");
  play("g1f3");
  fireEvent.click(screen.getByRole("link", { name: "Voltar ao estudo" }));
  expect(confirm).toHaveBeenCalled();
  expect(screen.getByTestId("where").textContent).toBe("/estudos/s1/capitulos/c1/editar");

  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole("link", { name: "Voltar ao estudo" }));
  expect(screen.getByTestId("where").textContent).toBe("/estudos/s1");
});

test("sem alterações o link volta direto", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPage();
  await screen.findByLabelText("Nome do capítulo");
  fireEvent.click(screen.getByRole("link", { name: "Voltar ao estudo" }));
  expect(confirm).not.toHaveBeenCalled();
  expect(screen.getByTestId("where").textContent).toBe("/estudos/s1");
});

test("salvar mantém o lance atual no tabuleiro", async () => {
  renderPage();
  await screen.findByLabelText("Nome do capítulo");
  fireEvent.click(screen.getByText("e5"));
  const fen = last().fen;
  expect(fen).not.toBe(START);

  // o enunciado do cabeçalho só entra na árvore na hora de salvar: o tabuleiro
  // recebe uma árvore nova e não pode voltar à posição inicial por causa disso
  fireEvent.change(screen.getByLabelText("Enunciado"), { target: { value: "Pretas jogam e empatam." } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(screen.getByText(/salvo às \d{2}:\d{2}/)).toBeTruthy());
  expect(last().fen).toBe(fen);
  expect(screen.getByText("e5").getAttribute("aria-current")).toBe("true");
});

test("edição feita enquanto o PUT está no ar continua não salva", async () => {
  let liberar!: () => void;
  vi.spyOn(api, "saveChapter").mockReturnValue(
    new Promise((res) => { liberar = () => res(capitulo()); }),
  );
  renderPage();
  await screen.findByLabelText("Nome do capítulo");
  play("g1f3");
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveChapter).toHaveBeenCalled());

  // o usuário continua editando antes de a resposta chegar
  fireEvent.change(screen.getByLabelText("Nome do capítulo"), { target: { value: "Outro nome" } });
  await act(async () => { liberar(); });

  expect(screen.getByText("alterações não salvas")).toBeTruthy();
  expect(screen.queryByText(/salvo às/)).toBeNull();
});

test("mudar a orientação ou sair do enunciado não volta ao começo", async () => {
  renderPage();
  await screen.findByLabelText("Nome do capítulo");
  fireEvent.click(screen.getByText("e5"));
  const fen = last().fen;
  expect(fen).not.toBe(START);

  fireEvent.change(screen.getByLabelText("Orientação"), { target: { value: "black" } });
  expect(last().fen).toBe(fen);
  expect(last().orientation).toBe("black");

  const enunciado = screen.getByLabelText("Enunciado");
  fireEvent.change(enunciado, { target: { value: "Pretas jogam e empatam." } });
  fireEvent.blur(enunciado);
  expect(last().fen).toBe(fen);
  expect(screen.getByText("e5").getAttribute("aria-current")).toBe("true");
});

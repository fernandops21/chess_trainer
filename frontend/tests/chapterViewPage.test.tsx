import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Key } from "chessground/types";
import { api, ApiError } from "../src/api/client";
import type { BoardProps } from "../src/board/Board";
import type { AnalyseOut, ChapterDetail } from "../src/api/types";

const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

import { emptyTree, insertLine, mainline, setComment } from "../src/analysis/moveTree";
import { ChapterViewPage } from "../src/pages/ChapterViewPage";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const arvore = insertLine(emptyTree(START), null, ["e2e4", "e7e5"]).tree;

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
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/estudos/s1/capitulos/c1"]}>
        <Routes>
          <Route path="/estudos/:id/capitulos/:cid" element={<ChapterViewPage />} />
          <Route path="*" element={null} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  boardProps.length = 0;
  vi.spyOn(api, "analyse").mockResolvedValue(analyse);
  vi.spyOn(api, "chapter").mockResolvedValue(capitulo());
});
afterEach(() => vi.restoreAllMocks());

test("mostra nome, enunciado e a árvore do capítulo", async () => {
  renderPage();
  expect(await screen.findByText("Torre atrás do peão")).toBeTruthy();
  expect(screen.getByText("Brancas jogam e ganham.")).toBeTruthy();
  expect(screen.getByText(/^1\. e4$/)).toBeTruthy();
});

test("é só leitura: sem caixa de comentário e sem botão Salvar", async () => {
  renderPage();
  await screen.findByText("Torre atrás do peão");
  expect(screen.queryByLabelText("Comentário")).toBeNull();
  expect(screen.queryByRole("button", { name: "Salvar" })).toBeNull();
});

/** Comentário maior que o resumo da lista de lances (que corta em 80 e põe reticências). */
const COMENTARIO_LONGO =
  "Este lance abre a diagonal do bispo e a da dama, e é assim que o Chernev explica a partida no Logical Chess: cada lance com um porquê, sem pular nada.";

test("a leitura usa o modo livro: página do lance à direita e a lista sob o tabuleiro", async () => {
  const { container } = renderPage();
  await screen.findByText("Torre atrás do peão");
  expect(container.querySelector(".livro-pagina")).toBeTruthy();
  expect(container.querySelector(".tree")).toBeTruthy();
});

test("o comentário do autor sai inteiro no livro, sem reticências", async () => {
  const comentada = setComment(arvore, mainline(arvore)[0].id, COMENTARIO_LONGO);
  vi.spyOn(api, "chapter").mockResolvedValue(
    capitulo({ tree: { ...comentada, intro: "Brancas jogam e ganham." } }),
  );
  const { container } = renderPage();
  await screen.findByText("Torre atrás do peão");
  // na lista só a marca; a página traz o comentário inteiro quando o lance é o atual
  expect(container.querySelector(".tree .comment")).toBeNull();
  expect(container.querySelector(".tree .tem-comentario")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /^1\. e4/ }));
  const pagina = container.querySelector(".livro-pagina")!;
  expect(pagina.textContent).toContain(COMENTARIO_LONGO);
  expect(pagina.textContent).not.toContain("…");
});

test("Treinar este abre o exercício do capítulo", async () => {
  renderPage();
  await screen.findByText("Torre atrás do peão");
  fireEvent.click(screen.getByRole("button", { name: "Treinar este" }));
  expect(screen.getByTestId("where").textContent).toBe("/treinar?puzzle=p1");
});

test("sem exercício na repetição não oferece treinar", async () => {
  vi.spyOn(api, "chapter").mockResolvedValue(capitulo({ mode: "read", puzzle_id: null, in_queue: false }));
  renderPage();
  await screen.findByText("Torre atrás do peão");
  expect(screen.queryByRole("button", { name: "Treinar este" })).toBeNull();
});

test("capítulo de leitura não oferece treinar, mesmo com exercício guardado", async () => {
  // virar leitura tira o exercício da repetição sem apagá-lo: o botão levaria a
  // um exercício que não está mais na fila
  vi.spyOn(api, "chapter").mockResolvedValue(capitulo({ mode: "read", puzzle_id: "p1", in_queue: true }));
  renderPage();
  await screen.findByText("Torre atrás do peão");
  expect(screen.queryByRole("button", { name: "Treinar este" })).toBeNull();
});

test("tem os links de editar e voltar ao estudo", async () => {
  renderPage();
  await screen.findByText("Torre atrás do peão");
  expect(screen.getByRole("link", { name: "Editar" }).getAttribute("href")).toBe(
    "/estudos/s1/capitulos/c1/editar",
  );
  expect(screen.getByRole("link", { name: "Voltar ao estudo" }).getAttribute("href")).toBe("/estudos/s1");
});

/** Diagrama do estudo do Basso ("Ataque duplo - Cavalo"): sem rei branco. */
const SEM_REIS = "r1r5/8/1N6/8/8/8/5N2/3k3q w - - 0 1";
const MSG_ENGINE = "posição inválida para a engine (faltam os dois reis ou há peças demais)";

/** O último tabuleiro renderizado (o dublê guarda as props). */
const tabuleiro = () => boardProps.at(-1) as unknown as BoardProps;

function capituloSemReis() {
  vi.spyOn(api, "chapter").mockResolvedValue(
    capitulo({ fen: SEM_REIS, tree: { ...emptyTree(SEM_REIS), intro: "Brancas jogam e ganham." } }),
  );
}

test("capítulo sem os dois reis abre o tabuleiro com as peças do diagrama", async () => {
  capituloSemReis();
  renderPage();
  await screen.findByText("Torre atrás do peão");
  expect(tabuleiro().fen).toBe(SEM_REIS);
  // os dois ataques duplos do cavalo de b6 estão à disposição
  expect(tabuleiro().dests?.get("b6" as Key)).toEqual(expect.arrayContaining(["a8", "c8"]));
});

test("no diagrama sem os dois reis dá para jogar Nxc8", async () => {
  capituloSemReis();
  renderPage();
  await screen.findByText("Torre atrás do peão");
  act(() => { tabuleiro().onMove!("b6" as Key, "c8" as Key); });
  expect(screen.getByRole("button", { name: "1. Nxc8+" })).toBeTruthy();
});

test("no diagrama sem os dois reis dá para jogar Nxa8", async () => {
  capituloSemReis();
  renderPage();
  await screen.findByText("Torre atrás do peão");
  act(() => { tabuleiro().onMove!("b6" as Key, "a8" as Key); });
  expect(screen.getByRole("button", { name: "1. Nxa8+" })).toBeTruthy();
});

test("o painel do motor mostra por que a engine não analisa o diagrama", async () => {
  capituloSemReis();
  vi.spyOn(api, "analyse").mockRejectedValue(new ApiError(400, MSG_ENGINE));
  renderPage();
  // lendo um capítulo a engine começa desligada: nada de seta nem de análise até o leitor pedir
  expect(await screen.findByRole("button", { name: "Analisar com a engine" })).toBeTruthy();
  expect(api.analyse).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Analisar com a engine" }));
  expect(await screen.findByText(MSG_ENGINE)).toBeTruthy();
});

test("'Editar' leva o lance atual, e '?lance=' abre a leitura nele", async () => {
  const { container } = renderPage();
  await screen.findByText("Torre atrás do peão");
  fireEvent.click(screen.getByRole("button", { name: /^1\. e4/ }));
  const editar = screen.getByRole("link", { name: "Editar" }) as HTMLAnchorElement;
  expect(editar.getAttribute("href")).toBe("/estudos/s1/capitulos/c1/editar?lance=n1");
  // e na volta: sem lance escolhido o link não leva nada
  fireEvent.click(screen.getByRole("button", { name: "posição inicial" }));
  expect((screen.getByRole("link", { name: "Editar" }) as HTMLAnchorElement).getAttribute("href")).toBe("/estudos/s1/capitulos/c1/editar");
  expect(container.querySelector(".livro-pagina")).toBeTruthy();
});

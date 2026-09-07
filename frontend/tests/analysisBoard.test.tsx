import { useState, type ReactNode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Key } from "chessground/types";
import type { BoardProps } from "../src/board/Board";
import { api } from "../src/api/client";
import type { AnalyseOut, OpeningsOut, Settings } from "../src/api/types";

// O chessground não é reproduzível no jsdom: o dublê guarda o que o
// AnalysisBoard manda e devolve o `onMove` para o teste jogar um lance.
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

import { MAX_NODES, emptyTree, fenAt, findNode, insertLine, setComment } from "../src/analysis/moveTree";
import type { Tree } from "../src/analysis/moveTree";
import { AnalysisBoard } from "../src/analysis/AnalysisBoard";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const last = () => boardProps.at(-1) as unknown as BoardProps;
const play = (uci: string) =>
  act(() => { last().onMove!(uci.slice(0, 2) as Key, uci.slice(2, 4) as Key); });

const analyse: AnalyseOut = {
  fen: START,
  turn: "white",
  terminal: null,
  lines: [{ move: "e2e4", san: "e4", score: 30, pv: ["e2e4", "e7e5", "g1f3"], pv_san: ["e4", "e5", "Nf3"] }],
};

function renderBoard(props: Partial<Parameters<typeof AnalysisBoard>[0]> = {}) {
  const onTreeChange = vi.fn();
  const onSave = vi.fn();
  const r = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <AnalysisBoard tree={emptyTree(START)} onTreeChange={onTreeChange} onSave={onSave} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...r, onTreeChange, onSave };
}

/** Última árvore que o componente devolveu. */
const lastTree = (spy: ReturnType<typeof vi.fn>): Tree => spy.mock.calls.at(-1)![0] as Tree;

const aberturas: OpeningsOut = {
  opening: { eco: "A00", name: "Posição inicial" },
  total: 3000, white: 1200, draws: 900, black: 900,
  moves: [{ uci: "e2e4", san: "e4", games: 2000, white: 800, draws: 600, black: 600, avg_rating: 2400 }],
};

/** Configurações do teste: sem classificação, a não ser onde o teste ligar. */
const SETTINGS: Settings = {
  chesscom_username: "eu", categories: ["rapid"], stockfish_path: "", analysis_depth: 18, puzzle_depth: 20,
  mistake_threshold_cp: 100, blunder_threshold_cp: 200, avoid_gap_cp: 150, new_per_day: 10, leech_lapses: 5,
  analysis_seconds: 15, puzzle_search_seconds: 20, puzzle_reply_seconds: 10,
  tactics_rating: 1200, tactics_window: 150, lichess_min_plays: 2000, lichess_min_popularity: 90,
  classify_moves: false, lichess_token_set: false,
};

beforeEach(() => {
  boardProps.length = 0;
  localStorage.clear();
  vi.spyOn(api, "analyse").mockResolvedValue(analyse);
  vi.spyOn(api, "openings").mockResolvedValue(aberturas);
  vi.spyOn(api, "settings").mockResolvedValue(SETTINGS);
});
afterEach(() => vi.restoreAllMocks());

test("joga lances pelo tabuleiro e avisa a árvore nova", () => {
  const { container, onTreeChange } = renderBoard();
  play("e2e4");
  play("e7e5");
  expect(container.textContent).toMatch(/1\. e4/);
  expect(container.textContent).toMatch(/e5/);
  const t = lastTree(onTreeChange);
  expect(t.root.children[0].san).toBe("e4");
  expect(t.root.children[0].children[0].san).toBe("e5");
});

test("navega pelo teclado: setas e Home", () => {
  renderBoard();
  play("e2e4");
  play("e7e5");
  const depois = last().fen;
  fireEvent.keyDown(window, { key: "ArrowLeft" });
  expect(last().fen).not.toBe(depois);
  fireEvent.keyDown(window, { key: "ArrowRight" });
  expect(last().fen).toBe(depois);
  fireEvent.keyDown(window, { key: "Home" });
  expect(last().fen).toBe(START);
});

test("clicar num lance da árvore vai para a posição dele", () => {
  renderBoard();
  play("e2e4");
  play("e7e5");
  const depois = last().fen;
  fireEvent.click(screen.getByText(/^1\. e4$/));
  expect(last().fen).not.toBe(depois);
});

test("a caixa de comentário só aparece no modo edição e guarda no nó atual", () => {
  const semEdicao = renderBoard();
  expect(screen.queryByLabelText("Comentário")).toBe(null);
  semEdicao.unmount();

  const { onTreeChange } = renderBoard({ editable: true });
  play("e2e4");
  const caixa = screen.getByLabelText("Comentário");
  fireEvent.change(caixa, { target: { value: "avanço central" } });
  const t = lastTree(onTreeChange);
  const id = t.root.children[0].id;
  expect(findNode(t, id)!.comment).toBe("avanço central");
});

test("Ctrl+S dispara onSave", () => {
  const { onSave } = renderBoard({ editable: true });
  fireEvent.keyDown(window, { key: "s", ctrlKey: true });
  expect(onSave).toHaveBeenCalled();
});

test("a linha do motor entra como variação", async () => {
  const { container, onTreeChange } = renderBoard();
  const botao = await screen.findByText("adicionar como variação");
  fireEvent.click(botao);
  await waitFor(() => expect(container.textContent).toMatch(/2\. Nf3/));
  const t = lastTree(onTreeChange);
  expect(t.root.children[0].san).toBe("e4");
  expect(t.root.children[0].children[0].children[0].san).toBe("Nf3");
});

test("clicar na linha do motor joga só o primeiro lance", async () => {
  const { onTreeChange } = renderBoard();
  fireEvent.click(await screen.findByRole("button", { name: /\+0\.30 e4 e5 Nf3/ }));
  const t = lastTree(onTreeChange);
  expect(t.root.children[0].san).toBe("e4");
  expect(t.root.children[0].children).toEqual([]);
});

test("mostra o link Voltar quando recebe backTo", () => {
  renderBoard({ backTo: "/erros" });
  expect(screen.getByText("Voltar").getAttribute("href")).toBe("/erros");
});

// --- vaivém da árvore com o pai ----------------------------------------

/** Pai que guarda a árvore e devolve ela pelo `tree` (como o editor de capítulo). */
function Pai({ inicial }: { inicial: Tree }) {
  const [t, setT] = useState(inicial);
  return <AnalysisBoard editable tree={t} onTreeChange={setT} />;
}

/** Renderiza com os provedores e deixa trocar as props sem remontar. */
function comProvedores(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const envolver = (n: ReactNode) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>{n}</MemoryRouter>
    </QueryClientProvider>
  );
  const r = render(envolver(node));
  return { ...r, trocar: (n: ReactNode) => r.rerender(envolver(n)) };
}

test("a árvore que volta do pai não reinicia a navegação", () => {
  comProvedores(<Pai inicial={emptyTree(START)} />);
  play("e2e4");
  play("e7e5");
  const fen = last().fen;

  fireEvent.change(screen.getByLabelText("Comentário"), { target: { value: "simétrico" } });
  expect(last().fen).toBe(fen);
  expect(screen.getByText("e5").getAttribute("aria-current")).toBe("true");
});

test("uma árvore de fora sem o lance atual volta ao começo", () => {
  const { trocar } = comProvedores(<AnalysisBoard editable tree={emptyTree(START)} />);
  play("e2e4");
  expect(last().fen).not.toBe(START);

  const outra = emptyTree("8/8/8/8/8/8/8/K6k w - - 0 1");
  trocar(<AnalysisBoard editable tree={outra} />);
  expect(last().fen).toBe(outra.fen);
});

test("uma árvore de fora com o mesmo caminho mantém o lance atual", () => {
  const { trocar } = comProvedores(<AnalysisBoard editable tree={emptyTree(START)} />);
  play("e2e4");
  const fen = last().fen;

  // mesma linha, outro enunciado (é o que o editor manda ao salvar): o lance fica
  const mesma = insertLine(emptyTree(START), null, ["e2e4"]).tree;
  trocar(<AnalysisBoard editable tree={{ ...mesma, intro: "novo enunciado" }} />);
  expect(last().fen).toBe(fen);
  expect(screen.getByText(/^1\. e4$/).getAttribute("aria-current")).toBe("true");
});

// --- menu do lance ------------------------------------------------------

test("o menu do lance promove, marca NAG e apaga", () => {
  const { onTreeChange } = renderBoard({ editable: true });
  play("e2e4");
  fireEvent.keyDown(window, { key: "Home" });
  play("d2d4");

  // depois do NAG o texto do lance vira "1. d4!": o nome casa pelo começo
  const abrir = () => fireEvent.contextMenu(screen.getByRole("button", { name: /^1\. d4/ }), { clientX: 20, clientY: 20 });

  abrir();
  fireEvent.click(screen.getByRole("menuitem", { name: "Promover a linha principal" }));
  expect(lastTree(onTreeChange).root.children[0].san).toBe("d4");

  abrir();
  fireEvent.click(screen.getByRole("menuitem", { name: "marcar !" }));
  expect(lastTree(onTreeChange).root.children[0].nags).toEqual([1]);

  abrir();
  fireEvent.click(screen.getByRole("menuitem", { name: "Apagar daqui" }));
  expect(lastTree(onTreeChange).root.children.map((n) => n.san)).toEqual(["e4"]);
});

test("no modo edição a seta do motor é azul (o verde fica para as marcações do autor)", async () => {
  const semEdicao = renderBoard();
  await waitFor(() => expect(last().arrows?.[0]?.brush).toBe("green"));
  semEdicao.unmount();

  renderBoard({ editable: true });
  await waitFor(() => expect(last().arrows?.[0]?.brush).toBe("blue"));
});

// --- modo leitura: comentários do autor --------------------------------

/** Comentário mais longo que o corte da árvore (80 caracteres). */
const LONGO =
  "As brancas seguram o peão passado com a torre atrás dele e só então avançam o rei pela coluna livre.";

/** Árvore com enunciado e um comentário longo no primeiro lance. */
function comComentarios(): Tree {
  const base = insertLine(emptyTree(START), null, ["e2e4"]).tree;
  const com = setComment(base, base.root.children[0].id, LONGO);
  return { ...com, intro: "Brancas jogam e ganham." };
}

test("no modo leitura o enunciado e o comentário do lance aparecem inteiros", () => {
  comProvedores(<AnalysisBoard tree={comComentarios()} />);
  // na posição inicial o cartão traz o enunciado
  expect(screen.getByText("Brancas jogam e ganham.")).toBeTruthy();

  fireEvent.click(screen.getByText(/^1\. e4$/));
  // a árvore corta o comentário em 80 caracteres; o cartão mostra o texto todo
  expect(screen.getByText(LONGO)).toBeTruthy();
  expect(screen.getByText("Comentário de e4")).toBeTruthy();
  expect(screen.queryByText("Brancas jogam e ganham.")).toBeNull();
});

test("sem comentário nenhum o modo leitura não mostra o cartão", () => {
  comProvedores(<AnalysisBoard tree={emptyTree(START)} />);
  expect(screen.queryByText("Enunciado")).toBeNull();
});

test("no modo edição o cartão de leitura não aparece junto da caixa de edição", () => {
  comProvedores(<AnalysisBoard editable tree={comComentarios()} />);
  expect((screen.getByLabelText("Comentário") as HTMLTextAreaElement).value).toBe("Brancas jogam e ganham.");
  // só a caixa de edição traz o texto: nada de mostrar duas vezes
  expect(screen.getAllByText("Brancas jogam e ganham.").length).toBe(1);
  expect(screen.queryByText("Enunciado")).toBeNull();
  expect(screen.getByText("Enunciado (posição inicial)")).toBeTruthy();
});

test("com a árvore no limite, avisa em vez de deixar o lance sumir", () => {
  // árvore sintética larga: para o limite só a contagem de nós importa
  const cheia: Tree = {
    ...emptyTree(START),
    root: {
      children: Array.from({ length: MAX_NODES }, (_, i) => ({
        id: `n${i + 1}`, uci: "e2e4", san: "e4", comment: "", shapes: [], nags: [], children: [],
      })),
    },
  };
  comProvedores(<AnalysisBoard editable tree={cheia} />);
  expect(screen.getByText(/Limite de 2000 lances por capítulo/)).toBeTruthy();
});

test("árvore dentro do limite não mostra o aviso", () => {
  comProvedores(<AnalysisBoard editable tree={emptyTree(START)} />);
  expect(screen.queryByText(/Limite de 2000 lances/)).toBeNull();
});

// --- montar posição -----------------------------------------------------

test("montar posição troca a análise pela posição nova", () => {
  const { onTreeChange } = renderBoard();
  fireEvent.click(screen.getByRole("button", { name: "Montar posição" }));
  fireEvent.change(screen.getByLabelText("FEN"), { target: { value: "8/8/8/8/8/5k2/8/7K b - - 0 1" } });
  fireEvent.click(screen.getByRole("button", { name: "Usar posição" }));
  const t = lastTree(onTreeChange);
  expect(t.fen).toBe("8/8/8/8/8/5k2/8/7K b - - 0 1");
  expect(t.root.children).toEqual([]);
  // voltou ao tabuleiro de análise
  expect(screen.getByRole("button", { name: "Montar posição" })).toBeTruthy();
});

test("com lances na árvore, montar posição pede confirmação antes de apagar tudo", () => {
  const { onTreeChange } = renderBoard();
  play("e2e4");
  const confirmar = vi.spyOn(window, "confirm").mockReturnValue(false);
  fireEvent.click(screen.getByRole("button", { name: "Montar posição" }));
  fireEvent.change(screen.getByLabelText("FEN"), { target: { value: "8/8/8/8/8/5k2/8/7K b - - 0 1" } });
  fireEvent.click(screen.getByRole("button", { name: "Usar posição" }));
  expect(confirmar).toHaveBeenCalledWith("Substituir a análise atual pela nova posição?");
  // recusou: a análise continua de pé e o editor fica aberto
  expect(lastTree(onTreeChange).root.children[0].san).toBe("e4");

  confirmar.mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "Usar posição" }));
  expect(lastTree(onTreeChange).fen).toBe("8/8/8/8/8/5k2/8/7K b - - 0 1");
  expect(lastTree(onTreeChange).root.children).toEqual([]);
});

test("cancelar a montagem não mexe na análise", () => {
  const { onTreeChange } = renderBoard();
  play("e2e4");
  const antes = lastTree(onTreeChange);
  fireEvent.click(screen.getByRole("button", { name: "Montar posição" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
  expect(screen.getByRole("button", { name: "Montar posição" })).toBeTruthy();
  expect(lastTree(onTreeChange)).toBe(antes);
});

// --- abas do painel lateral --------------------------------------------

test("o painel abre na aba Engine e a aba Aberturas mostra o livro", async () => {
  renderBoard();
  const engine = screen.getByRole("tab", { name: "Engine" });
  const abertura = screen.getByRole("tab", { name: "Aberturas" });
  expect(engine.getAttribute("aria-selected")).toBe("true");
  expect(abertura.getAttribute("aria-selected")).toBe("false");
  // a engine continua como era: avaliação e linhas
  expect(await screen.findByRole("button", { name: /\+0\.30 e4 e5 Nf3/ })).toBeTruthy();

  fireEvent.click(abertura);
  expect(abertura.getAttribute("aria-selected")).toBe("true");
  expect(await screen.findByText("A00 · Posição inicial")).toBeTruthy();
  // sem a engine na tela, mas a árvore de lances continua
  expect(screen.queryByText("adicionar como variação")).toBeNull();
  expect(localStorage.getItem("analysis.sidePanel")).toBe('"aberturas"');
});

test("clicar num lance do livro joga ele na árvore", async () => {
  const { onTreeChange } = renderBoard();
  fireEvent.click(screen.getByRole("tab", { name: "Aberturas" }));
  fireEvent.click(await screen.findByRole("button", { name: "e4" }));
  expect(lastTree(onTreeChange).root.children[0].san).toBe("e4");
});

test("a aba escolhida volta na próxima abertura do tabuleiro", async () => {
  localStorage.setItem("analysis.sidePanel", '"aberturas"');
  renderBoard();
  expect(screen.getByRole("tab", { name: "Aberturas" }).getAttribute("aria-selected")).toBe("true");
  expect(await screen.findByText("A00 · Posição inicial")).toBeTruthy();
});

test("com o editor de posição aberto, as setas não navegam a árvore escondida", () => {
  const { onTreeChange } = renderBoard();
  play("e2e4");
  play("e7e5");
  const antes = onTreeChange.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Montar posição" }));
  fireEvent.keyDown(window, { key: "ArrowLeft" });
  fireEvent.keyDown(window, { key: "Home" });
  // nenhuma mutação/navegação chega ao pai enquanto o editor está aberto
  expect(onTreeChange.mock.calls.length).toBe(antes);
  fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
  // voltou no mesmo lance em que estava (e5 continua o lance atual)
  expect(screen.getByText("e5").closest("[aria-current]")?.getAttribute("aria-current")).toBe("true");
});

// --- classificação dos lances ------------------------------------------

/** Melhor lance de cada posição do teste, para o dublê da engine. */
const melhorDe = (fen: string) =>
  fen === START ? "e2e4" : fen.split(" ")[1] === "b" ? "e7e5" : "g1f3";

/** Engine que responde conforme a FEN pedida (o dublê padrão devolve sempre a inicial). */
function engineDeVerdade() {
  return vi.spyOn(api, "analyse").mockImplementation(async (fen: string) => {
    const move = melhorDe(fen);
    return {
      fen,
      turn: fen.split(" ")[1] === "b" ? "black" : "white",
      terminal: null,
      lines: [{ move, san: move, score: 30, pv: [move], pv_san: [move] }],
    } as AnalyseOut;
  });
}

/** Análise com dois lances na linha principal, para haver o que classificar. */
const comLinha = () => insertLine(emptyTree(START), null, ["e2e4", "e7e5"]).tree;

test("com a classificação ligada, os lances ganham selo na árvore e no tabuleiro", async () => {
  vi.spyOn(api, "settings").mockResolvedValue({ ...SETTINGS, classify_moves: true });
  engineDeVerdade();
  const { container } = comProvedores(<AnalysisBoard tree={comLinha()} />);
  fireEvent.click(screen.getByText("e5"));

  await waitFor(() => expect(last().badge).toBeTruthy());
  // e5 é o melhor lance da engine ali: selo sobre a casa de destino
  expect(last().badge).toEqual({ square: "e5", text: "★", className: "class-melhor" });
  // um selo por lance do caminho, na árvore
  await waitFor(() => expect(container.querySelectorAll(".tree .class").length).toBe(1));
  const selo = container.querySelector(".tree .class") as HTMLElement;
  expect(selo.getAttribute("title")).toBe("melhor");
  expect(selo.className).toContain("class-melhor");
  // e4 está no livro de mestres: lá o símbolo do livro vence a classificação
  const lances = container.querySelectorAll(".tree .move");
  expect(lances[0].querySelector(".book")).toBeTruthy();
  expect(lances[0].querySelector(".class")).toBeNull();
  // a perda vai negada na linha do cabeçalho
  expect(container.textContent).toMatch(/lance: melhor \(-0\.60\)/);
});

test("com a classificação desligada, a engine só é consultada para a posição na tela", async () => {
  vi.spyOn(api, "settings").mockResolvedValue({ ...SETTINGS, classify_moves: false });
  engineDeVerdade();
  const arvore = comLinha();
  const fenE4 = fenAt(arvore, arvore.root.children[0].id);
  const fenE5 = fenAt(arvore, arvore.root.children[0].children[0].id);

  const { container } = comProvedores(<AnalysisBoard tree={arvore} />);
  fireEvent.click(screen.getByText("e5"));
  // a engine do painel acompanha a posição na tela
  await waitFor(() => expect(vi.mocked(api.analyse).mock.calls.some((c) => c[0] === fenE5)).toBe(true));

  // a posição intermediária só interessaria à classificação
  expect(vi.mocked(api.analyse).mock.calls.some((c) => c[0] === fenE4)).toBe(false);
  expect(last().badge).toBeUndefined();
  expect(container.querySelectorAll(".class").length).toBe(0);
  expect(container.textContent).not.toMatch(/lance:/);
});

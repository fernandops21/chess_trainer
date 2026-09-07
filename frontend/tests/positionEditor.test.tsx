import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { Key } from "chessground/types";
import type { BoardProps } from "../src/board/Board";

// O chessground não roda no jsdom: o dublê guarda o que o editor manda e
// devolve os retornos do modo montagem para o teste "clicar" no tabuleiro.
const { boardProps } = vi.hoisted(() => ({ boardProps: [] as Record<string, unknown>[] }));
vi.mock("../src/board/Board", () => ({
  Board: (p: Record<string, unknown>) => {
    boardProps.push(p);
    return <div data-testid="board" />;
  },
}));

import { PositionEditor } from "../src/analysis/PositionEditor";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const REIS = "4k3/8/8/8/8/8/8/4K3 w - - 0 1";

const last = () => boardProps.at(-1) as unknown as BoardProps;
const clicar = (key: string) => act(() => { last().editor!.onSquareClick(key as Key); });
const arrastar = (placement: string) => act(() => { last().editor!.onChange(placement); });
const campoFen = () => screen.getByLabelText("FEN") as HTMLInputElement;
const fen = () => campoFen().value;
const botao = (nome: string) => screen.getByRole("button", { name: nome });

function montar(initialFen = REIS) {
  const onUse = vi.fn();
  const onCancel = vi.fn();
  const r = render(<PositionEditor initialFen={initialFen} onUse={onUse} onCancel={onCancel} />);
  return { ...r, onUse, onCancel };
}

beforeEach(() => {
  boardProps.length = 0;
});

test("escolher uma peça na paleta e clicar numa casa coloca a peça", () => {
  montar();
  const dama = botao("Dama branca");
  fireEvent.click(dama);
  expect(dama.getAttribute("aria-pressed")).toBe("true");
  clicar("d4");
  expect(fen()).toBe("4k3/8/8/8/3Q4/8/8/4K3 w - - 0 1");
  // a peça escolhida continua: dá para preencher várias casas seguidas
  clicar("d5");
  expect(fen()).toBe("4k3/8/8/3Q4/3Q4/8/8/4K3 w - - 0 1");
});

test("clicar de novo na mesma peça da paleta desmarca e o clique no tabuleiro não faz nada", () => {
  montar();
  const dama = botao("Dama branca");
  fireEvent.click(dama);
  fireEvent.click(dama);
  expect(dama.getAttribute("aria-pressed")).toBe("false");
  clicar("d4");
  expect(fen()).toBe(REIS);
});

test("Apagar tira a peça da casa clicada", () => {
  montar("4k3/8/8/8/3Q4/8/8/4K3 w - - 0 1");
  fireEvent.click(botao("Apagar"));
  clicar("d4");
  expect(fen()).toBe(REIS);
});

test("arrastar peças no tabuleiro atualiza a FEN", () => {
  montar();
  // o chessground devolve só a parte das peças
  arrastar("8/8/8/8/8/8/8/K6k");
  expect(fen()).toBe("8/8/8/8/8/8/8/K6k w - - 0 1");
});

test("Usar posição manda a FEN montada", () => {
  const { onUse } = montar();
  fireEvent.click(botao("Dama branca"));
  clicar("d4");
  fireEvent.click(botao("Usar posição"));
  expect(onUse).toHaveBeenCalledWith("4k3/8/8/8/3Q4/8/8/4K3 w - - 0 1");
});

test("Cancelar volta sem mexer em nada", () => {
  const { onCancel, onUse } = montar();
  fireEvent.click(botao("Cancelar"));
  expect(onCancel).toHaveBeenCalled();
  expect(onUse).not.toHaveBeenCalled();
});

test("posição inválida lista o erro e desabilita Usar posição", () => {
  montar("4k3/8/8/8/8/8/8/8 w - - 0 1");
  expect(screen.getByText("Falta o rei branco.")).toBeTruthy();
  expect((botao("Usar posição") as HTMLButtonElement).disabled).toBe(true);
});

test("lado a jogar entra na FEN", () => {
  montar();
  fireEvent.change(screen.getByLabelText("Lado a jogar"), { target: { value: "black" } });
  expect(fen()).toBe("4k3/8/8/8/8/8/8/4K3 b - - 0 1");
});

test("FEN colada válida entra no tabuleiro; a inválida avisa e não muda a posição", () => {
  montar();
  const alvo = "4k3/8/8/8/8/8/4P3/4K3 b - - 0 1";
  fireEvent.change(campoFen(), { target: { value: alvo } });
  expect(last().fen).toBe(alvo);
  expect(screen.getByLabelText("Lado a jogar")).toHaveProperty("value", "black");

  fireEvent.change(campoFen(), { target: { value: "isso não é uma FEN" } });
  expect(screen.getByText("FEN inválido.")).toBeTruthy();
  // o tabuleiro ficou na última posição boa
  expect(last().fen).toBe(alvo);
});

test("roque só fica disponível com rei e torre nas casas de origem", () => {
  montar(START);
  const pequeno = screen.getByLabelText("Roque pequeno das brancas") as HTMLInputElement;
  expect(pequeno.checked).toBe(true);
  expect(pequeno.disabled).toBe(false);

  // tira a torre de h1: o roque pequeno das brancas some da FEN
  fireEvent.click(botao("Apagar"));
  clicar("h1");
  const depois = screen.getByLabelText("Roque pequeno das brancas") as HTMLInputElement;
  expect(depois.checked).toBe(false);
  expect(depois.disabled).toBe(true);
  expect(fen().split(" ")[2]).toBe("Qkq");
});

test("desmarcar um roque tira a letra da FEN", () => {
  montar(START);
  fireEvent.click(screen.getByLabelText("Roque grande das pretas"));
  expect(fen().split(" ")[2]).toBe("KQk");
});

test("Limpar esvazia e Posição inicial repõe o começo da partida", () => {
  montar();
  fireEvent.click(botao("Limpar"));
  expect(fen()).toBe("8/8/8/8/8/8/8/8 w - - 0 1");
  fireEvent.click(botao("Posição inicial"));
  expect(fen()).toBe(START);
});

test("Inverter troca o lado de baixo do tabuleiro", () => {
  montar();
  expect(last().orientation).toBe("white");
  fireEvent.click(botao("Inverter"));
  expect(last().orientation).toBe("black");
});

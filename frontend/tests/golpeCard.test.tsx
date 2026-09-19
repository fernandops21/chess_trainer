import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { IrmaosOut, Procedencia, TacticOut } from "../src/api/types";
import { BlocoProvider } from "../src/train/BlocoContext";
import { GolpeCard } from "../src/train/GolpeCard";

const tactic = (id: string, rating: number): TacticOut => ({ id, fen_start: "8/8/8/8/8/8/8/K6k w - - 0 1", side_to_move: "white", solution: { moves: [], explanation_pv: [] }, rating, themes: [], saved: false } as unknown as TacticOut);
const procedencia = (n: number): Procedencia => ({ degrau: "inteira", nivel: "destinos", n, posicao: "inteira", espelhado: false });
const irmaos: IrmaosOut = { assinatura: "Ke8 | Q xP f7 #", itens: [
  { tier: "mesmo", tactic: tactic("a", 800), procedencia: procedencia(1) },
  { tier: "mesmo", tactic: tactic("b", 900), procedencia: procedencia(2) },
] };

function montar(props: { errou: boolean }, iniciar = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <BlocoProvider value={{ iniciar }}><GolpeCard origem="own" id="p1" errou={props.errou} /></BlocoProvider>
    </QueryClientProvider>,
  );
  return iniciar;
}

beforeEach(() => vi.spyOn(api, "golpesIrmaos").mockResolvedValue(irmaos));
afterEach(() => vi.restoreAllMocks());

describe("GolpeCard", () => {
  it("erro: imagem e botão que abre o bloco com os irmãos", async () => {
    const iniciar = montar({ errou: true });
    expect(await screen.findByAltText("O golpe desenhado")).toHaveAttribute("src", "/api/golpes/own/p1/imagem.svg");
    await userEvent.click(screen.getByRole("button", { name: "Treinar 2 parecidos" }));
    expect(iniciar).toHaveBeenCalledWith({
      anchorId: "p1", anchorOrigem: "own", itens: irmaos.itens.map((i) => i.tactic),
      tiers: { a: "mesmo", b: "mesmo" },
      procedencias: { a: procedencia(1), b: procedencia(2) },
    });
  });
  it("acerto: só a imagem", async () => {
    montar({ errou: false });
    expect(await screen.findByAltText("O golpe desenhado")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /parecidos/ })).toBeNull();
  });
  it("com padrão de mate: mostra a linha em português", async () => {
    vi.spyOn(api, "golpesIrmaos").mockResolvedValue({ ...irmaos, padrao: "mate do corredor" });
    montar({ errou: false });
    expect(await screen.findByText("Padrão: mate do corredor")).toBeInTheDocument();
  });
  it("sem padrão de mate: não mostra a linha", async () => {
    montar({ errou: false });
    await screen.findByAltText("O golpe desenhado");
    expect(screen.queryByText(/^Padrão:/)).toBeNull();
  });
  it("sem assinatura (404): nada", async () => {
    vi.spyOn(api, "golpesIrmaos").mockResolvedValue(null);
    const { container } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><GolpeCard origem="lichess" id="x" errou /></QueryClientProvider>,
    );
    await waitFor(() => expect(api.golpesIrmaos).toHaveBeenCalled());
    expect(container.querySelector("img")).toBeNull();
  });
  it("sem irmãos: o cartão não existe (spec §6)", async () => {
    vi.spyOn(api, "golpesIrmaos").mockResolvedValue({ assinatura: "Ke8 | Q xP f7 #", itens: [] });
    const { container } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><GolpeCard origem="lichess" id="x" errou /></QueryClientProvider>,
    );
    await waitFor(() => expect(api.golpesIrmaos).toHaveBeenCalled());
    // a resposta chega antes de checar: sem isto, a asserção passaria mesmo com o bug
    // (`itens: []` não distingue de "carregando" enquanto `data` ainda é `undefined`)
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector("img")).toBeNull();
  });
});

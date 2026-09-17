import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { GolpesStatus, RotulagemItem, RotulagemResumoLinha, TacticOut } from "../src/api/types";
import { RotulagemPage } from "../src/pages/RotulagemPage";

const status: GolpesStatus = { enabled: true, versao: 1, assinados: 6, total: 6, cobertura: null, rotulagem: true, trechos: 0 };
const t = (id: string): TacticOut => ({ id, fen_start: "8/8/8/8/8/8/8/K6k w - - 0 1" } as unknown as TacticOut);
const item: RotulagemItem = { anchor: { origem: "lichess", id: "p0", assinatura: "Ke8 | Q xP f7 #" },
                              candidatos: [
                                { id: "a", tier: "mesmo", procedencia: { degrau: "mesmo", nivel: "destinos", n: 1, posicao: "inteira", espelhado: false }, tactic: t("a") },
                                { id: "b", tier: "espelho", procedencia: { degrau: "espelho", nivel: "destinos_esp", n: 1, posicao: "inteira", espelhado: true }, tactic: t("b") },
                              ] };
const resumo: RotulagemResumoLinha[] = [
  { tier: "inteira", posicao: "inteira", n_lances: 1, mesmo: 3, parecido: 1, nada: 1, total: 5 },
];

function montar() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><RotulagemPage /></QueryClientProvider>);
}

beforeEach(() => {
  vi.spyOn(api, "golpesStatus").mockResolvedValue(status);
  vi.spyOn(api, "rotulagemProximo").mockResolvedValue(item);
  vi.spyOn(api, "rotulagemContagem").mockResolvedValue({ total: 3, por_label: { mesmo: 3 } });
  vi.spyOn(api, "rotulagemResumo").mockResolvedValue(resumo);
  vi.spyOn(api, "rotular").mockResolvedValue({});
});
afterEach(() => vi.restoreAllMocks());

describe("RotulagemPage", () => {
  it("mostra a âncora, os candidatos e grava o rótulo sem revelar a camada", async () => {
    montar();
    expect(await screen.findByText("Ke8 | Q xP f7 #")).toBeInTheDocument();
    expect(screen.getByText("3 rótulos")).toBeInTheDocument();
    expect(screen.queryByText(/espelho/)).toBeNull();
    const botoes = screen.getAllByRole("button", { name: "mesmo golpe" });
    expect(botoes).toHaveLength(2);
    await userEvent.click(botoes[0]);
    expect(api.rotular).toHaveBeenCalledWith({
      anchor_origem: "lichess", anchor_id: "p0", candidate_id: "a", tier: "mesmo", label: "mesmo",
      n_lances: 1, posicao: "inteira", nivel: "destinos", espelhado: false,
    });
    await waitFor(() => expect(screen.getAllByRole("button", { name: "mesmo golpe" })).toHaveLength(1));
  });

  it("mostra o placar por procedência embaixo do contador", async () => {
    montar();
    await screen.findByText("Ke8 | Q xP f7 #");
    const linhas = screen.getAllByText("inteira");
    expect(linhas.length).toBe(2); // colunas "degrau" e "posição"
    const linha = linhas[0].closest("tr");
    expect(linha).not.toBeNull();
    expect(linha!.textContent).toContain("5");
    expect(linha!.textContent).toContain("20%"); // 1 de 5 é "nada a ver"
  });
  it("quando os candidatos acabam, pede o próximo item", async () => {
    montar();
    await screen.findByText("Ke8 | Q xP f7 #");
    await userEvent.click(screen.getAllByRole("button", { name: "nada a ver" })[0]);
    await userEvent.click(screen.getAllByRole("button", { name: "nada a ver" })[0]);
    await waitFor(() => expect(api.rotulagemProximo).toHaveBeenCalledTimes(2));
  });
  it("quando a consulta ao status falha, avisa em vez de ficar em branco (achado 9)", async () => {
    vi.spyOn(api, "golpesStatus").mockRejectedValue(new Error("falha de rede"));
    montar();
    expect(await screen.findByText(/Não consegui consultar o servidor\./)).toBeInTheDocument();
    expect(screen.getByText(/falha de rede/)).toBeInTheDocument();
  });

  it("desligada: explica como ligar", async () => {
    vi.spyOn(api, "golpesStatus").mockResolvedValue({ ...status, rotulagem: false });
    montar();
    expect(await screen.findByText(/CHESS_TRAINER_ROTULAGEM=1/)).toBeInTheDocument();
    expect(api.rotulagemProximo).not.toHaveBeenCalled();
  });
  it("sem mais nada para rotular, mostra a mensagem de fim de fila", async () => {
    vi.spyOn(api, "rotulagemProximo").mockResolvedValue(null);
    montar();
    expect(await screen.findByText("Nada para rotular.")).toBeInTheDocument();
  });
  it("quando a busca do próximo item falha, mostra o erro e permite tentar de novo", async () => {
    vi.spyOn(api, "rotulagemProximo").mockRejectedValue(new Error("falha de rede"));
    montar();
    expect(await screen.findByText(/Não consegui buscar o próximo item\./)).toBeInTheDocument();
    expect(screen.getByText(/falha de rede/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
    expect(screen.queryByText("Nada para rotular.")).toBeNull();
  });
  it("quando gravar o rótulo falha, mantém o candidato e avisa; a próxima gravação some com o aviso", async () => {
    vi.spyOn(api, "rotular").mockRejectedValueOnce(new Error("erro de rede")).mockResolvedValueOnce({});
    montar();
    await screen.findByText("Ke8 | Q xP f7 #");
    await userEvent.click(screen.getAllByRole("button", { name: "mesmo golpe" })[0]);
    expect(await screen.findByText(/Não consegui gravar o rótulo; tente de novo\./)).toBeInTheDocument();
    expect(screen.getByText(/erro de rede/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "mesmo golpe" })).toHaveLength(2);
    await userEvent.click(screen.getAllByRole("button", { name: "mesmo golpe" })[0]);
    await waitFor(() => expect(screen.getAllByRole("button", { name: "mesmo golpe" })).toHaveLength(1));
    expect(screen.queryByText(/Não consegui gravar o rótulo/)).toBeNull();
  });
});

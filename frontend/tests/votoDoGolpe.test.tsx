import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { Procedencia } from "../src/api/types";
import { VotoDoGolpe } from "../src/train/VotoDoGolpe";

const procedencia: Procedencia = { degrau: "trecho2", nivel: "destinos", n: 2, posicao: "fim", espelhado: false };

function montar(over: Partial<{ anchorOrigem: "own" | "lichess"; anchorId: string; candidateId: string; onVotado: () => void }> = {}) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <VotoDoGolpe anchorOrigem="own" anchorId="p1" candidateId="c1" procedencia={procedencia} tier="trecho2" {...over} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "golpeVoto").mockResolvedValue({ label: null });
  vi.spyOn(api, "votarGolpe").mockResolvedValue({ ok: true, label: "mesmo" });
});
afterEach(() => vi.restoreAllMocks());

describe("VotoDoGolpe", () => {
  it("mostra a pergunta e os três botões, sem revelar a tier", async () => {
    montar();
    expect(await screen.findByText("Tem a ver com o seu erro?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "mesmo golpe" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "parecido" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "nada a ver" })).toBeInTheDocument();
    expect(screen.queryByText("trecho2")).toBeNull();
    expect(screen.queryByText(/trecho2/)).toBeNull();
  });

  it("clicar grava o voto com a procedência completa", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "mesmo golpe" }));
    expect(api.votarGolpe).toHaveBeenCalledWith({
      anchor_origem: "own", anchor_id: "p1", candidate_id: "c1", tier: "trecho2", label: "mesmo",
      n_lances: 2, posicao: "fim", nivel: "destinos", espelhado: false,
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "mesmo golpe" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "mesmo golpe" }).className).toContain("primary");
  });

  it("um voto já gravado vem pré-marcado", async () => {
    vi.spyOn(api, "golpeVoto").mockResolvedValue({ label: "parecido" });
    montar();
    await waitFor(() => expect(screen.getByRole("button", { name: "parecido" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "mesmo golpe" })).toHaveAttribute("aria-pressed", "false");
  });

  it("clicar noutro botão troca o voto", async () => {
    vi.spyOn(api, "golpeVoto").mockResolvedValue({ label: "parecido" });
    vi.spyOn(api, "votarGolpe").mockResolvedValue({ ok: true, label: "nada" });
    montar();
    await waitFor(() => expect(screen.getByRole("button", { name: "parecido" })).toHaveAttribute("aria-pressed", "true"));
    await userEvent.click(screen.getByRole("button", { name: "nada a ver" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "nada a ver" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "parecido" })).toHaveAttribute("aria-pressed", "false");
  });

  it("um POST que falha mostra o aviso e mantém a marca anterior", async () => {
    vi.spyOn(api, "golpeVoto").mockResolvedValue({ label: "mesmo" });
    vi.spyOn(api, "votarGolpe").mockRejectedValue(new Error("sem conexão"));
    montar();
    await waitFor(() => expect(screen.getByRole("button", { name: "mesmo golpe" })).toHaveAttribute("aria-pressed", "true"));
    await userEvent.click(screen.getByRole("button", { name: "nada a ver" }));
    expect(await screen.findByText("Não consegui gravar o voto.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "mesmo golpe" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "nada a ver" })).toHaveAttribute("aria-pressed", "false");
  });
  it("votar avança: com o voto gravado chama onVotado (votei, já vai para o próximo)", async () => {
    const onVotado = vi.fn();
    montar({ onVotado });
    await userEvent.click(screen.getByRole("button", { name: "parecido" }));
    await waitFor(() => expect(onVotado).toHaveBeenCalledTimes(1));
    expect(api.votarGolpe).toHaveBeenCalledTimes(1);
  });
  it("voto que não gravou não avança", async () => {
    vi.spyOn(api, "votarGolpe").mockRejectedValue(new Error("sem conexão"));
    const onVotado = vi.fn();
    montar({ onVotado });
    await userEvent.click(screen.getByRole("button", { name: "nada a ver" }));
    expect(await screen.findByText("Não consegui gravar o voto.")).toBeInTheDocument();
    expect(onVotado).not.toHaveBeenCalled();
  });
});

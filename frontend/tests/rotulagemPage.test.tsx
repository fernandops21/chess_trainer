import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { GolpesStatus, RotulagemItem, TacticOut } from "../src/api/types";
import { RotulagemPage } from "../src/pages/RotulagemPage";

const status: GolpesStatus = { enabled: true, versao: 1, assinados: 6, total: 6, cobertura: null, rotulagem: true };
const t = (id: string): TacticOut => ({ id, fen_start: "8/8/8/8/8/8/8/K6k w - - 0 1" } as unknown as TacticOut);
const item: RotulagemItem = { anchor: { origem: "lichess", id: "p0", assinatura: "Ke8 | Q xP f7 #" },
                              candidatos: [{ id: "a", tier: "mesmo", tactic: t("a") }, { id: "b", tier: "espelho", tactic: t("b") }] };

function montar() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><RotulagemPage /></QueryClientProvider>);
}

beforeEach(() => {
  vi.spyOn(api, "golpesStatus").mockResolvedValue(status);
  vi.spyOn(api, "rotulagemProximo").mockResolvedValue(item);
  vi.spyOn(api, "rotulagemContagem").mockResolvedValue({ total: 3, por_label: { mesmo: 3 } });
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
    expect(api.rotular).toHaveBeenCalledWith({ anchor_origem: "lichess", anchor_id: "p0", candidate_id: "a", tier: "mesmo", label: "mesmo" });
    await waitFor(() => expect(screen.getAllByRole("button", { name: "mesmo golpe" })).toHaveLength(1));
  });
  it("quando os candidatos acabam, pede o próximo item", async () => {
    montar();
    await screen.findByText("Ke8 | Q xP f7 #");
    await userEvent.click(screen.getAllByRole("button", { name: "nada a ver" })[0]);
    await userEvent.click(screen.getAllByRole("button", { name: "nada a ver" })[0]);
    await waitFor(() => expect(api.rotulagemProximo).toHaveBeenCalledTimes(2));
  });
  it("desligada: explica como ligar", async () => {
    vi.spyOn(api, "golpesStatus").mockResolvedValue({ ...status, rotulagem: false });
    montar();
    expect(await screen.findByText(/CHESS_TRAINER_ROTULAGEM=1/)).toBeInTheDocument();
    expect(api.rotulagemProximo).not.toHaveBeenCalled();
  });
});

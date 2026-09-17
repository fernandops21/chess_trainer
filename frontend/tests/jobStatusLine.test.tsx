import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { JobStatus, StatusOut } from "../src/api/types";
import { JobStatusLine } from "../src/components/JobStatusLine";

const job = (over: Partial<JobStatus>): JobStatus => ({
  state: "idle", job: null, stage: "", done: 0, total: 0, message: "", error: null, finished_at: null, cancel_requested: false, ...over,
});

function montar(j: JobStatus) {
  const status: StatusOut = {
    engine: { available: true, path: "stockfish" }, job: j,
    games_total: 0, games_pending: 0, last_import_at: null, local_url: "http://192.168.0.2:8000",
  };
  vi.spyOn(api, "status").mockResolvedValue(status);
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <JobStatusLine job="golpes_preparar" />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

test("rodando: o contador diz que o clique funcionou e quanto já foi", async () => {
  montar(job({ state: "running", job: "golpes_preparar", done: 400000, total: 1056428, message: "400000/1056428 puzzles" }));
  expect(await screen.findByText("Em andamento: 400.000 de 1.056.428")).toBeInTheDocument();
});

test("rodando sem total conhecido: mostra a mensagem da tarefa", async () => {
  montar(job({ state: "running", job: "golpes_preparar", message: "contando" }));
  expect(await screen.findByText("Em andamento: contando")).toBeInTheDocument();
});

test("cancelamento pedido: diz que está cancelando", async () => {
  montar(job({ state: "running", job: "golpes_preparar", done: 10, total: 20, cancel_requested: true }));
  expect(await screen.findByText("Cancelando… 10 de 20")).toBeInTheDocument();
});

test("outra tarefa rodando: explica por que o botão está desabilitado", async () => {
  montar(job({ state: "running", job: "import_lichess", message: "lendo" }));
  expect(await screen.findByText("Outra tarefa em andamento: Importação das táticas do Lichess")).toBeInTheDocument();
});

test("terminou: a última mensagem fica visível", async () => {
  montar(job({ state: "idle", job: "golpes_preparar", done: 1056428, total: 1056428, message: "concluído" }));
  expect(await screen.findByText("Última vez: concluído")).toBeInTheDocument();
});

test("falhou: mostra o erro", async () => {
  montar(job({ state: "error", job: "golpes_preparar", error: "disco cheio" }));
  expect(await screen.findByText("Falhou: disco cheio")).toBeInTheDocument();
});

test("parado e a última tarefa foi outra: nada aparece", async () => {
  const { container } = montar(job({ state: "idle", job: "analyze", message: "ok" }));
  await vi.waitFor(() => expect(api.status).toHaveBeenCalled());
  expect(container.textContent).toBe("");
});

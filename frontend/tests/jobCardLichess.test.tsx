import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { JobCard } from "../src/components/JobCard";

vi.mock("../src/api/queries", () => ({
  useStatus: () => ({
    data: {
      engine: { available: true, path: null },
      job: {
        state: "running",
        job: "import_lichess",
        stage: "import",
        done: 0,
        total: 0,
        message: "1.250.000 linhas lidas · 200.000 táticas novas",
        error: null,
        finished_at: null,
        cancel_requested: false,
      },
      games_total: 0,
      games_pending: 0,
      last_import_at: null,
      local_url: "",
    },
  }),
  useStartJob: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useCancelJob: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}));

test("importação das táticas: barra indeterminada, mensagem e cancelar por lote", () => {
  const { container } = render(<JobCard />);
  expect(screen.getByText(/Importação das táticas do Lichess/)).toBeTruthy();
  expect(screen.getByText(/baixa o banco \(~300 MB\)/)).toBeTruthy();
  expect(screen.getByText(/1\.250\.000 linhas lidas · 200\.000 táticas novas/)).toBeTruthy();
  expect(screen.queryByText(/0\/0/)).toBeNull();
  const bar = container.querySelector("progress") as HTMLProgressElement;
  expect(bar.hasAttribute("value")).toBe(false);
  expect(screen.getByRole("button", { name: "Cancelar (após o lote atual)" })).toBeTruthy();
});

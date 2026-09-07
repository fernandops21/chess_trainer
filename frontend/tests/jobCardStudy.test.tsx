import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { JobCard } from "../src/components/JobCard";

vi.mock("../src/api/queries", () => ({
  useStatus: () => ({
    data: {
      engine: { available: true, path: null },
      job: {
        state: "running",
        job: "import_study",
        stage: "import",
        done: 2,
        total: 5,
        message: "2/5 capítulos",
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

test("importação de estudo: nome da tarefa, dica e progresso por capítulo", () => {
  render(<JobCard />);
  expect(screen.getByText(/Importação de estudo do Lichess/)).toBeTruthy();
  expect(screen.getByText(/baixa o PGN do estudo e cria um exercício por capítulo/)).toBeTruthy();
  expect(screen.getByText(/2\/5 capítulos/)).toBeTruthy();
});

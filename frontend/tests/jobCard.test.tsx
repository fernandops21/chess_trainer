import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { JobCard } from "../src/components/JobCard";

vi.mock("../src/api/queries", () => ({
  useStatus: () => ({
    data: {
      engine: { available: true, path: null },
      job: {
        state: "running",
        job: "regenerate_avoid",
        stage: "puzzles",
        done: 1,
        total: 10,
        message: "",
        error: null,
        finished_at: null,
        cancel_requested: true,
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

test("mostra o rótulo do job 'evitar' e o botão desabilitado enquanto cancela", () => {
  render(<JobCard />);
  expect(screen.getByText(/Regeração dos puzzles evitar/)).toBeTruthy();
  const button = screen.getByRole("button", { name: /Cancelando/ }) as HTMLButtonElement;
  expect(button.textContent).toMatch(/Cancelando/);
  expect(button.disabled).toBe(true);
});

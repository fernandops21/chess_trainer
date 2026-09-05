import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "../src/App";

test("renderiza o esqueleto", () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter><App /></MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.getAllByText(/Chess Trainer/).length).toBeGreaterThan(0);
});

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { StudyOut, TacticsStatus } from "../src/api/types";
import { SessionStart } from "../src/train/SessionStart";

const STUDIES: StudyOut[] = [
  { id: "s1", title: "Finais de torre", author: "Basso", source_url: "https://lichess.org/study/aaa", lichess_id: "aaa", imported_at: null, chapter_count: 27, in_queue: 20, due_today: 3 },
  { id: "s2", title: "Aberturas", author: "Basso", source_url: "", lichess_id: null, imported_at: null, chapter_count: 4, in_queue: 4, due_today: 0 },
];

const status: TacticsStatus = {
  imported: true, count: 100, imported_at: null, source_rows: null, rating: 1200, window: 200,
  attempts_total: 0, attempts_today: 0, attempts_30d: 0, correct_30d: 0,
};

function renderStart(entry = "/treinar") {
  const onStart = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <SessionStart onStart={onStart} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onStart;
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(api, "tacticsStatus").mockResolvedValue(status);
  vi.spyOn(api, "tacticThemes").mockResolvedValue([]);
  vi.spyOn(api, "studies").mockResolvedValue(STUDIES);
});
afterEach(() => vi.restoreAllMocks());

test("sem nenhuma fonte marcada a sessão não filtra por fonte", () => {
  const onStart = renderStart();
  expect(screen.getByText("Meus erros")).toBeTruthy();
  expect(screen.getByText("Lichess guardados")).toBeTruthy();
  expect(screen.getByText("Estudos")).toBeTruthy();
  fireEvent.click(screen.getByText("Começar"));
  const cfg = onStart.mock.calls[0][0];
  expect(cfg.filters.sources).toBe(undefined);
  expect(cfg.filters.study_id).toBe(undefined);
});

test("chips escolhem as fontes e ficam guardados em train.sources", () => {
  const onStart = renderStart();
  fireEvent.click(screen.getByText("Meus erros"));
  fireEvent.click(screen.getByText("Lichess guardados"));
  expect(screen.getByText("Meus erros").getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(screen.getByText("Começar"));
  expect(onStart.mock.calls[0][0].filters.sources).toEqual(["own", "lichess"]);
  expect(localStorage.getItem("train.sources")).toBe(JSON.stringify(["own", "lichess"]));
});

test("marcar Estudos mostra o select e manda study_id", async () => {
  const onStart = renderStart();
  expect(screen.queryByLabelText("Estudo")).toBeNull();
  fireEvent.click(screen.getByText("Estudos"));
  await screen.findByText("Finais de torre");
  const select = screen.getByLabelText("Estudo") as HTMLSelectElement;
  fireEvent.change(select, { target: { value: "s2" } });
  fireEvent.click(screen.getByText("Começar"));
  expect(onStart.mock.calls[0][0].filters).toMatchObject({ sources: ["study"], study_id: "s2" });
});

test("?study=<id> já vem com Estudos marcado e o estudo escolhido", async () => {
  const onStart = renderStart("/treinar?study=s1");
  expect(screen.getByText("Estudos").getAttribute("aria-pressed")).toBe("true");
  await screen.findByText("Finais de torre");
  expect((screen.getByLabelText("Estudo") as HTMLSelectElement).value).toBe("s1");
  fireEvent.click(screen.getByText("Começar"));
  expect(onStart.mock.calls[0][0].filters).toMatchObject({ sources: ["study"], study_id: "s1" });
});

test("train.sources guardado antes volta marcado", () => {
  localStorage.setItem("train.sources", JSON.stringify(["lichess"]));
  renderStart();
  expect(screen.getByText("Lichess guardados").getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByText("Meus erros").getAttribute("aria-pressed")).toBe("false");
});

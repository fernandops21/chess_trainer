import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api/client";
import type { ChapterOut, StudyDetail } from "../src/api/types";
import { StudyDetailPage } from "../src/pages/StudyDetailPage";

const chapter = (over: Partial<ChapterOut> = {}): ChapterOut => ({
  id: "c1",
  order: 1,
  name: "Torre atrás do peão",
  lichess_url: "https://lichess.org/study/abc12345/cap00001",
  mode: "gamebook",
  in_queue: true,
  puzzle_id: "p1",
  intro_comment: "Brancas jogam e ganham.",
  ...over,
});

const detail = (over: Partial<StudyDetail> = {}): StudyDetail => ({
  id: "s1",
  title: "Finais de torre",
  author: "Mestre X",
  source_url: "https://lichess.org/study/abc12345",
  lichess_id: "abc12345",
  imported_at: "2026-09-01T10:00:00",
  chapter_count: 2,
  in_queue: 1,
  due_today: 0,
  chapters: [
    chapter(),
    chapter({ id: "c2", order: 2, name: "Ponte de Lucena", mode: "read", in_queue: false, puzzle_id: null, intro_comment: "" }),
  ],
  ...over,
});

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/estudos/s1"]}>
        <Routes>
          <Route path="/estudos/:id" element={<StudyDetailPage />} />
          <Route path="*" element={null} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "study").mockResolvedValue(detail());
});
afterEach(() => vi.restoreAllMocks());

test("mostra o cabeçalho com autor e o link do estudo no Lichess", async () => {
  renderPage();
  expect(await screen.findByText("Finais de torre")).toBeTruthy();
  expect(screen.getByText(/Mestre X/)).toBeTruthy();
  const links = screen.getAllByRole("link", { name: "ver no Lichess" });
  expect(links[0].getAttribute("href")).toBe("https://lichess.org/study/abc12345");
  expect(api.study).toHaveBeenCalledWith("s1");
});

test("lista os capítulos em ordem, com modo e enunciado", async () => {
  renderPage();
  expect(await screen.findByText("Torre atrás do peão")).toBeTruthy();
  expect(screen.getByText("Ponte de Lucena")).toBeTruthy();
  expect(screen.getByText("1.")).toBeTruthy();
  expect(screen.getByText("2.")).toBeTruthy();
  expect(screen.getByText("exercício")).toBeTruthy();
  expect(screen.getByText("leitura (sem exercício)")).toBeTruthy();
  expect(screen.getByText("Brancas jogam e ganham.")).toBeTruthy();
});

test("capítulo com exercício abre o treino daquele exercício; sem exercício não tem botão", async () => {
  renderPage();
  await screen.findByText("Torre atrás do peão");
  const treinar = screen.getAllByRole("button", { name: "Treinar este" });
  expect(treinar.length).toBe(1);
  fireEvent.click(treinar[0]);
  expect(screen.getByTestId("where").textContent).toBe("/treinar?puzzle=p1");
});

test("capítulo fora da repetição ganha a etiqueta", async () => {
  renderPage();
  await screen.findByText("Ponte de Lucena");
  expect(screen.getByText("fora da repetição")).toBeTruthy();
});

test("capítulo sem link no Lichess não mostra o link", async () => {
  vi.spyOn(api, "study").mockResolvedValue(
    detail({ source_url: "", lichess_id: null, chapters: [chapter({ lichess_url: null })] }),
  );
  renderPage();
  await screen.findByText("Torre atrás do peão");
  expect(screen.queryByRole("link", { name: "ver no Lichess" })).toBeNull();
});

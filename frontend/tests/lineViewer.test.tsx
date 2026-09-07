import { fireEvent, render, screen } from "@testing-library/react";

// só o `play` do módulo de som vira dublê
vi.mock("../src/lib/sound", async (original) => ({
  ...(await original<typeof import("../src/lib/sound")>()),
  play: vi.fn(),
}));

import { play } from "../src/lib/sound";
import { LineViewer } from "../src/train/LineViewer";

const fenStart = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1";
const ucis = ["e1e8", "c8e8", "a4e8"];

test("posição não reseta quando `ucis` é recriado com o mesmo conteúdo (ex.: relógio re-renderizando o pai)", () => {
  const { rerender } = render(
    <LineViewer fenStart={fenStart} ucis={ucis} orientation="white" startPly={1} />,
  );

  // len-1 = 3 (4 fens: inicial + 3 lances)
  expect(screen.getByText("3/3")).toBeTruthy();

  fireEvent.click(screen.getByLabelText("anterior"));
  expect(screen.getByText("2/3")).toBeTruthy();

  // Um pai que re-renderiza (ex.: a cada tick do relógio) tipicamente reconstrói `ucis`
  // com um novo array de mesmo conteúdo. Isso não deve resetar a posição.
  rerender(
    <LineViewer fenStart={fenStart} ucis={[...ucis]} orientation="white" startPly={1} />,
  );
  expect(screen.getByText("2/3")).toBeTruthy();
});

test("initialPos abre a linha na posição pedida", () => {
  render(
    <LineViewer fenStart="2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1" ucis={["e1e8", "c8e8", "a4e8"]} orientation="white" startPly={1} initialPos={1} keyboard={false} />,
  );
  expect(screen.getByText("1/3")).toBeTruthy();
});

// Último lance do adversário na linha do resultado: a posição 0 passa a ser a
// FEN de antes dele, e a numeração recua um meio-lance.
const fenBefore = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 24";
const fenAfter = "2r1R1k1/5ppp/8/8/Q7/8/8/6K1 b - - 1 24";
const startPly48 = 48; // pretas jogam o lance 24

test("sem `fenBefore` a linha começa no lance das pretas", () => {
  render(
    <LineViewer fenStart={fenAfter} ucis={["c8e8", "a4e8"]} orientation="white" startPly={startPly48} keyboard={false} />,
  );
  expect(screen.getByText(/^24… Rxe8$/)).toBeTruthy();
  expect(screen.getByText("2/2")).toBeTruthy();
});

test("com `fenBefore` o último lance do adversário abre a linha e a numeração recua", () => {
  render(
    <LineViewer fenStart={fenAfter} ucis={["c8e8", "a4e8"]} orientation="white" startPly={startPly48}
      fenBefore={fenBefore} lastMoveUci="e1e8" initialPos={2} keyboard={false} />,
  );
  // três lances mostrados: o do adversário (24. Re8+) e os dois da solução
  expect(screen.getByText(/^24\. Re8\+$/)).toBeTruthy();
  expect(screen.getByText("Rxe8")).toBeTruthy();
  expect(screen.getByText(/^25\. Qxe8#$/)).toBeTruthy();
  // initialPos vem relativo a `fenStart` (2 lances da solução) e é deslocado em +1
  expect(screen.getByText("3/3")).toBeTruthy();
});

test("`onPos` continua contando a partir de `fenStart` mesmo com `fenBefore`", () => {
  const seen: number[] = [];
  render(
    <LineViewer fenStart={fenAfter} ucis={["c8e8", "a4e8"]} orientation="white" startPly={startPly48}
      fenBefore={fenBefore} lastMoveUci="e1e8" initialPos={2} keyboard={false} onPos={(p) => seen.push(p)} />,
  );
  expect(seen.at(-1)).toBe(2);
  fireEvent.click(screen.getByLabelText("anterior"));
  expect(seen.at(-1)).toBe(1);
  fireEvent.click(screen.getByLabelText("anterior"));
  expect(seen.at(-1)).toBe(0); // posição de `fenStart`
  fireEvent.click(screen.getByLabelText("anterior"));
  expect(seen.at(-1)).toBe(-1); // posição de `fenBefore`, antes do lance do adversário
});

test("último lance incoerente com a linha guardada cai no comportamento de sempre", () => {
  // `a4a5` é legal na fen guardada, mas depois dele a linha da solução não é:
  // meia linha na tela seria pior do que começar em `fenStart`
  render(
    <LineViewer fenStart={fenAfter} ucis={["c8e8", "a4e8"]} orientation="white" startPly={startPly48}
      fenBefore={fenBefore} lastMoveUci="a4a5" keyboard={false} />,
  );
  expect(screen.getByText(/^24… Rxe8$/)).toBeTruthy();
  expect(screen.getByText("2/2")).toBeTruthy();
});

// --- sons ao navegar --------------------------------------------------------

const sons = () => vi.mocked(play).mock.calls.map((c) => c[0]);

test("avançar na linha toca o som do lance alcançado", () => {
  vi.mocked(play).mockClear();
  render(
    <LineViewer fenStart={fenStart} ucis={ucis} orientation="white" startPly={1} initialPos={0} keyboard={false} />,
  );
  expect(sons()).toEqual([]);

  fireEvent.click(screen.getByLabelText("próximo"));   // Re8+
  fireEvent.click(screen.getByLabelText("próximo"));   // Rxe8
  expect(sons()).toEqual(["check", "capture"]); // xeque tem prioridade, como no puzzle

  // voltar não toca nada
  fireEvent.click(screen.getByLabelText("anterior"));
  fireEvent.click(screen.getByLabelText("anterior"));
  expect(sons()).toEqual(["check", "capture"]); // xeque tem prioridade, como no puzzle

  // pular direto para um lance à frente também toca
  fireEvent.click(screen.getByText(/Qxe8#$/));
  expect(sons()).toEqual(["move", "capture", "capture"]);
});

test("sound={false} silencia a navegação", () => {
  vi.mocked(play).mockClear();
  render(
    <LineViewer fenStart={fenStart} ucis={ucis} orientation="white" startPly={1} initialPos={0} keyboard={false} sound={false} />,
  );
  fireEvent.click(screen.getByLabelText("próximo"));
  expect(sons()).toEqual([]);
});

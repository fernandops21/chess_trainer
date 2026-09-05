import { fireEvent, render, screen } from "@testing-library/react";
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

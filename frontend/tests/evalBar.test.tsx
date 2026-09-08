import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { EvalBar, fracaoBrancas } from "../src/analysis/EvalBar";

const altura = (c: HTMLElement) => (c.querySelector(".eval-bar__brancas") as HTMLElement).style.height;

test("igualdade fica no meio; vantagem branca sobe; mate enche a barra", () => {
  expect(fracaoBrancas(0)).toBeCloseTo(0.5, 5);
  expect(fracaoBrancas(300)).toBeGreaterThan(0.7);
  expect(fracaoBrancas(-300)).toBeLessThan(0.3);
  expect(fracaoBrancas(99_990)).toBe(1);
  expect(fracaoBrancas(-99_990)).toBe(0);
});

test("o score da engine é de quem joga: com as pretas a jogar o sinal inverte", () => {
  const brancas = render(<EvalBar score={200} turn="white" orientation="white" />);
  const pretas = render(<EvalBar score={200} turn="black" orientation="white" />);
  expect(parseFloat(altura(brancas.container))).toBeGreaterThan(50);
  expect(parseFloat(altura(pretas.container))).toBeLessThan(50);
  expect(pretas.container.querySelector(".eval-bar")?.getAttribute("aria-label")).toBe("avaliação -2.00");
});

test("mate na posição e orientação invertida", () => {
  const mate = render(<EvalBar score={null} turn="black" orientation="black" terminal="checkmate" />);
  expect(parseFloat(altura(mate.container))).toBe(100);
  expect(mate.container.querySelector(".eval-bar")?.className).toContain("eval-bar--invertida");
  expect(mate.container.textContent).toBe("1-0");
  const sem = render(<EvalBar score={undefined} turn="white" orientation="white" />);
  expect(parseFloat(altura(sem.container))).toBe(50);
  expect(sem.container.textContent).toBe("…");
});

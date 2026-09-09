import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { BarChart } from "../src/components/charts/BarChart";
import { LineChart } from "../src/components/charts/LineChart";

const PONTOS = [
  { label: "01/09/2026", value: 1500 },
  { label: "02/09/2026", value: 1532 },
  { label: "03/09/2026", value: 1520 },
];

const COLUNAS = [
  { label: "01/09", correct: 3, wrong: 1 },
  { label: "02/09", correct: 0, wrong: 2 },
  { label: "03/09", correct: 5, wrong: 0 },
];

test("LineChart desenha um ponto por valor e resume os dados no aria-label", () => {
  const { container } = render(<LineChart points={PONTOS} titulo="Rating de táticas" />);
  const svg = screen.getByRole("img");
  expect(svg.getAttribute("aria-label")).toBe(
    "Rating de táticas: 3 ponto(s), de 1500 a 1520, mínimo 1500 e máximo 1532.",
  );
  expect(container.querySelectorAll("[data-ponto]").length).toBe(3);
  expect(container.querySelectorAll("[data-linha]").length).toBe(1);
  // 5 marcas no eixo (4 intervalos), do mínimo ao máximo
  const eixo = [...container.querySelectorAll("text.grafico-eixo")].map((t) => t.textContent);
  expect(eixo).toEqual(["1500", "1508", "1516", "1524", "1532"]);
});

test("LineChart com um ponto só não repete a marca do eixo e some quando não há dados", () => {
  const { container } = render(<LineChart points={[PONTOS[0]]} titulo="Rating" unidade=" pontos" />);
  expect(container.querySelectorAll("[data-ponto]").length).toBe(1);
  expect(container.querySelectorAll("text.grafico-eixo").length).toBe(1);
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("máximo 1500 pontos");
  const vazio = render(<LineChart points={[]} titulo="Rating" />);
  expect(vazio.container.querySelector("svg")).toBeNull();
});

test("BarChart empilha certas e erradas por dia e resume os totais no aria-label", () => {
  const { container } = render(<BarChart bars={COLUNAS} titulo="Revisões por dia" />);
  expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
    "Revisões por dia: 3 dia(s), 8 certa(s) e 3 errada(s).",
  );
  expect(container.querySelectorAll("[data-barra]").length).toBe(3);
  expect(container.querySelectorAll("[data-certo]").length).toBe(3);
  expect(container.querySelectorAll("[data-errado]").length).toBe(3);
  // a coluna mais alta (5 revisões) chega ao topo da escala inteira de 0 a 8
  const certas = [...container.querySelectorAll("[data-certo]")].map((r) => Number(r.getAttribute("height")));
  expect(certas[1]).toBe(0);
  expect(certas[2]).toBeGreaterThan(certas[0]);
  const eixo = [...container.querySelectorAll("text.grafico-eixo")].map((t) => t.textContent);
  expect(eixo.slice(0, 5)).toEqual(["0", "2", "4", "6", "8"]);
});

test("BarChart sem colunas não desenha nada", () => {
  const { container } = render(<BarChart bars={[]} titulo="Revisões por dia" />);
  expect(container.querySelector("svg")).toBeNull();
});

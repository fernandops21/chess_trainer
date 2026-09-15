import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { CodeTag } from "../src/components/CodeTag";

const ID = "ff466803-9e8a-4a1e-8f2a-0b1c2d3e4f50";

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

test("a etiqueta mostra o código curto e copia o id inteiro", () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  render(<CodeTag id={ID} />);
  const tag = screen.getByTitle("clique para copiar");
  expect(tag.textContent).toBe("#ff466803");

  fireEvent.click(tag);
  expect(writeText).toHaveBeenCalledWith(ID);
  expect(screen.getByText("copiado")).toBeTruthy();
  // o código continua à vista ao lado do aviso
  expect(tag.textContent).toContain("#ff466803");

  // o aviso some sozinho depois de 1,5 s
  act(() => { vi.advanceTimersByTime(1600); });
  expect(screen.queryByText("copiado")).toBeNull();
});

test("sem área de transferência o clique não quebra", () => {
  vi.stubGlobal("navigator", { ...navigator, clipboard: undefined });
  render(<CodeTag id={ID} />);
  fireEvent.click(screen.getByTitle("clique para copiar"));
  expect(screen.getByText("copiado")).toBeTruthy();
});

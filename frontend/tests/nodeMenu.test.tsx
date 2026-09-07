import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { NodeMenu } from "../src/analysis/NodeMenu";

/** Tamanho do menu: no jsdom todo elemento mede zero. */
function medir(width: number, height: number) {
  const rect = vi
    .spyOn(Element.prototype, "getBoundingClientRect")
    .mockReturnValue({ width, height, top: 0, left: 0, right: width, bottom: height, x: 0, y: 0, toJSON: () => ({}) });
  return rect;
}

function janela(innerWidth: number, innerHeight: number) {
  Object.defineProperty(window, "innerWidth", { value: innerWidth, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: innerHeight, configurable: true });
}

function renderMenu(x: number, y: number) {
  const acoes = { onPromote: vi.fn(), onDelete: vi.fn(), onNag: vi.fn(), onClose: vi.fn() };
  render(<NodeMenu x={x} y={y} {...acoes} />);
  return acoes;
}

afterEach(() => {
  vi.restoreAllMocks();
  janela(1024, 768);
});

test("o menu não passa da borda da janela", () => {
  medir(200, 150);
  janela(400, 300);
  renderMenu(390, 290);
  const menu = screen.getByRole("menu");
  // 400 - 200 - 8 e 300 - 150 - 8
  expect(menu.style.left).toBe("192px");
  expect(menu.style.top).toBe("142px");
});

test("cabendo na janela, o menu abre onde foi o clique", () => {
  medir(200, 150);
  janela(1024, 768);
  renderMenu(300, 200);
  const menu = screen.getByRole("menu");
  expect(menu.style.left).toBe("300px");
  expect(menu.style.top).toBe("200px");
});

test("promover, apagar e NAG chamam a ação e fecham o menu", () => {
  // `onClose` é um dublê: o menu segue na tela e dá para clicar em tudo
  const acoes = renderMenu(10, 10);
  fireEvent.click(screen.getByRole("menuitem", { name: "Promover a linha principal" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Apagar daqui" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "marcar !" }));
  expect(acoes.onPromote).toHaveBeenCalled();
  expect(acoes.onDelete).toHaveBeenCalled();
  expect(acoes.onNag).toHaveBeenCalledWith(1);
  expect(acoes.onClose).toHaveBeenCalledTimes(3);
});

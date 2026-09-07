import { render } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { Key } from "chessground/types";

// O tabuleiro real do chessground não expõe a API para o teste; um dublê deixa
// checar o que o Board manda para ele (config e limpeza das marcações).
const { api } = vi.hoisted(() => ({
  api: { set: vi.fn(), setShapes: vi.fn(), destroy: vi.fn() },
}));
vi.mock("chessground", () => ({ Chessground: () => api }));

import { Board, toConfig } from "../src/board/Board";

const F1 = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1";
const F2 = "2r1R1k1/5ppp/8/8/Q7/8/8/6K1 b - - 1 1";

test("por padrão não dá para desenhar", () => {
  const cfg = toConfig({ fen: F1, orientation: "white" });
  expect(cfg.drawable?.enabled).toBe(false);
});

test("com `drawable` o botão direito desenha e o clique esquerdo apaga", () => {
  const cfg = toConfig({ fen: F1, orientation: "white", drawable: true });
  expect(cfg.drawable?.enabled).toBe(true);
  expect(cfg.drawable?.visible).toBe(true);
  expect(cfg.drawable?.eraseOnClick).toBe(true);
});

test("dica, setas e casas do autor viram autoShapes", () => {
  const cfg = toConfig({
    fen: F1,
    orientation: "white",
    highlight: ["c3" as Key],
    arrows: [{ orig: "e1" as Key, dest: "e8" as Key, brush: "blue" }],
    squares: [{ orig: "g8" as Key, brush: "red" }],
  });
  expect(cfg.drawable?.autoShapes).toEqual([
    { orig: "c3", brush: "green" },
    { orig: "e1", dest: "e8", brush: "blue" },
    { orig: "g8", brush: "red" },
  ]);
});

test("as marcações do usuário somem ao trocar de posição, mas não a cada re-render", () => {
  const { rerender } = render(<Board fen={F1} orientation="white" drawable />);
  api.set.mockClear();
  api.setShapes.mockClear();

  // re-render sem mudar a posição (ex.: tick do relógio do pai): não mexe nas marcações
  rerender(<Board fen={F1} orientation="white" drawable />);
  expect(api.setShapes).not.toHaveBeenCalled();
  expect(api.set.mock.calls[0][0].fen).toBeUndefined();

  // nova posição: as marcações do usuário são limpas (não persistem)
  rerender(<Board fen={F2} orientation="white" drawable />);
  expect(api.setShapes).toHaveBeenCalledWith([]);
  expect(api.set.mock.calls[1][0].fen).toBe(F2);
});

import { render } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Key } from "chessground/types";

// O tabuleiro real do chessground não expõe a API para o teste; um dublê deixa
// checar o que o Board manda para ele (config, marcações e o toque longo).
const { api } = vi.hoisted(() => ({
  api: {
    set: vi.fn(),
    // o chessground de verdade guarda o que recebe: o dublê precisa fazer o mesmo,
    // senão o toggle do toque longo nunca enxerga a marcação anterior
    setShapes: vi.fn((shapes: { orig: string; dest?: string; brush?: string }[]) => {
      api.state.drawable.shapes = shapes;
    }),
    destroy: vi.fn(),
    cancelMove: vi.fn(),
    getKeyAtDomPos: vi.fn(),
    getFen: vi.fn(() => "8/8/8/8/8/8/8/4K3"),
    state: { drawable: { shapes: [] as { orig: string; dest?: string; brush?: string }[] } },
  },
}));
vi.mock("chessground", () => ({ Chessground: () => api }));

import { Board, toConfig } from "../src/board/Board";

const F1 = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1";
const F2 = "2r1R1k1/5ppp/8/8/Q7/8/8/6K1 b - - 1 1";

/** Ponteiro grosso (celular) ou fino (mouse): o jsdom não traz `matchMedia`. */
function setPointer(coarse: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: coarse && query.includes("coarse"), media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

/** Evento de toque simplificado: o jsdom não constrói `TouchEvent` com pontos. */
function touch(type: string, points: { clientX: number; clientY: number }[]) {
  const ev = new Event(type, { bubbles: true, cancelable: true }) as Event & {
    touches: typeof points; changedTouches: typeof points;
  };
  ev.touches = type === "touchend" ? [] : points;
  ev.changedTouches = points;
  return ev;
}
const at = (x: number) => ({ clientX: x, clientY: 10 });

/** O `div` onde o Board registra o toque longo. */
function boardOf(container: HTMLElement) {
  return container.querySelector(".board > div") as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.state.drawable.shapes = [];
  // metade esquerda = e2, metade direita = e4
  api.getKeyAtDomPos.mockImplementation(([x]: [number, number]) => (x < 50 ? "e2" : "e4"));
});
afterEach(() => {
  vi.useRealTimers();
  delete (window as { matchMedia?: unknown }).matchMedia;
});

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

test("no celular o clique não apaga as marcações (lá quem desenha é o toque longo)", () => {
  setPointer(true);
  const coarse = toConfig({ fen: F1, orientation: "white", drawable: true });
  // o `eraseOnClick` do chessground roda no `touchstart`, antes dos 350 ms do toque
  // longo: ligado, ele apagaria a marcação anterior a cada gesto e nada se acumularia
  expect(coarse.drawable?.eraseOnClick).toBe(false);
  setPointer(false);
  expect(toConfig({ fen: F1, orientation: "white", drawable: true }).drawable?.eraseOnClick).toBe(true);
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

// --- toque longo (celular) ---------------------------------------------

test("no celular, segurar numa casa e soltar em outra desenha uma seta", () => {
  setPointer(true);
  vi.useFakeTimers();
  const { container } = render(<Board fen={F1} orientation="white" drawable />);
  const el = boardOf(container);

  el.dispatchEvent(touch("touchstart", [at(10)]));
  vi.advanceTimersByTime(350);
  el.dispatchEvent(touch("touchend", [at(90)]));

  expect(api.setShapes).toHaveBeenCalledWith([{ orig: "e2", dest: "e4", brush: "green" }]);
  // o chessground já tinha começado a arrastar a peça no mesmo toque
  expect(api.cancelMove).toHaveBeenCalled();
});

test("no celular, segurar e soltar na mesma casa destaca a casa", () => {
  setPointer(true);
  vi.useFakeTimers();
  const { container } = render(<Board fen={F1} orientation="white" drawable />);
  const el = boardOf(container);

  el.dispatchEvent(touch("touchstart", [at(10)]));
  vi.advanceTimersByTime(350);
  el.dispatchEvent(touch("touchend", [at(20)]));

  expect(api.setShapes).toHaveBeenCalledWith([{ orig: "e2", brush: "green" }]);
});

test("repetir o mesmo gesto apaga a marcação e preserva as outras", () => {
  setPointer(true);
  vi.useFakeTimers();
  api.state.drawable.shapes = [{ orig: "a1", dest: "h8", brush: "green" }, { orig: "e2", dest: "e4", brush: "green" }];
  const { container } = render(<Board fen={F1} orientation="white" drawable />);
  const el = boardOf(container);

  el.dispatchEvent(touch("touchstart", [at(10)]));
  vi.advanceTimersByTime(350);
  el.dispatchEvent(touch("touchend", [at(90)]));

  expect(api.setShapes).toHaveBeenCalledWith([{ orig: "a1", dest: "h8", brush: "green" }]);
});

test("mover o dedo antes dos 350 ms cancela o desenho (rolagem da página)", () => {
  setPointer(true);
  vi.useFakeTimers();
  const { container } = render(<Board fen={F1} orientation="white" drawable />);
  const el = boardOf(container);

  el.dispatchEvent(touch("touchstart", [at(10)]));
  el.dispatchEvent(touch("touchmove", [at(40)]));
  vi.advanceTimersByTime(350);
  el.dispatchEvent(touch("touchend", [at(90)]));

  expect(api.setShapes).not.toHaveBeenCalled();
});

test("no computador o toque longo não desenha (lá é o botão direito)", () => {
  setPointer(false);
  vi.useFakeTimers();
  const { container } = render(<Board fen={F1} orientation="white" drawable />);
  const el = boardOf(container);

  el.dispatchEvent(touch("touchstart", [at(10)]));
  vi.advanceTimersByTime(350);
  el.dispatchEvent(touch("touchend", [at(90)]));

  expect(api.setShapes).not.toHaveBeenCalled();
});

test("tabuleiro congelado: viewOnly de verdade no celular, desenhável no computador", () => {
  setPointer(true);
  expect(toConfig({ fen: F1, orientation: "white", viewOnly: true, drawable: true }).viewOnly).toBe(true);
  setPointer(false);
  expect(toConfig({ fen: F1, orientation: "white", viewOnly: true, drawable: true }).viewOnly).toBe(false);
});

test("no celular o tabuleiro congelado não desenha com toque longo (a página rola)", () => {
  setPointer(true);
  vi.useFakeTimers();
  const { container } = render(<Board fen={F1} orientation="white" drawable viewOnly />);
  const el = boardOf(container);

  el.dispatchEvent(touch("touchstart", [at(10)]));
  vi.advanceTimersByTime(350);
  el.dispatchEvent(touch("touchend", [at(90)]));

  expect(api.setShapes).not.toHaveBeenCalled();
});

test("no celular as marcações se acumulam e o mesmo gesto apaga só a sua", () => {
  setPointer(true);
  vi.useFakeTimers();
  const { container } = render(<Board fen={F1} orientation="white" drawable />);
  const el = boardOf(container);

  const marcar = (x: number) => {
    el.dispatchEvent(touch("touchstart", [at(x)]));
    vi.advanceTimersByTime(350);
    el.dispatchEvent(touch("touchend", [at(x)]));
  };

  marcar(10);
  expect(api.setShapes).toHaveBeenLastCalledWith([{ orig: "e2", brush: "green" }]);

  // segunda marcação: a primeira continua lá
  marcar(90);
  expect(api.setShapes).toHaveBeenLastCalledWith([
    { orig: "e2", brush: "green" },
    { orig: "e4", brush: "green" },
  ]);

  // repetir o gesto apaga só a marcação dele
  marcar(90);
  expect(api.setShapes).toHaveBeenLastCalledWith([{ orig: "e2", brush: "green" }]);
});

test("no celular o toque longo avisa o pai da marcação nova", () => {
  setPointer(true);
  vi.useFakeTimers();
  const onShapesChange = vi.fn();
  const { container } = render(
    <Board fen={F1} orientation="white" drawable onShapesChange={onShapesChange} />,
  );
  const el = boardOf(container);

  el.dispatchEvent(touch("touchstart", [at(10)]));
  vi.advanceTimersByTime(350);
  el.dispatchEvent(touch("touchend", [at(90)]));

  // o `api.setShapes` não dispara o `onChange` do chessground: o aviso é nosso
  expect(onShapesChange).toHaveBeenCalledWith([{ orig: "e2", dest: "e4", brush: "green" }]);

  // repetir o gesto apaga e avisa a lista vazia
  el.dispatchEvent(touch("touchstart", [at(10)]));
  vi.advanceTimersByTime(350);
  el.dispatchEvent(touch("touchend", [at(90)]));
  expect(onShapesChange).toHaveBeenLastCalledWith([]);
});

test("lance recusado pelo app: a fen volta a ser enviada para a peça retornar, e as marcações ficam", () => {
  setPointer(false);
  api.set.mockClear();
  api.state.drawable.shapes = [];
  const onMove = vi.fn();
  const { rerender } = render(<Board fen={F1} orientation="white" movableColor="white" onMove={onMove} drawable />);
  // o chessground moveu a peça e avisou o app; o app recusou (fen igual)
  const cfg = api.set.mock.calls.at(-1)?.[0] ?? {};
  api.state.drawable.shapes = [{ orig: "e1", dest: "e8", brush: "green" }];
  (cfg.movable?.events?.after ?? (api.set.mock.calls[0]?.[0] as { movable?: { events?: { after?: (o: Key, d: Key) => void } } }).movable?.events?.after)?.("e1" as Key, "e8" as Key);
  expect(onMove).toHaveBeenCalledWith("e1", "e8");
  api.set.mockClear();
  rerender(<Board fen={F1} orientation="white" movableColor="white" onMove={onMove} drawable />);
  const resync = api.set.mock.calls.at(-1)?.[0];
  expect(resync?.fen).toBe(F1);
  expect(api.state.drawable.shapes).toEqual([{ orig: "e1", dest: "e8", brush: "green" }]);
  // re-render seguinte sem lance: a fen volta a ficar de fora (marcações não somem)
  api.set.mockClear();
  rerender(<Board fen={F1} orientation="white" movableColor="white" onMove={onMove} drawable />);
  expect(api.set.mock.calls.at(-1)?.[0]?.fen).toBeUndefined();
});

// --- modo montagem ------------------------------------------------------

test("no modo montagem a peça vai para qualquer casa e o clique é do pai", () => {
  const onSquareClick = vi.fn();
  const cfg = toConfig({
    fen: F1,
    orientation: "white",
    editor: { onSquareClick, onChange: vi.fn() },
  });
  expect(cfg.viewOnly).toBe(false);
  expect(cfg.movable?.free).toBe(true);
  expect(cfg.movable?.color).toBe("both");
  expect(cfg.draggable?.enabled).toBe(true);
  // arrastar para fora do tabuleiro apaga a peça
  expect(cfg.draggable?.deleteOnDropOff).toBe(true);
  // clicar não move a peça selecionada: quem decide o que fazer é a paleta
  expect(cfg.selectable?.enabled).toBe(false);
  expect(cfg.drawable?.enabled).toBe(false);
  cfg.events?.select?.("e4" as Key);
  expect(onSquareClick).toHaveBeenCalledWith("e4");
});

test("no modo montagem o tabuleiro devolve a FEN das peças a cada mudança", () => {
  const onChange = vi.fn();
  render(<Board fen={F1} orientation="white" editor={{ onSquareClick: vi.fn(), onChange }} />);
  const cfg = api.set.mock.calls.at(-1)![0] as { events?: { change?: () => void } };
  cfg.events?.change?.();
  expect(onChange).toHaveBeenCalledWith("8/8/8/8/8/8/8/4K3");
});

test("no modo montagem a posição do pai volta ao tabuleiro quando muda", () => {
  const editor = { onSquareClick: vi.fn(), onChange: vi.fn() };
  const { rerender } = render(<Board fen={F1} orientation="white" editor={editor} />);
  api.set.mockClear();
  rerender(<Board fen={F2} orientation="white" editor={editor} />);
  expect(api.set.mock.calls.at(-1)?.[0]?.fen).toBe(F2);
});

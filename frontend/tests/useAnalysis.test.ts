import { act, renderHook } from "@testing-library/react";
import { useAnalysis } from "../src/analysis/useAnalysis";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

test("play/undo/reset e ilegal ignorado", () => {
  const { result } = renderHook(() => useAnalysis(START));
  expect(result.current.play("e2e5")).toBe(false);
  act(() => { result.current.play("e2e4"); });
  act(() => { result.current.play("e7e5"); });
  expect(result.current.sans).toEqual(["e4", "e5"]);
  expect(result.current.turn).toBe("white");
  act(() => result.current.undo());
  expect(result.current.sans).toEqual(["e4"]);
  act(() => { result.current.play("c7c5"); });
  expect(result.current.sans).toEqual(["e4", "c5"]);
  act(() => result.current.goTo(1));
  expect(result.current.fen.split(" ")[1]).toBe("b");
  act(() => { result.current.play("d7d5"); });     // descarta o futuro (c5)
  expect(result.current.sans).toEqual(["e4", "d5"]);
  act(() => result.current.reset());
  expect(result.current.sans).toEqual([]) ;
  expect(result.current.fen).toBe(START);
});

test("playLine aplica os lances em sequência", () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useAnalysis(START, { stepMs: 10 }));
  act(() => result.current.playLine(["e2e4", "e7e5", "g1f3"]));
  act(() => { vi.advanceTimersByTime(50); });
  expect(result.current.sans).toEqual(["e4", "e5", "Nf3"]);
  vi.useRealTimers();
});

test("undo cancela o timer do playLine em andamento", () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useAnalysis(START, { stepMs: 10 }));
  act(() => result.current.playLine(["e2e4", "e7e5", "g1f3"]));
  act(() => { vi.advanceTimersByTime(10); });
  expect(result.current.sans).toEqual(["e4", "e5"]);
  act(() => result.current.undo());
  expect(result.current.sans).toEqual(["e4"]);
  act(() => { vi.advanceTimersByTime(1000); });
  expect(result.current.sans).toEqual(["e4"]);  // Nf3 nunca chegou a ser jogado
  vi.useRealTimers();
});

test("playLine cancela o timer ao desmontar (sem erro nem estado após o unmount)", () => {
  vi.useFakeTimers();
  const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const { result, unmount } = renderHook(() => useAnalysis(START, { stepMs: 10 }));
  act(() => result.current.playLine(["e2e4", "e7e5", "g1f3"]));
  expect(result.current.sans).toEqual(["e4"]); // primeiro lance é síncrono; os demais ficam agendados
  unmount();
  expect(() => { act(() => { vi.advanceTimersByTime(1000); }); }).not.toThrow();
  expect(result.current.sans).toEqual(["e4"]);
  expect(errorSpy).not.toHaveBeenCalled();
  errorSpy.mockRestore();
  vi.useRealTimers();
});

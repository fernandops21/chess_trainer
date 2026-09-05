import { act, renderHook } from "@testing-library/react";
import { useSessionClock } from "../src/train/useSessionClock";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("contagem regressiva e expiração única", () => {
  const { result } = renderHook(() => useSessionClock(1));
  expect(result.current.label).toBe("01:00");
  act(() => { vi.advanceTimersByTime(30_000); });
  expect(result.current.remainingMs).toBe(30_000);
  expect(result.current.label).toBe("00:30");
  expect(result.current.expired).toBe(false);
  act(() => { vi.advanceTimersByTime(30_000); });
  expect(result.current.expired).toBe(true);
  expect(result.current.remainingMs).toBe(0);
});

test("continuar passa a contar o excedente", () => {
  const { result } = renderHook(() => useSessionClock(1));
  act(() => { vi.advanceTimersByTime(60_000); });
  act(() => result.current.continueSession());
  expect(result.current.overtime).toBe(true);
  expect(result.current.expired).toBe(false);
  act(() => { vi.advanceTimersByTime(65_000); });
  expect(result.current.label).toBe("+01:05");
});

test("sem plano conta para cima", () => {
  const { result } = renderHook(() => useSessionClock(null));
  act(() => { vi.advanceTimersByTime(125_000); });
  expect(result.current.remainingMs).toBeNull();
  expect(result.current.label).toBe("02:05");
  expect(result.current.expired).toBe(false);
});

test("stop congela", () => {
  const { result } = renderHook(() => useSessionClock(null));
  act(() => { vi.advanceTimersByTime(10_000); });
  act(() => result.current.stop());
  act(() => { vi.advanceTimersByTime(10_000); });
  expect(result.current.elapsedMs).toBe(10_000);
  expect(result.current.stopped).toBe(true);
});

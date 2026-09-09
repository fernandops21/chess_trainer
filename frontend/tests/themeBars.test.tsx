import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ThemeBars } from "../src/components/ThemeBars";
import type { ThemeStat } from "../src/api/types";

const row = (over: Partial<ThemeStat> = {}): ThemeStat => ({
  theme: "fork", label: "garfo", attempts: 10, correct: 6, accuracy: 0.6, own: 0, lichess: 10, ...over,
});

test("mostra o rótulo, a contagem e a barra proporcional ao acerto", () => {
  render(
    <ThemeBars rows={[row(), row({ theme: "pin", label: "cravada", attempts: 4, correct: 1, accuracy: 0.25 })]} />,
  );
  expect(screen.getByText("garfo")).toBeTruthy();
  expect(screen.getByText("cravada")).toBeTruthy();
  expect(screen.getByText("6/10")).toBeTruthy();
  expect(screen.getByText("1/4")).toBeTruthy();
  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect((items[0].querySelector("[data-bar]") as HTMLElement).style.width).toBe("60%");
  expect((items[1].querySelector("[data-bar]") as HTMLElement).style.width).toBe("25%");
  // o preenchimento é `--brand` sobre `--line`: `--accent` some no tema escuro
  expect((items[0].querySelector("[data-bar]") as HTMLElement).style.background).toBe("var(--brand)");
  expect((items[0].querySelector("[data-bar]")!.parentElement as HTMLElement).style.background).toBe("var(--line)");
});

test("mostra no máximo 10 linhas", () => {
  const rows = Array.from({ length: 14 }, (_, i) => row({ theme: `t${i}`, label: `tema ${i}` }));
  render(<ThemeBars rows={rows} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(10);
  expect(screen.queryByText("tema 10")).toBeNull();
});

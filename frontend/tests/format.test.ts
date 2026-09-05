import { colorName, formatEval, kindLabel, resultLabel } from "../src/lib/format";

test("formatEval", () => {
  expect(formatEval(125)).toBe("+1.25");
  expect(formatEval(-40)).toBe("-0.40");
  expect(formatEval(0)).toBe("0.00");
  expect(formatEval(99997)).toBe("#3");
  expect(formatEval(-99998)).toBe("#-2");
});

test("rótulos", () => {
  expect(colorName("white")).toBe("Brancas");
  expect(kindLabel("punish")).toBe("punir o erro");
  expect(kindLabel("avoid")).toBe("evitar o erro");
  expect(resultLabel("1-0", "white")).toBe("vitória");
  expect(resultLabel("1-0", "black")).toBe("derrota");
  expect(resultLabel("1/2-1/2", "white")).toBe("empate");
});

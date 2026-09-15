import { categoryLabel, colorName, formatEval, kindLabel, resultLabel, shortCode, themeLabel } from "../src/lib/format";

test("formatEval", () => {
  expect(formatEval(125)).toBe("+1.25");
  expect(formatEval(-40)).toBe("-0.40");
  expect(formatEval(0)).toBe("0.00");
  // perda zero na linha "lance: …" chega negada e não pode virar "-0.00"
  expect(formatEval(-0)).toBe("0.00");
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

test("as outras fontes têm tema e categoria em português", () => {
  expect(themeLabel("study")).toBe("estudo");
  expect(themeLabel("lichess")).toBe("tática do Lichess");
  expect(themeLabel("mate_in_2")).toBe("mate em 2");
  expect(categoryLabel("study")).toBe("estudo");
  expect(categoryLabel("lichess")).toBe("Lichess");
  expect(categoryLabel("rapid")).toBe("rapid");
});

test("shortCode", () => {
  expect(shortCode("ff466803-9e8a-4a1e-8f2a-0b1c2d3e4f50")).toBe("#ff466803");
  // ids curtos (os dos testes) saem inteiros
  expect(shortCode("p1")).toBe("#p1");
});

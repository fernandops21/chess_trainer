import { buildLine, uciToMove } from "../src/board/line";

test("buildLine gera fens e SAN, parando em lance ilegal", () => {
  const line = buildLine("2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1", ["e1e8", "c8e8", "a4e8", "zzzz"]);
  expect(line.sans).toEqual(["Re8+", "Rxe8", "Qxe8#"]);
  expect(line.fens).toHaveLength(4);
  expect(line.lastMoves[1]).toEqual(["e1", "e8"]);
});

test("uciToMove com promoção", () => {
  expect(uciToMove("a7a8q")).toEqual({ from: "a7", to: "a8", promotion: "q" });
  expect(uciToMove("e2e4")).toEqual({ from: "e2", to: "e4" });
});

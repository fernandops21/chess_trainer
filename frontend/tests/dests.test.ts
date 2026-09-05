import { Chess } from "chess.js";
import { destsFrom } from "../src/board/dests";

test("destinos legais por casa de origem", () => {
  const d = destsFrom(new Chess());
  expect(d.get("e2")).toEqual(expect.arrayContaining(["e3", "e4"]));
  expect(d.get("g1")).toEqual(expect.arrayContaining(["f3", "h3"]));
  expect(d.has("e1")).toBe(false);
});

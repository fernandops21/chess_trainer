import { expect, test } from "vitest";
import { novoChess, temOsDoisReis } from "../src/lib/chess";

/** Diagrama do estudo do Basso: "Ataque duplo - Cavalo", sem rei branco. */
const SEM_REI_BRANCO = "r1r5/8/1N6/8/8/8/5N2/3k3q w - - 0 1";
const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const pecasDe = (fen: string) => fen.trim().split(" ")[0];

test("carrega diagrama sem os dois reis e gera lances", () => {
  const chess = novoChess(SEM_REI_BRANCO);
  expect(chess.moves().length).toBeGreaterThan(0);
  expect(pecasDe(chess.fen())).toBe(pecasDe(SEM_REI_BRANCO));
});

test("no diagrama sem rei branco os cavalos jogam normalmente", () => {
  const chess = novoChess(SEM_REI_BRANCO);
  expect(chess.move({ from: "b6", to: "c8" }).san).toBe("Nxc8+");
  const outro = novoChess(SEM_REI_BRANCO);
  expect(outro.move({ from: "b6", to: "a8" }).san).toBe("Nxa8+");
});

test("posição normal continua validada", () => {
  expect(novoChess(START).fen()).toBe(START);
  expect(novoChess().fen()).toBe(START);
});

test("FEN que não é tabuleiro continua lançando", () => {
  expect(() => novoChess("lixo")).toThrow();
  expect(() => novoChess("rnbqkbnr/pppppppp/8/8/8 w KQkq - 0 1")).toThrow();
});

test("diagrama sem rei com peão na borda continua lançando", () => {
  // com `skipValidation` o chess.js aceitaria, e depois `moves()` estouraria
  // com "Cannot mix BigInt and other types" no meio de um render
  expect(() => novoChess("Pnbq4/8/8/8/8/8/8/4K3 w - - 0 1")).toThrow();
  expect(() => novoChess("4K3/8/8/8/8/8/8/4p3 w - - 0 1")).toThrow();
});

test("diagrama sem rei perde as flags de roque da cor sem rei", () => {
  // roque sem rei sairia da casa -1 e `moves()` quebraria ao ler a origem
  const chess = novoChess("8/8/1N6/8/8/8/5N2/3k3q w KQ - 0 1");
  expect(chess.moves().length).toBeGreaterThan(0);
  expect(chess.fen().split(" ")[2]).toBe("-");
});

test("diagrama com rei repetido continua lançando", () => {
  // o chess.js guarda uma casa por cor e apagaria o primeiro rei em silêncio
  expect(() => novoChess("r1r5/8/1N6/8/2k5/8/5N2/3k3q w - - 0 1")).toThrow();
});

test("temOsDoisReis olha só o campo das peças", () => {
  expect(temOsDoisReis(SEM_REI_BRANCO)).toBe(false);
  expect(temOsDoisReis(START)).toBe(true);
  // o rei preto sozinho também não basta
  expect(temOsDoisReis("8/8/8/8/8/8/8/4K3 w - - 0 1")).toBe(false);
  // "k" no campo dos roques não vale como rei
  expect(temOsDoisReis("r1r5/8/1N6/8/8/8/5N2/3q4 w Kk - 0 1")).toBe(false);
});

import { describe, expect, it } from "vitest";

import type { Procedencia, TacticOut } from "../src/api/types";
import { configDoBloco, corpoDoSalvamento, itemDoBloco } from "../src/train/bloco";

const t = (id: string): TacticOut => ({ id } as unknown as TacticOut);
const proc = (n: number): Procedencia => ({ degrau: "inteira", nivel: "destinos", n, posicao: "inteira", espelhado: false });
const bloco = {
  anchorId: "p1", anchorOrigem: "own" as const, itens: [t("a"), t("b")],
  tiers: { a: "mesmo", b: "trecho2" }, procedencias: { a: proc(1), b: proc(2) },
};

describe("bloco de irmãos", () => {
  it("percorre a lista fixa e acaba", () => {
    expect(itemDoBloco(bloco, 0)?.id).toBe("a");
    expect(itemDoBloco(bloco, 1)?.id).toBe("b");
    expect(itemDoBloco(bloco, 2)).toBeNull();
  });
  it("salva o irmão com o vínculo para o exercício de origem e o degrau que o trouxe", () => {
    expect(corpoDoSalvamento(bloco, { correct: true, used_hint: false, duration_ms: 1200, session_id: "s1" }, "a"))
      .toEqual({ correct: true, used_hint: false, duration_ms: 1200, session_id: "s1", sibling_of: "p1", sibling_tier: "mesmo" });
    expect(corpoDoSalvamento(bloco, { correct: true, used_hint: false, duration_ms: 1200 }, "b").sibling_tier).toBe("trecho2");
    const lichess = corpoDoSalvamento({ ...bloco, anchorOrigem: "lichess" }, { correct: false, used_hint: true, duration_ms: 5 }, "a");
    expect(lichess.sibling_of).toBeUndefined();
    expect(lichess.sibling_tier).toBe("mesmo"); // independe da âncora ser própria ou do Lichess
  });
  it("abre uma sessão de táticas no modo bloco", () => {
    expect(configDoBloco(bloco)).toMatchObject({ source: "tactics", mode: "bloco", bloco });
  });
});

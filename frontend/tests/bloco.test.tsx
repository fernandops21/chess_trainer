import { describe, expect, it } from "vitest";

import type { TacticOut } from "../src/api/types";
import { configDoBloco, corpoDoSalvamento, itemDoBloco } from "../src/train/bloco";

const t = (id: string): TacticOut => ({ id } as unknown as TacticOut);
const bloco = { anchorId: "p1", anchorOrigem: "own" as const, itens: [t("a"), t("b")] };

describe("bloco de irmãos", () => {
  it("percorre a lista fixa e acaba", () => {
    expect(itemDoBloco(bloco, 0)?.id).toBe("a");
    expect(itemDoBloco(bloco, 1)?.id).toBe("b");
    expect(itemDoBloco(bloco, 2)).toBeNull();
  });
  it("salva o irmão com o vínculo para o exercício de origem", () => {
    expect(corpoDoSalvamento(bloco, { correct: true, used_hint: false, duration_ms: 1200, session_id: "s1" }))
      .toEqual({ correct: true, used_hint: false, duration_ms: 1200, session_id: "s1", sibling_of: "p1" });
    expect(corpoDoSalvamento({ ...bloco, anchorOrigem: "lichess" }, { correct: false, used_hint: true, duration_ms: 5 }).sibling_of).toBeUndefined();
  });
  it("abre uma sessão de táticas no modo bloco", () => {
    expect(configDoBloco(bloco)).toMatchObject({ source: "tactics", mode: "bloco", bloco });
  });
});

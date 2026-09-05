import type { Chess } from "chess.js";
import type { Key } from "chessground/types";

export function destsFrom(chess: Chess): Map<Key, Key[]> {
  const map = new Map<Key, Key[]>();
  for (const m of chess.moves({ verbose: true })) {
    const from = m.from as Key;
    const list = map.get(from) ?? [];
    if (!list.includes(m.to as Key)) list.push(m.to as Key);
    map.set(from, list);
  }
  return map;
}

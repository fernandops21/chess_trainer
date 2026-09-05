import { Board } from "./Board";
import type { Key } from "chessground/types";

export function MiniBoard({ fen, orientation, lastMove }: { fen: string; orientation: "white" | "black"; lastMove?: [Key, Key] }) {
  return <div className="miniboard"><Board fen={fen} orientation={orientation} lastMove={lastMove} viewOnly coordinates={false} /></div>;
}

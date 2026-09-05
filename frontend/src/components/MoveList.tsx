import type { Ply } from "../lib/plies";

export function MoveList({ plies, current, onSelect }: { plies: Ply[]; current: number; onSelect: (ply: number) => void }) {
  const rows: Ply[][] = [];
  for (const p of plies) { if (p.ply % 2 === 1) rows.push([p]); else (rows[rows.length - 1] ??= []).push(p); }
  return (
    <div className="movelist">
      {rows.map((row, i) => (
        <div key={i} className="moverow">
          <span className="muted">{i + 1}.</span>
          {row.map((p) => (
            <button key={p.ply} onClick={() => onSelect(p.ply)} className={`san ${p.ply === current ? "cur" : ""} ${p.level ?? ""}`}>{p.san}</button>
          ))}
        </div>
      ))}
    </div>
  );
}

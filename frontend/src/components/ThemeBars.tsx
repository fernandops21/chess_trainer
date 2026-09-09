import type { ThemeStat } from "../api/types";
import { themeLabel } from "../lib/format";

const MAX_ROWS = 10;

/** Barras de acerto por tema (as `rows` já vêm ordenadas pelo backend). */
export function ThemeBars({ rows }: { rows: ThemeStat[] }) {
  return (
    <div role="list">
      {rows.slice(0, MAX_ROWS).map((r) => {
        const pct = Math.round(r.accuracy * 100);
        return (
          <div key={r.theme} role="listitem" className="row" style={{ gap: 8, alignItems: "center", margin: "4px 0" }}>
            <span style={{ width: 150, flexShrink: 0 }}>{r.label || themeLabel(r.theme)}</span>
            <span
              title={`${pct}% de acerto`}
              style={{ flex: 1, minWidth: 60, height: 10, borderRadius: 999, background: "var(--line)", overflow: "hidden" }}
            >
              <span data-bar style={{ display: "block", width: `${pct}%`, height: "100%", background: "var(--brand)" }} />
            </span>
            <span className="muted" style={{ width: 70, textAlign: "right", fontSize: 13 }}>{r.correct}/{r.attempts}</span>
          </div>
        );
      })}
    </div>
  );
}

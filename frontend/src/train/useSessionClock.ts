import { useCallback, useEffect, useRef, useState } from "react";

export const mmss = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

export function useSessionClock(plannedMinutes: number | null, opts: { now?: () => number } = {}) {
  const now = opts.now ?? Date.now;
  const startedAt = useRef(now());
  const [elapsedMs, setElapsed] = useState(0);
  const [overtime, setOvertime] = useState(false);
  const [stopped, setStopped] = useState(false);

  useEffect(() => {
    if (stopped) return;
    const id = setInterval(() => setElapsed(now() - startedAt.current), 1000);
    return () => clearInterval(id);
  }, [stopped, now]);

  const plannedMs = plannedMinutes != null ? plannedMinutes * 60_000 : null;
  const remainingMs = plannedMs != null ? Math.max(0, plannedMs - elapsedMs) : null;
  const expired = remainingMs === 0 && !overtime && !stopped;

  const continueSession = useCallback(() => setOvertime(true), []);
  const stop = useCallback(() => { setElapsed(now() - startedAt.current); setStopped(true); }, [now]);

  let label: string;
  if (plannedMs == null) label = mmss(elapsedMs);
  else if (overtime) label = `+${mmss(elapsedMs - plannedMs)}`;
  else label = mmss(remainingMs ?? 0);

  return { elapsedMs, remainingMs, expired, overtime, stopped, continueSession, stop, label };
}

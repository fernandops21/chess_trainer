export function StatCard({ value, label, hint }: { value: number | string; label: string; hint?: string }) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 140 }}>
      <div className="stat">{value}</div>
      <div>{label}</div>
      {hint && <div className="muted" style={{ fontSize: 13 }}>{hint}</div>}
    </div>
  );
}

import { NavLink } from "react-router-dom";
import { useDashboard } from "../api/queries";
import { play, useSoundEnabled } from "../lib/sound";

const items = [
  { to: "/", label: "Painel", icon: "▦", end: true },
  { to: "/treinar", label: "Treinar", icon: "♞" },
  { to: "/estudos", label: "Estudos", icon: "▤" },
  { to: "/analise", label: "Análise", icon: "⌕" },
  { to: "/partidas", label: "Partidas", icon: "≡" },
  { to: "/erros", label: "Erros", icon: "!" },
  { to: "/config", label: "Config", icon: "⚙" },
];

export function Nav() {
  const { data } = useDashboard();
  const due = data?.due_today ?? 0;
  const [som, setSom] = useSoundEnabled();
  return (
    <nav className="nav" aria-label="Principal">
      <div className="brand">Chess Trainer</div>
      {items.map((it) => (
        <NavLink key={it.to} to={it.to} end={it.end} className={({ isActive }) => (isActive ? "active" : "")}>
          <span aria-hidden="true">{it.icon}</span>
          <span>{it.label}</span>
          {it.to === "/treinar" && due > 0 && <span className="badge">{due}</span>}
        </NavLink>
      ))}
      <button
        type="button"
        className="nav-som"
        aria-label={som ? "Som ligado" : "Som desligado"}
        aria-pressed={som}
        onClick={() => { const novo = !som; setSom(novo); if (novo) play("move"); }}
      >
        <span aria-hidden="true">{som ? "🔊" : "🔇"}</span>
        <span>Som</span>
      </button>
    </nav>
  );
}

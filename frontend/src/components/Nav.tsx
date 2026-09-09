import { NavLink } from "react-router-dom";
import { useDashboard } from "../api/queries";
import { play, useSoundEnabled } from "../lib/sound";
import { useTema } from "../lib/theme";

const items = [
  { to: "/", label: "Painel", icon: "▦", end: true },
  { to: "/progresso", label: "Progresso", icon: "↗" },
  { to: "/revisar", label: "Revisar", icon: "↻" },
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
  // o número sozinho não diz o que é: o rótulo explica que são os vencidos da repetição
  const vencidos = `${due} vencido${due === 1 ? "" : "s"} na repetição`;
  const [som, setSom] = useSoundEnabled();
  const [tema, setTema] = useTema();
  const escuro = tema === "escuro";
  return (
    <nav className="nav" aria-label="Principal">
      <div className="brand">Chess Trainer</div>
      {items.map((it) => (
        <NavLink key={it.to} to={it.to} end={it.end} className={({ isActive }) => (isActive ? "active" : "")}>
          <span aria-hidden="true">{it.icon}</span>
          <span>{it.label}</span>
          {it.to === "/revisar" && due > 0 && <span className="badge" title={vencidos} aria-label={vencidos}>{due}</span>}
        </NavLink>
      ))}
      <button
        type="button"
        className="nav-botao nav-som"
        aria-label={som ? "Som ligado" : "Som desligado"}
        aria-pressed={som}
        onClick={() => { const novo = !som; setSom(novo); if (novo) play("move"); }}
      >
        <span aria-hidden="true">{som ? "🔊" : "🔇"}</span>
        <span>Som</span>
      </button>
      <button
        type="button"
        className="nav-botao nav-tema"
        aria-label={escuro ? "Tema escuro" : "Tema claro"}
        aria-pressed={escuro}
        onClick={() => setTema(escuro ? "claro" : "escuro")}
      >
        <span aria-hidden="true">{escuro ? "🌙" : "☀️"}</span>
        <span>Tema</span>
      </button>
    </nav>
  );
}

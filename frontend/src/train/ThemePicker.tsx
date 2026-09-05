import { useTacticThemes } from "../api/queries";

const TOP = 20;

/** Chips dos temas mais frequentes do banco do Lichess; multi-seleção. */
export function ThemePicker({ selected, onChange }: { selected: string[]; onChange: (themes: string[]) => void }) {
  const { data, isLoading, error } = useTacticThemes();
  const top = [...(data ?? [])].sort((a, b) => b.count - a.count).slice(0, TOP);
  const toggle = (theme: string) =>
    onChange(selected.includes(theme) ? selected.filter((t) => t !== theme) : [...selected, theme]);

  if (isLoading) return <p className="muted">Carregando temas…</p>;
  if (error) return <p className="muted">Não foi possível carregar os temas.</p>;
  if (top.length === 0) return <p className="muted">Nenhum tema disponível.</p>;
  return (
    <div>
      <div className="muted">Temas (opcional; sem escolha, vale qualquer um)</div>
      <div className="row" style={{ marginTop: 6, gap: 6 }}>
        {top.map((t) => {
          const on = selected.includes(t.theme);
          return (
            <button key={t.theme} type="button" className={on ? "tag selected" : "tag"} aria-pressed={on} onClick={() => toggle(t.theme)}>
              {t.label}
            </button>
          );
        })}
        {selected.length > 0 && <button type="button" onClick={() => onChange([])}>Limpar</button>}
      </div>
    </div>
  );
}

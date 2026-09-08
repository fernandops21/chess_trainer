import type { ClassKind } from "./classify";

/**
 * Ícones dos selos de classificação, em SVG: nítidos em qualquer tamanho, ao
 * contrário do emoji/texto dentro de um círculo. Cores no padrão do chess.com,
 * que é o que o usuário já conhece. O `<svg>` é decorativo (`aria-hidden`):
 * quem fala o nome da classificação é o elemento em volta.
 */
export const CORES: Record<ClassKind, string> = {
  livro: "#a88865",
  brilhante: "#1baca6",
  otimo: "#5c8bb0",
  melhor: "#81b64c",
  excelente: "#81b64c",
  bom: "#95b776",
  imprecisao: "#f7c631",
  erro: "#ffa459",
  blunder: "#fa412d",
};

/** Texto em negrito, centralizado no círculo. */
function Texto({ t, tamanho = 13 }: { t: string; tamanho?: number }) {
  return (
    <text x="12" y="12" textAnchor="middle" dominantBaseline="central" fill="#fff"
      fontFamily="system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif" fontWeight="800" fontSize={tamanho}>
      {t}
    </text>
  );
}

function Glifo({ kind }: { kind: ClassKind }) {
  switch (kind) {
    case "livro":
      // livro aberto: duas páginas com a lombada no meio
      return (
        <g fill="#fff">
          <path d="M11.2 7.2c-1.4-.9-3.3-1.2-5.2-1v10.6c1.9-.2 3.8.1 5.2 1V7.2z" />
          <path d="M12.8 7.2c1.4-.9 3.3-1.2 5.2-1v10.6c-1.9-.2-3.8.1-5.2 1V7.2z" />
        </g>
      );
    case "melhor":
      return <path fill="#fff" d="M12 4.6l2.2 4.6 5 .7-3.6 3.5.9 5-4.5-2.4-4.5 2.4.9-5L4.8 9.9l5-.7z" />;
    case "excelente":
      return <path fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" d="M6.5 12.5l3.6 3.6 7.4-8" />;
    case "bom":
      return <path fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" d="M7 12.5l3.3 3.3 6.7-7.3" />;
    case "brilhante": return <Texto t="!!" />;
    case "otimo": return <Texto t="!" tamanho={15} />;
    case "imprecisao": return <Texto t="?!" />;
    case "erro": return <Texto t="?" tamanho={15} />;
    case "blunder": return <Texto t="??" />;
  }
}

export function ClassIcon({ kind, size = "1em", className }: { kind: ClassKind; size?: number | string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} className={className} aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="11" fill={CORES[kind]} stroke="rgba(255,255,255,.85)" strokeWidth="1" />
      <Glifo kind={kind} />
    </svg>
  );
}

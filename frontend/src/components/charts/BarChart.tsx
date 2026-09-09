import { marcasInteiras } from "./escala";
import "./charts.css";

export interface BarDatum {
  /** Rótulo da coluna (o dia); aparece ao passar o mouse e nas pontas do eixo. */
  label: string;
  correct: number;
  wrong: number;
}

const L = 620;
const A = 180;
const MARGEM = { topo: 10, direita: 8, baixo: 26, esquerda: 44 };

/**
 * Colunas empilhadas (certas embaixo, erradas em cima) em SVG, sem biblioteca.
 * Só as pontas do eixo horizontal ganham rótulo — com muitos dias eles se
 * sobreporiam; o dia de cada coluna está no `<title>`.
 */
export function BarChart({ bars, titulo }: { bars: BarDatum[]; titulo: string }) {
  if (bars.length === 0) return null;
  const totais = bars.map((b) => b.correct + b.wrong);
  const { topo, valores } = marcasInteiras(Math.max(...totais));
  const larguraUtil = L - MARGEM.esquerda - MARGEM.direita;
  const alturaUtil = A - MARGEM.topo - MARGEM.baixo;
  const passo = larguraUtil / bars.length;
  // no máximo 28 px e nunca mais larga que o passo: com 365 dias as colunas ficam
  // finas, mas não se sobrepõem
  const largura = Math.min(passo, Math.max(1, Math.min(28, passo * 0.7)));
  const altura = (v: number) => (v / topo) * alturaUtil;
  const base = MARGEM.topo + alturaUtil;
  const y = (v: number) => MARGEM.topo + alturaUtil - altura(v);
  const certas = bars.reduce((s, b) => s + b.correct, 0);
  const erradas = bars.reduce((s, b) => s + b.wrong, 0);
  const rotulo = `${titulo}: ${bars.length} dia(s), ${certas} certa(s) e ${erradas} errada(s).`;
  return (
    <svg className="grafico" viewBox={`0 0 ${L} ${A}`} role="img" aria-label={rotulo}>
      {valores.map((v) => (
        <g key={v}>
          <line className="grafico-grade" x1={MARGEM.esquerda} x2={L - MARGEM.direita} y1={y(v)} y2={y(v)} />
          <text className="grafico-eixo" x={MARGEM.esquerda - 6} y={y(v) + 4} textAnchor="end">{v}</text>
        </g>
      ))}
      {bars.map((b, i) => {
        const cx = MARGEM.esquerda + passo * i + (passo - largura) / 2;
        return (
          <g key={`${b.label}-${i}`} data-barra>
            <title>{`${b.label}: ${b.correct} certa(s), ${b.wrong} errada(s)`}</title>
            <rect data-certo className="grafico-certo" x={cx} width={largura} y={base - altura(b.correct)} height={altura(b.correct)} />
            <rect data-errado className="grafico-errado" x={cx} width={largura}
                  y={base - altura(b.correct) - altura(b.wrong)} height={altura(b.wrong)} />
          </g>
        );
      })}
      <text className="grafico-eixo" x={MARGEM.esquerda} y={A - 6}>{bars[0].label}</text>
      {bars.length > 1 && (
        <text className="grafico-eixo" x={L - MARGEM.direita} y={A - 6} textAnchor="end">{bars[bars.length - 1].label}</text>
      )}
    </svg>
  );
}

import { marcas } from "./escala";
import "./charts.css";

export interface LinePoint {
  /** Rótulo do ponto (uma data, por exemplo); aparece ao passar o mouse. */
  label: string;
  value: number;
}

const L = 620;
const A = 180;
const MARGEM = { topo: 10, direita: 8, baixo: 16, esquerda: 44 };

/**
 * Linha simples em SVG, sem biblioteca. O eixo vertical ganha até 5 marcas entre o
 * menor e o maior valor; com todos os valores iguais a linha fica no meio da área.
 * Com mais pontos do que pixels de largura, só a polilinha é desenhada.
 */
export function LineChart({ points, titulo, unidade = "" }: { points: LinePoint[]; titulo: string; unidade?: string }) {
  if (points.length === 0) return null;
  const valores = points.map((p) => p.value);
  const min = Math.min(...valores);
  const max = Math.max(...valores);
  const larguraUtil = L - MARGEM.esquerda - MARGEM.direita;
  const alturaUtil = A - MARGEM.topo - MARGEM.baixo;
  // linha plana (todos os valores iguais): fica no meio, e não colada no fundo
  const plana = max === min;
  const x = (i: number) =>
    MARGEM.esquerda + (points.length === 1 ? larguraUtil / 2 : (larguraUtil * i) / (points.length - 1));
  const y = (v: number) =>
    plana ? MARGEM.topo + alturaUtil / 2 : MARGEM.topo + alturaUtil - ((v - min) / (max - min)) * alturaUtil;
  // com mais pontos do que pixels úteis, as bolinhas só se amontoam: fica só a linha
  const comPontos = points.length <= larguraUtil;
  const rotulo =
    `${titulo}: ${points.length} ponto(s), de ${valores[0]} a ${valores[valores.length - 1]}` +
    `, mínimo ${min} e máximo ${max}${unidade}.`;
  return (
    <svg className="grafico" viewBox={`0 0 ${L} ${A}`} role="img" aria-label={rotulo}>
      {marcas(min, max).map((v) => (
        <g key={v}>
          <line className="grafico-grade" x1={MARGEM.esquerda} x2={L - MARGEM.direita} y1={y(v)} y2={y(v)} />
          <text className="grafico-eixo" x={MARGEM.esquerda - 6} y={y(v) + 4} textAnchor="end">{Math.round(v)}</text>
        </g>
      ))}
      <polyline data-linha className="grafico-linha" points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ")} />
      {comPontos &&
        points.map((p, i) => (
          <circle key={`${p.label}-${i}`} data-ponto className="grafico-ponto" cx={x(i)} cy={y(p.value)} r={3}>
            <title>{`${p.label}: ${p.value}${unidade}`}</title>
          </circle>
        ))}
    </svg>
  );
}

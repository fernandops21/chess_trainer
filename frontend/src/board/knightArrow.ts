import type { DrawShape } from "chessground/draw";
import type { Color } from "chessground/types";

/**
 * Seta de cavalo decorada. O chessground só desenha a linha reta quando o
 * `brush` está definido; para a seta em "L" o `brush` sai e o desenho vira um
 * `customSvg`. O pincel original fica guardado no campo extra `cavalo`, que é o
 * que volta para a árvore do estudo (que nunca guarda `customSvg`).
 */
export type KnightShape = DrawShape & { cavalo?: string };

/** Lado da casa no `viewBox` do `customSvg` (o chessground usa `0 0 100 100` por casa). */
const CASA = 100;

/**
 * Espessura da linha e recuo da ponta, em unidades do `viewBox`: o chessground
 * usa `lineWidth`/64 e `arrowMargin`/64 de casa, ambos 10/64 ≈ 0,156 casa.
 */
const ESPESSURA = 15.6;
const MARGEM = 15.6;

/** Cor e opacidade dos pincéis do chessground (`state.js`); desconhecido vira verde. */
const PINCEIS: Record<string, { color: string; opacity: number }> = {
  green: { color: "#15781B", opacity: 1 },
  red: { color: "#882020", opacity: 1 },
  blue: { color: "#003088", opacity: 1 },
  yellow: { color: "#e68f00", opacity: 1 },
  paleBlue: { color: "#003088", opacity: 0.4 },
  paleGreen: { color: "#15781B", opacity: 0.4 },
  paleRed: { color: "#882020", opacity: 0.4 },
  paleGrey: { color: "#4a4a4a", opacity: 0.35 },
  purple: { color: "#68217a", opacity: 0.65 },
  pink: { color: "#ee2080", opacity: 0.5 },
  white: { color: "white", opacity: 1 },
};

function pincel(nome: string | undefined) {
  return PINCEIS[nome ?? ""] ?? PINCEIS.green;
}

/** Coluna (0–7) e fileira (0–7) de uma casa; `undefined` fora do tabuleiro. */
function casa(square: string): [number, number] | null {
  const col = square.charCodeAt(0) - 97;
  const row = Number(square[1]) - 1;
  if (!Number.isInteger(row) || col < 0 || col > 7 || row < 0 || row > 7) return null;
  return [col, row];
}

/** Número curto para o `d` do path: no máximo duas casas decimais, sem zeros à toa. */
function n(v: number): string {
  return String(Math.round(v * 100) / 100);
}

/** O salto de cavalo: (1,2) ou (2,1) casas. */
export function ehLanceDeCavalo(orig: string, dest: string | undefined): boolean {
  if (!dest) return false;
  const a = casa(orig);
  const b = casa(dest);
  if (!a || !b) return false;
  const dc = Math.abs(b[0] - a[0]);
  const df = Math.abs(b[1] - a[1]);
  return (dc === 1 && df === 2) || (dc === 2 && df === 1);
}

/**
 * Caminho em "L" do salto de cavalo, em coordenadas do `viewBox` do `customSvg`
 * (100 unidades por casa, origem no centro da casa de partida = `50,50`; o eixo
 * x cresce para a direita e o y para baixo **na tela**, então com o tabuleiro
 * virado os deltas trocam de sinal).
 *
 * O ramo longo (2 casas) vem primeiro, como no chess.com, e o curto termina
 * `MARGEM` antes do centro da casa de destino — é onde a ponta da seta encosta.
 */
export function caminhoEmL(orig: string, dest: string, orientation: Color): string {
  return pernas(orig, dest, orientation)?.d ?? "";
}

/**
 * As duas pernas do "L": o `d` do caminho, onde ele termina e por qual direção
 * a ponta entra na casa de destino (a do ramo curto), para desenhar a seta.
 */
function pernas(orig: string, dest: string, orientation: Color) {
  const a = casa(orig);
  const b = casa(dest);
  if (!a || !b) return null;
  const sinal = orientation === "white" ? 1 : -1;
  // na tela, x cresce para a direita e y para baixo: a fileira inverte
  const dx = sinal * (b[0] - a[0]) * CASA;
  const dy = -sinal * (b[1] - a[1]) * CASA;
  const inicio: [number, number] = [50, 50];
  // ramo longo primeiro: o de 2 casas
  const cotovelo: [number, number] =
    Math.abs(dy) > Math.abs(dx) ? [inicio[0], inicio[1] + dy] : [inicio[0] + dx, inicio[1]];
  const alvo: [number, number] = [inicio[0] + dx, inicio[1] + dy];
  // direção do ramo curto (sempre horizontal ou vertical, uma casa)
  const u: [number, number] = [Math.sign(alvo[0] - cotovelo[0]), Math.sign(alvo[1] - cotovelo[1])];
  const fim: [number, number] = [alvo[0] - u[0] * MARGEM, alvo[1] - u[1] * MARGEM];
  const d = `M${n(inicio[0])} ${n(inicio[1])} L${n(cotovelo[0])} ${n(cotovelo[1])} L${n(fim[0])} ${n(fim[1])}`;
  return { u, fim, d };
}

/**
 * Ponta da seta, copiando a do chessground: o marcador dele é o triângulo
 * `M0,0 V4 L3,2 Z` em múltiplos da espessura, com `refX` 2,05 e `refY` 2. Ele
 * fica nas `<defs>` do svg das setas retas e só é criado para marcações com
 * `brush`; como a seta de cavalo não tem `brush`, o marcador não existiria e a
 * seta ficaria sem ponta — por isso o triângulo é desenhado aqui.
 */
function ponta(fim: [number, number], u: [number, number]): string {
  const p: [number, number] = [-u[1], u[0]];
  const desloca = (au: number, ap: number): string =>
    `${n(fim[0] + au * u[0] + ap * p[0])} ${n(fim[1] + au * u[1] + ap * p[1])}`;
  const bico = 0.95 * ESPESSURA;
  const recuo = 2.05 * ESPESSURA;
  const meia = 2 * ESPESSURA;
  return `M${desloca(-recuo, -meia)} L${desloca(bico, 0)} L${desloca(-recuo, meia)} Z`;
}

/**
 * Troca a linha reta de um salto de cavalo por um caminho em "L", como no
 * chess.com. Marcações que não são salto de cavalo saem intactas.
 *
 * O `brush` sai (senão o chessground desenharia a reta por cima) e vai para o
 * campo `cavalo`; o desenho vira um `customSvg` centrado na casa de partida.
 */
export function decorarCavalo(shape: KnightShape, orientation: Color): KnightShape {
  const { orig, dest } = shape;
  if (!dest || !ehLanceDeCavalo(orig, dest)) return shape;
  const nome = shape.cavalo ?? shape.brush ?? "green";
  const { color, opacity } = pincel(nome);
  const { u, fim, d } = pernas(orig, dest, orientation)!;
  const html =
    `<path d="${d}" fill="none" stroke="${color}" stroke-width="${ESPESSURA}"` +
    ` stroke-linecap="round" stroke-linejoin="round" opacity="${opacity}"/>` +
    `<path d="${ponta(fim, u)}" fill="${color}" opacity="${opacity}"/>`;
  return { ...shape, brush: undefined, cavalo: nome, customSvg: { html, center: "orig" } };
}

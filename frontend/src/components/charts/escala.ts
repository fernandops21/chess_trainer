/**
 * Marcas do eixo vertical: até `quantidade + 1` valores igualmente espaçados, com
 * passo inteiro (≥ 1) para que os rótulos arredondados nunca se repitam quando a
 * faixa é menor que `quantidade` (1500, 1501, 1501…).
 */
export function marcas(min: number, max: number, quantidade = 4): number[] {
  if (max <= min) return [min];
  const passo = Math.max(1, Math.ceil((max - min) / quantidade));
  const valores: number[] = [];
  for (let v = min; v <= max; v += passo) valores.push(v);
  return valores;
}

/**
 * Topo e marcas inteiras para contagens: o passo é arredondado para cima, de
 * modo que as marcas nunca repitam o mesmo número (1, 1, 2, 2…).
 */
export function marcasInteiras(max: number, quantidade = 4): { topo: number; valores: number[] } {
  const passo = Math.max(1, Math.ceil(Math.max(max, 1) / quantidade));
  const topo = passo * quantidade;
  return { topo, valores: Array.from({ length: quantidade + 1 }, (_, i) => i * passo) };
}

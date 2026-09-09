/** Marcas do eixo vertical: 5 valores igualmente espaçados (4 intervalos). */
export function marcas(min: number, max: number, quantidade = 4): number[] {
  if (max <= min) return [min];
  return Array.from({ length: quantidade + 1 }, (_, i) => min + ((max - min) * i) / quantidade);
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

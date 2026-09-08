import { expect, test } from "vitest";
import { caminhoEmL, decorarCavalo, ehLanceDeCavalo, type KnightShape } from "../src/board/knightArrow";

test("o salto de cavalo é (1,2) ou (2,1); o resto não", () => {
  expect(ehLanceDeCavalo("g1", "f3")).toBe(true);
  expect(ehLanceDeCavalo("b1", "c3")).toBe(true);
  expect(ehLanceDeCavalo("d4", "f5")).toBe(true);
  expect(ehLanceDeCavalo("e2", "e4")).toBe(false);
  expect(ehLanceDeCavalo("c1", "h6")).toBe(false);
  // casa destacada (sem destino) não é seta nenhuma
  expect(ehLanceDeCavalo("g1", undefined)).toBe(false);
});

test("g1→f3 com as brancas embaixo: sobe duas casas e depois vira à esquerda", () => {
  const d = caminhoEmL("g1", "f3", "white");
  // centro da casa de partida no viewBox do customSvg
  expect(d.startsWith("M50 50")).toBe(true);
  // ramo longo primeiro: duas casas para cima (200 unidades)
  expect(d).toContain("L50 -150");
  // o ramo curto para 15,6 unidades antes do centro de f3 (-50), onde entra a ponta
  expect(d).toBe("M50 50 L50 -150 L-34.4 -150");
});

test("virando o tabuleiro, o mesmo salto espelha os dois ramos", () => {
  expect(caminhoEmL("g1", "f3", "black")).toBe("M50 50 L50 250 L134.4 250");
});

test("quando o ramo longo é horizontal, ele também vem primeiro", () => {
  // g1→e2: duas colunas para a esquerda, uma fileira para cima
  expect(caminhoEmL("g1", "e2", "white")).toBe("M50 50 L-150 50 L-150 -34.4");
});

test("uma seta que não é de cavalo sai intacta", () => {
  const reta: KnightShape = { orig: "e2", dest: "e4", brush: "green" };
  expect(decorarCavalo(reta, "white")).toBe(reta);
});

test("a seta de cavalo perde o pincel e vira um desenho próprio", () => {
  const seta = decorarCavalo({ orig: "g1", dest: "f3", brush: "green" }, "white");
  // com `brush` o chessground desenharia a reta por cima
  expect(seta.brush).toBeUndefined();
  // o pincel fica guardado para voltar à árvore do estudo
  expect(seta.cavalo).toBe("green");
  expect(seta.customSvg?.center).toBe("orig");
  expect(seta.customSvg?.html).toContain('stroke="#15781B"');
  expect(seta.customSvg?.html).toContain('d="M50 50 L50 -150 L-34.4 -150"');
  // a ponta é desenhada aqui: o marcador do chessground só existe para setas com pincel
  expect(seta.customSvg?.html).toContain('fill="#15781B"');
});

test("cada pincel tem sua cor; o desconhecido vira verde", () => {
  const azul = decorarCavalo({ orig: "b1", dest: "c3", brush: "blue" }, "white");
  expect(azul.cavalo).toBe("blue");
  expect(azul.customSvg?.html).toContain('stroke="#003088"');
  const estranho = decorarCavalo({ orig: "b1", dest: "c3", brush: "arco-iris" }, "white");
  expect(estranho.customSvg?.html).toContain('stroke="#15781B"');
});

test("decorar duas vezes não perde o pincel original", () => {
  const uma = decorarCavalo({ orig: "b1", dest: "c3", brush: "red" }, "white");
  const outra = decorarCavalo(uma, "black");
  expect(outra.cavalo).toBe("red");
  expect(outra.brush).toBeUndefined();
  expect(outra.customSvg?.html).toContain('stroke="#882020"');
});

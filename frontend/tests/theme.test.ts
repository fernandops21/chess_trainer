import { afterEach, beforeEach, expect, test, vi } from "vitest";

type Ouvinte = (evento: { matches: boolean }) => void;

/** O jsdom não traz `matchMedia`: este dublê responde pela preferência do sistema. */
function fakeMatchMedia(escuro: boolean) {
  const ouvintes: Ouvinte[] = [];
  const mq = {
    matches: escuro,
    media: "(prefers-color-scheme: dark)",
    addEventListener: (_tipo: string, fn: Ouvinte) => { ouvintes.push(fn); },
    removeEventListener: () => { /* nada */ },
  };
  window.matchMedia = (() => mq) as unknown as typeof window.matchMedia;
  return {
    ouvintes,
    /** O sistema trocou de tema com a página aberta. */
    mudar(valor: boolean) {
      mq.matches = valor;
      for (const fn of ouvintes) fn({ matches: valor });
    },
  };
}

/** Módulo novo a cada teste: o ouvinte do sistema é registrado na importação. */
async function carregar() {
  vi.resetModules();
  return await import("../src/lib/theme");
}

const atributo = () => document.documentElement.getAttribute("data-theme");

function limpar() {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  delete (window as { matchMedia?: unknown }).matchMedia;
}

beforeEach(limpar);
afterEach(limpar);

test("sem escolha guardada, o tema segue o sistema", async () => {
  fakeMatchMedia(true);
  expect((await carregar()).getTema()).toBe("escuro");

  fakeMatchMedia(false);
  expect((await carregar()).getTema()).toBe("claro");
});

test("navegador sem matchMedia fica no claro, sem lançar", async () => {
  const { getTema, aplicarTema } = await carregar();
  expect(getTema()).toBe("claro");
  expect(() => aplicarTema()).not.toThrow();
  expect(atributo()).toBe("");
});

test("setTema('escuro') guarda a escolha e liga a paleta escura", async () => {
  fakeMatchMedia(false);
  const { setTema, getTema } = await carregar();
  setTema("escuro");
  expect(getTema()).toBe("escuro");
  expect(localStorage.getItem("tema")).toBe('"escuro"');
  expect(atributo()).toBe("dark");
});

test("setTema('claro') limpa o atributo", async () => {
  fakeMatchMedia(true);
  const { setTema, getTema } = await carregar();
  setTema("escuro");
  setTema("claro");
  expect(getTema()).toBe("claro");
  expect(localStorage.getItem("tema")).toBe('"claro"');
  expect(atributo()).toBe("");
});

test("a escolha guardada vence a preferência do sistema", async () => {
  fakeMatchMedia(true);
  localStorage.setItem("tema", '"claro"');
  const { getTema, aplicarTema } = await carregar();
  expect(getTema()).toBe("claro");
  aplicarTema();
  expect(atributo()).toBe("");
});

test("a escolha guardada sobrevive ao recarregar a página", async () => {
  fakeMatchMedia(false);
  (await carregar()).setTema("escuro");

  const outro = await carregar();
  expect(outro.getTema()).toBe("escuro");
  outro.aplicarTema();
  expect(atributo()).toBe("dark");
});

test("valor estranho no armazenamento cai de volta no sistema", async () => {
  fakeMatchMedia(true);
  localStorage.setItem("tema", '"roxo"');
  expect((await carregar()).getTema()).toBe("escuro");
  localStorage.setItem("tema", "não é json");
  expect((await carregar()).getTema()).toBe("escuro");
});

test("sem escolha guardada, o tema acompanha o sistema mudando", async () => {
  const sistema = fakeMatchMedia(false);
  const { getTema, aplicarTema } = await carregar();
  aplicarTema();
  expect(atributo()).toBe("");

  sistema.mudar(true);
  expect(getTema()).toBe("escuro");
  expect(atributo()).toBe("dark");
});

test("com escolha guardada, a mudança do sistema não mexe no tema", async () => {
  const sistema = fakeMatchMedia(false);
  const { getTema, setTema } = await carregar();
  setTema("claro");

  sistema.mudar(true);
  expect(getTema()).toBe("claro");
  expect(atributo()).toBe("");
});

import { useSyncExternalStore } from "react";
import { storage } from "./storage";

/** Tema visual da interface. */
export type Tema = "claro" | "escuro";

const CHAVE = "tema";

const ouvintes = new Set<() => void>();

function avisarTodos(): void {
  for (const avisar of ouvintes) avisar();
}

/** A escolha guardada, ou `null` quando o usuário nunca escolheu. */
function guardado(): Tema | null {
  const valor = storage.get<unknown>(CHAVE, null);
  return valor === "claro" || valor === "escuro" ? valor : null;
}

/** O que o sistema pede; navegador sem `matchMedia` (jsdom, por exemplo) conta como claro. */
function doSistema(): Tema {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return "claro";
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "escuro" : "claro";
  } catch {
    return "claro";
  }
}

/** Tema em vigor: a escolha guardada manda; sem ela, o sistema decide. */
export function getTema(): Tema {
  return guardado() ?? doSistema();
}

/** Escreve o tema no `<html>`: é o `data-theme="dark"` que liga a paleta escura. */
export function aplicarTema(tema: Tema = getTema()): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = tema === "escuro" ? "dark" : "";
}

/** Guarda a escolha e aplica na hora. */
export function setTema(tema: Tema): void {
  storage.set(CHAVE, tema);
  aplicarTema(tema);
  avisarTodos();
}

function assinar(avisar: () => void): () => void {
  ouvintes.add(avisar);
  return () => { ouvintes.delete(avisar); };
}

/** `[tema, setTema]`; toda tela montada reage à troca. */
export function useTema(): [Tema, (tema: Tema) => void] {
  const tema = useSyncExternalStore(assinar, getTema, getTema);
  return [tema, setTema];
}

// Sem escolha guardada o tema segue o sistema — inclusive quando ele muda com a
// página aberta (o modo escuro que entra sozinho ao anoitecer, por exemplo).
if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
  try {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener?.("change", () => {
      if (guardado()) return;
      aplicarTema();
      avisarTodos();
    });
  } catch {
    /* sistema sem preferência de cor: fica no claro */
  }
}

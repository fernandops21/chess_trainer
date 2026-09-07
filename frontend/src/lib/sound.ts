import { useSyncExternalStore } from "react";
import { storage } from "./storage";

/** Efeitos sonoros do treino e da análise. */
export type SoundKind = "move" | "capture" | "check" | "correct" | "wrong" | "solved" | "hint";

const CHAVE = "sound.enabled";

// ---------------------------------------------------------------- preferência

const ouvintes = new Set<() => void>();
let ligado = storage.get<boolean>(CHAVE, true) !== false;

export function isEnabled(): boolean {
  return ligado;
}

export function setEnabled(valor: boolean): void {
  const novo = !!valor;
  if (novo === ligado) return;
  ligado = novo;
  storage.set(CHAVE, novo);
  for (const avisar of ouvintes) avisar();
}

function assinar(avisar: () => void): () => void {
  ouvintes.add(avisar);
  return () => { ouvintes.delete(avisar); };
}

/** `[ligado, setLigado]`; toda tela montada reage à troca. */
export function useSoundEnabled(): [boolean, (valor: boolean) => void] {
  const valor = useSyncExternalStore(assinar, isEnabled, isEnabled);
  return [valor, setEnabled];
}

/** Som do lance a partir do SAN: xeque na frente de captura. */
export function sanSound(san: string): SoundKind {
  if (san.includes("+") || san.includes("#")) return "check";
  return san.includes("x") ? "capture" : "move";
}

// -------------------------------------------------------------------- síntese

type Janela = typeof window & { webkitAudioContext?: typeof AudioContext };

let ctx: AudioContext | null = null;
// navegador sem Web Audio (ou que reclamou ao criar o contexto): não insiste
let quebrado = false;

function contexto(): AudioContext | null {
  if (ctx) return ctx;
  if (quebrado || typeof window === "undefined") return null;
  try {
    const w = window as Janela;
    const Ctor = w.AudioContext ?? w.webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
  } catch {
    quebrado = true;
    return null;
  }
  return ctx;
}

/** Política de autoplay: o contexto nasce suspenso até um gesto do usuário. */
function retomar(c: AudioContext): void {
  try {
    if (c.state !== "suspended") return;
    const p = c.resume?.();
    if (p && typeof p.catch === "function") p.catch(() => { /* ignorar */ });
  } catch {
    /* ignorar */
  }
}

/** Uma nota curta com ataque rápido e queda exponencial. */
function nota(c: AudioContext, inicio: number, freq: number, durMs: number, pico: number, tipo: OscillatorType = "sine"): void {
  const dur = durMs / 1000;
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.type = tipo;
  osc.frequency.setValueAtTime(freq, inicio);
  g.gain.setValueAtTime(0.0001, inicio);
  g.gain.exponentialRampToValueAtTime(pico, inicio + 0.006);
  g.gain.exponentialRampToValueAtTime(0.0001, inicio + dur);
  osc.connect(g);
  g.connect(c.destination);
  osc.start(inicio);
  osc.stop(inicio + dur + 0.02);
}

/** Estalo de ruído filtrado: é ele que dá o "toc" da peça na casa. */
function clique(c: AudioContext, inicio: number, durMs: number, pico: number, corte: number): void {
  if (typeof c.createBuffer !== "function" || typeof c.createBufferSource !== "function" || typeof c.createBiquadFilter !== "function") return;
  const dur = durMs / 1000;
  const amostras = Math.max(1, Math.floor((c.sampleRate || 44100) * dur));
  const buffer = c.createBuffer(1, amostras, c.sampleRate || 44100);
  const dados = buffer.getChannelData(0);
  for (let i = 0; i < amostras; i++) dados[i] = (Math.random() * 2 - 1) * (1 - i / amostras);
  const fonte = c.createBufferSource();
  fonte.buffer = buffer;
  const filtro = c.createBiquadFilter();
  filtro.type = "lowpass";
  filtro.frequency.setValueAtTime(corte, inicio);
  const g = c.createGain();
  g.gain.setValueAtTime(pico, inicio);
  g.gain.exponentialRampToValueAtTime(0.0001, inicio + dur);
  fonte.connect(filtro);
  filtro.connect(g);
  g.connect(c.destination);
  fonte.start(inicio);
  fonte.stop(inicio + dur + 0.02);
}

/** Toca um efeito. Sem som ligado, sem Web Audio ou com qualquer erro, não faz nada. */
export function play(kind: SoundKind): void {
  if (!ligado) return;
  const c = contexto();
  if (!c) return;
  try {
    retomar(c);
    const t = c.currentTime + 0.005;
    switch (kind) {
      case "move":
        nota(c, t, 180, 60, 0.16);
        clique(c, t, 25, 0.06, 2200);
        break;
      case "capture":
        nota(c, t, 120, 90, 0.25);
        clique(c, t, 35, 0.1, 1400);
        break;
      case "check":
        nota(c, t, 660, 90, 0.16, "triangle");
        break;
      case "correct":
        nota(c, t, 523, 80, 0.14, "triangle");
        nota(c, t + 0.085, 784, 80, 0.14, "triangle");
        break;
      case "wrong":
        nota(c, t, 150, 150, 0.09, "square");
        break;
      case "solved":
        nota(c, t, 523, 90, 0.14, "triangle");
        nota(c, t + 0.095, 659, 90, 0.14, "triangle");
        nota(c, t + 0.19, 784, 140, 0.16, "triangle");
        break;
      case "hint":
        nota(c, t, 440, 80, 0.13, "triangle");
        break;
    }
  } catch {
    /* som nunca derruba a tela */
  }
}

// O contexto nasce suspenso: o primeiro gesto do usuário na página já o retoma,
// para o primeiro som não sair mudo nem atrasado.
function armar(): void {
  // com o som desligado não vale criar o contexto de áudio: `play` cria quando precisar
  if (!isEnabled()) return;
  const c = contexto();
  if (c) retomar(c);
  window.removeEventListener("pointerdown", armar);
  window.removeEventListener("keydown", armar);
}

if (typeof window !== "undefined") {
  window.addEventListener("pointerdown", armar);
  window.addEventListener("keydown", armar);
}

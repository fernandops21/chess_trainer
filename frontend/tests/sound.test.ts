import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { SoundKind } from "../src/lib/sound";

/** Parâmetro de áudio dublê: guarda o que foi agendado para o teste conferir. */
function fakeParam() {
  return {
    value: 0,
    setValueAtTime: vi.fn(),
    exponentialRampToValueAtTime: vi.fn(),
    linearRampToValueAtTime: vi.fn(),
  };
}

type FakeOsc = { type: string; frequency: ReturnType<typeof fakeParam>; connect: ReturnType<typeof vi.fn>; start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn> };
type FakeGain = { gain: ReturnType<typeof fakeParam>; connect: ReturnType<typeof vi.fn> };

/** O jsdom não tem Web Audio: este dublê registra os nós criados. */
function fakeAudio(state: "running" | "suspended" = "running") {
  const criados = { ctx: 0, osc: [] as FakeOsc[], gain: [] as FakeGain[], fontes: 0, filtros: 0, resume: 0 };
  class FakeAudioContext {
    state = state;
    currentTime = 0;
    sampleRate = 44100;
    destination = {};
    constructor() { criados.ctx += 1; }
    resume() { criados.resume += 1; this.state = "running"; return Promise.resolve(); }
    createOscillator(): FakeOsc {
      const o = { type: "sine", frequency: fakeParam(), connect: vi.fn(), start: vi.fn(), stop: vi.fn() };
      criados.osc.push(o);
      return o;
    }
    createGain(): FakeGain {
      const g = { gain: fakeParam(), connect: vi.fn() };
      criados.gain.push(g);
      return g;
    }
    createBuffer(_ch: number, len: number) { return { getChannelData: () => new Float32Array(len) }; }
    createBufferSource() {
      criados.fontes += 1;
      return { buffer: null as unknown, connect: vi.fn(), start: vi.fn(), stop: vi.fn() };
    }
    createBiquadFilter() {
      criados.filtros += 1;
      return { type: "lowpass", frequency: fakeParam(), Q: fakeParam(), connect: vi.fn() };
    }
  }
  (window as unknown as { AudioContext: unknown }).AudioContext = FakeAudioContext;
  return criados;
}

/** Módulo novo a cada teste: o AudioContext e a preferência ficam em cache no módulo. */
async function carregar() {
  vi.resetModules();
  return await import("../src/lib/sound");
}

beforeEach(() => {
  localStorage.clear();
  delete (window as unknown as { AudioContext?: unknown }).AudioContext;
  delete (window as unknown as { webkitAudioContext?: unknown }).webkitAudioContext;
});

afterEach(() => {
  delete (window as unknown as { AudioContext?: unknown }).AudioContext;
  delete (window as unknown as { webkitAudioContext?: unknown }).webkitAudioContext;
});

test("play('move') cria e agenda os nós de áudio", async () => {
  const criados = fakeAudio();
  const { play } = await carregar();
  play("move");
  expect(criados.ctx).toBe(1);
  expect(criados.osc.length).toBeGreaterThan(0);
  expect(criados.gain.length).toBeGreaterThan(0);
  const osc = criados.osc[0];
  expect(osc.frequency.setValueAtTime).toHaveBeenCalledWith(180, expect.any(Number));
  expect(osc.start).toHaveBeenCalled();
  expect(osc.stop).toHaveBeenCalled();
  // o "tock" leva também um clique de ruído filtrado
  expect(criados.fontes).toBe(1);
  expect(criados.filtros).toBe(1);
});

test("cada tipo de som agenda pelo menos um oscilador", async () => {
  const criados = fakeAudio();
  const { play } = await carregar();
  const kinds: SoundKind[] = ["move", "capture", "check", "correct", "wrong", "solved", "hint"];
  for (const kind of kinds) {
    const antes = criados.osc.length;
    play(kind);
    expect(criados.osc.length, kind).toBeGreaterThan(antes);
  }
  // arpejo de três notas ao resolver
  expect(criados.osc.length).toBeGreaterThanOrEqual(kinds.length + 3);
});

test("os ganhos ficam baixos", async () => {
  const criados = fakeAudio();
  const { play } = await carregar();
  play("capture");
  play("solved");
  const valores = criados.gain.flatMap((g) => [
    ...g.gain.setValueAtTime.mock.calls,
    ...g.gain.exponentialRampToValueAtTime.mock.calls,
    ...g.gain.linearRampToValueAtTime.mock.calls,
  ].map((c) => c[0] as number));
  expect(valores.length).toBeGreaterThan(0);
  expect(Math.max(...valores)).toBeLessThanOrEqual(0.25);
});

test("o mesmo AudioContext é reaproveitado", async () => {
  const criados = fakeAudio();
  const { play } = await carregar();
  play("move");
  play("check");
  expect(criados.ctx).toBe(1);
});

test("contexto suspenso é retomado ao tocar", async () => {
  const criados = fakeAudio("suspended");
  const { play } = await carregar();
  play("hint");
  expect(criados.resume).toBeGreaterThan(0);
});

test("com o som desligado, play não cria nada", async () => {
  const criados = fakeAudio();
  const { play, setEnabled, isEnabled } = await carregar();
  expect(isEnabled()).toBe(true);
  setEnabled(false);
  play("move");
  expect(criados.ctx).toBe(0);
  expect(criados.osc.length).toBe(0);
});

test("sem AudioContext no navegador, play não lança", async () => {
  const { play } = await carregar();
  expect(() => play("move")).not.toThrow();
  expect(() => play("solved")).not.toThrow();
});

test("AudioContext que lança no construtor não quebra o play", async () => {
  (window as unknown as { AudioContext: unknown }).AudioContext = function () {
    throw new Error("sem áudio");
  };
  const { play } = await carregar();
  expect(() => play("move")).not.toThrow();
});

test("usa webkitAudioContext quando só ele existe", async () => {
  const criados = fakeAudio();
  const Ctor = (window as unknown as { AudioContext: unknown }).AudioContext;
  delete (window as unknown as { AudioContext?: unknown }).AudioContext;
  (window as unknown as { webkitAudioContext: unknown }).webkitAudioContext = Ctor;
  const { play } = await carregar();
  play("move");
  expect(criados.ctx).toBe(1);
});

test("a preferência fica guardada em sound.enabled", async () => {
  fakeAudio();
  const { isEnabled, setEnabled } = await carregar();
  expect(isEnabled()).toBe(true);
  setEnabled(false);
  expect(localStorage.getItem("sound.enabled")).toBe("false");
  expect(isEnabled()).toBe(false);

  const outro = await carregar();
  expect(outro.isEnabled()).toBe(false);
  outro.setEnabled(true);
  expect(localStorage.getItem("sound.enabled")).toBe("true");
});

test("sanSound classifica pelo SAN", async () => {
  const { sanSound } = await carregar();
  expect(sanSound("Nf3")).toBe("move");
  expect(sanSound("exd5")).toBe("capture");
  expect(sanSound("Qxf7+")).toBe("check");
  expect(sanSound("Rd8#")).toBe("check");
  expect(sanSound("O-O")).toBe("move");
});

test("um ponteiro/tecla retoma o contexto cedo", async () => {
  const criados = fakeAudio("suspended");
  await carregar();
  window.dispatchEvent(new Event("pointerdown"));
  expect(criados.ctx).toBeGreaterThan(0);
  expect(criados.resume).toBeGreaterThan(0);
});

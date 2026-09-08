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

type FakeSource = { buffer: unknown; connect: ReturnType<typeof vi.fn>; start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn> };

/** O jsdom não tem Web Audio: este dublê registra os nós criados. */
function fakeAudio(state: "running" | "suspended" = "running") {
  const criados = { ctx: 0, osc: [] as FakeOsc[], gain: [] as FakeGain[], fontes: [] as FakeSource[], filtros: 0, resume: 0, decode: 0 };
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
    createBufferSource(): FakeSource {
      const fonte = { buffer: null as unknown, connect: vi.fn(), start: vi.fn(), stop: vi.fn() };
      criados.fontes.push(fonte);
      return fonte;
    }
    createBiquadFilter() {
      criados.filtros += 1;
      return { type: "lowpass", frequency: fakeParam(), Q: fakeParam(), connect: vi.fn() };
    }
    decodeAudioData(_dados: ArrayBuffer): Promise<unknown> {
      criados.decode += 1;
      return Promise.resolve({ marca: "amostra-decodificada" });
    }
  }
  (window as unknown as { AudioContext: unknown }).AudioContext = FakeAudioContext;
  return criados;
}

/** Dublê de `fetch`: resolve com um ArrayBuffer, contando as chamadas por URL. */
function fakeFetch() {
  const chamadas: string[] = [];
  const mock = vi.fn((url: string) => {
    chamadas.push(url);
    return Promise.resolve({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)) });
  });
  (globalThis as unknown as { fetch: unknown }).fetch = mock;
  return { mock, chamadas };
}

/** Espera as microtasks de `fetch`+`decodeAudioData` (várias cadeias de `.then`) resolverem. */
async function flush() {
  for (let i = 0; i < 12; i++) await Promise.resolve();
}

/** Módulo novo a cada teste: o AudioContext e a preferência ficam em cache no módulo. */
async function carregar() {
  vi.resetModules();
  return await import("../src/lib/sound");
}

const fetchOriginal = globalThis.fetch;

beforeEach(() => {
  localStorage.clear();
  delete (window as unknown as { AudioContext?: unknown }).AudioContext;
  delete (window as unknown as { webkitAudioContext?: unknown }).webkitAudioContext;
});

afterEach(() => {
  delete (window as unknown as { AudioContext?: unknown }).AudioContext;
  delete (window as unknown as { webkitAudioContext?: unknown }).webkitAudioContext;
  globalThis.fetch = fetchOriginal;
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
  expect(criados.fontes.length).toBe(1);
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

test("o primeiro gesto já busca as amostras dos lances", async () => {
  fakeAudio("suspended");
  const { chamadas } = fakeFetch();
  await carregar();
  window.dispatchEvent(new Event("pointerdown"));
  expect(chamadas).toEqual(["/sound/Move.mp3", "/sound/Capture.mp3"]);
});

test("o primeiro lance depois do gesto já sai da amostra, sem sintetizar", async () => {
  const criados = fakeAudio("suspended");
  await carregar();
  const { play } = await import("../src/lib/sound");
  fakeFetch();
  window.dispatchEvent(new Event("pointerdown"));
  await flush();
  const oscAntes = criados.osc.length;
  play("move");
  expect(criados.fontes.length).toBe(1);
  expect(criados.osc.length).toBe(oscAntes);
});

test("com o som desligado, o gesto não busca amostra nenhuma", async () => {
  fakeAudio("suspended");
  const { mock } = fakeFetch();
  const { setEnabled } = await carregar();
  setEnabled(false);
  window.dispatchEvent(new Event("keydown"));
  expect(mock).not.toHaveBeenCalled();
});

// ------------------------------------------------------------- amostras Lichess

test("depois da amostra carregada, play('move') toca um AudioBufferSourceNode com o buffer decodificado", async () => {
  const criados = fakeAudio();
  const { chamadas } = fakeFetch();
  const { play } = await carregar();

  play("move"); // primeira chamada: amostra ainda não chegou, cai no sintetizado
  await flush();
  expect(chamadas).toEqual(["/sound/Move.mp3"]);
  expect(criados.decode).toBe(1);

  const fontesAntes = criados.fontes.length;
  play("move"); // segunda chamada: amostra já em cache
  expect(criados.fontes.length).toBe(fontesAntes + 1);
  const fonte = criados.fontes[criados.fontes.length - 1];
  expect(fonte.buffer).toEqual({ marca: "amostra-decodificada" });
  expect(fonte.start).toHaveBeenCalled();
});

test("fetch é chamado uma única vez por tipo mesmo com vários play()", async () => {
  const criados = fakeAudio();
  const { mock, chamadas } = fakeFetch();
  const { play } = await carregar();

  play("move");
  play("move");
  play("move");
  await flush();
  play("move");
  play("move");

  expect(chamadas.filter((u) => u === "/sound/Move.mp3").length).toBe(1);
  expect(mock).toHaveBeenCalledTimes(1);
  expect(criados.decode).toBe(1);
});

test("dois tipos que usam a mesma amostra (move e check) compartilham o fetch", async () => {
  const { mock } = fakeFetch();
  fakeAudio();
  const { play } = await carregar();

  play("move");
  play("check");
  await flush();

  expect(mock.mock.calls.filter((c) => c[0] === "/sound/Move.mp3").length).toBe(1);
});

test("falha no fetch mantém o som sintetizado (oscilador) como alternativa", async () => {
  const criados = fakeAudio();
  (globalThis as unknown as { fetch: unknown }).fetch = vi.fn(() => Promise.reject(new Error("rede fora")));
  const { play } = await carregar();

  play("wrong");
  await flush();
  expect(criados.osc.length).toBeGreaterThan(0);

  // depois da falha, novas chamadas continuam usando o sintetizado, sem lançar
  const oscAntes = criados.osc.length;
  expect(() => play("wrong")).not.toThrow();
  expect(criados.osc.length).toBeGreaterThan(oscAntes);
});

test("falha ao decodificar também mantém o sintetizado, sem lançar", async () => {
  const criados = fakeAudio();
  fakeFetch();
  const { play } = await carregar();
  const c = (window as unknown as { AudioContext: { prototype: { decodeAudioData: () => Promise<unknown> } } }).AudioContext;
  c.prototype.decodeAudioData = () => Promise.reject(new Error("mp3 inválido"));

  expect(() => play("solved")).not.toThrow();
  await flush();
  expect(criados.osc.length).toBeGreaterThan(0);
});

test("com o som desligado, play não busca nem decodifica amostra", async () => {
  fakeAudio();
  const { mock } = fakeFetch();
  const { play, setEnabled } = await carregar();
  setEnabled(false);
  play("move");
  await flush();
  expect(mock).not.toHaveBeenCalled();
});

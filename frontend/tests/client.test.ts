import { api, ApiError } from "../src/api/client";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => ({
    ok: status < 400, status, statusText: "ST",
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

test("monta URL e query string sem parâmetros vazios", async () => {
  const fn = mockFetch(200, []);
  await api.games({ category: "rapid", color: undefined, analyzed: false, limit: 50, offset: 0 });
  const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/games?category=rapid&analyzed=false&limit=50&offset=0");
  expect(init.method ?? "GET").toBe("GET");
});

test("POST envia JSON", async () => {
  const fn = mockFetch(201, { id: "r1" });
  await api.review({ puzzle_id: "p1", correct: true, used_hint: false, duration_ms: 1200 });
  const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/reviews");
  expect(init.method).toBe("POST");
  expect(JSON.parse(String(init.body))).toEqual({ puzzle_id: "p1", correct: true, used_hint: false, duration_ms: 1200 });
});

test("erro HTTP vira ApiError com detail", async () => {
  mockFetch(409, { detail: "já existe uma tarefa em andamento" });
  await expect(api.importGames()).rejects.toMatchObject({ status: 409, message: "já existe uma tarefa em andamento" });
  await expect(api.importGames()).rejects.toBeInstanceOf(ApiError);
});

test("erro sem corpo JSON usa statusText", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, statusText: "Boom", json: async () => { throw new Error("no json"); } })));
  await expect(api.status()).rejects.toMatchObject({ status: 500, message: "Boom" });
});

test("api.regenerate sem kind não manda query string", async () => {
  const fn = mockFetch(202, { queued: true, job: "regenerate" });
  await api.regenerate();
  const [url] = fn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/puzzles/regenerate");
});

test("api.regenerate('avoid') manda kind=avoid na query string", async () => {
  const fn = mockFetch(202, { queued: true, job: "regenerate" });
  await api.regenerate("avoid");
  const [url] = fn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/puzzles/regenerate?kind=avoid");
});

test("api.analyse faz POST /api/analyse com fen e multipv padrão", async () => {
  const fn = mockFetch(200, { fen: "f", turn: "white", terminal: null, lines: [] });
  await api.analyse("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
  const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/analyse");
  expect(init.method).toBe("POST");
  expect(JSON.parse(String(init.body))).toEqual({
    fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    multipv: 3,
  });
});

test("api.nextTactic junta temas e exclusões em CSV e omite os vazios", async () => {
  const fn = mockFetch(200, {});
  await api.nextTactic({ themes: ["fork", "pin"], exclude: ["a", "b"] });
  expect((fn.mock.calls[0] as unknown as [string])[0]).toBe("/api/tactics/next?themes=fork%2Cpin&exclude=a%2Cb");
  await api.nextTactic({ exclude: [] });
  expect((fn.mock.calls[1] as unknown as [string])[0]).toBe("/api/tactics/next");
});

test("api.attempt faz POST /api/tactics/attempts com o corpo", async () => {
  const fn = mockFetch(201, { id: "a1" });
  await api.attempt({ puzzle_id: "00sHx", correct: true, used_hint: false, duration_ms: 900 });
  const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/tactics/attempts");
  expect(init.method).toBe("POST");
  expect(JSON.parse(String(init.body))).toEqual({ puzzle_id: "00sHx", correct: true, used_hint: false, duration_ms: 900 });
});

test("api.queue junta as fontes em CSV e passa o estudo", async () => {
  const fn = mockFetch(200, { due_count: 0, new_available: 0, new_remaining_today: 0, items: [] });
  await api.queue({ sources: ["own", "lichess"], study_id: "s1", kind: "punish" });
  expect((fn.mock.calls[0] as unknown as [string])[0]).toBe("/api/queue?kind=punish&sources=own%2Clichess&study_id=s1");
  await api.queue({ sources: [] });
  expect((fn.mock.calls[1] as unknown as [string])[0]).toBe("/api/queue");
});

test("api.setQueue faz POST em /puzzles/{id}/queue", async () => {
  const fn = mockFetch(200, {});
  await api.setQueue("p1", false);
  const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/puzzles/p1/queue");
  expect(init.method).toBe("POST");
  expect(JSON.parse(String(init.body))).toEqual({ in_queue: false });
});

test("api.saveTactic faz POST em /tactics/{id}/save", async () => {
  const fn = mockFetch(201, {});
  await api.saveTactic("00sHx");
  const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/tactics/00sHx/save");
  expect(init.method).toBe("POST");
});

test("api.importStudy manda a URL e api.deleteStudy aceita 204 sem corpo", async () => {
  const fn = mockFetch(202, { queued: true, job: "import_study" });
  await api.importStudy({ url: "https://lichess.org/study/4JKVAfaE" });
  const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/studies/import");
  expect(JSON.parse(String(init.body))).toEqual({ url: "https://lichess.org/study/4JKVAfaE" });

  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 204, statusText: "No Content", json: async () => { throw new Error("sem corpo"); } })));
  await expect(api.deleteStudy("s1")).resolves.toBeUndefined();
});

test("detail em lista vira uma mensagem só e guarda as linhas", async () => {
  mockFetch(422, { detail: ["lance ilegal no nó n3: e2e5", "comentário longo demais"] });
  await expect(api.status()).rejects.toMatchObject({
    status: 422,
    message: "lance ilegal no nó n3: e2e5; comentário longo demais",
    details: ["lance ilegal no nó n3: e2e5", "comentário longo demais"],
  });
});

test("detail que não é texto nem lista de textos vira JSON", async () => {
  mockFetch(422, { detail: [{ loc: ["body", "name"], msg: "campo obrigatório" }] });
  await expect(api.status()).rejects.toMatchObject({
    status: 422,
    message: '[{"loc":["body","name"],"msg":"campo obrigatório"}]',
    details: undefined,
  });
});

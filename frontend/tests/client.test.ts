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

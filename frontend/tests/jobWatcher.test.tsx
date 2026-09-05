import { act, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useJobWatcher } from "../src/api/queries";

let jobState: "idle" | "running" | "error" = "running";

const statusPayload = () => ({
  engine: { available: true, path: null },
  job: { state: jobState, job: "analyze", stage: "", done: 0, total: 0, message: "", error: null, finished_at: null },
  games_total: 0,
  games_pending: 0,
  last_import_at: null,
  local_url: "http://127.0.0.1:8000",
});

function Watcher() {
  useJobWatcher();
  return <div>watcher</div>;
}

beforeEach(() => {
  jobState = "running";
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => statusPayload() })));
});
afterEach(() => vi.unstubAllGlobals());

test("invalida as queries quando o job sai de running", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  render(
    <QueryClientProvider client={qc}>
      <Watcher />
    </QueryClientProvider>,
  );

  await waitFor(() => expect(qc.getQueryData(["status"])).toBeTruthy());
  expect(spy).not.toHaveBeenCalledWith({ queryKey: ["dashboard"] });

  jobState = "idle";
  await act(async () => {
    await qc.refetchQueries({ queryKey: ["status"] });
  });

  await waitFor(() => expect(spy).toHaveBeenCalledWith({ queryKey: ["dashboard"] }));
  for (const k of ["status", "queue", "games", "game", "mistakes", "leeches"]) {
    expect(spy).toHaveBeenCalledWith({ queryKey: [k] });
  }
});

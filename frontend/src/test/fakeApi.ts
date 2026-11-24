import { vi, type MockedFunction } from "vitest";
import type { Schemas } from "../api/client";
import type { ApiError, ProductApi, Result } from "../api/productApi";
import orientOk from "../../fixtures/product/orient_ok.json";
import locateOk from "../../fixtures/product/locate_ok.json";
import readinessReady from "../../fixtures/product/readiness_ready.json";
import reposList from "../../fixtures/product/repos_list.json";
import askOk from "../../fixtures/product/ask_ok.json";
import investigationPartial from "../../fixtures/product/investigation_finished_partial.json";
import investigationCitation from "../../fixtures/product/investigation_citation_ok.json";
import investigationRunning from "../../fixtures/product/investigation_running.json";

// The fixtures are the contract fixtures validated against the OpenAPI schema
// by the Python tests; JSON imports widen enum strings, hence the assertions.
export const REPO_A = reposList.body.repos[0]!.repo_id;
export const REPO_B = "00000000-0000-4000-8000-0000000000b2";
export const GEN_A = readinessReady.body.generation_id;
export const GEN_B = "00000000-0000-4000-8000-0000000000c3";

export const repos = {
  repos: [
    ...reposList.body.repos,
    { ...reposList.body.repos[0]!, repo_id: REPO_B, display_name: "acme/other" },
  ],
} as Schemas["ProductRepoList"];

export const readiness = readinessReady.body as Schemas["Readiness"];
export const orient = orientOk.body as Schemas["ProductOrient"];
export const locate = locateOk.body as Schemas["ProductLocate"];

export const runningRecord =
  investigationRunning.body as Schemas["ProductInvestigation"];
export const partialRecord =
  investigationPartial.body as Schemas["ProductInvestigation"];

export const citationText =
  investigationCitation.body as Schemas["InvestigationCitationText"];

export const askAnswer = askOk.body as Schemas["ProductAsk"];

/** A 40-line file; returns exactly the requested inclusive interval. */
export function sourceFor(
  start = 1,
  end = 40,
  extra: Partial<Schemas["ProductSource"]> = {},
): Schemas["ProductSource"] {
  const last = Math.min(end, 40);
  const lines = [];
  for (let n = start; n <= last; n++) lines.push(`line ${n}`);
  return {
    repo_id: REPO_A,
    generation_id: GEN_A,
    commit_sha: null,
    path: "pkg/mod.py",
    canonical_id: "pkg/mod.py",
    document_id: "doc-0",
    doc_type: "python source",
    representation: "stored_source",
    start_line: start,
    end_line: last,
    complete_file: start === 1 && last === 40,
    next_start_line: last < 40 ? last + 1 : null,
    text: lines.join("\n") + "\n",
    returned_text_sha256: "0".repeat(64),
    text_sha256: null,
    total_lines: 40,
    envelope: { schema_version: "1", repo_id: REPO_A, generation_id: GEN_A },
    ...extra,
  } as Schemas["ProductSource"];
}

export const ok = <T>(data: T): Result<T> => ({ ok: true, data });

export const fail = (
  code: ApiError["code"],
  message = "failed",
  status = 503,
): Result<never> => ({
  ok: false,
  error: { status, code, message, details: {} },
});

export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

export type FakeApi = {
  [K in keyof ProductApi]: MockedFunction<ProductApi[K]>;
};

export function makeApi(overrides: Partial<ProductApi> = {}) {
  const api = {
    listRepos: vi.fn(async () => ok(repos)),
    readiness: vi.fn(async (repoId: string) =>
      ok({
        ...readiness,
        repo_id: repoId,
        generation_id: repoId === REPO_B ? GEN_B : GEN_A,
      } as Schemas["Readiness"]),
    ),
    orient: vi.fn(async (repoId: string, generationId: string) =>
      ok({ ...orient, repo_id: repoId, generation_id: generationId }),
    ),
    locate: vi.fn(async () => ok(locate)),
    source: vi.fn(async (_r: string, _g: string, _p: string, s = 1, e = 40) =>
      ok(sourceFor(s, e)),
    ),
    ask: vi.fn(async () => ok(askAnswer)),
    capabilities: vi.fn(async () => ok({ ask: true, investigate: false })),
    startInvestigation: vi.fn(async () => ok(runningRecord)),
    getInvestigation: vi.fn(async () => ok(partialRecord)),
    getInvestigationCitation: vi.fn(async () => ok(citationText)),
    ...overrides,
  };
  return api as unknown as FakeApi;
}

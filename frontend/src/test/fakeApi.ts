import { vi, type MockedFunction } from "vitest";
import type { Schemas } from "../api/client";
import type { ApiError, ProductApi, Result } from "../api/productApi";
import orientOk from "../../fixtures/product/orient_ok.json";
import locateOk from "../../fixtures/product/locate_ok.json";
import readinessReady from "../../fixtures/product/readiness_ready.json";
import reposList from "../../fixtures/product/repos_list.json";

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
    ...overrides,
  };
  return api as unknown as FakeApi;
}

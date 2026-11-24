// The browser's view of the product API: a small interface so components and
// tests do not depend on fetch. Every method resolves; failures are values
// (`ok: false`) carrying the stable product error code, never thrown.
import { createProductClient, type ProductErrorCode, type Schemas } from "./client";

export type ApiErrorCode = ProductErrorCode | "network" | "unexpected";

export interface ApiError {
  status: number;
  code: ApiErrorCode;
  message: string;
  details: Record<string, unknown>;
}

export type Result<T> = { ok: true; data: T } | { ok: false; error: ApiError };

export interface ProductApi {
  listRepos(): Promise<Result<Schemas["ProductRepoList"]>>;
  readiness(repoId: string): Promise<Result<Schemas["Readiness"]>>;
  orient(
    repoId: string,
    generationId: string,
  ): Promise<Result<Schemas["ProductOrient"]>>;
  locate(
    repoId: string,
    generationId: string,
    query: string,
    cursor?: string,
  ): Promise<Result<Schemas["ProductLocate"]>>;
  source(
    repoId: string,
    generationId: string,
    path: string,
    startLine?: number,
    endLine?: number,
  ): Promise<Result<Schemas["ProductSource"]>>;
  ask(
    repoId: string,
    generationId: string,
    question: string,
  ): Promise<Result<Schemas["ProductAsk"]>>;
  capabilities(): Promise<Result<Schemas["Capabilities"]>>;
  startInvestigation(
    repoId: string,
    generationId: string,
    question: string,
  ): Promise<Result<Schemas["ProductInvestigation"]>>;
  getInvestigation(
    repoId: string,
    runId: string,
  ): Promise<Result<Schemas["ProductInvestigation"]>>;
  getInvestigationCitation(
    repoId: string,
    runId: string,
    citationId: string,
  ): Promise<Result<Schemas["InvestigationCitationText"]>>;
}

type Settled<T> = {
  data?: T;
  error?: unknown;
  response: { status: number };
};

function isProductError(
  value: unknown,
): value is Schemas["ProductErrorResponse"] {
  const error = (value as { error?: { code?: unknown } } | null)?.error;
  return typeof error?.code === "string";
}

function settle<T>(call: Settled<T>): Result<T> {
  if (call.data !== undefined) return { ok: true, data: call.data };
  if (isProductError(call.error)) {
    const { code, message, details } = call.error.error;
    return {
      ok: false,
      error: {
        status: call.response.status,
        code,
        message,
        details: details ?? {},
      },
    };
  }
  return {
    ok: false,
    error: {
      status: call.response.status,
      code: "unexpected",
      message: "The service returned an unexpected response.",
      details: {},
    },
  };
}

async function guarded<T>(run: () => Promise<Settled<T>>): Promise<Result<T>> {
  try {
    return settle(await run());
  } catch {
    return {
      ok: false,
      error: {
        status: 0,
        code: "network",
        message: "The service could not be reached.",
        details: {},
      },
    };
  }
}

export function createHttpProductApi(baseUrl = ""): ProductApi {
  const client = createProductClient(baseUrl);
  return {
    listRepos: () => guarded(() => client.GET("/v1/product/repos")),
    readiness: (repoId) =>
      guarded(() =>
        client.GET("/v1/product/repos/{repo_id}/readiness", {
          params: { path: { repo_id: repoId } },
        }),
      ),
    orient: (repoId, generationId) =>
      guarded(() =>
        client.GET("/v1/product/repos/{repo_id}/orient", {
          params: {
            path: { repo_id: repoId },
            query: { generation_id: generationId },
          },
        }),
      ),
    locate: (repoId, generationId, query, cursor) =>
      guarded(() =>
        client.GET("/v1/product/repos/{repo_id}/locate", {
          params: {
            path: { repo_id: repoId },
            query: { generation_id: generationId, query, cursor },
          },
        }),
      ),
    source: (repoId, generationId, path, startLine, endLine) =>
      guarded(() =>
        client.GET("/v1/product/repos/{repo_id}/source", {
          params: {
            path: { repo_id: repoId },
            query: {
              generation_id: generationId,
              path,
              start_line: startLine,
              end_line: endLine,
            },
          },
        }),
      ),
    ask: (repoId, generationId, question) =>
      guarded(() =>
        client.POST("/v1/product/repos/{repo_id}/ask", {
          params: { path: { repo_id: repoId } },
          body: { question, generation_id: generationId },
        }),
      ),
    capabilities: () => guarded(() => client.GET("/v1/product/capabilities")),
    startInvestigation: (repoId, generationId, question) =>
      guarded(() =>
        client.POST("/v1/product/repos/{repo_id}/investigations", {
          params: { path: { repo_id: repoId } },
          body: { question, generation_id: generationId },
        }),
      ),
    getInvestigationCitation: (repoId, runId, citationId) =>
      guarded(() =>
        client.GET(
          "/v1/product/repos/{repo_id}/investigations/{run_id}/citations/{citation_id}",
          {
            params: {
              path: { repo_id: repoId, run_id: runId, citation_id: citationId },
            },
          },
        ),
      ),
    getInvestigation: (repoId, runId) =>
      guarded(() =>
        client.GET("/v1/product/repos/{repo_id}/investigations/{run_id}", {
          params: { path: { repo_id: repoId, run_id: runId } },
        }),
      ),
  };
}

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { Schemas } from "./api/client";
import {
  GEN_A,
  GEN_B,
  REPO_A,
  REPO_B,
  deferred,
  type FakeApi,
  fail,
  locate,
  makeApi,
  ok,
  orient,
  readiness,
} from "./test/fakeApi";

async function openRepo(api: FakeApi, repoId = REPO_A) {
  const user = userEvent.setup();
  render(<App api={api} />);
  await user.selectOptions(await screen.findByLabelText(/repository/i), repoId);
  return user;
}

describe("repository selection and readiness", () => {
  it("shows the indexed generation and commit once a repository is selected", async () => {
    await openRepo(makeApi());
    expect(await screen.findByText(GEN_A)).toBeInTheDocument();
    expect(screen.getByText("a".repeat(12))).toBeInTheDocument();
  });

  it("says plainly when the commit is not recorded", async () => {
    const api = makeApi({
      readiness: vi.fn(async () =>
        ok({ ...readiness, commit_sha: null } as Schemas["Readiness"]),
      ),
    });
    await openRepo(api);
    expect(
      await screen.findByText(/not recorded for this generation/i),
    ).toBeInTheDocument();
  });

  it("disables questions and source reads when no generation is ready", async () => {
    const api = makeApi({
      readiness: vi.fn(async () =>
        fail("unavailable", "repository has no ready generation"),
      ),
    });
    await openRepo(api);
    expect(
      await screen.findByText(/questions and source reads are unavailable/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Overview" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Find files" })).toBeNull();
    expect(api.orient).not.toHaveBeenCalled();
  });

  it("offers a retry when the repository list cannot be loaded", async () => {
    const api = makeApi();
    api.listRepos.mockResolvedValueOnce(fail("network", "could not be reached", 0));
    const user = userEvent.setup();
    render(<App api={api} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/i);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText(/repository/i)).toBeInTheDocument();
  });
});

describe("overview", () => {
  it("displays the limits the backend reports", async () => {
    await openRepo(makeApi());
    const overview = await screen.findByRole("region", { name: "Overview" });
    expect(within(overview).getByText(/python: 3/)).toBeInTheDocument();
    expect(within(overview).getByText(/test_dirs is heuristic/)).toBeInTheDocument();
    expect(
      within(overview).getByText(/services: no compose file found/),
    ).toBeInTheDocument();
  });

  it("requests the overview for exactly the pinned generation", async () => {
    const api = makeApi();
    await openRepo(api);
    await screen.findByRole("region", { name: "Overview" });
    expect(api.orient).toHaveBeenCalledWith(REPO_A, GEN_A);
  });
});

describe("file search", () => {
  async function search(api: FakeApi, text = "mod.py") {
    const user = await openRepo(api);
    await user.type(await screen.findByLabelText(/path, file name or glob/i), text);
    await user.click(screen.getByRole("button", { name: "Search" }));
    return user;
  }

  it("keeps ambiguous matches individually selectable", async () => {
    const user = await search(makeApi());
    const python = await screen.findByRole("button", { name: "pkg/mod.py" });
    const typescript = screen.getByRole("button", { name: "web/mod.ts" });
    await user.click(typescript);
    expect(typescript).toHaveAttribute("aria-pressed", "true");
    expect(python).toHaveAttribute("aria-pressed", "false");
  });

  it("shows verified Python definitions with spans and labels unsupported coverage", async () => {
    await search(makeApi());
    expect(await screen.findByText(/function a \(lines 1–2\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/definitions are not available for this language/i),
    ).toBeInTheDocument();
  });

  it("labels this as file search, not semantic search", async () => {
    await openRepo(makeApi());
    expect(
      await screen.findByText(/definition-name and semantic search are not available/i),
    ).toBeInTheDocument();
  });

  it("paginates with the original query and generation even if the input changed", async () => {
    const page1 = { ...locate, next_cursor: "page-2" } as Schemas["ProductLocate"];
    const page2 = {
      ...locate,
      candidates: [{ ...locate.candidates[0]!, path: "pkg/second.py", canonical_id: "pkg/second.py" }],
      next_cursor: null,
    } as Schemas["ProductLocate"];
    const api = makeApi({
      locate: vi.fn(async (_r: string, _g: string, _q: string, cursor?: string) =>
        ok(cursor ? page2 : page1),
      ),
    });
    const user = await search(api, "mod.py");
    await screen.findByRole("button", { name: "pkg/mod.py" });
    const input = screen.getByLabelText(/path, file name or glob/i);
    await user.clear(input);
    await user.type(input, "something-else");
    await user.click(screen.getByRole("button", { name: "Load more files" }));
    expect(await screen.findByRole("button", { name: "pkg/second.py" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "pkg/mod.py" })).toBeInTheDocument();
    expect(api.locate).toHaveBeenLastCalledWith(REPO_A, GEN_A, "mod.py", "page-2");
    expect(screen.queryByRole("button", { name: "Load more files" })).toBeNull();
  });

  it("says so when nothing matches", async () => {
    const empty = { ...locate, candidates: [], next_cursor: null } as Schemas["ProductLocate"];
    await search(makeApi({ locate: vi.fn(async () => ok(empty)) }), "nothing");
    expect(await screen.findByText(/no files matched “nothing”/i)).toBeInTheDocument();
  });

  it("shows a service error instead of results", async () => {
    await search(
      makeApi({ locate: vi.fn(async () => fail("resource_limit", "too large", 413)) }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/too large/);
    expect(screen.queryByRole("button", { name: "pkg/mod.py" })).toBeNull();
  });

  it("renders paths as text, never as markup", async () => {
    const hostile = {
      ...locate,
      candidates: [
        { ...locate.candidates[0]!, path: "<img src=x onerror=alert(1)>.py", canonical_id: "h" },
      ],
    } as Schemas["ProductLocate"];
    await search(makeApi({ locate: vi.fn(async () => ok(hostile)) }));
    expect(
      await screen.findByRole("button", { name: "<img src=x onerror=alert(1)>.py" }),
    ).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("context changes", () => {
  it("never shows a late response from the previous repository", async () => {
    const slow = deferred<ReturnType<typeof ok<Schemas["ProductOrient"]>>>();
    const api = makeApi({
      orient: vi.fn(async (repoId: string, generationId: string) =>
        repoId === REPO_A
          ? slow.promise
          : ok({ ...orient, repo_id: repoId, generation_id: generationId, languages: { rust: 7 } }),
      ),
    });
    const user = await openRepo(api, REPO_A);
    await waitFor(() => expect(api.orient).toHaveBeenCalledWith(REPO_A, GEN_A));
    await user.selectOptions(screen.getByLabelText(/repository/i), REPO_B);
    expect(await screen.findByText(/rust: 7/)).toBeInTheDocument();
    slow.resolve(ok({ ...orient, languages: { cobol: 1 } }));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/cobol/)).toBeNull();
    expect(screen.getByText(/rust: 7/)).toBeInTheDocument();
  });

  it("clears results and offers a refresh when the generation is stale", async () => {
    const api = makeApi();
    const user = await openRepo(api);
    await user.type(await screen.findByLabelText(/path, file name or glob/i), "mod.py");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByRole("button", { name: "pkg/mod.py" });

    api.locate.mockResolvedValueOnce(fail("stale", "generation is not current", 409));
    api.readiness.mockResolvedValue(
      ok({ ...readiness, generation_id: GEN_B } as Schemas["Readiness"]),
    );
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText(/this repository was re-indexed/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "pkg/mod.py" })).toBeNull();

    await user.click(
      screen.getByRole("button", { name: /refresh to the current generation/i }),
    );
    expect(await screen.findByText(GEN_B)).toBeInTheDocument();
    await waitFor(() => expect(api.orient).toHaveBeenLastCalledWith(REPO_A, GEN_B));
    expect(screen.queryByRole("button", { name: "pkg/mod.py" })).toBeNull();
  });
});

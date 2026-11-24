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
  askAnswer,
  deferred,
  fail,
  makeApi,
  ok,
  readiness,
  sourceFor,
  type FakeApi,
} from "./test/fakeApi";

const answerWith = (
  overrides: Partial<Schemas["ProductAsk"]>,
): Schemas["ProductAsk"] => ({ ...askAnswer, ...overrides });

async function openAndAsk(api: FakeApi, question = "What does it do?") {
  const user = userEvent.setup();
  render(<App api={api} />);
  await user.selectOptions(await screen.findByLabelText(/repository/i), REPO_A);
  await user.type(await screen.findByLabelText(/question/i), question);
  await user.click(screen.getByRole("button", { name: "Ask" }));
  return user;
}

function rows() {
  return Array.from(document.querySelectorAll("tr[data-line]")) as HTMLElement[];
}

describe("Ask", () => {
  it("answers with the indexed generation and the evidence", async () => {
    const api = makeApi();
    await openAndAsk(api);
    const article = await screen.findByRole("article");
    expect(within(article).getByText("It does X.")).toBeInTheDocument();
    expect(article).toHaveTextContent(`Indexed generation ${GEN_A}`);
    expect(article).toHaveTextContent("commit aaaaaaaaaaaa");
    expect(api.ask).toHaveBeenCalledWith(REPO_A, GEN_A, "What does it do?");
  });

  it("labels evidence as consulted passages, not claim-level support", async () => {
    await openAndAsk(makeApi());
    expect(
      await screen.findByRole("heading", { name: "Consulted passages" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/do not show which statement in the answer/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/supports this claim/i)).toBeNull();
  });

  it("shows a recoverable error and retries", async () => {
    const api = makeApi();
    api.ask.mockResolvedValueOnce(fail("network", "could not be reached", 0));
    const user = await openAndAsk(api);
    expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/i);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("It does X.")).toBeInTheDocument();
    expect(api.ask).toHaveBeenCalledTimes(2);
  });

  it("sanitizes answer Markdown: no raw HTML, no script, no javascript: links", async () => {
    const hostile = answerWith({
      answer:
        "**bold** <script>alert(1)</script> <img src=x onerror=alert(1)> " +
        "[click](javascript:alert(1)) [ok](https://example.com/docs)",
    });
    await openAndAsk(makeApi({ ask: vi.fn(async () => ok(hostile)) }));
    const article = await screen.findByRole("article");
    expect(article.querySelector("strong")).toHaveTextContent("bold");
    expect(document.querySelector("script")).toBeNull();
    expect(article.querySelector("img")).toBeNull();
    const hrefs = Array.from(article.querySelectorAll("a")).map((a) =>
      a.getAttribute("href"),
    );
    expect(hrefs).not.toContain("javascript:alert(1)");
    expect(hrefs.some((h) => h?.startsWith("javascript:"))).toBe(false);
    expect(hrefs).toContain("https://example.com/docs");
  });

  it("allows one question at a time and keeps the pending state visible", async () => {
    const pending = deferred<ReturnType<typeof ok<Schemas["ProductAsk"]>>>();
    const api = makeApi({ ask: vi.fn(() => pending.promise) });
    await openAndAsk(api, "first?");
    const busy = await screen.findByRole("button", { name: "Asking…" });
    expect(busy).toBeDisabled();
    expect(api.ask).toHaveBeenCalledTimes(1);
    pending.resolve(ok(answerWith({ answer: "first answer" })));
    expect(await screen.findByText("first answer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });

  it("never shows an answer that finishes after the repository changed", async () => {
    const slow = deferred<ReturnType<typeof ok<Schemas["ProductAsk"]>>>();
    const api = makeApi({ ask: vi.fn(() => slow.promise) });
    const user = await openAndAsk(api);
    await user.selectOptions(screen.getByLabelText(/repository/i), REPO_B);
    await screen.findByText(GEN_B);
    slow.resolve(ok(answerWith({ answer: "answer about the old repository" })));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/old repository/)).toBeNull();
  });

  it("offers refresh and rerun when the generation is stale", async () => {
    const api = makeApi();
    api.ask.mockResolvedValueOnce(fail("stale", "generation is not current", 409));
    const user = await openAndAsk(api, "Where is auth?");
    expect(await screen.findByText(/this repository was re-indexed/i)).toBeInTheDocument();
    api.readiness.mockResolvedValue(
      ok({ ...readiness, generation_id: GEN_B } as Schemas["Readiness"]),
    );
    await user.click(
      screen.getByRole("button", { name: /refresh and rerun my last question/i }),
    );
    await waitFor(() =>
      expect(api.ask).toHaveBeenLastCalledWith(REPO_A, GEN_B, "Where is auth?"),
    );
    expect(await screen.findByText("It does X.")).toBeInTheDocument();
  });
});

describe("Verify: citations and the shared source viewer", () => {
  it("opens the cited revision and highlights only the returned interval", async () => {
    const api = makeApi();
    const user = await openAndAsk(api);
    await user.click(await screen.findByRole("button", { name: "Show lines 1–2" }));
    await screen.findByRole("region", { name: "Source viewer" });
    // The cited generation is passed, with a bounded window around the cite.
    expect(api.source).toHaveBeenCalledWith(REPO_A, GEN_A, "pkg/mod.py", 1, 12);
    await waitFor(() => expect(rows().length).toBe(12));
    const marked = rows()
      .filter((r) => r.dataset.highlighted === "true")
      .map((r) => r.dataset.line);
    expect(marked).toEqual(["1", "2"]);
  });

  it("windows around a mid-file citation and highlights exactly the cited lines", async () => {
    const cited = answerWith({
      citations: [
        { ...askAnswer.citations[0]!, start_line: 20, end_line: 22 },
      ],
    });
    const api = makeApi({ ask: vi.fn(async () => ok(cited)) });
    const user = await openAndAsk(api);
    await user.click(await screen.findByRole("button", { name: "Show lines 20–22" }));
    expect(api.source).toHaveBeenCalledWith(REPO_A, GEN_A, "pkg/mod.py", 10, 32);
    await waitFor(() => expect(rows().length).toBe(23));
    expect(
      rows()
        .filter((r) => r.dataset.highlighted === "true")
        .map((r) => r.dataset.line),
    ).toEqual(["20", "21", "22"]);
  });

  it("keeps a citation without a range visible, with its reason, and highlights nothing", async () => {
    const noRange = answerWith({
      citations: [
        {
          repo_id: REPO_A,
          generation_id: GEN_A,
          path: "README.md",
          start_line: null,
          end_line: null,
          range_reason: "line span not persisted at ingestion",
        },
      ],
    });
    const api = makeApi({ ask: vi.fn(async () => ok(noRange)) });
    const user = await openAndAsk(api);
    expect(await screen.findByText("README.md")).toBeInTheDocument();
    expect(
      screen.getByText(/no usable line range: line span not persisted at ingestion/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /show lines/i })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Open file (no highlight)" }));
    await waitFor(() => expect(rows().length).toBeGreaterThan(0));
    expect(rows().every((r) => r.dataset.highlighted === "false")).toBe(true);
  });

  it("disables the jump for a citation from an older generation", async () => {
    const older = answerWith({
      citations: [{ ...askAnswer.citations[0]!, generation_id: GEN_B }],
    });
    const api = makeApi({ ask: vi.fn(async () => ok(older)) });
    await openAndAsk(api);
    expect(await screen.findByText(/older generation: the source jump is disabled/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /show lines/i })).toBeNull();
    expect(api.source).not.toHaveBeenCalled();
  });

  it("renders source as text, never as markup", async () => {
    const api = makeApi({
      source: vi.fn(async () =>
        ok(sourceFor(1, 2, { text: "<b>bold</b>\n<img src=x onerror=alert(1)>\n", end_line: 2 })),
      ),
    });
    const user = await openAndAsk(api);
    await user.click(await screen.findByRole("button", { name: "Show lines 1–2" }));
    expect(await screen.findByText("<b>bold</b>")).toBeInTheDocument();
    expect(document.querySelector("table.source b")).toBeNull();
    expect(document.querySelector("table.source img")).toBeNull();
  });

  it("does not highlight when the cited lines are outside the returned range", async () => {
    const api = makeApi({
      source: vi.fn(async () => ok(sourceFor(1, 3))),
    });
    const cited = answerWith({
      citations: [{ ...askAnswer.citations[0]!, start_line: 30, end_line: 31 }],
    });
    api.ask.mockResolvedValue(ok(cited));
    const user = await openAndAsk(api);
    await user.click(await screen.findByRole("button", { name: "Show lines 30–31" }));
    expect(await screen.findByText(/not within the returned range/i)).toBeInTheDocument();
    expect(rows().every((r) => r.dataset.highlighted === "false")).toBe(true);
  });

  it("says where a partial read continues", async () => {
    const user = await openAndAsk(makeApi());
    await user.click(await screen.findByRole("button", { name: "Show lines 1–2" }));
    expect(await screen.findByText(/the file continues at line 13/i)).toBeInTheDocument();
  });

  it.each([
    ["stale", "generation is not current", 409, /re-indexed/i],
    ["not_found", "File not found in generation", 404, /not found/i],
    ["resource_limit", "At most 500 lines per read", 413, /too large/i],
    ["unavailable", "Source service unavailable", 503, /not available/i],
    ["invalid_range", "Start line is beyond EOF", 416, /invalid line range/i],
  ] as const)("shows a %s source error visibly", async (code, message, status, title) => {
    const api = makeApi({
      source: vi.fn(async () => fail(code, message, status)),
    });
    const user = await openAndAsk(api);
    await user.click(await screen.findByRole("button", { name: "Show lines 1–2" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert).toHaveTextContent(title);
  });

  it("opens a file picked in file search in the same viewer", async () => {
    const api = makeApi();
    const user = userEvent.setup();
    render(<App api={api} />);
    await user.selectOptions(await screen.findByLabelText(/repository/i), REPO_A);
    await user.type(await screen.findByLabelText(/path, file name or glob/i), "mod.py");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(await screen.findByRole("button", { name: "pkg/mod.py" }));
    expect(api.source).toHaveBeenCalledWith(REPO_A, GEN_A, "pkg/mod.py", 1, 100);
    expect(await screen.findByRole("region", { name: "Source viewer" })).toBeInTheDocument();
  });
});

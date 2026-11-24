import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { Schemas } from "./api/client";
import { stopReasonLabel } from "./components/InvestigatePanel";
import {
  GEN_A,
  GEN_B,
  REPO_A,
  fail,
  makeApi,
  ok,
  partialRecord,
  runningRecord,
  type FakeApi,
} from "./test/fakeApi";

type Rec = Schemas["ProductInvestigation"];
const finished = (over: Partial<Rec> = {}): Rec => ({ ...partialRecord, ...over });

function enabledApi(overrides: Parameters<typeof makeApi>[0] = {}) {
  return makeApi({
    capabilities: vi.fn(async () => ok({ ask: true, investigate: true })),
    ...overrides,
  });
}

async function openAndInvestigate(api: FakeApi, question = "Where is recovery?") {
  const user = userEvent.setup();
  render(<App api={api} investigatePollMs={5} />);
  await user.selectOptions(await screen.findByLabelText(/repository/i), REPO_A);
  const panel = await screen.findByRole("region", { name: "Investigate" });
  const textarea = panel.querySelector("textarea") as HTMLTextAreaElement;
  await user.type(textarea, question);
  await user.click(panel.querySelector("button[type=submit]") as HTMLButtonElement);
  return user;
}

describe("capability gating", () => {
  it("hides Investigate unless the deployment enables it, and Ask is unaffected", async () => {
    const api = makeApi();
    const user = userEvent.setup();
    render(<App api={api} />);
    await user.selectOptions(await screen.findByLabelText(/repository/i), REPO_A);
    await screen.findByRole("region", { name: "Ask" });
    expect(screen.queryByRole("region", { name: "Investigate" })).toBeNull();
  });

  it("hides Investigate when the capability lookup fails", async () => {
    const api = makeApi({
      capabilities: vi.fn(async () => fail("network", "unreachable", 0)),
    });
    const user = userEvent.setup();
    render(<App api={api} />);
    await user.selectOptions(await screen.findByLabelText(/repository/i), REPO_A);
    await screen.findByRole("region", { name: "Ask" });
    expect(screen.queryByRole("region", { name: "Investigate" })).toBeNull();
  });
});

describe("Investigate run record", () => {
  it("starts a generation-pinned run and polls until it finishes", async () => {
    const api = enabledApi();
    api.getInvestigation
      .mockResolvedValueOnce(ok(runningRecord))
      .mockResolvedValue(ok(finished()));
    await openAndInvestigate(api);
    expect(api.startInvestigation).toHaveBeenCalledWith(REPO_A, GEN_A, "Where is recovery?");
    expect(await screen.findByText(/Account recovery is handled in auth.py/)).toBeInTheDocument();
    expect(api.getInvestigation).toHaveBeenCalledWith(REPO_A, runningRecord.run_id);
    expect(api.getInvestigation.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("shows findings, admitted evidence, open gaps and the stop reason for a partial run", async () => {
    await openAndInvestigate(enabledApi());
    expect(await screen.findByText(/Partial: some statements/)).toBeInTheDocument();
    expect(screen.getByText(/repeated an action and was stopped/i)).toBeInTheDocument();
    expect(screen.getByText("app/auth.py")).toBeInTheDocument();
    expect(screen.getByText("The email template was not read.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Open gaps" })).toBeInTheDocument();
  });

  it("treats no findings as a normal result with its reason", async () => {
    const api = enabledApi();
    api.getInvestigation.mockResolvedValue(
      ok(finished({ outcome: "none", stop_reason: "invalid_model_output", findings: [], open_gaps: [] })),
    );
    await openAndInvestigate(api);
    expect(await screen.findByText("No supported findings")).toBeInTheDocument();
    expect(screen.getByText(/could not accept/i)).toBeInTheDocument();
    expect(screen.getByText("No findings were recorded.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows an unknown stop reason and outcome through the default branch", async () => {
    const api = enabledApi();
    api.getInvestigation.mockResolvedValue(
      ok(finished({ outcome: "unknown", stop_reason: "a_reason_added_later", findings: [] })),
    );
    await openAndInvestigate(api);
    expect(await screen.findByText("Result not classified")).toBeInTheDocument();
    expect(screen.getByText(/Stopped: a_reason_added_later/)).toBeInTheDocument();
  });

  it("labels fixture runs as synthetic", async () => {
    const api = enabledApi();
    api.getInvestigation.mockResolvedValue(ok(finished({ evidence_mode: "fixture" })));
    await openAndInvestigate(api);
    expect(await screen.findByText(/synthetic fixture data/i)).toBeInTheDocument();
  });

  it("opens an admitted reference in the shared viewer, pinned to its generation", async () => {
    const api = enabledApi();
    const user = await openAndInvestigate(api);
    await user.click(await screen.findByRole("button", { name: "Show lines 10–14" }));
    expect(api.source).toHaveBeenCalledWith(REPO_A, GEN_A, "app/auth.py", 1, 24);
    await screen.findByRole("region", { name: "Source viewer" });
    await waitFor(() =>
      expect(
        Array.from(document.querySelectorAll("tr[data-highlighted=true]")).map(
          (r) => (r as HTMLElement).dataset.line,
        ),
      ).toEqual(["10", "11", "12", "13", "14"]),
    );
  });

  it("disables the jump for evidence from an older generation", async () => {
    const api = enabledApi();
    const old = finished();
    old.findings = [
      {
        statement: "Old claim",
        evidence: [{ ...partialRecord.findings![0]!.evidence[0]!, generation_id: GEN_B }],
      },
    ];
    api.getInvestigation.mockResolvedValue(ok(old));
    await openAndInvestigate(api);
    expect(await screen.findByText(/older generation: the source jump is disabled/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /show lines/i })).toBeNull();
    expect(api.source).not.toHaveBeenCalled();
  });
});

describe("Investigate failure handling", () => {
  it("shows the service as unavailable and leaves Ask usable", async () => {
    const api = enabledApi({
      startInvestigation: vi.fn(async () =>
        fail("unavailable", "The investigation service is unavailable"),
      ),
    });
    const user = await openAndInvestigate(api);
    expect(await screen.findByRole("alert")).toHaveTextContent(/investigation service is unavailable/i);
    expect(screen.getByText(/ask is still available/i)).toBeInTheDocument();
    // Ask still works.
    const ask = screen.getByRole("region", { name: "Ask" });
    await user.type(ask.querySelector("textarea") as HTMLTextAreaElement, "still works?");
    await user.click(ask.querySelector("button[type=submit]") as HTMLButtonElement);
    expect(await screen.findByText("It does X.")).toBeInTheDocument();
  });

  it("rejects a run that ends because the generation changed and offers a refresh", async () => {
    const api = enabledApi();
    api.getInvestigation.mockResolvedValue(fail("stale", "generation changed", 409));
    await openAndInvestigate(api);
    expect(await screen.findByText(/this repository was re-indexed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Account recovery/)).toBeNull();
  });

  it("refuses to start against a stale generation", async () => {
    const api = enabledApi({
      startInvestigation: vi.fn(async () => fail("stale", "not current", 409)),
    });
    await openAndInvestigate(api);
    expect(await screen.findByText(/this repository was re-indexed/i)).toBeInTheDocument();
  });

  it("reports a polling failure on that run without crashing", async () => {
    const api = enabledApi();
    api.getInvestigation.mockResolvedValue(fail("unavailable", "service went away"));
    await openAndInvestigate(api);
    expect(await screen.findByRole("alert")).toHaveTextContent(/service went away/);
  });

  it("stops polling when the panel goes away", async () => {
    const api = enabledApi();
    api.getInvestigation.mockResolvedValue(ok(runningRecord));
    const user = userEvent.setup();
    const { unmount } = render(<App api={api} investigatePollMs={5} />);
    await user.selectOptions(await screen.findByLabelText(/repository/i), REPO_A);
    const panel = await screen.findByRole("region", { name: "Investigate" });
    await user.type(panel.querySelector("textarea") as HTMLTextAreaElement, "q");
    await user.click(panel.querySelector("button[type=submit]") as HTMLButtonElement);
    await waitFor(() => expect(api.getInvestigation).toHaveBeenCalled());
    unmount();
    const calls = api.getInvestigation.mock.calls.length;
    await new Promise((r) => setTimeout(r, 40));
    expect(api.getInvestigation.mock.calls.length).toBeLessThanOrEqual(calls + 1);
  });
});

describe("stopReasonLabel", () => {
  it("covers documented reasons and falls back for new ones", () => {
    expect(stopReasonLabel("repeated_action")).toMatch(/repeated an action/);
    expect(stopReasonLabel("brand_new")).toBe("Stopped: brand_new");
    expect(stopReasonLabel(null)).toBe("");
  });
});

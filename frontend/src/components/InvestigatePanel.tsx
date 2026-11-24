import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Schemas } from "../api/client";
import type { ApiError, ProductApi } from "../api/productApi";
import { ErrorNotice } from "./ErrorNotice";
import type { ViewerTarget } from "./SourceViewer";

type InvestigationRecord = Schemas["ProductInvestigation"];

interface Run {
  key: number;
  question: string;
  record: InvestigationRecord | null;
  error: ApiError | null;
  timedOut: boolean;
}

const OUTCOMES: Readonly<Record<string, string>> = {
  complete: "Complete",
  partial: "Partial: some statements may be unsupported or evidence unread",
  none: "No supported findings",
  unknown: "Result not classified",
};

/** Reasons the service has documented. Anything else falls through to the
 * default branch: the service may add reasons without a Foundry release. */
const STOP_REASONS: Readonly<Record<string, string>> = {
  repeated_action: "The investigation repeated an action and was stopped.",
  invalid_model_output:
    "The model produced output the service could not accept.",
  stale_generation: "The repository was re-indexed during the run.",
};

export function stopReasonLabel(reason: string | null | undefined): string {
  if (!reason) return "";
  return STOP_REASONS[reason] ?? `Stopped: ${reason}`;
}

export function InvestigatePanel({
  api,
  repoId,
  generationId,
  pollMs = 2000,
  maxWaitMs = 300_000,
  onOpenSource,
  onStale,
}: {
  api: ProductApi;
  repoId: string;
  generationId: string;
  pollMs?: number;
  maxWaitMs?: number;
  onOpenSource: (target: ViewerTarget) => void;
  onStale: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<ApiError | null>(null);
  const mounted = useRef(true);
  const counter = useRef(0);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  function patch(key: number, change: Partial<Run>) {
    if (!mounted.current) return;
    setRuns((all) => all.map((r) => (r.key === key ? { ...r, ...change } : r)));
  }

  async function track(key: number, runId: string) {
    const deadline = Date.now() + maxWaitMs;
    while (mounted.current) {
      await new Promise((resolve) => setTimeout(resolve, pollMs));
      if (!mounted.current) return;
      const result = await api.getInvestigation(repoId, runId);
      if (!mounted.current) return;
      if (!result.ok) {
        patch(key, { error: result.error });
        if (result.error.code === "stale") onStale();
        return;
      }
      patch(key, { record: result.data, error: null });
      if (result.data.status === "finished") return;
      if (Date.now() > deadline) {
        patch(key, { timedOut: true });
        return;
      }
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || starting) return;
    setStarting(true);
    setStartError(null);
    const result = await api.startInvestigation(repoId, generationId, text);
    if (!mounted.current) return;
    setStarting(false);
    if (!result.ok) {
      setStartError(result.error);
      if (result.error.code === "stale") onStale();
      return;
    }
    const key = ++counter.current;
    setRuns((all) => [
      { key, question: text, record: result.data, error: null, timedOut: false },
      ...all,
    ]);
    void track(key, result.data.run_id);
  }

  return (
    <section aria-label="Investigate">
      <h2>Investigate</h2>
      <p className="hint">
        An investigation reads the repository step by step and reports what it
        found, what it could not establish, and why it stopped. Partial results
        and runs with no findings are normal outcomes.
      </p>
      <form onSubmit={submit}>
        <label>
          Question{" "}
          <textarea
            value={question}
            maxLength={2000}
            rows={3}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </label>{" "}
        <button type="submit" disabled={starting || !question.trim()}>
          {starting ? "Starting…" : "Investigate"}
        </button>
      </form>
      {startError ? (
        <>
          <ErrorNotice error={startError} />
          <p className="hint">Ask is still available.</p>
        </>
      ) : null}
      {runs.map((run) => (
        <RunView
          key={run.key}
          run={run}
          sessionGenerationId={generationId}
          onOpenSource={onOpenSource}
        />
      ))}
    </section>
  );
}

function RunView({
  run,
  sessionGenerationId,
  onOpenSource,
}: {
  run: Run;
  sessionGenerationId: string;
  onOpenSource: (target: ViewerTarget) => void;
}) {
  const { record } = run;
  return (
    <article className="answer" aria-label={`Investigation ${record?.run_id ?? run.key}`}>
      <h3>{run.question}</h3>
      {run.error ? <ErrorNotice error={run.error} /> : null}
      {record && record.status === "running" && !run.error ? (
        <p role="status">{run.timedOut ? "Still running after a long wait. It may not finish; you can start a new run." : "Running…"}</p>
      ) : null}
      {record && record.status === "finished" ? (
        <>
          {record.evidence_mode === "fixture" ? (
            <p role="note" className="notice">
              Synthetic fixture data, not derived from this repository.
            </p>
          ) : null}
          <p>
            <strong>{OUTCOMES[record.outcome ?? "unknown"] ?? "Result not classified"}</strong>
            {record.stop_reason ? ` · ${stopReasonLabel(record.stop_reason)}` : ""}
          </p>
          <p className="meta">
            Indexed generation {record.generation_id}
            {record.envelope?.commit_sha
              ? ` · commit ${record.envelope.commit_sha.slice(0, 12)}`
              : " · commit not recorded"}
          </p>
          <h4>Findings</h4>
          {record.findings && record.findings.length > 0 ? (
            <ul>
              {record.findings.map((finding, i) => (
                <li key={i}>
                  {finding.statement}
                  <ul className="citations">
                    {finding.evidence.map((ev, j) => {
                      const older = ev.generation_id !== sessionGenerationId;
                      return (
                        <li key={j}>
                          <code>{ev.path}</code>{" "}
                          {older ? (
                            <span className="meta">
                              older generation: the source jump is disabled
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={() =>
                                onOpenSource({
                                  repoId: ev.repo_id,
                                  path: ev.path,
                                  generationId: ev.generation_id,
                                  highlight: { start: ev.start_line, end: ev.end_line },
                                })
                              }
                            >
                              Show lines {ev.start_line}–{ev.end_line}
                            </button>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          ) : (
            <p>No findings were recorded.</p>
          )}
          <h4>Open gaps</h4>
          {record.open_gaps && record.open_gaps.length > 0 ? (
            <ul>
              {record.open_gaps.map((gap, i) => (
                <li key={i}>{gap}</li>
              ))}
            </ul>
          ) : (
            <p>None reported.</p>
          )}
        </>
      ) : null}
    </article>
  );
}

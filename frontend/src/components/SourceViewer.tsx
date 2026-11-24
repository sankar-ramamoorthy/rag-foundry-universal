import { useState } from "react";
import type { Schemas } from "../api/client";
import type { ProductApi } from "../api/productApi";
import { useRequest } from "../hooks/useRequest";
import { ErrorNotice } from "./ErrorNotice";

export interface ViewerTarget {
  repoId: string;
  path: string;
  /** The generation the path was found or cited in; never the session's. */
  generationId: string;
  /** One-based inclusive lines to highlight (from a citation). */
  highlight?: { start: number; end: number };
}

const CONTEXT_LINES = 10;
const DEFAULT_LINES = 100;
const MAX_LINES = 500; // the backend's per-read cap

/** A bounded window around the cited lines, never above the read cap. */
export function windowFor(highlight?: { start: number; end: number }): {
  start: number;
  end: number;
} {
  if (!highlight) return { start: 1, end: DEFAULT_LINES };
  const start = Math.max(1, highlight.start - CONTEXT_LINES);
  const end = Math.min(highlight.end + CONTEXT_LINES, start + MAX_LINES - 1);
  return { start, end };
}

export function SourceViewer({
  api,
  target,
  sessionGenerationId,
  onClose,
}: {
  api: ProductApi;
  target: ViewerTarget;
  sessionGenerationId: string;
  onClose: () => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const older = target.generationId !== sessionGenerationId;
  const { start, end } = windowFor(target.highlight);
  const source = useRequest(
    older
      ? null
      : () => api.source(target.repoId, target.generationId, target.path, start, end),
    `source:${target.repoId}:${target.generationId}:${target.path}:${start}:${end}`,
    attempt,
  );

  return (
    <section aria-label="Source viewer">
      <h2>
        Source <code>{target.path}</code>{" "}
        <button type="button" onClick={onClose}>
          Close
        </button>
      </h2>
      {older ? (
        <div role="alert" className="notice notice-error">
          This reference belongs to an older generation of the repository, so
          the source jump is disabled. Ask again to get references for the
          current generation.
        </div>
      ) : null}
      {source.status === "loading" ? <p>Loading source…</p> : null}
      {source.status === "error" ? (
        <ErrorNotice error={source.error} onRetry={() => setAttempt((n) => n + 1)} />
      ) : null}
      {source.status === "ok" ? (
        <SourceLines data={source.data} highlight={target.highlight} />
      ) : null}
    </section>
  );
}

function SourceLines({
  data,
  highlight,
}: {
  data: Schemas["ProductSource"];
  highlight?: { start: number; end: number };
}) {
  const lines = data.text.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  const outside =
    highlight &&
    (highlight.end < data.start_line || highlight.start > data.end_line);
  return (
    <>
      <p className="meta">
        Lines {data.start_line}–{data.end_line}
        {data.total_lines ? ` of ${data.total_lines}` : ""}
        {data.complete_file ? " (whole file)" : ""}
        {data.next_start_line
          ? ` · the file continues at line ${data.next_start_line}`
          : ""}
        {" · "}generation {data.generation_id}
      </p>
      {outside ? (
        <p className="notice">
          The cited lines are not within the returned range, so nothing is
          highlighted.
        </p>
      ) : null}
      <table className="source">
        <tbody>
          {lines.map((line, i) => {
            const n = data.start_line + i;
            const marked =
              !!highlight && n >= highlight.start && n <= highlight.end;
            return (
              <tr key={n} data-line={n} data-highlighted={marked ? "true" : "false"}>
                <td className="ln">{n}</td>
                <td>
                  <code>{line}</code>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

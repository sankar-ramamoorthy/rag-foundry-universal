import { useEffect, useState } from "react";
import type { ProductApi } from "../api/productApi";
import { useRequest } from "../hooks/useRequest";
import { ErrorNotice } from "./ErrorNotice";

export function OrientPanel({
  api,
  repoId,
  generationId,
  onStale,
}: {
  api: ProductApi;
  repoId: string;
  generationId: string;
  onStale: () => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const orient = useRequest(
    () => api.orient(repoId, generationId),
    `orient:${repoId}:${generationId}`,
    attempt,
  );
  const stale = orient.status === "error" && orient.error.code === "stale";
  useEffect(() => {
    if (stale) onStale();
  }, [stale, onStale]);

  if (orient.status === "loading" || orient.status === "idle") {
    return <p>Loading overview…</p>;
  }
  if (orient.status === "error") {
    return (
      <ErrorNotice
        error={orient.error}
        onRetry={() => setAttempt((n) => n + 1)}
      />
    );
  }
  const o = orient.data;
  // The server already turns every gap into an envelope note ("category:
  // reason"). Show each gap once, with its path, and keep the other notes.
  const gapNotes = new Set(o.gaps.map((g) => `${g.category}: ${g.reason}`));
  const limits = [
    ...new Set([
      ...(o.envelope.limitations ?? []).filter((t) => !gapNotes.has(t)),
      ...o.gaps.map(
        (g) => `${g.category}${g.path ? ` (${g.path})` : ""}: ${g.reason}`,
      ),
    ]),
  ];
  return (
    <section aria-label="Overview">
      <h2>Overview</h2>
      <p>
        Coverage: <strong>{o.envelope.coverage}</strong>
      </p>
      <h3>Languages</h3>
      <ul>
        {Object.entries(o.languages).map(([name, count]) => (
          <li key={name}>
            {name}: {count}
          </li>
        ))}
      </ul>
      <p>
        Files indexed: {o.file_counts.indexed ?? 0} of {o.file_counts.total ?? 0}
      </p>
      {o.manifests.length > 0 ? (
        <>
          <h3>Manifests</h3>
          <ul>
            {o.manifests.map((m) => (
              <li key={`${m.kind}:${m.path}`}>
                {m.kind}: {m.path}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {o.services.length > 0 ? (
        <>
          <h3>Services</h3>
          <ul>
            {o.services.map((s) => (
              <li key={`${s.compose_file}:${s.name}`}>{s.name}</li>
            ))}
          </ul>
        </>
      ) : null}
      {limits.length > 0 ? (
        <>
          <h3>Limits reported</h3>
          <ul>
            {limits.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

import type { Schemas } from "../api/client";
import type { RequestState } from "../hooks/useRequest";
import { ErrorNotice } from "./ErrorNotice";

export function SessionBanner({
  readiness,
  onRetry,
}: {
  readiness: RequestState<Schemas["Readiness"]>;
  onRetry: () => void;
}) {
  if (readiness.status === "idle") return null;
  if (readiness.status === "loading") return <p>Checking repository…</p>;
  if (readiness.status === "error") {
    return (
      <>
        <ErrorNotice error={readiness.error} onRetry={onRetry} />
        <p className="notice">
          Questions and source reads are unavailable until the repository is
          ready.
        </p>
      </>
    );
  }
  const { generation_id, commit_sha, ingested_at } = readiness.data;
  return (
    <dl className="session" aria-label="Indexed generation">
      <dt>Generation</dt>
      <dd>{generation_id}</dd>
      <dt>Commit</dt>
      <dd>
        {commit_sha ? commit_sha.slice(0, 12) : "not recorded for this generation"}
      </dd>
      {ingested_at ? (
        <>
          <dt>Indexed</dt>
          <dd>{ingested_at}</dd>
        </>
      ) : null}
    </dl>
  );
}

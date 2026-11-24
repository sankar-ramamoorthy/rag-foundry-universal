import { useCallback, useState } from "react";
import type { ProductApi } from "./api/productApi";
import { LocatePanel } from "./components/LocatePanel";
import { OrientPanel } from "./components/OrientPanel";
import { RepoPicker } from "./components/RepoPicker";
import { SessionBanner } from "./components/SessionBanner";
import { useRequest } from "./hooks/useRequest";

export function App({ api }: { api: ProductApi }) {
  const [repoId, setRepoId] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [stale, setStale] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const readiness = useRequest(
    repoId ? () => api.readiness(repoId) : null,
    `readiness:${repoId ?? ""}:${refresh}`,
  );
  const generationId =
    readiness.status === "ok" ? readiness.data.generation_id : null;

  const markStale = useCallback(() => setStale(true), []);

  function selectRepo(next: string | null) {
    setRepoId(next);
    setStale(false);
    setSelectedPath(null);
  }

  function refreshGeneration() {
    setStale(false);
    setSelectedPath(null);
    setRefresh((n) => n + 1);
  }

  return (
    <main>
      <h1>Foundry</h1>
      <RepoPicker api={api} selected={repoId} onSelect={selectRepo} />
      <SessionBanner readiness={readiness} onRetry={refreshGeneration} />
      {stale ? (
        <div role="alert" className="notice notice-error">
          <strong>This repository was re-indexed.</strong> Results from the
          previous generation have been cleared.{" "}
          <button type="button" onClick={refreshGeneration}>
            Refresh to the current generation
          </button>
        </div>
      ) : null}
      {repoId && generationId && !stale ? (
        // Keyed by repository and generation: switching either discards every
        // result and in-flight request of the previous view.
        <div key={`${repoId}:${generationId}`}>
          <OrientPanel
            api={api}
            repoId={repoId}
            generationId={generationId}
            onStale={markStale}
          />
          <LocatePanel
            api={api}
            repoId={repoId}
            generationId={generationId}
            selectedPath={selectedPath}
            onSelectFile={setSelectedPath}
            onStale={markStale}
          />
          {selectedPath ? (
            <p aria-live="polite">
              Selected file: <code>{selectedPath}</code>
            </p>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}

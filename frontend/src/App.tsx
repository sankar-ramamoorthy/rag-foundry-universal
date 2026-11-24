import { useCallback, useState } from "react";
import type { ProductApi } from "./api/productApi";
import { AskPanel } from "./components/AskPanel";
import { LocatePanel } from "./components/LocatePanel";
import { OrientPanel } from "./components/OrientPanel";
import { RepoPicker } from "./components/RepoPicker";
import { SessionBanner } from "./components/SessionBanner";
import { SourceViewer, type ViewerTarget } from "./components/SourceViewer";
import { useRequest } from "./hooks/useRequest";

export function App({ api }: { api: ProductApi }) {
  const [repoId, setRepoId] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [stale, setStale] = useState(false);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [rerun, setRerun] = useState<string | undefined>(undefined);

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
    setViewer(null);
    setLastQuestion(null);
    setRerun(undefined);
  }

  function refreshGeneration(rerunQuestion?: string) {
    setStale(false);
    setViewer(null);
    setRerun(rerunQuestion);
    setRefresh((n) => n + 1);
  }

  return (
    <main>
      <h1>Foundry</h1>
      <RepoPicker api={api} selected={repoId} onSelect={selectRepo} />
      <SessionBanner readiness={readiness} onRetry={() => refreshGeneration()} />
      {stale ? (
        <div role="alert" className="notice notice-error">
          <strong>This repository was re-indexed.</strong> Results and source
          from the previous generation have been cleared.{" "}
          <button type="button" onClick={() => refreshGeneration()}>
            Refresh to the current generation
          </button>
          {lastQuestion ? (
            <>
              {" "}
              <button
                type="button"
                onClick={() => refreshGeneration(lastQuestion)}
              >
                Refresh and rerun my last question
              </button>
            </>
          ) : null}
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
          <AskPanel
            api={api}
            repoId={repoId}
            generationId={generationId}
            initialQuestion={rerun}
            onAsked={(question) => {
              setLastQuestion(question);
              setRerun(undefined);
            }}
            onOpenSource={setViewer}
            onStale={markStale}
          />
          <LocatePanel
            api={api}
            repoId={repoId}
            generationId={generationId}
            selectedPath={viewer?.path ?? null}
            onSelectFile={(path) =>
              setViewer({ repoId, path, generationId })
            }
            onStale={markStale}
          />
          {viewer ? (
            <SourceViewer
              api={api}
              target={viewer}
              sessionGenerationId={generationId}
              onClose={() => setViewer(null)}
            />
          ) : null}
        </div>
      ) : null}
    </main>
  );
}

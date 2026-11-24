import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Schemas } from "../api/client";
import type { ApiError, ProductApi } from "../api/productApi";
import { ErrorNotice } from "./ErrorNotice";

type Candidate = Schemas["LocateCandidate"];

/** Say plainly what definition coverage a candidate has; never leave an
 * unverified or unsupported file looking like "no definitions". */
export function definitionsLabel(candidate: Candidate): string | null {
  switch (candidate.definitions_status) {
    case "not_requested":
      return null;
    case "verified_complete":
      return candidate.definitions && candidate.definitions.length === 0
        ? "Verified: no definitions found."
        : null;
    case "not_covered_language":
      return "Definitions are not available for this language.";
    case "not_attempted":
      return "Definitions were not attempted for this file (page limit).";
    default:
      return `Definitions could not be verified (${candidate.definitions_status}).`;
  }
}

interface Search {
  id: number;
  query: string;
  pages: Schemas["ProductLocate"][];
}

export function LocatePanel({
  api,
  repoId,
  generationId,
  selectedPath,
  onSelectFile,
  onStale,
}: {
  api: ProductApi;
  repoId: string;
  generationId: string;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  onStale: () => void;
}) {
  const [input, setInput] = useState("");
  const [search, setSearch] = useState<Search | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const latest = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function fetchPage(id: number, query: string, cursor?: string) {
    setLoading(true);
    setError(null);
    const result = await api.locate(repoId, generationId, query, cursor);
    // Drop answers for a superseded search or an unmounted panel.
    if (!mounted.current || id !== latest.current) return;
    setLoading(false);
    if (!result.ok) {
      setError(result.error);
      if (result.error.code === "stale") onStale();
      return;
    }
    setSearch((current) => {
      const pages = cursor && current ? [...current.pages, result.data] : [result.data];
      return { id, query, pages };
    });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const query = input.trim();
    if (!query) return;
    latest.current += 1;
    setSearch(null);
    void fetchPage(latest.current, query);
  }

  const last = search?.pages[search.pages.length - 1];
  // Pagination always reuses the search's own query and this panel's
  // generation, never what is currently typed in the box.
  const nextCursor = last?.next_cursor ?? null;
  const candidates = search?.pages.flatMap((page) => page.candidates) ?? [];
  const limits = [...new Set(search?.pages.flatMap((p) => p.envelope.limitations ?? []))];

  return (
    <section aria-label="File search">
      <h2>Find files</h2>
      <form onSubmit={submit}>
        <label>
          Path, file name or glob{" "}
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. routes.py or src/**/*.ts"
          />
        </label>{" "}
        <button type="submit" disabled={loading || !input.trim()}>
          Search
        </button>
      </form>
      <p className="hint">
        File search matches paths and file names. Definition-name and semantic
        search are not available yet.
      </p>
      {error ? <ErrorNotice error={error} /> : null}
      {loading && !search ? <p>Searching…</p> : null}
      {search && candidates.length === 0 ? (
        <p>No files matched “{search.query}” at this generation.</p>
      ) : null}
      {candidates.length > 0 ? (
        <ul className="candidates">
          {candidates.map((candidate) => {
            const note = definitionsLabel(candidate);
            return (
              <li key={`${candidate.canonical_id}:${candidate.path}`}>
                <button
                  type="button"
                  aria-pressed={selectedPath === candidate.path}
                  onClick={() => onSelectFile(candidate.path)}
                >
                  {candidate.path}
                </button>{" "}
                <span className="meta">
                  {candidate.doc_type}
                  {candidate.source_status === "unavailable"
                    ? " · source unavailable"
                    : ""}
                </span>
                {candidate.definitions && candidate.definitions.length > 0 ? (
                  <ul className="definitions">
                    {candidate.definitions.map((d) => (
                      <li key={`${d.name}:${d.start_line}`}>
                        {d.kind} {d.name} (lines {d.start_line}–{d.end_line})
                      </li>
                    ))}
                  </ul>
                ) : null}
                {note ? <p className="meta">{note}</p> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
      {limits.length > 0 ? (
        <>
          <h3>Limits reported</h3>
          <ul>
            {limits.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </>
      ) : null}
      {search && nextCursor ? (
        <button
          type="button"
          disabled={loading}
          onClick={() => void fetchPage(search.id, search.query, nextCursor)}
        >
          {loading ? "Loading…" : "Load more files"}
        </button>
      ) : null}
    </section>
  );
}

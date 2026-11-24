import { useEffect, useRef, useState, type FormEvent } from "react";
import Markdown from "react-markdown";
import type { Schemas } from "../api/client";
import type { ApiError, ProductApi } from "../api/productApi";
import { ErrorNotice } from "./ErrorNotice";
import type { ViewerTarget } from "./SourceViewer";

type Answer = Schemas["ProductAsk"];
type Citation = Schemas["Citation"];

export function AskPanel({
  api,
  repoId,
  generationId,
  initialQuestion,
  onAsked,
  onOpenSource,
  onStale,
}: {
  api: ProductApi;
  repoId: string;
  generationId: string;
  /** Set after a stale refresh: the question is rerun once, on the user's click. */
  initialQuestion?: string;
  onAsked: (question: string) => void;
  onOpenSource: (target: ViewerTarget) => void;
  onStale: () => void;
}) {
  const [question, setQuestion] = useState(initialQuestion ?? "");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const latest = useRef(0);
  const mounted = useRef(true);
  const ranInitial = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function run(text: string) {
    const id = ++latest.current;
    setLoading(true);
    setError(null);
    onAsked(text);
    const result = await api.ask(repoId, generationId, text);
    // A superseded or unmounted request must not touch the current view.
    if (!mounted.current || id !== latest.current) return;
    setLoading(false);
    if (!result.ok) {
      setError(result.error);
      if (result.error.code === "stale") onStale();
      return;
    }
    setAnswers((previous) => [result.data, ...previous]);
  }

  useEffect(() => {
    if (initialQuestion && !ranInitial.current) {
      ranInitial.current = true;
      void run(initialQuestion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (text) void run(text);
  }

  return (
    <section aria-label="Ask">
      <h2>Ask about this repository</h2>
      <form onSubmit={submit}>
        <label>
          Question{" "}
          <textarea
            value={question}
            maxLength={8192}
            rows={3}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </label>{" "}
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? "Asking…" : "Ask"}
        </button>
      </form>
      {error ? (
        <ErrorNotice
          error={error}
          onRetry={question.trim() ? () => void run(question.trim()) : undefined}
        />
      ) : null}
      {answers.map((answer) => (
        <AnswerView
          key={answer.run_id}
          answer={answer}
          sessionGenerationId={generationId}
          onOpenSource={onOpenSource}
        />
      ))}
    </section>
  );
}

function AnswerView({
  answer,
  sessionGenerationId,
  onOpenSource,
}: {
  answer: Answer;
  sessionGenerationId: string;
  onOpenSource: (target: ViewerTarget) => void;
}) {
  const limits = answer.envelope.limitations ?? [];
  return (
    <article className="answer" aria-label={`Answer ${answer.run_id}`}>
      <h3>{answer.question}</h3>
      {/* react-markdown renders no raw HTML and drops unsafe URL schemes. */}
      <Markdown>{answer.answer}</Markdown>
      <p className="meta">
        Indexed generation {answer.generation_id}
        {answer.envelope.commit_sha
          ? ` · commit ${answer.envelope.commit_sha.slice(0, 12)}`
          : " · commit not recorded"}
        {" · coverage "}
        {answer.envelope.coverage ?? "unknown"}
        {answer.model_used ? ` · model ${answer.model_used}` : ""}
      </p>
      {limits.length > 0 ? (
        <ul className="meta">
          {limits.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      ) : null}
      <h4>Consulted passages</h4>
      <p className="meta">
        These are the passages placed in front of the model. They do not show
        which statement in the answer each one supports.
      </p>
      {answer.citations.length === 0 ? (
        <p>No passages were recorded for this answer.</p>
      ) : (
        <ul className="citations">
          {answer.citations.map((citation, i) => (
            <CitationRow
              key={`${citation.chunk_id ?? citation.path ?? "c"}:${i}`}
              citation={citation}
              repoId={answer.repo_id}
              sessionGenerationId={sessionGenerationId}
              onOpenSource={onOpenSource}
            />
          ))}
        </ul>
      )}
    </article>
  );
}

function CitationRow({
  citation,
  repoId,
  sessionGenerationId,
  onOpenSource,
}: {
  citation: Citation;
  repoId: string;
  sessionGenerationId: string;
  onOpenSource: (target: ViewerTarget) => void;
}) {
  const { path, start_line, end_line, generation_id } = citation;
  if (!path) {
    return (
      <li>
        A passage without a file path
        {citation.range_reason ? ` (${citation.range_reason})` : ""}.
      </li>
    );
  }
  const generation = generation_id ?? sessionGenerationId;
  const older = generation !== sessionGenerationId;
  const hasRange =
    typeof start_line === "number" &&
    typeof end_line === "number" &&
    start_line >= 1 &&
    start_line <= end_line;
  const open = (highlight?: { start: number; end: number }) =>
    onOpenSource({ repoId, path, generationId: generation, highlight });

  return (
    <li>
      <code>{path}</code>{" "}
      {older ? (
        <span className="meta">
          older generation: the source jump is disabled
        </span>
      ) : hasRange ? (
        <button
          type="button"
          onClick={() => open({ start: start_line, end: end_line })}
        >
          Show lines {start_line}–{end_line}
        </button>
      ) : (
        <>
          <span className="meta">
            No usable line range
            {citation.range_reason ? `: ${citation.range_reason}` : ""}.
          </span>{" "}
          <button type="button" onClick={() => open()}>
            Open file (no highlight)
          </button>
        </>
      )}
    </li>
  );
}

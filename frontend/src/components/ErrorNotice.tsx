import type { ApiError } from "../api/productApi";

const TITLES: Record<ApiError["code"], string> = {
  unavailable: "Not available",
  stale: "Repository was re-indexed",
  invalid_range: "Invalid line range",
  resource_limit: "Request too large",
  not_found: "Not found",
  invalid_request: "Invalid request",
  network: "Service unreachable",
  unexpected: "Unexpected response",
};

export function ErrorNotice({
  error,
  onRetry,
}: {
  error: ApiError;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="notice notice-error" data-code={error.code}>
      <strong>{TITLES[error.code]}.</strong> <span>{error.message}</span>
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

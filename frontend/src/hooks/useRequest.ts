import { useEffect, useState } from "react";
import type { ApiError, Result } from "../api/productApi";

export type RequestState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "error"; error: ApiError };

/**
 * Run `load` when `key` changes (or `attempt` is bumped to retry). A response
 * that arrives after the key has changed, or after unmount, is discarded, so a
 * slow answer for a previous repository or generation can never populate the
 * current view. `load` is deliberately not a dependency: `key` identifies the
 * request.
 */
export function useRequest<T>(
  load: (() => Promise<Result<T>>) | null,
  key: string,
  attempt = 0,
): RequestState<T> {
  const [state, setState] = useState<{ key: string; value: RequestState<T> }>({
    key,
    value: { status: load ? "loading" : "idle" },
  });

  useEffect(() => {
    if (!load) {
      setState({ key, value: { status: "idle" } });
      return;
    }
    let current = true;
    setState({ key, value: { status: "loading" } });
    void load().then((result) => {
      if (!current) return;
      setState({
        key,
        value: result.ok
          ? { status: "ok", data: result.data }
          : { status: "error", error: result.error },
      });
    });
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  // Never expose a result that belongs to a different key.
  return state.key === key
    ? state.value
    : { status: load ? "loading" : "idle" };
}

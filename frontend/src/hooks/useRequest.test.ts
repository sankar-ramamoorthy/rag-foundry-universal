import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useRequest } from "./useRequest";
import { deferred, ok } from "../test/fakeApi";

describe("useRequest", () => {
  it("discards a late response after the key changed and never exposes it", async () => {
    const slow = deferred<ReturnType<typeof ok<string>>>();
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) =>
        useRequest(
          () => (id === "a" ? slow.promise : Promise.resolve(ok("fresh-b"))),
          id,
        ),
      { initialProps: { id: "a" } },
    );
    expect(result.current.status).toBe("loading");

    rerender({ id: "b" });
    // The old key's state must not leak while the new request is in flight.
    expect(result.current.status).not.toBe("ok");
    await waitFor(() =>
      expect(result.current).toEqual({ status: "ok", data: "fresh-b" }),
    );

    await act(async () => {
      slow.resolve(ok("stale-a"));
      await Promise.resolve();
    });
    expect(result.current).toEqual({ status: "ok", data: "fresh-b" });
  });

  it("reports a failure as a value", async () => {
    const { result } = renderHook(() =>
      useRequest(
        async () => ({
          ok: false as const,
          error: { status: 503, code: "unavailable" as const, message: "m", details: {} },
        }),
        "k",
      ),
    );
    await waitFor(() => expect(result.current.status).toBe("error"));
  });

  it("is idle without a loader", () => {
    const { result } = renderHook(() => useRequest<string>(null, "none"));
    expect(result.current.status).toBe("idle");
  });
});

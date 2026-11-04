import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import { useUrlState } from "../shared/url-state";

function setup(url: string) {
  const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>;
  return renderHook(
    () => {
      const [values, update] = useUrlState({ q: "", page: "1" });
      return { values, update, search: useLocation().search };
    },
    { wrapper },
  );
}

describe("useUrlState", () => {
  it("reads values from the URL, with defaults", () => {
    const { result } = setup("/?q=abc");
    expect(result.current.values).toEqual({ q: "abc", page: "1" });
  });

  it("writes to the URL and reads back (round trip)", () => {
    const { result } = setup("/");
    act(() => result.current.update({ q: "J10", page: "3" }));
    expect(result.current.search).toBe("?q=J10&page=3");
    expect(result.current.values).toEqual({ q: "J10", page: "3" });
  });

  it("drops params that equal their default or are empty", () => {
    const { result } = setup("/?q=abc&page=2");
    act(() => result.current.update({ q: "", page: "1" }));
    expect(result.current.search).toBe("");
  });
});

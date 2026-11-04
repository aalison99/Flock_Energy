import { useCallback, useRef } from "react";
import { useSearchParams } from "react-router";

/**
 * Keep a flat set of string params in the URL. Values equal to their default
 * (or empty) are removed so URLs stay short; reading falls back to the default.
 * `update` is referentially stable, so it is safe in effect dependencies.
 */
export function useUrlState<K extends string>(defaults: Record<K, string>) {
  const [params, setParams] = useSearchParams();
  const defaultsRef = useRef(defaults);
  defaultsRef.current = defaults;

  const values = {} as Record<K, string>;
  for (const k of Object.keys(defaults) as K[]) values[k] = params.get(k) ?? defaults[k];

  const update = useCallback(
    (patch: Partial<Record<K, string>>, options?: { replace?: boolean }) => {
      const base = defaultsRef.current;
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const k of Object.keys(patch) as K[]) {
            const v = patch[k];
            if (v === undefined || v === "" || v === base[k]) next.delete(k);
            else next.set(k, v);
          }
          return next;
        },
        { replace: options?.replace ?? false },
      );
    },
    [setParams],
  );

  return [values, update] as const;
}

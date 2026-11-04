import { useEffect, useState } from "react";

export const SEARCH_DEBOUNCE_MS = 300;
/** Matches the API's `q` max_length (64); longer values would be rejected with 422. */
export const SEARCH_MAX_LENGTH = 64;

interface Props {
  value: string;
  onChange: (value: string) => void;
}

/** Text input that reports changes after a 300 ms pause in typing. */
export function SearchBox({ value, onChange }: Props) {
  const [text, setText] = useState(value);

  // Follow the URL when it changes from outside (back button, reload).
  useEffect(() => setText(value), [value]);

  useEffect(() => {
    if (text === value) return;
    const timer = setTimeout(() => onChange(text), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text, value, onChange]);

  return (
    <input
      type="search"
      aria-label="Search meters"
      placeholder="Search by meter id or serial…"
      value={text}
      maxLength={SEARCH_MAX_LENGTH}
      onChange={(e) => setText(e.target.value)}
      className="w-full max-w-md rounded border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
    />
  );
}

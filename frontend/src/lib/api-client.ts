import createClient from "openapi-fetch";
import type { paths } from "../generated/schema";
import { ApiError } from "./api-error";

export { ApiError } from "./api-error";

function isEnvelope(
  body: unknown,
): body is { error: { code: string; message: string; details?: Record<string, unknown> } } {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const e = (body as { error: unknown }).error;
  return (
    typeof e === "object" &&
    e !== null &&
    typeof (e as { code?: unknown }).code === "string" &&
    typeof (e as { message?: unknown }).message === "string"
  );
}

/** Turn a failed response body (envelope or not) into an ApiError. */
export function toApiError(body: unknown, status: number): ApiError {
  if (isEnvelope(body)) {
    return new ApiError(status, body.error.code, body.error.message, body.error.details ?? {});
  }
  return new ApiError(status, `http_${status}`, `Request failed with status ${status}`);
}

// VITE_API_BASE is the only place a base URL is configured. Empty means same origin
// (the Vite dev/preview proxy forwards /api to the backend).
const baseUrl = import.meta.env.VITE_API_BASE || window.location.origin;

export const client = createClient<paths>({
  baseUrl,
  fetch: (request) => globalThis.fetch(request),
});

interface Result<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Await an openapi-fetch call; return its data or throw an ApiError. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await call;
  } catch (cause) {
    if (cause instanceof ApiError) throw cause;
    throw new ApiError(0, "network_error", "Could not reach the API");
  }
  if (result.error !== undefined || result.data === undefined) {
    throw toApiError(result.error, result.response.status);
  }
  return result.data;
}

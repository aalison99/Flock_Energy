const IST = "Asia/Kolkata";

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { timeZone: IST, dateStyle: "medium", timeStyle: "short" });
}

export function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { timeZone: IST, day: "2-digit", month: "short" });
}

export function formatNumber(n: number, digits = 1): string {
  return n.toLocaleString("en-IN", { maximumFractionDigits: digits });
}

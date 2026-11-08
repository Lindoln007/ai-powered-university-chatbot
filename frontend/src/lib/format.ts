const dayFormatter = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
const timeFormatter = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });

/** "Today", "Yesterday" or a short date, for grouping the conversation list. */
export function relativeDay(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(today) - startOf(date)) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "This week";
  return "Earlier";
}

export const formatTime = (iso: string) => timeFormatter.format(new Date(iso));
export const formatDay = (iso: string) => dayFormatter.format(new Date(iso));

export const percent = (value: number) => `${Math.round(value * 100)}%`;

export function formatMs(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;
}

/** Turns plain-text answers (with blank-line paragraphs) into paragraph strings. */
export function paragraphs(text: string): string[] {
  return text
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function isoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

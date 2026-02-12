export const APP_TIMEZONE = "America/Sao_Paulo";

const TZ_SUFFIX_REGEX = /(Z|[+-]\d{2}:\d{2})$/i;

export function parseApiDate(value: string): Date {
  const raw = (value || "").trim();
  // Legacy backend payloads may come without timezone offset.
  // Assume UTC in this case to avoid browser-local reinterpretation.
  const normalized = TZ_SUFFIX_REGEX.test(raw) ? raw : `${raw}Z`;
  return new Date(normalized);
}

export function formatDateTime(
  value: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  const date = parseApiDate(value);
  return date.toLocaleString("pt-BR", {
    timeZone: APP_TIMEZONE,
    ...options,
  });
}

export function formatDate(value: string, options?: Intl.DateTimeFormatOptions): string {
  const date = parseApiDate(value);
  return date.toLocaleDateString("pt-BR", {
    timeZone: APP_TIMEZONE,
    ...options,
  });
}

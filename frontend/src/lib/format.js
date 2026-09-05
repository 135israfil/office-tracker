// Shared formatting for the dashboards.
//
// Durations arrive from the API as seconds and are shown the way §20-§24 write them
// ("9h 01m"), because that is what people compare against a timesheet. Keeping it in
// one place means the employee dashboard and the admin activity page can never
// disagree about how long an hour is.

export function duration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours === 0 && minutes === 0) return total > 0 ? "<1m" : "0m";
  if (hours === 0) return `${minutes}m`;
  return `${hours}h ${String(minutes).padStart(2, "0")}m`;
}

// Times are shown in the *office* timezone, not the viewer's. An admin checking the
// dashboard from another country must still see the 09:02 check-in as 09:02 — the date
// a session belongs to was already decided in office-local terms, and a display that
// disagreed with it would put the morning on the wrong day.
export function clockTime(value, timeZone) {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    ...(timeZone ? { timeZone } : {}),
  });
}

export function dateTime(value, timeZone) {
  if (!value) return "—";
  return new Date(value).toLocaleString([], timeZone ? { timeZone } : {});
}

export function today() {
  // Local date in YYYY-MM-DD, which is what the API's date parameters expect.
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export function describeError(err) {
  const payload = err?.payload;
  if (!payload) return err?.message ?? "Something went wrong";
  if (typeof payload === "string") return payload;
  if (payload.detail) return payload.detail;
  return Object.entries(payload)
    .map(([field, messages]) => `${field}: ${[].concat(messages).join(", ")}`)
    .join(" · ");
}

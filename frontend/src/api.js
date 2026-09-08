const BASE = "/api";

async function handle(res) {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep default */ }
    throw new Error(msg);
  }
  return res.json();
}

export const get = (path) => fetch(BASE + path).then(handle);
export const post = (path, body) =>
  fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  }).then(handle);

export const fmt$ = (x, digits = 2) =>
  x == null ? "—" : x.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });

export const fmtPct = (x, digits = 2, signed = true) =>
  x == null ? "—" : `${signed && x > 0 ? "+" : ""}${x.toFixed(digits)}%`;

export const fmtNum = (x, digits = 2) => (x == null ? "—" : x.toFixed(digits));

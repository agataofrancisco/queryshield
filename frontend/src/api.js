// Cliente da API. O token vive apenas em memória (nunca em localStorage).
// Todas as respostas são dados não confiáveis: os componentes convertem e verificam tipos.

export const API_BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:18200").replace(/\/$/, "");

export class ApiFailure extends Error {
  constructor(status, code, message, details) {
    super(typeof message === "string" ? message : "Pedido falhou.");
    this.status = Number.isInteger(status) ? status : 0;
    this.code = typeof code === "string" ? code : "request_failed";
    this.details = details && typeof details === "object" ? details : {};
  }
}

async function request(path, { token, method = "GET", body } = {}) {
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiFailure(0, "network_error", "Não foi possível contactar o servidor.");
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const error = data && typeof data === "object" && data.error ? data.error : {};
    throw new ApiFailure(response.status, error.code, error.message, error);
  }
  return data;
}

export const api = {
  demoLogin: (persona) => request("/auth/demo-login", { method: "POST", body: { persona } }),
  generate: (token, question) =>
    request("/query/generate", { token, method: "POST", body: { question } }),
  execute: (token, payload) =>
    request("/query/execute", { token, method: "POST", body: payload }),
  history: (token) => request("/query/history", { token }),
  health: () => request("/health"),
};

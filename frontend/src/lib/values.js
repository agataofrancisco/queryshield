// Funções puras e defensivas para valores vindos da API. Nunca lançam erro.

const NUMERIC = /^-?\d+(\.\d+)?$/;

export function toText(value) {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : String(value);
}

// Converte número ou texto numérico em número; devolve NaN se não for possível.
export function toNumber(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : Number.NaN;
  if (typeof value === "string" && NUMERIC.test(value.trim())) return Number(value.trim());
  return Number.NaN;
}

// Gráfico só quando a forma é "rótulo + um valor numérico" em todas as linhas.
export function chartableRows(columns, rows) {
  if (!Array.isArray(columns) || columns.length !== 2 || !Array.isArray(rows)) return null;
  if (rows.length === 0 || rows.length > 200) return null;
  const points = [];
  for (const row of rows) {
    if (!Array.isArray(row) || row.length !== 2) return null;
    const value = toNumber(row[1]);
    if (Number.isNaN(value)) return null;
    points.push({ label: toText(row[0]), value });
  }
  return points;
}

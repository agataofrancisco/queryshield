import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartableRows, toText } from "../lib/values";

// Tabela de resultados. Os valores chegam como texto (Decimal exacto); mostram-se tal como vêm.
export function ResultTable({ columns, rows, truncated }) {
  const cols = Array.isArray(columns) ? columns.map(toText) : [];
  const body = Array.isArray(rows) ? rows : [];
  return (
    <div className="result-table">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {cols.map((c, i) => (
                <th key={`${c}-${i}`}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, r) => (
              <tr key={r}>
                {(Array.isArray(row) ? row : []).map((cell, c) => (
                  <td key={c}>{toText(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated ? (
        <p className="muted">Resultado truncado ao limite de linhas. Refine a pergunta.</p>
      ) : null}
    </div>
  );
}

// Gráfico de barras só quando a forma é adequada; caso contrário não há gráfico.
export function ResultChart({ columns, rows }) {
  const points = chartableRows(columns, rows);
  if (!points) return null;
  return (
    <div className="result-chart" aria-label="Gráfico do resultado">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#2f6f73" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

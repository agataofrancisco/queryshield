import { useState } from "react";
import { toText } from "../lib/values";

// Avisos semânticos: não bloqueiam, mas dizem porque o resultado não está verificado.
export function Warnings({ warnings }) {
  const list = Array.isArray(warnings) ? warnings : [];
  if (list.length === 0) return null;
  return (
    <ul className="warnings" role="status">
      {list.map((w, i) => (
        <li key={i}>
          <strong>{toText(w?.code)}</strong>: {toText(w?.message)}
        </li>
      ))}
    </ul>
  );
}

// Problemas da validação: explicam porque a consulta foi bloqueada (nada é executado).
export function Issues({ issues }) {
  const list = Array.isArray(issues) ? issues : [];
  if (list.length === 0) return null;
  return (
    <ul className="issues" role="alert">
      {list.map((issue, i) => (
        <li key={i}>
          <strong>{toText(issue?.code)}</strong>: {toText(issue?.message)}
          {issue?.suggestion ? <span> Sugestão: <code>{toText(issue.suggestion)}</code></span> : null}
        </li>
      ))}
    </ul>
  );
}

export function Assumptions({ items }) {
  const list = Array.isArray(items) ? items : [];
  if (list.length === 0) return null;
  return (
    <div className="assumptions">
      <span className="muted">Suposições:</span>
      <ul>
        {list.map((a, i) => (
          <li key={i}>{toText(a)}</li>
        ))}
      </ul>
    </div>
  );
}

export function ExplainPanel({ plan }) {
  const lines = Array.isArray(plan) ? plan.map(toText) : [];
  if (lines.length === 0) return null;
  return (
    <pre className="plan" aria-label="Plano de execução (EXPLAIN, sem ANALYZE)">
      {lines.join("\n")}
    </pre>
  );
}

// Feedback só local (sem endpoint no escopo): guardado apenas no estado desta página.
export function Feedback() {
  const [choice, setChoice] = useState(null);
  if (choice) return <p className="muted">Obrigado pelo feedback ({choice}).</p>;
  return (
    <div className="feedback">
      <span className="muted">Esta resposta foi útil?</span>
      <button type="button" onClick={() => setChoice("sim")}>Sim</button>
      <button type="button" onClick={() => setChoice("não")}>Não</button>
    </div>
  );
}

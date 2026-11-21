import SqlViewer from "./SqlViewer";
import { ResultChart, ResultTable } from "./ResultView";
import { Assumptions, ExplainPanel, Feedback, Issues, Warnings } from "./Panels";
import { toText } from "../lib/values";

// Uma resposta do assistente. Nada é executado sem uma validação aceite (botão desactivado).
export default function Answer({ turn, onExecute, onClarify }) {
  const proposal = turn.proposal;
  if (turn.error) {
    return (
      <div className="notice notice-error" role="alert">
        {toText(turn.error)}
      </div>
    );
  }
  if (!proposal) return null;

  if (proposal.status === "needs_clarification" && proposal.clarification) {
    const options = Array.isArray(proposal.clarification.options)
      ? proposal.clarification.options
      : [];
    return (
      <div className="answer">
        <p>{toText(proposal.clarification.question)}</p>
        <div className="options">
          {options.map((option, i) => (
            <button key={i} type="button" onClick={() => onClarify(toText(option))}>
              {toText(option)}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (proposal.status === "unsupported" || !proposal.sql) {
    return (
      <div className="answer">
        <p className="muted">
          Não consigo responder a esta pergunta com as definições disponíveis.
          {proposal.rationale ? ` (${toText(proposal.rationale)})` : ""}
        </p>
      </div>
    );
  }

  const validation = proposal.validation || {};
  const blocked = validation.ok !== true;
  const execution = turn.execution;
  return (
    <div className="answer">
      <p className="muted">
        Provider: <code>{toText(proposal.provider)}</code>
        {proposal.provider === "mock" ? " (gerador determinístico, não é um LLM)" : ""}
      </p>
      <SqlViewer value={proposal.sql} />
      {blocked ? (
        <div className="notice notice-error" role="alert">
          <strong>Bloqueado pela validação.</strong> Nada foi executado.
          <Issues issues={validation.issues} />
        </div>
      ) : (
        <>
          <p className={validation.verified ? "badge badge-ok" : "badge badge-warn"}>
            {validation.verified ? "Verificado" : "Não verificado"}
          </p>
          <Warnings warnings={validation.warnings} />
          <Assumptions items={proposal.assumptions} />
          {!execution ? (
            <div className="actions">
              <button type="button" onClick={() => onExecute(turn, false)} disabled={turn.busy}>
                Executar
              </button>
              <button type="button" onClick={() => onExecute(turn, true)} disabled={turn.busy}>
                Explicar plano (sem executar)
              </button>
            </div>
          ) : null}
        </>
      )}
      {execution && execution.mode === "explain" ? <ExplainPanel plan={execution.plan} /> : null}
      {execution && execution.mode === "execute" ? (
        <div className="result">
          <p className={execution.verified ? "badge badge-ok" : "badge badge-warn"}>
            {execution.verified ? "Verificado" : "Não verificado"} · {toText(execution.row_count)} linha(s)
            {execution.elapsed_ms !== undefined ? ` · ${toText(execution.elapsed_ms)} ms` : ""}
          </p>
          <Warnings warnings={execution.warnings} />
          <ResultChart columns={execution.columns} rows={execution.rows} />
          <ResultTable
            columns={execution.columns}
            rows={execution.rows}
            truncated={execution.truncated}
          />
          {execution.explanation ? (
            <details>
              <summary>Explicação</summary>
              <ul>
                {(execution.explanation.filters || []).map((f, i) => (
                  <li key={i}>
                    <code>{toText(f)}</code>
                  </li>
                ))}
              </ul>
              <p className="muted">Tabelas: {(execution.explanation.tables || []).map(toText).join(", ")}</p>
            </details>
          ) : null}
          <Feedback />
        </div>
      ) : null}
    </div>
  );
}

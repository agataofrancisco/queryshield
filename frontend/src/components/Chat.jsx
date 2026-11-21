import { useRef, useState } from "react";
import Answer from "./Answer";
import ErrorBoundary from "./ErrorBoundary";
import { toText } from "../lib/values";

const MAX_QUESTION = 500;

export default function Chat({ token, api, onSessionExpired }) {
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState("");
  const nextId = useRef(1);

  function patchTurn(id, patch) {
    setTurns((current) => current.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }

  function handleFailure(id, failure) {
    if (failure && failure.status === 401) {
      onSessionExpired();
      return;
    }
    patchTurn(id, { busy: false, error: failure?.message || "Pedido falhou." });
  }

  async function ask(question) {
    const text = toText(question).trim();
    if (text.length < 3 || text.length > MAX_QUESTION) return;
    const id = nextId.current++;
    setTurns((current) => [...current, { id, question: text, busy: true }]);
    try {
      const proposal = await api.generate(token, text);
      patchTurn(id, { busy: false, proposal });
    } catch (failure) {
      handleFailure(id, failure);
    }
  }

  async function execute(turn, explain) {
    const proposal = turn.proposal;
    if (!proposal || !proposal.validation || proposal.validation.ok !== true) return;
    patchTurn(turn.id, { busy: true });
    try {
      const execution = await api.execute(token, {
        sql: proposal.sql,
        parameters: proposal.parameters || {},
        validated_hash: proposal.validation.sql_hash,
        explain,
        question: turn.question,
        assumptions: Array.isArray(proposal.assumptions) ? proposal.assumptions : [],
      });
      patchTurn(turn.id, { busy: false, execution });
    } catch (failure) {
      handleFailure(turn.id, failure);
    }
  }

  function submit(event) {
    event.preventDefault();
    const text = draft;
    setDraft("");
    ask(text);
  }

  return (
    <section className="chat">
      <div className="turns">
        {turns.length === 0 ? (
          <p className="muted">
            Experimente: "qual foi a receita de março de 2026?" ou "quantas encomendas em março de 2026?"
          </p>
        ) : null}
        {turns.map((turn) => (
          <article key={turn.id} className="turn">
            <p className="question">{turn.question}</p>
            {turn.busy && !turn.proposal && !turn.execution ? <p className="muted">A pensar…</p> : null}
            <ErrorBoundary>
              <Answer
                turn={turn}
                onExecute={execute}
                onClarify={(option) => ask(`${turn.question} — ${option}`)}
              />
            </ErrorBoundary>
          </article>
        ))}
      </div>
      <form className="composer" onSubmit={submit}>
        <input
          value={draft}
          maxLength={MAX_QUESTION}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Pergunte aos dados…"
          aria-label="Pergunta"
        />
        <button type="submit" disabled={draft.trim().length < 3}>
          Perguntar
        </button>
      </form>
    </section>
  );
}

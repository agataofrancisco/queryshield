import { useState } from "react";

// Personas fictícias do modo demo (o backend só as aceita com QS_DEMO_AUTH=true).
export const PERSONAS = [
  { id: "analista.ngola", label: "Analista · Ngola Tech (sem finanças)" },
  { id: "financas.ngola", label: "Finanças · Ngola Tech" },
  { id: "analista.benguela", label: "Analista · Casa Benguela" },
  { id: "admin.plataforma", label: "Administração · Ngola Tech" },
];

export default function Login({ onLogin, api }) {
  const [persona, setPersona] = useState(PERSONAS[0].id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = await api.demoLogin(persona);
      onLogin({ token: body.access_token, role: body.role, sellerId: body.seller_id, persona });
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <h1>QueryShield</h1>
      <p className="muted">Pergunta aos dados do Kianda Market. Dados sintéticos.</p>
      <label>
        Persona demo
        <select value={persona} onChange={(e) => setPersona(e.target.value)} disabled={busy}>
          {PERSONAS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={busy}>
        {busy ? "A entrar…" : "Entrar"}
      </button>
      {error ? <p className="notice notice-error" role="alert">{error}</p> : null}
    </form>
  );
}

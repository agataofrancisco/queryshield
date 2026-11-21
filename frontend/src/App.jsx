import { useState } from "react";
import Chat from "./components/Chat";
import Login from "./components/Login";
import { api } from "./api";

// Sessão só em memória: recarregar a página pede novo login (sem tokens em armazenamento).
export default function App() {
  const [session, setSession] = useState(null);

  if (!session) {
    return (
      <main className="shell">
        <Login api={api} onLogin={setSession} />
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <span>
          <strong>QueryShield</strong> · {session.persona} · papel <code>{session.role}</code> · vendedor{" "}
          {session.sellerId}
        </span>
        <button type="button" onClick={() => setSession(null)}>
          Sair
        </button>
      </header>
      <Chat token={session.token} api={api} onSessionExpired={() => setSession(null)} />
    </main>
  );
}

import { useEffect, useState } from "react";
import * as api from "./api";

const AUTHOR = "Thalari Sony Prashanthi";

export default function App() {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("user") || "null");
    } catch {
      return null;
    }
  });
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [files, setFiles] = useState([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!user) return;
    api
      .listDocuments()
      .then((d) => setFiles(d.files || []))
      .catch(() => {});
  }, [user]);

  async function onAuth(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") {
        await api.register(email, password, fullName);
      }
      const data = await api.login(email, password);
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));
      setUser(data.user);
      setPassword("");
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function onLogout() {
    setBusy(true);
    await api.logout();
    setUser(null);
    setFiles([]);
    setAnswer(null);
    setBusy(false);
  }

  async function onUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await api.uploadDocument(file);
      setFiles(res.session_files || []);
      setNotice(res.note || "Uploaded to session memory only.");
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  async function onClearDocs() {
    setBusy(true);
    try {
      await api.clearDocuments();
      setFiles([]);
      setAnswer(null);
      setNotice("Session documents wiped from memory.");
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function onAsk(e) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.askQuestion(question.trim());
      setAnswer(res);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  if (!user) {
    return (
      <div className="page">
        <header className="hero">
          <p className="badge">Session-only RAG · No document persistence</p>
          <h1>AI Regulatory Document Assistant</h1>
          <p className="sub">
            Upload company policies and ask natural-language compliance questions.
            Documents stay in memory for your login session only — never saved to disk
            or a database.
          </p>
          <p className="author">Author: {AUTHOR}</p>
        </header>
        <form className="card auth" onSubmit={onAuth}>
          <div className="tabs">
            <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
              Login
            </button>
            <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
              Register
            </button>
          </div>
          {mode === "register" && (
            <input placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          )}
          <input type="email" required placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" required minLength={6} placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          {error && <p className="error">{error}</p>}
          <button className="primary" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
          <p className="hint">Demo auth is in-memory. Register each time the backend restarts.</p>
        </form>
        <footer>Built by {AUTHOR} · Portfolio project</footer>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1>AI Regulatory Document Assistant</h1>
          <p className="author">Author: {AUTHOR}</p>
        </div>
        <div className="userbox">
          <span>{user.email}</span>
          <button onClick={onLogout} disabled={busy}>Logout (wipes session docs)</button>
        </div>
      </header>

      <div className="banner">
        <strong>Privacy notice:</strong> Uploaded documents are <em>not stored anywhere</em>.
        They exist only in server memory for this login session and are deleted on logout,
        clear, or server restart.
      </div>

      <main className="grid">
        <section className="card">
          <h2>Session documents</h2>
          <label className="upload">
            <input type="file" accept=".pdf,.docx,.txt,.md,.csv" onChange={onUpload} disabled={busy} />
            <span>{busy ? "Processing…" : "Upload PDF / DOCX / TXT"}</span>
          </label>
          <ul className="files">
            {files.length === 0 && <li className="muted">No files in this session yet.</li>}
            {files.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          <button onClick={onClearDocs} disabled={busy || !files.length}>Clear session documents</button>
          {notice && <p className="ok">{notice}</p>}
          {error && <p className="error">{error}</p>}
        </section>

        <section className="card">
          <h2>Ask a compliance question</h2>
          <form onSubmit={onAsk}>
            <textarea
              rows={4}
              placeholder="e.g. What is the data retention period for customer records?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <button className="primary" disabled={busy}>{busy ? "Thinking…" : "Query with RAG"}</button>
          </form>
          {error && <p className="error">{error}</p>}
          {answer && (
            <div className="answer">
              <h3>Answer</h3>
              <p>{answer.answer}</p>
              {answer.sources?.length > 0 && (
                <p className="sources">Sources: {answer.sources.join(", ")}</p>
              )}
              <p className="muted">{answer.disclaimer}</p>
            </div>
          )}
        </section>
      </main>
      <footer>© {new Date().getFullYear()} {AUTHOR} · Gemini RAG · Session-memory only</footer>
    </div>
  );
}

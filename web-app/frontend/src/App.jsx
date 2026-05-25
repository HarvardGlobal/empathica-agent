import { useEffect, useMemo, useState } from "react";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080";

async function api(path, opts = {}, token) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    }
  });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }
  if (!res.ok) throw data;
  return data;
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [me, setMe] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("Is ibuprofen safe with my current treatment?");
  const [chatOut, setChatOut] = useState("");
  const [debug, setDebug] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const loggedIn = useMemo(() => Boolean(token), [token]);

  useEffect(() => {
    if (!token) {
      setMe(null);
      return;
    }
    api("/auth/me", {}, token)
      .then((d) => setMe(d.user))
      .catch(() => {
        setToken("");
        localStorage.removeItem("token");
      });
  }, [token]);

  async function register() {
    setErr("");
    try {
      const d = await api(
        "/auth/register",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        },
        ""
      );
      localStorage.setItem("token", d.token);
      setToken(d.token);
    } catch (e) {
      setErr(JSON.stringify(e));
    }
  }

  async function login() {
    setErr("");
    try {
      const d = await api(
        "/auth/login",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        },
        ""
      );
      localStorage.setItem("token", d.token);
      setToken(d.token);
    } catch (e) {
      setErr(JSON.stringify(e));
    }
  }

  async function sendChat() {
    setErr("");
    setBusy(true);
    try {
      const d = await api(
        "/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            literacy_level: "medium",
            empathy_level: "medium"
          })
        },
        token
      );
      setChatOut(d.answer || "");
      setDebug(d.debug || null);
    } catch (e) {
      setErr(JSON.stringify(e));
    } finally {
      setBusy(false);
    }
  }

  async function uploadOnboarding(ev) {
    ev.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const formEl = ev.target;
      const fd = new FormData(formEl);
      const d = await api(
        "/api/onboarding/upload",
        {
          method: "POST",
          body: fd
        },
        token
      );
      setDebug(d);
    } catch (e) {
      setErr(JSON.stringify(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wrap">
      <h1>Empathica Chatbot</h1>
      <p className="sub">Frontend calls your backend. Backend calls private Cloud Run.</p>

      {!loggedIn ? (
        <section className="card">
          <h2>Auth</h2>
          <label>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          <label>Password (min 8)</label>
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
          <div className="row">
            <button onClick={register}>Register</button>
            <button onClick={login}>Login</button>
          </div>
        </section>
      ) : (
        <>
          <section className="card">
            <h2>Session</h2>
            <p>
              Logged in as <b>{me?.email}</b> | user_id <b>{me?.user_id}</b>
            </p>
            <button
              onClick={() => {
                setToken("");
                localStorage.removeItem("token");
                setMe(null);
              }}
            >
              Logout
            </button>
          </section>

          <section className="card">
            <h2>Chat</h2>
            <textarea rows={5} value={message} onChange={(e) => setMessage(e.target.value)} />
            <button disabled={busy} onClick={sendChat}>
              {busy ? "Sending..." : "Send"}
            </button>
            {chatOut ? <pre className="out">{chatOut}</pre> : null}
          </section>

          <section className="card">
            <h2>Onboarding Upload</h2>
            <form onSubmit={uploadOnboarding}>
              <label>Structured FHIR JSON</label>
              <input required name="structured_fhir_file" type="file" accept=".json,application/json" />
              <label>Unstructured markdown/text</label>
              <input required name="unstructured_file" type="file" accept=".md,.txt,text/markdown,text/plain" />
              <label>Optional target folders (comma-separated)</label>
              <input
                name="target_document_types"
                placeholder="medication_management,oncology_notes,care_coordination"
              />
              <button disabled={busy} type="submit">
                {busy ? "Uploading..." : "Upload"}
              </button>
            </form>
          </section>
        </>
      )}

      {err ? <pre className="err">{err}</pre> : null}
      {debug ? <pre className="debug">{JSON.stringify(debug, null, 2)}</pre> : null}
    </main>
  );
}


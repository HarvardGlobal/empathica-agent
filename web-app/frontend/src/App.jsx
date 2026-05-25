import { useEffect, useMemo, useState } from "react";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080";

const NAV_ITEMS = [
  { key: "chat", label: "Chat" },
  { key: "data", label: "My Data" },
  { key: "upload", label: "Upload Data" },
  { key: "profile", label: "My Profile" }
];

const PERSONA_DATA = {
  "000-001": {
    fullName: "Emily Wilson",
    age: 34,
    overview:
      "Active patient record with medication safety support enabled. Uses the assistant for treatment and side-effect questions.",
    conditions: ["Type 2 Diabetes", "Hypertension", "Anxiety"],
    medications: ["Metformin", "Lisinopril", "Sertraline"],
    allergies: ["Penicillin"],
    careTeam: ["Primary Care", "Endocrinology"]
  },
  "000-002": {
    fullName: "Mary (Maria) Rodriguez Johnson",
    age: 73,
    overview:
      "Complex oncology and chronic-care profile with caregiver-supported medication management and multilingual communication needs.",
    conditions: [
      "Stage IV HR+/HER2- Metastatic Breast Cancer",
      "Type 2 Diabetes",
      "Hypertension",
      "Osteoarthritis",
      "Osteoporosis",
      "GERD"
    ],
    medications: [
      "Letrozole",
      "Palbociclib",
      "Metformin ER",
      "Sitagliptin",
      "Lisinopril",
      "Omeprazole"
    ],
    allergies: ["Penicillin", "Shellfish", "Latex"],
    careTeam: ["Oncology", "Primary Care", "Endocrinology", "Pharmacy"]
  }
};

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

function toDisplayNameCase(name) {
  return String(name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function onEnterSubmit(fn) {
  return (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      fn();
    }
  };
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [me, setMe] = useState(null);
  const [authMode, setAuthMode] = useState("login");
  const [activePage, setActivePage] = useState("chat");

  const [regName, setRegName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regConfirmPassword, setRegConfirmPassword] = useState("");
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState([
    {
      role: "assistant",
      content: "Welcome. Do you have any questions about your medications, labs, or care plan?"
    }
  ]);

  const [debug, setDebug] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const [profileDisplayName, setProfileDisplayName] = useState("");
  const [profileLiteracy, setProfileLiteracy] = useState("medium");
  const [profileEmpathy, setProfileEmpathy] = useState("medium");

  const loggedIn = useMemo(() => Boolean(token), [token]);

  const myData = useMemo(() => {
    if (!me?.user_id) return null;
    return PERSONA_DATA[me.user_id] || null;
  }, [me]);

  const displayName = useMemo(() => {
    const dbName = (me?.name || "").trim();
    if (dbName) return toDisplayNameCase(dbName);
    const profileName = (profileDisplayName || "").trim();
    if (profileName) return toDisplayNameCase(profileName);
    const email = (me?.email || "").trim();
    if (email.includes("@")) return toDisplayNameCase(email.split("@")[0]);
    return "Account";
  }, [me, profileDisplayName]);

  useEffect(() => {
    if (!token) {
      setMe(null);
      return;
    }
    api("/auth/me", {}, token)
      .then((d) => {
        setMe(d.user);
        setProfileDisplayName(d.user.name || "");
      })
      .catch(() => {
        setToken("");
        localStorage.removeItem("token");
      });
  }, [token]);

  function presentError(e) {
    if (!e) return "Unknown error";
    if (e.code === "EMAIL_EXISTS") return "This email is already registered. Please log in.";
    if (e.code === "INVALID_INPUT") return e.detail || "Please complete all required fields.";
    if (e.detail) return e.detail;
    if (e.raw) return e.raw;
    return "Request failed";
  }

  async function register() {
    setErr("");
    if (!regName.trim()) return setErr("Please enter your full name.");
    if (!regEmail.trim()) return setErr("Please enter your email.");
    if (regPassword.length < 8) return setErr("Password must be at least 8 characters.");
    if (regPassword !== regConfirmPassword) return setErr("Passwords do not match.");

    try {
      const d = await api(
        "/auth/register",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: regName, email: regEmail, password: regPassword })
        },
        ""
      );
      localStorage.setItem("token", d.token);
      setToken(d.token);
      setRegName("");
      setRegEmail("");
      setRegPassword("");
      setRegConfirmPassword("");
      setActivePage("chat");
    } catch (e) {
      setErr(presentError(e));
    }
  }

  async function login() {
    setErr("");
    if (!loginEmail.trim() || !loginPassword) return setErr("Please enter your email and password.");

    try {
      const d = await api(
        "/auth/login",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: loginEmail, password: loginPassword })
        },
        ""
      );
      localStorage.setItem("token", d.token);
      setToken(d.token);
      setActivePage("chat");
    } catch (e) {
      setErr(presentError(e));
    }
  }

  async function sendChat() {
    if (!chatInput.trim()) return;
    setErr("");
    setBusy(true);
    const userText = chatInput.trim();
    setChatInput("");
    setChatHistory((prev) => [...prev, { role: "user", content: userText }]);

    try {
      const d = await api(
        "/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: userText,
            literacy_level: profileLiteracy,
            empathy_level: profileEmpathy
          })
        },
        token
      );
      setChatHistory((prev) => [...prev, { role: "assistant", content: d.answer || "No response returned." }]);
      setDebug(d.debug || null);
    } catch (e) {
      setErr(presentError(e));
      setChatHistory((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "I could not process that request right now. Please try again."
        }
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function uploadOnboarding(ev) {
    ev.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const fd = new FormData(ev.target);
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
      setErr(presentError(e));
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setToken("");
    localStorage.removeItem("token");
    setMe(null);
    setActivePage("chat");
  }

  function renderAuth() {
    return (
      <section className="auth-shell">
        <div className="auth-brand">
          <p className="eyebrow">Division of Clinical Informatics Network</p>
          <h1>Empathica Patient Assistant</h1>
          <p>
            Secure medication and care guidance with a patient-friendly interface. Register or log in to access your
            data, chat, and uploads.
          </p>
        </div>

        <div className="auth-card">
          <div className="tabs">
            <button
              type="button"
              className={authMode === "login" ? "tab active" : "tab"}
              onClick={() => {
                setErr("");
                setAuthMode("login");
              }}
            >
              Login
            </button>
            <button
              type="button"
              className={authMode === "register" ? "tab active" : "tab"}
              onClick={() => {
                setErr("");
                setAuthMode("register");
              }}
            >
              Register
            </button>
          </div>

          {authMode === "register" ? (
            <>
              <label htmlFor="register-name">Full Name</label>
              <input
                id="register-name"
                value={regName}
                onChange={(e) => setRegName(e.target.value)}
                placeholder="Jane Doe"
                autoComplete="name"
              />
              <label htmlFor="register-email">Email</label>
              <input
                id="register-email"
                value={regEmail}
                onChange={(e) => setRegEmail(e.target.value)}
                placeholder="janedoe@email.com"
                autoComplete="email"
              />
              <label htmlFor="register-password">Password (min 8)</label>
              <input
                id="register-password"
                type="password"
                value={regPassword}
                onChange={(e) => setRegPassword(e.target.value)}
                autoComplete="new-password"
              />
              <label htmlFor="register-confirm-password">Confirm Password</label>
              <input
                id="register-confirm-password"
                type="password"
                value={regConfirmPassword}
                onChange={(e) => setRegConfirmPassword(e.target.value)}
                autoComplete="new-password"
                onKeyDown={onEnterSubmit(register)}
              />
              <button onClick={register}>Create Account</button>
            </>
          ) : (
            <>
              <label htmlFor="login-email">Email</label>
              <input
                id="login-email"
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                placeholder="janedoe@email.com"
                autoComplete="email"
              />
              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                autoComplete="current-password"
                onKeyDown={onEnterSubmit(login)}
              />
              <button onClick={login}>Login</button>
            </>
          )}
        </div>
      </section>
    );
  }

  function renderDataPage() {
    return (
      <section className="page-grid">
        <article className="card hero-card">
          <p className="eyebrow">Patient Summary</p>
          <h2>{myData?.fullName || displayName}</h2>
          <p>{myData?.overview || "FHIR-backed summary will appear here as your data is synchronized."}</p>
          <div className="meta-row">
            <span>Age: {myData?.age || "-"}</span>
          </div>
        </article>

        <article className="card">
          <h3>Conditions</h3>
          <ul className="chip-list">
            {(myData?.conditions || ["No conditions loaded yet"]).map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h3>Active Medications</h3>
          <ul className="chip-list">
            {(myData?.medications || ["No medications loaded yet"]).map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h3>Allergies</h3>
          <ul className="chip-list">
            {(myData?.allergies || ["No allergies loaded yet"]).map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h3>Care Team</h3>
          <ul className="chip-list">
            {(myData?.careTeam || ["No care team loaded yet"]).map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </article>
      </section>
    );
  }

  function renderChatPage() {
    return (
      <section className="page-single">
        <article className="card chat-card">
          <div className="chat-header">
            <h2>Chat</h2>
            <p>Ask anything about your treatment, medications, side effects, or lab results.</p>
          </div>

          <div className="chat-log">
            {chatHistory.map((msg, idx) => (
              <div key={`${msg.role}-${idx}`} className={`bubble ${msg.role === "user" ? "user" : "assistant"}`}>
                <p>{msg.content}</p>
              </div>
            ))}
          </div>

          <div className="chat-compose">
            <label htmlFor="chat-input">Your Question</label>
            <textarea
              id="chat-input"
              rows={3}
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Type your question in your own words..."
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  if (!busy) sendChat();
                }
              }}
            />
            <p className="field-help">Press Ctrl+Enter (Windows) or Cmd+Enter (Mac) to send quickly.</p>
            <button disabled={busy} onClick={sendChat}>
              {busy ? "Sending..." : "Send"}
            </button>
          </div>
        </article>
      </section>
    );
  }

  function renderUploadPage() {
    return (
      <section className="page-single">
        <article className="card">
          <h2>Upload New Data</h2>
          <p>Upload a structured FHIR file and an unstructured markdown/text file for this patient.</p>

          <form onSubmit={uploadOnboarding}>
            <label>Structured FHIR JSON</label>
            <input required name="structured_fhir_file" type="file" accept=".json,application/json" />

            <label>Unstructured File (Markdown, text, or PDF)</label>
            <input
              required
              name="unstructured_file"
              type="file"
              accept=".md,.txt,.pdf,text/markdown,text/plain,application/pdf"
            />

            <button disabled={busy} type="submit">
              {busy ? "Uploading..." : "Upload Data"}
            </button>
          </form>
        </article>
      </section>
    );
  }

  function renderProfilePage() {
    return (
      <section className="page-single">
        <article className="card">
          <h2>My Profile</h2>
          <p>Manage your account-facing preferences for chat tone and readability.</p>

          <label>Display Name</label>
          <input value={profileDisplayName} onChange={(e) => setProfileDisplayName(e.target.value)} />

          <label>Default Literacy Level</label>
          <select value={profileLiteracy} onChange={(e) => setProfileLiteracy(e.target.value)}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>

          <label>Default Empathy Level</label>
          <select value={profileEmpathy} onChange={(e) => setProfileEmpathy(e.target.value)}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>

          <div className="profile-meta">
            <div>
              <strong>Email:</strong> {me?.email}
            </div>
          </div>
        </article>
      </section>
    );
  }

  function renderPage() {
    if (activePage === "data") return renderDataPage();
    if (activePage === "upload") return renderUploadPage();
    if (activePage === "profile") return renderProfilePage();
    return renderChatPage();
  }

  if (!loggedIn) {
    return (
      <main className="app-wrap">
        {renderAuth()}
        {err ? <div className="err">{err}</div> : null}
      </main>
    );
  }

  return (
    <main className="app-wrap">
      <header className="topbar">
        <div>
          <p className="eyebrow">Empathica</p>
          <h1>Patient Assistant</h1>
        </div>
        <div className="session-identity">
          <div className="identity-text">
            <span className="identity-label">Signed in as</span>
            <strong>{displayName}</strong>
          </div>
          <button className="logout-link" onClick={logout}>
            Logout
          </button>
        </div>
      </header>

      <nav className="nav-tabs" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            className={activePage === item.key ? "nav-btn active" : "nav-btn"}
            onClick={() => {
              setErr("");
              setActivePage(item.key);
            }}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {renderPage()}

      {err ? <div className="err">{err}</div> : null}
      {debug ? <pre className="debug">{JSON.stringify(debug, null, 2)}</pre> : null}
    </main>
  );
}

import { useEffect, useMemo, useState } from "react";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080";

const NAV_ITEMS = [
  { key: "chat", label: "Chat" },
  { key: "data", label: "My Data" },
  { key: "profile", label: "My Profile" },
  { key: "about", label: "About EMPATHICA" }
];

const PAGE_KEYS = new Set(["chat", "data", "profile", "about"]);
const INITIAL_ASSISTANT_TEXT =
  "Welcome. If you have questions about your medications, laboratory results, or treatment plan, I am here to help.";

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
  if (!res.ok) throw { ...data, status: res.status };
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

function renderInlineBold(text, keyPrefix = "k") {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={`${keyPrefix}-${idx}`}>{part.slice(2, -2)}</strong>;
    }
    return <span key={`${keyPrefix}-${idx}`}>{part}</span>;
  });
}

function renderAssistantContent(content) {
  const lines = String(content || "").split("\n");
  const blocks = [];
  let listItems = [];

  const flushList = (key) => {
    if (listItems.length > 0) {
      blocks.push(
        <ul key={`list-${key}`} className="assistant-list">
          {listItems.map((item, i) => (
            <li key={`li-${key}-${i}`}>{renderInlineBold(item, `li-${key}-${i}`)}</li>
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  lines.forEach((rawLine, idx) => {
    const line = rawLine.trim();
    if (!line) {
      flushList(idx);
      return;
    }

    const bulletMatch = line.match(/^[*-]\s+(.*)$/);
    if (bulletMatch) {
      listItems.push(bulletMatch[1]);
      return;
    }

    flushList(idx);
    blocks.push(
      <p key={`p-${idx}`} className="assistant-paragraph">
        {renderInlineBold(line, `p-${idx}`)}
      </p>
    );
  });

  flushList("final");
  return <>{blocks}</>;
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
  const [publicPage, setPublicPage] = useState("auth");

  const [regName, setRegName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regConfirmPassword, setRegConfirmPassword] = useState("");
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  const [chatInput, setChatInput] = useState("");
  const [chatThreads, setChatThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState("");
  const [showChatSettings, setShowChatSettings] = useState(false);
  const [chatLiteracyOverride, setChatLiteracyOverride] = useState("");
  const [chatEmpathyOverride, setChatEmpathyOverride] = useState("");
  const [deletingThreadIds, setDeletingThreadIds] = useState([]);
  const [chatHistory, setChatHistory] = useState([
    {
      role: "assistant",
      content: INITIAL_ASSISTANT_TEXT
    }
  ]);

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);
  const [myData, setMyData] = useState(null);

  const [profileDisplayName, setProfileDisplayName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");

  const loggedIn = useMemo(() => Boolean(token), [token]);

  function initialThread() {
    return {
      id: `local-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      title: "New Conversation",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      messages: [{ role: "assistant", content: INITIAL_ASSISTANT_TEXT }]
    };
  }

  function formatThreadTime(ts) {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString();
  }

  function pageToHash(page, isLoggedIn) {
    if (!isLoggedIn) return page === "about" ? "#/about" : "#/login";
    if (!PAGE_KEYS.has(page)) return "#/chat";
    return `#/${page}`;
  }

  function hashToPage(hash, isLoggedIn) {
    const raw = String(hash || "").replace(/^#\/?/, "").trim().toLowerCase();
    if (!raw) return isLoggedIn ? "chat" : "auth";
    if (!isLoggedIn) return raw === "about" ? "about" : "auth";
    if (raw === "upload") return "data";
    return PAGE_KEYS.has(raw) ? raw : "chat";
  }

  const displayName = useMemo(() => {
    const dbName = (me?.name || "").trim();
    if (dbName) return toDisplayNameCase(dbName);
    const profileName = (profileDisplayName || "").trim();
    if (profileName) return toDisplayNameCase(profileName);
    const email = (me?.email || "").trim();
    if (email.includes("@")) return toDisplayNameCase(email.split("@")[0]);
    return "Account";
  }, [me, profileDisplayName]);

  async function refreshMyData(authToken = token) {
    if (!authToken) return;
    try {
      const d = await api("/api/my-data", {}, authToken);
      setMyData(d || null);
    } catch {
      setMyData(null);
    }
  }

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
      .catch((e) => {
        if (e?.status === 401) {
          setToken("");
          localStorage.removeItem("token");
          return;
        }
        setErr("Could not refresh your profile right now. Please try again.");
      });
  }, [token]);

  useEffect(() => {
    const applyFromHash = () => {
      const route = hashToPage(window.location.hash, loggedIn);
      if (!loggedIn) {
        setPublicPage(route === "about" ? "about" : "auth");
        return;
      }
      setActivePage(route);
    };

    applyFromHash();
    window.addEventListener("hashchange", applyFromHash);
    return () => window.removeEventListener("hashchange", applyFromHash);
  }, [loggedIn, activeThreadId, token]);

  useEffect(() => {
    if (!loggedIn) return;
    refreshMyData(token);
  }, [loggedIn, token]);

  useEffect(() => {
    if (!loggedIn) return;
    api("/api/chat/threads", {}, token)
      .then((d) => {
        const threads = Array.isArray(d?.threads) ? d.threads : [];
        if (threads.length === 0) {
          const first = initialThread();
          setChatThreads([first]);
          setActiveThreadId(first.id);
          setChatHistory(first.messages);
          return;
        }
        setChatThreads(threads);
        setActiveThreadId(String(threads[0].id));
      })
      .catch(() => {
        const first = initialThread();
        setChatThreads([first]);
        setActiveThreadId(first.id);
        setChatHistory(first.messages);
      });
  }, [loggedIn, token]);

  useEffect(() => {
    if (!loggedIn || !activeThreadId || activeThreadId.startsWith("local-")) return;
    api(`/api/chat/threads/${activeThreadId}`, {}, token)
      .then((d) => {
        const msgs = Array.isArray(d?.messages) ? d.messages : [];
        if (msgs.length > 0) {
          setChatHistory(msgs.map((m) => ({ role: m.role, content: m.content })));
        } else {
          setChatHistory([{ role: "assistant", content: INITIAL_ASSISTANT_TEXT }]);
        }
      })
      .catch(() => {
        setChatHistory([{ role: "assistant", content: INITIAL_ASSISTANT_TEXT }]);
      });
  }, [loggedIn, activeThreadId, token]);

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
      setMe(d.user || null);
      setProfileDisplayName(d.user?.name || "");
      setRegName("");
      setRegEmail("");
      setRegPassword("");
      setRegConfirmPassword("");
      setActivePage("chat");
      window.location.hash = pageToHash("chat", true);
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
      setMe(d.user || null);
      setProfileDisplayName(d.user?.name || "");
      setActivePage("chat");
      window.location.hash = pageToHash("chat", true);
    } catch (e) {
      setErr(presentError(e));
    }
  }

  async function sendChat() {
    if (!chatInput.trim()) return;
    if (!activeThreadId) return;
    setErr("");
    setBusy(true);
    const userText = chatInput.trim();
    setChatInput("");
    const userMsg = { role: "user", content: userText };
    const withUser = [...chatHistory, userMsg];
    setChatHistory(withUser);

    try {
      const d = await api(
        "/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            thread_id: activeThreadId.startsWith("local-") ? null : Number(activeThreadId),
            message: userText,
            literacy_level: chatLiteracyOverride || null,
            empathy_level: chatEmpathyOverride || null
          })
        },
        token
      );
      const resolvedThreadId = String(d.thread_id || activeThreadId);
      if (activeThreadId.startsWith("local-") && d.thread_id) setActiveThreadId(resolvedThreadId);
      const assistantMsg = { role: "assistant", content: d.answer || "No response returned." };
      const withAssistant = [...withUser, assistantMsg];
      setChatHistory(withAssistant);
      const list = await api("/api/chat/threads", {}, token);
      const serverThreads = Array.isArray(list?.threads) ? list.threads : [];
      setChatThreads((prev) => {
        const localDrafts = prev.filter((t) => String(t.id).startsWith("local-") && t.id !== activeThreadId);
        return [...localDrafts, ...serverThreads];
      });
      if (d?.debug) {
        console.debug("AI debug payload", d.debug);
      }
    } catch (e) {
      setErr(presentError(e));
      const failMsg = {
        role: "assistant",
        content: "I could not process that request right now. Please try again."
      };
      const withFailure = [...withUser, failMsg];
      setChatHistory(withFailure);
    } finally {
      setBusy(false);
    }
  }

  function openThread(id) {
    const strId = String(id);
    setActiveThreadId(strId);
    if (strId.startsWith("local-")) {
      const thread = chatThreads.find((t) => String(t.id) === strId);
      setChatHistory(thread?.messages || [{ role: "assistant", content: INITIAL_ASSISTANT_TEXT }]);
    }
  }

  function createNewThread() {
    const thread = initialThread();
    setChatThreads((prev) => [thread, ...prev]);
    setActiveThreadId(thread.id);
    setChatHistory(thread.messages);
    setChatInput("");
  }

  async function deleteThread(id) {
    const strId = String(id);
    if (deletingThreadIds.includes(strId)) return;
    setDeletingThreadIds((prev) => [...prev, strId]);
    if (strId.startsWith("local-")) {
      const remaining = chatThreads.filter((t) => String(t.id) !== strId);
      setChatThreads(remaining);
      if (activeThreadId === strId) {
        if (remaining.length > 0) {
          setActiveThreadId(String(remaining[0].id));
          if (String(remaining[0].id).startsWith("local-")) {
            setChatHistory(remaining[0].messages || [{ role: "assistant", content: INITIAL_ASSISTANT_TEXT }]);
          }
        } else {
          createNewThread();
        }
      }
      setDeletingThreadIds((prev) => prev.filter((x) => x !== strId));
      return;
    }
    const previousThreads = chatThreads;
    const previousActive = activeThreadId;
    const remainingLocal = chatThreads.filter((t) => String(t.id).startsWith("local-"));
    const remainingServer = chatThreads.filter((t) => !String(t.id).startsWith("local-") && String(t.id) !== strId);
    const optimistic = [...remainingLocal, ...remainingServer];
    setChatThreads(optimistic);
    if (activeThreadId === strId) {
      if (optimistic.length > 0) {
        setActiveThreadId(String(optimistic[0].id));
      } else {
        createNewThread();
      }
    }
    try {
      await api(`/api/chat/threads/${strId}`, { method: "DELETE" }, token);
      const list = await api("/api/chat/threads", {}, token);
      const threads = Array.isArray(list?.threads) ? list.threads : [];
      setChatThreads((prev) => {
        const localDrafts = prev.filter((t) => String(t.id).startsWith("local-"));
        const filteredServer = threads.filter((t) => String(t.id) !== strId);
        return [...localDrafts, ...filteredServer];
      });
      if (activeThreadId === strId) {
        const next = threads.find((t) => String(t.id) !== strId);
        if (next) {
          setActiveThreadId(String(next.id));
        } else {
          createNewThread();
        }
      }
    } catch (e) {
      setChatThreads(previousThreads);
      setActiveThreadId(previousActive);
      setErr(presentError(e));
    } finally {
      setDeletingThreadIds((prev) => prev.filter((x) => x !== strId));
    }
  }

  async function saveProfileName() {
    setErr("");
    if (!profileDisplayName.trim()) return setErr("Please enter your name.");
    setProfileBusy(true);
    try {
      const d = await api(
        "/auth/profile",
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: profileDisplayName.trim() })
        },
        token
      );
      setMe(d.user);
      setProfileDisplayName(d.user?.name || "");
    } catch (e) {
      setErr(presentError(e));
    } finally {
      setProfileBusy(false);
    }
  }

  async function changePassword() {
    setErr("");
    if (!currentPassword || !newPassword) return setErr("Please enter current and new password.");
    if (newPassword.length < 8) return setErr("New password must be at least 8 characters.");
    if (newPassword !== confirmNewPassword) return setErr("New passwords do not match.");
    setProfileBusy(true);
    try {
      await api(
        "/auth/change-password",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword
          })
        },
        token
      );
      setCurrentPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
    } catch (e) {
      setErr(presentError(e));
    } finally {
      setProfileBusy(false);
    }
  }

  function formatTimestamp(ts) {
    if (!ts) return "Not available yet";
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "Not available yet";
    return d.toLocaleString();
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
      console.debug("Onboarding response", d);
      await refreshMyData(token);
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
    setMyData(null);
    setActivePage("chat");
    setPublicPage("auth");
    window.location.hash = pageToHash("auth", false);
  }

  function renderAuth() {
    return (
      <section className="auth-shell">
        <div className="auth-brand">
          <p className="eyebrow">DCI Network</p>
          <h1>Empathica Patient Assistant</h1>
          <p>
            Patient-friendly medication information support. Register or log in to access your data, chat, and
            uploads.
          </p>
          <button
            className="about-entry-btn"
            type="button"
            onClick={() => {
              setPublicPage("about");
              window.location.hash = pageToHash("about", false);
            }}
          >
            Learn About EMPATHICA
          </button>
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

  function renderAboutPage() {
    return (
      <section className="page-view about-shell">
        <div className="page-intro">
          <p className="eyebrow">Program Overview</p>
          <h2>About EMPATHICA</h2>
        </div>
        <article className="card about-card">
          <h3>Patient-centered AI for medication understanding</h3>
          <p className="about-paragraph">
            EMPATHICA is an AI-powered, patient-centered system designed to improve medication understanding through
            clear language, empathetic communication, and safety-focused responses.
          </p>

          <p className="about-paragraph">
            The name EMPATHICA combines empathy and informatics. Its purpose is to help patients and caregivers better
            understand medication information and support more informed conversations with clinical teams.
          </p>

          <h3>Peer-reviewed publication</h3>
          <p>
            <a href="https://pubmed.ncbi.nlm.nih.gov/41726533/" target="_blank" rel="noreferrer">
              Design and Evaluation of EMPATHICA: A Chatbot for Enhancing Medication Literacy
            </a>
          </p>
          <p className="about-meta">PMID: 41726533 | PMCID: PMC12919623</p>

          <h3>How it is built</h3>
          <p className="about-paragraph">
            EMPATHICA was developed through collaboration among patients, clinicians, researchers, and medication
            safety experts. The system uses retrieval-augmented generation (RAG) grounded in verified sources,
            including FDA-approved medication labeling, with safety guardrails to reduce unsupported medical advice.
          </p>

          <p className="about-paragraph">
            The broader mission is to make medication information more understandable and accessible across diverse
            populations while maintaining trust through transparency, clinical caution, and patient-centered design.
          </p>

          <h3>What the name EMPATHICA means</h3>
          <p className="about-paragraph">
            E - Empower, M - Medication information, P - Patient-centric, A - Accessible, T - Technology-driven, H -
            Healthcare journey, I - Innovative, C - Communication, A - AI-powered.
          </p>

          <h3>Learn more</h3>
          <ul className="about-links">
            <li>
              <a href="https://www.dcinetwork.org/empathica" target="_blank" rel="noreferrer">
                DCI Network - EMPATHICA
              </a>
            </li>
            <li>
              <a href="https://www.dcinetwork.org/about-us" target="_blank" rel="noreferrer">
                About DCI Network
              </a>
            </li>
            <li>
              <a href="https://www.dcinetwork.org/register" target="_blank" rel="noreferrer">
                Join the Network
              </a>
            </li>
          </ul>
        </article>
      </section>
    );
  }

  function renderDataPage() {
    const hasData = Boolean(myData?.fhir_linked);
    const medications = Array.isArray(myData?.medications) ? myData.medications : [];
    const conditions = Array.isArray(myData?.conditions) ? myData.conditions : [];
    const allergies = Array.isArray(myData?.allergies) ? myData.allergies : [];
    return (
      <section className="page-view">
        <div className="page-intro">
          <p className="eyebrow">Patient Information</p>
          <h2>My Data</h2>
        </div>
        {!hasData ? (
          <article className="card">
            <h3>No patient data is currently available</h3>
            <p>
              To view your medication profile and clinical summary, please upload structured and unstructured records
              below.
            </p>
          </article>
        ) : null}
        <div className="page-grid">
        <article className="card hero-card">
          <p className="eyebrow">Patient Summary</p>
          <h2>{myData?.profile_name || displayName}</h2>
          <p>
            {hasData
              ? "This section reflects your current Google Cloud FHIR record."
              : "FHIR-backed summary will appear here as your data is synchronized."}
          </p>
        </article>

        <article className="card">
          <h3>Conditions</h3>
          <ul className="chip-list">
            {(conditions.length > 0 ? conditions : ["No conditions loaded yet"]).map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h3>Active Medications</h3>
          <ul className="chip-list">
            {(medications.length > 0 ? medications : ["No medications loaded yet"]).map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h3>Allergies</h3>
          <ul className="chip-list">
            {(allergies.length > 0 ? allergies : ["No allergies loaded yet"]).map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </article>
        </div>

        <article className="card" style={{ marginTop: "0.9rem" }}>
          <h3>Upload or Update Data</h3>
          <p>Upload a structured FHIR file and an unstructured markdown, text, or PDF file for this patient.</p>

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

  function renderChatPage() {
    return (
      <section className="page-view">
        <div className="chat-layout">
          <aside className="card chat-history-card">
              <div className="chat-history-header">
                <h3>Conversations</h3>
                <button type="button" className="chat-new-btn" onClick={createNewThread}>
                  New Chat
                </button>
              </div>
              <div className="chat-thread-list">
                {chatThreads.map((t) => (
                  <div
                    key={String(t.id)}
                    className={activeThreadId === String(t.id) ? "chat-thread-item active" : "chat-thread-item"}
                  >
                    <button
                      type="button"
                      className="chat-thread-open"
                      onClick={() => openThread(t.id)}
                      aria-label={`Open conversation ${t.title || "New Conversation"}`}
                    >
                      <span className="chat-thread-title">{t.title || "New Conversation"}</span>
                      <span className="chat-thread-time">{formatThreadTime(t.updated_at || t.updatedAt)}</span>
                    </button>
                    <button
                      type="button"
                      className="chat-thread-delete"
                      disabled={deletingThreadIds.includes(String(t.id))}
                      onClick={(ev) => {
                        ev.preventDefault();
                        ev.stopPropagation();
                        deleteThread(t.id);
                      }}
                    >
                      {deletingThreadIds.includes(String(t.id)) ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                ))}
              </div>
          </aside>

          <article className="card chat-card">
          <div className="chat-log">
            {chatHistory.map((msg, idx) => (
              <div key={`${msg.role}-${idx}`} className={`bubble ${msg.role === "user" ? "user" : "assistant"}`}>
                {msg.role === "assistant" && idx === 0 ? (
                  <div className="assistant-bubble-head">
                    <div className="dci-mark" aria-hidden="true">
                      DCI
                    </div>
                    <div>
                      <p className="assistant-eyebrow">EMPATHICA Assistant</p>
                      <div className="assistant-content">{renderAssistantContent(msg.content)}</div>
                    </div>
                  </div>
                ) : (
                  <div className="assistant-content">
                    {msg.role === "assistant" ? renderAssistantContent(msg.content) : <p>{msg.content}</p>}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="chat-compose">
            <label htmlFor="chat-input">Message</label>
            <textarea
              id="chat-input"
              rows={3}
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Enter a question..."
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  if (!busy) sendChat();
                }
              }}
            />
            <div className="chat-settings-row">
              <button
                type="button"
                className="chat-settings-toggle"
                onClick={() => setShowChatSettings((v) => !v)}
              >
                {showChatSettings ? "Hide Response Settings" : "Response Settings"}
              </button>
            </div>
            {showChatSettings ? (
              <div className="chat-settings-panel">
                <label htmlFor="chat-literacy-override">Literacy Level (optional)</label>
                <select
                  id="chat-literacy-override"
                  value={chatLiteracyOverride}
                  onChange={(e) => setChatLiteracyOverride(e.target.value)}
                >
                  <option value="">Automatic (recommended)</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>

                <label htmlFor="chat-empathy-override">Empathy Level (optional)</label>
                <select
                  id="chat-empathy-override"
                  value={chatEmpathyOverride}
                  onChange={(e) => setChatEmpathyOverride(e.target.value)}
                >
                  <option value="">Automatic (recommended)</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
            ) : null}
            <div className="chat-actions">
              <button disabled={busy} onClick={sendChat}>
                {busy ? "Sending..." : "Send"}
              </button>
            </div>
            <p className="chat-caution">
              Educational information only. This does not replace medical advice. For urgent symptoms or treatment
              decisions, contact your clinical team.
            </p>
          </div>
          </article>
        </div>
      </section>
    );
  }

  function renderProfilePage() {
    return (
      <section className="page-view">
        <div className="page-intro">
          <p className="eyebrow">Account</p>
          <h2>My Profile</h2>
        </div>
        <article className="card">
          <h3>Profile Preferences</h3>
          <p>Manage your account details and security.</p>

          <label>Display Name</label>
          <input value={profileDisplayName} onChange={(e) => setProfileDisplayName(e.target.value)} />
          <button type="button" disabled={profileBusy} onClick={saveProfileName}>
            {profileBusy ? "Saving..." : "Save Name"}
          </button>

          <h3>Change Password</h3>
          <label>Current Password</label>
          <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          <label>New Password</label>
          <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          <label>Confirm New Password</label>
          <input
            type="password"
            value={confirmNewPassword}
            onChange={(e) => setConfirmNewPassword(e.target.value)}
          />
          <button type="button" disabled={profileBusy} onClick={changePassword}>
            {profileBusy ? "Updating..." : "Update Password"}
          </button>

          <div className="profile-meta">
            <div>
              <strong>Email:</strong> {me?.email}
            </div>
            <div>
              <strong>Last structured EHR update:</strong> {formatTimestamp(me?.last_structured_update_at)}
            </div>
            <div>
              <strong>Last unstructured data update:</strong> {formatTimestamp(me?.last_unstructured_update_at)}
            </div>
          </div>
        </article>
      </section>
    );
  }

  function renderPage() {
    if (activePage === "about") return renderAboutPage();
    if (activePage === "data") return renderDataPage();
    if (activePage === "profile") return renderProfilePage();
    return renderChatPage();
  }

  if (!loggedIn) {
    return (
      <main className="app-wrap">
        {publicPage === "about" ? (
          <>
            <header className="topbar">
              <div>
                <p className="eyebrow">Empathica</p>
                <h1>Patient Assistant</h1>
              </div>
              <button
                className="logout-link"
                type="button"
                onClick={() => {
                  setPublicPage("auth");
                  window.location.hash = pageToHash("auth", false);
                }}
              >
                Back to Login
              </button>
            </header>
            {renderAboutPage()}
          </>
        ) : (
          renderAuth()
        )}
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
              window.location.hash = pageToHash(item.key, true);
            }}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {renderPage()}

      {err ? <div className="err">{err}</div> : null}
    </main>
  );
}

import cors from "cors";
import dotenv from "dotenv";
import express from "express";
import multer from "multer";
import bcrypt from "bcryptjs";
import pg from "pg";
import crypto from "node:crypto";

dotenv.config();

const app = express();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    files: 2,
    fileSize: 5 * 1024 * 1024
  }
});

const PORT = Number(process.env.PORT || 8080);
const CLOUD_RUN_SERVICE_URL = (process.env.CLOUD_RUN_SERVICE_URL || "").replace(/\/+$/, "");
const CORS_ORIGIN = process.env.CORS_ORIGIN || "http://localhost:5173";
const DATABASE_URL = process.env.DATABASE_URL || "";
const PG_SSL_REJECT_UNAUTHORIZED = process.env.PG_SSL_REJECT_UNAUTHORIZED !== "false";
const SESSION_TTL_MS = 8 * 60 * 60 * 1000;
const SESSION_CLEANUP_INTERVAL_MS = 10 * 60 * 1000;
const ALLOWED_FHIR_MIME = new Set(["application/json", "application/fhir+json", "text/json"]);
const ALLOWED_UNSTRUCTURED_MIME = new Set(["text/markdown", "text/plain", "application/pdf"]);
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const allowedCorsOrigins = CORS_ORIGIN.split(",")
  .map((x) => x.trim())
  .filter(Boolean);

if (!CLOUD_RUN_SERVICE_URL) {
  throw new Error("CLOUD_RUN_SERVICE_URL is required");
}
if (!DATABASE_URL) {
  throw new Error("DATABASE_URL is required");
}

const { Pool } = pg;
const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: process.env.PGSSLMODE === "require" ? { rejectUnauthorized: PG_SSL_REJECT_UNAUTHORIZED } : undefined,
  connectionTimeoutMillis: 5000
});
const sessions = new Map();
const authAttempts = new Map();

app.disable("x-powered-by");
app.use((req, res, next) => {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader("Referrer-Policy", "no-referrer");
  res.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  next();
});
app.use(
  cors({
    origin(origin, cb) {
      if (!origin) return cb(null, true);
      if (allowedCorsOrigins.includes(origin)) return cb(null, true);
      return cb(new Error("CORS origin denied"));
    },
    methods: ["GET", "POST", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization"],
    maxAge: 86400
  })
);
app.use(express.json({ limit: "2mb" }));

function nextUserIdFromInt(lastSeq) {
  const max = Number(lastSeq || 0);
  return `000-${String(max + 1).padStart(3, "0")}`;
}

async function initDb() {
  console.log("Initializing database...");
  await pool.query("SET statement_timeout = 5000");
  await pool.query("SELECT 1");
  const exists = await pool.query(
    "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'app_users' LIMIT 1"
  );
  if (exists.rowCount === 0) {
    throw new Error("Required table app_users not found. Run DB bootstrap first.");
  }
  await pool.query("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS name TEXT");
  console.log("Database ready.");
}

function signSession(user) {
  const token = crypto.randomBytes(32).toString("hex");
  const expiresAt = Date.now() + SESSION_TTL_MS;
  sessions.set(token, {
    sub: user.user_id,
    email: user.email,
    expiresAt
  });
  return token;
}

function requireAuth(req, res, next) {
  const auth = req.headers.authorization || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) return res.status(401).json({ detail: "Missing bearer token" });
  const session = sessions.get(token);
  if (!session || session.expiresAt < Date.now()) {
    sessions.delete(token);
    return res.status(401).json({ detail: "Invalid or expired token" });
  }
  req.session = session;
  next();
}

function getClientIp(req) {
  const xff = req.headers["x-forwarded-for"];
  if (typeof xff === "string" && xff) return xff.split(",")[0].trim();
  return req.ip || req.socket?.remoteAddress || "unknown";
}

function authRateLimit(req, res, next) {
  const ip = getClientIp(req);
  const now = Date.now();
  const windowMs = 15 * 60 * 1000;
  const maxAttempts = 20;
  const state = authAttempts.get(ip) || { count: 0, startedAt: now };
  if (now - state.startedAt > windowMs) {
    authAttempts.set(ip, { count: 1, startedAt: now });
    return next();
  }
  if (state.count >= maxAttempts) {
    return res.status(429).json({ detail: "Too many attempts. Try again later." });
  }
  state.count += 1;
  authAttempts.set(ip, state);
  return next();
}

setInterval(() => {
  const now = Date.now();
  for (const [token, session] of sessions.entries()) {
    if (session.expiresAt < now) sessions.delete(token);
  }
  for (const [ip, state] of authAttempts.entries()) {
    if (now - state.startedAt > 15 * 60 * 1000) authAttempts.delete(ip);
  }
}, SESSION_CLEANUP_INTERVAL_MS).unref();

async function getCloudRunHeaders() {
  const { GoogleAuth } = await import("google-auth-library");
  const auth = new GoogleAuth();
  const client = await auth.getIdTokenClient(CLOUD_RUN_SERVICE_URL);
  const headers = await client.getRequestHeaders();
  return headers;
}

app.get("/healthz", (_req, res) => {
  res.json({ ok: true, service: "empathica-web-backend" });
});

app.post("/auth/register", authRateLimit, async (req, res) => {
  const { name, email, password } = req.body || {};
  const cleanName = String(name || "").trim();
  const normalizedEmail = String(email || "").trim().toLowerCase();
  const passwordStr = String(password || "");
  if (
    !cleanName ||
    cleanName.length > 100 ||
    !normalizedEmail ||
    !EMAIL_RE.test(normalizedEmail) ||
    passwordStr.length < 8 ||
    passwordStr.length > 128
  ) {
    return res.status(400).json({
      code: "INVALID_INPUT",
      detail: "Valid name/email required and password must be 8-128 chars"
    });
  }
  const existing = await pool.query("SELECT 1 FROM app_users WHERE email = $1", [normalizedEmail]);
  if (existing.rowCount > 0) {
    return res.status(409).json({
      code: "EMAIL_EXISTS",
      detail: "An account with this email already exists. Please log in."
    });
  }

  const seqResult = await pool.query("SELECT COALESCE(MAX(id), 0) AS max_id FROM app_users");
  const user_id = nextUserIdFromInt(seqResult.rows[0].max_id);
  const password_hash = await bcrypt.hash(passwordStr, 10);
  await pool.query(
    "INSERT INTO app_users (user_id, name, email, password_hash) VALUES ($1, $2, $3, $4)",
    [user_id, cleanName, normalizedEmail, password_hash]
  );
  const user = { user_id, name: cleanName, email: normalizedEmail };

  const token = signSession(user);
  return res
    .status(201)
    .json({ token, user: { name: user.name, email: user.email, user_id: user.user_id } });
});

app.post("/auth/login", authRateLimit, async (req, res) => {
  const { email, password } = req.body || {};
  const normalizedEmail = String(email || "").trim().toLowerCase();
  const passwordStr = String(password || "");
  if (!EMAIL_RE.test(normalizedEmail) || !passwordStr || passwordStr.length > 128) {
    return res.status(400).json({ detail: "Invalid credentials" });
  }
  const result = await pool.query(
    "SELECT user_id, name, email, password_hash FROM app_users WHERE email = $1",
    [normalizedEmail]
  );
  if (result.rowCount === 0) return res.status(401).json({ detail: "Invalid credentials" });
  const user = result.rows[0];

  const ok = await bcrypt.compare(passwordStr, user.password_hash);
  if (!ok) return res.status(401).json({ detail: "Invalid credentials" });

  const token = signSession(user);
  return res.json({ token, user: { name: user.name || "", email: user.email, user_id: user.user_id } });
});

app.get("/auth/me", requireAuth, async (req, res) => {
  const result = await pool.query("SELECT user_id, name, email FROM app_users WHERE user_id = $1", [req.session.sub]);
  if (result.rowCount === 0) return res.status(404).json({ detail: "User not found" });
  return res.json({ user: result.rows[0] });
});

app.post("/api/chat", requireAuth, async (req, res) => {
  try {
    const cloudHeaders = await getCloudRunHeaders();
    const payload = {
      user_id: req.session.sub,
      message: req.body?.message || "",
      literacy_level: req.body?.literacy_level || "medium",
      empathy_level: req.body?.empathy_level || "medium"
    };
    const out = await fetch(`${CLOUD_RUN_SERVICE_URL}/chat`, {
      method: "POST",
      headers: { ...cloudHeaders, "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const text = await out.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
    return res.status(out.status).json(data);
  } catch (err) {
    return res.status(500).json({ detail: "Chat proxy failed" });
  }
});

app.post(
  "/api/onboarding/upload",
  requireAuth,
  upload.fields([
    { name: "structured_fhir_file", maxCount: 1 },
    { name: "unstructured_file", maxCount: 1 }
  ]),
  async (req, res) => {
    try {
      const fhirFile = req.files?.structured_fhir_file?.[0];
      const unstructuredFile = req.files?.unstructured_file?.[0];
      if (!fhirFile || !unstructuredFile) {
        return res.status(400).json({ detail: "structured_fhir_file and unstructured_file are required" });
      }
      if (!ALLOWED_FHIR_MIME.has(fhirFile.mimetype || "")) {
        return res.status(400).json({ detail: "structured_fhir_file must be JSON/FHIR JSON" });
      }
      if (!ALLOWED_UNSTRUCTURED_MIME.has(unstructuredFile.mimetype || "")) {
        return res.status(400).json({ detail: "unstructured_file must be markdown, text, or PDF" });
      }

      const form = new FormData();
      form.append("user_id", req.session.sub);
      form.append("tenant", req.body?.tenant || "default");
      form.append("status", req.body?.status || "active");
      if (req.body?.target_document_types) {
        form.append("target_document_types", String(req.body.target_document_types));
      }
      form.append("structured_fhir_file", fhirFile.buffer, {
        filename: fhirFile.originalname || "structured_fhir_file.json",
        type: fhirFile.mimetype || "application/json"
      });
      form.append("unstructured_file", unstructuredFile.buffer, {
        filename: unstructuredFile.originalname || "unstructured_file.md",
        type: unstructuredFile.mimetype || "text/markdown"
      });

      const cloudHeaders = await getCloudRunHeaders();
      const nativeForm = new FormData();
      for (const [k, v] of form.entries()) {
        nativeForm.append(k, v);
      }
      const out = await fetch(`${CLOUD_RUN_SERVICE_URL}/onboarding/upload`, {
        method: "POST",
        headers: { ...cloudHeaders },
        body: nativeForm
      });
      const text = await out.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        data = { detail: text };
      }
      return res.status(out.status).json(data);
    } catch (err) {
      return res.status(500).json({ detail: "Onboarding proxy failed" });
    }
  }
);

async function boot() {
  try {
    await initDb();
    app.listen(PORT, () => {
      console.log(`backend listening on http://localhost:${PORT}`);
    });
  } catch (err) {
    console.error("Database init failed:", err);
    process.exitCode = 1;
  }
}

boot();

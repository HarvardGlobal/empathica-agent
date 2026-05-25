import cors from "cors";
import dotenv from "dotenv";
import express from "express";
import multer from "multer";
import bcrypt from "bcryptjs";
import pg from "pg";
import crypto from "node:crypto";

dotenv.config();

const app = express();
const upload = multer({ storage: multer.memoryStorage() });

const PORT = Number(process.env.PORT || 8080);
const APP_JWT_SECRET = process.env.APP_JWT_SECRET || "change-me";
const CLOUD_RUN_SERVICE_URL = (process.env.CLOUD_RUN_SERVICE_URL || "").replace(/\/+$/, "");
const CORS_ORIGIN = process.env.CORS_ORIGIN || "http://localhost:5173";
const DATABASE_URL = process.env.DATABASE_URL || "";

if (!CLOUD_RUN_SERVICE_URL) {
  throw new Error("CLOUD_RUN_SERVICE_URL is required");
}
if (!DATABASE_URL) {
  throw new Error("DATABASE_URL is required");
}

const { Pool } = pg;
const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: process.env.PGSSLMODE === "require" ? { rejectUnauthorized: false } : undefined,
  connectionTimeoutMillis: 5000
});
const sessions = new Map();

app.use(cors({ origin: CORS_ORIGIN }));
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
  console.log("Database ready.");
}

function signSession(user) {
  const token = crypto.randomBytes(32).toString("hex");
  const expiresAt = Date.now() + 8 * 60 * 60 * 1000;
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

app.post("/auth/register", async (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password || String(password).length < 8) {
    return res.status(400).json({ detail: "email and password (min 8 chars) required" });
  }

  const normalizedEmail = String(email).toLowerCase();
  const existing = await pool.query("SELECT 1 FROM app_users WHERE email = $1", [normalizedEmail]);
  if (existing.rowCount > 0) {
    return res.status(409).json({ detail: "Email already exists" });
  }

  const seqResult = await pool.query("SELECT COALESCE(MAX(id), 0) AS max_id FROM app_users");
  const user_id = nextUserIdFromInt(seqResult.rows[0].max_id);
  const password_hash = await bcrypt.hash(String(password), 10);
  await pool.query(
    "INSERT INTO app_users (user_id, email, password_hash) VALUES ($1, $2, $3)",
    [user_id, normalizedEmail, password_hash]
  );
  const user = { user_id, email: normalizedEmail };

  const token = signSession(user);
  return res.status(201).json({ token, user: { email: user.email, user_id: user.user_id } });
});

app.post("/auth/login", async (req, res) => {
  const { email, password } = req.body || {};
  const normalizedEmail = String(email || "").toLowerCase();
  const result = await pool.query(
    "SELECT user_id, email, password_hash FROM app_users WHERE email = $1",
    [normalizedEmail]
  );
  if (result.rowCount === 0) return res.status(401).json({ detail: "Invalid credentials" });
  const user = result.rows[0];

  const ok = await bcrypt.compare(String(password || ""), user.password_hash);
  if (!ok) return res.status(401).json({ detail: "Invalid credentials" });

  const token = signSession(user);
  return res.json({ token, user: { email: user.email, user_id: user.user_id } });
});

app.get("/auth/me", requireAuth, async (req, res) => {
  return res.json({ user: { user_id: req.session.sub, email: req.session.email } });
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

      const form = new FormData();
      form.append("user_id", req.session.sub);
      form.append("tenant", req.body?.tenant || "default");
      form.append("status", req.body?.status || "active");
      if (req.body?.target_document_types) {
        form.append("target_document_types", String(req.body.target_document_types));
      }
      form.append("structured_fhir_file", fhirFile.buffer, {
        type: fhirFile.mimetype || "application/json"
      });
      form.append("unstructured_file", unstructuredFile.buffer, {
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

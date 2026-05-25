import cors from "cors";
import dotenv from "dotenv";
import express from "express";
import multer from "multer";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import axios from "axios";
import FormData from "form-data";
import { GoogleAuth } from "google-auth-library";
import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

dotenv.config();

const app = express();
const upload = multer({ storage: multer.memoryStorage() });

const PORT = Number(process.env.PORT || 8080);
const APP_JWT_SECRET = process.env.APP_JWT_SECRET || "change-me";
const CLOUD_RUN_SERVICE_URL = (process.env.CLOUD_RUN_SERVICE_URL || "").replace(/\/+$/, "");
const CORS_ORIGIN = process.env.CORS_ORIGIN || "http://localhost:5173";

if (!CLOUD_RUN_SERVICE_URL) {
  throw new Error("CLOUD_RUN_SERVICE_URL is required");
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DATA_DIR = path.resolve(__dirname, "..", "data");
const USERS_FILE = path.join(DATA_DIR, "users.json");

app.use(cors({ origin: CORS_ORIGIN }));
app.use(express.json({ limit: "2mb" }));

async function ensureUserStore() {
  await fs.mkdir(DATA_DIR, { recursive: true });
  try {
    await fs.access(USERS_FILE);
  } catch {
    await fs.writeFile(USERS_FILE, JSON.stringify({ users: [] }, null, 2), "utf-8");
  }
}

async function readUsers() {
  await ensureUserStore();
  const raw = await fs.readFile(USERS_FILE, "utf-8");
  return JSON.parse(raw);
}

async function writeUsers(payload) {
  await fs.writeFile(USERS_FILE, JSON.stringify(payload, null, 2), "utf-8");
}

function nextUserId(users) {
  const max = users.reduce((m, u) => Math.max(m, Number((u.user_id || "000-000").split("-")[1] || 0)), 0);
  return `000-${String(max + 1).padStart(3, "0")}`;
}

function signSession(user) {
  return jwt.sign(
    {
      sub: user.user_id,
      email: user.email
    },
    APP_JWT_SECRET,
    { expiresIn: "8h" }
  );
}

function requireAuth(req, res, next) {
  const auth = req.headers.authorization || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) return res.status(401).json({ detail: "Missing bearer token" });
  try {
    req.session = jwt.verify(token, APP_JWT_SECRET);
    next();
  } catch {
    return res.status(401).json({ detail: "Invalid or expired token" });
  }
}

async function getCloudRunHeaders() {
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

  const db = await readUsers();
  if (db.users.some((u) => u.email.toLowerCase() === String(email).toLowerCase())) {
    return res.status(409).json({ detail: "Email already exists" });
  }

  const password_hash = await bcrypt.hash(String(password), 10);
  const user = {
    email: String(email).toLowerCase(),
    user_id: nextUserId(db.users),
    password_hash,
    created_at: new Date().toISOString()
  };
  db.users.push(user);
  await writeUsers(db);

  const token = signSession(user);
  return res.status(201).json({ token, user: { email: user.email, user_id: user.user_id } });
});

app.post("/auth/login", async (req, res) => {
  const { email, password } = req.body || {};
  const db = await readUsers();
  const user = db.users.find((u) => u.email.toLowerCase() === String(email || "").toLowerCase());
  if (!user) return res.status(401).json({ detail: "Invalid credentials" });

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
    const out = await axios.post(`${CLOUD_RUN_SERVICE_URL}/chat`, payload, {
      headers: { ...cloudHeaders, "Content-Type": "application/json" },
      timeout: 120000
    });
    return res.status(out.status).json(out.data);
  } catch (err) {
    const status = err?.response?.status || 500;
    const data = err?.response?.data || { detail: "Chat proxy failed" };
    return res.status(status).json(data);
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
        filename: fhirFile.originalname || "structured_fhir.json",
        contentType: fhirFile.mimetype || "application/json"
      });
      form.append("unstructured_file", unstructuredFile.buffer, {
        filename: unstructuredFile.originalname || "unstructured.md",
        contentType: unstructuredFile.mimetype || "text/markdown"
      });

      const cloudHeaders = await getCloudRunHeaders();
      const out = await axios.post(`${CLOUD_RUN_SERVICE_URL}/onboarding/upload`, form, {
        headers: { ...cloudHeaders, ...form.getHeaders() },
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
        timeout: 180000
      });
      return res.status(out.status).json(out.data);
    } catch (err) {
      const status = err?.response?.status || 500;
      const data = err?.response?.data || { detail: "Onboarding proxy failed" };
      return res.status(status).json(data);
    }
  }
);

app.listen(PORT, () => {
  console.log(`backend listening on http://localhost:${PORT}`);
});


import "dotenv/config";
import express from "express";
import OpenAI from "openai";
import rateLimit from "express-rate-limit";
import { fileURLToPath } from "node:url";
import path from "node:path";

const required = ["OPENAI_API_KEY"];
for (const name of required) {
  if (!process.env[name]) throw new Error(`${name} is required. Add it to .env, never to client code.`);
}

const app = express();
const appDirectory = path.dirname(fileURLToPath(import.meta.url));
const allowedOrigins = (process.env.ALLOWED_ORIGINS || "https://moo5561.github.io,http://localhost:3000")
  .split(",").map((origin) => origin.trim());
const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

app.set("trust proxy", 1);
app.use((req, res, next) => {
  const origin = req.get("origin");
  if (origin && !allowedOrigins.includes(origin)) return res.status(403).json({ error: "Origin not allowed." });
  res.set("Access-Control-Allow-Origin", origin || allowedOrigins[0]);
  res.set("Vary", "Origin");
  res.set("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});
app.use(express.json({ limit: "12kb" }));
app.use(rateLimit({ windowMs: 15 * 60 * 1000, limit: 30, standardHeaders: "draft-8", legacyHeaders: false }));

app.post("/api/chat", async (req, res) => {
  const prompt = typeof req.body?.prompt === "string" ? req.body.prompt.trim() : "";
  if (!prompt || prompt.length > 2000) return res.status(400).json({ error: "Send a message between 1 and 2,000 characters." });
  try {
    const response = await client.responses.create({
      model: process.env.OPENAI_MODEL || "gpt-4.1-mini",
      instructions: "You are Birdvirus Cloud, a concise, welcoming assistant for the Birdvirus Discord community. Be helpful, practical, and never claim access to private server data.",
      input: prompt,
      max_output_tokens: 500,
    });
    return res.json({ answer: response.output_text || "I couldn't generate a reply. Please try again." });
  } catch (error) {
    console.error("OpenAI request failed:", error.message);
    return res.status(502).json({ error: "Birdvirus Cloud is having trouble right now. Try again soon." });
  }
});

app.get("/health", (_req, res) => res.json({ ok: true }));
app.use(express.static(appDirectory, { index: "index.html", dotfiles: "deny" }));
app.listen(process.env.PORT || 3000, () => console.log("Birdvirus Cloud API is listening."));


import express from "express";
import helmet from "helmet";
import rateLimit from "express-rate-limit";
import OpenAI from "openai";
import path from "node:path";
import { fileURLToPath } from "node:url";

const app = express();
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

app.use(helmet());
app.use(express.json({ limit: "20kb" }));
app.use(express.static(path.join(__dirname, "public")));

const limiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 20,
  standardHeaders: "draft-8",
  legacyHeaders: false
});

app.get("/api/health", (req, res) => {
  res.json({
    status: "ok",
    aiConfigured: Boolean(process.env.OPENAI_API_KEY)
  });
});

app.post("/api/generate", limiter, async (req, res) => {
  try {
    const { service, language, tone, details } = req.body ?? {};

    if (typeof service !== "string" || !service.trim()) {
      return res.status(400).json({ error: "Service is required." });
    }

    if (typeof details !== "string" || details.length > 6000) {
      return res.status(400).json({ error: "Please provide valid details." });
    }

    if (!process.env.OPENAI_API_KEY) {
      return res.status(503).json({ error: "AI is not configured yet." });
    }

    const client = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY
    });

    const response = await client.responses.create({
      model: process.env.OPENAI_MODEL || "gpt-4.1-mini",
      instructions:
        "You are Nexa Business Hub AI, a helpful business assistant. " +
        "Answer accurately, clearly, and practically. Never claim that you " +
        "submitted an application or performed an action you did not perform. " +
        "Do not request passwords, API keys, or unnecessary sensitive data.",
      input:
        `Service: ${service.slice(0, 150)}\n` +
        `Language: ${String(language || "Urdu").slice(0, 30)}\n` +
        `Tone: ${String(tone || "professional").slice(0, 50)}\n` +
        `User details:\n${details}`
    });

    res.json({ text: response.output_text });
  } catch (error) {
    console.error("AI request failed:", error.message);
    res.status(500).json({
      error: "AI could not generate a response. Please try again."
    });
  }
});

app.get("*", (req, res, next) => {
  if (req.path.startsWith("/api/")) {
    return res.status(404).json({ error: "API route not found." });
  }
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, "0.0.0.0", () => {
  console.log(`Nexa Business Hub AI running on port ${PORT}`);
});

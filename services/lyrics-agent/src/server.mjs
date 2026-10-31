import { Agent } from "@cursor/sdk";
import { spawn } from "node:child_process";
import express from "express";
import fs from "node:fs";
import path from "node:path";

const app = express();
app.use(express.json({ limit: "1mb" }));

const PORT = Number(process.env.PORT || 8020);
const MODEL = process.env.CURSOR_LLM_MODEL || "composer-2.5";
const WORKSPACE = process.env.LYRICS_WORKSPACE || "/tmp/ragam-lyrics-workspace";
// auto | cli | sdk — auto prefers Cursor CLI (ask mode) when available, else SDK
const BACKEND = (process.env.LYRICS_BACKEND || "auto").toLowerCase();
const CLI_TIMEOUT_MS = Number(process.env.LYRICS_CLI_TIMEOUT_MS || 180_000);
// Prefer plan-included Composer first; third-party (Gemini) hits Pro usage caps quickly.
const MODEL_FALLBACKS = [
  MODEL,
  "composer-2.5",
  "composer-2",
  "gemini-3-flash",
  "claude-haiku-5-5",
].filter((v, i, a) => v && a.indexOf(v) === i);

fs.mkdirSync(WORKSPACE, { recursive: true });
const readme = path.join(WORKSPACE, "README.md");
if (!fs.existsSync(readme)) {
  fs.writeFileSync(
    readme,
    "# Ragam lyrics scratch\nAgent workspace for Telugu lyric generation only.\n",
    "utf8",
  );
}

function buildPrompt({
  title,
  deity,
  topic,
  vocal,
  language,
  musicGenre,
  regenerate,
  previousLyrics,
  previousStyle,
  variationSeed,
}) {
  const vocalLabel = vocal === "f" ? "female" : "male";
  const regenBlock =
    regenerate || previousLyrics
      ? `
REGENERATE (mandatory — this is a NEW draft, not a polish)
- Variation seed: ${variationSeed || Date.now()}
- Write a DISTINCTLY different song: new Pallavi refrain, new Slokam, new Charanam imagery.
- Do NOT reuse lines, phrases, or the same Pallavi from the previous draft below.
- Also write a NEW style_prompt with a DIFFERENT tempo/BPM and instrumental colour than before
  (if previous was slow, try medium or medium-brisk when lyrics allow; never copy the old style string).
Previous style_prompt (DO NOT copy):
${previousStyle || "(none)"}

Previous lyrics (DO NOT copy — avoid same Pallavi / Charanam lines):
${(previousLyrics || "").slice(0, 1800) || "(none)"}
`
      : "";

  return `You are a senior Telugu keerthana / bhajan lyricist for YouTube channel "Ragam Spiritual".
Write ORIGINAL, temple-grade song lyrics in Telugu script for Suno custom mode — in the DEPTH of traditional Carnatic / bhakti poetry, NOT everyday speech.

LANGUAGE REGISTER (critical — failure if violated)
- Sung lines MUST be Telugu script (తెలుగు). Never transliteration-only; never Hindi Devanagari for sung lines.
- Write in CLASSICAL / GRANTHIKA-leaning BHAKTI Telugu — the sacred poetic tongue of old keerthanas and temple bhajans.
- Words must feel deep, spiritual, and traditional: nama, guna, leela, karuna, sharanagati, jyothi, amrutham, karunarasam, charanamule, padamulu, hrudayam, ananda, divya, punya, etc. where natural.
- Prefer elevated, archaic-flavoured diction and compound bhakti phrases over common spoken Telugu.
- FORBIDDEN (reject these reflexes): modern colloquial chat language; newspaper/general prose; casual verbs of daily talk; film-song slang; motivational-poster Telugu; flat “simple kids bhajan” wording; English mix-ins in sung lines.
- Do NOT use very common, shallow everyday words when a deeper traditional synonym exists. Sound like a temple poet, not a conversation.
- Imagery should be classical: lotus feet, mandapam lamps, sacred rivers, vibhuti / tulasi / shankha-chakra, dawn sevas, nama japa — not generic “happy life” talk.
- Pallavi = nama-rich, chantable sacred refrain (congregation can repeat), still poetic — not a slogan.
- Charanams = metered-feeling bhakti poetry (gunas, leelas, surrender); dense spiritual meaning in short singable lines.
- Slokam may use elevated Sanskrit or Sanskritised Telugu (original only).
- Title: prefer Telugu script with traditional flavour when it fits.

TELUGU SINGABILITY & PRONUNCIATION (critical for AI vocals — failure if violated)
- Write for a NATIVE Telugu Carnatic/bhajan singer: every syllable must be easy to pronounce clearly when sung.
- Prefer open, vowel-rich words and natural Telugu word endings (-ము, -లు, -ని, -కు, -గా, -మై) that AI singers articulate cleanly.
- Prefer short–medium sung lines (about 4–9 Telugu words). One clear idea per line. Break long compounds across lines if needed.
- Avoid tongue-twisters: dense stacked consonants, rare tongue-breaker sandhi, or overlong Sanskrit compounds that AI mangles.
- Avoid awkward English-letter lookalikes, half-Hindi lines, or mixed-script words inside sung lines.
- Keep Pallavi especially pronunciation-clean (congregation-friendly, no hard clusters).
- Slokam may be Sanskritised but still chantable — short, clear syllables; not a dense stotra dump.
- Self-check: read every line aloud mentally — if any word would sound muddy, wrong language, or hard to pronounce when sung, rewrite it.

BRIEF
- Language: ${language || "Telugu (te) — deep traditional bhakti Telugu script only for sung lines"}
- Title hint: ${title || "(invent a melodic traditional Telugu title)"}
- Deity / theme: ${deity || "general Hindu devotion"}
- Topic / mood: ${topic || "peaceful traditional temple devotion"}
- Lead vocal: ${vocalLabel}
- Music direction hint: ${musicGenre || "traditional Telugu Carnatic-devotional bhajan"}
${regenBlock}

MANDATORY SONG FORM (classic keerthana — Pallavi is the repeating chorus)
Write the lyrics file EXACTLY in this section order (use these tags):

[Pallavi]
… 2–4 short melodic lines. Sacred HOOK / chorus. Nama-rich, deep Telugu, singable; rhyme or assonance OK. Not a list of plain common words.

[Anupallavi]
… 2–4 lines that lift from the Pallavi in the same elevated register (preferred).

[Pallavi]
… REPEAT the SAME Pallavi text again (do not rewrite).

[Slokam]
… 1 short original Sanskrit or Sanskritised-Telugu sloka (2–4 lines) praising the deity — soft chant break. Not copied from famous stotras.

[Pallavi]
… REPEAT the SAME Pallavi text again.

[Charanam 1]
… 4–6 deep poetic lines (guna, leela, karuna, sharanu). Traditional bhakti Telugu — never prosaic speech.

[Pallavi]
… REPEAT the SAME Pallavi text again.

[Charanam 2]
… 4–6 new deep poetic lines; return naturally to Pallavi.

[Pallavi]
… REPEAT the SAME Pallavi text again (final chorus).

Optional [Charanam 3] then one last [Pallavi] if the song needs length.

HARD RULES
1. Pallavi text must appear at least 4 times (opening + after Anupallavi + after Slokam + after each Charanam). Same words every time.
2. Pallavi must sound like a sacred song refrain — melody-friendly, nama-rich, spiritually deep — NOT dry word stacks, slogans, or common spoken phrases.
3. Charanams = traditional bhakti poetry with deep spiritual vocabulary. Ban modern slang, film-copy lines, and general/colloquial Telugu.
4. Include exactly one [Slokam] block between early Pallavi cycles as specified.
5. No copyrighted film lyrics; no copying Annamayya/Tyagaraja verses verbatim; original only (spirit of tradition, not plagiarism).
6. Keep lines short–medium for singing, but keep WORD CHOICE deep and traditional.
7. Self-check before output: if any line sounds like everyday talk or “simple modern bhajan”, rewrite it in classical temple diction.

STYLE_PROMPT (English, for Suno — MUST match THESE lyrics, not a fixed slow template)
First decide the song's musical energy from the lyrics you wrote:
- peaceful / meditative / lamp aarti / surrender → slow (≈60–75 BPM), soft mridangam, spacious
- graceful Devi / Lakshmi / flowing bhakti → slow–medium (≈75–90 BPM), lyrical violin/veena
- joyful nama sankirtana / Govinda / festive → medium (≈90–105 BPM), brighter mridangam + manjira
- Hanuman courage / protection / marching devotion → medium–brisk (≈100–115 BPM), firmer percussion (still classical, NOT rock/EDM)
- morning Suprabhata / Surya → medium bright, not sleepy-slow
- Slokam section may feel slightly freer / chant-like; Pallavi returns to chosen groove

THEN write style_prompt as comma-separated tags that FIT that choice (perfect for Suno singing — no language/pronunciation failures):
- traditional Telugu Carnatic keerthana / temple bhajan only (no film item, no EDM, no pop beat drop, no Hindi film vocal style)
- MUST include: "authentic Telugu language vocals", "native Telugu pronunciation", "crystal clear Telugu diction", "perfect Telugu enunciation", "no accent issues", "singable Telugu syllables"
- ${vocalLabel} native Telugu Carnatic/bhajan vocalist, classical gamakas, steady shruti, emotionally reverent (not theatrical film drama)
- tanpura drone; choose percussion intensity to match energy (soft vs firm mridangam / khanjira / manjira)
- instruments that serve the deity mood (flute for Krishna, veena/violin for Devi/Shiva, temple bells for Venkateswara, firm classical percussion for Narasimha/Hanuman, etc.)
- Only Hindu deities / avataras for this channel: Shiva, Parvati, Sri Vishnu, Sri Rama, Krishna, Narasimha, Lakshmi, Saraswati, Durga, Hanuman, Ganesha, Subrahmanya, Venkateswara, Surya, Ayyappa, Annapurna, etc. Do not write Sai Baba / Shirdi songs.
- EXPLICIT tempo words: e.g. "slow 68 BPM" OR "medium 96 BPM" OR "brisk classical 108 BPM" — pick ONE range that fits the lyrics
- temple mandapam reverb appropriate to energy (intimate for slow; lively hall for sankirtana)
- "Pallavi chorus repeats", "brief sloka chant break", "dynamic contrast Charanam then return to Pallavi"
- "studio-quality vocal take", "no mumbled words", "lyrics fully intelligible in Telugu"
Do NOT default every song to "slow" or every song to "fast". Wrong tempo for the lyrics is a failure.
Do NOT omit Telugu pronunciation tags — missing them is a failure.
Max ~650 characters; no quotes inside.

Also set:
- "tempo": one of "slow" | "slow_medium" | "medium" | "medium_brisk"
- "bpm_hint": integer in the range you chose
- "energy": short phrase e.g. "meditative", "graceful", "sankirtana-joy", "courageous-bhakti"

Respond with ONLY valid JSON (no markdown fences):
{"title":"...","style_prompt":"...","lyrics":"...","tempo":"...","bpm_hint":90,"energy":"..."}`;
}

function extractJson(text) {
  if (!text) throw new Error("Empty agent response");
  const trimmed = text.trim();
  const fence = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  const candidate = fence ? fence[1].trim() : trimmed;
  const start = candidate.indexOf("{");
  const end = candidate.lastIndexOf("}");
  if (start === -1 || end === -1) throw new Error("No JSON object in agent response");
  return JSON.parse(candidate.slice(start, end + 1));
}

function resolveCliBinary() {
  const configured = process.env.CURSOR_CLI_PATH || process.env.CURSOR_AGENT_PATH;
  if (configured && fs.existsSync(configured)) return configured;
  const candidates = [
    "cursor-agent",
    "agent",
    path.join(process.env.HOME || "", ".local/bin/cursor-agent"),
    path.join(process.env.HOME || "", ".local/bin/agent"),
    "/usr/local/bin/cursor-agent",
  ];
  for (const c of candidates) {
    if (!c || c.endsWith("/")) continue;
    try {
      if (fs.existsSync(c) && fs.statSync(c).isFile()) return c;
    } catch {
      /* ignore */
    }
  }
  return null;
}

function runCli(prompt, apiKey) {
  const bin = resolveCliBinary();
  if (!bin) {
    const err = new Error("Cursor CLI not found (set CURSOR_CLI_PATH or install cursor-agent)");
    err.code = "CLI_MISSING";
    throw err;
  }

  // ask mode = read-only Q&A — faster than a full coding agent for JSON lyrics
  const args = [
    "-p",
    "--mode",
    "ask",
    "--output-format",
    "text",
    "--model",
    MODEL,
    "--trust",
    "--workspace",
    WORKSPACE,
    "--api-key",
    apiKey,
    prompt,
  ];

  // `cursor agent ...` if binary is the main cursor launcher
  const useCursorAgentSub = /(?:^|\/)cursor$/.test(bin);
  const cmd = bin;
  const finalArgs = useCursorAgentSub ? ["agent", ...args] : args;

  return new Promise((resolve, reject) => {
    const child = spawn(cmd, finalArgs, {
      env: { ...process.env, CURSOR_API_KEY: apiKey },
      cwd: WORKSPACE,
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`Cursor CLI timed out after ${CLI_TIMEOUT_MS}ms`));
    }, CLI_TIMEOUT_MS);

    child.stdout.on("data", (d) => {
      stdout += d.toString();
    });
    child.stderr.on("data", (d) => {
      stderr += d.toString();
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(
          new Error(
            `Cursor CLI exit ${code}: ${(stderr || stdout).slice(0, 600) || "no output"}`,
          ),
        );
        return;
      }
      resolve({ raw: stdout, backend: "cli", binary: bin });
    });
  });
}

function sdkErrorMessage(result) {
  const err = result?.error;
  if (!err) return "Cursor SDK agent run failed";
  if (typeof err === "string") return err;
  if (err.message) return String(err.message);
  try {
    return JSON.stringify(err);
  } catch {
    return "Cursor SDK agent run failed";
  }
}

async function runSdkOnce(prompt, apiKey, modelId) {
  const result = await Agent.prompt(prompt, {
    apiKey,
    model: { id: modelId },
    local: { cwd: WORKSPACE },
  });
  if (result.status === "error") {
    const err = new Error(sdkErrorMessage(result));
    err.runId = result.id;
    err.model = modelId;
    throw err;
  }
  const raw = typeof result.result === "string" ? result.result : JSON.stringify(result.result);
  return {
    raw,
    backend: "sdk",
    runStatus: result.status,
    runId: result.id,
    model: modelId,
  };
}

async function runSdk(prompt, apiKey) {
  const failures = [];
  for (const modelId of MODEL_FALLBACKS) {
    try {
      return await runSdkOnce(prompt, apiKey, modelId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.warn(`[lyrics-agent] SDK model ${modelId} failed: ${msg.slice(0, 240)}`);
      failures.push(`${modelId}: ${msg.slice(0, 180)}`);
    }
  }
  throw new Error(`All SDK models failed. ${failures.join(" | ")}`);
}

async function generateWithBackend(prompt, apiKey) {
  const preferCli = BACKEND === "cli" || BACKEND === "auto";
  const preferSdk = BACKEND === "sdk" || BACKEND === "auto";

  if (preferCli && resolveCliBinary()) {
    try {
      return await runCli(prompt, apiKey);
    } catch (err) {
      if (BACKEND === "cli") throw err;
      console.warn("[lyrics-agent] CLI failed, falling back to SDK:", err.message);
    }
  } else if (BACKEND === "cli") {
    throw new Error("LYRICS_BACKEND=cli but Cursor CLI binary not found");
  }

  if (preferSdk) {
    return await runSdk(prompt, apiKey);
  }
  throw new Error(`Unknown LYRICS_BACKEND=${BACKEND}`);
}

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    model: MODEL,
    fallbacks: MODEL_FALLBACKS,
    backend: BACKEND,
    cli_available: Boolean(resolveCliBinary()),
    cli_path: resolveCliBinary(),
  });
});

app.post("/generate", async (req, res) => {
  const apiKey = process.env.CURSOR_API_KEY;
  if (!apiKey) {
    res.status(503).json({ error: "CURSOR_API_KEY missing" });
    return;
  }

  const body = req.body || {};
  const variationSeed = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const prompt = buildPrompt({ ...body, variationSeed });
  const started = Date.now();

  try {
    const {
      raw,
      backend,
      runStatus,
      runId,
      binary,
      model: usedModel = MODEL,
    } = await generateWithBackend(prompt, apiKey);
    const parsed = extractJson(raw);
    if (!parsed.lyrics || !String(parsed.lyrics).trim()) {
      res.status(502).json({ error: "Agent returned no lyrics", raw: String(raw).slice(0, 800) });
      return;
    }

    res.json({
      data: {
        title: String(parsed.title || body.title || "Untitled Devotional").slice(0, 200),
        style_prompt: String(parsed.style_prompt || "").slice(0, 1000),
        lyrics: String(parsed.lyrics).trim(),
        tempo: parsed.tempo ? String(parsed.tempo) : null,
        bpm_hint: typeof parsed.bpm_hint === "number" ? parsed.bpm_hint : null,
        energy: parsed.energy ? String(parsed.energy) : null,
        model: usedModel,
        backend,
        cli_path: binary || null,
        run_status: runStatus || "ok",
        run_id: runId || null,
        elapsed_ms: Date.now() - started,
      },
    });
  } catch (err) {
    res.status(502).json({
      error: err instanceof Error ? err.message : String(err),
      model: MODEL,
      fallbacks: MODEL_FALLBACKS,
      backend: BACKEND,
    });
  }
});

function buildImagePrompt({ deity, mood, lyricsHint, filename, outFile }) {
  const deityBit = deity || "Hindu temple deity";
  const moodBit = mood || "serene sacred devotion";
  const hint = (lyricsHint || "").slice(0, 240);
  const file = filename || "thumb_bg.png";
  const dest = outFile || path.join(WORKSPACE, file);
  return `The user explicitly asks you to generate a PREMIUM YouTube thumbnail BACKGROUND image and save it to disk.

STEP 1 — Call GenerateImage exactly once:
- filename: "${file}"
- aspect_ratio: "16:9"
- description: Ultra-premium cinematic YouTube thumbnail still for Telugu Hindu devotion channel. Subject: powerful heroic depiction of ${deityBit} filling the LEFT half of frame (close-medium shot, ornate crown, jewelry, garland, dramatic expression matching ${moodBit}). Background: ancient South Indian stone temple mandapam, carved pillars, fiery golden sunset rim light, sacred aura/halo behind deity head, floating dust motes, optional oil lamp glow. Composition: deity LEFT, RIGHT third kept softer/emptier for later title overlay. Lyric mood: ${hint || "divine bhakti power"}. Style: photorealistic epic, rich gold-orange-red palette, high contrast, masterpiece thumbnail art. STRICT: NO text, NO Telugu or English letters, NO watermark, NO logo, NO captions, NO Sai Baba, NO modern people selfies.

STEP 2 — REQUIRED: copy the generated image onto this absolute path using Shell:
  cp <generated-image-path> "${dest}"
If you are unsure where GenerateImage wrote the file, search then copy:
  find /tmp /home /root /app /var -name "${file}" 2>/dev/null | head -5
  ls -la "${WORKSPACE}"
Then ensure "${dest}" exists (png/jpg/webp bytes on disk).

STEP 3 — Respond with ONLY valid JSON (no markdown):
{"ok":true,"path":"${dest}"}`;
}

function findNewestImage(dir, afterMs, depth = 0) {
  const exts = new Set([".png", ".jpg", ".jpeg", ".webp"]);
  let best = null;
  let bestM = afterMs;
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return null;
  }
  for (const ent of entries) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      if (depth >= 3 || ent.name === "node_modules" || ent.name === ".git") continue;
      const nested = findNewestImage(full, afterMs, depth + 1);
      if (nested) {
        const st = fs.statSync(nested);
        if (st.mtimeMs >= bestM) {
          best = nested;
          bestM = st.mtimeMs;
        }
      }
      continue;
    }
    if (!ent.isFile()) continue;
    if (!exts.has(path.extname(ent.name).toLowerCase())) continue;
    let st;
    try {
      st = fs.statSync(full);
    } catch {
      continue;
    }
    if (st.mtimeMs >= bestM) {
      best = full;
      bestM = st.mtimeMs;
    }
  }
  return best;
}

app.post("/generate-image", async (req, res) => {
  const apiKey = process.env.CURSOR_API_KEY;
  if (!apiKey) {
    res.status(503).json({ error: "CURSOR_API_KEY missing" });
    return;
  }

  const body = req.body || {};
  const started = Date.now();
  const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const filename = `thumb_bg_${stamp}.png`;
  const preferred = path.join(WORKSPACE, filename);
  const prompt = buildImagePrompt({
    deity: body.deity,
    mood: body.mood,
    lyricsHint: body.lyrics_hint || body.lyricsHint,
    filename,
    outFile: preferred,
  });

  let agent;
  try {
    const before = Date.now() - 1000;
    agent = await Agent.create({
      apiKey,
      model: { id: process.env.CURSOR_IMAGE_MODEL || MODEL },
      local: { cwd: WORKSPACE },
    });
    const run = await agent.send(prompt);
    const toolHits = [];
    const eventTypes = new Set();
    try {
      for await (const event of run.stream()) {
        const t = String(event?.type || event?.event || "");
        if (t) eventTypes.add(t);
        const raw = JSON.stringify(event);
        if (
          /image|generate|tool|media|artifact|file/i.test(t) ||
          /GenerateImage|image\/|\.png|\.jpe?g|base64/i.test(raw)
        ) {
          toolHits.push({
            type: t,
            keys: Object.keys(event || {}).slice(0, 40),
            snippet: raw.slice(0, 1500),
          });
        }
      }
    } catch (streamErr) {
      console.warn("[lyrics-agent] image stream:", streamErr?.message || streamErr);
    }

    const result = (await run.wait()) || run;

    if (result.status === "error") {
      const msg =
        typeof result.error === "object" && result.error?.message
          ? result.error.message
          : "Cursor image agent run failed";
      res.status(502).json({
        error: msg,
        run_id: result.id,
        tools: toolHits.slice(0, 8),
        event_types: [...eventTypes],
      });
      return;
    }

    let imagePath = null;
    let inlineB64 = null;
    for (const hit of toolHits) {
      const mPath = hit.snippet.match(/"(?:path|filePath|absolutePath)"\s*:\s*"([^"]+\.(?:png|jpe?g|webp))"/i);
      const mB64 = hit.snippet.match(/"b64(?:_json)?"\s*:\s*"([A-Za-z0-9+/=]{80,})"/);
      const mDataUrl = hit.snippet.match(/data:image\/(?:png|jpeg);base64,([A-Za-z0-9+/=]+)/);
      if (mPath && fs.existsSync(mPath[1])) imagePath = mPath[1];
      if (mB64) inlineB64 = mB64[1];
      if (mDataUrl) inlineB64 = mDataUrl[1];
    }

    if (!imagePath) {
      imagePath = fs.existsSync(preferred) ? preferred : findNewestImage(WORKSPACE, before);
    }
    if (!imagePath && inlineB64) {
      fs.writeFileSync(preferred, Buffer.from(inlineB64, "base64"));
      imagePath = preferred;
    }
    if ((!imagePath || !fs.existsSync(imagePath)) && result.result) {
      const agentText =
        typeof result.result === "string" ? result.result : JSON.stringify(result.result);
      const pathMatch = agentText.match(/(\/[^\s"'\\]+\.(?:png|jpe?g|webp))/i);
      if (pathMatch && fs.existsSync(pathMatch[1])) imagePath = pathMatch[1];
    }

    if (!imagePath || !fs.existsSync(imagePath)) {
      res.status(502).json({
        error: "GenerateImage did not produce a file in workspace",
        agent: String(result.result || "").slice(0, 500),
        run_id: result.id,
        tools: toolHits.slice(0, 8),
        event_types: [...eventTypes],
        workspace_files: fs.readdirSync(WORKSPACE).slice(0, 40),
      });
      return;
    }

    if (imagePath !== preferred) {
      fs.copyFileSync(imagePath, preferred);
      imagePath = preferred;
    }

    const buf = fs.readFileSync(imagePath);
    res.json({
      data: {
        path: imagePath,
        filename: path.basename(imagePath),
        mime: imagePath.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg",
        b64: buf.toString("base64"),
        bytes: buf.length,
        model: process.env.CURSOR_IMAGE_MODEL || MODEL,
        run_status: result.status,
        elapsed_ms: Date.now() - started,
      },
    });
  } catch (err) {
    res.status(502).json({
      error: err instanceof Error ? err.message : String(err),
      model: process.env.CURSOR_IMAGE_MODEL || MODEL,
    });
  } finally {
    try {
      await agent?.[Symbol.asyncDispose]?.();
    } catch {
      /* ignore */
    }
    try {
      await agent?.close?.();
    } catch {
      /* ignore */
    }
  }
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(
    `lyrics-agent on ${PORT} model=${MODEL} fallbacks=${MODEL_FALLBACKS.join(",")} backend=${BACKEND} cli=${resolveCliBinary() || "none"}`,
  );
});

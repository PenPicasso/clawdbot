# ClawDBot Phase 2 — Autonomous AI Agent via OpenClaw

> **Copy this entire file into a new Sonnet session to begin Phase 2.**
> Sonnet plans. Haiku executes. You (Opus) can peek in anytime.

---

## Table of Contents
1. [Current State (Phase 1 Complete)](#1-current-state)
2. [Phase 2 Goal](#2-phase-2-goal)
3. [Architecture Overview](#3-architecture-overview)
4. [OpenClaw Integration Plan](#4-openclaw-integration-plan)
5. [Step-by-Step Implementation](#5-step-by-step-implementation)
6. [Dual-Model Agent Loop](#6-dual-model-agent-loop)
7. [Token Estimates & Cost Model](#7-token-estimates--cost-model)
8. [Orchestrator Model (Sonnet → Haiku → Opus)](#8-orchestrator-model)
9. [DNS Cutover (Prerequisite)](#9-dns-cutover-prerequisite)
10. [Critical Files Reference](#10-critical-files-reference)

---

## 1. Current State

**Phase 1 is LIVE.** ClawDBot (@Athena27bBot) is running on Oracle Cloud:

| Component | Status | Details |
|-----------|--------|---------|
| Telegram Bot | LIVE | @Athena27bBot, webhook active |
| FastAPI Backend | LIVE | Oracle VM, systemd `openclaw.service` |
| Fast Model (Ollama) | LIVE | gemma3:4b, local CPU, ~13s response |
| Deep Model (HF Space) | LIVE | Gemma 27B at `mansamensa-clawdbot-27b.hf.space` |
| HTTPS Tunnel | LIVE | Cloudflare quick tunnel (temporary) |
| Job Queue | LIVE | SQLite + aiosqlite, WAL mode |
| Poller | LIVE | Background asyncio task, retry + fallback |

**Pending from Phase 1:**
- DNS propagation for `bot.energydial.net` (nameservers changed to Cloudflare)
- Once DNS resolves → switch from quicktunnel to named tunnel (permanent URL)
- Commands to run when DNS is ready:
  ```bash
  sudo systemctl stop quicktunnel && sudo systemctl disable quicktunnel
  sudo mv /etc/cloudflared/config.yml.bak /etc/cloudflared/config.yml
  sudo systemctl enable --now cloudflared
  curl -s -X POST "https://api.telegram.org/bot8771088454:AAHB306qfS40Bm16OWtzu0yghkEs-18Ul_s/setWebhook" \
    -H "Content-Type: application/json" \
    -d '{"url":"https://bot.energydial.net/webhook/clawdsecret2026"}'
  ```

**Infrastructure:**
- Oracle VM: Ubuntu 22.04 x86_64, Always Free tier
- SSH: via Cloud Shell key (original key had permission issues on company PC)
- App path: `/opt/openclaw/app/`
- Data path: `/opt/openclaw/data/jobs.db`
- Env file: `/opt/openclaw/app/.env`
- Local code: `C:\dev\clawdbot\`

---

## 2. Phase 2 Goal

Transform ClawDBot from a simple prompt-response bot into an **autonomous AI agent** with:

1. **PLAN → EXECUTE → TEST → CRITIQUE → ITERATE loops** — the bot doesn't just answer, it reasons through multi-step problems
2. **Tool use** — web search, calculations, code execution, file operations
3. **Memory** — conversation context persists across sessions (SQLite + vector embeddings)
4. **Dual-model intelligence** — fast model (4B) handles routine work, deep model (27B) handles planning/critique
5. **Multi-channel support** — Telegram now, expandable to Discord/Slack/Web later
6. **Skill system** — modular capabilities that can be added without touching core code

**Framework:** [OpenClaw](https://github.com/openclaw/openclaw) — open-source agent orchestration platform.

---

## 3. Architecture Overview

```
User (Telegram)
    │
    ▼
OpenClaw Gateway (Node.js control plane)
    │
    ├── Channel: Telegram (already working)
    ├── Channel: Discord (future)
    ├── Channel: Web (future)
    │
    ▼
Session Manager ←→ Memory Store (SQLite/Redis)
    │
    ▼
Agent Loop (PLAN → EXECUTE → TEST → CRITIQUE → ITERATE)
    │
    ├── Fast Executor: Ollama gemma3:4b (local, <15s)
    │       └── Handles: routine replies, tool calls, code gen
    │
    ├── Deep Planner/Critic: HF Space Gemma 27B (remote, 2-15min)
    │       └── Handles: planning, critique, complex reasoning
    │
    └── Tools
        ├── web_search (DuckDuckGo/SearXNG)
        ├── calculator (Python eval sandbox)
        ├── code_exec (Docker sandbox)
        ├── file_read / file_write
        ├── memory_recall (vector similarity search)
        └── custom skills (user-defined)
```

**Key insight:** The existing FastAPI backend stays. OpenClaw wraps around it as the orchestration layer, adding agent loops, tools, and memory on top of the existing Telegram + model infrastructure.

---

## 4. OpenClaw Integration Plan

### What OpenClaw Provides

OpenClaw (https://github.com/openclaw/openclaw) is a Node.js gateway that provides:

| Feature | What It Does | How We Use It |
|---------|-------------|---------------|
| **Gateway** | Control plane for agent orchestration | Routes messages through agent loop before responding |
| **Channels** | 22+ messaging integrations | Telegram adapter (replace our webhook handler) |
| **Sessions** | Conversation state management | Persist context across messages per user |
| **Skills** | Modular capability plugins | Web search, code exec, memory recall |
| **Tools** | Function-calling interface | Let models invoke tools with structured I/O |
| **Model Failover** | Automatic fallback between models | Our existing fast/deep pattern, formalized |
| **Plugins** | Extensible middleware | Add logging, rate limiting, admin controls |

### What We Keep From Phase 1

| Component | Keep/Replace | Reason |
|-----------|-------------|--------|
| Ollama (gemma3:4b) | KEEP | Fast executor, already running |
| HF Space (Gemma 27B) | KEEP | Deep planner/critic, already live |
| SQLite job queue | KEEP (extend) | Add memory tables alongside job queue |
| systemd services | KEEP | Add openclaw-gateway.service |
| Cloudflare tunnel | KEEP | HTTPS for both Telegram and OpenClaw |
| FastAPI server | ADAPT | Becomes internal API; OpenClaw handles external routing |

### What OpenClaw Adds

1. **Agent loop controller** — PLAN→EXECUTE→TEST→CRITIQUE→ITERATE
2. **Tool registry** — structured function calling
3. **Session/memory manager** — conversation persistence
4. **Skill plugins** — modular capabilities
5. **Multi-channel routing** — Telegram now, others later

---

## 5. Step-by-Step Implementation

### Phase 2A: Foundation (Node.js + OpenClaw Setup)

**Estimated effort:** 2-3 Haiku sessions

```
Step 2A.1 — Install Node.js on Oracle VM
  ssh into VM
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
  node --version  # confirm v20+
  npm --version

Step 2A.2 — Clone and configure OpenClaw
  cd /opt/openclaw
  sudo git clone https://github.com/openclaw/openclaw.git gateway
  cd gateway
  sudo npm install
  # Copy and edit config (see below)

Step 2A.3 — Configure OpenClaw for our stack
  Create /opt/openclaw/gateway/.env:
    TELEGRAM_BOT_TOKEN=8771088454:AAHB306qfS40Bm16OWtzu0yghkEs-18Ul_s
    OLLAMA_URL=http://localhost:11434
    HF_SPACE_URL=https://mansamensa-clawdbot-27b.hf.space
    SQLITE_PATH=/opt/openclaw/data/agent.db
    PORT=3000

Step 2A.4 — Create systemd service for OpenClaw gateway
  /etc/systemd/system/openclaw-gateway.service
  ExecStart=/usr/bin/node /opt/openclaw/gateway/src/index.js
  After=network-online.target ollama.service openclaw.service

Step 2A.5 — Update Cloudflare tunnel to route:
  /webhook/* → localhost:8080 (existing FastAPI)
  /gateway/* → localhost:3000 (OpenClaw gateway)
  Or: OpenClaw handles Telegram directly on :3000
```

### Phase 2B: Agent Loop (Dual-Model PLAN→EXECUTE)

**Estimated effort:** 3-4 Haiku sessions

```
Step 2B.1 — Create agent loop module
  /opt/openclaw/gateway/skills/agent-loop.js

  The loop:
    1. PLAN: Send user message + context to Gemma 27B (deep)
       → Returns structured plan: {steps: [...], tools_needed: [...]}
    2. EXECUTE: Send each step to Gemma 4B (fast) with tool access
       → Fast model executes, calls tools, produces results
    3. TEST: Fast model self-checks results against plan
    4. CRITIQUE: Send results back to 27B for quality review
       → Returns: {approved: bool, feedback: str, revision: str}
    5. ITERATE: If not approved, fast model revises based on feedback
       → Max 3 iterations before returning best result

Step 2B.2 — Implement tool registry
  /opt/openclaw/gateway/tools/
    web_search.js  — DuckDuckGo instant answers API (free, no key)
    calculator.js  — safe math eval (mathjs library)
    code_exec.js   — sandboxed Node.js eval (vm2 or isolated-vm)
    memory.js      — SQLite vector search (see Phase 2C)

Step 2B.3 — Create model router adapter
  /opt/openclaw/gateway/models/router.js

  Wraps our existing infrastructure:
    fast(prompt) → POST http://localhost:11434/api/generate (Ollama)
    deep(prompt) → POST https://mansamensa-clawdbot-27b.hf.space/infer
    route(message) → 'fast' | 'deep' (reuse existing keyword logic)

Step 2B.4 — Wire agent loop into OpenClaw message handler
  When message arrives via Telegram channel:
    if route(message) === 'fast':
      → Direct fast model response (no agent loop)
    if route(message) === 'deep':
      → Full agent loop (PLAN→EXECUTE→TEST→CRITIQUE→ITERATE)
      → Send "thinking..." ACK immediately
      → Edit message when done (same pattern as Phase 1 poller)
```

### Phase 2C: Memory System

**Estimated effort:** 2-3 Haiku sessions

```
Step 2C.1 — Extend SQLite schema
  CREATE TABLE memories (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,          -- float32 array, serialized
    created_at REAL NOT NULL,
    importance REAL DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed REAL
  );

  CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,       -- 'user' | 'assistant' | 'system'
    content TEXT NOT NULL,
    created_at REAL NOT NULL
  );

Step 2C.2 — Embedding generation
  Option A: Use Ollama embeddings endpoint
    POST http://localhost:11434/api/embeddings
    {"model": "gemma3:4b", "prompt": "text to embed"}
    → Returns 2048-dim float array

  Option B: Use all-MiniLM-L6-v2 via HF API (384-dim, faster)

Step 2C.3 — Memory recall tool
  On each message:
    1. Generate embedding for user message
    2. Cosine similarity search against memories table
    3. Top-5 relevant memories injected into system prompt
    4. After response, store new memory with importance score

Step 2C.4 — Conversation context
  Last N messages from conversations table included in prompt
  Sliding window: 10 messages for fast, 20 for deep
```

### Phase 2D: Skills System

**Estimated effort:** 2-3 Haiku sessions

```
Step 2D.1 — Skill plugin structure
  /opt/openclaw/gateway/skills/
    index.js          — skill registry and loader
    web-research.js   — multi-step web search + summarize
    code-assistant.js — write/review/debug code
    daily-briefing.js — scheduled news/weather/calendar summary
    study-helper.js   — flashcards, quizzes, spaced repetition

Step 2D.2 — Skill invocation
  User triggers via:
    /skill <name> <args>  — explicit
    Auto-detect from message content (like current deep keyword routing)

Step 2D.3 — Skill template
  module.exports = {
    name: 'web-research',
    description: 'Multi-step web research with source synthesis',
    triggers: ['research', 'find out', 'look up', 'what is'],
    async execute(context, tools) {
      const plan = await context.deep(`Plan research for: ${context.message}`);
      const results = [];
      for (const step of plan.steps) {
        const searchResult = await tools.web_search(step.query);
        results.push(await context.fast(`Summarize: ${searchResult}`));
      }
      return await context.deep(`Synthesize these findings:\n${results.join('\n')}`);
    }
  };
```

### Phase 2E: Testing & Hardening

**Estimated effort:** 1-2 Haiku sessions

```
Step 2E.1 — End-to-end test suite
  Test fast path: simple question → immediate Ollama response
  Test deep path: complex question → agent loop → edited message
  Test tools: "what's 2+2" → calculator tool invoked
  Test memory: ask something, ask again later, verify context recalled
  Test fallback: kill HF Space → verify 4B fallback works

Step 2E.2 — Rate limiting
  Per-user: max 10 messages/minute
  Global: max 50 deep jobs/hour (HF Space is slow)
  Admin bypass for your own chat ID

Step 2E.3 — Error handling
  All tools wrapped in try/catch with graceful degradation
  Agent loop has max iteration limit (3)
  Memory operations are best-effort (don't block responses)

Step 2E.4 — Monitoring
  /admin-status command → system health dashboard
  Log rotation: journalctl --vacuum-time=7d
  SQLite WAL checkpoint: PRAGMA wal_checkpoint(TRUNCATE) daily
```

---

## 6. Dual-Model Agent Loop

This is the core innovation — inspired by Karpathy's AutoResearch pattern:

```
┌─────────────────────────────────────────────┐
│              USER MESSAGE                    │
│  "Compare nuclear vs solar for Nigeria"      │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  ROUTER: deep keywords detected → AGENT LOOP │
│  Send ACK: "Queued for deep analysis..."     │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  STEP 1 — PLAN (Gemma 27B, ~2-5 min)        │
│                                              │
│  System: You are a research planner.         │
│  User: Compare nuclear vs solar for Nigeria  │
│  Context: [relevant memories injected]       │
│                                              │
│  Output: {                                   │
│    "steps": [                                │
│      "Search current Nigeria energy mix",    │
│      "Find nuclear costs for developing...", │
│      "Find solar costs for tropical...",     │
│      "Compare grid stability factors",       │
│      "Synthesize with Nigeria-specific..."   │
│    ],                                        │
│    "tools": ["web_search", "calculator"]     │
│  }                                           │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  STEP 2 — EXECUTE (Gemma 4B, ~13s per step)  │
│                                              │
│  For each plan step:                         │
│    → Fast model generates search queries     │
│    → web_search tool fetches results         │
│    → Fast model summarizes findings          │
│    → calculator tool for cost comparisons    │
│                                              │
│  Output: [result_1, result_2, ..., result_5] │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  STEP 3 — TEST (Gemma 4B, ~13s)             │
│                                              │
│  "Check: do these results answer the         │
│   original question? Any gaps?"              │
│                                              │
│  Output: {complete: true, gaps: []}          │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  STEP 4 — CRITIQUE (Gemma 27B, ~2-5 min)    │
│                                              │
│  "Review this research output for accuracy,  │
│   completeness, and Nigeria-specific          │
│   relevance. Rate 1-10."                     │
│                                              │
│  Output: {                                   │
│    "score": 8,                               │
│    "approved": true,                         │
│    "feedback": "Good. Add note about..."     │
│  }                                           │
└──────────────┬───────────────────────────────┘
               │
               ▼ (if approved)
┌──────────────────────────────────────────────┐
│  STEP 5 — FORMAT & DELIVER                   │
│                                              │
│  Fast model formats final response           │
│  Edit the ACK message with result            │
│  Store conversation in memory                │
│  Store key facts as retrievable memories     │
└──────────────────────────────────────────────┘

Total time: ~5-15 minutes for a deep research query
(vs current: single HF inference, no tools, no memory)
```

**If critique rejects (score < 7):**
- Fast model revises based on feedback
- Loop back to CRITIQUE
- Max 3 iterations, then return best result with disclaimer

---

## 7. Token Estimates & Cost Model

### Sonnet Plans, Haiku Executes

For implementing Phase 2 using Claude Code:

| Task | Model | Est. Tokens (In/Out) | Est. Cost |
|------|-------|---------------------|-----------|
| 2A: Foundation setup | Haiku | 50K/20K | ~$0.07 |
| 2A: Config & debug | Sonnet | 30K/10K | ~$0.27 |
| 2B: Agent loop | Haiku | 80K/40K | ~$0.12 |
| 2B: Planning/review | Sonnet | 40K/15K | ~$0.38 |
| 2C: Memory system | Haiku | 60K/30K | ~$0.09 |
| 2C: Planning/review | Sonnet | 30K/10K | ~$0.27 |
| 2D: Skills system | Haiku | 60K/30K | ~$0.09 |
| 2D: Planning/review | Sonnet | 25K/10K | ~$0.24 |
| 2E: Testing | Haiku | 40K/20K | ~$0.06 |
| 2E: Review/debug | Sonnet | 30K/15K | ~$0.30 |
| **Total** | | **~445K/200K** | **~$1.89** |

**On a $20/month Claude Pro plan:**
- Phase 1 used roughly 40-60% of your daily token budget (lots of debugging)
- Phase 2 should be 3-5 sessions spread across days
- Each session: ~30-45 min of active work
- **Recommendation:** Do 1 phase per day to stay within limits

### Sonnet → Haiku Advisor Pattern

This mirrors Anthropic's "advisor model" but with Sonnet as the senior and Haiku as the junior:

```
YOU (human):  "Implement Phase 2B — agent loop"
     │
     ▼
SONNET (planner):
  - Reads codebase
  - Writes detailed implementation plan
  - Specifies exact files, functions, line numbers
  - Outputs: "Here's the plan. Switch to Haiku and paste this."
     │
     ▼
HAIKU (executor):
  - Receives Sonnet's plan as system prompt
  - Writes code, runs commands, tests
  - If stuck: "I need Sonnet's help with X"
  - If unstuck: completes implementation
     │
     ▼ (if stuck)
SONNET (advisor):
  - Haiku sends its error/confusion
  - Sonnet diagnoses and provides specific fix
  - Back to Haiku to continue
```

**How to do this in Claude Code:**
1. Start session with Sonnet (default)
2. Paste the relevant Phase section
3. Sonnet outputs the plan with exact code
4. Start new session, set model to Haiku: `claude --model haiku`
5. Paste Sonnet's plan as the first message
6. Haiku executes. If it says "stuck", copy the error back to a Sonnet session
7. Sonnet diagnoses, you carry the fix back to Haiku

**Token savings:** ~60% cheaper than pure Sonnet, ~3x faster than pure Sonnet (Haiku responds much faster for code generation).

---

## 8. Orchestrator Model (Sonnet → Haiku → Opus)

### Can Opus peek in as the highest-level orchestrator?

**Yes, absolutely.** Here's how the three-tier model works:

```
OPUS (you invoke manually, rare)
  │  Role: Architect, strategic reviewer, stuck-unblocker
  │  When: Major design decisions, Phase transitions, multi-day debugging
  │  Cost: ~$15/M input, $75/M output — use sparingly
  │
  ▼
SONNET (your default planning model)
  │  Role: Planner, code reviewer, advisor to Haiku
  │  When: Start of each Phase, when Haiku gets stuck, PR reviews
  │  Cost: ~$3/M input, $15/M output — moderate use
  │
  ▼
HAIKU (your execution model)
     Role: Code writer, command runner, test executor
     When: All implementation work, file edits, deploys
     Cost: ~$0.25/M input, $1.25/M output — use freely
```

### How to invoke Opus as peek-in orchestrator:

**Option 1: Claude Code model switching**
```bash
# Normal work
claude --model haiku

# Need Sonnet's brain
claude --model sonnet

# Need Opus for architecture review
claude --model opus
```

**Option 2: In-conversation escalation**
Just say in any session: "Escalate to Opus" or "I need Opus-level thinking on this."
Then start a new `claude --model opus` session with the specific question.

**Option 3: Scheduled Opus reviews**
At each Phase boundary (2A→2B, 2B→2C, etc.):
1. Open Opus session
2. Paste: "Review ClawDBot Phase 2X implementation. Here's the current state: [paste key files]"
3. Opus reviews architecture, catches design flaws, suggests improvements
4. Apply Opus feedback in next Haiku session

**Cost estimate for Opus peek-ins:**
- 5 reviews across Phase 2, ~20K tokens each = ~100K tokens
- Cost: ~$1.50 input + $7.50 output = ~$9 total
- Worth it for catching architectural issues early

---

## 9. DNS Cutover (Prerequisite)

Before starting Phase 2, complete the DNS migration from Phase 1.

**Check if DNS has propagated:**
```bash
nslookup bot.energydial.net
# Should return a Cloudflare IP (104.x.x.x or 172.x.x.x)
```

**If propagated, run on the Oracle VM:**
```bash
# Stop quick tunnel
sudo systemctl stop quicktunnel
sudo systemctl disable quicktunnel

# Restore named tunnel config
sudo mv /etc/cloudflared/config.yml.bak /etc/cloudflared/config.yml

# Start named tunnel
sudo systemctl enable --now cloudflared

# Verify tunnel is working
curl -s https://bot.energydial.net/health

# Update Telegram webhook to permanent URL
curl -s -X POST \
  "https://api.telegram.org/bot8771088454:AAHB306qfS40Bm16OWtzu0yghkEs-18Ul_s/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://bot.energydial.net/webhook/clawdsecret2026"}'
```

**If NOT propagated yet:**
- Check Namecheap → Domain → Custom DNS shows:
  - `lady.ns.cloudflare.com`
  - `rustam.ns.cloudflare.com`
- Check Cloudflare dashboard → DNS → `bot` CNAME record exists pointing to tunnel
- Wait up to 24-48 hours for full propagation
- Phase 2 can start independently (uses existing quick tunnel)

---

## 10. Critical Files Reference

### Local (Windows)
| File | Purpose |
|------|---------|
| `C:\dev\clawdbot\openclaw\main.py` | FastAPI entry point, webhook, lifespan |
| `C:\dev\clawdbot\openclaw\bot.py` | Telegram handlers, command routing |
| `C:\dev\clawdbot\openclaw\models.py` | Ollama + HF Space clients, routing logic |
| `C:\dev\clawdbot\openclaw\config.py` | Environment config loader |
| `C:\dev\clawdbot\openclaw\poller.py` | Background job processor |
| `C:\dev\clawdbot\openclaw\queue.py` | SQLite job queue (aiosqlite) |
| `C:\dev\clawdbot\openclaw\scheduler.py` | APScheduler cron tasks |
| `C:\dev\clawdbot\openclaw\utils.py` | Logger, retry, Telegram helpers |
| `C:\dev\clawdbot\requirements.txt` | Python dependencies |
| `C:\dev\clawdbot\setup\install_oracle_vm.sh` | VM provisioning |
| `C:\dev\clawdbot\setup\install_ollama.sh` | Ollama install |

### Remote (Oracle VM)
| Path | Purpose |
|------|---------|
| `/opt/openclaw/app/` | Application code |
| `/opt/openclaw/app/.env` | Environment variables |
| `/opt/openclaw/data/jobs.db` | SQLite database |
| `/etc/systemd/system/openclaw.service` | FastAPI systemd service |
| `/etc/systemd/system/quicktunnel.service` | Quick tunnel (temporary) |
| `/etc/cloudflared/config.yml.bak` | Named tunnel config (restore later) |
| `/home/ubuntu/.cloudflared/` | Cloudflare tunnel credentials |

### Environment Variables (current .env)
```env
TELEGRAM_BOT_TOKEN=8771088454:AAHB306qfS40Bm16OWtzu0yghkEs-18Ul_s
TELEGRAM_WEBHOOK_SECRET=clawdsecret2026
HF_SPACE_URL=https://mansamensa-clawdbot-27b.hf.space
HF_SPACE_SECRET=
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
WEBHOOK_BASE_URL=https://bot.energydial.net
SQLITE_DB_PATH=/opt/openclaw/data/jobs.db
POLL_INTERVAL_SECONDS=30
MAX_RETRIES=3
BRIEFING_HOUR=8
TIMEZONE=UTC
ADMIN_CHAT_ID=8713019531
FAST_INFER_TIMEOUT=60
```

---

## Quick-Start Prompt for Sonnet

When you open a new Sonnet session to begin Phase 2A, paste this:

> I'm building ClawDBot Phase 2 — upgrading a working Telegram bot into an autonomous AI agent using OpenClaw (https://github.com/openclaw/openclaw). Phase 1 is live: FastAPI backend on Oracle Cloud, Ollama gemma3:4b for fast responses, HF Space Gemma 27B for deep analysis, SQLite job queue, Cloudflare tunnel for HTTPS.
>
> My project is at `C:\dev\clawdbot\`. The Oracle VM has the app at `/opt/openclaw/app/`.
>
> Start with Phase 2A: Install Node.js and OpenClaw gateway on the Oracle VM alongside the existing Python backend. Plan the exact steps, then I'll switch to Haiku to execute. Tell me which SSH commands to run and what files to create.
>
> Read the full plan: `C:\dev\clawdbot\PHASE2_CODEX.md`

---

*Generated 2026-04-10. ClawDBot by RunitBackStudios.*

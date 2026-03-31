# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Asthralios is an AI assistant inspired by the Markizano Draconus story. It provides multi-platform chat interfaces (Discord, Slack), speech recognition/TTS, document ingestion with RAG, code quality analysis, and agentic workflows via LangGraph.

## Commands

```bash
# Install package for development
pip install -e ".[dev]"

# Run the assistant
uv run python -m asthralios [converse|ingest|chat|agent|sentinel]

# Run all tests
uv run pytest tests/

# Run a single test file
uv run pytest tests/asthraliosunit/adapters/test_atwiki.py

# Run a specific test
uv run pytest tests/asthraliosunit/adapters/test_hatchet.py::TestHatchet::test_init
```

## Architecture

### Entry Points
- `lib/asthralios/__init__.py` — `main()` function; initializes config, logger, CLI, and dispatches to subcommands
- `lib/asthralios/cli/` — Argument parsing; actions: `converse`, `ingest`, `chat`, `agent`, `sentinel`, `digest`, `notify`

### Core Modules

**`lib/asthralios/config.py`** — Singleton `Configuration` class using `kizano.Config` + `EasyDict`. Dot-notation access to nested YAML config (e.g., `config.oui.base_url`).

**`lib/asthralios/senses/`** — Input processing:
- `ears.py` — Audio capture via PulseAudio, speech-to-text with `faster-whisper`, TTS with XTTS v2, VAD with configurable thresholds. Uses multiprocessing for responsiveness.
- `hands.py` — Document ingestion (`Hands` class) supporting txt, pdf, json, md, html, docx, pptx, xlsx, csv, xml, yaml. Uses LangChain loaders → PGVector with Ollama embeddings.
- `eyes.py` — (stub)

**`lib/asthralios/asr/`** — Factory + interface pattern for ASR backends. `ASRFactory` creates instances; `FasterWhisperASR` is the primary implementation.

**`lib/asthralios/vad/`** — Factory + interface for Voice Activity Detection. `PyannoteVAD` is the primary implementation.

**`lib/asthralios/chat/`** — Chat platform adapters:
- `adapter.py` — Abstract `ChatAdapter` base; integrates with Open WebUI client over OpenAI-compatible API
- `my_discord.py` — Discord adapter (discord.py, socket intents, slash commands, 2000-char limit)
- `my_slack.py` — Slack adapter (Slack Bolt, socket mode, 4000-char limit)
- `my_msteams.py` — MS Teams stub (unimplemented)
- `manager.py` — `ChatManager` runs each adapter in a subprocess; handles signals and lifecycle
- `agentic.py` — LangGraph state machine with `MessageClassifier` for routing (information/support/action)

**`lib/asthralios/sentinel/`** — LLM-based code quality analysis:
- `cqc.py` — Walks codebase, sends Python files to LLM for review
- `types.py` — Pydantic models: `CQCResult` (severity, CWE, CVE, OWASP, lines, remediation), `CQCResultSet`
- `prompts.py` — System/user prompts for code analysis

**`lib/asthralios/adapters/`** — External service integrations:
- `atwiki.py` — Atlassian Confluence (`AtlassianWiki` class, pagination via generators)
- `hatchet.py` — GitHub (`Hatchet` class, org-based access, workflow/log management)

**`lib/asthralios/brain/`** — 2nd Brain feature: captures messages from a designated inbox channel, classifies them with an LLM, files them as Obsidian-compatible Markdown, and maintains a SQLite audit log.
- `schema.py` — Pydantic v2 models: `ClassificationResult`, `InboxLogRecord`, per-category entries (`PersonEntry`, `ProjectEntry`, `IdeaEntry`, `AdminEntry`, `MusingEntry`, `EventEntry`)
- `prompts.py` — All LLM prompts: classifier, daily digest, weekly digest
- `classifier.py` — `BrainClassifier` uses LangChain `init_chat_model`; returns `ClassificationResult`; handles low-confidence with clarification requests; strips markdown fences from LLM output
- `writer.py` — `BrainWriter` writes `{vault}/{category}/{YYYY-MM-DD}-{slug}.md` with YAML frontmatter
- `db.py` — `BrainDB` SQLite audit log; tables: `inbox_log`, `digest_log`; query helpers for digest generation
- `digest.py` — `run_digest(config, 'daily'|'weekly')` builds context from DB, calls LLM, returns text
- `rbac.py` — `RBACManager`, `UserIdentity`, `AccessContext`; resolves platform user → role; logs every interaction to `access_log`; enforces access before any LLM call; roles: `blocked < user < admin`

**`lib/asthralios/voice/`** — Whisper fine-tuning:
- `trainer.py` — LoRA-based fine-tuning for custom vocabulary (kizano dict)
- `modern_trainer.py` — ATCO2 ATC dataset trainer using Whisper-small

### Key Patterns
- **Singleton:** `Configuration`
- **Factory:** `ASRFactory`, `VADFactory`
- **Adapter:** `ChatAdapter` base with per-platform subclasses
- **Multiprocessing:** `ChatManager` spawns each chat adapter in its own process
- **LangGraph:** Agentic workflows in `chat/agentic.py`
- **Barrel imports:** `senses/`, `sentinel/`, `chat/` expose selected symbols via `__init__.py`

### Chat Adapter Changes (v0.2)
- `adapter.py` — `get_message_history()` replaced by `get_thread_history(thread_id)` (thread-only context, capped at `config.oui.thread_context_limit`). Added `on_brain_message()` and `is_brain_channel()` for brain routing.
- `my_slack.py` — Implements `get_thread_history()` via `conversations_replies`; routes brain channels to `on_brain_message()`; handles `fix: <category>` commands; exposes `send_slack_message(config, channel, message)` for proactive sends.
- `my_discord.py` — Same brain routing and fix handling; exposes `send_discord_message(config, channel_id, message)` as a standalone async function.

### CLI Subcommands (v0.2)
- `digest --daily|--weekly [--deliver-slack CHANNEL] [--deliver-discord CHANNEL_ID]` — Generate and optionally deliver a digest
- `notify --slack CHANNEL MESSAGE | --discord CHANNEL_ID MESSAGE` — Proactive send without an incoming event
- `users list` — Print all known users and their roles
- `users set-role --platform slack|discord --user-id ID --role admin|user|blocked` — Change a user's role
- `users log [--user-id ID] [--limit N]` — Print access log

### RBAC Design Invariants
- Identity is resolved once at the platform boundary; all downstream code receives `AccessContext`
- Every interaction is logged to `access_log` regardless of outcome (append-only)
- Roles live in SQLite; config seeds admins (config always wins via `force_role=True`)
- The LLM never sees role data — enforcement is code, not prompts
- Blocked users get one polite reply on first contact, then silence (still logged)
- `notify` and `digest --deliver-*` are implicitly admin-only (require server shell access); logged with `platform='system'`, `platform_user_id='cli'`

### Config Keys (brain module)
```yaml
brain:
  inbox_channel: "sb-inbox"       # Slack channel name or Discord name/ID; list for multiple
  vault_path: "/home/user/brain"  # Obsidian vault root
  db_path: "/home/user/brain/.brain.db"  # SQLite audit log (NOT inside vault)
  model: "llama3.2:3b"            # LLM for classification
  provider: "ollama"
  confidence_threshold: 0.60      # Below this → ask for clarification

oui:
  thread_context_limit: 10        # Max thread messages sent to LLM context

rbac:
  admins:
    slack: "U01234ABC"            # Raw Slack user ID (profile → three-dot → Copy member ID)
    discord: "123456789012"       # Discord snowflake (Settings → Advanced → Developer Mode → right-click self → Copy User ID)
    # Both accept lists: slack: ["U01234ABC", "U09876ZYX"]
  default_role: "user"            # Role for new users on first contact; set "blocked" for fully private bot
  blocked_message: >
    This assistant is a private tool. If you think this is an error,
    reach out to the owner directly.
```

### LLM Backends
- **Ollama** (local, default `127.0.0.1:11434`) — used in `gpt.py` and for embeddings
- **Open WebUI** — primary chat backend via OpenAI-compatible API
- **OpenAI API** — configured via `OPENAI_BASE_URL` (can point to local server)

### Environment Variables
Loaded from `.env` (not committed). Key vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OUI_IMAGE_MODEL`, `GOOGLE_API_KEY`.

### Test Structure
Tests live in `tests/asthraliosunit/`. The `runtests.py` sets `PYTHONPATH=lib` and `UNIT_TESTING=1`. Tests use `unittest.mock` for external service isolation.

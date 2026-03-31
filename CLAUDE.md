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
- `lib/asthralios/cli/` — Argument parsing; actions: `converse`, `ingest`, `chat`, `agent`, `sentinel`

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

### LLM Backends
- **Ollama** (local, default `127.0.0.1:11434`) — used in `gpt.py` and for embeddings
- **Open WebUI** — primary chat backend via OpenAI-compatible API
- **OpenAI API** — configured via `OPENAI_BASE_URL` (can point to local server)

### Environment Variables
Loaded from `.env` (not committed). Key vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OUI_IMAGE_MODEL`, `GOOGLE_API_KEY`.

### Test Structure
Tests live in `tests/asthraliosunit/`. The `runtests.py` sets `PYTHONPATH=lib` and `UNIT_TESTING=1`. Tests use `unittest.mock` for external service isolation.

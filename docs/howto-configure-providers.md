# How to Configure an Inference Provider

Exercise Coach uses an LLM to generate workout plans and assess completed sessions.
Five providers are supported. This guide shows how to set up each one and switch between them.

## Prerequisites

- `config/config.toml` exists (run `coach setup` if not)
- macOS 13+ for cloud/local providers; macOS 26+ for Swift and Apple Intelligence

---

## Option A: Swift Foundation Models (recommended on macOS 26+)

Uses Apple's on-device Foundation Models framework. Private, fast, and free.

**Requirements:** macOS 26 (Tahoe) or later.

1. Build the Swift inference binary:

   ```bash
   make -C swift build
   ```

   This produces `swift/.build/release/CoachInfer`. Run `make -C swift help` to
   see all available targets (`build`, `debug`, `test`, `clean`, `smoke`).

2. Set `provider = "swift"` in `config/config.toml`:

   ```toml
   [llm]
   provider = "swift"

   [llm.swift]
   binary = "swift/.build/release/CoachInfer"
   ```

3. Verify:

   ```bash
   uv run coach setup --non-interactive
   ```

   The provider table should show Swift as **Yes / ready**. To run a live
   end-to-end test against Apple Intelligence:

   ```bash
   make -C swift smoke
   ```

---

## Option B: Anthropic API

Uses Claude via the Anthropic API. Works on any macOS version. Requires an API key.

1. Get an API key from [console.anthropic.com](https://console.anthropic.com).

2. Set the environment variable:

   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

   For persistence, add it to `~/.zshrc` or `~/.zprofile`.

3. Set `provider = "anthropic"` in `config/config.toml`:

   ```toml
   [llm]
   provider = "anthropic"

   [llm.anthropic]
   model = "claude-sonnet-4-20250514"
   ```

4. Verify:

   ```bash
   uv run coach setup --non-interactive
   ```

   The provider table should show Anthropic as **Yes**.

---

## Option C: Ollama (local LLM)

Runs a model locally via [Ollama](https://ollama.com). Private, free, works offline.

1. Install Ollama:

   ```bash
   brew install ollama
   ```

2. Pull a model (llama3.2 works well for planning):

   ```bash
   ollama pull llama3.2
   ```

3. Start the Ollama server (or let it run as a background service):

   ```bash
   ollama serve
   ```

4. Set `provider = "ollama"` in `config/config.toml`:

   ```toml
   [llm]
   provider = "ollama"

   [llm.ollama]
   base_url = "http://localhost:11434"
   model    = "llama3.2"
   ```

5. Verify:

   ```bash
   uv run coach plan --dry-run
   ```

---

## Option D: llama.cpp server

Uses a locally-hosted model via the llama.cpp OpenAI-compatible server.

1. Start the llama.cpp server pointing at a `.gguf` file. For example:

   ```bash
   llama-server --model ~/models/mistral-7b-instruct.gguf --port 8080
   ```

2. Set `provider = "llamacpp"` in `config/config.toml`:

   ```toml
   [llm]
   provider = "llamacpp"

   [llm.llamacpp]
   server_url = "http://localhost:8080"
   ```

3. Verify with a dry-run:

   ```bash
   uv run coach plan --dry-run
   ```

---

## Option E: Apple Intelligence via Shortcuts

Uses Apple Intelligence through Shortcuts.app. Requires macOS 26+ and Apple Intelligence enabled.

1. Create Shortcuts named `EC-Plan`, `EC-Assess`, etc. with Apple Intelligence actions.

2. Set `provider = "apple"` in `config/config.toml`:

   ```toml
   [llm]
   provider = "apple"

   [llm.apple]
   shortcut_prefix = "EC-"
   ```

---

## Switching providers

Change the `provider` value in `[llm]`:

```toml
[llm]
provider = "anthropic"   # was "swift"
```

No other changes needed. All providers use the same prompt templates.

## Verification

```bash
uv run coach setup --non-interactive
```

The provider availability table shows which providers are configured and reachable on your system.

## Troubleshooting

**"Provider is not available"** — run `coach setup` to see the provider table. Common causes:
- `swift`: binary not built, or macOS version < 26
- `anthropic`: `ANTHROPIC_API_KEY` not set in the current shell
- `ollama`: Ollama server not running (`ollama serve`)
- `llamacpp`: llama.cpp server not running

**"Inference error"** — the provider responded but returned invalid JSON. This triggers an automatic retry. If it persists, try a different (larger) model.

## Related

- [Configuration reference](reference-config.md) — full `[llm]` section docs
- [Command reference](reference-commands.md)

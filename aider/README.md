# aider

[Aider](https://aider.chat) — `aider-chat`, the AI pair-programming CLI — as its makers ship it, headless in
a HarnessGateway session. Pinned at **0.86.2**, the latest stable release.

Aider edits files by asking the model for complete files (or search/replace blocks) and applying them itself,
and it can run the shell commands the model suggests. It does not browse or use tools of its own; it is a
pair-programmer, not a general agent.

## What it needs

| | |
|---|---|
| Image | `sh`, and `python3` with `pip` (the default image has both). Node.js is not used. |
| Interpreter | aider-chat 0.86.2 supports Python **>=3.10,<3.13**. If the image has one (`python3.12`, `python3.11`, `python3.10`, or a suitable `python3`), `install` uses it. Otherwise it installs `uv` with pip and fetches a CPython 3.12 from GitHub's copy of python-build-standalone into `$HG_HARNESS/tools/python`, then makes a venv. Nothing is installed outside `$HG_HARNESS/tools`. |
| Provider | One of the APIs below. The provider's base URL and key are handed to aider through litellm's environment. |
| Operator settings | **None.** The package declares no settings and no secrets. |
| Environment | Must carry this harness and allow the provider. A turn needs no other host (see **Hosts**). |

## The command one turn runs

```
aider --model <prefix>/<HG_MODEL> --weak-model ... --editor-model ... --edit-format diff
      --no-pretty --no-auto-commits --no-git --no-gitignore --no-check-update
      --analytics-disable --no-show-model-warnings --no-show-release-notes --disable-playwright
      --map-tokens 0 --chat-history-file <mind>/.aider/chat.history.md
      --input-history-file <mind>/.aider/input.history [--restore-chat-history]
      --message "<request brief>" [--reasoning-effort <effort>] <files...>
```

`--message` is aider's single-message, non-interactive mode: it sends the message, applies the edits, runs the
commands the model suggested, and exits. Confirmations are answered by end-of-input, which is their default
("yes"); `--yes-always` is deliberately *not* used because aider ignores it for shell commands, which it
requires a person to approve explicitly.

`<prefix>` is chosen from `HG_PROVIDER_API`: `anthropic` → `anthropic`, `openai-chat` → `openai`, `gemini` →
`gemini`. `--weak-model` and `--editor-model` get the same model, so summarization and commit-message calls do
not reach for a model the provider does not have. `--edit-format diff` is aider's search/replace format: it
keeps edits small and is also the format in which aider hears the model's suggested shell commands.

### Files put in aider's chat

Aider only edits files that are in its chat. Each turn the package passes:

- the files the request's prompt names, when they exist in `/work`;
- every text file in `/work` when there are at most 50 (the ordinary case), like `aider .`;
- when there are more, the named files and the files earlier turns touched (kept in `state`), plus as much of
  the rest as fits.

Caps: 200 files, text files up to 200 KB each and 2 MB in total, images (PNG/JPEG/GIF/WebP) up to 5 MB each and
8 MB in total. Hidden files, `.git`, `node_modules`, virtualenvs and other caches are skipped. Uploaded files
arrived in `inputs/` and are included and named in the brief.

## Request fields

| In the request | What the package does |
|---|---|
| `input` (string or messages) | `request.brief()` — handover line, instructions, the paths of files, then the prompt — goes to `--message`. |
| `instructions` | Prepended to the message: aider has no system-prompt option. |
| `input_file` / `input_image` | `request.brief()` places them under `inputs/` in the work folder and names them; aider sees the text files in its chat and images among the files it is given. |
| `model` (`HG_MODEL`) | The model half of `--model`; the package adds the provider prefix. |
| provider URL / key | litellm variables: `ANTHROPIC_API_BASE`/`ANTHROPIC_API_KEY`, `OPENAI_API_BASE`/`OPENAI_API_KEY`, or `GEMINI_API_BASE`/`GEMINI_API_KEY`. The key is the platform's placeholder. |
| `reasoning.effort` | `--reasoning-effort`. |
| `tools` of type `mcp` | **Not honoured.** aider has no MCP support; a turn with MCP tools logs one line saying so. |
| `text.format` | **Not honoured.** aider has no output-format option; a turn that sets it logs one line saying so. |
| `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata` | Ignored: aider exposes no option for them. |
| `previous_response_id`, `stream`, `background`, `store` | The platform's own; the package resumes from the mind and always prints events as they happen. |

Aider also offers URL reading: if a prompt contains a URL, aider offers to fetch it and (by end-of-input)
does. That host is then one the turn must be able to reach; it is not otherwise needed.

## What is printed

| aider does | Responses output |
|---|---|
| reasons (a reasoning tag or `reasoning_content`) | a `reasoning` item, streamed as its summary text |
| answers | a `message` item, streamed as `output_text` |
| creates or changes a file (`Applied edit to <path>`) | `apply_patch_call` (`create_file` / `update_file`) and its output. The diff is built from the SEARCH/REPLACE block aider was given; when no block can be read, the diff is empty. |
| runs a suggested command (`Running <cmd>`) | `shell_call` and `shell_call_output`. aider merges the command's stdout and stderr and does not report its exit code, so the output is emitted as `stdout` and the outcome is `exit_code: 0`. |
| prints its banner, token report, file-list echo, or bookkeeping | `hg.log`, or nothing |
| fails at the provider or exits without a response | `hg.failed` — `provider_error` with the provider's message, or `cli_exit` with the exit code |
| hits a token limit | `hg.incomplete` (`max_output_tokens`) |
| finishes | `hg.done`, with the token report's counts: `sent` as `input_tokens`, `received` as `output_tokens`, `cache hit` as `cached_tokens` |

A stopped turn prints no terminal line: the kit stops aider and everything it started and ends `run`.

## How the session continues

Aider has **no session id**. Its conversation is the markdown history it writes, so the package points
`--chat-history-file` at `$HOME/.aider/chat.history.md` in the mind and starts every turn with
`--restore-chat-history`. The mind is restored with the session, so the next turn reloads the previous
conversation. A stopped turn has already written the user's message to that file, so the next turn continues
from it.

The package keeps one small state value, `files`: the paths it has applied edits to, used to decide what to put
in aider's chat when the work folder is large. If the chat history cannot be read (a stopped turn can leave it
truncated) and aider exits non-zero without producing anything, `run` logs that, deletes the file, clears that
state, and runs the turn again as a new session.

`$HOME/.aider/caches` is listed in the manifest's `cache`, so it is not saved with the session. At the start of
each turn `run` copies litellm's bundled model-price table into it, which is what keeps aider from fetching that
table from `raw.githubusercontent.com`.

## Hosts

**Install:** `pypi.org`, `files.pythonhosted.org` (pip). When the image has no Python 3.10–3.12, uv also fetches
the interpreter from `github.com` / `release-assets.githubusercontent.com`. All of these are in the platform's
install registries, so **no `setup.egress` entry is required**.

**Turns:** none beyond the provider. Trials with this session's provider asked only for `api.deepseek.com`.
Because the model-price cache is primed from the installed litellm, `raw.githubusercontent.com` is not needed.
The one exception is a URL in the prompt: aider fetches it from the host it names, which the environment must
allow for that turn.

## What could not be tried here

- The **Gemini** path (`gemini/<model>`, `GEMINI_API_BASE`): this session's provider speaks Anthropic and
  OpenAI Chat only. The `openai-chat` path was tried against the same provider (base URL ending in `/v1`) and
  works.
- A provider that speaks only `openai-responses`: litellm's aider path is Chat Completions, so the manifest
  does not list that API.
- Image inputs end to end: the file selection includes them, but no image was sent in a trial.
- Model names other than this session's `deepseek-flash`; aider's edit format for a known model may differ from
  the `diff` format this package forces.
- A `closed` environment: the trials ran where the provider was reachable, and all install hosts are registry
  hosts.

## Using it

The package names its harness `aider`. Once an environment carries it, a request names it as
`<environment>/aider/<provider>/<model>`. There is nothing to configure on the harness.

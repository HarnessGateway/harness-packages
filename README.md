# harness-packages

The harness packages that ship with [HarnessGateway](https://github.com/HarnessGateway/harnessgateway):
one folder per agent CLI. Everything that is particular to a CLI is here, and nothing about any CLI is in
the platform.

| Package | CLI | Provider APIs it speaks | Notes |
|---|---|---|---|
| `aider` | Aider 0.86.2 | OpenAI Chat Completions, Anthropic Messages, Gemini | Prints text only: no tool calls are reported |
| `cheetahclaws` | CheetahClaws 3.5.90 | Anthropic Messages, OpenAI Chat Completions | |
| `claude-code` | Claude Code 2.1.323 | Anthropic Messages | |
| `cline` | Cline CLI 3.0.74 | Anthropic Messages, OpenAI Chat Completions | Run over ACP, which is what continues a session headless. Token counts are read from the CLI's own session record |
| `codex` | Codex CLI 0.167.2 | OpenAI Responses | |
| `dcode` | Deep Agents Code 0.2.10 | Anthropic Messages, OpenAI Chat Completions, OpenAI Responses, Gemini | Run over ACP. Token counts come from the CLI's session database |
| `docker-agent` | Docker Agent 1.161.0 | Anthropic Messages, OpenAI Responses, OpenAI Chat Completions, Gemini | |
| `dsh` | DeepSeek Harness 0.2.2-rc.4 | Anthropic Messages | Its makers publish pre-releases only, so a pre-release is what is pinned |
| `fast-agent` | fast-agent 0.10.57 | Anthropic Messages, OpenAI Chat Completions, OpenAI Responses, Gemini | Run over ACP |
| `goose` | goose 1.60.1 | Anthropic Messages, OpenAI Chat Completions, Gemini | |
| `grok` | Grok Build 1.0.89 | OpenAI Chat Completions, OpenAI Responses, Anthropic Messages | Its install downloads from `x.ai`, which an environment's `setup.egress` must name |
| `harness-package-builder` | Claude Code 2.1.323, set up to write new packages: with the guide to the package contract, the platform's own checker, and a trial that runs a package inside its sandbox | Anthropic Messages | The one package with a purpose of its own |
| `hermes` | Hermes Agent 0.23.1 | OpenAI Chat Completions | |
| `jcode` | J-Code 1.0.0 | Anthropic Messages, OpenAI Chat Completions, OpenAI Responses, Gemini | |
| `kilo` | Kilo Code CLI 7.8.27 | Anthropic Messages, OpenAI Chat Completions | |
| `kimi` | Kimi Code CLI 2.6.3 | Anthropic Messages, OpenAI Chat Completions, OpenAI Responses | Token counts come from the session log the CLI writes |
| `minimax` | MiniMax Code 0.7.7 | Anthropic Messages, OpenAI Responses, OpenAI Chat Completions, Gemini | |
| `nanobot` | nanobot 0.4.1 | OpenAI Chat Completions, OpenAI Responses, Anthropic Messages | The CLI has no output a program can read, so a small driver calls the Python SDK its makers document |
| `omp` | Oh My Pi 18.22.2 | Anthropic Messages, OpenAI Chat Completions, OpenAI Responses, Gemini | |
| `opencode` | OpenCode 1.19.6 | Anthropic Messages, OpenAI Chat Completions | |
| `openhands` | OpenHands Software Agent SDK 1.62.0 | OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, Gemini | Its makers ship an SDK and no command, so a small driver runs the SDK's own default agent |
| `opensquilla` | OpenSquilla 0.5.8 | OpenAI Chat Completions, Anthropic Messages, OpenAI Responses, Gemini | |
| `pi` | pi 1.5.2 | Anthropic Messages, OpenAI Responses, OpenAI Chat Completions | |
| `qwen-code` | Qwen Code 0.28.0 | Anthropic Messages, OpenAI Chat Completions, OpenAI Responses, Gemini | |
| `roder` | Roder 0.4.10 | OpenAI Chat Completions, OpenAI Responses | |
| `vibe` | Mistral Vibe 3.1.3 | Anthropic Messages, OpenAI Chat Completions, OpenAI Responses | Token counts come from a file the CLI writes |
| `zeroclaw` | ZeroClaw 0.9.0 | Anthropic Messages, OpenAI Responses, OpenAI Chat Completions | Run over ACP. Token counts come from a file the CLI writes |

Every package but `harness-package-builder` is its CLI unmodified, as its makers ship it: no added
instructions, skills or restrictions. To make an agent of your own, copy a package, give it a new name, put its
instructions and skills under `seeds/mind/`, and add it. Or have it written: ask `harness-package-builder` in
the chat for a package (a CLI's name, or what you need an agent for), install what it wrote from its session's
page, and tick it in an environment.

The `shell` package, the smallest one and the template, is in the platform's own repository
(`packages/shell`), with the guide to writing a package.

## How each was made and proven

`claude-code`, `codex`, `pi`, `hermes` and `harness-package-builder` were written by hand. Every other package
was written by `harness-package-builder` itself, on HarnessGateway 4.3.0 with `deepseek-flash`:

1. The builder was asked, in one sentence, for a package for the CLI. It read the CLI's documentation and help,
   pinned a version, wrote `harness.json`, `install`, `run` and a README, tried the package with its trial inside
   its own sandbox, recorded test cases, and checked the package with the platform's own checker.
2. The folder it wrote was taken from its session as a draft and installed as a harness, as the console does
   (`POST /v1/drafts`, then `POST /v1/drafts/<name>/install`).
3. The harness was put through five steps over the Responses API: a streamed turn that writes and runs a file;
   a continued turn that must remember it; a fork from the first turn; a turn that is interrupted; and a turn
   after the interrupt that must carry on. Every turn that completed had to report its token usage.
4. Where a step failed, the builder was told what failed, once, in the same session, and the steps were run
   again. `opencode` and `cline` needed that round.

A package is here only if all five steps passed. Not tried for the packages the builder wrote: the Gemini and
OpenAI Responses APIs where a package lists them (the proof used a provider that speaks Anthropic Messages and
Chat Completions; a package's own README says what its builder tried), and MCP servers sent with a request.

## The default environment

A package names no host: what an install and a turn may reach is the environment's to say. Each package's
README lists what an environment must allow for it beyond the provider and the package managers, and
`default-environment.json` holds what a new installation's `default` environment is given so that every package
here installs and runs in it. Today that is one host during setup, `x.ai`, for `grok`'s install.

## Using one

A new installation of the platform adds every package here, and its `default` environment carries them all.
A package added later, or one that was removed, is added from the catalog:

```
POST /v1/harnesses   {"catalog": "claude-code"}
```

or, in the console: Harnesses, Add from the catalog. A request may name a harness only in an environment that
carries it, so tick it in an environment too: in the console, in the environment's Harnesses checklist; over
the API, with the whole list the environment is to carry:

```
PATCH /v1/environments/default   {"harnesses": ["claude-code", "codex", "harness-package-builder", "pi"]}
```

The environment installs it on its image. Then name it in a request, every part of the model string named:
`environment/harness/provider/model`.

```python
client.responses.create(model="default/claude-code/deepseek/deepseek-flash", input="…")
```

## What each package does

Each has the same three parts:

- `harness.json` says which provider APIs the CLI speaks, where it keeps its state, and what of that is a cache.
- `install` installs the CLI at a pinned version under `$HG_HARNESS/tools`, by its makers' own method, and
  checks the version.
- `run` starts the CLI headless for one turn, resumes the CLI's own session when it has one, and translates
  each line the CLI prints into OpenAI Responses events.

## Checking a package

```
pip install git+https://github.com/HarnessGateway/harnessgateway
harnessgateway package check claude-code
pytest
```

Every package carries recordings of its CLI's real output under `tests/`. The check replays each through
`run` and holds the result to `expected.jsonl`, so a package's translation is tested without the CLI or a
model.

## Running the real CLIs without a provider

`tools/scripted_model.py` is a model that follows a script, behind the three provider APIs. Pointed at it,
a real CLI can be run end to end through a real platform, for nothing, with the same answer every time. The
recordings here were made that way. `tests/test_live.py` does the same against any platform:

```
HG_TEST_URL=http://localhost:8000 HG_TEST_KEY=hg_… pytest tests/test_live.py
```

It uses a provider named `scripted` unless `HG_TEST_PROVIDER` names another (a real one, with a real key
set on the platform), in which case the same tests run against a real model and assert less about its words.
`HG_TEST_MODEL` names that provider's model; without it, the first of the models the provider lists is used.
Each harness is added, the environment it runs in is made to carry it, and its install there is waited for.

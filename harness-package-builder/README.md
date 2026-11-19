# harness-package-builder

Claude Code, set up to write harness packages: for an agent CLI the platform does not ship, or for an
organization's own agent built on one. It is the one harness that is taught the platform's package contract,
and the console takes a package only from its sessions.

## Using it

Add it from the catalog, pick it in the chat, and ask:

- "Create a harness package for aider": the CLI as its makers ship it. It builds without questions.
- "I need an agent that reviews pull requests for our payments team and can never push": an agent for a
  purpose. It asks what it needs to know, proposes a plan, and builds on a go.

It writes the package into a folder of the session's work, tries it there, and says when it is ready. Then,
in the console: **Sessions**, that session, **New harness from workspace**. The folder opens as a draft where
every file can be read and changed, and **Install** makes it a harness. Over the API:
`POST /v1/drafts {"name", "session", "path"}`, then `POST /v1/drafts/<name>/install`. A request can name the
new harness once an environment carries it: tick it in the environment's Harnesses, or
`PATCH /v1/environments/<environment>` with the `harnesses` it is to carry.

In the default environment it reaches its provider and the common package registries, which is enough for
most CLIs. For one whose installer or documentation is elsewhere, give it an environment whose network is
`open` and that carries `harness-package-builder`, and name that environment in the model
(`<environment>/harness-package-builder/<provider>/<model>`). It says so itself when a host it needs is
refused.

## What is in it

| | |
|---|---|
| `install` | `claude-code`'s, then the package checker of the platform that runs it (`harnessgateway package check`), from the wheel the platform puts beside the kit, in a Python environment under `tools/platform`. Needs HarnessGateway 4.3 or later, and Python 3.12 or later in the image; the default image has it. |
| `run` | `claude-code`'s, byte for byte |
| `guide/BUILDER.md` | How the builder works: the two kinds of package, the steps, what must hold before it hands over |
| `guide/packages.md` | The package contract: the manifest, `install`, `run`, what a turn is given, sessions, secrets, tests |
| `guide/events.md` | What `run` prints, with the kit and as raw lines |
| `guide/request.md` | The Responses request, onto a CLI |
| `guide/tailoring.md` | An organization's agent: what to ask, and where each answer lives |
| `guide/trial.py` | Runs a package's `install` and real turns of it inside the builder's sandbox, as the platform would, lists every host asked for, and keeps turns as test cases |
| `seeds/mind/.claude/CLAUDE.md` | Tells Claude Code it is the builder, and to read the guide |

The guide is in the package, not in the session's mind: it is read-only during a turn, and a session always
reads the installed version. This repository's tests hold it to the platform: every kit function, variable,
host and manifest it shows must be one the platform has.

## What it cannot do

It tries the CLI against its own session's provider. A CLI that speaks only an API that provider does not
offer cannot be run there: the builder then writes the translation from the CLI's documented output and says
so. A declared secret has no value until the organization sets it on the installed harness, so calls that
need one are not tried.

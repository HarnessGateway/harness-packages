# The package contract

Everything the platform asks of a harness package, and everything it gives one. Contract version 1.

## The folder

```
<name>/
  harness.json     the manifest
  install          executable: puts the pinned CLI under $HG_HARNESS/tools. Runs once per environment image.
  run              executable: one turn
  seeds/mind/      optional: files copied into the session's mind on first use
  README.md        what it is, what it needs, what it maps
  tests/<case>/    recorded turns: request.json, recording, expected.jsonl
```

`install` and `run` are executables in any language: a first line naming the interpreter, or a Linux
binary. The default image has `sh`, `bash`, Python 3, Node.js, `git` and `curl`.

Limits: 64 MiB packed, 256 MiB unpacked, 5,000 files. Plain files and folders only: no links. Nothing under
`kit/` (the platform puts the kit there). `.git`, `__pycache__` and `.DS_Store` are left out when a folder
is packed.

## The manifest

```json
{
  "contract": 1,
  "name": "my-agent",
  "version": "1.4.2-1",
  "description": "One sentence: what it is.",
  "mind": ".mycli",
  "apis": ["anthropic", "openai-chat"],
  "install": { "egress": ["downloads.example.com"], "timeout_s": 900 },
  "run": { "egress": ["api.example.com"], "stop_grace_s": 10 },
  "settings": {
    "EFFORT": { "description": "Reasoning effort when the request names none", "default": "medium" }
  },
  "secrets": {
    "EXAMPLE_TOKEN": { "description": "Lets the agent call the Example API", "hosts": ["api.example.com"] }
  }
}
```

| Field | Required | Rule |
|---|---|---|
| `contract` | yes | `1` |
| `name` | yes | 1 to 63 characters of `a-z`, `0-9` and `-`, starting with a letter or a digit. It is what requests put in `model`. |
| `version` | yes | `<CLI version>-<package revision>`: `1.4.2-1`. The CLI's version is the one `install` pins. |
| `description` | no | Up to 4,000 characters |
| `mind` | no | The CLI's own folder under `$HOME` (`.mycli`). Another harness that takes over the session is pointed at it. Leave it out for a CLI that keeps no session. |
| `apis` | yes | The provider APIs the CLI speaks, the one it speaks best first: `anthropic` (Anthropic Messages), `openai-responses`, `openai-chat` (Chat Completions). `[]` for a harness that needs no model. |
| `install.egress` | no | Hosts the install needs beyond the registries below |
| `install.timeout_s` | no | 1 to 3600, default 900 |
| `run.egress` | no | Hosts every turn needs beyond its provider |
| `run.stop_grace_s` | no | 1 to 300, default 10: how long a stopped turn has to end by itself |
| `settings` | no | Up to 64 values the organization may set, not secret. Each: `description`, optional `default`, optional `required`. A turn gets each as a variable. |
| `secrets` | no | Up to 64 secret values the organization may set. Each: `description`, `hosts` (at least one), optional `required`. A turn gets each as a variable holding a placeholder. |

Unknown fields are refused. Setting and secret names are upper-case letters, digits and `_`, start with a
letter, and are not `HOME` or any name the platform sets (nothing beginning `HG_`).

A host entry is `host`, `*.suffix`, or either with `:port`. Without a port it covers 80 and 443. A bare `*` is
refused, and there is no entry that denies.

There is no field for a provider, a model, a time limit, an image, or MCP servers. A request names its
provider and model in full (`environment/harness/provider/model`); the turn's time limit and image belong to
the environment, which also chooses the harnesses it carries; an MCP server is the package's own business (see
`tailoring.md`).

## `install`

Runs once on the image of each environment that carries the harness (after the environment's setup script,
when it has one), in a container of that image, as user 10000, with the root read-only.

| | |
|---|---|
| Working directory | The package, laid out with the kit: `$HG_HARNESS`, writable for this run only |
| `HOME` | `/tmp/home` |
| Variables | `HG_CONTRACT`, `HG_HARNESS`, `HG_HARNESS_NAME`, `HG_HARNESS_VERSION`, and the proxy and certificate variables |
| Network | The registries below, plus `install.egress`. No provider, no secrets. |
| Time limit | `install.timeout_s` |

It must:

- install the CLI at a pinned version, by the CLI's own documented method, entirely under `$HG_HARNESS/tools`;
- check the version it got, and exit non-zero with a plain message when it is wrong or the image lacks
  something the CLI needs;
- write nowhere else, need no root, and name no CPU architecture (let the package manager pick the build).

Write `$HG_HARNESS`, never the path it stands for: that is what lets an install be tried anywhere.

**npm.** npm 12, which the platform's default image has, runs no package's install script unless told to;
earlier npm runs every one. An install that is the same on both installs with `--ignore-scripts`, then runs by
name the one script the CLI needs, if it has one (`npm view <package>@<version> scripts` shows it). Claude Code
needs its own, which puts the native binary in place: see `claude-code/install`.

An install can always reach the package managers, whatever its environment's network:

| Group | Hosts |
|---|---|
| Version control | `github.com`, `www.github.com`, `api.github.com`, `gist.github.com`, `codeload.github.com`, `npm.pkg.github.com`, `raw.githubusercontent.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`, `pkg-npm.githubusercontent.com`, `avatars.githubusercontent.com`, `camo.githubusercontent.com`, `gitlab.com`, `www.gitlab.com`, `registry.gitlab.com`, `bitbucket.org`, `www.bitbucket.org`, `api.bitbucket.org` |
| Container registries | `registry-1.docker.io`, `auth.docker.io`, `index.docker.io`, `hub.docker.com`, `www.docker.com`, `production.cloudflare.docker.com`, `production.cloudfront.docker.com`, `download.docker.com`, `gcr.io`, `*.gcr.io`, `ghcr.io`, `mcr.microsoft.com`, `*.data.mcr.microsoft.com`, `public.ecr.aws` |
| JavaScript | `registry.npmjs.org`, `www.npmjs.com`, `www.npmjs.org`, `npmjs.com`, `npmjs.org`, `yarnpkg.com`, `registry.yarnpkg.com`, `jsr.io`, `npm.jsr.io`, `nodejs.org`, `www.nodejs.org` |
| Python | `pypi.org`, `www.pypi.org`, `files.pythonhosted.org`, `pythonhosted.org`, `test.pypi.org`, `pypi.python.org`, `pypa.io`, `www.pypa.io`, `astral.sh`, `repo.anaconda.com`, `conda.anaconda.org`, `anaconda.org`, `www.anaconda.com`, `anaconda.com`, `continuum.io` |
| Ruby | `rubygems.org`, `www.rubygems.org`, `api.rubygems.org`, `index.rubygems.org`, `ruby-lang.org`, `www.ruby-lang.org`, `rubyforge.org`, `www.rubyforge.org`, `rubyonrails.org`, `www.rubyonrails.org`, `rvm.io`, `get.rvm.io` |
| Rust | `crates.io`, `www.crates.io`, `index.crates.io`, `static.crates.io`, `rustup.rs`, `static.rust-lang.org`, `www.rust-lang.org` |
| Go | `proxy.golang.org`, `sum.golang.org`, `index.golang.org`, `golang.org`, `www.golang.org`, `goproxy.io`, `pkg.go.dev` |
| The JVM | `maven.org`, `repo.maven.org`, `central.maven.org`, `repo1.maven.org`, `repo.maven.apache.org`, `maven.google.com`, `jcenter.bintray.com`, `gradle.org`, `www.gradle.org`, `services.gradle.org`, `plugins.gradle.org`, `plugins-artifacts.gradle.org`, `kotlinlang.org`, `www.kotlinlang.org`, `spring.io`, `repo.spring.io` |
| PHP, .NET, Dart, Elixir, Perl, CocoaPods, Haskell, Swift | `packagist.org`, `www.packagist.org`, `repo.packagist.org`, `nuget.org`, `www.nuget.org`, `api.nuget.org`, `pub.dev`, `api.pub.dev`, `hex.pm`, `www.hex.pm`, `cpan.org`, `www.cpan.org`, `metacpan.org`, `www.metacpan.org`, `api.metacpan.org`, `cocoapods.org`, `www.cocoapods.org`, `cdn.cocoapods.org`, `haskell.org`, `www.haskell.org`, `hackage.haskell.org`, `swift.org`, `www.swift.org` |
| Linux distributions | `deb.debian.org`, `security.debian.org`, `ubuntu.com`, `*.ubuntu.com`, `ppa.launchpad.net`, `launchpad.net`, `www.launchpad.net`, `dl-cdn.alpinelinux.org`, `*.nixos.org` |
| Development tools | `dl.k8s.io`, `pkgs.k8s.io`, `k8s.io`, `www.k8s.io`, `releases.hashicorp.com`, `apt.releases.hashicorp.com`, `rpm.releases.hashicorp.com`, `archive.releases.hashicorp.com`, `hashicorp.com`, `www.hashicorp.com`, `apache.org`, `www.apache.org`, `archive.apache.org`, `downloads.apache.org`, `eclipse.org`, `www.eclipse.org`, `download.eclipse.org`, `developer.apple.com`, `developer.android.com`, `pkg.stainless.com`, `binaries.prisma.sh` |
| Mirrors, fonts, schemas, the Model Context Protocol | `sourceforge.net`, `*.sourceforge.net`, `packagecloud.io`, `*.packagecloud.io`, `fonts.googleapis.com`, `fonts.gstatic.com`, `json-schema.org`, `www.json-schema.org`, `json.schemastore.org`, `www.schemastore.org`, `*.modelcontextprotocol.io` |

A turn reaches them too in an environment whose network is `limited` and allows package managers, which is
the default. Do not count on it for something every turn needs: declare that host in `run.egress`. In an
environment whose network is `closed` a turn reaches its provider and nothing else, not even what
`run.egress` declares.

**A CLI that cannot be installed this way.** Some CLIs keep their dependencies with the home they run under,
or update themselves in place; one read-only install shared by every session does not suit them. When the
CLI's makers publish an image, use it: `install` installs nothing, checks that the CLI is on the `PATH` at
the pinned version, and when it is not, says which image to make an environment from, that the environment
must carry the harness (`"harnesses": ["<harness>"]`), and how the model is then named
(`<environment>/<harness>/<provider>/<model>`). The README says the same. An image's own entry point is never run:
`run` starts the CLI itself.

## `run`

Called as `$HG_HARNESS/run`, with no arguments, in the work folder, once per turn. It reads the turn's
inputs, starts its CLI headless, prints events as the CLI works, prints one terminal line, and exits 0.
Standard error is free text: it is kept as the turn's log (its last 64 KiB) and never shown to the caller.

When a turn is stopped, `run` is sent a termination signal. It stops its CLI and exits; after
`run.stop_grace_s` it is killed. What was printed until then is the turn's output.

### What a turn is given

| Path | |
|---|---|
| `/turn/request.json` | The Responses request, exactly as the caller sent it |
| `/turn/handover.txt` | One line when another harness worked on this session last; otherwise empty |
| `/turn/history.json` | The turns this harness has not seen, oldest first: `[{"id", "harness", "status", "input", "output"}]`. `[]` when there are none. |
| `/turn/files/<file id>/<filename>` | Each uploaded file the request refers to by id |

| Variable | |
|---|---|
| `HOME`, `HG_MIND` | `/mind`: saved with the session |
| `HG_WORK` | `/work`: saved with the session. `run` starts here. |
| `HG_TURN` | `/turn` |
| `HG_HARNESS` | `/harness`: the installed package, read-only |
| `HG_STATE` | A folder in the mind for the package's own small state. The package creates it. |
| `HG_SESSION`, `HG_RESPONSE` | The session's id, and this turn's response id |
| `HG_HARNESS_NAME`, `HG_HARNESS_VERSION` | From the manifest |
| `HG_ENVIRONMENT` | The environment's name |
| `HG_CONTRACT` | `1` |
| `HG_PROVIDER` | The provider's name; empty for a harness that needs none |
| `HG_PROVIDER_API` | Which of the manifest's `apis` this turn speaks: the first one the provider offers |
| `HG_PROVIDER_URL` | The provider's base URL for that API. For `anthropic` it has no `/v1`; for the two OpenAI APIs it ends in `/v1`. |
| `HG_PROVIDER_KEY` | A placeholder. Hand it to the CLI as if it were the key. |
| `HG_MODEL` | The model to ask the provider for |
| `HG_HANDOVER` | The handover line, or empty |
| `HTTPS_PROXY`, `HTTP_PROXY`, `NODE_USE_ENV_PROXY`, `SSL_CERT_FILE`, `NODE_EXTRA_CA_CERTS` and their kin | The platform's proxy and its certificate authority. Leave them as they are, and pass them on to the CLI. |

Then the environment's own variables, each declared setting that has a value, and each declared secret as a
placeholder.

### What a turn prints

One JSON object per line on standard output, and nothing else there:

- **output events** of the OpenAI Responses stream, without `sequence_number`;
- `{"type": "hg.log", "text": "…"}`: a line for the turn's log;
- exactly one **terminal line**, last: `hg.done`, `hg.incomplete` or `hg.failed`.

The package never prints `response.created`, `response.completed`, `response.failed` or any other event
about the response as a whole: the platform writes those. `/harness/guide/events.md` has every line.

## The kit

`hgkit` is one Python file, standard library only, placed in every install at `$HG_HARNESS/kit/hgkit.py`.
It is optional: a `run` in another language prints the same lines itself.

```python
import os, sys
sys.path.insert(0, os.path.join(os.environ["HG_HARNESS"], "kit"))
import hgkit

request, emit, state = hgkit.Request(), hgkit.Emitter(), hgkit.State()
hgkit.seed_mind()                                    # seeds/mind into $HOME; what is there is left alone
cli = hgkit.Cli([...], env=..., stdin=request.brief())
for line in cli.lines():                             # the CLI's standard output, a line at a time
    ...                                              # emit.say, emit.think, emit.ran, emit.wrote, …
emit.done(usage)
```

| | |
|---|---|
| `hgkit.Request` | The turn's inputs. `/harness/guide/request.md` |
| `hgkit.State` | `state.get(name)`, `state.set(name, value)`, `state.clear(name)`: small named values under `$HG_STATE` |
| `hgkit.seed_mind` | Copies `seeds/mind` into the mind, never over a file that is there |
| `hgkit.Cli` | Runs the CLI; `lines()` gives its standard output; stops it when the turn is stopped (`stopped` is then true); `exit_code` when it has ended. Under a check it replays a recording in the CLI's place. |
| `hgkit.Emitter` | Prints lines the platform accepts. `/harness/guide/events.md` |

Give `hgkit.Cli` the CLI's whole environment (`dict(os.environ)` plus what the CLI needs). The CLI's standard
error goes to the turn's log by itself.

## How a session continues

The platform restores `/mind` and `/work` and tells the package nothing else. Whether this is a first turn, a
continued one, a rewind to an earlier response or a fork, the package finds out from what is in the mind.

1. **The CLI's own session.** Its store is under `$HOME`, so it comes back with the mind. Save the CLI's
   session id with `state.set("session", id)` **the moment the CLI reports it**, not at the end: a stopped
   turn must still be continued. Next turn, `state.get("session")` and resume it.
2. **When the CLI says the session is gone** (a stopped turn can leave it unusable): `state.clear`, say so
   with `emit.log`, and run the turn again as a new session. `/harness/run` shows the pattern.
3. **When another harness worked on the session last**, there is a handover line, naming that harness's
   folder in the mind. `request.brief()` puts it in front of the prompt, which is all most packages need.
   `request.history` holds those turns' requests and outputs for a package that wants to do more.

Never read another harness's files or formats yourself. The agent may; the package does not.

## Secrets

A secret's value never enters the sandbox. The variable holds a placeholder (`hgs_` and 32 hex characters,
new every turn). The proxy replaces it wherever it appears in a header or a URL's query, in requests to the
hosts the secret is bound to, and nowhere else. So put the variable's value exactly where the CLI would put
the real token, and bind the secret to that host in the manifest. A secret's hosts are reachable without
being in `run.egress`.

The provider's key works the same way: `HG_PROVIDER_KEY`, toward the provider's host.

Never write a key, a token or a placeholder into a file of the package, a recording included.

## Tests

One folder per case under `tests/`:

| File | |
|---|---|
| `request.json` | Required. The request body. |
| `recording` | The CLI's real standard output for that request |
| `handover.txt`, `history.json` | The turn's other inputs, when the case is about them |
| `expected.jsonl` | The lines `run` must print |

`/harness/tools/platform/bin/harnessgateway package check <folder>` is the platform's own checker. It
validates the package as an upload is validated, then runs `run` for each case with the recording in the
CLI's place (the kit's `hgkit.Cli` reads it, so neither the CLI nor a model is needed) and checks every line
as a live turn's lines are checked. With `--record` it writes `expected.jsonl`; without, it holds `run` to it.

Under a check the provider is a stand-in (`https://provider.invalid`), `HG_CHECK` is `1`, and the kit numbers
item ids by counting, so the same recording always gives the same lines. A `run` must not need the network,
the clock or a random number to translate a recording.

`python3 /harness/guide/trial.py turn <folder> "<prompt>" --case <name>` makes a case from a real turn.

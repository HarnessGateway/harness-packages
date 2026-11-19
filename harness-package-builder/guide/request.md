# The request, onto a CLI

`/turn/request.json` is the OpenAI Responses request exactly as the caller sent it. The platform has already
used the parts that are its own (`model`, `previous_response_id`, `stream`, `background`, `store`) and passes
everything else to the package untouched. Map what the CLI can honour; say in the README what it cannot.

With the kit, `request = hgkit.Request()`.

| In the request | With the kit | Where it usually goes |
|---|---|---|
| `input`: a string, or a list of messages | `request.prompt`: the user's text, joined | The CLI's prompt: standard input, or an argument. Prefer `request.brief()` (below). |
| `input_file` and `input_image` parts, by file id or inline | `request.place_files()` puts them in `inputs/` in the work folder and returns their paths. `request.files` lists the uploaded ones. | Name them in the prompt (`request.brief()` does), or pass them the CLI's own way |
| `instructions` | `request.instructions` | A system-prompt option of the CLI when it has one; otherwise in front of the prompt |
| the handover, when another harness worked on the session last | `request.handover` | In front of the prompt |
| the turns this harness has not seen | `request.history` | Usually nothing: the handover line points the agent at the other harness's folder |
| `model` | `request.model` (`HG_MODEL`: the model alone, already resolved) | The CLI's model option. Set every model name the CLI uses (a "small" or "background" model too) to it. |
| the provider | `request.provider.api`, `request.provider.url`, `request.provider.key`, `request.provider.name` | The CLI's base-URL and key options. The key is a placeholder: pass it as the key. |
| `reasoning.effort` | `request.effort` | The CLI's effort or thinking option |
| `tools` of type `mcp` | `request.mcp_servers`: each as sent (`server_label`, `server_url`, `headers`, `allowed_tools`, …) | The CLI's MCP configuration. Their hosts must be ones the turn can reach. |
| `text.format`, `max_output_tokens`, `temperature`, `top_p`, `max_tool_calls`, `truncation`, `user`, `metadata`, … | `request.body` (the whole request, a dict) | The CLI's own option when it has one |
| `previous_response_id` | nothing | The platform already chose the session: its mind and work are restored. Resume the CLI's own session from `hgkit.State`. |
| `stream`, `background`, `store` | nothing | The platform's. Always print events as they happen. |

A tool of any type but `mcp` never reaches a package: the platform refuses the request.

## The brief

`request.brief()` is what the agent is asked this turn, as one text, in this order: the handover line when
there is one; the request's `instructions`; where the request's files were put; the prompt. It places the
files. Hand it to the CLI as the prompt and the three things that are easy to forget are done.

When the CLI takes instructions some other way (a system-prompt option), pass `request.brief(instructions=False)`
as the prompt and `request.instructions` there. `/harness/run` does this.

## The provider

`HG_PROVIDER_API` is one of the `apis` the manifest lists: the first that the request's provider offers.
A CLI that speaks several must be configured for the one it is given.

| `HG_PROVIDER_API` | `HG_PROVIDER_URL` is | Typical CLI settings |
|---|---|---|
| `anthropic` | Anthropic's base URL form: no `/v1` | `ANTHROPIC_BASE_URL`, and the key as `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` |
| `openai-responses` | OpenAI's base URL form: ends in `/v1` | `OPENAI_BASE_URL`, `OPENAI_API_KEY`, or a provider entry in the CLI's config |
| `openai-chat` | The same | The same; many CLIs call this "OpenAI-compatible" |
| `gemini` | Google's base URL form: no `/v1beta` | `GOOGLE_GEMINI_BASE_URL` and `GEMINI_API_KEY`, or the CLI's own names for them |

The provider is rarely the CLI's maker. Turn off anything that assumes it is: sign-in, an update check, a
model list fetched from the maker, telemetry. A turn that hangs on a host it cannot reach is almost always
one of these; the trial's host list shows which.

A harness that needs no model has `"apis": []`, and these variables are empty. A request names it with
`none` for its provider and its model: `<environment>/<name>/none/none`.

## What a CLI cannot honour

Do not fail the turn over a field the CLI has no option for. Leave it, list it in the README under the
request fields, and when it changes what the caller gets (a `text.format` the CLI cannot enforce), say so
once with `emit.log`.

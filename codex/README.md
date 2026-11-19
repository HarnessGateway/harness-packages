# codex

The Codex CLI, unmodified, at version 0.167.2.

- **Provider API:** OpenAI Responses.
- **Installed with:** npm (`@openai/codex`), under `/harness/tools`. The image needs Node.js and Python 3.
- **Session:** kept by Codex under `~/.codex`; its thread id is kept in the package's state and resumed with
  `exec resume`.
- **Not saved:** `~/.codex/.tmp`, where Codex keeps a plugin catalogue it fetches from GitHub (about 100 MB).
  It is the manifest's `cache`: Codex fetches it again after a restore, where the environment allows GitHub.
- **Output:** each message, piece of reasoning, command and file change as it finishes. Codex does not print
  text word by word, so a message arrives whole.
- **Request fields honoured:** `instructions`, put in front of the prompt; input files and images (put under
  `inputs/` in the work folder, and named to the agent).

What this package handles for you: the provider is given to Codex on its command line as a custom model
provider; Codex's own inner sandbox and approval prompts are turned off, because it already runs in one.

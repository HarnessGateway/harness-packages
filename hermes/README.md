# hermes

Hermes Agent, unmodified, at version 0.23.1.

- **Provider API:** OpenAI Chat Completions.
- **Needs an environment built from Hermes's own image.** Hermes installs and updates itself, and keeps its
  dependencies with the home it runs under: started with a fresh home it downloads them again, several
  hundred megabytes into the session's mind. The one layout its makers ship in which a single read-only
  install serves many homes is their image. So this package installs nothing and checks the image instead:

  ```
  POST /v1/environments  {"name": "hermes", "image": "nousresearch/hermes-agent:v0.23.1"}
  model: "hermes:hermes/<provider>/<model>"
  ```

  A session can still move between Hermes and the other harnesses: the next request names another
  environment in its model, and the mind and the work go with it.
- **Session:** kept by Hermes in `~/.hermes`; its id is kept in the package's state and resumed with
  `--resume`.
- **Output:** text word by word; its `terminal` tool as shell calls; `write_file` and `patch` as file
  changes; every other tool as a custom tool call.
- **Request fields honoured:** `instructions`, put in front of the prompt; input files and images (put under
  `inputs/` in the work folder, and named to the agent).

What this package handles for you: Hermes will not resume a session with a different key on its command
line, so the key is given through the environment; its file tools are told they may write in the work
folder; its image's service stack is not started, only the agent.

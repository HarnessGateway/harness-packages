"""Each shipped harness, for real: its CLI installed and run in a sandbox by a running platform.

These tests need a platform, so they are skipped unless told where one is:

    HG_TEST_URL=http://localhost:8000 HG_TEST_KEY=hg_...(an admin key) pytest tests/test_live.py

By default they use a provider named `scripted`, pointing at tools/scripted_model.py, which they create when
it is missing (HG_TEST_SCRIPTED_URL says where the platform can reach it; default http://hg-stack-model:8000).
The scripted model's answers are known, so the tests assert them exactly.

With HG_TEST_PROVIDER naming a provider that already exists on the platform (a real one, with a real key),
the same turns run against a real model, and the tests assert only what must hold whatever the model says.
HG_TEST_MODEL names its model; without it, the first model the provider lists is used. HG_TEST_HARNESSES limits
which harnesses are tried (comma-separated).

Each harness runs in the `default` environment, which the tests make carry it.
"""

import asyncio
import base64
import io
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from harnessgateway import packaging
from openai import AsyncOpenAI

ROOT = Path(__file__).parents[1]
URL, KEY = os.environ.get("HG_TEST_URL"), os.environ.get("HG_TEST_KEY")
PROVIDER = os.environ.get("HG_TEST_PROVIDER", "scripted")
SCRIPTED = PROVIDER == "scripted"
MODEL = os.environ.get("HG_TEST_MODEL") or ("scripted" if SCRIPTED else None)
SCRIPTED_URL = os.environ.get("HG_TEST_SCRIPTED_URL", "http://hg-stack-model:8000")
HARNESSES = [name for name in os.environ.get("HG_TEST_HARNESSES", "claude-code,codex,pi,hermes").split(",") if name]
INSTALL_TIMEOUT_S = 1800
ENVIRONMENT = "default"
MIND_MAX = 100 * 1024 * 1024       # a harness's CLI and its dependencies are its install's, never a session's
DOT_FOLDER = {"claude-code": ".claude", "codex": ".codex", "pi": ".pi", "hermes": ".hermes"}

pytestmark = pytest.mark.skipif(not (URL and KEY), reason="set HG_TEST_URL and HG_TEST_KEY to run against a platform")


class Live:
    def __init__(self, admin: httpx.AsyncClient, client: AsyncOpenAI, model: str) -> None:
        self.admin, self.client, self.model = admin, client, model

    def model_of(self, harness: str) -> str:
        """The model string a request names a harness by: environment/harness/provider/model."""
        return f"{ENVIRONMENT}/{harness}/{PROVIDER}/{self.model}"

    async def add(self, name: str) -> None:
        """Add a package from this repository, have the environment carry it, and let its install there finish.

        A turn installs what is missing anyway; waiting here keeps a slow install out of the turn's time."""
        archive = packaging.pack(ROOT / name)
        added = await self.admin.post("/v1/harnesses", files={"package": (f"{name}.tar.gz", io.BytesIO(archive))})
        assert added.status_code == 200, added.text
        found = await self.admin.get(f"/v1/environments/{ENVIRONMENT}")
        assert found.status_code == 200, found.text
        carried = found.json()["harnesses"]
        if name not in carried:                  # an environment may run only the harnesses it carries
            changed = await self.admin.patch(f"/v1/environments/{ENVIRONMENT}", json={"harnesses": [*carried, name]})
            assert changed.status_code == 200, changed.text
        async with asyncio.timeout(INSTALL_TIMEOUT_S):
            while True:
                await asyncio.sleep(3)
                shown = (await self.admin.get(f"/v1/environments/{ENVIRONMENT}")).json()
                if shown["build"] and shown["build"]["status"] == "failed":
                    pytest.fail(f"{ENVIRONMENT}: its setup failed\n{shown['build']['log'][-3000:]}")
                status = next((install["status"] for install in shown["installs"] if install["harness"] == name), None)
                if status not in (None, "pending"):
                    break

    async def ask(self, harness: str, text: str, previous: Any = None) -> Any:
        response = await self.client.responses.create(
            model=self.model_of(harness), input=text, previous_response_id=previous.id if previous else None)
        if response.status != "completed":
            trace = (await self.admin.get(f"/v1/responses/{response.id}/trace")).json()
            pytest.fail(f"{harness}: {response.status}: {response.error}\n{trace['log'][-3000:]}")
        return response


@pytest.fixture
async def live() -> AsyncIterator[Live]:
    assert URL and KEY
    admin = httpx.AsyncClient(base_url=URL, headers={"Authorization": f"Bearer {KEY}"}, timeout=INSTALL_TIMEOUT_S)
    client = AsyncOpenAI(api_key=KEY, base_url=f"{URL}/v1", max_retries=0, timeout=INSTALL_TIMEOUT_S)
    if SCRIPTED and (await admin.get("/v1/providers/scripted")).status_code == 404:
        made = await admin.post("/v1/providers", json={
            "name": "scripted", "api_key": "scripted-model-key", "models": ["scripted"],
            "apis": {"anthropic": f"{SCRIPTED_URL}/anthropic", "openai-responses": f"{SCRIPTED_URL}/v1",
                     "openai-chat": f"{SCRIPTED_URL}/v1"}})
        assert made.status_code == 200, made.text
    model = MODEL
    if model is None:
        offered = (await admin.get(f"/v1/providers/{PROVIDER}")).json().get("models") or []
        assert offered, f"set HG_TEST_MODEL: provider {PROVIDER!r} lists no models"
        model = offered[0]
    yield Live(admin, client, model)
    await admin.aclose()
    await client.close()


@pytest.mark.parametrize("harness", HARNESSES)
async def test_the_harness_answers_runs_a_command_and_remembers_its_session(live: Live, harness: str) -> None:
    await live.add(harness)

    first = await live.ask(harness, "RUN: echo made by the agent > note.txt && cat note.txt" if SCRIPTED else
                           "Run this shell command and tell me what it printed: "
                           "echo made by the agent > note.txt && cat note.txt")
    kinds = [item.type for item in first.output]
    assert "shell_call" in kinds, kinds                        # the agent ran a command, and it is reported as one
    assert kinds[-1] == "message"
    assert "made by the agent" in first.output_text
    assert first.usage is not None
    assert first.usage.input_tokens > 0

    session = first.metadata["hg_session"]
    files = (await live.admin.get(f"/v1/sessions/{session}/files")).json()["data"]
    assert "work/note.txt" in [file["path"] for file in files]  # what it made is in the session's work
    assert any(file["path"].startswith("mind/") for file in files)        # and it kept a mind of its own
    mind = sum(file["bytes"] for file in files if file["path"].startswith("mind/"))
    assert mind < MIND_MAX, f"{harness} put {mind} bytes in the session's mind"   # not a copy of its own install

    second = await live.ask(harness, "What did I ask you first?", previous=first)
    if SCRIPTED:
        assert second.output_text.startswith("[turn 2] You said:")           # its own session was resumed
    else:
        assert "note.txt" in second.output_text or "echo" in second.output_text


@pytest.mark.parametrize("harness", HARNESSES)
async def test_a_file_sent_with_a_request_is_in_the_work_folder_and_the_agent_is_told(live: Live, harness: str) -> None:
    await live.add(harness)
    note = base64.b64encode(b"the note says hello").decode()
    response = await live.client.responses.create(model=live.model_of(harness), input=[{
        "role": "user", "content": [
            {"type": "input_text", "text": "RUN: cat inputs/note.txt" if SCRIPTED else
             "Run this shell command and tell me exactly what it printed: cat inputs/note.txt"},
            {"type": "input_file", "filename": "note.txt", "file_data": f"data:text/plain;base64,{note}"}]}])
    assert response.status == "completed", response.error
    assert "the note says hello" in response.output_text
    files = (await live.admin.get(f"/v1/sessions/{response.metadata['hg_session']}/files")).json()["data"]
    assert "work/inputs/note.txt" in [file["path"] for file in files]


@pytest.mark.parametrize(("first", "second"), [
    pair for pair in (("claude-code", "codex"), ("codex", "pi"), ("pi", "hermes"), ("hermes", "claude-code"))
    if pair[0] in HARNESSES and pair[1] in HARNESSES])
async def test_a_harness_takes_over_from_another_with_the_work_and_a_handover(
    live: Live, first: str, second: str
) -> None:
    await live.add(first)
    await live.add(second)
    one = await live.ask(first, "RUN: echo left by the first agent > handed.txt" if SCRIPTED else
                         "Run this shell command: echo left by the first agent > handed.txt")
    two = await live.ask(second, "RUN: cat handed.txt" if SCRIPTED else
                         "Run this shell command and tell me exactly what it printed: cat handed.txt", previous=one)
    assert "left by the first agent" in two.output_text        # the same work folder
    assert two.metadata["hg_session"] == one.metadata["hg_session"]

    trace = (await live.admin.get(f"/v1/responses/{two.id}/trace")).json()
    assert trace["handover"].startswith(f"Handover from {first}.")
    assert f"/mind/{DOT_FOLDER[first]}" in trace["handover"]
    if SCRIPTED:
        three = await live.ask(second, "Just say this back.", previous=two)
        assert three.output_text.startswith("[turn 2] You said:")           # the second harness's own session

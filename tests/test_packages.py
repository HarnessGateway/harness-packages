"""Every package is valid, and translates its CLI's recorded output into exactly the lines it is known to."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from harnessgateway import packaging
from harnessgateway.catalog import Catalog
from harnessgateway.domain.archive import read_archive
from harnessgateway.domain.environment import Environment
from harnessgateway.kit import hgkit

ROOT = Path(__file__).parents[1]
PACKAGES = sorted(path.parent.name for path in ROOT.glob("*/harness.json"))
BUILDER = "harness-package-builder"                           # the one package with a purpose: the rest are a CLI each
# Their recordings were made with the scripted model (tools/scripted_model.py), so what they hold is known exactly.
# Every other CLI's package was written by the builder, and its recordings are of turns with a real model.
SCRIPTED = ["claude-code", "codex", "hermes", "pi"]
RECORDED_WITH_A_REAL_MODEL = [name for name in PACKAGES if name not in (*SCRIPTED, BUILDER)]
# A recording holds what a CLI printed. These write their token counts to a file instead, so a replayed case has
# none: on a platform, every turn of theirs reports its counts.
COUNTS_ARE_NOT_PRINTED = {"dcode", "kimi", "vibe", "zeroclaw"}


def test_the_readme_lists_every_package_and_no_other() -> None:
    listed = re.findall(r"^\| `([a-z0-9-]+)` \|", (ROOT / "README.md").read_text(), re.MULTILINE)
    assert sorted(listed) == PACKAGES
    assert len(PACKAGES) == 27


def test_the_default_environment_the_catalog_asks_for_is_one_that_carries_every_package() -> None:
    fields = Catalog(ROOT).default_environment()
    environment = Environment.load({**fields, "name": "default", "harnesses": PACKAGES})
    assert environment.harnesses == tuple(PACKAGES)
    assert set(fields) == {"setup"}                           # only what an install needs: a turn's network is as new
    assert [entry.host for entry in environment.setup.egress] == ["x.ai"]     # grok's install downloads from it


@pytest.mark.parametrize("name", PACKAGES)
def test_the_package_is_valid_and_its_recordings_translate_as_expected(name: str) -> None:
    results = packaging.check(ROOT / name)
    package = read_archive(packaging.pack(ROOT / name))
    assert package.manifest.name == Path(name).name
    assert (ROOT / name / "README.md").exists()
    if name != BUILDER:                                       # its translation is claude-code's, tested there
        assert {result.name for result in results} >= {"hello", "command"}
        assert all((ROOT / name / "tests" / result.name / "expected.jsonl").exists() for result in results)


@pytest.mark.parametrize("name", SCRIPTED)
def test_a_command_the_agent_ran_is_a_shell_call_and_its_answer_is_a_message(name: str) -> None:
    command = next(result for result in packaging.check(ROOT / name) if result.name == "command")
    kinds = [item["type"] for item in command.output]
    assert kinds[:2] == ["shell_call", "shell_call_output"]
    assert kinds[-1] == "message"
    assert "echo made by the agent" in command.output[0]["action"]["commands"][0]
    assert "made by the agent" in command.output[1]["output"][0]["stdout"]
    assert command.output[1]["output"][0]["outcome"] == {"type": "exit", "exit_code": 0}
    assert command.terminal.kind == "done"
    assert command.terminal.usage is not None
    assert command.terminal.usage["input_tokens"] > 0


@pytest.mark.parametrize("name", RECORDED_WITH_A_REAL_MODEL)
def test_a_real_model_ran_a_command_and_answered_in_the_recorded_case(name: str) -> None:
    command = next(result for result in packaging.check(ROOT / name) if result.name == "command")
    kinds = [item["type"] for item in command.output]
    assert "shell_call" in kinds
    assert kinds.index("shell_call_output") > kinds.index("shell_call")
    assert "message" in kinds                       # said something: before or after, as that CLI does
    assert command.terminal.kind == "done"
    assert (command.terminal.usage is None) == (name in COUNTS_ARE_NOT_PRINTED)
    assert name in COUNTS_ARE_NOT_PRINTED or command.terminal.usage["input_tokens"] > 0


@pytest.mark.parametrize("name", PACKAGES)
def test_the_version_in_the_manifest_is_the_version_the_install_pins(name: str) -> None:
    manifest = json.loads((ROOT / name / "harness.json").read_text())
    pinned = re.search(r"^VERSION=(\S+)", (ROOT / name / "install").read_text(), re.MULTILINE)
    assert pinned is not None
    assert manifest["version"].rsplit("-", 1)[0] == pinned.group(1)


@pytest.mark.parametrize("name", PACKAGES)
def test_no_file_of_the_package_holds_a_key_or_a_placeholder(name: str) -> None:
    suspicious = re.compile(r"hgs_[0-9a-f]{32}|scripted-model-key|sk-[A-Za-z0-9]{20,}|hg_[A-Za-z0-9]{40}")
    for path in (ROOT / name).rglob("*"):
        if path.is_file():
            assert not suspicious.search(path.read_text(errors="replace")), path


_FAKE_HERMES = """#!/bin/sh
# Stands in for Hermes: notes how it was called and, for a chat, what the package had noted for the next turn.
echo "$* [unfinished: $(cat "$HG_STATE/unfinished" 2>/dev/null)]" >> "$HG_WORK/calls"
if [ "$1" = chat ]; then
  echo '{"type": "result", "session_id": "local-1", "exit_code": 0, "tokens": {"input": 1, "output": 1}}'
fi
"""


def _hermes_turn(base: Path) -> list[str]:
    """One turn of the hermes package on a stand-in Hermes, in `base`. How Hermes was called, call by call."""
    harness, state = base / "harness", base / "mind" / ".harnessgateway" / "hermes"
    if not harness.exists():
        shutil.copytree(ROOT / "hermes", harness)
        (harness / "kit").mkdir()
        shutil.copy(hgkit.__file__, harness / "kit" / "hgkit.py")
        fake = harness / "tools" / "bin" / "hermes"
        fake.parent.mkdir(parents=True)
        fake.write_text(_FAKE_HERMES)
        fake.chmod(0o755)
        for name in ("work", "turn"):
            (base / name).mkdir()
        state.mkdir(parents=True)
        (base / "turn" / "request.json").write_text('{"input": "hello"}')
        (base / "turn" / "history.json").write_text("[]")
        (base / "turn" / "handover.txt").write_text("")
    (base / "work" / "calls").unlink(missing_ok=True)
    done = subprocess.run(
        [str(harness / "run")], cwd=base / "work", capture_output=True, text=True, timeout=60, check=False,
        env={"PATH": os.environ["PATH"], "HOME": str(base / "mind"), "HG_TURN": str(base / "turn"),
             "HG_MIND": str(base / "mind"), "HG_WORK": str(base / "work"), "HG_HARNESS": str(harness),
             "HG_STATE": str(state), "HG_PROVIDER_API": "openai-chat", "HG_PROVIDER_URL": "https://provider.invalid",
             "HG_PROVIDER_KEY": "hgs_" + "0" * 32, "HG_MODEL": "a-model", "HG_HANDOVER": ""})
    assert done.returncode == 0, done.stderr
    assert '"hg.done"' in done.stdout.splitlines()[-1]
    return (base / "work" / "calls").read_text().splitlines()


def test_hermes_acknowledges_a_turn_that_was_stopped_before_it_resumes_the_session(tmp_path: Path) -> None:
    state = tmp_path / "mind" / ".harnessgateway" / "hermes"

    first = _hermes_turn(tmp_path)                             # a first turn: nothing to resume or acknowledge
    assert [call.split()[0] for call in first] == ["chat"]
    assert first[0].endswith("[unfinished: yes]")            # while Hermes works, the turn is marked unfinished
    assert not (state / "unfinished").exists()                 # and the mark is gone once it has ended
    assert (state / "session").read_text() == "local-1"

    second = _hermes_turn(tmp_path)                            # a turn after one that ended: resumed as it is
    assert [call.split()[0] for call in second] == ["chat"]
    assert "--resume local-1" in second[0]

    (state / "unfinished").write_text("yes")                   # a turn that was stopped leaves its mark behind
    third = _hermes_turn(tmp_path)
    assert third[0].startswith("sessions discard local-1 --yes")
    assert third[1].startswith("chat") and "--resume local-1" in third[1]

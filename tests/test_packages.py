"""Every package is valid, and translates its CLI's recorded output into exactly the lines it is known to."""

import json
import re
from pathlib import Path

import pytest
from harnessgateway import packaging
from harnessgateway.domain.archive import read_archive

ROOT = Path(__file__).parents[1]
PACKAGES = sorted(path.parent.name for path in ROOT.glob("*/harness.json"))


def test_the_packages_that_ship_are_all_here() -> None:
    assert PACKAGES == ["claude-code", "codex", "harness-package-builder", "hermes", "pi"]


@pytest.mark.parametrize("name", PACKAGES)
def test_the_package_is_valid_and_its_recordings_translate_as_expected(name: str) -> None:
    results = packaging.check(ROOT / name)
    package = read_archive(packaging.pack(ROOT / name))
    assert package.manifest.name == name
    assert (ROOT / name / "README.md").exists()
    if name != "harness-package-builder":                     # its translation is claude-code's, tested there
        assert {result.name for result in results} >= {"hello", "command"}
        assert all((ROOT / name / "tests" / result.name / "expected.jsonl").exists() for result in results)


@pytest.mark.parametrize("name", [name for name in PACKAGES if name != "harness-package-builder"])
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

"""The builder is held to the platform: what its guide says exists, and what its trial does is what a turn gets."""

import base64
import filecmp
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from harnessgateway import packaging
from harnessgateway.domain.archive import read_archive
from harnessgateway.domain.events import RunOutput
from harnessgateway.domain.hosts import PACKAGE_MANAGER_HOSTS
from harnessgateway.domain.package import Manifest
from harnessgateway.kit import hgkit

ROOT = Path(__file__).parents[1]
BUILDER = ROOT / "harness-package-builder"
GUIDE = BUILDER / "guide"
TRIAL = GUIDE / "trial.py"
DOCUMENTS = sorted(GUIDE.glob("*.md"))


def _trial_module():
    spec = importlib.util.spec_from_file_location("trial", TRIAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trial(tmp_path: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the trial as the builder does: in a sandbox whose /harness holds the kit, and whose work is a folder."""
    harness = tmp_path / "builder-harness"
    (harness / "kit").mkdir(parents=True, exist_ok=True)
    (harness / "kit" / "hgkit.py").write_bytes(Path(hgkit.__file__).read_bytes())
    work = tmp_path / "builder-work"
    work.mkdir(exist_ok=True)
    variables = {"PATH": os.environ["PATH"], "HG_HARNESS": str(harness), "HG_WORK": str(work), **(env or {})}
    return subprocess.run([sys.executable, str(TRIAL), *args], env=variables, cwd=work, capture_output=True,
                          text=True, timeout=120, check=False)


RUN = """#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.environ["HG_HARNESS"], "kit"))
import hgkit

request, emit = hgkit.Request(), hgkit.Emitter()
cli = hgkit.Cli(["sh", "-c", "exec 2>&1\\n" + request.prompt])          # the "agent" is the shell
for line in cli.lines():
    emit.say(line + "\\n")
if cli.exit_code == 0:
    emit.done()
elif not cli.stopped:
    emit.failed("command_failed", f"The command exited with code {cli.exit_code}.")
"""


@pytest.fixture
def package(tmp_path: Path) -> Path:
    """A package being written in the builder's work folder: the smallest one there can be."""
    folder = tmp_path / "builder-work" / "my-shell"
    folder.mkdir(parents=True)
    (folder / "harness.json").write_text(json.dumps({"contract": 1, "name": "my-shell", "version": "1-1", "apis": []}))
    (folder / "install").write_text("#!/bin/sh\necho nothing to install\n")
    (folder / "run").write_text(RUN)
    for name in ("install", "run"):
        (folder / name).chmod(0o755)
    return folder


# ── the trial ──────────────────────────────────────────────────────────────────────────────────────────────


def test_a_turn_is_refused_until_the_package_s_install_has_run(tmp_path: Path, package: Path) -> None:
    tried = _trial(tmp_path, "turn", str(package), "echo hi")
    assert tried.returncode != 0
    assert "trial.py install" in tried.stderr


def test_a_tried_turn_prints_what_the_platform_accepts_and_is_kept_as_a_case(tmp_path: Path, package: Path) -> None:
    assert _trial(tmp_path, "install", str(package)).returncode == 0
    tried = _trial(tmp_path, "turn", str(package), "echo made here > note.txt; cat note.txt", "--case", "hello")
    assert tried.returncode == 0, tried.stdout + tried.stderr
    assert "ended with: " in tried.stdout
    assert "hg.done" in tried.stdout

    stand_in = tmp_path / "builder-work" / ".trial" / "my-shell"
    reader = RunOutput(first_sequence_number=2)
    for line in (stand_in / "turn" / "printed.jsonl").read_text().splitlines():
        reader.read(line)
    assert reader.terminal is not None
    assert reader.terminal.kind == "done"
    assert (stand_in / "work" / "note.txt").read_text() == "made here\n"
    kept = json.loads((package / "tests" / "hello" / "request.json").read_text())
    assert kept["input"].startswith("echo made")
    assert kept["model"] == "default/my-shell/none/none"       # every part named; it calls no model
    assert (package / "tests" / "hello" / "recording").read_text() == "made here\n"
    assert [result.name for result in packaging.check(package)] == ["hello"]           # the case replays


def test_a_second_turn_continues_the_first_and_a_fresh_one_does_not(tmp_path: Path, package: Path) -> None:
    _trial(tmp_path, "install", str(package))
    _trial(tmp_path, "turn", str(package), "echo kept > note.txt")
    printed = tmp_path / "builder-work" / ".trial" / "my-shell" / "turn" / "printed.jsonl"
    assert _trial(tmp_path, "turn", str(package), "cat note.txt").returncode == 0
    assert "kept" in printed.read_text()
    fresh = _trial(tmp_path, "turn", str(package), "cat note.txt", "--fresh")
    assert fresh.returncode == 0                             # a turn that fails, and says so properly, is well formed
    assert "hg.failed" in fresh.stdout
    assert "kept" not in printed.read_text()


def test_a_tried_turn_is_given_the_variables_a_real_turn_is(tmp_path: Path, package: Path) -> None:
    _trial(tmp_path, "install", str(package))
    tried = _trial(tmp_path, "turn", str(package), "env", "--set", "LEVEL=high",
                   env={"HG_PROVIDER_URL": "https://provider.example", "ANTHROPIC_MODEL": "the-builder-s-own"})
    assert tried.returncode == 0, tried.stdout + tried.stderr
    recorded = (tmp_path / "builder-work" / ".trial" / "my-shell" / "turn" / "recording").read_text()
    given = dict(line.split("=", 1) for line in recorded.splitlines() if "=" in line)
    platform_s = packaging._variables(read_archive(packaging.pack(package)), tmp_path, "", None)
    assert set(platform_s) - {"HG_CHECK"} <= set(given)
    assert given["LEVEL"] == "high"
    assert given["HOME"] == given["HG_MIND"]
    assert given["HG_PROVIDER_URL"] == ""                    # this package needs no provider, so it is told of none
    assert "ANTHROPIC_MODEL" not in given                    # nothing of the builder's own CLI reaches it


def test_a_placeholder_in_what_run_prints_is_called_out(tmp_path: Path, package: Path) -> None:
    manifest = json.loads((package / "harness.json").read_text())
    (package / "harness.json").write_text(json.dumps({**manifest, "apis": ["anthropic"]}))
    _trial(tmp_path, "install", str(package))
    tried = _trial(tmp_path, "turn", str(package), "echo $HG_PROVIDER_KEY",
                   env={"HG_PROVIDER_KEY": "hgs_" + "0" * 32, "HG_PROVIDER_API": "anthropic"})
    assert tried.returncode == 1
    assert "placeholder" in tried.stdout


def test_a_stopped_turn_is_stopped_the_way_the_platform_stops_one(tmp_path: Path, package: Path) -> None:
    _trial(tmp_path, "install", str(package))
    tried = _trial(tmp_path, "turn", str(package), "echo started; sleep 60", "--stop-after", "1")
    assert "stopping it after 1 seconds" in tried.stderr
    assert "started" in (tmp_path / "builder-work" / ".trial" / "my-shell" / "turn" / "recording").read_text()


class _Proxy:
    """A stand-in for the sandbox's proxy: lets one host through, refuses the rest, and keeps what it was sent."""

    def __init__(self) -> None:
        self.heads: list[str] = []
        self._server = socket.socket()
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(8)
        self.port = self._server.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            client, _ = self._server.accept()
            head = client.recv(65536).decode()
            self.heads.append(head)
            if head.startswith("CONNECT allowed.example:443"):
                client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            elif head.startswith("POST http://model.example:8000/"):
                while not head.endswith("the body"):                     # it answers once it has the whole request
                    head += client.recv(65536).decode()
                client.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nanswer")
            else:
                client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 30\r\n\r\nthis host is not allowed here\n")
            client.close()


ASK = """
import os, socket
from urllib.parse import urlsplit
proxy = urlsplit(os.environ["HTTPS_PROXY"])
for host in ("allowed.example:443", "other.example:8443", "other.example:8443"):
    with socket.create_connection((proxy.hostname, proxy.port)) as s:
        s.sendall(f"CONNECT {host} HTTP/1.1\\r\\nHost: {host}\\r\\n\\r\\n".encode())
        s.recv(65536)
"""


def test_the_hosts_a_command_asks_for_are_listed_with_what_the_proxy_made_of_them(tmp_path: Path) -> None:
    proxy = _Proxy()
    observed = _trial(tmp_path, "observe", "--", sys.executable, "-c", ASK,
                      env={"HTTPS_PROXY": f"http://turn-1:its-token@127.0.0.1:{proxy.port}"})
    assert observed.returncode == 0, observed.stderr
    assert "allowed.example  1x  reached" in observed.stderr
    assert "other.example:8443  2x  REFUSED: this host is not allowed here" in observed.stderr
    login = base64.b64encode(b"turn-1:its-token").decode()
    assert all(f"Proxy-Authorization: Basic {login}" in head for head in proxy.heads)       # as the sandbox's own


# ── the guide ──────────────────────────────────────────────────────────────────────────────────────────────


def test_the_builder_runs_exactly_as_claude_code_does_and_installs_it_the_same_way() -> None:
    assert filecmp.cmp(ROOT / "claude-code" / "run", BUILDER / "run", shallow=False)
    assert (BUILDER / "install").read_text().startswith((ROOT / "claude-code" / "install").read_text())


def test_the_builder_is_told_where_its_guide_is() -> None:
    told = (BUILDER / "seeds/mind/.claude/CLAUDE.md").read_text()
    assert "/harness/guide/BUILDER.md" in told
    assert {path.name for path in DOCUMENTS} == {"BUILDER.md", "packages.md", "events.md", "request.md", "tailoring.md"}
    for path in DOCUMENTS:                                   # every guide file a document names is there
        for name in re.findall(r"/harness/guide/([\w.-]+)", path.read_text()):
            assert (GUIDE / name).exists(), f"{path.name} names {name}"


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda path: path.name)
def test_everything_the_guide_says_the_kit_has_the_kit_has(path: Path) -> None:
    text = path.read_text()
    for verb in re.findall(r"\bemit\.(\w+)", text):
        assert callable(getattr(hgkit.Emitter, verb, None)), f"{path.name}: emit.{verb}"
    for name in set(re.findall(r"\brequest\.(\w+)", text)) - {"json", "md"}:        # the files of those names
        assert hasattr(hgkit.Request, name) or name in ("body", "history", "handover", "model", "provider"), \
            f"{path.name}: request.{name}"
    for name in set(re.findall(r"\bhgkit\.(\w+)", text)) - {"py"}:
        assert name in hgkit.__all__, f"{path.name}: hgkit.{name}"
    for name in re.findall(r"\bstate\.(\w+)", text):
        assert callable(getattr(hgkit.State, name, None)), f"{path.name}: state.{name}"


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda path: path.name)
def test_every_manifest_the_guide_shows_is_one_the_platform_takes(path: Path) -> None:
    for block in re.findall(r"```json\n(.*?)```", path.read_text(), re.DOTALL):
        if '"contract"' in block:
            Manifest.load(json.loads(block))


def test_the_variables_the_guide_lists_are_the_ones_a_turn_is_given() -> None:
    listed = set(re.findall(r"`(HG_[A-Z_]+)`", (GUIDE / "packages.md").read_text()))
    given = set(packaging._variables(read_archive(packaging.pack(ROOT / "claude-code")), Path("/"), "", None))
    assert {name for name in given if name.startswith("HG_")} - {"HG_CHECK"} <= listed


def test_the_hosts_the_guide_says_an_install_always_reaches_are_the_platform_s() -> None:
    text = (GUIDE / "packages.md").read_text()
    section = text[text.index("always reach"):]
    listed = set(re.findall(r"`((?:\*\.)?[a-z0-9.-]+\.[a-z]+)`", section[:section.index("\n\nA turn reaches them")]))
    assert listed == {entry.host for entry in PACKAGE_MANAGER_HOSTS}


def test_every_raw_line_the_guide_shows_is_one_the_platform_accepts() -> None:
    blocks = re.findall(r"```jsonl\n(.*?)```", (GUIDE / "events.md").read_text(), re.DOTALL)
    assert len(blocks) == 2
    for block in blocks:
        reader = RunOutput(first_sequence_number=2)
        for line in block.splitlines():
            assert reader.read(line) is not None, line
        assert reader.terminal is not None


POST = """
import os, socket, time
from urllib.parse import urlsplit
proxy = urlsplit(os.environ["HTTP_PROXY"])
with socket.create_connection((proxy.hostname, proxy.port), timeout=10) as s:
    s.sendall(b"POST http://model.example:8000/v1/messages HTTP/1.1\\r\\nHost: model.example:8000\\r\\n"
              b"Content-Length: 8\\r\\n\\r\\n")
    time.sleep(0.3)
    s.sendall(b"the body")
    print(s.recv(65536).decode()[-6:])
"""


def test_a_request_over_plain_http_is_passed_on_whole_before_its_answer_is_waited_for(tmp_path: Path) -> None:
    proxy = _Proxy()
    observed = _trial(tmp_path, "observe", "--", sys.executable, "-c", POST,
                      env={"HTTPS_PROXY": f"http://turn-1:its-token@127.0.0.1:{proxy.port}"})
    assert observed.stdout.strip() == "answer", observed.stderr
    assert "model.example:8000  1x  answered 200" in observed.stderr

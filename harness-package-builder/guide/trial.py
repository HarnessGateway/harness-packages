#!/usr/bin/env python3
"""Try a harness package where it is being written, as the platform would run it.

    trial.py observe -- <command>          run a command and print every host it asked the network for
    trial.py install <folder>              lay the package out as an install finds it, and run its `install`
    trial.py turn <folder> "<prompt>"      run one turn of it, with this session's provider
        --case NAME         keep the request and the CLI's recorded output as <folder>/tests/NAME/
        --instructions T    the request's `instructions`
        --request FILE      a whole request body, in place of a prompt
        --handover TEXT     the line a turn is given when another harness worked on the session last
        --fresh             a new session: an empty mind and an empty work folder
        --stop-after S      stop the turn after S seconds, the way a cancelled turn is stopped
        --set NAME=VALUE    a setting, or any other variable the turn should be given (repeatable)

`install` and `turn` stand in for /harness, /mind, /work and /turn with folders under $HG_WORK/.trial/<name>/.
They stay between turns of this session, so a second `turn` continues the first: that is how resuming is tried.

Every command is run through a proxy on this machine that notes the hosts it asks for and passes each request
on to the sandbox's own proxy. What that proxy refuses is marked: those are the hosts the package must declare.

Standard library only.
"""

import argparse
import base64
import contextlib
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROXIES = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")
# What a sandbox is given whatever runs in it (the platform's variables that are not about one turn).
PASSED = ("PATH", "LANG", *PROXIES, "NO_PROXY", "no_proxy", "NODE_USE_ENV_PROXY", "SSL_CERT_FILE",
          "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "GIT_SSL_CAINFO", "NODE_EXTRA_CA_CERTS", "PIP_CERT")
# What a turn is told about its provider and its environment: this session's own.
PROVIDED = ("HG_ENVIRONMENT", "HG_PROVIDER", "HG_PROVIDER_API", "HG_PROVIDER_URL", "HG_PROVIDER_KEY", "HG_MODEL")
LEFT_OUT = {".git", "__pycache__", ".DS_Store"}
TERMINAL = ("hg.done", "hg.incomplete", "hg.failed")
KILL_AFTER_S = 5


# ── the hosts a command asks for ───────────────────────────────────────────────────────────────────────────


class Observer:
    """A proxy on this machine: notes each host asked for, and passes the request on."""

    def __init__(self, env):
        onward = env.get("HTTPS_PROXY") or env.get("https_proxy") or ""
        self._onward = urlsplit(onward) if onward else None
        self.seen = {}                                       # "host:port" -> [times asked, what came of it]
        self._lock = threading.Lock()
        self._server = socket.socket()
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(64)
        self.url = f"http://127.0.0.1:{self._server.getsockname()[1]}"
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            client, _ = self._server.accept()
            threading.Thread(target=self._serve, args=(client,), daemon=True).start()

    def _note(self, key, verdict):
        with self._lock:
            entry = self.seen.setdefault(key, [0, verdict])
            entry[0] += 1
            entry[1] = verdict

    def _serve(self, client):
        try:
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 65536:
                piece = client.recv(4096)
                if not piece:
                    return
                head += piece
            method, target = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[:2]
            if method == "CONNECT":
                host, _, port = target.rpartition(":")
                port = int(port) if port.isdigit() else 443
            else:
                url = urlsplit(target)
                host, port = url.hostname or "?", url.port or 80
            key = f"{host}:{port}"
            try:
                onward = self._pass_on(head, method, host, port)
            except OSError as e:
                self._note(key, f"could not be reached: {e}")
                return
            # What the caller sends next goes on at once: a request's body may come after its head.
            threading.Thread(target=_splice, args=(client, onward), daemon=True).start()
            answer = b"HTTP/1.1 200 Connection established\r\n\r\n" if self._onward is None and method == "CONNECT" \
                else onward.recv(65536)
            status = answer.split(b" ", 2)[1:2]
            if method != "CONNECT":
                self._note(key, "answered " + (status[0].decode("latin-1") if status else "nothing"))
            elif status == [b"200"]:
                self._note(key, "reached")
            else:
                said = answer.partition(b"\r\n\r\n")[2].decode("utf-8", "replace").strip().splitlines()
                self._note(key, "REFUSED: " + (said[0] if said else answer.split(b"\r\n", 1)[0].decode("latin-1")))
            client.sendall(answer)
            _splice(onward, client)
        except (OSError, ValueError):
            pass
        finally:
            client.close()

    def _pass_on(self, head, method, host, port):
        """Send the request on: to the sandbox's proxy, or straight to the host where there is no proxy."""
        where = (host, port) if self._onward is None else (self._onward.hostname, self._onward.port or 8080)
        onward = socket.create_connection(where, timeout=30)
        onward.settimeout(None)                              # a model may think for longer than any timeout
        if self._onward is None:
            if method != "CONNECT":
                onward.sendall(head)
            return onward
        if self._onward.username and b"\r\nproxy-authorization:" not in head.lower():
            login = f"{unquote(self._onward.username)}:{unquote(self._onward.password or '')}"
            line = b"Proxy-Authorization: Basic " + base64.b64encode(login.encode()) + b"\r\n"
            first, _, rest = head.partition(b"\r\n")
            head = first + b"\r\n" + line + rest
        onward.sendall(head)
        return onward

    def report(self, out=sys.stderr):
        print("\n--- hosts asked for ---", file=out)
        for key in sorted(self.seen):
            host, _, port = key.rpartition(":")
            times, verdict = self.seen[key]
            print(f"{host if port in ('80', '443') else key}  {times}x  {verdict}", file=out)
        if not self.seen:
            print("(none)", file=out)


def _splice(source, target):
    try:
        while data := source.recv(65536):
            target.sendall(data)
    except OSError:
        pass
    finally:
        for end in (source, target):
            with contextlib.suppress(OSError):
                end.shutdown(socket.SHUT_RDWR)


def observed(command, env, cwd=None, stdout=None, stop_after=None, grace=10):
    """Run a command through the observer. Its exit code; the hosts it asked for are printed afterwards."""
    observer = Observer(env)
    process = subprocess.Popen(command, env={**env, **dict.fromkeys(PROXIES, observer.url)}, cwd=cwd, stdout=stdout,
                               stdin=subprocess.DEVNULL)
    try:
        code = process.wait(timeout=stop_after)
    except subprocess.TimeoutExpired:
        print(f"stopping it after {stop_after:g} seconds", file=sys.stderr)
        process.send_signal(signal.SIGTERM)
        try:
            code = process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            print(f"it did not end within {grace} seconds of being stopped, and was killed", file=sys.stderr)
            process.kill()
            code = process.wait(timeout=KILL_AFTER_S)
    observer.report()
    return code


# ── a package, laid out as the platform lays it out ────────────────────────────────────────────────────────


class Trial:
    """A package folder, and the folders that stand in for /harness, /mind, /work and /turn."""

    def __init__(self, folder, env):
        self.folder = Path(folder).resolve()
        self.env = env
        try:
            self.manifest = json.loads((self.folder / "harness.json").read_text())
            self.name = self.manifest["name"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            sys.exit(f"{self.folder} is not a package: its harness.json could not be read ({e})")
        self.root = Path(env.get("HG_WORK", ".")).resolve() / ".trial" / self.name
        self.harness, self.mind, self.work, self.turn = (
            self.root / part for part in ("harness", "mind", "work", "turn"))

    def _files(self):
        for path in sorted(self.folder.rglob("*")):
            if path.is_file() and not LEFT_OUT & set(path.relative_to(self.folder).parts):
                yield path

    def _lay_out(self):
        """The package's files at the root of the stand-in /harness, and the kit beside them."""
        for path in self._files():
            target = self.harness / path.relative_to(self.folder)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        kit = Path(self.env["HG_HARNESS"]) / "kit"
        shutil.copytree(kit, self.harness / "kit", dirs_exist_ok=True)

    def _install_digest(self):
        return hashlib.sha256((self.folder / "install").read_bytes()).hexdigest()

    def _common(self):
        return {
            **{name: self.env[name] for name in PASSED if name in self.env},
            "HG_CONTRACT": self.env.get("HG_CONTRACT", "1"),
            "HG_HARNESS": str(self.harness),
            "HG_HARNESS_NAME": self.name,
            "HG_HARNESS_VERSION": str(self.manifest.get("version", "")),
        }

    def install(self):
        shutil.rmtree(self.harness, ignore_errors=True)
        self._lay_out()
        home = Path("/tmp/home")                             # where the platform puts an install's HOME
        home.mkdir(parents=True, exist_ok=True)
        limit = (self.manifest.get("install") or {}).get("timeout_s", 900)
        code = observed([str(self.harness / "install")], {**self._common(), "HOME": str(home)}, cwd=self.harness,
                        stop_after=limit, grace=KILL_AFTER_S)
        print(f"install exited with code {code}")
        if code == 0:
            (self.root / "installed").write_text(self._install_digest())
        return code

    def run_turn(self, args):
        marker = self.root / "installed"
        if not marker.exists() or marker.read_text() != self._install_digest():
            sys.exit(f"run `trial.py install {args.folder}` first: "
                     "this package's install has not been run as it is now")
        self._lay_out()
        if args.fresh:
            for folder in (self.mind, self.work):
                shutil.rmtree(folder, ignore_errors=True)
        shutil.rmtree(self.turn, ignore_errors=True)
        for folder in (self.mind, self.work, self.turn / "files"):
            folder.mkdir(parents=True, exist_ok=True)
        recording, printed = self.turn / "recording", self.turn / "printed.jsonl"
        needs_provider = bool(self.manifest.get("apis"))
        settings = {name: str(setting["default"]) for name, setting in (self.manifest.get("settings") or {}).items()
                    if isinstance(setting, dict) and setting.get("default") is not None}
        given = dict(pair.split("=", 1) for pair in args.set)
        env = {
            **self._common(),
            **{name: self.env.get(name, "") if needs_provider or name == "HG_ENVIRONMENT" else "" for name in PROVIDED},
            "HOME": str(self.mind), "HG_MIND": str(self.mind), "HG_WORK": str(self.work), "HG_TURN": str(self.turn),
            "HG_STATE": str(self.mind / ".harnessgateway" / self.name),
            "HG_SESSION": "sess_trial", "HG_RESPONSE": "resp_trial", "HG_HANDOVER": args.handover,
            **settings, **given, "HGKIT_RECORD": str(recording),
        }

        if args.request:
            request = json.loads(Path(args.request).read_text())
        else:
            request = {"model": self._model(env), "input": args.prompt}
            if args.instructions:
                request["instructions"] = args.instructions
        (self.turn / "request.json").write_text(json.dumps(request, indent=2) + "\n")
        (self.turn / "history.json").write_text("[]\n")
        (self.turn / "handover.txt").write_text(args.handover)
        api = env["HG_PROVIDER_API"]
        if needs_provider and api not in self.manifest["apis"]:
            print(f"note: this session's provider is reached by the {api or 'no'} API, and the package lists "
                  f"{self.manifest['apis']}. The turn is given the provider as this session has it.", file=sys.stderr)

        grace = (self.manifest.get("run") or {}).get("stop_grace_s", 10)
        with printed.open("w") as out:
            code = observed([str(self.harness / "run")], env, cwd=self.work, stdout=out,
                            stop_after=args.stop_after, grace=grace)
        print(f"run exited with code {code}")
        ok = self._read(printed, recording, env.get("HG_PROVIDER_KEY", "")) and code == 0
        if args.case:
            case = self.folder / "tests" / args.case
            case.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.turn / "request.json", case / "request.json")
            kept = ["request.json"]
            for name, text in (("handover.txt", args.handover), ("recording", recording.exists())):
                if text:
                    shutil.copy(self.turn / name, case / name)
                    kept.append(name)
            print(f"kept as {case}/ ({', '.join(kept)})")
        return 0 if ok else 1

    def _model(self, env):
        """The request's model string, environment/harness/provider/model, for what the turn is given: this
        session's environment, provider and model, or none/none for a package that calls no model."""
        provider, model = (env["HG_PROVIDER"], env["HG_MODEL"]) if self.manifest.get("apis") else ("", "")
        return "/".join((env["HG_ENVIRONMENT"] or "default", self.name, provider or "none", model or "none"))

    @staticmethod
    def _read(printed, recording, placeholder):
        """Say what `run` printed, and what is plainly wrong with it. The platform's checker says the rest."""
        ok, kinds, last = True, [], None
        lines = [line for line in printed.read_text().splitlines() if line]
        for number, text in enumerate(lines, 1):
            try:
                line = json.loads(text)
                last = line["type"]
            except (ValueError, KeyError, TypeError):
                print(f"line {number} is not a JSON object with a type: {text[:200]}")
                ok, last = False, None
                continue
            if last == "response.output_item.done":
                kinds.append(line.get("item", {}).get("type"))
        ended = [number for number, text in enumerate(lines, 1) if any(f'"{kind}"' in text for kind in TERMINAL)]
        print(f"printed {len(lines)} lines to {printed}; items: {', '.join(map(str, kinds)) or 'none'}")
        if last not in TERMINAL or len(ended) != 1:
            print("WRONG: exactly one terminal line (hg.done, hg.incomplete, hg.failed) must be printed, last")
            ok = False
        else:
            print(f"ended with: {lines[-1][:300]}")
        if recording.exists():
            print(f"the CLI's own output was recorded at {recording} ({len(recording.read_text().splitlines())} lines)")
        for path in (printed, recording):
            if placeholder and path.exists() and placeholder in path.read_text():
                print(f"WRONG: the provider key's placeholder is in {path}. A key, even a stand-in, is never printed.")
                ok = False
        return ok


def main(argv=None):
    parser = argparse.ArgumentParser(prog="trial.py", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe")
    observe.add_argument("argv", nargs=argparse.REMAINDER)
    install = commands.add_parser("install")
    install.add_argument("folder")
    turn = commands.add_parser("turn")
    turn.add_argument("folder")
    turn.add_argument("prompt", nargs="?", default="")
    turn.add_argument("--case")
    turn.add_argument("--instructions")
    turn.add_argument("--request")
    turn.add_argument("--handover", default="")
    turn.add_argument("--fresh", action="store_true")
    turn.add_argument("--stop-after", type=float)
    turn.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.command == "observe":
        command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        if not command:
            parser.error("observe -- <command>")
        return observed(command, env)
    if args.command == "turn" and not (args.prompt or args.request):
        parser.error("turn needs a prompt, or --request FILE")
    if args.command == "turn" and any("=" not in pair for pair in args.set):
        parser.error("--set takes NAME=VALUE")
    trial = Trial(args.folder, env)
    return trial.install() if args.command == "install" else trial.run_turn(args)


if __name__ == "__main__":
    sys.exit(main())

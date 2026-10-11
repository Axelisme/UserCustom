"""Shared test support: a hermetic process environment and external-runtime guards.

Tests run real git and the installed Pi runtime. Both must behave the same on
every machine, so `isolate_environment()` replaces the inherited user state
(HOME, global/system git config, identity, clock, stray GIT_* variables, Pi network access) in
this process's environment. Every subprocess a test starts -- git, python
scripts, the node harness and the git calls it makes -- inherits the result.
"""

from __future__ import annotations

import atexit
import importlib.machinery
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType

DEFAULT_PI_PACKAGE = "/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js"
PI_PACKAGE = Path(os.environ.get("PI_PACKAGE") or DEFAULT_PI_PACKAGE)
NODE = shutil.which("node") or "node"
# `git init --object-format` is the newest git feature the suite relies on.
MIN_GIT_VERSION = (2, 29)

FIXED_DATE = "2000-01-01T00:00:00Z"
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_AUTHOR_DATE": FIXED_DATE,
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_COMMITTER_DATE": FIXED_DATE,
}

_isolated_home: Path | None = None


def isolate_environment() -> None:
    """Point HOME and git configuration at an empty per-process sandbox. Idempotent."""
    global _isolated_home
    if _isolated_home is not None:
        return
    _isolated_home = Path(tempfile.mkdtemp(prefix="test-home-"))
    atexit.register(shutil.rmtree, _isolated_home, ignore_errors=True)
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        del os.environ[name]
    os.environ.update(
        {
            "HOME": str(_isolated_home),
            "XDG_CONFIG_HOME": str(_isolated_home / ".config"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            # The Pi runtime a harness loads must never reach the network from a test.
            "PI_OFFLINE": "1",
            **GIT_IDENTITY,
        }
    )


def _git_version() -> tuple[int, ...] | None:
    try:
        output = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"(\d+)\.(\d+)", output)
    return tuple(int(part) for part in match.groups()) if match else None


def require_git() -> None:
    """Module guard: isolate the environment, then skip when git is missing or too old."""
    isolate_environment()
    version = _git_version()
    if version is None or version < MIN_GIT_VERSION:
        wanted = ".".join(map(str, MIN_GIT_VERSION))
        raise unittest.SkipTest(f"git >= {wanted} is required (found {version})")


def require_pi() -> None:
    """Module guard for suites that load the installed Pi runtime through node."""
    if shutil.which("node") is None:
        raise unittest.SkipTest("node is not installed")
    if not PI_PACKAGE.is_file():
        raise unittest.SkipTest(f"Pi package not found at {PI_PACKAGE} (set PI_PACKAGE)")
    require_git()


def load_script(path: Path) -> ModuleType:
    """Import a shipped script by path, extension or not, so a test calls its main in-process."""
    name = f"script_{path.stem.replace('-', '_')}"
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    loader.exec_module(module)
    return module


def run_main(
    main: Callable[..., int], argv: tuple[str, ...] | list[str], **inputs: object
) -> subprocess.CompletedProcess[str]:
    """Call a script's main in-process; argv, stdout, stderr, and exit status match a process run."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = main(list(argv), **inputs)
        except SystemExit as exit:  # argparse rejects bad usage by exiting
            code = 0 if exit.code is None else exit.code
    return subprocess.CompletedProcess(list(argv), code, stdout.getvalue(), stderr.getvalue())

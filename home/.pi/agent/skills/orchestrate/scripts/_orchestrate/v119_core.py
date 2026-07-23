"""Public v119 Git-core command seams.

The Oracle slice deliberately publishes command names and argument boundaries before
Git behavior is implemented.  Implementers may replace these bodies while keeping the
Root-facing JSON interface and the contract-test surface stable.
"""

from __future__ import annotations

import argparse
from typing import Any

from .primitives import OrchestrateError


def _not_implemented(operation: str, args: argparse.Namespace) -> dict[str, Any]:
    raise OrchestrateError(
        f"{operation} behavior is not implemented; v119 Git core contract is red"
    )


def command_worktree_create(args: argparse.Namespace) -> dict[str, Any]:
    return _not_implemented("worktree create", args)


def command_worktree_status(args: argparse.Namespace) -> dict[str, Any]:
    return _not_implemented("worktree status", args)


def command_worktree_remove(args: argparse.Namespace) -> dict[str, Any]:
    return _not_implemented("worktree remove", args)


def command_contract_merge(args: argparse.Namespace) -> dict[str, Any]:
    return _not_implemented("contract merge", args)


def command_profile_report(args: argparse.Namespace) -> dict[str, Any]:
    return _not_implemented("profile report", args)

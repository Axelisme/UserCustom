#!/usr/bin/env python3
"""Stable entrypoint for the internal orchestrate package."""

from importlib import import_module

main = import_module("_orchestrate.cli").main


if __name__ == "__main__":
    raise SystemExit(main())

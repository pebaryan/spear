#!/usr/bin/env python3
"""Deterministic showcase runner for the minimal coding agent."""

import os
import sys
from typing import List

import agent


def _run(argv: List[str], expected_exit: int | None = None) -> int:
    print(f"\n$ agent.py {' '.join(argv)}")
    args = agent.parse_args(argv)
    rc = agent.execute_args(args)
    print(f"exit={rc}")
    if expected_exit is not None and rc != expected_exit:
        print(f"Unexpected exit code. expected={expected_exit} actual={rc}")
        return 1
    return 0


def main() -> int:
    # Deterministic mode for demos without external LLM dependency.
    os.environ.setdefault("SPEAR_DISABLE_LLM_FIX", "true")

    steps = [
        (["reset"], 0),
        (["tests"], 1),
        (["solve", "--reset-target"], 0),
        (["tests"], 0),
        (["explain", "last"], 0),
    ]

    for argv, expected in steps:
        rc = _run(argv, expected_exit=expected)
        if rc != 0:
            return rc

    print("\nShowcase demo completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

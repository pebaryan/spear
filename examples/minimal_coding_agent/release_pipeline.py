#!/usr/bin/env python3
"""Release pipeline helpers tied to minimal agent changelog versions."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CHANGELOG = BASE_DIR / "CHANGELOG.md"
DEFAULT_NOTES_OUT = BASE_DIR / "evals" / "release_notes_latest.md"
DEFAULT_META_OUT = BASE_DIR / "evals" / "release_metadata_latest.json"
VERSION_RE = re.compile(r"^##\s+\[(?P<version>[0-9]+\.[0-9]+\.[0-9]+)\]\s+-\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$")


def parse_changelog_sections(content: str) -> List[Dict[str, str]]:
    lines = content.splitlines()
    sections: List[Dict[str, str]] = []
    current: Dict[str, str] | None = None
    buffer: List[str] = []

    for line in lines:
        match = VERSION_RE.match(line.strip())
        if match:
            if current is not None:
                current["notes"] = "\n".join(buffer).strip() + "\n"
                sections.append(current)
            current = {
                "version": match.group("version"),
                "date": match.group("date"),
            }
            buffer = []
            continue
        if current is not None:
            buffer.append(line)

    if current is not None:
        current["notes"] = "\n".join(buffer).strip() + "\n"
        sections.append(current)
    return sections


def load_changelog_sections(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return parse_changelog_sections(text)


def normalize_tag_version(tag: str) -> str:
    value = str(tag or "").strip()
    if not value:
        return ""
    if value.startswith("refs/tags/"):
        value = value.split("/", 2)[-1]
    # Accept forms: v1.2.3, minimal-agent-v1.2.3, 1.2.3
    for pattern in (
        r"^minimal-agent-v([0-9]+\.[0-9]+\.[0-9]+)$",
        r"^v([0-9]+\.[0-9]+\.[0-9]+)$",
        r"^([0-9]+\.[0-9]+\.[0-9]+)$",
    ):
        match = re.match(pattern, value)
        if match:
            return match.group(1)
    return ""


def select_release_version(
    sections: List[Dict[str, str]], requested_version: str
) -> Tuple[str, Dict[str, str] | None]:
    if not sections:
        return "", None
    if requested_version:
        for section in sections:
            if section.get("version") == requested_version:
                return requested_version, section
        return requested_version, None
    latest = sections[0]
    return str(latest.get("version", "")), latest


def build_release_notes(version: str, section: Dict[str, str]) -> str:
    date_value = section.get("date", "")
    notes = section.get("notes", "").strip()
    lines = [
        f"# Minimal Coding Agent {version}",
        "",
        f"Release date: {date_value}",
        "",
    ]
    if notes:
        lines.append(notes)
    else:
        lines.append("(No release notes found in changelog section.)")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate release notes/metadata from minimal agent changelog"
    )
    parser.add_argument(
        "--changelog",
        default=str(DEFAULT_CHANGELOG),
        help="Path to changelog markdown",
    )
    parser.add_argument(
        "--version",
        default=os.getenv("RELEASE_VERSION", "").strip(),
        help="Release version (e.g., 0.4.0). Defaults to latest changelog section.",
    )
    parser.add_argument(
        "--tag",
        default=os.getenv("GITHUB_REF_NAME", "").strip(),
        help="Tag name to validate (e.g., minimal-agent-v0.4.0).",
    )
    parser.add_argument(
        "--notes-output",
        default=str(DEFAULT_NOTES_OUT),
        help="Output markdown file for release notes",
    )
    parser.add_argument(
        "--metadata-output",
        default=str(DEFAULT_META_OUT),
        help="Output JSON file for release metadata",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    changelog_path = Path(args.changelog)
    sections = load_changelog_sections(changelog_path)
    if not sections:
        print(f"No semver sections found in changelog: {changelog_path}")
        return 1

    version, section = select_release_version(sections, args.version)
    if not version or section is None:
        print(f"Version not found in changelog: {args.version or '(latest)'}")
        return 1

    tag_version = normalize_tag_version(args.tag)
    if args.tag and not tag_version:
        print(f"Unsupported tag format: {args.tag}")
        return 1
    if tag_version and tag_version != version:
        print(
            "Tag/changelog version mismatch:",
            f"tag={tag_version}",
            f"changelog={version}",
        )
        return 1

    notes = build_release_notes(version, section)
    notes_path = Path(args.notes_output)
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(notes, encoding="utf-8")

    metadata = {
        "created_at": datetime.now().isoformat(),
        "version": version,
        "date": section.get("date", ""),
        "tag": args.tag,
        "tag_version": tag_version,
        "changelog_path": str(changelog_path),
        "notes_output": str(notes_path),
    }
    metadata_path = Path(args.metadata_output)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(
        "Release metadata generated:",
        f"version={version}",
        f"notes={notes_path}",
        f"metadata={metadata_path}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

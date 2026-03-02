"""Tests for release pipeline changelog/tag integration."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import release_pipeline as rp  # noqa: E402


def test_parse_changelog_sections_extracts_versions():
    content = """# Changelog

## [0.5.0] - 2026-02-15
### Added
- X

## [0.4.0] - 2026-02-14
### Added
- Y
"""
    sections = rp.parse_changelog_sections(content)
    assert len(sections) == 2
    assert sections[0]["version"] == "0.5.0"
    assert sections[1]["version"] == "0.4.0"


def test_normalize_tag_version_supports_expected_formats():
    assert rp.normalize_tag_version("minimal-agent-v0.4.0") == "0.4.0"
    assert rp.normalize_tag_version("v0.4.0") == "0.4.0"
    assert rp.normalize_tag_version("0.4.0") == "0.4.0"
    assert rp.normalize_tag_version("bad-tag") == ""


def test_select_release_version_latest_when_unspecified():
    sections = [
        {"version": "0.5.0", "date": "2026-02-15", "notes": "n1"},
        {"version": "0.4.0", "date": "2026-02-14", "notes": "n2"},
    ]
    version, section = rp.select_release_version(sections, "")
    assert version == "0.5.0"
    assert section["date"] == "2026-02-15"


def test_build_release_notes_contains_version_and_notes():
    notes = rp.build_release_notes(
        "0.4.0",
        {"date": "2026-02-14", "notes": "### Added\n- Example"},
    )
    assert "# Minimal Coding Agent 0.4.0" in notes
    assert "Release date: 2026-02-14" in notes
    assert "- Example" in notes

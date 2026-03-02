"""Tests for repository context retrieval helpers."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers.context_retrieval import (  # noqa: E402
    build_project_context,
    format_context_for_prompt,
)


def test_build_project_context_ranks_relevant_file(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(
        "def running_average(total, count):\n"
        "    if count <= 0:\n"
        "        raise ValueError('count must be positive')\n"
        "    return total / count\n",
        encoding="utf-8",
    )
    (project / "helpers.py").write_text(
        "def slugify(name):\n"
        "    return name.lower().replace(' ', '-')\n",
        encoding="utf-8",
    )

    context = build_project_context(
        project,
        objective="Fix running_average ValueError behavior",
        error_message="AssertionError running_average failed",
    )

    selected = context["selected_files"]
    assert selected
    assert selected[0]["relative_path"] == "app.py"


def test_build_project_context_handles_syntax_error_file(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "broken.py").write_text("def nope(:\n", encoding="utf-8")
    (project / "ok.py").write_text("def work():\n    return 1\n", encoding="utf-8")

    context = build_project_context(
        project,
        objective="work function",
    )
    assert isinstance(context["selected_files"], list)


def test_format_context_for_prompt_can_exclude_primary_files(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (project / "service.py").write_text("def compute_tax():\n    return 0\n", encoding="utf-8")

    context = build_project_context(
        project,
        objective="compute tax service",
    )
    rendered = format_context_for_prompt(context, exclude_paths={"app.py"})

    assert "File: service.py" in rendered
    assert "File: app.py" not in rendered


def test_build_project_context_expands_dependency_neighbors(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(
        "import service\n\ndef run():\n    return service.compute()\n",
        encoding="utf-8",
    )
    (project / "service.py").write_text(
        "def compute():\n    return 42\n",
        encoding="utf-8",
    )
    (project / "unrelated.py").write_text(
        "def noop():\n    return None\n",
        encoding="utf-8",
    )

    context = build_project_context(
        project,
        objective="Fix run in app",
        max_files=2,
    )
    selected = context["selected_files"]
    rel_paths = [item["relative_path"] for item in selected]

    assert "app.py" in rel_paths
    assert "service.py" in rel_paths


def test_build_project_context_expands_symbol_neighbors_without_import(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(
        "def run():\n    return compute_total(10)\n",
        encoding="utf-8",
    )
    (project / "service.py").write_text(
        "def compute_total(value):\n    return value + 1\n",
        encoding="utf-8",
    )
    (project / "other.py").write_text(
        "def noop():\n    return 0\n",
        encoding="utf-8",
    )

    context = build_project_context(
        project,
        objective="Fix run behavior in app",
        max_files=2,
    )
    selected = context["selected_files"]
    rel_paths = [item["relative_path"] for item in selected]
    assert "app.py" in rel_paths
    assert "service.py" in rel_paths

    service_item = next(item for item in selected if item["relative_path"] == "service.py")
    assert service_item.get("related") is True
    assert "symbol" in str(service_item.get("related_by", ""))


def test_build_project_context_writes_index_cache(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    context = build_project_context(project, objective="run function")
    assert context["selected_files"]
    cache = project / ".spear_context_index.json"
    assert cache.exists()


def test_build_project_context_refreshes_cache_for_changed_file(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    app = project / "app.py"
    app.write_text("def alpha():\n    return 1\n", encoding="utf-8")

    first = build_project_context(project, objective="alpha behavior")
    assert first["selected_files"]

    app.write_text("def beta_value():\n    return 2\n", encoding="utf-8")
    second = build_project_context(project, objective="beta value behavior")
    selected = second["selected_files"]
    assert selected
    assert selected[0]["relative_path"] == "app.py"

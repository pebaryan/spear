"""Project context retrieval helpers for prompt grounding."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "when",
    "then",
    "should",
    "error",
    "failed",
    "tests",
    "test",
    "python",
    "code",
    "file",
}
INDEX_VERSION = 1
INDEX_FILE_NAME = ".spear_context_index.json"


def _tokenize(text: str) -> Set[str]:
    if not text:
        return set()
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text.lower())
    return {token for token in tokens if token not in STOPWORDS}


def _iter_python_files(project_dir: Path) -> Iterable[Path]:
    for path in project_dir.rglob("*.py"):
        normalized = path.as_posix()
        if "/.venv/" in normalized or "/__pycache__/" in normalized:
            continue
        yield path


def _index_cache_path(project_dir: Path) -> Path:
    return project_dir / INDEX_FILE_NAME


def _load_index_cache(project_dir: Path) -> Dict[str, object]:
    path = _index_cache_path(project_dir)
    if not path.exists():
        return {"version": INDEX_VERSION, "files": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": INDEX_VERSION, "files": {}}
    if not isinstance(payload, dict):
        return {"version": INDEX_VERSION, "files": {}}
    if int(payload.get("version", 0) or 0) != INDEX_VERSION:
        return {"version": INDEX_VERSION, "files": {}}
    files = payload.get("files", {})
    if not isinstance(files, dict):
        files = {}
    return {"version": INDEX_VERSION, "files": files}


def _save_index_cache(project_dir: Path, payload: Dict[str, object]) -> None:
    path = _index_cache_path(project_dir)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _file_signature(path: Path) -> str:
    stat = path.stat()
    return f"{int(stat.st_mtime_ns)}:{int(stat.st_size)}"


def _build_context_index(
    project_dir: Path, max_preview_chars: int = 4000
) -> Dict[str, Dict[str, object]]:
    cache = _load_index_cache(project_dir)
    cached_files = cache.get("files", {})
    if not isinstance(cached_files, dict):
        cached_files = {}

    indexed: Dict[str, Dict[str, object]] = {}
    changed = False

    for path in _iter_python_files(project_dir):
        rel = str(path.relative_to(project_dir))
        rel_key = _normalize_rel(Path(rel))
        signature = _file_signature(path)
        cached = cached_files.get(rel_key, {})
        if (
            isinstance(cached, dict)
            and str(cached.get("signature", "")) == signature
            and isinstance(cached.get("symbols"), dict)
        ):
            indexed[rel_key] = cached
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue

        symbols = _parse_symbols(source)
        source_preview = source[:max_preview_chars]
        source_tokens = sorted(_tokenize(source_preview))
        indexed[rel_key] = {
            "path": str(path),
            "relative_path": rel,
            "signature": signature,
            "symbols": symbols,
            "source_preview": source_preview,
            "source_tokens": source_tokens,
        }
        changed = True

    if set(indexed.keys()) != set(cached_files.keys()):
        changed = True

    if changed:
        _save_index_cache(
            project_dir,
            {"version": INDEX_VERSION, "files": indexed},
        )

    return indexed


def _parse_symbols(source: str) -> Dict[str, List[str]]:
    symbols = {
        "functions": [],
        "classes": [],
        "imports": [],
        "references": [],
        "import_from": [],
    }
    try:
        tree = ast.parse(source)
    except Exception:
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            symbols["functions"].append(node.name)
        elif isinstance(node, ast.ClassDef):
            symbols["classes"].append(node.name)
        elif isinstance(node, ast.Import):
            for item in node.names:
                symbols["imports"].append(item.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            symbols["imports"].append(module)
            import_item = {
                "module": module,
                "level": int(node.level or 0),
                "names": [item.name for item in node.names if getattr(item, "name", "")],
            }
            symbols["import_from"].append(import_item)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                symbols["references"].append(func.id)
            elif isinstance(func, ast.Attribute):
                symbols["references"].append(func.attr)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            symbols["references"].append(node.id)

    for key in symbols:
        seen = set()
        deduped = []
        if key == "import_from":
            deduped_meta = []
            for item in symbols[key]:
                if not isinstance(item, dict):
                    continue
                encoded = json.dumps(item, sort_keys=True)
                if encoded not in seen:
                    seen.add(encoded)
                    deduped_meta.append(item)
            symbols[key] = deduped_meta
        else:
            for item in symbols[key]:
                if item and item not in seen:
                    seen.add(item)
                    deduped.append(item)
            symbols[key] = deduped
    return symbols


def _candidate_paths_for_module(module_name: str) -> List[Path]:
    if not module_name:
        return []
    parts = [part for part in module_name.split(".") if part]
    if not parts:
        return []
    base = Path(*parts)
    return [base.with_suffix(".py"), base / "__init__.py"]


def _normalize_rel(path: Path) -> str:
    return path.as_posix().lower()


def _resolve_relative_base(importer_rel: Path, level: int) -> Path:
    # level=1 means same package, level=2 means parent package, etc.
    base = importer_rel.parent
    ascents = max(level - 1, 0)
    for _ in range(ascents):
        if str(base) in {"", "."}:
            return Path(".")
        base = base.parent
    return base


def _build_import_graph(all_items: Dict[str, Dict[str, object]]) -> Dict[str, Set[str]]:
    graph: Dict[str, Set[str]] = {rel: set() for rel in all_items}
    known = set(all_items.keys())

    def add_if_known(src_rel: str, candidate_rel: Path) -> None:
        candidate_key = _normalize_rel(candidate_rel)
        if candidate_key in known and candidate_key != src_rel:
            graph[src_rel].add(candidate_key)

    for rel_path, item in all_items.items():
        symbols = item.get("symbols", {})
        if not isinstance(symbols, dict):
            continue

        imports = symbols.get("imports", [])
        if isinstance(imports, list):
            for module_name in imports:
                module_text = str(module_name or "").strip()
                if not module_text:
                    continue
                for candidate in _candidate_paths_for_module(module_text):
                    add_if_known(rel_path, candidate)

        import_from = symbols.get("import_from", [])
        if not isinstance(import_from, list):
            continue
        importer_rel = Path(rel_path)
        for entry in import_from:
            if not isinstance(entry, dict):
                continue
            module_name = str(entry.get("module", "") or "").strip()
            level = int(entry.get("level", 0) or 0)
            names = entry.get("names", [])
            if not isinstance(names, list):
                names = []

            if level > 0:
                rel_base = _resolve_relative_base(importer_rel, level)
                if module_name:
                    for candidate in _candidate_paths_for_module(module_name):
                        add_if_known(rel_path, rel_base / candidate)
                else:
                    for name in names:
                        text = str(name or "").strip()
                        if not text:
                            continue
                        for candidate in _candidate_paths_for_module(text):
                            add_if_known(rel_path, rel_base / candidate)
            elif module_name:
                for candidate in _candidate_paths_for_module(module_name):
                    add_if_known(rel_path, candidate)

    return graph


def _build_symbol_reference_graph(
    all_items: Dict[str, Dict[str, object]],
) -> Dict[str, Set[str]]:
    graph: Dict[str, Set[str]] = {rel: set() for rel in all_items}
    definitions: Dict[str, Set[str]] = {}

    for rel, item in all_items.items():
        symbols = item.get("symbols", {})
        if not isinstance(symbols, dict):
            continue
        defined_names = []
        for key in ("functions", "classes"):
            values = symbols.get(key, [])
            if isinstance(values, list):
                defined_names.extend([str(value).strip() for value in values if value])
        for name in defined_names:
            key = name.lower()
            definitions.setdefault(key, set()).add(rel)

    for rel, item in all_items.items():
        symbols = item.get("symbols", {})
        if not isinstance(symbols, dict):
            continue
        refs = symbols.get("references", [])
        if not isinstance(refs, list):
            continue
        for ref in refs:
            ref_key = str(ref).strip().lower()
            if not ref_key:
                continue
            for target in definitions.get(ref_key, set()):
                if target != rel:
                    graph[rel].add(target)

    return graph


def _expand_with_related_files(
    seed_rel_paths: List[str],
    relation_graph: Dict[str, Set[str]],
    relation_types: Dict[tuple, str],
    max_files: int,
) -> tuple[List[str], Dict[str, str]]:
    if len(seed_rel_paths) >= max_files:
        return seed_rel_paths[:max_files], {}

    reverse_graph: Dict[str, Set[str]] = {key: set() for key in relation_graph}
    for src, targets in relation_graph.items():
        for dst in targets:
            reverse_graph.setdefault(dst, set()).add(src)

    ordered = list(seed_rel_paths)
    selected = set(ordered)
    reasons: Dict[str, str] = {}

    while len(ordered) < max_files:
        added = False
        for seed in list(ordered):
            neighbors = sorted(relation_graph.get(seed, set())) + sorted(
                reverse_graph.get(seed, set())
            )
            for neighbor in neighbors:
                if neighbor in selected:
                    continue
                selected.add(neighbor)
                ordered.append(neighbor)
                direct_type = relation_types.get((seed, neighbor), "")
                reverse_type = relation_types.get((neighbor, seed), "")
                merged = set()
                for kind in (direct_type, reverse_type):
                    if kind:
                        merged.update(kind.split("+"))
                reason = "+".join(sorted(item for item in merged if item))
                reasons[neighbor] = reason or "related"
                added = True
                break
            if len(ordered) >= max_files:
                break
        if not added:
            break

    return ordered[:max_files], reasons


def _score_file(
    path: Path,
    symbols: Dict[str, List[str]],
    source_tokens: Set[str],
    query_tokens: Set[str],
) -> float:
    score = 0.0

    path_tokens = _tokenize(path.stem.replace("-", "_"))
    symbol_tokens = _tokenize(
        " ".join(symbols["functions"] + symbols["classes"] + symbols["imports"])
    )
    score += len(query_tokens.intersection(path_tokens)) * 5.0
    score += len(query_tokens.intersection(symbol_tokens)) * 3.0
    score += len(query_tokens.intersection(source_tokens)) * 1.0

    # Prefer core app/test files when relevance is tied.
    lower_name = path.name.lower()
    if lower_name in {"app.py", "test_app.py"}:
        score += 0.5

    return score


def build_project_context(
    project_dir: Path,
    objective: str,
    error_message: str = "",
    test_output: str = "",
    max_files: int = 4,
    max_chars_per_file: int = 700,
) -> Dict[str, object]:
    """Build a ranked set of relevant files and snippets for prompting."""
    query = f"{objective}\n{error_message}\n{test_output}"
    query_tokens = _tokenize(query)

    indexed = _build_context_index(project_dir)
    all_items: Dict[str, Dict[str, object]] = {}
    for rel_key, entry in indexed.items():
        if not isinstance(entry, dict):
            continue
        path_text = str(entry.get("path", "")).strip()
        if not path_text:
            continue
        path = Path(path_text)
        symbols = entry.get("symbols", {})
        if not isinstance(symbols, dict):
            symbols = {"functions": [], "classes": [], "imports": [], "references": []}
        source_tokens_raw = entry.get("source_tokens", [])
        if isinstance(source_tokens_raw, list):
            source_tokens = {str(token) for token in source_tokens_raw}
        else:
            source_tokens = set()
        score = _score_file(path, symbols, source_tokens, query_tokens)
        snippet = str(entry.get("source_preview", ""))[:max_chars_per_file]
        all_items[rel_key] = {
            "path": str(path),
            "relative_path": str(entry.get("relative_path", "")) or str(path.name),
            "score": round(score, 2),
            "symbols": symbols,
            "snippet": snippet,
        }

    ranked = [item for item in all_items.values() if float(item.get("score", 0)) > 0]
    ranked.sort(key=lambda item: float(item["score"]), reverse=True)

    if ranked:
        seed = ranked[: max(1, max_files)]
    else:
        seed = sorted(
            all_items.values(), key=lambda item: str(item.get("relative_path", ""))
        )[: max(1, max_files)]

    seed_rel_keys = [
        _normalize_rel(Path(str(item.get("relative_path", "")))) for item in seed
    ]
    import_graph = _build_import_graph(all_items)
    symbol_graph = _build_symbol_reference_graph(all_items)

    relation_graph: Dict[str, Set[str]] = {key: set() for key in all_items}
    relation_types: Dict[tuple, str] = {}
    for src in relation_graph:
        import_neighbors = import_graph.get(src, set())
        symbol_neighbors = symbol_graph.get(src, set())
        merged = set(import_neighbors).union(symbol_neighbors)
        relation_graph[src].update(merged)
        for dst in merged:
            kinds = []
            if dst in import_neighbors:
                kinds.append("import")
            if dst in symbol_neighbors:
                kinds.append("symbol")
            relation_types[(src, dst)] = "+".join(kinds) if kinds else "related"

    selected_rel_keys, reasons = _expand_with_related_files(
        seed_rel_keys, relation_graph, relation_types, max_files
    )

    ranked_rel = set(seed_rel_keys)
    selected = []
    for rel_key in selected_rel_keys:
        item = all_items.get(rel_key)
        if not item:
            continue
        item_copy = dict(item)
        if rel_key not in ranked_rel:
            item_copy["related"] = True
            item_copy["related_by"] = reasons.get(rel_key, "related")
        selected.append(item_copy)

    return {
        "project_dir": str(project_dir),
        "query_tokens": sorted(query_tokens),
        "selected_files": selected,
    }


def format_context_for_prompt(
    context: Dict[str, object], exclude_paths: Set[str] | None = None
) -> str:
    """Convert context payload into compact text for an LLM prompt."""
    files = context.get("selected_files", [])
    if not isinstance(files, list) or not files:
        return ""

    excluded = {item.lower() for item in (exclude_paths or set())}
    sections: List[str] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        relative_path = str(item.get("relative_path", ""))
        normalized = relative_path.lower().replace("\\", "/")
        if normalized in excluded or any(
            normalized.endswith("/" + ex) or normalized == ex for ex in excluded
        ):
            continue

        symbols = item.get("symbols", {})
        functions = ", ".join(symbols.get("functions", [])[:8]) if symbols else ""
        classes = ", ".join(symbols.get("classes", [])[:8]) if symbols else ""
        snippet = str(item.get("snippet", ""))
        score = item.get("score", 0)

        section = (
            f"File: {relative_path}\n"
            f"Relevance score: {score}\n"
            f"Related by dependency: {'yes' if item.get('related') else 'no'}\n"
            f"Dependency source: {item.get('related_by', 'ranked')}\n"
            f"Functions: {functions or '(none)'}\n"
            f"Classes: {classes or '(none)'}\n"
            f"Snippet:\n```python\n{snippet}\n```"
        )
        sections.append(section)

    return "\n\n".join(sections)

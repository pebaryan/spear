"""Minimal automatic program repair engine for Python projects."""

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .common import PythonTestTool

try:
    from .context_retrieval import build_project_context
except Exception:
    build_project_context = None

try:
    from .template_kg import get_template_weights as get_template_weights_from_kg
except Exception:
    get_template_weights_from_kg = None

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_WEIGHTS_PATH = BASE_DIR / "template_weights.json"


@dataclass
class Mutation:
    file_path: Path
    start: int
    end: int
    replacement: str
    description: str
    line_no: int
    confidence: float = 0.5
    template: str = "generic"


@dataclass
class RepairResult:
    success: bool
    applied: bool
    steps: List[Dict[str, object]]
    final_exit_code: str
    final_output: str


def _line_offsets(source: str) -> List[int]:
    offsets = [0]
    cursor = 0
    for line in source.splitlines(True):
        cursor += len(line)
        offsets.append(cursor)
    return offsets


def _span_for_node(source: str, node: ast.AST) -> Optional[Tuple[int, int]]:
    if not hasattr(node, "lineno") or not hasattr(node, "col_offset"):
        return None
    end_lineno = getattr(node, "end_lineno", None)
    end_col = getattr(node, "end_col_offset", None)
    if end_lineno is None or end_col is None:
        return None

    offsets = _line_offsets(source)
    if node.lineno - 1 >= len(offsets) or end_lineno - 1 >= len(offsets):
        return None

    start = offsets[node.lineno - 1] + int(node.col_offset)
    end = offsets[end_lineno - 1] + int(end_col)
    if start >= end:
        return None
    return (start, end)


def _replace_span(source: str, span: Tuple[int, int], replacement: str) -> str:
    start, end = span
    return source[:start] + replacement + source[end:]


def _line_number_for_offset(source: str, offset: int) -> int:
    return source.count("\n", 0, max(0, offset)) + 1


def _load_template_weights_json(path: Path) -> Dict[str, float]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if isinstance(payload, dict) and isinstance(payload.get("weights"), dict):
        raw = payload.get("weights", {})
    elif isinstance(payload, dict):
        raw = payload
    else:
        return {}

    weights: Dict[str, float] = {}
    for key, value in raw.items():
        try:
            numeric = float(value)
        except Exception:
            continue
        if numeric <= 0:
            continue
        weights[str(key)] = numeric
    return weights


def load_template_weights(path: Path = TEMPLATE_WEIGHTS_PATH) -> Dict[str, float]:
    json_weights = _load_template_weights_json(path)
    if get_template_weights_from_kg is None:
        return json_weights

    try:
        kg_weights = get_template_weights_from_kg()
    except Exception:
        return json_weights

    if not kg_weights:
        return json_weights

    merged = dict(json_weights)
    merged.update(kg_weights)
    return merged


def _weighted_confidence(
    template: str, confidence: float, template_weights: Optional[Dict[str, float]]
) -> float:
    if not template_weights:
        return max(0.05, min(1.0, float(confidence)))
    weight = float(template_weights.get(template, 1.0))
    adjusted = float(confidence) * weight
    return max(0.05, min(1.0, adjusted))


def _is_test_path(path: Path) -> bool:
    lower = path.as_posix().lower()
    name = path.name.lower()
    if "/tests/" in lower:
        return True
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return False


def discover_source_files(project_dir: Path) -> List[Path]:
    files = []
    for path in sorted(project_dir.rglob("*.py")):
        if _is_test_path(path):
            continue
        files.append(path)
    return files


def _normalize_rel(path: Path) -> str:
    return path.as_posix().lower()


def _file_priority_from_context(
    project_dir: Path, source_files: List[Path], current_output: str
) -> Dict[str, int]:
    priorities: Dict[str, int] = {}
    if not source_files:
        return priorities
    if build_project_context is None:
        return priorities

    try:
        context = build_project_context(
            project_dir=project_dir,
            objective="deterministic program repair",
            error_message=current_output[:1200],
            test_output=current_output[:1200],
            max_files=min(max(3, len(source_files)), 8),
        )
        selected = context.get("selected_files", [])
        if isinstance(selected, list):
            score = len(selected) + 1
            for item in selected:
                if not isinstance(item, dict):
                    continue
                rel = str(item.get("relative_path", "")).strip()
                if not rel:
                    continue
                priorities[_normalize_rel(Path(rel))] = score
                score -= 1
    except Exception:
        pass

    return priorities


def _op_swap(op: ast.AST) -> Optional[str]:
    mapping = {
        ast.Lt: "<=",
        ast.Gt: ">=",
        ast.LtE: "<",
        ast.GtE: ">",
        ast.Eq: "!=",
        ast.NotEq: "==",
    }
    for cls, symbol in mapping.items():
        if isinstance(op, cls):
            return symbol
    return None


def _const_number(node: ast.AST) -> Optional[float]:
    if not isinstance(node, ast.Constant):
        return None
    if isinstance(node.value, bool):
        return None
    if isinstance(node.value, (int, float)):
        return float(node.value)
    return None


def _binary_swap_symbol(op: ast.AST) -> Optional[str]:
    mapping = {
        ast.Add: "-",
        ast.Sub: "+",
        ast.Mult: "/",
        ast.Div: "*",
    }
    for cls, symbol in mapping.items():
        if isinstance(op, cls):
            return symbol
    return None


def _iter_mutations_for_source(
    file_path: Path, source: str, template_weights: Optional[Dict[str, float]] = None
) -> Iterable[Mutation]:
    try:
        tree = ast.parse(source)
    except Exception:
        return []

    seen = set()
    mutations = []
    parent_map: Dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent

    def add_mutation(
        span: Tuple[int, int],
        replacement: str,
        description: str,
        confidence: float = 0.5,
        template: str = "generic",
    ) -> None:
        key = (span[0], span[1], replacement)
        if key in seen:
            return
        seen.add(key)
        mutations.append(
            Mutation(
                file_path=file_path,
                start=span[0],
                end=span[1],
                replacement=replacement,
                description=description,
                line_no=_line_number_for_offset(source, span[0]),
                confidence=_weighted_confidence(
                    template, confidence, template_weights
                ),
                template=template,
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
            swapped = _op_swap(node.ops[0])
            span = _span_for_node(source, node)
            left = ast.get_source_segment(source, node.left)
            right = ast.get_source_segment(source, node.comparators[0])
            if swapped and span and left and right:
                parent = parent_map.get(node)
                right_num = _const_number(node.comparators[0])
                left_lower = left.lower()
                boundary_hint = any(
                    token in left_lower
                    for token in ("count", "index", "idx", "len", "size")
                )
                is_guard = isinstance(parent, ast.If) and parent.test is node
                confidence = 0.52
                template = "operator_swap"
                if (
                    is_guard
                    and right_num == 0.0
                    and isinstance(node.ops[0], (ast.Lt, ast.Gt, ast.LtE, ast.GtE))
                ):
                    confidence = 0.84 if boundary_hint else 0.76
                    template = "boundary_guard"
                add_mutation(
                    span,
                    f"{left} {swapped} {right}",
                    f"Swap comparison operator to {swapped}",
                    confidence=confidence,
                    template=template,
                )

        if isinstance(node, ast.BinOp):
            span = _span_for_node(source, node)
            if not span:
                continue

            left_src = ast.get_source_segment(source, node.left)
            right_src = ast.get_source_segment(source, node.right)
            if not left_src or not right_src:
                continue

            swap_symbol = _binary_swap_symbol(node.op)
            if swap_symbol:
                add_mutation(
                    span,
                    f"{left_src} {swap_symbol} {right_src}",
                    f"Swap binary operator to {swap_symbol}",
                    confidence=0.42,
                    template="arithmetic_swap",
                )

            left_num = _const_number(node.left)
            right_num = _const_number(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if right_num == 1.0:
                    add_mutation(
                        span,
                        left_src,
                        "Remove +/- 1 from expression (right side)",
                        confidence=0.9,
                        template="off_by_one_fix",
                    )
                if left_num == 1.0:
                    add_mutation(
                        span,
                        right_src,
                        "Remove +/- 1 from expression (left side)",
                        confidence=0.9,
                        template="off_by_one_fix",
                    )

    return sorted(mutations, key=lambda m: (m.file_path.as_posix(), m.start, m.description))


def _extract_suspect_locations(output: str, project_dir: Path) -> List[Tuple[str, int]]:
    suspects: List[Tuple[str, int]] = []
    seen = set()
    if not output:
        return suspects

    patterns = [
        r"([A-Za-z]:[\\/][^:\n]+\.py):(\d+)",  # Windows absolute path
        r"([^\s:][^:\n]*\.py):(\d+)",  # Relative path
    ]
    for pattern in patterns:
        for path_text, line_text in re.findall(pattern, output):
            try:
                line_no = int(line_text)
            except Exception:
                continue
            path_obj = Path(path_text)
            if not path_obj.is_absolute():
                path_obj = (project_dir / path_obj).resolve()
            else:
                path_obj = path_obj.resolve()

            try:
                rel = str(path_obj.relative_to(project_dir))
            except Exception:
                rel = path_obj.name
            key = (rel.lower().replace("\\", "/"), line_no)
            if key in seen:
                continue
            seen.add(key)
            suspects.append((rel, line_no))

    return suspects


def _mutation_priority(mutation: Mutation, suspects: List[Tuple[str, int]]) -> int:
    if not suspects:
        return 0

    mutation_rel = mutation.file_path.name.lower().replace("\\", "/")
    best = 0
    for suspect_rel, suspect_line in suspects:
        normalized = suspect_rel.lower().replace("\\", "/")
        file_match = (
            mutation_rel == normalized
            or mutation.file_path.name.lower() == Path(normalized).name.lower()
            or normalized.endswith("/" + mutation_rel)
        )
        if not file_match:
            continue
        score = 100
        distance = abs(int(mutation.line_no) - int(suspect_line))
        score += max(0, 40 - distance)
        if score > best:
            best = score
    return best


def _extract_test_cost(exit_code: str, output: str) -> Tuple[int, int, int]:
    if str(exit_code) == "0":
        passed = _extract_first_int(r"(\d+)\s+passed", output)
        return (0, 0, passed)

    failed = _extract_first_int(r"(\d+)\s+failed", output)
    errors = _extract_first_int(r"(\d+)\s+error", output)
    passed = _extract_first_int(r"(\d+)\s+passed", output)
    unknown_penalty = 50 if failed == 0 and errors == 0 else 0
    cost = failed * 100 + errors * 100 + unknown_penalty - passed
    return (cost, failed + errors, passed)


def _extract_first_int(pattern: str, text: str) -> int:
    match = re.search(pattern, text)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except Exception:
        return 0


def _run_tests(project_dir: Path) -> Tuple[str, str, int]:
    result = PythonTestTool.run_tests(project_dir)
    exit_code = result["exit_code"]
    output = result["output"]
    cost, _, _ = _extract_test_cost(exit_code, output)
    return (exit_code, output, cost)


def auto_repair_project(project_dir: Path, max_steps: int = 3) -> RepairResult:
    source_files = discover_source_files(project_dir)
    if not source_files:
        exit_code, output, _ = _run_tests(project_dir)
        return RepairResult(
            success=(exit_code == "0"),
            applied=False,
            steps=[{"stage": "no_source_files"}],
            final_exit_code=exit_code,
            final_output=output,
        )

    state: Dict[Path, str] = {}
    for path in source_files:
        state[path] = path.read_text(encoding="utf-8")

    baseline_exit, baseline_output, baseline_cost = _run_tests(project_dir)
    if baseline_exit == "0":
        return RepairResult(
            success=True,
            applied=False,
            steps=[{"stage": "already_green"}],
            final_exit_code=baseline_exit,
            final_output=baseline_output,
        )

    steps: List[Dict[str, object]] = []
    current_cost = baseline_cost
    current_output = baseline_output
    applied_any = False
    template_weights = load_template_weights()

    for step_no in range(1, max_steps + 1):
        best = None
        best_cost = current_cost
        best_priority = -1
        best_confidence = -1.0
        best_result = None
        best_kind = ""
        best_pair = None

        priorities = _file_priority_from_context(project_dir, source_files, current_output)
        ordered_files = sorted(
            source_files,
            key=lambda p: (
                -priorities.get(_normalize_rel(p.relative_to(project_dir)), 0),
                p.as_posix(),
            ),
        )
        mutations: List[Mutation] = []
        for path in ordered_files:
            mutations.extend(
                _iter_mutations_for_source(
                    path, state[path], template_weights=template_weights
                )
            )

        if not mutations:
            steps.append({"step": step_no, "event": "no_mutations"})
            break

        suspects = _extract_suspect_locations(current_output, project_dir)
        if suspects and len(steps) < 25:
            steps.append(
                {
                    "step": step_no,
                    "event": "suspects_identified",
                    "suspects": [f"{path}:{line}" for path, line in suspects[:6]],
                }
            )

        mutations.sort(
            key=lambda m: (
                -priorities.get(_normalize_rel(m.file_path.relative_to(project_dir)), 0),
                -_mutation_priority(m, suspects),
                -float(m.confidence),
                m.file_path.as_posix(),
                m.start,
                m.description,
            )
        )

        for mutation in mutations:
            current_text = state[mutation.file_path]
            candidate_text = _replace_span(
                current_text, (mutation.start, mutation.end), mutation.replacement
            )
            if candidate_text == current_text:
                continue

            mutation.file_path.write_text(candidate_text, encoding="utf-8")
            exit_code, output, cost = _run_tests(project_dir)
            mutation.file_path.write_text(current_text, encoding="utf-8")
            priority = _mutation_priority(mutation, suspects)

            result_step = {
                "step": step_no,
                "file": mutation.file_path.name,
                "line": mutation.line_no,
                "description": mutation.description,
                "template": mutation.template,
                "confidence": round(float(mutation.confidence), 3),
                "exit_code": exit_code,
                "cost": cost,
                "priority": priority,
            }

            if exit_code == "0":
                state[mutation.file_path] = candidate_text
                mutation.file_path.write_text(candidate_text, encoding="utf-8")
                current_output = output
                steps.append(result_step)
                return RepairResult(
                    success=True,
                    applied=True,
                    steps=steps,
                    final_exit_code=exit_code,
                    final_output=output,
                )

            if cost < best_cost or (
                cost == best_cost
                and (
                    priority > best_priority
                    or (
                        priority == best_priority
                        and float(mutation.confidence) > best_confidence
                    )
                )
            ):
                best_cost = cost
                best_priority = priority
                best_confidence = float(mutation.confidence)
                best = mutation
                best_result = (candidate_text, exit_code, output, priority)
                best_kind = "single"

            # Keep just a compact trace to avoid huge reports.
            if len(steps) < 25:
                steps.append(result_step)

        # Try small pairwise multi-file combinations when single edits are not enough.
        top_mutations = mutations[: min(8, len(mutations))]
        pair_count = 0
        for i in range(len(top_mutations)):
            first = top_mutations[i]
            for j in range(i + 1, len(top_mutations)):
                second = top_mutations[j]
                if first.file_path == second.file_path:
                    continue
                pair_count += 1
                if pair_count > 12:
                    break

                first_text = state[first.file_path]
                second_text = state[second.file_path]
                first_candidate = _replace_span(
                    first_text, (first.start, first.end), first.replacement
                )
                second_candidate = _replace_span(
                    second_text, (second.start, second.end), second.replacement
                )
                if first_candidate == first_text and second_candidate == second_text:
                    continue

                first.file_path.write_text(first_candidate, encoding="utf-8")
                second.file_path.write_text(second_candidate, encoding="utf-8")
                exit_code, output, cost = _run_tests(project_dir)
                first.file_path.write_text(first_text, encoding="utf-8")
                second.file_path.write_text(second_text, encoding="utf-8")

                pair_priority = _mutation_priority(first, suspects) + _mutation_priority(
                    second, suspects
                )
                pair_confidence = (float(first.confidence) + float(second.confidence)) / 2.0

                pair_step = {
                    "step": step_no,
                    "event": "pair_candidate",
                    "files": [first.file_path.name, second.file_path.name],
                    "lines": [first.line_no, second.line_no],
                    "descriptions": [first.description, second.description],
                    "templates": [first.template, second.template],
                    "confidence": round(pair_confidence, 3),
                    "exit_code": exit_code,
                    "cost": cost,
                    "priority": pair_priority,
                }

                if exit_code == "0":
                    state[first.file_path] = first_candidate
                    state[second.file_path] = second_candidate
                    first.file_path.write_text(first_candidate, encoding="utf-8")
                    second.file_path.write_text(second_candidate, encoding="utf-8")
                    current_output = output
                    steps.append(pair_step)
                    return RepairResult(
                        success=True,
                        applied=True,
                        steps=steps,
                        final_exit_code=exit_code,
                        final_output=output,
                    )

                if cost < best_cost or (
                    cost == best_cost
                    and (
                        pair_priority > best_priority
                        or (
                            pair_priority == best_priority
                            and pair_confidence > best_confidence
                        )
                    )
                ):
                    best_cost = cost
                    best_priority = pair_priority
                    best_confidence = pair_confidence
                    best_result = (
                        (first.file_path, first_candidate),
                        (second.file_path, second_candidate),
                        exit_code,
                        output,
                    )
                    best_kind = "pair"
                    best_pair = (first, second)

                if len(steps) < 35:
                    steps.append(pair_step)
            if pair_count > 12:
                break

        if best_result is None:
            steps.append({"step": step_no, "event": "no_improvement"})
            break

        if best_kind == "single" and best is not None:
            state[best.file_path] = best_result[0]
            best.file_path.write_text(best_result[0], encoding="utf-8")
            current_output = best_result[2]
        elif best_kind == "pair" and best_pair is not None:
            first, second = best_pair
            first_path, first_candidate = best_result[0]
            second_path, second_candidate = best_result[1]
            state[first_path] = first_candidate
            state[second_path] = second_candidate
            first_path.write_text(first_candidate, encoding="utf-8")
            second_path.write_text(second_candidate, encoding="utf-8")
            current_output = best_result[3]
        else:
            steps.append({"step": step_no, "event": "no_improvement"})
            break

        current_cost = best_cost
        applied_any = True
        if best_kind == "single" and best is not None:
            steps.append(
                {
                    "step": step_no,
                    "event": "accepted_best_candidate",
                    "kind": "single",
                    "file": best.file_path.name,
                    "line": best.line_no,
                    "description": best.description,
                    "template": best.template,
                    "confidence": round(float(best.confidence), 3),
                    "cost": best_cost,
                    "priority": best_result[3],
                }
            )
        elif best_kind == "pair" and best_pair is not None:
            first, second = best_pair
            steps.append(
                {
                    "step": step_no,
                    "event": "accepted_best_candidate",
                    "kind": "pair",
                    "files": [first.file_path.name, second.file_path.name],
                    "lines": [first.line_no, second.line_no],
                    "descriptions": [first.description, second.description],
                    "templates": [first.template, second.template],
                    "confidence": round(best_confidence, 3),
                    "cost": best_cost,
                    "priority": best_priority,
                }
            )

    final_exit, final_output, _ = _run_tests(project_dir)
    return RepairResult(
        success=(final_exit == "0"),
        applied=applied_any and final_exit == "0",
        steps=steps,
        final_exit_code=final_exit,
        final_output=final_output,
    )

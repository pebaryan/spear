"""Minimal automatic program repair engine for Python projects."""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .common import PythonTestTool


@dataclass
class Mutation:
    file_path: Path
    start: int
    end: int
    replacement: str
    description: str


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


def _iter_mutations_for_source(file_path: Path, source: str) -> Iterable[Mutation]:
    try:
        tree = ast.parse(source)
    except Exception:
        return []

    seen = set()
    mutations = []

    def add_mutation(span: Tuple[int, int], replacement: str, description: str) -> None:
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
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
            swapped = _op_swap(node.ops[0])
            span = _span_for_node(source, node)
            left = ast.get_source_segment(source, node.left)
            right = ast.get_source_segment(source, node.comparators[0])
            if swapped and span and left and right:
                add_mutation(
                    span,
                    f"{left} {swapped} {right}",
                    f"Swap comparison operator to {swapped}",
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
                )

            left_num = _const_number(node.left)
            right_num = _const_number(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if right_num == 1.0:
                    add_mutation(
                        span,
                        left_src,
                        "Remove +/- 1 from expression (right side)",
                    )
                if left_num == 1.0:
                    add_mutation(
                        span,
                        right_src,
                        "Remove +/- 1 from expression (left side)",
                    )

    return sorted(mutations, key=lambda m: (m.file_path.as_posix(), m.start, m.description))


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
    applied_any = False

    for step_no in range(1, max_steps + 1):
        best = None
        best_cost = current_cost
        best_result = None

        mutations: List[Mutation] = []
        for path in source_files:
            mutations.extend(_iter_mutations_for_source(path, state[path]))

        if not mutations:
            steps.append({"step": step_no, "event": "no_mutations"})
            break

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

            result_step = {
                "step": step_no,
                "file": mutation.file_path.name,
                "description": mutation.description,
                "exit_code": exit_code,
                "cost": cost,
            }

            if exit_code == "0":
                state[mutation.file_path] = candidate_text
                mutation.file_path.write_text(candidate_text, encoding="utf-8")
                steps.append(result_step)
                return RepairResult(
                    success=True,
                    applied=True,
                    steps=steps,
                    final_exit_code=exit_code,
                    final_output=output,
                )

            if cost < best_cost:
                best_cost = cost
                best = mutation
                best_result = (candidate_text, exit_code, output)

            # Keep just a compact trace to avoid huge reports.
            if len(steps) < 25:
                steps.append(result_step)

        if best is None or best_result is None:
            steps.append({"step": step_no, "event": "no_improvement"})
            break

        state[best.file_path] = best_result[0]
        best.file_path.write_text(best_result[0], encoding="utf-8")
        current_cost = best_cost
        applied_any = True
        steps.append(
            {
                "step": step_no,
                "event": "accepted_best_candidate",
                "file": best.file_path.name,
                "description": best.description,
                "cost": best_cost,
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

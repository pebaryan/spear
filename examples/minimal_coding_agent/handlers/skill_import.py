"""Skill import system - convert markdown skills to RDF skills.

This module enables:
1. Loading skills from markdown files
2. Converting skills to RDF
3. Registering skills for agent use
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLS_PATH = BASE_DIR / "skills.ttl"

AG = Namespace("http://example.org/agent/")
SKILL = Namespace("http://example.org/skill/")

_namespaces = {
    "ag": AG,
    "skill": SKILL,
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
}

PROMPT_INJECTION_PATTERNS = {
    "instruction_override": re.compile(
        r"(ignore\s+(all|previous|prior)\s+instructions?)",
        re.IGNORECASE,
    ),
    "prompt_exfiltration": re.compile(
        r"(system\s+prompt|developer\s+message|hidden\s+prompt)",
        re.IGNORECASE,
    ),
    "dangerous_execution": re.compile(
        r"(run\s+this\s+command|execute\s+(shell|bash|powershell)|subprocess\.)",
        re.IGNORECASE,
    ),
    "secret_exfiltration": re.compile(
        r"(print\s+environment\s+variables|show\s+api\s+key|reveal\s+secrets?)",
        re.IGNORECASE,
    ),
}


def _create_skills_graph() -> Graph:
    g = Graph()
    for prefix, ns in _namespaces.items():
        g.bind(prefix, ns)
    return g


def load_skills_graph() -> Graph:
    g = _create_skills_graph()
    if SKILLS_PATH.exists():
        g.parse(SKILLS_PATH, format="turtle")
    return g


def save_skills_graph(g: Graph) -> None:
    g.serialize(SKILLS_PATH, format="turtle")


def _get_skill_count(g: Graph) -> int:
    count = 0
    for _ in g.subjects(RDF.type, SKILL.Skill):
        count += 1
    return count


def sanitize_skill_text(text: str) -> tuple[str, List[str]]:
    """Remove prompt-injection style lines and return risk flags."""
    if not text:
        return "", []

    risk_flags = set()
    kept_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        matched_flags = []
        for flag, pattern in PROMPT_INJECTION_PATTERNS.items():
            if pattern.search(stripped):
                matched_flags.append(flag)
        if matched_flags:
            risk_flags.update(matched_flags)
        else:
            kept_lines.append(line)

    cleaned = "\n".join(kept_lines).strip()
    return cleaned, sorted(risk_flags)


def parse_markdown_skill(
    markdown_content: str, source_file: str = None
) -> Dict[str, Any]:
    """Parse a markdown file into a skill structure."""
    lines = markdown_content.split("\n")

    title = ""
    description = ""
    category = "general"
    examples = []
    patterns = []
    code_blocks = []

    in_examples = False
    in_patterns = False
    current_example = ""
    current_pattern = ""

    for line in lines:
        line = line.rstrip()
        stripped = line.strip()
        is_bullet = stripped.startswith("- ")
        is_numbered = bool(re.match(r"^\d+\.\s+", stripped))
        item_text = re.sub(r"^\d+\.\s+", "", stripped)
        if is_bullet:
            item_text = stripped[2:].strip()

        if line.startswith("# "):
            title = line[2:].strip()
            continue

        if line.lower().startswith("## description"):
            continue
        if line.lower().startswith("## examples"):
            in_examples = True
            in_patterns = False
            continue
        if line.lower().startswith("## patterns"):
            in_patterns = True
            in_examples = False
            continue
        if line.startswith("```"):
            if code_blocks:
                if code_blocks[-1] == "end":
                    code_blocks.pop()
                else:
                    code_blocks.append(line[3:].strip())
            else:
                lang = line[3:].strip()
                code_blocks.append(lang if lang else "python")
            continue

        if in_examples and (is_bullet or is_numbered):
            if current_example:
                examples.append(current_example)
            current_example = item_text.strip()
            continue
        elif in_patterns and (is_bullet or is_numbered):
            if current_pattern:
                patterns.append(current_pattern)
            current_pattern = item_text.strip()
            continue
        elif not in_examples and not in_patterns and line:
            description += line + " "

    if current_example:
        examples.append(current_example)
    if current_pattern:
        patterns.append(current_pattern)

    risk_flags = set()

    title, title_flags = sanitize_skill_text(title)
    risk_flags.update(title_flags)
    if not title:
        title = "Untitled Skill"

    description, description_flags = sanitize_skill_text(description.strip())
    risk_flags.update(description_flags)

    cleaned_examples = []
    for example in examples:
        cleaned, flags = sanitize_skill_text(example)
        risk_flags.update(flags)
        if cleaned:
            cleaned_examples.append(cleaned)

    cleaned_patterns = []
    for pattern in patterns:
        cleaned, flags = sanitize_skill_text(pattern)
        risk_flags.update(flags)
        if cleaned:
            cleaned_patterns.append(cleaned)

    return {
        "title": title,
        "description": description,
        "category": category,
        "examples": cleaned_examples,
        "patterns": cleaned_patterns,
        "source": source_file,
        "sanitized": bool(risk_flags),
        "risk_flags": sorted(risk_flags),
    }


def import_markdown_skill(markdown_path: str) -> str:
    """Import a markdown file as a skill."""
    path = Path(markdown_path)

    if not path.exists():
        return f"File not found: {markdown_path}"

    content = path.read_text(encoding="utf-8")
    skill_data = parse_markdown_skill(content, str(path))

    g = load_skills_graph()

    skill_id = _get_skill_count(g)
    skill_uri = SKILL[f"skill/{skill_id}"]

    g.add((skill_uri, RDF.type, SKILL.Skill))
    g.add(
        (
            skill_uri,
            SKILL.importedAt,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    g.add((skill_uri, SKILL.title, Literal(skill_data["title"])))
    g.add((skill_uri, SKILL.description, Literal(skill_data["description"])))
    g.add((skill_uri, SKILL.category, Literal(skill_data["category"])))
    g.add(
        (
            skill_uri,
            SKILL.isSanitized,
            Literal(bool(skill_data.get("sanitized")), datatype=XSD.boolean),
        )
    )

    if skill_data["source"]:
        g.add((skill_uri, SKILL.sourceFile, Literal(skill_data["source"])))
    for flag in skill_data.get("risk_flags", []):
        g.add((skill_uri, SKILL.safetyFlag, Literal(flag)))

    for idx, example in enumerate(skill_data["examples"]):
        example_uri = SKILL[f"skill/{skill_id}/example/{idx}"]
        g.add((example_uri, RDF.type, SKILL.Example))
        g.add((example_uri, SKILL.content, Literal(example)))
        g.add((skill_uri, SKILL.hasExample, example_uri))

    for idx, pattern in enumerate(skill_data["patterns"]):
        pattern_uri = SKILL[f"skill/{skill_id}/pattern/{idx}"]
        g.add((pattern_uri, RDF.type, SKILL.Pattern))
        g.add((pattern_uri, SKILL.content, Literal(pattern)))
        g.add((skill_uri, SKILL.hasPattern, pattern_uri))

    save_skills_graph(g)

    sanitized_note = ""
    if skill_data.get("risk_flags"):
        sanitized_note = f" [sanitized flags: {', '.join(skill_data['risk_flags'])}]"
    return f"Imported skill: {skill_data['title']} (ID: {skill_id}){sanitized_note}"


def import_directory_skills(directory: str) -> List[str]:
    """Import all markdown files from a directory."""
    dir_path = Path(directory)

    if not dir_path.exists():
        return [f"Directory not found: {directory}"]

    results = []

    for md_file in dir_path.glob("**/*.md"):
        result = import_markdown_skill(str(md_file))
        results.append(result)

    return results


def get_skills(limit: int = 50) -> List[Dict[str, Any]]:
    """Get all imported skills."""
    g = load_skills_graph()

    skills = []
    for skill in g.subjects(RDF.type, SKILL.Skill):
        data = {
            "uri": str(skill),
            "title": str(g.value(skill, SKILL.title) or ""),
            "description": str(g.value(skill, SKILL.description) or ""),
            "category": str(g.value(skill, SKILL.category) or ""),
            "imported_at": str(g.value(skill, SKILL.importedAt) or ""),
            "source": str(g.value(skill, SKILL.sourceFile) or ""),
            "examples": [],
            "patterns": [],
            "risk_flags": [],
            "sanitized": False,
        }

        for example in g.objects(skill, SKILL.hasExample):
            content = g.value(example, SKILL.content)
            if content:
                data["examples"].append(str(content))

        for pattern in g.objects(skill, SKILL.hasPattern):
            content = g.value(pattern, SKILL.content)
            if content:
                data["patterns"].append(str(content))

        for flag in g.objects(skill, SKILL.safetyFlag):
            data["risk_flags"].append(str(flag))
        data["risk_flags"] = sorted(set(data["risk_flags"]))
        sanitized_literal = g.value(skill, SKILL.isSanitized)
        if sanitized_literal is not None:
            try:
                data["sanitized"] = bool(sanitized_literal.toPython())
            except Exception:
                data["sanitized"] = (
                    str(sanitized_literal).strip().lower() in {"1", "true", "yes"}
                )
        elif data["risk_flags"]:
            data["sanitized"] = True

        skills.append(data)

    skills.sort(key=lambda x: x["imported_at"], reverse=True)
    return skills[:limit]


def search_skills(query: str, safe_only: bool = True) -> List[Dict[str, Any]]:
    """Search skills by query."""
    skills = get_skills()
    query_lower = query.lower()

    results = []
    for skill in skills:
        if safe_only and skill.get("risk_flags"):
            continue
        if query_lower in skill["title"].lower():
            results.append(skill)
        elif query_lower in skill["description"].lower():
            results.append(skill)
        elif any(query_lower in p.lower() for p in skill["patterns"]):
            results.append(skill)

    return results


def get_skill_for_context(context: str) -> Optional[Dict[str, Any]]:
    """Get most relevant skill for a context."""
    skills = search_skills(context, safe_only=True)
    return skills[0] if skills else None


class SkillRegistry:
    """Registry of loaded skills for agent use."""

    def __init__(self):
        self._skills = {}
        self._load_from_rdf()

    def _load_from_rdf(self):
        """Load skills from RDF."""
        skills = get_skills()
        for skill in skills:
            self._skills[skill["title"]] = skill

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a skill by name."""
        return self._skills.get(name)

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search skills."""
        return search_skills(query)

    def all(self) -> List[Dict[str, Any]]:
        """Get all skills."""
        return list(self._skills.values())

    def reload(self):
        """Reload skills from RDF."""
        self._skills = {}
        self._load_from_rdf()


_global_registry = SkillRegistry()


def get_skill_registry() -> SkillRegistry:
    """Get the global skill registry."""
    return _global_registry

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = ROOT / "tests" / "fixtures"
REQUIRED_GOVERNANCE_DOCS = {
    "AGENTS.md",
    "CLAUDE.md",
    "CONTEXT.md",
    "QUESTION_STRUCTURE.md",
    "ARCHITECTURE.md",
    "IMPLEMENTATION_PLAN.md",
}
FORBIDDEN_RUNTIME_MODULE_PARTS = {"evaluation", "fixtures", "legacy", "nexus", "priority"}
ROUTING_IDENTIFIER_NAMES = {"question_id", "test_id", "case_id", "cq_id"}
REQUIRED_FIXTURE_FIELDS = {
    "test_id",
    "test_purpose",
    "capability_under_test",
    "question",
    "question_structure",
    "expected_decision",
    "falsifies_if",
    "ambiguity_intentional",
    "provenance",
}


def runtime_python_files() -> list[Path]:
    if not SRC.exists():
        return []
    return sorted(SRC.rglob("*.py"))


def load_question_fixtures() -> list[dict[str, object]]:
    fixtures: list[dict[str, object]] = []
    for path in sorted(FIXTURES.glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            record = json.loads(line)
            record["_location"] = f"{path.relative_to(ROOT)}:{line_number}"
            fixtures.append(record)
    return fixtures


def dotted_import_parts(node: ast.Import | ast.ImportFrom) -> set[str]:
    names: list[str] = []
    if isinstance(node, ast.Import):
        names.extend(alias.name for alias in node.names)
    elif node.module:
        names.append(node.module)
    return {part for name in names for part in name.split(".")}


def referenced_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def contains_nonempty_literal(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and bool(child.value.strip())
        for child in ast.walk(node)
    )


def test_required_governance_documents_exist() -> None:
    missing = sorted(name for name in REQUIRED_GOVERNANCE_DOCS if not (ROOT / name).is_file())
    assert not missing, f"missing architecture governance documents: {missing}"


def test_runtime_does_not_import_legacy_or_evaluation_modules() -> None:
    violations: list[str] = []
    for path in runtime_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            forbidden = dotted_import_parts(node) & FORBIDDEN_RUNTIME_MODULE_PARTS
            if forbidden:
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} imports {sorted(forbidden)}"
                )
    assert not violations, "runtime imports forbidden legacy/evaluation modules:\n" + "\n".join(
        violations
    )


def test_runtime_does_not_branch_on_nonempty_fixture_identifiers() -> None:
    violations: list[str] = []
    for path in runtime_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            expression: ast.AST | None = None
            if isinstance(node, ast.If):
                expression = node.test
            elif isinstance(node, ast.Match):
                expression = node.subject
            if expression is None:
                continue
            if referenced_names(expression) & ROUTING_IDENTIFIER_NAMES and (
                isinstance(node, ast.Match) or contains_nonempty_literal(expression)
            ):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, (
        "runtime control flow branches on question/test/case/CQ identifiers: " + ", ".join(violations)
    )


def test_runtime_does_not_embed_source_workspace_or_fixture_questions() -> None:
    question_texts = {
        str(record["question"])
        for record in load_question_fixtures()
        if isinstance(record.get("question"), str)
    }
    violations: list[str] = []
    for path in runtime_python_files():
        text = path.read_text(encoding="utf-8")
        normalized = text.replace("\\", "/").lower()
        if "c:/users/user/asset_agent" in normalized:
            violations.append(f"{path.relative_to(ROOT)} embeds the previous workspace path")
        for question in question_texts:
            if question and question in text:
                violations.append(f"{path.relative_to(ROOT)} embeds fixture question: {question!r}")
    assert not violations, "runtime contains migration residue:\n" + "\n".join(violations)


def test_question_fixtures_declare_purpose_and_ambiguity_intent() -> None:
    violations: list[str] = []
    for record in load_question_fixtures():
        location = str(record["_location"])
        missing = sorted(REQUIRED_FIXTURE_FIELDS - record.keys())
        if missing:
            violations.append(f"{location} missing {missing}")
            continue
        if record["ambiguity_intentional"] is True:
            purpose = str(record["test_purpose"]).lower()
            capability = str(record["capability_under_test"]).lower()
            expected = str(record["expected_decision"]).lower()
            if "ambig" not in purpose + capability or "refus" not in expected:
                violations.append(
                    f"{location} intentional ambiguity must test ambiguity refusal explicitly"
                )
    assert not violations, "invalid purpose-based question fixtures:\n" + "\n".join(violations)

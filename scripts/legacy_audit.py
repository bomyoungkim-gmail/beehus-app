"""
Legacy pattern audit for Python code.

Usage:
    python scripts/legacy_audit.py
    python scripts/legacy_audit.py --path core app
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass
class Finding:
    file_path: Path
    line: int
    kind: str
    message: str


DEFAULT_PATHS = ["app", "core", "migrations", "scripts"]
IGNORE_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules"}


class LegacyAuditVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, source_lines: List[str]):
        self.file_path = file_path
        self.source_lines = source_lines
        self.findings: List[Finding] = []

    def _add(self, node: ast.AST, kind: str, message: str) -> None:
        self.findings.append(
            Finding(
                file_path=self.file_path,
                line=getattr(node, "lineno", 1),
                kind=kind,
                message=message,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "utcnow" and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "datetime":
                    self._add(
                        node,
                        "utcnow",
                        "Use timezone-aware UTC (datetime.now(timezone.utc) or project helper)",
                    )
            if node.func.attr == "dict":
                self._add(
                    node,
                    "pydantic-dict",
                    "Use model_dump(...) instead of dict(...) for Pydantic v2 models",
                )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        base_names = {self._base_name(base) for base in node.bases}
        is_pydantic_model = any(name in {"BaseModel", "BaseSettings"} for name in base_names)

        if is_pydantic_model:
            for child in node.body:
                if isinstance(child, ast.ClassDef) and child.name == "Config":
                    self._add(
                        child,
                        "pydantic-config",
                        "Use model_config = ConfigDict(...) instead of class Config",
                    )

                if isinstance(child, ast.AnnAssign):
                    target_name = self._annassign_name(child)
                    if target_name and self._is_mutable_literal(child.value):
                        self._add(
                            child,
                            "mutable-default",
                            f"Field '{target_name}' uses mutable literal default; use Field(default_factory=...)",
                        )
                elif isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name) and self._is_mutable_literal(child.value):
                            self._add(
                                child,
                                "mutable-default",
                                f"Field '{target.id}' uses mutable literal default; use Field(default_factory=...)",
                            )

        self.generic_visit(node)

    @staticmethod
    def _base_name(base: ast.expr) -> str:
        if isinstance(base, ast.Name):
            return base.id
        if isinstance(base, ast.Attribute):
            return base.attr
        return ""

    @staticmethod
    def _annassign_name(node: ast.AnnAssign) -> str:
        if isinstance(node.target, ast.Name):
            return node.target.id
        return ""

    @staticmethod
    def _is_mutable_literal(value: ast.AST | None) -> bool:
        return isinstance(value, (ast.List, ast.Dict, ast.Set))


def iter_python_files(paths: Iterable[Path]) -> Iterable[Path]:
    for root in paths:
        if root.is_file() and root.suffix == ".py":
            yield root
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in IGNORE_DIRS for part in path.parts):
                continue
            yield path


def audit_file(file_path: Path) -> List[Finding]:
    try:
        source = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [
            Finding(file_path=file_path, line=exc.lineno or 1, kind="syntax", message="Cannot parse file")
        ]

    visitor = LegacyAuditVisitor(file_path=file_path, source_lines=source.splitlines())
    visitor.visit(tree)
    return visitor.findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit workspace for legacy Python patterns")
    parser.add_argument("--path", nargs="*", default=DEFAULT_PATHS, help="Paths to scan")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    scan_paths = [project_root / p for p in args.path]

    all_findings: List[Finding] = []
    for py_file in iter_python_files(scan_paths):
        all_findings.extend(audit_file(py_file))

    if not all_findings:
        print("✅ No legacy patterns found in scanned paths.")
        return 0

    all_findings.sort(key=lambda f: (str(f.file_path), f.line, f.kind))
    print(f"⚠️  Found {len(all_findings)} legacy pattern(s):")
    for finding in all_findings:
        rel = finding.file_path.relative_to(project_root)
        print(f"- {rel}:{finding.line} [{finding.kind}] {finding.message}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

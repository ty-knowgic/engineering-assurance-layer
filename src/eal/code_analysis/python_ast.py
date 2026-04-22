"""Static analysis for Python code inputs using stdlib ``ast`` only."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from eal.code_analysis.matching import classify_numeric_symbol, normalize_symbol_name
from eal.ingestion.loaders import CodeFile
from eal.ir.schema import CodeComparison, CodeConstant, CodeEvidence


def _evidence_id(prefix: str, file: str, line: Optional[int], key: str) -> str:
    base = f"{prefix}|{file}|{line or 0}|{key}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _op_to_text(op: ast.cmpop) -> Optional[str]:
    if isinstance(op, ast.Lt):
        return "<"
    if isinstance(op, ast.LtE):
        return "<="
    if isinstance(op, ast.Gt):
        return ">"
    if isinstance(op, ast.GtE):
        return ">="
    if isinstance(op, ast.Eq):
        return "=="
    if isinstance(op, ast.NotEq):
        return "!="
    return None


def _invert_op(op: str) -> str:
    return {
        "<": ">",
        "<=": ">=",
        ">": "<",
        ">=": "<=",
        "==": "==",
        "!=": "!=",
    }[op]


@dataclass
class CodeAnalysisResult:
    constants: list[CodeConstant] = field(default_factory=list)
    comparisons: list[CodeComparison] = field(default_factory=list)
    evidence: list[CodeEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class _PythonExtractor(ast.NodeVisitor):
    def __init__(self, path: Path, source: str) -> None:
        self.path = str(path)
        self.source = source
        self.lines = source.splitlines()

        self.constants: list[CodeConstant] = []
        self.comparisons: list[CodeComparison] = []
        self.evidence: list[CodeEvidence] = []

        self._env_stack: list[dict[str, float]] = [{}]
        self._scope_stack: list[str] = ["module"]
        self._class_stack: list[str] = []
        self._context_stack: list[str] = []

    def _scope(self) -> str:
        return self._scope_stack[-1]

    def _context(self) -> Optional[str]:
        return self._context_stack[-1] if self._context_stack else None

    def _lookup(self, key: str) -> Optional[float]:
        for env in reversed(self._env_stack):
            if key in env:
                return env[key]
        # Fallback for class references: prefer leaf name if exact key not found.
        leaf = key.split(".")[-1]
        for env in reversed(self._env_stack):
            if leaf in env:
                return env[leaf]
        return None

    def _store(self, key: str, value: float) -> None:
        self._env_stack[-1][key] = value

    def _snippet(self, node: ast.AST) -> Optional[str]:
        segment = ast.get_source_segment(self.source, node)
        if segment:
            text = " ".join(segment.strip().split())
            return text[:220]
        lineno = getattr(node, "lineno", None)
        if lineno and 0 < lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()[:220]
        return None

    def _symbol_from_expr(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._symbol_from_expr(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return None

    def _resolve_numeric(self, node: ast.AST) -> Optional[float]:
        if isinstance(node, ast.Constant):
            val = node.value
            if isinstance(val, bool):
                return None
            if isinstance(val, (int, float)):
                return float(val)
            return None

        if isinstance(node, ast.UnaryOp):
            inner = self._resolve_numeric(node.operand)
            if inner is None:
                return None
            if isinstance(node.op, ast.USub):
                return -inner
            if isinstance(node.op, ast.UAdd):
                return inner
            return None

        if isinstance(node, ast.Name):
            return self._lookup(node.id)

        if isinstance(node, ast.Attribute):
            symbol = self._symbol_from_expr(node)
            if symbol is None:
                return None
            return self._lookup(symbol)

        if isinstance(node, ast.BinOp):
            left = self._resolve_numeric(node.left)
            right = self._resolve_numeric(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    return None
                return left / right
        return None

    def _is_constant_candidate(self, name: str) -> bool:
        if len(name) < 3:
            return False
        if not name.replace("_", "").isalnum():
            return False
        # Accept conventional constants and engineering-style snake_case declarations.
        return name.isupper() or "_" in name

    def _record_constant(self, node: ast.AST, symbol: str, value: float) -> None:
        normalized = normalize_symbol_name(symbol)
        if not normalized:
            return
        symbol_class, class_conf, class_reason = classify_numeric_symbol(symbol)
        line = getattr(node, "lineno", 1)
        evid = _evidence_id("CC", self.path, line, f"{symbol}={value}")
        const = CodeConstant(
            evidence_id=evid,
            file=self.path,
            line=line,
            symbol=symbol,
            normalized_name=normalized,
            value=value,
            snippet=self._snippet(node),
            scope=self._scope(),
            classification=symbol_class,
            classification_confidence=class_conf,
            classification_reason=class_reason,
        )
        self.constants.append(const)
        self.evidence.append(CodeEvidence(
            evidence_id=evid,
            kind="constant",
            file=self.path,
            line=line,
            symbol=symbol,
            normalized_name=normalized,
            value=value,
            snippet=const.snippet,
        ))

    def _record_comparison(self, node: ast.Compare, symbol: str, op: str, value: float) -> None:
        normalized = normalize_symbol_name(symbol)
        if not normalized:
            return
        symbol_class, class_conf, class_reason = classify_numeric_symbol(symbol)
        line = getattr(node, "lineno", 1)
        evid = _evidence_id("CMP", self.path, line, f"{symbol}{op}{value}")
        cmp_item = CodeComparison(
            evidence_id=evid,
            file=self.path,
            line=line,
            symbol=symbol,
            normalized_name=normalized,
            operator=op,
            value=value,
            snippet=self._snippet(node),
            context=self._context(),
            classification=symbol_class,
            classification_confidence=class_conf,
            classification_reason=class_reason,
        )
        self.comparisons.append(cmp_item)
        self.evidence.append(CodeEvidence(
            evidence_id=evid,
            kind="comparison",
            file=self.path,
            line=line,
            symbol=symbol,
            normalized_name=normalized,
            value=value,
            operator=op,
            snippet=cmp_item.snippet,
        ))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        self._scope_stack.append("class")
        self._env_stack.append({})

        for stmt in node.body:
            self.visit(stmt)

        class_env = self._env_stack.pop()
        class_name = self._class_stack.pop()
        self._scope_stack.pop()

        # Export class constants for later references like Limits.MAX_SPEED.
        for key, value in class_env.items():
            self._env_stack[-1][f"{class_name}.{key}"] = value

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope_stack.append("function")
        self._env_stack.append({})
        self.generic_visit(node)
        self._env_stack.pop()
        self._scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_If(self, node: ast.If) -> None:
        self._context_stack.append("if")
        self.visit(node.test)
        self._context_stack.pop()
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_Assert(self, node: ast.Assert) -> None:
        self._context_stack.append("assert")
        self.visit(node.test)
        self._context_stack.pop()
        if node.msg is not None:
            self.visit(node.msg)

    def visit_While(self, node: ast.While) -> None:
        self._context_stack.append("while")
        self.visit(node.test)
        self._context_stack.pop()
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_Assign(self, node: ast.Assign) -> None:
        value = self._resolve_numeric(node.value)
        if value is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbol = target.id
                    self._store(symbol, value)
                    if self._scope() in {"module", "class"} and self._is_constant_candidate(symbol):
                        self._record_constant(node, symbol, value)
                elif isinstance(target, ast.Attribute):
                    symbol = self._symbol_from_expr(target)
                    if symbol:
                        self._store(symbol, value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            value = self._resolve_numeric(node.value)
            if value is not None and isinstance(node.target, ast.Name):
                symbol = node.target.id
                self._store(symbol, value)
                if self._scope() in {"module", "class"} and self._is_constant_candidate(symbol):
                    self._record_constant(node, symbol, value)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if len(node.ops) != 1 or len(node.comparators) != 1:
            self.generic_visit(node)
            return

        op = _op_to_text(node.ops[0])
        if op is None:
            self.generic_visit(node)
            return

        left = node.left
        right = node.comparators[0]

        left_symbol = self._symbol_from_expr(left)
        right_symbol = self._symbol_from_expr(right)
        left_num = self._resolve_numeric(left)
        right_num = self._resolve_numeric(right)

        if left_symbol and right_num is not None:
            self._record_comparison(node, left_symbol, op, right_num)
        elif right_symbol and left_num is not None:
            self._record_comparison(node, right_symbol, _invert_op(op), left_num)

        self.generic_visit(node)


def analyze_python_code_files(code_files: list[CodeFile]) -> CodeAnalysisResult:
    """Analyze Python files and extract constants/comparisons for assurance rules."""
    result = CodeAnalysisResult()

    for code_file in code_files:
        path = Path(code_file.path)
        file_str = str(path)

        if path.suffix != ".py":
            warning = f"Code analysis skipped non-Python file: {file_str}"
            result.warnings.append(warning)
            evid = _evidence_id("CW", file_str, None, "non-python")
            result.evidence.append(CodeEvidence(
                evidence_id=evid,
                kind="warning",
                file=file_str,
                message=warning,
            ))
            continue

        try:
            tree = ast.parse(code_file.text, filename=file_str)
        except SyntaxError as exc:
            line = exc.lineno or 0
            warning = f"Python parse error in {file_str}:{line}: {exc.msg}"
            result.warnings.append(warning)
            evid = _evidence_id("CW", file_str, line, exc.msg)
            result.evidence.append(CodeEvidence(
                evidence_id=evid,
                kind="warning",
                file=file_str,
                line=exc.lineno,
                snippet=(exc.text or "").strip()[:220] or None,
                message=warning,
            ))
            continue

        extractor = _PythonExtractor(path=path, source=code_file.text)
        extractor.visit(tree)

        result.constants.extend(extractor.constants)
        result.comparisons.extend(extractor.comparisons)
        result.evidence.extend(extractor.evidence)

    # Explicit sort for stable artifact output independent of list order.
    result.constants.sort(key=lambda c: (c.file, c.line, c.symbol, c.value))
    result.comparisons.sort(key=lambda c: (c.file, c.line, c.symbol, c.operator, c.value))
    result.evidence.sort(key=lambda e: (e.file, e.line or 0, e.evidence_id))
    return result

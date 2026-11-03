"""Architecture check: enforces import-layer and env-access rules over backend/app via ast.

Rules are data (see RULES); run as a script, it prints violations and exits 1 if any.
"""

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    name: str
    applies_to_prefix: tuple[str, ...]  # empty tuple: applies to every module
    forbidden_prefixes: tuple[str, ...]
    allowed_exceptions: tuple[str, ...] = ()
    skip_modules: tuple[str, ...] = ()


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    name: str
    rule: str

    def __str__(self) -> str:
        if self.rule == SYNTAX_RULE:
            return f"{self.path}:{self.line}: syntax error: {self.name}"
        return f"{self.path}:{self.line}: forbidden import '{self.name}' (rule: {self.rule})"


SYNTAX_RULE = "syntax-error"
COMPOSITION_ROOT = ("app.core.deps", "app.main")

RULES: tuple[Rule, ...] = (
    Rule(
        "domain-pure",
        ("app.domain",),
        ("app.", "fastapi", "starlette", "pydantic", "sqlalchemy", "httpx"),
        ("app.domain",),
    ),
    Rule(
        "api-no-data-access",
        ("app.api",),
        ("app.repositories", "app.portal", "app.db", "sqlalchemy", "httpx"),
        skip_modules=COMPOSITION_ROOT,
    ),
    Rule(
        "services-no-http-or-concrete",
        ("app.services",),
        (
            "fastapi",
            "starlette",
            "app.api",
            "app.db",
            "sqlalchemy",
            "httpx",
            "app.repositories",
            "app.portal",
            "app.core",
        ),
        ("app.repositories.interfaces", "app.portal.interfaces", "app.core.interfaces"),
    ),
    Rule(
        "repositories-no-upward",
        ("app.repositories",),
        ("fastapi", "starlette", "app.api", "app.services", "app.portal"),
    ),
    Rule(
        "portal-isolated",
        ("app.portal",),
        (
            "fastapi",
            "starlette",
            "app.api",
            "app.services",
            "app.repositories",
            "app.db",
            "sqlalchemy",
            "app.core",
        ),
        ("app.core.interfaces",),
    ),
    Rule(
        "core-no-features",
        ("app.core",),
        ("app.services", "app.repositories", "app.portal", "app.db"),
        skip_modules=COMPOSITION_ROOT,
    ),
    Rule(
        "env-only-in-config",
        (),
        ("os.environ", "os.getenv", "os.*", "pydantic_settings"),
        skip_modules=("app.core.config",),
    ),
    Rule("no-dynamic-imports", (), ("importlib.import_module", "__import__")),
    Rule("no-star-imports", (), ("*",)),
    Rule(
        "clock-wired-in-deps",
        (),
        ("app.core.clock",),
        skip_modules=("app.core.deps", "app.core.clock"),
    ),
    Rule(
        "cache-wired-in-deps",
        (),
        ("app.core.cache",),
        skip_modules=("app.core.deps", "app.core.cache"),
    ),
)


def _matches(name: str, prefix: str) -> bool:
    if prefix == "*":  # wildcard rule: any star-import
        return name.endswith(".*")
    if prefix.endswith("."):
        return name.startswith(prefix)
    return name == prefix or name.startswith(prefix + ".")


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Map local names bound by `import x[.y] [as z]` to the module they refer to."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = a.name
                else:
                    top = a.name.split(".")[0]
                    aliases[top] = top
    return aliases


def _imports(tree: ast.AST, module: str, is_package: bool) -> list[tuple[int, str]]:
    """Return (line, dotted name) for every import, attribute use and dynamic import."""
    package = module.split(".") if is_package else module.split(".")[:-1]
    aliases = _aliases(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                if node.module:
                    base = [*base, node.module]
                base_name = ".".join(base)
            else:
                base_name = node.module or ""
            # `from a import b` imports a.b (module or attribute): resolve it for every rule.
            found += [(node.lineno, f"{base_name}.{a.name}") for a in node.names]
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            found.append((node.lineno, f"{aliases[node.value.id]}.{node.attr}"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
        ):
            found.append((node.lineno, "__import__"))
    return found


def _display_path(root: Path, path: Path) -> str:
    """Path relative to the repo root (root's grandparent), so it is clickable from there."""
    return path.relative_to(root.parent.parent).as_posix()


def check(root: Path) -> list[Violation]:
    """Check every .py file under root (the `app` package dir) against RULES."""
    violations: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        module = _module_name(root, path)
        shown = _display_path(root, path)
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError as exc:
            violations.append(Violation(shown, exc.lineno or 0, exc.msg, SYNTAX_RULE))
            continue
        imports = _imports(tree, module, path.name == "__init__.py")
        for rule in RULES:
            if module in rule.skip_modules:
                continue
            if rule.applies_to_prefix and not any(
                _matches(module, p) for p in rule.applies_to_prefix
            ):
                continue
            seen_lines: set[int] = set()
            for line, name in imports:
                if line in seen_lines or any(_matches(name, a) for a in rule.allowed_exceptions):
                    continue
                if any(_matches(name, f) for f in rule.forbidden_prefixes):
                    seen_lines.add(line)
                    violations.append(Violation(shown, line, name, rule.name))
    return violations


def main(argv: list[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parents[1] / "app"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    args = parser.parse_args(argv)
    violations = check(args.root)
    for v in violations:
        print(v)
    if violations:
        return 1
    count = sum(1 for _ in args.root.rglob("*.py"))
    print(f"layering OK ({count} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

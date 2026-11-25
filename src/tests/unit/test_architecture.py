"""Clean-architecture guard: each layer may only import layers inside it."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "rarest_blue"
LAYERS = ["domain", "application", "infrastructure", "entrypoints"]  # inner to outer
# What each layer may import from outside the standard library.
ALLOWED_THIRD_PARTY = {
    "domain": set(),
    "application": {"pydantic"},  # the LLM reply contract
    "infrastructure": {"psycopg", "httpx"},
    "entrypoints": {"fastapi", "pydantic", "uvicorn", "discord"},
}
THIRD_PARTY = {"fastapi", "pydantic", "psycopg", "httpx", "uvicorn", "starlette", "discord"}


def _imports(path: Path) -> set[str]:
    """Absolute module names this file imports (relative imports resolved against the package)."""
    rel = path.relative_to(PACKAGE.parent).with_suffix("")
    pkg = list(rel.parts[:-1])
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[: len(pkg) - node.level + 1]
                found.add(".".join(base + ([node.module] if node.module else [])))
            elif node.module:
                found.add(node.module)
    return found


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_only_depends_inward(layer):
    outer = set(LAYERS[LAYERS.index(layer) + 1 :]) | ({"config"} if layer in ("domain", "application") else set())
    for path in (PACKAGE / layer).rglob("*.py"):
        for mod in _imports(path):
            parts = mod.split(".")
            if parts[0] == "rarest_blue":
                assert len(parts) < 2 or parts[1] not in outer, f"{path.relative_to(PACKAGE)} imports {mod}"
            elif parts[0] in THIRD_PARTY:
                assert parts[0] in ALLOWED_THIRD_PARTY[layer], f"{path.relative_to(PACKAGE)} imports {mod}"

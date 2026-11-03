import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_layering import check

BACKEND = Path(__file__).resolve().parents[1]


def _pkg(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "app"
    for rel, src in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)
    return root


def _rules(root: Path) -> set[str]:
    return {v.rule for v in check(root)}


def test_real_app_passes() -> None:
    assert check(BACKEND / "app") == []


@pytest.mark.parametrize(
    ("path", "src", "rule"),
    [
        ("api/v1/routers/h.py", "import app.repositories.x\n", "api-no-data-access"),
        ("services/s.py", "import fastapi\n", "services-no-http-or-concrete"),
        ("services/s.py", "from app.portal.http_client import C\n", "services-no-http-or-concrete"),
        ("domain/m.py", "from pydantic import BaseModel\n", "domain-pure"),
        ("domain/m.py", "from app.core import config\n", "domain-pure"),
        ("services/s.py", "import os\nx = os.getenv('A')\n", "env-only-in-config"),
        ("services/s.py", "import os\nx = os.environ['A']\n", "env-only-in-config"),
        ("services/s.py", "from os import environ\n", "env-only-in-config"),
        ("api/v1/r.py", "from ...repositories import x\n", "api-no-data-access"),
        ("core/c.py", "from app.services import s\n", "core-no-features"),
    ],
)
def test_violations(tmp_path: Path, path: str, src: str, rule: str) -> None:
    assert rule in _rules(_pkg(tmp_path, {path: src}))


def test_allowed_exceptions(tmp_path: Path) -> None:
    root = _pkg(
        tmp_path,
        {
            "services/s.py": (
                "from app.portal.interfaces import P\nfrom app.core.interfaces import C\n"
            ),
            "domain/m.py": "from app.domain import exceptions\n",
            "core/config.py": "import os\nfrom pydantic_settings import BaseSettings\n",
        },
    )
    assert check(root) == []


def test_composition_root_exempt_from_layers_not_env(tmp_path: Path) -> None:
    root = _pkg(
        tmp_path,
        {
            "core/deps.py": "from app.repositories import x\nimport os\nos.getenv('A')\n",
            "main.py": "from app.portal import y\n",
        },
    )
    assert _rules(root) == {"env-only-in-config"}


def test_cli_output_and_exit_code(tmp_path: Path) -> None:
    root = _pkg(tmp_path, {"api/v1/routers/h.py": "import app.repositories\n"})
    script = BACKEND / "scripts" / "check_layering.py"
    r = subprocess.run(
        [sys.executable, str(script), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 1
    assert (
        "app/api/v1/routers/h.py:1: forbidden import 'app.repositories' (rule: api-no-data-access)"
    ) in r.stdout
    ok = subprocess.run(
        [sys.executable, str(script), "--root", str(BACKEND / "app")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0
    assert ok.stdout.startswith("layering OK (")


@pytest.mark.parametrize(
    ("path", "src", "rule"),
    [
        ("services/s.py", "import os as o\nx = o.environ['A']\n", "env-only-in-config"),
        ("services/s.py", "import os as o\nx = o.getenv('A')\n", "env-only-in-config"),
        ("services/s.py", "from os import *\n", "no-star-imports"),
        ("services/s.py", "from os import *\n", "env-only-in-config"),
        ("api/v1/r.py", "from fastapi import *\n", "no-star-imports"),
        ("services/s.py", "import importlib\nimportlib.import_module('x')\n", "no-dynamic-imports"),
        ("services/s.py", "import importlib as il\nil.import_module('x')\n", "no-dynamic-imports"),
        ("services/s.py", "from importlib import import_module\n", "no-dynamic-imports"),
        ("api/v1/r.py", "m = __import__('os')\n", "no-dynamic-imports"),
        ("services/s.py", "import app.repositories\n", "services-no-http-or-concrete"),
        ("services/s.py", "from app import repositories\n", "services-no-http-or-concrete"),
        ("services/s.py", "from app import core\n", "services-no-http-or-concrete"),
        ("services/s.py", "from app import portal\n", "services-no-http-or-concrete"),
        ("portal/p.py", "from app import core\n", "portal-isolated"),
        ("portal/p.py", "import app.core\n", "portal-isolated"),
        ("api/v1/r.py", "from app import repositories\n", "api-no-data-access"),
        ("domain/m.py", "from app import core\n", "domain-pure"),
        ("api/v1/r.py", "from app.core import clock\n", "clock-wired-in-deps"),
    ],
)
def test_bypasses_closed(tmp_path: Path, path: str, src: str, rule: str) -> None:
    assert rule in _rules(_pkg(tmp_path, {path: src}))


def test_interfaces_still_allowed_via_from_import(tmp_path: Path) -> None:
    root = _pkg(
        tmp_path,
        {
            "services/s.py": "from app.core import interfaces\n",
            "portal/p.py": "from app.core import interfaces\n",
        },
    )
    assert check(root) == []


def test_deps_may_import_clock(tmp_path: Path) -> None:
    root = _pkg(tmp_path, {"core/deps.py": "from app.core.clock import SystemClock\n"})
    assert check(root) == []


def test_syntax_error_is_reported_not_raised(tmp_path: Path) -> None:
    root = _pkg(tmp_path, {"services/s.py": "def (:\n"})
    vs = check(root)
    assert [v.rule for v in vs] == ["syntax-error"]
    assert "syntax error" in str(vs[0])


def test_violation_path_is_repo_relative_for_real_layout(tmp_path: Path) -> None:
    root = tmp_path / "backend" / "app"
    (root / "api").mkdir(parents=True)
    (root / "api" / "x.py").write_text("import app.repositories\n")
    assert str(check(root)[0]).startswith("backend/app/api/x.py:1:")

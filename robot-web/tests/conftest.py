import os
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from autoweb.navigateur import VAR_EXECUTABLE  # noqa: E402

# Dans l'environnement de test, un chromium peut être fourni hors de Playwright.
_CHROMIUM_LOCAL = Path("/opt/pw-browsers/chromium")
if VAR_EXECUTABLE not in os.environ and _CHROMIUM_LOCAL.exists():
    os.environ[VAR_EXECUTABLE] = str(_CHROMIUM_LOCAL)


def navigateur_disponible() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            executable = os.environ.get(VAR_EXECUTABLE)
            b = p.chromium.launch(executable_path=executable) if executable else p.chromium.launch()
            b.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def navigateur_ok():
    if not navigateur_disponible():
        pytest.skip("aucun navigateur Chromium disponible pour les tests de bout en bout")
    return True


@pytest.fixture
def dossier_modeles() -> Path:
    return RACINE / "autoweb" / "modeles"

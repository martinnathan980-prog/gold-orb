"""Le fichier requirements.txt doit installer un Playwright utilisable partout,
y compris sur les Mac en macOS 12 où les versions récentes n'ont plus de navigateur."""

from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
packaging = pytest.importorskip("packaging.requirements")
from packaging.requirements import Requirement  # noqa: E402

# platform_release = version du noyau Darwin : 21.x = macOS 12, 22.x = macOS 13
ENVIRONNEMENTS = {
    "mac12 (Monterey)": {"sys_platform": "darwin", "platform_release": "21.6.0", "os_name": "posix"},
    "mac13 (Ventura)": {"sys_platform": "darwin", "platform_release": "22.6.0", "os_name": "posix"},
    "mac récent": {"sys_platform": "darwin", "platform_release": "25.1.0", "os_name": "posix"},
    "windows": {"sys_platform": "win32", "platform_release": "10", "os_name": "nt"},
    "linux": {"sys_platform": "linux", "platform_release": "6.1.0", "os_name": "posix"},
}


def exigences():
    for ligne in (RACINE / "requirements.txt").read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#"):
            yield Requirement(ligne)


def test_une_seule_version_de_playwright_par_systeme():
    for nom, env in ENVIRONNEMENTS.items():
        retenues = [r for r in exigences() if r.name == "playwright" and (r.marker is None or r.marker.evaluate(env))]
        assert len(retenues) == 1, f"{nom} : {len(retenues)} ligne(s) playwright retenue(s)"
        specificateur = str(retenues[0].specifier)
        if nom.startswith("mac12"):
            assert specificateur == "==1.57.0", f"{nom} attend Playwright 1.57 (dernier navigateur macOS 12)"
        else:
            assert ">=" in specificateur


def test_les_autres_bibliotheques_sont_toujours_installees():
    for nom, env in ENVIRONNEMENTS.items():
        noms = {r.name for r in exigences() if r.marker is None or r.marker.evaluate(env)}
        assert {"openpyxl", "PyYAML", "pypdf", "python-docx"} <= noms, nom

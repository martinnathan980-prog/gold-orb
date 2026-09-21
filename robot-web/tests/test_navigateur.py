"""Choix du navigateur : ordre des candidats et détection des navigateurs installés."""

import os
from pathlib import Path

import pytest

from autoweb import navigateur as N
from autoweb.erreurs import ErreurAutoweb
from autoweb.navigateur import VAR_EXECUTABLE, Navigateur
from autoweb.scenario import ConfigNavigateur


@pytest.fixture
def sans_variable(monkeypatch):
    monkeypatch.delenv(VAR_EXECUTABLE, raising=False)


def _nav(canal="auto", executable=None):
    return Navigateur(ConfigNavigateur(canal=canal, executable=executable), Path("."))


def test_variable_denvironnement_prioritaire(monkeypatch):
    monkeypatch.setenv(VAR_EXECUTABLE, "/chemin/vers/navigateur")
    assert _nav().  _candidats() == [("executable", "/chemin/vers/navigateur")]


def test_auto_essaie_chrome_puis_edge_puis_chromium(sans_variable, monkeypatch):
    monkeypatch.setattr(N.Navigateur, "_chemins_connus", lambda self, canaux: [])
    assert _nav("auto")._candidats() == [("chrome", None), ("msedge", None), ("chromium", None)]


def test_auto_ajoute_les_navigateurs_installes(sans_variable, monkeypatch, tmp_path):
    chrome = tmp_path / "Google Chrome"
    brave = tmp_path / "Brave Browser"
    for f in (chrome, brave):
        f.write_text("")
    monkeypatch.setattr(N, "sys", type("s", (), {"platform": "darwin"}))
    monkeypatch.setattr(N, "CHEMINS_MAC", {
        "chrome": [str(chrome), "/absent/Chrome"],
        "msedge": ["/absent/Edge"],
        "chromium": [str(brave)],
    })
    candidats = _nav("auto")._candidats()
    assert candidats == [
        ("chrome", None), ("msedge", None),
        ("chrome", str(chrome)), ("chromium", str(brave)),
        ("chromium", None),
    ]


def test_canal_explicite_reste_sur_ce_canal(sans_variable, monkeypatch):
    monkeypatch.setattr(N.Navigateur, "_chemins_connus", lambda self, canaux: [("chrome", "/x")])
    assert _nav("chrome")._candidats() == [("chrome", None), ("chrome", "/x")]
    assert _nav("chromium")._candidats() == [("chromium", None)]


def test_message_d_erreur_adapte_au_systeme(sans_variable, monkeypatch):
    nav = _nav("auto")
    for plateforme, attendu in (("darwin", "google.com/chrome"), ("win32", "chrome.exe"), ("linux", "playwright install")):
        monkeypatch.setattr(N, "sys", type("s", (), {"platform": plateforme}))
        assert attendu in nav._pistes()


def test_aucun_navigateur_message_complet(sans_variable, monkeypatch):
    monkeypatch.setattr(N.Navigateur, "_chemins_connus", lambda self, canaux: [])
    monkeypatch.setattr(N, "sys", type("s", (), {"platform": "darwin"}))

    class _FauxPw:
        class chromium:
            @staticmethod
            def launch(**kw):
                raise N.PlaywrightError("Chromium distribution 'chrome' is not found at /Applications/...")

            @staticmethod
            def launch_persistent_context(**kw):
                raise N.PlaywrightError("Chromium distribution 'chrome' is not found at /Applications/...")

    nav = _nav("auto")
    nav._pw = _FauxPw()
    with pytest.raises(ErreurAutoweb) as exc:
        nav._lancer()
    message = str(exc.value)
    assert "Aucun navigateur n'a pu être lancé" in message
    assert "google.com/chrome" in message and "macOS 12" in message
    assert "C:\\Program Files" not in message  # plus de chemins Windows sur un Mac

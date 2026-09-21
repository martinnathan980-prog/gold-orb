import datetime as dt

import pytest

from autoweb.erreurs import ErreurGabarit
from autoweb.gabarit import est_vrai, formater, manquants, noms_utilises, rendre, rendre_structure


def test_rendu_simple_et_tolerance_accents_casse():
    ctx = {"Numéro plan": "PL-1", "Titre": " Rez  "}
    assert rendre("{{Numéro plan}} / {{numero plan}} / {{ NUMÉRO PLAN }}", ctx) == "PL-1 / PL-1 / PL-1"
    assert rendre("{{Titre}}", ctx) == "Rez"  # espaces retirés
    assert rendre("sans gabarit", ctx) == "sans gabarit"


def test_formatage_valeurs_excel():
    assert formater(None) == ""
    assert formater(5.0) == "5"
    assert formater(5.5) == "5.5"
    assert formater(True) == "oui"
    assert formater(dt.datetime(2026, 9, 21)) == "21/09/2026"
    assert formater(dt.datetime(2026, 9, 21, 14, 30)) == "21/09/2026 14:30"
    assert formater(dt.date(2026, 1, 2)) == "02/01/2026"


def test_filtres():
    ctx = {"Date": dt.datetime(2026, 9, 21), "Nb": 12.0, "Texte": "abc", "Vide": None, "Prix": 3.14159,
           "DateTexte": "2026-09-21", "Oui": "x"}
    assert rendre("{{Date | date:%Y-%m-%d}}", ctx) == "2026-09-21"
    assert rendre("{{DateTexte | date:%d/%m/%Y}}", ctx) == "21/09/2026"
    assert rendre("{{Nb | entier}}", ctx) == "12"
    assert rendre("{{Prix | nombre:2}}", ctx) == "3.14"
    assert rendre("{{Prix | nombre:1 | virgule}}", ctx) == "3,1"
    assert rendre("{{Texte | majuscules}}", ctx) == "ABC"
    assert rendre("{{Vide | defaut:RAS}}", ctx) == "RAS"
    assert rendre("{{Inconnue | defaut:rien}}", ctx) == "rien"
    assert rendre("{{Texte | tronquer:2}}", ctx) == "ab"
    assert rendre("{{Oui | ouinon}}", ctx) == "oui"
    assert rendre("{{Vide | ouinon}}", ctx) == "non"


def test_colonne_absente_message_utile():
    with pytest.raises(ErreurGabarit) as exc:
        rendre("{{Inconnue}}", {"Titre": "x"})
    assert "Inconnue" in str(exc.value) and "Titre" in str(exc.value)
    # mode non strict : le gabarit est laissé tel quel
    assert rendre("{{Inconnue}}", {"Titre": "x"}, strict=False) == "{{Inconnue}}"


def test_filtre_inconnu():
    with pytest.raises(ErreurGabarit):
        rendre("{{Titre | nimportequoi}}", {"Titre": "x"})


def test_est_vrai():
    for v in ("oui", "Oui", "x", "X", "1", 1, True, "vrai", "TRUE", "yes", "ok"):
        assert est_vrai(v), v
    for v in ("non", "", None, "0", 0, False, "faux", "no", "-"):
        assert not est_vrai(v), v
    assert est_vrai("peu importe")  # texte non vide = vrai


def test_rendre_structure_et_noms():
    structure = {"champs": {"#a": "{{A}}", "#b": "{{B | defaut:x}}"}, "liste": ["{{C}}", 3]}
    assert noms_utilises(structure) == {"A", "B", "C"}
    assert manquants(structure, ["a", "c"]) == set()  # B a un defaut, A/C présents (insensible à la casse)
    assert manquants(structure, ["A"]) == {"C"}
    rendu = rendre_structure(structure, {"A": 1, "C": "z"})
    assert rendu == {"champs": {"#a": "1", "#b": "x"}, "liste": ["z", 3]}

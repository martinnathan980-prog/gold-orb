"""Où atterrissent les fichiers : tâches, exports, chemins collés depuis l'explorateur."""

from pathlib import Path

from autoweb import cli
from autoweb.assistant import Dialogue, construire_depuis_enregistrement
from autoweb.enregistreur import EtapeEnregistree


def test_nettoyer_chemin_enleve_les_guillemets_de_windows():
    assert cli.nettoyer_chemin('"C:\\Users\\moi\\mon fichier.xlsx"') == "C:\\Users\\moi\\mon fichier.xlsx"
    assert cli.nettoyer_chemin("  suivi.xlsx  ") == "suivi.xlsx"
    assert cli.nettoyer_chemin("'/tmp/a b.xlsx'") == "/tmp/a b.xlsx"
    assert cli.nettoyer_chemin("") == ""


def test_les_taches_sont_rangees_la_ou_le_menu_les_retrouve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # l'utilisateur peut être n'importe où
    chemin = cli._chemin_scenario("export des plans", str(tmp_path / "ailleurs" / "suivi.xlsx"), None, False)
    assert chemin.parent == cli.DOSSIER_PROJET / "taches"
    assert chemin.name == "export_des_plans.yaml"


def test_deux_enregistrements_du_meme_nom_ne_s_ecrasent_pas(tmp_path):
    sortie = tmp_path / "tache.yaml"
    sortie.write_text("etapes: []", encoding="utf-8")
    autre = cli._chemin_scenario("tache", None, str(sortie), False)
    assert autre != sortie and autre.stem.startswith("tache-")
    assert cli._chemin_scenario("tache", None, str(sortie), True) == sortie  # --ecraser


def test_les_fichiers_telecharges_arrivent_a_cote_de_l_excel(tmp_path):
    etapes = [
        EtapeEnregistree("aller", {"url": "https://outil/x"}),
        EtapeEnregistree("telecharger", {"cliquer": "role=button:Exporter", "nom_propose": "export.csv"},
                         libelle="Exporter"),
    ]
    dossier_excel = tmp_path / "Documents"
    dossier_excel.mkdir()
    texte = construire_depuis_enregistrement(
        etapes, ["Contrat"], [{"Contrat": "HDK"}],
        Dialogue(["", "", "", "", "", "n", "n"]), nom="export",
        fichier_excel=str(dossier_excel / "suivi.xlsx"), canal="chrome",
        url_depart="https://outil/x", dossier_exports=str(dossier_excel / "exports"),
    )
    attendu = str(dossier_excel / "exports") + "/"
    assert f'vers: "{attendu}"' in texte, texte
    assert 'renommer: "export_{{Contrat}}"' in texte and "convertir_excel: true" in texte

"""La commande releve photographie la page de démo et propose des sélecteurs corrects."""

import shutil
from pathlib import Path

import yaml

from autoweb.cli import main
from autoweb.scenario import charger


def test_releve_sur_la_demo(tmp_path, dossier_modeles, navigateur_ok, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    shutil.copyfile(dossier_modeles / "formulaire_demo.html", tmp_path / "formulaire_demo.html")
    url = (tmp_path / "formulaire_demo.html").resolve().as_uri()
    code = main(["releve", url, "--cache", "--sans-pause", "--nom", "demo plans", "--sortie", "releves"])
    sortie = capsys.readouterr().out
    assert code == 0, sortie
    dossiers = list((tmp_path / "releves").iterdir())
    assert len(dossiers) == 1
    dossier = dossiers[0]
    assert dossier.name.endswith("-demo_plans")
    for nom in ("capture.png", "page.html", "champs.txt", "brouillon.yaml"):
        assert (dossier / nom).exists(), nom

    champs = (dossier / "champs.txt").read_text(encoding="utf-8")
    assert "-> sélecteur : #numero" in champs
    assert "libellé « Numéro de plan" in champs
    assert "-> sélecteur : #type" in champs and "ARC | Architecture" in champs
    assert "-> sélecteur : role=button:Enregistrer" in champs
    assert "-> sélecteur : #btn-connexion" in champs
    assert "input checkbox" in champs
    assert "(masqué)" in champs  # le formulaire est caché tant qu'on n'est pas connecté

    brouillon = (dossier / "brouillon.yaml").read_text(encoding="utf-8")
    donnees = yaml.safe_load(brouillon)
    assert donnees["nom"] == "demo plans" and donnees["navigateur"]["canal"] == "chrome"
    # la page non connectée n'affiche que la connexion : champs visibles = identifiant / mot de passe
    assert '"#utilisateur"' in brouillon and "{{Identifiant ?}}" in brouillon
    assert "{{mot_de_passe}}" in brouillon
    assert "pause:" in brouillon
    assert "# - cliquer: \"#btn-connexion\"" in brouillon
    # le brouillon est un scénario valide (structure), prêt à être complété
    (tmp_path / "brouillon.yaml").write_text(brouillon, encoding="utf-8")
    scenario = charger(tmp_path / "brouillon.yaml")
    assert scenario.etapes[0].action == "aller"

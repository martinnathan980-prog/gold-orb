from pathlib import Path

import pytest
import yaml

from autoweb.erreurs import ErreurScenario
from autoweb.scenario import Etape, charger, depuis_dict, toutes_les_etapes


def _scenario(tmp_path, texte: str):
    chemin = tmp_path / "s.yaml"
    chemin.write_text(texte, encoding="utf-8")
    return charger(chemin)


def test_chargement_demo(dossier_modeles):
    s = charger(dossier_modeles / "demo.yaml")
    assert s.nom.startswith("Démo")
    assert s.excel.fichier == "demo_suivi.xlsx" and s.excel.feuille == "Plans"
    assert s.navigateur.canal == "auto"
    actions = [e.action for e in s.etapes]
    assert actions == ["aller", "attendre", "remplir", "choisir", "cocher", "cliquer", "verifier", "lire", "capture"]
    assert s.etapes[0].args == {"fichier": "formulaire_demo.html"}
    assert "champs" in s.etapes[2].args and "#numero" in s.etapes[2].args["champs"]
    assert s.avant[1].action == "si" and s.avant[1].args["alors"][0].action == "remplir"
    assert len(toutes_les_etapes(s.avant)) == 5


def test_modele_scenario_valide(dossier_modeles):
    texte = (dossier_modeles / "modele_scenario.yaml").read_text(encoding="utf-8")
    texte = texte.replace("__NOM__", "Test").replace("__EXCEL__", "suivi.xlsx").replace("__PROFIL__", "profils/test")
    s = depuis_dict(yaml.safe_load(texte), Path("modele.yaml"))
    assert s.navigateur.profil == "profils/test"
    assert any(e.action == "pause" for e in toutes_les_etapes(s.avant))


def test_formes_courtes_et_alias(tmp_path):
    s = _scenario(tmp_path, """
etapes:
  - goto: "https://exemple.fr"
  - click: "#ok"
  - attendre: 500
  - press: Enter
  - screenshot: "x.png"
  - recharger
  - fill: {"#a": "1", "#b": "2"}
  - saisir: {selecteur: "#c", valeur: "3"}
  - remplir:
      - {selecteur: "#d", valeur: "4"}
  - verifier_url: "/plans"
  - onglet: dernier
  - cliquer: "#x"
    nom: "Valider"
    optionnel: oui
    delai_max: 3000
""")
    actions = [e.action for e in s.etapes]
    assert actions == ["aller", "cliquer", "attendre", "touche", "capture", "recharger", "remplir", "remplir",
                       "remplir", "verifier_url", "onglet", "cliquer"]
    assert s.etapes[0].args == {"url": "https://exemple.fr"}
    assert s.etapes[2].args == {"ms": 500}
    assert s.etapes[6].args == {"champs": {"#a": "1", "#b": "2"}}
    assert s.etapes[7].args == {"selecteur": "#c", "valeur": "3"}
    assert s.etapes[8].args == {"champs": {"#d": "4"}}
    assert s.etapes[9].args == {"contient": "/plans"}
    derniere = s.etapes[-1]
    assert derniere.nom == "Valider" and derniere.optionnel and derniere.delai_max == 3000


@pytest.mark.parametrize("texte, attendu", [
    ("etapes:\n  - clicker: '#a'\n", "cliquer"),                       # suggestion de correction
    ("etapes:\n  - remplir: '#a'\n", "dictionnaire"),                   # forme courte interdite
    ("etapes:\n  - lire: {selecteur: '#a'}\n", "vers"),                 # paramètre manquant
    ("etapes:\n  - cliquer: '#a'\n    remplir: {}\n", "une seule action"),
    ("etapes:\n  - si: {alors: []}\n", "condition"),
    ("etapes:\n  - cadre: '#iframe'\n", "etapes"),
    ("etapes: []\n", "vide"),
    ("navigateur: {canal: firefox}\netapes:\n  - recharger\n", "firefox"),
    ("navigateurs: {}\netapes:\n  - recharger\n", "navigateur"),
    ("excel: {fichier: a.xlsx, feuil: x}\netapes:\n  - recharger\n", "feuille"),
    ("etapes:\n  - aller: {fichier: x}\n    optionnel: peut-etre\n", "oui/non"),
])
def test_erreurs_de_scenario(tmp_path, texte, attendu):
    with pytest.raises(ErreurScenario) as exc:
        _scenario(tmp_path, texte)
    assert attendu in str(exc.value)


def test_yaml_invalide_et_fichier_absent(tmp_path):
    with pytest.raises(ErreurScenario, match="introuvable"):
        charger(tmp_path / "absent.yaml")
    with pytest.raises(ErreurScenario, match="YAML"):
        _scenario(tmp_path, "etapes: [\n  - aller: x")


def test_masquage_des_secrets(tmp_path):
    from autoweb.gabarit import rendre_structure
    from autoweb.scenario import MASQUE, masquer_secrets

    s = _scenario(tmp_path, """
etapes:
  - remplir:
      "#utilisateur": "{{Utilisateur}}"
      "#mot-de-passe": "{{Mdp}}"
      "input[name=password]": "abc"
      "#titre": "{{Titre}}"
  - remplir: {selecteur: "#code", valeur: "{{mot_de_passe}}"}
  - remplir: {selecteur: "#autre", valeur: "{{Titre}}"}
    secret: true
  - remplir: {selecteur: "#visible", valeur: "{{Titre}}"}
""")
    ctx = {"Utilisateur": "martin", "Mdp": "s3cret", "mot_de_passe": "xyz", "Titre": "Plan A"}
    rendus = [rendre_structure(e.args, ctx) for e in s.etapes]
    champs = masquer_secrets(rendus[0], s.etapes[0])["champs"]
    assert champs == {"#utilisateur": "martin", "#mot-de-passe": MASQUE, "input[name=password]": MASQUE, "#titre": "Plan A"}
    assert masquer_secrets(rendus[1], s.etapes[1])["valeur"] == MASQUE
    assert masquer_secrets(rendus[2], s.etapes[2])["valeur"] == MASQUE
    assert masquer_secrets(rendus[3], s.etapes[3])["valeur"] == "Plan A"
    resume = Etape(s.etapes[0].action, masquer_secrets(rendus[0], s.etapes[0])).resume()
    assert "s3cret" not in resume and "abc" not in resume and "martin" in resume


def test_suggestion_privilegie_le_francais(tmp_path):
    with pytest.raises(ErreurScenario) as exc:
        _scenario(tmp_path, "etapes:\n  - clicker: '#a'\n")
    assert "« cliquer »" in str(exc.value)


def test_config_excel_et_navigateur(tmp_path):
    s = _scenario(tmp_path, """
navigateur:
  canal: edge
  visible: non
  profil: profils/x
  attacher: 9222
  delai_max: 20000
  dialogues: refuser
excel:
  fichier: suivi.xlsx
  ligne_entete: 3
  traiter_si: "A faire"
  colonne_statut: Etat
etapes:
  - recharger
""")
    assert s.navigateur.canal == "msedge" and s.navigateur.visible is False
    assert s.navigateur.attacher == "9222" and s.navigateur.dialogues == "refuser"
    assert s.excel.ligne_entete == 3 and s.excel.traiter_si == ["A faire"] and s.excel.colonne_statut == "Etat"

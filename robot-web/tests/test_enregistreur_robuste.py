"""Cas difficiles de l'enregistrement, tous rencontrés sur de vrais outils :
iframe, mot de passe sans étiquette, champ à suggestions, tableau de résultats,
touche Entrée après la frappe.
"""

from pathlib import Path

import pytest
import yaml

from autoweb.assistant import Dialogue, construire_depuis_enregistrement
from autoweb.cli import _servir_dossier
from autoweb.enregistreur import Enregistreur, remplacer_texte_selecteur
from autoweb.erreurs import ErreurAutoweb
from autoweb.navigateur import Navigateur
from autoweb.scenario import ConfigNavigateur, charger

PAGE = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Outil difficile</title></head>
<body>
  <h1>Outil</h1>
  <!-- un mot de passe sans id, sans name, sans label : cas du formulaire « maison » -->
  <div><input type="password" placeholder="Mot de passe"></div>
  <div><input type="password" name="ged_pwd"></div>
  <div><input type="text" name="otp_code" placeholder="Code reçu par SMS"></div>

  <!-- champ à suggestions : aucun événement « change » n'est émis -->
  <label for="client">Client</label>
  <input id="client" autocomplete="off">
  <ul id="suggestions"><li id="sugg1">Dupont Jean</li></ul>

  <label for="recherche">Recherche</label>
  <input id="recherche">

  <table><tbody>
    <tr><td>HDK-001</td><td><button aria-label="Telecharger">T</button><button aria-label="Supprimer">S</button></td></tr>
    <tr><td>HDK-002</td><td><button aria-label="Telecharger">T</button><button aria-label="Supprimer">S</button></td></tr>
  </tbody></table>

  <textarea id="commentaire"></textarea>
  <iframe id="cadre1" src="interieur.html" style="width:300px;height:120px"></iframe>
<script>
  document.getElementById('sugg1').addEventListener('click', function () {
    document.getElementById('client').value = 'Dupont Jean';
  });
</script>
</body></html>
"""

PAGE_INTERIEURE = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"></head>
<body><button id="dans-le-cadre">Valider dans le cadre</button></body></html>
"""


@pytest.fixture
def site(tmp_path):
    (tmp_path / "difficile.html").write_text(PAGE, encoding="utf-8")
    (tmp_path / "interieur.html").write_text(PAGE_INTERIEURE, encoding="utf-8")
    serveur, url = _servir_dossier(tmp_path, "difficile.html", port=0)
    try:
        yield tmp_path, url
    finally:
        serveur.shutdown()
        serveur.server_close()


def _enregistrer(dossier: Path, url: str, actions):
    nav = Navigateur(ConfigNavigateur(canal="auto", visible=False), dossier, visible=False)
    nav.ouvrir()
    enregistreur = Enregistreur(nav)
    try:
        page = enregistreur.demarrer(url)   # ne doit pas se bloquer malgré l'iframe
        page.wait_for_selector("#__autoweb_badge")
        actions(page)
        page.wait_for_timeout(900)
        return enregistreur.arreter()
    finally:
        nav.fermer()


def test_iframe_ne_bloque_pas_et_est_reperee(site, navigateur_ok):
    """Une iframe figeait tout le programme : le sélecteur du cadre est résolu à la fin."""
    dossier, url = site

    def tache(page):
        page.frame_locator("#cadre1").locator("#dans-le-cadre").click()
        page.fill("#recherche", "apres le cadre")

    etapes = _enregistrer(dossier, url, tache)
    dans_cadre = [e for e in etapes if e.cadre]
    assert dans_cadre, [(e.action, e.args, e.cadre) for e in etapes]
    assert dans_cadre[0].args["selecteur"] == "#dans-le-cadre"
    assert dans_cadre[0].cadre == "#cadre1"
    # ce qui suit, hors du cadre, est bien enregistré aussi
    assert any(e.action == "remplir" and e.args["selecteur"] == "#recherche" for e in etapes)


def test_mot_de_passe_jamais_dans_le_selecteur_ni_dans_le_libelle(site, navigateur_ok):
    dossier, url = site
    secret = "Secret-Bureau-2026!"

    def tache(page):
        page.fill("input[type=password] >> nth=0", secret)
        page.fill("input[name=ged_pwd]", "AutreSecret")

    etapes = _enregistrer(dossier, url, tache)
    saisies = [e for e in etapes if e.action == "remplir"]
    assert len(saisies) == 2
    for etape in saisies:
        assert secret not in etape.args["selecteur"]
        assert secret not in etape.libelle
        assert secret not in etape.resume() and "AutreSecret" not in etape.resume()

    # deux mots de passe distincts -> deux variables distinctes, aucune valeur écrite
    texte = construire_depuis_enregistrement(
        etapes, [], [], Dialogue(["", "n", "", "n", "n"]), nom="connexion",
        fichier_excel="suivi.xlsx", canal="chromium", url_depart=url,
    )
    assert secret not in texte and "AutreSecret" not in texte
    assert "{{mot_de_passe}}" in texte and "{{mot_de_passe_2}}" in texte
    donnees = yaml.safe_load(texte)
    assert donnees["variables"]["mot_de_passe"] == "" and donnees["variables"]["mot_de_passe_2"] == ""


def test_code_a_usage_unique_devient_une_pause(site, navigateur_ok):
    dossier, url = site

    def tache(page):
        page.fill("input[name=otp_code]", "123456")
        page.fill("#recherche", "x")

    etapes = _enregistrer(dossier, url, tache)
    texte = construire_depuis_enregistrement(
        etapes, [], [], Dialogue(["", "n", "", "n", "n"]), nom="avec code",
        fichier_excel="suivi.xlsx", canal="chromium", url_depart=url,
    )
    assert "123456" not in texte
    assert "Saisissez le code dans le navigateur" in texte


def test_champ_a_suggestions_et_touche_entree(site, navigateur_ok):
    """La frappe doit être notée AVANT le clic sur la suggestion et avant la touche Entrée."""
    dossier, url = site

    def tache(page):
        page.locator("#client").click()
        page.locator("#client").press_sequentially("Dup", delay=30)
        page.wait_for_timeout(800)          # le site n'émet pas « change »
        page.click("#sugg1")
        page.locator("#recherche").press_sequentially("plan", delay=30)
        page.keyboard.press("Enter")

    etapes = _enregistrer(dossier, url, tache)
    resume = [(e.action, e.args.get("selecteur"), e.args.get("valeur") or e.args.get("touche")) for e in etapes]
    assert ("remplir", "#client", "Dup") in resume, resume
    position_frappe = resume.index(("remplir", "#client", "Dup"))
    position_clic = [i for i, r in enumerate(resume) if r[0] == "cliquer"][0]
    assert position_frappe < position_clic
    # la frappe dans « recherche » précède la touche Entrée
    i_remplir = [i for i, r in enumerate(resume) if r[:2] == ("remplir", "#recherche")][0]
    i_touche = [i for i, r in enumerate(resume) if r[0] == "touche"][0]
    assert i_remplir < i_touche, resume


def test_clic_dans_un_tableau_est_ancre_sur_le_texte_de_la_ligne(site, navigateur_ok):
    """Sans ancre, le sélecteur viserait « la 2e ligne » et changerait de cible chaque jour."""
    dossier, url = site

    def tache(page):
        page.locator('tr:has-text("HDK-002") [aria-label="Telecharger"]').click()

    etapes = _enregistrer(dossier, url, tache)
    clic = [e for e in etapes if e.action == "cliquer"][0]
    selecteur = clic.args["selecteur"]
    assert 'tr:has-text("HDK-002")' in selecteur, selecteur
    assert '[aria-label="Telecharger"]' in selecteur
    assert "nth-of-type" not in selecteur
    assert clic.texte_selecteur == "HDK-002"
    # le texte est remplaçable par une colonne, et seul ce texte-là
    remplace = remplacer_texte_selecteur(selecteur, "HDK-002", "{{Numéro}}")
    assert 'tr:has-text("{{Numéro}}")' in remplace and '[aria-label="Telecharger"]' in remplace


def test_scenario_avec_mot_de_passe_est_accepte_par_verifier(site, navigateur_ok, capsys):
    """La variable de mot de passe doit être déclarée, sinon « verifier » la croit manquante."""
    from autoweb.cli import main
    from autoweb.excel import creer_classeur

    dossier, url = site
    creer_classeur(dossier / "suivi.xlsx", ["Contrat"], [["HDK"]], feuille="Suivi")

    def tache(page):
        page.fill("input[type=password] >> nth=0", "Secret2026")
        page.fill("#recherche", "HDK")

    etapes = _enregistrer(dossier, url, tache)
    texte = construire_depuis_enregistrement(
        etapes, ["Contrat"], [{"Contrat": "HDK"}], Dialogue(["", "n", "", "", "n", "n"]),
        nom="avec mot de passe", fichier_excel=str(dossier / "suivi.xlsx"), canal="chromium", url_depart=url,
    )
    chemin = dossier / "avec_mdp.yaml"
    chemin.write_text(texte, encoding="utf-8")
    capsys.readouterr()
    assert main(["verifier", str(chemin)]) == 0, capsys.readouterr().out
    sortie = capsys.readouterr().out
    assert "valide" in sortie and "absentes" not in sortie


def test_valeur_sur_plusieurs_lignes_et_scenario_vide(site, navigateur_ok):
    dossier, url = site

    def tache(page):
        page.fill("#commentaire", "Ligne une\nLigne deux")

    etapes = _enregistrer(dossier, url, tache)
    texte = construire_depuis_enregistrement(
        etapes, [], [], Dialogue(["", "", "n", "n"]), nom="commentaire",
        fichier_excel="suivi.xlsx", canal="chromium", url_depart=url,
    )
    donnees = yaml.safe_load(texte)  # doit rester du YAML valide
    remplir = [e["remplir"] for e in donnees["etapes"] if isinstance(e, dict) and "remplir" in e][0]
    assert remplir["valeur"] == "Ligne une\nLigne deux"
    (dossier / "c.yaml").write_text(texte, encoding="utf-8")
    scenario = charger(dossier / "c.yaml")
    assert scenario.etapes[-1].args["valeur"] == "Ligne une\nLigne deux"

    # si l'utilisateur retire toutes les actions, on refuse d'écrire une tâche qui ne fait rien
    with pytest.raises(ErreurAutoweb, match="aucune action"):
        construire_depuis_enregistrement(
            etapes, [], [], Dialogue(["1,2,3,4,5,6,7,8,9,10"]), nom="vide",
            fichier_excel="suivi.xlsx", canal="chromium", url_depart=url,
        )

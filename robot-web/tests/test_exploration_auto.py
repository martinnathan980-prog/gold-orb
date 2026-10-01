"""Carte faite par le robot tout seul, à partir de l'adresse : vieux portail ASP.NET où tout passe
par des envois de formulaire (menus, recherche, lignes, onglets). Le robot doit trouver la
recherche, la liste de résultats, la fiche d'un plan et ses onglets, sans JAMAIS envoyer une
suppression, une duplication ou une création. Puis une tâche écrite seulement avec les repères
du fichier à partager (carte=E2/C1...) doit marcher."""

import pytest

import portail_webforms as P
from autoweb import carte as module_carte
from autoweb.explorateur import Explorateur, Limites, corps_action, libelle_neutre
from autoweb.navigateur import Navigateur
from autoweb.runner import Options, lancer
from autoweb.scenario import ConfigNavigateur, charger

DANGEREUX = ("Delete%24", "Edit%24", "btnSupprimer", "btnDupliquer", "btnNouveau")


@pytest.fixture
def portail():
    serveur, url = P.demarrer()
    try:
        yield url
    finally:
        serveur.shutdown()
        serveur.server_close()


def _explorer(tmp_path, url, terme=""):
    cfg = ConfigNavigateur(canal="auto", visible=False, profil=str(tmp_path / "profil"), dialogues="ignorer")
    nav = Navigateur(cfg, tmp_path, visible=False)
    nav.options_lancement = {"handle_sigint": False}
    nav.options_contexte = {"service_workers": "block"}
    nav.ouvrir()
    robot = Explorateur(nav, tmp_path / "explorations" / "20261001-101500", Limites(minutes=5, delai_ms=0),
                        interactif=False, connexion=lambda page: None)
    robot.terme = terme
    try:
        robot.explorer(url)
    finally:
        nav.fermer()
    return robot


def test_carte_toute_seule_d_un_portail_a_formulaires(portail, tmp_path, navigateur_ok):
    robot = _explorer(tmp_path, portail)
    titres = [(e.titres or [e.titre])[0] for e in robot.ecrans]
    for attendu in ("Recherche de plans", "Recherche de composants", "Composants trouvés", "Fournisseurs"):
        assert attendu in titres, (attendu, titres)
    assert sum(t.startswith("Plan PL-") for t in titres) >= 3, titres  # la fiche et ses onglets (Révisions, Documents)
    # jamais une suppression, une duplication, une édition ni une création
    assert not [c for c in P.Portail.envois if any(x in c for x in DANGEREUX)]
    assert robot.complet
    partage = (tmp_path / "explorations" / "20261001-101500" / "carte_a_partager.txt").read_text(encoding="utf-8")
    assert "CARTE N° 20261001-101500" in partage
    assert "C1 Numéro [texte]" in partage and "K4 Rechercher" in partage
    assert "recherche : champ C1 « Numéro », bouton K4" in partage
    assert "Supprimer → non cliqué" in partage and "Poste source Nord" not in partage
    assert "DE CONSULTATION FAITS PAR LE ROBOT" in partage


def test_une_tache_ecrite_avec_les_reperes(portail, tmp_path, monkeypatch, navigateur_ok):
    """« ecran: E2 » revient sur la recherche de plans, C1 est le champ Numéro, K4 le bouton Rechercher :
    le robot traduit, sur le poste, chaque repère en élément exact."""
    _explorer(tmp_path, portail)
    monkeypatch.setattr(module_carte, "DOSSIER_EXPLORATIONS", tmp_path / "explorations")
    tache = tmp_path / "ouvrir_plan.yaml"
    tache.write_text("""nom: ouvrir un plan
navigateur: {canal: auto, visible: false, profil: profil}
questions: {numero: "Numéro du plan"}
etapes:
  - ecran: "carte=20261001-101500/E2"
  - remplir: {selecteur: "carte=20261001-101500/E2/C1", valeur: "{{numero}}"}
  - cliquer: "carte=E2/K4"
  - cliquer: "texte_exact={{numero}}"
  - verifier: {texte_page: "Plan {{numero}}"}
""", encoding="utf-8")
    bilan = lancer(charger(tache), Options(visible=False, interactif=False, variables={"numero": "PL-13"}))
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume()
    assert not [c for c in P.Portail.envois if any(x in c for x in DANGEREUX)]


def test_repere_inconnu_explique(tmp_path, monkeypatch):
    from autoweb.erreurs import ErreurEtape

    monkeypatch.setattr(module_carte, "DOSSIER_EXPLORATIONS", tmp_path)
    with pytest.raises(ErreurEtape, match="aucune carte"):
        module_carte.selecteur("carte=E2/C1")


@pytest.mark.parametrize("corps, coupe", [
    ("__VIEWSTATE=x&__EVENTTARGET=ctl00%24Menu&__EVENTARGUMENT=Plans", False),
    ("__EVENTTARGET=ctl00%24Main%24gv&__EVENTARGUMENT=Select%240", False),
    ("__EVENTTARGET=&ctl00%24Main%24txtNum=PL&ctl00%24Main%24btnRechercher=Rechercher", False),
    ("__EVENTTARGET=ctl00%24gv&__EVENTARGUMENT=Sort%24DateModification", False),
    ('{"q": "pompe", "page": 2}', False),
    ("__EVENTTARGET=ctl00%24Main%24gv&__EVENTARGUMENT=Delete%240", True),
    ("__EVENTTARGET=ctl00%24Main%24btnSupprimer&__EVENTARGUMENT=", True),
    ("ctl00%24Main%24btnSave=Enregistrer", True),
    ('{"query": "mutation { deletePlan(id: 5) }"}', True),
    ('{"action": "delete", "id": 5}', True),
    ("action=supprimer&ids=5", True),
])
def test_envois_permis_ou_coupes(corps, coupe):
    assert bool(corps_action(corps, "application/x-www-form-urlencoded")) == coupe, corps


def test_libelles_neutres():
    for texte in ("Historique", "Plan de masse", "Nomenclature", "Documents liés", "Cas d'emploi", "Structure"):
        assert libelle_neutre(texte), texte
    for texte in ("Basculer", "Rattacher", "Transmettre", "Release", "Nouveau", "Réviser", "Copy", "Associer"):
        assert not libelle_neutre(texte), texte


def test_menu_8_le_robot_explore_seul_et_retient_l_adresse(tmp_path, monkeypatch):
    from autoweb import cli

    appels = []
    monkeypatch.setattr(cli, "cmd_explorer", lambda args: appels.append(args) or 0)
    monkeypatch.setattr(cli, "FICHIER_PORTAIL", tmp_path / "portail.txt")
    reponses = iter(["8", "https://portail.entreprise.fr/accueil", "8", "", "8v", "", "0"])
    monkeypatch.setattr("builtins.input", lambda *a: next(reponses))
    cli.cmd_menu(cli._ns())
    assert [a.url for a in appels] == ["https://portail.entreprise.fr/accueil"] * 3  # Entrée : la même adresse
    assert [a.visite for a in appels] == [False, False, True]  # 8 : le robot seul ; 8v : visite guidée


def test_ajouter_une_tache_ecrite_par_claude(tmp_path, monkeypatch):
    from autoweb import cli
    from autoweb.erreurs import ErreurAutoweb

    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path / "robot-web")
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    recus = tmp_path / "Downloads"
    recus.mkdir()
    (recus / "tache_chercher_un_plan.txt").write_text(
        "nom: chercher un plan\nnavigateur: {profil: robot}\nquestions: {numero: Numéro du plan}\n"
        "etapes:\n  - ecran: \"carte=E2\"\n  - remplir: {selecteur: \"carte=E2/C1\", valeur: \"{{numero}}\"}\n",
        encoding="utf-8")
    (recus / "A_ENVOYER_A_CLAUDE_20261001.txt").write_text("etapes:\n", encoding="utf-8")  # jamais proposé
    monkeypatch.setattr("builtins.input", lambda *a: "1")
    assert cli.cmd_ajouter(cli._ns(fichier=None)) == 0
    assert (tmp_path / "robot-web" / "taches" / "chercher_un_plan.yaml").is_file()

    (recus / "tache_cassee.txt").write_text("nom: cassée\netapes:\n  - voler: oui\n", encoding="utf-8")
    with pytest.raises(ErreurAutoweb, match="contient une erreur"):
        cli.cmd_ajouter(cli._ns(fichier=str(recus / "tache_cassee.txt")))
    assert [f.name for f in (tmp_path / "robot-web" / "taches").iterdir()] == ["chercher_un_plan.yaml"]

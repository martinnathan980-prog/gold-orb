"""Onglets que Chrome ouvre de lui-même (session précédente, nouveautés, page Google...).

Ils passaient devant l'onglet du robot : pendant l'enregistrement l'utilisateur
travaillait dedans, et à la relance le robot « était sur Google ».
"""

import json
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from autoweb import navigateur as nav_mod
from autoweb.enregistreur import Enregistreur, Evenement, est_hors_tache
from autoweb.navigateur import Navigateur, adresse_courte, est_onglet_parasite, est_onglet_vide
from autoweb.scenario import ConfigNavigateur


# ---------------------------------------------------------------------- reconnaissance des adresses
@pytest.mark.parametrize("url", [
    "chrome://whats-new/",
    "chrome://welcome/",
    "chrome://intro",
    "https://www.google.com/chrome/whats-new/?version=141",
    "https://www.google.fr/intl/fr_fr/chrome/",
    "https://www.google.com/chrome",
])
def test_onglets_parasites_reconnus(url):
    assert est_onglet_parasite(url)


@pytest.mark.parametrize("url", [
    "https://accounts.google.com/signin",      # connexion d'entreprise par Google : jamais fermée
    "https://docs.google.com/spreadsheets/d/1",
    "https://www.google.fr/",                  # accueil Google : filtré à l'enregistrement, pas fermé
    "chrome://newtab/",                        # Ctrl+T de l'utilisateur
    "http://intranet/outil/chrome/plan",       # « chrome » dans l'adresse d'un outil
    "https://outil.exemple/",
])
def test_onglets_legitimes_non_fermes(url):
    assert not est_onglet_parasite(url)


def test_onglet_vide():
    assert est_onglet_vide("") and est_onglet_vide("about:blank") and est_onglet_vide("chrome://newtab/")
    assert not est_onglet_vide("https://outil.exemple/")


def test_adresse_courte_ne_montre_pas_les_jetons():
    assert adresse_courte("https://www.google.com/chrome/whats-new/?jeton=SECRET#x") == "www.google.com/chrome/whats-new/"


@pytest.mark.parametrize("url, attendu", [
    ("https://www.google.fr/", True),
    ("https://www.google.com/search?q=mon+outil", True),
    ("https://consent.google.fr/ml?continue=x", True),
    ("chrome://whats-new/", True),
    ("about:blank", True),
    ("https://outil.exemple/plans", False),
    ("https://accounts.google.com/o/oauth2", False),   # connexion : fait partie de la tâche
    ("https://docs.google.com/document/d/1", False),
    ("", False),
])
def test_pages_hors_tache(url, attendu):
    assert est_hors_tache(url, "https://outil.exemple/") is attendu


def test_rien_n_est_filtre_quand_l_outil_est_chez_google():
    assert not est_hors_tache("https://www.google.com/search?q=x", "https://www.google.com/")


class _FauxNav:
    parasites: list = []


def test_evenements_hors_tache_ecartes_et_adresses_jamais_gardees():
    enregistreur = Enregistreur(_FauxNav())
    enregistreur.url_depart = "https://outil.exemple/"
    clic_google = {"selecteur": "#L2AGLb", "tag": "button", "url": "https://consent.google.fr/x",
                   "url_page": "https://consent.google.fr/x"}
    clic_outil = {"selecteur": "#chercher", "tag": "button", "url": "https://outil.exemple/p?jeton=SECRET",
                  "url_page": "https://outil.exemple/p?jeton=SECRET"}
    # iframe d'une autre origine dans l'outil : la page principale est inconnue, on garde
    clic_cadre = {"selecteur": "#ok", "tag": "button", "url": "https://autre.exemple/cadre", "url_page": ""}
    enregistreur.evenements = [
        Evenement("page", {"url": "https://outil.exemple/", "titre": ""}),
        Evenement("clic", clic_google),
        Evenement("clic", clic_outil),
        Evenement("clic", clic_cadre),
    ]
    etapes = enregistreur.arreter()
    assert enregistreur.ignorees == 1
    assert [e.action for e in etapes] == ["aller", "cliquer", "cliquer"]
    assert etapes[0].args["url"] == "https://outil.exemple/"
    assert [e.args["selecteur"] for e in etapes[1:]] == ["#chercher", "#ok"]
    assert "SECRET" not in repr([e.args for e in etapes])


# ---------------------------------------------------------------------- vrai navigateur
class _Silencieux(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def site(tmp_path):
    (tmp_path / "outil.html").write_text(
        "<title>Outil</title><h1>Outil</h1>"
        "<a id=lien target=_blank href=fiche.html>fiche</a>"
        "<a id=simple href=fiche.html>simple</a>"
        "<button id=lanceur onclick=\"window.open('fiche.html','app','width=600');window.close()\">lancer</button>"
        "<button id=chercher onclick=\"document.body.dataset.fait='1'\">Chercher</button>",
        encoding="utf-8")
    (tmp_path / "fiche.html").write_text("<title>Fiche</title>fiche", encoding="utf-8")
    (tmp_path / "promo.html").write_text("<title>Découvrez Google</title>promo", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        "<title>Google</title><button id=L2AGLb>Tout accepter</button>", encoding="utf-8")
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencieux, directory=str(tmp_path)))
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        yield tmp_path, f"http://127.0.0.1:{serveur.server_address[1]}"
    finally:
        serveur.shutdown()
        serveur.server_close()


def _ouvrir(dossier: Path, profil=None, arguments=None) -> Navigateur:
    cfg = ConfigNavigateur(canal="auto", visible=False, profil=profil)
    if arguments:
        cfg.arguments = arguments
    nav = Navigateur(cfg, dossier, visible=False)
    nav.ouvrir()
    return nav


def test_onglets_restaures_par_chrome_fermes_au_demarrage(site, tmp_path_factory, navigateur_ok):
    """Profil réglé sur « Continuer là où vous en étiez » : Chrome rouvre les onglets
    de la dernière fois. Le robot garde son onglet vide et ferme les autres."""
    dossier, base = site
    profil = tmp_path_factory.mktemp("profil")
    (profil / "Default").mkdir()
    (profil / "Default" / "Preferences").write_text(json.dumps({"session": {"restore_on_startup": 1}}))
    nav = _ouvrir(dossier, profil=str(profil))
    try:
        nav.page.goto(f"{base}/outil.html")
        autre = nav.contexte.new_page()
        autre.goto(f"{base}/promo.html")
        nav.page.wait_for_timeout(1500)  # le temps que Chrome enregistre la session
    finally:
        nav.fermer()

    nav = _ouvrir(dossier, profil=str(profil))
    try:
        ouvertes = [p for p in nav.contexte.pages if not p.is_closed()]
        assert ouvertes == [nav.page]
        assert nav.page.url == "about:blank"
        assert len(nav.parasites) >= 1  # Chrome avait bien rouvert des onglets
    finally:
        nav.fermer()


def test_onglet_tardif_de_chrome_ferme_mais_pas_les_fenetres_de_l_outil(site, tmp_path_factory, navigateur_ok):
    dossier, base = site
    port = base.rsplit(":", 1)[1]
    # profil conservé, comme pour une vraie tâche (et Target.createTarget y ouvre l'onglet) ;
    # « promo.exemple » : un autre site que l'outil, servi par le même petit serveur
    nav = _ouvrir(dossier, profil=str(tmp_path_factory.mktemp("profil")),
                  arguments=["--host-resolver-rules=MAP promo.exemple 127.0.0.1"])
    try:
        page = nav.page
        page.goto(f"{base}/outil.html")
        # un onglet ouvert par l'outil (lien target=_blank) : il a un « opener », on le garde
        with page.expect_popup() as info:
            page.click("#lien")
        fiche = info.value
        # un onglet ouvert par Chrome lui-même, sans opener (comme « Nouveautés »)
        cdp = nav.contexte.new_cdp_session(page)
        cdp.send("Target.createTarget", {"url": f"http://promo.exemple:{port}/promo.html"})
        for _ in range(20):
            page.wait_for_timeout(200)
            if nav.parasites:
                break
        assert [p.url for p in nav.parasites] == [f"http://promo.exemple:{port}/promo.html"]
        assert nav.parasites[0].is_closed()
        assert not fiche.is_closed()
        assert nav.page_courante() is page
    finally:
        nav.fermer()


def test_apres_le_demarrage_seuls_les_onglets_de_chrome_connus_sont_fermes(
        site, monkeypatch, tmp_path_factory, navigateur_ok):
    dossier, base = site
    monkeypatch.setattr(nav_mod, "FENETRE_DEMARRAGE_S", 0.0)
    nav = _ouvrir(dossier, profil=str(tmp_path_factory.mktemp("profil")))
    try:
        page = nav.page
        page.goto(f"{base}/outil.html")
        cdp = nav.contexte.new_cdp_session(page)
        cdp.send("Target.createTarget", {"url": f"{base}/fiche.html"})  # adresse ordinaire : gardée
        page.wait_for_timeout(1500)
        assert not nav.parasites
        monkeypatch.setattr(nav_mod, "MOTIF_ONGLET_PARASITE", nav_mod.re.compile(r".*/promo\.html$"))
        cdp.send("Target.createTarget", {"url": f"{base}/promo.html"})  # adresse connue : fermée
        for _ in range(20):
            page.wait_for_timeout(200)
            if nav.parasites:
                break
        assert [p.url for p in nav.parasites] == [f"{base}/promo.html"]
    finally:
        nav.fermer()


def test_clics_sur_google_ignores_pendant_l_enregistrement(site, navigateur_ok):
    """L'utilisateur passe par l'accueil Google (bandeau cookies) avant d'aller sur son outil."""
    dossier, base = site
    port = base.rsplit(":", 1)[1]
    nav = _ouvrir(dossier, arguments=[f"--host-resolver-rules=MAP www.google.fr 127.0.0.1:{port}"])
    enregistreur = Enregistreur(nav)
    try:
        page = enregistreur.demarrer("about:blank")
        page.goto("http://www.google.fr/")
        page.wait_for_selector("#__autoweb_badge")
        page.click("#L2AGLb")
        page.goto(f"{base}/outil.html")
        page.wait_for_selector("#__autoweb_badge")
        page.click("#chercher")
        page.wait_for_timeout(800)
        etapes = enregistreur.arreter()
    finally:
        nav.fermer()
    assert enregistreur.ignorees == 1
    assert [e.args.get("selecteur") for e in etapes if e.action == "cliquer"] == ["#chercher"]


# ---------------------------------------------------------------------- relecture de la revue
@pytest.mark.parametrize("comment", [dict(button="middle"), dict(modifiers=["ControlOrMeta"]), dict(modifiers=["Shift"])])
def test_onglet_ouvert_par_l_utilisateur_sur_l_outil_garde(site, tmp_path_factory, comment, navigateur_ok):
    """Clic molette, Ctrl+clic, Maj+clic : Chrome ouvre l'onglet sans « opener »,
    mais il est sur le site de l'outil : il fait partie de la tâche."""
    dossier, base = site
    nav = _ouvrir(dossier, profil=str(tmp_path_factory.mktemp("profil")))
    try:
        page = nav.page
        page.goto(f"{base}/outil.html")
        page.click("#simple", **comment)
        for _ in range(10):
            page.wait_for_timeout(200)
        ouvertes = [p.url for p in nav.contexte.pages if not p.is_closed()]
        assert f"{base}/fiche.html" in ouvertes and not nav.parasites
    finally:
        nav.fermer()


def test_application_ouverte_par_un_portail_qui_se_referme_gardee(site, tmp_path_factory, navigateur_ok):
    dossier, base = site
    nav = _ouvrir(dossier, profil=str(tmp_path_factory.mktemp("profil")))
    try:
        page = nav.page
        page.goto(f"{base}/outil.html")
        with page.expect_popup() as info:
            page.evaluate("window.open('outil.html')")
        portail = info.value
        portail.wait_for_load_state()
        portail.click("#lanceur")  # ouvre l'application puis se ferme aussitôt
        for _ in range(10):
            page.wait_for_timeout(200)
        ouvertes = [p.url for p in nav.contexte.pages if not p.is_closed()]
        assert f"{base}/fiche.html" in ouvertes and not nav.parasites
    finally:
        nav.fermer()


def test_pendant_une_pause_les_questions_de_l_outil_restent_a_l_utilisateur(navigateur_ok, tmp_path):
    nav = _ouvrir(tmp_path)
    try:
        page = nav.page
        page.set_content("<title>t</title>")
        page.evaluate("setTimeout(() => { document.title = 'reponse=' + confirm('Supprimer ?'); }, 200)")
        with nav.pause_manuelle():
            fin = time.monotonic() + 1.5
            while time.monotonic() < fin:
                nav.pomper()
            assert len(nav._dialogues_differes) == 1  # mise de côté : personne n'a répondu à sa place
        page.wait_for_function("document.title.startsWith('reponse')", timeout=5000)
        assert page.title() == "reponse=true"  # à la reprise : réglage habituel (accepter)
    finally:
        nav.fermer()


SCRIPT_CTRL_C = """
import os, signal, sys, threading, time
sys.path.insert(0, {racine!r})
from pathlib import Path
from autoweb import console
from autoweb.navigateur import Navigateur
from autoweb.scenario import ConfigNavigateur
console.console_interactive = lambda: True
nav = Navigateur(ConfigNavigateur(canal="auto", visible=False), Path({dossier!r}), visible=False)
nav.ouvrir()
lecture, _ = os.pipe()
sys.stdin = os.fdopen(lecture, "r")
threading.Thread(target=lambda: (time.sleep(1.5), os.kill(os.getpid(), signal.SIGINT)), daemon=True).start()
try:
    console.lire_ligne(nav.pomper)
except KeyboardInterrupt:
    print("interrompu", flush=True)
debut = time.monotonic()
nav.fermer()
print("ferme en %.1f s" % (time.monotonic() - debut), flush=True)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="signal envoyé à soi-même : POSIX")
def test_ctrl_c_pendant_une_pause_arrete_proprement(tmp_path, navigateur_ok):
    """Ctrl+C reçu pendant que le navigateur tourne ne doit pas bloquer la fermeture."""
    script = SCRIPT_CTRL_C.format(racine=str(Path(__file__).resolve().parent.parent), dossier=str(tmp_path))
    sortie = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60).stdout
    assert "interrompu" in sortie and "ferme en" in sortie


class _FauxMsvcrt:
    def __init__(self, touches):
        self.touches = list(touches)

    def kbhit(self):
        return bool(self.touches)

    def getwch(self):
        return self.touches.pop(0)


@pytest.mark.parametrize("touches, attendu", [
    ("à\r", "à"),                       # « à » (touche 0 du clavier français) n'est pas une flèche
    ("\xe0Hstop\r", "stop"),            # flèche haut, puis « stop »
    ("\x00;ok\r", "ok"),                # touche F1, puis « ok »
    ("abc\bd\r", "abd"),                # retour arrière
])
def test_lecture_windows_du_clavier(monkeypatch, capsys, touches, attendu):
    from autoweb import console

    monkeypatch.setitem(sys.modules, "msvcrt", _FauxMsvcrt(touches))
    assert console._lire_ligne_windows(lambda: None, []) == attendu

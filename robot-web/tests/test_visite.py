"""Visite guidée : l'utilisateur clique, le robot regarde et note, sans rien bloquer ni modifier.

Le faux portail ressemble aux vieux portails d'entreprise : recherche en formulaire
ASP.NET (envoi POST), fiche de plan à onglets, documents dans un cadre, PDF, écran de
connexion. Les « clics de l'utilisateur » sont joués par le test.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from autoweb import cli
from autoweb.explorateur import Explorateur
from autoweb.navigateur import Navigateur
from autoweb.scenario import ConfigNavigateur
from autoweb.visite import Visite

MENU = ("<nav><a href=/accueil>Accueil</a> <a href=/plans>Plans</a> <a href=/composants>Composants</a> "
        "<a href=/documents>Documents</a></nav>")


def _page(titre, corps):
    return f"<!doctype html><meta charset=utf-8><title>{titre}</title>{MENU}<h1>{titre}</h1>{corps}"


def _plans(recherche=""):
    lignes = "".join(f"<tr><td><a href=/plans/{i}>PL-{i}</a></td><td>Plan secret {i}</td></tr>" for i in (10, 11, 12))
    return _page("Recherche de plans",
                 "<form method=post action=/plans.aspx>"
                 "<input type=hidden name=__VIEWSTATE value=abc><input type=hidden name=__EVENTTARGET value=''>"
                 "<label for=num>Numéro</label><input id=num name=ctl00$Main$txtNum>"
                 "<input type=submit name=ctl00$Main$btnChercher value=Rechercher></form>"
                 + (f"<table><thead><tr><th>Numéro</th><th>Titre</th></tr></thead><tbody>{lignes}</tbody></table>"
                    if recherche else ""))


def _fiche(numero):
    return _page(f"Plan PL-{numero}", """
<div role=tablist><button role=tab onclick="montrer('g')">Général</button>
<button role=tab onclick="montrer('r')">Révisions</button>
<button role=tab onclick="montrer('d')">Documents</button></div>
<section id=g><label for=t>Titre</label><input id=t value='Plan confidentiel Dupont'></section>
<section id=r hidden><table><thead><tr><th>Indice</th><th>Date</th><th>Auteur</th></tr></thead>
<tbody><tr><td>B</td><td>01/02</td><td>M. Martin</td></tr></tbody></table></section>
<section id=d hidden><a href=/plans/doc.pdf>Plan au format PDF</a></section>
<script>function montrer(x){for(const i of ['g','r','d'])document.getElementById(i).hidden=(i!==x);}</script>""")


PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")


class _Portail(BaseHTTPRequestHandler):
    requetes = []

    def log_message(self, *args):
        pass

    def _repondre(self):
        longueur = int(self.headers.get("Content-Length") or 0)
        corps_recu = self.rfile.read(longueur).decode("utf-8", "replace") if longueur else ""
        type(self).requetes.append((self.command, self.path, corps_recu))
        chemin = urlsplit(self.path).path
        type_contenu = "text/html; charset=utf-8"
        if chemin in ("/", "/accueil"):
            corps = _page("Accueil", "<p>Bienvenue</p>")
        elif chemin == "/connexion":
            corps = ("<!doctype html><meta charset=utf-8><title>Connexion</title><form method=post action=/accueil>"
                     "<label for=u>Identifiant</label><input id=u name=user><label for=p>Mot de passe</label>"
                     "<input id=p type=password name=pw><button>Se connecter</button></form>")
        elif chemin == "/plans":
            corps = _plans()
        elif chemin == "/plans.aspx":
            corps = _plans(parse_qs(corps_recu).get("ctl00$Main$txtNum", [""])[0])
        elif chemin == "/plans/doc.pdf":
            corps, type_contenu = PDF, "application/pdf"
        elif chemin.startswith("/plans/"):
            corps = _fiche(chemin.rsplit("/", 1)[1])
        elif chemin == "/documents":
            corps = _page("Documents", "<iframe src=/cadre width=600 height=300></iframe>")
        elif chemin == "/cadre":
            corps = ("<!doctype html><meta charset=utf-8><h2>Classeur</h2><table><thead><tr><th>Nom du fichier</th>"
                     "<th>Version</th></tr></thead><tbody><tr><td>Schéma Durand.pdf</td><td>3</td></tr></tbody></table>")
        else:
            corps = _page("Autre", "<p>page non prévue</p>")
        donnees = corps if isinstance(corps, bytes) else corps.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    do_GET = do_POST = _repondre


@pytest.fixture
def portail():
    _Portail.requetes = []
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Portail)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{serveur.server_address[1]}"
    finally:
        serveur.shutdown()
        serveur.server_close()


def _visiter(tmp_path, url, promenade):
    cfg = ConfigNavigateur(canal="auto", visible=False, profil=str(tmp_path / "profil"), dialogues="ignorer")
    nav = Navigateur(cfg, tmp_path, visible=False)
    nav.options_lancement = {"handle_sigint": False}
    nav.ouvrir()
    visite = Visite(nav, tmp_path / "carte", interactif=False, releve_s=0.4)
    try:
        visite.visiter(url, promenade=promenade)
    finally:
        nav.fermer()
    return visite


def test_visite_guidee_note_les_ecrans_sans_rien_bloquer(portail, tmp_path, navigateur_ok):
    def promenade(v):
        page = v.nav.page_courante()
        page.click("text=Plans")
        v.laisser_tourner(1.5)
        page.fill("#num", "PL-12")
        page.click("input[type=submit]")
        v.laisser_tourner(1.5)
        page.click("text=PL-10")
        v.laisser_tourner(1.5)
        page.click("role=tab[name='Révisions']")
        v.laisser_tourner(1.5)
        page.click("role=tab[name='Documents']")
        v.laisser_tourner(1.5)
        page.click("text=Documents >> nth=0")  # menu : l'écran des documents, avec son cadre
        v.laisser_tourner(2.0)

    visite = _visiter(tmp_path, portail + "/accueil", promenade)
    # rien n'a été bloqué : la recherche (envoi POST) est bien arrivée au portail
    assert any(m == "POST" and p == "/plans.aspx" and "PL-12" in c for m, p, c in _Portail.requetes)
    titres = [(e.titres or [""])[0] for e in visite.ecrans]
    assert "Accueil" in titres and "Recherche de plans" in titres and "Plan PL-10" in titres
    assert visite.resume()["mode"] == "visite"
    # la fiche et chacun de ses onglets ouverts : trois écrans du même modèle d'adresse
    fiches = [e for e in visite.ecrans if e.modele == "/plans/{id}"]
    assert len(fiches) >= 3, [(e.id, e.titres, e.modele) for e in visite.ecrans]
    # le contenu du cadre est lu à part
    assert any(e.cadre and any("Nom du fichier" in " ".join(t["entetes"]) for t in e.tableaux) for e in visite.ecrans)
    # comment on arrive aux écrans : les clics de l'utilisateur
    acces = [" › ".join(p.partage for p in e.chemin) for e in visite.ecrans]
    assert any("onglet « Révisions »" in a for a in acces), acces
    assert any("ligne 1 du tableau" in a for a in acces), acces
    # la nature des envois (sans valeurs) et la technologie
    assert any("ASP.NET WebForms" in n and "ctl#$Main$btnChercher" in n for n in visite.envois), visite.envois
    assert "ASP.NET WebForms" in visite.techno

    partage = (tmp_path / "carte" / "carte_a_partager.txt").read_text(encoding="utf-8")
    assert "Visite guidée" in partage
    assert "TECHNOLOGIE RECONNUE : ASP.NET WebForms" in partage
    for secret in ("PL-12", "PL-10", "Plan secret", "Dupont", "Martin", "Durand", "127.0.0.1", "Plan confidentiel"):
        assert secret not in partage, secret
    assert (tmp_path / "carte" / "carte.html").exists()


def test_visite_note_un_pdf_sans_le_garder(portail, tmp_path, navigateur_ok):
    def promenade(v):
        page = v.nav.page_courante()
        page.click("text=PL-11") if page.locator("text=PL-11").count() else page.goto(portail + "/plans/11")
        v.laisser_tourner(1.5)
        page.click("role=tab[name='Documents']")
        v.laisser_tourner(1.2)
        try:
            page.click("text=Plan au format PDF", timeout=3000)
        except Exception:
            pass
        v.laisser_tourner(2.0)

    visite = _visiter(tmp_path, portail + "/plans/11", promenade)
    assert visite.documents + len(visite.telechargements) >= 1
    fichiers = [f for f in (tmp_path / "telechargements").glob("*")] if (tmp_path / "telechargements").exists() else []
    assert not fichiers, fichiers


def test_ecran_de_connexion_pas_note(portail, tmp_path, navigateur_ok):
    def promenade(v):
        page = v.nav.page_courante()
        page.goto(portail + "/connexion")
        v.laisser_tourner(1.5)
        page.goto(portail + "/plans")
        v.laisser_tourner(1.5)

    visite = _visiter(tmp_path, portail + "/accueil", promenade)
    assert not any(any(c["type"] == "password" for c in e.champs) for e in visite.ecrans)
    assert any((e.titres or [""])[0] == "Recherche de plans" for e in visite.ecrans)


def test_page_du_portail_choisie_parmi_les_onglets(portail, tmp_path, navigateur_ok):
    """Connecté dans un autre onglet : le robot part de l'onglet du portail, pas d'une page Google."""
    cfg = ConfigNavigateur(canal="auto", visible=False, profil=str(tmp_path / "profil"))
    nav = Navigateur(cfg, tmp_path, visible=False)
    nav.ouvrir()
    try:
        robot = Explorateur(nav, tmp_path / "carte", interactif=False)
        robot.url_demandee = portail + "/accueil"
        nav.page_courante().goto(portail.replace("127.0.0.1", "localhost") + "/accueil")  # « autre site »
        autre = nav.contexte.new_page()
        autre.goto(portail + "/plans")
        assert robot._page_du_portail() is autre
        nav.page = autre
        assert robot._page_du_portail() is autre
    finally:
        nav.fermer()


def test_profil_du_robot_unique_et_repris(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path)
    monkeypatch.setattr(cli, "PROFIL_ROBOT", tmp_path / "profils" / "chrome_robot")
    (tmp_path / "profils" / "explorateur" / "Default").mkdir(parents=True)
    profil, premiere = cli.profil_robot()
    assert profil == tmp_path / "profils" / "chrome_robot" and profil.is_dir()
    assert not premiere  # la connexion faite avec la carte de la version 18 est gardée
    assert not (tmp_path / "profils" / "explorateur").exists()
    tache = tmp_path / "taches" / "dupliquer_un_plan.yaml"
    assert cli.chemin_profil_pour(tache, profil) == "../profils/chrome_robot"


def test_premiere_fois_sans_profil(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path)
    monkeypatch.setattr(cli, "PROFIL_ROBOT", tmp_path / "profils" / "chrome_robot")
    _, premiere = cli.profil_robot()
    assert premiere


def test_rassembler_met_tout_dans_un_fichier(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path)
    visite = tmp_path / "explorations" / "20260928-100000-visite"
    auto = tmp_path / "explorations" / "20260928-090000"
    for dossier, texte in ((auto, "carte auto"), (visite, "carte visite")):
        dossier.mkdir(parents=True)
        (dossier / "carte_a_partager.txt").write_text(texte, encoding="utf-8")
    (tmp_path / "taches").mkdir()
    (tmp_path / "taches" / "dupliquer_un_plan_a_partager.txt").write_text("gestes dupliquer", encoding="utf-8")
    (tmp_path / "taches" / "dupliquer_un_plan.yaml").write_text("secret: ne pas envoyer", encoding="utf-8")
    assert cli.cmd_rassembler(cli._ns(sans_ouvrir=True)) == 0
    texte = (tmp_path / "A_ENVOYER_A_CLAUDE.txt").read_text(encoding="utf-8")
    assert "carte visite" in texte and "carte auto" in texte and "gestes dupliquer" in texte
    assert "ne pas envoyer" not in texte
    assert texte.index("carte visite") < texte.index("carte auto") < texte.index("gestes dupliquer")


def test_rien_a_rassembler(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path)
    assert cli.cmd_rassembler(cli._ns(sans_ouvrir=True)) == 1

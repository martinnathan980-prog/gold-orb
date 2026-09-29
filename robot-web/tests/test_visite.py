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
        elif chemin == "/atelier":
            corps = ("<!doctype html><meta charset=utf-8><title>Atelier</title>"
                     "<header><nav><a href=/accueil>Accueil</a><div class=user-menu><a href=/moi>Jean DUPONT</a></div></nav></header>"
                     "<h1>Atelier</h1><div role=tablist><span role=tab>Poste Lyon Sud<span class=close>×</span></span>"
                     "<span role=tab>Général</span></div>"
                     "<dl><dt>Titre du plan</dt><dd>Poste confidentiel</dd><dt>Indice</dt><dd>B</dd></dl>"
                     "<button id=btnVoir onclick=\"document.title='vu'\">Voir Poste Lyon Sud</button>"
                     "<button id=btnSupprimerPlan onclick=\"fetch('/api/supprimer',{method:'POST'})\">Supprimer</button>"
                     "<a href=/fichier.pdf>Télécharger le plan</a>")
        elif chemin == "/fichier.pdf":
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", "attachment; filename=plan-secret.pdf")
            self.send_header("Content-Length", str(len(PDF)))
            self.end_headers()
            self.wfile.write(PDF)
            return
        elif chemin == "/noms":
            corps = ("<!doctype html><meta charset=utf-8><title>Tableau de bord</title>"
                     "<header><nav><a href=/accueil>Accueil</a> <a href=/plans>Plans</a> <a href=/projet>Projet Flamanville</a> "
                     "<a href=/hpc>Hinkley Point C</a> <a href=/equipe>Kofi Mensah</a> <a href=/aide>Where Used</a></nav></header>"
                     "<h1>Tableau de bord</h1>"
                     "<div role=tablist><div role=tab tabindex=0>Général</div><div role=tab tabindex=0>Révisions</div></div>"
                     "<div role=tablist><div role=tab tabindex=0>Pompe Bugey <img src=/img/close_tab.gif width=8 height=8 alt=''></div>"
                     "<div role=tab tabindex=0>Vanne Paluel <span class='ti ti-x'></span></div></div>"
                     "<label for=r>Rechercher dans Flamanville</label><input id=r>"
                     "<table id=kv><tr><th>Turbine Chooz</th><td>A</td></tr><tr><th>Pompe Bugey</th><td>B</td></tr></table>"
                     "<span>Gravelines :</span><span>12 plans</span> <span>Tricastin (tranche 3) :</span><span>4</span>"
                     "<a href=/plans/42>ligne 42 - PL-FLA-00123 Flamanville</a>"
                     "<button onclick=\"document.title='a'\">Newcastle</button> <button onclick=\"document.title='b'\">Printemps</button>"
                     "<button onclick=\"document.title='c'\">Exporter en PDF</button>"
                     "<button onclick=\"location.href='/note'\">Télécharger la note</button>")
        elif chemin == "/note":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=Note.Penly")
            self.send_header("Content-Length", "4")
            self.end_headers()
            self.wfile.write(b"abcd")
            return
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
    (tmp_path / "Telechargements").mkdir(exist_ok=True)
    visite = Visite(nav, tmp_path / "carte", interactif=False, releve_s=0.4,
                    dossier_telechargements=tmp_path / "Telechargements")
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
    ligne_techno = next(l for l in partage.splitlines() if l.startswith("TECHNOLOGIE RECONNUE"))
    assert "ASP.NET WebForms" in ligne_techno and "EPLAN" not in ligne_techno  # « /plans » n'est pas EPLAN
    assert "[étape : Accueil et menus]" in partage
    for secret in ("PL-12", "PL-10", "Plan secret", "Dupont", "Martin", "Durand", "127.0.0.1", "Plan confidentiel"):
        assert secret not in partage, secret
    assert (tmp_path / "carte" / "carte_PRIVEE_ne_pas_envoyer.html").exists()


def test_visite_range_un_pdf_dans_telechargements(portail, tmp_path, navigateur_ok):
    """Un PDF ouvert pendant la visite arrive dans Téléchargements, comme d'habitude ; la carte
    note seulement qu'un document existe."""
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
    if visite.telechargements:  # navigateur sans visionneuse de PDF : le fichier est téléchargé
        assert [f.name for f in (tmp_path / "Telechargements").iterdir()] == ["doc.pdf"]


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


def test_profil_robot_dans_les_taches(tmp_path):
    from autoweb.navigateur import PROFIL_ROBOT, chemin_profil

    assert chemin_profil("robot", tmp_path) == PROFIL_ROBOT
    # tâche enregistrée en version 18 : un profil par tâche, désormais le Chrome du robot
    assert chemin_profil("profils/dupliquer_un_plan", tmp_path / "taches") == PROFIL_ROBOT
    assert chemin_profil("profils/outil", tmp_path) == tmp_path / "profils" / "outil"


def test_profil_deja_ouvert_detecte(tmp_path):
    import os
    import socket
    import sys

    from autoweb.navigateur import profil_verrouille

    assert not profil_verrouille(tmp_path)
    if sys.platform != "win32":
        os.symlink(f"{socket.gethostname()}-{os.getpid()}", tmp_path / "SingletonLock")
        assert profil_verrouille(tmp_path)
        os.remove(tmp_path / "SingletonLock")
        os.symlink(f"{socket.gethostname()}-999999999", tmp_path / "SingletonLock")  # Chrome arrêté brutalement
        assert not profil_verrouille(tmp_path)


def test_premiere_fois_sans_profil(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path)
    monkeypatch.setattr(cli, "PROFIL_ROBOT", tmp_path / "profils" / "chrome_robot")
    _, premiere = cli.profil_robot()
    assert premiere


def test_rassembler_met_tout_dans_un_fichier(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path)
    visite = tmp_path / "explorations" / "20260928-100000-visite"
    auto = tmp_path / "explorations" / "20260928-090000"
    import json
    import os
    import time

    ancienne = tmp_path / "explorations" / "20260927-100000"  # carte de la version 18 : jamais envoyée
    ratee = tmp_path / "explorations" / "20260928-110000-visite"  # visite d'un seul écran : pas envoyée
    for i, (dossier, texte, version, ecrans) in enumerate(((ancienne, "carte v18", 0, 30), (auto, "carte auto", 19, 12),
                                                           (visite, "carte visite", 19, 20), (ratee, "carte ratee", 19, 1))):
        dossier.mkdir(parents=True)
        (dossier / "carte_a_partager.txt").write_text(texte, encoding="utf-8")
        (dossier / "carte.json").write_text(json.dumps({"version": version, "ecrans": [{}] * ecrans}), encoding="utf-8")
        horodatage = time.time() - 100 + i
        os.utime(dossier / "carte_a_partager.txt", (horodatage, horodatage))
    (tmp_path / "taches").mkdir()
    (tmp_path / "taches" / "dupliquer_un_plan_a_partager.txt").write_text("gestes dupliquer", encoding="utf-8")
    (tmp_path / "taches" / "dupliquer_un_plan.yaml").write_text("secret: ne pas envoyer", encoding="utf-8")
    (tmp_path / "mots_a_cacher.txt").write_text("# commentaire\nFlamanville\n", encoding="utf-8")
    (tmp_path / "taches" / "lire_un_plan_a_partager.txt").write_text("onglet flamanville", encoding="utf-8")
    assert cli.cmd_rassembler(cli._ns(sans_ouvrir=True)) == 0
    (sortie,) = tmp_path.glob("A_ENVOYER_A_CLAUDE_*.txt")
    texte = sortie.read_text(encoding="utf-8")
    assert "flamanville" not in texte.lower() and "onglet XXX" in texte
    assert "carte v18" not in texte and "carte ratee" not in texte
    assert "carte visite" in texte and "carte auto" in texte and "gestes dupliquer" in texte
    assert "ne pas envoyer" not in texte
    assert texte.index("carte visite") < texte.index("carte auto") < texte.index("gestes dupliquer")


def test_rien_a_rassembler(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path)
    assert cli.cmd_rassembler(cli._ns(sans_ouvrir=True)) == 1


# ---------------------------------------------------------------------- nature des envois, sans valeurs
@pytest.mark.parametrize("url, type_contenu, corps, attendu, absent", [
    ("https://x/Plans.aspx", "application/x-www-form-urlencoded",
     "__VIEWSTATE=abc&__EVENTTARGET=ctl00%24Main%24gvPlans&__EVENTARGUMENT=Page%242&ctl00%24Main%24txtNum=PL-12",
     ["ASP.NET WebForms", "ctl#$Main$gvPlans", "commande Page", "[lecture probable]"], ["PL-12", "abc"]),
    ("https://x/Plans.aspx", "application/x-www-form-urlencoded",
     "__VIEWSTATE=abc&__EVENTTARGET=ctl00%24Main%24btnSupprimerPlan&__EVENTARGUMENT=",
     ["[écriture probable]"], []),
    ("https://x/app/graphql", "application/json",
     '[{"query":"query A { a }","operationName":"GetPlans"},{"query":"mutation B { b(id: \\"PL-9\\") }"}]',
     ["GraphQL", "mutation", "[écriture probable]"], ["PL-9"]),
    ("https://x/app/graphql", "application/json",
     '{"query":"fragment F on P { id }\\nquery Q { p(numero: \\"PL-3\\") { ...F } }","variables":{"n":"PL-3"}}',
     ["GraphQL query", "[lecture probable]"], ["PL-3"]),
    ("https://x/Server/InnovatorServer.aspx", "text/xml",
     "<Body><ApplyItem><Item type='Part' action='get'><item_number>PL-4</item_number></Item></ApplyItem></Body>",
     ["Aras" if False else "SOAP/XML", "action get", "[lecture probable]"], ["PL-4"]),
    ("https://x/tc/JsonRestServices/Core-2007-01-DataManagement/getProperties", "application/json",
     '{"body":{"objects":[{"uid":"QxSJ5"}]}}', ["Teamcenter SOA", "getProperties", "[lecture probable]"], ["QxSJ5"]),
    ("https://x/sap/opu/odata/sap/API_X/$batch", "multipart/mixed; boundary=batch_1",
     "--batch_1\nGET Parts('PL-5') HTTP/1.1\n\n--batch_1\nGET Docs HTTP/1.1\n", ["OData", "2 GET", "[lecture probable]"],
     ["PL-5"]),
    ("https://x/a/fiche.xhtml", "application/x-www-form-urlencoded",
     "javax.faces.ViewState=x&javax.faces.source=form%3Atable&javax.faces.behavior.event=page&form%3Aq=Dupont",
     ["JSF", "événement page", "[lecture probable]"], ["Dupont"]),
    ("https://x/projets/Flamanville", "application/json", '{"numero":"PL-6","titre":"Poste Dupont"}',
     ["JSON, clés : numero, titre"], ["Flamanville", "PL-6", "Dupont"]),
])
def test_nature_des_envois_sans_valeurs(url, type_contenu, corps, attendu, absent):
    from autoweb.explorateur import classer_envoi

    texte = classer_envoi("POST", url, type_contenu, corps)
    for morceau in attendu:
        assert morceau in texte, texte
    for secret in absent:
        assert secret not in texte, texte


def test_modeles_d_adresse_des_portails_a_route():
    from autoweb.explorateur import modele_url

    awc = "https://tc/awc/#/com.siemens.splm.clientfx.tcui.xrt.showObject?uid=gRTJnuFxIOqA"
    assert modele_url(awc) == "/awc/#/com.siemens.splm.clientfx.tcui.xrt.showObject?uid={}"
    windchill = "https://w/Windchill/app/#ptc1/tcomp/infoPage?oid=OR:wt.part.WTPart:123456"
    assert modele_url(windchill) == "/Windchill/app/#ptc1/tcomp/infoPage?oid=OR:wt.part.WTPart:{id}"
    assert modele_url("https://p/projets/renovation-poste-source-nord/plans") == "/projets/{id}/plans"


def test_connecter_ouvre_le_chrome_du_robot_sans_robot(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path)
    monkeypatch.setattr(cli, "PROFIL_ROBOT", tmp_path / "profils" / "chrome_robot")
    trace = tmp_path / "arguments.txt"
    faux = tmp_path / "faux_chrome.sh"
    faux.write_text(f'#!/bin/sh\necho "$@" > "{trace}"\nsleep 4.5\n', encoding="utf-8")
    faux.chmod(0o755)
    assert cli.cmd_connecter(cli._ns(url="https://portail.exemple/accueil", executable=str(faux))) == 0
    arguments = trace.read_text(encoding="utf-8")
    assert f"--user-data-dir={tmp_path / 'profils' / 'chrome_robot'}" in arguments
    assert "https://portail.exemple/accueil" in arguments
    assert "--remote-debugging" not in arguments and "--enable-automation" not in arguments


def test_connecter_chrome_du_robot_deja_ouvert(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DOSSIER_PROJET", tmp_path)
    monkeypatch.setattr(cli, "PROFIL_ROBOT", tmp_path / "profils" / "chrome_robot")
    faux = tmp_path / "faux_chrome.sh"
    faux.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")  # Chrome passe la main à la fenêtre déjà ouverte
    faux.chmod(0o755)
    assert cli.cmd_connecter(cli._ns(url=None, executable=str(faux))) == 1


def test_diagnostic_de_connexion_sans_donnees(tmp_path):
    from autoweb.navigateur import EXTENSION_SSO_MICROSOFT, diagnostic_connexion

    (tmp_path / "Default" / "Extensions" / EXTENSION_SSO_MICROSOFT).mkdir(parents=True)
    lignes = dict(diagnostic_connexion(tmp_path))
    assert lignes["extension de connexion Microsoft installée dans le Chrome du robot"] == "oui"
    assert lignes["Chrome du robot déjà utilisé"] == "oui"
    assert all(v in ("oui", "non") or v.replace(".", "").isdigit() for v in lignes.values())



def test_filet_de_securite_et_carte_sans_noms(portail, tmp_path, navigateur_ok):
    """Pendant la visite, « Supprimer » ne part pas ; le nom de l'utilisateur, le nom d'un
    document ouvert et la suite de « Voir ... » ne sont jamais repris ; un fichier
    téléchargé arrive dans Téléchargements, comme d'habitude."""
    def promenade(v):
        page = v.nav.page_courante()
        page.click("#btnSupprimerPlan")
        v.laisser_tourner(1.0)
        page.evaluate("document.querySelector('.__autoweb_etape').click()")  # « Étape suivante »
        v.laisser_tourner(1.0)
        page.click("text=Télécharger le plan")
        v.laisser_tourner(1.5)

    telechargements = tmp_path / "Telechargements"
    telechargements.mkdir()
    cfg = ConfigNavigateur(canal="auto", visible=False, profil=str(tmp_path / "profil"), dialogues="ignorer")
    nav = Navigateur(cfg, tmp_path, visible=False)
    nav.ouvrir()
    visite = Visite(nav, tmp_path / "carte", interactif=False, releve_s=0.4, dossier_telechargements=telechargements)
    try:
        visite.visiter(portail + "/atelier", promenade=promenade)
    finally:
        nav.fermer()
    assert not any(p == "/api/supprimer" for _, p, _ in _Portail.requetes)
    assert visite.boutons_bloques == 1 and visite.etape == 1
    assert [f.name for f in telechargements.iterdir()] == ["plan-secret.pdf"]
    partage = (tmp_path / "carte" / "carte_a_partager.txt").read_text(encoding="utf-8")
    for secret in ("DUPONT", "Lyon", "Poste confidentiel", "plan-secret"):
        assert secret not in partage, secret
    assert "Voir …" in partage and "Titre du plan" in partage and "Indice" in partage
    assert "onglets de document (un par élément ouvert) : 1" in partage
    assert "code " not in partage  # noms de code (id, name) : jamais dans le fichier à partager
    assert "1 bouton(s) et 0 envoi(s) de modification bloqué(s)" in partage


def test_recherche_ne_cree_pas_un_nouvel_ecran():
    from autoweb.explorateur import modele_url

    assert modele_url("https://p/plans?q=Flamanville&page=2") == modele_url("https://p/plans?q=Chinon&page=3")
    assert "Flamanville" not in modele_url("https://p/plans?recherche=Flamanville")


def test_noms_de_personnes_reconnus():
    from autoweb.explorateur import ressemble_a_une_personne as p

    for nom in ("Jean DUPONT", "DUPONT Jean", "J. Dupont", "Mme Martin", "Dupont, Jean"):
        assert p(nom), nom
    for libelle in ("Plans", "Recherche avancée", "Mes documents", "Accueil"):
        assert not p(libelle), libelle



def test_carte_sans_noms_de_projets_ni_de_sites(portail, tmp_path, navigateur_ok):
    """Menus, chemin d'accès, onglets de document (croix en image), champs, entêtes, libellés, clé
    « ligne ... », boutons qui commencent comme un verbe, type du fichier téléchargé : aucun nom de
    projet, de site ou de personne dans le fichier à partager ni dans la fenêtre noire."""
    def promenade(v):
        page = v.nav.page_courante()
        page.click("text=Newcastle")
        v.laisser_tourner(0.6)
        page.click("text=Télécharger la note")
        v.laisser_tourner(1.2)
        page.click("text=ligne 42 - PL-FLA-00123 Flamanville")
        v.laisser_tourner(1.2)
        page.goto(portail + "/noms")
        v.laisser_tourner(0.8)
        page.click("text=Projet Flamanville")
        v.laisser_tourner(1.2)

    visite = _visiter(tmp_path, portail + "/noms", promenade)
    partage = (tmp_path / "carte" / "carte_a_partager.txt").read_text(encoding="utf-8")
    for secret in ("Flamanville", "Hinkley", "Point C", "Kofi", "Mensah", "Bugey", "Paluel", "Chooz", "Newcastle",
                   "Printemps", "Penly", "Gravelines", "Tricastin", "ligne 42", "FLA"):
        assert secret not in partage, secret
    assert "Where Used" in partage and "Général" in partage and "Révisions" in partage  # la structure reste
    assert "onglets de document (un par élément ouvert) : 2" in partage
    assert "Exporter en PDF" in partage and "(sans nom) [texte]" in partage
    assert "télécharge un fichier .?" in partage and visite.telechargements


def test_filtres_de_noms_et_de_types():
    from autoweb.cli import cacher_mots
    from autoweb.explorateur import (_modele_sans_requete, extension_connue, masquer, nom_propre_dedans,
                                     verbe_de_bouton)

    for nom in ("Projet Flamanville", "Site Penly", "Hinkley Point C", "Kofi Mensah", "Rechercher dans Chinon"):
        assert nom_propre_dedans(nom), nom
    for libelle in ("Date de création", "Where Used", "Bill of Materials", "Mes Documents", "Part Number",
                    "Cycle de vie", "Advanced Search", "Change Requests", "Général"):
        assert not nom_propre_dedans(libelle), libelle
    for mot in ("Newcastle", "Lockheed", "Printemps", "Addison", "Runcorn", "Stopford", "Paluel"):
        assert not verbe_de_bouton(mot), mot
    for mot in ("Supprimer", "Exporter", "Delete", "Voir", "Nouveau", "Télécharger", "Print"):
        assert verbe_de_bouton(mot), mot
    assert extension_connue("CR réunion M.Roux") == "?" and extension_connue("Note.Penly") == "?"
    assert extension_connue("plan.PDF") == "pdf" and extension_connue("/plans/{id}/vue.dwg?x=1") == "dwg"
    assert masquer("Tricastin (tranche 3) :") == "Tricastin (tranche #) :"
    assert _modele_sans_requete("/plans/{id}?onglet=general") == "/plans/{id}"
    assert _modele_sans_requete("/app#/plan/{id}?tab=x") == "/app#/plan/{id}"
    texte, comptes = cacher_mots("menus : Cœur Défense ; Œting ; Groß ; Ørsted ; Łódź",
                                 ["Coeur Defense", "Oeting", "Gross", "Orsted", "Lodz"])
    assert texte == "menus : XXX ; XXX ; XXX ; XXX ; XXX" and all(comptes.values())
    import unicodedata
    texte, _ = cacher_mots(unicodedata.normalize("NFD", "Étienne Lefèvre"), ["Lefèvre", "Étienne"])
    assert texte == "XXX XXX"


# ---------------------------------------------------------------------- filet de sécurité : les pièges de la relecture
PIEGES = """<!doctype html><meta charset=utf-8><title>Fiche</title>
<script>const envoi = n => fetch('/api/' + n, {method: 'POST', body: 'x'});</script>
<nav><a href=/accueil>Accueil</a> <a href=/modifications>Mes modifications</a></nav>
<ul role=menu><li role=menuitem onclick="envoi('menuitem_supprimer')">Supprimer</li>
<li role=menuitem onclick="envoi('menuitem_dupliquer')">Dupliquer</li></ul>
<header><h2>PL-12</h2><button onclick="envoi('header_supprimer')">Supprimer</button></header>
<aside><button onclick="envoi('aside_enregistrer')">Enregistrer</button></aside>
<button id=a1 onclick="envoi('enregistrer_fermer')">Enregistrer et fermer</button>
<button id=a2 onclick="envoi('cancel_checkout')">Cancel Checkout</button>
<button id=a3 onclick="envoi('reviser')">Réviser</button>
<button id=ctl00_Main_ucResultatsRecherche_gvPlans_ctl02_btnSupprimer onclick="envoi('grille')">Supprimer</button>
<button id=a4 class=btn-danger onclick="envoi('icone_seule')"><i class="fa fa-trash"></i></button>
<a id=a5 href="javascript:void(0)" onclick="envoi('img_alt')"><img alt=Supprimer src=data:,></a>
<a id=a6 href="/plans/5" onclick="envoi('lien_onclick');return false">Supprimer</a>
<div id=a7 style="cursor:pointer" onclick="envoi('div_maison')">Supprimer</div>
<button id=a8 onpointerup="envoi('pointerup')">Supprimer</button>
<div id=a9 role=button tabindex=0 onkeydown="if(event.key==='Enter')envoi('clavier')">Supprimer</div>
<a id=a10 href="/plans/5/delete">Retirer du dossier</a>
<form id=f1 onsubmit="envoi('formulaire_enregistrer');return false"><input name=t><button>Enregistrer</button></form>
<button id=a11 onclick="fetch('/api/plans/5', {method: 'DELETE'})">Mettre à la une</button>
<button id=a12 onclick="fetch('/api/Plans.aspx', {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: '__VIEWSTATE=x&__EVENTTARGET=ctl00%24Main%24btnSupprimerPlan'})">Continuer</button>
<table><thead><tr><th>Numéro</th><th>Statut</th></tr></thead><tbody>
<tr style="cursor:pointer" onclick="envoi('ligne_publiee')"><td>PL-12</td><td>Publié</td></tr></tbody></table>
<a id=b1 href=/plans/7>Nouveau poste source</a>
<button id=b2 onclick="envoi('rechercher')">Rechercher</button>
<button id=b3 onclick="envoi('telecharger')">Télécharger le PDF</button>
<button id=b4 onclick="envoi('fermer')">Fermer</button>
<x-bouton id=a13 role=button onclick="envoi('composant_web')">Supprimer</x-bouton>
<button id=a14 onclick="envoi('emoji_trash')"><i class="fa fa-trash"></i>🗑</button>
<div id=a15 role=button tabindex=0 onkeyup="if(event.key===' ')envoi('keyup')">Supprimer</div>
<div id=a16 tabindex=0 onkeydown="if(event.key==='Delete')envoi('touche_suppr')">PL-12</div>
<a id=a17 href="/plans/6" data-turbo-method="delete" onclick="event.preventDefault();envoi('turbo')">Retirer</a>
<button id=a18 onclick="fetch('/api/plans/5/delete', {method: 'POST', body: '{}'})">Oui</button>
<button id=a19 onclick="fetch('/api/plans/5', {method: 'POST', headers: {'X-HTTP-Method-Override': 'DELETE'}})">OK</button>
<button id=a20 onclick="fetch('/api/plans/bulk', {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: 'action=supprimer&ids=5'})">Valider</button>
<label id=a21 class=btn style="cursor:pointer" onclick="envoi('label_btn')">Supprimer</label>
<button id=a22 onclick="fetch('/api/Plans.aspx', {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: '__VIEWSTATE=x&__EVENTTARGET=ctl00%24Main%24gv&__EVENTARGUMENT=Delete%240'})">Continuer</button>
<button id=a23 onclick="const w = window.open('', 'edition', 'width=400,height=300'); w.document.open(); w.document.write('<button id=b onclick=&quot;opener.envoi(\\'popup_docwrite\\')&quot;>Enregistrer</button>'); w.document.close();">Ouvrir la fiche</button>
<iframe id=cadre_vide width=300 height=80></iframe>
<script>
  window.addEventListener('load', () => setTimeout(() => {
    const d = document.getElementById('cadre_vide').contentDocument;
    d.body.innerHTML = "<button id=dans_cadre onclick=parent.envoi('cadre_vide_enregistrer')>Enregistrer</button>";
  }, 300));
</script>
"""

CONSULTATION = """<!doctype html><meta charset=utf-8><title>Fiche</title>
<script>const lire = n => fetch('/lecture/' + n);</script>
<nav><a id=c1 href=/favoris>Favoris</a> <a id=c2 href=/nouveautes>Nouveautés</a>
<a id=c3 href="/plans?cree_par=moi">Plans créés par moi</a> <a id=c4 href="#" onclick="lire('supprimes')">Documents supprimés</a></nav>
<div role=tablist><button id=c5 role=tab onclick="lire('historique')">Historique des modifications</button>
<button id=c6 role=tab onclick="lire('commentaires')">Commentaires</button></div>
<button id=c7 onclick="lire('filtres')">Appliquer les filtres</button>
<button id=c8 onclick="lire('nouvelle_recherche')">Nouvelle recherche</button>
<button id=c9 onclick="lire('modifier_recherche')">Modifier la recherche</button>
<button id=c10 onclick="lire('reinitialiser')">Réinitialiser</button>
<button id=c11 onclick="fetch('/api/plans/5/comments').then(() => lire('commentaires_api'))">Voir les commentaires</button>
<table><thead><tr><th>Titre</th><th>Statut</th></tr></thead><tbody>
<tr style="cursor:pointer" onclick="lire('ligne')"><td id=c12>Nouveau poste source</td><td>Publié</td></tr>
<tr style="cursor:pointer" onclick="lire('ligne_new')"><td>Poste Nord</td><td id=c13>New</td></tr>
<tr><td><a id=c14 href="javascript:void(0)" onclick="lire('titre_modifier')">Modifier poste HTA</a></td><td>Release</td></tr>
</tbody></table>
<div role=listbox aria-label=Statut><div role=option id=c15 onclick="lire('option_nouveau')">Nouveau</div></div>
<button id=c16 onclick="lire('copier_lien')">Copier le lien</button>
<ul role=menu><li role=menuitem id=c17 onclick="lire('release_notes')">Release notes</li></ul>
"""
SESSION_EXPIREE = ("document.body.insertAdjacentHTML('beforeend', '<div role=dialog aria-label=\"Session expirée\">"
                   "<input type=password><button id=c18 onclick=\"lire(\\'reconnexion\\')\">Envoyer</button></div>')")
CONSULTATION_ATTENDUS = ["supprimes", "historique", "commentaires", "filtres", "nouvelle_recherche", "modifier_recherche",
                         "reinitialiser", "commentaires_api", "ligne", "ligne_new", "titre_modifier", "option_nouveau",
                         "copier_lien", "release_notes", "reconnexion"]

DANGEREUX = ["menuitem_supprimer", "menuitem_dupliquer", "header_supprimer", "aside_enregistrer", "enregistrer_fermer",
             "cancel_checkout", "reviser", "grille", "icone_seule", "img_alt", "lien_onclick", "div_maison", "pointerup",
             "clavier", "formulaire_enregistrer", "composant_web", "emoji_trash", "keyup", "touche_suppr", "turbo",
             "cadre_vide_enregistrer", "bulk", "label_btn", "popup_docwrite"]
PERMIS = ["ligne_publiee", "rechercher", "telecharger", "fermer"]


def _serveur_pieges():
    requetes = []

    class Pieges(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _repondre(self):
            longueur = int(self.headers.get("Content-Length") or 0)
            corps = self.rfile.read(longueur).decode("utf-8", "replace") if longueur else ""
            requetes.append((self.command, urlsplit(self.path).path, corps))
            chemin = urlsplit(self.path).path
            page = {"/": PIEGES, "/fiche": PIEGES, "/consultation": CONSULTATION}.get(chemin, "<!doctype html><title>x</title>ok")
            donnees = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        do_GET = do_POST = do_DELETE = do_PUT = _repondre

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Pieges)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, requetes


def test_filet_de_securite_resiste_aux_pieges(tmp_path, navigateur_ok):
    serveur, requetes = _serveur_pieges()
    url = f"http://127.0.0.1:{serveur.server_address[1]}/fiche"

    def promenade(v):
        page = v.nav.page_courante()
        for selecteur in ("[role=menuitem] >> nth=0", "[role=menuitem] >> nth=1", "header button", "aside button",
                          "#a1", "#a2", "#a3", "#ctl00_Main_ucResultatsRecherche_gvPlans_ctl02_btnSupprimer", "#a4",
                          "#a5", "#a6", "#a7", "#a8", "#f1 button", "#a11", "#a12", "#a13",
                          "tbody tr", "#b2", "#b3", "#b4"):
            page.click(selecteur)
            page.wait_for_timeout(150)
        page.focus("#a9")
        page.keyboard.press("Enter")
        page.focus("#a15")
        page.keyboard.press(" ")
        page.focus("#a16")
        page.keyboard.press("Delete")
        for selecteur in ("#a14", "#a17", "#a18", "#a19", "#a20"):
            page.click(selecteur)
            page.wait_for_timeout(150)
        page.frame_locator("#cadre_vide").locator("#dans_cadre").click()
        page.click("#a21")
        page.click("#a22")
        with page.expect_popup() as fenetre:
            page.click("#a23")
        fenetre.value.click("#b")  # tout de suite, avant le relevé suivant du robot
        page.click("#a10", button="middle")
        v.laisser_tourner(1.0)
        page.click("#b1")  # un lien ordinaire dont le texte ressemble à une action : il s'ouvre
        v.laisser_tourner(1.0)

    try:
        cfg = ConfigNavigateur(canal="auto", visible=False, profil=str(tmp_path / "profil"), dialogues="ignorer")
        nav = Navigateur(cfg, tmp_path, visible=False)
        nav.ouvrir()
        visite = Visite(nav, tmp_path / "carte", interactif=False, releve_s=0.4)
        try:
            visite.visiter(url, promenade=promenade)
        finally:
            nav.fermer()
    finally:
        serveur.shutdown()
        serveur.server_close()
    arrives = {p.rsplit("/", 1)[-1] for m, p, _ in requetes if p.startswith("/api/")}
    for nom in DANGEREUX:
        assert nom not in arrives, nom
    for nom in PERMIS:
        assert nom in arrives, nom
    assert not any(m == "DELETE" for m, _, _ in requetes)  # « Mettre à la une » : DELETE coupé par la 2e barrière
    assert not any(p in ("/api/plans/5/delete", "/api/plans/5", "/api/plans/bulk") for _, p, _ in requetes)
    assert not any("btnSupprimerPlan" in c for _, _, c in requetes)  # envoi ASP.NET de suppression coupé
    assert not any("Delete%240" in c for _, _, c in requetes)  # suppression d'une ligne de grille ASP.NET coupée
    assert not any(p == "/plans/5/delete" for _, p, _ in requetes)  # clic molette sur un lien d'action
    assert any(p == "/plans/7" for _, p, _ in requetes)  # « Nouveau poste source » : simple lien, ouvert
    assert visite.envois_bloques and visite.boutons_bloques >= 10


def test_connexion_d_entreprise_jamais_bloquee(tmp_path, navigateur_ok):
    """Page de connexion (autre site, bouton « okta-signin-submit ») : le filet ne s'en mêle pas."""
    serveur, requetes = _serveur_pieges()
    port = serveur.server_address[1]
    connexion = f"http://localhost:{port}/connexion"

    def promenade(v):
        page = v.nav.page_courante()
        page.set_content("<form method=post action='/login'><input name=u><input type=password name=p>"
                         "<input type=submit id=okta-signin-submit value='Sign In'></form>")
        page.click("#okta-signin-submit")
        page.wait_for_timeout(500)

    try:
        cfg = ConfigNavigateur(canal="auto", visible=False, profil=str(tmp_path / "profil"), dialogues="ignorer")
        nav = Navigateur(cfg, tmp_path, visible=False)
        nav.ouvrir()
        visite = Visite(nav, tmp_path / "carte", interactif=False, releve_s=0.4)
        try:
            visite.visiter(connexion, promenade=promenade)
        finally:
            nav.fermer()
    finally:
        serveur.shutdown()
        serveur.server_close()
    assert any(m == "POST" and p == "/login" for m, p, _ in requetes)
    assert visite.boutons_bloques == 0



def test_filet_de_securite_laisse_consulter(tmp_path, navigateur_ok):
    """Onglets, menus, filtres, recherches, lignes : de la consultation, jamais bloquée, même quand
    le libellé contient un mot d'action (« Historique des modifications », « Nouveau poste »)."""
    serveur, requetes = _serveur_pieges()
    url = f"http://127.0.0.1:{serveur.server_address[1]}/consultation"

    def promenade(v):
        page = v.nav.page_courante()
        for selecteur in ("#c4", "#c5", "#c6", "#c7", "#c8", "#c9", "#c10", "#c11", "#c12", "#c13", "#c14", "#c15",
                          "#c16", "#c17"):
            page.click(selecteur)
            page.wait_for_timeout(200)
        page.evaluate(SESSION_EXPIREE)  # la session expire : on se reconnecte dans la page
        page.click("#c18")
        page.wait_for_timeout(200)
        for lien in ("#c1", "#c2", "#c3"):
            page.goto(url)
            page.click(lien)
            page.wait_for_timeout(300)
        v.laisser_tourner(1.0)

    try:
        cfg = ConfigNavigateur(canal="auto", visible=False, profil=str(tmp_path / "profil"), dialogues="ignorer")
        nav = Navigateur(cfg, tmp_path, visible=False)
        nav.ouvrir()
        visite = Visite(nav, tmp_path / "carte", interactif=False, releve_s=0.4)
        try:
            visite.visiter(url, promenade=promenade)
        finally:
            nav.fermer()
    finally:
        serveur.shutdown()
        serveur.server_close()
    lectures = {p.rsplit("/", 1)[-1] for _, p, _ in requetes if p.startswith("/lecture/")}
    for nom in CONSULTATION_ATTENDUS:
        assert nom in lectures, nom
    for chemin in ("/favoris", "/nouveautes", "/plans", "/api/plans/5/comments"):
        assert any(p == chemin for _, p, _ in requetes), chemin
    assert visite.boutons_bloques == 0 and not visite.envois_bloques

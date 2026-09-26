"""L'explorateur parcourt un portail sans rien modifier et en dresse la carte.

Le faux portail ci-dessous est piégé : liens de suppression et de déconnexion,
boutons Modifier / Supprimer / Imprimer, bouton « Actualiser » qui envoie en réalité
des données, fichier PDF, lien externe. Le serveur note chaque requête reçue :
rien de tout cela ne doit l'atteindre.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from autoweb import cli
from autoweb.explorateur import Explorateur, Limites, masquer, modele_url, mot_interdit, est_lecture
from autoweb.navigateur import Navigateur
from autoweb.scenario import ConfigNavigateur

NAV = ("<nav><a href=/accueil>Accueil</a> <a href='/composants?page=1'>Composants</a> "
       "<a href=/plans>Plans</a> <a href=/aide.pdf>Aide</a> <a href=/deconnexion>Déconnexion</a> "
       "<a href=/plans/supprimer-tout>Tout effacer</a> <a href='https://externe.exemple/'>Partenaire</a></nav>")


def _page(titre, corps):
    return f"<!doctype html><meta charset=utf-8><title>{titre}</title>{NAV}<h1>{titre}</h1>{corps}"


def _composants(n):
    lignes = "".join(
        f"<tr><td><a href=/composants/REF-{n}{i}>REF-{n}{i}</a></td><td>Disjoncteur modèle {n}{i}</td><td>Fabricant {i}</td></tr>"
        for i in range(10))
    return _page("Composants", f"<table><thead><tr><th>Référence</th><th>Désignation</th><th>Fabricant</th></tr></thead>"
                               f"<tbody>{lignes}</tbody></table>"
                               f"<a href='/composants?page={n + 1}'>Suivant</a>")


def _fiche_composant(ref):
    return _page(f"Composant {ref}",
                 "<label for=des>Désignation</label><input id=des readonly value='Disjoncteur secret'>"
                 "<label for=fab>Fabricant</label><input id=fab readonly value='ACME'>"
                 f"<button type=button onclick=\"fetch('/api/composants/{ref}/maj',{{method:'POST'}})\">Modifier</button>"
                 "<a href='/composants?page=1'>Retour</a>")


def _plans():
    lignes = "".join(f"<tr><td><a href=/plans/{i}>PL-{i}</a></td><td>Plan du bâtiment {i}</td></tr>" for i in range(1, 31))
    return _page("Plans",
                 "<form method=get action=/plans><label for=q>Numéro</label><input id=q name=q>"
                 "<button type=submit>Rechercher</button></form>"
                 "<button type=button onclick=\"location='/plans/nouveau'\">Nouveau plan</button>"
                 "<button type=button id=actu onclick=\"fetch('/api/plans/lecture',{method:'POST'})"
                 ".then(()=>document.body.dataset.ok=1).catch(()=>document.body.dataset.ko=1)\">Actualiser</button>"
                 f"<table><thead><tr><th>Numéro</th><th>Titre</th></tr></thead><tbody>{lignes}</tbody></table>")


def _fiche_plan(numero):
    return _page(f"Plan PL-{numero}", """
<div role=tablist><button role=tab onclick="montrer('g')">Général</button>
<button role=tab onclick="montrer('c')">Composants</button>
<button role=tab onclick="montrer('h')">Historique</button></div>
<section id=g><label for=t>Titre</label><input id=t value='Plan confidentiel'><label for=s>Statut</label>
<select id=s><option>En cours</option><option>Diffusé</option></select></section>
<section id=c hidden><table><thead><tr><th>Repère</th><th>Composant</th></tr></thead><tbody><tr><td>Q1</td><td>REF-11</td></tr></tbody></table></section>
<section id=h hidden><table><thead><tr><th>Date</th><th>Auteur</th><th>Action</th></tr></thead><tbody><tr><td>01/01</td><td>M. X</td><td>Création</td></tr></tbody></table></section>
<button type=button onclick="fetch('/api/plans/1',{method:'DELETE'})">Supprimer</button>
<button type=button onclick="window.print()">Imprimer</button>
<button type=button class=icone onclick="fetch('/api/plans/1/corbeille',{method:'POST'})"><svg width=16 height=16><rect width=16 height=16></rect></svg></button>
<script>function montrer(x){for(const i of ['g','c','h'])document.getElementById(i).hidden=(i!==x);}</script>""")


class _Portail(BaseHTTPRequestHandler):
    requetes = []

    def log_message(self, *args):
        pass

    def _repondre(self):
        type(self).requetes.append((self.command, self.path))
        chemin = urlsplit(self.path).path
        requete = parse_qs(urlsplit(self.path).query)
        if chemin in ("/", "/accueil"):
            corps = _page("Accueil", "<p>Bienvenue</p>")
        elif chemin == "/composants":
            corps = _composants(int(requete.get("page", ["1"])[0]))
        elif chemin.startswith("/composants/"):
            corps = _fiche_composant(chemin.rsplit("/", 1)[1])
        elif chemin == "/plans":
            corps = _plans()
        elif chemin.startswith("/plans/") and chemin.rsplit("/", 1)[1].isdigit():
            corps = _fiche_plan(chemin.rsplit("/", 1)[1])
        else:
            corps = _page("Autre", "<p>page non prévue</p>")
        donnees = corps.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    do_GET = do_POST = do_DELETE = do_PUT = _repondre


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


def _explorer(dossier, url, connexion=None, limites=None):
    cfg = ConfigNavigateur(canal="auto", visible=False, profil=str(dossier / "profil"), dialogues="ignorer")
    nav = Navigateur(cfg, dossier, visible=False)
    nav.options_contexte = {"service_workers": "block"}
    nav.ouvrir()
    explorateur = Explorateur(nav, dossier / "carte", limites or Limites(minutes=5, delai_ms=0),
                              interactif=False, connexion=connexion)
    try:
        explorateur.explorer(url)
    finally:
        nav.fermer()
    return explorateur


def test_exploration_du_portail_sans_rien_modifier(portail, tmp_path, navigateur_ok):
    explorateur = _explorer(tmp_path, f"{portail}/accueil")
    requetes = list(_Portail.requetes)
    chemins = [c for _, c in requetes]

    # 1. rien de dangereux n'a atteint le serveur
    assert {m for m, _ in requetes} == {"GET"}, requetes
    for interdit in ("/deconnexion", "/plans/supprimer-tout", "/plans/nouveau", "/aide.pdf"):
        assert not any(c.startswith(interdit) for c in chemins), interdit
    assert not any(c.startswith("/api/") for c in chemins)
    # le bouton « Actualiser » a été essayé, mais son envoi de données a été bloqué dans le navigateur
    assert ("POST", "/api/plans/lecture") in explorateur.bloquees
    assert not any("/maj" in u or "corbeille" in u for _, u in explorateur.bloquees)  # jamais cliqués

    # 2. une grosse base n'est pas visitée en entier : deux exemples par modèle
    assert len({c for c in chemins if c.startswith("/composants/REF-")}) <= 2
    assert len({c for c in chemins if c.startswith("/plans/") and c[7:].isdigit()}) <= 2
    assert len({c for c in chemins if c.startswith("/composants?page=")}) <= 2

    # 3. les écrans attendus sont sur la carte, onglets compris
    titres = [e.titres[0] if e.titres else e.titre for e in explorateur.ecrans]
    assert "Accueil" in titres and "Composants" in titres and "Plans" in titres
    assert any(t.startswith("Composant REF-") for t in titres)
    fiches_plan = [e for e in explorateur.ecrans if (e.titres or [""])[0].startswith("Plan PL-")]
    entetes = {tuple(t["entetes"]) for e in fiches_plan for t in e.tableaux}
    assert ("Repère", "Composant") in entetes and ("Date", "Auteur", "Action") in entetes  # onglets visités
    resultats = " ".join(v for e in explorateur.ecrans for v in e.resultats.values())
    assert "risque (« supprim »)" in resultats and "risque (« imprim »)" in resultats
    assert "élément sans texte" in resultats

    # 4. la carte à partager ne contient pas les données
    partage = (tmp_path / "carte" / "carte_a_partager.txt").read_text(encoding="utf-8")
    for donnee in ("REF-", "PL-", "Disjoncteur", "confidentiel", "secret", "ACME", "127.0.0.1", "M. X", "bâtiment"):
        assert donnee not in partage, donnee
    assert "Référence | Désignation | Fabricant" in partage and "Titre [texte]" in partage
    assert (tmp_path / "carte" / "carte.html").exists() and (tmp_path / "carte" / "carte.json").exists()


def test_exploration_de_la_base_demo_une_seule_page(tmp_path, navigateur_ok):
    """Application d'une seule page (tout en boutons, comme beaucoup de portails d'entreprise)."""
    cli.preparer_bac_a_sable(tmp_path)
    serveur, url = cli._servir_dossier(tmp_path, "base_demo.html", port=0)

    def connexion(page):
        page.fill("#utilisateur", "demo")
        page.fill("#mot-de-passe", "demo")
        page.click("#btn-connexion")
        page.wait_for_selector("#liste:not([hidden])")

    try:
        explorateur = _explorer(tmp_path, url, connexion=connexion)
    finally:
        serveur.shutdown()
        serveur.server_close()
    assert len(explorateur.ecrans) == 3  # liste vide, liste remplie après « Rechercher », fiche d'un plan
    fiche = explorateur.ecrans[2]
    assert fiche.modele.endswith("#fiche={}")
    assert {c["libelle"] for c in fiche.champs} >= {"Titre", "Statut", "Indice", "Commentaire"}
    assert fiche.resultats["Enregistrer"].startswith("non cliqué")


def test_limite_d_ecrans_respectee(portail, tmp_path, navigateur_ok):
    explorateur = _explorer(tmp_path, f"{portail}/accueil", limites=Limites(ecrans=2, minutes=5, delai_ms=0))
    assert len(explorateur.ecrans) == 2 and "limite de 2 écrans" in explorateur.arret


@pytest.mark.parametrize("texte", ["Supprimer", "Se déconnecter", "Nouveau plan", "Exporter CSV", "Enregistrer",
                                   "Valider la diffusion", "Imprimer", "Créer", "Modifier", "Réinitialiser"])
def test_mots_d_action_interdits(texte):
    assert mot_interdit(texte)


@pytest.mark.parametrize("texte", ["Général", "Attributs", "Archives", "Pays", "Consignes", "Terminal",
                                   "Composants", "Historique", "Rechercher"])
def test_mots_de_consultation_permis(texte):
    assert not mot_interdit(texte)


def test_lecture_et_modeles():
    assert est_lecture("Rechercher") and est_lecture("Voir le détail") and not est_lecture("Général")
    assert modele_url("https://portail/plans/1234/fiche?onglet=2#fiche=X") == "/plans/{id}/fiche?onglet={}#fiche={}"
    assert masquer("Plan PL-12 de a.b@c.fr, mène à E4") == "Plan # de <email>, mène à E4"

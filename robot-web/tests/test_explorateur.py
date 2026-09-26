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
from autoweb.explorateur import (Action, Explorateur, Limites, adresse_action, est_lecture, masquer,
                                 modele_url, mot_interdit)
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
                 ".then(()=>document.body.dataset.ok=1).catch(()=>document.body.dataset.ko=1)\">Afficher les alertes</button>"
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
    # « Afficher les alertes » a été essayé, mais son envoi de données a été bloqué dans le navigateur
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
    assert "sans texte" in resultats

    # 4. la carte à partager ne contient pas les données
    partage = (tmp_path / "carte" / "carte_a_partager.txt").read_text(encoding="utf-8")
    for donnee in ("REF-", "PL-", "Disjoncteur", "confidentiel", "secret", "ACME", "127.0.0.1", "M. X", "bâtiment"):
        assert donnee not in partage, donnee
    assert "Référence | Désignation | Fabricant" in partage and "Titre [texte]" in partage
    assert "onglets : Composants ; Général ; Historique" in partage
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
                                   "Valider la diffusion", "Imprimer", "Créer", "Modifier", "Réinitialiser",
                                   "Renvoyer", "Relancer", "Dévalider", "Désassigner", "Unpublish", "Approve",
                                   "Suppr.", "MàJ", "Aperçu avant impression", "Oui", "OK", "Appliquer",
                                   "Changer le statut", "Marquer comme obsolète", "archive", "push_pin"])
def test_mots_d_action_interdits(texte):
    assert mot_interdit(texte)


@pytest.mark.parametrize("texte", ["Général", "Attributs", "Archives", "Pays", "Consignes", "Terminal",
                                   "Composants", "Historique", "Rechercher", "Connecteurs", "Révisions",
                                   "Demandes", "Nomenclatures", "Marquage"])
def test_mots_de_consultation_permis(texte):
    assert not mot_interdit(texte)


def test_lecture_et_modeles():
    assert est_lecture("Rechercher") and est_lecture("Voir le détail") and not est_lecture("Général")
    assert not est_lecture("Tout marquer comme lu") and not est_lecture("Ouvrir un ticket")
    assert modele_url("https://portail/plans/1234/fiche?onglet=2#fiche=X12") == "/plans/{id}/fiche?onglet={}#fiche={}"
    # portail « à paramètre » : chaque module est un écran différent, pas chaque numéro
    assert modele_url("https://p/index.php?module=plans&id=77") == "/index.php?id={}&module=plans"
    assert masquer("Plan PL-12 de a.b@c.fr, armoire E12") == "Plan # de <email>, armoire #"
    assert adresse_action("https://p/plans.php?action=del&id=2") and adresse_action("https://p/api/plans/7/supprimer")
    assert adresse_action("https://p/index.php?module=plans&action=voir") is None


# ---------------------------------------------------------------------- pièges trouvés en relecture
def _serveur(routes):
    """Petit portail : chemin -> HTML ; chaque requête reçue est notée."""
    requetes = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _r(self):
            requetes.append((self.command, self.path))
            corps = routes.get(urlsplit(self.path).path, "<title>ok</title>ok").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        do_GET = do_POST = do_DELETE = _r

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f"http://127.0.0.1:{serveur.server_address[1]}", requetes


def _explorer_routes(tmp_path, routes, depart="/", limites=None):
    serveur, base, requetes = _serveur(routes)
    try:
        explorateur = _explorer(tmp_path, base + depart, limites=limites)
    finally:
        serveur.shutdown()
        serveur.server_close()
    return explorateur, [c for _, c in requetes]


def test_rien_n_est_clique_si_l_ecran_a_change_entre_verification_et_clic(tmp_path, navigateur_ok):
    """La vérification et le clic ont lieu dans le même instant : un bouton remplacé n'est pas cliqué."""
    serveur, base, requetes = _serveur({"/": "<title>t</title><div id=barre><button type=button>Voir</button></div>"})
    cfg = ConfigNavigateur(canal="auto", visible=False, dialogues="ignorer")
    nav = Navigateur(cfg, tmp_path, visible=False)
    nav.ouvrir()
    try:
        explorateur = Explorateur(nav, tmp_path / "carte", Limites(delai_ms=0), interactif=False)
        page = nav.page
        page.goto(base + "/")
        cible = explorateur._lire(page)["cibles"][0]
        assert explorateur._decision(cible)[0] == "clic"
        page.evaluate("document.getElementById('barre').innerHTML = "
                      "'<button type=button onclick=\"fetch(\\'/api/supprimer\\')\">Supprimer le plan</button>'")
        pas = Action("clic", selecteur=cible["selecteur"], texte="Voir", attendu=explorateur._attendu(cible))
        assert explorateur._jouer(page, pas).startswith("l'élément a changé")
        page.wait_for_timeout(300)
        assert not any("/api/" in c for _, c in requetes)
    finally:
        nav.fermer()
        serveur.shutdown()
        serveur.server_close()


def test_ligne_cliquable_sans_toucher_la_case_a_cocher_du_milieu(tmp_path, navigateur_ok):
    lignes = "".join(
        f"<tr onclick=\"location.href='/fiche/{i}'\"><td>C{i}</td><td class=c><input type=checkbox class=actif checked data-id={i}></td><td>X</td></tr>"
        for i in range(1, 4))
    liste = ("<title>Liste</title><style>table{width:600px}td.c{text-align:center}</style>"
             "<table><thead><tr><th>Réf</th><th>Actif</th><th>Fab</th></tr></thead><tbody>" + lignes + "</tbody></table>"
             "<script>document.querySelectorAll('.actif').forEach(c => {"
             "c.addEventListener('click', ev => ev.stopPropagation());"
             "c.addEventListener('change', () => fetch('/etat/' + c.dataset.id + '?valeur=' + c.checked)); });</script>")
    explorateur, chemins = _explorer_routes(tmp_path, {"/": liste, "/fiche/1": "<title>Fiche</title><h1>Fiche</h1>"})
    assert not any(c.startswith("/etat/") for c in chemins), chemins
    assert "/fiche/1" in chemins  # la ligne a bien été ouverte


def test_fenetre_de_confirmation_jamais_cliquee(tmp_path, navigateur_ok):
    lignes = "".join(f"<tr><td><a href=/plans/{i}>Plan</a></td><td><button type=button onclick='modale({i})'>×</button></td></tr>"
                     for i in range(1, 3))
    page = ("<title>Plans</title><table><thead><tr><th>Plan</th><th></th></tr></thead><tbody>" + lignes + "</tbody></table>"
            "<div id=m class=modal hidden><p>Supprimer définitivement ?</p><a href=# id=oui>Oui</a><button>Non</button></div>"
            "<button type=button onclick=\"document.getElementById('m').hidden=false\">Voir les alertes</button>"
            "<script>function modale(i){const m=document.getElementById('m');m.hidden=false;"
            "document.getElementById('oui').onclick=()=>location.href='/plans.php?op=destroy&id='+i;}"
            "document.getElementById('oui').onclick=()=>location.href='/plans.php?op=destroy&id=9';</script>")
    explorateur, chemins = _explorer_routes(tmp_path, {"/": page})
    assert not any(c.startswith("/plans.php") for c in chemins), chemins
    resultats = " ".join(v for e in explorateur.ecrans for v in e.resultats.values())
    assert "fenêtre de confirmation" in resultats  # la fenêtre a été vue, rien n'y a été cliqué


def test_requete_get_qui_ressemble_a_une_action_bloquee(tmp_path, navigateur_ok):
    page = ("<title>Plan</title><h1>Plan</h1>"
            "<button type=button onclick=\"fetch('/api/plans/7/supprimer'); new Image().src='/api/plans/7/delete.gif'\">"
            "Voir le détail</button>")
    explorateur, chemins = _explorer_routes(tmp_path, {"/": page})
    assert not any(c.startswith("/api/") for c in chemins), chemins
    assert explorateur.bloquees


def test_page_de_depart_avec_un_mot_d_action_dans_l_adresse(tmp_path, navigateur_ok):
    routes = {"/_layouts/15/start.aspx": "<title>Accueil</title><nav><a href=/Pages/plans.aspx>Plans</a></nav>",
              "/Pages/plans.aspx": "<title>Plans</title><h1>Plans</h1><div role=tablist>"
                                   "<button role=tab onclick=\"document.body.dataset.o=1\">Détails</button></div>"}
    explorateur, chemins = _explorer_routes(tmp_path, routes, depart="/_layouts/15/start.aspx")
    assert "/Pages/plans.aspx" in chemins and len(explorateur.ecrans) >= 2
    assert explorateur.complet


def test_portail_a_parametre_module(tmp_path, navigateur_ok):
    nav_html = "".join(f"<a href='/index.php?module={m}'>{m.title()}</a> " for m in ("plans", "composants", "affaires"))
    routes = {"/index.php": "<title>Portail</title><nav>" + nav_html + "</nav><h1>Module</h1>"}

    def module(nom):
        return f"<title>{nom}</title><nav>{nav_html}</nav><h2>{nom}</h2><label for=f>Filtre {nom}</label><input id=f>"

    explorateur, chemins = _explorer_routes(tmp_path, routes, depart="/index.php")
    vus = {c for c in chemins if "module=" in c}
    assert {"/index.php?module=plans", "/index.php?module=composants", "/index.php?module=affaires"} <= vus


def test_carte_a_partager_sans_noms_de_clients_ni_de_personnes(tmp_path, navigateur_ok):
    accueil = """<title>GED</title>
<header><a href=/affaires>Affaires</a> <div role=button onclick="this.dataset.o=1">Sophie Marchand</div></header>
<nav aria-label=Breadcrumb class=breadcrumb><a href=/>Accueil</a> › <a href=/clients/dupont-industrie>Dupont Industrie</a></nav>
<aside><h3>Consultés récemment</h3><a href=/ged/poste-villeurbanne>Poste source Villeurbanne</a>
<a href=/ged/tgbt-michelin>TGBT usine Michelin gros site</a></aside>
<label>Client <select><option>Tous<option>SNCF Réseau<option>Enedis</select></label>
<input placeholder="ex. Jean Dupont">
<table><thead><tr><th>Chargé d'affaires <select><option>Paul Girard<option>Léa Rousseau</select></th><th>Site</th></tr></thead>
<tbody><tr><td><a href=/affaires/lyon-est>Usine Lyon Est</a></td><td>Madame Lefebvre</td></tr></tbody></table>
<div role=button onclick="this.dataset.o=1">Réclamation Michelin défaut armoire</div>
<label><input type=checkbox> Madame Lefebvre</label>"""
    explorateur, _ = _explorer_routes(tmp_path, {"/": accueil})
    partage = (tmp_path / "carte" / "carte_a_partager.txt").read_text(encoding="utf-8")
    for donnee in ("Sophie", "Marchand", "Dupont", "Villeurbanne", "Michelin", "SNCF", "Enedis", "Jean", "Girard",
                   "Rousseau", "Lefebvre", "Lyon", "Réclamation", "127.0.0.1", "dupont-industrie"):
        assert donnee not in partage, donnee
    assert "Client [liste, 3 choix]" in partage and "Chargé d'affaires | Site" in partage


def test_retour_de_connexion_d_entreprise_permis_mais_pas_les_envois_de_donnees():
    from autoweb.explorateur import MOTIF_RETOUR_CONNEXION

    for chemin in ("/saml/acs", "/Saml2/Acs", "/signin-oidc", "/Shibboleth.sso/SAML2/POST", "/login/oauth2/code/azure"):
        assert MOTIF_RETOUR_CONNEXION.search(chemin), chemin
    for chemin in ("/api/plans/7", "/api/saml-settings/update", "/admin/sso/config", "/plans/acs-list/save"):
        assert not MOTIF_RETOUR_CONNEXION.search(chemin), chemin

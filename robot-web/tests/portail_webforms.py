"""Faux portail ASP.NET WebForms pour les tests : tout passe par des envois de formulaire (__doPostBack)."""
import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PLANS = {"12": "Poste source Nord", "13": "Poste HTA Sud", "14": "Transformateur T2"}


def page(titre, corps, vue="", action="/Default.aspx"):
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{titre}</title>
<style>.sub{{display:none}} li:hover .sub{{display:block}}</style></head><body>
<form method=post action="{action}" id=aspnetForm>
<input type=hidden name=__VIEWSTATE value="vs-{vue}"><input type=hidden name=__EVENTTARGET id=__EVENTTARGET value="">
<input type=hidden name=__EVENTARGUMENT id=__EVENTARGUMENT value="">
<script>function __doPostBack(t, a) {{ var f = document.getElementById('aspnetForm'); f.__EVENTTARGET.value = t; f.__EVENTARGUMENT.value = a; f.submit(); }}</script>
<div id=menu><ul>
 <li><a href="javascript:__doPostBack('ctl00$Menu','Accueil')">Accueil</a></li>
 <li><a href="javascript:__doPostBack('ctl00$Menu','Plans')">Plans</a></li>
 <li><a href="#">Composants</a><ul class=sub><li><a href="/Composants.aspx">Recherche de composants</a></li>
     <li><a href="/Fournisseurs.aspx">Fournisseurs</a></li></ul></li>
</ul></div>
<h1>{titre}</h1>{corps}</form></body></html>"""


def accueil():
    return page("Accueil", "<p>Bienvenue sur le portail des plans.</p>", "accueil")


def recherche(resultats=None, terme=""):
    corps = """<table><tr><td><label for=txtNum>Numéro</label></td><td><input name="ctl00$Main$txtNum" id=txtNum></td></tr>
<tr><td><label for=txtTitre>Titre</label></td><td><input name="ctl00$Main$txtTitre" id=txtTitre></td></tr>
<tr><td><label for=ddlStatut>Statut</label></td><td><select name="ctl00$Main$ddlStatut" id=ddlStatut><option>Tous</option><option>Publié</option></select></td></tr>
<tr><td colspan=2><input type=submit name="ctl00$Main$btnRechercher" value="Rechercher" id=btnRechercher>
<input type=submit name="ctl00$Main$btnNouveau" value="Nouveau plan" id=btnNouveau></td></tr></table>"""
    if resultats is not None:
        lignes = "".join(
            f"<tr><td><a href=\"javascript:__doPostBack('ctl00$Main$gvPlans','Select${i}')\">PL-{n}</a></td><td>{html.escape(t)}</td>"
            f"<td>Publié</td><td><a href=\"javascript:__doPostBack('ctl00$Main$gvPlans','Delete${i}')\">Supprimer</a>"
            f" <a href=\"javascript:__doPostBack('ctl00$Main$gvPlans','Edit${i}')\">Éditer</a></td></tr>"
            for i, (n, t) in enumerate(resultats))
        corps += ("<table id=gvPlans><tr><th>Numéro</th><th>Titre</th><th>Statut</th><th></th></tr>" + lignes + "</table>"
                  "<a href=\"javascript:__doPostBack('ctl00$Main$gvPlans','Page$2')\">2</a>")
    return page("Recherche de plans", corps, "recherche")


def fiche(numero, onglet="general"):
    contenu = {
        "general": f"<dl><dt>Numéro</dt><dd>PL-{numero}</dd><dt>Titre</dt><dd>{PLANS.get(numero, '?')}</dd><dt>Indice</dt><dd>B</dd></dl>",
        "revisions": "<table><tr><th>Indice</th><th>Date</th><th>Auteur</th></tr><tr><td>A</td><td>01/02</td><td>M. Martin</td></tr></table>",
        "documents": f"<a href=/docs/PL-{numero}.pdf>Plan PL-{numero}.pdf</a>",
    }[onglet]
    corps = (f"<input type=hidden name=hidNum value={numero}>"
             "<div class=tabs>"
             + "".join(f"<a href=\"javascript:__doPostBack('ctl00$Main$tabs','{o}')\">{l}</a> "
                       for o, l in (("general", "Général"), ("revisions", "Révisions"), ("documents", "Documents")))
             + "</div>"
             f"<div id=contenu>{contenu}</div>"
             "<input type=submit name=\"ctl00$Main$btnDupliquer\" value=\"Dupliquer\">"
             "<input type=submit name=\"ctl00$Main$btnSupprimer\" value=\"Supprimer\">"
             "<button type=button onclick=\"fetch('/api/historique?id=" + numero + "').then(r=>r.text()).then(t=>document.getElementById('contenu').textContent=t)\">Historique</button>")
    return page(f"Plan PL-{numero}", corps, f"fiche{numero}{onglet}")


class Portail(BaseHTTPRequestHandler):
    envois = []

    def log_message(self, *args):
        pass

    def _repondre(self, corps, type_contenu="text/html; charset=utf-8"):
        donnees = corps.encode() if isinstance(corps, str) else corps
        self.send_response(200)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    def do_GET(self):
        chemin = urlsplit(self.path).path
        if chemin.startswith("/api/historique"):
            return self._repondre("Historique : 2 révisions", "text/plain")
        if chemin.startswith("/docs/"):
            return self._repondre(b"%PDF-1.4 x", "application/pdf")
        if chemin == "/Composants.aspx":
            return self._repondre(page("Recherche de composants",
                                       "<label for=q>Référence</label><input id=q name=q type=search>"
                                       "<input type=submit value=Chercher name=\"ctl00$Main$btnChercher\">",
                                       "composants", action="/Composants.aspx"))
        if chemin == "/Fournisseurs.aspx":
            return self._repondre(page("Fournisseurs", "<table><tr><th>Nom</th><th>Pays</th></tr><tr><td>ACME</td><td>FR</td></tr></table>", "fourn"))
        return self._repondre(accueil())

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(n).decode()
        type(self).envois.append(corps)
        d = {k: v[0] for k, v in parse_qs(corps, keep_blank_values=True).items()}
        cible, arg = d.get("__EVENTTARGET", ""), d.get("__EVENTARGUMENT", "")
        chemin = urlsplit(self.path).path
        if chemin == "/Composants.aspx":
            return self._repondre(page("Composants trouvés", "<table><tr><th>Référence</th><th>Désignation</th></tr>"
                                       "<tr><td>C-1</td><td>Disjoncteur</td></tr></table>", "comp-res", action="/Composants.aspx"))
        if cible == "ctl00$Menu":
            return self._repondre(recherche() if arg == "Plans" else accueil())
        if "ctl00$Main$btnRechercher" in d:
            return self._repondre(recherche(list(PLANS.items())))
        if cible == "ctl00$Main$gvPlans" and arg.startswith("Select$"):
            i = int(arg.split("$")[1])
            return self._repondre(fiche(list(PLANS)[i]))
        if cible == "ctl00$Main$gvPlans" and arg.startswith("Page$"):
            return self._repondre(recherche(list(PLANS.items())[:1]))
        if cible == "ctl00$Main$tabs":
            return self._repondre(fiche(d.get("hidNum", "12"), arg))
        return self._repondre(accueil())


def demarrer():
    Portail.envois = []
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Portail)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f"http://127.0.0.1:{serveur.server_address[1]}/Default.aspx"

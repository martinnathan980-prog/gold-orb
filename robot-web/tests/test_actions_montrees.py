"""Actions montrées au robot : dupliquer un plan (le plan de départ est demandé au
lancement, la copie s'ouvre dans un nouvel onglet) et supprimer un plan (confirmation
OUI obligatoire). Le fichier « à partager » décrit les gestes sans aucune valeur."""

import builtins
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from autoweb.assistant import Dialogue, construire_depuis_enregistrement
from autoweb.enregistreur import Enregistreur
from autoweb.navigateur import Navigateur
from autoweb.runner import Options, etapes_de_suppression, lancer
from autoweb.scenario import ConfigNavigateur, charger

PLANS = """<!doctype html><meta charset=utf-8><title>Plans</title><h1>Plans</h1>
<label for=recherche>Numéro de plan</label><input id=recherche>
<button type=button id=chercher onclick="chercher()">Rechercher</button>
<table><thead><tr><th>Numéro</th><th>Titre</th></tr></thead><tbody id=res></tbody></table>
<script>
function chercher() {
  const q = document.getElementById('recherche').value.trim();
  document.getElementById('res').innerHTML = [3, 5, 7].map(i => 'PL-' + i).filter(n => n === q)
    .map(n => '<tr><td><a href="/plans/fiche?n=' + n + '">' + n + '</a></td><td>Tableau général</td></tr>').join('');
}
</script>"""

FICHE = """<!doctype html><meta charset=utf-8><title>Fiche</title><h1 id=num></h1>
<button type=button id=dupliquer onclick="window.open('/plans/nouveau?source=' + n)">Dupliquer</button>
<button type=button id=supprimer onclick="if (confirm('Supprimer ce plan ?')) fetch('/api/plans/' + n, {method: 'DELETE'})
  .then(() => document.getElementById('msg').textContent = 'Plan supprimé')">Supprimer</button>
<p id=msg></p>
<script>const n = new URLSearchParams(location.search).get('n'); document.getElementById('num').textContent = 'Plan ' + n;</script>"""

NOUVEAU = """<!doctype html><meta charset=utf-8><title>Nouveau plan</title><h1>Nouveau plan</h1>
<label for=titre>Titre</label><input id=titre required>
<label for=indice>Indice</label><input id=indice>
<label for=contrat>Contrat</label><select id=contrat><option>HDK</option><option>QRS</option></select>
<button type=button id=enregistrer onclick="fetch('/api/plans', {method: 'POST', body: JSON.stringify({
  source: new URLSearchParams(location.search).get('source'), titre: document.getElementById('titre').value,
  indice: document.getElementById('indice').value})}).then(() => document.getElementById('ok').textContent = 'Plan créé')">Enregistrer</button>
<p id=ok></p>"""


class _Portail(BaseHTTPRequestHandler):
    envois = []

    def log_message(self, *args):
        pass

    def _repondre(self):
        chemin = urlsplit(self.path).path
        if self.command != "GET":
            longueur = int(self.headers.get("Content-Length") or 0)
            corps = self.rfile.read(longueur).decode("utf-8") if longueur else ""
            type(self).envois.append((self.command, chemin, corps))
            html = "ok"
        else:
            html = {"/plans": PLANS, "/plans/fiche": FICHE, "/plans/nouveau": NOUVEAU}.get(chemin, "<title>x</title>x")
        donnees = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    do_GET = do_POST = do_DELETE = _repondre


@pytest.fixture
def portail():
    _Portail.envois = []
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Portail)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{serveur.server_address[1]}"
    finally:
        serveur.shutdown()
        serveur.server_close()


def _enregistrer(dossier, url, geste):
    nav = Navigateur(ConfigNavigateur(canal="auto", visible=False), dossier, visible=False)
    nav.ouvrir()
    enregistreur = Enregistreur(nav)
    try:
        page = enregistreur.demarrer(url)
        page.wait_for_selector("#__autoweb_badge")
        geste(page)
        page.wait_for_timeout(1200)
        return enregistreur.arreter()
    finally:
        nav.fermer()


def _chercher_et_ouvrir(page, numero):
    page.fill("#recherche", numero)
    page.click("#chercher")
    page.click(f"text={numero}")
    page.wait_for_selector("#dupliquer")
    page.wait_for_timeout(900)  # la photo de l'écran est prise après le chargement


def test_dupliquer_un_plan_montre_une_fois_rejoue_avec_un_autre_plan(portail, tmp_path, navigateur_ok):
    def geste(page):
        _chercher_et_ouvrir(page, "PL-3")
        with page.expect_popup() as info:
            page.click("#dupliquer")
        copie = info.value
        copie.wait_for_selector("#titre")
        copie.wait_for_timeout(900)
        copie.fill("#titre", "Titre de la copie")
        copie.click("#enregistrer")
        copie.wait_for_selector("text=Plan créé")

    etapes = _enregistrer(tmp_path, f"{portail}/plans", geste)
    assert _Portail.envois and json.loads(_Portail.envois[0][2])["source"] == "PL-3"  # le geste réel a bien eu lieu
    _Portail.envois = []
    reponses = [
        "",                # ne rien retirer
        "plan de départ",  # « PL-3 » change à chaque fois
        "titre",           # « Titre de la copie » aussi
        "",                # pas de texte de contrôle
        "n",               # pas de connexion à la main
        "n",               # pas de capture
    ]
    partage: dict = {}
    texte = construire_depuis_enregistrement(
        etapes, [], [], Dialogue(reponses), nom="dupliquer un plan", fichier_excel=None,
        canal="chromium", url_depart=f"{portail}/plans", sortie_partage=partage,
    )
    donnees = yaml.safe_load(texte)
    assert donnees["questions"] == {"plan_de_depart": "Plan de départ", "titre": "Titre"}
    assert {"remplir": {"selecteur": "#recherche", "valeur": "{{plan_de_depart}}"}} in donnees["etapes"]
    assert {"cliquer": {"selecteur": "#dupliquer", "nouvel_onglet": True}} in donnees["etapes"]
    assert "PL-3" not in texte and "Titre de la copie" not in texte

    # ---- la description à partager : les gestes et les champs, jamais les valeurs
    description = partage["texte"]
    assert "Valeurs demandées à chaque lancement : Plan de départ ; Titre" in description
    assert "(ouvre un nouvel onglet)" in description
    assert "Titre [text, obligatoire] vide" in description and "Indice [text] vide" in description
    assert "Contrat [liste] rempli" in description
    for donnee in ("PL-3", "Titre de la copie", "127.0.0.1", "Tableau général"):
        assert donnee not in description, donnee

    # ---- rejouée sur un AUTRE plan, avec un autre titre
    chemin = tmp_path / "dupliquer.yaml"
    chemin.write_text(texte, encoding="utf-8")
    bilan = lancer(charger(chemin), Options(visible=False, interactif=False,
                                            variables={"plan_de_depart": "PL-5", "titre": "Titre robot"}))
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume()
    envoi = json.loads(_Portail.envois[-1][2])
    assert envoi["source"] == "PL-5" and envoi["titre"] == "Titre robot"


def test_supprimer_un_plan_demande_oui_avant_de_partir(portail, tmp_path, monkeypatch, navigateur_ok):
    def geste(page):
        _chercher_et_ouvrir(page, "PL-7")
        page.click("#supprimer")  # la confirmation du portail est acceptée pendant l'enregistrement
        page.wait_for_selector("text=Plan supprimé")

    etapes = _enregistrer(tmp_path, f"{portail}/plans", geste)
    _Portail.envois = []
    texte = construire_depuis_enregistrement(
        etapes, [], [], Dialogue(["", "plan à supprimer", "", "n", "n"]), nom="supprimer un plan",
        fichier_excel=None, canal="chromium", url_depart=f"{portail}/plans",
    )
    chemin = tmp_path / "supprimer.yaml"
    chemin.write_text(texte, encoding="utf-8")
    scenario = charger(chemin)
    assert etapes_de_suppression(scenario) and scenario.confirmer  # proposé par défaut, la tâche supprime

    # le numéro est demandé d'abord, puis le robot récapitule et attend OUI ; autre chose : rien n'est fait
    reponses = iter(["PL-5", "non"])
    monkeypatch.setattr(builtins, "input", lambda *a: next(reponses))
    bilan = lancer(scenario, Options(visible=False, interactif=True))
    assert bilan.interrompu and "non confirmée" in bilan.message
    assert not _Portail.envois

    # le numéro, puis OUI : le plan est supprimé
    reponses = iter(["PL-5", "OUI"])
    monkeypatch.setattr(builtins, "input", lambda *a: next(reponses))
    bilan = lancer(scenario, Options(visible=False, interactif=True))
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume()
    assert _Portail.envois == [("DELETE", "/api/plans/PL-5", "")]


def test_jamais_le_plan_voisin_quand_le_numero_demande_n_existe_pas(portail, tmp_path, navigateur_ok):
    """Plans PL-3, PL-5, PL-7 : demander PL-1 ou PL- ne doit JAMAIS viser une autre ligne."""
    def geste(page):
        page.fill("#recherche", "PL-7")
        page.click("#chercher")
        page.click("text=PL-7")
        page.wait_for_selector("#supprimer")

    etapes = _enregistrer(tmp_path, f"{portail}/plans", geste)
    texte = construire_depuis_enregistrement(
        etapes, [], [], Dialogue(["", "oui", "", "", "n", "n", "o"]), nom="ouvrir un plan",
        fichier_excel=None, canal="chromium", url_depart=f"{portail}/plans",
    )
    donnees = yaml.safe_load(texte)
    # « oui » à la question : le robot demande un nom et propose le libellé du champ
    assert donnees["questions"] == {"numero_de_plan": "Numéro de plan"}
    chemin = tmp_path / "ouvrir.yaml"
    chemin.write_text(texte, encoding="utf-8")
    for demande in ("PL-", "L-7"):
        bilan = lancer(charger(chemin), Options(visible=False, interactif=False,
                                                variables={"numero_de_plan": demande}))
        assert bilan.erreurs == 1, (demande, bilan.resume())  # rien trouvé : erreur, aucune autre ligne ouverte
    bilan = lancer(charger(chemin), Options(visible=False, interactif=False, variables={"numero_de_plan": "PL-5"}))
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume()

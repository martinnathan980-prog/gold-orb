"""Relance d'une tâche derrière une page de connexion : le robot ne reste plus planté à attendre
Entrée dans la fenêtre noire. Déjà connecté, il continue tout de suite ; sinon il montre un bandeau
dans SA fenêtre et repart tout seul dès que l'outil s'affiche."""

import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from autoweb import console
from autoweb.runner import Options, lancer
from autoweb.scenario import charger

OUTIL = ("<!doctype html><meta charset=utf-8><title>Outil</title><h1>Recherche de plans</h1>"
         "<input id=num aria-label=Numéro><button id=go onclick=\"fetch('/chercher?n=' + num.value)\">Rechercher</button>")
# la « connexion d'entreprise » se termine toute seule après 2 s (comme un SSO après le mot de passe)
CONNEXION = ("<!doctype html><meta charset=utf-8><title>Connexion</title><h1>Connectez-vous</h1>"
             "<input type=password><script>setTimeout(() => { document.cookie = 'ok=1; path=/'; location.href = '/'; }, 2000)"
             "</script>")


class _Outil(BaseHTTPRequestHandler):
    recherches = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/chercher"):
            type(self).recherches.append(self.path)
        corps = OUTIL if "ok=1" in (self.headers.get("Cookie") or "") else CONNEXION
        donnees = corps.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)


@pytest.fixture
def outil():
    _Outil.recherches = []
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Outil)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{serveur.server_address[1]}/"
    finally:
        serveur.shutdown()
        serveur.server_close()


def _tache(dossier, url, attente):
    chemin = dossier / "recherche.yaml"
    chemin.write_text(f"""nom: recherche
navigateur: {{canal: auto, visible: false, profil: profil}}
variables: {{url: "{url}"}}
avant:
  - aller: "{{{{url}}}}"
  - {attente}
etapes:
  - aller: "{{{{url}}}}"
  - remplir: {{selecteur: "#num", valeur: "PL-12"}}
  - cliquer: "#go"
  - patienter: 300
""", encoding="utf-8")
    return charger(chemin)


@pytest.mark.parametrize("attente", [
    'pause: "Vérifiez que vous êtes bien connecté dans le navigateur, puis appuyez sur Entrée"',  # tâches v19
    'connexion: "Connectez-vous dans cette fenêtre si votre outil le demande."',
])
def test_relance_attend_la_connexion_puis_repart_toute_seule(outil, tmp_path, monkeypatch, navigateur_ok, attente):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(console, "touche_entree_disponible", lambda: False)  # personne ne tape Entrée
    monkeypatch.setattr(console, "vider_clavier", lambda: None)
    scenario = _tache(tmp_path, outil, attente)

    debut = time.monotonic()
    bilan = lancer(scenario, Options(visible=False, interactif=True))
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume()
    assert _Outil.recherches == ["/chercher?n=PL-12"]
    assert time.monotonic() - debut < 25

    # deuxième lancement : déjà connecté (même Chrome du robot), aucune attente
    debut = time.monotonic()
    bilan = lancer(scenario, Options(visible=False, interactif=True))
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume()
    assert len(_Outil.recherches) == 2
    assert time.monotonic() - debut < 12


def test_bandeau_continuer_dans_la_page(outil, tmp_path, monkeypatch, navigateur_ok):
    """Une pause ordinaire se termine aussi par le bouton « Continuer » du bandeau, dans Chrome."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(console, "touche_entree_disponible", lambda: False)
    monkeypatch.setattr(console, "vider_clavier", lambda: None)
    chemin = tmp_path / "pause.yaml"
    chemin.write_text(f"""nom: pause
navigateur: {{canal: auto, visible: false, profil: profil}}
etapes:
  - aller: "{outil}"
  - executer_js: "setTimeout(() => document.querySelector('#__autoweb_attente button').click(), 1500)"
  - pause: "Vérifiez le formulaire à l'écran"
""", encoding="utf-8")
    debut = time.monotonic()
    bilan = lancer(charger(chemin), Options(visible=False, interactif=True))
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume()
    assert time.monotonic() - debut < 20


def test_adresse_tapee_dans_la_barre_de_chrome_est_rejouee():
    """Pendant l'enregistrement, l'utilisateur tape l'adresse de son outil dans la barre de Chrome (le robot
    ne voit pas cette barre) : la tâche doit ouvrir cette adresse. Les redirections (connexion) et les pages
    ouvertes par un clic ou par Entrée ne deviennent pas des « ouvrir »."""
    from autoweb.enregistreur import Evenement, construire_etapes

    evenements = [
        Evenement("page", {"url": "https://www.google.com/", "titre": ""}, t=0.0),
        Evenement("navigation", {"url": "https://www.google.com/"}, t=0.2),                 # le départ lui-même
        Evenement("navigation", {"url": "https://portail.entreprise.fr/login"}, t=20.0),    # tapée en haut
        Evenement("navigation", {"url": "https://portail.entreprise.fr/accueil"}, t=21.0),  # redirection
        Evenement("saisie", {"selecteur": "#num", "valeur": "PL-12", "tag": "input", "type": "text"}, t=30.0),
        Evenement("touche", {"selecteur": "#num", "touche": "Enter", "tag": "input"}, t=31.0),
        Evenement("navigation", {"url": "https://portail.entreprise.fr/plans?n=PL-12"}, t=32.0),  # après Entrée
    ]
    etapes = construire_etapes(evenements)
    allers = [e.args["url"] for e in etapes if e.action == "aller"]
    assert allers == ["https://www.google.com/", "https://portail.entreprise.fr/login"], allers
    assert [e.action for e in etapes if e.action != "attendre"][-2:] == ["remplir", "touche"]

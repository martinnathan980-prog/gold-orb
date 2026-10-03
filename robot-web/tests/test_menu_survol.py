"""Menus déroulants au survol (cas réel : « GATES » > « Données MK1 »).

Le portail ne crée le sous-menu qu'au passage de la souris, et chaque entrée de menu contient
son sous-menu. Avant la version 23, le robot notait tout le bloc du menu
(li:has-text("GATES Données MK1 Données MK2 ...")) et ne le retrouvait jamais à la relance.
Maintenant : survol de « GATES » noté, clic noté par le texte exact, relance réussie."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml

from autoweb.assistant import Dialogue, construire_depuis_enregistrement
from autoweb.enregistreur import Enregistreur
from autoweb.navigateur import Navigateur
from autoweb.runner import Options, lancer
from autoweb.scenario import ConfigNavigateur, charger

ACCUEIL = """<!doctype html><meta charset=utf-8><title>Portail</title>
<style>
  .barre { list-style: none; display: flex; gap: 30px; margin: 0; padding: 10px; background: #eee; }
  .barre > li { position: relative; cursor: pointer; padding: 4px; }
  .sous { list-style: none; position: absolute; top: 100%; left: 0; background: #fff; border: 1px solid #999;
          padding: 4px; margin: 0; min-width: 160px; }
  .css .sous { display: none; }
  .css:hover .sous { display: block; }
  .sous li { padding: 4px; cursor: pointer; white-space: nowrap; }
</style>
<div class=entete><ul class=barre>
  <li id=gates><span>GATES</span></li>
  <li class=css>BOX<ul class=sous>
    <li onclick="location='/page?n=box1'"><span>Données MK1 bis</span></li>
    <li onclick="location='/page?n=box2'"><span>Nouveau rep.</span></li>
  </ul></li>
  <li onclick="location='/page?n=aide'">Aide</li>
</ul></div>
<h1>Accueil</h1>
<script>
  // sous-menu fabriqué seulement au survol, retiré quand la souris s'en va
  const g = document.getElementById('gates');
  g.addEventListener('mouseenter', () => {
    if (g.querySelector('ul')) return;
    const u = document.createElement('ul'); u.className = 'sous';
    for (const [t, n] of [['Données MK1', 'mk1'], ['Données MK2', 'mk2'], ['Nouveau rep. e', 'rep']]) {
      const li = document.createElement('li');
      li.innerHTML = '<span></span>'; li.firstChild.textContent = t;
      li.onclick = (ev) => { ev.stopPropagation(); location = '/page?n=' + n; };
      u.appendChild(li);
    }
    g.appendChild(u);
  });
  g.addEventListener('mouseleave', () => { const u = g.querySelector('ul'); if (u) u.remove(); });
</script>"""


class _Portail(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/page"):
            nom = self.path.split("n=")[-1]
            corps = f"<!doctype html><meta charset=utf-8><title>{nom}</title><h1>Page {nom}</h1>"
        else:
            corps = ACCUEIL
        donnees = corps.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)


@pytest.fixture
def portail():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Portail)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{serveur.server_address[1]}/"
    finally:
        serveur.shutdown()
        serveur.server_close()


def _enregistrer(dossier, url, actions):
    nav = Navigateur(ConfigNavigateur(canal="auto", visible=False), dossier, visible=False)
    nav.ouvrir()
    enregistreur = Enregistreur(nav)
    try:
        page = enregistreur.demarrer(url)
        page.wait_for_selector("#__autoweb_badge")
        actions(page)
        page.wait_for_timeout(800)
        return enregistreur.arreter()
    finally:
        nav.fermer()


def _rejouer(dossier, etapes, url, nom):
    texte = construire_depuis_enregistrement(etapes, [], [], Dialogue(["", "", "", "n", "n"]), nom=nom,
                                             fichier_excel=None, canal="chromium", url_depart=url)
    chemin = dossier / f"{nom}.yaml"
    chemin.write_text(texte, encoding="utf-8")
    return texte, lancer(charger(chemin), Options(visible=False, interactif=False))


def test_sous_menu_cree_au_survol(portail, tmp_path, navigateur_ok):
    def tache(page):
        page.hover("#gates > span")
        page.click("text=Données MK1")
        page.wait_for_selector("text=Page mk1")

    etapes = _enregistrer(tmp_path, portail, tache)
    gestes = [(e.action, e.args.get("selecteur")) for e in etapes if e.action in ("cliquer", "survoler")]
    assert gestes == [("survoler", "texte_exact=GATES"), ("cliquer", "texte_exact=Données MK1")], gestes

    texte, bilan = _rejouer(tmp_path, etapes, portail, "menu_gates")
    assert ":has-text(" not in texte, texte
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume() + "\n" + texte


def test_sous_menu_css_cache(portail, tmp_path, navigateur_ok):
    """Sous-menu présent mais caché (display:none tant que la souris n'est pas dessus)."""
    def tache(page):
        page.hover("li.css")
        page.click("text=Nouveau rep.")
        page.wait_for_selector("text=Page box2")

    etapes = _enregistrer(tmp_path, portail, tache)
    gestes = [(e.action, e.args.get("selecteur")) for e in etapes if e.action in ("cliquer", "survoler")]
    assert gestes == [("survoler", "texte_exact=BOX"), ("cliquer", "texte_exact=Nouveau rep.")], gestes
    _, bilan = _rejouer(tmp_path, etapes, portail, "menu_box")
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume()


def test_tache_ecrite_sans_survol(portail, tmp_path, navigateur_ok):
    """Tâche écrite à la main, sans « survoler » : le robot ouvre seul le sous-menu caché qui
    contient l'élément, et « Nouveau rep. » n'attrape pas « Nouveau rep. e »."""
    chemin = tmp_path / "ecrite.yaml"
    chemin.write_text(f"""nom: écrite
navigateur: {{canal: auto, visible: false}}
etapes:
  - aller: "{portail}"
  - cliquer: "texte_exact=Nouveau rep."
  - verifier: {{texte_page: "Page box2"}}
""", encoding="utf-8")
    bilan = lancer(charger(chemin), Options(visible=False, interactif=False))
    assert (bilan.ok, bilan.erreurs) == (1, 0), bilan.resume()


def test_le_robot_ne_choisit_pas_au_hasard(portail, tmp_path, navigateur_ok):
    chemin = tmp_path / "ambigu.yaml"
    chemin.write_text(f"""nom: ambigu
navigateur: {{canal: auto, visible: false}}
etapes:
  - aller: "{portail}"
  - cliquer: "li"
""", encoding="utf-8")
    bilan = lancer(charger(chemin), Options(visible=False, interactif=False))
    assert bilan.erreurs == 1 and "ne choisit" in bilan.resume(), bilan.resume()

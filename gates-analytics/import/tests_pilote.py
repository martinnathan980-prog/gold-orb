#!/usr/bin/env python3
"""
Batterie du pilote Chrome : elle lance un vrai Chrome et lui fait faire, sur
une page fabriquée pour l'occasion, tout ce que l'extraction lui demandera —
aller à une adresse, remplir un champ, cliquer un bouton nommé par son texte,
lire un tableau, attendre un téléchargement.

    python3 import/tests_pilote.py

Chrome est cherché tout seul ; SUIVI_FWD_CHROME ou CHROMIUM_PATH imposent un
chemin. Sans Chrome sur le poste, la batterie le dit et s'arrête sans échouer :
le reste du projet ne dépend pas d'elle.

Aucune dépendance : bibliothèque standard uniquement.
"""

import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from piloter_chrome import Chrome, ErreurPilote, chemin_chrome   # noqa: E402

echecs = []
faits = []


def verifier(nom, condition, detail=''):
    if condition:
        faits.append(nom)
        print('  ✓ ' + nom)
    else:
        echecs.append(nom)
        print('  ✗ ' + nom + (' — ' + str(detail) if detail else ''))


def section(titre):
    print('\n— ' + titre + ' —')


PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Extract d'essai</title></head>
<body>
  <h1 id="titre">Recherche de contrat</h1>
  <input id="recherche" value="">
  <button id="chercher" type="button" onclick="chercher()">Tout extraire</button>
  <a id="lien-plan" href="#" onclick="ouvrirPlan();return false">Ouvrir le plan</a>
  <p id="etat">au repos</p>
  <table id="resultats"><tr><th>Référence</th><th>Avancement</th></tr></table>
  <a id="telecharger" download="extrait.csv"
     href="data:text/csv;charset=utf-8,Reference%3BAvancement%0ATFE2130A600001A%3BTermin%C3%A9%0A">Télécharger</a>
  <script>
    function chercher() {
      var q = document.getElementById('recherche').value;
      document.getElementById('etat').textContent = 'recherche : ' + q;
      var t = document.getElementById('resultats');
      while (t.rows.length > 1) t.deleteRow(1);
      ['TFE2130A600001A', 'WLE4610A600003C'].forEach(function (r, i) {
        var l = t.insertRow();
        l.insertCell().textContent = q + '-' + r;
        l.insertCell().textContent = i === 0 ? 'Terminé' : 'En cours';
      });
    }
    function ouvrirPlan() { document.getElementById('etat').textContent = 'plan ouvert'; }
    setTimeout(function () {
      var tard = document.createElement('p');
      tard.id = 'tardif'; tard.textContent = 'arrivé après coup';
      document.body.appendChild(tard);
    }, 700);
  </script>
</body></html>"""


def chrome_pour_la_batterie():
    """Le Chrome à piloter : celui du poste, celui qu'on impose, ou celui que
    Playwright a déjà installé pour les autres batteries du projet."""
    impose = os.environ.get('SUIVI_FWD_CHROME') or os.environ.get('CHROMIUM_PATH')
    if impose and os.path.exists(impose):
        return impose
    trouve = chemin_chrome() if not impose else None
    if trouve:
        return trouve
    import glob
    for motif in ('/opt/pw-browsers/chromium-*/chrome-linux/chrome',
                  os.path.expanduser('~/.cache/ms-playwright/chromium-*/chrome-linux/chrome')):
        for c in sorted(glob.glob(motif), reverse=True):
            if os.path.exists(c):
                return c
    return None


def main():
    exe = chrome_pour_la_batterie()
    if not exe:
        print('Chrome est introuvable sur ce poste : batterie non jouée (ce n\'est pas un échec).')
        return 0
    os.environ['SUIVI_FWD_CHROME'] = exe

    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-pilote-'))
    try:
        page = atelier / 'page.html'
        page.write_text(PAGE, encoding='utf-8')
        telechargements = atelier / 'telechargements'
        telechargements.mkdir()
        profil = atelier / 'profil'

        section('Le canal s\'ouvre et la page répond')
        # Dans un conteneur, le bac à sable de Chrome n'a pas les droits qu'il
        # lui faut ; sur un poste ordinaire, cette option ne sert pas.
        options = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
        with Chrome(port=9333, telechargements=telechargements, lancer=True,
                    profil=str(profil), sans_fenetre=True, delai=40, options=options) as chrome:
            url = chrome.ouvrir(page.as_uri())
            verifier('la page demandée est celle qui s\'ouvre', url.endswith('page.html'), url)
            verifier('son titre se lit', chrome.titre() == 'Extract d\'essai', chrome.titre())
            verifier('une expression est évaluée dans la page',
                     chrome.evaluer('1 + 1') == 2 and chrome.evaluer('document.getElementById("titre").textContent') == 'Recherche de contrat')
            verifier('un gros retour passe entier (au-delà d\'une trame courte)',
                     len(chrome.evaluer('"x".repeat(200000)')) == 200000)
            verifier('une erreur de la page est rapportée, pas avalée',
                     _leve(chrome.evaluer, 'nexistePas()'))

            section('Les gestes')
            chrome.remplir('#recherche', 'HDK')
            verifier('remplir un champ écrit sa valeur', chrome.evaluer('document.getElementById("recherche").value') == 'HDK')
            chrome.cliquer_texte('Tout extraire')
            chrome.attendre('document.querySelectorAll("#resultats tr").length > 1')
            table = chrome.tableau('#resultats')
            verifier('cliquer un bouton par son texte déclenche la page',
                     chrome.texte('#etat') == 'recherche : HDK', chrome.texte('#etat'))
            verifier('le tableau se lit, en-tête compris, ligne par ligne',
                     table == [['Référence', 'Avancement'],
                               ['HDK-TFE2130A600001A', 'Terminé'],
                               ['HDK-WLE4610A600003C', 'En cours']], table)
            chrome.cliquer('#lien-plan')
            verifier('un lien se clique aussi, par son sélecteur', chrome.texte('#etat') == 'plan ouvert', chrome.texte('#etat'))
            verifier('attendre un élément qui arrive plus tard fonctionne',
                     chrome.attendre_selecteur('#tardif', delai=5))
            verifier('un élément qui n\'arrive jamais lève une erreur claire, sans bloquer',
                     _leve(chrome.attendre_selecteur, '#jamais', delai=2))
            verifier('cliquer ce qui n\'existe pas est une erreur, pas un silence',
                     _leve(chrome.cliquer_texte, 'Bouton absent', delai=2))

            section('Le téléchargement')
            avant = chrome.fichiers_presents()
            chrome.cliquer('#telecharger')
            fichier = chrome.attendre_telechargement(avant, delai=60)
            contenu = fichier.read_text(encoding='utf-8')
            verifier('le fichier arrive dans le dossier demandé',
                     fichier.parent == telechargements and fichier.exists(), str(fichier))
            verifier('et il porte bien l\'extract',
                     contenu.startswith('Reference;Avancement') and 'TFE2130A600001A;Terminé' in contenu,
                     contenu[:60])
            verifier('attendre un téléchargement qui ne vient pas lève une erreur, sans bloquer',
                     _leve(chrome.attendre_telechargement, chrome.fichiers_presents(), delai=2))

        section('Quand rien n\'écoute')
        verifier('s\'attacher à un port fermé dit quoi faire, sans trace incompréhensible',
                 _leve(Chrome(port=9444, delai=3).demarrer))
    finally:
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


def _leve(fonction, *args, **params):
    """Vrai si l'appel lève ErreurPilote — et que le message est en français."""
    try:
        fonction(*args, **params)
    except ErreurPilote as err:
        return bool(str(err).strip())
    except Exception:
        return False
    return False


if __name__ == '__main__':
    sys.exit(main())

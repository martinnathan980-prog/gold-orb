#!/usr/bin/env python3
"""
Batterie de la chaîne d'import : la recette d'extraction (lecture,
vérification, variables) rejouée dans un vrai Chrome sur une page fabriquée,
et le dépôt dans le classeur joué contre un faux classeur qui répond comme le
vrai — y compris quand il refuse.

    python3 import/tests_import.py

Sans Chrome sur le poste, la partie navigateur est sautée en le disant ; le
reste tourne quand même.

Aucune dépendance : bibliothèque standard uniquement.
"""

import http.server
import json
import os
import pathlib
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import deposer as dep                                            # noqa: E402
import extraire as ext                                           # noqa: E402
from piloter_chrome import Chrome                                # noqa: E402
from tests_pilote import PAGE, chrome_pour_la_batterie           # noqa: E402

echecs, faits = [], []


def verifier(nom, condition, detail=''):
    if condition:
        faits.append(nom)
        print('  ✓ ' + nom)
    else:
        echecs.append(nom)
        print('  ✗ ' + nom + (' — ' + str(detail) if detail else ''))


def section(titre):
    print('\n— ' + titre + ' —')


def _leve(erreur, fonction, *args, **params):
    """Vrai si l'appel lève cette erreur, avec un message non vide."""
    try:
        fonction(*args, **params)
    except erreur as err:
        return bool(str(err).strip())
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
#  Un faux classeur : il répond comme l'application web du script
# ---------------------------------------------------------------------------
class FauxClasseur(http.server.BaseHTTPRequestHandler):
    recu = []
    secret = 'phrase longue et imprévisible'

    def do_POST(self):
        taille = int(self.headers.get('Content-Length', 0))
        corps = self.rfile.read(taille).decode('utf-8')
        try:
            demande = json.loads(corps)
        except ValueError:
            return self._repondre({'ok': False, 'message': 'Corps illisible'})
        FauxClasseur.recu.append(demande)
        if demande.get('secret') != FauxClasseur.secret:
            return self._repondre({'ok': False, 'message': 'Secret refusé.'})
        if demande.get('onglet') == '__redirige__':
            # Apps Script répond par une redirection : le résultat est servi
            # ailleurs, et le client doit la suivre.
            self.send_response(302)
            self.send_header('Location', '/resultat')
            self.end_headers()
            return
        if demande.get('onglet') == '__html__':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html>Connectez-vous</html>')
            return
        lignes = demande.get('lignes') or []
        reponse = {'ok': True, 'onglet': demande.get('onglet'), 'lignes': len(lignes),
                   'colonnes': max((len(l) for l in lignes), default=0)}
        if demande.get('archiver'):
            reponse['archive'] = {'ok': True, 'semaine': '2026-S38',
                                  'total': max(len(lignes) - 1, 0), 'termine': 1}
        self._repondre(reponse)

    def do_GET(self):
        if self.path == '/resultat':
            return self._repondre({'ok': True, 'onglet': 'Données', 'lignes': 3, 'colonnes': 2,
                                   'archive': {'ok': True, 'semaine': '2026-S38', 'total': 2, 'termine': 1}})
        self.send_response(404)
        self.end_headers()

    def _repondre(self, objet):
        charge = json.dumps(objet).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(charge)))
        self.end_headers()
        self.wfile.write(charge)

    def log_message(self, *_):
        pass


def main():
    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-import-'))
    serveur = http.server.HTTPServer(('127.0.0.1', 0), FauxClasseur)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    adresse = 'http://127.0.0.1:%d/exec' % serveur.server_address[1]
    try:
        section('La recette se lit, ou dit pourquoi elle ne tient pas debout')
        bonne = {'nom': 'essai', 'variable': 'contrat', 'valeurs': ['HDK', 'THS'],
                 'etapes': [{'faire': 'ouvrir', 'url': 'https://x/{contrat}'}]}
        fichier = atelier / 'recette.json'
        fichier.write_text(json.dumps(bonne), encoding='utf-8')
        verifier('une recette correcte se lit telle quelle',
                 ext.lire_recette(fichier)['nom'] == 'essai')
        verifier('une recette introuvable le dit', _leve(ext.ErreurRecette, ext.lire_recette, atelier / 'absente.json'))
        (atelier / 'cassee.json').write_text('{ pas du json', encoding='utf-8')
        verifier('une recette illisible le dit sans trace incompréhensible',
                 _leve(ext.ErreurRecette, ext.lire_recette, atelier / 'cassee.json'))
        verifier('une recette sans étape est refusée', _leve(ext.ErreurRecette, ext.verifier_recette, {'etapes': []}))
        verifier('un geste inconnu est refusé, et les gestes possibles sont nommés',
                 _leve(ext.ErreurRecette, ext.verifier_recette, {'etapes': [{'faire': 'danser'}]}))
        verifier('un geste auquel il manque un renseignement est refusé',
                 _leve(ext.ErreurRecette, ext.verifier_recette, {'etapes': [{'faire': 'remplir', 'ou': '#x'}]}))
        verifier('des valeurs sans variable sont refusées',
                 _leve(ext.ErreurRecette, ext.verifier_recette,
                       {'valeurs': ['a'], 'etapes': [{'faire': 'ouvrir', 'url': 'x'}]}))
        verifier('une étape « telecharger » sans dossier de téléchargement est refusée à la lecture, pas en pleine extraction',
                 _leve(ext.ErreurRecette, ext.verifier_recette,
                       {'etapes': [{'faire': 'ouvrir', 'url': 'x'}, {'faire': 'telecharger'}]}))
        verifier('une recette qui attend des valeurs et n\'en reçoit aucune le dit, au lieu de jouer un tour « None »',
                 _leve(ext.ErreurRecette, ext.valeurs_de,
                       {'variable': 'plan', 'etapes': [{'faire': 'ouvrir', 'url': 'x'}]}))
        (atelier / 'refs-vide.txt').write_text('# rien que des commentaires\n\n', encoding='utf-8')
        verifier('un fichier de valeurs vide le dit aussi',
                 _leve(ext.ErreurRecette, ext.valeurs_de, bonne, None, atelier / 'refs-vide.txt'))
        verifier('les variables se remplacent dans les textes',
                 ext.remplacer('gates-{contrat}-{an}.csv', {'contrat': 'HDK', 'an': 2026}) == 'gates-HDK-2026.csv')
        verifier('une variable inconnue est signalée, pas laissée telle quelle',
                 _leve(ext.ErreurRecette, ext.remplacer, '{inconnue}', {'contrat': 'HDK'}))
        verifier('les tours viennent de la recette, de la ligne de commande ou d\'un fichier',
                 ext.valeurs_de(bonne) == ['HDK', 'THS'] and
                 ext.valeurs_de(bonne, ['VRK']) == ['VRK'] and
                 ext.valeurs_de({'etapes': []}) == [None])
        refs = atelier / 'refs.txt'
        refs.write_text('# les plans à ouvrir\nTFE2130A600001A\n\n  WLE4610A600003C  \n', encoding='utf-8')
        verifier('un fichier de valeurs se lit, sans les commentaires ni les lignes vides',
                 ext.valeurs_de(bonne, None, refs) == ['TFE2130A600001A', 'WLE4610A600003C'])

        section('Le dépôt dans le classeur')
        csv_bon = atelier / 'extrait.csv'
        csv_bon.write_text('Référence;Avancement\nTFE2130A600001A;Terminé\nWLE4610A600003C;En cours\n',
                           encoding='utf-8')
        lignes = dep.lire_tableur(csv_bon)
        verifier('un CSV à point-virgule se lit, accents compris',
                 lignes == [['Référence', 'Avancement'], ['TFE2130A600001A', 'Terminé'],
                            ['WLE4610A600003C', 'En cours']], lignes)
        csv_virgule = atelier / 'virgule.csv'
        csv_virgule.write_bytes('﻿Ref,Etat\nA,1\nB,2\n'.encode('utf-8'))
        verifier('un CSV à virgule, avec BOM, se lit aussi',
                 dep.lire_tableur(csv_virgule) == [['Ref', 'Etat'], ['A', '1'], ['B', '2']])
        csv_ansi = atelier / 'ansi.csv'
        csv_ansi.write_bytes('Réf;État\nTermin\xe9;1\n'.encode('cp1252'))
        verifier('un CSV enregistré par Excel en ANSI se lit sans se plaindre',
                 dep.lire_tableur(csv_ansi)[1][0] == 'Terminé', dep.lire_tableur(csv_ansi))
        verifier('un fichier absent le dit', _leve(dep.ErreurDepot, dep.lire_tableur, atelier / 'nulle-part.csv'))
        (atelier / 'classeur.xlsx').write_bytes(b'PK\x03\x04 pas vraiment')
        verifier('un vrai .xlsx est refusé en expliquant quoi faire',
                 _leve(dep.ErreurDepot, dep.lire_tableur, atelier / 'classeur.xlsx'))
        # Le geste le plus courant : renommer le .xlsx en .csv dans l'explorateur.
        renomme = atelier / 'renomme.csv'
        renomme.write_bytes(b'PK\x03\x04' + b'\x00' * 200)
        verifier('un classeur Excel simplement renommé en .csv est reconnu et refusé, pas déposé en binaire',
                 _leve(dep.ErreurDepot, dep.lire_tableur, renomme))
        # Une ligne de titre au-dessus de l'en-tête, avec une virgule dedans :
        # le séparateur reste le point-virgule.
        titre = atelier / 'titre.csv'
        titre.write_text('Export GATES, programme 225, semaine 38\n'
                         'Référence;ATA;Avancement\n'
                         'TFE2130A600001A;21;Terminé\n'
                         'WLE4610A600003C;24;En cours\n', encoding='utf-8')
        lu = dep.lire_tableur(titre)
        verifier('une ligne de titre qui contient des virgules ne fait pas découper l\'extract de travers',
                 lu[1] == ['Référence', 'ATA', 'Avancement'] and lu[2][0] == 'TFE2130A600001A' and len(lu[3]) == 3, lu)
        # Excel « Texte Unicode » : de l'UTF-16 avec BOM.
        unicode16 = atelier / 'unicode.csv'
        unicode16.write_bytes('Réf;État\nTFE2130A600001A;Terminé\n'.encode('utf-16'))
        verifier('un CSV enregistré en « Texte Unicode » (UTF-16) se lit, au lieu de partir en charabia',
                 dep.lire_tableur(unicode16) == [['Réf', 'État'], ['TFE2130A600001A', 'Terminé']],
                 dep.lire_tableur(unicode16))
        tabule = atelier / 'tab.csv'
        tabule.write_text('Ref\tEtat\nA\t1\nB\t2\n', encoding='utf-8')
        verifier('un extract séparé par des tabulations se lit aussi',
                 dep.lire_tableur(tabule) == [['Ref', 'Etat'], ['A', '1'], ['B', '2']])

        resultat = dep.deposer(lignes, 'HDK', adresse, FauxClasseur.secret, archiver=True)
        recu = FauxClasseur.recu[-1]
        verifier('le classeur reçoit l\'onglet, les lignes et la demande d\'archivage',
                 recu['onglet'] == 'HDK' and recu['lignes'] == lignes and recu['archiver'] is True and
                 resultat['ok'] and resultat['lignes'] == 3, json.dumps(recu)[:120])
        verifier('le compte rendu se lit en français',
                 'déposée' in dep.raconter(resultat) and 'archivé' in dep.raconter(resultat), dep.raconter(resultat))
        verifier('un refus du classeur devient une erreur claire',
                 _leve(dep.ErreurDepot, dep.deposer, lignes, 'HDK', adresse, 'mauvais secret'))
        verifier('une page HTML au lieu du JSON (déploiement mal partagé) est dite comme telle',
                 _leve(dep.ErreurDepot, dep.deposer, lignes, '__html__', adresse, FauxClasseur.secret))
        verifier('un classeur injoignable est dit comme tel',
                 _leve(dep.ErreurDepot, dep.deposer, lignes, 'HDK', 'http://127.0.0.1:1/exec', FauxClasseur.secret))
        vide = atelier / 'reglages.json'
        verifier('sans adresse ni secret, le script dit quoi créer',
                 _leve(dep.ErreurDepot, dep.reglages, vide))
        vide.write_text(json.dumps({'adresse': adresse, 'secret': 'x'}), encoding='utf-8')
        verifier('un fichier de réglages se lit', dep.reglages(vide) == (adresse, 'x'))
        redirige = dep.deposer(lignes, '__redirige__', adresse, FauxClasseur.secret)
        verifier('une réponse servie après redirection — comme le fait une application web Apps Script — est lue normalement',
                 redirige['ok'] and redirige['lignes'] == 3 and redirige['archive']['semaine'] == '2026-S38',
                 json.dumps(redirige))

        section('Le dossier de téléchargement, tel qu\'un humain l\'écrit')
        from piloter_chrome import dossier_utilisable, ErreurPilote
        os.environ['SUIVI_FWD_ESSAI'] = str(atelier)
        verifier('une variable d\'environnement et le tilde sont développés',
                 dossier_utilisable('%SUIVI_FWD_ESSAI%') == atelier.resolve() and
                 dossier_utilisable('~') == pathlib.Path(os.path.expanduser('~')).resolve(),
                 str(dossier_utilisable('%SUIVI_FWD_ESSAI%')))
        verifier('un dossier qui n\'existe pas est refusé tout de suite, au lieu d\'attendre un fichier qui n\'arrivera jamais',
                 _leve(ErreurPilote, dossier_utilisable, str(atelier / 'pas-la')))

        section('La recette rejouée dans un vrai Chrome')
        exe = chrome_pour_la_batterie()
        if not exe:
            print('  (Chrome introuvable : partie sautée, ce n\'est pas un échec)')
        else:
            os.environ['SUIVI_FWD_CHROME'] = exe
            page = atelier / 'page.html'
            page.write_text(PAGE, encoding='utf-8')
            telechargements = atelier / 'telechargements'
            telechargements.mkdir()
            recette = {
                'nom': 'essai complet', 'variable': 'contrat', 'valeurs': ['HDK', 'THS'],
                'telechargements': str(telechargements),
                'etapes': [
                    {'faire': 'ouvrir', 'url': page.as_uri()},
                    {'faire': 'remplir', 'ou': '#recherche', 'texte': '{contrat}'},
                    {'faire': 'cliquer_texte', 'texte': 'Tout extraire'},
                    {'faire': 'attendre', 'ou': '#resultats tr:nth-child(2)'},
                    {'faire': 'lire_tableau', 'ou': '#resultats'},
                    {'faire': 'cliquer', 'ou': '#telecharger'},
                    {'faire': 'telecharger', 'vers': 'gates-{contrat}.csv', 'delai': 60, 'motif': '*.csv'},
                ],
            }
            fichier_recette = atelier / 'complete.json'
            fichier_recette.write_text(json.dumps(recette), encoding='utf-8')
            options = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
            muet = lambda *_: None                                       # noqa: E731
            with Chrome(port=9334, telechargements=telechargements, lancer=True,
                        profil=str(atelier / 'profil'), sans_fenetre=True, delai=40,
                        options=options) as chrome:
                tout = {'fichiers': [], 'tableaux': []}
                for valeur in ext.valeurs_de(recette):
                    r = ext.jouer(chrome, recette, {'contrat': valeur}, muet)
                    tout['fichiers'] += r['fichiers']
                    tout['tableaux'] += r['tableaux']
            # Deux téléchargements de suite ne doivent pas rendre deux fois le
            # même fichier : le second attend vraiment le suivant.
            deuxFois = {'telechargements': str(telechargements), 'etapes': [
                {'faire': 'ouvrir', 'url': page.as_uri()},
                {'faire': 'cliquer', 'ou': '#telecharger'},
                {'faire': 'telecharger', 'vers': 'premier.csv', 'delai': 60},
                {'faire': 'cliquer', 'ou': '#telecharger'},
                {'faire': 'telecharger', 'vers': 'second.csv', 'delai': 60},
            ]}
            with Chrome(port=9335, telechargements=telechargements, lancer=True,
                        profil=str(atelier / 'profil2'), sans_fenetre=True, delai=40,
                        options=options) as chrome2:
                r2 = ext.jouer(chrome2, deuxFois, {}, muet)
            verifier('deux téléchargements de suite rendent deux fichiers différents',
                     sorted(f.name for f in r2['fichiers']) == ['premier.csv', 'second.csv'],
                     [f.name for f in r2['fichiers']])
            noms = sorted(f.name for f in tout['fichiers'])
            verifier('deux tours, deux fichiers, nommés d\'après la variable',
                     noms == ['gates-HDK.csv', 'gates-THS.csv'], noms)
            verifier('chaque fichier porte l\'extract', all(
                f.read_text(encoding='utf-8').startswith('Reference;Avancement') for f in tout['fichiers']))
            verifier('le tableau lu au passage suit la variable du tour',
                     len(tout['tableaux']) == 2 and tout['tableaux'][0][1][0] == 'HDK-TFE2130A600001A' and
                     tout['tableaux'][1][1][0] == 'THS-TFE2130A600001A',
                     json.dumps([t[1][0] for t in tout['tableaux']]))
            # Et la chaîne entière : ce que Chrome a récolté part dans le classeur.
            depot = dep.deposer(dep.lire_tableur(tout['fichiers'][0]), 'HDK', adresse,
                                FauxClasseur.secret, archiver=True)
            verifier('l\'extract récolté se dépose ensuite dans le classeur, qui archive la semaine',
                     depot['ok'] and depot['lignes'] == 2 and depot['archive']['semaine'] == '2026-S38',
                     json.dumps(depot))
    finally:
        serveur.shutdown()
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


if __name__ == '__main__':
    sys.exit(main())

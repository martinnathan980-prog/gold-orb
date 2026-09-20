#!/usr/bin/env python3
"""
Dépose un extract dans le classeur, sans l'ouvrir.

Le classeur publie une petite adresse (l'« application web » du script Apps
Script). Ce programme lui envoie les lignes d'un extract ; le classeur les
colle dans l'onglet du contrat — exactement le geste Ctrl+A, Suppr, coller en
A1 — et, si on le lui demande, archive le relevé de la semaine. La page se
met à jour toute seule.

    python3 import/deposer.py gates-HDK.csv --onglet HDK --archiver

L'adresse et le secret se lisent dans `import/depot.json`, à créer sur le
poste et à ne jamais publier :

    { "adresse": "https://script.google.com/macros/s/…/exec",
      "secret":  "la même phrase que dans CONFIG.DEPOT.SECRET" }

À défaut, les variables SUIVI_FWD_DEPOT_ADRESSE et SUIVI_FWD_DEPOT_SECRET.

Aucune dépendance : bibliothèque standard uniquement.
"""

import argparse
import csv
import io
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

CONFIG = pathlib.Path(__file__).resolve().parent / 'depot.json'
SEPARATEURS = ';,\t'


class ErreurDepot(Exception):
    """Ce qui empêche le dépôt, dit en français."""


def reglages(chemin=None):
    """L'adresse et le secret : le fichier de configuration, sinon l'environnement."""
    fichier = pathlib.Path(chemin) if chemin else CONFIG
    valeurs = {}
    if fichier.exists():
        try:
            valeurs = json.loads(fichier.read_text(encoding='utf-8'))
        except ValueError as err:
            raise ErreurDepot('%s est illisible : %s' % (fichier.name, err))
    adresse = valeurs.get('adresse') or os.environ.get('SUIVI_FWD_DEPOT_ADRESSE', '')
    secret = valeurs.get('secret') or os.environ.get('SUIVI_FWD_DEPOT_SECRET', '')
    if not adresse or not secret:
        raise ErreurDepot(
            'Adresse ou secret absents. Créez %s avec { "adresse": "…", "secret": "…" }, '
            'ou renseignez SUIVI_FWD_DEPOT_ADRESSE et SUIVI_FWD_DEPOT_SECRET.' % fichier)
    return adresse, secret


def decoder(brut, nom):
    """Le texte d'un fichier, quel que soit l'encodage que l'outil a choisi."""
    if brut[:2] in (b'\xff\xfe', b'\xfe\xff') or brut[:4] in (b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff'):
        for encodage in ('utf-32', 'utf-16'):
            try:
                return brut.decode(encodage)
            except (UnicodeDecodeError, LookupError):
                continue
    if b'\x00' in brut[:4096]:
        for encodage in ('utf-16-le', 'utf-16-be'):
            try:
                return brut.decode(encodage)
            except UnicodeDecodeError:
                continue
        raise ErreurDepot(
            '%s n\'est pas un fichier texte : il contient des octets nuls. Si c\'est un classeur '
            'Excel renommé, enregistrez-le vraiment en CSV.' % nom)
    for encodage in ('utf-8-sig', 'cp1252'):
        try:
            return brut.decode(encodage)
        except UnicodeDecodeError:
            continue
    return brut.decode('latin-1')


def separateur_de(texte):
    """Le séparateur qui découpe le mieux : celui qui donne le même nombre de
    colonnes d'une ligne à l'autre, et le plus de colonnes."""
    lignes = [l for l in texte.splitlines()[:40] if l.strip()]
    if not lignes:
        return ';'
    meilleur, note_max = ';', (-1, -1)
    for candidat in SEPARATEURS:
        comptes = {}
        for ligne in lignes:
            n = len(next(csv.reader([ligne], delimiter=candidat)))
            comptes[n] = comptes.get(n, 0) + 1
        dominant = max(comptes.items(), key=lambda x: (x[1], x[0]))
        if dominant[0] < 2:
            continue                      # une seule colonne : ce n'est pas un séparateur
        note = (dominant[1] / float(len(lignes)), dominant[0])
        if note > note_max:
            meilleur, note_max = candidat, note
    return meilleur


def lire_tableur(chemin):
    """Un CSV — quel que soit son séparateur, avec ou sans BOM — en lignes de cellules."""
    fichier = pathlib.Path(chemin)
    if not fichier.exists():
        raise ErreurDepot('Fichier introuvable : %s' % fichier)
    brut = fichier.read_bytes()
    # Un classeur Excel est une archive ZIP, quel que soit le nom qu'on lui donne :
    # le renommer en .csv ne le transforme pas.
    if brut[:4] == b'PK\x03\x04' or brut[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' or \
            fichier.suffix.lower() in ('.xlsx', '.xls', '.xlsm'):
        raise ErreurDepot(
            '%s est un classeur Excel : enregistrez-le en CSV (Fichier → Enregistrer sous → '
            'CSV), ou demandez le CSV à l\'export — lire le format Excel demanderait une '
            'bibliothèque que le poste ne peut pas installer.' % fichier.name)
    texte = decoder(brut, fichier.name)
    lignes = list(csv.reader(io.StringIO(texte), delimiter=separateur_de(texte)))
    lignes = [l for l in lignes if any(str(c).strip() for c in l)]
    if not lignes:
        raise ErreurDepot('%s ne contient aucune ligne.' % fichier.name)
    return lignes


def deposer(lignes, onglet, adresse, secret, archiver=False, creer=False, delai=180):
    """Envoie les lignes au classeur et rend sa réponse."""
    corps = json.dumps({'secret': secret, 'onglet': onglet, 'lignes': lignes,
                        'archiver': bool(archiver), 'creer': bool(creer)}).encode('utf-8')
    demande = urllib.request.Request(adresse, data=corps,
                                     headers={'Content-Type': 'application/json'})
    try:
        # Une application web Apps Script répond par une redirection vers
        # googleusercontent : c'est là que le résultat est servi, et urllib la
        # suit toute seule. Ce qui revient est donc bien la réponse du classeur.
        with urllib.request.urlopen(demande, timeout=delai) as reponse:
            texte = reponse.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as err:
        raise ErreurDepot('Le classeur a répondu %s : %s' % (err.code, err.reason))
    except urllib.error.URLError as err:
        raise ErreurDepot('Le classeur est injoignable : %s' % err.reason)
    try:
        resultat = json.loads(texte)
    except ValueError:
        raise ErreurDepot('Réponse inattendue du classeur (déploiement mal partagé ?) : %s'
                          % texte[:200])
    if not resultat.get('ok'):
        raise ErreurDepot('Dépôt refusé : %s' % resultat.get('message', 'sans raison donnée'))
    return resultat


def raconter(resultat):
    lignes = ['%d ligne(s) déposée(s) dans « %s » (%d colonnes).'
              % (resultat.get('lignes', 0), resultat.get('onglet', '?'), resultat.get('colonnes', 0))]
    archive = resultat.get('archive')
    if archive and archive.get('ok'):
        lignes.append('Relevé %s archivé : %d plans, %d terminés.'
                      % (archive.get('semaine', '?'), archive.get('total', 0), archive.get('termine', 0)))
    elif archive:
        lignes.append('Pas d\'archivage : %s' % archive.get('message', ''))
    return '\n'.join(lignes)


def main(argv=None):
    parseur = argparse.ArgumentParser(description='Dépose un extract CSV dans le classeur.')
    parseur.add_argument('fichier', help='l\'extract, en CSV')
    parseur.add_argument('--onglet', required=True, help='l\'onglet du classeur (le contrat, ou SEE)')
    parseur.add_argument('--archiver', action='store_true', help='archiver le relevé de la semaine')
    parseur.add_argument('--creer', action='store_true', help='créer l\'onglet s\'il n\'existe pas')
    parseur.add_argument('--config', help='un autre fichier de configuration que depot.json')
    args = parseur.parse_args(argv)
    try:
        adresse, secret = reglages(args.config)
        lignes = lire_tableur(args.fichier)
        resultat = deposer(lignes, args.onglet, adresse, secret, args.archiver, args.creer)
        print(raconter(resultat))
        return 0
    except ErreurDepot as err:
        print('Arrêt : %s' % err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

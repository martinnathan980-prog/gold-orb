#!/usr/bin/env python3
"""
Le socle commun des lecteurs de plans : ce qu'est un composant, comment on
rattache un repère à sa boîte, comment on lit un repère mal écrit, et comment
on compare ce qu'on a lu à ce que la base attend.

Tous les lecteurs — PDF de dessin, Visio, DXF, scan — ramènent le plan à la
même chose : des **textes** placés (x, y) et des **boîtes** (x, y, largeur,
hauteur). À partir de là, la règle est la même pour tous, et c'est elle qui
fait la fiabilité :

- une boîte, un repère → un composant **sûr** ;
- une boîte à plusieurs repères, ou sans aucun → **douteux**, signalé ;
- un repère écrit à côté d'une boîte sans repère → rattaché, mais seulement
  si une seule boîte est assez proche ; sinon **orphelin**, signalé.

**Un composant n'est jamais inventé.** Ce qui n'est pas sûr est dit.

Aucune dépendance : bibliothèque standard uniquement.
"""

import csv
import io
import itertools
import pathlib
import re

# Un repère électrique, par défaut : quelques chiffres, quelques lettres, et
# éventuellement des chiffres — « 18AB », « 120PA3 ». Se remplace en ligne de
# commande le jour où la convention diffère.
REPERE = re.compile(r'^[0-9]{1,3}[A-Z]{1,4}[0-9]{0,3}$')
COTE_MINI = 8.0          # une boîte plus petite que cela n'est pas un équipement (en points)
DISTANCE_MAXI = 40.0     # un repère écrit à côté de sa boîte, pas à l'autre bout (en points)

# Ce qu'une reconnaissance de caractères confond le plus souvent. Chaque
# lettre donne les formes qu'on essaie à sa place quand la lecture brute ne
# fait pas un repère — jamais plus loin que cela.
CONFUSIONS = {
    'O': '0', '0': 'O', 'Q': '0', 'D': '0',
    'I': '1', '1': 'I', 'L': '1', '|': '1',
    'S': '5', '5': 'S',
    'B': '8', '8': 'B',
    'Z': '2', '2': 'Z',
    'G': '6', '6': 'G',
}
POSITIONS_MAXI = 8       # au-delà, on n'essaie plus les variantes : trop de combinaisons


class ErreurPlan(Exception):
    """Ce qui empêche de lire le plan, dit en français."""


# ---------------------------------------------------------------------------
#  Une boîte et un texte : dedans, ou à quelle distance
# ---------------------------------------------------------------------------
def dedans(rect, t):
    return (rect['x'] <= t['x'] <= rect['x'] + rect['largeur'] and
            rect['y'] <= t['y'] <= rect['y'] + rect['hauteur'])


def distance_au_bord(rect, t):
    dx = max(rect['x'] - t['x'], 0, t['x'] - (rect['x'] + rect['largeur']))
    dy = max(rect['y'] - t['y'], 0, t['y'] - (rect['y'] + rect['hauteur']))
    return (dx * dx + dy * dy) ** 0.5


# ---------------------------------------------------------------------------
#  Lire un repère : tel quel, ou en corrigeant ce qu'une lecture confond
# ---------------------------------------------------------------------------
def nettoyer(mot):
    """« (18AB) », « 18ab. » → « 18AB » : les repères s'écrivent en capitales,
    sans ponctuation autour."""
    propre = (mot or '').strip().upper().replace(' ', '')
    return re.sub(r'^[^0-9A-Z|]+|[^0-9A-Z|]+$', '', propre)


def variantes(mot):
    """Toutes les formes qu'un mot lu pouvait avoir, avec le nombre de lettres
    changées : [(forme, changements)] — la lecture brute d'abord, à 0."""
    positions = [i for i, c in enumerate(mot) if c in CONFUSIONS]
    if not positions or len(positions) > POSITIONS_MAXI:
        return [(mot, 0)]
    formes = []
    vues = set()
    for choix in itertools.product((False, True), repeat=len(positions)):
        lettres = list(mot)
        for pos, changer in zip(positions, choix):
            if changer:
                lettres[pos] = CONFUSIONS[lettres[pos]]
        forme = ''.join(lettres)
        if forme not in vues:
            vues.add(forme)
            formes.append((forme, sum(choix)))
    formes.sort(key=lambda f: f[1])
    return formes


def interpreter(mot, repere=REPERE, connus=None, confiance=1.0, confiance_mini=0.5):
    """Ce qu'un mot lu veut dire : ('sur', repère), ('corrige', repère),
    ('incertain', candidats) ou ('non', None) quand ce n'est pas un repère.

    On ne change jamais plus de lettres qu'il n'en faut : parmi les formes
    qui font un repère, seule la plus proche de la lecture compte, et s'il y
    en a plusieurs à égalité, on ne tranche pas. `connus` — les repères que
    la base attend pour ce plan — ne filtre rien (un repère lu qui n'y est
    pas est justement ce qu'on veut voir) mais passe avant tout le reste.
    """
    propre = nettoyer(mot)
    if not propre:
        return ('non', None)
    valides = [(f, d) for f, d in variantes(propre) if repere.match(f)]
    if not valides:
        return ('non', None)

    def plus_proches(formes):
        distance = min(d for f, d in formes)
        return sorted(f for f, d in formes if d == distance), distance
    if connus:
        dans = [(f, d) for f, d in valides if f in connus]
        if dans:
            meilleurs, distance = plus_proches(dans)
            if len(meilleurs) == 1:
                return ('sur' if distance == 0 else 'corrige', meilleurs[0])
            return ('incertain', meilleurs)
    meilleurs, distance = plus_proches(valides)
    if confiance < confiance_mini or len(meilleurs) > 1:
        return ('incertain', meilleurs)
    return ('sur' if distance == 0 else 'corrige', meilleurs[0])


def interpreter_mots(mots, repere=REPERE, connus=None, confiance_mini=0.5):
    """Applique `interpreter` à chaque mot lu et rend les textes prêts pour
    `composants` : le repère compris dans `texte`, la lecture brute dans `lu`,
    les candidats dans `candidats` quand on ne tranche pas."""
    textes = []
    for m in mots:
        statut, valeur = interpreter(m['texte'], repere, connus, m.get('confiance', 1.0), confiance_mini)
        t = dict(m)
        if statut in ('sur', 'corrige'):
            if statut == 'corrige':
                t['lu'] = m['texte']
            t['texte'] = valeur
            if connus and valeur in connus:
                t['dans_base'] = True
        elif statut == 'incertain':
            t['candidats'] = valeur
        textes.append(t)
    return textes


# ---------------------------------------------------------------------------
#  Les composants : une boîte, et le repère qui est dedans ou juste à côté
# ---------------------------------------------------------------------------
def composants(textes, rectangles, repere=REPERE, cote_mini=COTE_MINI,
               distance_maxi=DISTANCE_MAXI):
    """Rend { trouves, douteux, orphelins, incertains, boites } — jamais une invention.

    trouves    : [{ repere, x, y, largeur, hauteur, textes, lu? }] — une boîte, un repère ;
    douteux    : les boîtes à plusieurs repères, sans aucun, ou au repère mal lu ;
    orphelins  : les repères écrits loin de toute boîte ;
    incertains : les lectures qu'on n'a pas su trancher, hors de toute boîte.
    """
    boites = [r for r in rectangles
              if r['largeur'] >= cote_mini and r['hauteur'] >= cote_mini]
    # Le cadre du plan est un rectangle comme les autres, mais il couvre la
    # page : un repère qui traîne dedans n'en fait pas un équipement.
    cadres = [r for r in boites if est_un_cadre(r, textes, rectangles)]
    boites = [r for r in boites if r not in cadres]
    # Une boîte dans une autre : on garde la plus petite qui contient le
    # repère, donc on trie du plus petit au plus grand.
    boites.sort(key=lambda r: r['largeur'] * r['hauteur'])
    pris = set()
    trouves, douteux = [], []
    for rect in boites:
        interieur = [(i, t) for i, t in enumerate(textes) if i not in pris and dedans(rect, t)]
        reperes = [t for i, t in interieur if not t.get('candidats') and repere.match(t['texte'])]
        incertains = [t for i, t in interieur if t.get('candidats')]
        if len(reperes) > 1:
            # Deux repères dans une boîte, mais la base n'en attend qu'un : c'est
            # l'autre qui est un mot mal lu (« Boîtier » lu « 801TIER »). La base
            # tranche — et seulement quand elle ne désigne qu'un seul des deux.
            attendus = [t for t in reperes if t.get('dans_base')]
            if len(attendus) == 1:
                reperes = attendus
        if len(reperes) == 1:
            for i, t in interieur:
                pris.add(i)
            trouve = {'repere': reperes[0]['texte'], 'x': rect['x'], 'y': rect['y'],
                      'largeur': rect['largeur'], 'hauteur': rect['hauteur'],
                      'textes': [t['texte'] for i, t in interieur]}
            if reperes[0].get('lu'):
                trouve['lu'] = reperes[0]['lu']
            trouves.append(trouve)
        elif len(reperes) > 1:
            for i, t in interieur:
                pris.add(i)
            douteux.append({'pourquoi': 'plusieurs repères dans la même boîte',
                            'reperes': [t['texte'] for t in reperes], 'rect': rect})
        elif incertains:
            for i, t in interieur:
                pris.add(i)
            douteux.append({'pourquoi': 'repère mal lu',
                            'candidats': sorted(set(c for t in incertains for c in t['candidats'])),
                            'textes': [t['texte'] for i, t in interieur], 'rect': rect})
        else:
            douteux.append({'pourquoi': 'aucun repère dans la boîte',
                            'textes': [t['texte'] for i, t in interieur], 'rect': rect})
    # Les repères écrits à côté d'une boîte sans repère : on les rattache, mais
    # seulement si une seule boîte est assez proche — sinon on ne tranche pas.
    orphelins, incertains = [], []
    libres = [t for i, t in enumerate(textes) if i not in pris]
    for t in libres:
        if t.get('candidats'):
            incertains.append(t)
            continue
        if not repere.match(t['texte']):
            continue
        proches = [d for d in douteux
                   if d['pourquoi'] == 'aucun repère dans la boîte' and
                   distance_au_bord(d['rect'], t) <= distance_maxi]
        if len(proches) == 1:
            d = proches[0]
            douteux.remove(d)
            trouve = {'repere': t['texte'], 'x': d['rect']['x'], 'y': d['rect']['y'],
                      'largeur': d['rect']['largeur'], 'hauteur': d['rect']['hauteur'],
                      'textes': d.get('textes', []) + [t['texte']]}
            if t.get('lu'):
                trouve['lu'] = t['lu']
            trouves.append(trouve)
        else:
            orphelins.append(t)
    trouves.sort(key=lambda c: (-c['y'], c['x']))
    return {'trouves': trouves, 'douteux': douteux, 'orphelins': orphelins,
            'incertains': incertains, 'boites': len(boites), 'cadres': len(cadres)}


def est_un_cadre(rect, textes, rectangles):
    """Un rectangle qui contient d'autres boîtes et couvre plus de la moitié
    de tout ce qui est dessiné : le cadre du plan, pas un équipement."""
    if not any(r is not rect and contient(rect, r) for r in rectangles):
        return False
    xs = [t['x'] for t in textes] + [r['x'] for r in rectangles] + [r['x'] + r['largeur'] for r in rectangles]
    ys = [t['y'] for t in textes] + [r['y'] for r in rectangles] + [r['y'] + r['hauteur'] for r in rectangles]
    etendue = max(1e-9, (max(xs) - min(xs)) * (max(ys) - min(ys)))
    return rect['largeur'] * rect['hauteur'] > 0.5 * etendue


def contient(grand, petit):
    return (grand['x'] <= petit['x'] and grand['y'] <= petit['y'] and
            petit['x'] + petit['largeur'] <= grand['x'] + grand['largeur'] and
            petit['y'] + petit['hauteur'] <= grand['y'] + grand['hauteur'])


# ---------------------------------------------------------------------------
#  Ce que la base attend, et ce que le plan montre
# ---------------------------------------------------------------------------
def correspondance(resultat, attendus):
    """Compare les repères sûrs du plan à ceux que la base attend pour lui.

    Rend { communs, absents, en_plus } : absents = attendus que le plan ne
    montre pas ; en_plus = lus sur le plan mais inconnus de la base.
    """
    lus = set(c['repere'] for c in resultat['trouves'])
    attendus = set(attendus or [])
    return {'communs': sorted(lus & attendus),
            'absents': sorted(attendus - lus),
            'en_plus': sorted(lus - attendus)}


def lire_connus(chemin):
    """Les repères attendus, par plan : { plan: {repères} }.

    Un CSV avec une colonne « plan » (ou « référence ») et une colonne
    « repère » ; ou un simple fichier texte, un repère par ligne, pour un
    seul plan (clé '').
    """
    fichier = pathlib.Path(chemin)
    if not fichier.exists():
        raise ErreurPlan('Liste des repères attendus introuvable : %s' % fichier)
    brut = fichier.read_bytes()
    if brut[:4] == b'PK\x03\x04' or brut[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        raise ErreurPlan('%s est un classeur Excel : enregistrez-le en CSV.' % fichier.name)
    for encodage in ('utf-8-sig', 'utf-16', 'cp1252'):
        try:
            texte = brut.decode(encodage)
            break
        except UnicodeDecodeError:
            continue
    else:
        texte = brut.decode('latin-1')
    lignes = [l for l in texte.splitlines() if l.strip()]
    if not lignes:
        raise ErreurPlan('%s ne contient aucune ligne.' % fichier.name)
    separateur = _separateur(lignes)
    if separateur is None:
        return {'': set(nettoyer(l) for l in lignes if nettoyer(l))}
    tableau = list(csv.reader(io.StringIO('\n'.join(lignes)), delimiter=separateur))
    entete = [_sans_accents(c).lower() for c in tableau[0]]
    col_plan = _colonne(entete, ('plan', 'reference', 'ref', 'name', 'nom'))
    col_repere = _colonne(entete, ('repere', 'rep', 'tag', 'elec', 'composant', 'equipement'))
    if col_repere is None:
        raise ErreurPlan(
            '%s : aucune colonne « repère » reconnue. En-têtes lus : %s'
            % (fichier.name, ', '.join(tableau[0])))
    connus = {}
    for ligne in tableau[1:]:
        if len(ligne) <= col_repere:
            continue
        repere = nettoyer(ligne[col_repere])
        if not repere:
            continue
        plan = ligne[col_plan].strip() if col_plan is not None and len(ligne) > col_plan else ''
        connus.setdefault(plan, set()).add(repere)
    return connus


def attendus_pour(connus, nom_plan):
    """Les repères attendus pour ce plan : par son nom exact, par la référence
    contenue dans le nom du fichier, ou la seule liste s'il n'y en a qu'une."""
    if not connus:
        return None
    if nom_plan in connus:
        return connus[nom_plan]
    haut = nom_plan.upper()
    proches = [p for p in connus if p and p.upper() in haut]
    if len(proches) == 1:
        return connus[proches[0]]
    if len(connus) == 1:
        return next(iter(connus.values()))
    return None


def _separateur(lignes):
    for candidat in (';', '\t', ','):
        comptes = [len(next(csv.reader([l], delimiter=candidat))) for l in lignes[:40]]
        if min(comptes) >= 2 and len(set(comptes)) == 1:
            return candidat
    return None


def _colonne(entete, mots):
    for mot in mots:
        for i, titre in enumerate(entete):
            if mot in titre:
                return i
    return None


def _sans_accents(texte):
    table = str.maketrans('àâäéèêëîïôöùûüç', 'aaaeeeeiioouuuc')
    return texte.translate(table)


# ---------------------------------------------------------------------------
#  Le compte rendu, et le CSV
# ---------------------------------------------------------------------------
def raconter(resultat, nom='', correspondances=None):
    """Le compte rendu d'un plan, tel qu'on le lit à l'écran."""
    tete = '%s : ' % (nom or 'Plan')
    if resultat.get('resume'):
        tete += resultat['resume'] + ', '
    tete += '%d boîte(s) retenue(s)' % resultat['boites']
    if resultat.get('cadres'):
        tete += ', %d cadre(s) ignoré(s)' % resultat['cadres']
    if resultat.get('pages', 0) > 1:
        tete += ' sur %d pages' % resultat['pages']
    lignes = [tete, '  %d composant(s) sûr(s)' % len(resultat['trouves'])]
    for c in resultat['trouves'][:20]:
        autres = [t for t in c['textes'] if t != c['repere']]
        lu = ' (lu « %s »)' % c['lu'] if c.get('lu') else ''
        lignes.append('    %-10s %s' % (c['repere'], (' · '.join(autres[:4]) + lu).strip()))
    if len(resultat['trouves']) > 20:
        lignes.append('    … et %d autre(s)' % (len(resultat['trouves']) - 20))
    corriges = [c for c in resultat['trouves'] if c.get('lu')]
    if corriges:
        lignes.append('  %d repère(s) corrigé(s) à la lecture : %s'
                      % (len(corriges), ', '.join('%s → %s' % (c['lu'], c['repere']) for c in corriges[:10])))
    if resultat['douteux']:
        lignes.append('  %d boîte(s) à regarder :' % len(resultat['douteux']))
        for d in resultat['douteux'][:10]:
            detail = d.get('reperes') or d.get('candidats') or d.get('textes') or ['(vide)']
            lignes.append('    %s — %s' % (d['pourquoi'], ', '.join(detail)[:60]))
    if resultat['orphelins']:
        lignes.append('  %d repère(s) sans boîte : %s'
                      % (len(resultat['orphelins']),
                         ', '.join(t['texte'] for t in resultat['orphelins'][:10])))
    if resultat.get('incertains'):
        lignes.append('  %d lecture(s) incertaine(s) hors boîte : %s'
                      % (len(resultat['incertains']),
                         ', '.join('%s ?' % t['texte'] for t in resultat['incertains'][:10])))
    if correspondances is not None:
        n = len(correspondances['communs']) + len(correspondances['absents'])
        lignes.append('  la base attend %d repère(s) : %d retrouvé(s) sur le plan'
                      % (n, len(correspondances['communs'])))
        if correspondances['absents']:
            lignes.append('    %d absent(s) du plan : %s'
                          % (len(correspondances['absents']), ', '.join(correspondances['absents'][:15])))
        if correspondances['en_plus']:
            lignes.append('    %d sur le plan, inconnu(s) de la base : %s'
                          % (len(correspondances['en_plus']), ', '.join(correspondances['en_plus'][:15])))
    return '\n'.join(lignes)


ENTETE_CSV = ['Fichier', 'Page', 'Repère', 'Statut', 'Lu', 'X', 'Y', 'Largeur', 'Hauteur', 'Textes']


def lignes_csv(resultat, nom='', correspondances=None):
    """Une ligne par chose vue : sûr, corrigé, douteux, orphelin — et les
    attendus absents quand une base a été donnée."""
    lignes = []
    for c in resultat['trouves']:
        lignes.append([nom, c.get('page', 1), c['repere'], 'corrigé' if c.get('lu') else 'sûr',
                       c.get('lu', ''), c['x'], c['y'], c['largeur'], c['hauteur'], ' | '.join(c['textes'])])
    for d in resultat['douteux']:
        r = d['rect']
        detail = d.get('reperes') or d.get('candidats') or d.get('textes') or []
        lignes.append([nom, d.get('page', 1), ' / '.join(detail), 'douteux : ' + d['pourquoi'], '',
                       r['x'], r['y'], r['largeur'], r['hauteur'], ' | '.join(d.get('textes', []))])
    for t in resultat['orphelins']:
        lignes.append([nom, t.get('page', 1), t['texte'], 'orphelin', t.get('lu', ''),
                       t['x'], t['y'], t.get('largeur', ''), t.get('hauteur', ''), ''])
    for t in resultat.get('incertains', []):
        lignes.append([nom, t.get('page', 1), ' / '.join(t['candidats']), 'incertain', t['texte'],
                       t['x'], t['y'], t.get('largeur', ''), t.get('hauteur', ''), ''])
    if correspondances:
        for repere in correspondances['absents']:
            lignes.append([nom, '', repere, 'attendu, absent du plan', '', '', '', '', '', ''])
    return lignes


def ecrire_csv(chemin, lignes):
    with open(chemin, 'w', encoding='utf-8-sig', newline='') as sortie:
        plume = csv.writer(sortie, delimiter=';')
        plume.writerow(ENTETE_CSV)
        plume.writerows(lignes)

#!/usr/bin/env python3
"""
L'essai à blanc : un faux GATES sur votre propre PC, pour apprendre la chaîne
sans intranet, sans risque, et sans rien casser.

Ce programme fabrique un dossier d'essai qui contient tout ce qu'il faut :

- une **page GATES d'essai** — un champ « Contrat », un bouton « Rechercher »,
  un tableau de résultats et un lien de téléchargement, comme l'intranet ;
- la **recette** qui va avec, déjà remplie : elle ouvre la page, cherche le
  contrat, clique, et récupère le CSV ;
- un **plan d'essai** en PDF, un en DXF, et sa version scannée, avec des
  repères dans des boîtes — dont un repère sans boîte et une boîte à deux
  repères, pour voir ce que le lecteur signale au lieu d'inventer ;
- la **liste des repères attendus**, comme une base de composants.

    python3 import/essai.py            prépare le dossier et affiche la marche à suivre
    python3 import/essai.py --jouer    fait tout tout seul, du début à la fin

`--jouer` lance son propre Chrome : il n'y a même pas besoin d'avoir préparé
le raccourci de débogage. C'est la façon la plus courte de voir la chaîne
fonctionner ; la marche à suivre, elle, apprend les vrais gestes.

Aucune dépendance : bibliothèque standard uniquement (la version scannée du
plan demande pillow, et son absence n'empêche rien d'autre).
"""

import argparse
import json
import os
import pathlib
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from piloter_chrome import Chrome, ErreurPilote, etat_du_poste     # noqa: E402
import extraire                                                    # noqa: E402

DOSSIER_DEFAUT = pathlib.Path(__file__).resolve().parent / 'essai'
PORT_ESSAI = 9223          # pas 9222 : l'essai ne dérange pas le Chrome du bureau


# ---------------------------------------------------------------------------
#  L'extract d'essai : les colonnes de GATES, et des plans qui leur ressemblent
# ---------------------------------------------------------------------------
GROUPES = ['', 'Informations principales', 'Informations principales', 'Informations principales',
           'Informations principales', 'Informations principales', 'Informations principales',
           'Informations principales', 'Informations principales', 'Informations principales',
           'Informations principales', 'Définition du plan', 'Définition du plan',
           'Définition du plan', 'Définition du plan', 'Définition du plan', 'Réalisation FWD']
TITRES = ['', 'Référence UD', 'RPT', '', '', 'Propa.', 'Libellé', 'Domaine', 'Type',
          'Date création', 'Nom Installation', 'CC', 'ATA', 'Séquence', 'ECP',
          'Validation Définition Electrique', 'Avancement']

# code circuit, ATA, séquence, solution, indice, libellé, domaine, ECP, date, avancement
PLANS = {
    'HDK': [
        ('TF', '2130', '600', '001', 'A', 'Alimentation tableau avant', 'BASE', 'ECP-1201', '2026-01-12', '100'),
        ('TF', '2130', '700', '001', 'A', 'Alimentation tableau avant (copilote)', 'BASE', 'ECP-1201', '2026-01-12', '100'),
        ('WL', '4610', '600', '003', 'C', 'Éclairage cabine', 'BASE', 'ECP-1188', '2026-01-19', '75'),
        ('WL', '4610', '800', '003', 'A', 'Éclairage — boîte de jonction', 'BASE', 'ECP-1188', '2026-01-19', '40'),
        ('KB', '3110', '600', '002', 'B', 'Tableau d\'alarmes', 'OPTION', 'ECP-1244', '2026-02-02', '100'),
        ('KB', '3110', '700', '002', 'A', 'Tableau d\'alarmes (copilote)', 'OPTION', 'ECP-1244', '2026-02-02', '60'),
        ('PA', '2420', '600', '005', 'A', 'Distribution 28 V', 'BASE', 'ECP-1201', '2026-02-16', '100'),
        ('PA', '2420', '800', '005', 'A', 'Distribution 28 V — panier à cartes', 'BASE', 'ECP-1201', '2026-02-16', '20'),
        ('HS', '2560', '600', '001', 'A', 'Treuil de sauvetage', 'PERSO', 'ECP-1310', '2026-03-02', '0'),
        ('HS', '2560', '700', '001', 'A', 'Treuil — commande copilote', 'PERSO', 'ECP-1310', '2026-03-02', ''),
        ('DG', '3420', '600', '004', 'B', 'Dégivrage pare-brise', 'BASE', 'ECP-1188', '2026-03-16', '90'),
        ('DG', '3420', '800', '004', 'A', 'Dégivrage — boîtier de régulation', 'BASE', 'ECP-1188', '2026-03-16', '55'),
        ('RA', '2310', '600', '002', 'A', 'Radio VHF', 'OPTION', 'ECP-1244', '2026-04-06', '100'),
        ('RA', '2310', '700', '002', 'A', 'Radio VHF (copilote)', 'OPTION', 'ECP-1244', '2026-04-06', '35'),
    ],
    'THS': [
        ('TF', '2130', '600', '001', 'B', 'Alimentation tableau avant', 'BASE', 'ECP-2001', '2026-01-26', '100'),
        ('WL', '4610', '600', '003', 'A', 'Éclairage cabine', 'BASE', 'ECP-2001', '2026-01-26', '45'),
        ('WL', '4610', '800', '003', 'A', 'Éclairage — boîte de jonction', 'BASE', 'ECP-2001', '2026-01-26', '0'),
        ('KB', '3110', '600', '002', 'A', 'Tableau d\'alarmes', 'OPTION', 'ECP-2044', '2026-02-09', '100'),
        ('PA', '2420', '600', '005', 'A', 'Distribution 28 V', 'BASE', 'ECP-2001', '2026-02-23', '80'),
        ('HS', '2560', '600', '001', 'A', 'Treuil de sauvetage', 'PERSO', 'ECP-2110', '2026-03-09', ''),
        ('DG', '3420', '600', '004', 'A', 'Dégivrage pare-brise', 'BASE', 'ECP-2044', '2026-03-23', '100'),
        ('RA', '2310', '700', '002', 'A', 'Radio VHF (copilote)', 'OPTION', 'ECP-2044', '2026-04-13', '25'),
    ],
    'VRK': [
        ('TF', '2130', '600', '001', 'A', 'Alimentation tableau avant', 'BASE', 'ECP-3300', '2026-02-02', '100'),
        ('WL', '4610', '600', '003', 'A', 'Éclairage cabine', 'BASE', 'ECP-3300', '2026-02-02', '100'),
        ('KB', '3110', '800', '002', 'A', 'Tableau d\'alarmes — boîtier', 'OPTION', 'ECP-3341', '2026-02-16', '15'),
        ('PA', '2420', '600', '005', 'B', 'Distribution 28 V', 'BASE', 'ECP-3300', '2026-03-02', '70'),
        ('HS', '2560', '700', '001', 'A', 'Treuil — commande copilote', 'PERSO', 'ECP-3412', '2026-03-16', '0'),
        ('DG', '3420', '600', '004', 'A', 'Dégivrage pare-brise', 'BASE', 'ECP-3341', '2026-03-30', '50'),
    ],
}


def reference(cc, ata, sequence, solution, indice):
    """L'anatomie d'une référence UD : code circuit, E, ATA, A, séquence,
    solution, indice — TFE2130A600001A."""
    return '%sE%sA%s%s%s' % (cc, ata, sequence, solution, indice)


def lignes_de(contrat):
    """L'extract d'un contrat : la ligne des groupes, celle des intitulés, puis les plans."""
    lignes = [list(GROUPES), list(TITRES)]
    for rang, (cc, ata, seq, sol, ind, libelle, domaine, ecp, date, avancement) in enumerate(PLANS[contrat], 1):
        lignes.append(['', reference(cc, ata, seq, sol, ind), '%s-%04d' % (contrat, 1000 + rang), '', '',
                       'Oui' if domaine == 'BASE' else 'Non', libelle, domaine,
                       'Modification' if ind != 'A' else 'Création', date,
                       'INST-%s-%s' % (ata, seq), cc, ata, seq, ecp,
                       'Validé' if avancement == '100' else '', avancement])
    return lignes


def csv_de(contrat):
    """Le CSV tel qu'un export d'entreprise le donne : point-virgule, guillemets
    quand il le faut, fins de ligne Windows."""
    sortie = []
    for ligne in lignes_de(contrat):
        cellules = []
        for cellule in ligne:
            if ';' in cellule or '"' in cellule:
                cellule = '"' + cellule.replace('"', '""') + '"'
            cellules.append(cellule)
        sortie.append(';'.join(cellules))
    return '\r\n'.join(sortie) + '\r\n'


# ---------------------------------------------------------------------------
#  La page d'essai : l'intranet en miniature
# ---------------------------------------------------------------------------
PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>GATES — extraction (essai)</title>
<style>
  body { font: 15px/1.5 "Segoe UI", system-ui, sans-serif; margin: 0; color: #1c2430; background: #eef1f5; }
  header { background: #123b66; color: #fff; padding: 14px 28px; }
  header b { font-size: 19px; letter-spacing: .02em; }
  header span { opacity: .75; margin-left: 10px; font-size: 13px; }
  main { max-width: 900px; margin: 24px auto; background: #fff; padding: 24px 28px 30px;
         border: 1px solid #d5dce5; border-radius: 6px; }
  h2 { font-size: 15px; text-transform: uppercase; letter-spacing: .08em; color: #5a6b80;
       margin: 0 0 14px; font-weight: 600; }
  label { font-weight: 600; margin-right: 8px; }
  input { font: inherit; padding: 6px 10px; border: 1px solid #a9b6c6; border-radius: 3px; width: 160px; }
  button { font: inherit; padding: 6px 16px; margin-left: 8px; border: 0; border-radius: 3px;
           background: #1a5fa8; color: #fff; cursor: pointer; }
  #etat { color: #5a6b80; font-size: 14px; min-height: 20px; }
  table { border-collapse: collapse; width: 100%; margin-top: 14px; font-size: 13px; }
  th, td { border: 1px solid #dfe5ec; padding: 5px 8px; text-align: left; }
  th { background: #f3f6fa; font-weight: 600; }
  #telecharger { display: inline-block; margin-top: 16px; padding: 8px 18px; background: #117a4a;
                 color: #fff; text-decoration: none; border-radius: 3px; font-weight: 600; }
  .note { margin-top: 26px; padding: 12px 16px; background: #fbf7e8; border-left: 3px solid #d6b33c;
          font-size: 13px; color: #4a4230; }
</style></head><body>
<header><b>GATES</b><span>poste d'essai — rien de tout ceci n'est réel</span></header>
<main>
  <h2>Extraction par contrat</h2>
  <label for="recherche">Contrat</label>
  <input id="recherche" value="" placeholder="HDK, THS ou VRK">
  <button id="chercher" type="button" onclick="chercher()">Rechercher</button>
  <p id="etat">Au repos.</p>
  <div id="resultats"></div>
  <p class="note">Cette page imite l'intranet pour apprendre la chaîne : un champ, un bouton,
     un tableau, un lien de téléchargement. Au bureau, seuls l'adresse, le nom du champ et le
     texte des boutons changent — la recette, elle, s'écrit pareil.</p>
</main>
<script>
var DONNEES = __DONNEES__;
function chercher() {
  var contrat = document.getElementById('recherche').value.trim().toUpperCase();
  var etat = document.getElementById('etat');
  var zone = document.getElementById('resultats');
  zone.innerHTML = '';
  if (!DONNEES[contrat]) {
    etat.textContent = 'Contrat inconnu : ' + (contrat || '(vide)') + '. Essayez HDK, THS ou VRK.';
    return;
  }
  etat.textContent = 'Recherche du contrat ' + contrat + '\\u2026';
  /* L'intranet met une seconde à répondre : la recette doit savoir attendre. */
  setTimeout(function () {
    var lignes = DONNEES[contrat].split('\\r\\n').filter(function (l) { return l.length; });
    var html = '<table id="tableau"><tr><th>Référence UD</th><th>Libellé</th><th>Domaine</th><th>Avancement</th></tr>';
    for (var i = 2; i < lignes.length; i++) {
      var c = lignes[i].split(';');
      html += '<tr><td>' + c[1] + '</td><td>' + c[6].replace(/^"|"$/g, '') + '</td><td>' + c[7] + '</td><td>' + (c[16] || '—') + '</td></tr>';
    }
    html += '</table>';
    zone.innerHTML = html +
      '<a id="telecharger" download="extract-' + contrat + '.csv" href="data:text/csv;charset=utf-8,' +
      encodeURIComponent('\\ufeff' + DONNEES[contrat]) + '">Télécharger l\\'extract</a>';
    etat.textContent = contrat + ' : ' + (lignes.length - 2) + ' plan(s) trouvé(s).';
  }, 900);
}
</script>
</body></html>
"""


def page_html():
    return PAGE.replace('__DONNEES__', json.dumps({c: csv_de(c) for c in PLANS}, ensure_ascii=False))


# ---------------------------------------------------------------------------
#  Le plan d'essai : un PDF de dessin, un DXF, et une version scannée
# ---------------------------------------------------------------------------
# Les composants du plan : repère, texte qui l'accompagne, et sa boîte.
COMPOSANTS = [
    ('18AB', 'Connecteur', 'PN-1001', 90, 430),
    ('120PA3', 'Boitier', 'PN-1002', 300, 430),
    ('7XY', 'Relais', 'PN-1003', 510, 430),
    ('19CD', 'Bornier', 'PN-1004', 90, 300),
    ('31AB2', 'Disjoncteur', 'PN-1005', 300, 300),
]
BOITE_DOUBLE = (510, 300)      # une boîte où deux repères sont écrits : à signaler
SANS_BOITE = (200, 160)        # un repère écrit à l'écart : sans boîte, à signaler
ATTENDUS = ['18AB', '120PA3', '7XY', '19CD', '31AB2', '44XY', '45XZ', '66ZZ']


def _pdf(contenu):
    """Un PDF d'une page portant ce flux de dessin."""
    flux = zlib.compress(contenu.encode('cp1252'))
    objets = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Contents 4 0 R '
        b'/Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length ' + str(len(flux)).encode('ascii') + b' /Filter /FlateDecode >>\nstream\n' + flux + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    sortie = bytearray(b'%PDF-1.4\n')
    positions = []
    for rang, corps in enumerate(objets, 1):
        positions.append(len(sortie))
        sortie += str(rang).encode('ascii') + b' 0 obj\n' + corps + b'\nendobj\n'
    debut = len(sortie)
    sortie += b'xref\n0 ' + str(len(objets) + 1).encode('ascii') + b'\n0000000000 65535 f \n'
    for p in positions:
        sortie += ('%010d 00000 n \n' % p).encode('ascii')
    sortie += (b'trailer\n<< /Size ' + str(len(objets) + 1).encode('ascii') +
               b' /Root 1 0 R >>\nstartxref\n' + str(debut).encode('ascii') + b'\n%%EOF\n')
    return bytes(sortie)


def plan_pdf():
    """Le plan d'essai, comme un outil de dessin le sort : du texte et des traits."""
    morceaux = ['0.6 w\n']
    for repere, quoi, pn, x, y in COMPOSANTS:
        morceaux.append('%d %d 150 70 re S\n' % (x, y))
        morceaux.append(_ecrire(x + 10, y + 48, repere, 11))
        morceaux.append(_ecrire(x + 10, y + 30, quoi, 8))
        morceaux.append(_ecrire(x + 10, y + 14, pn, 8))
        morceaux.append('%d %d m %d %d l S\n' % (x + 150, y + 35, x + 190, y + 35))   # le fil
    x, y = BOITE_DOUBLE
    morceaux.append('%d %d 150 70 re S\n' % (x, y))
    morceaux.append(_ecrire(x + 10, y + 48, '44XY', 11))
    morceaux.append(_ecrire(x + 80, y + 48, '45XZ', 11))
    morceaux.append(_ecrire(x + 10, y + 30, 'Double repere', 8))
    morceaux.append(_ecrire(SANS_BOITE[0], SANS_BOITE[1], '91AA', 11))
    morceaux.append('20 20 802 555 re S\n')                                            # le cadre
    morceaux.append(_ecrire(40, 545, 'TFE2130A600001A  -  Alimentation tableau avant', 10))
    morceaux.append(_ecrire(40, 60, 'PLAN D\'ESSAI - aucune valeur industrielle', 9))
    return _pdf(''.join(morceaux))


def _ecrire(x, y, texte, taille):
    echappe = texte.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')
    return 'BT /F1 %d Tf 1 0 0 1 %d %d Tm (%s) Tj ET\n' % (taille, x, y, echappe)


def plan_dxf():
    """Le même plan, exporté en DXF, avec un bloc par équipement."""
    def p(code, valeur):
        return '%d\n%s\n' % (code, valeur)

    def rect(x, y, l, h):
        return (p(0, 'LWPOLYLINE') + p(8, 'CONTOURS') + p(90, 4) + p(70, 1) +
                p(10, x) + p(20, y) + p(10, x + l) + p(20, y) +
                p(10, x + l) + p(20, y + h) + p(10, x) + p(20, y + h))

    def texte(x, y, t, hauteur=3.5):
        return p(0, 'TEXT') + p(8, 'TEXTES') + p(10, x) + p(20, y) + p(40, hauteur) + p(1, t)
    entites = []
    for rang, (repere, quoi, pn, x, y) in enumerate(COMPOSANTS):
        bx, by = 20 + (rang % 3) * 90, 120 - (rang // 3) * 60
        entites.append(rect(bx, by, 60, 30) + texte(bx + 4, by + 18, repere) +
                       texte(bx + 4, by + 8, pn, 2.5))
    entites.append(rect(10, 10, 380, 260))
    entites.append(texte(16, 265, 'TFE2130A600001A', 4))
    return (p(0, 'SECTION') + p(2, 'HEADER') + p(9, '$INSUNITS') + p(70, 4) + p(0, 'ENDSEC') +
            p(0, 'SECTION') + p(2, 'ENTITIES') + ''.join(entites) + p(0, 'ENDSEC') + p(0, 'EOF'))


def plan_scanne(chemin):
    """La version scannée du plan — papier gris, traits un peu tremblés. Sans
    pillow, on s'en passe et on le dit."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except ImportError:
        return None
    largeur, hauteur = 1684, 1190
    image = Image.new('L', (largeur, hauteur), 255)
    dessin = ImageDraw.Draw(image)

    def police(taille):
        try:
            return ImageFont.load_default(size=taille)
        except TypeError:
            return ImageFont.load_default()
    grande, petite = police(26), police(18)
    for repere, quoi, pn, x, y in COMPOSANTS:
        gx, gy = x * 2, (595 - y - 70) * 2
        dessin.rectangle([gx, gy, gx + 300, gy + 140], outline=0, width=3)
        dessin.text((gx + 18, gy + 16), repere, fill=0, font=grande)
        dessin.text((gx + 18, gy + 60), quoi, fill=0, font=petite)
        dessin.text((gx + 18, gy + 90), pn, fill=0, font=petite)
        dessin.line([gx + 300, gy + 70, gx + 380, gy + 70], fill=0, width=3)
    x, y = BOITE_DOUBLE
    gx, gy = x * 2, (595 - y - 70) * 2
    dessin.rectangle([gx, gy, gx + 300, gy + 140], outline=0, width=3)
    dessin.text((gx + 18, gy + 16), '44XY', fill=0, font=grande)
    dessin.text((gx + 160, gy + 16), '45XZ', fill=0, font=grande)
    dessin.text((SANS_BOITE[0] * 2, (595 - SANS_BOITE[1]) * 2), '91AA', fill=0, font=grande)
    dessin.rectangle([40, 40, largeur - 40, hauteur - 40], outline=0, width=4)
    dessin.text((80, 70), 'TFE2130A600001A  -  Alimentation tableau avant', fill=0, font=petite)
    try:                                       # le grain du papier et de la vitre
        import random
        brouillard = Image.new('L', (largeur, hauteur))
        hasard = random.Random(7)
        brouillard.putdata([236 + hasard.randrange(20) for _ in range(largeur * hauteur)])
        image = Image.blend(image.convert('L'), brouillard, 0.10).filter(ImageFilter.GaussianBlur(0.5))
    except Exception:
        pass
    image.save(str(chemin))
    return chemin


def base_composants():
    """La base des composants, comme un extract de connecteurs : le plan, le
    repère, et le part number. 66ZZ n'est pas sur le plan : c'est voulu."""
    lignes = ['Plan;Repère ELEC;Part Number']
    pn = {r: p for r, _, p, _, _ in COMPOSANTS}
    for repere in ATTENDUS:
        lignes.append('TFE2130A600001A;%s;%s' % (repere, pn.get(repere, 'PN-9%03d' % (ATTENDUS.index(repere) + 1))))
    return '\r\n'.join(lignes) + '\r\n'


# ---------------------------------------------------------------------------
#  Préparer le dossier
# ---------------------------------------------------------------------------
def recette(dossier):
    """La recette d'essai, déjà remplie : elle vise la page du dossier."""
    return {
        'nom': 'GATES d\'essai — un extract par contrat',
        '_ceci_est_un_essai': [
            'Au bureau, il n\'y a que trois choses à changer dans ce fichier :',
            '  1. « telechargements » : votre dossier de téléchargement,',
            '  2. l\'« url » de la première étape : l\'adresse de GATES,',
            '  3. les sélecteurs (#recherche) et les textes de boutons, s\'ils diffèrent.',
            'Le reste — la suite des gestes — ne change pas.',
        ],
        'telechargements': str(dossier / 'telechargements'),
        'variable': 'contrat',
        'valeurs': sorted(PLANS),
        'etapes': [
            {'faire': 'ouvrir', 'url': (dossier / 'gates-essai.html').as_uri()},
            {'faire': 'attendre', 'ou': '#recherche'},
            {'faire': 'remplir', 'ou': '#recherche', 'texte': '{contrat}'},
            {'faire': 'cliquer_texte', 'texte': 'Rechercher'},
            {'faire': 'attendre', 'ou': '#telecharger', 'delai': 30},
            {'faire': 'cliquer', 'ou': '#telecharger'},
            {'faire': 'telecharger', 'vers': 'gates-{contrat}.csv', 'delai': 60},
        ],
    }


def preparer(dossier):
    """Écrit tout le dossier d'essai et rend la liste de ce qui a été fait."""
    dossier = pathlib.Path(dossier)
    (dossier / 'telechargements').mkdir(parents=True, exist_ok=True)
    faits = []
    page = dossier / 'gates-essai.html'
    page.write_text(page_html(), encoding='utf-8')
    faits.append((page, 'la page GATES d\'essai (à ouvrir dans Chrome pour voir)'))
    fichier = dossier / 'recette-essai.json'
    fichier.write_text(json.dumps(recette(dossier), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    faits.append((fichier, 'la recette, déjà remplie pour cette page'))
    fichier = dossier / 'plan-essai.pdf'
    fichier.write_bytes(plan_pdf())
    faits.append((fichier, 'un plan en PDF de dessin (5 composants, 1 boîte double, 1 repère sans boîte)'))
    fichier = dossier / 'plan-essai.dxf'
    fichier.write_text(plan_dxf(), encoding='utf-8')
    faits.append((fichier, 'le même plan exporté en DXF'))
    scanne = plan_scanne(dossier / 'plan-essai-scanne.png')
    if scanne:
        faits.append((scanne, 'la version scannée du plan (papier gris, pour la reconnaissance de caractères)'))
    fichier = dossier / 'composants-base.csv'
    fichier.write_text(base_composants(), encoding='utf-8-sig')
    faits.append((fichier, 'la base des composants attendus (66ZZ n\'est pas sur le plan : c\'est voulu)'))
    return dossier, faits


# ---------------------------------------------------------------------------
#  La marche à suivre
# ---------------------------------------------------------------------------
def marche_a_suivre(dossier):
    d = str(dossier)
    racine = str(pathlib.Path(__file__).resolve().parent.parent)
    return """
================================================================
  LA MARCHE À SUIVRE — un quart d'heure, une seule fois
================================================================

Toutes les commandes se tapent dans l'Invite de commandes (touche Windows,
taper « cmd »), depuis le dossier du projet :

    cd {racine}

----------------------------------------------------------------
  1. Voir ce que le poste sait faire
----------------------------------------------------------------

    python import\\piloter_chrome.py

Trois lignes : la version de Python, le Chrome trouvé, et l'état du canal.
Le canal est « fermé » : c'est normal, on l'ouvre à l'étape 2.

----------------------------------------------------------------
  2. Ouvrir le canal de Chrome (une seule fois, puis un raccourci)
----------------------------------------------------------------

Fermer Chrome ENTIÈREMENT (toutes les fenêtres), puis :

    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222

Chrome s'ouvre comme d'habitude — mêmes onglets, mêmes favoris, même
authentification. Relancer la commande de l'étape 1 : le canal est « ouvert ».

Pour ne plus jamais retaper cela : clic droit sur le raccourci Chrome →
Propriétés → à la fin de « Cible », ajouter un espace puis
--remote-debugging-port=9222 — et n'utiliser que ce raccourci.

----------------------------------------------------------------
  3. Regarder la page d'essai (facultatif, mais instructif)
----------------------------------------------------------------

Ouvrir dans Chrome :   {page}

Taper HDK, cliquer « Rechercher », puis « Télécharger l'extract ».
C'est exactement ce que le script va faire tout seul — en une seconde.

----------------------------------------------------------------
  4. Jouer la recette
----------------------------------------------------------------

    python import\\extraire.py "{recette}" --verifier
    python import\\extraire.py "{recette}"

La première commande relit la recette sans rien lancer. La seconde la joue :
Chrome ouvre un onglet à part, cherche HDK, THS, VRK et récupère trois CSV
dans :

    {telechargements}

Ouvrir gates-HDK.csv : c'est un extract GATES, avec ses deux lignes d'en-tête.

----------------------------------------------------------------
  5. Lire les composants d'un plan
----------------------------------------------------------------

    python import\\lire_composants.py "{pdf}" --connus "{base}"

Le compte rendu doit dire : 5 composants sûrs, une boîte à deux repères,
un repère sans boîte, et 66ZZ attendu mais absent du plan. Rien n'est
inventé — c'est tout l'intérêt.

Le même plan en DXF :

    python import\\lire_composants.py "{dxf}" --connus "{base}"

Et le scan, si pillow est installé ({scan}) :

    pip install numpy pillow opencv-python-headless rapidocr-onnxruntime
    python import\\lire_composants.py "{scan}" --connus "{base}" --controle "{dossier}"

Le PNG « -controle » montre en vert ce qui est sûr, en orange ce qui est
douteux, en rouge ce qui n'a pas de boîte.

================================================================
  CE QUI CHANGE AU BUREAU
================================================================

Copier {recette} à côté, sous un autre nom, et changer TROIS choses :

  1. "telechargements" : votre vrai dossier de téléchargement,
                         par exemple "%USERPROFILE%/Downloads"
  2. l'"url" de la première étape : l'adresse de GATES
  3. les sélecteurs et les textes de boutons, s'ils diffèrent :
     "#recherche" devient ce que vous lisez dans F12 (clic droit sur le
     champ → Inspecter → relever son id), et "Rechercher" / le lien de
     téléchargement deviennent les textes réels des boutons.

Le reste ne bouge pas. Et si une étape rate, le script dit laquelle et
pourquoi, au lieu de continuer dans le vide.
""".format(racine=racine, page=str(dossier / 'gates-essai.html'), dossier=d,
           recette=str(dossier / 'recette-essai.json'),
           telechargements=str(dossier / 'telechargements'),
           pdf=str(dossier / 'plan-essai.pdf'), dxf=str(dossier / 'plan-essai.dxf'),
           base=str(dossier / 'composants-base.csv'),
           scan=str(dossier / 'plan-essai-scanne.png'))


# ---------------------------------------------------------------------------
#  Tout jouer, tout seul
# ---------------------------------------------------------------------------
def jouer(dossier, port=PORT_ESSAI, contrats=None, sans_fenetre=False, options=None, journal=print,
          lire_les_plans=True):
    """Joue la chaîne entière sur le dossier d'essai : Chrome, extraction,
    lecture du plan. Rend les fichiers obtenus."""
    dossier = pathlib.Path(dossier)
    recette_jouee = extraire.lire_recette(dossier / 'recette-essai.json')
    tours = contrats or sorted(PLANS)
    journal('\n— Chrome —')
    journal(etat_du_poste())
    journal('\n— Extraction —')
    fichiers = []
    with Chrome(port=port, telechargements=dossier / 'telechargements', lancer=True,
                profil=str(dossier / 'profil-chrome'), sans_fenetre=sans_fenetre,
                options=options or []) as chrome:
        for contrat in tours:
            journal('  · %s' % contrat)
            recolte = extraire.jouer(chrome, recette_jouee, {'contrat': contrat}, journal)
            fichiers += recolte['fichiers']
    for fichier in fichiers:
        lignes = fichier.read_text(encoding='utf-8-sig').splitlines()
        journal('\n  %s — %d ligne(s) :' % (fichier.name, len(lignes)))
        for ligne in lignes[:4]:
            journal('    ' + (ligne[:110] + '…' if len(ligne) > 110 else ligne))
        if len(lignes) > 4:
            journal('    … et %d autre(s)' % (len(lignes) - 4))
    if not lire_les_plans:
        return fichiers
    journal('\n— Composants du plan —')
    import lire_composants
    for plan in ('plan-essai.pdf', 'plan-essai.dxf', 'plan-essai-scanne.png'):
        chemin = dossier / plan
        if not chemin.exists():
            continue
        if plan.endswith('.png'):
            try:
                import cv2, numpy, PIL                                   # noqa: F401
            except ImportError:
                journal('\n  %s : non lu — pip install numpy pillow opencv-python-headless '
                        'rapidocr-onnxruntime' % plan)
                continue
        journal('')
        code = lire_composants.main([str(chemin), '--connus', str(dossier / 'composants-base.csv')] +
                                    (['--controle', str(dossier)] if plan.endswith('.png') else []))
        if code:
            journal('  (ce plan n\'a pas pu être lu — voir le message ci-dessus)')
    return fichiers


def main(argv=None):
    parseur = argparse.ArgumentParser(description='L\'essai à blanc : un faux GATES sur ce PC.')
    parseur.add_argument('--dossier', default=str(DOSSIER_DEFAUT), help='où poser le dossier d\'essai')
    parseur.add_argument('--jouer', action='store_true', help='jouer la chaîne entière tout seul')
    parseur.add_argument('--contrat', action='append', help='ne jouer que ce(s) contrat(s)')
    parseur.add_argument('--port', type=int, default=PORT_ESSAI, help='le port du Chrome d\'essai')
    parseur.add_argument('--sans-fenetre', action='store_true', help='sans ouvrir de fenêtre Chrome')
    args = parseur.parse_args(argv)
    dossier, faits = preparer(args.dossier)
    print('Dossier d\'essai : %s' % dossier)
    for chemin, quoi in faits:
        print('  %-26s %s' % (chemin.name, quoi))
    if not args.jouer:
        print(marche_a_suivre(dossier))
        print('Pour tout voir fonctionner d\'un coup, sans rien préparer :')
        print('    python import\\essai.py --jouer')
        return 0
    options = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
    try:
        jouer(dossier, args.port, args.contrat, args.sans_fenetre, options)
    except ErreurPilote as err:
        print('\nArrêt : %s' % err, file=sys.stderr)
        return 1
    print('\n— Voilà. —')
    print('C\'est toute la chaîne : Chrome a cherché, téléchargé, et le plan a été lu.')
    print('La marche à suivre pas à pas, avec les vrais gestes :')
    print('    python import\\essai.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())

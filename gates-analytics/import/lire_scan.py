#!/usr/bin/env python3
"""
Lit un plan ELEC **scanné** — une image, ou un PDF qui ne contient qu'une
image — et en retire les composants : les boîtes, et le repère écrit dedans
ou juste à côté.

Ce que ce programme fait, dans l'ordre :

1. il sort l'image du fichier (PNG, JPEG, TIFF, ou l'image enfouie dans le
   PDF : JPEG, CCITT de télécopie, brute compressée) ;
2. il trouve les **boîtes** — les rectangles fermés tracés à l'encre — par
   une analyse d'image classique, sans apprentissage, donc sans surprise ;
3. il fait lire le texte par un moteur de **reconnaissance de caractères**,
   deux fois : la page entière, puis chaque boîte agrandie, là où le repère
   est petit ;
4. il comprend chaque mot lu comme un repère, en corrigeant ce qu'une lecture
   confond (O et 0, I et 1, S et 5…) mais **seulement quand une seule forme
   est possible** — la liste des repères que la base attend tranche les
   autres cas ;
5. il rattache chaque repère à sa boîte, avec la règle commune à tous les
   lecteurs : une boîte, un repère, sinon c'est dit.

Deux moteurs de lecture, tous deux hors ligne :

- **RapidOCR** — `pip install rapidocr-onnxruntime` : un paquet Python
  ordinaire, sans exécutable ; le plus sûr des deux ;
- **le moteur intégré à Windows 10/11** (`ocr_windows.ps1`) : rien à
  installer du tout.

Il faut aussi `numpy`, `pillow` et `opencv-python-headless` — des paquets
Python ordinaires, eux aussi.

    python3 import/lire_scan.py scan.pdf
    python3 import/lire_scan.py plan.png --connus base.csv --csv composants.csv --controle .
"""

import argparse
import base64
import io
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from composants import (ErreurPlan, REPERE, composants, interpreter_mots, raconter,   # noqa: E402
                        lignes_csv, ecrire_csv, lire_connus, attendus_pour, correspondance)

SCRIPT_WINDOWS = pathlib.Path(__file__).resolve().parent / 'ocr_windows.ps1'
ORIENTATIONS = (0, 90, 270, 180)     # dans cet ordre : le plus probable d'abord
TUILE = 1600                         # la page entière se lit par morceaux de ce côté
CHEVAUCHEMENT = 120                  # qui se recouvrent, pour ne couper aucun mot
CONFIANCE_MINI = 0.5


# ---------------------------------------------------------------------------
#  Les bibliothèques d'image, chargées quand on en a besoin
# ---------------------------------------------------------------------------
def _np():
    try:
        import numpy
    except ImportError:
        raise ErreurPlan(
            'Lire un scan demande numpy, pillow et opencv-python-headless — des paquets Python '
            'ordinaires : pip install numpy pillow opencv-python-headless')
    return numpy


def _cv2():
    try:
        import cv2
    except ImportError:
        raise ErreurPlan(
            'Lire un scan demande opencv-python-headless (un paquet Python ordinaire, sans '
            'exécutable) : pip install opencv-python-headless')
    return cv2


def _pil():
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise ErreurPlan('Lire un scan demande pillow : pip install pillow')
    return Image, ImageOps


# ---------------------------------------------------------------------------
#  L'image : d'un fichier image, ou enfouie dans un PDF
# ---------------------------------------------------------------------------
def images_de(chemin):
    """[(numéro de page, image en niveaux de gris — tableau numpy)]."""
    fichier = pathlib.Path(chemin)
    if not fichier.exists():
        raise ErreurPlan('Plan introuvable : %s' % fichier)
    donnees = fichier.read_bytes()
    Image, _ = _pil()
    if donnees.startswith(b'%PDF'):
        images = images_du_pdf(donnees)
        if not images:
            raise ErreurPlan(
                '%s ne contient aucune image de page : ce n\'est pas un scan. S\'il porte du '
                'texte et des traits, c\'est lire_plan.py qui le lit.' % fichier.name)
    else:
        try:
            source = Image.open(io.BytesIO(donnees))
        except Exception:
            raise ErreurPlan('%s n\'est ni une image lisible (PNG, JPEG, TIFF, BMP) ni un PDF.'
                             % fichier.name)
        images = []
        for rang in range(getattr(source, 'n_frames', 1)):
            source.seek(rang)
            images.append(source.copy())
    return [(rang + 1, en_gris(im)) for rang, im in enumerate(images)]


def en_gris(image):
    np = _np()
    if image.mode == 'CMYK':
        image = image.convert('RGB')
    if image.mode != 'L':
        image = image.convert('L')
    return np.asarray(image, dtype='uint8')


OBJET = re.compile(rb'(\d+)\s+\d+\s+obj\b')


def images_du_pdf(donnees):
    """Les images de page enfouies dans le PDF, dans l'ordre du fichier —
    sans les vignettes ni les masques de transparence."""
    Image, ImageOps = _pil()
    masques = set(int(m.group(1)) for m in re.finditer(rb'/SMask\s+(\d+)\s+\d+\s+R', donnees))
    images = []
    for trouvaille in OBJET.finditer(donnees):
        numero = int(trouvaille.group(1))
        debut = trouvaille.end()
        pos_flux = donnees.find(b'stream', debut)
        fin_objet = donnees.find(b'endobj', debut)
        if pos_flux == -1 or (fin_objet != -1 and fin_objet < pos_flux):
            continue
        entete = donnees[debut:pos_flux]
        if not re.search(rb'/Subtype\s*/Image\b', entete) or numero in masques:
            continue
        dico = dictionnaire_image(entete)
        if dico['largeur'] < 64 or dico['hauteur'] < 64:
            continue                                   # un logo, une vignette
        brut = flux_apres(donnees, pos_flux, dico['longueur'])
        image = decoder_image(dico, brut)
        if dico['inverse']:
            image = ImageOps.invert(image.convert('L'))
        images.append(image)
    return images


def dictionnaire_image(entete):
    def nombre(cle, defaut=None):
        m = re.search(rb'/' + cle + rb'\s+(-?\d+)(?!\s+\d+\s+R)', entete)
        return int(m.group(1)) if m else defaut

    def booleen(cle, defaut=False):
        m = re.search(rb'/' + cle + rb'\s+(true|false)', entete)
        return m.group(1) == b'true' if m else defaut

    filtres = []
    m = re.search(rb'/Filter\s*(/\w+|\[[^\]]*\])', entete)
    if m:
        filtres = [f.decode('ascii') for f in re.findall(rb'/(\w+)', m.group(1))]
    espace = 'DeviceGray'
    palette = None
    m = re.search(rb'/ColorSpace\s*(/\w+|\[[^\]]*\])', entete)
    if m:
        noms = re.findall(rb'/(\w+)', m.group(1))
        if noms and noms[0] == b'Indexed':
            espace = 'Indexed'
            hexa = re.search(rb'<([0-9A-Fa-f\s]+)>', m.group(1))
            if hexa:
                palette = bytes.fromhex(re.sub(rb'\s', b'', hexa.group(1)).decode('ascii'))
        elif noms:
            espace = noms[-1].decode('ascii')
    decode = re.search(rb'/Decode\s*\[\s*([0-9.]+)', entete)
    return {
        'largeur': nombre(b'Width', 0), 'hauteur': nombre(b'Height', 0),
        'bits': nombre(b'BitsPerComponent', 1 if booleen(b'ImageMask') else 8),
        'espace': espace, 'palette': palette, 'filtres': filtres,
        'longueur': nombre(b'Length'), 'masque': booleen(b'ImageMask'),
        'inverse': bool(decode and decode.group(1).startswith(b'1')),
        'k': nombre(b'K', 0), 'colonnes': nombre(b'Columns', 1728), 'lignes': nombre(b'Rows'),
        'aligne': booleen(b'EncodedByteAlign'), 'noir_vaut_1': booleen(b'BlackIs1'),
        'predicteur': nombre(b'Predictor', 1), 'couleurs': nombre(b'Colors', 1),
    }


def flux_apres(donnees, pos_flux, longueur):
    m = re.match(rb'stream\r?\n', donnees[pos_flux:pos_flux + 8])
    debut = pos_flux + (m.end() if m else 6)
    if longueur is not None and donnees[debut + longueur:debut + longueur + 12].lstrip().startswith(b'endstream'):
        return donnees[debut:debut + longueur]
    fin = donnees.find(b'endstream', debut)
    if fin == -1:
        fin = len(donnees)
    return donnees[debut:fin].rstrip(b'\r\n')


def decoder_image(dico, brut):
    """L'image PIL, quel que soit l'empilement de filtres du PDF."""
    Image, _ = _pil()
    donnees = brut
    for filtre in dico['filtres']:
        if filtre in ('FlateDecode', 'Fl'):
            donnees = zlib.decompress(donnees)
            if dico['predicteur'] >= 10:
                return image_png(donnees, dico)
            if dico['predicteur'] == 2:
                donnees = depredire_tiff(donnees, dico)
        elif filtre in ('LZWDecode', 'LZW'):
            donnees = decoder_lzw(donnees)
            if dico['predicteur'] >= 10:
                return image_png(donnees, dico)
        elif filtre in ('ASCIIHexDecode', 'AHx'):
            donnees = bytes.fromhex(re.sub(rb'[^0-9A-Fa-f]', b'', donnees.split(b'>')[0]).decode('ascii'))
        elif filtre in ('ASCII85Decode', 'A85'):
            donnees = base64.a85decode(donnees.split(b'~>')[0], adobe=False)
        elif filtre in ('RunLengthDecode', 'RL'):
            donnees = decoder_rle(donnees)
        elif filtre in ('DCTDecode', 'DCT', 'JPXDecode'):
            try:
                image = Image.open(io.BytesIO(donnees))
                image.load()
            except Exception as err:
                raise ErreurPlan('Une image du PDF (%s) ne se décode pas : %s' % (filtre, err))
            return image
        elif filtre in ('CCITTFaxDecode', 'CCF'):
            return image_ccitt(donnees, dico)
        elif filtre == 'JBIG2Decode':
            raise ErreurPlan(
                'Ce PDF porte une image JBIG2, un format de compression que rien ne lit ici. '
                'Rescanner en PDF « image JPEG » ou en TIFF/PNG, ou réenregistrer le PDF avec '
                'un autre outil.')
        else:
            raise ErreurPlan('Une image du PDF utilise un filtre inconnu : %s.' % filtre)
    return image_brute(donnees, dico)


def image_brute(donnees, dico):
    """Des échantillons nus — 1 ou 8 bits, gris, RVB ou CMJN — en image."""
    Image, _ = _pil()
    largeur, hauteur, bits = dico['largeur'], dico['hauteur'], dico['bits']
    if dico['masque'] or bits == 1:
        attendu = (largeur + 7) // 8 * hauteur
        if len(donnees) < attendu:
            raise ErreurPlan('Une image du PDF est tronquée (%d octets pour %d attendus).' % (len(donnees), attendu))
        return Image.frombytes('1', (largeur, hauteur), donnees[:attendu], 'raw', '1')
    if bits == 16:
        np = _np()
        canaux = {'DeviceGray': 1, 'DeviceRGB': 3, 'DeviceCMYK': 4}.get(dico['espace'], 1)
        tableau = np.frombuffer(donnees[:largeur * hauteur * canaux * 2], dtype='>u2')
        donnees = (tableau >> 8).astype('uint8').tobytes()
        bits = 8
    if bits != 8:
        raise ErreurPlan('Une image du PDF est codée sur %d bits par composante : cas non traité.' % bits)
    if dico['espace'] == 'Indexed':
        image = Image.frombytes('L', (largeur, hauteur), donnees[:largeur * hauteur], 'raw', 'L')
        if dico['palette']:
            image = image.convert('P')
            image.putpalette(dico['palette'][:768].ljust(768, b'\0'))
        return image
    mode = {'DeviceGray': 'L', 'CalGray': 'L', 'DeviceRGB': 'RGB', 'CalRGB': 'RGB',
            'ICCBased': None, 'DeviceCMYK': 'CMYK'}.get(dico['espace'], 'L')
    if mode is None:                                 # ICC : on déduit du volume
        canaux = len(donnees) // max(1, largeur * hauteur)
        mode = {1: 'L', 3: 'RGB', 4: 'CMYK'}.get(canaux, 'L')
    attendu = largeur * hauteur * len(mode)
    if len(donnees) < attendu:
        raise ErreurPlan('Une image du PDF est tronquée (%d octets pour %d attendus).' % (len(donnees), attendu))
    return Image.frombytes(mode, (largeur, hauteur), donnees[:attendu], 'raw', mode)


def image_png(donnees, dico):
    """Des lignes filtrées « à la PNG » : on les remet dans un PNG, que la
    bibliothèque d'image décode elle-même — c'est exactement son format."""
    Image, _ = _pil()
    couleurs, bits = dico['couleurs'], dico['bits']
    type_couleur = {1: 0, 2: 4, 3: 2, 4: 6}.get(couleurs)
    if type_couleur is None:
        raise ErreurPlan('Une image du PDF a %d composantes par pixel : cas non traité.' % couleurs)

    def bloc(nom, contenu):
        return (struct.pack('>I', len(contenu)) + nom + contenu +
                struct.pack('>I', zlib.crc32(nom + contenu) & 0xFFFFFFFF))
    entete = struct.pack('>IIBBBBB', dico['largeur'], dico['hauteur'], bits, type_couleur, 0, 0, 0)
    png = (b'\x89PNG\r\n\x1a\n' + bloc(b'IHDR', entete) +
           bloc(b'IDAT', zlib.compress(donnees, 1)) + bloc(b'IEND', b''))
    image = Image.open(io.BytesIO(png))
    image.load()
    return image


def depredire_tiff(donnees, dico):
    """Le prédicteur TIFF (2) : chaque octet est la différence avec le précédent."""
    np = _np()
    if dico['bits'] != 8:
        return donnees
    couleurs, colonnes = dico['couleurs'], dico['colonnes'] if dico['colonnes'] else dico['largeur']
    largeur_ligne = couleurs * colonnes
    lignes = len(donnees) // largeur_ligne
    tableau = np.frombuffer(donnees[:lignes * largeur_ligne], dtype='uint8').reshape(lignes, colonnes, couleurs)
    return np.cumsum(tableau, axis=1, dtype='uint8').tobytes()


def decoder_lzw(donnees, precoce=1):
    """Le LZW des PDF (9 à 12 bits, changement précoce)."""
    sortie = bytearray()
    dictionnaire = None
    largeur, precedent = 9, None
    tampon, nb_bits = 0, 0
    for octet in donnees:
        tampon = (tampon << 8) | octet
        nb_bits += 8
        while nb_bits >= largeur:
            code = (tampon >> (nb_bits - largeur)) & ((1 << largeur) - 1)
            nb_bits -= largeur
            if code == 256:
                dictionnaire = [bytes([i]) for i in range(256)] + [b'', b'']
                largeur, precedent = 9, None
                continue
            if code == 257:
                return bytes(sortie)
            if dictionnaire is None:
                dictionnaire = [bytes([i]) for i in range(256)] + [b'', b'']
            if code < len(dictionnaire):
                mot = dictionnaire[code]
                if precedent is not None:
                    dictionnaire.append(precedent + mot[:1])
            elif precedent is not None:
                mot = precedent + precedent[:1]
                dictionnaire.append(mot)
            else:
                raise ErreurPlan('Une image LZW du PDF est abîmée.')
            sortie += mot
            precedent = mot
            if len(dictionnaire) + precoce - 1 >= (1 << largeur) and largeur < 12:
                largeur += 1
    return bytes(sortie)


def decoder_rle(donnees):
    sortie = bytearray()
    i = 0
    while i < len(donnees):
        n = donnees[i]
        if n == 128:
            break
        if n < 128:
            sortie += donnees[i + 1:i + 2 + n]
            i += 2 + n
        else:
            sortie += donnees[i + 1:i + 2] * (257 - n)
            i += 2
    return bytes(sortie)


def image_ccitt(donnees, dico):
    """Un flux de télécopie (CCITT G3/G4) : on le glisse dans une enveloppe
    TIFF minimale, que la bibliothèque d'image sait décoder."""
    Image, _ = _pil()
    largeur = dico['colonnes'] or dico['largeur']
    hauteur = dico['lignes'] or dico['hauteur']
    compression = 4 if dico['k'] < 0 else 3
    options = (1 if dico['k'] > 0 else 0) | (4 if dico['aligne'] else 0)
    entrees = [
        (256, 4, 1, largeur), (257, 4, 1, hauteur), (258, 3, 1, 1), (259, 3, 1, compression),
        (262, 3, 1, 0), (266, 3, 1, 1), (273, 4, 1, 0), (277, 3, 1, 1), (278, 4, 1, hauteur),
        (279, 4, 1, len(donnees)), (292 if compression == 3 else 293, 4, 1, options),
    ]
    debut_donnees = 8 + 2 + 12 * len(entrees) + 4
    tiff = bytearray(b'II' + struct.pack('<HI', 42, 8) + struct.pack('<H', len(entrees)))
    for etiquette, genre, compte, valeur in entrees:
        if etiquette == 273:
            valeur = debut_donnees
        if genre == 3:
            tiff += struct.pack('<HHIHH', etiquette, genre, compte, valeur, 0)
        else:
            tiff += struct.pack('<HHII', etiquette, genre, compte, valeur)
    tiff += struct.pack('<I', 0) + donnees
    try:
        image = Image.open(io.BytesIO(bytes(tiff)))
        image.load()
    except Exception as err:
        raise ErreurPlan('Une image de télécopie (CCITT) du PDF ne se décode pas : %s' % err)
    # Dans un flux de télécopie, le papier est une suite de « blancs » : c'est
    # ainsi qu'on le rend. BlackIs1 dit qu'à l'écran le PDF montre l'inverse.
    if dico['noir_vaut_1']:
        image = _pil()[1].invert(image.convert('L'))
    return image


# ---------------------------------------------------------------------------
#  Les boîtes : les rectangles fermés tracés à l'encre
# ---------------------------------------------------------------------------
def boites_de(gris, cote_mini):
    """Les rectangles fermés de l'image, en pixels, coin haut gauche.

    On ne garde que les traits droits (une ouverture morphologique efface les
    lettres et les courbes), on ressoude les coupures d'un trait scanné, puis
    on cherche les **trous** du dessin : l'intérieur d'une boîte en est un,
    et il est rectangulaire. Un fil qui arrive sur la boîte ne la change pas.
    """
    cv2, np = _cv2(), _np()
    long = max(3, int(round(cote_mini)))
    bloc = max(15, (int(round(cote_mini)) * 2) | 1)
    encre = cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, bloc, 12)
    horizontaux = cv2.morphologyEx(encre, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (long, 1)))
    verticaux = cv2.morphologyEx(encre, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, long)))
    traits = cv2.dilate(cv2.bitwise_or(horizontaux, verticaux), np.ones((3, 3), dtype='uint8'))
    contours, hierarchie = cv2.findContours(traits, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    boites = []
    if hierarchie is None:
        return boites
    for rang, contour in enumerate(contours):
        if hierarchie[0][rang][3] == -1:
            continue                                   # un bord extérieur : pas l'intérieur d'une boîte
        x, y, largeur, hauteur = cv2.boundingRect(contour)
        if largeur < cote_mini or hauteur < cote_mini:
            continue
        if cv2.contourArea(contour) < 0.85 * largeur * hauteur:
            continue                                   # un trou qui n'est pas un rectangle
        boites.append({'x': float(x), 'y': float(y), 'largeur': float(largeur), 'hauteur': float(hauteur)})
    return boites


# ---------------------------------------------------------------------------
#  Les moteurs de lecture : chacun rend, par image, des mots placés
# ---------------------------------------------------------------------------
def moteur_rapidocr():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise ErreurPlan(
            'RapidOCR n\'est pas installé : pip install rapidocr-onnxruntime (un paquet Python '
            'ordinaire, sans exécutable ; il fonctionne ensuite hors ligne).')
    ocr = RapidOCR()

    def lire(images):
        sorties = []
        for image in images:
            mots = []
            if image.size and min(image.shape[:2]) >= 8:
                lignes, _ = ocr(image)
                for quadrilatere, texte, score in (lignes or []):
                    xs = [p[0] for p in quadrilatere]
                    ys = [p[1] for p in quadrilatere]
                    mots += decouper_ligne({'texte': texte, 'x': min(xs), 'y': min(ys),
                                            'largeur': max(xs) - min(xs), 'hauteur': max(ys) - min(ys),
                                            'confiance': float(score)})
            sorties.append(mots)
        return sorties
    return lire


def decouper_ligne(ligne):
    """Un moteur qui rend des lignes entières : on les coupe en mots, chacun à
    la place que sa longueur lui donne."""
    texte = ligne['texte']
    if ' ' not in texte.strip():
        return [ligne]
    mots = []
    total = max(1, len(texte))
    pos = 0
    for mot in re.finditer(r'\S+', texte):
        debut, fin = mot.start(), mot.end()
        mots.append({'texte': mot.group(0),
                     'x': ligne['x'] + ligne['largeur'] * debut / total, 'y': ligne['y'],
                     'largeur': ligne['largeur'] * (fin - debut) / total, 'hauteur': ligne['hauteur'],
                     'confiance': ligne.get('confiance', 1.0)})
        pos = fin
    return mots


def moteur_windows(commande=None, script=SCRIPT_WINDOWS, delai=900):
    """Le moteur intégré à Windows, par PowerShell. `commande` remplace
    l'appel à PowerShell (la batterie s'en sert)."""
    if commande is None and os.name != 'nt':
        raise ErreurPlan('Le moteur de lecture intégré à Windows n\'existe que sous Windows.')
    Image, _ = _pil()

    def lire(images):
        with tempfile.TemporaryDirectory(prefix='suivi-fwd-ocr-') as dossier:
            noms = []
            for rang, image in enumerate(images):
                nom = 'morceau-%04d.png' % rang
                Image.fromarray(image).save(os.path.join(dossier, nom))
                noms.append(nom)
            ordre = list(commande) if commande else ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                                     '-File', str(script)]
            try:
                fini = subprocess.run(ordre + [dossier], capture_output=True, timeout=delai)
            except FileNotFoundError:
                raise ErreurPlan('PowerShell est introuvable : le moteur de lecture intégré à Windows '
                                 'passe par lui (powershell.exe, celui de Windows).')
            except subprocess.TimeoutExpired:
                raise ErreurPlan('Le moteur de lecture intégré à Windows n\'a pas répondu en %d s.' % delai)
            if fini.returncode != 0:
                raise ErreurPlan('Le moteur de lecture intégré à Windows a échoué : %s'
                                 % fini.stderr.decode('utf-8', 'replace').strip()[:400])
            return mots_du_json(fini.stdout, noms)
    return lire


def mots_du_json(brut, noms):
    """Ce que ocr_windows.ps1 écrit, remis dans l'ordre des images."""
    try:
        texte = brut.decode('utf-8-sig')
        donnees = json.loads(texte) if texte.strip() else []
    except (UnicodeDecodeError, ValueError):
        raise ErreurPlan('Le moteur de lecture intégré à Windows a rendu autre chose que du JSON : %s'
                         % brut[:120])
    if isinstance(donnees, dict):
        donnees = [donnees]
    par_nom = {}
    for entree in donnees:
        chemin = str(entree.get('chemin', ''))
        mots = entree.get('mots') or []
        if isinstance(mots, dict):
            mots = [mots]
        par_nom[re.split(r'[\\/]', chemin)[-1]] = [        # un chemin Windows, même lu ailleurs
            {'texte': str(m.get('texte', '')), 'x': float(m.get('x', 0)), 'y': float(m.get('y', 0)),
             'largeur': float(m.get('largeur', 0)), 'hauteur': float(m.get('hauteur', 0)),
             'confiance': float(m.get('confiance', 1.0))}
            for m in mots if str(m.get('texte', '')).strip()]
    return [par_nom.get(nom, []) for nom in noms]


def choisir_moteur(nom='auto'):
    if callable(nom):
        return nom
    if nom == 'rapidocr':
        return moteur_rapidocr()
    if nom == 'windows':
        return moteur_windows()
    if nom == 'auto':
        try:
            return moteur_rapidocr()
        except ErreurPlan:
            pass
        if os.name == 'nt':
            return moteur_windows()
        raise ErreurPlan(
            'Aucun moteur de lecture : installez RapidOCR (pip install rapidocr-onnxruntime — un '
            'paquet Python ordinaire, hors ligne ensuite), ou lancez sous Windows, dont le moteur '
            'intégré suffit.')
    raise ErreurPlan('Moteur inconnu : %s (rapidocr, windows ou auto).' % nom)


# ---------------------------------------------------------------------------
#  Lire la page : la page entière par tuiles, puis chaque boîte agrandie
# ---------------------------------------------------------------------------
def mots_de(gris, lecteur, boites, marge, page_entiere=True):
    cv2 = _cv2()
    hauteur_page, largeur_page = gris.shape[:2]
    demandes = []
    for b in boites:
        x0, y0 = max(0, int(b['x'] - marge)), max(0, int(b['y'] - marge))
        x1 = min(largeur_page, int(b['x'] + b['largeur'] + marge))
        y1 = min(hauteur_page, int(b['y'] + b['hauteur'] + marge))
        morceau = gris[y0:y1, x0:x1]
        petit = min(b['largeur'], b['hauteur'])
        echelle = 3 if petit < 60 else (2 if petit < 120 else 1)
        if echelle > 1:
            morceau = cv2.resize(morceau, None, fx=echelle, fy=echelle, interpolation=cv2.INTER_CUBIC)
        demandes.append((morceau, x0, y0, echelle))
    if page_entiere:
        pas = TUILE - CHEVAUCHEMENT
        y0 = 0
        while True:
            x0 = 0
            while True:
                demandes.append((gris[y0:y0 + TUILE, x0:x0 + TUILE], x0, y0, 1))
                if x0 + TUILE >= largeur_page:
                    break
                x0 += pas
            if y0 + TUILE >= hauteur_page:
                break
            y0 += pas
    lectures = lecteur([d[0] for d in demandes])
    mots = []
    for (morceau, dx, dy, echelle), lus in zip(demandes, lectures):
        for m in lus:
            mots.append({'texte': m['texte'], 'x': dx + m['x'] / echelle, 'y': dy + m['y'] / echelle,
                         'largeur': m['largeur'] / echelle, 'hauteur': m['hauteur'] / echelle,
                         'confiance': float(m.get('confiance', 1.0))})
    return dedoublonner(mots)


def recouvrement(a, b):
    """La part commune de deux mots, rapportée au plus petit."""
    x0, y0 = max(a['x'], b['x']), max(a['y'], b['y'])
    x1 = min(a['x'] + a['largeur'], b['x'] + b['largeur'])
    y1 = min(a['y'] + a['hauteur'], b['y'] + b['hauteur'])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    petit = min(a['largeur'] * a['hauteur'], b['largeur'] * b['hauteur'])
    return (x1 - x0) * (y1 - y0) / petit if petit > 0 else 0.0


def dedoublonner(mots):
    """Un mot lu deux fois — par une tuile et par une boîte agrandie — ne
    compte qu'une fois : on garde la lecture la plus sûre, la boîte agrandie
    à égalité."""
    gardes = []
    for m in sorted(mots, key=lambda m: -round(m['confiance'], 2)):
        if any(recouvrement(m, g) > 0.5 for g in gardes):
            continue
        gardes.append(m)
    return gardes


def recoller(mots, repere=REPERE):
    """« 18 AB » lu en deux mots : recollés quand, ensemble, ils font un
    repère et que séparés ils n'en font pas."""
    from composants import interpreter
    restants = list(mots)
    recolles = []
    utilises = set()
    for i, a in enumerate(restants):
        if i in utilises or interpreter(a['texte'], repere)[0] != 'non':
            continue
        for j, b in enumerate(restants):
            if j == i or j in utilises or interpreter(b['texte'], repere)[0] != 'non':
                continue
            meme_ligne = min(a['y'] + a['hauteur'], b['y'] + b['hauteur']) - max(a['y'], b['y']) > 0.5 * min(a['hauteur'], b['hauteur'])
            ecart = b['x'] - (a['x'] + a['largeur'])
            if meme_ligne and -0.2 * a['hauteur'] <= ecart <= 0.8 * max(a['hauteur'], 1):
                if interpreter(a['texte'] + b['texte'], repere)[0] != 'non':
                    recolles.append({'texte': a['texte'] + b['texte'], 'x': a['x'], 'y': min(a['y'], b['y']),
                                     'largeur': b['x'] + b['largeur'] - a['x'],
                                     'hauteur': max(a['y'] + a['hauteur'], b['y'] + b['hauteur']) - min(a['y'], b['y']),
                                     'confiance': min(a['confiance'], b['confiance'])})
                    utilises.update((i, j))
                    break
    return [m for i, m in enumerate(restants) if i not in utilises] + recolles


def lire_image(gris, lecteur, repere=REPERE, connus=None, cote_mini=None, distance_maxi=None,
               confiance_mini=CONFIANCE_MINI, page_entiere=True):
    """Une image : ses boîtes, ses mots, ses composants — en pixels, y vers le bas."""
    hauteur, largeur = gris.shape[:2]
    cote = cote_mini or max(12.0, largeur / 200.0)
    distance = distance_maxi or largeur / 40.0
    boites = boites_de(gris, cote)
    mots = recoller(mots_de(gris, lecteur, boites, distance, page_entiere), repere)
    centres = [dict(m, x=m['x'] + m['largeur'] / 2, y=m['y'] + m['hauteur'] / 2) for m in mots]
    textes = interpreter_mots(centres, repere, connus, confiance_mini)
    # La règle commune compte y vers le haut (comme un PDF) et trie du haut
    # vers le bas ; l'image compte y vers le bas. On retourne, puis on remet.
    for t in textes:
        t['y'] = hauteur - t['y']
    rects = [{'x': b['x'], 'y': hauteur - (b['y'] + b['hauteur']), 'largeur': b['largeur'], 'hauteur': b['hauteur']}
             for b in boites]
    r = composants(textes, rects, repere, cote, distance)
    for c in r['trouves']:
        c['y'] = hauteur - (c['y'] + c['hauteur'])
    for d in r['douteux']:
        d['rect'] = dict(d['rect'], y=hauteur - (d['rect']['y'] + d['rect']['hauteur']))
    for t in r['orphelins'] + r['incertains']:
        t['y'] = hauteur - t['y']
    r['mots'] = len(mots)
    r['boites'] = len(boites)
    r['part_verticale'] = part_verticale(mots)
    return r


def part_verticale(mots):
    """La part des mots lus plus hauts que larges : sur une page couchée,
    c'est la majorité — et c'est le signe qu'il faut la tourner."""
    longs = [m for m in mots if len(m['texte'].strip()) >= 3 and m['largeur'] > 0]
    if not longs:
        return 0.0
    return sum(1 for m in longs if m['hauteur'] > 1.2 * m['largeur']) / float(len(longs))


def tourner(gris, angle):
    np = _np()
    return gris if angle == 0 else np.ascontiguousarray(np.rot90(gris, k=angle // 90))


def lire(chemin, repere=REPERE, connus=None, moteur='auto', cote_mini=None, distance_maxi=None,
         confiance_mini=CONFIANCE_MINI, page_entiere=True, orientations=ORIENTATIONS, controle=None):
    """Le scan, de bout en bout, page après page. Lève ErreurPlan quand il
    n'est pas lisible.

    Une page qui ne livre presque rien est réessayée tournée d'un quart de
    tour, puis de l'autre, puis retournée : un scan couché se lit quand même.
    """
    pages = images_de(chemin)
    lecteur = choisir_moteur(moteur)
    resultat = {'trouves': [], 'douteux': [], 'orphelins': [], 'incertains': [],
                'boites': 0, 'mots': 0, 'pages': len(pages), 'rotations': [], 'controles': []}
    for numero, gris in pages:
        # La page telle quelle d'abord. On ne la tourne que si elle semble
        # couchée — des mots plus hauts que larges — ou si presque rien n'en
        # sort ; et on garde l'orientation qui livre le plus.
        essais = []
        for angle in orientations:
            image = tourner(gris, angle)
            r = lire_image(image, lecteur, repere, connus, cote_mini, distance_maxi, confiance_mini, page_entiere)
            r['rotation'], r['image'] = angle, image
            essais.append(r)
            if not essais[0]['boites'] and _score(essais[0]) == 0:
                break                                  # une page blanche : inutile de la tourner
            if angle == orientations[0] and r['part_verticale'] < 0.5 and _score(r) >= 2:
                break                                  # elle est droite et livre : on la garde
            if angle != orientations[0] and r['part_verticale'] < 0.5 and _score(r) >= 2 and not r['douteux']:
                break                                  # tournée, propre : c'est la bonne
        meilleur = max(essais, key=lambda r: (len(r['trouves']), -len(r['douteux']), -r['part_verticale']))
        image_gardee = meilleur.pop('image')
        for cle in ('trouves', 'douteux', 'orphelins', 'incertains'):
            for element in meilleur[cle]:
                element['page'] = numero
            resultat[cle] += meilleur[cle]
        resultat['boites'] += meilleur['boites']
        resultat['cadres'] = resultat.get('cadres', 0) + meilleur.get('cadres', 0)
        resultat['mots'] += meilleur['mots']
        resultat['rotations'].append(meilleur['rotation'])
        resultat['resume'] = '%d mot(s) lu(s)' % resultat['mots']
        if controle:
            nom = '%s-p%d-controle.png' % (pathlib.Path(chemin).stem, numero)
            sortie = pathlib.Path(controle) / nom
            _pil()[0].fromarray(image_de_controle(image_gardee, meilleur)).save(str(sortie))
            resultat['controles'].append(str(sortie))
    return resultat


def _score(r):
    return len(r['trouves']) + len(r['orphelins'])


# ---------------------------------------------------------------------------
#  L'image de contrôle : ce qu'on a vu, dessiné sur le scan
# ---------------------------------------------------------------------------
def image_de_controle(gris, r):
    """Le scan, avec en vert les composants sûrs, en orange les boîtes à
    regarder, en rouge les repères sans boîte : une relecture d'un coup d'œil."""
    cv2 = _cv2()
    couleur = cv2.cvtColor(gris, cv2.COLOR_GRAY2BGR)
    largeur = gris.shape[1]
    epaisseur = max(2, largeur // 1200)
    taille = max(0.5, largeur / 2500.0)

    def rect(b, teinte):
        cv2.rectangle(couleur, (int(b['x']), int(b['y'])),
                      (int(b['x'] + b['largeur']), int(b['y'] + b['hauteur'])), teinte, epaisseur)

    def mot(texte, x, y, teinte):
        cv2.putText(couleur, texte, (int(x), max(12, int(y) - 4)), cv2.FONT_HERSHEY_SIMPLEX, taille, teinte,
                    max(1, epaisseur - 1), cv2.LINE_AA)
    VERT, ORANGE, ROUGE, VIOLET = (0, 150, 0), (0, 140, 255), (0, 0, 220), (200, 0, 160)
    for c in r['trouves']:
        rect(c, VERT)
        mot(c['repere'] + (' (lu %s)' % c['lu'] if c.get('lu') else ''), c['x'], c['y'], VERT)
    for d in r['douteux']:
        rect(d['rect'], ORANGE)
        mot('? ' + d['pourquoi'], d['rect']['x'], d['rect']['y'], ORANGE)
    for t in r['orphelins']:
        cv2.circle(couleur, (int(t['x']), int(t['y'])), int(max(8, t.get('hauteur', 16))), ROUGE, epaisseur)
        mot(t['texte'] + ' sans boite', t['x'], t['y'] - t.get('hauteur', 16), ROUGE)
    for t in r['incertains']:
        cv2.circle(couleur, (int(t['x']), int(t['y'])), int(max(8, t.get('hauteur', 16))), VIOLET, epaisseur)
        mot(t['texte'] + ' ?', t['x'], t['y'] - t.get('hauteur', 16), VIOLET)
    return couleur


# ---------------------------------------------------------------------------
def main(argv=None):
    parseur = argparse.ArgumentParser(description='Retire les composants d\'un plan ELEC scanné (image ou PDF).')
    parseur.add_argument('plan', help='l\'image (PNG, JPEG, TIFF) ou le PDF scanné')
    parseur.add_argument('--csv', help='écrire ce qui a été vu dans ce fichier')
    parseur.add_argument('--connus', help='les repères que la base attend (CSV plan;repère, ou un par ligne)')
    parseur.add_argument('--plan-nom', help='le nom du plan dans la liste des connus (sinon : le nom du fichier)')
    parseur.add_argument('--repere', help='l\'expression qui reconnaît un repère électrique')
    parseur.add_argument('--moteur', default='auto', choices=['auto', 'rapidocr', 'windows'])
    parseur.add_argument('--controle', help='écrire dans ce dossier une image de contrôle par page')
    parseur.add_argument('--cote-mini', type=float, help='côté minimal d\'une boîte, en pixels')
    parseur.add_argument('--distance-maxi', type=float, help='distance maximale d\'un repère à sa boîte, en pixels')
    parseur.add_argument('--confiance-mini', type=float, default=CONFIANCE_MINI)
    parseur.add_argument('--sans-page-entiere', action='store_true', help='ne lire que les boîtes')
    parseur.add_argument('--sans-rotation', action='store_true', help='ne pas essayer la page tournée')
    args = parseur.parse_args(argv)
    try:
        motif = re.compile(args.repere) if args.repere else REPERE
        nom = pathlib.Path(args.plan).name
        connus = lire_connus(args.connus) if args.connus else None
        attendus = attendus_pour(connus, args.plan_nom or pathlib.Path(args.plan).stem) if connus else None
        resultat = lire(args.plan, motif, attendus, args.moteur, args.cote_mini, args.distance_maxi,
                        args.confiance_mini, not args.sans_page_entiere,
                        (0,) if args.sans_rotation else ORIENTATIONS, args.controle)
        corr = correspondance(resultat, attendus) if attendus is not None else None
        print(raconter(resultat, nom, corr))
        for c in resultat['controles']:
            print('  → image de contrôle : %s' % c)
        if args.csv:
            ecrire_csv(args.csv, lignes_csv(resultat, nom, corr))
            print('  → %s' % args.csv)
        return 0
    except ErreurPlan as err:
        print('Arrêt : %s' % err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

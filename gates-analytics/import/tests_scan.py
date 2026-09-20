#!/usr/bin/env python3
"""
Batterie du lecteur de scans : elle dessine de vraies images — boîtes,
repères dedans ou à côté, fils, cadre, bruit de scan — les enfouit dans des
PDF comme un scanner le fait (JPEG, télécopie CCITT, brut compressé), puis
vérifie que le lecteur retrouve les composants attendus et dit ce dont il
n'est pas sûr.

    python3 import/tests_scan.py

Il faut numpy, pillow et opencv-python-headless. La reconnaissance de
caractères est jouée avec RapidOCR quand il est là ; sinon ces
vérifications-là sont passées en le disant, sans échouer. Le moteur intégré
à Windows est joué avec un faux PowerShell, pour vérifier le dialogue.
"""

import io
import json
import os
import pathlib
import shutil
import struct
import sys
import tempfile
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lire_scan as ls                                             # noqa: E402
from composants import ErreurPlan                                  # noqa: E402

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


def _leve(fonction, *args, **params):
    try:
        fonction(*args, **params)
    except ErreurPlan as err:
        return bool(str(err).strip())
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
#  Dessiner un plan
# ---------------------------------------------------------------------------
def police(taille):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=taille)
    except TypeError:
        for chemin in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/arial.ttf'):
            if os.path.exists(chemin):
                return ImageFont.truetype(chemin, taille)
        return ImageFont.load_default()


REPERES = ['18AB', '120PA3', '7XY', '19CD', '31AB2', '4PB']


def dessiner(boites=None, textes=(), traits=(), cadre=True, largeur=1600, hauteur=1100, taille=22, bruit=False):
    """Une image de plan : des boîtes (x, y, l, h, texte dedans), des textes
    libres (x, y, texte), des traits (x0, y0, x1, y1)."""
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np
    image = Image.new('L', (largeur, hauteur), 255)
    d = ImageDraw.Draw(image)
    grande, petite = police(taille), police(int(taille * 0.7))
    if boites is None:
        boites = []
        for i, r in enumerate(REPERES):
            x, y = 120 + (i % 3) * 450, 150 + (i // 3) * 400
            boites.append((x, y, 180, 90, r + '\nPN-%04d' % (1000 + i)))
            traits = list(traits) + [(x + 180, y + 45, x + 300, y + 45)]
    for x, y, l, h, texte in boites:
        d.rectangle([x, y, x + l, y + h], outline=0, width=2)
        for rang, ligne in enumerate(texte.split('\n')):
            d.text((x + 10, y + 10 + rang * int(taille * 1.8)), ligne, fill=0, font=grande if rang == 0 else petite)
    for x, y, texte in textes:
        d.text((x, y), texte, fill=0, font=grande)
    for x0, y0, x1, y1 in traits:
        d.line([x0, y0, x1, y1], fill=0, width=2)
    if cadre:
        d.rectangle([20, 20, largeur - 20, hauteur - 20], outline=0, width=3)
        d.text((60, 50), 'TFE2130A600001A  Schema de principe', fill=0, font=petite)
    if bruit:
        tableau = np.asarray(image, dtype='float32')
        aleatoire = np.random.RandomState(7)
        tableau = tableau * 0.92 + aleatoire.normal(0, 9, tableau.shape)         # papier gris, grain
        poussieres = aleatoire.rand(*tableau.shape) < 0.0015
        tableau[poussieres] = 40
        image = Image.fromarray(np.clip(tableau, 0, 255).astype('uint8')).filter(ImageFilter.GaussianBlur(0.6))
    return image


# ---------------------------------------------------------------------------
#  Enfouir une image dans un PDF, comme un scanner
# ---------------------------------------------------------------------------
def pdf_image(largeur, hauteur, dico, donnees, autres_objets=()):
    """Un PDF d'une page portant cette image (et d'autres objets s'il le faut)."""
    objets = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Contents 4 0 R /Resources << /XObject << /Im0 5 0 R >> >> >>',
        b'<< /Length 35 >>\nstream\nq 842 0 0 595 0 0 cm /Im0 Do Q\nendstream',
        (b'<< /Type /XObject /Subtype /Image /Width %d /Height %d %s /Length %d >>\nstream\n'
         % (largeur, hauteur, dico, len(donnees))) + donnees + b'\nendstream',
    ] + list(autres_objets)
    sortie = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    positions = []
    for rang, corps in enumerate(objets, 1):
        positions.append(len(sortie))
        sortie += str(rang).encode('ascii') + b' 0 obj\n' + corps + b'\nendobj\n'
    debut_xref = len(sortie)
    sortie += b'xref\n0 ' + str(len(objets) + 1).encode('ascii') + b'\n0000000000 65535 f \n'
    for p in positions:
        sortie += ('%010d 00000 n \n' % p).encode('ascii')
    sortie += (b'trailer\n<< /Size ' + str(len(objets) + 1).encode('ascii') +
               b' /Root 1 0 R >>\nstartxref\n' + str(debut_xref).encode('ascii') + b'\n%%EOF\n')
    return bytes(sortie)


def jpeg(image, qualite=90):
    tampon = io.BytesIO()
    image.save(tampon, 'JPEG', quality=qualite)
    return tampon.getvalue()


def lignes_png(image):
    """Les lignes filtrées « à la PNG » d'une image, telles qu'un PDF les
    porte sous /Predictor 15 : on les sort d'un vrai PNG."""
    tampon = io.BytesIO()
    image.save(tampon, 'PNG')
    donnees = tampon.getvalue()
    pos, idat = 8, b''
    while pos < len(donnees):
        longueur, nom = struct.unpack('>I4s', donnees[pos:pos + 8])
        if nom == b'IDAT':
            idat += donnees[pos + 8:pos + 8 + longueur]
        pos += 12 + longueur
    return zlib.decompress(idat)


def bande_ccitt(image):
    """Le flux CCITT G4 d'une image noir et blanc, tel qu'un télécopieur
    l'écrit : le papier en « blancs »."""
    from PIL import Image, ImageOps
    # Pillow code les 1 comme des « noirs » de télécopie : on inverse avant,
    # pour que le papier soit bien la suite de blancs qu'un scanner produit.
    inversee = ImageOps.invert(image.convert('L')).convert('1')
    tampon = io.BytesIO()
    inversee.save(tampon, 'TIFF', compression='group4', tiffinfo={278: image.height})
    donnees = tampon.getvalue()
    tiff = Image.open(io.BytesIO(donnees))
    debut, longueur = tiff.tag_v2[273][0], tiff.tag_v2[279][0]
    return donnees[debut:debut + longueur]


def egales(a, b, tolerance=0):
    import numpy as np
    a, b = np.asarray(a.convert('L'), dtype='int16'), np.asarray(b.convert('L'), dtype='int16')
    return a.shape == b.shape and float(abs(a - b).mean()) <= tolerance


def main():
    try:
        import numpy   # noqa: F401
        import cv2     # noqa: F401
        from PIL import Image
    except ImportError as err:
        print('Batterie non jouée : il manque %s (pip install numpy pillow opencv-python-headless).' % err.name)
        return 0
    import numpy as np
    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-scan-'))
    try:
        plan = dessiner(textes=[(650, 700, '91AA')])
        plan.save(str(atelier / 'plan.png'))
        gris = np.asarray(plan)

        section('Les boîtes se trouvent sans lire une lettre')
        boites = ls.boites_de(gris, 12)
        boites_sans_cadre = [b for b in boites if b['largeur'] < 1000]
        verifier('les six boîtes sont trouvées, plus le cadre', len(boites_sans_cadre) == 6 and len(boites) == 7, len(boites))
        premiere = sorted(boites_sans_cadre, key=lambda b: (b['y'], b['x']))[0]
        verifier('chacune à sa place, à quelques pixels près (l\'intérieur du trait)',
                 abs(premiere['x'] - 120) <= 4 and abs(premiere['y'] - 150) <= 4 and
                 abs(premiere['largeur'] - 180) <= 6 and abs(premiere['hauteur'] - 90) <= 6, premiere)
        verifier('un fil qui arrive sur la boîte ne l\'abîme pas (elles ont toutes un fil)', len(boites_sans_cadre) == 6)
        coupee = dessiner(boites=[(100, 100, 200, 100, ''), (500, 100, 200, 100, '')], cadre=False)
        from PIL import ImageDraw
        ImageDraw.Draw(coupee).rectangle([150, 96, 170, 104], fill=255)      # un trou de 20 px dans le trait du haut
        trouvees = ls.boites_de(np.asarray(coupee), 12)
        verifier('une boîte dont le trait est coupé n\'est pas une boîte : rien n\'est deviné',
                 len(trouvees) == 1 and abs(trouvees[0]['x'] - 500) <= 4, trouvees)
        texte_seul = dessiner(boites=[], textes=[(100, 100, '18AB'), (300, 100, 'Boîtier de jonction')], cadre=False)
        verifier('du texte seul ne fait aucune boîte', ls.boites_de(np.asarray(texte_seul), 12) == [])
        bruite = dessiner(bruit=True)
        verifier('sur un papier gris et grenu, avec des poussières, les boîtes tiennent',
                 len([b for b in ls.boites_de(np.asarray(bruite), 12) if b['largeur'] < 1000]) == 6)

        section('L\'image sort du PDF, quel que soit l\'emballage du scanner')
        petit = plan.resize((400, 275))
        p_jpeg = atelier / 'jpeg.pdf'
        p_jpeg.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode', jpeg(petit)))
        images = ls.images_du_pdf(p_jpeg.read_bytes())
        verifier('une image JPEG (le cas le plus courant)', len(images) == 1 and egales(images[0], petit, 3), len(images))
        p_flate = atelier / 'flate.pdf'
        p_flate.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode', zlib.compress(petit.tobytes())))
        images = ls.images_du_pdf(p_flate.read_bytes())
        verifier('des pixels bruts compressés, en gris', len(images) == 1 and egales(images[0], petit))
        rvb = petit.convert('RGB')
        p_rvb = atelier / 'rvb.pdf'
        p_rvb.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode', zlib.compress(rvb.tobytes())))
        verifier('… ou en couleurs', egales(ls.images_du_pdf(p_rvb.read_bytes())[0], petit, 1))
        p_png = atelier / 'png.pdf'
        p_png.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode '
                                    b'/DecodeParms << /Predictor 15 /Colors 1 /BitsPerComponent 8 /Columns 400 >>',
                                    zlib.compress(lignes_png(petit))))
        verifier('des lignes filtrées à la PNG (prédicteur 15)', egales(ls.images_du_pdf(p_png.read_bytes())[0], petit))
        noir_blanc = petit.convert('1')
        p_bits = atelier / 'bits.pdf'
        p_bits.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 1', noir_blanc.tobytes()))
        verifier('un bit par pixel, nu', egales(ls.images_du_pdf(p_bits.read_bytes())[0], noir_blanc))
        inverses = bytes(b ^ 0xFF for b in noir_blanc.tobytes())
        p_inv = atelier / 'inverse.pdf'
        p_inv.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 1 /Decode [1 0]', inverses))
        verifier('… et retourné par /Decode [1 0]', egales(ls.images_du_pdf(p_inv.read_bytes())[0], noir_blanc))
        p_masque = atelier / 'masque.pdf'
        p_masque.write_bytes(pdf_image(400, 275, b'/ImageMask true', noir_blanc.tobytes()))
        verifier('un masque d\'image (les télécopies l\'emploient)', egales(ls.images_du_pdf(p_masque.read_bytes())[0], noir_blanc))
        bande = bande_ccitt(noir_blanc)
        p_fax = atelier / 'fax.pdf'
        p_fax.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 1 /Filter /CCITTFaxDecode '
                                    b'/DecodeParms << /K -1 /Columns 400 /Rows 275 >>', bande))
        verifier('une télécopie CCITT G4 — le noir et blanc des scanners de bureau', egales(ls.images_du_pdf(p_fax.read_bytes())[0], noir_blanc))
        p_fax1 = atelier / 'fax-noir1.pdf'
        p_fax1.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 1 /Filter /CCITTFaxDecode '
                                     b'/DecodeParms << /K -1 /Columns 400 /Rows 275 /BlackIs1 true >> /Decode [1 0]', bande))
        verifier('… avec BlackIs1 et /Decode [1 0], qui s\'annulent', egales(ls.images_du_pdf(p_fax1.read_bytes())[0], noir_blanc))
        hexa = ('>'.encode('ascii'))
        p_chaine = atelier / 'chaine.pdf'
        p_chaine.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter [/ASCIIHexDecode /FlateDecode]',
                                       zlib.compress(petit.tobytes()).hex().encode('ascii') + hexa))
        verifier('deux filtres empilés (ASCIIHex puis Flate)', egales(ls.images_du_pdf(p_chaine.read_bytes())[0], petit))
        logo = b'<< /Type /XObject /Subtype /Image /Width 32 /Height 32 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1024 >>\nstream\n' + b'\x80' * 1024 + b'\nendstream'
        masque = b'<< /Type /XObject /Subtype /Image /Width 400 /Height 275 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 110000 >>\nstream\n' + b'\xff' * 110000 + b'\nendstream'
        p_deux = atelier / 'deux.pdf'
        p_deux.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode /SMask 7 0 R', jpeg(petit),
                                     autres_objets=[logo, masque]))
        verifier('un logo minuscule et un masque de transparence ne sont pas des pages', len(ls.images_du_pdf(p_deux.read_bytes())) == 1)
        p_jbig = atelier / 'jbig2.pdf'
        p_jbig.write_bytes(pdf_image(400, 275, b'/ColorSpace /DeviceGray /BitsPerComponent 1 /Filter /JBIG2Decode', b'\0' * 100))
        try:
            ls.images_du_pdf(p_jbig.read_bytes())
            message = ''
        except ErreurPlan as err:
            message = str(err)
        verifier('une image JBIG2 est refusée en disant quoi faire', 'JBIG2' in message and 'Rescanner' in message, message)
        codes = [256, 45, 258, 258, 65, 259, 66, 257]
        bits = ''.join(format(c, '09b') for c in codes)
        bits += '0' * (-len(bits) % 8)
        paquet = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
        verifier('le LZW des vieux PDF se décode (l\'exemple de la norme)',
                 ls.decoder_lzw(paquet) == bytes([45, 45, 45, 45, 45, 65, 45, 45, 45, 66]))
        verifier('et le RunLength', ls.decoder_rle(bytes([2, 65, 66, 67, 254, 68, 128])) == b'ABCDDD')
        tiff = atelier / 'deux-pages.tif'
        dessiner(boites=[(100, 100, 200, 100, '18AB')], cadre=False, largeur=600, hauteur=400).save(
            str(tiff), save_all=True, append_images=[dessiner(boites=[(100, 100, 200, 100, '19CD')], cadre=False, largeur=600, hauteur=400)])
        verifier('un TIFF à deux pages fait deux images', [n for n, _ in ls.images_de(tiff)] == [1, 2])

        section('Le moteur intégré à Windows, par un faux PowerShell')
        faux = atelier / 'faux_ocr.py'
        faux.write_text('''import json, os, sys
from PIL import Image
dossier = sys.argv[-1]
if os.environ.get('FAUX_OCR') == 'panne':
    sys.stderr.write('Aucune langue de reconnaissance installee.'); sys.exit(2)
if os.environ.get('FAUX_OCR') == 'charabia':
    print('pas du json'); sys.exit(0)
sortie = []
for nom in sorted(os.listdir(dossier)):
    l, h = Image.open(os.path.join(dossier, nom)).size
    sortie.append({'chemin': nom, 'mots': [{'texte': '18AB', 'x': l / 2 - 20, 'y': h / 2 - 8, 'largeur': 40, 'hauteur': 16}]})
sys.stdout.write(json.dumps(sortie))
''', encoding='utf-8')
        commande = [sys.executable, str(faux)]
        une = np.asarray(dessiner(boites=[(100, 100, 200, 100, '')], cadre=False, largeur=600, hauteur=400))
        r = ls.lire_image(une, ls.moteur_windows(commande=commande), page_entiere=False)
        verifier('les mots rendus par PowerShell reviennent à leur place dans la page, et font un composant',
                 [c['repere'] for c in r['trouves']] == ['18AB'] and abs(r['trouves'][0]['x'] - 100) <= 4, r)
        os.environ['FAUX_OCR'] = 'panne'
        verifier('un moteur qui échoue rend son message, en français',
                 _leve(ls.moteur_windows(commande=commande), [une]))
        os.environ['FAUX_OCR'] = 'charabia'
        verifier('un moteur qui rend autre chose que du JSON est une erreur claire',
                 _leve(ls.moteur_windows(commande=commande), [une]))
        os.environ.pop('FAUX_OCR', None)
        verifier('PowerShell introuvable est une erreur claire', _leve(ls.moteur_windows(commande=['programme-qui-nexiste-pas']), [une]))
        mots = ls.mots_du_json(b'\xef\xbb\xbf' + json.dumps({'chemin': 'C:\\temp\\morceau-0000.png', 'mots': {'texte': '7XY', 'x': 1, 'y': 2, 'largeur': 3, 'hauteur': 4}}).encode('utf-8'),
                               ['morceau-0000.png', 'morceau-0001.png'])
        verifier('un seul résultat, un seul mot (PowerShell les désenveloppe) et un BOM : lus quand même',
                 mots[0][0]['texte'] == '7XY' and mots[0][0]['confiance'] == 1.0 and mots[1] == [], mots)
        if os.name != 'nt':
            verifier('hors Windows, le moteur intégré dit qu\'il n\'existe pas', _leve(ls.moteur_windows))

        section('Ce que le lecteur refuse franchement')
        verifier('un fichier introuvable le dit', _leve(ls.lire, atelier / 'nulle-part.png', moteur=lambda images: [[] for _ in images]))
        texte = atelier / 'texte.txt'
        texte.write_text('pas une image')
        verifier('un fichier qui n\'est ni image ni PDF le dit', _leve(ls.images_de, texte))
        sans_image = atelier / 'vecteur.pdf'
        sans_image.write_bytes(b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n')
        try:
            ls.images_de(sans_image)
            message = ''
        except ErreurPlan as err:
            message = str(err)
        verifier('un PDF sans image renvoie vers le lecteur de dessins', 'lire_plan' in message, message)
        verifier('un moteur inconnu le dit', _leve(ls.choisir_moteur, 'tesseract'))

        try:
            import rapidocr_onnxruntime   # noqa: F401
            moteur = 'rapidocr'
        except ImportError:
            moteur = None
        if not moteur:
            print('\nRapidOCR n\'est pas installé : la lecture des caractères n\'est pas jouée (ce n\'est pas un échec).')
        else:
            section('Lire les repères, pour de vrai (RapidOCR)')
            controle = atelier / 'controle'
            controle.mkdir()
            r = ls.lire(atelier / 'plan.png', moteur=moteur, controle=controle)
            reperes = sorted(c['repere'] for c in r['trouves'])
            verifier('les six repères sont lus, chacun dans sa boîte', reperes == sorted(REPERES), reperes)
            verifier('le part number reste attaché à son composant',
                     all(any(t.startswith('PN-') for t in c['textes']) for c in r['trouves']), [c['textes'] for c in r['trouves']])
            verifier('le repère qui traîne hors de toute boîte est signalé, pas inventé ; le cadre est ignoré',
                     [t['texte'] for t in r['orphelins']] == ['91AA'] and r['cadres'] == 1 and not r['douteux'], (r['orphelins'], r['douteux']))
            verifier('la page n\'a pas eu besoin d\'être tournée', r['rotations'] == [0])
            verifier('l\'image de contrôle est écrite à côté',
                     len(r['controles']) == 1 and pathlib.Path(r['controles'][0]).stat().st_size > 1000, r['controles'])
            compte_rendu = ls.raconter(r, 'plan.png')
            verifier('le compte rendu dit les mots lus, les boîtes, les composants',
                     'mot(s) lu(s)' in compte_rendu and '6 composant(s) sûr(s)' in compte_rendu, compte_rendu)

            cote = dessiner(boites=[(200, 200, 180, 90, ''), (700, 200, 180, 90, '')],
                            textes=[(210, 300, '19CD'), (720, 600, '20EF')], cadre=False)
            cote.save(str(atelier / 'cote.png'))
            r = ls.lire(atelier / 'cote.png', moteur=moteur)
            verifier('un repère écrit juste sous sa boîte lui est rattaché ; loin, il est orphelin',
                     [c['repere'] for c in r['trouves']] == ['19CD'] and [t['texte'] for t in r['orphelins']] == ['20EF'], r)
            deux = dessiner(boites=[(200, 200, 260, 90, '18AB    19CD')], cadre=False)
            deux.save(str(atelier / 'deux.png'))
            r = ls.lire(atelier / 'deux.png', moteur=moteur)
            verifier('deux repères dans une boîte : signalé, rien d\'inventé',
                     not r['trouves'] and any(d['pourquoi'] == 'plusieurs repères dans la même boîte' for d in r['douteux']), r)

            lecteur = ls.moteur_rapidocr()

            def truque(images):
                """Un moteur qui lit comme un scanner fatigué : un l pour un 1, un B pour un 8."""
                sorties = lecteur(images)
                for mots in sorties:
                    for m in mots:
                        m['texte'] = m['texte'].replace('18AB', 'l8AB').replace('19CD', '1BAB' if False else '19CD').replace('7XY', '7XY')
                        if m['texte'] == '4PB':
                            m['texte'] = '4P8'
                return sorties
            r = ls.lire(atelier / 'plan.png', moteur=truque)
            par = {c['repere']: c for c in r['trouves']}
            verifier('une lettre confondue est corrigée quand une seule forme est possible, et la lecture brute est gardée',
                     '18AB' in par and par['18AB'].get('lu') == 'l8AB', par.get('18AB'))
            verifier('une confusion qui fait quand même un repère n\'est pas changée sans la base : 4P8 reste 4P8',
                     '4P8' in par and '4PB' not in par, sorted(par))
            r = ls.lire(atelier / 'plan.png', moteur=truque, connus=set(REPERES))
            par = {c['repere']: c for c in r['trouves']}
            verifier('… et avec la liste de la base, 4P8 devient 4PB, corrigé et dit',
                     '4PB' in par and par['4PB'].get('lu') == '4P8' and 'l8AB → 18AB' in ls.raconter(r) and '4P8 → 4PB' in ls.raconter(r),
                     ls.raconter(r))
            from composants import correspondance
            c = correspondance(r, set(REPERES) | {'99ZZ'})
            verifier('la correspondance avec la base dit ce qui manque sur le plan',
                     c['absents'] == ['99ZZ'] and c['en_plus'] == [] and len(c['communs']) == 6, c)

            tournee = plan.rotate(90, expand=True)
            tournee.save(str(atelier / 'tournee.png'))
            r = ls.lire(atelier / 'tournee.png', moteur=moteur)
            verifier('un scan couché est lu quand même, en tournant la page',
                     sorted(c['repere'] for c in r['trouves']) == sorted(REPERES) and r['rotations'][0] in (90, 270), (r['rotations'], len(r['trouves'])))

            r = ls.lire(tiff, moteur=moteur)
            verifier('deux pages, un composant chacune, chacun sait sa page',
                     sorted((c['repere'], c['page']) for c in r['trouves']) == [('18AB', 1), ('19CD', 2)], r['trouves'])

            bruite.save(str(atelier / 'bruite.png'))
            r = ls.lire(atelier / 'bruite.png', moteur=moteur)
            verifier('sur le papier gris et grenu, les six repères sont lus',
                     sorted(c['repere'] for c in r['trouves']) == sorted(REPERES), sorted(c['repere'] for c in r['trouves']))

            scan = atelier / 'scan.pdf'
            scan.write_bytes(pdf_image(plan.width, plan.height, b'/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode', jpeg(plan, 85)))
            r = ls.lire(scan, moteur=moteur)
            verifier('un PDF scanné en JPEG, de bout en bout', sorted(c['repere'] for c in r['trouves']) == sorted(REPERES))
            fax = atelier / 'fax-plan.pdf'
            nb = plan.convert('1')
            fax.write_bytes(pdf_image(plan.width, plan.height, b'/ColorSpace /DeviceGray /BitsPerComponent 1 /Filter /CCITTFaxDecode '
                                      b'/DecodeParms << /K -1 /Columns %d /Rows %d >>' % (plan.width, plan.height), bande_ccitt(nb)))
            r = ls.lire(fax, moteur=moteur)
            verifier('un PDF de télécopie (CCITT), de bout en bout', sorted(c['repere'] for c in r['trouves']) == sorted(REPERES))

            sortie = atelier / 'sortie.csv'
            code = ls.main([str(atelier / 'plan.png'), '--csv', str(sortie), '--connus', str(_liste(atelier)), '--controle', str(controle)])
            contenu = sortie.read_text(encoding='utf-8-sig')
            verifier('la ligne de commande lit, compare, écrit le CSV et l\'image de contrôle',
                     code == 0 and '18AB;sûr' in contenu and '91AA;orphelin' in contenu and 'attendu, absent du plan' in contenu,
                     contenu[:200])
    finally:
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


def _liste(atelier):
    liste = atelier / 'attendus.txt'
    liste.write_text('\n'.join(REPERES + ['99ZZ']), encoding='utf-8')
    return liste


if __name__ == '__main__':
    sys.exit(main())

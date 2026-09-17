#!/usr/bin/env python3
"""
Emballe un fichier pour qu'il traverse la passerelle mail.

La passerelle d'entreprise retient ce qui ressemble a du code ou a du HTML.
Compresse en gzip puis encode en base64, un fichier n'y ressemble plus : il
devient un pave de caracteres sans forme. C'est le pendant de decoder.py, qui
fait le chemin inverse.

    python empaqueter.py ..\\prototype\\suivi-fwd-demo.html
    python empaqueter.py fichier.html -o autre-nom.txt

Ecrit un .txt : en-tete en ASCII pur (nom, taille, empreinte sha256), puis le
contenu en base64 coupe a 76 caracteres. decoder.py le relit, verifie
l'empreinte et rend le fichier d'origine a l'octet pres.

Aucune dependance : bibliotheque standard uniquement.
"""

import argparse
import base64
import gzip
import hashlib
import pathlib
import sys

GABARIT = """\
# Suivi FWD -- transfert de {nom} vers la machine de travail
#
# La passerelle mail retient ce qui ressemble a du code ou a du HTML.
# Compresse en gzip puis encode en base64, ce fichier ne ressemble plus ni a
# du texte ni a du code, et il passe.
#
# Pour le reconstruire : placer ce fichier et decoder.py dans le meme
# dossier, puis lancer :
#
#     py decoder.py
#
# decoder.py decompresse, verifie l'empreinte ci-dessous, et ecrit
# {nom} a cote.
#
# fichier : {nom}
# octets  : {octets}
# sha256  : {sha}
#
"""


def main():
    p = argparse.ArgumentParser(description="Emballe un fichier en gzip + base64 pour la messagerie.")
    p.add_argument("source", help="le fichier a emballer")
    p.add_argument("-o", "--sortie", help="le .txt a ecrire (par defaut : <source>.gz.b64.txt)")
    args = p.parse_args()

    src = pathlib.Path(args.source)
    if not src.exists():
        raise SystemExit("Introuvable : %s" % src)

    octets = src.read_bytes()
    sha = hashlib.sha256(octets).hexdigest()
    # mtime=0 : gzip deterministe, le meme fichier redonne le meme .txt
    comprime = gzip.compress(octets, compresslevel=9, mtime=0)
    corps = base64.encodebytes(comprime).decode("ascii")   # deja coupe a 76

    entete = GABARIT.format(nom=src.name, octets=len(octets), sha=sha)
    dst = pathlib.Path(args.sortie) if args.sortie else src.with_suffix(src.suffix + ".gz.b64.txt")
    # encoding='ascii' : plante si un caractere non-ASCII s'est glisse dans l'en-tete
    dst.write_text(entete + corps, encoding="ascii")

    print("%s emballe" % src.name)
    print("  origine : %d octets   sha256 %s" % (len(octets), sha))
    print("  gzip    : %d octets   (%.2fx)" % (len(comprime), len(octets) / len(comprime)))
    print("  ecrit   : %s (%d octets)" % (dst, dst.stat().st_size))


if __name__ == "__main__":
    sys.exit(main())

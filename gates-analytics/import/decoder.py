#!/usr/bin/env python3
"""
Reconstruit Javascript.html a partir de son .txt de transfert.

Javascript.html (~130 Ko) est retenu par la passerelle mail d'entreprise :
elle y reconnait du JavaScript (document., .innerHTML, addEventListener...).
Compresse en gzip puis encode en base64, il ne ressemble plus ni a du texte
ni a du code, et il traverse. Ce script fait le chemin inverse : il relit le
.txt, decompresse, verifie l'empreinte sha256 du fichier d'origine, puis
reecrit Javascript.html a cote du .txt.

Poser ce script et le .txt dans le meme dossier, puis, au choix :

    py decoder.py                         (le .txt est trouve tout seul)
    py decoder.py Javascript.html.gz.b64.txt   (nom donne explicitement)

Aucune dependance : bibliotheque standard uniquement.
"""

import base64
import gzip
import hashlib
import pathlib
import sys
import zlib

# Alphabet base64 standard, padding compris. Sert a distinguer les lignes de
# donnees des lignes d'en-tete (qui commencent par '#').
ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


def ressemble_transfert(chemin):
    """Vrai si le .txt porte notre en-tete (ligne '# sha256')."""
    try:
        tete = chemin.read_text(encoding="ascii", errors="ignore")[:4096].lower()
    except OSError:
        return False
    return "sha256" in tete


def trouver_txt():
    """
    Sans argument : cherche le .txt de transfert a cote du script, puis dans
    le dossier courant. Un seul candidat -> il est pris ; plusieurs -> on
    prefere celui qui porte notre en-tete.
    """
    dossiers = []
    ici = pathlib.Path(__file__).resolve().parent
    dossiers.append(ici)
    courant = pathlib.Path.cwd()
    if courant != ici:
        dossiers.append(courant)

    vus = []
    for d in dossiers:
        for p in sorted(d.glob("*.txt")):
            if p not in vus:
                vus.append(p)

    if not vus:
        raise SystemExit(
            "Aucun fichier .txt a cote de decoder.py.\n"
            "Placez le .txt de transfert dans le meme dossier, puis relancez : py decoder.py"
        )
    if len(vus) == 1:
        return vus[0]

    marques = [p for p in vus if ressemble_transfert(p)]
    if len(marques) == 1:
        return marques[0]

    liste = "\n  ".join(p.name for p in vus)
    raise SystemExit(
        "Plusieurs .txt trouves, precisez lequel :\n  %s\n"
        "    py decoder.py <nom-du-fichier.txt>" % liste
    )


def lire(chemin):
    """Separe l'en-tete du corps base64 et recupere sha256 + nom de sortie."""
    sha_attendu = None
    nom_sortie = "Javascript.html"
    corps = []
    for ligne in chemin.read_text(encoding="ascii").splitlines():
        nu = ligne.strip()
        if not nu:
            continue
        if nu.startswith("#"):
            cle = nu.lstrip("# ").lower()
            if cle.startswith("sha256"):
                sha_attendu = nu.split(":", 1)[1].strip().lower()
            elif cle.startswith("fichier"):
                nom_sortie = nu.split(":", 1)[1].strip()
            continue
        if set(nu) <= ALPHABET:
            corps.append(nu)
    if not corps:
        raise SystemExit(
            "%s ne contient pas de donnees base64.\n"
            "Est-ce bien le .txt de transfert (et pas decoder.py renomme) ?" % chemin.name
        )
    return "".join(corps), sha_attendu, nom_sortie


def main():
    if len(sys.argv) > 2:
        raise SystemExit("Usage : py decoder.py [fichier.txt]")

    if len(sys.argv) == 2:
        txt = pathlib.Path(sys.argv[1])
        if not txt.exists():
            raise SystemExit("Introuvable : %s" % txt)
    else:
        txt = trouver_txt()
        print("Fichier trouve : %s" % txt.name)
    txt = txt.resolve()

    b64, sha_attendu, nom_sortie = lire(txt)
    try:
        donnees = gzip.decompress(base64.b64decode(b64))
    except (ValueError, OSError, EOFError, zlib.error) as e:
        raise SystemExit("Decodage impossible (%s) : le .txt est peut-etre tronque ou altere." % e)

    sha_obtenu = hashlib.sha256(donnees).hexdigest()
    if sha_attendu and sha_obtenu != sha_attendu:
        raise SystemExit(
            "Empreinte differente : le fichier reconstruit ne correspond pas.\n"
            "  attendu : %s\n  obtenu  : %s\n"
            "Le .txt est arrive altere. Le renvoyer par mail sans le modifier." % (sha_attendu, sha_obtenu)
        )

    sortie = txt.parent / nom_sortie
    sortie.write_bytes(donnees)
    print("%s reconstruit (%d octets)" % (sortie.name, len(donnees)))
    print("  sha256 %s : %s" % ("verifie" if sha_attendu else "non fourni", sha_obtenu))
    print("  ecrit : %s" % sortie)


if __name__ == "__main__":
    sys.exit(main())

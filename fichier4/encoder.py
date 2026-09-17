#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
encoder.py — Fichier 4 : encodeur gzip + base64 (GB64)
======================================================

Transforme n'importe quel fichier en texte portable : compression gzip
puis encodage base64, dans un conteneur « .gb64 » auto-décrit (nom,
taille, SHA-256). Peut découper la sortie en plusieurs parties de taille
bornée pour contourner les limites de collage / d'envoi (c'est le point
qui bloquait : un flux base64 trop long).

Le résultat se relit avec decoder.py (base64 -> octets -> gunzip).
Aucune dépendance externe : bibliothèque standard Python 3 uniquement.

Exemples
--------
    # Encode un fichier -> mesdonnees.csv.gb64
    python3 encoder.py mesdonnees.csv

    # Sortie vers un chemin précis
    python3 encoder.py data.csv -o data.gb64

    # Découpe en parties de 2 Mo max (part-001, part-002, ...)
    python3 encoder.py gros.csv --chunk-bytes 2M

    # Le fichier est déjà compressé (.gz) : on n'ajoute pas de gzip
    python3 encoder.py archive.csv.gz --no-gzip

    # Affiche le conteneur sur la sortie standard (petit fichier)
    python3 encoder.py petit.txt --stdout
"""

import argparse
import base64
import gzip
import hashlib
import os
import sys

MARKER = "GB64 v1"


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def parse_size(text):
    """Convertit « 2M », « 500k », « 1048576 » en octets."""
    text = str(text).strip().lower()
    if not text:
        raise ValueError("taille vide")
    mult = 1
    if text[-1] in "kmg":
        mult = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}[text[-1]]
        text = text[:-1]
    if text.endswith("b"):
        text = text[:-1]
    value = float(text)
    return int(value * mult)


def sanitize_name(name):
    """
    Neutralise les caractères de contrôle (dont \\n et \\r) dans le nom
    stocké : ils casseraient le format ligne par ligne de l'en-tête.
    Les noms ordinaires (y compris accentués) ne sont pas modifiés.
    """
    out = []
    for ch in name:
        if ch in ("\r", "\n") or ord(ch) < 0x20 or ch == "\x7f":
            out.append("_")
        else:
            out.append(ch)
    return "".join(out)


def wrap_b64(data, width):
    """Encode en base64 et coupe en lignes de largeur fixe."""
    b64 = base64.b64encode(data).decode("ascii")
    if width and width > 0:
        return "\n".join(b64[i:i + width] for i in range(0, len(b64), width))
    return b64


def build_header(name, size, sha, gzip_flag, parts, part, psize, psha):
    lines = [
        MARKER,
        "name=%s" % name,
        "size=%d" % size,
        "sha256=%s" % sha,
        "gzip=%d" % (1 if gzip_flag else 0),
        "parts=%d" % parts,
        "part=%d" % part,
        "psize=%d" % psize,
        "psha256=%s" % psha,
        "",  # ligne vide -> fin de l'en-tête
    ]
    return "\n".join(lines)


def emit(container_text, out_path, use_stdout):
    """Écrit le conteneur (UTF-8, cohérent avec la lecture du décodeur)."""
    if use_stdout:
        sys.stdout.write(container_text)
        if not container_text.endswith("\n"):
            sys.stdout.write("\n")
        return
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(container_text)
        if not container_text.endswith("\n"):
            fh.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="encoder.py",
        description="Encode un fichier en conteneur(s) gzip+base64 (GB64).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    parser.add_argument("file", help="fichier à encoder")
    parser.add_argument("-o", "--output", metavar="CHEMIN",
                        help="chemin de sortie (par défaut : <fichier>.gb64). "
                             "Pour les parties, sert de préfixe.")
    parser.add_argument("--chunk-bytes", metavar="N",
                        help="découpe le flux compressé en parties de N octets "
                             "max (ex : 2M, 500k). Sans cette option : un seul "
                             "fichier.")
    parser.add_argument("--no-gzip", action="store_true",
                        help="n'applique pas gzip (fichier déjà compressé)")
    parser.add_argument("--level", type=int, default=9, metavar="0-9",
                        help="niveau de compression gzip (défaut : 9)")
    parser.add_argument("--width", type=int, default=76, metavar="N",
                        help="largeur des lignes base64 (défaut : 76 ; 0 = une "
                             "seule ligne)")
    parser.add_argument("--stdout", action="store_true",
                        help="écrit le conteneur sur stdout (incompatible avec "
                             "le découpage)")
    parser.add_argument("-f", "--force", action="store_true",
                        help="écrase les fichiers de sortie existants")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="réduit les messages")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.file):
        eprint("Erreur : fichier introuvable : %s" % args.file)
        return 2

    if args.stdout and args.chunk_bytes:
        eprint("Erreur : --stdout est incompatible avec --chunk-bytes.")
        return 2

    try:
        with open(args.file, "rb") as fh:
            original = fh.read()
    except OSError as exc:
        eprint("Erreur de lecture : %s" % exc)
        return 2

    orig_size = len(original)
    orig_sha = sha256_hex(original)
    name = sanitize_name(os.path.basename(args.file))

    do_gzip = not args.no_gzip
    if do_gzip:
        level = max(0, min(9, args.level))
        payload = gzip.compress(original, compresslevel=level)
    else:
        payload = original

    # taille des tranches
    if args.chunk_bytes:
        try:
            chunk = parse_size(args.chunk_bytes)
        except ValueError as exc:
            eprint("Erreur : --chunk-bytes invalide : %s" % exc)
            return 2
        if chunk <= 0:
            eprint("Erreur : --chunk-bytes doit être > 0")
            return 2
    else:
        chunk = len(payload) if payload else 1

    # tranches d'octets du flux (compressé ou non)
    if len(payload) == 0:
        slices = [b""]
    else:
        slices = [payload[i:i + chunk] for i in range(0, len(payload), chunk)]
    parts_total = len(slices)

    base_out = args.output or (args.file + ".gb64")

    # calcule d'abord tous les chemins, vérifie l'absence de collision AVANT
    # d'écrire quoi que ce soit
    plans = []
    for idx, chunk_bytes in enumerate(slices, start=1):
        if args.stdout:
            out_path = None
        elif parts_total == 1:
            out_path = base_out
        else:
            root = base_out[:-len(".gb64")] if base_out.endswith(".gb64") \
                else base_out
            out_path = "%s.part-%03d.gb64" % (root, idx)
        plans.append((idx, chunk_bytes, out_path))

    if not args.stdout and not args.force:
        for _, _, out_path in plans:
            if out_path and os.path.exists(out_path):
                eprint("Erreur : le fichier existe déjà : %s (utiliser --force)"
                       % out_path)
                return 2

    written = []
    for idx, chunk_bytes, out_path in plans:
        header = build_header(
            name=name, size=orig_size, sha=orig_sha, gzip_flag=do_gzip,
            parts=parts_total, part=idx,
            psize=len(chunk_bytes), psha=sha256_hex(chunk_bytes))
        container = header + "\n" + wrap_b64(chunk_bytes, args.width) + "\n"
        try:
            emit(container, out_path, args.stdout)
        except OSError as exc:
            eprint("Erreur d'écriture (%s) : %s" % (out_path, exc))
            return 2
        if not args.stdout:
            written.append(out_path)

    if not args.quiet and not args.stdout:
        pct = (100.0 * len(payload) / orig_size) if orig_size else 100.0
        eprint("Source    : %s (%d octets, sha256=%s...)"
               % (name, orig_size, orig_sha[:16]))
        eprint("Compressé : %d octets (gzip=%s, taille = %.1f%% de l'original)"
               % (len(payload), "oui" if do_gzip else "non", pct))
        eprint("Parties   : %d" % parts_total)
        for w in written:
            eprint("  écrit : %s (%d octets)" % (w, os.path.getsize(w)))
        if parts_total == 1:
            eprint("Décoder avec : python3 decoder.py %s" % written[0])
        else:
            root = base_out[:-len(".gb64")] if base_out.endswith(".gb64") \
                else base_out
            eprint("Décoder avec : python3 decoder.py %s.part-*.gb64" % root)

    return 0


if __name__ == "__main__":
    sys.exit(main())

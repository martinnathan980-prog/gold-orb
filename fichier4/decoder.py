#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decoder.py — Fichier 4 : décodeur gzip + base64 (GB64)
======================================================

Reconstruit le fichier binaire d'origine à partir d'un ou plusieurs
conteneurs texte « .gb64 » produits par encoder.py (format GB64 v1),
ou à partir de base64 brut (sans en-tête).

Aucune dépendance externe : bibliothèque standard Python 3 uniquement
(base64, gzip, hashlib, argparse...). Fonctionne avec Python >= 3.6.

Idée générale
-------------
Un gros fichier binaire est difficile à coller ou à transporter dans une
conversation ou un canal texte. On le compresse (gzip) puis on l'encode en
texte (base64), éventuellement découpé en plusieurs parties. Ce script fait
le chemin inverse : base64 -> octets -> gunzip -> fichier d'origine, avec
vérification d'intégrité (taille + SHA-256).

Exemples
--------
    # Un seul fichier .gb64 -> écrit le fichier d'origine à côté
    python3 decoder.py mesdonnees.csv.gb64

    # Plusieurs parties (reconstruction automatique dans l'ordre)
    python3 decoder.py sortie.part-*.gb64

    # Un dossier entier de .gb64 (regroupés par nom d'origine)
    python3 decoder.py --input-dir ./bundle -o ./restaure

    # Sortie vers un chemin précis
    python3 decoder.py data.gb64 -o /tmp/data.csv.gz

    # Lire depuis l'entrée standard
    cat data.gb64 | python3 decoder.py -

    # Afficher seulement les métadonnées, sans décoder
    python3 decoder.py --info data.gb64
"""

import argparse
import base64
import binascii
import glob
import gzip
import hashlib
import os
import sys

MAGIC = "GB64"          # marqueur de première ligne d'en-tête
GZIP_MAGIC = b"\x1f\x8b"  # signature d'un flux gzip


# --------------------------------------------------------------------------- #
# Utilitaires                                                                  #
# --------------------------------------------------------------------------- #
def eprint(*args, **kwargs):
    """Écrit sur stderr (les messages ne polluent pas la sortie de données)."""
    print(*args, file=sys.stderr, **kwargs)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def safe_basename(name):
    """
    Empêche toute traversée de répertoire : on ne garde que le nom de base.
    Un conteneur malveillant ne peut donc pas écrire hors du dossier voulu.
    """
    if not name:
        return ""
    name = name.replace("\\", "/")
    name = os.path.basename(name)
    # neutralise quelques cas dégénérés
    if name in (".", "..", ""):
        return ""
    return name


def b64decode_lenient(text):
    """
    Décode du base64 en tolérant les espaces, retours à la ligne, et un
    éventuel rembourrage manquant. Accepte aussi le base64 « URL-safe ».
    """
    # retire tout ce qui n'est pas un caractère base64 significatif
    cleaned = "".join(text.split())
    if not cleaned:
        return b""
    # supporte l'alphabet URL-safe éventuel
    cleaned = cleaned.replace("-", "+").replace("_", "/")
    # rétablit le rembourrage '=' si nécessaire
    missing = (-len(cleaned)) % 4
    cleaned += "=" * missing
    try:
        return base64.b64decode(cleaned, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("base64 invalide : %s" % exc)


# --------------------------------------------------------------------------- #
# Analyse d'un conteneur GB64                                                  #
# --------------------------------------------------------------------------- #
class Part(object):
    """Une partie décodée d'un fichier (index, octets bruts, métadonnées)."""

    def __init__(self, header, raw, source):
        self.header = header          # dict des clés d'en-tête
        self.raw = raw                # octets après décodage base64
        self.source = source          # nom du fichier source (info)

    @property
    def name(self):
        return self.header.get("name", "")

    @property
    def part_index(self):
        try:
            return int(self.header.get("part", "1"))
        except (TypeError, ValueError):
            return 1

    @property
    def parts_total(self):
        try:
            return int(self.header.get("parts", "1"))
        except (TypeError, ValueError):
            return 1


def parse_container(text, source="<?>"):
    """
    Sépare l'en-tête (lignes « clé=valeur » jusqu'à la première ligne vide)
    du corps base64, puis décode le corps. Tolère l'absence d'en-tête
    (base64 brut) et les lignes de commentaire commençant par '#'.
    """
    lines = text.splitlines()

    header = {}
    body_start = 0
    saw_header = False

    # Détecte un en-tête : soit la première ligne commence par le marqueur,
    # soit on trouve des lignes « clé=valeur » avant une ligne vide.
    i = 0
    n = len(lines)

    # Ligne marqueur optionnelle : "GB64 v1"
    if n > 0 and lines[0].strip().upper().startswith(MAGIC):
        header["_marker"] = lines[0].strip()
        saw_header = True
        i = 1

    # Lignes d'en-tête clé=valeur jusqu'à une ligne vide
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped == "":
            # fin de l'en-tête
            i += 1
            body_start = i
            break
        if stripped.startswith("#"):
            i += 1
            continue
        if "=" in stripped and _looks_like_header_key(stripped.split("=", 1)[0]):
            key, value = stripped.split("=", 1)
            header[key.strip()] = value.strip()
            saw_header = True
            i += 1
            continue
        # première ligne qui ne ressemble pas à un en-tête -> début du corps
        body_start = i
        break
    else:
        # on a consommé toutes les lignes comme en-tête (pas de corps)
        body_start = n

    if not saw_header:
        # aucun en-tête reconnu : tout le contenu est du base64 brut
        body_start = 0

    body = "\n".join(lines[body_start:])
    raw = b64decode_lenient(body)
    return Part(header, raw, source)


def _looks_like_header_key(token):
    token = token.strip()
    if not token or len(token) > 40:
        return False
    return all(c.isalnum() or c in "-_" for c in token)


# --------------------------------------------------------------------------- #
# Reconstruction d'un fichier à partir de ses parties                         #
# --------------------------------------------------------------------------- #
def reassemble(parts):
    """
    Trie les parties par index, vérifie la cohérence, concatène les octets
    bruts, décompresse (gzip) si nécessaire, puis vérifie l'intégrité.
    Retourne (octets_d_origine, en_tête_de_référence).
    """
    if not parts:
        raise ValueError("aucune partie à reconstruire")

    parts = sorted(parts, key=lambda p: p.part_index)
    ref = parts[0].header

    total = parts[0].parts_total
    # cohérence du nombre de parties déclaré
    declared_totals = set(p.parts_total for p in parts)
    if len(declared_totals) > 1:
        eprint("Attention : nombre total de parties incohérent entre les "
               "fichiers : %s" % sorted(declared_totals))
        total = max(declared_totals)

    if total != len(parts):
        eprint("Attention : %d partie(s) fournie(s) mais %d attendue(s)."
               % (len(parts), total))

    seen = {}
    for p in parts:
        idx = p.part_index
        if idx in seen:
            raise ValueError("partie %d en double (%s et %s)"
                             % (idx, seen[idx].source, p.source))
        seen[idx] = p

    if len(parts) > 1:
        expected = list(range(1, len(parts) + 1))
        got = sorted(seen.keys())
        if got != expected:
            raise ValueError("indices de parties non contigus : attendu %s, "
                             "obtenu %s" % (expected, got))

    # vérifie l'intégrité de chaque partie (psize / psha256) si fournie
    for p in parts:
        psize = p.header.get("psize")
        if psize is not None:
            try:
                if int(psize) != len(p.raw):
                    raise ValueError(
                        "taille de partie %d incohérente : en-tête=%s, "
                        "réel=%d" % (p.part_index, psize, len(p.raw)))
            except ValueError as exc:
                raise ValueError(str(exc))
        psha = p.header.get("psha256")
        if psha:
            actual = sha256_hex(p.raw)
            if actual.lower() != psha.lower():
                raise ValueError(
                    "SHA-256 de la partie %d invalide : en-tête=%s, réel=%s"
                    % (p.part_index, psha, actual))

    payload = b"".join(p.raw for p in parts)

    # décompression gzip
    gzip_flag = ref.get("gzip")
    if gzip_flag is None:
        # auto-détection si l'en-tête ne précise rien
        do_gunzip = payload[:2] == GZIP_MAGIC
    else:
        do_gunzip = str(gzip_flag).strip() in ("1", "true", "yes", "on")

    if do_gunzip:
        try:
            original = gzip.decompress(payload)
        except (OSError, EOFError) as exc:
            raise ValueError("échec de la décompression gzip : %s" % exc)
    else:
        original = payload

    # vérification d'intégrité globale
    size = ref.get("size")
    if size is not None:
        try:
            if int(size) != len(original):
                raise ValueError(
                    "taille finale incohérente : en-tête=%s, réel=%d"
                    % (size, len(original)))
        except ValueError as exc:
            raise ValueError(str(exc))

    sha = ref.get("sha256")
    if sha:
        actual = sha256_hex(original)
        if actual.lower() != sha.lower():
            raise ValueError(
                "SHA-256 final invalide : en-tête=%s, réel=%s (fichier corrompu)"
                % (sha, actual))

    return original, ref


# --------------------------------------------------------------------------- #
# Découverte des entrées                                                       #
# --------------------------------------------------------------------------- #
def collect_inputs(inputs, input_dir):
    """Retourne une liste de chemins de fichiers à lire (hors '-')."""
    paths = []

    if input_dir:
        if not os.path.isdir(input_dir):
            raise ValueError("dossier introuvable : %s" % input_dir)
        for entry in sorted(os.listdir(input_dir)):
            if entry.endswith(".gb64") or ".part-" in entry:
                full = os.path.join(input_dir, entry)
                if os.path.isfile(full):
                    paths.append(full)

    for item in inputs:
        if item == "-":
            paths.append("-")
            continue
        if os.path.isdir(item):
            for entry in sorted(os.listdir(item)):
                full = os.path.join(item, entry)
                if os.path.isfile(full) and (entry.endswith(".gb64")
                                             or ".part-" in entry):
                    paths.append(full)
            continue
        # motif glob (utile si le shell n'a pas développé *)
        if any(ch in item for ch in "*?[") and not os.path.exists(item):
            matched = sorted(glob.glob(item))
            if not matched:
                raise ValueError("aucun fichier ne correspond à : %s" % item)
            paths.extend(matched)
            continue
        paths.append(item)

    # dédoublonnage en conservant l'ordre
    seen = set()
    unique = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def read_text(path):
    if path == "-":
        data = sys.stdin.buffer.read()
        return data.decode("utf-8", errors="replace"), "<stdin>"
    with open(path, "rb") as fh:
        data = fh.read()
    return data.decode("utf-8", errors="replace"), path


# --------------------------------------------------------------------------- #
# Écriture de la sortie                                                        #
# --------------------------------------------------------------------------- #
def output_path_for(ref, group_key, args):
    """Détermine le chemin de sortie pour un groupe reconstruit."""
    if args.output and not os.path.isdir(args.output):
        # -o est un chemin de fichier explicite (uniquement si un seul groupe)
        return args.output

    name = safe_basename(ref.get("name", "")) or safe_basename(group_key) \
        or "sortie.bin"

    out_dir = args.output if (args.output and os.path.isdir(args.output)) \
        else os.getcwd()
    return os.path.join(out_dir, name)


def write_output(data, path, force):
    if os.path.exists(path) and not force:
        raise ValueError("le fichier existe déjà : %s (utiliser --force pour "
                         "écraser)" % path)
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "wb") as fh:
        fh.write(data)


# --------------------------------------------------------------------------- #
# Programme principal                                                          #
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(
        prog="decoder.py",
        description="Décode des conteneurs gzip+base64 (GB64) vers le fichier "
                    "d'origine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    p.add_argument("inputs", nargs="*", metavar="ENTREE",
                   help="fichiers .gb64, motifs glob, dossiers, ou '-' pour "
                        "stdin")
    p.add_argument("--input-dir", metavar="DOSSIER",
                   help="décode tous les .gb64 d'un dossier")
    p.add_argument("-o", "--output", metavar="CHEMIN",
                   help="fichier de sortie (un seul groupe) ou dossier de "
                        "sortie (plusieurs groupes)")
    p.add_argument("--stdout", action="store_true",
                   help="écrit les octets décodés sur la sortie standard")
    p.add_argument("--info", action="store_true",
                   help="affiche seulement les métadonnées, sans décoder")
    p.add_argument("-f", "--force", action="store_true",
                   help="écrase les fichiers de sortie existants")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="réduit les messages")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if not args.inputs and not args.input_dir:
        # aucun argument : lit stdin par défaut
        args.inputs = ["-"]

    try:
        paths = collect_inputs(args.inputs, args.input_dir)
    except ValueError as exc:
        eprint("Erreur : %s" % exc)
        return 2

    if not paths:
        eprint("Erreur : aucune entrée à décoder.")
        return 2

    # lit et analyse chaque conteneur
    parts = []
    for path in paths:
        try:
            text, src = read_text(path)
            part = parse_container(text, source=src)
            parts.append(part)
        except (OSError, ValueError) as exc:
            eprint("Erreur en lisant %s : %s" % (path, exc))
            return 2

    # mode info : affiche les en-têtes et sort
    if args.info:
        for part in parts:
            print("--- %s ---" % part.source)
            if part.header:
                for key in sorted(part.header):
                    print("  %s = %s" % (key, part.header[key]))
            else:
                print("  (aucun en-tête ; base64 brut)")
            print("  octets décodés (cette partie) = %d" % len(part.raw))
        return 0

    # regroupe les parties par fichier d'origine (clé = name, sinon source)
    groups = {}
    order = []
    for part in parts:
        key = part.name or _strip_part_suffix(os.path.basename(part.source))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(part)

    if args.stdout and len(order) > 1:
        eprint("Erreur : --stdout impossible avec plusieurs fichiers "
               "reconstruits (%d groupes)." % len(order))
        return 2

    if args.output and not os.path.isdir(args.output) and len(order) > 1:
        eprint("Erreur : -o doit être un dossier quand plusieurs fichiers "
               "sont reconstruits.")
        return 2

    exit_code = 0
    for key in order:
        try:
            data, ref = reassemble(groups[key])
        except ValueError as exc:
            eprint("Erreur (%s) : %s" % (key, exc))
            exit_code = 1
            continue

        if args.stdout:
            sys.stdout.buffer.write(data)
            continue

        out = output_path_for(ref, key, args)
        try:
            write_output(data, out, args.force)
        except (OSError, ValueError) as exc:
            eprint("Erreur d'écriture (%s) : %s" % (key, exc))
            exit_code = 1
            continue

        if not args.quiet:
            eprint("OK : %s -> %s (%d octets)" % (key, out, len(data)))

    return exit_code


def _strip_part_suffix(name):
    """Retire les suffixes .gb64 et .part-NNN pour déduire un nom logique."""
    for suf in (".gb64",):
        if name.endswith(suf):
            name = name[: -len(suf)]
    # retire un éventuel « .part-001 »
    import re
    name = re.sub(r"\.part-\d+$", "", name)
    return name


if __name__ == "__main__":
    sys.exit(main())

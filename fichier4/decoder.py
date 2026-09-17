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

Un conteneur GB64 commence par la ligne marqueur « GB64 vN ». En l'absence
de ce marqueur, l'entrée entière est traitée comme du base64 brut (décodé,
puis décompressé si les octets commencent par la signature gzip).

Exemples
--------
    # Un seul fichier .gb64 -> écrit le fichier d'origine à côté
    python3 decoder.py mesdonnees.csv.gb64

    # Plusieurs parties (reconstruction automatique dans l'ordre)
    python3 decoder.py sortie.part-*.gb64

    # Un dossier entier de .gb64 (regroupés par nom d'origine)
    python3 decoder.py --input-dir ./bundle -o ./restaure/

    # Sortie vers un chemin précis
    python3 decoder.py data.gb64 -o /tmp/data.csv.gz

    # Lire depuis l'entrée standard
    cat data.gb64 | python3 decoder.py -

    # Afficher seulement les métadonnées, sans décoder
    python3 decoder.py --info data.gb64

    # Borne de sécurité pour des conteneurs non fiables
    python3 decoder.py inconnu.gb64 --max-output-bytes 200M
"""

import argparse
import base64
import binascii
import glob
import gzip
import hashlib
import io
import os
import re
import sys
import zlib

MARKER = "GB64"                # début de la ligne marqueur (« GB64 vN »)
MARKER_RE = re.compile(r"^GB64\s+\S", re.IGNORECASE)  # marqueur = « GB64 » + espace + version
GZIP_MAGIC = b"\x1f\x8b"       # signature d'un flux gzip
KNOWN_KEYS = {"name", "size", "sha256", "gzip", "parts", "part",
              "psize", "psha256"}


# --------------------------------------------------------------------------- #
# Utilitaires                                                                  #
# --------------------------------------------------------------------------- #
def eprint(*args, **kwargs):
    """Écrit sur stderr (les messages ne polluent pas la sortie de données)."""
    print(*args, file=sys.stderr, **kwargs)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def sanitize_display(value):
    """
    Neutralise les caractères de contrôle avant affichage vers un terminal
    (évite l'injection de séquences d'échappement via un en-tête hostile).
    """
    if value is None:
        return ""
    out = []
    for ch in str(value):
        if ch == "\t" or (" " <= ch <= "~") or ch > "\x7f":
            out.append(ch)
        else:
            out.append("\\x%02x" % ord(ch))
    return "".join(out)


def safe_basename(name):
    """
    Empêche toute traversée de répertoire : on ne garde que le nom de base.
    Un conteneur malveillant ne peut donc pas écrire hors du dossier voulu.
    """
    if not name:
        return ""
    name = name.replace("\\", "/")
    name = os.path.basename(name)
    if name in (".", "..", ""):
        return ""
    return name


def b64decode_lenient(text):
    """
    Décode du base64 en tolérant les espaces, retours à la ligne, et un
    éventuel rembourrage manquant. Accepte aussi le base64 « URL-safe ».
    """
    cleaned = "".join(text.split())
    if not cleaned:
        return b""
    cleaned = cleaned.replace("-", "+").replace("_", "/")
    missing = (-len(cleaned)) % 4
    cleaned += "=" * missing
    try:
        return base64.b64decode(cleaned, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("base64 invalide : %s" % exc)


def gunzip_bounded(payload, limit):
    """
    Décompresse un flux gzip en flux, en s'arrêtant si la sortie dépasse
    `limit` octets (None = pas de limite). Protège contre les bombes de
    décompression : on n'alloue jamais au-delà de la borne.
    """
    src = io.BytesIO(payload)
    out = io.BytesIO()
    total = 0
    try:
        with gzip.GzipFile(fileobj=src, mode="rb") as gz:
            while True:
                chunk = gz.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if limit is not None and total > limit:
                    raise ValueError(
                        "la sortie décompressée dépasse la limite de %d octets "
                        "(possible bombe de décompression ; ajuster "
                        "--max-output-bytes)" % limit)
                out.write(chunk)
    except (OSError, EOFError, zlib.error) as exc:
        raise ValueError("échec de la décompression gzip : %s" % exc)
    return out.getvalue()


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
        return _int_field(self.header, "part", default=1, source=self.source)

    @property
    def parts_total(self):
        return _int_field(self.header, "parts", default=1, source=self.source)


def _int_field(header, key, default=None, source="<?>"):
    """Lit une valeur entière d'en-tête, avec message clair si non numérique."""
    raw = header.get(key)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError("champ d'en-tête « %s » non numérique dans %s : %r"
                         % (key, source, raw))


def parse_container(text, source="<?>"):
    """
    Sépare l'en-tête du corps base64, puis décode le corps.

    L'en-tête n'est reconnu QUE si la première ligne non vide est le marqueur
    « GB64 vN ». Dans ce cas, les lignes « clé=valeur » sont lues jusqu'à la
    première ligne vide. Sans marqueur, tout le texte est du base64 brut :
    on ne tente jamais d'interpréter une ligne isolée comme un en-tête (ce
    qui corromprait un base64 finissant par « = » ou commençant par « GB64 »).
    """
    lines = text.splitlines()
    header = {}

    # cherche la première ligne non vide
    first_idx = 0
    while first_idx < len(lines) and lines[first_idx].strip() == "":
        first_idx += 1

    has_marker = (first_idx < len(lines)
                  and MARKER_RE.match(lines[first_idx].strip()))

    if not has_marker:
        # base64 brut : aucun en-tête
        raw = b64decode_lenient(text)
        return Part(header, raw, source)

    header["_marker"] = lines[first_idx].strip()
    i = first_idx + 1
    n = len(lines)
    body_start = n

    while i < n:
        stripped = lines[i].strip()
        if stripped == "":
            body_start = i + 1
            break
        if stripped.startswith("#"):
            i += 1
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
            header[key.strip()] = value.strip()
            i += 1
            continue
        # ligne inattendue dans l'en-tête -> début du corps
        body_start = i
        break

    body = "\n".join(lines[body_start:])
    raw = b64decode_lenient(body)
    return Part(header, raw, source)


# --------------------------------------------------------------------------- #
# Reconstruction d'un fichier à partir de ses parties                         #
# --------------------------------------------------------------------------- #
def reassemble(parts, max_output=None):
    """
    Trie les parties par index, vérifie la cohérence, concatène les octets
    bruts, décompresse (gzip) si nécessaire, puis vérifie l'intégrité.
    Retourne (octets_d_origine, en_tête_de_référence).
    """
    if not parts:
        raise ValueError("aucune partie à reconstruire")

    parts = sorted(parts, key=lambda p: p.part_index)
    ref = parts[0].header

    declared_totals = set(p.parts_total for p in parts)
    if len(declared_totals) > 1:
        raise ValueError("nombre total de parties incohérent entre les "
                         "fichiers : %s" % sorted(declared_totals))
    total = declared_totals.pop()

    # index en double ?
    seen = {}
    for p in parts:
        idx = p.part_index
        if idx in seen:
            raise ValueError("partie %d en double (%s et %s)"
                             % (idx, sanitize_display(seen[idx].source),
                                sanitize_display(p.source)))
        seen[idx] = p

    # nombre de parties fourni == total déclaré ? (sinon reconstruction
    # tronquée -> erreur fatale, pas un simple avertissement)
    if total != len(parts):
        raise ValueError("%d partie(s) fournie(s) mais %d attendue(s) : "
                         "reconstruction incomplète" % (len(parts), total))

    # indices contigus 1..total ?
    expected = list(range(1, total + 1))
    got = sorted(seen.keys())
    if got != expected:
        raise ValueError("indices de parties non contigus : attendu %s, "
                         "obtenu %s" % (expected, got))

    # intégrité de chaque partie (psize / psha256) si fournie
    for p in parts:
        psize = _int_field(p.header, "psize", source=p.source)
        if psize is not None and psize != len(p.raw):
            raise ValueError("taille de partie %d incohérente : en-tête=%d, "
                             "réel=%d" % (p.part_index, psize, len(p.raw)))
        psha = p.header.get("psha256")
        if psha:
            actual = sha256_hex(p.raw)
            if actual.lower() != psha.lower():
                raise ValueError(
                    "SHA-256 de la partie %d invalide : en-tête=%s, réel=%s"
                    % (p.part_index, psha, actual))

    payload = b"".join(p.raw for p in parts)

    # taille d'origine annoncée (sert aussi de borne de décompression)
    size = _int_field(ref, "size", source=parts[0].source)

    # gzip : selon l'en-tête, sinon auto-détection par la signature
    gzip_flag = ref.get("gzip")
    if gzip_flag is None:
        do_gunzip = payload[:2] == GZIP_MAGIC
    else:
        do_gunzip = str(gzip_flag).strip() in ("1", "true", "yes", "on")

    if do_gunzip:
        # borne : la plus petite entre la taille annoncée et --max-output-bytes
        limits = [x for x in (size, max_output) if x is not None]
        limit = min(limits) if limits else None
        original = gunzip_bounded(payload, limit)
    else:
        if max_output is not None and len(payload) > max_output:
            raise ValueError("la sortie dépasse la limite de %d octets"
                             % max_output)
        original = payload

    # vérification d'intégrité globale
    if size is not None and size != len(original):
        raise ValueError("taille finale incohérente : en-tête=%d, réel=%d"
                         % (size, len(original)))

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

    def scan_dir(d):
        found = []
        for entry in sorted(os.listdir(d)):
            full = os.path.join(d, entry)
            if os.path.isfile(full) and (entry.endswith(".gb64")
                                         or ".part-" in entry):
                found.append(full)
        return found

    if input_dir:
        if not os.path.isdir(input_dir):
            raise ValueError("dossier introuvable : %s" % input_dir)
        paths.extend(scan_dir(input_dir))

    for item in inputs:
        if item == "-":
            paths.append("-")
            continue
        if os.path.isdir(item):
            paths.extend(scan_dir(item))
            continue
        if any(ch in item for ch in "*?[") and not os.path.exists(item):
            matched = sorted(glob.glob(item))
            if not matched:
                raise ValueError("aucun fichier ne correspond à : %s" % item)
            paths.extend(matched)
            continue
        paths.append(item)

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
def looks_like_dir(path):
    """-o est-il un dossier ? (existant, ou terminé par un séparateur)"""
    if not path:
        return False
    if os.path.isdir(path):
        return True
    return path.endswith(os.sep) or (os.altsep and path.endswith(os.altsep))


def output_path_for(ref, group_key, out_dir_or_file, as_dir):
    """Détermine le chemin de sortie pour un groupe reconstruit."""
    name = safe_basename(ref.get("name", "")) or safe_basename(group_key) \
        or "sortie.bin"
    if out_dir_or_file and not as_dir:
        return out_dir_or_file  # -o est un fichier explicite (un seul groupe)
    out_dir = out_dir_or_file if as_dir else os.getcwd()
    return os.path.join(out_dir, name)


def write_output(data, path, force):
    if os.path.exists(path) and not force:
        raise ValueError("le fichier existe déjà : %s (utiliser --force pour "
                         "écraser)" % path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


# --------------------------------------------------------------------------- #
# Programme principal                                                          #
# --------------------------------------------------------------------------- #
def parse_size(text):
    """Convertit « 200M », « 500k », « 1048576 » en octets."""
    text = str(text).strip().lower()
    if not text:
        raise ValueError("taille vide")
    mult = 1
    if text[-1] in "kmg":
        mult = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}[text[-1]]
        text = text[:-1]
    if text.endswith("b"):
        text = text[:-1]
    return int(float(text) * mult)


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
                        "sortie (terminer par « / » ou plusieurs groupes)")
    p.add_argument("--stdout", action="store_true",
                   help="écrit les octets décodés sur la sortie standard")
    p.add_argument("--info", action="store_true",
                   help="affiche seulement les métadonnées, sans décoder")
    p.add_argument("--max-output-bytes", metavar="N", default=None,
                   help="borne de sécurité sur la taille décompressée "
                        "(ex : 200M) ; utile pour un conteneur non fiable")
    p.add_argument("-f", "--force", action="store_true",
                   help="écrase les fichiers de sortie existants")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="réduit les messages")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if not args.inputs and not args.input_dir:
        args.inputs = ["-"]  # aucun argument : lit stdin

    max_output = None
    if args.max_output_bytes is not None:
        try:
            max_output = parse_size(args.max_output_bytes)
        except ValueError as exc:
            eprint("Erreur : --max-output-bytes invalide : %s" % exc)
            return 2
        if max_output <= 0:
            max_output = None

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
            parts.append(parse_container(text, source=src))
        except (OSError, ValueError) as exc:
            eprint("Erreur en lisant %s : %s"
                   % (sanitize_display(path), exc))
            return 2

    # mode info : affiche les en-têtes et sort
    if args.info:
        for part in parts:
            print("--- %s ---" % sanitize_display(part.source))
            if part.header:
                for key in sorted(part.header):
                    print("  %s = %s" % (sanitize_display(key),
                                         sanitize_display(part.header[key])))
            else:
                print("  (aucun en-tête ; base64 brut)")
            print("  octets décodés (cette partie) = %d" % len(part.raw))
        return 0

    # regroupe les parties : les fichiers découpés (parts>1) par nom d'origine,
    # les conteneurs mono-partie chacun séparément (pas de fusion abusive).
    groups = {}
    order = []
    try:
        for part in parts:
            if part.parts_total > 1:
                key = "multi:" + (part.name
                                  or _strip_part_suffix(
                                      os.path.basename(part.source)))
            else:
                key = "single:" + part.source
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(part)
    except ValueError as exc:
        eprint("Erreur : %s" % exc)
        return 2

    multiple = len(order) > 1

    if args.stdout and multiple:
        eprint("Erreur : --stdout impossible avec plusieurs fichiers "
               "reconstruits (%d groupes)." % len(order))
        return 2

    as_dir = bool(args.output) and (looks_like_dir(args.output) or multiple)
    if args.output and multiple and not as_dir:
        # plusieurs groupes mais -o ressemble à un fichier -> on le traite en
        # dossier (créé au besoin)
        as_dir = True

    exit_code = 0
    for key in order:
        try:
            data, ref = reassemble(groups[key], max_output=max_output)
        except ValueError as exc:
            eprint("Erreur (%s) : %s"
                   % (sanitize_display(_group_label(key)), exc))
            exit_code = 1
            continue

        if args.stdout:
            sys.stdout.buffer.write(data)
            continue

        out = output_path_for(ref, _group_label(key), args.output, as_dir)
        try:
            write_output(data, out, args.force)
        except (OSError, ValueError) as exc:
            eprint("Erreur d'écriture (%s) : %s"
                   % (sanitize_display(_group_label(key)), exc))
            exit_code = 1
            continue

        if not args.quiet:
            eprint("OK : %s -> %s (%d octets)"
                   % (sanitize_display(_group_label(key)),
                      sanitize_display(out), len(data)))

    return exit_code


def _group_label(key):
    """Nom lisible d'un groupe (retire le préfixe interne multi:/single:)."""
    if key.startswith("multi:"):
        return key[len("multi:"):]
    if key.startswith("single:"):
        return os.path.basename(key[len("single:"):])
    return key


def _strip_part_suffix(name):
    """Retire les suffixes .gb64 et .part-NNN pour déduire un nom logique."""
    if name.endswith(".gb64"):
        name = name[: -len(".gb64")]
    name = re.sub(r"\.part-\d+$", "", name)
    return name


if __name__ == "__main__":
    sys.exit(main())

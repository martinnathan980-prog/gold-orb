"""Extraction de champs depuis des documents (PDF, Word, texte) vers un Excel.

Un fichier de règles YAML décrit les champs à repérer par expression régulière :

    fichiers: "*.pdf"            # motif des fichiers (glob), ou une liste de motifs
    champs:
      Numéro plan: 'N°\\s*plan\\s*:\\s*(\\S+)'
      Titre:
        regex: 'Titre\\s*:\\s*(.+)'
        defaut: "(sans titre)"
      Dates:
        regex: '\\d{2}/\\d{2}/\\d{4}'
        tous: true               # toutes les occurrences, séparées par « ; »

Le résultat est un Excel prêt pour le robot : une ligne par document, colonne
« Fichier » + un champ par colonne + Statut/Message/Horodatage vides.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from . import symboles as S
from .erreurs import ErreurAutoweb
from .excel import creer_classeur

journal = logging.getLogger("autoweb")

EXTENSIONS_TEXTE = (".txt", ".csv", ".md", ".log", ".json", ".xml", ".html", ".htm")


@dataclass
class Champ:
    nom: str
    regex: "re.Pattern[str]"
    groupe: int = 1
    defaut: str = ""
    tous: bool = False
    separateur: str = "; "
    nettoyer: bool = True
    obligatoire: bool = False


@dataclass
class Regles:
    fichiers: List[str]
    champs: List[Champ]
    dossier: Optional[str] = None
    feuille: str = "Suivi"
    colonne_fichier: str = "Fichier"
    sous_dossiers: bool = True
    pages: Optional[str] = None  # ex. "1-2" pour ne lire que les premières pages d'un PDF


@dataclass
class BilanExtraction:
    fichiers: int = 0
    reussis: int = 0
    incomplets: int = 0
    illisibles: int = 0
    sortie: Optional[Path] = None
    details: List[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- lecture
def _pages_selection(pages: Optional[str], nb: int) -> range:
    if not pages:
        return range(nb)
    debut, _, fin = str(pages).partition("-")
    try:
        a = int(debut) if debut else 1
        b = int(fin) if fin else (a if not _ else nb)
    except ValueError:
        raise ErreurAutoweb(f"Sélection de pages invalide : « {pages} » (attendu ex. 1-3).")
    return range(max(0, a - 1), min(nb, b))


def lire_pdf(chemin: Path, pages: Optional[str] = None) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ErreurAutoweb("Le module pypdf est requis pour lire des PDF : pip install pypdf")
    lecteur = PdfReader(str(chemin))
    if lecteur.is_encrypted:
        try:
            lecteur.decrypt("")
        except Exception:
            raise ErreurAutoweb("PDF protégé par mot de passe.")
    morceaux = []
    for i in _pages_selection(pages, len(lecteur.pages)):
        try:
            morceaux.append(lecteur.pages[i].extract_text() or "")
        except Exception as e:  # page abîmée : on continue
            journal.debug("page %d de %s illisible : %s", i + 1, chemin.name, e)
    texte = "\n".join(morceaux)
    if not texte.strip():
        raise ErreurAutoweb(
            "aucun texte trouvé (PDF scanné ? il faudrait une reconnaissance de caractères / OCR)."
        )
    return texte


def lire_docx(chemin: Path) -> str:
    try:
        import docx  # python-docx
    except ImportError:
        raise ErreurAutoweb("Le module python-docx est requis pour lire des .docx : pip install python-docx")
    document = docx.Document(str(chemin))
    morceaux = [p.text for p in document.paragraphs]
    for table in document.tables:
        for rangee in table.rows:
            # une cellule par ligne : les regex « libellé : valeur » restent simples
            morceaux.extend(cellule.text for cellule in rangee.cells)
    for section in document.sections:
        for partie in (section.header, section.footer):
            try:
                morceaux.extend(p.text for p in partie.paragraphs)
            except Exception:
                pass
    return "\n".join(morceaux)


def lire_texte_brut(chemin: Path) -> str:
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return chemin.read_text(encoding=encodage)
        except UnicodeDecodeError:
            continue
    return chemin.read_bytes().decode("utf-8", errors="replace")


def lire_document(chemin: Path, pages: Optional[str] = None) -> str:
    """Texte brut d'un document selon son extension."""
    ext = chemin.suffix.lower()
    if ext == ".pdf":
        return lire_pdf(chemin, pages)
    if ext == ".docx":
        return lire_docx(chemin)
    if ext == ".doc":
        raise ErreurAutoweb("format .doc (ancien Word) non pris en charge : enregistrez-le en .docx.")
    if ext in EXTENSIONS_TEXTE:
        return lire_texte_brut(chemin)
    raise ErreurAutoweb(f"extension non prise en charge : {ext}")


# ----------------------------------------------------------------------------- règles
def _compiler(nom: str, motif: str, options: Dict[str, Any]) -> "re.Pattern[str]":
    drapeaux = re.MULTILINE
    if options.get("ignorer_casse", True):
        drapeaux |= re.IGNORECASE
    if options.get("multiligne_point", False):
        drapeaux |= re.DOTALL
    try:
        return re.compile(motif, drapeaux)
    except re.error as e:
        raise ErreurAutoweb(f"Champ « {nom} » : expression régulière invalide « {motif} » ({e}).")


def charger_regles(chemin: Path) -> Regles:
    chemin = Path(chemin)
    if not chemin.exists():
        raise ErreurAutoweb(f"Fichier de règles introuvable : {chemin}")
    try:
        donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ErreurAutoweb(f"YAML invalide dans {chemin.name} : {e}")
    if not isinstance(donnees, dict) or not isinstance(donnees.get("champs"), dict) or not donnees["champs"]:
        raise ErreurAutoweb(f"{chemin.name} : il faut une section « champs » (nom -> expression régulière).")
    fichiers = donnees.get("fichiers") or ["*.pdf", "*.docx", "*.txt"]
    if isinstance(fichiers, str):
        fichiers = [fichiers]
    champs: List[Champ] = []
    for nom, spec in donnees["champs"].items():
        nom = str(nom)
        if isinstance(spec, str):
            spec = {"regex": spec}
        if not isinstance(spec, dict) or not spec.get("regex"):
            raise ErreurAutoweb(f"{chemin.name} : le champ « {nom} » doit être une regex ou un dictionnaire avec « regex ».")
        motif = _compiler(nom, str(spec["regex"]), spec)
        groupe = int(spec.get("groupe", 1 if motif.groups else 0))
        if groupe > motif.groups:
            raise ErreurAutoweb(f"Champ « {nom} » : groupe {groupe} demandé mais la regex n'a que {motif.groups} groupe(s).")
        champs.append(Champ(
            nom=nom, regex=motif, groupe=groupe,
            defaut="" if spec.get("defaut") is None else str(spec["defaut"]),
            tous=bool(spec.get("tous", False)),
            separateur=str(spec.get("separateur", "; ")),
            nettoyer=bool(spec.get("nettoyer", True)),
            obligatoire=bool(spec.get("obligatoire", False)),
        ))
    return Regles(
        fichiers=[str(f) for f in fichiers],
        champs=champs,
        dossier=str(donnees["dossier"]) if donnees.get("dossier") else None,
        feuille=str(donnees.get("feuille") or "Suivi"),
        colonne_fichier=str(donnees.get("colonne_fichier") or "Fichier"),
        sous_dossiers=bool(donnees.get("sous_dossiers", True)),
        pages=str(donnees["pages"]) if donnees.get("pages") else None,
    )


# ----------------------------------------------------------------------------- extraction
def _nettoyer(texte: str) -> str:
    return " ".join(texte.split())


def extraire_champs(texte: str, champs: Sequence[Champ]) -> Dict[str, str]:
    """Applique les règles à un texte : {nom du champ: valeur}. Les champs absents prennent `defaut`."""
    resultat: Dict[str, str] = {}
    for champ in champs:
        valeurs: List[str] = []
        for m in champ.regex.finditer(texte):
            brut = m.group(champ.groupe) if champ.groupe <= (m.re.groups or 0) else m.group(0)
            if brut is None:
                continue
            valeur = _nettoyer(brut) if champ.nettoyer else brut
            if valeur:
                valeurs.append(valeur)
            if not champ.tous:
                break
        if valeurs:
            resultat[champ.nom] = champ.separateur.join(dict.fromkeys(valeurs)) if champ.tous else valeurs[0]
        else:
            resultat[champ.nom] = champ.defaut
    return resultat


def lister_documents(dossier: Path, regles: Regles) -> List[Path]:
    fichiers: List[Path] = []
    for motif in regles.fichiers:
        fichiers.extend(dossier.rglob(motif) if regles.sous_dossiers else dossier.glob(motif))
    uniques = sorted({f.resolve() for f in fichiers if f.is_file() and not f.name.startswith("~$")})
    return [Path(f) for f in uniques]


def extraire(regles: Regles, dossier: Path, sortie: Path, ecraser: bool = False) -> BilanExtraction:
    dossier = Path(dossier)
    sortie = Path(sortie)
    if not dossier.is_dir():
        raise ErreurAutoweb(f"Dossier de documents introuvable : {dossier}")
    if sortie.exists() and not ecraser:
        raise ErreurAutoweb(f"{sortie} existe déjà : choisissez un autre nom ou ajoutez --ecraser.")
    documents = lister_documents(dossier, regles)
    bilan = BilanExtraction(fichiers=len(documents), sortie=sortie)
    if not documents:
        raise ErreurAutoweb(f"Aucun document correspondant à {', '.join(regles.fichiers)} dans {dossier}.")
    colonnes = [regles.colonne_fichier] + [c.nom for c in regles.champs]
    lignes: List[List[Any]] = []
    for document in documents:
        relatif = document.relative_to(dossier) if dossier.resolve() in document.resolve().parents else document
        ligne: List[Any] = [str(relatif)]
        try:
            texte = lire_document(document, regles.pages)
        except ErreurAutoweb as e:
            bilan.illisibles += 1
            bilan.details.append(f"{relatif} : {e}")
            ligne += [""] * len(regles.champs) + ["ERREUR", f"lecture impossible : {e}", _horodatage()]
            journal.warning("  %s %s : %s", S.ERREUR, relatif, e)
            lignes.append(ligne)
            continue
        except Exception as e:
            bilan.illisibles += 1
            bilan.details.append(f"{relatif} : {e}")
            ligne += [""] * len(regles.champs) + ["ERREUR", f"lecture impossible : {e.__class__.__name__} {e}", _horodatage()]
            journal.warning("  %s %s : %s", S.ERREUR, relatif, e)
            lignes.append(ligne)
            continue
        valeurs = extraire_champs(texte, regles.champs)
        manquants = [c.nom for c in regles.champs if not valeurs.get(c.nom) and c.obligatoire]
        vides = [c.nom for c in regles.champs if not valeurs.get(c.nom)]
        ligne += [valeurs.get(c.nom, "") for c in regles.champs]
        if manquants:
            bilan.incomplets += 1
            ligne += ["A verifier", "champs obligatoires non trouvés : " + ", ".join(manquants), _horodatage()]
            journal.info("  %s %s : champs obligatoires manquants (%s)", S.ATTENTION, relatif, ", ".join(manquants))
        else:
            bilan.reussis += 1
            ligne += ["", ("non trouvés : " + ", ".join(vides)) if vides else "", ""]
            journal.info("  %s %s", S.OK, relatif)
        lignes.append(ligne)
    creer_classeur(sortie, colonnes, lignes, feuille=regles.feuille)
    return bilan


def _horodatage() -> str:
    return dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

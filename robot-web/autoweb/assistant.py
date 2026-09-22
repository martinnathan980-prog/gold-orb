"""Assistant interactif : construit un scénario à partir d'un relevé d'écran et
des colonnes de l'Excel, par questions/réponses dans la console.

Deux types de scénario :
  1. remplir un formulaire et enregistrer (une ligne Excel = une fiche) ;
  2. appliquer des filtres puis exporter / télécharger un fichier.

Tout se passe sur le poste de l'utilisateur : aucune donnée ne sort.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import symboles as S
from .enregistreur import remplacer_texte_selecteur
from .erreurs import ErreurAutoweb
from .gabarit import normaliser_cle
from .releve import selecteur_suggere

MOTS_ENREGISTRER = ("enregistr", "valid", "sauvegard", "soumettre", "save", "submit", "confirm", "creer", "créer", "ajouter", "ok")
MOTS_RECHERCHER = ("recherch", "filtr", "appliquer", "search", "afficher", "actualiser", "go")
MOTS_EXPORTER = ("export", "telecharg", "télécharg", "csv", "excel", "xls", "download", "extraire", "extract")
MOTS_IGNORER_BOUTON = ("annul", "cancel", "retour", "fermer", "supprim", "delete", "reset", "reinit", "réinit", "connect", "deconnex", "déconnex")


class Dialogue:
    """Pose des questions dans la console ; `reponses` permet de les scripter (tests)."""

    def __init__(self, reponses: Optional[Iterable[str]] = None) -> None:
        self.reponses = list(reponses) if reponses is not None else None

    def dire(self, texte: str = "") -> None:
        print(texte)

    def demander(self, question: str, defaut: str = "") -> str:
        invite = f"{question} [{defaut}] : " if defaut else f"{question} : "
        if self.reponses is not None:
            reponse = self.reponses.pop(0) if self.reponses else ""
            print(invite + reponse)
        else:
            print(invite, end="", flush=True)
            try:
                reponse = input()
            except EOFError:
                reponse = ""
        reponse = reponse.strip()
        return reponse if reponse else defaut

    def oui_non(self, question: str, defaut: bool) -> bool:
        reponse = self.demander(f"{question} (o/n)", "o" if defaut else "n").lower()
        return reponse in ("o", "oui", "y", "yes")


def _etiquette(e: Dict[str, Any]) -> str:
    return (e.get("libelle") or e.get("placeholder") or e.get("name") or e.get("id") or "champ").strip().rstrip(" :*")


def _nom_colonne_propose(etiquette: str, colonnes: Sequence[str]) -> Optional[int]:
    """Index (0-based) de la colonne Excel la plus proche de l'étiquette, ou None."""
    if not colonnes:
        return None
    cible = normaliser_cle(etiquette)
    normalisees = [normaliser_cle(c) for c in colonnes]
    if cible in normalisees:
        return normalisees.index(cible)
    for i, c in enumerate(normalisees):
        if cible and (cible in c or c in cible) and min(len(c), len(cible)) >= 4:
            return i
    proches = difflib.get_close_matches(cible, normalisees, n=1, cutoff=0.7)
    return normalisees.index(proches[0]) if proches else None


def _yaml_chaine(texte: str) -> str:
    """Chaîne YAML entre guillemets, avec les sauts de ligne et tabulations échappés."""
    texte = str(texte)
    texte = texte.replace("\\", "\\\\").replace('"', '\\"')
    texte = texte.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n").replace("\t", "\\t")
    return '"' + texte + '"'


# Champs dont la valeur ne doit JAMAIS être écrite dans le scénario.
MOTIF_CHAMP_SECRET = re.compile(r"pass|pwd|mdp|mot.?de.?passe|secret|token|jeton|credential", re.I)
# Codes à usage unique : une variable serait inutile, il faut les saisir sur le moment.
MOTIF_CODE_UNIQUE = re.compile(r"\botp\b|\bsms\b|2fa|mfa|usage.?unique|one.?time|totp|code.?(recu|reçu|envoye|envoyé)", re.I)


def _texte_identifiant(etape: Any) -> str:
    return f"{etape.args.get('selecteur', '')} {getattr(etape, 'libelle', '')}"


def _est_secret(etape: Any) -> bool:
    if getattr(etape, "type_champ", "") == "password":
        return True
    return bool(MOTIF_CHAMP_SECRET.search(_texte_identifiant(etape)))


def _est_code_unique(etape: Any) -> bool:
    return bool(MOTIF_CODE_UNIQUE.search(_texte_identifiant(etape)))


def _bouton_par_defaut(boutons: List[Dict[str, Any]], mots: Sequence[str]) -> Optional[int]:
    for i, b in enumerate(boutons):
        t = normaliser_cle(b.get("texte", ""))
        if any(m in t for m in mots) and not any(m in t for m in MOTS_IGNORER_BOUTON):
            return i
    return None


def _choisir_bouton(d: Dialogue, boutons: List[Dict[str, Any]], question: str, mots: Sequence[str]) -> Optional[str]:
    if boutons:
        d.dire(f"{S.FLECHE} {question}")
        for i, b in enumerate(boutons, start=1):
            etat = "  (désactivé pour l'instant)" if b.get("desactive") else ""
            d.dire(f"     {i}. « {b['texte']} »  ({selecteur_suggere(b)}){etat}")
        defaut = _bouton_par_defaut(boutons, mots)
        reponse = d.demander("   Numéro du bouton (0 = aucun)", str(defaut + 1) if defaut is not None else "0")
        if reponse.isdigit() and 1 <= int(reponse) <= len(boutons):
            return selecteur_suggere(boutons[int(reponse) - 1])
        return None
    reponse = d.demander(f"{S.FLECHE} {question} : sélecteur du bouton (vide = aucun)", "")
    return reponse or None


def _etape_champ(e: Dict[str, Any], sel: str, valeur: str) -> Optional[str]:
    if e.get("tag") == "select":
        return f"  - choisir: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}"
    if e.get("type") == "checkbox" or e.get("role") == "checkbox":
        return f"  - cocher: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}"
    if e.get("type") == "radio":
        return f"  - cliquer: {_yaml_chaine(sel)}"
    if e.get("type") == "file":
        return f"  - televerser: {{selecteur: {_yaml_chaine(sel)}, fichier: {_yaml_chaine(valeur)}}}"
    if e.get("type") == "date":
        if valeur.startswith("{{"):
            valeur = valeur[:-2].rstrip() + " | date:%Y-%m-%d}}"
        return f"  - remplir: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}   # champ date HTML : AAAA-MM-JJ"
    return f"  - remplir: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}"


def _questions_champs(d: Dialogue, champs: List[Dict[str, Any]], colonnes: Sequence[str], mot: str) -> List[str]:
    """Pour chaque champ visible : quelle colonne Excel (ou valeur fixe) le remplit ?"""
    etapes: List[str] = []
    for e in champs:
        etiquette = _etiquette(e)
        sel = selecteur_suggere(e)
        if sel.startswith("("):
            d.dire(f"   ({mot} « {etiquette} » sans sélecteur fiable : ignoré, voir champs.txt)")
            continue
        genre = e.get("tag")
        if genre == "input":
            genre = f"input {e.get('type') or 'text'}"
        d.dire()
        d.dire(f"{S.FLECHE} {mot} « {etiquette} »  ({genre}, sélecteur {sel})")
        if e.get("options"):
            d.dire("   options : " + " ; ".join(e["options"][:10]) + (" ; ..." if len(e["options"]) > 10 else ""))
        if e.get("type") == "password":
            if d.oui_non("   Mot de passe : le saisir au lancement avec --var mot_de_passe=... ?", True):
                etapes.append(f"  - remplir: {{selecteur: {_yaml_chaine(sel)}, valeur: \"{{{{mot_de_passe}}}}\"}}")
            continue
        if colonnes:
            for i, c in enumerate(colonnes, start=1):
                d.dire(f"     {i}. {c}")
            propose = _nom_colonne_propose(etiquette, colonnes)
            defaut = str(propose + 1) if propose is not None else "0"
            reponse_brute = d.demander("   Colonne Excel (numéro), v = valeur fixe, 0 = ignorer", defaut)
        else:
            reponse_brute = d.demander("   Nom de la colonne Excel (vide = ignorer, v = valeur fixe)", "")
        reponse = reponse_brute.lower()
        if reponse in ("", "0", "n", "non"):
            continue
        if reponse in ("v", "valeur", "fixe"):
            fixe = d.demander("   Valeur fixe à saisir", "")
            if not fixe:
                continue
            valeur = fixe
        elif colonnes and reponse.isdigit() and 1 <= int(reponse) <= len(colonnes):
            valeur = "{{" + colonnes[int(reponse) - 1] + "}}"
        elif not colonnes:
            valeur = "{{" + reponse_brute + "}}"
        else:
            correspondance = _nom_colonne_propose(reponse_brute, colonnes)
            if correspondance is None:
                d.dire(f"   {S.ATTENTION} « {reponse_brute} » ne correspond à aucune colonne : {mot.lower()} ignoré.")
                continue
            valeur = "{{" + colonnes[correspondance] + "}}"
        etape = _etape_champ(e, sel, valeur)
        if etape:
            etapes.append(etape)
    return etapes


def deviner_colonne(valeur: Any, colonnes: Sequence[str], lignes: Sequence[Dict[str, Any]]) -> Optional[int]:
    """Colonne de l'Excel dont une cellule vaut exactement `valeur` (index 0, None si aucune ou plusieurs)."""
    from .gabarit import formater

    import datetime as _dt

    def formes(v: Any) -> set:
        """Écritures possibles d'une valeur : « 21/09/2026 » et « 2026-09-21 » sont la même date."""
        resultat = {normaliser_cle(formater(v))}
        if isinstance(v, (_dt.datetime, _dt.date)):
            resultat.add(normaliser_cle(v.strftime("%Y-%m-%d")))
        elif isinstance(v, str):
            from .gabarit import parser_date

            date = parser_date(v)
            if date is not None:
                resultat.add(normaliser_cle(date.strftime("%Y-%m-%d")))
                resultat.add(normaliser_cle(date.strftime("%d/%m/%Y")))
        return {f for f in resultat if f}

    cibles = formes(valeur)
    if not cibles:
        return None
    trouvees = set()
    for ligne in lignes:
        for i, colonne in enumerate(colonnes):
            if formes(ligne.get(colonne)) & cibles:
                trouvees.add(i)
    if len(trouvees) == 1:
        return trouvees.pop()
    return None


def _entete_scenario(
    nom: str, base: str, canal: str, fichier_excel: str, feuille: Optional[str],
    colonnes: Sequence[str], url: str, secrets: Sequence[str] = (),
) -> List[str]:
    lignes = [
        "# Scénario autoweb — à relire, puis :",
        "#   ./robot.command verifier <ce fichier>     (robot verifier ... sous Windows)",
        "#   ./robot.command simuler  <ce fichier>",
        "#   ./robot.command lancer   <ce fichier> --limite 1",
        f"nom: {_yaml_chaine(nom)}",
        "navigateur:",
        f"  canal: {canal if canal in ('chrome', 'msedge', 'chromium', 'auto') else 'auto'}"
        "            # chrome | msedge | chromium | auto",
        f"  profil: profils/{base}",
        "  visible: true",
        "  delai_max: 15000",
        "excel:",
        f"  fichier: {_yaml_chaine(fichier_excel)}",
    ]
    if feuille:
        lignes.append(f"  feuille: {_yaml_chaine(feuille)}")
    if colonnes:
        lignes.append(f"  colonne_libelle: {_yaml_chaine(colonnes[0])}")
    lignes += ["variables:", f"  url: {_yaml_chaine(url)}"]
    for secret in secrets:
        lignes.append(f'  {secret}: ""   # demandé au lancement, ou --var {secret}=...')
    return lignes


def _remplacer_valeur(texte: str, colonne: Optional[str]) -> str:
    return "{{" + colonne + "}}" if colonne else texte


def _bloc_etapes(
    etapes: List[Any],
    indent: str,
    question_valeur,
    telechargements: List[Any],
    secrets: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Traduit des étapes enregistrées en lignes YAML, en gérant les iframes."""
    lignes: List[str] = []
    cadre_courant = ""
    indent_courant = indent
    for e in etapes:
        if e.cadre != cadre_courant:
            cadre_courant = e.cadre
            indent_courant = indent
            if cadre_courant:
                lignes.append(f"{indent}- cadre:")
                lignes.append(f"{indent}    selecteur: {_yaml_chaine(cadre_courant)}")
                lignes.append(f"{indent}    etapes:")
                indent_courant = indent + "      "

        i = indent_courant
        if e.action == "aller":
            lignes.append(f'{i}- aller: "{{{{url}}}}"')
        elif e.action == "attendre":
            lignes.append(f"{i}- attendre: {{chargement: reseau, delai: {int(e.args.get('delai', 8000))}}}")
            lignes.append(f"{i}  optionnel: true")
        elif e.action == "cliquer":
            selecteur = str(e.args["selecteur"])
            if e.texte_selecteur:
                colonne = question_valeur(e.texte_selecteur, "Vous avez cliqué sur")
                if colonne:
                    selecteur = remplacer_texte_selecteur(selecteur, e.texte_selecteur, "{{" + colonne + "}}")
            lignes.append(f"{i}- cliquer: {_yaml_chaine(selecteur)}")
        elif e.action in ("remplir", "choisir", "cocher"):
            selecteur = str(e.args["selecteur"])
            valeur = str(e.args.get("valeur", ""))
            commentaire = ""
            if _est_code_unique(e):
                # code à usage unique : il change à chaque fois, on le demande sur le moment
                lignes.append(
                    f'{i}- pause: "Saisissez le code dans le navigateur ({e.libelle or selecteur}), '
                    'puis appuyez sur Entrée"')
                continue
            if _est_secret(e):
                registre = secrets if secrets is not None else {}
                if selecteur not in registre:
                    registre[selecteur] = "mot_de_passe" if not registre else f"mot_de_passe_{len(registre) + 1}"
                valeur_finale = "{{" + registre[selecteur] + "}}"
                commentaire = "   # jamais écrit ici : demandé au lancement"
            else:
                contexte = {"remplir": "Vous avez écrit", "choisir": "Vous avez choisi", "cocher": "Vous avez coché"}[e.action]
                colonne = question_valeur(valeur, f"{contexte}, dans « {e.libelle or selecteur} » :")
                valeur_finale = "{{" + colonne + "}}" if colonne else valeur
                if colonne and e.type_champ == "date":
                    valeur_finale = "{{" + colonne + " | date:%Y-%m-%d}}"
                    commentaire = "   # champ date : format AAAA-MM-JJ attendu par le navigateur"
            lignes.append(
                f"{i}- {e.action}: {{selecteur: {_yaml_chaine(selecteur)}, valeur: {_yaml_chaine(valeur_finale)}}}{commentaire}"
            )
        elif e.action == "touche":
            lignes.append(
                f"{i}- touche: {{selecteur: {_yaml_chaine(str(e.args['selecteur']))}, touche: {e.args.get('touche', 'Enter')}}}"
            )
        elif e.action == "telecharger":
            telechargements.append(e)
            lignes.append(f"{i}__TELECHARGEMENT_{len(telechargements) - 1}__")
    return lignes


def construire_depuis_enregistrement(
    etapes: List[Any],
    colonnes: Sequence[str],
    lignes_excel: Sequence[Dict[str, Any]],
    dialogue: Dialogue,
    nom: str,
    fichier_excel: str = "suivi.xlsx",
    feuille: Optional[str] = None,
    canal: str = "chrome",
    url_depart: str = "",
    dossier_exports: str = "exports",
) -> str:
    """Transforme un enregistrement (liste d'EtapeEnregistree) en scénario YAML,
    en demandant d'où vient chaque valeur saisie."""
    d = dialogue
    base = re.sub(r"[^a-z0-9_-]+", "_", nom.lower()).strip("_") or "tache"

    d.dire()
    d.dire(f"{S.LIGNE} Enregistrement terminé : {len(etapes)} étape(s)")
    for i, e in enumerate(etapes, start=1):
        d.dire(f"   {i:2}. {e.resume()}")
    d.dire()
    retirer = d.demander("Étapes à retirer (numéros séparés par des virgules, Entrée = tout garder)", "")
    if retirer.strip():
        a_retirer = {int(m.strip()) for m in retirer.replace(";", ",").split(",") if m.strip().isdigit()}
        etapes = [e for i, e in enumerate(etapes, start=1) if i not in a_retirer]
        d.dire(f"   {len(etapes)} étape(s) conservée(s).")

    # Connexion : à faire une fois au début, pas à chaque ligne de l'Excel.
    etapes_connexion: List[Any] = []
    selecteur_connexion = ""
    index_mdp = next((i for i, e in enumerate(etapes) if getattr(e, "type_champ", "") == "password"), None)
    if index_mdp is not None:
        fin = index_mdp
        for j in range(index_mdp + 1, len(etapes)):
            if etapes[j].action == "cliquer":
                fin = j
                break
        debut = 1 if etapes and etapes[0].action == "aller" else 0
        d.dire()
        d.dire(f"{S.FLECHE} Les premières étapes ressemblent à une connexion :")
        for e in etapes[debut:fin + 1]:
            d.dire(f"     - {e.resume()}")
        if d.oui_non("   La faire une seule fois au début, et non à chaque ligne (recommandé) ?", True):
            etapes_connexion = etapes[debut:fin + 1]
            selecteur_connexion = str(etapes[index_mdp].args.get("selecteur", ""))
            etapes = etapes[:debut] + etapes[fin + 1:]

    if colonnes:
        d.dire()
        d.dire("Pour chaque valeur que vous avez saisie, indiquez la colonne de l'Excel qui la donne.")
        d.dire("Entrée accepte la proposition ; 0 garde la valeur telle quelle à chaque ligne.")

    def question_valeur(valeur: str, contexte: str) -> Optional[str]:
        if not colonnes or not str(valeur).strip():
            return None
        propose = deviner_colonne(valeur, colonnes, lignes_excel)
        if propose is None and contexte.startswith("Vous avez cliqué"):
            return None  # texte de bouton : il ne change pas d'une ligne à l'autre
        d.dire()
        d.dire(f"{S.FLECHE} {contexte} « {valeur} »")
        for i, c in enumerate(colonnes, start=1):
            d.dire(f"     {i}. {c}")
        defaut = str(propose + 1) if propose is not None else "0"
        reponse = d.demander("   Colonne (numéro), 0 = valeur toujours identique", defaut)
        if reponse.isdigit() and 1 <= int(reponse) <= len(colonnes):
            return colonnes[int(reponse) - 1]
        return None

    telechargements: List[Any] = []
    secrets: Dict[str, str] = {}
    lignes_etapes = _bloc_etapes(etapes, "  ", question_valeur, telechargements, secrets)
    lignes_connexion = _bloc_etapes(etapes_connexion, "        ", lambda v, c: None, telechargements, secrets)
    if not [l for l in lignes_etapes if l.strip() and not l.strip().startswith("- aller")]:
        raise ErreurAutoweb(
            "Il ne reste aucune action à rejouer : le scénario ne ferait rien.\n"
            "Recommencez l'enregistrement (menu, choix 1) en faisant la tâche complète."
        )

    d.dire()
    premiere = colonnes[0] if colonnes else "ligne"
    texte_succes = ""
    if telechargements:
        dossier = d.demander(f"{S.FLECHE} Dossier où ranger les fichiers téléchargés", dossier_exports)
        nom_fichier = d.demander(
            f"{S.FLECHE} Nom du fichier, sans extension (vide = nom donné par l'outil)",
            f"export_{{{{{premiere}}}}}" if colonnes else "")
        convertir = d.oui_non(f"{S.FLECHE} Convertir un export CSV en Excel (.xlsx) ?", True)
        colonne_fichier = d.demander(
            f"{S.FLECHE} Colonne où écrire le chemin du fichier obtenu (vide = aucune)", "Fichier export")
        for numero, e in enumerate(telechargements):
            options = [f"cliquer: {_yaml_chaine(str(e.args['cliquer']))}",
                       f"vers: {_yaml_chaine(dossier.rstrip('/') + '/')}"]
            if nom_fichier:
                options.append(f"renommer: {_yaml_chaine(nom_fichier)}")
            if convertir:
                options.append("convertir_excel: true")
            if colonne_fichier:
                options.append(f"vers_colonne: {_yaml_chaine(colonne_fichier)}")
            remplacement = "- telecharger: {" + ", ".join(options) + "}"
            marque = f"__TELECHARGEMENT_{numero}__"
            lignes_etapes = [l.replace(marque, remplacement) for l in lignes_etapes]
            lignes_connexion = [l.replace(marque, remplacement) for l in lignes_connexion]
    else:
        texte_succes = d.demander(
            f"{S.FLECHE} Texte affiché par l'outil quand tout s'est bien passé (vide = pas de contrôle)", "")

    if etapes_connexion:
        pause_connexion = d.oui_non(
            f"{S.FLECHE} Ajouter une pause au début, pour vérifier la connexion (code, carte, écran en deux temps) ?", True)
    else:
        pause_connexion = d.oui_non(f"{S.FLECHE} Faut-il se connecter à la main au début (SSO, mot de passe) ?", True)
    capture = d.oui_non(f"{S.FLECHE} Faire une capture d'écran à la fin de chaque ligne ?", True)

    lignes = _entete_scenario(nom, base, canal, fichier_excel, feuille, colonnes, url_depart,
                              secrets=sorted(set(secrets.values())))
    if etapes_connexion or pause_connexion:
        lignes.append("avant:")
        lignes.append('  - aller: "{{url}}"')
        if etapes_connexion:
            lignes.append("  - si:")
            lignes.append(f"      visible: {_yaml_chaine(selecteur_connexion)}   # seulement si l'écran de connexion est là")
            lignes.append("      alors:")
            lignes += lignes_connexion
        if pause_connexion:
            lignes.append('  - pause: "Vérifiez que vous êtes bien connecté dans le navigateur, puis appuyez sur Entrée"')
    lignes.append("etapes:")
    if not lignes_etapes or not lignes_etapes[0].strip().startswith("- aller"):
        lignes.append('  - aller: "{{url}}"')
    lignes += lignes_etapes
    if texte_succes:
        lignes.append(f"  - verifier: {{texte_page: {_yaml_chaine(texte_succes)}}}")
    if capture:
        lignes.append(f"  - capture: {_yaml_chaine('captures/{{' + premiere + '}}.png')}")
    return "\n".join(lignes) + "\n"


def construire(
    releve: Dict[str, Any],
    colonnes: Sequence[str],
    dialogue: Dialogue,
    nom: Optional[str] = None,
    fichier_excel: str = "suivi.xlsx",
    feuille: Optional[str] = None,
    canal: str = "chrome",
) -> str:
    """Pose les questions et renvoie le texte YAML du scénario."""
    elements = [e for e in releve["elements"] if e.get("visible")]
    champs = [e for e in elements if not e.get("bouton") and e.get("tag") != "a" and not e.get("desactive")]
    boutons = [e for e in elements if e.get("bouton") and e.get("texte")]
    nom = nom or releve.get("nom") or releve.get("titre") or "scenario"
    base = re.sub(r"[^a-z0-9_-]+", "_", nom.lower()).strip("_") or "outil"
    d = dialogue

    d.dire()
    d.dire(f"{S.LIGNE} Assistant de scénario : « {nom} »")
    d.dire(f"   Écran relevé : {releve.get('titre', '')}  ({releve.get('url', '')})")
    d.dire(f"   {len(champs)} champ(s) visible(s), {len(boutons)} bouton(s).")
    if colonnes:
        d.dire("   Colonnes Excel : " + ", ".join(colonnes))
    d.dire("   Entrée = accepter la proposition entre crochets.")
    d.dire()
    d.dire(f"{S.FLECHE} Que doit faire ce scénario ?")
    d.dire("     1. Remplir un formulaire et enregistrer (une ligne Excel = une fiche)")
    d.dire("     2. Appliquer des filtres puis exporter / télécharger un fichier (une ligne Excel = un export)")
    export = d.demander("   Choix", "1").startswith("2")
    d.dire()
    d.dire(f"{S.FLECHE} Adresse ouverte pour chaque ligne de l'Excel.")
    if colonnes:
        d.dire(f"   Vous pouvez y insérer une colonne, par exemple : .../fiche={{{{{colonnes[0]}}}}}")
    url = d.demander("   Adresse", releve.get("url", ""))

    d.dire()
    if export:
        d.dire("   Pour chaque filtre, indiquez la colonne Excel qui donne sa valeur (numéro), « v » pour une valeur fixe, 0 pour ne pas y toucher.")
    else:
        d.dire("   Pour chaque champ, indiquez la colonne Excel qui le remplit (numéro), « v » pour une valeur fixe, 0 pour l'ignorer.")
    etapes = _questions_champs(d, champs, colonnes, "Filtre" if export else "Champ")
    d.dire()

    premiere = colonnes[0] if colonnes else "ligne"
    lignes_fin: List[str] = []
    if export:
        bouton_recherche = _choisir_bouton(d, boutons, "Quel bouton applique les filtres / lance la recherche ?", MOTS_RECHERCHER)
        bouton_export = _choisir_bouton(d, boutons, "Quel bouton exporte / télécharge ?", MOTS_EXPORTER)
        dossier = d.demander(f"{S.FLECHE} Dossier où enregistrer les fichiers (ex. exports, ou %USERPROFILE%\\Desktop)", "exports")
        renommer = d.demander(f"{S.FLECHE} Nom du fichier, sans extension (vide = nom donné par l'outil)", f"export_{{{{{premiere}}}}}" if colonnes else "")
        convertir = d.oui_non(f"{S.FLECHE} Convertir un export CSV en Excel (.xlsx) ?", True)
        vers_colonne = d.demander(f"{S.FLECHE} Colonne Excel où écrire le chemin du fichier obtenu (vide = aucune)", "Fichier export")
        connexion = d.oui_non(f"{S.FLECHE} Faut-il se connecter à la main au début (SSO, mot de passe) ?", True)
        pause = False
        if bouton_recherche:
            lignes_fin.append(f"  - cliquer: {_yaml_chaine(bouton_recherche)}")
            lignes_fin.append("  - attendre: {chargement: reseau, delai: 5000}   # laisse les résultats se charger")
            lignes_fin.append("    optionnel: true")
        if bouton_export:
            options = [f"cliquer: {_yaml_chaine(bouton_export)}", f"vers: {_yaml_chaine(dossier.rstrip('/') + '/')}"]
            if renommer:
                options.append(f"renommer: {_yaml_chaine(renommer)}")
            if convertir:
                options.append("convertir_excel: true")
            if vers_colonne:
                options.append(f"vers_colonne: {_yaml_chaine(vers_colonne)}")
            lignes_fin.append("  - telecharger: {" + ", ".join(options) + "}")
        else:
            lignes_fin.append("  # - telecharger: {cliquer: \"role=button:Exporter\", vers: \"exports/\", convertir_excel: true}")
        capture = False
        texte_succes = ""
        sel_reference = ""
        colonne_reference = ""
        bouton_sel = None
    else:
        bouton_sel = _choisir_bouton(d, boutons, "Quel bouton enregistre le formulaire ?", MOTS_ENREGISTRER)
        pause = d.oui_non(f"{S.FLECHE} Garder une pause de vérification avant le clic final (recommandé pour les premiers essais) ?", True)
        texte_succes = d.demander(f"{S.FLECHE} Texte affiché par l'outil quand l'enregistrement a réussi (vide = pas de contrôle)", "")
        sel_reference = d.demander(f"{S.FLECHE} Sélecteur de la référence attribuée à relever dans l'Excel (vide = aucune)", "")
        colonne_reference = d.demander("   Colonne Excel où l'écrire", "Référence outil") if sel_reference else ""
        connexion = d.oui_non(f"{S.FLECHE} Faut-il se connecter à la main au début (SSO, mot de passe) ?", True)
        capture = d.oui_non(f"{S.FLECHE} Faire une capture d'écran après chaque ligne ?", True)

    lignes = _entete_scenario(nom, base, canal, fichier_excel, feuille, colonnes, url)
    if connexion:
        lignes += [
            "avant:",
            "  - aller: \"{{url}}\"",
            "  - pause: \"Connectez-vous dans le navigateur si nécessaire, puis appuyez sur Entrée\"",
        ]
    lignes += ["etapes:", "  - aller: \"{{url}}\""]
    lignes += etapes
    if pause:
        lignes.append("  - pause: \"Vérifiez le formulaire à l'écran puis appuyez sur Entrée (stop pour arrêter)\"   # à retirer une fois validé")
    if bouton_sel:
        lignes.append(f"  - cliquer: {_yaml_chaine(bouton_sel)}")
    lignes += lignes_fin
    if texte_succes:
        lignes.append(f"  - verifier: {{texte_page: {_yaml_chaine(texte_succes)}}}")
    if sel_reference:
        lignes.append(f"  - lire: {{selecteur: {_yaml_chaine(sel_reference)}, vers: {_yaml_chaine(colonne_reference)}}}")
    if capture:
        lignes.append(f"  - capture: \"captures/{{{{{premiere}}}}}.png\"")
    return "\n".join(lignes) + "\n"

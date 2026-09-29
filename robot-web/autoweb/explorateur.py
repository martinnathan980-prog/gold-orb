"""Explorateur : parcourt un portail web SANS RIEN MODIFIER et en dresse la carte.

Le robot part de la page d'accueil (l'utilisateur s'est connecté), puis suit les
liens et clique sur les éléments de navigation (menus, onglets, lignes de tableau,
boutons de consultation). Pour chaque écran rencontré, il note les champs, les
boutons, les tableaux, et comment on y arrive.

Sécurité, en couches indépendantes :
1. il ne remplit aucun champ, n'appuie sur aucune touche, ne coche rien ;
2. il ne clique que sur des éléments de navigation ou de consultation (liste
   d'autorisation), jamais sur un élément dont le texte évoque une action (liste
   d'interdiction), ni sur un symbole sans texte (×, icône), ni dans une fenêtre
   de confirmation, ni sur un bouton qui envoie un formulaire ;
3. la vérification et le clic ont lieu dans le MÊME instant, dans la page : si
   l'écran a changé entre-temps, rien n'est cliqué ; et le clic vise l'élément
   lui-même, jamais un point de l'écran (une case à cocher posée au milieu d'une
   ligne n'est pas touchée) ;
4. dans le navigateur, toute requête qui enverrait des données (POST, PUT,
   DELETE...), toute adresse qui ressemble à une action (…/supprimer,
   ?action=del...) et toute connexion WebSocket sont bloquées avant de partir ;
5. les confirmations reçoivent « Annuler », l'impression est neutralisée, les
   téléchargements annulés, les fenêtres ouvertes refermées.

Sur une grosse base, tout visiter serait infini : un ou deux exemples par modèle
d'écran suffisent (deux fiches composant, deux pages de liste...).

Résultats, dans explorations/<date>/ :
- carte.json et carte_PRIVEE_ne_pas_envoyer.html : tout ce qui a été vu (restent sur le poste) ;
- carte_a_partager.txt : la structure (écrans, noms des champs, colonnes, onglets,
  menus, boutons usuels), sans valeurs, sans adresses, sans titres de page.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlsplit

from playwright.sync_api import Page

from . import symboles as S
from .erreurs import ErreurAutoweb
from .navigateur import Navigateur, navigateur_ferme, site_de

journal = logging.getLogger("autoweb")


# ---------------------------------------------------------------------- vocabulaire
def normaliser(texte: str) -> str:
    """minuscules, sans accents, espaces simples : « Créer un Plan » -> « creer un plan »."""
    texte = unicodedata.normalize("NFD", str(texte or ""))
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texte.lower()).strip()


# Débuts de mots qui évoquent une action : jamais cliqués. Un préfixe (re-, dé-, in-,
# un-...) est accepté devant : « renvoyer », « dévalider », « unpublish » sont interdits.
RADICAUX_INTERDITS = (
    "supprim", "suppr", "effac", "delete", "remove", "retir", "archiver", "valid", "enregistr", "enreg",
    "sauvegard", "save", "submit", "soumettre", "envoyer", "renvoyer", "renvoi", "send", "publier", "publish", "diffuser",
    "cree", "creer", "creat", "ajout", "add", "insert", "nouveau", "nouvelle", "new", "modif",
    "edit", "import", "upload", "joindre", "attach", "dupliqu", "copier", "clon", "deplac", "affecter",
    "attribuer", "assign", "approuv", "approve", "rejet", "reject", "refus", "signer", "sign in",
    "sign up", "signup", "confirm", "annul", "cancel", "initialis", "reset", "deconnex", "deconnect",
    "disconnect", "logout", "log out", "logoff", "sign out", "signout", "quitter", "fermer", "close",
    "imprim", "impression", "print", "export", "telecharg", "download", "verrou", "lock", "clotur",
    "clore", "terminer", "transfer", "commander", "achat", "acheter", "payer", "paiement", "payment",
    "vider", "purge", "restaur", "retablir", "activer", "activate", "enable", "disable", "mettre a jour",
    "mise a jour", "update", "generer", "generate", "generation", "lancer", "execut", "run", "demarrer",
    "start", "stop", "arreter", "notif", "partag", "share", "invit", "abonn", "subscri", "vote",
    "accepter", "accept", "decline", "renomm", "rename", "fusion", "merge", "calcul", "traiter", "sync",
    "reserver", "liberer", "bloquer", "debloquer", "reviser", "indicer", "detrui", "destroy",
    "erase", "discard", "revert", "rollback", "undo", "appliqu", "apply", "release", "promouv", "promot",
    "freeze", "geler", "figer", "check in", "check out", "checkin", "checkout", "extraire", "detach",
    "dissoci", "remplac", "marquer", "obsolet", "changer", "change", "corbeille", "trash", "favori",
    "suivre", "follow", "epingl", "noter", "commenter", "comment", "repondre", "reply", "transmet",
    "afficher en tant", "retourner", "rejouer", "relire", "planifier", "schedul", "demander",
)
MOTS_ENTIERS_INTERDITS = ("del", "rm", "ok", "oui", "yes", "go", "done", "maj", "x", "star", "like", "set",
                          "pin", "unpin", "archive")
MOTIF_INTERDIT = re.compile(
    r"(?<![a-z0-9])(?:re|de|des|in|un|dis|pre|auto)?(?:" + "|".join(re.escape(m) for m in RADICAUX_INTERDITS) + ")"
    r"|(?<![a-z0-9])(?:" + "|".join(re.escape(m) for m in MOTS_ENTIERS_INTERDITS) + r")(?![a-z0-9])"
)

# Premier mot d'un bouton de simple consultation : seul cas où un bouton ordinaire est cliqué.
PREMIERS_MOTS_LECTURE = {
    "rechercher", "recherche", "chercher", "search", "filtrer", "filter", "afficher", "voir", "view",
    "consulter", "detail", "details", "suivant", "next", "precedent", "previous", "prev", "page",
    "retour", "back", "accueil", "home", "apercu", "preview", "historique", "history", "trier", "sort",
    "developper", "deplier", "replier", "agrandir", "expand", "collapse", "plus",
}
# Valeurs d'un paramètre « action » qui restent de la consultation.
VALEURS_LECTURE = PREMIERS_MOTS_LECTURE | {"list", "liste", "show", "index", "display", "read", "get", "fiche"}
CLES_ACTION = {"action", "op", "operation", "cmd", "command", "do", "task"}

EXTENSIONS_FICHIERS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".csv", ".zip", ".7z", ".rar", ".txt",
    ".xml", ".json", ".dwg", ".dxf", ".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".ppt", ".pptx",
)
# Types de fichiers repris dans la carte : un nom de fichier peut finir par « .Roux » ou « .Penly »
TYPES_FICHIERS = {e.lstrip(".") for e in EXTENSIONS_FICHIERS} | {
    "step", "stp", "igs", "iges", "stl", "sat", "jt", "prt", "asm", "drw", "sldprt", "sldasm", "slddrw", "catpart",
    "catproduct", "catdrawing", "dgn", "dwf", "dwfx", "plt", "hpgl", "svg", "bmp", "webp", "msg", "eml", "odt",
    "ods", "odp", "odg", "rtf", "html", "htm", "gz", "tar", "tgz", "bin", "dat", "log", "ifc", "rvt", "vsd", "vsdx",
    "mpp", "xlsb", "docm", "pptm", "xps", "oxps", "p7m", "sig",
}


def extension_connue(nom: str) -> str:
    """Type d'un fichier (« pdf », « dwg ») s'il est connu, sinon « ? »."""
    m = re.search(r"\.([A-Za-z0-9]{1,12})(?:$|[?#])", str(nom or ""))
    extension = m.group(1).lower() if m else ""
    return extension if extension in TYPES_FICHIERS else "?"


METHODES_LECTURE = ("GET", "HEAD", "OPTIONS")
# Adresses où le serveur de connexion de l'entreprise (SSO) renvoie l'utilisateur pour ouvrir
# la session : ce retour se fait en POST, mais il ne modifie aucune donnée du portail.
MOTIF_RETOUR_CONNEXION = re.compile(
    r"/(?:saml2?/(?:acs|post|consume|sso)|acs|signin-oidc|signin-saml|signin-wsfed|shibboleth\.sso/saml2?/post"
    r"|oauth2?/callback|login/oauth2?/code(?:/[^/]*)?|auth/callback|openid/callback|_trust|adfs/ls"
    # jeton de connexion demandé par la page elle-même (Microsoft, Okta, ADFS) : aucune donnée du portail
    r"|oauth2/(?:v2\.0/)?token|connect/token|as/token\.oauth2|oauth2/v1/token|adfs/oauth2/token)/?$",
    re.IGNORECASE,
)
# Ressources jamais bloquées pour leur adresse : feuilles de style, polices, scripts, médias.
RESSOURCES_STATIQUES = ("stylesheet", "font", "script", "media", "manifest", "texttrack")


def mot_interdit(*textes: str) -> Optional[str]:
    """Le mot qui interdit le clic, ou None."""
    for texte in textes:
        m = MOTIF_INTERDIT.search(normaliser(texte).replace("_", " "))
        if m:
            return m.group(0)
    return None


# Filet de sécurité de la visite guidée : les mots d'ACTION (modification). Sans les mots de
# consultation ou de sortie (Télécharger, Exporter, Imprimer, Fermer, Annuler seul, Déconnexion)
# ni les ambigus (Valider, OK, Oui, Confirmer, Générer) : ceux-là passent par le contrôle des envois.
EXCLUS_GARDE = {
    "export", "telecharg", "download", "imprim", "impression", "print", "fermer", "close", "quitter", "valid",
    "confirm", "annul", "cancel", "relire", "retourner", "afficher en tant", "rejouer", "changer", "change",
    "generer", "generate", "generation", "sign in", "sign up", "signup", "logout", "log out", "logoff", "sign out",
    "signout", "deconnex", "deconnect", "disconnect", "demander", "noter", "lancer", "run", "start", "demarrer",
    "stop", "arreter", "calcul", "traiter", "execut", "appliqu", "apply", "initialis", "reset",
}
# Verbes anglais à leur forme de base : « Delete », « Save » (en français, l'infinitif suffit :
# « Supprimer » oui, « Supprimés » ou « Modifications » non).
VERBES_ANGLAIS = [
    "delete", "remove", "save", "create", "update", "archive", "restore", "rename", "move", "merge", "release",
    "approve", "promote", "revise", "duplicate", "erase", "purge", "clone", "insert", "add", "edit", "copy", "lock",
    "unlock", "checkout", "checkin", "submit", "send", "upload", "import", "assign", "reject", "publish", "discard",
    "revert", "rollback", "undo", "destroy", "transfer", "sign", "decline", "accept", "share", "invite", "subscribe",
    "follow", "pin", "unpin", "attach", "detach", "replace", "freeze", "commit", "post",
]
# Verbes d'action NETS, pour les adresses et les envois de la page (…/delete, action=supprimer) et
# pour les onglets : pas de noms (« commentaires », « favoris ») ni d'ambigus (« valider »).
VERBES_FORTS = [
    "supprim", "suppr", "delete", "remove", "effac", "erase", "destroy", "purge", "enregistr", "sauvegard", "save",
    "dupliqu", "duplicate", "clon", "copier", "copy", "creer", "create", "insert", "ajout", "add", "update", "modif",
    "edit", "approuv", "approve", "rejet", "reject", "refus", "publier", "publish", "verrou", "lock", "unlock",
    "checkout", "checkin", "archiv", "restaur", "restore", "renomm", "rename", "deplac", "move", "transfer",
    "promouv", "promote", "revis", "liber", "release", "submit", "soumettre", "envoy", "send", "import", "upload",
    "assign", "affect", "attribu", "merge", "fusion", "undo", "revert", "rollback", "discard", "retir", "vider",
]
VERBES_FORTS_ONGLETS = ["supprim", "delete", "remove", "effac", "erase", "enregistr", "sauvegard", "save", "purge"]
RADICAUX_GARDE = [r for r in RADICAUX_INTERDITS if r not in EXCLUS_GARDE]
MOTS_GARDE = [m for m in MOTS_ENTIERS_INTERDITS if m not in {"ok", "oui", "yes", "go", "done", "x"}]
MOTIF_GARDE_SOURCE = (
    r"(?<![a-z0-9])(?:re|de|des|in|un|dis|pre|auto)?(?:" + "|".join(r.replace(" ", r"\s") for r in RADICAUX_GARDE) + ")"
    r"|(?<![a-z0-9])(?:" + "|".join(MOTS_GARDE) + r")(?![a-z0-9])"
    # « Annuler l'extraction », « Cancel checkout » : annuler QUELQUE CHOSE est une action
    r"|^(?:annul\w*|cancel)\s+\S"
)
MOTIF_GARDE = re.compile(MOTIF_GARDE_SOURCE)


def mot_garde(*textes: str) -> Optional[str]:
    """Le mot d'action qui fait bloquer un bouton pendant la visite, ou None."""
    for texte in textes:
        m = MOTIF_GARDE.search(normaliser(texte).replace("_", " "))
        if m:
            return m.group(0)
    return None


# Premiers mots de bouton repris tels quels : des verbes, ou des noms d'action (jamais « Newcastle »,
# « Printemps » ou « Lockheed », qui ne font que COMMENCER comme un verbe)
MOTS_ACTION_BOUTONS = {
    "nouveau", "nouvelle", "new", "impression", "export", "exportation", "import", "suppression", "creation",
    "modification", "duplication", "enregistrement", "validation", "telechargement", "sauvegarde", "copie", "ajout",
    "open", "close", "cancel", "print", "download", "show", "check", "refresh", "run", "start", "stop", "apply",
    "reset", "compare", "generate", "validate", "confirm", "ok", "oui", "non", "yes", "no",
}


def verbe_de_bouton(mot: str) -> bool:
    """« Supprimer », « Exporter », « Delete », « Voir », « Nouveau » : oui. « Newcastle » : non."""
    m = normaliser(mot).strip(".:,;!?…()[]")
    if m in PREMIERS_MOTS_LECTURE or m in VERBES_ANGLAIS or m in MOTS_ACTION_BOUTONS:
        return True
    return bool(re.fullmatch(r"[a-z]+(?:er|ir|re)", m)) and mot_interdit(m) is not None


def est_lecture(texte: str) -> bool:
    """Vrai si le libellé COMMENCE par un mot de consultation (« Voir le détail »),
    jamais pour « Tout marquer comme lu » ou « Ouvrir un ticket »."""
    mots = re.findall(r"[a-z]+", normaliser(texte))
    return bool(mots) and mots[0] in PREMIERS_MOTS_LECTURE and mot_interdit(texte) is None


def a_des_lettres(texte: str) -> bool:
    return bool(re.search(r"[a-z]{2}", normaliser(texte)))


def decouper(url: str):
    try:
        return urlsplit(url or "")
    except ValueError:
        return None


# Identifiant technique à points, sans chiffre (com.siemens.splm.clientfx.tcui.xrt.showObject) :
# c'est un nom d'écran, pas une valeur, même s'il est long.
MOTIF_IDENTIFIANT_POINTE = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+")
# Clés dont la valeur est toujours un numéro d'objet, même sans chiffre (uid=gRTJnuFxIOqA).
MOTIF_CLE_IDENTIFIANT = re.compile(
    r"(?:^|_)(?:id|uid|oid|guid|key|token|ref)$|^id"
    # texte cherché : chaque recherche serait sinon un « nouvel écran » (et le mot cherché, une donnée)
    r"|^(?:q|query|search|recherche|rech|text|texte|keyword|keywords|motcle|mot_cle|term|terms|filter|filtre|s)$",
    re.IGNORECASE,
)


def _segment_variable(segment: str) -> bool:
    if re.fullmatch(r"[a-z]{1,4}\d", segment):
        return False  # v1, v2, api2, ptc1 : une version ou un module, pas un numéro
    if re.search(r"\d", segment):
        return True
    return len(segment) > 24 and not MOTIF_IDENTIFIANT_POINTE.fullmatch(segment)


def _valeur_modele(cle: str, valeur: str) -> str:
    # Windchill : OR:wt.part.WTPart:123 -> le genre d'objet est gardé, pas son numéro
    m = re.fullmatch(r"((?:OR|VR):[A-Za-z_][\w.]*:)\d+", valeur)
    if m:
        return m.group(1) + "{id}"
    if not valeur or _segment_variable(valeur) or MOTIF_CLE_IDENTIFIANT.search(cle):
        return "{}"
    return valeur


def _requete_modele(paires) -> str:
    return "&".join(sorted(f"{k}={_valeur_modele(k, v)}" for k, v in paires))


def modele_url(url: str) -> str:
    """Adresse sans le serveur ni les valeurs variables : /plans/1234?onglet=2&module=plans
    -> /plans/{id}?module=plans&onglet={}. Deux adresses qui ne diffèrent que par ces
    valeurs montrent le même modèle d'écran ; module=plans et module=composants, non.
    Les portails à route après « # » (#/ecran?uid=...) sont traités de la même façon."""
    m = decouper(url)
    if m is None:
        return ""
    if m.scheme not in ("http", "https", "file"):
        return f"{m.scheme}:"
    chemin = "/".join("{id}" if _segment_variable(s) else s for s in m.path.split("/"))
    requete = _requete_modele(parse_qsl(m.query, keep_blank_values=True))
    fragment = m.fragment
    if fragment:
        route, _, requete_fragment = fragment.partition("?")
        if "=" in route and not route.startswith("/") and not requete_fragment:
            fragment = _requete_modele(p.partition("=")[::2] for p in route.split("&"))
        else:
            fragment = "/".join("{id}" if _segment_variable(s) else s for s in route.split("/"))
            if requete_fragment:
                fragment += "?" + _requete_modele(p.partition("=")[::2] for p in requete_fragment.split("&"))
    return chemin + (f"?{requete}" if requete else "") + (f"#{fragment}" if fragment else "")


def _modele_sans_requete(modele: str) -> str:
    """« /plans/{id}?onglet=general » -> « /plans/{id} » ; « /app#/plan/{id}?tab=x » -> « /app#/plan/{id} »."""
    chemin, _, fragment = (modele or "").partition("#")
    route = fragment.split("?")[0]
    if "=" in route and not route.startswith("/"):
        route = ""
    return chemin.split("?")[0] + (f"#{route}" if route else "")


def adresse_action(url: str) -> Optional[str]:
    """Raison pour laquelle une adresse ressemble à une action (…/supprimer, ?action=del), ou None."""
    m = decouper(url)
    if m is None:
        return "adresse illisible"
    mot = mot_interdit(re.sub(r"[/_.\-]+", " ", m.path))
    if mot:
        return f"« {mot} » dans l'adresse"
    for cle, valeur in parse_qsl(m.query, keep_blank_values=True):
        mot = mot_interdit(re.sub(r"[_.\-]+", " ", cle), re.sub(r"[_.\-]+", " ", valeur))
        if mot:
            return f"« {mot} » dans l'adresse"
        if normaliser(cle) in CLES_ACTION and valeur and normaliser(valeur) not in VALEURS_LECTURE:
            return f"paramètre « {cle}={valeur} »"
    return None


def adresse_dangereuse(url: str) -> Optional[str]:
    """Comme adresse_action, avec le vocabulaire du filet de la visite : …/plans/5/delete oui,
    …/plans/5/telecharger non."""
    m = decouper(url)
    if m is None:
        return None
    mot = mot_garde(re.sub(r"[/_.\-]+", " ", m.path))
    if mot:
        return mot
    for cle, valeur in parse_qsl(m.query, keep_blank_values=True):
        mot = mot_garde(re.sub(r"[_.\-]+", " ", cle)) or \
            (mot_garde(re.sub(r"[_.\-]+", " ", valeur)) if normaliser(cle) in CLES_ACTION else None)
        if mot:
            return mot
    return None


def sans_fragment(url: str) -> str:
    return (url or "").split("#", 1)[0]


def masquer(texte: str) -> str:
    """Tout mot contenant un chiffre, et les adresses mail, sont masqués."""
    texte = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", str(texte or ""))
    # « (tranche 3) » -> « (tranche #) » : les parenthèses et crochets autour restent
    return re.sub(r"[^\s()\[\]{}«»]*\d[^\s()\[\]{}«»]*", "#", texte)


TYPES_CHAMPS = {
    "text": "texte", "number": "nombre", "checkbox": "case à cocher", "radio": "choix unique",
    "password": "mot de passe", "search": "recherche", "file": "fichier", "email": "mail",
    "tel": "téléphone", "datetime-local": "date et heure", "month": "mois", "url": "adresse web",
}


def type_champ(type_brut: str) -> str:
    return TYPES_CHAMPS.get(type_brut, type_brut)


# Indicateurs de chargement (« Veuillez patienter », voile, roue) : un écran qui les montre n'est
# pas encore prêt. Une seule liste pour la lecture des écrans et pour la visite guidée.
INDICATEURS_CHARGEMENT = [
    "[aria-busy=true]", "[role=progressbar]", ".blockUI", ".blockOverlay", ".ui-blockui", ".x-mask", ".loading",
    ".spinner", ".loader", ".chargement", "#chargement", "#loading", ".ui-widget-overlay", ".k-loading-mask",
    ".sapUiLocalBusyIndicator",
]

# ---------------------------------------------------------------------- lecture d'un écran
# Outils communs aux deux scripts : la description d'un élément doit être calculée
# EXACTEMENT de la même façon au moment de la lecture et au moment du clic.
JS_OUTILS = r"""
  const vis = e => {
    if (!e || !e.isConnected || !e.getBoundingClientRect) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const court = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n || 80);
  const idOk = id => !!id && /^[A-Za-z_][\w-]*$/.test(id) && !/\d{3,}/.test(id) && id.length <= 40;
  // texte d'un libellé ou d'une entête SANS les listes et champs qu'il contient (options = données)
  const texteSeul = n => {
    const c = n.cloneNode(true);
    c.querySelectorAll('select, option, optgroup, datalist, input, textarea, button, script, style').forEach(x => x.remove());
    return court(c.textContent, 80);
  };
  const libelle = e => {
    if (idOk(e.id)) {
      try { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return [texteSeul(l), 'label']; } catch (err) {}
    }
    const p = e.closest('label'); if (p) return [texteSeul(p), 'label'];
    const al = e.getAttribute('aria-label'); if (al) return [court(al), 'aria'];
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = document.getElementById(lb.split(' ')[0]); if (t) return [texteSeul(t), 'aria']; }
    const th = e.closest('th'); if (th) return [texteSeul(th), 'entete'];
    const prev = e.previousElementSibling;
    if (prev && ['LABEL', 'SPAN', 'TD', 'TH', 'DIV', 'B', 'STRONG'].includes(prev.tagName)) {
      const t = texteSeul(prev); if (t.length < 60) return [t, 'voisin'];
    }
    const ph = e.getAttribute('placeholder'); if (ph) return [court(ph), 'exemple'];
    return ['', ''];
  };
  const chemin = e => {
    const parts = [];
    let n = e;
    while (n && n.nodeType === 1 && n !== document.body && n !== document.documentElement) {
      if (idOk(n.id)) {
        let unique = false;
        try { unique = document.querySelectorAll('#' + CSS.escape(n.id)).length === 1; } catch (err) {}
        if (unique) { parts.unshift('#' + CSS.escape(n.id)); return parts.join(' > '); }
      }
      let k = 1, s = n;
      while ((s = s.previousElementSibling)) if (s.tagName === n.tagName) k++;
      parts.unshift(n.tagName.toLowerCase() + ':nth-of-type(' + k + ')');
      n = n.parentElement;
    }
    return 'body > ' + parts.join(' > ');
  };
  const FENETRE = '[role=dialog], [role=alertdialog], dialog[open], [aria-modal=true], .modal, .modal-dialog, ' +
                  '.swal2-popup, .ui-dialog, .popup, .popin, .lightbox, .blockUI';
  const dansFenetre = e => {
    if (e.closest(FENETRE)) return true;
    // voile maison : un ancêtre fixe qui couvre une grande partie de l'écran
    for (let n = e.parentElement; n && n !== document.body; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.position === 'fixed') {
        const r = n.getBoundingClientRect();
        if (r.width * r.height > 0.3 * innerWidth * innerHeight) return true;
      }
    }
    return false;
  };
  // arborescence et fil d'Ariane : souvent des données (dossiers, projets) ; menu latéral : navigation
  const ARBRE = '[role=tree], .tree, .breadcrumb, [aria-label*=readcrumb], [aria-label*="Fil d"]';
  const LATERAL = 'aside, .sidebar, .side-bar, .sidenav, .side-nav';
  const zone = e => {
    if (dansFenetre(e)) return 'fenetre';
    if (e.getAttribute('role') === 'tab' || e.closest('[role=tablist]')) return 'onglet';
    if (e.closest('tbody tr, [role=row]')) return 'tableau';
    if (e.closest(ARBRE) || e.getAttribute('role') === 'treeitem') return 'arbre';
    if (e.closest(LATERAL)) return 'lateral';
    if (e.closest('nav, [role=navigation], [role=menu], [role=menubar], header, .menu, .navbar, .nav')) return 'menu';
    return 'page';
  };
  const conteneurDe = (e, z) => {
    if (z === 'tableau') return e.closest('tbody, [role=rowgroup], table, [role=grid], [role=table]') || e.parentElement;
    if (z === 'arbre') return e.closest(ARBRE) || e.parentElement;
    if (z === 'lateral') return e.closest(LATERAL) || e.parentElement;
    return null;
  };
  const SELECTION = 'a[href], button, input[type=submit], input[type=button], input[type=image], input[type=reset], ' +
                    '[role=button], [role=tab], [role=menuitem], [role=link], [role=treeitem], [onclick], summary';
  const EXCLUS = 'input:not([type=submit]):not([type=button]):not([type=image]):not([type=reset]), select, option, ' +
                 'textarea, label, [role=checkbox], [role=radio], [role=switch], [role=option], [contenteditable=true]';
  // composants web (UI5, Vaadin, ServiceNow...) : leurs éléments sont dans des « racines fantômes »
  let racinesCache = null;
  const racines = () => {
    if (racinesCache) return racinesCache;
    const r = [document];
    for (let i = 0; i < r.length && r.length < 300; i++) {
      for (const x of r[i].querySelectorAll('*')) if (x.shadowRoot) r.push(x.shadowRoot);
    }
    return (racinesCache = r);
  };
  const tous = sel => { const res = []; for (const r of racines()) r.querySelectorAll(sel).forEach(x => res.push(x)); return res; };
  const INDICATEURS_CHARGEMENT = """ + json.dumps(INDICATEURS_CHARGEMENT) + r""";
  // compte de l'utilisateur, avatar, profil : son nom n'est jamais repris
  const PERSO = '[class*=user i], [class*=account i], [class*=profil i], [class*=avatar i], [id*=user i], ' +
                '[id*=account i], [id*=profil i], [aria-label*=compte i], [aria-label*=account i], [aria-label*=profil i]';
  const FERMER = '[class*=close i], [class*=fermer i], [aria-label*=close i], [aria-label*=fermer i], ' +
                 '[title*=close i], [title*=fermer i], .fa-times, .fa-xmark, .k-i-x, .k-i-close, [class*=remove i], ' +
                 '.bi-x, .bi-x-lg, .bi-x-circle, .pi-times, .pi-times-circle, .lucide-x, [class*=icon-x i], ' +
                 '[data-dismiss], [data-bs-dismiss], .glyphicon-remove, img[alt*=ferm i], img[alt*=close i], ' +
                 'img[title*=ferm i], img[title*=close i], img[src*=close i], img[src*=fermer i], use[href*=close i], ' +
                 'use[href$="-x"], use[href$="#x"], [data-icon*=close i], [data-icon*=times i], [data-icon*=xmark i], ' +
                 '[data-feather=x], [data-lucide=x], [data-icon=x]';
  // classe d'icône « croix » : ti-x, bx-x, la-times, feather-x, icon-cross, mdi-close...
  const CLASSE_CROIX = /(^|[-_])(x|times|close|xmark|cross)$/i;
  const classesDe = i => {
    const c = typeof i.className === 'string' ? i.className : ((i.className && i.className.baseVal) || '');
    return c.split(/\s+/).filter(Boolean);
  };
  // une croix dans l'élément : classe, info-bulle, image, ou glyphe (×, ligature « close » des icônes Material)
  const croix = x => {
    if (!x) return false;
    try { if (x.querySelector(FERMER)) return true; } catch (err) {}
    for (const i of [x].concat(Array.from(x.querySelectorAll('span, i, button, a, mat-icon, svg, img, use')).slice(0, 12))) {
      if (i !== x && classesDe(i).some(c => CLASSE_CROIX.test(c))) return true;
      try {
        const lien = i.tagName.toLowerCase() === 'use' ? (i.getAttribute('href') || i.getAttribute('xlink:href') || '') : '';
        if (/(close|fermer|times|xmark|cross|[#-]x)$/i.test(lien)) return true;
      } catch (err) {}
      if (i !== x && ['×', '✕', '✖', '⨯', 'x', 'close', 'clear', 'cancel'].includes((i.textContent || '').trim().toLowerCase())) return true;
      try {  // croix dessinée par le style (« ::after { content: '×' } »)
        for (const pseudo of ['::after', '::before']) {
          if (/[×✕✖]/.test(getComputedStyle(i, pseudo).content || '')) return true;
        }
      } catch (err) {}
    }
    return false;
  };
  const cache = new Map();
  const indexes = new Map();
  const indexLigne = tr => {
    const parent = tr.parentElement;
    if (!parent) return -1;
    let m = indexes.get(parent);
    if (!m) { m = new Map(); Array.prototype.forEach.call(parent.children, (x, i) => m.set(x, i)); indexes.set(parent, m); }
    const i = m.get(tr);
    return i === undefined ? -1 : i;
  };
  const rangDans = (conteneur, e) => {
    let liste = cache.get(conteneur);
    if (!liste) { liste = Array.from(conteneur.querySelectorAll(SELECTION)).filter(x => !x.matches(EXCLUS)); cache.set(conteneur, liste); }
    return liste.indexOf(e);
  };
  const decrire = e => {
    const tag = e.tagName.toLowerCase();
    let type = (e.getAttribute('type') || '').toLowerCase();
    const formulaire = e.form || null;
    if (tag === 'button' && !['submit', 'button', 'reset'].includes(type)) type = formulaire ? 'submit' : 'button';
    const soumet = !!formulaire && (type === 'submit' || type === 'image');
    const methode = soumet ? (e.getAttribute('formmethod') || formulaire.getAttribute('method') || 'get').toLowerCase() : '';
    const z = zone(e);
    let ligne = -1, rang = -1, conteneur = '';
    const cont = conteneurDe(e, z);
    if (cont) {
      if (z === 'tableau') {
        const tr = e.closest('tbody tr, [role=row]');
        ligne = tr ? indexLigne(tr) : -1;
        rang = tr ? (tr === e ? 0 : Array.from(tr.querySelectorAll(SELECTION)).filter(x => !x.matches(EXCLUS)).indexOf(e) + 1) : -1;
      } else {
        ligne = rangDans(cont, e);
      }
      conteneur = chemin(cont);
    }
    const ombre = e.getRootNode && e.getRootNode() !== document;
    let perso = false, fermable = false;
    try {
      perso = !!e.closest(PERSO) ||
        (tag === 'a' && /(^|[\/_.?=&-])(user|users|utilisateur|profil|profile|compte|account|moi|me|mon-?compte|my-?account)([\/_.?=&-]|$)/i.test(e.getAttribute('href') || ''));
    } catch (err) {}
    try {
      // onglet de document (un par plan ouvert) : une croix DANS l'onglet, ou dans son enveloppe si
      // elle ne contient que lui. Aussi pour les onglets Bootstrap, vus comme un menu.
      const p = e.parentElement;
      const commeOnglet = z === 'onglet' || (z === 'menu' && !!e.closest('.nav-tabs, .nav-pills, [role=tablist]'));
      fermable = commeOnglet && (croix(e) || (!!p && p.querySelectorAll('[role=tab], a').length <= 1 && croix(p)));
    } catch (err) {}
    return {
      ombre: ombre, perso: perso, fermable: fermable,
      texte: court(tag === 'input' ? (e.value || '') : (e.innerText || ''), 80),
      aria: court(e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('alt') || '', 80),
      tag: tag, type: type, role: e.getAttribute('role') || '', id: e.id || '',
      href: tag === 'a' ? (e.getAttribute('href') || '') : '',
      href_absolu: (tag === 'a' && e.href) ? String(e.href) : '',
      telechargement: tag === 'a' && e.hasAttribute('download'),
      desactive: !!e.disabled || e.getAttribute('aria-disabled') === 'true',
      zone: z, ligne: ligne, rang: rang, conteneur: conteneur,
      soumet: soumet, methode: methode, selecteur: ombre ? '' : chemin(e),
      testid: court(e.getAttribute('data-testid') || e.getAttribute('data-test') || e.getAttribute('name') || '', 60),
    };
  };
"""

JS_ECRAN = r"""
([exemples, maxCibles]) => {
""" + JS_OUTILS + r"""
  // bandeaux posés par le robot lui-même : jamais lus comme une partie de l'écran
  const robot = e => !!(e.closest && e.closest('[data-autoweb]'));
  const titres = [];
  tous('h1, h2, h3, [role=heading]').forEach(h => { if (vis(h) && !robot(h) && titres.length < 12) titres.push(court(h.innerText, 100)); });
  const champs = [];
  tous('input, select, textarea, [contenteditable=true]').forEach(e => {
    const tag = e.tagName.toLowerCase();
    const type = (e.getAttribute('type') || '').toLowerCase();
    if (type === 'hidden' || ['submit', 'button', 'reset', 'image'].includes(type) || !vis(e) || robot(e) || champs.length >= 200) return;
    const tr = e.closest('tbody tr');
    if (tr && indexLigne(tr) >= exemples) return;
    const [lib, source] = libelle(e);
    champs.push({
      libelle: lib, source: source, nom: e.id || e.getAttribute('name') || '',
      type: tag === 'select' ? 'liste' : tag === 'textarea' ? 'texte long' : (e.isContentEditable && tag !== 'input') ? 'texte riche' : (type || 'text'),
      obligatoire: !!e.required, lecture_seule: !!(e.readOnly || e.disabled),
      nb_options: tag === 'select' ? e.options.length : 0,
      options: tag === 'select' ? Array.from(e.options).slice(0, 15).map(o => court(o.text, 60)) : [],
      dans_tableau: !!tr, zone: zone(e),
    });
  });
  // fiche en lecture : « Titre : ... », <dt>, entête de ligne <th> suivie de sa valeur <td>.
  // Seuls les LIBELLÉS sont lus, jamais les valeurs.
  const infos = [];
  const ajouterInfo = t => {
    t = court(t, 60).replace(/\s*:\s*$/, '');
    if (t && t.split(' ').length <= 3 && !/["«»“”]/.test(t) && !infos.includes(t) && infos.length < 60) infos.push(t);
  };
  // <dt> : une vraie fiche en a peu ; une longue liste <dl> est une liste d'objets
  tous('dl').forEach(l => {
    const dts = Array.from(l.querySelectorAll(':scope > dt, :scope > div > dt'));
    if (dts.length <= 25) dts.forEach(x => { if (vis(x) && !robot(x) && !x.querySelector('a, button')) ajouterInfo(x.textContent || ''); });
  });
  // entête de ligne : seulement dans une vraie fiche « libellé | valeur » (tableau SANS entêtes de
  // colonnes) et pour les premières lignes ; dans une liste de résultats, ce sont des noms d'objets
  tous('table').forEach(t => {
    // une liste de résultats a des entêtes de colonnes (thead, ou une première ligne tout en th) : pas une fiche
    const premiere = t.querySelector('tr');
    const entetesEnLigne = !!premiere && premiere.children.length > 1 && Array.from(premiere.children).every(c => c.tagName === 'TH');
    if (!vis(t) || robot(t) || entetesEnLigne || t.querySelector('thead th, [role=columnheader], th[scope=col]')) return;
    t.querySelectorAll('tr > th:first-child').forEach(x => {
      const tr = x.parentElement;
      if (tr && indexLigne(tr) < 30 && !x.querySelector('a, button') && x.nextElementSibling && x.nextElementSibling.tagName === 'TD') ajouterInfo(x.textContent || '');
    });
  });
  // « Titre : » suivi de sa valeur : le texte de l'élément LUI-MÊME, sans rien d'imbriqué
  tous('label, span, b, strong, td, div').forEach(x => {
    if (infos.length >= 60 || x.children.length || robot(x)) return;
    const t = (x.textContent || '').trim();
    if (t.length > 1 && t.length < 40 && /:\s*$/.test(t) && x.nextElementSibling && vis(x)) ajouterInfo(t);
  });
  const chargement = [];
  for (const sel of INDICATEURS_CHARGEMENT) {
    if (tous(sel).some(x => vis(x) && !robot(x) && !x.querySelector('input') && x.getBoundingClientRect().width * x.getBoundingClientRect().height > 400)) chargement.push(sel);
  }
  const tableaux = [];
  tous('table, [role=grid]').forEach(t => {
    if (!vis(t) || t.parentElement.closest('table')) return;
    let entetes = Array.from(t.querySelectorAll('thead th, [role=columnheader]')).map(texteSeul);
    if (!entetes.length) {
      // première ligne TOUTE en entêtes (au moins 2) ; un <th> seul en tête de ligne est un nom d'objet
      const tr = t.querySelector('tr');
      if (tr && tr.children.length > 1 && Array.from(tr.children).every(c => c.tagName === 'TH')) entetes = Array.from(tr.children).map(texteSeul);
    }
    tableaux.push({ entetes: entetes.slice(0, 40), lignes: t.querySelectorAll('tbody tr, [role=row]').length });
  });
  const cibles = [];
  let tronque = false;
  for (const e of tous(SELECTION)) {
    const tr = e.closest('tbody tr, [role=row]');
    if (tr && indexLigne(tr) >= exemples) continue;   // une ligne ressemble aux autres : les premières suffisent
    if (e.matches(EXCLUS) || !vis(e) || robot(e)) continue;
    if (cibles.length >= maxCibles) { tronque = true; break; }
    cibles.push(decrire(e));
  }
  const cadres = Array.from(document.querySelectorAll('iframe, frame')).filter(vis).map(f => String(f.src || ''));
  const motDePasse = !!tous('input[type=password]').find(vis);
  const identifiant = !!Array.from(document.querySelectorAll('input[type=email], input[autocomplete=username], ' +
      'input[name*=user i], input[name*=login i], input[id*=user i], input[id*=login i], input[name*=identifiant i]')).find(vis);
  const fenetre = !!Array.from(document.querySelectorAll(FENETRE)).find(vis);
  return {
    url: location.href, titre: court(document.title, 120), titres: titres, champs: champs,
    tableaux: tableaux, cibles: cibles, tronque: tronque, cadres: cadres,
    mot_de_passe: motDePasse, identifiant: identifiant, fenetre: fenetre,
    infos: infos, chargement: chargement, ombre: racines().length > 1,
  };
}
"""

# Vérifie ET clique dans le même instant : si l'élément n'est plus exactement celui qui a
# été approuvé, rien n'est cliqué. Le clic est envoyé à l'élément lui-même (pas à un
# point de l'écran) : ce qui est posé dessus ou dedans n'est jamais touché.
JS_CLIC = r"""
([selecteur, attendu]) => {
""" + JS_OUTILS + r"""
  let e = null;
  try { e = document.querySelector(selecteur); } catch (err) { return 'sélecteur illisible'; }
  if (!e) return 'absent';
  if (e.matches(EXCLUS) || !vis(e)) return 'plus cliquable';
  const d = decrire(e);
  for (const k of Object.keys(attendu)) {
    if (String(d[k]) !== String(attendu[k])) return 'changé (' + k + ')';
  }
  const options = { bubbles: true, cancelable: true, view: window };
  e.dispatchEvent(new MouseEvent('mouseover', options));
  e.dispatchEvent(new MouseEvent('mousedown', options));
  e.dispatchEvent(new MouseEvent('mouseup', options));
  e.click();
  return 'ok';
}
"""

# L'écran est prêt quand presque plus rien ne bouge et qu'aucun indicateur de chargement
# n'est visible (voile « Veuillez patienter », aria-busy, barre de progression).
JS_CALME = r"""
(maximum) => new Promise(fini => {
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const aire = e => { const r = e.getBoundingClientRect(); return r.width * r.height; };
  const charge = () => {
    if (document.readyState !== 'complete') return true;
    for (const e of document.querySelectorAll('[aria-busy=true], [role=progressbar], .blockUI, .blockOverlay')) if (vis(e)) return true;
    for (const e of document.querySelectorAll('.loading, .spinner, .loader, .chargement, #chargement, #loading')) {
      if (vis(e) && !e.querySelector('input') && aire(e) > 400) return true;
    }
    for (const e of document.querySelectorAll('div, span, p, h1, h2, h3')) {
      if (e.children.length) continue;
      const t = (e.textContent || '').trim().toLowerCase();
      if (t.length < 40 && /^(chargement|loading|veuillez patienter|please wait|patientez)(\s+en cours)?\s*(\.\.\.|…)?$/.test(t) && vis(e)) return true;
    }
    return false;
  };
  const activite = [];
  let courant = 0;
  const obs = new MutationObserver(l => { courant += l.length; });
  obs.observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
  const debut = Date.now();
  const tic = setInterval(() => {
    activite.push(courant); courant = 0;
    const calme = activite.length >= 3 && activite.slice(-3).every(n => n <= 2);
    const fin = Date.now() - debut > maximum;
    if (fin || (calme && !charge())) { clearInterval(tic); obs.disconnect(); fini(!fin); }
  }, 200);
})
"""

# Injecté dans chaque page : l'impression ouvrirait une fenêtre qui bloque tout.
JS_NEUTRALISER = r"""
window.print = function () {}; window.showModalDialog = function () {};
(() => {
  // bandeau rassurant, dans la fenêtre principale : il ne capte aucun clic
  if (window !== window.top) return;
  const poser = () => {
    if (!document.documentElement || document.getElementById('__autoweb_lecture')) return;
    const b = document.createElement('div');
    b.id = '__autoweb_lecture';
    b.setAttribute('data-autoweb', '1');
    b.setAttribute('style', 'position:fixed;bottom:12px;left:12px;z-index:2147483647;background:#1d4ed8;' +
      'color:#fff;font:600 12px/1.3 system-ui,-apple-system,Arial;padding:8px 11px;border-radius:6px;' +
      'box-shadow:0 2px 10px rgba(0,0,0,.35);pointer-events:none;max-width:320px;opacity:.93');
    b.textContent = 'Robot en LECTURE SEULE : il regarde et note. Tout envoi de données vers le portail est bloqué.';
    document.documentElement.appendChild(b);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', poser); else poser();
})();
"""


# ---------------------------------------------------------------------- envois et technologie
# Ce que le portail ENVOIE dit comment il fonctionne (formulaire ASP.NET, JSF, GraphQL, SOAP,
# API JSON) : on note la nature de l'envoi et des noms techniques, JAMAIS les valeurs.
COMMANDES_GRILLE = {"page", "sort", "select", "edit", "delete", "update", "cancel", "insert", "new"}
CLES_WEBFORMS = {
    "__VIEWSTATE", "__VIEWSTATEGENERATOR", "__VIEWSTATEENCRYPTED", "__EVENTVALIDATION", "__EVENTTARGET",
    "__EVENTARGUMENT", "__LASTFOCUS", "__SCROLLPOSITIONX", "__SCROLLPOSITIONY", "__PREVIOUSPAGE", "__ASYNCPOST",
    "__VIEWSTATEFIELDCOUNT",
}


# Mots de développeur : un nom de clé, de contrôle ou d'opération fait uniquement de ces mots
# (et de préfixes courts comme btn, txt, ctl) est un nom de code ; un autre mot (« Flamanville »,
# « jdupont ») peut être une donnée : il n'est pas repris.
VOCABULAIRE_CODE = set("""
main content contents placeholder holder header footer body page pages master form forms panel pnl grid grids table
tables row rows col cols column columns cell list liste lists item items view views vue mode search recherche
rechercher chercher query requete filter filters filtre filtres sort sorting order orderby tri trier page paging
pagination size taille limit offset start end first last count total from to date dates type types id ids key keys
code codes ref reference references num numero number name nom names title titre label libelle text texte value
valeur values description designation desc comment commentaire status statut state etat version versions indice
revision revisions plan plans composant composants component components document documents doc docs file files
fichier fichiers piece pieces part parts item article articles projet project projects site sites famille family
category categorie categories fabricant manufacturer supplier fournisseur owner proprietaire author auteur user users
utilisateur login session token csrf nonce lang language langue locale format export import print download upload
submit button bouton btn link lien menu menus tab tabs onglet onglets tree arbre node nodes action actions event
events target argument source partial ajax execute render behavior faces viewstate validation generator async post
get set load read fetch find lookup show display detail details info infos properties property attribute
attributes data field fields select selected selection check checked option options choice radio input output
result results resultats resultat criteria criteres advanced avance simple quick rapide new nouveau save enregistrer
delete supprimer remove update edit modifier create creer add ajouter copy copier duplicate dupliquer cancel annuler
close fermer ok yes no oui non next previous suivant precedent back retour home accueil default index portal portail
app application service services api rest json xml soap rpc graphql odata batch server serveur client module modules
widget widgets container content dialog modal popup window frame iframe control controls ctl cmd txt lbl lnk ddl chk
rb cb img pic hdn hf gv rpt uc tb dd sel inp fld frm mat mdc ng item apply ok innovator default ptc wt apex
q id pk db uid oid ts dt fk num nb qte qty ui ux js css url uri ko fr en es it nl x y z i j k n s v el btn bt lb ib
lst tbl dlg pop pnl sec hd ft nav col row idx pos rel src dst min max avg sum str int bool obj arr fn cfg env
""".split())


def nom_de_code(nom: Any) -> bool:
    """Vrai si le nom n'est fait que de mots de développeur (voir VOCABULAIRE_CODE)."""
    brut = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(nom or ""))
    morceaux = [m for m in re.split(r"[^A-Za-z]+", brut) if m]
    if not morceaux:
        return False
    # chaque morceau doit être un mot de développeur connu, même court : « FLA », « JD » (code de site,
    # initiales) ne passent pas
    return all(normaliser(m) in VOCABULAIRE_CODE for m in morceaux)


def nom_technique(texte: Any, longueur: int = 40) -> str:
    """Identifiant technique (nom de contrôle, d'opération, de clé) : chiffres masqués ; tout
    ce qui ressemble à du texte libre (espaces, @, ponctuation) est remplacé par « ? »."""
    texte = re.sub(r"\d+", "#", str(texte or ""))[:longueur]
    if not texte:
        return ""
    return texte if re.fullmatch(r"[A-Za-z_$#][\w$:.#-]*", texte) else "?"


# Fins d'adresse gardées : programmes (…/Plans.aspx) et mots techniques génériques. Tout le
# reste (…/Flamanville) peut être un nom de site, de projet ou de client : remplacé par « … ».
MOTIF_FIN_TECHNIQUE = re.compile(
    r"[A-Za-z_][\w.-]{0,38}\.(?:aspx|asmx|ashx|axd|svc|jsp|jspx|jsf|faces|xhtml|do|action|php|cgi|pl|json|xml)"
    r"|(?:graphql|api|rest|rpc|jsonrpc|soap|odata|batch|search|query|find|list|get|read|load|fetch|save|update"
    r"|delete|remove|create|insert|execute|exec|upload|download|export|import|login|logout|auth|token|session"
    r"|services?|servlet|dispatch|command|handler|data|lookup|filter|count|details?|\$batch)",
    re.IGNORECASE,
)


def _fin_adresse(url: str) -> str:
    """Dernier morceau du chemin s'il est technique (…/graphql, …/InnovatorServer.aspx) ;
    jamais le serveur ni le reste de l'adresse. Un nom de fichier ou de page qui n'est pas un
    nom de programme connu (…/PL-FLA-00123.json, …/Projet_Penly.aspx) devient « …/*.json »."""
    m = decouper(url)
    dernier = (m.path.rstrip("/").rsplit("/", 1)[-1] if m else "") or ""
    if not MOTIF_FIN_TECHNIQUE.fullmatch(dernier):
        return "…"
    radical, point, extension = dernier.rpartition(".")
    if point and radical:
        return f"…/{dernier}" if nom_de_code(radical) and not re.search(r"\d", radical) else f"…/*.{extension}"
    return f"…/{dernier}"


# Premiers mots d'une opération de LECTURE (en plus des mots de consultation français).
VERBES_LECTURE = PREMIERS_MOTS_LECTURE | {
    "get", "search", "find", "load", "read", "query", "list", "fetch", "retrieve", "lookup", "show", "count",
    "select", "browse", "render", "rows", "page", "paging", "pagination", "sort", "sorting", "filtering",
    "tabchange", "rowselect", "rowtoggle", "expand", "describe", "lister", "lire", "charger", "obtenir",
}
PREFIXES_CONTROLES = ("btn", "lnk", "lb", "ib", "img", "cmd", "bt", "link", "button", "menu", "mnu", "tab")


def _mots(nom: str) -> List[str]:
    """« ctl00$Main$btnSupprimerPlan » -> ['supprimer', 'plan'] (dernier morceau, sans préfixe)."""
    dernier = re.split(r"[$:./]", str(nom or ""))[-1]
    dernier = re.sub(r"([a-z])([A-Z])", r"\1 \2", dernier)
    mots = re.findall(r"[a-z]+", normaliser(dernier.replace("_", " ").replace("-", " ")))
    while mots and mots[0] in PREFIXES_CONTROLES and len(mots) > 1:
        mots = mots[1:]
    return mots


def sens_operation(nom: str, motif: Optional[Any] = None) -> str:
    """« lecture probable », « écriture probable » ou "" d'après un nom d'opération ou de contrôle.
    Ce n'est qu'un indice : le programme du serveur fait ce qu'il veut. `motif` : vocabulaire
    d'action à utiliser (par défaut, celui de l'exploration automatique)."""
    mots = _mots(nom)
    if not mots:
        return ""
    if (motif.search(" ".join(mots)) if motif is not None else mot_interdit(" ".join(mots))):
        return "écriture probable"
    if mots[0] in VERBES_LECTURE or mots[:2] == ["perform", "search"]:
        return "lecture probable"
    return ""


def _avec_sens(texte: str, sens: str) -> str:
    return f"{texte} [{sens}]" if sens else texte


def _clefs(noms: List[str], n: int = 8) -> str:
    """Noms de clés ou de champs, seulement s'ils sont des noms de code ; les autres sont comptés."""
    propres = sorted({nom_technique(k, 30) for k in noms if nom_de_code(k)} - {"", "?"})
    autres = len({k for k in noms if not nom_de_code(k)})
    texte = ", ".join(propres[:n]) + ("…" if len(propres) > n else "")
    if autres:
        texte += (" + " if texte else "") + f"{autres} autre(s), noms non repris"
    return texte or "?"


def _code(nom: Any, longueur: int = 60) -> str:
    """Nom de contrôle ou d'opération, repris seulement s'il est un nom de code."""
    return nom_technique(nom, longueur) if nom_de_code(nom) else ("(nom non repris)" if nom else "")


def classer_envoi(methode: str, url: str, type_contenu: str, corps: Optional[str],
                  soap_action: str = "", entetes: Optional[Dict[str, str]] = None, motif: Optional[Any] = None) -> str:
    """« POST …/Plans.aspx (formulaire ASP.NET WebForms, cible ctl#$Main$btnChercher) [lecture probable] ».
    Seuls la nature de l'envoi et des NOMS techniques sont gardés, jamais les valeurs."""
    entetes = {k.lower(): v for k, v in (entetes or {}).items()}
    methode = (entetes.get("x-http-method-override") or entetes.get("x-http-method") or methode).upper()[:10]
    fin = _fin_adresse(url)
    ct_complet = (type_contenu or entetes.get("content-type", "") or "")
    ct = ct_complet.split(";")[0].strip().lower()
    corps = (corps or "")[:200000]
    debut = corps.lstrip()[:1]
    m_url = decouper(url)
    chemin = m_url.path if m_url else ""

    # Teamcenter Active Workspace : …/JsonRestServices/<Bibliothèque-AAAA-MM-Service>/<opération>
    m = re.search(r"/JsonRestServices/([^/]+)/([^/?]+)", chemin)
    if m:
        return _avec_sens(f"{methode} …/JsonRestServices/{_code(m.group(1))}/{_code(m.group(2))}"
                          " (Teamcenter SOA)", sens_operation(m.group(2), motif))
    # SharePoint : lecture de liste ou recherche envoyées en POST
    m = re.search(r"/_api/.*?/?(RenderListDataAsStream|postquery|GetItems|ProcessQuery)\b", chemin, re.IGNORECASE)
    if m:
        lecture = m.group(1).lower() in ("renderlistdataasstream", "postquery", "getitems")
        return _avec_sens(f"{methode} …/_api/…/{m.group(1)} (SharePoint)", "lecture probable" if lecture else "")
    if ct == "text/x-gwt-rpc" or "x-gwt-permutation" in entetes:
        champs = corps.split("|")
        interface = champs[5].rsplit(".", 1)[-1] if len(champs) > 6 else ""
        operation = champs[6] if len(champs) > 6 else ""
        return _avec_sens(f"{methode} {fin} (GWT-RPC {_code(interface)}.{_code(operation)})",
                          sens_operation(operation, motif))
    if ct == "multipart/mixed" or (chemin.endswith("$batch") and ct.startswith("multipart")):
        verbes = re.findall(r"(?m)^(GET|POST|PUT|PATCH|MERGE|DELETE) ", corps)
        changeset = "changeset" in corps.lower()
        lecture = bool(verbes) and set(verbes) == {"GET"} and not changeset
        detail = ", ".join(f"{verbes.count(v)} {v}" for v in sorted(set(verbes))) or "?"
        return _avec_sens(f"{methode} …/$batch (OData, {detail})",
                          "lecture probable" if lecture else ("écriture probable" if verbes else ""))
    if ct == "application/graphql":
        return _classer_graphql(methode, fin, [{"query": corps}], motif)
    if "x-www-form-urlencoded" in ct or (not ct and "=" in corps[:300] and debut not in "{[<"):
        paires = parse_qsl(corps, keep_blank_values=True)
        cles = [k for k, _ in paires]
        valeurs = dict(paires)
        if CLES_WEBFORMS & set(cles):
            cible = valeurs.get("__EVENTTARGET") or ""
            if not cible:  # bouton qui envoie : son nom est une clé du formulaire
                cible = next((k for k in reversed(cles) if k not in CLES_WEBFORMS and "$btn" in k.lower()), "")
            # commande standard des grilles : Page$2, Sort$Nom, Select$3, Delete$1... (sans ce qui suit $)
            # seulement les commandes standard : ailleurs, l'argument est une valeur (sGravelines...)
            commande = (valeurs.get("__EVENTARGUMENT") or "").split("$", 1)[0]
            commande = commande if commande.lower() in COMMANDES_GRILLE else ""
            partiel = ", partiel" if "__ASYNCPOST" in valeurs or "x-microsoftajax" in entetes else ""
            sens = {"page": "lecture probable", "sort": "lecture probable", "select": "lecture probable",
                    "delete": "écriture probable", "update": "écriture probable", "insert": "écriture probable",
                    "new": "écriture probable"}.get(commande.lower(), "") or sens_operation(cible, motif)
            texte = (f"{methode} {fin} (formulaire ASP.NET WebForms{partiel}, cible {_code(cible) or '?'}"
                     + (f", commande {commande}" if commande else "") + ")")
            return _avec_sens(texte, sens)
        faces = next((k for k in cles if k.endswith("faces.ViewState")), "")
        if faces:
            prefixe = faces.rsplit(".", 1)[0]
            source = valeurs.get(f"{prefixe}.source") or ""
            evenement = valeurs.get(f"{prefixe}.behavior.event") or ""
            evenement = evenement if re.fullmatch(r"[A-Za-z]{2,30}", evenement) else ""
            ajax = ", ajax" if valeurs.get(f"{prefixe}.partial.ajax") or "faces-request" in entetes else ""
            drapeaux = [k.rsplit("_", 1)[-1] for k in cles if re.search(r"_(pagination|sorting|filtering)$", k)]
            sens = ("lecture probable" if evenement.lower() in ("page", "sort", "filter", "tabchange", "rowselect",
                                                                  "rowtoggle", "expand", "collapse") or drapeaux
                    else sens_operation(source, motif))
            texte = (f"{methode} {fin} (formulaire JSF{ajax}, composant {_code(source) or '?'}"
                     + (f", événement {evenement}" if evenement else "")
                     + (f", {'/'.join(sorted(set(drapeaux)))}" if drapeaux else "") + ")")
            return _avec_sens(texte, sens)
        if "p_request" in valeurs and ("p_flow_id" in valeurs or "wwv_flow" in chemin):
            return f"{methode} {fin} (Oracle APEX)"
        return f"{methode} {fin} (formulaire, champs : {_clefs(cles)})"
    if "json" in ct or debut in ("{", "["):
        try:
            donnees = json.loads(corps)
        except ValueError:
            donnees = None
        lots = [d for d in (donnees if isinstance(donnees, list) else [donnees]) if isinstance(d, dict)]
        if lots:
            premier = lots[0]
            if "query" in premier or "operationName" in premier or "graphql" in url.lower():
                return _classer_graphql(methode, fin, lots, motif)
            if "method" in premier and ("jsonrpc" in premier or "params" in premier):
                return _avec_sens(f"{methode} {fin} (JSON-RPC {_code(premier.get('method'))})",
                                  sens_operation(str(premier.get("method") or ""), motif))
            if isinstance(premier.get("requests"), list):  # OData 4 : lot en JSON
                verbes = [str(r.get("method", "")).upper() for r in premier["requests"] if isinstance(r, dict)]
                lecture = bool(verbes) and set(verbes) == {"GET"}
                detail = ", ".join(f"{verbes.count(v)} {nom_technique(v)}" for v in sorted(set(verbes))) or "?"
                return _avec_sens(f"{methode} {fin} (OData, lot JSON : {detail})",
                                  "lecture probable" if lecture else "écriture probable")
            return f"{methode} {fin} (JSON, clés : {_clefs(list(premier))})"
        return f"{methode} {fin} (JSON)"
    if "xml" in ct or debut == "<":
        action = soap_action or entetes.get("soapaction", "")
        m = re.search(r"action=\"?([^\";]+)", ct_complet)  # SOAP 1.2 : l'action est dans le type de contenu
        if not action and m:
            action = m.group(1)
        operation = _code(action.strip('"').rsplit("/", 1)[-1].rsplit("#", 1)[-1])
        if not operation:
            m = re.search(r"<(?:\w+:)?Body[^>]*>\s*<(?:\w+:)?([A-Za-z_][\w.-]*)", corps)
            operation = _code(m.group(1)) if m else ""
        actions = sorted({_code(a) for a in re.findall(r"<Item\b[^>]*\baction=[\"']([\w]+)[\"']", corps)} - {""})
        types = sorted({_code(t.replace(" ", "_"))
                        for t in re.findall(r"<Item\b[^>]*\btype=[\"']([\w ]{1,40})[\"']", corps)} - {""})
        if actions:  # Aras : chaque élément dit ce qu'il fait
            sens = "lecture probable" if set(a.lower() for a in actions) <= {"get"} else "écriture probable"
            return _avec_sens(f"{methode} {fin} (SOAP/XML {operation or '?'}, éléments {'/'.join(types[:4]) or '?'} : "
                              f"action {'/'.join(actions[:4])})", sens)
        return _avec_sens(f"{methode} {fin} (SOAP/XML{' ' + operation if operation else ''})", sens_operation(operation, motif))
    if "multipart" in ct:
        return f"{methode} {fin} (envoi de formulaire ou de fichier)"
    return f"{methode} {fin} ({nom_technique(ct.replace('/', '_'), 40) or 'sans contenu'})"


def _classer_graphql(methode: str, fin: str, lots: List[Dict[str, Any]], motif: Optional[Any] = None) -> str:
    """Type de CHAQUE opération (query / mutation) : le texte de la requête n'est jamais gardé."""
    genres, operations = set(), []
    for lot in lots:
        texte = str(lot.get("query") or "")
        trouves = re.findall(r"(?m)^\s*(query|mutation|subscription)\b", re.sub(r"#[^\n]*", "", texte))
        if trouves:
            genres.update(trouves)
        elif re.search(r"(?m)^\s*\{", texte):
            genres.add("query")  # document abrégé « { plans { id } } » : une lecture
        else:
            genres.add("requête enregistrée")
        nom = _code(lot.get("operationName") or "")
        if nom and nom not in operations:
            operations.append(nom)
    if "mutation" in genres:
        sens = "écriture probable"
    elif genres <= {"query"}:
        sens = "lecture probable"
    else:
        sens = sens_operation(operations[0], motif) if operations else ""
    texte = f"{methode} {fin} (GraphQL {'/'.join(sorted(genres))}{' ' + ', '.join(operations[:3]) if operations else ''})"
    return _avec_sens(texte, sens)


def classer_requete(requete: Any, motif: Optional[Any] = None) -> str:
    """classer_envoi() pour une requête Playwright, sans jamais lever."""
    try:
        entetes = requete.headers or {}
    except Exception:  # noqa: BLE001
        entetes = {}
    try:
        corps = requete.post_data
    except Exception:  # noqa: BLE001 - contenu binaire
        corps = None
    try:
        return classer_envoi(requete.method.upper(), requete.url, entetes.get("content-type", ""), corps,
                             entetes.get("soapaction", ""), entetes, motif)
    except Exception:  # noqa: BLE001
        return f"{requete.method.upper()} …"


# Plateformes reconnues d'après les adresses appelées par la page (jamais l'adresse elle-même).
TECHNO_ADRESSES = (
    (re.compile(r"/JsonRestServices/", re.I), "Siemens Teamcenter (SOA)"),
    (re.compile(r"InnovatorServer\.aspx|/Client/X-salt=", re.I), "Aras Innovator"),
    (re.compile(r"/Windchill/", re.I), "PTC Windchill"),
    (re.compile(r"/sap/opu/odata|/sap/bc/ui5_ui5/|/sap/bc/ui2/flp|/sap/bc/gui/sap/its/webgui", re.I), "SAP"),
    (re.compile(r"/\$batch\b", re.I), "OData"),
    (re.compile(r"/_api/|/_vti_bin/|/_layouts/15/", re.I), "SharePoint"),
    (re.compile(r"/graphql\b", re.I), "GraphQL"),
    (re.compile(r"/resources/v1/modeler/|/3dspace/|/3ddashboard/", re.I), "3DEXPERIENCE / ENOVIA"),
    (re.compile(r"/dctm-rest/|/D2/|/webtop/", re.I), "OpenText Documentum"),
    (re.compile(r"[/.](?:javax|jakarta)\.faces\.resource/|/rfRes/", re.I), "JSF"),
    (re.compile(r"/(?:WebResource|ScriptResource)\.axd", re.I), "ASP.NET WebForms"),
    (re.compile(r"/wwv_flow|[?&]p=\d+:\d+", re.I), "Oracle APEX"),
    (re.compile(r"/AutodeskDM/|/AutodeskTC/", re.I), "Autodesk Vault"),
    (re.compile(r"/PW_WSG/|/ws/v2\.\d+/repositories/Bentley\.PW", re.I), "Bentley ProjectWise"),
    (re.compile(r"/Agile/PLMServlet", re.I), "Oracle Agile PLM"),
    (re.compile(r"/REST/objects|/vnext/", re.I), "M-Files"),
)


def techno_depuis_adresse(url: str) -> List[str]:
    return [nom for motif, nom in TECHNO_ADRESSES if motif.search(url or "")]


def techno_depuis_entetes(entetes: Dict[str, str]) -> List[str]:
    """Serveur et outil déclarés par le portail dans ses réponses : noms seulement, sans version."""
    noms = []
    for cle, prefixe in (("server", "serveur "), ("x-powered-by", ""), ("x-aspnet-version", "")):
        valeur = str((entetes or {}).get(cle) or "")
        if not valeur:
            continue
        if cle == "x-aspnet-version":
            noms.append("ASP.NET")
            continue
        for motif, produit in PRODUITS_SERVEUR:
            if motif.search(valeur) and prefixe + produit not in noms:
                noms.append(prefixe + produit)
    return noms


# Seuls des noms de produits connus sont repris des réponses du serveur : le reste peut être
# le nom d'une machine ou d'un site (« srv-plm-flamanville01 »).
PRODUITS_SERVEUR = tuple((re.compile(m, re.IGNORECASE), p) for m, p in (
    (r"microsoft-iis|\biis\b", "Microsoft IIS"), (r"apache-coyote|tomcat", "Apache Tomcat"),
    (r"^apache\b(?!-coyote)", "Apache"), (r"nginx", "nginx"), (r"jetty", "Jetty"), (r"weblogic", "WebLogic"),
    (r"websphere|\bibm_http", "WebSphere"), (r"kestrel", "Kestrel (ASP.NET Core)"), (r"asp\.net", "ASP.NET"),
    (r"\bphp\b", "PHP"), (r"express", "Express (Node.js)"), (r"servlet|\bjsp\b", "Java Servlet/JSP"),
    (r"\bjsf\b|mojarra|myfaces", "JSF"), (r"sharepoint", "SharePoint"), (r"wildfly|jboss|undertow", "WildFly/JBoss"),
    (r"glassfish|payara", "GlassFish/Payara"), (r"openresty", "OpenResty"), (r"envoy", "Envoy"),
    (r"cloudflare", "Cloudflare"), (r"\bbig-?ip\b|^f5\b", "F5 BIG-IP"), (r"sap netweaver|sap web", "SAP NetWeaver"),
    (r"oracle-http|oracle http|\bohs\b", "Oracle HTTP Server"),
    (r"oracle-application-server|oracle application server", "Oracle Application Server"),
    (r"microsoft-httpapi", "Microsoft HTTP API"), (r"wordpress", "WordPress"), (r"drupal", "Drupal"),
    (r"joomla", "Joomla"), (r"zope|plone", "Plone"), (r"lotus|domino", "HCL Domino"),
))


COOKIES_TECHNO = (
    (re.compile(r"^JSESSIONID$"), "Java (JSESSIONID)"),
    (re.compile(r"^ASP\.NET_SessionId$"), "ASP.NET"),
    (re.compile(r"^\.AspNetCore\."), "ASP.NET Core"),
    (re.compile(r"^PHPSESSID$"), "PHP"),
    (re.compile(r"^(FedAuth|rtFa)$"), "SharePoint"),
    (re.compile(r"^(SAP_SESSIONID_|MYSAPSSO2$|sap-usercontext$)"), "SAP"),
    (re.compile(r"^CASTGC$"), "connexion CAS (3DEXPERIENCE ?)"),
    (re.compile(r"^MSISAuth"), "connexion ADFS (Microsoft)"),
    (re.compile(r"^(connect\.sid)$"), "Node.js"),
    (re.compile(r"^(csrftoken|sessionid)$"), "Django"),
    (re.compile(r"^laravel_session$"), "PHP Laravel"),
)


def techno_depuis_cookies(noms: List[str]) -> List[str]:
    """Plateforme d'après les NOMS des cookies du portail (leurs valeurs ne sont jamais lues)."""
    trouves = []
    for motif, nom in COOKIES_TECHNO:
        if any(motif.search(n) for n in noms) and nom not in trouves:
            trouves.append(nom)
    return trouves


# Plateformes et outils reconnus de l'intérieur de la page : des noms de produits, rien d'autre.
JS_TECHNO = r"""
() => {
  const t = [];
  const w = window, d = document;
  const chemin = (location.pathname + location.hash).toLowerCase(), hote = location.hostname.toLowerCase();
  // un nom de produit doit être un mot entier de l'adresse : « /listeplans » n'est pas EPLAN
  const mot = nom => new RegExp('(^|[/.#?=&_-])' + nom + '([/.#?=&_-]|$)');
  const ou = re => re.test(chemin) || re.test(hote);
  const a = s => { try { return !!d.querySelector(s); } catch (e) { return false; } };
  // existence seulement : ces objets contiennent parfois l'identifiant de l'utilisateur, jamais lus
  if (a('input[name=__VIEWSTATE]') || typeof w.__doPostBack === 'function' || (w.Sys && w.Sys.WebForms)) t.push('ASP.NET WebForms');
  if (a('input[name$="faces.ViewState"]') || w.jsf || (w.faces && w.faces.ajax)) t.push('JSF');
  if (w.PrimeFaces) t.push('PrimeFaces');
  if (w.RichFaces || w.A4J) t.push('RichFaces');
  if (w.ice && w.ice.ace) t.push('ICEfaces');
  if (a('[ng-version]')) t.push('Angular');
  if (w.angular && w.angular.version) t.push('AngularJS');
  if (w.React || a('[data-reactroot]') || Array.from(d.querySelectorAll('body > div')).some(e =>
      e._reactRootContainer || Object.keys(e).some(k => k.startsWith('__react')))) t.push('React');
  if (w.Vue || w.__VUE__ || a('[data-v-app]') || Array.from(d.querySelectorAll('body > div')).some(e => e.__vue__ || e.__vue_app__)) t.push('Vue');
  if (w.Ext && (w.Ext.getVersion || w.Ext.version)) t.push('ExtJS');
  if ((w.sap && w.sap.ui) || a('#sap-ui-bootstrap') || ou(/\/sap\/(bc|opu)\//)) t.push('SAP UI5 / Fiori');
  if (w._spPageContextInfo || a('#s4-workspace') || ou(/\/_layouts\/15\//)) t.push('SharePoint');
  if ((w.apex && w.apex.item) || a('#pFlowId')) t.push('Oracle APEX');
  if (w.Vaadin || w.vaadin) t.push('Vaadin');
  if (w.Wicket) t.push('Wicket');
  if (w.Blazor) t.push('Blazor');
  if (w.mx && w.mx.session) t.push('Mendix');
  if (w.OutSystems) t.push('OutSystems');
  if (w.dojo) t.push('Dojo');
  if (w.jQuery) t.push('jQuery');
  if (w.kendo) t.push('Kendo UI');
  if (w.DevExpress || w.ASPx) t.push('DevExpress');
  if (w.Telerik || w.$telerik) t.push('Telerik');
  if (w.GWT || w.__gwt_activeModules || a('#__gwt_historyFrame')) t.push('GWT');
  if (ou(/\/windchill\//) || /#ptc1\//.test(chemin) || a('input[name=CSRF_NONCE]') || w.PTC) t.push('PTC Windchill');
  if (/com\.siemens\.splm\.clientfx/.test(chemin) || ou(/(^|\/)awc(\/|$)/) || w.afxWeakImport || w.afxDynamicImport) t.push('Siemens Teamcenter Active Workspace');
  if (ou(/\/3dspace|\/3ddashboard|\/enovia|\/3dpassport|emxnavigator/) || w.UWA) t.push('3DEXPERIENCE / ENOVIA');
  if (ou(/\/client\/x-salt=|innovatorserver|\/innovator\//) || w.aras || w.ArasModules) t.push('Aras Innovator');
  if (ou(/plmservlet/) || (ou(mot('agile')) && ou(/servlet|plm/))) t.push('Oracle Agile PLM');
  if (ou(/\/autodesktc\/|\/autodeskdm\//)) t.push('Autodesk Vault');
  if (ou(mot('projectwise')) || ou(/pw_wsg/)) t.push('Bentley ProjectWise');
  if (ou(/\/d2\/|\/webtop\/|dctm-rest/) || ou(mot('documentum'))) t.push('OpenText Documentum');
  if (ou(mot('m-files')) || w.MFiles) t.push('M-Files');
  if (ou(mot('comos(web)?'))) t.push('Siemens COMOS');
  if (ou(mot('eplan')) || /(^|\.)eview\.eplan\./.test(hote)) t.push('EPLAN');
  if (ou(/service-?now/) || w.g_form) t.push('ServiceNow');
  const gen = d.querySelector('meta[name=generator]');
  // générateur de la page : seulement un produit connu (le reste peut être le nom de l'intranet)
  if (gen && gen.content) {
    const g = gen.content.toLowerCase();
    for (const [motif, produit] of [[/wordpress/, 'WordPress'], [/drupal/, 'Drupal'], [/joomla/, 'Joomla'],
        [/sharepoint/, 'SharePoint'], [/microsoft/, 'Microsoft'], [/plone/, 'Plone'], [/typo3/, 'TYPO3'],
        [/confluence/, 'Confluence'], [/liferay/, 'Liferay'], [/sitecore/, 'Sitecore'], [/wix/, 'Wix'],
        [/oracle/, 'Oracle'], [/sap/, 'SAP'], [/mendix/, 'Mendix'], [/outsystems/, 'OutSystems']]) {
      if (motif.test(g)) { t.push('générateur : ' + produit); break; }
    }
  }
  if (d.querySelector('frameset')) t.push('cadres (frameset)');
  return t;
}
"""


# Version des cartes : le choix 9 n'envoie que des cartes faites avec les filtres actuels.
VERSION_CARTE = 19
# Mots qui peuvent suivre le verbe d'un bouton sans rien dire des données (« Voir le détail »).
MOTS_GENERIQUES = set("""
le la les l du de des d un une au aux en et ou a sur pour par tout tous toute toutes ce cette ces mon ma mes
pdf excel csv word xml zip fichier fichiers fiche fiches plan plans composant composants detail details liste
listes selection element elements document documents version versions revision revisions ligne lignes resultat
resultats recherche avancee simple page suivante precedente nomenclature historique arborescence donnees
""".split())
# Nom de personne : « Jean DUPONT », « DUPONT Jean », « J. Dupont », « M. Dupont », « Dupont, Jean ».
MOTIF_PERSONNE = re.compile(
    r"^(?:[A-ZÀ-Ý][a-zà-ÿ'’]+(?:-[A-ZÀ-Ý][a-zà-ÿ'’]+)?\s+[A-ZÀ-Ý]{2,}(?:[\s-][A-ZÀ-Ý]{2,})*"
    r"|[A-ZÀ-Ý]{2,}(?:[\s-][A-ZÀ-Ý]{2,})*\s+[A-ZÀ-Ý][a-zà-ÿ'’-]+"
    r"|[A-ZÀ-Ý]\.\s*[A-ZÀ-Ý][a-zà-ÿ'’-]+"
    r"|(?:M\.|Mme|Mlle|Mr|Mrs|Ms|Dr)\s+\S+.*"
    r"|[A-ZÀ-Ý][a-zà-ÿ'’-]+,\s*[A-ZÀ-Ý][a-zà-ÿ'’-]+)$"
)


# Prénoms courants (sans accents, minuscules) : « Marie Martin » est une personne, « Mes plans » non.
PRENOMS = set("""
jean pierre michel philippe alain nicolas christophe patrick daniel bernard eric laurent frederic stephane david
olivier christian julien thierry sebastien francois pascal thomas didier jacques gerard dominique vincent andre
alexandre antoine guillaume maxime romain kevin mathieu matthieu anthony jerome franck sylvain yves claude
bruno fabrice cedric ludovic arnaud benoit emmanuel serge denis herve regis joel gilles lionel remi hugo lucas louis
paul arthur gabriel raphael leo jules adam nathan theo enzo mehdi karim mohamed ahmed rachid samir yannick loic
quentin florian clement benjamin xavier jonathan jeremy mickael michael damien adrien aurelien baptiste bastien
alexis valentin corentin dylan tristan victor martin simon axel mathis noah ethan tom timothee gaetan gregory
fabien johan jordan morgan steven teddy william yoann yohan cyril cyrille marcel roger rene robert henri georges
maurice raymond lucien fernand gaston albert andre emile edouard etienne felix hubert jean-baptiste marc
marie nathalie isabelle sylvie catherine francoise christine monique valerie sandrine sophie veronique nicole
patricia celine stephanie aurelie julie caroline laure laurence emilie camille claire anne helene martine brigitte
chantal agnes elodie audrey melanie virginie severine delphine sabine florence corinne pauline lea manon chloe emma
sarah laura marion lucie charlotte mathilde juliette alice ines jade louise zoe fatima nadia sonia karine magali
beatrice genevieve josiane odile evelyne danielle michele jacqueline cecile oceane gaelle yasmine amandine
jessica justine margaux morgane noemie ophelie oriane romane solene tiphaine vanessa alexandra anais estelle
eloise fanny gwenaelle helena ingrid jeanne josephine lucile marine mylene nina rose valentine yasmina amelie
ludivine myriam nadege perrine rachel regine sylviane therese yvette yvonne colette denise simone suzanne
marc-antoine jean-pierre jean-claude jean-marc jean-luc jean-francois jean-michel jean-louis jean-paul
marie-claire marie-christine marie-france anne-marie anne-sophie marie-laure marie-pierre pierre-yves
john james robert william richard joseph charles mary jennifer linda elizabeth susan jessica karen nancy lisa
betty sandra ashley donna emily michelle carol amanda melissa deborah stephen steven andrew kenneth joshua brian
george edward ronald timothy jason jeffrey ryan jacob gary peter hans klaus jurgen stefan andreas giuseppe
marco luca giovanni carlos jose juan miguel antonio manuel ana maria
""".split())


# Mots d'interface souvent écrits avec une majuscule (« Where Used », « Bill of Materials »,
# « Part Number », « Mes Documents ») : cette majuscule ne signale pas un nom propre.
MOTS_INTERFACE = set("""
where used bill materials material tasks task requests request changes change notices notice orders order
history structure related relations relation attachments attachment my all recent recents favorites workspace
workspaces reports report dashboard bord settings parametres preferences help aide about overview summary resume
general information informations proprietes attributs lifecycle cycle vie workflow processes process approvals
approbation approbations notes notifications notification messages message inbox boite reception assemblies
assembly drawings drawing objects object products product libraries library folders folder viewer visualisation
preview apercu iterations iteration results queries saved team teams members member groups group roles role people
personnes creation modification created modified updated by par of the and for in on at with sans avec number
numbers owner owners creator context organization organisation container location emplacement quantity quantite
unit units unite level niveau line position checked locked time heure weight poids length longueur width largeur
height hauteur voltage tension power puissance reference category classification class classe parent child
children primary secondary principal principale effective released release approved draft work progress cours
used uses where-used bom plm erp sap cao cad dao ged eco ecr ecn ecm mrp oem hta htb bt pdf id management gestion
links liens viewed recently recemment quick access acces control controle admin administration tools outils
collaboration compare comparaison comparison search searches home tree view explorer navigator utilise utilisee
utilises emploi cas lies liees lien associes associees composition dossier dossiers equivalences equivalents
documentation proprietes caracteristiques caracteristique technique techniques contexte suivi audit securite droits
acces visualiseur miniature vignette apercu signatures signature validations cycle etats etat revisions
""".split())


def _mot_interface(mot: str) -> bool:
    m = normaliser(mot).strip(".:,;()[]{}'’«»\"!?")
    connus = MOTS_GENERIQUES | VOCABULAIRE_CODE | MOTS_INTERFACE

    def connu(x: str) -> bool:  # « Searches », « Requêtes » : le pluriel d'un mot connu aussi
        return x in connus or (x.endswith("s") and x[:-1] in connus) or (x.endswith("es") and x[:-2] in connus)

    return not m or bool(re.search(r"\d", m)) or connu(m) or all(connu(x) for x in m.split("-") if x)


def nom_propre_dedans(texte: str) -> bool:
    """« Résultats pour Tricastin », « Site Penly », « Hinkley Point C » : un mot à majuscule après le
    premier, hors des mots d'interface (les libellés s'écrivent « Date de création », « Where Used ») ;
    ou un nom de personne."""
    mots = str(texte or "").split()
    return ressemble_a_une_personne(texte) or any(
        m[:1].isupper() and not _mot_interface(m) and (len(m) > 1 or i == len(mots) - 1)
        for i, m in enumerate(mots[1:], 1))


def ressemble_a_une_personne(texte: str) -> bool:
    texte = str(texte or "").strip()
    # une ligature d'icône devant (« person Marie Martin ») ou une ponctuation (« (Marie Martin) »)
    texte = re.sub(r"^(?:person|account_circle|account|user|face|badge)\s+", "", texte)
    texte = texte.strip("()[]{}«»\"' .,;:-")
    if MOTIF_PERSONNE.match(texte):
        return True
    brut = texte.split()
    mots = normaliser(texte).split()
    if not 2 <= len(mots) <= 4:
        return False
    # « Marie Martin », « Jean-Pierre Durand », « Martin Marie » : un prénom connu, tous les mots
    # commençant par une majuscule (« Mark as read » n'est pas une personne)
    prenom = any(m in PRENOMS or all(x in PRENOMS for x in m.split("-")) for m in mots)
    return prenom and all(b[:1].isupper() for b in brut)


# ---------------------------------------------------------------------- modèle de la carte
@dataclass
class Action:
    """Un pas pour atteindre un écran : ouvrir une adresse, ou cliquer sur un élément."""

    type: str  # "aller" | "clic"
    url: str = ""
    selecteur: str = ""
    texte: str = ""
    zone: str = ""
    ligne: int = -1
    attendu: Dict[str, Any] = field(default_factory=dict)
    partage: str = ""  # libellé sans données, pour la carte à partager

    def libelle(self) -> str:
        if self.type == "aller":
            return f"ouvrir {modele_url(self.url)}"
        if self.zone == "tableau":
            return f"ligne {self.ligne + 1} du tableau"
        return self.texte or "(élément sans texte)"


@dataclass
class Ecran:
    id: str
    url: str
    modele: str
    signature: str
    chemin: List[Action]
    titre: str = ""
    titres: List[str] = field(default_factory=list)
    champs: List[Dict[str, Any]] = field(default_factory=list)
    tableaux: List[Dict[str, Any]] = field(default_factory=list)
    cibles: List[Dict[str, Any]] = field(default_factory=list)
    cadres: List[str] = field(default_factory=list)
    tronque: bool = False
    fenetre: bool = False
    profondeur: int = 0
    resultats: Dict[str, str] = field(default_factory=dict)
    cadre: bool = False  # contenu d'un cadre (iframe, frameset) de la page, lu à part
    infos: List[str] = field(default_factory=list)  # libellés d'une fiche en lecture (sans valeurs)
    chargement: List[str] = field(default_factory=list)  # indicateurs de chargement vus
    ombre: bool = False  # composants web (racines fantômes)
    etape: str = ""  # visite guidée : ce que l'utilisateur montrait à ce moment-là


@dataclass
class Limites:
    ecrans: int = 150
    profondeur: int = 6
    minutes: float = 60.0
    delai_ms: int = 500
    exemples: int = 2  # écrans visités par modèle d'adresse, lignes essayées par tableau
    max_cibles: int = 400  # éléments cliquables lus par écran


class ArretExploration(Exception):
    pass


def _norm_chiffres(texte: str) -> str:
    return re.sub(r"\d+", "#", normaliser(texte))


def signature(lecture: Dict[str, Any]) -> str:
    """Empreinte de la STRUCTURE d'un écran : ni données, ni menus changeants (récents,
    arborescence), ni chiffres. Deux fiches de composants différents ont la même empreinte."""
    onglets = sorted({_norm_chiffres(c["texte"] or c["aria"]) for c in lecture["cibles"] if c["zone"] == "onglet"})
    boutons = sorted({_norm_chiffres(c["texte"] or c["aria"]) for c in lecture["cibles"]
                      if c["zone"] in ("page", "fenetre") and c["tag"] != "a"})
    champs = sorted({(_norm_chiffres(c["libelle"]) if c["source"] in ("label", "aria", "entete") else "", c["type"])
                     for c in lecture["champs"] if not c["dans_tableau"] and c["zone"] not in ("arbre", "lateral")})
    tableaux = sorted((tuple(_norm_chiffres(e) for e in t["entetes"]), t["lignes"] > 0) for t in lecture["tableaux"])
    brut = json.dumps([modele_url(lecture["url"]), onglets, boutons, champs, tableaux, lecture.get("fenetre", False)],
                      ensure_ascii=False)
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------- explorateur
class Explorateur:
    def __init__(
        self,
        nav: Navigateur,
        dossier: Path,
        limites: Optional[Limites] = None,
        interactif: bool = True,
        connexion: Optional[Callable[[Page], None]] = None,
    ) -> None:
        self.nav = nav
        self.dossier = Path(dossier)
        self.limites = limites or Limites()
        self.interactif = interactif
        self.connexion = connexion  # tests : se connecter sans intervention
        self.ecrans: List[Ecran] = []
        self._par_signature: Dict[str, Ecran] = {}
        self._infos_vues: Dict[Tuple[str, str], set] = {}  # (modèle, libellé) -> adresses où il a été lu
        self._visites_modele: Dict[str, int] = {}
        self._clics_globaux: Dict[str, int] = {}
        self.transitions: List[Dict[str, str]] = []
        self.bloquees: List[Tuple[str, str]] = []  # (méthode, modèle d'adresse) : envois empêchés
        # nature des envois (bloqués ici ; observés pendant une visite), sans aucune valeur
        self.envois: Dict[str, int] = {}
        self.techno: List[str] = []  # plateformes et outils reconnus
        self.mode = "exploration"
        self.diagnostic: List[Tuple[str, str]] = []  # réglages de connexion du poste (oui / non)
        self.websockets = 0
        self.telechargements: List[str] = []
        self.externes: List[str] = []
        self.formulaires_bloques = 0
        self.essais = 0
        self.hote = ""
        self.depart = ""
        self.garde_active = False
        self.arret = ""
        self.complet = False
        self._debut = 0.0
        self._relogins = 0
        self._echecs_consecutifs = 0
        self._calme_max = 8000
        self._delais_depasses = 0
        self._urls_sures: Set[str] = set()
        self._nouvelles_pages: List[Page] = []
        self._fenetres_a_voir: List[str] = []
        self._interrompu: List[int] = []
        self._depuis_sauvegarde = 0
        self.url_demandee = ""

    # ------------------------------------------------------------------ sécurité réseau
    def _garde(self, route: Any) -> None:
        """Toute requête qui enverrait des données, ou dont l'adresse ressemble à une action,
        est bloquée avant de partir. Exception : les adresses que le robot ouvre lui-même
        (page de départ, liens déjà vérifiés)."""
        try:
            requete = route.request
            methode = requete.method.upper()
            self._techno_adresse(requete.url)
            raison = ""
            if methode not in METHODES_LECTURE:
                m = decouper(requete.url)
                if not (methode == "POST" and m is not None and MOTIF_RETOUR_CONNEXION.search(m.path)):
                    raison = methode
            elif requete.resource_type not in RESSOURCES_STATIQUES:
                if not (requete.is_navigation_request() and sans_fragment(requete.url) in self._urls_sures):
                    raison = adresse_action(requete.url) or ""
            if self.garde_active and raison:
                self.bloquees.append((methode, modele_url(requete.url)))
                self._noter_envoi(classer_requete(requete) if methode not in METHODES_LECTURE
                                  else f"{methode} {_fin_adresse(requete.url)} (adresse d'action)")
                journal.debug("Requête bloquée (%s) : %s %s", raison, methode, modele_url(requete.url))
                route.abort()
            else:
                route.continue_()
        except Exception as e:  # noqa: BLE001 - un gestionnaire ne doit jamais lever
            journal.debug("Garde : %s", e)

    def _noter_envoi(self, nature: str) -> None:
        self.envois[nature] = self.envois.get(nature, 0) + 1

    def _techno_adresse(self, url: str) -> None:
        for nom in techno_depuis_adresse(url):
            if nom not in self.techno:
                self.techno.append(nom)

    def _reponse(self, reponse: Any) -> None:
        """Serveur et outil déclarés dans les réponses des pages du portail."""
        try:
            if reponse.request.resource_type != "document":
                return
            site = getattr(self, "site", "") or site_de(self.depart or self.url_demandee)
            if site and site_de(reponse.url) != site:
                return
            for nom in techno_depuis_entetes(reponse.headers):
                if nom not in self.techno:
                    self.techno.append(nom)
        except Exception as e:  # noqa: BLE001 - un gestionnaire ne doit jamais lever
            journal.debug("Réponse non lue : %s", e)

    def _techno_cookies(self) -> None:
        """Plateforme d'après les noms des cookies du portail (valeurs jamais gardées)."""
        site = getattr(self, "site", "") or site_de(self.depart or self.url_demandee)
        try:
            noms = [c.get("name", "") for c in self.nav.contexte.cookies()
                    if not site or str(c.get("domain", "")).lstrip(".").endswith(site)]
        except Exception:  # noqa: BLE001
            return
        for nom in techno_depuis_cookies(noms):
            if nom not in self.techno:
                self.techno.append(nom)

    def _noter_techno(self, cadre: Any) -> None:
        """Plateforme du portail (Windchill, WebForms, Angular...) : lue sur chaque nouvel écran."""
        try:
            trouves = cadre.evaluate(JS_TECHNO) or []
        except Exception:  # noqa: BLE001
            return
        for nom in trouves:
            if isinstance(nom, str) and nom not in self.techno:
                self.techno.append(nom)

    def _garde_websocket(self, ws: Any) -> None:
        """Aucune connexion WebSocket ne part vers le serveur (rien n'est relayé)."""
        self.websockets += 1

    def _telechargement(self, telechargement: Any) -> None:
        try:
            self.telechargements.append(telechargement.suggested_filename)
            telechargement.cancel()
        except Exception:  # noqa: BLE001
            pass

    def _nouvelle_page(self, page: Page) -> None:
        if page is not self.nav.page:
            self._nouvelles_pages.append(page)

    # ------------------------------------------------------------------ déroulement
    def explorer(self, url: str) -> None:
        import signal

        def sur_ctrl_c(*_: Any) -> None:
            if self._interrompu:  # second Ctrl+C : sortie immédiate, la carte est sauvée
                try:
                    self.arret = "arrêt immédiat (second Ctrl+C)"
                    self.enregistrer()
                finally:
                    os._exit(130)
            self._interrompu.append(1)
            print(f"\n{S.ATTENTION} Arrêt demandé : le robot termine l'action en cours puis s'arrête "
                  "(Ctrl+C encore une fois pour arrêter tout de suite).", flush=True)

        try:
            ancien = signal.signal(signal.SIGINT, sur_ctrl_c)
        except (ValueError, OSError):
            ancien = None
        try:
            self._explorer(url)
        finally:
            if ancien is not None:
                signal.signal(signal.SIGINT, ancien)

    def _explorer(self, url: str) -> None:
        contexte = self.nav.contexte
        page = self.nav.page_courante()
        contexte.route("**/*", self._garde)
        if hasattr(contexte, "route_web_socket"):
            try:
                contexte.route_web_socket(re.compile(".*"), self._garde_websocket)
            except Exception as e:  # noqa: BLE001
                journal.debug("WebSocket non contrôlés : %s", e)
        contexte.add_init_script(JS_NEUTRALISER)
        contexte.on("page", self._nouvelle_page)
        contexte.on("response", self._reponse)
        page.on("download", self._telechargement)
        self._debut = time.monotonic()
        self.url_demandee = url
        self._urls_sures.add(sans_fragment(url))
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:  # noqa: BLE001
            raise ErreurAutoweb(f"Impossible d'ouvrir {url} : {str(e).splitlines()[0]}")
        self._attendre(page)
        self._connexion(page, premiere_fois=True)
        page = self.nav.page_courante()
        try:
            page.evaluate(JS_NEUTRALISER)
        except Exception:  # noqa: BLE001
            pass
        m = decouper(page.url)
        self.hote = m.netloc if m else ""
        self.depart = page.url
        self._urls_sures.add(sans_fragment(page.url))
        self.garde_active = True
        premier = self._observer(page, [Action("aller", url=page.url, partage="page de départ")], 0)
        if premier is None:
            raise ErreurAutoweb("La page de départ n'a pas pu être lue.")
        self._visites_modele[premier.modele] = 1
        a_traiter = [premier]
        try:
            while a_traiter:
                ecran = a_traiter.pop(0)
                if ecran.profondeur < self.limites.profondeur:
                    for cible in self._cibles_a_essayer(ecran):
                        self._verifier_limites()
                        nouveau = self._essayer_sans_planter(ecran, cible)
                        if nouveau is not None:
                            a_traiter.append(nouveau)
                            self._sauvegarde_periodique()
                for adresse in self._fenetres_a_voir:  # fenêtres ouvertes par l'outil : vues à part
                    self._verifier_limites()
                    nouveau = self._essayer_sans_planter(ecran, self._pseudo_lien(adresse, "fenêtre"))
                    if nouveau is not None:
                        a_traiter.append(nouveau)
                self._fenetres_a_voir = []
            self.complet = True
            self.arret = "tout ce qui était accessible sans rien modifier a été vu"
        except ArretExploration as e:
            self.arret = str(e)
        except KeyboardInterrupt:
            self.arret = "arrêt demandé (Ctrl+C)"
        finally:
            self.garde_active = False
            if self.formulaires_bloques >= 3:
                self.complet = False
                self.arret += (" ; attention : ce portail navigue en envoyant des formulaires, bloqués par "
                               "sécurité : la carte est incomplète")
            try:
                contexte.unroute("**/*", self._garde)
            except Exception:  # noqa: BLE001
                pass
            self._techno_cookies()
            self.enregistrer()

    def _essayer_sans_planter(self, ecran: Ecran, cible: Dict[str, Any]) -> Optional[Ecran]:
        """Une erreur sur un élément ne doit pas arrêter toute l'exploration."""
        try:
            return self._essayer(ecran, cible)
        except (ArretExploration, KeyboardInterrupt):
            raise
        except Exception as e:  # noqa: BLE001
            if navigateur_ferme(e):
                raise ArretExploration("le navigateur a été fermé")
            ecran.resultats[self._cle(cible)] = "erreur pendant l'essai"
            journal.debug("Erreur sur %s : %s", self._cle(cible), e)
            return None

    def _verifier_limites(self) -> None:
        from .console import touche_entree_disponible

        if self._interrompu:
            raise ArretExploration("arrêt demandé (Ctrl+C)")
        if len(self.ecrans) >= self.limites.ecrans:
            raise ArretExploration(f"limite de {self.limites.ecrans} écrans atteinte")
        if time.monotonic() - self._debut > self.limites.minutes * 60:
            raise ArretExploration(f"limite de {self.limites.minutes:g} minutes atteinte")
        if touche_entree_disponible():
            raise ArretExploration("arrêt demandé (Entrée)")

    def _connexion(self, page: Page, premiere_fois: bool = False) -> None:
        """Première fois : l'utilisateur se connecte et choisit la page de départ.
        Ensuite : seulement si la session a expiré."""
        if self.connexion is not None:
            self.connexion(page)
            self._attendre(page)
            return
        if not self.interactif:
            if premiere_fois:
                return
            raise ArretExploration("la session a expiré (connexion redemandée) : carte incomplète")
        if premiere_fois:
            self._choisir_accueil()
            return
        self._relogins += 1
        if self._relogins > 3:
            raise ArretExploration("la connexion est redemandée sans cesse : carte incomplète")
        print()
        print(f"{S.PAUSE}  Le portail redemande la connexion : reconnectez-vous dans la fenêtre du robot,")
        print("   sans rien faire d'autre.")
        print("   Puis revenez ici et appuyez sur Entrée : ", end="", flush=True)
        self._attendre_entree()
        self._attendre(self.nav.page_courante())

    def _attendre_entree(self) -> Optional[str]:
        """Entrée dans le terminal ; pendant ce temps l'utilisateur a la main sur le navigateur
        (ses boîtes de dialogue sont à lui, et la connexion peut envoyer des données)."""
        from .console import lire_ligne, vider_clavier

        actif, self.garde_active = self.garde_active, False
        try:
            with self.nav.pause_manuelle():
                return lire_ligne(self.nav.pomper)
        finally:
            self.garde_active = actif
            vider_clavier()  # un second Entrée ne doit rien déclencher

    def _page_du_portail(self) -> Page:
        """L'onglet où l'utilisateur a affiché son portail : de préférence celui du robot, sinon
        le plus récent du même site que l'adresse donnée, sinon le plus récent tout court."""
        pages = self.nav.pages_de_travail()
        web = [p for p in pages if p.url.startswith(("http:", "https:", "file:"))]
        voulu = site_de(self.url_demandee)
        memes = [p for p in web if site_de(p.url) == voulu]
        for liste in (memes, web, pages):
            if self.nav.page in liste:
                return self.nav.page
            if liste:
                return liste[-1]
        return self.nav.page_courante()

    def _choisir_accueil(self) -> None:
        """Première fois : l'utilisateur se connecte et affiche l'accueil de son portail. Le robot
        montre la page d'où il partira et demande confirmation : il ne part jamais, sans le dire,
        d'une page Google, de Chrome ou de connexion."""
        from .console import lire_ligne

        print()
        print(f"{S.PAUSE}  Dans la fenêtre du robot : connectez-vous si besoin, puis affichez la page")
        print("   d'ACCUEIL de votre portail, comme d'habitude.")
        from .console import vider_clavier

        for _ in range(6):
            print("   Quand c'est fait, revenez ici et appuyez sur Entrée : ", end="", flush=True)
            self._attendre_entree()
            print("   Un instant, le robot regarde la page...", flush=True)
            page = self._page_du_portail()
            self.nav.utiliser_page(page)
            self._attendre(page)
            lecture = self._lire(page) or {}
            menus = sum(1 for c in lecture.get("cibles") or [] if c["zone"] in ("menu", "lateral", "arbre"))
            print()
            # ni le titre de la page, ni l'adresse du serveur : ces lignes peuvent être recopiées et envoyées
            forme = f"{menus} élément(s) de menu" + (", un mot de passe demandé" if lecture.get("mot_de_passe") else "")
            if self.mode == "visite":
                print(f"   Vous êtes sur la page affichée dans la fenêtre du robot ({forme}).")
            else:
                print(f"   Le robot partira de la page affichée dans sa fenêtre ({forme}).")
            doute = False
            if lecture.get("mot_de_passe") and menus < 3:  # « mon compte, changer le mot de passe » : normal
                doute = True
                print(f"   {S.ATTENTION} Cette page demande un mot de passe : vous n'êtes peut-être pas encore connecté.")
            elif self.url_demandee and site_de(page.url) != site_de(self.url_demandee):
                doute = True
                print(f"   {S.ATTENTION} Elle n'est pas à l'adresse que vous avez donnée : est-ce bien votre portail ?")
                print("   (Un portail change parfois d'adresse après la connexion : dans ce cas, répondez o.)")
            # en cas de doute, Entrée seule veut dire « non » : on ne part pas d'une page de connexion
            vider_clavier()  # un Entrée tapé pendant la lecture ne répond pas à la question
            print(f"   C'est bien votre portail, et vous êtes connecté ? (o/n) [{'n' if doute else 'o'}] : ",
                  end="", flush=True)
            with self.nav.pause_manuelle():
                reponse = lire_ligne(self.nav.pomper)
            reponse = (reponse or "").strip().lower() or ("n" if doute else "o")
            if not reponse.startswith("n"):
                return
            print()
            print("   D'accord. Dans la fenêtre du robot, affichez la bonne page (connectez-vous si besoin).")
        raise ErreurAutoweb("La page de départ n'a pas été confirmée : rien n'a été fait.")

    def _attendre(self, page: Page) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:  # noqa: BLE001
            pass
        try:
            calme = page.evaluate(JS_CALME, self._calme_max)
            if calme is False:
                self._delais_depasses += 1
                if self._delais_depasses >= 3:
                    self._calme_max = 3000  # page qui bouge sans cesse : on n'attend plus autant
            else:
                self._delais_depasses = 0
        except Exception:  # noqa: BLE001 - la page a changé pendant l'attente
            pass
        if self.limites.delai_ms:
            page.wait_for_timeout(self.limites.delai_ms)

    def _lire(self, page: Page) -> Optional[Dict[str, Any]]:
        for _ in range(2):
            try:
                return page.evaluate(JS_ECRAN, [self.limites.exemples, self.limites.max_cibles])
            except Exception:  # noqa: BLE001 - navigation en cours : on réessaie une fois
                self._attendre(page)
        return None

    # ------------------------------------------------------------------ fenêtres, session
    def _fermer_fenetres_en_trop(self) -> List[str]:
        """Toute fenêtre autre que celle du robot est notée puis refermée."""
        adresses = []
        for autre in list(self.nav.contexte.pages):
            if autre is self.nav.page or autre.is_closed():
                continue
            try:
                adresses.append(autre.url)
                autre.close()
            except Exception:  # noqa: BLE001
                pass
        self._nouvelles_pages = []
        return adresses

    def _connexion_perdue(self, lecture: Dict[str, Any], apres_aller: bool) -> bool:
        """Écran de connexion, ou renvoi vers un autre serveur (SSO) après avoir ouvert
        une adresse connue du portail : la session a probablement expiré."""
        m = decouper(lecture["url"])
        if apres_aller and m is not None and m.netloc != self.hote:
            return True
        menus = sum(1 for c in lecture["cibles"] if c["zone"] in ("menu", "lateral", "arbre"))
        if menus >= 3:
            return False  # « Mon compte / changer le mot de passe » : un écran normal du portail
        if lecture["mot_de_passe"]:
            return True
        chemin = normaliser(m.path if m else "")
        return lecture["identifiant"] and bool(re.search(r"login|signin|sso|saml|oauth|authorize|connexion|logon", chemin))

    # ------------------------------------------------------------------ écrans
    def _observer(self, page: Any, chemin: List[Action], profondeur: int,
                  lecture: Optional[Dict[str, Any]] = None, annoncer: bool = True) -> Optional[Ecran]:
        """Lit l'écran courant (page ou cadre) ; renvoie un Ecran s'il est NOUVEAU, sinon None."""
        lecture = lecture or self._lire(page)
        if lecture is None:
            return None
        # libellés de fiche : sur combien d'objets (d'adresses) de ce modèle d'écran les a-t-on vus ?
        modele = _modele_sans_requete(modele_url(lecture["url"]))
        for info in lecture.get("infos") or []:
            vues = self._infos_vues.setdefault((modele, normaliser(info)), set())
            if len(vues) < 3:
                vues.add(lecture["url"])
        sig = signature(lecture)
        if sig in self._par_signature:
            return None
        ecran = Ecran(
            id=f"E{len(self.ecrans) + 1}", url=lecture["url"], modele=modele_url(lecture["url"]), signature=sig,
            chemin=list(chemin), titre=lecture["titre"], titres=lecture["titres"],
            champs=lecture["champs"], tableaux=lecture["tableaux"], cibles=lecture["cibles"],
            cadres=lecture["cadres"], tronque=lecture["tronque"], fenetre=lecture["fenetre"], profondeur=profondeur,
            infos=list(lecture.get("infos") or []), chargement=list(lecture.get("chargement") or []),
            ombre=bool(lecture.get("ombre")),
        )
        self.ecrans.append(ecran)
        self._par_signature[sig] = ecran
        self._noter_techno(page)
        if annoncer:
            journal.info("   %s %s : « %s » — %d champ(s), %d élément(s) cliquable(s), %d tableau(x)",
                         S.OK, ecran.id, (ecran.titres[0] if ecran.titres else ecran.titre)[:60],
                         len(ecran.champs), len(ecran.cibles), len(ecran.tableaux))
        return ecran

    def _decision(self, cible: Dict[str, Any]) -> Tuple[str, str]:
        """(« aller » | « clic » | « non », raison). Tout ce qui n'est pas explicitement de la
        navigation ou de la consultation est refusé."""
        texte = cible["texte"] or cible["aria"]
        if cible["desactive"]:
            return "non", "désactivé"
        if cible.get("ombre"):
            return "non", "dans un composant web : on ne peut pas vérifier l'élément au moment du clic"
        if cible["zone"] == "fenetre":
            return "non", "dans une fenêtre de confirmation ou de saisie"
        interdit = mot_interdit(cible["aria"], cible["id"], cible["href"],
                                "" if cible["tag"] == "tr" else texte)  # texte d'une ligne entière = données
        if interdit:
            return "non", f"risque (« {interdit} »)"
        href = cible["href"].strip()
        if cible["tag"] == "a" and href and not href.startswith(("#", "javascript:")):
            m = decouper(cible["href_absolu"])
            if m is None:
                return "non", "lien illisible"
            if m.scheme in ("mailto", "tel"):
                return "non", "adresse mail / téléphone"
            if m.scheme not in ("http", "https", "file"):
                return "non", "lien spécial"
            if cible["telechargement"] or m.path.lower().endswith(EXTENSIONS_FICHIERS):
                self.telechargements.append(modele_url(cible["href_absolu"]))
                return "non", "fichier à télécharger"
            if m.netloc != self.hote:
                self.externes.append(m.netloc)
                return "non", "lien vers un autre site"
            action = adresse_action(cible["href_absolu"])
            if action:
                return "non", f"adresse qui ressemble à une action ({action})"
            return "aller", ""
        if cible["tag"] == "tr":
            return "clic", ""  # ligne entière cliquable : le clic va à la ligne, pas à ce qu'elle contient
        if not a_des_lettres(texte):
            return "non", "symbole ou icône sans texte : on ne sait pas ce qu'il fait"
        if cible["soumet"]:
            if cible["methode"] != "get" or not est_lecture(texte):
                return "non", "bouton qui envoie un formulaire"
            return "clic", ""
        if cible["tag"] == "a" and len(href) > 1 and href.startswith("#") and href != "#!":
            return "clic", ""  # lien de navigation interne (#fiche=..., #/plans)
        if cible["zone"] == "tableau" and cible["tag"] == "a" and cible["rang"] == 1:
            return "clic", ""  # premier lien d'une ligne : ouvre la fiche (son texte, ce sont des données)
        if cible["zone"] in ("menu", "lateral", "onglet", "arbre") or cible["role"] in ("tab", "menuitem", "treeitem"):
            return "clic", ""
        if cible["tag"] == "summary" or est_lecture(texte):
            return "clic", ""
        return "non", "bouton d'action (à me montrer si utile)"

    def _cle(self, cible: Dict[str, Any]) -> str:
        if cible["zone"] == "tableau":
            if cible["rang"] <= 0:
                return f"ligne {cible['ligne'] + 1} du tableau"
            return f"ligne {cible['ligne'] + 1} du tableau, élément {cible['rang']}"
        if cible.get("pseudo"):
            return cible["texte"]
        return cible["texte"] or cible["aria"] or cible["selecteur"]

    def _pseudo_lien(self, adresse: str, nature: str) -> Dict[str, Any]:
        return {"texte": f"{nature} {modele_url(adresse)}", "aria": "", "tag": "a", "type": "", "role": "",
                "id": "", "href": adresse, "href_absolu": adresse, "telechargement": False, "desactive": False,
                "zone": "page", "ligne": -1, "rang": -1, "conteneur": "", "soumet": False, "methode": "",
                "selecteur": "", "pseudo": nature}

    def _cibles_a_essayer(self, ecran: Ecran) -> List[Dict[str, Any]]:
        retenues: List[Dict[str, Any]] = []
        deja: set = set()
        cibles = list(ecran.cibles)
        cibles += [self._pseudo_lien(src, "cadre") for src in ecran.cadres if src.startswith(("http", "file"))]
        for cible in cibles:
            if cible["zone"] == "tableau" and not (0 <= cible["ligne"] < self.limites.exemples):
                continue
            if cible["zone"] == "arbre" and cible["ligne"] >= self.limites.exemples:
                ecran.resultats.setdefault(self._cle(cible), "déjà vu (autre élément de l'arborescence)")
                continue
            if cible["zone"] == "lateral" and cible["ligne"] >= 25:
                ecran.resultats.setdefault(self._cle(cible), "non essayé (menu latéral très long)")
                continue
            action, raison = self._decision(cible)
            cle = self._cle(cible)
            if action == "non":
                ecran.resultats.setdefault(cle, f"non cliqué : {raison}")
                continue
            if action == "aller":
                modele = modele_url(cible["href_absolu"])
                if sans_fragment(cible["href_absolu"]) == sans_fragment(ecran.url) and "#" not in cible["href"]:
                    continue  # lien vers la page elle-même
                if self._visites_modele.get(modele, 0) >= self.limites.exemples or (action, modele) in deja:
                    ecran.resultats.setdefault(cle, "déjà vu (même genre de page)")
                    continue
                deja.add((action, modele))
            else:
                globale = self._cle_globale(ecran, cible)
                if globale and self._clics_globaux.get(globale, 0) >= 1:
                    ecran.resultats.setdefault(cle, "déjà essayé depuis un autre écran")
                    continue
                if (action, cle) in deja:
                    continue
                deja.add((action, cle))
            retenues.append(cible)
        return retenues

    @staticmethod
    def _cle_globale(ecran: Ecran, cible: Dict[str, Any]) -> str:
        """Un même menu se retrouve sur tous les écrans : un seul essai suffit."""
        if cible["zone"] in ("menu", "lateral"):
            return f"menu|{_norm_chiffres(cible['texte'] or cible['aria'])}"
        if cible["zone"] == "onglet":
            return f"onglet|{ecran.modele}|{_norm_chiffres(cible['texte'] or cible['aria'])}"
        return ""

    @staticmethod
    def _attendu(cible: Dict[str, Any]) -> Dict[str, Any]:
        """Ce qui doit être IDENTIQUE au moment du clic pour que le clic ait lieu."""
        cles = ["tag", "type", "role", "id", "zone", "soumet", "methode", "aria", "href"]
        if not (cible["zone"] == "tableau" and cible["tag"] in ("tr", "a")):
            cles.append("texte")  # le texte d'une ligne ou d'un lien de ligne, ce sont des données
        if cible["zone"] in ("tableau", "arbre", "lateral"):
            cles += ["ligne", "rang", "conteneur"]
        return {k: cible[k] for k in cles}

    def _essayer(self, ecran: Ecran, cible: Dict[str, Any]) -> Optional[Ecran]:
        cle = self._cle(cible)
        action, _ = self._decision(cible)
        self._fermer_fenetres_en_trop()
        page = self.nav.page_courante()
        if action == "aller":
            pas = Action("aller", url=cible["href_absolu"], partage="un lien" if not cible.get("pseudo") else cible["pseudo"])
            modele = modele_url(pas.url)
            self._visites_modele[modele] = self._visites_modele.get(modele, 0) + 1
            chemin = [pas]
        else:
            if not self._restaurer(ecran):
                ecran.resultats[cle] = "écran impossible à retrouver"
                return None
            page = self.nav.page_courante()
            pas = Action("clic", selecteur=cible["selecteur"], texte=cible["texte"] or cible["aria"],
                         zone=cible["zone"], ligne=cible["ligne"], attendu=self._attendu(cible),
                         partage=self._libelle_partage(cible))
            chemin = ecran.chemin + [pas]
            globale = self._cle_globale(ecran, cible)
            if globale:
                self._clics_globaux[globale] = self._clics_globaux.get(globale, 0) + 1
        nb_bloquees, nb_fichiers = len(self.bloquees), len(self.telechargements)
        self._nouvelles_pages = []
        self.essais += 1
        resultat = self._jouer(page, pas)
        if resultat != "ok":
            ecran.resultats[cle] = f"non cliqué : {resultat}"
            return None
        page = self.nav.page_courante()
        notes = []
        for adresse in self._fermer_fenetres_en_trop():
            m = decouper(adresse)
            notes.append(f"ouvre une nouvelle fenêtre ({modele_url(adresse)})")
            if m is not None and m.netloc == self.hote and adresse not in self._fenetres_a_voir:
                self._fenetres_a_voir.append(adresse)
        if len(self.bloquees) > nb_bloquees:
            notes.append("a voulu ENVOYER des données : bloqué")
            journal.info("   %s « %s » : le portail a voulu envoyer des données. Bloqué : rien n'est parti.",
                         S.ATTENTION, cle[:50])
        if len(self.telechargements) > nb_fichiers:
            notes.append("lance un téléchargement (annulé)")
        lecture = self._lire(page)
        if lecture is None:
            ecran.resultats[cle] = " ; ".join(notes + ["écran illisible"])
            return None
        if lecture["url"].startswith(("chrome-error:", "about:blank")):
            self.formulaires_bloques += 1
            if self.formulaires_bloques >= 6 and len(self.ecrans) <= 5:
                raise ArretExploration("ce portail envoie des données même pour changer d'écran, ce que le robot "
                                       "bloque par sécurité : la visite guidée (menu, choix 8) le cartographiera "
                                       "bien mieux")
            ecran.resultats[cle] = " ; ".join(notes + ["navigation par envoi de formulaire : bloquée"])
            return None
        # un nouveau lien qui mène ailleurs sort simplement du portail ; seul un écran de
        # connexion signale ici une session expirée (le renvoi SSO est vu en revenant sur un écran connu)
        if self._connexion_perdue(lecture, apres_aller=False):
            ecran.resultats[cle] = "connexion redemandée"
            self._connexion(page)
            return None
        m = decouper(lecture["url"])
        if m is None or m.netloc != self.hote:
            if m is not None:
                self.externes.append(m.netloc)
            ecran.resultats[cle] = " ; ".join(notes + ["sort du portail"])
            return None
        nouveau = self._observer(page, chemin, ecran.profondeur + 1, lecture)
        if nouveau is not None:
            notes.insert(0, f"mène à {nouveau.id}")
            self.transitions.append({"de": ecran.id, "action": cle, "vers": nouveau.id})
        else:
            vers = self._par_signature.get(signature(lecture))
            notes.insert(0, f"mène à {vers.id}" if vers else "rien de nouveau")
            if vers and vers is not ecran:
                self.transitions.append({"de": ecran.id, "action": cle, "vers": vers.id})
        ecran.resultats[cle] = " ; ".join(notes)
        return nouveau

    def _restaurer(self, ecran: Ecran) -> bool:
        """Revient sur l'écran : il suffit parfois d'y être déjà, sinon on rejoue le chemin."""
        page = self.nav.page_courante()
        lecture = self._lire(page)
        if lecture is not None and signature(lecture) == ecran.signature and lecture["url"] == ecran.url:
            return True
        for essai in range(2):
            ok = True
            for pas in ecran.chemin:
                if self._jouer(self.nav.page_courante(), pas) != "ok":
                    ok = False
                    break
                self._fermer_fenetres_en_trop()
            lecture = self._lire(self.nav.page_courante()) if ok else None
            if lecture is not None and self._connexion_perdue(lecture, apres_aller=True) and essai == 0:
                self._connexion(self.nav.page_courante())
                continue
            if lecture is not None and signature(lecture) == ecran.signature:
                self._echecs_consecutifs = 0
                return True
            break
        self._echecs_consecutifs += 1
        if self._echecs_consecutifs >= 6:
            raise ArretExploration("les écrans ne se retrouvent plus (session expirée ?) : carte incomplète")
        return False

    def _jouer(self, page: Page, pas: Action) -> str:
        """« ok », ou la raison pour laquelle rien n'a été fait."""
        try:
            if pas.type == "aller":
                self._urls_sures.add(sans_fragment(pas.url))
                page.goto(pas.url, wait_until="domcontentloaded")
            else:
                try:
                    resultat = page.evaluate(JS_CLIC, [pas.selecteur, pas.attendu])
                except Exception as e:  # noqa: BLE001
                    texte = str(e)
                    if "context was destroyed" in texte or "navigat" in texte:
                        resultat = "ok"  # le clic a déclenché un changement de page
                    else:
                        raise
                if resultat != "ok":
                    return f"l'élément a changé ({resultat})"
        except (ArretExploration, KeyboardInterrupt):
            raise
        except Exception as e:  # noqa: BLE001
            if navigateur_ferme(e):
                raise ArretExploration("le navigateur a été fermé")
            journal.debug("Action impossible (%s) : %s", pas.libelle(), str(e).splitlines()[0])
            return "action impossible"
        self._attendre(self.nav.page_courante())
        return "ok"

    # ------------------------------------------------------------------ résultats
    def resume(self) -> Dict[str, Any]:
        return {
            "ecrans": len(self.ecrans),
            "essais": self.essais,
            "bloquees": len(self.bloquees),
            "websockets": self.websockets,
            "telechargements": len(set(self.telechargements)),
            "arret": self.arret,
            "complet": self.complet,
            "duree_s": round(time.monotonic() - self._debut) if self._debut else 0,
            "mode": self.mode,
        }

    def _sauvegarde_periodique(self) -> None:
        self._depuis_sauvegarde += 1
        if self._depuis_sauvegarde >= 5:
            self._depuis_sauvegarde = 0
            self.enregistrer()

    def enregistrer(self) -> None:
        self.dossier.mkdir(parents=True, exist_ok=True)
        donnees = {
            "genere": dt.datetime.now().isoformat(timespec="seconds"),
            "resume": self.resume(),
            "ecrans": [asdict(e) for e in self.ecrans],
            "transitions": self.transitions,
            "envois_bloques": sorted({f"{m} {u}" for m, u in self.bloquees}),
            "telechargements": sorted(set(self.telechargements)),
            "sites_externes": sorted(set(self.externes)),
            "technologie": self.techno,
            "envois": self.envois,
            "version": VERSION_CARTE,
        }
        (self.dossier / "carte.json").write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
        (self.dossier / "carte_PRIVEE_ne_pas_envoyer.html").write_text(self._html(), encoding="utf-8")
        (self.dossier / "carte_a_partager.txt").write_text(self._texte_partage(), encoding="utf-8")

    def _acces(self, ecran: Ecran) -> str:
        return " › ".join(p.libelle() for p in ecran.chemin)

    # ------------------------------------------------------------------ carte à partager
    # Liste d'AUTORISATION : seuls les textes de l'interface qui ne sont presque jamais des
    # données sont repris (noms de champs, entêtes de colonnes, onglets et menus courts,
    # boutons usuels). Tout le reste est remplacé par sa nature : « (bouton) », « un lien ».
    # Jamais repris : ce qui ressemble à un nom de personne, le menu du compte de
    # l'utilisateur, les onglets de document (un onglet par plan ouvert, avec une croix).
    @staticmethod
    def _court(texte: str, mots: int = 3) -> bool:
        return 0 < len(normaliser(texte).split()) <= mots

    @classmethod
    def _sur(cls, texte: str, mots: int = 3) -> Optional[str]:
        """Le texte masqué s'il peut être repris, sinon None : ni nom de personne, ni nom propre
        (« Projet Flamanville », « Hinkley Point C ») dans un onglet, un menu ou un chemin d'accès."""
        if not cls._court(texte, mots) or nom_propre_dedans(texte):
            return None
        return masquer(texte)

    def _texte_bouton(self, cible: Dict[str, Any]) -> str:
        texte = cible["texte"] or cible["aria"]
        if cible.get("perso") or ressemble_a_une_personne(texte):
            return "(bouton)"
        premier = (texte.split() or [""])[0]
        if verbe_de_bouton(premier) and (est_lecture(texte) or self._court(texte, 4)):
            # « Voir le détail » oui ; « Voir Poste Lyon Sud », « Exporter Pompe Bugey » : la suite
            # peut être une donnée, seuls les mots génériques sont repris. Le premier mot doit être
            # le verbe lui-même (« Paluel Exporter », « Newcastle », « Printemps » : rien de repris)
            mots = texte.split()
            suite = [m for m in mots[1:] if normaliser(m).strip(".:,;") in MOTS_GENERIQUES]
            return masquer(" ".join([mots[0]] + suite) + (" …" if len(suite) < len(mots) - 1 else ""))
        return "(bouton)"

    def _libelle_partage(self, cible: Dict[str, Any]) -> str:
        texte = cible["texte"] or cible["aria"]
        if cible["zone"] == "tableau":
            return f"ligne {cible['ligne'] + 1} du tableau"
        if cible["zone"] == "arbre":
            return "un élément de l'arborescence"
        if cible.get("perso"):
            return "un élément du compte de l'utilisateur"
        if cible.get("fermable"):
            return "un onglet de document"
        noms = {"onglet": "onglet", "menu": "menu"}
        sur = self._sur(texte)
        if cible["zone"] in noms and sur and \
                (cible["tag"] == "a" or cible["role"] in ("tab", "menuitem") or cible["zone"] == "onglet"):
            return f"{noms[cible['zone']]} « {sur} »"
        if cible["zone"] == "lateral":
            return "un élément du menu latéral"
        if cible["tag"] == "a":
            return "un lien"
        return f"bouton « {self._texte_bouton(cible)} »" if self._texte_bouton(cible) != "(bouton)" else "un bouton"

    def _info_revue(self, ecran: "Ecran", info: str) -> bool:
        """Libellé lu sur au moins deux objets (deux adresses) du même modèle d'écran."""
        return len(self._infos_vues.get((_modele_sans_requete(ecran.modele), normaliser(info)), ())) >= 2

    def _libelle_champ(self, champ: Dict[str, Any]) -> str:
        if champ["type"] in ("checkbox", "radio"):
            return "(case)"
        libelle = champ["libelle"]
        if nom_propre_dedans(libelle):  # « Rechercher dans Flamanville », « Site Penly », un nom de personne
            return "(sans nom)"
        if champ["source"] in ("label", "aria", "entete") and self._court(libelle, 5):
            return masquer(libelle)
        if champ["source"] == "voisin" and libelle.rstrip().endswith(":") and self._court(libelle, 5):
            return masquer(libelle)
        return "(sans nom)"

    def _onglet_courant(self, cible: Dict[str, Any], ecran: "Ecran") -> bool:
        """Onglet qu'on retrouve sur un autre écran du même modèle : un onglet de l'interface, pas le
        nom d'un plan ouvert."""
        nom = _norm_chiffres(cible["texte"] or cible["aria"])
        modele = _modele_sans_requete(ecran.modele)  # ?onglet=general, ?onglet=revisions : la même fiche
        return any(
            autre is not ecran and _modele_sans_requete(autre.modele) == modele
            and any(_norm_chiffres(c["texte"] or c["aria"]) == nom for c in autre.cibles if c["zone"] == "onglet")
            for autre in self.ecrans
        )

    def _texte_partage(self) -> str:
        r = self.resume()
        ids = {e.id for e in self.ecrans}

        def resultat(texte: str) -> str:
            texte = re.sub(r"\([^)]*\)", "", texte)  # adresses, mots entre parenthèses : retirés
            return " ".join(m if m.rstrip(",;") in ids else masquer(m) for m in texte.split())

        lignes = [
            f"CARTE DU PORTAIL - VERSION A PARTAGER (robot version {VERSION_CARTE})",
            "=" * 60,
            "Ce fichier décrit la STRUCTURE du portail : écrans, noms des champs, colonnes des",
            "tableaux, onglets et menus courts, boutons usuels. Il ne contient ni valeurs, ni contenu",
            "de tableau, ni titres de page, ni adresses. Les mots contenant un chiffre sont remplacés",
            "par #, les autres textes par leur nature, par exemple « (bouton) ».",
            "Un nom d'onglet, de menu ou de colonne peut malgré tout être un nom de client, de projet",
            "ou de personne : RELISEZ-LE et remplacez ce qui vous semble sensible avant de l'envoyer.",
            "",
            self._bilan_partage(r),
            "",
        ]
        for e in self.ecrans:
            lignes.append(f"{e.id}" + (f"   [étape : {e.etape}]" if e.etape else "")
                          + ("   (fenêtre ouverte par-dessus l'écran)" if e.fenetre else "")
                          + ("   (contenu d'un cadre de la page)" if e.cadre else "")
                          + ("   (composants web)" if e.ombre else ""))
            lignes.append(f"     accès : {' › '.join(p.partage or 'un clic' for p in e.chemin)}")
            onglets_cibles = [c for c in e.cibles if c["zone"] == "onglet" and not c.get("perso")]
            documents_ouverts = any(c.get("fermable") for c in e.cibles)
            # avec des onglets de document ouverts, un onglet sans croix est repris s'il est aussi sur une
            # autre fiche, ou s'il n'est fait que de mots d'interface (« Général », « Où utilisé »)
            onglets = sorted({x for x in (self._sur(c["texte"]) for c in onglets_cibles if not c.get("fermable")
                                          and (not documents_ouverts or self._onglet_courant(c, e)
                                               or all(_mot_interface(m) for m in c["texte"].split()))) if x})
            if onglets:
                lignes.append(f"     onglets : {' ; '.join(onglets)}")
            documents = sum(1 for c in e.cibles if c.get("fermable") and not c.get("perso"))
            if documents:
                lignes.append(f"     onglets de document (un par élément ouvert) : {documents}, noms non repris")
            menus = sorted({x for x in (self._sur(c["texte"]) for c in e.cibles
                                        if c["zone"] == "menu" and not c.get("perso") and not c.get("fermable")
                                        and (c["tag"] == "a" or c["role"] == "menuitem")) if x})
            if menus:
                lignes.append(f"     menus : {' ; '.join(menus)}")
            lateral = sum(1 for c in e.cibles if c["zone"] == "lateral")
            if lateral:
                # souvent « consultés récemment », dossiers, projets : noms non repris
                lignes.append(f"     menu latéral : {lateral} entrée(s), noms non repris")
            champs = []
            for c in e.champs:
                if c["dans_tableau"] or c["zone"] in ("arbre", "lateral"):
                    continue
                # les noms de code (id, name) restent dans carte.json, sur le poste : dans un nom de
                # code peut se glisser un nom de site ou de personne (site_Flamanville, auteur_mmartin)
                champs.append(f"{self._libelle_champ(c)} [{type_champ(c['type'])}"
                              + (f", {c['nb_options']} choix" if c["type"] == "liste" else "")
                              + (", obligatoire" if c["obligatoire"] else "")
                              + (", lecture seule" if c["lecture_seule"] else "") + "]")
            if champs:
                lignes.append(f"     champs : {' ; '.join(champs)}")
            # un libellé de fiche se retrouve d'un objet à l'autre (fiche d'un deuxième plan) ; un nom de
            # site écrit seul (« Flamanville : », « Gravelines ») non : seuls les libellés revus sont repris
            gardes, autres = set(), 0
            for i in e.infos:
                x = self._sur(i, 5)
                if x and (self._info_revue(e, i) or all(_mot_interface(m) for m in i.split())):
                    gardes.add(x)
                else:
                    autres += 1
            infos = sorted(gardes)
            if infos or autres:
                lignes.append("     libellés affichés (fiche en lecture) : " + " ; ".join(infos[:40])
                              + (" ; " if infos and autres else "")
                              + (f"{autres} autre(s), non repris (vus sur une seule fiche)" if autres else ""))
            boutons = []
            for c in e.cibles:
                if c["zone"] not in ("page", "fenetre") or c["tag"] == "a":
                    continue
                res = e.resultats.get(self._cle(c), "")
                boutons.append(self._texte_bouton(c) + (f" → {resultat(res)}" if res else ""))
            if boutons:
                lignes.append(f"     boutons : {' ; '.join(boutons)}")
            for t in e.tableaux:
                entetes = [x if not nom_propre_dedans(x) else "(nom)" for x in t["entetes"]]
                lignes.append(f"     tableau : [{masquer(' | '.join(entetes))}] ({t['lignes']} lignes)")
            # seulement les clés du robot (« ligne 2 du tableau ») : un lien dont le texte commence par
            # « ligne » est un texte de la page
            for k, v in sorted((k, v) for k, v in e.resultats.items()
                               if re.fullmatch(r"ligne \d+ du tableau(?:, élément \d+)?", k)):
                lignes.append(f"     {k} → {resultat(v)}")
            liens = sum(1 for c in e.cibles if c["tag"] == "a" and c["zone"] in ("page", "arbre"))
            liens += sum(1 for c in e.cibles if c["zone"] == "menu" and not self._court(c["texte"]))
            if liens:
                lignes.append(f"     autres liens : {liens}")
            if e.tronque:
                lignes.append("     (écran très chargé : seuls les premiers éléments ont été lus)")
            lignes.append("")
        lignes += self._diagnostic_partage()
        return "\n".join(lignes) + "\n"

    def _bilan_partage(self, r: Dict[str, Any]) -> str:
        return (f"Exploration automatique : {r['ecrans']} écran(s) vus, {r['essais']} élément(s) essayés, "
                f"{r['bloquees']} envoi(s) de données bloqué(s). "
                f"{'Exploration complète.' if r['complet'] else 'Exploration INCOMPLÈTE.'}")

    def _raisons_refus(self) -> Dict[str, int]:
        """Pourquoi des éléments n'ont pas été cliqués : explique une carte pauvre."""
        raisons: Dict[str, int] = {}
        for e in self.ecrans:
            for resultat in e.resultats.values():
                if not resultat.startswith("non cliqué : "):
                    continue
                raison = re.sub(r"\s*(«[^»]*»|\([^)]*\))", "", resultat[len("non cliqué : "):]).strip(" :;,")
                raisons[raison] = raisons.get(raison, 0) + 1
        return raisons

    def _diagnostic_partage(self) -> List[str]:
        """Ce qui m'aide à comprendre le portail : sa technologie, la nature des envois de
        données (jamais leurs valeurs), et pourquoi des éléments n'ont pas été essayés."""
        lignes = ["TECHNOLOGIE RECONNUE : " + (", ".join(self.techno) if self.techno else "rien de connu")]
        if self.diagnostic:
            lignes.append("")
            lignes.append("CONNEXION DU CHROME DU ROBOT (réglages du poste, oui / non)")
            for libelle, valeur in self.diagnostic:
                lignes.append(f"   {libelle} : {valeur}")
        if self.envois:
            lignes.append("")
            lignes.append("ENVOIS DE DONNEES " + ("VUS PENDANT LA VISITE" if self.mode == "visite"
                                                   else "BLOQUES PAR SECURITE (rien n'est parti)")
                          + " : nature seulement, sans aucune valeur")
            for nature, nombre in sorted(self.envois.items(), key=lambda x: (-x[1], x[0]))[:40]:
                lignes.append(f"   {nombre:3} × {nature}")
        indicateurs = sorted({i for e in self.ecrans for i in e.chargement})
        if indicateurs:
            lignes.append("")
            lignes.append(f"INDICATEURS DE CHARGEMENT VUS : {', '.join(indicateurs)}")
        raisons = self._raisons_refus()
        if raisons:
            lignes.append("")
            lignes.append("ELEMENTS NON CLIQUES PAR SECURITE, PAR RAISON")
            for raison, nombre in sorted(raisons.items(), key=lambda x: (-x[1], x[0]))[:20]:
                lignes.append(f"   {nombre:3} × {raison}")
        if self.telechargements:
            extensions = sorted({extension_connue(t) for t in self.telechargements})
            lignes.append("")
            lignes.append(f"FICHIERS PROPOSES AU TELECHARGEMENT : {len(set(self.telechargements))} "
                          f"(types : {', '.join(masquer(x) for x in extensions)})")
        return lignes

    def _html(self) -> str:
        r = self.resume()
        h = html.escape
        morceaux = [
            "<!doctype html><html lang=fr><meta charset=utf-8><title>Carte du portail</title>",
            "<style>body{font:14px/1.45 system-ui,Arial;margin:24px;max-width:1100px;color:#1f2937}"
            "h1{font-size:22px}h2{font-size:17px;margin:28px 0 6px;border-top:1px solid #ddd;padding-top:14px}"
            "table{border-collapse:collapse;margin:6px 0}td,th{border:1px solid #ddd;padding:3px 8px;text-align:left;"
            "vertical-align:top}th{background:#f3f4f6}.gris{color:#6b7280}.rouge{color:#b91c1c}"
            ".vert{color:#15803d}code{background:#f3f4f6;padding:1px 4px}</style>",
            "<h1>Carte du portail</h1>",
            f"<p>{r['ecrans']} écran(s) vus · {r['essais']} élément(s) essayés · "
            f"<span class=rouge>{r['bloquees']} envoi(s) de données bloqué(s)</span> · {r['duree_s']} s<br>"
            f"<span class=gris>Fin : {h(r['arret'])}. Ce fichier reste sur votre poste : il peut contenir des données.</span></p>",
        ]
        for e in self.ecrans:
            morceaux.append(f"<h2 id={e.id}>{e.id} — {h((e.titres[0] if e.titres else e.titre) or '(sans titre)')}</h2>")
            morceaux.append(f"<p class=gris>Adresse : <code>{h(e.modele)}</code><br>Accès : {h(self._acces(e))}</p>")
            if e.champs:
                morceaux.append("<table><tr><th>Champ</th><th>Type</th><th>Détails</th></tr>")
                for c in e.champs:
                    details = []
                    if c["obligatoire"]:
                        details.append("obligatoire")
                    if c["lecture_seule"]:
                        details.append("lecture seule")
                    if c["type"] == "liste":
                        details.append(f"{c['nb_options']} choix : " + ", ".join(c["options"][:15]))
                    morceaux.append(f"<tr><td>{h(c['libelle'] or c['nom'] or '?')}</td><td>{h(type_champ(c['type']))}</td>"
                                    f"<td>{h(' ; '.join(details))}</td></tr>")
                morceaux.append("</table>")
            for t in e.tableaux:
                morceaux.append(f"<p>Tableau ({t['lignes']} lignes) : <b>{h(' | '.join(t['entetes']))}</b></p>")
            morceaux.append("<table><tr><th>Élément</th><th>Où</th><th>Résultat</th></tr>")
            for c in e.cibles:
                res = e.resultats.get(self._cle(c), "")
                classe = "rouge" if ("bloqu" in res or res.startswith("non")) else ("vert" if res.startswith("mène") else "gris")
                liens = re.sub(r"\b(E\d+)\b", r"<a href=#\1>\1</a>", h(res))
                morceaux.append(f"<tr><td>{h(c['texte'] or c['aria'] or '(icône)')}</td><td>{h(c['zone'])}</td>"
                                f"<td class={classe}>{liens}</td></tr>")
            morceaux.append("</table>")
        morceaux.append(f"<h2>Technologie reconnue</h2><p>{h(', '.join(self.techno) or 'rien de connu')}</p>")
        if self.envois:
            morceaux.append("<h2>Nature des envois de données " + ("vus" if self.mode == "visite" else "bloqués")
                            + "</h2><ul>")
            for nature, nombre in sorted(self.envois.items(), key=lambda x: (-x[1], x[0])):
                morceaux.append(f"<li>{nombre} × <code>{h(nature)}</code></li>")
            morceaux.append("</ul>")
        if self.bloquees:
            morceaux.append("<h2>Envois de données bloqués</h2><ul>")
            for envoi in sorted({f"{m} {u}" for m, u in self.bloquees}):
                morceaux.append(f"<li><code>{h(envoi)}</code></li>")
            morceaux.append("</ul>")
        return "".join(morceaux) + "</html>\n"

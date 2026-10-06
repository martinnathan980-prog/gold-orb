# -*- coding: utf-8 -*-
r"""
PRISE EN MAIN DU ROBOT (version 1)
==================================

Le robot montre, une chose a la fois, qu'il sait prendre la main sur votre ordinateur :
    1. Python fonctionne
    2. fichiers et dossiers : il cree un dossier d'essai sur le Bureau et l'ouvre
    3. clavier : il ouvre SON fichier dans le Bloc-notes et y ecrit une phrase tout seul
    4. souris : il bouge la souris et clique dans ce Bloc-notes
    5. votre navigateur habituel : il y ouvre l'adresse de votre portail
    6. son propre navigateur : il remplit et clique une page d'essai
    7. ce navigateur sur votre portail : il compte et encadre ce qu'il sait cliquer
    8. un clic que VOUS choisissez sur le portail (un menu, un lien), apres votre accord

Il ne modifie RIEN dans vos outils : il ne fait que creer le dossier « Robot - essai »
sur le Bureau. Il n'ecrit QUE dans son propre fichier essai_clavier.txt. Sur le portail,
il ne clique que sur des liens et des menus, jamais sur un bouton de formulaire, une case
a cocher, ni sur ce qui ressemble a une action (Supprimer, Enregistrer, Valider, OK...).

A la fin, un RESULTAT s'affiche : prenez-le en photo et envoyez-le. Il est aussi ecrit
dans « Robot - essai\resultat_prise_en_main.txt ». Il ne contient aucune donnee du
portail : ni adresse, ni texte des pages, ni les mots tapes. Seulement OK / ECHEC et des nombres.

Lancement, dans une fenetre noire ouverte dans le dossier ou est ce fichier :
    python prise_en_main.txt
(si « python » n'est pas reconnu :  py prise_en_main.txt )
"""

import ctypes
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import tempfile
import time
import unicodedata
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

VERSION = "1"
WINDOWS = os.name == "nt"
# pour les essais automatiques du programme seulement (navigateur caché)
INVISIBLE = os.environ.get("PRISE_EN_MAIN_INVISIBLE") == "1"
FICHIER_CLAVIER = "essai_clavier.txt"

# Sur le portail, le robot ne clique jamais sur ce qui pourrait modifier quelque chose.
# Comparé à mots() : texte sans accents, en minuscules, « camelCase » et ponctuation découpés en mots
# (« btnSupprimer », « lnk_Suppr », « Supprimé »... sont tous pris).
MOTS_INTERDITS = re.compile(
    r"suppr|\bdel\b|delet|remov|retir|retrait|effac|erase|destro|detrui|vider|\bclear|nettoy|corbeil|trash|purg|"
    r"dupliq|duplic|\bcopi|\bcopy|\bclon|valid|enregistr|sauv|\bsave|\bcreer|\bcree\b|\bcreat|nouveau|nouvelle|"
    r"\bnew\b|ajout|\badd\b|modif|\bedit|envoy|envoi|\bsend\b|soumet|soumis|submit|confirm|annul|cancel|"
    r"\barchiv|\bpublier|\bpublish|transfer|transmet|transmis|forward|\bstatut|\bstatus|\betat\b|rejet|reject|"
    r"approuv|approb|approv|\bsigner|\bsign\b|\bsignature|associ|rattach|attach|joindre|detach|\bimport|"
    r"\breviser\b|\bliberer|\brelease|verrou|\block|unlock|bascul|clotur|\bclore|\bclos\b|ferm|\bclose|"
    r"mettre a jour|mise a jour|\bmaj\b|update|upgrade|reinitialis|reset|\braz\b|restaur|restore|\blancer|execut|"
    r"\brun\b|\bstart|demarr|arret|\bstop\b|activer|desactiv|activate|deactivat|\benable|\bdisable|affect|assign|"
    r"attribu|\baccept|refus|declin|\bterminer|finish|\bcompleter|\bcomplete\b|resolu|resou|resolv|appliqu|"
    r"\bapply|upload|televers|\bdepos|deplac|\bmove\b|renomm|rename|rempla|replace|\bgenerer|regener|generat|"
    r"\bcommander|\border\b|\bpayer|paiement|\bpay\b|factur|repond|reply|\bcommenter|relanc|prise en charge|"
    r"prendre en charge|\btraiter|\btraite\b|synchro|recalcul|fusion|merge|deploy|deploi|abandon|revoq|revok|"
    r"autoris|inscri|mise en|mettre en|dissoci|unlink|"
    r"^oui$|^ok$|^yes$|^non$|^no$|^go$",
    re.IGNORECASE,
)

# Adresse copiée juste après un clic : celle d'une ACTION si l'un de ses mots est un de ces verbes.
VERBES_ACTION = set("""supprimer suppression suppr delete del remove retirer effacer erase destroy detruire purge purger
vider clear valider validate validation enregistrer save sauvegarder dupliquer duplicate copier copy clone creer create
new nouveau nouvelle ajouter add edit editer modifier modification update maj envoyer send submit soumettre approuver
approve rejeter reject annuler cancel archiver archive publier publish importer import upload deplacer move renommer
rename remplacer replace activer desactiver activate deactivate enable disable lock unlock verrouiller deverrouiller
signer sign cloturer close reset restaurer restore transferer transfer assigner assign affecter attribuer appliquer
apply confirmer confirm executer execute""".split())


def mots(texte):
    t = sans_accents(texte)
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t)
    t = re.sub(r"[^A-Za-z0-9]+", " ", t)
    return " ".join(t.split()).lower()


def interdit(texte):
    return bool(MOTS_INTERDITS.search(mots(texte)))


# ---------------------------------------------------------------------------- console
def preparer_console():
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def ecrire(texte=""):
    print(texte, flush=True)


def vider_clavier():
    """Une touche tapée pendant que le robot travaillait ne doit pas répondre à la question suivante."""
    if not WINDOWS:
        return
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getwch()
    except Exception:
        pass


def demander(question, defaut=""):
    vider_clavier()
    try:
        reponse = input(question + " ")
    except EOFError:
        reponse = ""
    return reponse.strip() or defaut


def oui(question, defaut="o"):
    return demander(f"{question} (o/n) [{defaut}] :", defaut).lower().startswith(("o", "y"))


def pause(texte="Appuyez sur Entree pour commencer..."):
    demander("   >>> " + texte)


def titre_etape(numero, texte):
    ecrire()
    ecrire("=" * 70)
    ecrire(f" ETAPE {numero} : {texte}")
    ecrire("=" * 70)


def revenez_ici():
    revenir_console()
    ecrire("   Revenez dans CETTE fenetre noire (cliquez dedans) pour repondre.")


def sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", str(texte)) if unicodedata.category(c) != "Mn")


def masquer(texte, url=""):
    """Rien du portail ni de votre compte dans le résultat : ni adresse, ni chemin, ni nom d'utilisateur."""
    texte = str(texte or "")
    if url:
        texte = texte.replace(url, "<portail>")
        hote = urlsplit(url).hostname or ""
        if len(hote) >= 3:
            texte = re.sub(r"(?<![\w.-])" + re.escape(hote) + r"(?![\w-])", "<portail>", texte, flags=re.IGNORECASE)
    texte = re.sub(r"(https?|file)://\S+", "<adresse>", texte)
    texte = texte.replace("\\\\", "\\")  # chemins affichés avec des barres doublées (repr)
    for chemin in sorted({str(Path.home()), os.environ.get("USERPROFILE", ""), os.environ.get("OneDrive", ""),
                          os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", "")}, key=len, reverse=True):
        if len(chemin) > 3:
            texte = texte.replace(chemin, "~")
    texte = re.sub(r"(?i)\b[a-z]:\\[^'\"\n]*", "<chemin>", texte)
    texte = re.sub(r"/(home|Users)/[^/\s'\"]+", r"/\1/<moi>", texte)
    utilisateur = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if len(utilisateur) >= 3:
        texte = re.sub(r"(?<![\w])" + re.escape(utilisateur) + r"(?![\w])", "<moi>", texte, flags=re.IGNORECASE)
    return " ".join(texte.split())[:100]


def erreur_courte(e):
    """Une erreur de fichier sans son chemin (qui contient votre nom et celui de l'entreprise)."""
    code = getattr(e, "winerror", None) or getattr(e, "errno", None)
    return e.__class__.__name__ + (f" ({code})" if code else "")


def premiere_ligne(erreur):
    lignes = [l.strip() for l in str(erreur).splitlines() if l.strip()]
    return lignes[0] if lignes else erreur.__class__.__name__


def expliquer(erreur):
    """Une erreur du navigateur, en quelques mots compréhensibles (sans adresse ni texte de page)."""
    t = str(erreur).lower()
    connues = (
        (("disallowed by the system admin", "remotedebuggingallowed", "remote debugging is disallowed"),
         "pilotage du navigateur interdit par une strategie de l'entreprise"),
        (("executable doesn't exist", "is not found at", "looks like playwright", "please run the following command"),
         "navigateur absent de ce poste"),
        (("err_blocked_by_administrator",), "page bloquee par une strategie de l'entreprise"),
        (("err_invalid_auth_credentials", "http authentication"),
         "le portail demande une connexion par une petite fenetre du navigateur"),
        (("err_name_not_resolved",), "adresse introuvable depuis ce poste"),
        (("err_cert", "certificate"), "certificat de securite refuse"),
        (("err_tunnel_connection_failed", "err_proxy", "proxy"), "probleme de proxy"),
        (("err_connection_refused", "err_connection_timed_out", "err_timed_out", "err_internet_disconnected"),
         "le portail ne repond pas depuis ce poste"),
        (("target page, context or browser has been closed", "browser has been closed", "target closed"),
         "la fenetre du robot a ete fermee"),
        (("timeout",), "delai depasse"),
    )
    for indices, explication in connues:
        if any(i in t for i in indices):
            return explication
    return masquer(premiere_ligne(erreur))


# ---------------------------------------------------------------------------- bilan
CODES = {"OK": "1", "ECHEC": "0", "SAUTE": "-", "PAS VU": "?", "NON DISPONIBLE": "x"}
ORDRE = "PFKSWNDRC"


class Bilan:
    def __init__(self):
        self.lignes = {}  # lettre -> (intitule, statut, detail)

    def noter(self, lettre, intitule, statut, detail="", afficher=True):
        self.lignes[lettre] = (intitule, statut, masquer(detail))
        if afficher:
            ecrire(f"   --> {intitule} : {statut}" + (f"  ({masquer(detail)})" if detail else ""))
            if statut == "ECHEC":
                ecrire("       Ce n'est pas grave : c'est justement ce qu'on cherche a savoir. On continue.")

    def tries(self):
        return sorted(self.lignes.items(), key=lambda kv: ORDRE.index(kv[0]) if kv[0] in ORDRE else 99)

    def code(self):
        return " ".join(lettre + CODES.get(v[1], "?") for lettre, v in self.tries())

    def texte(self):
        lignes = [f"RESULTAT DE LA PRISE EN MAIN (version {VERSION}) - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                  "-" * 70]
        for lettre, (intitule, statut, detail) in self.tries():
            lignes.append(f" {lettre}  {(intitule + ' ').ljust(40, '.')} {statut}")
            if detail:
                lignes.append(f"      {detail}")
        lignes += ["-" * 70, "CODE : " + self.code()]
        return "\n".join(lignes)


# ---------------------------------------------------------------------------- Windows : clavier, souris, fenêtres
if WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _UNION_ENTREE(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _UNION_ENTREE)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]

    INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
    KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
    MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x0001, 0x8000, 0x4000
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
    MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
    VK_RETURN = 0x0D
    GA_ROOT, GA_ROOTOWNER = 2, 3
    SM_SWAPBUTTON = 23
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79


def rendre_net():
    """Coordonnées de la souris en vrais pixels, même avec un affichage à 125 % ou 150 %."""
    if not WINDOWS:
        return
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:  # renvoie un code, ne lève pas d'erreur
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def edition_rapide_coupee():
    """Console classique : un clic dedans la met en mode « Sélectionner » et Entrée ne répond plus.
    On coupe ce mode le temps du test ; renvoie l'ancien réglage, à remettre à la fin."""
    if not WINDOWS:
        return None
    try:
        h = kernel32.GetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF))
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(h, ctypes.byref(mode)):
            return None
        # sans « Sélectionner » (0x40) ni souris captée (0x10) : le clic droit colle à nouveau
        kernel32.SetConsoleMode(h, (mode.value | 0x0080) & ~0x0040 & ~0x0010)
        return mode.value
    except Exception:
        return None


def remettre_console(ancien):
    if WINDOWS and ancien is not None:
        try:
            kernel32.SetConsoleMode(kernel32.GetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF)), ancien)
        except Exception:
            pass


def _envoyer(*entrees):
    tableau = (INPUT * len(entrees))(*entrees)
    n = user32.SendInput(len(entrees), tableau, ctypes.sizeof(INPUT))
    if n != len(entrees):
        raise OSError(f"Windows a refuse le geste simule (SendInput, code {ctypes.get_last_error()})")


def _touche(vk=0, unite=0, relache=False):
    e = INPUT()
    e.type = INPUT_KEYBOARD
    e.ki = KEYBDINPUT(vk, unite, (KEYEVENTF_UNICODE if not vk else 0) | (KEYEVENTF_KEYUP if relache else 0), 0, 0)
    return e


def _souris(drapeaux, dx=0, dy=0):
    e = INPUT()
    e.type = INPUT_MOUSE
    e.mi = MOUSEINPUT(dx, dy, 0, drapeaux, 0, 0)
    return e


def cliquer_ici():
    """Appui et relâchement du bouton, là où est la souris (vérifiée juste avant), en un seul envoi."""
    gaucher = bool(user32.GetSystemMetrics(SM_SWAPBUTTON))
    appui, relache = (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) if gaucher else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
    _envoyer(_souris(appui), _souris(relache))


def zone_de_travail(x, y):
    """L'écran (sans la barre des tâches) qui contient ce point : (gauche, haut, droite, bas)."""
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]
    try:
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        ecran = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if ecran and user32.GetMonitorInfoW(ecran, ctypes.byref(info)):
            r = info.rcWork
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def fenetre_active():
    return user32.GetForegroundWindow()


def _classe(hwnd):
    tampon = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, tampon, 256)
    return tampon.value


def _titre(hwnd):
    tampon = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, tampon, 512)
    return tampon.value


def est_notre_fichier(hwnd):
    """La fenêtre qui affiche NOTRE fichier essai_clavier.txt (Bloc-notes, ou l'éditeur choisi par
    l'entreprise) : jamais un document de l'utilisateur, jamais un navigateur ni l'Explorateur."""
    if not hwnd:
        return False
    classe = _classe(hwnd)
    if classe in ("CabinetWClass", "ExploreWClass", "Chrome_WidgetWin_1", "MozillaWindowClass", "ConsoleWindowClass",
                  "CASCADIA_HOSTING_WINDOW_CLASS"):
        return False
    return FICHIER_CLAVIER.split(".")[0] in _titre(hwnd).lower()


def attendre_fenetre(test, secondes):
    fin = time.time() + secondes
    while time.time() < fin:
        hwnd = fenetre_active()
        if test(hwnd):
            return hwnd
        time.sleep(0.2)
    return None


def taper(texte, hwnd, delai=0.04):
    """Tape le texte, caractère par caractère, SEULEMENT tant que notre fichier est au premier plan :
    si une autre fenêtre passe devant, le robot s'arrête (il n'écrit jamais ailleurs)."""
    ecrits = 0
    for caractere in texte:
        active = fenetre_active()
        if active != hwnd or not est_notre_fichier(active):
            return ecrits, False
        if caractere == "\n":
            _envoyer(_touche(vk=VK_RETURN), _touche(vk=VK_RETURN, relache=True))
        else:
            donnees = caractere.encode("utf-16-le")
            for i in range(0, len(donnees), 2):
                unite = int.from_bytes(donnees[i:i + 2], "little")
                _envoyer(_touche(unite=unite), _touche(unite=unite, relache=True))
        ecrits += 1
        time.sleep(delai)
    return ecrits, True


def position_souris():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def deplacer_doucement(x, y, duree=0.5):
    x0, y0 = position_souris()
    pas = 25
    for i in range(1, pas + 1):
        user32.SetCursorPos(int(x0 + (x - x0) * i / pas), int(y0 + (y - y0) * i / pas))
        time.sleep(duree / pas)


def revenir_console():
    """Remet la fenêtre noire devant (cmd classique ; dans Windows Terminal, sa fenêtre visible)."""
    if not WINDOWS:
        return
    try:
        h = kernel32.GetConsoleWindow()
        if h and not user32.IsWindowVisible(h):
            h = user32.GetAncestor(h, GA_ROOTOWNER)
        if h and user32.IsWindowVisible(h):
            user32.SetForegroundWindow(h)
    except Exception:
        pass


def dossier_bureau():
    if WINDOWS:
        tampon = ctypes.create_unicode_buffer(260)
        try:
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, tampon) == 0 and tampon.value:
                return Path(tampon.value)
        except Exception:
            pass
    for p in (Path.home() / "Desktop", Path.home() / "Bureau"):
        if p.is_dir():
            return p
    return Path.home()


def effacer_dossier(chemin):
    """Efface un dossier temporaire du robot, en réessayant : sous Windows, le navigateur garde parfois
    des fichiers ouverts quelques instants après sa fermeture. Jamais d'erreur : au pire, il reste."""
    import shutil
    for _ in range(6):
        shutil.rmtree(chemin, ignore_errors=True)
        if not os.path.exists(chemin):
            return
        time.sleep(0.5)


def ouvrir_dans_windows(chemin):
    if WINDOWS:
        os.startfile(str(chemin))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(chemin)])
    else:
        subprocess.Popen(["xdg-open", str(chemin)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------- étapes 1 à 5
def etape_python(bilan):
    titre_etape(1, "Python fonctionne")
    detail = f"Python {platform.python_version()} {platform.architecture()[0]}, {platform.system()} {platform.release()}"
    ecrire("   " + detail)
    bilan.noter("P", "Python fonctionne", "OK", detail)


def etape_fichiers(bilan):
    titre_etape(2, "Fichiers et dossiers")
    dossier = dossier_bureau() / "Robot - essai"
    ecrire("   Le robot va creer le dossier « Robot - essai » sur votre Bureau, y ecrire")
    ecrire("   le fichier bonjour.txt, puis ouvrir ce dossier.")
    pause()
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "bonjour.txt").write_text(
            "Bonjour ! Ce fichier a ete cree par le robot le %s.\n"
            "Vous pouvez supprimer le dossier « Robot - essai » quand vous voulez.\n"
            % datetime.now().strftime("%d/%m/%Y a %H:%M"), encoding="utf-8")
    except Exception as e:
        bilan.noter("F", "Fichiers et dossiers", "ECHEC", erreur_courte(e))
        return dossier if dossier.is_dir() else None
    try:
        ouvrir_dans_windows(dossier)
    except Exception as e:
        bilan.noter("F", "Fichiers et dossiers", "PAS VU", "fichier cree, dossier pas ouvert : " + erreur_courte(e))
        return dossier
    time.sleep(1.5)
    revenez_ici()
    if oui("   Voyez-vous le dossier « Robot - essai » avec le fichier bonjour.txt ?"):
        bilan.noter("F", "Fichiers et dossiers", "OK")
    else:
        bilan.noter("F", "Fichiers et dossiers", "PAS VU", "fichier cree mais dossier pas vu a l'ecran")
    return dossier


def etape_clavier(bilan, dossier):
    titre_etape(3, "Le clavier : ecrire tout seul dans le Bloc-notes")
    if not WINDOWS:
        bilan.noter("K", "Clavier (Bloc-notes)", "NON DISPONIBLE", "pas Windows")
        return None
    ecrire("   Le robot va ouvrir SON fichier essai_clavier.txt dans le Bloc-notes et y ecrire")
    ecrire("   une phrase tout seul. Pendant qu'il ecrit (10 secondes) : NE TOUCHEZ NI AU CLAVIER")
    ecrire("   NI A LA SOURIS. (Si une autre fenetre passe devant, il s'arrete : il n'ecrit jamais")
    ecrire("   ailleurs que dans son fichier.)")
    pause()
    try:
        dossier = dossier if dossier is not None and dossier.is_dir() else Path(tempfile.gettempdir())
        fichier = dossier / FICHIER_CLAVIER
        fichier.write_text("", encoding="utf-8")
        subprocess.Popen(["notepad.exe", str(fichier)])
    except Exception as e:
        bilan.noter("K", "Clavier (Bloc-notes)", "ECHEC", "Bloc-notes impossible a ouvrir : " + erreur_courte(e))
        return None
    hwnd = attendre_fenetre(est_notre_fichier, 10)
    if not hwnd:
        ecrire("   Le Bloc-notes n'est pas passe devant. Cliquez sur son icone qui clignote en bas,")
        ecrire("   dans la barre des taches (la fenetre « essai_clavier »). Le robot attend 20 secondes...")
        hwnd = attendre_fenetre(est_notre_fichier, 20)
    if not hwnd:
        devant = fenetre_active()
        bilan.noter("K", "Clavier (Bloc-notes)", "ECHEC",
                    f"le fichier essai_clavier n'est jamais passe devant (fenetre devant : {_classe(devant) if devant else 'aucune'})")
        revenez_ici()
        return None
    time.sleep(1.2)  # le temps que la zone de texte soit prête à recevoir les touches
    try:
        ecrits, complet = taper("Bonjour ! Je suis le robot. J'ecris tout seul, sans toucher au clavier.\n"
                                "Avec les accents : é è à ç ù ê.\n", hwnd)
    except OSError as e:
        bilan.noter("K", "Clavier (Bloc-notes)", "ECHEC", str(e))
        revenez_ici()
        return hwnd
    revenez_ici()
    if not complet:
        ecrire(f"   Arrete apres {ecrits} caractere(s) : une autre fenetre est passee devant.")
    if oui("   Avez-vous vu la phrase s'ecrire toute seule dans le Bloc-notes ?"):
        bilan.noter("K", "Clavier (Bloc-notes)", "OK" if complet else "ECHEC",
                    "" if complet else f"interrompu apres {ecrits} caracteres (autre fenetre devant)")
    else:
        bilan.noter("K", "Clavier (Bloc-notes)", "PAS VU", f"{ecrits} caracteres envoyes, rien vu a l'ecran")
    return hwnd


def _ramener(hwnd):
    """Notre fichier au premier plan (restauré s'il a été réduit). Faux si ce n'est pas possible."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.5)
    user32.SetForegroundWindow(hwnd)
    if attendre_fenetre(lambda h: h == hwnd, 2):
        return True
    ecrire("   Cliquez sur l'icone du Bloc-notes « essai_clavier » en bas, dans la barre des taches,")
    ecrire("   puis LACHEZ LA SOURIS. Le robot attend 20 secondes...")
    if not attendre_fenetre(lambda h: h == hwnd and est_notre_fichier(h), 20):
        return False
    time.sleep(2)  # le temps de lâcher la souris
    return True


def etape_souris(bilan, hwnd):
    titre_etape(4, "La souris : bouger et cliquer toute seule")
    if not WINDOWS:
        bilan.noter("S", "Souris", "NON DISPONIBLE", "pas Windows")
        return
    ecrire("   Le robot va faire un carre avec la souris" + (", puis cliquer DANS son fichier" if hwnd else "")
           + (" et y ecrire une ligne." if hwnd else "."))
    ecrire("   NE TOUCHEZ PAS A LA SOURIS pendant 5 secondes. Il la remet ensuite ou elle etait.")
    pause()
    depart = position_souris()
    clic = "pas de Bloc-notes : mouvement seulement"
    try:
        if hwnd and not _ramener(hwnd):
            hwnd = None
        if hwnd:
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
        else:
            cx, cy = position_souris()
        gauche, haut, droite, bas = zone_de_travail(cx, cy)
        cx = min(max(cx, gauche + 130), droite - 130)
        cy = min(max(cy, haut + 90), bas - 90)
        carre = [(cx - 120, cy - 80), (cx + 120, cy - 80), (cx + 120, cy + 80), (cx - 120, cy + 80), (cx, cy)]
        bouge = True
        for x, y in carre:
            deplacer_doucement(x, y)
            px, py = position_souris()
            bouge = bouge and abs(px - x) <= 2 and abs(py - y) <= 2
        if hwnd:
            # on ne clique QUE si la souris est bien là où le robot l'a mise, sur NOTRE fichier, au premier plan
            px, py = position_souris()
            sous = user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(px, py)), GA_ROOT)
            if (bouge and abs(px - cx) <= 1 and abs(py - cy) <= 1 and sous == hwnd
                    and fenetre_active() == hwnd and est_notre_fichier(hwnd)):
                cliquer_ici()
                time.sleep(0.4)
                taper("\nLe robot a aussi bouge la souris et clique ici.\n", hwnd)
                clic = "clic fait dans le Bloc-notes"
            else:
                clic = "clic annule par prudence : le Bloc-notes n'etait pas sous la souris"
        deplacer_doucement(*depart, duree=0.3)
    except OSError as e:
        bilan.noter("S", "Souris", "ECHEC", str(e))
        revenez_ici()
        return
    revenez_ici()
    if not bouge:
        bilan.noter("S", "Souris", "ECHEC", "la souris n'est pas allee ou le robot voulait")
    elif oui("   Avez-vous vu la souris bouger toute seule" + (" et la ligne s'ecrire apres le clic ?" if hwnd else " ?")):
        bilan.noter("S", "Souris", "OK", clic)
    else:
        bilan.noter("S", "Souris", "PAS VU", clic)


def adresse_prudente(adresse):
    """Une adresse copiée juste après un clic peut être celle d'une ACTION (…/Plans/Suppression?id=5,
    …#/plans/5/supprimer) : l'ouvrir la referait. Dans ce cas, on ne garde que l'accueil du portail."""
    morceaux = urlsplit(adresse)
    reste = mots(unquote(" ".join((morceaux.path, morceaux.query, morceaux.fragment))))
    if VERBES_ACTION & set(reste.split()):
        return f"{morceaux.scheme}://{morceaux.netloc}/", True
    return adresse, False


def demander_adresse():
    ecrire()
    ecrire("=" * 70)
    ecrire(" L'ADRESSE DE VOTRE PORTAIL")
    ecrire("=" * 70)
    ecrire("   Dans votre Chrome, allez sur la page d'ACCUEIL du portail. Cliquez dans la barre")
    ecrire("   d'adresse tout en haut, faites Ctrl+C pour la copier. Revenez dans cette fenetre noire")
    ecrire("   et faites Ctrl+V pour la coller (ou clic droit, puis Coller), puis Entree.")
    ecrire("   Entree sans rien = sauter les etapes du portail.")
    ecrire("   (L'adresse n'est ecrite nulle part : elle sert seulement pendant ce test.)")
    adresse = demander("   Adresse du portail :").strip().strip('"')
    if not adresse:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", adresse, re.I):
        adresse = "https://" + adresse
    try:
        valable = bool(urlsplit(adresse).hostname)
        adresse, coupee = adresse_prudente(adresse)
    except ValueError:
        valable = False
    if not valable:
        ecrire("   Ce n'est pas une adresse de site : les etapes du portail sont sautees.")
        return ""
    if coupee:
        ecrire("   Cette adresse ressemble a celle d'une ACTION (supprimer, valider...). Par prudence,")
        ecrire("   le robot ouvrira seulement l'ACCUEIL du portail.")
    return adresse


def etape_navigateur_habituel(bilan, url):
    titre_etape(5, "Votre navigateur habituel")
    if not url:
        bilan.noter("W", "Portail dans votre navigateur", "SAUTE", "pas d'adresse donnee")
        return
    ecrire("   Le robot va ouvrir le portail dans VOTRE navigateur habituel (comme un clic sur un lien).")
    ecrire("   Ne tapez rien dans la page du portail : regardez seulement si elle s'ouvre.")
    pause()
    try:
        ouvert = webbrowser.open(url)
    except Exception as e:
        bilan.noter("W", "Portail dans votre navigateur", "ECHEC", masquer(premiere_ligne(e), url))
        return
    time.sleep(2.5)
    revenez_ici()
    if oui("   La page du portail s'est-elle ouverte dans votre navigateur ?"):
        bilan.noter("W", "Portail dans votre navigateur", "OK")
    else:
        bilan.noter("W", "Portail dans votre navigateur", "PAS VU" if ouvert else "ECHEC",
                    "" if ouvert else "Windows n'a pas trouve de navigateur par defaut")
    ecrire("   Vous pouvez fermer cet onglet du portail dans votre Chrome.")


# ---------------------------------------------------------------------------- étapes 6 à 8 : navigateur piloté
def _python_avec_playwright(chemin):
    try:
        return subprocess.call([str(chemin), "-c", "import playwright.sync_api"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60) == 0
    except Exception:
        return False


def trouver_python_playwright():
    """Le Python qui a le pilote de navigateur : celui-ci, ou celui du dossier robot-web déjà installé."""
    try:
        import playwright.sync_api  # noqa: F401
        return sys.executable
    except ImportError:
        pass
    ici = Path(__file__).resolve().parent
    bases = [ici, ici.parent, Path.home() / "Downloads", Path.home() / "Telechargements", Path.home() / "Téléchargements",
             dossier_bureau(), Path.home() / "Documents", Path.home()]
    for base in bases:
        for dossier in (base, base / "robot-web"):
            for morceaux in (("venv", "Scripts", "python.exe"), ("venv", "bin", "python")):
                candidat = dossier.joinpath(*morceaux)
                if candidat.is_file() and _python_avec_playwright(candidat):
                    return str(candidat)
    return None


def obtenir_python_playwright():
    ecrire("   Recherche du pilote de navigateur sur ce poste...")
    python = trouver_python_playwright()
    if python:
        return python
    ecrire("   Le pilote de navigateur (Playwright) n'est pas trouve sur ce poste.")
    ecrire("   Si vous avez un dossier robot-web : faites-le GLISSER dans cette fenetre noire,")
    ecrire("   puis Entree. Sinon, Entree sans rien.")
    chemin = demander("   Dossier robot-web :").strip().strip('"')
    if chemin:
        for morceaux in (("venv", "Scripts", "python.exe"), ("venv", "bin", "python")):
            candidat = Path(chemin).joinpath(*morceaux)
            if candidat.is_file() and _python_avec_playwright(candidat):
                return str(candidat)
        ecrire("   Pas de pilote de navigateur dans ce dossier.")
    commande = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location"]
    if sys.prefix == sys.base_prefix:  # pas dans un environnement à part : installation dans votre compte
        commande.append("--user")
    commande.append("playwright")
    ecrire("   Le robot peut l'installer depuis Internet (2 a 5 minutes, dans votre compte Windows,")
    ecrire("   sans droits d'administrateur) avec la commande :")
    ecrire("      python " + " ".join(commande[1:]))
    if not oui("   Tapez o pour l'installer, n pour sauter les etapes du navigateur.", "n"):
        return None
    if subprocess.call(commande) != 0:
        ecrire("   L'installation n'a pas abouti. Ce n'est pas grave : le robot continue.")
        ecrire("   Prenez aussi en photo les dernieres lignes ci-dessus.")
        return None
    return sys.executable if _python_avec_playwright(sys.executable) else None


def etape_navigateur_robot(bilan, url):
    titre_etape(6, "Le navigateur du robot")
    ecrire("   Le robot va ouvrir SON navigateur (une fenetre a part, vide, qui ne touche pas a")
    ecrire("   votre Chrome ni a vos mots de passe), puis remplir et cliquer une page d'essai.")
    pause()
    python = obtenir_python_playwright()
    if not python:
        for lettre, intitule in (("N", "Navigateur du robot (page d'essai)"), ("R", "Navigateur du robot sur le portail"),
                                 ("C", "Clic choisi sur le portail")):
            bilan.noter(lettre, intitule, "SAUTE", "pilote de navigateur absent", afficher=False)
        ecrire("   --> Etapes du navigateur sautees : pilote de navigateur absent.")
        return
    echange = Path(tempfile.mkdtemp(prefix="robot_essai_"))
    try:
        (echange / "adresse.txt").write_text(url or "", encoding="utf-8")  # jamais sur la ligne de commande
        interrompu = None
        try:
            enfant = subprocess.Popen([python, str(Path(__file__).resolve()), "--navigateur", str(echange)])
            try:
                enfant.wait()
            except KeyboardInterrupt as e:  # Ctrl+C : on laisse l'enfant noter où il en était
                interrompu = e
                try:
                    enfant.wait(timeout=5)
                except Exception:
                    enfant.kill()
        except Exception as e:
            bilan.noter("N", "Navigateur du robot (page d'essai)", "ECHEC", expliquer(e), afficher=False)
            return
        try:
            notes = json.loads((echange / "resultat.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            notes = [["N", "Navigateur du robot (page d'essai)", "ECHEC", "le programme du navigateur s'est arrete"]]
        for lettre, intitule, statut, detail in notes:
            if lettre in ("N", "D", "R", "C"):
                bilan.noter(lettre, intitule, statut, masquer(detail, url), afficher=False)
        if interrompu is not None:
            raise interrompu
    finally:
        effacer_dossier(echange)


PAGE_ESSAI = """<!doctype html><html lang=fr><meta charset=utf-8><title>Page d'essai du robot</title>
<style>body{font:18px Arial,sans-serif;margin:40px;background:#f4f6fb}label,button,input{font-size:20px}
input{padding:6px;margin:0 10px}button{padding:8px 18px;cursor:pointer}#reponse{margin-top:30px;font-size:26px;color:#15803d}</style>
<h1>Page d'essai du robot</h1>
<p>Le robot va écrire son nom dans le champ, puis cliquer sur « Valider ».</p>
<label for=prenom>Votre prénom</label><input id=prenom autocomplete=off><button id=valider>Valider</button>
<div id=reponse></div>
<script>document.getElementById('valider').onclick = () => {
  document.getElementById('reponse').textContent = 'Bonjour ' + document.getElementById('prenom').value + ', le clic a marché !';
};</script></html>"""

JS_STRUCTURE = r"""() => {
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const q = s => Array.from(document.querySelectorAll(s));
  const cliquables = q('a[href], button, input[type=submit], input[type=button], input[type=image], [role=button], ' +
                       '[role=link], [role=menuitem], [role=tab], [onclick]').filter(vis);
  let ombres = 0;
  for (const e of document.querySelectorAll('*')) if (e.shadowRoot) ombres++;
  return { cliquables: cliquables.length, champs: q('input:not([type=hidden]), select, textarea').filter(vis).length,
           frameset: !!document.querySelector('frameset'), ombres: ombres,
           dessins: q('canvas, embed, object').filter(vis).length };
}"""

JS_MARQUER_CLIQUABLES = """() => Array.from(document.querySelectorAll('a[href], button, input[type=submit], input[type=button], [role=button], [role=menuitem], [role=tab]'))
  .filter(e => { const r = e.getBoundingClientRect(); return r.width > 4 && r.height > 4 && r.top >= 0 && r.top < innerHeight; })
  .slice(0, 5).map(e => { e.setAttribute('data-robot-essai', '1'); return 1; }).length"""

JS_ENCADRER = """(e, ms) => { e.scrollIntoView({block: 'nearest', inline: 'nearest'});
  if (e.dataset.robotContour === undefined) e.dataset.robotContour = e.style.outline || '';
  e.style.outline = '4px solid #dc2626'; e.style.outlineOffset = '2px';
  if (ms > 0) setTimeout(() => { e.style.outline = e.dataset.robotContour || ''; e.style.outlineOffset = '';
                                 delete e.dataset.robotContour; }, ms); }"""

# Après les essais : le robot retire ses marques et ses cadres de la page.
JS_NETTOYER = """(tout) => { for (const e of document.querySelectorAll('[data-robot-cible], [data-robot-texte], [data-robot-essai], [data-robot-contour], [data-robot-trouve]')) {
  if (e.dataset.robotContour !== undefined) { e.style.outline = e.dataset.robotContour; e.style.outlineOffset = ''; }
  e.removeAttribute('data-robot-contour');
  if (tout) for (const a of ['data-robot-cible', 'data-robot-texte', 'data-robot-essai', 'data-robot-trouve']) e.removeAttribute(a);
} }"""

# Les éléments dont le PROPRE texte (sans celui de leurs sous-menus) est ce mot, majuscules ignorées.
JS_TROUVER_PROPRE_TEXTE = r"""([mot, jeton]) => {
  const norme = t => (t || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const cherche = norme(mot);
  for (const e of document.querySelectorAll('body *')) {
    let propre = '';
    for (const n of e.childNodes) if (n.nodeType === 3) propre += n.textContent;
    if (norme(propre) === cherche) e.setAttribute('data-robot-trouve', jeton);
  }
}"""

# L'élément trouvé par son texte -> l'élément que le clic déclencherait vraiment.
# LISTE BLANCHE : un lien, une entrée de menu / d'onglet, ou un élément d'un menu (nav, menu...), un bouton
# qui ouvre un menu. Refusé : bouton de formulaire, case, champ, bascule, zone modifiable, élément de tableau
# qui n'est pas un simple lien, élément qui contient un autre bouton (icône poubelle...).
# Les attributs de l'élément et les gestionnaires de clic de TOUS ses parents sont renvoyés pour le contrôle des mots.
JS_EXAMINER = r"""(e, jeton) => {
  const SOUS = 'ul, ol, [role=menu], [role=group], [role=listbox], table, select';
  const CLIQ = 'a, button, input, select, textarea, label, summary, option, [role=button], [role=link], [role=menuitem], ' +
               '[role=menuitemcheckbox], [role=menuitemradio], [role=tab], [role=treeitem], [role=checkbox], [role=switch], ' +
               '[role=radio], [role=option], [onclick]';
  const MENU = 'nav, header, [role=navigation], [role=menu], [role=menubar], [role=tablist], [role=tree], ' +
               '[class*=menu i], [id*=menu i], [class*=nav i], [id*=nav i], [class*=tab i]';
  const c = e.closest(CLIQ) || e;
  c.setAttribute('data-robot-cible', jeton);
  const tag = c.tagName.toLowerCase(), role = (c.getAttribute('role') || '').toLowerCase();
  const href = (c.getAttribute('href') || '').trim();
  const lien = tag === 'a' && c.hasAttribute('href') && !/^javascript:/i.test(href);
  const lienScript = tag === 'a' && /^javascript:/i.test(href);
  const entree = ['menuitem', 'tab', 'link', 'treeitem'].includes(role);
  const bouton = tag === 'button' || role === 'button';
  const menuBouton = bouton && !c.form && !c.closest('form') && (tag !== 'button' || c.type === 'button') &&
                     (c.hasAttribute('aria-haspopup') || c.hasAttribute('aria-expanded'));
  // un élément d'un menu, ou d'une liste (les menus sont presque toujours des listes ul > li)
  const dansMenu = !!(c.closest(MENU) || c.closest('li')) && ['li', 'span', 'div', 'a', 'p'].includes(tag);
  let refus = '';
  if (['input', 'select', 'textarea', 'label', 'summary', 'option'].includes(tag) ||
      ['checkbox', 'switch', 'radio', 'option', 'menuitemcheckbox', 'menuitemradio'].includes(role) ||
      c.hasAttribute('aria-checked') || c.hasAttribute('aria-pressed') || (bouton && !menuBouton))
    refus = 'bouton, case ou champ';
  else if (c.isContentEditable || document.designMode === 'on')
    refus = 'zone modifiable';
  else if (!(lien || entree || menuBouton || dansMenu || (lienScript && c.closest(MENU))))
    refus = 'pas un lien ni un menu';
  else if (!lien && c.closest('table, [role=grid], [role=row], [role=gridcell], [role=treegrid]'))
    refus = 'element de tableau';
  else if (c.hasAttribute('data-confirm') || c.hasAttribute('data-method') || c.hasAttribute('data-turbo-method') ||
           c.hasAttribute('data-ajax-method') || ['hx-post', 'hx-put', 'hx-patch', 'hx-delete'].some(a => c.hasAttribute(a)))
    refus = 'action envoyee au serveur';
  // le texte propre de l'élément (sous-menus à part), et ce qu'il contient
  const copie = c.cloneNode(true);
  copie.querySelectorAll(SOUS).forEach(x => x.remove());
  if (!refus && copie.querySelector('a[href], button, input, select, textarea, label, [role=button], [role=checkbox], [onclick]'))
    refus = 'contient un autre bouton';
  const texte = (copie.textContent || '').replace(/\s+/g, ' ').trim();
  const attributs = [];
  for (const n of [copie, ...copie.querySelectorAll('*')].slice(0, 80))
    for (const a of Array.from(n.attributes))
      if (a.name !== 'style' && !a.name.startsWith('data-robot')) attributs.push(a.name + ' ' + a.value);
  // les parents : leurs gestionnaires de clic, et le formulaire qui serait envoyé
  const GEST = /^(on(click|dblclick|mousedown|mouseup|pointerdown|pointerup|touchstart|touchend|submit))$|click|^hx-|^wire:|^x-on|^@|^data-(ajax|turbo|confirm|method|action|url)/i;
  for (let n = c.parentElement; n && n !== document.documentElement; n = n.parentElement)
    for (const a of Array.from(n.attributes))
      if (GEST.test(a.name)) attributs.push(a.name + ' ' + a.value);
  const formulaire = c.form || c.closest('form');
  if (formulaire) attributs.push('form ' + (formulaire.getAttribute('action') || ''));
  return { texte: texte.slice(0, 300), attributs: attributs.join(' | '), refus: refus };
}"""

# Le point où cliquer : le propre texte de l'élément (pas son centre, qui peut tomber sur un sous-menu).
# Marque le parent de ce texte (data-robot-texte) pour revérifier le même point au dernier moment.
JS_POINT = r"""(c, jeton) => {
  const SOUS = 'ul, ol, [role=menu], [role=group], [role=listbox], table, select';
  c.scrollIntoView({block: 'nearest', inline: 'nearest'});
  const rc = c.getBoundingClientRect();
  let r = null, p = c;
  const marcheur = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
  for (let n = marcheur.nextNode(); n; n = marcheur.nextNode()) {
    if (!n.textContent.trim()) continue;
    const parent = n.parentElement;
    if (parent && parent !== c && parent.closest(SOUS) && c.contains(parent.closest(SOUS))) continue;
    const plage = document.createRange(); plage.selectNodeContents(n);
    const b = plage.getBoundingClientRect();
    if (b.width > 0 && b.height > 0) { r = b; p = parent || c; break; }
  }
  if (!r) r = rc;
  p.setAttribute('data-robot-texte', jeton);
  return { x: r.left + Math.min(r.width / 2, 40) - rc.left, y: r.top + r.height / 2 - rc.top };
}"""

# Ce qui est sous la souris est-il bien le texte choisi (et pas un sous-menu ouvert par-dessus, un calque...) ?
JS_VERIFIER_POINT = r"""(c, [x, y, jeton]) => {
  const SOUS = 'ul, ol, [role=menu], [role=group], [role=listbox], table, select';
  const p = document.querySelector('[data-robot-texte="' + jeton + '"]');
  const rc = c.getBoundingClientRect();
  const sous = document.elementFromPoint(rc.left + x, rc.top + y);
  if (!p || !sous) return false;
  const liste = sous.closest(SOUS);
  return (sous === p || p.contains(sous)) && !(liste && liste !== p && p.contains(liste));
}"""

# Élément caché dans un menu fermé : l'entrée de menu visible la plus proche, à survoler (comme la souris).
JS_ENTREE_MENU = r"""e => {
  const vis = n => { const s = getComputedStyle(n); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = n.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  if (vis(e)) return null;
  let n = e.parentElement, haut = 1;
  while (n && !vis(n)) { n = n.parentElement; haut++; }
  if (!n || n === document.body || n === document.documentElement || haut > 12) return { haut: 0, enfant: -2 };
  const enfant = Array.from(n.children).findIndex(c => !c.contains(e) && vis(c) && (c.innerText || '').trim() &&
    !c.matches('ul, ol, [role=menu], [role=group], [role=listbox], .dropdown-menu, .submenu, .sub-menu'));
  return { haut: haut, enfant: enfant };
}"""


def _visible(loc):
    try:
        return loc.is_visible()
    except Exception:
        return False


def _encadrer(loc, ms=1200):
    try:
        loc.evaluate(JS_ENCADRER, ms)
        time.sleep(ms / 1000 + 0.2)
    except Exception:
        pass


def _taper_lentement(loc, texte):
    if hasattr(loc, "press_sequentially"):
        loc.press_sequentially(texte, delay=150)
    else:
        loc.type(texte, delay=150)


def _ouvrir_menus(loc):
    """Survole, de haut en bas, les entrées de menu qui cachent l'élément (4 niveaux au plus)."""
    deja = set()
    for _ in range(4):
        try:
            point = loc.evaluate(JS_ENTREE_MENU)
        except Exception:
            return False
        if not point:
            return True
        if point["enfant"] == -2 or (point["haut"], point["enfant"]) in deja:
            return False
        deja.add((point["haut"], point["enfant"]))
        entree = loc.locator("xpath=" + "/".join([".."] * point["haut"]))
        if point["enfant"] >= 0:
            entree = entree.locator(f"xpath=./*[{point['enfant'] + 1}]")
        try:
            entree.hover(timeout=3000)
            loc.wait_for(state="visible", timeout=1000)
            return True
        except Exception:
            continue
    return _visible(loc)


def _strategie_profil_impose(canal):
    """Stratégie d'entreprise « UserDataDir » : le navigateur ignorerait le profil vide du robot et
    ouvrirait VOTRE profil. Dans ce cas, le robot n'utilise pas ce navigateur."""
    if not WINDOWS or canal not in ("chrome", "msedge"):
        return False
    import winreg
    cle = r"SOFTWARE\Policies\Google\Chrome" if canal == "chrome" else r"SOFTWARE\Policies\Microsoft\Edge"
    for racine in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for vue in (winreg.KEY_WOW64_64KEY, 0):
            try:
                with winreg.OpenKey(racine, cle, 0, winreg.KEY_READ | vue) as k:
                    winreg.QueryValueEx(k, "UserDataDir")
                    return True
            except OSError:
                continue
    return False


class Notes:
    """Résultats des étapes 6 à 8, affichés au fil de l'eau et sauvés pour le programme principal."""

    def __init__(self, fichier):
        self.fichier = fichier
        self.liste = []

    def noter(self, lettre, intitule, statut, detail=""):
        detail = masquer(detail, self.url) if hasattr(self, "url") else masquer(detail)
        self.liste = [n for n in self.liste if n[0] != lettre]
        self.liste.append([lettre, intitule, statut, detail])
        ecrire(f"   --> {intitule} : {statut}" + (f"  ({detail})" if detail else ""))
        if statut == "ECHEC":
            ecrire("       Ce n'est pas grave : c'est justement ce qu'on cherche a savoir. On continue.")
        self.sauver()

    def statut(self, lettre):
        return next((n[2] for n in self.liste if n[0] == lettre), None)

    def sauver(self):
        try:
            self.fichier.write_text(json.dumps(self.liste, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def _ouvrir_navigateur(p, notes):
    essais = []
    for canal, nom in (("chrome", "Chrome"), ("msedge", "Edge"), (None, "le navigateur integre du robot")):
        if _strategie_profil_impose(canal):
            essais.append(f"{nom} : profil impose par l'entreprise, non utilise")
            ecrire(f"   {nom} : l'entreprise impose son profil ; le robot ne l'utilise pas (pour ne pas toucher au votre).")
            continue
        ecrire(f"   Ouverture du navigateur du robot avec {nom} (jusqu'a 30 secondes). Ne touchez a rien...")
        try:
            options = {"headless": INVISIBLE, "slow_mo": 0 if INVISIBLE else 120, "timeout": 30000}
            if canal:
                options["channel"] = canal
            navigateur = p.chromium.launch(**options)
            return navigateur, nom, canal, essais
        except Exception as e:
            raison = expliquer(e)
            essais.append(f"{nom} : {raison}")
            ecrire(f"   {nom} : impossible ({raison}).")
    notes.noter("N", "Navigateur du robot (page d'essai)", "ECHEC", " | ".join(essais))
    return None, "", None, essais


def _verifier_demarrage(p, canal, notes):
    """Chrome avec un profil (comme un robot qui garde votre connexion) : quels onglets s'ouvrent tout
    seuls au démarrage ? Une page Google imposée peut détourner un robot (« il ouvre Google et ne fait rien »)."""
    if canal is None:
        notes.noter("D", "Demarrage avec un profil", "NON DISPONIBLE", "seul le navigateur integre a demarre")
        return
    ecrire("   Controle rapide : une deuxieme fenetre s'ouvre puis se ferme toute seule (5 secondes)...")
    profil = tempfile.mkdtemp(prefix="robot_profil_")
    try:
        try:
            contexte = p.chromium.launch_persistent_context(profil, channel=canal, headless=INVISIBLE, timeout=30000)
        except Exception as e:
            notes.noter("D", "Demarrage avec un profil", "ECHEC", expliquer(e))
            return
        try:
            time.sleep(3)
            sortes = []
            for page in contexte.pages:
                adresse = (page.url or "").lower()
                hote = urlsplit(adresse).hostname or ""
                if adresse in ("", "about:blank") or adresse.startswith(("chrome://newtab", "chrome://new-tab-page",
                                                                           "edge://newtab", "chrome-search://")):
                    sortes.append("vide")
                elif "google." in hote:
                    sortes.append("google")
                elif adresse.startswith(("chrome://", "edge://")):
                    sortes.append("page du navigateur")
                else:
                    sortes.append("autre site")
            notes.noter("D", "Demarrage avec un profil", "OK",
                        f"{len(contexte.pages)} onglet(s) au demarrage : " + (", ".join(sortes) or "aucun"))
        finally:
            try:
                contexte.close()
            except Exception:
                pass
    finally:
        effacer_dossier(profil)


def _page_essai(page, nom, notes):
    page.set_content(PAGE_ESSAI)  # pas de fichier ni d'adresse file:// (souvent bloquées en entreprise)
    page.bring_to_front()
    champ = page.get_by_label("Votre prénom")
    _encadrer(champ, 800)
    champ.click()
    _taper_lentement(champ, "Robot")
    bouton = page.get_by_role("button", name="Valider")
    _encadrer(bouton, 800)
    bouton.click()
    page.get_by_text("Bonjour Robot, le clic a marché !").wait_for(timeout=5000)
    time.sleep(1.5)
    notes.noter("N", "Navigateur du robot (page d'essai)", "OK", f"avec {nom}")


def _analyser_portail(page, url, notes):
    """Étape 7. Renvoie vrai si le portail s'est affiché (l'étape 8 peut alors avoir lieu)."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        notes.noter("R", "Navigateur du robot sur le portail", "ECHEC", expliquer(e))
        return False
    page.bring_to_front()
    ecrire()
    ecrire("   La fenetre du robot (celle qui affichait la « Page d'essai du robot ») montre le portail.")
    ecrire("   SI le portail demande de vous connecter : connectez-vous DANS CETTE FENETRE-LA")
    ecrire("   (pas dans votre Chrome habituel). Le robot ne lit pas votre mot de passe, et cette")
    ecrire("   fenetre est oubliee a la fin.")
    pause("Quand vous voyez la page d'ACCUEIL du portail, revenez ici et appuyez sur Entree...")
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    total = {"cliquables": 0, "champs": 0, "ombres": 0, "dessins": 0}
    cadres_lus, cadres_illisibles, frameset = 0, 0, False
    meilleur, max_cliquables = None, -1
    for cadre in page.frames:
        try:
            s = cadre.evaluate(JS_STRUCTURE)
        except Exception:
            cadres_illisibles += 1
            continue
        cadres_lus += 1
        frameset = frameset or s["frameset"]
        for cle in total:
            total[cle] += s[cle]
        if s["cliquables"] > max_cliquables:
            meilleur, max_cliquables = cadre, s["cliquables"]
    detail = (f"{total['cliquables']} cliquables, {total['champs']} champs, {cadres_lus} cadre(s)"
              + (", frameset" if frameset else "")
              + (f", {cadres_illisibles} illisible(s)" if cadres_illisibles else "")
              + (f", {total['ombres']} composant(s) web" if total["ombres"] else "")
              + (f", {total['dessins']} zone(s) dessinee(s)" if total["dessins"] else ""))
    ecrire("   Le robot voit : " + detail)
    encadres = 0
    if meilleur is not None and max_cliquables > 0:
        ecrire("   Il encadre en rouge, un par un, quelques elements qu'il saurait cliquer (SANS cliquer)...")
        try:
            meilleur.evaluate(JS_MARQUER_CLIQUABLES)
            marques = meilleur.locator("[data-robot-essai]")
            for i in range(min(marques.count(), 5)):
                _encadrer(marques.nth(i), 900)
                encadres += 1
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 500)
            time.sleep(0.8)
            page.mouse.wheel(0, -500)
        except Exception:
            pass
    _nettoyer(page)
    if encadres:
        revenez_ici()
        vu = oui("   Avez-vous vu des cadres rouges apparaitre sur le portail, dans la fenetre du robot ?")
        notes.noter("R", "Navigateur du robot sur le portail", "OK" if vu else "PAS VU", detail)
    else:
        notes.noter("R", "Navigateur du robot sur le portail", "ECHEC",
                    detail + " ; aucun element cliquable classique (menus faits en JavaScript ?)")
    return True


def _candidats(page, mot):
    """Les éléments dont le texte est EXACTEMENT celui tapé, dans tous les cadres : texte complet,
    propre texte d'une entrée de menu (sous-menu à part), puis la même chose sans tenir compte des majuscules.
    Jamais un élément qui contient seulement ce mot (« plans » ne désigne pas « Suppression des plans »)."""
    exact_sans_casse = re.compile(r"^\s*" + re.escape(mot) + r"\s*$", re.IGNORECASE)
    jeton = secrets.token_hex(8)

    def propre_texte_sans_casse(cadre):
        cadre.evaluate(JS_TROUVER_PROPRE_TEXTE, [mot, jeton])
        return cadre.locator(f'[data-robot-trouve="{jeton}"]')

    facons = (
        lambda cadre: cadre.get_by_text(mot, exact=True),
        lambda cadre: cadre.locator("text=" + json.dumps(mot, ensure_ascii=False)),
        lambda cadre: cadre.get_by_text(exact_sans_casse),
        propre_texte_sans_casse,
    )
    for chercher in facons:
        trouves = []
        for numero, cadre in enumerate(page.frames):
            try:
                loc = chercher(cadre)
                for i in range(min(loc.count(), 10)):
                    trouves.append((numero, cadre, loc.nth(i)))
            except Exception:
                continue
        if trouves:
            return trouves
    return []


def _examiner(cadre, loc):
    """Fixe l'élément (il ne peut plus changer entre la vérification et le clic) et dit s'il peut être cliqué."""
    jeton = secrets.token_hex(8)
    try:
        info = loc.evaluate(JS_EXAMINER, jeton)
    except Exception:
        return None, "texte illisible"
    cible = cadre.locator(f'[data-robot-cible="{jeton}"]')
    if info["refus"]:
        return cible, info["refus"]
    if not info["texte"]:
        return cible, "texte illisible"
    if interdit(info["texte"]) or interdit(info["attributs"]):
        return cible, "ressemble a une action qui modifie"
    return cible, ""


def _choisir(trouves):
    """Le premier élément que le robot a le droit de cliquer, les visibles d'abord.
    Renvoie ((numéro du cadre, cadre, cible) ou None, raison du refus, nombre de visibles)."""
    visibles = [t for t in trouves if _visible(t[2])]
    refus = ""
    for numero_cadre, cadre, loc in (visibles + [t for t in trouves if t not in visibles])[:10]:
        cible, raison = _examiner(cadre, loc)
        if not raison:
            return (numero_cadre, cadre, cible), "", len(visibles)
        refus = refus or raison
    return None, refus, len(visibles)


def _cliquer_prudemment(page, cadre, cible):
    """Rouvre le menu si besoin, revérifie l'élément au dernier moment, pose la souris sur son texte,
    vérifie ce qui est VRAIMENT sous la souris, et seulement alors appuie. Renvoie "" si le clic est fait."""
    if cible.count() != 1:
        return "l'element a disparu de la page"
    if not _visible(cible) and not _ouvrir_menus(cible):
        return "toujours cache : menu ferme"
    cible2, refus = _examiner(cadre, cible)
    if refus or cible2 is None:
        return "refuse au dernier moment : " + (refus or "texte illisible")
    jeton = secrets.token_hex(8)
    point = cible2.evaluate(JS_POINT, jeton)
    cible2.hover(position=point, timeout=5000)  # la souris arrive sur le texte (un menu peut s'ouvrir)
    time.sleep(0.5)
    if not cible2.evaluate(JS_VERIFIER_POINT, [point["x"], point["y"], jeton]):
        return "refuse : autre chose est sous la souris (sous-menu ouvert par-dessus ?)"
    _, refus = _examiner(cadre, cible2)
    if refus:
        return "refuse au dernier moment : " + refus
    avant = len(page.context.pages)
    page.mouse.down()  # la souris ne bouge plus : appui et relâchement là où on a vérifié
    page.mouse.up()
    page.wait_for_timeout(1500)
    return "nouvel onglet" if len(page.context.pages) > avant else ""


def _nettoyer(page, tout=True):
    """Retire les cadres rouges (et, avec tout=True, les marques du robot) de toutes les zones de la page."""
    for cadre in page.frames:
        try:
            cadre.evaluate(JS_NETTOYER, tout)
        except Exception:
            pass


def _clic_choisi(page, notes):
    ecrire()
    ecrire("=" * 70)
    ecrire(" ETAPE 8 : un clic que VOUS choisissez sur le portail")
    ecrire("=" * 70)
    ecrire("   Tapez le texte EXACT d'un MENU ou d'un LIEN du portail, tel qu'il est ecrit")
    ecrire("   (par exemple GATES), accents compris. Le robot le cherche, l'encadre en rouge, et")
    ecrire("   vous demande avant de cliquer. Il ne clique que sur des liens et des menus : jamais")
    ecrire("   sur un bouton de formulaire, une case, ni sur Supprimer, Enregistrer, Valider, OK...")
    ecrire("   Pendant que vous repondez, ne passez pas la souris sur la fenetre du robot.")
    codes = []  # un code court par essai, pour le RESULTAT (jamais le mot tapé)
    while len(codes) < 5:
        mot = demander("   Texte a chercher (Entree sans rien = finir) :")
        if not mot:
            break
        n = len(codes) + 1
        if len(mot) < 3 or sans_accents(mot).lower() in ("oui", "non", "ok", "yes"):
            ecrire("   Tapez le texte d'un menu ou d'un lien (3 lettres au moins), pas une reponse o / n.")
            continue
        if interdit(mot):
            ecrire("   Refuse : ce mot ressemble a une action qui modifie. Choisissez un menu ou un lien.")
            codes.append(f"{n}:refus-mot")
            continue
        trouves = _candidats(page, mot)
        if not trouves:
            ecrire("   Pas trouve avec exactement ce texte. Recopiez-le tel qu'il est ecrit sur le portail")
            ecrire("   (accents compris). Si c'est dans un menu qui se deroule, tapez d'abord le nom du menu.")
            codes.append(f"{n}:introuvable")
            continue
        choix, refus, nb_visibles = _choisir(trouves)
        if choix is None:
            ecrire(f"   Refuse par prudence : {refus}.")
            codes.append(f"{n}:refus({refus.split()[0]})")
            continue
        numero_cadre, cadre, cible = choix
        ou = "dans la page" if numero_cadre == 0 else "dans une zone interieure de la page"
        cache = not _visible(cible)
        if cache:
            question = (f"   Trouve {ou}, mais cache dans un menu ferme. Le robot va survoler le menu pour l'ouvrir,"
                        " puis cliquer. Tapez o pour cliquer, n pour ne rien faire")
        else:
            if nb_visibles > 1:
                ecrire(f"   {nb_visibles} elements portent ce texte : le robot prend le premier qu'il a le droit de cliquer.")
            _encadrer(cible, 0)  # le cadre rouge reste pendant la question
            question = f"   Trouve {ou}, encadre en rouge. Tapez o pour que le robot clique dessus, n pour ne rien faire"
        revenez_ici()
        accord = oui(question, "n")
        _nettoyer(page, tout=False)  # le cadre rouge part ; la marque de la cible reste jusqu'au clic
        if not accord:
            codes.append(f"{n}:non-clique")
            continue
        try:
            souci = _cliquer_prudemment(page, cadre, cible)
        except Exception as e:
            souci = "clic en echec (" + expliquer(e) + ")"
        if souci and souci != "nouvel onglet":
            ecrire("   Pas de clic : " + souci + ".")
            codes.append(f"{n}:pas-de-clic")
            continue
        if souci == "nouvel onglet":
            page = page.context.pages[-1]
            try:
                page.bring_to_front()
            except Exception:
                pass
            ecrire("   Le clic a ouvert un nouvel onglet : le robot continue dans ce nouvel onglet.")
        ecrire("   Clic fait. Regardez la fenetre du robot : la page a-t-elle reagi comme avec votre souris ?")
        revenez_ici()
        reagi = oui("   Ca a marche ?")
        codes.append(f"{n}:clic" + ("-survol" if cache else "") + ("" if reagi else "-sans-effet"))
        _nettoyer(page)
    _nettoyer(page)
    if not codes:
        notes.noter("C", "Clic choisi sur le portail", "SAUTE", "aucun mot donne")
    else:
        bons = [c for c in codes if ":clic" in c and "sans-effet" not in c]
        notes.noter("C", "Clic choisi sur le portail", "OK" if bons else "ECHEC", " ".join(codes))


def sous_programme_navigateur(dossier_echange):
    """Étapes 6 à 8, lancées avec le Python qui a le pilote de navigateur."""
    preparer_console()
    echange = Path(dossier_echange)
    notes = Notes(echange / "resultat.json")
    try:
        url = (echange / "adresse.txt").read_text(encoding="utf-8").strip()
        (echange / "adresse.txt").unlink()
    except OSError:
        url = ""
    notes.url = url
    etape = ["N", "Navigateur du robot (page d'essai)"]
    navigateur = None
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            navigateur, nom, canal, _ = _ouvrir_navigateur(p, notes)
            if navigateur is None:
                for lettre, intitule in (("D", "Demarrage avec un profil"), ("R", "Navigateur du robot sur le portail"),
                                         ("C", "Clic choisi sur le portail")):
                    notes.noter(lettre, intitule, "SAUTE", "navigateur du robot impossible a ouvrir")
                return 1
            page = navigateur.new_context(no_viewport=True).new_page()
            try:
                _page_essai(page, nom, notes)
            except Exception as e:
                notes.noter("N", "Navigateur du robot (page d'essai)", "ECHEC", f"avec {nom} : " + expliquer(e))
            if notes.statut("N") == "OK":
                revenez_ici()
                if not oui("   Avez-vous vu le robot ecrire « Robot » et cliquer sur Valider ?"):
                    notes.noter("N", "Navigateur du robot (page d'essai)", "PAS VU", f"avec {nom}")
            etape[:] = ["D", "Demarrage avec un profil"]
            try:
                _verifier_demarrage(p, canal, notes)
            except Exception as e:  # ce contrôle ne doit jamais empêcher les étapes du portail
                notes.noter("D", "Demarrage avec un profil", "ECHEC", expliquer(e))
            titre_etape(7, "Le navigateur du robot sur votre portail")
            if not url:
                notes.noter("R", "Navigateur du robot sur le portail", "SAUTE", "pas d'adresse donnee")
                notes.noter("C", "Clic choisi sur le portail", "SAUTE", "pas d'adresse donnee")
            else:
                etape[:] = ["R", "Navigateur du robot sur le portail"]
                if _analyser_portail(page, url, notes):
                    etape[:] = ["C", "Clic choisi sur le portail"]
                    _clic_choisi(page, notes)
                else:
                    notes.noter("C", "Clic choisi sur le portail", "SAUTE", "portail non affiche")
            pause("Fin des essais du navigateur. Entree pour fermer la fenetre du robot...")
            try:
                navigateur.close()
            except Exception:
                pass
    except KeyboardInterrupt:
        notes.noter(etape[0], etape[1], "ECHEC", "arrete par Ctrl+C")
        return 130
    except Exception as e:
        notes.noter(etape[0], etape[1], "ECHEC", expliquer(e))
    return 0


# ---------------------------------------------------------------------------- programme principal
def principal():
    preparer_console()
    rendre_net()
    ancien_mode = edition_rapide_coupee()
    ecrire("=" * 70)
    ecrire(" PRISE EN MAIN DU ROBOT (version %s)" % VERSION)
    ecrire("=" * 70)
    ecrire(" Le robot va montrer, une chose a la fois, qu'il sait se servir de votre")
    ecrire(" ordinateur : fichiers, clavier, souris, navigateur. Il ne modifie RIEN dans vos")
    ecrire(" outils. Avant chaque etape, il explique et attend votre Entree.")
    ecrire(" Quand il pose une question : cliquez d'abord dans CETTE fenetre noire, puis repondez.")
    ecrire(" Pour arreter a tout moment : Ctrl + C dans cette fenetre.")
    bilan = Bilan()
    etat = {"dossier": None, "hwnd": None, "url": ""}

    def etape(lettre, intitule, faire):
        """Une étape qui plante inopinément est notée ECHEC ; les suivantes ont quand même lieu."""
        try:
            faire()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            bilan.noter(lettre, intitule, "ECHEC", "erreur imprevue : " + (erreur_courte(e) if isinstance(e, OSError)
                                                                             else masquer(premiere_ligne(e))))

    try:
        etape("P", "Python fonctionne", lambda: etape_python(bilan))
        etape("F", "Fichiers et dossiers", lambda: etat.update(dossier=etape_fichiers(bilan)))
        etape("K", "Clavier (Bloc-notes)", lambda: etat.update(hwnd=etape_clavier(bilan, etat["dossier"])))
        etape("S", "Souris", lambda: etape_souris(bilan, etat["hwnd"]))
        etape("W", "Portail dans votre navigateur", lambda: etat.update(url=demander_adresse()))
        etape("W", "Portail dans votre navigateur", lambda: etape_navigateur_habituel(bilan, etat["url"]))
        etape("N", "Navigateur du robot (page d'essai)", lambda: etape_navigateur_robot(bilan, etat["url"]))
    except KeyboardInterrupt:
        ecrire("\n   Arrete a votre demande.")
    dossier = etat["dossier"]
    texte = bilan.texte()
    # la photo ne doit montrer que le résultat (ni l'adresse, ni les mots tapés plus haut) : des lignes
    # vides d'abord (marche partout), puis l'effacement de l'écran si la fenêtre le permet
    ecrire("\n" * 60)
    if WINDOWS:
        try:
            os.system("cls")
        except Exception:
            pass
    ecrire("=" * 70)
    ecrire(texte)
    ecrire("=" * 70)
    ecrire(" PRENEZ CE RESULTAT EN PHOTO et envoyez-le-moi.")
    if dossier is not None:
        try:
            (dossier / "resultat_prise_en_main.txt").write_text(texte + "\n", encoding="utf-8")
            ecrire(" Il est aussi ecrit dans : Bureau > Robot - essai > resultat_prise_en_main.txt")
        except OSError:
            pass
    ecrire(" Vous pouvez fermer le Bloc-notes (essai_clavier) ; enregistrer ou non, peu importe.")
    remettre_console(ancien_mode)
    demander("\n Entree pour terminer.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--navigateur"] and len(sys.argv) >= 3:
        sys.exit(sous_programme_navigateur(sys.argv[2]))
    sys.exit(principal())

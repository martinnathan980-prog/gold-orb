# -*- coding: utf-8 -*-
# ROBOT - lancement :  python robot.txt   (1 = test, 2 = releve des pages, 3 = lancer une tache)
# Il ne modifie rien sur le portail sans votre accord ; tout ce qu'il ecrit est dans Bureau > Robot.

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
from urllib.parse import unquote, urljoin, urlsplit

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
    r"approuv|approb|approv|\bsigner|\bsign\b|\bsignature|\bassocier|\bassociation|rattach|attach|joindre|detach|\bimport|"
    r"\breviser\b|\bliberer|\brelease|verrou|\block|unlock|bascul|clotur|\bclore|\bclos\b|ferm|\bclose|"
    r"mettre a jour|mise a jour|\bmaj\b|update|upgrade|reinitialis|reset|\braz\b|restaur|restore|\blancer|execut|"
    r"\brun\b|\bstart|demarr|arret|\bstop\b|activer|desactiv|activate|deactivat|\benable|\bdisable|affect|assign|"
    r"attribu|\baccept|refus|declin|\bterminer|finish|\bcompleter|\bcomplete\b|resolu|resou|resolv|appliqu|"
    r"\bapply|upload|televers|\bdepos|deplac|\bmove\b|renomm|rename|rempla|replace|\bgenerer|regener|generat|"
    r"\bcommander|\border\b|\bpayer|paiement|\bpay\b|factur|repond|reply|\bcommenter|relanc|prise en charge|"
    r"prendre en charge|\btraiter|\btraite\b|synchro|recalcul|fusion|merge|deploy|deploi|abandon|revoq|revok|"
    r"autoris|inscri|mise en|mettre en|\bdissocier|unlink|enlev|resili|\bradier|radiation|suspend|\bbloqu|debloqu|"
    r"ecras|\bexclu|\bdelier|declass|rebut|remettre a zero|\bcontinuer\b|poursuiv|"
    r"^oui\b|^ok\b|^yes\b|^non$|^no$|^go$",
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


# expressions qui contiennent un mot d'action mais ne modifient rien
NEUTRES = ("nouvelle recherche", "new search", "afficher les nouveautes", "nouveautes")


def interdit(texte):
    t = " " + mots(texte) + " "
    for phrase in NEUTRES:
        t = t.replace(" " + phrase + " ", " ")
    return bool(MOTS_INTERDITS.search(t.strip()))


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


def oui(question, defaut=""):
    """o ou n. Sans défaut (questions « avez-vous vu ? »), Entrée seule redemande : on ne note jamais OK par erreur."""
    while True:
        reponse = demander(f"{question} (o/n)" + (f" [{defaut}]" if defaut else "") + " :", defaut).lower()
        if reponse[:1] in ("o", "y", "n"):
            return reponse[:1] != "n"
        ecrire("   Repondez o ou n.")


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
ORDRE = "PFKSWNDRCV"


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
    dossier = dossier_bureau() / "Robot"
    ecrire("   Le robot va creer le dossier « Robot » sur votre Bureau, y ecrire")
    ecrire("   le fichier bonjour.txt, puis ouvrir ce dossier.")
    pause()
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "bonjour.txt").write_text(
            "Bonjour ! Ce fichier a ete cree par le robot le %s.\n"
            "Le robot range ici tout ce qu'il ecrit (releves, resultats des taches).\n"
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
    if oui("   Voyez-vous le dossier « Robot » avec le fichier bonjour.txt ?"):
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
        ecrire("   Cliquez sur l'icone du Bloc-notes « essai_clavier » en bas, dans la barre des taches,")
        ecrire("   puis LACHEZ LA SOURIS. Le robot attend 20 secondes...")
        hwnd = attendre_fenetre(est_notre_fichier, 20)
        if hwnd:
            time.sleep(2)  # le temps de lâcher la souris
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
    precedente = adresse_retenue()
    if precedente:
        ecrire("   Entree sans rien = la meme adresse que la derniere fois.")
    else:
        ecrire("   Entree sans rien = sauter les etapes du portail.")
    ecrire("   (L'adresse reste sur ce poste, dans Bureau > Robot ; elle n'est jamais dans le RESULTAT.)")
    adresse = demander("   Adresse du portail :").strip().strip('"') or precedente
    if not adresse:
        return ""
    if adresse.count("://") > 1 or " " in adresse:
        ecrire("   Ce n'est pas une adresse (collee deux fois ?). Recommencez : Ctrl+V une seule fois.")
        return demander_adresse()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", adresse, re.I):
        if "." not in adresse:
            ecrire("   Ce n'est pas une adresse. Copiez-la dans la barre d'adresse de Chrome (Ctrl+C), puis Ctrl+V ici.")
            return demander_adresse()
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
    retenir_adresse(adresse)
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


RAISON_PILOTE = ["pilote de navigateur absent"]


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
    ecrire("      python " + " ".join(commande[1:]) + "   (rien a taper : le robot la lance lui-meme)")
    if not oui("   Tapez o pour l'installer, n pour sauter les etapes du navigateur.", "n"):
        return None
    if subprocess.call(commande) != 0 or not _python_avec_playwright(sys.executable):
        ecrire("   L'installation n'a pas abouti.")
        pause("Prenez en photo les lignes ci-dessus, puis Entree...")
        RAISON_PILOTE[0] = "installation du pilote echouee"
        return None
    return sys.executable


def etape_navigateur_robot(bilan, url):
    titre_etape(6, "Le navigateur du robot")
    ecrire("   Le robot va ouvrir SON navigateur (une fenetre a part, vide, qui ne touche pas a")
    ecrire("   votre Chrome ni a vos mots de passe), puis remplir et cliquer une page d'essai.")
    pause()
    python = obtenir_python_playwright()
    if not python:
        for lettre, intitule in (("N", "Navigateur du robot (page d'essai)"), ("R", "Navigateur du robot sur le portail"),
                                 ("C", "Clic choisi sur le portail")):
            bilan.noter(lettre, intitule, "ECHEC" if "echouee" in RAISON_PILOTE[0] else "SAUTE", RAISON_PILOTE[0],
                        afficher=False)
        ecrire(f"   --> Etapes du navigateur sautees : {RAISON_PILOTE[0]}.")
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
            if lettre in ("N", "D", "R", "C", "V"):
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
  // vieux portails : menus faits de li / span avec la main de la souris (curseur « pointer »)
  for (const e of q('li, span, div, td').slice(0, 3000))
    if (!cliquables.includes(e) && vis(e) && getComputedStyle(e).cursor === 'pointer' &&
        !(e.parentElement && getComputedStyle(e.parentElement).cursor === 'pointer')) cliquables.push(e);
  let ombres = 0;
  for (const e of document.querySelectorAll('*')) if (e.shadowRoot) ombres++;
  return { cliquables: cliquables.length, champs: q('input:not([type=hidden]), select, textarea').filter(vis).length,
           frameset: !!document.querySelector('frameset'), ombres: ombres,
           dessins: q('canvas, embed, object').filter(vis).length };
}"""

JS_MARQUER_CLIQUABLES = """() => Array.from(document.querySelectorAll('a[href], button, input[type=submit], input[type=button], [role=button], [role=menuitem], [role=tab], [onclick], li, span'))
  .filter(e => { const r = e.getBoundingClientRect(); if (!(r.width > 4 && r.height > 4 && r.top >= 0 && r.top < innerHeight)) return false;
                 if (['LI', 'SPAN'].includes(e.tagName) && !e.hasAttribute('onclick')) return getComputedStyle(e).cursor === 'pointer' &&
                   !(e.parentElement && getComputedStyle(e.parentElement).cursor === 'pointer');
                 return true; })
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
        if self.fichier is None:
            return
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
            ecrire(f"   {nom} : impossible ({raison}). Le robot essaie autre chose...")
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
        attendre_portail(page)
    except ErreurTache:
        notes.noter("R", "Navigateur du robot sur le portail", "ECHEC", "toujours sur la page de connexion")
        return False
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
                    etape[:] = ["V", "Releve des pages (pour Claude)"]
                    titre_etape(9, "Releve des pages du portail (pour Claude)")
                    fichier, nombre = boucle_releve(page)
                    if fichier:
                        notes.noter("V", "Releve des pages (pour Claude)", "OK",
                                    f"{nombre} page(s) : Bureau > Robot > A_ENVOYER_releve.txt")
                    else:
                        notes.noter("V", "Releve des pages (pour Claude)", "SAUTE", "aucune page relevee")
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


# ---------------------------------------------------------------------------- outils communs au relevé et aux tâches
def dossier_robot(*sous):
    """Bureau > Robot (et ses sous-dossiers) : tout ce que le robot écrit est là."""
    d = dossier_bureau() / "Robot"
    for s in sous:
        d = d / s
    d.mkdir(parents=True, exist_ok=True)
    return d


def adresse_retenue():
    try:
        url = (dossier_robot() / "adresse_portail.txt").read_text(encoding="utf-8-sig").strip().lstrip("\ufeff")
    except (OSError, UnicodeDecodeError):
        return ""
    try:
        return url if re.match(r"^https?://", url, re.I) and urlsplit(url).hostname else ""
    except ValueError:
        return ""


def retenir_adresse(url):
    if url:
        try:
            (dossier_robot() / "adresse_portail.txt").write_text(url, encoding="utf-8")
        except OSError:
            pass


def adresse_du_portail():
    """L'adresse retenue la dernière fois ; sinon on la demande (et on la retient)."""
    url = adresse_retenue()
    if url:
        ecrire(f"   Adresse du portail : {url}")
        ecrire("   (pour la changer : supprimez Bureau > Robot > adresse_portail.txt, puis relancez)")
        return url
    url = demander_adresse()
    retenir_adresse(url)
    return url


def _champ_mot_de_passe(page):
    for cadre in page.frames:
        try:
            if cadre.locator("input[type=password]").filter(visible=True).count():
                return True
        except Exception:
            try:
                loc = cadre.locator("input[type=password]")
                if any(_visible(loc.nth(i)) for i in range(min(loc.count(), 5))):
                    return True
            except Exception:
                continue
    return False


def attendre_chargement(page, secondes=10):
    for etat in ("domcontentloaded", "networkidle"):
        try:
            page.wait_for_load_state(etat, timeout=int(secondes * 1000))
        except Exception:
            pass
    try:
        page.wait_for_timeout(400)  # (attente qui laisse aussi passer les fenêtres du portail)
    except Exception:
        time.sleep(0.4)


def attendre_portail(page):
    """Si le portail affiche une page de connexion, on attend que vous vous connectiez DANS la fenêtre du robot."""
    attendre_chargement(page)
    attendu = False
    for _ in range(5):
        if not _champ_mot_de_passe(page):
            return attendu
        attendu = True
        ecrire()
        ecrire("   Le portail demande de vous connecter : connectez-vous DANS LA FENETRE DU ROBOT.")
        pause("Quand vous voyez l'accueil du portail, revenez ici et appuyez sur Entree...")
        attendre_chargement(page)
    raise ErreurTache("toujours sur la page de connexion")


def ouvrir_robot(p):
    """Le navigateur du robot (Chrome, sinon Edge, sinon le navigateur intégré) et sa page. Sans profil :
    rien de votre Chrome n'est lu ni gardé."""
    notes = Notes(None)
    navigateur, nom, _, _ = _ouvrir_navigateur(p, notes)
    if navigateur is None:
        raise ErreurTache("le navigateur du robot ne s'ouvre pas sur ce poste (faites le test : choix 1)")
    contexte = navigateur.new_context(no_viewport=True, accept_downloads=True)
    return navigateur, contexte, contexte.new_page()


# ---------------------------------------------------------------------------- relevé des pages (pour Claude)
# STRUCTURE seulement : noms des menus, onglets, champs, boutons, colonnes de tableaux, libellés d'une fiche.
# Jamais une valeur : ni le contenu des champs, ni les cellules des tableaux, ni les choix des listes.
JS_BARRES = r"""() => {
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const propre = e => { let t = ''; for (const n of e.childNodes) if (n.nodeType === 3) t += n.textContent;
                        t = t.replace(/\s+/g, ' ').trim();
                        if (!t) { const l = e.querySelector(':scope > a, :scope > span, :scope > div, :scope > button');
                                  if (l) t = (l.textContent || '').replace(/\s+/g, ' ').trim(); }
                        return t; };
  // une barre de menu : une liste de 2 à 15 entrées courtes, côte à côte, en haut de la page (ou dans un menu)
  const MENU = 'nav, header, [role=navigation], [role=menubar], [class*=menu i], [id*=menu i], [class*=nav i]';
  const entrees = [];
  for (const ul of document.querySelectorAll('ul, ol, [role=menubar]')) {
    if (ul.parentElement && ul.parentElement.closest('li')) continue;          // un sous-menu, pas une barre
    const lis = Array.from(ul.children).filter(li => vis(li));
    if (lis.length < 2 || lis.length > 15) continue;
    const hauts = lis.map(li => Math.round(li.getBoundingClientRect().top));
    const enLigne = Math.max(...hauts) - Math.min(...hauts) <= 6;
    const enHaut = ul.getBoundingClientRect().top < 260 || !!ul.closest(MENU);
    if (!enLigne || !enHaut) continue;
    if (!lis.every(li => { const t = propre(li); return t && t.length <= 30; })) continue;
    for (const li of lis) { li.setAttribute('data-robot-barre', String(entrees.length)); entrees.push(propre(li)); }
  }
  return entrees;
}"""

JS_SOUS_MENU = r"""(li) => {
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const propre = e => { let t = ''; for (const n of e.childNodes) if (n.nodeType === 3) t += n.textContent;
                        t = t.replace(/\s+/g, ' ').trim();
                        if (!t) { const l = e.querySelector(':scope > a, :scope > span, :scope > div, :scope > button');
                                  if (l) t = (l.textContent || '').replace(/\s+/g, ' ').trim(); }
                        return t; };
  const vus = [];
  const h = x => (x && x.getAttribute('href')) || '';
  const enregistrement = x => /^(tel|mailto):/i.test(h(x)) || /[?&][^=&]+=([^&]*\d{2,}|[A-Za-z]+-\d+)/.test(h(x)) ||
                              /\/\d{2,}(\/|$|\?)/.test(h(x));
  for (const e of li.querySelectorAll('li, [role=menuitem]')) {
    if (e === li || !vis(e)) continue;
    const t = enregistrement(e.querySelector('a') || e.closest('a')) ? '(donnee masquee)' : propre(e);
    if (t && !vus.includes(t)) vus.push(t);
  }
  return vus;
}"""

JS_RELEVE = r"""() => {
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const court = t => (t || '').replace(/\s+/g, ' ').trim();
  const sansChamps = n => { const c = n.cloneNode(true);
    c.querySelectorAll('select, option, input, textarea, button, script, style').forEach(x => x.remove()); return court(c.textContent); };
  // une ligne de DONNÉES d'un tableau : son contenu n'est jamais relevé. Ne sont pas des données : un tableau
  // de mise en page (qui contient d'autres tableaux), la ligne des titres, une ligne de formulaire, une ligne de fiche « Statut : »
  const ligneDeDonnees = e => { if (e.closest('[role=row], [role=gridcell]')) return true;
    const tr = e.closest('tr'); if (!tr) return false; const t = tr.closest('table');
    if (!t || t.querySelector('table') || tr.closest('thead')) return false;
    const premiere = t.querySelector('tr');
    const titres = !!t.querySelector('thead th') || (premiere && premiere.children.length > 1 &&
                   Array.from(premiere.children).every(c => c.tagName === 'TH'));
    if (tr === premiere && (titres || !premiere.querySelector('td'))) return false;     // la ligne des titres
    const corps = Array.from(t.querySelectorAll('tr')).filter(l => l.querySelector('td'));
    if (titres && corps.length >= 2) return true;      // tableau à titres : chaque ligne est un enregistrement
    if (tr.querySelector('input:not([type=hidden]), select, textarea')) return false;   // ligne de formulaire
    const c = tr.querySelector('td, th'); if (c && /:\s*$/.test(c.textContent || '')) return false;   // fiche
    return true; };
  const MENU = 'nav, header, [role=navigation], [role=menu], [role=menubar], [class*=menu i], [id*=menu i], [data-robot-barre]';
  const libelleDe = e => {
    if (e.id) { try { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l && sansChamps(l)) return sansChamps(l); } catch (x) {} }
    const p = e.closest('label'); if (p && sansChamps(p)) return sansChamps(p);
    const a = e.getAttribute('aria-label'); if (a) return court(a);
    const ph = e.getAttribute('placeholder'); if (ph) return court(ph) + ' (indice)';
    const cell = e.closest('td');
    // la cellule voisine sert de libellé seulement si elle finit par « : », ou si le champ est vide (formulaire de
    // recherche) : à côté d'un champ déjà rempli, c'est souvent une donnée de la fiche
    if (cell && cell.previousElementSibling && (/:\s*$/.test(cell.previousElementSibling.textContent || '') ||
        (cell.parentElement.children.length <= 3 && !(e.value || '').trim()))) {
      const t = sansChamps(cell.previousElementSibling); if (t && t.length < 50) return t; }
    const prev = e.previousElementSibling; if (prev && !['INPUT', 'SELECT', 'TEXTAREA'].includes(prev.tagName)) { const t = sansChamps(prev); if (t && t.length < 50) return t; }
    return e.getAttribute('title') || '(sans nom)';
  };
  const enregistrement = a => { const h = (a && a.getAttribute && a.getAttribute('href')) || '';
    return /^(tel|mailto|callto|sip):/i.test(h) || /[?&][^=&]+=([^&]*\d{2,}|[A-Za-z]+-\d+)/.test(h) || /\/\d{2,}(\/|$|\?)/.test(h); };
  const nomDe = e => enregistrement(e.closest('a') || e.querySelector('a')) ? '(donnee masquee)' : court(e.textContent);
  const r = { autresMenus: [], onglets: [], champs: [], boutons: [], tableaux: [], libelles: [], liens: [],
              cadres: document.querySelectorAll('iframe, frame').length };
  for (const e of document.querySelectorAll('nav a, [role=menuitem], [class*=menu i] a, [id*=menu i] a')) {
    if (!vis(e) || ligneDeDonnees(e) || e.closest('[data-robot-barre]')) continue;
    r.autresMenus.push(nomDe(e));
  }
  for (const e of document.querySelectorAll('[role=tab], [class*=onglet i] a, [class*=onglet i] li, [class*=tabs i] a, [class*=tabs i] li'))
    if (vis(e) && !ligneDeDonnees(e)) r.onglets.push(nomDe(e));
  for (const e of document.querySelectorAll('input, select, textarea')) {
    const type = (e.getAttribute('type') || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type) || !vis(e) || ligneDeDonnees(e)) continue;
    let genre = e.tagName === 'SELECT' ? 'liste de ' + e.options.length + ' choix' : (e.tagName === 'TEXTAREA' ? 'texte long' : (type || 'texte'));
    if (type === 'password') genre = 'mot de passe';
    r.champs.push(libelleDe(e) + ' [' + genre + (e.required ? ', obligatoire' : '') + (e.readOnly || e.disabled ? ', lecture seule' : '') + ']');
  }
  const listeDeDonnees = e => !!e.closest('li') && !e.closest(MENU) && !e.closest('[class*=onglet i], [class*=tabs i], [role=tablist]');
  for (const e of document.querySelectorAll('button, input[type=submit], input[type=button], input[type=reset], [role=button]')) {
    if (!vis(e) || ligneDeDonnees(e) || listeDeDonnees(e)) continue;
    const texte = e.tagName === 'INPUT' ? court(e.value) : court(e.textContent);
    const bulle = court(e.getAttribute('title') || e.getAttribute('aria-label') || '');
    r.boutons.push(texte && /[A-Za-zÀ-ÿ]/.test(texte) ? texte : (bulle ? '(icone) ' + bulle : '(icone sans nom)'));
  }
  for (const t of document.querySelectorAll('table, [role=grid]')) {
    if (!vis(t) || t.parentElement.closest('table td')) continue;
    let entetes = Array.from(t.querySelectorAll('thead th, [role=columnheader]'));
    if (!entetes.length) { const l = t.querySelector('tr'); if (l && l.children.length > 1 && Array.from(l.children).every(c => c.tagName === 'TH')) entetes = Array.from(l.children); }
    if (!entetes.length) continue;
    const lignes = Array.from(t.querySelectorAll('tr, [role=row]')).filter(l => l.querySelector('td, [role=gridcell]'));
    const colonnes = entetes.map((h, i) => { let n = court(h.textContent) || '(sans titre)';
      const exemple = lignes.find(l => l.children.length === entetes.length);
      if (exemple && exemple.children[i]) { const c = exemple.children[i];
        if (c.querySelector('a[href]')) n += ' (lien)';
        if (c.querySelector('input:not([type=hidden]), select, textarea')) n += ' (champ a remplir)';
        const actions = Array.from(c.querySelectorAll('button, input[type=button], input[type=submit], [role=button], a[title], img[title]'))
          .map(b => { const x = b.tagName === 'INPUT' ? court(b.value) : court(b.textContent);
                      return x && /[A-Za-zÀ-ÿ]/.test(x) && b.tagName !== 'A' ? 'bouton ' + x.split(' ').slice(0, 2).join(' ')
                        : (b.getAttribute('title') ? 'icone ' + court(b.getAttribute('title')).split(' ')[0] : ''); })
          .filter(Boolean);
        if (actions.length) n += ' (' + actions.join(', ') + ')'; }
      return n; });
    const vide = lignes.length === 1 && lignes[0].children.length === 1 &&
                 /aucun|aucune|vide|pas de|no data|no record|empty/i.test(lignes[0].textContent || '');
    r.tableaux.push({ colonnes: colonnes, lignes: vide ? 0 : lignes.length });
  }
  // libellés d'une fiche (« Statut : » ...) : le libellé seulement, jamais la valeur à côté
  for (const e of document.querySelectorAll('td, th, dt, label, span, b, strong, div, p')) {
    if (!vis(e) || ligneDeDonnees(e) || e.closest(MENU)) continue;
    let propre = ''; for (const n of e.childNodes) if (n.nodeType === 3) propre += n.textContent;
    propre = court(propre);
    if (propre && /:$/.test(propre) && propre.length <= 30) r.libelles.push(propre.replace(/\s*:$/, ''));
  }
  for (const a of document.querySelectorAll('a[href]'))
    if (vis(a) && !a.closest('td, th, [role=gridcell], [role=row]') && !listeDeDonnees(a) && !a.closest(MENU) &&
        !a.closest('[class*=onglet i], [class*=tabs i], [role=tablist]'))
      r.liens.push(enregistrement(a) ? '(donnee masquee)' : court(a.textContent || a.getAttribute('title') || ''));
  return r;
}"""


# « Jean DUPONT », « DUPONT Jean », « Mme Durand », « Paul Martin » : un nom de personne n'est jamais de la structure
PRENOMS = set("""jean marie pierre paul jacques michel philippe alain nicolas christophe patrick daniel bernard eric
laurent frederic stephane david olivier sebastien thomas julien francois pascal thierry vincent christian didier
dominique gerard guillaume antoine alexandre maxime romain mathieu julie nathalie isabelle sylvie catherine sophie
christine martine francoise valerie sandrine stephanie anne celine helene veronique monique nicole chantal brigitte
caroline emilie aurelie claire camille laura sarah lea manon chloe emma louise lucas hugo louis gabriel arthur jules
martin marc yves luc andre rene henri georges claude roger""".split())
NOM_DE_PERSONNE = re.compile(r"\b[A-ZÉÈÀÂÎÔÛÇ][a-zéèêëàâîïôûüç]+(?:-[A-Z][a-z]+)?\s+[A-ZÉÈÀÂÎÔÛÇ]{2,}(?![\w])|"
                             r"\b[A-ZÉÈÀÂÎÔÛÇ]{2,}\s+[A-ZÉÈÀÂÎÔÛÇ][a-zéèêëàâîïôûüç]+\b|"
                             r"\b(?:M\.|Mme|Mlle|Mr|Monsieur|Madame|Mademoiselle)\s+[A-ZÉÈ]")
AUTRES_DONNEES = re.compile(r"\d{3,}|@|https?://|\\|\b[A-Za-z]{1,6}-\d+|\d{2}[ .]\d{2}[ .]\d{2}|\d{1,2}/\d{1,2}/\d{2,4}")


def _prenom_nom(texte):
    mots_ = re.findall(r"[A-Za-zÀ-ÿ'-]+", texte)
    return any((sans_accents(a).lower() in PRENOMS and b[:1].isupper() and len(b) > 1) or
               (sans_accents(b).lower() in PRENOMS and a[:1].isupper() and len(a) > 2 and a.lower() not in ("de", "du", "la"))
               for a, b in zip(mots_, mots_[1:]))


def _structure(texte):
    """Un nom d'élément du portail, gardé seulement s'il ressemble à de la structure (pas à une donnée)."""
    t = " ".join(str(texte or "").split())
    if not t or len(t) > 45:
        return None
    if t == "(donnee masquee)":
        return t
    if AUTRES_DONNEES.search(t) or NOM_DE_PERSONNE.search(t) or _prenom_nom(t):
        return "(donnee masquee)"
    return t


def _liste(elements, limite=40):
    vus = []
    for e in elements:
        t = _structure(e)
        if t and t not in vus:
            vus.append(t)
    return vus[:limite]


def relever_page(page):
    """La structure de la page affichée dans la fenêtre du robot (tous les cadres)."""
    barres = []
    try:
        for i, nom in enumerate(page.evaluate(JS_BARRES)):
            entree = page.locator(f'[data-robot-barre="{i}"]')
            sous = []
            try:
                entree.hover(timeout=3000)  # survol seulement : jamais de clic
                time.sleep(0.8)
                sous = page.locator(f'[data-robot-barre="{i}"]').evaluate(JS_SOUS_MENU)
            except Exception:
                pass
            barres.append((nom, sous))
        page.mouse.move(0, 0)
        time.sleep(0.3)
    except Exception:
        pass
    total = {"autresMenus": [], "onglets": [], "champs": [], "boutons": [], "tableaux": [], "libelles": [], "liens": [], "cadres": 0}
    for cadre in page.frames:
        try:
            r = cadre.evaluate(JS_RELEVE)
        except Exception:
            continue
        for cle in total:
            if cle == "cadres":
                total[cle] += r[cle]
            else:
                total[cle] += r[cle]
    _nettoyer(page)
    for cadre in page.frames:
        try:
            cadre.evaluate("() => document.querySelectorAll('[data-robot-barre]').forEach(e => e.removeAttribute('data-robot-barre'))")
        except Exception:
            pass
    menus = []
    for nom, sous in barres:
        t = _structure(nom)
        if t:
            s = _liste(sous, 25)
            menus.append(t + (" > " + " ; ".join(s) if s else ""))
    tableaux = []
    for tab in total["tableaux"]:
        cols = [c for c in (_structure(c) for c in tab["colonnes"]) if c]
        if cols:
            tableaux.append(" | ".join(cols) + f"   ({tab['lignes']} ligne(s))")
    return {
        "menus": menus, "autres menus": _liste(total["autresMenus"]), "onglets": _liste(total["onglets"]),
        "champs": _liste(total["champs"]), "boutons": _liste(total["boutons"]), "tableaux": tableaux,
        "libelles de fiche": _liste(total["libelles"]), "liens": _liste(total["liens"], 25),
        "zones interieures (iframes)": total["cadres"],
    }


def ecrire_releve(pages):
    lignes = [f"RELEVE DU PORTAIL - pour Claude - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
              "Structure seulement (noms des menus, champs, boutons, colonnes). Aucune valeur.",
              "Relisez : une vraie valeur (nom de client, numero de plan...) -> effacez ce mot seulement.", ""]
    menus_vus = None
    for numero, (nom, r) in enumerate(pages, 1):
        lignes.append(f"PAGE {numero} : {nom}")
        if r["menus"] and r["menus"] != menus_vus:
            lignes.append("  Menu du haut : " + "  |  ".join(r["menus"]))
            menus_vus = r["menus"]
        elif r["menus"]:
            lignes.append("  Menu du haut : le meme")
        for cle in ("autres menus", "onglets", "champs", "boutons", "libelles de fiche", "liens"):
            if r[cle]:
                lignes.append(f"  {cle.capitalize()} : " + " ; ".join(r[cle]))
        for t in r["tableaux"]:
            lignes.append("  Tableau : " + t)
        if r["zones interieures (iframes)"]:
            lignes.append(f"  Zones interieures (iframes) : {r['zones interieures (iframes)']}")
        lignes.append("")
    for nom in ("A_ENVOYER_releve.txt", "A_ENVOYER_releve_2.txt", "A_ENVOYER_releve_3.txt"):
        fichier = dossier_robot() / nom
        try:
            fichier.write_text("\n".join(lignes), encoding="utf-8")
            return fichier
        except OSError:
            continue
    raise ErreurTache("impossible d'ecrire le releve dans Bureau > Robot")


def boucle_releve(page):
    """Vous allez sur une page dans la fenêtre du robot, vous la nommez, le robot la relève. Entrée vide = fini."""
    pages = []
    ecrire("   Dans la FENETRE DU ROBOT, allez sur une page du portail (comme d'habitude, a la souris).")
    ecrire("   Puis revenez ici, tapez un nom court pour cette page et Entree.")
    ecrire("   Exemples : recherche plans, liste resultats, fiche plan, onglet references.")
    ecrire("   Entree sans rien = fini.")
    while len(pages) < 30:
        nom = demander(f"   Nom de la page {len(pages) + 1} (Entree sans rien = fini) :")
        if not nom:
            if pages or not oui("   Aucune page relevee pour l'instant. Continuer le releve ?", "o"):
                break
            continue
        try:
            page = page.context.pages[-1] if page.context.pages else page  # l'onglet le plus récent
            page.bring_to_front()
            attendre_chargement(page, 5)
            ecrire("   Releve en cours : ne touchez pas a la fenetre du robot...")
            avant = page.url
            r = relever_page(page)
            if page.url != avant:
                ecrire("   --> la page a change pendant le releve : revenez sur cette page, puis retapez son nom.")
                continue
            pages.append((_structure(nom) or f"page {len(pages) + 1}", r))
            nb = sum(len(v) for k, v in r.items() if isinstance(v, list))
            ecrire(f"   --> page relevee ({nb} elements). Allez sur la page suivante, ou Entree sans rien = fini.")
        except Exception as e:
            ecrire("   --> cette page n'a pas pu etre relevee : " + expliquer(e))
    if not pages:
        return None, 0
    return ecrire_releve(pages), len(pages)


# ---------------------------------------------------------------------------- tâches (écrites par Claude, lancées par vous)
class ErreurTache(Exception):
    pass


class Passer(Exception):
    """On ne touche à rien de plus pour cet élément de la liste : on passe au suivant."""


class AVerifier(Exception):
    """Une action a peut-être été faite, puis le portail a affiché autre chose : à vérifier sur le portail."""


class Arreter(Exception):
    pass


ACTIONS_TACHE = {
    # en-tête
    "TACHE": "nom de la tache", "DEMANDER": "nom = question", "LISTE": "fichier", "CONFIRMER": "oui / non",
    # navigation et gestes
    "ACCUEIL": "", "ALLER": "adresse", "MENU": "Menu > Sous-menu", "CLIQUER": "texte [DANS LIGNE valeur]",
    "ECRIRE": "Libelle = valeur", "CHOISIR": "Libelle = choix", "COCHER": "Libelle", "DECOCHER": "Libelle",
    "TOUCHE": "Entree / Tab / Echap", "ATTENDRE": "texte, ou 3 secondes", "VERIFIER": "texte",
    "LIRE": "Libelle", "ACCEPTER FENETRE": "texte de la fenetre", "CAPTURE": "nom",
    # décisions
    "SI PRESENT": "texte [DANS COLONNE titre]", "SI ABSENT": "texte [DANS COLONNE titre]", "SINON": "", "FIN SI": "",
    "REPETER TANT QUE PRESENT": "texte [DANS COLONNE titre]", "REPETER TANT QUE ABSENT": "texte [DANS COLONNE titre]",
    "FIN REPETER": "",
    "PASSER": "raison", "PREVENIR": "message", "ARRETER": "raison", "PAUSE": "message",
}
TOUCHES = {"ENTREE": "Enter", "ENTER": "Enter", "TAB": "Tab", "TABULATION": "Tab", "ECHAP": "Escape",
           "ECHAPPE": "Escape", "ESC": "Escape", "BAS": "ArrowDown", "HAUT": "ArrowUp", "ESPACE": "Space"}
GESTES = ("ACCUEIL", "ALLER", "MENU", "CLIQUER", "ECRIRE", "CHOISIR", "COCHER", "DECOCHER", "TOUCHE")
MOTIF_DUREE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(s|sec\w*|minutes?|min)?$", re.IGNORECASE)


def _nom_action(brut):
    return " ".join(sans_accents(brut).upper().split())


def lire_texte(chemin):
    """Le texte d'un fichier reçu, quel que soit l'enregistrement (UTF-8, Excel « CSV », Unicode...)."""
    donnees = Path(chemin).read_bytes()
    if donnees[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return donnees.decode("utf-16")
    try:
        return donnees.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        texte = donnees.decode("cp1252")
    except UnicodeDecodeError:
        texte = ""
    if not texte or re.search("[‚„…‡ŠŽƒ]", texte):
        raise ErreurTache(f"« {Path(chemin).name} » illisible : dans Excel, Fichier > Enregistrer sous > « CSV UTF-8 »")
    return texte


def lire_tache(chemin):
    """Lit un fichier de tâche. Renvoie (entête, étapes) ; une erreur dit la ligne et quoi corriger."""
    texte = lire_texte(chemin)
    entete = {"nom": Path(chemin).stem, "demander": [], "liste": None, "confirmer": True}
    racine = []
    pile = [racine]
    ouverts = []
    for numero, ligne in enumerate(texte.splitlines(), 1):
        brut = ligne.strip()
        if not brut or brut.startswith(("#", "//")):
            continue
        m = re.match(r"^([A-Za-zÀ-ÿ' ]+?)\s*(?::\s*(.*))?$", brut)
        action = _nom_action(m.group(1)) if m else ""
        arg = (m.group(2) or "").strip() if m else ""
        if action not in ACTIONS_TACHE:
            raise ErreurTache(f"ligne {numero} : action inconnue « {brut[:40]} »")
        if action == "TACHE":
            entete["nom"] = arg or entete["nom"]
        elif action == "DEMANDER":
            if "=" not in arg:
                raise ErreurTache(f"ligne {numero} : ecrire DEMANDER : nom = question")
            nom, question = (x.strip() for x in arg.split("=", 1))
            entete["demander"].append((nom, question or nom))
        elif action == "LISTE":
            entete["liste"] = arg
        elif action == "CONFIRMER":
            entete["confirmer"] = not sans_accents(arg).lower().startswith("non")
        elif action in ("SI PRESENT", "SI ABSENT", "REPETER TANT QUE PRESENT", "REPETER TANT QUE ABSENT"):
            if not arg:
                raise ErreurTache(f"ligne {numero} : il manque le texte apres « {action} : »")
            genre = "SI" if action.startswith("SI") else "REPETER"
            bloc = {"action": genre, "present": action.endswith("PRESENT"), "arg": arg, "ligne": numero,
                    "alors": [], "sinon": [], "genre": genre}
            pile[-1].append(bloc)
            pile.append(bloc["alors"])
            ouverts.append(bloc)
        elif action in ("SINON", "FIN SI", "FIN REPETER"):
            attendu = "REPETER" if action == "FIN REPETER" else "SI"
            if not ouverts:
                raise ErreurTache(f"ligne {numero} : {action} sans {attendu}")
            if ouverts[-1]["genre"] != attendu:
                fin = "FIN REPETER" if ouverts[-1]["genre"] == "REPETER" else "FIN SI"
                raise ErreurTache(f"ligne {numero} : il manque d'abord {fin} (bloc ouvert ligne {ouverts[-1]['ligne']})")
            if action == "SINON":
                if pile[-1] is not ouverts[-1]["alors"]:
                    raise ErreurTache(f"ligne {numero} : deux SINON pour le meme SI")
                pile[-1] = ouverts[-1]["sinon"]
            else:
                pile.pop()
                ouverts.pop()
        else:
            if action in ("ECRIRE", "CHOISIR") and "=" not in arg:
                raise ErreurTache(f"ligne {numero} : ecrire {action} : Libelle = valeur")
            if action in ("ALLER", "MENU", "CLIQUER", "ECRIRE", "CHOISIR", "COCHER", "DECOCHER", "TOUCHE", "ATTENDRE",
                          "VERIFIER", "LIRE", "ACCEPTER FENETRE") and not arg:
                raise ErreurTache(f"ligne {numero} : il manque ce qu'il faut apres « {action} : »")
            if action == "TOUCHE" and _nom_action(arg) not in TOUCHES:
                raise ErreurTache(f"ligne {numero} : touche inconnue « {arg} » (Entree, Tab, Echap, Bas, Haut, Espace)")
            pile[-1].append({"action": action, "arg": arg, "ligne": numero})
    if ouverts:
        fin = "FIN REPETER" if ouverts[-1]["genre"] == "REPETER" else "FIN SI"
        raise ErreurTache(f"ligne {ouverts[-1]['ligne']} : il manque {fin}")
    if not racine:
        raise ErreurTache("la tache ne contient aucune action")
    return entete, racine


def variables_utilisees(etapes):
    for e in etapes:
        for nom in re.findall(r"\{([^{}]+)\}", e.get("arg", "")):
            yield nom.strip(), e["ligne"]
        yield from variables_utilisees(e.get("alors", []))
        yield from variables_utilisees(e.get("sinon", []))


def _versions(base, nom):
    """Le fichier et ses copies « nom (1).csv » laissées par le navigateur, du plus récent au plus ancien."""
    p = Path(nom)
    trouves = [base / nom] + list(base.glob(f"{p.stem} (*){p.suffix}"))
    trouves = [f for f in trouves if f.is_file()]
    return sorted(trouves, key=lambda f: f.stat().st_mtime, reverse=True)


def _chercher_fichier(nom, pres_de):
    for base in (Path(pres_de).parent, Path.home() / "Downloads", Path.home() / "Téléchargements", dossier_robot(),
                 dossier_robot("taches")):
        try:
            versions = _versions(base, nom)
        except OSError:
            continue
        if versions:
            if len(versions) > 1:
                ecrire(f"   Plusieurs « {nom} » : le robot prend la plus recente, {versions[0].name} "
                       f"(recue le {datetime.fromtimestamp(versions[0].stat().st_mtime):%d/%m a %H:%M}).")
            return versions[0]
    raise ErreurTache(f"liste « {nom} » introuvable (mettez-la dans Telechargements)")


def lire_liste(nom, pres_de):
    """Les lignes de la liste (Excel, CSV ou texte) : une ligne = une fois la tâche."""
    import csv
    f = _chercher_fichier(nom, pres_de)
    suffixe = f.suffix.lower()
    if suffixe in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise ErreurTache("pour une liste Excel, enregistrez-la en CSV (Fichier > Enregistrer sous > CSV UTF-8)")
        feuille = load_workbook(f, read_only=True, data_only=True).worksheets[0]
        lignes = [["" if v is None else str(v).strip() for v in row] for row in feuille.iter_rows(values_only=True)]
    elif suffixe == ".csv":
        brut = lire_texte(f)
        entete = next((l for l in brut.splitlines() if l.strip()), "")
        separateur = "," if ("," in entete and ";" not in entete) else ";"
        lignes = [[c.strip() for c in r] for r in csv.reader(brut.splitlines(), delimiter=separateur)]
    elif suffixe == ".txt":
        lignes = [["valeur"]] + [[l.strip()] for l in lire_texte(f).splitlines() if l.strip()]
    else:
        raise ErreurTache(f"liste « {nom} » : format inconnu (CSV UTF-8, .xlsx ou .txt)")
    lignes = [l for l in lignes if any(l)]
    if len(lignes) < 2:
        raise ErreurTache(f"la liste « {nom} » est vide")
    entetes = [h or f"colonne{i + 1}" for i, h in enumerate(lignes[0])]
    return [dict(zip(entetes, l + [""] * (len(entetes) - len(l)))) for l in lignes[1:]]


JS_LIGNE = r"""([valeur, jeton]) => {
  document.querySelectorAll('[data-robot-ligne]').forEach(x => x.removeAttribute('data-robot-ligne'));
  const norme = t => (t || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const v = norme(valeur); let n = 0;
  for (const e of document.querySelectorAll('td, th, [role=gridcell], li, a, span, div, b')) {
    let propre = ''; for (const c of e.childNodes) if (c.nodeType === 3) propre += c.textContent;
    if (norme(propre) !== v && norme(e.textContent) !== v) continue;
    const ligne = e.closest('tr, [role=row], li');
    // une « ligne » qui contient d'autres lignes est de la mise en page : ce n'est pas la ligne de ce plan
    if (!ligne || ligne.querySelector('tr, [role=row], li, table')) continue;
    if (!ligne.hasAttribute('data-robot-ligne')) { ligne.setAttribute('data-robot-ligne', jeton); n++; }
  }
  return n;
}"""

JS_CHAMP_PAR_LIBELLE = r"""([libelle, jeton]) => {
  const norme = t => (t || '').replace(/\s+/g, ' ').replace(/[\s:*]+$/, '').trim().toLowerCase();
  const v = norme(libelle); let n = 0;
  const champs = Array.from(document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea'));
  for (const e of document.querySelectorAll('label, td, th, span, div, b, strong, p, dt')) {
    let propre = ''; for (const c of e.childNodes) if (c.nodeType === 3) propre += c.textContent;
    if (norme(propre) !== v) continue;
    const bloc = e.closest('tr, li, p, dl, fieldset, .form-group, div') || e.parentElement;
    const suivant = champs.find(c => (e.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING) && bloc.contains(c));
    if (suivant) { suivant.setAttribute('data-robot-champ', jeton); n++; }
  }
  return n;
}"""

# La valeur affichée en face d'un libellé (fiche « Statut : Validé », champ, ou cellule sous un titre de colonne).
JS_LIRE = r"""([libelle]) => {
  const norme = t => (t || '').replace(/\s+/g, ' ').replace(/[\s:*]+$/, '').trim().toLowerCase();
  const court = t => (t || '').replace(/\s+/g, ' ').trim();
  const valeurDe = c => c.tagName === 'SELECT' ? court((c.options[c.selectedIndex] || {}).text) : court(c.value);
  const v = norme(libelle);
  for (const e of document.querySelectorAll('label, th, [role=columnheader], td, span, div, b, strong, p, dt')) {
    let propre = ''; for (const c of e.childNodes) if (c.nodeType === 3) propre += c.textContent;
    const p = court(propre);
    if (norme(p) !== v && !norme(p).startsWith(v + ' :') && !norme(p).startsWith(v + ':')) continue;
    if (norme(p) !== v) return { valeur: court(p.split(':').slice(1).join(':')) };
    if (e.tagName === 'TH' || e.getAttribute('role') === 'columnheader') {      // titre de colonne
      const titres = e.parentElement, table = e.closest('table, [role=grid]');
      const rang = Array.from(titres.children).indexOf(e);
      const lignes = Array.from(table.querySelectorAll('tr, [role=row]'))
        .filter(l => l !== titres && Array.from(l.children).some(c => c.tagName === 'TD' || c.getAttribute('role') === 'gridcell'));
      if (lignes.length !== 1) return { erreur: lignes.length ? 'plusieurs lignes dans le tableau' : 'tableau vide' };
      const c = lignes[0].children[rang];
      return c ? { valeur: court(c.textContent) } : { erreur: 'colonne vide' };
    }
    if (e.tagName === 'LABEL' && e.control) return { valeur: valeurDe(e.control) };
    const champ = e.parentElement && e.parentElement.querySelector('input, select, textarea');
    if (champ && (e.compareDocumentPosition(champ) & Node.DOCUMENT_POSITION_FOLLOWING)) return { valeur: valeurDe(champ) };
    const suivant = e.nextElementSibling;
    if (suivant && suivant.tagName !== 'TH') return { valeur: court(suivant.textContent) };
    const cell = e.closest('td, dt');
    if (cell && cell.nextElementSibling) return { valeur: court(cell.nextElementSibling.textContent) };
  }
  return null;
}"""

# Une ligne du tableau a-t-elle ce texte dans cette colonne ? (cellule égale, ou qui commence par ce texte :
# « Validé » trouve « Validé le 12/03 », pas « Non validé »). Tableaux visibles seulement.
JS_COLONNE = r"""([colonne, texte]) => {
  const norme = t => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const egal = (cellule, t) => { const c = norme(cellule), x = norme(t);
    return c === x || (c.startsWith(x) && /^[^a-z0-9]/.test(c.slice(x.length))); };
  let trouve = false;
  for (const t of document.querySelectorAll('table, [role=grid]')) {
    if (!vis(t)) continue;
    let entetes = Array.from(t.querySelectorAll('thead th, [role=columnheader]'));
    if (!entetes.length) { const l = t.querySelector('tr'); if (l && Array.from(l.children).every(c => c.tagName === 'TH')) entetes = Array.from(l.children); }
    let rang = entetes.findIndex(h => norme(h.textContent) === norme(colonne));
    if (rang < 0) { const proches = entetes.map((h, i) => [norme(h.textContent), i]).filter(([h]) => h.includes(norme(colonne)));
                    if (proches.length === 1) rang = proches[0][1]; }
    if (rang < 0) continue;
    trouve = true;
    for (const l of t.querySelectorAll('tr, [role=row]')) {
      const cellules = Array.from(l.children).filter(c => c.tagName === 'TD' || c.getAttribute('role') === 'gridcell');
      if (!cellules.length) continue;
      if (cellules.length === 1 && /aucun|aucune|vide|pas de|no data|empty/i.test(l.textContent || '')) continue;
      if (cellules.length < entetes.length) return 'illisible';
      // colonne sans titre (cases, actions) : on regarde les deux alignements possibles
      const decalage = cellules.length - entetes.length;
      if (egal(cellules[rang].textContent, texte) || (decalage && egal(cellules[rang + decalage].textContent, texte))) return 'oui';
    }
  }
  return trouve ? 'non' : 'colonne absente';
}"""

JS_BANDEAU = r"""(message) => {
  const b = document.createElement('div');
  b.textContent = 'ROBOT : ' + message;
  b.setAttribute('data-robot-bandeau', '1');
  b.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#f59e0b;' +
    'color:#111;font:600 15px Arial,sans-serif;padding:12px 18px;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,.4);max-width:80%';
  document.documentElement.appendChild(b);
  setTimeout(() => b.remove(), 5000);
}"""

# Ce que la touche Entrée (ou Espace) déclencherait : l'élément actif, son formulaire et ses boutons d'envoi.
JS_FOCUS = r"""() => {
  const e = document.activeElement;
  if (!e || e === document.body || e.tagName === 'IFRAME' || e.tagName === 'FRAME') return null;
  e.setAttribute('data-robot-focus', '1');   // pour remettre le curseur ici après une question
  const f = e.form || e.closest('form');
  const boutons = f ? Array.from(f.querySelectorAll('button, input[type=submit], input[type=image]'))
    .map(b => [b.innerText, b.value, b.title, b.getAttribute('aria-label')].join(' ')) : [];
  let touchesParents = '';
  for (let n = e.parentElement; n; n = n.parentElement)
    for (const a of ['onkeydown', 'onkeypress', 'onkeyup']) if (n.getAttribute && n.getAttribute(a)) touchesParents += ' ' + n.getAttribute(a);
  const libelle = (e.labels && e.labels[0] ? e.labels[0].innerText : '') + ' ' + (e.name || '') + ' ' + (e.id || '');
  return { texte: [e.innerText, e.value, e.title, e.getAttribute('aria-label'), e.getAttribute('onclick'),
                   e.getAttribute('onkeydown'), e.getAttribute('onkeypress'), libelle, touchesParents].join(' '),
           formulaire: f ? [f.getAttribute('action') || '', f.getAttribute('onsubmit') || '', boutons.join(' ')].join(' ') : '',
           avecFormulaire: !!f, post: !!f && (f.getAttribute('method') || '').toLowerCase() === 'post',
           genre: e.tagName === 'INPUT' ? (e.type || 'text').toLowerCase() : e.tagName.toLowerCase(),
           lien: e.tagName === 'A' || e.tagName === 'BUTTON' || e.getAttribute('role') === 'button',
           auto: !!(e.getAttribute('onchange') || e.getAttribute('onclick') || touchesParents ||
                    (f && (f.getAttribute('onchange') || f.getAttribute('onclick')))) };
}"""


def _correspond(attendu, message):
    """La fenêtre du portail est-elle celle annoncée ? Mots entiers : « PL-1 » ne vaut pas pour « PL-10 »."""
    a, m = mots(attendu), mots(message)
    return bool(a) and re.search(r"(^| )" + re.escape(a) + r"( |$)", m) is not None


class Tache:
    """Exécute une tâche, élément par élément de la liste, en notant chaque résultat dans un fichier."""

    def __init__(self, entete, etapes, page, url):
        self.entete, self.etapes = entete, etapes
        self.page = page
        self.url = url
        self.variables = {}
        self.tout_confirme = not entete["confirmer"]
        self.oui_lignes = set()  # « t » : oui pour cette ligne de la tâche, pour tous les éléments
        self.element = ""
        self.ligne_courante = 0
        self.lectures = {}
        self.attendues = []
        self.en_vol = 0
        self.nouvel_element()
        self.suivre_page(page)
        page.context.on("page", self.suivre_page)
        page.context.on("request", lambda r: self._reseau(r, 1))
        page.context.on("requestfinished", lambda r: self._reseau(r, -1))
        page.context.on("requestfailed", lambda r: self._reseau(r, -1))

    def _reseau(self, requete, sens):
        try:
            if requete.resource_type in ("document", "xhr", "fetch"):
                self.en_vol = max(0, self.en_vol + sens)
        except Exception:
            pass

    def calme(self, maximum=15):
        """Attendre que le portail ait répondu (plus aucune requête en cours pendant une demi-seconde) : sinon on
        regarderait la page d'avant la réponse (ligne pas encore retirée, message pas encore affiché)."""
        fin, tranquille = time.time() + maximum, None
        while time.time() < fin:
            if self.en_vol <= 0:
                tranquille = tranquille or time.time()
                if time.time() - tranquille >= 0.5:
                    break
            else:
                tranquille = None
            try:
                self.page.wait_for_timeout(100)
            except Exception:
                break

    def page_ouverte(self):
        """Une fenêtre (popup d'édition) qui s'est fermée toute seule : on revient sur la dernière fenêtre ouverte."""
        if self.page.is_closed():
            ouvertes = [p for p in self.page.context.pages if not p.is_closed()]
            if not ouvertes:
                raise ErreurTache("la fenetre du robot a ete fermee")
            self.page = ouvertes[-1]
            self.page.bring_to_front()

    def nouvel_element(self):
        self.lectures = {}
        self.attendues = []
        self.acceptee = None  # une action acceptée vaut pour tout l'élément : tout message ensuite = A VERIFIER
        self.apres = []
        self.nouveau_geste()

    def nouveau_geste(self):
        self.refusees = []
        self.accord_geste = False

    # --- fenêtres du portail (« Voulez-vous vraiment supprimer ? ») : seule celle annoncée est acceptée
    def suivre_page(self, page):
        page.on("dialog", self.sur_fenetre)

    def sur_fenetre(self, fenetre):
        message = " ".join((fenetre.message or "").split())
        if fenetre.type == "beforeunload" or not message:
            message = "Quitter cette page ? (des modifications pourraient ne pas etre enregistrees)"
        attendue = next((a for a in self.attendues if _correspond(a, message)), None)
        try:
            if attendue and not self.refusees and (self.accord_geste or not interdit(message)):
                self.attendues.remove(attendue)
                self.acceptee = self.acceptee or message
                ecrire(f"      fenetre du portail acceptee : « {message[:80]} »")
                fenetre.accept()
            elif fenetre.type == "alert" and self.acceptee:
                # après une action acceptée, une alerte n'a qu'un bouton OK : on la ferme, et on le signale
                self.apres.append(message)
                ecrire(f"      message du portail apres l'action : « {message[:80]} »")
                fenetre.accept()
            else:
                self.refusees.append(message)
                ecrire(f"      fenetre du portail REFUSEE (pas prevue) : « {message[:80]} »")
                fenetre.dismiss()
        except Exception:
            pass

    def verifier_fenetres(self):
        if self.acceptee and (self.apres or self.refusees):
            autre = (self.apres + self.refusees)[0]
            raise AVerifier(f"« {self.acceptee[:50]} » accepte, puis le portail a affiche « {autre[:80]} » : "
                            "verifiez cet element sur le portail")
        if self.refusees:
            raise Passer(f"le portail a affiche « {self.refusees[0][:100]} » : rien n'a ete valide, on passe au suivant")

    # --- outils
    def remplir(self, texte):
        def valeur(m):
            nom = m.group(1).strip()
            for cle, v in self.variables.items():
                if mots(cle) == mots(nom):
                    v = str(v).strip()
                    if not v:
                        raise Passer(f"{{{nom}}} est vide pour cet element : rien n'est fait")
                    return v
            raise ErreurTache(f"valeur inconnue {{{nom}}}")
        return re.sub(r"\{([^{}]+)\}", valeur, texte)

    def cadres(self):
        return list(self.page.frames)

    def retirer_bandeaux(self):
        for cadre in self.cadres():
            try:
                cadre.evaluate("() => document.querySelectorAll('[data-robot-bandeau]').forEach(b => b.remove())")
            except Exception:
                pass

    def candidats(self, texte, racines, attente=5):
        """Les éléments qui portent EXACTEMENT ce texte (nom de bouton, lien, texte, bulle), les visibles d'abord.
        On réessaie quelques secondes : la page peut être encore en train de s'afficher."""
        if not texte.strip():
            raise ErreurTache("texte vide")
        exact_sans_casse = re.compile(r"^\s*" + re.escape(texte) + r"\s*$", re.IGNORECASE)
        jeton = secrets.token_hex(6)

        def propre_texte(r):
            if hasattr(r, "child_frames"):  # un cadre de la page entière
                r.evaluate(JS_TROUVER_PROPRE_TEXTE, [texte, jeton])
            else:
                r.evaluate("(e, [m, j]) => { const norme = t => (t || '').replace(/\\s+/g, ' ').trim().toLowerCase();"
                           " for (const x of [e, ...e.querySelectorAll('*')]) { let p = '';"
                           " for (const n of x.childNodes) if (n.nodeType === 3) p += n.textContent;"
                           " if (norme(p) === norme(m)) x.setAttribute('data-robot-trouve', j); } }", [texte, jeton])
            return r.locator(f'[data-robot-trouve="{jeton}"]')

        facons = [lambda r, role=role: r.get_by_role(role, name=texte, exact=True)
                  for role in ("button", "link", "menuitem", "tab", "treeitem")]
        facons += [lambda r: r.get_by_text(texte, exact=True), propre_texte,
                   lambda r: r.get_by_title(texte, exact=True),
                   lambda r: r.locator(f"[aria-label={json.dumps(texte, ensure_ascii=False)}]"),
                   lambda r: r.get_by_text(exact_sans_casse)]
        fin = time.time() + attente
        while True:
            for facon in facons:
                trouves = []
                for r in racines:
                    try:
                        loc = facon(r)
                        for i in range(min(loc.count(), 10)):
                            trouves.append(loc.nth(i))
                    except Exception:
                        continue
                if trouves:
                    visibles = [t for t in trouves if _visible(t)]
                    return visibles + [t for t in trouves if t not in visibles]
            if time.time() >= fin:
                return []
            self.page.wait_for_timeout(500)

    def racines_ligne(self, valeur):
        jeton = secrets.token_hex(6)
        racines = []
        for cadre in self.cadres():
            try:
                if cadre.evaluate(JS_LIGNE, [valeur, jeton]):
                    racines.append(cadre.locator(f'[data-robot-ligne="{jeton}"]'))
            except Exception:
                continue
        lignes = sum(r.count() for r in racines)
        if lignes == 0:
            raise ErreurTache(f"aucune ligne « {valeur} » sur la page")
        if lignes > 1:
            raise ErreurTache(f"{lignes} lignes « {valeur} » sur la page : le robot ne choisit pas au hasard")
        return racines

    def _sans_focus(self):
        """Personne ne doit pouvoir taper dans la page pendant une question : on retire le curseur des champs."""
        for cadre in self.cadres():
            try:
                cadre.evaluate("() => { const a = document.activeElement; if (a && a !== document.body && a.blur) a.blur(); }")
            except Exception:
                pass

    def confirmer(self, loc, quoi, cle=None):
        """Avant un geste qui modifie : votre accord (o), ou « t » donné avant pour CETTE action précise
        (même ligne de la tâche ET même texte : « t » pour Archiver ne vaut jamais pour Supprimer)."""
        cle = (self.ligne_courante, mots(cle or quoi))
        if self.tout_confirme or cle in self.oui_lignes:
            self.accord_geste = True
            return
        attendues, self.attendues = self.attendues, []  # rien n'est accepté pendant la question
        self._sans_focus()
        if loc is not None:
            _encadrer(loc, 0)
        revenez_ici()
        reponse = demander(f"   [{self.element}] Le robot va {quoi}. Tapez o (oui), n (non : on passe au suivant), "
                           "t (oui pour cette action, pour toute la liste) :", "n").lower()
        _nettoyer(self.page, tout=False)
        if reponse.startswith("t"):
            self.oui_lignes.add(cle)
        elif not reponse.startswith(("o", "y")):
            raise Passer("refuse par vous")
        self.attendues = attendues
        self.accord_geste = True

    def _texte_de(self, loc):
        """Le texte de l'élément, ses bulles et actions, et celles de ses PARENTS : le clic remonte jusqu'à eux."""
        try:
            return loc.evaluate(r"""e => {
              const parts = [e.innerText, e.value, e.title, e.getAttribute('aria-label'), e.getAttribute('href'), e.getAttribute('onclick')];
              const GEST = /^(on(click|dblclick|mousedown|mouseup|pointerdown|pointerup|touchstart|touchend))$|click|^hx-|^wire:|^x-on|^@|^data-(ajax|turbo|confirm|method|action|url)|^title$|^aria-label$/i;
              for (let n = e.parentElement; n && n !== document.body; n = n.parentElement)
                for (const a of Array.from(n.attributes)) if (GEST.test(a.name)) parts.push(a.value);
              const f = e.form || e.closest('form'); if (f) parts.push(f.getAttribute('action') || '');
              return parts.join(' '); }""")
        except Exception:
            return ""

    def cliquer(self, arg):
        nieme = 1
        m = re.match(r"^(.*?)\s*\[(\d+)\]\s*$", arg)
        if m:
            arg, nieme = m.group(1), int(m.group(2))
        racines = self.cadres()
        quoi = arg
        m = re.match(r"^(.*?)\s+DANS\s+LIGNE\s+(.+)$", arg, re.IGNORECASE)
        if m:
            arg, ligne = m.group(1).strip(), m.group(2).strip()
            racines = self.racines_ligne(ligne)
            quoi = f"{arg} (ligne {ligne})"
        trouves = self.candidats(arg, racines)
        if len(trouves) < nieme:
            raise ErreurTache(f"« {arg} » introuvable sur la page")
        loc = trouves[nieme - 1]
        if not _visible(loc):
            _ouvrir_menus(loc)
        if (interdit(arg) or interdit(self._texte_de(loc)) or any(interdit(a) for a in self.attendues)) \
                and not self.accord_geste:
            self.confirmer(loc, f"cliquer « {quoi} »", cle="cliquer " + arg)
        avant = len(self.page.context.pages)
        loc.click(timeout=15000)
        attendre_chargement(self.page)
        self.calme()
        self.page_ouverte()
        if len(self.page.context.pages) > avant:
            self.page = self.page.context.pages[-1]
            self.page.bring_to_front()
            attendre_chargement(self.page)

    def menu(self, arg):
        parties = [p.strip() for p in arg.split(">") if p.strip()]
        for i, partie in enumerate(parties):
            dernier = i == len(parties) - 1
            trouves = self.candidats(partie, self.cadres())
            if not trouves:
                raise ErreurTache(f"menu « {partie} » introuvable")
            loc = trouves[0]
            if i == 0 and any(interdit(p) for p in parties) and not self.accord_geste:
                self.confirmer(loc, "ouvrir le menu « " + " > ".join(parties) + " »", cle="menu " + " > ".join(parties))
            if not _visible(loc):
                _ouvrir_menus(loc)
            if dernier:
                self.cliquer(partie)
                return
            loc.hover(timeout=10000)
            self.page.wait_for_timeout(800)
            suivant = self.candidats(parties[i + 1], self.cadres(), attente=1)
            if not (suivant and _visible(suivant[0])):
                # menu qui s'ouvre au clic : ce clic aussi est contrôlé
                if interdit(self._texte_de(loc)) and not self.accord_geste:
                    self.confirmer(loc, f"cliquer « {partie} »", cle="cliquer " + partie)
                loc.click(timeout=10000)
                self.page.wait_for_timeout(800)

    def champ(self, libelle):
        if libelle.startswith("#"):
            return self.page.locator(libelle)
        jeton = secrets.token_hex(6)
        facons = [lambda r: r.get_by_label(libelle, exact=True),
                  lambda r: r.get_by_label(re.compile(r"^\s*" + re.escape(libelle) + r"\s*[:*]?\s*$", re.IGNORECASE)),
                  lambda r: r.get_by_placeholder(libelle, exact=True)]
        fin = time.time() + 5
        while True:
            for facon in facons + [None]:
                trouves = []
                for cadre in self.cadres():
                    try:
                        if facon is None:
                            cadre.evaluate(JS_CHAMP_PAR_LIBELLE, [libelle, jeton])
                            loc = cadre.locator(f'[data-robot-champ="{jeton}"]')
                        else:
                            loc = facon(cadre)
                        for i in range(min(loc.count(), 5)):
                            trouves.append(loc.nth(i))
                    except Exception:
                        continue
                visibles = [t for t in trouves if _visible(t)]
                if visibles:
                    return visibles[0]
            if time.time() >= fin:
                raise ErreurTache(f"champ « {libelle} » introuvable sur la page")
            self.page.wait_for_timeout(500)

    def _envoi_automatique(self, loc, texte=False):
        """Le champ enregistre-t-il tout seul (au changement, ou quand on le quitte pour un texte) ?"""
        attributs = "['onchange', 'onblur']" if texte else "['onclick', 'onchange']"
        try:
            return bool(loc.evaluate("e => " + attributs + ".some(a => e.getAttribute(a)) || "
                                     "!!(e.form && (e.form.getAttribute('onchange') || e.form.getAttribute('onclick')))"))
        except Exception:
            return False

    def presence(self, arg, attente=3):
        """Le texte est-il sur la page (mots entiers) ? Avec « DANS COLONNE x » : dans une ligne du tableau, sous ce titre."""
        if not arg.strip():
            raise ErreurTache("texte vide")
        self.retirer_bandeaux()  # le message du robot n'est pas du texte du portail
        m = re.match(r"^(.*?)\s+DANS\s+COLONNE\s+(.+)$", arg, re.IGNORECASE)
        motif = re.compile(r"(?<![\w-])" + re.escape(arg.strip()) + r"(?![\w-])", re.IGNORECASE)
        fin = time.time() + attente
        while True:
            if m:
                reponses = []
                for cadre in self.cadres():
                    try:
                        reponses.append(cadre.evaluate(JS_COLONNE, [m.group(2).strip(), m.group(1).strip()]))
                    except Exception:
                        continue
                if "oui" in reponses:
                    return True
                if "illisible" in reponses:
                    raise ErreurTache(f"tableau illisible sous la colonne « {m.group(2).strip()} »")
                if "non" in reponses and time.time() >= fin:
                    return False
                if time.time() >= fin:
                    # jamais « rien trouvé, on continue » quand le tableau a changé : c'est une erreur
                    raise ErreurTache(f"colonne « {m.group(2).strip()} » absente de la page")
            else:
                for cadre in self.cadres():
                    try:
                        loc = cadre.get_by_text(motif)
                        if any(_visible(loc.nth(i)) for i in range(min(loc.count(), 10))):
                            return True
                    except Exception:
                        continue
                if time.time() >= fin:
                    return False
            self.page.wait_for_timeout(500)

    def lire(self, arg):
        for cadre in self.cadres():
            try:
                r = cadre.evaluate(JS_LIRE, [arg])
            except Exception:
                continue
            if r is None:
                continue
            if r.get("erreur"):
                raise ErreurTache(f"« {arg} » : {r['erreur']}")
            return r.get("valeur", "")
        raise ErreurTache(f"« {arg} » introuvable sur la page")

    def touche(self, arg):
        nom = TOUCHES[_nom_action(arg)]
        info = None
        for cadre in self.cadres():
            try:
                info = cadre.evaluate(JS_FOCUS)
            except Exception:
                continue
            if info:
                break
        demander_accord = False
        if info:
            dangereux = interdit(info["texte"]) or interdit(info["formulaire"])
            if nom == "Enter":
                # Entrée envoie : seul un formulaire de recherche ordinaire (sans POST, sans action) passe sans question
                demander_accord = dangereux or info["post"] or info["auto"] or (not info["avecFormulaire"] and not info["lien"])
            elif nom == "Space":
                demander_accord = (info["lien"] or info["genre"] in ("checkbox", "radio")) and (dangereux or info["auto"])
            elif nom in ("ArrowDown", "ArrowUp"):
                demander_accord = info["genre"] in ("select", "radio") and (dangereux or info["auto"])
        if demander_accord and not self.accord_geste:
            self.confirmer(None, f"appuyer sur {arg} (cela peut enregistrer quelque chose)", cle="touche " + arg)
            for cadre in self.cadres():  # la question a retiré le curseur du champ : on l'y remet
                try:
                    cadre.evaluate("() => { const e = document.querySelector('[data-robot-focus]');"
                                   " if (e) { e.removeAttribute('data-robot-focus'); e.focus(); } }")
                except Exception:
                    pass
        try:
            with self.page.expect_navigation(timeout=5000):
                self.page.keyboard.press(nom)
        except Exception:
            pass  # pas de changement de page : rien à attendre
        attendre_chargement(self.page)
        self.calme()

    def aller(self, arg):
        cible = urljoin(self.url or "", arg)
        if (urlsplit(cible).hostname or "") != (urlsplit(self.url or "").hostname or ""):
            raise ErreurTache("adresse hors du portail : refusee")
        morceaux = urlsplit(cible)
        action = adresse_prudente(cible)[1] or interdit(unquote(" ".join((morceaux.path, morceaux.query, morceaux.fragment))))
        if action and not self.accord_geste:
            self.confirmer(None, "ouvrir une adresse qui ressemble a une action : " + (morceaux.path or "/"),
                           cle="aller " + re.sub(r"\d+", "#", morceaux.path))
        self.page.goto(cible, wait_until="domcontentloaded", timeout=60000)
        connexion = attendre_portail(self.page)
        # après une connexion, le portail a pu ramener à l'accueil : on rouvre l'adresse, mais JAMAIS une adresse
        # d'action (elle referait l'action)
        if connexion and not action and urlsplit(self.page.url).path != morceaux.path:
            self.page.goto(cible, wait_until="domcontentloaded", timeout=60000)
            attendre_chargement(self.page)
        self.calme()

    # --- les actions
    def executer(self, etapes):
        for etape in etapes:
            self.page_ouverte()
            self.verifier_fenetres()  # une fenêtre arrivée en retard, après le geste précédent
            self.nouveau_geste()
            self.ligne_courante = etape["ligne"]
            action = etape["action"]
            try:
                arg = self.remplir(etape["arg"])
            except ErreurTache as e:
                raise ErreurTache(f"ligne {etape['ligne']} : {e}")
            if action in ("SI", "REPETER"):
                self.bloc(etape, arg)
                continue
            ecrire(f"   ligne {etape['ligne']:>3} : {action.lower()}" + (f" : {arg}" if arg else ""))
            try:
                self.faire(action, arg)
                self.verifier_fenetres()
            except (Passer, Arreter, AVerifier):
                raise
            except ErreurTache as e:
                raise ErreurTache(f"ligne {etape['ligne']} ({action.lower()}) : {e}")
            except Exception as e:
                raise ErreurTache(f"ligne {etape['ligne']} ({action.lower()}) : {expliquer(e)}")
            if action in GESTES:
                self.attendues = []  # une fenêtre annoncée ne vaut que pour le geste qui la suit

    def bloc(self, etape, arg):
        mot = "si" if etape["action"] == "SI" else "repeter tant que"
        for tour in range(31 if etape["action"] == "REPETER" else 1):
            self.calme()  # la réponse au geste précédent d'abord : jamais de décision sur la page d'avant
            self.verifier_fenetres()
            try:
                vrai = self.presence(arg) == etape["present"]
            except ErreurTache as e:
                raise ErreurTache(f"ligne {etape['ligne']} ({mot}) : {e}")
            ecrire(f"   ligne {etape['ligne']:>3} : {mot} {'present' if etape['present'] else 'absent'} : {arg}"
                   f" -> {'oui' if vrai else 'non'}")
            if etape["action"] == "SI":
                self.executer(etape["alors"] if vrai else etape["sinon"])
                return
            if not vrai:
                return
            if tour == 30:
                raise ErreurTache(f"ligne {etape['ligne']} : repete 30 fois sans fin, le robot s'arrete")
            self.executer(etape["alors"])

    def faire(self, action, arg):
        page = self.page
        if action == "ACCUEIL":
            if not self.url:
                raise ErreurTache("adresse du portail inconnue")
            page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
            attendre_portail(page)
        elif action == "ALLER":
            self.aller(arg)
        elif action == "MENU":
            self.menu(arg)
        elif action == "CLIQUER":
            self.cliquer(arg)
        elif action in ("ECRIRE", "CHOISIR"):
            libelle, valeur = (x.strip() for x in arg.split("=", 1))
            loc = self.champ(libelle)
            balise = loc.evaluate("e => e.tagName.toLowerCase()")
            if balise == "select":
                options = loc.evaluate("e => Array.from(e.options).map(o => [o.text.trim(), o.value])")
                rang = next((i for i, (t, v) in enumerate(options) if mots(t) == mots(valeur) or v == valeur), None)
                if rang is None:
                    raise ErreurTache(f"choix « {valeur} » absent de la liste « {libelle} »")
                if (interdit(libelle) or interdit(valeur) or self._envoi_automatique(loc)) and not self.accord_geste:
                    self.confirmer(loc, f"choisir « {valeur} » dans « {libelle} »", cle=f"choisir {libelle} {valeur}")
                loc.select_option(index=rang, timeout=10000)
                attendre_chargement(page)
                self.calme()
            elif action == "CHOISIR":
                raise ErreurTache(f"« {libelle} » n'est pas une liste de choix (utilisez ECRIRE)")
            else:
                if (interdit(libelle) or self._envoi_automatique(loc, texte=True)) and not self.accord_geste:
                    self.confirmer(loc, f"ecrire dans « {libelle} » (le portail peut l'enregistrer tout seul)",
                                   cle=f"ecrire {libelle}")
                loc.fill(valeur, timeout=10000)
        elif action in ("COCHER", "DECOCHER"):
            loc = self.champ(arg)
            if (interdit(arg) or self._envoi_automatique(loc)) and not self.accord_geste:
                self.confirmer(loc, f"{action.lower()} « {arg} »", cle=f"{action} {arg}")
            loc.set_checked(action == "COCHER", timeout=10000)
            attendre_chargement(page)
            self.calme()
        elif action == "TOUCHE":
            self.touche(arg)
        elif action == "ATTENDRE":
            m = MOTIF_DUREE.match(arg)
            if m:
                duree = float(m.group(1).replace(",", "."))
                if (m.group(2) or "").lower().startswith("min"):
                    duree *= 60
                page.wait_for_timeout(int(min(duree, 600) * 1000))
            elif not self.presence(arg, attente=30):
                raise ErreurTache(f"« {arg} » n'est pas apparu en 30 secondes")
        elif action == "VERIFIER":
            if not self.presence(arg, attente=10):
                raise ErreurTache(f"« {arg} » absent de la page")
        elif action == "LIRE":
            valeur = self.lire(arg)
            self.lectures[arg] = valeur
            ecrire(f"      {arg} : lu (dans le fichier de resultats)")
        elif action == "ACCEPTER FENETRE":
            self.attendues.append(arg)
        elif action == "CAPTURE":
            nom = re.sub(r"[^\w.-]+", "_", arg)[:40] or "capture"
            page.screenshot(path=str(dossier_robot("resultats") / f"{nom}_{datetime.now():%H%M%S}.png"))
        elif action == "PREVENIR":
            ecrire()
            ecrire("   " + "!" * 66)
            ecrire(f"   !!  {arg}")
            ecrire("   " + "!" * 66)
            try:
                page.evaluate(JS_BANDEAU, arg)
            except Exception:
                pass
            self.lectures.setdefault("prevenu", arg)
        elif action == "PASSER":
            raise Passer(arg or "passe")
        elif action == "ARRETER":
            raise Arreter(arg or "arret demande par la tache")
        elif action == "PAUSE":
            self._sans_focus()
            revenez_ici()
            pause((arg or "Pause") + " - puis Entree pour continuer...")


def _cellule_sure(valeur):
    texte = str(valeur)
    formule = texte[:1] in ("=", "@", "\t", "\r") or (texte[:1] in ("+", "-") and len(texte) > 1)
    return "'" + texte if formule else texte


def choisir_tache():
    """Les fichiers tache*.txt reçus, à côté de ce programme, dans Téléchargements ou Bureau > Robot (plus récents d'abord)."""
    ici = Path(__file__).resolve().parent
    vus = {}
    bases = [ici, Path.home() / "Downloads", Path.home() / "Téléchargements"]
    try:
        bases += [dossier_robot(), dossier_robot("taches")]
    except OSError:
        pass
    for base in bases:
        try:
            for f in base.glob("*.txt"):
                if f.name.lower().startswith("tache"):
                    vus.setdefault(f.resolve(), f)
        except OSError:
            continue
    fichiers = sorted(vus.values(), key=lambda f: f.stat().st_mtime, reverse=True)
    if not fichiers:
        ecrire("   Aucune tache trouvee. Enregistrez le fichier tache_....txt recu dans Telechargements.")
        return None
    ecrire()
    for i, f in enumerate(fichiers, 1):
        ecrire(f"   {i}. {f.name}   (recue le {datetime.fromtimestamp(f.stat().st_mtime):%d/%m a %H:%M})")
    choix = demander("   Numero de la tache a lancer :")
    if not choix.isdigit() or not 1 <= int(choix) <= len(fichiers):
        ecrire("   Pas de tache choisie.")
        return None
    return fichiers[int(choix) - 1]


def executer_tache(p, chemin, url):
    """Lance une tâche sur chaque ligne de sa liste (ou une fois), et écrit le fichier de résultats."""
    import csv
    entete, etapes = lire_tache(chemin)  # une faute de rédaction est dite tout de suite, avant d'ouvrir quoi que ce soit
    if not entete["confirmer"]:
        ecrire("   ATTENTION : cette tache demande de cliquer Supprimer, Valider... SANS vous redemander a chaque fois.")
        if demander("   Tapez OUI (en entier) pour l'accepter, ou Entree pour que le robot vous demande a chaque fois :") != "OUI":
            entete["confirmer"] = True
    variables_fixes = {}
    for nom, question in entete["demander"]:
        valeur = ""
        while not valeur:
            valeur = demander(f"   {question} :")
            if not valeur:
                ecrire("   Reponse obligatoire (Ctrl+C pour arreter).")
        variables_fixes[nom] = valeur
    lignes = lire_liste(entete["liste"], chemin) if entete["liste"] else [{}]
    connus = [mots(n) for n in list(variables_fixes) + (list(lignes[0]) if lignes and lignes[0] else [])]
    for nom, ligne in variables_utilisees(etapes):
        if mots(nom) not in connus:
            raise ErreurTache(f"ligne {ligne} : {{{nom}}} inconnu (colonnes de la liste : "
                              + ", ".join(lignes[0]) + ")" if lignes[0] else f"ligne {ligne} : {{{nom}}} inconnu")
    if entete["liste"]:
        ecrire(f"   Liste : {len(lignes)} ligne(s), premiere : {next(iter(lignes[0].values()), '')}")
    ecrire(f"   Tache « {entete['nom']} » : {len(lignes)} fois.")
    navigateur, contexte, page = ouvrir_robot(p)
    if url:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.bring_to_front()
        revenez_ici()
        pause("Connectez-vous si besoin dans la fenetre du robot. Quand vous voyez l'accueil du portail, Entree...")
        attendre_portail(page)
    nom_fichier = re.sub(r"[^\w-]+", "_", sans_accents(entete["nom"]))[:40] or "tache"
    resultats = dossier_robot("resultats") / f"{nom_fichier}_{datetime.now():%Y%m%d-%H%M%S}.csv"
    colonnes_lues = []
    lignes_csv = []
    compte = {}
    tache = Tache(entete, etapes, page, url)
    ecrit = [resultats]

    def sauver():
        for essai in range(5):
            cible = ecrit[0] if essai == 0 else resultats.with_name(f"{resultats.stem}_{essai + 1}.csv")
            try:
                with open(cible, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["N", "element", "statut", "message"] + colonnes_lues)
                    for l in lignes_csv:
                        w.writerow([_cellule_sure(x) for x in l[:4] + [l[4].get(c, "") for c in colonnes_lues]])
                if cible != ecrit[0]:
                    ecrire(f"   (fichier de resultats ouvert ailleurs : ecrit dans {cible.name})")
                    ecrit[0] = cible
                return
            except OSError:
                continue

    def noter(numero, element, statut, message, lectures):
        compte[statut] = compte.get(statut, 0) + 1
        for c in lectures:
            if c not in colonnes_lues:
                colonnes_lues.append(c)
        lignes_csv.append([numero, element, statut, message, dict(lectures)])
        sauver()

    fait = 0
    erreurs_de_suite = 0
    arret = ""
    try:
        for numero, ligne in enumerate(lignes, 1):
            element = next(iter(ligne.values()), "") if ligne else (" ".join(variables_fixes.values()) or "-")
            ecrire()
            ecrire(f"=== {numero}/{len(lignes)} : {element}")
            tache.variables = dict(variables_fixes, **ligne)
            tache.element = element
            tache.nouvel_element()
            try:
                tache.executer(tache.etapes)
                tache.calme()
                tache.verifier_fenetres()
                statut, message = "OK", ""
            except Passer as e:
                statut, message = "PASSE", str(e)
            except AVerifier as e:
                statut, message = "A VERIFIER", str(e)
            except ErreurTache as e:
                statut, message = "ERREUR", str(e)
                try:
                    tache.page.screenshot(path=str(dossier_robot("resultats") / f"erreur_{numero}.png"))
                except Exception:
                    pass
            except Arreter as e:
                statut, message = "ARRETE", str(e)
                arret = f"tache arretee : {e}"
            except KeyboardInterrupt:
                statut, message = "INTERROMPU", "Ctrl+C pendant cet element : verifiez-le sur le portail"
                arret = "arrete a votre demande"
            fait = numero
            erreurs_de_suite = erreurs_de_suite + 1 if statut == "ERREUR" else 0
            ecrire(f"    --> {statut}" + (f" : {message}" if message else ""))
            noter(numero, element, statut, message, tache.lectures)
            if arret:
                break
            if erreurs_de_suite >= 3:
                arret = "3 erreurs de suite : le robot s'arrete (le portail a peut-etre change)"
                break
    except KeyboardInterrupt:
        arret = "arrete a votre demande"
    for numero in range(fait + 1, len(lignes) + 1):
        ligne = lignes[numero - 1]
        noter(numero, next(iter(ligne.values()), "") if ligne else "-", "NON FAIT", arret or "", {})
    ecrire()
    ecrire("=" * 70)
    if arret:
        ecrire(" " + arret.upper())
    ecrire(" FIN : " + ", ".join(f"{n} {s}" for s, n in compte.items()))
    for l in lignes_csv:
        if l[2] not in ("OK", "NON FAIT"):
            ecrire(f"   {l[0]}. {l[1]} : {l[2]} - {l[3][:110]}")
    ecrire(f" Resultats : Bureau > Robot > resultats > {ecrit[0].name}")
    ecrire("=" * 70)
    try:
        pause("Photo de cet ecran, puis Entree pour fermer la fenetre du robot...")
    except KeyboardInterrupt:
        pass
    try:
        navigateur.close()
    except Exception:
        pass
    return 0 if set(compte) <= {"OK", "PASSE"} else 1


# ---------------------------------------------------------------------------- programmes du navigateur (processus enfant)
def programme_enfant(mode, dossier_echange):
    """Relevé (choix 2) ou tâche (choix 3), lancés avec le Python qui a le pilote de navigateur."""
    preparer_console()
    fichier_demande = Path(dossier_echange) / "demande.json"
    echange = json.loads(fichier_demande.read_text(encoding="utf-8"))
    try:
        fichier_demande.unlink()  # l'adresse du portail ne reste pas dans le dossier temporaire
    except OSError:
        pass
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            if mode == "tache":
                return executer_tache(p, echange["fichier"], echange["url"])
            navigateur, contexte, page = ouvrir_robot(p)
            page.goto(echange["url"], wait_until="domcontentloaded", timeout=60000)
            page.bring_to_front()
            revenez_ici()
            pause("Connectez-vous si besoin dans la fenetre du robot. Quand vous voyez l'accueil du portail, Entree...")
            attendre_portail(page)
            fichier, _ = boucle_releve(page)
            ecrire()
            if fichier:
                ecrire(f"   Fichier cree : Bureau > Robot > {fichier.name}")
                ecrire("   Ouvrez-le, relisez-le, puis envoyez-le-moi (ou une photo).")
            else:
                ecrire("   Aucune page relevee : rien a envoyer.")
            try:
                navigateur.close()
            except Exception:
                pass
            return 0
    except KeyboardInterrupt:
        ecrire("   Arrete a votre demande.")
        return 130
    except ErreurTache as e:
        ecrire(f"   PROBLEME : {e}")
        ecrire("   Prenez cet ecran en photo et envoyez-la-moi.")
        return 1
    except Exception as e:
        ecrire(f"   PROBLEME : {expliquer(e)}")
        ecrire("   Prenez cet ecran en photo et envoyez-la-moi.")
        return 1


def lancer_programme_enfant(mode, demande):
    python = obtenir_python_playwright()
    if not python:
        ecrire(f"   Le robot ne peut pas ouvrir son navigateur ({RAISON_PILOTE[0]}).")
        ecrire("   Prenez cet ecran en photo et envoyez-la-moi.")
        return 1
    echange = Path(tempfile.mkdtemp(prefix="robot_"))
    try:
        (echange / "demande.json").write_text(json.dumps(demande, ensure_ascii=False), encoding="utf-8")
        enfant = subprocess.Popen([python, str(Path(__file__).resolve()), "--" + mode, str(echange)])
        try:
            return enfant.wait()
        except KeyboardInterrupt:
            try:
                enfant.wait(timeout=5)
            except Exception:
                enfant.kill()
            return 130
    finally:
        effacer_dossier(echange)


# ---------------------------------------------------------------------------- programme principal
def robot_plus_recent():
    """« robot (1).txt » : le navigateur a gardé l'ancien robot.txt et rangé le nouveau à côté."""
    try:
        moi = Path(__file__).resolve()
        recents = [f for f in moi.parent.glob(f"{moi.stem} (*){moi.suffix}") if f.stat().st_mtime > moi.stat().st_mtime]
        return max(recents, key=lambda f: f.stat().st_mtime) if recents else None
    except OSError:
        return None


def principal():
    preparer_console()
    rendre_net()
    ancien_mode = edition_rapide_coupee()
    try:
        ecrire("=" * 70)
        ecrire(" ROBOT (version %s)" % VERSION)
        ecrire("=" * 70)
        recent = robot_plus_recent()
        if recent:
            ecrire(f"   ATTENTION : un robot plus recent est la : « {recent.name} ».")
            ecrire(f"   Dans Telechargements : supprimez « {Path(__file__).stem} », renommez « {recent.stem} » en "
                   f"{Path(__file__).stem} (sans .txt), puis relancez.")
        ecrire("   1 = Test de prise en main")
        ecrire("   2 = Releve des pages du portail (pour Claude)")
        ecrire("   3 = Lancer une tache")
        choix = demander(" Votre choix (1, 2 ou 3) :")
        if choix == "1":
            test_prise_en_main()
            return 0
        if choix in ("2", "3"):
            fichier = None
            if choix == "3":
                fichier = choisir_tache()
                if fichier:
                    try:
                        lire_tache(fichier)
                    except ErreurTache as e:
                        ecrire(f"   La tache contient une erreur : {e}")
                        ecrire("   Prenez cet ecran en photo et envoyez-la-moi.")
                        fichier = None
            if choix == "2" or fichier:
                url = adresse_du_portail()
                if not url:
                    ecrire("   Pas d'adresse du portail : rien a faire.")
                else:
                    demande = {"url": url} if choix == "2" else {"fichier": str(fichier), "url": url}
                    lancer_programme_enfant("releve" if choix == "2" else "tache", demande)
        else:
            ecrire("   Rien a faire.")
    except KeyboardInterrupt:
        ecrire("\n   Arrete a votre demande.")
    except Exception as e:
        ecrire("   PROBLEME : " + (erreur_courte(e) if isinstance(e, OSError) else expliquer(e)))
        ecrire("   Prenez cet ecran en photo et envoyez-la-moi.")
    finally:
        remettre_console(ancien_mode)
    try:
        demander("\n Entree pour terminer.")
    except KeyboardInterrupt:
        pass
    return 0


def test_prise_en_main():
    ancien_mode = None
    ecrire("=" * 70)
    ecrire(" TEST DE PRISE EN MAIN")
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
            ecrire(" Il est aussi ecrit dans : Bureau > Robot > resultat_prise_en_main.txt")
        except OSError:
            pass
    ecrire(" Vous pouvez fermer le Bloc-notes (essai_clavier) ; enregistrer ou non, peu importe.")
    if bilan.lignes.get("V", ("", ""))[1] == "OK":
        ecrire(" Envoyez aussi le releve : Bureau > Robot > A_ENVOYER_releve.txt (relisez-le d'abord).")
    remettre_console(ancien_mode)
    demander("\n Entree pour terminer.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--navigateur"] and len(sys.argv) >= 3:
        sys.exit(sous_programme_navigateur(sys.argv[2]))
    if sys.argv[1:2] in (["--releve"], ["--tache"]) and len(sys.argv) >= 3:
        sys.exit(programme_enfant(sys.argv[1][2:], sys.argv[2]))
    sys.exit(principal())

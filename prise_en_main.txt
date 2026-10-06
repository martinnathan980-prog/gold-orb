# -*- coding: utf-8 -*-
r"""
PRISE EN MAIN DU ROBOT - ETAPE 1
================================

Le robot montre, une chose a la fois, qu'il sait prendre la main sur votre ordinateur :
    1. Python fonctionne
    2. fichiers et dossiers : il cree un dossier d'essai sur le Bureau et l'ouvre
    3. clavier : il ouvre le Bloc-notes et y ecrit une phrase tout seul
    4. souris : il bouge la souris et clique dans le Bloc-notes
    5. votre navigateur habituel : il y ouvre l'adresse de votre portail
    6. son propre navigateur : il remplit et clique une page d'essai
    7. ce navigateur sur votre portail : il compte et encadre ce qu'il sait cliquer
    8. un clic que VOUS choisissez sur le portail (un menu, un lien), apres votre accord

Il ne modifie RIEN dans vos outils : il ne fait que creer le dossier « Robot - essai »
sur le Bureau. Sur le portail, il refuse de cliquer sur tout ce qui pourrait modifier
(Supprimer, Enregistrer, Valider, Dupliquer, Nouveau, OK...).

A la fin, un RESULTAT s'affiche : prenez-le en photo et envoyez-le. Il est aussi ecrit
dans « Robot - essai\resultat_prise_en_main.txt ». Il ne contient aucune donnee du
portail : ni adresse, ni texte des pages, seulement des OK / ECHEC et des nombres.

Lancement, dans une fenetre noire ouverte dans le dossier ou est ce fichier :
    python prise_en_main.txt
(si « python » n'est pas reconnu :  py prise_en_main.txt )
"""

import ctypes
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "1"
WINDOWS = os.name == "nt"
# pour les essais automatiques du programme seulement (navigateur caché)
INVISIBLE = os.environ.get("PRISE_EN_MAIN_INVISIBLE") == "1"

# Sur le portail, le robot ne clique jamais sur ce qui pourrait modifier quelque chose.
MOTS_INTERDITS = re.compile(
    r"supprim|effac|delet|remov|retir|corbeil|dupliq|duplic|copi|copy|valid|enregistr|sauv|save|"
    r"creer|cree|creat|nouveau|nouvelle|\bnew\b|ajout|\badd\b|modif|edit|envoy|\bsend\b|soumet|submit|"
    r"confirm|annul|cancel|vider|archiv|publi|transfer|statut|status|etat|rejet|reject|approuv|approv|"
    r"sign|associ|rattach|detach|import|revis|liber|releas|verrou|lock|bascul|clotur|ferm|close|"
    r"^oui$|^ok$|^yes$|^non$|^no$|^go$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------- console
def preparer_console():
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def ecrire(texte=""):
    print(texte, flush=True)


def demander(question, defaut=""):
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


def sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", str(texte)) if unicodedata.category(c) != "Mn")


def masquer(texte, url=""):
    """Une erreur ne doit jamais emporter l'adresse du portail dans le resultat."""
    texte = str(texte or "")
    if url:
        texte = texte.replace(url, "<portail>")
        hote = urlsplit(url).hostname or ""
        if len(hote) >= 3:
            texte = re.sub(r"(?<![\w.-])" + re.escape(hote) + r"(?![\w-])", "<portail>", texte, flags=re.IGNORECASE)
    texte = re.sub(r"(https?|file)://\S+", "<adresse>", texte)
    return " ".join(texte.split())[:160]


def premiere_ligne(erreur):
    lignes = [l.strip() for l in str(erreur).splitlines() if l.strip()]
    return lignes[0] if lignes else erreur.__class__.__name__


# ---------------------------------------------------------------------------- bilan
CODES = {"OK": "1", "ECHEC": "0", "SAUTE": "-", "PAS VU": "?", "NON DISPONIBLE": "x"}


class Bilan:
    def __init__(self):
        self.lignes = []  # (lettre, intitule, statut, detail)

    def noter(self, lettre, intitule, statut, detail=""):
        self.lignes = [l for l in self.lignes if l[0] != lettre]
        self.lignes.append((lettre, intitule, statut, detail))
        marque = {"OK": "OK", "ECHEC": "ECHEC", "SAUTE": "saute", "PAS VU": "PAS VU", "NON DISPONIBLE": "non disponible"}
        ecrire(f"   --> {intitule} : {marque.get(statut, statut)}" + (f"  ({detail})" if detail else ""))

    def code(self):
        return " ".join(l[0] + CODES.get(l[2], "?") for l in self.lignes)

    def texte(self):
        lignes = [
            "RESULTAT DE LA PRISE EN MAIN (version %s) - %s" % (VERSION, datetime.now().strftime("%d/%m/%Y %H:%M")),
            "-" * 70,
        ]
        for lettre, intitule, statut, detail in self.lignes:
            lignes.append(f" {lettre}  {(intitule + ' ').ljust(42, '.')} {statut}")
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
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    kernel32.GetConsoleWindow.restype = wintypes.HWND

    INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
    KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
    MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
    VK_RETURN = 0x0D
    GA_ROOT = 2
    SM_CXSCREEN, SM_CYSCREEN, SM_SWAPBUTTON = 0, 1, 23


def rendre_net():
    """Coordonnées de la souris en vrais pixels, même avec un affichage à 125 % ou 150 %."""
    if not WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
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


def _bouton_souris(relache):
    gauche_inverse = bool(user32.GetSystemMetrics(SM_SWAPBUTTON))  # souris de gaucher
    if gauche_inverse:
        drapeau = MOUSEEVENTF_RIGHTUP if relache else MOUSEEVENTF_RIGHTDOWN
    else:
        drapeau = MOUSEEVENTF_LEFTUP if relache else MOUSEEVENTF_LEFTDOWN
    e = INPUT()
    e.type = INPUT_MOUSE
    e.mi = MOUSEINPUT(0, 0, 0, drapeau, 0, 0)
    return e


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


def est_bloc_notes(hwnd):
    return bool(hwnd) and (_classe(hwnd) == "Notepad" or bool(re.search(r"bloc-notes|notepad", _titre(hwnd), re.I)))


def attendre_fenetre(test, secondes):
    fin = time.time() + secondes
    while time.time() < fin:
        hwnd = fenetre_active()
        if test(hwnd):
            return hwnd
        time.sleep(0.2)
    return None


def taper(texte, hwnd, delai=0.04):
    """Tape le texte, caractère par caractère, SEULEMENT tant que la fenêtre hwnd est au premier
    plan : si vous cliquez ailleurs, le robot s'arrête (il n'écrit jamais dans une autre fenêtre)."""
    ecrits = 0
    for caractere in texte:
        if fenetre_active() != hwnd:
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
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        try:
            user32.SetForegroundWindow(hwnd)
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
    ecrire(f"   Le robot va creer le dossier « Robot - essai » sur votre Bureau, y ecrire")
    ecrire(f"   le fichier bonjour.txt, puis ouvrir ce dossier.")
    pause()
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "bonjour.txt").write_text(
            "Bonjour ! Ce fichier a ete cree par le robot le %s.\n"
            "Vous pouvez supprimer le dossier « Robot - essai » quand vous voulez.\n"
            % datetime.now().strftime("%d/%m/%Y a %H:%M"), encoding="utf-8")
    except Exception as e:
        bilan.noter("F", "Fichiers et dossiers", "ECHEC", masquer(premiere_ligne(e)))
        return dossier if dossier.is_dir() else None
    try:
        ouvrir_dans_windows(dossier)
    except Exception as e:
        bilan.noter("F", "Fichiers et dossiers", "PAS VU", "fichier cree, dossier pas ouvert : " + masquer(premiere_ligne(e)))
        return dossier
    time.sleep(1.5)
    if oui("   Voyez-vous le dossier « Robot - essai » avec le fichier bonjour.txt ?"):
        bilan.noter("F", "Fichiers et dossiers", "OK")
    else:
        bilan.noter("F", "Fichiers et dossiers", "PAS VU", "fichier cree mais dossier pas vu a l'ecran")
    return dossier


def etape_clavier(bilan):
    titre_etape(3, "Le clavier : ecrire tout seul dans le Bloc-notes")
    if not WINDOWS:
        bilan.noter("K", "Clavier (Bloc-notes)", "NON DISPONIBLE", "pas Windows")
        return None
    ecrire("   Le robot va ouvrir le Bloc-notes et y ecrire une phrase tout seul.")
    ecrire("   Pendant qu'il ecrit (10 secondes) : NE TOUCHEZ NI AU CLAVIER NI A LA SOURIS.")
    ecrire("   (Si vous cliquez ailleurs, il s'arrete : il n'ecrit jamais dans une autre fenetre.)")
    pause()
    try:
        subprocess.Popen(["notepad.exe"])
    except Exception as e:
        bilan.noter("K", "Clavier (Bloc-notes)", "ECHEC", "Bloc-notes impossible a ouvrir : " + masquer(premiere_ligne(e)))
        return None
    hwnd = attendre_fenetre(est_bloc_notes, 10)
    if not hwnd:
        ecrire("   Le Bloc-notes n'est pas passe devant. CLIQUEZ UNE FOIS DEDANS : le robot attend 20 secondes...")
        hwnd = attendre_fenetre(est_bloc_notes, 20)
    if not hwnd:
        bilan.noter("K", "Clavier (Bloc-notes)", "ECHEC", "le Bloc-notes n'est jamais passe au premier plan")
        return None
    time.sleep(1.0)
    try:
        ecrits, complet = taper("Bonjour ! Je suis le robot. J'ecris tout seul, sans toucher au clavier.\n"
                                "Avec les accents : é è à ç ù ê.\n", hwnd)
    except OSError as e:
        revenir_console()
        bilan.noter("K", "Clavier (Bloc-notes)", "ECHEC", masquer(str(e)))
        return hwnd
    revenir_console()
    if not complet:
        ecrire(f"   Arrete apres {ecrits} caractere(s) : une autre fenetre est passee devant.")
    ecrire("   Revenez dans CETTE fenetre noire (cliquez dedans) pour repondre.")
    if oui("   Avez-vous vu la phrase s'ecrire toute seule dans le Bloc-notes ?"):
        bilan.noter("K", "Clavier (Bloc-notes)", "OK" if complet else "ECHEC",
                    "" if complet else f"interrompu apres {ecrits} caracteres (autre fenetre devant)")
    else:
        bilan.noter("K", "Clavier (Bloc-notes)", "PAS VU", f"{ecrits} caracteres envoyes, rien vu a l'ecran")
    return hwnd


def etape_souris(bilan, hwnd):
    titre_etape(4, "La souris : bouger et cliquer toute seule")
    if not WINDOWS:
        bilan.noter("S", "Souris", "NON DISPONIBLE", "pas Windows")
        return
    ecrire("   Le robot va faire un carre avec la souris" + (", puis cliquer DANS le Bloc-notes" if hwnd else "")
           + " et y ecrire une ligne.")
    ecrire("   NE TOUCHEZ PAS A LA SOURIS pendant 5 secondes. Il remet ensuite la souris ou elle etait.")
    pause()
    depart = position_souris()
    try:
        if hwnd:
            user32.SetForegroundWindow(hwnd)
            if not attendre_fenetre(lambda h: h == hwnd, 2):
                ecrire("   CLIQUEZ UNE FOIS DANS LE BLOC-NOTES : le robot attend 20 secondes...")
                if not attendre_fenetre(lambda h: h == hwnd, 20):
                    hwnd = None
        if hwnd:
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
        else:
            cx, cy = user32.GetSystemMetrics(SM_CXSCREEN) // 2, user32.GetSystemMetrics(SM_CYSCREEN) // 2
        carre = [(cx - 120, cy - 80), (cx + 120, cy - 80), (cx + 120, cy + 80), (cx - 120, cy + 80), (cx, cy)]
        bouge = True
        for x, y in carre:
            deplacer_doucement(x, y)
            bouge = bouge and abs(position_souris()[0] - x) <= 2 and abs(position_souris()[1] - y) <= 2
        clic = "pas de Bloc-notes"
        if hwnd:
            sous = user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(cx, cy)), GA_ROOT)
            if sous == hwnd and fenetre_active() == hwnd:  # on ne clique QUE sur le Bloc-notes
                _envoyer(_bouton_souris(False), _bouton_souris(True))
                time.sleep(0.4)
                taper("\nLe robot a aussi bouge la souris et clique ici.\n", hwnd)
                clic = "clic fait"
            else:
                clic = "clic annule : le Bloc-notes n'etait pas sous la souris"
        deplacer_doucement(*depart, duree=0.3)
    except OSError as e:
        revenir_console()
        bilan.noter("S", "Souris", "ECHEC", masquer(str(e)))
        return
    revenir_console()
    ecrire("   Revenez dans CETTE fenetre noire (cliquez dedans) pour repondre.")
    if not bouge:
        bilan.noter("S", "Souris", "ECHEC", "la souris n'est pas allee ou le robot voulait")
    elif oui("   Avez-vous vu la souris bouger toute seule" + (" et la ligne s'ecrire apres le clic ?" if hwnd else " ?")):
        bilan.noter("S", "Souris", "OK", clic)
    else:
        bilan.noter("S", "Souris", "PAS VU", clic)


def demander_adresse():
    ecrire()
    ecrire("   Pour les etapes suivantes, le robot a besoin de l'adresse de votre portail")
    ecrire("   (celle de la page d'accueil, qui commence souvent par https://).")
    ecrire("   Copiez-la dans la barre d'adresse de votre Chrome, puis faites un CLIC DROIT")
    ecrire("   dans cette fenetre noire pour la coller. Entree sans rien = sauter.")
    ecrire("   (L'adresse n'est ecrite nulle part : elle sert seulement pendant ce test.)")
    adresse = demander("   Adresse du portail :").strip().strip('"')
    if adresse and not re.match(r"^[a-z][a-z0-9+.-]*://", adresse, re.I):
        adresse = "https://" + adresse
    return adresse


def etape_navigateur_habituel(bilan, url):
    titre_etape(5, "Votre navigateur habituel")
    if not url:
        bilan.noter("W", "Portail dans votre navigateur", "SAUTE", "pas d'adresse donnee")
        return
    ecrire("   Le robot va ouvrir le portail dans VOTRE navigateur habituel (comme un clic sur un lien).")
    pause()
    try:
        ouvert = webbrowser.open(url)
    except Exception as e:
        bilan.noter("W", "Portail dans votre navigateur", "ECHEC", masquer(premiere_ligne(e), url))
        return
    time.sleep(2)
    if oui("   La page du portail s'est-elle ouverte dans votre navigateur ?"):
        bilan.noter("W", "Portail dans votre navigateur", "OK")
    else:
        bilan.noter("W", "Portail dans votre navigateur", "PAS VU" if ouvert else "ECHEC",
                    "" if ouvert else "Windows n'a pas trouve de navigateur par defaut")


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
    sous_chemins = [("venv", "Scripts", "python.exe"), ("venv", "bin", "python")]
    for base in bases:
        for dossier in (base, base / "robot-web"):
            for morceaux in sous_chemins:
                candidat = dossier.joinpath(*morceaux)
                if candidat.is_file() and _python_avec_playwright(candidat):
                    return str(candidat)
    return None


def obtenir_python_playwright():
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
    if not oui("   Installer le pilote maintenant (2 a 5 minutes, depuis Internet) ?", "o"):
        return None
    commande = [sys.executable, "-m", "pip", "install", "--user", "playwright"]
    ecrire("   " + " ".join(commande[1:]))
    if subprocess.call(commande) != 0:
        ecrire("   L'installation n'a pas abouti (Internet bloque pour Python ?).")
        return None
    return sys.executable if _python_avec_playwright(sys.executable) else None


def etape_navigateur_robot(bilan, url):
    titre_etape(6, "Le navigateur du robot")
    ecrire("   Le robot va ouvrir SON navigateur (une fenetre Chrome a part, vide, qui ne touche")
    ecrire("   pas a votre Chrome), puis remplir et cliquer une page d'essai.")
    pause()
    python = obtenir_python_playwright()
    if not python:
        for lettre, intitule in (("N", "Navigateur du robot (page d'essai)"), ("R", "Navigateur du robot sur le portail"),
                                 ("C", "Clic choisi sur le portail")):
            bilan.noter(lettre, intitule, "SAUTE", "pilote de navigateur absent")
        return
    with tempfile.TemporaryDirectory() as dossier:
        resultat = Path(dossier) / "resultat.json"
        try:
            subprocess.call([python, str(Path(__file__).resolve()), "--navigateur", str(resultat), url or "-"])
        except Exception as e:
            bilan.noter("N", "Navigateur du robot (page d'essai)", "ECHEC", masquer(premiere_ligne(e), url))
            return
        try:
            notes = json.loads(resultat.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            notes = [["N", "Navigateur du robot (page d'essai)", "ECHEC", "le programme du navigateur s'est arrete"]]
    for lettre, intitule, statut, detail in notes:
        if lettre not in ("N", "R", "C", "D"):
            continue
        bilan.lignes = [l for l in bilan.lignes if l[0] != lettre]
        bilan.lignes.append((lettre, intitule, statut, masquer(detail, url)))


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
           cadres: q('iframe, frame').length, frameset: !!document.querySelector('frameset'), ombres: ombres,
           dessins: q('canvas, embed, object').filter(vis).length };
}"""

JS_CLIQUABLES = """() => Array.from(document.querySelectorAll('a[href], button, input[type=submit], input[type=button], [role=button], [role=menuitem], [role=tab]'))
  .filter(e => { const r = e.getBoundingClientRect(); return r.width > 4 && r.height > 4 && r.top >= 0 && r.top < innerHeight; })
  .slice(0, 5).map(e => { e.setAttribute('data-robot-essai', '1'); return 1; }).length"""

JS_ENCADRER = """(e, ms) => { e.scrollIntoView({block: 'center', inline: 'nearest'});
  const avant = [e.style.outline, e.style.outlineOffset];
  e.style.outline = '4px solid #dc2626'; e.style.outlineOffset = '2px';
  setTimeout(() => { e.style.outline = avant[0]; e.style.outlineOffset = avant[1]; }, ms); }"""


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


def _ouvrir_navigateur(p, notes):
    essais = []
    for canal, nom in (("chrome", "Chrome"), ("msedge", "Edge"), (None, "Chromium du robot")):
        try:
            options = {"headless": INVISIBLE, "slow_mo": 0 if INVISIBLE else 120}
            if canal:
                options["channel"] = canal
            return p.chromium.launch(**options), nom, canal, essais
        except Exception as e:
            essais.append(f"{nom} : {premiere_ligne(e)[:70]}")
    notes.append(["N", "Navigateur du robot (page d'essai)", "ECHEC", " | ".join(essais)])
    return None, "", None, essais


def _verifier_demarrage(p, canal, notes):
    """Chrome « avec un profil » (comme le robot quand il garde votre connexion) : quels onglets
    s'ouvrent tout seuls au démarrage ? (des onglets imposés, une page Google... peuvent détourner le robot)"""
    with tempfile.TemporaryDirectory() as profil:
        try:
            options = {"headless": INVISIBLE}
            if canal:
                options["channel"] = canal
            contexte = p.chromium.launch_persistent_context(profil, **options)
        except Exception as e:
            notes.append(["D", "Demarrage avec un profil", "ECHEC", premiere_ligne(e)[:120]])
            return
        try:
            time.sleep(3)
            sortes = []
            for page in contexte.pages:
                adresse = (page.url or "").lower()
                hote = urlsplit(adresse).hostname or ""
                if adresse in ("", "about:blank") or adresse.startswith(("chrome://newtab", "chrome://new-tab-page", "edge://newtab")):
                    sortes.append("vide")
                elif "google." in hote:
                    sortes.append("google")
                elif adresse.startswith(("chrome://", "edge://", "chrome-search://")):
                    sortes.append("page du navigateur")
                else:
                    sortes.append("autre site")
            notes.append(["D", "Demarrage avec un profil", "OK",
                          f"{len(contexte.pages)} onglet(s) au demarrage : " + (", ".join(sortes) or "aucun")])
        finally:
            try:
                contexte.close()
            except Exception:
                pass


def _page_essai(page, nom, notes):
    with tempfile.TemporaryDirectory() as dossier:
        fichier = Path(dossier) / "page_essai.html"
        fichier.write_text(PAGE_ESSAI, encoding="utf-8")
        page.goto(fichier.as_uri())
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
    notes.append(["N", "Navigateur du robot (page d'essai)", "OK", f"avec {nom}"])


def _analyser_portail(page, url, notes):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.bring_to_front()
    ecrire()
    ecrire("   La fenetre du robot affiche le portail.")
    ecrire("   SI le portail demande de vous connecter : connectez-vous DANS LA FENETRE DU ROBOT")
    ecrire("   (votre mot de passe n'est ni lu ni garde : cette fenetre est oubliee a la fin).")
    pause("Quand vous voyez la page d'accueil du portail, revenez ici et appuyez sur Entree...")
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
    detail = (f"{total['cliquables']} elements cliquables, {total['champs']} champs, {cadres_lus} cadre(s)"
              + (f" dont {cadres_lus - 1} cadre(s) interieur(s)" if cadres_lus > 1 else "")
              + (", page en cadres (frameset)" if frameset else "")
              + (f", {cadres_illisibles} cadre(s) illisible(s)" if cadres_illisibles else "")
              + (f", {total['ombres']} composant(s) web" if total["ombres"] else "")
              + (f", {total['dessins']} zone(s) dessinee(s)" if total["dessins"] else ""))
    ecrire("   Le robot voit : " + detail)
    if meilleur is not None and max_cliquables > 0:
        ecrire("   Il encadre en rouge, un par un, quelques elements qu'il saurait cliquer (sans cliquer)...")
        try:
            meilleur.evaluate(JS_CLIQUABLES)
            marques = meilleur.locator("[data-robot-essai]")
            for i in range(min(marques.count(), 5)):
                _encadrer(marques.nth(i), 900)
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 500)
            time.sleep(0.8)
            page.mouse.wheel(0, -500)
        except Exception:
            pass
    vu = oui("   Avez-vous vu des cadres rouges apparaitre sur le portail, dans la fenetre du robot ?")
    statut = "OK" if max_cliquables > 0 and vu else ("PAS VU" if max_cliquables > 0 else "ECHEC")
    notes.append(["R", "Navigateur du robot sur le portail", statut, detail])


def _candidats(page, mot):
    """Tous les éléments qui portent ce texte, dans tous les cadres : d'abord le texte exact."""
    for exact in (True, False):
        trouves = []
        for numero, cadre in enumerate(page.frames):
            try:
                loc = cadre.get_by_text(mot, exact=exact)
                for i in range(min(loc.count(), 10)):
                    trouves.append((numero, loc.nth(i)))
            except Exception:
                continue
        if trouves:
            return trouves, exact
    return [], True


def _survoler_au_dessus(loc):
    """Élément caché dans un menu fermé : survoler le premier parent visible (le menu), comme la souris."""
    for niveau in range(1, 9):
        parent = loc.locator("xpath=" + "/".join([".."] * niveau))
        try:
            if parent.count() and parent.first.is_visible():
                parent.first.hover(timeout=3000)
                time.sleep(0.8)
                return loc.is_visible()
        except Exception:
            return False
    return False


def _clic_choisi(page, notes):
    ecrire()
    ecrire("=" * 70)
    ecrire(" ETAPE 8 : un clic que VOUS choisissez sur le portail")
    ecrire("=" * 70)
    ecrire("   Tapez le texte d'un MENU ou d'un LIEN visible sur le portail (par exemple GATES).")
    ecrire("   Le robot le cherche, l'encadre en rouge, et vous demande avant de cliquer.")
    ecrire("   Par prudence, il refuse Supprimer, Enregistrer, Valider, Dupliquer, Nouveau, OK...")
    essais = []
    while len(essais) < 5:
        mot = demander("   Texte a chercher (Entree sans rien = finir) :")
        if not mot:
            break
        numero = len(essais) + 1
        if MOTS_INTERDITS.search(sans_accents(mot)):
            ecrire("   Refuse : ce mot ressemble a une action qui modifie. Choisissez un menu ou un lien.")
            continue
        trouves, exact = _candidats(page, mot)
        visibles = [(c, l) for c, l in trouves if _visible(l)]
        if not trouves:
            ecrire("   Pas trouve sur la page. Verifiez l'orthographe (majuscules comprises), ou essayez un autre mot.")
            essais.append(f"mot {numero} : pas trouve")
            continue
        if not visibles:
            ecrire("   Trouve, mais CACHE (dans un menu ferme ?). Le robot survole le menu au-dessus...")
            if _survoler_au_dessus(trouves[0][1]):
                visibles = [trouves[0]]
                ecrire("   Le survol a ouvert le menu : l'element est maintenant visible.")
            else:
                ecrire("   Toujours cache. Essayez d'abord le texte du menu au-dessus.")
                essais.append(f"mot {numero} : trouve mais cache")
                continue
        cadre, loc = visibles[0]
        if len(visibles) > 1:
            ecrire(f"   {len(visibles)} elements visibles portent ce texte : le robot prend le premier.")
        _encadrer(loc, 1500)
        ou = "cadre principal" if cadre == 0 else "cadre interieur"
        texte_loc = (loc.inner_text(timeout=2000) or "").strip() if _visible(loc) else ""
        if MOTS_INTERDITS.search(sans_accents(texte_loc)):
            ecrire("   Refuse : l'element trouve ressemble a une action qui modifie.")
            essais.append(f"mot {numero} : refuse (action)")
            continue
        if not oui(f"   Trouve ({ou}, texte {'exact' if exact else 'approchant'}), encadre en rouge. Le robot clique dessus ?", "o"):
            essais.append(f"mot {numero} : trouve, pas clique ({ou})")
            continue
        try:
            loc.click(timeout=10000)
            page.wait_for_timeout(1500)
            ecrire("   Clic fait. Regardez la fenetre du robot : la page a-t-elle reagi comme avec votre souris ?")
            reagi = oui("   Ca a marche ?")
            essais.append(f"mot {numero} : clique ({ou}){'' if reagi else ', sans effet visible'}")
        except Exception as e:
            ecrire("   Le clic n'a pas marche : " + premiere_ligne(e)[:120])
            # le texte de l'erreur cite le mot cherché (peut-être une donnée) : il ne part pas dans le résultat
            erreur = re.sub(re.escape(mot), "<mot>", premiere_ligne(e), flags=re.IGNORECASE)
            essais.append(f"mot {numero} : clic en echec ({erreur[:60]})")
    if not essais:
        notes.append(["C", "Clic choisi sur le portail", "SAUTE", "aucun mot donne"])
    else:
        bons = [e for e in essais if "clique (" in e and "sans effet" not in e]
        notes.append(["C", "Clic choisi sur le portail", "OK" if bons else "ECHEC", " ; ".join(essais)])


def _visible(loc):
    try:
        return loc.is_visible()
    except Exception:
        return False


def sous_programme_navigateur(fichier_resultat, url):
    """Étapes 6 à 8, lancées avec le Python qui a le pilote de navigateur."""
    preparer_console()
    notes = []
    url = "" if url == "-" else url

    def sauver():
        Path(fichier_resultat).write_text(json.dumps(notes, ensure_ascii=False), encoding="utf-8")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        notes.append(["N", "Navigateur du robot (page d'essai)", "ECHEC", "pilote absent : " + premiere_ligne(e)])
        sauver()
        return 1
    try:
        with sync_playwright() as p:
            navigateur, nom, canal, essais = _ouvrir_navigateur(p, notes)
            if navigateur is None:
                sauver()
                return 1
            if essais:
                ecrire("   (essais precedents : " + " | ".join(essais) + ")")
            try:
                page = navigateur.new_context(no_viewport=True).new_page()
                try:
                    _page_essai(page, nom, notes)
                except Exception as e:
                    notes.append(["N", "Navigateur du robot (page d'essai)", "ECHEC", f"avec {nom} : " + premiere_ligne(e)[:120]])
                sauver()
                if notes[-1][2] == "OK" and not oui("   Avez-vous vu le robot ecrire « Robot » et cliquer sur Valider ?"):
                    notes[-1][2] = "PAS VU"
                _verifier_demarrage(p, canal, notes)
                sauver()
                titre_etape(7, "Le navigateur du robot sur votre portail")
                if not url:
                    notes.append(["R", "Navigateur du robot sur le portail", "SAUTE", "pas d'adresse donnee"])
                    notes.append(["C", "Clic choisi sur le portail", "SAUTE", "pas d'adresse donnee"])
                else:
                    try:
                        _analyser_portail(page, url, notes)
                    except Exception as e:
                        notes.append(["R", "Navigateur du robot sur le portail", "ECHEC", masquer(premiere_ligne(e), url)])
                    sauver()
                    if notes[-1][0] == "R" and notes[-1][2] != "ECHEC":
                        _clic_choisi(page, notes)
                    else:
                        notes.append(["C", "Clic choisi sur le portail", "SAUTE", "portail non affiche"])
                sauver()
                pause("Fin des essais du navigateur. Entree pour fermer la fenetre du robot...")
            finally:
                try:
                    navigateur.close()
                except Exception:
                    pass
    except Exception as e:
        notes.append(["N", "Navigateur du robot (page d'essai)", "ECHEC", masquer(premiere_ligne(e), url)])
    for note in notes:
        note[3] = masquer(note[3], url)
    sauver()
    return 0


# ---------------------------------------------------------------------------- programme principal
def principal():
    preparer_console()
    rendre_net()
    ecrire("=" * 70)
    ecrire(" PRISE EN MAIN DU ROBOT - etape 1 (version %s)" % VERSION)
    ecrire("=" * 70)
    ecrire(" Le robot va montrer, une chose a la fois, qu'il sait se servir de votre")
    ecrire(" ordinateur : fichiers, clavier, souris, navigateur. Il ne modifie RIEN dans vos")
    ecrire(" outils. Avant chaque etape, il explique et attend votre Entree.")
    ecrire(" Pour arreter a tout moment : Ctrl + C dans cette fenetre.")
    bilan = Bilan()
    dossier = None
    try:
        etape_python(bilan)
        dossier = etape_fichiers(bilan)
        hwnd = etape_clavier(bilan)
        etape_souris(bilan, hwnd)
        url = demander_adresse()
        etape_navigateur_habituel(bilan, url)
        etape_navigateur_robot(bilan, url)
    except KeyboardInterrupt:
        ecrire("\n   Arrete a votre demande.")
    texte = bilan.texte()
    ecrire()
    ecrire("=" * 70)
    ecrire(texte)
    ecrire("=" * 70)
    ecrire(" PRENEZ CE RESULTAT EN PHOTO et envoyez-le (ou le fichier ci-dessous).")
    if dossier is not None:
        try:
            fichier = dossier / "resultat_prise_en_main.txt"
            fichier.write_text(texte + "\n", encoding="utf-8")
            ecrire(f" Aussi ecrit dans : {fichier}")
        except OSError:
            pass
    ecrire(" Vous pouvez fermer le Bloc-notes SANS enregistrer.")
    demander("\n Entree pour terminer.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--navigateur"] and len(sys.argv) >= 4:
        sys.exit(sous_programme_navigateur(sys.argv[2], sys.argv[3]))
    sys.exit(principal())

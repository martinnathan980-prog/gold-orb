"""Petites aides de console : lire une touche sans bloquer, demander un mot de passe.

Sert pendant l'enregistrement : le programme doit continuer à faire tourner le
navigateur tout en surveillant si l'utilisateur appuie sur Entrée dans le terminal.
"""

from __future__ import annotations

import getpass
import signal
import sys
from typing import Callable, List, Optional


def console_interactive() -> bool:
    try:
        return bool(sys.stdin) and sys.stdin.isatty()
    except Exception:
        return False


def touche_entree_disponible() -> bool:
    """Vrai si l'utilisateur vient d'appuyer sur Entrée dans le terminal.

    Ne bloque jamais. Renvoie False si l'entrée n'est pas un vrai terminal
    (exécution planifiée, sortie redirigée, tests).
    """
    if not console_interactive():
        return False
    try:
        if sys.platform == "win32":
            import msvcrt

            appuye = False
            while msvcrt.kbhit():
                touche = msvcrt.getwch()
                if touche in ("\r", "\n"):
                    appuye = True
            return appuye
        import select

        prets, _, _ = select.select([sys.stdin], [], [], 0)
        if not prets:
            return False
        sys.stdin.readline()
        return True
    except Exception:
        return False


# Second code envoyé par les flèches et touches de fonction après « \xe0 ». Seul, « \xe0 »
# est la lettre « à » (touche 0 du clavier français) : il ne faut pas la confondre.
CODES_ETENDUS = set("GHIKMOPQRSstuvw") | {chr(c) for c in (0x84, 0x85, 0x86, 0x8D, 0x91, 0x92, 0x93, 0x94)}


def lire_ligne(pomper: Callable[[], None]) -> Optional[str]:
    """Lit une ligne tapée dans le terminal, comme input(), mais sans figer le navigateur :
    `pomper` est appelé en boucle pendant l'attente. None si pas de vrai terminal.

    Ctrl+C est intercepté le temps de la lecture puis relancé ici, hors de Playwright :
    reçu au milieu d'un appel Playwright, il laisserait le navigateur impossible à fermer.
    """
    if not console_interactive():
        return None
    interrompu: List[int] = []
    try:
        ancien = signal.signal(signal.SIGINT, lambda *_: interrompu.append(1))
    except (ValueError, OSError):  # pas dans le fil principal
        ancien = None
    try:
        return _lire_ligne_windows(pomper, interrompu) if sys.platform == "win32" else _lire_ligne_posix(pomper, interrompu)
    finally:
        if ancien is not None:
            signal.signal(signal.SIGINT, ancien)


def _pomper(pomper: Callable[[], None], interrompu: List[int]) -> None:
    if interrompu:
        raise KeyboardInterrupt
    pomper()
    if interrompu:
        raise KeyboardInterrupt


def _lire_ligne_posix(pomper: Callable[[], None], interrompu: List[int]) -> str:
    import select

    while True:
        prets, _, _ = select.select([sys.stdin], [], [], 0)
        if prets:
            ligne = sys.stdin.readline()
            if interrompu:
                raise KeyboardInterrupt
            return ligne.rstrip("\r\n")
        _pomper(pomper, interrompu)


def _lire_ligne_windows(pomper: Callable[[], None], interrompu: List[int]) -> str:
    import msvcrt

    tampon: List[str] = []

    def ecrire(texte: str) -> None:
        sys.stdout.write(texte)
        sys.stdout.flush()

    while True:
        while msvcrt.kbhit():
            touche = msvcrt.getwch()
            if touche == "\x00":
                msvcrt.getwch()  # touche de fonction : second code ignoré
                continue
            if touche == "\xe0" and msvcrt.kbhit():
                suivante = msvcrt.getwch()  # une flèche envoie ses deux codes d'un coup
                if suivante in CODES_ETENDUS:
                    continue
                tampon.append(touche)
                ecrire(touche)
                touche = suivante
            if touche in ("\r", "\n"):
                ecrire("\n")
                return "".join(tampon)
            if touche == "\x03":
                raise KeyboardInterrupt
            if touche == "\b":
                if tampon:
                    tampon.pop()
                    ecrire("\b \b")
            else:
                tampon.append(touche)
                ecrire(touche)
        _pomper(pomper, interrompu)


def vider_clavier() -> None:
    """Oublie les touches tapées en avance (un second Entrée ne doit rien déclencher)."""
    if not console_interactive():
        return
    try:
        if sys.platform == "win32":
            import msvcrt

            while msvcrt.kbhit():
                msvcrt.getwch()
        else:
            import termios

            termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:  # noqa: BLE001
        pass


def demander_secret(question: str) -> Optional[str]:
    """Demande un mot de passe sans l'afficher. None si pas de terminal."""
    if not console_interactive():
        return None
    try:
        return getpass.getpass(question)
    except Exception:
        return None

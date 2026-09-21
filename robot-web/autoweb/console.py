"""Petites aides de console : lire une touche sans bloquer, demander un mot de passe.

Sert pendant l'enregistrement : le programme doit continuer à faire tourner le
navigateur tout en surveillant si l'utilisateur appuie sur Entrée dans le terminal.
"""

from __future__ import annotations

import getpass
import sys
from typing import Optional


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


def demander_secret(question: str) -> Optional[str]:
    """Demande un mot de passe sans l'afficher. None si pas de terminal."""
    if not console_interactive():
        return None
    try:
        return getpass.getpass(question)
    except Exception:
        return None

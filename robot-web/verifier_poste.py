"""Diagnostic du poste : dit exactement ce qui marche et ce qui est bloqué.

À lancer quand l'installation échoue :
    Windows :  py verifier_poste.py
    Mac      :  python3 verifier_poste.py

N'installe rien, ne modifie rien, n'envoie rien. Affiche un rapport à recopier.
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent


def titre(texte):
    print()
    print("=" * 62)
    print(" " + texte)
    print("=" * 62)


def ligne(nom, valeur):
    print("  %-34s %s" % (nom + " :", valeur))


def essayer(description, commande):
    """Lance une commande et dit si elle passe, sans jamais planter."""
    try:
        resultat = subprocess.run(commande, capture_output=True, text=True, timeout=120)
        if resultat.returncode == 0:
            print("  OK    %s" % description)
            return True, (resultat.stdout or "").strip()
        detail = ((resultat.stderr or "") + (resultat.stdout or "")).strip().splitlines()
        print("  ECHEC %s" % description)
        for l in detail[:3]:
            print("          %s" % l[:150])
        return False, "\n".join(detail[:3])
    except Exception as e:
        print("  ECHEC %s" % description)
        print("          %s" % str(e)[:150])
        return False, str(e)


def main():
    titre("ROBOT WEB - diagnostic du poste")
    ligne("Systeme", "%s %s" % (platform.system(), platform.release()))
    ligne("Python", sys.version.split()[0])
    ligne("Emplacement de Python", sys.executable)
    ligne("Dossier du robot", str(RACINE))

    titre("1. Executer un programme depuis le profil utilisateur")
    print("  Certaines entreprises l'interdisent (erreur 1260).")
    cible = RACINE / "essai_venv"
    essayer("creation d'un environnement isole", [sys.executable, "-m", "venv", str(cible)])
    python_venv = cible / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    venv_ok = False
    if python_venv.exists():
        venv_ok, _ = essayer("execution d'un programme de ce dossier", [str(python_venv), "-c", "print(1)"])
    else:
        print("  ECHEC environnement isole non cree")
    try:
        import shutil
        shutil.rmtree(cible, ignore_errors=True)
    except Exception:
        pass

    titre("2. Bibliotheques Python")
    for module in ("playwright", "openpyxl", "yaml", "pypdf", "docx"):
        try:
            __import__(module)
            print("  OK    %s" % module)
        except ImportError:
            print("  ABSENT %s" % module)

    titre("3. Moteur de pilotage du navigateur")
    print("  C'est le point decisif : Playwright utilise un petit programme (node)")
    print("  range dans les bibliotheques Python, donc dans votre profil.")
    moteur_ok, sortie = essayer(
        "demarrage du moteur",
        [sys.executable, "-c",
         "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print('MOTEUR OK'); p.stop()"],
    )

    titre("4. Navigateurs installes sur le poste")
    chemins = [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    trouve = False
    for chemin in chemins:
        reel = os.path.expandvars(chemin)
        if "%" not in reel and Path(reel).exists():
            print("  OK    %s" % reel)
            trouve = True
    if not trouve:
        print("  AUCUN navigateur trouve aux emplacements habituels")

    titre("CONCLUSION")
    if moteur_ok:
        print("  Le poste peut piloter un navigateur. Lancez :")
        print("      %s demo" % ("robot" if os.name == "nt" else "./robot.command"))
    else:
        print("  Le moteur de pilotage ne demarre pas sur ce poste.")
        if not venv_ok:
            print("  Cause tres probable : l'entreprise interdit d'executer un programme")
            print("  range dans votre profil utilisateur (erreur 1260).")
        print("  Copiez TOUT ce rapport et envoyez-le a Claude : une autre approche")
        print("  existe, qui pilote le Chrome deja installe sans programme supplementaire.")
    print()


if __name__ == "__main__":
    main()

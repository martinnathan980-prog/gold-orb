"""Exceptions d'autoweb. Les messages sont destinés à l'utilisateur (en français)."""


class ErreurAutoweb(Exception):
    """Erreur générale : le message explique quoi faire."""


class ErreurScenario(ErreurAutoweb):
    """Le scénario YAML est invalide (clé inconnue, étape mal formée...)."""


class ErreurGabarit(ErreurAutoweb):
    """Un gabarit {{colonne}} référence une colonne absente ou un filtre inconnu."""


class ErreurExcel(ErreurAutoweb):
    """Problème avec le fichier Excel (introuvable, verrouillé, feuille absente...)."""


class ErreurEtape(ErreurAutoweb):
    """Une étape a échoué pour la ligne en cours : la ligne passe en ERREUR."""


class LigneIgnoree(ErreurAutoweb):
    """Levée par l'étape « ignorer » : la ligne passe en IGNORE et on continue."""


class ArretDemande(ErreurAutoweb):
    """Levée par l'étape « arreter » : on arrête tout le traitement proprement."""


class NavigateurFerme(ErreurAutoweb):
    """Le navigateur a été fermé (par l'utilisateur ou un plantage) : on arrête."""

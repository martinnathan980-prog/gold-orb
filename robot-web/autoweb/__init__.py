"""autoweb — robot de saisie web piloté par un fichier Excel.

Principe : un fichier Excel liste les éléments à traiter (un par ligne), un
scénario YAML décrit les étapes à réaliser sur la page web pour chaque ligne,
et le robot exécute le tout en écrivant le résultat (Statut / Message /
Horodatage) dans le même Excel pour le suivi.
"""

__version__ = "0.1.0"

# Jalons du projet (reçus le 17/09/2026)

| Jalon | Date |
|---|---|
| Solde FWD | 15/12/2026 |
| Diffusion PH Base | 15/01/2027 |
| Diffusion PH Perso | 22/01/2027 |
| Diffusion TO Base | 05/02/2027 |
| Diffusion TO Perso | 26/02/2027 |

## Ce que cela implique pour le robot

- **Avant le 15/12/2026** : le robot doit être fiable sur l'outil principal
  (scénario validé sur quelques lignes, puis sur un lot complet) pour absorber
  le solde FWD sans saisie manuelle.
- **Janvier 2027 (PH Base puis PH Perso)** : deux vagues de diffusion à une
  semaine d'écart. Prévoir un scénario par type de diffusion si les écrans
  diffèrent, et un Excel de suivi par vague.
- **Février 2027 (TO Base puis TO Perso)** : même schéma, trois semaines d'écart.

Ordre de travail proposé :
1. connecter le robot à l'outil cible (voir README, sections 4 à 6) ;
2. construire l'Excel de suivi à partir des documents (`extraire`) ;
3. valider une vague à blanc (`simuler`, puis `lancer --limite 1`) ;
4. lancer les lots, relire la colonne Message, relancer avec `--reprendre-erreurs`.

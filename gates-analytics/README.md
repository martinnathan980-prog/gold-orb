# GATES Analytics

Tableau de bord de suivi des plans d'intégration électrique, construit sur
Google Apps Script + Google Sheets.

```
PROCEDURE.md      Le geste hebdomadaire, en deux étapes
import/           Script Python : archiver un export hors Google Sheets
Code.gs           Serveur : lecture de la feuille, historique, jalons
Index.html        Structure de la page
Styles.html       Feuille de style
Javascript.html   Logique client (filtres, tri, tableau, graphiques)
appsscript.json   Manifeste (fuseau, portées OAuth, déploiement web)
tests/run-tests.js Tests unitaires (node tests/run-tests.js)
```

## Installation

1. Ouvrir le classeur Google Sheets ▸ **Extensions ▸ Apps Script**.
2. Créer les fichiers `Code.gs`, `Index.html`, `Styles.html`, `Javascript.html`
   et y coller le contenu de ce dossier (les trois derniers sont des fichiers
   **HTML** dans l'éditeur Apps Script, même pour le CSS et le JS).
3. **Déployer ▸ Nouveau déploiement ▸ Application Web**, puis ouvrir l'URL `/exec`.
4. Recharger le classeur : le menu **GATES Analytics** apparaît.
5. Menu ▸ **Activer le suivi hebdomadaire automatique** pour lancer l'historique.

Avec [clasp](https://github.com/google/clasp) : `clasp push` depuis ce dossier.

## Configuration

Tout se règle dans l'objet `CONFIG` en haut de `Code.gs` :

| Clé | Rôle |
|---|---|
| `FEUILLE_DONNEES` | Onglet à lire. Vide = premier onglet visible non interne. |
| `FEUILLE_HISTORIQUE` | Onglet des instantanés (`Historique_FWD`). |
| `MOTS_CLES_ENTETE` | Mots-clés qui identifient la ligne d'en-têtes. |
| `AUTORISER_INTEGRATION_EXTERNE` | `true` pour embarquer la page dans Google Sites. |
| `FENETRE_RYTHME` | Nombre de semaines sur lesquelles se mesure le rythme (6 par défaut). |

## Fonctionnement

**Historique.** L'export GATES ne contient que l'état du jour : on ne sait pas
quand un plan est passé à 100 %. L'historique ne peut donc pas être reconstitué,
seulement **accumulé**. `enregistrerInstantaneHebdo()` écrit une ligne par semaine
ISO dans `Historique_FWD` — comptes globaux, comptes par ATA, et avancement plan
par plan sur les deux derniers relevés (pour le comparatif entre imports).
L'opération est idempotente : plusieurs imports la même semaine ne font qu'une
ligne, la dernière. Voir [`PROCEDURE.md`](PROCEDURE.md) pour le geste hebdomadaire.

**Classement de l'avancement.** `classerFWD()` applique d'abord une règle
numérique (`>= 100` terminé, `<= 0` vide), puis des mots-clés. La fonction est
dupliquée à l'identique dans `Code.gs` et `Javascript.html` — le serveur s'en sert
pour les instantanés, le client pour les KPI filtrés. **Toute modification doit
être reportée des deux côtés** ; un test vérifie que les deux versions concordent.

**Jalons.** Stockés dans les propriétés du document (`PropertiesService`), donc
partagés par tous les utilisateurs et conservés entre deux sessions.

## Tests

```bash
node tests/run-tests.js     # ou: npm test
```

Les tests chargent `Code.gs` et le `<script>` de `Javascript.html` dans un
contexte `vm` isolé, avec des stubs minimaux. Ils couvrent les semaines ISO,
le classement d'avancement, la détection des en-têtes, l'échappement HTML,
le tri, le réordonnancement des colonnes et l'agrégation des graphiques.

## Ce qui a changé par rapport à la version initiale

### Corrections

| # | Problème | Correction |
|---|---|---|
| 1 | `getDonneesPlans` calculait l'historique réel puis renvoyait `historiqueExemple`, un tableau codé en dur : **le graphique d'évolution affichait des chiffres inventés**. | L'historique réel est lu depuis `Historique_FWD`, dédoublonné et trié. Les données de démonstration sont derrière une option désactivée. |
| 2 | `getActiveSheet()` : le tableau de bord lisait l'onglet ouvert en dernier, y compris `Historique_FWD`. | Résolution déterministe de l'onglet (`CONFIG.FEUILLE_DONNEES`, sinon premier onglet visible non interne). |
| 3 | Les valeurs des cellules étaient injectées en HTML sans échappement (`<td>${valeur}</td>`, `onclick="cacherGroupe('${groupe}')"`). Un groupe nommé « Définition d'ensemble » cassait la page ; un contenu de cellule pouvait injecter du HTML. | Échappement systématique + gestion des clics par délégation avec `data-*`, plus aucun `onclick` construit par concaténation. |
| 4 | Trier ou masquer une colonne reconstruisait les en-têtes et **effaçait tous les filtres de colonne** en cours. | Les filtres vivent dans l'état et sont restaurés à chaque reconstruction. |
| 5 | Le glisser-déposer de colonnes calculait l'index cible avant de retirer la colonne source : décalage d'un cran vers la droite. | Fonction pure `reordonner()`, couverte par des tests. |
| 6 | Le graphique de dates gardait les 20 périodes les **plus fréquentes** avant de les trier : des mois disparaissaient de la courbe. | Tri chronologique d'abord, puis conservation des 24 dernières périodes. |
| 7 | `s.includes('100')` classait comme « terminé » toute cellule contenant la suite `100` : « 1001 pièces », « ECP-1004 », « 100 à revoir ». | Règle numérique explicite (`>= 100` / `<= 0`) évaluée avant les mots-clés. |
| 8 | Le tri numérique échouait sur « 75 % », « 1 234,5 » (virgule, espace insécable) et mélangeait les cellules vides. | `valeurNumerique()` tolérante + vides toujours en bas + `localeCompare` français. |
| 9 | Les lignes entièrement vides de la feuille étaient comptées dans le total, ce qui diluait le pourcentage d'avancement. | Filtrage des lignes vides côté serveur. |
| 10 | Les jalons n'existaient qu'en mémoire : perdus à chaque rechargement. | Persistance via `PropertiesService`, partagée entre utilisateurs. |
| 11 | Les lignes de `Historique_FWD` étaient renvoyées dans leur ordre d'insertion, et la semaine existante était cherchée par comparaison stricte (`===`) sur la valeur brute de la cellule : une semaine ressaisie ou reformatée créait un doublon affiché hors chronologie. | Lecture normalisée, dédoublonnée et triée ; `numeroSemaineISO()` testée sur les bascules d'année (2020-S53, 2025-S01). |
| 12 | Les deux jalons codés en dur (`2026-S30`, `2026-S36`) ne correspondaient qu'aux données de démonstration ; posés sur une semaine absente de l'axe, ils disparaissaient sans explication. | Jalons saisis et persistés par l'utilisateur, ceux qui sortent de la plage affichée sont ignorés explicitement. |
| 13 | `setXFrameOptionsMode(ALLOWALL)` autorisait l'intégration de la page dans n'importe quel site (clickjacking). | Protection par défaut, intégration externe derrière une option explicite. |
| 14 | Aucun `withFailureHandler` : en cas d'erreur serveur, la page restait bloquée sur le spinner. | Bandeau d'erreur, états vides et messages explicites. |
| 15 | La lecture du tableau de bord **écrivait** dans le classeur à chaque ouverture. | La lecture ne modifie plus rien ; l'écriture est déclenchée par le menu ou le déclencheur hebdomadaire. |

### Performances

- `ajusterHauteursEnTetes()` était appelé à **chaque événement de défilement**, créant
  un `setTimeout` par pixel parcouru sans rien changer au rendu. Il ne s'exécute plus
  qu'après un rendu ou un redimensionnement, via `requestAnimationFrame`.
- Chaque frappe dans un filtre relançait le filtrage, deux reconstructions de
  graphique (`destroy()` + `new Chart()`) et un rendu complet du tableau. Les saisies
  sont maintenant débattues (180 ms), le graphique d'évolution n'est plus touché par
  les filtres, et le graphique dynamique est mis à jour au lieu d'être recréé tant
  que son type ne change pas.
- `genererNomPropre()` appelait `getIdxFWDStrict()` pour **chaque colonne**, et cette
  fonction reparcourt elle-même les en-têtes jusqu'à trois fois : le coût était
  quadratique en nombre de colonnes à chaque reconstruction du tableau. L'index FWD
  est désormais calculé une seule fois, côté serveur.
- Le tableau se rendait d'un bloc. Il est désormais rendu par tranches de 200 lignes,
  avec chargement au défilement.

### Nouveautés

- KPI « Sans statut » et total, cohérents avec le classement serveur.
- Courbe du pourcentage d'avancement sur un second axe du graphique d'évolution.
- Export CSV de la vue filtrée (UTF-8 + `;`, lisible directement par Excel FR).
- Bouton « Réinitialiser » et compteur de filtres actifs.
- Disposition des colonnes (ordre + colonnes masquées) mémorisée par utilisateur.
- Toutes les colonnes sont proposées dans l'analyse, groupées par famille
  (l'ancienne liste blanche en cachait la plupart).
- Menu du classeur : instantané manuel, activation/désactivation du suivi hebdomadaire.
- Accessibilité : libellés, rôles ARIA, respect de `prefers-reduced-motion`,
  mise en page utilisable sur écran étroit.
- Intégrités SRI sur les CDN Bootstrap.

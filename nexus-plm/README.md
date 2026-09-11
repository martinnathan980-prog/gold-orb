# NEXUS PLM

Gestion de nomenclatures d'assemblages, sur Google Apps Script + Google Sheets.

- `ANALYSE.md` — analyse de la version d'origine (bugs, fragilités, décision d'architecture)
- `correctifs/` — lot 1 : correctifs ciblés des 6 bugs, à poser sur la version d'origine
- `src/` — **réécriture complète** (celle-ci)
- `test/` — 158 tests, exécutés sur les fichiers réellement livrés

```
npm test
```

## Structure

```
src/
  appsscript.json          manifeste (V8, portée du déploiement, scopes)
  Index.html               squelette — aucune logique

  server/
    Config.gs              feuilles, en-têtes, statuts, URL du catalogue
    Repository.gs          E/S Sheets : lecture, écriture par lot, clés, verrou, journal
    Api.gs                 SEULES fonctions exposées au client + validation
    Setup.gs               création de structure, jeu de démo, menu

  client/
    Styles.html            CSS, couleurs en variables
    Dom.html               esc(), formats, délégation d'événements
    Api.html               google.script.run -> Promise   <-- frontière unique
    Store.html             état + recherche indexée, zéro DOM
    Compare.html           scoring PUR, aucun HTML produit
    ViewGrid.html          tuiles, onglets, indicateurs
    ViewFiche.html         panneau latéral
    ViewCompare.html       rendu des équivalences
    Main.html              contrôleur : actions et démarrage
```

Deux règles portent l'essentiel :

1. **Aucune donnée n'entre dans une chaîne de code.** `esc()` systématique et
   `data-action` plutôt que `onclick="…('${valeur}')"`. Un PN contenant `"` ou
   `'` ne peut plus casser l'interface ni faire perdre une saisie.
2. **`google.script.run` n'existe que dans `client/Api.html`.** Le
   `withFailureHandler` est écrit une fois pour les 9 appels. Une migration
   future ne coûterait que ce fichier.

## Déploiement

```bash
npm install -g @google/clasp
clasp login
clasp clone <ID_DU_SCRIPT>     # ou clasp create --type sheets
clasp push
```

Apps Script accepte le `/` dans les noms de fichiers : `client/Dom.html` apparaît
comme un dossier dans l'éditeur, et `include('client/Dom')` le résout.

Ensuite, **une fois** :

1. Paramètres du projet → Propriétés du script → ajouter `URL_CATALOGUE`
   (l'URL du classeur catalogue). Elle n'est plus en dur dans le source.
2. Recharger le Sheet → menu **NEXUS PLM** → *Créer / compléter la structure*.
3. Déployer en application web.

Le manifeste fixe `access: "DOMAIN"` : l'application n'est accessible qu'aux
comptes du domaine. À adapter si besoin, mais pas à élargir sans raison.

## Ce qui a changé

### Les 6 bugs confirmés

| | Correction |
|---|---|
| Catalogue ajoutant le mauvais composant | l'index réel est conservé, plus celui de la liste filtrée |
| Aucun `withFailureHandler` | un seul passe-plat `appelerServeur`, bandeau d'erreur, arrêt des indicateurs |
| « Invalidé » compté comme validé | liste fermée + égalité stricte, et validation à la saisie |
| Export CSV cassé | `Blob` au lieu de `data:`+`encodeURI`, guillemets doublés, BOM UTF-8, séparateur `;` |
| Compteur d'onglet incohérent | un seul filtrage dont tout dérive |
| « undefined » affiché | helper `txt()` |

### Les fragilités structurelles

- **Échappement** — `esc()` partout, délégation d'événements, plus un seul
  `onclick` en ligne. Un test vérifie qu'un PN piégé (`332"P<script>…'A`)
  traverse l'affichage et revient intact.
- **Identité** — le numéro de ligne ne quitte plus le serveur. Le client envoie
  `PN Global` ou `ID_Ligne`, le serveur résout au moment de l'écriture. Deux
  suppressions rapprochées ne peuvent plus viser la mauvaise ligne.
- **Concurrence** — `LockService` sur toutes les mutations.
- **Comparateurs** — calcul séparé du rendu, pondérations dans `POIDS`. Les deux
  bugs de scoring sont corrigés : un critère non mesurable sort du dénominateur
  **et** est affiché comme tel. Un taux de **couverture** dit sur quelle part des
  critères le score a été calculé.
- **Recherche** — index sur les valeurs seules. `image`, `commentaires`,
  `rowindex` ne ramènent plus tout. Recherche multi-mots, avec anti-rebond.
- **Performances** — écriture par lot (1 appel par ligne au lieu d'un par
  colonne), retours différentiels au lieu de relire les deux feuilles à chaque
  frappe, catalogue en `CacheService`.
- **Sécurité** — `XFrameOptionsMode.DEFAULT`, URL du catalogue en Script
  Property, validation serveur, journal `9_JOURNAL` (qui, quoi, quand).
- **Divers** — `.max-width-xl` enfin définie, panneau latéral responsive,
  `initialiserBaseDeDonnees` scindée en une version sûre et une version
  destructive à confirmation écrite, conversion Drive dédupliquée (elle était
  copiée 3 fois), annulation d'édition possible.

### Fonctions

Les 10 fonctions serveur et les ~34 fonctions client d'origine sont toutes
conservées. Renommages principaux :

| Origine | Devient |
|---|---|
| `getToutLeContenu` | inchangé |
| `saveLigne(feuille, rowIndex, modifs)` | `saveBoite(pn, modifs)` / `saveNomenclature(id, modifs)` |
| `deleteLigne(feuille, rowIndex)` | `deleteNomenclature(id)` |
| `deleteBoiteEntiere(pn, rowIndex)` | `deleteBoiteEntiere(pn)` |
| `addBoiteLibre` / `addSousEnsembleLibre` | `addBoite` / `addSousEnsemble` |
| `initialiserBaseDeDonnees` | `creerStructureSiAbsente` + `reinitialiserAvecDemo` |
| `filtrerInterface` | `calculerVue` + `rendreInterface` |
| `comparerBoite` / `comparerSousEnsemble` | `equivalencesBoite` / `equivalencesSousEnsemble` |
| les `toggleEdit*` | actions `editer-*` / `annuler-*` / `sauver-*` |

Ajouts : annulation d'édition, filtre par composants affiché et retirable,
taux de couverture des scores, journal des modifications.

## Réserve

Le code d'origine m'est parvenu via un PDF : l'extraction a perdu les emojis
(icônes ✅/❌ des comparateurs) et introduit des retours à la ligne. Les icônes
sont remplacées par `✓ ≈ ✗ –`. **Avant de pousser, comparer avec les fichiers
authentiques** — notamment si des colonnes ont été ajoutées au Sheet depuis.

Deux points à valider en conditions réelles, non testables hors navigateur :

1. **Téléchargement CSV** — l'interface tourne dans une iframe sandboxée ;
   selon le navigateur un téléchargement déclenché par script peut être bloqué.
   C'était déjà le cas avant. Repli : `window.open(url)` ou génération du fichier
   dans Drive côté serveur.
2. **Séparateur `;`** — adapté à Excel FR. À passer à `,` dans `Dom.html`
   (`CSV_SEPARATEUR`) si les fichiers alimentent un outil attendant la virgule.

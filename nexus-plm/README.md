# NEXUS PLM

Gestion de nomenclatures d'assemblages, sur Google Apps Script + Google Sheets.

- `ANALYSE.md` — analyse de la version d'origine (bugs, fragilités, décision d'architecture)
- `correctifs/` — lot 1 : correctifs ciblés des 6 bugs, à poser sur la version d'origine
- `src/` — **réécriture complète** (celle-ci)
- `test/` — 326 tests, exécutés sur les fichiers réellement livrés

```
npm test                 # 222 tests : logique client + serveur
npm run demo             # construit build/demo.html
npm run test:navigateur  # 104 tests dans un vrai Chromium
```

## Démonstration navigable

`build/build-demo.js` assemble une version qui tourne hors de Google. Elle
résout les `<?!= include() ?>`, inline Bootstrap (la politique de sécurité des
Artifacts interdit les feuilles de style externes) et insère
`demo/FauxServeur.html`, qui fournit un `google.script.run` factice adossé à
des données en mémoire.

**Aucun fichier de `src/` n'est modifié pour la démo.** C'est la démonstration
concrète du découpage : `Api.html` appelle `google.script.run` exactement comme
en production, seul le transport change. C'est aussi ce qui permet de tester
l'interface dans un navigateur sans Google (`test/test-navigateur.js`).

La démo ajoute un interrupteur « simuler une panne serveur » : il sert à voir
le comportement d'échec, qui était totalement muet dans la version d'origine.
L'aperçu du CSV remplace le téléchargement, bloqué par le bac à sable.

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
    Styles.html            design system : jetons, thèmes clair et sombre
    Types.html             REGISTRE DES TYPES : champs + critères par type
    Dom.html               esc(), formats, délégation d'événements
    Api.html               google.script.run -> Promise   <-- frontière unique
    Store.html             état, recherche indexée, pondérations, journal
    Compare.html           scoring PUR, piloté par le registre, aucun HTML
    ViewGrid.html          cartes, onglets, filtres par type, indicateurs
    ViewFiche.html         panneau latéral, champs selon le type
    ViewCompare.html       rendu des équivalences
    Reglages.html          pondérations réglables, aperçu en direct
    Annulation.html        rattrapage d'une suppression
    Main.html              contrôleur : actions et démarrage
```

## Types de sous-ensembles

`client/Types.html` est la pièce maîtresse : un seul endroit décrit, pour chaque
type, **les champs qu'il porte** et **les critères qui servent à l'équivalence**.
L'affichage de la fiche, le moteur de scoring et l'écran de réglages en sont
tous générés. Ajouter un type ou un critère ne demande de toucher à aucun autre
fichier.

| Type | Champs propres | Critères d'équivalence |
|---|---|---|
| **Structure boîte** | montage, nombre de pas, longueur, largeur, masse, HL, DAL | montage, pas, dimensions, masse, DAL, HL, qualifications, composants |
| **Harnais** | PN, référence — **ni cotes, ni masse, ni qualification** | référence, composants |
| **Plaquette éclairante** | PN, **mots-clés** — ni numéro, ni cotes, ni qualification | mots-clés, composants |
| **Autre** | référence, masse | référence, masse, qualifications, composants |

Une pièce n'est comparée qu'aux pièces du **même type** : confronter une
plaquette et un harnais n'a pas de sens, ils n'ont pas les mêmes critères.

Les mots-clés sont comparés en recouvrement de vocabulaire, insensible aux
accents et à la casse, doublons écartés : « mission SAR » et « Mission Sar »
sont le même terme.

## Pondération

Chaque critère porte un poids, réglé **depuis la comparaison elle-même** : le
panneau s'ouvre sur la portée de ce qu'on regarde (harnais, plaquette, structure
ou boîte) et nulle part ailleurs. On ne règle pas des critères dans un écran de
paramètres détaché du travail en cours.

Trois partis pris :

- On affiche la **part** de chaque critère (sa fraction du total), pas son poids
  brut : c'est la part qui détermine le score, un poids de 30 ne veut rien dire seul.
- L'**aperçu se recalcule à chaque mouvement de curseur**, sur des données
  réelles. Le panneau est sans voile : ouvert par-dessus une comparaison, on voit
  le classement se recomposer derrière.
- Un poids mis à **0** sort le critère du calcul, et la comparaison l'annonce
  (« ignoré par vos réglages ») au lieu de le passer sous silence.

Quatre réglages rapides sont fournis (Équilibré, Priorité composants, Priorité
géométrie, Priorité qualification). Les réglages sont mémorisés sur le poste.

## Ne rien perdre

- **Annulation** : une suppression reste rattrapable deux minutes. L'élément est
  recréé — avec un identifiant neuf, ce que l'interface annonce plutôt que de
  laisser croire à un retour en arrière exact.
- Côté serveur, la feuille `9_JOURNAL` enregistre qui a modifié quoi et quand.

## Duplication

- Une **boîte** se duplique depuis sa carte, dans la liste — pas depuis sa fiche.
- Un **sous-ensemble** se duplique depuis la fiche, avec tous les champs de son
  type recopiés.

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

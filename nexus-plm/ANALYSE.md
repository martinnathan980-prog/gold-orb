# NEXUS PLM — analyse du code existant

Analyse du code fourni le 11/09/2026 (Google Apps Script : `Code.gs` + `Index.html`,
~850 lignes réelles). Objectif : comprendre, lister ce qui va / ce qui ne va pas,
et trancher la question « on reste sur Apps Script ou on passe sur autre chose ».

---

## 1. Ce que fait l'application

Un outil de **gestion de nomenclatures d'équipements** (boîtes / assemblages électriques),
adossé à Google Sheets.

**Modèle de données** — deux onglets, relation 1-N via la colonne `PN Global` :

| Onglet | Rôle | Colonnes |
|---|---|---|
| `1_BOITES` | l'assemblage | Fonction, PN Global, DS/VCI Associé, Porteur, Statut, Niveau de qualification, Image, Commentaires |
| `2_NOMENCLATURE` | les sous-ensembles | ID_Ligne, PN Global, Type, PN du type, Montage, Nombre de pas, Dim Long/Larg, Masse, HL, DAL, 3× Qualification, Composant STD, Image, Commentaires |

Plus un **catalogue de composants** externe, lu en lecture seule dans un 3ᵉ classeur.

**Fonctions couvertes** (14 côté serveur, ~30 côté client) :

- Initialisation / réinitialisation de la base avec jeu de démo
- Lecture globale, CRUD boîte, CRUD sous-ensemble, duplication d'assemblage
- Grille de tuiles + onglets par Fonction + KPI
- Recherche globale texte
- Recherche multi-critères par composants embarqués
- Fiche détaillée en panneau latéral, édition inline champ par champ
- Champs multi-valeurs à puces (Porteur, 3 Qualifications, Composants STD)
- Rattachement de composants depuis le catalogue
- Export CSV de la nomenclature
- **Deux moteurs de comparaison** : équivalences entre boîtes, et entre sous-ensembles de même Type

Le cœur métier, et ce qui fait la valeur de l'outil, ce sont les deux moteurs
d'équivalences. Le reste est du CRUD.

---

## 2. Ce qui va bien

Il faut le dire, parce que ça conditionne la suite : **l'application est bonne dans
ses choix de fond.**

1. **Le modèle de données est juste.** Deux tables, une clé de jointure, pas de
   dénormalisation sauvage. C'est le bon découpage métier, il tiendra la montée en charge.

2. **Le rendu est piloté par les en-têtes**, pas par des colonnes en dur :
   `dataGlobale.headersBoites.forEach(...)`. Ajouter une colonne dans le Sheet la fait
   apparaître dans la fiche sans toucher au code. C'est un très bon réflexe, rare.

3. **L'édition « silencieuse »** (`saveBoite(idx, true)` + restauration de l'état d'édition
   après re-rendu) : l'intention UX est la bonne — on reste dans le flux, pas de
   rechargement visible à chaque puce ajoutée.

4. **Les moteurs de comparaison sont une vraie idée métier.** Score pondéré, raisons
   explicitées ligne par ligne, tri décroissant, distinction commun / manquant / en trop.
   C'est ce qui fait que l'outil sert à quelque chose. C'est aussi la partie à
   protéger en priorité lors du refactor.

5. **Le design tient la route** et est cohérent (tokens de couleur réguliers, hiérarchie
   typographique, badges de statut lisibles).

6. **Les miniatures Drive** : convertir un lien Drive en `thumbnail?id=...` est le bon
   contournement, bien vu.

**Conclusion : il n'y a rien à jeter.** Le problème n'est pas quoi faire, c'est comment
c'est écrit. Toutes les fonctions restent.

---

## 3. Ce qui ne va pas

### 3.1 Bugs confirmés (reproduits)

Classés par gravité. Les six premiers sont vérifiés par exécution, pas déduits à la lecture.

---

**B1 — Le catalogue ajoute le mauvais composant dès qu'on filtre.** *(critique — corruption de données)*

```js
const res = catalogueComposants.filter(...).slice(0, 30);
res.map((c, i) => `... onclick="ajouterCatalogue(${i})" ...`)   // i = index dans res (filtré)

function ajouterCatalogue(idx) {
  let cat = catalogueComposants[idx];                            // mais lu dans la liste COMPLÈTE
```

L'index affiché appartient à la liste filtrée, il est relu dans la liste non filtrée.

Reproduction : catalogue `[Bouton poussoir, Switch, Relais, Diode]`, on tape « diode »,
un seul résultat s'affiche (`Diode`, index 0), on clique → **`Bouton poussoir` est écrit
dans la nomenclature.**

Le bug ne se voit pas tant qu'on ne filtre pas (index filtré = index réel). Dès qu'on
cherche — c'est-à-dire l'usage normal — chaque ajout est faux. Et comme l'écriture est
immédiate et silencieuse, les nomenclatures se remplissent de composants erronés sans
que personne ne s'en aperçoive.

*Correctif : passer une clé stable (la norme / réf), pas un index de tableau.*

---

**B2 — Aucun `withFailureHandler` dans toute l'application.** *(critique — perte de données silencieuse)*

Les 10 appels `google.script.run` déclarent un `withSuccessHandler`, jamais de
`withFailureHandler`. Si le serveur lève (quota, droits, ligne supprimée entre-temps,
coupure réseau), **il ne se passe rien** : le spinner tourne indéfiniment, aucun message.

L'utilisateur voit une roue qui tourne, se dit que c'est lent, ferme le panneau.
**Sa saisie est perdue et il croit qu'elle est enregistrée.** Sur un outil qui suit des
statuts de qualification, c'est le défaut le plus coûteux du lot.

Même chose côté retour applicatif : `getToutLeContenu` peut renvoyer `{erreur: ...}`,
et le client fait `if(reponse.erreur) return;` — sortie muette, spinner bloqué.

---

**B3 — « Invalidé » est compté comme validé.** *(logique métier)*

```js
String(b['Statut']).toLowerCase().includes('valid')
```

| Statut | Résultat |
|---|---|
| `Validé` | compté validé ✔ |
| `Invalidé` | **compté validé** ✘ |
| `Non validé` | **compté validé** ✘ |

Le test par sous-chaîne attrape les négations. Conséquence : badge vert et KPI faux
sur des boîtes explicitement invalidées.

*Correctif : liste de statuts fermée + comparaison exacte, pas `includes`.*

---

**B4 — Le CSV exporté est cassé de trois façons.** *(export inexploitable)*

```js
let csvContent = "data:text/csv;charset=utf-8,Type,...";
csvContent += `"${nom['Type']||''}",...`;
link.setAttribute("href", encodeURI(csvContent));
```

- `encodeURI` **n'encode pas `#`**. Un `#` dans un commentaire (fréquent : « repère #3 »)
  tronque l'URL de données : tout ce qui suit est perdu.
- Les `"` contenus dans les champs ne sont pas doublés → colonnes décalées.
- **Pas de BOM UTF-8** → Excel en français affiche `Boîte` au lieu de `Boîte`.
- Accessoirement, les téléchargements par `data:` URI sont bloqués dans l'iframe
  sandboxée d'Apps Script sur les navigateurs récents.

*Correctif : `Blob` + `URL.createObjectURL`, BOM `﻿`, échappement CSV correct.*

---

**B5 — Le compteur de l'onglet « Toutes » ment pendant une recherche.**

```js
boitesAFitrer.forEach(boite => { if(!boxesForcees && !JSON.stringify(boite)...) return; ... })
let tabHtml = `... Toutes <span class="tab-count">${boitesAFitrer.length}</span>`  // non filtré
```

Les compteurs par fonction utilisent la liste filtrée, celui de « Toutes » la liste
brute. Sur 3 boîtes (2 APU + 1 NAV), recherche `332p2` → « Toutes (3) » affiché,
2 cartes visibles, somme des onglets = 2. Les compteurs se contredisent à l'écran.

---

**B6 — « undefined » s'affiche sur les cartes.**

```js
${String(boite['Porteur']).replace(/\n/g, ', ')||'-'}
```

`String(undefined)` vaut `"undefined"`, qui est *truthy* → le `||'-'` ne se déclenche
jamais. Une boîte sans Porteur affiche littéralement **`undefined`**. Les autres champs
de la même carte font correctement `${boite['DS/VCI Associé']||'-'}` — c'est une
incohérence locale.

---

### 3.2 Fragilité structurelle

**F1 — Les guillemets et apostrophes cassent l'interface.** *(le plus pénible au quotidien)*

Tout le rendu est de la concaténation de chaînes injectée en `innerHTML`, avec les
valeurs du Sheet insérées brutes :

```js
`<input type="text" ... value="${val}">`
`<button onclick="comparerBoite('${boite['PN Global']}')">`
```

- Une valeur contenant `"` ferme l'attribut : `value="Entraxe 5" nominal"` → la valeur
  devient `Entraxe 5`, et **le reste est silencieusement perdu à la sauvegarde**.
- Une apostrophe dans un `onclick` casse le handler : bouton mort. En français,
  « Boîte d'alimentation » suffit.
- Le `c.replace(/'/g, "\\'")` utilisé par endroits est un demi-échappement : il ne
  traite ni `"`, ni `<`, ni `&`.

Ce n'est pas d'abord un sujet de sécurité, c'est un **sujet de correction** : les données
réelles (dimensions en pouces, apostrophes françaises) déclenchent le bug tous les jours.
Accessoirement, oui, c'est aussi une injection HTML : une cellule contenant
`<img src=x onerror=...>` s'exécute.

*Correctif — et c'est celui qui élimine la classe entière de bugs :
fonction `esc()` obligatoire + **délégation d'événements** via `data-action` / `data-id`
au lieu des `onclick="...('${valeur}')"` inline. Plus aucune donnée n'atterrit dans du code.*

---

**F2 — L'identité des lignes est leur position.** *(risque de suppression de la mauvaise ligne)*

`_rowIndex` est le numéro de ligne dans la feuille. Toute suppression décale toutes les
lignes en dessous. Le client se resynchronise après chaque opération, ce qui masque le
problème en usage lent — mais deux suppressions rapprochées, ou deux personnes en
parallèle, et la seconde opération s'applique à **la mauvaise ligne**.

Aggravant : il n'y a **aucun `LockService`**, donc aucune sérialisation des écritures
concurrentes. Et la colonne `ID_Ligne`, qui serait la vraie clé, est écrite mais
**jamais utilisée** — deux notions d'identité coexistent, dont une morte.

*Correctif : `ID_Ligne` devient la clé réelle, le serveur résout clé → ligne à chaque
écriture, et `LockService` encadre les mutations.*

---

**F3 — Les index de tableau servent d'identifiants côté client.**

`currentBoiteIndex` est une position dans `dataGlobale.boites`. Après un rafraîchissement,
le code la retrouve… en relisant le titre affiché dans le DOM :

```js
const currPn = document.getElementById('slideOverTitle').innerText;
currentBoiteIndex = dataGlobale.boites.findIndex(b => b['PN Global'] === currPn);
```

Le DOM sert de source de vérité. Si `findIndex` renvoie `-1` (boîte renommée ou
supprimée), `dataGlobale.boites[-1]` vaut `undefined` et le rendu plante.

---

**F4 — Les deux moteurs de comparaison mélangent calcul et affichage.**

~200 lignes où chaque critère calcule *et* produit son HTML dans la même expression :

```js
if(source['Fonction']) { tot+=15; if(cible['Fonction'] === source['Fonction']) { score+=15;
  raisonsHTML.push(`<div class="analyze-row">...`); } else { raisonsHTML.push(`...`); } }
```

Conséquences : les pondérations (15, 10, 25, 50 / 10, 10, 10, 10, 5, 5, 15, 35) sont
noyées dans le balisage et impossibles à ajuster sans relire du HTML ; la logique n'est
pas testable ; et les deux moteurs dupliquent la même structure.

**Et ça cache deux vrais bugs de scoring :**

- **Dénominateur gonflé.** `tot += 50` dès que `srcStd.length > 0 || cibStd.length > 0`,
  mais les points ne sont ajoutés que `if(srcStd.length > 0)`. Source sans composant STD
  + cible qui en a → **0/50**. Deux boîtes par ailleurs identiques plafonnent à un score
  bas. Même schéma avec `35` dans le comparateur de sous-ensembles.
- **Pénalité silencieuse.** Masse : `if(!isNaN(sM)) { totalPts+=10; if(!isNaN(cM)) {...} }` —
  si la cible n'a pas de masse renseignée, on ajoute 10 au dénominateur, on n'accorde
  aucun point, **et on n'affiche aucune ligne d'explication**. L'utilisateur voit un score
  bas sans raison visible. Idem sur les dimensions.

*Correctif : extraire des fonctions de score pures (données → `{score, max, raisons[]}`),
pondérations dans un objet de configuration, rendu séparé. C'est là que le refactor
rapporte le plus : le métier devient lisible, ajustable et testable.*

---

**F5 — La recherche par `JSON.stringify` produit des faux positifs.**

```js
JSON.stringify(boite).toLowerCase().includes(query)
```

On cherche dans la sérialisation JSON — donc aussi dans **les noms de colonnes** et dans
`_rowIndex` :

| Requête | Résultat |
|---|---|
| `image` | matche **toutes** les boîtes (c'est un nom de colonne) |
| `commentaires` | matche **toutes** les boîtes |
| `rowindex` | matche **toutes** les boîtes |
| `2` | matche presque tout (numéros de ligne) |

En prime : `JSON.stringify` échappe les retours à la ligne en `\n` littéral, donc un
terme à cheval sur deux lignes ne matche jamais ; et l'opération est refaite **deux fois
par rendu**, à chaque frappe, sans anti-rebond.

---

**F6 — Une écriture = relecture intégrale des deux feuilles.**

Chaque mutation se termine par `return getToutLeContenu()`, qui relit `1_BOITES` **et**
`2_NOMENCLATURE` en entier. Ajouter une puce « Porteur » déclenche donc :
sauvegarde → relecture complète → re-rendu complet de la page.

Et `saveLigne` écrit **cellule par cellule dans une boucle** :

```js
for (const [key, value] of Object.entries(modifications)) {
  if (colIndex !== -1) sheet.getRange(rowIndex, colIndex + 1).setValue(value);
}
```

soit un aller-retour vers le service Sheets par colonne, là où un seul `setValues` sur
la plage de la ligne suffirait. Sur 17 colonnes : 17 appels au lieu d'1.

Ça passe sur 10 boîtes. Sur quelques centaines d'assemblages et quelques milliers de
lignes, ça devient inutilisable, et on approchera de la limite d'exécution d'Apps Script.

*À noter : `google.script.run` ne garantit pas l'ordre de retour. Deux ajouts de puces
rapprochés partent en parallèle, chacun relisant l'état courant du champ caché →
dernier arrivé écrase. Une puce peut disparaître.*

---

**F7 — Duplication.**

- La conversion Drive → miniature est copiée **3 fois**, chaque fois précédée du même
  commentaire `*** TRANSFORMATION MINIATURE INTEGRÉE DIRECTEMENT ICI ***`.
- Le bloc « En commun / Absents / Présents en plus » est dupliqué entre les deux
  comparateurs (styles inline compris).
- La gestion des champs multi-valeurs existe en deux exemplaires quasi identiques
  (`ajouterMultiBoite` / `ajouterMultiNom`, `supprimerMultiBoite` / `supprimerMultiNom`).

---

**F8 — Divers**

- `toggleEditBoite` / `toggleEditNom` ne basculent que dans **un** sens : pas d'annulation
  possible, il faut sauvegarder pour sortir du mode édition. Le nom est trompeur.
- `activeTab` peut devenir orphelin : si l'onglet actif n'existe plus après une recherche,
  sa pastille disparaît mais il reste actif → « Aucun assemblage dans cette catégorie »
  alors que des résultats existent, sans moyen évident de revenir.
- `dupliquerBoite` code en dur les indices de colonnes (`newRowB[1]`, `newRowB[4]`) alors
  que tout le reste du code travaille par en-têtes. Et n'empêche pas les PN en double.
- `dupliquerBoite` appelle `appendRow` dans une boucle : un aller-retour par ligne.
- KPI : le libellé dit « Boîtes Validées », la valeur affichée est un **pourcentage**.
- `let idx = dataGlobale.boites.indexOf(boite)` dans un `.map()` → O(n²) au rendu.
- `filtrerCatalogue` coupe à `.slice(0, 30)` sans l'indiquer : l'utilisateur conclut que
  le composant n'existe pas.
- `.max-width-xl` est utilisée deux fois dans le HTML mais **n'est définie nulle part**
  (et n'existe pas dans Bootstrap 5) : les conteneurs sont pleine largeur, sans doute
  contre l'intention.
- `.offcanvas { width: 650px !important; }` déborde sur mobile malgré le `viewport`.
- `getCatalogueComposants` relit le classeur externe entier à **chaque ouverture de page**,
  sans `CacheService`.
- `initialiserBaseDeDonnees` fait `sheet.clear()` puis réinjecte le jeu de démo,
  **sans aucune confirmation** : un lancement accidentel depuis l'éditeur efface tout.
  Elle applique aussi `applyRowBanding` sur une plage déjà bandée au 2ᵉ lancement → erreur.
- `doGet` utilise `createTemplateFromFile` (donc le moteur de template) mais aucun
  scriptlet ni fonction `include()` n'existe : on paie le template sans l'utiliser.
  C'est pourtant exactement le mécanisme qui permet de découper `Index.html`.
- 8 variables globales mutables (`dataGlobale`, `currentBoiteIndex`, `activeTab`,
  `isEditingBoite`, `isEditingNom`, …) implicitement couplées.
- `saveNom(r)` / `deleteNom(r)` : le paramètre de la callback `(r) => ...` **masque** le
  `r` externe. Le code est correct (l'argument est évalué avant), mais c'est un piège
  posé pour la prochaine relecture.

### 3.3 Sécurité et gouvernance

- **`setXFrameOptionsMode(ALLOWALL)`** autorise l'intégration de l'application dans
  *n'importe quel* site tiers (clickjacking). À passer en `DEFAULT` sauf besoin explicite
  d'embarquer dans Google Sites.
- **Aucun modèle d'autorisation.** Pas de `Session.getActiveUser()`, pas de rôles. Selon
  le déploiement, toute personne disposant de l'URL a un accès en écriture complet.
- **Aucune traçabilité.** Pour un outil qui suit des statuts de qualification, « qui a
  modifié quoi et quand » est normalement indispensable. Rien n'est journalisé.
- **Aucune validation serveur.** `addBoiteLibre` accepte n'importe quel PN, doublons compris.
- L'URL du catalogue est en dur dans le source : à déplacer en Script Property.

---

## 4. La question : on reste sur Apps Script, ou on passe « en HTML » ?

**Il faut d'abord lever une ambiguïté : l'interface est *déjà* du HTML.** `Index.html`
fait 600 lignes de HTML/CSS/JS standard. Apps Script n'est pas une alternative au HTML —
c'est ce qui **sert** ce HTML et lui donne accès au Sheet. Les deux ne s'opposent pas.

La vraie question est donc : **qu'est-ce qui stocke et sert les données ?**

| | Apps Script + Sheets (actuel) | HTML statique seul | Vraie app web (API + base) |
|---|---|---|---|
| Persistance partagée | ✅ le Sheet | ❌ **aucune** | ✅ |
| Authentification | ✅ Google, gratuite | ❌ | À construire |
| Hébergement | ✅ inclus | À héberger | À héberger |
| Coût | 0 | 0 | Serveur + BDD |
| Images Drive | ✅ natif | ⚠️ | À refaire |
| Le Sheet comme back-office | ✅ | ❌ | ❌ |
| Montée en charge | ⚠️ quelques milliers de lignes | — | ✅ |
| Multi-utilisateur concurrent | ❌ | ❌ | ✅ |
| Traçabilité / rôles | ❌ | ❌ | ✅ |

**Le HTML statique seul est exclu** : sans backend, il n'y a plus de persistance ni de
partage. On perdrait la raison d'être de l'outil.

### Recommandation : rester sur Apps Script, mais découpler l'interface du backend

Rester, parce que le rapport valeur/effort y est imbattable dans le contexte : l'auth,
le partage, Drive et l'hébergement sont déjà là et gratuits ; et le Sheet qui sert de
back-office est **une fonctionnalité**, pas un défaut — corriger une valeur à la main
sans passer par l'appli, c'est précieux pour une petite équipe.

Mais avec une condition, et c'est le point d'architecture important :

> **`google.script.run` ne doit plus apparaître que dans un seul fichier.**

Aujourd'hui il est appelé directement à 10 endroits, au milieu de fonctions d'interface.
On le met derrière un module `Api` qui renvoie des `Promise`. Ce qu'on gagne :

1. Le `withFailureHandler` manquant est écrit **une fois** (B2 réglé partout).
2. `await` remplace les callbacks imbriquées — la logique redevient linéaire.
3. On peut développer et tester l'interface **en local**, avec un faux `Api`.
4. **Si un jour on migre**, on réécrit ce seul fichier. Pas les 600 autres lignes.

Autrement dit : on reste sur Apps Script **aujourd'hui**, et on structure le code pour que
partir demain coûte un fichier au lieu d'une réécriture. On ne paie pas maintenant une
migration dont on n'a pas encore besoin.

**Quand faudra-t-il vraiment partir ?** Quand l'un de ces seuils tombe :
plusieurs milliers de lignes de nomenclature · plusieurs personnes qui éditent en même
temps · une exigence formelle de traçabilité ou de rôles. Tant qu'on est en deçà,
Apps Script fait le travail.

### Deuxième recommandation : sortir le code de l'éditeur Apps Script

Passer en **`clasp`** (l'outil officiel) + ce dépôt git. L'éditeur en ligne n'a ni
historique exploitable, ni branches, ni revue, ni diff. Sur un outil qui commence à
porter de la donnée métier, c'est le changement qui rapporte le plus vite — et c'est
lui qui rend le refactor qui suit sûr, parce qu'on peut revenir en arrière.

---

## 5. Structure cible proposée

Apps Script accepte le `/` dans les noms de fichiers et les affiche en arborescence ;
avec `clasp`, les dossiers locaux correspondent directement.

```
Code.gs                 doGet() + include() — rien d'autre

server/
  Config.gs             noms de feuilles, en-têtes, pondérations, Script Properties
  Repository.gs         E/S feuilles : lecture, écriture par LOT, résolution ID→ligne
  Boites.gs             opérations métier sur les assemblages
  Nomenclature.gs       opérations métier sur les sous-ensembles
  Catalogue.gs          catalogue externe + CacheService
  Api.gs                SEULES fonctions exposées au client : validation + LockService

client/
  Index.html            squelette seul
  Styles.html           CSS, couleurs en variables CSS
  Api.html              google.script.run -> Promise   <-- LA frontière unique
  Dom.html              esc(), helpers, délégation d'événements
  Store.html            état + index de recherche, aucun DOM
  Compare.html          scoring PUR : données -> {score, max, raisons[]}
  ViewGrid.html         cartes, onglets, KPI
  ViewFiche.html        panneau latéral
  ViewCompare.html      rendu des résultats de comparaison
```

Deux règles qui portent l'essentiel du gain :

1. **`Compare.html` ne produit pas de HTML.** Il renvoie des données. `ViewCompare.html`
   les affiche. Les pondérations vivent dans `Config`, ajustables sans toucher au balisage.
2. **Aucune donnée n'entre dans une chaîne de code.** `esc()` systématique, et
   `data-action` + délégation à la place des `onclick` inline. F1 disparaît par construction.

### Ordre d'exécution proposé

| # | Lot | Contenu | Risque |
|---|---|---|---|
| 1 | Filet de sécurité | `clasp` + dépôt git, source authentique commitée | nul |
| 2 | Bugs critiques | B1, B2, B3, B4, B5, B6 — correctifs ciblés, sans restructurer | faible |
| 3 | Socle | `Config`, `Repository` (écriture par lot), `Api` (Promise + erreurs) | moyen |
| 4 | Rendu | `esc()` + délégation d'événements → F1 éliminé | moyen |
| 5 | Métier | extraction du scoring pur + correction des 2 bugs de pondération | moyen |
| 6 | Perf | retours différentiels, index de recherche, anti-rebond, cache catalogue | faible |
| 7 | Robustesse | `ID_Ligne` comme clé, `LockService`, journal des modifications | moyen |

Le lot 2 est indépendant : il peut partir en production tout de suite, avant toute
restructuration. **Les 14 fonctions serveur et les ~30 fonctions client sont toutes
conservées** — à périmètre fonctionnel strictement identique.

---

## 6. Réserve sur la source

Ce document est établi à partir du code extrait du PDF. L'extraction a introduit des
retours à la ligne artificiels et **a perdu les emojis** (icônes ✅/❌/⚠️ des comparateurs,
icône de la barre de recherche). Avant de commencer le refactor, il faut repartir des
fichiers authentiques `Code.gs` et `Index.html`.

L'extraction brute est conservée dans `baseline/source-extrait-du-pdf.txt` à titre de
référence. L'en-tête d'e-mail, la signature et la mention de confidentialité n'ont
volontairement pas été repris.

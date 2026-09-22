# ETII Hub

Portail métier d'un service d'ingénierie : communication interne,
comptes-rendus de réunion, organigramme, base de connaissances et
**recherche documentaire**.

Reprise complète d'une implémentation Google Sites + Google Apps Script.

## Pourquoi cette réécriture

L'ancienne version était un site Google Sites dans lequel étaient
encastrées des applications Apps Script affichées en `iframe`. Les
symptômes :

- **Faux responsive.** Chaque page était une maquette figée à 1600×900
  que l'on rétrécissait avec `transform: scale()` recalculé à chaque
  redimensionnement. Sur un écran étroit, tout devenait minuscule au lieu
  de se réorganiser.
- **Défilement confisqué.** `overflow: hidden !important` sur `html, body`
  et masquage de toutes les barres de défilement, y compris pour les
  personnes qui naviguent au clavier.
- **Poids inutile.** jQuery, Bootstrap, Fuse.js et une bibliothèque PDF
  chargés depuis des CDN, soit plusieurs centaines de kilo-octets avant
  le premier contenu utile.
- **Animations permanentes.** Une animation de particules en boucle
  infinie et un effet machine à écrire posant un minuteur par caractère.
- **Données fragiles.** Lecture de cellules par indices en dur
  (`getRange(13, 3, …)`), qui cassait au moindre ajout de ligne.

La version actuelle est un **site statique sans aucune dépendance**.

## Démarrer

Le site n'a ni build, ni installation, ni dépendance.

```bash
cd etii-hub
python3 -m http.server 8000
```

Puis ouvrir <http://localhost:8000>.

> Un serveur local est nécessaire : les pages chargent leurs données via
> `fetch`, que les navigateurs bloquent sur `file://`. N'importe quel
> serveur de fichiers statiques convient, et n'importe quel hébergeur
> statique convient pour la mise en ligne.

## Les pages

| Page | Rôle |
|---|---|
| `index.html` | Tableau de bord : Communication center (kiosque + éditeur), À venir (les prochains rendez-vous), Porteurs, Suivi OTQ / OTD |
| `etiia.html`, `etiie.html`, `etiii.html` | L'espace d'un pôle : sa communication, le pôle en un coup d'œil (repères, organigramme, référents, par porteur), ses documents récents, sa FAQ (voir ci-dessous) |
| `reunions.html` | Les comptes-rendus de réunion, par périmètre |
| `organigramme.html` | Équipes, rôles, compétences ; hors de la barre du site, on y arrive depuis un pôle |
| `faq.html` | Base de connaissances |
| `docsearch.html` | **Recherche documentaire — le cœur du site** |

### L'en-tête de page et le sommaire

Sur le tableau de bord comme sur un espace de pôle, le titre de la page et
son sommaire se posent sur la bande (`--fond-bande`, pleine largeur, un
filet en bas) : l'entrée de la page se distingue du papier de la première
section, puis les bandes alternent une section sur deux. Le sommaire (la
« petite barre » `.sous-nav`) reste collé sous la barre du site et son lien
courant suit la lecture (`suivreSommaire()` de `assets/js/ui.js`, partagé
par `index.js` et `pole.js` : est courante la dernière section dont le haut
a passé la ligne de lecture, au tiers haut de la fenêtre). Sur le tableau
de bord : Communication · À venir · Porteurs · Suivi OTQ / OTD.

### Les espaces de pôle

Les trois pages de pôle sont une seule page (`assets/js/pole.js`),
paramétrée par `<body data-pole="ETIIA|ETIIE|ETIII">`. Le sommaire
collant (Communication, En un coup d'œil, Documents, FAQ) suit la
lecture. Aucune section n'invente rien : chacune est calculée depuis les
fichiers de `assets/data/` pour ce pôle.

| Section | Source | Ce qu'elle montre |
|---|---|---|
| Communication | `communications.json` (`pole`) | Le kiosque du pôle, identique à celui du tableau de bord : chaque pôle y a au moins une annonce riche en blocs (image d'un de ses porteurs avec son crédit, chiffres clés, courbe, pastilles, encadré) — des données d'exemple |
| Le pôle en un coup d'œil | `organigramme.json`, `flotte.json`, `documents.json` | Quatre repères cliquables (personnes, squads, référents, documents en vigueur), un champ « Qui sait faire… ? », puis trois volets côte à côte qui défilent chacun dans leur cadre : **Organigramme** (le responsable, puis chaque squad et ses membres, le lead d'abord), **Référents** (pour chaque compétence, qui solliciter en premier) et **Par porteur** (pour chaque porteur suivi par le pôle — `flotte.json` → `poles`, puis les codes que ses membres déclarent —, les personnes dont le champ `porteur` ou `perimetre` est ce code ; un porteur sans personne dit « Contact à renseigner »). Une personne tient en une ligne : son nom, vers sa fiche, et son rôle |
| Documents du pôle | `documents.json` (`pole`, `porteur`) | Les huit documents en vigueur les plus récents du pôle, puis « Tous les documents du pôle (N) » vers la recherche filtrée |
| Questions fréquentes | `faq.json` (`pole`) | Les questions du pôle puis celles du service, et « Interroger un expert » |

Un pôle n'a pas de section Réunions : ce qui vaut d'être dit se publie en
communication. Les comptes-rendus restent lisibles dans `reunions.html`.
Il n'a pas non plus de galerie de porteurs : tout le pôle travaille sur les
porteurs du service, qui sont sur le tableau de bord.

## Architecture

```
etii-hub/
  *.html                  Une page = un point d'entrée, un module ES
  assets/
    css/
      polices.css         IBM Plex Sans, IBM Plex Mono, Newsreader embarquées
      tokens.css          Jetons : couleurs, typo, espacements, ombres
      base.css            Reset, typographie, mise en page, en-tête
      components.css      Cartes, boutons, champs, onglets, modales
      skin.css            La matière : registre « document technique »
    js/
      data.js             Chargement JSON, cache, états d'erreur
      search.js           Moteur de recherche
      ui.js               Helpers DOM sûrs, modale, toast, thème
      <page>.js           Un module par page
    data/
      *.json              Données (fictives)
  SPEC.md                 Spécification de référence
```

Trois règles structurent le code :

1. **Aucune valeur brute dans le CSS.** Couleurs, espacements, rayons,
   ombres et durées viennent tous de `tokens.css`. Changer l'identité
   visuelle, c'est modifier un seul fichier.
2. **Aucun `innerHTML` avec de la donnée.** Tout passe par les
   constructeurs d'éléments de `ui.js`, qui insèrent le texte en
   `textContent`. L'injection HTML est structurellement impossible.
3. **Aucun gestionnaire d'événement en attribut HTML.** Pas de
   `onclick="…"` construit par concaténation — c'est ce qui cassait
   l'ancienne version dès qu'un nom contenait une apostrophe.

## Le moteur de recherche

`assets/js/search.js` est un module autonome, sans dépendance, partagé par
la recherche documentaire, la FAQ et les réunions.

- Index inversé construit une fois au chargement, plus un index de
  préfixes et un index de bigrammes.
- Insensible à la casse **et aux accents** : « intégration » et
  « integration » sont équivalents.
- Tolérance aux fautes de frappe par distance d'édition bornée, qui ne
  prime jamais sur une correspondance exacte.
- Classement par pertinence pondérée, avec départage **stable** :
  score, puis date de mise à jour, puis titre.
- `surligner()` ne renvoie jamais de HTML, seulement des segments de
  texte balisés — l'appelant construit les nœuds.

## Données

Les fichiers de `assets/data/` sont **entièrement fictifs** et servent de
démonstration. Aucune donnée réelle n'y figure : les personnes sont
identifiées par `Personne 01`, `Personne 02`…, les liens pointent vers le
domaine réservé `example.invalid`, et seuls des programmes publics d'Airbus
Helicopters sont cités (les fiches des porteurs s'appuient sur des sources
publiques, citées dans chaque fiche).

Pour brancher de vraies données, remplacez les fichiers JSON en respectant
leur forme, ou saisissez-les dans le site en mode édition (ci-dessous).

### Modifier le contenu dans le site

Tout ce que le site affiche se modifie depuis le site lui-même, sans
toucher aux fichiers : un bouton **Modifier** dans la barre allume le mode
édition (`assets/js/edition.js`) et fait apparaître partout « Ajouter »,
« Modifier » et « Supprimer » — communications et alertes, rendez-vous,
porteurs, personnes et squads, documents, questions, comptes-rendus.
« Terminer » l'éteint ; les lecteurs ne voient aucune commande.

Les fichiers de `assets/data/` restent la base. Une modification est posée
par-dessus au chargement (`assets/js/modifications.js`, appelé par
`chargerDonnees()`), si bien que toutes les pages voient les mêmes données.
Elle est rangée par `assets/js/magasin.js` :

- **sur le lien publié** (claude.ai), dans la base de la page, partagée par
  tous ses lecteurs — une collection `modifications_<jeu>` par fichier ;
  seuls ceux qui ont le droit de modifier la page voient le bouton ;
- **partout ailleurs** (fichier ouvert en local, serveur de test), dans ce
  navigateur seulement, et le bandeau du mode édition le dit.

Un élément supprimé du fichier de base est masqué, jamais effacé du
fichier ; une personne dont la squad est retirée attend dans « À affecter ».

### Qui met à jour quoi

Après toute modification d'un fichier de `assets/data/`, lancer
`node tests/audit.mjs` ; pour les communications aussi
`node tests/communications.test.mjs`, pour `documents.json` aussi
`node tests/search.test.mjs`.

| Fichier | Ce qu'il alimente | Ce qui le vérifie |
|---|---|---|
| `communications.json` | Le Communication center du tableau de bord et la communication de chaque espace de pôle | `node tests/audit.mjs`, `node tests/communications.test.mjs` |
| `documents.json` | La recherche documentaire, et les documents portés affichés sur la fiche d'une personne | `node tests/audit.mjs`, `node tests/search.test.mjs` |
| `faq.json` | La page FAQ et la FAQ de chaque espace de pôle | `node tests/audit.mjs` |
| `flotte.json` | La galerie Porteurs du tableau de bord, les fiches d'appareil et les crédits photo | `node tests/audit.mjs` |
| `indicateurs.json` | Les repères chiffrés des espaces de pôle | `node tests/audit.mjs` |
| `organigramme.json` | L'organigramme, le trombinoscope, les compétences, les équipes et référents des pôles | `node tests/audit.mjs` |
| `reunions.json` | Les comptes-rendus de réunion | `node tests/audit.mjs` |
| `otq-exemple.csv` | Le Suivi OTQ / OTD tant que `SOURCE.url` d'`assets/js/otq.js` est vide | `node tests/audit.mjs` |

L'audit vérifie aussi la cohérence *entre* ces fichiers : qu'un document est
bien porté par quelqu'un qui existe dans l'organigramme, que ses valeurs de
filtre sont déclarées dans les facettes, qu'aucune référence n'est en double.
Il distingue l'erreur, qui fait perdre une donnée en silence, de
l'avertissement, qui signale une dérive sans rien casser.

### Photos des personnes

Chaque personne de `organigramme.json` accepte un champ `photo`, facultatif :
ajoutez `"photo": "assets/img/personnes/p03.jpg"` sur une personne (un
chemin sous `assets/` ou une URL `https`) et sa photo remplace son portrait
partout — arbre d'un pôle, organigramme, trombinoscope, fiche, onglet
Équipe d'un porteur. Sans `photo`, `assets/js/portraits.js` dessine un
portrait illustré (plat, sobre, fond teinté du pôle), choisi de façon
déterministe depuis l'identifiant : ce sont les « photos test » du site,
jamais des visages réels. Les initiales restent le texte accessible du
portrait. Un carré d'environ 256 px suffit ; l'image est cadrée sur le
haut.

Exception : la base des porteurs (`flotte.json`) est constituée depuis des
sources **publiques** (Wikipédia, site public d'Airbus Helicopters, EASA) et
chaque valeur porte sa confiance et sa source. Les fiches sont marquées
« relecture non effectuée » tant qu'elles n'ont pas été relues en
contradictoire par le service.

### Photos des porteurs

Les photos de `assets/img/porteurs/` viennent de Wikimedia Commons, sous
licence libre (CC BY, CC BY-SA). La condition de réutilisation est de citer
l'auteur et la licence : c'est ce que fait la ligne de crédit sous chaque
photo, alimentée par le champ `credit` de `flotte.json` (`auteur`, `licence`,
`fichier`, `page`, `note`). Pour remplacer une photo par une photo interne,
mettez le fichier dans le dossier, changez `photo` et videz `credit` (ou
renseignez-y la source interne). Les vignettes sont servies à 960 px de
large ; inutile d'en mettre de plus grandes.

`credit` porte un dernier champ, `vu` : **une phrase qui décrit ce qu'on voit
sur l'image**, écrite en l'ouvrant. `node tests/audit.mjs` refuse un appareil
qui a une `photo` sans ce champ. Ce n'est pas une formalité : une récupération
automatique depuis Commons a déjà apparié le H225M sur son surnom et rapporté
la photo d'un caracal — le félin. Un nom de fichier ne permet pas de trancher
(une photo authentique a le droit de ne porter qu'un nom de salon), une phrase
descriptive ne s'écrit pas sans avoir regardé, et elle se relit dans un diff.

## Accessibilité

- Navigation clavier complète sur chaque page, y compris la mise en page des
  blocs de l'éditeur de communication : ↑ ↓ déplacent un bloc, ← → règlent sa
  largeur, chaque geste porte son libellé ARIA (`assets/js/editeur.js`).
- Anneau de focus visible sur tout élément interactif.
- Barres de défilement natives conservées.
- Thème clair et sombre, suivant le système par défaut, avec choix manuel
  mémorisé.
- Toute animation est neutralisée sous `prefers-reduced-motion: reduce`.
- Cibles tactiles d'au moins 44 px.

## Version autonome, en un seul fichier

```bash
node tools/build-artifact.mjs   # -> dist/etii-hub.html
```

Le fichier produit contient le site entier : les six pages, les feuilles de
style, les modules et les données. Il n'a **aucune dépendance et aucun
chemin relatif**, donc il s'ouvre par double-clic — sans serveur — et se
publie tel quel sur n'importe quel hébergeur.

Le site multi-pages de la racine reste la source de vérité ; le script
assemble, il ne modifie rien.

Trois détails que l'assemblage doit gérer, et qui sont testés :

- les pages contiennent des `</script>`, qui fermeraient la balise
  englobante si la sérialisation ne les échappait pas ;
- deux modules utilisent `await` au niveau racine, licite dans un module ES
  mais pas dans une fonction ordinaire ;
- deux modules utilisent `import()` dynamique, résolu vers le registre
  interne plutôt que vers le réseau.

Le script analyse chaque script assemblé avec `node --check` avant de
sceller le fichier : une erreur de syntaxe échoue à la construction, pas
dans le navigateur.

## Documents de mise en œuvre

- `docs/COMMUNICATIONS-GOOGLE-SHEETS.md` — la publication : le bouton
  « Ajouter une communication » du site (éditeur en blocs, aperçu vivant)
  envoie vers une feuille Google que le site lit à l'ouverture
  (`assets/js/communications.js`, `SOURCE.url` / `SOURCE.publication`).

| Fichier | Ce qu'il explique |
|---|---|
| `docs/OTQ-GOOGLE-SHEETS.md` | Alimenter le suivi OTQ / OTD chaque nuit depuis un Google Sheet |
| `docs/ASSISTANT-IA.md` | Brancher un assistant documentaire (Gemini) : chemins, coûts, interlocuteurs, précautions |
| `docs/RECHERCHE-A-L-ECHELLE.md` | Ce qui fait la qualité d'une recherche sur des milliers de documents |
| `SPEC.md` | Le cahier des charges de la réécriture ; les en-têtes de modules y renvoient par numéro de section |

Les scripts Apps Script correspondants sont dans `tools/apps-script/`.

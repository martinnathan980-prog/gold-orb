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
| `index.html` | Dispatcher : accès aux trois pôles et à la recherche |
| `etiia.html`, `etiie.html`, `etiii.html` | L'espace d'un pôle : sa communication, ses repères, ses référents, ses porteurs, son organigramme, sa FAQ (voir ci-dessous) |
| `reunions.html` | Les comptes-rendus de réunion, par périmètre |
| `admin.html` | Publier une communication : formulaire, aperçu vivant, ligne à coller dans la feuille Google (`docs/COMMUNICATIONS-GOOGLE-SHEETS.md`) |
| `organigramme.html` | Équipes, rôles, réorganisation |
| `faq.html` | Base de connaissances |
| `docsearch.html` | **Recherche documentaire — le cœur du site** |

### Les espaces de pôle

Les trois pages de pôle sont une seule page (`assets/js/pole.js`),
paramétrée par `<body data-pole="ETIIA|ETIIE|ETIII">`. Une sous-navigation
collante (Communication, Référents, Porteurs, Organigramme, FAQ) suit la
lecture. Aucune section n'invente rien : chacune est calculée depuis les
fichiers de `assets/data/` pour ce pôle.

| Section | Source | Ce qu'elle montre |
|---|---|---|
| Communication | `communications.json` (`pole`) | Le kiosque du pôle, identique à celui du tableau de bord |
| Le pôle en un coup d'œil | `organigramme.json`, `flotte.json`, `documents.json` | Cinq repères cliquables : personnes, squads, référents, porteurs, documents portés par ses membres (`documents.json` → `porteur` ∈ noms des membres) |
| Référents & expertises | `organigramme.json` (`competences`) | Une carte par compétence du pôle : ses référents (niveau `referent`, liens vers `organigramme.html#pole=CODE&personne=ID`), puis le nombre de confirmés et de pratiquants ; un champ filtre les compétences et les noms, un compteur dit « N compétences · M référents » |
| Porteurs du pôle | `flotte.json` (`poles`) | Les appareils dont `poles` cite le pôle, en cartes photo (la carte de la galerie du tableau de bord) vers `index.html#porteur=CODE` |
| Organigramme | `organigramme.json` | L'arbre d'équipe du pôle : responsable, squads repliables |
| Questions fréquentes | `faq.json` (`pole`) | Les questions du pôle puis celles du service, et la demande aux experts |

Un pôle n'a pas de section Réunions : ce qui vaut d'être dit se publie en
communication. Les comptes-rendus restent lisibles dans `reunions.html`.

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
identifiées par `Personne 01` … `Personne 65`, les liens pointent vers le
domaine réservé `example.invalid`, et seuls les programmes publics H160 et
H175 sont cités.

Pour brancher de vraies données, remplacez les fichiers JSON en respectant
leur forme. Rien d'autre n'est à modifier.

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

## Accessibilité

- Navigation clavier complète sur chaque page, y compris le glisser-déposer
  de l'organigramme, qui dispose d'un équivalent clavier.
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

- `docs/COMMUNICATIONS-GOOGLE-SHEETS.md` — la partie administrateur : une
  feuille Google, une ligne par communication, lue par le site
  (`assets/js/communications.js`, `SOURCE.url`).

| Fichier | Ce qu'il explique |
|---|---|
| `docs/OTQ-GOOGLE-SHEETS.md` | Alimenter le suivi OTQ / OTD chaque nuit depuis un Google Sheet |
| `docs/ASSISTANT-IA.md` | Brancher un assistant documentaire (Gemini) : chemins, coûts, interlocuteurs, précautions |
| `docs/RECHERCHE-A-L-ECHELLE.md` | Ce qui fait la qualité d'une recherche sur des milliers de documents |

Les scripts Apps Script correspondants sont dans `tools/apps-script/`.

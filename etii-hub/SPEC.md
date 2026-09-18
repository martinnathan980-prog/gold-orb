# ETII Hub — Spécification de reconstruction

Portail métier d'un service d'ingénierie. Remplace une implémentation
Google Sites + Google Apps Script jugée trop lourde et non optimisée.

## 0. Règles de confidentialité (NON NÉGOCIABLES)

Ce dépôt est **public**. Aucun fichier ne doit jamais contenir :

- de nom ou prénom de personne réelle → utiliser `Personne 01` … `Personne 65`
- d'adresse e-mail réelle ou de domaine d'entreprise (`@airbus.com`, etc.)
  → utiliser `contact@example.invalid` ou un `mailto:` vide
- d'URL interne (`sites.google.com/airbus.com/...`, `*.sharepoint.com`,
  intranet, PLM, serveurs) → utiliser `#` ou `https://example.invalid/...`
- d'identifiant Google Drive / Sheets / Docs (`1moBQcC...`, `?id=...`)
- de nom de programme non public. **Seuls autorisés : H160, H175**
  (produits Airbus Helicopters communiqués publiquement).
- de jalon, procédure, norme ou référence documentaire interne

Identité visuelle Airbus (bleu, typographie) : autorisée, c'est public.
Les acronymes d'équipe ETIIA / ETIIE / ETIII sont conservés comme
libellés structurels neutres, sans lien vers quoi que ce soit d'interne.

Toute donnée est **fictive et illustrative**.

## 1. Objectifs

1. **Alléger.** Zéro dépendance externe : pas de jQuery, pas de Bootstrap,
   pas de Fuse.js, pas de html2pdf, aucun CDN. HTML/CSS/JS natifs.
2. **Optimiser.** Chargement instantané, pas d'animation permanente qui
   brûle le CPU, pas de reflow inutile.
3. **Embellir.** Design system unique et cohérent sur les 6 pages.
4. **Corriger.** Les bugs fonctionnels de l'ancienne version (§6).
5. **Rendre accessible.** Clavier, lecteurs d'écran, contrastes, motion.

## 1bis. Structure du service (accord d'équipe — ne se discute pas)

Le hub n'est pas plat. Il suit la hiérarchie réelle du service :

    ETII  ............... le service, niveau le plus haut
     ├── ETIIA .......... Squelette & ADN — logique et règles d'architecture
     ├── ETIIE .......... Système nerveux — schémas électriques, communication
     ├── ETIII .......... Structure & harnais — intégration physique, routage
     └── Recherche documentaire, transverse aux trois pôles

- Le **tableau de bord ETII** porte la communication de service et les
  indicateurs : OTQ, OTD, écarts ouverts, charge.
- Chaque **pôle** a son espace, avec sa communication, son organigramme,
  ses réunions et sa FAQ.
- Dans l'ancien site, les trois pages de pôle étaient des duplicatas. Ici,
  un **gabarit unique paramétré** (`pole.js` + `data-pole`) : une correction
  se fait une fois, pas trois.
- Les quatre pages transverses (communication, réunions, organigramme, FAQ)
  sont **partagées et filtrées** par le pôle actif, porté dans le hash :
  `communication.html#pole=ETIIA`. La valeur `ETII` signifie « tout le
  service ». Toute valeur inconnue retombe sur `ETII` sans erreur.

### Couleurs de pôle

Palette catégorielle **validée** (bande de clarté, plancher de chroma,
séparation en vision daltonienne et en vision normale, contraste sur la
surface), avec des pas propres à chaque thème :

| Pôle  | Sombre    | Clair     | Jeton              |
|-------|-----------|-----------|--------------------|
| ETIIA | `#8b5cf6` | `#7c3aed` | `--pole-etiia`     |
| ETIIE | `#0ea5c9` | `#0e8aa8` | `--pole-etiie`     |
| ETIII | `#c47a0c` | `#b45309` | `--pole-etiii`     |

Délibérément distinctes de l'accent émeraude de l'interface : une même
teinte ne doit pas désigner à la fois « action » et « pôle ».

Le pôle n'est **jamais** signalé par la couleur seule : toujours une
pastille étiquetée ou un libellé.

### Règles de visualisation des indicateurs

- Jamais deux axes verticaux. Deux mesures d'échelles différentes : deux
  graphiques, ou une base commune.
- La couleur suit l'entité, jamais son rang. Masquer une série ne repeint
  pas les autres.
- Les couleurs de statut sont réservées à l'état, jamais série n°4.
- Légende dès deux séries ; étiquetage direct jusqu'à quatre séries.
- Une vue tabulaire accompagne toujours un graphique.

## 2. Ce qu'il faut supprimer de l'ancienne implémentation

Ces patterns sont la cause de la lourdeur. Ils sont **interdits** dans la
nouvelle version :

| Pattern legacy | Problème | Remplacement |
|---|---|---|
| `.scalable-canvas` + `transform: scale()` recalculé au resize (`lockHeightResize`, `smartScale`) | Faux responsive : une maquette figée à 1600×900 qu'on rétrécit. Texte illisible sur mobile, flou, pas de reflow réel. | Vrai responsive : CSS Grid/Flex, `clamp()`, media queries |
| `::-webkit-scrollbar { display: none !important }` + `scrollbar-width: none` sur `*` | Rend la page inutilisable au clavier/sans trackpad. Anti-accessibilité. | Scrollbars visibles, stylées discrètement |
| `overflow: hidden !important` sur `html, body` | Empêche tout scroll natif | Scroll normal |
| Machine à écrire qui tape du HTML caractère par caractère (`typeWriter`) en parsant `<` et `>` à la main | ~1 timer par caractère, injection HTML, illisible | Animation CSS d'apparition, ou rien |
| `canvas` 100 particules en `requestAnimationFrame` infini | CPU/batterie en continu | Supprimé (ou statique + `prefers-reduced-motion`) |
| `innerHTML +=` avec données non échappées | XSS, reflow quadratique | `textContent` + `<template>` + `DocumentFragment` |
| jQuery + Bootstrap + Fuse.js + html2pdf en CDN | ~300 ko avant le premier octet utile | 0 dépendance |
| `Code.gs` dupliqué (doublons `onOpen`, `doGet`, `publierCommunication`) | Collision silencieuse de noms | Modules ES, un rôle par fichier |
| Données lues par index de colonne/ligne en dur (`getRange(13, 3, ...)`) | Casse au moindre ajout de ligne | JSON avec schéma nommé |

## 3. Architecture cible

Site statique. Aucune étape de build. Ouvrable par double-clic ou
servable par n'importe quel serveur de fichiers.

    etii-hub/
      index.html              Tableau de bord ETII (indicateurs, OTQ)
      etiia.html              Espace du pôle ETIIA  ─┐
      etiie.html              Espace du pôle ETIIE   ├─ même gabarit
      etiii.html              Espace du pôle ETIII  ─┘  (pole.js)
      communication.html      Communication Center
      reunions.html           Comptes-rendus + points à venir
      organigramme.html       Équipes et rôles
      faq.html                Base de connaissances
      docsearch.html          Recherche documentaire  <-- LE CŒUR
      assets/
        css/
          polices.css         Polices embarquées (Plex Sans, Plex Mono, Newsreader)
          tokens.css          Variables : couleurs, espacements, typo, ombres
          base.css            Reset, typographie, primitives, utilitaires
          components.css      Cartes, boutons, champs, badges, modales
          skin.css            Matière : papier, filets, mono, marine
        js/
          data.js             Chargement JSON + cache + erreurs
          search.js           Moteur de recherche (§5)
          ui.js               Helpers DOM sûrs, modale, toast, focus trap
          indicateurs.js      Graphiques : tuiles, lignes, barres
          pole.js             Gabarit partagé des trois espaces
          <page>.js           Un module par page
        data/
          communications.json
          reunions.json
          organigramme.json
          faq.json
          documents.json      Corpus du moteur de recherche
          indicateurs.json    OTQ, OTD, écarts, charge — 12 mois
      SPEC.md
      README.md

Chaque page : un seul `<script type="module">`. Pas de global partagé.

### Contrat de données

Le JSON est la source de vérité. `data.js` expose
`loadData(nom)` → `Promise<objet>`, avec cache mémoire, timeout, et un
état d'erreur affichable. Toute page doit rester utilisable (état vide
explicite) si son JSON manque ou est invalide.

## 4. Les six pages

### 4.1 `index.html` — Dispatcher
Trois cartes (ETIIA / ETIIE / ETIII) : titre, sous-titre métaphorique,
description, lien. Plus un accès proéminent à la recherche documentaire.
Garder l'effet de relief au survol mais en CSS, léger, désactivé sous
`prefers-reduced-motion`. Navigation clavier complète.

### 4.2 `communication.html` — Communication Center
Liste chronologique d'annonces + panneau de détail.
Chaque annonce : date, statut (`info` | `urgent` | `succes`), catégorie,
titre, résumé, corps.
Le corps est un tableau de lignes typées — **le format legacy à base de
préfixes `!`, `V `, `->` est remplacé par des types explicites** :
`{ "type": "alerte" | "valide" | "titre" | "puce" | "vide", "texte": "..." }`.
Bandeau d'alertes défilant : conserver l'idée, mais en CSS pur, en pause
au survol et au focus, et masqué sous `prefers-reduced-motion`.

### 4.3 `reunions.html` — Réunions
**Deux onglets** : « Comptes-rendus » et « Prochains points ».
Chaque entrée : titre, date, lieu, objectif/synthèse, liste de sujets
(titre + notes), **liste d'actions**, et pour les CR **liste de décisions**.
Recherche dans la liste. Export : impression via CSS `@media print`
(pas de bibliothèque PDF).

### 4.4 `organigramme.html` — Organigramme
Direction + N squads. Chaque squad : un leader, N membres.
Membre : identifiant, libellé (`Personne NN`), poste, périmètre, avatar.
**Avatars générés localement** (initiales + couleur dérivée de l'identifiant,
en SVG inline) — aucun appel réseau, pas de service tiers.
Réorganisation par glisser-déposer conservée, **avec un équivalent clavier
obligatoire** (menu « Déplacer vers… » sur chaque carte). Les changements
sont locaux (mémoire + `localStorage`), avec un bouton de réinitialisation.
Recherche/filtre qui met en retrait les non-correspondances.
Zoom et panoramique conservés, au clavier également.

### 4.5 `faq.html` — Base de connaissances
Liste de questions + réponse affichée. Recherche avec classement par
pertinence (§5). Si aucune réponse ne convient : formulaire « poser une
question », qui **enregistre en local et affiche la question soumise** —
pas d'envoi réseau, pas d'adresse e-mail en dur.

### 4.6 `docsearch.html` — Recherche documentaire — **LE CŒUR**

C'est la page qui compte le plus. Elle doit être excellente.

Document : `{ id, titre, reference, type, metier[], porteur, perimetre,
lien, description, motsCles[], maj }`.

Exigences :
- **Recherche instantanée** dès la frappe, sans latence perceptible sur
  plusieurs milliers de documents. Debounce court, index pré-calculé.
- **Classement par pertinence** explicite et justifiable (§5).
- **Tolérance aux fautes de frappe** (distance d'édition bornée).
- **Insensible à la casse et aux accents.**
- **Surlignage** des termes trouvés dans les résultats.
- **Facettes combinables** : type, métier, porteur, périmètre. Chaque
  facette affiche le nombre de résultats correspondants et se met à jour
  en fonction des autres filtres actifs.
- **Navigation 100 % clavier** : `/` pour focaliser, `↑`/`↓` pour parcourir,
  `Entrée` pour ouvrir, `Échap` pour effacer.
- **URL partageable** : l'état (requête + facettes) est reflété dans le
  hash de l'URL et restauré au chargement.
- **États explicites** : chargement, vide, aucun résultat (avec
  suggestion « vouliez-vous dire… » et proposition d'ajouter le document).
- **Accès rapides** par type depuis l'accueil de la page.
- Copier le lien d'un document en un clic, avec retour visuel.

## 5. Moteur de recherche (`search.js`)

Module autonome, sans dépendance, testable, réutilisé par `docsearch`,
`faq` et `reunions`.

Indexation (une fois au chargement) :
1. Normalisation : minuscules, suppression des diacritiques (NFD), 
   ponctuation → espaces.
2. Découpage en termes, et génération de préfixes pour la recherche
   au fil de la frappe.
3. Index inversé `terme → [ids]`, plus un index de bigrammes de caractères
   pour la tolérance aux fautes.

Score d'un document pour une requête, somme pondérée sur chaque terme :
- correspondance exacte d'un terme du titre : poids fort
- correspondance par préfixe du titre : poids moyen-fort
- correspondance exacte hors titre (référence, mots-clés, métier) : moyen
- correspondance dans la description : faible
- correspondance approximative (Levenshtein ≤ 1 pour 4-7 caractères,
  ≤ 2 au-delà) : très faible, et jamais seule si une exacte existe
- bonus si **tous** les termes de la requête sont trouvés
- bonus si la requête correspond au début du titre

Le score doit être **stable et déterministe**, et les égalités départagées
par un critère explicite (date de mise à jour, puis titre) — jamais par
l'ordre d'insertion.

## 6. Bugs de l'ancienne version à corriger

1. `Code.gs` existait en deux exemplaires : `onOpen`, `doGet` et
   `publierCommunication` déclarés deux fois, le dernier écrasant
   silencieusement le premier → sous-menus perdus.
2. `ouvrirFormFutur` référençait un fichier `form_reunion_point_avenir`
   absent du projet → plantage du bouton.
3. Le formulaire de compte-rendu n'envoyait jamais `synthese`, `actions`
   ni `decisions` ; la fonction de sauvegarde les lisait pourtant, et
   l'affichage cherchait des marqueurs `⚡`/`✅` qui n'existaient jamais.
   → Fonctionnalité morte. **Doit marcher de bout en bout.**
4. La page Réunions ne rendait que l'onglet « comptes-rendus » : les
   prochains points étaient chargés côté serveur puis jamais affichés.
   → **Les deux onglets doivent exister.**
5. Les fonctions `init*` appelaient `clear()` sans sauvegarde possible.
   → Toute action destructrice doit être annulable ou confirmée
   explicitement.
6. Noms de squad avec apostrophe ou guillemet : sélecteurs CSS et
   attributs `onclick` construits par concaténation → cassés.
   → Aucun gestionnaire d'événement construit par chaîne de caractères.

## 7. Design system

Palette (identité Airbus, valeurs publiques) :
- Bleu principal `#00205B`, bleu profond `#001233`
- Cyan d'accent `#00A0D2`
- Ambre d'accent `#FFB100`
- Statuts : info `#0284C7`, succès `#16A34A`, alerte `#EA580C`,
  critique `#DC2626`
- Neutres : une échelle de gris de 50 à 900

Règles :
- Tous les tokens dans `:root` de `tokens.css`. **Aucune valeur de couleur
  en dur ailleurs.**
- **Thème sombre** via `@media (prefers-color-scheme: dark)`, plus un
  sélecteur manuel persistant.
- Typographie système, échelle fluide en `clamp()`.
- Rayons, ombres, durées : tokens également.
- Focus visible sur **tout** élément interactif.
- Toute animation encadrée par `@media (prefers-reduced-motion: reduce)`.
- Cibles tactiles ≥ 44 px.
- Contraste AA minimum sur texte et composants.

## 8. Qualité exigée

- HTML valide, landmarks sémantiques, un seul `<h1>` par page.
- Aucun `innerHTML` avec de la donnée : `textContent` ou `<template>`.
- Aucun gestionnaire d'événement en attribut HTML (`onclick="..."`).
- Aucune dépendance réseau : le site doit fonctionner hors ligne.
- Chaque page utilisable au clavier seul, de bout en bout.
- Code commenté en français, cohérent avec le reste du projet.

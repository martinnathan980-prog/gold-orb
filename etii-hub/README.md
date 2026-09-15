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
| `communication.html` | Annonces du service, par ordre chronologique |
| `reunions.html` | Comptes-rendus **et** prochains points planifiés |
| `organigramme.html` | Équipes, rôles, réorganisation |
| `faq.html` | Base de connaissances |
| `docsearch.html` | **Recherche documentaire — le cœur du site** |

## Architecture

```
etii-hub/
  *.html                  Une page = un point d'entrée, un module ES
  assets/
    css/
      tokens.css          Jetons : couleurs, typo, espacements, ombres
      base.css            Reset, typographie, mise en page, en-tête
      components.css      Cartes, boutons, champs, onglets, modales
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

## Accessibilité

- Navigation clavier complète sur chaque page, y compris le glisser-déposer
  de l'organigramme, qui dispose d'un équivalent clavier.
- Anneau de focus visible sur tout élément interactif.
- Barres de défilement natives conservées.
- Thème clair et sombre, suivant le système par défaut, avec choix manuel
  mémorisé.
- Toute animation est neutralisée sous `prefers-reduced-motion: reduce`.
- Cibles tactiles d'au moins 44 px.

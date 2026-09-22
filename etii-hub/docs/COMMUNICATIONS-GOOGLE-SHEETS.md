# Communications — publier depuis le site, stocker dans une feuille Google

Tout se joue dans le site : le bouton **« Ajouter une communication »**
du Communication Center ouvre l'éditeur — l'auteur compose sa communication
en blocs (texte, image, galerie, chiffres clés, courbe, pastilles,
encadré), les met en page à la souris dans l'aperçu, la voit à droite
telle que le site la rendra, et clique **Publier**. Le site étant statique, ce qui est publié doit être stocké
quelque part : une feuille Google, invisible pour tout le monde sauf pour
celui qui la branche.

```
site — bouton « Ajouter une communication » (assets/js/editeur.js)
        │  Publier  (POST JSON vers la web app, SOURCE.publication)
        ▼
Apps Script doPost (tools/apps-script/communications-sync.gs)
        │  ajoute une ligne à l'onglet « communications »
        ▼
Feuille de PUBLICATION ──── publiée en CSV ────▶ le site la lit à l'ouverture
                                                  (SOURCE.url, assets/js/communications.js)
```

Tant que `SOURCE.publication` est vide, ce que l'on publie reste **dans le
navigateur** de l'auteur, marqué « brouillon » dans la liste (et se retire
depuis l'éditeur) : c'est le mode démonstration. Tant que `SOURCE.url` est
vide, le site lit `assets/data/communications.json`.

## 0. Brancher la publication, en cinq minutes

1. Créez un Google Sheet (par exemple `ETII Hub — publication`) avec un
   onglet `communications` dont la ligne 1 porte les en-têtes de la
   section 2 (le script les écrit lui-même si l'onglet est vide).
2. Extensions → Apps Script, collez `tools/apps-script/communications-sync.gs`.
   Renseignez `CLE_PUBLICATION` (une phrase de votre choix).
3. Déployer → Nouveau déploiement → **Application web**, exécuter en tant
   que « Moi », accès « Toute personne du domaine » (ou « disposant du
   lien », la clé fait alors le garde-fou). Copiez l'URL `/exec`.
4. Fichier → Partager → Publier sur le web → onglet `communications`,
   format **CSV** → Publier. Copiez l'URL (`output=csv`). Si la publication
   est interdite, l'URL `/exec` sert aussi le CSV (`doGet`).
5. Dans `assets/js/communications.js` :

   ```js
   export const SOURCE = {
     url: 'https://…output=csv',          // lecture
     publication: 'https://…/exec',       // écriture (bouton Publier)
     cle: 'la même phrase que CLE_PUBLICATION'
   };
   ```

À partir de là, « Publier » ajoute une ligne à la feuille et tout le monde
voit la communication à la prochaine ouverture du site. Une annonce
publiée avec l'identifiant d'une ligne existante la remplace.

## 1. Préparer la feuille

1. Créez un Google Sheet, par exemple `ETII Hub — publication` (le même que
   pour le suivi OTQ / OTD convient : un onglet de plus).
2. Créez un onglet `communications` dont la **ligne 1** porte exactement
   ces en-têtes (l'ordre n'a pas d'importance, la casse et les accents non
   plus) :

   ```
   type | id | date | pole | categorie | statut | titre | resume | corps | image | imageAlt | imageLegende | chiffres | serie | auteur | fonction
   ```

3. Chaque ligne suivante est une communication. En temps normal c'est le
   bouton **Publier** de l'éditeur qui les écrit ; on peut aussi les saisir
   à la main, ou les faire venir d'un Google Form (script `synchroniser`).

## 2. Ce que le site attend

| colonne        | contenu                                                                                       |
|----------------|-----------------------------------------------------------------------------------------------|
| `type`         | `annonce` (ou vide), `mot` (l'édito de la direction : le plus récent est en vedette, les précédents reprennent leur place dans la frise à leur date), `alerte` (bandeau) |
| `id`           | facultatif ; sert à **remplacer** une communication (même id) ; fabriqué sinon                |
| `date`         | `AAAA-MM-JJ`, et rien d'autre ; obligatoire — pour une alerte, c'est sa date de mise en ligne. Mettez la colonne au format Texte (Format → Nombre → Texte) : sinon Sheets réécrit la date dans la locale du classeur à l'export CSV (`09/21/2026`), et le site refuse la ligne plutôt que d'inventer un mois |
| `pole`         | `ETII` (tout le service), `ETIIA`, `ETIIE`, `ETIII`                                           |
| `categorie`    | un programme ou un thème (`H160`, `Outils`, `Transverse`…), affiché en étiquette              |
| `statut`       | `info`, `succes`, `urgent`                                                                    |
| `titre`        | obligatoire ; pour une alerte, c'est le texte du bandeau — une alerte quitte le bandeau 14 jours après sa `date` ; laissez `date` vide pour un bandeau qui reste jusqu'à ce que vous supprimiez la ligne |
| `resume`       | une ou deux phrases : la liste et le chapeau de la lecture                                     |
| `corps`        | le texte, une ligne par idée, avec les préfixes ci-dessous                                     |
| `image`        | une URL `https://` publique, ou un chemin `assets/img/communications/…` du site               |
| `imageAlt`     | la description de l'image (lecteurs d'écran) — obligatoire si `image` est renseignée           |
| `imageLegende` | la légende posée sur l'image                                                                   |
| `chiffres`     | jusqu'à quatre tuiles : `Libellé = valeur unité tendance ; …` (voir plus bas)                  |
| `serie`        | une courbe : `Libellé (unité) \| 2026-04 = 92,1 ; 2026-05 = 92,8 ; …`                          |
| `auteur`, `fonction` | pour l'édito seulement                                                                  |
| `blocs`        | les blocs libres de l'éditeur, en JSON — écrits par le bouton Publier ; les colonnes à plat restent renseignées pour la lecture ailleurs |

### Mise en page

Chaque bloc de la colonne `blocs` porte, en plus de son contenu, deux
attributs de mise en page que l'éditeur règle dans l'aperçu (poignée de
largeur sur le bord du bloc, boutons ◧ ◨ pour le côté, poignée ⇅ pour
l'ordre) ou dans les listes de chaque carte du formulaire :

- `largeur` : `pleine` (défaut), `deux-tiers`, `moitie` ou `tiers` — la
  place du bloc dans la grille de six colonnes de la lecture ;
- `cote` : vide (défaut, le bloc coule à la suite du précédent), `gauche`
  ou `droite` — le bord contre lequel il se cale ; deux blocs qui tiennent
  sur une même ligne se posent côte à côte.

```json
[{ "type": "image", "src": "assets/img/porteurs/h145.jpg", "alt": "Un H145 en vol",
   "largeur": "moitie", "cote": "droite" },
 { "type": "chiffres", "chiffres": [{ "libelle": "Harnais qualifiés", "valeur": 3 }],
   "largeur": "moitie" }]
```

Un attribut absent ou inconnu vaut la valeur par défaut. Une image en
premier bloc est la bannière de la communication : sa mise en page ne
s'applique pas. Sur un écran de moins de 700 px, tout repasse en pleine
largeur, dans l'ordre des blocs.

### Les préfixes du corps

C'est le vocabulaire du formulaire Apps Script d'origine du service :

```
-> Ce qui change              → un titre
• Nouvelle arborescence.      → une puce (« - » ou « * » marchent aussi)
V Aucune action requise.      → une ligne validée (coche verte)
! Sauvegardez avant 19h30.    → une alerte (triangle)
                              → une ligne vide aère
Un texte sans préfixe.        → un paragraphe
```

### Les chiffres clés

`OTQ du service = 95,4 % hausse ; Semaines d'essais = 6 ; Points bloquants = 0 baisse`

- la valeur accepte la virgule ou le point ; `%` collé ou séparé va dans
  l'unité ;
- la tendance est `hausse`, `baisse` ou `stable` (ou `↗ ↘ →`), facultative ;
- au-delà de quatre, les suivants sont ignorés.

### La courbe

`OTQ mensuel (%) | 2026-04 = 92,1 ; 2026-05 = 92,8 ; 2026-06 = ; 2026-07 = 94,2`

Un mois sans valeur laisse un **trou** : le site n'interpole jamais.

## 3. Exposer la feuille au site (lecture)

**Option A — publication sur le web (le plus simple)**
Fichier → Partager → Publier sur le web → choisir l'onglet `communications`
et le format **CSV** → Publier. Copiez l'URL (elle finit par `output=csv`).

**Option B — web app Apps Script (si la publication est interdite)**
Extensions → Apps Script, collez `tools/apps-script/communications-sync.gs`,
puis Déployer → Nouveau déploiement → « Application web » → exécuter en
tant que « Moi », accès « Toute personne disposant du lien ». L'URL `/exec`
sert le même CSV. Le script peut aussi recopier chaque nuit un onglet
source (celui d'un Google Form, par exemple) vers l'onglet publié, en
normalisant les dates.

Dans les deux cas, collez l'URL dans `assets/js/communications.js` :

```js
export const SOURCE = {
  url: 'https://…output=csv'      // ← ici
};
```

## 4. Les images

- Le plus simple : un fichier dans `assets/img/communications/` du site,
  et son chemin dans la colonne `image`. Gardez des images de 1 200 px de
  large au plus (150–250 ko).
- Sinon une image **publique** : dans Drive, partager en « Toute personne
  disposant du lien », puis utiliser le lien direct de téléchargement
  (`https://drive.google.com/uc?export=view&id=…`). Une image qui demande
  une connexion ne s'affichera pas pour les autres.
- Le site n'accepte que `https://` ou `assets/…` : tout autre chemin est
  ignoré, sans erreur.

## 5. Vérifier

- Dans le navigateur, ouvrez l'URL du CSV : l'en-tête doit apparaître en
  première ligne.
- Sur le site, la console du navigateur n'affiche aucun avertissement
  `[communications]`. Une ligne illisible (sans titre ou sans date) est
  ignorée et signalée dans cette console, jamais en page.
- Si la feuille est injoignable, le site retombe sur le fichier
  `communications.json` : personne ne voit une page blanche.

## 6. Points d'attention

- **Confidentialité** : « Publier sur le web » rend l'onglet lisible par
  quiconque a l'URL. Ne publiez que l'onglet `communications`. Si la
  politique du domaine l'interdit, prenez l'option B et restreignez l'accès
  de la web app au domaine.
- **Texte seul** : pas de HTML ni de mise en forme dans les cellules — les
  préfixes suffisent.
- **Remplacer** une communication : reprenez son `id` sur une nouvelle
  ligne et supprimez l'ancienne (le site ne dédoublonne que les entrées de
  même titre à la même date).
- **Variante Google Form** : un formulaire lié à la feuille écrit ses
  réponses dans un onglet ; le script `communications-sync.gs` recopie cet
  onglet vers `communications` chaque nuit en renommant les colonnes.

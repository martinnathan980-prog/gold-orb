# Communications — publier depuis une feuille Google

Le site est statique : il ne publie rien, il **lit**. La « partie
administrateur » est donc une feuille Google : le chef y ajoute **une ligne
par communication**, et le site la lit à l'ouverture de la page. Aucun
serveur, aucun compte, aucun déploiement.

```
admin.html (le formulaire + l'aperçu)        Feuille de PUBLICATION (la vôtre)
┌────────────────────────────────┐  coller   ┌──────────────────────────────┐
│ titre, résumé, texte, image,   │ ────────▶ │ onglet « communications »    │
│ chiffres clés, courbe → LIGNE  │           │ une ligne = une communication│
└────────────────────────────────┘           └──────────────┬───────────────┘
                                                            │ publié sur le web (CSV)
                                                            ▼
                                       ETII Hub — assets/js/communications.js (SOURCE.url)
```

Tant que `SOURCE.url` est vide, le site lit `assets/data/communications.json`
(et la version autonome lit toujours le fichier intégré).

## 1. Préparer la feuille

1. Créez un Google Sheet, par exemple `ETII Hub — publication` (le même que
   pour le suivi OTQ / OTD convient : un onglet de plus).
2. Créez un onglet `communications` dont la **ligne 1** porte exactement
   ces en-têtes (l'ordre n'a pas d'importance, la casse et les accents non
   plus) :

   ```
   type | id | date | pole | categorie | statut | titre | resume | corps | image | imageAlt | imageLegende | chiffres | serie | auteur | fonction
   ```

3. Chaque ligne suivante est une communication. Le plus simple : ouvrir
   `admin.html`, remplir le formulaire, cliquer **Copier la ligne pour la
   feuille Google**, puis coller dans la première ligne vide de l'onglet
   (Ctrl V : Sheets répartit les colonnes tout seul).

## 2. Ce que le site attend

| colonne        | contenu                                                                                       |
|----------------|-----------------------------------------------------------------------------------------------|
| `type`         | `annonce` (ou vide), `mot` (le mot du chef : le plus récent est affiché), `alerte` (bandeau)   |
| `id`           | facultatif ; sert à **remplacer** une communication (même id) ; fabriqué sinon                |
| `date`         | `AAAA-MM-JJ` ou `JJ/MM/AAAA` ; obligatoire sauf pour une alerte                               |
| `pole`         | `ETII` (tout le service), `ETIIA`, `ETIIE`, `ETIII`                                           |
| `categorie`    | un programme ou un thème (`H160`, `Outils`, `Transverse`…), affiché en étiquette              |
| `statut`       | `info`, `succes`, `urgent`                                                                    |
| `titre`        | obligatoire ; pour une alerte, c'est le texte du bandeau                                      |
| `resume`       | une ou deux phrases : la liste et le chapeau de la lecture                                     |
| `corps`        | le texte, une ligne par idée, avec les préfixes ci-dessous                                     |
| `image`        | une URL `https://` publique, ou un chemin `assets/img/communications/…` du site               |
| `imageAlt`     | la description de l'image (lecteurs d'écran) — obligatoire si `image` est renseignée           |
| `imageLegende` | la légende posée sur l'image                                                                   |
| `chiffres`     | jusqu'à quatre tuiles : `Libellé = valeur unité tendance ; …` (voir plus bas)                  |
| `serie`        | une courbe : `Libellé (unité) \| 2026-04 = 92,1 ; 2026-05 = 92,8 ; …`                          |
| `auteur`, `fonction` | pour le mot du chef seulement                                                           |

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

## 3. Exposer la feuille au site

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

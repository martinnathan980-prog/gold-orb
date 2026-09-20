# Suivi OTQ / OTD — alimentation nocturne depuis Google Sheets

Le site est statique : il ne calcule rien, il **lit** un CSV à l'ouverture
de la page. Le travail de nuit se fait dans Google Sheets, avec Apps Script.

```
Feuille SOURCE (accès en lecture)          Feuille de PUBLICATION (la vôtre)
┌──────────────────────────────┐  minuit   ┌──────────────────────────────┐
│ mois │ otq │ otd │ cibles     │ ───────▶ │ onglet « publication » (CSV) │
└──────────────────────────────┘ Apps      └──────────────┬───────────────┘
                                  Script                  │ publié sur le web
                                                          ▼
                                            ETII Hub — assets/js/otq.js (SOURCE.url)
```

## 1. Préparer la feuille de publication

1. Créez un Google Sheet à vous, nommé par exemple `ETII Hub — publication`.
2. Extensions → Apps Script. Collez le contenu de
   `tools/apps-script/otq-sync.gs`. Renseignez en tête :
   - `ID_FEUILLE_SOURCE` : l'identifiant de la feuille qu'on vous a
     partagée (dans son URL, entre `/d/` et `/edit`) ;
   - `NOM_ONGLET_SOURCE` et `PLAGE_SOURCE` : l'onglet et les colonnes
     `mois | otq | otd | cible otq | cible otd` (les cibles sont facultatives).
3. Exécutez `synchroniser` une fois à la main : Google demande
   l'autorisation d'accéder aux deux feuilles ; acceptez. L'onglet
   `publication` apparaît, rempli.
4. Exécutez `installerDeclencheur` une fois : le script tournera **chaque
   nuit entre 0 h et 1 h** (fuseau horaire : Paramètres du projet).
   Vérifiez dans le menu « Déclencheurs » (icône réveil).

## 2. Exposer le CSV au site

**Option A — publication sur le web (le plus simple)**
Fichier → Partager → Publier sur le web → choisir l'onglet `publication`
et le format **CSV** → Publier. Copiez l'URL (elle finit par
`output=csv`).

**Option B — web app Apps Script (si la publication est interdite)**
Déployer → Nouveau déploiement → type « Application web » → exécuter en
tant que « Moi », accès « Toute personne disposant du lien » → Déployer.
Copiez l'URL qui finit par `/exec` : la fonction `doGet` du script sert
le même CSV.

Dans les deux cas, collez l'URL dans `assets/js/otq.js` :

```js
export const SOURCE = {
  url: 'https://…output=csv',      // ← ici
  exemple: 'assets/data/otq-exemple.csv'
};
```

Tant que `url` est vide, la page affiche l'exemple embarqué avec le
bandeau « Données d'exemple ». Dès qu'elle est renseignée, le bandeau
devient « Source du service ».

## 3. Ce que le site attend

| colonne     | format          | obligatoire |
|-------------|-----------------|-------------|
| `mois`      | `AAAA-MM`       | oui         |
| `otq`       | nombre (95,4 ou 95.4) | oui   |
| `otd`       | nombre          | oui         |
| `cible_otq` | nombre          | non         |
| `cible_otd` | nombre          | non         |

Une case vide laisse un **trou** dans la courbe : le site n'interpole
jamais et ne remplace jamais par zéro. Les douze derniers mois sont
tracés ; les tuiles montrent le dernier mois, l'écart à la cible et la
variation mensuelle.

## 4. Vérifier

- Dans le navigateur, ouvrez l'URL du CSV : vous devez voir le texte brut
  avec l'en-tête `mois,otq,otd,cible_otq,cible_otd`.
- Sur le site, le bandeau doit indiquer « Source du service ».
- En cas d'erreur (URL fausse, feuille dépubliée), la section affiche
  l'erreur et un bouton « Réessayer » : aucun chiffre périmé n'est montré.

## 5. Points d'attention

- **Confidentialité** : « Publier sur le web » rend l'onglet lisible par
  quiconque a l'URL. Ne publiez que l'onglet `publication`, jamais la
  feuille source. Si la politique du domaine l'interdit, prenez l'option B
  et restreignez l'accès de la web app au domaine.
- **Quota** : un déclencheur quotidien est très loin des limites Apps
  Script.
- **Historique** : si vous voulez conserver plus de douze mois, laissez-les
  dans l'onglet — le site ne trace que les douze derniers, mais le tableau
  du graphique donne tout ce qu'il lit.

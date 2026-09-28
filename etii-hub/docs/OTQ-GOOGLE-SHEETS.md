# Suivi OTQ — le site lit votre Command Center

Le suivi OTQ du tableau de bord (`assets/js/otq.js`) ne recompte rien : il
lit l'onglet **« Data »** de la feuille « Command Center » du service, que
son propre script remplit (menu **🚀 Airbus Sync**, ou son déclencheur de
nuit) à partir de deux sources, « Drawings Prod » et « Drawings TVE »,
pour toutes les lignes où figure ETII.

```
Drawings Prod ─┐                          ┌─ Code.gs du site (lireOtq_)
               ├─ script du Command Center ─ onglet « Data » ─┤  à chaque ouverture, lu seulement
Drawings TVE ──┘   (Airbus Sync)                              └─ otq.js : le mois en grand, les barres
```

## Ce que le site lit

Une ligne par mois, sept colonnes, reconnues par leurs mots (emoji et
majuscules sans importance) :

| Colonne de « Data » | Dans le site |
|---|---|
| 📅 MOIS (« OCT 26 ») | le mois (`2026-10`) |
| ✅ PROD ACCEPTED · ⚠️ PROD MINOR REFUSED · ❌ PROD REFUSED | **Qualité des plans (OTQ)** : acceptés, refus mineurs, refusés |
| 🟢 TVE ACCEPTED · 🟡 TVE FALSE REFUSED · 🔴 TVE REFUSED | **TVE** : acceptés, faux refus, refusés |

Le taux affiché est **acceptés ÷ plans présentés** (la somme des trois
statuts) ; le mois en grand est le dernier mois **complet** (le mois en
cours est montré estompé, « en cours »). Les bascules choisissent la
mesure (OTQ ou TVE) et la période (3 mois, 6 mois, 1 an, tout) ; le
tableau des nombres est replié sous les barres.

## Le brancher

Dans `tools/apps-script/site/Code.gs`, en haut :

```js
var OTQ_ID_FEUILLE = '1AbC…';   // la feuille du Command Center
var OTQ_ONGLET = 'Data';
```

Puis **installer** (le journal d'exécution dit « Suivi OTQ lu : 14 mois »)
et une nouvelle version du déploiement. Pas à pas :
`docs/INSTALLER-SUR-GOOGLE.txt`, étape 10.

Tant que `OTQ_ID_FEUILLE` est vide, le site montre
`assets/data/otq-exemple.csv`, annoncé « Données d'exemple ». On peut
aussi publier un CSV au même format (`SOURCE.url` d'`otq.js`), mais ce
dépôt est public : n'y écrivez jamais d'adresse.

## Ce que le site ne sait pas (encore)

- **L'OTD** : les deux sources comptent des statuts, pas des dates. Un
  « On Time Delivery » demanderait une date promise et une date de remise
  par plan. Si TVE tient lieu de suivi des délais chez vous, dites-le :
  la section se renommera.
- Les mois sans aucun plan n'apparaissent pas dans « Data » : la période
  « 3 mois » compte les trois derniers mois **présents**.

# Import et automatisation

GATES ne fournit qu'une photo : l'état du jour. **On ne peut pas reconstituer
le passé, seulement l'accumuler.** Tout ce dossier sert à cela : récupérer les
extracts, les déposer dans le classeur, et laisser l'historique se construire
de lui-même.

Trois contraintes du poste de travail commandent la forme de ces scripts :
aucun exécutable à installer, aucune bibliothèque à télécharger, et le PC
n'est allumé que quand on travaille. Les cinq scripts tiennent donc en
**bibliothèque standard Python**, et rien ne tourne quand la machine dort.

| Script | Ce qu'il fait |
|---|---|
| `piloter_chrome.py` | Parle à Chrome — va à cette page, clique ce bouton, lis ce tableau |
| `extraire.py` | Rejoue une **recette** : la suite de gestes de l'extraction |
| `deposer.py` | Envoie un extract au classeur, qui le colle et archive la semaine |
| `lire_plan.py` | Retire les composants d'un plan ELEC au format PDF |
| `releve.py` | Variante hors Google : archive les relevés dans des fichiers locaux |

```bash
npm run test:import      # les trois batteries de ce dossier
```

## 1. Préparer Chrome (une seule fois)

Chrome sait obéir à des ordres, à condition d'avoir été lancé avec une option
de débogage. **Fermer Chrome entièrement**, puis le relancer ainsi :

```
chrome.exe --remote-debugging-port=9222
```

Le plus simple : copier le raccourci Chrome, propriétés, ajouter l'option à la
fin de la cible, et n'utiliser que ce raccourci. Le profil reste le vôtre —
vos onglets, vos favoris, votre **authentification intranet**. Rien n'est
stocké : aucun mot de passe n'est lu ni écrit par ces scripts.

Pour vérifier que tout est en place :

```bash
python3 import/piloter_chrome.py
```

Il répond en trois lignes : la version de Python, le Chrome trouvé, et si le
canal est ouvert.

**Ce n'est pas un clic simulé.** On ne déplace pas la souris, on ne tape pas
au clavier : on désigne un élément de la page et on lui demande de faire ce
qu'il ferait sous le doigt. Travailler à côté pendant ce temps ne dérange
rien, et rien ne se dérègle si une fenêtre passe devant : le pilote **ouvre
son propre onglet** au lieu de détourner celui qui est sous vos yeux, et le
referme en partant.

## 2. Écrire la recette, une fois

Une recette est un fichier JSON qui dit les gestes, dans l'ordre. Trois
modèles sont fournis dans `recettes/`, à compléter avec ce qu'on voit à
l'écran :

| Modèle | Pour |
|---|---|
| `gates-par-contrat.json` | l'extract GATES, un contrat après l'autre |
| `see-par-contrat.json` | l'extract SEE (« Nommage WD BFLOW ») |
| `composants-par-plan.json` | les composants, un plan après l'autre |

```json
{
  "telechargements": "C:/Users/VOTRE-COMPTE/Downloads",
  "variable": "contrat",
  "valeurs": ["HDK", "THS", "VRK"],
  "etapes": [
    { "faire": "ouvrir",        "url": "https://intranet/gates/recherche" },
    { "faire": "remplir",       "ou": "#recherche", "texte": "{contrat}" },
    { "faire": "cliquer_texte", "texte": "Tout extraire" },
    { "faire": "telecharger",   "vers": "gates-{contrat}.csv" }
  ]
}
```

Les gestes : `ouvrir`, `attendre`, `cliquer`, `cliquer_texte`, `remplir`,
`telecharger`, `lire_tableau`, `patienter`. `{contrat}` — ou toute autre
variable — est remplacé par la valeur du tour en cours. Chaque étape accepte
un `delai` en secondes ; `telecharger` accepte un `motif` (`"*.csv"`) pour ne
pas confondre avec un fichier téléchargé en même temps.

Le dossier de `telechargements` peut s'écrire comme sous Windows —
`%USERPROFILE%/Downloads`, `~/Downloads` — et doit exister : sinon le script
le dit au lieu d'attendre un fichier qui n'arrivera jamais.

Le plus simple reste **`cliquer_texte`** : il suffit du texte écrit sur le
bouton — l'égalité exacte l'emporte sur la ressemblance, pour qu'« Extraire »
ne clique pas « Extraire l'historique complet ». Pour un champ, il faut un sélecteur : clic droit dessus, « Inspecter »,
et relever son `id` (`#recherche`) ou sa classe (`.champ-recherche`).

Vérifier une recette sans rien lancer :

```bash
python3 import/extraire.py import/recettes/gates-par-contrat.json --verifier
```

Puis la jouer :

```bash
python3 import/extraire.py import/recettes/gates-par-contrat.json
python3 import/extraire.py import/recettes/composants-par-plan.json --valeurs-fichier refs.txt
```

Rien n'est deviné : tant que la recette ne dit pas quoi cliquer, le script ne
clique rien. Une étape qui échoue arrête le tour en disant laquelle et
pourquoi.

## 3. Déposer dans le classeur

Le classeur peut publier une petite adresse qui reçoit les extracts. Dans
`Code.gs`, renseigner un secret :

```js
DEPOT: { SECRET: 'une phrase longue et imprévisible', MAX_LIGNES: 20000 },
```

puis **Déployer → Nouveau déploiement → Application web**, exécutée en votre
nom, accessible à vous seul. Copier l'adresse obtenue dans
`import/depot.json` (ce fichier n'est jamais publié — il est dans le
`.gitignore`) :

```json
{ "adresse": "https://script.google.com/macros/s/…/exec",
  "secret":  "la même phrase que dans CONFIG.DEPOT.SECRET" }
```

Alors :

```bash
python3 import/deposer.py gates-HDK.csv --onglet HDK --archiver
```

L'onglet est vidé et réécrit — le geste `Ctrl+A`, `Suppr`, coller en A1 — puis
le relevé de la semaine est archivé pour ce contrat. La page se met à jour
toute seule. Redéposer la même semaine **met la ligne à jour** au lieu d'en
empiler une seconde.

Sans secret, tout dépôt est refusé. Un onglet d'historique n'est jamais une
cible. `--creer` autorise la création d'un onglet absent (pour coller SEE la
première fois).

`deposer.py` lit des **CSV** : point-virgule, virgule ou tabulation, avec ou
sans BOM, en UTF-8 ou en ANSI. Il ne lit pas le format Excel — cela demanderait
une bibliothèque que le poste ne peut pas installer. Demander le CSV à
l'export, ou enregistrer le `.xlsx` en CSV.

## 4. La semaine, d'un seul geste

Un fichier `.bat` sur le Bureau, à double-cliquer le lundi :

```bat
@echo off
cd /d C:\chemin\vers\gates-analytics
python import\extraire.py import\recettes\gates-par-contrat.json
if errorlevel 1 goto rate
for %%C in (HDK THS VRK) do (
  python import\deposer.py "%USERPROFILE%\Downloads\gates-%%C.csv" --onglet %%C --archiver
  if errorlevel 1 goto rate
)
echo Termine.
goto fin
:rate
echo ATTENTION : une etape a echoue, rien de plus n'a ete depose.
:fin
pause
```

Le `if errorlevel 1` compte : sans lui, une extraction ratée le lundi ferait
redéposer et **archiver l'extract de la semaine précédente**, et l'historique
enregistrerait une semaine sans avancement qui n'a jamais existé.

Pour s'en passer tout à fait : **Planificateur de tâches Windows**, nouvelle
tâche, déclencheur « à l'ouverture de session » ou « chaque lundi à 9 h », avec
la case *Exécuter la tâche dès que possible si un démarrage planifié est
manqué* — le PC éteint le lundi rattrape au premier allumage. Et Chrome doit
avoir été lancé avec son option de débogage.

À valider avec l'informatique avant mise en place.

## 5. Les composants d'un plan : `lire_plan.py`

Quand les composants ne sortent d'aucun tableur, ils sont sur le **plan**. Un
PDF sorti d'un outil de dessin n'est pas une image : le texte y est écrit
comme du texte, avec ses coordonnées, et les boîtes comme des rectangles. Il
n'y a donc **rien à reconnaître et rien à deviner** — on lit ce qui est écrit,
et on regarde ce qui est dans quelle boîte.

```bash
python3 import/lire_plan.py plan.pdf
python3 import/lire_plan.py plan.pdf --csv composants.csv
python3 import/lire_plan.py plan.pdf --repere "^EQ-[0-9]{4}$"
```

Le compte rendu dit toujours trois choses, et c'est ce qui le rend utilisable :

```
plan.pdf : 312 texte(s), 96 rectangle(s), 51 boîte(s) retenue(s)
  50 composant(s) sûr(s)
    18AB       Connecteur · PN-1001
    120PA3     Boîtier · PN-1002
  1 boîte(s) à regarder :
    plusieurs repères dans la même boîte — 44XY, 45XZ
  2 repère(s) sans boîte : 91AA, 92AB
```

**Un composant n'est jamais inventé** : une boîte avec deux repères, une boîte
sans repère, un repère écrit entre deux boîtes possibles — tout cela est
signalé, jamais tranché au hasard. C'est ce qui permet de faire confiance aux
lignes « sûres » et de ne relire à la main que la poignée restante.

Le motif du repère se règle (`--repere`) ; par défaut quelques chiffres,
quelques lettres, éventuellement des chiffres : `18AB`, `120PA3`.

**Un plan scanné ne marche pas, et le script le dit.** Une photo de papier ne
contient aucun texte : il faudrait de la reconnaissance de caractères, donc un
programme à installer. Dans ce cas, demander le PDF d'origine — celui qui sort
de l'outil de dessin — plutôt qu'un scan.

## 6. La variante hors Google : `releve.py`

Elle ne dépend d'aucun classeur : elle archive les relevés dans des fichiers
locaux, pour travailler sans le tableau de bord.

```bash
python releve.py export.csv
```

Sortie :

```
Relevé 2026-S38 archivé (2 au total)
  7 plans : 3 terminés (43 %), 3 en cours, 1 à faire, 0 non renseignés
  depuis le dernier import : 2 ont avancé, 1 ont reculé, 1 vient d'être renseigné,
  1 nouveau, 0 disparu
  ATTENTION, avancement en recul : UD-31-0005
```

Deux fichiers sont tenus à jour dans `donnees/` :

| Fichier | Contenu |
|---|---|
| `releves.csv` | un relevé par semaine ISO : comptes globaux et par ATA |
| `plans.json` | l'avancement plan par plan du dernier import, pour comparer au suivant |

Réimporter dans la même semaine **met à jour** la ligne au lieu d'en ajouter une.

### Ce que le script tolère

- une ou plusieurs lignes de titre au-dessus de l'en-tête réel ;
- une ligne de groupes fusionnés au-dessus des noms de colonnes ;
- un séparateur `;` ou `,` (détecté automatiquement) ;
- un BOM UTF-8 en tête de fichier ;
- des colonnes déplacées ou renommées — elles sont retrouvées par mots-clés
  (`CLES` en haut du fichier), pas par position.

Si une colonne indispensable manque, le script s'arrête **en affichant les
en-têtes qu'il a lus**, pour qu'on voie tout de suite quoi ajuster.

### Les quatre états

Identiques à ceux du tableau de bord :

| État | Règle |
|---|---|
| terminé | `>= 100`, ou « terminé / achevé / clôturé / soldé / fini » |
| en cours | valeur strictement entre 0 et 100 |
| à faire | `<= 0`, ou « à faire » |
| non renseigné | cellule vide |

« À faire » est une valeur saisie ; une cellule vide est un **défaut de saisie**.
Les confondre masquerait le second — c'est précisément ce qu'on veut voir.

## 7. Le transport par la messagerie

La passerelle mail retient ce qui ressemble à du code. `empaqueter.py` le rend
méconnaissable (gzip puis base64), `decoder.py` le reconstruit et vérifie son
empreinte :

```bash
python3 import/empaqueter.py Javascript.html -o import/Javascript.html.gz.b64.txt
python3 decoder.py Javascript.html.gz.b64.txt
```

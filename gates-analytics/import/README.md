# Import et automatisation

GATES ne fournit qu'une photo : l'état du jour. **On ne peut pas reconstituer
le passé, seulement l'accumuler.** Tout ce dossier sert à cela : récupérer les
extracts, les déposer dans le classeur, et laisser l'historique se construire
de lui-même.

Trois contraintes du poste de travail commandent la forme de ces scripts :
aucun exécutable à installer, aucune bibliothèque à télécharger, et le PC
n'est allumé que quand on travaille. Tout tient donc en **bibliothèque
standard Python** — sauf la lecture des scans, qui demande trois paquets
Python ordinaires et un moteur de reconnaissance, eux aussi sans exécutable —
et rien ne tourne quand la machine dort.

| Script | Ce qu'il fait |
|---|---|
| `essai.py` | **L'essai à blanc** : un faux GATES sur votre PC, pour apprendre la chaîne sans intranet |
| `diagnostic.py` | **La fiche d'un vrai extract** : colonnes, valeurs d'avancement, anatomie des références — lit les .xlsx sans rien installer |
| `piloter_chrome.py` | Parle à Chrome — va à cette page, clique ce bouton, lis ce tableau |
| `extraire.py` | Rejoue une **recette** : la suite de gestes de l'extraction |
| `deposer.py` | Envoie un extract au classeur, qui le colle et archive la semaine |
| `lire_composants.py` | Un plan, ou un dossier de plans, **quel que soit le format** : ses composants, comparés à la base |
| `lire_plan.py` · `lire_visio.py` · `lire_dxf.py` · `lire_scan.py` | Les lecteurs : PDF de dessin, Visio, DXF, scan |
| `composants.py` | Le socle commun des lecteurs : la règle « une boîte, un repère », les lectures confondues, la comparaison à la base |
| `releve.py` | Variante hors Google : archive les relevés dans des fichiers locaux |

```bash
npm run test:import      # les neuf batteries de ce dossier
```

## 0. D'abord : l'essai à blanc

Avant de toucher à l'intranet, on s'entraîne sur **un faux GATES qui tourne
sur le PC**. Une seule commande fabrique tout et joue la chaîne entière :

```bash
python import\essai.py --jouer
```

Elle lance son propre Chrome, ouvre une page GATES d'essai, cherche HDK, THS
et VRK, télécharge trois CSV, puis lit les composants d'un plan d'essai —
en PDF, en DXF et en scan. Il n'y a **rien à préparer** : ni raccourci de
débogage, ni recette à écrire, ni intranet.

Sans `--jouer`, la même commande prépare le dossier et affiche la **marche à
suivre** pas à pas, avec les vrais gestes : ouvrir le canal de Chrome, jouer
la recette, lire un plan — et ce qui changera au bureau (trois lignes).

Le dossier d'essai contient :

| Fichier | Ce que c'est |
|---|---|
| `gates-essai.html` | l'intranet en miniature : un champ, un bouton, un tableau, un lien |
| `recette-essai.json` | la recette déjà remplie pour cette page — le modèle à copier |
| `plan-essai.pdf` · `.dxf` · `-scanne.png` | le même plan sous trois formes |
| `composants-base.csv` | les repères que « la base » attend — dont un absent du plan, exprès |

Le plan d'essai est fait pour **montrer ce que le lecteur refuse d'inventer** :
cinq composants nets, une boîte où deux repères sont écrits, un repère posé
loin de toute boîte, et un repère attendu qui n'est pas dessiné. Le compte
rendu doit dire exactement cela.


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

## 5. Les composants d'un plan, quel que soit le format

Quand les composants ne sortent d'aucun tableur, ils sont sur le **plan** —
et le plan arrive sous toutes les formes : un PDF sorti de l'outil de dessin,
un Visio, un DXF, un scan. Une seule commande les lit tous :

```bash
python3 import/lire_composants.py plan.pdf
python3 import/lire_composants.py dossier-des-plans/ --connus base.csv --csv composants.csv --controle controles/
```

| Le fichier | Le lecteur | Ce qu'il lit |
|---|---|---|
| PDF sorti d'un outil de dessin | `lire_plan.py` | le texte et les rectangles, écrits comme tels |
| Visio `.vsdx`, `.vsdm`, `.vdx` — et `.vsd` si Visio est sur le poste | `lire_visio.py` | les formes et leur texte, groupes ouverts, gabarits compris |
| DXF | `lire_dxf.py` | textes, polylignes, traits qui se rejoignent, blocs insérés et leurs attributs |
| PDF scanné, PNG, JPEG, TIFF | `lire_scan.py` | l'image : les boîtes d'abord, puis les caractères |

Le choix se fait tout seul, sur l'extension puis sur le contenu : un PDF qui
n'a pas de texte est lu comme un scan.

### La règle, la même partout

Tous les lecteurs ramènent le plan à la même chose — des textes placés, et
des boîtes — puis appliquent la même règle :

- une boîte, un repère → un composant **sûr** ;
- une boîte à plusieurs repères, ou sans aucun → **à regarder**, signalée
  avec ce qu'elle contient ;
- un repère écrit à côté d'une boîte vide → rattaché, mais seulement si une
  seule boîte est assez proche ; sinon **sans boîte**, signalé ;
- le cadre du plan — le rectangle qui contient les autres et couvre la page —
  est ignoré, et compté comme tel.

**Un composant n'est jamais inventé.** C'est ce qui permet de faire confiance
aux lignes sûres et de ne relire à la main que la poignée restante :

```
plan.pdf (dessin PDF) : 312 texte(s), 96 rectangle(s), 51 boîte(s) retenue(s), 1 cadre(s) ignoré(s)
  50 composant(s) sûr(s)
    18AB       Connecteur · PN-1001
    120PA3     Boîtier · PN-1002
  1 boîte(s) à regarder :
    plusieurs repères dans la même boîte — 44XY, 45XZ
  2 repère(s) sans boîte : 91AA, 92AB
  la base attend 52 repère(s) : 50 retrouvé(s) sur le plan
    2 absent(s) du plan : 44XY, 45XZ
```

Le motif du repère se règle (`--repere`) ; par défaut quelques chiffres,
quelques lettres, éventuellement des chiffres : `18AB`, `120PA3`.

### Les scans : l'image, puis les caractères

Un scan ne contient aucun texte : il faut le reconnaître. `lire_scan.py` s'y
prend en cinq temps.

1. Il sort l'image du fichier — PNG, JPEG, TIFF, ou l'image enfouie dans le
   PDF, quel que soit l'emballage du scanner : JPEG, télécopie CCITT, pixels
   bruts compressés, lignes à la PNG, vieux LZW.
2. Il trouve les **boîtes** par une analyse d'image classique, sans
   apprentissage : on ne garde que les traits droits, on ressoude les
   coupures, et l'intérieur d'une boîte est un trou rectangulaire du dessin.
   Un fil qui arrive sur la boîte ne la change pas. Un trait franchement
   coupé fait une boîte qu'on ne voit pas — et le repère qu'elle portait est
   alors signalé « sans boîte », pas inventé.
3. Il fait lire les caractères deux fois : la page entière par tuiles, puis
   **chaque boîte agrandie**, là où le repère est petit.
4. Il comprend chaque mot lu comme un repère, en corrigeant ce qu'une
   lecture confond — O et 0, I et 1, S et 5, B et 8, Z et 2, G et 6 — mais
   jamais plus de lettres qu'il n'en faut, et seulement quand une seule
   forme est possible. **La liste des repères que la base attend tranche les
   autres cas** (`--connus`) : c'est elle qui fait la fiabilité.
5. Une page couchée est tournée jusqu'à ce que les mots soient droits.

Chaque correction est dite (`l8AB → 18AB`) et gardée dans le CSV ; ce qui
reste incertain est listé avec ses candidats. Et `--controle dossier/` écrit
**une image de contrôle** par page : le scan, avec en vert les composants
sûrs, en orange les boîtes à regarder, en rouge les repères sans boîte — la
relecture d'un coup d'œil.

Deux moteurs de reconnaissance, tous deux **hors ligne**, sans exécutable :

| Moteur | Installation | Remarque |
|---|---|---|
| **RapidOCR** | `pip install rapidocr-onnxruntime` | un paquet Python ordinaire, modèles compris ; le plus sûr des deux — c'est lui que la batterie joue |
| **Windows 10/11 intégré** | rien | `ocr_windows.ps1`, appelé par PowerShell ; la langue doit avoir sa *reconnaissance optique des caractères* (Paramètres › Langue › Options) |

Et trois paquets Python ordinaires pour l'image :
`pip install numpy pillow opencv-python-headless`. Le moteur se choisit
tout seul (`--moteur rapidocr` ou `windows` pour l'imposer). Tout le reste du
dossier reste en bibliothèque standard.

### Comparer à la base : `--connus`

```
Plan;Repère ELEC;PN
TFE2130A600001A;18AB;PN-1001
TFE2130A600001A;19CD;PN-1002
```

Un CSV avec une colonne plan et une colonne repère — les intitulés sont
retrouvés par mots-clés, comme partout ailleurs — ou un repère par ligne pour
un seul plan. Le plan d'un fichier se retrouve par son nom, ou par la
référence contenue dans le nom du fichier. Le compte rendu dit alors ce que
la base attend, ce qui est retrouvé, ce qui manque sur le plan, ce qui est en
plus. Le CSV de sortie met tout sur **une ligne par chose vue** — sûr,
corrigé, douteux, sans boîte, incertain, attendu absent — à trier dans un
tableur.

Dans le `.bat` du lundi, une ligne de plus :

```bat
python import\lire_composants.py "%USERPROFILE%\Plans" --connus composants-base.csv --csv composants-lus.csv --controle controles
```

### Ce que ces lecteurs ne font pas

- une boîte en pointillés, ou un trait coupé sur un scan : pas de boîte — le
  repère est signalé sans boîte ;
- un `.vsd` binaire sans Visio : *Enregistrer sous → Dessin Visio (.vsdx)* ;
  avec Visio et `pip install pywin32`, la conversion se fait toute seule ;
- un DWG : *Enregistrer sous → DXF* ;
- une image JBIG2 dans un PDF : rescanner en JPEG ou en TIFF ;
- un PDF de dessin dont le texte a été converti en traits : ni texte ni
  image — demander l'original, ou l'imprimer en image ;
- les formes Visio tournées et les blocs DXF tournés d'un angle quelconque :
  la boîte est prise droite.

### Ce qui a été vérifié, et où

La batterie fabrique ses propres plans — PDF, Visio, DXF, images, et PDF
scannés dans chaque emballage — et RapidOCR y lit vraiment les repères :
papier gris et grenu, page couchée, télécopie, lettres confondues corrigées
par la liste de la base. **Aucun vrai plan n'est encore passé dedans** : le
premier réglera le motif du repère et les tailles, et dira ce que ces plans
fabriqués n'ont pas prévu. Le moteur intégré à Windows n'a pu être joué
qu'avec un faux PowerShell : le dialogue est vérifié, pas le moteur lui-même —
cela demande un poste Windows.

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

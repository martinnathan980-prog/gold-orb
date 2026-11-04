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
| `robot.py` | **Le robot (débrief 28)** : il regarde une fois l'export fait à la main (« apprendre »), le refait tout seul une fois par jour, à partir de 14 h (une seule tâche planifiée, `activer` : l'heure, l'ouverture de session, le retour devant l'écran) et dépose les fichiers dans le tableau de bord (page `?page=import`, réservée au responsable et aux administrateurs de tous les contrats). GATES s'apprend sur un seul contrat : le robot le refait pour chaque contrat que la fenêtre d'import connaît ce jour-là (nom du contrat remplacé, exigé sur ce qu'il clique), chacun dans sa case. Il attend que Google réponde, réessaie lui-même (trois passages par jour au plus, à 20 min) et ne le dit qu'après le dernier ; jamais deux robots à la fois ; un fichier dont la fenêtre d'import doute n'est pas importé. Un champ se reconnaît à son nom (son intitulé : « PSN »), jamais à ce qu'on y a tapé ; la frappe s'apprend dès qu'on tape (listes de suggestions), y compris dans un composant à racine fantôme. Un bouton icône se reconnaît à sa bulle d'aide (« Export all »), son icône ou son identifiant de test ; après chaque clic, le robot attend que la page ait fini de calculer (requêtes en cours, roue de chargement), et ne clique pas un bouton grisé ou couvert ; un bouton qui ouvre un menu (« Export all ») dont le menu ne paraît pas est réessayé autrement (second clic, appui envoyé au bouton, Entrée, flèche bas, Espace) — jamais un « Submit » ; le fichier est attendu juste après le geste qui le fait venir, avant un « log out ». Débrief 30 : les contrats se gèrent dans le tableau de bord (Administration → Contrats) ; le robot lit dans la fenêtre d'import chaque contrat, le nom exact de sa tranche dans GATES (celui de sa fiche l'emporte sur ce qu'il avait retenu) et les contrats « prévus » (ajoutés, sans onglet encore : leur premier export crée leur onglet) ; ses exports d'avant se rangent tout seuls (l'ancien « GATES HDK » devient l'export de tous les contrats, une seule exportation par case, les autres en secours ; robot.json copié d'abord dans robot.avant-rangement.json) ; après le dépôt, il envoie son compte rendu au tableau de bord par le pont de la fenêtre (#pont-robot → importRapport) — une erreur « de fiche » (nom GATES, colonne ELEC, PSN, export douteux) s'y voit à côté du contrat, sans nouvel essai ni fenêtre d'alerte. Débrief 31 : la page du robot garde le focus même quand on clique dans une autre application (Chrome fait comme si elle était au premier plan, et un script posé dans chaque page lui cache la perte du focus venue de l'extérieur : un menu de GATES ou de SEE ne se referme plus) ; à chaque passage le robot dit ce qu'il a lu du tableau de bord (l'adresse, sa « Livraison », et pour chaque contrat ce qu'il tapera dans GATES), et dit en clair une ANCIENNE version du tableau de bord (une adresse /exec d'un ancien déploiement) ; son adresse se garde en lien **/dev** (Déployer → Tester les déploiements : toujours le dernier code enregistré, plus jamais à changer), se change et se vérifie avec « Changer l'adresse du tableau de bord » (et « 1 - Preparer ») ; son compte rendu porte la `livraison` qu'il a vue ; GATES s'apprend en lisant les fiches (« HDK AA » reconnu sans question) ; « 0 - Tout oublier » pour tout recommencer (voir § 9). Tests : `tests_robot.py` (avec un vrai Chrome : `SUIVI_FWD_CHROME` ; focus : ce Chrome à l'écran sous Xvfb, partie sautée sans Xvfb ; avec Node, la vraie fenêtre d'import servie par `tests/fenetre-pour-robot.js`, par /exec et par /dev ; `SUIVI_FWD_CODE_GS` : un autre Code.gs à servir). Installé par `suivi-fwd-robot.py.txt` (fabriqué par `paquet_robot.py`) |
| `essai.py` | **L'essai à blanc** : un faux GATES sur votre PC, pour apprendre la chaîne sans intranet |
| `paquet.py` | Fabrique **le fichier unique qui se déballe tout seul** : tout ce dossier, en un `.txt` qui est aussi un programme |
| `diagnostic.py` | **La fiche d'un vrai extract** : colonnes, valeurs d'avancement, anatomie des références — lit les .xlsx sans rien installer |
| `piloter_chrome.py` | Parle à Chrome — va à cette page, clique ce bouton, lis ce tableau |
| `extraire.py` | Rejoue une **recette** : la suite de gestes de l'extraction |
| `deposer.py` | Envoie un extract au classeur, qui le colle et archive la semaine |
| `lire_composants.py` | Un plan, ou un dossier de plans, **quel que soit le format** : ses composants, comparés à la base |
| `lire_plan.py` · `lire_visio.py` · `lire_dxf.py` · `lire_scan.py` | Les lecteurs : PDF de dessin, Visio, DXF, scan |
| `composants.py` | Le socle commun des lecteurs : la règle « une boîte, un repère », les lectures confondues, la comparaison à la base |
| `releve.py` | Variante hors Google : archive les relevés dans des fichiers locaux |

```bash
npm run test:import      # les dix batteries de ce dossier
```

## 0. Porter tout cela sur le poste : `paquet.py`

La messagerie d'entreprise mange les pièces jointes de code, le Drive
personnel est fermé, et le dépôt n'est pas toujours joignable. D'où un seul
fichier qui passe partout :

```bash
python3 import/paquet.py
```

Il écrit `suivi-fwd-outils.py.txt` : tout le dossier compressé **dans un
programme Python**. Sur le poste, une seule commande — et **rien à
renommer**, Python se moque de l'extension :

```
python suivi-fwd-outils.py.txt
```

Le dossier `suivi-fwd` apparaît, et le programme dit les trois commandes qui
comptent. Refabriqué sans changement, le paquet est identique à l'octet près :
on voit donc tout de suite ce qui a bougé.

## 1. D'abord : l'essai à blanc

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


## 2. Préparer Chrome (une seule fois)

> **⚠ Débrief 26 — à revoir avant toute automatisation.** Depuis Chrome 136,
> l'option `--remote-debugging-port` est ignorée sur le profil habituel : il
> faut un profil à part (`--user-data-dir=…`), dans lequel on se connecte une
> fois à GATES et à SEE ([annonce de Chrome](https://developer.chrome.com/blog/remote-debugging-port)).
> « Le profil reste le vôtre », plus bas, n'est donc plus vrai. Et le dépôt
> par `deposer.py` → `doPost` demande une application web ouverte à « Tout
> le monde » : à abandonner au profit d'un dossier Google Drive synchronisé.
> Le plan d'automatisation du débrief 26 reprend tout cela.

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

## 3. Écrire la recette, une fois

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

## 4. Déposer dans le classeur

Le classeur peut publier une petite adresse qui reçoit les extracts. Dans
`Code.gs`, renseigner un secret :

```js
DEPOT: { SECRET: 'une phrase longue et imprévisible', MAX_LIGNES: 20000 },
```

puis **Déployer → Nouveau déploiement → Application web**, exécutée en votre
nom. **Attention à l'accès** : `deposer.py` n'a pas de compte Google, il
ne passe que si l'application web est ouverte à « Tout le monde ». Or c'est
la même application que le tableau de bord : l'ouvrir ainsi mettrait la
page, et l'extract entier, sur internet sans connexion. Tant que le dépôt
automatique reste « pour plus tard » (AU-BUREAU), ne pas l'activer ; le
jour venu, il faudra une solution à part, à décider avant. Copier l'adresse obtenue dans
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

## 5. La semaine, d'un seul geste

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

## 6. Les composants d'un plan, quel que soit le format

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

## 7. La variante hors Google : `releve.py`

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

## 8. Le transport par la messagerie

La passerelle mail retient ce qui ressemble à du code. `empaqueter.py` le rend
méconnaissable (gzip puis base64), `decoder.py` le reconstruit et vérifie son
empreinte :

```bash
python3 import/empaqueter.py Javascript.html -o import/Javascript.html.gz.b64.txt
python3 decoder.py Javascript.html.gz.b64.txt
```

## 9. Le robot au quotidien (débrief 31)

Les raccourcis du dossier « Robot Suivi FWD », sur le Bureau :

| Raccourci | Ce qu'il fait |
|---|---|
| **0 - Tout oublier (recommencer les exports)** | Le robot oublie tous les exports appris, les noms GATES qu'il avait retenus et ceux qui avaient marché la dernière fois. Il demande d'abord (o/n). Rien n'est effacé : les exports sont rangés dans `exports-oublies\<date>` (avec une copie de `robot.json`). Il garde ses connexions, l'adresse du tableau de bord, le navigateur, son heure et son lancement automatique. Puis il dit la suite : **2 - Apprendre** → 1 (GATES, sur un seul contrat, en tapant son nom exact dans GATES : « HDK AA »), **2 - Apprendre** → 2 (SEE), **3 - Essayer** |
| **1 - Preparer (une seule fois)** | Les connexions (Google, CHILDNéo, SEE). Il montre aussi l'adresse du tableau de bord qu'il utilise : Entrée pour la garder, ou collez la bonne (le lien qui finit par `/dev`, voir plus bas). Après les connexions, il ouvre la fenêtre d'import et dit ce qu'il y voit (sa « Livraison », les contrats) |
| **2 - Apprendre un export** | GATES (un contrat suffit) ou SEE. Pour GATES, il lit les fiches du tableau de bord : le nom tapé (« HDK AA ») est reconnu sans question, et il écrit, contrat par contrat, ce qu'il tapera chaque jour |
| **3 - Essayer** | Il refait tout devant vous, sans déposer |
| **4 - Activer (tout seul, une fois par jour)** | Chaque jour, à partir de 14 h |
| **Changer l'adresse du tableau de bord** | Montre l'adresse que le robot utilise, demande la nouvelle (Entrée = la garder), accepte `/dev` ou `/exec` (une `/exec` avec un avertissement : chaque « Nouveau déploiement » en a une autre). Puis il ouvre aussitôt la fenêtre d'import à cette adresse et dit sa « Livraison » et, pour chaque contrat, ce qu'il tapera dans GATES (une page de connexion Google : se connecter dans la fenêtre du robot, puis Entrée pour relire) |
| **Lancer maintenant** · **Etat du robot** · **Desactiver le lancement automatique** · **Choisir le navigateur (Chrome ou Edge)** | Comme avant. **Etat du robot** liste les exports appris (pour qui, appris quand, sur quel nom), ce qu'il a lu du tableau de bord la dernière fois, et signale une adresse `/exec` |

**Ce que le robot a lu.** En tête de chaque passage (et dans `journal.txt`) :

```
Tableau de bord lu : https://script.google.com/…/dev?page=import — Livraison cd9cd8e
Contrats lus dans le tableau de bord :
  HDK → tape « HDK AA »
  THS → tape « THS AA »
  NEO → tape « NEO AA » (prévu, nouvel onglet)
  VRK → tape « VRK AA » (deviné : à écrire dans sa fiche pour être sûr)
```

Le nom tapé vient de la **fiche** du contrat (tableau de bord → Administration → Contrats), qui l'emporte toujours. Sans nom dans la fiche : pour le contrat sur lequel GATES a été appris, ce qu'on a tapé ; pour les autres, ce que le robot avait retenu ; sinon il le devine sur le modèle appris (« HDK AA » appris sur HDK → « THS AA », jamais pour une tranche), et le dit ; sinon le nom du contrat. Le remplacement se fait en une fois : jamais « THS AA AA ».

**Le lien /dev : l'adresse qui ne change jamais.** Chaque « Nouveau déploiement » d'Apps Script a sa propre adresse `/exec`, qui reste sur la version de ce déploiement. Nathan en fait un à chaque livraison : le robot, qui gardait la première adresse, voyait une ancienne version (ni les noms GATES des fiches — il tapait « THS » au lieu de « THS AA » —, ni les contrats ajoutés, et son compte rendu n'arrivait pas). Le lien de **test** finit par `/dev` : projet Apps Script → **Déployer → Tester les déploiements → « Application Web »** → copier. Il montre toujours le dernier code *enregistré* à son propriétaire (le navigateur du robot est connecté avec le compte de Nathan) : on le donne une fois au robot (**Changer l'adresse du tableau de bord**), et l'on peut ensuite créer autant de liens qu'on veut pour soi. Tout marche pareil par `/dev` : la fenêtre d'import (`…/dev?page=import`), son cadre chez googleusercontent, le dépôt, le pont du compte rendu. Une adresse collée depuis la fenêtre d'import (`?page=import`), avec `#…` ou une barre finale, est nettoyée.

**« Le robot voit une ANCIENNE version du tableau de bord ».** Une fenêtre d'import sans pont du robot (`#pont-robot`) ou dont les cases GATES n'ont pas `data-contrat` est d'avant les fiches. Le robot le dit en tête de chaque passage, avec l'adresse et quoi faire : donner le lien `/dev` (ci-dessus). (Pour garder une adresse `/exec`, il reste **Déployer → Gérer les déploiements → crayon ✏️ → Version : « Nouvelle version » → Déployer**, sur ce déploiement-là ; débrief 31, relu : le robot ne le propose plus — Nathan fait un nouveau déploiement à chaque livraison, et ces mises à jour de lien « déconnent ».) Si l'adresse est déjà un `/dev`, c'est le code du projet qui est ancien : recoller la dernière livraison et enregistrer. Le robot doit écrire la même « Livraison » que le bas du tableau de bord (son compte rendu la porte, champ `livraison`, avec la sorte de son lien, champ `adresse` : `dev` ou `exec`). Sur un lien `/exec`, le tableau de bord avertit quand la livraison n'est pas la sienne (« ⚠ Le robot regarde une autre version du site… », avec le lien `/dev` à donner par « Changer l'adresse du tableau de bord ») ; sur `/dev`, il dit seulement « ◌ … il lira la dernière livraison à son prochain passage » (juste après une livraison, rien à faire). En automatique, une petite fenêtre le dit à la fin des passages du jour (une fois par jour au plus ; jamais entre deux essais) ; « Lancer maintenant » et « 3 - Essayer » le redisent à la fin de la fenêtre noire. Les lignes des contrats disent alors « fiche non lue ».

**« … plus ANCIENNE que lui (elle ne dit pas sa « Livraison ») ».** Débrief 31 (relu) : une fenêtre qui a le pont et les fiches, mais pas `data-livraison` sur `#pont-robot`, est d'avant le débrief 31 — un déploiement `/exec` du débrief 30. Le robot y lit les fiches, mais pas ce qui a changé depuis ; il le dit comme ci-dessus (jamais « ✓ Le robot voit le tableau de bord »), avec le même « quoi faire ». Le tableau de bord, lui, ne peut pas le savoir : c'est l'ancien code qui reçoit le compte rendu.

**Apprendre GATES en tapant le début du nom.** Débrief 31 (relu) : taper « HDK A » puis cliquer la suggestion « HDK AA » est reconnu (le nom de la fiche, sans question) ; pour les autres contrats, le début tapé devient leur nom entier (« THS AA »), sinon GATES ne proposait que HDK. Sans nom GATES dans la fiche du contrat appris, le robot prend ce que GATES montrait (« HDK AA » dans « HDK AA — 634 plans ») : jamais « THS AB AA — … ».

**D'autres chemins vers « THS » au lieu de « THS AA » (débrief 31, fermés).** La fiche l'emporte toujours. Un nom retenu égal au nom du contrat (« THS » → « THS », réponse à la question d'avant le débrief 30) ne cache plus le nom deviné ; réapprendre GATES en tapant « HDK » seul efface l'ancien « HDK AA » retenu ; pour le contrat appris, ce qu'on vient de montrer passe avant ce qui était retenu ; un ancien export « GATES THS » resté à côté du modèle (fichier illisible au rangement) n'est jamais fait — il aurait déposé son fichier par-dessus celui du modèle, ou arrêté le passage ; avec une fenêtre d'avant, « HDK AA » tapé se reconnaît encore sans question (il commence par le nom d'un seul contrat, jamais une tranche). La lecture de la fenêtre ratée est dite (adresse et raison), jamais un repli muet. Aucune liste de contrats n'est gardée d'un jour à l'autre : elle est relue à chaque passage.

**Cliquer ailleurs pendant qu'il travaille** ne le gêne plus : sa page se croit toujours au premier plan (deux défenses, chacune suffit : Chrome garde le focus de la page — `Emulation.setFocusEmulationEnabled` —, et un script posé dans chaque page lui cache la perte du focus venue de l'extérieur, sans jamais arrêter un « blur » que le robot provoque lui-même en cliquant). Prouvé par `tests_robot.py` avec un vrai Chrome à l'écran (Xvfb) et une autre application qui prend le focus au milieu de l'export — entre « Ouvrir données MK2 » et « XLSX » (le menu se ferme), juste avant « Ouvrir données MK2 » (le bouton ignore un clic sans le focus), après le PSN de SEE (sa liste se ferme), ou une autre fenêtre du navigateur du robot qui passe devant : sans la parade l'export rate, avec il sort ; chacune des deux défenses suffit seule. Pendant « apprendre », seul Chrome garde le focus (aucun script dans la page).

**Une attente longue** dit son maximum, puis où elle en est chaque minute :

```
    (attente : « Données MK2… » grisé — j'attends jusqu'à 5 min)
    … toujours grisé (1 min)
    … toujours grisé (2 min)
```

**Le menu GATES qui ne s'ouvre pas (débrief 32).** Vous n'avez plus à ouvrir le menu GATES à la main : si « Données MK2 » ne se montre pas après le clic sur le menu, le robot rouvre le menu tout seul, et le dit dans sa fenêtre :

```
  1/6 cliquer (le menu qui ouvre « Données MK2 »)
    (« Données MK2 » ne s'est pas montré : le menu ne s'est pas ouvert, le robot essaie de le rouvrir)
      … essai 1 : la souris posée sur le menu
      … essai 2 : un nouveau clic sur le menu
    ✓ « Données MK2 » est là (essai 2) — le menu qui ouvre « Données MK2 » ne s'était pas ouvert du premier coup ; rouvert par : un nouveau clic sur le menu
  2/6 cliquer « Données MK2 »
```

Rien à réapprendre. S'il s'arrête quand même (« Le menu qui ouvre « Données MK2 » ne s'est pas ouvert, même après plusieurs essais… »), ouvrez ce menu vous-même dans GATES : s'il s'ouvre normalement et montre « Données MK2 », GATES a seulement mal répondu, relancez « 3 - Essayer » (en automatique, le robot réessaie seul plus tard) ; si « Données MK2 » n'y est plus, refaites « 2 - Apprendre un export ».

Pour qui reprend le code : après un clic, la suite doit être là ET visible — pas seulement posée dans la page, transparente, non affichée, coupée par un menu replié ou rangée hors de l'écran (« caché ») ; sinon le robot rouvre le menu (les six façons ci-dessus, numérotées, le bouton retrouvé à neuf avant chaque essai ; un bouton qui n'a pas l'air d'un menu : la souris posée dessus puis un seul nouveau clic, jamais plus), au bout de quelques secondes de page calme, 15 s au plus même si la page fait des requêtes en fond. Une suite absente ou sous un voile ne fait recliquer qu'un bouton qui a l'air d'ouvrir un menu ; un bouton ordinaire (« Afficher »), le robot l'attend comme avant. Jamais recliqués : ce qui envoie ou calcule (« Submit », « Valider », « OK », « Enregistrer »…), une connexion (« Se connecter », « Sign in »…), « Page suivante », une case à cocher, ce qui fait venir le fichier (« XLSX », « Télécharger »…), un clic qui a mené à une autre page (même un peu plus tard), un bouton lui-même sous un voile. Ce qu'on va cliquer reste caché (le menu s'est refermé) : menu rouvert au bout de 15 s ; au bout du délai, une erreur claire avec quoi faire, au lieu d'un clic à l'aveugle. Le journal note chaque menu rouvert. Chaque export part d'une page rechargée et calme (« la page se charge ») ; une adresse de départ qui ne diffère que par son « #… » est rechargée aussi (ce n'est pas le cas de l'adresse GATES de Nathan) ; une page qui demande « Quitter la page ? » ne bloque plus le robot. Une liste qui a sa propre barre de défilement défile pour montrer la ligne à cliquer. Un élément sans nom appris désormais garde aussi d'autres indices (texte caché court, texte d'une image, titre d'un dessin, une classe à lui) ; les exports appris avant restent valables tels quels. Essais : `tests_robot.py`, « Débrief 32 » et « Débrief 32, relecture » (des pages comme GATES servies en local, HDK puis VRK dans le même onglet).


# Au bureau : tout installer, pas à pas

Ce document est fait pour être suivi **au bureau, dans l'ordre, sans rien
savoir d'autre**. Chaque étape dit quoi taper, ce qui doit apparaître, et quoi
faire si ce n'est pas ce qui apparaît.

Il y a **trois chantiers indépendants**. Aucun n'empêche les autres :

| # | Chantier | Durée | Ce que ça donne |
|---|---|---|---|
| 1 | Le mail à l'informatique | 5 min | Débloque la suite. **À faire en premier : la réponse met des jours.** |
| 2 | Le tableau de bord dans le classeur | 5 min | La page, sur vos vraies données |
| 3 | La fiche de votre vrai extract | 10 min | Ce qu'il me faut pour régler le reste |

Si le temps manque : **1, puis 3.** Le chantier 2 peut attendre demain.

---

## Chantier 1 — Le mail à l'informatique (5 minutes, à faire en premier)

Trois autorisations, trois délais. Elles ne coûtent rien à demander et
bloquent tout si on s'y prend tard. Un seul mail :

> Objet : Demande d'autorisation — outil de suivi d'avancement (3 points)
>
> Bonjour,
>
> Je mets en place un outil de suivi de l'avancement des plans d'intégration
> électrique, pour mon équipe. Il n'installe aucun exécutable. Trois points
> demandent votre accord :
>
> 1. **Lancer Chrome avec l'option `--remote-debugging-port=9222`.** C'est une
>    option officielle de Chrome, qui ouvre un canal **local** (127.0.0.1)
>    permettant à un script de rejouer une extraction que je fais aujourd'hui
>    à la main. Aucune donnée ne sort du poste, aucun logiciel n'est installé.
>
> 2. **Installer des paquets Python avec `pip`.** Ce sont des bibliothèques de
>    code Python, pas des exécutables. Concrètement : `numpy`, `pillow`,
>    `opencv-python-headless`, `rapidocr-onnxruntime`. Elles servent à lire les
>    plans, **hors ligne**, une fois installées.
>
> 3. **Déployer un script Google Apps Script en application web**, dans mon
>    espace Google professionnel, accessible **à moi seul**. Il sert à déposer
>    automatiquement les extracts dans mon classeur.
>
> Je peux détailler chaque point ou faire une démonstration.
>
> Merci d'avance,

**Envoyez-le avant de commencer le reste.**

---

## Chantier 2 — Le tableau de bord dans le classeur

Le tableau de bord tient en **quatre fichiers**, dont un de 222 Ko : personne
ne recopie cela à la main, et une pièce jointe de code se fait manger par la
passerelle mail. D'où les deux plans.

*(Les outils Python, eux, sont déjà arrivés : un seul fichier,
`suivi-fwd-outils.py.txt`, qui se déballe tout seul — voir le chantier 3.
C'est le tableau de bord, et lui seul, qui demande ce qui suit.)*

### Le plan A — le chargeur (3 gestes, 5 minutes)

**Un seul fichier à coller, et rien d'autre.** Pas de manifeste à modifier,
pas d'API à activer. Ce fichier ne contient pas le tableau de bord : il va le
chercher sur le dépôt **au moment où on l'ouvre**, et le fait tourner. C'est
Google qui télécharge, depuis ses serveurs — le réseau de l'entreprise n'est
pas concerné.

1. Dans le classeur : **Extensions → Apps Script**.
2. Dans `Code.gs`, **tout effacer**, coller `Chargeur.gs.txt`, **Ctrl + S**.
3. Recharger le classeur (**F5**) → menu **Suivi FWD** → **Ouvrir le tableau
   de bord**. Autoriser quand Google le demande.

Le menu offre aussi **Diagnostic** (ce que le script voit du classeur) et
**Recharger le code** (après une mise à jour de ma part).

Depuis l'éditeur, la fonction **`verifier`** dit en trois lignes si la page,
le serveur et le classeur répondent — sans rien ouvrir.

| Ce qui s'affiche | Quoi faire |
|---|---|
| « Le dépôt a répondu 404 » | La branche a changé de nom : me le dire |
| « Le dépôt a répondu 403 / délai dépassé » | Google n'a pas joint le dépôt → **plan C** |
| Le menu n'apparaît pas | F5. Sinon : Apps Script → fonction `onOpen` → ▶ |
| La page s'ouvre sur la démonstration, bordée de tirets | Normal tant qu'aucun onglet de contrat n'est rempli : voir « Ce que vous verrez » |

**Première ouverture : 3 à 5 secondes** (il lit 280 Ko sur le dépôt). Ensuite
c'est immédiat : il garde le code six heures.

---

### Le plan B — l'installateur (20 minutes, pour poser le code pour de bon)

À faire **plus tard**, quand l'outil aura fait ses preuves : au lieu d'aller
chercher le code à chaque ouverture, il l'**écrit dans le projet**. La page
s'ouvre alors instantanément, et ne dépend plus d'aucun réseau.

#### A.1 — Ouvrir l'éditeur de script

1. Ouvrir le **classeur Google Sheets** qui portera le tableau de bord (un
   classeur neuf convient).
2. Menu **Extensions → Apps Script**. Un nouvel onglet s'ouvre.
3. À gauche, il y a déjà un fichier **`Code.gs`**. **Ne pas y toucher.**

#### A.2 — Créer le fichier de l'installateur

1. À gauche, à côté de « Fichiers », cliquer le **`+`** → **Script**.
2. Le nommer exactement : **`Installateur`** (sans extension, Apps Script
   ajoute `.gs` tout seul).

   > ⚠️ **Ne pas coller l'installateur dans `Code.gs`.** `Code` est le nom d'un
   > des fichiers à installer : l'installateur s'effacerait lui-même au milieu
   > de son travail. Il le détecte et refuse, mais autant ne pas y aller.

3. Effacer tout ce qu'il y a dedans et **coller le contenu de
   `Installateur.gs.txt`** (reçu dans la conversation ; il est aussi dans le
   dossier `apps-script/` du paquet déballé).
4. **Ctrl + S** pour enregistrer.

#### A.3 — Ouvrir le manifeste et y mettre les permissions

1. À gauche, l'icône **⚙ Paramètres du projet**.
2. Cocher **« Afficher le fichier manifeste appsscript.json dans l'éditeur »**.
3. Retour à l'éditeur (icône `<>`), le fichier **`appsscript.json`** est
   apparu. Cliquer dessus, tout effacer, et coller **exactement** ceci :

```json
{
  "timeZone": "Europe/Paris",
  "dependencies": {},
  "exceptionLogging": "STACKDRIVER",
  "runtimeVersion": "V8",
  "oauthScopes": [
    "https://www.googleapis.com/auth/spreadsheets.currentonly",
    "https://www.googleapis.com/auth/script.container.ui",
    "https://www.googleapis.com/auth/script.scriptapp",
    "https://www.googleapis.com/auth/script.external_request",
    "https://www.googleapis.com/auth/script.projects"
  ]
}
```

4. **Ctrl + S**.

#### A.4 — Activer l'API Apps Script (une seule fois, pour toujours)

1. Ouvrir dans un autre onglet : **https://script.google.com/home/usersettings**
2. Mettre **« API Google Apps Script »** sur **ACTIVÉ**.
3. Attendre une minute — le temps que Google s'en aperçoive.

> **Si l'interrupteur est grisé** : c'est l'administrateur qui l'a fermé.
> → rester au **plan A**, ou passer au **plan C**.

#### A.5 — Lancer l'installation

1. Revenir sur l'onglet Apps Script.
2. En haut, dans la liste déroulante des fonctions, choisir **`installer`**.
3. Cliquer **▶ Exécuter**.
4. Google demande une autorisation :
   **Examiner les autorisations** → choisir votre compte →
   *« Google n'a pas validé cette application »* → **Paramètres avancés** →
   **Accéder à « … » (non sécurisé)** → **Autoriser**.

   > Ce message est normal : il s'affiche pour tout script personnel non
   > publié sur le magasin Google. C'est **votre** script, dans **votre**
   > compte.

5. En bas, le **journal d'exécution** s'ouvre et affiche :

```
1. Lecture du projet actuel…
   3 fichier(s) déjà présent(s) : appsscript, Code, Installateur
2. Téléchargement du code depuis le dépôt…
   Code.gs — 68 Ko
   Index.html — 12 Ko
   Styles.html — 44 Ko
   Javascript.html — 217 Ko
3. Écriture dans le projet…
   écrits : Code, Index, Styles, Javascript
   gardés : appsscript, Installateur

TERMINÉ. Il reste deux gestes :
```

6. **Recharger le classeur (F5).** Après quelques secondes, un menu
   **« Suivi FWD »** apparaît à côté de « Extensions ».
7. **Suivi FWD → Ouvrir le tableau de bord.** Une nouvelle autorisation est
   demandée la première fois : accepter, de la même façon.

#### A.6 — Si ça coince

| Ce qui s'affiche | Ce que ça veut dire | Quoi faire |
|---|---|---|
| « L'API Apps Script n'est pas activée » | L'étape A.4 n'a pas pris | Refaire A.4, attendre 1 min, relancer |
| Le même message, et l'interrupteur est grisé | L'administrateur l'a fermé | **Plan A** ou **plan C** |
| « Autorisation refusée » (401) | Le manifeste n'a pas les 5 permissions | Refaire A.3, relancer, réautoriser |
| « Le projet est introuvable » (404) | L'API vient d'être activée | Attendre 1 minute, relancer |
| « Le dépôt a répondu 403 / délai dépassé » | Google n'a pas pu joindre GitHub | **Plan C** |
| « Cet installateur est dans un fichier nommé Code » | Collé au mauvais endroit | Refaire A.2 avec le bon nom |
| Le menu « Suivi FWD » n'apparaît pas | Le classeur n'a pas été rechargé | F5. Si rien : Apps Script → fonction `onOpen` → Exécuter |

**Pour mettre à jour plus tard** : rouvrir Apps Script, fonction `installer`,
▶ Exécuter. C'est tout.

---

### Le plan C — à la main (15 minutes, marche toujours)

À utiliser si Google ne peut joindre le dépôt ni à l'ouverture (plan A) ni à
l'installation (plan B). Ici, **c'est vous** qui apportez les fichiers.

#### B.1 — Récupérer les quatre fichiers

1. Sur le PC, ouvrir Chrome et aller à :
   **https://github.com/martinnathan980-prog/gold-orb/tree/claude/javascript-gzip-base64-decoder-v0yr1m**
2. Bouton vert **Code** → **Download ZIP**.
3. Dans **Téléchargements**, clic droit sur le ZIP → **Extraire tout**.
4. Les fichiers sont dans `gold-orb-…\gates-analytics\` :
   `Code.gs`, `Index.html`, `Styles.html`, `Javascript.html`.

> **Si GitHub est bloqué** : dites-le-moi, je vous envoie les quatre fichiers
> directement dans la conversation, en `.txt`. C'est ainsi que vous avez reçu
> `suivi-fwd-outils.py.txt` : rien ne dépend d'un site à joindre.

#### B.2 — Les coller un par un

Dans l'éditeur Apps Script (Extensions → Apps Script) :

| Fichier du ZIP | Dans Apps Script | Comment |
|---|---|---|
| `Code.gs` | fichier **`Code`** | il existe déjà : tout effacer, coller |
| `Index.html` | **`Index`** (HTML) | `+` → **HTML**, nommer `Index` |
| `Styles.html` | **`Styles`** (HTML) | `+` → **HTML**, nommer `Styles` |
| `Javascript.html` | **`Javascript`** (HTML) | `+` → **HTML**, nommer `Javascript` |

Pour chacun : ouvrir le fichier du ZIP avec le **Bloc-notes**, **Ctrl + A**,
**Ctrl + C**, puis dans Apps Script **Ctrl + A**, **Ctrl + V**, **Ctrl + S**.

> ⚠️ Les noms doivent être **exactement** ceux de la colonne du milieu, sans
> extension : Apps Script ajoute `.gs` ou `.html` tout seul. Une majuscule
> oubliée et la page ne se construit pas.

> ⚠️ Un fichier HTML créé par `+ → HTML` arrive avec un squelette
> (`<!DOCTYPE html>…`). **Tout effacer** avant de coller.

`Javascript.html` fait 222 Ko : le Bloc-notes met deux ou trois secondes à
l'ouvrir, et Apps Script autant à l'enregistrer. C'est normal.

#### B.3 — La suite est la même

Recharger le classeur (F5) → menu **Suivi FWD** → **Ouvrir le tableau de
bord** → autoriser.

Avec le plan B, le manifeste n'a pas besoin d'être touché : Apps Script déduit
les permissions du code.

---

### Ce que vous verrez, et ce qui est normal

Au premier lancement, le classeur est vide : la page **s'ouvre sur la
démonstration** — trois contrats fictifs (HDK, THS, VRK), le graphique, le
journal, et le rapprochement avec la seconde base en deux cercles. Le bandeau
du haut le dit, et l'alerte à côté dit ce qui manque au classeur. C'est toute
la page, telle qu'elle sera avec vos données.

L'interrupteur **Données réelles / Exemple**, en haut, fait passer de l'une à
l'autre. « Données réelles » sur un classeur vide montre une page sans plan,
avec le message qui l'explique : c'est normal.

Pour la nourrir : exporter un contrat depuis GATES, ouvrir un onglet du
classeur, le nommer du nom du contrat (`HDK`), **Ctrl+A, Suppr**, cliquer en
**A1** et coller. Rouvrir le tableau de bord : il est sur vos plans. Puis
**Suivi FWD → Diagnostic** : la page dit ce qu'elle a compris de vos colonnes.
**Ce texte-là m'intéresse énormément** — c'est lui qui me dira si le modèle
de colonnes tombe juste.

Pour le rapprochement avec SEE : un onglet nommé **`SEE`**, et l'extract
« Nommage WD BFLOW » collé dedans en A1. Rien d'autre à configurer : l'onglet
est reconnu par son nom, et les deux cercles apparaissent sous le tableau.

---

## Chantier 3 — La fiche de votre vrai extract (10 minutes)

C'est **le plus utile des trois pour moi**. Tout le reste (le motif des
repères, les états d'avancement, le nom des colonnes) est aujourd'hui deviné.

### C.1 — Vérifier Python

Touche **Windows**, taper `cmd`, **Entrée**. Puis :

```
python --version
```

- Un numéro s'affiche (`Python 3.11.5`) → **c'est bon**.
- « n'est pas reconnu » → essayer `py --version`, puis `python3 --version`.
  Si aucun ne répond, Python n'est pas installé : passer ce chantier et me le
  dire.

### C.2 — Récupérer les outils : un seul fichier

Le fichier **`suivi-fwd-outils.py.txt`** contient tout le dossier
d'automatisation, compressé — et c'est lui-même un programme Python. Le
mettre dans **Téléchargements**, puis :

```
cd %USERPROFILE%\Downloads
python suivi-fwd-outils.py.txt
```

**Rien à renommer** : Python se moque de l'extension. Un dossier `suivi-fwd`
apparaît, avec les 30 fichiers dedans, et le programme affiche les trois
commandes qui comptent.

> Si seul `diagnostic.py` vous intéresse, il est aussi fourni seul, en
> `diagnostic.py.txt` : il se lance tel quel, sans renommage, lui aussi.

### C.3 — Exporter un contrat depuis GATES

Un seul contrat suffit. Peu importe le format : **.xlsx ou .csv**, les deux
se lisent.

### C.4 — Lancer la fiche

```
cd %USERPROFILE%\Downloads
python suivi-fwd\import\diagnostic.py extract-HDK.xlsx
```

(en remplaçant `extract-HDK.xlsx` par le vrai nom du fichier ; avec des
guillemets s'il contient des espaces)

Si le classeur a plusieurs onglets et que ce n'est pas le premier qui
compte :

```
python suivi-fwd\import\diagnostic.py extract-HDK.xlsx --onglet "Nom de l'onglet"
```

### C.5 — Ce qui s'affiche

```
FICHE D'EXTRACT — extract-HDK.xlsx
==================================================================

Format lu    : classeur Excel (.xlsx), onglet « Extract »
Lignes       : 1 482 au total, dont 1 480 plans
Colonnes     : 138
En-tête      : les intitulés sont ligne 2, les groupes ligne 1

LES COLONNES QUI COMMANDENT LE TABLEAU DE BORD
------------------------------------------------------------------
  la référence du plan     colonne 2    « Référence UD »
  l'avancement suivi       colonne 42   « Avancement » (groupe « Réalisation FWD »)
  …

LES VALEURS RÉELLES DE LA COLONNE D'AVANCEMENT   (la question nº 1)
------------------------------------------------------------------
  1 203 plans renseignés sur 1 480 — 277 cellule(s) vide(s)
  6 valeur(s) distincte(s) :
      100
      En cours
      …
```

Et il écrit **`fiche-extract-HDK.txt`** à côté de l'extract.

### C.6 — Ce que vous me renvoyez

**Le fichier `fiche-extract-HDK.txt`**, tel quel.

Ce qu'il contient : les **intitulés** des colonnes, des **comptes**, et les
valeurs **courtes** (20 caractères au plus) des colonnes à petit vocabulaire —
un avancement, un domaine, un ATA.

Ce qu'il ne contient pas : **aucun libellé**, aucun commentaire, aucun texte
libre, **aucune ligne entière**.

**Relisez-le avant de l'envoyer.** Et s'il y a le moindre doute :

```
python suivi-fwd\import\diagnostic.py extract-HDK.xlsx --anonyme
```

remplace chaque valeur par sa **forme** (`TFE2130A600001A` devient
`AAA9999A999999A`). La fiche reste utile : c'est la forme qui m'intéresse.

### C.7 — Si ça coince

| Ce qui s'affiche | Quoi faire |
|---|---|
| `python n'est pas reconnu` | Essayer `py` à la place de `python` |
| `Fichier introuvable` | `dir` pour voir les noms ; mettre le nom entre guillemets s'il a des espaces |
| `est un vieux classeur Excel (.xls)` | Ouvrir dans Excel → Enregistrer sous → `.xlsx` |
| `n'est pas un vrai .xlsx` | Le fichier est un `.csv` renommé, ou abîmé : réexporter |
| `Aucun onglet « … »` | Le message liste les onglets réels : reprendre le bon |
| Une erreur en anglais avec `Traceback` | **Me l'envoyer entière** : c'est un défaut de mon côté |

---

## Et aussi, si le temps le permet

### L'essai à blanc (10 minutes, sans intranet)

Il y a un faux GATES qui tourne sur le PC, pour apprendre la chaîne sans
risque. Depuis le dossier déballé à l'étape C.2 :

```
cd %USERPROFILE%\Downloads\suivi-fwd
python import\essai.py --jouer
```

Chrome se lance tout seul, cherche trois contrats, télécharge trois CSV, et
lit un plan d'essai. Sans `--jouer`, la même commande affiche la marche à
suivre avec les vrais gestes.

### Les trois choses que j'attends de vous

Par ordre d'utilité :

1. **`fiche-extract-*.txt`** (chantier 3) — débloque le modèle de colonnes.
2. **Un vrai plan**, un par format que vous rencontrez (PDF de dessin, Visio,
   DXF, scan). Même moche, même mal scanné.
3. **Vingt à trente vrais repères électriques**, recopiés tels qu'ils sont
   écrits sur un plan, en disant lesquels sont des connecteurs, des colis
   bendit, des raccords. Le motif que j'utilise aujourd'hui est **inventé** :
   c'est le maillon faible de toute la chaîne des composants.

Et, si vous passez par l'onglet du classeur : **le texte du Diagnostic**
(menu Suivi FWD → Diagnostic).

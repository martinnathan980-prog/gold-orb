# Des milliers de documents, une barre de recherche, Gemini — le mode d'emploi

> Trois questions, trois réponses :
>
> - **Où stocker autant de documents ?** Dans un **Drive partagé** du
>   service, rangé par pôle. Le **classeur Google** (celui que le site lit
>   déjà) en est le catalogue, rempli automatiquement.
> - **Comment les faire lire à Gemini ?** Tout de suite, avec le Gemini
>   que vous avez au travail : **« Demander à Gemini » dans Drive** et des
>   **carnets NotebookLM** par thème. Aucune installation.
> - **Comment la barre de recherche devient le portail pour tout lire ?**
>   Elle trouve déjà *le* document. Pour qu'elle dise aussi *ce que dit*
>   le document, sur tout le fonds, il faut **Gemini Enterprise** (la DSI)
>   et une petite page Apps Script, déjà écrite dans ce dépôt.
>
> Faits vérifiés le 26 septembre 2026 sur la documentation Google. Les noms
> de produits et les tarifs changent souvent : revérifiez avant de vous
> engager. Ce qui n'a pas pu être vérifié est signalé **(à confirmer)**.

```
                    ┌──────────────────────────── Drive partagé « ETII — Fonds documentaire »
                    │                              ETIIA/  ETIIE/  ETIII/  Commun/
                    │                                │  (les fichiers, et les droits)
                    │                                ▼
   index-documents.gs  ──▶  Classeur des documents (un onglet par pôle)
   (chaque nuit)            Titre · Référence · Type · Lien · Porteur…
                                     │
                                     ▼
   Portail ETII Hub — Recherche  « routage harnais »  ──▶  la fiche + « Ouvrir ↗ »  ──▶  le document dans Drive
                              │                                                           └─ « Demander à Gemini » (partie 2)
                              └─ « Demander à Gemini ↗ »  ──▶  page Assistant (partie 3)
                                                              └─ Gemini Enterprise lit le Drive partagé
                                                                 avec VOS droits, répond, cite les documents
```

---

## 0. Deux précautions avant tout

1. **Le contrôle export.** Un document d'ingénierie électrique hélicoptère
   peut relever des biens à double usage (règlement UE 2021/821) ou de
   l'ITAR/EAR. Faites valider par le référent conformité **quels dossiers**
   Gemini peut lire avant d'y mettre des documents réels. Un dossier
   exclu reste simplement hors du Drive partagé indexé.
2. **Jamais de clé API personnelle, jamais d'outil grand public.** Tout ce
   qui suit passe par le compte Google de l'entreprise, dans le cadre du
   contrat du groupe. Le site ne contient aucune clé et n'en contiendra
   jamais.

---

## 1. Ranger — aujourd'hui, sans la DSI

### 1.1 Le Drive partagé

Un **Drive partagé** (et non « Mon Drive ») : les fichiers appartiennent au
service, pas à une personne. Quand quelqu'un part, rien ne disparaît. Un
Drive partagé contient jusqu'à **400 000 éléments** (fichiers et dossiers) :
des milliers de documents y tiennent largement.

Dans Drive : **Drives partagés › Nouveau** › « ETII — Fonds documentaire ».

```
ETII — Fonds documentaire
├── ETIIA/
│   ├── Guides/
│   ├── Notes techniques/
│   ├── Procédures/
│   ├── Retours d'expérience/
│   └── Formations/
├── ETIIE/      (même découpage)
├── ETIII/      (même découpage)
└── Commun/     (ce qui vaut pour tout le service)
```

Le nom du **premier sous-dossier** devient le **Type** du document dans le
portail (étape 1.3) : choisissez des noms que vous voulez voir dans le
filtre « Type ».

**Les droits** : partagez avec des **groupes Google** (un par pôle), pas
personne par personne.

| Rôle Drive | À qui |
|---|---|
| Lecteur | tout le service |
| Contributeur | les référents qui déposent des documents |
| Gestionnaire | deux personnes, pas plus |

### 1.2 Des fichiers que Gemini lit bien

- **Un nom normalisé**, la référence d'abord :
  `ETII-TEC-001_indice-C_routage-harnais.pdf`. Le script de l'étape 1.3 lit
  la référence dans le nom (le début, jusqu'au premier `_` ou à la
  première espace).
- **Du texte, pas une image** : un PDF exporté depuis Word ou Docs est lu
  entièrement ; un PDF scanné sans reconnaissance de texte est mal lu.
- **Un document = un sujet.** Un « guide complet » de 400 pages répond à
  tout, donc mal. De plus, Gemini Enterprise n'indexe qu'une partie du
  texte d'un très gros fichier (partie 3.1).
- **Une seule version en vigueur dans le dossier.** Les versions périmées
  vont dans un dossier `Archives/` **hors** du Drive partagé indexé, sinon
  Gemini peut citer l'ancienne règle.

### 1.3 Le catalogue : le classeur des documents, rempli tout seul

Le site lit déjà le classeur des documents : un onglet par pôle (ETIIA,
ETIIE, ETIII), colonnes Titre, Référence, Type, Métier, Porteur,
Périmètre, Mise à jour, Lien… (voir `INSTALLER-SUR-GOOGLE.txt`, étape 9).
Pour des milliers de fichiers, un script le remplit à votre place.

1. Ouvrez le classeur des documents › **Extensions › Apps Script**.
2. **+ › Script**, nommez-le `index-documents`, collez tout le contenu de
   `tools/apps-script/index-documents.gs`.
3. En haut du fichier, dans `DOSSIERS_POLES`, collez l'identifiant du
   dossier de chaque pôle (dans l'adresse du dossier, ce qui suit
   `/folders/`).
4. Choisissez la fonction **`indexerDocuments`** › **Exécuter**. La
   première fois, Google demande l'autorisation de lire Drive et d'écrire
   dans le classeur : acceptez.
5. Des milliers de fichiers ? Le script s'arrête proprement vers 5 minutes
   (la limite d'Apps Script est de 6) et **se relance tout seul** une
   minute plus tard jusqu'à la fin. Le bilan est dans **Exécutions**.
6. Une fois : exécutez **`planifierChaqueNuit`**. Chaque nuit vers 6 h, les
   nouveaux fichiers sont ajoutés.

Ce que le script fait et ne fait pas :

- il **ajoute** une ligne par nouveau fichier (Titre, Référence, Type,
  Mise à jour, Lien) ;
- il **ne modifie ni n'efface jamais** une ligne existante. Ce que vous
  complétez à la main (Métier, Porteur, Description, Mots-clés) reste ;
- il reconnaît un fichier déjà listé par son identifiant Drive dans la
  colonne Lien, même si vous avez changé son titre dans le classeur.

Complétez ensuite **Métier, Porteur et Mots-clés** au fil de l'eau, en
commençant par les documents les plus demandés : la recherche du portail
tolère les fautes de frappe, mais elle ne trouve que ce qui est écrit.

### 1.4 Vérifier dans le portail

Ouvrez le site › **Recherche** : les documents apparaissent, filtrables par
pôle, type, métier. Chaque fiche a **« Ouvrir ↗ »**, qui ouvre le fichier
dans Drive, avec les droits de la personne.

---

## 2. Faire lire à Gemini — aujourd'hui, avec votre Gemini au travail

Aucune installation : c'est le Gemini inclus dans Google Workspace.

### 2.1 « Demander à Gemini » dans Drive — sur tout un dossier

1. Dans Drive, ouvrez le Drive partagé ou un dossier (ETIIA/Guides…).
2. En haut à droite, **Demander à Gemini** (l'étoile).
3. Posez la question : *« Quelle distance minimale entre un faisceau de
   puissance et un faisceau signal ? Cite le document et la page. »*
4. Gemini répond en citant les fichiers ; cliquez pour ouvrir la source.

Gemini ne lit que ce que **vous** avez le droit d'ouvrir. Il peut aussi
travailler sur un seul document, depuis son panneau latéral, une fois le
document ouvert depuis le portail (« Ouvrir ↗ »).

Limite à connaître : Google ne publie pas combien de fichiers d'un dossier
Gemini lit à chaque question, et une réponse peut ne s'appuyer que sur une
partie du dossier. Posez des questions précises, dans le bon sous-dossier.

### 2.2 L'application Gemini — comparer quelques documents

Dans Gemini, tapez **@** puis choisissez des fichiers Drive (jusqu'à
**10 fichiers** par question) : *« @guide-routage @note-blindage : ces deux
documents sont-ils cohérents sur la séparation des faisceaux ? »*

### 2.3 NotebookLM — un carnet par thème, partagé avec le pôle

Pour un corpus que tout le monde interroge (« Règles de conception
harnais », « Normes CEM », « Accueil des nouveaux ») :

1. Ouvrez NotebookLM (renommé « Gemini Notebook » en 2026) › **Nouveau
   carnet**.
2. **Ajouter des sources › Google Drive** : choisissez les documents du
   thème. Nombre de sources par carnet selon l'édition : 50 (standard),
   100 (Plus), 300 (Pro et Enterprise), 500 à 600 (Ultra) ; chaque source
   jusqu'à 500 000 mots ou 200 Mo.
3. **Partager** le carnet avec le groupe du pôle, en lecture.
4. Chaque réponse renvoie au **passage exact** de la source.

Quand un document change, vérifiez que la source du carnet est à jour.

**Mettre ces carnets dans le portail** : en mode Modifier, ajoutez à la FAQ
du pôle une question « Où interroger les règles harnais ? » avec le lien du
carnet. Le lien est rangé dans votre feuille Google, pas dans ce dépôt
public.

### 2.4 Ce que la partie 2 ne fait pas

Aucune de ces trois portes n'a d'interface de programmation : elles ne
peuvent pas répondre **dans** la barre du portail. Pour une seule question
posée à **tout** le fonds depuis le portail, il faut la partie 3.

---

## 3. La barre du portail qui répond — avec la DSI

### 3.1 Le produit : Gemini Enterprise, relié au Drive partagé

**Gemini Enterprise** (ex-Agentspace) est différent du Gemini inclus dans
Workspace : c'est l'offre de recherche et d'assistant d'entreprise de
Google Cloud. Relié au Drive partagé par son **connecteur Google Drive**, il
lit les documents **avec les droits de chaque personne** : un stagiaire ne
recevra jamais un passage d'un document qu'il ne peut pas ouvrir.

Ce qu'il faut savoir sur le connecteur Drive :

- il est **fédéré** : il interroge Drive au moment de la question, avec
  l'identité Workspace de la personne. Il ne marche que dans la même
  organisation ;
- il se limite au **Drive partagé** choisi (ou à des dossiers) ;
- il n'indexe que le **premier Mo de texte** de chaque fichier. Les très
  gros PDF (au-delà d'environ 50 Mo ou 80 pages selon la documentation,
  **(à confirmer)** avec la DSI) ne sont pas lus. D'où « un document = un
  sujet » (1.2).

**Coût** (prix publics, en dollars, hors remise du groupe) : Gemini
Enterprise de **21 à 30 $ par personne et par mois** selon l'édition. Le
groupe a peut-être déjà un contrat : c'est la première question à poser.

### 3.2 Ce que la DSI fait — la liste à lui remettre

- [ ] Un **projet Google Cloud standard** du groupe, avec l'**API
      Discovery Engine** activée.
- [ ] Une **application Gemini Enterprise**, région **eu**, avec un
      **magasin de données Google Drive** limité au Drive partagé
      « ETII — Fonds documentaire ».
- [ ] Une **licence Gemini Enterprise** pour chaque membre du service qui
      l'utilisera.
- [ ] Pour ces personnes (un groupe Google), un rôle IAM qui porte la
      permission `discoveryengine.assistants.assist` sur le projet (par
      exemple « Discovery Engine User », **(à confirmer)**).
- [ ] L'écran de consentement OAuth du projet en **interne**, pour que le
      script de 3.3 puisse demander ses autorisations.
- [ ] En retour, deux informations pour vous :
      - le **numéro du projet** (pour relier le script) ;
      - le **nom complet de l'application**, de la forme
        `projects/123456789/locations/eu/collections/default_collection/engines/etii-docs`.

La DSI peut d'abord tester l'application dans l'interface web de Gemini
Enterprise : si les réponses y sont bonnes, la page 3.3 donnera les mêmes.

### 3.3 Ce que vous faites — la page « Assistant », 20 minutes

Le code est prêt dans `tools/apps-script/assistant/` : `Code.gs`,
`Page.html`, `appsscript.json`. C'est une **application à part** du site :
le site s'exécute « en tant que Moi » (il écrit dans votre feuille) ; un
assistant exécuté ainsi lirait les documents avec **vos** droits pour tout
le monde. Celui-ci s'exécute **au nom de la personne qui l'ouvre**.

1. Dans le navigateur : `script.new` › un nouveau projet Apps Script,
   nommé « Assistant documentaire ETII ».
2. **Paramètres du projet** (roue dentée) › cochez **Afficher le fichier
   manifeste « appsscript.json »**. Revenez à l'éditeur, ouvrez
   `appsscript.json`, remplacez tout par le fichier du dépôt.
3. `Code.gs` : remplacez tout par `tools/apps-script/assistant/Code.gs`.
4. **+ › HTML**, nommez-le exactement `Page`, collez `Page.html`.
5. **Paramètres du projet › Projet Google Cloud › Changer de projet** :
   le numéro fourni par la DSI.
6. **Paramètres du projet › Propriétés du script › Ajouter** :
   `GEMINI_APP` = le nom complet de l'application.
7. **Déployer › Nouveau déploiement › Application web** :
   - Exécuter en tant que : **Utilisateur accédant à l'application Web** ;
   - Qui a accès : **tous les utilisateurs de votre organisation**.

   Copiez l'adresse qui se termine par `/exec`.
8. Ouvrez cette adresse suivie de `?q=bonjour` : la première fois, Google
   demande votre accord (chaque personne le donnera une fois), puis la
   page répond.

**Relier le portail** (sur votre copie locale, jamais dans ce dépôt public) :

9. Dans `assets/js/assistant.js`, collez l'adresse `/exec` dans
   `SOURCE.url`.
10. `ETII_RACCORDE=1 node tests/audit.mjs`, puis
    `node tools/build-artifact.mjs`.
11. Dans Drive, **remplacez** le fichier `etii-hub.html` par le nouveau
    `dist/etii-hub.html` (clic droit › Gérer les versions › Importer une
    nouvelle version : l'identifiant reste le même, le site suit).

Le résultat : sur la page Recherche du portail, le bloc **« Demander à
Gemini ce que disent les documents »** reprend ce que vous tapez dans la
barre de recherche. **Demander à Gemini ↗** ouvre la page de l'assistant,
qui répond aussitôt, avec les **documents cités** (titre, page, extrait,
lien). Une question de suite garde le fil de la conversation.

### 3.4 La recette, avant d'annoncer quoi que ce soit

1. **Dix questions dont vous connaissez la réponse**, prises dans des
   documents différents. Notez : bonne réponse ? bon document cité ?
2. **Le test des droits** : un collègue qui n'a pas accès à un dossier pose
   une question dont la réponse n'est que dans ce dossier. Il ne doit
   **rien** en obtenir.
3. **Le test de la version** : une règle qui a changé d'indice. La réponse
   doit citer l'indice en vigueur.

Une réponse **sans document cité** est affichée comme non vérifiable :
c'est voulu.

### 3.5 Si ça ne marche pas

| Message de la page | Cause | Remède |
|---|---|---|
| « pas encore relié : la propriété GEMINI_APP est vide » | étape 6 oubliée | ajouter la propriété |
| « doit avoir la forme projects/… » | nom d'application incomplet | recopier le nom complet fourni par la DSI |
| « refuse l'accès (403) … licence … rôle » | pas de licence, ou pas le rôle IAM | DSI, liste 3.2 |
| « Application Gemini introuvable » | mauvais nom ou mauvaise région | vérifier `locations/eu` et l'identifiant |
| « Gemini n'a pas reconnu une question » | message trop court (« bonjour ») | poser une vraie question |
| Aucune autorisation demandée, erreur d'API désactivée | script non relié au projet | étape 5 |

---

## 4. Le plan, en clair

| Quand | Quoi | Qui |
|---|---|---|
| Semaine 1 | Drive partagé, dossiers, groupes, noms de fichiers (1.1, 1.2) | Vous |
| Semaine 1 | `index-documents.gs` : le catalogue se remplit (1.3) | Vous |
| Semaine 2 | Gemini dans Drive et deux carnets NotebookLM, présentés au service (partie 2) | Vous |
| Semaine 2 | Mesurer : combien de questions, combien de temps gagné | Vous |
| Semaine 3 | Chef de service, puis DSI : « avons-nous Gemini Enterprise ? » avec la liste 3.2 | Vous + chef |
| Ensuite | Conformité et RSSI : quels dossiers peuvent être lus | DSI pilote |
| Ensuite | Page Assistant (3.3), recette (3.4), puis ouverture au service | Vous |

**Qui voir, dans quel ordre** : votre chef de service (le mandat), la DSI
(ce qui existe déjà, le chemin agréé), la RSSI (le niveau de
confidentialité admis), le référent contrôle export, le DPO si des noms de
personnes figurent dans les documents, les achats (le porteur du budget).
Arriver avec les parties 1 et 2 qui fonctionnent déjà et un périmètre
écrit, c'est une discussion ; arriver avec une idée, c'est un « non ».

---

## 5. Les questions qu'on vous posera

> **« Et si Gemini invente ? »**
> Chaque réponse cite ses documents, et la page affiche une réponse sans
> source comme non vérifiable. La règle du service : on vérifie dans le
> document avant d'appliquer.

> **« Tout le monde va-t-il voir les documents restreints ? »**
> Non : Gemini Enterprise interroge Drive avec l'identité de chaque
> personne, et la page Assistant s'exécute au nom de celui qui l'ouvre.
> C'est vérifié en recette (3.4, test des droits).

> **« Nos documents servent-ils à entraîner le modèle ? »**
> Question pour la DSI, qui la tranche avec les engagements contractuels
> du groupe (Workspace et Google Cloud). Ne répondez pas à sa place.

> **« Pourquoi pas un simple export des PDF vers une IA ? »**
> Parce qu'une copie n'a ni droits d'accès, ni versions, ni traçabilité.
> Ici, les documents restent à un seul endroit, le Drive partagé ; tout le
> reste (catalogue, portail, Gemini) le lit.

> **« Combien de temps avant que ça marche ? »**
> Parties 1 et 2 : quelques jours. Partie 3 : l'essentiel du délai est la
> validation, pas la technique ; la page Assistant elle-même s'installe en
> vingt minutes.

---

### Les fichiers de ce dépôt

| Fichier | Rôle |
|---|---|
| `tools/apps-script/index-documents.gs` | Remplit le classeur des documents depuis le Drive partagé (1.3) |
| `tools/apps-script/assistant/Code.gs` | L'assistant : pose la question à Gemini Enterprise au nom de la personne (3.3) |
| `tools/apps-script/assistant/Page.html` | La page de questions, réponses et documents cités |
| `tools/apps-script/assistant/appsscript.json` | Autorisations et mode d'exécution de l'assistant |
| `assets/js/assistant.js` | Le bloc du portail qui ouvre l'assistant, la question déjà posée |
| `tests/assistant-gemini.test.mjs` | Vérifie les deux scripts contre la forme de réponse documentée par Google |

Référence utilisée pour le format des appels : Gemini Enterprise, REST v1,
`projects.locations.collections.engines.assistants.streamAssist`, et la
ressource `AssistAnswer` (consultées le 26 septembre 2026).

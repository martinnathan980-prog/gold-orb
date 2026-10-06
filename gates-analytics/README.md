# Suivi FWD

Tableau de bord de l'avancement FWD des plans d'intégration électrique, à
poser dans un classeur Google Sheets. La mise en place et le geste
hebdomadaire sont dans **[MODE-D-EMPLOI.md](MODE-D-EMPLOI.md)** ; les règles, dans
**[PROCEDURE.md](PROCEDURE.md)**.

C'est un outil de **consultation** : la page montre, elle ne modifie rien.

## Ce qu'il y a dans ce dossier

| Fichier | Rôle |
|---|---|
| `Code.gs` | Serveur : contrats (un onglet visible chacun), modèle de colonnes, historique par contrat, jalons de configuration, lecture de la seconde base, et la fenêtre d'import des exports GATES et SEE (lus sur le poste, sans Excel : `.xlsx`, vrais `.xls` d'Excel 97-2003 et 95, `.csv`, pages web, pages web archivées `.mht`) |
| `Index.html` | Page ; elle injecte le premier contrat au rendu, sans aller-retour, et tend le pont `SUIVI_FWD_API.chargerContrat` pour les autres |
| `Styles.html` | Feuille de style |
| `Javascript.html` | Interface |
| `appsscript.json` | Manifeste (fuseau, portées OAuth) |
| `prototype/` | La même interface, autonome, avec une démonstration à trois contrats fictifs — c'est la source |
| `import/` | L'automatisation : pilote Chrome, recettes d'extraction, dépôt dans le classeur, lecture des composants sur les plans (PDF, Visio, DXF, scans), transport par la messagerie |
| `apps-script/` | Ce qu'on colle dans Apps Script : le **chargeur** (un fichier, qui va chercher le reste à l'ouverture) et l'**installateur** (qui écrit les quatre fichiers dans le projet) |
| `MODE-D-EMPLOI.md` | Ce qu'on fait dans le classeur, concrètement : importer les exports de la semaine, chacun dans sa case (ou les coller), un onglet par contrat, archiver la semaine, brancher SEE (un extract pour tous, trié par le PSN de chaque contrat), lire la page |
| `AU-BUREAU.md` | La marche à suivre, pas à pas, pour installer sur le poste de travail — et, pour plus tard, l'automatisation |
| `tests/` | Batterie de l'add-on (serveur + page rendue) ; `tests/xls/`, de vrais `.xls` écrits par LibreOffice, SheetJS et xlwt, et leur lecture par SheetJS (l'oracle de la fenêtre d'import) |

## Une seule interface, deux sources

`prototype/suivi-fwd.html` est **la** version de l'interface. Elle tourne seule
sur une démonstration (trois contrats fictifs), ce qui permet de la montrer et
de la tester sans classeur. Quand elle trouve `window.SUIVI_FWD_DONNEES` posé
dans la page, elle s'alimente à la place sur le classeur — et sur lui seul :
la construction retire la démonstration des fichiers de l'add-on, et un
classeur vide affiche « Le classeur n’a pas encore de plans », jamais des données fabriquées.

`Styles.html`, `Javascript.html` et `Index.html` en sont **dérivés** :

```sh
npm run build        # redécoupe le prototype en fichiers Apps Script
```

Ne jamais modifier les trois fichiers dérivés à la main : la modification se
ferait perdre au découpage suivant. Tout passe par le prototype (et par
`tests/Index.modele.html` pour l'enveloppe d'`Index.html`).

## Ce que la page montre

- **Un bandeau tout en haut** avec le sélecteur de **contrat** quand le
  classeur en a plusieurs ; le titre, seul ; puis, à droite de la phrase
  d'avancement, le **périmètre** (Tout, puis une puce par domaine —
  `BASE/OPTION`, `PERSO`…) qui pilote toute la page.
- **L'avancement du jour** : barre et états, lus dans **une seule colonne**,
  `HDK AA 011 > Avancement Définition Electrique` (ou le concept harnais du
  même bloc) — introuvable, la page le dit en haut et n'en lit aucune autre ;
  le pied de page nomme la colonne suivie.
- **La courbe dans le temps**, avec les jalons de configuration, une bulle
  qui résume chaque semaine en chiffres, cadrée à l'ouverture jusqu'à la
  semaine qui suit la dernière échéance, et dessous le **journal** de ce qui a
  changé, semaine par semaine — un tableau, une colonne par sorte de
  passage (passés validés, reculs en rouge, **changements d'indice** : le
  même plan réémis sous un autre indice, retrouvé par la racine de sa
  référence UD, nouveaux, disparus) —, plan par plan. En haut, « À
  surveiller » : les plans en cours qui n'ont pas bougé depuis six semaines.
  Un seul rythme, le rythme tenu.
- **Avancement FWD par…** : par ATA, Séquence, CC, ECP ou mois de création,
  rangé par nom (ATA 21, 24, 25…), avec la fin estimée et le rythme requis
  par le prochain jalon ; un filtre sur la colonne de gauche, et sous chaque
  ligne toutes ses références, une sous-liste par valeur (Validé, En cours,
  À faire…).
- **La vie d'un plan** : un clic sur une référence, n'importe où, et son
  historique s'ouvre au-dessus du tableau — relevé après relevé, d'un indice
  à l'autre.
- **La vue d'ensemble des contrats**, depuis le bandeau : une ligne par
  contrat, avec les chiffres de sa propre page.
- **La comparaison des bases de données** (GATES et SEE), dès qu'un onglet
  `SEE` est là, sous le tableau. Un plan connu de SEE est un plan créé, donc
  validé : la section croise cette présence avec l'avancement de GATES. Deux
  cercles face à face, l'anneau des plans en commun dans leur recouvrement,
  six verdicts en français — validés et dans SEE, autre indice, dans SEE mais
  pas validés ici, validés absents de SEE, pas encore dans SEE, seulement
  dans SEE — qui filtrent le tableau, puis **plan par plan** : un groupe par
  verdict dans l'ordre des priorités, tous repliés à l'ouverture,
  et un clic sur une référence la montre dans le tableau ; derrière
  l'interrupteur GATES | SEE, l'onglet SEE à l'identique (trois colonnes
  s'il a été importé par le menu) avec le verdict sur chaque ligne.
- **Le tableau** : l'extract GATES à l'identique — toutes les colonnes, les
  mêmes intitulés, l'ordre de la feuille (la colonne suivie figée juste après
  la référence) — en deux vues seulement,
  *Toutes les colonnes* et *Vue essentielle*. Seule exception : la **première**
  colonne quand elle est sans intitulé et entièrement vide (« Colonne 1 » sur
  l'export réel, ajoutée par Excel). Les autres colonnes sans intitulé restent,
  même vides.
- **L'automatisation**, dans `import/` : un pilote qui parle à Chrome sans rien
  installer, des recettes d'extraction rejouables, un dépôt qui envoie
  l'extract au classeur (lequel archive le relevé de la semaine), et un
  lecteur de plans PDF qui retire les composants de leurs boîtes.

## Tests

```sh
npm install
npm test
```

- `npm run test:addon` — 567 tests. Le vrai `Code.gs` tourne dans Node contre
  un classeur en mémoire (`tests/faux-classeur.js`), sur un export
  volontairement pénible : lignes de titre, groupes fusionnés, en-têtes
  accentués ou dupliqués, ligne vide au milieu, avancements de toutes les
  formes — puis sur la vraie structure à 138 colonnes de l'export GATES
  (`tests/feuille-gates.js`). La page qu'Apps Script rendrait est ensuite
  chargée dans un vrai navigateur et comparée aux comptes du serveur. Couvre
  aussi : feuille vide, feuille sans colonne d'avancement, historique
  corrompu, 4 000 plans, jalons de configuration hostiles, deux contrats
  (archivage, suppression, diagnostic, ancien onglet d'historique orphelin,
  changement de contrat dans la page, panne du classeur), périmètre dérivé
  des cartes plan par plan, seconde base à rapprocher, et le dépôt
  automatique (secret absent ou refusé, corps illisible, onglet d'historique
  protégé, archivage de la semaine — même quand `getDocumentLock()` rend
  null, comme en application web —, réponse JSON de `doPost`), et l'export
  identique à un relevé plus ancien : refusé le vendredi, archivé du menu
  après « Oui ». Et la colonne
  suivie : `HDK AA 011 > Avancement Définition Electrique` sur la vraie
  structure, nommée dans le pied de la page ; introuvable, aucune autre n'est
  lue à la place, la page le dit en haut et l'archivage refuse.
- `npm run test:import` — 308 tests en Python : le paquet qui se déballe tout seul (fabriqué, lancé, et chaque fichier vérifié octet pour octet) ; la fiche d'extract (classeurs .xlsx fabriqués à la main, CSV de tous encodages, détection de l'en-tête et des groupes, confidentialité de la fiche) ; l'essai à blanc (un faux GATES joué de bout en bout dans un vrai Chrome) ; le pilote Chrome (canal
  WebSocket écrit à la main, gestes, téléchargements, erreurs lisibles) joué
  contre un vrai Chrome ; la lecture des recettes ; le dépôt joué contre un
  faux classeur qui répond comme le vrai — y compris quand il refuse ; et les
  lecteurs de plans, joués sur des plans fabriqués pour l'occasion : PDF de
  dessin (boîtes, repères dedans ou à côté, flux compressé, coordonnées
  transformées, cas douteux), Visio (groupes, gabarits, connecteurs, deux
  pages, vieux XML), DXF (polylignes, quatre traits, blocs et attributs,
  unités), et scans — l'image sortie de chaque emballage de PDF (JPEG,
  télécopie CCITT, pixels bruts, lignes PNG, LZW), les boîtes trouvées sans
  lire une lettre, puis les repères lus pour de vrai par RapidOCR et corrigés
  par la liste de la base, sur papier gris et page couchée. Sans Chrome ou
  sans RapidOCR sur le poste, ces parties-là sont sautées en le disant.
- `npm run test:import-see` — 328 tests sur la fenêtre d'import (menu Suivi
  FWD → Importer les exports GATES et SEE…) : la vraie fenêtre, rendue par le
  vrai `Code.gs`, ouverte dans un vrai navigateur, `google.script.run`
  branché sur le serveur en mémoire. Une case par export (débrief 21) :
  « GATES HDK » par contrat, « Ajouter un contrat… », une case SEE pour
  l'extract de tous les porteurs ; chaque fichier posé ou glissé dans sa
  case, sa sorte vérifiée à sa ligne d'en-têtes par les règles du serveur,
  rien de deviné. L'essai clé : la vraie structure GATES (138 colonnes, 16
  cellules fusionnées), importée en `.xlsx`, donne le même onglet que le même
  export collé, et `construireModele`, `getDonneesPourClient`,
  `compterAvancements` y lisent la même chose — aussi depuis un vrai `.xls`
  (écrit par LibreOffice et par xlwt : les mêmes valeurs, les mêmes fusions),
  une page web archivée (`.mht` nommé `.xls`), une page web nommée `.xls`
  (colspan, rowspan), du XML 2003, ou un CSV (sans fusion : la fenêtre
  prévient). Les vrais `.xls` : ceux de `tests/xls/` (LibreOffice, dont un
  export SEE de 3 200 lignes, un fichier protégé par un mot de passe et
  l'export GATES chiffré avec le mot de passe par défaut d'Excel ;
  SheetJS en Excel 97-2003, 95 et 2 ; xlwt), lus cellule par cellule comme
  les lit SheetJS, un lecteur indépendant (l'oracle,
  `tests/xls/oracle.json.gz`, refait par `tests/preparer-xls.js`) ; et ceux
  de `tests/fabriquer-xls.js`, écrits octet par octet : chaque façon
  d'écrire une cellule, des textes partagés coupés en plein caractère, en
  pleine mise en forme ou en pleine phonétique, secteurs de 4 096 octets
  mélangés, mini-flux, DIFAT, calendrier 1904, formats, onglets graphiques,
  de macros, masqués, un graphique posé dans l'onglet, lignes dans le
  désordre, Excel 95 en page de codes 850, un flux sans conteneur, formules
  d'Apple Numbers, texte vide sans octet d'options, émojis coupés entre deux
  enregistrements, noms locaux de « General » ; un `.xls` chiffré avec le
  mot de passe par défaut d'Excel (« VelvetSweatshop » : LibreOffice, et RC4
  d'Excel 97 ou CryptoAPI 40 et 128 bits fabriqués, vérifiés une fois par
  msoffcrypto-tool) lu comme en clair ; les refus (protégé par un vrai mot
  de passe, tronqué, chaîne ou répertoire qui boucle, document Word, Excel 2
  à 4, `.xlsb`, trop gros, fichier vide, dossier compressé) ; et 60 000
  lignes lues sans que la fenêtre se fige — en `.xls` comme en page web
  archivée de 70 à 90 Mo.
  Puis les cases : l'export d'un autre contrat posé dans la case de HDK
  (prévenu, jamais déplacé : « seulement 3 plans sur 186 en commun »), le
  nouveau contrat nommé d'après ses groupes, son nom vérifié et sa place,
  le même fichier dans deux cases (la date de chaque fichier), GATES puis
  SEE pour deux contrats, deux tours dans la même fenêtre (la liste des
  contrats relue). Le tri de l'extract SEE : le PSN comparé en entier (4530
  n'est ni 14530 ni 45301, aux virgules, points-virgules et espaces),
  DIAGRAM TYPE « WD » à la casse et aux espaces près, deux contrats et deux
  PSN tirés d'un seul fichier, un PSN tapé recompté sans relire le fichier,
  enregistré et retrouvé à la réouverture, un PSN refusé, vidé, celui d'un
  nouveau contrat gardé une fois créé, un contrat sans PSN sans base, une
  colonne du tri qui manque (« importer sans ce tri »), « toutes » sur
  l'extract trié, 60 000 lignes triées sans figer la fenêtre, l'extract
  collé à la main trié par la page à la lecture, et les lignes du
  Diagnostic. Et le deuxième contrat qui fait renommer « SEE » et l'ancien
  historique au nom du premier, la fin d'un import qui refuse sans le
  verrou, le relevé archivé contrat par contrat et ses refus, un import
  GATES interrompu (l'ancien onglet, ses
  fusions et son historique intacts ; un nouveau contrat jamais créé à
  moitié), les restes d'un import jamais pris pour des contrats, la case
  « toutes » changée pendant une lecture. Et tout l'import SEE d'avant ; les
  fichiers sont fabriqués pour l'occasion (`tests/fabriquer-xlsx.js`,
  cellules fusionnées comprises) : chaînes partagées ou en ligne,
  chaînes riches et lecture phonétique, formats (dates 1900 et 1904, heures,
  zéros de tête, décimales, pourcentages, milliers, scientifique, monnaie),
  préfixes d'espace de noms, cellules sans référence, descripteurs de
  données, Zip64, plusieurs onglets, CSV Windows-1252, UTF-16 ou à accent
  tardif, tout entre guillemets, faux `.xls` en HTML ou en XML 2003 (même
  après 64 Ko de styles, CDATA compris), une formule calculée vide ; la
  garde hors du classeur et le jeton, la case de chaque contrat et l'onglet créé,
  un lot qui échoue une fois (renvoyé, sans doublon), une panne qui dure
  (l'ancienne base reste), un refus jamais renvoyé, la réponse de fin
  perdue, un import incomplet,
  deux imports en même temps, une fenêtre fermée en plein envoi (le reste
  signalé puis retiré), un classeur au bord des dix millions de cellules, un
  vrai `.xls` nommé `.xlsx` (lu), un fichier protégé ou chiffré, tronqué
  ou abîmé au milieu, une formule
  sans valeur, et 120 000 lignes sur 24 colonnes suivies de liens.
- `npm run test:chargeur` — 34 tests sur le chargeur : un faux Apps Script en
  mémoire (classeur, UrlFetchApp qui sert le dépôt depuis le disque, cache,
  menus, fenêtres), le vrai `Chargeur.gs` lancé dedans, et la page qu'il
  fabrique ouverte dans un vrai navigateur — les états, les colonnes, le
  graphe et le journal comparés au paquet du classeur.
- `npm run test:interface` — 817 tests sur l’interface elle-même.
  Elle n'essaie pas seulement de vérifier que ça marche : recherches avec
  balises, expressions régulières, 3 000 caractères ou émoji, jalon de
  configuration au texte injecté, `localStorage` corrompu puis inaccessible,
  zoom et déplacement extrêmes, sept largeurs d'écran, clavier seul, contraste
  dans les deux thèmes ; la légende de la barre à huit valeurs, le parseur
  de références UD sur quinze formes, les changements d'indice, le périmètre
  (PERSO + BASE/OPTION = Tout, point par point), les trois contrats de la
  démonstration, le rapprochement aux écarts délibérés. Toute erreur
  JavaScript remontée par la console fait échouer le lot.
- `npm run test:chiffres` — l'audit des chiffres, indépendant de la page :
  pour chaque contrat, chaque avancement et chaque périmètre, il recalcule
  depuis la source brute, avec ses propres formules, les comptes par état,
  la courbe, le rythme tenu, la fin estimée, le rythme requis et les plans à
  l'arrêt, et les compare à ce que la page affiche — sur la démonstration et
  sur la page servie par le vrai `Code.gs` (301 vérifications : la démonstration ne donne plus de jalons qu’à HDK). Il vérifie
  aussi que la page classe chaque valeur exactement comme le serveur.

Les deux lots se lancent séparément ; chacun affiche à la fin
« N test(s) réussi(s), M échec(s) ». `CHROMIUM_PATH` force un binaire Chromium
précis si celui de Playwright n'est pas installé.

## Le parti pris

**L'historique s'accumule, il ne se reconstitue pas.** L'export GATES est une
photo du jour : il ne dit pas quand un plan est passé à 100 %. Un relevé est
donc archivé à chaque import, un par semaine ISO et par contrat, et rien n'est
jamais supprimé ni réécrit. Ce que la page montre sous un périmètre est
**dérivé** à la lecture des cartes plan par plan archivées, jamais recalculé
dans l'onglet.

**Quatre états, pas trois.** « À faire » est une valeur saisie ; une cellule
vide est un défaut de saisie. Les confondre masquerait le second.

**Un plan garde son identité quand il est réémis.** Une référence UD, c'est une
racine fixe, puis un indice et une révision qui bougent. Comparer par la racine
évite qu'une réémission passe pour un disparu plus un nouveau.

**Le rythme est mesuré, pas lissé.** La saisie est irrégulière — une semaine un
lot entier, la suivante rien. Une moyenne glissante mesurerait surtout la date
du dernier lot. On prend donc la cadence moyenne depuis le premier relevé, et
le bouton « ? » de la colonne *fin estimée* refait le calcul avec les chiffres
de la ligne, pour que personne n'ait à faire confiance sur parole.

**Tout le monde regarde la même chose.** Pas de colonnes à choisir, pas de
jalons à déplacer : ce qui se partage (jalons, contrats, seconde base) est dans
la configuration et le classeur, et seule la mise en page reste locale.

**Aucun nom de colonne en dur.** Tout se déduit de l'en-tête et du contenu. Si
l'export change de colonnes, il n'y a rien à modifier.

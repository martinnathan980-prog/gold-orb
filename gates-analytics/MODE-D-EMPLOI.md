# Mode d'emploi — le classeur, semaine après semaine

Ce document dit **ce que vous faites, physiquement, dans le classeur**, une
fois le tableau de bord installé (menu **Suivi FWD** visible dans le classeur).
Rien ne se saisit dans la page : le classeur est la mémoire, la page est la
lecture.

En une phrase : **un onglet par contrat, l'extract GATES collé dedans tel
quel, et une fois par semaine « Archiver le relevé »**. Le reste est
automatique.

---

## 1. Ouvrir le tableau de bord

1. Ouvrir le classeur Google Sheets. Le menu **Suivi FWD** est à droite de
   « Aide » (s'il manque : **F5**, attendre dix secondes).
2. **Suivi FWD → Ouvrir le tableau de bord.** À la première ouverture, Google
   demande une autorisation : Autoriser, choisir votre compte, « Autoriser »
   encore.
3. La page s'ouvre dans une fenêtre. Tant que le classeur est vide, elle
   le dit — **« Le classeur est vide »** — et rappelle les trois gestes
   ci-dessous. Elle ne montre jamais rien de fabriqué : seulement vos
   données.

### Recoller une livraison (quand je vous envoie les fichiers)

Le tableau de bord tient en **quatre fichiers**, et ils vont **ensemble** :
`Code`, `Index`, `Styles`, `Javascript`. À chaque livraison, **recollez les
quatre**, même si un seul semble avoir changé : un fichier laissé à la
livraison d'avant suffit à laisser la page blanche.

1. Extensions → Apps Script. Pour chacun des quatre fichiers : l'ouvrir à
   gauche, **Ctrl+A, Suppr**, puis coller le `.txt` du même nom **en entier**
   (dans le `.txt` : Ctrl+A, Ctrl+C), **Ctrl+S**.
2. **Si vous ouvrez la page par un lien `…/exec`** (application web) : ce lien
   sert la version *déployée*, pas celle que vous venez de coller. Déployer →
   Gérer les déploiements → ✏️ → Version : **Nouvelle version** → Déployer.
   Le menu Suivi FWD → Ouvrir le tableau de bord, lui, prend toujours le code
   enregistré.
3. Vérifier : **en bas de la page, « Livraison xxxxxxx »** — le numéro que je
   donne avec les fichiers. (Quand je ne corrige que `Code`, la livraison ne
   change pas : on ne recolle que `Code`.) Suivi FWD → **Diagnostic** le confirme :
   « ✓ Livraison xxxxxxx : Code, Index, Styles et Javascript concordent ».

Si un fichier ne concorde pas, **la page le dit elle-même**, en tête : « Les
fichiers du tableau de bord ne concordent pas. Index ne vient pas de la même
livraison… » ; et si elle ne peut pas s'afficher du tout, un cadre « La page
n'a pas pu s'afficher » (ou « n'a pas pu démarrer ») dit pourquoi et quoi
recoller — plus jamais un squelette vide sans un mot.

## 2. Mettre un contrat : l'extract GATES, dans un onglet

Un contrat = **un onglet** du classeur, qui porte **le nom du contrat**. Tout
le reste se déduit de là.

1. Dans GATES, exporter la liste du contrat en **Excel** (de préférence au
   CSV : l'export Excel garde les cellules fusionnées de la ligne des
   groupes, et c'est par le groupe « Réalisation FWD » que la page reconnaît
   la bonne colonne « Avancement » parmi les vingt-sept), l'ouvrir dans
   Excel.
2. Dans Excel : **Ctrl+A**, **Ctrl+C**. Tout l'extract, sans rien trier ni
   retirer : les lignes de titre au-dessus, la ligne des groupes, la ligne
   des en-têtes, les colonnes vides — tout reste tel quel.
3. Dans le classeur Google : pour le **premier** contrat, l'onglet de départ
   (« Feuille 1 ») fait l'affaire — double-clic sur son nom, le renommer du
   **nom du contrat**, par exemple `HDK`. Pour les suivants, **+** en bas à
   gauche, puis renommer de même. C'est ce nom que la page affichera. (Un
   onglet resté vide n'est pas pris pour un contrat.)
4. Cliquer la cellule **A1** de cet onglet, **Ctrl+V**. Attendre que Google
   finisse de coller (quelques secondes pour 138 colonnes).
5. Fermer la fenêtre du tableau de bord si elle est ouverte, et la rouvrir :
   **Suivi FWD → Ouvrir le tableau de bord.** La page est sur vos plans.

Ce que la page a compris de l'extract se lit dans **Suivi FWD → Diagnostic**
(les colonnes reconnues, le nombre de plans, la ligne « Avancement FWD :
colonne « … », groupe « Réalisation FWD » »). **Envoyez-moi ce texte** : c'est
lui qui me dit si le modèle de colonnes tombe juste. Le texte se copie à la
souris dans la boîte ; s'il est trop long, il est aussi dans **Extensions →
Apps Script → Exécutions**, dernière exécution de `diagnostic`.

À savoir :

- Le premier onglet (dans l'ordre des onglets, de gauche à droite) est le
  contrat sur lequel la page s'ouvre. On les réordonne en les faisant
  glisser.
- Un onglet **masqué** n'est pas un contrat, un onglet **vide** non plus. Les
  onglets `Historique_FWD_…` sont créés et masqués par l'outil : ne pas y
  toucher, ne pas les renommer.
- Un seul extract par onglet. Coller le même extract dans un second onglet
  donnerait deux « contrats » identiques.
- Si un jour l'extract change de colonnes et que le Diagnostic ne trouve
  plus le groupe « Réalisation FWD » après le collage : supprimer l'onglet
  (clic droit → Supprimer) et le recréer sous le **même nom**, puis coller.
  L'historique, nommé d'après l'onglet, est conservé.

## 3. Un deuxième contrat, un troisième

Même geste, dans un **nouvel onglet** nommé du nouveau contrat (`THS`). Dans
la page, un sélecteur **Contrat** apparaît dans le bandeau du haut dès qu'il
y a deux onglets ; il passe de l'un à l'autre sans recharger.

## 4. Chaque semaine : recoller, puis archiver

C'est le geste qui construit l'historique — la courbe, la fin estimée et le
journal des changements n'existent que par lui.

1. Refaire l'export GATES de chaque contrat.
2. Dans l'onglet du contrat : **Ctrl+A**, **Suppr**, cliquer **A1**,
   **Ctrl+V**. (Pour chaque contrat.)
3. **Suivi FWD → Archiver le relevé de cette semaine.** Une boîte confirme :
   « Relevé S39 archivé : HDK (186 plans), THS (93 plans). »

L'archivage passe sur **tous les contrats d'un coup** : une ligne datée de la
semaine dans l'onglet d'historique de chaque contrat (`Historique_FWD_HDK`,
créé et masqué tout seul au premier archivage). Refaire l'archivage dans la
même semaine **remplace** la ligne de la semaine, il n'en ajoute pas une
seconde. Une erreur de manipulation (mauvais extract collé) : **Suivi FWD →
Supprimer le relevé de cette semaine**, recoller le bon, archiver de nouveau.
Pour vérifier après coup : le pied du tableau de bord (« 3 relevés
archivés ») ou le Diagnostic (« Relevés archivés : 3 »).

**Coller écrase-t-il l'historique ?** Non. Coller remplace **l'extract** de
l'onglet du contrat — c'est voulu, l'onglet ne garde que l'état du jour.
L'historique, lui, est dans l'onglet masqué `Historique_FWD_HDK` : **une
ligne par semaine archivée**, que rien n'écrase, sauf un second archivage
dans la même semaine (il remplace la ligne de cette semaine-là). Le seul
piège : recoller un nouvel extract **avant** d'avoir archivé le précédent —
la semaine du précédent est alors perdue. Coller puis archiver dans la foulée
(ou laisser l'archivage du vendredi le faire) suffit. En attendant
l'archivage, la page compte déjà l'extract collé pour la semaine en cours, et
le pied le dit (« l'extract du jour, pas encore archivé, compte pour S39 »).

**L'archivage refuse** si la colonne suivie est introuvable dans un onglet
(« Colonne « HDK AA 011 > Avancement Définition Electrique » introuvable ») :
une semaine où tout serait « non renseigné » fausserait la courbe pour de bon.
Le Diagnostic dit alors où se trouve l'intitulé (voir § 7).

Pour ne plus y penser : **Suivi FWD → Activer l'archivage automatique
(vendredi 17 h)**, et Google prend le relevé chaque vendredi **entre 17 h et
18 h**, à partir de ce qui est dans les onglets à ce moment-là. Il faut donc
avoir recollé l'extract avant ; à ce rendez-vous-là, personne n'est devant
l'écran, aucune boîte ne s'affiche. Vérifier une fois, dans **Extensions →
Apps Script → ⚙ Paramètres du projet**, que le fuseau horaire est
Europe/Paris. « Désactiver l'archivage automatique » l'arrête.

### Rattraper une semaine passée (l'export gardé de côté)

Quand un relevé porte le mauvais export — par exemple S39 archivé avec
l'export de S40, les deux relevés identiques, donc aucun rythme — et que
l'export de cette semaine-là est encore sous la main :

1. Dans l'onglet du contrat (`HDK`) : **Ctrl+A**, **Suppr**, **A1**,
   **Ctrl+V** de l'export **de la semaine passée**. Rester sur cet onglet.
2. **Suivi FWD → Archiver l'onglet affiché pour une semaine passée…**,
   taper la semaine où l'export a été tiré de GATES : `S39` (ou `39`).
3. La boîte redit tout avant d'écrire : « Archiver l'export affiché dans
   « HDK » comme relevé S39 ? Il remplace le relevé S39 déjà archivé… » →
   **Oui**. Seul ce contrat est touché.
4. **Tout de suite** : recoller l'export **du jour** dans `HDK`, puis **Suivi
   FWD → Archiver le relevé de cette semaine**. Sinon l'archivage du
   vendredi prendrait l'export de S39 pour celui de la semaine en cours.

Une semaine à venir est refusée ; « S52 » tapé en janvier est celle de
l'année d'avant (la boîte écrit alors « S52 2025 »).

## 5. La seconde base, SEE : un onglet par contrat

Chaque contrat a sa propre base SEE, donc son propre onglet :

1. **+** pour un nouvel onglet, le nommer **`SEE` suivi du nom du contrat** —
   **`SEE HDK`** pour le contrat de l'onglet `HDK`, **`SEE THS`** pour `THS`
   (`SEE - HDK` ou `SEE_HDK` marchent aussi).
2. Ouvrir l'extract « Nommage WD BFLOW » **de ce contrat** dans Excel,
   **Ctrl+A**, **Ctrl+C**.
3. Dans l'onglet `SEE HDK`, **A1**, **Ctrl+V** — tel quel, titre en ligne 1 et
   en-têtes en ligne 3 compris.
4. Rouvrir le tableau de bord : chaque contrat se compare à sa base.

Avec **un seul contrat** dans le classeur, un onglet nommé `SEE` tout court
suffit. Avec plusieurs, un `SEE` tout court n'est lu pour aucun — il ne dit
pas à quel contrat il appartient : le **Diagnostic** le signale et donne le
nom à lui donner.

Sous le tableau des plans apparaît la section **Comparaison des bases de
données** : les deux cercles et, à leur droite, les verdicts — un clic sur
l'un d'eux déplie ses plans sous sa ligne. Au-dessus du tableau, l'interrupteur **GATES | SEE**
montre l'un ou l'autre extract. Rien à configurer : l'onglet est reconnu par
son nom (les en-têtes sont trouvés seuls, ligne 3 dans l'extract), et la
référence est recomposée à partir des colonnes NAME, SOL. et Cust.V — le A
du NAME, que SEE écrit un cran trop tôt (`TFE311A0600` pour le plan que
GATES appelle `TFE3110A600`), est décalé pour retrouver le plan dans GATES.

SEE n'a pas d'historique : la comparaison porte toujours sur l'extract qui
est dans l'onglet. On le recolle quand on en a un plus récent (Ctrl+A, Suppr,
A1, Ctrl+V), sans rien archiver.

### Si le collage rame

C'est Sheets qui peine sous le volume, pas le tableau de bord : aucun calcul
n'est déclenché par une saisie dans le classeur. Dans l'ordre d'efficacité :

1. **Coller les valeurs seules** — **Ctrl+Maj+V** au lieu de Ctrl+V. C'est le
   plus gros gain : sans la mise en forme qui vient d'Excel (polices, bordures,
   couleurs, largeurs), Sheets a bien moins à écrire.
2. **Vider pour de vrai avant de recoller** — sélectionner les lignes par leurs
   numéros à gauche, clic droit, **Supprimer les lignes**. Un simple **Suppr**
   efface le texte mais laisse les lignes et leur mise en forme, qui
   s'accumulent d'une semaine sur l'autre. Même chose pour les colonnes vides à
   droite de l'extract.
3. **Coller par paquets** de deux ou trois mille lignes plutôt que tout d'un
   coup : la fenêtre reste utilisable pendant ce temps.
4. **Ne garder que les colonnes utiles.** La comparaison n'en lit que trois :
   **NAME**, **SOL.** et **Cust.V**. Les autres ne servent qu'à regarder
   l'extract dans le tableau SEE. Si c'est trop lourd, ne coller que ces trois
   colonnes : la page dit exactement la même chose, en beaucoup plus léger.
5. **Onglet `SEE` nu** — pas de mise en forme conditionnelle, pas de filtre, pas
   de volet figé, et surtout aucune formule d'un autre onglet qui pointe dessus :
   elle se recalculerait à chaque collage.
6. **Si l'export existe en `.csv`** — onglet `SEE` sélectionné, Fichier →
   Importer → le fichier, puis **« Remplacer la feuille actuelle »**. Sheets
   lit un fichier bien plus vite qu'il n'avale un collage. ⚠️ Surtout pas
   « Remplacer la feuille de calcul » : celle-là remplace **tout le
   classeur**, contrats et historique compris.
7. Fermer les autres onglets Chrome lourds, et le tableau de bord pendant
   l'opération : il ne recalcule rien, mais il occupe la mémoire.

## 6. Lire la page, de haut en bas

- **Le bandeau**, à droite : dès deux contrats le lien **Vue d'ensemble**
  (une ligne par contrat : validés, reculs, rythme, plans à l'arrêt,
  prochaine échéance) et le sélecteur **Contrat**, et
  dessous l'interrupteur **Avancement : Définition électrique | Concept
  harnais** — les deux
  avancements du bloc HDK AA 011 ; toute la page suit celui qui est choisi,
  le titre aussi (« Suivi FWD » ou « Suivi concept harnais »). Sous le
  titre, la semaine où l'on est, et rien d'autre.
- **Le périmètre** : Tout / BASE/OPTION / PERSO — les valeurs de la colonne
  « Domaine » de l'extract, telles quelles. Il restreint toute la page.
- **En haut, sans titre** : la phrase « N sur M plans validés », la barre
  des valeurs de la colonne telles qu'elles sont écrites (Validé, Check, En
  cours, A traiter, non renseigné…) avec leur nombre, et **À surveiller** :
  les plans en cours qui n'ont pas bougé depuis 6 semaines ou plus, un clic
  les montre. Au début, il n'y en a aucun : il faut six semaines de relevés
  pour qu'un plan puisse être « à l'arrêt ». Au-delà de quatre valeurs, ou
  quand l'une est trop petite pour se voir (deux plans sur six cents), les
  valeurs passent en **légende** sous la barre ; survoler une case éclaire
  son segment. VALIDATED (« Validé ») compte comme validé — partout, la
  page dit « validés » ; une autre valeur qui voudrait dire validé se
  déclare dans `Code` (`VALEURS_FINIES`).
- **Avancement dans le temps** : la courbe des validés relevé après relevé,
  les jalons du programme (numérotés 1 à 5 sur une rangée, en clair dans la
  légende dessous), la fin estimée au rythme tenu et le rythme requis pour
  tenir le prochain jalon (« manque N » quand le rythme ne suffit pas). Il
  s'ouvre sur **Échéances** — jusqu'à la semaine qui suit la dernière
  échéance : les cinq jalons à l'écran — ; **Échéances · 3 mois · 6 mois ·
  1 an · Tout** à droite. Les jalons sont ceux de **HDK** ; **THS** n'en a
  pas (un autre contrat, d'autres dates, à venir) : sa page montre le rythme
  tenu et la fin estimée, sans échéance. Sous chaque jalon de la légende, son nom et sa
  semaine ; le reste (périmètre, jours) au survol et dans la fiche. En
  tête, la prochaine échéance en jours : un clic ouvre sa fiche (Échap la
  ferme). Les jalons **TO** (table outil) suivent le concept harnais : sous
  la définition électrique, ils restent dessinés, en retrait.
- **Ce qui a changé, semaine par semaine** : le journal — quels plans sont
  passés à VALIDATED, lesquels ont changé d'indice, lesquels sont apparus ou ont
  disparu de l'extract, et les **reculs**, en rouge. Les semaines forment un
  tableau : une colonne par sorte de passage, nommée dans l'en-tête, de la
  plus fréquente à la plus rare, la pastille et le nombre dans la case —
  tout tombe droit d'une semaine à l'autre. Dépliée, une ligne = une
  référence et son passage, sans libellé. Les semaines s'ouvrent repliées ; le petit champ
  « Chercher un plan… » à droite ne cherche que dans le journal.
- **Avancement FWD par…** (ou **Concept harnais par…**) : le même avancement découpé par ATA, séquence,
  CC, ECP, ou par mois de création, avec la fin estimée et le rythme requis
  (en plans par semaine, le rythme tenu dessous) par groupe, rangés par ATA
  dans l'ordre, chacun avec son chevron et, en ambre, ses plans **à
  l'arrêt** — en cours, sans changement depuis 6 semaines ou plus (le bloc
  le rappelle en tête).
  Un clic sur un groupe déplie ses plans **sur place**, sous sa ligne —
  les autres groupes restent là, comme les semaines du journal ; le reste
  de la page (phrase, courbe, tableau) suit ce groupe, un second clic le
  referme. Une sous-liste par valeur (VALIDATED, PWD_IN_PROGRESS…), chacune
  avec son compte. Son champ « ATA ou plan… » trouve un groupe ou un plan.
- **Plans** : l'extract, à l'identique, avec ses colonnes ; recherche, tri,
  filtres. « Vue essentielle » n'en garde qu'une poignée — référence, nom
  d'installation, ECP, ATA, séquence, validation définition électrique, date
  de création, avancement — celles de cette liste qui se retrouvent dans
  l'extract. Les cases à cocher se lisent Oui / Non. **Un clic sur une
  référence** — ici ou n'importe où dans la page — ne montre que ce plan, et
  ouvre au-dessus du tableau **sa vie** : une case par relevé, depuis quand
  il est dans son état, ses changements (reculs en rouge, changements
  d'indice en violet).
- **Comparaison des bases de données** (si l'onglet `SEE` est là) : ce que
  GATES dit validé et que SEE connaît, et les écarts — en cercles, et à
  droite six verdicts, une seule liste : un clic sur un verdict filtre le
  tableau et déplie tous ses plans sous sa ligne, en puces. Un clic sur une
  référence la montre dans le tableau ; le petit champ à droite du titre ne
  cherche que dans la comparaison. Elle n'existe que pour la définition
  électrique : SEE ne connaît pas le concept harnais.

## 7. Si quelque chose ne va pas

D'abord **Suivi FWD → Diagnostic** : il dit ce que le script voit, onglet par
onglet, et ce qui manque. Puis :

| Ce que vous voyez | Ce que ça veut dire | Quoi faire |
|---|---|---|
| Pas de menu « Suivi FWD » | Le script n'est pas chargé | F5 ; sinon Extensions → Apps Script, fonction `onOpen`, ▶ Exécuter (le menu ne dépend que du fichier `Code`) |
| « Ouvrir le tableau de bord » donne une erreur | Un fichier HTML manque ou est mal nommé | Diagnostic : il nomme le fichier (`Index`, `Styles`, `Javascript`) introuvable |
| La page reste **blanche** : le titre, des cadres vides, des tirets « — » | Le code de la page ne s'est pas lancé — le plus souvent un fichier resté à la livraison d'avant, ou coupé au collage (débrief 17) | Recoller **les quatre** fichiers de la dernière livraison (§ 1, « Recoller une livraison ») ; par un lien `…/exec`, publier une **nouvelle version** du déploiement. Les pages livrées depuis le 29 septembre le disent elles-mêmes en tête |
| En tête : « Les fichiers du tableau de bord ne concordent pas. **Index** ne vient pas de la même livraison… » | Ce fichier-là est resté à une autre livraison | Le recoller depuis la dernière livraison, Ctrl+S (et nouvelle version du déploiement pour un lien `…/exec`) |
| En tête : « La page n'a pas pu démarrer. Le fichier Javascript semble incomplet » | `Javascript` a été collé en partie (le fichier est long) | Dans `Javascript.html.txt` : Ctrl+A, Ctrl+C ; dans Apps Script : `Javascript`, Ctrl+A, Ctrl+V, Ctrl+S. Le Diagnostic dit « ✗ « Javascript » est incomplet » tant que ce n'est pas fait |
| En tête : « La page n'a pas pu s'afficher. Une erreur l'a arrêtée » | Une panne de la page elle-même | M'envoyer une capture du cadre (il ne cite aucune valeur du classeur) : le « Détail » me dit où chercher |
| En bas de la page, la livraison n'est pas celle que je vous ai donnée | Le lien `…/exec` sert encore l'ancienne version déployée | Déployer → Gérer les déploiements → ✏️ → Nouvelle version → Déployer |
| Une page « Le tableau de bord ne peut pas s'ouvrir : les fichiers collés ne tiennent pas ensemble » | Un fichier manque au projet (`Index`, `Styles` ou `Javascript`) | Elle nomme le fichier : + → HTML, le nommer exactement, y coller le `.txt` |
| Le Diagnostic dit « Javascript : 213 307 caractères » alors que le `.txt` en fait 300 000 | Normal : Apps Script compte les fichiers sans leurs commentaires | Rien à faire, tant qu'il dit « ✓ … concordent, et sont entiers » |
| « Le fichier Javascript contient deux copies » | Collé sans tout effacer (le neuf au-dessus de l'ancien) | `Javascript` : Ctrl+A, Suppr, coller, Ctrl+S |
| Au-dessus de la barre : « L'onglet d'historique « Historique_FWD_… » n'est rattaché à aucun contrat » | Un onglet de contrat renommé : ses relevés sont restés sous l'ancien nom. L'archivage est refusé d'ici là | Afficher les onglets masqués, renommer l'historique comme la page l'indique |
| « La colonne … est vide sur les N plans » | L'export collé n'a pas cette colonne remplie | Recoller un export complet ; l'archivage est refusé si la semaine d'avant en avait des valeurs |
| « L'onglet « THS » ne porte aucun plan (en-têtes seuls) » | Un onglet préparé d'avance | Y coller l'export du contrat ; en attendant, il n'est pas archivé |
| En bas : « Chiffres lus dans le classeur le vendredi… » | La page est ouverte depuis longtemps | Recharger la page avant de présenter |
| « Le classeur est vide », avec une alerte | Aucun onglet de données lisible : l'alerte dit pourquoi | « Aucune colonne d'avancement FWD n'a été reconnue » : l'extract est collé sans sa ligne d'en-têtes ou sa ligne de groupes → recoller entier en A1 ; « Aucun onglet de données exploitable : « Feuille 1 » est vide » : aucun onglet ne contient encore d'extract |
| En haut : « Colonne « HDK AA 011 > Avancement Définition Electrique » introuvable » | L'extract n'a pas cette colonne sous ce groupe (groupe renommé, bloc absent) : la page n'en lit **aucune autre** à la place, rien n'est dit validé, l'archivage refuse | Diagnostic : il liste les groupes où l'intitulé existe ; corriger le nom du groupe dans `COLONNE_FWD` (partie avant « > ») s'il a changé dans l'export |
| Pour vérifier la colonne lue | — | Le **pied de la page** la nomme : « Colonne suivie : HDK AA 011 › Avancement Définition Electrique » |
| « 0 sur 600 plans validés », et au-dessus de la barre « Aucun plan n'est compté « validé » » | Le mot qui veut dire « fini » dans la colonne n'est pas connu de la page (seul « Validé » l'est, avec « Validée », « Terminé », « OK », « 100 % »…) | La page liste les valeurs lues : m'envoyer celle(s) qui veulent dire « fini » (et « pas commencé »), je les ajoute à `VALEURS_FINIES` (et `VALEURS_A_FAIRE`) dans `Code` |
| « Ce qui a changé semaine par semaine » reste vide | Le journal dit pourquoi : un seul relevé (deux archivages la même semaine n'en font qu'un), ou deux relevés identiques — le même export archivé deux fois | Recoller le **dernier** export de GATES, puis archiver ; le Diagnostic dit combien de plans ont changé entre les deux derniers relevés |
| Pas de courbe, pas de fin estimée | Aucun relevé archivé | Suivi FWD → Archiver le relevé de cette semaine |
| Pas de section « Comparaison » | Pas d'onglet `SEE <contrat>` (ou `SEE` pour un seul contrat), ou illisible | Diagnostic, ligne « Seconde base » : elle dit s'il manque l'onglet, s'il est vide, ou si les en-têtes NAME / SOL. / Cust.V ne s'y trouvent pas |
| Un contrat en trop ou en moins | Un onglet visible en trop, ou masqué | Chaque onglet visible qui porte un export (Référence UD, ATA…) est un contrat ; un onglet « Notes » à côté est écarté tout seul (le Diagnostic le dit) |
| « N lignes répètent une référence déjà vue » au-dessus de la barre | L'export a été collé par-dessus l'ancien sans le vider : des lignes de l'ancien restent en dessous | Ctrl+A, Suppr, puis recoller l'export en A1 |
| Après avoir renommé un onglet de contrat, la courbe repart d'un seul relevé | L'historique porte encore l'ancien nom (`Historique_FWD_Feuille 1`) | Le Diagnostic le signale : renommer cet onglet d'historique `Historique_FWD_<nom du contrat>` |
| Sous le graphique : « S41 : identique au relevé d'avant (export pas recollé ?) » | L'archivage (celui du vendredi, souvent) a repris l'export de la semaine d'avant | Recoller le dernier export, puis archiver : le relevé de la semaine est remplacé |
| Deux relevés identiques alors que j'ai bien les deux exports | La semaine passée a été archivée avec l'export d'aujourd'hui | § 4, « Rattraper une semaine passée » : recoller l'export de la semaine passée, **Archiver l'onglet affiché pour une semaine passée…**, puis recoller l'export du jour et archiver |
| « Ce geste ne se lance que dans le classeur, menu Suivi FWD » | Quelqu'un a essayé d'archiver, supprimer ou couper l'archivage depuis la page (la console du navigateur) | Rien à faire : la page est en consultation, elle ne modifie rien. Ces gestes se font dans le classeur, menu Suivi FWD |
| THS n'a pas d'échéance | Voulu : les jalons livrés sont ceux de HDK | Me donner les dates de THS quand elles existent : je les ajoute dans `CONFIG.JALONS` avec `contrat: 'THS'` |

Et dans tous les cas : **le texte du Diagnostic** (copié à la souris dans la
boîte, ou pris dans Extensions → Apps Script → Exécutions) suffit pour que je
voie ce qui se passe.

## 8. Ce qu'il ne faut pas faire

- Renommer ou modifier les onglets `Historique_FWD_…` : c'est la mémoire.
- Retoucher l'extract collé (trier, supprimer des colonnes, renommer des
  en-têtes) : le tableau de la page doit être l'extract, et le modèle de
  colonnes se repère sur les en-têtes de GATES.
- Coller deux extracts dans le même onglet.

---

*Le reste — l'installation pas à pas, et plus tard l'automatisation des
extracts — est dans `AU-BUREAU.md`. Le détail de chaque règle est dans
`PROCEDURE.md`.*

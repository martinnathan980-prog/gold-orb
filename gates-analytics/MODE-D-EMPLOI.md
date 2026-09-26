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

C'est le geste qui construit l'historique — la courbe, la fin estimée, le
comparatif « depuis le dernier relevé » et le journal des changements
n'existent que par lui.

1. Refaire l'export GATES de chaque contrat.
2. Dans l'onglet du contrat : **Ctrl+A**, **Suppr**, cliquer **A1**,
   **Ctrl+V**. (Pour chaque contrat.)
3. **Suivi FWD → Archiver le relevé de cette semaine.** Une boîte confirme :
   « Relevé 2026-S39 archivé : HDK (186 plans), THS (93 plans). »

L'archivage passe sur **tous les contrats d'un coup** : une ligne datée de la
semaine dans l'onglet d'historique de chaque contrat (`Historique_FWD_HDK`,
créé et masqué tout seul au premier archivage). Refaire l'archivage dans la
même semaine **remplace** la ligne de la semaine, il n'en ajoute pas une
seconde. Une erreur de manipulation (mauvais extract collé) : **Suivi FWD →
Supprimer le relevé de cette semaine**, recoller le bon, archiver de nouveau.
Pour vérifier après coup : le pied du tableau de bord (« 3 relevés
archivés ») ou le Diagnostic (« Relevés archivés : 3 »).

Pour ne plus y penser : **Suivi FWD → Activer l'archivage automatique
(vendredi 17 h)**, et Google prend le relevé chaque vendredi **entre 17 h et
18 h**, à partir de ce qui est dans les onglets à ce moment-là. Il faut donc
avoir recollé l'extract avant ; à ce rendez-vous-là, personne n'est devant
l'écran, aucune boîte ne s'affiche. Vérifier une fois, dans **Extensions →
Apps Script → ⚙ Paramètres du projet**, que le fuseau horaire est
Europe/Paris. « Désactiver l'archivage automatique » l'arrête.

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
données** : les deux cercles, les verdicts, et la liste **plan par plan** de
ce qu'il faut regarder. Au-dessus du tableau, l'interrupteur **GATES | SEE**
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

- **Le bandeau** : dès deux contrats le sélecteur **Contrat**, et
  l'interrupteur **Définition électrique | Concept harnais** — les deux
  avancements du bloc HDK AA 011 ; toute la page suit celui qui est choisi,
  le titre aussi (« Suivi FWD » ou « Suivi concept harnais »). Sous le
  titre, la semaine où l'on est, et rien d'autre.
- **Le périmètre** : Tout / BASE/OPTION / PERSO — les valeurs de la colonne
  « Domaine » de l'extract, telles quelles. Il restreint toute la page.
- **En haut, sans titre** : la phrase « N sur M plans terminés », la barre
  des valeurs de la colonne telles qu'elles sont écrites (Validé, Check, En
  cours, A traiter, non renseigné…) avec leur nombre, et, dès le second
  relevé, ce qui a bougé depuis le dernier. Au-delà de quatre valeurs, ou
  quand l'une est trop petite pour se voir (deux plans sur six cents), les
  valeurs passent en **légende** sous la barre ; survoler une case éclaire
  son segment. « Validé » compte comme fini ;
  une autre valeur qui voudrait dire fini se déclare dans `Code`
  (`VALEURS_FINIES`).
- **Avancement dans le temps** : la courbe des terminés relevé après relevé,
  les jalons du programme (numérotés 1 à 5 sur une rangée, en clair dans la
  légende dessous), la fin estimée au rythme actuel et le rythme requis pour
  tenir le prochain jalon (« manque N » quand le rythme ne suffit pas). Il
  s'ouvre sur six mois ; **3 mois · 6 mois · 1 an · Tout** à droite. En
  tête, la prochaine échéance en jours : un clic ouvre sa fiche (Échap la
  ferme). Les jalons **TO** (table outil) suivent le concept harnais : sous
  la définition électrique, ils restent dessinés, en retrait.
- **Ce qui a changé, semaine par semaine** : le journal — quels plans sont
  passés terminés, lesquels ont changé d'indice, lesquels sont apparus ou ont
  disparu de l'extract. Une ligne = une référence et son passage, sans
  libellé. Les semaines s'ouvrent repliées ; le petit champ
  « Chercher un plan… » à droite ne cherche que dans le journal.
- **Avancement FWD par…** (ou **Concept harnais par…**) : le même avancement découpé par ATA, séquence,
  CC, ECP, ou par mois de création, avec la fin estimée et l'effort demandé
  par groupe. Son champ « ATA ou plan… » trouve un groupe ou un plan.
- **Plans** : l'extract, à l'identique, avec ses colonnes ; recherche, tri,
  filtres. « Vue essentielle » n'en garde qu'une poignée — référence, nom
  d'installation, ECP, ATA, séquence, validation définition électrique, date
  de création, avancement — celles de cette liste qui se retrouvent dans
  l'extract.
- **Comparaison des bases de données** (si l'onglet `SEE` est là) : ce que
  GATES dit terminé et que SEE connaît, et les écarts — en cercles, en
  verdicts, puis plan par plan en puces, les écarts d'abord, tous repliés à
  l'ouverture — un lot déplié montre tous ses plans. Un clic sur une
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
| « Le classeur est vide », avec une alerte | Aucun onglet de données lisible : l'alerte dit pourquoi | « Aucune colonne d'avancement FWD n'a été reconnue » : l'extract est collé sans sa ligne d'en-têtes ou sa ligne de groupes → recoller entier en A1 ; « Aucun onglet de données exploitable : « Feuille 1 » est vide » : aucun onglet ne contient encore d'extract |
| Pas de courbe, pas de fin estimée | Aucun relevé archivé | Suivi FWD → Archiver le relevé de cette semaine |
| Pas de section « Comparaison » | Pas d'onglet `SEE <contrat>` (ou `SEE` pour un seul contrat), ou illisible | Diagnostic, ligne « Seconde base » : elle dit s'il manque l'onglet, s'il est vide, ou si les en-têtes NAME / SOL. / Cust.V ne s'y trouvent pas |
| Un contrat en trop ou en moins | Un onglet visible en trop, ou masqué | Chaque onglet visible est un contrat ; masquer ce qui n'en est pas un |

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

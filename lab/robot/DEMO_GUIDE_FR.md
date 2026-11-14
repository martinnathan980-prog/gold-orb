# Lancer la démo du robot : le guide

Robot : `ClaudeRobot.mq5`, build `fd6aaf01e332`. Compte démo FP Markets.

Ce guide sert pour toute la démo (environ 2 semaines).
Maintenant : parties 1 à 3 (environ 20 minutes, puis jusqu'à 15 minutes d'attente).
Ensuite : parties 4 et 5. Garde-les sous la main.

Le robot trade 4 marchés depuis un seul graphique : XAUUSD.r (or), US100.r (Nasdaq), BTCUSD.r (bitcoin) et ETHUSD.r (ether).

**Bon à savoir :**

- Capture d'écran : Maj + Cmd + 4, puis encadre la zone avec la souris. L'image arrive sur le Bureau. Glisse-la dans le chat.
- Sur un Mac ancien, « Réglages Système » s'appelle « Préférences Système ».
- Un réglage introuvable, un doute : envoie-moi une capture.

---

## 1. Avant de commencer (2 minutes)

**Il te faut :**

- le Mac, avec MetaTrader 5 (l'app de MetaQuotes) ;
- le fichier `ClaudeRobot.mq5` que je t'envoie dans le chat ;
- un compte démo FP Markets réglé comme ceci :

| Réglage | Valeur |
|---|---|
| Type | Démo |
| Compte | Raw |
| Devise | EUR |
| Levier | 1:500 |
| Solde de départ | 1 000 € |
| Mode | Couverture (hedging) |

Sans le mode couverture, le robot n'envoie aucun ordre.

**Tu as déjà ouvert ce compte ? Vérifie-le :**

1. Solde : Affichage → Boîte à outils (View → Toolbox) → onglet « Trade » (ou « Trading »). La ligne du bas commence par « Solde » (Balance). Elle doit montrer 1 000.00 EUR. Aucune position et aucun ordre ne doivent être ouverts.
2. Couverture : la barre de titre de MetaTrader (tout en haut) indique en général « Hedge ». « Netting » : ce compte ne va pas. Ni l'un ni l'autre ? Dans la Boîte à outils, onglet « Journal » : cherche une ligne avec « hedging » (ou « couverture »). Toujours rien : continue, et active les notifications (partie 4). Le robot préviendra au premier trade.
3. Levier 1:500 : regarde la liste de tes comptes dans ton espace client FP Markets. Si tu ne le trouves pas, ce n'est pas bloquant : je le verrai dans les fichiers de fin.
4. Démo et Raw : le robot les confirmera lui-même au démarrage (partie 3).

**Un point ne va pas ? Ouvre un nouveau compte démo.**

- Dans MetaTrader : Fichier → Ouvrir un compte (File → Open an Account) → FP Markets → compte de démo.
- Coche « Utiliser la couverture (hedging) en trading » (Use hedge in trading).
- Choisis le type Raw en EUR, le dépôt 1000 et le levier 1:500.
- Tu peux aussi l'ouvrir depuis ton espace client FP Markets.

**Sur ce compte, avant de lancer le robot :**

- Enlève tout robot, ClaudeRobot compris s'il tourne déjà : on repart propre. Regarde le coin en haut à droite de chaque graphique ouvert. S'il y a un nom de robot (par exemple ClaudeMains ou ClaudeRobot) : ferme ce graphique.
- ClaudeRobot a déjà tourné sur ce Mac (même aujourd'hui) ? Dis-le-moi (sur ce compte démo ou sur un autre).
- Vérifie l'heure du Mac : Réglages Système → Général → Date et heure → « Régler la date et l'heure automatiquement » doit être activé. Le robot contrôle l'horloge.

**Pendant toute la démo, sur ce compte :**

- aucun trade à la main (ni sur le Mac, ni sur le téléphone) ;
- aucun dépôt, aucun retrait ;
- le robot sur ce seul Mac, sur un seul graphique. Sur le téléphone, tu peux regarder le compte, sans jamais trader.

---

## 2. Installer (environ 15 minutes)

### Étape 1 : copier le fichier

- Télécharge `ClaudeRobot.mq5` depuis le chat. Il arrive dans le dossier Téléchargements (Downloads).
- Vérifie son vrai nom : clique une fois dessus, puis Cmd + I. Rubrique « Nom et extension » : tu dois lire exactement `ClaudeRobot.mq5`. S'il y a `.txt` à la fin : efface `.txt`, appuie sur Entrée, puis clique sur « Utiliser .mq5 ».
- Dans le Finder : menu Aller → Aller au dossier… (Go → Go to Folder…, ou Maj + Cmd + G). Colle cette ligne, puis Entrée :

```
~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts
```

- Glisse `ClaudeRobot.mq5` dans cette fenêtre. Si le Mac propose de remplacer un ancien fichier : Remplacer.
- Le Finder dit que le dossier est introuvable ? Dans MetaTrader : Fichier → Ouvrir le dossier des données (File → Open Data Folder). Envoie-moi une capture de la fenêtre qui s'ouvre.

### Étape 2 : compiler

- Dans MetaTrader, appuie sur F4. Si F4 fait autre chose (luminosité, son…) : fn + F4 (la touche fn porte parfois un globe). Sinon : menu Outils → MetaQuotes Language Editor (Tools), ou le bouton « IDE » en haut. MetaEditor s'ouvre.
- À gauche, ouvre Experts. Double-clique sur ClaudeRobot.mq5. Tu ne le vois pas ? Envoie-moi une capture.
- Clique sur « Compiler » (Compile), en haut.
- En bas, onglet « Erreurs » (Errors) : tu dois lire « 0 errors, 0 warnings » (zéro erreur, zéro avertissement).
- S'il y a des « errors » : arrête-toi là. Envoie-moi une capture.
- S'il n'y a que des « warnings » : envoie-moi une capture, puis continue.
- Ferme MetaEditor.

### Étape 3 : barres max (une seule fois)

- Outils → Options (Tools → Options) → onglet « Graphiques » (Charts).
- « Nombre maximum de barres dans le graphique » (Max. bars in chart) : 500000.
- Clique sur OK.
- Quitte MetaTrader (Cmd + Q) et rouvre-le. Ce redémarrage est obligatoire pour ce réglage.

### Étape 4 : les 4 marchés

- Affichage → Observation du marché (View → Market Watch).
- Clique sur « + » en bas de la liste. Tape `XAUUSD.r`. Valide.
- Fais pareil pour `US100.r`, `BTCUSD.r` et `ETHUSD.r`.
- Autre façon : clic droit dans la liste → Symboles (Symbols) → cherche le nom → Montrer (Show).

### Étape 5 : le graphique

- Clic droit sur XAUUSD.r → Fenêtre de graphique (Chart Window).
- Clique sur M1 dans la barre des périodes (ou passe par le menu Graphiques). Fais-le avant de lancer le robot.
- Un seul graphique suffit : le robot trade les 4 marchés depuis celui-ci. Ne le mets sur aucun autre graphique.

### Étape 6 : lancer le robot

- Affichage → Navigateur (View → Navigator) → Expert Advisors. Tu ne vois pas ClaudeRobot ? Clic droit sur Expert Advisors → Actualiser (Refresh).
- Glisse ClaudeRobot sur le graphique XAUUSD.r M1. Une fenêtre s'ouvre.
- Onglet « Commun » (Common ; « Général » dans certaines versions) : coche la case du trading algo. Selon la version : « Autoriser le trading algorithmique » ou « Permettre le Trading Automatique » (Allow Algo Trading).
- Onglet « Paramètres d'entrée » (Inputs ; « Paramètres » dans certaines versions) : change seulement 2 lignes. MetaTrader les affiche avec leur description en anglais.
- Pour chacune : double-clique sur la valeur. Efface tout l'ancien texte. Colle avec Cmd + V (si rien ne s'écrit : Ctrl + V, ou clic droit → Coller). Puis Entrée.

La ligne « Risk table from:pct, read on max(balance, money paid in) (D2) » → colle :

```
0:7;3000:3.5;10000:1.4;20000:0.7
```

La ligne « K1 thresholds YYYY:T;YYYY:T in bp, from the lab » (vide au départ) → colle :

```
2026:417.23813245421888
```

- Des points, pas de virgules. Aucun espace.
- Ne touche à aucune autre ligne. La ligne « Plan start… » affiche 1970.01.01 00:00 : c'est normal.
- Clique sur OK.

Le robot risquera au plus 7 % du compte par trade (souvent moins) jusqu'à 3 000 €, puis au plus 3,5 % jusqu'à 10 000 €, 1,4 % jusqu'à 20 000 €, et ensuite 0,7 %.

### Étape 7 : Algo Trading

- Le bouton « Algo Trading » en haut (« Trading Automatique » dans certaines versions) doit être vert (▶). S'il est rouge (■), clique dessus.
- En haut à droite du graphique : le nom ClaudeRobot, avec une petite icône à pastille verte.

---

## 3. Vérifier au démarrage

Affichage → Boîte à outils (View → Toolbox) → onglet « Experts ». Les lignes du robot commencent par `CR|`.

**Tu dois voir, dans cet ordre :**

1. **INIT**, tout de suite. Au début de la ligne, vérifie :
   - `build=fd6aaf01e332`. Sinon, ce n'est pas le bon fichier : refais les étapes 1 et 2.
   - `demo=1`. Sinon, ce n'est pas un compte démo : enlève le robot tout de suite.

   La ligne est très longue : sa fin est coupée à l'écran. Clic droit dessus → Copier (Copy), puis colle-la dans le chat. Je vérifie le reste (ta mise de 7 %, le seuil K1, les 4 marchés).

   Une ligne INIT avec `deinit=` (sans `build=`) est la ligne d'arrêt du robot. Elle est normale après un changement de paramètre, une erreur ou la fermeture de MetaTrader. Regarde la ligne INIT qui contient `build=`. Aucune ? Cherche une ligne `ERROR` : voir « Une ligne ERROR ? », plus bas dans ce guide.
2. **SELFTEST** avec `ok=1`, tout de suite.
3. **PLAN** avec `state=ok`, quelques secondes après. Elle montre aussi ta mise : `risk=0:7;3000:3.5;10000:1.4;20000:0.7`. Une autre ligne PLAN (`src=first_deal`) peut la précéder : c'est normal.
4. **REBUILD**, juste après.
5. **READY** pour chacun des 4 marchés : `READY|XAUUSD`, `READY|US100`, `READY|BTCUSD`, `READY|ETHUSD`, dans n'importe quel ordre.
   Ça prend de quelques secondes à environ 15 minutes la première fois : MetaTrader charge l'historique.
   En attendant, des lignes NOTREADY, GAP, LATEBAR ou un nouveau REBUILD sont normales. Après chaque REBUILD, les lignes READY reviennent.

Le robot ne dessine rien sur le graphique : c'est normal.

Exemple (les « … » changent à chaque fois) :

```
CR|…|INIT|-|build=fd6aaf01e332|version=2.00|demo=1|vps=0|tester=0|observer=0|…
CR|…|SELFTEST|-|ok=1|why=|golden=366
CR|…|PLAN|-|src=first_deal|T=…
CR|…|PLAN|-|T=…|state=ok|demo=1|B_T=…|risk=0:7;3000:3.5;10000:1.4;20000:0.7
CR|…|REBUILD|-|n=1|why=start|…
CR|…|READY|XAUUSD|…
CR|…|READY|US100|…
CR|…|READY|BTCUSD|…
CR|…|READY|ETHUSD|…
```

**Corriger un paramètre** (si je te le demande, ou si la ligne PLAN ne montre pas ta mise) : clique sur le graphique. Appuie sur F7 (ou fn + F7). Onglet « Paramètres d'entrée ». Corrige la ligne. OK. Le robot redémarre tout seul. Copie-moi la nouvelle ligne INIT.

**Si tu vois… fais ceci :**

| Si tu vois… | Fais ceci |
|---|---|
| `SELFTEST` avec `ok=0` | Le robot se bloque lui-même : il ne tradera pas. Clic droit sur la ligne → Copier (Copy). Colle-la dans le chat. Laisse le robot en place. |
| INIT et SELFTEST, mais pas de PLAN après 2 minutes | Regarde en bas à droite de MetaTrader. « No connection » (Pas de connexion) : attends que la connexion revienne. Sinon : capture. |
| Un marché toujours sans READY après 30 minutes | Vérifie le réglage 500000 (étape 3) et que MetaTrader a bien été redémarré. Si c'est bon : capture de l'onglet Experts. |
| `CLOCK` avec `state=wrong` | Une ligne `CLOCK` avec `state=ok` arrive dans les minutes suivantes : rien à faire. Sinon, l'heure du Mac est fausse : active « Régler la date et l'heure automatiquement » (partie 1), puis redémarre MetaTrader. |
| Le bouton Algo Trading rouge | Clique dessus pour le passer au vert. |
| La pastille du robot rouge (en haut à droite du graphique) | D'abord, le bouton Algo Trading doit être vert. Il l'est et la pastille reste rouge ? Clique sur le graphique, F7 (ou fn + F7) → onglet « Commun » → coche la case du trading algo → OK. |
| Pas de nom de robot en haut à droite du graphique | Le robot ne tourne pas. Relance-le (étape 6, avec les 2 valeurs). |
| Aucune ligne qui commence par `CR` | Vérifie que tu es sur l'onglet « Experts » (pas « Journal »). Puis regarde le coin du graphique (ligne au-dessus). |

**Une ligne `ERROR` ?** Lis la fin de la ligne. S'il y a deux lignes ERROR, lis les deux.

- Elle parle de `InpRiskTable`, de `InpK1T` ou de `rule BKE` : faute de frappe dans une des 2 valeurs.
- Elle dit `symbol … not found` : en bas à droite, MetaTrader doit être connecté à ton compte démo FP Markets. Attends une minute. Si ça revient après la relance : capture.
- Elle dit `another copy` : le robot tourne aussi sur un autre graphique. Enlève-le de l'autre graphique.
- Autre chose : envoie-moi une capture.

Puis regarde le coin du graphique. Le nom ClaudeRobot a disparu : relance le robot (étape 6, avec les 2 valeurs). Il est toujours là : ne le relance pas, envoie-moi une capture.

**Envoie-moi :**

1. la ligne INIT copiée, tout de suite ;
2. une capture de l'onglet Experts, quand les 4 marchés ont leur READY.

Le premier trade peut prendre quelques heures. Le week-end, il ne se passe rien. Lancé un samedi ou un dimanche, le robot démarre quand même (INIT, PLAN, READY) : il tradera à la réouverture, dans la nuit de dimanche à lundi.

---

## 4. Pendant les deux semaines

**Le Mac ne doit jamais s'endormir.**

- Mac portable : branché au secteur, capot ouvert. Réglages Système → Batterie → Options… → active « Empêcher la suspension d'activité automatique sur adaptateur secteur lorsque l'écran est éteint » (System Settings → Battery → Options → Prevent automatic sleeping on power adapter when the display is off).
- Mac de bureau : Réglages Système → Énergie → active « Empêcher la suspension d'activité automatique lorsque l'écran est éteint » (System Settings → Energy → Prevent automatic sleeping when the display is off). Sur un macOS plus ancien, ce menu peut s'appeler « Économiseur d'énergie ».
- L'écran peut s'éteindre. Tu peux verrouiller l'écran. Mais ne ferme pas ta session.
- Garde le Mac connecté à Internet.
- Tu ne trouves pas le réglage ? Ouvre Applications → Utilitaires → Terminal. Tape `caffeinate -i`, puis Entrée. Laisse cette fenêtre ouverte : le Mac ne s'endort pas tant qu'elle est ouverte.

**Pas de redémarrage automatique.**

- Réglages Système → Général → Mise à jour de logiciels → bouton (i) à côté de « Mises à jour automatiques ». Désactive « Installer les mises à jour de macOS » et « Installer les mises à jour de sécurité et les fichiers système » (ou « …réponses de sécurité… »). Tu les réactiveras après la démo.
- Si le Mac propose une mise à jour : « Plus tard », puis l'option qui rappelle demain. Jamais « Redémarrer », ni « dans une heure », ni « ce soir » : le Mac redémarrerait.
- Si MetaTrader propose de redémarrer pour se mettre à jour : « Plus tard » (Later) aussi. S'il ne se connecte plus sans cette mise à jour : accepte-la, puis fais les vérifications « Après une coupure ».

**Ne touche à rien.**

- Ne quitte pas MetaTrader. Ne réduis pas sa fenêtre dans le Dock.
- Ne ferme pas le graphique XAUUSD.r M1. Ne change ni sa période, ni son symbole.
- Ne change pas les paramètres du robot.
- Ne touche pas aux positions du robot : ne les ferme pas, ne déplace pas leurs stops.
- Ne te connecte pas à un autre compte dans ce MetaTrader.
- N'utilise pas le testeur de stratégie (Strategy Tester).

**Après une coupure** (MetaTrader fermé, Mac redémarré ou éteint, Internet coupé) :

1. Rouvre MetaTrader s'il est fermé : il ne se relance pas tout seul après un redémarrage du Mac. Si tu utilises `caffeinate`, rouvre le Terminal et retape `caffeinate -i`.
2. Vérifie : ClaudeRobot en haut à droite du graphique XAUUSD.r M1, avec la pastille verte. Bouton Algo Trading vert.
3. ClaudeRobot n'y est plus ? Refais l'étape 6 avec les 2 valeurs. Puis copie-moi la nouvelle ligne INIT.

Le robot repart tout seul. Il relit tout et retrouve ses positions. Pendant la coupure, elles gardent leur stop chez le courtier, mais il rate les entrées prévues. Après une coupure de plus d'une minute, tu reverras REBUILD et des lignes READY (plus INIT, SELFTEST et PLAN si MetaTrader a redémarré). Si une de ses positions devait sortir pendant la coupure, il la ferme au retour : un message « ORPHAN … » juste après une coupure est normal.

**Si le compte démo disparaît** (MetaTrader dit qu'il n'existe plus, ou FP annonce sa fin) : n'ouvre pas d'autre compte. Préviens-moi tout de suite.

**Notifications sur ton téléphone** (très conseillé : c'est le seul moyen de savoir à distance que le robot tourne) :

- Installe l'app MetaTrader 5 sur ton téléphone. Dans l'app, trouve ton MetaQuotes ID (rubrique « Messages », parfois dans les Réglages). Note-le : 8 caractères.
- Sur le Mac : Outils → Options → onglet « Notifications » → coche « Activer les notifications push » (Enable Push Notifications) → tape ton MetaQuotes ID → « Test » → OK.
- Le robot est déjà réglé pour envoyer ses messages. Ils commencent par « Robot Claude : ».
- Chaque soir vers 23 h (heure de Paris) : « resume du jour : solde …, fonds … ». S'il n'arrive pas, et qu'aucun autre message du robot n'est arrivé vers 23 h, va voir le Mac. Si « ecart… » ou « commission or… » arrive à sa place, c'est normal.

Lis le tableau de haut en bas : la première ligne qui correspond au message décide.

| Message reçu | Que faire |
|---|---|
| Un message avec « algo_trading_off » ou « trading automatique desactive » | Remets le bouton Algo Trading au vert. Vérifie aussi la pastille verte du robot (sinon : clique sur le graphique, F7 (ou fn + F7) → onglet « Commun » → coche la case du trading algo → OK). |
| « REFUSED … (not_hedging) » | Le compte n'est pas en couverture. Dis-le-moi : il faudra un nouveau compte démo. |
| « ORPHAN … » juste après une coupure | Rien : le robot ferme une position qui devait sortir pendant la coupure. |
| « resume du jour… », « compte de demo sans InpPlanStart… », « ecart… », « commission or… », « rappel… », « GFP : vendredi saute… », « horloge du serveur de nouveau correcte… » | Rien. C'est de l'info. |
| « … pas pret depuis 10 min », « trou dans l'historique… », « barre manquante… », « MISSED… » | Rien tout de suite. Si ça revient souvent, dis-le-moi. |
| « ERREUR… », « ATTENTION… », « REFUSED… », « SLFIX… », « DUP… », « ORPHAN… », « horloge… », « auto-test en echec… », « une autre copie du robot… » | Regarde le Mac. Envoie-moi une capture de l'onglet Experts. |
| Un message sans « Robot Claude : » (ordre, transaction, solde) | Rien : c'est MetaTrader qui signale un trade. |
| Un autre message du robot | Envoie-le-moi (capture). |

**Coup d'œil quotidien (30 secondes) :**

1. MetaTrader est ouvert. En bas à droite, pas de « No connection » (Pas de connexion).
2. En haut à droite du graphique : ClaudeRobot avec la pastille verte. Bouton Algo Trading vert.
3. Onglet « Experts » : aucune ligne `ERROR` ni `REFUSED` parmi les dernières.
4. La notification du soir est arrivée (si tu l'as activée).

Un doute ? Une capture dans le chat.

**C'est normal :**

- Du vendredi soir au dimanche soir, le robot ne trade pas.
- Certains jours, il ne trade pas du tout.
- Il peut avoir jusqu'à 6 positions ouvertes en même temps.
- Il peut sauter un trade (par exemple faute de marge). C'est noté dans son journal : je le verrai.

---

## 5. Quoi m'envoyer, et quand

| Quand | Quoi |
|---|---|
| Au démarrage | La ligne INIT copiée et la capture de l'onglet Experts (partie 3). |
| Dès qu'un message de la ligne « Regarde le Mac » arrive (partie 4) | Une capture de l'onglet Experts. |
| Après 3 jours de marché (mercredi soir si tu lances ce week-end) | Le dossier ClaudeRobot, compressé. |
| Chaque samedi | Le dossier ClaudeRobot, compressé. |
| À la fin (environ 2 semaines) | Les dossiers Files et Logs, compressés (voir plus bas). |

**Trouver le dossier ClaudeRobot :** dans le Finder, Aller → Aller au dossier… (Maj + Cmd + G). Colle cette ligne, puis Entrée :

```
~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files
```

Le dossier ClaudeRobot est là. Il contient un fichier par jour, par exemple `20261116.log`.

**Compresser et envoyer :**

1. Clic droit (ou Ctrl + clic) sur le dossier ClaudeRobot → Compresser.
2. Un fichier `ClaudeRobot.zip` apparaît à côté.
3. Glisse-le dans ce chat (ou bouton « + » en bas à gauche de la zone de texte). Si le chat refuse le fichier, dis-le-moi.
4. Une fois envoyé, mets `ClaudeRobot.zip` à la corbeille.

**Facultatif (1 minute), avec l'envoi du mercredi :** dans Observation du marché, clic droit sur BTCUSD.r → Spécification (Specification). Fais une capture de la fenêtre. Pareil pour US100.r. Je verrai la marge demandée sur le bitcoin et le lot minimum du Nasdaq.

**À la fin de la démo :**

1. Avant la fin, je t'envoie la nouvelle version de ReleveFP, avec ses étapes. Je te dirai aussi quand lancer SondeFP, et comment enregistrer l'historique de tes trades (prix et frais de chacun). Les fichiers de ReleveFP et SondeFP iront dans Files → claude → releve.
2. Ensuite, dans le Finder : Aller → Aller au dossier… Colle cette ligne, puis Entrée :

   ```
   ~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5
   ```

   Clique sur Files, puis Cmd + clic sur Logs. Clic droit → Compresser. Envoie-moi le fichier `Archive.zip`.
3. Trop gros pour le chat ? Compresse Files et Logs chacun à part, puis envoie les deux .zip.
4. Laisse le robot tourner jusqu'à ce que je te dise de l'arrêter.

**Confidentialité :** ces fichiers peuvent contenir ton nom, ton numéro de compte démo ou le nom du serveur. Ce n'est pas grave : ils restent entre nous, je ne les publie jamais. N'envoie jamais ton mot de passe.

---

## 6. Après la démo

Je compare chaque trade du compte avec le labo : prix, stops et frais réels. Si tout colle, il restera deux étapes avant l'argent réel : un test du robot sur l'historique dans MetaTrader (le testeur de stratégie), et le serveur MetaQuotes (VPS), qui fera tourner le robot 24 h/24. Avec le VPS viendront deux semaines « à blanc » : deux copies du robot tournent sans trader, pour vérifier qu'elles font la même chose. Avant l'argent réel (1 000 €), je te rappellerai le risque de ton choix à 7 % (le compte peut perdre la moitié, ou plus), et tu confirmeras. Je te donnerai les étapes le moment venu.

---

## Résumé pour le chat

Tout est prêt pour la démo. Le guide complet est joint ; voici l'essentiel :

1. Compte démo FP Markets : Raw, EUR, levier 1:500, 1 000 €, en couverture (hedging). Aucun autre robot, aucun trade à la main sur ce compte.
2. Télécharge `ClaudeRobot.mq5`. Dans le Finder (Aller → Aller au dossier…), mets-le dans le dossier Experts de MetaTrader : le chemin exact est dans le guide (étape 1).
3. Dans MetaTrader : F4 (ou fn + F4), double-clique sur ClaudeRobot.mq5, puis « Compiler » : tu dois lire 0 errors.
4. Outils → Options → Graphiques : barres max 500000. Quitte MetaTrader (Cmd + Q) et rouvre-le.
5. Observation du marché : affiche XAUUSD.r, US100.r, BTCUSD.r, ETHUSD.r. Ouvre XAUUSD.r en M1 et glisse ClaudeRobot dessus. Onglet Commun : coche le trading algo.
6. Onglet Paramètres d'entrée, change 2 lignes seulement. La ligne « Risk table… » :

   ```
   0:7;3000:3.5;10000:1.4;20000:0.7
   ```

   La ligne « K1 thresholds… » :

   ```
   2026:417.23813245421888
   ```

7. Le bouton Algo Trading doit être vert.
8. Onglet Experts : INIT (avec build=fd6aaf01e332 et demo=1), SELFTEST ok=1, PLAN, puis READY pour les 4 marchés (jusqu'à 15 min). Copie-moi la ligne INIT (clic droit → Copier) et envoie-moi une capture.
9. Pendant 2 semaines : Mac branché, sans veille ni redémarrage, MetaTrader ouvert, on ne touche à rien.
10. Mercredi soir, puis chaque samedi : le dossier ClaudeRobot compressé (partie 5 du guide). Avant la fin, je t'envoie ReleveFP. N'envoie jamais ton mot de passe.

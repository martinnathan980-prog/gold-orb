# Lancer la démo du robot : le guide

Robot : `ClaudeRobot.mq5`, build `fd6aaf01e332`. Compte démo FP Markets.

Ce guide sert pour toute la démo (environ 2 semaines).
Maintenant : parties 1 et 2 (environ 20 minutes), puis la partie 3 au lancement.
Ensuite : parties 4 et 5. Garde-les sous la main.

Le robot trade 4 marchés depuis un seul graphique : XAUUSD.r (or), US100.r (Nasdaq), BTCUSD.r (bitcoin) et ETHUSD.r (ether).

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

1. Couverture : la barre de titre de MetaTrader (tout en haut) indique en général « Hedge ». Si elle indique « Netting », ce compte ne va pas. Si tu ne vois ni l'un ni l'autre, continue : le robot le signalera au premier trade (partie 4).
2. EUR et 1 000 € : Affichage → Boîte à outils (View → Toolbox) → onglet « Trade ». La ligne du bas commence par « Balance ». Elle doit montrer 1 000.00 EUR.
3. Levier 1:500 : regarde la liste de tes comptes dans ton espace client FP Markets. Si tu ne le trouves pas, ce n'est pas bloquant : je le verrai dans les fichiers de fin.
4. Démo et Raw : le robot les confirmera lui-même au démarrage (partie 3).

**Un point ne va pas ? Ouvre un nouveau compte démo.**

- Dans MetaTrader : Fichier → Ouvrir un compte (File → Open an Account) → FP Markets → compte de démo.
- Coche « Utiliser la couverture (hedging) en trading » (Use hedge in trading).
- Choisis le type Raw en EUR, le dépôt 1000 et le levier 1:500.
- Tu peux aussi l'ouvrir depuis ton espace client FP Markets.

**Sur ce compte, avant de lancer le robot :**

- Enlève tout autre robot. Regarde le coin en haut à droite de chaque graphique ouvert. S'il y a un nom de robot (par exemple ClaudeMains) : clic droit sur son icône → Supprimer (Remove). Ou ferme ce graphique.
- Si l'onglet « Trade » montre des positions ouvertes, ferme-les à la main.
- Vérifie l'heure du Mac : Réglages Système → Général → Date et heure → « Régler la date et l'heure automatiquement » doit être activé. Le robot contrôle l'horloge.

**Pendant toute la démo, sur ce compte :**

- aucun trade à la main (ni sur le Mac, ni sur le téléphone) ;
- aucun dépôt, aucun retrait ;
- ce compte ouvert dans ce seul MetaTrader, sur ce seul Mac.

---

## 2. Installer (environ 15 minutes)

### Étape 1 : copier le fichier

- Dans MetaTrader : Fichier → Ouvrir le dossier des données (File → Open Data Folder).
- Ouvre le dossier MQL5, puis Experts.
- Glisse `ClaudeRobot.mq5` dedans. Si le Mac propose de remplacer un ancien fichier : Remplacer.
- Le fichier doit s'appeler exactement `ClaudeRobot.mq5`. S'il s'appelle `ClaudeRobot.mq5.txt`, renomme-le.
- Si le dossier ne s'ouvre pas : dans le Finder, menu Aller → Aller au dossier… (Go → Go to Folder…). Colle cette ligne, puis Entrée :

```
~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts
```

### Étape 2 : compiler

- Dans MetaTrader, appuie sur F4. Sur un clavier de Mac : fn + F4 (la touche fn est en bas à gauche). MetaEditor s'ouvre.
- Si rien ne s'ouvre : menu Outils → MetaQuotes Language Editor (Tools → MetaQuotes Language Editor).
- À gauche, ouvre Experts. Double-clique sur ClaudeRobot.mq5.
- Clique sur « Compiler » (Compile), en haut.
- En bas, onglet « Erreurs » (Errors) : tu dois lire « 0 errors, 0 warnings ».
- S'il y a des « errors » : arrête-toi là. Envoie-moi une capture.
- S'il n'y a que des « warnings » : envoie-moi une capture, puis continue.
- Ferme MetaEditor.

### Étape 3 : barres max (une seule fois)

- Outils → Options (Tools → Options) → onglet « Graphiques » (Charts).
- « Nombre maximum de barres dans le graphique » (Max. bars in chart) : 500000.
- Clique sur OK.
- Quitte MetaTrader et rouvre-le. Ce redémarrage est obligatoire pour ce réglage.

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

- Affichage → Navigateur (View → Navigator) → Expert Advisors.
- Glisse ClaudeRobot sur le graphique XAUUSD.r M1. Une fenêtre s'ouvre.
- Onglet « Commun » (Common ; « Général » dans certaines versions) : coche la case du trading algo. Selon la version : « Autoriser le trading algorithmique » ou « Permettre le Trading Automatique » (Allow Algo Trading).
- Onglet « Paramètres » (Inputs) : change seulement 2 lignes. MetaTrader les affiche avec leur description en anglais. Double-clique sur la valeur, colle, puis Entrée.

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

Le robot risquera donc 7 % du compte par trade jusqu'à 3 000 €, puis 3,5 % jusqu'à 10 000 €, 1,4 % jusqu'à 20 000 €, et ensuite 0,7 %.

### Étape 7 : Algo Trading

- Le bouton « Algo Trading » en haut (« Trading Automatique » dans certaines versions) doit être vert (▶). S'il est rouge (■), clique dessus.
- En haut à droite du graphique : le nom ClaudeRobot, avec une petite icône à pastille verte.

---

## 3. Vérifier au démarrage

Affichage → Boîte à outils (View → Toolbox) → onglet « Experts ». Les lignes du robot commencent par `CR|`.

**Tu dois voir, dans cet ordre :**

1. **INIT**, tout de suite. Vérifie 5 choses dans cette ligne :
   - `build=fd6aaf01e332`. Sinon, ce n'est pas le bon fichier : refais les étapes 1 et 2.
   - `demo=1`. Sinon, ce n'est pas un compte démo : enlève le robot tout de suite.
   - `risk=0:7;3000:3.5;10000:1.4;20000:0.7`. Sinon : voir « Corriger un paramètre » plus bas.
   - `k1t=2026:4.17238132…` avec `e+02` (ou `e+002`) au bout. MetaTrader écrit le nombre autrement : `4.17238132…e+02` veut dire 417,238… C'est normal. Si `k1t=` est vide : voir « Corriger un paramètre ».
   - `XAUUSD=XAUUSD.r`, `US100=US100.r`, `BTCUSD=BTCUSD.r`, `ETHUSD=ETHUSD.r`. Sans « .r », ce n'est pas un compte Raw : dis-le-moi.
2. **SELFTEST** avec `ok=1`, tout de suite.
3. **PLAN** avec `state=ok`, quelques secondes après. Il y a deux lignes PLAN : c'est normal.
4. **REBUILD**, juste après.
5. Quatre lignes **READY** : `READY|XAUUSD`, `READY|US100`, `READY|BTCUSD`, `READY|ETHUSD`, dans n'importe quel ordre.
   Ça prend de quelques secondes à environ 15 minutes la première fois : MetaTrader charge l'historique.
   En attendant, des lignes NOTREADY, GAP, LATEBAR ou un deuxième REBUILD sont normales.

Le robot ne dessine rien sur le graphique : c'est normal.

Exemple (les « … » changent à chaque fois) :

```
CR|…|INIT|-|build=fd6aaf01e332|version=2.00|demo=1|vps=0|tester=0|observer=0|entries_off=0|harness=0|comm_pts=6|risk=0:7;3000:3.5;10000:1.4;20000:0.7|sleeves=ALL|S0.75r=on|K1=on|H2=on|k1t=2026:4.1723813245421888e+02|XAUUSD=XAUUSD.r|US100=US100.r|BTCUSD=BTCUSD.r|ETHUSD=ETHUSD.r
CR|…|SELFTEST|-|ok=1|why=|golden=366
CR|…|PLAN|-|src=first_deal|T=…
CR|…|PLAN|-|T=…|state=ok|demo=1|B_T=…|risk=0:7;3000:3.5;10000:1.4;20000:0.7
CR|…|REBUILD|-|n=1|why=start|…
CR|…|READY|XAUUSD|…
CR|…|READY|US100|…
CR|…|READY|BTCUSD|…
CR|…|READY|ETHUSD|…
```

**Corriger un paramètre :** clique sur le graphique. Appuie sur F7 (fn + F7). Onglet « Paramètres ». Corrige la ligne. OK. Le robot redémarre tout seul.

**Si tu vois… fais ceci :**

| Si tu vois… | Fais ceci |
|---|---|
| `SELFTEST` avec `ok=0` | Le robot se bloque lui-même : il ne tradera pas. Clic droit sur la ligne → Copier (Copy). Colle-la dans le chat. Laisse le robot en place. |
| Une ligne `ERROR` au lancement (le robot s'arrête) | Lis la fin de la ligne. Elle parle de `InpRiskTable` (la ligne « Risk table… ») ou de `InpK1T` (la ligne « K1 thresholds… ») : faute de frappe. Relance le robot (étape 6) et recolle les 2 valeurs. Elle dit `symbol … not found` : refais l'étape 4. Elle dit `another copy` : le robot tourne déjà sur un autre graphique, garde-n'en qu'un. Autre chose : capture. |
| Un marché toujours sans READY après 30 minutes | Vérifie le réglage 500000 (étape 3) et que MetaTrader a bien été redémarré. Si c'est bon : capture de l'onglet Experts. |
| Le bouton Algo Trading rouge | Clique dessus pour le passer au vert. |
| L'icône du robot avec une pastille rouge (en haut à droite du graphique) | Clique sur le graphique, puis F7 (fn + F7) → onglet « Commun » → coche la case du trading algo → OK. |
| Pas de nom de robot en haut à droite du graphique | Le robot ne tourne pas. Relance-le (étape 6). |
| Une ligne `CLOCK` avec `state=wrong` | L'heure du Mac est fausse. Active « Régler la date et l'heure automatiquement » (partie 1). Puis redémarre MetaTrader. |
| Aucune ligne qui commence par CR | Vérifie que tu es sur l'onglet « Experts » (pas « Journal »). Puis regarde le coin du graphique (deux lignes plus haut). |

**Envoie-moi une capture** de l'onglet Experts, avec INIT, SELFTEST, PLAN et les 4 READY.
Si la ligne INIT est coupée : clic droit dessus → Copier (Copy), puis colle-la dans le chat.

Le premier trade peut prendre quelques heures. Le week-end, il ne se passe rien.

---

## 4. Pendant les deux semaines

**Le Mac ne doit jamais s'endormir.**

- Mac portable : branché au secteur, capot ouvert. Réglages Système → Batterie → Options… → active « Empêcher la suspension d'activité automatique sur adaptateur secteur lorsque l'écran est éteint » (System Settings → Battery → Options → Prevent automatic sleeping on power adapter when the display is off).
- Mac de bureau : Réglages Système → Énergie → active « Empêcher la suspension d'activité automatique lorsque l'écran est éteint » (System Settings → Energy → Prevent automatic sleeping when the display is off). Sur un macOS plus ancien, ce menu peut s'appeler « Économiseur d'énergie ».
- L'écran peut s'éteindre. Tu peux verrouiller l'écran. Mais ne ferme pas ta session.
- Garde le Mac connecté à Internet.
- Tu ne trouves pas le réglage ? Ouvre Applications → Utilitaires → Terminal. Tape `caffeinate -i`, puis Entrée. Laisse cette fenêtre ouverte : le Mac ne s'endort pas tant qu'elle est ouverte.

**Pas de redémarrage automatique.**

- Réglages Système → Général → Mise à jour de logiciels → bouton (i) à côté de « Mises à jour automatiques » → désactive « Installer les mises à jour de macOS ». Tu le réactiveras après la démo.
- Si le Mac propose une mise à jour : « Plus tard ».
- Si MetaTrader propose de redémarrer pour se mettre à jour : « Plus tard » (Later) aussi.

**Ne touche à rien.**

- Ne quitte pas MetaTrader. Ne réduis pas sa fenêtre dans le Dock.
- Ne ferme pas le graphique XAUUSD.r M1. Ne change ni sa période, ni son symbole.
- Ne change pas les paramètres du robot.
- Ne touche pas aux positions du robot : ne les ferme pas, ne déplace pas leurs stops.
- Ne te connecte pas à un autre compte dans ce MetaTrader.

**Après une coupure** (MetaTrader fermé, Mac redémarré, Internet coupé) :

- Rouvre MetaTrader si besoin. Le robot repart tout seul.
- Il relit tout et retrouve ses positions. Tu reverras une ligne REBUILD et les 4 READY (plus INIT, SELFTEST ok=1 et PLAN si MetaTrader a redémarré).
- Il rate les entrées prévues pendant la coupure. Ses positions gardent leur stop chez le courtier.
- Vérifie juste que le bouton Algo Trading est vert.

**Notifications sur ton téléphone** (facultatif, conseillé) :

- Installe l'app MetaTrader 5 sur ton téléphone. Dans « Messages », copie ton MetaQuotes ID.
- Sur le Mac : Outils → Options → onglet « Notifications » → coche « Activer les notifications push » (Enable Push Notifications) → colle ton MetaQuotes ID → « Test » → OK.
- Le robot est déjà réglé pour envoyer ses messages. Ils commencent par « Robot Claude : ».
- Chaque soir vers 23 h (heure de Paris) : « resume du jour : solde …, fonds … ». S'il n'arrive pas, va voir le Mac.

| Message reçu | Que faire |
|---|---|
| « resume du jour… », « compte de demo sans InpPlanStart… », « ecart… », « commission or… », « rappel… », « GFP : vendredi saute… » | Rien. C'est de l'info. |
| « … pas pret depuis 10 min », « trou dans l'historique… », « barre manquante… », « MISSED… » | Rien tout de suite. Si ça revient souvent, dis-le-moi. |
| « ERREUR… », « ATTENTION… », « REFUSED… », « SLFIX… », « DUP… », « ORPHAN… », « horloge… », « auto-test en echec… », « une autre copie du robot… » | Regarde le Mac. Envoie-moi une capture. |
| Un message avec « algo_trading_off » ou « trading automatique desactive » | Remets le bouton Algo Trading au vert. |
| « REFUSED … (not_hedging) » | Le compte n'est pas en couverture. Dis-le-moi : il faudra un nouveau compte démo. |
| Un autre message | Envoie-le-moi (capture). |

**Coup d'œil quotidien (30 secondes) :**

1. MetaTrader est ouvert. En bas à droite, pas de « No connection » (Pas de connexion).
2. En haut à droite du graphique : ClaudeRobot avec la pastille verte. Bouton Algo Trading vert.
3. Onglet « Experts » : aucune ligne `ERROR` parmi les dernières.
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
| Au démarrage | La capture de l'onglet Experts (partie 3). |
| Dès qu'un message « ERREUR » ou « ATTENTION » arrive | Une capture. |
| Au bout de 3 jours | Le dossier ClaudeRobot, compressé. |
| À la fin (environ 2 semaines) | Les dossiers Files et Logs, compressés. |

**Trouver le dossier ClaudeRobot :**
MetaTrader → Fichier → Ouvrir le dossier des données (File → Open Data Folder) → MQL5 → Files → ClaudeRobot.
Il contient un fichier par jour, par exemple `20261114.log`.

**Compresser et envoyer :**

1. Clic droit (ou Ctrl + clic) sur le dossier ClaudeRobot → Compresser.
2. Un fichier `ClaudeRobot.zip` apparaît à côté.
3. Glisse-le dans ce chat (ou joins-le avec le trombone).

**À la fin de la démo :**

1. Avant la fin, je t'envoie la nouvelle version de ReleveFP, avec ses étapes. Je te dirai aussi quand lancer SondeFP. Leurs fichiers iront dans MQL5 → Files → claude → releve.
2. Ensuite, ouvre le dossier MQL5. Sélectionne Files et Logs (touche Cmd enfoncée). Clic droit → Compresser. Envoie-moi le fichier `Archive.zip`.
3. Si le fichier est trop gros pour le chat : envoie les dossiers un par un.
4. Laisse le robot tourner jusqu'à ce que je te dise de l'arrêter.

**Confidentialité :** ces fichiers peuvent contenir ton numéro de compte démo ou le nom du serveur. Ce n'est pas grave : ils restent entre nous, je ne les publie jamais. N'envoie jamais ton mot de passe.

---

## 6. Après la démo

Je compare chaque trade du compte avec le labo : prix, stops et frais réels. Si tout colle, on passe à l'argent réel, avec 1 000 €. Avant, je te rappellerai le risque de ton choix à 7 % (le compte peut perdre la moitié, ou plus), et tu confirmeras. Ensuite viendra le serveur MetaQuotes (VPS), qui fera tourner le robot 24 h/24. Les deux semaines « à blanc » (deux copies du robot tournent sans trader, pour vérifier qu'elles font la même chose) se feront avec cette étape. Je te donnerai les étapes le moment venu.

---

## Résumé pour le chat

Tout est prêt pour la démo. Le guide complet est joint ; voici l'essentiel :

1. Compte démo FP Markets : Raw, EUR, levier 1:500, 1 000 €, en couverture (hedging). Aucun autre robot, aucun trade à la main sur ce compte.
2. Fichier → Ouvrir le dossier des données → MQL5 → Experts : mets-y `ClaudeRobot.mq5`. Puis fn + F4, double-clique sur le fichier, « Compiler » : tu dois lire 0 errors.
3. Outils → Options → Graphiques : barres max 500000. Redémarre MetaTrader.
4. Observation du marché : ajoute XAUUSD.r, US100.r, BTCUSD.r, ETHUSD.r. Ouvre XAUUSD.r en M1.
5. Glisse ClaudeRobot sur ce graphique. Onglet Commun : coche le trading algo. Onglet Paramètres, change 2 lignes seulement :
   « Risk table… » → `0:7;3000:3.5;10000:1.4;20000:0.7`
   « K1 thresholds… » → `2026:417.23813245421888`
6. Le bouton Algo Trading doit être vert.
7. Onglet Experts : INIT (avec build=fd6aaf01e332 et demo=1), SELFTEST ok=1, PLAN, puis 4 lignes READY (jusqu'à 15 min). Envoie-moi une capture.
8. Pendant 2 semaines : Mac branché et sans veille (Réglages Système → Batterie → Options, ou Énergie), MetaTrader ouvert, on ne touche à rien.
9. Dans 3 jours : envoie-moi le dossier MQL5 → Files → ClaudeRobot, compressé (clic droit → Compresser).
10. Avant la fin, je t'envoie la nouvelle version de ReleveFP. N'envoie jamais ton mot de passe.

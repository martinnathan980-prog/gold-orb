# GoldOrb_Donchian4H — mode d'emploi

Programme MetaTrader 5 (Expert Advisor) de la règle retenue par le laboratoire : **cassure du canal de 10 jours sur bougies de 4 heures, sur l'or (XAUUSD)**. Résultats et limites : voir le bilan (`lab/report/bilan.html`) et `lab/results/`.

> **Statut :** règle validée sur l'historique 2013-2025 et sur le test final 2026 (43 trades), mais **non validée en réel**. Commencez par l'observation et la démo. Ce n'est pas un conseil financier.

## Ce que fait le programme

Toutes les 4 heures (00 h, 04 h, 08 h, 12 h, 16 h, 20 h **UTC**), s'il n'y a pas de position :
- niveau d'**achat** = plus haut des 60 dernières bougies de 4 h (10 jours), niveau de **vente** = plus bas ;
- valables jusqu'à la clôture de 4 h suivante ; le premier touché déclenche le trade, l'autre est annulé ;
- stop initial = 2 × ATR(14) des bougies de 4 h ; stop suiveur = même distance depuis le meilleur prix, déplacé à chaque clôture de bougie d'une minute ;
- sortie forcée 5 jours de bourse (heure de New York) après la décision, moins 5 minutes.

Le programme tient une **position fictive** (« papier ») qui applique exactement les règles du simulateur du labo, bougie M1 par bougie M1. Il vous envoie une alerte quand le prix franchit un niveau, une alerte de sortie avec le résultat en R, un bilan chaque vendredi soir, et il écrit tout dans un journal CSV.

## Les 3 modes (`InpMode`)

| Mode | Ce qu'il fait | Pour qui |
|---|---|---|
| **0 – Alertes** (défaut) | aucun ordre ; alertes + position fictive + journal | observer sans risque |
| **1 – Gestion manuelle** | vous ouvrez la position vous-même après l'alerte ; le programme pose le stop, le fait suivre chaque minute et ferme au bout de 5 jours | si vous tenez à décider de chaque entrée |
| **2 – Automatique** | ordres stop OCO chez le courtier, stop suiveur, sortie au temps | **compte démo** d'abord (refusé sur compte réel tant que `InpAllowAutoReal = false`) |

Pourquoi l'automatique est recommandé à terme : dans les tests, entrer à la main 1 à 15 minutes après l'alerte a retiré 25 à 35 % de l'avantage, et les cassures de nuit (heure de Paris) ont pesé un quart des gains.

## Installation

1. Dans MetaTrader 5 : **Fichier > Ouvrir le dossier des données**, puis `MQL5\Experts\`. Copiez-y `GoldOrb_Donchian4H.mq5`.
2. Ouvrez **MetaEditor** (F4), ouvrez le fichier, **Compiler** (F7). Il doit afficher « 0 errors ». Si une erreur apparaît, envoyez-moi le message exact.
3. Dans MT5 : ouvrez un graphique **XAUUSD** (n'importe quelle unité de temps ; le programme calcule lui-même ses bougies de 4 h en heure UTC). Faites glisser le programme sur le graphique, onglet **Paramètres**, puis OK. Activez le bouton **Algo Trading**.
4. Pour avoir assez d'historique : **Outils > Options > Graphiques > Nombre max. de barres** = « illimité » (ou ≥ 100 000). Le programme a besoin d'environ 180 jours de bougies M5.

## Réglages importants

- **`InpServerTZ` — fuseau du serveur.** Le programme doit convertir l'heure du serveur en UTC. Choix :
  - *Serveur = New York + 7 h* (UTC+2 l'hiver, UTC+3 l'été américain) : le cas le plus courant (IC Markets, Pepperstone, Tickmill, FP Markets…) ;
  - *UTC+2/+3 selon l'heure d'été européenne* : certains courtiers ;
  - *fixe*.
  Au démarrage puis à chaque clôture de 4 h, le programme compare la règle choisie au décalage réellement mesuré. En cas de désaccord, il envoie **OFFSET_WARN** et ne place aucun niveau : changez alors `InpServerTZ`.
- **`InpRiskPct`** (0,5 % par défaut) : sert à calculer la taille conseillée. Le lot minimum de l'or (0,01 = 1 once) risque déjà tout le stop (35 à 55 $ en 2025-2026). Il faut donc environ **7 000 à 11 000 $** pour rester à 0,5 % par trade. Si le lot minimum dépasse 1,5 fois le risque visé (`InpMaxRiskMult`), le message l'indique (« TROP RISQUÉ »), et le mode automatique ne place pas l'ordre.
- **`InpNotifyLevels`** : envoie les deux niveaux à chaque clôture de 4 h, seulement entre `InpWakeFrom` et `InpWakeTo` (heure de Paris).

## Notifications sur le téléphone

- **Push MT5 (gratuit) :** installez l'appli MetaTrader 5 sur le téléphone, menu **Messages**, notez votre **MetaQuotes ID**. Sur l'ordinateur : **Outils > Options > Notifications**, cochez « Activer les notifications push », saisissez l'ID, puis **Test**.
- **Telegram (optionnel) :** créez un bot avec @BotFather (vous obtenez un *token*), envoyez-lui un message, récupérez votre *chat_id* (par exemple avec @userinfobot). Renseignez `InpTgToken` et `InpTgChat`, puis **Outils > Options > Expert Advisors > Autoriser WebRequest** pour `https://api.telegram.org`.

## Faire tourner en continu (VPS)

Le programme doit tourner 24 h/24, 5 jours sur 5. Le plus simple : clic droit sur votre compte dans le Navigateur MT5, **Enregistrer un serveur virtuel** (VPS MetaQuotes, environ 10-15 $/mois), puis migrer le programme. Les notifications push fonctionnent depuis le VPS. Le journal reste sur la machine où tourne le programme.

## Vérification AVANT toute utilisation (obligatoire)

1. **Testeur de stratégie** (Ctrl+R) : programme `GoldOrb_Donchian4H`, symbole XAUUSD, période 2025-01-01 → 2025-12-31, modélisation **« Chaque tick basé sur les ticks réels »**, mode 0.
2. Le journal du test est écrit dans `%APPDATA%\MetaQuotes\Terminal\Common\Files\GoldOrb\tester_journal_XAUUSD.csv`.
3. Copiez-le dans le dépôt et lancez :
   ```
   python3 lab/live/compare_journal.py tester_journal_XAUUSD.csv
   ```
   Attendu : **au moins 90 % des trades identiques** et un total en R proche du labo (avec des données MT5, le jumeau Python du labo retrouve 92 % des trades et le même résultat). En dessous, ne pas utiliser : envoyez-moi le résultat.

## Protocole conseillé

1. **2 à 3 mois d'observation :** mode 0 sur votre compte, et une copie en mode 2 sur un **compte démo**, sur VPS.
2. **Règle d'arrêt fixée d'avance :** on arrête si le cumul papier descend à **−10 R**, ou si la démo s'écarte du papier de plus de **0,03 R par trade** en moyenne (glissement, écarts, heure du serveur).
3. **Seulement ensuite**, en réel : 0,25 à 0,5 % de risque par trade, mode automatique, chez un courtier ECN à frais bas. Ne sautez jamais un signal « au feeling » : les gains viennent de quelques gros trades.

## À quoi s'attendre (historique 2013-2026, frais prudents)

- Environ **1 trade par semaine**, 40 % de gagnants, gain moyen ≈ 2 fois la perte moyenne.
- **1 semaine sur 3 positive**, 43 % négatives, 25 % sans trade. Jusqu'à 9 pertes d'affilée, et des périodes de 2 ans sans nouveau sommet.
- À 0,5 % de risque par trade : ≈ +3,4 %/an, pire baisse ≈ 4 %. À 1 % : ≈ +6,7 %/an, pire baisse ≈ 8 %.
- Si l'avantage réel n'est que la moitié de celui mesuré, divisez par deux.

## Fichiers produits

Dans `%APPDATA%\MetaQuotes\Terminal\Common\Files\GoldOrb\` :
- `journal_XAUUSD.csv` : un événement par ligne (LEVELS, ENTRY, EXIT, WEEK, REAL_*, OFFSET_WARN, DATA_WARN, REPLAY, SPREAD, HEARTBEAT), avec l'heure UTC, l'heure de Paris, l'heure du serveur et le décalage utilisé ;
- `state_XAUUSD.bin` : l'état (position fictive, niveaux, cumul), rechargé au redémarrage. Après une coupure, le programme **rattrape** les bougies manquées sans renvoyer les vieilles alertes.

## Questions fréquentes

- *Mon symbole s'appelle `XAUUSD.r` ou `GOLD`.* Ça marche ; le programme prévient seulement si le nom ne contient ni « XAU » ni « GOLD ».
- *Compte en euros ?* La taille de position utilise la valeur du tick fournie par le courtier, dans la devise du compte.
- *Compte « netting » ou « hedging » ?* Les deux conviennent : le programme ne tient qu'une position à la fois.
- *Puis-je utiliser les bougies H4 du graphique ?* Non : chez la plupart des courtiers, elles suivent l'heure du serveur, et les tests montrent un résultat plus faible (1,28 au lieu de 1,35 sur 2013-2021). Le programme reconstruit lui-même des bougies de 4 h en heure UTC.

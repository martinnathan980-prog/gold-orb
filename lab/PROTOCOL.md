# Protocole de recherche (pré-enregistré le 2026-11-05, AVANT tout test de stratégie)

Objectif : trouver une ou plusieurs règles de trading (achat ET/OU vente) qui gagnent plus
qu'elles ne perdent **après frais réalistes**, avec des trades de quelques minutes à 5 jours,
à une fréquence d'environ 1 trade/semaine à 3 trades/jour. Le résultat « rien ne passe » est
un résultat valide et sera rapporté comme tel.

## 1. Données et découpage (figé)

| Période | Dates | Usage |
|---|---|---|
| IS (recherche) | 2013-01-01 → 2021-12-31 | libre : idées, réglages |
| VAL (validation) | 2022-01-01 → 2025-12-31 | **une seule fois**, sur la/les config(s) choisie(s) sur IS. Accès journalisé (`results/val_access.log`). Pas de re-réglage après. |
| HOLDOUT (test final) | 2026-01-01 → dernière donnée dispo | absente du disque ; téléchargée **une fois** à la fin, pour les 1–3 finalistes. |

Source : Dukascopy M1 bid+ask (or) ; bid seul + spread fixe estimé (autres marchés).

## 2. Critères de réussite d'une stratégie (figés)

Sur IS (2013–2021), config choisie :
1. ≥ 200 trades ; entre 25 et 750 trades/an.
2. Profit factor (en R) ≥ 1,20 ; t-stat de l'espérance ≥ 2,0.
3. Au moins 2/3 des années positives.
4. Durée max d'un trade ≤ 5 jours de bourse (sortie forcée).
5. Robustesse : paramètres voisins (±20 % ou case adjacente de la grille) → PF médian ≥ 1,10.
6. Frais ×1,5 (spread, slippage, commission) → PF ≥ 1,05.

Sur VAL (2022–2025), même config, sans retouche :
7. PF ≥ 1,10 et espérance > 0.

Sur HOLDOUT (2026), regard unique :
8. PF > 1,0. (Échantillon court : réussite = indice faible, échec net = information forte.)

Rapporté sans être éliminatoire : % de semaines positives, pire semaine, drawdown max,
résultat achat vs vente séparé (vérifier que ce n'est pas juste « l'or a monté »).

## 3. Contrôle du sur-apprentissage

- Budget ≤ 150 configurations testées sur IS par piste, **toutes journalisées**
  (`results/<piste>/trials.jsonl`). Le nombre d'essais fait partie de la preuve.
- Les signaux n'utilisent que l'information disponible à l'instant de décision
  (clôture de bougie → entrée à la bougie M1 suivante).
- Un agent « avocat du diable » audite chaque finaliste : biais de futur, fuseaux horaires,
  frais, cohérence M1 vs ticks (S2 2025), robustesse.

## 4. Modèle de frais (prudent, défini avant les tests)

- Or : spread réel bid/ask Dukascopy (médiane ~0,32 $ 2013–2025, ~0,60 $ fin 2025),
  + slippage 1,5 point de base par côté sur ordres au marché / stop,
  + commission 0,07 $/oz aller-retour (~7 $/lot),
  + swap : 5 %/an (achat), 2 %/an (vente) par nuit à 17h New York, mercredi ×3.
- Ambiguïté intra-bougie : si stop et objectif sont touchés dans la même minute → stop.
- Vérifié : des entrées aléatoires perdent ~0,25 R/trade (= les frais), pas d'argent gratuit.

## 5. Exécution prévue

Phase 1 : alertes uniquement (notification MT5 / Telegram) + journal de chaque signal.
Phase 2 : comparaison réel vs backtest après 2–3 mois. Phase 3 seulement ensuite : démo auto.

## Amendement 1 — 2026-11-05 (après le rapport de la piste ORB, AVANT les résultats des 5 autres pistes)

Constat de la piste ORB : en intraday sur l'or, le verdict dépend surtout des frais (signal brut
+0,1 à +0,2 R, frais ~0,8 $/trade soit 0,13 à 0,5 R). Le modèle pré-enregistré reste le modèle
**principal** et n'est pas modifié. On ajoute, pour information :

1. Un scénario secondaire « courtier ECN à bas coûts », dont les paramètres sont fixés à partir
   d'une recherche documentée sur les courtiers (`COSTS.md`) **avant** d'être appliqué au moindre
   candidat. Chaque finaliste est rapporté sous les deux modèles.
2. Statuts : **PASS** = passe tout avec le modèle principal ; **CONDITIONNEL** = échoue avec le modèle
   principal mais passe tout avec le scénario bas coûts (viable seulement chez un courtier à bas
   coûts) ; **ÉCHEC** sinon.
3. Le test final 2026 porte sur au plus 5 candidats (PASS d'abord, puis CONDITIONNEL) ; **tous**
   les résultats 2026 sont rapportés, pas seulement le meilleur.
4. Tout nouvel accès à la période VAL (2022-2025) est journalisé et compté dans le rapport final.

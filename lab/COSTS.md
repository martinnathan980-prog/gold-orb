# Frais réels de trading sur l'or (XAUUSD) — scénarios de l'amendement 1

*Fixé le 2026-11-05, à partir de la recherche documentée ci-dessous, **avant** toute application à un candidat.*
Données brutes, sources et vérifications : `results/costs_research.json` (4 enquêtes web, 99 relevés de courtiers, 2 vérifications indépendantes).

## Ce que dit la recherche (aller-retour à 4 000 $/oz, entrée et sortie au marché ou par stop)

| Profil | Écart (spread) | Commission | Slippage | Total / oz |
|---|---|---|---|---|
| **Modèle du protocole (principal)** | Dukascopy réel, ~0,60 $ fin 2025 (1,5 pb) | 0,07 $ | 1,5 pb/côté (2 × 0,60 $) | **≈ 1,87 $** |
| Courtier ECN à bas coûts (compte « raw » UE, MT5) | 0,08–0,12 $ publiés en 2026 (≈ 0,3 pb) | 0,07 $ (3,50 $/lot/côté) | ≈ 0,5–0,75 pb/côté | ≈ 0,59 $ |
| Compte standard d'un courtier UE grand public | 0,23–0,50 $, médiane ≈ 0,35 $ (≈ 0,9 pb) | 0 | ≈ 1 pb/côté | ≈ 1,16 $ |
| Mauvaises conditions (plateforme chère, stops qui glissent) | ≈ 0,80 $ (2 pb) | 0,07 $ | 2 pb/côté | ≈ 2,47 $ |

Exemples de courtiers accessibles depuis la France (entités CySEC) : IC Markets (EU) Raw Spread — moyenne XAUUSD affichée 0,08 $ + 7 $/lot aller-retour ; Pepperstone EU Razor — 0,12 $ en moyenne (août 2026, rollover inclus) + 7 $/lot ; Tickmill Europe Raw — ≈ 0,09 $. Comptes standard : Pepperstone EU Standard 0,23–0,25 $, IG France 0,30 $, XTB 0,35 $, FxPro 0,38 $, Admirals 0,49 $, Capital.com 0,50 $.

**Verdict :** le modèle du protocole est **prudent** : environ 3 fois les frais d'un bon compte ECN, 1,6 fois ceux d'un compte standard en conditions normales. Il correspond à « compte standard avec des stops qui glissent ». Le stress ×1,5 du protocole (≈ 2,81 $) couvre le scénario « mauvaises conditions ».

## Corrections apportées par les vérificateurs (et retenues)
1. **Années 2013–2021 :** les écarts en dollars n'étaient **pas** proportionnels au prix. Un compte ECN payait ≈ 0,07–0,12 $ (et non 0,04 $), un compte standard ≈ 0,35 $ (FXCM 2018 : 0,357 $). Le multiplicateur d'écart est donc fixé de façon à rester réaliste **sur toute la période**, quitte à être prudent sur 2022–2025.
2. **Slippage des ordres stop sur compte ECN :** aucune statistique officielle ; le seul relevé réel (compte IC Markets, 2026) implique ≥ 0,78 pb par entrée stop → **0,75 pb/côté** (et non 0,5).
3. **Swap vendeur :** actuellement *crédité* chez la plupart des courtiers (≈ +1,8 à +3,1 %/an), mais rien de fiable sur 2013–2021 → on ne compte **aucun crédit** (0 % en ECN, coût de 1,5 %/an en standard).

## Paramètres retenus pour le simulateur (`audit/cost_scenarios.json`)

| Scénario | spread_mult (× Dukascopy) | slip_bps / côté | commission $/oz | swap achat | swap vente |
|---|---|---|---|---|---|
| low_cost_ecn | 0,35 (≈ 0,10 $ en 2013–21, ≈ 0,20 $ fin 2025 : prudent vs 0,08–0,12 $ publiés) | 0,75 | 0,07 | 4,6 %/an | 0 |
| typical_retail | 1,0 (≈ 0,30 $ en 2013–21, ≈ 0,60 $ fin 2025 : prudent vs 0,35 $) | 1,0 | 0 | 6 %/an | 1,5 %/an |
| conservative | 1,5 | 2,0 | 0,07 | 8 %/an | 3 %/an |

Règle de l'amendement 1 : **CONDITIONNEL** = échoue avec le modèle principal mais passe **tous** les critères (2013–2021 et 2022–2025) avec `low_cost_ecn`. Un candidat CONDITIONNEL n'est viable que chez un courtier ECN à bas coûts.

## Contraintes réglementaires (client particulier en France)
Décision AMF du 1er août 2019 (mesures ESMA) : levier max **20:1 sur l'or** (marge 5 %), clôture des positions quand les fonds propres passent sous 50 % de la marge initiale, protection contre le solde négatif, bonus interdits. Ces protections ne s'appliquent qu'aux clients « particuliers ».

## Horaires à éviter
Réouverture quotidienne 18:00–18:05 New York : écart × 1,5 à 2,6 chez Dukascopy, × 8 à 11 chez un courtier ECN ; dimanche soir à l'ouverture : 0,9–3,5 $. Pas de cotation de 17:00 à 18:00 New York.

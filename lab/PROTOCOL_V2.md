# Protocole n°2 (pré-enregistré le 2026-11-10, AVANT tout test de la 2ᵉ recherche)

## 1. Objectif (fixé par l'utilisateur)
Un robot 100 % automatique sur MetaTrader 5, compte **FP Markets Standard, levier 1:500, capital 1 000 €**
qu'il accepte de perdre, **arrêt définitif à −50 %** (500 €). Plusieurs trades par jour, pertes coupées
vite, croissance la plus rapide possible. Cible déclarée : +50 % par mois. Engagement du labo : chercher
le maximum, puis donner pour chaque niveau de mise le gain médian par mois, la probabilité d'un mois à
+50 % et la probabilité de toucher l'arrêt. « Rien ne passe » reste un résultat possible et sera dit.

## 2. Ce qui est nouveau par rapport au protocole n°1
- **Marchés jamais testés ici** : Nasdaq 100 (us100), S&P 500 (us500), Dow (us30), DAX (ger40, vrai
  bid+ask), bitcoin (btcusd), ether (ethusd), argent (xagusd), en plus de l'or.
- **Portefeuille de petites règles (« manches »)** au lieu d'une règle unique ; plusieurs positions
  possibles en même temps.
- **Frais du vrai compte** (section 3) au lieu du modèle prudent n°1.

## 3. Modèle de frais (figé avant les tests ; valeurs dans `r2/fp_costs.json`)
- **Modèle principal « FP d'aujourd'hui »** : écart achat/vente du compte FP Markets Standard d'aujourd'hui,
  exprimé en points de base du prix et appliqué à tout l'historique (forme intraday reprise de
  Dukascopy : élargissement au rollover, hors séance, aux annonces). Pas de commission.
  Glissement : X pb par côté sur les ordres stop, Y pb sur les ordres au marché. Swap annuel par actif.
- Raison : la question est « que rapporterait cette règle à partir de maintenant », et les frais relatifs
  ont été divisés par ~3 en dix ans (écart en points stable, prix triplés).
- **Garde-fous** : (a) stress frais ×1,5 ; (b) résultat brut (sans frais) rapporté par période pour
  vérifier que l'avantage brut ne s'est pas érodé ; (c) pour les finalistes, modèle « historique »
  (écart Dukascopy réel) rapporté à titre d'information.
- Les valeurs provisoires du 2026-11-10 sont remplacées par la recherche documentée FP Markets dès
  qu'elle est vérifiée ; tous les finalistes sont alors recalculés. Aucune règle n'est choisie sur les
  valeurs provisoires sans ce recalcul.

## 4. Découpage et critères d'une manche
| Période | Dates | Usage |
|---|---|---|
| IS | début des données → 2021-12-31 | recherche libre (≤ 120 configurations par piste, toutes journalisées) |
| VAL | 2022-01-01 → 2025-12-31 | **une fois**, pour la config choisie sur IS ; accès journalisé |
| HOLDOUT | 2026 | hors du disque de recherche ; **un seul regard**, sur le portefeuille figé |

Sur IS : ≥ 250 trades ; gain/perte (PF) ≥ 1,12 ; t ≥ 2,5 ; ≥ 60 % des années positives ; PF ≥ 1,04 avec
frais ×1,5 ; voisins de réglage : PF médian ≥ 1,06 ; espérance > 0 aussi quand **chaque signal** est pris
(leçon du protocole n°1) ; durée max ≤ 5 jours de bourse ; et **battre le hasard à structure identique** :
l'espérance de la règle doit dépasser 97,5 % de 200 rejeux où les mêmes trades (même sens, mêmes stops,
mêmes durées) sont pris à des moments tirés au sort (`r2.null_test` ; même heure / jour au hasard pour une
règle à signal, moment entièrement au hasard pour une règle de calendrier). Ce test écarte ce qui n'est
que « le marché a monté ».
Une même règle appliquée avec les mêmes réglages à plusieurs marchés peut être jugée en **panier** (trades
réunis) si son espérance est positive sur chaque marché du panier.
Sur VAL : PF ≥ 1,06, espérance > 0, et espérance > 0 quand chaque signal est pris.
Pas de retouche après VAL. Les pistes or réutilisent un VAL déjà consulté au protocole n°1 pour d'autres
règles : c'est signalé, et le test 2026 + la démo font foi.

## 5. Portefeuille et test final
- Entrent au portefeuille **toutes** les manches qui passent IS et VAL, à risque égal par trade (aucune
  optimisation des poids sur VAL). Au plus 2 manches par piste.
- Tableau de mise : rééchantillonnage par blocs de 4 semaines de l'historique IS+VAL du portefeuille
  (et VAL seul), pour un risque par trade de 1 à 10 % : gain médian/mois, P(mois ≥ +50 %), P(arrêt −50 %)
  à 3 et 6 mois ; plus la simulation du compte réel (lots minimum, marge).
- **Test 2026, un seul regard, portefeuille figé** : réussite si le portefeuille gagne (PF > 1).
  Lecture annoncée d'avance : PF ≥ 1,3 soutien fort ; 1,0–1,3 cohérent mais faible ; < 1,0 contre.
  Chaque manche est rapportée, pas seulement le total.
- Ensuite seulement : robot en démo, puis compte réel de 1 000 €.

## 6. Contrôles
Revue contradictoire de chaque finaliste par des agents indépendants (triche au futur, hasard/sélection,
exécution réelle), comme au protocole n°1. Le nombre total d'essais (n°1 : 321) est rapporté avec les
résultats.

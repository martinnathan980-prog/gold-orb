# GardeFou — mode d'emploi court

Programme MT5 qui **ne prend aucun trade** : tu décides, il protège. Il surveille toutes tes positions et applique tes règles sans émotion.

## Les règles (réglages par défaut)
- **Stop obligatoire.** Sans stop au bout de 60 s, il le pose à la distance du risque maximum.
- **Stop jamais éloigné ni retiré.** Il est remis immédiatement.
- **Risque maximum par trade : 10 % du solde.** Au-delà, il réduit la taille.
- **Une seule position à la fois, pas d'ajout.**
- **Pause de 6 h** après chaque entrée et après chaque perte.
- **Perte maximale du jour : 10 %.** Tout est fermé, blocage jusqu'au lendemain.
- **Pas d'entrée 30 min avant ou après une annonce forte en USD** (emploi, inflation, Fed : calendrier intégré à MT5).
- Toute position ouverte pendant un blocage est **fermée aussitôt**.
- **Durcir une règle : immédiat. L'assouplir : 24 h plus tard.**

## Installation
1. Copie `GardeFou.mq5` dans `MQL5\Experts\`, puis compile-le dans MetaEditor (F7). Envoie-moi l'erreur exacte s'il y en a une.
2. Attache-le à **un seul** graphique (n'importe quel symbole) et active **Algo Trading**. Il surveille tout le compte.
3. Pour les notifications push : Outils > Options > Notifications, puis ton MetaQuotes ID.

## Test sur compte démo (10 minutes)
1. Ouvre un trade **sans stop** : 60 s plus tard, un stop doit apparaître.
2. Mets un stop, attends 60 s, puis **éloigne-le** : il doit revenir.
3. Ouvre un **2e trade** : il doit être fermé aussitôt.
4. Ferme le 1er trade **en perte**, puis rouvre : fermé aussitôt (pause de 6 h).
5. Mets `InpMaxRiskPct` à 1 et ouvre un gros lot : la taille doit être réduite.

Chaque intervention est notée dans `%APPDATA%\MetaQuotes\Terminal\Common\Files\GardeFou\journal_<compte>.csv`.

## Limites (honnêtes)
- Si tu **retires** le programme ou coupes Algo Trading, il ne protège plus. Il te prévient quand Algo Trading est coupé. Pour plus de friction, fais-le tourner sur un **VPS** (VPS MetaQuotes, environ 10-15 $/mois).
- Supprimer son fichier d'état remet les règles à zéro : c'est de la friction, pas un coffre-fort.
- À 10 % par trade et 10 % par jour, **un seul stop plein bloque la journée**.

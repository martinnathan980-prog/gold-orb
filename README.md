# gold-orb

Dépôt personnel regroupant deux sujets indépendants.

## `gates-analytics/`

Tableau de bord Google Apps Script de suivi des plans d'intégration électrique
(KPI d'avancement FWD, historique hebdomadaire, jalons, tableau filtrable).
Voir [`gates-analytics/README.md`](gates-analytics/README.md) pour l'installation,
la configuration et le détail des corrections.

```bash
cd gates-analytics && npm test
```

## Données de marché

Scripts de téléchargement des données Dukascopy via
[`dukascopy-node`](https://github.com/Leo4815162342/dukascopy-node),
stockées compressées dans `download/`.

| Script | Rôle |
|---|---|
| `dl.sh` | Bougies M1 XAUUSD, bid et ask, année par année. |
| `dl2.sh` | Bougies M1 des marchés de comparaison (EURUSD, GBPUSD, USDJPY, DAX, WTI). |
| `ticks.sh` | Ticks XAUUSD mois par mois, compression et contrôle de la limite de 100 Mo. |

```bash
bash dl.sh                    # 2013 → 2025
bash dl.sh 2020 2022          # plage précise
bash dl2.sh eurusd            # un seul instrument
bash ticks.sh 2025-01 2025-05 # plage de mois
POUSSER=1 bash ticks.sh       # avec commit + push
```

Les trois scripts **ignorent les fichiers déjà téléchargés** : les relancer
reprend là où ça s'était arrêté au lieu de tout refaire.

### Corrections apportées à ces scripts

- **`ticks.sh` commençait par `git reset --mixed origin/main`**, ce qui écartait
  sans prévenir tout commit local non poussé. Supprimé : un script de
  téléchargement n'a pas à réécrire l'historique git.
- **Les mois s'arrêtaient au 28** (`-to 2025-$m-28`) : 2 à 3 jours de ticks
  manquaient à chaque mois. La borne de fin est maintenant le 1er du mois suivant.
  Les fichiers déjà présents au format `…-28` sont signalés comme incomplets.
- **Les fichiers dépassant 100 Mo étaient supprimés.** Ils sont désormais déplacés
  dans `download/trop-gros/` (ignoré par git) : des heures de téléchargement ne
  sont plus perdues pour une limite d'hébergement.
- **Le commit et le push étaient automatiques**, et `git push` sans argument
  pouvait viser la mauvaise branche. Ils sont maintenant explicites (`POUSSER=1`)
  et poussent sur la branche courante avec `-u origin`.
- `set -euo pipefail`, shebang et `cd` vers le dossier du script partout ;
  `stat -c%s` (spécifique GNU) remplacé par `wc -c`.
- Le fichier d'échange nano `.d.sh.swp`, commité par erreur, a été retiré du suivi
  et un `.gitignore` empêche que cela se reproduise.

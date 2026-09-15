# Procédure hebdomadaire

## En deux gestes

1. Dans GATES, **Exporter**.
2. Dans le classeur, onglet **Données** : `Ctrl+A`, `Suppr`, puis coller l'export en `A1`.

C'est tout. Le relevé est archivé **tout seul**, à la fermeture du classeur ou
à l'ouverture du tableau de bord.

## Ce que vous ne faites jamais

| ❌ | ✅ |
|---|---|
| Créer une nouvelle feuille par import | Toujours le même onglet **Données**, écrasé |
| Toucher à l'onglet **Historique** | Il se remplit seul, laissez-le masqué |
| Garder les anciens exports | L'historique en garde le résumé, c'est suffisant |

L'onglet **Données** ne contient donc **que le dernier export**. Tout ce qui doit
survivre est déjà dans l'onglet **Historique**.

## Les deux onglets

**Données** — votre export collé tel quel. Colonnes dans l'ordre de GATES, la page
s'adapte à ce qu'elle y trouve. Vous n'avez rien à réorganiser.

**Historique** (masqué) — une ligne par semaine, écrite automatiquement :

| Semaine | Date | Total | Terminés | En cours | À faire | Non renseignés | Par ATA | Plans |
|---|---|---|---|---|---|---|---|---|
| 2026-S37 | 08/09/2026 | 186 | 58 | 71 | 34 | 23 | `{…}` | `{…}` |
| 2026-S38 | 15/09/2026 | 186 | 63 | 69 | 33 | 21 | `{…}` | `{…}` |

- `Par ATA` sert aux projections par groupe.
- `Plans` garde l'avancement plan par plan. **Rien n'est jamais effacé** : tout
  l'historique est conservé, y compris le détail. C'est ce qui permet de dire
  « 2 passés en terminé, 5 nouveaux » — et ce qui permettra demain des analyses
  qu'on n'a pas encore imaginées.

## Plusieurs imports dans la même semaine

Aucun problème : **une ligne par semaine ISO**. Le dernier import de la semaine
remplace le précédent. Vous pouvez importer trois fois le mardi, le graphique
n'affichera qu'un point pour cette semaine.

## Une semaine sans import

Aucun problème non plus. Le graphique reste régulier : s'il s'écoule trois
semaines entre deux relevés, le gain est **réparti sur les trois semaines** dans
la bande « terminés par semaine ». Les hauteurs restent comparables quelle que
soit votre cadence.

Le pied de page rappelle la date du dernier import.

## Si vous vous trompez d'export

Menu **GATES Analytics ▸ Supprimer le dernier relevé**. La ligne de la semaine
courante est retirée de l'historique ; recollez le bon export, il sera réarchivé.

## Le premier import

Le graphique affichera **un seul point** et le dira. C'est normal : GATES ne
fournit que l'état du jour, on ne peut pas reconstituer le passé. L'historique
se construit à partir de là, un relevé par semaine.

Au deuxième import apparaissent le comparatif et la première mesure de rythme ;
la projection devient fiable au bout de cinq ou six semaines.

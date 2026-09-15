# Import des exports GATES

GATES ne fournit qu'une photo : l'état du jour. **On ne peut pas reconstituer
le passé, seulement l'accumuler.** C'est ce que fait ce dossier : un relevé
archivé par import, et l'historique se construit de lui-même.

## Usage

```bash
python releve.py export.csv
```

Sortie :

```
Relevé 2026-S38 archivé (2 au total)
  7 plans : 3 terminés (43 %), 3 en cours, 1 à faire, 0 non renseignés
  depuis le dernier import : 2 ont avancé, 1 ont reculé, 1 vient d'être renseigné,
  1 nouveau, 0 disparu
  ATTENTION, avancement en recul : UD-31-0005
```

Deux fichiers sont tenus à jour dans `donnees/` :

| Fichier | Contenu |
|---|---|
| `releves.csv` | un relevé par semaine ISO : comptes globaux et par ATA |
| `plans.json` | l'avancement plan par plan du dernier import, pour comparer au suivant |

Réimporter dans la même semaine **met à jour** la ligne au lieu d'en ajouter une.

## Ce que le script tolère

- une ou plusieurs lignes de titre au-dessus de l'en-tête réel ;
- une ligne de groupes fusionnés au-dessus des noms de colonnes ;
- un séparateur `;` ou `,` (détecté automatiquement) ;
- un BOM UTF-8 en tête de fichier ;
- des colonnes déplacées ou renommées — elles sont retrouvées par mots-clés
  (`CLES` en haut du fichier), pas par position.

Si une colonne indispensable manque, le script s'arrête **en affichant les
en-têtes qu'il a lus**, pour qu'on voie tout de suite quoi ajuster.

## Les quatre états

Identiques à ceux du tableau de bord :

| État | Règle |
|---|---|
| terminé | `>= 100`, ou « terminé / achevé / clôturé / soldé / fini » |
| en cours | valeur strictement entre 0 et 100 |
| à faire | `<= 0`, ou « à faire » |
| non renseigné | cellule vide |

« À faire » est une valeur saisie ; une cellule vide est un **défaut de saisie**.
Les confondre masquerait le second — c'est précisément ce qu'on veut voir.

## Automatiser l'export lui-même

Ce script part d'un CSV déjà exporté. Pour supprimer aussi le clic d'export,
voir `export_gates.py` (à écrire une fois la page GATES connue) : il pilote le
navigateur **déjà ouvert et déjà authentifié**, de sorte qu'aucun mot de passe
n'est stocké nulle part.

À valider avec l'IT avant mise en place.

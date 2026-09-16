# Suivi FWD — mise en place et usage hebdomadaire

## 1. Installer le script (une seule fois)

Dans le classeur Google Sheets :

1. **Extensions → Apps Script**.
2. Créer les fichiers suivants et y coller le contenu de ce dossier, à
   l'identique. Le nom compte : Apps Script retrouve les fichiers par leur nom.

   | Dans Apps Script | Type | Fichier à coller |
   |---|---|---|
   | `Code.gs` | Script | `Code.gs` |
   | `Index` | HTML | `Index.html` |
   | `Styles` | HTML | `Styles.html` |
   | `Javascript` | HTML | `Javascript.html` |

   Pour créer un fichier HTML : **+ → HTML**, puis saisir le nom **sans**
   l'extension (`Index`, et non `Index.html`).

3. Facultatif mais recommandé : **Projet → Paramètres → Afficher
   « appsscript.json »**, puis y coller `appsscript.json`.
4. **Enregistrer**, puis recharger le classeur.

Un menu **Suivi FWD** apparaît dans la barre du haut.

La première ouverture demande une autorisation Google : c'est normal, le script
lit le classeur et y écrit l'onglet d'historique.

## 2. Ouvrir le tableau de bord

**Suivi FWD → Ouvrir le tableau de bord.**

Pour le partager à quelqu'un qui n'ouvre pas le classeur :
**Déployer → Nouveau déploiement → Application Web**, exécuter en tant que
soi-même, accès selon la politique de l'entreprise. Le lien obtenu ouvre la
même page.

## 3. Le geste de chaque semaine

1. Dans GATES, exporter la liste en CSV.
2. Ouvrir l'onglet **Données** du classeur, `Ctrl+A`, `Suppr`, puis coller
   l'export en **A1**.
3. **Suivi FWD → Archiver le relevé de cette semaine.**

C'est tout. Ne jamais créer un nouvel onglet : le tableau de bord lit toujours
le premier onglet visible.

L'étape 3 peut se faire toute seule : **Suivi FWD → Activer l'archivage
automatique**, et un relevé est pris chaque vendredi vers 17 h.

## 4. Ce que devient l'historique

GATES ne donne qu'une photo du jour : l'export ne dit pas *quand* un plan est
passé à 100 %. L'historique ne peut donc pas être reconstitué après coup — il
s'accumule, un relevé par semaine, dans l'onglet masqué **Historique_FWD**.

- Un seul relevé par semaine ISO : réimporter le lundi puis le jeudi met la
  ligne à jour, elle ne se dédouble pas.
- **Rien n'est jamais supprimé.** Chaque relevé garde les comptes globaux, les
  comptes par colonne, et l'avancement plan par plan.
- Mauvais export collé par erreur ? **Suivi FWD → Supprimer le relevé de cette
  semaine**, recoller le bon, ré-archiver.

Pour consulter l'onglet : clic droit sur un onglet → *Afficher les feuilles
masquées* → `Historique_FWD`. Le remasquer ensuite n'est pas obligatoire.

## 5. Ce que le script devine tout seul

Aucun nom de colonne n'est écrit en dur.

- **La ligne d'en-têtes** est cherchée dans les huit premières lignes : les
  lignes de titre de l'export ne gênent pas.
- **La ligne au-dessus** est prise pour des groupes de colonnes fusionnés, et
  propagée vers la droite.
- **L'avancement FWD** est la colonne dont l'en-tête ou le groupe parle de FWD
  et d'avancement.
- **La référence** est la colonne qui identifie un plan ; elle reste figée à
  gauche du tableau.
- **Les dimensions** de « Avancement FWD par… » sont les colonnes qui se
  comportent comme des catégories : entre 2 et 40 valeurs distinctes. Une
  colonne de commentaires ou d'identifiants en est donc exclue d'office.
- **La date de création**, si elle existe, ajoute la dimension « ancienneté ».

Si les colonnes de l'export changent, il n'y a rien à modifier : recoller et
ré-archiver suffit.

## 6. Les quatre états

| État | Ce qui le déclenche |
|---|---|
| **Terminé** | `100 %`, `terminé`, `achevé`, `clôturé`, `soldé`, `fini`, `ok` |
| **En cours** | tout pourcentage strictement entre 0 et 100, `en cours`, ou tout autre texte |
| **À faire** | `à faire`, `non commencé`, `0 %` |
| **Non renseigné** | cellule vide, ou `-` |

« À faire » est une valeur *saisie*. Une cellule vide est un *défaut de
saisie*. Les confondre masquerait le second, qui est précisément ce qu'on
cherche à voir : le bouton « non renseignés » sous la barre sort la liste.

## 7. Les jalons

Se posent en cliquant une semaine sur le graphique, se déplacent à la souris ou
aux flèches du clavier, se retirent par la croix. Ils sont **partagés** : ils
vivent dans le classeur, pas dans le navigateur. Ce que pose la collègue, sa
chef le voit.

Le jalon à venir le plus proche pilote les colonnes « à solder/sem. » et
« effort demandé » du bloc par ATA. Sans jalon, ces colonnes laissent la place
au rythme actuel.

## 8. Ce qui reste local à chaque personne

L'ordre des colonnes, celles qui sont masquées, le tri et le cadrage du
graphique sont retenus dans le navigateur de chacun. Personne n'impose sa mise
en page à personne.

# Le relevé de fin de démo (ReleveFP 1.11)

**Quand :** le dernier jour de la démo, avec le robot toujours en marche. Au plus tard une semaine après la fin.

**Ce que fait le script :** il relève les prix et les frais du courtier. Il enregistre aussi l'historique des transactions du compte (achats, ventes, commissions, swaps) et les positions ouvertes.

Il ne passe aucun ordre et ne demande aucun mot de passe. Il n'écrit ni ton nom, ni ton numéro de compte, ni le nom du serveur.

---

## 1. Installer le script

1. Télécharge `ReleveFP.mq5` depuis le chat. Clique une fois dessus, puis Cmd + I. Le nom doit être exactement `ReleveFP.mq5`. S'il y a `.txt` à la fin, efface-le.
2. Dans le Finder : Aller → Aller au dossier… (Maj + Cmd + G). Colle cette ligne, puis Entrée :

   ```
   ~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Scripts
   ```

3. Glisse `ReleveFP.mq5` dans cette fenêtre. Si le Mac propose de remplacer l'ancien fichier : Remplacer.
4. Compile-le :
   - Dans MetaTrader, appuie sur F4 (ou fn + F4).
   - À gauche, ouvre Scripts. Double-clique sur ReleveFP.mq5. Clique sur « Compiler ».
   - En bas, dans l'onglet « Erreurs », tu dois lire « 0 errors ». Sinon, arrête-toi et envoie-moi une capture.
   - Ferme MetaEditor.
5. Vérifie les barres max : Outils → Options → Graphiques. « Nombre maximum de barres dans le graphique » (Max. bars in chart) doit être 500000. Sinon : mets 500000, clique sur OK, quitte MetaTrader (Cmd + Q) et rouvre-le. Le robot repart tout seul.

## 2. Lancer le relevé

6. Ne touche pas au graphique du robot. Ouvre un autre graphique : Fichier → Nouveau graphique → EURUSD (n'importe quel marché convient).
7. Affichage → Navigateur. Ouvre Scripts. Glisse ReleveFP sur ce nouveau graphique.
8. Une fenêtre s'ouvre. Va dans l'onglet « Paramètres d'entrée » et ne change rien. Tu dois lire ces six lignes (à gauche le nom, à droite la valeur) :

   | Nom | Valeur |
   |---|---|
   | Marches (noms de base, du plus important au moins important) | BTCUSD,ETHUSD,US100,XAUUSD,USDJPY,JP225,EURUSD,US500,GER40 |
   | Jours d'historique de ticks a relever | 30 |
   | Barres M1 du terminal (r1_<marche>.csv) : marche:jours | XAUUSD:200,US100:100,BTCUSD:100,ETHUSD:100 |
   | Attente maximale (secondes) du chargement des barres M1 d'un marche | 300 |
   | Passer au marche suivant apres ce nombre de jours vides d'affilee | 6 |
   | Ecrire aussi la liste de tous les marches du courtier | true |

   - Une valeur est différente ? Clique sur « Réinitialiser » (en bas de la fenêtre) : MetaTrader reprend les valeurs du script.
   - Tu lis encore autre chose, ou la ligne « Barres M1 du terminal » n'existe pas ? C'est l'ancien script : clique sur Annuler et refais l'étape 4.
   - Sinon, clique sur OK.
9. En haut à gauche du graphique, tu lis : « Releve FP Markets en cours (aucun ordre n'est passe) ». Laisse le Mac allumé, branché et connecté, sans mise en veille. Ne ferme pas MetaTrader.
10. Le relevé prend en général 10 à 30 minutes, et jusqu'à environ 1 heure si MetaTrader doit télécharger beaucoup d'historique. Il peut rester plusieurs minutes sur un marché : c'est normal. À la fin, il lit l'historique des transactions du compte en quelques secondes.
11. C'est fini quand l'alerte « Releve termine : … marches sur 9. Vous pouvez le dire a Claude. » s'affiche. Moins de 9 ? Dis-le-moi, c'est tout.

## 3. Vérifier fini.txt

12. Dans le Finder, fais Aller au dossier… et colle :

    ```
    ~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/claude/releve
    ```

    Double-clique sur `fini.txt`. S'il n'existe pas, le relevé n'est pas fini (le script l'efface au départ et l'écrit en dernier) : attends l'alerte, ou relance-le (étapes 7 à 11).

    | Tu dois lire | Sinon |
    |---|---|
    | Première ligne : `version=1.11` | C'est l'ancien script : refais l'étape 4, puis les étapes 7 à 11. |
    | Plus bas : `max_barres=500000` | Refais l'étape 5, puis les étapes 7 à 11. |
    | Vers la fin : `positions=` suivi d'un nombre (0 ou plus), `deals=` suivi d'un nombre plus grand que 0, puis `erreur_deals=0` | `positions=-1`, `deals=0`, `deals=-1` ou un autre nombre après `erreur_deals=` : dis-le-moi, c'est tout. |
    | Vers la fin : `stopped=0` | `stopped=1` : le script a été arrêté. Relance-le (étapes 7 à 11). |

    Dans ce dossier, tu vois aussi `deals.csv` (l'historique des transactions) et `positions.csv` (les positions ouvertes). Ne les ouvre pas avec Numbers ni Excel, et ne les modifie pas.

## 4. M'envoyer les fichiers

13. Envoie les fichiers comme dans la partie 5 du guide de la démo (« À la fin de la démo ») : dans le dossier MQL5, sélectionne Files et Logs, clic droit → Compresser, puis envoie `Archive.zip`.
    - Le dossier releve compressé pèse environ 13 Mo (entre 10 et 20 Mo). L'historique des transactions ajoute moins de 1 Mo.
    - Trop gros pour le chat ? Compresse Files et Logs chacun à part.
14. Laisse le robot tourner jusqu'à ce que je te dise de l'arrêter.

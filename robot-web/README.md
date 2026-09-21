# autoweb — robot de saisie web piloté par Excel

Vous avez des centaines de plans (ou dossiers, demandes, fiches…) à saisir dans
des outils web, un par un, à la main. **autoweb** fait la saisie à votre place :

1. vous listez les éléments dans un **fichier Excel** (une ligne = un élément) ;
2. vous décrivez **une fois** les clics et saisies à faire, dans un petit fichier
   texte (le *scénario*, en français) ;
3. le robot ouvre votre navigateur, traite chaque ligne, et écrit dans l'Excel
   **Statut / Message / Horodatage** (et ce qu'il relève dans l'outil, par
   exemple la référence attribuée). Le suivi, c'est l'Excel.

Conçu pour un **poste d'entreprise** : Python seulement (pas de `.exe` à
télécharger, pas de droits administrateur), utilise le **Edge ou Chrome déjà
installé**, et sait se brancher sur votre navigateur déjà connecté (SSO).

---

## 1. Installation (5 minutes)

Prérequis : Python 3.9 ou plus (`python --version`).

```bat
cd robot-web
python -m pip install --user -r requirements.txt
python -m autoweb demo
```

`demo` ouvre un faux outil web (une page HTML locale), saisit 4 lignes d'un
Excel de démonstration (dont 1 en erreur volontaire) et vous dit si votre poste
est prêt. Le dossier `demo/` créé contient l'Excel rempli, les captures et le journal.

Sous Windows vous pouvez aussi double-cliquer sur `installer.bat`.

**Derrière un proxy d'entreprise**, si `pip` échoue :

```bat
set HTTPS_PROXY=http://proxy.entreprise:8080
python -m pip install --user --proxy %HTTPS_PROXY% --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
```

**Si aucun navigateur n'est trouvé** (message « Aucun navigateur n'a pu être lancé ») :
- indiquez le chemin de votre Edge dans le scénario (`navigateur: executable: ...`), ou
- installez le navigateur de Playwright, qui est un simple dossier décompressé
  dans votre profil utilisateur : `python -m playwright install chromium`, ou
- branchez-vous sur un Edge déjà ouvert (section 6).

---

## 2. Démarrer votre premier outil

```bat
python -m autoweb initialiser mon_outil --nom "Saisie des plans" --colonnes "Numéro plan,Titre,Type,Date,Urgent,Commentaire"
```

Cela crée `mon_outil/saisie_des_plans.yaml` (scénario modèle commenté) et
`mon_outil/suivi.xlsx` (Excel vide avec vos colonnes + Statut/Message/Horodatage).

Ensuite :

| Étape | Commande |
|---|---|
| Trouver les sélecteurs des champs de votre outil | `python -m autoweb inspecter https://votre-outil/...` |
| Ou enregistrer vos clics pour vous en inspirer | `python -m autoweb enregistrer https://votre-outil/...` |
| Vérifier scénario + colonnes Excel | `python -m autoweb verifier mon_outil/saisie_des_plans.yaml` |
| Voir ce qui serait fait, sans navigateur | `python -m autoweb simuler mon_outil/saisie_des_plans.yaml` |
| Lancer sur UNE ligne pour valider | `python -m autoweb lancer mon_outil/saisie_des_plans.yaml --limite 1` |
| Lancer tout | `python -m autoweb lancer mon_outil/saisie_des_plans.yaml` |

Le robot ne traite que les lignes dont le **Statut est vide ou « A faire »**.
Les lignes OK sont laissées tranquilles : vous pouvez ajouter des lignes dans
l'Excel et relancer la même commande autant de fois que nécessaire.

---

## 3. L'Excel de suivi

- Ligne 1 = noms de colonnes (n'importe lesquels : ce sont eux que vous utilisez dans le scénario avec `{{Nom de colonne}}`).
- Colonnes gérées par le robot (créées si absentes) : **Statut** (`OK`, `ERREUR`, `IGNORE`), **Message** (cause de l'erreur, avec le nom de la capture d'écran), **Horodatage**.
- Les colonnes relevées par l'étape `lire` (ex. `Référence outil`) sont créées à droite.
- Une copie de sauvegarde est faite dans `sauvegardes/` à chaque lancement (10 dernières conservées).
- **Fermez le fichier dans Excel pendant le traitement** : Excel verrouille le fichier ; si c'est le cas le robot vous demande de le fermer et réessaie.
- Les formules sont conservées ; le robot lit leur dernière valeur calculée par Excel.

Options de relance :

```bat
python -m autoweb lancer scenario.yaml --reprendre-erreurs      # retraite aussi les lignes ERREUR
python -m autoweb lancer scenario.yaml --lignes 12,15-20        # numéros de lignes Excel
python -m autoweb lancer scenario.yaml --tout --limite 3        # retraite tout, 3 lignes max
python -m autoweb lancer scenario.yaml --cache                  # navigateur invisible
python -m autoweb lancer scenario.yaml --inspecter-si-erreur    # ouvre l'inspecteur quand une ligne échoue
python -m autoweb lancer scenario.yaml --arret-premiere-erreur
python -m autoweb lancer scenario.yaml --var url_base=https://recette.outil.local
```

`Ctrl+C` arrête proprement : l'Excel est sauvegardé, relancez la même commande pour reprendre.

---

## 4. Écrire un scénario

Un scénario est un fichier YAML (texte) en quatre parties :

```yaml
nom: Saisie des plans
navigateur:
  canal: auto              # Edge installé, sinon Chrome, sinon chromium Playwright
  profil: profils/plans    # garde la session (cookies) d'une exécution à l'autre
  visible: true
excel:
  fichier: suivi.xlsx
  feuille: Suivi
  colonne_libelle: Numéro plan
variables:
  url_base: https://mon-outil.entreprise.local

avant:                     # une fois au début
  - aller: "{{url_base}}/plans"
  - si:
      visible: "texte=Se connecter"
      alors:
        - pause: "Connectez-vous, puis Entrée"

etapes:                    # pour CHAQUE ligne de l'Excel
  - aller: "{{url_base}}/plans/nouveau"
  - remplir:
      "libelle=Numéro de plan": "{{Numéro plan}}"
      "#titre": "{{Titre}}"
      "#date": "{{Date | date:%d/%m/%Y}}"
  - choisir: {selecteur: "#type", valeur: "{{Type}}"}
  - cocher: {selecteur: "#urgent", valeur: "{{Urgent}}"}
  - cliquer: "role=button:Enregistrer"
  - verifier: {selecteur: ".alert-success", contient: "enregistré"}
  - lire: {selecteur: ".reference", vers: "Référence outil"}
  - capture: "captures/{{Numéro plan}}.png"
```

### Les actions

| Action | Exemple | Ce que ça fait |
|---|---|---|
| `aller` | `aller: "{{url_base}}/x"` / `aller: "fichier:page.html"` | ouvre une adresse (ou un fichier local, relatif au dossier du scénario) |
| `attendre` | `attendre: "#form"` / `{selecteur: ".spinner", etat: cache}` / `attendre: 500` | attend un élément (visible / cache / present / absent), une URL (`url:`), le chargement (`chargement: reseau`) ou N ms |
| `remplir` | `remplir: {"#a": "{{A}}", "#b": "{{B}}"}` ou `{selecteur, valeur, appuyer: Tab}` | vide le champ et écrit la valeur |
| `taper` | `taper: {selecteur: "#ville", valeur: "{{Ville}}", appuyer: Enter}` | tape touche par touche (champs à suggestions) |
| `effacer` | `effacer: "#a"` | vide un champ |
| `cliquer` | `cliquer: "texte=Enregistrer"` / `{selecteur, si_present: true}` / `{selecteur, nouvel_onglet: true}` / `double: true` | clic |
| `choisir` | `choisir: {selecteur: "#type", valeur: "{{Type}}"}` (ou `libelle:` / `index:`) | liste déroulante (valeur OU libellé de l'option) |
| `cocher` / `decocher` | `cocher: {selecteur: "#urgent", valeur: "{{Urgent}}"}` | case à cocher ; oui/non/x/1/vrai… |
| `touche` | `touche: Enter` / `{selecteur: "#a", touche: Tab}` | touche clavier |
| `survoler` | `survoler: "#menu"` | passe la souris (menus) |
| `televerser` | `televerser: {selecteur: "input[type=file]", fichier: "plans/{{Numéro plan}}.pdf"}` | joint un fichier |
| `telecharger` | `telecharger: {cliquer: "texte=Exporter", vers: "telechargements/", vers_colonne: Fichier}` | clique et enregistre le téléchargement |
| `lire` | `lire: {selecteur: ".ref", vers: "Référence outil", regex: "REF-(\\d+)"}` | relève un texte / une valeur / un attribut (`attribut: href`) et l'écrit dans l'Excel |
| `verifier` | `verifier: {selecteur: ".msg", contient: "enregistré"}` (`egal`, `valeur`, `coche`, `absent`, `cache`) ou `{texte_page: "Succès"}` | contrôle, sinon la ligne passe en ERREUR |
| `verifier_url` | `verifier_url: "/plans/"` | l'URL doit contenir ce texte |
| `capture` | `capture: "captures/{{Numéro plan}}.png"` (`page_entiere: true`) | capture d'écran |
| `journal` | `journal: "Ligne {{n}}/{{total}}"` | écrit dans le journal |
| `pause` | `pause: "Vérifiez puis Entrée"` | attend que vous appuyiez sur Entrée (`stop` pour arrêter) |
| `inspecter` | `- inspecter` | ouvre l'inspecteur Playwright (pour mettre au point) |
| `executer_js` | `executer_js: {script: "document.title", vers: "Titre"}` | exécute du JavaScript |
| `si` | voir ci-dessous | condition |
| `cadre` | `cadre: {selecteur: "iframe#contenu", etapes: [...]}` | étapes dans une iframe |
| `onglet` / `fermer_onglet` | `onglet: dernier` / `onglet: {titre: "Détail"}` | change d'onglet |
| `retour` / `recharger` | `- recharger` | navigation |
| `ignorer` | `ignorer: "pas de numéro"` | ligne IGNORE, on passe à la suivante |
| `echouer` | `echouer: "doublon détecté"` | ligne ERREUR, on passe à la suivante |
| `arreter` | `arreter: "outil indisponible"` | arrête tout le traitement |

Sur n'importe quelle étape : `nom: "Valider le formulaire"` (pour le journal),
`optionnel: true` (une erreur n'arrête pas la ligne), `delai_max: 30000` (ms).
Les alias anglais (`goto`, `fill`, `click`, `select`, `check`, `wait`…) sont acceptés.

### Conditions (`si`)

```yaml
- si:
    valeur: "{{Urgent}}"       # une valeur de l'Excel...
    vrai: true                 # ...ou egal: X / different: X / contient: X / vide: true / non_vide: true
    alors:
      - cocher: "#urgent"
- si:
    present: "#popup"          # ou absent: / visible: / cache: (sélecteur, attente courte : delai: 2000)
    alors:
      - cliquer: "#popup .fermer"
    sinon:
      - journal: "pas de popup"
```

### Les sélecteurs (comment désigner un élément de la page)

| Forme | Exemple | Remarque |
|---|---|---|
| CSS | `#numero`, `input[name=titre]`, `.btn-primary` | le plus stable quand l'élément a un `id` ou un `name` |
| Libellé | `libelle=Numéro de plan` | le champ associé au texte du `<label>` : très lisible |
| Texte | `texte=Enregistrer`, `texte_exact=OK` | un élément contenant ce texte |
| Rôle | `role=button:Enregistrer`, `role=link:Nouveau plan` | boutons / liens par leur nom visible |
| Indice | `placeholder=jj/mm/aaaa` | |
| Autres | `titre=Fermer`, `test=btn-save`, `xpath=//table//tr[2]/td[1]` | |

Plusieurs correspondances ? ajoutez `nieme: 2` (le 2e) ou `premier: true` / `dernier: true`.

Pour les trouver : `python -m autoweb inspecter URL` ouvre la page avec
l'inspecteur Playwright ; cliquez sur « Pick locator » puis sur un élément.

### Les gabarits `{{ }}`

- `{{Numéro plan}}` : la cellule de la colonne « Numéro plan » (casse, accents et espaces tolérés).
- Filtres : `{{Date | date:%d/%m/%Y}}`, `{{Qté | entier}}` (5.0 → 5), `{{Prix | nombre:2 | virgule}}`,
  `{{Code | majuscules}}`, `{{Commentaire | defaut:RAS}}`, `{{X | tronquer:10}}`, `{{X | sans_espaces}}`, `{{X | ouinon}}`.
- Variables : celles de `variables:` et de `--var`, plus `{{aujourdhui}}`, `{{maintenant}}`, `{{ligne}}` (n° de ligne Excel), `{{n}}`, `{{total}}`.
- Une colonne utilisée dans le scénario mais absente de l'Excel est signalée **avant** de lancer.

---

## 5. Mettre au point sans casser quoi que ce soit

1. `simuler` : affiche pour chaque ligne les étapes avec les valeurs réelles, sans ouvrir de navigateur.
2. `lancer --limite 1` avec `visible: true` et, au début, une étape `pause: "Vérifiez le formulaire"`
   juste avant le clic sur Enregistrer : vous validez à la main la première fois.
3. `lenteur: 300` dans `navigateur:` pour voir chaque action.
4. À chaque erreur : capture d'écran dans `captures/erreurs/`, message dans l'Excel, détail dans `journal/`.
5. `--inspecter-si-erreur` ouvre l'inspecteur au moment de l'erreur, page en l'état.

---

## 6. Connexion à l'outil (SSO, mot de passe, MFA)

Trois façons, de la plus simple à la plus robuste :

1. **Profil persistant** (`navigateur: profil: profils/mon_outil`) : le robot ouvre son propre Edge avec un
   profil dédié. La première fois, une étape `pause` dans `avant:` vous laisse vous connecter à la main ;
   les fois suivantes la session est mémorisée. *Ne partagez jamais le dossier `profils/` (cookies).*
2. **Se brancher sur votre Edge déjà ouvert** : lancez `edge_debug.bat` (ouvre Edge avec
   `--remote-debugging-port=9222`), connectez-vous à vos outils, puis dans le scénario :
   ```yaml
   navigateur:
     attacher: 9222
   ```
   Le robot travaille dans cette fenêtre, avec vos sessions ; il ne la ferme pas à la fin.
3. **Saisir les identifiants dans le scénario** : possible (`remplir` sur les champs de connexion) mais
   évitez de mettre un mot de passe dans un fichier ; utilisez plutôt `--var mdp=...` au lancement.

---

## 7. Extraire des documents vers l'Excel (PDF / Word / texte)

Quand les données de départ sont dans des documents, `extraire` construit l'Excel de suivi :

```bat
python -m autoweb extraire regles.yaml --dossier "C:\plans\a_saisir" --sortie suivi.xlsx
```

`regles.yaml` (modèle complet : `autoweb/modeles/modele_regles_extraction.yaml`) :

```yaml
fichiers: ["*.pdf", "*.docx"]
champs:
  Numéro plan: {regex: 'N[°o]\s*plan\s*[:=]?\s*(\S+)', obligatoire: true}
  Titre: 'Titre\s*:\s*(.+)'
  Dates: {regex: '\d{2}/\d{2}/\d{4}', tous: true}
```

Une ligne par document, colonne `Fichier` + un champ par colonne, Statut vide (prêt pour le robot) ou
`A verifier` si un champ obligatoire manque. Les PDF scannés (images) n'ont pas de texte : il faudra
un OCR, à voir dans une étape suivante.

---

## 8. Organisation des fichiers

```
robot-web/
  autoweb/            le programme (ne pas modifier pour un usage courant)
  autoweb/modeles/    formulaire de démo, scénario modèle, règles d'extraction modèle
  tests/              tests automatisés (python -m pytest)
  mon_outil/          VOS dossiers : un par outil, créés par `initialiser`
    saisie_des_plans.yaml, suivi.xlsx, captures/, journal/, profils/, sauvegardes/
```

Les dossiers `profils/`, `captures/`, `journal/`, `sauvegardes/`, `telechargements/` et les `*.xlsx`
sont exclus de git (`.gitignore`) : ils contiennent des sessions ou des données métier.

---

## 9. Problèmes fréquents

| Symptôme | Cause / solution |
|---|---|
| `Aucun navigateur n'a pu être lancé` | Edge/Chrome introuvables : `executable:` avec le chemin de msedge.exe, ou `python -m playwright install chromium`, ou `attacher: 9222` |
| `le fichier est ouvert dans Excel` | fermez l'Excel, appuyez sur Entrée : le robot réessaie |
| `délai dépassé : élément introuvable` | mauvais sélecteur ou page lente : `inspecter`, puis `delai_max` plus grand ou une étape `attendre` |
| Le robot ne traite aucune ligne | colonne Statut déjà remplie : videz-la ou `--reprendre-erreurs` / `--tout` |
| Accents bizarres dans la console | lancez `chcp 65001` avant, ou lisez `journal/autoweb-AAAAMMJJ.log` |
| Profil « déjà utilisé » | une autre fenêtre utilise le même `profil:` : fermez-la ou changez de dossier |
| Antivirus bloque `node.exe` de Playwright | signalez-le : on basculera sur une autre approche (Selenium avec le pilote Edge) |

---

## 10. Suite prévue

- OCR pour les PDF scannés (`extraire`) ;
- exécution planifiée (Planificateur de tâches Windows) pour les traitements de nuit, sans surveillance ;
- rapport de fin (résumé HTML/Excel envoyé par mail) ;
- bibliothèque de scénarios par outil, partagée dans ce dépôt.

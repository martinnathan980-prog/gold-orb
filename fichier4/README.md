# Fichier 4 — gzip + base64 + `decoder.py`

Outil autonome pour **transporter un fichier binaire sous forme de texte** :
on le **compresse (gzip)**, on l'**encode en base64**, éventuellement
**découpé en plusieurs parties**, puis on le reconstruit à l'identique avec
`decoder.py`.

C'est la 4ᵉ approche (« fichier 4 ») pour sortir/partager des données quand
un canal n'accepte que du texte ou impose une taille maximale : chat, copier-
coller, limite GitHub de 100 Mo par fichier, etc. Le point qui bloquait dans
les approches précédentes — **un flux base64 trop long à coller / à envoyer
d'un coup** — est réglé ici par le **découpage en parties** (`--chunk-bytes`).

- Aucune dépendance : **Python 3 standard uniquement** (testé sur 3.11).
- **Intégrité vérifiée** : taille + `SHA-256` du fichier d'origine, et de
  chaque partie.
- **Roundtrip exact** octet pour octet (vérifié sur du texte, des fichiers
  vides et de vraies données `.csv.gz`).

## Contenu

| Fichier       | Rôle                                                        |
|---------------|-------------------------------------------------------------|
| `encoder.py`  | fichier  →  conteneur(s) texte `.gb64` (gzip + base64)      |
| `decoder.py`  | conteneur(s) `.gb64`  →  fichier d'origine reconstruit      |
| `README.md`   | ce document                                                 |

## Démarrage rapide

```bash
# 1) Encoder un fichier -> data.csv.gb64
python3 fichier4/encoder.py data.csv

# 2) Le transporter (copier-coller, commit, envoi...) c'est du texte pur

# 3) Reconstruire le fichier d'origine
python3 fichier4/decoder.py data.csv.gb64
# -> écrit "data.csv" (nom mémorisé dans l'en-tête), SHA-256 vérifié
```

### Fichier trop gros ? On découpe

```bash
# Parties de 2 Mo maximum : data.part-001.gb64, data.part-002.gb64, ...
python3 fichier4/encoder.py gros.csv --chunk-bytes 2M

# Reconstruction : le décodeur remet les parties dans l'ordre tout seul
python3 fichier4/decoder.py gros.part-*.gb64
```

Chaque partie est un fichier texte indépendant, court, facile à coller ou à
envoyer. Le décodeur les trie par index, vérifie qu'il ne manque rien, puis
recompose le fichier.

## Exemples avec les données du dépôt

Les fichiers de `download/` sont **déjà** compressés (`.csv.gz`). Inutile de
les recompresser : on utilise `--no-gzip`.

```bash
# Encoder une année de données XAU/USD en parties de 3 Mo
python3 fichier4/encoder.py \
  download/xauusd-m1-bid-2024-01-01-2025-01-01.csv.gz \
  --no-gzip --chunk-bytes 3M -o export/xau2024.gb64

# Reconstruire le .csv.gz, puis lire le CSV
python3 fichier4/decoder.py export/xau2024.part-*.gb64 -o /tmp/xau2024.csv.gz
gunzip -c /tmp/xau2024.csv.gz | head
```

## Options utiles

### `encoder.py`

| Option              | Effet                                                    |
|---------------------|----------------------------------------------------------|
| `-o CHEMIN`         | chemin de sortie (préfixe si découpage)                  |
| `--chunk-bytes N`   | découpe en parties de N octets (`2M`, `500k`, `1048576`) |
| `--no-gzip`         | ne pas recompresser (fichier déjà en `.gz`)              |
| `--level 0-9`       | niveau gzip (défaut : 9)                                  |
| `--width N`         | largeur des lignes base64 (défaut : 76 ; `0` = 1 ligne)  |
| `--stdout`          | écrit le conteneur sur la sortie standard                |
| `-f, --force`       | écrase les sorties existantes                            |

### `decoder.py`

| Option                  | Effet                                                       |
|-------------------------|-------------------------------------------------------------|
| `-o CHEMIN`             | fichier de sortie ; **dossier** si le chemin finit par `/` ou si plusieurs fichiers sont reconstruits (créé au besoin) |
| `--input-dir DIR`       | décode tous les `.gb64` d'un dossier                        |
| `--stdout`              | écrit les octets décodés sur la sortie standard             |
| `--info`                | affiche seulement les métadonnées (ne décode pas)           |
| `--max-output-bytes N`  | borne la taille décompressée (`200M`) ; à utiliser pour un conteneur non fiable (anti-bombe de décompression) |
| `-f, --force`           | écrase le fichier de sortie existant                        |
| `-`                     | lit un conteneur depuis l'entrée standard                   |

Le décodeur n'interprète un en-tête que si le fichier commence par la ligne
marqueur `GB64 vN`. Sinon il traite tout le contenu comme du **base64 brut** :
il décode puis décompresse automatiquement si les octets commencent par la
signature gzip (`1f 8b`).

## Format du conteneur (`GB64 v1`)

Un conteneur est un fichier texte : un en-tête `clé=valeur`, une ligne vide,
puis le corps base64.

```
GB64 v1
name=data.csv          # nom d'origine (seul le nom de base est utilisé)
size=1048576           # taille du fichier d'origine, en octets
sha256=<hex>           # SHA-256 du fichier d'origine (non compressé)
gzip=1                 # 1 = corps compressé en gzip, 0 = octets bruts
parts=3                # nombre total de parties
part=1                 # index de cette partie (1..parts)
psize=349525           # octets de cette partie (après base64, avant gunzip)
psha256=<hex>          # SHA-256 de cette partie

Te0KSw0K...            # corps base64 (lignes de 76 caractères)
```

Chaîne complète : `fichier → gzip → découpage → base64 → texte`, et l'inverse
au décodage, avec vérification de chaque `SHA-256`.

## Sécurité

- Le champ `name` d'un conteneur n'est **jamais** utilisé tel quel : seul le
  **nom de base** est retenu, ce qui empêche l'écriture hors du dossier de
  sortie (`../../…` ou chemin absolu neutralisés).
- Par défaut, le décodeur **n'écrase pas** un fichier existant (`--force`
  requis).
- Un `SHA-256` qui ne correspond pas fait échouer le décodage (code de retour
  non nul) : une donnée corrompue n'est pas écrite silencieusement.
- Une **partie manquante** ou un total incohérent fait échouer le décodage :
  jamais de reconstruction tronquée silencieuse.
- La décompression est **bornée** : le décodeur s'arrête si la sortie dépasse
  la taille annoncée dans l'en-tête, et l'option `--max-output-bytes` pose une
  borne dure pour un conteneur non fiable (protection contre les bombes de
  décompression). Les valeurs d'en-tête sont assainies avant affichage.

## Codes de retour

| Code | Signification                                        |
|------|-----------------------------------------------------|
| `0`  | succès                                               |
| `1`  | échec de reconstruction / intégrité (SHA, parties)  |
| `2`  | erreur d'usage / entrée introuvable                 |

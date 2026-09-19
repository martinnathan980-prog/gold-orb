# Les cartons

14 images en 1920 × 1080, PNG, prêtes à glisser dans iMovie. Style panneau d'aéroport : fond bleu nuit, texte ambre, cadre fin.

| Fichier | Où ça sert |
|---|---|
| `00-logo.png` | Générique, 0:00 |
| `01-panneau-departs.png` | Générique, 0:00, sous l'annonce 1 |
| `02-carton-nimes.png` | Décollage, 1:15 |
| `03-carton-ecole.png` | Escale École, 2:00. **Provisoire**, à regénérer avec le vrai nom |
| `04-carton-marignane.png` | Escale Marignane, 2:30 |
| `05-carton-turbulences.png` | Turbulences, 3:00 |
| `06-carton-pointe-a-pitre.png` | Escale PTP, 3:30 |
| `07-carton-cabine.png` | Cabine classe éco, 4:00 |
| `08-carton-duty-free.png` | Duty free, 4:30 |
| `09-carton-presidence.png` | Présidence, 5:00 |
| `10-carton-perte-signal.png` | Perte de signal, 5:30 |
| `11-carton-maternite.png` | Terminal Maternité, 6:00 |
| `12-carton-final.png` | Carton final, 7:00 |
| `12b-carton-meme-equipage.png` | La toute dernière image, après une seconde de noir |
| `13-carte-embarquement.png` | Bonus, à imprimer et faire signer |

## La fin en deux temps

Le film ne se termine pas sur un carton mais sur deux, séparés par **une seconde de noir complet**.

1. `12-carton-final.png`, quatre secondes. On sort sur un rire : la compagnie n'a toujours pas d'hélicoptères, et c'est la seule experte en hélicoptères de la salle qui le lit.
2. Une seconde de noir. Le rire retombe.
3. `12b-carton-meme-equipage.png`, trois secondes. Deux mots seuls au milieu de l'écran. Ils ne parlent plus du voyage, ils parlent d'eux trois. Ça dit « on sera encore tous là » sans avoir à le dire.

C'est la seule chose du montage où l'ordre compte vraiment. Le rire d'abord, le silence ensuite. Jamais l'inverse.

## Comment les utiliser dans iMovie
Glisse le PNG sur la timeline comme une photo. Durée conseillée : **2 secondes pour un carton d'escale**, 3 secondes pour le logo et le panneau des départs, 4 secondes pour le carton final.

Désactive l'effet Ken Burns, qui est actif par défaut sur les images et qui fait zoomer le carton lentement. Sélectionne l'image, clique sur l'icône de recadrage au-dessus de l'aperçu, et choisis **Ajuster**.

## La carte d'embarquement
Imprime-la en A4 paysage sur du papier épais. Fais-la signer par tout le monde au dos, pendant la fête, et donne-la à Océane après la projection. C'est le seul objet du projet qu'elle pourra garder.

## Les regénérer
Le script qui les produit est dans ce dossier : `generer-cartons.py`. Il tourne avec Python et Pillow.

```
pip install pillow
python3 generer-cartons.py
```

Dis-moi ce que tu veux changer, couleurs, textes, ajout d'un carton, je modifie le script et je relance.

## Ce qui manque encore
- Le carton École, dès que tu m'auras confirmé le nom et la ville.
- Un carton de générique de fin avec la liste d'équipage, dès que le casting est figé.

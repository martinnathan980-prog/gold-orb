# Guide de montage

Version 2, calée sur les 7 minutes.

## Outils

| Situation | Outil | Pourquoi |
|---|---|---|
| Téléphone ou tablette | **CapCut** (gratuit) | Simple, gère le vertical vers l'horizontal avec fond flou, textes, musique. Attention aux effets payants. |
| Mac | **iMovie** (gratuit) | Largement suffisant ici. |
| PC ou Mac, tu veux un vrai outil | **DaVinci Resolve** (gratuit) | Puissant, plus long à prendre en main. |
| PC, tu veux simple | **Clipchamp** (dans Windows 11) ou **CapCut desktop** | |

L'outil que tu connais déjà est le bon. Ce n'est pas l'outil qui fait la vidéo, c'est le rythme.

## Préparer les rushs (semaine du 12 octobre)
1. Un dossier `rushs/` sur ton ordinateur, un sous-dossier par séquence : `00-generique`, `030-securite`, `115-nimes`, `200-blagnac`, `230-marignane`, `300-turbulences`, `330-ptp`, `400-cabine`, `430-dutyfree`, `500-mamie`, `530-signal`, `600-maternite`, `630-atterrissage`. Pas dans ce dépôt : les vidéos n'ont rien à faire dans git.
2. Renommer : `500_mamie_presidence_v1.mp4`.
3. Regarder chaque vidéo **à la réception** et noter dans `05-casting.md` : validée, ou à refaire.
4. Les verticales : on les garde, en fond flou ou côte à côte avec une photo. Demander une version horizontale si la personne peut refaire.
5. Archives papier : scanner avec l'app Notes (iPhone) ou Google Drive (Android), à plat, lumière du jour, sans reflet.

## L'ordre de montage
1. **Poser la colonne vertébrale d'abord** : les 8 annonces du commandant, dans l'ordre, avec du vide entre elles. Tu as déjà un film de 2 minutes qui se tient.
2. **Remplir les trous** avec les clips, séquence par séquence.
3. **Couper chaque clip sur la valise.** La phrase de la valise est le point de coupe : on la garde entière, on coupe juste après.
4. **Regarder d'une traite, chronomètre en main.** Note les moments où tu décroches. Ce sont ceux à couper, même si tu les aimes.
5. **Vérifier l'alternance** sincère/gag sur le tableau de `03-script.md`. Deux gags de suite, c'est un problème à régler avant d'aller plus loin.
6. Seulement après : cartons, sons, musique.

## Le budget temps, séquence par séquence
Imprime ce tableau et tiens-le. À 7 minutes, chaque dépassement se paie ailleurs.

| Séquence | Cible | Plafond |
|---|---|---|
| Générique | 30 s | 35 s |
| Consignes de sécurité | 45 s | 50 s |
| Chaque escale | 30 s | 35 s |
| Décollage Nîmes | 45 s | 50 s |
| Atterrissage | 30 s | 40 s |
| **Total** | **7:00** | **8:00** |

Au-delà de 8 minutes, coupe une escale entière plutôt que de raboter partout. Une séquence coupée net ne se voit pas, une vidéo qui traîne partout se voit tout de suite.

## Les graphismes (je te les prépare dès qu'on a les noms et les dates)
- Logo Océane Airlines
- Panneau des départs animé, pour le générique
- Cartons d'escale avec les codes aéroport : NIM, TLS, MRS, PTP
- Carton duty free avec prix barré
- Carton du documentaire animalier
- Carton final « prochaine destination »
- Format 1920 × 1080, PNG

## Les sons
Sources gratuites : Pixabay, Freesound, YouTube Audio Library.
- « Ding » de cabine (chercher « airplane chime »)
- Ambiance aéroport, annonces lointaines
- Réacteurs au décollage, train d'atterrissage, roues qui touchent
- Applaudissements
- Grésillement et coupure radio, pour la perte de signal
- Musique : une rythmée pour les escales, une douce pour le Terminal Maternité. Idéalement une chanson qu'elle aime.

Diffusion privée en famille : pas de souci de droits. Si ça finit sur les réseaux, passer aux musiques libres.

## Traiter la perte de signal
C'est la séquence la plus technique, et c'est 30 secondes. Trois effets suffisent : baisser la qualité de l'image (effet pixellisation ou VHS, présent dans CapCut et Resolve), couper le son par à-coups, et poser un grésillement par-dessus. Ne pas chercher mieux : l'effet vient du montage cut, pas des filtres.

## Export
MP4, H.264, 1920 × 1080, 25 ou 30 im/s, son AAC stéréo, qualité haute.
Nom : `Oceane_Airlines_OA30_FINAL_v1.mp4`, et incrémenter. Il y a toujours une v2.

## Checklist jour J, à faire le vendredi 6 novembre
- [ ] La vidéo lue **sur l'écran du jour J**, avec le vrai câble, la vraie clé, du début à la fin
- [ ] Le son assez fort pour la pièce, testé avec la vidéo, enceinte si besoin
- [ ] Trois copies : clé USB en exFAT, téléphone, cloud
- [ ] Un deuxième appareil prêt, avec la vidéo dessus et un câble HDMI
- [ ] La lumière de la pièce, les rideaux
- [ ] Quelqu'un désigné pour filmer la réaction d'Océane
- [ ] Des mouchoirs

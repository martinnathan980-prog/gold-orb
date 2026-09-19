# Guide de montage, pour quelqu'un qui n'a jamais monté

Version 3, écrite pour Nathan : Mac, iMovie, jamais monté, projection en HDMI sur la télé dans les Cévennes.

iMovie est largement suffisant pour ce film. Ce n'est pas l'outil qui fait la vidéo, c'est le rythme. Tu vas passer trois ou quatre soirées dessus, pas trois semaines.

## Avant de commencer

**Installe Audacity** (gratuit, audacityteam.org). Tu ne t'en serviras qu'une fois, pour traiter ta voix de commandant, mais ça vaut le détour : c'est ce qui fait la différence entre « mon frère qui lit un texte » et « une annonce de cabine ».

**Crée ton dossier de travail** sur le Mac, pas dans le dépôt. Un dossier `Oceane_OC1996/` avec dedans :

```
rushs/        les vidéos reçues, un sous-dossier par séquence
archives/     les photos et vidéos anciennes
sons/         les bruitages et la musique
cartons/      les images que je te prépare
export/       les versions finales
```

Renomme chaque rush dès réception : `500_christiane_presidence_v1.mp4`. Tu me remercieras à la troisième soirée.

## Les six étapes, dans l'ordre

### 1. Enregistrer les huit annonces (semaine du 21 septembre)
Avant tout le reste. Elles sont la colonne vertébrale : une fois posées, tu as déjà un film.

- Enregistre avec **les écouteurs filaires du téléphone**, le micro à dix centimètres de la bouche, jamais le micro interne du Mac.
- Mets-toi dans une pièce avec des rideaux, ou carrément dans une penderie ouverte, face aux vêtements. Ça absorbe l'écho et ça change tout.
- L'appli Dictaphone suffit. Trois prises par annonce, tu garderas la meilleure.
- Lis **plus lentement que tu ne crois nécessaire**. Puis encore plus lentement.

### 2. Traiter la voix dans Audacity (une heure, une seule fois)
C'est le seul moment technique du projet, et il y a trois réglages.

1. Ouvre le fichier dans Audacity, sélectionne tout avec Cmd+A.
2. **Effet → Filtre passe-haut**, fréquence 300 Hz. Ça enlève le grave de la voix, comme une vraie radio.
3. **Effet → Filtre passe-bas**, fréquence 3400 Hz. Ça enlève l'aigu. Entre les deux, tu es exactement dans la bande passante d'une annonce de cabine.
4. **Effet → Compresseur**, réglages par défaut. Ça égalise le volume.
5. Optionnel, si tu veux t'éloigner encore de ta vraie voix : **Effet → Changer la hauteur**, environ moins 8 pour cent. Pas plus, sinon ça sonne faux.
6. **Fichier → Exporter → Exporter en WAV.**

Ce traitement fait aussi un travail invisible mais essentiel : il te permet d'être à la fois le commandant et présent à l'image dans les consignes de sécurité, sans que personne ne fasse le lien.

Évite les sites de clonage de voix. Le rendu artificiel casse le sérieux, et ton vrai enregistrement traité sonnera bien mieux.

### 3. Poser la colonne vertébrale (une soirée)
Dans iMovie : **Fichier → Nouveau → Film**. Pas « Bande-annonce ».

Importe tes huit annonces traitées et pose-les dans l'ordre sur la timeline, avec du vide entre elles. Tu as maintenant un film de deux minutes qui tient debout. C'est ton filet de sécurité : même si tout le reste prend du retard, tu as une structure.

### 4. Remplir les trous (deux soirées)
Séquence par séquence, dans l'ordre du conducteur (`03-script.md`).

**La règle de coupe :** chaque clip finit par « Et dans sa valise, je mets… ». Tu gardes cette phrase entière et tu coupes juste après. Si un clip est trop long, tu gardes le début et la valise, tu jettes le milieu. Personne ne le verra.

**Les vidéos verticales :** iMovie ajoute des bandes noires sur les côtés. Deux options. Soit tu les laisses, et ça passe très bien sur une ou deux vidéos. Soit tu sélectionnes le clip, tu cliques sur l'icône de recadrage en haut de la fenêtre d'aperçu et tu choisis **Rogner pour remplir**, mais attention, ça coupe le haut de la tête. Teste avant de valider.

### 5. Le son et les cartons (une soirée)
- Glisse les cartons PNG comme des photos, trois secondes chacun.
- Pour la musique sous une voix : sélectionne le clip de musique, puis dans les réglages audio coche **Réduire le volume des autres pistes**. iMovie baisse automatiquement la musique quand quelqu'un parle. C'est le réglage le plus utile de tout le logiciel.
- Pour la perte de signal à 5:30, trois effets suffisent : baisse la qualité d'image avec un filtre pixellisé ou VHS, coupe le son par à-coups, pose un grésillement par-dessus. Ne cherche pas mieux, l'effet vient du montage sec.

### 6. Regarder d'une traite, chronomètre en main
Note les moments où tu décroches. Ce sont ceux à couper, même si tu les aimes. Vérifie ensuite l'alternance sincère/gag sur le tableau du conducteur.

## Le budget temps, séquence par séquence

| Séquence | Cible | Plafond |
|---|---|---|
| Générique | 30 s | 35 s |
| Consignes de sécurité | 45 s | 50 s |
| Décollage Nîmes | 45 s | 50 s |
| Chaque escale | 30 s | 35 s |
| Turbulences | 35 s | 40 s |
| Atterrissage | 30 s | 40 s |
| **Total** | **7:00** | **8:00** |

Au-delà de 8 minutes, coupe une escale entière plutôt que de raboter partout. Une séquence coupée net ne se voit pas. Une vidéo qui traîne partout se voit tout de suite.

## Les sons à récupérer
Sur Pixabay ou la bibliothèque audio de YouTube, gratuits :
- « ding » de cabine, chercher *airplane chime*
- ambiance aéroport, *airport ambience*
- réacteurs au décollage, *jet takeoff*
- train d'atterrissage et roues, *landing gear*, *touchdown*
- applaudissements
- grésillement radio, pour la perte de signal

Pour la musique : une rythmée pour les escales, une douce pour le Terminal Maternité. Diffusion privée en famille, donc aucun souci de droits.

## L'export
**Fichier → Partager → Fichier.** Résolution 1080p, Qualité Élevée, Compression Meilleure qualité.
Nom : `Oceane_OC1996_FINAL_v1.mp4`. Incrémente à chaque version, il y en aura une deuxième.

## Le test du vendredi 6 novembre

Tu projettes depuis ton Mac en HDMI sur la télé. Trois choses se passent mal ce soir-là si tu ne testes pas avant.

- [ ] Branche le HDMI et va dans **Réglages Système → Son → Sortie**, et sélectionne la télé. Sans ça, le son sort des haut-parleurs du Mac et personne n'entend rien. C'est la panne numéro un.
- [ ] Regarde la vidéo **en entier** sur la vraie télé, pas trente secondes.
- [ ] Le son est-il assez fort pour la pièce ? Si la télé est faible, prévois une enceinte et teste-la avec la vidéo.
- [ ] Désactive la mise en veille du Mac : Réglages Système → Écran verrouillé, tout sur Jamais.
- [ ] Mets le Mac en **Ne pas déranger**. Une notification en plein Terminal Maternité, ça ne pardonne pas.
- [ ] Trois copies : le Mac, une clé USB en exFAT, et un cloud.
- [ ] Un deuxième appareil prêt avec la vidéo dessus.
- [ ] Repère les rideaux et les lumières de la pièce.
- [ ] Désigne quelqu'un pour filmer **la réaction d'Océane**. Personne n'y pense et tout le monde le regrette.
- [ ] Des mouchoirs.

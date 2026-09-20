# Messages de la cabine, blocs 1 et 2

Vol OC 1996. Les deux blocs de 3:15 (55 s) et 8:05 (45 s), calés sur `02-concept.md` et `03-script.md`, avec les prénoms de `08-fiche-oceane.md`.

**Mode d'emploi.** Tout ce qui est en bloc citation se copie et s'envoie tel quel. Tout ce qui est en *italique* est pour toi et ne sort jamais du document. Quand tu colles dans WhatsApp, enlève les doubles astérisques : WhatsApp met en gras avec une seule étoile, `*comme ça*`.

---

## 1. Le dispositif, et pourquoi il vaut mieux que la dispersion

Sur une trentaine de sollicitations, une bonne moitié des gens ne jouera aucun rôle. Ils enverront un « joyeux anniversaire Océane » gentil et vide, et c'est parfaitement normal : personne ne leur doit un sketch. Le problème n'est donc pas la qualité de ces messages, c'est leur emplacement. Posé entre deux sketches, un message simple oblige la salle à sortir de la fiction, à redescendre au niveau d'une carte de vœux, puis à remonter. Trois fois de suite et la salle décroche pour de bon. La solution est de ne jamais les disperser : on les regroupe dans **deux blocs annoncés par le commandant comme les messages transmis par les passagers depuis leur siège**, et on introduit chacun par un **mini-carton de siège**, « SIÈGE 14C ». Trois choses se passent d'un coup. D'abord les messages cessent de se comparer au reste du film et ne se comparent plus qu'entre eux, ce qui est un combat beaucoup plus juste. Ensuite le carton et le *ding* de cabine leur donnent une forme commune, si bien qu'un message plat devient un élément d'une série au lieu d'être un trou : c'est la répétition qui crée la fiction, pas le contenu. Enfin la personne n'a rien à jouer et se retrouve pourtant dans le thème, sans qu'on lui ait rien demandé d'autre que quinze secondes. Et il y a un quatrième bénéfice, purement pratique : ces deux blocs deviennent le seul endroit où la durée du film se règle, ce qui te permet de lancer les demandes aujourd'hui sans savoir combien de gens répondront.

---

## 2. Les deux annonces du commandant

Même règle que les huit autres annonces de `10-annonces-commandant.md` : **sérieux absolu, débit lent, aucun sourire dans la voix**. Le texte est drôle tout seul. Les deux s'enregistrent dans la même session que les autres, le même jour, sans changer de pièce.

### Annonce du bloc 1, à 3:15

**39 mots, environ 15 secondes.**

> Mesdames et messieurs, ici votre commandant de bord. L'équipage a relevé les messages déposés par les passagers depuis leur siège. Nous allons vous les transmettre maintenant, dans l'ordre de réception. Merci de garder votre ceinture attachée pendant la lecture.

*Jeu : « dans l'ordre de réception » se dit exactement du même ton que « merci de garder votre ceinture attachée », c'est une information de service, pas une vanne. Une seconde de silence après « depuis leur siège », le temps que la salle comprenne qu'on lui installe un système. C'est cette annonce qui fait exister le dispositif pour tout le film, donc c'est la plus lente des deux.*

### Annonce du bloc 2, à 8:05

**40 mots, environ 15 secondes.** Elle ne réexplique rien, sinon on sent la reprise.

> Mesdames et messieurs, ici votre commandant de bord. Nous procédons à la seconde levée des messages de la cabine. Le volume reçu dépasse les prévisions de la compagnie. Le vol sera prolongé en conséquence. Nous vous remercions de votre compréhension.

*Jeu : ton de l'excuse commerciale, celui du retard annoncé à Roissy un mardi matin. Aucune accentuation sur « dépasse les prévisions », c'est un fait administratif. La vanne, c'est que la compagnie prolonge un vol parce qu'elle a reçu trop d'affection, et que personne ne le dit.*

*Pourquoi elle marche mieux que la première : elle admet le débordement au lieu de le cacher, elle fait rire de la longueur du film au moment précis où la salle pourrait commencer à la sentir, et elle t'autorise publiquement à allonger le bloc si tu reçois beaucoup de réponses. Deux annonces, deux fonctions : la première installe, la seconde assume.*

---

## 3. Le mini-carton de siège

**Plein écran, pas d'incrustation.** L'incrustation en bandeau est pénible à faire dans iMovie et tient mal la transparence. Un carton plein écran très court fait exactement le même effet et se pose en trois secondes.

| Point | La règle |
|---|---|
| **Format** | 1920 × 1080, même famille visuelle que les cartons d'escale : fond bleu nuit, code en ambre, cadre fin |
| **Contenu** | Le code de siège en gros, en chiffres monospace. Le prénom en dessous, petit, en blanc, en capitales espacées |
| **Durée** | **1,5 s** pour le tout premier du bloc 1. **0,8 s** partout ailleurs. **0,6 s** dans le bloc 2 |
| **Position** | Toujours **avant** le message, jamais par-dessus |
| **Son** | Le *ding* de cabine se pose **sur le carton**, jamais sur la vidéo. C'est le métronome du bloc |
| **Ken Burns** | À désactiver, comme pour tous les cartons : recadrage → **Ajuster** |

**Pourquoi le prénom en plus du code.** Le code seul est plus pur, mais la moitié de la salle ne connaît pas Hervé ni Julien, et une cousine par alliance n'est pas reconnue par tout le monde. Trois caractères ambre ne suffisent pas à dire qui parle. Le prénom en petit règle ça sans casser l'illusion, parce qu'une vraie compagnie affiche aussi le nom du passager sur sa carte d'embarquement.

*Dis-moi le nombre de sièges à sortir et je les ajoute à `cartons/generer-cartons.py`, une image par siège, nommées `siege-07B.png`. Attends d'avoir reçu les vidéos : les lettres dépendent de l'ordre d'arrivée.*

---

## 4. Le système de numéros de siège

### La règle, en une phrase

**Le rang dit d'où tu viens. La lettre dit dans quel ordre ta vidéo est arrivée.**

C'est tout. Tu n'as rien à mémoriser d'autre, et tu peux attribuer un siège à n'importe qui en deux secondes, même à quelqu'un qui te répond la veille du montage.

### Les rangs

| Rang | La branche |
|---|---|
| **1** | Océane, Célestin, Joséphine. **Réservé, jamais attribué dans les blocs** |
| **2** | La présidence et sa génération. Mamie Christiane |
| **3** | Le côté de Véronique et Guy |
| **4** | Le côté de Serge et Marité |
| **5** | La fratrie. Nathan, Coralie, et Paul côté Coralie |
| **6** | Le côté de Célestin. Sébastien et les siens |
| **7** | Les cousins et les cousines |
| **8** | Les amis et les amies |
| **9** | Le travail. Marignane et l'ENAC |
| **10 à 12** | Libres. Réserve, si une branche déborde |
| **14** | Le rang du fond. Tous ceux qui arrivent après la fermeture des portes, c'est-à-dire après le 11 octobre |

**Le moyen mnémotechnique :** plus tu es à l'avant, plus tu es près d'elle. Le rang 1 c'est chez elle, les rangs 3 et 4 ce sont ses parents, le 7 et le 8 les cousins et les amis, le 9 le bureau, le fond les retardataires.

**Et le rang 13 n'existe pas.** Les compagnies le sautent par superstition, donc on le saute aussi. C'est pour ça que le rang du fond est le 14, et c'est pour ça que « SIÈGE 14C » sonne vrai : c'est la première rangée après le trou.

### Les lettres

- **A, B, C, D, E, F**, dans l'ordre d'arrivée des vidéos. Le premier qui répond dans son rang prend la première lettre libre.
- **Les lettres déjà prises par un rôle joué sont prises.** Guy est en 3B parce que Véronique occupe le 3A.
- **Pas de lettre I**, elle se confond avec le chiffre 1. Les vraies compagnies ne l'utilisent pas non plus, ça renforce l'illusion gratuitement.
- Si un rang déborde au-delà de F, tu continues en G et H. Ça existe sur les gros porteurs et personne ne comptera.

### Le tableau d'attribution

**Règle de fond : tout le monde a un siège, mais seuls ceux qui envoient un message simple voient leur carton à l'écran.** Ça te permet d'attribuer un siège à n'importe qui à n'importe quel moment, et ça rend la carte d'embarquement (`cartons/13-carte-embarquement.png`) cohérente avec le film.

| Siège | Qui | Message cabine ? |
|---|---|---|
| 1A | **Océane** | Non. C'est la passagère du 1A, elle est dans la salle |
| 1B | **Célestin** | Non. Terminal Maternité à 9:50 |
| 1C | **Joséphine** | Non. Terminal Maternité à 9:50 |
| 2A | **Christiane** | Non. Présidence à 8:50 |
| 3A | **Véronique** | Non. Aux commandes à 1:25 |
| 3B | **Guy** | 🎯 **Oui, candidat naturel.** Il est dans la cabine et le compte à rebours, il n'a pas encore de voix à lui. **Bloc 1** |
| 4A | **Serge** | Non. Aux commandes à 1:25 |
| 4B | **Marité** | 🎯 **Oui, candidate naturelle.** Même raison que Guy. **Bloc 2**, pour ne pas la coller à lui |
| 5A | **Nathan** | Non. C'est toi, tu es le commandant |
| 5B | **Coralie** | Non. Consignes de sécurité à 0:35 |
| 5C | **Paul** | 🎯 **Oui.** Il n'a que la cabine éco. **Bloc 2** |
| 6A | **Sébastien** | Non. Escale Pointe-à-Pitre à 6:30 |
| 6B | | |
| 7A | | |
| 7B | | |
| 7C | | |
| 7D | | |
| 7E | | |
| 7F | | |
| 8A | | |
| 8B | | |
| 8C | | |
| 8D | | |
| 8E | | |
| 8F | | |
| 9A | **Hervé** | Non. Escale Marignane à 5:15 |
| 9B | **Julien** | Non. ENAC à 4:10 et Marignane à 5:15 |
| 9C | | |
| 9D | | |
| 9E | | |
| 14A | | |
| 14B | | |
| 14C | | |
| 14D | | |

**La règle qui protège tout le tableau : quelqu'un qui a déjà un clip joué ne prend jamais un siège à l'écran.** Sinon on le voit deux fois et son deuxième passage tombe à plat. Les trois seules exceptions sont Guy, Marité et Paul, qui n'existent aujourd'hui que dans des séquences collectives et n'ont jamais la parole seuls.

**Et la règle des 90 secondes :** personne n'apparaît deux fois à moins de 90 secondes d'écart. C'est pour ça que Guy va dans le bloc 1 (3:15) et Marité dans le bloc 2 (8:05) : la cabine éco est à 7:00, donc Marité y est déjà 65 secondes avant le bloc 2. Si tu tiens à la mettre dans le bloc 2, place-la **en dernier** du bloc, tu récupères vingt secondes d'écart.

---

## 5. La consigne à envoyer à quelqu'un qui ne veut pas jouer un rôle

Trois versions. **Tu en choisis une par personne, tu remplis le siège et la question avant d'envoyer, et tu n'envoies jamais le choix.** Si tu laisses les gens choisir, tu reçois quinze fois la même chose, et en retard.

*Note importante : dans les trois versions, la phrase d'ouverture « Ici le siège 7B » est présentée comme facultative. Elle est ce qui transforme un message plat en passage de film, donc tu la veux vraiment, mais si tu la rends obligatoire tu rajoutes de la pression à quelqu'un qui n'en voulait déjà pas. Présentée comme un bonus, tu l'obtiens de sept personnes sur dix.*

### Version A : celle qui ne sait pas quoi dire

> Salut [prénom] ! Petit service pour la vidéo surprise des 30 ans d'Océane 🎂
>
> Dans la vidéo, la famille et les collègues sont les passagers d'un vol. Tu n'as **aucun rôle à jouer**, rien à apprendre, rien à préparer. Ton siège à bord, c'est le **7B**.
>
> Ce que je te demande : **15 secondes de vidéo**, comme si tu parlais depuis ton siège. Et pour que tu ne sèches pas devant la caméra, je te donne la question, tu n'as qu'à y répondre :
>
> **[la question de relance choisie]**
>
> Une ou deux phrases, c'est tout. Tu finis par **« Joyeux anniversaire Océane »** et c'est plié.
>
> Trois détails et j'arrête : téléphone **à l'horizontale** ↔️, la lumière **devant** toi et jamais la fenêtre dans ton dos, et **2 secondes de silence** au début et à la fin. Ce silence, c'est ce qui me permet de couper proprement, c'est le seul truc technique qui compte vraiment.
>
> 🎁 Si ça t'amuse, commence par **« Ici le siège 7B »**. Si ça ne t'amuse pas, ne le dis pas, je mettrai juste le petit carton avant ton passage, ça marche pareil.
>
> Reprends-toi à trois fois si tu veux, envoie-moi les trois, je prends la meilleure. C'est presque toujours la deuxième.
>
> 📅 Avant le **dimanche 11 octobre**. Et pas un mot à Océane, on est déjà une trentaine dans la combine 🤫

### Version B : celle qui est mal à l'aise en caméra

> Salut [prénom] ! J'ai un petit truc à te demander pour la vidéo surprise des 30 ans d'Océane, et je sais très bien que se filmer, ce n'est pas ton truc. Du coup on fait autrement, et honnêtement ça rend souvent mieux.
>
> Dans la vidéo, tout le monde est passager d'un vol. Ton siège, c'est le **7B**. Aucun rôle à jouer, aucun texte.
>
> **Trois façons de faire, tu prends celle qui t'embête le moins :**
>
> 1. **Sans ton visage.** Tu poses le téléphone et tu parles pendant que tu fais autre chose. On voit tes mains, ta cuisine, ton jardin, ton chien qui passe. On entend ta voix. Sur grand écran, beaucoup de gens préfèrent ça à un plan de visage, je te le dis sérieusement.
> 2. **Juste ta voix.** Tu m'envoies un message vocal, ou mieux le dictaphone de ton téléphone posé sur la table. Je mets ta voix sur des photos.
> 3. **Avec quelqu'un.** Tu demandes à [prénom] de te filmer pendant que vous discutez tous les deux. Tu ne parles pas à la caméra, tu lui parles à lui. C'est toujours meilleur, parce que tu oublies le téléphone au bout de dix secondes.
>
> Ce que je te demande dans les trois cas : **une ou deux phrases**, pas plus. Et pour que tu n'aies pas à chercher :
>
> **[la question de relance choisie]**
>
> Puis **« Joyeux anniversaire Océane »**, et c'est fini.
>
> Zéro pression, vraiment : si tu m'envoies dix secondes de voix, j'ai ce qu'il me faut. Et si tu préfères ne rien envoyer du tout, dis-le-moi simplement, tu es dans le film de toute façon, il y a un passage où tout le monde est réuni à la fin.
>
> 📅 Avant le **dimanche 11 octobre** 🤫

### Version C : celle qui n'a que trente secondes devant elle

> Salut [prénom] ! **10 secondes** pour les 30 ans d'Océane, et je te jure que c'est 10 secondes ⏱️
>
> Téléphone **à l'horizontale**, tu appuies, tu dis :
>
> **« Ici le siège 7B. [une phrase]. Joyeux anniversaire Océane. »**
>
> Tu arrêtes, tu m'envoies. **Une seule prise, même ratée, c'est la bonne.** Ne la refais pas, je te connais.
>
> Si tu bloques sur la phrase du milieu, réponds juste à ça : **[la question de relance choisie]**
>
> 📅 Avant le **dimanche 11 octobre**, et pas un mot à Océane 🤫

*Note pour toi : la version C est celle qui revient le plus vite, souvent dans l'heure. Envoie-la aux gens que tu sais débordés plutôt qu'une version longue qu'ils liront mercredi et oublieront jeudi. Et ne dis jamais « quand tu veux » : une demande de dix secondes sans date se fait en trois semaines ou jamais.*

---

## 6. Les six questions de relance

À envoyer **une par une**, jamais en liste, à quelqu'un qui répond « je ne sais pas quoi dire ». Chacune déclenche une phrase concrète en dix secondes, parce qu'elle demande un fait et pas un sentiment.

**La phrase interdite, comme partout dans le projet : « dis un mot sur Océane ».** Elle produit du compliment, et le compliment ne se monte pas.

### 1. Le lieu

> « Tu étais où la dernière fois que tu l'as vue ? Commence exactement comme ça : "La dernière fois qu'on s'est vus, c'était à…" »

*Marche avec absolument tout le monde, même quelqu'un qui la croise deux fois par an. Un lieu, c'est déjà une image. Et le début de phrase imposé supprime les trois secondes de « alors, euh ».*

### 2. La voix

> « C'est quoi la dernière chose qu'elle a dite qui t'a fait rire ? Redis-la avec sa voix à elle, pas avec la tienne. »

*La meilleure des six. Dès que quelqu'un imite, il arrête de réciter et il devient drôle sans le vouloir. Et ça alimente la perte de signal à 9:20 : garde les rushes même si tu ne mets pas le message dans un bloc.*

### 3. L'objet

> « Qu'est-ce que tu ne lui prêterais jamais ? »

*Réponse instantanée, toujours concrète, souvent une voiture ou des clés. La salle connaît la trilogie du trottoir et les clés dans le sac, donc la réponse est rattrapée par le film sans que la personne ait besoin de connaître la vanne.*

### 4. L'heure

> « À partir de quelle heure tu sais qu'il ne faut plus l'appeler ? »

*Une heure, c'est un fait, et c'est immédiatement drôle. Ça rejoint l'extinction des feux à vingt et une heures du commandant et des consignes de sécurité. N'envoie pas cette question à plus de trois personnes, sinon tu récupères trois fois la même réponse et tu dois en jeter deux.*

### 5. La phrase à finir

> « Finis cette phrase, sans réfléchir : "Océane, c'est la seule personne que je connaisse qui…" »

*Le format à trou est ce qui débloque les gens qui ont peur de mal dire. Ils ne construisent pas une phrase, ils la complètent. Demande-leur de dire la phrase en entier, début compris, sinon tu récupères trois mots hors contexte.*

### 6. La peur de l'avion

> « Elle a peur en avion, et dans la vidéo elle est en vol pendant onze minutes. Rassure-la en une phrase, bien en face de la caméra. »

*La plus forte pour finir un bloc. Elle est drôle pour ceux qui connaissent la vanne, touchante pour les autres, et elle fait entrer la personne dans la fiction sans lui avoir demandé de jouer quoi que ce soit. Garde-la pour trois ou quatre personnes maximum, et garde la meilleure pour la dernière place du bloc 2.*

**Si ça ne prend toujours pas**, après une question posée : ne relance pas une deuxième fois avec une septième question. Bascule en version C et laisse la personne dire trois mots. Trois mots utilisables valent mieux qu'un message parfait qui n'arrivera jamais.

---

## 7. Rendre un message plat intéressant au montage

C'est là que se gagne le bloc. Un message plat n'a pas besoin d'être bon, il a besoin d'être **court, net et à sa place**.

### Où couper

**L'entrée, au ras.** Les gens commencent tous pareil : « alors… coucou… c'est moi… j'espère que ça marche ». Tu coupes tout. **La première image du message doit montrer quelqu'un qui parle déjà**, jamais quelqu'un qui attend, qui se replace ou qui vérifie l'écran. Entre sur le premier vrai mot, pas sur la respiration d'avant.

**La sortie, sur la dernière consonne, plus quatre images.** Tu ne gardes ni le « voilà », ni le sourire qui retombe, ni le bras qui va chercher le téléphone. **Une exception, une seule : le dernier message du bloc**, où tu gardes une seconde de plus. C'est l'atterrissage du bloc, il a le droit de respirer.

**Le milieu.** Si le message fait vingt secondes et ne dit rien pendant douze, tu coupes dedans. Deux façons de rendre la coupe invisible : coupe **sur un mouvement** (au moment où la personne bouge la tête ou les mains), ou couvre-la avec une photo d'archive. Et si tu n'y arrives pas, applique la règle suivante, qui est la vraie solution : **un saut d'image tout seul, c'est une erreur. Cinq sauts d'image dans le même bloc, c'est un parti pris.** Fais-le partout ou nulle part.

### Quoi garder

| Tu gardes | Tu jettes |
|---|---|
| La phrase qui contient un **nom concret** : un lieu, un objet, une heure, un chiffre | « Je te souhaite plein de bonheur », « profite bien », tous les vœux génériques |
| **L'accident** : le chien qui passe, l'enfant qui coupe, le fou rire, le téléphone qui tombe | La deuxième moitié, quand la personne se répète parce qu'elle ne sait pas comment finir |
| Le **prénom** quand il est dit. « Joyeux anniversaire Océane » vaut deux fois « joyeux anniversaire » | Les excuses : « désolé c'est nul », « je ne sais pas quoi dire ». Systématiquement |
| Le **premier essai**, si la personne t'en a envoyé trois. Elle est moins parfaite et plus vivante | La justification de l'absence : « je suis loin », « je ne peux pas venir » |

**S'il n'y a strictement rien de concret :** tu ne jettes pas le message, tu le réduis à **deux secondes** et tu le mets dans une rafale (voir plus bas). Deux secondes de quelqu'un qu'on aime, ça ne coûte rien et ça compte pour la personne.

### Comment enchaîner deux messages

- **Coupe franche, toujours. Aucune transition, aucun fondu.** iMovie propose des fondus enchaînés par défaut : désactive-les sur ce bloc. **C'est le carton qui fait la ponctuation**, il remplace la transition.
- **Alterne ce qui se voit.** Un intérieur après un extérieur, un plan large après un gros plan, un duo après un solo, une voix grave après une voix aiguë. Si deux messages consécutifs se ressemblent, inverse-les, ça ne coûte rien et ça sauve les deux.
- **Jamais deux personnes de la même branche à la suite.** Deux cousins d'affilée et la salle entend un appel de la classe, pas une séquence.
- **Jamais deux messages de la même durée à la suite.** C'est ce qui donne la sensation de liste.
- **Bonus, si tu te sens :** fais démarrer le son du message suivant une demi-seconde avant son image. Dans iMovie : sélectionne le clip, **Modifier → Détacher l'audio**, puis fais glisser la bande sonore d'un cran vers la gauche. Ça tire le bloc vers l'avant. Facultatif, mais c'est le truc qui fait la différence entre un enchaînement et un défilement.

### Quand poser le mini-carton

Toujours avant, jamais par-dessus. **0,8 seconde**, soit vingt images : assez pour lire trois caractères, trop court pour être une pause. Le *ding* dessus. Le premier du bloc 1 monte à 1,5 seconde parce que la salle découvre le système, et à partir du deuxième tu redescends et tu ne remontes plus. Dans le bloc 2, tu descends à 0,6 : la salle connaît, elle n'a plus besoin de lire, elle a juste besoin de reconnaître.

### Le rythme du bloc

Trois règles, et le bloc tient tout seul.

1. **Une seule musique sous tout le bloc**, lancée avant la fin de l'annonce du commandant et coupée sur la dernière image. C'est elle qui transforme une liste en séquence. Dans iMovie, sélectionne le clip de musique et coche **Réduire le volume des autres pistes**, elle baissera automatiquement sous les voix.
2. **Chaque message est plus court que le précédent.** C'est le seul truc à retenir de toute cette section. Un bloc qui raccourcit monte. Un bloc à durées égales traîne, même avec de meilleurs messages.
3. **Le *ding* à chaque carton**, sans exception. C'est le métronome : c'est lui qui dit à la salle qu'il y a un système, et un système, ça se suit sans fatigue.

### Le faire monter plutôt que traîner

**Énergie qui monte, durées qui descendent.** Les deux en même temps. Concrètement : le message le plus calme en premier, le plus vivant vers la fin, et les cartons qui raccourcissent au fur et à mesure (1,5 s puis 0,8 puis 0,8 puis 0,6 pour les derniers).

**Le point d'accélération obligatoire :** l'avant-dernière place du bloc est une **rafale**, trois messages très courts collés, deux secondes chacun, sans carton entre eux. Un seul carton pour les trois, « SIÈGES 7A 7B 7C », une seconde. C'est le moment où le bloc décolle, et c'est là que tu recycles tes trois messages les plus plats.

**Les deux tests, à faire quand le bloc est monté :**
- **Regarde-le sans le son.** Si ton œil s'ennuie, les messages sont trop longs. Enlève une seconde à chacun, pas une seconde au total.
- **Écoute-le sans l'image.** Si tu entends trois fois la même intonation de suite, ce n'est pas un problème de durée, c'est un problème d'ordre. Réorganise.

---

## 8. L'ordre de montage du bloc

### Les places, dans l'ordre

| Place | Qui tu mets là | Pourquoi |
|---|---|---|
| **1** | Le plus **clair et le plus court**, quelqu'un que la salle reconnaît en une demi-seconde | Son boulot n'est pas d'être le meilleur, c'est d'expliquer le système par l'exemple. Un inconnu en première place et la salle passe le message suivant à se demander qui c'était |
| **2** | **Le plus drôle** | La salle vient de comprendre le dispositif, donc la vanne porte. En première place, elle serait tombée dans le vide |
| **3 à n** | Tout le reste, **par durées décroissantes**, en alternant les branches et les décors | C'est le corps du bloc. Il ne doit jamais être long, il doit être régulier |
| **Avant-dernière** | **La rafale de trois messages courts** | L'accélération juste avant l'arrivée |
| **Dernière** | Celui qui **touche**, ou celui qui a la meilleure phrase concrète | Seul message qui a droit à une seconde de silence derrière, et à une seconde de plus au montage |

**Ce qu'on ne fait jamais :** commencer par le plus émouvant (la salle n'est pas prête, elle vient de rire), et finir sur un vœu générique (ça éteint le bloc et la séquence suivante démarre à froid).

### La répartition entre les deux blocs

**Bloc 1, à 3:15 :** ceux qui jouent un petit peu le jeu. La phrase du siège, l'objet dans la main, une vraie anecdote de dix secondes. C'est le bloc qui installe le dispositif, donc il a le droit d'être un peu plus démonstratif.

**Bloc 2, à 8:05 :** les plus courts et les plus bruts. À 8:05 la salle est chaude, elle a déjà vu le système deux fois, et elle va plus vite que toi. Une réponse de quatre secondes y fait plus d'effet qu'une anecdote de dix.

**Garde ta meilleure réponse à la question 6 (« rassure-la ») pour la toute dernière place du bloc 2.** Elle enchaîne sur la Présidence à 8:50, Mamie Christiane, qui est le grand moment de calme du film. Un message qui rassure suivi d'une grand-mère, c'est la meilleure jonction disponible dans tout le conducteur.

### Un message très long dans le bloc

**Plafond dur : 8 secondes dans le bloc 1, 7 secondes dans le bloc 2.** Aucune exception, quelle que soit la personne.

Trois façons de traiter un message de vingt-cinq secondes :

1. **Tu le coupes à ses huit meilleures secondes** et tu le mets en place 2 ou 3. C'est la solution par défaut, et personne ne le verra jamais.
2. **Tu le coupes en deux et tu le répartis sur les deux blocs.** C'est le luxe qu'offre le fait d'avoir deux blocs plutôt qu'un. Le carton du deuxième morceau porte alors la mention **« SIÈGE 7B (suite) »**. C'est la seule vanne du dispositif, donc **tu ne l'utilises qu'une fois dans tout le film**, sinon elle s'use.
3. **S'il est vraiment bon sur vingt-cinq secondes**, c'est qu'il n'a rien à faire dans un bloc de messages : c'est un clip. Mais alors ça touche à la structure, donc appelle-moi avant de le poser ailleurs.

### Un message de trois mots dans le même bloc

**Jamais seul, jamais en première ou dernière place.** Trois mots isolés entre deux messages de six secondes, ça se lit comme un oubli.

- **La solution normale :** il va dans la rafale, avec deux autres messages courts, sous un carton triple.
- **La solution qui fait rire :** tu le colles **juste après le message le plus long du bloc**. Huit secondes de quelqu'un qui raconte, puis deux secondes de quelqu'un qui dit « joyeux anniversaire Océane » et c'est tout. Le contraste fait la blague, et tu n'as rien eu à écrire.
- **Ce qu'il ne faut pas faire :** mettre deux messages de trois mots côte à côte hors rafale. Un contraste, ça marche. Deux d'affilée, c'est une panne.

---

## 9. La règle d'or du dimensionnement

**Ces deux blocs sont le seul endroit du film où la durée se règle. On ne touche jamais au reste de la structure pour ajuster.**

### Les chiffres

| Bloc | Total | Annonce | Messages | Nombre de messages |
|---|---|---|---|---|
| **1, à 3:15** | 55 s | 15 s | **40 s** | 8, rafale comprise |
| **2, à 8:05** | 45 s | 15 s | **30 s** | 7, rafale comprise |

**Minutage type du bloc 1 (40 s de messages) :** 8 s, 7 s, 6 s, 5 s, puis la rafale (1 s de carton + 3 × 2 s = 7 s), puis 7 s pour le dernier. Cartons compris.

**Minutage type du bloc 2 (30 s de messages) :** 6 s, 5 s, 5 s, puis la rafale (7 s), puis 7 s pour le dernier.

**Le plancher et le plafond.** Un bloc en dessous de **30 secondes** ne se lit plus comme un dispositif, juste comme deux messages égarés : il faut au minimum quatre passages pour qu'une salle perçoive un système. Un bloc au-dessus de **75 secondes** redevient une liste, quoi que tu fasses. Donc le film flexe entre **10:25 et 11:40**, et c'est une vraie marge : quarante secondes de jeu sans avoir déplacé une seule séquence.

### Comment décider, au montage, ce qui entre et ce qui sort

Tu regardes chaque message **une seule fois**, chronomètre à côté, et tu le mets dans une des trois piles. Ne réfléchis pas, ne reviens pas dessus.

| Pile | Le critère | Ce que tu en fais |
|---|---|---|
| **1. Ça fait quelque chose** | Il se passe un truc dans les **trois premières secondes** : un rire, un lieu, un objet, une voix qui imite | Entre entier, plafond de 8 s |
| **2. Ça fait quelque chose si je le raccourcis** | Il y a une bonne seconde quelque part, noyée | Réduit à ses 2 ou 3 meilleures secondes, part dans la rafale |
| **3. Ça ne fait rien** | Un vœu générique, aucun fait, aucune image | Ne va pas dans les blocs |

Tu remplis le bloc 1 avec la pile 1 jusqu'à 40 secondes, le bloc 2 jusqu'à 30, et tu montes les rafales avec la pile 2. Si la pile 1 déborde, tu montes les blocs jusqu'à leur plafond. Si elle ne suffit pas, tu prends dans la pile 2.

### La règle qui te permet de couper sans culpabiliser

**Avant de sortir le message de quelqu'un, vérifie qu'il est dans le compte à rebours à 10:30 ou dans le final collectif.** Personne n'est absent du film, jamais. Ce n'est pas une consolation, c'est la vraie structure : les blocs de messages sont un choix de montage, le final est une question de présence. Tiens la liste à jour sur ton téléphone au fur et à mesure, parce que c'est exactement la question qu'on te posera le soir de la projection.

### L'ordre des arbitrages, si tu dépasses

Dans cet ordre, et tu t'arrêtes dès que tu es dans les clous.

1. **Raccourcis les cartons.** De 0,8 à 0,6 seconde. Sur quinze messages, ça fait trois secondes gratuites.
2. **Resserre les entrées et les sorties.** Il y a presque toujours une demi-seconde à prendre au début de chaque message.
3. **Bascule le message le plus faible dans la rafale.** Six secondes qui deviennent deux.
4. **Et seulement après, enlève un message.** Le dernier de la pile 1, jamais celui du milieu du bloc.

**Ce que tu ne raccourcis jamais : l'annonce du commandant.** Quinze secondes chacune, elles sont ce qui fait tenir le dispositif. Sans elles, les blocs redeviennent ce qu'on voulait éviter, une suite de messages d'anniversaire.

### Si tu es en dessous

**Ne rallonge rien.** Un bloc de 35 secondes serré est meilleur qu'un bloc de 55 secondes rembourré, et un film de 10:25 est un bon film. Garde les deux blocs dans tous les cas, même avec quatre messages chacun : la deuxième annonce a besoin que la première existe, sinon sa vanne sur le volume reçu ne veut plus rien dire.

### Les trois interdits

- **Jamais un troisième bloc.** Deux, c'est un dispositif. Trois, c'est un format.
- **Jamais un message à l'intérieur d'un sketch.** C'est précisément le problème qu'on est en train de régler.
- **Jamais déplacer un bloc.** 3:15 casse la série de deux gags de 2:10 et 2:45. 8:05 casse celle de 7:00 et 7:35. Ils sont là pour ça.

---

## 10. Trois idées pour ceux qui veulent en faire un peu plus

Pour les gens qui répondent « je veux bien faire un truc en plus, mais je ne veux pas jouer ». Chaque idée tient en trois lignes à rajouter au bas de leur message.

### Idée 1 : tenir un objet

> 🎁 Si tu veux en faire un peu plus : prends dans ta main **un objet**, n'importe lequel, et dis la phrase qui revient dans toute la vidéo : **« Et dans sa valise, je mets… »**
>
> Deux conditions : l'objet est **dans le cadre avant** que tu parles (ne le sors pas au dernier moment, je n'aurai pas le temps de le cadrer), et tu le tiens **immobile deux secondes** après avoir fini de parler. Un objet concret, quelque chose qu'on peut tenir dans la main. Ça marche mille fois mieux qu'une jolie phrase, je te promets.

*Pour toi : la valise est obligatoire pour les clips joués et facultative pour les messages simples. Note au fur et à mesure ce que chacun annonce, dans une note de téléphone. Au moindre doublon, tu rappelles le deuxième et tu lui fais refaire juste cette phrase, ça prend dix secondes. Et le concret bat toujours l'abstrait : « un rouleau de scotch » fait rire, « ma tendresse » ne fait rien.*

### Idée 2 : se faire filmer comme à bord

> 🎁 Si tu veux en faire un peu plus : **filme-toi comme si tu étais assis dans l'avion.**
>
> Tu t'assieds bien droit sur une chaise, avec **le dossier d'une autre chaise visible devant toi ou derrière**, un sac sur les genoux, les bras croisés. Une fenêtre dans le fond si tu en as une, ça fait le hublot tout seul. Le téléphone **posé** sur quelque chose à deux mètres, à hauteur des yeux, jamais dans ta main.
>
> Et si quelqu'un peut faire semblant de dormir à côté de toi pendant que tu parles, c'est cadeau 😄

*Pour toi : c'est l'idée qui rend les messages homogènes entre eux sans rien demander de plus qu'un déplacement de chaise. Si trois ou quatre personnes le font, le bloc change complètement de niveau. Tu peux aussi leur envoyer `cartons/13-carte-embarquement.png` à imprimer et à tenir à la main : ça leur donne quelque chose à faire de leurs mains, ce qui est le vrai problème de quiconque se filme.*

### Idée 3 : lire son message comme une annonce

> 🎁 Si tu veux en faire un peu plus : **dis ton message comme une annonce de bord.**
>
> Tu commences par **« Mesdames et messieurs, ici le siège 7B »**, et tu continues avec ton message. Tu peux tenir le téléphone contre ta bouche comme un micro, ou mettre ta main en coupe devant.
>
> Le seul truc qui compte : **ne cherche surtout pas à être drôle.** Voix posée, débit lent, aucun sourire, exactement comme quelqu'un qui annonce un retard de quarante minutes. C'est le sérieux qui fait rire, pas la blague. Si tu souris, ça tombe à plat, et si tu restes impassible, la salle est par terre.

*Pour toi : c'est la meilleure des trois, et c'est celle qui coûte le moins. Elle transforme un message plat en vrai passage de film sans demander la moindre anecdote. Propose-la en priorité aux gens qui n'ont rien à raconter mais qui sont bons publics, et mets systématiquement ces messages-là en place 1 et 2 du bloc : ce sont eux qui installent le dispositif pour toute la salle.*

---

## Le suivi

| À faire | Quand |
|---|---|
| Arrêter la liste des gens qui ne feront qu'un message simple | Cette semaine |
| Leur attribuer un rang (pas encore de lettre) | Cette semaine |
| Envoyer les versions A, B ou C, une par personne, question déjà remplie | Semaine du 21 septembre |
| Attribuer les lettres au fur et à mesure des arrivées | En continu |
| Relance unique, gentille, à ceux qui n'ont rien envoyé | Lundi 5 octobre |
| Tout doit être arrivé | Dimanche 11 octobre |
| Tri en trois piles, chronomètre à côté | Semaine du 12 octobre |
| Générer les mini-cartons de siège, une fois les lettres figées | Semaine du 12 octobre |
| Monter les deux blocs en dernier, quand le reste du film est calé | Fin octobre |

*Le dernier point est important : monte les deux blocs à la fin. Ils sont la variable d'ajustement, donc tu as besoin de connaître la durée réelle de tout le reste avant de décider ce qui rentre dedans.*

**L'arithmétique, pour te rassurer.** Sur une trentaine de sollicitations, tu recevras une vingtaine de réponses, dont une quinzaine d'utilisables. Les deux blocs en tiennent quinze. Ça tombe juste, et ce n'est pas un hasard : c'est pour ça qu'ils font 55 et 45 secondes.

---

## À valider avec toi

**Ce qui bloque un envoi**
1. La liste des gens qui ne feront qu'un message simple, avec pour chacun sa branche. C'est la seule chose qui manque pour que je remplisse le tableau des sièges et que tu puisses envoyer.
2. Guy, Marité et Paul font-ils un message de cabine ? Je les ai marqués comme candidats naturels parce qu'ils n'ont aujourd'hui aucune parole à eux, seulement la cabine éco et le compte à rebours. Si tu es d'accord, ce sont les trois premiers à briefer.
3. Quelle version pour qui : A pour ceux qui sèchent, B pour ceux qui n'aiment pas la caméra, C pour les débordés. Dis-moi les trois listes et je remplis les sièges et les questions dans chaque message.
4. Combien de cousins et de cousines, et combien d'amis ? Ça décide de la taille des rangs 7 et 8.

**Une collision dans les documents existants, à trancher**
5. Le siège **1A** est attribué trois fois. Le commandant dit « la passagère du 1A » pour Océane dans quatre annonces et dans les consignes de sécurité, donc c'est verrouillé. Mais `15-briefs-escales.md` donne le 1A à Joséphine et `05-casting.md` le donne à Célestin. Ma proposition, qui ne change aucun texte déjà écrit : **Océane 1A, Célestin 1B, Joséphine 1C**. Joséphine garde son titre de plus jeune passagère de la compagnie, elle change juste de siège. Tu valides et je corrige les deux documents.

**Le dispositif**
6. Le prénom en petit sous le code de siège sur le mini-carton, ou le code tout seul ? J'ai tranché pour le prénom parce que la moitié de la salle ne connaît pas les collègues, mais c'est un peu moins pur.
7. La question 4 (« à partir de quelle heure il ne faut plus l'appeler ») et la question 6 (« rassure-la, elle a peur en avion ») sont les deux plus efficaces, mais elles s'usent. Je les ai limitées à trois ou quatre personnes chacune. Tu veux les garder pour qui ?
8. La mention « (suite) » sur le carton d'un message coupé en deux : c'est la seule vanne du dispositif et elle ne sert qu'une fois. Tu la gardes ?

**Le montage**
9. Tu veux que je te sorte les mini-cartons dès maintenant avec des sièges provisoires, ou on attend que les vidéos soient arrivées pour figer les lettres ? Je penche pour attendre, mais si ça te rassure d'avoir les images tôt, je génère un jeu complet de rangs 7, 8 et 14.
10. La musique des blocs : une seule piste sous les deux blocs, ou deux pistes différentes ? Une seule les relie et fait système, deux évitent la sensation de redite à 8:05. Je penche pour la même piste, plus rapide et plus courte au bloc 2.

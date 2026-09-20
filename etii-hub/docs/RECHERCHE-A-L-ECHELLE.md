# Des milliers de documents — comment on fait, vraiment

> La question : « je veux que l'IA cherche dans tout et donne la bonne
> réponse ». La réponse courte : **l'IA n'est pas le sujet.** Ce qui
> décide de la qualité, c'est ce qu'on lui met sous les yeux.

---

## 1. Ce qui se passe vraiment quand tu poses une question

Beaucoup de gens imaginent que le modèle « lit » les 3 000 documents.
Il n'en lit aucun. Voici la vraie chaîne :

```
   ta question
        │
        ▼
  ┌─────────────────┐   ① le moteur choisit 10 à 20 passages parmi des
  │   RECHERCHE     │      centaines de milliers
  └────────┬────────┘
           ▼
  ┌─────────────────┐   ② le modèle ne voit QUE ces passages
  │     MODÈLE      │      et rédige à partir d'eux
  └────────┬────────┘
           ▼
     réponse + citations
```

**Si l'étape ① rate, l'étape ② ment.** Le modèle ne dira pas « je n'ai
pas les bons documents » : il répondra avec ce qu'on lui a donné, même
si c'est à côté. C'est l'unique cause des mauvaises réponses que les
gens attribuent à « l'IA qui hallucine ».

**Conséquence : 90 % du travail est dans la recherche, pas dans l'IA.**
Changer de modèle ne rattrape jamais une mauvaise recherche.

---

## 2. Les six choses qui font la différence

### ① Recherche hybride — mots-clés ET sémantique

Deux façons de chercher, complémentaires :

| | Trouve bien | Rate |
|---|---|---|
| **Mots-clés** (BM25) | `ETII-TEC-032`, `EN 3475`, `indice C`, un terme exact | « comment éviter la corrosion entre deux métaux » (mots différents) |
| **Sémantique** (vecteurs) | le sens, les synonymes, les reformulations | **les références exactes** — un numéro n'a pas de sens sémantique |

En documentation technique, la moitié des recherches sont des
références. **Une recherche purement sémantique est donc un piège** :
elle est impressionnante en démonstration et décevante au quotidien.

**Ce qu'il faut : les deux, fusionnés.** On lance les deux recherches,
on fusionne les classements. C'est le standard, et c'est non négociable
pour du technique. Quand tu évalueras un outil, **la question à poser
est « faites-vous de l'hybride ? »** — pas « quel modèle ? ».

### ② Filtrer avant de chercher

Sur 3 000 documents, si on sait que la question porte sur le harnais du
H160, on ne cherche que dans les 80 documents concernés. Le gain de
précision est énorme et gratuit.

Cela demande des **métadonnées propres** sur chaque document :

```
  métier · porteur · périmètre (H160 / H175 / transverse)
  type (norme, process, outil…) · indice · date · pôle
```

**C'est exactement ce que ton portail gère déjà.** Ce n'est pas un
hasard : ces facettes sont ce qui rend la recherche fine, aujourd'hui
sans IA et demain avec.

### ③ Le découpage compte plus que le modèle

Un guide de 400 pages doit être coupé en morceaux. Coupé tous les 1 000
caractères au hasard, on obtient des passages comme :

> « …la distance minimale est de 25 mm. Dans le cas contraire… »

**Minimale entre quoi et quoi ?** Le morceau est inutilisable, et le
modèle répondra n'importe quoi avec.

**La règle : couper par section, et garder le titre de la section dans
chaque morceau.**

> « [Guide de routage — 4.2 Séparation des faisceaux] La distance
> minimale est de 25 mm. Dans le cas contraire… »

Là, le passage se suffit à lui-même. Même modèle, réponse juste.

### ④ Les indices : le vrai tueur

Répondre en citant l'indice B alors que l'indice C est en vigueur est
**pire que ne pas répondre** : c'est faux, et c'est crédible.

**La règle, simple et impitoyable : un document remplacé sort de
l'index le jour où il est remplacé.** Si tu veux garder l'historique,
garde-le dans le fonds documentaire, pas dans l'index de recherche.

Corollaire : tu as besoin de savoir **qui** retire. Sans un responsable
nommé, l'index pourrit en six mois et l'outil perd la confiance des
gens — et une fois perdue, elle ne revient pas.

### ⑤ Citations obligatoires

Chaque réponse porte le document et le passage d'origine. Une réponse
sans citation doit être affichée comme **non vérifiable**, pas comme une
réponse. C'est déjà le comportement prévu dans le portail.

### ⑥ Mesurer, sinon tu navigues à l'aveugle

Écris **30 à 50 vraies questions** que tes ingénieurs posent, avec la
bonne réponse et le bon document notés à la main. C'est ton jeu d'essai.

À chaque changement (découpage, filtres, modèle, réglages), tu relances
les 50 questions et tu comptes :

- **Le bon document est-il dans les passages retrouvés ?** (le seul
  chiffre qui compte vraiment — si non, aucune IA ne sauvera la réponse)
- La réponse est-elle juste ?
- Cite-t-elle le bon document ?

Une demi-journée pour construire ce jeu. Sans lui, tu ne sauras jamais
si un changement améliore ou dégrade, et tu prendras des décisions au
feeling sur un outil utilisé par 400 personnes.

---

## 3. L'ordre de travail — contre-intuitif mais payant

| Ordre | Quoi | Pourquoi |
|---|---|---|
| **1** | **Nettoyer les métadonnées et les noms de fichiers** | C'est le plus gros gain, et ça ne coûte pas un euro d'IA |
| **2** | **Sortir les documents périmés** | Un index propre bat un index gros |
| **3** | Recherche hybride + filtres | La sélection, donc la qualité des réponses |
| **4** | Découpage par section | Des passages qui se suffisent |
| **5** | **Seulement là**, brancher l'IA | Elle rédige ; elle ne répare rien en amont |
| **6** | Le jeu de 50 questions, en continu | Pour savoir où tu en es |

Le réflexe habituel est de commencer par 5. C'est ce qui produit les
démonstrations impressionnantes et les outils abandonnés au bout de
trois mois.

---

## 4. Deux moteurs, deux usages — garde les deux

```
  « guide routage harnais »        ──▶  recherche du portail  ──▶  la fiche du document
  « à quelle distance minimale
    d'un faisceau de puissance ? » ──▶  assistant             ──▶  la réponse + la citation
```

La recherche du portail est **instantanée, gratuite, hors ligne, et ne
se trompe jamais sur une référence**. Elle restera le geste le plus
fréquent : les gens cherchent « le » document bien plus souvent qu'ils
ne posent une question rédigée. L'assistant ne la remplace pas.

### Le portail tient-il à 3 000 documents ?

Oui, avec une réserve mesurée :

- **Jusqu'à ~2 000 documents** : l'index actuel (construit au chargement
  dans le navigateur) reste sous 5 Mo et se construit en moins d'une
  seconde. Rien à changer.
- **Au-delà de ~5 000** : il faut construire l'index **une fois**, à la
  publication, et le livrer déjà fait — le navigateur ne le recalcule
  plus. C'est une journée de travail, à faire quand tu approcheras du
  seuil, pas avant.
- **Au-delà de ~20 000** : le fonds n'a plus sa place dans un fichier
  statique ; c'est le moment du chemin « Gemini Enterprise » de
  `docs/ASSISTANT-IA.md`.

---

## 5. Les questions à poser à un fournisseur

Quand la DSI te présentera un outil, ces cinq questions te diront en
dix minutes s'il tient la route :

1. **« Faites-vous de la recherche hybride, mots-clés et sémantique ? »**
   Si la réponse est « nous utilisons des embeddings de dernière
   génération », c'est non.
2. **« Comment découpez-vous mes documents, et puis-je le régler ? »**
   Si le découpage est une boîte noire fixe, les guides longs
   répondront mal.
3. **« Puis-je filtrer par métier, périmètre et indice avant la
   recherche ? »** Sans filtres, la précision s'effondre à l'échelle.
4. **« Les réponses respectent-elles les droits d'accès de celui qui
   pose la question ? »** À 400 personnes, c'est éliminatoire.
5. **« Comment mesurez-vous la qualité, et puis-je rejouer mon propre
   jeu de questions ? »** Sans mesure, personne ne sait rien.

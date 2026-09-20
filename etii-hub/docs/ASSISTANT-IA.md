# Poser une question au fonds documentaire — le guide

> Objectif : taper « quelle est la règle de séparation entre un faisceau
> de puissance et un faisceau signal ? » et obtenir **la** réponse, tirée
> des documents du service, **avec la référence du document et la page**.
>
> Faits vérifiés le 20 septembre 2026 sur la documentation Google. Les
> tarifs et les noms de produits bougent vite : revérifiez avant de vous
> engager. Ce document ne remplace pas l'avis de votre DSI.

---

## 0. La chose à savoir avant tout le reste

**Une clé API Gemini personnelle ne doit jamais toucher un document
d'entreprise.** Deux raisons, pas une :

1. **Les conditions d'usage.** Sur les *Unpaid Services* de l'API Gemini
   (clé gratuite, AI Studio), Google écrit noir sur blanc qu'il utilise
   vos contenus « pour fournir, améliorer et développer les produits
   Google », et que **des relecteurs humains peuvent lire vos données**.
   Sur les *Paid Services* (facturation activée), ce n'est plus le cas.
   La bascule gratuit → payant n'est donc pas une histoire de quota :
   c'est une histoire de confidentialité.
2. **Le contrôle export.** Un document d'ingénierie électrique
   hélicoptère peut relever du contrôle des biens à double usage
   (règlement UE 2021/821) ou de l'ITAR/EAR s'il y a du contenu
   américain. L'envoyer vers un service cloud dont vous ne maîtrisez ni
   la région ni les accès, c'est potentiellement un transfert non
   autorisé. Ce n'est pas un risque théorique.

**Conclusion pratique** : montez la maquette sur des documents publics
ou fictifs, et faites valider le chemin de production par la DSI **avant**
d'y mettre le premier document réel.

---

## 1. Les trois chemins possibles

| | A — File Search (API Gemini) | B — Gemini Enterprise | C — Gemini Notebook Enterprise |
|---|---|---|---|
| **Ce que c'est** | Un « magasin de fichiers » géré par Google : il découpe, indexe et cite vos documents | Recherche intranet + assistant, connecté à vos sources existantes | Un carnet de recherche sur un lot de documents choisi |
| **Qui l'installe** | Vous, avec une clé API et un bout de code | La DSI, dans le projet Google Cloud du groupe | La DSI, puis vous |
| **Droits d'accès** | ❌ aucun : qui interroge voit tout | ✅ *permissions-aware* : chacun ne voit que ce à quoi il a droit | selon le carnet |
| **Sources** | fichiers que vous poussez | connecteurs SharePoint, Drive, Confluence, Jira, ServiceNow… | fichiers ajoutés au carnet |
| **Effort** | jours | semaines à mois (c'est un projet) | heures |
| **Pour vous** | la maquette | **la cible** | la preuve de valeur immédiate |

### Recommandation

1. **Cette semaine** : maquette en A, sur des documents non sensibles.
   Elle vous sert à montrer ce que ça donne et à convaincre.
2. **En parallèle** : demandez à la DSI si le groupe a déjà **Gemini
   Enterprise** ou un équivalent (Microsoft Copilot, Glean…). Dans une
   entreprise de cette taille, la réponse est souvent « oui, mais
   personne ne le sait ». Vous éviterez de rebâtir ce qui existe.
3. **En cible** : B, parce que c'est le seul chemin qui respecte les
   droits d'accès document par document. Sans ça, votre assistant
   répondra à un stagiaire avec le contenu d'un document restreint.

---

## 2. Chemin A — la maquette, en détail

### 2.1 Comment ça marche

```
 vos fichiers            File Search Store                 votre question
 (PDF, docx, txt)  ──▶   découpage en morceaux    ──▶     + morceaux pertinents  ──▶  réponse
                         + index sémantique                  (Gemini)                  + citations
```

Google fait le découpage et l'index tout seul. À l'interrogation, il
retrouve les bons morceaux, les donne au modèle, et la réponse revient
avec des **annotations `file_citation`** : nom du fichier et passage
d'origine. C'est ce qui fait la différence entre « une réponse » et « une
réponse qu'on peut vérifier ».

### 2.2 Les étapes

1. **Créer le projet et la clé.** [aistudio.google.com](https://aistudio.google.com)
   → « Get API key ». Créez la clé dans un **projet Google Cloud dédié**,
   pas dans un projet personnel.
2. **Activer la facturation sur ce projet.** C'est ce qui fait basculer
   en *Paid Services*, donc hors réutilisation de vos données. Sans
   facturation, ne mettez rien de confidentiel.
3. **Créer un magasin** (`fileSearchStores`), un par périmètre : un pour
   ETIIA, un pour ETIIE, un pour ETIII, ou un par famille de documents.
   C'est votre seul moyen de cloisonner en chemin A.
4. **Y verser les documents.** Import direct, ou upload puis import.
   Limites constatées : **100 Mo par document**, 1 Go gratuit de
   stockage, et Google recommande de **rester sous 20 Go par magasin**
   pour que la recherche reste rapide.
5. **Interroger** en passant `file_search_store_names` dans la requête,
   et **lire les citations** dans la réponse.
6. **Réindexer** quand les documents changent : rien ne se met à jour
   tout seul.

### 2.3 Ce que ça coûte

- **Stockage** : gratuit.
- **Indexation** : facturée au titre des embeddings, **0,15 $ par million
  de tokens** indexés (une fois, à l'import).
- **Interrogation** : les morceaux retrouvés sont facturés comme des
  tokens d'entrée normaux, au tarif du modèle choisi.

Ordre de grandeur pour se faire une idée : un fonds de 2 000 pages
represente très grossièrement 1 à 1,5 million de tokens, soit **moins de
0,25 $ à indexer**. Le coût réel, c'est l'usage quotidien, pas l'index.

### 2.4 Le piège à ne pas rater

**La clé API ne doit jamais se trouver dans le site.** Le portail ETII
est un site statique : tout ce qu'il contient est lisible par quiconque
ouvre les outils du navigateur. Une clé dans le JavaScript, c'est une
clé publique — facturée sur votre projet, par n'importe qui.

Il faut donc un intermédiaire qui détient la clé et que le site appelle :

```
navigateur (site ETII)  ──▶  intermédiaire (Apps Script / Cloud Run)  ──▶  API Gemini
   pas de clé                  la clé vit ici, côté serveur
```

Deux implémentations possibles :

- **Apps Script** (le plus simple, vous savez déjà faire) :
  `tools/apps-script/assistant-proxy.gs` dans ce dépôt. La clé va dans
  les *propriétés du script*, jamais dans le code. Déploiement en
  application web, accès restreint au domaine.
- **Cloud Run** (le plus propre) : un petit service, la clé dans Secret
  Manager, l'authentification par le compte Google de l'utilisateur.
  C'est ce que la DSI voudra si le projet grandit.

---

## 3. Chemin B — la cible, et comment l'obtenir

**Gemini Enterprise** est décrit par Google comme une recherche intranet
et un assistant, avec des connecteurs prêts pour SharePoint, Confluence,
Jira, ServiceNow et l'espace Google Workspace, et — le point qui compte —
des résultats **soumis aux droits d'accès** de celui qui pose la
question. C'est la seule façon propre de servir 300 à 500 personnes qui
n'ont pas toutes les mêmes habilitations.

Ce n'est pas quelque chose que vous installez : c'est un projet. Votre
rôle est d'arriver avec un dossier, pas avec une demande.

### Qui contacter, dans quel ordre

| Interlocuteur | Ce que vous lui demandez | Ce qu'il va vous demander |
|---|---|---|
| **1. Votre manager / chef de service** | Le mandat : « je porte ce sujet pour ETII » | Le gain en heures, pour combien de personnes |
| **2. La DSI / l'équipe Digital Workplace** | « Avons-nous déjà Gemini Enterprise, Copilot ou Glean ? Sinon, quel est le chemin agréé pour un assistant documentaire ? » | Le volume, les sources, le nombre d'utilisateurs |
| **3. La sécurité des systèmes d'information (RSSI)** | La classification admise : jusqu'à quel niveau de confidentialité peut-on indexer ? | La liste des types de documents |
| **4. Le référent contrôle export / conformité** | Y a-t-il du contenu sous contrôle dans le périmètre ? | Les références documentaires concernées |
| **5. Le DPO** | Si des noms de personnes apparaissent dans les documents | La finalité, la durée de conservation |
| **6. Les achats / le contrôle de gestion** | Le porteur du budget et le contrat-cadre Google existant | Le coût annuel estimé |

**L'ordre compte.** Arriver chez le RSSI sans le mandat de votre chef,
c'est un non. Arriver avec une maquette qui fonctionne, un périmètre
écrit et une estimation de coût, c'est une discussion.

### Ce qu'il faut préparer avant la première réunion

1. **Le périmètre** : quels documents, combien, où ils sont aujourd'hui,
   qui a le droit de les lire.
2. **Le gain** : « chaque ingénieur cherche un document *n* fois par
   semaine et y passe *m* minutes ; sur 400 personnes, cela fait *X*
   heures par an ». Mesurez-le, même grossièrement — le portail peut
   vous aider en comptant les recherches faites.
3. **Ce que vous ne demandez pas** : pas d'accès à tout, pas de nouveau
   fournisseur si le groupe a déjà un outil, pas de données classifiées
   au premier tour.
4. **La maquette** (chemin A), sur des documents publics.

---

## 4. Où stocker les documents

Le point le plus souvent négligé, et celui qui décide de tout.

**Règle simple : une seule source de vérité, et l'assistant lit cette
source — il ne la remplace pas.**

| Où | Pour | Contre |
|---|---|---|
| **L'espace documentaire existant** (SharePoint, Drive du service) | Les droits sont déjà posés, les gens y sont | Il faut un connecteur (chemin B) ou une synchronisation |
| **Un Drive dédié « fonds ETII »** | Simple, maîtrisé par le service | Une copie de plus à tenir à jour |
| **Le magasin File Search seul** | Rien à gérer | ❌ aucun droit d'accès, aucune version, aucune traçabilité — **jamais comme source unique** |

**Ce qu'il faut faire, quel que soit le chemin :**

1. Un **dossier par périmètre**, avec les droits d'accès posés dessus.
2. Un **nom de fichier normalisé** : `ETII-TEC-001_indice-C_routage-harnais.pdf`.
   L'indice dans le nom, c'est ce qui évite de répondre avec la version
   périmée.
3. **Un porteur par document**, nommé — c'est déjà dans le portail.
4. **Un document = un fichier** : pas de « guide complet » de 400 pages
   qui répond à tout et donc à rien.
5. **Une purge** : un document retiré du fonds doit être retiré de
   l'index le jour même. Prévoyez qui le fait.

---

## 5. Ce que le portail apporte déjà, et ce qu'il apportera

**Déjà :** la recherche documentaire du portail trouve un document par
son titre, sa référence, son métier, son porteur, avec tolérance aux
fautes de frappe — sans aucun service externe, instantanément. Pour
« retrouver LE document », c'est souvent suffisant, et ça le restera.

**L'assistant répond à une autre question** : pas « où est le document »
mais « que dit le document ». Les deux coexistent :

```
  « guide routage harnais »  ──▶  recherche documentaire  ──▶  la fiche du document
  « à quelle distance d'un
    faisceau de puissance ? » ──▶  assistant             ──▶  la réponse + la citation
```

Le point de raccordement est déjà écrit dans le portail :
`assets/js/assistant.js`, constante `SOURCE`. Tant qu'elle est vide, le
bloc explique qu'il n'est pas raccordé et **ne montre aucune réponse
inventée**. Le jour où vous collez l'URL de votre intermédiaire, il
s'active — rien d'autre à changer.

---

## 6. Le plan, en clair

| Quand | Quoi | Qui |
|---|---|---|
| Semaine 1 | Maquette chemin A sur 20 documents publics, avec le proxy Apps Script | Vous |
| Semaine 1 | Mesurer : combien de recherches, combien de temps perdu | Vous |
| Semaine 2 | Montrer la maquette au chef de service, obtenir le mandat | Vous |
| Semaine 3 | DSI : « qu'avons-nous déjà ? quel est le chemin agréé ? » | Vous + chef |
| Semaine 4+ | RSSI, contrôle export, DPO — périmètre écrit | DSI pilote |
| Ensuite | Chemin B sur un pôle pilote, puis extension | DSI + vous |

**Ne sautez pas l'étape 3.** Dans un groupe de cette taille, la question
n'est presque jamais « peut-on faire de l'IA ? » mais « pourquoi
faites-vous ça dans votre coin alors que nous avons déjà l'outil ? ».

---

## 7. Les questions qu'on vous posera, et les réponses

> **« Et si l'IA invente une réponse ? »**
> C'est pour ça que les citations sont obligatoires. Une réponse sans
> citation est une réponse à jeter, et l'interface doit le montrer comme
> tel. Le portail affichera la source sous chaque réponse, exactement
> comme les fiches des porteurs affichent la leur.

> **« Nos données servent-elles à entraîner le modèle ? »**
> Sur les services payants de l'API Gemini, non — les conditions le
> disent explicitement. Sur la version gratuite, oui, et des relecteurs
> humains peuvent y accéder. D'où la facturation activée dès le premier
> document interne.

> **« Où sont hébergées les données ? »**
> Question pour la DSI : elle se règle au niveau du projet Google Cloud
> (région, résidence des données, engagements contractuels du groupe).
> Ne répondez pas à sa place.

> **« Qui paie ? »**
> Pour la maquette, quelques euros par mois : demandez une carte achat
> ou un budget d'expérimentation. Pour la cible, c'est une ligne
> budgétaire à porter par le service ou la DSI — d'où l'étape « achats ».

> **« Combien de temps avant que ça marche ? »**
> La maquette : quelques jours. La cible, dans une grande entreprise :
> comptez en mois, l'essentiel du délai étant les validations, pas la
> technique.

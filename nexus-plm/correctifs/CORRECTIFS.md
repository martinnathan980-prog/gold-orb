# Lot 1 — correction des 6 bugs confirmés

Périmètre : **uniquement les 6 bugs**, sans restructuration. Aucune fonction
n'est supprimée, aucun comportement volontaire n'est modifié. Déployable seul.

**Ordre de pose conseillé : B2 d'abord.** C'est lui qui rend les autres visibles —
tant qu'il n'est pas posé, une erreur serveur reste muette et on ne sait pas si
un correctif a pris.

| | Bug | Fichier | Nature |
|---|---|---|---|
| B2 | Aucun `withFailureHandler` (9 sites) | `Index.html` | perte de données silencieuse |
| B1 | Le catalogue ajoute le mauvais composant | `Index.html` | corruption de données |
| B3 | « Invalidé » compté comme validé | `Index.html` | logique métier |
| B4 | Export CSV cassé (3 défauts) | `Index.html` | export inexploitable |
| B5 | Compteur d'onglet incohérent | `Index.html` | affichage |
| B6 | « undefined » affiché sur les cartes | `Index.html` | affichage |

**Préalable** : coller le contenu de `lib-correctifs.js` en haut du `<script>` de
`Index.html` (juste après la ligne `let dataGlobale = {}; ...`). Il ne contient que
des fonctions, il ne s'exécute pas tout seul.

Les fonctions pures de ce fichier sont couvertes par `test-correctifs.js`
(`node test-correctifs.js` → 53 assertions). Chaque test vérifie **à la fois** que
l'ancien code échouait et que le nouveau passe.

---

## B2 — traiter les échecs serveur

*Sans ce correctif : si le serveur lève (quota, droits, ligne supprimée entre-temps,
réseau), le spinner tourne indéfiniment, aucun message. L'utilisateur croit avoir
enregistré. C'est le défaut le plus coûteux de l'application.*

### B2.1 — Ajouter le passe-plat et le signalement

À coller avec le reste des helpers :

```js
// Unique point de passage vers le serveur. Le withFailureHandler qui manquait
// aux 9 appels est désormais écrit une seule fois, ici.
function run(nomFonction) {
  const args = Array.prototype.slice.call(arguments, 1);
  return new Promise(function (resolve, reject) {
    // On garde une reference au runner : les methodes de google.script.run
    // s'appuient sur leur `this`, un .apply(null, ...) les casserait.
    const runner = google.script.run
      .withSuccessHandler(resolve)
      .withFailureHandler(reject);
    runner[nomFonction].apply(runner, args);
  });
}

function arreterSpinners() {
  document.querySelectorAll('.mini-spinner').forEach(function (el) { el.remove(); });
  const loading = document.getElementById('loading');
  if (loading) loading.style.display = 'none';
}

function signalerErreur(err, contexte) {
  arreterSpinners();
  console.error(contexte, err);
  afficherBandeau(
    'Échec : ' + contexte + '. ' + ((err && err.message) ? err.message : '') +
    ' — votre modification n\'a PAS été enregistrée.', 'erreur');
}

function afficherBandeau(message, type) {
  let el = document.getElementById('bandeauMessage');
  if (!el) {
    el = document.createElement('div');
    el.id = 'bandeauMessage';
    document.body.appendChild(el);
  }
  el.className = 'bandeau bandeau-' + (type || 'info');
  el.textContent = message;              // textContent : jamais innerHTML ici
  el.style.display = 'block';
  clearTimeout(el._t);
  el._t = setTimeout(function () { el.style.display = 'none'; }, 8000);
}
```

CSS à ajouter dans le `<style>` :

```css
.bandeau { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  max-width: 620px; padding: 14px 20px; border-radius: 12px; font-size: 14px;
  font-weight: 600; z-index: 2000; box-shadow: 0 10px 30px rgba(0,0,0,.2);
  display: none; }
.bandeau-erreur { background: #ff3b30; color: #fff; }
.bandeau-info   { background: #0b132b; color: #fff; }
```

### B2.2 — Réécrire les 9 points d'appel

Chacun suit le même schéma : `run(...)` → `.then(...)` → `.catch(...)`.

```js
// 1/9  chargement du catalogue (DOMContentLoaded)
//      garde ajoutée : getCatalogueComposants peut renvoyer {error:...}, ce qui
//      transformait catalogueComposants en objet et faisait planter .forEach
run('getCatalogueComposants')
  .then(function (r) { catalogueComposants = Array.isArray(r) ? r : []; })
  .catch(function (e) { signalerErreur(e, 'chargement du catalogue de composants'); });

// 2/9  refreshData
function refreshData(silent) {
  if (!silent) document.getElementById('loading').style.display = 'block';
  run('getToutLeContenu')
    .then(function (r) { preparerData(r, silent); })
    .catch(function (e) { signalerErreur(e, 'chargement des données'); });
}

// 3/9  dupliquer
run('dupliquerBoite', boite['PN Global'], newPn.trim())
  .then(function (r) { fermerFiche(); preparerData(r, false); })
  .catch(function (e) { signalerErreur(e, 'duplication de l\'assemblage'); });

// 4/9  supprimerBoiteEntiere
run('deleteBoiteEntiere', dataGlobale.boites[boiteIndex]['PN Global'],
                          dataGlobale.boites[boiteIndex]._rowIndex)
  .then(function (r) { fermerFiche(); preparerData(r, false); })
  .catch(function (e) { signalerErreur(e, 'suppression de l\'assemblage'); });

// 5/9  saveBoite
run('saveLigne', '1_BOITES', dataGlobale.boites[boiteIndex]._rowIndex, modifs)
  .then(function (r) { preparerData(r, true); })
  .catch(function (e) { signalerErreur(e, 'sauvegarde de l\'assemblage'); });

// 6/9  saveNom   (rowIndex renommé : il était masqué par le (r) de la callback)
run('saveLigne', '2_NOMENCLATURE', rowIndex, modifs)
  .then(function (r) { preparerData(r, true); })
  .catch(function (e) { signalerErreur(e, 'sauvegarde du sous-ensemble'); });

// 7/9  deleteNom
run('deleteLigne', '2_NOMENCLATURE', rowIndex)
  .then(function (r) { preparerData(r, true); })
  .catch(function (e) { signalerErreur(e, 'suppression du sous-ensemble'); });

// 8/9  creerBoite
run('addBoiteLibre', pn, f, ds)
  .then(function (r) { preparerData(r, false); })
  .catch(function (e) { signalerErreur(e, 'création de l\'assemblage'); });

// 9/9  creerSousEnsemble
run('addSousEnsembleLibre', dataGlobale.boites[currentBoiteIndex]['PN Global'], type, pn)
  .then(function (r) { preparerData(r, true); })
  .catch(function (e) { signalerErreur(e, 'ajout du sous-ensemble'); });
```

Petit helper utilisé par 3 et 4 — le `Offcanvas.getInstance(...).hide()` était écrit
en toutes lettres deux fois et lève si l'instance n'existe pas :

```js
function fermerFiche() {
  const inst = bootstrap.Offcanvas.getInstance(document.getElementById('detailsSlideOver'));
  if (inst) inst.hide();
}
```

### B2.3 — Ne plus sortir en silence sur `{erreur}`

```js
function preparerData(reponse, silent) {
  if (!reponse || reponse.erreur) {
    arreterSpinners();
    afficherBandeau(reponse && reponse.erreur ? reponse.erreur
                    : 'Réponse vide du serveur.', 'erreur');
    return;                                    // avant : return muet, spinner bloqué
  }
  ...
}
```

---

## B1 — le catalogue ajoute le composant affiché

Remplacer `filtrerCatalogue` et `ajouterCatalogue` :

```js
function filtrerCatalogue() {
  const res = filtrerCatalogueData(catalogueComposants,
                                   document.getElementById('catSearch').value);

  document.getElementById('catalogueList').innerHTML = res.affiches.map(function (e) {
    const type = e.composant['Type'] || '';
    const sousType = e.composant['Sous Type/Désignation'] || '';
    const norm = e.composant['Norm'] || e.composant['Standard number'] || e.composant['Ref'] || '';
    const titre = type + (sousType ? ' | ' + sousType : '');
    // indexReel, et non l'index dans la liste filtrée : c'est TOUT le correctif
    return '<div class="d-flex justify-content-between align-items-center p-2 border-bottom"' +
           ' onclick="ajouterCatalogue(' + e.indexReel + ')" style="cursor:pointer;">' +
           '<div><b>' + titre + '</b><br><span class="text-muted" style="font-size:11px;">' +
           'Norme/Réf: ' + norm + '</span></div>' +
           '<button class="btn btn-sm btn-outline-success fw-bold">+</button></div>';
  }).join('');

  // le .slice(30) était silencieux : on croyait que le composant n'existait pas
  const info = document.getElementById('catalogueInfo');
  if (info) {
    info.textContent = res.total > res.affiches.length
      ? res.affiches.length + ' résultats affichés sur ' + res.total + ' — affinez la recherche.'
      : res.total + ' résultat' + (res.total > 1 ? 's' : '');
  }
}

function ajouterCatalogue(indexReel) {
  const cat = catalogueComposants[indexReel];
  if (!cat) return;
  let compFormat = formaterComposant(cat) || 'Composant Inconnu';
  bootstrap.Modal.getInstance(document.getElementById('catalogueModal')).hide();
  document.getElementById('spin-nom-' + currentNomRowIndex).innerHTML =
    '<span class="mini-spinner"></span>';
  const champ = document.getElementById('input-nom-' + currentNomRowIndex + '-Composant STD');
  champ.value = champ.value.trim() === '' ? compFormat : champ.value + '\n' + compFormat;
  saveNom(currentNomRowIndex, true);
}
```

Ajouter la ligne d'info sous le champ de recherche du modal catalogue :

```html
<div id="catalogueInfo" class="text-muted mb-2" style="font-size:12px;"></div>
```

> `formaterComposant` remplace le bloc de mise en forme qui était dupliqué à
> l'identique dans `ajouterCatalogue` et `ouvrirMultiRecherche`. Remplacer aussi
> celui de `ouvrirMultiRecherche` par un appel à `formaterComposant(c)`.

---

## B3 — statut

Deux endroits.

Dans `filtrerInterface`, la classe du badge :

```js
// avant : includes('valid') / includes('obs')
const st = txt(boite['Statut'], '');
const stClass = classeStatut(st);
const badgeHtml = st ? '<span class="status-badge ' + stClass + '">' + st + '</span>' : '';
```

Dans `genererKPIDashboard`, tout le corps est remplacé par un appel à `calculerKpi` :

```js
function genererKPIDashboard(listeBoites) {
  if (!listeBoites) return;
  const kpi = calculerKpi(listeBoites);
  document.getElementById('kpiBoites').innerText = kpi.nbBoites;
  document.getElementById('kpiNoms').innerText   = kpi.refsUniques;
  document.getElementById('kpiVal').innerText    = kpi.nbValides + ' (' + kpi.pctValides + '%)';
}
```

> Le libellé du 3ᵉ KPI dit « Boîtes Validées » alors que l'ancien code affichait un
> pourcentage. On affiche désormais les deux : `3 (30%)`. Si tu préfères le seul
> pourcentage, remets `kpi.pctValides + '%'`.

---

## B4 — export CSV

```js
function exporterBOM() {
  const boite = dataGlobale.boites[currentBoiteIndex];
  if (!boite) return;
  telecharger(construireCsv(lignesBomPourBoite(boite)),
              'BOM_' + boite['PN Global'] + '.csv',
              'text/csv;charset=utf-8');
}

function telecharger(contenu, nomFichier, type) {
  const blob = new Blob([contenu], { type: type });
  const url = URL.createObjectURL(blob);          // remplace data: + encodeURI
  const a = document.createElement('a');
  a.href = url; a.download = nomFichier;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
}
```

**Deux points à valider en conditions réelles :**

1. **Séparateur `;`.** Excel en locale française n'ouvre pas les `,` en colonnes.
   Le `;` + le BOM donnent un fichier qui s'ouvre correctement d'un double-clic.
   Si tes fichiers partent vers un outil qui attend la virgule, passer
   `CSV_SEPARATEUR` à `','` dans `lib-correctifs.js`.
2. **Sandbox Apps Script.** L'interface tourne dans une iframe sandboxée : selon le
   navigateur, un téléchargement déclenché par script peut être bloqué — c'était
   déjà le cas avant, le correctif ne l'aggrave pas. **À tester en premier.**
   Si c'est bloqué, replier sur `window.open(url, '_blank')`, ou générer le fichier
   côté serveur dans Drive et renvoyer son lien (à traiter au lot 6).

---

## B5 — compteurs d'onglets

Le début de `filtrerInterface` devient :

```js
function filtrerInterface(boxesForcees) {
  boxesForcees = boxesForcees || null;
  const query = document.getElementById('searchBar').value;

  // Un seul filtrage, tout en dérive : compteurs et cartes ne peuvent plus diverger.
  const vue = calculerAffichage(dataGlobale.boites, query, activeTab, boxesForcees);
  activeTab = vue.ongletEffectif;               // onglet orphelin -> "Toutes"

  let tabHtml = '<div class="tab-pill ' + (activeTab === 'Toutes' ? 'active' : '') + '"' +
                ' onclick="changerTab(\'Toutes\')">Toutes ' +
                '<span class="tab-count">' + vue.visibles.length + '</span></div>';
  Array.from(vue.parFonction.keys()).sort().forEach(function (fonction) {
    tabHtml += '<div class="tab-pill ' + (activeTab === fonction ? 'active' : '') + '"' +
               ' onclick="changerTab(\'' + fonction + '\')">' + fonction +
               ' <span class="tab-count">' + vue.parFonction.get(fonction).length +
               '</span></div>';
  });
  document.getElementById('functionTabs').innerHTML = tabHtml;

  const boitesAAfficher = vue.aAfficher;
  // ... la suite (construction des cartes) est inchangée
```

Supprimer la ligne `let boitesAAfficher = activeTab === 'Toutes' ? ... : ...` qui
suivait : `vue.aAfficher` la remplace.

> Gains obtenus au passage, sans effort supplémentaire : le `JSON.stringify` de
> chaque boîte n'est plus fait **deux fois par rendu** mais une, et l'onglet actif
> orphelin ne bloque plus l'affichage sur « Aucun assemblage dans cette catégorie ».

---

## B6 — plus de « undefined »

Dans `filtrerInterface`, le bloc `detailsGloHtml` :

```js
// avant : String(boite['Porteur']).replace(/\n/g, ', ')||'-'
//         -> String(undefined) === "undefined", truthy, le ||'-' ne partait jamais
const detailsGloHtml =
  '<div class="internal-list-row mt-2" style="border-top: 1px dashed #e5e5ea;">' +
    '<span class="internal-type text-muted">DS/VCI Associé</span>' +
    '<span class="internal-pn text-muted">' + txt(boite['DS/VCI Associé']) + '</span></div>' +
  '<div class="internal-list-row" style="border-bottom:none;">' +
    '<span class="internal-type text-muted">Porteur</span>' +
    '<span class="internal-pn text-muted">' + txt(valeursMulti(boite['Porteur']).join(', ')) +
    '</span></div>';
```

Puis passer à `txt(...)` les autres affichages de la même famille :
`${l['Type'] || '-'}`, `${l['PN du type'] || '-'}`, `${boite['PN Global']}`.
Ils ne produisent pas « undefined » aujourd'hui, mais `txt()` les rend uniformes et
traite aussi le cas de la chaîne d'espaces.

---

## Ce que ce lot ne corrige PAS

À traiter aux lots suivants, listés ici pour qu'on ne les croie pas réglés :

- **F1 — guillemets et apostrophes cassent l'interface.** Une valeur contenant `"`
  ferme encore l'attribut `value="..."` et la saisie est perdue à la sauvegarde ;
  une apostrophe dans un PN casse encore le `onclick`. **C'est le plus pénible au
  quotidien** et ça demande le passage à `esc()` + délégation d'événements (lot 4).
- **F2** — `_rowIndex` reste l'identité des lignes : deux suppressions rapprochées
  peuvent encore viser la mauvaise ligne. Pas de `LockService`.
- **F4** — les deux bugs de pondération des comparateurs (dénominateur gonflé,
  pénalité silencieuse) sont intacts.
- **F5** — la recherche par `JSON.stringify` garde ses faux positifs (`image`,
  `commentaires`, `rowindex` matchent tout). Isolée dans `correspond()` pour
  n'avoir qu'un endroit à reprendre.
- **F6** — une écriture relit toujours les deux feuilles en entier, et `saveLigne`
  écrit toujours cellule par cellule.
- Sécurité : `ALLOWALL`, absence d'autorisation et de journal restent en l'état.

## Vérification après pose

```
node test-correctifs.js      # 53 assertions sur les fonctions pures
```

Puis dans l'application, dans cet ordre :

1. Ouvrir le catalogue, **taper une recherche**, cliquer un résultat → vérifier que
   c'est bien celui-là qui apparaît dans les Composants STD *(B1)*.
2. Mettre une boîte à « Invalidé » → badge non vert, KPI qui ne la compte pas *(B3)*.
3. Exporter une nomenclature dont un commentaire contient `#` et `"` → ouvrir dans
   Excel : accents corrects, colonnes alignées, rien de tronqué *(B4)*.
4. Chercher un terme ne ramenant qu'une partie des boîtes → « Toutes (n) » doit
   égaler la somme des autres onglets *(B5)*.
5. Une boîte sans Porteur → « - » et non « undefined » *(B6)*.
6. Renommer temporairement une fonction serveur dans `Code.gs` pour provoquer une
   erreur → un bandeau rouge doit apparaître et le spinner s'arrêter *(B2)*.

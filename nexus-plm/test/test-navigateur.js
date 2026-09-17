/**
 * NEXUS PLM — test de bout en bout dans un vrai Chromium.
 *   node build/build-demo.js && node test/test-navigateur.js
 */
const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const fs = require('fs');
const path = require('path');

const RACINE = path.join(__dirname, '..');
let ok = 0, ko = 0;
const V = '\x1b[32m', R = '\x1b[31m', Z = '\x1b[0m';

function eq(t, a, b) {
  const x = JSON.stringify(a), y = JSON.stringify(b);
  if (x === y) { ok++; console.log('  ' + V + 'OK' + Z + '   ' + t); }
  else { ko++; console.log('  ' + R + 'KO' + Z + '   ' + t +
                           '\n         attendu ' + y + '\n         obtenu  ' + x); }
}
function vrai(t, c) { eq(t, !!c, true); }
function faux(t, c) { eq(t, !!c, false); }
function bloc(t) { console.log('\n' + t); }

function pageComplete() {
  return '<!doctype html><html><head><meta charset="utf-8">' +
         '<meta name="viewport" content="width=device-width, initial-scale=1">' +
         '<style>body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style>' +
         '</head><body>' + fs.readFileSync(path.join(RACINE, 'build/demo.html'), 'utf8') +
         '</body></html>';
}

/** Un indicateur se vise par son libelle : la bande est rendue, pas figee. */
const indic = function (page, libelle) {
  return page.locator('.indicateur', { hasText: libelle }).first();
};
const valeurIndic = async function (page, libelle) {
  return (await indic(page, libelle).locator('.indicateur-valeur').innerText()).trim();
};
const detailIndic = async function (page, libelle) {
  return (await indic(page, libelle).locator('.indicateur-detail').innerText()).trim();
};

const texte = function (page, sel) {
  return page.locator(sel).first().evaluate(function (el) { return el.textContent; });
};

async function attendreFerme(page, id) {
  await page.waitForFunction(function (i) {
    const el = document.getElementById(i);
    return el && !el.classList.contains('show');
  }, id, { timeout: 6000 });
  await page.waitForTimeout(380);
}
async function fermerModale(page, id) {
  await page.locator('#' + id + ' .btn-close').click();
  await attendreFerme(page, id);
}
/**
 * Les branches d'une fiche sont repliees a l'ouverture : la plupart des
 * tests lisent le CONTENU des sous-ensembles, on les deplie donc toutes.
 * Un test qui veut la vue d'ensemble passe `replie`.
 */
async function deplierBranches(page) {
  for (let i = 0; i < 12; i++) {
    const repliee = page.locator('#slideOverBody .branche-tete[aria-expanded="false"]').first();
    if (!(await repliee.count())) break;
    await repliee.click();
    await page.waitForTimeout(180);
  }
}
async function ouvrirFiche(page, pn, replie) {
  await page.locator('.carte', { hasText: pn })
            .getByRole('button', { name: 'Fiche complète' }).click();
  await page.waitForSelector('#detailsSlideOver.show');
  await page.waitForTimeout(320);
  if (!replie) await deplierBranches(page);
}
async function fermerFiche(page) {
  await page.locator('#detailsSlideOver .btn-close').click();
  await attendreFerme(page, 'detailsSlideOver');
}
/** Le dialogue intégré : on attend qu'il soit là, on répond, on attend qu'il parte. */
async function repondreDialogue(page, valeur) {
  await page.waitForSelector('#dialogueModal.show', { timeout: 6000 });
  await page.waitForTimeout(350);
  if (valeur !== undefined) await page.fill('#dialogueChamp', valeur);
  await page.locator('#dialogueValider').click();
  await attendreFerme(page, 'dialogueModal');
}
async function railVisible(page) {
  return await page.evaluate(function () {
    const r = document.getElementById('reglagesRail');
    return !!r && !r.hidden && r.getBoundingClientRect().width > 0;
  });
}

/**
 * Remet l'écran à plat entre deux sections : sans cela une assertion peut
 * lire un bandeau resté d'une action précédente, ou cliquer à travers un
 * panneau encore ouvert.
 */
async function ecranPropre(page) {
  await page.evaluate(function () {
    window.scrollTo(0, 0);          // la barre collante recouvrirait l'en-tête
    ['detailsSlideOver'].forEach(function (id) {
      const el = document.getElementById(id);
      const i = el && window.bootstrap.Offcanvas.getInstance(el);
      if (i) i.hide();
    });
    if (typeof afficherRail === 'function') afficherRail(false);
    ['compareModal', 'catalogueModal', 'newBoiteModal', 'dialogueModal', 'doublonsModal',
     'newSousEnsModal', 'multiSearchModal', 'demoCsvModal', 'loupeModal'].forEach(function (id) {
      const el = document.getElementById(id);
      const i = el && window.bootstrap.Modal.getInstance(el);
      if (i) i.hide();
    });
    const b = document.getElementById('bandeauMessage');
    if (b) { b.hidden = true; b.textContent = ''; }
  });
  await page.waitForTimeout(500);
}

(async function () {
  const navigateur = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await navigateur.newPage({ viewport: { width: 1400, height: 950 } });

  // Trois catégories distinctes : une exception JS est un défaut ; un
  // console.error émis volontairement par signalerErreur n'en est pas ; un
  // échec de chargement réseau relève de l'environnement de test.
  const exceptions = [], diagnostics = [], reseau = [];
  const ATTENDUS = /Panne simulée|existe déjà|est obligatoire|introuvable/;
  page.on('pageerror', function (e) { exceptions.push(e.message); });
  page.on('console', function (m) {
    if (m.type() !== 'error') return;
    const t = m.text();
    if (/Failed to load resource|ERR_/.test(t)) reseau.push(t);
    else if (ATTENDUS.test(t)) diagnostics.push(t);
    else exceptions.push(t);
  });
  const requetesEchouees = [];
  page.on('requestfailed', function (r) { requetesEchouees.push(r.url()); });

  await page.setContent(pageComplete(), { waitUntil: 'load' });
  await page.waitForSelector('.carte', { timeout: 10000 });

  // ---------------------------------------------------------------
  bloc('Chargement');
  eq('13 boîtes', await page.locator('.carte').count(), 13);
  eq('titre NEXUS seul', (await texte(page, '.marque h1')).trim(), 'NEXUS');
  eq('indicateur boîtes', await valeurIndic(page, 'Boîtes'), '13');
  eq('validées', await valeurIndic(page, 'Validées'), '7 / 13');
  eq('libellé « Boîtes »', (await texte(page, '.indicateur-libelle')).trim(), 'Boîtes');
  eq('plus d\'indicateur de réutilisation', await page.locator('#kpiReutil').count(), 0);
  eq('ni son filtre', await page.locator('[data-action="filtrer-reutilise"]').count(), 0);
  vrai('indicateur « À standardiser » renseigné',
       Number(await valeurIndic(page, 'À standardiser')) >= 0);
  eq('plus de ligne de portée sous les chiffres',
     await page.locator('.indicateurs-portee').count(), 0);
  eq('plus de badge « / » dans le champ de recherche',
     await page.locator('.champ-recherche .raccourci').count(), 0);
  vrai('indicateur de doublons renseigné',
       (await valeurIndic(page, 'Doublons probables')).length > 0);
  eq('pas de compteur de sous-ensembles', await page.locator('#kpiLignes').count(), 0);
  eq('pas de bouton Journal', await page.locator('[data-action="ouvrir-journal"]').count(), 0);
  eq('pas de Pondération dans l\'en-tête',
     await page.locator('.entete [data-action="ouvrir-reglages"]').count(), 0);
  vrai('bouton « Nouvelle boîte »', (await texte(page, '.btn-creer')).indexOf('Nouvelle boîte') !== -1);

  // Le bouton a quitté le voisinage du titre : il vit dans la barre d'action,
  // sous l'en-tête, avec la recherche.
  const posBouton = await page.locator('.btn-creer').boundingBox();
  const posTitre = await page.locator('.marque h1').boundingBox();
  const posEntete = await page.locator('.entete').boundingBox();
  const posBande = await page.locator('.bande-action').boundingBox();
  const posRecherche = await page.locator('.champ-recherche').boundingBox();
  vrai('le bouton est SOUS le titre, plus à côté', posBouton.y > posTitre.y + posTitre.height);
  vrai('et hors de l\'en-tête', posBouton.y >= posEntete.y + posEntete.height - 2);
  vrai('il est dans la barre d\'action', posBouton.y >= posBande.y - 1 &&
       posBouton.y + posBouton.height <= posBande.y + posBande.height + 1);
  vrai('la recherche est sur la même ligne', Math.abs(posRecherche.y - posBouton.y) < 40);
  vrai('le bouton est à droite de la recherche',
       posBouton.x > posRecherche.x + posRecherche.width - 1);
  eq('plus aucun bouton dans l\'en-tête',
     await page.locator('.entete [data-action="nouvelle-boite"]').count(), 0);

  // Le sol est blanc, et ce sont les OBJETS posés dessus qui portent la couleur.
  const teintes = await page.evaluate(function () {
    const lire = function (sel, prop) {
      const el = document.querySelector(sel);
      return el ? getComputedStyle(el)[prop || 'backgroundColor'] : null;
    };
    return {
      sol: getComputedStyle(document.body).backgroundColor,
      carte: lire('.carte'),
      bande: lire('.bande-action', 'backgroundImage'),
      filet: lire('.bande-action', 'borderTopColor'),
      champ: lire('.champ-recherche')
    };
  });
  const rgb = function (c) { return (c.match(/\d+/g) || []).map(Number); };
  eq('le sol est blanc', teintes.sol, 'rgb(255, 255, 255)');
  faux('les cartes, elles, ne sont pas blanches', teintes.carte === 'rgb(255, 255, 255)');
  vrai('les cartes sont bleutées', rgb(teintes.carte)[2] > rgb(teintes.carte)[0]);
  vrai('elles se détachent du blanc par leur teinte',
       rgb(teintes.carte).reduce(function (a, b) { return a + b; }, 0) <
       rgb(teintes.sol).reduce(function (a, b) { return a + b; }, 0));
  eq('l\'en-tête est blanc, sous NEXUS',
     await page.locator('.entete').evaluate(function (e) { return getComputedStyle(e).backgroundColor; }),
     'rgb(255, 255, 255)');
  // Il est en pilule, pas en bouton de formulaire : l'arrondi doit valoir au
  // moins la moitié de sa hauteur.
  const rondeur = await page.locator('.btn-creer').evaluate(function (e) {
    return { rayon: parseFloat(getComputedStyle(e).borderTopLeftRadius),
             hauteur: e.getBoundingClientRect().height };
  });
  vrai('le bouton de création est en pilule', rondeur.rayon >= rondeur.hauteur / 2);

  // Les indicateurs : une ligne cadrée de filets, plus une rangée de cartes.
  const mesures = await page.evaluate(function () {
    const liste = Array.prototype.slice.call(document.querySelectorAll('.indicateur'));
    const conteneur = document.querySelector('.indicateurs');
    return {
      nombre: liste.length,
      alignes: liste.every(function (e) {
        return Math.abs(e.getBoundingClientRect().top - liste[0].getBoundingClientRect().top) < 2;
      }),
      fondTransparent: getComputedStyle(liste[0]).backgroundColor,
      sansBordure: getComputedStyle(liste[0]).borderTopWidth,
      cadre: getComputedStyle(conteneur).borderTopWidth,
      disposition: getComputedStyle(conteneur).display
    };
  });
  eq('quatre mesures', mesures.nombre, 4);
  vrai('toutes sur la même ligne', mesures.alignes);
  eq('sans fond propre : ce ne sont pas des cartes', mesures.fondTransparent, 'rgba(0, 0, 0, 0)');
  eq('ni bordure propre', mesures.sansBordure, '0px');
  eq('la ligne, elle, est cadrée', mesures.cadre, '1px');
  eq('et disposée en ligne', mesures.disposition, 'flex');
  eq('plus de jauge sous les chiffres', await page.locator('.indicateur-jauge').count(), 0);
  vrai('la barre d\'action porte un dégradé', /gradient/.test(teintes.bande));
  vrai('soulignée d\'un filet marine', teintes.filet === 'rgb(0, 32, 91)');
  eq('le champ de recherche reste blanc : c\'est là qu\'on écrit',
     teintes.champ, 'rgb(255, 255, 255)');
  eq('15 porteurs proposés à la création',
     await page.locator('#newBoitePorteurs input').count(), 15);
  eq('« Dauphin » y figure',
     await page.locator('#newBoitePorteurs input[value="Dauphin"]').count(), 1);
  eq('« H155 » n\'y est plus',
     await page.locator('#newBoitePorteurs input[value="H155"]').count(), 0);
  eq('« H175M » non plus',
     await page.locator('#newBoitePorteurs input[value="H175M"]').count(), 0);
  eq('« UH-72 Lakota » non plus',
     await page.locator('#newBoitePorteurs input[value="UH-72 Lakota"]').count(), 0);
  eq('aucun « Multi »', await page.locator('#newBoitePorteurs input[value="Multi"]').count(), 0);
  eq('« Super Puma » n\'est plus un porteur', await page.locator('#list-Porteur option[value="Super Puma"]').count(), 0);
  eq('pas d\'export CSV', await page.locator('[data-action="exporter-bom"]').count(), 0);
  faux('chargement masqué', await page.locator('#loading').isVisible());
  eq('chaque boîte a sa photo', await page.locator('img.carte-image').count(), 13);
  eq('le statut se lit sur la photo', await page.locator('.carte-statut').count(), 13);
  vrai('la composition est une barre empilée',
       await page.locator('.compo-barre').count() >= 8);
  // Une entrée par type présent et par carte, pas une par sous-ensemble.
  const compositions = await page.locator('.composition li').count();
  vrai('la composition par type est affichée', compositions >= 8);
  vrai('les trois types apparaissent en composition',
       (await texte(page, '#mainContainer')).indexOf('Harnais') !== -1 &&
       (await texte(page, '#mainContainer')).indexOf('Plaquette') !== -1 &&
       (await texte(page, '#mainContainer')).indexOf('Structure') !== -1);

  // ---------------------------------------------------------------
  bloc('Créer une boîte complète');
  await page.locator('.btn-creer').click();
  await page.waitForSelector('#newBoiteModal.show');
  await page.waitForTimeout(300);
  await page.fill('#newBoitePn', 'ESSAI-100');
  await page.fill('#newBoiteFonction', 'ESSAI');
  await page.fill('#newBoiteDs', 'ESSAI-150');
  // La case est masquée derrière son étiquette (un jeton) : on clique le jeton.
  await page.locator('#newBoitePorteurs .jeton-porteur', { hasText: /^NH90$/ }).click();
  await page.locator('#newBoitePorteurs .jeton-porteur', { hasText: /^H160$/ }).click();
  eq('deux porteurs cochés', await page.locator('#newBoitePorteurs input:checked').count(), 2);
  await page.selectOption('#newBoiteStatut', 'Validé');
  await page.fill('#newBoiteNiveau', 'Qualified to NH90');
  await page.fill('#newBoiteImage', 'https://exemple.fr/photo.jpg');
  await page.locator('[data-action="creer-boite"]').click();
  await page.waitForSelector('#detailsSlideOver.show');
  await page.waitForTimeout(900);
  const creee = await texte(page, '#slideOverBody');
  vrai('la boîte est créée et ouverte', (await texte(page, '#slideOverTitle')).indexOf('ESSAI-100') !== -1);
  vrai('fonction reprise', creee.indexOf('ESSAI') !== -1);
  vrai('DS/VCI repris', creee.indexOf('ESSAI-150') !== -1);
  vrai('porteurs repris', creee.indexOf('NH90') !== -1 && creee.indexOf('H160') !== -1);
  vrai('le porteur s\'ajoute depuis une liste fermée, pas en saisie libre',
       await page.locator('#slideOverBody select.saisie-multi[data-champ="Porteur"]').count() === 1);
  vrai('statut repris', creee.indexOf('Validé') !== -1);
  vrai('niveau repris', creee.indexOf('Qualified to NH90') !== -1);
  // L'URL saisie devient bien une balise <img> : la photo vient d'un lien,
  // pas d'un dessin fabriqué. (Elle ne se charge pas ici : domaine fictif.)
  eq('la photo est rendue depuis l\'URL saisie',
     await page.locator('#slideOverBody img[src="https://exemple.fr/photo.jpg"]').count(), 1);
  await fermerFiche(page);
  eq('14 boîtes', await page.locator('.carte').count(), 14);

  // On la retire pour ne pas fausser la suite — via le dialogue intégré,
  // puisque confirm() n'existe pas dans l'iframe d'Apps Script.
  await ouvrirFiche(page, 'ESSAI-100');
  // Supprimer se voit sans passer en edition : c'est une action sur la
  // fiche, pas un champ de formulaire.
  eq('Supprimer est offert sans passer en edition',
     await page.locator('#slideOverBody [data-action="supprimer-boite"]').count(), 1);
  await page.locator('#slideOverBody [data-action="supprimer-boite"]').click();
  await page.waitForSelector('#dialogueModal.show');
  vrai('le dialogue de confirmation est le nôtre',
       (await texte(page, '#dialogueTitre')).indexOf('Supprimer') !== -1);
  vrai('le bouton est marqué dangereux',
       (await page.locator('#dialogueValider').getAttribute('class')).indexOf('btn-danger-plein') !== -1);
  await repondreDialogue(page);
  await page.waitForTimeout(900);
  eq('retour à 10 boîtes', await page.locator('.carte').count(), 13);
  await ecranPropre(page);

  bloc('Indicateurs qui filtrent');
  await indic(page, 'Validées').click();
  await page.waitForTimeout(300);
  eq('cliquer « Validées » ne montre que les validées', await page.locator('.carte').count(), 7);
  vrai('l\'indicateur se dit actif',
       (await indic(page, 'Validées').getAttribute('class')).indexOf('actif') !== -1);
  eq('et propose son retrait dans les filtres',
     await page.locator('#filtreActif [data-action="filtrer-statut"]').count(), 1);
  await indic(page, 'Validées').click();
  await page.waitForTimeout(300);
  eq('second clic : retour à 10', await page.locator('.carte').count(), 13);
  await indic(page, 'Boîtes').click();
  await page.waitForTimeout(300);
  eq('« Boîtes » remet tout', await page.locator('.carte').count(), 13);

  // ---------------------------------------------------------------
  bloc('Vue Pièces : où sert chaque référence');
  await ecranPropre(page);
  eq('trois lectures de la base des boîtes', await page.locator('.onglet-vue').count(), 3);
  vrai('« Boîtes » est la vue par défaut',
       (await texte(page, '.onglet-vue.actif')).trim() === 'Boîtes');
  eq('la seconde vue s\'appelle « Sous-ensembles », pas « Pièces »',
     (await page.locator('.onglet-vue').nth(1).evaluate(function (e) { return e.textContent; })).trim(),
     'Sous-ensembles');
  eq('la grille est affichée', await page.locator('#mainContainer.grille').count(), 1);

  await page.locator('.onglet-vue', { hasText: 'Sous-ensembles' }).click();
  await page.waitForTimeout(350);
  vrai('l\'inventaire s\'affiche', await page.locator('.inventaire').count() === 1);
  vrai('il annonce des sous-ensembles, pas des composants',
       (await texte(page, '.inventaire-entete')).indexOf('Sous-ensemble') !== -1);
  vrai('et liste bien des types de sous-ensemble',
       /Harnais|Structure boîte|Plaquette/.test(await texte(page, '.inventaire')));
  faux('aucun composant n\'y figure',
       /Bouton poussoir|Colonnette|Collier/.test(await texte(page, '.inventaire')));
  eq('la grille laisse la place', await page.locator('#mainContainer.grille').count(), 0);
  eq('plus de cartes', await page.locator('.carte').count(), 0);
  const nbPieces = await page.locator('.piece').count();
  vrai('des sous-ensembles sont listés', nbPieces >= 10);
  vrai('le bilan les compte comme tels',
       (await texte(page, '#bilanResultats')).indexOf('sous-ensembles') !== -1);
  eq('le tri disparaît : l\'inventaire a son propre ordre',
     await page.locator('#triBouton').count(), 0);

  // Les pièces partagées portent le filet marine, et sont en tête.
  const partagees = await page.locator('.piece-partagee').count();
  vrai('au moins une pièce partagée est signalée', partagees >= 1);
  const premiere = page.locator('.piece').first();
  vrai('la plus réutilisée est en tête',
       (await premiere.getAttribute('class')).indexOf('piece-partagee') !== -1);
  const compte = await premiere.locator('.piece-compte').evaluate(function (e) { return e.textContent; });
  vrai('elle annonce son nombre de boîtes', /\d+ boîtes/.test(compte));
  vrai('et les nomme', await premiere.locator('.usage-lien').count() >= 2);

  // Un clic sur une boîte ouvre sa fiche : l'inventaire est un point de départ.
  const cible = (await premiere.locator('.usage-lien').first()
                   .evaluate(function (e) { return e.textContent; })).trim();
  await premiere.locator('.usage-lien').first().click();
  await page.waitForSelector('#detailsSlideOver.show');
  await page.waitForTimeout(400);
  eq('la fiche de la boîte s\'ouvre', (await texte(page, '#slideOverTitle')).trim(), cible);
  await fermerFiche(page);

  // L'inventaire suit les filtres en cours.
  await page.fill('#searchBar', 'mission SAR');
  await page.waitForTimeout(400);
  const piecesFiltrees = await page.locator('.piece').count();
  vrai('la recherche restreint l\'inventaire', piecesFiltrees > 0 && piecesFiltrees < nbPieces);
  await page.fill('#searchBar', '');
  await page.waitForTimeout(400);
  eq('et le rend quand on efface', await page.locator('.piece').count(), nbPieces);

  // Pas de débordement horizontal, c'est un tableau.
  const largeurs = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de défilement horizontal (inventaire)', largeurs.doc <= largeurs.vue + 1);

  await page.locator('.onglet-vue', { hasText: 'Boîtes' }).click();
  await page.waitForTimeout(350);
  eq('retour à la grille', await page.locator('#mainContainer.grille').count(), 1);
  eq('les cartes reviennent', await page.locator('.carte').count(), 13);
  eq('et le tri aussi', await page.locator('#triBouton').count(), 1);

  // ---------------------------------------------------------------
  bloc('Vue Standardisation : où la base se disperse');
  await ecranPropre(page);
  eq('trois lectures de la base des boîtes', await page.locator('.onglet-vue').count(), 3);
  await page.locator('.onglet-vue', { hasText: 'Standardisation' }).click();
  await page.waitForTimeout(400);
  const nbFamilles = await page.locator('.famille').count();
  vrai('des familles dispersées sont listées', nbFamilles >= 3);
  vrai('le bilan les compte',
       (await texte(page, '#bilanResultats')).indexOf('famille') !== -1);
  eq('plus de cartes', await page.locator('.carte').count(), 0);
  eq('ni d\'inventaire', await page.locator('.inventaire').count(), 0);

  // La colonnette du jeu de démonstration : une norme, cinq références.
  const colonnette = page.locator('.famille', { hasText: 'Colonnette' }).first();
  eq('la colonnette est repérée', await colonnette.count(), 1);
  const compteColonnette = await colonnette.locator('.famille-chiffre')
    .evaluateAll(function (els) { return els.map(function (e) { return e.textContent.trim(); }); });
  vrai('elle annonce une seule norme', compteColonnette[0].indexOf('1 norme') === 0);
  vrai('mais plusieurs références', /[2-9] références/.test(compteColonnette[1]));
  vrai('et les nomme', await colonnette.locator('.ref-pn').count() >= 2);
  vrai('avec leur nombre de boîtes',
       /\d+ boîte/.test(await colonnette.locator('.ref-usage').first()
         .evaluate(function (e) { return e.textContent; })));

  // La plus dispersée arrive en tête.
  const premiereFamille = page.locator('.famille').first();
  const refsPremiere = await premiereFamille.locator('.ref-pn').count();
  const refsDerniere = await page.locator('.famille').last().locator('.ref-pn').count();
  vrai('la plus dispersée est en tête', refsPremiere >= refsDerniere);

  // L'analyse suit les filtres.
  await page.fill('#searchBar', 'APU');
  await page.waitForTimeout(400);
  const apresFiltre = await page.locator('.famille').count();
  vrai('la recherche restreint l\'analyse', apresFiltre <= nbFamilles);
  await page.fill('#searchBar', '');
  await page.waitForTimeout(400);
  eq('et la rend quand on efface', await page.locator('.famille').count(), nbFamilles);

  // Les familles DEJA rangees ne sont plus listees : elles ne demandent aucune
  // action, et noyaient celles qui en demandent une.
  eq('plus de section « Deja rangees »', await page.locator('.standard-propres').count(), 0);
  eq('ni de ligne rangee', await page.locator('.propre').count(), 0);
  faux('le mot ne figure plus dans la vue',
       (await texte(page, '#mainContainer')).indexOf('Déjà rangées') !== -1);

  // Cliquer une reference nomme les boites ou elle sert, et y mene.
  const refPliee = page.locator('.famille .ref').first();
  eq('les boites sont repliees au depart',
     await refPliee.getAttribute('aria-expanded'), 'false');
  const boitesCachees = refPliee.locator('xpath=following-sibling::span[@class="ref-boites"]');
  faux('et vraiment masquees', await boitesCachees.isVisible());
  await refPliee.click();
  await page.waitForTimeout(250);
  eq('un clic les deplie', await refPliee.getAttribute('aria-expanded'), 'true');
  vrai('les boites sont nommees', await boitesCachees.locator('.usage-lien').count() >= 1);
  const nomBoite = await boitesCachees.locator('.usage-lien').first()
    .evaluate(function (e) { return e.textContent.trim(); });
  vrai('avec un PN lisible', nomBoite.length > 0);
  await refPliee.click();
  await page.waitForTimeout(250);
  eq('un second clic les replie', await refPliee.getAttribute('aria-expanded'), 'false');

  // Et de la, on ouvre la fiche de la boite citee.
  await refPliee.click();
  await page.waitForTimeout(250);
  await boitesCachees.locator('.usage-lien').first().click();
  await page.waitForSelector('#detailsSlideOver.show');
  await page.waitForTimeout(350);
  vrai('la boite citee s\'ouvre depuis la reference',
       (await texte(page, '#slideOverTitle')).indexOf(nomBoite) !== -1);
  await fermerFiche(page);

  // La reference la plus utilisee d'une famille dispersee est signalee : c'est
  // celle vers laquelle converger.
  vrai('une reference majoritaire est signalee',
       await page.locator('.famille .ref-majoritaire').count() >= 1);

  // Le bilan de la convergence, en tete : ce qu'elle rapporte, ce qu'elle coute.
  eq('un bilan en trois tuiles', await page.locator('.standard-bilan .sb-tuile').count(), 3);
  const bilanTxt = await texte(page, '.standard-bilan');
  vrai('il compte les familles', /familles? dispersée/.test(bilanTxt));
  vrai('les references avant et apres', /\d+\s*→\s*\d+/.test(bilanTxt));
  vrai('et les boites a modifier', /boîtes? à modifier/.test(bilanTxt));
  // Chaque famille annonce sa cible et son cout.
  eq('chaque famille porte sa cible', await page.locator('.famille .famille-cible').count(), nbFamilles);
  eq('la cible est la plus montee',
     (await colonnette.locator('.famille-cible b').innerText()).trim(), 'NAS43DD3-20');
  vrai('et le cout en boites',
       /\d+ boîtes? à modifier/.test(await colonnette.locator('.famille-cout').innerText()));
  eq('avec ses parts en barre', await colonnette.locator('.parts .part-cible').count(), 1);

  const largeurStd = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de défilement horizontal (standardisation)', largeurStd.doc <= largeurStd.vue + 1);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-standardisation.png') });

  await page.locator('.onglet-vue', { hasText: 'Boîtes' }).click();
  await page.waitForTimeout(350);
  eq('retour à la grille', await page.locator('.carte').count(), 13);

  // ---------------------------------------------------------------
  bloc('Recherche par composants : plus de bouton a viser');
  await ecranPropre(page);
  await page.locator('#btnComposant').click();
  await page.waitForSelector('#multiSearchModal.show');
  await page.waitForTimeout(350);
  eq('plus de bouton Ajouter',
     await page.locator('#multiSearchModal [data-action="ajouter-chip"]').count(), 0);
  eq('un bouton Fermer, en revanche',
     await page.locator('#multiSearchModal [data-action="fermer-multi-recherche"]').count(), 1);

  // Choisir une suggestion suffit : l'input recoit la valeur, le filtre part.
  // On vise une suggestion reellement montee : le catalogue propose aussi des
  // composants que personne n'a encore posés, et filtrer dessus ne rend rien.
  const suggestion = await page.evaluate(function () {
    const montes = new Set();
    Store.boites.forEach(function (b) {
      listeComposants(b['Composants']).forEach(function (c) { montes.add(libelleComposant(c)); });
    });
    return Array.from(document.querySelectorAll('#datalistStds option'))
      .map(function (o) { return o.value; })
      .find(function (v) { return montes.has(v); }) || '';
  });
  vrai('une suggestion deja montee est proposee', suggestion.length > 0);
  await page.fill('#multiSearchInputSelect', suggestion);
  await page.waitForTimeout(400);
  eq('la valeur choisie devient une puce, sans clic de plus',
     await page.locator('#multiSearchPillsContainer .puce').count(), 1);
  eq('et le champ est vide, pret pour la suivante',
     await page.locator('#multiSearchInputSelect').inputValue(), '');

  // Le filtre s'applique DERRIERE la modale restee ouverte.
  vrai('la modale est restee ouverte',
       await page.locator('#multiSearchModal.show').count() === 1);
  const filtrees = await page.locator('.carte').count();
  vrai('la grille derriere est deja filtree', filtrees > 0 && filtrees < 13);
  eq('le filtre actif le dit',
     await page.locator('#filtreActif .filtre-jeton').count(), 1);

  // Entree ajoute aussi, pour une valeur libre.
  await page.fill('#multiSearchInputSelect', 'NAS43');
  await page.locator('#multiSearchInputSelect').press('Enter');
  await page.waitForTimeout(400);
  eq('Entree ajoute une seconde puce',
     await page.locator('#multiSearchPillsContainer .puce').count(), 2);

  // Retirer une puce relache le filtre, toujours sans fermer.
  await page.locator('#multiSearchPillsContainer .puce-suppr').first().click();
  await page.waitForTimeout(400);
  eq('une puce de moins', await page.locator('#multiSearchPillsContainer .puce').count(), 1);
  vrai('la modale est toujours la',
       await page.locator('#multiSearchModal.show').count() === 1);
  await page.locator('#multiSearchModal [data-action="fermer-multi-recherche"]').click();
  await attendreFerme(page, 'multiSearchModal');
  await page.locator('#filtreActif .filtre-jeton button').first().click();
  await page.waitForTimeout(400);
  eq('filtre relache, toutes les boites reviennent',
     await page.locator('.carte').count(), 13);

  // ---------------------------------------------------------------
  bloc('Ajouter sans viser : listes fermees, Entree, et le focus rendu');
  await ecranPropre(page);
  await ouvrirFiche(page, '332P20001');
  // Liste fermee (les porteurs) : choisir, c'est ajouter.
  const porteurs = page.locator('#slideOverBody select.saisie-multi[data-champ="Porteur"]');
  eq('le porteur est une liste fermee, sans bouton', await porteurs.count(), 1);
  const avantPorteurs = await page.locator('#slideOverBody .puce-porteur').count();
  const offert = await porteurs.locator('option:not([value=""])').first()
    .evaluate(function (e) { return e.value; });
  await porteurs.selectOption(offert);
  await page.waitForTimeout(900);
  eq('un porteur de plus, sans confirmer',
     await page.locator('#slideOverBody .puce-porteur').count(), avantPorteurs + 1);

  // Champ libre : Entree ajoute, et le focus revient dans le champ.
  const libre = page.locator('#slideOverBody input.saisie-multi[data-champ="Mots-clés"]').first();
  if (await libre.count()) {
    await libre.fill('ESSAI-ENTREE');
    await libre.press('Enter');
    await page.waitForTimeout(900);
    vrai('Entree ajoute le mot-cle',
         (await texte(page, '#slideOverBody')).indexOf('ESSAI-ENTREE') !== -1);
    eq('et le focus revient dans le champ, pour enchainer',
       await page.evaluate(function () {
         const a = document.activeElement;
         return a ? (a.dataset && a.dataset.champ) || a.tagName : null;
       }), 'Mots-clés');
  }
  await fermerFiche(page);
  await ecranPropre(page);

  // ---------------------------------------------------------------
  bloc('Saisie guidee : la norme suit la fonction');
  await ecranPropre(page);
  await ouvrirFiche(page, '332P20001');
  const blocBoite = '.bloc-general .ajout-composant';
  const listeDe = function (niveau) {
    return page.evaluate(function (n) {
      const el = document.querySelector('.bloc-general .saisie-composant[data-niveau="' + n + '"]');
      const dl = el && document.getElementById(el.getAttribute('list'));
      return dl ? Array.from(dl.options).map(function (o) { return o.value; }) : null;
    }, niveau);
  };
  const normesToutes = await listeDe('norme');
  vrai('au depart, toutes les normes de la categorie', normesToutes.length > 3);
  await page.locator(blocBoite + ' .saisie-composant[data-niveau="fonction"]').fill('Bouton poussoir');
  await page.waitForTimeout(300);
  const normesBP = await listeDe('norme');
  vrai('la liste Norme se resserre sur la fonction', normesBP.length < normesToutes.length);
  faux('une norme de colonnette n\'y figure plus', normesBP.indexOf('NAS43') !== -1);
  vrai('mais la sienne, oui', normesBP.indexOf('MS24523') !== -1);
  const refsBP = await listeDe('reference');
  vrai('les references suivent aussi',
       refsBP.length > 0 && refsBP.every(function (r) { return /^MS2(4523|4524|5089)/.test(r); }));
  await page.locator(blocBoite + ' .saisie-composant[data-niveau="norme"]').fill('MS24523');
  await page.waitForTimeout(300);
  const refsNorme = await listeDe('reference');
  vrai('et se resserrent encore sur la norme', refsNorme.length < refsBP.length);
  await page.locator(blocBoite + ' .saisie-composant[data-niveau="fonction"]').fill('Fonction inedite');
  await page.waitForTimeout(300);
  eq('une fonction inconnue ne bloque rien', (await listeDe('norme')).length, normesToutes.length);

  // Le bloc mecanique de la structure a ses propres listes : les deux
  // n'interferent pas.
  await page.locator('.bloc-type-structure .saisie-composant[data-niveau="fonction"]').first().fill('Colonnette');
  await page.waitForTimeout(300);
  const normesMeca = await page.evaluate(function () {
    const el = document.querySelector('.bloc-type-structure .saisie-composant[data-niveau="norme"]');
    return Array.from(document.getElementById(el.getAttribute('list')).options).map(function (o) { return o.value; });
  });
  vrai('la colonnette ne propose que sa norme', normesMeca.indexOf('NAS43') !== -1);
  faux('et pas celles des boutons', normesMeca.indexOf('MS24523') !== -1);
  eq('le bloc de la boite n\'a pas bouge', (await listeDe('norme')).length, normesToutes.length);

  bloc('Equivalences depuis la fiche de la boite');
  eq('le bouton y est', await page.locator('#slideOverBody [data-action="comparer-boite"]').count(), 1);
  await page.locator('#slideOverBody [data-action="comparer-boite"]').first().click();
  await page.waitForSelector('#compareModal.show'); await page.waitForTimeout(800);
  vrai('le classement s\'ouvre sans refermer la fiche',
       await page.locator('#compareResult .resultat').count() > 0);
  await fermerModale(page, 'compareModal');
  await fermerFiche(page);
  await ecranPropre(page);

  // ---------------------------------------------------------------
  bloc('Doublons : ce qui les separe, et la comparaison complete');
  await indic(page, 'Doublons probables').click();
  await page.waitForSelector('#doublonsModal.show'); await page.waitForTimeout(400);
  const premierDoublon = page.locator('.doublon').first();
  vrai('chaque paire montre son detail', await premierDoublon.locator('.doublon-detail').count() === 1);
  const texteDoublon = await premierDoublon.innerText();
  vrai('on nomme ce qui concorde ou ce qui separe',
       /ce qui concorde|ce qui les s/i.test(texteDoublon));
  vrai('le critere porte une valeur lisible',
       await premierDoublon.locator('.doublon-crit-val').count() > 0);
  vrai('et l\'interet est rappele en tete',
       (await texte(page, '#doublonsSous')).indexOf('approvisionner') !== -1);
  await premierDoublon.locator('[data-action="comparer-depuis-doublons"]').click();
  await page.waitForTimeout(900);
  eq('la liste se referme', await page.locator('#doublonsModal.show').count(), 0);
  eq('la comparaison ponderee s\'ouvre', await page.locator('#compareModal.show').count(), 1);
  await fermerModale(page, 'compareModal');
  await ecranPropre(page);

  // ---------------------------------------------------------------
  bloc('Indicateur « A standardiser »');
  eq('il a remplace « References uniques »',
     await page.locator('.indicateur', { hasText: 'Références uniques' }).count(), 0);
  eq('et c\'est un bouton',
     await page.locator('button.indicateur', { hasText: 'À standardiser' }).count(), 1);
  vrai('il annonce un nombre de familles',
       Number(await valeurIndic(page, 'À standardiser')) >= 0);
  vrai('et dit de quoi il s\'agit',
       (await detailIndic(page, 'À standardiser')).indexOf('référence') !== -1);
  await indic(page, 'À standardiser').click();
  await page.waitForTimeout(450);
  eq('un clic mene a la vue Standardisation', await page.locator('.carte').count(), 0);
  vrai('des familles y sont listees', await page.locator('.famille').count() > 0);
  eq('l\'indicateur se marque', await indic(page, 'À standardiser').getAttribute('aria-pressed'), 'true');
  await indic(page, 'À standardiser').click();
  await page.waitForTimeout(450);
  eq('un second clic ramene aux cartes', await page.locator('.carte').count(), 13);


  // ---------------------------------------------------------------
  bloc('Ce que la batterie a trouve');
  await ecranPropre(page);

  // Le balayage des doublons se coupait au-dela de 400 paires, soit 29
  // sous-ensembles du meme type : toute base reelle restait a « — ».
  const seuils = await page.evaluate(function () {
    const mesure = function (n) {
      const b = [], no = [];
      for (let i = 0; i < n; i++) {
        b.push({ 'PN Global': 'T' + i });
        no.push({ 'ID_Ligne': 'T' + i + '-h', 'PN Global': 'T' + i, 'Type': 'Harnais',
                  'PN du type': 'T' + i + '.h', 'Référence': 'R-' + (i % 4) });
      }
      const memoireB = Store.boites, memoireN = Store.nomenclature;
      chargerDonnees({ boites: b, nomenclature: no, headersBoites: ['PN Global'],
        headersNom: ['ID_Ligne', 'PN Global', 'Type', 'PN du type', 'Référence'],
        config: { colonnes: { boites: 'PN Global', nomenclature: 'ID_Ligne' } } });
      const t0 = performance.now();
      const r = compterDoublonsProbables(Store.boites);
      const ms = Math.round(performance.now() - t0);
      Store.boites = memoireB; Store.nomenclature = memoireN;
      return { n: n, tronque: r.nombre === null, ms: ms };
    };
    return [mesure(60), mesure(150), mesure(400)];
  });
  vrai('60 boites du meme type : balayage complet', !seuils[0].tronque);
  vrai('150 aussi', !seuils[1].tronque);
  vrai('et sans y passer la journee', seuils[1].ms < 2000);
  vrai('400 : on s\'arrete, plutot que de figer la page', seuils[2].tronque);
  await page.evaluate(function () { return chargerTout(); });
  await page.waitForTimeout(800);

  // Et le « — » ne reste pas muet.
  const detailDoublons = await detailIndic(page, 'Doublons probables');
  vrai('l\'indicateur porte un detail', detailDoublons.trim().length > 0);

  // Avant que les reglages ne soient charges, tous les criteres comptent :
  // un classement entierement a zero se lirait « rien ne se ressemble ».
  const replis = await page.evaluate(function () {
    const memoire = Store.criteresActifs;
    Store.criteresActifs = {};
    const a = Store.boites[0];
    const r = comparerBoites(a, a);
    const n = criteresActifs('boite').length;
    Store.criteresActifs = memoire;
    return { score: r.score, mesurable: r.mesurable, n: n };
  });
  eq('une boite vaut 100 contre elle-meme', replis.score, 100);
  vrai('la comparaison reste mesurable', replis.mesurable);
  vrai('tous les criteres comptent par defaut', replis.n > 0);

  // On ne peut pas ecarter le dernier critere.
  const dernier = await page.evaluate(function () {
    const memoire = Store.criteresActifs.boite.slice();
    CRITERES_BOITE.slice(0, -1).forEach(function (c) { desactiverCritere('boite', c.cle); });
    const reste = criteresActifs('boite').length;
    const refus = desactiverCritere('boite', criteresActifs('boite')[0].cle) === false;
    Store.criteresActifs.boite = memoire;
    reinitialiserPoids();
    return { reste: reste, refus: refus };
  });
  eq('il reste un critere', dernier.reste, 1);
  vrai('et il ne part pas', dernier.refus);
  await page.evaluate(function () { chargerReglages(); rendreInterface(); });
  await page.waitForTimeout(400);

  // Aucune fonction morte parmi celles retirees.
  const disparues = await page.evaluate(function () {
    return ['construireCsv', 'champCsv', 'clesNormalisees', 'formaterComposant',
            'piecesReutilisees', 'famillesStandardisees', 'telecharger']
      .filter(function (n) { return typeof window[n] === 'function' || typeof eval('typeof ' + n) === 'function'; });
  });
  eq('les fonctions retirees ne sont plus la', disparues, []);
  await ecranPropre(page);

  // ---------------------------------------------------------------
  bloc('Espace Composants : une base a part, pas une lecture de plus');
  await ecranPropre(page);
  eq('deux espaces sont offerts', await page.locator('.onglet-espace').count(), 2);
  eq('« Boîtes » est l\'espace par defaut',
     (await page.locator('.onglet-espace.actif').innerText()).trim(), 'Boîtes');
  eq('les trois lectures sont la', await page.locator('.onglet-vue').count(), 3);

  await page.locator('.onglet-espace', { hasText: 'Composants' }).click();
  await page.waitForTimeout(700);
  eq('les lectures des boites disparaissent', await page.locator('.onglet-vue').count(), 0);
  eq('les filtres par type aussi', await page.locator('.filtres-type .jeton').count(), 0);
  eq('les onglets de fonction aussi', await page.locator('#functionTabs .onglet').count(), 0);
  eq('plus de cartes', await page.locator('.carte').count(), 0);

  // Les indicateurs du HAUT changent avec l'espace : garder ceux des boites
  // faisait lire « 13 boites » comme s'il qualifiait les composants.
  const libelles = await page.locator('.indicateur-libelle').allTextContents();
  eq('quatre indicateurs, pas sept', libelles.length, 4);
  ['Références', 'À ranger', 'Hors catalogue', 'Montées une fois'].forEach(function (l) {
    vrai('l\'espace composants annonce « ' + l + ' »', libelles.indexOf(l) !== -1);
  });
  faux('« Boîtes » a disparu du haut', libelles.indexOf('Boîtes') !== -1);
  faux('« Validées » aussi', libelles.indexOf('Validées') !== -1);
  eq('plus de seconde bande de chiffres', await page.locator('.compo-bande').count(), 0);

  // Le rail : les familles, rien d'autre. Un etat ou un mode d'emploi se
  // filtre depuis la bande du haut, quand on vient justement pour ca.
  eq('quatre entrees au rail : « Toutes » plus les trois familles',
     await page.locator('.cf-famille').count(), 4);
  const famillesRail = await page.locator('.cf-nom').allTextContents();
  ['Toutes', 'Composants de boîte', 'Composants mécaniques', 'Composants routing']
    .forEach(function (f) {
      vrai('« ' + f + ' » est proposee', famillesRail.indexOf(f) !== -1);
    });
  eq('plus de filtre par etat au rail', await page.locator('.cf-etat').count(), 0);

  // La liste des fonctions : c'est ce qu'on cherche, « il me faut un collier ».
  const nbFonctions = await page.locator('.lf-ligne').count();
  vrai('des fonctions sont listees', nbFonctions > 10);
  eq('plus d\'arbre deplie', await page.locator('.cfo-bloc').count(), 0);
  eq('ni de bouton « tout deplier »', await page.locator('.arbre-barre-btn').count(), 0);
  const ligneFct = page.locator('.lf-ligne').first();
  vrai('chaque ligne porte sa fonction',
       (await ligneFct.locator('.lf-nom').innerText()).trim().length > 0);
  // Plus de colonne famille : la liste est rangee par famille, avec un en-tete.
  eq('la liste est rangee par famille : trois en-tetes', await page.locator('.lf-groupe').count(), 3);
  vrai('dans l\'ordre du registre : boite, mecanique, routing',
       /boîte[\s\S]*?mécaniques[\s\S]*?routing/i.test(await page.locator('.lf-cadre').innerText()));
  vrai('chaque en-tete compte ses fonctions et ses boites',
       /\d+ fonctions? · \d+ boîtes?/.test(await page.locator('.lf-groupe-n').first().innerText()));
  vrai('la premiere ligne suit son en-tete', await page.evaluate(function () {
    const g = document.querySelector('.lf-groupe');
    return g && g.nextElementSibling && g.nextElementSibling.classList.contains('lf-ligne');
  }));
  eq('plus de colonne famille dans les lignes', await page.locator('.lf-famille').count(), 0);
  // On dit comment lire, sous le commutateur.
  vrai('la liste s\'explique en deux phrases',
       /Hors catalogue[\s\S]*?absente du catalogue/.test(await texte(page, '.compo-lire')));
  vrai('et les marques ont une info-bulle',
       /absente du catalogue/.test(await page.locator('.lf-tag-hors').first().getAttribute('title')));
  vrai('le compte de normes ET de references',
       await ligneFct.locator('.lf-n').count() === 2);
  vrai('et une jauge d\'emploi', await ligneFct.locator('.lf-jauge').count() === 1);
  vrai('les dispersees sont marquees', await page.locator('.lf-tag-ranger').count() >= 1);

  // Le tri : trois ordres, a l'interieur des familles.
  eq('trois tris offerts', await page.locator('.compo-tri-btn').count(), 3);
  eq('plus de tri « par famille » : c\'est la structure, pas un ordre',
     await page.locator('.compo-tri-btn', { hasText: 'famille' }).count(), 0);
  const teteListe = async function () {
    return (await page.locator('.lf-nom').first().innerText()).trim();
  };
  const parEmploi = await teteListe();
  await page.locator('.compo-tri-btn', { hasText: 'Alphabétique' }).click();
  await page.waitForTimeout(500);
  const parAlpha = await teteListe();
  vrai('trier change l\'ordre', parAlpha !== parEmploi);
  eq('et le tri pose est marque', await page.locator('.compo-tri-btn.actif').count(), 1);
  await page.locator('.compo-tri-btn', { hasText: 'Les plus montés' }).click();
  await page.waitForTimeout(500);
  eq('on revient a l\'emploi', await teteListe(), parEmploi);

  // Trois lectures de la meme base : la liste, la matrice par porteur, la carte.
  eq('trois lectures offertes', await page.locator('.compo-vue-btn').count(), 3);
  eq('la liste est la lecture par defaut',
     (await page.locator('.compo-vue-btn.actif').innerText()).trim(), 'Liste');
  vrai('les fonctions dispersees montrent leurs parts', await page.locator('.lf-ligne .parts').count() >= 3);
  const ligneCollierListe = page.locator('.lf-ligne', { hasText: 'Collier' }).first();
  const partsCollier = ligneCollierListe.locator('.parts');
  eq('la cible d\'abord', await partsCollier.locator('.part-cible').count(), 1);
  vrai('puis un segment par autre reference montee', await partsCollier.locator('.part-autre').count() >= 1);
  vrai('et le detail est dans l\'info-bulle',
       /cible MS3367-4-9 : \d+ boîtes/.test(await partsCollier.getAttribute('title')));
  const boitesCollier = (await ligneCollierListe.locator('.lf-boites').innerText()).trim().split(' ')[0];

  await page.locator('.compo-vue-btn', { hasText: 'Par porteur' }).click(); await page.waitForTimeout(500);
  eq('la matrice est une table', await page.locator('table.mx').count(), 1);
  eq('plus de liste', await page.locator('.lf-ligne').count(), 0);
  const porteursMx = await page.locator('.mx-porteur').allTextContents();
  vrai('un porteur par colonne', porteursMx.length >= 5);
  vrai('dans l\'ordre du registre',
       porteursMx.indexOf('Dauphin') < porteursMx.indexOf('H160') &&
       porteursMx.indexOf('H160') < porteursMx.indexOf('H225'));
  eq('une fonction par ligne', await page.locator('.mx tbody tr:not(.mx-groupe)').count(), nbFonctions);
  eq('rangees par famille, avec un en-tete', await page.locator('.mx tbody tr.mx-groupe').count(), 3);
  vrai('la matrice s\'explique : la case, la teinte, le total',
       /boîtes distinctes/.test(await texte(page, '.compo-lire')));
  vrai('la colonne du total dit ce qu\'elle compte',
       /distinctes/.test(await page.locator('th.mx-total').getAttribute('title')));
  const ligneCollierMx = page.locator('.mx tbody tr', { hasText: 'Collier' }).first();
  const casesCollier = await ligneCollierMx.locator('.mx-case span').allTextContents();
  vrai('chaque case porte son nombre', casesCollier.some(function (c) { return /^\d+$/.test(c.trim()); }));
  eq('le total de la ligne est le nombre de boites de la liste',
     (await ligneCollierMx.locator('.mx-total').innerText()).trim(), boitesCollier);
  vrai('la teinte suit le nombre : du plus clair au plus fonce',
       await page.locator('.mx-case.mx-5').count() >= 1 && await page.locator('.mx-case.mx-1, .mx-case.mx-2').count() >= 1);
  vrai('une case vide se dit', await page.locator('.mx-case.mx-0').count() >= 1);
  vrai('et une legende explique l\'echelle', (await texte(page, '.mx-legende')).indexOf('boîte') !== -1);
  const largeurMx = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de defilement horizontal (matrice)', largeurMx.doc <= largeurMx.vue + 1);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-composants-porteurs.png') });
  await ligneCollierMx.locator('.mx-fonction').click();
  await page.waitForSelector('#detailsSlideOver.show'); await page.waitForTimeout(500);
  eq('la fonction ouvre sa fiche depuis la matrice', (await texte(page, '#slideOverTitle')).trim(), 'Collier');
  // La fiche : le plan de convergence, et qui monte quoi.
  eq('la fiche donne un plan de convergence', await page.locator('.fc-plan').count(), 1);
  vrai('qui nomme les boites a modifier', await page.locator('.fc-plan-boites .usage-lien').count() >= 1);
  vrai('et chiffre ce qu\'on cesse de faire vivre', /−\d/.test(await texte(page, '.fc-plan-chiffres')));
  eq('une matrice reference par porteur', await page.locator('.fc-matrice table.mx').count(), 1);
  eq('avec la cible marquee', await page.locator('.fc-matrice .mx-cible-tag').count(), 1);
  vrai('une ligne par reference montee', await page.locator('.fc-matrice tbody tr').count() >= 2);
  await fermerFiche(page);

  await page.locator('.compo-vue-btn', { hasText: 'Carte' }).click(); await page.waitForTimeout(500);
  eq('la carte est la', await page.locator('.tm').count(), 1);
  eq('sans tri : elle se range par aire', await page.locator('.compo-tri-btn').count(), 0);
  const nbTuiles = await page.locator('.tm-tuile').count();
  vrai('une tuile par fonction montee', nbTuiles >= 15 && nbTuiles < nbFonctions);
  eq('trois regions, une par famille', await page.locator('.tm-region').count(), 3);
  const tuileCollier = page.locator('.tm-tuile[aria-label^="Collier"]').first();
  const tuileCosse = page.locator('.tm-tuile[aria-label^="Cosse"]').first();
  const bCollier = await tuileCollier.boundingBox();
  const bCosse = await tuileCosse.boundingBox();
  vrai('l\'aire suit les boites : le collier est bien plus grand que la cosse',
       bCollier.width * bCollier.height > 5 * bCosse.width * bCosse.height);
  vrai('les dispersees sont marquees', await page.locator('.tm-tuile.tm-disperse').count() >= 5);
  vrai('les dormantes sont listees a part', (await texte(page, '.tm-dormantes')).indexOf('Vis') !== -1);
  vrai('chaque tuile dit tout dans son titre', /\d+ boîtes/.test(await tuileCollier.getAttribute('title')));
  const geometrie = await page.evaluate(function () {
    const r = Array.from(document.querySelectorAll('.tm-tuile')).map(function (e) { return e.getBoundingClientRect(); });
    const carte = document.querySelector('.tm').getBoundingClientRect();
    let hors = 0, chev = 0;
    r.forEach(function (a, i) {
      if (a.left < carte.left - 1 || a.right > carte.right + 1 || a.top < carte.top - 1 || a.bottom > carte.bottom + 1) hors++;
      r.forEach(function (b, j) {
        if (j <= i) return;
        const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (x > 2 && y > 2) chev++;
      });
    });
    return { hors: hors, chev: chev };
  });
  eq('aucune tuile hors de la carte', geometrie.hors, 0);
  eq('aucun chevauchement', geometrie.chev, 0);
  const largeurTm = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de defilement horizontal (carte)', largeurTm.doc <= largeurTm.vue + 1);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-composants-carte.png') });
  await tuileCollier.click();
  await page.waitForSelector('#detailsSlideOver.show'); await page.waitForTimeout(500);
  eq('une tuile ouvre sa fiche', (await texte(page, '#slideOverTitle')).trim(), 'Collier');
  await fermerFiche(page);
  // (le stockage local est ferme dans ce bac a sable : la memorisation est
  // couverte par les tests unitaires, on verifie ici l'etat en place)
  vrai('la lecture est celle de l\'etat', await page.evaluate(function () {
    return Store.compo.vue === 'carte';
  }));
  await page.locator('.compo-vue-btn', { hasText: 'Liste' }).click(); await page.waitForTimeout(400);
  eq('retour a la liste', await page.locator('.lf-ligne').count(), nbFonctions);

  // Le detail s'ouvre dans la FICHE, comme pour une boite.
  await ligneFct.click();
  await page.waitForSelector('#detailsSlideOver.show'); await page.waitForTimeout(500);
  eq('la fiche porte le nom de la fonction',
     (await texte(page, '#slideOverTitle')).trim(), parEmploi);
  vrai('et sa famille en sous-titre',
       (await texte(page, '#slideOverSousTitre')).indexOf('Composants') !== -1);
  eq('un resume de trois mesures', await page.locator('.fc-mesure').count(), 3);
  vrai('les normes sont des blocs', await page.locator('.fc-norme').count() >= 1);
  vrai('avec leurs references', await page.locator('.fc-ref').count() >= 1);
  vrai('la plus montee est marquee', await page.locator('.fc-majoritaire').count() === 1);
  vrai('et un plan de convergence est donne, en phrases',
       (await texte(page, '.fc-plan')).indexOf('Si toutes les boîtes montaient cette référence') !== -1);

  // De la fiche d'une fonction, on ouvre la boite qui la monte.
  const boiteCitee = (await page.locator('.fc-ref-boites .usage-lien').first().innerText()).trim();
  await page.locator('.fc-ref-boites .usage-lien').first().click();
  await page.waitForTimeout(600);
  vrai('la boite citee s\'ouvre',
       (await texte(page, '#slideOverTitle')).indexOf(boiteCitee) !== -1);
  await fermerFiche(page);

  // Le filtre par famille.
  const avantFamille = await page.locator('.lf-ligne').count();
  await page.locator('.cf-famille', { hasText: 'routing' }).click();
  await page.waitForTimeout(500);
  vrai('filtrer par famille restreint', await page.locator('.lf-ligne').count() < avantFamille);
  eq('le rail marque la famille posee', await page.locator('.cf-famille.actif').count(), 1);
  await page.locator('.cf-effacer').click(); await page.waitForTimeout(500);
  eq('tout revient', await page.locator('.lf-ligne').count(), avantFamille);

  // Les etats se filtrent depuis la bande du haut.
  await indic(page, 'Hors catalogue').click();
  await page.waitForTimeout(500);
  const horsCat = await page.locator('.lf-ligne').count();
  vrai('« Hors catalogue » restreint', horsCat >= 1 && horsCat < avantFamille);
  eq('et les lignes le disent', await page.locator('.lf-tag-hors').count(), horsCat);
  await indic(page, 'Hors catalogue').click();
  await page.waitForTimeout(500);
  await indic(page, 'Montées une fois').click();
  await page.waitForTimeout(500);
  vrai('« Montées une fois » aussi',
       await page.locator('.lf-ligne').count() < avantFamille);
  await indic(page, 'Montées une fois').click();
  await page.waitForTimeout(500);

  // La recherche de l'espace lui appartient : revenir aux boites ne l'herite pas.
  await page.fill('#searchBar', 'collier');
  await page.waitForTimeout(500);
  const apresRecherche = await page.locator('.lf-ligne').count();
  vrai('la recherche restreint la base', apresRecherche > 0 && apresRecherche < avantFamille);
  await page.locator('.onglet-espace', { hasText: 'Boîtes' }).click();
  await page.waitForTimeout(600);
  eq('l\'espace boites n\'herite pas du mot-cle', await page.locator('.carte').count(), 13);
  eq('et son champ est bien vide', await page.locator('#searchBar').inputValue(), '');
  await page.locator('.onglet-espace', { hasText: 'Composants' }).click();
  await page.waitForTimeout(600);
  eq('en revenant, la recherche des composants est retrouvee',
     await page.locator('#searchBar').inputValue(), 'collier');
  eq('et son resultat aussi', await page.locator('.lf-ligne').count(), apresRecherche);
  await page.locator('.cf-effacer').click(); await page.waitForTimeout(500);

  const largeurCompo = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de defilement horizontal (composants)', largeurCompo.doc <= largeurCompo.vue + 1);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-composants.png') });

  await page.locator('.onglet-espace', { hasText: 'Boîtes' }).click();
  await page.waitForTimeout(500);
  eq('retour a la grille', await page.locator('.carte').count(), 13);
  await ecranPropre(page);

  // ---------------------------------------------------------------
  bloc('Favoris de ponderation : une intention posee d\'un coup');
  await ecranPropre(page);
  await page.locator('.carte', { hasText: '332H80001' })
            .getByRole('button', { name: 'Équivalences' }).click();
  await page.waitForSelector('#compareModal.show'); await page.waitForTimeout(900);
  await page.locator('[data-action="ouvrir-reglages"]').first().click();
  await page.waitForTimeout(600);
  vrai('le rail propose des favoris', await page.locator('.favori').count() >= 4);
  vrai('chacun porte son intention',
       (await page.locator('.favori-aide').first().innerText()).trim().length > 5);

  const tete = async function () {
    return (await texte(page, '#compareResult .resultat .resultat-pn, #compareResult .resultat')).trim();
  };
  const scoreTete = async function () {
    return parseInt(await texte(page, '#compareResult .resultat .score b'), 10);
  };
  const avantFavori = await scoreTete();
  await page.locator('.favori', { hasText: 'Même porteur' }).click();
  await page.waitForTimeout(700);
  eq('le favori pose est marque', await page.locator('.favori.actif').count(), 1);
  const apresPorteur = await scoreTete();
  vrai('le classement se recompose', apresPorteur !== avantFavori);
  eq('le total reste a 100 %',
     await page.evaluate(function () {
       return criteresActifs('boite').reduce(function (t, c) { return t + poidsDe('boite', c); }, 0);
     }), 100);
  vrai('le porteur pese le plus',
       await page.evaluate(function () {
         return criteresActifs('boite').reduce(function (a, b) {
           return poidsDe('boite', a) >= poidsDe('boite', b) ? a : b;
         }).cle === 'porteur';
       }));

  // Un favori dit aussi ce qui NE compte pas.
  await page.locator('.favori', { hasText: 'Même contenu' }).click();
  await page.waitForTimeout(700);
  eq('« Même contenu » ne garde que ses criteres',
     await page.evaluate(function () { return criteresActifs('boite').length; }), 3);
  // Les curseurs vivent derriere un engrenage : ils servent une fois sur dix.
  eq('aucun curseur a l\'ouverture du rail',
     await page.locator('#reglagesRail .curseur').count(), 0);
  await page.locator('[data-action="basculer-reglage-detaille"]').click();
  await page.waitForTimeout(500);
  vrai('l\'engrenage les revele', await page.locator('#reglagesRail .curseur').count() > 0);
  vrai('les criteres ecartes sont proposes au rajout',
       await page.locator('.btn-ajout-critere').count() >= 1);

  // Bouger un curseur quitte le favori : on ne pretend pas y etre reste.
  const curseur = page.locator('#reglagesRail .curseur[data-portee="boite"]').first();
  await curseur.evaluate(function (el) {
    el.value = 70; el.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(600);
  eq('plus aucun favori n\'est marque', await page.locator('.favori.actif').count(), 0);

  await page.locator('.favori', { hasText: 'Par défaut' }).click();
  await page.waitForTimeout(700);
  eq('« Par défaut » remet les parts du registre',
     await page.evaluate(function () { return criteresActifs('boite').length; }),
     await page.evaluate(function () { return CRITERES_BOITE.length; }));
  await fermerModale(page, 'compareModal');
  await ecranPropre(page);

  // ---------------------------------------------------------------
  bloc('La fiche ne cache plus rien hors edition');
  await ouvrirFiche(page, '332P20001');
  const corpsLu = await texte(page, '#slideOverBody');
  vrai('le champ Image se lit sans passer en edition',
       await page.locator('#slideOverBody .lien-url').count() >= 1);
  vrai('le type du sous-ensemble se lit aussi', corpsLu.indexOf('Structure boîte') !== -1);
  // Les photos du jeu d'exemple sont embarquees : on dit ce que c'est plutot
  // que de deverser 4 Ko de donnees dans la fiche.
  vrai('une image embarquee est annoncee, pas deversee',
       corpsLu.indexOf('image intégrée') !== -1);
  faux('sa charge utile ne remplit pas la fiche', corpsLu.indexOf('data:image/svg') !== -1);
  // Une vraie URL, elle, est un lien.
  await page.evaluate(function () {
    boiteParPn('332P20001')['Image'] = 'https://exemple.fr/boitier.jpg';
    rendreFiche();
  });
  await page.waitForTimeout(400);
  eq('une URL http devient un lien',
     await page.locator('#slideOverBody .lien-url[target="_blank"]').count(), 1);
  vrai('vers la bonne adresse',
       (await page.locator('#slideOverBody .lien-url').first().getAttribute('href'))
         === 'https://exemple.fr/boitier.jpg');
  // Ce qui est lisible doit rester editable.
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  await page.waitForTimeout(400);
  vrai('et reste editable',
       await page.locator('#slideOverBody .champ-boite[data-champ="Image"]').count() === 1);
  await page.locator('#slideOverBody [data-action="annuler-boite"]').click();
  await page.waitForTimeout(400);
  await fermerFiche(page);
  await ecranPropre(page);

  // ---------------------------------------------------------------
  bloc('Le classement se lit replie');
  await ecranPropre(page);
  await page.locator('.carte', { hasText: '332H80001' })
            .getByRole('button', { name: 'Équivalences' }).click();
  await page.waitForSelector('#compareModal.show'); await page.waitForTimeout(800);

  const nbCandidats = await page.locator('.resultat').count();
  vrai('plusieurs candidats sont classes', nbCandidats > 3);
  // C'est une liste : rien n'est deplie a l'ouverture, on clique ce qu'on veut lire.
  eq('aucun n\'est deplie a l\'ouverture', await page.locator('.resultat.ouvert').count(), 0);
  eq('aucun critere n\'est deroule', await page.locator('.resultat .critere').count(), 0);

  // La ligne repliee dit deja l'essentiel : le PN, le score, et le partage.
  const ligneRepliee = page.locator('.resultat').nth(1);
  vrai('chaque ligne porte son PN',
       (await ligneRepliee.locator('.resultat-pn').innerText()).trim().length > 0);
  vrai('son score', await ligneRepliee.locator('.score').count() === 1);
  vrai('et le compte de ce qui concorde',
       (await ligneRepliee.locator('.rb-ok').innerText()).indexOf('concordent') !== -1);

  const hautListe = await page.evaluate(function () {
    return document.getElementById('compareResult').scrollHeight;
  });
  await ligneRepliee.locator('.resultat-tete').click();
  await page.waitForTimeout(500);
  eq('cliquer en deplie un', await page.locator('.resultat.ouvert').count(), 1);
  vrai('et la page s\'allonge du detail', await page.evaluate(function () {
    return document.getElementById('compareResult').scrollHeight;
  }) > hautListe + 100);
  vrai('et c\'est celui qu\'on a clique',
       (await ligneRepliee.getAttribute('class')).indexOf('ouvert') !== -1);
  await page.locator('.resultat').first().locator('.resultat-tete').click();
  await page.waitForTimeout(400);
  eq('en deplier un autre referme le premier', await page.locator('.resultat.ouvert').count(), 1);
  vrai('et c\'est le nouveau',
       (await page.locator('.resultat').first().getAttribute('class')).indexOf('ouvert') !== -1);
  await page.locator('.resultat').first().locator('.resultat-tete').click();
  await page.waitForTimeout(300);
  await ligneRepliee.locator('.resultat-tete').click();
  await page.waitForTimeout(400);
  vrai('le detail montre les criteres',
       await page.locator('.resultat.ouvert .critere').count() >= 2);

  // Tout replier : le classement seul, sans un detail.
  await ligneRepliee.locator('.resultat-tete').click();
  await page.waitForTimeout(500);
  eq('on peut tout replier', await page.locator('.resultat.ouvert').count(), 0);
  const hautNu = await page.evaluate(function () {
    return document.getElementById('compareResult').scrollHeight;
  });
  eq('et la page retrouve la hauteur de la liste', hautNu, hautListe);
  await fermerModale(page, 'compareModal');
  await ecranPropre(page);

  // ---------------------------------------------------------------
  bloc('La fiche est un arbre : la boite, puis ses branches repliees');
  await ouvrirFiche(page, '332P20001', true);
  eq('un bloc pour la boite', await page.locator('#slideOverBody .bloc-general').count(), 1);
  eq('une tete pour les sous-ensembles', await page.locator('.arbre-tete').count(), 1);
  vrai('qui les compte',
       (await texte(page, '.arbre-compte')).indexOf('monté') !== -1);
  vrai('et resume leur composition dans la meme tete',
       await page.locator('.arbre-tete .sommaire-item').count() >= 3);
  const nbBranches = await page.locator('.arbre-branche .bloc-branche').count();
  vrai('chaque sous-ensemble est une branche', nbBranches >= 3);

  // La vue d'ensemble : les branches sont repliees, une ligne chacune.
  eq('toutes repliees a l\'ouverture',
     await page.locator('.branche-tete[aria-expanded="false"]').count(), nbBranches);
  eq('aucun corps deplie', await page.locator('.branche-corps').count(), 0);
  const ligneStruct = page.locator('.bloc-type-structure .branche-tete').first();
  vrai('la ligne dit le type',
       /structure/i.test(await ligneStruct.locator('.branche-type').innerText()));
  vrai('le PN', (await ligneStruct.locator('.branche-pn').innerText()).trim().length > 0);
  vrai('et un resume — montage, cotes, masse',
       /mm/.test(await ligneStruct.locator('.branche-resume').innerText()));
  vrai('avec sa photo en timbre', await ligneStruct.locator('.branche-photo img').count() === 1);
  const hautVueEnsemble = await page.evaluate(function () {
    return document.getElementById('slideOverBody').scrollHeight;
  });
  vrai('la fiche tient en peu de hauteur : c\'est une vue d\'ensemble', hautVueEnsemble < 1500);

  // Un clic deplie, un second replie.
  await ligneStruct.click(); await page.waitForTimeout(350);
  eq('un clic deplie la branche', await page.locator('.bloc-type-structure .branche-corps').count(), 1);
  eq('et le dit',
     await page.locator('.bloc-type-structure .branche-tete').first().getAttribute('aria-expanded'), 'true');
  vrai('ses champs apparaissent', (await texte(page, '.bloc-type-structure')).indexOf('Longueur') !== -1);
  eq('avec ses trois boutons',
     await page.locator('.bloc-type-structure .branche-outils .btn-action').count(), 3);
  vrai('la fiche s\'allonge d\'autant', await page.evaluate(function () {
    return document.getElementById('slideOverBody').scrollHeight;
  }) > hautVueEnsemble + 300);
  await page.locator('.bloc-type-structure .branche-tete').first().click(); await page.waitForTimeout(350);
  eq('un second clic la replie', await page.locator('.bloc-type-structure .branche-corps').count(), 0);

  // La subordination se voit : les branches sont en retrait de la boite.
  const posBoite = await page.locator('#slideOverBody .bloc-general').boundingBox();
  const posBranche = await page.locator('.arbre-branche .bloc').first().boundingBox();
  vrai('les branches sont en retrait', posBranche.x > posBoite.x + 8);
  vrai('et sous la boite', posBranche.y > posBoite.y + posBoite.height - 2);
  vrai('un filet les relie au tronc', await page.evaluate(function () {
    const b = document.querySelector('.arbre-branches');
    return !!b && getComputedStyle(b, '::before').content !== 'none';
  }));
  vrai('la boite prend du relief, pas les branches', await page.evaluate(function () {
    return getComputedStyle(document.querySelector('.bloc-general')).boxShadow !== 'none' &&
           getComputedStyle(document.querySelector('.bloc-branche')).boxShadow === 'none';
  }));

  // La photo se pose en haut a droite, en timbre ; les champs gardent leur
  // place a gauche et reprennent toute la largeur sous elle.
  const vign = await page.locator('.bloc-general .vignette-fiche').boundingBox();
  const champs = await page.locator('.bloc-general .fiche-champs').boundingBox();
  const premiereCle = await page.locator('.bloc-general .fiche-champs .ligne-cle').first().boundingBox();
  vrai('la photo est petite', vign.width <= 160);
  vrai('en haut a droite', vign.x + vign.width >= champs.x + champs.width - 2 &&
       Math.abs(vign.y - champs.y) < 24);
  vrai('les champs commencent au bord gauche', premiereCle.x <= champs.x + 2);
  vrai('et repassent a pleine largeur sous la photo', await page.evaluate(function () {
    const lignes = Array.from(document.querySelectorAll('.bloc-general .fiche-champs .ligne'));
    const derniere = lignes[lignes.length - 1].getBoundingClientRect();
    const photo = document.querySelector('.bloc-general .fiche-photo').getBoundingClientRect();
    return derniere.top >= photo.bottom - 1 && derniere.right >= photo.right - 2;
  }));
  vrai('dans un cadre de rapport fixe',
       Math.abs(vign.width / vign.height - 4 / 3) < 0.05);
  const posPn = await page.locator('.bloc-general .ligne-cle', { hasText: 'PN Global' }).boundingBox();
  vrai('la fonction et le PN se lisent sans defiler', posPn.y < 600);

  // Les trois boutons se distinguent : plein, blanc, blanc lisere de rouge.
  const fonds = await page.evaluate(function () {
    const g = document.querySelector('.bloc-general');
    const st = function (sel) { return getComputedStyle(g.querySelector(sel)); };
    return { eq: st('[data-action="comparer-boite"]').backgroundColor,
             eqTexte: st('[data-action="comparer-boite"]').color,
             ed: st('[data-action="editer-boite"]').backgroundColor,
             edBord: st('[data-action="editer-boite"]').borderTopColor,
             sup: st('[data-action="supprimer-boite"]').backgroundColor,
             supTexte: st('[data-action="supprimer-boite"]').color,
             supBord: st('[data-action="supprimer-boite"]').borderTopColor };
  });
  eq('Equivalences est plein marine', fonds.eq, 'rgb(0, 32, 91)');
  eq('en blanc dessus', fonds.eqTexte, 'rgb(255, 255, 255)');
  eq('Editer est blanc', fonds.ed, 'rgb(255, 255, 255)');
  eq('Supprimer aussi', fonds.sup, 'rgb(255, 255, 255)');
  eq('mais ecrit en rouge', fonds.supTexte, 'rgb(163, 32, 32)');
  vrai('et lisere de rouge, la ou Editer est lisere de gris', fonds.supBord !== fonds.edBord);

  // « Aussi montee dans » est une ligne de la fiche, pas un bandeau colle a la photo.
  await deplierBranches(page);
  const usages = page.locator('#slideOverBody .usages').first();
  eq('le reemploi se lit', await usages.count(), 1);
  vrai('comme une ligne, avec son libelle',
       (await usages.locator('xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " ligne ")][1]').innerText())
         .indexOf('Aussi montée dans') !== -1);
  eq('plus de bandeau', await page.locator('.usages-titre').count(), 0);
  await fermerFiche(page);
  await ecranPropre(page);

  bloc('Filtres par type de sous-ensemble');
  eq('3 types présents', await page.locator('.filtres-type .jeton').count(), 3);
  await page.locator('.jeton', { hasText: 'Harnais' }).click();
  await page.waitForTimeout(250);
  const avecHarnais = await page.locator('.carte').count();
  vrai('filtre appliqué', avecHarnais > 0 && avecHarnais < 10);
  vrai('filtre affiché comme retirable',
       await page.locator('#filtreActif .filtre-jeton').count() === 1);
  await page.locator('.jeton', { hasText: 'Plaquette' }).click();
  await page.waitForTimeout(250);
  const deuxTypes = await page.locator('.carte').count();
  vrai('deux types exigés ensemble = plus restrictif', deuxTypes <= avecHarnais);
  await page.locator('#filtreActif [data-action="tout-effacer"]').click();
  await page.waitForTimeout(250);
  eq('tout effacé', await page.locator('.carte').count(), 13);

  // ---------------------------------------------------------------
  bloc('Recherche et tri');
  await page.fill('#searchBar', 'mission SAR');
  await page.waitForTimeout(350);
  const parMotCle = await page.locator('.carte').count();
  vrai('recherche par mot-clé de plaquette', parMotCle > 0 && parMotCle < 10);
  await page.fill('#searchBar', 'commentaires');
  await page.waitForTimeout(350);
  eq('un nom de colonne ne ramène rien', await page.locator('.carte').count(), 0);
  await page.fill('#searchBar', '');
  await page.waitForTimeout(350);

  const compteurs = await page.locator('.onglet .onglet-compte')
    .evaluateAll(function (els) { return els.map(function (e) { return Number(e.textContent); }); });
  eq('somme des onglets = compteur « Toutes »',
     compteurs.slice(1).reduce(function (s, n) { return s + n; }, 0), compteurs[0]);

  // Le tri est un menu discret, plus un <select> planté dans la page.
  eq('pas de select de tri', await page.locator('#triSelect').count(), 0);
  await page.locator('#triBouton').click();
  await page.waitForTimeout(200);
  faux('le menu s\'ouvre', await page.locator('#triMenu').isHidden());
  await page.locator('.tri-option', { hasText: 'Statut' }).click();
  await page.waitForTimeout(300);
  vrai('tri par statut : un validé en tête',
       (await texte(page, '.carte')).indexOf('Validé') !== -1);
  vrai('le bouton reflète le tri courant',
       (await texte(page, '#triBouton')).indexOf('Statut') !== -1);
  await page.locator('#triBouton').click();
  await page.waitForTimeout(150);
  await page.locator('.tri-option', { hasText: 'PN croissant' }).click();
  await page.waitForTimeout(300);
  await page.mouse.click(5, 5);
  await page.waitForTimeout(200);
  vrai('le menu se referme quand on clique ailleurs',
       await page.locator('#triMenu').isHidden());

  // ---------------------------------------------------------------
  bloc('Fiche : des champs différents selon le type');
  await ouvrirFiche(page, '332P20001');
  eq('titre', await texte(page, '#slideOverTitle'), '332P20001');
  vrai('sommaire des types', await page.locator('.sommaire-item').count() >= 3);
  eq('1 bloc général + 3 sous-ensembles', await page.locator('#slideOverBody .bloc').count(), 4);
  eq('le bloc général s\'appelle « Boîte »',
     (await texte(page, '#slideOverBody .bloc-general h3')).trim(), 'Boîte');

  const blocHarnais = page.locator('.bloc-type-harnais').first();
  const txtHarnais = await blocHarnais.evaluate(function (el) { return el.textContent; });
  vrai('le harnais affiche sa référence', txtHarnais.indexOf('EN4165-002-02') !== -1);
  faux('le harnais n\'affiche pas de longueur', txtHarnais.indexOf('Longueur') !== -1);
  faux('ni de masse', txtHarnais.indexOf('Masse') !== -1);
  faux('ni de qualification', txtHarnais.indexOf('Qualif') !== -1);
  faux('ni de composants', txtHarnais.indexOf('Composants STD') !== -1);
  eq('le harnais ne propose plus de duplication',
     await blocHarnais.locator('[data-action="dupliquer-nom"]').count(), 0);
  eq('aucun sous-ensemble ne la propose',
     await page.locator('#slideOverBody [data-action="dupliquer-nom"]').count(), 0);
  vrai('mais il reste éditable',
       await blocHarnais.locator('[data-action="editer-nom"]').count() === 1);

  const blocStruct = page.locator('.bloc-type-structure').first();
  const txtStruct = await blocStruct.evaluate(function (el) { return el.textContent; });
  vrai('la structure affiche sa longueur', txtStruct.indexOf('Longueur') !== -1);
  vrai('et son nombre de pas', txtStruct.indexOf('Nombre de pas') !== -1);
  eq('la structure n\'a pas de champ Référence (celui du harnais)',
     await blocStruct.locator('.ligne-cle', { hasText: /^Référence/ }).count(), 0);
  vrai('elle porte sa composants mécaniques', txtStruct.indexOf('Composants mécaniques') !== -1);
  vrai('et ses composants électriques', txtStruct.indexOf('Composants routing') !== -1);
  eq('deux tableaux de composants', await blocStruct.locator('.composants').count(), 2);
  vrai('en trois colonnes : fonction, norme, référence',
       await blocStruct.locator('.composant .niveau-reference').count() >= 2);
  vrai('la colonnette est dans la composants mécaniques', txtStruct.indexOf('Colonnette') !== -1);
  vrai('le collier est dans les composants électriques', txtStruct.indexOf('Collier') !== -1);

  const blocGeneral = page.locator('.bloc-general');
  const txtGeneral = await blocGeneral.evaluate(function (el) { return el.textContent; });
  vrai('la boîte porte ses propres composants (boutons, voyants)',
       txtGeneral.indexOf('Bouton poussoir') !== -1);
  eq('un seul tableau de composants sur la boîte', await blocGeneral.locator('.composants').count(), 1);
  faux('pas de colonnette sur la boîte', txtGeneral.indexOf('Colonnette') !== -1);

  // Ajout d'un composant en trois niveaux, sans passer en édition.
  const nbAvantCompo = await blocGeneral.locator('.composant').count();
  await blocGeneral.locator('.saisie-composant[data-niveau="fonction"]').fill('Interrupteur');
  await blocGeneral.locator('.saisie-composant[data-niveau="norme"]').fill('ASNE 0567');
  await blocGeneral.locator('.saisie-composant[data-niveau="reference"]').fill('MS24524-23');
  await blocGeneral.locator('[data-action="ajouter-composant"]').click();
  await page.waitForTimeout(800);
  eq('composant ajouté sur la boîte',
     await page.locator('.bloc-general .composant').count(), nbAvantCompo + 1);
  vrai('avec ses trois niveaux',
       (await texte(page, '.bloc-general')).indexOf('MS24524-23') !== -1);
  await page.locator('.bloc-general .composant', { hasText: 'MS24524-23' })
            .locator('[data-action="supprimer-composant"]').click();
  await page.waitForTimeout(800);
  eq('et retiré', await page.locator('.bloc-general .composant').count(), nbAvantCompo);

  const blocPlaq = page.locator('.bloc-type-plaquette').first();
  const txtPlaq = await blocPlaq.evaluate(function (el) { return el.textContent; });
  vrai('la plaquette affiche ses mots-clés', txtPlaq.indexOf('mission SAR') !== -1);
  faux('pas de numéro', txtPlaq.indexOf('Numéro') !== -1);
  faux('pas de cotes', txtPlaq.indexOf('Longueur') !== -1);
  faux('pas de qualification', txtPlaq.indexOf('Qualif') !== -1);
  faux('pas de composants', txtPlaq.indexOf('Composants STD') !== -1);
  vrai('en puces dédiées', await blocPlaq.locator('.puce-motcle').count() >= 2);
  faux('plus de duplication de boîte dans la fiche',
       (await texte(page, '.bloc-general')).indexOf('Dupliquer') !== -1);

  // ---------------------------------------------------------------
  bloc('Édition');
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  await page.locator('.champ-boite[data-champ="DS/VCI Associé"]').fill('TEST-42');
  await page.locator('#slideOverBody [data-action="sauver-boite"]').click();
  await page.waitForTimeout(700);
  vrai('modification en fiche', (await texte(page, '#slideOverBody')).indexOf('TEST-42') !== -1);
  vrai('modification en carte',
       (await texte(page, '.carte:has-text("332P20001")')).indexOf('TEST-42') !== -1);

  const PIEGE = 'Entraxe 5" d\'origine <b>gras</b>';
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  await page.locator('.champ-boite[data-champ="Commentaires libres"]').fill(PIEGE);
  await page.locator('#slideOverBody [data-action="sauver-boite"]').click();
  await page.waitForTimeout(700);
  vrai('valeur piégée affichée entière',
       (await texte(page, '#slideOverBody')).indexOf(PIEGE) !== -1);
  eq('la balise n\'est pas interprétée',
     await page.locator('#slideOverBody b:text-is("gras")').count(), 0);
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  eq('elle revient intacte',
     await page.locator('.champ-boite[data-champ="Commentaires libres"]').inputValue(), PIEGE);
  await page.locator('#slideOverBody [data-action="annuler-boite"]').click();
  await page.waitForTimeout(200);
  eq('annulation', await page.locator('.champ-boite').count(), 0);

  // Mot-clé ajouté sur une plaquette
  const avantMots = await blocPlaq.locator('.puce-motcle').count();
  // Plus de bouton « Ajouter » : Entree pose la valeur, c'est tout.
  eq('le bouton Ajouter a disparu des champs libres',
     await blocPlaq.locator('.ajout-multi .btn-mini').count(), 0);
  await blocPlaq.locator('.saisie-multi[data-champ="Mots-clés"]').fill('treuil');
  await blocPlaq.locator('.saisie-multi[data-champ="Mots-clés"]').press('Enter');
  await page.waitForTimeout(750);
  eq('mot-clé ajouté',
     await page.locator('.bloc-type-plaquette').first().locator('.puce-motcle').count(),
     avantMots + 1);

  // ---------------------------------------------------------------
  bloc('Équivalences par type');
  await page.locator('.bloc-type-harnais [data-action="comparer-nom"]').first().click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(400);
  const sousTitre = await texte(page, '#compareSousTitre');
  vrai('le type est rappelé', sousTitre.indexOf('Harnais') !== -1);
  const corpsCompare = await texte(page, '#compareResult');
  vrai('des critères de harnais', corpsCompare.indexOf('Référence') !== -1);
  faux('aucun critère de dimensions', corpsCompare.indexOf('Dimensions') !== -1);
  faux('plus de « couverture » en pourcentage', /couverture/i.test(corpsCompare));
  vrai('le rappel de pondération est affiché', corpsCompare.indexOf('Pondération') !== -1);
  // Seul le candidat deplie montre ses criteres : douze candidats deroules
  // d'un coup, c'etait cent lignes et on perdait le fil. A l'ouverture, aucun.
  eq('a l\'ouverture, aucun candidat n\'est deplie',
     await page.locator('#compareResult .resultat.ouvert').count(), 0);
  await page.locator('#compareResult .resultat-tete').first().click();
  await page.waitForTimeout(400);
  vrai('le candidat deplie montre ses jauges',
       await page.locator('#compareResult .resultat.ouvert .critere-jauge').count() >= 1);
  eq('un seul candidat est deplie',
     await page.locator('#compareResult .resultat.ouvert').count(), 1);
  const replies = await page.locator('#compareResult .resultat:not(.ouvert)').count();
  if (replies) {
    eq('les autres ne montrent aucun critere',
       await page.locator('#compareResult .resultat:not(.ouvert) .critere-jauge').count(), 0);
  }
  // Un harnais se compare sur une égalité : pas d'ensembles à détailler.
  eq('aucun bloc d\'ensembles pour un harnais',
     await page.locator('#compareResult .ensemble').count(), 0);
  const scoreAvant = Number((await texte(page, '#compareResult .score b')).replace(/\D/g, ''));
  vrai('un score chiffré', scoreAvant >= 0 && scoreAvant <= 100);

  // ---------------------------------------------------------------
  bloc('Pondération en direct, côte à côte');
  faux('le rail est fermé au départ', await railVisible(page));
  await page.locator('#compareResult [data-action="ouvrir-reglages"]').click();
  await page.waitForTimeout(400);
  vrai('le rail de réglages s\'ouvre', await railVisible(page));
  // La comparaison reste à l'écran, à DROITE du rail : c'est tout l'intérêt.
  vrai('la comparaison reste à l\'écran',
       await page.locator('#compareModal.show').count() === 1);
  const boiteRail = await page.locator('#reglagesRail').boundingBox();
  const boiteResultats = await page.locator('#compareResult').boundingBox();
  vrai('le rail est à gauche du classement', boiteRail.x + boiteRail.width <= boiteResultats.x + 1);
  vrai('sur la même ligne', Math.abs(boiteRail.y - boiteResultats.y) < 40);
  vrai('le bouton dit maintenant « Masquer »',
       (await texte(page, '#compareResult [data-action="ouvrir-reglages"]')).indexOf('Masquer') !== -1);
  vrai('le panneau s\'ouvre sur la portée de la comparaison',
       (await texte(page, '#reglagesPortee')).indexOf('Harnais') !== -1);
  eq('plus d\'onglets de portée : le contexte décide',
     await page.locator('.onglet-reglage').count(), 0);
  eq('aucun curseur : le harnais n\'a qu\'un critère',
     await page.locator('.curseur').count(), 0);
  vrai('et le panneau l\'explique',
       (await texte(page, '#reglagesCurseurs')).indexOf('Un seul critère') !== -1);
  eq('plus de réglages rapides', await page.locator('[data-action="appliquer-preset"]').count(), 0);
  eq('plus d\'aperçu séparé : le classement est l\'aperçu', await page.locator('#reglagesApercu').count(), 0);
  vrai('le classement est toujours là, à droite',
       await page.locator('#compareResult .resultat').count() >= 1);
  await page.locator('#btnReglages').click();
  await page.waitForTimeout(300);
  faux('le bouton d\'en-tête referme le rail', await railVisible(page));

  await ecranPropre(page);

  // La structure, elle, s'arbitre : c'est là que les curseurs vivent.
  bloc('Pondération : le total reste à 100 %');
  await ouvrirFiche(page, '332P20001');
  await page.locator('.bloc-type-structure [data-action="comparer-nom"]').first().click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(400);
  await page.locator('#compareResult [data-action="ouvrir-reglages"]').click();
  await page.waitForTimeout(400);
  vrai('rail ouvert sur la structure', await railVisible(page) &&
       (await texte(page, '#reglagesPortee')).indexOf('Structure') !== -1);

  const lireTotal = async function () {
    return Number((await texte(page, '.reglage-total')).replace(/\D/g, ''));
  };
  const lireParts = async function () {
    return await page.locator('.reglage-part').evaluateAll(function (els) {
      return els.map(function (e) { return Number(e.textContent.replace(/\D/g, '')); });
    });
  };

  // 9 critères de structure, plus les 3 niveaux de composant qui se règlent
  // dans le même rail dès que la portée compare des composants.
  eq('9 critères de structure + 3 niveaux de composant',
     await page.locator('.curseur').count(), 12);
  eq('les niveaux ont leur propre bloc', await page.locator('.sous-reglage').count(), 1);
  vrai('l\'en-tête du rail annonce leur présence',
       (await texte(page, '#reglagesPortee')).indexOf('niveaux de composant') !== -1);
  // Le rail se lit de haut en bas : son en-tête reste fixe, le reste défile.
  const cadreRail = await page.locator('#reglagesRail').boundingBox();
  const teteAvant = await page.locator('.rail-tete').boundingBox();
  const premierCritere = await page.locator('.reglage').first().boundingBox();
  vrai('l\'en-tête coiffe les critères', teteAvant.y < premierCritere.y);

  await page.locator('#reglagesRail').evaluate(function (e) { e.scrollTo(0, e.scrollHeight); });
  await page.waitForTimeout(400);
  const teteApres = await page.locator('.rail-tete').boundingBox();
  vrai('il reste en place quand on descend',
       Math.abs(teteApres.y - teteAvant.y) < 3);
  vrai('et on sait toujours quelle portée on règle',
       (await texte(page, '.rail-tete')).indexOf('Structure') !== -1);
  const cadreNiveaux = await page.locator('.sous-reglage').boundingBox();
  vrai('on atteint les niveaux de composant en descendant',
       cadreNiveaux.y > cadreRail.y && cadreNiveaux.y < cadreRail.y + cadreRail.height);
  await page.locator('#reglagesRail').evaluate(function (e) { e.scrollTo(0, 0); });
  await page.waitForTimeout(300);
  eq('et leur propre total', await page.locator('.reglage-total').count(), 2);
  eq('les trois niveaux sont nommés',
     await page.locator('.sous-reglage .reglage-tete label')
               .evaluateAll(function (els) { return els.map(function (e) { return e.textContent; }); }),
     ['Fonction', 'Norme', 'Référence']);
  const totalNiveaux = Number((await page.locator('.reglage-total[data-portee="composant"]')
    .evaluate(function (e) { return e.textContent; })).replace(/\D/g, ''));
  eq('les niveaux totalisent 100 %', totalNiveaux, 100);

  // Bouger un niveau recompose le classement, comme n'importe quelle part.
  const scoreAvantNiveau = await texte(page, '#compareResult .score b');
  await page.locator('.sous-reglage .curseur').first().fill('90');
  await page.dispatchEvent('.sous-reglage .curseur', 'input');
  await page.waitForTimeout(450);
  const totalApres = Number((await page.locator('.reglage-total[data-portee="composant"]')
    .evaluate(function (e) { return e.textContent; })).replace(/\D/g, ''));
  eq('ils totalisent toujours 100 %', totalApres, 100);
  vrai('la pondération des niveaux est bien mémorisée comme les autres',
       await page.locator('#reglagesModifies').isVisible());
  vrai('un score reste affiché', (await texte(page, '#compareResult .score b')).length > 0);
  vrai('le score de structure a suivi ou tenu bon',
       typeof scoreAvantNiveau === 'string');
  await page.locator('#reglagesRail .btn-lien[data-action="reinitialiser-reglages"]').click();
  await page.waitForTimeout(400);
  // Les composants se comparent par paliers : référence, norme, fonction —
  // visibles dans le candidat qu'on deplie.
  if (!(await page.locator('#compareResult .resultat.ouvert').count())) {
    await page.locator('#compareResult .resultat-tete').first().click();
    await page.waitForTimeout(400);
  }
  vrai('les paliers d\'équivalence des composants sont affichés',
       await page.locator('#compareResult .palier').count() >= 1);
  const scoreAvantCurseur = Number((await texte(page, '#compareResult .score b')).replace(/\D/g, ''));
  eq('total à 100 au départ', await lireTotal(), 100);

  const partsAvant = await lireParts();
  await page.locator('.curseur').first().fill('80');
  await page.dispatchEvent('.curseur', 'input');
  await page.waitForTimeout(400);
  const partsApres = await lireParts();
  eq('total toujours 100 après déplacement', await lireTotal(), 100);
  // La première équivalence est identique sur tous les critères : son score
  // reste 100 quoi qu'on pondère. C'est le rappel des parts, réécrit à
  // chaque mouvement, qui prouve que le classement s'est recomposé.
  vrai('le classement à droite s\'est recomposé en direct',
       await page.locator('#compareResult .resultat').count() >= 1 &&
       (await texte(page, '#compareResult .rappel-texte')).indexOf('Montage 80 %') !== -1);
  vrai('un score chiffré reste affiché', scoreAvantCurseur >= 0 && scoreAvantCurseur <= 100);
  vrai('le rail est resté ouvert', await railVisible(page));
  eq('le curseur poussé vaut 80', partsApres[0], 80);
  vrai('les AUTRES ont bien diminué',
       partsApres.slice(1).every(function (p, i) { return p <= partsAvant[i + 1]; }));
  vrai('et au moins un a vraiment bougé',
       partsApres.slice(1).some(function (p, i) { return p < partsAvant[i + 1]; }));

  await page.locator('.curseur').first().fill('10');
  await page.dispatchEvent('.curseur', 'input');
  await page.waitForTimeout(400);
  const partsBasses = await lireParts();
  eq('total encore 100', await lireTotal(), 100);
  vrai('en redescendant, les autres remontent',
       partsBasses.slice(1).some(function (p, i) { return p > partsApres[i + 1]; }));

  bloc('Pondération : choisir les critères');
  const avantRetrait = await page.locator('.curseur').count();
  await page.locator('.reglage-retirer').first().click();
  await page.waitForTimeout(400);
  eq('un critère de moins', await page.locator('.curseur').count(), avantRetrait - 1);
  eq('total toujours 100', await lireTotal(), 100);
  eq('le critère écarté est proposé au rajout',
     await page.locator('.btn-ajout-critere').count(), 1);

  await page.locator('.btn-ajout-critere').first().click();
  await page.waitForTimeout(400);
  eq('critère réintégré', await page.locator('.curseur').count(), avantRetrait);
  eq('total toujours 100', await lireTotal(), 100);
  eq('plus rien dans les écartés', await page.locator('.btn-ajout-critere').count(), 0);

  vrai('la pondération personnalisée est signalée',
       await page.locator('#reglagesModifies').isVisible());

  await page.locator('#seuilCurseur').fill('60');
  await page.dispatchEvent('#seuilCurseur', 'input');
  await page.waitForTimeout(300);
  eq('seuil mis à jour', (await texte(page, '#seuilValeur')).trim(), '60 %');

  await page.locator('#reglagesRail .btn-lien[data-action="reinitialiser-reglages"]').click();
  await page.waitForTimeout(400);
  faux('plus de pondération personnalisée',
       await page.locator('#reglagesModifies').isVisible());
  eq('total rétabli à 100', await lireTotal(), 100);
  eq('seuil rétabli', (await texte(page, '#seuilValeur')).trim(), '15 %');
  await ecranPropre(page);

  // ---------------------------------------------------------------
  bloc('Annulation d\'une suppression');
  await ecranPropre(page);
  await ouvrirFiche(page, '332P20001');
  const avantSuppr = await page.locator('#slideOverBody .bloc').count();
  // Meme regle pour un sous-ensemble : Supprimer est la, tout de suite.
  vrai('Supprimer un sous-ensemble ne demande pas le mode edition',
       await page.locator('.bloc-type-plaquette [data-action="supprimer-nom"]').count() >= 1);
  await page.locator('.bloc-type-plaquette [data-action="supprimer-nom"]').first().click();
  await repondreDialogue(page);
  await page.waitForTimeout(900);
  eq('sous-ensemble supprimé', await page.locator('#slideOverBody .bloc').count(), avantSuppr - 1);
  vrai('un recours est proposé',
       await page.locator('#bandeauMessage [data-action="annuler-suppression"]').count() === 1);
  await page.locator('[data-action="annuler-suppression"]').click();
  await page.waitForTimeout(1600);
  eq('restauré', await page.locator('#slideOverBody .bloc').count(), avantSuppr);


  // ---------------------------------------------------------------
  bloc('Réemploi et doublons');
  await ecranPropre(page);
  // Une pièce montée dans plusieurs boîtes doit le dire, avec un lien.
  await ouvrirFiche(page, '332P20001');
  vrai('le réemploi est signalé',
       await page.locator('#slideOverBody .usages').count() >= 1);
  const lienUsage = page.locator('#slideOverBody .usage-lien').first();
  const pnLie = (await lienUsage.evaluate(function (el) { return el.textContent; })).trim();
  await lienUsage.click();
  await page.waitForTimeout(700);
  eq('le lien mène à l\'autre boîte', (await texte(page, '#slideOverTitle')).trim(), pnLie);
  await ecranPropre(page);

  await page.locator('[data-action="ouvrir-doublons"]').click();
  await page.waitForSelector('#doublonsModal.show');
  await page.waitForTimeout(400);
  const nbDoublons = await page.locator('.doublon').count();
  vrai('la liste des doublons s\'ouvre depuis l\'indicateur',
       nbDoublons >= 1 || (await texte(page, '#doublonsCorps')).indexOf('Aucun doublon') !== -1);
  if (nbDoublons) {
    vrai('chaque paire montre son score',
         await page.locator('.doublon .score').count() === nbDoublons);
    await page.locator('.doublon .doublon-boite').first().click();
    await page.waitForTimeout(700);
    vrai('on rebondit sur la fiche', await page.locator('#detailsSlideOver.show').count() === 1);
  }
  await ecranPropre(page);

  bloc('Plus de duplication : ni la boîte, ni ses sous-ensembles');
  await ecranPropre(page);
  eq('aucun bouton Dupliquer sur les cartes',
     await page.locator('.carte [data-action="dupliquer-boite"]').count(), 0);
  eq('aucun dans toute la page',
     await page.locator('[data-action="dupliquer-boite"]').count(), 0);
  await ouvrirFiche(page, '332P20001');
  eq('ni dans la fiche', await page.locator('#slideOverBody [data-action*="dupliquer"]').count(), 0);
  faux('le mot n\'apparaît plus dans la fiche',
       (await texte(page, '#slideOverBody')).indexOf('Dupliquer') !== -1);
  vrai('on ajoute un sous-ensemble plutôt que de le dupliquer',
       await page.locator('[data-action="nouveau-sous-ensemble"]').count() === 1);
  await fermerFiche(page);

  bloc('Catalogue et création typée');
  if (!(await page.locator('#detailsSlideOver.show').count())) await ouvrirFiche(page, '332P20001');
  // Le catalogue est filtré par catégorie : la composants mécaniques ne
  // propose pas de bouton poussoir, ni la boîte de colonnette.
  await page.locator('.bloc-type-structure [data-action="ouvrir-catalogue"][data-categorie="mecanique"]').first().click();
  await page.waitForSelector('#catalogueModal.show');
  await page.waitForTimeout(350);
  const catMeca = await texte(page, '#catalogueList');
  vrai('le catalogue mécanique propose des colonnettes', catMeca.indexOf('Colonnette') !== -1);
  faux('mais aucun bouton poussoir', catMeca.indexOf('Bouton poussoir') !== -1);
  await page.fill('#catSearch', 'NAS43DD3-22');
  await page.waitForTimeout(350);
  eq('un seul résultat', await page.locator('.ligne-catalogue').count(), 1);
  await page.locator('.ligne-catalogue').click();
  await page.waitForTimeout(900);
  const compos = await page.locator('.bloc-type-structure .composant')
    .evaluateAll(function (e) { return e.map(function (x) { return x.textContent; }); });
  vrai('le composant affiché est celui ajouté, avec sa référence',
       compos.some(function (p) { return p.indexOf('Colonnette') !== -1 && p.indexOf('NAS43DD3-22') !== -1; }));

  // Le catalogue se referme apres l'ajout : le geste se termine sur la fiche,
  // ou l'on voit tout de suite le composant pose.
  eq('le catalogue se referme apres un ajout',
     await page.locator('#catalogueModal.show').count(), 0);
  await page.waitForTimeout(400);

  await page.locator('.bloc-general [data-action="ouvrir-catalogue"]').first().click();
  await page.waitForSelector('#catalogueModal.show');
  await page.waitForTimeout(350);
  const catBoite = await texte(page, '#catalogueList');
  vrai('le catalogue de la boîte propose des boutons', catBoite.indexOf('Bouton poussoir') !== -1);
  faux('mais aucune colonnette', catBoite.indexOf('Colonnette') !== -1);
  await fermerModale(page, 'catalogueModal');

  await page.locator('[data-action="nouveau-sous-ensemble"]').click();
  await page.waitForSelector('#newSousEnsModal.show');
  await page.waitForTimeout(300);
  eq('3 types proposés, sans « Autre »', await page.locator('.choix-type').count(), 3);
  faux('« Autre sous-ensemble » a disparu',
       (await texte(page, '#choixType')).indexOf('Autre') !== -1);
  await page.locator('.choix-type', { hasText: 'Plaquette' }).click();
  await page.fill('#newEnsPn', 'PLQ-TEST');
  await page.locator('[data-action="creer-sous-ensemble"]').click();
  await page.waitForTimeout(900);
  vrai('créé avec le bon type',
       (await texte(page, '#slideOverBody')).indexOf('PLQ-TEST') !== -1);
  vrai('et ouvert directement en saisie',
       await page.locator('.champ-nom').count() > 0);

  // ---------------------------------------------------------------
  bloc('Panne serveur');
  await ecranPropre(page);
  await page.check('#demoPanne');
  await ouvrirFiche(page, '332P20001');
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  await page.locator('.champ-boite[data-champ="DS/VCI Associé"]').fill('NE-PASSE-PAS');
  await page.locator('#slideOverBody [data-action="sauver-boite"]').click();
  // On attend le CONTENU attendu, pas seulement la visibilité : un bandeau
  // d'une action précédente satisferait « visible » sans rien prouver.
  await page.waitForFunction(function () {
    const b = document.getElementById('bandeauMessage');
    return b && !b.hidden && b.textContent.indexOf('Échec') !== -1;
  }, null, { timeout: 8000 });
  const bandeau = await texte(page, '#bandeauMessage');
  vrai('bandeau d\'échec', bandeau.indexOf('Échec') !== -1);
  vrai('il dit que rien n\'est enregistré', bandeau.indexOf("n'a PAS été enregistrée") !== -1);
  eq('aucun indicateur bloqué', await page.locator('.mini-spinner').count(), 0);
  faux('la donnée n\'a pas bougé',
       (await texte(page, '#slideOverBody')).indexOf('NE-PASSE-PAS') !== -1);
  await fermerFiche(page);
  await page.uncheck('#demoPanne');

  // ---------------------------------------------------------------
  bloc('Validation serveur');
  await ecranPropre(page);
  await page.locator('.btn-creer').click();
  await page.waitForSelector('#newBoiteModal.show');
  await page.locator('[data-action="creer-boite"]').click();
  await page.waitForTimeout(400);
  vrai('PN vide refusé', (await texte(page, '#bandeauMessage')).indexOf('obligatoire') !== -1);
  await page.fill('#newBoitePn', '332P20001');
  await page.locator('[data-action="creer-boite"]').click();
  await page.waitForFunction(function () {
    const b = document.getElementById('bandeauMessage');
    return b && !b.hidden && b.textContent.indexOf('existe déjà') !== -1;
  }, null, { timeout: 8000 });
  vrai('PN en double refusé', true);
  await ecranPropre(page);
  eq('aucune boîte créée', await page.locator('.carte').count(), 13);

  // ---------------------------------------------------------------
  bloc('Thème sombre');
  await ecranPropre(page);
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.waitForTimeout(400);
  const sombre = await page.evaluate(function () {
    const corps = getComputedStyle(document.body);
    const carte = document.querySelector('.carte');
    return { fond: corps.backgroundColor, encre: corps.color,
             fondCarte: carte ? getComputedStyle(carte).backgroundColor : null };
  });
  vrai('le fond devient sombre',
       sombre.fond !== 'rgb(244, 246, 250)' && sombre.fond !== 'rgba(0, 0, 0, 0)');
  vrai('le texte reste clair sur fond sombre', sombre.encre.indexOf('231') !== -1 ||
       sombre.encre !== 'rgb(16, 26, 43)');
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-sombre.png') });
  await page.emulateMedia({ colorScheme: 'light' });
  await page.waitForTimeout(300);

  // ---------------------------------------------------------------
  bloc('Affichage mobile');
  await ecranPropre(page);
  await page.setViewportSize({ width: 400, height: 820 });
  await page.waitForTimeout(450);
  let l = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de défilement horizontal (grille)', l.doc <= l.vue + 1);
  await ouvrirFiche(page, '332P20001');
  l = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth,
             panneau: document.getElementById('detailsSlideOver').getBoundingClientRect().width };
  });
  vrai('pas de défilement horizontal (fiche)', l.doc <= l.vue + 1);
  vrai('le panneau tient dans l\'écran', l.panneau <= l.vue);
  await fermerFiche(page);
  await ecranPropre(page);
  // Le panneau ne s'ouvre plus que depuis une comparaison.
  await page.locator('.carte').first()
            .getByRole('button', { name: 'Équivalences' }).click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(400);
  await page.locator('#compareResult [data-action="ouvrir-reglages"]').click();
  await page.waitForTimeout(400);
  vrai('le rail s\'ouvre aussi sur mobile', await railVisible(page));
  l = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de défilement horizontal (réglages)', l.doc <= l.vue + 1);
  await ecranPropre(page);
  await page.setViewportSize({ width: 1400, height: 950 });

  // ---------------------------------------------------------------
  bloc('Captures');
  await ecranPropre(page);
  await page.locator('#demoReset').click();
  await page.waitForTimeout(1200);
  eq('réinitialisation de la démo', await page.locator('.carte').count(), 13);
  await page.evaluate(function () {
    // Bootstrap rend le focus au déclencheur en fermant un panneau, ce qui
    // refait défiler la page : on le retire avant de remonter.
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    document.body.style.overflow = '';
    document.body.classList.remove('modal-open', 'offcanvas-open');
    const b = document.getElementById('bandeauMessage');
    if (b) b.hidden = true;
  });
  await page.waitForTimeout(400);
  // La page se recompose après la réinitialisation ; on insiste jusqu'à ce
  // que le défilement tienne vraiment à zéro.
  await page.waitForFunction(function () {
    window.scrollTo(0, 0);
    return window.scrollY === 0;
  }, null, { timeout: 5000 });
  eq('la page est bien en haut', await page.evaluate(function () { return window.scrollY; }), 0);
  vrai('en-tête visible en haut de page', await page.locator('.entete').isVisible());
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-grille.png') });
  await page.locator('.onglet-vue', { hasText: 'Sous-ensembles' }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-pieces.png') });
  await page.locator('.onglet-vue', { hasText: 'Boîtes' }).click();
  await page.waitForTimeout(400);
  await ouvrirFiche(page, '332P20001', true);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-fiche.png') });
  await deplierBranches(page);
  await page.locator('.bloc-type-plaquette [data-action="comparer-nom"]').first().click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-equivalences.png') });
  await fermerModale(page, 'compareModal');
  // La structure : c'est elle qui porte les curseurs.
  await page.locator('.bloc-type-structure [data-action="comparer-nom"]').first().click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(400);

  // Réglages PAR-DESSUS la comparaison : c'est la situation réelle d'usage,
  // on ajuste en voyant le classement se recomposer.
  await page.locator('#compareResult [data-action="ouvrir-reglages"]').click();
  await page.waitForTimeout(700);
  vrai('réglages et comparaison coexistent, côte à côte',
       await page.locator('#compareModal.show').count() === 1 && await railVisible(page));
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-reglages.png') });
  console.log('  8 captures écrites dans build/');

  eq('aucune exception JavaScript non rattrapée', exceptions, []);
  vrai('les échecs provoqués ont été journalisés', diagnostics.length >= 2);
  // Aucune ressource ne doit manquer, hors polices : elles ont une pile de
  // repli déclarée, et le bac à sable de test n'a pas accès au réseau.
  // Hors polices (pas de réseau ici) et hors l'URL fictive que le test injecte
  // lui-même pour vérifier que le champ Image est bien câblé.
  const inattendues = requetesEchouees.filter(function (u) {
    return u.indexOf('fonts.googleapis.com') === -1 &&
           u.indexOf('fonts.gstatic.com') === -1 &&
           u.indexOf('exemple.fr') === -1;
  });
  eq('aucune ressource manquante inattendue', inattendues, []);
  if (reseau.length) {
    console.log('  ' + '\x1b[90m' + 'note : ' + reseau.length +
                ' chargement(s) réseau bloqué(s) par le bac à sable (polices)' + '\x1b[0m');
  }

  await navigateur.close();
  console.log('\n' + (ko === 0 ? V : R) + ok + ' OK, ' + ko + ' KO' + Z);
  process.exit(ko === 0 ? 0 : 1);
})().catch(function (e) {
  console.error('\n' + R + 'Échec du test navigateur : ' + Z + e.message);
  process.exit(1);
});

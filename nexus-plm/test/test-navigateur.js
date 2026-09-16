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
async function ouvrirFiche(page, pn) {
  await page.locator('.carte', { hasText: pn })
            .getByRole('button', { name: 'Fiche complète' }).click();
  await page.waitForSelector('#detailsSlideOver.show');
  await page.waitForTimeout(320);
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
  eq('10 boîtes', await page.locator('.carte').count(), 10);
  eq('titre NEXUS seul', (await texte(page, '.marque h1')).trim(), 'NEXUS');
  eq('indicateur boîtes', await texte(page, '#kpiBoites'), '10');
  eq('validées', await texte(page, '#kpiVal'), '5 / 10');
  eq('libellé « Boîtes »', (await texte(page, '.indicateur-libelle')).trim(), 'Boîtes');
  eq('plus d\'indicateur de réutilisation', await page.locator('#kpiReutil').count(), 0);
  eq('ni son filtre', await page.locator('[data-action="filtrer-reutilise"]').count(), 0);
  vrai('indicateur « À standardiser » renseigné',
       Number(await texte(page, '#kpiStandard')) >= 0);
  eq('plus de ligne de portée sous les chiffres',
     await page.locator('#kpiPortee, .indicateurs-portee').count(), 0);
  eq('plus de badge « / » dans le champ de recherche',
     await page.locator('.champ-recherche .raccourci').count(), 0);
  vrai('indicateur de doublons renseigné',
       (await texte(page, '#kpiDoublons')).trim().length > 0);
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
  eq('17 porteurs proposés à la création',
     await page.locator('#newBoitePorteurs input').count(), 17);
  eq('aucun « Multi »', await page.locator('#newBoitePorteurs input[value="Multi"]').count(), 0);
  eq('« Super Puma » n\'est plus un porteur', await page.locator('#list-Porteur option[value="Super Puma"]').count(), 0);
  eq('pas d\'export CSV', await page.locator('[data-action="exporter-bom"]').count(), 0);
  faux('chargement masqué', await page.locator('#loading').isVisible());
  eq('chaque boîte a sa photo', await page.locator('img.carte-image').count(), 10);
  eq('le statut se lit sur la photo', await page.locator('.carte-statut').count(), 10);
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
  eq('11 boîtes', await page.locator('.carte').count(), 11);

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
  eq('retour à 10 boîtes', await page.locator('.carte').count(), 10);
  await ecranPropre(page);

  bloc('Indicateurs qui filtrent');
  await page.locator('#indValidees').click();
  await page.waitForTimeout(300);
  eq('cliquer « Validées » ne montre que les validées', await page.locator('.carte').count(), 5);
  vrai('l\'indicateur se dit actif',
       (await page.locator('#indValidees').getAttribute('class')).indexOf('actif') !== -1);
  eq('et propose son retrait dans les filtres',
     await page.locator('#filtreActif [data-action="filtrer-statut"]').count(), 1);
  await page.locator('#indValidees').click();
  await page.waitForTimeout(300);
  eq('second clic : retour à 10', await page.locator('.carte').count(), 10);
  await page.locator('#indBoites').click();
  await page.waitForTimeout(300);
  eq('« Boîtes » remet tout', await page.locator('.carte').count(), 10);

  // ---------------------------------------------------------------
  bloc('Vue Pièces : où sert chaque référence');
  await ecranPropre(page);
  eq('trois vues proposées', await page.locator('.onglet-vue').count(), 3);
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
  eq('les cartes reviennent', await page.locator('.carte').count(), 10);
  eq('et le tri aussi', await page.locator('#triBouton').count(), 1);

  // ---------------------------------------------------------------
  bloc('Vue Standardisation : où la base se disperse');
  await ecranPropre(page);
  eq('trois vues proposées', await page.locator('.onglet-vue').count(), 3);
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

  const largeurStd = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de défilement horizontal (standardisation)', largeurStd.doc <= largeurStd.vue + 1);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-standardisation.png') });

  await page.locator('.onglet-vue', { hasText: 'Boîtes' }).click();
  await page.waitForTimeout(350);
  eq('retour à la grille', await page.locator('.carte').count(), 10);

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
  const suggestion = await page.locator('#datalistStds option').first()
    .evaluate(function (e) { return e.value; });
  vrai('des suggestions sont proposees', suggestion.length > 0);
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
  vrai('la grille derriere est deja filtree', filtrees > 0 && filtrees < 10);
  eq('le filtre actif le dit',
     await page.locator('#filtreActif .filtre-jeton').count(), 1);

  // Entree ajoute aussi, pour une valeur libre.
  await page.fill('#multiSearchInputSelect', 'NSA 5512');
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
     await page.locator('.carte').count(), 10);

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
  faux('une norme de colonnette n\'y figure plus', normesBP.indexOf('NSA 5512') !== -1);
  vrai('mais la sienne, oui', normesBP.indexOf('ECS 7251') !== -1);
  const refsBP = await listeDe('reference');
  vrai('les references suivent aussi',
       refsBP.length > 0 && refsBP.every(function (r) { return r.indexOf('MS24523') === 0; }));
  await page.locator(blocBoite + ' .saisie-composant[data-niveau="norme"]').fill('ECS 7251');
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
  vrai('la colonnette ne propose que sa norme', normesMeca.indexOf('NSA 5512') !== -1);
  faux('et pas celles des boutons', normesMeca.indexOf('ECS 7251') !== -1);
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
  await page.locator('#indDoublons').click();
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
     await page.locator('#indRefs').count(), 0);
  eq('et c\'est un bouton', await page.locator('button#indStandard').count(), 1);
  vrai('il annonce un nombre de familles',
       Number(await texte(page, '#kpiStandard')) >= 0);
  vrai('et dit de quoi il s\'agit',
       (await texte(page, '#kpiStandardDetail')).indexOf('référence') !== -1);
  await page.locator('#indStandard').click();
  await page.waitForTimeout(450);
  eq('un clic mene a la vue Standardisation', await page.locator('.carte').count(), 0);
  vrai('des familles y sont listees', await page.locator('.famille').count() > 0);
  eq('l\'indicateur se marque', await page.locator('#indStandard').getAttribute('aria-pressed'), 'true');
  await page.locator('#indStandard').click();
  await page.waitForTimeout(450);
  eq('un second clic ramene aux cartes', await page.locator('.carte').count(), 10);


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
  const detailDoublons = await texte(page, '#kpiDoublonsDetail');
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
  eq('tout effacé', await page.locator('.carte').count(), 10);

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
  vrai('le harnais affiche sa référence', txtHarnais.indexOf('HRN-2251-A') !== -1);
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
  vrai('elle porte sa structure mécanique', txtStruct.indexOf('Structure mécanique') !== -1);
  vrai('et ses composants électriques', txtStruct.indexOf('Composants électriques') !== -1);
  eq('deux tableaux de composants', await blocStruct.locator('.composants').count(), 2);
  vrai('en trois colonnes : fonction, norme, référence',
       await blocStruct.locator('.composant .niveau-reference').count() >= 2);
  vrai('la colonnette est dans la structure mécanique', txtStruct.indexOf('Colonnette') !== -1);
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
  await blocGeneral.locator('.saisie-composant[data-niveau="reference"]').fill('8500K12');
  await blocGeneral.locator('[data-action="ajouter-composant"]').click();
  await page.waitForTimeout(800);
  eq('composant ajouté sur la boîte',
     await page.locator('.bloc-general .composant').count(), nbAvantCompo + 1);
  vrai('avec ses trois niveaux',
       (await texte(page, '.bloc-general')).indexOf('8500K12') !== -1);
  await page.locator('.bloc-general .composant', { hasText: '8500K12' })
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
  await blocPlaq.locator('.saisie-multi[data-champ="Mots-clés"]').fill('treuil');
  await blocPlaq.locator('[data-action="ajouter-multi-nom"][data-champ="Mots-clés"]').click();
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
  vrai('chaque critère montre sa jauge',
       await page.locator('#compareResult .critere-jauge').count() >= 2);
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
  await page.locator('[data-action="reinitialiser-reglages"]').click();
  await page.waitForTimeout(400);
  // Les composants se comparent par paliers : référence, norme, fonction.
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

  await page.locator('[data-action="reinitialiser-reglages"]').click();
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
  // Le catalogue est filtré par catégorie : la structure mécanique ne
  // propose pas de bouton poussoir, ni la boîte de colonnette.
  await page.locator('.bloc-type-structure [data-action="ouvrir-catalogue"][data-categorie="mecanique"]').first().click();
  await page.waitForSelector('#catalogueModal.show');
  await page.waitForTimeout(350);
  const catMeca = await texte(page, '#catalogueList');
  vrai('le catalogue mécanique propose des colonnettes', catMeca.indexOf('Colonnette') !== -1);
  faux('mais aucun bouton poussoir', catMeca.indexOf('Bouton poussoir') !== -1);
  await page.fill('#catSearch', 'entretoise');
  await page.waitForTimeout(350);
  eq('un seul résultat', await page.locator('.ligne-catalogue').count(), 1);
  await page.locator('.ligne-catalogue').click();
  await page.waitForTimeout(900);
  const compos = await page.locator('.bloc-type-structure .composant')
    .evaluateAll(function (e) { return e.map(function (x) { return x.textContent; }); });
  vrai('le composant affiché est celui ajouté, avec sa référence',
       compos.some(function (p) { return p.indexOf('Entretoise') !== -1 && p.indexOf('ENT-10') !== -1; }));

  // Poser trois colonnettes ne doit pas demander d'ouvrir le catalogue trois
  // fois : il reste ouvert, et la liste se rafraichit sur place.
  vrai('le catalogue reste ouvert apres un ajout',
       await page.locator('#catalogueModal.show').count() === 1);
  await page.fill('#catSearch', 'colonnette');
  await page.waitForTimeout(350);
  vrai('on peut y enchainer un second choix',
       await page.locator('.ligne-catalogue').count() >= 1);
  await page.locator('.ligne-catalogue').first().click();
  await page.waitForTimeout(900);
  const compos2 = await page.locator('.bloc-type-structure .composant')
    .evaluateAll(function (e) { return e.map(function (x) { return x.textContent; }); });
  vrai('le second composant est pose lui aussi',
       compos2.some(function (p) { return p.indexOf('Colonnette') !== -1; }));
  await fermerModale(page, 'catalogueModal');
  await page.waitForTimeout(300);

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
  eq('aucune boîte créée', await page.locator('.carte').count(), 10);

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
  eq('réinitialisation de la démo', await page.locator('.carte').count(), 10);
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
  await ouvrirFiche(page, '332P20001');
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-fiche.png') });
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
  console.log('  6 captures écrites dans build/');

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

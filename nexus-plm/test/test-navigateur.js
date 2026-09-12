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

/**
 * Remet l'écran à plat entre deux sections : sans cela une assertion peut
 * lire un bandeau resté d'une action précédente, ou cliquer à travers un
 * panneau encore ouvert.
 */
async function ecranPropre(page) {
  await page.evaluate(function () {
    window.scrollTo(0, 0);          // la barre collante recouvrirait l'en-tête
    ['detailsSlideOver', 'reglagesModal'].forEach(function (id) {
      const el = document.getElementById(id);
      const i = el && window.bootstrap.Offcanvas.getInstance(el);
      if (i) i.hide();
    });
    ['compareModal', 'journalModal', 'catalogueModal', 'newBoiteModal',
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
  eq('10 assemblages', await page.locator('.carte').count(), 10);
  eq('indicateur assemblages', await texte(page, '#kpiBoites'), '10');
  eq('indicateur sous-ensembles', await texte(page, '#kpiLignes'), '18');
  eq('validés', await texte(page, '#kpiVal'), '5 / 10');
  faux('chargement masqué', await page.locator('#loading').isVisible());
  eq('toutes les cartes ont une illustration', await page.locator('.carte-image').count(), 10);
  vrai('les illustrations sont des images réelles',
       await page.locator('img.carte-image').count() === 10);
  // Une entrée par type présent et par carte, pas une par sous-ensemble.
  const compositions = await page.locator('.composition li').count();
  vrai('la composition par type est affichée', compositions >= 10);
  vrai('les trois types apparaissent en composition',
       (await texte(page, '#mainContainer')).indexOf('Harnais') !== -1 &&
       (await texte(page, '#mainContainer')).indexOf('Plaquette') !== -1 &&
       (await texte(page, '#mainContainer')).indexOf('Structure') !== -1);

  // ---------------------------------------------------------------
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
  await page.locator('[data-action="tout-effacer"]').click();
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

  await page.selectOption('#triSelect', 'statut');
  await page.waitForTimeout(250);
  vrai('tri par statut : un validé en tête',
       (await texte(page, '.carte')).indexOf('Validé') !== -1);
  await page.selectOption('#triSelect', 'pn');
  await page.waitForTimeout(250);

  // ---------------------------------------------------------------
  bloc('Fiche : des champs différents selon le type');
  await ouvrirFiche(page, '332P20001');
  eq('titre', await texte(page, '#slideOverTitle'), '332P20001');
  vrai('sommaire des types', await page.locator('.sommaire-item').count() >= 3);
  eq('1 bloc général + 3 sous-ensembles', await page.locator('#slideOverBody .bloc').count(), 4);

  const blocHarnais = page.locator('.bloc-type-harnais').first();
  const txtHarnais = await blocHarnais.evaluate(function (el) { return el.textContent; });
  vrai('le harnais affiche sa référence', txtHarnais.indexOf('HRN-2251-A') !== -1);
  faux('le harnais n\'affiche pas de longueur', txtHarnais.indexOf('Longueur') !== -1);
  faux('ni de masse', txtHarnais.indexOf('Masse') !== -1);

  const blocStruct = page.locator('.bloc-type-structure').first();
  const txtStruct = await blocStruct.evaluate(function (el) { return el.textContent; });
  vrai('la structure affiche sa longueur', txtStruct.indexOf('Longueur') !== -1);
  vrai('et son nombre de pas', txtStruct.indexOf('Nombre de pas') !== -1);
  faux('la structure n\'a pas de référence', txtStruct.indexOf('Référence') !== -1);

  const blocPlaq = page.locator('.bloc-type-plaquette').first();
  const txtPlaq = await blocPlaq.evaluate(function (el) { return el.textContent; });
  vrai('la plaquette affiche son numéro', txtPlaq.indexOf('PL-1042') !== -1);
  vrai('et ses mots-clés', txtPlaq.indexOf('mission SAR') !== -1);
  vrai('en puces dédiées', await blocPlaq.locator('.puce-motcle').count() >= 2);
  vrai('chaque sous-ensemble a son illustration',
       await page.locator('#slideOverBody .vignette').count() >= 3);

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
  vrai('la couverture est affichée', /couverture/i.test(corpsCompare));
  vrai('la part de chaque critère est affichée', /% du score/.test(corpsCompare));
  vrai('chaque critère montre sa jauge',
       await page.locator('#compareResult .critere-jauge').count() >= 2);
  vrai('les blocs commun / manquant / en plus',
       await page.locator('#compareResult .ensemble').count() >= 1);
  const scoreAvant = Number((await texte(page, '#compareResult .score b')).replace(/\D/g, ''));
  vrai('un score chiffré', scoreAvant >= 0 && scoreAvant <= 100);

  // ---------------------------------------------------------------
  bloc('Pondération en direct');
  await page.locator('#compareResult [data-action="ouvrir-reglages"]').click();
  await page.waitForSelector('#reglagesModal.show');
  // La comparaison doit rester visible derrière : c'est tout l'intérêt.
  vrai('la comparaison reste à l\'écran',
       await page.locator('#compareModal.show').count() === 1);
  await page.waitForTimeout(400);
  vrai('la portée Harnais est pré-sélectionnée',
       (await texte(page, '.onglet-reglage.actif')).indexOf('Harnais') !== -1);
  const nbCurseurs = await page.locator('.curseur').count();
  eq('un curseur par critère du harnais', nbCurseurs, 3);
  vrai('aperçu en direct présent', await page.locator('.apercu-liste li').count() >= 1);

  const partAvant = await texte(page, '.reglage .reglage-part');
  await page.locator('.curseur').first().fill('100');
  await page.waitForTimeout(350);
  const partApres = await texte(page, '.reglage .reglage-part');
  vrai('la part affichée change avec le curseur', partAvant !== partApres);
  vrai('la pondération personnalisée est signalée',
       await page.locator('#reglagesModifies').isVisible());

  await page.locator('.curseur').first().fill('0');
  await page.waitForTimeout(350);
  vrai('un critère à 0 est marqué ignoré',
       (await texte(page, '.reglage')).indexOf('ignoré') !== -1);
  // Et le classement derrière le dit aussi : c'est le lien réglage -> résultat.
  vrai('la comparaison affiche « ignoré par vos réglages »',
       (await texte(page, '#compareResult')).indexOf('ignoré par vos réglages') !== -1);

  await page.locator('[data-action="appliquer-preset"]').first().click();
  await page.waitForTimeout(350);
  await page.locator('.onglet-reglage', { hasText: 'Plaquette' }).click();
  await page.waitForTimeout(300);
  vrai('les critères de la plaquette apparaissent',
       (await texte(page, '#reglagesCurseurs')).indexOf('Mots-clés') !== -1);
  await page.locator('.onglet-reglage', { hasText: 'Structure' }).click();
  await page.waitForTimeout(300);
  vrai('ceux de la structure aussi',
       (await texte(page, '#reglagesCurseurs')).indexOf('Dimensions') !== -1);

  await page.locator('#seuilCurseur').fill('60');
  await page.waitForTimeout(300);
  eq('seuil mis à jour', (await texte(page, '#seuilValeur')).trim(), '60 %');
  await page.locator('#seuilCurseur').fill('15');
  await page.waitForTimeout(300);

  await page.locator('[data-action="reinitialiser-reglages"]').click();
  await page.waitForTimeout(350);
  faux('plus de pondération personnalisée',
       await page.locator('#reglagesModifies').isVisible());
  await page.locator('#reglagesModal .btn-close').click();
  await attendreFerme(page, 'reglagesModal');

  // Le score recalculé doit correspondre aux réglages remis à zéro
  await page.waitForTimeout(300);
  const scoreApres = Number((await texte(page, '#compareResult .score b')).replace(/\D/g, ''));
  eq('score revenu à sa valeur d\'origine', scoreApres, scoreAvant);
  await fermerModale(page, 'compareModal');

  // ---------------------------------------------------------------
  bloc('Journal et annulation');
  await fermerFiche(page);                       // l'en-tête doit être atteignable
  await page.locator('[data-action="ouvrir-journal"]').click();
  await page.waitForSelector('#journalModal.show');
  await page.waitForTimeout(300);
  vrai('des actions sont tracées', await page.locator('.journal-ligne').count() >= 3);
  vrai('le compteur suit', Number(await texte(page, '#journalCompteur')) >= 3);
  await fermerModale(page, 'journalModal');

  await ouvrirFiche(page, '332P20001');
  const avantSuppr = await page.locator('#slideOverBody .bloc').count();
  page.once('dialog', function (d) { d.accept(); });
  await page.locator('.bloc-type-plaquette [data-action="editer-nom"]').first().click();
  await page.locator('.bloc-type-plaquette [data-action="supprimer-nom"]').first().click();
  await page.waitForTimeout(900);
  eq('sous-ensemble supprimé', await page.locator('#slideOverBody .bloc').count(), avantSuppr - 1);
  vrai('un recours est proposé',
       await page.locator('#bandeauMessage [data-action="annuler-suppression"]').count() === 1);
  await page.locator('[data-action="annuler-suppression"]').click();
  await page.waitForTimeout(1600);
  eq('restauré', await page.locator('#slideOverBody .bloc').count(), avantSuppr);
  vrai('la restauration est tracée',
       (await page.locator('.journal-ligne').first().evaluate(function (el) { return el.textContent; }) ||
        (await texte(page, '#journalCorps'))).length > 0);

  // ---------------------------------------------------------------
  bloc('Catalogue et création typée');
  if (!(await page.locator('#detailsSlideOver.show').count())) await ouvrirFiche(page, '332P20001');
  await page.locator('.bloc-type-harnais [data-action="ouvrir-catalogue"]').first().click();
  await page.waitForSelector('#catalogueModal.show');
  await page.fill('#catSearch', 'diode');
  await page.waitForTimeout(350);
  eq('un seul résultat', await page.locator('.ligne-catalogue').count(), 1);
  await page.locator('.ligne-catalogue').click();
  await page.waitForTimeout(900);
  const puces = await page.locator('.bloc-type-harnais .puce')
    .evaluateAll(function (e) { return e.map(function (x) { return x.textContent; }); });
  vrai('le composant affiché est celui ajouté',
       puces.some(function (p) { return p.indexOf('Diode') !== -1; }));

  await page.locator('[data-action="nouveau-sous-ensemble"]').click();
  await page.waitForSelector('#newSousEnsModal.show');
  await page.waitForTimeout(300);
  eq('4 types proposés', await page.locator('.choix-type').count(), 4);
  await page.locator('.choix-type', { hasText: 'Plaquette' }).click();
  await page.fill('#newEnsPn', 'PLQ-TEST');
  await page.locator('[data-action="creer-sous-ensemble"]').click();
  await page.waitForTimeout(900);
  vrai('créé avec le bon type',
       (await texte(page, '#slideOverBody')).indexOf('PLQ-TEST') !== -1);
  vrai('et ouvert directement en saisie',
       await page.locator('.champ-nom').count() > 0);

  // ---------------------------------------------------------------
  bloc('Export CSV');
  await page.locator('[data-action="exporter-bom"]').click();
  await page.waitForSelector('#demoCsvModal.show');
  await page.waitForTimeout(300);
  const meta = await texte(page, '#demoCsvMeta');
  const csv = await texte(page, '#demoCsvContenu');
  vrai('BOM UTF-8', meta.indexOf('BOM UTF-8 présent') !== -1);
  vrai('colonnes des trois types', csv.indexOf('"Référence"') !== -1 &&
       csv.indexOf('"Mots-clés"') !== -1);
  vrai('accents intacts', /é/.test(csv));
  await fermerModale(page, 'demoCsvModal');

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
  await page.locator('.btn-entete-fort').click();
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
  eq('aucun assemblage créé', await page.locator('.carte').count(), 10);

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
  await page.locator('.btn-entete', { hasText: 'Pondération' }).click();
  await page.waitForSelector('#reglagesModal.show');
  await page.waitForTimeout(400);
  l = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de défilement horizontal (réglages)', l.doc <= l.vue + 1);
  await page.locator('#reglagesModal .btn-close').click();
  await attendreFerme(page, 'reglagesModal');
  await page.setViewportSize({ width: 1400, height: 950 });

  // ---------------------------------------------------------------
  bloc('Captures');
  await ecranPropre(page);
  await page.locator('#demoReset').click();
  await page.waitForTimeout(1000);
  await page.evaluate(function () {
    window.scrollTo(0, 0);
    const b = document.getElementById('bandeauMessage');
    if (b) b.hidden = true;
  });
  await page.waitForTimeout(400);
  vrai('en-tête visible en haut de page', await page.locator('.entete').isVisible());
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-grille.png') });
  await ouvrirFiche(page, '332P20001');
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-fiche.png') });
  await page.locator('.bloc-type-plaquette [data-action="comparer-nom"]').first().click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-equivalences.png') });

  // Réglages PAR-DESSUS la comparaison : c'est la situation réelle d'usage,
  // on ajuste en voyant le classement se recomposer.
  await page.locator('#compareResult [data-action="ouvrir-reglages"]').click();
  await page.waitForSelector('#reglagesModal.show');
  await page.waitForTimeout(700);
  vrai('réglages et comparaison coexistent',
       await page.locator('#compareModal.show').count() === 1 &&
       await page.locator('#reglagesModal.show').count() === 1);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-reglages.png') });
  console.log('  5 captures écrites dans build/');

  eq('aucune exception JavaScript non rattrapée', exceptions, []);
  vrai('les échecs provoqués ont été journalisés', diagnostics.length >= 2);
  // Aucune ressource ne doit manquer, hors polices : elles ont une pile de
  // repli déclarée, et le bac à sable de test n'a pas accès au réseau.
  const horsPolices = requetesEchouees.filter(function (u) {
    return u.indexOf('fonts.googleapis.com') === -1 && u.indexOf('fonts.gstatic.com') === -1;
  });
  eq('aucune ressource manquante hors polices', horsPolices, []);
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

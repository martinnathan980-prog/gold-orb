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
    ['compareModal', 'catalogueModal', 'newBoiteModal',
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
  eq('libellé « Boîtes »', (await texte(page, '.indicateur dt')).trim(), 'Boîtes');
  vrai('indicateur de réutilisation renseigné',
       Number(await texte(page, '#kpiReutil')) > 0);
  vrai('indicateur de doublons renseigné',
       (await texte(page, '#kpiDoublons')).trim().length > 0);
  eq('pas de compteur de sous-ensembles', await page.locator('#kpiLignes').count(), 0);
  eq('pas de bouton Journal', await page.locator('[data-action="ouvrir-journal"]').count(), 0);
  eq('pas de Pondération dans l\'en-tête',
     await page.locator('.entete [data-action="ouvrir-reglages"]').count(), 0);
  eq('bouton « + Boîte »', (await texte(page, '.btn-entete-fort')).trim(), '+ Boîte');
  eq('pas d\'export CSV', await page.locator('[data-action="exporter-bom"]').count(), 0);
  faux('chargement masqué', await page.locator('#loading').isVisible());
  // Aucune image fabriquée : le champ attend une URL de photo.
  eq('aucun dessin généré', await page.locator('img.carte-image').count(), 0);
  eq('un état « pas de photo » assumé',
     await page.locator('.carte-image-absente').count(), 10);
  // Une entrée par type présent et par carte, pas une par sous-ensemble.
  const compositions = await page.locator('.composition li').count();
  vrai('la composition par type est affichée', compositions >= 10);
  vrai('les trois types apparaissent en composition',
       (await texte(page, '#mainContainer')).indexOf('Harnais') !== -1 &&
       (await texte(page, '#mainContainer')).indexOf('Plaquette') !== -1 &&
       (await texte(page, '#mainContainer')).indexOf('Structure') !== -1);

  // ---------------------------------------------------------------
  bloc('Créer une boîte complète');
  await page.locator('.btn-entete-fort').click();
  await page.waitForSelector('#newBoiteModal.show');
  await page.waitForTimeout(300);
  await page.fill('#newBoitePn', 'ESSAI-100');
  await page.fill('#newBoiteFonction', 'ESSAI');
  await page.fill('#newBoiteDs', 'ESSAI-150');
  await page.fill('#newBoitePorteur', 'NH90');
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
  vrai('porteur repris', creee.indexOf('NH90') !== -1);
  vrai('statut repris', creee.indexOf('Validé') !== -1);
  vrai('niveau repris', creee.indexOf('Qualified to NH90') !== -1);
  // L'URL saisie devient bien une balise <img> : la photo vient d'un lien,
  // pas d'un dessin fabriqué. (Elle ne se charge pas ici : domaine fictif.)
  eq('la photo est rendue depuis l\'URL saisie',
     await page.locator('#slideOverBody img[src="https://exemple.fr/photo.jpg"]').count(), 1);
  await fermerFiche(page);
  eq('11 boîtes', await page.locator('.carte').count(), 11);

  // On la retire pour ne pas fausser la suite.
  page.once('dialog', function (d) { d.accept(); });
  await ouvrirFiche(page, 'ESSAI-100');
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  await page.locator('#slideOverBody [data-action="supprimer-boite"]').click();
  await page.waitForTimeout(900);
  eq('retour à 10 boîtes', await page.locator('.carte').count(), 10);
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
  eq('le bloc général s\'appelle « Boîte »',
     (await texte(page, '#slideOverBody .bloc-general h3')).trim(), 'Boîte');

  const blocHarnais = page.locator('.bloc-type-harnais').first();
  const txtHarnais = await blocHarnais.evaluate(function (el) { return el.textContent; });
  vrai('le harnais affiche sa référence', txtHarnais.indexOf('HRN-2251-A') !== -1);
  faux('le harnais n\'affiche pas de longueur', txtHarnais.indexOf('Longueur') !== -1);
  faux('ni de masse', txtHarnais.indexOf('Masse') !== -1);
  faux('ni de qualification', txtHarnais.indexOf('Qualif') !== -1);
  faux('ni de composants', txtHarnais.indexOf('Composants STD') !== -1);
  vrai('le harnais propose la duplication',
       await blocHarnais.locator('[data-action="dupliquer-nom"]').count() === 1);

  const blocStruct = page.locator('.bloc-type-structure').first();
  const txtStruct = await blocStruct.evaluate(function (el) { return el.textContent; });
  vrai('la structure affiche sa longueur', txtStruct.indexOf('Longueur') !== -1);
  vrai('et son nombre de pas', txtStruct.indexOf('Nombre de pas') !== -1);
  faux('la structure n\'a pas de référence', txtStruct.indexOf('Référence') !== -1);

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
  bloc('Pondération en direct');
  await page.locator('#compareResult [data-action="ouvrir-reglages"]').click();
  await page.waitForSelector('#reglagesModal.show');
  // La comparaison doit rester visible derrière : c'est tout l'intérêt.
  vrai('la comparaison reste à l\'écran',
       await page.locator('#compareModal.show').count() === 1);
  await page.waitForTimeout(400);
  vrai('le panneau s\'ouvre sur la portée de la comparaison',
       (await texte(page, '#reglagesPortee')).indexOf('Harnais') !== -1);
  eq('plus d\'onglets de portée : le contexte décide',
     await page.locator('.onglet-reglage').count(), 0);
  eq('aucun curseur : le harnais n\'a qu\'un critère',
     await page.locator('.curseur').count(), 0);
  vrai('et le panneau l\'explique',
       (await texte(page, '#reglagesCurseurs')).indexOf('Un seul critère') !== -1);
  eq('plus de réglages rapides', await page.locator('[data-action="appliquer-preset"]').count(), 0);
  vrai('aperçu en direct présent', await page.locator('.apercu-liste li').count() >= 1);

  await ecranPropre(page);

  // La structure, elle, s'arbitre : c'est là que les curseurs vivent.
  bloc('Pondération : le total reste à 100 %');
  await ouvrirFiche(page, '332P20001');
  await page.locator('.bloc-type-structure [data-action="comparer-nom"]').first().click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(400);
  await page.locator('#compareResult [data-action="ouvrir-reglages"]').click();
  await page.waitForSelector('#reglagesModal.show');
  await page.waitForTimeout(400);

  const lireTotal = async function () {
    return Number((await texte(page, '.reglage-total')).replace(/\D/g, ''));
  };
  const lireParts = async function () {
    return await page.locator('.reglage-part').evaluateAll(function (els) {
      return els.map(function (e) { return Number(e.textContent.replace(/\D/g, '')); });
    });
  };

  eq('8 curseurs pour la structure', await page.locator('.curseur').count(), 8);
  eq('total à 100 au départ', await lireTotal(), 100);

  const partsAvant = await lireParts();
  await page.locator('.curseur').first().fill('80');
  await page.dispatchEvent('.curseur', 'input');
  await page.waitForTimeout(400);
  const partsApres = await lireParts();
  eq('total toujours 100 après déplacement', await lireTotal(), 100);
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


  // ---------------------------------------------------------------
  bloc('Duplication');
  await ecranPropre(page);
  page.once('dialog', function (d) { d.accept('COPIE-1'); });
  await page.locator('.carte', { hasText: '332P20001' })
            .locator('[data-action="dupliquer-boite"]').click({ force: true });
  await page.waitForTimeout(1000);
  eq('boîte dupliquée depuis la liste', await page.locator('.carte').count(), 11);
  vrai('le vocabulaire dit « boîte »',
       (await texte(page, '#bandeauMessage')).indexOf('Boîte dupliquée') !== -1);
  vrai('la copie apparaît', await page.locator('.carte', { hasText: 'COPIE-1' }).count() === 1);

  await ouvrirFiche(page, 'COPIE-1');
  faux('pas de duplication de boîte dans son bloc',
       (await texte(page, '.bloc-general')).indexOf('Dupliquer') !== -1);
  const avantDup = await page.locator('#slideOverBody .bloc').count();
  page.once('dialog', function (d) { d.accept('SE-COPIE'); });
  await page.locator('.bloc-type-structure [data-action="dupliquer-nom"]').first().click();
  await page.waitForTimeout(1200);
  eq('sous-ensemble dupliqué', await page.locator('#slideOverBody .bloc').count(), avantDup + 1);
  vrai('avec le PN saisi', (await texte(page, '#slideOverBody')).indexOf('SE-COPIE') !== -1);
  await fermerFiche(page);

  bloc('Catalogue et création typée');
  if (!(await page.locator('#detailsSlideOver.show').count())) await ouvrirFiche(page, '332P20001');
  // Le catalogue n'existe que là où il y a des composants : la structure.
  await page.locator('.bloc-type-structure [data-action="ouvrir-catalogue"]').first().click();
  await page.waitForSelector('#catalogueModal.show');
  await page.fill('#catSearch', 'diode');
  await page.waitForTimeout(350);
  eq('un seul résultat', await page.locator('.ligne-catalogue').count(), 1);
  await page.locator('.ligne-catalogue').click();
  await page.waitForTimeout(900);
  const puces = await page.locator('.bloc-type-structure .puce')
    .evaluateAll(function (e) { return e.map(function (x) { return x.textContent; }); });
  vrai('le composant affiché est celui ajouté',
       puces.some(function (p) { return p.indexOf('Diode') !== -1; }));

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
  eq('aucune boîte créée', await page.locator('.carte').count(), 11);

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
  await page.waitForSelector('#reglagesModal.show');
  await page.waitForTimeout(400);
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
  await fermerModale(page, 'compareModal');
  // La structure : c'est elle qui porte les curseurs.
  await page.locator('.bloc-type-structure [data-action="comparer-nom"]').first().click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(400);

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

/**
 * Test de bout en bout dans un vrai Chromium.
 * Charge build/demo.html comme le ferait l'hôte Artifact et pilote l'interface.
 *   node test/test-navigateur.js
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
function bloc(t) { console.log('\n' + t); }

/** Reproduit l'enveloppe que l'hôte Artifact ajoute autour du fichier. */
function pageComplete() {
  return '<!doctype html><html><head><meta charset="utf-8">' +
         '<meta name="viewport" content="width=device-width, initial-scale=1">' +
         '<style>body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style>' +
         '</head><body>' + fs.readFileSync(path.join(RACINE, 'build/demo.html'), 'utf8') +
         '</body></html>';
}

const texteDe = function (page, selecteur) {
  return page.locator(selecteur).evaluate(function (el) { return el.textContent; });
};

async function ouvrirFiche(page, pn) {
  await page.locator('.product-card', { hasText: pn })
            .getByRole('button', { name: 'Fiche complète' }).click();
  await page.waitForSelector('#detailsSlideOver.show');
  await page.waitForTimeout(300);
}
async function fermerFiche(page) {
  await page.locator('#detailsSlideOver .btn-close').click();
  await page.waitForFunction(function () {
    var el = document.getElementById('detailsSlideOver');
    return el && !el.classList.contains('show');
  }, null, { timeout: 5000 });
  await page.waitForTimeout(400);
}
async function fermerModale(page, id) {
  await page.locator('#' + id + ' .btn-close').click();
  await page.waitForFunction(function (i) {
    var el = document.getElementById(i);
    return el && !el.classList.contains('show');
  }, id, { timeout: 5000 });
  await page.waitForTimeout(400);
}

(async function () {
  const navigateur = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await navigateur.newPage({ viewport: { width: 1280, height: 900 } });

  // Une exception non rattrapée est un défaut. Les console.error émis
  // volontairement par signalerErreur pendant les scénarios de panne et de
  // validation n'en sont pas : on les compte à part.
  const exceptions = [];
  const diagnostics = [];
  const ATTENDUS = /Panne simulée|existe déjà|est obligatoire/;
  page.on('pageerror', function (e) { exceptions.push(e.message); });
  page.on('console', function (m) {
    if (m.type() !== 'error') return;
    (ATTENDUS.test(m.text()) ? diagnostics : exceptions).push('console: ' + m.text());
  });

  await page.setContent(pageComplete(), { waitUntil: 'load' });
  await page.waitForSelector('.product-card', { timeout: 8000 });

  // ---------------------------------------------------------------
  bloc('Chargement');
  eq('10 assemblages affichés', await page.locator('.product-card').count(), 10);
  eq('indicateur « boîtes »', await page.locator('#kpiBoites').innerText(), '10');
  vrai('indicateur « références »',
       parseInt(await page.locator('#kpiNoms').innerText(), 10) > 10);
  eq('« boîtes validées » : 5 sur 10 (B3)',
     await texteDe(page, '#kpiVal'), '5 (50 %)');
  eq('indicateur de chargement masqué', await page.locator('#loading').isVisible(), false);
  vrai('onglets par fonction', await page.locator('.tab-pill').count() >= 8);
  vrai('badges de statut rendus', await page.locator('.status-badge').count() >= 8);

  // ---------------------------------------------------------------
  bloc('Onglets, compteurs et recherche (B5, F5)');
  const compteurs = async function () {
    const pastilles = await page.locator('.tab-pill').all();
    let total = parseInt(await pastilles[0].locator('.tab-count').innerText(), 10);
    let somme = 0;
    for (let i = 1; i < pastilles.length; i++) {
      somme += parseInt(await pastilles[i].locator('.tab-count').innerText(), 10);
    }
    return { total: total, somme: somme, cartes: await page.locator('.product-card').count() };
  };
  let c = await compteurs();
  eq('somme des onglets = « Toutes »', c.somme, c.total);

  await page.fill('#searchBar', '332P2');
  await page.waitForTimeout(350);
  c = await compteurs();
  eq('compteur cohérent avec les cartes', c.total, c.cartes);
  eq('somme toujours cohérente', c.somme, c.total);
  vrai('la recherche a filtré', c.cartes < 10);

  await page.fill('#searchBar', 'commentaires');
  await page.waitForTimeout(350);
  eq('un nom de colonne ne ramène plus tout', await page.locator('.product-card').count(), 0);

  await page.fill('#searchBar', 'harnais console');
  await page.waitForTimeout(350);
  vrai('recherche multi-mots', await page.locator('.product-card').count() >= 1);

  await page.fill('#searchBar', '');
  await page.waitForTimeout(350);
  eq('recherche effacée : 10 cartes', await page.locator('.product-card').count(), 10);

  await page.locator('.tab-pill', { hasText: 'APU' }).first().click();
  await page.waitForTimeout(250);
  eq('un seul onglet actif', await page.locator('.tab-pill.active').count(), 1);
  eq("l'onglet APU ne montre que ses 2 assemblages",
     await page.locator('.product-card').count(), 2);

  await page.locator('.tab-pill', { hasText: 'Toutes' }).click();
  await page.waitForTimeout(250);
  eq('retour sur « Toutes »', await page.locator('.product-card').count(), 10);

  // ---------------------------------------------------------------
  bloc('Équivalences (F4)');
  await ouvrirFiche(page, '332P20001');
  await page.locator('#slideOverBody [data-action="comparer-nom"]').first().click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(300);
  vrai('des résultats sont proposés',
       await page.locator('#compareResult .component-block').count() >= 1);
  const texteCompare = await texteDe(page, '#compareResult');
  vrai('un score est affiché', /%/.test(texteCompare));
  vrai('la couverture est affichée', /couverture/i.test(texteCompare));
  vrai('les icônes d\'état sont rendues', /[✓✗≈–]/.test(texteCompare));
  vrai('un critère non mesurable est affiché, pas silencieux',
       texteCompare.indexOf('hors calcul') !== -1);
  await fermerModale(page, 'compareModal');

  await page.locator('.product-card', { hasText: '332P20001' })
            .getByRole('button', { name: 'Équivalences' }).click()
            .catch(async function () {
              await fermerFiche(page);
              await page.locator('.product-card', { hasText: '332P20001' })
                        .getByRole('button', { name: 'Équivalences' }).click();
            });
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(300);
  vrai('équivalences au niveau assemblage',
       await page.locator('#compareResult .component-block').count() >= 1);
  vrai('blocs commun / manquant / en plus',
       await page.locator('#compareResult .bloc-ensemble').count() >= 1);
  await fermerModale(page, 'compareModal');

  // ---------------------------------------------------------------
  bloc('Fiche et édition');
  if (!(await page.locator('#detailsSlideOver.show').count())) await ouvrirFiche(page, '332P20001');
  eq('titre du panneau', await texteDe(page, '#slideOverTitle'), '332P20001');
  eq('1 bloc général + 3 sous-ensembles',
     await page.locator('#slideOverBody .component-block').count(), 4);

  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  vrai('champs d\'édition affichés', await page.locator('.champ-boite').count() > 0);
  await page.locator('.champ-boite[data-champ="DS/VCI Associé"]').fill('TEST-42');
  await page.locator('#slideOverBody [data-action="sauver-boite"]').click();
  await page.waitForTimeout(700);
  vrai('modification visible dans la fiche',
       (await texteDe(page, '#slideOverBody')).indexOf('TEST-42') !== -1);
  vrai('modification propagée à la carte',
       (await texteDe(page, '.product-card:has-text("332P20001")')).indexOf('TEST-42') !== -1);

  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  await page.locator('#slideOverBody [data-action="annuler-boite"]').click();
  eq('annulation d\'édition (nouveau)', await page.locator('.champ-boite').count(), 0);

  // ---------------------------------------------------------------
  bloc('Valeur piégée : guillemet, apostrophe, balise (F1)');
  const PIEGE = 'Entraxe 5" d\'origine <b>gras</b>';
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  await page.locator('.champ-boite[data-champ="Commentaires libres"]').fill(PIEGE);
  await page.locator('#slideOverBody [data-action="sauver-boite"]').click();
  await page.waitForTimeout(700);
  vrai('la valeur est affichée en entier',
       (await texteDe(page, '#slideOverBody')).indexOf(PIEGE) !== -1);
  eq('le <b> n\'est pas interprété',
     await page.locator('#slideOverBody b:text-is("gras")').count(), 0);
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  eq('elle revient intacte dans le champ',
     await page.locator('.champ-boite[data-champ="Commentaires libres"]').inputValue(), PIEGE);
  await page.locator('#slideOverBody [data-action="annuler-boite"]').click();

  // ---------------------------------------------------------------
  bloc('Champs multi-valeurs');
  const avantPuces = await page.locator('#slideOverBody .std-chip').count();
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  await page.locator('.saisie-multi[data-champ="Porteur"]').fill('NH90');
  await page.locator('#slideOverBody [data-action="ajouter-multi-boite"]').click();
  await page.waitForTimeout(700);
  vrai('porteur ajouté',
       (await texteDe(page, '#slideOverBody')).indexOf('NH90') !== -1);
  vrai('nouvelle puce', await page.locator('#slideOverBody .std-chip').count() > avantPuces);

  // ---------------------------------------------------------------
  bloc('Catalogue (B1)');
  await page.locator('#slideOverBody [data-action="ouvrir-catalogue"]').first().click();
  await page.waitForSelector('#catalogueModal.show');
  await page.waitForTimeout(300);
  eq('catalogue complet', await page.locator('.ligne-catalogue').count(), 16);
  await page.fill('#catSearch', 'diode');
  await page.waitForTimeout(350);
  eq('un seul résultat', await page.locator('.ligne-catalogue').count(), 1);
  vrai('c\'est bien la diode',
       (await texteDe(page, '.ligne-catalogue')).indexOf('Diode') !== -1);
  await page.locator('.ligne-catalogue').click();
  await page.waitForTimeout(800);
  const puces = await page.locator('#slideOverBody .std-chip').evaluateAll(
    function (els) { return els.map(function (e) { return e.textContent; }); });
  vrai('le composant AJOUTÉ est celui qui était AFFICHÉ',
       puces.some(function (p) { return p.indexOf('Diode') !== -1; }));
  eq('et pas « Bouton poussoir » à sa place',
     puces.filter(function (p) { return p.indexOf('Pushrod') !== -1; }).length, 0);

  // ---------------------------------------------------------------
  bloc('Ajout et suppression de sous-ensemble');
  const avantBlocs = await page.locator('#slideOverBody .component-block').count();
  await page.locator('[data-action="nouveau-sous-ensemble"]').click();
  await page.waitForSelector('#newSousEnsModal.show');
  await page.fill('#newEnsType', 'Capot');
  await page.fill('#newEnsPn', 'CAP-001');
  await page.locator('[data-action="creer-sous-ensemble"]').click();
  await page.waitForTimeout(800);
  eq('sous-ensemble ajouté',
     await page.locator('#slideOverBody .component-block').count(), avantBlocs + 1);
  vrai('visible dans la fiche',
       (await texteDe(page, '#slideOverBody')).indexOf('CAP-001') !== -1);

  // ---------------------------------------------------------------
  bloc('Export CSV (B4)');
  // Le commentaire piégé posé plus haut contient un guillemet et une apostrophe.
  await page.locator('[data-action="exporter-bom"]').click();
  await page.waitForSelector('#demoCsvModal.show');
  await page.waitForTimeout(300);
  const meta = await texteDe(page, '#demoCsvMeta');
  const csv = await texteDe(page, '#demoCsvContenu');
  vrai('le BOM UTF-8 est présent', meta.indexOf('BOM UTF-8 présent') !== -1);
  vrai('nom de fichier correct', meta.indexOf('BOM_332P20001.csv') !== -1);
  vrai('en-tête de colonnes', csv.indexOf('"Type";"PN du type"') !== -1);
  vrai('les accents sont intacts', /é|è/.test(csv));
  vrai('les sous-ensembles sont présents', csv.indexOf('Harnais') !== -1);
  vrai('les composants multi-lignes sont aplatis', csv.indexOf(' / ') !== -1);
  await fermerModale(page, 'demoCsvModal');

  // ---------------------------------------------------------------
  bloc('Panne serveur (B2)');
  await fermerFiche(page);
  await page.check('#demoPanne');
  await ouvrirFiche(page, '332P20001');
  await page.locator('#slideOverBody [data-action="editer-boite"]').click();
  await page.locator('.champ-boite[data-champ="DS/VCI Associé"]').fill('NE-DOIT-PAS-PASSER');
  await page.locator('#slideOverBody [data-action="sauver-boite"]').click();
  await page.waitForSelector('#bandeauMessage', { state: 'visible', timeout: 5000 });
  const bandeau = await texteDe(page, '#bandeauMessage');
  vrai('un bandeau d\'erreur apparaît', bandeau.indexOf('Échec') !== -1);
  vrai('il dit que rien n\'a été enregistré', bandeau.indexOf("n'a PAS été enregistrée") !== -1);
  eq('aucun indicateur ne reste à tourner', await page.locator('.mini-spinner').count(), 0);
  vrai('la donnée n\'a pas été modifiée',
       (await texteDe(page, '#slideOverBody')).indexOf('NE-DOIT-PAS-PASSER') === -1);
  await fermerFiche(page);
  await page.uncheck('#demoPanne');

  // ---------------------------------------------------------------
  bloc('Validation serveur');
  await page.locator('.tab-pill', { hasText: 'Toutes' }).click();   // état déterministe
  await page.waitForTimeout(250);
  await page.locator('.btn-new-boite').click();
  await page.waitForSelector('#newBoiteModal.show');
  await page.locator('[data-action="creer-boite"]').click();     // PN vide
  await page.waitForTimeout(400);
  vrai('PN vide refusé',
       (await texteDe(page, '#bandeauMessage')).indexOf('obligatoire') !== -1);
  vrai('sans aller-retour serveur', await page.locator('#newBoiteModal.show').count() === 1);

  await page.fill('#newBoitePn', '332P20001');                   // PN déjà pris
  await page.locator('[data-action="creer-boite"]').click();
  await page.waitForTimeout(800);
  vrai('PN en double refusé',
       (await texteDe(page, '#bandeauMessage')).indexOf('existe déjà') !== -1);
  eq('aucune boîte créée', await page.locator('.product-card').count(), 10);

  await page.locator('.btn-new-boite').click();
  await page.waitForTimeout(400);
  await page.fill('#newBoitePn', 'ESSAI-001');
  await page.fill('#newBoiteFonction', 'ESSAI');
  await page.locator('[data-action="creer-boite"]').click();
  await page.waitForTimeout(800);
  eq('création valide acceptée', await page.locator('.product-card').count(), 11);

  // ---------------------------------------------------------------
  bloc('Recherche par composants');
  await page.locator('[data-action="ouvrir-multi-recherche"]').click();
  await page.waitForSelector('#multiSearchModal.show');
  await page.fill('#multiSearchInputSelect', 'Bouton poussoir | Push button (ECS 7251)');
  await page.locator('[data-action="ajouter-chip"]').click();
  await page.waitForTimeout(200);
  eq('composant retenu', await page.locator('#multiSearchPillsContainer .multi-search-pill').count(), 1);
  await page.locator('[data-action="lancer-multi-recherche"]').click();
  await page.waitForTimeout(600);
  const filtrees = await page.locator('.product-card').count();
  vrai('filtre appliqué', filtrees > 0 && filtrees < 11);
  vrai('filtre actif affiché et retirable',
       await page.locator('#filtreActif [data-action="retirer-filtre"]').count() === 1);
  await page.locator('[data-action="vider-filtre"]').click();
  await page.waitForTimeout(400);
  await page.locator('.tab-pill', { hasText: 'Toutes' }).click();
  await page.waitForTimeout(250);
  eq('filtre vidé', await page.locator('.product-card').count(), 11);

  // ---------------------------------------------------------------
  bloc('Affichage mobile');
  await page.setViewportSize({ width: 400, height: 800 });
  await page.waitForTimeout(500);
  let largeurs = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth };
  });
  vrai('pas de défilement horizontal (grille)', largeurs.doc <= largeurs.vue + 1);
  await ouvrirFiche(page, '332P20001');
  largeurs = await page.evaluate(function () {
    return { doc: document.documentElement.scrollWidth, vue: window.innerWidth,
             panneau: document.getElementById('detailsSlideOver').getBoundingClientRect().width };
  });
  vrai('pas de défilement horizontal (fiche ouverte)', largeurs.doc <= largeurs.vue + 1);
  vrai('le panneau tient dans l\'écran', largeurs.panneau <= largeurs.vue);
  await fermerFiche(page);
  await page.setViewportSize({ width: 1280, height: 900 });

  // ---------------------------------------------------------------
  bloc('Réinitialisation de la démo');
  await page.locator('#demoReset').click();
  await page.waitForTimeout(900);
  eq('retour au jeu initial', await page.locator('.product-card').count(), 10);

  // ---------------------------------------------------------------
  bloc('Captures');
  // Haut de page et bandeau masqué, sinon la capture rate l'en-tête et les KPI.
  await page.evaluate(function () {
    window.scrollTo(0, 0);
    var b = document.getElementById('bandeauMessage');
    if (b) b.style.display = 'none';
  });
  await page.waitForTimeout(400);
  vrai('en-tête et KPI visibles en haut de page',
       await page.locator('.hero-panel').isVisible());
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-grille.png') });
  await ouvrirFiche(page, '332P20001');
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-fiche.png') });
  await page.locator('#slideOverBody [data-action="comparer-nom"]').first().click();
  await page.waitForSelector('#compareModal.show');
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(RACINE, 'build/apercu-equivalences.png') });
  console.log('  3 captures écrites dans build/');

  eq('aucune exception JavaScript non rattrapée', exceptions, []);
  // Deux et non trois : le PN vide est rejeté côté client, sans aller-retour
  // serveur. Seules la panne simulée et le PN en double atteignent le serveur.
  eq('les 2 échecs serveur provoqués sont journalisés', diagnostics.length, 2);

  await navigateur.close();
  console.log('\n' + (ko === 0 ? V : R) + ok + ' OK, ' + ko + ' KO' + Z);
  process.exit(ko === 0 ? 0 : 1);
})().catch(function (e) {
  console.error('\n' + R + 'Échec du test navigateur : ' + Z + e.message);
  process.exit(1);
});

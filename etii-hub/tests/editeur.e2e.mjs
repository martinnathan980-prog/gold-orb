// L'éditeur de communication — exécuter depuis etii-hub/ avec un serveur :
//   python3 -m http.server 8111 &   puis   node tests/editeur.e2e.mjs
// Passe en mode édition, compose une communication de cinq blocs, vérifie
// l'aperçu, met en page les blocs (listes de gauche, poignées de l'aperçu,
// clavier), publie (le serveur de test n'a pas de base partagée : la
// publication reste dans ce navigateur), recharge, retrouve la mise en
// page dans la lecture, la modifie depuis sa lecture, la supprime.
// Le brouillon est rangé par page : la clé porte le pôle (ici ETII).

import { chromium } from 'playwright';

const B = process.env.BASE || 'http://localhost:8111';
let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const err = [];
page.on('pageerror', (e) => err.push(e.message));

/* Le centre d'une poignée, en coordonnées de la fenêtre. */
async function centre(selecteur) {
  await page.locator(selecteur).scrollIntoViewIfNeeded();
  const r = await page.locator(selecteur).boundingBox();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
}

console.log('== Le Communication Center ==');
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
/* Un départ propre : ni brouillon, ni modification, ni mode édition
   restés d'un passage précédent. */
await page.evaluate(() => {
  try {
    for (const k of Object.keys(localStorage)) {
      if (/^etii:(editeur\.communication|modifications:|edition\.)/.test(k)) localStorage.removeItem(k);
    }
  } catch (_e) { /* sans stockage */ }
});
await page.reload({ waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
const h = await page.evaluate(() => ({
  flux: document.querySelector('.kiosque__flux').getBoundingClientRect().height,
  lecture: document.querySelector('.kiosque__lecture').getBoundingClientRect().height
}));
t('la liste et la lecture ont la même hauteur', Math.abs(h.flux - h.lecture) < 2, JSON.stringify(h));
t('aucune légende posée sur l’image de bannière', (await page.locator('.kiosque__image figcaption').count()) === 0);
const avant = await page.locator('.kiosque__carte').count();

console.log('\n== Le mode édition ==');
t('hors mode édition, aucune commande : ni « Ajouter une communication », ni « Modifier »',
  !(await page.locator('.kiosque__ajout').isVisible()) && !(await page.locator('.kiosque__edition').isVisible())
  && (await page.locator('.bascule-edition').innerText()).includes('Modifier'));
await page.click('.bascule-edition');
await page.waitForTimeout(300);
t('« Modifier » allume le mode édition, et le bandeau dit où partent les modifications',
  await page.evaluate(() => document.documentElement.classList.contains('mode-edition'))
  && /navigateur seulement/.test(await page.locator('.edition-bandeau').innerText())
  && (await page.locator('.bascule-edition').getAttribute('aria-pressed')) === 'true');
t('les commandes apparaissent : ajouter, et modifier la communication lue',
  (await page.locator('.kiosque__ajout').isVisible()) && (await page.locator('.kiosque__edition').isVisible()));

console.log('\n== L’éditeur ==');
await page.click('.kiosque__ajout');
await page.waitForTimeout(500);
t('la fenêtre s’ouvre avec le formulaire et l’aperçu',
  (await page.locator('.modale--editeur .editeur__formulaire').count()) === 1
  && (await page.locator('.modale--editeur .editeur__apercu-zone .kiosque__lecture').count()) === 1);
const typesTexte = await page.locator('.editeur__types').innerText();
t('le type « mot » s’appelle Édito, plus de « chef »', /Édito/.test(typesTexte) && !/chef/i.test(typesTexte));
await page.click('.modale__actions button:has-text("Publier")');
await page.waitForTimeout(400);
t('publier sans titre est refusé, avec les raisons', (await page.locator('.editeur__erreurs li').count()) >= 2 && (await page.locator('.modale').count()) === 1);

/* Le geste central de l'éditeur : cliquer un type de bloc ne doit ni rendre
   la main en haut du formulaire ni perdre le clavier. */
await page.locator('.editeur__ajout button:has-text("Chiffres clés")').scrollIntoViewIfNeeded();
const yAvant = await page.evaluate(() => document.querySelector('.modale--editeur .modale__corps').scrollTop);
await page.click('.editeur__ajout button:has-text("Chiffres clés")');
await page.waitForTimeout(400);
const apresAjout = await page.evaluate(() => ({
  y: document.querySelector('.modale--editeur .modale__corps').scrollTop,
  actif: document.activeElement ? document.activeElement.tagName : 'aucun',
  dansLaCarte: !!(document.activeElement && document.activeElement.closest('.editeur__bloc[data-index="1"]'))
}));
t('ajouter un bloc garde la place dans le formulaire et donne le clavier à la nouvelle carte',
  yAvant > 0 && apresAjout.y > 0 && apresAjout.actif !== 'BODY' && apresAjout.dansLaCarte,
  JSON.stringify({ yAvant, ...apresAjout }));
await page.click('.editeur__bloc[data-index="1"] [aria-label="Supprimer le bloc"]');
await page.waitForTimeout(250);
t('le bloc d’essai se retire', (await page.locator('.editeur__bloc').count()) === 1);

/* Le radiogroupe des types : après un changement, le clavier reste sur le
   radio coché — sinon une seule flèche fonctionne, puis le focus s'en va. */
await page.locator('input[name="editeur-type"][value="annonce"]').focus();
await page.keyboard.press('ArrowDown');
await page.waitForTimeout(300);
await page.keyboard.press('ArrowDown');
await page.waitForTimeout(300);
t('les flèches parcourent les types sans perdre le clavier',
  await page.evaluate(() => document.activeElement && document.activeElement.name === 'editeur-type'
    && document.activeElement.value === 'alerte'),
  await page.evaluate(() => (document.activeElement ? document.activeElement.value || document.activeElement.tagName : 'aucun')));
await page.locator('input[name="editeur-type"][value="annonce"]').check();
await page.waitForTimeout(300);

await page.fill('input[placeholder="Validation du jalon de définition"]', 'Nouveau banc d’essais harnais');
await page.fill('textarea[placeholder^="Une ou deux phrases"]', 'Le banc est opérationnel depuis lundi.');
await page.fill('textarea[placeholder^="-> Ce qui change"]', '-> Ce que ça change\n• Un banc dédié.\n\nV Trois harnais conformes.');
/* « 2062 » au lieu de « 2026 » épinglerait la communication en tête du fil. */
const borneDate = await page.locator('input[type="date"]').getAttribute('max');
await page.fill('input[type="date"]', '2062-09-18');
await page.click('.modale__actions button:has-text("Publier")');
await page.waitForTimeout(400);
const erreursDate = await page.locator('.editeur__erreurs li').allInnerTexts();
t('une date dans le futur est refusée, en répétant la date fautive, et le champ est borné au jour même',
  /^\d{4}-\d{2}-\d{2}$/.test(borneDate || '') && erreursDate.some((e) => /futur/.test(e) && /2062/.test(e)),
  JSON.stringify({ borneDate, erreursDate }));
await page.fill('input[type="date"]', borneDate);
await page.waitForTimeout(300);

await page.click('.editeur__ajout button:has-text("Image")');
await page.locator('input[placeholder^="https://… ou assets/img/communications"]').last().fill('assets/img/porteurs/h145.jpg');
await page.locator('input[placeholder="Un H160 sur un salon"]').last().fill('Un H145 en vol');
await page.click('.editeur__ajout button:has-text("Chiffres clés")');
await page.locator('[aria-label="Libellé du chiffre 1"]').last().fill('Harnais qualifiés');
await page.locator('[aria-label="Valeur du chiffre 1"]').last().fill('3');
await page.click('.editeur__ajout button:has-text("Pastilles")');
await page.locator('input[placeholder="H160, Lot 3, Essais"]').fill('H145, Harnais');
await page.click('.editeur__ajout button:has-text("Encadré")');
await page.locator('textarea[placeholder="Ce qu’il faut retenir."]').fill('Réservez le banc 48 h à l’avance.');
await page.waitForTimeout(500);
const apercu = page.locator('.editeur__apercu-zone');
t('l’aperçu rend le titre, l’image, les chiffres, les pastilles et l’encadré',
  /banc d’essais/i.test(await apercu.innerText())
  && (await apercu.locator('.kiosque__figure img').count()) === 1
  && (await apercu.locator('.kiosque__chiffre').count()) === 1
  && (await apercu.locator('.kiosque__pastilles li').count()) === 2
  && (await apercu.locator('.kiosque__encadre').count()) === 1);
t('le texte est typé (titre, puce, validé)',
  (await apercu.locator('.kiosque__ligne--titre').count()) === 1
  && (await apercu.locator('.kiosque__ligne--puce').count()) === 1
  && (await apercu.locator('.kiosque__ligne--valide').count()) === 1);
await page.click('.editeur__bloc:nth-of-type(5) [aria-label="Monter le bloc"]');
await page.waitForTimeout(200);
t('un bloc se déplace depuis la carte de gauche', (await page.locator('.editeur__bloc').nth(3).innerText()).includes('Encadré'));

console.log('\n== La mise en page ==');
t('chaque bloc rendu porte un cadre d’édition avec ses poignées',
  (await apercu.locator('.kiosque__bloc.editeur__cadre').count()) === 5
  && (await apercu.locator('.editeur__cadre .editeur__poignee--deplacer').count()) === 5
  && (await apercu.locator('.editeur__cadre .editeur__poignee--largeur').count()) === 5
  && (await apercu.locator('.editeur__cadre .editeur__poignee--cote').count()) === 10);
t('les cadres portent l’indice de leur carte de gauche',
  (await apercu.locator('.editeur__cadre').evaluateAll((n) => n.map((c) => c.dataset.index).join(','))) === '0,1,2,3,4');

/* Depuis la liste de gauche : l'image (bloc 2) en moitié, à droite. */
await page.locator('.editeur__bloc').nth(1).locator('.editeur__segment[aria-label="Moitié"]').click();
await page.locator('.editeur__bloc').nth(1).locator('.editeur__segment[aria-label="Calé à droite"]').click();
await page.waitForTimeout(300);
t('la liste de gauche règle la largeur et le côté ; l’aperçu suit',
  (await apercu.locator('.kiosque__bloc--moitie.kiosque__bloc--droite[data-type="image"][data-largeur="moitie"][data-cote="droite"]').count()) === 1
  && (await page.locator('.editeur__bloc').nth(1).locator('.editeur__segment[aria-pressed="true"]').allInnerTexts()).join('|') === '½|Droite');
t('la poignée de largeur d’un bloc calé à droite passe sur son bord gauche',
  (await apercu.locator('.editeur__cadre[data-index="1"]').evaluate((n) => n.classList.contains('editeur__cadre--ancre-droite'))));

/* Depuis l'aperçu, à la souris : la poignée des chiffres (bloc 3) tirée
   jusqu'au milieu de la grille → moitié. */
const grille = await apercu.locator('.kiosque__blocs').boundingBox();
let p = await centre('.editeur__cadre[data-index="2"] .editeur__poignee--largeur');
await page.mouse.move(p.x, p.y);
await page.mouse.down();
for (let i = 1; i <= 8; i += 1) await page.mouse.move(p.x + (grille.x + grille.width * 0.52 - p.x) * (i / 8), p.y);
await page.mouse.up();
await page.waitForTimeout(300);
t('tirer la poignée de largeur aimante le bloc sur la moitié',
  (await apercu.locator('.editeur__cadre[data-index="2"]').getAttribute('data-largeur')) === 'moitie'
  && (await page.locator('.editeur__bloc').nth(2).locator('.editeur__segment[aria-pressed="true"]').first().innerText()) === '½');
t('la poignée garde le clavier après le geste',
  await page.evaluate(() => document.activeElement && document.activeElement.classList.contains('editeur__poignee--largeur')));

/* Les boutons de côté : gauche, puis retour dans le flux. */
await apercu.locator('.editeur__cadre[data-index="2"] .editeur__poignee--cote[data-cote="gauche"]').click();
await page.waitForTimeout(250);
t('◧ cale le bloc à gauche', (await apercu.locator('.editeur__cadre[data-index="2"]').getAttribute('data-cote')) === 'gauche');
await apercu.locator('.editeur__cadre[data-index="2"] .editeur__poignee--cote[data-cote="gauche"]').click();
await page.waitForTimeout(250);
t('◧ une seconde fois le remet dans le flux', (await apercu.locator('.editeur__cadre[data-index="2"]').getAttribute('data-cote')) === '');

/* Au clavier : ← rétrécit, → élargit ; ↑ ↓ déplacent. */
await centre('.editeur__cadre[data-index="2"] .editeur__poignee--largeur');
await apercu.locator('.editeur__cadre[data-index="2"] .editeur__poignee--largeur').focus();
await page.keyboard.press('ArrowLeft');
await page.waitForTimeout(250);
t('← rétrécit d’un cran (moitié → tiers)', (await apercu.locator('.editeur__cadre[data-index="2"]').getAttribute('data-largeur')) === 'tiers');
await page.keyboard.press('ArrowRight');
await page.waitForTimeout(250);
await page.keyboard.press('ArrowRight');
await page.waitForTimeout(250);
t('→ → élargit (tiers → deux tiers)', (await apercu.locator('.editeur__cadre[data-index="2"]').getAttribute('data-largeur')) === 'deux-tiers');
await apercu.locator('.editeur__cadre[data-index="2"] .editeur__poignee--deplacer').focus();
await page.keyboard.press('ArrowUp');
await page.waitForTimeout(250);
t('↑ remonte le bloc, à droite comme à gauche',
  (await apercu.locator('.editeur__cadre[data-index="1"]').getAttribute('data-type')) === 'chiffres'
  && (await page.locator('.editeur__bloc').nth(1).innerText()).includes('Chiffres clés')
  && await page.evaluate(() => document.activeElement && document.activeElement.closest('.editeur__cadre') && document.activeElement.closest('.editeur__cadre').dataset.index === '1'));
await page.keyboard.press('ArrowDown');
await page.waitForTimeout(250);
t('↓ le redescend', (await apercu.locator('.editeur__cadre[data-index="2"]').getAttribute('data-type')) === 'chiffres');

/* Glisser-déposer dans l'aperçu : l'encadré (bloc 4) posé sur la moitié
   haute des chiffres (bloc 3) passe devant eux. */
p = await centre('.editeur__cadre[data-index="3"] .editeur__poignee--deplacer');
const chiffresBloc = await apercu.locator('.editeur__cadre[data-index="2"]').boundingBox();
await page.mouse.move(p.x, p.y);
await page.mouse.down();
for (let i = 1; i <= 8; i += 1) await page.mouse.move(p.x + (chiffresBloc.x + 60 - p.x) * (i / 8), p.y + (chiffresBloc.y + 12 - p.y) * (i / 8));
await page.waitForTimeout(100);
const repere = await apercu.locator('.editeur__repere:not([hidden])').count();
await page.mouse.up();
await page.waitForTimeout(300);
t('un repère d’insertion apparaît pendant le glissement', repere === 1);
t('glisser un bloc dans l’aperçu le réordonne, et la carte de gauche suit',
  (await apercu.locator('.editeur__cadre[data-index="2"]').getAttribute('data-type')) === 'encadre'
  && (await apercu.locator('.editeur__cadre[data-index="3"]').getAttribute('data-type')) === 'chiffres'
  && (await page.locator('.editeur__bloc').nth(2).innerText()).includes('Encadré')
  && (await page.locator('.editeur__bloc').nth(3).innerText()).includes('Chiffres clés'));
t('le repère a disparu', (await apercu.locator('.editeur__repere').count()) === 0);

/* Remise en ordre attendue pour la publication : chiffres en moitié
   (dans le flux), image en moitié à droite. */
await apercu.locator('.editeur__cadre[data-index="3"] .editeur__poignee--largeur').focus();
await page.keyboard.press('ArrowLeft');
await page.waitForTimeout(250);
t('le brouillon local conserve largeur et côté',
  await page.evaluate(() => {
    const b = JSON.parse(localStorage.getItem('etii:editeur.communication:ETII')).blocs;
    const image = b.find((x) => x.type === 'image');
    const chiffres = b.find((x) => x.type === 'chiffres');
    return image.largeur === 'moitie' && image.cote === 'droite' && chiffres.largeur === 'moitie' && chiffres.cote === '';
  }));

console.log('\n== La publication ==');
await page.click('.modale__actions button:has-text("Publier")');
await page.waitForTimeout(1200);
t('la publication ferme la fenêtre et recharge la liste',
  (await page.locator('.modale').count()) === 0 && (await page.locator('.kiosque__carte').count()) === avant + 1);
const carte = () => page.locator('.kiosque__carte', { hasText: 'Nouveau banc d’essais harnais' });
t('la communication publiée est dans la liste, sans étiquette de brouillon',
  (await carte().count()) === 1 && (await page.locator('.kiosque__carte .badge--alerte').count()) === 0);
t('elle est rangée dans ce navigateur, comme une modification du jeu « communications »',
  await page.evaluate(() => {
    const brut = JSON.parse(localStorage.getItem('etii:modifications:communications') || '{}');
    return Object.values(brut).some((m) => m.type === 'annonce' && m.op === 'maj' && /banc d’essais/.test(m.donnees.titre));
  }));

await page.reload({ waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
t('elle survit au rechargement, et le mode édition aussi',
  (await carte().count()) === 1 && await page.evaluate(() => document.documentElement.classList.contains('mode-edition')));
await carte().first().click();
await page.waitForTimeout(800);
const lecture = page.locator('.kiosque__lecture').first();
t('la lecture retrouve la mise en page : image en moitié à droite, chiffres en moitié',
  (await lecture.locator('.kiosque__bloc--moitie.kiosque__bloc--droite[data-type="image"]').count()) === 1
  && (await lecture.locator('.kiosque__bloc--moitie[data-type="chiffres"]:not(.kiosque__bloc--droite)').count()) === 1
  && (await lecture.locator('.editeur__cadre').count()) === 0);

console.log('\n== Modifier, supprimer ==');
await page.click('.kiosque__edition button:has-text("Modifier")');
await page.waitForTimeout(600);
t('« Modifier » rouvre l’éditeur sur la communication, sans rien retaper',
  /Modifier la communication/.test(await page.locator('.modale__titre').innerText())
  && (await page.locator('.modale__actions button:text-is("Enregistrer")').count()) === 1
  && (await page.inputValue('input[placeholder="Validation du jalon de définition"]')) === 'Nouveau banc d’essais harnais'
  && (await page.locator('.modale--editeur .editeur__bloc').count()) === 5);
await page.fill('input[placeholder="Validation du jalon de définition"]', 'Nouveau banc d’essais harnais (corrigé)');
await page.waitForTimeout(300);
await page.click('.modale__actions button:text-is("Enregistrer")');
await page.waitForTimeout(1200);
t('enregistrer corrige la carte au lieu d’en ajouter une seconde',
  (await page.locator('.kiosque__carte').count()) === avant + 1
  && (await page.locator('.kiosque__carte', { hasText: '(corrigé)' }).count()) === 1);

await page.locator('.kiosque__carte', { hasText: '(corrigé)' }).first().click();
await page.waitForTimeout(600);
await page.click('.kiosque__edition .barre-edition__bouton--danger');
await page.waitForTimeout(400);
t('« Supprimer » demande confirmation', /sera retiré/.test(await page.locator('.modale__boite').last().innerText()));
await page.locator('.modale__boite').last().locator('.modale__actions .bouton--danger').click();
await page.waitForTimeout(1200);
t('confirmée, la suppression retire la carte',
  (await page.locator('.kiosque__carte').count()) === avant
  && (await page.locator('.kiosque__carte', { hasText: 'banc d’essais' }).count()) === 0);

/* Une communication du fichier se modifie de la même façon : on l'édite,
   puis on revient en arrière en retirant la modification. */
await page.locator('.kiosque__carte').first().click();
await page.waitForTimeout(600);
const titreBase = await page.locator('.kiosque__lecture-titre').first().innerText();
await page.click('.kiosque__edition button:has-text("Modifier")');
await page.waitForTimeout(600);
/* Le titre d'un édito a son propre exemple : on prend l'un ou l'autre. */
const champTitre = page.locator('.modale--editeur input[placeholder="Validation du jalon de définition"], .modale--editeur input[placeholder="Un trimestre qui se tient"]');
t('une communication du fichier s’ouvre aussi dans l’éditeur', (await champTitre.count()) === 1 && (await champTitre.inputValue()) === titreBase,
  JSON.stringify({ titreBase, champ: await champTitre.inputValue().catch(() => null) }));
await page.keyboard.press('Escape');
await page.waitForTimeout(300);

await page.click('.bascule-edition');
await page.waitForTimeout(300);
t('« Terminer » éteint le mode édition : les commandes disparaissent',
  !(await page.evaluate(() => document.documentElement.classList.contains('mode-edition')))
  && (await page.locator('.edition-bandeau').count()) === 0 && !(await page.locator('.kiosque__ajout').isVisible()));

t('aucune erreur JavaScript', err.length === 0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

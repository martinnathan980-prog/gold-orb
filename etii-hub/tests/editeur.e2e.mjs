// L'éditeur de communication — exécuter depuis etii-hub/ avec un serveur :
//   python3 -m http.server 8111 &   puis   node tests/editeur.e2e.mjs
// Compose une communication de cinq blocs, vérifie l'aperçu, publie dans
// le navigateur (aucune feuille branchée), recharge, retire.

import { chromium } from 'playwright';

const B = process.env.BASE || 'http://localhost:8111';
let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const err = [];
page.on('pageerror', (e) => err.push(e.message));

console.log('== Le Communication Center ==');
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
const h = await page.evaluate(() => ({
  flux: document.querySelector('.kiosque__flux').getBoundingClientRect().height,
  lecture: document.querySelector('.kiosque__lecture').getBoundingClientRect().height
}));
t('la liste et la lecture ont la même hauteur', Math.abs(h.flux - h.lecture) < 2, JSON.stringify(h));
t('aucune légende posée sur l’image de bannière', (await page.locator('.kiosque__image figcaption').count()) === 0);
const avant = await page.locator('.kiosque__carte').count();

console.log('\n== L’éditeur ==');
await page.click('.kiosque__ajout');
await page.waitForTimeout(500);
t('la fenêtre s’ouvre avec le formulaire et l’aperçu',
  (await page.locator('.modale--editeur .editeur__formulaire').count()) === 1
  && (await page.locator('.modale--editeur .editeur__apercu-zone .kiosque__lecture').count()) === 1);
await page.click('.modale__actions button:has-text("Publier")');
await page.waitForTimeout(400);
t('publier sans titre est refusé, avec les raisons', (await page.locator('.editeur__erreurs li').count()) >= 2 && (await page.locator('.modale').count()) === 1);

await page.fill('input[placeholder="Validation du jalon de définition"]', 'Nouveau banc d’essais harnais');
await page.fill('textarea[placeholder^="Une ou deux phrases"]', 'Le banc est opérationnel depuis lundi.');
await page.fill('textarea[placeholder^="-> Ce qui change"]', '-> Ce que ça change\n• Un banc dédié.\n\nV Trois harnais conformes.');
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
t('un bloc se déplace', (await page.locator('.editeur__bloc').nth(3).innerText()).includes('Encadré'));

await page.click('.modale__actions button:has-text("Publier")');
await page.waitForTimeout(1200);
t('la publication ferme la fenêtre et recharge la liste',
  (await page.locator('.modale').count()) === 0 && (await page.locator('.kiosque__carte').count()) === avant + 1);
t('l’entrée publiée est marquée « brouillon » (aucune feuille branchée)', (await page.locator('.kiosque__carte-local').count()) === 1);

await page.reload({ waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
t('elle survit au rechargement', (await page.locator('.kiosque__carte-local').count()) === 1);
await page.click('.kiosque__ajout');
await page.waitForTimeout(400);
await page.click('.editeur__locaux-liste button:has-text("Retirer")');
await page.waitForTimeout(700);
t('elle se retire depuis l’éditeur', (await page.locator('.kiosque__carte-local').count()) === 0);
await page.keyboard.press('Escape');

t('aucune erreur JavaScript', err.length === 0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

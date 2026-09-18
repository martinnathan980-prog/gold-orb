// Test du fichier autonome produit par tools/build-artifact.mjs.
//
//   node tools/build-artifact.mjs && node tests/bundle.e2e.mjs
//
// Ouvre le fichier en file://, SANS serveur : c'est tout l'intérêt de cette
// construction. Vérifie le rendu, la composition de chaque page et la
// navigation entre les neuf pages.

import { chromium } from 'playwright';

const FICHIER = 'file:///home/user/gold-orb/etii-hub/dist/etii-hub.html';
const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await ctx.newPage();
const err = [];
page.on('pageerror', e => err.push('PAGE: ' + e.message));
page.on('console', m => m.type() === 'error' && err.push('CONSOLE: ' + m.text()));

await page.goto(FICHIER);
await page.waitForTimeout(3000);

let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`))
                                : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };
const f = page.frameLocator('#cadre');

console.log('== Page du service, en file:// ==');
t('le titre s\'affiche', (await f.locator('h1').innerText()).includes('ETII'));
const style = await page.evaluate(() => {
  const d = document.getElementById('cadre').contentDocument;
  return { fond: getComputedStyle(d.body).backgroundColor,
           taille: getComputedStyle(d.querySelector('h1')).fontSize };
});
t('le CSS est appliqué', parseFloat(style.taille) > 30, JSON.stringify(style));

console.log('\n== L\'agenda du service ==');
const texte = await f.locator('main').innerText();
t('la frise est rendue', /agenda/i.test(texte));
t('le mot du chef est présent', /trimestre qui se tient/i.test(texte));
t('le repère « aujourd\'hui » est posé', /aujourd/i.test(texte));
t('des entrées à venir sont annoncées', /jours?/i.test(texte));

console.log('\n== La flotte ==');
t('la grille de flotte est rendue', (await f.locator('.flotte-grille').count()) > 0);
const cartes = await f.locator('.flotte-grille > *').count();
t('les onze appareils sont présents', cartes === 11, `(${cartes})`);
t('les trois catégories sont proposées',
  ['Civil', 'Militaire', 'Prototype'].every(c => texte.includes(c)));

console.log('\n== Une carte se retourne ==');
const retourner = f.locator('button').filter({ hasText: /Voir les données/ }).first();
await retourner.scrollIntoViewIfNeeded();
await retourner.click();
await page.waitForTimeout(700);
const apres = await f.locator('main').innerText();
t('la face arrière montre les deux groupes',
  /techniques/i.test(apres) && /conomiques/i.test(apres));
t('les valeurs absentes sont annoncées comme telles', /à renseigner/i.test(apres));

console.log('\n== Le suivi OTQ attend sa source ==');
t('l\'attente est annoncée honnêtement',
  /attente|raccordement|source/i.test(texte) && !/\d+,\d\s*%/.test(texte),
  'aucun chiffre ne doit être affiché');

console.log('\n== Un espace de pôle ==');
await f.locator('nav.site-nav a[href="etiia.html"]').first().click();
await page.waitForTimeout(2200);
const pole = await f.locator('main').innerText();
t('ETIIA s\'ouvre', /ETIIA/.test(await f.locator('h1').innerText()));
t('sa communication est en tête', /communication/i.test(pole));
t('son organigramme est résumé', /organigramme|squad/i.test(pole));
t('aucun indicateur n\'y figure', !/OTQ|OTD/.test(pole));

console.log('\n== La recherche ==');
await f.locator('nav.site-nav a[href="docsearch.html"]').first().click();
await page.waitForTimeout(2200);
await f.locator('#ds-champ').fill('conecteur');
await page.waitForTimeout(1100);
t('la tolérance aux fautes marche hors serveur',
  (await f.locator('#ds-resultats > *').count()) > 0);
t('les termes sont surlignés', (await f.locator('mark').count()) > 0);
const menus = await f.locator('#ds-metier, #ds-porteur, #ds-pole').count();
t('les trois menus de filtre sont présents', menus === 3, `(${menus})`);

console.log('\n== Les neuf pages s\'ouvrent ==');
for (const [lien, attendu] of [['etiie.html', 'ETIIE'], ['etiii.html', 'ETIII'],
                               ['index.html', 'ETII']]) {
  await f.locator(`nav.site-nav a[href="${lien}"]`).first().click();
  await page.waitForTimeout(1900);
  t(lien, new RegExp(attendu).test(await f.locator('h1').innerText()));
}
for (const [lien, attendu] of [['organigramme.html', 'Organigramme'],
                               ['faq.html', 'question|connaissance|FAQ']]) {
  await f.locator('nav.site-nav a[href="etiia.html"]').first().click();
  await page.waitForTimeout(1900);
  // « :visible » : les liens de FAQ vivent désormais dans des volets fermés.
  const cible = f.locator(`a[href^="${lien}"]:visible`).first();
  if (await cible.count() === 0) { t(`${lien} accessible depuis ETIIA`, false); continue; }
  await cible.click();
  await page.waitForTimeout(1900);
  const titre = await f.locator('h1').innerText();
  t(`${lien} depuis l'espace ETIIA`, new RegExp(attendu, 'i').test(titre), `("${titre}")`);
}

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

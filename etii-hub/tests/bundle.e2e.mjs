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

console.log('\n== Le Communication Center ==');
const texte = await f.locator('main').innerText();
t('le kiosque est rendu', (await f.locator('.kiosque').count()) === 1);
t('le mot du chef est en vedette', (await f.locator('.kiosque__vedette').count()) === 1 && /trimestre qui se tient/i.test(texte));
t('l\'historique est en cartes', (await f.locator('.kiosque__carte').count()) >= 3 && /historique/i.test(texte));
t('rien d\'« à venir » dans la communication', !/à venir/i.test(texte));
t('le bandeau d\'alertes est là', (await f.locator('.kiosque__alertes').count()) === 1);
const secondeEntree = f.locator('.kiosque__carte').nth(1);
const titreCarte = (await secondeEntree.locator('.kiosque__carte-titre').innerText()).trim();
await secondeEntree.click();
await page.waitForTimeout(600);
t('cliquer une carte ouvre sa lecture en fenêtre',
  (await f.locator('.modale .modale__titre').count()) === 1
  && (await f.locator('.modale .modale__titre').innerText()).trim() === titreCarte);
await page.keyboard.press('Escape');
await page.waitForTimeout(400);
t('Échap referme la lecture', (await f.locator('.modale').count()) === 0);

console.log('\n== Les porteurs ==');
t('la galerie des porteurs est rendue', (await f.locator('.porteurs__galerie').count()) > 0 && (await f.locator('.porteurs__groupe-galerie').count()) === 3);
const fiches = await f.locator('.porteurs__fiche').count();
t('les seize appareils sont présents', fiches === 16, `(${fiches})`);
t('les trois catégories sont proposées',
  ['Civil', 'Militaire', 'Prototype'].every(c => texte.includes(c)));

console.log('\n== La fiche d\'un porteur ==');
const troisieme = f.locator('.porteurs__fiche').nth(2);
await troisieme.scrollIntoViewIfNeeded();
await troisieme.click();
await page.waitForTimeout(500);
const apres = await f.locator('.porteurs__detail').innerText();
t('la fiche propose ses rubriques (technique, économie, service, sources)',
  /Technique/.test(apres) && /économie/i.test(apres) && /Données service/.test(apres) && /Sources/.test(apres));
t('les valeurs absentes sont annoncées comme telles', /à renseigner/i.test(apres));
t('la fiche suit le porteur choisi', apres.includes(await troisieme.locator('.porteurs__fiche-code').innerText()));

console.log('\n== Le suivi OTQ / OTD ==');
const zoneOtq = f.locator('#zone-otq');
t('l\'exemple est annoncé comme tel', /Données d’exemple|Données d'exemple/i.test(await zoneOtq.innerText()));
t('deux tuiles OTQ et OTD', (await zoneOtq.locator('.ind-tuile').count()) === 2);
t('le graphique est tracé', (await zoneOtq.locator('.ind-graphique svg').count()) >= 1);

console.log('\n== Un espace de pôle ==');
await f.locator('nav.site-nav a[href="etiia.html"]').first().click();
await page.waitForTimeout(2200);
const pole = await f.locator('main').innerText();
t('ETIIA s\'ouvre', /ETIIA/.test(await f.locator('h1').innerText()));
t('sa communication est en tête', (await f.locator('.kiosque').count()) === 1);
t('ses réunions sont lisibles', (await f.locator('#zone-reunions .liseuse').count()) === 1);
t('son organigramme est un arbre', (await f.locator('.arbre__carte').count()) > 3);
t('sa FAQ est lisible', (await f.locator('#zone-faq .liseuse').count()) === 1);
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

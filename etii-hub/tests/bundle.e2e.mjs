// Test du fichier autonome produit par tools/build-artifact.mjs.
//
//   node tools/build-artifact.mjs && node tests/bundle.e2e.mjs
//
// Ouvre le fichier en file://, SANS serveur : c'est tout l'intérêt de cette
// construction. Vérifie le rendu, les indicateurs, la navigation entre les
// neuf pages et la recherche.

import { chromium } from 'playwright';
const FICHIER = 'file:///home/user/gold-orb/etii-hub/dist/etii-hub.html';
const nav = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport:{width:1440,height:1000}, colorScheme:'dark' });
const page = await ctx.newPage();
const err=[];
page.on('pageerror',e=>err.push('PAGE: '+e.message));
page.on('console',m=>m.type()==='error'&&err.push('CONSOLE: '+m.text()));
await page.goto(FICHIER); await page.waitForTimeout(2800);
let ok=0,ko=0; const t=(n,c,d='')=>{c?(ok++,console.log(`  OK    ${n}`)):(ko++,console.log(`  ÉCHEC ${n} ${d}`))};
const f = page.frameLocator('#cadre');

console.log('== Tableau de bord, en file:// ==');
t('le titre s\'affiche', (await f.locator('h1').innerText()).includes('ETII'));
const style = await page.evaluate(() => {
  const d=document.getElementById('cadre').contentDocument;
  return { fond:getComputedStyle(d.body).backgroundColor,
           taille:getComputedStyle(d.querySelector('h1')).fontSize };
});
t('CSS appliqué (fond sombre)', !/255,\s*255,\s*255/.test(style.fond), JSON.stringify(style));
t('les 4 tuiles d\'indicateurs sont rendues',
  (await f.locator('#zone-indicateurs .carte').count()) >= 4,
  `(${await f.locator('#zone-indicateurs .carte').count()})`);
t('le graphique de suivi est tracé', (await f.locator('.ind-graphique__svg').count()) > 0);
t('les sparklines sont tracées', (await f.locator('.ind-spark').count()) >= 4);
t('la vue tabulaire accompagne les figures', (await f.locator('.ind-donnees').count()) > 0);
t('les 3 cartes de pôle sont présentes', (await f.locator('#zone-poles .carte').count()) === 3,
  `(${await f.locator('#zone-poles .carte').count()})`);

console.log('\n== Changement d\'indicateur ==');
const sel = f.locator('select').first();
if (await sel.count()) {
  const avant = await f.locator('.ind-graphique__svg').first().innerHTML();
  await sel.selectOption({ index: 2 }); await page.waitForTimeout(900);
  t('changer d\'indicateur redessine le graphique',
    (await f.locator('.ind-graphique__svg').first().innerHTML()) !== avant);
} else t('sélecteur d\'indicateur présent', false);

console.log('\n== Navigation vers un espace de pôle ==');
await f.locator('nav.site-nav a[href="etiia.html"]').first().click();
await page.waitForTimeout(2000);
t('ETIIA s\'ouvre', /ETIIA/.test(await f.locator('h1').innerText()));
t('le pôle a ses propres indicateurs', (await f.locator('.ind-spark').count()) >= 4);

console.log('\n== Recherche, avec facette de pôle ==');
await f.locator('nav.site-nav a[href="docsearch.html"]').first().click();
await page.waitForTimeout(2000);
await f.locator('#ds-champ').fill('conecteur'); await page.waitForTimeout(1000);
t('tolérance aux fautes hors serveur', (await f.locator('#ds-resultats > *').count()) > 0);
t('les termes sont surlignés', (await f.locator('mark').count()) > 0);
const pf = await f.locator('button.facette').filter({hasText:/ETIIA|ETIIE|ETIII/}).count();
t('la facette de pôle est proposée', pf === 3, `(${pf})`);

console.log('\n== Les neuf pages s\'ouvrent ==');
for (const [lien, attendu] of [['etiie.html','ETIIE'],['etiii.html','ETIII'],
     ['index.html','ETII']]) {
  await f.locator(`nav.site-nav a[href="${lien}"]`).first().click();
  await page.waitForTimeout(1700);
  t(`${lien}`, new RegExp(attendu).test(await f.locator('h1').innerText()));
}
// Les quatre pages transverses ne sont pas liées depuis le tableau de bord :
// on y accède par la sous-navigation d'un espace de pôle, ce qui porte
// aussi le pôle actif dans l'URL.
for (const [lien, attendu] of [['organigramme.html','Organigramme'],['reunions.html','Réunions'],
     ['faq.html','question|connaissance|FAQ'],['communication.html','Communication']]) {
  await f.locator('nav.site-nav a[href="etiia.html"]').first().click();
  await page.waitForTimeout(1700);
  const cible = f.locator(`a[href^="${lien}"]`).first();
  if (await cible.count() === 0) { t(`${lien} accessible depuis ETIIA`, false); continue; }
  await cible.click();
  await page.waitForTimeout(1700);
  const titre = await f.locator('h1').innerText();
  t(`${lien} depuis l'espace ETIIA`, new RegExp(attendu,'i').test(titre), `("${titre}")`);
}

t('aucune erreur JavaScript', err.length===0, err.slice(0,3).join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close(); process.exit(ko?1:0);

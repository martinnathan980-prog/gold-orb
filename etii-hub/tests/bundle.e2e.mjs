// Test du fichier autonome produit par tools/build-artifact.mjs.
//
//   node tools/build-artifact.mjs && node tests/bundle.e2e.mjs
//
// Ouvre le fichier en file://, SANS serveur : c'est tout l'intérêt de cette
// construction. Vérifie le rendu, la composition de chaque page et la
// navigation entre les neuf pages.

import { chromium } from 'playwright';
import { statSync } from 'node:fs';

// Le dist du dépôt où vit ce test, pas un chemin absolu : le test doit
// tourner tel quel dans un worktree ou un clone ailleurs.
const CHEMIN = new URL('../dist/etii-hub.html', import.meta.url);
const FICHIER = CHEMIN.href;
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

// Le plafond de publication est de 16 Mo ; la marge de 15 Mo est la règle du
// projet. Le poids est surtout fait d'images intégrées, et un module ajouté à
// palette.js — chargée par les huit pages — peut faire entrer les photos d'un
// jeu dans des pages qui ne les affichent pas : mesuré une fois à +2,8 Mo.
// Sans ce contrôle, le dépassement ne se voit qu'au refus de publication.
console.log('== Poids du fichier autonome ==');
const mo = statSync(CHEMIN).size / (1024 * 1024);
t(`le fichier autonome pèse ${mo.toFixed(1)} Mo`, mo < 15, '(plafond du projet : 15 Mo)');

console.log('\n== Page du service, en file:// ==');
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
t('le mot du chef ouvre la lecture', (await f.locator('.kiosque__lecture').count()) === 1
  && /trimestre qui se tient/i.test(await f.locator('.kiosque__lecture-titre').innerText()));
t('la liste est à côté de la lecture', (await f.locator('.kiosque__flux .kiosque__carte').count()) >= 3);
t('rien d\'« à venir » dans la communication', !/à venir/i.test(await f.locator('#zone-communication').innerText()));
t('les prochains rendez-vous ont leur bloc, « À venir »', (await f.locator('#zone-agenda .agenda__rdv').count()) >= 1);
t('le bandeau d\'alertes est là', (await f.locator('.kiosque__alertes').count()) === 1);
t('les chiffres clés et la courbe sont rendus', (await f.locator('.kiosque__chiffre').count()) >= 3 && (await f.locator('.kiosque__serie .ind-spark').count()) === 1);
t('l\'image de la communication est intégrée', /^data:image/.test((await f.locator('.kiosque__image img').first().getAttribute('src')) || ''));
const secondeEntree = f.locator('.kiosque__carte').nth(1);
const titreCarte = (await secondeEntree.locator('.kiosque__carte-titre').innerText()).trim();
await secondeEntree.click();
await page.waitForTimeout(600);
t('cliquer une entrée la lit à droite',
  (await secondeEntree.getAttribute('aria-current')) === 'true'
  && (await f.locator('.kiosque__lecture-titre').innerText()).trim() === titreCarte);

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
t('la fiche suit le porteur choisi', apres.includes(await troisieme.locator('.porteurs__fiche-code').innerText()));
// Les données propres au service sont vides dans le fichier public : c'est
// dans leur onglet qu'une valeur absente doit s'annoncer « à renseigner ».
await f.locator('.porteurs__detail [data-onglet="service"]').click();
await page.waitForTimeout(300);
t('les valeurs absentes sont annoncées comme telles',
  /à renseigner/i.test(await f.locator('.porteurs__detail').innerText()));
t('la fiche se replie quand on reclique sa carte', await (async () => {
  await troisieme.click();
  await page.waitForTimeout(400);
  return (await f.locator('.porteurs__detail').count()) === 0;
})());

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
t('son sommaire a quatre entrées', (await f.locator('.sous-nav a').count()) === 4);
t('plus de section Réunions ni Porteurs du pôle', (await f.locator('#section-reunions, #zone-reunions, #section-porteurs, #zone-porteurs').count()) === 0);
t('ses repères sont calculés', (await f.locator('#zone-reperes .pole-repere').count()) === 4);
t('l’organigramme, les référents et « par porteur » sont côte à côte',
  (await f.locator('#zone-reperes .annuaire__volet').count()) === 3
  && (await f.locator('#zone-reperes [id$="-organigramme"] .annuaire__personne').count()) > 50
  && (await f.locator('#zone-reperes [id$="-referents"] .annuaire__groupe').count()) > 3
  && (await f.locator('#zone-reperes [id$="-porteurs"] .annuaire__groupe').count()) > 3);
t('une personne s’y lit en une ligne : nom et rôle, sans portrait',
  (await f.locator('#zone-reperes .annuaire__personne .annuaire__role').count()) > 50
  && (await f.locator('#zone-reperes .portrait').count()) === 0);
t('ses documents récents sont listés', (await f.locator('#zone-documents .pole-doc').count()) === 8);
t('l\'image de sa communication est intégrée', /^data:image/.test((await f.locator('.kiosque__image img, .kiosque__figure img').first().getAttribute('src')) || ''));
t('sa FAQ est lisible, sans « Toute la base »', (await f.locator('#zone-faq .liseuse').count()) === 1 && !/Toute la base/i.test(pole));
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
// L'organigramme se rejoint depuis le pied de l'équipe d'un pôle ; la base
// de connaissances n'a plus de lien dans un espace de pôle (ses questions y
// sont, avec l'expert) : on y va par « Rechercher partout ».
await f.locator('nav.site-nav a[href="etiia.html"]').first().click();
await page.waitForTimeout(1900);
const versOrganigramme = f.locator('a[href^="organigramme.html"]:visible').first();
if (await versOrganigramme.count() === 0) { t('organigramme.html accessible depuis ETIIA', false); }
else {
  await versOrganigramme.click();
  await page.waitForTimeout(1900);
  const titre = await f.locator('h1').innerText();
  t('organigramme.html depuis l\'espace ETIIA', /Organigramme/i.test(titre), `("${titre}")`);
}
await f.locator('nav.site-nav a[href="etiia.html"]').first().click();
await page.waitForTimeout(1900);
await f.locator('.palette-ouvrir').first().click();
await page.waitForTimeout(600);
await f.locator('.palette__champ').fill('Base de connaissances');
await page.waitForTimeout(900);
const versFaq = f.locator('.palette__resultat[data-href^="faq.html"]').first();
if (await versFaq.count() === 0) { t('faq.html accessible depuis « Rechercher partout »', false); }
else {
  await versFaq.click();
  await page.waitForTimeout(1900);
  const titre = await f.locator('h1').innerText();
  t('faq.html depuis « Rechercher partout »', /question|connaissance|FAQ/i.test(titre), `("${titre}")`);
}

console.log('\n== Le mode édition, hors ligne ==');
// Ouvert depuis le disque, le fichier n'a pas de base partagée : ce qu'on
// modifie reste dans ce navigateur, et le bandeau le dit.
await f.locator('nav.site-nav a[href="index.html"]').first().click();
await page.waitForTimeout(1900);
t('le bouton « Modifier » est dans la barre', (await f.locator('.bascule-edition').count()) === 1);
await f.locator('.bascule-edition').click();
await page.waitForTimeout(300);
t('le bandeau dit que les modifications restent dans ce navigateur',
  /navigateur seulement/.test(await f.locator('.edition-bandeau').innerText()));
const rdvAvant = await f.locator('#zone-agenda .agenda__rdv').count();
await f.locator('#zone-agenda .edition-ajout').click();
await page.waitForTimeout(300);
await f.locator('.modale--formulaire input').first().fill('Rendez-vous d’essai du fichier autonome');
const demain = (() => { const d = new Date(Date.now() + 86400000); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); })();
await f.locator('.modale--formulaire input[type="date"]').fill(demain);
await f.locator('.modale--formulaire .modale__actions .bouton--principal').click();
await page.waitForTimeout(1200);
t('un rendez-vous ajouté apparaît dans « À venir »',
  (await f.locator('#zone-agenda .agenda__rdv', { hasText: 'Rendez-vous d’essai' }).count()) === 1, `(${rdvAvant} avant)`);
/* Au milieu de la fenêtre : collée en haut, la carte passerait sous la
   barre du site, qui recevrait le clic. */
await f.locator('#zone-agenda .agenda__rdv', { hasText: 'Rendez-vous d’essai' }).evaluate((e) => e.scrollIntoView({ block: 'center', behavior: 'instant' }));
await page.waitForTimeout(300);
await f.locator('#zone-agenda .agenda__rdv', { hasText: 'Rendez-vous d’essai' }).locator('.barre-edition__bouton--danger').click();
await page.waitForTimeout(400);
await f.locator('.modale__boite').last().locator('.modale__actions .bouton--danger').click();
await page.waitForTimeout(1200);
t('supprimé, il disparaît', (await f.locator('#zone-agenda .agenda__rdv', { hasText: 'Rendez-vous d’essai' }).count()) === 0);
await f.locator('.bascule-edition').click();
await page.waitForTimeout(300);

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));

console.log('\n== Rechercher partout, depuis une page qui n\'affiche pas la flotte ==');
// La version autonome n'embarque par page que les jeux que ses modules
// lisent ; le sélecteur doit pourtant trouver un porteur depuis la FAQ.
await f.locator('.palette-ouvrir').first().click();
await page.waitForTimeout(600);
await f.locator('.palette__champ').fill('H160');
await page.waitForTimeout(900);
const resultats = await f.locator('.palette__resultat').allInnerTexts();
t('un porteur ressort depuis la FAQ', resultats.some((r) => /H160/.test(r) && /porteur|pôle/i.test(r)), `(${resultats.slice(0, 3).join(' / ')})`);
await f.locator('.palette__champ').fill('Personne 22');
await page.waitForTimeout(900);
// PREMIÈRE ligne, et non « quelque part dans la liste » : c'est le seul test
// d'ordre de la palette, et Entrée ouvre cette ligne-là.
t('la personne d\'abord', /Personne 22/.test(await f.locator('.palette__resultat').first().innerText()),
  `("${(await f.locator('.palette__resultat').first().innerText()).replace(/\n/g, ' | ')}")`);
await page.keyboard.press('Escape');

console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

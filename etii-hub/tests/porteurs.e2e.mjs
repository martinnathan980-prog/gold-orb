// Test de bout en bout de la galerie des porteurs, dans un vrai navigateur.
//
//   1. lancer le site :  python3 -m http.server 8111
//   2. npm install playwright
//   3. node tests/porteurs.e2e.mjs
//
// Vérifie la mise en page demandée : trois sections l'une sous l'autre —
// Civil, Militaire, Prototype —, toutes visibles, sans onglet ni filtre ;
// toute la flotte de flotte.json, chaque appareil dans la section de son
// marché ; des rangées sans carte orpheline (5 ou 3 colonnes, jamais 4) ;
// des codes de même corps dans une section ; la fiche qui se déplie sous
// la rangée de sa carte, et qu'Échap replie ; le lien #porteur=CODE ; les
// crédits de chaque photo ; le téléphone (segments entiers, sur deux
// lignes au plus) et le thème sombre.

import { chromium } from 'playwright';
const B = process.env.BASE || 'http://localhost:8111';
const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const flotte = await (await fetch(B + '/assets/data/flotte.json')).json();
const appareils = flotte.flotte.filter((a) => a && a.code);
const marches = flotte.categories.map((c) => ({ cle: c.cle, libelle: c.libelle, codes: appareils.filter((a) => a.categorie === c.cle).map((a) => a.code) }));

const ctx = await nav.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const err = []; page.on('pageerror', (e) => err.push(e.message));
await page.goto(B + '/index.html', { waitUntil: 'networkidle' });
await page.waitForSelector('#porteurs-service .porteurs__fiche');
const g = page.locator('#porteurs-service');

console.log('\n== Trois sections, sans onglet ==');
const sections = await g.locator('.porteurs__groupe-galerie').evaluateAll((s) => s.map((x) => ({
  cle: x.dataset.categorie,
  titre: x.querySelector('h3 .porteurs__groupe-galerie-nom')?.textContent.trim(),
  compte: x.querySelector('h3 .porteurs__groupe-galerie-compte')?.textContent.trim(),
  codes: Array.from(x.querySelectorAll('.porteurs__fiche')).map((b) => b.dataset.code),
  visible: x.getBoundingClientRect().height > 0 && getComputedStyle(x).display !== 'none'
})));
t('trois sections, dans l\'ordre Civil · Militaire · Prototype',
  sections.map((s) => s.titre).join(' · ') === 'Civil · Militaire · Prototype', sections.map((s) => s.titre).join(' · '));
t('les trois sont visibles en même temps', sections.length === 3 && sections.every((s) => s.visible));
t('chaque intertitre est un h3 sous le titre « Porteurs » (h2)',
  await page.evaluate(() => {
    const h2 = document.querySelector('#section-porteurs h2');
    const h3 = document.querySelectorAll('#porteurs-service .porteurs__groupe-galerie > h3');
    return Boolean(h2) && h3.length === 3;
  }));
t('plus aucun onglet ni bouton de marché',
  (await g.locator('.porteurs__marches, .porteurs__marche, .porteurs__barre [aria-pressed]').count()) === 0
  && (await g.locator('> [role="tablist"], .porteurs__galerie > [role="tablist"]').count()) === 0);
for (const m of marches) {
  const s = sections.find((x) => x.cle === m.cle);
  t(`${m.libelle} : ses ${m.codes.length} appareils, dans l'ordre du fichier`, s && s.codes.join(',') === m.codes.join(','), s ? s.codes.join(',') : 'section absente');
  t(`${m.libelle} : le compte discret dit « ${m.codes.length} appareils »`, s && s.compte === `${m.codes.length} appareils`, s && s.compte);
}
const total = await g.locator('.porteurs__fiche').count();
t(`toute la flotte est là (${appareils.length} appareils), chacun une seule fois`, total === appareils.length
  && new Set(sections.flatMap((s) => s.codes)).size === appareils.length, `(${total})`);
t('toute la gamme H publique est présente',
  ['H125', 'H130', 'H135', 'H140', 'H145', 'H160', 'H175', 'H215', 'H225',
    'H125M', 'H145M', 'H160M', 'H175M', 'H215M', 'H225M'].every((c) => appareils.some((a) => a.code === c)));
t('les démonstrateurs publics sont en Prototype, PioneerLab compris',
  ['RACER', 'DISRUPTIVELAB', 'FLIGHTLAB', 'PIONEERLAB', 'U145'].every((c) => (sections.find((x) => x.cle === 'prototype') || { codes: [] }).codes.includes(c)));
/* « Ajouter » ferme chaque section, et seulement en mode édition : plus de
   barre au-dessus de la galerie. */
const ajouts = g.locator('.porteurs__groupe-galerie > .porteurs__ajout');
t('un bouton « Ajouter » par section, invisible hors du mode édition',
  (await ajouts.count()) === 3 && (await g.locator('.porteurs__barre').count()) === 0
  && (await ajouts.evaluateAll((l) => l.every((x) => x.getBoundingClientRect().height === 0))));

console.log('\n== Les rangées et les codes ==');
/* Neuf appareils : 5 + 4 ou 3 × 3, jamais une carte seule sur sa rangée. */
const rangees = async (largeur) => {
  await page.setViewportSize({ width: largeur, height: 900 });
  await page.waitForTimeout(250);
  return page.evaluate(() => Array.from(document.querySelectorAll('#porteurs-service .porteurs__grille')).map((ul) => {
    const hauts = Array.from(ul.querySelectorAll('.porteurs__item:not(.porteurs__item--detail)')).map((li) => li.offsetTop);
    const parRangee = [...new Set(hauts)].map((h) => hauts.filter((x) => x === h).length);
    return parRangee;
  }));
};
for (const [largeur, colonnes] of [[1280, 5], [1100, 5], [960, 3], [800, 3]]) {
  const r = await rangees(largeur);
  t(`${largeur} px : ${colonnes} cartes par rangée, aucune carte seule`,
    r.every((l) => l[0] === Math.min(colonnes, l.reduce((a, b) => a + b, 0)) && (l.length === 1 || l[l.length - 1] > 1)), JSON.stringify(r));
}
await page.setViewportSize({ width: 1280, height: 900 });
await page.waitForTimeout(250);
const corps = await g.locator('.porteurs__grille').evaluateAll((uls) => uls.map((ul) =>
  [...new Set(Array.from(ul.querySelectorAll('.porteurs__fiche-code')).map((c) => getComputedStyle(c).fontSize))]));
t('dans chaque section, tous les codes ont le même corps', corps.every((l) => l.length === 1), JSON.stringify(corps));

console.log('\n== Les photos ==');
const photos = await g.locator('.porteurs__fiche-photo').evaluateAll((imgs) => imgs.map((i) => ({ src: i.getAttribute('src'), lazy: i.getAttribute('loading') })));
t('chaque vignette se charge à la demande (loading="lazy")', photos.length > 0 && photos.every((p) => p.lazy === 'lazy'));
const avecPhoto = appareils.filter((a) => a.photo);
const absentes = [];
for (const a of avecPhoto) {
  const r = await fetch(B + '/' + a.photo);
  if (!r.ok) absentes.push(a.photo);
}
t(`les ${avecPhoto.length} photos déclarées existent, en local`, absentes.length === 0 && avecPhoto.every((a) => !/^https?:/.test(a.photo)), absentes.join(', '));
t('chaque photo a son crédit (auteur, licence, page Commons)',
  avecPhoto.every((a) => a.credit && a.credit.auteur && a.credit.licence && /^https:\/\/commons\.wikimedia\.org\//.test(a.credit.page)));
t('un appareil sans photo garde sa silhouette',
  await g.locator('.porteurs__item[data-code="H140"] .porteurs__fiche-visuel svg').count() === 1);

console.log('\n== La fiche dépliée ==');
const carte = g.locator('.porteurs__fiche[data-code="H175M"]');
await carte.scrollIntoViewIfNeeded();
await carte.click();
await page.waitForTimeout(600);
const place = await page.evaluate(() => {
  const d = document.querySelector('#porteurs-service .porteurs__item--detail');
  const c = document.querySelector('#porteurs-service .porteurs__item[data-code="H175M"]');
  if (!d || !c) return null;
  return { memeListe: d.parentNode === c.parentNode, section: d.closest('.porteurs__groupe-galerie').dataset.categorie,
    sousLaCarte: d.getBoundingClientRect().top >= c.getBoundingClientRect().bottom - 1,
    titre: d.querySelector('.porteurs__titre').textContent.trim(), niveau: d.querySelector('.porteurs__titre').tagName };
});
t('la fiche s\'ouvre sous la rangée de sa carte, dans sa section', place && place.memeListe && place.sousLaCarte && place.section === 'militaire', JSON.stringify(place));
t('le code est le titre de la fiche (h4 sous l\'intertitre h3)', place && place.titre === 'H175M' && place.niveau === 'H4');
const texteFiche = await g.locator('.porteurs__detail').textContent();
t('la fiche garde ses rubriques, dimensions comprises', /Technique/.test(texteFiche) && /Dimensions/.test(texteFiche) && /Diamètre du rotor/.test(texteFiche));
t('la fiche ne mentionne pas de lien extérieur', (await g.locator('.porteurs__detail a[href^="http"]').count()) === 0);
await carte.click();
await page.waitForTimeout(400);
t('recliquer la carte replie la fiche', (await g.locator('.porteurs__detail').count()) === 0);
await carte.click();
await page.waitForTimeout(400);
await g.locator('.porteurs__detail [role="tab"]').first().focus();
await page.keyboard.press('Escape');
await page.waitForTimeout(300);
t('Échap replie la fiche et rend le focus à sa carte', (await g.locator('.porteurs__detail').count()) === 0
  && await page.evaluate(() => document.activeElement && document.activeElement.dataset.code === 'H175M'));

console.log('\n== Les crédits photos du pied de page ==');
await page.locator('[data-credits-photos]').first().click();
await page.waitForTimeout(800);
const credits = await page.locator('[role="dialog"] .porteurs__credits-nom').allTextContents();
t(`la fenêtre crédite les ${avecPhoto.length} photos de la flotte`, avecPhoto.every((a) => credits.includes(a.fiche.nom || a.code)), credits.length);
await page.keyboard.press('Escape');
await ctx.close();

console.log('\n== Arrivée par un lien #porteur= ==');
for (const code of ['H140', 'PIONEERLAB', 'U145']) {
  const c2 = await nav.newContext({ viewport: { width: 1280, height: 900 } });
  const p2 = await c2.newPage();
  const e2 = []; p2.on('pageerror', (e) => e2.push(e.message));
  await p2.goto(B + '/index.html#porteur=' + code, { waitUntil: 'networkidle' });
  await p2.waitForTimeout(2200);
  const r = await p2.evaluate((cd) => {
    const d = document.querySelector('.porteurs__detail');
    const c = document.querySelector('.porteurs__item[data-code="' + cd + '"]').getBoundingClientRect();
    return { titre: d && d.querySelector('.porteurs__titre').textContent.trim(), haut: c.top, bas: c.bottom, h: innerHeight };
  }, code);
  t(`#porteur=${code} déplie sa fiche et amène sa carte à l'écran`, r.titre === code && r.haut >= 0 && r.bas <= r.h, JSON.stringify(r));
  t(`#porteur=${code} : aucune erreur JavaScript`, e2.length === 0, e2.join(' | '));
  await c2.close();
}

console.log('\n== Téléphone (390 px) et thème sombre ==');
const mob = await nav.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'dark' });
const pm = await mob.newPage();
await pm.goto(B + '/index.html', { waitUntil: 'networkidle' });
await pm.waitForSelector('#porteurs-service .porteurs__fiche');
t('aucun défilement horizontal à 390 px', await pm.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
const mesures = await pm.evaluate(() => Array.from(document.querySelectorAll('#porteurs-service .porteurs__fiche-code')).map((c) => ({
  code: c.textContent, uneLigne: c.scrollWidth <= c.clientWidth + 1 && c.getClientRects().length === 1
})));
t('chaque code tient sur une ligne, DISRUPTIVELAB compris', mesures.every((m) => m.uneLigne), mesures.filter((m) => !m.uneLigne).map((m) => m.code).join(', '));
const deuxColonnes = await pm.evaluate(() => {
  const l = Array.from(document.querySelectorAll('#porteurs-service .porteurs__groupe-galerie[data-categorie="civil"] .porteurs__item'));
  return l.length > 1 && l[0].offsetTop === l[1].offsetTop && l[2] && l[2].offsetTop > l[0].offsetTop;
});
t('deux cartes par rangée sur téléphone', deuxColonnes);
/* Le segment tient en entier sous le code, sur deux lignes au plus : ni
   points de suspension, ni troisième ligne dans la marge du bas. */
const segments = await pm.evaluate(() => Array.from(document.querySelectorAll('#porteurs-service .porteurs__fiche-segment')).map((s) => {
  const cs = getComputedStyle(s);
  const lignes = Math.round(s.getBoundingClientRect().height / parseFloat(cs.lineHeight));
  return { code: s.closest('.porteurs__item').dataset.code, entier: s.scrollHeight <= s.clientHeight + 1, lignes, fond: parseFloat(cs.paddingBottom) };
}));
t('chaque segment tient en entier, sur deux lignes au plus', segments.every((x) => x.entier && x.lignes <= 2 && x.fond === 0),
  JSON.stringify(segments.filter((x) => !(x.entier && x.lignes <= 2 && x.fond === 0))));
/* Le contraste du compte, discret mais lisible : au moins 4,5 contre le fond. */
const contraste = await pm.evaluate(() => {
  const lum = (rgb) => {
    const [r, g, b] = rgb.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const fond = (n) => { for (let e = n; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (c && !/rgba\(0, 0, 0, 0\)|transparent/.test(c)) return c; } return 'rgb(255,255,255)'; };
  const c = document.querySelector('#porteurs-service .porteurs__groupe-galerie-compte');
  const a = lum(getComputedStyle(c).color); const b = lum(fond(c));
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
});
t('le compte reste lisible en sombre (contraste ≥ 4,5)', contraste >= 4.5, contraste.toFixed(2));
await mob.close();

t('aucune erreur JavaScript', err.length === 0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close(); process.exit(ko ? 1 : 0);

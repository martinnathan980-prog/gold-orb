// Le décor vivant de la une ETIIE (assets/js/decor.js) — exécuter depuis
// etii-hub/ avec un serveur :
//   python3 -m http.server 8111 &   puis   node tests/decor.e2e.mjs
// Le réseau de neurones bouge : les neurones dérivent, les liaisons les
// suivent, les influx courent sur le réseau. Il ne tourne pas pour rien :
// 30 images par seconde au plus, rien hors de l'écran ni onglet caché, et
// rien du tout sous « mouvement réduit ». Les décors d'ETIIA et d'ETIII,
// eux, ne chargent pas le module.

import { chromium } from 'playwright';

const B = process.env.BASE || 'http://localhost:8111';
let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const err = [];

/* L'état du dessin à un instant : les neurones, les liaisons, les influx. */
const releve = (page) => page.evaluate(() => {
  const s = document.querySelector('.page-une__decor--nerf');
  const neurones = [...s.querySelectorAll('.page-une__neurones circle')].map((c) => [+c.getAttribute('cx'), +c.getAttribute('cy')]);
  const liaisons = [...s.querySelectorAll('.page-une__liaisons line')].map((l) => ['x1', 'y1', 'x2', 'y2'].map((a) => +l.getAttribute(a)));
  return {
    vivant: s.classList.contains('page-une__decor--vivant'),
    neurones, liaisons,
    influx: [...s.querySelectorAll('.page-une__influx')].map((c) => c.getAttribute('cx') + ',' + c.getAttribute('cy')),
    smil: s.querySelectorAll('animateMotion').length,
    couleur: getComputedStyle(s).color
  };
});
const identiques = (a, b) => JSON.stringify(a) === JSON.stringify(b);

console.log('== ETIIE : le réseau vit ==');
const ctx = await nav.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', (e) => err.push(e.message));
const brut = await (await page.request.get(`${B}/etiie.html`)).text();
const placesHtml = [...brut.matchAll(/<circle cx="(-?[\d.]+)" cy="(-?[\d.]+)" r="\d+" style="--i/g)].map((m) => [+m[1], +m[2]]);
await page.goto(`${B}/etiie.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);
const a = await releve(page);
await page.waitForTimeout(1200);
const b = await releve(page);
t('le module a pris le dessin en main (plus de chemins SMIL figés)', a.vivant && a.smil === 0, JSON.stringify({ vivant: a.vivant, smil: a.smil }));
t('les neurones dérivent', !identiques(a.neurones, b.neurones));
const bouges = a.neurones.map((p, i) => Math.hypot(p[0] - placesHtml[i][0], p[1] - placesHtml[i][1]));
t('… doucement, autour de leur place (moins de 20 unités)', placesHtml.length === a.neurones.length && Math.max(...bouges) < 20,
  `(${Math.max(...bouges).toFixed(1)})`);
const places = new Set(b.neurones.map((p) => p.join(',')));
t('les liaisons suivent leurs neurones', b.liaisons.every((l) => places.has(l[0] + ',' + l[1]) && places.has(l[2] + ',' + l[3])));
t('les influx courent sur le réseau', b.influx.length >= 5 && !identiques(a.influx, b.influx), JSON.stringify(b.influx.slice(0, 3)));
t('le réseau prend la couleur du pôle', /^rgb/.test(a.couleur) && a.couleur !== 'rgb(0, 0, 0)', a.couleur);

/* Le nom reste net et rien n'est rogné : une onde de décharge tient tout
   entière dans la une, sans toucher le nom ; un influx qui passe sous le
   nom s'efface. Relevé sur une dizaine de secondes. */
const cadrer = (p) => p.evaluate(() => new Promise((fin) => {
  const tete = document.querySelector('.page-tete--une').getBoundingClientRect();
  const h = document.querySelector('#pole-titre');
  const p = h.offsetParent.getBoundingClientRect();
  const nom = { left: p.left + h.offsetLeft, top: p.top + h.offsetTop, right: p.left + h.offsetLeft + h.offsetWidth, bottom: p.top + h.offsetTop + h.offsetHeight };
  const loin = (x, y) => Math.hypot(Math.max(nom.left - x, 0, x - nom.right), Math.max(nom.top - y, 0, y - nom.bottom));
  const r = { ondes: 0, rognees: 0, surNom: 0, sousNom: 0, vifsSousNom: 0 };
  let n = 0;
  const tic = setInterval(() => {
    for (const g of document.querySelectorAll('.page-une__eclat')) {
      const o = g.querySelector('.page-une__onde');
      if (Number(g.getAttribute('opacity') || 0) < 0.05 || !(Number(o.getAttribute('r')) > 0)) continue;
      const b = o.getBoundingClientRect();
      r.ondes += 1;
      if (b.top < tete.top - 1 || b.bottom > tete.bottom + 1) r.rognees += 1;
      if (loin(b.left + b.width / 2, b.top + b.height / 2) < b.width / 2 - 1) r.surNom += 1;
    }
    for (const c of document.querySelectorAll('.page-une__influx')) {
      const b = c.getBoundingClientRect();
      if (loin(b.left + b.width / 2, b.top + b.height / 2) > 0) continue;
      r.sousNom += 1;
      if (Number(getComputedStyle(c).opacity) > 0.4) r.vifsSousNom += 1;
    }
    if (++n >= 70) { clearInterval(tic); fin(r); }
  }, 150);
}));
const cadrage = await cadrer(page);
t('des décharges, et leur onde n’est jamais rognée par la une', cadrage.ondes > 5 && cadrage.rognees === 0, JSON.stringify(cadrage));
t('ni ne touche le nom du pôle', cadrage.surNom === 0, JSON.stringify(cadrage));
t('un influx sous le nom s’efface', cadrage.vifsSousNom === 0, JSON.stringify(cadrage));

const cadence = await page.evaluate(() => new Promise((fin) => {
  const p = document.querySelector('.page-une__influx');
  let n = 0; let dernier = p.getAttribute('cx');
  const obs = new MutationObserver(() => { const v = p.getAttribute('cx'); if (v !== dernier) { n += 1; dernier = v; } });
  obs.observe(p, { attributes: true });
  setTimeout(() => { obs.disconnect(); fin(n / 2); }, 2000);
}));
t('30 images par seconde au plus', cadence > 5 && cadence <= 32, `(${cadence} i/s)`);

await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await page.waitForTimeout(700);
const h1 = await releve(page);
await page.waitForTimeout(800);
const h2 = await releve(page);
t('hors de l’écran, plus rien ne bouge', identiques(h1.neurones, h2.neurones) && identiques(h1.influx, h2.influx));
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(700);
const r1 = await releve(page);
await page.waitForTimeout(600);
t('de retour à l’écran, il repart', !identiques(r1.influx, (await releve(page)).influx));

await page.evaluate(() => {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
  document.dispatchEvent(new Event('visibilitychange'));
});
await page.waitForTimeout(300);
const c1 = await releve(page);
await page.waitForTimeout(700);
t('onglet caché : à l’arrêt', identiques(c1.influx, (await releve(page)).influx));
await page.evaluate(() => {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
  document.dispatchEvent(new Event('visibilitychange'));
});
await page.waitForTimeout(300);
const c2 = await releve(page);
await page.waitForTimeout(600);
t('onglet revenu : il repart', !identiques(c2.influx, (await releve(page)).influx));
await ctx.close();

console.log('\n== Sombre et téléphone ==');
const sombre = await (await nav.newContext({ viewport: { width: 1366, height: 900 }, colorScheme: 'dark' })).newPage();
sombre.on('pageerror', (e) => err.push('sombre: ' + e.message));
await sombre.goto(`${B}/etiie.html`, { waitUntil: 'networkidle' });
await sombre.waitForTimeout(1200);
const s1 = await releve(sombre);
await sombre.waitForTimeout(800);
t('en sombre aussi, le réseau vit', s1.vivant && !identiques(s1.influx, (await releve(sombre)).influx));
const mobile = await (await nav.newContext({ viewport: { width: 390, height: 844 } })).newPage();
mobile.on('pageerror', (e) => err.push('mobile: ' + e.message));
await mobile.goto(`${B}/etiie.html`, { waitUntil: 'networkidle' });
await mobile.waitForTimeout(1200);
t('sur téléphone, le décor reste dans la une', await mobile.evaluate(() => {
  const tete = document.querySelector('.page-tete');
  const r = tete.getBoundingClientRect();
  return getComputedStyle(tete).overflow === 'hidden' && r.left >= 0 && r.right <= innerWidth + 0.5
    && document.querySelector('.page-une__decor--vivant') !== null;
}));
const cadrageMobile = await cadrer(mobile);
t('sur téléphone aussi, les ondes tiennent dans la une, hors du nom, et les influx s’effacent sous le nom',
  cadrageMobile.ondes > 5 && cadrageMobile.rognees === 0 && cadrageMobile.surNom === 0 && cadrageMobile.vifsSousNom === 0,
  JSON.stringify(cadrageMobile));

console.log('\n== Mouvement réduit ==');
const reduit = await (await nav.newContext({ viewport: { width: 1366, height: 900 }, reducedMotion: 'reduce' })).newPage();
reduit.on('pageerror', (e) => err.push('réduit: ' + e.message));
await reduit.goto(`${B}/etiie.html`, { waitUntil: 'networkidle' });
await reduit.waitForTimeout(1200);
const m1 = await releve(reduit);
await reduit.waitForTimeout(900);
const m2 = await releve(reduit);
t('le dessin reste exactement celui de la page, immobile',
  !m1.vivant && identiques(m1.neurones, placesHtml) && identiques(m1.neurones, m2.neurones));
t('ni influx, ni traîne, ni éclat à l’écran', await reduit.evaluate(() =>
  [...document.querySelectorAll('.page-une__signaux, .page-une__eclats')].every((g) => g.getBoundingClientRect().width === 0)));

console.log('\n== Les autres décors ne changent pas ==');
for (const code of ['etiia', 'etiii']) {
  const p = await (await nav.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  p.on('pageerror', (e) => err.push(code + ': ' + e.message));
  await p.goto(`${B}/${code}.html`, { waitUntil: 'networkidle' });
  await p.waitForTimeout(800);
  t(`${code} : le module du réseau n’est pas chargé`, await p.evaluate(() =>
    !performance.getEntriesByType('resource').some((r) => /decor\.js/.test(r.name))
    && document.querySelectorAll('.page-une__decor--vivant, .page-une__decor--nerf').length === 0));
}

t('aucune erreur JavaScript', err.length === 0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

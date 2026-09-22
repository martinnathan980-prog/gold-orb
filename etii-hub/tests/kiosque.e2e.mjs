// Le kiosque de communication — exécuter depuis etii-hub/ avec un serveur :
//   python3 -m http.server 8111 &   puis   node tests/kiosque.e2e.mjs
// Clique chaque carte et vérifie que rien n'est jamais coupé : la lecture
// contient son intérieur, reste dans sa section, et la liste a la même
// hauteur qu'elle. Puis la marque de fin, la frise (rail, points, mois
// collants), le clavier, le mobile et le sombre.

import { chromium } from 'playwright';

const B = process.env.BASE || 'http://localhost:8111';
let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const err = [];
page.on('pageerror', (e) => err.push(e.message));

/* Les rectangles qui comptent, mesurés dans la page. */
const mesurer = () => page.evaluate(() => {
  const r = (e) => { const b = e.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, left: b.left, right: b.right, height: b.height }; };
  const lecture = document.querySelector('.kiosque__lecture');
  const section = lecture.closest('section');
  const suivante = section.nextElementSibling;
  return {
    lecture: r(lecture),
    interieur: r(lecture.querySelector('.kiosque__lecture-interieur')),
    flux: r(document.querySelector('.kiosque__flux')),
    section: r(section),
    suivante: suivante ? r(suivante) : null,
    blocs: Array.from(lecture.querySelectorAll('.kiosque__bloc, .kiosque__image:not([hidden]), .kiosque__fin')).map(r),
    fluxStyle: document.querySelector('.kiosque__flux').getAttribute('style') || ''
  };
});

console.log('== Les hauteurs : jamais de lecture coupée ==');
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
const cartes = await page.locator('.kiosque__carte').count();
t('la liste a plusieurs cartes', cartes >= 3, `(${cartes})`);
const soucis = { interieur: [], section: [], suivante: [], liste: [], blocs: [] };
for (let i = 0; i < cartes; i++) {
  await page.locator('.kiosque__carte').nth(i).click();
  await page.waitForTimeout(1500);
  const m = await mesurer();
  const dedans = (a, b) => a.top >= b.top - 1 && a.bottom <= b.bottom + 1 && a.left >= b.left - 1 && a.right <= b.right + 1;
  if (!dedans(m.interieur, m.lecture)) soucis.interieur.push(i);
  if (!dedans(m.lecture, m.section)) soucis.section.push(i);
  if (m.suivante && m.suivante.top < m.lecture.bottom - 1) soucis.suivante.push(i);
  if (Math.abs(m.flux.height - m.lecture.height) >= 2 || !/block-size:\s*\d+px/.test(m.fluxStyle)) soucis.liste.push(i);
  if (m.blocs.some((b) => !dedans(b, m.lecture))) soucis.blocs.push(i);
}
t('l’intérieur de la lecture est entièrement dans la lecture', !soucis.interieur.length, `cartes ${soucis.interieur}`);
t('chaque bloc (bannière, blocs, marque de fin) est dans la lecture', !soucis.blocs.length, `cartes ${soucis.blocs}`);
t('la lecture reste dans sa section', !soucis.section.length, `cartes ${soucis.section}`);
t('rien ne chevauche la section suivante', !soucis.suivante.length, `cartes ${soucis.suivante}`);
t('la liste a la même hauteur que la lecture, posée en style en ligne', !soucis.liste.length, `cartes ${soucis.liste}`);

console.log('\n== Une lecture finie ==');
await page.locator('.kiosque__carte').first().click();
await page.waitForTimeout(1500);
const fin = await page.evaluate(() => {
  const f = document.querySelector('.kiosque__fin');
  if (!f || f.hidden) return null;
  const blocs = Array.from(document.querySelectorAll('.kiosque__lecture .kiosque__bloc'));
  const dernier = blocs[blocs.length - 1];
  const filet = getComputedStyle(f, '::before');
  return {
    apresDernierBloc: !dernier || f.getBoundingClientRect().top >= dernier.getBoundingClientRect().bottom - 1,
    couleur: filet.backgroundColor,
    largeur: parseFloat(filet.width),
    signature: /—|Personne|Direction/.test(f.textContent)
  };
});
t('la lecture se termine par une marque de fin, après le dernier bloc', !!fin && fin.apresDernierBloc, JSON.stringify(fin));
t('un court filet coloré, sans signature', !!fin && fin.largeur > 20 && fin.largeur < 80 && !/rgba\(0, 0, 0, 0\)/.test(fin.couleur) && !fin.signature, JSON.stringify(fin));

console.log('\n== La frise ==');
const frise = await page.evaluate(() => {
  const liste = document.querySelector('.kiosque__liste');
  const rail = getComputedStyle(liste, '::before');
  const groupes = Array.from(document.querySelectorAll('.kiosque__groupe'));
  const entrees = Array.from(document.querySelectorAll('.kiosque__entree'));
  const statuts = new Set(['info', 'succes', 'urgent', 'mot']);
  return {
    rail: rail.content !== 'none' && parseFloat(rail.width) >= 1 && !/rgba\(0, 0, 0, 0\)/.test(rail.backgroundColor),
    groupes: groupes.length,
    collants: groupes.every((g) => getComputedStyle(g).position === 'sticky'),
    statuts: entrees.every((e) => statuts.has(e.dataset.statut)),
    points: entrees.every((e) => { const p = getComputedStyle(e, '::before'); return p.content !== 'none' && parseFloat(p.width) >= 6; }),
    actives: document.querySelectorAll('.kiosque__entree--active').length,
    activeReliee: (() => { const a = document.querySelector('.kiosque__entree--active'); return !!a && getComputedStyle(a, '::after').opacity === '1' && a.querySelector('.kiosque__carte').getAttribute('aria-current') === 'true'; })(),
    quand: document.querySelectorAll('.kiosque__jour').length === entrees.length,
    resumes: document.querySelectorAll('.kiosque__carte-resume').length >= 1,
    ajout: document.querySelectorAll('.kiosque__ajout').length === 1
  };
});
t('un rail vertical longe la liste', frise.rail);
t('les mois sont des en-têtes collants', frise.groupes >= 1 && frise.collants, JSON.stringify(frise));
t('chaque entrée porte un point coloré selon son statut', frise.statuts && frise.points);
t('la carte lue est la seule active, reliée au rail', frise.actives === 1 && frise.activeReliee);
t('le bloc jour/mois, le résumé et le bouton d’ajout sont conservés', frise.quand && frise.resumes && frise.ajout);
await page.locator('.kiosque__carte').nth(1).hover();
await page.waitForTimeout(300);
t('le survol soulève la carte', (await page.locator('.kiosque__carte').nth(1).evaluate((c) => getComputedStyle(c).transform)) !== 'none');
const collant = await page.evaluate(() => {
  const zone = document.querySelector('.kiosque__defile');
  if (zone.scrollHeight <= zone.clientHeight + 4) return { deborde: false };
  zone.scrollTop = zone.scrollHeight;
  const z = zone.getBoundingClientRect();
  const auBord = Array.from(document.querySelectorAll('.kiosque__groupe')).some((g) => Math.abs(g.getBoundingClientRect().top - z.top) < 1.5);
  zone.scrollTop = 0;
  return { deborde: true, auBord };
});
t('la liste défile dans sa fenêtre et le mois reste collé en haut', !collant.deborde || collant.auBord, JSON.stringify(collant));

console.log('\n== Le clavier ==');
await page.locator('.kiosque__carte').first().click();
await page.waitForTimeout(300);
await page.locator('.kiosque__carte').first().focus();
const avantY = await page.evaluate(() => window.scrollY);
await page.keyboard.press('ArrowDown');
await page.waitForTimeout(400);
t('↓ passe à la carte suivante', (await page.locator('.kiosque__carte').nth(1).getAttribute('aria-current')) === 'true');
await page.keyboard.press('End');
await page.waitForTimeout(900);
const fin2 = await page.evaluate(() => {
  const zone = document.querySelector('.kiosque__defile').getBoundingClientRect();
  const c = document.querySelector('.kiosque__carte[aria-current="true"]').getBoundingClientRect();
  return { derniere: document.querySelector('.kiosque__carte[aria-current="true"]') === document.querySelector('.kiosque__entree:last-child .kiosque__carte'),
    visible: c.top >= zone.top - 1 && c.bottom <= zone.bottom + 1, scrollY: window.scrollY };
});
t('Fin va à la dernière carte, qui défile en vue dans la liste', fin2.derniere && fin2.visible, JSON.stringify(fin2));
t('la page, elle, ne bouge pas', Math.abs(fin2.scrollY - avantY) < 2, `${avantY} → ${fin2.scrollY}`);
await page.keyboard.press('Home');
await page.waitForTimeout(900);
t('Début revient à la première carte, visible', await page.evaluate(() => {
  const zone = document.querySelector('.kiosque__defile').getBoundingClientRect();
  const c = document.querySelector('.kiosque__carte').getBoundingClientRect();
  return document.querySelector('.kiosque__carte').getAttribute('aria-current') === 'true' && c.top >= zone.top - 1;
}));

console.log('\n== Arrivée par un lien ==');
const derniereId = await page.locator('.kiosque__carte').last().getAttribute('data-id');
await page.goto('about:blank'); // un vrai chargement, pas un simple changement d'ancre
await page.goto(`${B}/index.html#communication=${derniereId}`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
t('#communication=ID lit cette entrée et la montre dans la liste', await page.evaluate((id) => {
  const c = document.querySelector('.kiosque__carte[aria-current="true"]');
  const zone = document.querySelector('.kiosque__defile').getBoundingClientRect();
  const r = c.getBoundingClientRect();
  return c.dataset.id === id && r.top >= zone.top - 1 && r.bottom <= zone.bottom + 1;
}, derniereId));

console.log('\n== Mobile ==');
const mobile = await (await nav.newContext({ viewport: { width: 390, height: 844 } })).newPage();
mobile.on('pageerror', (e) => err.push('mobile: ' + e.message));
await mobile.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await mobile.waitForTimeout(1200);
const m = await mobile.evaluate(() => {
  const flux = document.querySelector('.kiosque__flux');
  const lecture = document.querySelector('.kiosque__lecture');
  const interieur = lecture.querySelector('.kiosque__lecture-interieur');
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  return {
    style: flux.getAttribute('style') || '',
    hauteur: flux.getBoundingClientRect().height, borne: 26 * rem,
    empiles: lecture.getBoundingClientRect().top >= flux.getBoundingClientRect().bottom - 1,
    dedans: interieur.getBoundingClientRect().bottom <= lecture.getBoundingClientRect().bottom + 1,
    largeur: document.documentElement.scrollWidth <= window.innerWidth
  };
});
t('sur une colonne, la liste a une hauteur bornée fixe et l’observateur ne pose rien', !/block-size/.test(m.style) && m.hauteur <= m.borne + 2, JSON.stringify(m));
t('la liste est au-dessus de la lecture, la lecture n’est pas coupée, pas de défilement horizontal', m.empiles && m.dedans && m.largeur, JSON.stringify(m));

// Sur une colonne, la lecture est SOUS la liste : toucher une carte doit
// l'amener à l'écran, sinon rien ne se passe visiblement.
await mobile.evaluate(() => window.scrollTo(0, 0));
await mobile.waitForTimeout(200);
await mobile.locator('.kiosque__carte').nth(2).click();
await mobile.waitForTimeout(700);
const venue = await mobile.evaluate(() => ({
  haut: document.querySelector('.kiosque__lecture').getBoundingClientRect().top,
  barre: document.querySelector('.site-entete').getBoundingClientRect().height,
  scrollY: window.scrollY
}));
t('toucher une communication amène la lecture sous la barre du site',
  venue.haut >= 0 && venue.haut <= venue.barre + 16, JSON.stringify(venue));
const navEntiere = await mobile.evaluate(() => {
  const u = document.querySelector('.site-nav__liste');
  return { scrollWidth: u.scrollWidth, clientWidth: u.clientWidth };
});
t('les liens de la barre tiennent à l’écran sur téléphone',
  navEntiere.scrollWidth <= navEntiere.clientWidth + 1, JSON.stringify(navEntiere));

console.log('\n== Sombre ==');
const sombre = await (await nav.newContext({ viewport: { width: 1366, height: 900 }, colorScheme: 'dark' })).newPage();
sombre.on('pageerror', (e) => err.push('sombre: ' + e.message));
await sombre.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await sombre.waitForTimeout(1200);
t('en sombre, le rail, les points et la marque de fin sont visibles', await sombre.evaluate(() => {
  const vide = (c) => /rgba\(0, 0, 0, 0\)/.test(c);
  return !vide(getComputedStyle(document.querySelector('.kiosque__liste'), '::before').backgroundColor)
    && !vide(getComputedStyle(document.querySelector('.kiosque__entree--active'), '::before').backgroundColor)
    && !vide(getComputedStyle(document.querySelector('.kiosque__fin'), '::before').backgroundColor);
}));

t('aucune erreur JavaScript', err.length === 0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

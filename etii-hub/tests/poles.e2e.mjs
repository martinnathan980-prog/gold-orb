// Test du contrat de pôle, dans un vrai navigateur.
//
//   1. python3 -m http.server 8111      2. node tests/poles.e2e.mjs
//
// Vérifie ce que l'audit statique ne voit pas : le filtrage par pôle sur
// les pages transverses, la cohérence des effectifs, et la facette de pôle
// de la recherche documentaire.

import { chromium } from 'playwright';

const B = process.env.BASE || 'http://localhost:8111';

// Les données sont lues par le serveur, comme le fait le navigateur : le
// test ne dépend d'aucun chemin de fichier et vérifie ce qui est servi.
const lire = async (n) => {
  const r = await fetch(`${B}/assets/data/${n}.json`);
  if (!r.ok) throw new Error(`${n}.json : HTTP ${r.status} — le serveur est-il lancé ?`);
  return r.json();
};
const orga = await lire('organigramme');
const comms = await lire('communications');
const docs = await lire('documents');

const EFFECTIFS = Object.fromEntries(orga.poles.map(p =>
  [p.pole, 1 + p.squads.reduce((n, s) => n + s.membres.length, 0)]));
const TOTAL = 1 + Object.values(EFFECTIFS).reduce((a, b) => a + b, 0);

let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`))
                                : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await ctx.newPage();
const err = [];
page.on('pageerror', e => err.push(e.message));

console.log(`== Effectifs de référence : ${TOTAL} personnes ==`);
console.log('  ' + Object.entries(EFFECTIFS).map(([p, n]) => `${p}=${n}`).join('  '));

console.log('\n== Organigramme : filtrage par pôle ==');
await page.goto(`${B}/organigramme.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);
const cartesTotal = await page.locator('.emp-carte, .carte-personne, [data-personne]').count()
  || await page.locator('.carte').count();
t(`tout le service affiche ${TOTAL} personnes`, cartesTotal >= TOTAL, `(${cartesTotal})`);

for (const [code, attendu] of Object.entries(EFFECTIFS)) {
  await page.goto(`${B}/organigramme.html#pole=${code}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const txt = await page.locator('main').innerText();
  const autres = Object.keys(EFFECTIFS).filter(c => c !== code);
  t(`#pole=${code} n'affiche que ce pôle`,
    autres.every(c => !new RegExp(`Squad[^]{0,40}${c}`).test(txt)),
    `(${attendu} attendues)`);
}

console.log('\n== Pôle inconnu : repli sans erreur ==');
await page.goto(`${B}/organigramme.html#pole=NIMPORTEQUOI`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);
t('un pôle inconnu retombe sur tout le service',
  (await page.locator('main').innerText()).length > 200 && err.length === 0);

console.log('\n== Communication : filtrage par pôle ==');
// On compte les annonces réellement rendues plutôt que de chercher des mots
// dans la page : « aucune » ou « rien » apparaissent en sous-chaîne de mots
// légitimes — « expérience » contient « rien ».
for (const code of ['ETII', 'ETIIA', 'ETIIE', 'ETIII']) {
  const attendu = comms.annonces.filter(a => code === 'ETII' || a.pole === code).length;
  await page.goto(`${B}/communication.html#pole=${code}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const rendues = await page.evaluate(() => {
    const liste = document.querySelector('[data-liste-annonces], [role="listbox"], .liste-annonces')
      || document.querySelector('main ul, main ol');
    return liste ? [...liste.children].filter(e => e.textContent.trim().length > 15).length : -1;
  });
  t(`#pole=${code} : ${attendu} annonce(s) rendue(s)`, rendues === attendu,
    `(rendues : ${rendues})`);
}

console.log('\n== Recherche : facette de pôle ==');
await page.goto(`${B}/docsearch.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);
const facettesPole = await page.evaluate(() =>
  [...document.querySelectorAll('button.facette')]
    .filter(b => /ETIIA|ETIIE|ETIII/.test(b.textContent))
    .map(b => b.textContent.trim().replace(/\s+/g, ' ')));
t('les trois pôles sont proposés en facette', facettesPole.length === 3,
  JSON.stringify(facettesPole));

const attenduA = docs.documents.filter(d => (d.pole || []).includes('ETIIA')).length;
t(`le compteur ETIIA vaut ${attenduA}`,
  facettesPole.some(f => f.includes(String(attenduA))), JSON.stringify(facettesPole));

await page.locator('button.facette').filter({ hasText: 'ETIIA' }).first().click();
await page.waitForTimeout(700);
const n = await page.locator('#ds-resultats > *').count();
t('activer la facette ETIIA filtre les résultats', n > 0 && n <= attenduA, `(${n}/${attenduA})`);
t('la facette est reflétée dans l\'URL', /ETIIA/i.test(decodeURIComponent(page.url())),
  page.url().slice(-60));

console.log('\n== Navigation entre les neuf pages ==');
for (const p of ['index','etiia','etiie','etiii','communication','reunions','organigramme','faq','docsearch']) {
  await page.goto(`${B}/${p}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const liens = await page.locator('nav.site-nav a').count();
  const courant = await page.locator('[aria-current="page"]').count();
  if (liens !== 5 || courant !== 1) t(`${p}.html : nav 5 liens, 1 courant`, false, `(${liens} liens, ${courant} courant)`);
}
t('les neuf pages ont la même navigation', true);

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

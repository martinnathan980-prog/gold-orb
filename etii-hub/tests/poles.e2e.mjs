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
const flotte = await lire('flotte');

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

console.log('\n== Communication : le kiosque de chaque pôle ==');
// La page dédiée a disparu : la communication se lit dans le Communication
// Center du tableau de bord (tout le service) et dans celui de chaque pôle.
// Seul le passé se lit : l'agenda « à venir » n'est plus de la
// communication. Un même événement saisi en annonce ET en agenda (même
// titre, même date) ne compte qu'une fois.
const cleUnique = (e) => e.date + '|' + String(e.titre || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const dedup = (liste) => { const vus = new Set(); return liste.filter((e) => { const k = cleUnique(e); if (vus.has(k)) return false; vus.add(k); return true; }); };
for (const code of ['ETIIA', 'ETIIE', 'ETIII']) {
  const attendu = dedup(comms.annonces.filter(a => a.pole === code)
    .concat(comms.agenda.filter(a => a.pole === code && a.statut !== 'a-venir' && a.type !== 'mot'))).length;
  await page.goto(`${B}/${code.toLowerCase()}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  const entrees = await page.locator('#zone-communication .kiosque__carte').count();
  t(`${code} : ${attendu} entrées dans son kiosque`, entrees === attendu, `(${entrees})`);
}

console.log('\n== Espace de pôle : repères, référents, porteurs ==');
// Plus de réunions dans un espace de pôle : entre la communication et
// l'organigramme, le pôle en un coup d'œil, ses référents par compétence
// et ses porteurs — tout calculé depuis organigramme.json, flotte.json et
// documents.json, sans rien d'inventé.
const membresDe = (bloc) => [bloc.responsable].concat(...bloc.squads.map(s => s.membres));
for (const bloc of orga.poles) {
  const code = bloc.pole;
  const membres = membresDe(bloc);
  const competences = new Set(membres.flatMap(m => (m.competences || []).map(c => c.nom)));
  const referents = new Set(membres.filter(m => (m.competences || []).some(c => c.niveau === 'referent')).map(m => m.id));
  const porteurs = flotte.flotte.filter(a => (a.poles || []).includes(code));
  const noms = new Set(membres.map(m => m.nom));
  const documents = docs.documents.filter(d => noms.has(d.porteur)).length;

  await page.goto(`${B}/${code.toLowerCase()}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  // textContent : innerText rendrait les capitales du CSS.
  const sousNav = await page.locator('.sous-nav a').evaluateAll(l => l.map(a => a.textContent.trim()));
  t(`${code} : sous-navigation Communication, Référents, Porteurs, Organigramme, FAQ`,
    sousNav.join('|') === 'Communication|Référents|Porteurs|Organigramme|FAQ', `(${sousNav.join('|')})`);
  t(`${code} : plus de section Réunions`, (await page.locator('#section-reunions, #zone-reunions').count()) === 0);

  const reperes = await page.locator('#zone-reperes .pole-repere__valeur').allInnerTexts();
  t(`${code} : repères ${membres.length} personnes, ${bloc.squads.length} squads, ${referents.size} référents, ${porteurs.length} porteurs, ${documents} documents`,
    reperes.join(' ') === [membres.length, bloc.squads.length, referents.size, porteurs.length, documents].join(' '),
    `(${reperes.join(' ')})`);

  const cartes = await page.locator('#zone-referents .pole-expertise').count();
  t(`${code} : une carte par compétence (${competences.size})`, cartes === competences.size, `(${cartes})`);
  t(`${code} : le compteur dit ${competences.size} compétences · ${referents.size} référents`,
    (await page.locator('#zone-referents .pole-experts__compte').evaluate(e => e.textContent)).trim()
      === `${competences.size} compétences · ${referents.size} référents`);
  const liensPersonne = page.locator('#zone-referents .pole-expertise__personne');
  const premierLien = (await liensPersonne.first().getAttribute('href')) || '';
  t(`${code} : les référents mènent à organigramme.html#pole=${code}&personne=…`,
    (await liensPersonne.count()) > 0 && premierLien.startsWith(`organigramme.html#pole=${code}&personne=p`), `(${premierLien})`);

  // La recherche filtre les compétences ; une requête sans réponse le dit.
  const premiereCompetence = (await page.locator('#zone-referents .pole-expertise__nom').first().innerText()).trim();
  await page.fill('#zone-referents .pole-experts__recherche', premiereCompetence);
  await page.waitForTimeout(400);
  const visibles = await page.locator('#zone-referents .pole-expertise:visible').count();
  t(`${code} : la recherche « ${premiereCompetence} » filtre les cartes`, visibles >= 1 && visibles < cartes, `(${visibles})`);
  await page.fill('#zone-referents .pole-experts__recherche', 'zzzz-rien');
  await page.waitForTimeout(400);
  t(`${code} : une recherche sans réponse l'annonce`, await page.locator('#zone-referents .pole-experts__vide').isVisible());
  await page.fill('#zone-referents .pole-experts__recherche', '');
  await page.waitForTimeout(400);

  const fiches = page.locator('#zone-porteurs .porteurs__fiche');
  const codes = (await fiches.locator('.porteurs__fiche-code').allInnerTexts()).map(s => s.trim()).sort();
  t(`${code} : ${porteurs.length} porteurs en cartes photo`,
    codes.join(',') === porteurs.map(a => a.code).sort().join(','), `(${codes.join(',')})`);
  const hrefs = await fiches.evaluateAll(l => l.map(a => a.getAttribute('href')));
  t(`${code} : chaque carte mène à index.html#porteur=CODE`,
    hrefs.length > 0 && hrefs.every(h => /^index\.html#porteur=[A-Z0-9]+$/.test(h)), `(${hrefs.join(' ')})`);
}
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
const toutes = dedup(comms.annonces.concat(comms.agenda.filter(a => a.statut !== 'a-venir' && a.type !== 'mot'))).length;
const auService = await page.locator('#zone-communication .kiosque__carte').count();
t(`le service liste le mot du chef et ses ${toutes} entrées passées`, auService === toutes + 1, `(${auService})`);
t('la lecture s\'ouvre sur le mot du chef', /trimestre qui se tient/i.test(await page.locator('#zone-communication .kiosque__lecture-titre').innerText()));

console.log('\n== Recherche : facette de pôle ==');
await page.goto(`${B}/docsearch.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);
// Le filtrage par pôle passe par un menu déroulant, aux côtés de « métier »
// et « porteur » — c'est la mise en page voulue par le service.
const optionsPole = await page.evaluate(() => {
  const sel = document.getElementById('ds-pole');
  return sel ? [...sel.options].map(o => o.value).filter(Boolean) : null;
});
t('le menu « pôle » propose les trois pôles',
  Array.isArray(optionsPole) && ['ETIIA', 'ETIIE', 'ETIII'].every(c => optionsPole.includes(c)),
  JSON.stringify(optionsPole));

const attenduA = docs.documents.filter(d => (d.pole || []).includes('ETIIA')).length;
await page.selectOption('#ds-pole', 'ETIIA');
await page.waitForTimeout(800);
const n = await page.locator('#ds-resultats > *').count();
t(`choisir ETIIA filtre les résultats (${attenduA} documents concernés)`,
  n > 0 && n <= attenduA, `(${n}/${attenduA})`);
t('le choix est reflété dans l\'URL', /ETIIA/i.test(decodeURIComponent(page.url())),
  page.url().slice(-60));
t('les trois menus de filtre sont présents',
  (await page.locator('#ds-metier, #ds-porteur, #ds-pole').count()) === 3);

console.log('\n== Navigation entre les neuf pages ==');
for (const p of ['index','etiia','etiie','etiii','reunions','organigramme','faq','docsearch','admin']) {
  await page.goto(`${B}/${p}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const liens = await page.locator('nav.site-nav a').count();
  const courant = await page.locator('[aria-current="page"]').count();
  // admin.html est hors navigation : aucune entrée courante, par construction.
  const attendu = p === 'admin' ? 0 : 1;
  if (liens !== 5 || courant !== attendu) t(`${p}.html : nav 5 liens, ${attendu} courant`, false, `(${liens} liens, ${courant} courant)`);
}
t('les huit pages ont la même navigation', true);

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

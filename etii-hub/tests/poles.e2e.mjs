// Test du contrat de pôle, dans un vrai navigateur.
//
//   1. python3 -m http.server 8111      2. node tests/poles.e2e.mjs
//
// Vérifie ce que l'audit statique ne voit pas : le filtrage par pôle sur
// les pages transverses, la cohérence des effectifs, les sections d'un
// espace de pôle, le sommaire du tableau de bord, et la facette de pôle
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

console.log('\n== Espace de pôle : en un coup d’œil, documents, FAQ ==');
// Plus de réunions ni de « porteurs du pôle » dans un espace de pôle. Entre
// la communication et la FAQ : le pôle en un coup d'œil — quatre repères,
// puis trois volets côte à côte (l'organigramme, les référents, qui
// travaille sur quel porteur), une personne par ligne, nom et rôle — et les
// documents du pôle, les plus récents en vigueur. Tout est calculé depuis
// organigramme.json, flotte.json et documents.json, sans rien d'inventé.
const sansAccents = (v) => String(v || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const membresDe = (bloc) => [bloc.responsable].concat(...bloc.squads.map(s => s.membres));
const porteurDe = (m) => String(m.porteur || m.perimetre || '').toUpperCase();
for (const bloc of orga.poles) {
  const code = bloc.pole;
  const membres = membresDe(bloc);
  const referents = new Set(membres.filter(m => (m.competences || []).some(c => c.niveau === 'referent')).map(m => m.id));
  const competencesAvecReferent = new Set(membres.flatMap(m => (m.competences || []).filter(c => c.niveau === 'referent').map(c => c.nom)));
  const noms = new Set(membres.map(m => sansAccents(m.nom)));
  const duPole = docs.documents.filter(d => d.titre && ((Array.isArray(d.pole) ? d.pole : [d.pole]).some(p => String(p || '').toUpperCase() === code) || noms.has(sansAccents(d.porteur))));
  const enVigueur = duPole.filter(d => !d.remplacePar).sort((a, b) => String(b.maj).localeCompare(String(a.maj)));
  const codesFlotte = flotte.flotte.filter(a => (a.poles || []).includes(code)).map(a => a.code.toUpperCase());
  const codesMembres = new Set(membres.map(porteurDe).filter(c => c && c !== 'TRANSVERSE'));
  const codesAttendus = new Set([...codesFlotte, ...codesMembres]);

  await page.goto(`${B}/${code.toLowerCase()}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  // textContent : innerText rendrait les capitales du CSS.
  const sousNav = await page.locator('.sous-nav a').evaluateAll(l => l.map(a => a.textContent.trim()));
  t(`${code} : sommaire Communication, En un coup d’œil, Documents, FAQ`,
    sousNav.join('|') === 'Communication|En un coup d’œil|Documents|FAQ', `(${sousNav.join('|')})`);
  t(`${code} : l’en-tête est sur la bande, le sommaire collant en dessous`,
    (await page.locator('.page-tete h1').count()) === 1
    && (await page.locator('.page-sommaire').evaluate(e => getComputedStyle(e).position)) === 'sticky');
  t(`${code} : aucune bande entre la barre du site et l’en-tête du pôle`,
    await page.evaluate(() => Math.abs(document.querySelector('.page-tete').getBoundingClientRect().top - document.querySelector('.site-entete').getBoundingClientRect().bottom) < 1));
  t(`${code} : plus de section Réunions, Porteurs, Organigramme ni « Équipe & référents »`,
    (await page.locator('#section-reunions, #zone-reunions, #section-porteurs, #zone-porteurs, #section-organigramme, #zone-organigramme, #section-equipe, #zone-equipe, .arbre').count()) === 0);

  const reperes = await page.locator('#zone-reperes .pole-repere__valeur').allInnerTexts();
  t(`${code} : repères ${membres.length} personnes, ${bloc.squads.length} squads, ${referents.size} référents, ${enVigueur.length} documents`,
    reperes.join(' ') === [membres.length, bloc.squads.length, referents.size, enVigueur.length].join(' '),
    `(${reperes.join(' ')})`);
  t(`${code} : les repères se lisent, ils ne se cliquent pas`,
    (await page.locator('#zone-reperes .pole-repere a').count()) === 0);

  // Trois volets, côte à côte et de même hauteur, dans une section courte.
  const volets = await page.locator('#zone-reperes .annuaire__volet').evaluateAll(l => l.map(v => {
    const r = v.getBoundingClientRect();
    return { titre: v.querySelector('.annuaire__volet-titre').textContent.trim(), top: Math.round(r.top), h: Math.round(r.height) };
  }));
  t(`${code} : trois volets — Organigramme, Référents, Par porteur — côte à côte`,
    volets.map(v => v.titre).join('|') === 'Organigramme|Référents|Par porteur'
    && volets.every(v => v.top === volets[0].top && Math.abs(v.h - volets[0].h) <= 1), JSON.stringify(volets));
  const hauteurSection = await page.locator('#section-reperes').evaluate(e => e.getBoundingClientRect().height);
  t(`${code} : la section tient en moins d’un écran et demi (${Math.round(hauteurSection)} px)`, hauteurSection < 1200);

  // L'organigramme : le responsable, puis une carte par squad.
  const orgaVolet = page.locator(`#annuaire-${code.toLowerCase()}-organigramme`);
  const groupes = await orgaVolet.locator('.annuaire__groupe').evaluateAll(l => l.map(g => ({
    titre: g.querySelector('.annuaire__groupe-titre').textContent.trim(),
    gens: [...g.querySelectorAll('.annuaire__personne')].map(p => ({
      nom: p.querySelector('.annuaire__nom').textContent.trim(),
      role: p.querySelector('.annuaire__role').textContent.trim(),
      href: p.querySelector('.annuaire__lien').getAttribute('href'),
      lead: !!p.querySelector('.annuaire__badge')
    }))
  })));
  t(`${code} : l’organigramme ouvre sur le responsable, puis ${bloc.squads.length} squads`,
    groupes.length === 1 + bloc.squads.length && groupes[0].titre === 'Responsable du pôle'
    && groupes[0].gens.length === 1 && groupes[0].gens[0].nom === bloc.responsable.nom
    && bloc.squads.every((sq, i) => groupes[i + 1].titre === sq.nom && groupes[i + 1].gens.length === sq.membres.length),
    JSON.stringify(groupes.map(g => g.titre + ':' + g.gens.length)));
  t(`${code} : chaque squad commence par son lead`,
    bloc.squads.every((sq, i) => !sq.membres.some(m => m.role === 'leader') || groupes[i + 1].gens[0].lead));
  const lignes = groupes.flatMap(g => g.gens);
  t(`${code} : une personne = une ligne, son nom et son rôle, vers sa fiche (${membres.length})`,
    lignes.length === membres.length
    && lignes.every(l => l.nom && l.role && l.href.startsWith(`organigramme.html#pole=${code}&personne=`))
    && (await orgaVolet.locator('.portrait, .pole-competence').count()) === 0, `(${lignes.length})`);

  // Les référents : une compétence, qui solliciter.
  const refVolet = page.locator(`#annuaire-${code.toLowerCase()}-referents`);
  const groupesRef = await refVolet.locator('.annuaire__groupe').count();
  t(`${code} : les référents couvrent ${competencesAvecReferent.size} compétences`, groupesRef === competencesAvecReferent.size, `(${groupesRef})`);

  // Par porteur : un groupe par porteur, les gens du pôle qui y travaillent.
  const porteursVolet = page.locator(`#annuaire-${code.toLowerCase()}-porteurs`);
  const groupesP = await porteursVolet.locator('.annuaire__groupe').evaluateAll(l => l.map(g => ({
    code: g.querySelector('.annuaire__porteur').textContent.trim().toUpperCase(),
    gens: [...g.querySelectorAll('.annuaire__personne')].map(p => ({ nom: p.querySelector('.annuaire__nom').textContent.trim(), lead: !!p.querySelector('.annuaire__badge') }))
  })));
  const codesRendus = new Set(groupesP.map(g => g.code));
  t(`${code} : « Par porteur » couvre ${codesAttendus.size} porteurs (flotte et périmètres des membres)`,
    codesRendus.size === codesAttendus.size && [...codesAttendus].every(c => codesRendus.has(c)), `(${[...codesRendus].join(',')})`);
  t(`${code} : les groupes commencent par les porteurs déclarés dans flotte.json`,
    codesFlotte.every((c, i) => groupesP[i] && groupesP[i].code === c));
  const groupeH160 = groupesP.find(g => g.code === 'H160');
  const gensH160 = membres.filter(m => porteurDe(m) === 'H160');
  t(`${code} : le groupe H160 compte ${gensH160.length} personnes, le lead d’abord`,
    Boolean(groupeH160) && groupeH160.gens.length === gensH160.length
    && (!gensH160.some(m => m.role === 'leader') || groupeH160.gens[0].lead), JSON.stringify(groupeH160 && groupeH160.gens.slice(0, 2)));

  // Un seul champ filtre les trois volets.
  const champ = page.locator('#zone-reperes .annuaire__recherche');
  await champ.fill('harnais');
  await page.waitForTimeout(400);
  const attendusHarnais = membres.filter(m => sansAccents([m.nom, m.poste, porteurDe(m)].concat((m.competences || []).map(c => c.nom)).join(' ')).includes('harnais')).length;
  const visiblesHarnais = await orgaVolet.locator('.annuaire__personne:visible').count();
  t(`${code} : « harnais » ne garde que ${attendusHarnais} personnes dans l’organigramme, et le dit`,
    visiblesHarnais === attendusHarnais
    && (await page.locator('#zone-reperes .annuaire__resultat').innerText()).startsWith(String(attendusHarnais)), `(${visiblesHarnais})`);
  await champ.fill('zzzz-rien');
  await page.waitForTimeout(400);
  t(`${code} : une recherche sans réponse l’annonce dans chaque volet`,
    (await page.locator('#zone-reperes .annuaire__rien:visible').count()) === 3);
  await champ.fill('');
  await page.waitForTimeout(400);

  // Les documents du pôle : les huit plus récents en vigueur.
  const docsRendus = await page.locator('#zone-documents .pole-doc .pole-doc__titre').allInnerTexts();
  t(`${code} : « Documents du pôle » montre les ${Math.min(8, enVigueur.length)} plus récents en vigueur`,
    docsRendus.length === Math.min(8, enVigueur.length)
    && docsRendus.every((titre, i) => titre.trim() === enVigueur[i].titre), JSON.stringify(docsRendus.slice(0, 2)));
  t(`${code} : « Tous les documents du pôle (${enVigueur.length}) » mène à la recherche filtrée`,
    (await page.locator('#zone-documents .pole-docs__pied a').getAttribute('href')) === `docsearch.html#pole=${code}`
    && (await page.locator('#zone-documents .pole-docs__pied a').innerText()).includes(`(${enVigueur.length})`));

  // FAQ : les questions et l'expert, sans « Toute la base ».
  const pied = await page.locator('#zone-faq .liseuse__pied').innerText();
  t(`${code} : la FAQ propose « Interroger un expert » sans « Toute la base »`,
    /Interroger un expert/.test(pied) && !/Toute la base/i.test(pied));
  t(`${code} : hors mode édition, aucune commande d’édition visible`,
    (await page.locator('.edition-seulement:visible').count()) === 0);
}

console.log('\n== Tableau de bord : en-tête sur la bande et sommaire ==');
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
const toutes = dedup(comms.annonces.concat(comms.agenda.filter(a => a.statut !== 'a-venir' && a.type !== 'mot'))).length;
const auService = await page.locator('#zone-communication .kiosque__carte').count();
t(`le service liste le mot du chef et ses ${toutes} entrées passées`, auService === toutes + 1, `(${auService})`);
t('la lecture s\'ouvre sur le mot du chef', /trimestre qui se tient/i.test(await page.locator('#zone-communication .kiosque__lecture-titre').innerText()));
const sommaireService = await page.locator('.sous-nav a').evaluateAll(l => l.map(a => a.textContent.trim() + ':' + a.getAttribute('aria-current')));
t('le sommaire du service : Communication (courant), À venir, Porteurs, Suivi OTQ / OTD',
  sommaireService.join('|') === 'Communication:true|À venir:false|Porteurs:false|Suivi OTQ / OTD:false', `(${sommaireService.join('|')})`);
// « À venir » : les prochains rendez-vous, du plus proche au plus lointain.
const jour = (() => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); })();
const aVenir = comms.agenda.filter(e => e.titre && e.type !== 'mot' && String(e.date) >= jour).sort((a, b) => String(a.date).localeCompare(String(b.date)));
const rdv = await page.locator('#zone-agenda .agenda__rdv .agenda__titre').evaluateAll(l => l.map(h => h.lastChild.textContent.trim()));
t(`« À venir » liste les ${Math.min(6, aVenir.length)} prochains rendez-vous, dans l’ordre`,
  rdv.length === Math.min(6, aVenir.length) && rdv.every((titre, i) => titre === aVenir[i].titre), JSON.stringify(rdv));
t('l\'en-tête ETII est sur la bande, sur toute la largeur',
  (await page.locator('.page-tete h1').innerText()).trim() === 'ETII'
  && (await page.evaluate(() => {
    const tete = document.querySelector('.page-tete');
    const fond = getComputedStyle(tete).backgroundColor;
    // La largeur du corps : la gouttière de barre de défilement est réservée.
    return tete.getBoundingClientRect().width >= document.body.clientWidth - 1
      && fond !== getComputedStyle(document.body).backgroundColor;
  })));
await page.evaluate(() => document.getElementById('section-porteurs').scrollIntoView());
await page.waitForTimeout(900);
const courantApres = await page.locator('.sous-nav a[aria-current="true"]').innerText();
t('le lien courant suit le défilement (Porteurs)', /porteurs/i.test(courantApres), `(${courantApres})`);

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
// La barre a cinq liens : le tableau de bord, les trois pôles, la
// recherche. faq.html, reunions.html et organigramme.html n'y figurent pas
// — on les atteint depuis un pôle — et n'ont donc AUCUNE entrée courante.
// Marquer « Tableau de bord » y serait un mensonge.
const HORS_BARRE = new Set(['faq', 'reunions', 'organigramme']);
let navOk = true;
for (const p of ['index','etiia','etiie','etiii','reunions','organigramme','faq','docsearch']) {
  await page.goto(`${B}/${p}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const liens = await page.locator('nav.site-nav a').count();
  const courant = await page.locator('nav.site-nav [aria-current="page"]').count();
  const attendu = HORS_BARRE.has(p) ? 0 : 1;
  if (liens !== 5 || courant !== attendu) { navOk = false; t(`${p}.html : nav 5 liens, ${attendu} courant`, false, `(${liens} liens, ${courant} courant)`); }
}
t('les huit pages ont la même navigation, sans lien Organigramme', navOk);

// Ouvert depuis un pôle, l'organigramme désigne ce pôle dans la barre.
await page.goto(`${B}/organigramme.html#pole=ETIIE`, { waitUntil: 'networkidle' });
await page.waitForTimeout(700);
t('organigramme.html#pole=ETIIE : « ETIIE » est la page courante de la barre',
  (await page.locator('nav.site-nav a[aria-current="page"]').getAttribute('href').catch(() => '')) === 'etiie.html');

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

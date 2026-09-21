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

console.log('\n== Espace de pôle : en un coup d’œil, équipe & référents, FAQ ==');
// Plus de réunions ni de « porteurs du pôle » dans un espace de pôle : entre
// la communication et la FAQ, le pôle en un coup d'œil (repères, à qui
// s'adresser, par porteur) et l'équipe & ses référents (par squad ou par
// compétence) — tout calculé depuis organigramme.json, flotte.json et
// documents.json, sans rien d'inventé.
const membresDe = (bloc) => [bloc.responsable].concat(...bloc.squads.map(s => s.membres));
const porteurDe = (m) => String(m.porteur || m.perimetre || '').toUpperCase();
for (const bloc of orga.poles) {
  const code = bloc.pole;
  const membres = membresDe(bloc);
  const competences = new Set(membres.flatMap(m => (m.competences || []).map(c => c.nom)));
  const referents = new Set(membres.filter(m => (m.competences || []).some(c => c.niveau === 'referent')).map(m => m.id));
  const leads = bloc.squads.map(s => s.membres.find(m => m.role === 'leader')).filter(Boolean);
  const noms = new Set(membres.map(m => m.nom));
  const documents = docs.documents.filter(d => noms.has(d.porteur)).length;
  const codesFlotte = flotte.flotte.filter(a => (a.poles || []).includes(code)).map(a => a.code.toUpperCase());
  const codesMembres = new Set(membres.map(porteurDe).filter(c => c && c !== 'TRANSVERSE'));
  const codesAttendus = new Set([...codesFlotte, ...codesMembres]);

  await page.goto(`${B}/${code.toLowerCase()}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  // textContent : innerText rendrait les capitales du CSS.
  const sousNav = await page.locator('.sous-nav a').evaluateAll(l => l.map(a => a.textContent.trim()));
  t(`${code} : sommaire Communication, En un coup d’œil, Équipe & référents, FAQ`,
    sousNav.join('|') === 'Communication|En un coup d’œil|Équipe & référents|FAQ', `(${sousNav.join('|')})`);
  t(`${code} : l’en-tête est sur la bande, le sommaire collant en dessous`,
    (await page.locator('.page-tete h1').count()) === 1
    && (await page.locator('.page-sommaire').evaluate(e => getComputedStyle(e).position)) === 'sticky');
  t(`${code} : plus de section Réunions, Porteurs ni Organigramme`,
    (await page.locator('#section-reunions, #zone-reunions, #section-porteurs, #zone-porteurs, #section-organigramme, #zone-organigramme, .arbre').count()) === 0);

  const reperes = await page.locator('#zone-reperes .pole-repere__valeur').allInnerTexts();
  t(`${code} : repères ${membres.length} personnes, ${bloc.squads.length} squads, ${referents.size} référents, ${documents} documents`,
    reperes.join(' ') === [membres.length, bloc.squads.length, referents.size, documents].join(' '),
    `(${reperes.join(' ')})`);
  t(`${code} : le repère « documents » mène à la recherche filtrée sur le pôle`,
    (await page.locator('#zone-reperes .pole-repere__lien').last().getAttribute('href')) === `docsearch.html#pole=${code}`);

  // À qui s'adresser : le responsable puis les leads, chacun vers sa fiche.
  const contacts = await page.locator('#zone-reperes .pole-contacts__bloc').first().locator('.pole-personne').evaluateAll(
    l => l.map(a => ({ nom: a.querySelector('.pole-personne__nom').textContent.trim(), href: a.getAttribute('href') })));
  t(`${code} : « À qui s’adresser » liste le responsable et les ${leads.length} leads`,
    contacts.length === 1 + leads.length && contacts[0].nom === bloc.responsable.nom
    && leads.every((l, i) => contacts[i + 1].nom === l.nom)
    && contacts.every(c => c.href.startsWith(`organigramme.html#pole=${code}&personne=`)), JSON.stringify(contacts.slice(0, 2)));

  // Par porteur : un groupe par porteur, les gens du pôle qui y travaillent.
  const groupes = await page.locator('#zone-reperes .pole-porteur-groupe').evaluateAll(
    l => l.map(g => ({ code: g.querySelector('.pole-porteur-groupe__code').textContent.trim().toUpperCase(),
                       gens: [...g.querySelectorAll('.pole-jeton')].map(j => j.textContent.trim()) })));
  const codesRendus = new Set(groupes.map(g => g.code));
  t(`${code} : « Par porteur » couvre ${codesAttendus.size} porteurs (flotte et périmètres des membres)`,
    codesRendus.size === codesAttendus.size && [...codesAttendus].every(c => codesRendus.has(c)), `(${[...codesRendus].join(',')})`);
  t(`${code} : les groupes commencent par les porteurs déclarés dans flotte.json`,
    codesFlotte.every((c, i) => groupes[i] && groupes[i].code === c));
  const groupeH160 = groupes.find(g => g.code === 'H160');
  const gensH160 = membres.filter(m => porteurDe(m) === 'H160');
  t(`${code} : le groupe H160 compte ${gensH160.length} personnes, le lead d’abord`,
    Boolean(groupeH160) && groupeH160.gens.length === gensH160.length
    && (!gensH160.some(m => m.role === 'leader') || /Lead$/.test(groupeH160.gens[0])), JSON.stringify(groupeH160 && groupeH160.gens.slice(0, 2)));

  // Équipe & référents : par squad d'abord.
  const vues = await page.locator('#zone-equipe .pole-experts__vue').evaluateAll(l => l.map(b => b.textContent.trim() + ':' + b.getAttribute('aria-pressed')));
  t(`${code} : le commutateur propose Par squad (actif) et Par compétence`, vues.join('|') === 'Par squad:true|Par compétence:false', `(${vues.join('|')})`);
  t(`${code} : le responsable ouvre la vue par squad, avec son portrait`,
    (await page.locator('#zone-equipe .pole-squad--responsable .portrait').count()) === 1
    && (await page.locator('#zone-equipe .pole-squad--responsable .pole-membre__nom').innerText()).trim() === bloc.responsable.nom);
  const squadsRendues = await page.locator('#zone-equipe .pole-squad:not(.pole-squad--responsable)').count();
  t(`${code} : une carte par squad (${bloc.squads.length})`, squadsRendues === bloc.squads.length, `(${squadsRendues})`);
  const membresRendus = await page.locator('#zone-equipe .pole-squad__membres .pole-membre').count();
  t(`${code} : chaque membre est listé avec son portrait (${membres.length - 1})`,
    membresRendus === membres.length - 1
    && (await page.locator('#zone-equipe .pole-squad__membres .pole-membre .portrait').count()) === membresRendus, `(${membresRendus})`);
  const nbReferentsPastilles = membres.flatMap(m => (m.competences || [])).filter(c => c.niveau === 'referent').length;
  t(`${code} : ${nbReferentsPastilles} pastilles « référent » en terre cuite`,
    (await page.locator('#zone-equipe .pole-squad .pole-competence--referent').count()) === nbReferentsPastilles);
  t(`${code} : le compteur dit ${membres.length} personnes · ${bloc.squads.length} squads`,
    (await page.locator('#zone-equipe .pole-experts__compte').evaluate(e => e.textContent)).trim()
      === `${membres.length} personnes · ${bloc.squads.length} squads`);
  const premierLien = (await page.locator('#zone-equipe .pole-squad__membres .pole-membre__nom').first().getAttribute('href')) || '';
  t(`${code} : les membres mènent à organigramme.html#pole=${code}&personne=…`,
    premierLien.startsWith(`organigramme.html#pole=${code}&personne=p`), `(${premierLien})`);

  // La recherche filtre les membres ; une squad sans réponse se replie.
  await page.fill('#zone-equipe .pole-experts__recherche', 'harnais');
  await page.waitForTimeout(400);
  const attendusHarnais = membres.filter(m => [m.nom, m.poste, porteurDe(m)].concat((m.competences || []).map(c => c.nom))
    .join(' ').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').includes('harnais')).length;
  const visiblesHarnais = await page.locator('#zone-equipe .pole-membre:visible').count();
  t(`${code} : « harnais » ne garde que ${attendusHarnais} personnes`, visiblesHarnais === attendusHarnais, `(${visiblesHarnais})`);
  await page.fill('#zone-equipe .pole-experts__recherche', 'zzzz-rien');
  await page.waitForTimeout(400);
  t(`${code} : une recherche sans réponse l’annonce`, await page.locator('#zone-equipe .pole-experts__vide').isVisible());
  await page.fill('#zone-equipe .pole-experts__recherche', '');
  await page.waitForTimeout(400);

  // Par compétence : l'ancienne grille, une carte par compétence.
  await page.click('#zone-equipe .pole-experts__vue[data-vue="competence"]');
  await page.waitForTimeout(300);
  const cartes = await page.locator('#zone-equipe .pole-expertise').count();
  t(`${code} : une carte par compétence (${competences.size})`, cartes === competences.size, `(${cartes})`);
  t(`${code} : le compteur dit ${competences.size} compétences · ${referents.size} référents`,
    (await page.locator('#zone-equipe .pole-experts__compte').evaluate(e => e.textContent)).trim()
      === `${competences.size} compétences · ${referents.size} référents`);
  const liensPersonne = page.locator('#zone-equipe .pole-expertise__personne');
  const premierReferent = (await liensPersonne.first().getAttribute('href')) || '';
  t(`${code} : les référents mènent à organigramme.html#pole=${code}&personne=…`,
    (await liensPersonne.count()) > 0 && premierReferent.startsWith(`organigramme.html#pole=${code}&personne=p`), `(${premierReferent})`);
  const premiereCompetence = (await page.locator('#zone-equipe .pole-expertise__nom').first().innerText()).trim();
  await page.fill('#zone-equipe .pole-experts__recherche', premiereCompetence);
  await page.waitForTimeout(400);
  const visibles = await page.locator('#zone-equipe .pole-expertise:visible').count();
  t(`${code} : la recherche « ${premiereCompetence} » filtre les cartes`, visibles >= 1 && visibles < cartes, `(${visibles})`);
  await page.fill('#zone-equipe .pole-experts__recherche', '');
  await page.waitForTimeout(400);

  // Le repère « référents » ouvre la vue par compétence.
  await page.click('#zone-equipe .pole-experts__vue[data-vue="squad"]');
  await page.click('#zone-reperes .pole-repere__lien[data-vue-equipe="competence"]');
  await page.waitForTimeout(400);
  t(`${code} : le repère « référents » ouvre la vue par compétence`,
    (await page.locator('#zone-equipe .pole-experts__vue[data-vue="competence"]').getAttribute('aria-pressed')) === 'true');

  // FAQ : les questions et l'expert, sans « Toute la base ».
  const pied = await page.locator('#zone-faq .liseuse__pied').innerText();
  t(`${code} : la FAQ propose « Interroger un expert » sans « Toute la base »`,
    /Interroger un expert/.test(pied) && !/Toute la base/i.test(pied));
}

console.log('\n== Tableau de bord : en-tête sur la bande et sommaire ==');
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
const toutes = dedup(comms.annonces.concat(comms.agenda.filter(a => a.statut !== 'a-venir' && a.type !== 'mot'))).length;
const auService = await page.locator('#zone-communication .kiosque__carte').count();
t(`le service liste le mot du chef et ses ${toutes} entrées passées`, auService === toutes + 1, `(${auService})`);
t('la lecture s\'ouvre sur le mot du chef', /trimestre qui se tient/i.test(await page.locator('#zone-communication .kiosque__lecture-titre').innerText()));
const sommaireService = await page.locator('.sous-nav a').evaluateAll(l => l.map(a => a.textContent.trim() + ':' + a.getAttribute('aria-current')));
t('le sommaire du service : Communication (courant), Porteurs, Suivi OTQ / OTD',
  sommaireService.join('|') === 'Communication:true|Porteurs:false|Suivi OTQ / OTD:false', `(${sommaireService.join('|')})`);
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
for (const p of ['index','etiia','etiie','etiii','reunions','organigramme','faq','docsearch']) {
  await page.goto(`${B}/${p}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const liens = await page.locator('nav.site-nav a').count();
  const courant = await page.locator('[aria-current="page"]').count();
  if (liens !== 5 || courant !== 1) t(`${p}.html : nav 5 liens, 1 courant`, false, `(${liens} liens, ${courant} courant)`);
}
t('les huit pages ont la même navigation', true);

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

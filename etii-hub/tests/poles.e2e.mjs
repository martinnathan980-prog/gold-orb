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
// la communication et la FAQ : le pôle en un coup d'œil — ses chiffres en
// une ligne, les équipes en tuiles qui s'ouvrent sur place, les référents
// en cartes, et une tuile par porteur avec ses gens — puis les documents
// du pôle, les plus récents en vigueur. Tout est calculé depuis organigramme.json, flotte.json et
// documents.json, sans rien d'inventé.
const sansAccents = (v) => String(v || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const membresDe = (bloc) => [bloc.responsable].concat(...bloc.squads.map(s => s.membres));
const porteurDe = (m) => String(m.porteur || m.perimetre || '').toUpperCase();
for (const bloc of orga.poles) {
  const code = bloc.pole;
  const membres = membresDe(bloc);
  const estReferent = (m) => m.referent === true || (m.referent !== false && (m.competences || []).some(c => c.niveau === 'referent'));
  const referents = new Set(membres.filter(estReferent).map(m => m.id));
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
  t(`${code} : sommaire Communication, À venir, En un coup d’œil, Documents, FAQ`,
    sousNav.join('|') === 'Communication|À venir|En un coup d’œil|Documents|FAQ', `(${sousNav.join('|')})`);
  // « À venir » : des pastilles sur leur ligne — plus de carte « prochain
  // rendez-vous », de compte à rebours ni de légende —, avec les
  // rendez-vous du pôle et ceux du service, et d'aucun autre pôle. La
  // couleur seule les distingue : celle du pôle, le marine du service.
  const polesVus = await page.locator('#zone-agenda .agenda__rdv').evaluateAll(l => l.map(e => e.dataset.pole));
  t(`${code} : « À venir » est une ligne de pastilles, sans compte à rebours ni légende`,
    (await page.locator('#zone-agenda .agenda').count()) === 1
    && (await page.locator('#zone-agenda [class*="agenda__prochain"], #zone-agenda .agenda__legende').count()) === 0
    && (await page.locator('#zone-agenda .agenda__scene, #zone-agenda .agenda--vide').count()) === 1
    && (await page.locator('#zone-agenda .agenda__rdv .agenda__pastille').count()) === polesVus.length);
  t(`${code} : « À venir » ne montre que le pôle et le service`,
    polesVus.every(p => p === code || p === 'ETII'), JSON.stringify(polesVus));
  const teintes = await page.evaluate((code) => {
    const jeton = (nom) => {
      const s = document.createElement('span');
      s.style.color = 'var(' + nom + ')';
      document.body.append(s);
      const c = getComputedStyle(s).color;
      s.remove();
      return c;
    };
    const attendues = { ETII: jeton('--agenda-service'), [code]: jeton('--pole-' + code.toLowerCase()) };
    return [...document.querySelectorAll('#zone-agenda .agenda__rdv')].map((li) => {
      const s = getComputedStyle(li.querySelector('.agenda__pastille'));
      const filet = li.classList.contains('agenda__rdv--droite') ? s.borderRightColor : s.borderLeftColor;
      return filet === attendues[li.dataset.pole] && attendues.ETII !== attendues[code];
    });
  }, code);
  t(`${code} : le pôle et le service se distinguent par la couleur seule`,
    teintes.every(Boolean) && !/service|ETII/i.test(await page.locator('#zone-agenda .agenda__quand').evaluateAll(l => l.map(e => e.textContent).join(' '))),
    JSON.stringify(teintes));
  t(`${code} : l’en-tête est sur la bande, le sommaire collant en dessous`,
    (await page.locator('.page-tete h1').count()) === 1
    && (await page.locator('.page-sommaire').evaluate(e => getComputedStyle(e).position)) === 'sticky');
  t(`${code} : aucune bande entre la barre du site et l’en-tête du pôle`,
    await page.evaluate(() => Math.abs(document.querySelector('.page-tete').getBoundingClientRect().top - document.querySelector('.site-entete').getBoundingClientRect().bottom) < 1));
  t(`${code} : plus de section Réunions, Porteurs, Organigramme ni « Équipe & référents »`,
    (await page.locator('#section-reunions, #zone-reunions, #section-porteurs, #zone-porteurs, #section-organigramme, #zone-organigramme, #section-equipe, #zone-equipe, .arbre').count()) === 0);

  const Z = '#zone-reperes';
  const fiche = new RegExp('^organigramme\\.html#pole=' + code + '&personne=');
  const nomsDe = (liste) => liste.map(m => m.nom).sort().join('|');
  const squadDe = (m) => { const sq = bloc.squads.find(x => x.membres.includes(m)); return sq ? sq.nom : ''; };
  const texteDe = (m) => sansAccents([m.nom, m.poste, porteurDe(m), squadDe(m)].concat((m.competences || []).map(c => c.nom)).join(' '));

  // Les chiffres : une ligne, qui se lit sans se cliquer — plus de tuiles.
  const chiffres = await page.locator(`${Z} .coup-oeil__nombre`).allInnerTexts();
  t(`${code} : chiffres ${membres.length} personnes, ${bloc.squads.length} squads, ${referents.size} référents, ${enVigueur.length} documents`,
    chiffres.join(' ') === [membres.length, bloc.squads.length, referents.size, enVigueur.length].join(' '), `(${chiffres.join(' ')})`);
  t(`${code} : les chiffres se lisent, ils ne se cliquent pas`,
    (await page.locator(`${Z} .coup-oeil__chiffres a`).count()) === 0);
  t(`${code} : ni tuiles de repères, ni onglets, ni volets`,
    (await page.locator(`${Z} .pole-repere, ${Z} [role="tab"], ${Z} [role="tabpanel"]`).count()) === 0);

  // Plus de champ « Qui peut m'aider ? » ni de « Souvent cherché » : on ne
  // sait pas qui l'on cherche, on ouvre une équipe, un référent, un porteur.
  t(`${code} : ni champ « Qui peut m’aider ? », ni « Souvent cherché », ni index par compétence`,
    (await page.locator(`${Z} [class*="qui__"], ${Z} input[type="search"], ${Z} .referents__index, ${Z} .referents__puce`).count()) === 0
    && !/Souvent cherché|Qui peut m’aider/.test(await page.locator(Z).innerText()));

  // Les équipes : une tuile par squad — son nom, son effectif, son lead.
  const E = `${Z} .equipes`;
  const tuiles = await page.locator(`${E} .equipe__tuile`).evaluateAll(l => l.map(b => ({
    nom: b.querySelector('.equipe__nom').textContent.trim(),
    n: Number(b.querySelector('.equipe__nombre').textContent),
    lead: (b.querySelector('.equipe__lead-nom') || { textContent: '' }).textContent.trim(),
    ouverte: b.getAttribute('aria-expanded')
  })));
  t(`${code} : ${bloc.squads.length} tuiles d’équipe, avec leur effectif et leur lead`,
    tuiles.length === bloc.squads.length && bloc.squads.every((sq, i) => tuiles[i].nom === sq.nom && tuiles[i].n === sq.membres.length
      && tuiles[i].lead === ((sq.membres.find(m => m.role === 'leader') || { nom: '' }).nom) && tuiles[i].ouverte === 'false'),
    JSON.stringify(tuiles.slice(0, 2)));
  t(`${code} : le responsable, nommé, mène à sa fiche`,
    (await page.locator(`${Z} .equipes__responsable-nom`).innerText()).trim() === bloc.responsable.nom
    && fiche.test(await page.locator(`${Z} .equipes__responsable-nom`).getAttribute('href')));
  t(`${code} : « L’organigramme complet » reste à portée`,
    (await page.locator(`${Z} a[href="organigramme.html#pole=${code}"]`).count()) === 1);
  // Les visages d'une tuile : six au plus, côte à côte — aucun ne cache les
  // initiales du voisin —, puis « +N » ; le nom de chacun en infobulle.
  const visages = await page.locator(`${E} .equipe__visages`).evaluateAll(l => l.map(v => {
    const r = [...v.querySelectorAll('.avatar')].map(a => a.getBoundingClientRect());
    return {
      n: r.length, chevauche: r.some((b, i) => i && b.left < r[i - 1].right - 0.5 && Math.abs(b.top - r[i - 1].top) < 1),
      titres: [...v.querySelectorAll('.avatar')].every(a => a.title),
      plus: (v.querySelector('.equipe__plus') || { textContent: '' }).textContent
    };
  }));
  t(`${code} : les visages des tuiles se lisent en entier (six au plus, puis « +N »)`,
    visages.length === bloc.squads.length && visages.every((v, i) => {
      const autres = bloc.squads[i].membres.length - (bloc.squads[i].membres.some(m => m.role === 'leader') ? 1 : 0);
      return v.n === Math.min(6, autres) && !v.chevauche && v.titres && v.plus === (autres > 6 ? '+' + (autres - 6) : '');
    }), JSON.stringify(visages.slice(0, 2)));

  // Une tuile s'ouvre sur place ; une seule à la fois.
  const panneaux = page.locator(`${E} .equipe__panneau`);
  const ouvrirTuile = async (i) => { await page.locator(`${E} .equipe__tuile`).nth(i).click(); await page.waitForTimeout(700); };
  await ouvrirTuile(1);
  const sq1 = bloc.squads[1];
  const cartesPanneau = panneaux.locator('.personne-carte');
  t(`${code} : « ${sq1.nom} » s’ouvre sur ses ${sq1.membres.length} membres, le lead d’abord`,
    (await panneaux.count()) === 1 && (await page.locator(`${E} .equipe__tuile`).nth(1).getAttribute('aria-expanded')) === 'true'
    && (await cartesPanneau.locator('.personne-carte__nom').allInnerTexts()).map(n => n.trim()).sort().join('|') === nomsDe(sq1.membres)
    && (!sq1.membres.some(m => m.role === 'leader') || (await cartesPanneau.first().locator('.personne-carte__badge:not(.personne-carte__badge--referent)').count()) === 1));
  const boiteTuile = await page.locator(`${E} .equipe__tuile`).nth(1).boundingBox();
  const boitePanneau = await panneaux.boundingBox();
  t(`${code} : le panneau se pose sous la rangée de sa tuile, sur toute la largeur`,
    boitePanneau.y >= boiteTuile.y + boiteTuile.height - 1 && boitePanneau.width > boiteTuile.width * 1.5,
    JSON.stringify({ tuile: boiteTuile, panneau: boitePanneau }));
  t(`${code} : ses cartes mènent aux fiches`,
    (await cartesPanneau.locator('.personne-carte__nom').evaluateAll(l => l.map(a => a.getAttribute('href')))).every(h => fiche.test(h)));
  await ouvrirTuile(2);
  t(`${code} : ouvrir « ${bloc.squads[2].nom} » referme « ${sq1.nom} »`,
    (await panneaux.count()) === 1
    && (await page.locator(`${E} .equipe__tuile[aria-expanded="true"]`).count()) === 1
    && (await page.locator(`${E} .equipe__tuile`).nth(2).getAttribute('aria-expanded')) === 'true'
    && (await cartesPanneau.count()) === bloc.squads[2].membres.length);
  await ouvrirTuile(2);
  t(`${code} : un second clic la referme`,
    (await panneaux.count()) === 0 && (await page.locator(`${E} .equipe__tuile[aria-expanded="true"]`).count()) === 0);

  // Les référents : les personnes à solliciter en premier, en cartes — sans
  // compétence, sans plus.
  const cartesRef = page.locator(`${Z} .referents__gens .personne-carte`);
  t(`${code} : « Les référents » liste ses ${referents.size} référents, chacun vers sa fiche`,
    (await cartesRef.count()) === referents.size
    && (await cartesRef.locator('.personne-carte__nom').allInnerTexts()).map(n => n.trim()).sort().join('|') === nomsDe(membres.filter(estReferent))
    && (await cartesRef.locator('.personne-carte__nom').evaluateAll(l => l.map(a => a.getAttribute('href')))).every(h => fiche.test(h)));
  t(`${code} : aucune compétence n’y est écrite`,
    (await page.locator(`${Z} .referents .competence-puce`).count()) === 0);

  // Par porteur : une tuile par appareil du pôle — sa photo, ses gens —,
  // les plus suivis d'abord ; elle s'ouvre sur les personnes qui y travaillent.
  const P = `${Z} .porteurs-pole`;
  const tuilesP = await page.locator(`${P} .equipe`).evaluateAll(l => l.map(li => ({
    code: li.dataset.porteur, n: Number(li.querySelector('.equipe__nombre').textContent)
  })));
  const gensSur = (c) => membres.filter(m => porteurDe(m) === c);
  t(`${code} : « Par porteur » couvre ses ${codesAttendus.size} appareils, avec leur effectif`,
    tuilesP.length === codesAttendus.size && tuilesP.every(x => codesAttendus.has(x.code) && x.n === gensSur(x.code).length),
    JSON.stringify(tuilesP.slice(0, 3)));
  t(`${code} : les appareils les plus suivis d’abord`,
    tuilesP.every((x, i) => !i || tuilesP[i - 1].n >= x.n));
  const plusSuivi = tuilesP[0];
  await page.locator(`${P} .equipe__tuile`).first().click();
  await page.waitForTimeout(700);
  const panneauP = page.locator(`${P} .equipe__panneau`);
  t(`${code} : le ${plusSuivi.code} s’ouvre sur ses ${plusSuivi.n} personnes, et sur sa fiche`,
    (await panneauP.count()) === 1
    && (await panneauP.locator('.personne-carte__nom').allInnerTexts()).map(n => n.trim()).sort().join('|') === nomsDe(gensSur(plusSuivi.code))
    && (await panneauP.locator(`a.coup-oeil__lien[href="index.html#porteur=${encodeURIComponent(plusSuivi.code)}"]`).count()) === 1);
  await page.locator(`${P} .equipe__tuile`).first().click();
  await page.waitForTimeout(500);

  // Les documents du pôle : les huit plus récents en vigueur.
  const docsRendus = await page.locator('#zone-documents .pole-doc .pole-doc__titre').allInnerTexts();
  t(`${code} : « Documents du pôle » montre les ${Math.min(8, enVigueur.length)} plus récents en vigueur`,
    docsRendus.length === Math.min(8, enVigueur.length)
    && docsRendus.every((titre, i) => titre.trim() === enVigueur[i].titre), JSON.stringify(docsRendus.slice(0, 2)));
  t(`${code} : une ligne de document dit le titre, la personne, la date — ni « Nouveau », ni référence, ni type`,
    (await page.locator('#zone-documents .pole-doc__nouveau, #zone-documents .pole-doc__ref, #zone-documents .pole-doc__type').count()) === 0
    && (await page.locator('#zone-documents .pole-doc').evaluateAll(l => l.every(li => li.querySelector('.pole-doc__titre') && li.querySelector('.pole-doc__porteur') && li.querySelector('.pole-doc__date'))))
    && !/Nouveau/.test(await page.locator('#zone-documents .pole-docs__liste').innerText()));
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

console.log('\n== Espace de pôle au téléphone (390 px) ==');
{
  const ctxMobile = await nav.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  const mobile = await ctxMobile.newPage();
  mobile.on('pageerror', e => err.push(e.message));
  for (const code of ['ETIIA', 'ETIIE', 'ETIII']) {
    await mobile.goto(`${B}/${code.toLowerCase()}.html`, { waitUntil: 'networkidle' });
    await mobile.waitForTimeout(1000);
    await mobile.locator('#zone-reperes .equipes .equipe__tuile').first().click();
    await mobile.waitForTimeout(500);
    await mobile.locator('#zone-reperes .porteurs-pole .equipe__tuile').first().click();
    await mobile.waitForTimeout(700);
    const debord = await mobile.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    t(`${code} : au téléphone, le coup d’œil ne déborde pas de l’écran`, debord <= 0, `(${debord} px)`);
  }
  await ctxMobile.close();
}

console.log('\n== Tableau de bord : en-tête sur la bande et sommaire ==');
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
/* La page du service ne montre que les communications du service : celles
   des pôles se lisent dans leur espace. */
const duService = (e) => !e.pole || String(e.pole).toUpperCase() === 'ETII';
const toutes = dedup(comms.annonces.concat(comms.agenda.filter(a => a.statut !== 'a-venir' && a.type !== 'mot')).filter(duService)).length;
const auService = await page.locator('#zone-communication .kiosque__carte').count();
t(`le service liste le mot du chef et ses ${toutes} entrées passées du service (pas celles des pôles)`, auService === toutes + 1, `(${auService})`);
t('la lecture s\'ouvre sur le mot du chef', /trimestre qui se tient/i.test(await page.locator('#zone-communication .kiosque__lecture-titre').innerText()));
/* Le nom de chaque entrée, sans le compteur qui le suit. */
const sommaireService = await page.locator('.sous-nav a').evaluateAll(l => l.map(a => (a.firstChild ? a.firstChild.textContent : '').trim() + ':' + a.getAttribute('aria-current')));

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
// Le filtrage par pôle passe par un groupe de boutons radio, le seul
// filtre de la barre : le pôle (le service) est le classement du fonds,
// sans métier ni porteur.
const optionsPole = await page.evaluate(() => {
  const groupe = document.getElementById('ds-pole');
  return groupe ? [...groupe.querySelectorAll('input[type="radio"]')].map(r => r.value).filter(Boolean) : null;
});
t('le choix « pôle » propose les trois pôles',
  Array.isArray(optionsPole) && ['ETIIA', 'ETIIE', 'ETIII'].every(c => optionsPole.includes(c)),
  JSON.stringify(optionsPole));

const attenduA = docs.documents.filter(d => (d.pole || []).includes('ETIIA')).length;
await page.locator('#ds-pole .ds-pole', { hasText: 'ETIIA' }).click();
await page.waitForTimeout(800);
const n = await page.locator('#ds-resultats > *').count();
t(`choisir ETIIA filtre les résultats (${attenduA} documents concernés)`,
  n > 0 && n <= attenduA, `(${n}/${attenduA})`);
t('le choix est reflété dans l\'URL', /ETIIA/i.test(decodeURIComponent(page.url())),
  page.url().slice(-60));
t('le pôle est le seul filtre de la barre',
  (await page.locator('#ds-metier, #ds-porteur, #ds-pole').count()) === 1
  && (await page.locator('#ds-pole').count()) === 1);

console.log('\n== Navigation entre les neuf pages ==');
// La barre a six liens : le tableau de bord, les porteurs, les trois
// pôles, la recherche. faq.html, reunions.html et organigramme.html n'y
// figurent pas — on les atteint depuis un pôle — et n'ont donc AUCUNE
// entrée courante. Marquer « Tableau de bord » y serait un mensonge.
const HORS_BARRE = new Set(['faq', 'reunions', 'organigramme']);
const BARRE = 'index.html porteurs.html etiia.html etiie.html etiii.html docsearch.html';
let navOk = true;
for (const p of ['index','porteurs','etiia','etiie','etiii','reunions','organigramme','faq','docsearch']) {
  await page.goto(`${B}/${p}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const liens = (await page.locator('nav.site-nav a').evaluateAll((l) => l.map((a) => a.getAttribute('href')))).join(' ');
  const courant = await page.locator('nav.site-nav [aria-current="page"]').count();
  const attendu = HORS_BARRE.has(p) ? 0 : 1;
  if (liens !== BARRE || courant !== attendu) { navOk = false; t(`${p}.html : nav des 6 liens, ${attendu} courant`, false, `(${liens} ; ${courant} courant)`); }
}
t('les neuf pages ont la même navigation, porteurs compris, sans lien Organigramme', navOk);

// Ouvert depuis un pôle, l'organigramme désigne ce pôle dans la barre.
await page.goto(`${B}/organigramme.html#pole=ETIIE`, { waitUntil: 'networkidle' });
await page.waitForTimeout(700);
t('organigramme.html#pole=ETIIE : « ETIIE » est la page courante de la barre',
  (await page.locator('nav.site-nav a[aria-current="page"]').getAttribute('href').catch(() => '')) === 'etiie.html');

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

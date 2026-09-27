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
// une ligne, « Qui peut m'aider ? » (un champ qui répond pendant la frappe
// par des cartes de personnes), les équipes en tuiles qui s'ouvrent sur
// place, l'index des référents — et les documents du pôle, les plus récents
// en vigueur. Tout est calculé depuis organigramme.json, flotte.json et
// documents.json, sans rien d'inventé.
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
  t(`${code} : sommaire Communication, À venir, En un coup d’œil, Documents, FAQ`,
    sousNav.join('|') === 'Communication|À venir|En un coup d’œil|Documents|FAQ', `(${sousNav.join('|')})`);
  // « À venir » : la ligne seule — plus de carte « prochain rendez-vous »
  // ni de compte à rebours —, avec les rendez-vous du pôle et ceux du
  // service, et d'aucun autre pôle.
  const polesVus = await page.locator('#zone-agenda .agenda__rdv').evaluateAll(l => l.map(e => e.dataset.pole));
  t(`${code} : « À venir » est une ligne, sans carte ni compte à rebours`,
    (await page.locator('#zone-agenda .agenda').count()) === 1
    && (await page.locator('#zone-agenda [class*="agenda__prochain"]').count()) === 0
    && (await page.locator('#zone-agenda .agenda__scene, #zone-agenda .agenda--vide').count()) === 1);
  t(`${code} : « À venir » ne montre que le pôle et le service`,
    polesVus.every(p => p === code || p === 'ETII'), JSON.stringify(polesVus));
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

  // « Qui peut m'aider ? » : sans recherche, rien que le champ et ses
  // suggestions — les compétences et les appareils les plus partagés.
  const champ = page.locator(`#qui-${code.toLowerCase()}-champ`);
  t(`${code} : « Qui peut m’aider ? » ouvre sur un champ, sans résultat affiché`,
    (await champ.count()) === 1 && (await page.locator(`${Z} .qui__resultats`).isHidden()));
  // Pas de phrase d'aide sous le titre : le texte d'attente du champ la dit
  // déjà ; elle reste pour les lecteurs d'écran, masquée.
  t(`${code} : pas de phrase d’aide visible sous « Qui peut m’aider ? »`,
    (await page.locator(`${Z} .qui > p:not(.visuellement-cache)`).count()) === 0
    && (await page.locator(`#${await champ.getAttribute('aria-describedby')}.visuellement-cache`).count()) === 1);
  const frequences = (valeurs) => [...valeurs.reduce((mp, v) => mp.set(v, (mp.get(v) || 0) + 1), new Map())]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'fr', { numeric: true })).map(([v]) => v);
  const suggestionsAttendues = frequences(membres.flatMap(m => (m.competences || []).map(c => c.nom))).slice(0, 4)
    .concat(frequences(membres.map(m => m.porteur || m.perimetre).filter(c => c && c.toUpperCase() !== 'TRANSVERSE')).slice(0, 3));
  const suggestions = await page.locator(`${Z} .qui > .qui__suggestions:not(.qui__porteurs) .qui__suggestion`).evaluateAll(l => l.map(b => b.dataset.suggestion));
  t(`${code} : suggestions — ${suggestionsAttendues.join(', ')}`,
    suggestions.join('|') === suggestionsAttendues.join('|'), `(${suggestions.join('|')})`);

  // La recherche filtre les personnes pendant la frappe : toutes celles qui
  // correspondent, et elles seules, chacune vers sa fiche.
  const cartes = page.locator(`${Z} .qui__resultats .personne-carte`);
  const toutVoir = async () => {
    if (await page.locator(`${Z} .qui__plus`).isVisible()) { await page.locator(`${Z} .qui__plus`).click(); await page.waitForTimeout(300); }
  };
  const nomsVisibles = async () => (await cartes.locator('.personne-carte__nom').allInnerTexts()).map(n => n.trim()).sort().join('|');
  await champ.fill('harnais');
  await page.waitForTimeout(300);
  const harnais = membres.filter(m => texteDe(m).includes('harnais'));
  const compteHarnais = await page.locator(`${Z} .qui__compte`).innerText();
  await toutVoir();
  t(`${code} : « harnais » trouve ses ${harnais.length} personnes, et le dit`,
    (await nomsVisibles()) === nomsDe(harnais) && compteHarnais.startsWith(harnais.length + ' personne'),
    `(${await cartes.count()} cartes, « ${compteHarnais} »)`);
  const refHarnais = membres.filter(m => (m.competences || []).some(c => c.niveau === 'referent' && sansAccents(c.nom).includes('harnais'))).map(m => m.nom);
  t(`${code} : un référent passe en tête`,
    !refHarnais.length || refHarnais.includes((await cartes.first().locator('.personne-carte__nom').innerText()).trim()));
  t(`${code} : chaque carte mène à la fiche de la personne`,
    (await cartes.locator('.personne-carte__nom').evaluateAll(l => l.map(a => a.getAttribute('href')))).every(h => fiche.test(h)));
  t(`${code} : le mot cherché est marqué`, (await page.locator(`${Z} .qui__resultats .qui__marque`).count()) > 0);

  // Au-delà de douze, « Voir les N autres » ; toutes les cartes ensuite. Un
  // reste de trois cartes ou moins se montre d'emblée, sans bouton.
  await champ.fill('ingenieur');
  await page.waitForTimeout(300);
  const ingenieurs = membres.filter(m => texteDe(m).includes('ingenieur'));
  const avantPlus = await cartes.count();
  const attenduAvant = ingenieurs.length <= 15 ? ingenieurs.length : 12;
  await toutVoir();
  t(`${code} : « ingénieur » montre ${attenduAvant} cartes, puis les ${ingenieurs.length} sur demande`,
    avantPlus === attenduAvant && (await cartes.count()) === ingenieurs.length, `(${avantPlus} → ${await cartes.count()})`);

  // Un nombre seul ne compte qu'en début de mot : « 1 » trouve « Squad 1 »
  // ou « Personne 157 », pas le « 1 » de « H175 », qui n'est pas marqué.
  await champ.fill('1');
  await page.waitForTimeout(300);
  await toutVoir();
  const debutDeMot = (v) => /(^|[^a-z0-9])1/.test(sansAccents(v));
  const avecUn = membres.filter(m => [m.nom, m.poste, porteurDe(m), squadDe(m)].concat((m.competences || []).map(c => c.nom)).some(debutDeMot));
  t(`${code} : « 1 » trouve ses ${avecUn.length} personnes (début de mot), sans marque dans un code d’appareil`,
    (await nomsVisibles()) === nomsDe(avecUn) && (await page.locator(`${Z} .qui__resultats .appareil-puce .qui__marque`).count()) === 0,
    `(${await cartes.count()} cartes)`);
  // Une requête de plusieurs mots se marque d'un trait là où elle se lit.
  const nomAvecChiffre = membres.map(m => m.nom).find(n => /\s\d+$/.test(n));
  if (nomAvecChiffre) {
    await champ.fill(nomAvecChiffre);
    await page.waitForTimeout(300);
    t(`${code} : « ${nomAvecChiffre} » vient en tête, marqué d’un seul trait`,
      (await cartes.first().locator('.personne-carte__nom').innerText()).trim() === nomAvecChiffre
      && (await cartes.first().locator('.personne-carte__nom .qui__marque').allInnerTexts()).join('|') === nomAvecChiffre);
  }

  // Un code d'appareil : ceux qui le suivent, et eux seuls (H160 ≠ H160M),
  // avec le lien vers sa fiche sur le tableau de bord.
  await champ.fill('H160');
  await page.waitForTimeout(300);
  await toutVoir();
  const surH160 = membres.filter(m => porteurDe(m) === 'H160');
  t(`${code} : « H160 » montre ses ${surH160.length} personnes et le lien vers sa fiche`,
    (await nomsVisibles()) === nomsDe(surH160)
    && (await page.locator(`${Z} .qui__actions a[href="index.html#porteur=H160"]`).count()) === 1);
  t(`${code} : la puce d’appareil d’une carte mène à la fiche du porteur`,
    (await cartes.locator('a.appareil-puce').evaluateAll(l => l.map(a => a.getAttribute('href')))).every(h => h === 'index.html#porteur=H160'));

  await champ.fill('zzzz-rien');
  await page.waitForTimeout(300);
  t(`${code} : une recherche sans réponse le dit`,
    (await cartes.count()) === 0 && (await page.locator(`${Z} .qui__rien`).isVisible()));
  await champ.press('Escape');
  await page.waitForTimeout(200);
  t(`${code} : Échap vide le champ et referme les résultats`,
    (await champ.inputValue()) === '' && (await page.locator(`${Z} .qui__resultats`).isHidden()));

  // Une suggestion se cherche d'un clic, et se relâche d'un autre.
  const premiere = page.locator(`${Z} .qui > .qui__suggestions:not(.qui__porteurs) .qui__suggestion`).first();
  await premiere.click();
  await page.waitForTimeout(300);
  // Une compétence exacte ramène ceux qui la pratiquent, et eux seuls.
  const avecPremiere = membres.filter(m => (m.competences || []).some(c => c.nom === suggestionsAttendues[0]));
  t(`${code} : la suggestion « ${suggestionsAttendues[0]} » se cherche d’un clic (${avecPremiere.length} personnes)`,
    (await champ.inputValue()) === suggestionsAttendues[0] && (await premiere.getAttribute('aria-pressed')) === 'true'
    && (await page.locator(`${Z} .qui__compte`).innerText()).startsWith(avecPremiere.length + ' personne'));
  // Une compétence exacte se marque sur sa seule puce, en entier : pas mot
  // à mot, ni dans les rôles (« Lead technique »).
  const marques = await page.locator(`${Z} .qui__resultats .qui__marque`).evaluateAll(l => l.map(m => ({
    texte: m.textContent, puce: Boolean(m.closest('.competence-puce__nom'))
  })));
  t(`${code} : « ${suggestionsAttendues[0]} » est marquée en entier sur sa puce, et nulle part ailleurs`,
    marques.length === Math.min(avecPremiere.length, 12 + (avecPremiere.length <= 15 ? 3 : 0))
    && marques.every(m => m.puce && m.texte === suggestionsAttendues[0]), JSON.stringify(marques.slice(0, 3)));
  await premiere.click();
  await page.waitForTimeout(300);
  t(`${code} : un second clic la relâche`, (await champ.inputValue()) === '' && (await premiere.getAttribute('aria-pressed')) === 'false');

  // Les équipes : une tuile par squad — son nom, son effectif, son lead.
  const tuiles = await page.locator(`${Z} .equipe__tuile`).evaluateAll(l => l.map(b => ({
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
  const visages = await page.locator(`${Z} .equipe__visages`).evaluateAll(l => l.map(v => {
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
  const panneaux = page.locator(`${Z} .equipe__panneau`);
  const ouvrirTuile = async (i) => { await page.locator(`${Z} .equipe__tuile`).nth(i).click(); await page.waitForTimeout(700); };
  await ouvrirTuile(1);
  const sq1 = bloc.squads[1];
  const cartesPanneau = panneaux.locator('.personne-carte');
  t(`${code} : « ${sq1.nom} » s’ouvre sur ses ${sq1.membres.length} membres, le lead d’abord`,
    (await panneaux.count()) === 1 && (await page.locator(`${Z} .equipe__tuile`).nth(1).getAttribute('aria-expanded')) === 'true'
    && (await cartesPanneau.locator('.personne-carte__nom').allInnerTexts()).map(n => n.trim()).sort().join('|') === nomsDe(sq1.membres)
    && (!sq1.membres.some(m => m.role === 'leader') || (await cartesPanneau.first().locator('.personne-carte__badge').count()) === 1));
  const boiteTuile = await page.locator(`${Z} .equipe__tuile`).nth(1).boundingBox();
  const boitePanneau = await panneaux.boundingBox();
  t(`${code} : le panneau se pose sous la rangée de sa tuile, sur toute la largeur`,
    boitePanneau.y >= boiteTuile.y + boiteTuile.height - 1 && boitePanneau.width > boiteTuile.width * 1.5,
    JSON.stringify({ tuile: boiteTuile, panneau: boitePanneau }));
  t(`${code} : ses cartes mènent aux fiches`,
    (await cartesPanneau.locator('.personne-carte__nom').evaluateAll(l => l.map(a => a.getAttribute('href')))).every(h => fiche.test(h)));
  await ouvrirTuile(2);
  t(`${code} : ouvrir « ${bloc.squads[2].nom} » referme « ${sq1.nom} »`,
    (await panneaux.count()) === 1
    && (await page.locator(`${Z} .equipe__tuile[aria-expanded="true"]`).count()) === 1
    && (await page.locator(`${Z} .equipe__tuile`).nth(2).getAttribute('aria-expanded')) === 'true'
    && (await cartesPanneau.count()) === bloc.squads[2].membres.length);
  await ouvrirTuile(2);
  t(`${code} : un second clic la referme`,
    (await panneaux.count()) === 0 && (await page.locator(`${Z} .equipe__tuile[aria-expanded="true"]`).count()) === 0);

  // Les référents : une puce par compétence qui a un référent ; la choisir
  // montre qui solliciter — ses référents, et eux seuls.
  const puces = page.locator(`${Z} .referents__puce`);
  t(`${code} : l’index couvre les ${competencesAvecReferent.size} compétences qui ont un référent, par leur seul nom`,
    (await puces.count()) === competencesAvecReferent.size
    && (await puces.evaluateAll(l => l.map(b => b.dataset.competence))).every(c => competencesAvecReferent.has(c))
    && (await puces.evaluateAll(l => l.every(b => b.textContent.trim() === b.dataset.competence && !b.querySelector('.avatar')))));
  // Le détail se pose sous l'index, sur toute sa largeur ; jusqu'à trois
  // référents tiennent sur une rangée.
  const boiteIndex = await page.locator(`${Z} .referents__index`).boundingBox();
  const boiteDetail = await page.locator(`${Z} .referents__detail`).boundingBox();
  const hauts = await page.locator(`${Z} .referents__gens > li`).evaluateAll(l => [...new Set(l.map(c => Math.round(c.getBoundingClientRect().top)))]);
  t(`${code} : le détail se pose sous l’index, ses référents sur une rangée`,
    boiteDetail.y >= boiteIndex.y + boiteIndex.height - 1 && Math.abs(boiteDetail.width - boiteIndex.width) < 2
    && (hauts.length === 1 || (await page.locator(`${Z} .referents__gens > li`).count()) > 3), JSON.stringify({ boiteIndex, boiteDetail, hauts }));
  const refsDe = (nom) => membres.filter(m => (m.competences || []).some(c => c.nom === nom && c.niveau === 'referent'));
  const detailNoms = async () => (await page.locator(`${Z} .referents__detail .personne-carte__nom`).allInnerTexts()).map(n => n.trim()).sort().join('|');
  const nomPremiere = await puces.first().getAttribute('data-competence');
  t(`${code} : la première compétence est montrée d’office, avec ses référents`,
    (await puces.first().getAttribute('aria-pressed')) === 'true' && (await detailNoms()) === nomsDe(refsDe(nomPremiere)));
  const derniere = puces.last();
  const nomDerniere = await derniere.getAttribute('data-competence');
  await derniere.click();
  await page.waitForTimeout(400);
  t(`${code} : choisir « ${nomDerniere} » montre ses ${refsDe(nomDerniere).length} référent(s)`,
    (await derniere.getAttribute('aria-pressed')) === 'true'
    && (await page.locator(`${Z} .referents__puce[aria-pressed="true"]`).count()) === 1
    && (await page.locator(`${Z} .referents__competence`).innerText()).trim() === nomDerniere
    && (await detailNoms()) === nomsDe(refsDe(nomDerniere)));
  await puces.nth(1).hover();
  await page.waitForTimeout(500);
  t(`${code} : à la souris, s’attarder sur une compétence la montre`,
    (await page.locator(`${Z} .referents__competence`).innerText()).trim() === (await puces.nth(1).getAttribute('data-competence')));
  t(`${code} : les référents mènent à leur fiche`,
    (await page.locator(`${Z} .referents__detail .personne-carte__nom`).evaluateAll(l => l.map(a => a.getAttribute('href')))).every(h => fiche.test(h)));
  // « Les N personnes qui la pratiquent » : la recherche, et le focus sur
  // son compte — la suite au clavier part des résultats.
  const tous = page.locator(`${Z} .referents__tous`);
  if (await tous.count()) {
    const competenceTous = (await page.locator(`${Z} .referents__competence`).innerText()).trim();
    await tous.focus();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(700);
    t(`${code} : « ${(await tous.innerText()).trim()} » cherche « ${competenceTous} » et y amène le focus`,
      (await champ.inputValue()) === competenceTous
      && (await page.evaluate(() => document.activeElement && document.activeElement.classList.contains('qui__compte'))));
    await champ.fill('');
  }

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

console.log('\n== Espace de pôle au téléphone (390 px) ==');
{
  const ctxMobile = await nav.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  const mobile = await ctxMobile.newPage();
  mobile.on('pageerror', e => err.push(e.message));
  for (const code of ['ETIIA', 'ETIIE', 'ETIII']) {
    await mobile.goto(`${B}/${code.toLowerCase()}.html`, { waitUntil: 'networkidle' });
    await mobile.waitForTimeout(1000);
    await mobile.fill(`#qui-${code.toLowerCase()}-champ`, 'harnais');
    await mobile.locator('#zone-reperes .equipe__tuile').first().click();
    await mobile.locator('#zone-reperes .referents__puce').last().click();
    await mobile.waitForTimeout(700);
    const debord = await mobile.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    t(`${code} : au téléphone, le coup d’œil ne déborde pas de l’écran`, debord <= 0, `(${debord} px)`);
    // Les rangées qui défilent de côté s'estompent au bord où il reste à voir.
    await mobile.fill(`#qui-${code.toLowerCase()}-champ`, '');
    const rangees = await mobile.locator('#zone-reperes .qui__suggestions:not(.qui__porteurs), #zone-reperes .referents__index').evaluateAll(l => l.map(r => {
      r.scrollLeft = 0; r.dispatchEvent(new Event('scroll'));
      const deborde = r.scrollWidth > r.clientWidth + 2;
      return { deborde, apres: r.hasAttribute('data-apres'), masque: getComputedStyle(r).maskImage || getComputedStyle(r).webkitMaskImage || 'none' };
    }));
    t(`${code} : au téléphone, suggestions et index des référents défilent avec un bord estompé`,
      rangees.length === 2 && rangees.every(r => r.deborde && r.apres && r.masque !== 'none'), JSON.stringify(rangees));
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

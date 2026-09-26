// Test de bout en bout de la recherche documentaire, dans un vrai navigateur.
//
//   1. lancer le site :  python3 -m http.server 8111
//   2. npm install playwright
//   3. node tests/docsearch.e2e.mjs
//
// Vérifie ce que l'audit statique ne peut pas voir : le comportement réel
// des facettes, du clavier, de l'URL partageable et du surlignage.

import { chromium } from 'playwright';
const B = process.env.BASE || 'http://localhost:8111';
const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport:{width:1440,height:900} });
const page = await ctx.newPage();
const erreurs = [];
page.on('pageerror', e => erreurs.push(e.message));
await page.goto(B + '/docsearch.html', {waitUntil:'networkidle'});
await page.waitForTimeout(600);

let ok=0, ko=0;
const t=(n,c,d='')=>{ if(c){ok++;console.log(`  OK    ${n}`);} else {ko++;console.log(`  ÉCHEC ${n} ${d}`);} };

console.log('== Facettes ==');
// Le document se classe par son pôle — le service qui le tient — et par
// son type (les tuiles d'exploration). Plus de menu Métier ni Porteur :
// le pôle se choisit d'un clic, dans un groupe de boutons radio nommé
// « Pôle », sous la barre.
const menus = await page.evaluate(() => {
  const g = document.getElementById('ds-pole');
  return {
    groupe: g ? g.tagName + '|' + (g.querySelector('legend') || {}).textContent : null,
    pole: g ? [...g.querySelectorAll('input[type="radio"]')].map(r => r.value) : null,
    libelles: g ? [...g.querySelectorAll('.ds-pole')].map(l => l.textContent.replace(/\s+/g, ' ').trim()) : null,
    coche: g ? (g.querySelector('input:checked') || {}).value : null,
    anciens: ['ds-metier', 'ds-porteur'].filter(id => document.getElementById(id)),
    selects: document.querySelectorAll('#ds-pole select, .ds-menus select').length
  };
});
t('un seul filtre : le groupe « Pôle », sans menu déroulant', menus.groupe === 'FIELDSET|Pôle'
  && menus.selects === 0 && menus.anciens.length === 0, JSON.stringify(menus));
t('il propose « Tous les pôles » (coché) et les trois pôles du service',
  JSON.stringify(menus.pole) === JSON.stringify(['', 'ETIIA', 'ETIIE', 'ETIII']) && menus.coche === ''
  && JSON.stringify(menus.libelles) === JSON.stringify(['Tous les pôles', 'ETIIA', 'ETIIE', 'ETIII']), JSON.stringify(menus));

console.log('\n== Un filtre restreint bien les résultats ==');
// Une requête reste active pendant la comparaison : sans requête NI filtre,
// la page revient à son écran d'accueil et n'affiche aucune liste — zéro
// résultat y serait le comportement correct, pas un point de comparaison.
await page.locator('#ds-champ').fill('norme');
await page.waitForTimeout(700);
const sansFiltre = await page.locator('#ds-resultats > *').count();
// Les propositions de la frappe se referment d'abord (Échap), comme on le
// ferait avant de cliquer dessous.
await page.keyboard.press('Escape');
await page.waitForTimeout(200);
await page.locator('#ds-pole .ds-pole', { hasText: 'ETIIA' }).click();
await page.waitForTimeout(700);
const avecFiltre = await page.locator('#ds-resultats > *').count();
t('un clic sur un pôle réduit le nombre de résultats',
  avecFiltre > 0 && avecFiltre < sansFiltre, `(${avecFiltre} avec, ${sansFiltre} sans)`);
const hashPole = decodeURIComponent(await page.evaluate(() => location.hash));
t('le pôle choisi est coché, écrit dans l’URL, sans jeton en double sous la barre',
  (await page.locator('#ds-pole input:checked').getAttribute('value')) === 'ETIIA'
  && (await page.locator('#ds-jetons .facette').count()) === 0 && /pole=ETIIA/.test(hashPole), hashPole);
// Au clavier : les flèches passent d'un pôle à l'autre, et filtrent.
await page.locator('#ds-pole input:checked').focus();
await page.keyboard.press('ArrowRight');
await page.waitForTimeout(600);
t('au clavier, → passe au pôle suivant et filtre',
  (await page.locator('#ds-pole input:checked').getAttribute('value')) === 'ETIIE'
  && (await page.locator('#ds-resultats > li').evaluateAll(l => l.every(c => /Pôle ETIIE/.test(c.textContent)))));
t('l’anneau de focus est visible sur la pastille',
  await page.evaluate(() => {
    const r = document.querySelector('#ds-pole input:focus-visible');
    return !!r && getComputedStyle(r.nextElementSibling).outlineStyle === 'solid';
  }));
await page.locator('#ds-pole .ds-pole', { hasText: 'Tous' }).click();
await page.waitForTimeout(500);
t('« Tous les pôles » lève le filtre', (await page.locator('#ds-resultats > *').count()) === sansFiltre);
await page.locator('#ds-champ').fill('');
await page.waitForTimeout(600);

console.log('\n== Les cinq tuiles d\'exploration ==');
const tuiles = await page.locator('[data-action="filtrer-type"]').count();
t('cinq tuiles d\'exploration par type', tuiles === 5, `(${tuiles})`);
const txtPerim = await page.locator('body').innerText();
t('la page mentionne le fonds documentaire', /document/i.test(txtPerim));

console.log('\n== Recherche au fil de la frappe ==');
const champ = page.locator('input[type="search"], input[role="combobox"], #recherche').first();
await champ.fill('harnais');
await page.waitForTimeout(400);
const nRes = await page.locator('#ds-resultats > *').count();
t('"harnais" donne des résultats', nRes>0, `(${nRes})`);
const surlignes = await page.locator('mark').count();
t('les termes sont surlignés', surlignes>0, `(${surlignes} <mark>)`);

console.log('\n== Tolérance aux fautes dans la page ==');
await champ.fill('conecteur');
await page.waitForTimeout(400);
const nFaute = await page.locator('#ds-resultats > *').count();
t('"conecteur" trouve quand même', nFaute>0, `(${nFaute})`);

console.log('\n== Aucun résultat ==');
await champ.fill('zzzzzqqqq');
await page.waitForTimeout(400);
const corps = await page.locator('main').innerText();
t('état "aucun résultat" affiché', /aucun|rien|pas de r/i.test(corps));

console.log('\n== Navigation clavier ==');
await champ.fill('norme');
await page.waitForTimeout(400);
// Deux mécanismes sont acceptables pour parcourir des résultats au clavier :
// déplacer le focus réel (roving tabindex) ou pointer aria-activedescendant.
// Le test porte sur le comportement, pas sur le mécanisme retenu.
const positionActive = () => page.evaluate(() => {
  const champ = document.getElementById('ds-champ');
  const parAttribut = champ && champ.getAttribute('aria-activedescendant');
  if (parAttribut) return 'add:' + parAttribut;
  const focalise = document.activeElement;
  if (focalise && focalise.closest && focalise.closest('#ds-resultats')) return 'focus:' + focalise.id;
  return null;
});
const avantFleche = await positionActive();
await champ.press('ArrowDown');
await page.waitForTimeout(200);
const apres1 = await positionActive();
t('ArrowDown sélectionne un résultat', !!apres1 && apres1 !== avantFleche, `(${avantFleche} -> ${apres1})`);
await page.keyboard.press('ArrowDown');
await page.waitForTimeout(200);
const apres2 = await positionActive();
t('ArrowDown déplace la sélection au suivant', !!apres2 && apres2 !== apres1, `(${apres1} -> ${apres2})`);
// La sélection peut viser la liste de SUGGESTIONS (motif combobox, le
// focus restant dans le champ) ou la liste de RÉSULTATS (tabindex mobile).
// Les deux sont valides : on vérifie que la cible existe et appartient bien
// à une liste, sans présumer laquelle.
const idActif = (apres2 || '').split(':')[1];
if (idActif) t('l\'élément sélectionné appartient à une liste',
  await page.evaluate(id => {
    const e = document.getElementById(id);
    return !!e && !!(e.closest('#ds-resultats') || e.closest('[role="listbox"]'));
  }, idActif), `(${idActif})`);

console.log('\n== Annonce aux lecteurs d\'écran ==');
await champ.fill('harnais');
await page.waitForTimeout(2200);   // l'annonce est volontairement différée
const annonce = await page.evaluate(() =>
  [...document.querySelectorAll('[aria-live]')].map(r => r.textContent.trim()).join(' '));
t('le nombre de résultats est annoncé', /\d+\s+résultats?/.test(annonce), `("${annonce}")`);
await champ.fill('zzzzqqqq');
await page.waitForTimeout(2200);
const annonce2 = await page.evaluate(() =>
  [...document.querySelectorAll('[aria-live]')].map(r => r.textContent.trim()).join(' '));
t('l\'absence de résultat est annoncée', /aucun/i.test(annonce2), `("${annonce2}")`);

console.log('\n== URL partageable ==');
await champ.fill('essai');
await page.waitForTimeout(500);
const hash = page.url().split('#')[1]||'';
t('la requête est dans le hash', /essai/.test(decodeURIComponent(hash)), `(#${hash})`);
const url2 = page.url();
await page.goto('about:blank'); await page.goto(url2, {waitUntil:'networkidle'});
await page.waitForTimeout(700);
const champ2 = page.locator('input[type="search"], input[role="combobox"], #recherche').first();
t('la requête est restaurée au rechargement', (await champ2.inputValue())==='essai', `("${await champ2.inputValue()}")`);

console.log('\n== Documents sans lien ==');
await champ2.fill('sur demande');
await page.waitForTimeout(400);
const corps2 = await page.locator('main').innerText();
t('les documents sans lien sont signalés', /sur demande/i.test(corps2) && /Lien\s*:\s*à renseigner/i.test(corps2));

console.log('\n== La chaîne de remplacement ==');
// `remplacePar` désigne la révision en vigueur. Une révision remplacée quitte
// le classement d'une requête en langage naturel — c'est le besoin n°1 du
// service, « retrouver un document ET sa dernière version » — mais elle
// reste atteignable par sa référence exacte et en parcourant tout le fonds.
const refsRendues = () => page.evaluate(() =>
  [...document.querySelectorAll('#ds-resultats > li')].map(c => ({
    ref: (c.querySelector('.badge--carre') || {}).textContent || '',
    titre: (c.querySelector('.ds-carte__titre') || {}).textContent || '',
    remplacant: (c.querySelector('.ds-carte__remplacant') || {}).textContent || null
  })));

await champ2.fill('routage harnais');
await page.waitForTimeout(700);
const famille = await refsRendues();
t('la révision en vigueur du guide de routage sort',
  famille.some(c => c.ref === 'ETII-TEC-032'), JSON.stringify(famille.map(c => c.ref)));
t('ses révisions remplacées ne sortent pas',
  !famille.some(c => c.ref === 'ETII-TEC-031' || c.ref === 'ETII-TEC-001'),
  JSON.stringify(famille.map(c => c.ref)));

// Le panneau de propositions est l'endroit du clic le plus rapide : il ne
// doit pas non plus proposer une version périmée.
const proposees = await page.evaluate(() =>
  [...document.querySelectorAll('.ds-suggestion')].map(s => s.textContent));
t('aucune proposition du champ ne porte « indice B »',
  !proposees.some(txt => /indice B/.test(txt)), JSON.stringify(proposees));

// « je cherche ETII-PRO-035 » est un geste légitime : justifier une décision
// passée, relire ce qui était écrit à l'époque.
await champ2.fill('ETII-PRO-035');
await page.waitForTimeout(700);
const exacte = await refsRendues();
const carteExacte = exacte.find(c => c.ref === 'ETII-PRO-035');
t('une référence exacte ramène la révision remplacée', !!carteExacte,
  JSON.stringify(exacte.slice(0, 4).map(c => c.ref)));
t('sa carte pointe la révision en vigueur',
  !!carteExacte && carteExacte.remplacant === 'ETII-PRO-036',
  JSON.stringify(carteExacte));

// « Parcourir tout le fonds » assume de montrer le fonds entier.
await page.goto(B + '/docsearch.html#tout=1', {waitUntil:'networkidle'});
await page.waitForTimeout(900);
const fonds = await refsRendues();
t('parcourir tout le fonds montre aussi les révisions remplacées',
  fonds.length === 72 && fonds.filter(c => c.remplacant).length === 36,
  `(${fonds.length} cartes, ${fonds.filter(c => c.remplacant).length} remplacées)`);

console.log('\n== Le pôle classe le document, sans porteur ni métier ==');
// Le fonds entier est à l'écran (#tout=1) : chaque carte dit son pôle, et
// aucune ne parle plus du porteur du document ni de ses métiers.
const cartesFonds = await page.evaluate(() => {
  const cartes = [...document.querySelectorAll('#ds-resultats > li')];
  return {
    cartes: cartes.length,
    avecPole: cartes.filter(c => c.querySelector('.badge--pole')).length,
    polesLus: [...new Set(cartes.flatMap(c => [...c.querySelectorAll('.badge--pole')].map(b => b.textContent.trim())))].sort(),
    porteur: cartes.filter(c => c.querySelector('.ds-carte__porteur') || /porteur\s*:/i.test(c.textContent)).length,
    metier: cartes.filter(c => /métier/i.test(c.textContent)).length
  };
});
t('chaque carte porte son pôle, écrit en toutes lettres',
  cartesFonds.cartes === 72 && cartesFonds.avecPole === 72
  && JSON.stringify(cartesFonds.polesLus) === JSON.stringify(['Pôle ETIIA', 'Pôle ETIIE', 'Pôle ETIII']), JSON.stringify(cartesFonds));
t('aucune carte ne parle du porteur ni du métier', cartesFonds.porteur === 0 && cartesFonds.metier === 0, JSON.stringify(cartesFonds));

// Le nom d'une personne n'est plus indexé : le taper ne ramène rien.
await page.goto(B + '/docsearch.html#q=' + encodeURIComponent('Personne 08'), {waitUntil:'networkidle'});
await page.waitForTimeout(900);
t('le nom d’un porteur ne ramène plus de document', (await page.locator('#ds-resultats > li').count()) === 0
  && /Aucun document/i.test(await page.locator('main').innerText()));

// Les mots d'un ancien métier restent cherchables : « harnais » trouve
// toujours les documents de harnais, même sans le mot dans leur titre.
await page.goto(B + '/docsearch.html#q=harnais', {waitUntil:'networkidle'});
await page.waitForTimeout(900);
t('« harnais » trouve encore les documents du domaine', (await page.locator('#ds-resultats > li').count()) >= 8,
  `(${await page.locator('#ds-resultats > li').count()})`);
// Aucun résultat ne paraît tombé du ciel : une carte qui ne montre le mot
// ni dans son titre, ni dans sa référence, ni dans son extrait le dit sur
// une ligne « Sujet : Harnais », le mot surligné.
const pourquoi = await page.locator('#ds-resultats > li').evaluateAll(l => l.map(c => ({
  titre: c.querySelector('.ds-carte__titre').textContent.slice(0, 40),
  marques: c.querySelectorAll('mark').length,
  sujet: c.querySelector('.ds-carte__sujet').hidden ? '' : c.querySelector('.ds-carte__sujet').textContent
})));
t('chaque carte montre ce qui l’a fait sortir, surligné', pourquoi.every(c => c.marques > 0), JSON.stringify(pourquoi.filter(c => !c.marques)));
t('par la ligne « Sujet » quand le mot n’est pas à l’écran',
  pourquoi.some(c => c.sujet === 'Sujet : Harnais'), JSON.stringify(pourquoi.map(c => c.sujet)));

// Un ancien lien partagé : ses clés métier / porteur sont ignorées sans
// erreur, le pôle s'applique, et l'URL réécrite ne les porte plus.
await page.goto('about:blank');
await page.goto(B + '/docsearch.html#q=norme&metier=Harnais&porteur=Personne%2008&pole=ETIIA', {waitUntil:'networkidle'});
await page.waitForTimeout(1200);
const ancien = await page.evaluate(() => ({
  pole: (document.querySelector('#ds-pole input:checked') || {}).value,
  jetons: [...document.querySelectorAll('#ds-jetons .facette')].map(j => j.textContent.replace(/\s+/g, ' ').trim()),
  cartes: document.querySelectorAll('#ds-resultats > li').length,
  horsPole: [...document.querySelectorAll('#ds-resultats > li')].filter(c => !/Pôle ETIIA/.test(c.textContent)).length,
  hash: decodeURIComponent(location.hash)
}));
t('un ancien lien métier / porteur s’ouvre filtré par pôle seulement',
  ancien.pole === 'ETIIA' && ancien.jetons.length === 0
  && ancien.cartes > 0 && ancien.horsPole === 0, JSON.stringify(ancien));
t('et l’URL réécrite ne porte plus ni métier ni porteur',
  !/metier|porteur/.test(ancien.hash) && /pole=ETIIA/.test(ancien.hash), ancien.hash);

console.log('\n== La requête échouée amorce la proposition ==');
await page.goto(B + '/docsearch.html', {waitUntil:'networkidle'});
await page.waitForTimeout(700);
const champ3 = page.locator('#ds-champ');
await champ3.fill('zircogrommelin');
await page.waitForTimeout(1200);
const boutonEchec = await page.evaluate(() =>
  [...document.querySelectorAll('[data-action="proposer"]')]
    .filter(b => b.offsetParent !== null).map(b => b.textContent));
t('le bouton dit qu\'il signale CE document manquant',
  boutonEchec.length === 1 && boutonEchec[0] === 'Signaler ce document manquant',
  JSON.stringify(boutonEchec));
await page.evaluate(() => {
  const b = [...document.querySelectorAll('[data-action="proposer"]')]
    .find(x => x.offsetParent !== null);
  if (b) b.click();
});
await page.waitForTimeout(600);
const titreAmorce = await page.evaluate(() => {
  const champ = document.querySelector('[role="dialog"] input[type="text"]');
  return champ ? champ.value : null;
});
t('le titre est pré-rempli avec la requête échouée', titreAmorce === 'zircogrommelin',
  JSON.stringify(titreAmorce));
const champsProposition = await page.evaluate(() => {
  const d = document.querySelector('[role="dialog"]');
  const etiquettes = d ? [...d.querySelectorAll('label, legend')].map(l => l.textContent.trim()) : [];
  const pole = d ? [...d.querySelectorAll('select')].find(s => [...s.options].some(o => o.value === 'ETIIE')) : null;
  return { etiquettes, pole: !!pole };
});
t('la proposition demande le pôle concerné, plus le porteur ni les métiers',
  champsProposition.pole && champsProposition.etiquettes.some(e => /Pôle concerné/.test(e))
  && !champsProposition.etiquettes.some(e => /Porteur|Métier/i.test(e)), JSON.stringify(champsProposition));
await page.keyboard.press('Escape');
await page.waitForTimeout(300);

t('aucune erreur JavaScript', erreurs.length===0, erreurs.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

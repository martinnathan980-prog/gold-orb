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
// Le filtrage se fait par trois menus déroulants et par les tuiles
// d'exploration : c'est la mise en page voulue par le service.
const menus = await page.evaluate(() => ['ds-metier','ds-porteur','ds-pole']
  .map(id => { const s = document.getElementById(id);
    return s ? { id, options: s.options.length } : null; }).filter(Boolean));
t('les trois menus de filtre sont présents', menus.length === 3, JSON.stringify(menus));
t('chaque menu propose des valeurs', menus.every(m => m.options > 1), JSON.stringify(menus));

console.log('\n== Un filtre restreint bien les résultats ==');
// Une requête reste active pendant la comparaison : sans requête NI filtre,
// la page revient à son écran d'accueil et n'affiche aucune liste — zéro
// résultat y serait le comportement correct, pas un point de comparaison.
await page.locator('#ds-champ').fill('norme');
await page.waitForTimeout(700);
const sansFiltre = await page.locator('#ds-resultats > *').count();
await page.selectOption('#ds-pole', 'ETIIA');
await page.waitForTimeout(700);
const avecFiltre = await page.locator('#ds-resultats > *').count();
t('filtrer par pôle réduit le nombre de résultats',
  avecFiltre > 0 && avecFiltre < sansFiltre, `(${avecFiltre} avec, ${sansFiltre} sans)`);
await page.selectOption('#ds-pole', '');
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
t('les documents sans lien sont signalés', /sur demande|porteur/i.test(corps2));

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

console.log('\n== Le porteur mène à sa fiche ==');
// Partout ailleurs le site fait d'un nom de personne un lien ; la carte de
// document est justement le moment où l'on se demande à qui demander.
const liensPorteur = await page.evaluate(() => {
  const cartes = [...document.querySelectorAll('#ds-resultats > li')];
  const liens = cartes.map(c => c.querySelector('.ds-carte__porteur')).filter(Boolean);
  return {
    cartes: cartes.length,
    liens: liens.length,
    premier: liens.length ? liens[0].getAttribute('href') : null
  };
});
t('le porteur est un lien sur chaque carte',
  liensPorteur.liens === liensPorteur.cartes, JSON.stringify(liensPorteur));
t('ce lien ouvre la fiche de la personne',
  /^organigramme\.html#personne=\S+/.test(liensPorteur.premier || ''),
  String(liensPorteur.premier));

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
await page.keyboard.press('Escape');
await page.waitForTimeout(300);

t('aucune erreur JavaScript', erreurs.length===0, erreurs.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

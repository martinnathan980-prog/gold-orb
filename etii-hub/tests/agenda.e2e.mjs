// « À venir » : la ligne des prochains rendez-vous, dans un vrai navigateur.
//
//   1. python3 -m http.server 8111      2. node tests/agenda.e2e.mjs
//
// Vérifie ce que la mise en page calcule et ce que la ligne fait vivre :
// les étiquettes ne se chevauchent pas et aucune tige ne les traverse, le
// survol montre l'aperçu, le clavier passe d'un point à l'autre, un clic
// ouvre la fiche et son fichier d'agenda (.ics), la ligne défile quand la
// place manque, se dresse en colonne sur téléphone, tient sans animation,
// et dit « rien d'inscrit » quand il n'y a rien. Les rendez-vous d'essai
// sont posés dans ce navigateur (magasin local), jamais dans les données.

import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

const B = process.env.BASE || 'http://localhost:8111';
let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const jour = (n) => {
  const d = new Date(Date.now() + n * 86400000);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
};

/* La ligne vide : les rendez-vous de la base retirés (leurs dates sont
   réelles, ils passent un jour ou l'autre : le test ne dépend pas d'eux). */
const vide = Object.fromEntries(['a01', 'a02', 'a03'].map((id) => ['agenda:' + id, { type: 'agenda', id, op: 'suppr', donnees: null }]));

/* Neuf rendez-vous d'essai : deux le même jour, un demain avec une heure,
   des types et des pôles variés, un de trop pour la ligne — de quoi la
   serrer. */
const essais = Object.assign({}, vide);
[[1, 'ETIIE', 'reunion', 'Point hebdomadaire d’essai', 'Salle B', '9 h 30'],
 [3, 'ETIII', 'formation', 'Formation d’essai', 'Visio', ''],
 [3, 'ETIIA', 'revue', 'Revue d’essai', '', ''],
 [6, 'ETIIA', 'atelier', 'Atelier d’harmonisation d’essai', '', ''],
 [12, 'ETII', 'jalon', 'Revue de configuration d’essai', '', ''],
 [15, 'ETIIE', 'evenement', 'Journée d’essai', 'Hall 2', ''],
 [34, 'ETII', 'jalon', 'Jalon d’essai', '', ''],
 [51, 'ETIII', 'atelier', 'Atelier d’essai', 'Salle C', '14 h'],
 [90, 'ETII', 'evenement', 'Séminaire d’essai', '', '']]
  .forEach(([n, pole, type, titre, lieu, heure], i) => {
    essais['agenda:essai' + i] = { type: 'agenda', id: 'essai' + i, op: 'maj', donnees: { id: 'essai' + i, date: jour(n), pole, type, titre, lieu, heure, resume: 'Rendez-vous d’essai.' } };
  });

const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const err = [];
async function ouvrir(largeur, modifs, options) {
  const ctx = await nav.newContext(Object.assign({ viewport: { width: largeur, height: 900 }, acceptDownloads: true }, options || {}));
  if (modifs) await ctx.addInitScript((m) => { localStorage.setItem('etii:modifications:communications', JSON.stringify(m)); }, modifs);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => err.push(e.message));
  await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.getElementById('section-agenda').scrollIntoView({ block: 'center', behavior: 'instant' }));
  await page.waitForTimeout(2600);
  return page;
}

console.log('== La ligne, sur un écran large ==');
let page = await ouvrir(1280, essais);
const n = await page.locator('#zone-agenda .agenda__rdv').count();
t('huit rendez-vous au plus sur la ligne, et la suite annoncée', n === 8
  && /autres? plus tard/.test(await page.locator('#zone-agenda .agenda__suite').innerText().catch(() => '')), `(${n})`);
t('la ligne, pas la colonne', (await page.locator('#zone-agenda .agenda--ligne').count()) === 1);
t('plus de carte « prochain rendez-vous » ni de compte à rebours',
  (await page.locator('#zone-agenda [class*="agenda__prochain"]').count()) === 0);
const dates = await page.locator('#zone-agenda .agenda__rdv').evaluateAll((l) => l.map((e) => e.dataset.date));
t('dans l’ordre des dates', dates.every((d, i) => !i || d >= dates[i - 1]), dates.join(','));
const geometrie = await page.evaluate(() => {
  const lis = [...document.querySelectorAll('#zone-agenda .agenda__rdv')];
  const boites = lis.map((li) => li.querySelector('.agenda__cible').getBoundingClientRect());
  let chevauchements = 0;
  let traversees = 0;
  let horsAxe = 0;
  const axe = document.querySelector('#zone-agenda .agenda__aujourdhui-point').getBoundingClientRect();
  const yAxe = axe.top + axe.height / 2;
  boites.forEach((a, i) => boites.forEach((b, j) => {
    if (j > i && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom) chevauchements += 1;
  }));
  lis.forEach((li, i) => {
    const tige = li.querySelector('.agenda__tige').getBoundingClientRect();
    boites.forEach((b, j) => {
      if (i !== j && tige.left > b.left - 1 && tige.left < b.right && tige.top < b.bottom && tige.bottom > b.top) traversees += 1;
    });
    const p = li.querySelector('.agenda__point').getBoundingClientRect();
    if (Math.abs(p.top + p.height / 2 - yAxe) > 1.5) horsAxe += 1;
  });
  const xs = lis.map((li) => li.querySelector('.agenda__point').getBoundingClientRect().left);
  return { chevauchements, traversees, horsAxe, croissants: xs.every((x, i) => !i || x > xs[i - 1]) };
});
t('aucune étiquette n’en chevauche une autre', geometrie.chevauchements === 0, JSON.stringify(geometrie));
t('aucune tige ne traverse une étiquette', geometrie.traversees === 0, JSON.stringify(geometrie));
t('chaque point est posé sur l’axe, de gauche à droite', geometrie.horsAxe === 0 && geometrie.croissants, JSON.stringify(geometrie));
t('le glyphe dit le type (un par rendez-vous)', (await page.locator('#zone-agenda .agenda__point svg.agenda__glyphe').count()) === n);
t('le nom accessible dit la date en toutes lettres et l’échéance',
  /demain/.test(await page.locator('#zone-agenda .agenda__cible').first().innerText()));

console.log('\n== Survol, clavier, fiche ==');
await page.locator('#zone-agenda .agenda__rdv').nth(2).locator('.agenda__point').hover();
await page.waitForTimeout(400);
t('le survol montre l’aperçu et estompe les autres',
  (await page.locator('#zone-agenda .agenda__apercu.est-visible').count()) === 1
  && (await page.locator('#zone-agenda .agenda--allume').count()) === 1
  && (await page.locator('#zone-agenda .agenda__rdv.est-allume').count()) === 1);
t('l’aperçu dit le type et la date en toutes lettres', /revue/i.test(await page.locator('#zone-agenda .agenda__apercu').innerText())
  && /\d{4}/.test(await page.locator('#zone-agenda .agenda__apercu').innerText()));
await page.mouse.move(4, 4);
await page.waitForTimeout(300);
t('hors de la ligne, tout s’éteint', (await page.locator('#zone-agenda .agenda--allume').count()) === 0);

await page.locator('#zone-agenda .agenda__cible').first().focus();
await page.keyboard.press('ArrowRight');
await page.keyboard.press('ArrowRight');
const rang = () => page.evaluate(() => document.activeElement.closest('.agenda__rdv')?.dataset.i);
t('→ passe au point suivant', (await rang()) === '2');
await page.keyboard.press('End');
t('Fin va au dernier', (await rang()) === String(n - 1));
t('un seul arrêt de tabulation dans la ligne', (await page.locator('#zone-agenda .agenda__cible[tabindex="0"]').count()) === 1);
await page.keyboard.press('Home');
await page.keyboard.press('Enter');
await page.waitForTimeout(500);
t('Entrée ouvre la fiche du rendez-vous', (await page.locator('.modale .agenda-fiche__corps').count()) === 1
  && /essai/i.test(await page.locator('.modale__titre').innerText()));
const telechargement = page.waitForEvent('download', { timeout: 3000 }).catch(() => null);
await page.locator('.modale .bouton', { hasText: 'Ajouter à mon agenda' }).click();
const fichier = await telechargement;
t('« Ajouter à mon agenda » donne un fichier .ics', !!fichier && /\.ics$/.test(fichier.suggestedFilename()));
if (fichier) {
  const ics = readFileSync(await fichier.path(), 'utf8');
  t('le .ics est un rendez-vous daté, à l’heure dite', /BEGIN:VEVENT/.test(ics) && new RegExp('DTSTART:' + jour(1).replace(/-/g, '') + 'T093000').test(ics)
    && /SUMMARY:Point hebdomadaire d’essai/.test(ics) && /\r\n/.test(ics), ics.slice(0, 200));
}
await page.keyboard.press('Escape');
await page.waitForTimeout(400);
t('Échap referme la fiche, le focus revient au point', await page.evaluate(() => !!document.activeElement.closest('#zone-agenda .agenda__rdv')));
await page.locator('#zone-agenda .agenda__rdv').nth(4).locator('.agenda__point').click();
await page.waitForTimeout(400);
t('un clic sur le point ouvre aussi la fiche', (await page.locator('.modale .agenda-fiche__corps').count()) === 1);
await page.keyboard.press('Escape');
await page.close();

console.log('\n== Quand la place manque : la ligne défile ==');
page = await ouvrir(820, essais);
const [large, visible] = await page.evaluate(() => { const d = document.querySelector('#zone-agenda .agenda__defilement'); return [d.scrollWidth, d.clientWidth]; });
t('la ligne est plus longue que son cadre', large > visible, `${large}/${visible}`);
t('la flèche « plus tard » est là, pas « plus tôt »', (await page.locator('#zone-agenda .agenda.peut-apres:not(.peut-avant)').count()) === 1);
await page.locator('#zone-agenda .agenda__fleche--apres').click();
await page.waitForTimeout(800);
const apres = await page.evaluate(() => document.querySelector('#zone-agenda .agenda__defilement').scrollLeft);
t('la flèche fait défiler', apres > 50, `(${apres})`);
const cadre = await page.locator('#zone-agenda .agenda__defilement').boundingBox();
await page.mouse.move(cadre.x + cadre.width / 2, cadre.y + 12);
await page.mouse.down();
await page.mouse.move(cadre.x + cadre.width / 2 + 180, cadre.y + 12, { steps: 8 });
await page.mouse.up();
await page.waitForTimeout(300);
const glisse = await page.evaluate(() => document.querySelector('#zone-agenda .agenda__defilement').scrollLeft);
t('on la fait glisser à la souris', glisse < apres, `(${apres} → ${glisse})`);
t('la page, elle, ne défile pas en largeur', await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
await page.close();

console.log('\n== Sur téléphone : la colonne ==');
page = await ouvrir(390, essais);
t('la ligne se dresse en colonne', (await page.locator('#zone-agenda .agenda--colonne').count()) === 1);
t('chaque rendez-vous y est détaillé', await page.locator('#zone-agenda .agenda__details').first().isVisible());
t('les mois s’y écrivent en intertitres', (await page.locator('#zone-agenda .agenda__rdv[data-mois]').count()) >= 1);
t('pas de défilement horizontal à 390 px', await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
await page.locator('#zone-agenda .agenda__cible').nth(1).click();
await page.waitForTimeout(400);
t('toucher un rendez-vous ouvre sa fiche', (await page.locator('.modale .agenda-fiche__corps').count()) === 1);
await page.close();

console.log('\n== Moins d’animations ==');
page = await ouvrir(1280, essais, { reducedMotion: 'reduce' });
t('rien n’attend une animation', (await page.locator('#zone-agenda .agenda--anime').count()) === 0
  && (await page.locator('#zone-agenda .agenda__cible').first().evaluate((e) => getComputedStyle(e).opacity)) === '1');
await page.close();

console.log('\n== Rien à venir ==');
page = await ouvrir(1280, vide);
t('la ligne reste et le dit', (await page.locator('#zone-agenda .agenda--vide .agenda__aujourdhui').count()) === 1
  && /rien d’inscrit/i.test(await page.locator('#zone-agenda').innerText()));
await page.close();

t('aucune erreur de page', err.length === 0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

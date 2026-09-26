// « À venir » : la ligne des prochains rendez-vous, dans un vrai navigateur.
//
//   1. python3 -m http.server 8111      2. node tests/agenda.e2e.mjs
//
// Vérifie ce que la mise en page calcule et ce que la ligne fait vivre :
// les étiquettes ne se chevauchent pas, aucune tige ne les traverse et
// aucune ne sort du bloc ; la ligne tient dans sa largeur (des réunions
// hebdomadaires également espacées, une coupure « ≈ 3 mois » avant un
// rendez-vous lointain), chaque mois s'écrit à son premier jour ; le
// survol montre l'aperçu, le clavier passe d'un point à l'autre, un clic
// ouvre la fiche et son fichier d'agenda (.ics) ; la ligne ne défile qu'en
// dernier recours, se dresse en colonne sur téléphone, apparaît même
// agrandie quatre fois, tient sans animation, et dit « rien d'inscrit »
// quand il n'y a rien. Les rendez-vous d'essai sont posés dans ce
// navigateur (magasin local), jamais dans les données.

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

/* Des rendez-vous d'essai, à n jours d'ici : [n, pôle, type, titre, résumé]. */
function scenario(liste) {
  const m = Object.assign({}, vide);
  liste.forEach(([n, pole, type, titre, resume], i) => {
    m['agenda:s' + i] = { type: 'agenda', id: 's' + i, op: 'maj', donnees: { id: 's' + i, date: jour(n), pole, type, titre, resume: resume || 'Rendez-vous d’essai.' } };
  });
  return m;
}
/* Huit réunions, une par semaine. */
const hebdo = scenario(Array.from({ length: 8 }, (_, i) => [1 + 7 * i, 'ETIIE', 'reunion', 'Point hebdomadaire harnais']));
/* Cinq rendez-vous dans la semaine, puis un séminaire dans quatre mois. */
const serreLoin = scenario([[2, 'ETIIE', 'reunion', 'Point hebdomadaire harnais'],
  [2, 'ETIIA', 'revue', 'Revue des règles d’architecture et de la définition électrique des harnais du lot avionique'],
  [2, 'ETIII', 'formation', 'Formation routage 3D'], [3, 'ETII', 'jalon', 'Jalon trimestriel'],
  [3, 'ETIIE', 'evenement', 'Journée portes ouvertes'], [120, 'ETII', 'evenement', 'Séminaire annuel du service']]);

const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const err = [];
async function ouvrir(largeur, modifs, options) {
  const o = Object.assign({ viewport: { width: largeur, height: 900 }, acceptDownloads: true }, options || {});
  const ctx = await nav.newContext(o);
  if (modifs) await ctx.addInitScript((m) => { localStorage.setItem('etii:modifications:communications', JSON.stringify(m)); }, modifs);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => err.push(e.message));
  await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.getElementById('section-agenda').scrollIntoView({ block: 'center', behavior: 'instant' }));
  await page.waitForTimeout(2600);
  return page;
}

/* La géométrie de la ligne : chevauchements, tiges qui traversent,
   points hors de l'axe, étiquettes hors du bloc, défilement. */
function mesurerLigne(page, zone = '#zone-agenda') {
  return page.evaluate((zone) => {
    const racine = document.querySelector(zone + ' .agenda');
    const scene = racine.querySelector('.agenda__scene').getBoundingClientRect();
    const d = racine.querySelector('.agenda__defilement');
    const lis = [...racine.querySelectorAll('.agenda__rdv')];
    const boites = lis.map((li) => li.querySelector('.agenda__cible').getBoundingClientRect());
    let chevauchements = 0;
    let traversees = 0;
    let horsAxe = 0;
    let dehors = 0;
    const axe = racine.querySelector('.agenda__aujourdhui-point').getBoundingClientRect();
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
      if (boites[i].left < scene.left - 1 || boites[i].right > scene.right + 1) dehors += 1;
    });
    const xs = lis.map((li) => { const p = li.querySelector('.agenda__point').getBoundingClientRect(); return p.left + p.width / 2; });
    return {
      chevauchements, traversees, horsAxe, dehors,
      croissants: xs.every((x, i) => !i || x > xs[i - 1]),
      defile: d.scrollWidth > d.clientWidth + 1,
      xs: xs.map(Math.round)
    };
  }, zone);
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
const geometrie = await mesurerLigne(page);
t('aucune étiquette n’en chevauche une autre', geometrie.chevauchements === 0, JSON.stringify(geometrie));
t('aucune tige ne traverse une étiquette', geometrie.traversees === 0, JSON.stringify(geometrie));
t('chaque point est posé sur l’axe, de gauche à droite', geometrie.horsAxe === 0 && geometrie.croissants, JSON.stringify(geometrie));
t('tout tient dans la largeur : rien ne défile, aucune étiquette ne sort', !geometrie.defile && geometrie.dehors === 0, JSON.stringify(geometrie));
/* Chaque nom de mois pend à son premier jour : les points avant lui sont
   du mois d'avant, ceux d'après de son mois. */
const moisBienPlaces = await page.evaluate(() => {
  const points = [...document.querySelectorAll('#zone-agenda .agenda__rdv')].map((li) => {
    const p = li.querySelector('.agenda__point').getBoundingClientRect();
    return { x: p.left + p.width / 2, date: li.dataset.date };
  });
  const noms = [...document.querySelectorAll('#zone-agenda .agenda__mois')];
  return noms.length > 0 && noms.every((n) => {
    const cran = n.getBoundingClientRect().left - 6;
    return points.every((p) => (p.x < cran - 1 ? p.date < n.dataset.debut : p.x > cran + 1 ? p.date >= n.dataset.debut : true));
  });
});
t('chaque mois s’écrit à son premier jour, jamais plus loin', moisBienPlaces);
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
const apercuLibre = await page.evaluate(() => {
  const a = document.querySelector('#zone-agenda .agenda__apercu').getBoundingClientRect();
  const b = document.querySelector('#zone-agenda .agenda__rdv.est-allume .agenda__cible').getBoundingClientRect();
  return a.right < b.left - 6 || a.left > b.right + 6 || a.bottom < b.top - 6 || a.top > b.bottom + 6;
});
t('l’aperçu ne couvre pas l’étiquette ni le contour du focus', apercuLibre);
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

console.log('\n== La ligne tient dans sa largeur ==');
page = await ouvrir(1280, hebdo);
let g = await mesurerLigne(page);
t('huit réunions hebdomadaires tiennent à 1280 px, sans défiler ni sortir du bloc', !g.defile && g.dehors === 0 && g.xs.length === 8, JSON.stringify(g));
t('… sans chevauchement ni tige qui traverse', g.chevauchements === 0 && g.traversees === 0, JSON.stringify(g));
const pas = g.xs.slice(2).map((x, i) => x - g.xs[i + 1]);
t('… et également espacées (une semaine = une même longueur)', Math.max(...pas) - Math.min(...pas) <= 2, JSON.stringify(pas));
await page.close();
page = await ouvrir(1280, serreLoin);
g = await mesurerLigne(page);
t('cinq rendez-vous dans la semaine et un dans quatre mois tiennent à 1280 px', !g.defile && g.dehors === 0 && g.chevauchements === 0 && g.traversees === 0, JSON.stringify(g));
t('le temps vide devient une coupure « ≈ … mois »', /≈ \d+ mois/.test(await page.locator('#zone-agenda .agenda__coupure').innerText().catch(() => '')));
t('les rendez-vous serrés ont de la place : aucun point à moins de 28 px du précédent', g.xs.every((x, i) => !i || x - g.xs[i - 1] >= 27), JSON.stringify(g.xs));
await page.close();
for (const largeur of [1024, 820]) {
  page = await ouvrir(largeur, essais);
  g = await mesurerLigne(page);
  t(`à ${largeur} px, huit rendez-vous variés tiennent sans défiler`, !g.defile && g.dehors === 0 && g.chevauchements === 0 && g.traversees === 0, JSON.stringify(g));
  t(`à ${largeur} px, la page ne défile pas en largeur`, await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
  await page.close();
}

console.log('\n== En dernier recours : la ligne défile ==');
/* Seize rendez-vous le même jour dans 700 px : rien ne peut tenir. La
   ligne est montée directement, avec une limite relevée. */
page = await ouvrir(1280, vide);
await page.evaluate(async (date) => {
  const { agenda } = await import('./assets/js/agenda.js');
  const boite = document.createElement('div');
  boite.id = 'essai-defile';
  boite.style.inlineSize = '700px';
  document.getElementById('zone-agenda').after(boite);
  boite.append(agenda({ agenda: Array.from({ length: 16 }, (_, i) => ({ id: 'd' + i, date, pole: 'ETIIA', type: 'reunion', titre: 'Rendez-vous du même jour n° ' + (i + 1) })) }, { limite: 16 }));
  boite.scrollIntoView({ block: 'center', behavior: 'instant' });
}, jour(2));
await page.waitForTimeout(2600);
const [large, visible] = await page.evaluate(() => { const d = document.querySelector('#essai-defile .agenda__defilement'); return [d.scrollWidth, d.clientWidth]; });
t('la ligne est plus longue que son cadre', large > visible, `${large}/${visible}`);
g = await mesurerLigne(page, '#essai-defile');
t('… et ses étiquettes ne se chevauchent toujours pas', g.chevauchements === 0 && g.traversees === 0, JSON.stringify(g));
t('la flèche « plus tard » est là, pas « plus tôt »', (await page.locator('#essai-defile .agenda.peut-apres:not(.peut-avant)').count()) === 1);
await page.locator('#essai-defile .agenda__fleche--apres').click();
await page.waitForTimeout(800);
const apres = await page.evaluate(() => document.querySelector('#essai-defile .agenda__defilement').scrollLeft);
t('la flèche fait défiler', apres > 50, `(${apres})`);
const cadre = await page.locator('#essai-defile .agenda__defilement').boundingBox();
await page.mouse.move(cadre.x + cadre.width / 2, cadre.y + 12);
await page.mouse.down();
await page.mouse.move(cadre.x + cadre.width / 2 + 180, cadre.y + 12, { steps: 8 });
await page.mouse.up();
await page.waitForTimeout(300);
const glisse = await page.evaluate(() => document.querySelector('#essai-defile .agenda__defilement').scrollLeft);
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

console.log('\n== Agrandie plus de quatre fois (320 × 220) ==');
/* Le bloc, en colonne, fait plus de cinq hauteurs d'écran : il doit
   apparaître quand même, une fois qu'on y arrive. */
const long = 'Un résumé assez long pour occuper plusieurs lignes sur un écran très étroit : l’ordre du jour, les pièces à relire, les décisions attendues.';
page = await ouvrir(320, scenario(Array.from({ length: 7 }, (_, i) => [1 + 3 * i, 'ETIIA', 'reunion', 'Rendez-vous d’essai n° ' + (i + 1), long])), { viewport: { width: 320, height: 220 } });
await page.evaluate(() => { const r = document.querySelector('#zone-agenda .agenda').getBoundingClientRect(); window.scrollBy(0, r.top + r.height / 2 - 110); });
await page.waitForTimeout(2500);
const grand = await page.evaluate(() => {
  const r = document.querySelector('#zone-agenda .agenda');
  return { haut: r.offsetHeight, visibles: [...r.querySelectorAll('.agenda__cible, .agenda__point')].every((e) => getComputedStyle(e).opacity === '1') };
});
t('le bloc, plus haut que cinq écrans, finit par apparaître en entier', grand.haut > 5 * 220 && grand.visibles, JSON.stringify(grand));
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

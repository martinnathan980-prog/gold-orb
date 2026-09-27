// « À venir » : les prochains rendez-vous en pastilles, dans un vrai navigateur.
//
//   1. python3 -m http.server 8111      2. node tests/agenda.e2e.mjs
//
// Vérifie ce que la mise en page calcule et ce que la ligne fait vivre :
// les pastilles ne se chevauchent pas, aucune tige ne les traverse et
// aucune ne sort du bloc ; la couleur seule dit le pôle (plus de légende
// ni d'étiquette « Service ») ; la ligne tient dans sa largeur (des
// réunions hebdomadaires également espacées, une coupure « ≈ 3 mois »
// avant un rendez-vous lointain), chaque mois s'écrit à son premier jour ;
// le plus proche est allumé d'emblée ; le survol soulève et déplie une
// pastille, allume la ligne jusqu'à elle et dit « dans N jours » ; le
// clavier passe d'une pastille à l'autre, un clic ouvre la fiche et son
// fichier d'agenda (.ics) ; la ligne ne défile qu'en dernier recours, se
// dresse en colonne sur téléphone, apparaît même agrandie quatre fois,
// tient sans animation, et dit « rien d'inscrit » quand il n'y a rien.
// Les rendez-vous d'essai sont posés dans ce navigateur (magasin local),
// jamais dans les données.

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
/* Un rendez-vous de chaque pôle, et un du service, au résumé long. */
const long = 'Un résumé assez long pour occuper plusieurs lignes sur un écran très étroit : l’ordre du jour, les pièces à relire, les décisions attendues.';
const quatre = scenario([[4, 'ETII', 'jalon', 'Revue de configuration trimestrielle', long],
  [6, 'ETIIA', 'atelier', 'Atelier d’harmonisation', long], [9, 'ETIIE', 'reunion', 'Point d’avancement', long],
  [13, 'ETIII', 'formation', 'Formation routage 3D', long]]);

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
  await page.waitForTimeout(2800);
  return page;
}

/* La géométrie de la ligne : pastilles qui se chevauchent, tiges qui les
   traversent, repères hors de l'axe, pastilles hors du bloc, défilement. */
function mesurerLigne(page, zone = '#zone-agenda') {
  return page.evaluate((zone) => {
    const racine = document.querySelector(zone + ' .agenda');
    const scene = racine.querySelector('.agenda__scene').getBoundingClientRect();
    const d = racine.querySelector('.agenda__defilement');
    const lis = [...racine.querySelectorAll('.agenda__rdv')];
    const boites = lis.map((li) => li.querySelector('.agenda__pastille').getBoundingClientRect());
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
        if (i !== j && tige.right > b.left + 0.5 && tige.left < b.right - 0.5 && tige.top < b.bottom - 0.5 && tige.bottom > b.top + 0.5) traversees += 1;
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

/* Les couleurs du filet de chaque pastille, et celles des jetons : la
   couleur d'un pôle, le marine (ou l'encre ivoire) du service. */
function couleurs(page) {
  return page.evaluate(() => {
    const jeton = (nom) => {
      const s = document.createElement('span');
      s.style.color = 'var(' + nom + ')';
      document.body.append(s);
      const c = getComputedStyle(s).color;
      s.remove();
      return c;
    };
    const attendues = { ETII: jeton('--agenda-service'), ETIIA: jeton('--pole-etiia'), ETIIE: jeton('--pole-etiie'), ETIII: jeton('--pole-etiii') };
    const vues = [...document.querySelectorAll('#zone-agenda .agenda__rdv')].map((li) => {
      const s = getComputedStyle(li.querySelector('.agenda__pastille'));
      const droite = li.classList.contains('agenda__rdv--droite');
      return { pole: li.dataset.pole, filet: droite ? s.borderRightColor : s.borderLeftColor, point: getComputedStyle(li.querySelector('.agenda__point'), '::before').backgroundColor };
    });
    return { attendues, vues };
  });
}

console.log('== La ligne, sur un écran large ==');
let page = await ouvrir(1280, essais);
const n = await page.locator('#zone-agenda .agenda__rdv').count();
t('huit rendez-vous au plus sur la ligne, et la suite annoncée', n === 8
  && /autres? plus tard/.test(await page.locator('#zone-agenda .agenda__suite').innerText().catch(() => '')), `(${n})`);
t('la ligne, pas la colonne', (await page.locator('#zone-agenda .agenda--ligne').count()) === 1);
t('chaque rendez-vous est une pastille', (await page.locator('#zone-agenda .agenda__rdv .agenda__pastille').count()) === n);
t('plus de carte « prochain rendez-vous » ni de compte à rebours',
  (await page.locator('#zone-agenda [class*="agenda__prochain"]').count()) === 0);
/* Ce qui est écrit sur la ligne : des dates et des titres, jamais le pôle. */
const ecrit = await page.locator('#zone-agenda .agenda__quand').evaluateAll((l) => l.map((e) => e.textContent).join(' | '));
t('plus de légende ni d’étiquette « Service » ou de pôle sur la ligne',
  (await page.locator('#zone-agenda .agenda__legende, #zone-agenda .agenda__pole').count()) === 0
  && !/service|ETII/i.test(ecrit), ecrit);
const dates = await page.locator('#zone-agenda .agenda__rdv').evaluateAll((l) => l.map((e) => e.dataset.date));
t('dans l’ordre des dates', dates.every((d, i) => !i || d >= dates[i - 1]), dates.join(','));
const geometrie = await mesurerLigne(page);
t('aucune pastille n’en chevauche une autre', geometrie.chevauchements === 0, JSON.stringify(geometrie));
t('aucune tige ne traverse une pastille', geometrie.traversees === 0, JSON.stringify(geometrie));
t('chaque repère est posé sur l’axe, de gauche à droite', geometrie.horsAxe === 0 && geometrie.croissants, JSON.stringify(geometrie));
t('tout tient dans la largeur : rien ne défile, aucune pastille ne sort', !geometrie.defile && geometrie.dehors === 0, JSON.stringify(geometrie));
/* Chaque nom de mois pend à son premier jour : les repères avant lui sont
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
const teintes = await couleurs(page);
t('la couleur dit le pôle : le filet et le repère de chaque pastille', teintes.vues.every((v) => v.filet === teintes.attendues[v.pole] && v.point === teintes.attendues[v.pole]),
  JSON.stringify(teintes));
t('les quatre couleurs (le service et les trois pôles) sont distinctes', new Set(Object.values(teintes.attendues)).size === 4, JSON.stringify(teintes.attendues));
t('un jalon se marque d’un losange, le reste d’un rond', await page.evaluate(() => [...document.querySelectorAll('#zone-agenda .agenda__rdv')]
  .every((li) => (getComputedStyle(li.querySelector('.agenda__point'), '::before').rotate === '45deg') === (li.dataset.type === 'jalon'))));
t('le nom accessible dit le type, le pôle, la date en toutes lettres et l’échéance',
  /Réunion, Pôle ETIIE, \S+ \d+ \S+, demain/.test(await page.locator('#zone-agenda .agenda__cible').first().innerText()));
/* Le plus proche est allumé d'emblée : la lumière du trait va jusqu'à
   son repère. */
const repos = await page.evaluate(() => {
  const r = document.querySelector('#zone-agenda .agenda');
  const j = r.querySelector('.agenda__jauge').getBoundingClientRect();
  const p = r.querySelector('.agenda__rdv--prochain .agenda__point').getBoundingClientRect();
  return { fin: Math.round(j.right), point: Math.round(p.left + p.width / 2), premier: r.querySelector('.agenda__rdv').classList.contains('agenda__rdv--prochain') };
});
t('au repos, le plus proche est allumé : la ligne s’éclaire jusqu’à lui', repos.premier && Math.abs(repos.fin - repos.point) <= 3, JSON.stringify(repos));

console.log('\n== Survol, clavier, fiche ==');
const pastille = (i) => page.locator('#zone-agenda .agenda__rdv').nth(i).locator('.agenda__pastille');
await pastille(0).hover();
await page.waitForTimeout(700);
t('le survol soulève et déplie la pastille, estompe les autres', await page.evaluate(() => {
  const r = document.querySelector('#zone-agenda .agenda');
  const allumee = r.querySelector('.agenda__rdv.est-allume');
  const autre = r.querySelector('.agenda__rdv:not(.est-allume)');
  return r.classList.contains('agenda--allume') && r.querySelectorAll('.agenda__rdv.est-allume').length === 1
    && allumee.querySelector('.agenda__details').offsetHeight > 20 && Number(getComputedStyle(autre).opacity) < 0.6;
}));
t('le dépli dit le type, l’heure et le lieu', /Réunion · 9 h 30 · Salle B/.test(await page.locator('#zone-agenda .agenda__rdv.est-allume .agenda__details').innerText()));
t('soulevée, la pastille garde son repère sur l’axe', (await mesurerLigne(page)).horsAxe === 0);
await pastille(4).hover();
await page.waitForTimeout(800);
const lumiere = await page.evaluate(() => {
  const r = document.querySelector('#zone-agenda .agenda');
  const j = r.querySelector('.agenda__jauge').getBoundingClientRect();
  const p = r.querySelector('.agenda__rdv.est-allume .agenda__point').getBoundingClientRect();
  const d = r.querySelector('.agenda__distance');
  return { fin: Math.round(j.right), point: Math.round(p.left + p.width / 2), distance: d.classList.contains('est-visible') ? d.textContent : '' };
});
t('la ligne s’allume d’aujourd’hui jusqu’à la pastille survolée', Math.abs(lumiere.fin - lumiere.point) <= 3, JSON.stringify(lumiere));
t('… et dit sur le trait le temps d’ici là', lumiere.distance === 'dans 12 jours', JSON.stringify(lumiere));
await page.mouse.move(4, 4);
await page.waitForTimeout(600);
t('hors de la ligne, tout se replie et la lumière revient au plus proche', (await page.locator('#zone-agenda .agenda--allume').count()) === 0
  && await page.evaluate(() => {
    const r = document.querySelector('#zone-agenda .agenda');
    const j = r.querySelector('.agenda__jauge').getBoundingClientRect();
    const p = r.querySelector('.agenda__rdv--prochain .agenda__point').getBoundingClientRect();
    return Math.abs(j.right - (p.left + p.width / 2)) <= 3;
  }));

await page.locator('#zone-agenda .agenda__cible').first().focus();
await page.keyboard.press('ArrowRight');
await page.keyboard.press('ArrowRight');
const rang = () => page.evaluate(() => document.activeElement.closest('.agenda__rdv')?.dataset.i);
t('→ passe à la pastille suivante', (await rang()) === '2');
t('au clavier aussi, la pastille se déplie', (await page.locator('#zone-agenda .agenda__rdv.est-allume[data-i="2"]').count()) === 1);
await page.keyboard.press('End');
t('Fin va à la dernière', (await rang()) === String(n - 1));
t('un seul arrêt de tabulation dans la ligne', (await page.locator('#zone-agenda .agenda__cible[tabindex="0"]').count()) === 1);
await page.keyboard.press('Home');
await page.keyboard.press('Enter');
await page.waitForTimeout(500);
t('Entrée ouvre la fiche du rendez-vous', (await page.locator('.modale .agenda-fiche__corps').count()) === 1
  && /essai/i.test(await page.locator('.modale__titre').innerText()));
t('la fiche dit le type et le pôle', /Réunion · Pôle ETIIE/i.test(await page.locator('.modale .agenda-fiche__type').innerText()));
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
t('Échap referme la fiche, le focus revient à la pastille', await page.evaluate(() => !!document.activeElement.closest('#zone-agenda .agenda__rdv')));
await page.locator('#zone-agenda .agenda__rdv').nth(4).locator('.agenda__point').click();
await page.waitForTimeout(400);
t('un clic sur le repère ouvre aussi la fiche', (await page.locator('.modale .agenda-fiche__corps').count()) === 1);
await page.keyboard.press('Escape');
await page.waitForTimeout(300);
await pastille(6).click({ position: { x: 30, y: 12 } });
await page.waitForTimeout(400);
t('un clic n’importe où sur la pastille ouvre la fiche', (await page.locator('.modale .agenda-fiche__corps').count()) === 1);
await page.keyboard.press('Escape');
await page.close();

console.log('\n== Dépliée, elle ne monte pas sur le titre ==');
page = await ouvrir(1280, quatre);
let g = await mesurerLigne(page);
t('un rendez-vous par pôle et un du service tiennent sans chevauchement', g.chevauchements === 0 && g.traversees === 0 && !g.defile && g.dehors === 0, JSON.stringify(g));
const couvre = [];
for (let i = 0; i < 4; i += 1) {
  await pastille(i).hover();
  await page.waitForTimeout(700);
  couvre.push(await page.evaluate(() => {
    const titre = document.querySelector('#section-agenda h2').getBoundingClientRect();
    const p = document.querySelector('#zone-agenda .agenda__rdv.est-allume .agenda__pastille').getBoundingClientRect();
    return Math.round(p.top - titre.bottom);
  }));
}
t('dépliée, aucune pastille ne couvre le titre de la section', couvre.every((e) => e >= 0), JSON.stringify(couvre));
t('la page ne défile pas en largeur, même dépliée', await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
await page.close();

console.log('\n== La ligne tient dans sa largeur ==');
page = await ouvrir(1280, hebdo);
g = await mesurerLigne(page);
t('huit réunions hebdomadaires tiennent à 1280 px, sans défiler ni sortir du bloc', !g.defile && g.dehors === 0 && g.xs.length === 8, JSON.stringify(g));
t('… sans chevauchement ni tige qui traverse', g.chevauchements === 0 && g.traversees === 0, JSON.stringify(g));
const pas = g.xs.slice(2).map((x, i) => x - g.xs[i + 1]);
t('… et également espacées (une semaine = une même longueur)', Math.max(...pas) - Math.min(...pas) <= 2, JSON.stringify(pas));
await page.close();
page = await ouvrir(1280, serreLoin);
g = await mesurerLigne(page);
t('cinq rendez-vous dans la semaine et un dans quatre mois tiennent à 1280 px', !g.defile && g.dehors === 0 && g.chevauchements === 0 && g.traversees === 0, JSON.stringify(g));
t('le temps vide devient une coupure « ≈ … mois »', /≈ \d+ mois/.test(await page.locator('#zone-agenda .agenda__coupure').innerText().catch(() => '')));
t('les rendez-vous serrés ont de la place : aucun repère à moins de 28 px du précédent', g.xs.every((x, i) => !i || x - g.xs[i - 1] >= 27), JSON.stringify(g.xs));
await page.close();
for (const largeur of [1024, 820]) {
  page = await ouvrir(largeur, essais);
  g = await mesurerLigne(page);
  t(`à ${largeur} px, huit rendez-vous variés tiennent sans défiler`, !g.defile && g.dehors === 0 && g.chevauchements === 0 && g.traversees === 0, JSON.stringify(g));
  t(`à ${largeur} px, la page ne défile pas en largeur`, await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
  await page.close();
}
/* Sur une tablette, huit rendez-vous dans la semaine empileraient trois
   rangées de tiges : la colonne se lit mieux. Deux rendez-vous, eux,
   restent sur la ligne. */
const semaine = scenario([[1, 'ETIIE', 'reunion', 'Point hebdomadaire harnais'], [2, 'ETIIA', 'revue', 'Revue des règles d’architecture du lot avionique'],
  [2, 'ETIII', 'formation', 'Formation routage 3D'], [3, 'ETII', 'jalon', 'Jalon trimestriel'], [4, 'ETIIE', 'evenement', 'Journée portes ouvertes'],
  [5, 'ETIIA', 'atelier', 'Atelier d’harmonisation'], [6, 'ETII', 'reunion', 'Comité de service'], [7, 'ETIII', 'revue', 'Revue de maturité']]);
page = await ouvrir(720, semaine);
t('à 720 px, huit rendez-vous dans la semaine se dressent en colonne plutôt qu’en forêt de tiges',
  (await page.locator('#zone-agenda .agenda--colonne').count()) === 1
  && await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
await page.close();
page = await ouvrir(720, scenario([[5, 'ETIIA', 'atelier', 'Atelier d’harmonisation des pratiques'], [11, 'ETII', 'jalon', 'Revue de configuration trimestrielle']]));
g = await mesurerLigne(page);
t('à 720 px, deux rendez-vous restent sur la ligne, entiers', (await page.locator('#zone-agenda .agenda--ligne').count()) === 1
  && !g.defile && g.dehors === 0 && g.chevauchements === 0, JSON.stringify(g));
await page.close();

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
await page.waitForTimeout(2800);
/* Posée, la ligne a changé de hauteur : on la recentre. */
await page.evaluate(() => document.getElementById('essai-defile').scrollIntoView({ block: 'center', behavior: 'instant' }));
await page.waitForTimeout(300);
const [large, visible] = await page.evaluate(() => { const d = document.querySelector('#essai-defile .agenda__defilement'); return [d.scrollWidth, d.clientWidth]; });
t('la ligne est plus longue que son cadre', large > visible, `${large}/${visible}`);
g = await mesurerLigne(page, '#essai-defile');
t('… et ses pastilles ne se chevauchent toujours pas', g.chevauchements === 0 && g.traversees === 0, JSON.stringify(g));
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
/* Le cadre qui défile coupe ce qui dépasse : la place d'une pastille
   dépliée y est gardée. */
await page.locator('#essai-defile .agenda__rdv').first().locator('.agenda__cible').focus();
await page.waitForTimeout(700);
t('dans la ligne qui défile, une pastille dépliée reste entière', await page.evaluate(() => {
  const d = document.querySelector('#essai-defile .agenda__defilement').getBoundingClientRect();
  const p = document.querySelector('#essai-defile .agenda__rdv.est-allume .agenda__pastille').getBoundingClientRect();
  return p.top >= d.top - 1 && p.bottom <= d.bottom + 1;
}));
t('la page, elle, ne défile pas en largeur', await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
await page.close();

console.log('\n== Sur téléphone : la colonne ==');
page = await ouvrir(390, essais);
t('la ligne se dresse en colonne', (await page.locator('#zone-agenda .agenda--colonne').count()) === 1);
t('chaque pastille y est dépliée', await page.locator('#zone-agenda .agenda__details').first().isVisible()
  && (await page.locator('#zone-agenda .agenda__details').first().evaluate((e) => e.offsetHeight)) > 20);
t('les mois s’y écrivent en intertitres', (await page.locator('#zone-agenda .agenda__rdv[data-mois]').count()) >= 1);
t('chaque pastille tient à son repère sur le rail', await page.evaluate(() => {
  const rail = document.querySelector('#zone-agenda .agenda__aujourdhui-point').getBoundingClientRect();
  const x = rail.left + rail.width / 2;
  return [...document.querySelectorAll('#zone-agenda .agenda__rdv .agenda__point')].every((p) => {
    const b = p.getBoundingClientRect();
    return Math.abs(b.left + b.width / 2 - x) <= 1.5;
  });
}));
t('pas de défilement horizontal à 390 px', await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
await page.locator('#zone-agenda .agenda__cible').nth(1).click();
await page.waitForTimeout(400);
t('toucher un rendez-vous ouvre sa fiche', (await page.locator('.modale .agenda-fiche__corps').count()) === 1);
await page.close();

console.log('\n== Agrandie plus de quatre fois (320 × 220) ==');
/* Le bloc, en colonne, fait plus de cinq hauteurs d'écran : il doit
   apparaître quand même, une fois qu'on y arrive. */
page = await ouvrir(320, scenario(Array.from({ length: 7 }, (_, i) => [1 + 3 * i, 'ETIIA', 'reunion', 'Rendez-vous d’essai n° ' + (i + 1), long])), { viewport: { width: 320, height: 220 } });
await page.evaluate(() => { const r = document.querySelector('#zone-agenda .agenda').getBoundingClientRect(); window.scrollBy(0, r.top + r.height / 2 - 110); });
await page.waitForTimeout(2800);
const grand = await page.evaluate(() => {
  const r = document.querySelector('#zone-agenda .agenda');
  return { haut: r.offsetHeight, visibles: [...r.querySelectorAll('.agenda__pastille, .agenda__point')].every((e) => getComputedStyle(e).opacity === '1') };
});
t('le bloc, plus haut que cinq écrans, finit par apparaître en entier', grand.haut > 5 * 220 && grand.visibles, JSON.stringify(grand));
await page.close();

console.log('\n== Moins d’animations ==');
page = await ouvrir(1280, essais, { reducedMotion: 'reduce' });
t('rien n’attend une animation', (await page.locator('#zone-agenda .agenda--anime').count()) === 0
  && (await page.locator('#zone-agenda .agenda__pastille').first().evaluate((e) => getComputedStyle(e).opacity)) === '1');
await pastille(1).hover();
t('le survol déplie sans glisser', await page.evaluate(() => document.querySelector('#zone-agenda .agenda__rdv.est-allume .agenda__details').offsetHeight > 20));
await page.close();

console.log('\n== Thème sombre ==');
page = await ouvrir(1280, quatre, { colorScheme: 'dark' });
const sombre = await couleurs(page);
t('en sombre aussi, la couleur dit le pôle, et les quatre restent distinctes',
  sombre.vues.every((v) => v.filet === sombre.attendues[v.pole]) && new Set(Object.values(sombre.attendues)).size === 4, JSON.stringify(sombre));
await page.close();

console.log('\n== Rien à venir ==');
page = await ouvrir(1280, vide);
t('la ligne reste et le dit, dans une pastille en pointillé', (await page.locator('#zone-agenda .agenda--vide .agenda__aujourdhui').count()) === 1
  && /rien d’inscrit/i.test(await page.locator('#zone-agenda').innerText())
  && (await page.locator('#zone-agenda .agenda__vide-texte').evaluate((e) => getComputedStyle(e).borderTopStyle)) === 'dashed');
await page.close();

t('aucune erreur de page', err.length === 0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

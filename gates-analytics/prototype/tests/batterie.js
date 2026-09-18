/* Batterie de tests de l'interface — Playwright, navigateur réel.
   On ne vérifie pas seulement que les fonctions marchent : on essaie de casser
   la page (entrées absurdes, clics répétés, stockage corrompu, largeurs
   extrêmes) et on relève tout ce qui remonte dans la console. */
const { chromium } = require('playwright');
const path = require('path');

const URL = 'file://' + path.join(__dirname, '..', 'apercu.html');
let reussis = 0;
const echecs = [];
const erreursJS = [];
let sectionCourante = '';

function verifier(nom, condition, detail) {
  if (condition) { reussis++; console.log('  ✓ ' + nom); }
  else {
    echecs.push('[' + sectionCourante + '] ' + nom + (detail ? ' — ' + detail : ''));
    console.log('  ✗ ' + nom + (detail ? ' — ' + detail : ''));
  }
}
function section(titre) { sectionCourante = titre; console.log('\n— ' + titre + ' —'); }

/* « tout reinitialiser » est masque quand rien n'est filtre : on ne clique que
   s'il est visible, sinon on remet l'etat a la main. */
async function reinitialiser(pg) {
  const bouton = await pg.$('#reinit');
  if (bouton && await bouton.isVisible()) { await bouton.click(); }
  else {
    await pg.fill('#recherche', '');
    for (const i of await pg.$$('input[data-filtre]')) await i.fill('');
  }
  await pg.waitForTimeout(400);
}

(async () => {
  const nav = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });

  function brancher(pg, etiquette) {
    pg.on('pageerror', e => erreursJS.push(etiquette + ' : ' + e.message));
    pg.on('console', m => {
      if (m.type() === 'error' && !m.text().includes('ERR_FILE')) erreursJS.push(etiquette + ' : ' + m.text());
    });
    pg.on('dialog', d => d.dismiss().catch(() => {}));
  }
  async function contexte(opts = {}) {
    const ctx = await nav.newContext(Object.assign({ viewport: { width: 1280, height: 950 } }, opts));
    return ctx;
  }
  async function page(ctx, etiquette = 'page') {
    const pg = await ctx.newPage();
    brancher(pg, etiquette);
    await pg.goto(URL);
    await pg.waitForTimeout(1300);
    return pg;
  }

  const ctx = await contexte();
  let p = await page(ctx, 'principal');
  /* Le jeu d'exemple peut changer de taille : on relève le total une fois et
     tout le reste s'y réfère. */
  const TOTAL = await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length);
  /* Le nombre total de colonnes de l'export : le tableau les ouvre toutes,
     c'est la consigne, et c'est aussi ce que « tout afficher » doit rendre. */
  const COLONNES_TOTAL = await p.evaluate(() =>
    document.querySelectorAll('#panneau-colonnes input[data-col]').length);
  console.log('  (jeu d\'exemple : ' + TOTAL + ' plans, ' + COLONNES_TOTAL + ' colonnes)');

  // =================================================================
  /* Le tableau du bas EST l'extract : toutes les colonnes, les memes
     intitules, l'ordre de la feuille. C'est la condition pour que tout le
     monde regarde la meme chose. */
  section('Le tableau ouvre sur l\'extract entier');
  const extrait = await p.evaluate(() => ({
    affichees: document.querySelectorAll('tr.titres th').length,
    ordre: [...document.querySelectorAll('tr.titres th')].map(t => t.dataset.cle),
    source: window.__ORDRE_SOURCE || null,
    figees: [...document.querySelectorAll('tr.titres th.col-fige')].map(t => t.dataset.cle),
    gauches: [...document.querySelectorAll('tr.titres th.col-fige')].map(t => parseFloat(t.style.left))
  }));
  verifier('aucune colonne n\'est cachee au depart',
    extrait.affichees === COLONNES_TOTAL, extrait.affichees + ' / ' + COLONNES_TOTAL);
  verifier('la reference est figee, et tout ce qui la precede avec elle',
    extrait.figees.length >= 1 &&
    extrait.figees[extrait.figees.length - 1] === 'reference' &&
    extrait.figees.join(',') === extrait.ordre.slice(0, extrait.figees.length).join(','),
    JSON.stringify(extrait.figees));
  verifier('les colonnes figees se posent l\'une apres l\'autre',
    extrait.gauches[0] === 0 &&
    extrait.gauches.every((g, i) => i === 0 || g > extrait.gauches[i - 1]),
    JSON.stringify(extrait.gauches));

  // =================================================================
  section('Les deux vues du tableau');
  const vTout = await p.evaluate(() => [...document.querySelectorAll('#vue-tableau button')]
    .map(b => b.dataset.vue + ':' + b.getAttribute('aria-pressed')).join(' '));
  verifier('on demarre sur « toutes les colonnes »',
    vTout === 'toutes:false essentielle:false' || vTout === 'toutes:true essentielle:false', vTout);
  await p.click('#vue-tableau button[data-vue="essentielle"]'); await p.waitForTimeout(600);
  const vEss = await p.evaluate(() => ({
    n: document.querySelectorAll('tr.titres th').length,
    premiere: (document.querySelector('tr.titres th') || {}).dataset,
    figees: document.querySelectorAll('tr.titres th.col-fige').length,
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    presse: [...document.querySelectorAll('#vue-tableau button')]
      .map(b => b.dataset.vue + ':' + b.getAttribute('aria-pressed')).join(' ')
  }));
  verifier('la vue essentielle reduit vraiment le tableau',
    vEss.n > 1 && vEss.n < COLONNES_TOTAL, vEss.n + ' colonnes');
  verifier('la reference l\'ouvre et reste seule figee',
    vEss.premiere.cle === 'reference' && vEss.figees === 1, JSON.stringify(vEss));
  verifier('et aucun plan n\'est perdu', vEss.lignes === TOTAL, String(vEss.lignes));
  verifier('l\'interrupteur dit laquelle est active',
    vEss.presse === 'toutes:false essentielle:true', vEss.presse);
  await p.click('#vue-tableau button[data-vue="toutes"]'); await p.waitForTimeout(600);
  verifier('revenir rend l\'extract entier, dans le meme ordre',
    await p.evaluate(o => [...document.querySelectorAll('tr.titres th')]
      .map(t => t.dataset.cle).join(',') === o.join(','), extrait.ordre));
  for (let i = 0; i < 4; i++) {
    await p.click('#vue-tableau button[data-vue="essentielle"]'); await p.waitForTimeout(130);
    await p.click('#vue-tableau button[data-vue="toutes"]'); await p.waitForTimeout(130);
  }
  await p.waitForTimeout(500);
  verifier('quatre allers-retours rapides ne derangent rien',
    await p.evaluate(t => document.querySelectorAll('tr.titres th').length === t.c &&
      document.querySelectorAll('#corps-tableau tr').length === t.n,
      { c: COLONNES_TOTAL, n: TOTAL }));

  // =================================================================
  section('L\'interrupteur exemple / reel');
  const modeDepart = await p.evaluate(() => ({
    haut: document.getElementById('bandeau-mode').getBoundingClientRect().top <
          document.querySelector('.masthead').getBoundingClientRect().top,
    presse: [...document.querySelectorAll('#mode-donnees button')]
      .map(b => b.dataset.mode + ':' + b.getAttribute('aria-pressed')).join(' '),
    marque: document.body.dataset.exemple
  }));
  verifier('il est tout en haut, avant le titre', modeDepart.haut, JSON.stringify(modeDepart));
  verifier('et il demarre sur le reel',
    modeDepart.presse === 'reel:true exemple:false' && modeDepart.marque === 'false',
    JSON.stringify(modeDepart));
  /* Parité : les deux modes passent par la même dérivation, donc chaque bloc
     rempli en réel l'est aussi en exemple — comparatif « depuis l'import »,
     journal, fin estimée et rythme par groupe, courbe. On relève la même
     signature dans les deux modes et on exige qu'elle soit identique. */
  const blocsRemplis = () => p.evaluate(() => ({
    comparatif: /Depuis l’import/.test(document.getElementById('comparatif').textContent) &&
                document.querySelectorAll('.puce-delta').length > 0,
    journal: document.querySelectorAll('.journal-ligne').length > 0,
    finEstimee: [...document.querySelectorAll('.critique-date .v')]
      .some(v => /^\d{4}-S\d{2}$/.test(v.textContent.trim())),
    rythme: [...document.querySelectorAll('.critique-effort .v')].some(v => /sem\./.test(v.textContent)),
    courbe: document.querySelectorAll('svg.graphe circle').length >= 5,
    groupes: document.querySelectorAll('.critique-ligne').length > 0,
    plans: document.querySelectorAll('#corps-tableau tr').length
  }));
  const reelBlocs = await blocsRemplis();
  verifier('en reel, tous les blocs sont remplis',
    Object.keys(reelBlocs).every(k => reelBlocs[k]), JSON.stringify(reelBlocs));
  await p.click('#mode-donnees button[data-mode="exemple"]'); await p.waitForTimeout(900);
  const modeEx = await p.evaluate(() => ({
    marque: document.body.dataset.exemple,
    bord: getComputedStyle(document.getElementById('bandeau-mode')).borderStyle,
    mot: document.getElementById('mot-mode').textContent,
    points: document.querySelectorAll('svg.graphe circle').length,
    lignes: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('la page entiere se marque en exemple',
    modeEx.marque === 'true' && /dashed/.test(modeEx.bord), JSON.stringify(modeEx).slice(0, 120));
  verifier('et elle dit ce qui est fabrique', /historique/i.test(modeEx.mot), modeEx.mot);
  verifier('le graphique se remplit sans perdre de plan',
    modeEx.points >= 5 && modeEx.lignes === TOTAL, JSON.stringify(modeEx));
  const exBlocs = await blocsRemplis();
  verifier('l\'exemple remplit exactement les memes blocs que le reel',
    JSON.stringify(exBlocs) === JSON.stringify(reelBlocs), JSON.stringify(exBlocs));
  verifier('le comparatif de l\'exemple se rapporte a l\'historique fabrique',
    await p.evaluate(() => /Depuis l’import du \d{4}-S\d{2}/.test(document.getElementById('comparatif').textContent)));
  // Choisir un groupe : la courbe et le rythme suivent, comme en réel.
  await p.click('.critique-ligne >> nth=0'); await p.waitForTimeout(450);
  const exGroupe = await p.evaluate(() => ({
    note: document.getElementById('note-graphe').textContent,
    points: document.querySelectorAll('svg.graphe circle').length,
    presse: document.querySelectorAll('.critique-ligne[aria-pressed="true"]').length,
    lignes: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('en exemple, choisir un groupe trace son historique',
    /Historique de/.test(exGroupe.note) && exGroupe.points >= 5 && exGroupe.presse === 1,
    JSON.stringify(exGroupe));
  verifier('et filtre le tableau', exGroupe.lignes > 0 && exGroupe.lignes < TOTAL, String(exGroupe.lignes));
  await p.click('.critique-ligne >> nth=0'); await p.waitForTimeout(350);
  // La bulle du graphique nomme les passages en terminé, comme en réel.
  await p.evaluate(() => document.getElementById('cadre-graphe').scrollIntoView({ block: 'center' }));
  await p.waitForTimeout(300);
  let bulleEx = '';
  for (const z of await p.$$('.zone-clic')) {
    const bb = await z.boundingBox();
    if (!bb || bb.y < 0 || bb.y > 900) continue;
    await p.mouse.move(bb.x + bb.width / 2, bb.y + bb.height * 0.6);
    await p.waitForTimeout(90);
    const t = await p.evaluate(() => document.getElementById('bulle').textContent);
    if (/passés? en terminé/.test(t)) { bulleEx = t; break; }
  }
  verifier('en exemple, la bulle du graphique annonce les passages en termine',
    /passés? en terminé/.test(bulleEx), bulleEx.slice(0, 80));
  await p.mouse.move(5, 5);
  // Les filtres marchent en exemple aussi.
  await p.click('.etat-btn[data-etat="termine"]'); await p.waitForTimeout(350);
  verifier('en exemple, filtrer un etat reduit le tableau',
    await p.evaluate(t => { const n = document.querySelectorAll('#corps-tableau tr').length; return n > 0 && n < t; }, TOTAL));
  await p.click('.etat-btn[data-etat="termine"]'); await p.waitForTimeout(300);
  await p.click('#mode-donnees button[data-mode="reel"]'); await p.waitForTimeout(800);
  verifier('revenir au reel efface la marque et la phrase',
    await p.evaluate(() => document.body.dataset.exemple === 'false' &&
      document.getElementById('mot-mode').textContent.trim() === ''));
  verifier('et retrouve exactement les blocs du depart',
    JSON.stringify(await blocsRemplis()) === JSON.stringify(reelBlocs));
  for (let i = 0; i < 5; i++) {
    await p.click('#mode-donnees button[data-mode="exemple"]'); await p.waitForTimeout(150);
    await p.click('#mode-donnees button[data-mode="reel"]'); await p.waitForTimeout(150);
  }
  await p.waitForTimeout(700);
  verifier('dix bascules d\'affilee laissent la page intacte',
    await p.evaluate(t => document.body.dataset.exemple === 'false' &&
      document.querySelectorAll('#corps-tableau tr').length === t, TOTAL));

  // =================================================================
  /* Plusieurs contrats, une seule page : le sélecteur vit dans le bandeau du
     haut, le contrat courant est rappelé sous le titre, et changer de contrat
     recharge tout — comptes, historique, pied de page — en repartant des
     filtres et du cadrage par défaut. */
  section('Sélecteur de contrat');
  const sel0 = await p.evaluate(() => ({
    visible: !document.getElementById('choix-contrat').hidden &&
             document.getElementById('select-contrat').offsetParent !== null,
    haut: document.getElementById('choix-contrat').getBoundingClientRect().top <
          document.querySelector('.masthead').getBoundingClientRect().top,
    options: [...document.querySelectorAll('#select-contrat option')].map(o => o.value).join(','),
    courant: document.getElementById('select-contrat').value,
    nom: document.getElementById('nom-contrat').textContent,
    nomVisible: !document.getElementById('contrat-courant').hidden,
    titre: document.title,
    zones: document.querySelectorAll('.zone-clic').length
  }));
  verifier('le selecteur est la, en haut, et liste les trois contrats',
    sel0.visible && sel0.haut && sel0.options === 'X1,X2,X3', JSON.stringify(sel0));
  verifier('il demarre sur X1, rappele sous le titre',
    sel0.courant === 'X1' && sel0.nom === 'X1' && sel0.nomVisible, JSON.stringify(sel0));
  verifier('le titre de la page reste « Suivi FWD »', sel0.titre === 'Suivi FWD', sel0.titre);
  const pied0 = await p.evaluate(() => document.getElementById('import').textContent);
  const etats0 = await p.evaluate(() => [...document.querySelectorAll('.etat-n')].map(e => e.textContent).join(' '));
  // Un filtre et un cadrage posés avant de changer : ils doivent repartir de zéro.
  await p.click('.etat-btn[data-etat="termine"]'); await p.waitForTimeout(300);
  await p.click('.segmente button[data-span="52"]'); await p.waitForTimeout(300);
  const lireContrat = () => p.evaluate(() => ({
    plans: document.querySelectorAll('#corps-tableau tr').length,
    pied: document.getElementById('import').textContent,
    nom: document.getElementById('nom-contrat').textContent,
    courant: document.getElementById('select-contrat').value,
    filtres: document.getElementById('filtres-actifs').hidden,
    presse: document.querySelectorAll('.etat-btn[aria-pressed="true"]').length,
    zones: document.querySelectorAll('.zone-clic').length,
    etats: [...document.querySelectorAll('.etat-n')].map(e => e.textContent).join(' '),
    groupes: [...document.querySelectorAll('.critique-total')].reduce((s, e) => s + (+e.textContent), 0),
    journal: document.querySelectorAll('.journal-ligne').length,
    mode: document.body.dataset.exemple
  }));
  await p.selectOption('#select-contrat', 'X2'); await p.waitForTimeout(1200);
  const x2 = await lireContrat();
  verifier('changer de contrat change le nombre de plans', x2.plans > 0 && x2.plans !== TOTAL, String(x2.plans));
  verifier('et le pied de page', x2.pied !== pied0, x2.pied);
  verifier('le contrat courant est rappele sous le titre', x2.nom === 'X2' && x2.courant === 'X2', x2.nom);
  verifier('les filtres et le cadrage repartent de zero',
    x2.filtres && x2.presse === 0 && x2.zones === sel0.zones, JSON.stringify(x2));
  verifier('le bloc par groupe et le journal suivent le nouveau contrat',
    x2.groupes === x2.plans && x2.journal > 0, x2.groupes + ' / ' + x2.plans);
  await p.selectOption('#select-contrat', 'X3'); await p.waitForTimeout(1200);
  const x3 = await lireContrat();
  verifier('un troisieme contrat a encore d\'autres comptes',
    x3.plans > 0 && x3.plans !== x2.plans && x3.plans !== TOTAL && x3.nom === 'X3', String(x3.plans));
  // L'exemple d'un autre contrat, puis un changement de contrat : on revient au réel.
  await p.click('#mode-donnees button[data-mode="exemple"]'); await p.waitForTimeout(800);
  await p.selectOption('#select-contrat', 'X1'); await p.waitForTimeout(1200);
  const x1 = await lireContrat();
  verifier('revenir a X1 redonne les comptes initiaux',
    x1.plans === TOTAL && x1.etats === etats0 && x1.pied === pied0, JSON.stringify(x1));
  verifier('et un changement de contrat ramene aux donnees reelles', x1.mode === 'false', x1.mode);
  // Sans liste de contrats — ou avec un seul — rien à choisir : le sélecteur disparaît.
  await p.evaluate(() => { const s = window.__jeuDExemple('X1'); delete s.contrats; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  const seul = await p.evaluate(() => ({
    cache: document.getElementById('choix-contrat').hidden &&
           document.getElementById('select-contrat').offsetParent === null,
    nomCache: document.getElementById('contrat-courant').hidden,
    plans: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('sans liste de contrats, le selecteur et le rappel disparaissent',
    seul.cache && seul.nomCache && seul.plans === TOTAL, JSON.stringify(seul));
  await p.evaluate(() => { const s = window.__jeuDExemple('X1'); s.contrats = [{ id: 'X1', nom: 'X1' }]; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  verifier('avec un seul contrat liste, pareil',
    await p.evaluate(() => document.getElementById('choix-contrat').hidden &&
      document.getElementById('contrat-courant').hidden));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('X1')));
  await p.waitForTimeout(900);
  verifier('la liste revenue, le selecteur revient',
    await p.evaluate(() => !document.getElementById('choix-contrat').hidden &&
      [...document.querySelectorAll('#select-contrat option')].map(o => o.value).join(',') === 'X1,X2,X3' &&
      document.getElementById('select-contrat').value === 'X1'));

  // =================================================================
  /* Une référence UD = racine (l'identité du plan : 3 lettres, 4 chiffres, A,
     3 chiffres) + indice (3 chiffres) + révision (une lettre). Le parseur
     tolère les séparateurs et la casse ; hors format, la chaîne entière tient
     lieu de racine et la référence n'est jamais appariée. */
  section('Références UD : le parseur');
  const formes = await p.evaluate(() => {
    const f = window.__analyserUD;
    return ['HEL0225A017001A', 'hel0225a017001a', 'HEL-0225-A017-001-A', 'HEL_0225_A017_001_A',
            'HEL 0225 A017 001 A', 'HEL.0225.A017.001.A', 'HEL/0225/A017/001/A', '  hel-0225 a 017.002/b ',
            'CAB1000A001003C', 'UD-24-1037', '  ud-24-1037 ', 'HEL0225A017001', 'HEL0225B017001A', '', null]
      .map(r => [r, f(r)]);
  });
  const lu = r => JSON.stringify(r);
  const canon = lu({ racine: 'HEL0225A017', indice: '001', revision: 'A', valide: true });
  formes.slice(0, 7).forEach(([forme, res]) => {
    verifier('« ' + forme + ' » se lit HEL0225A017 / 001 / A', lu(res) === canon, lu(res));
  });
  verifier('séparateurs mélangés, minuscules et espaces autour : 002 / B',
    lu(formes[7][1]) === lu({ racine: 'HEL0225A017', indice: '002', revision: 'B', valide: true }), lu(formes[7][1]));
  verifier('une autre racine, indice 003, révision C',
    lu(formes[8][1]) === lu({ racine: 'CAB1000A001', indice: '003', revision: 'C', valide: true }), lu(formes[8][1]));
  verifier('hors format : la chaîne entière est la racine, et rien d’autre',
    formes[9][1].racine === 'UD-24-1037' && formes[9][1].valide === false &&
    formes[9][1].indice === '' && formes[9][1].revision === '', lu(formes[9][1]));
  verifier('hors format, épurée : majuscules, sans espaces autour',
    formes[10][1].racine === 'UD-24-1037' && !formes[10][1].valide, lu(formes[10][1]));
  verifier('sans révision, ce n’est pas une référence au format',
    !formes[11][1].valide && formes[11][1].racine === 'HEL0225A017001', lu(formes[11][1]));
  verifier('un « B » à la place du « A » de la racine non plus', !formes[12][1].valide, lu(formes[12][1]));
  verifier('vide et null donnent une racine vide, non valide, sans planter',
    formes[13][1].racine === '' && !formes[13][1].valide && formes[14][1].racine === '' && !formes[14][1].valide);

  // =================================================================
  /* Six plans de la démonstration ont été réémis au fil des semaines : même
     racine, autre indice ou révision. Le journal et le comparatif doivent y
     voir un changement d'indice — jamais un disparu plus un nouveau. */
  section('Changements d’indice : appariement par racine');
  const colRef = () => [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
  const refsTable = await p.evaluate(() => {
    const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
    return [...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.children[i].textContent.trim());
  });
  verifier('toutes les références du tableau sont au format complet : racine, indice, révision',
    refsTable.length === TOTAL && refsTable.every(r => /^[A-Z]{3}\d{4}A\d{3}\d{3}[A-C]$/.test(r)),
    refsTable.slice(0, 3).join(' '));
  const app = await p.evaluate(() => {
    const J = window.__journal(), C = window.__comparatif(), racine = r => window.__analyserUD(r).racine;
    const indices = [], nouveaux = [], disparus = [];
    J.forEach(s => s.evenements.forEach(e => {
      if (e.type === 'indice') indices.push({ i: s.i, ref: e.ref, ancienne: e.ancienne, avant: e.avant, apres: e.apres });
      else if (e.type === 'nouveau') nouveaux.push(e.ref);
      else if (e.type === 'disparu') disparus.push(e.ref);
    }));
    const racines = indices.map(x => racine(x.ref));
    const derniere = Math.max.apply(null, indices.map(x => x.i));
    return {
      indices, nouveaux, disparus,
      semaines: new Set(indices.map(x => x.i)).size,
      memeRacine: indices.every(x => racine(x.ref) === racine(x.ancienne) && x.ref !== x.ancienne),
      avecEtat: indices.filter(x => x.avant !== x.apres).length,
      touches: nouveaux.concat(disparus).filter(r => racines.indexOf(racine(r)) !== -1),
      attenduComparatif: indices.filter(x => x.i === derniere).map(x => x.ref).sort(),
      comparatif: C && C.indice ? C.indice.slice().sort() : null,
      reemissions: C && C.reemissions ? C.reemissions : null
    };
  });
  verifier('le journal porte les six réémissions fabriquées', app.indices.length === 6, String(app.indices.length));
  verifier('à six semaines différentes', app.semaines === 6, String(app.semaines));
  verifier('chacune garde sa racine et change de référence', app.memeRacine, lu(app.indices.slice(0, 2)));
  verifier('deux d’entre elles changent aussi d’état au passage', app.avecEtat === 2, String(app.avecEtat));
  verifier('aucun de ces plans n’est compté comme nouveau ni disparu', app.touches.length === 0, lu(app.touches));
  verifier('les deux plans réellement apparus restent des nouveaux, et rien n’a disparu',
    app.nouveaux.length === 2 && app.disparus.length === 0, app.nouveaux.length + ' / ' + app.disparus.length);
  verifier('le journal parle des nouvelles références, celles du tableau',
    app.indices.every(x => refsTable.indexOf(x.ref) !== -1 && refsTable.indexOf(x.ancienne) === -1));
  verifier('le comparatif « depuis l’import » porte le lot des changements d’indice de la dernière semaine',
    app.comparatif && app.comparatif.length >= 1 && lu(app.comparatif) === lu(app.attenduComparatif),
    lu(app.comparatif) + ' vs ' + lu(app.attenduComparatif));
  verifier('avec, pour chacun, l’ancienne et la nouvelle référence',
    app.reemissions && app.reemissions.length === app.comparatif.length &&
    app.reemissions.every(r => r.ancienne && r.ref && r.ancienne !== r.ref), lu(app.reemissions));

  const domIndice = await p.evaluate(() => ({
    puce: (document.querySelector('.puce-delta[data-delta="indice"]') || { textContent: '' }).textContent,
    pastille: !!document.querySelector('.puce-delta[data-delta="indice"] .pastille.neutre'),
    comptes: [...document.querySelectorAll('.compte-passage[data-passage="indice"]')].map(b => b.textContent),
    bouton: !!document.querySelector('#filtre-journal button[data-journal="indice"]')
  }));
  verifier('la puce « changements d’indice » est là, avec une pastille neutre',
    /changements? d’indice/.test(domIndice.puce) && domIndice.pastille, domIndice.puce);
  verifier('chaque semaine concernée compte son changement d’indice, en bouton',
    domIndice.comptes.length === 6 && domIndice.comptes.every(t => /^1 changement d’indice$/.test(t)),
    lu(domIndice.comptes));
  verifier('et le filtre du journal propose aussi les changements d’indice', domIndice.bouton);

  // Survoler la puce : les deux références, ancienne → nouvelle.
  await p.evaluate(() => document.getElementById('comparatif').scrollIntoView({ block: 'center' }));
  await p.waitForTimeout(250);
  const bbPuce = await (await p.$('.puce-delta[data-delta="indice"]')).boundingBox();
  await p.mouse.move(bbPuce.x + 6, bbPuce.y + bbPuce.height / 2); await p.waitForTimeout(200);
  const survol = await p.evaluate(() => document.getElementById('bulle').textContent);
  verifier('survoler la puce montre « ancienne → nouvelle »',
    /[A-Z]{3}\d{4}A\d{6}[A-Z] → [A-Z]{3}\d{4}A\d{6}[A-Z]/.test(survol), survol.slice(0, 100));
  await p.mouse.move(5, 5); await p.waitForTimeout(150);

  // Cliquer la puce : le tableau ne montre plus que les plans réémis, sous leur nouvelle référence.
  await p.click('.puce-delta[data-delta="indice"]'); await p.waitForTimeout(500);
  const filtreIndice = await p.evaluate(() => {
    const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
    return {
      lignes: [...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.children[i].textContent.trim()).sort(),
      presse: document.querySelector('.puce-delta[data-delta="indice"]').getAttribute('aria-pressed'),
      jeton: document.getElementById('filtres-actifs').textContent
    };
  });
  verifier('cliquer « changements d’indice » filtre le tableau sur les nouvelles références',
    lu(filtreIndice.lignes) === lu(app.comparatif), lu(filtreIndice.lignes));
  verifier('la puce se marque pressée et le bandeau nomme le filtre',
    filtreIndice.presse === 'true' && /changements d’indice/.test(filtreIndice.jeton), filtreIndice.jeton);
  await p.click('.puce-delta[data-delta="indice"]'); await p.waitForTimeout(500);
  verifier('re-cliquer rend tous les plans',
    await p.evaluate(t => document.querySelectorAll('#corps-tableau tr').length === t, TOTAL));

  // Le compte du journal filtre sur les changements d'indice ; la ligne se lit ancienne → nouvelle.
  await p.click('.compte-passage[data-passage="indice"] >> nth=0'); await p.waitForTimeout(400);
  for (let garde = 0; garde < 20; garde++) {
    const plie = await p.$('.journal-plier[aria-expanded="false"]');
    if (!plie) break;
    await plie.click(); await p.waitForTimeout(90);
  }
  await p.waitForTimeout(250);
  const lignesIndice = await p.evaluate(() => ({
    total: document.querySelectorAll('.journal-ligne').length,
    indice: [...document.querySelectorAll('.journal-ligne.indice')].map(b => ({
      ref: b.dataset.ref, type: b.dataset.type,
      ancienne: (b.querySelector('.ref-indice .ancienne') || { textContent: '' }).textContent,
      nouvelle: (b.querySelector('.ref-indice .nouvelle') || { textContent: '' }).textContent,
      etats: b.querySelectorAll('.vers .etiq-etat').length,
      quoi: b.querySelector('.quoi').textContent
    })),
    presse: [...document.querySelectorAll('#filtre-journal button')]
      .map(b => b.dataset.journal + ':' + b.getAttribute('aria-pressed')).join(' ')
  }));
  verifier('sous ce filtre, le journal ne montre que les six réémissions',
    lignesIndice.total === 6 && lignesIndice.indice.length === 6, lignesIndice.total + ' / ' + lignesIndice.indice.length);
  verifier('chaque ligne se lit « ancienne → nouvelle », puis l’état avant et après',
    lignesIndice.indice.every(l => l.type === 'indice' && /^[A-Z]{3}\d{4}A\d{6}[A-Z]$/.test(l.ancienne) &&
      l.nouvelle === '→ ' + l.ref && l.etats === 2), lu(lignesIndice.indice[0]));
  verifier('et nomme le plan', lignesIndice.indice.every(l => l.quoi.trim() !== ''));
  verifier('le filtre du journal reflète le choix',
    lignesIndice.presse === ':false termine:false encours:false afaire:false indice:true', lignesIndice.presse);
  const refIndice = lignesIndice.indice[0].ref;
  await p.click('.journal-ligne.indice >> nth=0'); await p.waitForTimeout(500);
  verifier('cliquer une réémission réduit le tableau au plan, sous sa nouvelle référence',
    await p.evaluate(r => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
      const trs = document.querySelectorAll('#corps-tableau tr');
      return trs.length === 1 && trs[0].children[i].textContent.trim() === r;
    }, refIndice), refIndice);
  await p.click('.journal-ligne.indice >> nth=0'); await p.waitForTimeout(400);
  await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(400);
  verifier('« Tout » rend le journal entier',
    await p.evaluate(t => document.querySelectorAll('.journal-ligne').length > 6 &&
      document.querySelectorAll('#corps-tableau tr').length === t, TOTAL));
  await reinitialiser(p);

  // =================================================================
  /* La bulle d'une semaine résume ce qui a bougé — des comptes, une ligne
     chacun — et ne liste plus les plans : le journal, dessous, s'en charge. */
  section('La bulle du graphique résume la semaine sans lister les plans');
  await p.evaluate(() => document.getElementById('cadre-graphe').scrollIntoView({ block: 'center' }));
  await p.waitForTimeout(300);
  const bulles = [];
  for (const z of await p.$$('.zone-clic')) {
    const bb = await z.boundingBox();
    if (!bb || bb.y < 0 || bb.y > 900) continue;
    await p.mouse.move(bb.x + bb.width / 2, bb.y + bb.height * 0.6); await p.waitForTimeout(80);
    bulles.push(await p.evaluate(() => ({
      texte: document.getElementById('bulle').textContent,
      lignes: [...document.querySelectorAll('#bulle .bulle-comptes .bulle-ligne')].map(l => ({
        pastille: !!l.querySelector('.pastille'), n: (l.querySelector('.n') || { textContent: '' }).textContent,
        texte: l.textContent
      }))
    })));
  }
  await p.mouse.move(5, 5); await p.waitForTimeout(150);
  const releves = bulles.filter(b => /Relevé du \d{4}-S\d{2}/.test(b.texte));
  verifier('chaque semaine relevée a sa bulle « Relevé du … »', releves.length >= 5, String(releves.length));
  verifier('elle dit « terminés N / total »',
    releves.every(b => /terminés\s*\d+\s*\/\s*\d+/.test(b.texte)), (releves[0] || {}).texte);
  verifier('et « depuis le précédent ±n » dès le deuxième relevé',
    releves.filter(b => /depuis le précédent\s*[+\-−]?\s*\d/.test(b.texte)).length >= releves.length - 1);
  verifier('plus aucune référence de plan dans la bulle',
    releves.every(b => !/[A-Z]{3}\d{4}A\d{3}/.test(b.texte)), (releves.find(b => /[A-Z]{3}\d{4}A\d{3}/.test(b.texte)) || {}).texte);
  verifier('ni « et N autres »', releves.every(b => !/autres/.test(b.texte)));
  verifier('les semaines qui ont bougé donnent leurs comptes : passés en terminé…',
    releves.filter(b => /passés? en terminé/.test(b.texte)).length >= 3);
  verifier('… nouveaux, et changements d’indice',
    releves.some(b => /nouveaux/.test(b.texte)) && releves.some(b => /changements? d’indice/.test(b.texte)));
  const toutesLignes = releves.reduce((l, b) => l.concat(b.lignes), []);
  verifier('une ligne par compte : pastille, mot, nombre à droite',
    toutesLignes.length >= 6 && toutesLignes.every(l => l.pastille && /^\d+$/.test(l.n.replace(/\s/g, ''))),
    lu(toutesLignes.slice(0, 2)));
  verifier('les changements d’indice comptés dans les bulles font les six du journal',
    toutesLignes.filter(l => /changements? d’indice/.test(l.texte)).reduce((s, l) => s + Number(l.n), 0) === 6);

  // =================================================================
  section('Chargement et cohérence des chiffres');
  const kpi = await p.evaluate(() => ({
    titre: document.title,
    phrase: document.getElementById('phrase').textContent,
    pct: document.querySelector('.barre span').textContent,
    etats: [...document.querySelectorAll('.etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
    parts: [...document.querySelectorAll('.barre span')].map(s => parseFloat(s.style.width)),
    compte: document.getElementById('compte').textContent,
    lignes: (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length)
  }));
  const somme = kpi.etats.reduce((a, b) => a + b, 0);
  verifier('le titre de la page est posé', kpi.titre === 'Suivi FWD', kpi.titre);
  verifier('les quatre états totalisent le nombre de plans', somme === TOTAL, somme + ' vs ' + TOTAL);
  verifier('le % est écrit dans la barre et correspond aux terminés',
    kpi.pct.replace(/\D/g, '') === String(Math.round(kpi.etats[0] / TOTAL * 100)), 'lu=' + kpi.pct);
  verifier('plus de pourcentage en doublon au-dessus de la barre',
    await p.evaluate(() => !document.getElementById('pourcentage') && !document.querySelector('.etat-part')));
  verifier('la barre totalise 100 %', Math.abs(kpi.parts.reduce((a, b) => a + b, 0) - 100) < 0.2);
  verifier('le tableau annonce tous les plans', kpi.compte.indexOf(String(TOTAL)) !== -1, kpi.compte);
  verifier('le tableau affiche toutes les lignes', kpi.lignes === TOTAL, kpi.lignes + ' lignes');

  // =================================================================
  section('Alignement des chiffres et filets de séparation');
  const align = await p.evaluate(() => {
    const zone = document.getElementById('etats').getBoundingClientRect();
    const barre = [...document.querySelectorAll('.barre span')].map(s => s.getBoundingClientRect());
    const btns = [...document.querySelectorAll('.etat-btn')].map(b => b.getBoundingClientRect());
    const traits = [...document.querySelectorAll('.filets i')];
    const segs = [...document.querySelectorAll('.barre span')];
    return {
      dansLeCadre: btns.every(b => b.left >= zone.left - 1 && b.right <= zone.right + 1),
      chevauchement: btns.some((b, i) => i > 0 && b.left < btns[i - 1].right),
      ecarts: btns.map((b, i) => barre[i] ? Math.round((b.left + b.right) / 2 - (barre[i].left + barre[i].right) / 2) : null),
      nbTraits: traits.length,
      attendus: segs.length - 1,
      decalages: traits.map((t, i) => Math.round(t.getBoundingClientRect().left - segs[i].getBoundingClientRect().right)),
      hauteurTrait: traits.length ? Math.round(traits[0].getBoundingClientRect().height) : 0,
      basTrait: traits.length ? traits[0].getBoundingClientRect().bottom : 0,
      basChiffres: Math.max(...btns.map(b => b.bottom)),
      opacite: traits.length ? getComputedStyle(traits[0]).opacity : '0'
    };
  });
  verifier('aucune étiquette ne sort du cadre', align.dansLeCadre);
  verifier('aucune étiquette n\'en chevauche une autre', !align.chevauchement);
  verifier('chaque chiffre est centré sur son segment (±40 px)',
    align.ecarts.every(e => e === null || Math.abs(e) <= 40), 'écarts=' + JSON.stringify(align.ecarts));
  verifier('un filet par coupure de la barre', align.nbTraits === align.attendus,
    align.nbTraits + '/' + align.attendus);
  verifier('chaque filet tombe sur sa coupure (±3 px)',
    align.decalages.every(e => Math.abs(e) <= 3), JSON.stringify(align.decalages));
  verifier('les filets descendent jusqu\'aux chiffres (≥ 60 px)',
    align.hauteurTrait >= 60, align.hauteurTrait + ' px');
  verifier('les filets ne dépassent pas les chiffres de plus de 20 px',
    align.basTrait - align.basChiffres < 20, Math.round(align.basTrait - align.basChiffres) + ' px');
  verifier('les filets sont assez visibles (opacité ≥ .35)',
    parseFloat(align.opacite) >= 0.35, align.opacite);

  // =================================================================
  section('Filtres par état');
  for (const etat of ['termine', 'encours', 'afaire', 'vide']) {
    await p.click(`.etat-btn[data-etat="${etat}"]`); await p.waitForTimeout(350);
    const r = await p.evaluate(() => ({
      compte: document.getElementById('compte').textContent,
      lignes: (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length),
      presse: document.querySelectorAll('.etat-btn[aria-pressed="true"]').length
    }));
    verifier(`filtrer « ${etat} » ne garde qu'un seul état actif`, r.presse === 1, r.presse + ' actifs');
    verifier(`filtrer « ${etat} » réduit le tableau`, r.lignes > 0 && r.lignes < TOTAL, r.lignes + ' lignes');
    await p.click(`.etat-btn[data-etat="${etat}"]`); await p.waitForTimeout(300);
  }
  verifier('re-cliquer retire le filtre',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));
  await p.click('.etat-btn[data-etat="vide"]'); await p.waitForTimeout(350);
  verifier('« non renseignés » ne laisse que des cellules FWD vides',
    await p.evaluate(() => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => /^Avancement$/.test(t.textContent.trim()));
      if (i < 0) return false;
      return [...document.querySelectorAll('#corps-tableau tr')]
        .every(tr => /^(|—|non renseigné)$/i.test(tr.children[i].textContent.trim()));
    }));
  await reinitialiser(p);

  // =================================================================
  /* Le classeur rend la date telle qu'il l'affiche : jour d'abord sur une
     feuille francaise, annee d'abord ailleurs. Lire un seul ordre laisserait
     l'anciennete vide sur la moitie des exports, sans rien signaler. */
  section('Lecture des dates, dans les deux ordres');
  const dates = await p.evaluate(() => {
    const f = window.__anneeEtMois;
    if (!f) return null;
    const dit = v => { const r = f(v); return r ? r.annee + '/' + r.mois : null; };
    return {
      iso:        dit('2020-07-16'),
      isoHeure:   dit('2020-07-16T22:00:00.000Z'),
      isoPoints:  dit('2020.07.16'),
      fr:         dit('16/07/2020'),
      frTirets:   dit('16-07-2020'),
      frCourt:    dit('16/07/20'),
      ambigu:     dit('05/07/2020'),
      jourGrand:  dit('25/07/2020'),
      moisGrand:  dit('07/25/2020'),
      vide:       dit(''),
      nul:        dit(null),
      texte:      dit('sans date'),
      moisFaux:   dit('2020-13-16'),
      presqueUne: dit('12345678')
    };
  });
  verifier('la fonction de lecture des dates est accessible au test', !!dates);
  if (dates) {
    verifier('l\'ordre ISO est lu, avec ou sans heure',
      dates.iso === '2020/7' && dates.isoHeure === '2020/7' && dates.isoPoints === '2020/7',
      JSON.stringify(dates));
    verifier('l\'ordre francais est lu aussi',
      dates.fr === '2020/7' && dates.frTirets === '2020/7' && dates.frCourt === '2020/7',
      JSON.stringify(dates));
    verifier('deux nombres sous treize : on tranche a la francaise',
      dates.ambigu === '2020/7', String(dates.ambigu));
    verifier('un nombre au-dessus de douze est forcement le jour',
      dates.jourGrand === '2020/7' && dates.moisGrand === '2020/7',
      dates.jourGrand + ' / ' + dates.moisGrand);
    verifier('ce qui n\'est pas une date ne fait pas semblant d\'en etre une',
      [dates.vide, dates.nul, dates.texte, dates.moisFaux, dates.presqueUne]
        .every(v => v === null), JSON.stringify(dates));
  }
  /* L'anciennete et le regroupement par mois en dependent : si la lecture
     echoue, ils se taisent au lieu de se tromper, et personne ne le voit. */
  const dimAvant = await p.evaluate(() => document.getElementById('dim-critique').value);
  const aMois = await p.evaluate(() =>
    [...document.getElementById('dim-critique').options].some(o => o.value === '_mois'));
  if (aMois) {
    await p.selectOption('#dim-critique', '_mois');
    await p.waitForTimeout(600);
    verifier('le regroupement par mois nomme de vrais mois, pas des tirets',
      await p.evaluate(() => {
        const noms = [...document.querySelectorAll('.critique-ligne')].map(l => l.dataset.groupe);
        if (!noms.length) return false;
        return noms.filter(n => n === '\u2014' || n === '-').length / noms.length < 0.5;
      }),
      await p.evaluate(() => [...document.querySelectorAll('.critique-ligne')]
        .slice(0, 4).map(l => l.dataset.groupe).join(' | ')));
    await p.selectOption('#dim-critique', dimAvant);
    await p.waitForTimeout(500);
  }
  await reinitialiser(p);

  // =================================================================
  section('Recherche — entrées hostiles');
  /* La reference n'est plus la premiere cellule : dans l'ordre de la feuille
     une colonne sans intitule la precede. On la cherche par son en-tete. */
  const premiereRef = await p.evaluate(() => {
    const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
    return document.querySelector('#corps-tableau tr').children[i].textContent.trim();
  });
  const entrees = [
    { q: premiereRef, attendu: n => n === 1, nom: 'une référence exacte' },
    { q: premiereRef.toLowerCase(), attendu: n => n === 1, nom: 'la même en minuscules' },
    { q: 'bati', attendu: n => n > 0, nom: 'sans accent trouve l\'accentué (bâti)' },
    { q: 'BÂTI', attendu: n => n > 0, nom: 'accentué en capitales' },
    { q: 'treuil de sauvetage', attendu: n => n > 0, nom: 'plusieurs mots' },
    { q: '<b>injection</b>', attendu: n => n >= 0, nom: 'du HTML brut' },
    { q: '<script>window.__casse=1</script>', attendu: n => n === 0, nom: 'une balise script' },
    { q: '.*', attendu: n => n === 0, nom: 'une expression régulière' },
    { q: '((((', attendu: n => n === 0, nom: 'des parenthèses déséquilibrées' },
    { q: '\\', attendu: n => n === 0, nom: 'un antislash seul' },
    { q: '   ', attendu: n => n === TOTAL, nom: 'des espaces seuls' },
    { q: 'zzzzzzzz', attendu: n => n === 0, nom: 'rien du tout' },
    { q: 'a'.repeat(3000), attendu: n => n === 0, nom: 'une chaîne de 3000 caractères' },
    { q: '🚁 émoji', attendu: n => n === 0, nom: 'un émoji' }
  ];
  for (const e of entrees) {
    await p.fill('#recherche', e.q); await p.waitForTimeout(320);
    const n = await p.evaluate(() => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length));
    verifier(`recherche : ${e.nom}`, e.attendu(n), n + ' lignes');
  }
  verifier('aucun script injecté n\'a été exécuté',
    await p.evaluate(() => typeof window.__casse === 'undefined'));
  verifier('aucune balise n\'est passée dans le DOM du tableau',
    await p.evaluate(() => !document.querySelector('#corps-tableau b, #corps-tableau script')));
  await p.fill('#recherche', ''); await p.waitForTimeout(320);
  verifier('vider la recherche rend tous les plans',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));

  // =================================================================
  section('Filtres de colonne');
  await p.fill('input[data-filtre="ata"]', '24'); await p.waitForTimeout(350);
  const f1 = await p.evaluate(() => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length));
  verifier('filtrer une colonne réduit le tableau', f1 > 0 && f1 < TOTAL, f1 + ' lignes');
  await p.fill('#recherche', 'Cockpit'); await p.waitForTimeout(350);
  const f2 = await p.evaluate(() => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length));
  verifier('recherche + filtre colonne se cumulent', f2 <= f1, f2 + ' ≤ ' + f1);
  await p.fill('input[data-filtre="ecp"]', 'ECP-999999'); await p.waitForTimeout(350);
  verifier('trois filtres contradictoires donnent zéro ligne, sans plantage',
    await p.evaluate(() => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === 0));
  verifier('un message explique la sélection vide',
    await p.evaluate(() => /aucun|Aucun/.test(document.getElementById('corps-tableau').parentElement.textContent) ||
                            /0 plan/.test(document.getElementById('compte').textContent)));
  await reinitialiser(p);
  verifier('« tout réinitialiser » vide recherche et filtres',
    await p.evaluate(t => document.getElementById('recherche').value === '' &&
      [...document.querySelectorAll('input[data-filtre]')].every(i => i.value === '') &&
      (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));

  // =================================================================
  section('Tri du tableau');
  const cles = await p.evaluate(() => [...document.querySelectorAll('tr.titres button[data-tri]')].map(b => b.dataset.tri));
  let triOk = true, triDetail = '';
  for (const cle of cles) {
    await p.click(`tr.titres button[data-tri="${cle}"]`); await p.waitForTimeout(220);
    const asc = await p.evaluate(c => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === c);
      return [...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.children[i].textContent.trim());
    }, cle);
    await p.click(`tr.titres button[data-tri="${cle}"]`); await p.waitForTimeout(220);
    const desc = await p.evaluate(c => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === c);
      return [...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.children[i].textContent.trim());
    }, cle);
    if (asc.length !== TOTAL || desc.length !== TOTAL) { triOk = false; triDetail = cle + ' perd des lignes'; break; }
    if (asc.join('|') === desc.join('|') && new Set(asc).size > 1) { triOk = false; triDetail = cle + ' ne s\'inverse pas'; break; }
  }
  verifier('chaque colonne se trie dans les deux sens sans perdre de ligne', triOk, triDetail);
  verifier('aria-sort suit la colonne active',
    await p.evaluate(() => document.querySelectorAll('tr.titres th[aria-sort="ascending"], tr.titres th[aria-sort="descending"]').length === 1));

  // =================================================================
  section('Colonnes : masquer, tout masquer, remettre');
  await p.click('#bascule-colonnes'); await p.waitForTimeout(250);
  const avant = await p.evaluate(() => document.querySelectorAll('tr.titres th').length);
  const cases = await p.evaluate(() => [...document.querySelectorAll('#panneau-colonnes input[data-col]')]
    .filter(i => !i.disabled).map(i => i.dataset.col));
  for (const c of cases) { await p.click(`#panneau-colonnes input[data-col="${c}"]`); await p.waitForTimeout(60); }
  await p.waitForTimeout(350);
  const restant = await p.evaluate(() => document.querySelectorAll('tr.titres th').length);
  verifier('masquer toutes les colonnes possibles en laisse au moins une', restant >= 1, restant + ' colonne(s)');
  verifier('le tableau ne casse pas avec une seule colonne',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));
  await p.click('#tout-colonnes'); await p.waitForTimeout(900);
  /* « Tout afficher » rend TOUTES les colonnes de l'export, y compris celles
     que la page ouvre repliées : c'est bien plus que ce qu'on voyait au départ. */
  const apresTout = await p.evaluate(() => document.querySelectorAll('tr.titres th').length);
  verifier('« tout afficher » remet toutes les colonnes de la feuille',
    apresTout >= avant && apresTout === COLONNES_TOTAL,
    apresTout + ' affichées');
  verifier('la référence UD reste verrouillée',
    await p.evaluate(() => document.querySelector('#panneau-colonnes input[data-col="reference"]').disabled));
  await p.keyboard.press('Escape');
  await p.click('body', { position: { x: 5, y: 5 } }); await p.waitForTimeout(250);

  // =================================================================
  section('Graphique : zoom, déplacement, extrêmes');
  const zoom0 = await p.evaluate(() => document.querySelectorAll('.zone-clic').length);
  await p.click('.segmente button[data-span="52"]'); await p.waitForTimeout(350);
  const zoom1 = await p.evaluate(() => document.querySelectorAll('.zone-clic').length);
  verifier('le bouton « 1 an » élargit la fenêtre', zoom1 > zoom0, zoom0 + ' → ' + zoom1);
  const svg = await p.$('svg.graphe'); const box = await svg.boundingBox();
  await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  for (let i = 0; i < 30; i++) await p.mouse.wheel(0, -400);
  await p.waitForTimeout(400);
  const zoomMax = await p.evaluate(() => document.querySelectorAll('.zone-clic').length);
  verifier('30 crans de zoom avant laissent au moins une semaine', zoomMax >= 1, zoomMax + ' semaines');
  for (let i = 0; i < 60; i++) await p.mouse.wheel(0, 400);
  await p.waitForTimeout(400);
  const zoomMin = await p.evaluate(() => document.querySelectorAll('.zone-clic').length);
  verifier('60 crans de zoom arrière restent bornés', zoomMin > zoomMax && zoomMin < 400, zoomMin + ' semaines');
  verifier('le graphique est toujours dessiné après le zoom',
    await p.evaluate(() => !!document.querySelector('svg.graphe path, svg.graphe polyline')));
  await p.click('.segmente button[data-span="26"]'); await p.waitForTimeout(300);
  const g0 = await p.evaluate(() => [...document.querySelectorAll('svg.graphe .grad')].map(t => t.textContent).join('|'));
  await p.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.55);
  await p.mouse.down();
  await p.mouse.move(box.x - 4000, box.y + box.height * 0.55, { steps: 12 });
  await p.mouse.up(); await p.waitForTimeout(400);
  const g1 = await p.evaluate(() => [...document.querySelectorAll('svg.graphe .grad')].map(t => t.textContent).join('|'));
  verifier('un glisser de 4000 px déplace sans casser', g0 !== g1 && (await p.evaluate(() => document.querySelectorAll('.zone-clic').length)) > 0);
  verifier('le glisser ne sélectionne pas de texte', await p.evaluate(() => String(window.getSelection()).length === 0));
  await p.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.55);
  await p.mouse.down(); await p.mouse.move(box.x + 6000, box.y + box.height * 0.55, { steps: 12 }); await p.mouse.up();
  await p.waitForTimeout(400);
  verifier('un glisser inverse de 6000 px ne vide pas le graphique',
    await p.evaluate(() => document.querySelectorAll('.zone-clic').length > 0));
  await p.click('.segmente button[data-span="26"]'); await p.waitForTimeout(300);

  // =================================================================
  section('Glisser le graphique depuis n\'importe quel point');
  /* Le curseur promet la main sur tout le cadre : le glissement doit donc
     partir de partout, y compris de la frise des jalons et de la marge basse. */
  const cadre = await (await p.$('#cadre-graphe')).boundingBox();
  const derniereSemaine = () => p.evaluate(() =>
    [...document.querySelectorAll('svg.graphe .grad')].map(t => t.textContent).slice(-1)[0]);
  async function balayer(fracY, sens) {
    const y = cadre.y + cadre.height * fracY;
    const depart = cadre.x + cadre.width * (sens < 0 ? 0.75 : 0.25);
    const avant = await derniereSemaine();
    await p.mouse.move(depart, y);
    await p.mouse.down();
    for (let i = 1; i <= 8; i++) await p.mouse.move(depart + sens * i * 30, y);
    await p.mouse.up(); await p.waitForTimeout(300);
    return { avant, apres: await derniereSemaine() };
  }
  for (const fracY of [0.04, 0.12, 0.35, 0.6, 0.88]) {
    const r = await balayer(fracY, -1);
    verifier(`glisser vers la gauche depuis ${Math.round(fracY * 100)} % de la hauteur`,
      r.avant !== r.apres, r.avant + ' → ' + r.apres);
  }
  const retour = await balayer(0.5, +1);
  verifier('glisser vers la droite ramène en arrière', retour.avant !== retour.apres,
    retour.avant + ' → ' + retour.apres);
  const curseur = await p.evaluate(() => getComputedStyle(document.getElementById('cadre-graphe')).cursor);
  verifier('le cadre annonce bien la main', curseur === 'grab', curseur);
  verifier('le cadre ne reste pas bloqué en « glissement »',
    await p.evaluate(() => document.getElementById('cadre-graphe').dataset.glisse !== 'true'));
  await p.mouse.move(cadre.x + cadre.width * 0.5, cadre.y + cadre.height * 0.5);
  await p.waitForTimeout(300);
  verifier('l\'infobulle revient après un glissement',
    await p.evaluate(() => document.getElementById('bulle').dataset.visible === 'true'));
  // Un simple clic dans la frise du haut doit poser un jalon, pas glisser.
  await p.mouse.click(cadre.x + cadre.width * 0.75, cadre.y + cadre.height * 0.05);
  await p.waitForTimeout(350);
  verifier('un clic net dans la frise ouvre quand même la saisie de jalon',
    await p.evaluate(() => document.getElementById('saisie-jalon').dataset.ouvert === 'true'));
  await p.keyboard.press('Escape'); await p.waitForTimeout(250);
  verifier('Échap referme la saisie',
    await p.evaluate(() => document.getElementById('saisie-jalon').dataset.ouvert === 'false'));
  // Un glissement parti d'une poignée déplace le jalon, jamais la fenêtre.
  const avantPoignee = await derniereSemaine();
  const poigneeEl = await p.$('.jalon-poignee');
  if (poigneeEl) {
    const bp = await poigneeEl.boundingBox();
    await p.mouse.move(bp.x + bp.width / 2, bp.y + bp.height / 2);
    await p.mouse.down();
    for (let i = 1; i <= 6; i++) await p.mouse.move(bp.x + bp.width / 2 + i * 12, bp.y + bp.height / 2);
    await p.mouse.up(); await p.waitForTimeout(400);
  }
  verifier('glisser une poignée de jalon ne déplace pas la fenêtre',
    (await derniereSemaine()) === avantPoignee);
  await p.click('.segmente button[data-span="26"]'); await p.waitForTimeout(300);

  // =================================================================
  section('Jalons : ajout, doublon, texte hostile, suppression');
  const j0 = await p.evaluate(() => document.querySelectorAll('.jalon-supp').length);
  verifier('des jalons sont présents au départ', j0 >= 1, j0 + ' jalon(s)');
  async function poserJalon(indexDepuisFin, texte) {
    const zones = await p.$$('.zone-clic');
    if (!zones.length) return false;
    const z = zones[Math.max(0, zones.length - indexDepuisFin)];
    const bz = await z.boundingBox();
    await p.mouse.move(bz.x + bz.width / 2, bz.y + bz.height / 2);
    await p.mouse.down(); await p.mouse.up(); await p.waitForTimeout(350);
    const ouvert = await p.evaluate(() => document.getElementById('saisie-jalon').dataset.ouvert === 'true');
    if (!ouvert) return false;
    await p.fill('#champ-jalon', texte);
    await p.press('#champ-jalon', 'Enter'); await p.waitForTimeout(400);
    return true;
  }
  verifier('cliquer une semaine ouvre la saisie et pose un jalon', await poserJalon(5, 'Test recette'));
  verifier('le jalon saisi apparaît avec son texte',
    await p.evaluate(() => [...document.querySelectorAll('.jalon-texte')].some(t => t.textContent === 'Test recette')));
  verifier('reposer un jalon sur la même semaine n\'ouvre pas la saisie',
    !(await poserJalon(5, 'Doublon')));
  verifier('aucun doublon de jalon n\'a été créé',
    await p.evaluate(() => [...document.querySelectorAll('.jalon-texte')].filter(t => /Test recette|Doublon/.test(t.textContent)).length === 1));
  await poserJalon(9, '<img src=x onerror="window.__xss=1">');
  verifier('un texte de jalon avec balise ne s\'exécute pas',
    await p.evaluate(() => typeof window.__xss === 'undefined' && !document.querySelector('.jalon img')));
  await poserJalon(12, 'X'.repeat(400));
  verifier('un jalon de 400 caractères ne fait pas déborder la page',
    await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2),
    await p.evaluate(() => document.documentElement.scrollWidth + ' vs ' + window.innerWidth));
  await poserJalon(15, '');
  verifier('un jalon sans texte reçoit un libellé par défaut',
    await p.evaluate(() => [...document.querySelectorAll('.jalon-texte')].every(t => t.textContent.trim().length > 0)));
  verifier('aucune étiquette de jalon n\'en chevauche une autre',
    await p.evaluate(() => {
      const r = [...document.querySelectorAll('.jalon-texte')].map(t => t.getBoundingClientRect())
        .sort((a, b) => a.top - b.top || a.left - b.left);
      for (let i = 1; i < r.length; i++) {
        const a = r[i - 1], b = r[i];
        if (Math.abs(a.top - b.top) < 2 && b.left < a.right - 1) return false;
      }
      return true;
    }));
  const poignee = await p.$('.jalon-poignee');
  if (poignee) {
    await poignee.focus();
    const avantD = await p.evaluate(() => document.querySelectorAll('.jalon-poignee').length);
    await p.keyboard.press('ArrowRight'); await p.waitForTimeout(300);
    await p.keyboard.press('ArrowLeft'); await p.waitForTimeout(300);
    verifier('les flèches déplacent un jalon sans le perdre',
      await p.evaluate(() => document.querySelectorAll('.jalon-poignee').length) === avantD);
  }
  await p.click('.segmente button[data-span="0"]'); await p.waitForTimeout(400);
  let garde = 0;
  while ((await p.evaluate(() => document.querySelectorAll('.jalon-supp').length)) > 0 && garde++ < 40) {
    await p.click('.jalon-supp >> nth=0'); await p.waitForTimeout(220);
  }
  verifier('on peut supprimer tous les jalons',
    await p.evaluate(() => document.querySelectorAll('.jalon-supp').length === 0));
  verifier('sans jalon, le bloc par groupe bascule en mode « rythme actuel »',
    await p.evaluate(() => document.getElementById('zone-critique').classList.contains('sans-jalon')));
  verifier('sans jalon, le graphique tient toujours debout',
    await p.evaluate(() => document.querySelectorAll('.zone-clic').length > 0));

  // =================================================================
  section('Bloc par groupe : colonnes triables');
  await poserJalon(6, 'Jalon de test');
  await p.waitForTimeout(300);
  const tris = await p.evaluate(() => [...document.querySelectorAll('button[data-trig]')].map(b => b.dataset.trig));
  verifier('cinq colonnes triables avec un jalon', tris.length === 5, JSON.stringify(tris));
  verifier('les en-têtes sont centrés (sauf la répartition)',
    await p.evaluate(() => {
      const c = [...document.querySelectorAll('.critique-tete > span')];
      return c.filter(s => getComputedStyle(s).justifyContent === 'center').length === c.length - 1;
    }));
  verifier('les valeurs sont centrées',
    await p.evaluate(() => ['.critique-nom', '.critique-total', '.critique-fin', '.critique-effort', '.critique-date']
      .every(sel => { const e = document.querySelector(sel); return !e || getComputedStyle(e).textAlign === 'center'; })));

  function lire(cle) {
    return p.evaluate(c => [...document.querySelectorAll('.critique-ligne')].map(l => {
      const sel = { nom: '.critique-nom', total: '.critique-total', requis: '.critique-fin',
                    tension: '.critique-effort .v', fin: '.critique-date .v' }[c];
      const e = l.querySelector(sel);
      return e ? e.textContent.trim() : '';
    }), cle);
  }
  for (const cle of tris) {
    await p.click(`button[data-trig="${cle}"]`); await p.waitForTimeout(280);
    const a = await lire(cle);
    await p.click(`button[data-trig="${cle}"]`); await p.waitForTimeout(280);
    const b = await lire(cle);
    verifier(`tri « ${cle} » : les deux sens diffèrent`,
      a.join('|') !== b.join('|') || new Set(a).size === 1, JSON.stringify(a));
    verifier(`tri « ${cle} » : aucune ligne perdue`, a.length === b.length && a.length >= 5,
      a.length + '/' + b.length);
    await p.click(`button[data-trig="${cle}"]`); await p.waitForTimeout(250);
  }
  verifier('un troisième clic rend le classement par défaut',
    await p.evaluate(() => document.querySelectorAll('button[data-trig][data-actif="true"]').length === 0));
  await p.click('button[data-trig="nom"]'); await p.waitForTimeout(280);
  const parNom = await lire('nom');
  verifier('le tri par ATA est bien numérique et croissant',
    parNom.every((v, i) => i === 0 || Number(parNom[i - 1]) <= Number(v)), JSON.stringify(parNom));
  await p.click('button[data-trig="total"]'); await p.waitForTimeout(280);
  const parTotal = (await lire('total')).map(Number);
  verifier('le tri par nombre de plans est décroissant au premier clic',
    parTotal.every((v, i) => i === 0 || parTotal[i - 1] >= v), JSON.stringify(parTotal));

  // =================================================================
  section('Bloc par groupe : cohérence des chiffres');
  const coh = await p.evaluate(() => {
    const lignes = [...document.querySelectorAll('.critique-ligne')];
    return {
      totaux: lignes.map(l => +l.querySelector('.critique-total').textContent),
      dates: lignes.map(l => l.querySelector('.critique-date .v').textContent.trim()),
      efforts: lignes.map(l => l.querySelector('.critique-effort .v').textContent.trim()),
      barres: lignes.map(l => [...l.querySelectorAll('.critique-barre span')]
        .reduce((s, x) => s + parseFloat(x.style.width), 0))
    };
  });
  verifier('la somme des plans par groupe est complète',
    coh.totaux.reduce((a, b) => a + b, 0) === TOTAL, String(coh.totaux.reduce((a, b) => a + b, 0)));
  verifier('chaque répartition totalise 100 %',
    coh.barres.every(b => Math.abs(b - 100) < 0.5), JSON.stringify(coh.barres.map(b => b.toFixed(1))));
  verifier('« fin estimée » est une semaine ISO, « — » ou « soldé »',
    coh.dates.every(v => /^\d{4}-S\d{2}$/.test(v) || v === '—' || v === 'soldé'), JSON.stringify(coh.dates));
  verifier('« effort demandé » porte le facteur et le rythme',
    coh.efforts.every(v => /^×\d+,\d/.test(v) || /sold|rien/.test(v)), JSON.stringify(coh.efforts.slice(0, 3)));

  // =================================================================
  section('Panneau d\'explication de la fin estimée');
  verifier('le panneau est fermé au départ',
    await p.evaluate(() => !document.getElementById('panneau-fin') &&
      document.querySelector('button[data-aide]').getAttribute('aria-expanded') === 'false'));
  await p.click('button[data-aide] >> nth=0'); await p.waitForTimeout(350);
  const aide = await p.evaluate(() => {
    const el = document.getElementById('panneau-fin');
    if (!el) return null;
    return {
      texte: el.textContent,
      formules: [...el.querySelectorAll('.aide-formule')].map(f => f.textContent),
      expanded: document.querySelector('button[data-aide]').getAttribute('aria-expanded'),
      largeur: el.getBoundingClientRect().width,
      scrollFormule: [...el.querySelectorAll('.aide-formule')].some(f => f.scrollWidth > f.clientWidth + 1)
    };
  });
  verifier('le panneau s\'ouvre', !!aide);
  if (aide) {
    verifier('aria-expanded passe à true', aide.expanded === 'true');
    verifier('la formule générale est donnée', /rythme\s*=/.test(aide.formules[0] || '') && /fin\s*=/.test(aide.formules[0] || ''));
    verifier('un exemple chiffré reprend une ligne réelle', /Exemple/.test(aide.texte) && aide.formules.length >= 2);
    verifier('les colonnes voisines sont expliquées aussi', aide.formules.length >= 3);
    verifier('le panneau ne déborde pas en largeur', !aide.scrollFormule);
    // L'exemple doit être refaisable : on recalcule à partir de ses propres nombres.
    const ex = aide.formules[1] || '';
    const mR = ex.match(/rythme\s*=\s*\((\d+)\s*−\s*(\d+)\)\s*÷\s*(\d+)\s*sem\.\s*=\s*([\d,]+)/);
    const mF = ex.match(/fin\s*=\s*(\d+)\s*÷\s*([\d,]+)\s*=\s*(\d+)\s*semaines/);
    let calculOk = false, calculDetail = 'formule illisible';
    if (mR && mF) {
      const rythme = (Number(mR[1]) - Number(mR[2])) / Number(mR[3]);
      const affiche = Number(mR[4].replace(',', '.'));
      const semaines = Math.ceil(Number(mF[1]) / Number(mF[2].replace(',', '.')));
      calculOk = Math.abs(rythme - affiche) < 0.005 && semaines === Number(mF[3]);
      calculDetail = 'rythme ' + rythme + ' vs ' + affiche + ', semaines ' + semaines + ' vs ' + mF[3];
    }
    verifier('les chiffres de l\'exemple se recalculent exactement', calculOk, calculDetail);
  }
  await p.click('button[data-aide] >> nth=0'); await p.waitForTimeout(300);
  verifier('le panneau se referme', await p.evaluate(() => !document.getElementById('panneau-fin')));
  await p.click('button[data-aide] >> nth=0'); await p.waitForTimeout(250);
  for (let i = 0; i < 8; i++) { await p.click('button[data-aide] >> nth=0'); await p.waitForTimeout(60); }
  await p.waitForTimeout(300);
  verifier('huit bascules rapides du panneau ne cassent rien',
    await p.evaluate(() => document.querySelectorAll('.critique-ligne').length >= 5));
  verifier('ouvrir le panneau ne filtre pas le tableau',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));

  // =================================================================
  section('Sélection d\'un groupe et dimensions');
  await p.click('.critique-ligne >> nth=0'); await p.waitForTimeout(400);
  const apresGroupe = await p.evaluate(() => ({
    compte: document.getElementById('compte').textContent,
    note: document.getElementById('note-graphe').textContent,
    presse: document.querySelectorAll('.critique-ligne[aria-pressed="true"]').length
  }));
  verifier('cliquer un groupe filtre le tableau', apresGroupe.compte.indexOf(TOTAL + ' plans') === -1, apresGroupe.compte);
  verifier('le graphique suit le groupe', /Historique de/.test(apresGroupe.note), apresGroupe.note);
  verifier('une seule ligne est marquée sélectionnée', apresGroupe.presse === 1);
  await p.click('.critique-ligne >> nth=0'); await p.waitForTimeout(350);
  verifier('re-cliquer désélectionne',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));
  const dims = await p.evaluate(() => [...document.querySelectorAll('#dim-critique option')].map(o => o.value));
  for (const d of dims) {
    await p.selectOption('#dim-critique', d); await p.waitForTimeout(400);
    // Le bloc n'ouvre qu'une quinzaine de lignes : on déplie avant de compter.
    const plus = await p.$('#plus-groupes');
    if (plus) { await plus.click(); await p.waitForTimeout(400); }
    const r = await p.evaluate(() => ({
      lignes: document.querySelectorAll('.critique-ligne').length,
      titre: document.getElementById('titre-groupe').textContent,
      total: [...document.querySelectorAll('.critique-total')].reduce((s, e) => s + (+e.textContent), 0)
    }));
    verifier(`dimension « ${d} » : au moins un groupe et le compte est juste`,
      r.lignes > 0 && r.total === TOTAL, r.lignes + ' groupes, total ' + r.total);
  }
  await p.selectOption('#dim-critique', 'ata'); await p.waitForTimeout(350);

  // =================================================================
  section('Sélection vide : tout doit tenir');
  await p.fill('#recherche', 'zzzz-introuvable'); await p.waitForTimeout(400);
  const vide = await p.evaluate(() => ({
    lignes: (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length),
    critique: document.getElementById('zone-critique').textContent,
    graphe: !!document.querySelector('svg.graphe'),
    etats: [...document.querySelectorAll('.etat-n')].map(e => e.textContent.trim())
  }));
  verifier('aucune ligne dans le tableau', vide.lignes === 0, vide.lignes + ' lignes');
  verifier('le bloc par groupe explique la sélection vide', /Aucun/i.test(vide.critique),
    JSON.stringify(vide.critique.slice(0, 80)));
  verifier('le graphique survit à la sélection vide', vide.graphe);
  verifier('les compteurs d\'état tombent à zéro', vide.etats.every(v => v === '0'), JSON.stringify(vide.etats));
  await p.click('button[data-aide] >> nth=0').catch(() => {});
  await p.waitForTimeout(250);
  verifier('le bouton d\'aide absent ne provoque pas d\'erreur', true);
  await p.fill('#recherche', ''); await p.waitForTimeout(400);
  verifier('on revient à tous les plans après la sélection vide',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));

  // =================================================================
  section('Stress : clics répétés et combinaisons');
  for (let i = 0; i < 12; i++) {
    await p.click('.etat-btn[data-etat="encours"]');
    await p.click('.critique-ligne >> nth=0').catch(() => {});
  }
  await p.waitForTimeout(600);
  verifier('24 clics enchaînés laissent la page cohérente',
    await p.evaluate(() => document.querySelectorAll('.critique-ligne').length > 0 &&
      document.getElementById('compte').textContent.length > 0));
  await reinitialiser(p);
  verifier('« tout réinitialiser » remet tout d\'aplomb',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t &&
      document.querySelectorAll('.etat-btn[aria-pressed="true"]').length === 0, TOTAL));

  // =================================================================
  section('Persistance (même navigateur, page rechargée)');
  await p.click('button[data-trig="fin"]'); await p.waitForTimeout(300);
  const triAvant = await p.evaluate(() => {
    const b = document.querySelector('button[data-trig][data-actif="true"]');
    return b ? b.dataset.trig : null;
  });
  await p.waitForTimeout(700);
  await p.reload(); await p.waitForTimeout(1400);
  const apresRech = await p.evaluate(() => {
    const b = document.querySelector('button[data-trig][data-actif="true"]');
    return { tri: b ? b.dataset.trig : null, jalons: document.querySelectorAll('.jalon-supp').length };
  });
  verifier('le tri du bloc par groupe survit au rechargement',
    apresRech.tri === triAvant, triAvant + ' → ' + apresRech.tri);
  verifier('les jalons survivent au rechargement', apresRech.jalons >= 1, apresRech.jalons + ' jalon(s)');

  // =================================================================
  section('Stockage local corrompu ou indisponible');
  const ctxCorrompu = await contexte();
  let pc = await ctxCorrompu.newPage();
  brancher(pc, 'corrompu');
  await pc.goto(URL); await pc.waitForTimeout(600);
  await pc.evaluate(() => localStorage.setItem('suivi-fwd:v1', '{ceci n\'est pas du JSON'));
  await pc.reload(); await pc.waitForTimeout(1300);
  verifier('un stockage illisible ne bloque pas le démarrage',
    await pc.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));
  await pc.evaluate(() => localStorage.setItem('suivi-fwd:v1', JSON.stringify({
    jalons: [{ i: 'pas un nombre', texte: 42 }, null, { i: 99999 }],
    fen: { debut: 'x' }, tri: { cle: '__proto__' }, triGroupe: { cle: 'rm -rf', asc: 'oui' },
    ordre: ['inexistante'], cachees: { reference: true }
  })));
  await pc.reload(); await pc.waitForTimeout(1300);
  const survie = await pc.evaluate(() => ({
    lignes: (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length),
    colonnes: document.querySelectorAll('tr.titres th').length,
    refVisible: !!document.querySelector('tr.titres th[data-cle="reference"]'),
    triActif: document.querySelectorAll('button[data-trig][data-actif="true"]').length
  }));
  verifier('des préférences absurdes sont ignorées sans plantage', survie.lignes === TOTAL, survie.lignes + ' lignes');
  verifier('toutes les colonnes restent présentes', survie.colonnes >= 11, survie.colonnes + ' colonnes');
  verifier('la référence UD ne peut pas être masquée par le stockage', survie.refVisible);
  verifier('une clé de tri inconnue n\'est pas appliquée', survie.triActif === 0);
  await ctxCorrompu.close();

  const ctxBloque = await contexte();
  let pb = await ctxBloque.newPage();
  brancher(pb, 'stockage bloqué');
  await pb.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', {
      get() { throw new Error('stockage refusé'); }
    });
  });
  await pb.goto(URL); await pb.waitForTimeout(1300);
  verifier('un localStorage inaccessible ne casse pas la page',
    await pb.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));
  await pb.click('.etat-btn[data-etat="termine"]').catch(() => {});
  await pb.waitForTimeout(300);
  verifier('les filtres marchent quand même sans stockage',
    await pb.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) < t, TOTAL));
  await ctxBloque.close();

  // =================================================================
  section('Clavier et accessibilité');
  const ctxClavier = await contexte();
  let pk = await page(ctxClavier, 'clavier');
  const tab = await pk.evaluate(() => {
    const cibles = [...document.querySelectorAll('button, a[href], input, select, [tabindex]:not([tabindex="-1"])')];
    return {
      total: cibles.length,
      sansNom: cibles.filter(e => !e.textContent.trim() && !e.getAttribute('aria-label') &&
        !e.getAttribute('title') && !e.labels?.length && e.type !== 'text').length
    };
  });
  verifier('tous les éléments focusables ont un nom accessible', tab.sansNom === 0, tab.sansNom + ' sans nom');
  verifier('les états exposent aria-pressed',
    await pk.evaluate(() => [...document.querySelectorAll('.etat-btn')].every(b => b.hasAttribute('aria-pressed'))));
  verifier('les lignes de groupe exposent aria-pressed',
    await pk.evaluate(() => [...document.querySelectorAll('.critique-ligne')].every(b => b.hasAttribute('aria-pressed'))));
  await pk.focus('button[data-aide]');
  await pk.keyboard.press('Enter'); await pk.waitForTimeout(350);
  verifier('le panneau d\'aide s\'ouvre au clavier',
    await pk.evaluate(() => !!document.getElementById('panneau-fin')));
  verifier('le focus reste sur le bouton d\'aide après ouverture',
    await pk.evaluate(() => document.activeElement && document.activeElement.hasAttribute('data-aide')));
  await pk.keyboard.press('Enter'); await pk.waitForTimeout(300);
  await pk.focus('button[data-trig="total"]');
  await pk.keyboard.press('Enter'); await pk.waitForTimeout(350);
  verifier('un tri s\'active au clavier',
    await pk.evaluate(() => document.querySelectorAll('button[data-trig][data-actif="true"]').length === 1));
  verifier('le focus revient sur l\'en-tête trié',
    await pk.evaluate(() => document.activeElement && document.activeElement.dataset.trig === 'total'));
  await ctxClavier.close();

  // =================================================================
  section('Largeurs d\'écran');
  for (const largeur of [320, 400, 600, 768, 1024, 1440, 1920]) {
    const c = await contexte({ viewport: { width: largeur, height: 900 } });
    const pw = await page(c, largeur + 'px');
    const r = await pw.evaluate(() => ({
      debord: document.documentElement.scrollWidth - window.innerWidth,
      etats: document.querySelectorAll('.etat-n').length,
      graphe: !!document.querySelector('svg.graphe'),
      groupes: document.querySelectorAll('.critique-ligne').length,
      libelles: [...document.querySelectorAll('.critique-total')].every(e => e.dataset.libelle)
    }));
    verifier(`${largeur} px : pas de débordement horizontal`, r.debord <= 2, r.debord + ' px');
    verifier(`${largeur} px : les quatre états, le graphique et les groupes sont là`,
      r.etats === 4 && r.graphe && r.groupes > 0);
    if (largeur <= 720) {
      verifier(`${largeur} px : chaque valeur porte son libellé`, r.libelles);
      const lisible = await pw.evaluate(() => {
        const e = document.querySelector('.critique-total');
        return e ? getComputedStyle(e, '::before').content !== 'none' : false;
      });
      verifier(`${largeur} px : le libellé est bien rendu`, lisible);
    }
    await c.close();
  }

  // =================================================================
  section('Thème sombre');
  const ctxSombre = await contexte({ colorScheme: 'dark' });
  const ps = await page(ctxSombre, 'sombre');
  const sombre = await ps.evaluate(() => {
    function lum(c) {
      const m = c.match(/\d+/g).slice(0, 3).map(Number).map(v => {
        v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
    }
    function contraste(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
    const papier = getComputedStyle(document.body).backgroundColor;
    const fondDe = e => {
      const f = getComputedStyle(e).backgroundColor;
      return (!f || /rgba\(.*,\s*0\)$/.test(f)) ? papier : f;
    };
    const segs = [...document.querySelectorAll('.barre span')].filter(s => s.textContent.trim());
    return {
      fond: lum(getComputedStyle(document.body).backgroundColor),
      encre: lum(getComputedStyle(document.body).color),
      contrastesSegments: segs.map(s => contraste(getComputedStyle(s).color, fondDe(s))),
      contrasteTexte: contraste(getComputedStyle(document.body).color, getComputedStyle(document.body).backgroundColor)
    };
  });
  verifier('fond sombre et encre claire', sombre.fond < 0.1 && sombre.encre > 0.6);
  verifier('le texte principal dépasse 7:1', sombre.contrasteTexte >= 7, sombre.contrasteTexte.toFixed(1) + ':1');
  verifier('les pourcentages dans la barre dépassent 4,5:1',
    sombre.contrastesSegments.every(c => c >= 4.5),
    JSON.stringify(sombre.contrastesSegments.map(c => c.toFixed(1))));
  await ctxSombre.close();

  const ctxClair = await contexte({ colorScheme: 'light' });
  const pl = await page(ctxClair, 'clair');
  const clair = await pl.evaluate(() => {
    function lum(c) {
      const m = c.match(/\d+/g).slice(0, 3).map(Number).map(v => {
        v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
    }
    function contraste(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
    const papier = getComputedStyle(document.body).backgroundColor;
    const fondDe = e => {
      const f = getComputedStyle(e).backgroundColor;
      return (!f || /rgba\(.*,\s*0\)$/.test(f)) ? papier : f;
    };
    const segs = [...document.querySelectorAll('.barre span')].filter(s => s.textContent.trim());
    return segs.map(s => contraste(getComputedStyle(s).color, fondDe(s)));
  });
  verifier('en clair aussi, les pourcentages dépassent 4,5:1',
    clair.every(c => c >= 4.5), JSON.stringify(clair.map(c => c.toFixed(1))));
  await ctxClair.close();

  await ctx.close();
  await nav.close();

  // =================================================================
  console.log('\n═══════════════════════════════════════');
  console.log(reussis + ' test(s) réussi(s), ' + echecs.length + ' échec(s)');
  if (echecs.length) { console.log('\nÉchecs :'); echecs.forEach(e => console.log('  · ' + e)); }
  console.log('\nErreurs JavaScript : ' + (erreursJS.length ? '' : 'aucune'));
  [...new Set(erreursJS)].forEach(e => console.log('  ! ' + e));
  process.exit(echecs.length || erreursJS.length ? 1 : 0);
})();

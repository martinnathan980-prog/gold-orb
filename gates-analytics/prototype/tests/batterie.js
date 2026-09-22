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

/* L'interrupteur Données réelles / Exemple est visible en haut de page ;
   la batterie le manœuvre comme un clic. */
const basculerMode = (pg, mode) => pg.evaluate(m => document.querySelector('#mode-donnees button[data-mode="' + m + '"]').click(), mode);

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
  /* Le nombre de colonnes que le tableau montre : les 138 de l'export, moins
     « Colonne 1 » — sans intitulé et vide de bout en bout, la seule que la
     page retire. C'est la consigne, et tout le reste s'y réfère. */
  const COLONNES_TOTAL = 137;
  console.log('  (jeu d\'exemple : ' + TOTAL + ' plans, ' + COLONNES_TOTAL + ' colonnes attendues)');

  // =================================================================
  /* Le tableau du bas EST l'extract : toutes les colonnes, les memes
     intitules, l'ordre de la feuille. C'est la condition pour que tout le
     monde regarde la meme chose. */
  section('Le tableau ouvre sur l\'extract entier');
  const extrait = await p.evaluate(() => ({
    affichees: document.querySelectorAll('tr.titres th').length,
    ordre: [...document.querySelectorAll('tr.titres th')].map(t => t.dataset.cle),
    titres: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()),
    figees: [...document.querySelectorAll('tr.titres th.col-fige')].map(t => t.dataset.cle),
    gauches: [...document.querySelectorAll('tr.titres th.col-fige')].map(t => parseFloat(t.style.left)),
    /* Les deux colonnes sans intitulé qui restent, vides de bout en bout comme
       dans l'export réel : la structure de GATES se montre telle quelle, seule
       la première colonne — celle qu'Excel ajoute — s'efface. */
    col4: [...document.querySelectorAll('#corps-tableau tr')].every(tr =>
      tr.children[[...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'colonne_4')].textContent.trim() === '-'),
    col5: [...document.querySelectorAll('#corps-tableau tr')].every(tr =>
      tr.children[[...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'colonne_5')].textContent.trim() === '-')
  }));
  verifier('le tableau ouvre sur les 137 colonnes : l\'export entier, moins la seule vide sans intitule',
    extrait.affichees === COLONNES_TOTAL, extrait.affichees + ' / ' + COLONNES_TOTAL);
  verifier('« Colonne 1 », vide de bout en bout, n\'est pas dans les en-tetes',
    extrait.titres.indexOf('Colonne 1') === -1 && extrait.ordre.indexOf('colonne_1') === -1,
    extrait.titres.slice(0, 4).join(' | '));
  verifier('« Colonne 4 » et « Colonne 5 », sans intitule et vides elles aussi, restent a leur place : seule la premiere colonne s\'efface',
    extrait.titres[2] === 'Colonne 4' && extrait.titres[3] === 'Colonne 5' && extrait.col4 && extrait.col5,
    extrait.titres.slice(0, 5).join(' | '));
  verifier('la reference ouvre le tableau : plus rien ne la precede',
    extrait.ordre[0] === 'reference', extrait.ordre[0]);
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
    visible: !document.getElementById('mode-donnees').hidden && document.getElementById('mode-donnees').offsetParent !== null,
    bandeau: !!document.getElementById('bandeau-mode'),
    presse: [...document.querySelectorAll('#mode-donnees button')]
      .map(b => b.dataset.mode + ':' + b.getAttribute('aria-pressed')).join(' '),
    marque: document.body.dataset.exemple
  }));
  verifier('il est visible en haut de page, dans la démonstration aussi, à côté du bandeau', modeDepart.visible && modeDepart.bandeau, JSON.stringify(modeDepart));
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
  await basculerMode(p, 'exemple'); await p.waitForTimeout(900);
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
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(350);
  verifier('en exemple, filtrer un etat reduit le tableau',
    await p.evaluate(t => { const n = document.querySelectorAll('#corps-tableau tr').length; return n > 0 && n < t; }, TOTAL));
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(300);
  await basculerMode(p, 'reel'); await p.waitForTimeout(800);
  verifier('revenir au reel efface la marque ; seule, la page dit « Démonstration » à côté de l\'interrupteur',
    await p.evaluate(() => document.body.dataset.exemple === 'false' &&
      /^Démonstration — trois contrats fictifs/.test(document.getElementById('mot-mode').textContent.trim())));
  verifier('et retrouve exactement les blocs du depart',
    JSON.stringify(await blocsRemplis()) === JSON.stringify(reelBlocs));
  for (let i = 0; i < 5; i++) {
    await basculerMode(p, 'exemple'); await p.waitForTimeout(150);
    await basculerMode(p, 'reel'); await p.waitForTimeout(150);
  }
  await p.waitForTimeout(700);
  verifier('dix bascules d\'affilee laissent la page intacte',
    await p.evaluate(t => document.body.dataset.exemple === 'false' &&
      document.querySelectorAll('#corps-tableau tr').length === t, TOTAL));

  // =================================================================
  /* Plusieurs contrats, une seule page : le sélecteur vit dans le bandeau du
     haut — et nulle part ailleurs, le titre ne le répète pas — et changer de
     contrat recharge tout — comptes, historique, pied de page — en repartant
     des filtres et du cadrage par défaut. */
  section('Sélecteur de contrat');
  const sel0 = await p.evaluate(() => ({
    visible: !document.getElementById('choix-contrat').hidden &&
             document.getElementById('select-contrat').offsetParent !== null,
    haut: document.getElementById('choix-contrat').getBoundingClientRect().top <
          document.querySelector('.masthead').getBoundingClientRect().top,
    options: [...document.querySelectorAll('#select-contrat option')].map(o => o.value).join(','),
    courant: document.getElementById('select-contrat').value,
    masthead: document.querySelector('.masthead').textContent,
    titre: document.title,
    zones: document.querySelectorAll('.zone-clic').length
  }));
  verifier('le selecteur est la, en haut, et liste les trois contrats',
    sel0.visible && sel0.haut && sel0.options === 'HDK,THS,VRK', JSON.stringify(sel0));
  verifier('il demarre sur HDK, sans le répéter sous le titre',
    sel0.courant === 'HDK' && !/contrat/i.test(sel0.masthead), JSON.stringify(sel0));
  verifier('le titre de la page reste « Suivi FWD »', sel0.titre === 'Suivi FWD', sel0.titre);
  const pied0 = await p.evaluate(() => document.getElementById('import').textContent);
  const etats0 = await p.evaluate(() => [...document.querySelectorAll('#etats .etat-n')].map(e => e.textContent).join(' '));
  // Un filtre et un cadrage posés avant de changer : ils doivent repartir de zéro.
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(300);
  await p.click('.segmente button[data-span="52"]'); await p.waitForTimeout(300);
  const lireContrat = () => p.evaluate(() => ({
    plans: document.querySelectorAll('#corps-tableau tr').length,
    pied: document.getElementById('import').textContent,
    nom: document.getElementById('select-contrat').value,
    masthead: document.querySelector('.masthead').textContent,
    courant: document.getElementById('select-contrat').value,
    filtres: document.getElementById('filtres-actifs').hidden,
    presse: document.querySelectorAll('#etats .etat-btn[aria-pressed="true"]').length,
    zones: document.querySelectorAll('.zone-clic').length,
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => e.textContent).join(' '),
    groupes: [...document.querySelectorAll('.critique-total')].reduce((s, e) => s + (+e.textContent), 0),
    journal: document.querySelectorAll('.journal-ligne').length,
    mode: document.body.dataset.exemple,
    /* Le cadrage par défaut se reconnaît à ce qu'il montre : le repère du
       dernier relevé et tous les jalons du contrat — pas à un nombre de
       bandes, qui dépend de la source. */
    jalons: document.querySelectorAll('svg.graphe .jalon').length,
    aujourdhui: document.querySelectorAll('svg.graphe .repere-auj').length === 1
  }));
  await p.selectOption('#select-contrat', 'THS'); await p.waitForTimeout(1200);
  const x2 = await lireContrat();
  verifier('changer de contrat change le nombre de plans', x2.plans > 0 && x2.plans !== TOTAL, String(x2.plans));
  verifier('et le pied de page', x2.pied !== pied0, x2.pied);
  verifier('le contrat courant est celui du sélecteur, et le titre ne le répète pas',
    x2.nom === 'THS' && x2.courant === 'THS' && !/contrat/i.test(x2.masthead), x2.nom);
  verifier('les filtres et le cadrage repartent de zero',
    x2.filtres && x2.presse === 0 && x2.jalons === 5 && x2.aujourdhui, JSON.stringify(x2));
  verifier('le bloc par groupe et le journal suivent le nouveau contrat',
    x2.groupes === x2.plans && x2.journal > 0, x2.groupes + ' / ' + x2.plans);
  await p.selectOption('#select-contrat', 'VRK'); await p.waitForTimeout(1200);
  const x3 = await lireContrat();
  verifier('un troisieme contrat a encore d\'autres comptes',
    x3.plans > 0 && x3.plans !== x2.plans && x3.plans !== TOTAL && x3.nom === 'VRK', String(x3.plans));
  // L'exemple d'un autre contrat, puis un changement de contrat : on RESTE en
  // exemple, sur le nouveau contrat — rebasculer sans un mot sur le réel
  // trompait la lectrice.
  await basculerMode(p, 'exemple'); await p.waitForTimeout(800);
  await p.selectOption('#select-contrat', 'HDK'); await p.waitForTimeout(1200);
  const x1ex = await lireContrat();
  verifier('un changement de contrat en exemple reste en exemple, sur le nouveau contrat',
    x1ex.mode === 'true' && x1ex.nom === 'HDK', JSON.stringify({ mode: x1ex.mode, nom: x1ex.nom }));
  await basculerMode(p, 'reel'); await p.waitForTimeout(900);
  const x1 = await lireContrat();
  verifier('revenir a HDK, en donnees reelles, redonne les comptes initiaux',
    x1.plans === TOTAL && x1.etats === etats0 && x1.pied === pied0 && x1.mode === 'false', JSON.stringify(x1));
  // Sans liste de contrats — ou avec un seul — rien à choisir : le sélecteur disparaît.
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); delete s.contrats; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  const seul = await p.evaluate(() => ({
    cache: document.getElementById('choix-contrat').hidden &&
           document.getElementById('select-contrat').offsetParent === null,
    plans: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('sans liste de contrats, le selecteur disparait',
    seul.cache && seul.plans === TOTAL, JSON.stringify(seul));
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); s.contrats = [{ id: 'HDK', nom: 'HDK' }]; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  verifier('avec un seul contrat liste, pareil',
    await p.evaluate(() => document.getElementById('choix-contrat').hidden));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(900);
  verifier('la liste revenue, le selecteur revient',
    await p.evaluate(() => !document.getElementById('choix-contrat').hidden &&
      [...document.querySelectorAll('#select-contrat option')].map(o => o.value).join(',') === 'HDK,THS,VRK' &&
      document.getElementById('select-contrat').value === 'HDK'));

  // =================================================================
  /* Le rapprochement avec une seconde base : la démonstration joue SEE, un
     extract dont la référence se lit sur trois colonnes (NAME, SOL., Cust.V).
     Un plan dans SEE est un plan créé, donc terminé : la section croise cette
     présence avec l'avancement d'ici. Les écarts sont délibérés — 3 terminés
     que SEE ne connaît pas, 2 terminés sous un autre indice, 12 plans que SEE
     connaît sans que GATES les dise terminés, 5 références seulement dans
     SEE. La section vit sous le tableau des plans : une phrase, deux cercles
     face à face avec l'anneau des plans en commun, et six verdicts en
     français qui filtrent le tableau ; « terminés, absents de SEE » et « pas
     encore dans SEE » emmènent sur GATES, « seulement dans SEE » sur SEE.
     Elle suit le périmètre et le contrat, et disparaît sans seconde base. */
  section('Rapprochement avec une seconde base');
  const COLONNES_SEE = ['NAME', 'SOL.', 'Cust.V', 'Int. V', 'ARCHIVE FILE PREFIX', 'VALIDITY PSN FULL',
    'User Status', 'DIAGRAM TYPE', 'PRODUCT FAMILY', 'Validated', 'FG1 TAGDESCRIPTION', 'FG2 TAGDESCRIPTION',
    'SCHEMA NUMBER', 'Released Date', 'Obsolete Date', 'Validated Date', 'REDRAW', 'ARCHIVED', 'CGM', 'XPEMPTY'];
  const TERMINES = await p.evaluate(() => +document.querySelector('#etats .etat-n').textContent.replace(/\s/g, ''));
  const MANQUE = 3, EMISSION = 2, AVANCE = 12, SEUL = 5;
  const ACCORD = TERMINES - MANQUE - EMISSION, CONNUS = ACCORD + EMISSION, ATTENTE = TOTAL - TERMINES - AVANCE;
  const COMMUN = CONNUS + AVANCE, LIGNES_SEE = COMMUN + SEUL, PCT = Math.round(100 * ACCORD / TERMINES);
  const fr = n => n.toLocaleString('fr-FR');
  const lireRapp = () => p.evaluate(() => {
    const R = window.__rapprochement();
    const top = el => Math.round(document.getElementById(el).getBoundingClientRect().top + window.scrollY);
    return {
      cache: document.getElementById('rapprochement').hidden,
      titre: document.getElementById('titre-rapprochement').textContent,
      phrase: !!document.getElementById('phrase-rapprochement'),
      sous: !!document.getElementById('sous-rapprochement'),
      compte: !!document.getElementById('compte-rapprochement'),
      figure: (() => {
        const svg = document.querySelector('#venn-rapprochement svg');
        if (!svg) return null;
        const RAYON = 40;
        return {
          cercles: [...svg.querySelectorAll('circle.cercle-ici, circle.cercle-la')].map(c => c.getAttribute('class')).join(),
          bases: [...svg.querySelectorAll('.base-nom')].map(t => t.textContent).join(),
          comptes: [...svg.querySelectorAll('.base-compte')].map(t => t.textContent).join(' | '),
          parts: [...svg.querySelectorAll('.donut-seg')].map(x => ({
            cle: x.getAttribute('data-cle'), n: +x.getAttribute('data-n'),
            cat: x.getAttribute('class').replace('donut-seg', '').replace('survole', '').trim(),
            degres: x.tagName === 'circle' ? 360 : Math.round(x.getTotalLength() / (2 * Math.PI * RAYON) * 360) })),
          cotes: [...svg.querySelectorAll('.cote')].map(g => ({
            cle: g.getAttribute('data-cle'), n: +(g.querySelector('.grand') || g.querySelector('.moyen')).textContent.replace(/\s/g, ''),
            mots: [...g.querySelectorAll('.petit')].map(t => t.textContent.replace(/^[\d\s ]+/, '')).join(' · '),
            zero: g.classList.contains('zero') })),
          commun: +svg.querySelector('.commun-n').textContent.replace(/\s/g, ''), motCommun: svg.querySelector('.commun-mot').textContent,
          aria: document.getElementById('venn-rapprochement').getAttribute('aria-label')
        };
      })(),
      puces: [...document.querySelectorAll('#verdicts-rapprochement button[data-rapp]')].map(b => ({
        cle: b.dataset.rapp, n: +b.querySelector('.verdict-n').textContent.replace(/\s/g, ''),
        atterrit: b.dataset.atterrit,
        phrase: b.querySelector('.verdict-mot').textContent.replace(/\s+/g, ' ').trim(),
        gras: !b.querySelector('.verdict-mot b'),
        pastille: (b.querySelector('.pastille') || { className: '' }).className.replace('pastille', '').trim(),
        presse: b.getAttribute('aria-pressed'), inactif: b.disabled
      })),
      videIci: (document.querySelector('#corps-tableau .vide-message') || { textContent: '' }).textContent.replace(/\s+/g, ' ').trim(),
      ordre: top('cadre-tableau') < top('rapprochement') &&
             top('rapprochement') < Math.round(document.querySelector('.pied').getBoundingClientRect().top + window.scrollY),
      lignes: document.querySelectorAll('#corps-tableau tr').length,
      refsTableau: [...document.querySelectorAll('#corps-tableau tr td.ref')].map(td => td.textContent.trim()),
      jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()),
      seconde: document.querySelectorAll('#corps-seconde tr[data-i]').length,
      secondeCache: document.getElementById('choix-base').hidden,
      secondeVide: (document.querySelector('#corps-seconde .vide-message') || { textContent: '' }).textContent.replace(/\s+/g, ' ').trim(),
      secondeRefs: [...document.querySelectorAll('#corps-seconde tr[data-i] .verdict .ref')].map(e => e.textContent),
      R: R && {
        accord: R.accord.length, emission: R.emission.length, avance: R.avance.length, manque: R.manque.length,
        attente: R.attente.length, seul: R.seul.length, total: R.total, nbPlans: R.nbPlans, nbLignes: R.nbLignes, nbTermines: R.nbTermines,
        refsAccord: R.accord.map(x => x.reference), refsAvance: R.avance.map(x => x.reference), refsManque: R.manque.map(x => x.reference),
        etatsAvance: R.avance.map(x => x._etat), etatsManque: R.manque.map(x => x._etat), etatsAttente: R.attente.map(x => x._etat), etatsAccord: R.accord.map(x => x._etat),
        paires: R.emission.map(x => ({ ici: x.plan.reference, la: x.ref_la, etat: x.plan._etat,
          racineIci: window.__analyserUD(x.plan.reference).racine, racineLa: window.__analyserUD(x.ref_la).racine }))
      }
    };
  });
  const r0 = await lireRapp();
  verifier('la section est là, nommée d\'après la seconde base',
    !r0.cache && r0.titre === 'Comparaison des bases de données', r0.titre);
  /* La figure s'anime quand elle paraît à l'écran — pas avant —, même si un
     filtre l'a redessinée entre-temps ; une fois par source. */
  const animAvant = await p.evaluate(() => document.querySelector('#venn-rapprochement svg').classList.contains('anime'));
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(400);
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(400);
  await p.evaluate(() => document.getElementById('venn-rapprochement').scrollIntoView({ block: 'center' })); await p.waitForTimeout(700);
  const animApres = await p.evaluate(() => {
    const svg = document.querySelector('#venn-rapprochement svg');
    return { anime: svg.classList.contains('anime'), texteVisible: parseFloat(getComputedStyle(svg.querySelector('.commun-n')).opacity) };
  });
  await p.waitForTimeout(1200);
  const animFin = await p.evaluate(() => parseFloat(getComputedStyle(document.querySelector('#venn-rapprochement .commun-n')).opacity));
  verifier('la figure ne s\'anime qu\'en paraissant à l\'écran, même redessinée par un filtre avant ; ses textes finissent pleinement visibles',
    !animAvant && animApres.anime && animFin === 1, JSON.stringify([animAvant, animApres, animFin]));
  await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(200);

  /* Sous les cercles, plan par plan : les lots dans l'ordre des priorités —
     à vérifier d'abord, dépliés ; ce qui va ensuite, replié. Un clic sur une
     référence réduit le tableau d'ici à ce plan ; une ligne seulement là
     ouvre le tableau de SEE sur elle. */
  const lireListe = () => p.evaluate(() => ({
    titre: (document.querySelector('#liste-rapprochement .rapp-liste-titre') || {}).textContent,
    groupes: [...document.querySelectorAll('#liste-rapprochement .rapp-groupe')].map(g => ({
      cle: g.dataset.cle, ouvert: g.dataset.ouvert,
      n: +g.querySelector('.rapp-groupe-tete b').textContent.replace(/\s/g, ''),
      expanded: g.querySelector('.rapp-groupe-tete').getAttribute('aria-expanded'),
      lignes: g.querySelectorAll('.rapp-puce').length
    }))
  }));
  /* La colonne NAME de SEE porte l'écriture de SEE — le A un cran trop tôt.
     Pour la comparer aux références de GATES, on décale le A d'un cran. */
  const deSEE = n => /^[A-Z]{3}\d{3}A\d{4}$/.test(n) ? n.slice(0, 6) + n.charAt(7) + 'A' + n.slice(8) : n;
  const li0 = await lireListe();
  verifier('sous les cercles, « Plan par plan » range les lots dans l\'ordre des priorités, avec les comptes des verdicts',
    li0.titre === 'Plan par plan' && li0.groupes.map(g => g.cle).join() === 'manque,avance,emission,seul,attente,accord' &&
    li0.groupes.map(g => g.n).join() === [MANQUE, AVANCE, EMISSION, SEUL, ATTENTE, ACCORD].join(), JSON.stringify(li0));
  verifier('les lots à vérifier sont dépliés, une puce par plan ; « pas encore » et « d\'accord » sont repliés',
    li0.groupes.slice(0, 4).every(g => g.ouvert === 'true' && g.expanded === 'true' && g.lignes === g.n) &&
    li0.groupes.slice(4).every(g => g.ouvert === 'false' && g.expanded === 'false' && g.lignes === 0), JSON.stringify(li0));
  const rangees = await p.evaluate(() => {
    const lire = cle => [...document.querySelectorAll('#liste-rapprochement .rapp-groupe[data-cle="' + cle + '"] .rapp-puce')]
      .map(b => ({ ref: b.querySelector('.rapp-puce-ref').textContent, etat: b.dataset.etat, la: b.dataset.ligneLa, see: b.dataset.see,
        vers: (b.querySelector('.rapp-puce-vers') || { textContent: '' }).textContent,
        pastille: b.querySelector('.pastille') ? b.querySelector('.pastille').className.replace('pastille', '').trim() : null,
        couleur: b.querySelector('.pastille') ? (b.querySelector('.pastille').getAttribute('style') || '') : null, bulle: b.title }));
    return { manque: lire('manque'), avance: lire('avance'), emission: lire('emission'), seul: lire('seul') };
  });
  verifier('« terminés, absents de SEE » : une puce par plan — pastille verte, référence, et la bulle dit Terminé dans GATES, absent dans SEE, où mène le clic',
    rangees.manque.length === MANQUE && rangees.manque.every(r => /^[A-Z]{2}E\d{4}A\d{6}[A-Z]$/.test(r.ref) && r.etat === 'termine' && r.see === 'absent' &&
      r.pastille === '' && /--fait/.test(r.couleur) && r.vers === '' && r.bulle === 'Terminé dans GATES · absent dans SEE — ne montrer que ce plan dans le tableau'),
    JSON.stringify(rangees.manque));
  verifier('« dans SEE, pas terminés ici » : jamais terminé côté GATES, présent côté SEE ; « autre indice » porte la lettre en violet ; « seulement dans SEE » n\'a ni plan ni pastille et mène au tableau de SEE',
    rangees.avance.every(r => r.etat !== 'termine' && r.see === 'présent' && r.vers === '') &&
    rangees.emission.every(r => r.etat === 'termine' && /--fait/.test(r.couleur) && /^sous l’indice [A-Z] \([A-Z]{2}E\d{4}A\d{6}[A-Z]\)$/.test(r.see) && /^→ [A-Z]$/.test(r.vers)) &&
    rangees.seul.length === SEUL && rangees.seul.every(r => r.etat === undefined && r.la && r.see === 'présent' && r.pastille === null &&
      /^aucun plan dans GATES · présent dans SEE — voir cette ligne dans le tableau de SEE$/.test(r.bulle)),
    JSON.stringify([rangees.avance[0], rangees.emission[0], rangees.seul[0]]));
  const legendePuces = await p.evaluate(() => [...document.querySelectorAll('#liste-rapprochement .rapp-puces-legende > span')].map(s => s.textContent.trim()).join(','));
  verifier('en tête du plan par plan, la légende des pastilles d\'état', legendePuces === 'Terminé,En cours,À faire,Non renseigné', legendePuces);
  const deuxEcritures = await p.evaluate(() => {
    const a = window.__analyserUD('GBE3123A600002B'), b = window.__analyserUD('GBE312A3600002B');
    const c = window.__analyserUD('ZZE991A0800001A');
    return { a, b, c, seeDepuisGates: window.__racineSEE('GBE3123A600') };
  });
  verifier('une référence écrite à la mode de SEE — le A un cran trop tôt — se lit comme celle de GATES : même racine, même solution, même indice',
    deuxEcritures.a.valide && deuxEcritures.b.valide &&
    deuxEcritures.a.racine === deuxEcritures.b.racine && deuxEcritures.a.solution === deuxEcritures.b.solution &&
    deuxEcritures.a.indice === deuxEcritures.b.indice && deuxEcritures.c.racine === 'ZZE9910A800' &&
    deuxEcritures.seeDepuisGates === 'GBE312A3600', JSON.stringify(deuxEcritures));
  verifier('les références d\'un lot sont triées', rangees.avance.map(r => r.ref).join() === rangees.avance.map(r => r.ref).sort((a, b) => a.localeCompare(b, 'fr', { numeric: true, sensitivity: 'base' })).join());
  await p.click('#liste-rapprochement .rapp-groupe[data-cle="accord"] button[data-plier]'); await p.waitForTimeout(300);
  const li1 = await lireListe();
  verifier('déplier « terminés et dans SEE » montre TOUS ses plans — ' + ACCORD + ' puces, aucune coupure, aucun renvoi au tableau ; les autres ne bougent pas',
    li1.groupes[5].ouvert === 'true' && li1.groupes[5].lignes === ACCORD && li1.groupes[0].ouvert === 'true' && li1.groupes[4].ouvert === 'false' &&
    await p.evaluate(() => !document.querySelector('#liste-rapprochement .rapp-groupe-suite, #liste-rapprochement [data-rapp-tout]')),
    JSON.stringify(li1.groupes));
  const defile = await p.evaluate(() => {
    const corps = document.querySelector('#liste-rapprochement .rapp-groupe[data-cle="accord"] .rapp-groupe-corps');
    const page = document.documentElement;
    return { defile: corps.scrollHeight > corps.clientHeight + 1, reglage: getComputedStyle(corps).overflowY,
             retenue: getComputedStyle(corps).overscrollBehaviorY, hauteur: corps.getBoundingClientRect().height,
             plafond: window.innerHeight * 0.46, page: page.scrollWidth <= page.clientWidth + 1 };
  });
  verifier('le lot le plus gros défile dans sa zone — plafonnée à 46 % de la hauteur de fenêtre, retenue comprise — au lieu de pousser la page',
    defile.reglage === 'auto' && defile.defile && defile.retenue === 'contain' &&
    Math.abs(defile.hauteur - defile.plafond) <= 2 && defile.page, JSON.stringify(defile));
  await p.click('#liste-rapprochement .rapp-groupe[data-cle="accord"] button[data-plier]'); await p.waitForTimeout(300);
  verifier('replier le referme', (await lireListe()).groupes[5].ouvert === 'false');
  await p.click('#liste-rapprochement .rapp-groupe[data-cle="manque"] button[data-plan-rapp]'); await p.waitForTimeout(500);
  const clicPlan = await p.evaluate(() => ({
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    ref: (document.querySelector('#corps-tableau td.ref, #corps-tableau .ref') || {}).textContent,
    jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').replace(/\s+/g, ' ').trim()),
    base: document.querySelector('#choix-base button[aria-pressed="true"]').dataset.base,
    liste: document.querySelectorAll('#liste-rapprochement .rapp-groupe').length
  }));
  verifier('un clic sur une référence réduit le tableau GATES à ce plan, le bandeau le dit, et la liste reste entière',
    clicPlan.lignes === 1 && clicPlan.ref === rangees.manque[0].ref && clicPlan.base === 'ici' &&
    clicPlan.jetons.some(j => /Sélection : plan /.test(j)) && clicPlan.liste === 6, JSON.stringify(clicPlan));
  await p.click('.jeton .x'); await p.waitForTimeout(400);
  /* Un lot posé sur les plans d'ici cacherait toute ligne seulement là :
     le clic le retire. Le tableau de SEE se montre, cherché sur la ligne, le
     bandeau porte le jeton de cette recherche, et le focus se pose sur le
     bouton de base — qui survit au rendu. */
  await p.click('#verdicts-rapprochement button[data-rapp="accord"]'); await p.waitForTimeout(400);
  await p.evaluate(() => { window.__valeurLa = document.querySelector('#liste-rapprochement .rapp-groupe[data-cle="seul"] button[data-ligne-la]').dataset.ligneLa; });
  await p.click('#liste-rapprochement .rapp-groupe[data-cle="seul"] button[data-ligne-la]'); await p.waitForTimeout(600);
  const clicLa = await p.evaluate(() => ({
    base: document.querySelector('#choix-base button[aria-pressed="true"]').dataset.base,
    lignes: document.querySelectorAll('#corps-seconde tr[data-i]').length,
    recherche: document.getElementById('recherche-seconde').value,
    jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').replace(/\s+/g, ' ').trim()),
    presses: document.querySelectorAll('#verdicts-rapprochement button[aria-pressed="true"]').length,
    cherche: window.__valeurLa,
    lignesAvecLaValeur: [...document.querySelectorAll('#corps-seconde tr[data-i]')].filter(tr => tr.textContent.indexOf(window.__valeurLa) !== -1).length,
    haut: Math.round(document.getElementById('cadre-seconde').getBoundingClientRect().top),
    focus: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.base : null
  }));
  verifier('un clic sur une référence seulement dans SEE retire le lot posé, ouvre le tableau de SEE cherché sur elle, et le bandeau le dit',
    clicLa.base === 'la' && clicLa.lignes >= 1 && clicLa.lignes <= 2 && clicLa.recherche === clicLa.cherche && clicLa.cherche.length > 0 &&
    clicLa.lignesAvecLaValeur === clicLa.lignes && clicLa.presses === 0 &&
    clicLa.jetons.some(j => j === 'Recherche dans SEE : ' + clicLa.cherche) && !clicLa.jetons.some(j => /^Comparaison : /.test(j)), JSON.stringify(clicLa));
  verifier('la page est descendue sur le tableau de SEE, et le focus est sur son bouton de base',
    clicLa.haut >= -2 && clicLa.focus === 'la', JSON.stringify([clicLa.haut, clicLa.focus]));
  await p.click('.jeton .x'); await p.waitForTimeout(400);
  const apresCroix = await p.evaluate(() => ({
    recherche: document.getElementById('recherche-seconde').value,
    lignes: document.querySelectorAll('#corps-seconde tr[data-i]').length,
    jetons: document.querySelectorAll('.jeton').length
  }));
  verifier('la croix du jeton vide la recherche de SEE et rend son tableau entier',
    apresCroix.recherche === '' && apresCroix.lignes === LIGNES_SEE && apresCroix.jetons === 0, JSON.stringify(apresCroix));
  await p.click('#choix-base button[data-base="ici"]'); await p.waitForTimeout(400);
  verifier('de retour sur GATES, le tableau est entier', await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === TOTAL);
  /* Sous un filtre du haut, « ne montrer que ce plan » tient sa promesse :
     les filtres libres s'effacent, le plan est là, le périmètre reste. */
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(600);
  /* Le premier plan d'un lot déplié sous ce périmètre — quel qu'il soit —,
     et un filtre d'état qui l'exclut. */
  const cible = await p.evaluate(() => {
    const b = document.querySelector('#liste-rapprochement .rapp-groupe[data-ouvert="true"] button[data-plan-rapp]');
    if (!b) return null;
    return { ref: b.querySelector('.rapp-puce-ref').textContent, groupe: b.closest('.rapp-groupe').dataset.cle, etat: b.dataset.etat };
  });
  verifier('sous PERSO, un lot déplié a encore des plans à cliquer', !!cible, JSON.stringify(cible));
  const suitPerimetre = await p.evaluate(() => {
    const groupes = [...document.querySelectorAll('#liste-rapprochement .rapp-groupe')].map(g => ({
      cle: g.dataset.cle, n: +g.querySelector('.rapp-groupe-tete b').textContent.replace(/\s/g, ''),
      mot: g.querySelector('.rapp-groupe-phrase').textContent,
      gras: !g.querySelector('.rapp-groupe-mot')
    }));
    const puces = [...document.querySelectorAll('#verdicts-rapprochement button[data-rapp]')].map(b => ({
      cle: b.dataset.rapp, n: +b.querySelector('.verdict-n').textContent.replace(/\s/g, '')
    }));
    return { groupes, puces };
  });
  verifier('sous PERSO, la liste suit le périmètre : mêmes comptes que les verdicts, aucun groupe à zéro, « seulement dans SEE · tout le contrat »',
    suitPerimetre.groupes.every(g => g.n > 0 && suitPerimetre.puces.some(pu => pu.cle === g.cle && pu.n === g.n)) &&
    suitPerimetre.puces.filter(pu => pu.n > 0).length === suitPerimetre.groupes.length &&
    suitPerimetre.groupes.some(g => g.cle === 'seul' && g.mot === 'lignes de SEE sans plan dans GATES — tout le contrat') &&
    suitPerimetre.groupes.every(g => g.gras), JSON.stringify(suitPerimetre));
  const titres = await p.evaluate(() => {
    const j = document.querySelector('.titre-journal'), r = document.getElementById('titre-rapprochement');
    const cj = getComputedStyle(j), cr = getComputedStyle(r);
    return { tag: j.tagName, memePolice: cj.fontFamily === cr.fontFamily, memeTaille: cj.fontSize === cr.fontSize, taille: cj.fontSize };
  });
  verifier('le titre du journal est un h2, de la même police et de la même taille que les autres sections',
    titres.tag === 'H2' && titres.memePolice && titres.memeTaille, JSON.stringify(titres));
  const etatQuiExclut = cible && cible.etat === 'termine' ? 'encours' : 'termine';
  await p.click('#etats .etat-btn[data-etat="' + etatQuiExclut + '"]'); await p.waitForTimeout(400);
  await p.click('#liste-rapprochement .rapp-groupe[data-cle="' + (cible ? cible.groupe : 'manque') + '"] button[data-plan-rapp]'); await p.waitForTimeout(600);
  const sousFiltre = await p.evaluate(() => ({
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    ref: (document.querySelector('#corps-tableau td.ref, #corps-tableau .ref') || {}).textContent,
    jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').replace(/\s+/g, ' ').trim()),
    focus: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.base : null
  }));
  verifier('sous un filtre d\'état qui l\'exclut et le périmètre PERSO, le clic sur un plan de la liste l\'affiche seul : l\'état s\'efface, le périmètre reste',
    !!cible && sousFiltre.lignes === 1 && sousFiltre.ref === cible.ref && sousFiltre.focus === 'ici' &&
    sousFiltre.jetons.some(j => /^Périmètre : PERSO$/.test(j)) && !sousFiltre.jetons.some(j => /^État/.test(j)) &&
    sousFiltre.jetons.some(j => /^Sélection : plan /.test(j)), JSON.stringify([cible, sousFiltre]));
  await p.evaluate(() => { const b = document.getElementById('tout-effacer'); if (b) b.click(); });
  await p.waitForTimeout(500);
  verifier('sous le tableau des plans, avant le pied', r0.ordre);
  verifier('la tête de la section ne porte que le titre : ni phrase, ni sous-phrase, ni compte — les verdicts disent tout',
    !r0.phrase && !r0.sous && !r0.compte, JSON.stringify([r0.phrase, r0.sous, r0.compte]));
  verifier('six verdicts, dans l\'ordre de lecture, avec les nombres attendus : ' + [ACCORD, 2, 12, 3, ATTENTE, 5].join(' / '),
    r0.puces.map(x => x.cle + '=' + x.n).join(' ') === 'accord=' + ACCORD + ' emission=2 avance=12 manque=3 attente=' + ATTENTE + ' seul=5',
    JSON.stringify(r0.puces.map(x => x.cle + '=' + x.n)));
  verifier('aucun mot court en gras devant : le nombre, puis la phrase, rien d\'autre',
    r0.puces.every(x => x.gras), JSON.stringify(r0.puces.map(x => x.gras)));
  verifier('chaque verdict porte sa pastille : vert, violet (autre indice), ambre, rouge, gris, anneau',
    r0.puces.map(x => x.pastille).join() === 'accord,indice,avance,manque,attente,seul', r0.puces.map(x => x.pastille).join());
  verifier('et dit d\'avance où ses lignes existent : ce qui n\'est pas dans SEE emmène sur GATES, « seulement dans SEE » sur SEE',
    r0.puces.map(x => x.atterrit).join() === ',,,ici,ici,la', r0.puces.map(x => x.atterrit).join());
  verifier('chaque verdict se lit en une phrase de tous les jours, qui se suffit à elle-même',
    r0.puces.map(x => x.phrase).join(' | ') === 'terminés dans GATES et connus de SEE | dans SEE sous une autre lettre d’indice | dans SEE, mais GATES ne les dit pas terminés | terminés dans GATES, mais SEE ne les connaît pas | pas terminés, et pas encore dans SEE : rien d’anormal | lignes de SEE sans plan dans GATES',
    r0.puces.map(x => x.phrase).join(' | '));
  const F = r0.figure;
  verifier('deux cercles face à face, GATES plein à gauche avec ses terminés, SEE en pointillé à droite avec ses lignes',
    F && F.cercles === 'cercle-ici,cercle-la' && F.bases === 'GATES,SEE' &&
    F.comptes === fr(TOTAL) + ' plans · ' + fr(TERMINES) + ' terminés | ' + fr(LIGNES_SEE) + ' lignes', JSON.stringify(F && [F.cercles, F.bases, F.comptes]));
  verifier('dans le recouvrement, l\'anneau des plans en commun : ' + COMMUN + ', en trois parts vert / violet / ambre, dans l\'ordre des verdicts',
    F && F.commun === COMMUN && F.motCommun === 'en commun' &&
    F.parts.map(x => x.cle + '=' + x.n + ':' + x.cat).join(' ') === 'accord=' + ACCORD + ':accord emission=2:emission avance=12:avance',
    JSON.stringify(F && F.parts));
  const degres = F ? F.parts.reduce((t, x) => t + x.degres, 0) : 0;
  verifier('les parts sont à l\'échelle — le vert domine, ' + PCT + ' % des terminés — mais la plus petite reste visible',
    F && F.parts[0].degres >= 300 && F.parts.every(x => x.degres >= 4) && degres >= 340 && degres <= 360, JSON.stringify(F && F.parts.map(x => x.degres)));
  verifier('à gauche, le nombre qui compte — 3 terminés sans SEE, en alerte — et dessous, discret, ' + ATTENTE + ' pas encore dans SEE ; à droite, 5 seulement dans SEE',
    F && F.cotes.map(c => c.cle + '=' + c.n + ' ' + c.mots + (c.zero ? ' (zéro)' : '')).join(' | ') === 'manque=3 terminés sans SEE | attente=' + ATTENTE + ' pas encore dans SEE | seul=5 seulement dans SEE',
    JSON.stringify(F && F.cotes));
  verifier('la figure se lit aussi à voix haute',
    F && F.aria === 'Comparaison GATES / SEE : ' + ACCORD + ' terminés et dans SEE, 2 sous un autre indice, 12 dans SEE sans être terminés ici, 3 terminés absents de SEE, ' + ATTENTE + ' pas encore dans SEE, sur ' + TOTAL + ' plans ; 5 lignes seulement dans SEE.', F && F.aria);
  const rectsRapp = await p.evaluate(() => {
    const fig = document.getElementById('venn-rapprochement').getBoundingClientRect();
    const zone = document.getElementById('verdicts-rapprochement').getBoundingClientRect();
    const r = [...document.querySelectorAll('#verdicts-rapprochement button')].map(b => b.getBoundingClientRect());
    return { aDroite: zone.left >= fig.right, chevauche: r.some((a, i) => i > 0 && a.top < r[i - 1].bottom - 1), dedans: r.every(b => b.left >= zone.left - 1 && b.right <= zone.right + 1), n: r.length };
  });
  verifier('les verdicts sont une liste à droite de la figure, une ligne chacun, sans se chevaucher ni sortir du cadre',
    rectsRapp.n === 6 && rectsRapp.aDroite && !rectsRapp.chevauche && rectsRapp.dedans, JSON.stringify(rectsRapp));
  verifier('aucun n\'est pressé ni inactif au départ, les deux tableaux sont entiers',
    r0.puces.every(x => x.presse === 'false' && !x.inactif) && r0.lignes === TOTAL && r0.seconde === LIGNES_SEE && r0.jetons.length === 0,
    JSON.stringify([r0.lignes, r0.seconde, r0.jetons]));
  verifier('le moteur donne les mêmes comptes : 22 choses à vérifier, ' + TERMINES + ' terminés, un lot par plan',
    r0.R && r0.R.total === 22 && r0.R.nbPlans === TOTAL && r0.R.nbLignes === LIGNES_SEE && r0.R.nbTermines === TERMINES &&
    r0.R.accord + r0.R.emission + r0.R.avance + r0.R.manque + r0.R.attente === TOTAL,
    JSON.stringify(r0.R && [r0.R.total, r0.R.nbPlans, r0.R.nbLignes, r0.R.nbTermines]));
  verifier('les verdicts croisent bien l\'état d\'ici : d\'accord et absents-de-SEE sont terminés, les autres ne le sont pas',
    r0.R.etatsAccord.every(e => e === 'termine') && r0.R.etatsManque.every(e => e === 'termine') &&
    r0.R.etatsAvance.every(e => e !== 'termine') && r0.R.etatsAttente.every(e => e !== 'termine') && r0.R.paires.every(x => x.etat === 'termine'),
    JSON.stringify([r0.R.etatsAvance, r0.R.etatsManque]));
  verifier('un indice différent, c\'est le même plan — même racine, même solution — sous une autre lettre',
    r0.R.paires.length === 2 && r0.R.paires.every(x => x.racineIci === x.racineLa && x.ici !== x.la &&
      x.ici.slice(-1) !== x.la.slice(-1) && x.ici.slice(0, -1) === x.la.slice(0, -1)),
    JSON.stringify(r0.R.paires));

  // « dans SEE, pas terminés ici » : les deux tableaux se réduisent aux douze plans concernés.
  await p.click('#verdicts-rapprochement button[data-rapp="avance"]'); await p.waitForTimeout(500);
  const rAv = await lireRapp();
  verifier('cliquer « dans SEE, pas terminés ici » réduit le tableau d\'ici à 12 plans, et celui de SEE à leurs 12 lignes',
    rAv.lignes === 12 && rAv.seconde === 12, rAv.lignes + ' / ' + rAv.seconde);
  verifier('ce sont bien ces plans, des deux côtés',
    rAv.refsTableau.length === 12 && rAv.refsTableau.every(r => r0.R.refsAvance.indexOf(r) !== -1) &&
    rAv.secondeRefs.length === 12 && rAv.secondeRefs.every(r => r0.R.refsAvance.some(f => f.indexOf(deSEE(r)) === 0)), JSON.stringify(rAv.secondeRefs.slice(0, 3)));
  verifier('le bandeau nomme le filtre « Comparaison : dans SEE, pas terminés ici », le verdict est pressé',
    rAv.jetons.length === 1 && rAv.jetons[0] === 'Comparaison : dans SEE, mais GATES ne les dit pas terminés' &&
    rAv.puces.filter(x => x.presse === 'true').map(x => x.cle).join() === 'avance', JSON.stringify(rAv.jetons));
  verifier('les comptes ne bougent pas : le rapprochement ne se filtre pas lui-même',
    rAv.puces.map(x => x.n).join() === [ACCORD, 2, 12, 3, ATTENTE, 5].join());
  // Un verdict se combine avec un état : les « pas terminés ici » qui sont en cours.
  await p.click('#etats .etat-btn[data-etat="encours"]'); await p.waitForTimeout(450);
  const rCombi = await lireRapp();
  verifier('un verdict se combine avec l\'état du haut : « en cours » ne garde que les plans en cours parmi les 12',
    rCombi.lignes === r0.R.etatsAvance.filter(e => e === 'encours').length && rCombi.jetons.length === 2 &&
    rCombi.puces.filter(x => x.presse === 'true').map(x => x.cle).join() === 'avance', JSON.stringify([rCombi.lignes, rCombi.jetons]));
  await p.click('#etats .etat-btn[data-etat="encours"]'); await p.waitForTimeout(350);
  await p.click('#verdicts-rapprochement button[data-rapp="manque"]'); await p.waitForTimeout(500);
  const rMa = await lireRapp();
  verifier('« terminés, absents de SEE » remplace la sélection : 3 plans ici, et le tableau de SEE le dit vide, avec le chemin du retour',
    rMa.lignes === 3 && rMa.jetons[0] === 'Comparaison : terminés dans GATES, mais SEE ne les connaît pas' && rMa.seconde === 0 &&
    rMa.secondeVide === 'Ces 3 plans n’ont pas de ligne dans SEE. Les voir dans GATES' &&
    rMa.refsTableau.every(r => r0.R.refsManque.indexOf(r) !== -1) &&
    rMa.puces.filter(x => x.presse === 'true').map(x => x.cle).join() === 'manque', JSON.stringify([rMa.jetons, rMa.lignes, rMa.secondeVide]));
  await p.click('#verdicts-rapprochement button[data-rapp="emission"]'); await p.waitForTimeout(500);
  const rIn = await lireRapp();
  verifier('« autre indice » : 2 plans ici, leurs 2 lignes là, sous l\'autre lettre',
    rIn.lignes === 2 && rIn.refsTableau.sort().join() === r0.R.paires.map(x => x.ici).sort().join() &&
    rIn.secondeRefs.length === 2 && rIn.secondeRefs.every(r => r0.R.paires.some(x => x.la.indexOf(deSEE(r)) === 0)), JSON.stringify([rIn.refsTableau, rIn.secondeRefs]));
  await p.click('#verdicts-rapprochement button[data-rapp="accord"]'); await p.waitForTimeout(500);
  const rId = await lireRapp();
  verifier('« terminés et dans SEE » : les ' + ACCORD + ' plans, des deux côtés',
    rId.lignes === ACCORD && rId.seconde === ACCORD && rId.jetons[0] === 'Comparaison : terminés dans GATES et connus de SEE', JSON.stringify([rId.lignes, rId.seconde]));
  await p.click('#verdicts-rapprochement button[data-rapp="accord"]'); await p.waitForTimeout(500);
  const rOff = await lireRapp();
  verifier('re-cliquer le verdict pressé retire le filtre',
    rOff.lignes === TOTAL && rOff.seconde === LIGNES_SEE && rOff.jetons.length === 0 && rOff.puces.every(x => x.presse === 'false'));
  await p.click('#verdicts-rapprochement button[data-rapp="attente"]'); await p.waitForTimeout(500);
  const rAt = await lireRapp();
  verifier('« pas encore dans SEE » : les ' + ATTENTE + ' plans qui attendent, et le tableau de SEE le dit vide',
    rAt.lignes === ATTENTE && rAt.seconde === 0 && rAt.secondeVide === 'Ces ' + fr(ATTENTE) + ' plans n’ont pas de ligne dans SEE. Les voir dans GATES' &&
    rAt.jetons[0] === 'Comparaison : pas terminés, et pas encore dans SEE : rien d’anormal', JSON.stringify([rAt.lignes, rAt.secondeVide]));
  await p.click('.jeton .x'); await p.waitForTimeout(400);
  verifier('la croix du bandeau retire aussi le filtre du rapprochement',
    await p.evaluate(t => document.querySelectorAll('#corps-tableau tr').length === t &&
      document.getElementById('filtres-actifs').hidden, TOTAL));

  // « seulement dans SEE » : ces références n'ont pas de plan ici — le tableau passe sur SEE et se filtre.
  await p.click('#verdicts-rapprochement button[data-rapp="seul"]'); await p.waitForTimeout(400);
  const rIci = await lireRapp();
  verifier('« seulement dans SEE » réduit le tableau de SEE à ses 5 lignes ; celui de GATES le dit, avec le chemin vers SEE',
    rIci.seconde === 5 && rIci.videIci === 'Ces 5 lignes n’ont pas de plan dans GATES. Les voir dans SEE' &&
    rIci.puces.filter(x => x.presse === 'true').map(x => x.cle).join() === 'seul', JSON.stringify([rIci.seconde, rIci.videIci]));
  verifier('chaque référence est inédite ici',
    rIci.secondeRefs.length === 5 && rIci.secondeRefs.every(r => /^ZZE99\d{2}A800$/.test(deSEE(r)) && r0.R.refsAccord.indexOf(deSEE(r)) === -1), JSON.stringify(rIci.secondeRefs));
  verifier('le bandeau le nomme, avec sa croix',
    rIci.jetons.length === 1 && rIci.jetons[0] === 'Comparaison : lignes de SEE sans plan dans GATES', JSON.stringify(rIci.jetons));
  await p.click('.jeton .x'); await p.waitForTimeout(400);
  const rIci2 = await lireRapp();
  verifier('la croix rend le tableau de SEE entier', rIci2.seconde === LIGNES_SEE && rIci2.jetons.length === 0 && rIci2.puces.every(x => x.presse === 'false'));
  await p.click('#verdicts-rapprochement button[data-rapp="seul"]'); await p.waitForTimeout(300);
  await p.click('#verdicts-rapprochement button[data-rapp="avance"]'); await p.waitForTimeout(400);
  const rBasc = await lireRapp();
  verifier('un lot d\'ici posé après « seulement dans SEE » le remplace : un seul lot à la fois',
    rBasc.puces.filter(x => x.presse === 'true').map(x => x.cle).join() === 'avance' && rBasc.jetons.length === 1 && rBasc.seconde === 12, JSON.stringify(rBasc.jetons));
  await p.click('#verdicts-rapprochement button[data-rapp="avance"]'); await p.waitForTimeout(400);

  // Survoler un verdict éclaire sa part de la figure et ouvre la bulle.
  await p.evaluate(() => document.getElementById('rapprochement').scrollIntoView({ block: 'center' })); await p.waitForTimeout(200);
  const survolRapp = async (selecteur) => {
    await (await p.$(selecteur)).hover(); await p.waitForTimeout(250);
    return p.evaluate(() => ({
      visible: document.getElementById('bulle').dataset.visible,
      texte: document.getElementById('bulle').innerText.replace(/\s+/g, ' '),
      eclaire: [...document.querySelectorAll('#venn-rapprochement .survole')].map(x => x.getAttribute('data-cle')).join()
    }));
  };
  const nEnCours = r0.R.etatsAvance.filter(e => e === 'encours').length;
  const svAv = await survolRapp('#verdicts-rapprochement button[data-rapp="avance"]');
  verifier('survoler « dans SEE, pas terminés ici » éclaire sa part de l\'anneau et ouvre la bulle : le compte, la répartition par état d\'ici, le sens, où mène le clic',
    svAv.visible === 'true' && svAv.eclaire === 'avance' && /Dans SEE, mais pas terminés dans GATES/.test(svAv.texte) &&
    /12 plans/.test(svAv.texte) && new RegExp('en cours dans GATES ' + nEnCours).test(svAv.texte) &&
    /l’avancement GATES est peut-être en retard/.test(svAv.texte) && /n’afficher que ceux-là dans le tableau/.test(svAv.texte), svAv.texte.slice(0, 200));
  const svEm = await survolRapp('#verdicts-rapprochement button[data-rapp="emission"]');
  verifier('la bulle d’« autre indice » montre les paires : référence GATES → solution et lettre dans SEE',
    /[A-Z]{2}E\d{4}A[678]00\d{3}[A-Z] → \d{3}[A-Z]/.test(svEm.texte) && svEm.eclaire === 'emission', svEm.texte.slice(0, 120));
  await p.mouse.move(5, 5); await p.waitForTimeout(150);
  verifier('quitter la section referme la bulle et éteint la figure',
    await p.evaluate(() => document.getElementById('bulle').dataset.visible !== 'true' && !document.querySelector('#venn-rapprochement .survole')));
  // La figure elle-même répond : l'anneau sous la souris, un côté sous la souris.
  const surAnneau = await p.evaluate(() => {
    const path = document.querySelector('#venn-rapprochement .donut-seg[data-cle="accord"]');
    const m = path.getScreenCTM(), q = path.getPointAtLength(path.getTotalLength() / 2);
    return { x: m.a * q.x + m.c * q.y + m.e, y: m.b * q.x + m.d * q.y + m.f };
  });
  await p.mouse.move(surAnneau.x, surAnneau.y); await p.waitForTimeout(250);
  const svAn = await p.evaluate(() => ({
    visible: document.getElementById('bulle').dataset.visible, texte: document.getElementById('bulle').innerText.replace(/\s+/g, ' '),
    eclaire: [...document.querySelectorAll('#venn-rapprochement .survole')].map(x => x.getAttribute('data-cle')).join()
  }));
  verifier('survoler la part verte de l\'anneau ouvre la bulle des plans d\'accord — avec leur part des terminés — et l\'épaissit',
    svAn.visible === 'true' && svAn.eclaire === 'accord' && /Terminés ici, connus de SEE/.test(svAn.texte) &&
    new RegExp(ACCORD + ' plans ' + PCT + '\\s?% des terminés').test(svAn.texte), svAn.texte.slice(0, 120));
  const svMa = await survolRapp('#venn-rapprochement .cote[data-cle="manque"] .grand');
  verifier('survoler le 3 « terminés sans SEE » ouvre sa bulle et souligne le nombre',
    svMa.visible === 'true' && svMa.eclaire === 'manque' && /Terminés ici, inconnus de SEE/.test(svMa.texte) && /3 plans/.test(svMa.texte) &&
    /à vérifier des deux côtés/.test(svMa.texte), svMa.texte.slice(0, 120));
  const svAt = await survolRapp('#venn-rapprochement .cote[data-cle="attente"] .moyen');
  verifier('survoler « pas encore dans SEE » dit que ce n\'est pas anormal, avec la répartition par état',
    svAt.visible === 'true' && svAt.eclaire === 'attente' && /Pas encore dans SEE/.test(svAt.texte) && /rien d’anormal/.test(svAt.texte) &&
    /à faire dans GATES/.test(svAt.texte), svAt.texte.slice(0, 120));
  const svSe = await survolRapp('#venn-rapprochement .cote[data-cle="seul"] .grand');
  verifier('survoler le 5 « seulement dans SEE » ouvre sa bulle',
    svSe.visible === 'true' && svSe.eclaire === 'seul' && /Seulement dans SEE/.test(svSe.texte) && /5 lignes/.test(svSe.texte), svSe.texte.slice(0, 120));
  await p.mouse.move(5, 5); await p.waitForTimeout(150);
  // Au clavier : le verdict qui a le focus éclaire aussi sa part.
  await p.focus('#verdicts-rapprochement button[data-rapp="accord"]'); await p.keyboard.press('Tab'); await p.waitForTimeout(150);
  verifier('au clavier, le verdict qui a le focus éclaire sa part de la figure',
    await p.evaluate(() => document.activeElement.dataset.rapp === 'emission' &&
      [...document.querySelectorAll('#venn-rapprochement .survole')].map(x => x.getAttribute('data-cle')).join() === 'emission'));
  await p.evaluate(() => document.activeElement.blur()); await p.waitForTimeout(100);
  await p.click('#verdicts-rapprochement button[data-rapp="manque"]'); await p.waitForTimeout(400);
  await p.click('#choix-base button[data-base="la"]'); await p.waitForTimeout(400);
  await p.click('#corps-seconde button[data-aller-base="ici"]'); await p.waitForTimeout(400);
  const rLien = await lireRapp();
  verifier('« Les voir dans GATES » repasse sur GATES sans retirer le lot : 3 plans, jeton intact',
    rLien.lignes === 3 && rLien.jetons[0] === 'Comparaison : terminés dans GATES, mais SEE ne les connaît pas' &&
    await p.evaluate(() => !document.getElementById('cadre-tableau').hidden), JSON.stringify([rLien.lignes, rLien.jetons]));
  await p.click('.jeton .x'); await p.waitForTimeout(400);

  // Le périmètre : les plans hors périmètre ne comptent pas.
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const rPe = await lireRapp();
  verifier('le périmètre PERSO réduit les comptes des lots de plans, les verdicts suivent le moteur',
    rPe.R.nbPlans < TOTAL && rPe.R.nbTermines < TERMINES && rPe.R.accord + rPe.R.emission + rPe.R.avance + rPe.R.manque + rPe.R.attente === rPe.R.nbPlans &&
    rPe.puces.map(x => x.n).join() === [rPe.R.accord, rPe.R.emission, rPe.R.avance, rPe.R.manque, rPe.R.attente, rPe.R.seul].join(),
    JSON.stringify(rPe.puces.map(x => x.n)));
  verifier('les références seulement là, sans domaine, restent comptées', rPe.R.seul === 5);
  verifier('la figure le dit aussi : « plans du périmètre », et « tout le contrat » sous ce qui n\'est que là',
    rPe.figure.comptes.indexOf(rPe.R.nbPlans + ' plans du périmètre · ' + rPe.R.nbTermines + ' terminés') === 0 &&
    rPe.figure.cotes[2].mots === 'seulement dans SEE · tout le contrat', JSON.stringify([rPe.figure.comptes, rPe.figure.cotes[2]]));
  verifier('le verdict « seulement dans SEE » le dit aussi', rPe.puces[5].phrase === 'lignes de SEE sans plan dans GATES — tout le contrat', rPe.puces[5].phrase);
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(600);
  verifier('revenir à Tout redonne les 22 choses à vérifier', (await lireRapp()).R.total === 22);
  // Un lot posé suit le périmètre : le verdict et le tableau parlent des mêmes plans.
  await p.click('#verdicts-rapprochement button[data-rapp="avance"]'); await p.waitForTimeout(400);
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const rSuit = await lireRapp();
  verifier('un lot posé suit le périmètre : sous PERSO, le tableau compte ce que le verdict annonce',
    rSuit.puces[2].presse === 'true' && rSuit.lignes === rSuit.puces[2].n && rSuit.lignes < 12 && rSuit.jetons.indexOf('Comparaison : dans SEE, mais GATES ne les dit pas terminés') !== -1,
    JSON.stringify([rSuit.lignes, rSuit.puces[2].n, rSuit.jetons]));
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(600);
  await p.click('.jeton .x'); await p.waitForTimeout(400);
  verifier('de retour sur Tout, le lot retiré, le tableau est entier', (await lireRapp()).lignes === TOTAL);

  // Le contrat : la seconde base est celle du contrat courant.
  await p.selectOption('#select-contrat', 'VRK'); await p.waitForTimeout(1200);
  const rX3 = await lireRapp();
  verifier('changer de contrat recalcule le rapprochement sur ses plans',
    rX3.R.nbPlans !== TOTAL && rX3.R.nbPlans === rX3.lignes && rX3.R.nbLignes === rX3.R.accord + rX3.R.emission + rX3.R.avance + 5 &&
    rX3.R.total === rX3.R.manque + rX3.R.avance + rX3.R.emission + rX3.R.seul &&
    rX3.puces.map(x => x.n).join() === [rX3.R.accord, rX3.R.emission, rX3.R.avance, rX3.R.manque, rX3.R.attente, rX3.R.seul].join(),
    JSON.stringify([rX3.R, rX3.puces.map(x => x.n)]));
  verifier('les plans à vérifier sont ceux d\'un autre contrat',
    rX3.R.refsManque.length > 0 && rX3.R.refsManque.every(r => r0.R.refsManque.indexOf(r) === -1), JSON.stringify(rX3.R.refsManque.slice(0, 2)));
  await p.selectOption('#select-contrat', 'HDK'); await p.waitForTimeout(1200);

  // L'exemple : la même seconde base, les mêmes comptes.
  await basculerMode(p, 'exemple'); await p.waitForTimeout(800);
  const rEx = await lireRapp();
  verifier('en mode exemple, la section reste et dit la même chose',
    !rEx.cache && rEx.R.total === 22 && rEx.puces.map(x => x.cle + '=' + x.n).join() === r0.puces.map(x => x.cle + '=' + x.n).join(),
    JSON.stringify(rEx.puces.map(x => x.cle + '=' + x.n)));
  await basculerMode(p, 'reel'); await p.waitForTimeout(800);

  // Sans description de seconde base, il n'y a rien à rapprocher.
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); delete s.rapprochement; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  const rSans = await lireRapp();
  verifier('sans rapprochement dans la source, la section est absente, et le tableau de là avec elle',
    rSans.cache && rSans.R === null && rSans.secondeCache, JSON.stringify([rSans.cache, rSans.R, rSans.secondeCache]));
  verifier('et le reste de la page est intact', rSans.lignes === TOTAL);
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); s.rapprochement = { nom: 'Vide', cleReference: 'REF', lignes: [] }; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  const rVide = await lireRapp();
  verifier('une seconde base vide : tous les terminés lui manquent, les autres attendent, le reste est inactif, et la figure compte 0 ligne',
    !rVide.cache && rVide.R.manque === TERMINES && rVide.R.attente === TOTAL - TERMINES && rVide.puces[3].n === TERMINES && rVide.puces[3].phrase === 'terminés dans GATES, mais Vide ne les connaît pas' &&
    rVide.puces.filter((x, i) => i !== 3 && i !== 4).every(x => x.inactif) && rVide.figure && /0 ligne/.test(rVide.figure.comptes),
    JSON.stringify([rVide.puces.map(x => x.n), rVide.figure && rVide.figure.comptes]));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(900);
  verifier('la seconde base revenue, la section revient', !(await lireRapp()).cache && (await lireRapp()).R.total === 22);

  // =================================================================
  /* Le tableau de la seconde base : l'extract SEE tel quel — ses vingt
     colonnes, dans son ordre, sous leurs intitulés — derrière l'interrupteur
     GATES | SEE. Le verdict du rapprochement se lit sur chaque ligne : la
     pastille dans la cellule NAME. Pas de vue essentielle pour SEE : la
     source n'en désigne pas. Un tri, une recherche qui ne touchent qu'à
     lui ; cliquer une ligne appariée réduit le tableau d'ici au plan. */
  section('La seconde base, telle que son extract');
  const lireSeconde = () => p.evaluate(() => {
    const Sd = window.__secondeAffichee();
    const cats = {}; (Sd ? Sd.lignes : []).forEach(l => { cats[l.cat] = (cats[l.cat] || 0) + 1; });
    const entetes = [...document.querySelectorAll('#tete-seconde th')];
    const pastilles = {};
    document.querySelectorAll('#corps-seconde .verdict .pastille').forEach(s => {
      const k = s.className.replace('pastille', '').trim(); pastilles[k] = (pastilles[k] || 0) + 1;
    });
    return {
      cache: document.getElementById('choix-base').hidden,
      titre: document.getElementById('bouton-base-la').textContent,
      compte: document.getElementById('compte').textContent,
      interrupteur: !!document.querySelector('#section-plans .section-tete #choix-base'),
      base: [...document.querySelectorAll('#choix-base button')].map(b => b.dataset.base + ':' + b.getAttribute('aria-pressed')).join(' '),
      laMontre: !document.getElementById('cadre-seconde').hidden && document.getElementById('cadre-tableau').hidden,
      iciMontre: !document.getElementById('cadre-tableau').hidden && document.getElementById('cadre-seconde').hidden,
      outils: [...document.querySelectorAll('#section-plans .outils > *')].filter(el => !el.hidden)
        .map(el => el.id || (el.querySelector('input') || {}).id || el.className).join(' '),
      entetes: entetes.map(t => t.textContent.trim()),
      tris: entetes.map(t => t.getAttribute('aria-sort')),
      titres: Sd ? Sd.titres : null, essentielles: Sd ? Sd.essentielles : null,
      n: Sd ? Sd.lignes.length : -1, cats,
      refs: Sd ? Sd.lignes.map(l => l.ref) : [],
      refsPlans: Sd ? Sd.lignes.filter(l => l.cat !== 'seul').map(l => l.ref) : [],
      lignesDom: document.querySelectorAll('#corps-seconde tr[data-i]').length,
      premieres: [...document.querySelectorAll('#corps-seconde tr[data-i]')].slice(0, 3).map(tr => [...tr.children].map(td => td.textContent.trim())),
      pastilles,
      coches: document.querySelectorAll('#corps-seconde td.coche').length,
      cochesTexte: [...new Set([...document.querySelectorAll('#corps-seconde td.coche')].map(td => td.textContent.trim()))].sort(),
      vueVisible: !document.getElementById('vue-seconde').hidden,
      legende: [...document.querySelectorAll('#legende-seconde > span')].map(s => s.textContent.trim()),
      figee: !!document.querySelector('#corps-seconde tr td.col-fige-la .verdict .ref') && !!document.querySelector('#tete-seconde th.col-fige-la') &&
             getComputedStyle(document.querySelector('#tete-seconde th.col-fige-la')).position === 'sticky',
      choisies: document.querySelectorAll('#corps-seconde tr.choisie').length,
      seulsSansPlan: document.querySelectorAll('#corps-seconde tr[data-cat="seul"]').length -
                     document.querySelectorAll('#corps-seconde tr[data-cat="seul"][data-plan]').length,
      gates: document.querySelectorAll('#corps-tableau tr').length,
      jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()),
      reinit: !document.getElementById('reinit').hidden
    };
  });
  const sAvant = await lireSeconde();
  verifier('l’interrupteur GATES | SEE est dans l’en-tête de « Plans », nommé d’après la base, sur GATES au départ',
    !sAvant.cache && sAvant.titre === 'SEE' && sAvant.interrupteur && sAvant.base === 'ici:true la:false' && sAvant.iciMontre &&
    sAvant.outils === 'recherche vue-tableau', JSON.stringify([sAvant.titre, sAvant.base, sAvant.outils]));
  await p.click('#choix-base button[data-base="la"]'); await p.waitForTimeout(500);
  const s0 = await lireSeconde();
  verifier('SEE : le tableau d’ici se range, celui de SEE prend sa place, avec sa recherche et sa légende — sans vue essentielle, la source n’en désigne pas',
    s0.base === 'ici:false la:true' && s0.laMontre && s0.outils === 'recherche-seconde legende-seconde' && !s0.vueVisible, JSON.stringify([s0.base, s0.outils, s0.vueVisible]));
  verifier('toutes ses colonnes, dans son ordre, sous leurs intitulés — les vingt de l\'extract',
    s0.entetes.join('|') === COLONNES_SEE.join('|') && s0.titres.join('|') === COLONNES_SEE.join('|'), s0.entetes.join('|'));
  verifier('une ligne par ligne de l\'extract : ' + LIGNES_SEE + ', soit ' + COMMUN + ' plans d\'ici et 5 seulement là',
    s0.n === LIGNES_SEE && s0.lignesDom === LIGNES_SEE && s0.compte === fr(LIGNES_SEE) + ' lignes', s0.compte);
  verifier('le verdict en pastille dans la cellule NAME — vert, violet, ambre, anneau — aux comptes des verdicts',
    s0.pastilles.accord === ACCORD && s0.pastilles.indice === 2 && s0.pastilles.avance === 12 && s0.pastilles.seul === 5,
    JSON.stringify(s0.pastilles));
  verifier('la référence se recompose de NAME, SOL. et Cust.V : code circuit, E, ATA, A, séquence, trois chiffres, une lettre',
    s0.refs.every(r => /^[A-Z]{2}E\d{4}A[678]00\d{3}[A-Z]$/.test(r)) && s0.refsPlans.every(r => /^[A-Z]{2}E\d{4}A[678]00\d{3}[A-Z]$/.test(r)),
    JSON.stringify([s0.premieres[0].slice(0, 3), s0.refs[0]]));
  /* SEE n'écrit pas la référence comme GATES : son A tombe un cran trop
     tôt — trois chiffres avant lui au lieu de quatre. La colonne NAME porte
     donc cette écriture-là — l'extract tel quel — et c'est la page qui
     décale le A pour apparier. */
  verifier('la colonne NAME porte l’écriture de SEE, le A un cran trop tôt : trois chiffres avant lui',
    s0.premieres.every(l => /^[A-Z]{3}\d{3}A\d{4}$/.test(l[0])),
    JSON.stringify(s0.premieres.map(l => l[0])));
  verifier('et la référence recomposée décale le A d’un cran : NAME + SOL. + Cust.V se lit comme dans GATES',
    s0.premieres[0][0].slice(0, 6) + s0.premieres[0][0].charAt(7) + 'A' + s0.premieres[0][0].slice(8) +
      s0.premieres[0][1] + s0.premieres[0][2] === s0.refs[0],
    JSON.stringify([s0.premieres[0].slice(0, 3), s0.refs[0]]));
  verifier('la colonne NAME est figée à gauche', s0.figee);
  verifier('les cases à cocher de l\'extract se lisent ✓ ou – : cinq colonnes, ' + (5 * LIGNES_SEE) + ' cellules',
    s0.coches === 5 * LIGNES_SEE && s0.cochesTexte.join() === '–,✓', JSON.stringify([s0.coches, s0.cochesTexte]));
  verifier('la légende nomme les quatre verdicts qu\'on peut y lire',
    s0.legende.join('|') === 'terminé ici|autre indice|pas terminé ici|seulement dans SEE', s0.legende.join('|'));
  await p.click('#tete-seconde button[data-tri-seconde="VALIDITY PSN FULL"]'); await p.waitForTimeout(300);
  const sTri = await lireSeconde();
  verifier('cliquer un intitulé trie sur cette colonne',
    sTri.tris[5] === 'ascending' && sTri.premieres[0][5] <= sTri.premieres[1][5] && sTri.premieres[1][5] <= sTri.premieres[2][5],
    JSON.stringify(sTri.premieres.map(l => l[5])));
  await p.click('#tete-seconde button[data-tri-seconde="VALIDITY PSN FULL"]'); await p.waitForTimeout(300);
  const sTri2 = await lireSeconde();
  verifier('re-cliquer inverse', sTri2.tris[5] === 'descending' && sTri2.premieres[0][5] >= sTri2.premieres[1][5], JSON.stringify(sTri2.premieres.map(l => l[5])));
  await p.click('#tete-seconde button[data-tri-seconde="VALIDITY PSN FULL"]'); await p.waitForTimeout(300);
  const sTri3 = await lireSeconde();
  verifier('un troisième clic rend l\'ordre de l\'extract',
    sTri3.tris.every(t => t === 'none') && sTri3.refs[0] === s0.refs[0] && sTri3.premieres[0][0] === s0.premieres[0][0], JSON.stringify(sTri3.premieres[0].slice(0, 3)));
  await p.fill('#recherche-seconde', 'ZZE99'); await p.waitForTimeout(500);
  const sRe = await lireSeconde();
  verifier('la recherche ne filtre que ce tableau : 5 lignes sur ' + LIGNES_SEE + ', le tableau d\'ici intact',
    sRe.n === 5 && sRe.compte === '5 lignes sur ' + fr(LIGNES_SEE) && sRe.gates === TOTAL && sRe.reinit,
    JSON.stringify([sRe.n, sRe.compte, sRe.gates]));
  await p.fill('#recherche-seconde', 'aucune ligne ne porte ceci'); await p.waitForTimeout(500);
  verifier('rien trouvé : le tableau le dit', await p.evaluate(() => (document.querySelector('#corps-seconde .vide-message') || {}).textContent === 'Aucune ligne ne correspond.'));
  await p.click('#reinit'); await p.waitForTimeout(500);
  const sRz = await lireSeconde();
  verifier('« tout réinitialiser » vide aussi cette recherche, et ramène sur GATES',
    sRz.n === LIGNES_SEE && sRz.iciMontre && await p.evaluate(() => document.getElementById('recherche-seconde').value === ''));
  await p.click('#choix-base button[data-base="la"]'); await p.waitForTimeout(400);
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const sPe = await lireSeconde();
  const rPe2 = await lireRapp();
  verifier('sous le périmètre PERSO, les lignes des plans hors périmètre s\'effacent ; celles seulement là restent',
    !sPe.cats.hors && sPe.n === rPe2.R.accord + rPe2.R.emission + rPe2.R.avance + 5 && sPe.n < LIGNES_SEE &&
    sPe.compte === fr(sPe.n) + ' lignes sur ' + fr(LIGNES_SEE), JSON.stringify([sPe.n, sPe.cats, sPe.compte]));
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(700);
  const refChoisie = await p.evaluate(() => document.querySelector('#corps-seconde tr[data-plan]').dataset.plan);
  await p.click('#corps-seconde tr[data-plan] >> nth=0'); await p.waitForTimeout(500);
  const sCl = await lireSeconde();
  verifier('cliquer une ligne appariée bascule sur GATES, réduit à ce plan, la ligne se marque, le bandeau le nomme',
    sCl.gates === 1 && sCl.choisies === 1 && sCl.iciMontre && sCl.base === 'ici:true la:false' &&
    sCl.jetons.join() === 'Sélection : plan ' + refChoisie &&
    await p.evaluate(r => document.querySelector('#corps-tableau tr td.ref').textContent.trim() === r, refChoisie), JSON.stringify([sCl.jetons, sCl.base]));
  await p.click('.jeton .x'); await p.waitForTimeout(500);
  const sCl2 = await lireSeconde();
  verifier('la croix rend tous les plans, sans quitter GATES', sCl2.gates === TOTAL && sCl2.choisies === 0 && sCl2.jetons.length === 0 && sCl2.iciMontre);
  verifier('une ligne seulement là ne mène nulle part : pas de plan à montrer ici', s0.seulsSansPlan === 5 && sCl2.seulsSansPlan === 5);
  // Une sélection posée pendant qu'on regarde SEE ramène sur GATES, où elle a un sens.
  await p.click('#choix-base button[data-base="la"]'); await p.waitForTimeout(400);
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(500);
  const sEtat = await lireSeconde();
  verifier('choisir un état pendant qu’on regarde SEE ramène sur GATES, filtré',
    sEtat.iciMontre && sEtat.base === 'ici:true la:false' && sEtat.gates < TOTAL && sEtat.gates > 0, JSON.stringify([sEtat.base, sEtat.gates]));
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(400);
  await p.click('#choix-base button[data-base="la"]'); await p.waitForTimeout(400);
  await p.click('#verdicts-rapprochement button[data-rapp="accord"]'); await p.waitForTimeout(500);
  const sLot = await lireSeconde();
  verifier('mais un lot du rapprochement se lit des deux côtés : posé depuis SEE, le tableau y reste',
    sLot.laMontre && sLot.n === ACCORD, JSON.stringify([sLot.base, sLot.n]));
  await p.click('#verdicts-rapprochement button[data-rapp="seul"]'); await p.waitForTimeout(500);
  await p.click('#reinit'); await p.waitForTimeout(500);
  const sReinit = await lireSeconde();
  verifier('« tout réinitialiser » ramène sur GATES, entier, sans lot',
    sReinit.iciMontre && sReinit.gates === TOTAL && sReinit.jetons.length === 0, JSON.stringify([sReinit.base, sReinit.gates, sReinit.jetons]));

  // =================================================================
  /* La figure et les verdicts aux largeurs intermédiaires, périmètre posé
     (la figure gagne une ligne, « tout le contrat ») : côte à côte quand la
     place le permet, l'un sous l'autre sinon — jamais de recouvrement, jamais
     hors du cadre, jamais de débord de page. Et la ligne de la phrase, avec
     le périmètre à sa droite, tient elle aussi. */
  section('La figure et les verdicts à toutes les largeurs');
  for (const largeur of [360, 681, 700, 740, 800, 860, 960, 1280]) {
    await p.setViewportSize({ width: largeur, height: 900 }); await p.waitForTimeout(350);
    await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(600);
    const mesure = await p.evaluate(() => {
      const sec = document.getElementById('rapprochement').getBoundingClientRect();
      const fig = document.getElementById('venn-rapprochement').getBoundingClientRect();
      const ver = document.getElementById('verdicts-rapprochement').getBoundingClientRect();
      const r = [...document.querySelectorAll('#verdicts-rapprochement button')].map(b => b.getBoundingClientRect());
      const dedans = x => x.left >= sec.left - 1 && x.right <= sec.right + 1;
      const recouvre = (a, b) => a.right > b.left + 1 && b.right > a.left + 1 && a.bottom > b.top + 1 && b.bottom > a.top + 1;
      const per = document.getElementById('perimetre').getBoundingClientRect(), ph = document.getElementById('phrase').getBoundingClientRect();
      return { coteACote: ver.left >= fig.right - 1, dessous: ver.top >= fig.bottom - 1, recouvre: recouvre(fig, ver) || r.some((a, i) => r.some((b, j) => i < j && recouvre(a, b))),
        dedans: dedans(fig) && dedans(ver) && r.every(dedans), figureVisible: fig.width > 200,
        phraseOk: !recouvre(per, ph) && per.right <= document.querySelector('.avancement').getBoundingClientRect().right + 1,
        page: document.documentElement.scrollWidth <= window.innerWidth };
    });
    verifier('à ' + largeur + ' px, périmètre posé : ' + (mesure.coteACote ? 'côte à côte' : 'l\'un sous l\'autre') + ', sans recouvrement, dans le cadre, sans débord',
      (mesure.coteACote || mesure.dessous) && !mesure.recouvre && mesure.dedans && mesure.figureVisible && mesure.phraseOk && mesure.page, JSON.stringify(mesure));
    await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(400);
  }
  await p.setViewportSize({ width: 1280, height: 1000 }); await p.waitForTimeout(400);

  // =================================================================
  /* Le graphique, plus aérien : une échelle à valeurs rondes (0, 200, 400,
     le plafond nommé « 640 plans »), la semaine seule en graduation et
     l'année une fois par changement, des points pleins cerclés de fond, des
     barres fines au sommet arrondi, et une bande discrète sous la souris. */
  section('Le graphique, plus aérien');
  const graphe = await p.evaluate(() => {
    const grads = [...document.querySelectorAll('svg.graphe .grad')].map(t => t.textContent);
    const iPlafond = grads.findIndex(t => / plans$/.test(t));
    return {
      echelle: grads.slice(0, iPlafond), plafond: grads[iPlafond],
      semaines: grads.filter(t => /^S\d{2}$/.test(t)), avecAnnee: grads.filter(t => /^\d{4}-S/.test(t) && !/plans/.test(t)),
      annees: [...document.querySelectorAll('svg.graphe .annee')].map(t => t.textContent),
      pointsPleins: document.querySelectorAll('svg.graphe circle[fill="var(--fait)"][stroke="var(--surface)"]').length,
      barres: document.querySelectorAll('svg.graphe path[fill="var(--r4)"]').length,
      courbe: (document.querySelector('svg.graphe path[stroke="var(--fait)"][stroke-width="2"]') || {}).tagName === 'path'
    };
  });
  verifier('l’échelle compte trois traits ronds sous le plafond : 0, 200, 400',
    graphe.echelle.join() === '0,200,400', JSON.stringify(graphe.echelle));
  verifier('le plafond est nommé : « ' + TOTAL + ' plans »', graphe.plafond === TOTAL.toLocaleString('fr-FR') + ' plans', graphe.plafond);
  verifier('les graduations ne portent que la semaine, une dizaine au plus',
    graphe.semaines.length >= 6 && graphe.semaines.length <= 12 && graphe.avecAnnee.length <= 1, JSON.stringify([graphe.semaines, graphe.avecAnnee]));
  verifier('l’année s’écrit une fois par changement, sous la graduation',
    graphe.annees.length >= 1 && graphe.annees.length <= 3 && new Set(graphe.annees).size === graphe.annees.length &&
    graphe.annees.every(a => /^\d{4}$/.test(a)), JSON.stringify(graphe.annees));
  verifier('la courbe fait 2 px, ses relevés sont des points pleins cerclés de fond',
    graphe.courbe && graphe.pointsPleins >= 5, JSON.stringify([graphe.courbe, graphe.pointsPleins]));
  verifier('le rythme hebdomadaire se dessine en barres fines, dans un ton clair de la rampe', graphe.barres >= 5, String(graphe.barres));
  const zonesSurvol = await p.$$('.zone-clic');
  await zonesSurvol[Math.floor(zonesSurvol.length / 2)].hover(); await p.waitForTimeout(250);
  verifier('survoler une semaine l’éclaire d’une bande discrète',
    await p.evaluate(() => {
      const z = [...document.querySelectorAll('.zone-clic')].find(el => el.matches(':hover'));
      return !!z && getComputedStyle(z).fill !== 'rgba(0, 0, 0, 0)' && Number(getComputedStyle(z).fillOpacity) < 0.7;
    }));
  await p.mouse.move(5, 5); await p.waitForTimeout(150);

  // =================================================================
  /* Le périmètre : sous le titre, au-dessus de la barre. « Tout », puis une puce par
     domaine avec son compte. Il pilote toute la page — barre, tableau, bloc
     par groupe, courbe, journal, comparatif — et, sous un périmètre, la courbe
     est DÉRIVÉE des cartes plan par plan archivées croisées avec le domaine
     courant de chaque plan, jamais des comptes figés. */
  section('Périmètre par domaine, sous le titre');
  const additionner = l => l.reduce((a, b) => a + b, 0);
  const lirePerimetre = () => p.evaluate(() => {
    const iDom = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'domaine');
    const serie = window.__serieAffichee();
    const evts = window.__journalAffiche().reduce((l, s) => l.concat(s.evenements), []);
    const C = window.__comparatif();
    /* Le comparatif range ses passages par valeur d'arrivée (parValeur),
       puis les nouveaux, les disparus et les changements d'indice. */
    const refsComparatif = C ? Object.keys(C.parValeur).reduce((l, k) => l.concat(C.parValeur[k]), [])
      .concat(['nouveaux', 'disparus', 'indice'].reduce((l, k) => l.concat(C[k]), [])) : [];
    return {
      phrase: document.getElementById('phrase').textContent,
      etats: [...document.querySelectorAll('#etats .etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
      compte: document.getElementById('compte').textContent,
      lignes: document.querySelectorAll('#corps-tableau tr').length,
      domaines: [...new Set([...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.children[iDom].textContent.trim()))],
      groupes: document.querySelectorAll('.critique-ligne').length,
      totalGroupes: [...document.querySelectorAll('.critique-total')].reduce((s, e) => s + (+e.textContent), 0),
      serie: serie.pts, dernier: serie.pts[serie.pts.length - 1],
      note: document.getElementById('note-graphe').textContent,
      evenements: evts.length,
      domainesJournal: [...new Set(evts.map(e => window.__domaineDe(e.ref)))],
      lignesJournal: document.querySelectorAll('.journal-ligne').length,
      comparatif: refsComparatif.length,
      domainesComparatif: [...new Set(refsComparatif.map(r => window.__domaineDe(r)))],
      jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()),
      presse: [...document.querySelectorAll('#choix-perimetre button')]
        .map(b => b.dataset.perimetre + ':' + b.getAttribute('aria-pressed')).join(' '),
      incomplets: document.getElementById('incomplets').textContent,
      rythmes: [...document.querySelectorAll('.critique-effort .v')].map(v => v.textContent.trim()).join('|')
    };
  });
  const selP = await p.evaluate(() => ({
    visible: !document.getElementById('perimetre').hidden &&
             document.getElementById('choix-perimetre').offsetParent !== null,
    /* Hors de la zone du titre — le titre reste seul, centré — à droite de
       la phrase « N sur M plans terminés », juste au-dessus de la barre :
       c'est là qu'on choisit ce qu'on regarde. */
    haut: document.getElementById('perimetre').getBoundingClientRect().top >=
          document.querySelector('.masthead').getBoundingClientRect().bottom &&
          document.getElementById('perimetre').getBoundingClientRect().bottom <=
          document.getElementById('barre').getBoundingClientRect().top + 1,
    horsDuTitre: !document.querySelector('header.masthead #perimetre') &&
                 document.querySelector('.masthead').children.length === 2 &&
                 document.querySelector('.masthead').textContent.indexOf('Périmètre') === -1,
    dansLaLigne: !!document.querySelector('.avancement-ligne #perimetre #choix-perimetre') &&
                 document.getElementById('perimetre').getBoundingClientRect().left >
                 document.getElementById('phrase').getBoundingClientRect().right,
    boutons: [...document.querySelectorAll('#choix-perimetre button')].map(b => ({
      val: b.dataset.perimetre, texte: b.textContent.trim(),
      n: +(b.querySelector('.n') || { textContent: '0' }).textContent.replace(/\s/g, ''),
      presse: b.getAttribute('aria-pressed')
    }))
  }));
  verifier('le sélecteur est là, hors de la zone du titre : à droite de la phrase, au-dessus de la barre',
    selP.visible && selP.haut && selP.horsDuTitre && selP.dansLaLigne, JSON.stringify(selP).slice(0, 160));
  verifier('trois boutons : Tout, puis un par domaine de la démo',
    selP.boutons.map(b => b.val).join(',') === ',BASE/OPTION,PERSO' && /^Tout/.test(selP.boutons[0].texte),
    JSON.stringify(selP.boutons));
  verifier('il démarre sur Tout', selP.boutons.map(b => b.presse).join(',') === 'true,false,false');
  const nBase = selP.boutons[1].n, nPerso = selP.boutons[2].n;
  verifier('chaque puce porte son compte, et les deux domaines font le total',
    selP.boutons[0].n === TOTAL && nBase > 0 && nPerso > 0 && nBase + nPerso === TOTAL,
    nBase + ' + ' + nPerso + ' vs ' + TOTAL);
  const tout0 = await lirePerimetre();
  verifier('en Tout, le tableau mêle les deux domaines', tout0.domaines.length === 2 && tout0.lignes === TOTAL);

  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const perso = await lirePerimetre();
  verifier('choisir PERSO change la phrase d’avancement, qui nomme le périmètre',
    perso.phrase !== tout0.phrase && /dans le périmètre PERSO/.test(perso.phrase), perso.phrase);
  verifier('les quatre états totalisent les plans PERSO', additionner(perso.etats) === nPerso, JSON.stringify(perso.etats));
  verifier('le tableau ne montre que des plans PERSO, et les compte',
    perso.lignes === nPerso && perso.domaines.join() === 'PERSO' && perso.compte === nPerso + ' plans',
    perso.compte + ' / ' + perso.domaines.join());
  verifier('le bloc par groupe ne compte que le périmètre', perso.totalGroupes === nPerso, String(perso.totalGroupes));
  verifier('les rythmes par groupe sont recalculés sur le périmètre', perso.rythmes !== tout0.rythmes,
    perso.rythmes.slice(0, 60));
  verifier('les non renseignés du périmètre sont ceux de la barre',
    new RegExp('non renseigné ' + perso.etats[3] + '$').test(perso.incomplets), perso.incomplets);
  verifier('la courbe est dérivée du périmètre : dernier point = terminés / plans PERSO, autant de relevés',
    perso.dernier.termine === perso.etats[0] && perso.dernier.total === nPerso &&
    perso.serie.length === tout0.serie.length, JSON.stringify(perso.dernier));
  verifier('chaque point du périmètre est plus petit que le point global de la même semaine',
    perso.serie.every((pt, k) => pt.total < tout0.serie[k].total && pt.termine <= tout0.serie[k].termine));
  verifier('la note du graphique nomme le périmètre', /^Historique du périmètre PERSO · \d+ relevés$/.test(perso.note), perso.note);
  verifier('le journal ne garde que les plans PERSO : aucun événement d’un plan BASE/OPTION',
    perso.evenements > 0 && perso.domainesJournal.join() === 'PERSO' && perso.lignesJournal <= tout0.lignesJournal,
    JSON.stringify(perso.domainesJournal) + ' ' + perso.evenements);
  verifier('le comparatif « depuis l’import » aussi',
    perso.comparatif > 0 && perso.comparatif < tout0.comparatif && perso.domainesComparatif.join() === 'PERSO',
    perso.comparatif + ' / ' + tout0.comparatif);
  verifier('le bandeau nomme le périmètre comme un filtre, et la puce est pressée',
    perso.jetons.length === 1 && /^Périmètre : PERSO$/.test(perso.jetons[0]) &&
    perso.presse === ':false BASE/OPTION:false PERSO:true', JSON.stringify(perso.jetons) + ' ' + perso.presse);
  // Le bloc par mois : moins de groupes dans le périmètre que dans l'ensemble.
  await p.selectOption('#dim-critique', '_mois'); await p.waitForTimeout(500);
  const moisPerso = await p.evaluate(() => document.querySelectorAll('.critique-ligne').length);
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(500);
  const moisTout = await p.evaluate(() => document.querySelectorAll('.critique-ligne').length);
  verifier('par mois, le périmètre a moins de lignes de groupe que Tout',
    moisPerso > 0 && moisPerso < moisTout, moisPerso + ' vs ' + moisTout);
  await p.selectOption('#dim-critique', 'ata'); await p.waitForTimeout(500);

  await p.click('#choix-perimetre button[data-perimetre="BASE/OPTION"]'); await p.waitForTimeout(700);
  const base = await lirePerimetre();
  verifier('BASE/OPTION a ses propres comptes',
    additionner(base.etats) === nBase && base.lignes === nBase && base.domaines.join() === 'BASE/OPTION' &&
    base.dernier.total === nBase && base.dernier.termine === base.etats[0], JSON.stringify(base.etats));
  verifier('PERSO + BASE/OPTION = Tout, état par état',
    perso.etats.every((v, k) => v + base.etats[k] === tout0.etats[k]),
    JSON.stringify([perso.etats, base.etats, tout0.etats]));
  verifier('… pour chaque point de la courbe aussi',
    perso.serie.every((pt, k) => pt.total + base.serie[k].total === tout0.serie[k].total &&
      pt.termine + base.serie[k].termine === tout0.serie[k].termine));
  verifier('… et pour les événements du journal et du comparatif',
    perso.evenements + base.evenements === tout0.evenements && perso.comparatif + base.comparatif === tout0.comparatif,
    perso.evenements + ' + ' + base.evenements + ' vs ' + tout0.evenements);

  await p.click('.jeton .x'); await p.waitForTimeout(700);
  const retourTout = await lirePerimetre();
  verifier('la croix du bandeau ramène à Tout, avec exactement les valeurs initiales',
    JSON.stringify(retourTout) === JSON.stringify(tout0),
    Object.keys(tout0).filter(k => JSON.stringify(tout0[k]) !== JSON.stringify(retourTout[k])).join(','));

  // Le périmètre se cumule avec les autres filtres, et « Tout effacer » retire tout.
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(500);
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(500);
  const cumul = await lirePerimetre();
  verifier('périmètre + état se cumulent : les terminés PERSO, « sur » les plans PERSO',
    cumul.lignes === perso.etats[0] && cumul.compte === perso.etats[0] + ' plans sur ' + nPerso &&
    /dans la sélection/.test(cumul.phrase) && cumul.jetons.length === 2, cumul.compte + ' / ' + cumul.phrase);
  verifier('la courbe reste celle du périmètre, et le dit',
    cumul.dernier.total === nPerso && /Historique du périmètre PERSO/.test(cumul.note) &&
    /autres filtres ne s’appliquent pas/.test(cumul.note), cumul.note);
  await p.click('#tout-effacer'); await p.waitForTimeout(700);
  verifier('« Tout effacer » remet le périmètre à Tout',
    JSON.stringify(await lirePerimetre()) === JSON.stringify(tout0));
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(500);
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(700);
  verifier('le bouton « Tout » aussi', JSON.stringify(await lirePerimetre()) === JSON.stringify(tout0));
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(300);
  verifier('re-cliquer la puce pressée ne change rien', JSON.stringify(await lirePerimetre()) === JSON.stringify(tout0));

  // En exemple, même dérivation : l'historique fabriqué a ses cartes.
  await basculerMode(p, 'exemple'); await p.waitForTimeout(900);
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const exPerso = await lirePerimetre();
  verifier('en exemple aussi, la courbe du périmètre est dérivée des cartes',
    exPerso.serie.length >= 5 && exPerso.dernier.total === nPerso && exPerso.dernier.termine === exPerso.etats[0] &&
    exPerso.domainesJournal.join() === 'PERSO', JSON.stringify(exPerso.dernier));
  await basculerMode(p, 'reel'); await p.waitForTimeout(800);
  verifier('revenir au réel rouvre sur Tout', (await lirePerimetre()).presse === ':true BASE/OPTION:false PERSO:false');

  // Un relevé sans carte plan par plan ne peut pas être dérivé : il est écarté, et la note le dit.
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.releves[0].plans = null; s.releves[1].plans = null;
    window.__chargerSource(s);
  });
  await p.waitForTimeout(900);
  const toutSansCarte = await lirePerimetre();
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const sansCarte = await lirePerimetre();
  verifier('en Tout, les relevés sans carte restent sur la courbe (comptes archivés)',
    toutSansCarte.serie.length === tout0.serie.length && !/hors périmètre/.test(toutSansCarte.note), toutSansCarte.note);
  verifier('sous un périmètre, ils sont écartés de la série',
    sansCarte.serie.length === tout0.serie.length - 2, sansCarte.serie.length + ' points');
  verifier('et la note le dit', /2 relevés sans détail plan par plan, hors périmètre/.test(sansCarte.note), sansCarte.note);

  // Sans colonne de domaine, rien à proposer : le sélecteur se tait.
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); delete s.cleDomaine; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  const sansDomaine = await p.evaluate(() => ({
    cache: document.getElementById('perimetre').hidden && document.getElementById('choix-perimetre').offsetParent === null,
    boutons: document.querySelectorAll('#choix-perimetre button').length,
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    bandeau: document.getElementById('filtres-actifs').hidden
  }));
  verifier('sans colonne de domaine, le sélecteur disparaît et tout est affiché',
    sansDomaine.cache && sansDomaine.boutons === 0 && sansDomaine.lignes === TOTAL && sansDomaine.bandeau,
    JSON.stringify(sansDomaine));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(900);
  verifier('la colonne revenue, le sélecteur revient, sur Tout',
    await p.evaluate(() => !document.getElementById('perimetre').hidden &&
      document.querySelectorAll('#choix-perimetre button').length === 3 &&
      document.querySelector('#choix-perimetre button[data-perimetre=""]').getAttribute('aria-pressed') === 'true'));

  // Le périmètre n'est pas une préférence : la page rouvre toujours sur Tout.
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(900);
  await p.reload(); await p.waitForTimeout(1400);
  verifier('le périmètre n’est pas mémorisé : la page rouvre sur Tout',
    await p.evaluate(t => document.querySelector('#choix-perimetre button[data-perimetre=""]').getAttribute('aria-pressed') === 'true' &&
      document.querySelectorAll('#corps-tableau tr').length === t && document.getElementById('filtres-actifs').hidden, TOTAL));

  // =================================================================
  /* Une référence UD = racine (l'identité du plan : 3 lettres, 4 chiffres, A,
     3 chiffres) + solution (3 chiffres) + indice (une lettre). Le parseur
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
  const canon = lu({ racine: 'HEL0225A017', solution: '001', indice: 'A', valide: true });
  formes.slice(0, 7).forEach(([forme, res]) => {
    verifier('« ' + forme + ' » se lit HEL0225A017 / 001 / A', lu(res) === canon, lu(res));
  });
  verifier('séparateurs mélangés, minuscules et espaces autour : 002 / B',
    lu(formes[7][1]) === lu({ racine: 'HEL0225A017', solution: '002', indice: 'B', valide: true }), lu(formes[7][1]));
  verifier('une autre racine, solution 003, indice C',
    lu(formes[8][1]) === lu({ racine: 'CAB1000A001', solution: '003', indice: 'C', valide: true }), lu(formes[8][1]));
  verifier('hors format : la chaîne entière est la racine, et rien d’autre',
    formes[9][1].racine === 'UD-24-1037' && formes[9][1].valide === false &&
    formes[9][1].solution === '' && formes[9][1].indice === '', lu(formes[9][1]));
  verifier('hors format, épurée : majuscules, sans espaces autour',
    formes[10][1].racine === 'UD-24-1037' && !formes[10][1].valide, lu(formes[10][1]));
  verifier('sans révision, ce n’est pas une référence au format',
    !formes[11][1].valide && formes[11][1].racine === 'HEL0225A017001', lu(formes[11][1]));
  verifier('un « B » à la place du « A » de la racine non plus', !formes[12][1].valide, lu(formes[12][1]));
  verifier('vide et null donnent une racine vide, non valide, sans planter',
    formes[13][1].racine === '' && !formes[13][1].valide && formes[14][1].racine === '' && !formes[14][1].valide);

  /* Les références de la démonstration suivent l'anatomie réelle : code
     circuit (2 lettres), E, ATA et sous-ATA (4 chiffres), A, séquence (600
     côté pilote, 700 copilote, 800 les boîtes), solution, indice. Et la
     colonne « Séquence » de l'export dit la même chose que la référence :
     c'est ce qui permet de regrouper par séquence sans rien deviner. */
  const anatomie = await p.evaluate(() => {
    const iRef = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
    const iSeq = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'sequence');
    const lignes = [...document.querySelectorAll('#corps-tableau tr')].map(tr => ({
      ref: tr.children[iRef].textContent.trim(), seq: tr.children[iSeq].textContent.trim() }));
    return {
      titreSeq: [...document.querySelectorAll('tr.titres th')][iSeq].textContent.trim(),
      forme: lignes.every(l => /^[A-Z]{2}E\d{4}A[678]00\d{3}[A-Z]$/.test(l.ref)),
      accord: lignes.every(l => l.ref.slice(8, 11) === l.seq),
      sequences: [...new Set(lignes.map(l => l.seq))].sort(),
      racines: new Set(lignes.map(l => l.ref.slice(0, 14))).size, n: lignes.length
    };
  });
  verifier('les références de la démonstration s\'écrivent comme les vraies : CC + E + ATA + A + séquence + solution + indice',
    anatomie.forme, JSON.stringify(anatomie));
  verifier('la séquence vaut 600 (pilote), 700 (copilote) ou 800 (boîtes), et la colonne « Séquence » dit la même chose que la référence',
    anatomie.titreSeq === 'Séquence' && anatomie.sequences.join() === '600,700,800' && anatomie.accord,
    JSON.stringify([anatomie.titreSeq, anatomie.sequences, anatomie.accord]));
  verifier('chaque plan a sa propre racine + solution : rien ne s\'apparie par accident',
    anatomie.racines === anatomie.n, anatomie.racines + ' / ' + anatomie.n);
  const parSequence = await p.evaluate(async () => {
    const sel = document.getElementById('dim-critique');
    sel.value = 'sequence'; sel.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise(r => setTimeout(r, 500));
    const plus = document.getElementById('plus-groupes'); if (plus) { plus.click(); await new Promise(r => setTimeout(r, 400)); }
    return {
      propose: [...sel.options].map(o => o.value).indexOf('sequence') !== -1,
      groupes: [...document.querySelectorAll('.critique-ligne')].map(l => l.querySelector('.critique-nom').textContent.trim()).sort()
    };
  });
  verifier('« Séquence » est proposée dans « Avancement FWD par… », et n\'y ouvre que 600, 700 et 800',
    parSequence.propose && parSequence.groupes.join() === '600,700,800', JSON.stringify(parSequence));
  await p.evaluate(async () => {
    const sel = document.getElementById('dim-critique');
    sel.value = 'ata'; sel.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise(r => setTimeout(r, 400));
  });

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
      if (e.type === 'indice') indices.push({ i: s.i, type: e.type, ref: e.ref, ancienne: e.ancienne, avant: e.avant, apres: e.apres });
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
      types: indices.map(x => x.type).sort().join(' '),
      comparatif: C && C.indice ? C.indice.slice().sort() : null,
      reemissions: C && C.reemissions ? C.reemissions : null
    };
  });
  verifier('le journal porte les six réémissions fabriquées', app.indices.length === 6, String(app.indices.length));
  verifier('à six semaines différentes', app.semaines === 6, String(app.semaines));
  verifier('toutes changent d’indice (la lettre) : une autre solution serait un autre plan',
    app.types === 'indice indice indice indice indice indice', app.types);
  verifier('chacune garde sa racine et change de référence', app.memeRacine, lu(app.indices.slice(0, 2)));
  verifier('deux d’entre elles changent aussi d’état au passage', app.avecEtat === 2, String(app.avecEtat));
  verifier('aucun de ces plans n’est compté comme nouveau ni disparu', app.touches.length === 0, lu(app.touches));
  verifier('les deux plans réellement apparus restent des nouveaux, et rien n’a disparu',
    app.nouveaux.length === 2 && app.disparus.length === 0, app.nouveaux.length + ' / ' + app.disparus.length);
  verifier('le journal parle des nouvelles références, celles du tableau',
    app.indices.every(x => refsTable.indexOf(x.ref) !== -1 && refsTable.indexOf(x.ancienne) === -1));
  verifier('le comparatif « depuis l’import » porte les réémissions de la dernière semaine',
    app.comparatif && app.comparatif.length >= 1 && lu(app.comparatif) === lu(app.attenduComparatif),
    lu(app.comparatif) + ' vs ' + lu(app.attenduComparatif));
  verifier('avec, pour chacun, l’ancienne et la nouvelle référence',
    app.reemissions && app.reemissions.length === app.comparatif.length &&
    app.reemissions.every(r => r.ancienne && r.ref && r.ancienne !== r.ref), lu(app.reemissions));

  /* La dernière semaine porte un changement d'indice : la puce du comparatif
     est celle-là, et il n'y en a pas d'autre sorte. */
  const cleReem = 'indice';
  const domIndice = await p.evaluate(cle => ({
    puce: (document.querySelector('.puce-delta[data-delta="' + cle + '"]') || { textContent: '' }).textContent,
    pastille: !!document.querySelector('.puce-delta[data-delta="' + cle + '"] .pastille.indice'),
    comptes: [...document.querySelectorAll('.compte-passage[data-passage="indice"]')].map(b => b.textContent.replace(/\s+/g, ' ').trim()),
    boutons: !!document.querySelector('#filtre-journal button[data-journal="indice"]') &&
             !document.querySelector('#filtre-journal button[data-journal="solution"]') &&
             document.querySelectorAll('#filtre-journal button').length === 5
  }), cleReem);
  verifier('la puce de la réémission est là, avec sa pastille violette',
    /changements? d’indice/.test(domIndice.puce) && domIndice.pastille, domIndice.puce);
  verifier('chaque semaine concernée compte son changement d’indice, en bouton',
    domIndice.comptes.length === 6 && domIndice.comptes.every(t => /^1 changement d’indice$/.test(t)),
    lu(domIndice.comptes));
  verifier('et le filtre du journal ne propose que lui, en cinq boutons : Tout, trois états, l’indice', domIndice.boutons);
  const violet = await p.evaluate(() => {
    const fond = el => el && getComputedStyle(el).backgroundColor;
    return {
      puce: fond(document.querySelector('.puce-delta[data-delta="indice"] .pastille')),
      filtre: fond(document.querySelector('#filtre-journal button[data-journal="indice"] .pastille')),
      verdict: fond(document.querySelector('#verdicts-rapprochement button[data-rapp="emission"] .pastille')),
      anneau: getComputedStyle(document.querySelector('#venn-rapprochement .donut-seg.emission')).stroke
    };
  });
  verifier('le violet du changement d’indice est le même partout : puce du comparatif, filtre du journal, verdict « autre indice », part de l’anneau',
    /^rgb/.test(violet.puce) && violet.puce === violet.filtre && violet.puce === violet.verdict && violet.puce === violet.anneau, JSON.stringify(violet));

  /* « Pourtant il est faux » : le journal doit être juste. Chaque semaine, la
     somme des comptes du résumé est le nombre de lignes ; la mini-jauge fait
     100 ; et sous chaque filtre, les lignes montrées sont exactement celles
     que les comptes annoncent — une case par événement, partout. */
  const toutDeplier = async () => {
    for (let g = 0; g < 30; g++) { const pl = await p.$('.journal-plier[aria-expanded="false"]'); if (!pl) break; await pl.click(); await p.waitForTimeout(50); }
    for (let g = 0; g < 30; g++) { const b = await p.$('.journal-plus[data-tout]'); if (!b) break; await b.click(); await p.waitForTimeout(50); }
  };
  await toutDeplier();
  const justesse = await p.evaluate(() => [...document.querySelectorAll('.journal-semaine')].map(sem => ({
    sem: sem.querySelector('.sem').textContent,
    comptes: [...sem.querySelectorAll('.resume b')].reduce((t, b) => t + Number(b.textContent.replace(/\s/g, '')), 0),
    lignes: sem.querySelectorAll('.journal-ligne').length,
    jauge: Math.round([...sem.querySelectorAll('.mini-jauge span')].reduce((t, x) => t + parseFloat(x.style.width), 0)),
    effaceBouton: !!sem.querySelector('.compte-passage[data-passage="vide"]')
  })));
  verifier('dans chaque semaine, la somme des comptes du résumé est le nombre de lignes',
    justesse.length >= 5 && justesse.every(x => x.comptes === x.lignes), JSON.stringify(justesse.filter(x => x.comptes !== x.lignes).slice(0, 3)));
  verifier('et la mini-jauge de chaque semaine fait 100', justesse.every(x => x.jauge === 100), JSON.stringify(justesse.map(x => x.jauge)));
  verifier('« effacés » se compte mais ne se filtre pas : jamais un bouton que la barre du filtre ne saurait montrer',
    justesse.every(x => !x.effaceBouton));
  for (const f of ['termine', 'encours', 'afaire', 'indice']) {
    await p.click('#filtre-journal button[data-journal="' + f + '"]'); await p.waitForTimeout(300);
    await toutDeplier();
    const sousFiltre = await p.evaluate(f => ({
      lignes: document.querySelectorAll('.journal-ligne').length,
      comptes: [...document.querySelectorAll('.compte-passage[data-passage="' + f + '"] b')].reduce((t, b) => t + Number(b.textContent.replace(/\s/g, '')), 0),
      types: [...new Set([...document.querySelectorAll('.journal-ligne')].map(l => l.dataset.type))].join(),
      arrivees: [...new Set([...document.querySelectorAll('.journal-ligne .etiq-etat.apres')].map(e => e.textContent.trim()))].join()
    }), f);
    verifier('sous « ' + f + ' », les lignes sont exactement celles que les comptes annoncent',
      sousFiltre.lignes === sousFiltre.comptes && (f === 'indice' ? sousFiltre.types === 'indice' || sousFiltre.lignes === 0 : sousFiltre.types === 'change' || sousFiltre.lignes === 0),
      JSON.stringify(sousFiltre));
  }
  await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(300);

  // Survoler la puce : les deux références, ancienne → nouvelle.
  await p.evaluate(() => document.getElementById('comparatif').scrollIntoView({ block: 'center' }));
  await p.waitForTimeout(250);
  const bbPuce = await (await p.$('.puce-delta[data-delta="' + cleReem + '"]')).boundingBox();
  await p.mouse.move(bbPuce.x + 6, bbPuce.y + bbPuce.height / 2); await p.waitForTimeout(200);
  const survol = await p.evaluate(() => document.getElementById('bulle').textContent);
  verifier('survoler la puce montre « ancienne → nouvelle »',
    /[A-Z]{3}\d{4}A\d{6}[A-Z] → [A-Z]{3}\d{4}A\d{6}[A-Z]/.test(survol), survol.slice(0, 100));
  await p.mouse.move(5, 5); await p.waitForTimeout(150);

  // Cliquer la puce : le tableau ne montre plus que les plans réémis, sous leur nouvelle référence.
  await p.click('.puce-delta[data-delta="' + cleReem + '"]'); await p.waitForTimeout(500);
  const filtreIndice = await p.evaluate(cle => {
    const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
    return {
      lignes: [...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.children[i].textContent.trim()).sort(),
      presse: document.querySelector('.puce-delta[data-delta="' + cle + '"]').getAttribute('aria-pressed'),
      jeton: document.getElementById('filtres-actifs').textContent
    };
  }, cleReem);
  verifier('cliquer la puce de la réémission filtre le tableau sur les nouvelles références',
    lu(filtreIndice.lignes) === lu(app.comparatif), lu(filtreIndice.lignes));
  verifier('la puce se marque pressée et le bandeau nomme le filtre',
    filtreIndice.presse === 'true' && /changements d’indice/.test(filtreIndice.jeton), filtreIndice.jeton);
  await p.click('.puce-delta[data-delta="' + cleReem + '"]'); await p.waitForTimeout(500);
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
    indice: [...document.querySelectorAll('.journal-ligne.reemission')].map(b => ({
      ref: b.dataset.ref, type: b.dataset.type,
      ancienne: (b.querySelector('.ref-indice .ancienne') || { textContent: '' }).textContent,
      nouvelle: (b.querySelector('.ref-indice .nouvelle') || { textContent: '' }).textContent,
      etats: b.querySelectorAll('.vers .etiq-etat').length,
      quoi: b.querySelector('.quoi').textContent
    })),
    presse: [...document.querySelectorAll('#filtre-journal button')]
      .map(b => b.dataset.journal + ':' + b.getAttribute('aria-pressed')).join(' ')
  }));
  verifier('sous ce filtre, le journal ne montre que les six changements d’indice',
    lignesIndice.total === 6 && lignesIndice.indice.length === 6, lignesIndice.total + ' / ' + lignesIndice.indice.length);
  verifier('chaque ligne se lit « ancienne → nouvelle », puis l’état avant et après',
    lignesIndice.indice.every(l => l.type === 'indice' && /^[A-Z]{3}\d{4}A\d{6}[A-Z]$/.test(l.ancienne) &&
      l.nouvelle === '→ ' + l.ref && l.etats === 2), lu(lignesIndice.indice[0]));
  verifier('et nomme le plan', lignesIndice.indice.every(l => l.quoi.trim() !== ''));
  verifier('le filtre du journal reflète le choix',
    lignesIndice.presse === ':false termine:false encours:false afaire:false indice:true', lignesIndice.presse);
  await p.click('#filtre-journal button[data-journal="indice"]'); await p.waitForTimeout(400);
  // Le journal se replie à chaque rendu : seule la première semaine reste ouverte.
  for (let garde = 0; garde < 20; garde++) {
    const plie = await p.$('.journal-plier[aria-expanded="false"]');
    if (!plie) break;
    await plie.click(); await p.waitForTimeout(90);
  }
  await p.waitForTimeout(250);
  const lignesLettre = await p.evaluate(() => [...document.querySelectorAll('.journal-ligne')].map(b => b.dataset.type));
  verifier('le bouton « Changement d’indice » du filtre donne les mêmes six lignes',
    lignesLettre.length === 6 && lignesLettre.every(t => t === 'indice'), lu(lignesLettre));
  const refIndice = await p.evaluate(() => document.querySelector('.journal-ligne.reemission').dataset.ref);
  await p.click('.journal-ligne.reemission >> nth=0'); await p.waitForTimeout(500);
  verifier('cliquer une réémission réduit le tableau au plan, sous sa nouvelle référence',
    await p.evaluate(r => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
      const trs = document.querySelectorAll('#corps-tableau tr');
      return trs.length === 1 && trs[0].children[i].textContent.trim() === r;
    }, refIndice), refIndice);
  await p.click('.journal-ligne.reemission >> nth=0'); await p.waitForTimeout(400);
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
  verifier('les changements d’indice comptés dans les bulles font les six réémissions du journal',
    toutesLignes.filter(l => /changements? d’indice/.test(l.texte)).reduce((s, l) => s + Number(l.n), 0) === 6,
    lu(toutesLignes.filter(l => /changements? d’indice/.test(l.texte)).map(l => l.texte)));

  // =================================================================
  section('Chargement et cohérence des chiffres');
  const kpi = await p.evaluate(() => ({
    titre: document.title,
    phrase: document.getElementById('phrase').textContent,
    pct: document.querySelector('#barre span').textContent,
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
    parts: [...document.querySelectorAll('#barre span')].map(s => parseFloat(s.style.width)),
    compte: document.getElementById('compte').textContent,
    lignes: (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length)
  }));
  const somme = kpi.etats.reduce((a, b) => a + b, 0);
  verifier('le titre de la page est posé', kpi.titre === 'Suivi FWD', kpi.titre);
  /* La semaine ISO, éprouvée sur des dates dont la réponse est connue —
     jamais sur la formule de la page recopiée dans le test, qui ferait
     passer au vert l'erreur qu'elle contiendrait. Les heures comptent :
     une date qui traîne son heure faisait basculer la semaine d'un cran. */
  const CAS_ISO = [
    ['2026-09-21T00:00:00Z', '2026-S39'], ['2026-09-22T09:00:00Z', '2026-S39'], ['2026-09-27T23:30:00Z', '2026-S39'],
    ['2026-09-28T00:00:00Z', '2026-S40'], ['2027-01-01T12:00:00Z', '2026-S53'], ['2027-01-04T00:00:00Z', '2027-S01'],
    ['2027-01-05T09:00:00Z', '2027-S01'], ['2027-01-07T23:00:00Z', '2027-S01'], ['2027-01-11T09:00:00Z', '2027-S02'],
    ['2021-01-01T15:00:00Z', '2020-S53'], ['2024-12-30T12:00:00Z', '2025-S01'], ['2026-01-01T00:00:00Z', '2026-S01']
  ];
  const isoVu = await p.evaluate(cas => cas.map(c => window.__etiquetteISO(new Date(c[0]))), CAS_ISO);
  verifier('la semaine ISO est juste sur douze dates de référence, à toute heure du jour — y compris les années qui commencent un vendredi',
    isoVu.join() === CAS_ISO.map(c => c[1]).join(),
    JSON.stringify(CAS_ISO.map((c, i) => c[0] + ' → ' + isoVu[i] + (isoVu[i] === c[1] ? '' : ' ≠ ' + c[1])).filter((t, i) => isoVu[i] !== CAS_ISO[i][1])));
  /* Sous le titre : la semaine d'aujourd'hui, avec ses dates — et le
     repère de la courbe, qui doit s'accorder avec elle. On compare aux
     valeurs attendues, calculées ici, et non à la formule de la page. */
  const MOIS_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
  const attenduDuJour = () => {
    const n = new Date(), j = new Date(Date.UTC(n.getFullYear(), n.getMonth(), n.getDate()));
    const jour = j.getUTCDay() || 7;
    const lundi = new Date(j.getTime() - (jour - 1) * 86400000);
    const dim = new Date(lundi.getTime() + 6 * 86400000);
    const t = new Date(j.getTime() + (4 - jour) * 86400000);
    const sem = Math.ceil(((t.getTime() - Date.UTC(t.getUTCFullYear(), 0, 1)) / 86400000 + 1) / 7);
    const m1 = MOIS_FR[lundi.getUTCMonth()], m2 = MOIS_FR[dim.getUTCMonth()];
    return {
      num: 'Semaine ' + sem,
      dates: m1 === m2
        ? 'du ' + lundi.getUTCDate() + ' au ' + dim.getUTCDate() + ' ' + m2 + ' ' + dim.getUTCFullYear()
        : 'du ' + lundi.getUTCDate() + ' ' + m1 + ' au ' + dim.getUTCDate() + ' ' + m2 + ' ' + dim.getUTCFullYear()
    };
  };
  const attAvant = attenduDuJour();
  const semaineTitre = await p.evaluate(() => {
    const t = window.__semaineDuTitre();
    t.repere = ([...document.querySelectorAll('svg.graphe .repere-auj')].map(x => x.textContent)[0]) || '';
    t.sansMention = !document.getElementById('releve-semaine');
    return t;
  });
  const attApres = attenduDuJour();   // la batterie dure : minuit peut tomber entre les deux
  verifier('sous le titre, la semaine d’aujourd’hui et ses dates exactes — celles de la vraie date, pas celles du dernier relevé',
    (semaineTitre.num === attAvant.num && semaineTitre.dates === attAvant.dates) ||
    (semaineTitre.num === attApres.num && semaineTitre.dates === attApres.dates),
    JSON.stringify([semaineTitre.num, semaineTitre.dates, attAvant, attApres]));
  verifier('le titre ne porte que la semaine d’aujourd’hui : aucune mention du dernier relevé, quel que soit son âge',
    !/dernier relevé|il y a/.test(semaineTitre.titre) && semaineTitre.sansMention,
    JSON.stringify(semaineTitre));
  verifier('le repère de la courbe ne dit « aujourd’hui » que si le dernier relevé est de cette semaine',
    semaineTitre.repere === (semaineTitre.iAuj === semaineTitre.auj ? 'aujourd’hui' : 'dernier relevé'),
    JSON.stringify([semaineTitre.repere, semaineTitre.iAuj, semaineTitre.auj]));
  /* Les deux cas, joués pour de bon : un historique arrêté cette semaine —
     la ligne se tait, la courbe dit « aujourd'hui » — puis le même reculé
     de trois semaines. La démonstration étant figée en 2026, sans cela le
     premier cas ne serait jamais exercé. */
  const deuxCas = await p.evaluate(async () => {
    const jour = 86400000, lu = () => window.__semaineDuTitre();
    const poser = recul => {
      const s = window.__jeuDExemple('HDK'), n = s.releves.length, base = new Date();
      s.releves = s.releves.map((r, i) => {
        const d = new Date(base.getTime() - ((n - 1 - i) + recul) * 7 * jour);
        return Object.assign({}, r, { semaine: window.__etiquetteISO(d) });
      });
      window.__chargerSource(s);
    };
    const attendre = ms => new Promise(r => setTimeout(r, ms));
    poser(0); await attendre(600);
    const ajour = lu();
    ajour.repere = ([...document.querySelectorAll('svg.graphe .repere-auj')].map(x => x.textContent)[0]) || '';
    poser(3); await attendre(600);
    const vieux = lu();
    vieux.repere = ([...document.querySelectorAll('svg.graphe .repere-auj')].map(x => x.textContent)[0]) || '';
    return { ajour, vieux };
  });
  verifier('un historique archivé cette semaine : le titre dit la semaine, la courbe dit « aujourd’hui »',
    deuxCas.ajour.iAuj === deuxCas.ajour.auj && !/dernier relevé/.test(deuxCas.ajour.titre) && deuxCas.ajour.repere === 'aujourd’hui',
    JSON.stringify(deuxCas.ajour));
  verifier('le même reculé de trois semaines : le titre reste muet sur le relevé, c’est la courbe qui dit « dernier relevé »',
    deuxCas.vieux.iAuj - deuxCas.vieux.auj === 3 && !/dernier relevé|il y a/.test(deuxCas.vieux.titre) &&
    deuxCas.vieux.repere === 'dernier relevé',
    JSON.stringify(deuxCas.vieux));
  /* La reprise (retour sur l'onglet, minuterie horaire) ne casse rien quand
     la semaine n'a pas bougé : mêmes valeurs, page toujours debout. */
  const apresReprise = await p.evaluate(async () => {
    window.__reprendreLaSemaine();
    await new Promise(r => setTimeout(r, 300));
    const t = window.__semaineDuTitre();
    t.repere = ([...document.querySelectorAll('svg.graphe .repere-auj')].map(x => x.textContent)[0]) || '';
    t.lignes = document.querySelectorAll('#corps-tableau tr').length;
    return t;
  });
  verifier('reprendre la semaine sans qu’elle ait changé laisse la page identique',
    apresReprise.titre === deuxCas.vieux.titre && apresReprise.repere === 'dernier relevé' && apresReprise.lignes > 0,
    JSON.stringify(apresReprise));
  /* ---------------------------------------------------------------
     Chercher un plan : une seule barre sous le titre, qui répond par la
     fiche du plan. Les références attendues sont prises dans le
     rapprochement et le journal, les écritures tapées sont fabriquées ici.
     --------------------------------------------------------------- */
  console.log('\n— Chercher un plan —');
  await p.evaluate(() => window.scrollTo(0, 0));
  const ordreHaut = await p.evaluate(() => {
    const t = document.querySelector('.masthead'), c = document.getElementById('chercher-plan'), a = document.querySelector('section.avancement');
    return !!(t && c && a) && !!(t.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING) &&
      !!(c.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING) && c.offsetParent !== null;
  });
  verifier('la barre de recherche est sous le titre, avant l’avancement, et visible', ordreHaut);
  const cibles = await p.evaluate(() => {
    const R = window.__rapprochement();
    const accord = R.accord[0].reference;
    const seul = R.lignes.filter(l => l.cat === 'seul')[0];
    let bouge = null;
    window.__journal().some(sem => sem.evenements.some(e => {
      if (e.type === 'change' && R.parPlan[e.ref]) { bouge = { ref: e.ref, apres: e.apres, cApres: e.cApres, vApres: e.vApres }; return true; }
      return false;
    }));
    return { accord, seul: seul ? seul.ref : null, bouge };
  });
  const enSEE = r => r.slice(0, 6) + 'A' + r.charAt(6) + r.slice(8);
  const trouve = await p.evaluate(c => ({
    debut: window.__chercherPlan(c.accord.slice(0, 7)),
    entier: window.__chercherPlan(c.accord),
    see: window.__chercherPlan(c.accord.slice(0, 6) + 'A' + c.accord.charAt(6) + c.accord.slice(8)),
    tape: window.__chercherPlan(c.accord.slice(0, 3).toLowerCase() + '-' + c.accord.slice(3, 7) + ' ' + c.accord.slice(7)),
    court: window.__chercherPlan(c.accord.slice(0, 2)),
    seul: c.seul ? window.__chercherPlan(c.seul) : []
  }), cibles);
  verifier('un bout de référence trouve le plan ; la référence entière le trouve seul',
    trouve.debut.indexOf(cibles.accord) !== -1 && trouve.entier.length === 1 && trouve.entier[0] === cibles.accord, JSON.stringify([trouve.debut.slice(0, 4), trouve.entier]));
  verifier('écrite à la mode de SEE (' + enSEE(cibles.accord) + '), en minuscules ou avec des séparateurs, la référence mène au même plan',
    trouve.see[0] === cibles.accord && trouve.tape[0] === cibles.accord, JSON.stringify([trouve.see, trouve.tape]));
  verifier('moins de trois caractères : aucune suggestion', trouve.court.length === 0, JSON.stringify(trouve.court));
  verifier('une ligne que SEE est seule à connaître se cherche aussi', !!cibles.seul && trouve.seul[0] === cibles.seul, JSON.stringify([cibles.seul, trouve.seul]));

  await p.click('#champ-plan'); await p.keyboard.type(cibles.accord.slice(0, 7)); await p.waitForTimeout(250);
  const listeSug = await p.evaluate(() => ({
    visible: !document.getElementById('suggestions-plan').hidden,
    refs: [...document.querySelectorAll('#suggestions-plan .suggestion-plan .ref')].map(r => r.textContent),
    marque: !!document.querySelector('#suggestions-plan .suggestion-plan .ref mark'),
    choisie: document.querySelector('#suggestions-plan [aria-selected="true"]') ? document.querySelector('#suggestions-plan [aria-selected="true"] .ref').textContent : '',
    aria: document.getElementById('champ-plan').getAttribute('aria-expanded')
  }));
  verifier('taper le début d’une référence ouvre la liste, la partie tapée surlignée, la première suggestion choisie',
    listeSug.visible && listeSug.refs.indexOf(cibles.accord) !== -1 && listeSug.marque && listeSug.choisie === listeSug.refs[0] && listeSug.aria === 'true',
    JSON.stringify(listeSug));
  await p.keyboard.press('Escape'); await p.waitForTimeout(100);
  verifier('Échap referme la liste', await p.evaluate(() => document.getElementById('suggestions-plan').hidden));
  await p.fill('#champ-plan', ''); await p.keyboard.type(cibles.accord); await p.waitForTimeout(250);
  await p.keyboard.press('Enter'); await p.waitForTimeout(400);
  const fiche = await p.evaluate(ref => {
    const f = document.getElementById('fiche-plan');
    const cases = [...f.querySelectorAll('.fiche-frise .frise-case')];
    return {
      visible: !f.hidden, ref: f.querySelector('.fiche-ref') ? f.querySelector('.fiche-ref').textContent.replace(/\s+/g, ' ').trim() : '',
      cases: cases.length, derniere: cases.length ? cases[cases.length - 1].getAttribute('style') : '',
      trajectoire: window.__trajectoire(ref).length,
      titres: [...f.querySelectorAll('.fiche-bloc h3')].map(h => h.textContent),
      texte: f.textContent.replace(/\s+/g, ' '),
      liste: document.getElementById('suggestions-plan').hidden
    };
  }, cibles.accord);
  const decoupe = await p.evaluate(ref => { const u = window.__analyserUD(ref); return u.racine + ' ' + u.solution + ' ' + u.indice; }, cibles.accord);
  verifier('Entrée ouvre la fiche du plan : sa référence découpée racine · solution · indice, la liste refermée',
    fiche.visible && fiche.ref === decoupe && fiche.liste, JSON.stringify([fiche.ref, decoupe]));
  verifier('la fiche réunit aujourd’hui, semaine par semaine, son groupe et la comparaison',
    ['Aujourd’hui', 'Semaine par semaine', 'Comparaison avec SEE'].every(t => fiche.titres.indexOf(t) !== -1) &&
    fiche.titres.some(t => /^Avancement par /.test(t)), JSON.stringify(fiche.titres));
  verifier('une case par relevé détaillé, la dernière verte : ce plan est terminé',
    fiche.cases === fiche.trajectoire && fiche.cases >= 2 && /var\(--fait\)/.test(fiche.derniere), JSON.stringify([fiche.cases, fiche.trajectoire, fiche.derniere]));
  verifier('son verdict dans la comparaison est celui du rapprochement, et la ligne de SEE est donnée telle que SEE l’écrit',
    fiche.texte.indexOf('terminé dans GATES et connu de SEE') !== -1 && fiche.texte.indexOf('Ligne de SEE : ' + enSEE(cibles.accord).slice(0, 11)) !== -1,
    fiche.texte.slice(0, 400));
  verifier('son groupe se lit en nombres : terminés sur total, et le pourcentage', /\d+ \/ \d+ terminés · \d+ %/.test(fiche.texte), fiche.texte.slice(0, 300));
  await p.click('#fiche-plan [data-fiche-aller="tableau"]'); await p.waitForTimeout(500);
  const tableauFiche = await p.evaluate(ref => {
    const lignes = [...document.querySelectorAll('#corps-tableau tr')];
    return { n: lignes.length, avec: lignes.filter(tr => tr.textContent.indexOf(ref) !== -1).length };
  }, cibles.accord);
  verifier('« Voir dans le tableau des plans » réduit le tableau à ce plan', tableauFiche.n === 1 && tableauFiche.avec === 1, JSON.stringify(tableauFiche));
  if (cibles.bouge) {
    await p.evaluate(() => window.scrollTo(0, 0));
    await p.fill('#champ-plan', ''); await p.keyboard.type(cibles.bouge.ref); await p.waitForTimeout(250);
    await p.keyboard.press('Enter'); await p.waitForTimeout(400);
    const evts = await p.evaluate(() => [...document.querySelectorAll('#fiche-plan .fiche-evts li')]
      .map(li => li.querySelector('.sem').textContent.trim() + ' ' + li.lastElementChild.textContent.trim()));
    const motAttendu = cibles.bouge.cApres === 'vide' ? 'avancement effacé' : 'passé à « ' + cibles.bouge.vApres + ' »';
    verifier('un plan qui a bougé : la fiche liste son passage, semaine en tête (« S… ' + motAttendu + ' »)',
      evts.some(t => /^S\d{1,2} /.test(t) && t.slice(t.indexOf(' ') + 1) === motAttendu), JSON.stringify([evts, motAttendu]));
  }
  if (cibles.seul) {
    await p.fill('#champ-plan', ''); await p.keyboard.type(cibles.seul); await p.waitForTimeout(250);
    await p.keyboard.press('Enter'); await p.waitForTimeout(400);
    const ficheSeul = await p.evaluate(() => ({
      texte: document.getElementById('fiche-plan').textContent.replace(/\s+/g, ' '),
      lien: !!document.querySelector('#fiche-plan [data-fiche-aller="la"]'),
      frise: !!document.querySelector('#fiche-plan .fiche-frise')
    }));
    verifier('une ligne seulement dans SEE : la fiche le dit, sans frise d’avancement, avec le chemin vers son tableau',
      /ligne de SEE sans plan dans GATES/.test(ficheSeul.texte) && ficheSeul.lien && !ficheSeul.frise, ficheSeul.texte.slice(0, 300));
    await p.click('#fiche-plan [data-fiche-aller="la"]'); await p.waitForTimeout(500);
    const laSeul = await p.evaluate(() => ({ base: !document.getElementById('cadre-seconde').hidden, lignes: document.querySelectorAll('#corps-seconde tr[data-i]').length }));
    verifier('« Voir cette ligne dans SEE » passe au tableau de SEE, cherché sur elle', laSeul.base && laSeul.lignes === 1, JSON.stringify(laSeul));
  }
  await p.evaluate(() => window.scrollTo(0, 0));
  await p.click('#champ-plan'); await p.keyboard.press('Escape'); await p.waitForTimeout(80);
  await p.keyboard.press('Escape'); await p.waitForTimeout(150);
  verifier('Échap, champ vide de suggestions, referme la fiche', await p.evaluate(() => document.getElementById('fiche-plan').hidden));
  await p.fill('#champ-plan', ''); await p.keyboard.press('Escape');
  await p.click('#reinit').catch(() => {}); await p.waitForTimeout(300);

  /* ---------------------------------------------------------------
     L'avancement suivi : définition électrique (HDK AA 011, le FWD) ou
     concept harnais (même bloc). Les comptes attendus sont recomptés dans la
     source brute — les mots de l'extract, pas le classement de la page.
     --------------------------------------------------------------- */
  console.log('\n— Avancement suivi : définition électrique ou concept harnais —');
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); window.scrollTo(0, 0); });
  await p.waitForTimeout(700);
  const brut = await p.evaluate(() => {
    const src = window.__jeuDExemple('HDK');
    const cols = src.colonnes.filter(c => c.cle === 'avancement' || c.cle === src.cleConcept).map(c => c.groupe + ' > ' + c.titre);
    return {
      cols, cleConcept: src.cleConcept, total: src.plans.length,
      defTermine: src.plans.filter(x => x.avancement === 'Terminé').length,
      conceptTermine: src.plans.filter(x => x[src.cleConcept] === 'Terminé').length,
      relevesConcept: src.releves.filter(r => r.plansConcept).length
    };
  });
  verifier('la démonstration suit HDK AA 011 : la définition électrique pour le FWD, le concept harnais à côté',
    JSON.stringify(brut.cols) === JSON.stringify(['HDK AA 011 > Avancement Définition Electrique', 'HDK AA 011 > Avancement Concept Harnais']),
    JSON.stringify(brut.cols));
  const lireSuivi = () => p.evaluate(() => ({
    visible: !document.getElementById('choix-indicateur').hidden,
    presse: (document.querySelector('#choix-indicateur [aria-pressed="true"]') || {}).dataset,
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
    titre: document.getElementById('titre-groupe').textContent,
    ind: window.__indicateur(),
    perimetre: (document.querySelector('#choix-perimetre [aria-pressed="true"]') || {}).textContent || ''
  }));
  const surDef = await lireSuivi();
  verifier('l’interrupteur « Définition électrique | Concept harnais » est là, sur la définition au départ, et ses comptes sont ceux de la colonne',
    surDef.visible && surDef.presse && surDef.presse.indicateur === 'def' && surDef.ind.cle === 'avancement' &&
    surDef.etats[0] === brut.defTermine && surDef.etats.reduce((a, b) => a + b, 0) === brut.total && /^Avancement FWD par /.test(surDef.titre),
    JSON.stringify([surDef, brut.defTermine]));
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(500);
  await p.click('#choix-indicateur button[data-indicateur="concept"]'); await p.waitForTimeout(700);
  const surConcept = await lireSuivi();
  verifier('sur le concept harnais, toute la page le suit : ses terminés, son titre de groupe',
    surConcept.presse && surConcept.presse.indicateur === 'concept' && surConcept.ind.cle === brut.cleConcept &&
    /^Concept harnais par /.test(surConcept.titre), JSON.stringify(surConcept));
  verifier('le périmètre choisi reste posé quand on change d’avancement suivi', /PERSO/i.test(surConcept.perimetre), surConcept.perimetre);
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(500);
  const conceptTout = await lireSuivi();
  verifier('sur tout le contrat, les terminés du concept sont ceux de sa colonne (' + brut.conceptTermine + '), le total inchangé',
    conceptTout.etats[0] === brut.conceptTermine && conceptTout.etats.reduce((a, b) => a + b, 0) === brut.total,
    JSON.stringify([conceptTout.etats, brut.conceptTermine]));
  verifier('sa courbe a son propre historique : les relevés qui ont gardé le concept', conceptTout.ind.releves >= 2 && conceptTout.ind.releves <= brut.relevesConcept + 1,
    JSON.stringify([conceptTout.ind, brut.relevesConcept]));
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(400);
  const lignesConcept = await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length);
  verifier('le filtre « Terminés » du concept montre ses ' + brut.conceptTermine + ' plans dans le tableau', lignesConcept === brut.conceptTermine, String(lignesConcept));
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(300);
  await p.click('#choix-indicateur button[data-indicateur="def"]'); await p.waitForTimeout(700);
  const retourDef = await lireSuivi();
  verifier('revenir à la définition rend exactement les comptes du départ',
    JSON.stringify(retourDef.etats) === JSON.stringify(surDef.etats) && retourDef.ind.cle === 'avancement', JSON.stringify([retourDef.etats, surDef.etats]));
  /* Une source sans colonne de concept : pas d'interrupteur, et la page
     revient d'elle-même sur la définition. */
  const sansConcept = await p.evaluate(async () => {
    const s = window.__jeuDExemple('HDK'); delete s.cleConcept;
    window.__chargerSource(s);
    await new Promise(r => setTimeout(r, 400));
    return { cache: document.getElementById('choix-indicateur').hidden, cle: window.__indicateur().cle };
  });
  verifier('une source sans colonne de concept : pas d’interrupteur, la définition suivie', sansConcept.cache && sansConcept.cle === 'avancement', JSON.stringify(sansConcept));
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); window.scrollTo(0, 0); });
  await p.waitForTimeout(600);

  /* Les phrases des verdicts au singulier : le jeu d'essai n'a aucun lot à
     un seul plan, elles partiraient sans avoir jamais été lues. */
  const phrases1 = await p.evaluate(() => ['accord', 'emission', 'avance', 'manque', 'attente', 'seul'].map(c => window.__phraseLot(c, 1)));
  const phrases2 = await p.evaluate(() => ['accord', 'emission', 'avance', 'manque', 'attente', 'seul'].map(c => window.__phraseLot(c, 2)));
  verifier('au singulier, chaque verdict s’accorde : « terminé », « le connaît pas », « ligne de »',
    phrases1.join(' | ') === 'terminé dans GATES et connu de SEE | dans SEE sous une autre lettre d’indice | dans SEE, mais GATES ne le dit pas terminé | terminé dans GATES, mais SEE ne le connaît pas | pas terminé, et pas encore dans SEE : rien d’anormal | ligne de SEE sans plan dans GATES',
    phrases1.join(' | '));
  verifier('et au pluriel, la forme attendue', /^terminés dans GATES et connus de SEE/.test(phrases2[0]) && /lignes de SEE/.test(phrases2[5]), phrases2.join(' | '));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(700);
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
    const barre = [...document.querySelectorAll('#barre span')].map(s => s.getBoundingClientRect());
    const btns = [...document.querySelectorAll('#etats .etat-btn')].map(b => b.getBoundingClientRect());
    const traits = [...document.querySelectorAll('#filets i')];
    const segs = [...document.querySelectorAll('#barre span')];
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
      presse: document.querySelectorAll('#etats .etat-btn[aria-pressed="true"]').length
    }));
    verifier(`filtrer « ${etat} » ne garde qu'un seul état actif`, r.presse === 1, r.presse + ' actifs');
    verifier(`filtrer « ${etat} » réduit le tableau`, r.lignes > 0 && r.lignes < TOTAL, r.lignes + ' lignes');
    await p.click(`.etat-btn[data-etat="${etat}"]`); await p.waitForTimeout(300);
  }
  verifier('re-cliquer retire le filtre',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));
  await p.click('#etats .etat-btn[data-etat="vide"]'); await p.waitForTimeout(350);
  verifier('« non renseignés » ne laisse que des cellules vides dans la colonne suivie',
    await p.evaluate(() => {
      const cle = window.__indicateur().cle;
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === cle);
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
  /* Plus de « Choisir » ni de panneau de cases : le lecteur consulte, il ne
     compose pas son tableau. Deux vues, et rien entre les deux. */
  section('Deux vues, rien entre les deux');
  const deuxVues = await p.evaluate(() => ({
    choisir: !!document.getElementById('bascule-colonnes') || !!document.getElementById('panneau-colonnes') ||
             !!document.getElementById('compteur-colonnes') || !!document.getElementById('tout-colonnes'),
    boutons: [...document.querySelectorAll('.outils button')].map(b => b.textContent.trim()).filter(t => /choisir/i.test(t)).length,
    cases: document.querySelectorAll('.outils input[type="checkbox"]').length,
    vues: [...document.querySelectorAll('#vue-tableau button')].map(b => b.dataset.vue).join(' '),
    n: document.querySelectorAll('tr.titres th').length
  }));
  verifier('ni bouton « Choisir », ni panneau de colonnes, ni compteur',
    !deuxVues.choisir && deuxVues.boutons === 0 && deuxVues.cases === 0, JSON.stringify(deuxVues));
  verifier('il ne reste que « Toutes les colonnes » et « Vue essentielle »',
    deuxVues.vues === 'toutes essentielle', deuxVues.vues);
  verifier('« toutes » = 137 colonnes', deuxVues.n === COLONNES_TOTAL, String(deuxVues.n));
  await p.click('#vue-tableau button[data-vue="essentielle"]'); await p.waitForTimeout(500);
  const essentielle = await p.evaluate(() => [...document.querySelectorAll('tr.titres th')].map(t => t.dataset.cle));
  verifier('« essentielle » = 9 colonnes, la référence en tête, les deux avancements de HDK AA 011 dedans',
    essentielle.length === 9 && essentielle[0] === 'reference' &&
    essentielle.indexOf('avancement') !== -1 && essentielle.indexOf('avancement_concept_harnais_2') !== -1, essentielle.join(','));
  await p.click('#vue-tableau button[data-vue="toutes"]'); await p.waitForTimeout(500);
  const retourToutes = await p.evaluate(() => ({
    n: document.querySelectorAll('tr.titres th').length,
    titres: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()),
    lignes: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('retour = 137, sans perdre de plan', retourToutes.n === COLONNES_TOTAL && retourToutes.lignes === TOTAL,
    retourToutes.n + ' colonnes, ' + retourToutes.lignes + ' lignes');
  verifier('« Colonne 1 » n\'est dans aucune des deux vues',
    retourToutes.titres.indexOf('Colonne 1') === -1 && essentielle.indexOf('colonne_1') === -1);
  /* Une ancienne preference « cachees » (le panneau d'avant) ne doit plus rien
     masquer : contexte neuf, stockage pose avant le chargement. */
  const ctxAncien = await contexte();
  const pa = await ctxAncien.newPage();
  brancher(pa, 'ancienne pref');
  await pa.addInitScript(() => {
    try {
      localStorage.setItem('suivi-fwd:v1', JSON.stringify({
        cachees: { ata: true, avancement: true, nom_installation: true, rpt: true }
      }));
    } catch (e) { /* sans stockage, rien a ignorer */ }
  });
  await pa.goto(URL); await pa.waitForTimeout(1300);
  const ancien = await pa.evaluate(() => ({
    n: document.querySelectorAll('tr.titres th').length,
    ata: !!document.querySelector('tr.titres th[data-cle="ata"]'),
    avancement: !!document.querySelector('tr.titres th[data-cle="avancement"]'),
    stocke: /"cachees"/.test(localStorage.getItem('suivi-fwd:v1') || '')
  }));
  verifier('une ancienne pref « cachees » est ignoree : les 137 colonnes sont la',
    ancien.n === COLONNES_TOTAL && ancien.ata && ancien.avancement, JSON.stringify(ancien));
  verifier('et la page ne memorise plus de colonnes cachees', !ancien.stocke);
  await ctxAncien.close();

  // =================================================================
  /* Le bloc « Avancement FWD par… » : un filtre sur la colonne de gauche, qui
     ne touche qu'a ce bloc, et sous chaque ligne depliee TOUTES les
     references, en deux paquets titres. */
  section('Bloc par groupe : filtre de la colonne de gauche');
  await reinitialiser(p);
  await p.selectOption('#dim-critique', 'ata'); await p.waitForTimeout(500);
  const avantFiltre = await p.evaluate(() => ({
    champ: !!document.getElementById('filtre-groupe'),
    placeholder: (document.getElementById('filtre-groupe') || {}).placeholder,
    dansTete: !!document.querySelector('.section-tete #filtre-groupe'),
    hauteur: Math.round(document.getElementById('filtre-groupe').getBoundingClientRect().height),
    largeur: Math.round(document.getElementById('filtre-groupe').getBoundingClientRect().width),
    loupe: !!document.querySelector('.recherche-groupe svg'),
    groupes: [...document.querySelectorAll('.critique-ligne')].map(l => l.dataset.groupe),
    compte: document.getElementById('compte-groupes').textContent,
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => e.textContent).join(' '),
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    points: document.querySelectorAll('svg.graphe circle').length
  }));
  verifier('le champ de filtre existe, dans l\'en-tete du bloc, avec sa loupe',
    avantFiltre.champ && avantFiltre.dansTete && avantFiltre.loupe);
  verifier('son invite suit la dimension : « Filtrer les ATA… »',
    avantFiltre.placeholder === 'Filtrer les ATA…', avantFiltre.placeholder);
  verifier('il est compact : ~30 px de haut, ~200 px de large',
    avantFiltre.hauteur >= 26 && avantFiltre.hauteur <= 34 && avantFiltre.largeur >= 180 && avantFiltre.largeur <= 220,
    avantFiltre.hauteur + ' × ' + avantFiltre.largeur);
  verifier('sans filtre, pas de compte', avantFiltre.compte === '' && avantFiltre.groupes.length === 10,
    avantFiltre.compte + ' / ' + avantFiltre.groupes.length);
  await p.fill('#filtre-groupe', '2'); await p.waitForTimeout(450);
  const filtre2 = await p.evaluate(() => ({
    groupes: [...document.querySelectorAll('.critique-ligne')].map(l => l.dataset.groupe),
    compte: document.getElementById('compte-groupes').textContent,
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => e.textContent).join(' '),
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    points: document.querySelectorAll('svg.graphe circle').length,
    jetons: document.querySelectorAll('.jeton').length
  }));
  verifier('filtrer « 2 » ne garde que les ATA qui contiennent 2',
    filtre2.groupes.length > 0 && filtre2.groupes.length < 10 && filtre2.groupes.every(g => /2/.test(g)) &&
    avantFiltre.groupes.filter(g => /2/.test(g)).length === filtre2.groupes.length, filtre2.groupes.join(','));
  verifier('le compte dit « n sur m »',
    filtre2.compte === filtre2.groupes.length + ' sur 10', filtre2.compte);
  verifier('sans toucher au reste de la page : barre, tableau, courbe, bandeau des filtres',
    filtre2.etats === avantFiltre.etats && filtre2.lignes === TOTAL && filtre2.points === avantFiltre.points &&
    filtre2.jetons === 0, JSON.stringify(filtre2));
  await p.fill('#filtre-groupe', 'zzz'); await p.waitForTimeout(450);
  verifier('un filtre qui ne trouve rien le dit, sans casser l\'en-tete',
    await p.evaluate(() => document.querySelectorAll('.critique-ligne').length === 0 &&
      /Aucun groupe ne contient/.test(document.getElementById('zone-critique').textContent) &&
      !!document.querySelector('.critique-tete') &&
      document.getElementById('compte-groupes').textContent === '0 sur 10'));
  await p.fill('#filtre-groupe', '2'); await p.waitForTimeout(450);
  await p.focus('#filtre-groupe'); await p.keyboard.press('Escape'); await p.waitForTimeout(400);
  const echap = await p.evaluate(() => ({
    valeur: document.getElementById('filtre-groupe').value,
    groupes: document.querySelectorAll('.critique-ligne').length,
    compte: document.getElementById('compte-groupes').textContent
  }));
  verifier('Echap vide le champ et rend les dix lignes',
    echap.valeur === '' && echap.groupes === 10 && echap.compte === '', JSON.stringify(echap));
  await p.fill('#filtre-groupe', '3'); await p.waitForTimeout(450);
  await p.selectOption('#dim-critique', 'cc'); await p.waitForTimeout(500);
  const apresDim = await p.evaluate(() => ({
    valeur: document.getElementById('filtre-groupe').value,
    placeholder: document.getElementById('filtre-groupe').placeholder,
    compte: document.getElementById('compte-groupes').textContent,
    groupes: document.querySelectorAll('.critique-ligne').length
  }));
  verifier('changer de dimension vide le filtre et change l\'invite',
    apresDim.valeur === '' && apresDim.compte === '' && apresDim.placeholder === 'Filtrer les CC…' && apresDim.groupes > 0,
    JSON.stringify(apresDim));
  await p.fill('#filtre-groupe', '3'); await p.waitForTimeout(700);
  verifier('le filtre n\'est pas memorise',
    await p.evaluate(() => !/filtreGroupe/.test(localStorage.getItem('suivi-fwd:v1') || '')));
  await p.fill('#filtre-groupe', ''); await p.waitForTimeout(300);
  await p.selectOption('#dim-critique', 'ata'); await p.waitForTimeout(500);

  section('Bloc par groupe : la liste des UD est complete');
  const grosAta = await p.evaluate(() => {
    const l = [...document.querySelectorAll('.critique-ligne')];
    l.sort((a, b) => +b.querySelector('.critique-total').textContent - +a.querySelector('.critique-total').textContent);
    return { groupe: l[0].dataset.groupe, total: +l[0].querySelector('.critique-total').textContent };
  });
  await p.click(`.critique-ligne[data-groupe="${grosAta.groupe}"]`); await p.waitForTimeout(600);
  const liste = await p.evaluate(() => {
    const refs = [...document.querySelectorAll('.jeton-ud')];
    const titres = [...document.querySelectorAll('.groupe-refs .sous-titre')].map(t => t.textContent.replace(/\s+/g, ' ').trim());
    const paquets = [...document.querySelectorAll('.groupe-refs .sous-groupe')].map(sg => ({
      titre: sg.querySelector('.sous-titre').textContent,
      refs: [...sg.querySelectorAll('.jeton-ud')].map(b => ({
        ref: b.dataset.ud, etat: (b.getAttribute('title') || '').split(' — ')[0]
      }))
    }));
    const zone = document.getElementById('zone-critique');
    return {
      jetons: refs.length, ud: refs.filter(b => b.dataset.ud).length,
      autres: /autres/.test(document.querySelector('.groupe-refs').textContent),
      titres, paquets,
      entete: document.querySelector('.groupe-refs .entete').textContent,
      pastilles: refs.every(b => b.querySelector('.pastille')),
      mono: refs.every(b => /Mono|mono/.test(getComputedStyle(b).fontFamily)),
      dedans: refs.every(b => b.getBoundingClientRect().right <= zone.getBoundingClientRect().right + 1),
      defile: zone.scrollHeight > zone.clientHeight && getComputedStyle(zone).overflowY === 'auto'
    };
  });
  const ETATS_RESTANTS = ['À faire', 'Non renseigné', 'En cours'];
  const rangEtat = e => ETATS_RESTANTS.indexOf(e);
  const numRef = r => Number(r.replace(/\D/g, ''));
  const bienRange = (refs) => refs.every((x, i) => i === 0 ||
    rangEtat(refs[i - 1].etat) < rangEtat(x.etat) ||
    (rangEtat(refs[i - 1].etat) === rangEtat(x.etat) && refs[i - 1].ref.localeCompare(x.ref, 'fr', { numeric: true }) <= 0));
  verifier('deplier un groupe montre TOUTES ses references : autant de jetons que de plans',
    liste.ud === grosAta.total && liste.jetons === liste.ud, liste.ud + ' / ' + grosAta.total);
  verifier('plus aucun « et N autres »', !liste.autres);
  verifier('deux sous-titres, « Pas encore termines (n) » puis « Termines (n) », avec les bons comptes',
    liste.paquets.length === 2 && /^Pas encore terminés\s*\((\d+)\)$/.test(liste.titres[0]) && /^Terminés\s*\((\d+)\)$/.test(liste.titres[1]) &&
    +liste.titres[0].match(/\((\d+)\)/)[1] === liste.paquets[0].refs.length &&
    +liste.titres[1].match(/\((\d+)\)/)[1] === liste.paquets[1].refs.length &&
    liste.paquets[0].refs.length + liste.paquets[1].refs.length === grosAta.total,
    JSON.stringify(liste.titres));
  verifier('le premier paquet : a faire, non renseignes, en cours — dans cet ordre, puis par reference',
    liste.paquets[0].refs.every(r => rangEtat(r.etat) !== -1) && bienRange(liste.paquets[0].refs),
    JSON.stringify(liste.paquets[0].refs.slice(0, 3)));
  verifier('le second : rien que des termines, par reference',
    liste.paquets[1].refs.every(r => r.etat === 'Terminé') &&
    liste.paquets[1].refs.every((r, i) => i === 0 || liste.paquets[1].refs[i - 1].ref.localeCompare(r.ref, 'fr', { numeric: true }) <= 0));
  verifier('l\'en-tete dit combien et invite a cliquer une reference',
    new RegExp('^' + grosAta.total + ' plans · ' + liste.paquets[0].refs.length + ' pas encore terminés').test(liste.entete.trim()) &&
    /cliquez une référence pour la retrouver dans le tableau/.test(liste.entete), liste.entete.trim());
  verifier('des jetons compacts : pastille + reference en mono, aucun ne deborde',
    liste.pastilles && liste.mono && liste.dedans);
  verifier('le bloc defile plutot que de pousser la page', liste.defile);
  const refJeton = liste.paquets[1].refs[0].ref;
  await p.click(`.jeton-ud[data-ud="${refJeton}"]`); await p.waitForTimeout(600);
  verifier('un clic sur un jeton filtre le tableau sur ce plan',
    await p.evaluate(r => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
      const trs = document.querySelectorAll('#corps-tableau tr');
      return trs.length === 1 && trs[0].children[i].textContent.trim() === r &&
        [...document.querySelectorAll('.jeton')].some(j => j.textContent.indexOf(r) !== -1);
    }, refJeton), refJeton);
  /* Deux cents references d'un coup : une source ou tous les plans partagent
     le meme ATA. La liste doit rester lisible et defilable. */
  await p.evaluate(() => {
    const src = window.__jeuDExemple('HDK');
    src.plans.forEach(p => { p.ata = '21'; });
    window.__chargerSource(src);
  });
  await p.waitForTimeout(500);
  await p.click('.critique-ligne[data-groupe="21"]'); await p.waitForTimeout(700);
  const deuxCents = await p.evaluate(() => {
    const zone = document.getElementById('zone-critique');
    const refs = [...document.querySelectorAll('.jeton-ud')];
    const derniere = refs[refs.length - 1].getBoundingClientRect();
    return {
      jetons: refs.length, plans: document.querySelectorAll('#corps-tableau tr').length,
      defile: zone.scrollHeight > zone.clientHeight,
      hauteur: Math.round(zone.getBoundingClientRect().height),
      dedans: refs.every(b => b.getBoundingClientRect().right <= zone.getBoundingClientRect().right + 1),
      lignes: new Set(refs.map(b => Math.round(b.getBoundingClientRect().top))).size,
      dernierAtteignable: derniere.top - zone.getBoundingClientRect().top < zone.scrollHeight
    };
  });
  verifier('640 references dans un seul groupe : toutes la, en grille, dans un bloc qui defile',
    deuxCents.jetons === TOTAL && deuxCents.defile && deuxCents.dedans && deuxCents.lignes > 20 &&
    deuxCents.hauteur <= 460 && deuxCents.dernierAtteignable, JSON.stringify(deuxCents));
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); });
  await p.waitForTimeout(500);
  await reinitialiser(p);

  // =================================================================
  section('Graphique : zoom, déplacement, extrêmes');
  /* Le cadrage d'ouverture suit aujourd'hui et les jalons (38 semaines sur
     HDK, dont l'historique court est tout entier dans le cadre) : « 1 an »
     l'élargit à 52 semaines. */
  const zoom0 = await p.evaluate(() => document.querySelectorAll('.zone-clic').length);
  await p.click('.segmente button[data-span="52"]'); await p.waitForTimeout(350);
  const zoom1 = await p.evaluate(() => ({
    n: document.querySelectorAll('.zone-clic').length,
    presse: document.querySelector('.segmente button[data-span="52"]').getAttribute('aria-pressed')
  }));
  verifier('le bouton « 1 an » cadre 52 semaines et se marque pressé',
    zoom1.n === 52 && zoom1.presse === 'true', zoom0 + ' → ' + JSON.stringify(zoom1));
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
  /* Un clic net, dans la frise comme sur une semaine, ne fait rien : l'outil
     se consulte, rien ne se pose sur le graphique. */
  const avantClic = await p.evaluate(() => ({
    jalons: document.querySelectorAll('.jalon').length, semaine: null
  }));
  avantClic.semaine = await derniereSemaine();
  await p.mouse.click(cadre.x + cadre.width * 0.75, cadre.y + cadre.height * 0.05);
  await p.waitForTimeout(350);
  const apresClic = { jalons: await p.evaluate(() => document.querySelectorAll('.jalon').length), semaine: await derniereSemaine() };
  verifier('un clic net dans la frise ne pose rien et ne déplace rien',
    apresClic.jalons === avantClic.jalons && apresClic.semaine === avantClic.semaine, JSON.stringify(apresClic));
  /* Un glissement parti d'un marqueur de jalon déplace la fenêtre comme
     partout ailleurs : il n'y a plus de poignée qui capte le geste. (Le
     marqueur, pas le texte : un texte peut être masqué faute de place.) */
  const avantEtiquette = await derniereSemaine();
  const etiquetteEl = await p.$('.jalon-marque');
  if (etiquetteEl) {
    const bp = await etiquetteEl.boundingBox();
    await p.mouse.move(bp.x + bp.width / 2, bp.y + bp.height / 2);
    await p.mouse.down();
    for (let i = 1; i <= 8; i++) await p.mouse.move(bp.x + bp.width / 2 - i * 30, bp.y + bp.height / 2);
    await p.mouse.up(); await p.waitForTimeout(400);
  }
  verifier('glisser depuis un marqueur de jalon déplace la fenêtre, pas le jalon',
    !!etiquetteEl && (await derniereSemaine()) !== avantEtiquette, avantEtiquette + ' → ' + (await derniereSemaine()));
  await p.click('.segmente button[data-span="26"]'); await p.waitForTimeout(300);

  // =================================================================
  section('Jalons fixes');
  /* Les jalons viennent de la source, et d'elle seule : cinq par contrat en
     démonstration — ceux du programme. Rien ne permet d'en poser, d'en
     déplacer ni d'en retirer — l'outil se consulte. */
  await p.click('.segmente button[data-span="0"]'); await p.waitForTimeout(400);
  const fixes = await p.evaluate(() => ({
    source: window.__jeuDExemple('HDK').jalons.length,
    dessines: document.querySelectorAll('.jalon').length,
    textes: [...document.querySelectorAll('.jalon-texte')].map(t => t.textContent),
    poignees: document.querySelectorAll('.jalon-poignee, .jalon-supp, [data-glisse-jalon]').length,
    formulaire: !!(document.getElementById('saisie-jalon') || document.getElementById('champ-jalon') ||
                   document.querySelector('form.saisie-jalon')),
    boutons: document.querySelectorAll('svg.graphe [role="button"]').length,
    curseur: getComputedStyle(document.getElementById('cadre-graphe')).cursor,
    indice: document.querySelector('.commandes-graphe .indice').textContent,
    pont: !(window.SUIVI_FWD_API && window.SUIVI_FWD_API.sauverJalons)
  }));
  verifier('la démonstration a cinq jalons — ceux du programme, le solde FWD en tête',
    fixes.source === 5 && fixes.textes[0] === 'Solde FWD', JSON.stringify([fixes.source, fixes.textes]));
  verifier('les cinq sont dessinés, avec leur texte',
    fixes.dessines === 5 && fixes.textes.length === 5 && fixes.textes.every(t => t.trim().length > 0),
    JSON.stringify(fixes.textes));
  verifier('aucune poignée, croix ni formulaire dans le DOM', fixes.poignees === 0 && !fixes.formulaire);
  /* La légende des jalons, sous celle du graphique : chaque numéro en clair.
     La survoler éclaire le jalon sur le graphique, révèle son texte masqué
     par-dessus les voisins, et tout reprend sa place ensuite. */
  const legendeJ = await p.evaluate(() => ({
    visible: document.getElementById('legende-jalons').offsetParent !== null,
    mot: (document.querySelector('#legende-jalons .legende-jalons-mot') || {}).textContent,
    entrees: [...document.querySelectorAll('#legende-jalons .legende-jalon')].map(e => ({
      idx: e.dataset.jalon, num: e.querySelector('.num').textContent, mot: e.querySelector('.mot').textContent,
      quand: e.querySelector('.quand').textContent, critique: e.classList.contains('critique'), hors: e.classList.contains('hors-perimetre'),
      focusable: e.tabIndex === 0 })),
    critiquesDessin: [...document.querySelectorAll('svg.graphe .jalon.critique')].map(g => g.dataset.jalon).join(',')
  }));
  verifier('sous le graphique, la légende des jalons : « Jalons », puis chaque numéro, son texte, sa semaine et son périmètre, atteignable au clavier',
    legendeJ.visible && legendeJ.mot === 'Jalons' && legendeJ.entrees.length === 5 &&
    legendeJ.entrees.every((e, i) => e.num === String(i + 1) && e.idx === String(i) && e.mot.length > 0 && /^S\d{1,2} · \S+ \d{4}/.test(e.quand) && e.focusable && !e.hors) &&
    legendeJ.entrees[0].mot === 'Solde FWD' && legendeJ.entrees[1].quand === 'S2 · janv. 2027 · BASE/OPTION', JSON.stringify(legendeJ));
  const grilleJ = await p.evaluate(() => {
    const g = document.querySelector('#legende-jalons .legende-jalons-grille');
    if (!g) return null;
    const c = getComputedStyle(g), cases = [...g.querySelectorAll('.legende-jalon')].map(e => Math.round(e.getBoundingClientRect().left));
    const lignes = [...new Set([...g.querySelectorAll('.legende-jalon')].map(e => Math.round(e.getBoundingClientRect().top)))];
    const une = g.querySelector('.legende-jalon');
    const r = el => el.getBoundingClientRect();
    return { affichage: c.display, colonnes: c.gridTemplateColumns.split(' ').length, distinctes: new Set(cases).size, lignes: lignes.length,
             mot: (document.querySelector('#legende-jalons .legende-jalons-mot') || {}).textContent,
             motBloc: getComputedStyle(document.querySelector('#legende-jalons .legende-jalons-mot')).display,
             caseGrille: getComputedStyle(une).display,
             quandDessous: Math.round(r(une.querySelector('.quand')).top) > Math.round(r(une.querySelector('.mot')).top),
             memeColonne: Math.abs(Math.round(r(une.querySelector('.quand')).left) - Math.round(r(une.querySelector('.mot')).left)) <= 1 };
  });
  verifier('la légende des jalons est une grille de colonnes, pas une ligne où tout se touche : le mot « Jalons » sur sa ligne, puis une case par jalon',
    !!grilleJ && grilleJ.affichage === 'grid' && grilleJ.colonnes >= 2 && grilleJ.distinctes >= 2 &&
    grilleJ.mot === 'Jalons' && grilleJ.motBloc === 'block', JSON.stringify(grilleJ));
  verifier('et dans chaque case, la semaine se lit sous le nom, alignée avec lui — pas collée à côté',
    !!grilleJ && grilleJ.caseGrille === 'grid' && grilleJ.quandDessous && grilleJ.memeColonne, JSON.stringify(grilleJ));
  verifier('l\'échéance manquée est rouge dans la légende comme sur le graphique, et nulle part ailleurs',
    legendeJ.entrees.filter(e => e.critique).map(e => e.idx).join(',') === legendeJ.critiquesDessin, JSON.stringify([legendeJ.entrees.map(e => e.critique), legendeJ.critiquesDessin]));
  await p.hover('#legende-jalons .legende-jalon[data-jalon="1"]'); await p.waitForTimeout(250);
  const survolJ = await p.evaluate(() => {
    const svg = document.querySelector('svg.graphe'), g = svg.querySelector('.jalon[data-jalon="1"]');
    const groupes = [...svg.querySelectorAll('.jalon[data-jalon]')];
    return { survole: g.classList.contains('survole'), texte: getComputedStyle(g.querySelector('.jalon-texte')).display,
             dessus: groupes[groupes.length - 1] === g, trait: parseFloat(getComputedStyle(g.querySelector('line')).strokeWidth) };
  });
  await p.mouse.move(5, 5); await p.waitForTimeout(250);
  const apresSurvolJ = await p.evaluate(() => ({
    ordre: [...document.querySelectorAll('svg.graphe .jalon[data-jalon]')].map(g => g.dataset.jalon).join(','),
    survole: !!document.querySelector('svg.graphe .jalon.survole'),
    masques: document.querySelectorAll('svg.graphe .jalon-texte.masque').length
  }));
  verifier('survoler un jalon dans la légende l\'éclaire sur le graphique — trait épaissi, texte révélé, passé au-dessus des voisins — et tout reprend sa place ensuite',
    survolJ.survole && survolJ.texte === 'block' && survolJ.dessus && survolJ.trait >= 2 &&
    !apresSurvolJ.survole && apresSurvolJ.ordre === '0,1,2,3,4', JSON.stringify([survolJ, apresSurvolJ]));
  /* Un zoom serré laisse des jalons hors de la fenêtre : la légende les garde,
     en retrait, et le dit. */
  await p.click('.segmente button[data-span="13"]'); await p.waitForTimeout(400);
  const fenetreJ = await p.evaluate(() => ({
    dessines: document.querySelectorAll('svg.graphe .jalon[data-jalon]').length,
    legende: document.querySelectorAll('#legende-jalons .legende-jalon').length,
    horsFenetre: [...document.querySelectorAll('#legende-jalons .legende-jalon.hors-fenetre')].map(e => e.title),
    police: document.fonts ? document.fonts.check('500 11.5px "IBM Plex Sans"') : null
  }));
  verifier('à trois mois, les jalons sortis de la fenêtre restent dans la légende, en retrait, avec « hors de la fenêtre affichée » dans leur bulle',
    fenetreJ.legende === 5 && fenetreJ.horsFenetre.length === 5 - fenetreJ.dessines && fenetreJ.horsFenetre.length > 0 &&
    fenetreJ.horsFenetre.every(t => / — hors de la fenêtre affichée$/.test(t)), JSON.stringify(fenetreJ));
  verifier('la batterie dessine avec la vraie police (IBM Plex Sans chargée en local)', fenetreJ.police === true, String(fenetreJ.police));
  await p.click('.segmente button[data-span="0"]'); await p.waitForTimeout(400);
  verifier('aucun bouton dans le graphique', fixes.boutons === 0, String(fixes.boutons));
  verifier('le curseur du cadre reste la main du panoramique', fixes.curseur === 'grab', fixes.curseur);
  verifier('l\'indice ne promet plus de poser un jalon', !/poser/.test(fixes.indice), fixes.indice);
  verifier('aucun pont de sauvegarde des jalons', fixes.pont);

  /* Un jalon peut porter un périmètre : sous ce périmètre, il fait
     l'échéance ; sous l'autre, il est dessiné en retrait et ne compte pas.
     Sans périmètre choisi (« Tout »), tous comptent. La démonstration en
     porte quatre sur cinq (Base / Perso), comme la configuration livrée. */
  const per = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    return { avec: s.jalons.filter(j => j.perimetre).length, valeurs: [...new Set(s.jalons.map(j => j.perimetre || ''))].sort() };
  });
  verifier('la démonstration porte quatre jalons à périmètre, Base et Perso, et un pour tous',
    per.avec === 4 && per.valeurs.join('|') === '|BASE/OPTION|PERSO', JSON.stringify(per));
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.jalons = [
      { semaine: s.jalons[0].semaine, texte: 'Base seul', perimetre: 'BASE/OPTION' },
      { semaine: s.jalons[1].semaine, texte: 'Perso seul', perimetre: 'perso' },
      { semaine: s.jalons[2].semaine, texte: 'Tous' }
    ];
    window.__chargerSource(s);
  });
  await p.waitForTimeout(500);
  const lireEcheance = () => p.evaluate(() => ({
    prochain: window.__prochainJalon() && window.__prochainJalon().texte,
    entete: (document.querySelector('.critique-tete button[data-trig="tension"]') || {}).title || '',
    zone: document.getElementById('zone-critique').getAttribute('data-jalon'),
    retrait: [...document.querySelectorAll('.jalon.hors-perimetre .jalon-texte')].map(t => t.textContent),
    legende: document.getElementById('legende').textContent,
    aucun: [...document.querySelectorAll('svg.graphe text')].filter(t => /Aucun jalon/.test(t.textContent)).map(t => t.textContent).join('')
  }));
  const eTout = await lireEcheance();
  verifier('sur « Tout », le premier jalon à venir fait l\'échéance, périmètre ou pas, et l\'en-tête le nomme',
    eTout.prochain === 'Base seul' && /«\u00a0Base seul\u00a0» \(2026-S51\)/.test(eTout.entete) && eTout.zone === 'Base seul' && eTout.retrait.length === 0 &&
    /requis pour «\u00a0Base seul\u00a0»/.test(eTout.legende), JSON.stringify(eTout));
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const ePerso = await lireEcheance();
  verifier('sous PERSO, l\'échéance saute au jalon Perso (casse indifférente) ; le jalon Base est dessiné en retrait',
    ePerso.prochain === 'Perso seul' && /«\u00a0Perso seul\u00a0» \(2027-S02\)/.test(ePerso.entete) && ePerso.zone === 'Perso seul' &&
    ePerso.retrait.join('|') === 'Base seul' && /requis pour «\u00a0Perso seul\u00a0»/.test(ePerso.legende) && ePerso.aucun === '',
    JSON.stringify(ePerso));
  const retraitPerso = await p.evaluate(() => ({
    legende: [...document.querySelectorAll('#legende-jalons .legende-jalon')].map(e => (e.classList.contains('hors-perimetre') ? 'hors' : 'dans') + ':' + e.querySelector('.num').textContent).join(' '),
    numeroLisible: [...document.querySelectorAll('svg.graphe .jalon.hors-perimetre')].every(g =>
      getComputedStyle(g.querySelector('.jalon-num')).fill !== getComputedStyle(g.querySelector('.jalon-marque')).fill),
    traitEstompe: [...document.querySelectorAll('svg.graphe .jalon.hors-perimetre line')].every(l => parseFloat(getComputedStyle(l).opacity) < 0.6)
  }));
  verifier('la légende suit le périmètre : le jalon Base en retrait, son numéro gardé et lisible dans un marqueur creux, son trait estompé',
    retraitPerso.legende === 'hors:1 dans:2 dans:3' && retraitPerso.numeroLisible && retraitPerso.traitEstompe, JSON.stringify(retraitPerso));
  await p.click('#choix-perimetre button[data-perimetre="BASE/OPTION"]'); await p.waitForTimeout(700);
  const eBase = await lireEcheance();
  verifier('sous BASE/OPTION, l\'échéance est le jalon Base ; le jalon Perso est en retrait, « Tous » ne l\'est pas',
    eBase.prochain === 'Base seul' && eBase.retrait.join('|') === 'Perso seul', JSON.stringify(eBase));
  const bulle = await p.evaluate(() => (document.querySelector('.jalon.hors-perimetre title') || {}).textContent || '');
  verifier('la bulle d\'un jalon en retrait dit son périmètre et qu\'il ne compte pas ici',
    /périmètre perso/.test(bulle) && /ne compte pas ici/.test(bulle), bulle);
  /* Un jalon sans périmètre compte sous tout périmètre : placé avant celui
     du périmètre choisi, c'est lui l'échéance. Et deux jalons la même
     semaine, dont un hors périmètre : seul celui qui compte peut être peint
     en rouge. */
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.jalons = [
      { semaine: s.jalons[0].semaine, texte: 'Base seul', perimetre: 'BASE/OPTION' },
      { semaine: s.jalons[1].semaine, texte: 'Tous' },
      { semaine: s.jalons[1].semaine, texte: 'Perso même semaine', perimetre: 'PERSO' },
      { semaine: s.jalons[2].semaine, texte: 'Perso seul', perimetre: 'PERSO' }
    ];
    window.__chargerSource(s);
  });
  await p.waitForTimeout(500);
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const eTous = await lireEcheance();
  verifier('sous PERSO, un jalon sans périmètre placé avant fait l\'échéance : « Tous »',
    eTous.prochain === 'Tous' && eTous.zone === 'Tous' && eTous.retrait.join('|') === 'Base seul', JSON.stringify(eTous));
  await p.click('#choix-perimetre button[data-perimetre="BASE/OPTION"]'); await p.waitForTimeout(700);
  const rouge = await p.evaluate(() => ({
    prochain: window.__prochainJalon() && window.__prochainJalon().texte,
    critiques: [...document.querySelectorAll('.jalon')].filter(g => /alerte/.test(g.querySelector('line').getAttribute('stroke'))).map(g => g.querySelector('.jalon-texte').textContent),
    retrait: [...document.querySelectorAll('.jalon.hors-perimetre .jalon-texte')].map(t => t.textContent)
  }));
  verifier('sous BASE/OPTION, le jalon Perso de la même semaine que « Tous » est en retrait, jamais peint en rouge',
    rouge.prochain === 'Base seul' && rouge.retrait.join('|') === 'Perso même semaine|Perso seul' && rouge.critiques.indexOf('Perso même semaine') === -1,
    JSON.stringify(rouge));
  /* Sous un périmètre sans jalon à venir : la colonne redevient « rythme
     actuel », et le graphique dit que c'est dans ce périmètre qu'il n'y a
     rien — le jalon de l'autre reste dessiné. */
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.jalons = [{ semaine: s.jalons[0].semaine, texte: 'Base seul', perimetre: 'BASE/OPTION' }];
    window.__chargerSource(s);
  });
  await p.waitForTimeout(500);
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const eRien = await lireEcheance();
  verifier('sous PERSO sans jalon à venir : « rythme actuel », et le graphique dit « dans ce périmètre »',
    eRien.prochain === null && /Plans terminés par semaine/.test(eRien.entete) && eRien.zone === '' &&
    eRien.retrait.join('|') === 'Base seul' && eRien.aucun === 'Aucun jalon à venir dans ce périmètre',
    JSON.stringify(eRien));
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(500);
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(500);
  await p.click('.segmente button[data-span="0"]'); await p.waitForTimeout(400);
  /* Un clic sur une semaine, à venir ou passée, ne pose rien. */
  const zonesClic = await p.$$('.zone-clic');
  for (const k of [5, Math.round(zonesClic.length / 2)]) {
    const bz = await zonesClic[Math.max(0, zonesClic.length - k)].boundingBox();
    await p.mouse.move(bz.x + bz.width / 2, bz.y + bz.height / 2);
    await p.mouse.down(); await p.mouse.up(); await p.waitForTimeout(300);
  }
  await p.keyboard.press('Enter'); await p.keyboard.press('Delete'); await p.waitForTimeout(300);
  verifier('un clic sur une semaine ne pose rien, Entrée et Suppr ne changent rien',
    await p.evaluate(() => document.querySelectorAll('.jalon').length === 5 && !document.getElementById('champ-jalon')));
  /* Le dessin des jalons : un marqueur numéroté par jalon, sa bulle et son
     aria ; les textes ne s'écrivent que s'ils tiennent — donc rien ne se
     chevauche jamais, ni deux marqueurs, ni deux textes, ni un texte et un
     marqueur. */
  const dessinJ = await p.evaluate(() => {
    const rect = el => el.getBoundingClientRect();
    const croise = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
    const groupes = [...document.querySelectorAll('svg.graphe .jalon[data-jalon]')];
    const marques = groupes.map(g => rect(g.querySelector('.jalon-marque')));
    const textes = groupes.map(g => g.querySelector('.jalon-texte')).filter(t => !t.classList.contains('masque')).map(rect);
    const chev = [];
    for (let i = 0; i < marques.length; i++) for (let j = i + 1; j < marques.length; j++) if (croise(marques[i], marques[j])) chev.push('marques ' + i + '/' + j);
    for (let i = 0; i < textes.length; i++) for (let j = i + 1; j < textes.length; j++) if (croise(textes[i], textes[j])) chev.push('textes ' + i + '/' + j);
    textes.forEach((t, i) => marques.forEach((m, j) => { if (croise(t, m)) chev.push('texte ' + i + ' / marque ' + j); }));
    const rangs = new Set(groupes.map(g => g.querySelector('.jalon-marque').getAttribute('cy')));
    return { n: groupes.length, nums: groupes.map(g => g.querySelector('.jalon-num').textContent).join(','), visibles: textes.length, chev, rangs: rangs.size,
             titres: groupes.map(g => g.querySelector('title').textContent), aria: groupes.map(g => g.getAttribute('aria-label')) };
  });
  verifier('cinq marqueurs numérotés 1 à 5, dans l\'ordre des jalons, chacun avec sa bulle « N — texte — semaine » et son aria « Jalon N, … »',
    dessinJ.n === 5 && dessinJ.nums === '1,2,3,4,5' && dessinJ.titres.every((t, i) => new RegExp('^' + (i + 1) + ' — .+ — \\d{4}-S\\d{2}').test(t)) &&
    dessinJ.aria.every((a, i) => new RegExp('^Jalon ' + (i + 1) + ', ').test(a)), JSON.stringify([dessinJ.nums, dessinJ.titres]));
  verifier('les cinq numéros sur une seule rangée, sans étage, aucun ne touche l’autre, et aucun nom écrit sur le dessin — la légende les porte',
    dessinJ.chev.length === 0 && dessinJ.visibles === 0 && dessinJ.rangs === 1, JSON.stringify([dessinJ.chev, dessinJ.visibles, dessinJ.rangs]));
  /* Le panoramique et la molette marchent toujours, jalons compris. */
  const avantPan = await derniereSemaine();
  await balayer(0.5, -1);
  verifier('le panoramique fonctionne toujours', (await derniereSemaine()) !== avantPan);
  const avantMolette = await p.evaluate(() => document.querySelectorAll('.zone-clic').length);
  await p.mouse.move(cadre.x + cadre.width * 0.5, cadre.y + cadre.height * 0.5);
  await p.mouse.wheel(0, -300); await p.waitForTimeout(300);
  verifier('la molette fonctionne toujours',
    (await p.evaluate(() => document.querySelectorAll('.zone-clic').length)) !== avantMolette);
  /* Une configuration hostile : balise, 400 caractères, texte vide, semaine
     illisible. Rien ne s'exécute, rien ne déborde, l'illisible est écarté. */
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.jalons = [
      { semaine: s.jalons[0].semaine, texte: '<img src=x onerror="window.__xss=1">' },
      { semaine: s.jalons[1].semaine, texte: 'X'.repeat(400) },
      { semaine: s.jalons[2].semaine, texte: '' },
      { semaine: 'nawak', texte: 'ignoré' },
      null
    ];
    window.__chargerSource(s);
  });
  await p.click('.segmente button[data-span="0"]'); await p.waitForTimeout(400);
  const hostile = await p.evaluate(() => ({
    xss: typeof window.__xss === 'undefined' && !document.querySelector('.jalon img'),
    balise: [...document.querySelectorAll('.jalon-texte')].some(t => /<img/.test(t.textContent)),
    longueurs: [...document.querySelectorAll('.jalon-texte')].map(t => t.textContent.length),
    deborde: document.documentElement.scrollWidth > window.innerWidth + 2,
    largeur: document.documentElement.scrollWidth + ' vs ' + window.innerWidth,
    n: document.querySelectorAll('.jalon').length
  }));
  verifier('un texte de jalon avec balise ne s\'exécute pas et s\'affiche tel quel', hostile.xss && hostile.balise);
  verifier('un jalon de 400 caractères est coupé et ne fait pas déborder la page',
    !hostile.deborde && hostile.longueurs.every(l => l <= 60), hostile.largeur + ' ' + JSON.stringify(hostile.longueurs));
  verifier('un jalon sans texte reçoit un libellé, une semaine illisible est écartée',
    hostile.n === 3 && hostile.longueurs.every(l => l > 0), String(hostile.n));
  /* Sans jalon à venir, le bloc par groupe bascule en « rythme actuel ». */
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); s.jalons = []; window.__chargerSource(s); });
  await p.waitForTimeout(400);
  verifier('sans jalon, aucun n\'est dessiné et le graphique tient toujours debout',
    await p.evaluate(() => document.querySelectorAll('.jalon').length === 0 && document.querySelectorAll('.zone-clic').length > 0));
  verifier('sans jalon, le bloc par groupe bascule en mode « rythme actuel »',
    await p.evaluate(() => document.getElementById('zone-critique').classList.contains('sans-jalon')));
  verifier('sans jalon, le graphique le dit sans inviter à en poser',
    await p.evaluate(() => {
      const t = [...document.querySelectorAll('svg.graphe text')].map(x => x.textContent).find(x => /Aucun jalon/.test(x));
      return !!t && !/cliquez/.test(t);
    }));
  // Retour à la source de démonstration, avec ses cinq jalons.
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(400);

  // =================================================================
  section('Bloc par groupe : colonnes triables');
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
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => e.textContent.trim())
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
    await p.click('#etats .etat-btn[data-etat="encours"]');
    await p.click('.critique-ligne >> nth=0').catch(() => {});
  }
  await p.waitForTimeout(600);
  verifier('24 clics enchaînés laissent la page cohérente',
    await p.evaluate(() => document.querySelectorAll('.critique-ligne').length > 0 &&
      document.getElementById('compte').textContent.length > 0));
  await reinitialiser(p);
  verifier('« tout réinitialiser » remet tout d\'aplomb',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t &&
      document.querySelectorAll('#etats .etat-btn[aria-pressed="true"]').length === 0, TOTAL));

  // =================================================================
  // =================================================================
  /* Ce que trois relecteurs ont trouvé après le lot du débrief, et ce qui a
     été corrigé. Chaque test reproduit d'abord la situation qui cassait. */
  section('Relecture : les constats corrigés tiennent');
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await reinitialiser(p);

  // Le mode « Exemple » ne racontait que des « passés en terminé ».
  await basculerMode(p, 'exemple'); await p.waitForTimeout(900);
  const lotsExemple = await p.evaluate(() => (document.getElementById('comparatif').textContent || '').replace(/\s+/g, ' '));
  verifier('en exemple, le comparatif montre aussi passés en cours, nouveaux, disparus et une réémission',
    /passés? à « En cours »/.test(lotsExemple) && /nouveau/.test(lotsExemple) && /disparu/.test(lotsExemple) && /indice/.test(lotsExemple),
    lotsExemple.slice(0, 160));
  // Changer de contrat en exemple ne rebascule plus sans un mot sur les données réelles.
  await p.selectOption('#select-contrat', 'THS'); await p.waitForTimeout(900);
  const exempleX2 = await p.evaluate(() => ({
    marque: document.body.dataset.exemple, mot: document.getElementById('mot-mode').textContent,
    contrat: document.getElementById('select-contrat').value
  }));
  verifier('changer de contrat en exemple reste en exemple, sur le nouveau contrat',
    exempleX2.marque === 'true' && /fabriqué/.test(exempleX2.mot) && exempleX2.contrat === 'THS', JSON.stringify(exempleX2));
  await p.selectOption('#select-contrat', 'HDK'); await p.waitForTimeout(900);
  await basculerMode(p, 'reel'); await p.waitForTimeout(900);

  // Le pied « Jeu d'exemple » ne se lit que dans la démonstration.
  verifier('la démonstration dit « Jeu d’exemple » dans son pied',
    await p.evaluate(() => !document.getElementById('avertissement-demo').hidden &&
      /Jeu d'exemple/.test(document.querySelector('.pied').textContent)));

  // Le cadrage d'ouverture montre aujourd'hui et les cinq jalons configurés.
  const cadrage = await p.evaluate(() => ({
    jalons: document.querySelectorAll('svg.graphe .jalon').length,
    aujourdhui: [...document.querySelectorAll('svg.graphe .repere-auj')].length === 1
  }));
  verifier('à l’ouverture, les cinq jalons et le repère du dernier relevé sont dans le cadre',
    cadrage.jalons === 5 && cadrage.aujourdhui, JSON.stringify(cadrage));

  // La ligne « changement d'indice » de la semaine ouverte n'est plus reléguée derrière « voir les autres ».
  verifier('un changement d’indice se lit dans la semaine ouverte sans déplier « voir les autres »',
    await p.evaluate(() => !!document.querySelector('.journal-semaine .journal-liste .ref-indice')));

  // La bulle d'une puce du comparatif ne liste plus de références tronquées.
  const puceTermine = await p.$('.puce-delta[data-delta="termine"]');
  if (puceTermine) {
    await puceTermine.hover(); await p.waitForTimeout(250);
    const bulleTermine = await p.evaluate(() => document.getElementById('bulle').innerText);
    verifier('la bulle d’un lot compte et invite à cliquer, sans lister de références',
      !/[A-Z]{3}\d{4}A\d{3}/.test(bulleTermine) && /Cliquez/.test(bulleTermine) && !/autres/.test(bulleTermine),
      bulleTermine.replace(/\s+/g, ' ').slice(0, 100));
  }
  const puceIndice = await p.$('.puce-delta[data-delta="indice"]');
  if (puceIndice) {
    await puceIndice.hover(); await p.waitForTimeout(250);
    verifier('la bulle des changements d’indice montre les paires ancienne → nouvelle',
      await p.evaluate(() => /→/.test(document.getElementById('bulle').innerText)));
  }
  await p.mouse.move(5, 5); await p.waitForTimeout(150);

  // Sous périmètre, le rapprochement sépare ce qui est dans le périmètre de ce qui est absent d'ici (tout contrat).
  await p.click('#choix-perimetre button:has-text("PERSO")'); await p.waitForTimeout(700);
  const rappPerso = await p.evaluate(() => (document.getElementById('rapprochement').textContent || '').replace(/\s+/g, ' '));
  verifier('sous périmètre, la section de comparaison distingue les plans du périmètre des lignes comptées sur tout le contrat',
    /plans du périmètre/.test(rappPerso) && /tout le contrat/.test(rappPerso) && !/lignes là/.test(rappPerso), rappPerso.slice(0, 160));
  await p.click('#choix-perimetre button:has-text("Tout")'); await p.waitForTimeout(700);

  // Le journal filtré ouvre la première semaine réellement affichée.
  await p.click('#filtre-journal button[data-journal="afaire"]'); await p.waitForTimeout(500);
  const journalFiltre = await p.evaluate(() => {
    const s = document.querySelector('.journal-semaine');
    return s ? { ouvert: s.querySelector('.journal-plier').getAttribute('aria-expanded'), lignes: s.querySelectorAll('.journal-ligne').length } : null;
  });
  verifier('sous un filtre du journal, la première semaine affichée est dépliée',
    !!journalFiltre && journalFiltre.ouvert === 'true' && journalFiltre.lignes > 0, JSON.stringify(journalFiltre));
  await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(400);

  // Un filtre de colonne se voit dans le bandeau, avec sa croix.
  await p.fill('input[data-filtre="ata"]', '21'); await p.waitForTimeout(500);
  const bandeauColonne = await p.evaluate(() => ({
    visible: !document.getElementById('filtres-actifs').hidden,
    texte: document.getElementById('filtres-actifs').textContent.replace(/\s+/g, ' ')
  }));
  verifier('un filtre de colonne apparaît dans le bandeau des filtres actifs',
    bandeauColonne.visible && /ATA/.test(bandeauColonne.texte) && /21/.test(bandeauColonne.texte), JSON.stringify(bandeauColonne));
  await p.click('button[data-retirer="filtre:ata"]'); await p.waitForTimeout(500);
  verifier('sa croix retire le filtre',
    await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === TOTAL);

  // Un long historique : aujourd'hui, la projection et les jalons restent atteignables.
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const base = s.releves[s.releves.length - 1];
    const precedente = (sem, n) => { let [a, w] = sem.split('-S').map(Number); w -= n; while (w < 1) { a--; w += 52; } return a + '-S' + String(w).padStart(2, '0'); };
    const liste = [];
    for (let k = 112; k >= 0; k--) liste.push(Object.assign({}, base, { semaine: precedente(base.semaine, k) }));
    s.releves = liste;
    window.__chargerSource(s);
  });
  await p.waitForTimeout(500);
  const longOuverture = await p.evaluate(() => ({
    releves: /113 relevés/.test(document.getElementById('import').textContent),
    aujourdhui: [...document.querySelectorAll('svg.graphe .repere-auj')].length === 1,
    jalons: document.querySelectorAll('svg.graphe .jalon').length
  }));
  verifier('avec 113 relevés, l’ouverture montre encore le repère du dernier relevé et les jalons',
    longOuverture.releves && longOuverture.aujourdhui && longOuverture.jalons === 5, JSON.stringify(longOuverture));
  await p.click('.commandes-graphe button[data-span="0"]'); await p.waitForTimeout(400);
  const longTout = await p.evaluate(() => ({
    aujourdhui: document.querySelectorAll('svg.graphe .repere-auj').length === 1,
    jalons: document.querySelectorAll('svg.graphe .jalon').length
  }));
  verifier('et « Tout » les garde à l’écran', longTout.aujourdhui && longTout.jalons === 5, JSON.stringify(longTout));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(500);

  // norm() réduit comme le serveur : espaces internes, insécables, accents.
  verifier('norm() réduit les espaces comme le serveur',
    await p.evaluate(() => window.__norm('Non commencé  ') === 'non commence' && window.__norm(' Non   commencé') === 'non commence' &&
      window.__norm(' Terminé ') === 'termine'));

  // La page reste ES5 : pas de padStart dans le code expédié, normalize gardé.
  {
    const fs = require('fs');
    const src = fs.readFileSync(path.join(__dirname, '..', 'suivi-fwd.html'), 'utf8');
    const script = src.slice(src.indexOf('<script>'));
    verifier('aucun padStart dans le code de la page', !/\.padStart\(/.test(script.replace(/\/\*[\s\S]*?\*\//g, '')));
    verifier('normalize n’est appelé que s’il existe', /if \(s\.normalize\)/.test(script));
  }

  // Les préférences : l'ordre mémorisé est celui de la vue complète ; le tri survit au rechargement.
  {
    const ctxPrefs = await contexte();
    const pp = await page(ctxPrefs, 'préférences');
    await pp.click('#vue-tableau button[data-vue="essentielle"]'); await pp.waitForTimeout(800);
    await pp.reload(); await pp.waitForTimeout(1400);
    const apresEssentielle = await pp.evaluate(() => ({
      toutes: document.querySelector('#vue-tableau button[data-vue="toutes"]').getAttribute('aria-pressed'),
      n: document.querySelectorAll('tr.titres th').length,
      tete: [...document.querySelectorAll('tr.titres th')].slice(0, 3).map(t => t.dataset.cle).join(',')
    }));
    verifier('après « Vue essentielle » puis rechargement, « Toutes les colonnes » revient dans l’ordre de l’extract',
      apresEssentielle.toutes === 'true' && apresEssentielle.n === COLONNES_TOTAL && apresEssentielle.tete === 'reference,rpt,colonne_4',
      JSON.stringify(apresEssentielle));
    await pp.click('tr.titres button[data-tri="ata"]'); await pp.waitForTimeout(800);
    await pp.reload(); await pp.waitForTimeout(1400);
    verifier('le tri d’une colonne survit au rechargement',
      await pp.evaluate(() => document.querySelector('th[data-cle="ata"]').getAttribute('aria-sort') === 'ascending'));
    await ctxPrefs.close();
  }

  // Un paquet que le classeur n'a pas pu remplir : la page s'ouvre sur la
  // démonstration — et le dit —, et « Données réelles » montre la page vide
  // avec le message du classeur. L'interrupteur est visible : il y a de quoi
  // comparer.
  {
    const ctxVide = await contexte();
    await ctxVide.addInitScript(() => {
      window.SUIVI_FWD_DONNEES = { ok: false, message: 'Feuille vide : aucun plan.', colonnes: [], plans: [], releves: [], jalons: [], contrats: [], contrat: '' };
    });
    const pv = await page(ctxVide, 'classeur vide');
    const lire = () => pv.evaluate(() => ({
      visible: !document.getElementById('mode-donnees').hidden && document.getElementById('mode-donnees').offsetParent !== null,
      alerte: !document.getElementById('alerte-source').hidden,
      texte: document.getElementById('alerte-source').textContent,
      mot: document.getElementById('mot-mode').textContent,
      lignes: document.querySelectorAll('#corps-tableau td.ref, #corps-tableau .ref').length,
      demo: !document.getElementById('avertissement-demo').hidden,
      marque: document.body.dataset.exemple,
      presse: [...document.querySelectorAll('#mode-donnees button')].map(b => b.dataset.mode + ':' + b.getAttribute('aria-pressed')).join(' '),
      contrats: [...document.querySelectorAll('#select-contrat option')].map(o => o.value).join(','),
      rapprochement: !document.getElementById('rapprochement').hidden
    }));
    const ouverture = await lire();
    verifier('un classeur vide ouvre la page sur la démonstration, et le dit',
      ouverture.marque === 'true' && /Démonstration/.test(ouverture.mot) && ouverture.presse === 'reel:false exemple:true' &&
      ouverture.lignes > 0 && ouverture.demo, JSON.stringify(ouverture));
    verifier('… avec le message du classeur à côté, pour dire pourquoi',
      ouverture.alerte && /Feuille vide/.test(ouverture.texte), ouverture.texte);
    verifier('… l’interrupteur visible, les trois contrats fictifs et le rapprochement',
      ouverture.visible && ouverture.contrats === 'HDK,THS,VRK' && ouverture.rapprochement, JSON.stringify(ouverture));
    await basculerMode(pv, 'reel'); await pv.waitForTimeout(600);
    const reel = await lire();
    verifier('« Données réelles » montre alors la page vide, avec le message, sans plan ni démonstration',
      reel.marque === 'false' && reel.lignes === 0 && reel.alerte && /Feuille vide/.test(reel.texte) && !reel.demo && reel.mot === '',
      JSON.stringify(reel));
    await basculerMode(pv, 'exemple'); await pv.waitForTimeout(600);
    await pv.selectOption('#select-contrat', 'THS'); await pv.waitForTimeout(900);
    const ths = await lire();
    verifier('changer de contrat sous la démonstration reste dans la démonstration',
      ths.marque === 'true' && /Démonstration/.test(ths.mot) && ths.lignes > 0 && ths.lignes !== ouverture.lignes && ths.alerte,
      JSON.stringify([ths.lignes, ouverture.lignes, ths.mot]));
    await basculerMode(pv, 'reel'); await pv.waitForTimeout(600);
    verifier('et revenir au réel après cela retrouve la page vide du classeur, intacte',
      (await lire()).lignes === 0);
    await ctxVide.close();
  }

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
    return { tri: b ? b.dataset.trig : null, jalons: window.__jeuDExemple('HDK').jalons.length,
             stockes: /"jalons"/.test(localStorage.getItem('suivi-fwd:v1') || '') };
  });
  verifier('le tri du bloc par groupe survit au rechargement',
    apresRech.tri === triAvant, triAvant + ' → ' + apresRech.tri);
  verifier('les jalons ne passent pas par le stockage : ils viennent de la source',
    apresRech.jalons === 5 && !apresRech.stockes, JSON.stringify(apresRech));

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
    jalons: [{ i: 'pas un nombre', texte: 42 }, null, { i: 99999 }, { semaine: '2026-S50', texte: '<b>stocké</b>' }],
    fen: { debut: 'x' }, tri: { cle: '__proto__' }, triGroupe: { cle: 'rm -rf', asc: 'oui' },
    ordre: ['inexistante'], cachees: { reference: true }
  })));
  await pc.reload(); await pc.waitForTimeout(1300);
  await pc.click('.segmente button[data-span="0"]'); await pc.waitForTimeout(400);
  const survie = await pc.evaluate(() => ({
    lignes: (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length),
    colonnes: document.querySelectorAll('tr.titres th').length,
    refVisible: !!document.querySelector('tr.titres th[data-cle="reference"]'),
    triActif: document.querySelectorAll('button[data-trig][data-actif="true"]').length,
    jalons: [...document.querySelectorAll('.jalon-texte')].map(t => t.textContent)
  }));
  verifier('des préférences absurdes sont ignorées sans plantage', survie.lignes === TOTAL, survie.lignes + ' lignes');
  verifier('des jalons laissés dans un ancien stockage ne sont pas relus',
    survie.jalons.length === 5 && !survie.jalons.some(t => /stock/.test(t)), JSON.stringify(survie.jalons));
  verifier('une ancienne clé « cachees » est ignorée : les 137 colonnes restent présentes',
    survie.colonnes === COLONNES_TOTAL, survie.colonnes + ' colonnes');
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
  await pb.click('#etats .etat-btn[data-etat="termine"]').catch(() => {});
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
    await pk.evaluate(() => [...document.querySelectorAll('#etats .etat-btn')].every(b => b.hasAttribute('aria-pressed'))));
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
      etats: document.querySelectorAll('#etats .etat-n').length,
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
    const segs = [...document.querySelectorAll('#barre span')].filter(s => s.textContent.trim());
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
    const segs = [...document.querySelectorAll('#barre span')].filter(s => s.textContent.trim());
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

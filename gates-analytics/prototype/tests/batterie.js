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
    /* Les valeurs des deux colonnes sans intitulé qui restent : au moins une
       cellule renseignée chacune, sinon elles n'auraient rien à faire là. */
    col4: [...document.querySelectorAll('#corps-tableau tr')].some(tr =>
      tr.children[[...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'colonne_4')].textContent.trim() !== '-'),
    col5: [...document.querySelectorAll('#corps-tableau tr')].some(tr =>
      tr.children[[...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'colonne_5')].textContent.trim() !== '-')
  }));
  verifier('le tableau ouvre sur les 137 colonnes : l\'export entier, moins la seule vide sans intitule',
    extrait.affichees === COLONNES_TOTAL, extrait.affichees + ' / ' + COLONNES_TOTAL);
  verifier('« Colonne 1 », vide de bout en bout, n\'est pas dans les en-tetes',
    extrait.titres.indexOf('Colonne 1') === -1 && extrait.ordre.indexOf('colonne_1') === -1,
    extrait.titres.slice(0, 4).join(' | '));
  verifier('« Colonne 4 » et « Colonne 5 », sans intitule mais renseignees, restent, a leur place',
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
    sel0.visible && sel0.haut && sel0.options === 'HDK,THS,VRK', JSON.stringify(sel0));
  verifier('il demarre sur HDK, rappele sous le titre',
    sel0.courant === 'HDK' && sel0.nom === 'HDK' && sel0.nomVisible, JSON.stringify(sel0));
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
    mode: document.body.dataset.exemple,
    /* Le cadrage par défaut se reconnaît à ce qu'il montre : aujourd'hui et
       tous les jalons du contrat — pas à un nombre de bandes, qui dépend de
       la source. */
    jalons: document.querySelectorAll('svg.graphe .jalon').length,
    aujourdhui: [...document.querySelectorAll('svg.graphe text')].some(t => /aujourd/.test(t.textContent))
  }));
  await p.selectOption('#select-contrat', 'THS'); await p.waitForTimeout(1200);
  const x2 = await lireContrat();
  verifier('changer de contrat change le nombre de plans', x2.plans > 0 && x2.plans !== TOTAL, String(x2.plans));
  verifier('et le pied de page', x2.pied !== pied0, x2.pied);
  verifier('le contrat courant est rappele sous le titre', x2.nom === 'THS' && x2.courant === 'THS', x2.nom);
  verifier('les filtres et le cadrage repartent de zero',
    x2.filtres && x2.presse === 0 && x2.jalons === 4 && x2.aujourdhui, JSON.stringify(x2));
  verifier('le bloc par groupe et le journal suivent le nouveau contrat',
    x2.groupes === x2.plans && x2.journal > 0, x2.groupes + ' / ' + x2.plans);
  await p.selectOption('#select-contrat', 'VRK'); await p.waitForTimeout(1200);
  const x3 = await lireContrat();
  verifier('un troisieme contrat a encore d\'autres comptes',
    x3.plans > 0 && x3.plans !== x2.plans && x3.plans !== TOTAL && x3.nom === 'VRK', String(x3.plans));
  // L'exemple d'un autre contrat, puis un changement de contrat : on RESTE en
  // exemple, sur le nouveau contrat — rebasculer sans un mot sur le réel
  // trompait la lectrice.
  await p.click('#mode-donnees button[data-mode="exemple"]'); await p.waitForTimeout(800);
  await p.selectOption('#select-contrat', 'HDK'); await p.waitForTimeout(1200);
  const x1ex = await lireContrat();
  verifier('un changement de contrat en exemple reste en exemple, sur le nouveau contrat',
    x1ex.mode === 'true' && x1ex.nom === 'HDK', JSON.stringify({ mode: x1ex.mode, nom: x1ex.nom }));
  await p.click('#mode-donnees button[data-mode="reel"]'); await p.waitForTimeout(900);
  const x1 = await lireContrat();
  verifier('revenir a HDK, en donnees reelles, redonne les comptes initiaux',
    x1.plans === TOTAL && x1.etats === etats0 && x1.pied === pied0 && x1.mode === 'false', JSON.stringify(x1));
  // Sans liste de contrats — ou avec un seul — rien à choisir : le sélecteur disparaît.
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); delete s.contrats; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  const seul = await p.evaluate(() => ({
    cache: document.getElementById('choix-contrat').hidden &&
           document.getElementById('select-contrat').offsetParent === null,
    nomCache: document.getElementById('contrat-courant').hidden,
    plans: document.querySelectorAll('#corps-tableau tr').length
  }));
  verifier('sans liste de contrats, le selecteur et le rappel disparaissent',
    seul.cache && seul.nomCache && seul.plans === TOTAL, JSON.stringify(seul));
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); s.contrats = [{ id: 'HDK', nom: 'HDK' }]; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  verifier('avec un seul contrat liste, pareil',
    await p.evaluate(() => document.getElementById('choix-contrat').hidden &&
      document.getElementById('contrat-courant').hidden));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(900);
  verifier('la liste revenue, le selecteur revient',
    await p.evaluate(() => !document.getElementById('choix-contrat').hidden &&
      [...document.querySelectorAll('#select-contrat option')].map(o => o.value).join(',') === 'HDK,THS,VRK' &&
      document.getElementById('select-contrat').value === 'HDK'));

  // =================================================================
  /* Le rapprochement avec une seconde base : la démonstration en fabrique
     une, aux colonnes nommées autrement, avec des écarts délibérés — 5 plans
     absents là, 5 références absentes ici, 2 indices différents, 10 champs
     différents. La section vit entre le bloc par groupe et le tableau ; trois
     compteurs filtrent le tableau, « absents d'ici » déplie une liste, et
     un panneau détaille les écarts de champ. Elle suit le périmètre et le
     contrat, et disparaît quand la source ne décrit aucune seconde base. */
  section('Rapprochement avec une seconde base');
  const lireRapp = () => p.evaluate(() => {
    const R = window.__rapprochement();
    const top = el => Math.round(document.getElementById(el).getBoundingClientRect().top + window.scrollY);
    return {
      cache: document.getElementById('rapprochement').hidden,
      titre: document.getElementById('titre-rapprochement').textContent,
      phrase: document.getElementById('phrase-rapprochement').textContent,
      puces: [...document.querySelectorAll('#puces-rapprochement button[data-rapp]')].map(b => ({
        cle: b.dataset.rapp, n: +b.querySelector('b').textContent.replace(/\s/g, ''),
        libelle: b.textContent.replace(/^\s*\d+\s*/, '').trim(),
        presse: b.getAttribute('aria-pressed'), inactif: b.disabled
      })),
      ordre: top('zone-critique') < top('rapprochement') && top('rapprochement') < top('cadre-tableau'),
      lignes: document.querySelectorAll('#corps-tableau tr').length,
      refsTableau: [...document.querySelectorAll('#corps-tableau tr td.ref')].map(td => td.textContent.trim()),
      jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()),
      bouton: document.getElementById('bouton-detail-rapprochement').textContent,
      ouvert: document.getElementById('bouton-detail-rapprochement').getAttribute('aria-expanded'),
      grille: !!document.querySelector('#detail-rapprochement .rapp-grille'),
      cellules: document.querySelectorAll('#detail-rapprochement .rapp-grille > div').length,
      entetes: [...document.querySelectorAll('#detail-rapprochement .rapp-entete')].map(e => e.textContent),
      refsDetail: [...document.querySelectorAll('#detail-rapprochement .rapp-grille > div.ref')].map(e => e.textContent),
      lignesDetail: [...document.querySelectorAll('#detail-rapprochement .rapp-grille > div')].map(e => e.textContent),
      absents: document.querySelectorAll('#absents-rapprochement .rapp-liste .ligne').length,
      absentsRefs: [...document.querySelectorAll('#absents-rapprochement .ligne .ref')].map(e => e.textContent),
      absentsChamps: [...document.querySelectorAll('#absents-rapprochement .ligne')].map(l => l.querySelectorAll('.champ').length),
      R: R && {
        absentsLa: R.absentsLa.length, absentsIci: R.absentsIci.length,
        indice: R.indiceDifferent.length, ecarts: R.ecarts.length, total: R.total,
        nbPlans: R.nbPlans, nbLignes: R.nbLignes,
        refsEcarts: R.ecarts.map(e => e.plan.reference),
        champsEcarts: R.ecarts.map(e => e.champ),
        indices: R.indiceDifferent.map(x => ({ ici: x.plan.reference, la: x.ref_la, racineIci: window.__analyserUD(x.plan.reference).racine, racineLa: window.__analyserUD(x.ref_la).racine })),
        avancement: R.ecarts.filter(e => e.champ === 'Avancement').map(e => [e.ici, e.la])
      }
    };
  });
  const r0 = await lireRapp();
  verifier('la section est là, nommée d\'après la seconde base',
    !r0.cache && r0.titre === 'Rapprochement avec Base FWD (extract Excel)', r0.titre);
  verifier('entre le bloc par groupe et le tableau', r0.ordre);
  verifier('la phrase compte les deux côtés et les écarts',
    r0.phrase === TOTAL + ' plans ici, ' + TOTAL + ' lignes là : 22 écarts.', r0.phrase);
  verifier('quatre compteurs, dans l\'ordre, avec les nombres attendus : 5 / 5 / 2 / 10',
    r0.puces.map(x => x.cle + '=' + x.n).join(' ') === 'absentsLa=5 absentsIci=5 indiceDifferent=2 ecarts=10',
    JSON.stringify(r0.puces));
  verifier('et les libellés attendus',
    r0.puces.map(x => x.libelle).join(' | ') === 'absents de la seconde base | absents d’ici | solution ou indice différent | champs différents',
    r0.puces.map(x => x.libelle).join(' | '));
  verifier('aucun n\'est pressé ni inactif au départ, le tableau est entier',
    r0.puces.every(x => x.presse === 'false' && !x.inactif) && r0.lignes === TOTAL && r0.jetons.length === 0);
  verifier('le moteur donne les mêmes comptes : 22 écarts au total',
    r0.R && r0.R.total === 22 && r0.R.nbPlans === TOTAL && r0.R.nbLignes === TOTAL, JSON.stringify(r0.R && [r0.R.total, r0.R.nbPlans, r0.R.nbLignes]));
  verifier('les écarts de champ couvrent les cinq champs déclarés, deux fois chacun',
    ['ATA', 'ECP', 'Avancement', 'Nom Installation', 'Séquence'].every(c => r0.R.champsEcarts.filter(x => x === c).length === 2),
    JSON.stringify(r0.R.champsEcarts));
  verifier('l\'avancement se compare par état : « OK » / « WIP » contre « Terminé » / « En cours »',
    r0.R.avancement.length === 2 && r0.R.avancement.every(([ici, la]) => /^(OK|WIP)$/.test(la) && !/^(OK|WIP)$/.test(ici)),
    JSON.stringify(r0.R.avancement));
  verifier('un indice différent, c\'est la même racine sous une autre émission',
    r0.R.indices.length === 2 && r0.R.indices.every(x => x.racineIci === x.racineLa && x.ici !== x.la && /-/.test(x.la)),
    JSON.stringify(r0.R.indices));

  // « champs différents » : le tableau se réduit aux dix plans concernés.
  await p.click('#puces-rapprochement button[data-rapp="ecarts"]'); await p.waitForTimeout(500);
  const rEc = await lireRapp();
  verifier('cliquer « champs différents » réduit le tableau à 10 plans', rEc.lignes === 10, String(rEc.lignes));
  verifier('ce sont bien les plans en écart',
    rEc.refsTableau.length === 10 && rEc.refsTableau.every(r => r0.R.refsEcarts.indexOf(r) !== -1), JSON.stringify(rEc.refsTableau));
  verifier('le bandeau nomme le filtre « Rapprochement : champs différents », la puce est pressée',
    rEc.jetons.length === 1 && rEc.jetons[0] === 'Rapprochement : champs différents' &&
    rEc.puces.filter(x => x.presse === 'true').map(x => x.cle).join() === 'ecarts', JSON.stringify(rEc.jetons));
  verifier('les comptes ne bougent pas : le rapprochement ne se filtre pas lui-même',
    rEc.puces.map(x => x.n).join() === '5,5,2,10');
  await p.click('#puces-rapprochement button[data-rapp="absentsLa"]'); await p.waitForTimeout(500);
  const rAb = await lireRapp();
  verifier('« absents de la seconde base » remplace la sélection : 5 plans',
    rAb.lignes === 5 && rAb.jetons[0] === 'Rapprochement : absents de la seconde base' &&
    rAb.puces.filter(x => x.presse === 'true').map(x => x.cle).join() === 'absentsLa', JSON.stringify(rAb.jetons) + ' ' + rAb.lignes);
  await p.click('#puces-rapprochement button[data-rapp="indiceDifferent"]'); await p.waitForTimeout(500);
  const rIn = await lireRapp();
  verifier('« indice différent » : 2 plans, ceux du moteur',
    rIn.lignes === 2 && rIn.refsTableau.sort().join() === r0.R.indices.map(x => x.ici).sort().join(), JSON.stringify(rIn.refsTableau));
  await p.click('#puces-rapprochement button[data-rapp="indiceDifferent"]'); await p.waitForTimeout(500);
  const rOff = await lireRapp();
  verifier('re-cliquer le compteur pressé retire le filtre',
    rOff.lignes === TOTAL && rOff.jetons.length === 0 && rOff.puces.every(x => x.presse === 'false'));
  await p.click('#puces-rapprochement button[data-rapp="ecarts"]'); await p.waitForTimeout(400);
  await p.click('.jeton .x'); await p.waitForTimeout(400);
  verifier('la croix du bandeau retire aussi le filtre du rapprochement',
    await p.evaluate(t => document.querySelectorAll('#corps-tableau tr').length === t &&
      document.getElementById('filtres-actifs').hidden, TOTAL));

  // Le détail des écarts : fermé au départ, une grille de quatre colonnes.
  verifier('le détail est replié au départ, son bouton compte les écarts',
    r0.ouvert === 'false' && !r0.grille && r0.cellules === 0 && /^détail des écarts \(10\)$/.test(r0.bouton), r0.bouton);
  await p.click('#bouton-detail-rapprochement'); await p.waitForTimeout(350);
  const rDe = await lireRapp();
  verifier('le détail liste les 10 écarts en grille de quatre colonnes',
    rDe.ouvert === 'true' && rDe.grille && rDe.cellules === 44 && rDe.entetes.join('|') === 'Référence|Champ|Ici|Là',
    rDe.cellules + ' cellules, ' + rDe.entetes.join('|'));
  verifier('une ligne par écart : la référence en mono, le champ, la valeur ici, la valeur là',
    rDe.refsDetail.length === 10 && rDe.refsDetail.join() === r0.R.refsEcarts.join() &&
    rDe.lignesDetail.slice(4).filter((_, i) => i % 4 === 1).join() === r0.R.champsEcarts.join(),
    JSON.stringify(rDe.refsDetail.slice(0, 3)));
  verifier('ouvrir le détail ne filtre pas le tableau', rDe.lignes === TOTAL);
  await p.click('#bouton-detail-rapprochement'); await p.waitForTimeout(300);
  verifier('le détail se replie', (await lireRapp()).cellules === 0);

  // « absents d'ici » : ces références n'ont pas de ligne, on les liste.
  await p.click('#puces-rapprochement button[data-rapp="absentsIci"]'); await p.waitForTimeout(350);
  const rIci = await lireRapp();
  verifier('« absents d\'ici » déplie la liste des 5 références, sans toucher au tableau',
    rIci.absents === 5 && rIci.lignes === TOTAL && rIci.jetons.length === 0 &&
    rIci.puces.filter(x => x.presse === 'true').map(x => x.cle).join() === 'absentsIci', JSON.stringify([rIci.absents, rIci.lignes]));
  verifier('chaque référence est inédite ici, et vient avec ses cinq champs',
    rIci.absentsRefs.every(r => r0.R.refsEcarts.indexOf(r) === -1 && /^NEW/.test(r)) &&
    rIci.absentsChamps.every(n => n === 5), JSON.stringify(rIci.absentsRefs));
  await p.click('#puces-rapprochement button[data-rapp="absentsIci"]'); await p.waitForTimeout(300);
  verifier('re-cliquer replie la liste', (await lireRapp()).absents === 0);

  // Le périmètre : les plans hors périmètre ne comptent pas.
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const rPe = await lireRapp();
  verifier('le périmètre PERSO réduit les comptes des trois lots de plans',
    rPe.R.absentsLa + rPe.R.indice + rPe.R.ecarts < 17 && rPe.R.nbPlans < TOTAL &&
    rPe.puces.map(x => x.n).join() === [rPe.R.absentsLa, rPe.R.absentsIci, rPe.R.indice, rPe.R.ecarts].join(),
    JSON.stringify(rPe.puces.map(x => x.n)));
  verifier('les références absentes d\'ici, sans domaine, restent comptées', rPe.R.absentsIci === 5);
  /* Sous périmètre, les absents d'ici (sans domaine, tout le contrat) se
     comptent à part : la phrase ne les mêle plus aux écarts du périmètre. */
  const ecartsPerimetre = rPe.R.absentsLa + rPe.R.indice + rPe.R.ecarts;
  verifier('la phrase nomme le périmètre, compte ses écarts et met à part les absents d’ici',
    new RegExp('^' + rPe.R.nbPlans + ' plans ici \\(périmètre PERSO\\) : ' + ecartsPerimetre + ' écarts? dans le périmètre · ' +
               rPe.R.absentsIci + ' références? absentes? d’ici, tout le contrat\\.$').test(rPe.phrase), rPe.phrase);
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(600);
  verifier('revenir à Tout redonne les 22 écarts', (await lireRapp()).R.total === 22);

  // Le contrat : la seconde base est celle du contrat courant.
  await p.selectOption('#select-contrat', 'VRK'); await p.waitForTimeout(1200);
  const rX3 = await lireRapp();
  verifier('changer de contrat recalcule le rapprochement sur ses plans',
    rX3.R.nbPlans !== TOTAL && rX3.R.nbPlans === rX3.lignes && rX3.R.nbLignes === rX3.R.nbPlans &&
    rX3.phrase.indexOf(rX3.R.nbPlans + ' plans ici') === 0 && rX3.R.total === 22, rX3.phrase);
  verifier('les écarts sont ceux d\'autres plans',
    rX3.R.refsEcarts.every(r => r0.R.refsEcarts.indexOf(r) === -1), JSON.stringify(rX3.R.refsEcarts.slice(0, 2)));
  await p.selectOption('#select-contrat', 'HDK'); await p.waitForTimeout(1200);

  // L'exemple : la même seconde base, les mêmes comptes.
  await p.click('#mode-donnees button[data-mode="exemple"]'); await p.waitForTimeout(800);
  const rEx = await lireRapp();
  verifier('en mode exemple, la section reste et dit la même chose',
    !rEx.cache && rEx.R.total === 22 && rEx.phrase === r0.phrase, rEx.phrase);
  await p.click('#mode-donnees button[data-mode="reel"]'); await p.waitForTimeout(800);

  // Sans description de seconde base, il n'y a rien à rapprocher.
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); delete s.rapprochement; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  const rSans = await lireRapp();
  verifier('sans rapprochement dans la source, la section est absente',
    rSans.cache && rSans.R === null, JSON.stringify([rSans.cache, rSans.R]));
  verifier('et le reste de la page est intact', rSans.lignes === TOTAL);
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); s.rapprochement = { nom: 'Vide', cleReference: 'REF', champs: [], lignes: [] }; window.__chargerSource(s); });
  await p.waitForTimeout(900);
  const rVide = await lireRapp();
  verifier('une seconde base vide : tous les plans sont absents de là, les autres compteurs inactifs',
    !rVide.cache && rVide.R.absentsLa === TOTAL && rVide.puces[0].n === TOTAL &&
    rVide.puces.slice(1).every(x => x.inactif) && /aucun|écarts\.$/.test(rVide.phrase), rVide.phrase);
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(900);
  verifier('la seconde base revenue, la section revient', !(await lireRapp()).cache && (await lireRapp()).R.total === 22);

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
    const refsComparatif = C ? ['termine', 'encours', 'afaire', 'nouveaux', 'disparus', 'solution', 'indice']
      .reduce((l, k) => l.concat(C[k]), []) : [];
    return {
      phrase: document.getElementById('phrase').textContent,
      etats: [...document.querySelectorAll('.etat-n')].map(e => +e.textContent.replace(/\s/g, '')),
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
    /* Entre le titre et la barre d'avancement : c'est là qu'on choisit ce
       qu'on regarde, et le bandeau du haut garde sa sobriété. */
    haut: document.getElementById('perimetre').getBoundingClientRect().top >
          document.querySelector('.masthead').getBoundingClientRect().top &&
          document.getElementById('perimetre').getBoundingClientRect().bottom <=
          document.querySelector('.avancement').getBoundingClientRect().top + 1,
    dansBandeau: !!document.querySelector('header.masthead + #perimetre #choix-perimetre'),
    boutons: [...document.querySelectorAll('#choix-perimetre button')].map(b => ({
      val: b.dataset.perimetre, texte: b.textContent.trim(),
      n: +(b.querySelector('.n') || { textContent: '0' }).textContent.replace(/\s/g, ''),
      presse: b.getAttribute('aria-pressed')
    }))
  }));
  verifier('le sélecteur est là, sous le titre et au-dessus de la barre',
    selP.visible && selP.haut && selP.dansBandeau, JSON.stringify(selP).slice(0, 120));
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
  await p.click('.etat-btn[data-etat="termine"]'); await p.waitForTimeout(500);
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
  await p.click('#mode-donnees button[data-mode="exemple"]'); await p.waitForTimeout(900);
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const exPerso = await lirePerimetre();
  verifier('en exemple aussi, la courbe du périmètre est dérivée des cartes',
    exPerso.serie.length >= 5 && exPerso.dernier.total === nPerso && exPerso.dernier.termine === exPerso.etats[0] &&
    exPerso.domainesJournal.join() === 'PERSO', JSON.stringify(exPerso.dernier));
  await p.click('#mode-donnees button[data-mode="reel"]'); await p.waitForTimeout(800);
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
      if (e.type === 'indice' || e.type === 'solution') indices.push({ i: s.i, type: e.type, ref: e.ref, ancienne: e.ancienne, avant: e.avant, apres: e.apres });
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
      comparatif: C && C.indice && C.solution ? C.solution.concat(C.indice).sort() : null,
      reemissions: C && C.reemissions ? C.reemissions : null
    };
  });
  verifier('le journal porte les six réémissions fabriquées', app.indices.length === 6, String(app.indices.length));
  verifier('à six semaines différentes', app.semaines === 6, String(app.semaines));
  verifier('trois changent de solution (les chiffres), trois d’indice (la lettre)',
    app.types === 'indice indice indice solution solution solution', app.types);
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

  /* La dernière semaine porte un changement de solution ; la puce du
     comparatif est donc celle-là. On lit celle qui existe. */
  const cleReem = await p.evaluate(() => document.querySelector('.puce-delta[data-delta="solution"]') ? 'solution' : 'indice');
  const domIndice = await p.evaluate(cle => ({
    puce: (document.querySelector('.puce-delta[data-delta="' + cle + '"]') || { textContent: '' }).textContent,
    pastille: !!document.querySelector('.puce-delta[data-delta="' + cle + '"] .pastille.neutre'),
    comptes: [...document.querySelectorAll('.compte-passage[data-passage="indice"], .compte-passage[data-passage="solution"]')].map(b => b.textContent),
    boutons: !!document.querySelector('#filtre-journal button[data-journal="indice"]') &&
             !!document.querySelector('#filtre-journal button[data-journal="solution"]')
  }), cleReem);
  verifier('la puce de la réémission est là, avec une pastille neutre',
    /changements? (d’indice|de solution)/.test(domIndice.puce) && domIndice.pastille, domIndice.puce);
  verifier('chaque semaine concernée compte sa réémission, en bouton, solution ou indice',
    domIndice.comptes.length === 6 && domIndice.comptes.every(t => /^1 changement (d’indice|de solution)$/.test(t)),
    lu(domIndice.comptes));
  verifier('et le filtre du journal propose les deux', domIndice.boutons);

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
    filtreIndice.presse === 'true' && /changements (d’indice|de solution)/.test(filtreIndice.jeton), filtreIndice.jeton);
  await p.click('.puce-delta[data-delta="' + cleReem + '"]'); await p.waitForTimeout(500);
  verifier('re-cliquer rend tous les plans',
    await p.evaluate(t => document.querySelectorAll('#corps-tableau tr').length === t, TOTAL));

  // Le compte du journal filtre sur les changements de solution ; la ligne se lit ancienne → nouvelle.
  await p.click('.compte-passage[data-passage="solution"] >> nth=0'); await p.waitForTimeout(400);
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
  verifier('sous ce filtre, le journal ne montre que les trois changements de solution',
    lignesIndice.total === 3 && lignesIndice.indice.length === 3, lignesIndice.total + ' / ' + lignesIndice.indice.length);
  verifier('chaque ligne se lit « ancienne → nouvelle », puis l’état avant et après',
    lignesIndice.indice.every(l => l.type === 'solution' && /^[A-Z]{3}\d{4}A\d{6}[A-Z]$/.test(l.ancienne) &&
      l.nouvelle === '→ ' + l.ref && l.etats === 2), lu(lignesIndice.indice[0]));
  verifier('et nomme le plan', lignesIndice.indice.every(l => l.quoi.trim() !== ''));
  verifier('le filtre du journal reflète le choix',
    lignesIndice.presse === ':false termine:false encours:false afaire:false solution:true indice:false', lignesIndice.presse);
  await p.click('#filtre-journal button[data-journal="indice"]'); await p.waitForTimeout(400);
  // Le journal se replie à chaque rendu : seule la première semaine reste ouverte.
  for (let garde = 0; garde < 20; garde++) {
    const plie = await p.$('.journal-plier[aria-expanded="false"]');
    if (!plie) break;
    await plie.click(); await p.waitForTimeout(90);
  }
  await p.waitForTimeout(250);
  const lignesLettre = await p.evaluate(() => [...document.querySelectorAll('.journal-ligne')].map(b => b.dataset.type));
  verifier('le filtre « changements d’indice » n’en garde que trois, tous d’indice',
    lignesLettre.length === 3 && lignesLettre.every(t => t === 'indice'), lu(lignesLettre));
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
  verifier('solution et indice comptés dans les bulles font les six réémissions du journal',
    toutesLignes.filter(l => /changements? (d’indice|de solution)/.test(l.texte)).reduce((s, l) => s + Number(l.n), 0) === 6,
    lu(toutesLignes.filter(l => /changements? (d’indice|de solution)/.test(l.texte)).map(l => l.texte)));

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
  verifier('« essentielle » = 8 colonnes, la reference en tete',
    essentielle.length === 8 && essentielle[0] === 'reference', essentielle.join(','));
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
    etats: [...document.querySelectorAll('.etat-n')].map(e => e.textContent).join(' '),
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
    etats: [...document.querySelectorAll('.etat-n')].map(e => e.textContent).join(' '),
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
  /* Le cadrage d'ouverture suit aujourd'hui et les jalons (55 semaines sur
     la démo) : « 1 an » ne l'élargit pas forcément, il donne 52 semaines. */
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
  /* Un glissement parti d'une étiquette de jalon déplace la fenêtre comme
     partout ailleurs : il n'y a plus de poignée qui capte le geste. */
  const avantEtiquette = await derniereSemaine();
  const etiquetteEl = await p.$('.jalon-texte');
  if (etiquetteEl) {
    const bp = await etiquetteEl.boundingBox();
    await p.mouse.move(bp.x + bp.width / 2, bp.y + bp.height / 2);
    await p.mouse.down();
    for (let i = 1; i <= 8; i++) await p.mouse.move(bp.x + bp.width / 2 - i * 30, bp.y + bp.height / 2);
    await p.mouse.up(); await p.waitForTimeout(400);
  }
  verifier('glisser depuis une étiquette de jalon déplace la fenêtre, pas le jalon',
    !!etiquetteEl && (await derniereSemaine()) !== avantEtiquette, avantEtiquette + ' → ' + (await derniereSemaine()));
  await p.click('.segmente button[data-span="26"]'); await p.waitForTimeout(300);

  // =================================================================
  section('Jalons fixes');
  /* Les jalons viennent de la source, et d'elle seule : quatre par contrat en
     démonstration. Rien ne permet d'en poser, d'en déplacer ni d'en retirer —
     l'outil se consulte. */
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
  verifier('la démonstration a quatre jalons', fixes.source === 4, String(fixes.source));
  verifier('les quatre sont dessinés, avec leur texte',
    fixes.dessines === 4 && fixes.textes.length === 4 && fixes.textes.every(t => t.trim().length > 0),
    JSON.stringify(fixes.textes));
  verifier('aucune poignée, croix ni formulaire dans le DOM', fixes.poignees === 0 && !fixes.formulaire);
  verifier('aucun bouton dans le graphique', fixes.boutons === 0, String(fixes.boutons));
  verifier('le curseur du cadre reste la main du panoramique', fixes.curseur === 'grab', fixes.curseur);
  verifier('l\'indice ne promet plus de poser un jalon', !/poser/.test(fixes.indice), fixes.indice);
  verifier('aucun pont de sauvegarde des jalons', fixes.pont);
  /* Un clic sur une semaine, à venir ou passée, ne pose rien. */
  const zonesClic = await p.$$('.zone-clic');
  for (const k of [5, Math.round(zonesClic.length / 2)]) {
    const bz = await zonesClic[Math.max(0, zonesClic.length - k)].boundingBox();
    await p.mouse.move(bz.x + bz.width / 2, bz.y + bz.height / 2);
    await p.mouse.down(); await p.mouse.up(); await p.waitForTimeout(300);
  }
  await p.keyboard.press('Enter'); await p.keyboard.press('Delete'); await p.waitForTimeout(300);
  verifier('un clic sur une semaine ne pose rien, Entrée et Suppr ne changent rien',
    await p.evaluate(() => document.querySelectorAll('.jalon').length === 4 && !document.getElementById('champ-jalon')));
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
  // Retour à la source de démonstration, avec ses quatre jalons.
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
  // =================================================================
  /* Ce que trois relecteurs ont trouvé après le lot du débrief, et ce qui a
     été corrigé. Chaque test reproduit d'abord la situation qui cassait. */
  section('Relecture : les constats corrigés tiennent');
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await reinitialiser(p);

  // Le mode « Exemple » ne racontait que des « passés en terminé ».
  await p.click('#mode-donnees button[data-mode="exemple"]'); await p.waitForTimeout(900);
  const lotsExemple = await p.evaluate(() => (document.getElementById('comparatif').textContent || '').replace(/\s+/g, ' '));
  verifier('en exemple, le comparatif montre aussi passés en cours, nouveaux, disparus et une réémission',
    /passés en cours/.test(lotsExemple) && /nouveau/.test(lotsExemple) && /disparu/.test(lotsExemple) && /(indice|solution)/.test(lotsExemple),
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
  await p.click('#mode-donnees button[data-mode="reel"]'); await p.waitForTimeout(900);

  // Le pied « Jeu d'exemple » ne se lit que dans la démonstration.
  verifier('la démonstration dit « Jeu d’exemple » dans son pied',
    await p.evaluate(() => !document.getElementById('avertissement-demo').hidden &&
      /Jeu d'exemple/.test(document.querySelector('.pied').textContent)));

  // Le cadrage d'ouverture montre aujourd'hui et les quatre jalons configurés.
  const cadrage = await p.evaluate(() => ({
    jalons: document.querySelectorAll('svg.graphe .jalon').length,
    aujourdhui: [...document.querySelectorAll('svg.graphe text')].some(t => /aujourd/.test(t.textContent))
  }));
  verifier('à l’ouverture, les quatre jalons et « aujourd’hui » sont dans le cadre',
    cadrage.jalons === 4 && cadrage.aujourdhui, JSON.stringify(cadrage));

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
  const puceIndice = await p.$('.puce-delta[data-delta="solution"], .puce-delta[data-delta="indice"]');
  if (puceIndice) {
    await puceIndice.hover(); await p.waitForTimeout(250);
    verifier('la bulle des changements d’indice montre les paires ancienne → nouvelle',
      await p.evaluate(() => /→/.test(document.getElementById('bulle').innerText)));
  }
  await p.mouse.move(5, 5); await p.waitForTimeout(150);

  // Sous périmètre, le rapprochement sépare ce qui est dans le périmètre de ce qui est absent d'ici (tout contrat).
  await p.click('#choix-perimetre button:has-text("PERSO")'); await p.waitForTimeout(700);
  const rappPerso = await p.evaluate(() => (document.getElementById('rapprochement').textContent || '').replace(/\s+/g, ' '));
  verifier('sous périmètre, la phrase du rapprochement distingue le périmètre des absents d’ici',
    /périmètre/.test(rappPerso) && /absent/.test(rappPerso) && !/lignes là/.test(rappPerso), rappPerso.slice(0, 160));
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
    aujourdhui: [...document.querySelectorAll('svg.graphe text')].some(t => /aujourd/.test(t.textContent)),
    jalons: document.querySelectorAll('svg.graphe .jalon').length
  }));
  verifier('avec 113 relevés, l’ouverture montre encore aujourd’hui et les jalons',
    longOuverture.releves && longOuverture.aujourdhui && longOuverture.jalons === 4, JSON.stringify(longOuverture));
  await p.click('.commandes-graphe button[data-span="0"]'); await p.waitForTimeout(400);
  const longTout = await p.evaluate(() => ({
    aujourdhui: [...document.querySelectorAll('svg.graphe text')].some(t => /aujourd/.test(t.textContent)),
    jalons: document.querySelectorAll('svg.graphe .jalon').length
  }));
  verifier('et « Tout » les garde à l’écran', longTout.aujourdhui && longTout.jalons === 4, JSON.stringify(longTout));
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

  // Un paquet que le classeur n'a pas pu remplir : page vide qui l'explique, jamais la démonstration.
  {
    const ctxVide = await contexte();
    await ctxVide.addInitScript(() => {
      window.SUIVI_FWD_DONNEES = { ok: false, message: 'Feuille vide : aucun plan.', colonnes: [], plans: [], releves: [], jalons: [], contrats: [], contrat: '' };
    });
    const pv = await page(ctxVide, 'classeur vide');
    const vide = await pv.evaluate(() => ({
      alerte: !document.getElementById('alerte-source').hidden,
      texte: document.getElementById('alerte-source').textContent,
      lignes: document.querySelectorAll('#corps-tableau td.ref, #corps-tableau .ref').length,
      demo: document.getElementById('avertissement-demo').hidden,
      reel: document.querySelector('#mode-donnees button[data-mode="reel"]').getAttribute('aria-pressed')
    }));
    verifier('un paquet vide du classeur affiche son message, sans plan et sans la démonstration',
      vide.alerte && /Feuille vide/.test(vide.texte) && vide.lignes === 0 && vide.demo && vide.reel === 'true', JSON.stringify(vide));
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
    apresRech.jalons === 4 && !apresRech.stockes, JSON.stringify(apresRech));

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
    survie.jalons.length === 4 && !survie.jalons.some(t => /stock/.test(t)), JSON.stringify(survie.jalons));
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

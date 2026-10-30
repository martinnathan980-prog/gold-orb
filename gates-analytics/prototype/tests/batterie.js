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

/* « Tout effacer », dans le bandeau des filtres, n'existe que quand un
   filtre est posé (débrief 20 : le seul bouton de remise à zéro) : on ne
   clique que s'il est visible, sinon on remet l'etat a la main. */
async function reinitialiser(pg) {
  const bouton = await pg.$('#tout-effacer');
  if (bouton && await bouton.isVisible()) { await bouton.click(); }
  else {
    await pg.fill('#recherche', '');
    /* Débrief 27, lot D : la rangée des filtres de colonne était repliée tant
       qu'aucun filtre n'est posé. Débrief 28 : elle est toujours là, et vider
       un champ redessine les en-têtes (les autres champs sont remplacés) : on
       reprend à chaque fois le premier champ visible encore rempli, plutôt
       qu'une liste de champs relevée d'avance. */
    for (let k = 0; k < 20; k++) {
      const cle = await pg.evaluate(() => { const i = [...document.querySelectorAll('input[data-filtre]')].find(x => x.value !== '' && x.getClientRects().length > 0); return i ? i.dataset.filtre : null; });
      if (!cle) break;
      await pg.fill('input[data-filtre="' + cle + '"]', '').catch(() => {});
      await pg.waitForTimeout(50);
    }
  }
  await pg.waitForTimeout(400);
}
/* Débrief 29 (batterie) : après un changement de largeur, on attendait un
   délai fixe (300 à 600 ms) — trop court sur une machine chargée (le
   journal, les colonnes figées, la figure de la comparaison se remettent
   en page après coup), du temps perdu ailleurs. On attend maintenant ce que
   la page fait vraiment : son travail du « resize » (regroupé 160 ms), ses
   mesures à l'image suivante (ResizeObserver compris : deux images), et la
   fin de ses transitions. Au plus 5 s ; une largeur inchangée n'attend pas. */
async function redimensionner(pg, largeur, hauteur) {
  await pg.evaluate(([w, h]) => {
    if (!window.__veilleRedim) {
      window.__veilleRedim = true;
      let m = null;
      window.addEventListener('resize', () => {
        window.__redimFini = false; clearTimeout(m);
        m = setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(() => { window.__redimFini = true; })), 200);
      });
    }
    window.__redimFini = window.innerWidth === w && window.innerHeight === h;
  }, [largeur, hauteur]);
  await pg.setViewportSize({ width: largeur, height: hauteur });
  await pg.waitForFunction(w => window.innerWidth === w && window.__redimFini === true &&
    !document.getAnimations().some(a => a.playState === 'running' && isFinite(a.effect.getComputedTiming().endTime)),
    largeur, { timeout: 5000, polling: 'raf' }).catch(() => {});
}
/* Débrief 29 (batterie) : une page ouverte ou rechargée attendait un délai
   fixe (1,3 à 1,4 s) — sur une machine chargée, elle n'avait pas toujours
   fini de s'ouvrir (« après Vue essentielle puis rechargement » lisait la
   vue par défaut). On attend qu'elle se dise prête (data-suivi-fwd="pret",
   l'ouverture finie), 15 s au plus, et au moins le délai d'avant, que le
   reste de la batterie suppose (polices, mesures d'après l'image). */
async function attendrePrete(pg, minimum) {
  const t0 = Date.now();
  await pg.waitForFunction(() => document.documentElement.getAttribute('data-suivi-fwd') === 'pret' &&
    !(window.__ouverture && window.__ouverture().enCours), null, { timeout: 15000 }).catch(() => {});
  const reste = minimum - (Date.now() - t0);
  if (reste > 0) await pg.waitForTimeout(reste);
}
/* Débrief 27, lot D : les filtres de colonne se dépliaient d'un bouton
   (« Filtrer par colonne », X-A2). Débrief 28 : la rangée est toujours
   affichée et le bouton est retiré — on attend seulement qu'elle soit là. */
async function deplierFiltresColonne(pg) {
  await pg.waitForFunction(() => { const r = document.querySelector('tr.filtres'); return !!r && !r.hidden && r.getClientRects().length > 0; },
    null, { timeout: 5000 }).catch(() => {});
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
  /* Sur un gros extract, le tableau ne dessine d'abord qu'une tranche (le
     reste vient en descendant) ; cette batterie vérifie tout le reste sur
     TOUTES les lignes dessinées : elle lève le seuil. Les tranches ont leurs
     propres tests, côté add-on, sur un extract de 640 plans. Et elle rend la
     page d'un seul bloc, comme avant le débrief 23 : l'ouverture en deux
     temps a ses propres tests (prototype/tests/ouverture-page.js). */
  /* Débrief 27, lot D : un nouveau venu ouvre sur la « Vue essentielle », les
     colonnes vides de la sélection masquées. Les vérifications d'avant
     portent sur l'extract entier : elles partent du lecteur qui a choisi
     « Toutes les colonnes » et « Afficher » les colonnes vides — deux choix
     que la page retient (posés ici seulement si rien n'est encore retenu).
     Le nouveau venu a sa section (« Débrief 27 : le tableau des plans »),
     sur un contexte vierge ({ prefsVierges: true }). */
  async function contexte(opts = {}) {
    const { prefsVierges, ...options } = opts;
    const ctx = await nav.newContext(Object.assign({ viewport: { width: 1280, height: 950 } }, options));
    await ctx.addInitScript((retenir) => {
      window.SUIVI_FWD_BUDGET = 1e9; window.SUIVI_FWD_DIFFERER = false;
      if (retenir) {
        try { if (!localStorage.getItem('suivi-fwd:v1')) localStorage.setItem('suivi-fwd:v1', JSON.stringify({ vueTable: 'toutes', videsMontrees: true })); }
        catch (e) { /* sans stockage : la page ouvre sur ses valeurs par défaut */ }
      }
    }, !prefsVierges);
    return ctx;
  }
  async function page(ctx, etiquette = 'page') {
    const pg = await ctx.newPage();
    brancher(pg, etiquette);
    await pg.goto(URL);
    await attendrePrete(pg, 1300);
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
  /* Débrief 20 : les sections en panneaux allongent la page ; le tableau
     n'est plus dans la zone que le navigateur met en page à l'ouverture
     (content-visibility), et ses colonnes figées ne se posent qu'en
     paraissant. On l'amène à l'écran avant de les mesurer, puis on remonte.
     Elles se posent dans l'image qui suit : on attend qu'elles le soient
     (au plus 5 s) plutôt qu'un délai fixe, trop court sur une machine
     chargée ; si elles ne le sont jamais, le test plus bas le dit. */
  await p.evaluate(() => document.getElementById('cadre-tableau').scrollIntoView());
  await p.waitForFunction(() => {
    const g = [...document.querySelectorAll('tr.titres th.col-fige')].map(t => parseFloat(t.style.left));
    return g.length > 0 && g[0] === 0 && g.every((x, i) => i === 0 || x > g[i - 1]);
  }, null, { timeout: 5000, polling: 'raf' }).catch(() => {});
  const extrait = await p.evaluate(() => ({
    affichees: document.querySelectorAll('tr.titres th').length,
    ordre: [...document.querySelectorAll('tr.titres th')].map(t => t.dataset.cle),
    titres: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()),
    figees: [...document.querySelectorAll('tr.titres th.col-fige')].map(t => t.dataset.cle),
    gauches: [...document.querySelectorAll('tr.titres th.col-fige')].map(t => parseFloat(t.style.left)),
    /* Les deux colonnes sans intitulé qui restent, vides de bout en bout comme
       dans l'export réel : la structure de GATES se montre telle quelle, seule
       la première colonne — celle qu'Excel ajoute — s'efface. Débrief 27
       (B22) : une case vide s'écrit « — » (elle s'écrivait « - »). */
    col4: [...document.querySelectorAll('#corps-tableau tr')].every(tr =>
      tr.children[[...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'colonne_4')].textContent.trim() === '\u2014'),
    col5: [...document.querySelectorAll('#corps-tableau tr')].every(tr =>
      tr.children[[...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'colonne_5')].textContent.trim() === '\u2014')
  }));
  verifier('le tableau ouvre sur les 137 colonnes : l\'export entier, moins la seule vide sans intitule',
    extrait.affichees === COLONNES_TOTAL, extrait.affichees + ' / ' + COLONNES_TOTAL);
  verifier('« Colonne 1 », vide de bout en bout, n\'est pas dans les en-tetes',
    extrait.titres.indexOf('Colonne 1') === -1 && extrait.ordre.indexOf('colonne_1') === -1,
    extrait.titres.slice(0, 4).join(' | '));
  /* La seule entorse à l'ordre de la feuille : la colonne suivie vient
     juste après la référence. Le reste garde sa place. */
  verifier('la colonne suivie suit la référence ; « Colonne 4 » et « Colonne 5 », sans intitule et vides, restent a leur place',
    extrait.ordre[1] === 'avancement' && extrait.titres[3] === 'Colonne 4' && extrait.titres[4] === 'Colonne 5' && extrait.col4 && extrait.col5,
    extrait.titres.slice(0, 5).join(' | '));
  verifier('la reference ouvre le tableau : plus rien ne la precede',
    extrait.ordre[0] === 'reference', extrait.ordre[0]);
  verifier('la reference est figee, tout ce qui la precede et la colonne suivie avec elle',
    extrait.figees.length >= 2 &&
    extrait.figees[extrait.figees.length - 2] === 'reference' && extrait.figees[extrait.figees.length - 1] === 'avancement' &&
    extrait.figees.join(',') === extrait.ordre.slice(0, extrait.figees.length).join(','),
    JSON.stringify(extrait.figees));
  verifier('les colonnes figees se posent l\'une apres l\'autre',
    extrait.gauches[0] === 0 &&
    extrait.gauches.every((g, i) => i === 0 || g > extrait.gauches[i - 1]),
    JSON.stringify(extrait.gauches));
  await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(200);

  // =================================================================
  section('Les deux vues du tableau');
  const vTout = await p.evaluate(() => [...document.querySelectorAll('#vue-tableau button')]
    .map(b => b.dataset.vue + ':' + b.getAttribute('aria-pressed')).join(' '));
  /* Débrief 27 : « Toutes les colonnes » est ici le choix retenu du lecteur
     (voir contexte()) ; un nouveau venu, lui, ouvre sur la vue essentielle. */
  verifier('le choix retenu « toutes les colonnes » rouvre sur « toutes les colonnes »',
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
  verifier('la reference l\'ouvre, figee avec la colonne suivie',
    vEss.premiere.cle === 'reference' && vEss.figees === 2, JSON.stringify(vEss));
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
  section('Plus de mode « Exemple »');
  /* L'historique fabriqué n'existe plus : le classeur a ses relevés. Seule,
     la page dit qu'elle montre une démonstration ; il n'y a plus
     d'interrupteur, et tous les blocs sont remplis par la source elle-même. */
  const modeDepart = await p.evaluate(() => ({
    interrupteur: !!document.getElementById('mode-donnees') || !!document.querySelector('[data-mode="exemple"]'),
    bandeau: !!document.getElementById('bandeau-mode'),
    mot: document.getElementById('mot-mode').textContent.trim(),
    pied: !document.getElementById('avertissement-demo').hidden
  }));
  verifier('plus d\'interrupteur « Données réelles / Exemple » ; seule, la page dit « Démonstration » et son pied le rappelle',
    !modeDepart.interrupteur && modeDepart.bandeau && /^Démonstration — trois contrats fictifs/.test(modeDepart.mot) && modeDepart.pied,
    JSON.stringify(modeDepart));
  /* Débrief 15 : plus de bande « Depuis le relevé précédent » — le journal
     et la courbe le disent. */
  const blocsRemplis = () => p.evaluate(() => ({
    sansComparatif: !document.getElementById('comparatif') && !/Depuis le relevé précédent/.test(document.querySelector('section.avancement').textContent),
    journal: document.querySelectorAll('.journal-semaine').length > 0,
    finEstimee: [...document.querySelectorAll('.critique-date .v')]
      .some(v => /^S\d{1,2} · \S+ \d{4}$/.test(v.textContent.trim().replace(/[\u00a0\u202f]/g, ' '))),
    rythme: [...document.querySelectorAll('.critique-effort .v')].some(v => /sem\./.test(v.textContent)),
    courbe: document.querySelectorAll('svg.graphe circle').length >= 5,
    groupes: document.querySelectorAll('.critique-ligne').length > 0,
    plans: document.querySelectorAll('#corps-tableau tr').length
  }));
  const reelBlocs = await blocsRemplis();
  verifier('tous les blocs sont remplis',
    Object.keys(reelBlocs).every(k => reelBlocs[k]), JSON.stringify(reelBlocs));

  // =================================================================
  /* Plusieurs contrats, une seule page : le sélecteur vit dans le bandeau du
     haut — et nulle part ailleurs, le titre ne le répète pas — et changer de
     contrat recharge tout — comptes, historique, pied de page — en repartant
     des filtres et du cadrage par défaut. */
  section('Sélecteur de contrat');
  const sel0 = await p.evaluate(() => ({
    visible: !document.getElementById('choix-contrat').hidden &&
             document.getElementById('select-contrat').offsetParent !== null,
    /* Le bloc des réglages est en display: contents — sa boîte est vide ;
       on mesure le sélecteur lui-même. */
    haut: document.getElementById('select-contrat').getBoundingClientRect().bottom <=
          document.querySelector('.masthead').getBoundingClientRect().top + 1,
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
    journal: document.querySelectorAll('.journal-semaine').length,
    /* Le cadrage par défaut se reconnaît à ce qu'il montre : le repère du
       dernier relevé et tous les jalons du contrat — pas à un nombre de
       bandes, qui dépend de la source. */
    jalons: document.querySelectorAll('svg.graphe .jalon').length,
    aujourdhui: document.querySelectorAll('svg.graphe .repere-auj').length === 1,
    cadrage: [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')]
      .map(b => b.dataset.span).join(','),
    /* Débrief 27 (lot H, P-F12) : sans échéance à venir, « Échéances »
       reste à sa place, grisé (aria-disabled), au lieu de disparaître. */
    echeances: ((b) => !b.hidden && b.getAttribute('aria-disabled') !== 'true')(document.querySelector('.commandes-graphe .segmente button[data-span="jalons"]')),
    /* Débrief 28 : plus de surtitre au-dessus du titre (#contexte-page) ; le
       contrat montré se lit au menu du contrat et à la légende du tableau
       (« Plans GATES de THS : … »). */
    surtitre: !!document.getElementById('contexte-page'),
    option: (document.getElementById('select-contrat').selectedOptions[0] || {}).textContent || '',
    legende: (document.getElementById('legende-tableau') || {}).textContent || ''
  }));
  await p.selectOption('#select-contrat', 'THS'); await p.waitForTimeout(1200);
  const x2 = await lireContrat();
  verifier('changer de contrat change le nombre de plans', x2.plans > 0 && x2.plans !== TOTAL, String(x2.plans));
  verifier('et le pied de page', x2.pied !== pied0, x2.pied);
  /* Débrief 27 (lot H, B1, P-F11) : le titre ne dit toujours pas « contrat ».
     Débrief 28 : le surtitre (« THS · Définition électrique ») est retiré ;
     une capture dit encore quel contrat elle montre — le menu du contrat,
     dans le bandeau, et la légende du tableau le nomment. */
  verifier('le contrat courant est celui du sélecteur, que le menu et la légende du tableau nomment ; plus de surtitre au-dessus du titre (débrief 28)',
    x2.nom === 'THS' && x2.courant === 'THS' && !/contrat/i.test(x2.masthead) && !x2.surtitre && x2.option === 'THS' && /^Plans GATES de THS : /.test(x2.legende),
    JSON.stringify([x2.nom, x2.option, x2.surtitre, x2.legende]));
  verifier('les filtres et le cadrage repartent de zero : « Échéances » (ou six mois sans jalon à venir), le repère du dernier relevé',
    x2.filtres && x2.presse === 0 && x2.cadrage === (x2.echeances ? 'jalons' : '26') && x2.aujourdhui, JSON.stringify(x2));
  verifier('le bloc par groupe et le journal suivent le nouveau contrat',
    x2.groupes === x2.plans && x2.journal > 0, x2.groupes + ' / ' + x2.plans);
  await p.selectOption('#select-contrat', 'VRK'); await p.waitForTimeout(1200);
  const x3 = await lireContrat();
  verifier('un troisieme contrat a encore d\'autres comptes',
    x3.plans > 0 && x3.plans !== x2.plans && x3.plans !== TOTAL && x3.nom === 'VRK', String(x3.plans));
  await p.selectOption('#select-contrat', 'HDK'); await p.waitForTimeout(1200);
  const x1 = await lireContrat();
  verifier('revenir a HDK redonne les comptes initiaux',
    x1.plans === TOTAL && x1.etats === etats0 && x1.pied === pied0, JSON.stringify(x1));
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
        /* Débrief 27 (lot E, M9/B24) : les mots de la figure sont en HTML
           par-dessus le dessin (.venn) — ils se lisent dans la figure, plus
           dans son SVG, qui ne garde que les cercles et l'anneau. Le « · »
           des comptes tient au mot d'avant par une espace insécable. */
        const fig = document.getElementById('venn-rapprochement'), svg = fig.querySelector('svg');
        if (!svg) return null;
        const RAYON = 40;
        return {
          cercles: [...svg.querySelectorAll('circle.cercle-ici, circle.cercle-la')].map(c => c.getAttribute('class')).join(),
          bases: [...fig.querySelectorAll('.base-nom')].map(t => t.textContent).join(),
          comptes: [...fig.querySelectorAll('.base-compte')].map(t => t.textContent.replace(/\u00a0/g, ' ')).join(' | '),
          parts: [...svg.querySelectorAll('.donut-seg')].map(x => ({
            cle: x.getAttribute('data-cle'), n: +x.getAttribute('data-n'),
            cat: x.getAttribute('class').replace('donut-seg', '').replace('survole', '').trim(),
            degres: x.tagName === 'circle' ? 360 : Math.round(x.getTotalLength() / (2 * Math.PI * RAYON) * 360) })),
          cotes: [...fig.querySelectorAll('.cote')].map(g => ({
            cle: g.getAttribute('data-cle'), n: +(g.querySelector('.grand') || g.querySelector('.moyen')).textContent.replace(/\s/g, ''),
            mots: [...g.querySelectorAll('.petit')].map(t => t.textContent.replace(/^[\d\s ]+/, '')).join(' · '),
            zero: g.classList.contains('zero') })),
          commun: +fig.querySelector('.commun-n').textContent.replace(/\s/g, ''), motCommun: fig.querySelector('.commun-mot').textContent,
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
     filtre l'a redessinée entre-temps ; une fois par source.
     Débrief 27 (lot E) : c'est la figure entière (.venn : le dessin et ses
     mots en HTML) qui porte « anime », plus le seul SVG. */
  const animAvant = await p.evaluate(() => document.querySelector('#venn-rapprochement .venn').classList.contains('anime'));
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(400);
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(400);
  await p.evaluate(() => document.getElementById('venn-rapprochement').scrollIntoView({ block: 'center' }));
  /* Débrief 29 (batterie) : plus de délai fixe — on attend que la figure,
     parue, porte « anime » (5 s au plus) ; sa fin s'attend juste dessous. */
  await p.waitForFunction(() => document.querySelector('#venn-rapprochement .venn').classList.contains('anime'), null, { timeout: 5000, polling: 'raf' }).catch(() => {});
  const animApres = await p.evaluate(() => {
    const fig = document.querySelector('#venn-rapprochement .venn');
    return { anime: fig.classList.contains('anime'), texteVisible: parseFloat(getComputedStyle(fig.querySelector('.commun-n')).opacity) };
  });
  /* Débrief 27 : sur une machine chargée, l'animation tarde parfois à
     démarrer (le premier dessin après le défilement se fait attendre) : on
     attend qu'elle ait fini — 5 s au plus — avant de lire l'opacité. */
  const animFin = await p.evaluate(async () => {
    const fig = document.querySelector('#venn-rapprochement .venn');
    await Promise.race([Promise.all(fig.getAnimations({ subtree: true }).map(a => a.finished)), new Promise(r => setTimeout(r, 5000))]);
    return parseFloat(getComputedStyle(fig.querySelector('.commun-n')).opacity);
  });
  verifier('la figure ne s\'anime qu\'en paraissant à l\'écran, même redessinée par un filtre avant ; ses textes finissent pleinement visibles',
    !animAvant && animApres.anime && animFin === 1, JSON.stringify([animAvant, animApres, animFin]));
  await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(200);

  /* Débrief 14 : « la comparaison dit deux fois la même chose ». Plus de
     « Plan par plan » sous les cercles : les six verdicts, à droite, sont la
     seule liste. Un clic sur un verdict filtre les tableaux ET déplie ses
     plans sous sa ligne — comme une ligne d'ATA —, le chevron le dit ; un
     second clic retire l'un et l'autre. Un clic sur une référence réduit le
     tableau d'ici à ce plan ; une ligne seulement là ouvre le tableau de SEE
     sur elle. */
  const lireListe = () => p.evaluate(() => ({
    ancienne: !!document.querySelector('#liste-rapprochement, .rapp-liste-titre, .rapp-groupe'),
    groupes: [...document.querySelectorAll('#verdicts-rapprochement .verdict-bloc')].map(g => ({
      cle: g.dataset.lot, ouvert: g.dataset.ouvert,
      n: +g.querySelector('.verdict-n').textContent.replace(/\s/g, ''),
      expanded: g.querySelector('.verdict').getAttribute('aria-expanded'),
      presse: g.querySelector('.verdict').getAttribute('aria-pressed'),
      chevron: !!g.querySelector('.verdict .chevron'),
      lignes: g.querySelectorAll('.rapp-puce').length
    })),
    tableau: document.querySelectorAll('#corps-tableau tr').length
  }));
  const ouvrirLot = async cle => { await p.click('#verdicts-rapprochement button[data-rapp="' + cle + '"]'); await p.waitForTimeout(350); };
  /* La colonne NAME de SEE porte l'écriture de SEE — le A un cran trop tôt.
     Pour la comparer aux références de GATES, on décale le A d'un cran. */
  const deSEE = n => /^[A-Z]{3}\d{3}A\d{4}$/.test(n) ? n.slice(0, 6) + n.charAt(7) + 'A' + n.slice(8) : n;
  const li0 = await lireListe();
  verifier('une seule liste : les six verdicts à droite des cercles, chacun avec son chevron — plus de « Plan par plan » qui les répète dessous',
    !li0.ancienne && li0.groupes.map(g => g.cle).join() === 'accord,emission,avance,manque,attente,seul' &&
    li0.groupes.map(g => g.n).join() === [ACCORD, EMISSION, AVANCE, MANQUE, ATTENTE, SEUL].join() && li0.groupes.every(g => g.chevron),
    JSON.stringify(li0));
  verifier('à l\'ouverture, tous les verdicts sont repliés', li0.groupes.every(g => g.ouvert === 'false' && g.expanded === 'false' && g.lignes === 0),
    JSON.stringify(li0));
  await ouvrirLot('manque');
  const liManque = await lireListe();
  verifier('un clic sur un verdict le pose sur le tableau ET déplie ses plans sous sa ligne ; les autres restent repliés',
    liManque.groupes[3].ouvert === 'true' && liManque.groupes[3].expanded === 'true' && liManque.groupes[3].presse === 'true' &&
    liManque.groupes[3].lignes === MANQUE && liManque.tableau === MANQUE &&
    liManque.groupes.filter((g, k) => k !== 3).every(g => g.ouvert === 'false' && g.lignes === 0), JSON.stringify(liManque));
  const lirePuces = cle => p.evaluate(c => [...document.querySelectorAll('#verdicts-rapprochement .verdict-bloc[data-lot="' + c + '"] .rapp-puce')]
    .map(b => ({ ref: b.querySelector('.rapp-puce-ref').textContent, etat: b.dataset.etat, la: b.dataset.ligneLa, see: b.dataset.see,
      vers: (b.querySelector('.rapp-puce-vers') || { textContent: '' }).textContent,
      pastille: b.querySelector('.pastille') ? b.querySelector('.pastille').className.replace('pastille', '').trim() : null,
      couleur: b.querySelector('.pastille') ? (b.querySelector('.pastille').getAttribute('style') || '') : null, bulle: b.title })), cle);
  const rangees = { manque: await lirePuces('manque') };
  const legendePuces = await p.evaluate(() => [...document.querySelectorAll('#verdicts-rapprochement .verdict-corps .rapp-puces-legende > span')].map(s => s.textContent.trim()).join(','));
  for (const cle of ['avance', 'emission', 'seul']) { await ouvrirLot(cle); rangees[cle] = await lirePuces(cle); }
  const unSeulOuvert = await lireListe();
  verifier('un verdict à la fois : ouvrir le suivant replie le précédent', unSeulOuvert.groupes.filter(g => g.ouvert === 'true').map(g => g.cle).join() === 'seul',
    JSON.stringify(unSeulOuvert.groupes.map(g => g.cle + ':' + g.ouvert)));
  verifier('« validés, absents de SEE » : une puce par plan — pastille verte, référence, et la bulle dit Validé dans GATES, absent dans SEE, où mène le clic',
    rangees.manque.length === MANQUE && rangees.manque.every(r => /^[A-Z]{2}E\d{4}A\d{6}[A-Z]$/.test(r.ref) && r.etat === 'termine' && r.see === 'absent' &&
      r.pastille === '' && /--fait/.test(r.couleur) && r.vers === '' && r.bulle === 'Validé dans GATES · absent dans SEE — ne montrer que ce plan dans le tableau'),
    JSON.stringify(rangees.manque));
  verifier('« dans SEE, pas validés ici » : jamais validé côté GATES, présent côté SEE ; « autre indice » porte la lettre en violet ; « seulement dans SEE » n\'a ni plan ni pastille et mène au tableau de SEE',
    rangees.avance.length === AVANCE && rangees.avance.every(r => r.etat !== 'termine' && r.see === 'présent' && r.vers === '') &&
    rangees.emission.every(r => r.etat === 'termine' && /--fait/.test(r.couleur) && /^sous l’indice [A-Z] \([A-Z]{2}E\d{4}A\d{6}[A-Z]\)$/.test(r.see) && /^→ [A-Z]$/.test(r.vers)) &&
    rangees.seul.length === SEUL && rangees.seul.every(r => r.etat === undefined && r.la && r.see === 'présent' && r.pastille === null &&
      /^aucun plan dans GATES · présent dans SEE — voir cette ligne dans le tableau de SEE$/.test(r.bulle)),
    JSON.stringify([rangees.avance[0], rangees.emission[0], rangees.seul[0]]));
  /* Débrief 20 : la légende ne nomme que les valeurs de la liste — sous
     « validés, absents de SEE », une seule : pas de légende du tout. */
  verifier('en tête des plans dépliés d’un verdict d’une seule valeur, pas de légende', legendePuces === '', legendePuces);
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
  await ouvrirLot('accord');
  const li1 = await lireListe();
  /* Débrief 27 (lot E, D10, M2) : plus de zone qui défile dans la liste —
     elle retenait la molette et le doigt. Un gros lot montre ses 24
     premières puces, puis « Voir les N autres » déplie les autres sur place
     (toujours aucun renvoi au tableau) ; le focus passe à la première
     révélée, et la zone prend sa hauteur naturelle. */
  const plusAccord = await p.evaluate(() => (document.querySelector('#verdicts-rapprochement .verdict-bloc[data-lot="accord"] .rapp-voir-plus') || {}).textContent || null);
  verifier('déplier « validés et dans SEE » (' + ACCORD + ' plans) montre ses 24 premières puces, puis « Voir les ' + (ACCORD - 24) + ' autres » — aucun renvoi au tableau',
    li1.groupes[0].ouvert === 'true' && li1.groupes[0].lignes === 24 && plusAccord === 'Voir les ' + fr(ACCORD - 24) + ' autres' &&
    li1.groupes.slice(1).every(g => g.ouvert === 'false') &&
    await p.evaluate(() => !document.querySelector('#verdicts-rapprochement .rapp-groupe-suite, #verdicts-rapprochement [data-rapp-tout]')),
    JSON.stringify([li1.groupes[0], plusAccord]));
  await p.click('#verdicts-rapprochement .verdict-bloc[data-lot="accord"] .rapp-voir-plus'); await p.waitForTimeout(400);
  const toutAccord = await p.evaluate(() => {
    const puces = [...document.querySelectorAll('#verdicts-rapprochement .verdict-bloc[data-lot="accord"] .rapp-puce')];
    return { n: puces.length, plus: !!document.querySelector('#verdicts-rapprochement .rapp-voir-plus'), focus: puces.indexOf(document.activeElement),
             copier: (document.querySelector('#verdicts-rapprochement .verdict-bloc[data-lot="accord"] button[data-copier]') || {}).textContent };
  });
  verifier('« Voir les N autres » montre TOUS les plans du lot sur place, le focus sur la première puce révélée ; « Copier » copiait déjà tout',
    toutAccord.n === ACCORD && !toutAccord.plus && toutAccord.focus === 24 && toutAccord.copier === 'Copier (' + fr(ACCORD) + ')', JSON.stringify(toutAccord));
  const defile = await p.evaluate(() => {
    const corps = document.querySelector('#verdicts-rapprochement .verdict-bloc[data-lot="accord"] .verdict-corps');
    const page = document.documentElement, c = getComputedStyle(corps);
    return { defile: corps.scrollHeight > corps.clientHeight + 1, reglage: c.overflowY, plafond: c.maxHeight,
             retenue: c.overscrollBehaviorY, page: page.scrollWidth <= page.clientWidth + 1 };
  });
  verifier('le lot déplié prend sa hauteur naturelle : aucune zone qui défile ni ne retient le défilement de la page',
    defile.reglage === 'visible' && !defile.defile && defile.plafond === 'none' && defile.retenue === 'auto' && defile.page, JSON.stringify(defile));
  await ouvrirLot('accord');
  const replie = await lireListe();
  verifier('re-cliquer le verdict posé et déplié le replie et retire le filtre',
    replie.groupes[0].ouvert === 'false' && replie.groupes[0].presse === 'false' && replie.tableau === TOTAL, JSON.stringify(replie.groupes[0]));
  await ouvrirLot('manque');
  await p.click('#verdicts-rapprochement .verdict-bloc[data-lot="manque"] button[data-plan-rapp]'); await p.waitForTimeout(500);
  const clicPlan = await p.evaluate(() => ({
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    ref: (document.querySelector('#corps-tableau td.ref, #corps-tableau .ref') || {}).textContent,
    jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').replace(/\s+/g, ' ').trim()),
    base: document.querySelector('#choix-base button[aria-pressed="true"]').dataset.base,
    ouvert: (document.querySelector('#verdicts-rapprochement .verdict-bloc[data-ouvert="true"]') || { dataset: {} }).dataset.lot,
    puces: document.querySelectorAll('#verdicts-rapprochement .verdict-bloc[data-lot="manque"] .rapp-puce').length
  }));
  verifier('un clic sur une référence réduit le tableau GATES à ce plan, le bandeau le dit, et le verdict reste déplié',
    clicPlan.lignes === 1 && clicPlan.ref === rangees.manque[0].ref && clicPlan.base === 'ici' &&
    clicPlan.jetons.some(j => /Sélection : plan /.test(j)) && clicPlan.ouvert === 'manque' && clicPlan.puces === MANQUE, JSON.stringify(clicPlan));
  await p.click('.jeton .x'); await p.waitForTimeout(400);
  /* Un lot posé sur les plans d'ici cacherait toute ligne seulement là :
     le clic le retire. Le tableau de SEE se montre, cherché sur la ligne, le
     bandeau porte le jeton de cette recherche, et le focus se pose sur le
     bouton de base — qui survit au rendu. */
  await ouvrirLot('accord');
  await ouvrirLot('seul');
  await p.evaluate(() => { window.__valeurLa = document.querySelector('#verdicts-rapprochement .verdict-bloc[data-lot="seul"] button[data-ligne-la]').dataset.ligneLa; });
  await p.click('#verdicts-rapprochement .verdict-bloc[data-lot="seul"] button[data-ligne-la]'); await p.waitForTimeout(600);
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
  /* Le premier lot de plans d'ici qui a encore des plans sous ce périmètre,
     déplié ; son premier plan, et un filtre d'état qui l'exclut. */
  const lotPerso = await p.evaluate(() => ['manque', 'avance', 'emission', 'accord'].find(c => {
    const b = document.querySelector('#verdicts-rapprochement button[data-rapp="' + c + '"]');
    return b && !b.disabled;
  }));
  if (lotPerso) await ouvrirLot(lotPerso);
  const cible = await p.evaluate(() => {
    const b = document.querySelector('#verdicts-rapprochement .verdict-bloc[data-ouvert="true"] button[data-plan-rapp]');
    if (!b) return null;
    const bloc = b.closest('.verdict-bloc');
    return { ref: b.querySelector('.rapp-puce-ref').textContent, groupe: bloc.dataset.lot, etat: b.dataset.etat,
             puces: bloc.querySelectorAll('.rapp-puce').length, n: +bloc.querySelector('.verdict-n').textContent.replace(/\s/g, '') };
  });
  verifier('sous PERSO, un verdict déplié montre autant de plans que son nombre — ceux du périmètre',
    !!cible && cible.puces === cible.n && cible.n > 0, JSON.stringify(cible));
  const titres = await p.evaluate(() => {
    const j = document.querySelector('.titre-journal'), r = document.getElementById('titre-rapprochement');
    const cj = getComputedStyle(j), cr = getComputedStyle(r);
    return { tag: j.tagName, memePolice: cj.fontFamily === cr.fontFamily, memeTaille: cj.fontSize === cr.fontSize, taille: cj.fontSize };
  });
  verifier('le titre du journal est un h2, de la même police et de la même taille que les autres sections',
    titres.tag === 'H2' && titres.memePolice && titres.memeTaille, JSON.stringify(titres));
  const etatQuiExclut = cible && cible.etat === 'termine' ? 'encours' : 'termine';
  await p.click('#etats .etat-btn[data-etat="' + etatQuiExclut + '"]'); await p.waitForTimeout(400);
  await p.click('#verdicts-rapprochement .verdict-bloc[data-lot="' + (cible ? cible.groupe : 'manque') + '"] button[data-plan-rapp]'); await p.waitForTimeout(600);
  const sousFiltre = await p.evaluate(() => ({
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    ref: (document.querySelector('#corps-tableau td.ref, #corps-tableau .ref') || {}).textContent,
    jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').replace(/\s+/g, ' ').trim()),
    focus: document.activeElement ? document.activeElement.id : null
  }));
  /* Débrief 27, lot D (X-A1) : le focus va au titre de l'historique qui
     s'ouvre — il allait au bouton « GATES », sans rapport avec le geste. */
  verifier('sous un filtre d\'état qui l\'exclut et le périmètre PERSO, le clic sur un plan de la liste l\'affiche seul : l\'état s\'efface, le périmètre reste',
    !!cible && sousFiltre.lignes === 1 && sousFiltre.ref === cible.ref && sousFiltre.focus === 'titre-fiche-plan' &&
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
  /* Débrief 27 (B10) : « … pas encore dans SEE (rien d’anormal) » — la remarque
     entre parenthèses, plus après un deux-points (ici, dans le jeton du
     bandeau, la bulle, le nom de la figure et au singulier). */
  verifier('chaque verdict se lit en une phrase de tous les jours, qui se suffit à elle-même',
    r0.puces.map(x => x.phrase).join(' | ') === 'validés dans GATES et connus de SEE | dans SEE sous une autre lettre d’indice | dans SEE, mais GATES ne les dit pas validés | validés dans GATES, mais SEE ne les connaît pas | pas validés, et pas encore dans SEE (rien d’anormal) | lignes de SEE sans plan dans GATES',
    r0.puces.map(x => x.phrase).join(' | '));
  const F = r0.figure;
  verifier('deux cercles face à face, GATES plein à gauche avec ses validés, SEE en pointillé à droite avec ses lignes',
    F && F.cercles === 'cercle-ici,cercle-la' && F.bases === 'GATES,SEE' &&
    F.comptes === fr(TOTAL) + ' plans · ' + fr(TERMINES) + ' validés | ' + fr(LIGNES_SEE) + ' lignes', JSON.stringify(F && [F.cercles, F.bases, F.comptes]));
  verifier('dans le recouvrement, l\'anneau des plans en commun : ' + COMMUN + ', en trois parts vert / violet / ambre, dans l\'ordre des verdicts',
    F && F.commun === COMMUN && F.motCommun === 'en commun' &&
    F.parts.map(x => x.cle + '=' + x.n + ':' + x.cat).join(' ') === 'accord=' + ACCORD + ':accord emission=2:emission avance=12:avance',
    JSON.stringify(F && F.parts));
  const degres = F ? F.parts.reduce((t, x) => t + x.degres, 0) : 0;
  verifier('les parts sont à l\'échelle — le vert domine, ' + PCT + ' % des validés — mais la plus petite reste visible',
    F && F.parts[0].degres >= 300 && F.parts.every(x => x.degres >= 4) && degres >= 340 && degres <= 360, JSON.stringify(F && F.parts.map(x => x.degres)));
  verifier('à gauche, le nombre qui compte — 3 validés sans SEE, en alerte — et dessous, discret, ' + ATTENTE + ' pas encore dans SEE ; à droite, 5 seulement dans SEE',
    F && F.cotes.map(c => c.cle + '=' + c.n + ' ' + c.mots + (c.zero ? ' (zéro)' : '')).join(' | ') === 'manque=3 validés sans SEE | attente=' + ATTENTE + ' pas encore dans SEE | seul=5 seulement dans SEE',
    JSON.stringify(F && F.cotes));
  verifier('la figure se lit aussi à voix haute',
    F && F.aria === 'Comparaison GATES / SEE, sur ' + TOTAL + ' plans : ' + ACCORD + ' validés dans GATES et connus de SEE ; 2 dans SEE sous une autre lettre d’indice ; ' +
      '12 dans SEE, mais GATES ne les dit pas validés ; 3 validés dans GATES, mais SEE ne les connaît pas ; ' + ATTENTE +
      ' pas validés, et pas encore dans SEE (rien d’anormal) ; 5 lignes de SEE sans plan dans GATES.', F && F.aria);
  const rectsRapp = await p.evaluate(() => {
    const fig = document.getElementById('venn-rapprochement').getBoundingClientRect();
    const zone = document.getElementById('verdicts-rapprochement').getBoundingClientRect();
    const r = [...document.querySelectorAll('#verdicts-rapprochement button.verdict')].map(b => b.getBoundingClientRect());
    return { aDroite: zone.left >= fig.right, chevauche: r.some((a, i) => i > 0 && a.top < r[i - 1].bottom - 1), dedans: r.every(b => b.left >= zone.left - 1 && b.right <= zone.right + 1), n: r.length };
  });
  verifier('les verdicts sont une liste à droite de la figure, une ligne chacun, sans se chevaucher ni sortir du cadre',
    rectsRapp.n === 6 && rectsRapp.aDroite && !rectsRapp.chevauche && rectsRapp.dedans, JSON.stringify(rectsRapp));
  verifier('aucun n\'est pressé ni inactif au départ, les deux tableaux sont entiers',
    r0.puces.every(x => x.presse === 'false' && !x.inactif) && r0.lignes === TOTAL && r0.seconde === LIGNES_SEE && r0.jetons.length === 0,
    JSON.stringify([r0.lignes, r0.seconde, r0.jetons]));
  verifier('le moteur donne les mêmes comptes : 22 choses à vérifier, ' + TERMINES + ' validés, un lot par plan',
    r0.R && r0.R.total === 22 && r0.R.nbPlans === TOTAL && r0.R.nbLignes === LIGNES_SEE && r0.R.nbTermines === TERMINES &&
    r0.R.accord + r0.R.emission + r0.R.avance + r0.R.manque + r0.R.attente === TOTAL,
    JSON.stringify(r0.R && [r0.R.total, r0.R.nbPlans, r0.R.nbLignes, r0.R.nbTermines]));
  verifier('les verdicts croisent bien l\'état d\'ici : d\'accord et absents-de-SEE sont validés, les autres ne le sont pas',
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
  verifier('cliquer « dans SEE, pas validés ici » réduit le tableau d\'ici à 12 plans, et celui de SEE à leurs 12 lignes',
    rAv.lignes === 12 && rAv.seconde === 12, rAv.lignes + ' / ' + rAv.seconde);
  verifier('ce sont bien ces plans, des deux côtés',
    rAv.refsTableau.length === 12 && rAv.refsTableau.every(r => r0.R.refsAvance.indexOf(r) !== -1) &&
    rAv.secondeRefs.length === 12 && rAv.secondeRefs.every(r => r0.R.refsAvance.some(f => f.indexOf(deSEE(r)) === 0)), JSON.stringify(rAv.secondeRefs.slice(0, 3)));
  verifier('le bandeau nomme le filtre « Comparaison : dans SEE, pas validés ici », le verdict est pressé',
    rAv.jetons.length === 1 && rAv.jetons[0] === 'Comparaison : dans SEE, mais GATES ne les dit pas validés' &&
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
  verifier('« validés, absents de SEE » remplace la sélection : 3 plans ici, et le tableau de SEE le dit vide, avec le chemin du retour',
    rMa.lignes === 3 && rMa.jetons[0] === 'Comparaison : validés dans GATES, mais SEE ne les connaît pas' && rMa.seconde === 0 &&
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
  verifier('« validés et dans SEE » : les ' + ACCORD + ' plans, des deux côtés',
    rId.lignes === ACCORD && rId.seconde === ACCORD && rId.jetons[0] === 'Comparaison : validés dans GATES et connus de SEE', JSON.stringify([rId.lignes, rId.seconde]));
  await p.click('#verdicts-rapprochement button[data-rapp="accord"]'); await p.waitForTimeout(500);
  const rOff = await lireRapp();
  verifier('re-cliquer le verdict pressé retire le filtre',
    rOff.lignes === TOTAL && rOff.seconde === LIGNES_SEE && rOff.jetons.length === 0 && rOff.puces.every(x => x.presse === 'false'));
  await p.click('#verdicts-rapprochement button[data-rapp="attente"]'); await p.waitForTimeout(500);
  const rAt = await lireRapp();
  verifier('« pas encore dans SEE » : les ' + ATTENTE + ' plans qui attendent, et le tableau de SEE le dit vide',
    rAt.lignes === ATTENTE && rAt.seconde === 0 && rAt.secondeVide === 'Ces ' + fr(ATTENTE) + ' plans n’ont pas de ligne dans SEE. Les voir dans GATES' &&
    rAt.jetons[0] === 'Comparaison : pas validés, et pas encore dans SEE (rien d’anormal)', JSON.stringify([rAt.lignes, rAt.secondeVide]));
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
  /* La tête de la bulle est la phrase même du verdict, avec son compte. */
  verifier('survoler « dans SEE, mais GATES ne les dit pas validés » éclaire sa part de l\'anneau et ouvre la bulle : la phrase du verdict, la répartition par état dans GATES, le sens, où mène le clic',
    svAv.visible === 'true' && svAv.eclaire === 'avance' && /^12 dans SEE, mais GATES ne les dit pas validés/.test(svAv.texte) &&
    new RegExp('En cours dans GATES ' + nEnCours).test(svAv.texte) &&
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
  verifier('survoler la part verte de l\'anneau ouvre la bulle des plans d\'accord — avec leur part des validés — et l\'épaissit',
    svAn.visible === 'true' && svAn.eclaire === 'accord' && new RegExp('^' + ACCORD + ' validés dans GATES et connus de SEE').test(svAn.texte) &&
    new RegExp('part des validés de GATES ' + PCT + '\\s?%').test(svAn.texte), svAn.texte.slice(0, 120));
  const svMa = await survolRapp('#venn-rapprochement .cote[data-cle="manque"] .grand');
  verifier('survoler le 3 « validés sans SEE » ouvre sa bulle et souligne le nombre',
    svMa.visible === 'true' && svMa.eclaire === 'manque' && /^3 validés dans GATES, mais SEE ne les connaît pas/.test(svMa.texte) &&
    /à vérifier des deux côtés/.test(svMa.texte), svMa.texte.slice(0, 120));
  const svAt = await survolRapp('#venn-rapprochement .cote[data-cle="attente"] .moyen');
  verifier('survoler « pas encore dans SEE » dit que ce n\'est pas anormal, avec la répartition par état',
    svAt.visible === 'true' && svAt.eclaire === 'attente' && /pas validés, et pas encore dans SEE \(rien d’anormal\)/.test(svAt.texte) &&
    /À faire dans GATES/.test(svAt.texte), svAt.texte.slice(0, 120));
  const svSe = await survolRapp('#venn-rapprochement .cote[data-cle="seul"] .grand');
  verifier('survoler le 5 « seulement dans SEE » ouvre sa bulle',
    svSe.visible === 'true' && svSe.eclaire === 'seul' && /^5 lignes de SEE sans plan dans GATES/.test(svSe.texte), svSe.texte.slice(0, 120));
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
    rLien.lignes === 3 && rLien.jetons[0] === 'Comparaison : validés dans GATES, mais SEE ne les connaît pas' &&
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
    rPe.figure.comptes.indexOf(rPe.R.nbPlans + ' plans du périmètre · ' + rPe.R.nbTermines + ' validés') === 0 &&
    rPe.figure.cotes[2].mots === 'seulement dans SEE · tout le contrat', JSON.stringify([rPe.figure.comptes, rPe.figure.cotes[2]]));
  verifier('le verdict « seulement dans SEE » le dit aussi', rPe.puces[5].phrase === 'lignes de SEE sans plan dans GATES — tout le contrat', rPe.puces[5].phrase);
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(600);
  verifier('revenir à Tout redonne les 22 choses à vérifier', (await lireRapp()).R.total === 22);
  // Un lot posé suit le périmètre : le verdict et le tableau parlent des mêmes plans.
  await p.click('#verdicts-rapprochement button[data-rapp="avance"]'); await p.waitForTimeout(400);
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const rSuit = await lireRapp();
  verifier('un lot posé suit le périmètre : sous PERSO, le tableau compte ce que le verdict annonce',
    rSuit.puces[2].presse === 'true' && rSuit.lignes === rSuit.puces[2].n && rSuit.lignes < 12 && rSuit.jetons.indexOf('Comparaison : dans SEE, mais GATES ne les dit pas validés') !== -1,
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
  verifier('une seconde base vide : tous les validés lui manquent, les autres attendent, le reste est inactif, et la figure compte 0 ligne',
    !rVide.cache && rVide.R.manque === TERMINES && rVide.R.attente === TOTAL - TERMINES && rVide.puces[3].n === TERMINES && rVide.puces[3].phrase === 'validés dans GATES, mais Vide ne les connaît pas' &&
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
      reinit: !!document.getElementById('tout-effacer') && !document.getElementById('filtres-actifs').hidden
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
    s0.legende.join('|') === 'validé ici|autre indice|pas validé ici|seulement dans SEE', s0.legende.join('|'));
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
  await p.click('#tout-effacer'); await p.waitForTimeout(500);
  const sRz = await lireSeconde();
  verifier('« Tout effacer » vide aussi cette recherche, et ramène sur GATES',
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
  await p.click('#tout-effacer'); await p.waitForTimeout(500);
  const sReinit = await lireSeconde();
  verifier('« Tout effacer » ramène sur GATES, entier, sans lot',
    sReinit.iciMontre && sReinit.gates === TOTAL && sReinit.jetons.length === 0, JSON.stringify([sReinit.base, sReinit.gates, sReinit.jetons]));

  // =================================================================
  /* La figure et les verdicts aux largeurs intermédiaires, périmètre posé
     (la figure gagne une ligne, « tout le contrat ») : côte à côte quand la
     place le permet, l'un sous l'autre sinon — jamais de recouvrement, jamais
     hors du cadre, jamais de débord de page. Et la ligne de la phrase, avec
     le périmètre à sa droite, tient elle aussi. */
  section('La figure et les verdicts à toutes les largeurs');
  for (const largeur of [360, 681, 700, 740, 800, 860, 960, 1280]) {
    await redimensionner(p, largeur, 900);
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
  await redimensionner(p, 1280, 1000);

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
      semaines: grads.filter(t => /^S\d{1,2}$/.test(t)), avecAnnee: grads.filter(t => /^\d{4}-S/.test(t) && !/plans/.test(t)),
      annees: [...document.querySelectorAll('svg.graphe .annee')].map(t => t.textContent),
      pointsPleins: document.querySelectorAll('svg.graphe circle[fill="var(--fait)"][stroke="var(--surface)"]').length,
      /* Débrief 27 (B3, X-A12) : les barres prennent --barre-semaine (3:1 sur la surface ; --r4 faisait 2,2:1). */
      barres: document.querySelectorAll('svg.graphe path.barre-semaine[fill="var(--barre-semaine)"]').length,
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
    /* Le comparatif : les lignes du résumé commun — une par valeur
       d'arrivée, puis les changements d'indice, les nouveaux, les disparus. */
    const refsComparatif = C ? C.lignes.reduce((l, x) => l.concat(x.refs), []) : [];
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
    /* Débrief 27 (lot H, P-F5) : le périmètre porte sur toute la page — il
       est monté dans la barre des réglages, sur la ligne du contrat et de
       l'avancement, au-dessus du titre (il n'est plus dans la synthèse). */
    haut: document.getElementById('perimetre').getBoundingClientRect().bottom <=
          document.querySelector('.masthead').getBoundingClientRect().top + 1,
    horsDuTitre: !document.querySelector('.masthead #perimetre') && !document.querySelector('#section-synthese #perimetre') &&
                 document.querySelector('.masthead').textContent.indexOf('Périmètre ') === -1,
    dansLaLigne: !!document.querySelector('header#entete #portee #perimetre #choix-perimetre') &&
                 Math.abs((r => r.top + r.height / 2)(document.getElementById('choix-perimetre').getBoundingClientRect()) -
                          (r => r.top + r.height / 2)(document.getElementById('choix-indicateur').getBoundingClientRect())) <= 2 &&
                 document.getElementById('perimetre').getBoundingClientRect().left > document.getElementById('choix-indicateur').getBoundingClientRect().right,
    boutons: [...document.querySelectorAll('#choix-perimetre button')].map(b => ({
      val: b.dataset.perimetre, texte: b.textContent.trim(),
      n: +(b.querySelector('.n') || { textContent: '0' }).textContent.replace(/\s/g, ''),
      presse: b.getAttribute('aria-pressed')
    }))
  }));
  verifier('le sélecteur est là, dans la barre des réglages : sur la ligne de l’avancement, à sa droite, au-dessus du titre (plus dans la synthèse)',
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
  verifier('la courbe est dérivée du périmètre : dernier point = validés / plans PERSO, autant de relevés',
    perso.dernier.termine === perso.etats[0] && perso.dernier.total === nPerso &&
    perso.serie.length === tout0.serie.length, JSON.stringify(perso.dernier));
  verifier('chaque point du périmètre est plus petit que le point global de la même semaine',
    perso.serie.every((pt, k) => pt.total < tout0.serie[k].total && pt.termine <= tout0.serie[k].termine));
  verifier('la note du graphique nomme le périmètre', /^Historique · périmètre PERSO · \d+ relevés, de S\d{1,2} · \S+ \d{4} à S\d{1,2} · \S+ \d{4}$/.test(perso.note.replace(/[\u00a0\u202f]/g, ' ')), perso.note);
  verifier('le journal ne garde que les plans PERSO : aucun événement d’un plan BASE/OPTION',
    perso.evenements > 0 && perso.domainesJournal.join() === 'PERSO' && perso.lignesJournal <= tout0.lignesJournal,
    JSON.stringify(perso.domainesJournal) + ' ' + perso.evenements);
  verifier('le comparatif « depuis le relevé précédent » aussi',
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
  /* Débrief 27 (B23) : sous une tuile, la phrase dit la part choisie, dans
     le périmètre nommé (« 83 plans en Terminé · 36 % du périmètre PERSO »),
     au lieu de « 83 sur 83 plans validés dans la sélection ». */
  verifier('périmètre + état se cumulent : les validés PERSO, « sur » les plans PERSO',
    cumul.lignes === perso.etats[0] && cumul.compte === perso.etats[0] + ' plans sur ' + nPerso &&
    new RegExp('^' + perso.etats[0] + ' plans en .+ · \\d+ % du périmètre PERSO$').test(cumul.phrase.replace(/[\u00a0\u202f]/g, ' ').trim()) && cumul.jetons.length === 2, cumul.compte + ' / ' + cumul.phrase);
  verifier('la courbe reste celle du périmètre, et le dit',
    cumul.dernier.total === nPerso && /^Historique · périmètre PERSO/.test(cumul.note) &&
    /autres filtres ne s’appliquent pas/.test(cumul.note), cumul.note);
  await p.click('#tout-effacer'); await p.waitForTimeout(700);
  verifier('« Tout effacer » remet le périmètre à Tout',
    JSON.stringify(await lirePerimetre()) === JSON.stringify(tout0));
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(500);
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(700);
  verifier('le bouton « Tout » aussi', JSON.stringify(await lirePerimetre()) === JSON.stringify(tout0));
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(300);
  verifier('re-cliquer la puce pressée ne change rien', JSON.stringify(await lirePerimetre()) === JSON.stringify(tout0));


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
  /* Débrief 27, lot G : l'adresse suit désormais la vue (#…&perimetre=PERSO,
     google.script.history dans le classeur) — rechargée, la page se rouvre
     telle quelle. Rien n'est mémorisé dans le navigateur pour autant : la
     page ouverte par son adresse nue (le lien du classeur, un nouvel onglet)
     rouvre sur Tout. */
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(900);
  await p.reload(); await attendrePrete(p, 1400);
  verifier('débrief 27 : rechargée, la page garde le périmètre de son adresse (PERSO)',
    await p.evaluate(() => /perimetre=PERSO/.test(location.hash) &&
      document.querySelector('#choix-perimetre button[data-perimetre="PERSO"]').getAttribute('aria-pressed') === 'true'));
  await p.goto('about:blank'); await p.goto(URL); await p.waitForTimeout(1400);
  verifier('le périmètre n’est pas mémorisé : la page rouverte par son adresse nue est sur Tout',
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
      comparatif: C ? ((C.lignes.filter(l => l.cle === 'indice')[0] || { refs: [] }).refs).slice().sort() : null,
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
  verifier('le comparatif « depuis le relevé précédent » porte les réémissions de la dernière semaine',
    app.comparatif && app.comparatif.length >= 1 && lu(app.comparatif) === lu(app.attenduComparatif),
    lu(app.comparatif) + ' vs ' + lu(app.attenduComparatif));
  verifier('avec, pour chacun, l’ancienne et la nouvelle référence',
    app.reemissions && app.reemissions.length === app.comparatif.length &&
    app.reemissions.every(r => r.ancienne && r.ref && r.ancienne !== r.ref), lu(app.reemissions));

  /* La dernière semaine porte un changement d'indice : le filtre du journal
     est celui-là, et il n'y en a pas d'autre sorte. Débrief 18 : la rangée
     porte toutes les valeurs de la colonne, dans l'ordre des tuiles, puis
     les reculs et l'indice (débrief 23 : puis les nouveaux et les disparus). */
  const cleReem = 'indice';
  const domIndice = await p.evaluate(cle => {
    /* Débrief 23 : les nouveaux et les disparus ont aussi leur pilule, après l'indice, s'il y en a. */
    const evts = [].concat(...window.__journalAffiche().map(s => s.evenements));
    const sortes23 = [].concat(evts.some(e => e.type === 'nouveau') ? ['nouveaux'] : [], evts.some(e => e.type === 'disparu') ? ['disparus'] : []);
    return {
    pastille: !!document.querySelector('#filtre-journal button[data-journal="' + cle + '"] .pastille.indice'),
    comptes: [...document.querySelectorAll('.compte-passage[data-passage="indice"]')].map(b => b.textContent.replace(/\s+/g, ' ').trim()),
    /* Débrief 27 (lot B) : la rangée « Mouvements » range les reculs, puis
       les nouveaux, les disparus, et les changements d'indice en dernier. */
    boutons: !!document.querySelector('#filtre-journal button[data-journal="indice"]') &&
             !document.querySelector('#filtre-journal button[data-journal="solution"]') &&
             [...document.querySelectorAll('#filtre-journal button')].map(b => b.dataset.journal).join() ===
               ['', ...window.__valeurs().map(v => v.cle), 'reculs', ...sortes23, 'indice'].join()
    };
  }, cleReem);
  verifier('le filtre du journal « changement d’indice » est là, avec sa pastille violette', domIndice.pastille);
  verifier('chaque semaine concernée compte son changement d’indice, en bouton',
    domIndice.comptes.length === 6 && domIndice.comptes.every(t => /^1 changement d’indice$/.test(t)),
    lu(domIndice.comptes));
  verifier('et la rangée du journal : Tout, chaque valeur de la colonne dans l’ordre des tuiles, les reculs, (nouveaux, disparus,) l’indice',
    domIndice.boutons && await p.evaluate(() => !!document.querySelector('#filtre-journal button[data-journal="reculs"]')));
  const violet = await p.evaluate(() => {
    const fond = el => el && getComputedStyle(el).backgroundColor;
    return {
      filtre: fond(document.querySelector('#filtre-journal button[data-journal="indice"] .pastille')),
      verdict: fond(document.querySelector('#verdicts-rapprochement button[data-rapp="emission"] .pastille')),
      anneau: getComputedStyle(document.querySelector('#venn-rapprochement .donut-seg.emission')).stroke
    };
  });
  verifier('le violet du changement d’indice est le même partout : filtre du journal, verdict « autre indice », part de l’anneau',
    /^rgb/.test(violet.filtre) && violet.filtre === violet.verdict && violet.filtre === violet.anneau, JSON.stringify(violet));

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
  /* Un passage à « Non renseigné » se dit comme les autres, et se filtre
     comme eux : la barre du filtre a son bouton dès qu'il y en a un. */
  const filtreVide = await p.evaluate(() => !!document.querySelector('#filtre-journal button[data-journal="vide"]'));
  verifier('« passés à « Non renseigné » » se compte comme les autres passages : jamais un bouton que la barre du filtre ne saurait montrer',
    justesse.every(x => !x.effaceBouton) || filtreVide, JSON.stringify([justesse.some(x => x.effaceBouton), filtreVide]));
  /* Chaque filtre que le journal propose — les valeurs d'arrivée, les
     reculs (débrief 14 : ils ne sont plus des « passés à … »), l'indice. */
  const filtresPresents = await p.evaluate(() => [...document.querySelectorAll('#filtre-journal button[data-journal]:not([disabled])')].map(b => b.dataset.journal).filter(Boolean));
  verifier('le journal propose ses filtres, dont les reculs quand il y en a', filtresPresents.includes('indice') && filtresPresents.length >= 3, filtresPresents.join());
  for (const f of filtresPresents) {
    await p.click('#filtre-journal button[data-journal="' + f + '"]'); await p.waitForTimeout(300);
    await toutDeplier();
    const sousFiltre = await p.evaluate(f => {
      const v = window.__valeurs().find(x => x.cle === f);
      /* Les références attendues, tirées du journal lui-même : celles qui
         sont ARRIVÉES à la valeur (passages, reculs, réémissions). */
      const attendues = [].concat(...window.__journalAffiche().map(s => s.evenements))
        .filter(e => (e.type === 'change' || e.type === 'indice') && e.cApres === f && e.cAvant !== f).map(e => e.ref).sort().join();
      return {
        refs: [...document.querySelectorAll('.journal-ligne')].map(l => l.dataset.ref).sort().join() === attendues,
        lignes: document.querySelectorAll('.journal-ligne').length,
        pilule: Number(document.querySelector('#filtre-journal button[data-journal="' + f + '"] .n').textContent.replace(/\s/g, '')),
        comptes: [...document.querySelectorAll('.compte-passage[data-passage="' + f + '"] b')].reduce((t, b) => t + Number(b.textContent.replace(/\s/g, '')), 0),
        resume: [...document.querySelectorAll('.resume b')].reduce((t, b) => t + Number(b.textContent.replace(/\s/g, '')), 0),
        types: [...new Set([...document.querySelectorAll('.journal-ligne')].map(l => l.dataset.type))].sort().join(),
        arrivees: [...new Set([...document.querySelectorAll('.journal-ligne .etiq-etat.apres')].map(e => e.textContent.trim()))].join(),
        libelle: v ? v.libelle : null
      };
    }, f);
    /* Sous une valeur : tous les plans ARRIVÉS à elle — passages, reculs,
       réémissions —, chacun dans sa case de la semaine ; le compte de la
       pilule est le nombre de lignes. Sous « reculs » et « indice » : leur
       seule case. */
    verifier('sous « ' + f + ' », les lignes sont exactement celles que les comptes annoncent',
      sousFiltre.lignes === sousFiltre.pilule && sousFiltre.lignes === sousFiltre.resume &&
      (f === 'indice' ? sousFiltre.types === 'indice' && sousFiltre.lignes === sousFiltre.comptes
        : f === 'reculs' ? sousFiltre.types === 'change' && sousFiltre.lignes === sousFiltre.comptes
        /* Débrief 23 : sous « nouveaux » et « disparus », leur seule case. */
        : f === 'nouveaux' ? sousFiltre.types === 'nouveau' && sousFiltre.lignes === sousFiltre.comptes
        : f === 'disparus' ? sousFiltre.types === 'disparu' && sousFiltre.lignes === sousFiltre.comptes
        : /^(change|change,indice|indice)$/.test(sousFiltre.types) && sousFiltre.refs),
      JSON.stringify(sousFiltre));
  }
  await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(300);

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
      libelle: !!b.querySelector('.quoi')
    })),
    presse: [...document.querySelectorAll('#filtre-journal button')]
      .map(b => b.dataset.journal + ':' + b.getAttribute('aria-pressed')).join(' ')
  }));
  verifier('sous ce filtre, le journal ne montre que les six changements d’indice',
    lignesIndice.total === 6 && lignesIndice.indice.length === 6, lignesIndice.total + ' / ' + lignesIndice.indice.length);
  verifier('chaque ligne se lit « ancienne → nouvelle », puis l’état avant et après',
    lignesIndice.indice.every(l => l.type === 'indice' && /^[A-Z]{3}\d{4}A\d{6}[A-Z]$/.test(l.ancienne) &&
      l.nouvelle === '→ ' + l.ref && l.etats === 2), lu(lignesIndice.indice[0]));
  verifier('la ligne ne porte que la référence et le passage — plus le libellé du plan (« Faisceau 417 »)',
    lignesIndice.indice.every(l => !l.libelle));
  verifier('le filtre du journal reflète le choix',
    lignesIndice.presse.split(' ').filter(x => /:true$/.test(x)).join() === 'indice:true' && /^:false /.test(lignesIndice.presse), lignesIndice.presse);
  /* Débrief 27 (lot B) : le compte a déjà pressé « Changement d'indice » ; un
     second clic sur la pastille pressée reviendrait à « Tout ». On repart de
     « Tout » pour que la pastille, seule, donne ses lignes. */
  await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(300);
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
  const releves = bulles.filter(b => /Relevé de S\d{1,2}[\u00a0 ]· \S+[\u00a0 ]\d{4}/.test(b.texte));
  verifier('chaque semaine relevée a sa bulle « Relevé de S38 · sept. 2026 »', releves.length >= 5, String(releves.length));
  verifier('elle dit « validés N / total »',
    releves.every(b => /validés\s*\d+\s*\/\s*\d+/.test(b.texte)), (releves[0] || {}).texte);
  verifier('et « gain net sur le relevé précédent ±n » dès le deuxième relevé',
    releves.filter(b => /gain net sur le relevé précédent\s*[+\-−]?\s*\d/.test(b.texte)).length >= releves.length - 1);
  verifier('plus aucune référence de plan dans la bulle',
    releves.every(b => !/[A-Z]{3}\d{4}A\d{3}/.test(b.texte)), (releves.find(b => /[A-Z]{3}\d{4}A\d{3}/.test(b.texte)) || {}).texte);
  verifier('ni « et N autres »', releves.every(b => !/autres/.test(b.texte)));
  verifier('les semaines qui ont bougé donnent leurs comptes, dans les mots du journal : passés à « Validé »…',
    releves.filter(b => /passés? à « Terminé »/.test(b.texte.replace(/[\u00a0\u202f]/g, ' '))).length >= 3);
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
    /* Débrief 27 (lot H, P-F10) : la ligne de la semaine seule. Débrief 28 :
       la ligne de l'âge des chiffres (#fraicheur, « Chiffres du … · dernier
       relevé archivé … ») est retirée de l'en-tête. */
    t.ligne = document.querySelector('.masthead .semaine').textContent.replace(/\s+/g, ' ');
    t.fraicheur = !!document.getElementById('fraicheur');
    t.masthead = document.querySelector('.masthead').textContent.replace(/\s+/g, ' ');
    return t;
  });
  const attApres = attenduDuJour();   // la batterie dure : minuit peut tomber entre les deux
  verifier('sous le titre, la semaine d’aujourd’hui et ses dates exactes — celles de la vraie date, pas celles du dernier relevé',
    (semaineTitre.num === attAvant.num && semaineTitre.dates === attAvant.dates) ||
    (semaineTitre.num === attApres.num && semaineTitre.dates === attApres.dates),
    JSON.stringify([semaineTitre.num, semaineTitre.dates, attAvant, attApres]));
  /* Débrief 27 (lot H, P-F10, A-F13) : la ligne de la semaine reste muette
     sur le relevé. Débrief 28 : la ligne à part du dernier relevé archivé
     est retirée — l'en-tête ne dit plus ni « Chiffres du … » ni « dernier
     relevé archivé ». */
  verifier('la ligne de la semaine ne porte que la semaine d’aujourd’hui ; plus de ligne « Chiffres du … · dernier relevé archivé » sous elle (débrief 28)',
    !/dernier relevé|il y a/i.test(semaineTitre.ligne) && semaineTitre.sansMention && !semaineTitre.fraicheur &&
    !/Chiffres du|relevé archivé/i.test(semaineTitre.masthead),
    JSON.stringify(semaineTitre));
  /* Débrief 27 (B3) : un seul « maintenant » sur la courbe — le trait
     d'aujourd'hui, toujours nommé « aujourd'hui » ; le trait plein du
     « dernier relevé » est retiré (le dernier point garde son nombre, et le
     pointillé plat dit l'écart jusqu'à aujourd'hui). */
  verifier('le repère de la courbe dit « aujourd’hui » (un seul « maintenant »), quel que soit l’âge du dernier relevé',
    semaineTitre.repere === 'aujourd’hui',
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
        /* Débrief 27 : les relevés de démonstration portent leur date (lot B) ;
           déplacés dans le temps, ils la perdent — sinon la ligne de
           fraîcheur lirait l'ancienne. */
        const x = Object.assign({}, r, { semaine: window.__etiquetteISO(d) });
        delete x.date;
        return x;
      });
      window.__chargerSource(s);
    };
    const attendre = ms => new Promise(r => setTimeout(r, ms));
    poser(0); await attendre(600);
    /* Débrief 28 : plus de ligne de fraîcheur (#fraicheur) — ni son texte ni
       son ambre ne s'écrivent nulle part dans l'en-tête. */
    const ligne = () => ({ ligne: document.querySelector('.masthead .semaine').textContent.replace(/\s+/g, ' '),
      fraicheur: !!document.getElementById('fraicheur'), ambre: !!document.querySelector('.masthead .vieux'),
      entete: document.querySelector('.masthead').textContent.replace(/\s+/g, ' ') });
    const ajour = Object.assign(lu(), ligne());
    ajour.repere = ([...document.querySelectorAll('svg.graphe .repere-auj')].map(x => x.textContent)[0]) || '';
    poser(3); await attendre(600);
    const vieux = Object.assign(lu(), ligne());
    vieux.repere = ([...document.querySelectorAll('svg.graphe .repere-auj')].map(x => x.textContent)[0]) || '';
    vieux.palier = !!document.querySelector('svg.graphe .palier-attente');
    vieux.dernierRelevé = [...document.querySelectorAll('svg.graphe text')].some(t => /dernier relevé/.test(t.textContent));
    return { ajour, vieux };
  });
  verifier('un historique archivé cette semaine : le titre dit la semaine, la courbe dit « aujourd’hui »',
    deuxCas.ajour.iAuj === deuxCas.ajour.auj && !/dernier relevé/i.test(deuxCas.ajour.ligne) && !deuxCas.ajour.ambre && deuxCas.ajour.repere === 'aujourd’hui',
    JSON.stringify(deuxCas.ajour));
  /* Débrief 27 : la ligne de la semaine reste muette ; la courbe garde un
     seul repère, « aujourd'hui », à la semaine où l'on est, et le pointillé
     plat relie le dernier point à aujourd'hui (lot A, B3). Débrief 28 : la
     ligne de fraîcheur (l'âge du relevé, en ambre) est retirée — l'écart se
     lit au pointillé plat de la courbe, l'en-tête ne dit plus « il y a … ». */
  verifier('le même reculé de trois semaines : la ligne de la semaine reste muette, plus de ligne de fraîcheur (débrief 28) ; la courbe dit « aujourd’hui » à la semaine en cours, le pointillé plat montre l’écart',
    deuxCas.vieux.iAuj - deuxCas.vieux.auj === 3 && !/dernier relevé|il y a/i.test(deuxCas.vieux.ligne) &&
    !deuxCas.vieux.fraicheur && !deuxCas.vieux.ambre && !/il y a \d+ jours|relevé archivé/.test(deuxCas.vieux.entete) &&
    deuxCas.vieux.repere === 'aujourd’hui' && deuxCas.vieux.palier && !deuxCas.vieux.dernierRelevé,
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
    apresReprise.titre === deuxCas.vieux.titre && apresReprise.repere === 'aujourd’hui' && apresReprise.lignes > 0,   // débrief 27 : un seul repère
    JSON.stringify(apresReprise));
  /* ---------------------------------------------------------------
     Chercher dans une section : plus de barre qui cherche partout. Le
     journal, les groupes et la comparaison ont chacun leur petit champ, qui
     ne cherche que chez eux. Les références attendues sont prises dans le
     rapprochement et le journal, les écritures tapées sont fabriquées ici.
     --------------------------------------------------------------- */
  console.log('\n— Chercher dans une section —');
  await reinitialiser(p);
  /* Débrief 27, lot D (P-F23) : en plus des champs de section, « Chercher un
     plan » revient — pas comme une barre qui filtre toute la page, mais
     dans le sommaire collé : il ouvre l'historique du plan choisi. */
  const champs = await p.evaluate(() => ({
    global: !!document.getElementById('chercher-plan') || !!document.getElementById('champ-plan'),
    sommaire: !!document.querySelector('#sommaire #cherche-plan-champ[role="combobox"]'),
    journal: !!document.querySelector('#section-journal .panneau-tete + .ligne-filtres #recherche-journal'),
    groupe: !!document.querySelector('.ligne-filtres #filtre-groupe'),
    rapp: !!document.querySelector('#rapprochement .section-tete #recherche-rapp')
  }));
  verifier('pas de barre qui filtre toute la page : un champ dans le journal, les groupes et la comparaison, et « Chercher un plan » dans le sommaire',
    !champs.global && champs.sommaire && champs.journal && champs.groupe && champs.rapp, JSON.stringify(champs));
  const cibles = await p.evaluate(() => {
    const R = window.__rapprochement();
    const accord = R.accord[0].reference;
    const seul = R.lignes.filter(l => l.cat === 'seul')[0];
    let bouge = null;
    window.__journal().some(sem => sem.evenements.some(e => {
      if (e.type === 'change') { bouge = e.ref; return true; }
      return false;
    }));
    const semainesDe = bouge ? window.__journal().filter(sem => sem.evenements.some(e => e.ref === bouge)).length : 0;
    return { accord, seul: seul ? seul.ref : null, bouge, semainesDe };
  });
  const enSEE = r => r.slice(0, 6) + 'A' + r.charAt(6) + r.slice(8);
  const lignesTableau = () => p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length);
  const tableauAvant = await lignesTableau();

  // Le journal
  await p.fill('#recherche-journal', cibles.bouge.slice(0, 3).toLowerCase() + '-' + cibles.bouge.slice(3)); await p.waitForTimeout(450);
  const jr = await p.evaluate(() => ({
    refs: [...document.querySelectorAll('#zone-journal .journal-ligne')].map(b => b.dataset.ref),
    semaines: document.querySelectorAll('#zone-journal .journal-plier').length,
    ouvertes: document.querySelectorAll('#zone-journal .journal-plier[aria-expanded="true"]').length
  }));
  verifier('le champ du journal ne garde que les passages du plan cherché (minuscules et tirets compris)',
    jr.refs.length >= 1 && jr.refs.every(r => r === cibles.bouge), JSON.stringify(jr.refs));
  verifier('ses semaines — et elles seules — restent, ouvertes sur lui',
    jr.semaines === cibles.semainesDe && jr.ouvertes === jr.semaines, JSON.stringify([jr.semaines, jr.ouvertes, cibles.semainesDe]));
  verifier('chercher dans le journal ne touche pas au tableau', (await lignesTableau()) === tableauAvant);
  await p.fill('#recherche-journal', 'ZZZZZZ'); await p.waitForTimeout(450);
  verifier('rien trouvé : le journal le dit',
    /Aucun changement pour «\s?ZZZZZZ\s?»/.test(await p.evaluate(() => document.getElementById('zone-journal').textContent)));
  await p.fill('#recherche-journal', cibles.bouge.slice(0, 2)); await p.waitForTimeout(450);
  verifier('moins de trois caractères : le journal reste entier, replié',
    await p.evaluate(n => document.querySelectorAll('#zone-journal .journal-plier').length === n &&
      !document.querySelector('#zone-journal .journal-plier[aria-expanded="true"]'), (await p.evaluate(() => window.__journal().length))));
  await p.focus('#recherche-journal'); await p.keyboard.press('Escape'); await p.waitForTimeout(350);
  verifier('Échap vide le champ du journal', await p.evaluate(() => document.getElementById('recherche-journal').value === ''));

  // Les groupes
  await p.fill('#filtre-groupe', enSEE(cibles.accord).slice(0, 9)); await p.waitForTimeout(450);
  const gr = await p.evaluate(() => ({
    groupes: document.querySelectorAll('#zone-critique .critique-ligne').length,
    trouves: [...document.querySelectorAll('#zone-critique .groupe-refs.trouves .jeton-ud')].map(b => b.dataset.ud),
    blocs: document.querySelectorAll('#zone-critique .groupe-refs.trouves').length
  }));
  verifier('le champ des groupes trouve aussi un plan — écrit à la mode de SEE — et le montre sous son groupe, lui seul',
    gr.groupes >= 1 && gr.blocs === gr.groupes && gr.trouves.indexOf(cibles.accord) !== -1, JSON.stringify(gr));
  verifier('chercher dans les groupes ne touche pas au tableau', (await lignesTableau()) === tableauAvant);
  await p.click('#zone-critique .groupe-refs.trouves .jeton-ud[data-ud="' + cibles.accord + '"]'); await p.waitForTimeout(500);
  verifier('un clic sur le plan trouvé le montre dans le tableau',
    await p.evaluate(ref => { const l = [...document.querySelectorAll('#corps-tableau tr')]; return l.length >= 1 && l.every(tr => tr.textContent.indexOf(ref) !== -1); }, cibles.accord));
  await reinitialiser(p);
  await p.focus('#filtre-groupe'); await p.keyboard.press('Escape'); await p.waitForTimeout(350);

  // La comparaison
  await p.fill('#recherche-rapp', cibles.accord); await p.waitForTimeout(450);
  const rp = await p.evaluate(() => ({
    ouverts: [...document.querySelectorAll('#verdicts-rapprochement .verdict-bloc[data-ouvert="true"]')].map(g => g.dataset.lot),
    effaces: document.querySelectorAll('#verdicts-rapprochement .verdict-bloc.sans-trouve').length,
    puces: [...document.querySelectorAll('#verdicts-rapprochement .rapp-puce .rapp-puce-ref')].map(x => x.textContent),
    sur: [...document.querySelectorAll('#verdicts-rapprochement .rapp-sur')].map(x => x.textContent.replace(/\s+/g, ' ')),
    presses: document.querySelectorAll('#verdicts-rapprochement .verdict[aria-pressed="true"]').length
  }));
  verifier('le champ de la comparaison déplie le seul verdict du plan, sur lui — « 1 trouvé sur N » —, efface les autres, ne pose aucun filtre',
    rp.ouverts.length === 1 && rp.ouverts[0] === 'accord' && rp.puces.length === 1 && rp.puces[0] === cibles.accord &&
    rp.sur.length === 1 && /^1 trouvé sur \d+$/.test(rp.sur[0]) && rp.effaces === 5 && rp.presses === 0,
    JSON.stringify(rp));
  if (cibles.seul) {
    await p.fill('#recherche-rapp', cibles.seul); await p.waitForTimeout(450);
    verifier('une ligne que SEE est seule à connaître se cherche aussi',
      await p.evaluate(ref => {
        const g = [...document.querySelectorAll('#verdicts-rapprochement .verdict-bloc[data-ouvert="true"]')];
        return g.length === 1 && g[0].dataset.lot === 'seul' && g[0].querySelector('.rapp-puce-ref').textContent === ref;
      }, cibles.seul));
  }
  await p.fill('#recherche-rapp', 'ZZZZZZ'); await p.waitForTimeout(450);
  verifier('rien trouvé : la comparaison le dit',
    /Aucun plan de la comparaison ne contient «\s?ZZZZZZ\s?»/.test(await p.evaluate(() => document.getElementById('verdicts-rapprochement').textContent)));
  await p.focus('#recherche-rapp'); await p.keyboard.press('Escape'); await p.waitForTimeout(350);
  const rpApres = await p.evaluate(() => ({
    lots: document.querySelectorAll('#verdicts-rapprochement .verdict-bloc').length,
    ouverts: document.querySelectorAll('#verdicts-rapprochement .verdict[aria-expanded="true"]').length,
    effaces: document.querySelectorAll('#verdicts-rapprochement .verdict-bloc.sans-trouve').length
  }));
  verifier('Échap rend les six verdicts, repliés', rpApres.lots === 6 && rpApres.ouverts === 0 && rpApres.effaces === 0, JSON.stringify(rpApres));
  verifier('chercher dans la comparaison ne touche pas au tableau', (await lignesTableau()) === tableauAvant);

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
  verifier('sur le concept harnais, toute la page le suit : ses validés, son titre de groupe',
    surConcept.presse && surConcept.presse.indicateur === 'concept' && surConcept.ind.cle === brut.cleConcept &&
    /^Concept harnais par /.test(surConcept.titre), JSON.stringify(surConcept));
  verifier('le périmètre choisi reste posé quand on change d’avancement suivi', /PERSO/i.test(surConcept.perimetre), surConcept.perimetre);
  /* SEE ne connaît pas le concept harnais : le titre le nomme, et la
     comparaison des bases s'efface — la section comme l'interrupteur
     GATES | SEE du tableau. */
  const pageConcept = await p.evaluate(() => ({
    titre: document.getElementById('titre-page').textContent,
    rapp: document.getElementById('rapprochement').hidden,
    base: document.getElementById('choix-base').hidden
  }));
  verifier('sous le concept harnais, le titre devient « Suivi concept harnais » et la comparaison avec SEE disparaît',
    pageConcept.titre === 'Suivi concept harnais' && pageConcept.rapp && pageConcept.base, JSON.stringify(pageConcept));
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(500);
  const conceptTout = await lireSuivi();
  verifier('sur tout le contrat, les validés du concept sont ceux de sa colonne (' + brut.conceptTermine + '), le total inchangé',
    conceptTout.etats[0] === brut.conceptTermine && conceptTout.etats.reduce((a, b) => a + b, 0) === brut.total,
    JSON.stringify([conceptTout.etats, brut.conceptTermine]));
  verifier('sa courbe a son propre historique : les relevés qui ont gardé le concept', conceptTout.ind.releves >= 2 && conceptTout.ind.releves <= brut.relevesConcept + 1,
    JSON.stringify([conceptTout.ind, brut.relevesConcept]));
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(400);
  const lignesConcept = await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length);
  verifier('le filtre « Validés » du concept montre ses ' + brut.conceptTermine + ' plans dans le tableau', lignesConcept === brut.conceptTermine, String(lignesConcept));
  await p.click('#etats .etat-btn[data-etat="termine"]'); await p.waitForTimeout(300);
  await p.click('#choix-indicateur button[data-indicateur="def"]'); await p.waitForTimeout(700);
  const pageDef = await p.evaluate(() => ({
    titre: document.getElementById('titre-page').textContent,
    rapp: document.getElementById('rapprochement').hidden,
    base: document.getElementById('choix-base').hidden
  }));
  verifier('revenir à la définition rend « Suivi FWD » et la comparaison avec SEE',
    pageDef.titre === 'Suivi FWD' && !pageDef.rapp && !pageDef.base, JSON.stringify(pageDef));
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
  verifier('au singulier, chaque verdict s’accorde : « validé », « le connaît pas », « ligne de »',
    phrases1.join(' | ') === 'validé dans GATES et connu de SEE | dans SEE sous une autre lettre d’indice | dans SEE, mais GATES ne le dit pas validé | validé dans GATES, mais SEE ne le connaît pas | pas validé, et pas encore dans SEE (rien d’anormal) | ligne de SEE sans plan dans GATES',
    phrases1.join(' | '));
  verifier('et au pluriel, la forme attendue', /^validés dans GATES et connus de SEE/.test(phrases2[0]) && /lignes de SEE/.test(phrases2[5]), phrases2.join(' | '));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(700);
  verifier('les quatre états totalisent le nombre de plans', somme === TOTAL, somme + ' vs ' + TOTAL);
  verifier('le % est écrit dans la barre et correspond aux validés',
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

  /* Beaucoup de valeurs, ou de très petites : la barre passe en légende —
     une carte par valeur, dans l'ordre de la barre, sans filets — et le
     survol relie chaque carte à son segment, même large de quatre pixels. */
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const vals = ['Validé', 'En cours', 'A traiter', 'Check', 'Attente retour', 'Bloqué', 'Refusé', ''];
    const poids = [300, 150, 90, 40, 30, 3, 2, 25];
    s.plans.forEach((pl, i) => { let c = 0, j = 0; const r = i % 640; while (j < poids.length - 1 && r >= c + poids[j]) { c += poids[j]; j++; } pl.avancement = vals[j]; });
    window.__chargerSource(s);
  });
  await p.waitForTimeout(700);
  const legende = await p.evaluate(() => ({
    classe: document.getElementById('etats').className,
    filets: document.querySelectorAll('#filets i').length,
    cartes: [...document.querySelectorAll('#etats .etat-btn')].map(b => b.querySelector('.libelle').textContent + '|' + b.querySelector('.etat-pct').textContent.replace(/\s/g, ' ')),
    segments: [...document.querySelectorAll('#barre span[data-cle]')].map(x => ({ cle: x.dataset.cle, l: x.getBoundingClientRect().width })),
    ordre: [...document.querySelectorAll('#etats .etat-btn')].map(b => b.dataset.cle).join() === [...document.querySelectorAll('#barre span[data-cle]')].map(x => x.dataset.cle).join()
  }));
  verifier('huit valeurs dont deux minuscules : la barre passe en légende, sans filets, une carte par valeur dans l\'ordre de la barre',
    /en-legende/.test(legende.classe) && legende.filets === 0 && legende.cartes.length === 8 && legende.ordre, JSON.stringify(legende).slice(0, 300));
  verifier('chaque carte dit sa part, même petite (« 0,3 % »), et chaque segment reste visible (≥ 4 px)',
    legende.cartes.some(c => /\|0,3 %$/.test(c)) && legende.segments.every(x => x.l >= 3.5), JSON.stringify(legende.cartes));
  await p.hover('#etats .etat-btn[data-cle="refuse"]'); await p.waitForTimeout(250);
  const survolLegende = await p.evaluate(() => ({
    focalise: document.getElementById('barre').classList.contains('focalise'),
    eclaire: [...document.querySelectorAll('#barre span.eclaire')].map(x => x.dataset.cle).join(),
    carte: [...document.querySelectorAll('#etats .etat-btn.eclaire')].map(x => x.dataset.cle).join()
  }));
  verifier('survoler « Refusé » (2 plans) éclaire son segment et lui seul',
    survolLegende.focalise && survolLegende.eclaire === 'refuse' && survolLegende.carte === 'refuse', JSON.stringify(survolLegende));
  await p.mouse.move(5, 5); await p.waitForTimeout(200);
  verifier('en quittant la légende, la barre redevient entière', await p.evaluate(() => !document.getElementById('barre').classList.contains('focalise')));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(700);
  verifier('quatre grandes valeurs : les chiffres reviennent sous leurs segments, filets compris',
    await p.evaluate(() => !/en-legende/.test(document.getElementById('etats').className) && document.querySelectorAll('#filets i').length === 3));

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
  await deplierFiltresColonne(p);
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
  verifier('« Tout effacer » vide recherche et filtres',
    await p.evaluate(t => document.getElementById('recherche').value === '' &&
      [...document.querySelectorAll('input[data-filtre]')].every(i => i.value === '') &&
      (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));

  // =================================================================
  section('Tri du tableau');
  /* Débrief 29 (performance) : la boucle d'avant cliquait chaque colonne
     deux fois sur le tableau entier — 274 clics, chacun redessinant 640
     lignes × 137 colonnes (3 à 8 s le rendu, toutes les lignes dessinées
     d'un bloc par la batterie) : la batterie y passait des dizaines de
     minutes et finissait par manquer de mémoire. Même intention, en deux
     temps :
     1. TOUTES les colonnes, dans les deux sens, sur un échantillon de
        lignes (la recherche « GAE3 » : 16 plans, 120 colonnes non
        uniformes, comme l'extract entier) — un seul appel à la page, le
        clic de chaque en-tête et la lecture de l'état (lignes, sens,
        aria-sort, légende) faits sur place ;
     2. quelques colonnes de natures différentes (la colonne suivie, à son
        tri propre, une colonne texte, la dernière) cliquées pour de bon,
        dans les deux sens, sur le tableau entier : aucune ligne perdue. */
  const cles = await p.evaluate(() => [...document.querySelectorAll('tr.titres button[data-tri]')].map(b => b.dataset.tri));
  const lignesVues = () => p.evaluate(() => document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length);
  await p.fill('#recherche', 'GAE3');
  await p.waitForFunction(t => { const n = document.querySelectorAll('#corps-tableau tr').length; return n > 1 && n < t; }, TOTAL, { timeout: 5000 }).catch(() => {});
  const ECHANTILLON = await lignesVues();
  const triEchantillon = await p.evaluate(() => {
    const ths = () => [...document.querySelectorAll('tr.titres th')];
    const colonne = c => {
      const i = ths().findIndex(t => t.dataset.cle === c);
      return [...document.querySelectorAll('#corps-tableau tr')].map(tr => ({ t: tr.children[i].textContent.trim(), vide: tr.children[i].classList.contains('tiret-vide') }));
    };
    const cliquer = c => { const b = document.querySelector('tr.titres button[data-tri="' + c + '"]'); b.focus(); b.click(); };
    const etat = (c, sens) => {
      const th = ths().find(t => t.dataset.cle === c), b = th && th.querySelector('button[data-tri]');
      const nom = b ? b.textContent : '';
      const leg = (document.getElementById('legende-tableau') || {}).textContent || '';
      return !!th && th.getAttribute('aria-sort') === (sens ? 'ascending' : 'descending') &&
        document.querySelectorAll('tr.titres th[aria-sort="ascending"], tr.titres th[aria-sort="descending"]').length === 1 &&
        leg.indexOf(', triées par ' + nom + ', ordre ' + (sens ? 'croissant' : 'décroissant')) !== -1;
    };
    /* Les cases vides (« — ») restent en bas, dans les deux sens. */
    const videsEnBas = l => l.every((x, i) => !x.vide || l.slice(i).every(y => y.vide));
    const n0 = document.querySelectorAll('#corps-tableau tr').length;
    const fautes = [];
    /* Débrief 29 (B22) : « - » s'écrit « — » et se range avec les cases
       vides ; une colonne qui n'a plus qu'une seule valeur (« 1 », le reste
       « — ») ne peut pas s'inverser à l'œil : elle compte à part
       (uneValeur), vérifiée pour ses lignes et ses cases vides en bas. */
    let inversees = 0, uneValeur = 0;
    [...document.querySelectorAll('tr.titres button[data-tri]')].map(b => b.dataset.tri).forEach(c => {
      /* Un premier clic trie dans l'ordre croissant — sauf la colonne déjà
         triée (la référence, à l'ouverture), qu'il inverse : on clique alors
         jusqu'au croissant. */
      cliquer(c); if (!etat(c, true)) cliquer(c);
      const okAsc = etat(c, true), asc = colonne(c);
      cliquer(c);
      const okDesc = etat(c, false), desc = colonne(c);
      const tAsc = asc.map(x => x.t), tDesc = desc.map(x => x.t);
      if (asc.length !== n0 || desc.length !== n0) fautes.push(c + ' perd des lignes');
      else if (!okAsc || !okDesc) fautes.push(c + ' : sens, aria-sort ou légende faux');
      else if (!videsEnBas(asc) || !videsEnBas(desc)) fautes.push(c + ' : des cases vides remontent');
      else if (new Set(asc.filter(x => !x.vide).map(x => x.t)).size > 1 && tAsc.join('|') === tDesc.join('|')) fautes.push(c + ' ne s’inverse pas');
      else if (new Set(asc.filter(x => !x.vide).map(x => x.t)).size > 1) inversees++;
      else if (new Set(tAsc).size > 1) uneValeur++;
    });
    return { n0, colonnes: document.querySelectorAll('tr.titres button[data-tri]').length, inversees, uneValeur, fautes };
  });
  verifier('chaque colonne se trie dans les deux sens sans perdre de ligne — toutes les colonnes, sur un échantillon de lignes (sens, aria-sort et légende suivent, les cases vides restent en bas)',
    ECHANTILLON > 1 && ECHANTILLON < TOTAL && triEchantillon.n0 === ECHANTILLON && triEchantillon.colonnes === cles.length &&
    triEchantillon.inversees + triEchantillon.uneValeur >= 100 && triEchantillon.fautes.length === 0, JSON.stringify(Object.assign({ ECHANTILLON }, triEchantillon, { fautes: triEchantillon.fautes.slice(0, 5) })));
  await p.fill('#recherche', '');
  await p.waitForFunction(t => document.querySelectorAll('#corps-tableau tr').length === t, TOTAL, { timeout: 15000 }).catch(() => {});
  let triOk = true, triDetail = '';
  const colonneEntiere = c => p.evaluate(c => {
    const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === c);
    return [...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.children[i].textContent.trim());
  }, c);
  const sensDe = c => p.evaluate(c => (document.querySelector('tr.titres th[data-cle="' + c + '"]') || { getAttribute: () => '' }).getAttribute('aria-sort'), c);
  for (const cle of [...new Set(['avancement', 'ata', cles[cles.length - 1]])].filter(c => cles.indexOf(c) !== -1)) {
    await p.click(`tr.titres button[data-tri="${cle}"]`);
    await p.waitForFunction(c => (document.querySelector('tr.titres th[data-cle="' + c + '"]') || { getAttribute: () => '' }).getAttribute('aria-sort') === 'ascending', cle, { timeout: 15000 }).catch(() => {});
    const asc = await colonneEntiere(cle), sAsc = await sensDe(cle);
    await p.click(`tr.titres button[data-tri="${cle}"]`);
    await p.waitForFunction(c => (document.querySelector('tr.titres th[data-cle="' + c + '"]') || { getAttribute: () => '' }).getAttribute('aria-sort') === 'descending', cle, { timeout: 15000 }).catch(() => {});
    const desc = await colonneEntiere(cle), sDesc = await sensDe(cle);
    if (asc.length !== TOTAL || desc.length !== TOTAL) { triOk = false; triDetail = cle + ' perd des lignes'; break; }
    if (sAsc !== 'ascending' || sDesc !== 'descending') { triOk = false; triDetail = cle + ' : aria-sort ' + sAsc + '/' + sDesc; break; }
    if (asc.join('|') === desc.join('|') && new Set(asc).size > 1) { triOk = false; triDetail = cle + ' ne s\'inverse pas'; break; }
  }
  verifier('cliquées pour de bon sur le tableau entier, la colonne suivie, une colonne texte et la dernière se trient dans les deux sens sans perdre de ligne', triOk, triDetail);
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
      /* Débrief 27 : vueTable et videsMontrees disent « l'extract entier » ;
         la vérification porte sur « cachees ». */
      localStorage.setItem('suivi-fwd:v1', JSON.stringify({
        cachees: { ata: true, avancement: true, nom_installation: true, rpt: true }, vueTable: 'toutes', videsMontrees: true
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
    /* Débrief 19 : sur la ligne des pastilles, à droite — comme au journal. */
    dansTete: !!document.querySelector('.ligne-filtres #filtre-groupe') &&
      Math.abs(document.getElementById('filtre-groupe').getBoundingClientRect().right - document.getElementById('filtre-groupe').closest('.ligne-filtres').getBoundingClientRect().right) < 2,
    hauteur: Math.round(document.getElementById('filtre-groupe').getBoundingClientRect().height),
    largeur: Math.round(document.getElementById('filtre-groupe').getBoundingClientRect().width),
    loupe: !!document.querySelector('.recherche-groupe svg'),
    groupes: [...document.querySelectorAll('.critique-ligne')].map(l => l.dataset.groupe),
    compte: document.getElementById('compte-groupes').textContent,
    etats: [...document.querySelectorAll('#etats .etat-n')].map(e => e.textContent).join(' '),
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    points: document.querySelectorAll('svg.graphe circle').length
  }));
  verifier('le champ de filtre existe, sur la ligne des pastilles du bloc, au bout à droite, avec sa loupe',
    avantFiltre.champ && avantFiltre.dansTete && avantFiltre.loupe);
  verifier('son invite suit la dimension, et dit qu\'il trouve aussi un plan : « ATA ou plan… »',
    avantFiltre.placeholder === 'ATA ou plan…', avantFiltre.placeholder);
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
      /Ni groupe ni plan ne contient/.test(document.getElementById('zone-critique').textContent) &&
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
    apresDim.valeur === '' && apresDim.compte === '' && apresDim.placeholder === 'CC ou plan…' && apresDim.groupes > 0,
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
    const paquets = [...document.querySelectorAll('.groupe-refs .sous-groupe')].map(sg => {
      const t = sg.querySelector('.sous-titre');
      const n = t.querySelector('.n');
      /* Débrief 27 (lot C, B25) : le titre porte aussi la part de la
         sous-liste (« · 40 % », .part) après son compte. */
      const part = t.querySelector('.part');
      return {
        libelle: (t.textContent.slice(0, t.textContent.length - (n ? n.textContent.length : 0) - (part ? part.textContent.length : 0))).replace(/\s+/g, ' ').trim(),
        part: part ? Number(part.textContent.replace(/\D/g, '')) : NaN,
        n: n ? +n.textContent.replace(/\D/g, '') : NaN,
        pastille: !!t.querySelector('.pastille'),
        refs: [...sg.querySelectorAll('.jeton-ud')].map(b => ({
          ref: b.dataset.ud, etat: (b.getAttribute('title') || '').split(' — ')[0]
        }))
      };
    });
    const zone = document.getElementById('zone-critique');
    return {
      /* Débrief 20 : les plans à l'arrêt ouvrent la liste, sous leur titre,
         et ne se répètent pas dans les sous-listes par valeur. */
      arret: [...document.querySelectorAll('.groupe-refs .sous-arret .jeton-ud')].map(b => ({ ref: b.dataset.ud, etat: (b.getAttribute('title') || '').split(' — ')[0] })),
      jetons: refs.length, ud: refs.filter(b => b.dataset.ud).length,
      autres: /autres/.test(document.querySelector('.groupe-refs').textContent),
      paquets, valeurs: window.__valeurs(),
      entete: document.querySelector('.groupe-refs .entete').textContent,
      pastilles: refs.every(b => b.querySelector('.pastille')),
      mono: refs.every(b => /Mono|mono/.test(getComputedStyle(b).fontFamily)),
      dedans: refs.every(b => b.getBoundingClientRect().right <= zone.getBoundingClientRect().right + 1),
      /* Débrief 27 (lot C, D10) : plus de cadre qui défile — la liste prend
         sa hauteur dans la page. */
      naturel: zone.scrollHeight <= zone.clientHeight + 1 && getComputedStyle(zone).overflowY === 'visible' && getComputedStyle(zone).maxHeight === 'none',
      total: [...document.querySelectorAll('.groupe-refs .entete')].length,
      /* Débrief 28 : plus de « cliquez une référence… » ; « Filtrer la page
         sur ATA … » et « Copier (n) » côte à côte sur leur ligne
         (.actions-groupe), sous l'en-tête. */
      invite: /cliquez une référence/.test(document.querySelector('.groupe-refs').textContent),
      actions: (() => {
        const a = document.querySelector('.groupe-refs .actions-groupe');
        if (!a) return null;
        const f = a.querySelector('#filtrer-groupe-page'), c = a.querySelector('button.copier');
        const r = e => e.getBoundingClientRect();
        return { filtrer: !!f, copier: !!c && /^Copier \(\d+\)$/.test(c.textContent.trim()),
                 ordre: !!f && !!c && !!(f.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING),
                 coteACote: !!f && !!c && r(c).left >= r(f).right && Math.abs((r(c).top + r(c).height / 2) - (r(f).top + r(f).height / 2)) <= 2,
                 sousEntete: r(a).top >= r(document.querySelector('.groupe-refs .entete')).bottom - 1,
                 horsEntete: !document.querySelector('.groupe-refs .entete button') };
      })()
    };
  });
  const ordreValeurs = liste.valeurs.map(v => v.libelle);
  const familleDe = l => (liste.valeurs.find(v => v.libelle === l) || {}).famille;
  const parRef = refs => refs.every((r, i) => i === 0 || refs[i - 1].ref.localeCompare(r.ref, 'fr', { numeric: true }) <= 0);
  const restantsListe = liste.paquets.filter(q => familleDe(q.libelle) !== 'termine').reduce((t, q) => t + q.refs.length, 0) + liste.arret.length;
  verifier('deplier un groupe montre TOUTES ses references : autant de jetons que de plans',
    liste.ud === grosAta.total && liste.jetons === liste.ud, liste.ud + ' / ' + grosAta.total);
  verifier('plus aucun « et N autres »', !liste.autres);
  /* Débrief 13 : « c'est un peu le bordel ». Plus de tas « pas encore
     terminés » où les états se mêlaient : une sous-liste par valeur de la
     colonne, dans l'ordre de la barre du haut, chacune avec sa pastille et
     son compte. */
  verifier('une sous-liste par valeur, dans l’ordre de la barre du haut, chacune avec sa pastille et son compte',
    liste.paquets.length >= 2 &&
    liste.paquets.every((q, i) => ordreValeurs.indexOf(q.libelle) !== -1 &&
      (i === 0 || ordreValeurs.indexOf(liste.paquets[i - 1].libelle) < ordreValeurs.indexOf(q.libelle))) &&
    liste.paquets.every(q => q.pastille && q.n === q.refs.length) &&
    liste.paquets.reduce((t, q) => t + q.refs.length, 0) + liste.arret.length === grosAta.total,
    JSON.stringify(liste.paquets.map(q => [q.libelle, q.n, q.refs.length])));
  verifier('dans chaque sous-liste, un seul état — celui de son titre — et les références dans l’ordre',
    liste.paquets.every(q => q.refs.every(r => r.etat === q.libelle) && parRef(q.refs)),
    JSON.stringify(liste.paquets.map(q => [q.libelle, q.refs.slice(0, 2)])));
  /* Débrief 28 : l'en-tête dit combien, sans plus inviter à « cliquer une
     référence » ; ses deux gestes — filtrer la page, copier les références —
     sont côte à côte sur leur ligne, sous lui. */
  verifier('l’en-tête dit combien, sans « cliquez une référence… » ; « Filtrer la page sur ATA … » puis « Copier (n) », côte à côte sur leur ligne (débrief 28)',
    new RegExp('^' + grosAta.total + ' plans · ' + restantsListe + ' pas encore validés').test(liste.entete.trim()) &&
    !liste.invite && !!liste.actions && liste.actions.filtrer && liste.actions.copier && liste.actions.ordre && liste.actions.coteACote &&
    liste.actions.sousEntete && liste.actions.horsEntete, JSON.stringify([liste.entete.trim(), liste.invite, liste.actions]));
  verifier('des jetons compacts : pastille + reference en mono, aucun ne deborde',
    liste.pastilles && liste.mono && liste.dedans);
  /* Débrief 27 (lot C, D10, P-F4, B19) : le cadre de 430 px coupait une
     ligne en deux et gardait la molette ; la liste prend maintenant sa
     hauteur dans la page. */
  verifier('la liste dépliée prend sa hauteur dans la page : plus de cadre qui défile (débrief 27)', liste.naturel, JSON.stringify(liste.naturel));
  verifier('chaque sous-liste dit sa part du groupe (« · 40 % »), et les parts font 100 % (débrief 27, B25)',
    liste.paquets.every(q => q.part === Math.round(100 * q.refs.length / grosAta.total)), JSON.stringify(liste.paquets.map(q => [q.libelle, q.part, q.refs.length])));
  const refJeton = liste.paquets[liste.paquets.length - 1].refs[0].ref;
  await p.click(`.jeton-ud[data-ud="${refJeton}"]`); await p.waitForTimeout(600);
  verifier('un clic sur un jeton filtre le tableau sur ce plan',
    await p.evaluate(r => {
      const i = [...document.querySelectorAll('tr.titres th')].findIndex(t => t.dataset.cle === 'reference');
      const trs = document.querySelectorAll('#corps-tableau tr');
      return trs.length === 1 && trs[0].children[i].textContent.trim() === r &&
        [...document.querySelectorAll('.jeton')].some(j => j.textContent.indexOf(r) !== -1);
    }, refJeton), refJeton);
  /* Débrief 28 : le journal suit la page filtrée sur un plan — il ne garde
     que les changements de ce plan (tous, s'il en a). */
  const journalDuPlan = await p.evaluate(r => {
    const tous = window.__journal().reduce((l, s) => l.concat(s.evenements), []);
    const vus = window.__journalAffiche().reduce((l, s) => l.concat(s.evenements), []);
    return { tous: tous.length, duPlan: tous.filter(e => e.ref === r).length, vus: vus.length, autres: vus.filter(e => e.ref !== r).length,
             lignes: [...document.querySelectorAll('#zone-journal .journal-ligne[data-ref]')].filter(l => l.dataset.ref !== r).length };
  }, refJeton);
  verifier('la page filtrée sur ce plan, le journal ne montre que ses changements (débrief 28)',
    journalDuPlan.autres === 0 && journalDuPlan.lignes === 0 && journalDuPlan.vus === journalDuPlan.duPlan && journalDuPlan.vus < journalDuPlan.tous, JSON.stringify(journalDuPlan));
  /* Deux cents references d'un coup : une source ou tous les plans partagent
     le meme ATA. La liste doit rester lisible et defilable. */
  await p.evaluate(() => {
    const src = window.__jeuDExemple('HDK');
    src.plans.forEach(p => { p.ata = '21'; });
    window.__chargerSource(src);
  });
  await p.waitForTimeout(500);
  await p.click('.critique-ligne[data-groupe="21"]'); await p.waitForTimeout(700);
  /* Débrief 27 (lot C, D10) : plus de cadre qui défile. Les 640 puces sont
     là, une douzaine de rangées se montrent, « Voir les N autres plans »
     montre le reste sur place — et le replie. */
  const lireDeuxCents = () => p.evaluate(() => {
    const zone = document.getElementById('zone-critique');
    const refs = [...document.querySelectorAll('.jeton-ud')], vus = refs.filter(b => !b.hidden && b.getClientRects().length);
    const plus = document.querySelector('#zone-critique button[data-plus-refs]');
    return {
      jetons: refs.length, vus: vus.length, plans: document.querySelectorAll('#corps-tableau tr').length,
      defile: zone.scrollHeight > zone.clientHeight + 1,
      dedans: vus.every(b => b.getBoundingClientRect().right <= zone.getBoundingClientRect().right + 1),
      lignes: new Set(vus.map(b => Math.round(b.getBoundingClientRect().top))).size,
      plus: plus ? plus.textContent : null, deplie: plus ? plus.getAttribute('aria-expanded') : null
    };
  });
  const deuxCents = await lireDeuxCents();
  verifier('640 références dans un seul groupe : toutes là, en grille ; une douzaine de rangées montrées, puis « Voir les N autres plans de ce groupe » (débrief 27)',
    deuxCents.jetons === TOTAL && !deuxCents.defile && deuxCents.dedans && deuxCents.lignes >= 10 && deuxCents.lignes <= 14 &&
    deuxCents.plus === 'Voir les ' + (TOTAL - deuxCents.vus) + ' autres plans de ce groupe' && deuxCents.deplie === 'false', JSON.stringify(deuxCents));
  await p.click('#zone-critique button[data-plus-refs]'); await p.waitForTimeout(500);
  const deuxCentsTout = await lireDeuxCents();
  const focusPlus = await p.evaluate(() => document.activeElement && document.activeElement.classList.contains('jeton-ud'));
  verifier('« Voir les N autres plans » : les 640 se montrent sur place, le focus va à la première montrée, le bouton propose de réduire',
    deuxCentsTout.vus === TOTAL && deuxCentsTout.lignes > 20 && deuxCentsTout.plus === 'Réduire la liste des plans' && deuxCentsTout.deplie === 'true' && focusPlus,
    JSON.stringify([deuxCentsTout, focusPlus]));
  await p.evaluate(() => document.querySelector('#zone-critique button[data-plus-refs]').scrollIntoView({ block: 'center' }));
  const yReduire = await p.evaluate(() => document.querySelector('#zone-critique button[data-plus-refs]').getBoundingClientRect().top);
  await p.click('#zone-critique button[data-plus-refs]'); await p.waitForTimeout(500);
  const reduit = await p.evaluate(y => ({ vus: [...document.querySelectorAll('.jeton-ud')].filter(b => !b.hidden).length,
    saut: Math.round(document.querySelector('#zone-critique button[data-plus-refs]').getBoundingClientRect().top - y) }), yReduire);
  verifier('« Réduire la liste des plans » : retour à la douzaine de rangées, le bouton reste sous le pointeur',
    reduit.vus === deuxCents.vus && Math.abs(reduit.saut) <= 2, JSON.stringify(reduit));
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); });
  await p.waitForTimeout(500);
  await reinitialiser(p);

  // =================================================================
  section('Graphique : zoom, déplacement, extrêmes');
  /* Débrief 13 : le cadrage d'ouverture est « Échéances » — trois mois
     avant le dernier relevé, jusqu'à la semaine qui suit la dernière
     échéance : toutes les échéances à l'écran, la cinquième comprise, et
     rien au-delà. C'est celui du bouton « Échéances », pressé. */
  const cadrageOuv = await p.evaluate(() => {
    const zones = [...document.querySelectorAll('.zone-clic')].map(z => +z.dataset.i);
    const jal = [...document.querySelectorAll('svg.graphe .jalon')].map(g => +g.dataset.i);
    const auj = document.querySelector('svg.graphe .repere-auj');
    return {
      n: zones.length, premiere: Math.min(...zones), derniere: Math.max(...zones),
      jalons: jal, source: window.__jeuDExemple('HDK').jalons.length,
      horsFenetre: document.querySelectorAll('.legende-jalon.hors-fenetre').length,
      presses: [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')].map(b => b.dataset.span),
      premierBouton: document.querySelector('.commandes-graphe .segmente button').textContent.trim(),
      auj: !!auj
    };
  });
  verifier('le graphique s’ouvre sur « Échéances » : le premier bouton, seul pressé',
    cadrageOuv.presses.join() === 'jalons' && cadrageOuv.premierBouton === 'Échéances', JSON.stringify(cadrageOuv.presses));
  verifier('toutes les échéances sont à l’écran, la cinquième comprise, aucune « hors fenêtre »',
    cadrageOuv.jalons.length === cadrageOuv.source && cadrageOuv.source === 5 &&
    cadrageOuv.jalons.every(i => i >= cadrageOuv.premiere && i <= cadrageOuv.derniere) && cadrageOuv.horsFenetre === 0,
    JSON.stringify(cadrageOuv));
  verifier('le cadre s’arrête la semaine qui suit la dernière échéance, et montre le dernier relevé',
    cadrageOuv.derniere === Math.max(...cadrageOuv.jalons) + 1 && cadrageOuv.auj, JSON.stringify(cadrageOuv));
  await p.click('.segmente button[data-span="26"]'); await p.waitForTimeout(350);
  const zoom0 = await p.evaluate(() => document.querySelectorAll('.zone-clic').length);
  const presse0 = await p.evaluate(() => [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')].map(b => b.dataset.span).join());
  verifier('le bouton « 6 mois » cadre 26 semaines, et lui seul est pressé', zoom0 === 26 && presse0 === '26', zoom0 + ' ' + presse0);
  await p.click('.segmente button[data-span="jalons"]'); await p.waitForTimeout(350);
  const retourEch = await p.evaluate(() => ({
    n: document.querySelectorAll('.zone-clic').length,
    presses: [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')].map(b => b.dataset.span).join()
  }));
  verifier('« Échéances » y ramène', retourEch.n === cadrageOuv.n && retourEch.presses === 'jalons', JSON.stringify(retourEch));
  await p.click('.segmente button[data-span="52"]'); await p.waitForTimeout(350);
  const zoom1 = await p.evaluate(() => ({
    n: document.querySelectorAll('.zone-clic').length,
    presse: document.querySelector('.segmente button[data-span="52"]').getAttribute('aria-pressed')
  }));
  verifier('le bouton « 1 an » cadre 52 semaines et se marque pressé',
    zoom1.n === 52 && zoom1.presse === 'true', zoom0 + ' → ' + JSON.stringify(zoom1));
  /* Débrief 27 : la Synthèse a grandi (le verdict, « À vérifier ») — le graphique est d'abord ramené à l'écran, sinon son milieu tombait sous le bas de la fenêtre. */
  await p.evaluate(() => document.getElementById('cadre-graphe').scrollIntoView({ block: 'center' })); await p.waitForTimeout(150);
  const svg = await p.$('svg.graphe'); const box = await svg.boundingBox();
  await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  /* Débrief 27 (P-F1, X-A9) : le zoom passe par Ctrl + molette (la molette
     seule fait défiler la page). */
  await p.keyboard.down('Control');
  for (let i = 0; i < 30; i++) await p.mouse.wheel(0, -400);
  await p.waitForTimeout(400);
  const zoomMax = await p.evaluate(() => document.querySelectorAll('.zone-clic').length);
  verifier('30 crans de zoom avant laissent au moins une semaine', zoomMax >= 1, zoomMax + ' semaines');
  for (let i = 0; i < 60; i++) await p.mouse.wheel(0, 400);
  await p.keyboard.up('Control');
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
     partir de partout, y compris de la frise des jalons et de la marge basse.
     Débrief 27 : la Synthèse a grandi (le verdict, « À vérifier ») ; le
     cadre est ramené au milieu de l'écran avant d'en lire la place — en
     haut de page, son bas tombait sous la fenêtre. */
  let cadre = null;
  async function ramenerCadre() {
    await p.evaluate(() => document.getElementById('cadre-graphe').scrollIntoView({ block: 'center' })); await p.waitForTimeout(150);
    cadre = await (await p.$('#cadre-graphe')).boundingBox();
  }
  await ramenerCadre();
  /* La dernière semaine du cadre : celle de la dernière bande de survol. (Pas
     la dernière graduation : les mots posés sur la courbe, « fin S9… »,
     « manque 180 », passent après les traits des jalons.) */
  const derniereSemaine = () => p.evaluate(() =>
    [...document.querySelectorAll('svg.graphe .zone-clic')].map(z => z.dataset.i).slice(-1)[0]);
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
    indice: (document.querySelector('.commandes-graphe .indice') || { textContent: '' }).textContent,
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
      quand: e.querySelector('.quand').textContent.replace(/[\u00a0\u202f]/g, ' '), critique: e.classList.contains('critique'), hors: e.classList.contains('hors-perimetre'),
      autres: e.children.length - 3,
      focusable: e.tabIndex === 0 })),
    critiquesDessin: [...document.querySelectorAll('svg.graphe .jalon.critique')].map(g => g.dataset.jalon).join(',')
  }));
  /* Débrief 13 : « Diffusion PH base et la date, c'est nickel » — sous le
     nom, la semaine et rien d'autre : ni périmètre, ni « dans N jours ». */
  /* Débrief 27 (X-A8) : l'échéance manquée le dit aussi en mots, après sa
     semaine (« S51 · déc. 2026 · en retard ») — elle seule. */
  verifier('sous le graphique, la légende des jalons : « Jalons », puis chaque numéro, son texte et sa semaine — et « en retard » pour l’échéance manquée, rien d’autre —, atteignable au clavier',
    legendeJ.visible && legendeJ.mot === 'Jalons' && legendeJ.entrees.length === 5 &&
    legendeJ.entrees.every((e, i) => e.num === String(i + 1) && e.idx === String(i) && e.mot.length > 0 &&
      (e.critique ? /^S\d{1,2} · \S+ \d{4} · en retard$/ : /^S\d{1,2} · \S+ \d{4}$/).test(e.quand) && e.focusable) &&
    legendeJ.entrees.every(e => !/BASE|OPTION|PERSO|jour|demain|hier|FWD|concept/i.test(e.quand) && e.autres === 0) &&
    /* Sous la définition électrique, les diffusions TO — la table outil,
       concept harnais — restent dessinées, en retrait ; les autres comptent. */
    legendeJ.entrees.every(e => e.hors === /TO /.test(e.mot)) &&
    legendeJ.entrees[0].mot === 'Solde FWD' && legendeJ.entrees[1].quand === 'S2 · janv. 2027', JSON.stringify(legendeJ));
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
  verifier('plus de phrase d\'aide au-dessus du graphique : les périodes seules, à droite', fixes.indice === '', fixes.indice);
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
  /* Les jalons de cette source peuvent tomber hors du cadre d'ouverture :
     pour tous les lire, on montre tout l'axe. */
  await p.click('.commandes-graphe button[data-span="0"]'); await p.waitForTimeout(400);
  const lireEcheance = () => p.evaluate(() => ({
    prochain: window.__prochainJalon() && window.__prochainJalon().texte,
    entete: ((document.querySelector('.critique-tete button[data-trig="requis"], .critique-tete button[data-trig="vitesse"]') || {}).title || '').replace(/\u00a0/g, ' '),
    zone: document.getElementById('zone-critique').getAttribute('data-jalon'),
    retrait: [...document.querySelectorAll('.jalon.hors-perimetre .jalon-texte')].map(t => t.textContent),
    legende: document.getElementById('legende').textContent,
    aucun: [...document.querySelectorAll('svg.graphe text')].filter(t => /Aucun jalon/.test(t.textContent)).map(t => t.textContent).join('')
  }));
  const eTout = await lireEcheance();
  verifier('sur « Tout », le premier jalon à venir fait l\'échéance, périmètre ou pas, et l\'en-tête le nomme',
    eTout.prochain === 'Base seul' && /« Base seul » \(S51 · déc\. 2026\)/.test(eTout.entete) && eTout.zone === 'Base seul' && eTout.retrait.length === 0 &&
    /requis pour «\u00a0Base seul\u00a0»/.test(eTout.legende), JSON.stringify(eTout));
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(700);
  const ePerso = await lireEcheance();
  verifier('sous PERSO, l\'échéance saute au jalon Perso (casse indifférente) ; le jalon Base est dessiné en retrait',
    ePerso.prochain === 'Perso seul' && /« Perso seul » \(S2 · janv\. 2027\)/.test(ePerso.entete) && ePerso.zone === 'Perso seul' &&
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
  await p.click('.commandes-graphe button[data-span="0"]'); await p.waitForTimeout(400);
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
  verifier('sous PERSO sans jalon à venir : « rythme tenu », et le graphique dit « dans ce périmètre »',
    eRien.prochain === null && /Plans validés par semaine/.test(eRien.entete) && eRien.zone === '' &&
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
             titres: groupes.map(g => g.querySelector('title').textContent.replace(/[\u00a0\u202f]/g, ' ')), aria: groupes.map(g => g.getAttribute('aria-label')) };
  });
  verifier('cinq marqueurs numérotés 1 à 5, dans l\'ordre des jalons, chacun avec sa bulle « N — texte — semaine » et son aria « Jalon N, … »',
    dessinJ.n === 5 && dessinJ.nums === '1,2,3,4,5' && dessinJ.titres.every((t, i) => new RegExp('^' + (i + 1) + ' — .+ — S\\d{1,2} · \\S+ \\d{4}').test(t)) &&
    dessinJ.aria.every((a, i) => new RegExp('^Jalon ' + (i + 1) + ', ').test(a)), JSON.stringify([dessinJ.nums, dessinJ.titres]));
  verifier('les cinq numéros sur une seule rangée, sans étage, aucun ne touche l’autre, et aucun nom écrit sur le dessin — la légende les porte',
    dessinJ.chev.length === 0 && dessinJ.visibles === 0 && dessinJ.rangs === 1, JSON.stringify([dessinJ.chev, dessinJ.visibles, dessinJ.rangs]));
  /* Le panoramique et la molette marchent toujours, jalons compris. */
  await ramenerCadre();   // débrief 27 : à l'écran, la page a pu défiler depuis
  const avantPan = await derniereSemaine();
  await balayer(0.5, -1);
  verifier('le panoramique fonctionne toujours', (await derniereSemaine()) !== avantPan);
  const avantMolette = await p.evaluate(() => document.querySelectorAll('.zone-clic').length);
  await p.mouse.move(cadre.x + cadre.width * 0.5, cadre.y + cadre.height * 0.5);
  await p.keyboard.down('Control'); await p.mouse.wheel(0, -300); await p.keyboard.up('Control'); await p.waitForTimeout(300);   // débrief 27 : Ctrl + molette
  verifier('la molette (Ctrl + molette, débrief 27) fonctionne toujours',
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
  verifier('sans jalon, le graphique le dit — « Aucun jalon pour ce contrat », pas « à venir » — sans inviter à en poser',
    await p.evaluate(() => {
      const t = [...document.querySelectorAll('svg.graphe text')].map(x => x.textContent).find(x => /Aucun jalon/.test(x));
      return t === 'Aucun jalon pour ce contrat' && !/cliquez/.test(t);
    }));
  // Retour à la source de démonstration, avec ses cinq jalons.
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(400);

  // =================================================================
  section('Bloc par groupe : colonnes triables');
  const tris = await p.evaluate(() => [...document.querySelectorAll('button[data-trig]')].map(b => b.dataset.trig));
  verifier('cinq colonnes triables avec un jalon', tris.length === 5, JSON.stringify(tris));
  /* Débrief 21 : le nom du groupe part à gauche, juste après son chevron
     (centré, un nom long venait couvrir la flèche) ; le reste est centré. */
  verifier('les en-têtes sont centrés (sauf le nom, à gauche après le chevron, et la répartition)',
    await p.evaluate(() => {
      const c = [...document.querySelectorAll('.critique-tete > span')];
      return getComputedStyle(c[0]).justifyContent === 'flex-start'
        && c.filter(s => getComputedStyle(s).justifyContent === 'center').length === c.length - 2;
    }));
  verifier('les valeurs sont centrées, le nom du groupe à gauche',
    await p.evaluate(() => {
      const nom = document.querySelector('.critique-nom');
      return (!nom || getComputedStyle(nom).textAlign === 'left')
        && ['.critique-total', '.critique-fin', '.critique-effort', '.critique-date']
          .every(sel => { const e = document.querySelector(sel); return !e || getComputedStyle(e).textAlign === 'center'; });
    }));

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
  /* Le classement par défaut est « par ATA, dans l'ordre » — et il se voit :
     la colonne ATA est la colonne active, avec sa flèche. */
  const actifsDefaut = await p.evaluate(() => [...document.querySelectorAll('button[data-trig][data-actif="true"]')]
    .map(b => b.dataset.trig + (b.querySelector('.fleche') ? '+fleche' : '')).join(','));
  verifier('un troisième clic rend le classement par défaut : par ATA, colonne active et fléchée',
    actifsDefaut === 'nom+fleche', actifsDefaut);
  const parNom = await lire('nom');
  verifier('le tri par ATA est bien numérique et croissant',
    parNom.every((v, i) => i === 0 || Number(parNom[i - 1]) <= Number(v)), JSON.stringify(parNom));
  await p.click('button[data-trig="nom"]'); await p.waitForTimeout(280);
  const parNomInverse = await lire('nom');
  verifier('un clic sur ATA renverse l’ordre : décroissant',
    parNomInverse.every((v, i) => i === 0 || Number(parNomInverse[i - 1]) >= Number(v)) &&
      parNomInverse.join('|') === parNom.slice().reverse().join('|'), JSON.stringify(parNomInverse));
  await p.click('button[data-trig="nom"]'); await p.waitForTimeout(280);
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
  verifier('« fin estimée » est une semaine dite comme partout — « S18 · mai 2027 » —, « — » ou « validé »',
    coh.dates.every(v => /^S\d{1,2} · \S+ \d{4}$/.test(v.replace(/[\u00a0\u202f]/g, ' ')) || v === '—' || v === 'validé'), JSON.stringify(coh.dates));
  verifier('« rythme requis » se dit en plans par semaine, le rythme tenu dessous — un seul rythme (débrief 15)',
    coh.efforts.every(v => /^\d+,\d\/sem\.(tenu \d+,\d\/sem\.|rien de validé)$/.test(v) || /validé|—/.test(v)) &&
    !coh.efforts.some(v => /récent/.test(v)), JSON.stringify(coh.efforts.slice(0, 3)));

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
    verifier('la formule générale est donnée, avec les mots de la page', /rythme tenu\s*=/.test(aide.formules[0] || '') && /fin estimée\s*=/.test(aide.formules[0] || '') &&
      /rythme requis\s*=/.test(aide.formules[0] || ''));
    verifier('un exemple chiffré reprend une ligne réelle', /Exemple/.test(aide.texte) && aide.formules.length >= 2);
    verifier('les colonnes voisines sont expliquées aussi', aide.formules.length >= 3);
    verifier('le panneau ne déborde pas en largeur', !aide.scrollFormule);
    // L'exemple doit être refaisable : on recalcule à partir de ses propres nombres.
    const ex = aide.formules[1] || '';
    const mR = ex.match(/rythme tenu\s*=\s*(\d+)\s*÷\s*(\d+)\s*sem\.\s*=\s*([\d,]+)/);
    const mF = ex.match(/fin estimée\s*=\s*(\d+)\s*÷\s*([\d,]+)\s*=\s*(\d+)\s*semaines/);
    let calculOk = false, calculDetail = 'formule illisible';
    if (mR && mF) {
      const rythme = Number(mR[1]) / Number(mR[2]);
      const affiche = Number(mR[3].replace(',', '.'));
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
  /* Débrief 27 (lot C, P-F5) : « j'ai cliqué ATA 39 pour voir lesquels,
     et toute la page est devenue 6 sur 80 ». Une ligne cliquée ne fait
     plus que se déplier (aria-expanded) ; filtrer toute la page sur ce
     groupe est le bouton « Filtrer la page sur ATA … » de la liste
     dépliée — un second clic le retire. */
  const lignesDuBloc = () => p.evaluate(() => [...document.querySelectorAll('#zone-critique .critique-ligne')].map(l => ({
    g: l.dataset.groupe, n: +l.querySelector('.critique-total').textContent, presse: l.getAttribute('aria-expanded') === 'true',
    filtre: l.classList.contains('filtre-page') && !!l.querySelector('.marque-filtre'),
    /* Débrief 20 : le bouton « n à l'arrêt » se pose juste après la ligne. */
    ouvert: (s => !!(s && s.classList.contains('groupe-refs')))(l.nextElementSibling && l.nextElementSibling.classList.contains('critique-arret') ? l.nextElementSibling.nextElementSibling : l.nextElementSibling) })));
  const lignesTableau27 = () => p.evaluate(() => document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length);
  const avantGroupe = await lignesDuBloc();
  const noteAvant = await p.evaluate(() => document.getElementById('note-graphe').textContent);
  await p.click('.critique-ligne >> nth=0'); await p.waitForTimeout(400);
  const apresGroupe = await p.evaluate(() => ({
    compte: document.getElementById('compte').textContent,
    note: document.getElementById('note-graphe').textContent,
    presse: document.querySelectorAll('.critique-ligne[aria-expanded="true"]').length,
    jetons: document.querySelectorAll('#filtres-actifs .jeton').length,
    bouton: (document.getElementById('filtrer-groupe-page') || {}).textContent,
    focus: document.activeElement && document.activeElement.classList.contains('critique-ligne') && document.activeElement.dataset.groupe
  }));
  verifier('cliquer un groupe le déplie sans filtrer la page : tableau, courbe et bandeau des filtres inchangés (débrief 27)',
    apresGroupe.compte.indexOf(TOTAL + ' plans') !== -1 && apresGroupe.note === noteAvant && apresGroupe.jetons === 0, JSON.stringify(apresGroupe));
  verifier('une seule ligne est dépliée (aria-expanded), le focus reste sur elle, et sa liste offre « Filtrer la page sur ATA … »',
    apresGroupe.presse === 1 && apresGroupe.focus === avantGroupe[0].g && apresGroupe.bouton === 'Filtrer la page sur ATA ' + avantGroupe[0].g, JSON.stringify(apresGroupe));
  // Débrief 17 : un groupe cliqué se déplie sur place, comme une semaine du journal — les autres restent.
  const deplie17 = await lignesDuBloc();
  verifier('cliquer un groupe le déplie sur place : tous les autres groupes restent, avec leurs comptes, et ses plans s\'ouvrent juste sous lui',
    avantGroupe.length >= 5 && deplie17.map(l => l.g + '=' + l.n).join() === avantGroupe.map(l => l.g + '=' + l.n).join() &&
    deplie17[0].presse && deplie17[0].ouvert && deplie17.slice(1).every(l => !l.presse && !l.ouvert),
    JSON.stringify(deplie17.slice(0, 4)));
  /* Débrief 28 : le journal suit aussi les filtres de la page qui portent
     sur des plans (un groupe ATA/ECP, une liste de plans) — comme le reste
     de la page, il ne montre que les changements de leurs plans (Nathan :
     « ça filtre tout, sauf semaine par semaine »). */
  const journalDeLaPage = () => p.evaluate(() => {
    const evts = window.__journalAffiche().reduce((l, s) => l.concat(s.evenements), []);
    const refs = new Set([...document.querySelectorAll('#corps-tableau .ref-plan')].map(b => b.dataset.refPlan));
    const lignes = [...document.querySelectorAll('#zone-journal .journal-ligne[data-ref]')].map(l => l.dataset.ref);
    return { n: evts.length, refs: refs.size, horsTableau: evts.filter(e => !refs.has(e.ref)).map(e => e.ref).slice(0, 5),
             lignesHors: lignes.filter(r => !refs.has(r)).slice(0, 5), semaines: document.querySelectorAll('#zone-journal .journal-semaine').length };
  });
  const journalSansGroupe = await journalDeLaPage();
  await p.click('#filtrer-groupe-page'); await p.waitForTimeout(500);
  const journalDuGroupe = await journalDeLaPage();
  const filtre27 = await p.evaluate(() => ({
    compte: document.getElementById('compte').textContent, note: document.getElementById('note-graphe').textContent,
    jetons: [...document.querySelectorAll('#filtres-actifs .jeton')].map(j => j.textContent.replace('×', '').replace(/\s+/g, ' ').trim()),
    bouton: document.getElementById('filtrer-groupe-page').textContent, focus: document.activeElement && document.activeElement.id
  }));
  verifier('« Filtrer la page sur ATA … » filtre le tableau, la courbe suit le groupe et le nomme, le bandeau dit « ATA : … »',
    filtre27.compte.indexOf(TOTAL + ' plans') === -1 && /^Historique · \S+ /.test(filtre27.note) && filtre27.jetons.join() === 'ATA : ' + avantGroupe[0].g, JSON.stringify(filtre27));
  verifier('posé, le bouton dit comment le retirer, garde le focus, et la ligne porte l’entonnoir du filtre',
    filtre27.bouton === 'Retirer le filtre ATA ' + avantGroupe[0].g + ' de la page' && filtre27.focus === 'filtrer-groupe-page' && (await lignesDuBloc())[0].filtre, JSON.stringify(filtre27));
  verifier('le journal suit le filtre de la page sur ATA … : il ne garde que les changements des plans du groupe — tous dans le tableau filtré —, moins qu’avant (débrief 28)',
    journalSansGroupe.n > 0 && journalDuGroupe.n < journalSansGroupe.n && journalDuGroupe.horsTableau.length === 0 && journalDuGroupe.lignesHors.length === 0 &&
    journalDuGroupe.refs < journalSansGroupe.refs, JSON.stringify([journalSansGroupe, journalDuGroupe]));
  await p.click('.critique-ligne >> nth=2'); await p.waitForTimeout(400);
  const bascule17 = await lignesDuBloc();
  verifier('cliquer un autre groupe le déplie à la place du premier, la liste reste entière ; le filtre de la page reste sur le premier',
    bascule17.map(l => l.g + '=' + l.n).join() === avantGroupe.map(l => l.g + '=' + l.n).join() &&
    bascule17.filter(l => l.presse).length === 1 && bascule17[2].presse && bascule17[2].ouvert && !bascule17[0].ouvert &&
    bascule17[0].filtre && (await lignesTableau27()) === bascule17[0].n, JSON.stringify(bascule17.slice(0, 3)));
  await p.click('#filtrer-groupe-page'); await p.waitForTimeout(500);
  const lignesTableau17 = await lignesTableau27();
  const bascule27 = await lignesDuBloc();
  verifier('son bouton « Filtrer la page » fait suivre le tableau à ce groupe (un seul filtre de groupe)',
    lignesTableau17 === bascule27[2].n && bascule27[2].filtre && !bascule27[0].filtre, JSON.stringify([bascule27.slice(0, 3), lignesTableau17]));
  const journalAutreGroupe = await journalDeLaPage();
  await p.click('#filtrer-groupe-page'); await p.waitForTimeout(400);
  verifier('re-cliquer le bouton retire le filtre de la page, la ligne reste dépliée',
    (await lignesTableau27()) === TOTAL && (await lignesDuBloc())[2].presse);
  const journalRendu = await journalDeLaPage();
  verifier('le journal passe au groupe filtré à sa place (ses seuls plans), puis, le filtre retiré, rend tous les changements (débrief 28)',
    journalAutreGroupe.horsTableau.length === 0 && journalAutreGroupe.lignesHors.length === 0 && journalAutreGroupe.n < journalSansGroupe.n &&
    journalRendu.n === journalSansGroupe.n && journalRendu.semaines === journalSansGroupe.semaines, JSON.stringify([journalAutreGroupe, journalRendu, journalSansGroupe.n]));
  await p.click('.critique-ligne >> nth=2'); await p.waitForTimeout(350);
  verifier('re-cliquer la ligne la replie',
    (await lignesDuBloc()).every(l => !l.presse && !l.ouvert));
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
  verifier('« Tout effacer » remet tout d\'aplomb',
    await p.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t &&
      document.querySelectorAll('#etats .etat-btn[aria-pressed="true"]').length === 0, TOTAL));

  // =================================================================
  // =================================================================
  /* Ce que trois relecteurs ont trouvé après le lot du débrief, et ce qui a
     été corrigé. Chaque test reproduit d'abord la situation qui cassait. */
  section('Relecture : les constats corrigés tiennent');
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await reinitialiser(p);


  // Le pied « Démonstration » ne se lit que dans la démonstration.
  verifier('la démonstration dit « chiffres fictifs » dans son pied',
    await p.evaluate(() => !document.getElementById('avertissement-demo').hidden &&
      /Démonstration — les chiffres de cette page sont fictifs/.test(document.querySelector('.pied').textContent)));

  /* Le cadrage d'ouverture : « Échéances » — tous les jalons à l'écran. Le
     décompte en jours n'est plus écrit sous chaque jalon (le graphique le
     donne) : il se lit au survol, avec la semaine. */
  const cadrage = await p.evaluate(() => ({
    dessines: document.querySelectorAll('svg.graphe .jalon').length,
    legende: document.querySelectorAll('.legende-jalon').length,
    horsFenetre: document.querySelectorAll('.legende-jalon.hors-fenetre').length,
    decomptesEcrits: document.querySelectorAll('.legende-jalon .decompte').length,
    survols: [...document.querySelectorAll('.legende-jalon')].map(e => (e.getAttribute('title') || '').replace(/[\u00a0\u202f]/g, ' ')),
    aujourdhui: [...document.querySelectorAll('svg.graphe .repere-auj')].length === 1
  }));
  verifier('à l’ouverture, le repère du dernier relevé est dans le cadre, et les cinq jalons aussi : aucun « hors fenêtre »',
    cadrage.aujourdhui && cadrage.legende === 5 && cadrage.dessines === 5 && cadrage.horsFenetre === 0,
    JSON.stringify(cadrage));
  verifier('aucun « dans N jours » écrit sous les jalons ; le survol le dit, avec la semaine',
    cadrage.decomptesEcrits === 0 && cadrage.survols.length === 5 &&
    cadrage.survols.every(t => /S\d{1,2} · \S+ \d{4}, (dans \d+ jours|demain|aujourd’hui|hier|il y a \d+ jours)/.test(t)),
    JSON.stringify(cadrage.survols));

  // La ligne « changement d'indice » d'une semaine dépliée n'est plus reléguée derrière « voir les autres ».
  await p.click('.journal-semaine .journal-plier >> nth=0'); await p.waitForTimeout(300);
  verifier('un changement d’indice se lit dans la semaine dépliée sans ouvrir « voir les autres »',
    await p.evaluate(() => !!document.querySelector('.journal-semaine .journal-liste .ref-indice')));
  // On la replie : une semaine ouverte à la main le reste sous un filtre, et la dernière semaine a désormais un recul.
  await p.click('.journal-semaine .journal-plier >> nth=0'); await p.waitForTimeout(200);

  // Sous périmètre, le rapprochement sépare ce qui est dans le périmètre de ce qui est absent d'ici (tout contrat).
  await p.click('#choix-perimetre button:has-text("PERSO")'); await p.waitForTimeout(700);
  const rappPerso = await p.evaluate(() => (document.getElementById('rapprochement').textContent || '').replace(/\s+/g, ' '));
  verifier('sous périmètre, la section de comparaison distingue les plans du périmètre des lignes comptées sur tout le contrat',
    /plans du périmètre/.test(rappPerso) && /tout le contrat/.test(rappPerso) && !/lignes là/.test(rappPerso), rappPerso.slice(0, 160));
  await p.click('#choix-perimetre button:has-text("Tout")'); await p.waitForTimeout(700);

  // Le journal filtré reste replié ; la première semaine affichée se déplie d'un clic.
  // (Un filtre rare : les reculs — depuis le débrief 14, les « passés à À faire » de la démonstration en sont.)
  await p.click('#filtre-journal button[data-journal="reculs"]'); await p.waitForTimeout(500);
  const lireSemaine = () => p.evaluate(() => {
    const s = document.querySelector('.journal-semaine');
    return s ? { ouvert: s.querySelector('.journal-plier').getAttribute('aria-expanded'), lignes: s.querySelectorAll('.journal-ligne').length,
                 toutes: document.querySelectorAll('.journal-plier[aria-expanded="true"]').length } : null;
  });
  const journalFiltre = await lireSemaine();
  verifier('sous un filtre du journal, les semaines restent repliées',
    !!journalFiltre && journalFiltre.toutes === 0 && journalFiltre.lignes === 0, JSON.stringify(journalFiltre));
  await p.click('.journal-semaine .journal-plier >> nth=0'); await p.waitForTimeout(300);
  const journalDeplie = await lireSemaine();
  verifier('un clic déplie la première semaine affichée sur ses passages',
    !!journalDeplie && journalDeplie.ouvert === 'true' && journalDeplie.lignes > 0, JSON.stringify(journalDeplie));
  await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(400);

  // Un filtre de colonne se voit dans le bandeau, avec sa croix.
  await deplierFiltresColonne(p);
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
  verifier('avec 113 relevés, l’ouverture montre encore le repère du dernier relevé, et au moins le prochain jalon',
    longOuverture.releves && longOuverture.aujourdhui && longOuverture.jalons >= 1, JSON.stringify(longOuverture));
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
    await pp.click('#vue-tableau button[data-vue="essentielle"]');
    /* Débrief 29 (batterie) : la page retient le choix 400 ms après le geste
       (regroupé) ; sur une machine chargée, un délai fixe de 800 ms
       rechargeait parfois avant. On attend qu'il soit retenu (5 s au plus). */
    const retenu = (cle, val) => pp.waitForFunction(([k, v]) => { try { return JSON.stringify((JSON.parse(localStorage.getItem('suivi-fwd:v1')) || {})[k]) === JSON.stringify(v); } catch (e) { return false; } },
      [cle, val], { timeout: 5000 }).catch(() => {});
    await retenu('vueTable', 'essentielle');
    await pp.reload(); await attendrePrete(pp, 1400);
    /* Débrief 27, lot D (P-F15) : la vue choisie se retient — la page
       rouverte est sur « Vue essentielle » ; « Toutes les colonnes » rend
       ensuite l'extract dans l'ordre de la feuille (l'ordre mémorisé sous la
       vue essentielle est celui de la feuille). */
    const rouverteEss = await pp.evaluate(() => document.querySelector('#vue-tableau button[data-vue="essentielle"]').getAttribute('aria-pressed'));
    await pp.click('#vue-tableau button[data-vue="toutes"]'); await pp.waitForTimeout(800);
    const apresEssentielle = await pp.evaluate(() => ({
      toutes: document.querySelector('#vue-tableau button[data-vue="toutes"]').getAttribute('aria-pressed'),
      n: document.querySelectorAll('tr.titres th').length,
      tete: [...document.querySelectorAll('tr.titres th')].slice(0, 3).map(t => t.dataset.cle).join(',')
    }));
    verifier('après « Vue essentielle » puis rechargement, la page rouvre sur la vue essentielle ; « Toutes les colonnes » revient dans l’ordre de l’extract',
      rouverteEss === 'true' && apresEssentielle.toutes === 'true' && apresEssentielle.n === COLONNES_TOTAL && apresEssentielle.tete === 'reference,avancement,rpt',
      JSON.stringify([rouverteEss, apresEssentielle]));
    await pp.click('tr.titres button[data-tri="ata"]');
    await retenu('tri', { cle: 'ata', asc: true });
    await pp.reload(); await attendrePrete(pp, 1400);
    verifier('le tri d’une colonne survit au rechargement',
      await pp.evaluate(() => document.querySelector('th[data-cle="ata"]').getAttribute('aria-sort') === 'ascending'));
    await ctxPrefs.close();
  }

  // Un paquet que le classeur n'a pas pu remplir : plus de démonstration à
  // la place — la page le dit, avec le message du classeur, et dit le geste.
  {
    const ctxVide = await contexte();
    await ctxVide.addInitScript(() => {
      window.SUIVI_FWD_DONNEES = { ok: false, message: 'Feuille vide : aucun plan.', colonnes: [], plans: [], releves: [], jalons: [], contrats: [], contrat: '' };
    });
    const pv = await page(ctxVide, 'classeur vide');
    const ouverture = await pv.evaluate(() => ({
      alerte: !document.getElementById('alerte-source').hidden,
      texte: document.getElementById('alerte-source').textContent,
      mot: document.getElementById('mot-mode').textContent,
      lignes: document.querySelectorAll('#corps-tableau td.ref, #corps-tableau .ref').length,
      demo: !document.getElementById('avertissement-demo').hidden,
      vide: document.body.dataset.vide,
      panneau: getComputedStyle(document.getElementById('classeur-vide')).display !== 'none',
      sectionsCachees: [...document.querySelectorAll('section.avancement, section.bloc')].every(el => getComputedStyle(el).display === 'none')
    }));
    verifier('un classeur vide : ni plan fictif ni démonstration, le message du classeur, et la marche à suivre',
      ouverture.vide === 'true' && ouverture.panneau && ouverture.sectionsCachees && ouverture.lignes === 0 &&
      ouverture.alerte && /Feuille vide/.test(ouverture.texte) && !ouverture.demo && ouverture.mot === '',
      JSON.stringify(ouverture));
    await ctxVide.close();
  }

  section('Échéances en jours');
  /* Un jalon se donne à la semaine ; la page le dit en jours — jusqu'à sa
     date quand la configuration la donne, sinon jusqu'au vendredi de sa
     semaine. Le compte attendu est refait ici, à partir de la date portée
     par l'entrée de légende ou de l'étiquette ISO (dans sa bulle) et de la
     date du jour, sans passer par le code de la page. */
  await reinitialiser(p);
  await p.evaluate(() => window.scrollTo(0, 0));
  const joursAttendus = await p.evaluate(() => {
    return [...document.querySelectorAll('.legende-jalon')].map(el => {
      const m = el.dataset.semaine.match(/(\d{4})-S(\d{2})/);
      const an = +m[1], sem = +m[2];
      const j4 = new Date(Date.UTC(an, 0, 4));
      const lundi1 = new Date(j4.getTime() - ((j4.getUTCDay() + 6) % 7) * 86400000);
      const d = el.dataset.date ? el.dataset.date.split('-').map(Number) : null;
      const cible = d ? Date.UTC(d[0], d[1] - 1, d[2]) : lundi1.getTime() + ((sem - 1) * 7 + 4) * 86400000;
      const n = new Date(); const auj = Date.UTC(n.getFullYear(), n.getMonth(), n.getDate());
      return { idx: +el.dataset.jalon, jours: Math.round((cible - auj) / 86400000), date: el.dataset.date || '', nom: el.querySelector('.mot').textContent,
               /* Le décompte n'est plus écrit sous le jalon (débrief 13) : il se
                  lit au survol, juste après la semaine. */
               decompte: (((el.getAttribute('title') || '').replace(/[\u00a0\u202f]/g, ' ')
                 .match(/, (dans \d+ jours|demain|aujourd’hui|hier|il y a \d+ jours)/) || [])[1] || '') };
    });
  });
  const motAttendu = n => n === 0 ? 'aujourd’hui' : n === 1 ? 'demain' : n === -1 ? 'hier' : n > 1 ? 'dans ' + n + ' jours' : 'il y a ' + (-n) + ' jours';
  const espaces = t => t.replace(/[\s  ]+/g, ' ');
  verifier('chaque jalon dit, au survol, dans combien de jours il tombe — à sa date exacte (Solde FWD : mardi 15/12/2026)',
    joursAttendus.length === 5 && joursAttendus.every(j => espaces(j.decompte) === motAttendu(j.jours)) &&
    joursAttendus[0].date === '2026-12-15', JSON.stringify(joursAttendus));
  const titreEch = await p.evaluate(() => {
    const b = document.getElementById('echeance-titre');
    return { visible: !b.hidden && b.offsetParent !== null, texte: b.textContent, jalon: b.dataset.jalon,
             /* Pas sous le titre — il ne dit que la semaine — : en tête du graphique. */
             place: !b.closest('.masthead') && !!b.closest('.section-tete') &&
                    b.closest('.section-tete').querySelector('h2').textContent === 'Avancement dans le temps' };
  });
  const prochainAttendu = joursAttendus.filter(j => j.jours > 0)[0];
  verifier('en tête du graphique, la prochaine échéance, en jours — le titre, lui, ne dit que la semaine',
    titreEch.visible && titreEch.place && /Prochaine échéance/.test(titreEch.texte) && !!prochainAttendu &&
    titreEch.texte.indexOf(prochainAttendu.nom) !== -1 && espaces(titreEch.texte).indexOf(motAttendu(prochainAttendu.jours)) !== -1,
    JSON.stringify([titreEch, prochainAttendu]));
  await p.click('#echeance-titre'); await p.waitForTimeout(700);
  const fiche1 = await p.evaluate(() => {
    const f = document.getElementById('fiche-echeance');
    if (!f) return null;
    const chiffres = [...f.querySelectorAll('.fiche-echeance-chiffres > div')].map(d => ({ n: +d.querySelector('b').textContent.replace(/\s/g, ''), mot: d.querySelector('span').textContent }));
    const phrase = document.getElementById('phrase').textContent.replace(/\s/g, ' ');
    const m = phrase.match(/([\d ]+) sur ([\d ]+) plans?/);
    return { titre: f.querySelector('h3').textContent, chiffres, verdict: f.querySelector('.fiche-echeance-verdict').className,
             texte: f.textContent.replace(/\s+/g, ' '), restantsBarre: m ? +m[2].replace(/\s/g, '') - +m[1].replace(/\s/g, '') : null,
             ouvert: document.querySelector('.legende-jalon[aria-expanded="true"]') ? document.querySelector('.legende-jalon[aria-expanded="true"]').dataset.jalon : null };
  });
  verifier('un clic sur l’échéance du titre ouvre sa fiche : son nom, ses jours restants',
    !!fiche1 && fiche1.titre === prochainAttendu.nom && fiche1.chiffres[0].n === prochainAttendu.jours && /jours? restants?/.test(fiche1.chiffres[0].mot) &&
    fiche1.ouvert === String(prochainAttendu.idx), JSON.stringify(fiche1));
  verifier('la fiche dit combien de plans restent — ceux que la barre ne dit pas validés — et le rythme qu’il faut',
    !!fiche1 && fiche1.chiffres[2].n === fiche1.restantsBarre && /Il faut [\d,]+ plans validés par semaine/.test(fiche1.texte) &&
    /(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche) \d+ \S+ \d{4}/.test(fiche1.texte) && /(bon|mal)$/.test(fiche1.verdict), JSON.stringify(fiche1));
  // Un jalon d'un périmètre : ses plans à terminer sont ceux de ce périmètre.
  const jalonPerimetre = await p.evaluate(() => {
    /* Le périmètre d'un jalon ne s'écrit plus sous son nom (débrief 13) : il
       se lit dans son survol. */
    const el = [...document.querySelectorAll('.legende-jalon')].find(e => /périmètre BASE\/OPTION/.test(e.getAttribute('title') || ''));
    return el ? +el.dataset.jalon : null;
  });
  verifier('la démonstration a un jalon BASE/OPTION, que son survol nomme', jalonPerimetre !== null);
  if (jalonPerimetre !== null) {
    await p.click('.legende-jalon[data-jalon="' + jalonPerimetre + '"]'); await p.waitForTimeout(500);
    const fichePer = await p.evaluate(() => {
      const f = document.getElementById('fiche-echeance');
      return f ? { restants: +f.querySelectorAll('.fiche-echeance-chiffres > div b')[2].textContent.replace(/\s/g, ''), texte: f.textContent } : null;
    });
    await p.click('#choix-perimetre button[data-perimetre="BASE/OPTION"]'); await p.waitForTimeout(500);
    const barreBase = await p.evaluate(() => {
      const m = document.getElementById('phrase').textContent.replace(/\s/g, ' ').match(/([\d ]+) sur ([\d ]+) plans?/);
      return m ? +m[2].replace(/\s/g, '') - +m[1].replace(/\s/g, '') : null;
    });
    verifier('un jalon BASE/OPTION compte les plans à valider de BASE/OPTION, quel que soit le périmètre affiché',
      !!fichePer && fichePer.restants === barreBase && /BASE\/OPTION/.test(fichePer.texte), JSON.stringify([fichePer && fichePer.restants, barreBase]));
    await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(400);
  }
  // Re-cliquer ferme ; la croix ferme ; Entrée au clavier ouvre ; un numéro du graphique ouvre.
  const cle0 = String(joursAttendus[0].idx);
  await p.click('.legende-jalon[data-jalon="' + cle0 + '"]'); await p.waitForTimeout(300);
  const ouverte0 = await p.evaluate(() => !!document.getElementById('fiche-echeance'));
  await p.click('.legende-jalon[data-jalon="' + cle0 + '"]'); await p.waitForTimeout(300);
  verifier('re-cliquer le même jalon referme sa fiche',
    ouverte0 && await p.evaluate(() => !document.getElementById('fiche-echeance')));
  await p.focus('.legende-jalon[data-jalon="' + cle0 + '"]'); await p.keyboard.press('Enter'); await p.waitForTimeout(300);
  verifier('au clavier, Entrée sur un jalon ouvre sa fiche, et le focus reste sur lui',
    await p.evaluate(k => !!document.getElementById('fiche-echeance') && document.activeElement && document.activeElement.dataset.jalon === k, cle0));
  await p.click('#fiche-echeance [data-fermer-echeance]'); await p.waitForTimeout(300);
  verifier('la croix referme la fiche', await p.evaluate(() => !document.getElementById('fiche-echeance')));
  const idxMarque = await p.evaluate(() => { const g = document.querySelector('svg.graphe .jalon[data-jalon]'); return g ? g.getAttribute('data-jalon') : null; });
  if (idxMarque !== null) {
    // Par sélecteur : le graphique se redessine au survol, la cible se retrouve.
    await p.click('svg.graphe .jalon[data-jalon="' + idxMarque + '"] .jalon-marque'); await p.waitForTimeout(700);
    verifier('un clic sur un numéro du graphique ouvre la fiche de ce jalon',
      await p.evaluate(k => !!document.getElementById('fiche-echeance') &&
        document.querySelector('.legende-jalon[aria-expanded="true"]').dataset.jalon === k, idxMarque));
    await p.click('#fiche-echeance [data-fermer-echeance]'); await p.waitForTimeout(300);
  }
  // Le bouton « haut de page » : caché en haut, visible plus bas, et il ramène en haut.
  /* Caché pour de vrai : l'attribut ne suffisait pas, le display du bouton
     (inline-flex) l'emportait — il restait affiché en haut (débrief 17). */
  await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(200);
  const hautCache = await p.evaluate(() => { const b = document.getElementById('haut-de-page'); return b.hidden && getComputedStyle(b).display === 'none'; });
  await p.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await p.waitForTimeout(300);
  const hautVisible = await p.evaluate(() => { const b = document.getElementById('haut-de-page'); return !b.hidden && getComputedStyle(b).display !== 'none'; });
  await p.click('#haut-de-page'); await p.waitForTimeout(1500);
  verifier('le bouton « haut de page » est invisible en haut, paraît en descendant et ramène en haut',
    hautCache && hautVisible && await p.evaluate(() => window.scrollY < 5), JSON.stringify([hautCache, hautVisible]));
  /* Débrief 17 : THS n'a pas de jalon. La puce « Prochaine échéance » de
     HDK restait affichée en passant sur lui — cachée par l'attribut, montrée
     par son display. Aucun élément caché ne doit rester à l'écran. */
  await p.evaluate(() => { const s = window.__jeuDExemple('HDK'); s.jalons = []; window.__chargerSource(s); });
  await p.waitForTimeout(600);
  const sansJalon17 = await p.evaluate(() => {
    const b = document.getElementById('echeance-titre');
    return { cache: b.hidden, affiche: getComputedStyle(b).display, legende: document.getElementById('legende-jalons').textContent.trim(),
      restes: [...document.querySelectorAll('[hidden]')].filter(e => getComputedStyle(e).display !== 'none').map(e => e.id || e.className) };
  });
  verifier('un contrat sans jalon : pas de puce « Prochaine échéance » à l\'écran, pas de légende de jalons, et aucun élément caché ne reste affiché',
    sansJalon17.cache && sansJalon17.affiche === 'none' && sansJalon17.legende === '' && sansJalon17.restes.length === 0, JSON.stringify(sansJalon17));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK'))); await p.waitForTimeout(600);
  verifier('et de retour sur un contrat à jalons, la puce revient',
    await p.evaluate(() => { const b = document.getElementById('echeance-titre'); return !b.hidden && getComputedStyle(b).display !== 'none' && /Prochaine échéance/.test(b.textContent); }));

  // =================================================================
  /* Une seule formule, une seule façon de dire une semaine, un seul mot :
     chaque nombre qui se lit à deux endroits est le même aux deux endroits.
     Sur une page neuve, pour ne dépendre d'aucun test précédent. */
  section('Une seule formule, une seule façon de dire une semaine');
  {
    const pq = await page(await contexte(), 'cohérence');
    await pq.waitForTimeout(900);
    const esp = t => String(t || '').replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim();
    // Plus d'étiquette technique ni du mot « import » à l'écran (hors tableaux : l'extract a ses valeurs).
    const visible = await pq.evaluate(() => {
      const c = document.body.cloneNode(true);
      c.querySelectorAll('table, script, style').forEach(t => t.remove());
      return c.textContent;
    });
    verifier('plus aucune étiquette 2026-S38 à l\'écran : une semaine se dit « S38 · sept. 2026 »',
      !/\b20\d\d-S\d\d\b/.test(visible), (visible.match(/.{30}\b20\d\d-S\d\d\b.{10}/) || [''])[0]);
    /* « Importer », avec sa majuscule, est le nom d'un geste du classeur — le
       menu « Importer les exports GATES et SEE… » et le bouton de sa fenêtre —,
       pas d'une photo archivée : le panneau du classeur vide (débrief 20) les
       cite tels qu'ils sont écrits. */
    const sansGestes = visible.replace(/\bImporter\b/g, '');
    verifier('un seul mot pour une photo archivée : « relevé », jamais « import »',
      !/\bimport/i.test(sansGestes), (sansGestes.match(/.{30}\bimport.{20}/i) || [''])[0]);
    const lieux = await pq.evaluate(() => ({
      pied: document.getElementById('import').textContent,
      note: document.getElementById('note-graphe').textContent,
      journal: document.querySelector('.journal-semaine .sem').textContent,
      legende: [...document.querySelectorAll('.legende-jalon .quand')].map(q => q.textContent)
    }));
    const SEM = /S\d{1,2} · (janv\.|févr\.|mars|avr\.|mai|juin|juil\.|août|sept\.|oct\.|nov\.|déc\.) \d{4}/;
    /* Débrief 27 (lot B, P-F10) : le journal dit en plus les dates des deux
       relevés qu'il compare — « S38 · du ven. 11 au ven. 18 sept. » ; son
       numéro de semaine reste celui du pied. */
    const MOIS27 = '(janv\\.|févr\\.|mars|avr\\.|mai|juin|juil\\.|août|sept\\.|oct\\.|nov\\.|déc\\.)';
    const SEM_JOURNAL = new RegExp('^S\\d{1,2} · du (lun|mar|mer|jeu|ven|sam|dim)\\. \\d{1,2}( ' + MOIS27 + ')? au (lun|mar|mer|jeu|ven|sam|dim)\\. \\d{1,2} ' + MOIS27 + '( \\d{4})?$');
    /* Débrief 29 (lot E2, A-F13) : le pied dit « archivé » et le jour du
       relevé — « Dernier relevé archivé : S43 (vendredi 23 octobre) · 6
       relevés » ; son numéro de semaine reste celui de la note et du journal. */
    const PIED29 = /^Dernier relevé archivé : (S\d{1,2}) \((lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche) \d{1,2} (janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)( \d{4})?\) · \d+ relevés$/;
    const semPied = (esp(lieux.pied).match(PIED29) || [])[1];
    verifier('pied, note du graphique, journal et jalons nomment la semaine de la même façon (le pied avec le jour du relevé archivé, le journal avec les dates des deux relevés)',
      !!semPied &&
      /^\d+ relevés, de S\d{1,2} · \S+ \d{4} à S\d{1,2} · \S+ \d{4}$/.test(esp(lieux.note)) &&
      SEM_JOURNAL.test(esp(lieux.journal)) && esp(lieux.journal).split(' ')[0] === semPied &&
      lieux.legende.every(q => SEM.test(esp(q))), JSON.stringify(lieux));
    // Le pied et la note disent le même dernier relevé.
    verifier('le pied et la note du graphique nomment le même dernier relevé',
      !!semPied && (esp(lieux.note).split(' à ')[1] || '').split(' ')[0] === semPied, JSON.stringify(lieux));

    // La fiche, la légende, le « manque » du graphique et la puce : les mêmes nombres.
    await pq.click('#echeance-titre'); await pq.waitForTimeout(500);
    const m = await pq.evaluate(() => {
      const esp = t => String(t || '').replace(/[  ]/g, ' ').replace(/\s+/g, ' ');
      const f = document.getElementById('fiche-echeance');
      const fiche = esp(f.textContent), leg = esp(document.getElementById('legende').textContent);
      /* Débrief 19 : la légende ne dit plus « → fin … » ni le nombre du
         requis ; ils sont dans ses survols. */
      const survols = esp([...document.querySelectorAll('#legende .legende-item span[title]')].map(x => x.getAttribute('title')).join(' | '));
      const manque = [...document.querySelectorAll('.manque-jalon')].map(t => (esp(t.textContent).match(/manque (\d[\d ]*)$/) || [])[1]);
      const ch = [...f.querySelectorAll('.fiche-echeance-chiffres > div b')].map(b => +b.textContent.replace(/\s/g, ''));
      return {
        requisFiche: (fiche.match(/Il faut ([\d,]+) plans/) || [])[1], requisLegende: (survols.match(/ : ([\d,]+) par semaine\. En rouge/) || [])[1],
        tenuFiche: (fiche.match(/le rythme tenu est de ([\d,]+)/) || [])[1], tenuLegende: (leg.match(/au rythme tenu \(([\d,]+)\/sem\.\)/) || [])[1],
        finFiche: (fiche.match(/(?:tout serait validé|au rythme global, la fin serait) en (S\d+ · \S+ \d{4})/) || [])[1], finLegende: (survols.match(/: fin (S\d+ · \S+ \d{4})\./) || [])[1],
        legendeCourte: !/→ fin|\/sem\. sur|» : [\d,]+\/sem\./.test(leg),
        manqueFiche: (fiche.match(/il manquer(?:a|ait) (\d[\d ]*) plans?/) || [])[1], manqueGraphe: manque[0],   // débrief 27 (P-F18) : « il manquera »
        rouge: document.getElementById('echeance-titre').classList.contains('en-retard'),
        mal: f.querySelector('.fiche-echeance-verdict').classList.contains('mal'),
        jours: ch[0], semaines: ch[1], restants: ch[2]
      };
    });
    verifier('la fiche et la légende du graphique disent le même rythme requis, le même rythme tenu, la même fin (le requis et la fin dans les survols de la légende)',
      !!m.requisFiche && m.requisFiche === m.requisLegende && !!m.tenuFiche && m.tenuFiche === m.tenuLegende &&
      !!m.finFiche && m.finFiche === m.finLegende, JSON.stringify(m));
    verifier('débrief 19 : la légende dit « au rythme tenu (N/sem.) » et « requis pour « … » », sans « → fin … » ni le nombre du requis',
      m.legendeCourte && !!m.tenuLegende, JSON.stringify(m));
    verifier('« manque N » sur le graphique est le nombre de la fiche ; la puce a la couleur du verdict',
      !!m.manqueFiche && m.manqueFiche.replace(/ /g, '') === (m.manqueGraphe || '').replace(/ /g, '') && m.rouge === m.mal, JSON.stringify(m));
    verifier('jours et semaines restants se comptent tous deux d\'aujourd\'hui',
      m.semaines >= 1 && Math.abs(m.jours / 7 - m.semaines) < 1.2, JSON.stringify([m.jours, m.semaines]));
    /* Débrief 27 (P-F18) : au-delà de dix, le rythme requis s'arrondit au
       plan (« 83/sem. », plus « 83,0 ») — à un demi-plan près, donc. */
    verifier('le rythme requis est bien les plans à valider divisés par les semaines restantes',
      Math.abs(Number(m.requisFiche.replace(',', '.')) - m.restants / m.semaines) < (m.restants / m.semaines >= 10 ? 0.501 : 0.051), JSON.stringify([m.requisFiche, m.restants, m.semaines]));
    await pq.click('#fiche-echeance [data-fermer-echeance]'); await pq.waitForTimeout(300);

    // Une ligne du bloc, puis le graphique de ce groupe : les mêmes nombres.
    const ligne = await pq.evaluate(() => {
      const esp = t => String(t || '').replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim();
      const l = document.querySelector('.critique-ligne');
      const v = esp(l.querySelector('.critique-effort .v').textContent);
      return { requis: (v.match(/^([\d,]+)\/sem\./) || [])[1], tenu: (v.match(/tenu ([\d,]+)\/sem\./) || [])[1],
               fin: esp(l.querySelector('.critique-date .v').textContent) };
    });
    /* Débrief 27 (lot C) : le graphique suit le groupe quand on filtre la
       page sur lui (« Filtrer la page sur … »), plus au simple dépliage. */
    await pq.click('.critique-ligne >> nth=0'); await pq.waitForTimeout(400);
    await pq.click('#filtrer-groupe-page'); await pq.waitForTimeout(500);
    const legG = esp(await pq.evaluate(() => document.getElementById('legende').textContent));
    const survG = esp(await pq.evaluate(() => [...document.querySelectorAll('#legende .legende-item span[title]')].map(x => x.getAttribute('title')).join(' | ')));
    verifier('une ligne du bloc et le graphique de son groupe disent le même rythme requis, le même rythme tenu, la même fin',
      !!ligne.requis && survG.indexOf(': ' + ligne.requis + ' par semaine.') !== -1 && legG.indexOf('au rythme tenu (' + ligne.tenu + '/sem.)') !== -1 &&
      survG.indexOf(': fin ' + ligne.fin + '.') !== -1 && /requis pour « [^»]+ » \(\S+ [^)]+\)/.test(legG), JSON.stringify([ligne, legG, survG]));
    const phraseG = esp(await pq.evaluate(() => document.getElementById('phrase').textContent));
    const noteG = esp(await pq.evaluate(() => document.getElementById('note-graphe').textContent));
    verifier('choisir un groupe : la phrase et la note du graphique le nomment de la même façon, sans « autres filtres » inventés',
      /plans validés dans \S+ \S+$/.test(phraseG) && noteG.indexOf(phraseG.replace(/^.* dans /, '')) !== -1 && !/autres filtres/.test(noteG),
      JSON.stringify([phraseG, noteG]));
    await pq.click('#filtrer-groupe-page'); await pq.waitForTimeout(400);
    await pq.click('.critique-ligne >> nth=0'); await pq.waitForTimeout(400);

    // La dernière semaine : journal et bulle du graphique, les mêmes lignes.
    const res = await pq.evaluate(() => {
      const esp = t => String(t || '').replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim();
      /* Les cases vides du tableau du journal (une sorte de passage absente
         cette semaine) ne sont pas des lignes du résumé. */
      return { journal: [...document.querySelector('.journal-semaine .resume').children].filter(c => !c.classList.contains('case-vide')).map(c => esp(c.textContent)),
               auj: window.__semaineDuTitre().auj };
    });
    await pq.evaluate(() => document.getElementById('cadre-graphe').scrollIntoView({ block: 'center' })); await pq.waitForTimeout(200);
    await (await pq.$('.zone-clic[data-i="' + res.auj + '"]')).hover(); await pq.waitForTimeout(300);
    const bulleL = await pq.evaluate(() => [...document.querySelectorAll('#bulle .bulle-comptes .bulle-ligne')].map(l => {
      const esp = t => String(t || '').replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim();
      return esp(l.querySelector('.n').textContent) + ' ' + esp(l.textContent.replace(l.querySelector('.n').textContent, ''));
    }));
    verifier('la bulle du graphique dit la même semaine avec les mêmes lignes',
      bulleL.join('|') === res.journal.join('|'), JSON.stringify([bulleL, res.journal]));
    await pq.mouse.move(5, 5);

    // « Non renseigné » : le même compte sous la barre et au-dessus du tableau.
    const nr = await pq.evaluate(() => {
      const b = document.querySelector('#etats .etat-btn[data-cle="vide"] .etat-n');
      const puce = document.querySelector('#incomplets .puce-vide b');
      return { barre: b ? +b.textContent.replace(/\s/g, '') : null, puce: puce ? +puce.textContent.replace(/\s/g, '') : null };
    });
    verifier('« Non renseigné » compte la même chose sous la barre et au-dessus du tableau', nr.barre !== null && nr.barre === nr.puce, JSON.stringify(nr));

    // Le cadrage d'ouverture montre toujours la prochaine échéance.
    const cad = () => pq.evaluate(() => {
      const presse = [...document.querySelectorAll('.commandes-graphe .segmente button')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.textContent).join();
      const j = document.getElementById('echeance-titre').dataset.jalon;
      const leg = document.querySelector('.legende-jalon[data-jalon="' + j + '"]');
      return { presse: presse, horsFenetre: leg ? leg.classList.contains('hors-fenetre') : null };
    });
    const cDef = await cad();
    await pq.click('#choix-indicateur button[data-indicateur="concept"]'); await pq.waitForTimeout(700);
    const cCon = await cad();
    verifier('le graphique s\'ouvre sur « Échéances », sous les deux avancements : jamais sans la prochaine échéance',
      cDef.presse === 'Échéances' && cDef.horsFenetre === false && cCon.presse === 'Échéances' && cCon.horsFenetre === false, JSON.stringify([cDef, cCon]));
    // Sous le concept, sur « Tout », l'échéance TO Base ne demande que ses plans BASE/OPTION.
    const leg = await pq.evaluate(() => ({ texte: document.getElementById('legende').textContent.replace(/[  ]/g, ' '),
                                           voir: !!document.querySelector('#legende button[data-voir-perimetre]'),
                                           manque: document.querySelectorAll('.manque-jalon').length }));
    verifier('sur « Tout », un jalon BASE/OPTION se lit dans la légende, « sur ses plans BASE/OPTION », avec un lien — pas de droite sur la courbe de tous',
      /requis pour « Diffusion TO Base » sur ses plans BASE\/OPTION/.test(leg.texte) && leg.voir && leg.manque === 0, JSON.stringify(leg));
    await pq.click('#legende button[data-voir-perimetre]'); await pq.waitForTimeout(600);
    await pq.click('#echeance-titre'); await pq.waitForTimeout(400);
    const surBase = await pq.evaluate(() => {
      const esp = t => String(t || '').replace(/[  ]/g, ' ');
      return { per: document.querySelector('#choix-perimetre button[aria-pressed="true"]').dataset.perimetre,
               leg: esp([...document.querySelectorAll('#legende .legende-item span[title]')].map(x => x.getAttribute('title')).join(' | ')),
               fiche: esp((document.getElementById('fiche-echeance') || {}).textContent || ''),
               voir: !!document.querySelector('#legende button[data-voir-perimetre]') };
    });
    const rL = (surBase.leg.match(/ : ([\d,]+) par semaine\. En rouge/) || [])[1], rF = (surBase.fiche.match(/Il faut ([\d,]+) plans/) || [])[1];
    verifier('« voir BASE/OPTION » passe au périmètre du jalon, où la légende et la fiche disent le même rythme requis',
      surBase.per === 'BASE/OPTION' && !surBase.voir && !!rL && rL === rF, JSON.stringify([surBase.per, rL, rF]));
    /* Débrief 14 : « dans le concept harnais, on ne voyait pas les jalons ».
       Un cadrage choisi à la main sous un avancement pouvait cacher les
       échéances de l'autre : changer d'avancement revient sur « Échéances »,
       et toutes les échéances du nouvel avancement sont à l'écran. */
    await pq.click('.commandes-graphe .segmente button[data-span="13"]'); await pq.waitForTimeout(300);
    await pq.click('#choix-indicateur button[data-indicateur="def"]'); await pq.waitForTimeout(700);
    const apresDef = await cad();
    await pq.click('.commandes-graphe .segmente button[data-span="13"]'); await pq.waitForTimeout(300);
    await pq.click('#choix-indicateur button[data-indicateur="concept"]'); await pq.waitForTimeout(700);
    const apresCon = await pq.evaluate(() => ({
      presse: [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')].map(b => b.textContent).join(),
      horsFenetre: document.querySelectorAll('.legende-jalon.hors-fenetre').length,
      to: [...document.querySelectorAll('svg.graphe .jalon')].filter(g => /Diffusion TO/.test(g.getAttribute('aria-label'))).length,
      comptent: document.querySelectorAll('svg.graphe .jalon:not(.hors-perimetre)').length
    }));
    verifier('changer d’avancement revient sur « Échéances » : sous le concept harnais, ses deux échéances TO sont à l’écran (celle d’un autre périmètre en pâle), même après un zoom sur 3 mois',
      apresDef.presse === 'Échéances' && apresCon.presse === 'Échéances' && apresCon.horsFenetre === 0 && apresCon.to === 2 && apresCon.comptent >= 1,
      JSON.stringify([apresDef, apresCon]));
    await pq.context().close();
  }

  // =================================================================
  /* Débrief 13 : « contrat et définition électrique, l'un en dessous de
     l'autre » ; « dans ce qui a changé semaine par semaine… c'est pas droit,
     c'est pas carré… il faut tout sur la même colonne ». */
  section('Débrief 13 : un bandeau empilé, un journal au carré');
  await reinitialiser(p);
  await p.evaluate(() => window.scrollTo(0, 0));
  const bandeau13 = await p.evaluate(() => {
    const r = el => { const b = el.getBoundingClientRect(); return { l: Math.round(b.left), r: Math.round(b.right), t: Math.round(b.top), b: Math.round(b.bottom) }; };
    const lab = document.querySelector('#choix-contrat label[for="select-contrat"]');
    const mot = document.querySelector('#choix-avancement .mot-reglage');
    return {
      avancementVisible: !document.getElementById('choix-avancement').hidden && document.getElementById('choix-indicateur').offsetParent !== null,
      select: r(document.getElementById('select-contrat')), boutons: r(document.getElementById('choix-indicateur')),
      label: lab ? r(lab) : null, mot: mot ? r(mot) : null,
      motTexte: mot ? mot.textContent.trim() : '',
      boutonsTexte: [...document.querySelectorAll('#choix-indicateur button')].map(b => b.textContent.trim())
    };
  });
  /* Débrief 27 (lot H, B1) : plus d'escalier de trois lignes — une seule
     barre de réglages : le contrat, puis l'avancement (puis le périmètre),
     sur la même ligne, le contrat à gauche de l'avancement. */
  verifier('une seule barre : le contrat puis l’avancement « Définition électrique | Concept harnais », sur la même ligne',
    bandeau13.avancementVisible && Math.abs((bandeau13.select.t + bandeau13.select.b) - (bandeau13.boutons.t + bandeau13.boutons.b)) <= 4 &&
    bandeau13.select.r < bandeau13.boutons.l &&
    bandeau13.boutonsTexte.join('|') === 'Définition électrique|Concept harnais', JSON.stringify(bandeau13));
  /* Débrief 14 : « tout centré sur la droite ». La barre finissait au bord
     droit de la page. Débrief 28 : sur un écran large, la barre est au
     centre du bandeau, comme le titre (« réglages centrés ») ; chaque
     commande a toujours son mot juste devant elle. */
  const bordsBandeau = await p.evaluate(() => { const b = document.querySelector('.bandeau-mode'), r = b.getBoundingClientRect(), c = getComputedStyle(b);
    return { g: r.left + parseFloat(c.paddingLeft), d: r.right - parseFloat(c.paddingRight) }; });
  const vusBarre = await p.evaluate(() => [...document.querySelectorAll('#portee .reglage')].filter(e => e.getClientRects().length).map(e => { const r = e.getBoundingClientRect(); return [r.left, r.right]; }));
  const debutBarre = Math.min(...vusBarre.map(x => x[0])), finBarre = Math.max(...vusBarre.map(x => x[1]));
  const bordDroit = Math.round(bordsBandeau.d);
  verifier('la barre est au centre du bandeau, sans toucher ses bords (débrief 28), chaque commande avec son mot juste devant elle',
    Math.abs((debutBarre + finBarre) / 2 - (bordsBandeau.g + bordsBandeau.d) / 2) <= 2 && finBarre < bordsBandeau.d - 20 && debutBarre > bordsBandeau.g + 20 &&
    !!bandeau13.label && !!bandeau13.mot &&
    bandeau13.label.r <= bandeau13.select.l && bandeau13.select.l - bandeau13.label.r <= 14 &&
    bandeau13.mot.r <= bandeau13.boutons.l && bandeau13.boutons.l - bandeau13.mot.r <= 14 && bandeau13.motTexte === 'Avancement',
    JSON.stringify([bandeau13, bordDroit, finBarre]));

  await p.evaluate(() => document.getElementById('zone-journal').scrollIntoView({ block: 'start' }));
  await p.waitForTimeout(200);
  const carre = await p.evaluate(() => {
    const zone = document.getElementById('zone-journal');
    const debutContenu = el => {
      const vus = [...el.querySelectorAll('.pastille, b')].filter(x => x.getBoundingClientRect().width > 2);
      if (vus.length) return Math.round(Math.min(...vus.map(x => x.getBoundingClientRect().left)));
      const r = document.createRange(); r.selectNodeContents(el);
      return Math.round(r.getBoundingClientRect().left);
    };
    const semaines = [...zone.querySelectorAll('.journal-semaine')];
    const entetes = [...zone.querySelectorAll('.journal-entetes > span')];
    const nCol = entetes.length - 2;   // la semaine, puis les colonnes, puis la jauge
    const cols = [];
    for (let k = 0; k < nCol; k++) cols.push([]);
    const cases = semaines.map(sem => [...sem.querySelector('.resume').children]);
    cases.forEach(cs => cs.forEach((c, k) => {
      if (!c.classList.contains('case-vide') && cols[k]) cols[k].push(Math.round(c.getBoundingClientRect().left));
    }));
    const jauges = semaines.map(sem => sem.querySelector('.mini-jauge')).filter(Boolean).map(j => Math.round(j.getBoundingClientRect().right));
    const semLeft = semaines.map(sem => Math.round(sem.querySelector('.journal-plier').getBoundingClientRect().left));
    return {
      grille: zone.classList.contains('journal-grille'), semaines: semaines.length, nCol,
      casesParSemaine: [...new Set(cases.map(cs => cs.length))],
      ecartsColonnes: cols.map(c => c.length ? Math.max(...c) - Math.min(...c) : 0),
      remplies: cols.map(c => c.length),
      /* Ce que l'œil compare : le début du contenu (la pastille, sinon le
         texte) de chaque en-tête et de la première case remplie dessous. */
      entetesX: entetes.slice(1, -1).map(debutContenu),
      premieresX: cols.map((c, k) => {
        const cs = cases.map(l => l[k]).filter(x => x && !x.classList.contains('case-vide'));
        return cs.length ? debutContenu(cs[0]) : null;
      }),
      entetesTextes: entetes.slice(1, -1).map(e => e.textContent.replace(/[  ]/g, ' ').trim()),
      motsVisibles: [...zone.querySelectorAll('.journal-tete .mot-case')].filter(m => m.getBoundingClientRect().width > 2).length,
      ecartJauges: jauges.length ? Math.max(...jauges) - Math.min(...jauges) : 0,
      ecartSemaines: Math.max(...semLeft) - Math.min(...semLeft),
      deborde: zone.scrollWidth > zone.clientWidth + 1,
      collant: getComputedStyle(zone.querySelector('.journal-entetes')).position,
      groupes: [...zone.querySelectorAll('.journal-entetes .entete-groupe')].map(g => g.textContent)
    };
  });
  verifier('le journal est un tableau : une case par colonne dans chaque semaine, vide quand la semaine n’a pas cette sorte de passage',
    carre.grille && carre.semaines >= 5 && carre.nCol >= 3 && carre.casesParSemaine.length === 1 && carre.casesParSemaine[0] === carre.nCol &&
    carre.remplies.every(n => n >= 1), JSON.stringify(carre));
  verifier('chaque sorte de passage tombe dans sa colonne, au pixel près, d’une semaine à l’autre',
    carre.ecartsColonnes.every(e => e <= 1), JSON.stringify(carre.ecartsColonnes));
  /* Débrief 27 (lot B, B9) : « passés à » n'est plus répété dans chaque
     colonne — un étage « Passés à » les coiffe toutes, et chacune ne porte
     que le nom de sa valeur. */
  verifier('l’en-tête nomme chaque colonne une fois, exactement au-dessus de ses cases, et reste collé en haut',
    carre.entetesX.every((x, k) => carre.premieresX[k] === null || Math.abs(x - carre.premieresX[k]) <= 1) &&
    carre.groupes[0] === 'Passés à' && carre.entetesTextes.length > 0 && !carre.entetesTextes.some(t => /passés? à/i.test(t)) && carre.collant === 'sticky',
    JSON.stringify([carre.entetesX, carre.premieresX, carre.entetesTextes, carre.groupes]));
  verifier('dans les cases, le nombre et la pastille : les mots sont dans l’en-tête (et pour les lecteurs d’écran)',
    carre.motsVisibles === 0, String(carre.motsVisibles));
  verifier('les semaines et les jauges sont alignées elles aussi, et rien ne déborde',
    carre.ecartJauges <= 1 && carre.ecartSemaines <= 1 && !carre.deborde, JSON.stringify(carre));
  /* Un filtre qui retire une sorte de passage retire sa colonne : le tableau
     reste plein, sans colonne vide de bout en bout. */
  const filtreJ = await p.$('#filtre-journal button[data-journal="indice"]');
  if (filtreJ) {
    await filtreJ.click(); await p.waitForTimeout(350);
    const seul = await p.evaluate(() => ({
      entetes: [...document.querySelectorAll('#zone-journal .journal-entetes > span')].length - 2,
      cases: [...new Set([...document.querySelectorAll('#zone-journal .journal-semaine .resume')].map(r => r.children.length))]
    }));
    verifier('filtrer sur les changements d’indice ne laisse que leur colonne', seul.entetes === 1 && seul.cases.join() === '1', JSON.stringify(seul));
    await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(350);
  }
  await reinitialiser(p);

  // =================================================================
  /* Débrief 14 : ce qui péchait encore, et ce que Nathan a validé — les
     reculs, un seul mot pour une même chose, les plans à l'arrêt, la vie
     d'un plan, la vue d'ensemble des contrats. Débrief 15 : plus de bande
     « Depuis le relevé précédent », un seul rythme. */
  section('Débrief 14-15 : reculs, un seul rythme, plans à l’arrêt, vie d’un plan, vue d’ensemble');
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); window.scrollTo(0, 0); });
  await p.waitForTimeout(700);
  const esp14 = t => String(t || '').replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim();

  // --- Les reculs : une ligne à part, en rouge, jamais parmi les « passés à … ».
  const rec = await p.evaluate(() => {
    const J = window.__journal();
    const estRecul = e => e.type === 'change' && ((e.avant === 'termine' && e.apres !== 'termine') || (e.avant === 'encours' && e.apres === 'afaire'));
    const parSemaine = J.map(s => ({ i: s.i, reculs: s.evenements.filter(estRecul).length, total: s.evenements.length }));
    const semaines = [...document.querySelectorAll('.journal-semaine')].map(sem => ({
      cases: [...sem.querySelector('.resume').children].filter(c => !c.classList.contains('case-vide')).map(c => c.textContent.replace(/\s+/g, ' ').trim()),
      somme: [...sem.querySelectorAll('.resume b')].reduce((t, b) => t + Number(b.textContent.replace(/\s/g, '')), 0)
    }));
    const compte = document.querySelector('.journal-semaine .compte-passage.recul');
    return {
      parSemaine, semaines,
      entetes: [...document.querySelectorAll('.journal-entetes .entete-col')].map(e => e.textContent.trim()),
      compte: compte ? { texte: compte.textContent.replace(/\s+/g, ' ').trim(), rouge: getComputedStyle(compte.querySelector('b')).color } : null,
      alerte: getComputedStyle(document.body).getPropertyValue('--alerte').trim(),
      filtre: !!document.querySelector('#filtre-journal button[data-journal="reculs"] .pastille.recul')
    };
  });
  const recS38 = rec.parSemaine[0].reculs, totRec = rec.parSemaine.reduce((t, x) => t + x.reculs, 0);
  verifier('les reculs ont leur case : « ' + recS38 + ' recul » dans la dernière semaine du journal, le nombre en rouge',
    recS38 >= 1 && !!rec.compte && rec.compte.texte === recS38 + (recS38 > 1 ? ' reculs' : ' recul') &&
    rec.compte.rouge === (await p.evaluate(() => { const t = document.createElement('span'); t.style.color = 'var(--alerte)'; document.body.appendChild(t); const c = getComputedStyle(t).color; t.remove(); return c; })),
    JSON.stringify(rec.compte));
  verifier('plus de bande « Depuis le relevé précédent » sous la barre : le journal et la courbe le disent',
    await p.evaluate(() => !document.getElementById('comparatif') && !/Depuis le relevé précédent/.test(document.querySelector('section.avancement').textContent)));
  verifier('dans le journal, une colonne « reculs », un filtre « Reculs » ; chaque semaine compte tous ses événements, une fois chacun',
    /* Débrief 27 (lot B) : les en-têtes prennent la majuscule (« Reculs »). */
    rec.entetes.includes('Reculs') && rec.filtre && totRec >= 2 &&
    rec.semaines.every((s, k) => s.somme === rec.parSemaine[k].total), JSON.stringify([rec.entetes, rec.semaines.map(s => s.somme), rec.parSemaine.map(s => s.total)]));
  verifier('un recul ne se range plus parmi les « passés à … » : la semaine qui a 2 reculs ne dit plus « passés à « À faire » »',
    rec.semaines.every((s, k) => rec.parSemaine[k].reculs === 0 || s.cases.some(c => new RegExp('^' + rec.parSemaine[k].reculs + ' reculs?$').test(c))) &&
    !rec.semaines.some(s => s.cases.some(c => /passés? à « À faire »/.test(c))), JSON.stringify(rec.semaines.slice(0, 3)));
  await p.click('#filtre-journal button[data-journal="reculs"]'); await p.waitForTimeout(350);
  await p.click('.journal-semaine .journal-plier >> nth=0'); await p.waitForTimeout(300);
  const lignesRecul = await p.evaluate(() => [...document.querySelectorAll('.journal-liste .journal-ligne')].map(l => ({
    recul: l.classList.contains('recul'), passage: l.querySelector('.vers').textContent.replace(/\s+/g, ' ').trim(),
    rouge: getComputedStyle(l.querySelector('.ref')).color })));
  verifier('filtrer « Reculs » ne garde que des reculs — « Validé → … » ou « En cours → À faire » —, référence en rouge',
    lignesRecul.length >= 1 && lignesRecul.every(l => l.recul && (/^Terminé ?→/.test(l.passage) || /^En cours ?→ ?À faire$/.test(l.passage))) &&
    new Set(lignesRecul.map(l => l.rouge)).size === 1, JSON.stringify(lignesRecul));
  await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(300);
  await p.click('.journal-semaine .journal-plier >> nth=0'); await p.waitForTimeout(200);
  /* --- L'ordre. Débrief 27 (lot B, B9) : plus « de la sorte la plus
     fréquente à la plus rare » (débrief 14) mais l'ordre de la légende et
     des pastilles du dessus — les valeurs dans l'ordre des tuiles, puis les
     mouvements : reculs, nouveaux, disparus, changements d'indice. L'œil
     passe de la pastille à sa colonne sans chercher. */
  const ordre = await p.evaluate(() => {
    const entetes = [...document.querySelectorAll('.journal-entetes .entete-col')].map(e => e.textContent.trim());
    const vals = window.__valeurs().map(v => v.libelle);
    const filtres = [...document.querySelectorAll('#filtre-journal button[data-journal]:not([data-journal=""])')].map(b => b.querySelector('.libelle').textContent);
    return { entetes, vals, filtres };
  });
  const passes27 = ordre.entetes.filter(t => ordre.vals.indexOf(t) !== -1);
  const mouv27 = ['Reculs', 'Nouveaux', 'Disparus', 'Changements d’indice'];
  verifier('les colonnes du journal suivent la légende : les valeurs dans l’ordre des tuiles, puis reculs, nouveaux, disparus, changements d’indice — l’ordre des pastilles du dessus',
    passes27.length >= 2 && passes27.join() === ordre.vals.filter(v => passes27.indexOf(v) !== -1).join() &&
    ordre.entetes.slice(passes27.length).join() === mouv27.filter(m => ordre.entetes.indexOf(m) !== -1).join() &&
    ordre.entetes.join() === ordre.filtres.filter(f => ordre.entetes.indexOf(f) !== -1).join(), JSON.stringify(ordre));
  // --- Débrief 15 : un seul rythme, le rythme tenu — plus « les 4 dernières semaines » nulle part.
  const ryt = await p.evaluate(() => {
    const pts = window.__serieAffichee().pts, der = pts[pts.length - 1];
    const tenu = (der.termine - pts[0].termine) / (der.i - pts[0].i);
    return { tenu, legende: document.getElementById('legende').textContent.replace(/[\u00a0\u202f]/g, ' '),
             projections: document.querySelectorAll('svg.graphe path[stroke-dasharray]').length,
             recente: !!document.querySelector('svg.graphe path.projection-recente, .legende-recent, .fin-recente, .fiche-echeance-recent'),
             bloc: [...document.querySelectorAll('.critique-effort .v small')].map(s => s.textContent),
             page: document.body.innerText };
  });
  const v1 = x => (Math.round(x * 10) / 10).toFixed(1).replace('.', ',');
  verifier('la légende dit un seul rythme — « au rythme tenu (' + v1(ryt.tenu) + '/sem.) » — et le graphique ne trace plus de seconde projection',
    ryt.legende.indexOf('au rythme tenu (' + v1(ryt.tenu) + '/sem.)') !== -1 && !/dernières semaines/.test(ryt.legende) && !ryt.recente,
    ryt.legende);
  verifier('le bloc par groupe écrit le rythme tenu de chaque groupe, seul',
    ryt.bloc.length > 0 && ryt.bloc.every(t => /^tenu [\d,]+\/sem\.$|^rien de validé$/.test(t)), JSON.stringify(ryt.bloc.slice(0, 3)));
  await p.click('#echeance-titre'); await p.waitForTimeout(400);
  const ficheRyt = esp14(await p.evaluate(() => (document.getElementById('fiche-echeance') || {}).textContent));
  verifier('la fiche dit le rythme tenu, et plus « au rythme des 4 dernières semaines »',
    ficheRyt.indexOf('le rythme tenu est de ' + v1(ryt.tenu) + ' par semaine.') !== -1 && !/dernières semaines/.test(ficheRyt), ficheRyt);
  verifier('nulle part sur la page « récent » ni « dernières semaines »', !/ récent|dernières semaines/.test(ryt.page));
  await p.keyboard.press('Escape'); await p.waitForTimeout(200);

  // --- Oui/Non, partout.
  const ouiNon = await p.evaluate(() => {
    const ths = [...document.querySelectorAll('tr.titres th')];
    const i = ths.findIndex(t => /^RPT/.test(t.textContent.trim()));
    const vals = [...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.children[i] && tr.children[i].textContent.trim()).filter(Boolean);
    return { i, valeurs: [...new Set(vals)].sort() };
  });
  verifier('dans le tableau, une case à cocher de l’extract se lit « Oui » ou « Non » — plus de true/false',
    ouiNon.i > 0 && ouiNon.valeurs.join() === 'Non,Oui', JSON.stringify(ouiNon));
  await p.fill('#recherche', 'true'); await p.waitForTimeout(450);
  const parTrue = await p.evaluate(() => document.getElementById('compte').textContent.replace(/[\s\u00a0\u202f]+/g, ' ').trim());
  await p.fill('#recherche', ''); await p.waitForTimeout(350);
  verifier('et la recherche trouve encore les deux écritures', /^\d+ plans sur 640$/.test(parTrue), parTrue);

  // --- Les plans à l'arrêt : recomptés à la main dans la source.
  const arretAttendu = await p.evaluate(() => {
    const src = window.__jeuDExemple('HDK');
    const cle = ref => { const u = window.__analyserUD(ref); return u.valide ? u.racine + u.solution : ref; };
    const sem = l => +String(l).slice(6);
    const rel = src.releves.slice().sort((a, b) => sem(a.semaine) - sem(b.semaine)).map(r => {
      const m = {}; Object.keys(r.plans || {}).forEach(ref => { m[cle(ref)] = r.plans[ref]; }); return { s: sem(r.semaine), m };
    });
    const cur = {}; src.plans.forEach(p => { cur[cle(p.reference)] = p.avancement; });
    rel[rel.length - 1].m = cur;
    let n = 0;
    src.plans.forEach(p => {
      if (window.__classer(p.avancement) !== 'encours') return;
      const k0 = cle(p.reference); let depuis = rel[rel.length - 1].s;
      for (let k = rel.length - 2; k >= 0; k--) { if (rel[k].m[k0] !== p.avancement) break; depuis = rel[k].s; }
      if (rel[rel.length - 1].s - depuis >= 6) n++;
    });
    return n;
  });
  const arret = await p.evaluate(() => ({
    texte: document.getElementById('a-surveiller').textContent.replace(/\s+/g, ' ').trim(),
    liste: window.__plansALArret().length,
    parGroupe: [...document.querySelectorAll('.critique-ligne .arret-n')].reduce((t, e) => t + parseInt(e.textContent, 10), 0)
  }));
  verifier('« À surveiller : N plans en cours n’ont pas bougé depuis 6 semaines ou plus » — N recompté à la main dans la source : ' + arretAttendu,
    arretAttendu > 0 && arret.liste === arretAttendu &&
    new RegExp('^À surveiller : ?' + arretAttendu + ' plans en cours n’ont pas bougé depuis 6 semaines ou plus$').test(arret.texte), JSON.stringify(arret));
  verifier('le bloc par groupe les répartit par ATA : la somme des « à l’arrêt » fait N', arret.parGroupe === arretAttendu, String(arret.parGroupe));
  await p.click('#a-surveiller button[data-arret]'); await p.waitForTimeout(450);
  const arretFiltre = await p.evaluate(() => ({
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    etats: [...new Set([...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.querySelector('.etat-cellule') && tr.querySelector('.etat-cellule').textContent.trim()))],
    jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').replace(/\s+/g, ' ').trim()),
    presse: document.querySelector('#a-surveiller button').getAttribute('aria-pressed')
  }));
  verifier('un clic les montre dans le tableau — tous en cours —, le bandeau le dit', arretFiltre.lignes === arretAttendu && arretFiltre.presse === 'true' &&
    arretFiltre.etats.join() === 'En cours' && arretFiltre.jetons.some(j => j === 'À surveiller : en cours sans bouger depuis 6 semaines ou plus'), JSON.stringify(arretFiltre));
  await p.click('#a-surveiller button[data-arret]'); await p.waitForTimeout(400);
  verifier('un second clic retire le filtre', await p.evaluate(() => document.querySelectorAll('#corps-tableau tr').length) === TOTAL);
  const grpArret = await p.evaluate(() => {
    const l = [...document.querySelectorAll('.critique-ligne')].find(x => x.querySelector('.arret-n'));
    return l ? { groupe: l.dataset.groupe, n: parseInt(l.querySelector('.arret-n').textContent, 10) } : null;
  });
  await p.click('.critique-ligne[data-groupe="' + grpArret.groupe + '"]'); await p.waitForTimeout(500);
  const jetonsArret = await p.evaluate(() => [...document.querySelectorAll('.groupe-refs .jeton-ud.arret')].map(b => b.title));
  verifier('dans la liste d’un groupe, ses plans à l’arrêt sont cerclés d’ambre et leur bulle dit depuis quand',
    jetonsArret.length === grpArret.n && jetonsArret.every(t => /en cours sans bouger depuis (au moins )?S\d{1,2} · \S+ \d{4} \(\d+ semaines\)/.test(t.replace(/[  ]/g, ' '))),
    JSON.stringify([grpArret, jetonsArret.slice(0, 2)]));
  await p.click('.critique-ligne[data-groupe="' + grpArret.groupe + '"]'); await p.waitForTimeout(400);

  // --- La vie d'un plan : un clic sur une référence, où qu'elle soit.
  const refRecul = await p.evaluate(() => {
    const J = window.__journal();
    const e = J[0].evenements.find(x => x.type === 'change' && x.avant === 'termine' && x.apres !== 'termine');
    return e ? e.ref : null;
  });
  await p.evaluate(ref => { document.querySelector('#corps-tableau button[data-ref-plan="' + ref + '"]').scrollIntoView({ block: 'center' }); }, refRecul);
  await p.click('#corps-tableau button[data-ref-plan="' + refRecul + '"]'); await p.waitForTimeout(600);
  const vie = await p.evaluate(ref => {
    const f = document.getElementById('fiche-plan');
    return {
      visible: !f.hidden && f.offsetParent !== null, lignes: document.querySelectorAll('#corps-tableau tr').length,
      ref: (f.querySelector('.ref') || {}).textContent, cases: f.querySelectorAll('.fiche-plan-frise .case').length,
      releves: window.__historiquePlan(ref).length,
      etapes: [...f.querySelectorAll('.fiche-plan-etapes li')].map(li => ({ texte: li.textContent.replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim(), recul: li.classList.contains('recul') })),
      resume: (f.querySelector('.fiche-plan-resume') || {}).textContent,
      auDessus: f.getBoundingClientRect().bottom <= document.getElementById('cadre-tableau').getBoundingClientRect().top + 1
    };
  }, refRecul);
  verifier('cliquer une référence du tableau le réduit à ce plan et ouvre au-dessus son historique : une case par relevé',
    vie.visible && vie.lignes === 1 && vie.ref === refRecul && vie.cases === vie.releves && vie.releves >= 10 && vie.auDessus, JSON.stringify(vie));
  verifier('l’historique d’un plan dé-validé dit son recul, en rouge, et depuis quand il est dans son état',
    vie.etapes.some(e => e.recul && /^S\d{1,2} · \S+ \d{4} ?Terminé → En cours recul$/.test(e.texte)) &&
    /^En cours depuis S\d{1,2} · \S+ \d{4} \((ce relevé|\d+ semaines?)\)/.test(esp14(vie.resume)), JSON.stringify([vie.etapes, vie.resume]));
  await p.click('#fiche-plan button[data-fermer-plan]'); await p.waitForTimeout(400);
  verifier('la croix de l’historique rend le tableau entier', await p.evaluate(() => document.getElementById('fiche-plan').hidden &&
    document.querySelectorAll('#corps-tableau tr').length) === TOTAL);
  const refReemis = await p.evaluate(() => { const e = window.__journal().flatMap(s => s.evenements).find(x => x.type === 'indice'); return e ? e.ref : null; });
  await p.evaluate(ref => { const b = document.querySelector('#corps-tableau button[data-ref-plan="' + ref + '"]'); b.scrollIntoView({ block: 'center' }); b.click(); }, refReemis);
  await p.waitForTimeout(600);
  const vieReemis = await p.evaluate(() => [...document.querySelectorAll('#fiche-plan .fiche-plan-etapes li.indice')].map(li => li.textContent.replace(/\s+/g, ' ').trim()));
  verifier('l’historique d’un plan réémis le suit d’un indice à l’autre : « réémis sous l’indice X (ancienne → nouvelle) »',
    vieReemis.length >= 1 && vieReemis.every(t => /réémis sous l’indice [A-Z] \([A-Z]{2}E\d{4}A\d{6}[A-Z] → [A-Z]{2}E\d{4}A\d{6}[A-Z]\)/.test(t)), JSON.stringify(vieReemis));
  await p.click('#fiche-plan button[data-fermer-plan]'); await p.waitForTimeout(300);

  // --- Le chevron des groupes, comme celui des semaines.
  await p.click('.critique-ligne >> nth=0'); await p.waitForTimeout(400);
  /* Débrief 27 (lot C, X-A6) : la ligne dit « dépliée » (aria-expanded), plus « pressée ». */
  const chevrons = await p.evaluate(() => [...document.querySelectorAll('.critique-ligne')].map(l => ({
    chevron: !!l.querySelector('svg.chevron'), presse: l.getAttribute('aria-expanded'),
    tourne: getComputedStyle(l.querySelector('svg.chevron')).transform })));
  verifier('chaque groupe porte un chevron : vers la droite fermé, vers le bas ouvert — comme les semaines du journal',
    chevrons.every(c => c.chevron) && chevrons.filter(c => c.presse === 'true').every(c => c.tourne !== 'none') &&
    chevrons.filter(c => c.presse !== 'true').every(c => c.tourne === 'none'), JSON.stringify(chevrons.slice(0, 2)));
  await p.click('.critique-ligne >> nth=0'); await p.waitForTimeout(300);

  // --- La vue d'ensemble : les chiffres de chaque contrat, ceux de sa page.
  await p.click('#choix-perimetre button[data-perimetre="PERSO"]'); await p.waitForTimeout(400);
  const avantEns = await p.evaluate(() => ({ phrase: document.getElementById('phrase').textContent, lignes: document.querySelectorAll('#corps-tableau tr').length,
    contrat: document.getElementById('select-contrat').value, jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent).join('|') }));
  await p.click('#voir-ensemble'); await p.waitForTimeout(1500);
  const ens = await p.evaluate(() => [...document.querySelectorAll('#ensemble tbody tr')].map(tr => ({
    nom: tr.querySelector('th button').textContent.trim(), courant: tr.classList.contains('courant'),
    /* La valeur principale de chaque case (la petite ligne dessous à part). */
    cellules: [...tr.querySelectorAll('td')].map(td => ((td.querySelector('.v') || td).textContent).replace(/[\u00a0\u202f]/g, ' ').replace(/\s+/g, ' ').trim()) })));
  const apresEns = await p.evaluate(() => ({ phrase: document.getElementById('phrase').textContent, lignes: document.querySelectorAll('#corps-tableau tr').length,
    contrat: document.getElementById('select-contrat').value, jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent).join('|') }));
  verifier('la vue d’ensemble : une ligne par contrat, le contrat affiché signalé',
    ens.map(r => r.nom).join() === 'HDK,THS,VRK' && ens.filter(r => r.courant).map(r => r.nom).join() === 'HDK', JSON.stringify(ens.map(r => [r.nom, r.courant])));
  verifier('l’ouvrir ne touche à rien de ce que le lecteur regardait : même contrat, même périmètre, mêmes filtres',
    JSON.stringify(avantEns) === JSON.stringify(apresEns), JSON.stringify([avantEns, apresEns]));
  await p.click('#ensemble button[data-fermer-ensemble]'); await p.waitForTimeout(200);
  await p.click('#choix-perimetre button[data-perimetre=""]'); await p.waitForTimeout(400);
  for (const r of ens) {
    await p.selectOption('#select-contrat', r.nom); await p.waitForTimeout(900);
    const page = await p.evaluate(() => {
      const t = [...document.querySelectorAll('#etats .etat-btn')].find(b => b.dataset.famille === 'termine') || document.querySelector('#etats .etat-btn');
      return {
        phrase: document.getElementById('phrase').textContent.replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim(),
        legende: document.getElementById('legende').textContent.replace(/[  ]/g, ' '),
        arret: (document.getElementById('a-surveiller').textContent.match(/(\d+) plans?/) || [])[1] || '—',
        echeance: document.getElementById('echeance-titre').hidden ? '' :
          document.getElementById('echeance-titre').textContent.replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim()
      };
    });
    verifier('vue d’ensemble, ' + r.nom + ' : validés, rythme tenu, à l’arrêt et prochaine échéance sont ceux de sa page',
      page.phrase.indexOf(r.cellules[0].replace(' / ', ' sur ') + ' plans validés') === 0 &&
      page.legende.indexOf('au rythme tenu (' + r.cellules[2] + ')') !== -1 &&
      r.cellules[3] === page.arret &&
      /* THS et VRK n'ont pas de jalon (débrief 17) : ni puce sur leur page,
         ni échéance dans la vue d'ensemble, qui dit « aucun jalon ». */
      (r.nom === 'HDK' ? !!page.echeance && page.echeance.indexOf(r.cellules[4]) !== -1 : page.echeance === '' && r.cellules[4] === 'aucun jalon'),
      JSON.stringify([r.cellules, page]));
  }
  await p.selectOption('#select-contrat', 'HDK'); await p.waitForTimeout(900);

  // --- Sous le concept harnais, les mêmes fonctions.
  await p.click('#choix-indicateur button[data-indicateur="concept"]'); await p.waitForTimeout(800);
  const sousConcept = await p.evaluate(() => ({
    surveiller: !document.getElementById('a-surveiller').hidden,
    journal: document.querySelectorAll('.journal-entetes .entete-col').length,
    reculs: !!document.querySelector('.journal-semaine .compte-passage.recul'),
    jalons: document.querySelectorAll('svg.graphe .jalon').length,
    presse: [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')].map(b => b.dataset.span).join()
  }));
  await p.evaluate(() => { const b = document.querySelector('#corps-tableau button[data-ref-plan]'); b.scrollIntoView({ block: 'center' }); b.click(); });
  await p.waitForTimeout(500);
  const ficheConcept = await p.evaluate(() => !document.getElementById('fiche-plan').hidden && document.querySelectorAll('#fiche-plan .case').length > 1);
  verifier('sous le concept harnais, tout y est : à surveiller, journal, reculs, cinq jalons sur « Échéances », historique d’un plan',
    sousConcept.surveiller && sousConcept.journal >= 3 && sousConcept.reculs && sousConcept.jalons === 5 &&
    sousConcept.presse === 'jalons' && ficheConcept, JSON.stringify([sousConcept, ficheConcept]));
  await p.evaluate(() => { const b = document.querySelector('#fiche-plan button[data-fermer-plan]'); if (b) b.click(); });
  await p.click('#choix-indicateur button[data-indicateur="def"]'); await p.waitForTimeout(700);
  await reinitialiser(p);

  // =================================================================
  /* Débrief 15 : « est-ce qu'on regarde la bonne colonne ? », « tous nos
     calculs sont-ils logiques ? », et « à l'arrêt, qu'est-ce que ça veut
     dire ? ». */
  section('Débrief 15 : la colonne suivie, l’extract du jour, « à l’arrêt » expliqué, les groupes par mois');
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); window.scrollTo(0, 0); });
  await p.waitForTimeout(700);
  const esp15 = t => String(t || '').replace(/[\u00a0\u202f]/g, ' ').replace(/\s+/g, ' ').trim();

  // --- La colonne lue, nommée en bas de page, groupe compris ; et au survol de l'interrupteur.
  const colonnes15 = await p.evaluate(() => ({
    def: document.getElementById('colonne-suivie').textContent,
    titres: [...document.querySelectorAll('#choix-indicateur button')].map(b => b.title)
  }));
  await p.click('#choix-indicateur button[data-indicateur="concept"]'); await p.waitForTimeout(700);
  colonnes15.concept = await p.evaluate(() => document.getElementById('colonne-suivie').textContent);
  await p.click('#choix-indicateur button[data-indicateur="def"]'); await p.waitForTimeout(700);
  verifier('le pied nomme la colonne lue : « HDK AA 011 › Avancement Définition Electrique », puis « … › Avancement Concept Harnais »',
    esp15(colonnes15.def) === 'Colonne suivie : HDK AA 011 › Avancement Définition Electrique' &&
    esp15(colonnes15.concept) === 'Colonne suivie : HDK AA 011 › Avancement Concept Harnais', JSON.stringify(colonnes15));
  verifier('et chaque bouton de l’interrupteur dit, au survol, la colonne qu’il lit',
    colonnes15.titres.join('|') === 'Colonne lue : HDK AA 011 › Avancement Définition Electrique|Colonne lue : HDK AA 011 › Avancement Concept Harnais',
    JSON.stringify(colonnes15.titres));

  // --- « à l'arrêt » se définit dans le bloc, en toutes lettres, dès qu'un groupe en compte.
  const arret15 = await p.evaluate(() => ({
    note: (document.querySelector('#zone-critique .note-arret') || { textContent: '' }).textContent,
    lignes: document.querySelectorAll('.critique-ligne .arret-n').length
  }));
  verifier('« 1 à l’arrêt » s’explique dans le bloc : « à l’arrêt = en cours, sans changement depuis 6 semaines ou plus »',
    arret15.lignes > 0 && /^à l’arrêt = en cours, sans changement depuis 6 semaines ou plus\./.test(esp15(arret15.note)), JSON.stringify(arret15));

  // --- L'extract recollé après le dernier archivage : un point de plus, à la semaine où l'on est.
  const vivant15 = async (bouge) => {
    await p.evaluate(bouge => {
      const s = window.__jeuDExemple('HDK');
      const recule = sem => { let [a, w] = sem.split('-S').map(Number); w -= 2; if (w < 1) { a--; w += 52; } return a + '-S' + String(w).padStart(2, '0'); };
      s.releves = s.releves.map(r => Object.assign({}, r, { semaine: recule(r.semaine) }));
      if (bouge) s.plans.filter(x => window.__classer(x.avancement) === 'encours').slice(0, 3).forEach(x => { x.avancement = 'Validé'; });
      window.__chargerSource(s);
    }, bouge);
    await p.waitForTimeout(500);
    return p.evaluate(() => ({
      pts: window.__serieAffichee().pts.map(x => x.i), jour: window.__semaineDuTitre().iAuj, auj: window.__semaineDuTitre().auj,
      pied: document.getElementById('import').textContent, note: document.getElementById('note-graphe').textContent,
      repere: (document.querySelector('.repere-auj') || {}).textContent, journal: (document.querySelector('.journal-semaine .sem') || {}).textContent
    }));
  };
  const immobile = await vivant15(false), bouge15 = await vivant15(true);
  verifier('un extract inchangé depuis le dernier relevé reste ce relevé-là : pas de palier inventé à la semaine où l’on est',
    /* Débrief 27 (B3) : le repère dit toujours « aujourd'hui » (un seul « maintenant ») ; le dernier point reste avant lui. */
    immobile.pts[immobile.pts.length - 1] < immobile.jour && immobile.repere === 'aujourd’hui' && !/pas encore archivé/.test(immobile.pied),
    JSON.stringify(immobile));
  verifier('un extract recollé depuis devient un point de plus, à la semaine où l’on est — le relevé d’avant reste le sien',
    bouge15.pts[bouge15.pts.length - 1] === bouge15.jour && bouge15.pts.length === immobile.pts.length + 1 && bouge15.repere === 'aujourd’hui',
    JSON.stringify(bouge15));
  verifier('le pied, la note du graphique et le journal le disent : l’extract du jour, pas encore archivé',
    /· l’extract du jour, pas encore archivé, compte pour S\d{1,2} · \S+ \d{4}$/.test(esp15(bouge15.pied)) &&
    /, puis l’extract du jour en S\d{1,2} · \S+ \d{4}, pas encore archivé$/.test(esp15(bouge15.note)) &&
    /* Débrief 27 (lot B, P-F10) : la ligne du journal dit « S40 · depuis le
       ven. … » — l'extract du jour comparé au dernier relevé archivé —, sous
       le même numéro de semaine que le pied. */
    esp15(bouge15.journal).split(' · ')[0] === esp15(bouge15.pied).replace(/^.*compte pour /, '').split(' · ')[0] &&
    /^S\d{1,2} · depuis le (lun|mar|mer|jeu|ven|sam|dim)\. \d{1,2} \S+/.test(esp15(bouge15.journal)), JSON.stringify([bouge15.pied, bouge15.note, bouge15.journal]));
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); });
  await p.waitForTimeout(500);

  // --- Un groupe « par mois de création » a son historique, même quand le classeur n'archive pas ce découpage.
  const mois15 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.releves.forEach(r => { r.groupes = {}; });          // comme le classeur : pas de comptes « par mois »
    window.__chargerSource(s);
    return true;
  });
  await p.waitForTimeout(500);
  await p.selectOption('#dim-critique', '_mois'); await p.waitForTimeout(400);
  /* Débrief 27 (lot C) : la courbe d'un groupe, c'est le filtre de la page
     posé sur lui (le bouton de sa liste dépliée). */
  const serieMois = await p.evaluate(() => {
    document.querySelectorAll('.critique-ligne')[0].click();
    document.getElementById('filtrer-groupe-page').click();
    const pts = window.__serieAffichee().pts;
    const val = document.querySelectorAll('.critique-ligne')[0].dataset.groupe;
    /* recompte à la main : plans du mois, relevé par relevé */
    const s = window.__jeuDExemple('HDK');
    const MC = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
    const moisDe = d => { const v = window.__anneeEtMois(d); return v ? MC[v.mois - 1] + ' ' + v.annee : '\u2014'; };
    const refsMois = new Set(s.plans.filter(p => moisDe(p[s.cleDate]) === val).map(p => p.reference));
    const attendu = s.releves.slice().sort((a, b) => a.semaine < b.semaine ? -1 : 1)
      .map(r => Object.keys(r.plans).filter(ref => refsMois.has(ref) && window.__classer(r.plans[ref]) === 'termine').length);
    document.getElementById('filtrer-groupe-page').click();
    document.querySelectorAll('.critique-ligne')[0].click();
    return { val, termines: pts.map(x => x.termine), totaux: pts.map(x => x.total), attendu };
  });
  verifier('la courbe d’un mois de création part de ses vrais comptes, pas de zéro : chaque relevé recompté sur sa carte plan par plan',
    mois15 && serieMois.totaux.every(t => t > 0) && serieMois.termines.slice(0, -1).join() === serieMois.attendu.slice(0, serieMois.termines.length - 1).join(),
    JSON.stringify(serieMois));
  await p.selectOption('#dim-critique', 'ata'); await p.waitForTimeout(300);

  // --- Un périmètre se reconnaît sans espaces : « Base / Option » dans l'extract est le « BASE/OPTION » du jalon.
  const per15 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.plans.forEach(p => { if (p[s.cleDomaine] === 'BASE/OPTION') p[s.cleDomaine] = 'Base / Option'; });
    const nBase = s.plans.filter(p => p[s.cleDomaine] === 'Base / Option').length;
    window.__chargerSource(s);
    [...document.querySelectorAll('#choix-perimetre button')].find(b => b.dataset.perimetre === 'Base / Option').click();
    const legendes = [...document.querySelectorAll('.legende-jalon')].map(l => ({ texte: l.textContent.replace(/\s+/g, ' '), hors: l.classList.contains('hors-perimetre') }));
    const b = window.__bilanEcheance(1);          // Diffusion PH Base, périmètre BASE/OPTION
    return { nBase, legendes, bilan: b && { domaine: b.domaine, total: b.total } };
  });
  await p.waitForTimeout(400);
  const legPH = n => per15.legendes.find(l => l.texte.indexOf(n) !== -1) || {};
  verifier('sous « Base / Option », le jalon BASE/OPTION est le sien — il compte, l’autre non — et son bilan porte sur ses plans',
    legPH('Diffusion PH Base').hors === false && legPH('Diffusion PH Perso').hors === true &&
    !!per15.bilan && per15.bilan.domaine === 'Base / Option' && per15.bilan.total === per15.nBase && per15.nBase > 0, JSON.stringify(per15));
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); });
  await p.waitForTimeout(500);
  await reinitialiser(p);

  // =================================================================
  /* Débrief 16, au bureau sur les vraies données : « 0 sur 600 plans
     terminés » (un mot « fini » que la page ne connaissait pas), et un
     journal vide avec deux semaines archivées qui disait encore d'attendre
     le deuxième relevé. */
  section('Débrief 16 : vocabulaire inconnu signalé, accords, journal vide expliqué');
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); window.scrollTo(0, 0); });
  await p.waitForTimeout(600);
  verifier('sur la démonstration, aucune alerte de vocabulaire : des plans sont comptés validés',
    await p.evaluate(() => document.getElementById('alerte-valeurs').hidden));
  const vocab16 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.plans.forEach(x => { if (window.__classer(x.avancement) === 'termine') x.avancement = 'Released'; });
    window.__chargerSource(s);
    const z = document.getElementById('alerte-valeurs');
    return { visible: !z.hidden, texte: z.textContent.replace(/[\u00a0\u202f]/g, ' '), phrase: document.getElementById('phrase').textContent.replace(/\s+/g, ' ') };
  });
  await p.waitForTimeout(300);
  verifier('un mot « fini » inconnu : la page dit « Aucun plan n’est compté terminé », nomme la colonne et les valeurs lues, et où les déclarer',
    vocab16.visible && /^0 sur 640 plans validés/.test(vocab16.phrase) && /^Aucun plan n’est compté « validé »\./.test(vocab16.texte) &&
    /HDK AA 011 › Avancement Définition Electrique/.test(vocab16.texte) && /« Released » \(\d+\)/.test(vocab16.texte) && /VALEURS_FINIES/.test(vocab16.texte),
    JSON.stringify(vocab16));
  const accords16 = await p.evaluate(() => ['Validé', 'Validée', 'VALIDÉS', 'Non validé', 'OK', 'Non OK', 'Non terminé', '3 - Validé', '1 - En cours', '2026-09-01', '100 %', 'Pas commencé']
    .map(v => v + '=' + window.__classer(v)).join(' | '));
  verifier('« Validée », « Validés », « 3 - Validé » comptent comme « Validé » ; « Non OK », « Non terminé », une date, non',
    accords16 === 'Validé=termine | Validée=termine | VALIDÉS=termine | Non validé=encours | OK=termine | Non OK=encours | Non terminé=encours | ' +
      '3 - Validé=termine | 1 - En cours=encours | 2026-09-01=encours | 100 %=termine | Pas commencé=afaire', accords16);

  // --- Le journal vide dit la vraie raison.
  const journal16 = await p.evaluate(() => {
    const lire = () => (document.querySelector('#zone-journal .journal-vide') || { textContent: '' }).textContent.replace(/[\u00a0\u202f]/g, ' ');
    const s1 = window.__jeuDExemple('HDK');
    s1.releves = s1.releves.slice(-1);
    window.__chargerSource(s1);
    const un = lire();
    const s2 = window.__jeuDExemple('HDK');
    const carte = {}; s2.plans.forEach(x => { carte[x.reference] = x.avancement; });
    const deux = s2.releves.slice(-2).map(r => Object.assign({}, r, { plans: Object.assign({}, carte) }));
    s2.releves = deux;
    window.__chargerSource(s2);
    return { un, identiques: lire(), n: s2.plans.length };
  });
  verifier('un seul relevé : le journal le nomme et dit que deux archivages la même semaine n’en font qu’un',
    /^Un seul relevé archivé pour l’instant \(S\d{1,2} · \S+ \d{4}\) : le journal se remplira au suivant\. Deux archivages dans la même semaine n’en font qu’un/.test(journal16.un),
    journal16.un);
  verifier('deux relevés identiques : « Aucun plan n’a changé de valeur entre … et … », et le geste pour y remédier',
    new RegExp('^Aucun plan n’a changé de valeur entre S\\d{1,2} · \\S+ \\d{4} et S\\d{1,2} · \\S+ \\d{4} \\(' + journal16.n + ' plans comparés\\)').test(journal16.identiques) &&
    /même export qui a été archivé deux fois/.test(journal16.identiques), journal16.identiques);
  /* Les pièges des vraies données, trouvés en relecture : comptes archivés
     figés au classement du jour d'archivage, références en double, relevé
     identique au précédent. */
  const pieges16 = await p.evaluate(() => {
    const out = {};
    // 1. Des comptes archivés « 0 terminé » (ancien classement) : la page recompte sur la carte.
    const s1 = window.__jeuDExemple('HDK');
    s1.releves.forEach(r => { r.termine = 0; r.encours = r.total; });
    window.__chargerSource(s1);
    const pts = window.__serieAffichee().pts;
    const r0 = s1.releves.slice().sort((a, b) => a.semaine < b.semaine ? -1 : 1)[0];
    out.recompte = { premier: pts[0].termine, attendu: Object.keys(r0.plans).filter(k => window.__classer(r0.plans[k]) === 'termine').length };
    // 2. Trois références en double.
    const s2 = window.__jeuDExemple('HDK');
    s2.plans = s2.plans.concat(s2.plans.slice(0, 3).map(x => Object.assign({}, x)));
    window.__chargerSource(s2);
    out.doublons = document.getElementById('alerte-valeurs').hidden ? '' : document.getElementById('alerte-valeurs').textContent;
    // 3. Un relevé identique au précédent, plan par plan.
    const s3 = window.__jeuDExemple('HDK');
    const tries = s3.releves.slice().sort((a, b) => a.semaine < b.semaine ? -1 : 1);
    tries[tries.length - 2].plans = Object.assign({}, tries[tries.length - 3].plans);
    window.__chargerSource(s3);
    out.note = document.getElementById('note-graphe').textContent.replace(/[\u00a0\u202f]/g, ' ');
    out.identiqueSem = tries[tries.length - 2].semaine;
    // 4. Deux relevés seulement, une semaine d'écart : l'infobulle du rythme s'accorde (débrief 17).
    const s4 = window.__jeuDExemple('HDK');
    const t4 = s4.releves.slice().sort((a, b) => a.semaine < b.semaine ? -1 : 1);
    s4.releves = t4.slice(-2);
    window.__chargerSource(s4);
    const leg4 = [...document.querySelectorAll('.legende-item span[title]')].map(x => x.getAttribute('title')).filter(t => /du premier au dernier relevé/.test(t))[0] || '';
    out.accord = leg4.replace(/[\u00a0\u202f]/g, ' ');
    out.ecart4 = t4.length >= 2 ? t4[t4.length - 1].semaine + '/' + t4[t4.length - 2].semaine : '';
    window.__chargerSource(window.__jeuDExemple('HDK'));
    return out;
  });
  verifier('deux relevés à une semaine d\'écart : l\'infobulle du rythme dit « en 1 semaine », jamais « 1 semaines »',
    / en 1 semaine, du premier au dernier relevé/.test(pieges16.accord) && !/\b1 semaines\b|\b1 plans\b|\b0 plans\b/.test(pieges16.accord),
    JSON.stringify([pieges16.accord, pieges16.ecart4]));
  verifier('des comptes archivés figés à « 0 validé » : la courbe recompte chaque relevé sur sa carte plan par plan, au classement du jour',
    pieges16.recompte.premier > 0 && pieges16.recompte.premier === pieges16.recompte.attendu, JSON.stringify(pieges16.recompte));
  verifier('des références en double : la page le dit — « 3 lignes répètent une référence déjà vue »',
    /3 lignes répètent une référence déjà vue\. Seule la première ligne de chaque référence compte et s’affiche/.test(pieges16.doublons), pieges16.doublons);
  verifier('un relevé identique au précédent : la note du graphique le constate, sans reproche (lue par tous)',
    /S\d{1,2} · \S+ \d{4} : aucun changement depuis le relevé d’avant, plan par plan/.test(pieges16.note) && !/recoll/.test(pieges16.note), pieges16.note);
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); });
  await p.waitForTimeout(500);
  await reinitialiser(p);

  // =================================================================
  /* Débrief 18 : « je ne peux filtrer que par changement d'indice » — les
     petites pastilles de couleur partout : le journal (toutes les valeurs,
     jamais périmé, les plans devenus validés sous un nouvel indice
     compris), le bloc par ATA/ECP, et le graphique. */
  section('Débrief 18 : filtres par valeur à pastilles — journal, bloc par groupe, graphique');
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); window.scrollTo(0, 0); });
  await p.waitForTimeout(600);
  const nDe18 = t => Number(String(t || '').replace(/[\s  ]/g, ''));

  // --- Le journal : chaque pilule, la couleur de sa tuile et son compte juste.
  const j18 = await p.evaluate(() => {
    const fond = e => e ? getComputedStyle(e).backgroundColor + '|' + e.className : null;
    const evts = [].concat(...window.__journalAffiche().map(s => s.evenements));
    const estRecul = e => e.type === 'change' && ((e.avant === 'termine' && e.apres !== 'termine') || (e.avant === 'encours' && e.apres === 'afaire'));
    const attendu = { reculs: evts.filter(estRecul).length, indice: evts.filter(e => e.type === 'indice').length,
                      /* Débrief 23 : les nouveaux et les disparus aussi. */
                      nouveaux: evts.filter(e => e.type === 'nouveau').length, disparus: evts.filter(e => e.type === 'disparu').length };
    evts.forEach(e => { if ((e.type === 'change' || e.type === 'indice') && e.cApres !== e.cAvant) attendu[e.cApres] = (attendu[e.cApres] || 0) + 1; });
    const boutons = [...document.querySelectorAll('#filtre-journal button[data-journal]:not([data-journal=""])')].map(b => ({
      cle: b.dataset.journal, n: b.querySelector('.n') ? b.querySelector('.n').textContent : null, off: b.disabled,
      pastille: fond(b.querySelector('.pastille')),
      tuile: fond(document.querySelector('#etats .etat-btn[data-cle="' + b.dataset.journal + '"] .pastille'))
    }));
    return { boutons, attendu, reemisArrivees: evts.filter(e => e.type === 'indice' && e.cApres !== e.cAvant).length };
  });
  verifier('journal : chaque pilule de valeur a la pastille de sa tuile du haut (couleur et hachure)',
    j18.boutons.filter(b => b.tuile).length >= 2 &&
    j18.boutons.every(b => !b.tuile || b.pastille === b.tuile), JSON.stringify(j18.boutons.filter(b => b.pastille !== b.tuile && b.tuile)));
  /* Débrief 19 : seulement les passages qu'il y a — une pastille par sorte
     de passage présente, aucune pour les autres, et aucune grisée. */
  verifier('journal : une pilule par sorte de passage qu’il y a, chacune avec son nombre — passages, reculs et réémissions —, aucune à zéro ni grisée',
    j18.boutons.every(b => nDe18(b.n) === (j18.attendu[b.cle] || 0) && nDe18(b.n) > 0 && !b.off) &&
    Object.keys(j18.attendu).filter(k => j18.attendu[k] > 0).sort().join() === j18.boutons.map(b => b.cle).sort().join(),
    JSON.stringify([j18.boutons.map(b => b.cle + '=' + b.n), j18.attendu]));
  verifier('journal : la démonstration a des plans réémis qui ont changé de valeur au passage — ils comptent sous leur valeur d’arrivée',
    j18.reemisArrivees >= 1, String(j18.reemisArrivees));
  /* Sous la recherche du journal, chaque pastille compte ce qu'elle
     montrerait pour ce plan-là (relecture 18) ; le choix posé tient. */
  const refJ18 = await p.evaluate(() => [].concat(...window.__journalAffiche().map(s => s.evenements)).find(e => e.type === 'change' && e.cApres === 'encours').ref);
  await p.click('#filtre-journal button[data-journal="termine"]'); await p.waitForTimeout(250);
  await p.fill('#recherche-journal', refJ18); await p.waitForTimeout(400);
  const rechJ18 = await p.evaluate(ref => {
    const evts = [].concat(...window.__journalAffiche().map(s => s.evenements)).filter(e => e.ref === ref || e.ancienne === ref);
    const estRecul = e => e.type === 'change' && ((e.avant === 'termine' && e.apres !== 'termine') || (e.avant === 'encours' && e.apres === 'afaire'));
    const att = { reculs: evts.filter(estRecul).length, indice: evts.filter(e => e.type === 'indice').length };
    evts.forEach(e => { if ((e.type === 'change' || e.type === 'indice') && e.cApres !== e.cAvant) att[e.cApres] = (att[e.cApres] || 0) + 1; });
    const lus = [...document.querySelectorAll('#filtre-journal button[data-journal]:not([data-journal=""])')].map(b => ({
      cle: b.dataset.journal, n: Number(b.querySelector('.n').textContent), off: b.disabled, presse: b.getAttribute('aria-pressed') === 'true' }));
    return { lus, att, journal: window.__vueValeurs().journal };
  }, refJ18);
  verifier('journal : sous une recherche, seules les pastilles de ce plan-là restent, avec ses nombres — le choix posé tient et reste là',
    rechJ18.journal === 'termine' && rechJ18.lus.every(b => b.n === (rechJ18.att[b.cle] || 0) && !b.off && (b.n > 0 || b.presse)) &&
    rechJ18.lus.some(b => b.cle === 'termine' && b.presse) &&
    Object.keys(rechJ18.att).filter(k => rechJ18.att[k] > 0).every(k => rechJ18.lus.some(b => b.cle === k)),
    JSON.stringify(rechJ18));
  await p.fill('#recherche-journal', ''); await p.waitForTimeout(350);
  await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(250);
  // Une valeur que personne n'a atteinte : pas de pilule (débrief 19).
  const grise18 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const ref = s.plans[0].reference;
    s.plans[0].avancement = 'Statut inédit';
    s.releves.forEach(r => { if (r.plans && Object.prototype.hasOwnProperty.call(r.plans, ref)) r.plans[ref] = 'Statut inédit'; });
    window.__chargerSource(s);
    return { present: !!document.querySelector('#filtre-journal button[data-journal="statutinedit"]'),
             tuile: !!document.querySelector('#etats .etat-btn[data-cle="statutinedit"]'), journal: window.__vueValeurs().journal };
  });
  verifier('journal : une valeur que personne n’a encore atteinte a sa tuile en haut, mais pas de pilule dans le journal',
    !grise18.present && grise18.tuile && grise18.journal === '', JSON.stringify(grise18));
  // Jamais périmée : un filtre posé, puis une source à un seul relevé.
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.click('#filtre-journal button[data-journal="termine"]'); await p.waitForTimeout(300);
  const perime18 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.releves = s.releves.slice(-1);
    window.__chargerSource(s);
    const r = document.getElementById('filtre-journal');
    return { boutons: r.querySelectorAll('button').length, cachee: r.hidden, journal: window.__vueValeurs().journal,
             message: !!document.querySelector('#zone-journal .journal-vide'),
             recherche: !!document.getElementById('recherche-journal').offsetParent };
  });
  /* Débrief 27 (lot B, D8) : un journal vide efface aussi sa recherche, qui
     n'agirait sur rien ; le message reste (un bloc calme, voir la section
     du lot B). */
  verifier('journal vide : aucune pastille, pas même « Tout » — rien de la source d’avant ; le message reste, la recherche (qui n’agirait sur rien) s’efface',
    perime18.boutons === 0 && perime18.cachee && perime18.journal === '' && perime18.message && !perime18.recherche, JSON.stringify(perime18));
  // Une valeur d'hier : plus personne ne la porte, mais des plans y sont passés.
  const hier18 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.plans.forEach(x => { if (window.__classer(x.avancement) === 'encours') x.avancement = 'Terminé'; });
    window.__chargerSource(s);
    const cles = [...document.querySelectorAll('#filtre-journal button')].map(b => b.dataset.journal);
    const b = document.querySelector('#filtre-journal button[data-journal="encours"]');
    /* Débrief 23 : après l'indice viennent les nouveaux et les disparus, s'il y en a. */
    const evts = [].concat(...window.__journalAffiche().map(s => s.evenements));
    const suite = (evts.some(e => e.type === 'nouveau') ? ',nouveaux' : '') + (evts.some(e => e.type === 'disparu') ? ',disparus' : '');
    return { dansValeurs: window.__valeurs().some(v => v.cle === 'encours'), cles: cles.join(), off: b ? b.disabled : null,
             pastille: b ? !!b.querySelector('.pastille') : false, suite: suite };
  });
  verifier('journal : une valeur que plus aucun plan ne porte garde sa pilule, après celles des tuiles, si des plans y sont passés',
    /* Débrief 27 (lot B) : « Mouvements » range les reculs, les nouveaux, les disparus, puis l'indice. */
    !hier18.dansValeurs && hier18.cles.endsWith(',encours,reculs' + hier18.suite + ',indice') && hier18.off === false && hier18.pastille, JSON.stringify(hier18));
  await p.click('#filtre-journal button[data-journal="encours"]'); await p.waitForTimeout(300);
  await toutDeplier();
  const hierLignes = await p.evaluate(() => [...new Set([...document.querySelectorAll('.journal-ligne .etiq-etat.apres')].map(e => e.textContent.trim()))].join());
  verifier('et son filtre ne montre que des arrivées à elle', hierLignes === 'En cours', hierLignes);
  // Le graphique la garde aussi : on la voit descendre jusqu'à zéro.
  const hierG18 = await p.evaluate(() => {
    const cles = [...document.querySelectorAll('#filtre-valeur-graphe button')].map(b => b.dataset.valeurGraphe);
    const b = document.querySelector('#filtre-valeur-graphe button[data-valeur-graphe="encours"]');
    if (!b) return { cles };
    b.click();
    const pts = window.__serieValeur('encours').pts;
    return { cles, off: b.disabled, max: Math.max(...pts.map(x => x.termine)), fin: pts[pts.length - 1].termine,
             note: document.getElementById('note-graphe').textContent, courbe: !!document.querySelector('#zone-graphe path.courbe'),
             garde: window.__vueValeurs().graphe };
  });
  verifier('graphique : une valeur que plus aucun plan ne porte garde sa pilule, et sa courbe descend jusqu’à zéro',
    hierG18.cles[hierG18.cles.length - 1] === 'encours' && hierG18.off === false && hierG18.max > 0 && hierG18.fin === 0 &&
    hierG18.courbe && hierG18.garde === 'encours' && /^Plans « En cours » · /.test(hierG18.note), JSON.stringify(hierG18));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(400);
  // Le concept harnais : la rangée prend ses valeurs, jamais celles de la définition.
  const concept18 = await p.evaluate(() => {
    const b = document.querySelector('#choix-indicateur button[data-indicateur="concept"]');
    if (!b || document.getElementById('choix-indicateur').hidden) return null;
    b.click();
    const evts = [].concat(...window.__journalAffiche().map(s => s.evenements));
    const arrivees = new Set(evts.filter(e => (e.type === 'change' || e.type === 'indice') && e.cApres !== e.cAvant).map(e => e.cApres));
    const vals = window.__valeurs().map(v => v.cle);
    const r = { cles: [...document.querySelectorAll('#filtre-journal button')].map(x => x.dataset.journal).filter(Boolean).filter(k => ['reculs', 'indice', 'nouveaux', 'disparus'].indexOf(k) === -1).join(),
                attendu: vals.filter(k => arrivees.has(k)).join(),
                bloc: [...document.querySelectorAll('#filtre-valeur-groupe button')].map(x => x.dataset.valeurBloc).join(),
                attenduBloc: (vals.length ? [''].concat(vals) : []).join() };
    document.querySelector('#choix-indicateur button[data-indicateur="def"]').click();
    return r;
  });
  verifier('concept harnais : les rangées du journal et du bloc prennent ses valeurs à lui — seulement celles qu’il y a, comme sous la définition',
    !!concept18 && concept18.cles === concept18.attendu && concept18.bloc === concept18.attenduBloc, JSON.stringify(concept18));
  await p.waitForTimeout(400);
  // Au clavier, le focus reste sur la pilule choisie.
  await p.focus('#filtre-journal button[data-journal="indice"]'); await p.keyboard.press('Enter'); await p.waitForTimeout(300);
  verifier('journal : au clavier, Entrée choisit la pilule et le focus y reste',
    await p.evaluate(() => document.activeElement && document.activeElement.dataset.journal === 'indice' && window.__vueValeurs().journal === 'indice'));
  // Sous une pastille, une recherche vaine dit parmi quoi elle a cherché.
  await p.click('#filtre-journal button[data-journal="reculs"]'); await p.waitForTimeout(300);
  await p.fill('#recherche-journal', 'ZZZ-introuvable'); await p.waitForTimeout(350);
  const vain18 = await p.evaluate(() => (document.querySelector('#zone-journal .journal-vide') || { textContent: '' }).textContent.replace(/[\u00a0\u202f]/g, ' '));
  verifier('journal : sous « Reculs », une recherche vaine dit « parmi les reculs » et que « Tout » cherche partout',
    /^Aucun changement pour « ZZZ-introuvable » parmi les reculs dans l’historique — « Tout » les cherche tous\./.test(vain18), vain18);
  await p.fill('#recherche-journal', ''); await p.waitForTimeout(350);
  const titres18 = await p.evaluate(() => [...document.querySelectorAll('#filtre-journal button[title]')].map(b => b.getAttribute('title')));
  verifier('journal : les infobulles des pastilles s’accordent (« 1 arrivée », « 3 arrivées »), jamais « Les plan »',
    titres18.length > 3 && !titres18.some(t => /\bLes plan\b|\b1 arrivées\b/.test(t)) && titres18.some(t => /^\d+ arrivées? à « /.test(t)), JSON.stringify(titres18));
  await p.click('#filtre-journal button[data-journal=""]'); await p.waitForTimeout(300);

  // --- Le bloc par groupe.
  const avantBloc = await p.evaluate(() => ({
    lignes: [...document.querySelectorAll('.critique-ligne')].map(l => l.dataset.groupe + '=' + l.querySelector('.critique-total').textContent),
    etats: [...document.querySelectorAll('#etats .etat-n')].map(x => x.textContent).join(),
    rangee: (() => { const z = document.getElementById('filtre-valeur-groupe'); return {
      cles: [...z.querySelectorAll('button')].map(b => b.dataset.valeurBloc).join(), visible: !z.hidden,
      horsTete: !z.closest('.section-tete'), apresIndice: !!z.closest('.ligne-filtres') && z.closest('.ligne-filtres').previousElementSibling.id === 'indice-dim',
      presse: [...z.querySelectorAll('button[aria-pressed="true"]')].map(b => b.dataset.valeurBloc).join() }; })(),
    attendu: ['', ...window.__valeurs().filter(v => v.n > 0).map(v => v.cle)].join(),
    couleurs: [...document.querySelectorAll('#filtre-valeur-groupe button[data-valeur-bloc]:not([data-valeur-bloc=""])')].every(b =>
      getComputedStyle(b.querySelector('.pastille')).backgroundColor ===
      getComputedStyle(document.querySelector('#etats .etat-btn[data-cle="' + b.dataset.valeurBloc + '"] .pastille')).backgroundColor)
  }));
  verifier('bloc : sous l’explication de la dimension, une ligne « Tout » puis chaque valeur présente dans l’ordre des tuiles, aux couleurs des tuiles',
    avantBloc.rangee.visible && avantBloc.rangee.horsTete && avantBloc.rangee.apresIndice && avantBloc.rangee.cles === avantBloc.attendu &&
    avantBloc.rangee.presse === '' && avantBloc.couleurs, JSON.stringify(avantBloc.rangee));
  await p.click('#filtre-valeur-groupe button[data-valeur-bloc="termine"]'); await p.waitForTimeout(400);
  const blocT = await p.evaluate(TOTAL => {
    const lignes = [...document.querySelectorAll('.critique-ligne')];
    return {
      n: lignes.length,
      somme: lignes.reduce((t, l) => t + Number(l.querySelector('.critique-total').textContent), 0),
      tuile: Number(document.querySelector('#etats .etat-btn[data-cle="termine"] .etat-n').textContent.replace(/\s/g, '')),
      sur: lignes.map(l => l.dataset.groupe + '=' + (l.querySelector('.sur-n') || { textContent: '' }).textContent.replace(/^sur (\d+).*$/, '$1')),
      sansValeur: lignes.every(l => l.classList.contains('sans-valeur') === (l.querySelector('.critique-total').textContent === '0')),
      barres: lignes.every(l => { const b = l.querySelector('.critique-barre'); const e = b.querySelectorAll('span.eclaire');
        const w = [...b.children].reduce((t, s) => t + parseFloat(s.style.width), 0);
        return b.classList.contains('focalise') && (Number(l.querySelector('.critique-total').textContent) === 0 ? e.length === 0 : e.length === 1 && e[0].dataset.cle === 'termine') && Math.abs(w - 100) < 0.5; }),
      etats: [...document.querySelectorAll('#etats .etat-n')].map(x => x.textContent).join(),
      tableau: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length === TOTAL,
      reinit: document.getElementById('filtres-actifs').hidden,
      jetons: document.querySelectorAll('#filtres-actifs button[data-retirer]').length,
      note: (document.querySelector('#zone-critique .critique-note.note-valeur') || { textContent: '' }).textContent.replace(/[  ]/g, ' '),
      entete: !!document.querySelector('button[data-trig="total"] .pastille')
    };
  }, TOTAL);
  verifier('bloc sous « Terminé » : toutes les lignes restent, leurs comptes font le nombre de la tuile, chacune « sur » son total',
    blocT.n === avantBloc.lignes.length && blocT.somme === blocT.tuile &&
    blocT.sur.slice().sort().join() === avantBloc.lignes.slice().sort().join() && blocT.sansValeur, JSON.stringify(blocT));
  verifier('bloc : la barre passe aux valeurs, seule celle choisie s’éclaire, toujours 100 %',
    blocT.barres);
  verifier('bloc : le filtre ne touche qu’au bloc — tuiles, tableau, bandeau des filtres inchangés',
    blocT.etats === avantBloc.etats && blocT.tableau && blocT.reinit && blocT.jetons === 0, JSON.stringify([blocT.etats, avantBloc.etats, blocT.tableau, blocT.reinit, blocT.jetons]));
  verifier('bloc : l’en-tête « plans » prend la pastille, et une note dit que la fin estimée et les rythmes restent ceux du groupe',
    blocT.entete && /^Plans et répartition : les plans « Terminé » de chaque groupe, sur son total/.test(blocT.note) && /Fin estimée et rythmes : sur tous ses plans\.$/.test(blocT.note), blocT.note);
  // Ce qui est arrivé à la valeur au dernier relevé, groupe par groupe.
  const gains18 = await p.evaluate(() => {
    const J = window.__journal(), sem = J[0];
    const dim = document.getElementById('dim-critique').value;
    const lignes = [...document.querySelectorAll('.critique-ligne')];
    const affiches = lignes.reduce((t, l) => { const b = l.querySelector('.sur-n b'); return t + (b ? Number(b.textContent.replace('+', '')) : 0); }, 0);
    const attendus = sem.evenements.filter(e => (e.type === 'change' || e.type === 'indice') && e.cApres === 'termine' && e.cAvant !== 'termine').length;
    return { affiches, attendus, dim };
  });
  verifier('bloc : « +n » sous chaque groupe — les plans arrivés à la valeur au dernier relevé ; leur somme est celle du journal de cette semaine',
    gains18.affiches === gains18.attendus && gains18.attendus > 0, JSON.stringify(gains18));
  // Tri sur la valeur. Le tri du bloc est mémorisé : on part de celui
  // qu'ont laissé les sections d'avant, et on le rend tel quel.
  const etatTri18 = () => p.evaluate(() => {
    const b = document.querySelector('button[data-trig][data-actif="true"]');
    const d = b && b.querySelector('path') ? b.querySelector('path').getAttribute('d') : '';
    return b ? b.dataset.trig + ':' + (/^M5 1\.5v7/.test(d) ? 'desc' : 'asc') : '';
  });
  const triInitial18 = await etatTri18();
  for (let k = 0; k < 3 && await etatTri18() !== 'total:desc'; k++) { await p.click('button[data-trig="total"]'); await p.waitForTimeout(250); }
  const tri18 = await p.evaluate(() => [...document.querySelectorAll('.critique-ligne .critique-total')].map(e => Number(e.textContent)));
  verifier('bloc : sous une valeur, « plans » range par son nombre, du plus grand au plus petit',
    (await etatTri18()) === 'total:desc' && tri18.every((n, k) => k === 0 || tri18[k - 1] >= n), tri18.join());
  for (let k = 0; k < 3 && await etatTri18() !== triInitial18; k++) {
    await p.click('button[data-trig="' + triInitial18.split(':')[0] + '"]'); await p.waitForTimeout(250);
  }
  // Dépliage : une seule sous-liste, celle de la valeur.
  const ligne18 = await p.evaluate(() => {
    const l = [...document.querySelectorAll('.critique-ligne')].find(x => Number(x.querySelector('.critique-total').textContent) > 0);
    return l ? { g: l.dataset.groupe, n: Number(l.querySelector('.critique-total').textContent) } : null;
  });
  await p.evaluate(g => [...document.querySelectorAll('.critique-ligne')].find(x => x.dataset.groupe === g).click(), ligne18.g);
  await p.waitForTimeout(500);
  const deplie18 = await p.evaluate(() => {
    const r = document.querySelector('#zone-critique .groupe-refs');
    return { sous: r ? r.querySelectorAll('.sous-groupe').length : 0, titre: r && r.querySelector('.sous-titre') ? r.querySelector('.sous-titre').textContent : '',
             jetons: r ? r.querySelectorAll('.jeton-ud').length : 0, lignes: document.querySelectorAll('.critique-ligne').length,
             entete: r ? r.querySelector('.entete').textContent.replace(/[  ]/g, ' ') : '' };
  });
  verifier('bloc : déplier un groupe sous « Terminé » ne montre que ses plans « Terminé », les autres lignes restent',
    deplie18.sous === 1 && /^Terminé/.test(deplie18.titre) && deplie18.jetons === ligne18.n && deplie18.lignes === avantBloc.lignes.length &&
    new RegExp('^' + ligne18.n + ' plans? « Terminé » sur \\d+').test(deplie18.entete), JSON.stringify([deplie18, ligne18]));
  await p.evaluate(g => [...document.querySelectorAll('.critique-ligne')].find(x => x.dataset.groupe === g).click(), ligne18.g);
  await p.waitForTimeout(400);
  // À l'arrêt : sous « Terminé », aucun ; sous « En cours », tous.
  const arret18 = await p.evaluate(async () => {
    const somme = () => [...document.querySelectorAll('.critique-plans .arret-n')].reduce((t, e) => t + parseInt(e.textContent, 10), 0);
    const sousT = somme();
    document.querySelector('#filtre-valeur-groupe button[data-valeur-bloc="encours"]').click();
    return { sousT, sousE: somme(), attendu: window.__plansALArret().length };
  });
  verifier('bloc : « à l’arrêt » ne compte que les plans de la valeur — aucun sous « Terminé », tous sous « En cours »',
    arret18.sousT === 0 && arret18.sousE === arret18.attendu && arret18.attendu > 0, JSON.stringify(arret18));
  // La tuile d'une autre valeur l'emporte ; la même valeur garde le filtre.
  await p.click('#etats .etat-btn[data-cle="termine"]'); await p.waitForTimeout(400);
  const tuile18 = await p.evaluate(() => ({ bloc: window.__vueValeurs().bloc,
    actives: [...document.querySelectorAll('#filtre-valeur-groupe button:not([disabled])')].map(b => b.dataset.valeurBloc).join() }));
  verifier('bloc : cliquer la tuile d’une autre valeur ramène la rangée à « Tout » ; seules « Tout » et cette valeur restent (les autres ne sont plus dans la sélection)',
    tuile18.bloc === '' && tuile18.actives === ',termine', JSON.stringify(tuile18));
  await p.click('#filtre-valeur-groupe button[data-valeur-bloc="termine"]'); await p.waitForTimeout(300);
  await p.click('#etats .etat-btn[data-cle="termine"]'); await p.waitForTimeout(300);
  await p.click('#etats .etat-btn[data-cle="termine"]'); await p.waitForTimeout(300);
  verifier('bloc : la tuile de la même valeur garde le filtre du bloc',
    await p.evaluate(() => window.__vueValeurs().bloc === 'termine'));
  await p.click('#etats .etat-btn[data-cle="termine"]'); await p.waitForTimeout(300);
  // Vie de l'état : survit à la dimension, pas à la source ; jamais mémorisé.
  const dims18 = await p.evaluate(() => [...document.querySelectorAll('#dim-critique option')].map(o => o.value));
  const dimAvant18 = await p.evaluate(() => document.getElementById('dim-critique').value);
  await p.selectOption('#dim-critique', dims18.find(d => d !== dimAvant18));
  await p.waitForTimeout(400);
  const vie18 = await p.evaluate(() => ({ bloc: window.__vueValeurs().bloc, total: [...document.querySelectorAll('.critique-ligne .critique-total')].reduce((t, e) => t + Number(e.textContent), 0),
    tuile: Number(document.querySelector('#etats .etat-btn[data-cle="termine"] .etat-n').textContent.replace(/\s/g, '')),
    stocke: (() => { try { return localStorage.getItem('suivi-fwd:v1') || ''; } catch (e) { return ''; } })() }));
  verifier('bloc : le filtre survit au changement de dimension (ATA → autre), et les comptes font toujours la tuile',
    vie18.bloc === 'termine' && vie18.total === vie18.tuile, JSON.stringify([vie18.bloc, vie18.total, vie18.tuile]));
  verifier('bloc et graphique : rien de ces filtres n’est mémorisé', !/valeurBloc|valeurGraphe/.test(vie18.stocke));
  await p.selectOption('#dim-critique', dimAvant18); await p.waitForTimeout(300);
  // La recherche du bloc croise la valeur.
  const ref18 = await p.evaluate(() => {
    const t = [...document.querySelectorAll('#corps-tableau tr')];
    const i = [...document.querySelectorAll('tr.titres th')].findIndex(x => x.dataset.cle === 'reference');
    const j = [...document.querySelectorAll('tr.titres th')].findIndex(x => x.dataset.cle === 'avancement');
    const tr = t.find(r => /cours/i.test(r.children[j].textContent));
    return tr ? tr.children[i].textContent.trim() : null;
  });
  await p.fill('#filtre-groupe', ref18); await p.waitForTimeout(450);
  const rech18 = await p.evaluate(() => (document.querySelector('#zone-critique .vide-message') || { textContent: '' }).textContent.replace(/[  ]/g, ' '));
  verifier('bloc : sous « Terminé », chercher un plan « En cours » ne le trouve pas, et le message nomme la valeur',
    /^Ni groupe ni plan « Terminé » ne contient « /.test(rech18), rech18 + ' / ' + ref18);
  await p.fill('#filtre-groupe', ''); await p.waitForTimeout(400);
  // Deux valeurs d'une même famille : la barre par valeur les sépare.
  const famille18 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    let k = 0;
    s.plans.forEach(x => { if (window.__classer(x.avancement) === 'encours' && (k++ % 2)) x.avancement = 'PWD_TO_CONTROL'; });
    window.__chargerSource(s);
    const v = window.__valeurs().find(x => x.libelle === 'PWD_TO_CONTROL');
    const b = document.querySelector('#filtre-valeur-groupe button[data-valeur-bloc="' + v.cle + '"]');
    const cEnCours = getComputedStyle(document.querySelector('#filtre-valeur-groupe button[data-valeur-bloc="encours"] .pastille')).backgroundColor;
    const cPwd = getComputedStyle(b.querySelector('.pastille')).backgroundColor;
    b.click();
    const somme = [...document.querySelectorAll('.critique-ligne .critique-total')].reduce((t, e) => t + Number(e.textContent), 0);
    const eclaires = [...new Set([...document.querySelectorAll('.critique-barre span.eclaire')].map(e => e.dataset.cle))].join();
    return { n: v.n, somme, eclaires, cle: v.cle, couleursDistinctes: cEnCours !== cPwd, famille: v.famille };
  });
  verifier('bloc : deux valeurs « en cours » (En cours, PWD_TO_CONTROL) ont deux pilules de teintes distinctes ; filtrer l’une ne compte qu’elle',
    famille18.famille === 'encours' && famille18.couleursDistinctes && famille18.somme === famille18.n && famille18.eclaires === famille18.cle, JSON.stringify(famille18));
  // Le groupe « — » (plans sans valeur dans la dimension) : le choisir
  // donne au tableau et aux tuiles les mêmes plans que sa ligne du bloc.
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(300);
  const dimTiret18 = await p.evaluate(() => {
    const sel = document.getElementById('dim-critique');
    for (const o of [...sel.options]) {
      sel.value = o.value; sel.dispatchEvent(new Event('change', { bubbles: true }));
      if ([...document.querySelectorAll('.critique-ligne')].some(l => l.dataset.groupe === '\u2014')) return o.value;
    }
    return null;
  });
  if (dimTiret18) {
    const tiret18 = await p.evaluate(() => {
      const l = [...document.querySelectorAll('.critique-ligne')].find(x => x.dataset.groupe === '\u2014');
      const n = Number(l.querySelector('.critique-total').textContent);
      /* Débrief 27 (lot C) : « choisir » = déplier, puis filtrer la page sur lui. */
      l.click();
      document.getElementById('filtrer-groupe-page').click();
      return { n, tuiles: [...document.querySelectorAll('#etats .etat-n')].reduce((t, e) => t + Number(e.textContent.replace(/\s/g, '')), 0),
               lignes: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length };
    });
    verifier('bloc : choisir le groupe « — » (plans sans valeur) donne aux tuiles et au tableau ses plans, ni plus ni moins',
      tiret18.n > 0 && tiret18.tuiles === tiret18.n && tiret18.lignes === tiret18.n, JSON.stringify(tiret18));
  }
  // Le contrat change : tout repart à « Tout ».
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(400);
  verifier('bloc : une autre source ramène la rangée à « Tout »',
    await p.evaluate(() => window.__vueValeurs().bloc === '' && document.querySelector('#filtre-valeur-groupe button[data-valeur-bloc=""]').getAttribute('aria-pressed') === 'true'));
  await p.focus('#filtre-valeur-groupe button[data-valeur-bloc="afaire"]'); await p.keyboard.press('Enter'); await p.waitForTimeout(300);
  verifier('bloc : au clavier, Entrée choisit la pilule et le focus y reste',
    await p.evaluate(() => document.activeElement && document.activeElement.dataset.valeurBloc === 'afaire' && window.__vueValeurs().bloc === 'afaire'));
  await p.click('#filtre-valeur-groupe button[data-valeur-bloc=""]'); await p.waitForTimeout(300);

  // --- Le graphique.
  const g18 = await p.evaluate(() => {
    const z = document.getElementById('filtre-valeur-graphe');
    return { visible: !z.hidden, boutons: [...z.querySelectorAll('button')].map(b => b.dataset.valeurGraphe + ':' + b.querySelector('.libelle').textContent + ':' + b.getAttribute('aria-pressed')),
             projection: !!document.querySelector('#zone-graphe path[stroke-dasharray="5 4"]'), legende: document.getElementById('legende').textContent };
  });
  verifier('graphique : une rangée « Terminé » (la courbe des validés, pressée par défaut), puis les autres valeurs',
    g18.visible && g18.boutons.join('|') === ':Terminé:true|encours:En cours:false|afaire:À faire:false|vide:Non renseigné:false' && g18.projection && /réalisé/.test(g18.legende),
    JSON.stringify(g18));
  await p.click('#filtre-valeur-graphe button[data-valeur-graphe="encours"]'); await p.waitForTimeout(400);
  const gE = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const tries = s.releves.slice().sort((a, b) => a.semaine < b.semaine ? -1 : 1);
    const premier = Object.keys(tries[0].plans).filter(r => window.__classer(tries[0].plans[r]) === 'encours').length;
    const pts = window.__serieValeur('encours').pts;
    const courbe = document.querySelector('#zone-graphe path.courbe');
    return {
      note: document.getElementById('note-graphe').textContent.replace(/[  ]/g, ' '),
      legende: document.getElementById('legende').textContent.replace(/[  ]/g, ' '),
      items: document.querySelectorAll('#legende .legende-item').length,
      projection: !!document.querySelector('#zone-graphe path[stroke-dasharray="5 4"]'),
      aria: document.querySelector('#zone-graphe svg').getAttribute('aria-label'),
      couleur: courbe ? getComputedStyle(courbe).stroke : null,
      tuile: getComputedStyle(document.querySelector('#etats .etat-btn[data-cle="encours"] .pastille')).backgroundColor,
      premier, debut: pts[0].termine, fin: pts[pts.length - 1].termine,
      nTuile: Number(document.querySelector('#etats .etat-btn[data-cle="encours"] .etat-n').textContent.replace(/\s/g, '')),
      pertes: document.querySelectorAll('#zone-graphe .barre-semaine.perte').length,
      bande: [...document.querySelectorAll('#zone-graphe text')].some(t => /« En cours » : variation nette par semaine/.test(t.textContent))
    };
  });
  verifier('graphique sous « En cours » : la courbe compte ses plans relevé après relevé — du premier relevé au nombre de la tuile',
    gE.debut === gE.premier && gE.fin === gE.nTuile, JSON.stringify([gE.premier, gE.debut, gE.fin, gE.nTuile]));
  verifier('graphique : à la couleur de sa pastille, sans projection ni rythme requis, nommée dans la note, la légende et pour les lecteurs d’écran',
    gE.couleur === gE.tuile && !gE.projection && gE.items === 1 && /^Plans « En cours » · /.test(gE.note) &&
    /« En cours », relevé après relevé/.test(gE.legende) && /En cours/.test(gE.aria), JSON.stringify(gE));
  verifier('graphique : une valeur qui se vide a sa bande à deux sens — les baisses sous le trait',
    gE.bande && gE.pertes >= 1, JSON.stringify([gE.bande, gE.pertes]));
  const iBulle = await p.evaluate(() => { const pts = window.__serieValeur('encours').pts; return pts[pts.length - 2].i; });
  await p.hover('#zone-graphe .zone-clic[data-i="' + iBulle + '"]'); await p.waitForTimeout(300);
  const bulle18 = await p.evaluate(() => document.getElementById('bulle').textContent.replace(/[  ]/g, ' '));
  verifier('graphique : la bulle d’un relevé dit le nombre de la valeur et sa variation nette', /En cours\d/.test(bulle18) && /variation nette sur le relevé précédent/.test(bulle18), bulle18.slice(0, 160));
  await p.mouse.move(5, 5);
  // Sous un périmètre, la courbe de la valeur le suit.
  await p.click('#choix-perimetre button:has-text("PERSO")'); await p.waitForTimeout(600);
  const per18 = await p.evaluate(() => { const pts = window.__serieValeur('encours').pts;
    return { fin: pts[pts.length - 1].termine, tuile: Number(document.querySelector('#etats .etat-btn[data-cle="encours"] .etat-n').textContent.replace(/\s/g, '')), garde: window.__vueValeurs().graphe }; });
  verifier('graphique : sous le périmètre PERSO, la courbe « En cours » finit au nombre de sa tuile', per18.garde === 'encours' && per18.fin === per18.tuile, JSON.stringify(per18));
  await p.click('#choix-perimetre button:has-text("Tout")'); await p.waitForTimeout(600);
  // Un groupe choisi dans le bloc : la courbe de la valeur ne compte que lui.
  await p.click('#filtre-valeur-groupe button[data-valeur-bloc="encours"]'); await p.waitForTimeout(300);
  const ligneG18 = await p.evaluate(() => { const l = document.querySelector('.critique-ligne'); return { g: l.dataset.groupe, n: Number(l.querySelector('.critique-total').textContent) }; });
  // Débrief 27 (lot C) : « choisi » = la page filtrée sur lui, par le bouton de sa liste dépliée.
  await p.click('.critique-ligne >> nth=0'); await p.waitForTimeout(400);
  await p.click('#filtrer-groupe-page'); await p.waitForTimeout(500);
  const grp18 = await p.evaluate(() => { const pts = window.__serieValeur('encours').pts; return pts[pts.length - 1].termine; });
  verifier('graphique : un groupe choisi dans le bloc — la courbe « En cours » finit à son compte dans le bloc', grp18 === ligneG18.n, JSON.stringify([grp18, ligneG18]));
  await p.click('#filtrer-groupe-page'); await p.waitForTimeout(400);
  await p.click('.critique-ligne >> nth=0'); await p.waitForTimeout(400);
  await p.click('#filtre-valeur-groupe button[data-valeur-bloc=""]'); await p.waitForTimeout(300);
  await p.focus('#filtre-valeur-graphe button[data-valeur-graphe="afaire"]'); await p.keyboard.press('Enter'); await p.waitForTimeout(300);
  verifier('graphique : au clavier, Entrée choisit la pilule et le focus y reste',
    await p.evaluate(() => document.activeElement && document.activeElement.dataset.valeurGraphe === 'afaire' && window.__vueValeurs().graphe === 'afaire'));
  await p.click('#filtre-valeur-graphe button[data-valeur-graphe=""]'); await p.waitForTimeout(400);
  const retour18 = await p.evaluate(() => ({ projection: !!document.querySelector('#zone-graphe path[stroke-dasharray="5 4"]'),
    legende: document.getElementById('legende').textContent, graphe: window.__vueValeurs().graphe }));
  verifier('graphique : « Terminé » rend la courbe des validés, sa projection et sa légende',
    retour18.projection && /réalisé/.test(retour18.legende) && retour18.graphe === '', JSON.stringify(retour18));
  // Un relevé archivé sans carte plan par plan : hors de la courbe d'une valeur, et la bulle le dit.
  const sansCarte18 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const tries = s.releves.slice().sort((a, b) => a.semaine < b.semaine ? -1 : 1);
    const trou = tries[tries.length - 4];
    delete trou.plans; delete trou.plansConcept;
    window.__chargerSource(s);
    document.querySelector('#filtre-valeur-graphe button[data-valeur-graphe="encours"]').click();
    const pts = window.__serieValeur('encours').pts;
    const iTrou = [...document.querySelectorAll('#zone-graphe .zone-clic')].map(z => Number(z.dataset.i)).filter(i => !pts.some(pt => pt.i === i))
      .find(i => /hors de cette courbe/.test(document.querySelector('#zone-graphe .zone-clic[data-i="' + i + '"]').getAttribute('aria-label')));
    const apres = pts.find(pt => pt.i > iTrou);
    return { iTrou, apres: apres ? apres.i : null, note: document.getElementById('note-graphe').textContent };
  });
  verifier('graphique : un relevé sans carte est dit « hors de cette courbe » (note et lecteur d’écran)',
    sansCarte18.iTrou !== undefined && /1 relevé sans détail plan par plan, hors de cette courbe/.test(sansCarte18.note), JSON.stringify(sansCarte18));
  if (sansCarte18.iTrou !== undefined) {
    await p.hover('#zone-graphe .zone-clic[data-i="' + sansCarte18.iTrou + '"]'); await p.waitForTimeout(250);
    const bTrou = await p.evaluate(() => document.getElementById('bulle').textContent);
    await p.hover('#zone-graphe .zone-clic[data-i="' + sansCarte18.apres + '"]'); await p.waitForTimeout(250);
    const bApres = await p.evaluate(() => document.getElementById('bulle').textContent.replace(/[\u00a0\u202f]/g, ' '));
    verifier('graphique : sa bulle dit « sans détail plan par plan », et le relevé suivant dit sa variation « depuis le relevé de S… »',
      /Relevé sans détail plan par plan : hors de cette courbe/.test(bTrou) && /variation nette depuis le relevé de S\d/.test(bApres), JSON.stringify([bTrou, bApres.slice(0, 160)]));
    await p.mouse.move(5, 5);
  }
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(300);
  // Plusieurs valeurs « validé » : un premier bouton « Validés ».
  const deuxFinies = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    let k = 0;
    s.plans.forEach(x => { if (window.__classer(x.avancement) === 'termine' && (k++ % 3 === 0)) x.avancement = 'Validé'; });
    window.__chargerSource(s);
    const r = [...document.querySelectorAll('#filtre-valeur-graphe button')].map(b => b.dataset.valeurGraphe + ':' + b.querySelector('.libelle').textContent);
    window.__chargerSource(window.__jeuDExemple('HDK'));
    return r;
  });
  verifier('graphique : deux valeurs veulent dire « validé » — un premier bouton « Validés », puis chacune à part',
    deuxFinies[0] === ':Validés' && deuxFinies.filter(x => /^termine:|^valide:/.test(x)).length === 2, JSON.stringify(deuxFinies));
  // Le concept : la rangée du graphique repart des valeurs du concept, sur « Validés »/« Traité ».
  await p.click('#filtre-valeur-graphe button[data-valeur-graphe="encours"]'); await p.waitForTimeout(300);
  await p.evaluate(() => { const b = document.querySelector('#choix-indicateur button[data-indicateur="concept"]'); if (b) b.click(); });
  await p.waitForTimeout(400);
  verifier('graphique : passer au concept harnais ramène la courbe par défaut',
    await p.evaluate(() => window.__vueValeurs().graphe === ''));
  await p.evaluate(() => { const b = document.querySelector('#choix-indicateur button[data-indicateur="def"]'); if (b) b.click(); });
  await p.waitForTimeout(400);
  await reinitialiser(p);

  // =================================================================
  /* Débrief 19 : « homogène à la ligne » — dans chaque section, une seule
     ligne : les pastilles à gauche, la recherche au bout à droite ; seulement
     les valeurs qu'il y a, au concept comme à la définition ; les sept
     tuiles de GATES sur une ligne ; plus d'alerte au concept harnais. */
  section('Débrief 19 : une ligne par section, seulement ce qu’il y a, tuiles sur une ligne');
  await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); window.scrollTo(0, 0); });
  await p.waitForTimeout(600);
  const ligne19 = () => p.evaluate(() => {
    const lire = id => {
      const r = document.getElementById(id), l = r.closest('.ligne-filtres') || r, rech = l.querySelector('.recherche-groupe');
      const rr = r.getBoundingClientRect(), lr = l.getBoundingClientRect();
      const o = { visible: !r.hidden && rr.height > 0, rangs: new Set([...r.querySelectorAll('button')].map(b => Math.round(b.getBoundingClientRect().top))).size,
                  gauche: Math.round(rr.left - lr.left), fondu: r.classList.contains('deborde-droite'),
                  deborde: r.scrollWidth - r.clientWidth - r.scrollLeft > 2 };
      if (rech && rech !== r) {
        const sr = rech.getBoundingClientRect();
        Object.assign(o, { droite: Math.round(lr.right - sr.right), centres: Math.round(Math.abs((sr.top + sr.bottom) / 2 - (rr.top + rr.bottom) / 2)),
                           chevauche: rr.right > sr.left + 1, hauteur: Math.round(lr.height) });
        /* Débrief 27 (lot B) : les pastilles hors de leur cadre (cachées
           sous le bord), et où tombe la recherche par rapport à la première
           ligne de pastilles. */
        const prem = r.querySelector('.puces-rang button') || r.querySelector('button');
        Object.assign(o, { caches: [...r.querySelectorAll('button')].filter(b => { const x = b.getBoundingClientRect(); return x.right > rr.right + 1 || x.left < rr.left - 1 || x.width < 2; }).length,
                           premiereLigne: !!prem && Math.abs(sr.top - prem.getBoundingClientRect().top) <= 6, dessous: sr.top >= rr.bottom - 1,
                           titres: [...r.querySelectorAll('.mot-rang')].map(m => m.textContent).join() });
      }
      return o;
    };
    return { journal: lire('filtre-journal'), bloc: lire('filtre-valeur-groupe'), graphe: lire('filtre-valeur-graphe'),
             page: document.documentElement.scrollWidth <= window.innerWidth };
  });
  const bienAligne19 = o => o.visible && o.rangs === 1 && o.gauche <= 2 && o.droite <= 1 && o.centres <= 3 && !o.chevauche && o.hauteur <= 52 && o.fondu === o.deborde;
  /* Débrief 27 (lot B, P-F3, X-A3) : la rangée du journal ne défile plus
     sous un fondu (« Reculs » y était caché) : ses pastilles passent à la
     ligne, en deux rangées titrées, « Passés à » et « Mouvements » ; la
     recherche reste au bout de la première ligne, et passe dessous sous
     1 180 px. Aucune pastille hors du cadre, aucun fondu. */
  const journalRange27 = (o, w, souple) => o.visible && o.gauche <= 2 && o.droite <= 1 && !o.deborde && !o.fondu && o.caches === 0 &&
    (souple ? /^(Passés à,Mouvements|Passés à|Mouvements)$/ : /^Passés à,Mouvements$/).test(o.titres) && (w >= 1180 ? o.premiereLigne && !o.chevauche : o.dessous);
  for (const w of [1440, 1280, 1024]) {
    await redimensionner(p, w, 950);
    const l = await ligne19();
    verifier('à ' + w + ' px, journal : les pastilles à gauche, en deux rangées titrées qui passent à la ligne — aucune cachée —, « Chercher un plan » au bout à droite' + (w >= 1180 ? ', sur la première ligne' : ', dessous'),
      journalRange27(l.journal, w), JSON.stringify(l.journal));
    verifier('à ' + w + ' px, bloc par groupe : la même ligne — pastilles à gauche, compte et recherche à droite',
      bienAligne19(l.bloc), JSON.stringify(l.bloc));
    verifier('à ' + w + ' px, graphique : les pilules sur une seule ligne, sans débord de la page',
      l.graphe.visible && l.graphe.rangs === 1 && l.graphe.fondu === l.graphe.deborde && l.page, JSON.stringify(l.graphe));
  }
  /* Une ligne trop longue défilait, avec un fondu au bord droit. Débrief 27
     (lot B) : à 800 px aussi, les pastilles du journal passent à la ligne —
     toutes en vue, sans fondu ni défilement. */
  await redimensionner(p, 800, 950);
  const fondu19 = await p.evaluate(async () => {
    const r = document.getElementById('filtre-journal'), rr = r.getBoundingClientRect();
    return { deborde: r.scrollWidth > r.clientWidth + 2, fondu: r.classList.contains('deborde-droite'),
             caches: [...r.querySelectorAll('button')].filter(b => { const x = b.getBoundingClientRect(); return x.right > rr.right + 1 || x.width < 2; }).length,
             page: document.documentElement.scrollWidth <= window.innerWidth };
  });
  verifier('à 800 px, les pastilles du journal passent à la ligne : toutes en vue, ni fondu ni défilement',
    !fondu19.deborde && !fondu19.fondu && fondu19.caches === 0 && fondu19.page, JSON.stringify(fondu19));
  await redimensionner(p, 1280, 950);

  // Seulement les valeurs qu'il y a — à la définition comme au concept, dans les trois rangées.
  const rangees19 = () => p.evaluate(() => {
    const vals = window.__valeurs();
    const finies = vals.filter(v => v.famille === 'termine'), seule = finies.length === 1 ? finies[0].cle : null;
    const evts = [].concat(...window.__journalAffiche().map(s => s.evenements));
    const arrivees = new Set(evts.filter(e => (e.type === 'change' || e.type === 'indice') && e.cApres && e.cApres !== e.cAvant).map(e => e.cApres));
    const cles = (id, a) => [...document.querySelectorAll('#' + id + ' button')].map(b => b.getAttribute('data-' + a)).filter(Boolean);
    const max = k => Math.max(0, ...window.__serieValeur(k).pts.map(x => x.termine));
    const j = cles('filtre-journal', 'journal').filter(k => ['reculs', 'indice', 'nouveaux', 'disparus'].indexOf(k) === -1), b = cles('filtre-valeur-groupe', 'valeur-bloc'),
          g = cles('filtre-valeur-graphe', 'valeur-graphe');
    return { indicateur: document.querySelector('#choix-indicateur button[aria-pressed="true"]') ? document.querySelector('#choix-indicateur button[aria-pressed="true"]').dataset.indicateur : '',
      journal: j.every(k => arrivees.has(k)) && [...arrivees].every(k => j.indexOf(k) !== -1),
      bloc: b.join() === vals.filter(v => v.n > 0).map(v => v.cle).join(),
      graphe: g.every(k => max(k) > 0) && vals.filter(v => v.cle !== seule && max(v.cle) > 0).every(v => g.indexOf(v.cle) !== -1),
      grises: document.querySelectorAll('#filtre-journal button:disabled, #filtre-valeur-groupe button:disabled, #filtre-valeur-graphe button:disabled').length,
      detail: { j, b, g, vals: vals.map(v => v.cle + '=' + v.n) } };
  });
  const def19 = await rangees19();
  verifier('définition : journal, bloc et graphique n’ont que les valeurs qu’il y a, aucune grisée',
    def19.journal && def19.bloc && def19.graphe && def19.grises === 0, JSON.stringify(def19));
  const aConcept19 = await p.evaluate(() => !document.getElementById('choix-indicateur').hidden);
  if (aConcept19) {
    await p.click('#choix-indicateur button[data-indicateur="concept"]'); await p.waitForTimeout(700);
    const con19 = await rangees19();
    verifier('concept harnais : exactement pareil — journal, bloc et graphique n’ont que ses valeurs à lui qu’il y a, aucune grisée',
      con19.indicateur === 'concept' && con19.journal && con19.bloc && con19.graphe && con19.grises === 0, JSON.stringify(con19));
    const lc19 = await ligne19();
    verifier('concept harnais : la même ligne qu’à la définition — pastilles à gauche, recherche à droite',
      journalRange27(lc19.journal, 1280, true) && bienAligne19(lc19.bloc), JSON.stringify(lc19));
    await p.click('#choix-indicateur button[data-indicateur="def"]'); await p.waitForTimeout(700);
  } else verifier('la démonstration a un concept harnais', false);

  // Une seule valeur portée par les plans : « Tout » et elle, rien d'autre.
  const seule19 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const fini = s.plans.map(x => x.avancement).find(v => window.__classer(v) === 'termine');
    s.plans.forEach(x => { x.avancement = fini; });
    window.__chargerSource(s);
    return { bloc: [...document.querySelectorAll('#filtre-valeur-groupe button')].map(b => b.dataset.valeurBloc).join(),
             attendu: ['', ...window.__valeurs().map(v => v.cle)].join(), n: window.__valeurs().length };
  });
  verifier('des plans tous validés : le bloc n’a que « Tout » et la pastille validée',
    seule19.n === 1 && seule19.bloc === seule19.attendu, JSON.stringify(seule19));

  // Les sept valeurs de GATES : sept tuiles sur une ligne, aucun libellé coupé, de 1024 px à la pleine largeur.
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const vals = ['VALIDATED', 'TO_CONFIRM', 'PWD_TO_CONTROL', 'PWD_IN_PROGRESS', 'FWD_TO_SEIZE', 'TO_TREAT', ''];
    const poids = [54, 4, 6, 238, 3, 1, 334];
    s.plans.forEach((pl, i) => { let c = 0, j = 0; while (j < poids.length - 1 && i >= c + poids[j]) { c += poids[j]; j++; } pl.avancement = vals[j]; });
    window.__chargerSource(s);
  });
  for (const w of [1440, 1280, 1024]) {
    await redimensionner(p, w, 950);
    const t = await p.evaluate(() => {
      const bs = [...document.querySelectorAll('#etats .etat-btn')];
      return { n: bs.length, rangs: new Set(bs.map(b => Math.round(b.getBoundingClientRect().top))).size,
               coupes: bs.filter(b => { const l = b.querySelector('.libelle'); return l.scrollWidth > l.clientWidth + 1; }).map(b => b.querySelector('.libelle').textContent),
               parRang: Object.values(bs.reduce((m, b) => { const y = Math.round(b.getBoundingClientRect().top); m[y] = (m[y] || 0) + 1; return m; }, {})),
               points: bs.some(b => getComputedStyle(b.querySelector('.libelle')).textOverflow === 'ellipsis'),
               page: document.documentElement.scrollWidth <= window.innerWidth };
    });
    /* Dès 1280 px, sept tuiles sur une ligne. Débrief 27 (B10, D7) : plus
       étroit, plus de nom abrégé « entier au survol » (PWD_IN_PR… à 1024 px) —
       les tuiles passent en rangées équilibrées (4 + 3), et un code GATES
       n'est jamais coupé, à aucune largeur. */
    verifier('à ' + w + ' px, les sept valeurs de GATES : ' + (w >= 1280 ? 'sept tuiles sur une seule ligne' : 'deux rangées équilibrées (4 + 3)') + ', aucun libellé coupé, sans débord de la page',
      t.n === 7 && (w >= 1280 ? t.rangs === 1 : t.parRang.join() === '4,3') && !t.coupes.length && !t.points && t.page, JSON.stringify(t));
  }
  await redimensionner(p, 1280, 950);

  // Relecture 19 : les trois rangées ont le même pas, l'anneau du focus n'est pas rogné, pas de barre de défilement.
  const style19 = await p.evaluate(() => ['filtre-journal', 'filtre-valeur-groupe', 'filtre-valeur-graphe'].map(id => {
    const c = getComputedStyle(document.getElementById(id));
    return id + ':' + c.columnGap + '/' + c.paddingTop + '/' + c.scrollbarWidth + '/' + c.overflowY;
  }));
  /* Débrief 27 : la rangée du journal ne défile plus — rien à rogner,
     l'anneau du focus a toute sa place (lot B) ; au large, les pastilles du
     bloc par groupe passent à la ligne au lieu de défiler sous un fondu
     (lot C, X-A3) ; celles du graphique, inchangées. */
  const styleJ27 = await p.evaluate(() => { const r = document.getElementById('filtre-journal'), g = r.querySelector('.puces-rang');
    return { x: getComputedStyle(r).overflowX, y: getComputedStyle(r).overflowY, ecart: g ? getComputedStyle(g).columnGap : null }; });
  verifier('les trois rangées : le même écart entre pastilles, 4 px autour pour l’anneau du focus (le journal et le bloc par groupe : rien de rogné), sans barre de défilement',
    style19.filter(x => !/^filtre-journal:/.test(x)).every(x => { const id = x.split(':')[0]; return (id === 'filtre-valeur-groupe' ? /^:4px\/4px\/none\/visible$/ : /^:4px\/4px\/none\/hidden$/).test(x.slice(id.length)); }) &&
    styleJ27.x === 'visible' && styleJ27.y === 'visible' && styleJ27.ecart === '4px', JSON.stringify([style19, styleJ27]));

  // Une valeur que seul PERSO porte : sous BASE/OPTION, ni tuile, ni pastille au bloc, ni pilule au graphique ; pressée, sa tuile reste.
  const perso19 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    let k = 0;
    s.plans.forEach(x => { if (k < 6 && window.__domaineDe(x.reference) === 'PERSO') { x.avancement = 'Seulement perso'; k++; } });
    window.__chargerSource(s);
    const v = window.__valeurs().find(x => x.libelle === 'Seulement perso');
    const lire = () => ({ tuile: !!document.querySelector('#etats .etat-btn[data-cle="' + v.cle + '"]'),
      bloc: !!document.querySelector('#filtre-valeur-groupe button[data-valeur-bloc="' + v.cle + '"]'),
      graphe: !!document.querySelector('#filtre-valeur-graphe button[data-valeur-graphe="' + v.cle + '"]') });
    const tout = lire();
    [...document.querySelectorAll('#choix-perimetre button')].find(b => /BASE/.test(b.textContent)).click();
    const base = lire();
    [...document.querySelectorAll('#choix-perimetre button')].find(b => /^Tout/.test(b.textContent.trim())).click();
    document.querySelector('#etats .etat-btn[data-cle="' + v.cle + '"]').click();
    [...document.querySelectorAll('#choix-perimetre button')].find(b => /BASE/.test(b.textContent)).click();
    const presse = lire();
    const etat = document.querySelector('#etats .etat-btn[aria-pressed="true"]');
    if (etat) etat.click();
    [...document.querySelectorAll('#choix-perimetre button')].find(b => /^Tout/.test(b.textContent.trim())).click();
    return { n: k, tout, base, presse };
  });
  verifier('une valeur que seul PERSO porte : tuile, pastille du bloc et pilule du graphique sous Tout, aucune sous BASE/OPTION — pressée, sa tuile reste',
    perso19.n === 6 && perso19.tout.tuile && perso19.tout.bloc && perso19.tout.graphe && !perso19.base.tuile && !perso19.base.bloc && !perso19.base.graphe &&
    perso19.presse.tuile, JSON.stringify(perso19));
  await reinitialiser(p);

  // La rangée du bloc suit son champ « ATA ou plan… », comme celle du journal suit le sien.
  const sBloc19 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    window.__chargerSource(s);
    const pl = s.plans.filter(x => x.avancement)[7];
    const v = window.__valeurs().find(x => x.libelle === pl.avancement);
    return { ref: pl.reference, cle: v && v.cle };
  });
  await p.fill('#filtre-groupe', sBloc19.ref); await p.waitForTimeout(500);
  const blocCherche19 = await p.evaluate(() => [...document.querySelectorAll('#filtre-valeur-groupe button')].map(b => b.dataset.valeurBloc));
  await p.focus('#filtre-groupe'); await p.keyboard.press('Escape'); await p.waitForTimeout(500);
  const blocApres19 = await p.evaluate(() => [...document.querySelectorAll('#filtre-valeur-groupe button')].length);
  verifier('bloc : sous « ATA ou plan… » = une référence, la rangée n’a que « Tout » et la valeur de ce plan ; Échap la rend entière',
    blocCherche19.join() === ['', sBloc19.cle].join() && blocApres19 > 2, JSON.stringify([sBloc19, blocCherche19, blocApres19]));

  // Le fondu du bloc se remesure quand le compte « n sur m » paraît et s'en va (les sept valeurs de GATES).
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const vals = ['VALIDATED', 'TO_CONFIRM', 'PWD_TO_CONTROL', 'PWD_IN_PROGRESS', 'FWD_TO_SEIZE', 'TO_TREAT', ''];
    s.plans.forEach((pl, i) => { pl.avancement = vals[i % vals.length]; });
    window.__chargerSource(s);
  });
  const fonduBloc19 = [];
  for (const w of [1100, 1280]) {
    await redimensionner(p, w, 950);
    const lire = () => p.evaluate(() => { const r = document.getElementById('filtre-valeur-groupe');
      return { fondu: r.classList.contains('deborde-droite'), deborde: r.scrollWidth - r.clientWidth - r.scrollLeft > 2, compte: document.getElementById('compte-groupes').textContent }; });
    await p.fill('#filtre-groupe', '2'); await p.waitForTimeout(500);
    const tape = await lire();
    await p.focus('#filtre-groupe'); await p.keyboard.press('Escape'); await p.waitForTimeout(500);
    const vide = await lire();
    fonduBloc19.push({ w, tape, vide });
  }
  await redimensionner(p, 1280, 950);
  verifier('bloc : le fondu de la rangée suit le compte « n sur m » qui paraît et s’en va — jamais un fondu sans débord, jamais un débord sans fondu',
    fonduBloc19.every(x => !!x.tape.compte && x.tape.fondu === x.tape.deborde && !x.vide.compte && x.vide.fondu === x.vide.deborde), JSON.stringify(fonduBloc19));

  /* Le concept harnais avant son premier « Traité » (le cas réel de
     Nathan) : pas de pilule « Validés » pour une valeur que personne ne
     porte ; un second clic sur la pilule pressée ramène la courbe des
     validés. Et un « Traité » que seuls des relevés d'avant portent tient
     la pilule par défaut, une seule fois. */
  const concept19 = await p.evaluate(() => {
    const cles = id => [...document.querySelectorAll('#' + id + ' button')].map(b => b.getAttribute('data-' + (id === 'filtre-valeur-graphe' ? 'valeur-graphe' : id === 'filtre-valeur-groupe' ? 'valeur-bloc' : 'journal')) + ':' + b.querySelector('.libelle').textContent);
    const sansTraite = (s, aussiReleves) => {
      const c = s.cleConcept;
      s.plans.forEach(x => { if (window.__classer(x[c]) === 'termine') x[c] = 'À traiter'; });
      if (aussiReleves) s.releves.forEach(r => { if (r.plansConcept) Object.keys(r.plansConcept).forEach(k => { if (window.__classer(r.plansConcept[k]) === 'termine') r.plansConcept[k] = 'À traiter'; }); });
      return s;
    };
    const out = {};
    window.__chargerSource(sansTraite(window.__jeuDExemple('HDK'), true));
    document.querySelector('#choix-indicateur button[data-indicateur="concept"]').click();
    out.graphe = cles('filtre-valeur-graphe'); out.bloc = cles('filtre-valeur-groupe');
    out.tuiles = [...document.querySelectorAll('#etats .etat-btn .libelle')].map(x => x.textContent);
    out.alerte = !document.getElementById('alerte-valeurs').hidden;
    const b = document.querySelector('#filtre-valeur-graphe button');
    if (b) { b.click(); out.apres1 = window.__vueValeurs().graphe; document.querySelector('#filtre-valeur-graphe button[aria-pressed="true"]').click(); out.apres2 = window.__vueValeurs().graphe; }
    document.querySelector('#choix-indicateur button[data-indicateur="def"]').click();
    window.__chargerSource(sansTraite(window.__jeuDExemple('HDK'), false));
    document.querySelector('#choix-indicateur button[data-indicateur="concept"]').click();
    out.hier = cles('filtre-valeur-graphe');
    out.hierFinies = out.hier.filter(x => window.__classer(x.split(':')[1]) === 'termine' || /:Validés$/.test(x));
    document.querySelector('#choix-indicateur button[data-indicateur="def"]').click();
    window.__chargerSource(window.__jeuDExemple('HDK'));
    return out;
  });
  verifier('concept harnais sans « Traité » : le graphique n’a que les pilules de ce qu’il y a — pas de « Validés » —, comme les tuiles et le bloc, sans alerte',
    concept19.graphe.length > 0 && concept19.graphe.every(x => !/^:|:Validés$/.test(x)) && !concept19.alerte &&
    concept19.bloc.slice(1).map(x => x.split(':')[1]).every(l => concept19.tuiles.indexOf(l) !== -1), JSON.stringify(concept19));
  verifier('concept harnais sans « Traité » : une pilule pressée montre sa courbe, un second clic ramène celle des validés',
    !!concept19.apres1 && concept19.apres2 === '', JSON.stringify(concept19));
  verifier('une valeur « validé » que seuls les relevés d’avant portent : elle ouvre la rangée comme courbe par défaut, une seule fois, sans « Validés »',
    /^:/.test(concept19.hier[0] || '') && concept19.hierFinies.length === 1 && concept19.hierFinies[0] === concept19.hier[0], JSON.stringify(concept19.hier));

  // Un journal vide après un journal en grille : son message n'est pas coupé au bord de la carte.
  const vide19 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const carte = {}; s.plans.forEach(x => { carte[x.reference] = x[s.cleConcept]; });
    s.releves.forEach(r => { r.plansConcept = Object.assign({}, carte); });
    window.__chargerSource(s);
    const avant = document.getElementById('zone-journal').classList.contains('journal-grille');
    document.querySelector('#choix-indicateur button[data-indicateur="concept"]').click();
    const z = document.getElementById('zone-journal'), m = z.querySelector('.journal-vide');
    const r = { avant, grille: z.classList.contains('journal-grille'), message: !!m,
                dedans: !!m && m.getBoundingClientRect().right <= z.getBoundingClientRect().right + 1 && z.scrollWidth <= z.clientWidth + 1 };
    document.querySelector('#choix-indicateur button[data-indicateur="def"]').click();
    window.__chargerSource(window.__jeuDExemple('HDK'));
    return r;
  });
  verifier('un journal vide après un journal en grille : le message tient dans la carte',
    vide19.avant && !vide19.grille && vide19.message && vide19.dedans, JSON.stringify(vide19));

  // L'ancien cadrage gardé par la livraison d'avant ({ fen, cadrage: 4 }) n'est plus repris : la page s'ouvre sur « Échéances ».
  const ctxCadrage = await contexte();
  const pCadrage = await ctxCadrage.newPage();
  brancher(pCadrage, 'ancien cadrage');
  await pCadrage.addInitScript(() => {
    try { localStorage.setItem('suivi-fwd:v1', JSON.stringify({ fen: { debut: -400, span: 5000 }, cadrage: 4 })); } catch (e) { /* sans stockage, rien à reprendre */ }
  });
  await pCadrage.goto(URL); await pCadrage.waitForTimeout(1300);
  const ancienCadrage = await pCadrage.evaluate(() => [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')].map(x => x.textContent).join());
  verifier('l’ancien cadrage « Tout » gardé dans le navigateur (livraison d’avant) n’est plus repris : la page s’ouvre sur « Échéances »',
    ancienCadrage === 'Échéances', ancienCadrage);
  await ctxCadrage.close();
  await reinitialiser(p);

  // Plus d'alerte « aucun plan compté validé » au concept harnais, ni sur des plans tous « à faire ».
  const alerte19 = await p.evaluate(() => {
    const cachee = () => document.getElementById('alerte-valeurs').hidden;
    const out = {};
    const s1 = window.__jeuDExemple('HDK');
    s1.plans.forEach(x => { if (window.__classer(x[s1.cleConcept]) === 'termine') x[s1.cleConcept] = 'À traiter'; });
    window.__chargerSource(s1);
    const b = document.querySelector('#choix-indicateur button[data-indicateur="concept"]');
    if (b) b.click();
    out.concept = { cachee: cachee(), finies: window.__valeurs().filter(v => v.famille === 'termine').length,
                    texte: document.getElementById('alerte-valeurs').textContent.slice(0, 120) };
    document.querySelector('#choix-indicateur button[data-indicateur="def"]').click();
    const s2 = window.__jeuDExemple('HDK');
    s2.plans.forEach((x, i) => { x.avancement = i % 3 ? 'Pas commencé' : ''; });
    window.__chargerSource(s2);
    out.afaire = { cachee: cachee(), familles: [...new Set(window.__valeurs().map(v => v.famille))].join() };
    window.__chargerSource(window.__jeuDExemple('HDK'));
    return out;
  });
  verifier('concept harnais sans aucun « Traité » : pas d’alerte « Aucun plan n’est compté validé »',
    alerte19.concept.cachee && alerte19.concept.finies === 0, JSON.stringify(alerte19.concept));
  verifier('définition aux plans tous « à faire » ou vides : pas d’alerte non plus (seul un mot inconnu rangé « en cours » la déclenche)',
    alerte19.afaire.cachee && !/termine|encours/.test(alerte19.afaire.familles), JSON.stringify(alerte19.afaire));
  await p.waitForTimeout(400);
  await reinitialiser(p);

  section('Débrief 20 : des sections qu’on repère');
  {
    /* « Ça fait trop fil d'actualité, on n'arrive pas à bien les repérer » :
       chaque panneau a sa teinte (numéro, amorce du filet, mot à choisir),
       un sommaire collé en haut y mène. On vérifie aussi trois défauts de
       mise en page relevés par la chasse aux bugs, et le panneau du
       classeur vide réécrit pour la fenêtre d'import. */
    const lireTeintes = pg => pg.evaluate(() => {
      function lum(c) {
        const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => {
          v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
      }
      const contraste = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
      const papier = getComputedStyle(document.body).backgroundColor;
      const panneaux = ['section-synthese', 'section-tendance', 'section-journal', 'section-repartition', 'section-plans', 'rapprochement'].map(id => {
        const sec = document.getElementById(id);
        const sur = sec.querySelector('.surtitre');
        const num = getComputedStyle(sur, '::before');
        return { id, numero: num.color, fond: getComputedStyle(sec).backgroundColor,
                 titre: getComputedStyle(sec.querySelector('h2, .phrase')).color,
                 contrasteSurface: contraste(num.color, getComputedStyle(sec).backgroundColor),
                 contrastePapier: contraste(num.color, papier) };
      });
      const sel = document.getElementById('dim-critique');
      const liens = [...document.querySelectorAll('#sommaire-liste li:not([hidden]) a')].map(a => ({
        texte: a.textContent.trim(), numero: getComputedStyle(a, '::before').color, cible: a.dataset.chapitre }));
      return { panneaux, mot: getComputedStyle(sel).color, liens, encre: getComputedStyle(document.body).color,
               dim: sel.options[sel.selectedIndex].text.replace(/ \(.*\)$/, ''),
               surface: getComputedStyle(document.getElementById('section-plans')).backgroundColor };
    });
    await p.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); window.scrollTo(0, 0); });
    await redimensionner(p, 1280, 950);
    const t = await lireTeintes(p);
    const nums = t.panneaux.map(x => x.numero);
    verifier('chaque panneau porte sa teinte sur son numéro : six couleurs différentes (le journal a la sienne depuis le débrief 21), la synthèse à l’encre',
      new Set(nums).size === 6 && nums[0] === t.encre, JSON.stringify(nums));
    verifier('teintes calmes : aucun titre coloré — les panneaux restent blancs (seule leur tête est teintée, débrief 21), les titres à l’encre',
      t.panneaux.every(x => x.fond === t.surface && x.titre === t.encre), JSON.stringify(t.panneaux.map(x => [x.fond, x.titre])));
    verifier('thème clair : chaque numéro se lit (au moins 4,5:1 sur le panneau et sur le papier)',
      t.panneaux.every(x => x.contrasteSurface >= 4.5 && x.contrastePapier >= 4.5),
      JSON.stringify(t.panneaux.map(x => x.contrasteSurface.toFixed(2) + '/' + x.contrastePapier.toFixed(2))));
    verifier('« par [ATA ▾] » : le mot à choisir est dans la teinte du panneau 04', t.mot === t.panneaux[3].numero, t.mot);
    verifier('le sommaire liste les six panneaux, chacun dans la teinte de son panneau, dans le même ordre',
      t.liens.length === 6 && t.liens.every((l, k) => l.cible === t.panneaux[k].id && l.numero === t.panneaux[k].numero) &&
      t.liens[0].texte === 'Synthèse' && t.liens[2].texte === 'Changements' && t.liens[3].texte === 'Par ' + t.dim && t.liens[5].texte === 'Comparaison', JSON.stringify([t.dim, t.liens]));
    const ctxS = await contexte({ colorScheme: 'dark' });
    const ps20 = await page(ctxS, 'teintes sombres');
    const ts = await lireTeintes(ps20);
    verifier('thème sombre : d’autres valeurs des mêmes teintes, toujours distinctes et lisibles (4,5:1)',
      new Set(ts.panneaux.map(x => x.numero)).size === 6 && ts.panneaux.every((x, k) => x.numero !== nums[k]) &&
      ts.panneaux.every(x => x.contrasteSurface >= 4.5 && x.contrastePapier >= 4.5) && ts.mot === ts.panneaux[3].numero,
      JSON.stringify(ts.panneaux.map(x => x.numero + ' ' + x.contrasteSurface.toFixed(2))));
    await ctxS.close();

    // --- Le sommaire : hors du bandeau du titre, collé en haut, le panneau courant marqué.
    const tete = await p.evaluate(() => ({
      /* Débrief 27 (lot H) : le titre avait son surtitre (le contrat) et sa
         ligne de fraîcheur — quatre lignes. Débrief 28 : ni surtitre ni
         fraîcheur — le titre et la semaine, deux lignes, toujours sans le
         sommaire. */
      horsTitre: !document.querySelector('.masthead .sommaire') && document.querySelector('.masthead').children.length === 2 &&
        document.querySelector('.masthead').children[0].id === 'titre-page' && document.querySelector('.masthead').children[1].classList.contains('semaine'),
      sousTitre: document.getElementById('sommaire').getBoundingClientRect().top >= document.querySelector('.masthead').getBoundingClientRect().bottom - 12,
      avantPanneaux: document.getElementById('sommaire').getBoundingClientRect().bottom <= document.getElementById('section-synthese').getBoundingClientRect().top,
      position: getComputedStyle(document.getElementById('sommaire')).position
    }));
    verifier('le sommaire est sous « Suivi FWD » et la semaine, hors de leur bandeau, avant le premier panneau, collant',
      tete.horsTitre && tete.sousTitre && tete.avantPanneaux && tete.position === 'sticky', JSON.stringify(tete));
    const adresse = await p.evaluate(() => location.href);
    // Le glissement doux avance image par image : la page doit être au premier plan.
    await p.bringToFront();
    await p.click('#sommaire-liste a[data-chapitre="section-plans"]');
    /* Attendre la fin du glissement (au plus 4 s) : sous Playwright, une page
       sans rien à repeindre peut le laisser en plan ; l'attente image par
       image (raf) le fait avancer. */
    await p.waitForFunction(() => {
      const s = document.getElementById('section-plans').getBoundingClientRect().top;
      const n = document.getElementById('sommaire').getBoundingClientRect().bottom;
      return s >= n && s <= n + 40;
    }, null, { timeout: 4000, polling: 'raf' }).catch(() => {});
    await p.waitForTimeout(300);
    const saut = await p.evaluate(() => {
      const nav = document.getElementById('sommaire').getBoundingClientRect();
      const sec = document.getElementById('section-plans').getBoundingClientRect();
      const courant = document.querySelector('#sommaire-liste a[aria-current]');
      return { navHaut: Math.round(nav.top), navBas: nav.bottom, secHaut: sec.top, scroll: window.scrollY,
               courant: courant && courant.dataset.chapitre, focus: document.activeElement === document.querySelector('#section-plans h2'),
               href: location.href, colle: document.getElementById('sommaire').dataset.colle };
    });
    /* Débrief 27, lot G : l'adresse suit la vue (« section=plans » après le
       saut, voir le lien de la vue) ; ce qui compte ici : pas de saut
       d'ancre, jamais « #section-plans ». */
    verifier('un clic sur « 05 Plans » descend au panneau, juste sous le sommaire collé en haut, sans saut d’ancre dans l’adresse',
      saut.scroll > 500 && saut.navHaut === 0 && saut.secHaut >= saut.navBas && saut.secHaut <= saut.navBas + 40 &&
      saut.href.replace(/#.*$/, '') === adresse.replace(/#.*$/, '') && !/#section-plans$/.test(saut.href) && saut.colle === 'true',
      JSON.stringify(saut));
    verifier('le panneau atteint est marqué dans le sommaire, et le focus clavier est sur son titre',
      saut.courant === 'section-plans' && saut.focus, JSON.stringify(saut));
    await p.evaluate(() => document.getElementById('section-tendance').scrollIntoView());
    await p.waitForTimeout(400);
    verifier('en faisant défiler, la marque suit le panneau qu’on lit',
      await p.evaluate(() => (document.querySelector('#sommaire-liste a[aria-current]') || {}).dataset.chapitre) === 'section-tendance');
    /* Un filtre actif : le sommaire colle en haut, la ligne des filtres juste
       dessous. Débrief 27 (lot H, P-F6) : l'ordre s'inverse — le bandeau des
       filtres ne prend plus de place dans la page (hauteur nulle, sa ligne
       posée par-dessus), il pend sous le sommaire collé. */
    await p.click('.etat-btn >> nth=0'); await p.waitForTimeout(500);
    await p.evaluate(() => document.getElementById('section-repartition').scrollIntoView()); await p.waitForTimeout(400);
    const sousFiltres = await p.evaluate(() => {
      const f = document.querySelector('#filtres-actifs .filtres-ligne').getBoundingClientRect(), n = document.getElementById('sommaire').getBoundingClientRect();
      return { filtres: !document.getElementById('filtres-actifs').hidden, fHaut: Math.round(f.top), nBas: Math.round(n.bottom), nHaut: Math.round(n.top),
               place: Math.round(document.getElementById('filtres-actifs').getBoundingClientRect().height) };
    });
    verifier('avec un filtre actif, le sommaire colle en haut et la ligne des filtres juste dessous, sans le recouvrir ni prendre de place',
      sousFiltres.filtres && sousFiltres.nHaut === 0 && Math.abs(sousFiltres.fHaut - sousFiltres.nBas) <= 1 && sousFiltres.place === 0, JSON.stringify(sousFiltres));
    await reinitialiser(p);
    // La dimension suit : « Par ECP » quand on groupe par ECP. Puis on remet celle d'avant.
    const autreDim = await p.evaluate(() => {
      const s = document.getElementById('dim-critique'), avant = s.value;
      const o = [...s.options].find(x => x.value !== avant);
      if (!o) return null;
      s.value = o.value; s.dispatchEvent(new Event('change', { bubbles: true }));
      const r = { choisi: o.text.replace(/ \(.*\)$/, ''), lien: document.getElementById('sommaire-groupe').textContent };
      s.value = avant; s.dispatchEvent(new Event('change', { bubbles: true }));
      return r;
    });
    verifier('l’entrée 04 du sommaire suit la dimension choisie dans le titre',
      !!autreDim && autreDim.lien === 'Par ' + autreDim.choisi, JSON.stringify(autreDim));
    // Concept harnais : pas de comparaison, l'entrée 06 s'efface.
    await p.click('#choix-indicateur button[data-indicateur="concept"]'); await p.waitForTimeout(700);
    const sansSEE = await p.evaluate(() => ({
      cachee: document.getElementById('rapprochement').hidden,
      liens: [...document.querySelectorAll('#sommaire-liste li:not([hidden]) a')].map(a => a.dataset.chapitre)
    }));
    /* Débrief 27 (lot H, P-F12) : l'entrée 06 ne disparaît plus sans un mot —
       elle reste, grisée (aria-disabled), avec sa raison. */
    const sansSEE27 = await p.evaluate(() => {
      const a = document.querySelector('#sommaire-liste a[data-chapitre="rapprochement"]');
      return { grisee: a.getAttribute('aria-disabled') === 'true' && a.parentNode.hasAttribute('data-absent'), raison: a.title };
    });
    verifier('sans seconde base affichée (concept harnais), l’entrée « Comparaison » reste au sommaire, grisée, avec sa raison ; les cinq autres mènent à leur panneau',
      sansSEE.cachee && sansSEE.liens.length === 6 && sansSEE.liens[5] === 'rapprochement' && sansSEE27.grisee && /concept harnais/.test(sansSEE27.raison),
      JSON.stringify([sansSEE, sansSEE27]));
    await p.click('#choix-indicateur button[data-indicateur="def"]'); await p.waitForTimeout(700);
    await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(300);

    // Moins d'animations demandées : le saut est immédiat.
    const ctxR = await contexte({ reducedMotion: 'reduce' });
    const pr = await page(ctxR, 'sommaire sans animation');
    await pr.click('#sommaire-liste a[data-chapitre="section-repartition"]');
    const immediat = await pr.evaluate(() => window.scrollY);
    await pr.waitForTimeout(600);
    const ensuite = await pr.evaluate(() => window.scrollY);
    verifier('si le système demande moins d’animations, le saut est immédiat, sans glissement',
      immediat > 300 && immediat === ensuite, immediat + ' puis ' + ensuite);
    await ctxR.close();

    // Au téléphone : le sommaire défile de côté dans sa ligne, jamais la page.
    const ctxT = await contexte({ viewport: { width: 390, height: 844 } });
    const pt = await page(ctxT, 'sommaire téléphone');
    await pt.click('#sommaire-liste a[data-chapitre="rapprochement"]');
    /* Débrief 29 (batterie) : plus de délai fixe (1,5 s) — sur une machine
       chargée, le glissement n'était pas fini ; on attend que la page soit
       arrivée (l'entrée marquée, 5 s au plus, image par image). */
    await pt.waitForFunction(() => (document.querySelector('#sommaire-liste a[aria-current]') || { dataset: {} }).dataset.chapitre === 'rapprochement',
      null, { timeout: 5000, polling: 'raf' }).catch(() => {});
    await pt.waitForTimeout(300);
    const tel = await pt.evaluate(() => {
      const l = document.getElementById('sommaire-liste'), a = l.querySelector('a[aria-current]');
      const lr = l.getBoundingClientRect(), ar = a ? a.getBoundingClientRect() : null;
      return { page: document.documentElement.scrollWidth <= window.innerWidth, defile: l.scrollWidth > l.clientWidth,
               courant: a && a.dataset.chapitre, enVue: !!ar && ar.left >= lr.left - 1 && ar.right <= lr.right + 1,
               haut: Math.round(document.getElementById('sommaire').getBoundingClientRect().top) };
    });
    verifier('à 390 px, le sommaire défile dans sa ligne (la page, non), collé en haut, le panneau courant en vue',
      tel.page && tel.defile && tel.courant === 'rapprochement' && tel.enVue && tel.haut === 0, JSON.stringify(tel));

    // Défaut 3c : au téléphone, « Plans 65 » s'aligne comme ses voisins.
    /* Débrief 27 (lot C, M2) : la carte est plus courte — « Plans 65 » au
       bord droit, sur la ligne du nom ; dessous la barre, puis la fin
       estimée (à gauche) et le rythme (au bord droit, comme le nombre de
       plans), chacun sous son libellé. */
    await pt.evaluate(() => document.getElementById('zone-critique').scrollIntoView()); await pt.waitForTimeout(500);
    const plansTel = await pt.evaluate(() => {
      const l = [...document.querySelectorAll('#zone-critique .critique-ligne')].find(x => x.querySelector('.critique-total'));
      const bord = (el, cote) => { const r = document.createRange(); r.selectNodeContents(el); return Math.round(r.getBoundingClientRect()[cote]); };
      const tot = l.querySelector('.critique-total'), nom = l.querySelector('.critique-nom'), fin = l.querySelector('.critique-date .v'), eff = l.querySelector('.critique-effort .v');
      const rl = l.getBoundingClientRect();
      return { total: bord(tot, 'right'), effort: bord(eff, 'right'), ligneDroite: Math.round(rl.right),
               finGauche: bord(fin, 'left'), ligneGauche: Math.round(rl.left),
               memeLigne: Math.abs(tot.getBoundingClientRect().top + tot.getBoundingClientRect().height / 2 - (nom.getBoundingClientRect().top + nom.getBoundingClientRect().height / 2)) <= 4,
               hauteur: Math.round(rl.height) };
    });
    verifier('à 390 px, une ligne « par ATA » : le nombre de plans au bord droit sur la ligne du nom, le rythme au même bord, la fin estimée à gauche ; la carte tient en 140 px (débrief 27)',
      Math.abs(plansTel.total - plansTel.ligneDroite) <= 2 && Math.abs(plansTel.effort - plansTel.ligneDroite) <= 2 && plansTel.memeLigne &&
      plansTel.finGauche - plansTel.ligneGauche <= 2 && plansTel.hauteur <= 140, JSON.stringify(plansTel));

    // Défaut 3b : la vue d'ensemble au téléphone, une carte par contrat.
    await pt.evaluate(() => window.scrollTo(0, 0));
    await pt.click('#voir-ensemble'); await pt.waitForTimeout(900);
    const ens = await pt.evaluate(() => {
      const d = document.querySelector('.defile-ensemble'), h2 = document.querySelector('.ensemble-tete h2'),
            x = document.querySelector('.ensemble-tete .fiche-plan-fermer');
      const cellules = [...document.querySelectorAll('.ensemble-table tbody td')];
      const visibles = cellules.filter(c => c.getBoundingClientRect().width > 0);
      return { cache: d.scrollWidth - d.clientWidth, page: document.documentElement.scrollWidth <= window.innerWidth,
               cellules: cellules.length, visibles: visibles.length,
               libelles: visibles.every(c => c.colSpan > 1 || (c.dataset.libelle && getComputedStyle(c, '::before').content.length > 2)),
               dansLeCadre: visibles.every(c => c.getBoundingClientRect().right <= d.getBoundingClientRect().right + 1),
               croix: Math.abs(x.getBoundingClientRect().top - h2.getBoundingClientRect().top) <= 8 && x.getBoundingClientRect().left > h2.getBoundingClientRect().left };
    });
    verifier('à 390 px, la vue d’ensemble montre toutes les valeurs, chacune avec le nom de sa colonne, rien de caché à droite',
      ens.cache <= 0 && ens.page && ens.cellules > 6 && ens.visibles === ens.cellules && ens.libelles && ens.dansLeCadre, JSON.stringify(ens));
    verifier('à 390 px, la croix de la vue d’ensemble est sur la ligne du titre, pas seule sur la sienne', ens.croix, JSON.stringify(ens));
    await ctxT.close();

    // Défaut 3a : les en-têtes du journal ne se coupent plus mot à mot entre 768 et 900 px.
    for (const w of [900, 820, 768]) {
      await redimensionner(p, w, 950);
      const ent = await p.evaluate(() => [...document.querySelectorAll('.journal-entetes .entete-col')].map(e => {
        const lh = parseFloat(getComputedStyle(e.parentNode).lineHeight) || 15;
        return { texte: e.textContent, lignes: Math.round(e.getBoundingClientRect().height / lh) };
      }));
      verifier('à ' + w + ' px, chaque en-tête du journal tient sur deux lignes au plus (« passés à » / « « Terminé » »)',
        ent.length >= 3 && ent.every(e => e.lignes <= 2), JSON.stringify(ent));
    }
    await redimensionner(p, 1280, 950);
  }
  {
    // Le classeur vide : le geste de la fenêtre d'import, le collage en secours ; ni sommaire.
    const ctxV = await contexte();
    await ctxV.addInitScript(() => {
      window.SUIVI_FWD_DONNEES = { ok: false, message: 'Feuille vide : aucun plan.', colonnes: [], plans: [], releves: [], jalons: [], contrats: [], contrat: '' };
    });
    const pv = await page(ctxV, 'classeur vide (débrief 20)');
    const vide = await pv.evaluate(() => {
      const z = document.getElementById('classeur-vide');
      return { gestes: [...z.querySelectorAll('ol li')].map(li => li.textContent),
               secours: [...z.querySelectorAll('p.doux')].map(x => x.textContent).join(' | '),
               sommaire: getComputedStyle(document.getElementById('sommaire')).display,
               /* Débrief 29 (B4) : la liste des sections et la loupe se taisent, les
                  outils (Aide, Vue d'ensemble, Administration) restent. */
               liste: getComputedStyle(document.getElementById('sommaire-liste')).display, loupe: getComputedStyle(document.getElementById('cherche-plan')).display,
               aide: (b => !!b && b.getClientRects().length > 0)(document.getElementById('ouvrir-aide')) };
    });
    verifier('classeur vide : trois gestes — le menu « Importer les exports GATES et SEE… », les fichiers choisis sans les ouvrir, le relevé archivé par la même fenêtre',
      vide.gestes.length === 3 && /Suivi FWD → Importer les exports GATES et SEE…/.test(vide.gestes[0]) &&
      /plusieurs d’un coup/.test(vide.gestes[1]) && /sans les ouvrir/.test(vide.gestes[1]) && /archive le relevé/.test(vide.gestes[1]) &&
      !vide.gestes.some(g => /copier|coller|Ctrl/.test(g)), JSON.stringify(vide.gestes));
    verifier('classeur vide : le collage reste, en secours, sur une ligne à part', /coller/.test(vide.secours) && /Archiver le relevé/.test(vide.secours), vide.secours);
    verifier('classeur vide : pas de liste de sections ni de loupe (il n’y a aucun panneau) ; l’Aide reste au bout du sommaire (débrief 29)',
      vide.sommaire !== 'none' && vide.liste === 'none' && vide.loupe === 'none' && vide.aide, JSON.stringify(vide));
    await ctxV.close();
  }
  await reinitialiser(p);

  // =================================================================
  section('Débrief 20 : relecture');
  /* Les constats de la relecture du débrief 20, chacun reproduit d'abord tel
     qu'il trompait. Chaque cas ouvre sa propre fenêtre : la page principale
     reste dans l'état qu'attend la suite. */
  {
    /* Graphique : « manque N » ne disparaît plus sous « fin … ». Le cas
       trouvé : PERSO, par ECP, ECP-2108 ouvert — le jalon 1 et la fin à deux
       semaines d'écart ; à 1024 px on ne lisait plus que « ma ». Puis un
       balayage : à toute largeur, aucun mot du graphique n'est recouvert par
       un fond plein posé après lui, ni ne chevauche un autre mot. */
    /* La mesure, posée dans la page : les mots du graphique (« manque »,
       « fin »), ceux qu'un fond plein dessiné après eux recouvre, et ceux
       qui en chevauchent un autre. */
    const poserMesure = pg => pg.evaluate(() => {
      window.__motsRecouverts = () => {
        const svg = document.querySelector('#zone-graphe svg');
        if (!svg) return { mots: [], couverts: [], chevauches: [] };
        const ts = [...svg.querySelectorAll('text')].filter(t => t.textContent.trim() && t.getClientRects().length);
        const fonds = [...svg.querySelectorAll('rect.fond-mot')];
        const coupe = (a, c) => Math.min(a.right, c.right) - Math.max(a.left, c.left) > 1 && Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top) > 2;
        const nom = t => (t.querySelector('title') ? t.textContent.replace(t.querySelector('title').textContent, '') : t.textContent).trim();
        const couverts = [], chevauches = [];
        ts.forEach((t, i) => {
          const a = t.getBoundingClientRect();
          fonds.forEach(r => { if ((t.compareDocumentPosition(r) & Node.DOCUMENT_POSITION_FOLLOWING) && coupe(a, r.getBoundingClientRect())) couverts.push(nom(t)); });
          ts.slice(i + 1).forEach(u => { if (coupe(a, u.getBoundingClientRect())) chevauches.push(nom(t) + ' × ' + nom(u)); });
        });
        return { mots: ts.filter(t => t.classList.contains('manque-jalon') || t.classList.contains('fin-mot')).map(nom), couverts, chevauches };
      };
    });
    const motsRecouverts = pg => pg.evaluate(() => window.__motsRecouverts());
    for (const w of [1024, 1100, 1440]) {
      const ctxM = await contexte({ viewport: { width: w, height: 900 } });
      const pm = await page(ctxM, 'manque sous fin ' + w);
      await pm.click('#choix-perimetre button:nth-child(3)'); await pm.waitForTimeout(300);
      await pm.selectOption('#dim-critique', 'ecp'); await pm.waitForTimeout(300);
      /* Débrief 27 (lot C) : la courbe d'un groupe vient du filtre de la page posé sur lui. */
      await pm.locator('#zone-critique button.critique-ligne[data-groupe="ECP-2108"]').click(); await pm.waitForTimeout(300);
      await pm.click('#filtrer-groupe-page'); await pm.waitForTimeout(400);
      await poserMesure(pm);
      const r = await motsRecouverts(pm);
      verifier('à ' + w + ' px, PERSO, ECP-2108 ouvert : « manque N » et « fin … » se lisent tous deux, aucun fond plein ne recouvre un mot',
        r.mots.some(m => /^manque \d/.test(m)) && r.mots.some(m => /^fin S/.test(m)) && !r.couverts.length && !r.chevauches.length, JSON.stringify(r));
      await ctxM.close();
    }
    /* Le balayage se joue dans la page (un clic, une mesure, sans aller-
       retour avec le pilote) : le dessin du graphique suit le clic sans
       attendre. */
    const balayage = [];
    let vus = 0, avecManque = 0;
    for (const w of [390, 768, 1440]) {
      const ctxB = await contexte({ viewport: { width: w, height: 900 } });
      const pb = await page(ctxB, 'balayage du graphique ' + w);
      await poserMesure(pb);
      const r = await pb.evaluate(() => {
        const out = { vus: 0, avecManque: 0, fautes: [] };
        const choisirDim = d => { const s = document.getElementById('dim-critique'); s.value = d; s.dispatchEvent(new Event('change', { bubbles: true })); };
        for (const span of ['jalons', '26']) {
          document.querySelector('.commandes-graphe .segmente button[data-span="' + span + '"]').click();
          for (let per = 1; per <= 3; per++) {
            document.querySelector('#choix-perimetre button:nth-child(' + per + ')').click();
            for (const dim of ['ata', 'cc', 'ecp']) {
              choisirDim(dim);
              const noms = [...document.querySelectorAll('#zone-critique button.critique-ligne')].slice(0, 12).map(b => b.dataset.groupe);
              for (let i = -1; i < noms.length; i++) {
                const ligne = () => [...document.querySelectorAll('#zone-critique button.critique-ligne')].find(b => b.dataset.groupe === noms[i]);
                /* Débrief 27 (lot C) : déplier la ligne, puis filtrer la page sur
                   elle (le graphique suit le groupe) ; défaire dans l'ordre inverse. */
                if (i >= 0) { ligne().click(); document.getElementById('filtrer-groupe-page').click(); }
                const m = window.__motsRecouverts();
                out.vus++; if (m.mots.some(x => /^manque/.test(x))) out.avecManque++;
                if (m.couverts.length || m.chevauches.length) out.fautes.push(span + '/' + per + '/' + dim + '/' + (i < 0 ? '—' : noms[i]) + ' : ' + JSON.stringify(m));
                if (i >= 0) { document.getElementById('filtrer-groupe-page').click(); ligne().click(); }
              }
            }
          }
        }
        return out;
      });
      vus += r.vus; avecManque += r.avecManque;
      r.fautes.forEach(f => balayage.push(w + ' px, ' + f));
      await ctxB.close();
    }
    verifier('balayage (390, 768, 1440 px × Échéances, 6 mois × 3 périmètres × ATA, CC, ECP × chaque groupe) : aucun mot recouvert ni chevauché',
      !balayage.length && vus > 300 && avecManque > 20, vus + ' graphiques, ' + avecManque + ' avec « manque » ; ' + balayage.slice(0, 4).join(' | '));
  }
  {
    /* La fiche d'échéance nomme le périmètre du jalon quand ce n'est pas
       celui qu'on regarde : sous « Tout », « Diffusion TO Base » compte ses
       plans BASE/OPTION, et l'ATA 24 y finit plus tôt que sur sa ligne du
       bloc, qui compte tous ses plans. Sous BASE/OPTION, les deux disent la
       même semaine et la phrase n'a rien à préciser. */
    const ctxF = await contexte({ viewport: { width: 1440, height: 900 } });
    const pf = await page(ctxF, 'fiche et périmètre');
    await pf.click('button:has-text("Concept harnais")'); await pf.waitForTimeout(800);
    await pf.selectOption('#dim-critique', 'ata'); await pf.waitForTimeout(300);
    const lireFiche = async per => {
      await pf.click('#choix-perimetre button:nth-child(' + per + ')'); await pf.waitForTimeout(400);
      if (!await pf.$('#fiche-echeance')) { await pf.click('#echeance-titre'); await pf.waitForTimeout(400); }
      return pf.evaluate(() => {
        const v = (document.querySelector('#fiche-echeance .fiche-echeance-verdict') || { textContent: '' }).textContent.replace(/[  ]/g, ' ');
        const m = v.match(/le dernier groupe \(ATA (\w+)\)(, sur ses plans ([^,]+),)? finirait en (S\d+)/);
        const ligne = m ? document.querySelector('#zone-critique .critique-ligne[data-groupe="' + m[1] + '"] .critique-date .v') : null;
        return { verdict: v, groupe: m && m[1], portee: m && m[3], fin: m && m[4], ligne: ligne ? ligne.textContent.replace(/[  ]/g, ' ') : '' };
      });
    };
    const tout = await lireFiche(1), base = await lireFiche(2);
    verifier('concept harnais, sous « Tout » : « le dernier groupe (ATA 24), sur ses plans BASE/OPTION, finirait en S… » — le périmètre du jalon est dit',
      !!tout.groupe && tout.portee === 'BASE/OPTION', JSON.stringify(tout));
    verifier('sous BASE/OPTION, la phrase ne répète pas le périmètre, et sa semaine est celle de la ligne du groupe dans le bloc',
      !!base.groupe && !base.portee && base.ligne.indexOf(base.fin + ' ') === 0, JSON.stringify(base));
    verifier('et la fin dite sous « Tout » est bien celle du périmètre du jalon (la même que sous BASE/OPTION)',
      tout.fin === base.fin && tout.groupe === base.groupe, tout.fin + ' / ' + base.fin);
    await ctxF.close();
  }
  {
    /* Sous une tuile Validé, les boutons « N à l'arrêt » restent (le clic
       retire la tuile) : la note qui définit le mot reste avec eux. */
    const ctxA = await contexte({ viewport: { width: 1440, height: 900 } });
    const pa = await page(ctxA, 'note à l’arrêt');
    await pa.selectOption('#dim-critique', 'ata'); await pa.waitForTimeout(300);
    const lire = () => pa.evaluate(() => ({ boutons: document.querySelectorAll('#zone-critique button[data-arret-groupe]').length,
      note: !!document.querySelector('#zone-critique .note-arret') }));
    const avant = await lire();
    await pa.click('#etats .etat-btn[data-famille="termine"]'); await pa.waitForTimeout(400);
    const sousValide = await lire();
    verifier('sans filtre, des groupes ont « N à l’arrêt » et la note qui le définit est là', avant.boutons > 0 && avant.note, JSON.stringify(avant));
    verifier('sous la tuile Validé, les boutons « N à l’arrêt » restent et la note aussi (même compte)',
      sousValide.boutons > 0 && sousValide.note, JSON.stringify(sousValide));
    await pa.click('#etats .etat-btn[data-famille="termine"]'); await pa.waitForTimeout(300);
    await pa.click('#filtre-valeur-groupe button[data-valeur-bloc="termine"]'); await pa.waitForTimeout(400);
    const valeurValide = await lire();
    verifier('sous la valeur « Validé » du bloc, aucun groupe n’a de plan à l’arrêt : ni bouton, ni note',
      valeurValide.boutons === 0 && !valeurValide.note, JSON.stringify(valeurValide));
    await ctxA.close();
  }
  {
    /* Le second clic sur « N à l'arrêt » défait aussi la tuile que le
       premier avait posée lui-même (sous la valeur « En cours » du bloc) —
       mais pas une tuile que Nathan a pressée entre-temps. */
    const ctxT = await contexte({ viewport: { width: 1440, height: 900 } });
    const pt = await page(ctxT, 'tuile posée par « à l’arrêt »');
    await pt.selectOption('#dim-critique', 'ata'); await pt.waitForTimeout(300);
    const etat = () => pt.evaluate(() => ({
      lignes: document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length,
      tuiles: [...document.querySelectorAll('#etats .etat-btn[aria-pressed="true"]')].map(b => b.dataset.etat),
      filtres: (document.getElementById('filtres-actifs') || { textContent: '' }).textContent.replace(/\s+/g, ' ').trim() }));
    const depart = await etat();
    await pt.click('#filtre-valeur-groupe button[data-valeur-bloc="encours"]'); await pt.waitForTimeout(400);
    const groupeA = await pt.evaluate(() => document.querySelector('#zone-critique button[data-arret-groupe]').getAttribute('data-arret-groupe'));
    const bouton = '#zone-critique button[data-arret-groupe="' + groupeA + '"]';
    await pt.click(bouton); await pt.waitForTimeout(400);
    const premier = await etat();
    await pt.click(bouton); await pt.waitForTimeout(400);
    const second = await etat();
    verifier('sous la valeur « En cours » du bloc, le premier clic sur « N à l’arrêt » pose la tuile En cours et réduit le tableau',
      premier.tuiles.join() === 'encours' && premier.lignes > 0 && premier.lignes < depart.lignes, JSON.stringify(premier));
    verifier('le second clic retire la sélection ET la tuile qu’il avait posée : plus d’« État : En cours » jamais pressé à la main',
      !second.tuiles.length && !/État/.test(second.filtres), JSON.stringify(second));
    // La tuile pressée à la main entre les deux clics reste à Nathan.
    await pt.click(bouton); await pt.waitForTimeout(400);
    await pt.click('#etats .etat-btn[data-etat="encours"]'); await pt.waitForTimeout(300);
    await pt.click('#etats .etat-btn[data-etat="encours"]'); await pt.waitForTimeout(300);
    const presse = await pt.evaluate(b => document.querySelector(b).getAttribute('aria-pressed'), bouton);
    await pt.click(bouton); await pt.waitForTimeout(400);
    const garde = await etat();
    verifier('une tuile En cours re-pressée à la main entre les deux clics n’est pas retirée par le second',
      presse === 'true' && garde.tuiles.join() === 'encours', presse + ' ' + JSON.stringify(garde));
    /* La sélection retirée par la croix du bandeau : la tuile qui reste,
       Nathan l'a vue et gardée — elle est à lui. Un nouvel aller-retour sur
       « à l'arrêt » ne la retire pas. */
    await pt.click('#etats .etat-btn[data-etat="encours"]'); await pt.waitForTimeout(300);
    await pt.click(bouton); await pt.waitForTimeout(400);
    const avantCroix = await etat();
    await pt.click('#filtres-actifs button[data-retirer="refs"]'); await pt.waitForTimeout(400);
    await pt.click(bouton); await pt.waitForTimeout(400);
    await pt.click(bouton); await pt.waitForTimeout(400);
    const apresCroix = await etat();
    verifier('la croix du bandeau sur la sélection laisse la tuile posée par le clic à Nathan : un aller-retour sur « à l’arrêt » ne la retire plus',
      avantCroix.tuiles.join() === 'encours' && apresCroix.tuiles.join() === 'encours', JSON.stringify([avantCroix, apresCroix]));
    await ctxT.close();
  }
  {
    /* Le sommaire : un nom de dimension long pousse « Plans » et
       « Comparaison » hors de la ligne bien au-delà du téléphone ; le fondu
       du bord droit le dit à toute largeur. */
    const longue = 'Classification calculée bêta du bureau d’études électrique';
    for (const w of [768, 900]) {
      const ctxS = await contexte({ viewport: { width: w, height: 850 } });
      const ps = await page(ctxS, 'sommaire ' + w);
      await ps.evaluate(t => {
        const s = window.__jeuDExemple('HDK');
        s.colonnes.forEach(c => { if (c.cle === 'ata') c.titre = t; });
        window.__chargerSource(s);
      }, longue);
      await ps.waitForTimeout(500);
      await ps.selectOption('#dim-critique', 'ata'); await ps.waitForTimeout(400);
      const r = await ps.evaluate(() => {
        const l = document.getElementById('sommaire-liste'), cs = getComputedStyle(l);
        return { entree: document.getElementById('sommaire-groupe').textContent, deborde: l.scrollWidth - l.clientWidth,
                 classe: l.classList.contains('deborde-droite'), masque: cs.webkitMaskImage || cs.maskImage };
      });
      verifier('à ' + w + ' px, « Par Classification calculée… » déborde du sommaire : le fondu du bord droit le signale',
        /Classification/.test(r.entree) && r.deborde > 2 && r.classe && /gradient/.test(r.masque), JSON.stringify(r));
      await ctxS.close();
    }
    const ctxL = await contexte({ viewport: { width: 1440, height: 850 } });
    const pl = await page(ctxL, 'sommaire large');
    const large = await pl.evaluate(() => {
      const l = document.getElementById('sommaire-liste'), cs = getComputedStyle(l);
      return { deborde: l.scrollWidth - l.clientWidth, classe: l.classList.contains('deborde-droite'), masque: cs.webkitMaskImage || cs.maskImage };
    });
    verifier('à 1440 px, le sommaire tient : pas de fondu', large.deborde <= 2 && !large.classe && large.masque === 'none', JSON.stringify(large));
    await ctxL.close();
  }
  {
    /* La puce d'un plan à l'arrêt garde le « au moins » de sa bulle : quand
       la suite remonte au premier relevé connu, « depuis ≤ S26 ». */
    await p.selectOption('#dim-critique', 'ata'); await p.waitForTimeout(300);
    const jetons = await p.evaluate(() => {
      const out = [];
      [...document.querySelectorAll('#zone-critique .critique-ligne')].forEach(l => { if (l.getAttribute('aria-expanded') !== 'true') l.click(); });
      document.querySelectorAll('#zone-critique .jeton-ud.arret').forEach(j => {
        out.push({ auMoins: /depuis au moins S\d+/.test(j.title), puce: (j.querySelector('.depuis') || { textContent: '' }).textContent.replace(/ /g, ' ') });
      });
      [...document.querySelectorAll('#zone-critique .critique-ligne[aria-expanded="true"]')].forEach(l => l.click());
      return out;
    });
    const faux = jetons.filter(j => j.auMoins ? !/^depuis ≤ S\d+$/.test(j.puce) : !/^depuis S\d+$/.test(j.puce));
    verifier('plans à l’arrêt : « depuis ≤ S26 » quand la bulle dit « depuis au moins S26 », « depuis S30 » sinon',
      jetons.some(j => j.auMoins) && !faux.length, jetons.length + ' puces ; ' + JSON.stringify(faux.slice(0, 3)));
    await reinitialiser(p);
  }
  {
    /* La puce d'échéance au téléphone : le groupe passe à la ligne, aligné
       sous « Prochaine échéance », sans « · » isolé en tête ; au large, le
       « · » sépare toujours l'échéance du groupe, sur la même ligne. */
    for (const w of [360, 390, 1440]) {
      const ctxE = await contexte({ viewport: { width: w, height: 900 } });
      const pe = await page(ctxE, 'puce d’échéance ' + w);
      const cas = [];
      for (const dim of ['_mois', 'ata']) {
        await pe.selectOption('#dim-critique', dim); await pe.waitForTimeout(300);
        // Débrief 27 (lot C) : la puce nomme le groupe quand la page est filtrée sur lui.
        await pe.locator('#zone-critique button.critique-ligne').first().click(); await pe.waitForTimeout(300);
        await pe.click('#filtrer-groupe-page'); await pe.waitForTimeout(300);
        cas.push(await pe.evaluate(() => {
          const b = document.getElementById('echeance-titre'), mot = b.querySelector('span:not(.point):not(.portee):not(.jours)');
          const po = b.querySelector('.portee'), jo = b.querySelector('.jours');
          const r = e => e.getBoundingClientRect();
          return { texte: po.textContent, avant: getComputedStyle(po, '::before').content,
                   gauche: Math.round(r(po).left - r(mot).left), jours: Math.round(r(jo).left - r(mot).left),
                   ligne: Math.round(r(po).top - r(mot).top), largeur: b.scrollWidth <= b.clientWidth + 1 };
        }));
        await pe.click('#filtrer-groupe-page'); await pe.waitForTimeout(200);
        await pe.locator('#zone-critique button.critique-ligne').first().click(); await pe.waitForTimeout(200);
      }
      const telephone = w < 480;
      verifier('à ' + w + ' px, la puce d’échéance nomme le groupe sans « · » dans le texte' +
        (telephone ? ' ; au téléphone, groupe et jours sur la seconde ligne, alignés sous « Prochaine échéance », sans « · »' : ' ; au large, le « · » du style le sépare, sur la même ligne'),
        cas.every(c => c.texte.indexOf('·') === -1 && c.largeur &&
          (telephone ? c.avant === 'none' && c.ligne > 8 && Math.abs(c.gauche) <= 1 && (Math.abs(c.jours) <= 1 || c.jours > c.gauche)
                     : /·/.test(c.avant) && Math.abs(c.ligne) <= 2 && c.gauche > 0)), JSON.stringify(cas));
      await ctxE.close();
    }
  }
  {
    /* Les messages de la page disent d'abord d'importer (la fenêtre
       remplace l'onglet et archive dans la foulée), le collage en secours. */
    const textes = await p.evaluate(() => {
      const out = {};
      const lireJournal = () => (document.querySelector('#zone-journal .journal-vide') || { textContent: '' }).textContent.replace(/[  ]/g, ' ');
      const lireAlerte = () => { const z = document.getElementById('alerte-valeurs'); return z.hidden ? '' : z.textContent.replace(/[  ]/g, ' '); };
      const s1 = window.__jeuDExemple('HDK');
      const carte = {}; s1.plans.forEach(x => { carte[x.reference] = x.avancement; });
      s1.releves = s1.releves.slice(-2).map(r => Object.assign({}, r, { plans: Object.assign({}, carte) }));
      window.__chargerSource(s1);
      out.journal = lireJournal();
      const s2 = window.__jeuDExemple('HDK');
      s2.plans = s2.plans.concat(s2.plans.slice(0, 3).map(x => Object.assign({}, x)));
      window.__chargerSource(s2);
      out.doublons = lireAlerte();
      const s3 = window.__jeuDExemple('HDK');
      s3.plans.forEach(x => { x.avancement = ''; });
      window.__chargerSource(s3);
      out.colonne = lireAlerte();
      window.__chargerSource(window.__jeuDExemple('HDK'));
      return out;
    });
    const menu = 'menu Suivi FWD → Importer les exports GATES et SEE…';
    verifier('journal vide, deux relevés identiques : importer le dernier export (le menu, qui archive dans la foulée), ou le recoller puis archiver',
      textes.journal.indexOf('importer le dernier export de GATES (' + menu + ', qui archive dans la foulée), ou le recoller puis archiver.') !== -1, textes.journal);
    verifier('références en double : le réimporter (l’onglet est remplacé en entier), ou le recoller sur un onglet vidé',
      textes.doublons.indexOf('le réimporter (' + menu + ' : l’onglet est remplacé en entier), ou le recoller sur un onglet vidé (Ctrl+A, Suppr).') !== -1, textes.doublons);
    verifier('colonne suivie vide : vérifier l’export de GATES, puis le réimporter par le menu — plus « l’export collé »',
      /est vide sur les \d+ plans/.test(textes.colonne) && textes.colonne.indexOf('puis le réimporter (' + menu + ').') !== -1 && !/export collé/.test(textes.colonne), textes.colonne);
    await p.waitForTimeout(400);
    await reinitialiser(p);
  }

  // =================================================================
  section('Débrief 21 : bandeau');
  /* Débrief 21 : « ce qui change semaine par semaine, sa propre partie
     distincte » ; « par ECP, la flèche est cachée par ECP » ; « Suivi FWD,
     c'est trop caché dans le fond » ; « aller encore plus loin pour séparer
     les étapes ». Chaque point est vérifié sur la page telle qu'elle se
     dessine : le journal dans son panneau, le chevron jamais sous le mot,
     le titre dans sa bande, les panneaux bien séparés — dans les deux thèmes. */
  {
    await reinitialiser(p);
    await p.setViewportSize({ width: 1280, height: 950 });
    await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(400);

    // --- 1. Le journal, un panneau à lui, juste après la courbe.
    const jp = await p.evaluate(() => {
      const t = document.getElementById('section-tendance'), sec = document.getElementById('section-journal');
      return {
        panneau: !!sec && sec.matches('section.bloc.panneau.teinte-journal'),
        apres: !!sec && t.nextElementSibling === sec,
        chezLui: !!sec && ['zone-journal', 'filtre-journal', 'recherche-journal'].every(id => sec.contains(document.getElementById(id))) &&
                 !!sec.querySelector('.panneau-tete h2.titre-journal'),
        horsTendance: !t.querySelector('#zone-journal, .titre-journal, #recherche-journal, #filtre-journal'),
        surtitre: sec ? sec.querySelector('.panneau-tete .surtitre').textContent : '',
        titre: sec ? sec.querySelector('h2').textContent : '',
        panneaux: [...document.querySelectorAll('section.panneau:not(.panneau-hors-suite)')].filter(s => !s.hidden).map(s => s.id),
        liens: [...document.querySelectorAll('#sommaire-liste li:not([hidden]) a')].map(a => ({ cible: a.dataset.chapitre, texte: a.textContent.trim() }))
      };
    });
    verifier('le journal est un panneau à lui (« Changements »), juste après la tendance : titre, pastilles, recherche et liste chez lui, plus rien sous la courbe',
      jp.panneau && jp.apres && jp.chezLui && jp.horsTendance && jp.surtitre === 'Changements' && jp.titre === 'Ce qui a changé, semaine par semaine', JSON.stringify(jp));
    verifier('panneaux et sommaire dans le même ordre, donc les mêmes numéros : 01 Synthèse, 02 Tendance, 03 Changements, 04 Par…, 05 Plans, 06 Comparaison',
      JSON.stringify(jp.panneaux) === JSON.stringify(['section-synthese', 'section-tendance', 'section-journal', 'section-repartition', 'section-plans', 'rapprochement']) &&
      JSON.stringify(jp.liens.map(l => l.cible)) === JSON.stringify(jp.panneaux) && jp.liens[2].texte === 'Changements' && /^Par /.test(jp.liens[3].texte),
      JSON.stringify(jp.liens));
    // Ses gestes, dans son panneau : pastille, recherche, semaine dépliée, « Copier ».
    const gestes = await p.evaluate(async () => {
      const attendre = ms => new Promise(r => setTimeout(r, ms));
      const r = {};
      const pastille = document.querySelector('#filtre-journal button[data-journal="termine"]');
      pastille.click(); await attendre(250);
      r.pastille = window.__vueValeurs().journal === 'termine';
      document.querySelector('#filtre-journal button[data-journal=""]').click(); await attendre(250);
      r.pastilleOtee = window.__vueValeurs().journal === '';
      const tete = document.querySelector('#zone-journal button[data-semaine]');
      const avant = tete.getAttribute('aria-expanded');
      tete.click(); await attendre(250);
      const tete2 = document.querySelector('#zone-journal button[data-semaine="' + tete.dataset.semaine + '"]');
      r.deplie = avant !== tete2.getAttribute('aria-expanded');
      r.copier = !!tete2.closest('.journal-semaine').querySelector('.journal-copier button[data-copier]') || avant === 'true';
      const ref = (document.querySelector('#zone-journal button[data-ref]') || {}).dataset;
      r.ref = ref ? ref.ref : '';
      tete2.click(); await attendre(250);
      return r;
    });
    await p.fill('#recherche-journal', gestes.ref); await p.waitForTimeout(450);
    const rech21 = await p.evaluate(ref => {
      const sem = [...document.querySelectorAll('#zone-journal .journal-semaine')];
      return { n: sem.length, toutes: sem.every(s => s.textContent.indexOf(ref) !== -1) };
    }, gestes.ref);
    await p.fill('#recherche-journal', ''); await p.waitForTimeout(400);
    verifier('dans son panneau, le journal garde ses gestes : la pastille filtre, « Tout » la retire, une semaine se déplie avec « Copier », la recherche ne garde que les semaines du plan',
      gestes.pastille && gestes.pastilleOtee && gestes.deplie && gestes.copier && !!gestes.ref && rech21.n > 0 && rech21.toutes, JSON.stringify([gestes, rech21]));
    // Le sommaire y mène, le marque, et pose le focus sur son titre.
    await p.bringToFront();
    await p.click('#sommaire-liste a[data-chapitre="section-journal"]');
    await p.waitForFunction(() => {
      const s = document.getElementById('section-journal').getBoundingClientRect().top;
      const n = document.getElementById('sommaire').getBoundingClientRect().bottom;
      return s >= n && s <= n + 40;
    }, null, { timeout: 4000, polling: 'raf' }).catch(() => {});
    await p.waitForTimeout(300);
    const sautJ = await p.evaluate(() => {
      const nav = document.getElementById('sommaire').getBoundingClientRect(), sec = document.getElementById('section-journal').getBoundingClientRect();
      const courant = document.querySelector('#sommaire-liste a[aria-current]');
      return { navBas: Math.round(nav.bottom), secHaut: Math.round(sec.top), courant: courant && courant.dataset.chapitre,
               focus: document.activeElement === document.querySelector('#section-journal h2') };
    });
    verifier('« 03 Changements » dans le sommaire descend au journal, juste sous le sommaire collé, le marque et pose le focus sur son titre',
      sautJ.secHaut >= sautJ.navBas && sautJ.secHaut <= sautJ.navBas + 40 && sautJ.courant === 'section-journal' && sautJ.focus, JSON.stringify(sautJ));
    await p.evaluate(() => { document.activeElement.blur(); window.scrollTo(0, 0); }); await p.waitForTimeout(300);

    // --- 2. Le chevron du « par [ATA ▾] » : jamais sous le mot.
    /* Pour chaque dimension : le texte du mot, mesuré à part dans la police
       réellement calculée du menu ; la boîte du chevron, lue dans sa
       position de fond. Le texte (coupé au bord du contenu s'il est trop
       long) doit finir avant le chevron, le chevron doit être dans le menu,
       visible (rien ne le recouvre), et le menu dans son panneau. */
    const mesurerChevrons = pg => pg.evaluate(async () => {
      const sel = document.getElementById('dim-critique');
      const avant = sel.value, out = [];
      for (const o of [...sel.options]) {
        sel.value = o.value; sel.dispatchEvent(new Event('change', { bubbles: true }));
        sel.scrollIntoView({ block: 'center' });
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        const cs = getComputedStyle(sel), r = sel.getBoundingClientRect();
        const padL = parseFloat(cs.paddingLeft), padR = parseFloat(cs.paddingRight);
        const t = document.createElement('span');
        t.textContent = o.text;
        t.style.cssText = 'position:absolute;left:0;top:0;visibility:hidden;white-space:pre;';
        ['fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'letterSpacing', 'fontOpticalSizing', 'fontVariationSettings'].forEach(k => { t.style[k] = cs[k]; });
        document.body.appendChild(t);
        const largeurTexte = t.getBoundingClientRect().width; t.remove();
        const contenu = r.width - padL - padR;
        const finTexte = r.left + padL + Math.min(largeurTexte, contenu);
        const px = cs.backgroundPositionX, taille = parseFloat(cs.backgroundSize);
        let decalage = null;
        let m = px.match(/right\s+([\d.]+)px/); if (m) decalage = +m[1];
        m = px.match(/calc\(100% - ([\d.]+)px\)/); if (m) decalage = +m[1];
        const chevronG = decalage === null ? NaN : r.right - decalage - taille, chevronD = r.right - (decalage || 0);
        const centre = document.elementFromPoint((chevronG + chevronD) / 2, r.top + r.height / 2);
        const tete = sel.closest('.panneau-tete').getBoundingClientRect();
        out.push({ dim: o.value, mot: o.text, largeurTexte: Math.round(largeurTexte * 10) / 10, contenu: Math.round(contenu * 10) / 10,
                   ecart: Math.round((chevronG - finTexte) * 10) / 10,
                   chevronDedans: chevronG >= r.left + padL && chevronD <= r.right + 0.5,
                   visible: centre === sel, dansPanneau: r.right <= tete.right + 0.5 && r.left >= tete.left - 0.5,
                   entier: largeurTexte <= contenu + 0.5, police: cs.fontFamily.split(',')[0] });
      }
      sel.value = avant; sel.dispatchEvent(new Event('change', { bubbles: true }));
      return { mesures: out, page: document.documentElement.scrollWidth <= window.innerWidth };
    });
    const bonChevron = x => x.ecart >= 2 && x.chevronDedans && x.visible && x.dansPanneau;
    const dims21 = await p.evaluate(() => [...document.getElementById('dim-critique').options].map(o => o.text));
    for (const w of [360, 390, 768, 1024, 1440, 1920]) {
      await redimensionner(p, w, 900);
      const m = await mesurerChevrons(p);
      verifier('à ' + w + ' px, thème clair : pour les ' + dims21.length + ' dimensions, le chevron est dans le menu, visible, et le mot finit avant lui',
        m.mesures.length === dims21.length && m.mesures.every(bonChevron) && m.page, JSON.stringify(m.mesures.filter(x => !bonChevron(x))) + ' page:' + m.page);
      verifier('à ' + w + ' px : un nom court (ATA, ECP, CC, Séquence…) se lit en entier, sans être coupé',
        m.mesures.filter(x => x.mot.length <= 14).every(x => x.entier), JSON.stringify(m.mesures.filter(x => x.mot.length <= 14 && !x.entier)));
    }
    /* Avant l'arrivée de la police du titre, la page écrit le mot dans la
       police de secours ; puis Newsreader arrive. C'était le défaut : la
       largeur, mesurée une fois, ne suivait pas. On pose une police de
       secours nettement plus large (espacée), sans rien appeler du script,
       puis on la retire. */
    await redimensionner(p, 1280, 950);
    await p.selectOption('#dim-critique', 'ecp'); await p.waitForTimeout(400);
    const largeurEcp = () => p.evaluate(() => Math.round(document.getElementById('dim-critique').getBoundingClientRect().width));
    const lEcp = await largeurEcp();
    await p.addStyleTag({ content: '.titre-choix { font-family: "DejaVu Sans", Verdana, Arial, sans-serif !important; letter-spacing: .25em; } /* débrief21-secours */' });
    await p.waitForTimeout(200);
    const lSecours = await largeurEcp();
    const mSecours = await mesurerChevrons(p);
    await p.evaluate(() => { [...document.querySelectorAll('style')].filter(s => /débrief21-secours/.test(s.textContent)).forEach(s => s.remove()); });
    await p.waitForTimeout(200);
    const mApres = await mesurerChevrons(p);
    verifier('police de secours plus large (avant le chargement de Newsreader) : le menu s’élargit seul, le chevron reste après le mot, pour chaque dimension',
      lSecours > lEcp + 4 && mSecours.mesures.every(bonChevron) && mSecours.mesures[0].police !== 'Newsreader',
      lEcp + ' → ' + lSecours + ' ' + JSON.stringify(mSecours.mesures.filter(x => !bonChevron(x))));
    verifier('puis Newsreader revenue : le menu reprend sa largeur, sans aucune mesure du script, et le chevron reste à sa place',
      (await largeurEcp()) === lEcp && mApres.mesures.every(bonChevron), JSON.stringify(mApres.mesures.filter(x => !bonChevron(x))));
    verifier('plus de mesure au canevas : aucune largeur posée à la main sur le menu, la copie invisible porte le mot choisi',
      await p.evaluate(() => {
        const s = document.getElementById('dim-critique'), m = document.getElementById('dim-critique-mesure');
        return s.style.width === '' && m.textContent === s.options[s.selectedIndex].text && getComputedStyle(m).visibility === 'hidden' &&
               getComputedStyle(m).fontFamily === getComputedStyle(s).fontFamily && getComputedStyle(m).fontSize === getComputedStyle(s).fontSize;
      }));
    await p.selectOption('#dim-critique', 'ata'); await p.waitForTimeout(300);
    // Le cadre se cache avec le menu (sans dimension à proposer) : pas de blanc fantôme après « par ».
    const cache21 = await p.evaluate(() => {
      const s = document.getElementById('dim-critique'), c = document.getElementById('dim-critique-cadre');
      s.hidden = true; s.dispatchEvent(new Event('input'));
      const r = { cadre: getComputedStyle(c).display, largeur: c.getBoundingClientRect().width };
      s.hidden = false; s.dispatchEvent(new Event('input'));
      r.revenu = getComputedStyle(c).display !== 'none' && c.getBoundingClientRect().width > 20;
      return r;
    });
    verifier('menu caché (aucune dimension) : sa grille disparaît avec lui, sans blanc après « par » ; elle revient avec lui',
      cache21.cadre === 'none' && cache21.largeur === 0 && cache21.revenu, JSON.stringify(cache21));
    await p.waitForTimeout(300);

    // --- 3. Le titre et les panneaux, dans les deux thèmes. Débrief 22 : la
    //     bande d'encre du débrief 21 « faisait trop un bloc à part » — le
    //     titre se fond de nouveau dans la page, sans cadre, comme au débrief 20.
    const lireBandeau = pg => pg.evaluate(() => {
      function lum(c) {
        const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => {
          v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
      }
      const contraste = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
      const cs = el => getComputedStyle(el);
      /* Débrief 27 (lot H) : le bandeau du titre est dans l'en-tête de la page
         (header#entete, avec la barre des réglages) : c'est un div.masthead. */
      const mh = document.querySelector('header#entete .masthead'), h1 = mh.querySelector('h1'), sem = mh.querySelector('.semaine');
      const nav = document.getElementById('sommaire'), syn = document.getElementById('section-synthese');
      const rm = mh.getBoundingClientRect(), rn = nav.getBoundingClientRect(), rs = syn.getBoundingClientRect();
      const papier = cs(document.body).backgroundColor, surface = cs(document.getElementById('section-plans')).backgroundColor;
      const fond = cs(mh).backgroundColor;
      /* Débrief 28 : le titre est posé sur le bandeau d'encre marine de
         l'en-tête (peint d'un bord à l'autre par header.entete, son jeton
         --bandeau-fond), plus sur le papier : ses contrastes se mesurent
         contre lui. */
      const ent = document.querySelector('header.entete');
      const fondBandeau = (h => 'rgb(' + h.replace(/^#/, '').match(/../g).map(x => parseInt(x, 16)).join(', ') + ')')(cs(ent).getPropertyValue('--bandeau-fond').trim());
      const transparent = c => /rgba\(.*, 0\)$/.test(c) || c === 'transparent';
      const sansCadre = el => ['Top', 'Right', 'Bottom', 'Left'].every(c => parseFloat(cs(el)['border' + c + 'Width']) === 0) && cs(el).boxShadow === 'none';
      const centre = Math.abs((rm.left + rm.right) / 2 - (rs.left + rs.right) / 2) <= 2;
      const rt = document.createRange(); rt.selectNodeContents(h1);
      const rtitre = rt.getBoundingClientRect();
      const bandeau = {
        fond, papier, fondBandeau, fondus: transparent(fond) && sansCadre(mh) && cs(mh).borderRadius === '0px',
        peint: cs(ent).borderImageSource.indexOf(fondBandeau) !== -1 && ent.contains(mh) && fondBandeau !== papier,
        poids: +cs(h1).fontWeight, taille: parseFloat(cs(h1).fontSize), police: cs(h1).fontFamily.split(',')[0],
        cTitre: contraste(cs(h1).color, fondBandeau), cSemaine: contraste(cs(sem).color, fondBandeau),
        cSemaineB: contraste(cs(sem.querySelector('b')).color, fondBandeau),
        centre: centre && Math.abs((rtitre.left + rtitre.right) / 2 - (rs.left + rs.right) / 2) <= 3,
        sousTitre: rn.top >= rm.bottom - 12,
        navFond: cs(nav).backgroundColor === papier, navSansCadre: transparent(cs(nav).borderBottomColor) && parseFloat(cs(nav).borderTopWidth) === 0 &&
                 parseFloat(cs(nav).borderLeftWidth) === 0 && cs(nav).boxShadow === 'none' && cs(nav).borderBottomLeftRadius === '0px'
      };
      const ids = ['section-synthese', 'section-tendance', 'section-journal', 'section-repartition', 'section-plans', 'rapprochement'];
      const panneaux = ids.map(id => {
        const sec = document.getElementById(id), tete = sec.firstElementChild, r = sec.getBoundingClientRect(), rt = tete.getBoundingClientRect();
        const csec = cs(sec), ct = cs(tete);
        const titre = sec.querySelector('.panneau-tete h2, .panneau-tete .phrase'), sur = tete.querySelector('.surtitre');
        const numero = getComputedStyle(sur, '::before').color;
        return {
          id, tete: tete.classList.contains('panneau-tete') && !!sur && !!titre, fondTete: ct.backgroundColor, fond: csec.backgroundColor,
          pleineLargeur: Math.abs(rt.left - (r.left + parseFloat(csec.borderLeftWidth))) <= 1 && Math.abs(rt.right - (r.right - parseFloat(csec.borderRightWidth))) <= 1 &&
                         Math.abs(rt.top - (r.top + parseFloat(csec.borderTopWidth))) <= 1,
          filet: parseFloat(ct.borderBottomWidth) >= 1,
          /* Débrief 27 (D6) : le liseré passe de 3 à 2 px — avec le numéro et son
             trait, la seule trace de la teinte du panneau. */
          liseré: parseFloat(csec.borderTopWidth) === 2 && csec.borderTopColor === numero,
          cTitre: contraste(cs(titre).color, ct.backgroundColor), cNumero: contraste(numero, ct.backgroundColor),
          cSurtitre: contraste(cs(sur).color, ct.backgroundColor), ombre: csec.boxShadow !== 'none',
          haut: r.top, bas: r.bottom
        };
      });
      const ecarts = panneaux.slice(1).map((x, k) => Math.round(x.haut - panneaux[k].bas));
      return { bandeau, panneaux, ecarts, surface };
    });
    const verifierBandeau = (b, theme, largeur) => {
      const B = b.bandeau;
      /* Débrief 28 : le haut de page est un bandeau marine d'un bord à
         l'autre (plus « posé sur le papier ») ; le titre y reste sans fond ni
         cadre à lui, centré, en Newsreader, grand et lisible sur le bandeau. */
      verifier(theme + ', ' + largeur + ' px : « Suivi FWD » posé sur le bandeau marine de l’en-tête (débrief 28) — sans fond ni cadre à lui, centré au-dessus des panneaux, en Newsreader, grand et lisible',
        B.fondus && B.peint && B.centre && B.police === 'Newsreader' && B.taille >= (largeur < 720 ? 32 : 44) && B.cTitre >= 7 && B.cSemaine >= 4.5 && B.cSemaineB >= 4.5,
        JSON.stringify(B));
      verifier(theme + ', ' + largeur + ' px : le sommaire suit le titre, sur le papier, sans cadre autour — le bandeau marine s’arrête à l’en-tête (débrief 28)',
        B.sousTitre && B.navFond && B.navSansCadre, JSON.stringify(B));
      const P = b.panneaux;
      verifier(theme + ', ' + largeur + ' px : chaque panneau ouvre sur sa tête (surtitre et titre), d’un bord à l’autre, fermée d’un filet, sous un liseré de 2 px de sa teinte',
        P.every(x => x.tete && x.pleineLargeur && x.filet && x.liseré && x.fondTete !== x.fond && x.fond === b.surface),
        JSON.stringify(P.filter(x => !(x.tete && x.pleineLargeur && x.filet && x.liseré && x.fondTete !== x.fond))));
      /* Débrief 27 (D6) : six têtes teintées faisaient un patchwork avec les
         six couleurs d'état — une seule tête neutre pour tous les panneaux. */
      verifier(theme + ', ' + largeur + ' px : six têtes, une seule tête neutre (le même fond partout), et tout s’y lit (titre, numéro, surtitre à 4,5:1 au moins)',
        new Set(P.map(x => x.fondTete)).size === 1 && P.length === 6 && P.every(x => x.cTitre >= 4.5 && x.cNumero >= 4.5 && x.cSurtitre >= 4.5),
        JSON.stringify(P.map(x => x.id + ' ' + x.fondTete + ' ' + x.cTitre.toFixed(1) + '/' + x.cNumero.toFixed(1) + '/' + x.cSurtitre.toFixed(1))));
      verifier(theme + ', ' + largeur + ' px : un vrai blanc entre deux panneaux (' + (largeur < 720 ? 24 : 36) + ' px au moins), chacun avec son ombre',
        b.ecarts.every(e => e >= (largeur < 720 ? 24 : 36)) && P.every(x => x.ombre), JSON.stringify(b.ecarts));
    };
    await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(300);
    verifierBandeau(await lireBandeau(p), 'thème clair', 1280);
    await redimensionner(p, 390, 844);
    verifierBandeau(await lireBandeau(p), 'thème clair', 390);
    await redimensionner(p, 1280, 950);
    const ctxS21 = await contexte({ colorScheme: 'dark' });
    const ps21 = await page(ctxS21, 'bandeau sombre');
    verifierBandeau(await lireBandeau(ps21), 'thème sombre', 1280);
    for (const w of [360, 1440]) {
      await redimensionner(ps21, w, 900);
      const m = await mesurerChevrons(ps21);
      verifier('à ' + w + ' px, thème sombre : pour chaque dimension, le chevron est visible et le mot finit avant lui',
        m.mesures.every(bonChevron) && m.page, JSON.stringify(m.mesures.filter(x => !bonChevron(x))));
    }
    await ctxS21.close();
    // Collé en haut pendant qu'on lit : le sommaire, sur le papier, souligné d'un filet, devant les panneaux.
    // Le filet arrive en fondu (0,2 s) : on attend qu'il soit posé, pas un instant pris au milieu.
    await p.evaluate(() => window.scrollTo(0, document.getElementById('section-repartition').getBoundingClientRect().top + window.scrollY + 300));
    await p.waitForFunction(() => {
      const n = document.getElementById('sommaire');
      return n.dataset.colle === 'true' && /^rgb\(/.test(getComputedStyle(n).borderBottomColor);
    }, null, { timeout: 3000 }).catch(() => {});
    const colle21 = await p.evaluate(() => {
      const n = document.getElementById('sommaire'), r = n.getBoundingClientRect(), cs = getComputedStyle(n);
      return { colle: n.dataset.colle, haut: Math.round(r.top), fond: cs.backgroundColor === getComputedStyle(document.body).backgroundColor,
               filet: parseFloat(cs.borderBottomWidth) >= 1 && !/rgba\(.*, 0\)$/.test(cs.borderBottomColor), devant: +cs.zIndex > 0 };
    });
    verifier('en lisant plus bas, le sommaire reste collé en haut, sur le papier, souligné d’un filet, devant les panneaux',
      colle21.colle === 'true' && colle21.haut === 0 && colle21.fond && colle21.filet && colle21.devant, JSON.stringify(colle21));
    await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(300);
    await reinitialiser(p);

    /* L'autre flèche du débrief 21 : celle qui déplie chaque ligne du bloc.
       Centré dans sa colonne, « ECP-2100 » passait dessus, et en descendant
       la liste on ne la voyait plus. Le nom part maintenant après elle :
       pour chaque dimension, sur chaque ligne, le texte du nom ne touche
       jamais le chevron — à 1280 px, puis au téléphone où il passe à droite. */
    for (const w of [1280, 390]) {
      await redimensionner(p, w, 950);
      const chev = await p.evaluate(async () => {
        const attendre = ms => new Promise(r => setTimeout(r, ms));
        const sel = document.getElementById('dim-critique'), faux = [];
        let lignes = 0;
        for (const o of [...sel.options]) {
          sel.value = o.value; sel.dispatchEvent(new Event('change', { bubbles: true })); await attendre(250);
          document.querySelectorAll('#zone-critique .critique-ligne').forEach(l => {
            const c = l.querySelector('.chevron'), n = l.querySelector('.critique-nom');
            if (!c || !n || !n.firstChild) return;
            lignes++;
            const rg = document.createRange(); rg.selectNodeContents(n);
            const t = rg.getBoundingClientRect(), b = c.getBoundingClientRect();
            const touche = t.right > b.left - 2 && t.left < b.right + 2 && t.bottom > b.top && t.top < b.bottom;
            if (touche) faux.push(o.value + ' · ' + n.textContent);
          });
        }
        sel.value = sel.options[0].value; sel.dispatchEvent(new Event('change', { bubbles: true })); await attendre(200);
        return { lignes, faux: faux.slice(0, 6) };
      });
      verifier('à ' + w + ' px, dans chaque dimension (ATA, ECP…), le nom d’un groupe ne recouvre jamais le chevron qui le déplie',
        chev.lignes > 20 && !chev.faux.length, JSON.stringify(chev));
    }
    await p.setViewportSize({ width: 1280, height: 950 });
    await reinitialiser(p);
  }

  section('Débrief 21 : relecture');
  /* Un classeur vide, à l'écran puis imprimé : le titre reste posé sur la
     page, sans filet ni coins arrondis dessous (débrief 22 : plus de bande
     de titre, donc plus rien à refermer quand le sommaire n'est pas là). */
  {
    const ctxImp = await contexte();
    await ctxImp.addInitScript(() => {
      window.SUIVI_FWD_DONNEES = { ok: false, message: 'Feuille vide : aucun plan.', colonnes: [], plans: [], releves: [], jalons: [], contrats: [], contrat: '' };
    });
    const pi = await page(ctxImp, 'classeur vide imprimé');
    const cadre = () => pi.evaluate(() => {
      const st = getComputedStyle(document.querySelector('.masthead'));
      return { vide: document.body.dataset.vide, bas: st.borderBottomWidth + ' ' + st.borderBottomStyle, rayon: st.borderBottomLeftRadius };
    });
    const ecran = await cadre();
    await pi.emulateMedia({ media: 'print' });
    const papier = await cadre();
    verifier('classeur vide : à l’écran comme à l’impression, ni filet ni coins arrondis sous « Suivi FWD »',
      ecran.vide === 'true' && /^0px|none/.test(ecran.bas) && ecran.rayon === '0px' && /^0px|none/.test(papier.bas) && papier.rayon === '0px',
      JSON.stringify([ecran, papier]));
    await ctxImp.close();
  }

  // =================================================================
  section('Couleurs des valeurs (débrief 22)');
  /* Débrief 22 : « dans synthèse, les couleurs sont trop proches du orange.
     Je voudrais des couleurs variées, différentes. » Chaque valeur de la
     colonne suivie a maintenant SA couleur, et elle suit le mot, jamais son
     compte : vert pour les validés ; bleu, framboise, turquoise pour les en
     cours (PWD_IN_PROGRESS, PWD_TO_CONTROL, TO_CONFIRM) ; deux gris pour les
     à faire ; hachures pour « Non renseigné » — plus d'ambre dans les
     données. On injecte dans la démonstration le vrai vocabulaire GATES,
     avec la configuration de Code.gs (VALEURS_FINIES, VALEURS_A_FAIRE) et
     les comptes de HDK, puis de THS, et on vérifie tout dans les deux
     thèmes, sur des pages à part : la page principale ne bouge pas. Les
     lettres (a) à (m) renvoient à la spécification du débrief 22, (n) à
     (r) aux constats de sa relecture : un mot d'hier ne prend pas la
     couleur d'un mot du jour ; infobulles des barres par ATA ; bulle de
     la comparaison SEE par valeur ; liseré de la pastille « avant ». */
  {
    const erreursAvant22 = erreursJS.length;
    /* Les mots se répartissent sur les plans de la démonstration dans les
       proportions données, sans hasard (un pas de 37) : les mêmes plans
       reçoivent les mêmes mots à chaque passage. */
    const injecter22 = ({ mots, config }) => {
      const s = window.__jeuDExemple('HDK');
      if (config) { s.valeursFinies = ['Validé', 'VALIDATED', 'Traité']; s.valeursAFaire = ['TO_TREAT', 'FWD_TO_SEIZE']; }
      const total = mots.reduce((t, m) => t + m[1], 0);
      s.plans.forEach((x, i) => { let k = (i * 37) % total, j = 0; while (k >= mots[j][1]) { k -= mots[j][1]; j++; } x.avancement = mots[j][0]; });
      window.__chargerSource(s);
      return window.__valeurs();
    };
    /* Ce que l'œil voit : la pastille de chaque tuile, les fonds de la barre
       du haut dans l'ordre, et le contraste de l'encre sur chaque segment
       peint de la barre du haut et des barres par ATA. */
    const mesurer22 = () => {
      function rgb(c) { return c.match(/[\d.]+/g).map(Number).slice(0, 3); }
      function lum(c) { return rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }).reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0); }
      function contraste(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
      const segs = [...document.querySelectorAll('#barre span:not(.hachure)')];
      const ata = [...document.querySelectorAll('.critique-barre span:not(.hachure)')];
      const tuiles = {};
      document.querySelectorAll('#etats .etat-btn').forEach(b => {
        const p = b.querySelector('.pastille');
        tuiles[b.dataset.cle] = p.classList.contains('hachure') ? 'hachure' : getComputedStyle(p).backgroundColor;
      });
      const fonds = segs.map(s => getComputedStyle(s).backgroundColor);
      return {
        tuiles, fonds,
        voisinsEgaux: fonds.some((f, i) => i && f === fonds[i - 1]),
        encres: segs.concat(ata).map(s => ({ cle: s.dataset.cle, c: contraste(getComputedStyle(s).color, getComputedStyle(s).backgroundColor) })),
        ordre: [...document.querySelectorAll('#barre span')].map(s => s.dataset.cle).join(',')
      };
    };
    const encresFaibles = m => m.encres.filter(e => !(e.c >= 4.5)).map(e => e.cle + ' ' + e.c.toFixed(2));
    const GATES_HDK = [['VALIDATED', 54], ['PWD_IN_PROGRESS', 238], ['PWD_TO_CONTROL', 6], ['TO_CONFIRM', 4], ['FWD_TO_SEIZE', 3], ['TO_TREAT', 1], ['', 328]];
    const GATES_THS = [['VALIDATED', 21], ['PWD_IN_PROGRESS', 64], ['PWD_TO_CONTROL', 3], ['TO_CONFIRM', 2], ['FWD_TO_SEIZE', 4], ['TO_TREAT', 6], ['', 80]];
    const GATES_ECHANGES = [['VALIDATED', 54], ['PWD_IN_PROGRESS', 4], ['PWD_TO_CONTROL', 238], ['TO_CONFIRM', 6], ['FWD_TO_SEIZE', 1], ['TO_TREAT', 3], ['', 328]];
    const DOUZE = [['VALIDATED', 9], ['Validé', 6], ['PWD_IN_PROGRESS', 14], ['PWD_TO_CONTROL', 9], ['TO_CONFIRM', 8], ['ON_HOLD', 7], ['PWD_REJECTED', 7],
      ['TO_MODIFY', 7], ['FWD_TO_SEIZE', 8], ['TO_TREAT', 7], ['À faire', 7], ['', 11]];
    /* Assez de PWD_TO_CONTROL et de TO_CONFIRM pour qu'ils tombent dans les
       lots de la comparaison SEE de la démonstration. */
    const GATES_SEE = [['VALIDATED', 254], ['PWD_IN_PROGRESS', 120], ['PWD_TO_CONTROL', 40], ['TO_CONFIRM', 30], ['FWD_TO_SEIZE', 50], ['TO_TREAT', 40], ['', 106]];
    /* Les mots d'hier et ceux du jour : les mots de la démonstration
       (« Terminé », « En cours », « À faire ») deviennent ceux de
       « aujourdhui » dans l'extract et le dernier relevé, ceux de « avant »
       dans les relevés d'avant — un mot peut ainsi n'exister qu'hier. */
    const injecterHier22 = ({ aujourdhui, avant }) => {
      const s = window.__jeuDExemple('HDK');
      s.valeursFinies = ['Validé', 'VALIDATED', 'Traité']; s.valeursAFaire = ['TO_TREAT', 'FWD_TO_SEIZE'];
      const m = (t, v) => (Object.prototype.hasOwnProperty.call(t, v) ? t[v] : v);
      s.plans.forEach(x => { x.avancement = m(aujourdhui, x.avancement); });
      s.releves.forEach((r, i) => {
        const t = i === s.releves.length - 1 ? aujourdhui : avant;
        Object.keys(r.plans).forEach(ref => { r.plans[ref] = m(t, r.plans[ref]); });
      });
      window.__chargerSource(s);
    };
    /* Un plan passé d'un mot (« avant », absent du jour) à un autre
       (« apres ») : les pastilles des deux mots dans les pilules de la
       tendance et du journal, sur sa ligne du journal, et les bandes de sa
       frise (fiche ouverte d'un clic sur la ligne). */
    const passage22 = async ({ avant, apres, cles }) => {
      const attendre = ms => new Promise(r => setTimeout(r, ms));
      const fond = e => e ? getComputedStyle(e).backgroundColor : null;
      const r = {
        tendance: cles.map(k => fond(document.querySelector('#filtre-valeur-graphe button[data-valeur-graphe="' + k + '"] .pastille'))),
        pilules: cles.map(k => fond(document.querySelector('#filtre-journal button[data-journal="' + k + '"] .pastille'))),
        ligne: null, frise: null
      };
      const pil = document.querySelector('#filtre-journal button[data-journal="' + cles[1] + '"]');
      if (pil) { pil.click(); await attendre(250); }
      const sem = document.querySelector('#zone-journal .journal-plier[aria-expanded="false"]');
      if (sem) { sem.click(); await attendre(250); }
      const l = [...document.querySelectorAll('#zone-journal .journal-ligne')].find(x =>
        (x.querySelector('.etiq-etat.avant') || {}).textContent === avant && (x.querySelector('.etiq-etat.apres') || {}).textContent === apres);
      if (!l) return r;
      r.ligne = [fond(l.querySelector('.etiq-etat.avant .pastille')), fond(l.querySelector('.etiq-etat.apres .pastille'))];
      l.click(); await attendre(500);
      const bandes = m => [...new Set([...document.querySelectorAll('#fiche-plan .fiche-plan-frise .case')]
        .filter(c => c.title.endsWith(' : ' + m)).map(c => fond(c.querySelector('.bande'))))];
      r.frise = [bandes(avant), bandes(apres)];
      return r;
    };
    /* Deux couleurs différentes à chaque endroit, une seule par mot. */
    const distincts22 = r => ['tendance', 'pilules', 'ligne'].every(c => r[c] && r[c][0] && r[c][1] && r[c][0] !== r[c][1]) &&
      !!r.frise && r.frise[0].length === 1 && r.frise[1].length === 1 && r.frise[0][0] !== r.frise[1][0];

    for (const [theme, nom] of [['light', 'en clair'], ['dark', 'en sombre']]) {
      const ctx22 = await contexte({ colorScheme: theme });
      const pc = await page(ctx22, 'couleurs ' + theme);

      // (a) La couleur suit le mot : ni son compte, ni le contrat n'y changent rien.
      await pc.evaluate(injecter22, { mots: GATES_HDK, config: true }); await pc.waitForTimeout(400);
      const hdk = await pc.evaluate(mesurer22);
      await pc.evaluate(injecter22, { mots: GATES_THS, config: true }); await pc.waitForTimeout(400);
      const ths = await pc.evaluate(mesurer22);
      verifier(nom + ' : chaque mot GATES garde sa couleur, avec les comptes de HDK comme avec ceux de THS',
        JSON.stringify(hdk.tuiles) === JSON.stringify(ths.tuiles), JSON.stringify([hdk.tuiles, ths.tuiles]));
      verifier(nom + ' : et le même ordre de barre — FWD_TO_SEIZE avant TO_TREAT, même quand TO_TREAT est plus nombreux',
        hdk.ordre === ths.ordre && hdk.ordre === 'validated,pwd_in_progress,pwd_to_control,to_confirm,fwd_to_seize,to_treat,vide', hdk.ordre + ' / ' + ths.ordre);
      await pc.evaluate(injecter22, { mots: GATES_ECHANGES, config: true }); await pc.waitForTimeout(400);
      const ech22 = await pc.evaluate(mesurer22);
      verifier(nom + ' : comptes échangés (238 PWD_TO_CONTROL, 4 PWD_IN_PROGRESS) : aucune tuile ne change de couleur',
        JSON.stringify(ech22.tuiles) === JSON.stringify(hdk.tuiles), JSON.stringify(ech22.tuiles));

      // (h) Le vocabulaire GATES : six aplats distincts, des pourcentages lisibles.
      await pc.evaluate(injecter22, { mots: GATES_HDK, config: true }); await pc.waitForTimeout(400);
      const g = await pc.evaluate(mesurer22);
      const pleines = Object.values(g.tuiles).filter(c => c !== 'hachure');
      verifier(nom + ' : vocabulaire GATES : six aplats distincts, plus la hachure de « Non renseigné »',
        pleines.length === 6 && new Set(pleines).size === 6 && Object.values(g.tuiles).filter(c => c === 'hachure').length === 1, JSON.stringify(g.tuiles));
      verifier(nom + ' : chaque pourcentage écrit dans un aplat (barre du haut, barres par ATA) dépasse 4,5:1 — l’encre est mesurée sur chaque segment peint',
        g.encres.length > 0 && !encresFaibles(g).length, JSON.stringify(encresFaibles(g)));

      // (c) Aucune couleur de valeur n'imite une couleur réservée.
      const reserve = await pc.evaluate(() => {
        const t = document.createElement('i'); document.body.appendChild(t);
        const val = n => { t.style.background = 'var(' + n + ')'; return getComputedStyle(t).backgroundColor; };
        const r = { cours: val('--cours'), alerte: val('--alerte'), indice: val('--indice') };
        t.remove(); return r;
      });
      verifier(nom + ' : aucun fond de valeur ne reprend l’ambre de « à l’arrêt » (--cours), le rouge d’alerte ni le violet d’indice',
        pleines.every(c => c !== reserve.cours && c !== reserve.alerte && c !== reserve.indice), JSON.stringify([reserve, pleines]));

      // (b) Plus de color-mix ni d'ambre dans les marques de valeur.
      const styles = await pc.evaluate(() => [...document.querySelectorAll('#barre span, #etats .pastille, #etats .etat-btn, .critique-barre span, .mini-jauge span, ' +
        '[data-valeur-graphe] .pastille, [data-valeur-bloc] .pastille, [data-journal] .pastille')]
        .map(e => e.getAttribute('style') || '').filter(s => /color-mix\(|var\(--cours\)|var\(--afaire\)/.test(s)));
      verifier(nom + ' : plus aucun color-mix(, var(--cours) ni var(--afaire) dans le style d’une marque de valeur',
        styles.length === 0, styles.slice(0, 3).join(' | '));

      // (l) Barres par ATA sans valeur choisie et mini-jauge du journal : découpées par valeur, aux couleurs des tuiles.
      const decoupe = await pc.evaluate(() => {
        const fond = e => e && getComputedStyle(e).backgroundColor;
        const tuile = k => fond(document.querySelector('#etats .etat-btn[data-cle="' + k + '"] .pastille'));
        const pilule = k => fond(document.querySelector('#filtre-journal button[data-journal="' + k + '"] .pastille'));
        const famille = {}; window.__valeurs().forEach(v => { famille[v.cle] = v.famille; });
        const cles = boite => [...boite.querySelectorAll('span[data-cle]')].map(s => s.dataset.cle);
        const doublon = boite => { const c = cles(boite); return new Set(c).size !== c.length; };
        const segs = [...document.querySelectorAll('.critique-barre span:not(.hachure)')];
        const jauges = [...document.querySelectorAll('.mini-jauge')];
        const jauge = [...document.querySelectorAll('.mini-jauge span[data-cle]')];
        return {
          segments: segs.length,
          ata: segs.length > 0 && segs.every(s => s.dataset.cle && fond(s) === tuile(s.dataset.cle)),
          ptc: segs.some(s => s.dataset.cle === 'pwd_to_control'),
          doublonsAta: [...document.querySelectorAll('.critique-barre')].filter(doublon).length,
          morceaux: jauge.length,
          jauge: jauge.length > 0 && jauge.every(s => !!pilule(s.dataset.cle) && fond(s) === pilule(s.dataset.cle)),
          sansPilule: jauge.filter(s => !pilule(s.dataset.cle)).map(s => s.dataset.cle),
          doublonsJauge: jauges.filter(doublon).length,
          // Trois mots « en cours » arrivés la même semaine : trois morceaux, plus un seul bleu.
          enCoursSepares: jauges.some(j => new Set(cles(j).filter(k => famille[k] === 'encours')).size >= 2)
        };
      });
      verifier(nom + ' : barres par ATA sans valeur choisie : un segment par valeur, à la couleur de sa tuile (PWD_TO_CONTROL compris)',
        decoupe.ata && decoupe.ptc && decoupe.doublonsAta === 0, JSON.stringify(decoupe));
      verifier(nom + ' : mini-jauge du journal : un segment par valeur d’arrivée, à la couleur de sa pilule',
        decoupe.jauge && decoupe.doublonsJauge === 0 && decoupe.enCoursSepares, JSON.stringify(decoupe));

      // (f) La pastille de la cellule du tableau est celle de la tuile.
      const cellules = await pc.evaluate(() => {
        const valeurs = window.__valeurs();
        let n = 0, justes = 0;
        const orphelines = [];
        document.querySelectorAll('#corps-tableau .etat-cellule').forEach(c => {
          const p = c.querySelector('.pastille'), mot = ((c.querySelector('.num') || {}).textContent || '').trim();
          if (!mot || p.classList.contains('hachure')) return;
          const v = valeurs.find(x => x.libelle === mot);
          const t = v && document.querySelector('#etats .etat-btn[data-cle="' + v.cle + '"] .pastille');
          if (!t) { orphelines.push(mot); return; }
          n++;
          if (getComputedStyle(p).backgroundColor === getComputedStyle(t).backgroundColor) justes++;
        });
        return { n, justes, orphelines: orphelines.slice(0, 5) };
      });
      verifier(nom + ' : la pastille de chaque cellule de la colonne suivie a la couleur de sa tuile',
        cellules.n > 0 && cellules.justes === cellules.n && !cellules.orphelines.length, JSON.stringify(cellules));

      // (d) Deux mots pour la première place des validés : l'ordre alphabétique décide, jamais les comptes.
      const deux = await pc.evaluate(injecter22, { mots: [['Validé', 60], ['VALIDATED', 5], ['PWD_IN_PROGRESS', 50], ['', 20]], config: true });
      const vd = deux.find(v => v.cle === 'validated'), ve = deux.find(v => v.cle === 'valide');
      verifier(nom + ' : VALIDATED et Validé ensemble : VALIDATED garde le vert --fait, Validé prend --v-fait-2, même douze fois moins nombreux',
        !!vd && !!ve && vd.couleur === 'var(--fait)' && ve.couleur === 'var(--v-fait-2)', JSON.stringify(deux));

      // (g) Garde de famille : VALIDATED compté « en cours » (démonstration sans configuration) ne vole pas la place de PWD_IN_PROGRESS.
      const garde = await pc.evaluate(injecter22, { mots: [['VALIDATED', 30], ['PWD_IN_PROGRESS', 50], ['Terminé', 10], ['', 20]], config: false });
      const gv = garde.find(v => v.cle === 'validated'), gp = garde.find(v => v.cle === 'pwd_in_progress');
      verifier(nom + ' : un mot connu rangé dans une autre famille (VALIDATED sans configuration, donc « en cours ») ne prend la place d’aucun autre',
        !!gv && !!gp && gv.famille === 'encours' && gp.place === 0 && gp.couleur === 'var(--v-cours-1)' && gv.place !== 0, JSON.stringify(garde));

      // (i) Douze valeurs : 2 validés, 6 en cours (dont trois mots inconnus), 3 à faire.
      await pc.evaluate(injecter22, { mots: DOUZE, config: true }); await pc.waitForTimeout(400);
      const douze = await pc.evaluate(mesurer22);
      verifier(nom + ' : douze valeurs (2 validés, 6 en cours, 3 à faire) : chaque pourcentage dépasse 4,5:1',
        douze.encres.length > 0 && !encresFaibles(douze).length, JSON.stringify(encresFaibles(douze)));
      verifier(nom + ' : douze valeurs : deux segments voisins n’ont jamais la même couleur',
        !douze.voisinsEgaux, douze.fonds.join(' '));
      verifier(nom + ' : douze valeurs : l’ordre suit les places — les mots connus à la leur, les inconnus dans l’ordre alphabétique',
        douze.ordre === 'validated,valide,pwd_in_progress,pwd_to_control,to_confirm,on_hold,pwd_rejected,to_modify,afaire,fwd_to_seize,to_treat,vide', douze.ordre);

      // (m) La courbe « Non renseigné » se trace en tirets, comme sa hachure ; celle d'une autre valeur reste pleine.
      await pc.evaluate(injecter22, { mots: GATES_HDK, config: true }); await pc.waitForTimeout(400);
      const tirets = await pc.evaluate(async () => {
        const attendre = ms => new Promise(r => setTimeout(r, ms));
        const lire = async k => {
          const b = document.querySelector('#filtre-valeur-graphe button[data-valeur-graphe="' + k + '"]');
          if (!b) return ['pas de pilule ' + k];
          b.click(); await attendre(250);
          const c = document.querySelector('svg.graphe path.courbe'), l = document.querySelector('#legende .legende-item svg line');
          return [c ? c.getAttribute('stroke-dasharray') : 'pas de courbe', l ? l.getAttribute('stroke-dasharray') : 'pas de légende'];
        };
        const r = { vide: await lire('vide'), pwd_in_progress: await lire('pwd_in_progress') };
        const tout = document.querySelector('#filtre-valeur-graphe button[data-valeur-graphe=""]');
        if (tout) { tout.click(); await attendre(250); }
        return r;
      });
      verifier(nom + ' : la courbe « Non renseigné » se trace en tirets, sa ligne de légende aussi ; celle de PWD_IN_PROGRESS reste pleine',
        tirets.vide[0] === '6 4' && tirets.vide[1] === '6 4' && tirets.pwd_in_progress[0] === null && tirets.pwd_in_progress[1] === null, JSON.stringify(tirets));

      // (n) Un mot absent du jour ne prend pas la couleur d'un mot présent : PWD_IN_PROGRESS d'hier, ON_HOLD (mot inconnu) aujourd'hui.
      const surPageNeuve22 = async (etiquette, f) => {
        const cx = await contexte({ colorScheme: theme });
        const pg = await page(cx, 'couleurs ' + theme + ' ' + etiquette);
        const r = await f(pg);
        await cx.close();
        return r;
      };
      const hierN = await surPageNeuve22('hier-n', async pg => {
        await pg.evaluate(injecterHier22, { aujourdhui: { 'Terminé': 'VALIDATED', 'En cours': 'ON_HOLD', 'À faire': 'FWD_TO_SEIZE' },
          avant: { 'Terminé': 'VALIDATED', 'En cours': 'PWD_IN_PROGRESS', 'À faire': 'FWD_TO_SEIZE' } });
        await pg.waitForTimeout(400);
        return pg.evaluate(passage22, { avant: 'PWD_IN_PROGRESS', apres: 'ON_HOLD', cles: ['pwd_in_progress', 'on_hold'] });
      });
      verifier(nom + ' : PWD_IN_PROGRESS d’hier et ON_HOLD du jour ont deux couleurs — pilules de la tendance et du journal, ligne « PWD_IN_PROGRESS → ON_HOLD », frise du plan',
        distincts22(hierN), JSON.stringify(hierN));
      const hierB = await surPageNeuve22('hier-b', async pg => {
        await pg.evaluate(injecterHier22, { aujourdhui: { 'Terminé': 'VALIDATED', 'En cours': 'PWD_IN_PROGRESS', 'À faire': 'FWD_TO_SEIZE' },
          avant: { 'Terminé': 'Validé', 'En cours': 'PWD_IN_PROGRESS', 'À faire': 'FWD_TO_SEIZE' } });
        await pg.waitForTimeout(400);
        return pg.evaluate(passage22, { avant: 'Validé', apres: 'VALIDATED', cles: ['valide', 'validated'] });
      });
      verifier(nom + ' : « Validé » d’hier n’a pas le vert de VALIDATED du jour, nulle part',
        distincts22(hierB), JSON.stringify(hierB));

      // (o) FWD_TO_SEIZE tombé à zéro et TO_TREAT encore là : deux gris, jusque dans la frise.
      const hierO = await surPageNeuve22('hier-o', async pg => {
        await pg.evaluate(injecterHier22, { aujourdhui: { 'Terminé': 'VALIDATED', 'En cours': 'PWD_IN_PROGRESS', 'À faire': 'TO_TREAT' },
          avant: { 'Terminé': 'VALIDATED', 'En cours': 'PWD_IN_PROGRESS', 'À faire': 'FWD_TO_SEIZE' } });
        await pg.waitForTimeout(400);
        return pg.evaluate(passage22, { avant: 'FWD_TO_SEIZE', apres: 'TO_TREAT', cles: ['fwd_to_seize', 'to_treat'] });
      });
      verifier(nom + ' : FWD_TO_SEIZE d’hier et TO_TREAT du jour : deux gris dans les pilules, sur la ligne du journal et dans les bandes de la frise',
        distincts22(hierO), JSON.stringify(hierO));

      // (s) La pilule de la courbe par défaut (sans clé) porte la pastille de sa tuile : le vert de VALIDATED,
      //     pas une place « libre » de sa famille ; et chaque pilule du jour a la pastille de sa tuile.
      const defautS = await surPageNeuve22('defaut-s', async pg => {
        const tout = { 'Terminé': 'VALIDATED', 'En cours': 'PWD_IN_PROGRESS', 'À faire': 'FWD_TO_SEIZE' };
        await pg.evaluate(injecterHier22, { aujourdhui: tout, avant: tout });
        await pg.waitForTimeout(400);
        return pg.evaluate(() => {
          const fond = e => e ? getComputedStyle(e).backgroundColor : null;
          const tuile = k => fond(document.querySelector('#etats .etat-btn[data-cle="' + k + '"] .pastille'));
          const defaut = document.querySelector('#filtre-valeur-graphe button[data-valeur-graphe=""]');
          const autres = [...document.querySelectorAll('#filtre-valeur-graphe button[data-valeur-graphe]')]
            .filter(b => b.dataset.valeurGraphe && document.querySelector('#etats .etat-btn[data-cle="' + b.dataset.valeurGraphe + '"]'))
            .map(b => ({ k: b.dataset.valeurGraphe, pilule: fond(b.querySelector('.pastille:not(.hachure)')), tuile: tuile(b.dataset.valeurGraphe) }))
            .filter(x => x.pilule);
          return { texte: defaut && defaut.textContent.trim(), defaut: fond(defaut && defaut.querySelector('.pastille')), validated: tuile('validated'), autres };
        });
      });
      verifier(nom + ' : la pilule de la courbe par défaut, « VALIDATED », a le vert de sa tuile, et chaque pilule du jour la pastille de sa tuile',
        defautS.texte === 'VALIDATED' && !!defautS.defaut && defautS.defaut === defautS.validated && defautS.autres.length >= 2 &&
        defautS.autres.every(x => x.pilule === x.tuile), JSON.stringify(defautS));

      // (p) Barres par ATA : chaque segment dit sa valeur et son compte au survol ; l'infobulle de la ligne reprend la barre valeur par valeur.
      const ata22 = await pc.evaluate(() => {
        const libelle = {}; window.__valeurs().forEach(v => { libelle[v.cle] = v.libelle; });
        const chiffre = t => Number(String(t).replace(/[\s  ]/g, ''));
        const fautes = [];
        let segments = 0;
        document.querySelectorAll('.critique-ligne').forEach(l => {
          const segs = [...l.querySelectorAll('.critique-barre span[data-cle]')];
          let somme = 0, total = null;
          segs.forEach(s => {
            segments++;
            const m = (s.getAttribute('title') || '').match(/^(.+) : ([\d\s  ]+) sur ([\d\s  ]+)$/);
            if (!m || m[1] !== libelle[s.dataset.cle]) { fautes.push(l.dataset.groupe + ' ' + s.dataset.cle + ' title=' + JSON.stringify(s.getAttribute('title'))); return; }
            const n = chiffre(m[2]), t = chiffre(m[3]);
            somme += n; total = total === null ? t : total;
            const pct = Math.round(100 * n / t);
            /* Débrief 27 (lot C, X-A6) : la ligne se dit en une phrase (masquée à
               l'œil) au lieu d'une infobulle : elle redit chaque part, à côté de son mot. */
            const phrase = (l.querySelector('.masque') || { textContent: '' }).textContent;
            if (t !== total || phrase.indexOf(m[2] + ' ' + m[1] + ' (' + pct + ' %)') < 0) fautes.push(l.dataset.groupe + ' ligne=' + JSON.stringify(phrase));
            const ecrit = s.textContent.replace(/[\s %]/g, '');
            if (ecrit && Number(ecrit) !== pct) fautes.push(l.dataset.groupe + ' ' + s.dataset.cle + ' écrit ' + s.textContent + ' / ' + pct);
          });
          if (segs.length && somme !== total) fautes.push(l.dataset.groupe + ' somme ' + somme + ' / ' + total);
        });
        return { segments, fautes: fautes.slice(0, 4) };
      });
      verifier(nom + ' : barres par ATA : chaque segment a pour infobulle « valeur : n sur total », et la phrase de la ligne (lecteur d’écran) redit chaque part, à côté de son mot',
        ata22.segments > 0 && !ata22.fautes.length, JSON.stringify(ata22));

      // (q) La bulle d'un verdict SEE répartit le lot valeur par valeur, chaque pastille à la couleur de sa tuile.
      await pc.evaluate(injecter22, { mots: GATES_SEE, config: true }); await pc.waitForTimeout(600);
      const bulles22 = {};
      for (const lot of ['avance', 'attente']) {
        await pc.evaluate(() => document.getElementById('rapprochement').scrollIntoView({ block: 'center' })); await pc.waitForTimeout(200);
        await (await pc.$('#verdicts-rapprochement button[data-rapp="' + lot + '"]')).hover(); await pc.waitForTimeout(300);
        bulles22[lot] = await pc.evaluate(() => {
          const fond = e => e.classList.contains('hachure') ? 'hachure' : getComputedStyle(e).backgroundColor;
          const tuile = {}, libelle = {};
          document.querySelectorAll('#etats .etat-btn').forEach(b => { tuile[b.dataset.cle] = fond(b.querySelector('.pastille')); });
          window.__valeurs().forEach(v => { libelle[v.libelle + ' dans GATES'] = v.cle; });
          const lignes = [...document.querySelectorAll('#bulle .bulle-comptes .bulle-ligne')].map(l => {
            const n = l.querySelector('.n').textContent, mot = l.textContent.slice(0, -n.length).trim();
            const cle = libelle[mot];
            return { mot, n: Number(n.replace(/[\s  ]/g, '')), cle, fond: fond(l.querySelector('.pastille')), tuile: cle ? tuile[cle] : null };
          });
          const tete = ((document.querySelector('#bulle .tete-bulle') || {}).textContent || '').match(/^[\d\s  ]+/);
          return { tete: tete ? Number(tete[0].replace(/[\s  ]/g, '')) : null, lignes };
        });
        await pc.mouse.move(2, 2); await pc.waitForTimeout(150);
      }
      const bulleJuste = b => b.lignes.length >= 4 && b.lignes.every(l => l.cle && l.fond === l.tuile) &&
        ['pwd_in_progress', 'pwd_to_control', 'to_confirm'].every(k => b.lignes.some(l => l.cle === k)) &&
        b.lignes.reduce((t, l) => t + l.n, 0) === b.tete;
      verifier(nom + ' : bulles « dans SEE, mais GATES ne les dit pas validés » et « pas encore dans SEE » : une ligne par valeur (PWD_IN_PROGRESS, PWD_TO_CONTROL, TO_CONFIRM séparés), chaque pastille à la couleur de sa tuile, le compte du lot au total',
        bulleJuste(bulles22.avance) && bulleJuste(bulles22.attente), JSON.stringify(bulles22));

      // (r) La pastille « avant » du journal : pâle, mais son liseré se voit (3:1 sur le fond), même sur le gris de FWD_TO_SEIZE.
      const avant22 = await (async () => {
        const cx = await contexte({ colorScheme: theme, deviceScaleFactor: 4 });
        const pg = await page(cx, 'couleurs ' + theme + ' avant');
        await pg.evaluate(injecterHier22, { aujourdhui: { 'Terminé': 'VALIDATED', 'En cours': 'PWD_IN_PROGRESS', 'À faire': 'FWD_TO_SEIZE' },
          avant: { 'Terminé': 'VALIDATED', 'En cours': 'PWD_IN_PROGRESS', 'À faire': 'FWD_TO_SEIZE' } });
        await pg.waitForTimeout(400);
        // Toutes les semaines dépliées ; une pastille « avant » par couleur.
        const cibles = await pg.evaluate(() => {
          document.querySelectorAll('#zone-journal .journal-plier[aria-expanded="false"]').forEach(b => b.click());
          const vus = {}, r = [];
          document.querySelectorAll('#zone-journal .journal-ligne .etiq-etat.avant .pastille').forEach((p, i) => {
            const hachure = p.classList.contains('hachure'), k = hachure ? 'hachure' : getComputedStyle(p).backgroundColor;
            if (vus[k]) return;
            vus[k] = true; p.setAttribute('data-avant22', i);
            r.push({ i, hachure, couleur: k, mot: p.parentElement.textContent.trim() });
          });
          return r;
        });
        await pg.mouse.move(2, 2);
        const mesures = [];
        for (const c of cibles) {
          const el = await pg.$('[data-avant22="' + c.i + '"]');
          await el.scrollIntoViewIfNeeded();
          const bb = await el.boundingBox();
          const png = await pg.screenshot({ clip: { x: bb.x - 4, y: bb.y - 2, width: bb.width + 8, height: bb.height + 4 } });
          /* Les pixels lus dans la capture (×4) : le fond à gauche de la
             pastille, le milieu de son liseré gauche, son centre. */
          const px = await pg.evaluate(async ({ b64, w, h }) => {
            const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
            const cv = document.createElement('canvas'); cv.width = img.width; cv.height = img.height;
            const g = cv.getContext('2d'); g.drawImage(img, 0, 0);
            const lire = (x, y) => Array.from(g.getImageData(Math.round(x * 4), Math.round(y * 4), 1, 1).data).slice(0, 3);
            return { fond: lire(1.5, 2 + h / 2), lisere: lire(4.5, 2 + h / 2), centre: lire(4 + w / 2, 2 + h / 2) };
          }, { b64: png.toString('base64'), w: bb.width, h: bb.height });
          mesures.push(Object.assign({ mot: c.mot, couleur: c.couleur, hachure: c.hachure }, px));
        }
        await cx.close();
        return mesures;
      })();
      const lumPx = c => c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }).reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
      const contrastePx = (a, b) => { const x = lumPx(a), y = lumPx(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
      const avantFaibles = avant22.filter(m => !(contrastePx(m.lisere, m.fond) >= 3)).map(m => m.mot + ' liseré ' + m.lisere + ' sur ' + m.fond + ' ' + contrastePx(m.lisere, m.fond).toFixed(2));
      verifier(nom + ' : journal : le liseré de chaque pastille « avant » se voit à 3:1 au moins sur le fond — FWD_TO_SEIZE compris',
        avant22.some(m => m.mot === 'FWD_TO_SEIZE') && !avantFaibles.length, JSON.stringify({ avantFaibles, mots: avant22.map(m => m.mot) }));
      /* Et la pastille reste aussi pâle qu'au débrief 22 : sa couleur à 40 %
         sur le fond (à 3 près par canal). Débrief 26 : à 60 % en sombre —
         mêlée au noir, à 40 % elle perdait sa teinte (marine, prune, brun). */
      const part = /sombre/i.test(nom) ? 0.6 : 0.4;
      const avantPales = avant22.filter(m => !m.hachure).filter(m => {
        const c = m.couleur.match(/[\d.]+/g).map(Number);
        return m.centre.some((v, i) => Math.abs(v - (part * c[i] + (1 - part) * m.fond[i])) > 3);
      }).map(m => m.mot + ' centre ' + m.centre + ' couleur ' + m.couleur + ' fond ' + m.fond);
      verifier(nom + ' : journal : la pastille « avant » reste pâle — sa couleur à ' + Math.round(part * 100) + ' % sur le fond',
        avant22.length > 1 && !avantPales.length, JSON.stringify(avantPales));
      await ctx22.close();
    }

    // (j) Les deux blocs sombres (système sombre, data-theme="dark") déclarent les mêmes jetons, et pas ceux du clair.
    {
      const ctxJ = await contexte({ colorScheme: 'light' });
      const pj = await page(ctxJ, 'couleurs jetons');
      const jetons = () => pj.evaluate(() => {
        const cs = getComputedStyle(document.documentElement);
        return ['fait-2', 'cours-1', 'cours-2', 'cours-3', 'cours-4', 'cours-5', 'cours-6', 'afaire-1', 'afaire-2']
          .map(k => cs.getPropertyValue('--v-' + k).trim() + '/' + cs.getPropertyValue('--v-' + k + '-encre').trim());
      });
      const clair = await jetons();
      await pj.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
      const bascule = await jetons();
      await pj.evaluate(() => document.documentElement.removeAttribute('data-theme'));
      await pj.emulateMedia({ colorScheme: 'dark' });
      const systeme = await jetons();
      await pj.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
      const forceClair = await jetons();
      await ctxJ.close();
      const complet = l => l.length === 9 && l.every(x => /^#[0-9a-f]{6}\/#[0-9a-f]{6}$/i.test(x));
      verifier('les jetons --v-* et leurs encres sont les mêmes dans les deux blocs sombres (système sombre, data-theme="dark"), et chaque couleur y diffère du clair',
        complet(systeme) && complet(clair) && JSON.stringify(systeme) === JSON.stringify(bascule) &&
        systeme.every((x, i) => x.split('/')[0] !== clair[i].split('/')[0]),
        JSON.stringify({ clair, systeme, bascule }));
      verifier('data-theme="light" sur un système sombre rend les jetons du clair',
        JSON.stringify(forceClair) === JSON.stringify(clair), JSON.stringify({ clair, forceClair }));
    }

    // (e) Couleurs forcées (contraste élevé de Windows) : les marques de valeur gardent exactement leurs fonds.
    {
      const lireFonds = async pg => {
        const r = await pg.evaluate(() => {
          const lire = sel => [...document.querySelectorAll(sel)].map(s => (s.dataset.cle || '') + ' ' + getComputedStyle(s).backgroundColor);
          /* Le témoin : un aplat hors des marques protégées, que les
             couleurs forcées doivent bien repeindre — preuve qu'elles
             s'appliquent. */
          const t = document.createElement('span');
          t.style.cssText = 'display:inline-block;width:8px;height:8px;background:rgb(22, 141, 217)';
          document.getElementById('section-synthese').appendChild(t);
          const temoin = getComputedStyle(t).backgroundColor; t.remove();
          return { barre: lire('#barre span:not(.hachure)'), ata: lire('.critique-barre span:not(.hachure)'), jauge: lire('.mini-jauge span[data-cle]'), temoin };
        });
        // La frise de la fiche d'un plan, ouverte d'un clic sur sa référence.
        await pg.evaluate(() => { const b = document.querySelector('#corps-tableau button[data-ref-plan]'); b.scrollIntoView({ block: 'center' }); b.click(); });
        await pg.waitForTimeout(600);
        r.frise = await pg.evaluate(() => [...document.querySelectorAll('.fiche-plan-frise .bande[style*="background"]')].map(s => getComputedStyle(s).backgroundColor));
        return r;
      };
      const ctxN = await contexte();
      const normal = await lireFonds(await page(ctxN, 'couleurs normales'));
      await ctxN.close();
      const ctxF = await contexte({ forcedColors: 'active' });
      const force = await lireFonds(await page(ctxF, 'couleurs forcées'));
      await ctxF.close();
      verifier('couleurs forcées (contraste élevé de Windows) : barre du haut, barres par ATA, mini-jauge du journal et frise d’un plan gardent exactement leurs fonds',
        ['barre', 'ata', 'jauge', 'frise'].every(k => normal[k].length > 0 && JSON.stringify(force[k]) === JSON.stringify(normal[k])) &&
        normal.temoin === 'rgb(22, 141, 217)' && force.temoin !== normal.temoin,
        JSON.stringify({ temoin: [normal.temoin, force.temoin], force: ['barre', 'ata', 'jauge', 'frise'].map(k => k + ' ' + force[k].length + '/' + normal[k].length + ' ' + force[k].slice(0, 3).join(' ; ')) }));
    }

    const erreurs22 = erreursJS.slice(erreursAvant22).filter(e => /^couleurs /.test(e));
    verifier('aucune erreur JavaScript sur les pages de ces vérifications', !erreurs22.length, erreurs22.join(' | '));
  }

  section('Débrief 23 : le nom d’un groupe en entier, et un filtre pour chaque sorte de changement');
  /* « Par ECP, des fois trois petits points, la colonne ne s'adapte pas » :
     des noms d'ECP longs, puis la colonne du nom mesurée à trois largeurs. */
  {
    const cx23 = await contexte();
    const p23 = await page(cx23, 'débrief 23');
    const LONGS = ['ECP-2100-HARNAIS-COCKPIT-GAUCHE-MODIF-B', 'ECP 2207 — Câblage galley avant / zone 200', 'ECP-31'];
    const mesurerNoms = () => p23.evaluate(() => {
      const z = document.getElementById('zone-critique');
      const noms = [...z.querySelectorAll('.critique-ligne .critique-nom')];
      const tete = z.querySelector('.critique-tete > span:first-child');
      const barre = z.querySelector('.critique-ligne .critique-barre');
      const cs = n => getComputedStyle(n);
      const barres = [...z.querySelectorAll('.critique-ligne .critique-barre')].map(b => b.getBoundingClientRect());
      return {
        col: z.style.getPropertyValue('--col-nom'), largeurZone: z.clientWidth,
        barre: barre ? Math.round(barre.getBoundingClientRect().width) : 0,
        barresAlignees: new Set(barres.map(b => Math.round(b.left) + '/' + Math.round(b.width))).size === 1,
        noms: noms.map(n => ({ t: n.textContent, coupe: n.scrollWidth > n.clientWidth + 1 || cs(n).textOverflow === 'ellipsis',
          lignes: Math.round(n.getBoundingClientRect().height / parseFloat(cs(n).lineHeight)),
          dessus: n.parentNode.classList.contains('nom-dessus'),
          sousBarre: n.getBoundingClientRect().bottom <= n.parentNode.querySelector('.critique-barre').getBoundingClientRect().top + 1,
          gauche: Math.round(n.getBoundingClientRect().left), large: Math.round(n.getBoundingClientRect().width) })),
        tete: tete ? Math.round(tete.getBoundingClientRect().width) : 0
      };
    });
    await p23.evaluate(longs => {
      const s = window.__jeuDExemple('HDK');
      s.plans.forEach((x, i) => { x.ecp = longs[i % longs.length]; });
      window.__chargerSource(s);
    }, LONGS);
    await p23.waitForTimeout(400);
    await p23.selectOption('#dim-critique', 'ecp');
    await p23.waitForTimeout(450);
    const n1280 = await mesurerNoms();
    /* Débrief 24 : « des fois la ligne ECP est trop large ». Un nom plus
       large que la colonne permise (240 px au plus) ne l'élargit plus : il
       passe au-dessus de sa barre, en entier, sur une ligne ; les barres
       restent larges et alignées. Un nom court reste à sa place. */
    verifier('par ECP, 1280 px : chaque nom d’ECP se lit en entier, sur une ligne, sans « … » — les deux longs au-dessus de leur barre, le court à sa place',
      n1280.noms.length === 3 && n1280.noms.every(x => !x.coupe && x.lignes === 1) &&
      LONGS.every(l => n1280.noms.some(x => x.t === l)) &&
      n1280.noms.filter(x => x.dessus).length === 2 && n1280.noms.every(x => !x.dessus || x.sousBarre) &&
      !n1280.noms.find(x => x.t === 'ECP-31').dessus, JSON.stringify(n1280));
    verifier('par ECP, 1280 px : la colonne du nom ne dépasse jamais 240 px, les noms restent alignés à gauche, les barres sont alignées et larges (400 px et plus)',
      (n1280.col === '' || parseFloat(n1280.col) <= 240) && new Set(n1280.noms.map(x => x.gauche)).size === 1 &&
      n1280.barresAlignees && n1280.barre >= 400, JSON.stringify(n1280));
    await redimensionner(p23, 900, 950);
    const n900 = await mesurerNoms();
    verifier('par ECP, 900 px : la barre garde 220 px et plus, alignée sur les autres ; les noms trop longs passent au-dessus — toujours en entier, jamais coupés',
      n900.barre >= 219 && n900.barresAlignees && n900.noms.every(x => !x.coupe) && n900.noms.some(x => x.dessus && x.sousBarre),
      JSON.stringify(n900));
    await redimensionner(p23, 390, 844);
    const n390 = await mesurerNoms();
    verifier('par ECP, au téléphone : le nom a toute la ligne, sans largeur imposée, et rien n’est coupé',
      n390.col === '' && n390.noms.every(x => !x.coupe), JSON.stringify(n390));
    await redimensionner(p23, 1280, 950);
    /* Une dimension aux noms courts : la colonne revient à sa largeur d'avant. */
    await p23.selectOption('#dim-critique', 'ata'); await p23.waitForTimeout(400);
    const nAta = await mesurerNoms();
    verifier('par ATA (noms courts) : la colonne garde sa largeur d’avant, rien à agrandir, aucun nom au-dessus',
      nAta.col === '' && nAta.noms.every(x => !x.coupe && !x.dessus), JSON.stringify(nAta.col));

    /* « Nouveaux, supprimés… il faut un peu pour tous les filtres » : trois
       plans sortis de l'extract au dernier relevé, et les nouveaux de la
       démonstration. */
    await p23.evaluate(() => {
      const s = window.__jeuDExemple('HDK');
      const dernier = s.releves[s.releves.length - 1];
      const partis = Object.keys(dernier.plans).slice(0, 3);
      partis.forEach(ref => { delete dernier.plans[ref]; });
      s.plans = s.plans.filter(x => partis.indexOf(x.reference) === -1);
      window.__chargerSource(s);
    });
    await p23.waitForTimeout(400);
    const pilules23 = await p23.evaluate(() => [...document.querySelectorAll('#filtre-journal button')].map(b => ({
      cle: b.dataset.journal, texte: b.textContent.trim(), pastille: (b.querySelector('.pastille') || {}).className || '' })));
    const pil = k => pilules23.find(x => x.cle === k) || {};
    /* Débrief 27 (lot B) : « , » masqué entre le nom et le compte — un
       lecteur d'écran lit « Nouveaux, 6 », plus « Nouveaux6 ». */
    verifier('le journal a une pilule « Nouveaux » et une pilule « Disparus », chacune avec son compte et son signe (+ / −)',
      /^Nouveaux,?\s*\d+$/.test(pil('nouveaux').texte || '') && /^Disparus,?\s*3$/.test(pil('disparus').texte || '') &&
      /\bnouveau\b/.test(pil('nouveaux').pastille) && /\bdisparu\b/.test(pil('disparus').pastille), JSON.stringify(pilules23));
    const filtrer23 = async cle => {
      await p23.click('#filtre-journal button[data-journal="' + cle + '"]'); await p23.waitForTimeout(300);
      return p23.evaluate(() => {
        const sems = [...document.querySelectorAll('#zone-journal .journal-semaine')];
        const cases = [...document.querySelectorAll('#zone-journal button[data-passage]')].map(b => b.dataset.passage);
        const presse = (document.querySelector('#filtre-journal button[aria-pressed="true"]') || {}).dataset;
        return { semaines: sems.length, cases: [...new Set(cases)], presse: presse ? presse.journal : null };
      });
    };
    const fD = await filtrer23('disparus');
    verifier('« Disparus » ne garde que les plans sortis de l’extract : la semaine où ils sont partis, et rien d’autre',
      fD.presse === 'disparus' && fD.semaines === 1 && fD.cases.length === 1 && fD.cases[0] === 'disparus', JSON.stringify(fD));
    const fN = await filtrer23('nouveaux');
    verifier('« Nouveaux » ne garde que les plans apparus', fN.presse === 'nouveaux' && fN.semaines >= 1 && fN.cases.length === 1 && fN.cases[0] === 'nouveaux',
      JSON.stringify(fN));
    /* Dans le résumé d'une semaine, la case des disparus est un bouton comme
       les autres : un clic filtre, un second le retire. */
    await p23.click('#filtre-journal button[data-journal=""]'); await p23.waitForTimeout(300);
    const caseD = await p23.evaluate(() => {
      const b = document.querySelector('#zone-journal button[data-passage="disparus"]');
      if (!b) return null;
      b.click();
      return true;
    });
    await p23.waitForTimeout(300);
    const apresCase = await p23.evaluate(() => ({
      presse: ((document.querySelector('#filtre-journal button[aria-pressed="true"]') || {}).dataset || {}).journal,
      entetes: [...document.querySelectorAll('#zone-journal .journal-entetes .entete-col')].map(e => ({ t: e.textContent.trim(), pastille: !!e.querySelector('.pastille') }))
    }));
    verifier('la case « disparus » d’une semaine est un bouton : un clic n’affiche qu’eux, comme la pilule ; l’en-tête de sa colonne a sa pastille',
      caseD === true && apresCase.presse === 'disparus' && apresCase.entetes.length >= 1 && apresCase.entetes.every(e => e.pastille), JSON.stringify(apresCase));
    await cx23.close();
  }

  section('Débrief 24 : l’en-tête du bloc reste en vue, les lignes du journal sont droites');
  {
    const cx24 = await contexte();
    const p24 = await page(cx24, 'débrief 24');
    /* « Quand je scroll en bas, je ne vois plus Séquence, Plans, Répartition… » :
       l'en-tête de la liste reste en vue.
       Débrief 27 (lot C, D10, P-F4) : plus de cadre qui défile — la liste
       prend sa hauteur dans la page, et son en-tête colle sous le sommaire
       tant qu'on la lit. Les vérifications du débrief 24 se refont dans la
       page : ce que la page amène sous les yeux se pose sous l'en-tête. */
    await p24.selectOption('#dim-critique', 'ata'); await p24.waitForTimeout(400);
    /* Descendre la page jusqu'à la k-ième ligne du bloc, posée à y px du haut. */
    const poser24 = (k, y) => p24.evaluate(([k, y]) => {
      const l = document.querySelectorAll('#zone-critique .critique-ligne')[k];
      window.scrollBy(0, l.getBoundingClientRect().top - y);
    }, [k, y]);
    await poser24(5, 200); await p24.waitForTimeout(200);
    const tete24 = await p24.evaluate(() => {
      const z = document.getElementById('zone-critique'), t = z.querySelector('.critique-tete');
      const rt = t.getBoundingClientRect(), bs = document.getElementById('sommaire').getBoundingClientRect();
      const dessus = document.elementFromPoint(rt.left + 30, rt.top + rt.height / 2);
      const fond = getComputedStyle(t).backgroundColor;
      return { cadre: z.scrollHeight > z.clientHeight + 1 || getComputedStyle(z).overflowY !== 'visible', haut: Math.round(rt.top), sommaire: Math.round(bs.bottom),
               passee: z.querySelector('.critique-ligne').getBoundingClientRect().top < rt.top, visible: !!dessus && t.contains(dessus), opaque: !/rgba\(.*, 0\)$/.test(fond) };
    });
    verifier('en descendant la page dans la liste du bloc, l’en-tête (ATA, Plans, Répartition, Fin estimée, Rythme requis) reste collé sous le sommaire, opaque, au-dessus des lignes — et la liste n’a plus de cadre qui défile (débrief 27)',
      !tete24.cadre && tete24.passee && Math.abs(tete24.haut - tete24.sommaire) <= 1 && tete24.visible && tete24.opaque, JSON.stringify(tete24));

    /* Relecture du débrief 24 : l'en-tête collé ne doit rien cacher. Une
       ligne ouverte au ras du bas de l'écran monte pour montrer ses plans :
       elle se pose SOUS l'en-tête — sinon on voit la liste dépliée sans
       savoir quel groupe on vient d'ouvrir. Au téléphone, la barre « Trier »
       défile avec la liste. */
    const ouvrirDuBas24 = async () => {
      await poser24(0, 600); await p24.waitForTimeout(150);
      const i = await p24.evaluate(() => {
        const ls = [...document.querySelectorAll('#zone-critique .critique-ligne')];
        let k = -1; ls.forEach((l, j) => { const r = l.getBoundingClientRect(); if (r.height && r.bottom <= window.innerHeight) k = j; });
        return k;
      });
      const ligne = p24.locator('#zone-critique .critique-ligne').nth(i);
      const groupe = await ligne.getAttribute('data-groupe');
      await ligne.locator('.critique-nom').click(); await p24.waitForTimeout(400);
      const r = await p24.evaluate(g => {
        const z = document.getElementById('zone-critique'), t = z.querySelector('.critique-tete');
        const l = [...z.querySelectorAll('.critique-ligne')].find(x => x.dataset.groupe === g), n = l.querySelector('.critique-nom');
        const liste = document.getElementById(l.getAttribute('aria-controls') || '');
        const rt = t.getBoundingClientRect(), rl = l.getBoundingClientRect(), rn = n.getBoundingClientRect();
        const bas = Math.max(document.getElementById('sommaire').getBoundingClientRect().bottom, getComputedStyle(t).position === 'sticky' ? rt.bottom : 0);
        const pt = document.elementFromPoint(rn.left + Math.min(20, rn.width / 2), rn.top + rn.height / 2);
        return { groupe: g, ouverte: l.getAttribute('aria-expanded') === 'true', collee: getComputedStyle(t).position,
                 sousTete: Math.round(rl.top - bas), listeVue: !!liste && liste.getBoundingClientRect().top < window.innerHeight - 100, nomVu: !!pt && l.contains(pt) };
      }, groupe);
      await p24.locator('#zone-critique .critique-ligne').nth(i).locator('.critique-nom').click(); await p24.waitForTimeout(300);   // on la referme
      return r;
    };
    const bas1280 = await ouvrirDuBas24();
    verifier('ouvrir la dernière ligne visible de l’écran : elle monte montrer ses plans et se pose sous l’en-tête collé — son nom reste lisible',
      bas1280.ouverte && bas1280.collee === 'sticky' && bas1280.sousTete >= -1 && bas1280.listeVue && bas1280.nomVu, JSON.stringify(bas1280));

    /* Au clavier, en remontant (Maj+Tab), le navigateur amène chaque ligne
       au bord haut de l'écran : elle doit s'arrêter sous l'en-tête collé. */
    await poser24(8, 250); await p24.waitForTimeout(150);
    await p24.evaluate(() => document.querySelectorAll('#zone-critique .critique-ligne')[8].focus());
    const clavier24 = [];
    for (let k = 0; k < 10; k++) {
      await p24.keyboard.press('Shift+Tab'); await p24.waitForTimeout(80);
      clavier24.push(await p24.evaluate(() => {
        const z = document.getElementById('zone-critique'), a = document.activeElement;
        if (!a || !z.contains(a) || !a.closest('.critique-rangee')) return null;
        const l = a.closest('.critique-ligne'), cible = l ? l.querySelector('.critique-nom') : a;
        const rt = z.querySelector('.critique-tete').getBoundingClientRect(), rc = cible.getBoundingClientRect();
        const pt = document.elementFromPoint(rc.left + Math.min(20, rc.width / 2), rc.top + rc.height / 2);
        return { quoi: l ? l.dataset.groupe : a.className, haut: Math.round(rc.top), basTete: Math.round(rt.bottom), cache: !!pt && !!pt.closest('.critique-tete, .sommaire') };
      }));
    }
    const vus24 = clavier24.filter(Boolean);
    verifier('au clavier, en remontant la liste (Maj+Tab), chaque ligne qui prend le focus se pose sous l’en-tête collé, jamais dessous',
      vus24.length >= 6 && vus24.every(x => !x.cache && x.haut >= x.basTete - 1), JSON.stringify(vus24));

    /* L'en-tête collé se clique la liste descendue : « ? » ouvre l'aide
       au-dessus de la liste (débrief 27, P-F4) et la page remonte jusqu'à
       elle ; la refermer de plus bas ne fait pas sauter les lignes ; un tri
       montre le classement depuis son premier. */
    await poser24(6, 300); await p24.waitForTimeout(150);
    const clics24 = await p24.evaluate(async () => {
      const attendre = ms => new Promise(r => setTimeout(r, ms));
      const z = document.getElementById('zone-critique');
      const tete = () => z.querySelector('.critique-tete').getBoundingClientRect();
      const sommaire = () => document.getElementById('sommaire').getBoundingClientRect().bottom;
      const premiere = () => [...z.querySelectorAll('.critique-ligne')].findIndex(x => x.getBoundingClientRect().top >= tete().bottom - 1);
      const colle = Math.abs(tete().top - sommaire()) <= 1 && z.querySelector('.critique-ligne').getBoundingClientRect().top < tete().top;
      z.querySelector('.critique-tete button[data-aide]').click(); await attendre(300);
      const pa = document.getElementById('panneau-fin'), rp = pa ? pa.getBoundingClientRect() : null;
      const aide = { colle, ouvert: !!pa, haut: rp ? Math.round(rp.top - sommaire()) : null, dessus: rp ? Math.round(tete().top - rp.bottom) : null,
                     dansCadre: !!pa && !!pa.closest('.critique-table'), focus: document.activeElement && document.activeElement.getAttribute('data-aide') };
      /* Plus bas, l'aide hors de vue au-dessus, l'en-tête de nouveau collé. */
      window.scrollBy(0, (pa ? pa.getBoundingClientRect().bottom : 0) - sommaire() + 300);
      await attendre(150);
      const l0 = z.querySelectorAll('.critique-ligne')[premiere()], g = l0.dataset.groupe, y0 = l0.getBoundingClientRect().top;
      const auMilieu = Math.abs(tete().top - sommaire()) <= 1;
      z.querySelector('.critique-tete button[data-aide]').click(); await attendre(300);
      const l1 = [...z.querySelectorAll('.critique-ligne')].find(x => x.dataset.groupe === g);
      const fermer = { auMilieu, ferme: !document.getElementById('panneau-fin'), groupe: g, saut: Math.round(l1.getBoundingClientRect().top - y0) };
      window.scrollBy(0, z.querySelectorAll('.critique-ligne')[6].getBoundingClientRect().top - 300); await attendre(150);
      z.querySelector('.critique-tete button[data-trig="fin"]').click(); await attendre(300);
      const tri = { actif: z.querySelector('button[data-trig="fin"]').dataset.actif, premiere: premiere(),
                    sousTete: Math.round(z.querySelector('.critique-ligne').getBoundingClientRect().top - tete().bottom),
                    triee: z.querySelector('button[data-trig="fin"]').parentNode.getAttribute('aria-sort') };
      /* Deux clics de plus : retour au classement par défaut. */
      z.querySelector('.critique-tete button[data-trig="fin"]').click(); await attendre(200);
      z.querySelector('.critique-tete button[data-trig="fin"]').click(); await attendre(200);
      return { aide, fermer, tri };
    });
    verifier('liste descendue, « ? » dans l’en-tête collé : l’aide s’ouvre au-dessus de l’en-tête de la liste (pas dans un cadre) et la page remonte jusqu’à elle ; le focus reste sur le « ? »',
      clics24.aide.colle && clics24.aide.ouvert && clics24.aide.haut >= -1 && clics24.aide.haut < 60 && clics24.aide.dessus >= 0 && !clics24.aide.dansCadre && clics24.aide.focus === 'fin', JSON.stringify(clics24.aide));
    verifier('liste descendue sous l’aide ouverte, « ? » la referme : les lignes qu’on regardait restent où elles étaient',
      clics24.fermer.auMilieu && clics24.fermer.ferme && Math.abs(clics24.fermer.saut) <= 1, JSON.stringify(clics24.fermer));
    verifier('liste descendue, un tri depuis l’en-tête collé montre le classement depuis son premier, juste sous l’en-tête, et l’en-tête le dit (aria-sort)',
      clics24.tri.actif === 'true' && clics24.tri.premiere === 0 && Math.abs(clics24.tri.sousTete) <= 2 && /^(a|de)scending$/.test(clics24.tri.triee || ''), JSON.stringify(clics24.tri));

    /* Au téléphone, chaque ligne porte ses libellés : la barre « Trier »
       ne reste pas collée — elle cachait la ligne qu'on venait d'ouvrir. */
    await redimensionner(p24, 390, 844);
    await poser24(6, 300); await p24.waitForTimeout(150);
    const tel24 = await p24.evaluate(() => {
      const t = document.querySelector('#zone-critique .critique-tete');
      return { position: getComputedStyle(t).position, bas: Math.round(t.getBoundingClientRect().bottom) };
    });
    const bas390 = await ouvrirDuBas24();
    verifier('au téléphone, la barre « Trier » défile avec la liste au lieu d’en cacher le haut, et une ligne ouverte en bas de l’écran garde son nom lisible',
      tel24.position !== 'sticky' && tel24.bas < 0 && bas390.ouverte && bas390.nomVu && bas390.sousTete >= -1, JSON.stringify({ tel24, bas390 }));
    await redimensionner(p24, 1280, 950);

    /* Débrief 23, gardé : un nom MOYEN ne passe pas au-dessus, la colonne
       s'élargit pour lui (plus de 118 px, 240 au plus) et l'en-tête « ECP »
       prend sa largeur. Un nom trop long passe au-dessus de sa barre. */
    const NOMS24 = ['ECP 2207 — Galley avant', 'ECP-31', 'ECP-2100-HARNAIS-COCKPIT-GAUCHE-MODIF-B'];
    await p24.evaluate(noms => {
      const s = window.__jeuDExemple('HDK');
      s.plans.forEach((x, i) => { x.ecp = noms[i % noms.length]; });
      window.__chargerSource(s);
    }, NOMS24);
    await p24.waitForTimeout(400);
    await p24.selectOption('#dim-critique', 'ecp'); await p24.waitForTimeout(450);
    const col24 = await p24.evaluate(() => {
      const z = document.getElementById('zone-critique'), tete = z.querySelector('.critique-tete > span:first-child');
      const noms = [...z.querySelectorAll('.critique-ligne .critique-nom')].map(n => ({ t: n.textContent, dessus: n.parentNode.classList.contains('nom-dessus'),
        lignes: Math.round(n.getBoundingClientRect().height / parseFloat(getComputedStyle(n).lineHeight)), large: Math.round(n.getBoundingClientRect().width) }));
      return { col: z.style.getPropertyValue('--col-nom'), tete: Math.round(tete.getBoundingClientRect().width), noms };
    });
    const moyen24 = col24.noms.find(x => x.t === NOMS24[0]) || {}, long24 = col24.noms.find(x => x.t === NOMS24[2]) || {};
    verifier('par ECP, 1280 px : un nom moyen garde sa place, sur une ligne — la colonne s’élargit pour lui (plus de 118 px, 240 au plus) et l’en-tête « ECP » a sa largeur ; le nom trop long passe au-dessus',
      !moyen24.dessus && moyen24.lignes === 1 && parseFloat(col24.col) > 118 && parseFloat(col24.col) <= 240 &&
      Math.abs(col24.tete - moyen24.large) <= 1 && long24.dessus === true, JSON.stringify(col24));

    /* À l'impression A4 (marges par défaut de Chrome), la page fait 717 px :
       c'est la mise en page du téléphone, et rien ne remesure — la classe
       « nom-dessus » posée à l'écran reste. Elle ne doit rien y changer :
       le nom d'un tenant, les cellules empilées dessous, pas en escalier. */
    await p24.setViewportSize({ width: 717, height: 950 });
    /* Débrief 27 (lot C, M2) : la carte du téléphone a deux colonnes — le
       nom et « Plans 65 » sur une ligne, la barre dessous, puis la fin
       estimée et le rythme côte à côte. La classe « nom-dessus » ne doit
       rien y changer : le nom sur sa ligne, en entier, la barre sur toute
       la largeur, la fin estimée sous le nom, rien en escalier. */
    const impr24 = await p24.evaluate(nom => {
      const l = [...document.querySelectorAll('#zone-critique .critique-ligne')].find(x => x.querySelector('.critique-nom').textContent === nom);
      l.classList.add('nom-dessus');
      const n = l.querySelector('.critique-nom'), cs = getComputedStyle(l), r = e => l.querySelector(e).getBoundingClientRect();
      const rl = l.getBoundingClientRect(), rn = r('.critique-nom'), rp = r('.critique-plans'), rb = r('.critique-barre'), rf = r('.critique-date');
      return { colonnes: cs.gridTemplateColumns.split(' ').length, lignesNom: Math.round(rn.height / parseFloat(getComputedStyle(n).lineHeight)),
               memeLigne: Math.abs((rn.top + rn.bottom) / 2 - (rp.top + rp.bottom) / 2) <= 6, plansADroite: rp.left >= rn.right - 1,
               barreLarge: rb.width >= rl.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 2 && rb.top >= rn.bottom - 1,
               finSousNom: Math.abs(rf.left - rl.left - parseFloat(cs.paddingLeft)) <= 2 && rf.top >= rb.bottom - 1 };
    }, NOMS24[2]);
    verifier('impression A4 (page de 717 px) : une ligne dont le nom est passé au-dessus à l’écran s’imprime d’un tenant — le nom sur sa ligne avec « Plans » à droite, la barre sur toute la largeur, la fin estimée dessous, rien en escalier',
      impr24.colonnes === 2 && impr24.lignesNom === 1 && impr24.memeLigne && impr24.plansADroite && impr24.barreLarge && impr24.finSousNom, JSON.stringify(impr24));
    await redimensionner(p24, 1280, 950);

    /* « Les nouveaux sont pas droits » : des plans nouveaux arrivés à des
       valeurs de longueurs différentes, la flèche de chaque ligne au même
       endroit, « nouveau » aligné, l'arrivée qui commence au même x. Deux
       plans disparus partis d'une valeur longue et d'une courte : le départ
       finit au même écart de sa flèche, sur une ligne comme sur deux. */
    const VALEURS24 = ['Terminé', 'En cours', '', 'Un état au nom vraiment très long pour la colonne', 'PWD_IN_PROGRESS', 'FWD_TO_SEIZE_EN_ATTENTE_RETOUR_CLIENT'];
    await p24.evaluate(valeurs => {
      const s = window.__jeuDExemple('HDK');
      const modele = s.plans[0];
      valeurs.forEach((v, k) => {
        const x = JSON.parse(JSON.stringify(modele));
        x.reference = 'ZZZ' + (900 + k) + 'A600001A';
        x.avancement = v;
        s.plans.push(x);
        s.releves[s.releves.length - 1].plans[x.reference] = v;
      });
      const avant = s.releves[s.releves.length - 2];
      avant.plans.ZZZ910A600001A = 'Valeur saisie à la main beaucoup trop longue';
      avant.plans.ZZZ911A600001A = 'En cours';
      avant.plans.ZZZ912A600001A = 'PWD_TO_CONTROL';
      window.__chargerSource(s);
    }, VALEURS24);
    await p24.waitForTimeout(400);
    await p24.click('#filtre-journal button[data-journal="nouveaux"]'); await p24.waitForTimeout(300);
    /* Chaque ligne d'un type : où tombent le départ, la flèche, l'arrivée ;
       l'écart entre la fin du texte de départ et la flèche ; les valeurs
       coupées net (scrollWidth) ; et chaque retour à la ligne à l'intérieur
       d'une valeur — il doit tomber après un « _ » ou une espace. */
    const mesurerJournal24 = type => p24.evaluate(async type => {
      const attendre = ms => new Promise(r => setTimeout(r, ms));
      for (let k = 0; k < 8; k++) {
        const b = document.querySelector('#zone-journal .journal-plier[aria-expanded="false"]') || document.querySelector('#zone-journal button[data-tout]');
        if (!b) break; b.click(); await attendre(200);
      }
      const texte = e => { const tw = document.createTreeWalker(e, NodeFilter.SHOW_TEXT), ns = []; let n; while ((n = tw.nextNode())) ns.push(n); return ns; };
      const coupures = e => {
        const res = []; let avantTop = null, prec = '';
        texte(e).forEach(n => { for (let i = 0; i < n.textContent.length; i++) {
          const rg = document.createRange(); rg.setStart(n, i); rg.setEnd(n, i + 1); const r = rg.getClientRects()[0]; if (!r) continue;
          if (avantTop !== null && r.top > avantTop + 3) res.push(prec);
          avantTop = r.top; prec = n.textContent[i];
        } });
        return res;
      };
      /* Les plans de l'essai : ZZZ90x nouveaux, ZZZ91x disparus (nouveaux, eux, la semaine d'avant). */
      return [...document.querySelectorAll('#zone-journal .journal-ligne[data-type="' + type + '"]')].filter(l => l.dataset.ref.indexOf(type === 'nouveau' ? 'ZZZ90' : 'ZZZ91') === 0).map(l => {
        const av = l.querySelector('.etiq-etat.avant'), ap = l.querySelector('.etiq-etat.apres'), f = l.querySelector('.fleche-etat').getBoundingClientRect();
        const rav = av.getBoundingClientRect(), rap = ap.getBoundingClientRect();
        const finAvant = Math.max(...texte(av).map(n => { const rg = document.createRange(); rg.selectNodeContents(n); return Math.max(...[...rg.getClientRects()].map(r => r.right)); }));
        return { ref: l.dataset.ref, valeur: (type === 'nouveau' ? ap : av).textContent,
                 avant: Math.round(rav.right), avantGauche: Math.round(rav.left), colonneAvant: Math.round(l.querySelector('.vers').getBoundingClientRect().left),
                 alignAvant: getComputedStyle(av).textAlign, finAvant: Math.round(finAvant),
                 fleche: Math.round(f.left), apres: Math.round(rap.left), droite: Math.round(rap.right),
                 large: Math.round(l.querySelector('.vers').getBoundingClientRect().right), ecartAvant: Math.round(f.left - finAvant),
                 coupe: ap.scrollWidth > ap.clientWidth + 1 || av.scrollWidth > av.clientWidth + 1, haut: Math.round(rap.height),
                 lignes: 1 + coupures(type === 'nouveau' ? ap : av).length, coupuresMot: [...coupures(av), ...coupures(ap)].filter(c => c !== '_' && c !== ' ') };
      });
    }, type);
    const lignes24 = await mesurerJournal24('nouveau');
    const memes = (ls, k) => new Set(ls.map(x => x[k])).size === 1;
    const ligne24 = (ls, v) => ls.find(x => x.valeur === v) || {};
    verifier('journal, plans nouveaux : sur chaque ligne, « nouveau », la flèche et l’arrivée tombent au même endroit, quelle que soit la longueur de la valeur',
      lignes24.length === VALEURS24.length && memes(lignes24, 'avant') && memes(lignes24, 'fleche') && memes(lignes24, 'apres'), JSON.stringify(lignes24));
    /* Relecture : « passe à la ligne », vraiment — pas coupée net sur une
       ligne, et lisible en entier. Une valeur de GATES tient sur une ligne ;
       une valeur longue faite de « _ » passe à la ligne après l'un d'eux. */
    verifier('journal : une valeur au nom très long passe à la ligne dans sa moitié — en entier, jamais coupée net — sans pousser la flèche ni déborder',
      lignes24.every(x => x.droite <= x.large + 1 && !x.coupe && !x.coupuresMot.length) &&
      ligne24(lignes24, VALEURS24[3]).haut > 1.5 * ligne24(lignes24, 'Terminé').haut && ligne24(lignes24, VALEURS24[3]).lignes >= 2 &&
      ligne24(lignes24, 'PWD_IN_PROGRESS').lignes === 1 && ligne24(lignes24, VALEURS24[5]).lignes >= 2,
      JSON.stringify(lignes24.map(x => [x.valeur, x.droite, x.large, x.coupe, x.haut, x.lignes, x.coupuresMot])));

    /* Sous 720 px (une fenêtre en demi-écran, le téléphone), les lignes
       restent droites : une seule position de flèche par largeur, aucune
       valeur coupée au milieu d'un mot ni rognée au bord. */
    const etroits24 = [];
    for (const w of [720, 600, 390, 360]) {
      await redimensionner(p24, w, 900);
      const ls = await mesurerJournal24('nouveau');
      etroits24.push({ w, n: ls.length, fleches: [...new Set(ls.map(x => x.fleche))], apres: [...new Set(ls.map(x => x.apres))],
        debord: ls.filter(x => x.droite > x.large + 1 || x.coupe).map(x => x.valeur), coupuresMot: ls.filter(x => x.coupuresMot.length).map(x => x.valeur),
        gates: ligne24(ls, 'PWD_IN_PROGRESS').lignes });
    }
    await redimensionner(p24, 1280, 950);
    verifier('journal sous 720 px (720, 600, 390, 360) : la flèche et l’arrivée tombent au même endroit sur chaque ligne, rien n’est rogné, aucun mot coupé, PWD_IN_PROGRESS sur une ligne',
      etroits24.every(x => x.n === VALEURS24.length && x.fleches.length === 1 && x.apres.length === 1 && !x.debord.length && !x.coupuresMot.length && x.gates === 1),
      JSON.stringify(etroits24));

    await p24.click('#filtre-journal button[data-journal="disparus"]'); await p24.waitForTimeout(300);
    const disparus24 = await mesurerJournal24('disparu');
    const longD = ligne24(disparus24, 'Valeur saisie à la main beaucoup trop longue');
    /* Débrief 28 : les valeurs de départ s'alignent à gauche, en colonne,
       comme les arrivées (calées contre la flèche, « nouveau » ou « TO_TREAT »
       semblaient décalés) : même bord gauche sur chaque ligne, une valeur sur
       deux lignes passe à la ligne dans sa colonne, sans toucher la flèche. */
    verifier('journal, plans disparus : les valeurs de départ alignées à gauche, en colonne (même bord gauche) ; celle sur deux lignes reste dans sa colonne, avant la flèche (débrief 28)',
      disparus24.length === 3 && longD.lignes >= 2 && memes(disparus24, 'fleche') && memes(disparus24, 'avantGauche') &&
      disparus24.every(x => x.alignAvant === 'left' && x.avantGauche - x.colonneAvant <= 1 && x.finAvant <= x.fleche && !x.coupe && !x.coupuresMot.length),
      JSON.stringify(disparus24));
    await cx24.close();
  }

  section('Persistance (même navigateur, page rechargée)');
  await p.click('button[data-trig="fin"]'); await p.waitForTimeout(300);
  /* Débrief 19 : « quand on ouvre, t'es directement sur Tout » — un cadrage
     choisi à la main ne se reprend plus : on rouvre sur « Échéances ». */
  await p.click('.commandes-graphe .segmente button[data-span="0"]'); await p.waitForTimeout(300);
  const triAvant = await p.evaluate(() => {
    const b = document.querySelector('button[data-trig][data-actif="true"]');
    return b ? b.dataset.trig : null;
  });
  await p.waitForTimeout(700);
  await p.reload(); await attendrePrete(p, 1400);
  const apresRech = await p.evaluate(() => {
    const b = document.querySelector('button[data-trig][data-actif="true"]');
    return { tri: b ? b.dataset.trig : null, jalons: window.__jeuDExemple('HDK').jalons.length,
             stockes: /"jalons"/.test(localStorage.getItem('suivi-fwd:v1') || ''),
             zoom: [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')].map(x => x.textContent).join(),
             cadrageStocke: /"fen"|"cadrage"/.test(localStorage.getItem('suivi-fwd:v1') || '') };
  });
  verifier('débrief 19 : après un clic sur « Tout », la page rouverte est sur « Échéances » — le cadrage ne se mémorise plus',
    apresRech.zoom === 'Échéances' && !apresRech.cadrageStocke, JSON.stringify(apresRech));
  verifier('le tri du bloc par groupe survit au rechargement',
    apresRech.tri === triAvant, triAvant + ' → ' + apresRech.tri);
  verifier('les jalons ne passent pas par le stockage : ils viennent de la source',
    apresRech.jalons === 5 && !apresRech.stockes, JSON.stringify(apresRech));

  // =================================================================
  section('Débrief 20 : la page dit vrai partout');
  /* La chasse aux bugs du débrief 20 : chaque nombre affiché est celui que
     le clic montrera, un seul verdict par écran, pas de « 0 sur 0 ». Chaque
     test reproduit d'abord la situation qui trompait. */
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(500);
  await reinitialiser(p);
  /* Le regroupement choisi plus haut (ECP…) se garde d'un rechargement à
     l'autre : ces tests parlent d'ATA. */
  await p.selectOption('#dim-critique', 'ata'); await p.waitForTimeout(400);
  const lignes20 =() => p.evaluate(() => document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length);
  const nombre20 = t => parseInt(String(t || '').replace(/[\s\u00a0\u202f]/g, '').replace(/^\D*/, ''), 10);

  // A. « / » ne vole plus la frappe d'un autre champ.
  await p.click('#recherche-journal');
  await p.keyboard.type('S38/A'); await p.waitForTimeout(300);
  const barre20 = await p.evaluate(() => ({ journal: document.getElementById('recherche-journal').value, tableau: document.getElementById('recherche').value,
    actif: document.activeElement.id }));
  verifier('A — taper « S38/A » dans la recherche du journal : tout reste dans ce champ, la recherche du tableau ne prend rien',
    barre20.journal === 'S38/A' && barre20.tableau === '' && barre20.actif === 'recherche-journal', JSON.stringify(barre20));
  await p.keyboard.press('Escape'); await p.waitForTimeout(300);
  await p.evaluate(() => document.activeElement.blur());
  await p.keyboard.press('/'); await p.waitForTimeout(150);
  /* Débrief 29 (S9) : « / » ouvre la loupe du sommaire (là où l'on est),
     plus la recherche du tableau (la page sautait aux Plans). */
  verifier('A — hors d’un champ, « / » mène toujours à la recherche de plan (la loupe du sommaire, débrief 29)',
    await p.evaluate(() => document.activeElement.id === 'cherche-plan-champ'));
  await p.keyboard.press('Escape'); await p.waitForTimeout(150);
  await p.evaluate(() => document.activeElement.blur());

  // B et J. Une sélection vide : une phrase, une piste, des tuiles qui ne se recouvrent pas.
  const tuilesSeChevauchent = () => p.evaluate(() => {
    const r = [...document.querySelectorAll('#etats .etat-btn')].map(b => b.getBoundingClientRect());
    return r.some((a, i) => r.some((b, k) => k > i && a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5));
  });
  await p.fill('#recherche', 'zzzz'); await p.waitForTimeout(600);
  const vide20 = await p.evaluate(() => ({
    phrase: document.getElementById('phrase').textContent.replace(/\s+/g, ' ').trim(),
    piste: document.getElementById('barre').classList.contains('vide') && getComputedStyle(document.getElementById('barre'), '::before').content !== 'none' &&
      document.getElementById('barre').getBoundingClientRect().height > 0,
    legende: document.getElementById('etats').classList.contains('en-legende'),
    tuiles: document.querySelectorAll('#etats .etat-btn').length
  }));
  verifier('J — sélection vide : « Aucun plan dans la sélection », plus de « 0 sur 0 plans validés »', vide20.phrase === 'Aucun plan dans la sélection', vide20.phrase);
  verifier('B — sélection vide : la barre garde une piste fine au lieu d’un trou, et les tuiles passent en légende sans se recouvrir',
    vide20.piste && vide20.legende && vide20.tuiles >= 2 && !(await tuilesSeChevauchent()), JSON.stringify(vide20));
  const refs20 = await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const fini = s.plans.find(x => window.__classer(x.avancement) === 'termine');
    const pasFini = s.plans.find(x => window.__classer(x.avancement) === 'encours');
    return { fini: fini.reference, pasFini: pasFini.reference };
  });
  await p.fill('#recherche', refs20.pasFini); await p.waitForTimeout(600);
  const un0 = await p.evaluate(() => document.getElementById('phrase').textContent.replace(/[\s\u00a0\u202f]+/g, ' ').trim());
  await p.fill('#recherche', refs20.fini); await p.waitForTimeout(600);
  const un1 = await p.evaluate(() => document.getElementById('phrase').textContent.replace(/[\s\u00a0\u202f]+/g, ' ').trim());
  verifier('J — un seul plan : « 0 sur 1 plan validé », « 1 sur 1 plan validé » (au singulier)',
    un0 === '0 sur 1 plan validé dans la sélection' && un1 === '1 sur 1 plan validé dans la sélection', JSON.stringify([un0, un1]));
  verifier('B — un seul plan : ses tuiles ne se recouvrent pas non plus', !(await tuilesSeChevauchent()));
  await reinitialiser(p);
  verifier('B — sur toute la page, les chiffres sous la barre ne se recouvrent pas', !(await tuilesSeChevauchent()));

  // C. Les puces au-dessus du tableau comptent ce que leur clic montrera.
  /* Un groupe qui a des deux : des plans à l'arrêt et des « non renseignés ». */
  /* Débrief 27 (lot C) : la phrase de la ligne (plus son infobulle) dit ses
     valeurs ; « groupe ouvert » = la page filtrée sur lui, par son bouton. */
  await p.evaluate(() => [...document.querySelectorAll('.critique-arret')].map(a => a.previousElementSibling)
    .find(l => /Non renseigné/.test(l.querySelector('.masque').textContent)).click()); await p.waitForTimeout(500);
  await p.click('#filtrer-groupe-page'); await p.waitForTimeout(500);
  const puces20 = await p.evaluate(() => ({
    groupe: (document.querySelector('.critique-ligne.filtre-page[aria-expanded="true"]') || {}).dataset,
    vide: (document.querySelector('#incomplets .puce-vide b') || {}).textContent,
    arret: (document.getElementById('a-surveiller').textContent.match(/(\d+) plans?/) || [])[1]
  }));
  await p.click('#incomplets .puce-vide'); await p.waitForTimeout(500);
  const apresVide20 = await lignes20();
  await p.click('#incomplets .puce-vide'); await p.waitForTimeout(500);
  await p.click('#a-surveiller button[data-arret]'); await p.waitForTimeout(500);
  const apresArret20 = await lignes20();
  await p.click('#a-surveiller button[data-arret]'); await p.waitForTimeout(500);
  verifier('C — groupe ouvert : « non renseigné N » montre N lignes, « À surveiller : N plans » aussi (ils comptaient tout le périmètre)',
    !!puces20.groupe && nombre20(puces20.vide) === apresVide20 && apresVide20 > 0 && Number(puces20.arret) === apresArret20 && apresArret20 > 0 &&
    apresArret20 < 16, JSON.stringify([puces20, apresVide20, apresArret20]));
  await reinitialiser(p);
  await p.click('#etats .etat-btn[data-cle="termine"]'); await p.waitForTimeout(500);
  verifier('C — sous la tuile « Terminé », « non renseigné » vaudrait 0 : la puce s’efface',
    await p.evaluate(() => !document.querySelector('#incomplets .puce-vide')));

  // F. Le choix le plus récent l'emporte entre « À surveiller » et une tuile contraire.
  const arretVisible20 = await p.evaluate(() => !document.getElementById('a-surveiller').hidden &&
    (document.getElementById('a-surveiller').textContent.match(/(\d+) plans?/) || [])[1]);
  await p.click('#a-surveiller button[data-arret]'); await p.waitForTimeout(500);
  const f20a = await p.evaluate(() => ({ lignes: document.querySelectorAll('#corps-tableau tr').length,
    tuile: !!document.querySelector('#etats .etat-btn[aria-pressed="true"]'),
    etats: [...new Set([...document.querySelectorAll('#corps-tableau .etat-cellule')].map(x => x.textContent.trim()))].join() }));
  verifier('F — « À surveiller » sous la tuile « Terminé » : la tuile se retire, les plans à l’arrêt s’affichent (plus de 0 sur 0)',
    arretVisible20 === '16' && f20a.lignes === 16 && !f20a.tuile && f20a.etats === 'En cours', JSON.stringify([arretVisible20, f20a]));
  await p.click('#etats .etat-btn[data-cle="termine"]'); await p.waitForTimeout(500);
  const f20b = await p.evaluate(() => ({ lignes: document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length,
    jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()),
    phrase: document.getElementById('phrase').textContent }));
  verifier('F — puis la tuile « Terminé » : « À surveiller » se retire, la page montre les validés',
    f20b.lignes > 16 && f20b.jetons.length === 1 && /^État/.test(f20b.jetons[0]) && !/sur 0/.test(f20b.phrase), JSON.stringify(f20b));
  await reinitialiser(p);

  // G. Un filtre de colonne passe par le même chemin que la recherche.
  await deplierFiltresColonne(p);
  await p.click('input[data-filtre="reference"]');
  await p.keyboard.type(refs20.pasFini); await p.waitForTimeout(700);
  const g20a = await p.evaluate(() => ({ fiche: !document.getElementById('fiche-plan').hidden && (document.querySelector('#fiche-plan .ref') || {}).textContent,
    actif: document.activeElement.getAttribute('data-filtre'), valeur: document.activeElement.value, lignes: document.querySelectorAll('#corps-tableau tr').length,
    jeton: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()).join() }));
  verifier('G — un filtre de colonne qui ne laisse qu’un plan ouvre sa fiche, et le curseur reste dans le champ',
    g20a.fiche === refs20.pasFini && g20a.actif === 'reference' && g20a.valeur === refs20.pasFini && g20a.lignes === 1 && /Référence/.test(g20a.jeton), JSON.stringify(g20a));
  await p.keyboard.type('QQ'); await p.waitForTimeout(700);
  const g20b = await p.evaluate(() => ({ fiche: document.getElementById('fiche-plan').hidden, vide: !!document.querySelector('#corps-tableau .vide-message'),
    valeur: document.activeElement.value, incomplets: !!document.querySelector('#incomplets .puce-vide') }));
  verifier('G — et la fiche se ferme sur un tableau vide ; la puce « non renseigné » recompte (0 : elle s’efface)',
    g20b.fiche && g20b.vide && g20b.valeur === refs20.pasFini + 'QQ' && !g20b.incomplets, JSON.stringify(g20b));
  await p.evaluate(() => document.activeElement.blur());
  await reinitialiser(p);

  // L. Un seul verdict par écran : la puce de l'échéance suit le groupe ouvert.
  /* Un jalon entre les fins des groupes : tenu pour l'ensemble et pour
     certains ATA, manqué pour d'autres — le test compare des deux côtés. */
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.jalons = [{ semaine: '2027-S10', date: '2027-03-12', texte: 'Jalon de test' }];
    window.__chargerSource(s);
  });
  await p.waitForTimeout(500);
  const verdicts20 = await p.evaluate(async () => {
    const att = ms => new Promise(r => setTimeout(r, ms));
    const res = [];
    const groupes = [...document.querySelectorAll('.critique-ligne')].map(l => l.dataset.groupe);
    for (const g of groupes) {
      /* Débrief 27 (lot C) : déplier, puis filtrer la page sur le groupe. */
      [...document.querySelectorAll('.critique-ligne')].find(l => l.dataset.groupe === g).click();
      document.getElementById('filtrer-groupe-page').click();
      await att(150);
      const pill = document.getElementById('echeance-titre');
      const prochain = window.__prochainJalon();
      const idx = [...document.querySelectorAll('.legende-jalon')].findIndex(x => x.querySelector('.mot').textContent === prochain.texte);
      const svg = document.querySelector('svg.graphe .jalon[data-jalon="' + idx + '"]');
      res.push({ g, retard: pill.classList.contains('en-retard'), texte: pill.textContent,
        legende: document.querySelectorAll('.legende-jalon')[idx].classList.contains('critique'),
        svg: svg ? svg.classList.contains('critique') : null });
      document.getElementById('filtrer-groupe-page').click();
      [...document.querySelectorAll('.critique-ligne')].find(l => l.dataset.groupe === g).click();
      await att(120);
    }
    return res;
  });
  verifier('L — pour chaque ATA ouvert : le point de la puce « Prochaine échéance » a la couleur du jalon sur le graphique et dans sa légende, et la puce nomme le groupe',
    verdicts20.length >= 5 && verdicts20.every(v => v.retard === v.legende && (v.svg === null || v.svg === v.retard) && v.texte.indexOf('ATA ' + v.g) !== -1),
    JSON.stringify(verdicts20.filter(v => !(v.retard === v.legende && (v.svg === null || v.svg === v.retard) && v.texte.indexOf('ATA ' + v.g) !== -1))));
  const groupeTenu = verdicts20.find(v => !v.retard), groupeTard = verdicts20.find(v => v.retard);
  verifier('L — l’exemple a des groupes des deux sortes : le test compare vraiment', !!groupeTenu && !!groupeTard, JSON.stringify(verdicts20.map(v => v.g + ':' + v.retard)));
  if (groupeTenu) {
    await p.evaluate(g => [...document.querySelectorAll('.critique-ligne')].find(l => l.dataset.groupe === g).click(), groupeTenu.g); await p.waitForTimeout(400);
    await p.click('#filtrer-groupe-page'); await p.waitForTimeout(400);
    await p.click('#echeance-titre'); await p.waitForTimeout(400);
    const fiche20 = await p.evaluate(() => { const f = document.getElementById('fiche-echeance');
      return f ? { quand: f.querySelector('.quand').textContent, bon: f.querySelector('.fiche-echeance-verdict').classList.contains('bon'),
                   verdict: f.querySelector('.fiche-echeance-verdict').textContent } : null; });
    verifier('L — sous ce groupe, la fiche de l’échéance le nomme et dit le même verdict que la puce (tenue)',
      !!fiche20 && fiche20.quand.indexOf('ATA ' + groupeTenu.g) !== -1 && fiche20.bon && /tenue dans ATA/.test(fiche20.verdict), JSON.stringify(fiche20));
    await p.click('#echeance-titre'); await p.waitForTimeout(300);
  }
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(500);
  await reinitialiser(p);

  // W. « au rythme global », et le dernier groupe nommé quand il finit plus tard.
  await p.click('#echeance-titre'); await p.waitForTimeout(400);
  const w20 = await p.evaluate(() => {
    const esp = t => String(t || '').replace(/[\u00a0\u202f]/g, ' ').replace(/\s+/g, ' ').trim();
    const v = esp((document.querySelector('#fiche-echeance .fiche-echeance-verdict') || {}).textContent);
    const fins = [...document.querySelectorAll('.critique-ligne')].map(l => ({ g: l.dataset.groupe, fin: esp(l.querySelector('.critique-date .v').textContent) }))
      .filter(x => /^S\d+/.test(x.fin));
    const rang = f => { const m = f.match(/^S(\d+) · \S+ (\d{4})$/); return m ? +m[2] * 100 + +m[1] : 0; };
    fins.sort((a, b) => rang(b.fin) - rang(a.fin));
    /* Débrief 27 (P-F18) : « tout serait validé en … » (plus « au rythme global, la fin serait en … »). */
    return { v, dernier: fins[0], globale: (v.match(/tout serait validé en (S\d+ · \S+ \d{4})/) || [])[1] };
  });
  verifier('W — la fiche dit « tout serait validé en … » et nomme le dernier groupe, à la fin que montre le bloc',
    !!w20.globale && !!w20.dernier && w20.v.indexOf('le dernier groupe (ATA ' + w20.dernier.g + ') finirait en ' + w20.dernier.fin) !== -1, JSON.stringify(w20));
  await p.click('#echeance-titre'); await p.waitForTimeout(300);

  // M. Vue d'ensemble : sous « tenue », la fin du bilan de l'échéance, sur son périmètre.
  await p.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.jalons = [{ semaine: '2027-S40', date: '2027-10-01', texte: 'Jalon lointain', perimetre: 'BASE/OPTION' }];
    window.__chargerSource(s);
  });
  await p.waitForTimeout(500);
  await p.click('#echeance-titre'); await p.waitForTimeout(400);
  const ficheLoin = await p.evaluate(() => String((document.querySelector('#fiche-echeance .fiche-echeance-verdict') || {}).textContent).replace(/[\u00a0\u202f]/g, ' '));
  await p.click('#voir-ensemble'); await p.waitForTimeout(1500);
  /* Débrief 27 (lot H, P-F18) : « Au rythme tenu » est coupée en deux
     colonnes — « À l'échéance » (tenue, ou manque N) puis « Fin au rythme
     actuel » (la semaine, et le périmètre du jalon). */
  const ens20 = await p.evaluate(() => [...document.querySelectorAll('#ensemble tbody tr')].map(tr => {
    const td = [...tr.querySelectorAll('td')].map(c => c.textContent.replace(/[\u00a0\u202f]/g, ' '));
    return { echeance: td[td.length - 2], fin: td[td.length - 1] };
  }));
  await p.click('#ensemble button[data-fermer-ensemble]'); await p.waitForTimeout(200);
  const finLoin = (ficheLoin.match(/tout serait validé en (S\d+ · \S+ \d{4})/) || [])[1];   // débrief 27 (P-F18)
  verifier('M — vue d’ensemble, échéance tenue : « tenue » à l’échéance, et la fin écrite est celle de la fiche, sur le périmètre du jalon, qui est nommé',
    !!finLoin && /^tenue/.test(ens20[0].echeance) && ens20[0].fin.indexOf(finLoin) === 0 && /pour BASE\/OPTION/.test(ens20[0].fin), JSON.stringify([ficheLoin, ens20[0]]));
  verifier('M — un contrat sans jalon garde la fin de tout le contrat', /^S\d+ · \S+ \d{4}$/.test(ens20[1].fin) && ens20[1].echeance === '—', JSON.stringify(ens20[1]));
  await p.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await p.waitForTimeout(500);
  await reinitialiser(p);

  // X. Un verdict cliqué montre exactement son nombre, même avec un groupe ouvert.
  /* Débrief 27 (lot C) : ouvrir un groupe ne filtre plus la page ; c'est le
     filtre de la page posé sur lui (son bouton) que le verdict retire — la
     ligne, elle, peut rester dépliée. */
  await p.evaluate(() => document.querySelector('.critique-ligne').click()); await p.waitForTimeout(400);
  await p.click('#filtrer-groupe-page'); await p.waitForTimeout(500);
  await p.click('#verdicts-rapprochement button[data-rapp="avance"]'); await p.waitForTimeout(600);
  const x20 = await p.evaluate(() => ({ lignes: document.querySelectorAll('#corps-tableau tr').length,
    filtre: !!document.querySelector('.critique-ligne.filtre-page'),
    jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()) }));
  verifier('X — page filtrée sur un groupe, clic sur « 12 dans SEE, mais GATES ne les dit pas validés » : le filtre du groupe se retire, le tableau montre 12 lignes',
    x20.lignes === AVANCE && !x20.filtre && x20.jetons.length === 1 && /^Comparaison/.test(x20.jetons[0]), JSON.stringify(x20));

  // AA. Sous un verdict déplié, la légende ne nomme que les valeurs de sa liste.
  const aa20 = await p.evaluate(() => {
    const corps = document.querySelector('#verdicts-rapprochement .verdict-corps[data-lot="avance"]');
    /* Débrief 27 (lot E, D9) : chaque valeur de la légende porte son compte
       (<b class="n">) — la répartition que seule la bulle du survol donnait. */
    const items = [...corps.querySelectorAll('.rapp-puces-legende > span')].map(s => {
      const n = s.querySelector('.n'), t = s.textContent;
      return { mot: t.slice(0, t.length - (n ? n.textContent.length : 0)).trim(), n: n ? +n.textContent.replace(/\s/g, '') : null };
    });
    const legende = items.map(x => x.mot);
    const parRef = {}, compte = {};
    [...document.querySelectorAll('#corps-tableau tr')].forEach(tr => { parRef[tr.querySelector('td.ref').textContent.trim()] = tr.querySelector('.etat-cellule').textContent.trim(); });
    [...corps.querySelectorAll('.rapp-puce[data-plan-rapp]')].forEach(b => { const v = parRef[b.dataset.planRapp]; compte[v] = (compte[v] || 0) + 1; });
    const valeurs = Object.keys(compte);
    return { legende, valeurs, comptesJustes: items.every(x => x.n === compte[x.mot]), items };
  });
  verifier('AA — légende du verdict déplié : seulement les valeurs présentes, écrites comme dans la colonne, chacune avec son compte',
    aa20.legende.length >= 2 && aa20.legende.slice().sort().join() === aa20.valeurs.slice().sort().join() && aa20.comptesJustes, JSON.stringify(aa20));

  // P1. « Copier (n) » sur les listes de références.
  await p.evaluate(() => {
    window.__copies = [];
    try { navigator.clipboard.writeText = t => { window.__copies.push(t); return Promise.resolve(); }; }
    catch (e) { Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: t => { window.__copies.push(t); return Promise.resolve(); } } }); }
  });
  const copieLot = await p.evaluate(async () => {
    const b = document.querySelector('#verdicts-rapprochement .verdict-corps[data-lot="avance"] button[data-copier]');
    const refs = [...document.querySelectorAll('#verdicts-rapprochement .verdict-corps[data-lot="avance"] .rapp-puce-ref')].map(x => x.textContent);
    const avant = b.textContent;
    b.click(); await new Promise(r => setTimeout(r, 100));
    return { avant, apres: b.textContent, copie: window.__copies[0], refs: refs.join('\n'), imbrique: !!b.parentElement.closest('button') };
  });
  verifier('P1 — verdict déplié : « Copier (12) » met les 12 références dans le presse-papiers, une par ligne, puis dit « Copié »',
    copieLot.avant === 'Copier (' + AVANCE + ')' && copieLot.apres === 'Copié' && copieLot.copie === copieLot.refs && !copieLot.imbrique, JSON.stringify(copieLot).slice(0, 300));
  await p.waitForTimeout(2200);
  verifier('P1 — deux secondes après, le bouton redit « Copier (12) »',
    await p.evaluate(() => document.querySelector('#verdicts-rapprochement .verdict-corps[data-lot="avance"] button[data-copier]').textContent) === 'Copier (' + AVANCE + ')');
  await reinitialiser(p);
  // Au clavier, dans un groupe déplié : Entrée sur le bouton.
  await p.evaluate(() => document.querySelector('.critique-ligne').click()); await p.waitForTimeout(500);
  await p.focus('#zone-critique .groupe-refs button[data-copier]');
  await p.keyboard.press('Enter'); await p.waitForTimeout(200);
  const copieGroupe = await p.evaluate(() => ({ copie: window.__copies[window.__copies.length - 1],
    refs: [...document.querySelectorAll('#zone-critique .groupe-refs .jeton-ud')].map(b => b.dataset.ud).join('\n'),
    imbrique: !!document.querySelector('#zone-critique button button, #zone-critique button [data-copier]') }));
  verifier('P1 — groupe déplié, au clavier : toutes ses références, dans l’ordre affiché ; jamais un bouton dans un bouton',
    !!copieGroupe.copie && copieGroupe.copie === copieGroupe.refs && !copieGroupe.imbrique, JSON.stringify(copieGroupe).slice(0, 300));
  await reinitialiser(p);
  // Une semaine du journal, et la voie de secours quand le navigateur refuse le presse-papiers.
  const copieJournal = await p.evaluate(async () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: () => Promise.reject(new Error('refusé')) } });
    let secours = null;
    document.execCommand = c => { secours = c === 'copy' ? document.activeElement.value : null; return true; };
    document.querySelector('#zone-journal button[data-semaine]').click();
    await new Promise(r => setTimeout(r, 300));
    const b = document.querySelector('#zone-journal .journal-copier button[data-copier]');
    b.click(); await new Promise(r => setTimeout(r, 200));
    return { n: +b.textContent.replace(/\D/g, '') || null, texte: b.textContent, secours, lignes: secours ? secours.split('\n').length : 0,
             affichees: document.querySelectorAll('#zone-journal .journal-liste .journal-ligne').length };
  });
  verifier('P1 — semaine du journal dépliée : toutes ses références (même au-delà des douze affichées), par la voie de secours si le presse-papiers est refusé',
    copieJournal.texte === 'Copié' && copieJournal.lignes > 0 && copieJournal.lignes >= copieJournal.affichees, JSON.stringify(copieJournal).slice(0, 300));
  await p.evaluate(() => { delete document.execCommand; document.querySelector('#zone-journal button[data-semaine][aria-expanded="true"]').click(); });
  await p.waitForTimeout(300);

  // P2. « n à l'arrêt » d'un groupe est un bouton ; dans le groupe déplié, ils viennent en tête.
  const arretG = await p.evaluate(() => {
    const b = document.querySelector('#zone-critique button[data-arret-groupe]');
    const place = b.parentElement.previousElementSibling.querySelector('.arret-n.place');
    const rb = b.getBoundingClientRect(), rp = place.getBoundingClientRect();
    return { g: b.dataset.arretGroupe, n: parseInt(b.textContent, 10), dx: Math.abs((rb.left + rb.right) / 2 - (rp.left + rp.right) / 2), dy: Math.abs(rb.bottom - rp.bottom),
             imbrique: !!b.parentElement.closest('button') };
  });
  verifier('P2 — « n à l’arrêt » sous le compte d’un groupe : un vrai bouton, hors du bouton de la ligne, posé à la place que la ligne lui garde',
    arretG.n > 0 && !arretG.imbrique && arretG.dx < 2 && arretG.dy < 2, JSON.stringify(arretG));
  await p.evaluate(g => [...document.querySelectorAll('#zone-critique button[data-arret-groupe]')].find(b => b.dataset.arretGroupe === g).click(), arretG.g);
  await p.waitForTimeout(600);
  const p20 = await p.evaluate(g => ({
    lignes: document.querySelectorAll('#corps-tableau tr').length,
    etats: [...new Set([...document.querySelectorAll('#corps-tableau .etat-cellule')].map(x => x.textContent.trim()))].join(),
    ouvert: (document.querySelector('.critique-ligne[aria-expanded="true"]') || {}).dataset,
    presse: ([...document.querySelectorAll('#zone-critique button[data-arret-groupe]')].find(b => b.dataset.arretGroupe === g) || {}).getAttribute('aria-pressed'),
    surveiller: (document.getElementById('a-surveiller').textContent.match(/(\d+) plans?/) || [])[1],
    jetons: [...document.querySelectorAll('.jeton')].map(j => j.textContent.replace('×', '').trim()),
    /* Débrief 28 : sous l'en-tête du groupe vient la ligne de ses gestes
       (.actions-groupe : filtrer la page, copier) ; la première liste est
       celle qui la suit. */
    premier: (([...((document.querySelector('#zone-critique .groupe-refs') || {}).children || [])].filter(c => !c.classList.contains('entete') && !c.classList.contains('actions-groupe'))[0]) || {}).className,
    titre: ((document.querySelector('#zone-critique .groupe-refs .titre-arret') || {}).textContent || '').replace(/[\u00a0\u202f]/g, ' '),
    depuis: [...document.querySelectorAll('#zone-critique .groupe-refs .sous-arret .jeton-ud')].map(b => (b.querySelector('.depuis') || {}).textContent)
  }), arretG.g);
  verifier('P2 — un clic ne montre que ces plans : n lignes, toutes en cours, le groupe ouvert, « À surveiller » limité au groupe',
    p20.lignes === arretG.n && p20.etats === 'En cours' && p20.ouvert && p20.ouvert.groupe === arretG.g && p20.presse === 'true' && Number(p20.surveiller) === arretG.n &&
    p20.jetons.some(j => /^À surveiller/.test(j)) && p20.jetons.some(j => j.indexOf(arretG.g) !== -1), JSON.stringify(p20));
  verifier('P2 — dans le groupe déplié, les plans à l’arrêt viennent d’abord, sous « À l’arrêt », chacun avec « depuis Sxx » (« depuis ≤ Sxx » quand le début n’est pas connu)',
    p20.premier === 'sous-arret' && /^À l’arrêt/.test(p20.titre) && p20.depuis.length === arretG.n && p20.depuis.every(t => /^depuis (≤\u00a0)?S\d{1,2}$/.test(t)), JSON.stringify(p20));
  await p.evaluate(g => [...document.querySelectorAll('#zone-critique button[data-arret-groupe]')].find(b => b.dataset.arretGroupe === g).click(), arretG.g);
  await p.waitForTimeout(500);
  /* Débrief 27 (lot C) : le second clic défait tout ce que le premier a
     posé — la sélection et le filtre de la page sur le groupe — ; la ligne
     reste dépliée (elle ne filtre plus rien par elle-même). */
  const p20b = await p.evaluate(() => ({ lignes: document.querySelectorAll('#corps-tableau tr').length, ouvert: !!document.querySelector('.critique-ligne[aria-expanded="true"]'),
    jetons: document.querySelectorAll('#filtres-actifs .jeton').length }));
  verifier('P2 — un second clic retire le filtre (sélection et groupe) et laisse le groupe déplié', p20b.ouvert && p20b.lignes === TOTAL && p20b.jetons === 0, JSON.stringify(p20b));
  await reinitialiser(p);

  // P3. La réponse sous le titre de la comparaison.
  const p30 = await p.evaluate(async () => {
    const att = ms => new Promise(r => setTimeout(r, ms));
    const esp = t => String(t || '').replace(/[\u00a0\u202f]/g, ' ').replace(/\s+/g, ' ').trim();
    const res = [];
    for (const per of ['', 'BASE/OPTION', 'PERSO']) {
      document.querySelector('#choix-perimetre button[data-perimetre="' + per + '"]').click(); await att(300);
      const R = window.__rapprochement(), z = document.getElementById('reponse-rapprochement');
      const parts = [];
      if (R.manque.length) parts.push(R.manque.length + (R.manque.length > 1 ? ' plans validés absents de SEE' : ' plan validé absent de SEE'));
      if (R.avance.length) parts.push(R.avance.length + (R.avance.length > 1 ? ' plans dans SEE que GATES ne dit pas validés' : ' plan dans SEE que GATES ne dit pas validé'));
      res.push({ per, attendu: parts.length ? 'À traiter : ' + parts.join(' · ') : '', vu: z.hidden ? '' : esp(z.textContent) });
    }
    document.querySelector('#choix-perimetre button[data-perimetre=""]').click(); await att(300);
    return res;
  });
  verifier('P3 — « À traiter : 3 plans validés absents de SEE · 12 plans dans SEE que GATES ne dit pas validés », une part à 0 omise, sur chaque périmètre',
    p30[0].vu === 'À traiter : ' + MANQUE + ' plans validés absents de SEE · ' + AVANCE + ' plans dans SEE que GATES ne dit pas validés' &&
    p30.every(x => x.vu === x.attendu), JSON.stringify(p30));
  await p.click('#reponse-rapprochement button[data-rapp="manque"]'); await p.waitForTimeout(600);
  const p30b = await p.evaluate(() => ({ lignes: document.querySelectorAll('#corps-tableau tr').length,
    verdict: document.querySelector('#verdicts-rapprochement button[data-rapp="manque"]').getAttribute('aria-pressed'),
    deplie: document.querySelector('#verdicts-rapprochement .verdict-bloc[data-lot="manque"]').dataset.ouvert,
    focus: document.activeElement.closest('#reponse-rapprochement') !== null }));
  verifier('P3 — cliquer « 3 » fait ce que fait sa ligne de verdict : le tableau montre les 3 plans, le verdict est posé et déplié',
    p30b.lignes === MANQUE && p30b.verdict === 'true' && p30b.deplie === 'true' && p30b.focus, JSON.stringify(p30b));
  await reinitialiser(p);

  // AB. Un seul bouton de remise à zéro.
  const ab20 = await p.evaluate(() => ({ reinit: !!document.getElementById('reinit'),
    mots: [...document.querySelectorAll('button')].filter(b => /réinitialiser/i.test(b.textContent)).length }));
  verifier('AB — plus de « tout réinitialiser » à côté de « Vue essentielle » : « Tout effacer », dans le bandeau des filtres, reste seul',
    !ab20.reinit && ab20.mots === 0, JSON.stringify(ab20));

  // =================================================================
  section('Stockage local corrompu ou indisponible');
  const ctxCorrompu = await contexte();
  let pc = await ctxCorrompu.newPage();
  brancher(pc, 'corrompu');
  await pc.goto(URL); await pc.waitForTimeout(600);
  await pc.evaluate(() => localStorage.setItem('suivi-fwd:v1', '{ceci n\'est pas du JSON'));
  await pc.reload(); await attendrePrete(pc, 1300);
  verifier('un stockage illisible ne bloque pas le démarrage',
    await pc.evaluate(t => (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length) === t, TOTAL));
  await pc.evaluate(() => localStorage.setItem('suivi-fwd:v1', JSON.stringify({
    jalons: [{ i: 'pas un nombre', texte: 42 }, null, { i: 99999 }, { semaine: '2026-S50', texte: '<b>stocké</b>' }],
    fen: { debut: 'x' }, tri: { cle: '__proto__' }, triGroupe: { cle: 'rm -rf', asc: 'oui' },
    ordre: ['inexistante'], cachees: { reference: true },
    /* Débrief 27 : l'extract entier, pour que la vérification porte sur « cachees ». */
    vueTable: 'toutes', videsMontrees: true
  })));
  await pc.reload(); await attendrePrete(pc, 1300);
  await pc.click('.segmente button[data-span="0"]'); await pc.waitForTimeout(400);
  const survie = await pc.evaluate(() => ({
    lignes: (document.querySelector('#corps-tableau .vide-message') ? 0 : document.querySelectorAll('#corps-tableau tr').length),
    colonnes: document.querySelectorAll('tr.titres th').length,
    refVisible: !!document.querySelector('tr.titres th[data-cle="reference"]'),
    triActif: [...document.querySelectorAll('button[data-trig][data-actif="true"]')].map(b => b.dataset.trig).join(','),
    jalons: [...document.querySelectorAll('.jalon-texte')].map(t => t.textContent)
  }));
  verifier('des préférences absurdes sont ignorées sans plantage', survie.lignes === TOTAL, survie.lignes + ' lignes');
  verifier('des jalons laissés dans un ancien stockage ne sont pas relus',
    survie.jalons.length === 5 && !survie.jalons.some(t => /stock/.test(t)), JSON.stringify(survie.jalons));
  verifier('une ancienne clé « cachees » est ignorée : les 137 colonnes restent présentes',
    survie.colonnes === COLONNES_TOTAL, survie.colonnes + ' colonnes');
  verifier('la référence UD ne peut pas être masquée par le stockage', survie.refVisible);
  verifier('une clé de tri inconnue n\'est pas appliquée : le bloc reste rangé par nom', survie.triActif === 'nom', survie.triActif);
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
  section('Débrief 20 : un graphique lisible à toute largeur');
  /* Le graphique se dessinait sur 980 unités puis se laissait réduire :
     3,5 px de texte sur un téléphone, 7 px dans une demi-fenêtre au bureau.
     Il se dessine maintenant à la largeur de son cadre, et ses mots ne se
     chevauchent ni ne se font barrer par un trait, à toutes les largeurs,
     dans les deux thèmes. */
  const lireDessin20 = () => document.querySelector('svg.graphe') && (() => {
    const svg = document.querySelector('svg.graphe');
    const rs = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal;
    const echelle = rs.width / vb.width;
    const boites = [...svg.querySelectorAll('text')]
      .filter(t => !t.classList.contains('masque') && t.textContent.trim())
      .map(t => { const b = t.getBoundingClientRect();
        return { t: t.textContent.trim().slice(-24), g: b.left, d: b.right, h: b.top, b: b.bottom,
                 px: parseFloat(getComputedStyle(t).fontSize) * echelle, nominal: parseFloat(getComputedStyle(t).fontSize) }; });
    const croisent = (a, c) => a.g < c.d - 0.5 && c.g < a.d - 0.5 && a.h < c.b - 0.5 && c.h < a.b - 0.5;
    const chevauchements = [];
    for (let i = 0; i < boites.length; i++) for (let j = i + 1; j < boites.length; j++) {
      if (croisent(boites[i], boites[j])) chevauchements.push(boites[i].t + ' / ' + boites[j].t);
    }
    /* Les traits verticaux : jalons et dernier relevé. Un mot posé sur un
       fond plein qui cache le trait n'est pas barré. */
    const traits = [...svg.querySelectorAll('line')]
      .filter(l => l.getAttribute('x1') === l.getAttribute('x2') && Math.abs(l.getAttribute('y1') - l.getAttribute('y2')) > 30)
      .map(l => l.getBoundingClientRect());
    const fonds = [...svg.querySelectorAll('rect.fond-mot')].map(r => r.getBoundingClientRect());
    const barres = [];
    boites.forEach(a => traits.forEach(tr => {
      if (tr.left > a.g + 0.5 && tr.left < a.d - 0.5 && tr.top < a.b && tr.bottom > a.h &&
          !fonds.some(f => f.left <= a.g + 1 && f.right >= a.d - 1 && f.top <= a.h + 3 && f.bottom >= a.b - 3)) barres.push(a.t);
    }));
    return {
      vb: vb.width, largeur: Math.round(rs.width),
      tailles: boites.every(a => Math.abs(a.px - a.nominal) < 0.2), pxMin: Math.min(...boites.map(a => a.px)),
      chevauchements, barres,
      dehors: boites.filter(a => a.g < rs.left - 1 || a.d > rs.right + 1).map(a => a.t),
      graduations: boites.filter(a => /^S\d+$/.test(a.t)).length
    };
  })();
  const largeurs20 = [];
  for (const theme of ['light', 'dark']) {
    const ctxL = await contexte({ colorScheme: theme });
    const pl = await page(ctxL, 'graphique ' + theme);
    for (const w of [360, 768, 1024, 1440, 1920]) {
      await redimensionner(pl, w, 950);
      largeurs20.push(Object.assign({ theme, w }, await pl.evaluate(lireDessin20)));
    }
    await ctxL.close();
  }
  verifier('débrief 20 : le graphique se dessine à la largeur de son cadre — une unité pour un pixel, redessiné quand la fenêtre change',
    largeurs20.every(x => Math.abs(x.vb - x.largeur) <= 1) && new Set(largeurs20.map(x => x.vb)).size >= 4,
    JSON.stringify(largeurs20.map(x => [x.theme, x.w, x.vb, x.largeur])));
  /* Débrief 27 (D2) : plus aucun mot du graphique sous 11 px (l'année
     faisait 10 px). */
  verifier('débrief 20 : ses mots gardent leur taille (11 px au moins) à 360, 768, 1024, 1440 et 1920 px',
    largeurs20.every(x => x.tailles && x.pxMin >= 10.9), JSON.stringify(largeurs20.map(x => [x.theme, x.w, x.pxMin.toFixed(1)])));
  verifier('débrief 20 : aucun mot n’en chevauche un autre, aucun ne sort du cadre, à toutes les largeurs et dans les deux thèmes',
    largeurs20.every(x => !x.chevauchements.length && !x.dehors.length),
    JSON.stringify(largeurs20.filter(x => x.chevauchements.length || x.dehors.length).map(x => [x.theme, x.w, x.chevauchements, x.dehors])));
  verifier('débrief 20 : aucun mot barré par le trait d’un jalon ou du dernier relevé',
    largeurs20.every(x => !x.barres.length), JSON.stringify(largeurs20.filter(x => x.barres.length).map(x => [x.theme, x.w, x.barres])));
  const grad20 = largeurs20.filter(x => x.theme === 'light').map(x => x.graduations);
  verifier('débrief 20 : moins de graduations sur un cadre étroit, une dizaine sur un grand écran',
    grad20[0] >= 3 && grad20[0] < grad20[grad20.length - 1] && grad20[grad20.length - 1] >= 8, JSON.stringify(grad20));

  /* Sur un cadre étroit, le survol et le zoom visent toujours la bonne
     semaine : la bulle du point du dernier relevé dit sa semaine. */
  const ctxEtroit = await contexte({ viewport: { width: 390, height: 900 } });
  const pe = await page(ctxEtroit, 'graphique étroit');
  const zoneAuj20 = await pe.evaluate(() => {
    const zones = [...document.querySelectorAll('svg.graphe .zone-clic')];
    // La bande la plus à droite qui porte un nombre de validés : le dernier relevé.
    const z = zones.filter(r => / : \d+ validés$/.test(r.getAttribute('aria-label'))).pop();
    z.scrollIntoView({ block: 'center' });
    const b = z.getBoundingClientRect();
    return { x: b.left + b.width / 2, y: b.top + b.height / 2, libelle: z.getAttribute('aria-label') };
  });
  await pe.mouse.move(zoneAuj20.x, zoneAuj20.y); await pe.waitForTimeout(250);
  const bulle20 = await pe.evaluate(() => ({ visible: document.getElementById('bulle').dataset.visible, tete: (document.querySelector('#bulle .tete-bulle') || {}).textContent || '' }));
  verifier('débrief 20 : à 390 px, le survol du dernier relevé ouvre la bulle de sa semaine',
    bulle20.visible === 'true' && bulle20.tete.indexOf(zoneAuj20.libelle.split(' : ')[0]) !== -1, JSON.stringify([zoneAuj20.libelle, bulle20]));

  /* La molette en zoom arrière s'arrête à la largeur de « Tout » (elle
     allait jusqu'à deux ans, la moitié du graphique vide). */
  await redimensionner(pe, 1280, 950);
  await pe.click('.segmente button[data-span="0"]'); await pe.waitForTimeout(350);
  const nTout20 = await pe.evaluate(() => document.querySelectorAll('svg.graphe .zone-clic').length);
  await pe.click('.segmente button[data-span="26"]'); await pe.waitForTimeout(350);
  await pe.evaluate(() => document.getElementById('cadre-graphe').scrollIntoView({ block: 'center' })); await pe.waitForTimeout(150);   // débrief 27 : à l'écran
  const boiteZ = await (await pe.$('svg.graphe')).boundingBox();
  await pe.mouse.move(boiteZ.x + boiteZ.width / 2, boiteZ.y + boiteZ.height / 2);
  await pe.keyboard.down('Control');   // débrief 27 : le zoom passe par Ctrl + molette
  for (let i = 0; i < 40; i++) await pe.mouse.wheel(0, 400);
  await pe.keyboard.up('Control');
  await pe.waitForTimeout(400);
  const molette20 = await pe.evaluate(() => ({
    n: document.querySelectorAll('svg.graphe .zone-clic').length,
    presses: [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')].map(b => b.textContent.trim()).join()
  }));
  verifier('débrief 20 : 40 crans de zoom arrière s’arrêtent à la fenêtre de « Tout », qui se marque pressé',
    molette20.n === nTout20 && molette20.presses === 'Tout', JSON.stringify([nTout20, molette20]));
  await pe.click('.segmente button[data-span="52"]'); await pe.waitForTimeout(350);
  await pe.evaluate(() => document.getElementById('cadre-graphe').scrollIntoView({ block: 'center' })); await pe.waitForTimeout(150);   // débrief 27 : à l'écran
  const boiteAn = await (await pe.$('svg.graphe')).boundingBox();
  await pe.mouse.move(boiteAn.x + boiteAn.width / 2, boiteAn.y + boiteAn.height / 2);
  await pe.keyboard.down('Control');   // débrief 27
  for (let i = 0; i < 10; i++) await pe.mouse.wheel(0, 400);
  await pe.keyboard.up('Control');
  await pe.waitForTimeout(400);
  const an20 = await pe.evaluate(() => document.querySelectorAll('svg.graphe .zone-clic').length);
  verifier('débrief 20 : depuis « 1 an », plus large que « Tout », la molette n’élargit ni ne rétrécit en zoom arrière',
    an20 === 52, an20 + ' semaines');

  /* Le bout de la projection : un losange plein du vert du réalisé, plus
     un petit cercle creux qu'on lisait « jalon 5 atteint » ; « fin … » ne
     se pose ni en travers d'un jalon ni sur « 640 plans ». */
  /* Le jeu d'exemple a des relevés datés : la projection du rythme tenu ne
     finit dans la fenêtre « Échéances » qu'à la date où ce test a été écrit
     (semaine 41). Plus tard, son bout sort à droite, et c'est juste de ne
     pas le dessiner : l'horloge de cette page est donc arrêtée à cette date. */
  const ctxFin20 = await contexte({ viewport: { width: 390, height: 900 } });
  await ctxFin20.clock.setFixedTime(new Date('2026-10-06T09:00:00'));
  const pf20 = await page(ctxFin20, 'bout de la projection');
  await pf20.click('.segmente button[data-span="jalons"]'); await pf20.waitForTimeout(350);
  const fin20 = await pf20.evaluate(() => {
    const svg = document.querySelector('svg.graphe');
    const mot = svg.querySelector('.fin-mot'), bout = svg.querySelector('.fin-projection');
    const b = mot ? mot.getBoundingClientRect() : null;
    const traits = [...svg.querySelectorAll('.jalon line:not(.jalon-lien)')].map(l => l.getBoundingClientRect().left);
    const plafond = [...svg.querySelectorAll('text')].filter(t => / plans$/.test(t.textContent))[0];
    const p = plafond ? plafond.getBoundingClientRect() : null;
    return { mot: mot ? mot.textContent : '', bout: bout ? bout.tagName + ':' + bout.getAttribute('fill') : '',
             cerclesCreux: svg.querySelectorAll('circle[fill="none"]').length,
             barre: !!b && traits.some(x => x > b.left && x < b.right),
             surPlafond: !!b && !!p && b.left < p.right && p.left < b.right && b.top < p.bottom - 0.5 && p.top < b.bottom - 0.5 };
  });
  verifier('débrief 20 : le bout de la projection est un losange plein (vert du réalisé), « fin … » n’est barré par aucun jalon ni posé sur « 640 plans »',
    /^fin S\d+/.test(fin20.mot) && fin20.bout === 'path:var(--fait)' && fin20.cerclesCreux === 0 && !fin20.barre && !fin20.surPlafond, JSON.stringify(fin20));
  await ctxFin20.close();

  /* Tout validé : pas de projection (« fin S40 » s'écrivait sur un groupe
     fini), et le nombre du dernier point s'écrit sous lui, pas sur
     « dernier relevé ». */
  await pe.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    s.plans.forEach(x => { x.avancement = 'Terminé'; });
    const r = s.releves[s.releves.length - 1];
    r.termine = r.total; r.encours = r.afaire = r.vide = 0;
    window.__chargerSource(s);
  });
  await pe.waitForTimeout(500);
  const plein20 = await pe.evaluate(() => {
    const svg = document.querySelector('svg.graphe');
    const n = svg.querySelector('.nombre-point'), a = svg.querySelector('.repere-auj');
    const bn = n.getBoundingClientRect(), ba = a.getBoundingClientRect(), bs = svg.getBoundingClientRect();
    return { fin: svg.querySelectorAll('.fin-mot, .fin-projection, circle[fill="none"]').length + [...svg.querySelectorAll('text')].filter(t => /^fin /.test(t.textContent)).length,
             nombre: n.textContent, total: window.__serieAffichee().pts.slice(-1)[0].total,
             surRepere: bn.left < ba.right && ba.left < bn.right && bn.top < ba.bottom && ba.top < bn.bottom,
             dansLeCadre: bn.top >= bs.top, sousLePoint: bn.top > n.previousElementSibling.getBoundingClientRect().top,
             legende: document.getElementById('legende').textContent };
  });
  verifier('débrief 20 : tout validé — ni « fin … » ni bout de projection',
    plein20.fin === 0 && !/rythme tenu/.test(plein20.legende), JSON.stringify(plein20));
  verifier('débrief 20 : à 100 %, le nombre du dernier point s’écrit sous lui, pas sur « dernier relevé »',
    +plein20.nombre === plein20.total && !plein20.surRepere && plein20.dansLeCadre && plein20.sousLePoint, JSON.stringify(plein20));

  /* Rien de validé depuis le premier relevé : pas de projection, donc pas
     de « au rythme tenu (0,0/sem.) » ni de trait pointillé en légende. */
  await pe.evaluate(() => {
    const s = window.__jeuDExemple('HDK');
    const dernier = JSON.stringify(s.releves[s.releves.length - 1]);
    s.releves = s.releves.map(r => Object.assign(JSON.parse(dernier), { semaine: r.semaine }));
    window.__chargerSource(s);
  });
  await pe.waitForTimeout(500);
  const plat20 = await pe.evaluate(() => {
    const leg = document.getElementById('legende');
    /* Débrief 27 (X-A8) : la droite « requis » a son trait-point (8 3 2 3), en légende aussi — seul compte le pointillé de la projection. */
    return { legende: leg.textContent, pointilles: leg.querySelectorAll('line[stroke-dasharray]:not([stroke-dasharray="8 3 2 3"])').length,
             projection: document.querySelectorAll('svg.graphe path[stroke-dasharray="5 4"]').length,
             item: !!leg.querySelector('.sans-rythme') && !leg.querySelector('.sans-rythme svg') };
  });
  verifier('débrief 20 : rien de validé depuis le premier relevé — la légende le dit, sans pastille ni « 0,0/sem. », et aucune projection n’est tracée',
    /rien de validé depuis le premier relevé/.test(plat20.legende) && !/rythme tenu/.test(plat20.legende) && plat20.pointilles === 0 &&
    plat20.projection === 0 && plat20.item, JSON.stringify(plat20));
  await pe.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
  await ctxEtroit.close();

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
  /* Débrief 27 (lot C, X-A6) : une ligne se déplie — aria-expanded, et
     aria-controls vers sa liste quand elle est ouverte. */
  verifier('les lignes de groupe exposent aria-expanded (elles se déplient)',
    await pk.evaluate(() => [...document.querySelectorAll('.critique-ligne')].every(b => b.hasAttribute('aria-expanded') && !b.hasAttribute('aria-pressed'))));
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
  /* Débrief 27, lot G — l'accessibilité de toute la page (liens
     d'évitement, région principale, sections nommées), l'aide « Comment
     lire cette page », Échap qui ferme le panneau du dessus, le lien de la
     vue (adresse tenue à jour et relue), les annonces, la page imprimée, le
     pied en deux colonnes, le bouton « haut de page » qui ne couvre rien, le
     sommaire qui suit la section à 35 % de l'écran, et la couche tactile. */
  section('Débrief 27 : accessibilité globale, aide, partage, impression (lot G)');
  {
    const cG = await contexte();
    const g = await page(cG, 'lot G');
    // --- Structure : une région principale, des sections nommées, le pied hors de main.
    const struct = await g.evaluate(() => {
      const main = document.querySelectorAll('main');
      const secs = [...document.querySelectorAll('section.panneau:not(.panneau-hors-suite)')];
      const nom = s => { const id = s.getAttribute('aria-labelledby'); const e = id && document.getElementById(id); return (e ? e.textContent : s.getAttribute('aria-label') || '').trim(); };
      return { mains: main.length, id: main[0] && main[0].id, toutesDedans: secs.every(s => main[0].contains(s)),
               nommees: secs.filter(s => !s.hidden).map(s => s.id + ':' + nom(s)), sansNom: secs.filter(s => !s.hidden && !nom(s)).map(s => s.id),
               pied: !!document.querySelector('footer.pied') && !document.querySelector('main footer, section footer'),
               premier: (() => { const f = [...document.querySelectorAll('a[href], button, input, select, [tabindex]:not([tabindex="-1"])')][0]; return f && f.textContent.trim(); })() };
    });
    verifier('une seule région principale (main#contenu) autour de toutes les sections, chacune nommée par son titre, le pied hors de main',
      struct.mains === 1 && struct.id === 'contenu' && struct.toutesDedans && !struct.sansNom.length && struct.pied, JSON.stringify(struct));
    // --- Liens d'évitement : le premier Tab montre « Aller au contenu », Entrée y mène.
    await g.evaluate(() => { window.scrollTo(0, 0); document.activeElement && document.activeElement.blur(); });
    await g.keyboard.press('Tab'); await g.waitForTimeout(150);
    const evit = await g.evaluate(() => { const a = document.activeElement, r = a.getBoundingClientRect();
      return { texte: a.textContent.trim(), visible: r.width > 60 && r.height > 20 && r.top >= 0 && r.left >= 0, contraste: getComputedStyle(a).color }; });
    await g.keyboard.press('Enter'); await g.waitForTimeout(900);
    const apresEvit = await g.evaluate(() => ({ focus: document.activeElement.id, descendu: window.scrollY > 0 }));
    verifier('le premier Tab montre « Aller au contenu », lisible en haut à gauche ; Entrée pose le focus sur la région principale',
      evit.texte === 'Aller au contenu' && evit.visible && apresEvit.focus === 'contenu' && apresEvit.descendu, JSON.stringify([evit, apresEvit]));
    await g.evaluate(() => document.querySelector('.evitement[data-evitement="section-plans"]').click()); await g.waitForTimeout(900);
    verifier('« Aller au tableau des plans » mène au panneau des plans, le focus sur son titre',
      await g.evaluate(() => document.activeElement === document.querySelector('#section-plans h2')));
    await g.evaluate(() => { const s = window.__jeuDExemple('HDK'); delete s.rapprochement; window.__chargerSource(s); }); await g.waitForTimeout(700);
    verifier('sans comparaison, « Aller à la comparaison » s’efface ; elle revenue, le lien revient',
      await g.evaluate(() => document.querySelector('.evitement[data-evitement="rapprochement"]').hidden) &&
      await g.evaluate(async () => { window.__chargerSource(window.__jeuDExemple('HDK')); await new Promise(r => setTimeout(r, 300)); return !document.querySelector('.evitement[data-evitement="rapprochement"]').hidden; }));
    await g.evaluate(() => window.scrollTo(0, 0)); await g.waitForTimeout(200);

    // --- L'aide : ouverte depuis le pied, fenêtre modale, le focus sur son titre, Échap la ferme et rend le focus.
    await g.click('#ouvrir-aide-pied'); await g.waitForTimeout(400);
    const aide = await g.evaluate(() => {
      const d = document.getElementById('aide'), t = d.textContent;
      return { ouverte: d.open, modale: d.matches(':modal'), focus: document.activeElement.id,
               parties: d.querySelectorAll('.aide-liste:not(.aide-touches):not(.aide-glossaire) > div').length,
               sigles: ['S43', 'ATA', 'PSN', 'FWD', 'GATES', 'SEE', 'Relevé'].every(s => [...d.querySelectorAll('.aide-glossaire dt')].some(x => x.textContent.indexOf(s) === 0)),
               telsQuels: /ceux de GATES, tels quels/.test(t), filtres: /Toute la page/.test(t) && /Une seule partie/.test(t),
               clavier: !!d.querySelector('#raccourcis-clavier') && /Échap/.test(t), lien: !!d.querySelector('[data-copier-lien]'),
               source: /Chaque vendredi/.test(t), qui: !!document.getElementById('aide-responsable').textContent };
    });
    verifier('l’aide s’ouvre du pied : fenêtre modale, focus sur son titre, les six parties, les filtres, le clavier, les sigles, la source des chiffres, le lien, à qui demander — les états de GATES « tels quels »',
      aide.ouverte && aide.modale && aide.focus === 'aide-titre' && aide.parties === 6 && aide.sigles && aide.telsQuels && aide.filtres && aide.clavier && aide.lien && aide.source && aide.qui,
      JSON.stringify(aide));
    await g.keyboard.press('Escape'); await g.waitForTimeout(300);
    verifier('Échap ferme l’aide et rend le focus au bouton qui l’avait ouverte',
      await g.evaluate(() => !document.getElementById('aide').open && document.activeElement.id === 'ouvrir-aide-pied'));
    /* Le bouton « Aide » de la page (#ouvrir-aide) ouvre la même fenêtre.
       Débrief 28 : c'est l'icône ronde au bout du sommaire (plus un bouton
       posé dans le bandeau) — on clique la vraie, sans en fabriquer. */
    const iconeAide = await g.evaluate(() => { const b = document.getElementById('ouvrir-aide'); return { un: document.querySelectorAll('#ouvrir-aide').length, dansSommaire: !!b && !!b.closest('nav.sommaire #outils-page') }; });
    await g.click('#ouvrir-aide');
    await g.waitForFunction(() => document.getElementById('aide').open, null, { timeout: 3000 }).catch(() => {});
    const parBandeau = await g.evaluate(() => document.getElementById('aide').open);
    await g.click('#aide-fermer');
    await g.waitForFunction(() => !document.getElementById('aide').open, null, { timeout: 3000 }).catch(() => {});
    verifier('#ouvrir-aide (l’icône du sommaire, débrief 28) ouvre la même aide ; la croix la ferme et rend le focus',
      iconeAide.un === 1 && iconeAide.dansSommaire && parBandeau && await g.evaluate(() => !document.getElementById('aide').open && document.activeElement.id === 'ouvrir-aide'), JSON.stringify(iconeAide));

    // --- Le raccourci « / » se coupe dans l'aide (WCAG 2.1.4), et le choix est gardé.
    await g.evaluate(() => { document.activeElement.blur(); window.scrollTo(0, 0); });
    await g.keyboard.press('/'); await g.waitForTimeout(200);
    const avecRaccourci = await g.evaluate(() => document.activeElement.id);
    await g.click('#ouvrir-aide-pied'); await g.waitForTimeout(300);
    await g.click('#raccourcis-clavier'); await g.waitForTimeout(200);
    await g.keyboard.press('Escape'); await g.waitForTimeout(200);
    await g.evaluate(() => document.activeElement.blur());
    await g.keyboard.press('/'); await g.waitForTimeout(200);
    const sansRaccourci = await g.evaluate(() => ({ focus: document.activeElement.id || document.activeElement.tagName, garde: localStorage.getItem('suivi-fwd:raccourcis') }));
    /* Débrief 29 (S9) : « / » ouvre la loupe du sommaire. */
    verifier('« / » mène à la recherche des plans (la loupe du sommaire, débrief 29) ; coupé dans l’aide, il ne fait plus rien, et le choix est gardé sur ce poste',
      avecRaccourci === 'cherche-plan-champ' && sansRaccourci.focus !== 'cherche-plan-champ' && sansRaccourci.garde === 'non', JSON.stringify([avecRaccourci, sansRaccourci]));
    await g.evaluate(() => localStorage.removeItem('suivi-fwd:raccourcis'));

    // --- Échap ferme le panneau du dessus : la vue d'ensemble, l'aide « ? », la bulle ; pas un champ rempli.
    await g.click('#voir-ensemble'); await g.waitForTimeout(500);
    await g.keyboard.press('Escape'); await g.waitForTimeout(300);
    const ens = await g.evaluate(() => ({ ferme: document.getElementById('ensemble').hidden, focus: document.activeElement.id }));
    verifier('Échap ferme la vue d’ensemble, et le focus revient sur « Vue d’ensemble »', ens.ferme && ens.focus === 'voir-ensemble', JSON.stringify(ens));
    await g.focus('button[data-aide]'); await g.keyboard.press('Enter'); await g.waitForTimeout(400);
    const aideOuverte = await g.evaluate(() => !!document.getElementById('panneau-fin'));
    await g.fill('#filtre-groupe', 'zz'); await g.waitForTimeout(300);
    await g.focus('#filtre-groupe'); await g.keyboard.press('Escape'); await g.waitForTimeout(300);
    const apresChamp = await g.evaluate(() => ({ champ: document.getElementById('filtre-groupe').value, aide: !!document.getElementById('panneau-fin') }));
    await g.focus('button[data-aide]'); await g.keyboard.press('Escape'); await g.waitForTimeout(400);
    const apresEchap = await g.evaluate(() => ({ aide: !!document.getElementById('panneau-fin'), focus: document.activeElement && document.activeElement.hasAttribute('data-aide') }));
    verifier('Échap dans un champ rempli le vide sans rien fermer ; ensuite, il ferme l’aide « ? » ouverte et garde le focus sur son bouton',
      aideOuverte && apresChamp.champ === '' && apresChamp.aide && !apresEchap.aide && apresEchap.focus, JSON.stringify([aideOuverte, apresChamp, apresEchap]));
    await g.evaluate(() => { document.getElementById('bulle').dataset.visible = 'true'; });
    await g.keyboard.press('Escape'); await g.waitForTimeout(200);
    verifier('Échap cache une bulle restée affichée (WCAG 1.4.13)', await g.evaluate(() => document.getElementById('bulle').dataset.visible === 'false'));

    // --- Annonces : le périmètre, un filtre posé, un filtre retiré.
    await g.evaluate(() => window.scrollTo(0, 0));
    /* Débrief 29 (batterie) : l'échec connu d'ici (« les changements de la
       page sont dits ») venait d'un délai fixe de 700 ms — la page annonce
       400 ms après le geste, puis 60 ms (la zone vidée, puis écrite), soit
       660 à 730 ms après le clic : on lisait parfois encore l'annonce
       d'avant. On compte les messages écrits dans la zone et on attend le
       suivant (5 s au plus), puis 500 ms de calme pour garder le dernier. */
    await g.evaluate(() => {
      if (window.__annonces) return;
      window.__annonces = [];
      const z = document.getElementById('annonce');
      new MutationObserver(() => { if (z.textContent) window.__annonces.push(z.textContent); }).observe(z, { childList: true, characterData: true, subtree: true });
    });
    const nbAnnonces = () => g.evaluate(() => window.__annonces.length);
    const lireAnnonce = async n0 => {
      await g.waitForFunction(n => window.__annonces.length > n, n0, { timeout: 5000 }).catch(() => {});
      await g.waitForTimeout(500);
      return g.evaluate(() => window.__annonces.length ? window.__annonces[window.__annonces.length - 1] : document.getElementById('annonce').textContent);
    };
    let n0 = await nbAnnonces();
    await g.click('#choix-perimetre button[data-perimetre="PERSO"]');
    const aPer = await lireAnnonce(n0);
    n0 = await nbAnnonces();
    await g.click('.etat-btn >> nth=1');
    const aEtat = await lireAnnonce(n0);
    n0 = await nbAnnonces();
    await g.click('#tout-effacer');
    const aRetire = await lireAnnonce(n0);
    /* Débrief 27, intégration : la tuile dit elle-même son état (lot A, « 60
       plans en En cours · 26 % du périmètre PERSO »), et « Tout effacer »
       le sien (lot H, « Filtres effacés : … ») — la phrase générale ne les
       recouvre plus. Débrief 29 : on attend leur phrase d'aujourd'hui, telle
       quelle (plus les tournures d'avant, « État … : N plans » ou « Filtre
       retiré »). */
    verifier('les changements de la page sont dits : « Périmètre PERSO : N sur M plans validés. », la tuile choisie (« N plans en … · P % du périmètre PERSO »), puis « Filtres effacés : … »',
      /^Périmètre PERSO : \d[\d\u00a0\u202f ]* sur \d[\d\u00a0\u202f ]* plans? validés?\.$/.test(aPer) &&
      /^\d[\d\u00a0\u202f ]* plans? en \S.* · \d+(,\d+)? % du périmètre PERSO$/.test(aEtat) &&
      /^Filtres effacés : \d[\d\u00a0\u202f ]* sur \d[\d\u00a0\u202f ]* plans? validés?\.$/.test(aRetire),
      JSON.stringify([aPer, aEtat, aRetire]));

    // --- Le lien de la vue : l'adresse suit (contrat, avancement, périmètre, recherche, section).
    await g.click('#choix-perimetre button[data-perimetre="PERSO"]'); await g.waitForTimeout(400);
    await g.fill('#recherche', 'GAE'); await g.waitForTimeout(400);
    await g.evaluate(() => window.scrollTo(0, 0)); await g.waitForTimeout(900);
    const adr = await g.evaluate(() => ({ hash: decodeURIComponent(location.hash), lien: window.__lienDeLaVue() }));
    verifier('l’adresse suit la vue — contrat, périmètre, recherche — et « Copier le lien » la reprend',
      /contrat=HDK/.test(adr.hash) && /perimetre=PERSO/.test(adr.hash) && /recherche=GAE/.test(adr.hash) && decodeURIComponent(adr.lien).indexOf(adr.hash) !== -1, JSON.stringify(adr));
    await g.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight)); await g.waitForTimeout(300);
    await g.click('.pied [data-copier-lien]'); await g.waitForTimeout(500);
    const copie = await g.evaluate(() => { const b = document.querySelector('.pied [data-copier-lien]'), z = document.querySelector('.pied .lien-a-copier');
      return { dit: b.textContent, champ: z ? z.value : '', annonce: document.getElementById('annonce').textContent }; });
    verifier('« Copier le lien de cette vue » copie (le bouton dit « Lien copié ») ou, refusé, montre le lien prêt à copier',
      (copie.dit === 'Lien copié' && /copié/.test(copie.annonce)) || /perimetre=PERSO/.test(decodeURIComponent(copie.champ)), JSON.stringify(copie));
    await cG.close();
    /* Le lien rouvre la vue : un autre contrat, le concept harnais, son périmètre, sa recherche et sa section. */
    const cL = await contexte();
    const gl = await cL.newPage(); brancher(gl, 'lot G lien');
    await gl.goto(URL + '#contrat=THS&avancement=concept&perimetre=perso&recherche=GAE&section=plans'); await gl.waitForTimeout(2200);
    const rouverte = await gl.evaluate(() => {
      const sec = document.getElementById('section-plans').getBoundingClientRect(), nav = document.getElementById('sommaire').getBoundingClientRect();
      return { contrat: document.getElementById('select-contrat').value, titre: document.getElementById('titre-page').textContent,
               perimetre: (document.querySelector('#choix-perimetre button[aria-pressed="true"]') || {}).dataset, recherche: document.getElementById('recherche').value,
               plans: Math.round(sec.top - nav.bottom), fond: window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2 };
    });
    verifier('un lien partagé rouvre la page sur son contrat (THS), le concept harnais, PERSO, sa recherche, et descend à « Plans » (au plus bas si la page est courte)',
      rouverte.contrat === 'THS' && rouverte.titre === 'Suivi concept harnais' && rouverte.perimetre && rouverte.perimetre.perimetre === 'PERSO' &&
      rouverte.recherche === 'GAE' && rouverte.plans >= -2 && (rouverte.plans <= 40 || rouverte.fond), JSON.stringify(rouverte));
    await gl.goto('about:blank');
    await gl.goto(URL + '#contrat=INCONNU&perimetre=nulle-part'); await gl.waitForTimeout(1500);
    verifier('un lien vers un contrat ou un périmètre inconnus ouvre la page normale, sans erreur',
      await gl.evaluate(() => document.getElementById('select-contrat').value === 'HDK' &&
        document.querySelector('#choix-perimetre button[data-perimetre=""]').getAttribute('aria-pressed') === 'true'));
    await cL.close();

    // --- L'impression : vue essentielle, toutes les lignes, sans commandes, en-tête, couleurs claires même en sombre.
    const cI = await contexte({ colorScheme: 'dark' });
    const gi = await page(cI, 'lot G impression');
    const avantImp = await gi.evaluate(() => document.querySelectorAll('tr.titres th').length);
    await gi.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
    await gi.emulateMedia({ media: 'print', colorScheme: 'dark' });
    const imp = await gi.evaluate(() => {
      const cache = s => [...document.querySelectorAll(s)].every(e => getComputedStyle(e).display === 'none');
      const t = document.getElementById('entete-impression');
      const lum = c => { const m = c.match(/\d+/g).slice(0, 3).map(Number); return (m[0] + m[1] + m[2]) / 3; };
      return { colonnes: document.querySelectorAll('tr.titres th').length, lignes: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length,
               suite: document.querySelectorAll('#corps-tableau tr.ligne-suite').length,
               caches: cache('.sommaire') && cache('.reglages') && cache('.recherche') && cache('.segmente') && cache('.haut-de-page') && cache('.pied-actions') && cache('thead .filtres'),
               entete: getComputedStyle(t).display !== 'none' && /HDK/.test(t.textContent) && /Définition électrique/.test(t.textContent),
               encre: lum(getComputedStyle(document.body).color), fond: lum(getComputedStyle(document.querySelector('.panneau')).backgroundColor),
               titres: [...document.querySelectorAll('tr.titres th')].every(th => th.getAttribute('data-imprime')) };
    });
    await gi.emulateMedia({ media: 'screen', colorScheme: 'dark' });
    await gi.evaluate(() => window.dispatchEvent(new Event('afterprint')));
    const apresImp = await gi.evaluate(() => document.querySelectorAll('tr.titres th').length);
    verifier('imprimée : le tableau en vue essentielle, toutes ses lignes, sans commandes, l’en-tête du contrat, encre sombre sur fond clair même en thème sombre ; puis tout revient',
      imp.colonnes < avantImp && imp.colonnes > 0 && imp.lignes === TOTAL && imp.suite === 0 && imp.caches && imp.entete && imp.encre < 80 && imp.fond > 200 && imp.titres && apresImp === avantImp,
      JSON.stringify([imp, avantImp, apresImp]));
    await cI.close();

    // --- Le pied en deux colonnes, les infos techniques repliées ; une colonne au téléphone.
    const piedDe = async (pg) => pg.evaluate(() => {
      const gch = document.querySelector('.pied-gauche').getBoundingClientRect(), drt = document.querySelector('.pied-droite').getBoundingClientRect();
      const d = document.getElementById('pied-technique');
      return { cote: drt.left > gch.right && Math.abs(drt.top - gch.top) < 4, dessous: drt.top >= gch.bottom - 1,
               replie: !d.open && d.contains(document.getElementById('livraison')) && d.contains(document.getElementById('mesure-ouverture')),
               aide: !!document.querySelector('.pied [data-ouvrir-aide]'), lien: !!document.querySelector('.pied [data-copier-lien]') };
    });
    const cP = await contexte({ viewport: { width: 1440, height: 900 } });
    const gp = await page(cP, 'lot G pied');
    const pied1440 = await piedDe(gp);
    // Le bouton « haut de page » dans la marge, à 1440 px.
    await gp.evaluate(() => window.scrollTo(0, 2500)); await gp.waitForTimeout(300);
    const marge = await gp.evaluate(() => { const b = document.getElementById('haut-de-page').getBoundingClientRect(), p = document.querySelector('#section-synthese').getBoundingClientRect();
      return { visible: !document.getElementById('haut-de-page').hidden, ecart: Math.round(b.left - p.right) }; });
    await cP.close();
    const cT = await contexte({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const gt = await page(cT, 'lot G téléphone');
    const pied390 = await piedDe(gt);
    verifier('le pied : deux colonnes à 1440 px (les chiffres, puis l’aide et le lien), une seule au téléphone ; temps et livraison dans « Infos techniques », replié',
      pied1440.cote && pied1440.replie && pied1440.aide && pied1440.lien && pied390.dessous && pied390.replie, JSON.stringify([pied1440, pied390]));
    verifier('à 1440 px, le bouton « haut de page » est dans la marge, à côté des panneaux, sans les toucher',
      marge.visible && marge.ecart >= 8, JSON.stringify(marge));
    // Au téléphone : il ne paraît qu'en remontant, jamais pendant une saisie ; 36 px (la règle étroite gagne enfin).
    await gt.evaluate(() => window.scrollTo(0, 3000)); await gt.waitForTimeout(300);
    const descente = await gt.evaluate(() => !document.getElementById('haut-de-page').hidden);
    await gt.evaluate(() => window.scrollBy(0, -200)); await gt.waitForTimeout(300);
    const remontee = await gt.evaluate(() => { const b = document.getElementById('haut-de-page'); return { vu: !b.hidden, taille: Math.round(b.getBoundingClientRect().width) }; });
    await gt.evaluate(() => { const i = document.getElementById('filtre-groupe'); i.focus({ preventScroll: true }); window.scrollBy(0, -100); }); await gt.waitForTimeout(300);
    const saisie = await gt.evaluate(() => !document.getElementById('haut-de-page').hidden);
    verifier('au téléphone, le bouton « haut de page » ne paraît qu’en remontant (36 px), et se retire pendant une saisie',
      !descente && remontee.vu && remontee.taille === 36 && !saisie, JSON.stringify([descente, remontee, saisie]));
    // La couche tactile : liens doux, champs à 16 px.
    const tactile = await gt.evaluate(() => {
      const l = document.querySelector('.pied [data-copier-lien]'), a = getComputedStyle(l, '::after'), h = l.getBoundingClientRect().height - 2 * parseFloat(a.top);
      const champ = document.querySelector('table.plans thead .filtres input');
      return { zone: Math.round(h), police: champ ? parseFloat(getComputedStyle(champ).fontSize) : 16, contact: parseFloat(getComputedStyle(document.getElementById('recherche')).fontSize) };
    });
    verifier('au doigt : un lien doux offre 44 px à toucher, tous les champs écrivent en 16 px (iOS ne zoome plus)',
      tactile.zone >= 44 && tactile.police >= 16 && tactile.contact >= 16, JSON.stringify(tactile));
    await cT.close();

    // --- Le sommaire marque la section qui traverse 35 % de l'écran.
    const cS = await contexte({ viewport: { width: 1280, height: 800 } });
    const gs = await page(cS, 'lot G sommaire');
    await gs.evaluate(() => { const s = document.getElementById('section-repartition'); window.scrollTo(0, s.getBoundingClientRect().top + window.scrollY - window.innerHeight * 0.3); });
    await gs.waitForTimeout(400);
    const espion = await gs.evaluate(() => ({ courant: (document.querySelector('#sommaire-liste a[aria-current]') || {}).dataset,
      haut: Math.round(document.getElementById('section-repartition').getBoundingClientRect().top) }));
    verifier('le sommaire marque la section qui traverse 35 % de l’écran (« Par ATA » dès que son haut passe cette ligne), plus d’un panneau de retard',
      espion.courant && espion.courant.chapitre === 'section-repartition', JSON.stringify(espion));
    await cS.close();
  }

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
  /* Le menu déroulant d'un Chrome en mode sombre : la page déclare son
     schéma, et chaque option porte le fond et l'encre de la page — plus de
     texte clair sur une liste blanche. */
  const menus = await ps.evaluate(() => {
    function lum(c) {
      const m = c.match(/\d+/g).slice(0, 3).map(Number).map(v => {
        v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
    }
    function contraste(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
    const o = document.querySelector('#dim-critique option');
    const st = o ? getComputedStyle(o) : null;
    return { schema: getComputedStyle(document.documentElement).colorScheme,
             contraste: st ? contraste(st.color, st.backgroundColor) : 0, fond: st ? lum(st.backgroundColor) : 1 };
  });
  verifier('en sombre, les menus déroulants suivent : schéma déclaré, options sombres et lisibles (≥ 7:1)',
    /dark/.test(menus.schema) && menus.fond < 0.1 && menus.contraste >= 7, JSON.stringify(menus));
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

  // =================================================================
  /* Débrief 27, lot 0 — les fondations visuelles : un seul contrôle
     segmenté, une seule tête de panneau, le surtitre qui dit le nom du
     sommaire, l'échelle typographique, l'anneau du focus en ardoise, les
     champs à 3:1, la hachure calme, le bord du contenu, les deux aides
     communes (garderFocus, annoncer) et le thème sombre aux feuilles
     chaudes. */
  section('Débrief 27 : fondations visuelles (lot 0)');
  {
    const outilsCouleur = () => {
      window.__lum = c => {
        const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
        return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
      };
      window.__contraste = (a, b) => { const x = window.__lum(a), y = window.__lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    };
    for (const schema of ['light', 'dark']) {
      const c27 = await contexte({ colorScheme: schema });
      const q = await page(c27, 'lot 0 ' + schema);
      await q.evaluate(outilsCouleur);
      const r = await q.evaluate(() => {
        const cs = e => getComputedStyle(e);
        const vus = [...document.querySelectorAll('.segmente')].filter(s => s.getClientRects().length && !s.closest('dialog'));
        const surface = cs(document.getElementById('section-plans')).backgroundColor;
        const segs = vus.map(s => {
          const presse = s.querySelector('button[aria-pressed="true"]');
          const autre = s.querySelector('button[aria-pressed="false"]:not([hidden])');
          return {
            id: s.id || s.getAttribute('aria-label'), piste: cs(s).backgroundColor, rayon: cs(s).borderTopLeftRadius,
            /* Débrief 28 : dans le bandeau marine de l'en-tête, la pastille
               choisie prend la puce du bandeau (son jeton --seg-puce, lu ici). */
            bandeau: !!s.closest('header.entete'),
            puceBandeau: (v => v ? 'rgb(' + v.replace(/^#/, '').match(/../g).map(x => parseInt(x, 16)).join(', ') + ')' : '')(cs(s).getPropertyValue('--seg-puce').trim()),
            haut: Math.round(s.getBoundingClientRect().height),
            bordsBoutons: [...s.querySelectorAll('button')].every(b => parseFloat(cs(b).borderLeftWidth) === 0 && parseFloat(cs(b).borderRightWidth) === 0),
            presseFond: presse ? cs(presse).backgroundColor : null, presseGras: presse ? cs(presse).fontWeight : null,
            presseEncre: presse ? window.__contraste(cs(presse).color, cs(presse).backgroundColor) : 0,
            autreEncre: autre ? window.__contraste(cs(autre).color, cs(s).backgroundColor) : 99,
            ombre: presse ? cs(presse).boxShadow !== 'none' : false
          };
        });
        const ids = ['section-synthese', 'section-tendance', 'section-journal', 'section-repartition', 'section-plans', 'rapprochement'];
        const secs = ids.map(id => document.getElementById(id)).filter(s => s && s.getClientRects().length);
        const tetes = secs.map(s => cs(s.querySelector('.panneau-tete')).backgroundColor);
        const liseres = secs.map(s => ({ l: parseFloat(cs(s).borderTopWidth), c: cs(s).borderTopColor, n: getComputedStyle(s.querySelector('.surtitre'), '::before').color }));
        const n = document.querySelector('#etats .etat-n');
        const pastille = document.querySelector('#etats .pastille[style*="background"]');
        const champ = document.getElementById('recherche');
        const tuileLib = [...document.querySelectorAll('#etats .libelle')];
        return {
          segs, tetes, liseres,
          chiffre: { police: cs(n).fontFamily.split(',')[0].replace(/"/g, ''), taille: parseFloat(cs(n).fontSize), poids: cs(n).fontWeight,
                     encre: window.__contraste(cs(n).color, cs(n.closest('.etat-btn')).backgroundColor === 'rgba(0, 0, 0, 0)' ? surface : cs(n.closest('.etat-btn')).backgroundColor) },
          lisere: pastille ? cs(pastille).boxShadow : '',
          champ: { haut: Math.round(champ.getBoundingClientRect().height), bord: window.__contraste(cs(champ).borderTopColor, surface) },
          champGroupe: Math.round(document.getElementById('filtre-groupe').getBoundingClientRect().height),
          tronque: tuileLib.filter(l => cs(l).textOverflow === 'ellipsis' || l.scrollWidth > l.clientWidth + 1).map(l => l.textContent),
          surface, papier: cs(document.body).backgroundColor,
          tiret: !!document.querySelector('style') && [...document.styleSheets].some(f => { try { return [...f.cssRules].some(x => x.selectorText === '.tiret-vide'); } catch (e) { return false; } })
        };
      });
      /* Débrief 28 : les contrôles de l'en-tête sont sur le bandeau marine,
         dont les jetons sont redéfinis pour que « ses contrôles gardent leurs
         contrastes » : la même règle (choix ≥ 7:1) s'y vérifie à part, pour
         qu'un écart du bandeau se lise comme tel. */
      verifier(schema + ' : chaque contrôle segmenté de la page est une piste de 28 px, rayon 7, sans filet entre les boutons ; le choix est une pastille levée en graisse 500, lisible (≥ 7:1 hors du bandeau), les autres choix ≥ 4,5:1',
        r.segs.length >= 3 && r.segs.every(s => Math.abs(s.haut - 28) <= 1 && s.rayon === '7px' && s.bordsBoutons && s.presseGras === '500' && s.ombre && (s.bandeau || s.presseEncre >= 7) && s.autreEncre >= 4.5),
        JSON.stringify(r.segs));
      verifier(schema + ' : dans le bandeau marine de l’en-tête (débrief 28), le choix d’un contrôle segmenté reste lisible (≥ 7:1), comme ailleurs',
        r.segs.some(s => s.bandeau) && r.segs.filter(s => s.bandeau).every(s => s.presseEncre >= 7),
        JSON.stringify(r.segs.filter(s => s.bandeau).map(s => [s.id, s.presseFond, +s.presseEncre.toFixed(2)])));
      /* Débrief 28 : les contrôles de l'en-tête sont posés sur le bandeau
         marine — leur pastille choisie est la puce du bandeau (jeton
         --seg-puce), lisible (≥ 7:1, plus haut) ; ailleurs, toujours claire
         en clair (blanche), sombre en sombre. */
      verifier(schema + ' : plus de pavé noir — la pastille choisie est claire en clair (blanche), sombre en sombre ; dans le bandeau marine de l’en-tête, la puce du bandeau (débrief 28)',
        r.segs.some(s => s.bandeau) && r.segs.some(s => !s.bandeau) &&
        r.segs.every(s => s.bandeau ? (!!s.puceBandeau && s.presseFond === s.puceBandeau) : s.presseFond === (schema === 'light' ? 'rgb(255, 255, 255)' : 'rgb(44, 44, 51)')),
        JSON.stringify(r.segs.map(s => [s.id, s.bandeau, s.presseFond, s.puceBandeau])));
      verifier(schema + ' : une seule tête neutre pour tous les panneaux ; la teinte ne reste qu\'au liseré de 2 px, de la couleur du numéro',
        r.tetes.length >= 5 && r.tetes.every(t => t === r.tetes[0]) && r.tetes[0] === (schema === 'light' ? 'rgb(248, 247, 243)' : 'rgb(27, 27, 31)') &&
        r.liseres.every(l => l.l === 2 && l.c === l.n), JSON.stringify({ tetes: r.tetes, liseres: r.liseres }));
      verifier(schema + ' : le chiffre d\'une tuile est le texte le plus net de sa carte — Plex Sans 24/500, à l\'encre (≥ 12:1)',
        r.chiffre.police === 'IBM Plex Sans' && r.chiffre.taille === 24 && r.chiffre.poids === '500' && r.chiffre.encre >= 12, JSON.stringify(r.chiffre));
      verifier(schema + ' : la recherche du tableau fait 36 px, celle d\'un bloc 28 px ; leur bord tient 3:1 sur la surface',
        r.champ.haut === 36 && r.champGroupe === 28 && r.champ.bord >= 3, JSON.stringify({ champ: r.champ, groupe: r.champGroupe }));
      verifier(schema + ' : aucun nom de tuile n\'est coupé de points de suspension', r.tronque.length === 0, JSON.stringify(r.tronque));
      if (schema === 'light') {
        verifier('clair : les pastilles de couleur portent un liseré intérieur (TO_CONFIRM, vert clair à 3:1 sur le blanc)', /inset/.test(r.lisere), r.lisere);
        verifier('la classe commune du tiret de case vide (.tiret-vide) existe', r.tiret);
      } else {
        verifier('sombre : les feuilles sont chaudes comme le papier (surface #171716)', r.surface === 'rgb(23, 23, 22)', r.surface);
        /* Débrief 28 : les couleurs des états « Terre » — TO_TREAT n'est plus
           #9d9990 ; la valeur est lue au jeton (--v-afaire-2) et mesurée
           contre les autres marques de la barre, plus écrite en dur. */
        const sombre27 = await q.evaluate(() => {
          const rac = getComputedStyle(document.documentElement), jeton = n => rac.getPropertyValue(n).trim();
          const rgb = h => h.replace(/^#(..)(..)(..)$/, (m, a, b, c) => 'rgb(' + [a, b, c].map(x => parseInt(x, 16)).join(',') + ')');
          const marques = ['--fait', '--v-fait-2', '--v-cours-1', '--v-cours-2', '--v-cours-3', '--v-cours-4', '--v-cours-5', '--v-cours-6', '--v-afaire-1'].map(n => ({ n, l: window.__lum(rgb(jeton(n))) }));
          const afaire = jeton('--v-afaire-2');
          return { afaire, plusClaire: marques.every(m => window.__lum(rgb(afaire)) >= m.l),
                   encreAfaire: window.__contraste(rgb(jeton('--v-afaire-2-encre')), rgb(afaire)),
                   encre3: window.__contraste(rgb(jeton('--encre-3')), getComputedStyle(document.getElementById('section-plans')).backgroundColor) };
        });
        verifier('sombre : TO_TREAT (--v-afaire-2, « Terre » au débrief 28) n\'est pas la marque la plus claire de la barre, son encre s\'y lit (4,5:1), et le gris tertiaire tient 4,5:1 sur la surface',
          /^#[0-9a-f]{6}$/i.test(sombre27.afaire) && !sombre27.plusClaire && sombre27.encreAfaire >= 4.5 && sombre27.encre3 >= 4.5, JSON.stringify(sombre27));
      }
      /* L'anneau du focus clavier : l'ardoise, sur un bouton comme sur un champ. */
      await q.evaluate(() => { window.scrollTo(0, 0); document.getElementById('titre-page').setAttribute('tabindex', '-1'); document.getElementById('titre-page').focus(); });
      await q.keyboard.press('Tab'); await q.waitForTimeout(80);
      const anneau = await q.evaluate(() => { const a = document.activeElement, s = getComputedStyle(a); return { quoi: a.tagName + '.' + a.className, style: s.outlineStyle, l: s.outlineWidth, c: s.outlineColor }; });
      await q.focus('#recherche'); await q.waitForTimeout(80);
      const anneauChamp = await q.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, l: s.outlineWidth, c: s.outlineColor }; });
      const ardoise = schema === 'light' ? 'rgb(52, 80, 122)' : 'rgb(169, 190, 219)';
      verifier(schema + ' : l\'anneau du focus est en ardoise (plus le vert de VALIDATED), 2 px, sur un bouton comme sur un champ',
        anneau.style === 'solid' && anneau.l === '2px' && anneau.c === ardoise && anneauChamp.style === 'solid' && anneauChamp.c === ardoise,
        JSON.stringify({ anneau, anneauChamp }));
      await c27.close();
    }

    const c0 = await contexte();
    const q = await page(c0, 'lot 0');
    await q.evaluate(outilsCouleur);
    /* Le surtitre de chaque panneau dit le nom de son entrée du sommaire —
       et le suit quand le regroupement change. */
    const surtitres = () => q.evaluate(() => [...document.querySelectorAll('#sommaire-liste a[data-chapitre]')]
      .filter(a => a.getClientRects().length)
      .map(a => { const s = document.getElementById(a.dataset.chapitre); return { nav: a.textContent.trim(), surtitre: s ? s.querySelector('.surtitre').textContent.trim() : null }; }));
    const avant = await surtitres();
    verifier('chaque surtitre dit le nom de son entrée du sommaire (« 04 Par ATA » mène à « 04 · Par ATA »)',
      avant.length >= 5 && avant.every(x => x.nav === x.surtitre), JSON.stringify(avant));
    const autreDim = await q.evaluate(() => { const s = document.getElementById('dim-critique'); const o = [...s.options].find(x => x.value !== s.value && !x.disabled); return o ? o.value : null; });
    if (autreDim) {
      await q.selectOption('#dim-critique', autreDim); await q.waitForTimeout(500);
      const apres = await surtitres();
      verifier('le regroupement changé, le surtitre du bloc suit le sommaire', apres.every(x => x.nav === x.surtitre), JSON.stringify(apres));
      await q.selectOption('#dim-critique', 'ata'); await q.waitForTimeout(400);
    }
    /* Les comptes des segments et des pastilles : en gris tertiaire plein,
       plus en opacité (3,7:1 avant). */
    const comptes = await q.evaluate(() => {
      const fond = e => { for (let x = e; x; x = x.parentElement) { const f = getComputedStyle(x).backgroundColor; if (f && !/rgba\(.*,\s*0\)$/.test(f) && f !== 'transparent') return f; } return 'rgb(255,255,255)'; };
      return [...document.querySelectorAll('#choix-perimetre .n, .filtre-journal .n')].filter(n => n.getClientRects().length)
        .map(n => ({ t: n.textContent, c: +window.__contraste(getComputedStyle(n).color, fond(n)).toFixed(2), o: getComputedStyle(n).opacity }));
    });
    verifier('les comptes du périmètre et des pastilles tiennent 4,5:1, sans opacité', comptes.length > 0 && comptes.every(x => x.c >= 4.5 && x.o === '1'), JSON.stringify(comptes.slice(0, 6)));
    /* La hachure « Non renseigné » : un trait fin sur le fond creusé, et sa
       part posée sur une pastille de la surface. */
    const hachure = await q.evaluate(() => {
      const h = document.querySelector('#barre .hachure'); if (!h) return null;
      const e = h.querySelector('.etiq-part'), s = getComputedStyle(h);
      return { fond: s.backgroundColor, motif: s.backgroundImage, etiquette: e ? getComputedStyle(e).backgroundColor : null, surface: getComputedStyle(document.getElementById('section-plans')).backgroundColor, vide: !h.textContent.trim() };
    });
    verifier('la hachure « Non renseigné » est fine (1 px tous les 6 px) sur le fond creusé, et sa part se lit sur une pastille de la surface',
      !hachure || (/1px/.test(hachure.motif) && /6px/.test(hachure.motif) && hachure.fond !== 'rgba(0, 0, 0, 0)' && (hachure.vide || hachure.etiquette === hachure.surface)), JSON.stringify(hachure));
    /* Le bord du contenu : le bandeau, le pied et la marque collée
       s'alignent sur le contenu des panneaux. */
    const bords = await q.evaluate(() => {
      const sec = document.getElementById('section-synthese').getBoundingClientRect();
      const pied = document.querySelector('footer.pied'), pp = parseFloat(getComputedStyle(pied).paddingLeft), rp = pied.getBoundingClientRect();
      /* Débrief 28 : les réglages se centrent sur un écran large (comme le
         titre) : on mesure leurs réglages visibles, pas la boîte. */
      const vus = [...document.querySelectorAll('#portee .reglage')].filter(e => e.getClientRects().length).map(e => e.getBoundingClientRect());
      const reg = { left: Math.min(...vus.map(b => b.left)), right: Math.max(...vus.map(b => b.right)) };
      const tete = document.querySelector('#section-synthese .panneau-tete .surtitre').getBoundingClientRect();
      return { contenuG: tete.left, contenuD: tete.right, pied: rp.left + pp, reglagesG: reg.left, reglagesD: reg.right, largeurPage: sec.width };
    });
    /* Débrief 28 : les réglages ne se calent plus sur le bord droit du
       contenu — ils sont au centre du contenu, comme le titre, et restent
       dedans ; le pied garde le bord gauche du contenu. */
    verifier('le pied s\'aligne sur le bord du contenu des panneaux ; les réglages du haut sont au centre du contenu, sans en sortir (débrief 28)',
      Math.abs(bords.pied - bords.contenuG) <= 1 && Math.abs((bords.reglagesG + bords.reglagesD) / 2 - (bords.contenuG + bords.contenuD) / 2) <= 2 &&
      bords.reglagesG >= bords.contenuG - 1 && bords.reglagesD <= bords.contenuD + 1, JSON.stringify(bords));
    /* garderFocus : un rendu qui remplace l'élément focalisé rend le focus
       au même élément ; s'il n'existe plus, au titre de la section — jamais
       au corps de la page. */
    const focus27 = await q.evaluate(() => {
      const zone = document.getElementById('etats');
      const b = zone.querySelector('.etat-btn[data-etat]'); const cle = b.dataset.etat;
      b.focus();
      window.__garderFocus(function () { zone.innerHTML = zone.innerHTML; }, 'etats');
      const a = document.activeElement;
      const meme = a !== b && a.classList.contains('etat-btn') && a.dataset.etat === cle;
      const jour = document.getElementById('section-journal');
      const tmp = document.createElement('div'); tmp.innerHTML = '<button type="button" class="essai-focus">essai</button>';
      jour.appendChild(tmp); tmp.firstChild.focus();
      const rendu = window.__garderFocus(function () { tmp.remove(); return 'rendu'; });
      const b2 = document.activeElement;
      return { meme, rendu, apres: b2 === document.body ? 'body' : b2.tagName + '.' + b2.className, dansSection: jour.contains(b2) };
    });
    verifier('garderFocus rend le focus au même élément redessiné, ou au titre de sa section — jamais au corps de la page',
      focus27.meme && focus27.rendu === 'rendu' && focus27.apres !== 'body' && focus27.dansSection, JSON.stringify(focus27));
    /* annoncer : une seule zone polie, les appels rapprochés regroupés. */
    await q.evaluate(() => { window.__annoncer('premier'); window.__annoncer('12 plans affichés sur 634'); });
    /* Débrief 29 (batterie) : attendre le message attendu lui-même, 10 s au
       plus. La page l'écrit 460 ms après l'appel, mais ses minuteries passent
       après le rendu en cours : juste après le regroupement changé (le
       tableau entier redessiné, toutes ses lignes d'un bloc ici), il arrive
       vers 3,5 s — les 4 s d'avant ne suffisaient plus sur une machine
       chargée. */
    await q.waitForFunction(() => (document.getElementById('annonce') || {}).textContent === '12 plans affichés sur 634', null, { timeout: 10000 }).catch(() => {});
    const annonce = await q.evaluate(() => {
      const z = document.getElementById('annonce');
      return { role: z && z.getAttribute('role'), live: z && z.getAttribute('aria-live'), texte: z && z.textContent, masque: z && z.getBoundingClientRect().width <= 1,
               copierParle: document.querySelectorAll('.copier[aria-live]').length, zones: document.querySelectorAll('#annonce').length };
    });
    verifier('annoncer dit le dernier message dans une seule zone polie et masquée ; « Copier (n) » ne parle plus de lui-même',
      annonce.role === 'status' && annonce.live === 'polite' && annonce.texte === '12 plans affichés sur 634' && annonce.masque && annonce.copierParle === 0 && annonce.zones === 1,
      JSON.stringify(annonce));
    await c0.close();
  }

  // =================================================================
  /* Débrief 27, lot H : l'en-tête, les réglages et leurs états — une seule
     barre de réglages (le périmètre y monte), le surtitre du contrat et la
     fraîcheur des chiffres, l'attente et l'erreur d'un changement de contrat
     (rien ne s'écrit à côté du menu, un geste fait pendant l'attente n'est
     pas perdu, « Réessayer »), la vue d'ensemble en fenêtre, le bandeau des
     filtres qui ne pousse rien, les entrées et commandes absentes qui disent
     pourquoi. */
  section('Débrief 27 : en-tête, réglages, états (lot H)');
  {
    const cH = await contexte();
    const h = await page(cH, 'lot H');
    const barreH = await h.evaluate(() => {
      const r = e => e.getBoundingClientRect();
      const ent = document.querySelector('header#entete');
      const vus = [...document.querySelectorAll('#portee .reglage')].filter(e => e.getClientRects().length);
      const centres = vus.map(e => Math.round(r(e).top + r(e).height / 2));
      const ens = document.getElementById('voir-ensemble'), aide = document.getElementById('ouvrir-aide'), adm = document.getElementById('choix-admin');
      /* Débrief 28 : Vue d'ensemble, Aide et Administration sont trois icônes
         rondes au bout du sommaire collé (après la loupe), leur nom au survol
         (title) et pour les lecteurs d'écran (texte .masque) — plus dans le
         bandeau du titre. Débrief 29 : un seul groupe au bout du sommaire, le
         ⚙ en tête, puis la loupe ; le nom en bulle (data-nom) au survol et au
         clavier, plus en title. */
      const outils = document.getElementById('outils-page'), som = document.querySelector('nav.sommaire');
      const icone = b => { const c = getComputedStyle(b), t = b.querySelector('.masque'), rb = r(b);
        return !!b.querySelector('svg') && !!t && t.getBoundingClientRect().width <= 1 && !!b.dataset.nom && !b.title && Math.abs(rb.width - rb.height) <= 1 && rb.width <= 40 && c.borderTopLeftRadius === '50%'; };
      return {
        banniere: !!ent && ent.contains(document.getElementById('reglages')) && ent.contains(document.getElementById('titre-page')) && !document.querySelector('header header'),
        ordre: vus.map(e => e.id || e.classList[e.classList.length - 1]).join(','), uneLigne: Math.max(...centres) - Math.min(...centres) <= 2,
        outilsAuSommaire: !!outils && !!som && outils.parentElement === som && som.lastElementChild === outils &&
          outils.firstElementChild === adm && (adm.nextElementSibling || {}).id === 'cherche-plan' && !ent.contains(outils) && !document.getElementById('reglages').contains(outils),
        ensemble: ens.tagName === 'BUTTON' && getComputedStyle(ens).textDecorationLine === 'none' && icone(ens) && ens.getAttribute('aria-haspopup') === 'dialog' && /Vue d’ensemble/.test(ens.textContent),
        aide: !!aide && aide.tagName === 'BUTTON' && icone(aide) && /Aide/.test(aide.textContent),
        iconeAdmin: icone(document.getElementById('ouvrir-admin')) && document.getElementById('ouvrir-admin').dataset.nom === 'Administration',
        admin: getComputedStyle(adm).visibility === 'hidden' && r(adm).width >= 30 && adm.dataset.droits === 'attente',
        etat: r(document.getElementById('etat-contrat')).width <= 1 && !document.getElementById('etat-contrat').hasAttribute('aria-live'),
        noms: [...document.querySelectorAll('#choix-perimetre button')].map(b => b.textContent.replace(/\s+/g, ' ').trim())
      };
    });
    verifier('B1 : une seule barre de réglages dans l’en-tête de la page (repère bannière, avec le titre) — Contrat, Avancement, Périmètre sur une ligne, dans cet ordre',
      barreH.banniere && barreH.ordre === 'reglage-contrat,choix-avancement,perimetre' && barreH.uneLigne, JSON.stringify(barreH));
    verifier('B1, débrief 28 : les outils au bout du sommaire, avec la loupe — « Vue d’ensemble », « Aide » et « Administration » en icônes rondes (nom en bulle, débrief 29, et masqué pour les lecteurs d’écran), la place d’« Administration » gardée invisible en tête du groupe tant que les droits ne sont pas lus',
      barreH.outilsAuSommaire && barreH.ensemble && barreH.aide && barreH.iconeAdmin && barreH.admin, JSON.stringify(barreH));
    verifier('X-A13 : les boutons du périmètre se nomment « Tout 634 plans » (plus « Tout634 ») ; rien ne s’écrit à côté du menu du contrat (son état est masqué, sans aria-live)',
      barreH.etat && barreH.noms.length === 3 && barreH.noms.every(n => /^\S.* \d[\d\s ]* plans?$/.test(n)), JSON.stringify(barreH.noms));
    /* Débrief 28 : le haut de page est un bandeau d'encre marine (jetons
       redéfinis pour le seul en-tête), le titre et les réglages en clair ;
       les réglages au centre, comme le titre, sur un écran large. Mesuré,
       en clair puis en sombre (le marine plus clair que la page noire). */
    for (const schema of ['light', 'dark']) {
      await h.emulateMedia({ colorScheme: schema }); await h.waitForTimeout(150);
      const bandeau = await h.evaluate(() => {
        const lum = c => { const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
        const rgb = h => h.replace(/^#(..)(..)(..)$/, (m, a, b, c) => 'rgb(' + [a, b, c].map(x => parseInt(x, 16)).join(', ') + ')');
        const cr = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
        const ent = document.querySelector('header.entete'), cs = getComputedStyle(ent);
        const fond = rgb(cs.getPropertyValue('--bandeau-fond').trim()), papier = getComputedStyle(document.body).backgroundColor;
        const t = document.getElementById('titre-page'), rg = document.createRange(); rg.selectNodeContents(t);
        const tb = rg.getBoundingClientRect(), centre = b => (b.left + b.right) / 2;
        const vus = [...document.querySelectorAll('#portee .reglage')].filter(e => e.getClientRects().length).map(e => e.getBoundingClientRect());
        const reg = { left: Math.min(...vus.map(b => b.left)), right: Math.max(...vus.map(b => b.right)) };
        const contenu = document.querySelector('#section-synthese .panneau-tete .surtitre').getBoundingClientRect();
        return { fond, papier, peint: cs.borderImageSource.indexOf(fond) !== -1, titre: +cr(getComputedStyle(t).color, fond).toFixed(2), reglage: +cr(cs.color, fond).toFixed(2),
                 lumFond: +lum(fond).toFixed(3), lumPapier: +lum(papier).toFixed(3),
                 centreTitre: Math.round(centre(tb)), centreReglages: Math.round(centre(reg)), centreContenu: Math.round(centre(contenu)) };
      });
      verifier('débrief 28, ' + schema + ' : l’en-tête est un bandeau marine peint d’un bord à l’autre, distinct du papier ; le titre et les réglages s’y lisent en clair (≥ 7:1) ; les réglages au centre, comme le titre',
        bandeau.peint && Math.abs(bandeau.lumFond - bandeau.lumPapier) > 0.03 && (schema === 'dark' || bandeau.lumFond < bandeau.lumPapier) && bandeau.titre >= 7 && bandeau.reglage >= 7 &&
        Math.abs(bandeau.centreReglages - bandeau.centreTitre) <= 2 && Math.abs(bandeau.centreTitre - bandeau.centreContenu) <= 2, JSON.stringify(bandeau));
    }
    await h.emulateMedia({ colorScheme: 'light' }); await h.waitForTimeout(150);

    /* Le surtitre du titre, et ce qui le fait changer. Débrief 28 : le
       surtitre (« HDK · TRANCHE 1 · DÉFINITION ÉLECTRIQUE ») est retiré ;
       l'avancement suivi se lit au titre (« Suivi concept harnais »), le
       périmètre à son bouton pressé et au bandeau des filtres — et rien ne
       se réécrit au-dessus du titre quand ils changent. */
    const surtitre = () => h.evaluate(() => ({ surtitre: !!document.getElementById('contexte-page') || !!document.querySelector('.masthead .contexte-page'),
      titre: document.getElementById('titre-page').textContent, avantTitre: !document.getElementById('titre-page').previousElementSibling,
      perimetre: (document.querySelector('#choix-perimetre button[aria-pressed="true"]') || { dataset: {} }).dataset.perimetre }));
    const s0 = await surtitre();
    await h.click('#choix-indicateur button[data-indicateur="concept"]'); await h.waitForTimeout(600);
    const s1 = await surtitre();
    await h.click('#choix-indicateur button[data-indicateur="def"]'); await h.waitForTimeout(600);
    await h.click('#choix-perimetre button[data-perimetre="PERSO"]'); await h.waitForTimeout(600);
    const s2 = await surtitre();
    verifier('B1, débrief 28 : plus de surtitre au-dessus du titre (ni « HDK · Définition électrique », ni après un changement) ; le titre suit l’avancement, le périmètre se lit à son bouton',
      [s0, s1, s2].every(s => !s.surtitre && s.avantTitre) && s0.titre === 'Suivi FWD' && s1.titre === 'Suivi concept harnais' && s2.titre === 'Suivi FWD' && s2.perimetre === 'PERSO',
      JSON.stringify([s0, s1, s2]));

    // Le bandeau des filtres : posé par-dessus, rien ne bouge (P-F6).
    await h.click('#choix-perimetre button[data-perimetre=""]'); await h.waitForTimeout(600);
    await h.evaluate(() => window.scrollTo(0, 0)); await h.waitForTimeout(200);
    const place = () => h.evaluate(() => {
      const r = s => { const b = document.querySelector(s).getBoundingClientRect(); return [Math.round(b.top), Math.round(b.left)]; };
      return { perso: r('#choix-perimetre button[data-perimetre="PERSO"]'), synthese: r('#section-synthese'), tendance: r('#section-tendance'),
               hauteur: document.documentElement.scrollHeight, y: window.scrollY };
    });
    const avantF = await place();
    await h.click('#choix-perimetre button[data-perimetre="PERSO"]'); await h.waitForTimeout(600);
    const apresF = await place();
    const ligneF = await h.evaluate(() => {
      const f = document.getElementById('filtres-actifs'), l = f.querySelector('.filtres-ligne'), x = f.querySelector('button[data-retirer]');
      return { visible: !f.hidden, place: Math.round(f.getBoundingClientRect().height), sousSommaire: Math.abs(l.getBoundingClientRect().top - document.getElementById('sommaire').getBoundingClientRect().bottom) <= 1,
               nom: x && x.getAttribute('aria-label') };
    });
    verifier('P-F6 : un clic sur PERSO pose le bandeau des filtres sans rien pousser — le bouton reste sous le pointeur, la synthèse ne descend pas',
      ligneF.visible && ligneF.place === 0 && ligneF.sousSommaire && Math.abs(apresF.perso[0] - avantF.perso[0]) <= 1 &&
      apresF.synthese[0] === avantF.synthese[0] && apresF.tendance[0] === avantF.tendance[0], JSON.stringify([avantF, apresF, ligneF]));
    verifier('X-A13 : la croix d’un jeton dit quel filtre elle retire', ligneF.nom === 'Retirer le filtre Périmètre : PERSO', ligneF.nom);
    await h.focus('#filtres-actifs button[data-retirer="perimetre"]');
    await h.keyboard.press('Enter'); await h.waitForTimeout(600);
    const apresX = await h.evaluate(() => ({ cache: document.getElementById('filtres-actifs').hidden, focus: document.activeElement === document.body ? 'body' : document.activeElement.tagName + '#' + document.activeElement.id }));
    verifier('X-A1 : retirer le dernier filtre au clavier ne jette pas le focus sur le corps de la page', apresX.cache && apresX.focus !== 'body', JSON.stringify(apresX));

    /* La fraîcheur des chiffres, sous la semaine (P-F10). Débrief 28 : la
       ligne « Chiffres du … · dernier relevé archivé … » est retirée — ni
       un relevé frais ni un relevé de vingt jours ne l'écrivent. */
    const fraicheur = await h.evaluate(() => {
      const iso = d => d.toISOString().slice(0, 10);
      const lire = () => { const m = document.querySelector('.masthead'); return { ligne: !!document.getElementById('fraicheur'), texte: m.textContent.replace(/\s+/g, ' '), vieux: !!m.querySelector('.vieux') }; };
      const jour = n => { const d = new Date(); d.setHours(12); d.setDate(d.getDate() - n); return iso(d); };
      const s = window.__jeuDExemple('HDK'); s.releves[s.releves.length - 1].date = jour(2);
      window.__chargerSource(s); const frais = lire();
      const v = window.__jeuDExemple('HDK'); v.releves[v.releves.length - 1].date = jour(20);
      window.__chargerSource(v); const vieux = lire();
      window.__chargerSource(window.__jeuDExemple('HDK'));
      return { frais, vieux };
    });
    verifier('P-F10, débrief 28 : plus de ligne de fraîcheur sous la semaine — ni « Chiffres du … », ni « dernier relevé archivé », ni l’âge en ambre d’un relevé de vingt jours',
      [fraicheur.frais, fraicheur.vieux].every(x => !x.ligne && !x.vieux && !/Chiffres du|relevé archivé|il y a \d+ jours/i.test(x.texte)), JSON.stringify(fraicheur));

    // La vue d'ensemble : une fenêtre (B18, P-F16, P-F18, X-A19).
    await h.evaluate(() => window.scrollTo(0, 0)); await h.waitForTimeout(200);
    await h.click('#voir-ensemble'); await h.waitForTimeout(900);
    const fen = await h.evaluate(() => {
      const d = document.getElementById('ensemble');
      return { modal: d.tagName === 'DIALOG' && d.open && !d.hidden, focus: document.activeElement.id,
               colonnes: [...d.querySelectorAll('thead th')].map(t => t.textContent).join('|'),
               note: (d.querySelector('.ensemble-note') || {}).textContent || '', jauge: d.querySelectorAll('.jauge-ensemble i').length,
               lignes: d.querySelectorAll('tbody tr').length, aria: document.getElementById('voir-ensemble').getAttribute('aria-expanded') };
    });
    verifier('B18 : « Vue d’ensemble » s’ouvre en fenêtre (dialog), le focus sur son titre, une jauge sous chaque « validés »',
      fen.modal && fen.focus === 'ensemble-titre' && fen.lignes === 3 && fen.jauge === 3 && fen.aria === 'true', JSON.stringify(fen));
    verifier('P-F18 : des colonnes claires — « À l’échéance » puis « Fin au rythme actuel » —, et « À l’arrêt » expliqué en clair sous le tableau',
      fen.colonnes === 'Contrat|Validés|Depuis le relevé précédent|Rythme tenu|À l’arrêt|Prochaine échéance|À l’échéance|Fin au rythme actuel' &&
      /À l’arrêt : plans en cours sans aucun changement depuis \d+ semaines/.test(fen.note), JSON.stringify(fen));
    await h.keyboard.press('Escape'); await h.waitForTimeout(300);
    const ferme = await h.evaluate(() => ({ ouverte: document.getElementById('ensemble').open, cache: document.getElementById('ensemble').hidden, focus: document.activeElement.id }));
    await h.click('#voir-ensemble'); await h.waitForTimeout(700);
    await h.mouse.click(6, 6); await h.waitForTimeout(300);
    const dehors = await h.evaluate(() => !document.getElementById('ensemble').open && document.activeElement.id === 'voir-ensemble');
    verifier('X-A19 : Échap ferme la fenêtre et rend le focus au bouton ; un clic à côté la ferme aussi',
      !ferme.ouverte && ferme.cache && ferme.focus === 'voir-ensemble' && dehors, JSON.stringify([ferme, dehors]));

    // Ce qui manque pour un contrat dit pourquoi (P-F12).
    await h.click('#choix-indicateur button[data-indicateur="concept"]'); await h.waitForTimeout(700);
    await h.click('#sommaire-liste a[data-chapitre="rapprochement"]', { force: true }); await h.waitForTimeout(300);
    const absente = await h.evaluate(() => {
      const a = document.querySelector('#sommaire-liste a[data-chapitre="rapprochement"]'), b = document.getElementById('raison-indispo');
      return { li: !a.parentNode.hidden && a.parentNode.hasAttribute('data-absent'), aria: a.getAttribute('aria-disabled'), couleur: getComputedStyle(a).color,
               bulle: b && !b.hidden ? b.textContent : '', y: window.scrollY };
    });
    await h.keyboard.press('Escape'); await h.waitForTimeout(100);
    const bulleFermee = await h.evaluate(() => document.getElementById('raison-indispo').hidden);
    verifier('P-F12 : sous le concept harnais, « 06 Comparaison » reste au sommaire, grisée ; un clic dit pourquoi (dans une bulle, sans bouger la page), Échap la ferme',
      absente.li && absente.aria === 'true' && /concept harnais/.test(absente.bulle) && absente.y === 0 && bulleFermee, JSON.stringify([absente, bulleFermee]));
    await h.click('#choix-indicateur button[data-indicateur="def"]'); await h.waitForTimeout(700);
    await h.selectOption('#select-contrat', 'THS'); await h.waitForTimeout(1000);
    await h.click('.commandes-graphe button[data-span="jalons"]', { force: true }); await h.waitForTimeout(300);
    const echH = await h.evaluate(() => {
      const b = document.querySelector('.commandes-graphe button[data-span="jalons"]'), r = document.getElementById('raison-indispo');
      return { visible: !b.hidden && b.getClientRects().length > 0, aria: b.getAttribute('aria-disabled'), titre: b.title, bulle: r && !r.hidden ? r.textContent : '',
               presses: [...document.querySelectorAll('.commandes-graphe .segmente button[aria-pressed="true"]')].map(x => x.dataset.span).join() };
    });
    verifier('P-F12 : sur THS (aucun jalon), « Échéances » reste à sa place, grisé ; un clic dit « Aucun jalon pour THS » sans changer le cadrage',
      echH.visible && echH.aria === 'true' && /^Aucun jalon pour THS/.test(echH.titre) && echH.bulle === echH.titre && echH.presses === '26', JSON.stringify(echH));
    await h.selectOption('#select-contrat', 'HDK'); await h.waitForTimeout(1000);

    // Des tranches : « HDK › Tranche 1 », et la barre ne glisse pas vers THS (B7).
    const tranches = await h.evaluate(() => {
      const liste = [{ id: 'HDK', nom: 'HDK', contrat: 'HDK', tranche: '' }, { id: 'HDK Tranche 2', nom: 'HDK › Tranche 2', contrat: 'HDK', tranche: 'Tranche 2' }, { id: 'THS', nom: 'THS', contrat: 'THS', tranche: '' }];
      const a = window.__jeuDExemple('HDK'); a.contrats = liste; a.contrat = 'HDK';
      window.__chargerSource(a);
      const x = () => Math.round(document.getElementById('select-contrat').getBoundingClientRect().left);
      /* Débrief 28 : plus de surtitre (#contexte-page) — le contrat montré se
         lit au menu du contrat et à la légende du tableau. */
      const montre = () => ({ surtitre: !!document.getElementById('contexte-page'), contrat: document.getElementById('select-contrat').value,
                              legende: (document.getElementById('legende-tableau') || {}).textContent || '' });
      const r1 = Object.assign(montre(), { tranches: [...document.querySelectorAll('#select-tranche option')].map(o => o.textContent).join(','),
                   tranche: (document.getElementById('select-tranche').selectedOptions[0] || {}).textContent,
                   menu: !document.getElementById('select-tranche').hidden, x: x() });
      const t = window.__jeuDExemple('THS'); t.contrats = liste; t.contrat = 'THS';
      window.__chargerSource(t);
      const r2 = Object.assign(montre(), { menu: !document.getElementById('select-tranche').hidden,
                   unique: !document.getElementById('tranche-unique').hidden && document.getElementById('tranche-unique').getClientRects().length > 0, x: x() });
      window.__chargerSource(a);
      window.scrollTo(0, 1500);
      return { r1, r2 };
    });
    await h.waitForTimeout(400);
    const marque = await h.evaluate(() => document.getElementById('sommaire-contrat').textContent);
    /* Débrief 28 : sans surtitre, « HDK › Tranche 1 » se lit au menu des
       tranches et à la marque du sommaire collé. */
    verifier('A-F10 : « HDK › Tranche 1 » — le menu des tranches dit « Tranche 1 », la marque du sommaire collé « HDK › Tranche 1 » ; plus de surtitre (débrief 28)',
      !tranches.r1.surtitre && tranches.r1.contrat === 'HDK' && tranches.r1.tranche === 'Tranche 1' && tranches.r1.tranches === 'Tranche 1,Tranche 2' && marque === 'HDK › Tranche 1', JSON.stringify([tranches.r1, marque]));
    verifier('B7 : vers THS (une seule tranche), la case « Tranche » garde sa place (« unique ») — le menu du contrat ne glisse pas sous le pointeur',
      tranches.r1.menu && !tranches.r2.menu && tranches.r2.unique && Math.abs(tranches.r2.x - tranches.r1.x) <= 1 && !tranches.r2.surtitre &&
      tranches.r2.contrat === 'THS' && /^Plans GATES de THS : /.test(tranches.r2.legende), JSON.stringify(tranches));
    await h.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); window.scrollTo(0, 0); });
    await cH.close();

    // Un classeur lent, puis en panne : l'attente et l'erreur d'un changement de contrat (D8, A-F4, A-F5, X-A4).
    const cL = await contexte();
    await cL.addInitScript(() => {
      window.__lenteur = 900; window.__panne = '';
      window.SUIVI_FWD_API = { chargerContrat: function (id, rappel) {
        setTimeout(function () { if (window.__panne) rappel(null, window.__panne); else rappel(window.__jeuDExemple(id)); }, window.__lenteur);
      } };
    });
    const l = await page(cL, 'lot H lent');
    const lireL = () => l.evaluate(() => ({
      sel: document.getElementById('select-contrat').value, grise: document.getElementById('select-contrat').disabled,
      barre: !document.getElementById('barre-chargement').hidden, attente: document.body.getAttribute('data-attente'),
      occupe: [...document.querySelectorAll('main, .page > section')].some(sec => sec.getAttribute('aria-busy') === 'true'),   // débrief 27 : le <main> du lot G porte aria-busy
      concept: (document.querySelector('#choix-indicateur button[aria-pressed="true"]') || {}).dataset.indicateur,
      /* Débrief 28 : plus de surtitre (#contexte-page) à lire ; ce que la page
         montre se recompose de ce qui reste à l'écran — le contrat nommé par
         la légende du tableau, l'avancement par le titre (« Suivi concept
         harnais ») : « THS · Concept harnais », comme le surtitre d'avant. */
      ind: window.__indicateur().indicateur,
      contexte: (((document.getElementById('legende-tableau') || {}).textContent || '').match(/^Plans GATES de (.+?) : /) || [, '?'])[1] + ' · ' +
        (/concept harnais/i.test(document.getElementById('titre-page').textContent) ? 'Concept harnais' : 'Définition électrique'),
      x: Math.round(document.getElementById('select-contrat').getBoundingClientRect().left),
      alerte: document.getElementById('alerte-contrat').hidden ? '' : document.getElementById('alerte-contrat-texte').textContent,
      role: document.getElementById('alerte-contrat').getAttribute('role'), focus: document.activeElement.id
    }));
    const l0 = await lireL();
    await l.focus('#select-contrat');
    await l.selectOption('#select-contrat', 'THS'); await l.waitForTimeout(250);
    const l1 = await lireL();
    verifier('D8 / A-F14 : pendant l’attente, rien ne bouge dans la barre ; le menu garde THS, reste à portée (focus compris) ; un trait en haut de l’écran, la page d’avant voilée et aria-busy',
      l1.sel === 'THS' && !l1.grise && l1.barre && l1.attente === 'contrat' && l1.occupe && l1.x === l0.x && l1.focus === 'select-contrat' && l1.contexte === l0.contexte,
      JSON.stringify([l0, l1]));
    await l.click('#choix-indicateur button[data-indicateur="concept"]'); await l.waitForTimeout(150);
    const l2 = await lireL();
    await l.waitForTimeout(1600);
    const l3 = await lireL();
    verifier('A-F4 : « Concept harnais » cliqué pendant l’attente est gardé (pressé tout de suite) et appliqué à l’arrivée — le menu ne revient jamais à HDK',
      l2.sel === 'THS' && l2.concept === 'concept' && l2.ind === 'def' && l3.sel === 'THS' && l3.ind === 'concept' && !l3.barre && !l3.occupe &&
      l3.contexte === 'THS · Concept harnais', JSON.stringify([l2, l3]));
    /* La panne, et une horloge avancée d'une minute : la demande faite
       d'avance à l'ouverture du menu (débrief 23) n'est plus bonne, la page
       redemande au classeur — qui ne répond pas. */
    await l.evaluate(() => { window.__panne = 'Service indisponible'; const vrai = Date.now; Date.now = () => vrai() + 60000; });
    await l.selectOption('#select-contrat', 'VRK'); await l.waitForTimeout(2000);
    const l4 = await lireL();
    verifier('A-F5 : en panne, un bandeau d’alerte dit ce qui a échoué et ce qu’on voit encore, avec « Réessayer » ; le menu revient au contrat affiché',
      l4.role === 'alert' && /^VRK n’a pas pu être chargé : service indisponible\. La page montre toujours THS\.$/.test(l4.alerte) && l4.sel === 'THS' && !l4.barre && !l4.attente,
      JSON.stringify(l4));
    await l.evaluate(() => { window.__panne = ''; });
    await l.click('#reessayer-contrat'); await l.waitForTimeout(2000);
    const l5 = await lireL();
    verifier('A-F5 : « Réessayer » relance la même demande ; à l’arrivée le bandeau s’efface et le focus est sur le menu',
      l5.sel === 'VRK' && /^VRK · /.test(l5.contexte) && l5.alerte === '' && l5.focus === 'select-contrat', JSON.stringify(l5));
    // Au clavier : les flèches sur le menu fermé ne chargent qu'après une pause (X-A4).
    await l.focus('#select-contrat');
    await l.keyboard.press('ArrowUp'); await l.waitForTimeout(250);
    const k1 = await lireL();
    await l.waitForTimeout(2200);
    const k2 = await lireL();
    verifier('X-A4 : une flèche sur le menu fermé ne charge pas tout de suite (600 ms de pause) ; puis le contrat arrive et le focus reste sur le menu',
      k1.sel !== 'VRK' && !k1.attente && /^VRK · /.test(k1.contexte) && k2.sel === k1.sel && new RegExp('^' + k1.sel + ' · ').test(k2.contexte) && k2.focus === 'select-contrat',
      JSON.stringify([k1, k2]));
    await cL.close();

    // Au téléphone : la grille compacte et le bandeau des filtres sur une ligne (M5).
    const cT = await contexte({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const t = await page(cT, 'lot H téléphone');
    await t.tap('#choix-perimetre button[data-perimetre="PERSO"]'); await t.waitForTimeout(700);
    await t.evaluate(() => { const b = document.querySelector('#etats .etat-btn[data-etat]'); if (b) b.click(); }); await t.waitForTimeout(700);
    const tel = await t.evaluate(() => {
      const r = e => e.getBoundingClientRect();
      const jetons = [...document.querySelectorAll('.filtres-ligne .jeton')], zone = document.getElementById('filtres-jetons');
      const effacer = document.getElementById('tout-effacer');
      return { large: document.documentElement.scrollWidth <= window.innerWidth,
               uneLigne: jetons.length === 2 && new Set(jetons.map(j => Math.round(r(j).top))).size === 1 && r(document.querySelector('.filtres-ligne')).height <= 56,
               effacer: effacer.innerText.trim(), dedans: r(jetons[0]).right <= r(zone).right + 1,
               mot: getComputedStyle(document.querySelector('.filtres-ligne .mot')).display,
               contrat: Math.round(r(document.getElementById('select-contrat')).width), barre: Math.round(r(document.getElementById('portee')).width) };
    });
    verifier('M5 : au téléphone, le bandeau des filtres tient sur une ligne (jetons qui défilent, « Effacer » au bout), sans faire déborder la page',
      tel.large && tel.uneLigne && tel.effacer === 'Effacer' && tel.dedans && tel.mot === 'none', JSON.stringify(tel));
    await cT.close();
  }

  // =================================================================
  /* Débrief 27, lot D : le tableau des plans et la fiche d'un plan — la vue
     essentielle pour tout le monde (retenue), les colonnes vides masquées,
     « — » dans les cases vides, le tableau au clavier (deux arrêts de
     tabulation, les flèches), une colonne déplacée sans glisser, la ligne
     SEE dans la fiche, Échap qui la ferme, l'export, la recherche d'un plan
     dans le sommaire, le téléphone. */
  section('Débrief 27 : le tableau des plans (lot D)');
  {
    const cD = await contexte({ prefsVierges: true });
    const d = await page(cD, 'lot D');
    await d.evaluate(() => document.getElementById('section-plans').scrollIntoView());
    await d.waitForTimeout(300);
    const neuf = await d.evaluate(() => {
      const cs = e => getComputedStyle(e);
      const presse = [...document.querySelectorAll('#vue-tableau button')].map(b => b.dataset.vue + ':' + b.getAttribute('aria-pressed')).join(' ');
      const groupes = [...document.querySelectorAll('tr.groupes th')].map(t => t.textContent.trim());
      const cap = document.querySelector('table.plans caption');
      const ref = document.querySelector('#corps-tableau .ref-plan');
      return {
        presse, n: document.querySelectorAll('tr.titres th').length, groupes,
        caption: cap ? cap.textContent : '', cv: cs(document.getElementById('cadre-tableau')).contentVisibility,
        tirets: document.querySelectorAll('#corps-tableau td.tiret-vide').length,
        traits: [...document.querySelectorAll('#corps-tableau td')].filter(td => td.textContent.trim() === '-').length,
        refSoulignee: ref ? cs(ref).textDecorationStyle + ' ' + cs(ref).textDecorationLine : '',
        filtresCaches: document.querySelector('tr.filtres').hidden,
        /* Débrief 28 : plus de bouton « Filtrer par colonne » (ni « Copier le
           tableau », ni « Télécharger (CSV) ») : on relève s'ils se voient. */
        boutonFiltres: (b => !!b && b.getClientRects().length > 0)(document.getElementById('ouvrir-filtres')),
        boutonsExport: ['copier-tableau', 'telecharger-tableau'].filter(id => { const b = document.getElementById(id); return !!b && b.getClientRects().length > 0; }),
        /* Débrief 29 : la zone des actions, vide, est cachée — innerText d'un
           élément non dessiné rendrait tout son texte, même caché : on ne lit
           que ce qui se voit. */
        motsOutils: (a => a && a.getClientRects().length > 0 ? a.innerText : '')(document.getElementById('actions-tableau')),
        champsFiltres: [...document.querySelectorAll('tr.filtres input[data-filtre]')].filter(i => i.getClientRects().length > 0).length,
        arretsCorps: document.querySelectorAll('#corps-tableau [tabindex="0"]').length,
        refsHorsTab: [...document.querySelectorAll('#corps-tableau .ref-plan')].filter(b => b.getAttribute('tabindex') !== '-1' && b.getAttribute('tabindex') !== '0').length,
        arretsTete: document.querySelectorAll('tr.titres button[data-tri][tabindex="0"]').length,
        triHaut: Math.min(...[...document.querySelectorAll('tr.titres button[data-tri]')].map(b => b.getBoundingClientRect().height)),
        stocke: (() => { try { return localStorage.getItem('suivi-fwd:v1') || ''; } catch (e) { return ''; } })()
      };
    });
    verifier('un nouveau venu ouvre sur la « Vue essentielle » (P-F15)', neuf.presse === 'toutes:false essentielle:true' && neuf.n > 1 && neuf.n <= 9, JSON.stringify([neuf.presse, neuf.n]));
    /* Débrief 29 (P-F15) : la vue essentielle n'a plus de rangée de groupes
       (« Informations principales » s'y répétait trois fois) ; le libellé
       « Avancement (GATES · HDK AA 011) » et les cases jamais vides se
       vérifient en « Toutes les colonnes » (section « Débrief 29 : le
       tableau des plans (lot PL) »). */
    verifier('en vue essentielle, plus de rangée de groupes au-dessus des en-têtes (débrief 29, P-F15)',
      neuf.groupes.length === 0, JSON.stringify(neuf.groupes));
    verifier('le tableau a un nom (légende) qui dit ce qu’il montre, et plus de content-visibility qui cache ses lignes (X-A11)',
      /^Plans GATES de HDK : \d+ lignes, triées par Référence UD, ordre croissant/.test(neuf.caption) && neuf.cv !== 'auto', JSON.stringify([neuf.caption, neuf.cv]));
    verifier('une case vide s’écrit « — » (B22), plus jamais « - »', neuf.tirets > 0 && neuf.traits === 0, JSON.stringify([neuf.tirets, neuf.traits]));
    /* La démonstration écrit « non renseigné » à blanc : un plan reçoit ici
       « EMPTY », comme l'extract de GATES l'écrit. */
    const empty = await d.evaluate(() => {
      const s = window.__jeuDExemple('HDK'); s.plans[0].avancement = 'EMPTY'; window.__chargerSource(s);
      const e = document.querySelector('#corps-tableau .vide-gates');
      return e ? { titre: e.getAttribute('title'), masque: getComputedStyle(e, '::after').content, texte: e.textContent } : null;
    });
    verifier('« EMPTY » reste écrit tel quel, et dit son sens au survol et aux lecteurs d’écran (P-F14)',
      !!empty && empty.texte === 'EMPTY' && empty.titre === 'Non renseigné (EMPTY dans GATES)' && /non renseigné dans GATES/.test(empty.masque || ''), JSON.stringify(empty));
    await d.evaluate(() => window.__chargerSource(window.__jeuDExemple('HDK')));
    await d.waitForTimeout(300);
    verifier('la référence se voit cliquable sans survol : soulignée en pointillé (P-F17)', /dotted/.test(neuf.refSoulignee) && /underline/.test(neuf.refSoulignee), neuf.refSoulignee);
    /* Débrief 27 (X-A2) : la rangée était repliée derrière « Filtrer par
       colonne ». Débrief 28 : elle est toujours affichée, même pour un
       nouveau venu, et le bouton est retiré. */
    verifier('la rangée des filtres de colonne est toujours affichée, même pour un nouveau venu : un champ par colonne (débrief 28)',
      !neuf.filtresCaches && neuf.champsFiltres === neuf.n, JSON.stringify([neuf.filtresCaches, neuf.champsFiltres, neuf.n]));
    verifier('plus de bouton « Filtrer par colonne » au-dessus du tableau (débrief 28)',
      !neuf.boutonFiltres && !/Filtrer par colonne/.test(neuf.motsOutils), JSON.stringify([neuf.boutonFiltres, neuf.motsOutils]));
    verifier('plus de bouton « Copier le tableau » ni « Télécharger (CSV) » au-dessus du tableau (débrief 28)',
      neuf.boutonsExport.length === 0 && !/Copier le tableau|Télécharger/.test(neuf.motsOutils), JSON.stringify([neuf.boutonsExport, neuf.motsOutils]));
    verifier('un seul arrêt de tabulation pour les lignes, un pour les en-têtes (X-A2)',
      neuf.arretsCorps === 1 && neuf.refsHorsTab === 0 && neuf.arretsTete === 1, JSON.stringify([neuf.arretsCorps, neuf.refsHorsTab, neuf.arretsTete]));
    verifier('les boutons de tri font 24 px de haut au moins (2.5.8)', neuf.triHaut >= 24, String(neuf.triHaut));

    /* La ligne survolée se voit, et le gris tertiaire y reste lisible. */
    await d.hover('#corps-tableau tr:nth-child(3) td:nth-child(3)');
    const survol = await d.evaluate(() => {
      const lum = c => { const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
      const cr = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
      const td = document.querySelector('#corps-tableau tr:nth-child(3) td:nth-child(3)');
      const fond = getComputedStyle(td).backgroundColor, surface = getComputedStyle(document.getElementById('section-plans')).backgroundColor;
      const gris = getComputedStyle(document.querySelector('.tiret-vide') || td).color;
      return { fond, ecart: cr(fond, surface), gris: cr(gris, fond) };
    });
    verifier('une ligne survolée se voit (fond distinct de la surface), le gris tertiaire y tient 4,5:1 (P-F17)', survol.ecart > 1.08 && survol.gris >= 4.5, JSON.stringify(survol));

    /* Au clavier : les flèches, ↑ vers l'en-tête, Alt + → déplace la colonne. */
    await d.focus('#corps-tableau [tabindex="0"]');
    await d.keyboard.press('ArrowDown'); await d.keyboard.press('ArrowRight');
    const fleches = await d.evaluate(() => {
      const a = document.activeElement, tr = a.closest('tr');
      return { tag: a.tagName, ligne: [...document.querySelectorAll('#corps-tableau tr')].indexOf(tr), col: a.cellIndex, tab: a.getAttribute('tabindex'),
               autres: document.querySelectorAll('#corps-tableau [tabindex="0"]').length };
    });
    verifier('↓ puis → : la case de la deuxième ligne, deuxième colonne prend le focus et l’arrêt de tabulation (un seul)',
      fleches.tag === 'TD' && fleches.ligne === 1 && fleches.col === 1 && fleches.tab === '0' && fleches.autres === 1, JSON.stringify(fleches));
    await d.keyboard.press('ArrowUp'); await d.keyboard.press('ArrowUp');
    const versTete = await d.evaluate(() => document.activeElement.getAttribute('data-tri'));
    await d.keyboard.press('ArrowRight'); await d.keyboard.press('ArrowRight');
    const cleDeplacee = await d.evaluate(() => document.activeElement.getAttribute('data-tri'));
    const avantOrdre = await d.evaluate(() => [...document.querySelectorAll('tr.titres th')].map(t => t.dataset.cle));
    await d.keyboard.press('Alt+ArrowRight'); await d.waitForTimeout(300);
    const apresAlt = await d.evaluate(() => ({ ordre: [...document.querySelectorAll('tr.titres th')].map(t => t.dataset.cle), actif: document.activeElement.getAttribute('data-tri') }));
    await d.waitForFunction(() => /déplacée en/.test((document.getElementById('annonce') || {}).textContent || ''), null, { timeout: 3000 }).catch(() => {});
    const annonceAlt = await d.evaluate(() => (document.getElementById('annonce') || {}).textContent);
    const iAv = avantOrdre.indexOf(cleDeplacee);
    verifier('↑ depuis la première ligne remonte à l’en-tête ; Alt + → déplace la colonne d’un cran, le focus la suit, et c’est dit (2.5.7)',
      versTete === 'avancement' && iAv !== -1 && apresAlt.ordre.indexOf(cleDeplacee) === iAv + 1 && apresAlt.actif === cleDeplacee && /déplacée en/.test(annonceAlt || ''),
      JSON.stringify([versTete, cleDeplacee, iAv, apresAlt, annonceAlt]));
    /* Sans glisser, à la souris : le menu de la poignée. */
    const thMenu = 'tr.titres th[data-cle="' + cleDeplacee + '"]';
    await d.hover(thMenu);
    await d.click(thMenu + ' button.poignee');
    const menu = await d.evaluate(() => { const m = document.getElementById('menu-colonne'); return { vu: !m.hidden, boutons: [...m.querySelectorAll('button')].map(b => b.textContent.trim() + (b.disabled ? '(off)' : '')) }; });
    await d.click('#menu-colonne button[data-deplacer="-1"]'); await d.waitForTimeout(300);
    const apresMenu = await d.evaluate(() => [...document.querySelectorAll('tr.titres th')].map(t => t.dataset.cle));
    verifier('la poignée ouvre « ← Déplacer à gauche / Déplacer à droite → », et le clic déplace la colonne (2.5.7)',
      menu.vu && menu.boutons.length === 2 && apresMenu.indexOf(cleDeplacee) === iAv, JSON.stringify([menu, apresMenu.indexOf(cleDeplacee), iAv]));
    const pad = await d.evaluate(() => { const s = getComputedStyle(document.getElementById('defile')); return { haut: parseFloat(s.scrollPaddingTop), gauche: parseFloat(s.scrollPaddingLeft) }; });
    verifier('le cadre garde la place des en-têtes collés et des colonnes figées (scroll-padding, X-A3)', pad.haut > 30 && pad.gauche > 100, JSON.stringify(pad));

    /* « Toutes les colonnes » : retenu, et les colonnes vides masquées, dites. */
    await d.click('#vue-tableau button[data-vue="toutes"]'); await d.waitForTimeout(700);
    const toutes = await d.evaluate(() => ({ n: document.querySelectorAll('tr.titres th').length, vides: document.getElementById('colonnes-vides').textContent,
      c4: !!document.querySelector('tr.titres th[data-cle="colonne_4"]'), stocke: localStorage.getItem('suivi-fwd:v1') }));
    verifier('« Toutes les colonnes » masque les colonnes vides de la sélection et le dit (« N colonnes vides masquées · Afficher »)',
      toutes.n < 137 && !toutes.c4 && /^\d+ colonnes vides masquées/.test(toutes.vides) && /Afficher$/.test(toutes.vides) && toutes.n + parseInt(toutes.vides, 10) === 137,
      JSON.stringify([toutes.n, toutes.vides.slice(0, 60)]));
    await d.click('#colonnes-vides button'); await d.waitForTimeout(700);
    const affichees = await d.evaluate(() => ({ n: document.querySelectorAll('tr.titres th').length, vides: document.getElementById('colonnes-vides').textContent }));
    verifier('« Afficher » les remet toutes (137), « Masquer » les retire', affichees.n === 137 && /affichées/.test(affichees.vides) && /Masquer$/.test(affichees.vides), JSON.stringify(affichees));
    await d.waitForTimeout(600);
    await d.reload(); await attendrePrete(d, 1300);
    const rouvert = await d.evaluate(() => ({ presse: [...document.querySelectorAll('#vue-tableau button[aria-pressed="true"]')].map(b => b.dataset.vue).join(), n: document.querySelectorAll('tr.titres th').length }));
    verifier('les deux choix se retiennent : la page rouverte est sur « Toutes les colonnes », colonnes vides affichées', rouvert.presse === 'toutes' && rouvert.n === 137, JSON.stringify(rouvert));

    /* Filtrer par colonne : déplié, focus au premier champ ; un filtre posé
       garde la rangée. Débrief 28 : la rangée est toujours là, sans bouton —
       on tape directement dans le premier champ ; le filtre posé se voit
       (champ marqué actif, jeton du bandeau des filtres) et la rangée reste. */
    await d.evaluate(() => document.getElementById('section-plans').scrollIntoView());
    await d.click('tr.filtres input[data-filtre="reference"]');
    const deplie = await d.evaluate(() => ({ cache: document.querySelector('tr.filtres').hidden, actif: document.activeElement.getAttribute('data-filtre') }));
    await d.keyboard.type('GAE21');
    await d.waitForFunction(() => { const i = document.querySelector('tr.filtres input[data-filtre="reference"]'); return !!i && i.dataset.actif === 'true' && !document.getElementById('filtres-actifs').hidden; }, null, { timeout: 5000 }).catch(() => {});
    const garde = await d.evaluate(() => ({ cache: document.querySelector('tr.filtres').hidden, actif: (document.querySelector('tr.filtres input[data-filtre="reference"]') || {}).dataset,
      bouton: !!document.getElementById('ouvrir-filtres') && document.getElementById('ouvrir-filtres').getClientRects().length > 0,
      jeton: document.getElementById('filtres-actifs').hidden ? '' : document.getElementById('filtres-actifs').textContent.replace(/\s+/g, ' ') }));
    verifier('la rangée des filtres est là : on tape dans le champ de la référence, sans rien déplier ; le filtre posé se marque (champ actif, jeton du bandeau) et la rangée reste (débrief 28)',
      !deplie.cache && deplie.actif === 'reference' && !garde.cache && !!garde.actif && garde.actif.actif === 'true' && /GAE21/.test(garde.jeton), JSON.stringify([deplie, garde]));
    await reinitialiser(d);

    /* L'export : ce que montre le tableau, à la mode d'Excel. */
    await d.click('#vue-tableau button[data-vue="essentielle"]'); await d.waitForTimeout(500);
    await d.fill('#recherche', 'GAE2'); await d.waitForTimeout(500);
    const exp = await d.evaluate(() => {
      const tsv = window.__exportTableau('tsv'), csv = window.__exportTableau('csv');
      return { lignesTSV: tsv.split('\n').length, tete: tsv.split('\n')[0], lignesTableau: document.querySelectorAll('#corps-tableau tr').length,
               titres: [...document.querySelectorAll('tr.titres th')].map(t => t.textContent.trim()).join('\t'),
               bom: csv.charCodeAt(0) === 0xfeff, pointVirgule: csv.split('\r\n')[0].split(';').length };
    });
    /* Débrief 28 : les boutons « Copier le tableau » et « Télécharger (CSV) »
       sont retirés ; l'export interne qu'ils appelaient reste (il prend ce
       que montre le tableau) et se vérifie toujours. */
    verifier('l’export du tableau (gardé sans ses boutons, débrief 28) prend les lignes filtrées et les colonnes affichées, en colonnes pour Excel (P-F21)',
      exp.lignesTSV === exp.lignesTableau + 1 && exp.tete === exp.titres && exp.bom && exp.pointVirgule > 1,
      JSON.stringify([exp.lignesTSV, exp.lignesTableau, exp.tete.slice(0, 60), exp.bom, exp.pointVirgule]));
    /* Débrief 28 : plus rien à cliquer pour télécharger ni copier le
       tableau — aucun bouton visible, aucun mot posé sous les boutons. (Le
       bouton « Filtrer par colonne » a sa vérification plus haut.) */
    const sansExport = await d.evaluate(() => {
      const vu = id => { const b = document.getElementById(id); return !!b && b.getClientRects().length > 0 && !b.closest('[hidden]'); };
      return { telecharger: vu('telecharger-tableau'), copier: vu('copier-tableau'), filtrer: vu('ouvrir-filtres'),
               boutons: [...document.querySelectorAll('#section-plans button')].filter(b => b.getClientRects().length && /Télécharger|Copier le tableau/.test(b.textContent)).length,
               msg: document.getElementById('message-tableau').hidden ? '' : document.getElementById('message-tableau').textContent };
    });
    verifier('plus de « Télécharger (CSV) » ni de « Copier le tableau » dans la section des plans — rien ne se télécharge, rien ne s’écrit sous le tableau (débrief 28)',
      !sansExport.telecharger && !sansExport.copier && sansExport.boutons === 0 && sansExport.msg === '', JSON.stringify(sansExport));
    await d.fill('#recherche', ''); await d.waitForTimeout(400);

    /* La fiche d'un plan : la ligne SEE, la croix qui dit vrai, Échap, le focus rendu. */
    const refSee = await d.evaluate(() => {
      const r = [...document.querySelectorAll('#corps-tableau .ref-plan')].map(b => b.dataset.refPlan);
      return r;
    });
    await d.click('#corps-tableau .ref-plan >> nth=3'); await d.waitForTimeout(700);
    const fiche = await d.evaluate(() => ({ actif: document.activeElement.id, croix: (document.querySelector('#fiche-plan [data-fermer-plan]') || {}).getAttribute && document.querySelector('#fiche-plan [data-fermer-plan]').getAttribute('aria-label'),
      see: (document.getElementById('fiche-plan-see') || {}).textContent || '', ref: (document.querySelector('#fiche-plan .ref') || {}).textContent }));
    verifier('la fiche s’ouvre son titre au focus ; la croix dit « Fermer l’historique » (P-F16) ; elle dit où en est le plan dans SEE (P-F7)',
      fiche.actif === 'titre-fiche-plan' && fiche.croix === 'Fermer l’historique' && /^Dans SEE\s*:/.test(fiche.see.replace(/ /g, ' ')) && /→/.test(fiche.see), JSON.stringify(fiche));
    await d.keyboard.press('Escape'); await d.waitForTimeout(600);
    const echap = await d.evaluate(() => ({ cache: document.getElementById('fiche-plan').hidden, actif: document.activeElement.getAttribute('data-ref-plan'), lignes: document.querySelectorAll('#corps-tableau tr').length }));
    verifier('Échap ferme la fiche, le tableau revient à tous les plans et le focus à la référence cliquée',
      echap.cache && echap.actif === fiche.ref && echap.lignes > 1, JSON.stringify([echap, fiche.ref]));
    /* Un plan connu de SEE : sa ligne, « Voir la ligne SEE », la recherche SEE qui lit une référence de GATES. */
    /* Un plan qui a sa ligne dans SEE : le tableau de SEE le dit (data-plan). */
    const connu = await d.evaluate(() => { const tr = document.querySelector('#corps-seconde tr[data-plan]'); return tr ? tr.dataset.plan : null; });
    if (connu) {
      await d.fill('#recherche', connu); await d.waitForTimeout(500);
      await d.click('#corps-tableau .ref-plan'); await d.waitForTimeout(600);
    }
    const ligneSee = await d.evaluate(() => (document.getElementById('fiche-plan-see') || {}).textContent || '');
    if (connu) { await d.click('#fiche-plan button[data-voir-see]'); await d.waitForTimeout(600); }
    const voir = await d.evaluate(() => ({ base: [...document.querySelectorAll('#choix-base button[aria-pressed="true"]')].map(b => b.dataset.base).join(),
      lignes: [...document.querySelectorAll('#corps-seconde tr[data-plan]')].map(tr => tr.dataset.plan) }));
    verifier('« Voir la ligne SEE » passe au tableau de SEE, réduit aux lignes de ce plan (P-F7)',
      !!connu && voir.base === 'la' && voir.lignes.length >= 1 && voir.lignes.every(r => r === connu), JSON.stringify([connu, ligneSee.slice(0, 120), voir]));
    await d.click('#choix-base button[data-base="ici"]'); await d.waitForTimeout(300);
    await d.evaluate(() => { const x = document.querySelector('#fiche-plan [data-fermer-plan]'); if (x) x.click(); });
    await d.waitForTimeout(300);
    await d.click('#choix-base button[data-base="la"]'); await d.waitForTimeout(300);
    await d.fill('#recherche-seconde', connu || 'X'); await d.waitForTimeout(500);
    const parGates = await d.evaluate(() => [...document.querySelectorAll('#corps-seconde tr[data-plan]')].map(tr => tr.dataset.plan));
    verifier('la recherche de SEE trouve la ligne d’une référence écrite à la mode de GATES (même clé que la comparaison)',
      !!connu && parGates.length >= 1 && parGates.every(r => r === connu), JSON.stringify([connu, parGates]));
    await d.fill('#recherche-seconde', ''); await d.waitForTimeout(300);
    await d.click('#choix-base button[data-base="ici"]'); await d.waitForTimeout(300);

    /* Chercher un plan depuis le sommaire (combobox). */
    await d.evaluate(() => window.scrollTo(0, 0)); await d.waitForTimeout(200);
    const debut = (connu || 'GAE2').slice(0, 4);
    /* Débrief 28 : « Chercher un plan » est partout une loupe ronde, au bout
       du sommaire (le champ de 200 px poussait le sommaire) ; elle ouvre le
       champ par-dessus, le focus dedans. */
    await d.click('#cherche-plan-ouvrir');
    await d.waitForFunction(() => document.activeElement && document.activeElement.id === 'cherche-plan-champ', null, { timeout: 3000 }).catch(() => {});
    const loupe28 = await d.evaluate(() => ({ ouvert: document.getElementById('cherche-plan').getAttribute('data-ouvert'), actif: document.activeElement.id,
      rond: getComputedStyle(document.getElementById('cherche-plan-ouvrir')).borderTopLeftRadius }));
    await d.keyboard.type(debut, { delay: 20 }); await d.waitForTimeout(400);
    const liste = await d.evaluate(() => ({ exp: document.getElementById('cherche-plan-champ').getAttribute('aria-expanded'),
      options: [...document.querySelectorAll('#cherche-plan-liste li[role="option"][data-ref]')].map(o => o.dataset.ref),
      choisi: document.getElementById('cherche-plan-champ').getAttribute('aria-activedescendant') }));
    await d.keyboard.press('ArrowDown'); await d.keyboard.press('Enter'); await d.waitForTimeout(800);
    const ouvert = await d.evaluate(() => ({ fiche: !document.getElementById('fiche-plan').hidden, ref: (document.querySelector('#fiche-plan .ref') || {}).textContent, actif: document.activeElement.id,
      exp: document.getElementById('cherche-plan-champ').getAttribute('aria-expanded') }));
    verifier('« Chercher un plan » (sommaire) : la loupe ronde ouvre le champ (débrief 28) ; il propose les plans qui commencent par la saisie, au clavier (combobox) ; Entrée ouvre la fiche du plan choisi (P-F23)',
      loupe28.ouvert === 'true' && loupe28.actif === 'cherche-plan-champ' && loupe28.rond === '50%' && liste.exp === 'true' && liste.options.length >= 2 && liste.options.every(r => r.indexOf(debut) === 0) && !!liste.choisi &&
      ouvert.fiche && ouvert.ref === liste.options[1] && ouvert.actif === 'titre-fiche-plan' && ouvert.exp === 'false', JSON.stringify([loupe28, liste, ouvert]));
    await d.keyboard.press('Escape'); await d.waitForTimeout(500);
    const retourChamp = await d.evaluate(() => document.activeElement.id);
    /* Débrief 28 : la recherche est une loupe à toutes les largeurs — le
       plan choisi, elle se replie ; Échap sur la fiche rend le focus à la
       loupe (comme au téléphone), plus au champ, replié. */
    verifier('Échap ferme la fiche ouverte par la recherche et rend le focus à la recherche — la loupe, le champ replié (débrief 28)', retourChamp === 'cherche-plan-ouvrir', retourChamp);
    if (connu) {
      const formeSee = await d.evaluate(r => window.__racineSEE(window.__analyserUD(r).racine), connu);
      if (!(await d.evaluate(() => document.getElementById('cherche-plan').getAttribute('data-ouvert') === 'true'))) {
        await d.click('#cherche-plan-ouvrir');
        await d.waitForFunction(() => document.activeElement && document.activeElement.id === 'cherche-plan-champ', null, { timeout: 3000 }).catch(() => {});
      }
      await d.fill('#cherche-plan-champ', formeSee); await d.waitForTimeout(400);
      const parSee = await d.evaluate(() => [...document.querySelectorAll('#cherche-plan-liste li[data-ref]')].map(o => o.dataset.ref));
      verifier('une référence écrite à la mode de SEE trouve le plan de GATES', parSee.indexOf(connu) !== -1, JSON.stringify([formeSee, parSee]));
      await d.keyboard.press('Escape'); await d.keyboard.press('Escape');
    }
    await cD.close();

    /* Le téléphone : seule la référence figée, le tableau dans la page, la loupe. */
    const cT = await contexte({ prefsVierges: true, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const t = await page(cT, 'lot D téléphone');
    await t.evaluate(() => document.getElementById('section-plans').scrollIntoView()); await t.waitForTimeout(400);
    const tel = await t.evaluate(() => {
      const cs = e => getComputedStyle(e);
      const ref = document.querySelector('tr.titres th.col-ref'), suivie = document.querySelector('tr.titres th[data-cle="avancement"]');
      const td = document.querySelector('#corps-tableau td.col-ref');
      return { refLeft: cs(ref).left, refPos: cs(ref).position, suivieLeft: cs(suivie).left, refLarg: td.getBoundingClientRect().width,
               maxH: cs(document.getElementById('defile')).maxHeight, loupe: cs(document.getElementById('cherche-plan-ouvrir')).display,
               champ: cs(document.getElementById('cherche-plan-cadre')).display, debord: document.documentElement.scrollWidth - window.innerWidth,
               refCible: (() => { const b = document.querySelector('#corps-tableau .ref-plan'); const a = getComputedStyle(b, '::after'); return a.content; })() };
    });
    verifier('téléphone : seule la référence reste figée (40 % de l’écran au plus), la colonne suivie défile (M1)',
      tel.refPos === 'sticky' && tel.refLeft === '0px' && tel.suivieLeft === 'auto' && tel.refLarg <= 390 * 0.4 + 0.5, JSON.stringify(tel));
    verifier('téléphone : le tableau prend sa hauteur dans la page (pas de cadre qui retient le pouce, D10) ; la référence a sa cible de 44 px',
      tel.maxH === 'none' && tel.refCible !== 'none' && tel.debord <= 0, JSON.stringify(tel));
    await t.click('#cherche-plan-ouvrir'); await t.waitForTimeout(200);
    const loupe = await t.evaluate(() => ({ ouvert: document.getElementById('cherche-plan').getAttribute('data-ouvert'), actif: document.activeElement.id,
      large: document.getElementById('cherche-plan-champ').getBoundingClientRect().width }));
    verifier('téléphone : « Chercher un plan » est une loupe qui ouvre le champ sur toute la largeur du sommaire',
      tel.loupe !== 'none' && tel.champ === 'none' && loupe.ouvert === 'true' && loupe.actif === 'cherche-plan-champ' && loupe.large > 250, JSON.stringify([tel.loupe, tel.champ, loupe]));
    await cT.close();

    /* Les tranches, au budget réel (sans le seuil levé par la batterie). */
    const cR = await nav.newContext({ viewport: { width: 1280, height: 950 } });
    await cR.addInitScript(() => { window.SUIVI_FWD_DIFFERER = false; });
    const r = await page(cR, 'lot D tranches');
    await r.click('#vue-tableau button[data-vue="toutes"]'); await r.waitForTimeout(500);
    await r.evaluate(() => document.getElementById('section-plans').scrollIntoView()); await r.waitForTimeout(400);
    const tr1 = await r.evaluate(() => ({ lignes: document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length, suite: !!document.querySelector('#corps-tableau tr.ligne-suite'),
      fondu: document.getElementById('cadre-tableau').dataset.plusBas }));
    await r.evaluate(() => { const f = document.getElementById('defile'); f.scrollTop = f.scrollHeight; });
    await r.waitForTimeout(400);
    const tr2 = await r.evaluate(() => document.querySelectorAll('#corps-tableau tr:not(.ligne-suite)').length);
    verifier('le tableau se dessine par tranches (25 lignes de l’extract entier d’abord), la suite vient en descendant ; le bas du cadre fond tant qu’il reste des lignes (M4, D10)',
      tr1.lignes >= 20 && tr1.lignes <= 60 && tr1.suite && tr2 > tr1.lignes && tr1.fondu === 'true', JSON.stringify([tr1, tr2]));
    await cR.close();
  }

  // =================================================================
  section('Débrief 27 : Synthèse et Tendance (lot A)');
  {
    const couleursA = () => {
      window.__lumA = c => {
        const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
        return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
      };
      window.__contrasteA = (a, b) => { const x = window.__lumA(a), y = window.__lumA(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
      window.__fondA = e => { for (let x = e; x; x = x.parentElement) { const f = getComputedStyle(x).backgroundColor; if (f && !/rgba\(.*,\s*0\)$/.test(f) && f !== 'transparent') return f; } return 'rgb(255,255,255)'; };
    };
    const esp = 'const esp = t => String(t || "").replace(/[\\u00a0\\u202f]/g, " ").replace(/\\s+/g, " ").trim();';
    const cA = await contexte();
    const q = await page(cA, 'lot A');
    await q.evaluate(couleursA);

    // --- La Synthèse : un vrai titre, le verdict, « À vérifier ».
    /* Débrief 28 : le verdict de l'échéance (#verdict-synthese) et « À
       vérifier » (#signaux-synthese) sont retirés de la Synthèse (l'échéance
       se lit au graphique et à ses jalons) ; la puce de la Tendance et la
       phrase qui décrit le graphique disent toujours « il manquera N plans ». */
    const syn = await q.evaluate(new Function(esp + `
      const sec = document.getElementById('section-synthese');
      return { titre: document.getElementById('phrase').tagName, nom: sec.getAttribute('aria-label'), labelledby: sec.getAttribute('aria-labelledby'),
               verdict: !!document.getElementById('verdict-synthese') || !!sec.querySelector('.verdict-synthese'),
               signaux: !!document.getElementById('signaux-synthese') || !!sec.querySelector('.signaux-synthese, button[data-signal]'),
               texte: esp(sec.textContent),
               resume: esp(document.getElementById('resume-graphe').textContent),
               pastille: esp(document.getElementById('echeance-titre').textContent), retard: document.getElementById('echeance-titre').classList.contains('en-retard') };`));
    verifier('Synthèse : la phrase de tête est le titre (h2) de la région « Synthèse »',
      syn.titre === 'H2' && syn.nom === 'Synthèse' && !syn.labelledby, JSON.stringify(syn));
    verifier('Synthèse : plus de verdict de l’échéance sous la phrase (débrief 28) — ni « il faut N validés/sem. », ni « Détail »',
      !syn.verdict && !/il faut \d+ validés\/sem\.|→ donc au rythme actuel| Détail$/.test(syn.texte), JSON.stringify(syn));
    verifier('Tendance : la puce de l’échéance dit le verdict en mots (« en retard »), comme la phrase qui décrit le graphique (« il manquera N plans »)',
      syn.retard && /en retard$/.test(syn.pastille) && /il manquera \d+ plans\.$/.test(syn.resume), JSON.stringify([syn.pastille, syn.resume]));
    verifier('Synthèse : plus de ligne « À vérifier » ni de ses liens (reculs, validés absents de SEE) (débrief 28)',
      !syn.signaux && !/À vérifier/.test(syn.texte), JSON.stringify(syn));

    /* « Détail » ouvrait la fiche ; Échap la ferme et rend le focus au lien.
       Débrief 28 : sans le verdict, la fiche s'ouvre de la puce de la
       Tendance — au clavier ici, à la souris plus bas. */
    await q.focus('#echeance-titre'); await q.keyboard.press('Enter');
    await q.waitForFunction(() => !!document.getElementById('fiche-echeance'), null, { timeout: 3000 }).catch(() => {});
    const fiche = await q.evaluate(new Function(esp + `
      const f = document.getElementById('fiche-echeance');
      return f ? { verdict: esp(f.querySelector('.fiche-echeance-verdict').textContent), rythme: esp((f.querySelector('.fiche-echeance-rythme') || {}).textContent),
                   num: getComputedStyle(f.querySelector('.fiche-echeance-tete .num')).backgroundColor,
                   alerte: getComputedStyle(document.querySelector('.legende-jalon.critique .num') || document.body).backgroundColor } : null;`));
    verifier('la puce de l’échéance (au clavier, débrief 28) ouvre la fiche : « Au rythme tenu (N/sem.), il manquera N plans le …, soit N semaines après l’échéance », le rythme arrondi, le numéro en rouge — le même manque que la description du graphique',
      !!fiche && /^Au rythme tenu \([\d,]+\/sem\.\), il manquera \d+ plans le \S+ \d+ \S+ ; tout serait validé en S\d+ · \S+ \d{4}, soit \d+ semaines? après l’échéance/.test(fiche.verdict) &&
      /^Il faut \d+ plans validés par semaine/.test(fiche.rythme) && fiche.num === fiche.alerte && syn.resume.indexOf('il manquera ' + (fiche.verdict.match(/il manquera (\d+)/) || [])[1] + ' plans') !== -1,
      JSON.stringify([fiche, syn.resume]));
    await q.keyboard.press('Escape');
    await q.waitForFunction(() => !document.getElementById('fiche-echeance'), null, { timeout: 3000 }).catch(() => {});
    const apresEchap = await q.evaluate(() => ({ fiche: !!document.getElementById('fiche-echeance'), focus: document.activeElement.id || document.activeElement.tagName + '.' + document.activeElement.className }));
    verifier('Échap ferme la fiche de l’échéance et rend le focus à ce qui l’a ouverte (la puce de la Tendance, ouverte au clavier — débrief 28 : plus de « Détail » du verdict)',
      !apresEchap.fiche && apresEchap.focus === 'echeance-titre', JSON.stringify(apresEchap));
    await q.click('#echeance-titre'); await q.waitForTimeout(600);
    await q.keyboard.press('Escape'); await q.waitForTimeout(300);
    verifier('… et à la puce de la Tendance quand c’est elle qui l’a ouverte',
      await q.evaluate(() => !document.getElementById('fiche-echeance') && document.activeElement && document.activeElement.id === 'echeance-titre'));

    /* Les liens de « À vérifier ». Débrief 28 : la ligne est retirée ; la
       même case de la comparaison (« validés, absents de SEE ») et le filtre
       « reculs » du journal restent à portée dans leurs sections — on les
       pose de là, ils répondent comme avant. */
    await q.evaluate(() => window.scrollTo(0, 0));
    const caseSee = await q.evaluate(() => !!document.querySelector('#verdicts-rapprochement button[data-rapp="manque"]'));
    if (caseSee) {
      await q.click('#verdicts-rapprochement button[data-rapp="manque"]');
      await q.waitForFunction(() => (document.querySelector('#verdicts-rapprochement button[data-rapp="manque"]') || { getAttribute: () => '' }).getAttribute('aria-pressed') === 'true', null, { timeout: 3000 }).catch(() => {});
    }
    const lienSee = await q.evaluate(() => { const a = document.querySelector('#verdicts-rapprochement button[data-rapp="manque"]'); return a ? { rapp: a.dataset.rapp, presse: a.getAttribute('aria-pressed'), ouvert: a.getAttribute('aria-expanded'), signal: !!document.querySelector('button[data-signal]') } : null; });
    verifier('sans « À vérifier » (débrief 28), la case « validés, absents de SEE » se pose et se déplie de la comparaison elle-même ; aucun lien data-signal ne reste',
      !!lienSee && lienSee.rapp === 'manque' && lienSee.presse === 'true' && lienSee.ouvert === 'true' && !lienSee.signal, JSON.stringify(lienSee));
    await reinitialiser(q);
    const boutonReculs = await q.evaluate(() => !!document.querySelector('#filtre-journal button[data-journal="reculs"]'));
    if (boutonReculs) {
      await q.click('#filtre-journal button[data-journal="reculs"]');
      await q.waitForFunction(() => window.__vueValeurs().journal === 'reculs', null, { timeout: 3000 }).catch(() => {});
      const lienRecul = await q.evaluate(() => ({ filtre: window.__vueValeurs().journal, signal: !!document.querySelector('#signaux-synthese, button[data-signal="reculs"]') }));
      verifier('sans « À vérifier » (débrief 28), le journal se filtre sur les reculs de sa propre rangée',
        lienRecul.filtre === 'reculs' && !lienRecul.signal, JSON.stringify(lienRecul));
      await q.click('#filtre-journal button[data-journal=""]'); await q.waitForTimeout(300);
    }

    // B23 : une tuile pressée garde la répartition.
    await q.evaluate(() => window.scrollTo(0, 0));
    const avantTuile = await q.evaluate(() => ({ n: [...document.querySelectorAll('#etats .etat-n')].map(e => e.textContent), segs: document.querySelectorAll('#barre span[data-cle]').length }));
    const cleT = await q.evaluate(() => [...document.querySelectorAll('#etats .etat-btn')].find(b => b.dataset.famille === 'encours').dataset.etat);
    await q.focus('#etats .etat-btn[data-etat="' + cleT + '"]'); await q.keyboard.press('Enter'); await q.waitForTimeout(500);
    const tuile = await q.evaluate(new Function('cle', esp + `
      const b = document.querySelector('#etats .etat-btn[data-etat="' + cle + '"]');
      return { phrase: esp(document.getElementById('phrase').textContent), n: [...document.querySelectorAll('#etats .etat-n')].map(e => e.textContent),
               segs: document.querySelectorAll('#barre span[data-cle]').length,
               pales: [...document.querySelectorAll('#barre span[data-cle]')].filter(s => s.dataset.cle !== cle).map(s => getComputedStyle(s).opacity),
               choisi: getComputedStyle(document.querySelector('#barre span[data-cle="' + cle + '"]')).opacity,
               focus: document.activeElement === b, encreAutre: (() => { const o = [...document.querySelectorAll('#etats .etat-btn')].find(x => x !== b); const n = o.querySelector('.etat-n'); return window.__contrasteA(getComputedStyle(n).color, window.__fondA(n)); })(),
               lignes: document.querySelectorAll('#corps-tableau tr').length };`), cleT);
    verifier('B23 : une tuile pressée garde la répartition — mêmes tuiles et mêmes nombres, mêmes segments, les autres pâlis à 35 %, le texte des autres tuiles lisible (4,5:1)',
      JSON.stringify(tuile.n) === JSON.stringify(avantTuile.n) && tuile.segs === avantTuile.segs && tuile.pales.length && tuile.pales.every(o => o === '0.35') && tuile.choisi === '1' && tuile.encreAutre >= 4.5,
      JSON.stringify({ avantTuile, tuile }));
    verifier('B23 : la phrase dit la part choisie (« N plans en X · P % du périmètre »), le tableau reste filtré, le focus reste sur la tuile',
      /^\d+ plans? en .+ · \d+(,\d)? % du périmètre$/.test(tuile.phrase) && tuile.lignes < TOTAL && tuile.focus, JSON.stringify(tuile));
    await q.keyboard.press('Enter'); await q.waitForTimeout(400);

    // La Tendance : un seul « aujourd'hui », les jalons calmes, la droite requis.
    const g = await q.evaluate(() => {
      const svg = document.querySelector('#zone-graphe svg');
      const op = l => getComputedStyle(l).opacity;
      const jal = [...svg.querySelectorAll('.jalon')].map(j => ({ prochain: j.classList.contains('prochain'), trait: op(j.querySelector('.jalon-trait')), coche: !!j.querySelector('.jalon-coche') }));
      const mots = [...svg.querySelectorAll('text')].map(t => t.textContent);
      const rq = svg.querySelector('.droite-requis'), motRq = svg.querySelector('.requis-mot');
      let coupe = null;
      if (rq && motRq) {
        const b = motRq.getBBox(), L = rq.getTotalLength(); coupe = false;
        for (let k = 0; k <= 60; k++) { const p = rq.getPointAtLength(L * k / 60); if (p.x > b.x && p.x < b.x + b.width && p.y > b.y && p.y < b.y + b.height) coupe = true; }
      }
      const semaines = [...svg.querySelectorAll('text.grad')].filter(t => /^S\d+$/.test(t.textContent)).map(t => t.getBBox());
      const barres = [...svg.querySelectorAll('.barre-semaine')].map(b => b.getBBox());
      const proj = svg.querySelector('path[stroke-dasharray="5 4"]');
      const fondSvg = getComputedStyle(document.getElementById('section-tendance')).backgroundColor;
      const barre = svg.querySelector('.barre-semaine');
      return { aujourdhui: mots.filter(m => m === 'aujourd’hui').length, dernier: mots.some(m => /dernier relevé/.test(m)), auj: svg.querySelectorAll('.repere-auj').length,
               jal, dash: rq ? rq.getAttribute('stroke-dasharray') : null, motRq: motRq ? motRq.textContent : null, coupe,
               basSemaines: Math.max.apply(null, semaines.map(b => b.y + b.height)), hautBarres: barres.length ? Math.min.apply(null, barres.map(b => b.y)) : null,
               largeurBarre: barres.length ? Math.max.apply(null, barres.map(b => b.width)) : null, nom: mots.some(m => /^validés \/ semaine$/.test(m)),
               projOpacite: proj ? proj.getAttribute('opacity') : 'absente',
               barreContraste: barre ? window.__contrasteA(getComputedStyle(barre).fill, fondSvg) : 0,
               toucher: getComputedStyle(document.getElementById('cadre-graphe')).touchAction,
               decrit: svg.getAttribute('aria-describedby'), resume: document.getElementById('resume-graphe').textContent.replace(/[\u00a0\u202f]/g, ' ') };
    });
    verifier('B3 : un seul repère « aujourd’hui », plus de trait « dernier relevé »', g.aujourdhui === 1 && g.auj === 1 && !g.dernier, JSON.stringify({ a: g.aujourdhui, d: g.dernier }));
    verifier('B3 : seule la prochaine échéance a son trait pleine hauteur ; les autres jalons, une coche (leur trait est caché)',
      g.jal.filter(j => j.prochain).length >= 1 && g.jal.every(j => j.prochain ? +j.trait > 0 && !j.coche : j.trait === '0' && j.coche), JSON.stringify(g.jal));
    verifier('B3, X-A8 : la droite « requis » a son trait-point (8 3 2 3) et son nom « requis N/sem. » écrit contre elle, jamais en travers',
      g.dash === '8 3 2 3' && /^requis \d+(,\d)?\/sem\.$/.test(g.motRq) && g.coupe === false, JSON.stringify({ dash: g.dash, mot: g.motRq, coupe: g.coupe }));
    verifier('B3 : les barres des validés par semaine ont leur bande sous l’axe (« validés / semaine »), 10 px de large au plus, 3:1 sur la surface',
      g.hautBarres !== null && g.hautBarres > g.basSemaines && g.largeurBarre <= 10.01 && g.nom && g.barreContraste >= 3, JSON.stringify(g));
    verifier('X-A12 : la projection au rythme tenu est à pleine opacité ; M2 : le cadre laisse le défilement vertical au navigateur (pan-y)',
      g.projOpacite === null && g.toucher === 'pan-y', JSON.stringify({ o: g.projOpacite, t: g.toucher }));
    verifier('X-A7 : le dessin est décrit par une phrase (aria-describedby) qui dit le compte, le rythme et l’échéance',
      g.decrit === 'resume-graphe' && /^\d+ plans validés sur \d+, en S\d+ · .* Rythme tenu : [\d,]+ par semaine.* il manquera \d+ plans\.$/.test(g.resume), g.resume);
    // Survol d'un jalon dans la légende : son trait paraît, léger.
    const idxAutre = await q.evaluate(() => { const j = [...document.querySelectorAll('svg.graphe .jalon')].find(x => !x.classList.contains('prochain')); return j ? j.dataset.jalon : null; });
    if (idxAutre !== null) {
      await q.hover('.legende-jalon[data-jalon="' + idxAutre + '"]'); await q.waitForTimeout(250);
      const op = await q.evaluate(i => getComputedStyle(document.querySelector('svg.graphe .jalon[data-jalon="' + i + '"] .jalon-trait')).opacity, idxAutre);
      verifier('B3 : survoler un jalon dans la légende fait paraître son trait, léger (35 %)', op === '0.35', op);
      await q.mouse.move(5, 5);
    }

    // La molette : la page défile ; Ctrl + molette zoome.
    await q.evaluate(() => document.getElementById('section-tendance').scrollIntoView());
    await q.waitForTimeout(200);
    const centre = await q.evaluate(() => { const r = document.querySelector('#zone-graphe svg').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
    const avantMol = await q.evaluate(() => ({ y: scrollY, n: document.querySelectorAll('svg.graphe .zone-clic').length }));
    await q.mouse.move(centre.x, centre.y);
    await q.mouse.wheel(0, 200); await q.waitForTimeout(400);
    const apresMol = await q.evaluate(() => ({ y: scrollY, n: document.querySelectorAll('svg.graphe .zone-clic').length, indice: !document.getElementById('indice-zoom').hidden && /molette pour zoomer/.test(document.getElementById('indice-zoom').textContent) }));
    verifier('P-F1, X-A9 : la molette seule sur le graphique fait défiler la page, sans zoomer ; un mot dit « Ctrl + molette pour zoomer »',
      apresMol.y > avantMol.y && apresMol.n === avantMol.n && apresMol.indice, JSON.stringify({ avantMol, apresMol }));
    await q.evaluate(() => document.getElementById('section-tendance').scrollIntoView());
    await q.waitForTimeout(200);
    const centre2 = await q.evaluate(() => { const r = document.querySelector('#zone-graphe svg').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
    await q.mouse.move(centre2.x, centre2.y);
    const yZoom = await q.evaluate(() => scrollY);
    await q.keyboard.down('Control'); await q.mouse.wheel(0, -300); await q.keyboard.up('Control'); await q.waitForTimeout(300);
    const zoom = await q.evaluate(() => ({ y: scrollY, n: document.querySelectorAll('svg.graphe .zone-clic').length, revenir: !document.getElementById('revenir-cadrage').hidden, mot: document.getElementById('revenir-cadrage').textContent }));
    verifier('Ctrl + molette zoome le graphique (la page ne bouge pas), et « ↺ Revenir aux échéances » paraît',
      zoom.n < avantMol.n && zoom.y === yZoom && zoom.revenir && /Revenir aux échéances/.test(zoom.mot), JSON.stringify(zoom));
    await q.click('#revenir-cadrage'); await q.waitForTimeout(300);
    const retour = await q.evaluate(() => ({ n: document.querySelectorAll('svg.graphe .zone-clic').length, cache: document.getElementById('revenir-cadrage').hidden, presse: (document.querySelector('.commandes-graphe button[aria-pressed="true"]') || {}).textContent }));
    verifier('« Revenir aux échéances » ramène le cadrage d’ouverture et s’efface', retour.n === avantMol.n && retour.cache && retour.presse === 'Échéances', JSON.stringify(retour));

    // La bulle : Échap la ferme ; au clavier, les flèches parcourent les relevés et la page les dit.
    const zc = await q.evaluate(() => { const z = [...document.querySelectorAll('svg.graphe .zone-clic')].find(r => /validés$/.test(r.getAttribute('aria-label'))); const r = z.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
    await q.mouse.move(zc.x, zc.y); await q.waitForTimeout(200);
    const survol = await q.evaluate(() => document.getElementById('bulle').dataset.visible);
    await q.keyboard.press('Escape'); await q.waitForTimeout(150);
    const echapSurvol = await q.evaluate(() => document.getElementById('bulle').dataset.visible);
    verifier('X-A7 : Échap ferme la bulle du survol', survol === 'true' && echapSurvol === 'false', survol + '/' + echapSurvol);
    await q.mouse.move(5, 5);
    await q.focus('#cadre-graphe'); await q.keyboard.press('ArrowLeft'); await q.keyboard.press('ArrowLeft');
    await q.waitForFunction(() => /Relevé de/.test((document.getElementById('annonce') || {}).textContent || ''), null, { timeout: 3000 }).catch(() => {});
    const clavier = await q.evaluate(() => ({ bulle: document.getElementById('bulle').dataset.visible, texte: document.getElementById('bulle').textContent.slice(0, 40),
      annonce: document.getElementById('annonce').textContent, marquee: document.querySelectorAll('svg.graphe .zone-clic.marquee').length,
      cachee: document.getElementById('bulle').getAttribute('aria-hidden') }));
    verifier('X-A7 : au clavier, le graphique prend le focus, les flèches passent d’un relevé à l’autre, la bulle s’ouvre et la page dit la semaine',
      clavier.bulle === 'true' && /^Relevé de S\d+/.test(clavier.texte) && /^Relevé de S\d+ · .* ; validés : \d+ \/ \d+/.test(clavier.annonce) && clavier.marquee === 1 && clavier.cachee === 'true',
      JSON.stringify(clavier));
    await q.keyboard.press('Escape'); await q.waitForTimeout(150);
    verifier('… et Échap la referme', await q.evaluate(() => document.getElementById('bulle').dataset.visible === 'false'));

    // La légende : des boutons qui déplient leur phrase.
    await q.click('#legende button[data-legende="rythme"]'); await q.waitForTimeout(200);
    const leg = await q.evaluate(() => ({ exp: document.querySelector('#legende button[data-legende="rythme"]').getAttribute('aria-expanded'),
      detail: document.getElementById('legende-detail').textContent, titre: document.querySelector('#legende button[data-legende="rythme"] span[title]').getAttribute('title'),
      focus: document.activeElement.dataset.legende }));
    verifier('M3, D9 : un mot de la légende est un bouton qui déplie sa phrase (au doigt, au clavier) ; le focus reste sur lui',
      leg.exp === 'true' && leg.detail === leg.titre && /par semaine/.test(leg.detail) && leg.focus === 'rythme', JSON.stringify(leg));
    await q.click('#legende button[data-legende="rythme"]'); await q.waitForTimeout(200);
    verifier('… un second appui la replie', await q.evaluate(() => document.getElementById('legende-detail').hidden && document.getElementById('legende-detail').textContent === ''));

    // « Voir les chiffres ».
    await q.click('#donnees-graphe summary'); await q.waitForTimeout(200);
    const table = await q.evaluate(() => ({ lignes: document.querySelectorAll('#donnees-graphe-corps tbody tr').length,
      tete: [...document.querySelectorAll('#donnees-graphe-corps thead th')].map(t => t.textContent).join('|'),
      points: [...document.querySelectorAll('svg.graphe .zone-clic')].length, releves: (document.getElementById('note-graphe').textContent.match(/^(\d+) relevés/) || [])[1] }));
    verifier('X-A7 : « Voir les chiffres » déplie le tableau des relevés — semaine, validés, plans suivis, gain net', table.tete === 'Semaine|Validés|Plans suivis|Gain net' && table.lignes === +table.releves, JSON.stringify(table));
    /* Débrief 28 : la note « N relevés, de … à … » sous le graphique est
       réservée aux lecteurs d'écran (classe masque) : elle reste dans la
       page, à jour, mais ne se voit plus. */
    const note28 = await q.evaluate(() => { const n = document.getElementById('note-graphe'), b = n.getBoundingClientRect();
      return { masque: n.classList.contains('masque'), l: b.width, h: b.height, cache: n.hidden || getComputedStyle(n).display === 'none', texte: n.textContent.replace(/[  ]/g, ' ') }; });
    verifier('la note « N relevés, de … à … » du graphique est masquée à l’œil (classe masque, 1 px) mais lue aux lecteurs d’écran, à jour (débrief 28)',
      note28.masque && note28.l <= 1 && note28.h <= 1 && !note28.cache && /^\d+ relevés, de S\d+ · .+ à S\d+ · .+$/.test(note28.texte) && +note28.texte.match(/^\d+/)[0] === +table.releves,
      JSON.stringify(note28));
    await q.click('#donnees-graphe summary');

    // Les pilules : « Courbe : », un second clic revient aux validés ; une seule valeur : le cadre s'arrête à aujourd'hui + 4 semaines.
    const pil = await q.evaluate(() => ({ mot: (document.querySelector('#filtre-valeur-graphe .mot-rangee') || {}).textContent }));
    await q.click('#filtre-valeur-graphe button[data-valeur-graphe="encours"]'); await q.waitForTimeout(300);
    const val = await q.evaluate(() => {
      const zs = [...document.querySelectorAll('svg.graphe .zone-clic')], t = document.querySelector('svg.graphe .trait-auj');
      const xa = t ? +t.getAttribute('x1') : null;
      const iAuj = zs.findIndex(z => xa >= +z.getAttribute('x') && xa < +z.getAttribute('x') + +z.getAttribute('width'));
      return { graphe: window.__vueValeurs().graphe, apres: zs.length - 1 - iAuj };
    });
    await q.click('#filtre-valeur-graphe button[data-valeur-graphe="encours"]'); await q.waitForTimeout(300);
    const val2 = await q.evaluate(() => ({ graphe: window.__vueValeurs().graphe, focus: document.activeElement.dataset.valeurGraphe }));
    verifier('P-F19 : la rangée se nomme « Courbe : » ; un second clic sur la pilule pressée revient à la courbe des validés, le focus reste dessus',
      /^Courbe\s:$/.test((pil.mot || '').replace(/ /g, ' ')) && val.graphe === 'encours' && val2.graphe === '' && val2.focus === 'encours', JSON.stringify({ pil, val, val2 }));
    verifier('B3 : la courbe d’une seule valeur s’arrête quatre semaines après aujourd’hui (le cadre des échéances laissait 70 % de vide)', val.apres === 4, JSON.stringify(val));

    // Les jalons en retrait : lisibles (4,5:1), sans opacité ; l'échéance manquée dit « en retard ».
    const jl = await q.evaluate(() => {
      const r = [...document.querySelectorAll('.legende-jalon.hors-perimetre .quand, .legende-jalon.hors-fenetre .quand')].map(e => ({ c: window.__contrasteA(getComputedStyle(e).color, window.__fondA(e)), o: getComputedStyle(e).opacity, oj: getComputedStyle(e.closest('.legende-jalon')).opacity }));
      return { r, retard: (document.querySelector('.legende-jalon.critique .quand') || {}).textContent };
    });
    verifier('X-A8, contraste : les dates des jalons en retrait tiennent 4,5:1 sans opacité ; l’échéance manquée le dit en mots (« en retard »)',
      jl.r.length > 0 && jl.r.every(x => x.c >= 4.5 && x.o === '1' && x.oj === '1') && / · en retard$/.test(jl.retard || ''), JSON.stringify(jl));

    // Concept harnais : « plans traités ».
    const concept = await q.evaluate(() => { const b = document.querySelector('#choix-indicateur button[data-indicateur="concept"]'); if (!b || !b.getClientRects().length) return null; b.click(); const t = document.getElementById('phrase').textContent; document.querySelector('#choix-indicateur button[data-indicateur="def"]').click(); return t; });
    if (concept !== null) verifier('P-F14 : en concept harnais, la phrase dit « plans traités »', /plans traités/.test(concept), concept);

    // Un seul relevé : un état calme à la place d'une grille vide.
    const vide = await q.evaluate(() => {
      const s = window.__jeuDExemple('HDK'); s.releves = s.releves.slice(-1); window.__chargerSource(s);
      const r = { bloc: (document.querySelector('#zone-graphe .etat-vide-phrase') || {}).textContent, svg: !!document.querySelector('#zone-graphe svg'),
        pilules: !!document.getElementById('filtre-valeur-graphe').offsetParent, periode: !!document.querySelector('.commandes-graphe').offsetParent, legende: !!document.getElementById('legende').offsetParent };
      window.__chargerSource(window.__jeuDExemple('HDK'));
      return r;
    });
    verifier('D8, B7 : un seul relevé — « La courbe commence au deuxième relevé », sans grille, ni pilules, ni période, ni légende',
      vide.bloc === 'La courbe commence au deuxième relevé' && !vide.svg && !vide.pilules && !vide.periode && !vide.legende, JSON.stringify(vide));
    await cA.close();

    /* Sombre : le verdict et la puce lisibles. Débrief 28 : le verdict de la
       Synthèse est retiré — restent la puce, « requis » et les barres. */
    const cS = await contexte({ colorScheme: 'dark' });
    const qs = await page(cS, 'lot A sombre');
    await qs.evaluate(couleursA);
    const sombre = await qs.evaluate(() => {
      const m = document.querySelector('#echeance-titre .verdict-mot'), r = document.querySelector('svg.graphe .requis-mot'), b = document.querySelector('svg.graphe .barre-semaine');
      const fondG = getComputedStyle(document.getElementById('section-tendance')).backgroundColor;
      return { verdict: !!document.getElementById('verdict-synthese'), mot: window.__contrasteA(getComputedStyle(m).color, window.__fondA(m)),
               requis: window.__contrasteA(getComputedStyle(r).fill, fondG), barre: window.__contrasteA(getComputedStyle(b).fill, fondG) };
    });
    verifier('sombre : le mot de la puce et « requis N/sem. » tiennent 4,5:1, les barres par semaine 3:1 (plus de verdict dans la Synthèse, débrief 28)',
      !sombre.verdict && sombre.mot >= 4.5 && sombre.requis >= 4.5 && sombre.barre >= 3, JSON.stringify(sombre));
    await cS.close();

    // Au doigt : un toucher ouvre la bulle et la garde, en bas de l'écran ; un toucher ailleurs la ferme.
    const cT = await contexte({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const qt = await page(cT, 'lot A doigt');
    await qt.evaluate(() => document.getElementById('cadre-graphe').scrollIntoView({ block: 'center' }));
    await qt.waitForTimeout(300);
    const zt = await qt.evaluate(() => { const z = [...document.querySelectorAll('svg.graphe .zone-clic')].find(r => /validés$/.test(r.getAttribute('aria-label'))); const r = z.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height * 0.6 }; });
    await qt.touchscreen.tap(zt.x, zt.y); await qt.waitForTimeout(400);
    const tap = await qt.evaluate(() => { const b = document.getElementById('bulle'), r = b.getBoundingClientRect(); return { v: b.dataset.visible, cls: b.className, bas: Math.round(innerHeight - r.bottom), texte: b.textContent.slice(0, 30) }; });
    verifier('M3, D9 : au doigt, un toucher sur la courbe ouvre la bulle de la semaine et la garde, posée en bas de l’écran',
      tap.v === 'true' && /tenue/.test(tap.cls) && /en-bas/.test(tap.cls) && tap.bas >= 8 && tap.bas <= 16 && /^Relevé de S\d+/.test(tap.texte), JSON.stringify(tap));
    await qt.touchscreen.tap(20, 60); await qt.waitForTimeout(300);
    verifier('… un toucher ailleurs la ferme', await qt.evaluate(() => document.getElementById('bulle').dataset.visible === 'false'));
    await cT.close();
  }

  /* Débrief 27, lot C — « Par ATA » : la liste prend sa hauteur dans la
     page (plus de cadre qui défile, plus de ligne coupée, la molette
     descend la page), une ligne se déplie sans filtrer la page (le filtre
     est un bouton nommé), les en-têtes disent qu'ils trient (↕, ↑/↓,
     aria-sort), le rythme requis à l'encre avec sa jauge, seule la part des
     validés écrite dans la barre, des lignes qui se disent en une phrase. */
  section('Débrief 27 : Par ATA (lot C)');
  {
    const cC = await contexte({ viewport: { width: 1440, height: 900 } });
    const c = await page(cC, 'lot C');
    await c.selectOption('#dim-critique', 'ata'); await c.waitForTimeout(400);
    const rgb = col => col.match(/[\d.]+/g).map(Number).slice(0, 3);
    const lumC = col => rgb(col).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }).reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
    const contrasteC = (a, b) => { const x = lumC(a), y = lumC(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

    // 1. Structure : une table pour les lecteurs d'écran, aria-sort sur l'en-tête trié.
    const struct = await c.evaluate(() => {
      const t = document.querySelector('#zone-critique [role="table"]');
      const ent = [...document.querySelectorAll('#zone-critique .critique-tete > [role="columnheader"]')];
      const rangees = [...document.querySelectorAll('#zone-critique .critique-rangee[role="row"]')];
      return { table: !!t && !!t.getAttribute('aria-labelledby'), tete: document.querySelector('.critique-tete').getAttribute('role'), entetes: ent.length,
        tries: ent.filter(e => e.hasAttribute('aria-sort')).map(e => e.querySelector('button').dataset.trig + ':' + e.getAttribute('aria-sort')),
        repos: ent.filter(e => !e.hasAttribute('aria-sort')).every(e => !!e.querySelector('.tri-groupe .fleche.repos')),
        actif: ent.filter(e => e.hasAttribute('aria-sort')).every(e => !!e.querySelector('.tri-groupe .fleche:not(.repos)')),
        cellules: rangees.length > 0 && rangees.every(r => { const c = r.querySelector('[role="cell"]'); return c && c.getAttribute('aria-colspan') === '5' && c.querySelector('.critique-ligne'); }),
        hauteur: Math.round(document.querySelector('.critique-tete .tri-groupe').getBoundingClientRect().height) };
    });
    verifier('C — la liste est une table (en-tête de colonnes, une rangée par groupe), seule la colonne triée porte aria-sort, les autres une double flèche pâle',
      struct.table && struct.tete === 'row' && struct.entetes === 5 && struct.tries.join() === 'nom:ascending' && struct.repos && struct.actif && struct.cellules, JSON.stringify(struct));
    verifier('C — un en-tête qu’on clique fait 28 px de haut (D3)', struct.hauteur >= 28, String(struct.hauteur));
    await c.click('#zone-critique button[data-trig="fin"]'); await c.waitForTimeout(300);
    const tri = await c.evaluate(() => ({ tries: [...document.querySelectorAll('#zone-critique [role="columnheader"][aria-sort]')].map(e => e.querySelector('button').dataset.trig + ':' + e.getAttribute('aria-sort')),
      focus: document.activeElement && document.activeElement.dataset.trig }));
    /* annoncer attend 400 ms après le dernier appel : on attend la phrase. */
    const attendreAnnonce = motif => c.waitForFunction(m => new RegExp(m).test((document.getElementById('annonce') || {}).textContent || ''), motif, { timeout: 5000 }).catch(() => {});
    await attendreAnnonce('^Liste triée');
    const annonceTri = await c.evaluate(() => document.getElementById('annonce').textContent);
    verifier('C — trier par fin estimée : aria-sort passe à cette colonne, le focus y reste, et le tri est annoncé',
      tri.tries.join() === 'fin:descending' && tri.focus === 'fin' && /^Liste triée par fin estimée, ordre décroissant\./.test(annonceTri), JSON.stringify([tri, annonceTri]));
    await c.click('#zone-critique button[data-trig="fin"]'); await c.waitForTimeout(200);
    await c.click('#zone-critique button[data-trig="fin"]'); await c.waitForTimeout(200);

    // 2. Les « ? » : 24 px, nommés.
    const aides = await c.evaluate(() => [...document.querySelectorAll('#zone-critique button.aide')].map(b => {
      const r = b.getBoundingClientRect(); return { l: Math.round(r.width), h: Math.round(r.height), nom: b.getAttribute('aria-label') }; }));
    verifier('C — chaque « ? » est une cible de 24 px et dit ce qu’il explique (« Aide : comment la fin estimée est calculée »)',
      aides.length === 2 && aides.every(a => a.l >= 24 && a.h >= 24) && aides[0].nom === 'Aide : comment la fin estimée est calculée' &&
      /^Aide : comment le rythme (requis|tenu) est calculé$/.test(aides[1].nom), JSON.stringify(aides));

    // 3. Les lignes se disent en une phrase ; les cellules visibles sont cachées aux lecteurs d'écran.
    const phrases = await c.evaluate(() => [...document.querySelectorAll('#zone-critique .critique-ligne')].map(l => ({
      g: l.dataset.groupe, phrase: (l.querySelector(':scope > .masque') || { textContent: '' }).textContent,
      caches: [...l.children].filter(x => !x.classList.contains('masque')).every(x => x.getAttribute('aria-hidden') === 'true'),
      total: Number(l.querySelector('.critique-total').textContent), titre: l.hasAttribute('title') })));
    verifier('C — chaque ligne se dit « ATA 21, 65 plans : … VALIDATED (… %) … Fin estimée : … Rythme … » ; ses cellules visibles sont cachées aux lecteurs d’écran, plus d’infobulle',
      phrases.length >= 5 && phrases.every(x => x.phrase.indexOf('ATA ' + x.g + ', ' + x.total + ' plan') === 0 && /Fin estimée : /.test(x.phrase) && /Rythme (requis|tenu) : /.test(x.phrase) && x.caches && !x.titre),
      JSON.stringify(phrases.slice(0, 2)));

    // 4. Rythme requis à l'encre, 13/500, avec sa jauge ; plus de rouge dans le texte.
    const rythme = await c.evaluate(() => {
      const r = [...document.querySelectorAll('#zone-critique .critique-effort .requis')];
      const j = [...document.querySelectorAll('#zone-critique .critique-effort .jauge-rythme')];
      const encre = getComputedStyle(document.querySelector('.critique-nom')).color;
      return { n: r.length, jauges: j.length, couleurs: [...new Set(r.map(e => getComputedStyle(e).color))], encre, poids: [...new Set(r.map(e => getComputedStyle(e).fontWeight))],
        taille: [...new Set(r.map(e => getComputedStyle(e).fontSize))], chiffres: [...new Set(r.map(e => getComputedStyle(e).fontVariantNumeric))],
        dims: j.map(e => Math.round(e.getBoundingClientRect().width) + '×' + Math.round(e.getBoundingClientRect().height)),
        parts: [...document.querySelectorAll('#zone-critique .critique-effort')].filter(e => e.querySelector('.requis')).map(e => {
          const t = e.querySelector('.v').textContent.replace(/[\s  ]/g, '');
          const req = Number((t.match(/^([\d,]+)\/sem/) || [])[1].replace(',', '.')), tenu = Number(((t.match(/tenu([\d,]+)\//) || [])[1] || '0').replace(',', '.'));
          const jg = e.querySelector('.jauge-rythme'), w = parseFloat(jg.querySelector('i').style.width);
          return { req, tenu, w, suffit: jg.classList.contains('suffit') };
        }),
        fond: getComputedStyle(j[0]).backgroundColor, remplissage: getComputedStyle(j[0].querySelector('i')).backgroundColor,
        surface: getComputedStyle(document.getElementById('section-repartition')).backgroundColor };
    });
    verifier('C — « Rythme requis » à l’encre, 13 px, poids 500, chiffres alignés — plus de rouge sur toute la colonne (B13)',
      rythme.n >= 5 && rythme.couleurs.length === 1 && rythme.couleurs[0] === rythme.encre && rythme.poids.join() === '500' && rythme.taille.join() === '13px' && /tabular-nums/.test(rythme.chiffres.join()), JSON.stringify(rythme).slice(0, 400));
    verifier('C — sous lui, une jauge de 40 × 4 px : la part du rythme requis que tient le rythme tenu (pleine et verte quand il suffit)',
      rythme.jauges === rythme.n && rythme.dims.every(d => d === '40×4') &&
      /* Les rythmes écrits sont arrondis au dixième : la jauge, calculée sur
         les vrais, peut s'en écarter d'autant. */
      rythme.parts.every(x => x.suffit ? x.w === 100 : Math.abs(x.w - Math.min(100, 100 * x.tenu / x.req)) <= 100 * (0.05 / x.req + 0.05 * x.tenu / (x.req * (x.req - 0.05))) + 0.5),
      JSON.stringify(rythme.parts.filter(x => !(x.suffit ? x.w === 100 : Math.abs(x.w - Math.min(100, 100 * x.tenu / x.req)) <= 100 * (0.05 / x.req + 0.05 * x.tenu / (x.req * (x.req - 0.05))) + 0.5)).slice(0, 4)));
    verifier('C — la jauge se lit : son remplissage tient 3:1 sur sa piste', contrasteC(rythme.remplissage, rythme.fond) >= 3, contrasteC(rythme.remplissage, rythme.fond).toFixed(2));

    // 5. Dans la barre, seule la part des validés est écrite (B25).
    const barres = await c.evaluate(() => {
      const fam = {}; window.__valeurs().forEach(v => { fam[v.cle] = v.famille; });
      const ecrits = [...document.querySelectorAll('#zone-critique .critique-barre span[data-cle]')].filter(s => s.textContent.trim());
      return { ecrits: ecrits.length, familles: [...new Set(ecrits.map(s => fam[s.dataset.cle]))], titres: [...document.querySelectorAll('#zone-critique .critique-barre span[data-cle]')].every(s => !!s.title) };
    });
    verifier('C — dans les barres, seule la part des validés s’écrit ; chaque segment garde son infobulle',
      barres.ecrits > 0 && barres.familles.join() === 'termine' && barres.titres, JSON.stringify(barres));
    /* À 768 px, la barre n'a plus que ~115 px : « 12 % » se coupait en « 2% ». */
    await redimensionner(c, 768, 900);
    const coupees = await c.evaluate(() => [...document.querySelectorAll('#zone-critique .critique-barre span[data-cle]')].filter(s => {
      if (!s.textContent || getComputedStyle(s).fontSize === '0px') return false;
      const r = document.createRange(); r.selectNodeContents(s); return r.getBoundingClientRect().width > s.clientWidth + 0.5; }).map(s => s.textContent));
    verifier('C — à 768 px, aucune part n’est coupée dans une barre trop étroite : elle s’écrit en entier, ou pas du tout', coupees.length === 0, JSON.stringify(coupees));
    await redimensionner(c, 1440, 900);

    // 6. La molette au-dessus de la liste descend la page (P-F1).
    await c.evaluate(() => document.getElementById('section-repartition').scrollIntoView());
    await c.waitForTimeout(200);
    const yAvant = await c.evaluate(() => scrollY);
    const boite = await c.locator('#zone-critique .critique-ligne').nth(2).boundingBox();
    await c.mouse.move(boite.x + 300, boite.y + 10);
    for (let k = 0; k < 4; k++) { await c.mouse.wheel(0, 100); await c.waitForTimeout(60); }
    await c.waitForTimeout(300);
    const yApres = await c.evaluate(() => scrollY);
    verifier('C — la molette au-dessus de la liste fait descendre la page (plus de cadre qui la retient)', yApres - yAvant >= 300, yAvant + ' → ' + yApres);

    // 7. L'aide au-dessus de l'en-tête ; sa croix et Échap la referment, le focus revient au « ? ».
    await c.evaluate(() => document.getElementById('section-repartition').scrollIntoView());
    await c.click('#zone-critique button[data-aide="fin"]'); await c.waitForTimeout(300);
    const aideC = await c.evaluate(() => {
      const pa = document.getElementById('panneau-fin'), t = document.querySelector('#zone-critique .critique-table');
      return { ouvert: !!pa, avant: !!pa && !!(pa.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING) && !t.contains(pa),
               croix: !!pa && pa.querySelector('button[data-fermer-aide]').getAttribute('aria-label') };
    });
    await c.click('#panneau-fin button[data-fermer-aide]'); await c.waitForTimeout(300);
    const croixC = await c.evaluate(() => ({ ferme: !document.getElementById('panneau-fin'), focus: document.activeElement && document.activeElement.getAttribute('data-aide') }));
    await c.focus('#zone-critique button[data-aide="fin"]'); await c.keyboard.press('Enter'); await c.waitForTimeout(300);
    await c.keyboard.press('Escape'); await c.waitForTimeout(300);
    const echapC = await c.evaluate(() => ({ ferme: !document.getElementById('panneau-fin'), focus: document.activeElement && document.activeElement.getAttribute('data-aide'),
      etendu: document.querySelector('#zone-critique button[data-aide]').getAttribute('aria-expanded') }));
    verifier('C — « ? » ouvre l’explication au-dessus de l’en-tête de la liste ; sa croix « Fermer l’explication » et Échap la referment, le focus revient au « ? »',
      aideC.ouvert && aideC.avant && aideC.croix === 'Fermer l’explication' && croixC.ferme && croixC.focus === 'fin' && echapC.ferme && echapC.focus === 'fin' && echapC.etendu === 'false',
      JSON.stringify([aideC, croixC, echapC]));

    // 8. Déplier n'annonce que le dépliage ; le filtre de la page s'annonce.
    await c.click('#zone-critique .critique-ligne >> nth=1'); await c.waitForTimeout(300);
    await attendreAnnonce('déplié');
    const annonceDeplie = await c.evaluate(() => document.getElementById('annonce').textContent);
    const g1 = await c.evaluate(() => document.querySelectorAll('#zone-critique .critique-ligne')[1].dataset.groupe);
    const controle = await c.evaluate(() => { const l = document.querySelectorAll('#zone-critique .critique-ligne')[1]; const id = l.getAttribute('aria-controls'); return !!id && !!document.getElementById(id) && document.getElementById(id).classList.contains('groupe-refs'); });
    await c.click('#filtrer-groupe-page'); await c.waitForTimeout(300);
    await attendreAnnonce('^Page filtrée');
    const annonceFiltre = await c.evaluate(() => document.getElementById('annonce').textContent);
    verifier('C — déplier une ligne l’annonce (« ATA … déplié : N plans. »), sa ligne pointe vers sa liste (aria-controls) ; filtrer la page s’annonce aussi',
      new RegExp('^ATA ' + g1 + ' déplié : \\d+ plans?\\.$').test(annonceDeplie) && controle && new RegExp('^Page filtrée sur ATA ' + g1 + ' : \\d+ plans?\\.$').test(annonceFiltre),
      JSON.stringify([annonceDeplie, controle, annonceFiltre]));
    await c.click('#filtrer-groupe-page'); await c.waitForTimeout(400);
    await c.click('#zone-critique .critique-ligne >> nth=1'); await c.waitForTimeout(300);

    // 9. « Voir les N autres » : quinze groupes, puis le reste sur place.
    await c.selectOption('#dim-critique', 'ecp'); await c.waitForTimeout(400);
    const avantPlus = await c.evaluate(() => ({ vues: [...document.querySelectorAll('.critique-rangee')].filter(r => !r.hidden).length, toutes: document.querySelectorAll('.critique-rangee').length,
      bouton: (document.getElementById('plus-groupes') || {}).textContent, etendu: (document.getElementById('plus-groupes') || { getAttribute: () => null }).getAttribute('aria-expanded') }));
    verifier('C — par ECP (plus de quinze groupes) : quinze lignes, puis « Voir les N autres ECP »',
      avantPlus.vues === 15 && avantPlus.toutes > 18 && avantPlus.bouton === 'Voir les ' + (avantPlus.toutes - 15) + ' autres ECP' && avantPlus.etendu === 'false', JSON.stringify(avantPlus));
    const seizieme = await c.evaluate(() => document.querySelectorAll('.critique-rangee')[15].querySelector('.critique-ligne').dataset.groupe);
    await c.click('#plus-groupes'); await c.waitForTimeout(400);
    const apresPlus = await c.evaluate(() => ({ vues: [...document.querySelectorAll('.critique-rangee')].filter(r => !r.hidden).length,
      bouton: document.getElementById('plus-groupes').textContent, focus: document.activeElement && document.activeElement.dataset.groupe }));
    verifier('C — « Voir les N autres » montre tous les groupes sur place ; le focus va au premier montré ; le bouton propose de réduire',
      apresPlus.vues === avantPlus.toutes && apresPlus.focus === seizieme && apresPlus.bouton === 'Réduire la liste aux 15 premiers ECP', JSON.stringify(apresPlus));
    await c.evaluate(() => document.getElementById('plus-groupes').scrollIntoView({ block: 'center' }));
    const yPlus = await c.evaluate(() => document.getElementById('plus-groupes').getBoundingClientRect().top);
    await c.click('#plus-groupes'); await c.waitForTimeout(400);
    const reduitC = await c.evaluate(y => ({ vues: [...document.querySelectorAll('.critique-rangee')].filter(r => !r.hidden).length,
      saut: Math.round(document.getElementById('plus-groupes').getBoundingClientRect().top - y) }), yPlus);
    verifier('C — « Réduire la liste » : retour aux quinze, le bouton reste sous le pointeur', reduitC.vues === 15 && Math.abs(reduitC.saut) <= 2, JSON.stringify(reduitC));
    /* À l'impression, toute la liste. */
    await c.emulateMedia({ media: 'print' });
    const impr = await c.evaluate(() => [...document.querySelectorAll('.critique-rangee')].filter(r => getComputedStyle(r).display !== 'none').length);
    await c.emulateMedia({ media: 'screen' });
    verifier('C — à l’impression, tous les groupes s’impriment, même ceux derrière « Voir les N autres »', impr === avantPlus.toutes, impr + ' / ' + avantPlus.toutes);
    await c.selectOption('#dim-critique', 'ata'); await c.waitForTimeout(400);

    // 10. Un second clic sur la pastille choisie du bloc rend « Tout » (P-F19).
    await c.click('#filtre-valeur-groupe button[data-valeur-bloc="termine"]'); await c.waitForTimeout(300);
    await c.click('#filtre-valeur-groupe button[data-valeur-bloc="termine"]'); await c.waitForTimeout(300);
    const pastille = await c.evaluate(() => ({ bloc: window.__vueValeurs().bloc, tout: document.querySelector('#filtre-valeur-groupe button[data-valeur-bloc=""]').getAttribute('aria-pressed'),
      focus: document.activeElement && document.activeElement.dataset.valeurBloc }));
    verifier('C — un second clic sur la pastille choisie du bloc rend « Tout », le focus reste sur elle',
      pastille.bloc === '' && pastille.tout === 'true' && pastille.focus === 'termine', JSON.stringify(pastille));
    /* À 1440 px, les pastilles du bloc passent à la ligne : aucune n'est cachée sous un fondu. */
    const rangee = await c.evaluate(() => { const z = document.getElementById('filtre-valeur-groupe'), r = z.getBoundingClientRect();
      return { deborde: z.scrollWidth - z.clientWidth, cachees: [...z.querySelectorAll('button')].filter(b => b.getBoundingClientRect().right > r.right + 1).length, masque: getComputedStyle(z).webkitMaskImage || getComputedStyle(z).maskImage }; });
    verifier('C — à 1440 px, les pastilles du bloc passent à la ligne : aucune cachée, pas de fondu', rangee.deborde <= 1 && rangee.cachees === 0 && /none/.test(rangee.masque), JSON.stringify(rangee));

    // 11. La sélection vide : une phrase calme, les commandes du bloc s'effacent (D8).
    await c.fill('#recherche', 'zzzz-introuvable'); await c.waitForTimeout(500);
    const videC = await c.evaluate(() => ({ phrase: (document.querySelector('#zone-critique .etat-vide-phrase') || {}).textContent,
      detail: (document.querySelector('#zone-critique .etat-vide-detail') || {}).textContent,
      commandes: getComputedStyle(document.querySelector('#section-repartition .ligne-filtres')).display }));
    await c.fill('#recherche', ''); await c.waitForTimeout(500);
    const revenu = await c.evaluate(() => getComputedStyle(document.querySelector('#section-repartition .ligne-filtres')).display);
    verifier('C — sélection vide : « Aucun plan dans la sélection. » et son explication ; la ligne des pastilles et de la recherche s’efface, puis revient',
      videC.phrase === 'Aucun plan dans la sélection.' && /Tout effacer/.test(videC.detail || '') && videC.commandes === 'none' && revenu !== 'none', JSON.stringify([videC, revenu]));

    // 12. Thème sombre : rythme requis et jauge lisibles.
    await c.emulateMedia({ colorScheme: 'dark' }); await c.waitForTimeout(200);
    const sombre = await c.evaluate(() => {
      const r = document.querySelector('#zone-critique .critique-effort .requis'), j = document.querySelector('#zone-critique .jauge-rythme');
      return { encre: getComputedStyle(r).color, fond: getComputedStyle(document.getElementById('section-repartition')).backgroundColor,
               piste: getComputedStyle(j).backgroundColor, remplissage: getComputedStyle(j.querySelector('i')).backgroundColor };
    });
    verifier('C — en sombre, le rythme requis tient 4,5:1 sur le panneau et la jauge 3:1 sur sa piste',
      contrasteC(sombre.encre, sombre.fond) >= 4.5 && contrasteC(sombre.remplissage, sombre.piste) >= 3, JSON.stringify(sombre));
    await c.emulateMedia({ colorScheme: 'light' });
    await cC.close();

    // 13. Au téléphone (doigt) : une carte courte, des cibles de 44 px.
    const cT = await contexte({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const t = await page(cT, 'lot C téléphone');
    await t.selectOption('#dim-critique', 'ata'); await t.waitForTimeout(400);
    const tel = await t.evaluate(() => {
      const ls = [...document.querySelectorAll('#zone-critique .critique-ligne')].slice(0, 4);
      const tris = [...document.querySelectorAll('#zone-critique .tri-groupe')].map(b => Math.round(b.getBoundingClientRect().height));
      const aide = document.querySelector('#zone-critique button.aide'), apres = getComputedStyle(aide, '::after');
      return { hauteurs: ls.map(l => Math.round(l.getBoundingClientRect().height)), tris, aideCible: apres.content !== 'none' && parseFloat(apres.top) <= -10,
               debord: document.documentElement.scrollWidth - window.innerWidth };
    });
    verifier('C — au téléphone : une carte par groupe de 140 px au plus, des en-têtes de 44 px, le « ? » avec une cible de 44 px, rien ne déborde',
      tel.hauteurs.every(h => h <= 140) && tel.tris.every(h => h >= 44) && tel.aideCible && tel.debord <= 1, JSON.stringify(tel));
    await t.locator('#zone-critique .critique-ligne').nth(0).tap(); await t.waitForTimeout(400);
    const telOuvert = await t.evaluate(() => ({ vus: [...document.querySelectorAll('#zone-critique .groupe-refs .jeton-ud')].filter(b => !b.hidden).length,
      tous: document.querySelectorAll('#zone-critique .groupe-refs .jeton-ud').length, bouton: Math.round(document.getElementById('filtrer-groupe-page').getBoundingClientRect().height),
      plus: (document.querySelector('#zone-critique button[data-plus-refs]') || {}).textContent }));
    verifier('C — au téléphone, un groupe déplié montre une douzaine de plans puis « Voir les N autres plans de ce groupe » ; « Filtrer la page » fait 44 px',
      telOuvert.vus >= 6 && telOuvert.vus <= 24 && telOuvert.plus === 'Voir les ' + (telOuvert.tous - telOuvert.vus) + ' autres plans de ce groupe' && telOuvert.bouton >= 44, JSON.stringify(telOuvert));
    await cT.close();
  }

  /* Débrief 27, lot E — la comparaison : les côtés de la figure sont des
     boutons qui font ce que fait leur ligne de verdict (souris, clavier,
     doigt), les parts de l'anneau aussi au pointeur ; les mots de la figure,
     en HTML par-dessus le dessin, jamais sous 12 px à aucune largeur, sans
     se chevaucher ; les verdicts en grille 12 | 52 | 1fr | 16 ; « (rien
     d'anormal) » ; une apparition de 300 ms au plus, aucune sous mouvement
     réduit ; « 3 » et « 12 » de « À traiter » nommés par leur phrase, 24 px
     au moins (44 au doigt) ; un lot déplié dit ce qu'il veut dire. */
  section('Débrief 27 : comparaison (lot E)');
  {
    const cE = await contexte();
    const q = await page(cE, 'lot E');
    await q.evaluate(() => document.getElementById('rapprochement').scrollIntoView({ block: 'start' }));
    await q.waitForTimeout(800);
    await q.waitForFunction(() => document.querySelector('#venn-rapprochement .venn.anime'), null, { timeout: 5000 }).catch(() => {});
    const fig = await q.evaluate(() => {
      const f = document.getElementById('venn-rapprochement');
      return { role: f.getAttribute('role'), svgCache: f.querySelector('svg').getAttribute('aria-hidden'),
        boutons: [...f.querySelectorAll('button.cote')].map(b => b.dataset.rapp + ':' + b.textContent.replace(/\s+/g, ' ').trim()),
        svgTexte: f.querySelectorAll('svg text').length,
        anim: Math.max(0, ...[...f.querySelectorAll('.venn, .venn *')].map(e => {
          const c = getComputedStyle(e); if (c.animationName === 'none') return 0;
          const d = c.animationDuration.split(',').map(parseFloat), l = c.animationDelay.split(',').map(parseFloat);
          return Math.max(...d.map((x, i) => Math.round((x + (l[i] || 0)) * 1000)));
        })) };
    });
    verifier('E — la figure est un groupe : ses trois côtés sont des boutons, nommés par leur nombre et leurs mots ; son dessin est caché aux lecteurs d’écran',
      fig.role === 'group' && fig.svgCache === 'true' && fig.svgTexte === 0 &&
      fig.boutons.join(' | ') === 'manque:' + MANQUE + ' validés sans SEE | attente:' + fr(ATTENTE) + ' pas encore dans SEE | seul:5 seulement dans SEE', JSON.stringify(fig));
    verifier('E — l’apparition de la figure dure 300 ms au plus', fig.anim > 0 && fig.anim <= 300, String(fig.anim));
    const lire = () => q.evaluate(() => ({
      lignes: document.querySelectorAll('#corps-tableau tr').length,
      presses: [...document.querySelectorAll('#rapprochement button[aria-pressed="true"]')].map(b => (b.closest('#venn-rapprochement') ? 'fig:' : b.closest('#reponse-rapprochement') ? 'rep:' : 'ver:') + b.dataset.rapp).sort().join(),
      ouvert: [...document.querySelectorAll('#verdicts-rapprochement .verdict-bloc[data-ouvert="true"]')].map(b => b.dataset.lot).join(),
      focus: document.activeElement && document.activeElement.closest('#venn-rapprochement') ? document.activeElement.dataset.rapp : null,
      detail: (document.querySelector('#verdicts-rapprochement .rapp-detail') || {}).textContent || '',
      annonce: (document.getElementById('annonce') || {}).textContent || ''
    }));
    // À la souris : le côté « validés sans SEE ».
    await q.click('#venn-rapprochement .cote[data-cle="manque"]'); await q.waitForTimeout(900);
    await q.waitForFunction(() => /^Comparaison/.test((document.getElementById('annonce') || {}).textContent || ''), null, { timeout: 4000 }).catch(() => {});
    const eM = await lire();
    verifier('E — cliquer « ' + MANQUE + ' validés sans SEE » dans la figure fait ce que fait sa ligne : le tableau montre les ' + MANQUE + ' plans, le verdict est posé et déplié, le côté pressé, le focus y reste',
      eM.lignes === MANQUE && eM.ouvert === 'manque' && eM.presses === 'fig:manque,rep:manque,ver:manque' && eM.focus === 'manque', JSON.stringify(eM));
    verifier('E — le lot déplié dit ce qu’il veut dire et ce que fait un clic, et le changement est annoncé',
      /^À vérifier des deux côtés/.test(eM.detail) && /Un clic sur un plan le montre seul dans le tableau\./.test(eM.detail) &&
      /^Comparaison : 3 validés dans GATES, mais SEE ne les connaît pas\. Le tableau des plans ne montre plus que ceux-là\.$/.test(eM.annonce), JSON.stringify([eM.detail, eM.annonce]));
    await q.click('#venn-rapprochement .cote[data-cle="manque"]'); await q.waitForTimeout(900);
    await q.waitForFunction(() => /retiré/.test((document.getElementById('annonce') || {}).textContent || ''), null, { timeout: 4000 }).catch(() => {});
    const eM2 = await lire();
    verifier('E — un second clic sur le côté pressé retire le filtre et replie le lot',
      eM2.lignes === TOTAL && eM2.presses === '' && eM2.ouvert === '' && eM2.annonce === 'Filtre de la comparaison retiré.', JSON.stringify(eM2));
    // Au clavier : Entrée puis Espace sur « pas encore dans SEE ».
    await q.focus('#venn-rapprochement .cote[data-cle="attente"]'); await q.keyboard.press('Enter'); await q.waitForTimeout(700);
    const eA = await lire();
    const eclaire = await q.evaluate(() => [...document.querySelectorAll('#venn-rapprochement .survole')].map(x => x.dataset.cle).join());
    verifier('E — au clavier, Entrée sur « pas encore dans SEE » pose et déplie son lot, le focus reste sur le côté, qui s’éclaire',
      eA.lignes === ATTENTE && eA.ouvert === 'attente' && eA.focus === 'attente' && eclaire === 'attente', JSON.stringify([eA, eclaire]));
    await q.keyboard.press('Space'); await q.waitForTimeout(700);
    const eA2 = await lire();
    verifier('E — Espace le retire', eA2.lignes === TOTAL && eA2.ouvert === '' && eA2.focus === 'attente', JSON.stringify(eA2));
    // Au pointeur : une part de l'anneau.
    const surPart = await q.evaluate(() => {
      const path = document.querySelector('#venn-rapprochement .donut-seg[data-cle="avance"]');
      const m = path.getScreenCTM(), pt = path.getPointAtLength(path.getTotalLength() / 2);
      const x = m.a * pt.x + m.c * pt.y + m.e, y = m.b * pt.x + m.d * pt.y + m.f;
      const sous = document.elementFromPoint(x, y);
      return { x, y, cible: sous && sous.getAttribute('data-cible'), curseur: sous && getComputedStyle(sous).cursor };
    });
    await q.mouse.click(surPart.x, surPart.y); await q.waitForTimeout(800);
    const eP = await lire();
    verifier('E — cliquer la part ambre de l’anneau pose et déplie « dans SEE, mais GATES ne les dit pas validés » (12 plans), curseur de lien',
      surPart.cible === 'avance' && surPart.curseur === 'pointer' && eP.lignes === AVANCE && eP.ouvert === 'avance', JSON.stringify([surPart, eP]));
    await q.mouse.click(surPart.x, surPart.y); await q.waitForTimeout(700);
    // Les verdicts : la grille 12 | 52 | 1fr | 16.
    const grille = await q.evaluate(() => {
      const v = document.querySelector('#verdicts-rapprochement .verdict'), c = getComputedStyle(v);
      const p = v.querySelector('.pastille').getBoundingClientRect(), n = v.querySelector('.verdict-n'), nr = n.getBoundingClientRect();
      return { colonnes: c.gridTemplateColumns, ecart: c.columnGap, droite: getComputedStyle(n).textAlign, pastilleAuNombre: Math.round(nr.left - p.right) };
    });
    verifier('E — verdicts en grille 12 | 52 | 1fr | 16 px, 10 px d’écart, le nombre aligné à droite près de sa pastille',
      /^12px 52px .+ 16px$/.test(grille.colonnes) && grille.ecart === '10px' && grille.droite === 'right' && grille.pastilleAuNombre <= 52, JSON.stringify(grille));
    const insecable = await q.evaluate(() => {
      const s = document.querySelector('#verdicts-rapprochement button[data-rapp="attente"] .sans-coupure');
      return s ? s.textContent + '|' + getComputedStyle(s).whiteSpace : null;
    });
    verifier('E — « (rien d’anormal) » ne se coupe pas', insecable === '(rien d’anormal)|nowrap', String(insecable));
    // « À traiter » : nommés par leur phrase, 24 px au moins.
    const rep = await q.evaluate(() => [...document.querySelectorAll('#reponse-rapprochement button')].map(b => {
      const r = b.getBoundingClientRect(); return { nom: b.getAttribute('aria-label'), l: Math.round(r.width), h: Math.round(r.height) };
    }));
    verifier('E — « ' + MANQUE + ' » et « 12 » de « À traiter » se nomment par leur phrase et offrent 24 px au moins',
      rep.length === 2 && rep[0].nom === MANQUE + ' plans validés absents de SEE' && rep[1].nom === '12 plans dans SEE que GATES ne dit pas validés' &&
      rep.every(x => x.l >= 24 && x.h >= 24), JSON.stringify(rep));
    // Les mots de la figure, à toutes les largeurs : 12 px au moins, sans chevauchement, dans la figure.
    for (const largeur of [1280, 1024, 900, 600, 390, 320]) {
      await redimensionner(q, largeur, 900);
      const m = await q.evaluate(() => {
        const f = document.getElementById('venn-rapprochement'), boite = f.getBoundingClientRect();
        const mots = [...f.querySelectorAll('.venn-base, .cote, .commun-n, .commun-mot')];
        const tailles = [...f.querySelectorAll('.venn span, .venn p')].map(e => parseFloat(getComputedStyle(e).fontSize));
        const r = mots.map(e => e.getBoundingClientRect());
        let chevauche = 0;
        for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) {
          if (r[i].right > r[j].left + 1 && r[j].right > r[i].left + 1 && r[i].bottom > r[j].top + 1 && r[j].bottom > r[i].top + 1) chevauche++;
        }
        return { trace: f.querySelector('.venn').className, plusPetit: Math.min(...tailles), chevauche,
          dedans: r.every(x => x.left >= boite.left - 1 && x.right <= boite.right + 1 && x.top >= boite.top - 1 && x.bottom <= boite.bottom + 1),
          page: document.documentElement.scrollWidth <= window.innerWidth };
      });
      verifier('E — à ' + largeur + ' px (' + m.trace.replace('venn ', '') + ') : les mots de la figure à 12 px au moins, sans se chevaucher, dans la figure, sans débord de page',
        m.plusPetit >= 12 && m.chevauche === 0 && m.dedans && m.page, JSON.stringify(m));
    }
    await cE.close();
    // Au doigt (téléphone) : toucher un côté fait ce que fait sa ligne ; cibles de 44 px.
    const cT = await contexte({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const t = await page(cT, 'lot E doigt');
    await t.evaluate(() => document.getElementById('venn-rapprochement').scrollIntoView({ block: 'center' }));
    /* Débrief 29 (batterie) : plus de délai fixe — la figure à l'écran, son
       entrée jouée (« anime », plus de transition en cours), 5 s au plus. */
    await t.waitForFunction(() => { const f = document.querySelector('#venn-rapprochement .venn'), r = f && f.getBoundingClientRect();
      return !!r && r.bottom > 0 && r.top < innerHeight && f.classList.contains('anime') &&
        !document.getAnimations().some(a => a.playState === 'running' && isFinite(a.effect.getComputedTiming().endTime)); }, null, { timeout: 5000, polling: 'raf' }).catch(() => {});
    await t.tap('#venn-rapprochement .cote[data-cle="seul"]'); await t.waitForTimeout(1200);
    const eT = await t.evaluate(() => {
      const bloc = document.querySelector('#verdicts-rapprochement .verdict-bloc[data-lot="seul"]').getBoundingClientRect();
      return { ouvert: [...document.querySelectorAll('#verdicts-rapprochement .verdict-bloc[data-ouvert="true"]')].map(b => b.dataset.lot).join(),
        seconde: document.querySelectorAll('#corps-seconde tr[data-i]').length, blocEnVue: bloc.top >= 0 && bloc.top < innerHeight - 60 };
    });
    verifier('E — au doigt, toucher « 5 seulement dans SEE » pose et déplie son lot, et la liste dépliée est à l’écran',
      eT.ouvert === 'seul' && eT.seconde === 5 && eT.blocEnVue, JSON.stringify(eT));
    const doigt = await t.evaluate(() => ({
      rep: [...document.querySelectorAll('#reponse-rapprochement button')].map(b => { const r = b.getBoundingClientRect(), a = getComputedStyle(b, '::after');
        return Math.round(r.height - 2 * parseFloat(a.top)) + 'x' + Math.round(r.width - 2 * parseFloat(a.left)); }),
      verdicts: Math.min(...[...document.querySelectorAll('#verdicts-rapprochement .verdict')].map(b => b.getBoundingClientRect().height)),
      cotes: Math.min(...[...document.querySelectorAll('#venn-rapprochement .cote')].map(b => b.getBoundingClientRect().height))
    }));
    verifier('E — au doigt : « À traiter » touchables sur 44 px, chaque ligne de verdict et chaque côté de la figure 44 px au moins',
      doigt.rep.length === 2 && doigt.rep.every(x => x.split('x').every(v => +v >= 44)) && doigt.verdicts >= 44 && doigt.cotes >= 44, JSON.stringify(doigt));
    await cT.close();
    // Mouvement réduit : rien ne bouge.
    const cR = await contexte({ reducedMotion: 'reduce' });
    const r = await page(cR, 'lot E calme');
    await r.evaluate(() => document.getElementById('rapprochement').scrollIntoView()); await r.waitForTimeout(600);
    const calme = await r.evaluate(() => ({
      animations: [...document.querySelectorAll('#venn-rapprochement *')].filter(e => getComputedStyle(e).animationName !== 'none').length,
      transitions: [...document.querySelectorAll('#rapprochement .donut-seg, #rapprochement .chevron')].filter(e => getComputedStyle(e).transitionDuration.split(',').some(x => parseFloat(x) > 0)).length
    }));
    verifier('E — sous « moins d’animations », la figure ne s’anime pas et rien n’y glisse', calme.animations === 0 && calme.transitions === 0, JSON.stringify(calme));
    await cR.close();
  }

  // =================================================================
  /* Débrief 27, lot B — le journal des changements : deux rangées de
     pastilles titrées qui passent à la ligne (plus rien de caché sous un
     fondu), « Tout » au second clic, un en-tête à deux étages dans l'ordre
     de la légende, des semaines qui disent leurs dates, la hauteur
     naturelle (plus de cadre qui défile), la ligne de la semaine ouverte
     collée pendant qu'on lit, un compte touché qui déplie sa semaine, un
     état vide calme, et le doigt (44 px). */
  section('Débrief 27 : le journal des changements (lot B)');
  {
    /* Le journal de la démonstration écrit avec les mots de GATES : sept
       valeurs, comme chez Nathan (les valeurs « en cours » et « à faire »
       réparties par référence), VALIDATED déclarée finie. */
    const versGATES = () => {
      const s = window.__jeuDExemple('HDK');
      const h = ref => { let x = 0; for (const ch of ref) x = (x * 31 + ch.charCodeAt(0)) % 997; return x; };
      const code = (ref, v) => v === 'Terminé' ? 'VALIDATED' : v === 'En cours' ? ['PWD_IN_PROGRESS', 'PWD_TO_CONTROL', 'TO_CONFIRM'][h(ref) % 3]
        : v === 'À faire' ? ['FWD_TO_SEIZE', 'TO_TREAT'][h(ref) % 2] : v;
      s.valeursFinies = ['VALIDATED']; s.valeursAFaire = ['FWD_TO_SEIZE', 'TO_TREAT'];
      s.plans.forEach(x => { x.avancement = code(x.reference, x.avancement); });
      s.releves.forEach(r => { Object.keys(r.plans).forEach(ref => { r.plans[ref] = code(ref, r.plans[ref]); }); });
      /* Au dernier relevé, des plans non renseignés passent à FWD_TO_SEIZE
         et à TO_TREAT, et trois plans sortent de l'extract : les onze
         colonnes de chez Nathan (six valeurs, quatre mouvements). */
      const dernier = s.releves[s.releves.length - 1];
      s.plans.filter(x => x.avancement === '').slice(0, 8).forEach((x, i) => { x.avancement = dernier.plans[x.reference] = i % 2 ? 'TO_TREAT' : 'FWD_TO_SEIZE'; });
      const partis = Object.keys(dernier.plans).slice(0, 3);
      partis.forEach(ref => { delete dernier.plans[ref]; });
      s.plans = s.plans.filter(x => partis.indexOf(x.reference) === -1);
      window.__chargerSource(s);
    };
    const outils = () => {
      window.__lum = c => {
        const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
        return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
      };
      window.__contraste = (a, b) => { const x = window.__lum(a), y = window.__lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    };
    const cB = await contexte({ viewport: { width: 1440, height: 950 } });
    const qB = await page(cB, 'lot B');
    await qB.evaluate(outils);
    await qB.evaluate(versGATES);
    await qB.waitForTimeout(500);

    // --- 1. La rangée : « Tout », puis « Passés à » et « Mouvements », tout visible, à toute largeur.
    const rangee = () => qB.evaluate(() => {
      const r = document.getElementById('filtre-journal'), l = r.closest('.ligne-filtres'), rech = l.querySelector('.recherche-groupe');
      const rr = r.getBoundingClientRect(), lr = l.getBoundingClientRect(), sr = rech.getBoundingClientRect();
      const boutons = [...r.querySelectorAll('button')];
      const premier = r.querySelector('.rang-journal .puces-rang button');
      const mouv = [...r.querySelectorAll('.rang-journal')].find(g => /Mouvements/.test(g.textContent));
      return {
        tout: boutons[0] && boutons[0].dataset.journal === '' && boutons[0].textContent.trim() === 'Tout',
        titres: [...r.querySelectorAll('.rang-journal')].map(g => g.querySelector('.mot-rang').textContent + ':' + g.getAttribute('role') + ':' + !!document.getElementById(g.getAttribute('aria-labelledby'))),
        mouvements: mouv ? [...mouv.querySelectorAll('button')].map(b => b.dataset.journal) : [],
        caches: boutons.filter(b => { const x = b.getBoundingClientRect(); return x.width < 2 || x.right > rr.right + 1 || x.left < rr.left - 1 || x.bottom > rr.bottom + 1; }).map(b => b.dataset.journal),
        deborde: r.scrollWidth > r.clientWidth + 1, fondu: r.classList.contains('deborde-droite'), defile: getComputedStyle(r).overflowX,
        droite: Math.round(lr.right - sr.right), memeLigne: !!premier && Math.abs(sr.top - premier.getBoundingClientRect().top) <= 6,
        dessous: sr.top >= rr.bottom - 1, page: document.documentElement.scrollWidth <= window.innerWidth
      };
    });
    for (const w of [1440, 1280, 1024, 800]) {
      await redimensionner(qB, w, 950);
      const r = await rangee();
      verifier('à ' + w + ' px, la rangée du journal : « Tout », puis « Passés à » et « Mouvements » (deux groupes nommés) ; chaque pastille en vue, rien sous un fondu ni hors du cadre ; la recherche ' +
        (w >= 1180 ? 'au bout de la première rangée' : 'sur sa ligne, dessous'),
        r.tout && r.titres.join() === 'Passés à:group:true,Mouvements:group:true' && !r.caches.length && !r.deborde && !r.fondu && r.defile === 'visible' &&
        r.droite <= 1 && (w >= 1180 ? r.memeLigne : r.dessous) && r.page, JSON.stringify(r));
      if (w === 1440) {
        verifier('« Mouvements » : les reculs d’abord, puis les nouveaux, les disparus, les changements d’indice',
          r.mouvements[0] === 'reculs' && r.mouvements.join() === ['reculs', 'nouveaux', 'disparus', 'indice'].filter(k => r.mouvements.indexOf(k) !== -1).join(), JSON.stringify(r.mouvements));
      }
    }
    await redimensionner(qB, 1440, 950);
    const recul = await qB.evaluate(() => {
      const b = document.querySelector('#filtre-journal button[data-journal="reculs"]');
      const t = document.createElement('span'); t.style.color = 'var(--alerte)'; document.body.appendChild(t); const alerte = getComputedStyle(t).color; t.remove();
      const fond = getComputedStyle(document.getElementById('section-journal')).backgroundColor;
      return b ? { encre: getComputedStyle(b).color, n: getComputedStyle(b.querySelector('.n')).color, alerte, c: +window.__contraste(getComputedStyle(b.querySelector('.n')).color, fond).toFixed(2),
                   nom: (b.textContent.replace(/\s+/g, ' ').trim()) } : null;
    });
    verifier('la pastille « Reculs » est en rouge (--alerte), son compte aussi, à 4,5:1 au moins',
      !!recul && recul.encre === recul.alerte && recul.n === recul.alerte && recul.c >= 4.5, JSON.stringify(recul));
    /* Pressée, une pastille ne s'élargit pas (sa version grasse est en
       réserve) : la rangée ne bouge pas sous le pointeur. */
    const largeurs = await qB.evaluate(async () => {
      const lire = () => [...document.querySelectorAll('#filtre-journal button')].map(b => Math.round(b.getBoundingClientRect().width));
      const avant = lire();
      document.querySelector('#filtre-journal .puces-rang button').click();
      await new Promise(f => setTimeout(f, 200));
      const apres = lire();
      return { avant, apres };
    });
    verifier('choisir une pastille ne change la largeur d’aucune pastille (la rangée reste en place)',
      largeurs.avant.join() === largeurs.apres.join(), JSON.stringify(largeurs));

    // --- 2. Un second clic sur la pastille pressée revient à « Tout » ; le focus reste ; la page le dit.
    await qB.click('#filtre-journal button[data-journal=""]'); await qB.waitForTimeout(250);
    await qB.click('#filtre-journal button[data-journal="reculs"]'); await qB.waitForTimeout(250);
    const un = await qB.evaluate(() => window.__vueValeurs().journal);
    await qB.click('#filtre-journal button[data-journal="reculs"]'); await qB.waitForTimeout(250);
    await qB.waitForFunction(() => /^Journal : /.test((document.getElementById('annonce') || {}).textContent || ''), null, { timeout: 4000 }).catch(() => {});
    const deux = await qB.evaluate(() => ({ journal: window.__vueValeurs().journal, focus: (document.activeElement || {}).dataset ? document.activeElement.dataset.journal : null,
      tout: document.querySelector('#filtre-journal button[data-journal=""]').getAttribute('aria-pressed'), annonce: document.getElementById('annonce').textContent }));
    verifier('un second clic sur « Reculs » pressée revient à « Tout » ; le focus reste sur la pastille, et la page annonce « Journal : tous les changements… »',
      un === 'reculs' && deux.journal === '' && deux.tout === 'true' && deux.focus === 'reculs' && /^Journal : tous les changements, \d+/.test(deux.annonce), JSON.stringify([un, deux]));

    // --- 3. L'en-tête : deux étages, l'ordre de la légende, les codes en Plex Mono 11, « Répartition ».
    const tete = await qB.evaluate(() => {
      const z = document.getElementById('zone-journal'), e = z.querySelector('.journal-entetes');
      const cols = [...e.querySelectorAll(':scope > span')], groupes = [...e.querySelectorAll('.entete-groupe')];
      const x = el => { const r = el.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right)]; };
      const codes = [...e.querySelectorAll('.code-entete')].map(c => {
        const cs = getComputedStyle(c), lh = parseFloat(cs.lineHeight);
        /* Où le code passe à la ligne : jamais au milieu d'un mot. */
        const coupes = [];
        let haut = null;
        const texte = [...c.childNodes].filter(t => t.nodeType === 3);
        let prec = '';
        texte.forEach(t => { for (let i = 0; i < t.textContent.length; i++) {
          const rg = document.createRange(); rg.setStart(t, i); rg.setEnd(t, i + 1); const r = rg.getClientRects()[0]; if (!r) continue;
          if (haut !== null && r.top > haut + 3) coupes.push(prec);
          haut = r.top; prec = t.textContent[i];
        } });
        return { t: c.textContent, police: cs.fontFamily.split(',')[0].replace(/"/g, ''), taille: parseFloat(cs.fontSize), lignes: Math.round(c.getBoundingClientRect().height / lh), coupes };
      });
      const vals = window.__valeurs().map(v => v.libelle);
      const noms = cols.slice(1, -1).map(c => c.textContent.trim());
      const passes = noms.filter(t => vals.indexOf(t) !== -1);
      return {
        groupes: groupes.map(g => ({ t: g.textContent, x: x(g) })), noms, passes, vals,
        premierPasse: x(cols[1]), dernierPasse: x(cols[passes.length]), premierMouv: cols[passes.length + 1] ? x(cols[passes.length + 1]) : null, dernierMouv: x(cols[cols.length - 2]),
        semaine: cols[0].textContent, jauge: cols[cols.length - 1].textContent, jaugeVue: cols[cols.length - 1].getClientRects().length > 0, codes,
        colle: getComputedStyle(e).position, deborde: z.scrollWidth > z.clientWidth + 1, serre: z.classList.contains('journal-serre')
      };
    });
    const ordreMouv = ['Reculs', 'Nouveaux', 'Disparus', 'Changements d’indice'];
    verifier('l’en-tête du journal sur deux étages : « Passés à » au-dessus des seules colonnes des valeurs, « Mouvements » au-dessus des autres',
      tete.groupes.length === 2 && tete.groupes[0].t === 'Passés à' && tete.groupes[1].t === 'Mouvements' &&
      Math.abs(tete.groupes[0].x[0] - tete.premierPasse[0]) <= 1 && tete.groupes[0].x[1] <= tete.premierMouv[0] && tete.groupes[0].x[1] >= tete.dernierPasse[0] &&
      Math.abs(tete.groupes[1].x[0] - tete.premierMouv[0]) <= 1 && tete.groupes[1].x[1] >= tete.dernierMouv[0], JSON.stringify(tete.groupes) + JSON.stringify([tete.premierPasse, tete.dernierPasse, tete.premierMouv, tete.dernierMouv]));
    verifier('les colonnes dans l’ordre de la légende : VALIDATED, PWD_IN_PROGRESS, PWD_TO_CONTROL, TO_CONFIRM, FWD_TO_SEIZE, TO_TREAT…, puis reculs, nouveaux, disparus, changements d’indice',
      tete.passes.join() === tete.vals.filter(v => tete.passes.indexOf(v) !== -1).join() && tete.passes[0] === 'VALIDATED' && tete.passes.length >= 5 &&
      tete.noms.slice(tete.passes.length).join() === ordreMouv.filter(m => tete.noms.indexOf(m) !== -1).join() && tete.noms.length > tete.passes.length, JSON.stringify(tete.noms));
    verifier('sous « Passés à », le code seul, en Plex Mono 11 px — coupé une fois au plus, et seulement après un « _ » ; la semaine a son mot, la jauge « Répartition » ; l’en-tête reste collé',
      tete.codes.length >= 5 && tete.codes.every(c => c.police === 'IBM Plex Mono' && c.taille === 11 && c.lignes <= 2 && c.coupes.every(k => k === '_')) &&
      tete.semaine === 'Semaine' && tete.jauge === 'Répartition' && tete.jaugeVue && tete.colle === 'sticky' && !tete.deborde && !tete.serre, JSON.stringify(tete.codes));
    // À 1 024 px : plus de jauge ; les onze colonnes ne tiennent pas — chaque compte prend ses mots, rien n'est coupé.
    await redimensionner(qB, 1024, 900);
    const etroit = await qB.evaluate(() => {
      const z = document.getElementById('zone-journal'), zr = z.getBoundingClientRect();
      return { serre: z.classList.contains('journal-serre'), deborde: z.scrollWidth > z.clientWidth + 1,
               jauges: [...z.querySelectorAll('.mini-jauge')].filter(j => j.getClientRects().length).length,
               hors: [...z.querySelectorAll('.journal-tete button, .journal-tete .mot-case')].filter(b => b.getClientRects().length && b.getBoundingClientRect().right > zr.right + 1).length,
               mots: [...z.querySelectorAll('.journal-tete .mot-case')].filter(m => m.getBoundingClientRect().width > 2).length };
    });
    verifier('à 1 024 px, le journal ne coupe plus « Reculs » ni « Disparus » au bord : trop de colonnes pour la carte, chaque compte porte ses mots ; plus de jauge',
      !etroit.deborde && etroit.hors === 0 && (etroit.serre ? etroit.mots > 5 : true) && etroit.jauges === 0, JSON.stringify(etroit));
    await redimensionner(qB, 1440, 950);
    verifier('revenu à 1 440 px, le journal redevient un tableau',
      await qB.evaluate(() => { const z = document.getElementById('zone-journal'); return z.classList.contains('journal-grille') && !z.classList.contains('journal-serre'); }));

    // --- 4. Les semaines disent leurs dates.
    const dates = await qB.evaluate(() => [...document.querySelectorAll('#zone-journal .journal-plier')].map(b => ({ t: b.querySelector('.sem').textContent.replace(/[  ]/g, ' '), nom: b.getAttribute('aria-label') })));
    verifier('chaque semaine dit ses dates — « S38 · du ven. 11 au ven. 18 sept. » —, en toutes lettres pour un lecteur d’écran',
      dates.length >= 5 && dates.every(d => /^S\d{1,2} · du ven\. \d{1,2}( [a-zéû]+\.?)? au ven\. \d{1,2} [a-zéû]+\.?$/.test(d.t) && /^S\d{1,2}, semaine du vendredi \d{1,2}( [a-zéû]+)? au vendredi \d{1,2} [a-zéû]+$/.test(d.nom)) &&
      dates.some(d => / au ven\. \d{1,2} (sept|août|juil)/.test(d.t)), JSON.stringify(dates.slice(0, 3)));

    // --- 5. La hauteur naturelle : plus de cadre qui défile, la molette fait défiler la page.
    const naturel = await qB.evaluate(() => { const z = document.getElementById('zone-journal'), cs = getComputedStyle(z);
      return { y: cs.overflowY, max: cs.maxHeight, classe: z.classList.contains('defile-liste') }; });
    await qB.evaluate(() => { const z = document.getElementById('zone-journal'); window.scrollTo(0, z.getBoundingClientRect().top + scrollY - 200); });
    await qB.waitForTimeout(200);
    const yAvant = await qB.evaluate(() => scrollY);
    const zb = await qB.evaluate(() => { const r = document.getElementById('zone-journal').getBoundingClientRect(); return { x: r.left + r.width / 2, y: Math.min(r.top + 120, innerHeight - 40) }; });
    await qB.mouse.move(zb.x, zb.y);
    for (let i = 0; i < 4; i++) { await qB.mouse.wheel(0, 120); await qB.waitForTimeout(60); }
    await qB.waitForTimeout(200);
    const yApres = await qB.evaluate(() => scrollY);
    verifier('le journal prend sa hauteur : pas de cadre qui défile, la molette au-dessus de lui fait défiler la page',
      naturel.y === 'visible' && naturel.max === 'none' && !naturel.classe && yApres - yAvant >= 300, JSON.stringify([naturel, yAvant, yApres]));

    // --- 6. Une semaine ouverte : douze lignes puis « Voir les N autres » ; le focus passe à la treizième.
    await qB.evaluate(() => { const z = document.getElementById('zone-journal'); window.scrollTo(0, z.getBoundingClientRect().top + scrollY - 200); });
    await qB.click('#zone-journal .journal-semaine .journal-plier >> nth=0'); await qB.waitForTimeout(300);
    const ouverte = await qB.evaluate(() => { const s = document.querySelector('#zone-journal .journal-semaine'), p = s.querySelector('.journal-plus');
      return { lignes: s.querySelectorAll('.journal-ligne').length, plus: p ? p.textContent : null, focus: document.activeElement.dataset.semaine === s.querySelector('.journal-plier').dataset.semaine }; });
    await qB.focus('#zone-journal .journal-semaine .journal-plus'); await qB.keyboard.press('Enter'); await qB.waitForTimeout(300);
    const toutes = await qB.evaluate(() => { const s = document.querySelector('#zone-journal .journal-semaine'), ls = [...s.querySelectorAll('.journal-ligne')];
      return { lignes: ls.length, rang: ls.indexOf(document.activeElement), plus: !!s.querySelector('.journal-plus') }; });
    verifier('une semaine ouverte montre douze lignes puis « Voir les N autres » ; Entrée les déplie sur place et le focus passe à la treizième',
      ouverte.lignes === 12 && /^Voir les \d+ autres$/.test(ouverte.plus || '') && ouverte.focus && toutes.lignes > 12 && toutes.rang === 12 && !toutes.plus, JSON.stringify([ouverte, toutes]));

    // --- 7. La ligne de la semaine ouverte reste en vue pendant qu'on lit ses plans.
    await qB.evaluate(() => { const s = document.querySelector('#zone-journal .journal-semaine'); window.scrollTo(0, s.getBoundingClientRect().top + scrollY + 300); });
    await qB.waitForTimeout(300);
    const colle = await qB.evaluate(() => {
      const s = document.querySelector('#zone-journal .journal-semaine'), t = s.querySelector('.journal-tete'), e = document.querySelector('#zone-journal .journal-entetes');
      const bas = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bas-sommaire')) || 0;
      const som = document.getElementById('sommaire').getBoundingClientRect();
      return { bas, sommaire: Math.round(som.bottom), entetesHaut: Math.round(e.getBoundingClientRect().top), entetesBas: Math.round(e.getBoundingClientRect().bottom),
               tete: Math.round(t.getBoundingClientRect().top), debutSemaine: Math.round(s.getBoundingClientRect().top) };
    });
    verifier('en lisant les plans d’une semaine ouverte, l’en-tête du tableau reste collé sous le sommaire, et la ligne de la semaine juste dessous',
      colle.debutSemaine < colle.entetesBas - 100 && Math.abs(colle.entetesHaut - colle.bas) <= 1 && Math.abs(colle.tete - colle.entetesBas) <= 1, JSON.stringify(colle));
    // Au clavier, en remontant ses lignes (Maj+Tab) : aucune ne passe sous ce qui est collé (2.4.11).
    await qB.evaluate(() => { const ls = document.querySelector('#zone-journal .journal-semaine').querySelectorAll('.journal-ligne'); ls[ls.length - 1].focus(); });
    let cachees = 0, vues = 0;
    for (let i = 0; i < 16; i++) {
      await qB.keyboard.press('Shift+Tab'); await qB.waitForTimeout(40);
      const r = await qB.evaluate(() => {
        const a = document.activeElement; if (!a.classList.contains('journal-ligne')) return null;
        const bas = Math.max(0, ...[...document.querySelectorAll('#sommaire, #zone-journal .journal-entetes, #zone-journal .journal-semaine.ouverte > .journal-tete')]
          .filter(e => e.getClientRects().length && getComputedStyle(e).position === 'sticky').map(e => e.getBoundingClientRect().bottom));
        return a.getBoundingClientRect().top < bas - 1;
      });
      if (r !== null) { vues++; if (r) cachees++; }
    }
    verifier('au clavier, en remontant les plans d’une semaine ouverte, aucune ligne focalisée ne passe sous l’en-tête collé ni sous la ligne de sa semaine',
      vues >= 10 && cachees === 0, JSON.stringify({ vues, cachees }));
    // Au clavier, la replier garde le focus sur elle ; la ligne revient sous le pointeur.
    await qB.focus('#zone-journal .journal-semaine .journal-plier'); await qB.keyboard.press('Enter'); await qB.waitForTimeout(300);
    const replie = await qB.evaluate(() => { const a = document.activeElement, t = document.querySelector('#zone-journal .journal-semaine .journal-tete');
      return { cls: a.className, ouvert: a.getAttribute('aria-expanded'), haut: Math.round(t.getBoundingClientRect().top), vue: t.getBoundingClientRect().top >= 0 && t.getBoundingClientRect().bottom <= innerHeight }; });
    verifier('replier au clavier une semaine lue de loin : le focus reste sur sa ligne, qui revient à l’écran (pas en haut de la page)',
      replie.cls === 'journal-plier' && replie.ouvert === 'false' && replie.vue, JSON.stringify(replie));

    // --- 8. Toucher un compte : le filtre, et sa semaine dépliée, à l'écran ; le focus reste sur le compte.
    await qB.evaluate(() => { const z = document.getElementById('zone-journal'); window.scrollTo(0, z.getBoundingClientRect().top + scrollY - 150); });
    await qB.waitForTimeout(200);
    const cible = await qB.evaluate(() => { const s = document.querySelectorAll('#zone-journal .journal-semaine')[2]; const b = s.querySelector('button[data-passage]');
      return { sem: s.querySelector('.journal-plier').dataset.semaine, passage: b.dataset.passage }; });
    await qB.click('#zone-journal .journal-semaine >> nth=2 >> button[data-passage] >> nth=0'); await qB.waitForTimeout(400);
    const compte = await qB.evaluate(c => {
      const t = [...document.querySelectorAll('#zone-journal .journal-plier')].find(b => b.dataset.semaine === c.sem), s = t.closest('.journal-semaine');
      const a = document.activeElement, e = document.querySelector('#zone-journal .journal-entetes');
      return { filtre: window.__vueValeurs().journal, ouverte: t.getAttribute('aria-expanded'), lignes: s.querySelectorAll('.journal-ligne').length,
               focus: a.dataset.passage === c.passage && s.contains(a), haut: Math.round(s.getBoundingClientRect().top), bas: Math.round(e.getBoundingClientRect().bottom), vh: innerHeight };
    }, cible);
    verifier('toucher un compte d’une semaine filtre le journal ET déplie cette semaine sur ses plans, à l’écran ; le focus reste sur le compte',
      compte.filtre === cible.passage && compte.ouverte === 'true' && compte.lignes > 0 && compte.focus && compte.haut >= compte.bas - 2 && compte.haut < compte.vh - 80, JSON.stringify([cible, compte]));
    // Toute la ligne d'une semaine la déplie : un clic dans une case vide.
    await qB.click('#filtre-journal button[data-journal=""]'); await qB.waitForTimeout(250);
    const caseVide = await qB.evaluate(async () => {
      const s = [...document.querySelectorAll('#zone-journal .journal-semaine')].find(x => x.querySelector('.case-vide') && x.querySelector('.journal-plier').getAttribute('aria-expanded') === 'false');
      if (!s) return null;
      const i = s.querySelector('.journal-plier').dataset.semaine, c = s.querySelector('.case-vide');
      c.scrollIntoView({ block: 'center' });
      const r = c.getBoundingClientRect();
      return { i, x: r.left + r.width / 2, y: r.top + r.height / 2, tiret: c.textContent.trim() };
    });
    if (caseVide) {
      await qB.mouse.click(caseVide.x, caseVide.y); await qB.waitForTimeout(300);
      const apres = await qB.evaluate(i => [...document.querySelectorAll('#zone-journal .journal-plier')].find(b => b.dataset.semaine === i).getAttribute('aria-expanded'), caseVide.i);
      verifier('un clic n’importe où sur la ligne d’une semaine (ici une case vide, « — ») la déplie', apres === 'true' && caseVide.tiret === '—', JSON.stringify([caseVide, apres]));
    } else verifier('la démonstration a une semaine avec une case vide', false);
    await cB.close();

    // --- 9. Le journal vide : un bloc calme, sa phrase et son explication ; la recherche s'efface.
    const cV = await contexte();
    const qV = await page(cV, 'lot B vide');
    const vide = await qV.evaluate(() => {
      const s = window.__jeuDExemple('HDK'); s.releves = s.releves.slice(-1); window.__chargerSource(s);
      const z = document.getElementById('zone-journal'), e = z.querySelector('.etat-vide'), ph = e && e.querySelector('.etat-vide-phrase');
      return { bloc: !!e, phrase: ph ? ph.textContent : '', police: ph ? getComputedStyle(ph).fontFamily.split(',')[0].replace(/"/g, '') : '', taille: ph ? parseFloat(getComputedStyle(ph).fontSize) : 0,
               detail: (z.querySelector('.etat-vide .journal-vide') || {}).textContent || '', recherche: !!document.getElementById('recherche-journal').offsetParent,
               pastilles: document.querySelectorAll('#filtre-journal button').length };
    });
    verifier('journal vide (un seul relevé) : « Le journal commence au deuxième relevé » en Newsreader 18 px, l’explication dessous ; ni pastille ni recherche, qui n’agiraient sur rien',
      vide.bloc && vide.phrase === 'Le journal commence au deuxième relevé' && vide.police === 'Newsreader' && vide.taille === 18 && /^Un seul relevé archivé/.test(vide.detail) &&
      !vide.recherche && vide.pastilles === 0, JSON.stringify(vide));
    const revient = await qV.evaluate(() => { window.__chargerSource(window.__jeuDExemple('HDK')); return !!document.getElementById('recherche-journal').offsetParent && document.querySelectorAll('#filtre-journal button').length > 3; });
    verifier('l’historique revenu, la recherche et les pastilles reviennent', revient);
    await cV.close();

    // --- 10. Au doigt (téléphone) : 44 px, et seule la semaine se colle.
    const cT = await contexte({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const qT = await page(cT, 'lot B téléphone');
    await qT.evaluate(() => document.querySelector('#zone-journal .journal-plier').click());
    await qT.waitForTimeout(300);
    const doigt = await qT.evaluate(() => {
      const t = document.querySelector('#zone-journal .journal-plier'), p = document.querySelector('#zone-journal .journal-plus');
      const puce = document.querySelector('#filtre-journal .puces-rang button');
      const zone = puce ? parseFloat(getComputedStyle(puce, '::after').top) : 0;
      return { plier: Math.round(t.getBoundingClientRect().height), plus: p ? Math.round(p.getBoundingClientRect().height) : null,
               puce: puce ? Math.round(puce.getBoundingClientRect().height - 2 * zone) : 0 };
    });
    await qT.evaluate(() => { const s = document.querySelector('#zone-journal .journal-semaine'); window.scrollTo(0, s.getBoundingClientRect().top + scrollY + 600); });
    await qT.waitForTimeout(300);
    const colleT = await qT.evaluate(() => {
      const s = document.querySelector('#zone-journal .journal-semaine'), b = s.querySelector('.journal-plier');
      const bas = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bas-sommaire')) || 0;
      return { haut: Math.round(b.getBoundingClientRect().top), bas, hauteur: Math.round(b.getBoundingClientRect().height), page: document.documentElement.scrollWidth <= innerWidth };
    });
    verifier('au téléphone : la ligne d’une semaine et « Voir les N autres » font 44 px, chaque pastille offre 44 px à toucher',
      doigt.plier >= 44 && (doigt.plus === null || doigt.plus >= 44) && doigt.puce >= 44, JSON.stringify(doigt));
    verifier('au téléphone, en lisant une semaine ouverte : seul son nom reste collé sous le sommaire (une ligne, pas ses sept comptes), sans débord de la page',
      Math.abs(colleT.haut - colleT.bas) <= 1 && colleT.hauteur <= 60 && colleT.page, JSON.stringify(colleT));
    await cT.close();

    // --- 11. Sombre : les dates, les étages de l'en-tête et les reculs se lisent (4,5:1).
    const cS = await contexte({ colorScheme: 'dark', viewport: { width: 1440, height: 950 } });
    const qS = await page(cS, 'lot B sombre');
    await qS.evaluate(outils);
    const sombre = await qS.evaluate(() => {
      const fond = getComputedStyle(document.getElementById('section-journal')).backgroundColor;
      const c = sel => { const e = document.querySelector(sel); return e ? +window.__contraste(getComputedStyle(e).color, fond).toFixed(2) : 0; };
      return { dates: c('#zone-journal .sem-dates'), groupe: c('#zone-journal .entete-groupe'), mot: c('#filtre-journal .mot-rang'), reculs: c('#filtre-journal button[data-journal="reculs"] .n'),
               tiret: c('#zone-journal .case-vide .tiret-vide'), code: c('#zone-journal .entete-col') };
    });
    verifier('en sombre, dates des semaines, étages de l’en-tête, titres des rangées, reculs et tirets se lisent à 4,5:1 au moins',
      Object.values(sombre).every(v => v >= 4.5), JSON.stringify(sombre));
    await cS.close();
  }

  // =================================================================
  /* Débrief 27, lot F — l'administration, sur la page VIVANTE : le vrai
     Code.gs (le simulateur, tests/construire-simulateur.js) répond derrière
     google.script.run, comme au banc d'essai de la revue d'expérience
     (droits, jalons, contrats, administrateurs). Le responsable
     (nathan@airbus.com), une administratrice d'un seul contrat
     (anne@airbus.com) et un lecteur. Placée en dernier : le simulateur fixe
     le fuseau du processus (Europe/Paris). */
  section('Débrief 27 : administration (lot F)');
  {
    const fs27 = require('fs'), os27 = require('os');
    const outilsCouleur27 = () => {
      window.__lum = c => {
        const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
        return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
      };
      window.__contraste = (a, b) => { const x = window.__lum(a), y = window.__lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    };
    const { construireSimulateur } = require(path.join(__dirname, '..', '..', 'tests', 'construire-simulateur.js'));
    const { Feuille } = require(path.join(__dirname, '..', '..', 'tests', 'faux-classeur.js'));
    /* Comme chez Nathan : une tranche, « HDK Tranche 2 ». */
    const sim = construireSimulateur({ date: '2026-10-29', avantPage: function (c, classeur) {
      const ths = classeur.getSheetByName('THS');
      classeur.feuilles.splice(1, 0, new Feuille('HDK Tranche 2', ths.valeurs.map(l => l.slice()), false, ths.fusions.map(f => Object.assign({}, f))));
    } });
    const srv = sim.contexte;
    sim.classeur.proprietaire = 'nathan@airbus.com';
    srv.__emailScript = 'nathan@airbus.com';
    const fichier27 = path.join(os27.tmpdir(), 'suivi-fwd-admin-' + process.pid + '.html');
    fs27.writeFileSync(fichier27, sim.page.replace(/<script>\s*\/\* Simulateur : google\.script\.run[\s\S]*?<\/script>/, ''));
    const commeQui = (email, fn) => { const avant = srv.__emailLecteur; srv.__emailLecteur = email; try { return fn(); } finally { srv.__emailLecteur = avant; } };
    const vivante = async (o) => {
      const c = await nav.newContext({ viewport: { width: o.largeur || 1280, height: o.hauteur || 900 }, colorScheme: o.schema || 'light',
        isMobile: !!o.mobile, hasTouch: !!o.mobile, locale: 'en-US', reducedMotion: o.reducedMotion || 'no-preference' });
      const pg = await c.newPage();
      brancher(pg, 'administration ' + o.email);
      await pg.exposeFunction('__appel', (nom, args) => {
        if (typeof srv[nom] !== 'function' || /_$/.test(nom)) throw new Error('fonction inconnue ' + nom);
        return commeQui(o.email, () => { const r = srv[nom].apply(null, JSON.parse(args)); return JSON.stringify(r === undefined ? null : r); });
      });
      await pg.addInitScript(lent => {
        window.SUIVI_FWD_BUDGET = 1e9;
        function chaine(ok, ko) {
          const c = { withSuccessHandler: f => chaine(f, ko), withFailureHandler: f => chaine(ok, f), withUserObject: () => chaine(ok, ko) };
          return new Proxy(c, { get(t, nom) {
            if (nom in t) return t[nom];
            if (typeof nom !== 'string') return undefined;
            return function () {
              const args = Array.prototype.slice.call(arguments);
              setTimeout(() => window.__appel(nom, JSON.stringify(args)).then(j => { if (ok) ok(JSON.parse(j)); },
                e => { if (ko) ko({ message: String(e.message || e).replace(/^Error: /, '') }); }), lent);
            };
          } });
        }
        window.google = { script: { run: chaine(null, null) } };
      }, o.latence === undefined ? 40 : o.latence);
      await pg.goto('file://' + fichier27);
      await pg.waitForFunction(() => document.documentElement.getAttribute('data-suivi-fwd') === 'pret', null, { timeout: 30000 });
      /* Les droits arrivent après l'ouverture (mesDroits) : le bouton
         Administration paraît, ou le pied nomme le responsable. */
      await pg.waitForFunction(() => {
        const b = document.getElementById('ouvrir-admin');
        const vu = b && b.getClientRects().length && getComputedStyle(b).visibility !== 'hidden';
        return vu || (document.getElementById('pied-responsable') || {}).textContent;
      }, null, { timeout: 20000 }).catch(() => {});
      pg.__ctx = c;
      return pg;
    };
    const lire = (pg, s) => pg.evaluate(s => { const e = document.querySelector(s); return e ? e.textContent.trim() : null; }, s);
    const rect = (pg, s) => pg.evaluate(s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, b: r.bottom }; }, s);
    const message = pg => pg.evaluate(() => { const m = document.getElementById('admin-message'); return { classe: m.className, texte: (m.querySelector('.admin-message-texte') || m).textContent, bouton: (m.querySelector('button') || {}).textContent || '' }; });
    const actif = pg => pg.evaluate(() => { const a = document.activeElement; return a ? (a.getAttribute('aria-label') || a.getAttribute('data-admin') || a.getAttribute('data-message') || a.name || a.id || a.tagName) : ''; });
    const libre = pg => pg.waitForFunction(() => document.getElementById('admin').getAttribute('aria-busy') !== 'true', null, { timeout: 15000 }).catch(() => {});
    const onglet = async (pg, o) => { await pg.click('#admin-onglets [data-onglet="' + o + '"]'); await libre(pg); };
    const lignes = pg => pg.evaluate(() => [...document.querySelectorAll('#admin-corps table tbody tr:not(.admin-confirmation)')].map(tr => tr.innerText.replace(/\s+/g, ' ').trim()));

    const np = await vivante({ email: 'nathan@airbus.com' });
    await np.click('#ouvrir-admin'); await libre(np);
    await np.waitForSelector('#admin-corps table.admin-jalons', { timeout: 15000 }).catch(() => {});
    /* A-F16, B17 : calé en haut, des onglets soulignés. */
    const hauts = [(await rect(np, '#admin')).y];
    const tete = await np.evaluate(() => {
      const t = document.getElementById('admin-onglets'), sel = t.querySelector('[aria-selected="true"]'), s = getComputedStyle(sel);
      return { role: t.getAttribute('role'), onglets: [...t.querySelectorAll('[role="tab"]')].filter(b => !b.hidden).map(b => b.textContent), trait: s.borderBottomWidth + ' ' + s.borderBottomStyle,
               traitCouleur: s.borderBottomColor, couleur: s.color, fond: s.backgroundColor, panneau: document.getElementById('admin-corps').getAttribute('role'),
               titre: (document.getElementById('admin-jalons-titre') || {}).textContent };
    });
    await np.click('[data-admin="ajouter"]'); hauts.push((await rect(np, '#admin')).y);
    await np.click('[data-admin="annuler"]');
    await onglet(np, 'contrats'); hauts.push((await rect(np, '#admin')).y);
    await onglet(np, 'admins'); hauts.push((await rect(np, '#admin')).y);
    await onglet(np, 'jalons');
    verifier('le panneau d\'administration est calé en haut : il ne bouge plus d\'un onglet à l\'autre, ni quand le formulaire s\'ouvre (A-F16)',
      hauts.every(h => Math.abs(h - hauts[0]) < 1) && hauts[0] < 120, JSON.stringify(hauts));
    verifier('de vrais onglets soulignés (B17) : tablist / tab / tabpanel, l\'onglet ouvert à l\'encre sur un trait de 2 px, sans pastille',
      tete.role === 'tablist' && tete.panneau === 'tabpanel' && tete.onglets.join() === 'Jalons,Contrats,Administrateurs' && tete.trait === '2px solid' &&
      tete.traitCouleur === tete.couleur && tete.fond === 'rgba(0, 0, 0, 0)', JSON.stringify(tete));
    verifier('l\'onglet Jalons dit quel contrat il liste, en nom complet : « Jalons de HDK › Tranche 1 » (A-F17, A-F10)', tete.titre === 'Jalons de HDK › Tranche 1', tete.titre);
    /* X-A13 : les icônes nommées par leur jalon, la colonne d'actions nommée. */
    const noms = await np.evaluate(() => ({
      modifier: [...document.querySelectorAll('#admin-corps [data-admin="modifier"]')].map(b => b.getAttribute('aria-label')),
      supprimer: [...document.querySelectorAll('#admin-corps [data-admin="supprimer"]')].map(b => b.getAttribute('aria-label')),
      thVides: [...document.querySelectorAll('#admin-corps th')].filter(t => !t.textContent.trim()).length,
      avancement: [...document.querySelectorAll('#admin-corps td[data-titre="Avancement"]')].map(t => t.textContent),
      pour: [...document.querySelectorAll('#admin-corps td[data-titre="Pour"]')].map(t => t.textContent)
    }));
    verifier('« Modifier » et « Supprimer » sont des icônes nommées par leur jalon (« Modifier le jalon Solde FWD du 15/12/2026 »), la colonne d\'actions a un nom (X-A13)',
      noms.modifier.length >= 3 && noms.modifier.every(n => /^Modifier le jalon .+ du \d\d\/\d\d\/\d{4}$/.test(n)) && new Set(noms.modifier).size === noms.modifier.length &&
      noms.supprimer.every(n => /^Supprimer le jalon /.test(n)) && noms.thVides === 0, JSON.stringify(noms).slice(0, 400));
    verifier('la liste dit « Définition électrique » (plus « FWD ») et « HDK › Tranche 1 » (plus « HDK ») (A-F18, A-F10)',
      noms.avancement.every(a => a === 'Définition électrique' || a === 'Concept harnais') && noms.pour.every(p => p === 'HDK › Tranche 1'), JSON.stringify(noms.avancement.concat(noms.pour)));

    /* A-F7, A-F8, A-F15 : les messages sous les champs. */
    await np.click('[data-admin="ajouter"]');
    const options = await np.evaluate(() => [...document.querySelectorAll('#admin-pour option')].map(o => o.textContent));
    verifier('« Pour » nomme chaque onglet en entier et marque celui à l\'écran : « HDK › Tranche 1 (à l\'écran) », « HDK › Tranche 2 », « THS » (A-F10)',
      options[0] === 'HDK › Tranche 1 (à l’écran)' && options.indexOf('HDK › Tranche 2') !== -1 && options.indexOf('THS') !== -1, JSON.stringify(options));
    await np.click('form[data-form="jalon"] [type="submit"]');
    const vide = await np.evaluate(() => ({ texte: document.getElementById('admin-texte-msg').textContent, date: document.getElementById('admin-date-msg').textContent,
      invalides: [...document.querySelectorAll('form[data-form="jalon"] [aria-invalid="true"]')].map(e => e.name), lie: document.getElementById('admin-texte').getAttribute('aria-describedby'),
      focus: document.activeElement.name, general: document.getElementById('admin-message').textContent }));
    verifier('formulaire vide : chaque champ dit sous lui ce qui manque (relié par aria-describedby), le premier prend le focus, rien en haut (A-F7)',
      vide.texte === 'Donnez un nom au jalon (par exemple « Solde FWD »).' && vide.date === 'Choisissez la date du jalon.' && vide.invalides.join() === 'texte,date' &&
      /admin-texte-msg/.test(vide.lie) && vide.focus === 'texte' && !vide.general, JSON.stringify(vide));
    await np.click('#admin-date'); await np.keyboard.press('Home'); await np.keyboard.type('02312027');
    await np.click('form[data-form="jalon"] [type="submit"]');
    const impossible = await lire(np, '#admin-date-msg');
    await np.fill('#admin-date', '2199-05-01');
    await np.click('form[data-form="jalon"] [type="submit"]');
    const an2199 = await lire(np, '#admin-date-msg');
    verifier('un 31 février : « Cette date n\'existe pas » ; l\'an 2199 : « L\'année 2199 semble erronée… » (A-F7)',
      impossible === 'Cette date n’existe pas. Choisissez un jour du calendrier.' && an2199 === 'L’année 2199 semble erronée : choisissez une date entre 2000 et 2100.',
      impossible + ' / ' + an2199);
    await np.click('#admin-texte');
    await np.keyboard.insertText('Livraison des planches du lot avionique numéro un pour la revue de conception critique '.repeat(4));
    await np.waitForFunction(() => document.getElementById('admin-texte-msg').textContent, null, { timeout: 3000 }).catch(() => {});
    const long = await np.evaluate(() => ({ n: document.getElementById('admin-texte').value.length, msg: document.getElementById('admin-texte-msg').textContent,
      compte: document.getElementById('admin-texte-compte').textContent }));
    verifier('un nom collé trop long : coupé à 60, et dit (« Nom raccourci à 60 caractères… »), le compte « 60 / 60 caractères » (A-F8)',
      long.n === 60 && long.msg === 'Nom raccourci à 60 caractères : un nom court se lit mieux sur le graphique.' && long.compte === '60 / 60 caractères', JSON.stringify(long));
    await np.fill('#admin-texte', 'Revue passée');
    await np.fill('#admin-date', '2025-03-01');
    const passe = await np.evaluate(() => { const m = document.getElementById('admin-date-msg'); return { texte: m.textContent, classe: m.className, compte: document.getElementById('admin-texte-compte').textContent }; });
    verifier('en tapant : le compte suit (« 12 / 60 caractères »), une date passée se signale sans bloquer (A-F8, A-F15)',
      passe.compte === '12 / 60 caractères' && passe.texte === 'Cette date est déjà passée : le jalon sera listé en gris, sans repère sur le graphique.' && /avertissement/.test(passe.classe), JSON.stringify(passe));
    await np.click('form[data-form="jalon"] [type="submit"]'); await libre(np);
    const msgPasse = await message(np);
    verifier('un jalon passé enregistré : le message le dit au lieu de « il est sur le graphique » (A-F15)',
      /^Jalon « Revue passée » enregistré \(date passée\) : il est listé en gris, sans repère sur le graphique\.$/.test(msgPasse.texte) && /ok/.test(msgPasse.classe), JSON.stringify(msgPasse));

    /* A-F1 : un jalon pour une autre tranche ne disparaît plus. */
    await np.click('[data-admin="ajouter"]');
    await np.fill('#admin-texte', 'Revue T2'); await np.fill('#admin-date', '2026-12-10');
    await np.selectOption('#admin-pour', 'HDK Tranche 2');
    await np.click('form[data-form="jalon"] [type="submit"]'); await libre(np);
    const t2 = await np.evaluate(() => ({ titre: document.getElementById('admin-jalons-titre').textContent,
      recent: [...document.querySelectorAll('#admin-corps tr.recent')].map(t => t.innerText.replace(/\s+/g, ' ')), focus: document.activeElement.getAttribute('aria-label') }));
    const msgT2 = await message(np);
    verifier('un jalon pour une autre tranche reste sous les yeux : la liste passe à « Jalons de HDK › Tranche 2 », sa ligne s\'éclaire, le focus la suit (A-F1)',
      t2.titre === 'Jalons de HDK › Tranche 2' && t2.recent.length === 1 && /Revue T2/.test(t2.recent[0]) && t2.focus === 'Modifier le jalon Revue T2 du 10/12/2026', JSON.stringify(t2));
    verifier('… et le message dit où il est, sans prétendre qu\'il est sur le graphique à l\'écran, avec « Afficher HDK › Tranche 2 » (A-F1)',
      msgT2.texte === 'Jalon « Revue T2 » enregistré pour HDK › Tranche 2. Il apparaît sur le graphique de cette tranche.' && msgT2.bouton === 'Afficher HDK › Tranche 2', JSON.stringify(msgT2));

    /* Le même jalon une seconde fois : refusé sous le nom, plutôt qu'un doublon. */
    await np.click('[data-admin="ajouter"]');
    await np.fill('#admin-texte', 'Revue T2'); await np.fill('#admin-date', '2026-12-10');
    await np.selectOption('#admin-pour', 'HDK Tranche 2');
    await np.click('form[data-form="jalon"] [type="submit"]'); await libre(np);
    const doublon = await np.evaluate(() => ({ msg: (document.getElementById('admin-texte-msg') || {}).textContent, focus: document.activeElement.name,
      lignes: [...document.querySelectorAll('#admin-corps tr[data-cle]')].filter(t => /Revue T2/.test(t.innerText)).length }));
    verifier('le même jalon une seconde fois : « Ce jalon existe déjà… » sous le nom, rien d\'écrit (le doublon qu\'on créait en croyant le premier perdu)',
      doublon.msg === 'Ce jalon existe déjà : « Revue T2 », le 10/12/2026, pour HDK › Tranche 2.' && doublon.focus === 'texte' && doublon.lignes === 1, JSON.stringify(doublon));
    await np.click('[data-admin="annuler"]');

    /* A-F2, A-F19 : la suppression ne se confirme pas d'un double-clic, et s'annule. */
    const corbeille = await rect(np, '#admin-corps tr.recent [data-admin="supprimer"], #admin-corps tr[data-cle] [data-admin="supprimer"]');
    await np.mouse.dblclick(corbeille.x + corbeille.w / 2, corbeille.y + corbeille.h / 2);
    await np.evaluate(() => { const o = document.querySelector('[data-admin="supprimer-oui"]'); if (o) o.click(); });
    await np.waitForTimeout(150);
    const apresDouble = await np.evaluate(() => ({ question: (document.querySelector('.admin-confirmation .admin-question-texte') || {}).textContent || '',
      lignes: document.querySelectorAll('#admin-corps tr[data-cle]').length, focus: document.activeElement.getAttribute('data-admin') }));
    verifier('double-clic sur la corbeille, puis « Oui » aussitôt : rien n\'est supprimé — la question attend, sous la ligne (A-F2)',
      /^Supprimer « Revue T2 du 10\/12\/2026 » \? Il disparaît du graphique pour tout le monde\.$/.test(apresDouble.question) && apresDouble.lignes === 1, JSON.stringify(apresDouble));
    await np.waitForTimeout(450);
    await np.click('[data-admin="supprimer-oui"]'); await libre(np);
    await np.waitForFunction(() => document.querySelector('#admin-message button[data-message]'), null, { timeout: 10000 }).catch(() => {});
    const supprime = await message(np);
    const focusAnnuler = await actif(np);
    verifier('supprimé : « Jalon « Revue T2 » supprimé. » et le bouton « Annuler la suppression », qui prend le focus (A-F19)',
      supprime.texte === 'Jalon « Revue T2 » supprimé.' && supprime.bouton === 'Annuler la suppression' && focusAnnuler === 'retablir' &&
      !(await lignes(np)).some(l => /Revue T2/.test(l)), JSON.stringify({ supprime, focusAnnuler }));
    await np.waitForTimeout(450);
    await np.click('#admin-message button[data-message]'); await libre(np);
    await np.waitForFunction(() => /rétabli/.test(document.getElementById('admin-message').textContent), null, { timeout: 10000 }).catch(() => {});
    verifier('« Annuler la suppression » réécrit le jalon tel qu\'il était (A-F19)',
      (await message(np)).texte === 'Jalon « Revue T2 » rétabli.' && (await lignes(np)).some(l => /10\/12\/2026 Revue T2/.test(l)), JSON.stringify(await lignes(np)));

    /* A-F6, A-F17 : une saisie ne se perd plus en silence. */
    await np.click('[data-admin="ajouter"]');
    await np.fill('#admin-texte', 'Saisie en cours');
    await np.keyboard.press('Escape'); await np.waitForTimeout(150);
    const echap1 = await np.evaluate(() => ({ ouvert: document.getElementById('admin').open, garde: (document.querySelector('.admin-garde .admin-question-texte') || {}).textContent, focus: document.activeElement.getAttribute('data-admin') }));
    await np.keyboard.press('Escape'); await np.waitForTimeout(150);
    const echap2 = await np.evaluate(() => ({ ouvert: document.getElementById('admin').open, garde: !!document.querySelector('.admin-garde'), valeur: document.getElementById('admin-texte').value, focus: document.activeElement.name }));
    verifier('Échap pendant une saisie : le panneau reste, et demande « Abandonner ce jalon non enregistré ? » ; Échap encore : on continue, rien de perdu (A-F6)',
      echap1.ouvert && echap1.garde === 'Abandonner ce jalon non enregistré ?' && echap1.focus === 'garde-continuer' &&
      echap2.ouvert && !echap2.garde && echap2.valeur === 'Saisie en cours' && echap2.focus === 'texte', JSON.stringify({ echap1, echap2 }));
    await np.mouse.click(8, 450); await np.waitForTimeout(150);
    const voile = await np.evaluate(() => ({ ouvert: document.getElementById('admin').open, garde: !!document.querySelector('.admin-garde') }));
    await np.click('[data-admin="garde-continuer"]');
    const autres = await np.$$('#admin-corps tr[data-cle] [data-admin="modifier"]');
    await autres[0].click(); await np.waitForTimeout(100);
    const garde2 = await np.evaluate(() => !!document.querySelector('.admin-garde'));
    verifier('un clic sur le voile, ou « Modifier » sur une autre ligne, pendant une saisie : la même question d\'abord (A-F6)', voile.ouvert && voile.garde && garde2, JSON.stringify({ voile, garde2 }));
    await np.click('[data-admin="garde-abandonner"]');
    const edite = await np.evaluate(() => ({ titre: document.getElementById('admin-form-titre').textContent, nom: document.getElementById('admin-texte').value,
      ligne: [...document.querySelectorAll('#admin-corps tr.en-cours')].map(t => ({ texte: t.innerText.replace(/\s+/g, ' '), actions: t.querySelectorAll('.actions button').length })) }));
    verifier('abandonné, « Modifier » ouvre ce jalon-là — son nom, pas la saisie d\'avant — ; sa ligne est voilée, marquée « en cours de modification », sans boutons (A-F17)',
      /^Modifier « .+ »$/.test(edite.titre) && edite.titre === 'Modifier « ' + edite.nom + ' »' && edite.ligne.length === 1 &&
      /en cours de modification/.test(edite.ligne[0].texte) && edite.ligne[0].actions === 0, JSON.stringify(edite));
    await np.click('[data-admin="annuler"]');
    /* Abandonner puis fermer : la saisie n'est plus là à la réouverture. */
    await np.click('[data-admin="ajouter"]'); await np.fill('#admin-texte', 'À jeter');
    await np.click('#admin-fermer'); await np.click('[data-admin="garde-abandonner"]'); await np.waitForTimeout(150);
    const ferme = await np.evaluate(() => !document.getElementById('admin').open && !document.documentElement.classList.contains('admin-ouvert'));
    await np.click('#ouvrir-admin'); await libre(np);
    const rouvert = await np.evaluate(() => !document.querySelector('form[data-form="jalon"]'));
    verifier('« Abandonner » depuis × ferme vraiment, et la saisie jetée ne revient pas', ferme && rouvert, JSON.stringify({ ferme, rouvert }));

    /* A-F3, A-F22, A-F2 : les contrats — un tableau, masquer sans peur. */
    await onglet(np, 'contrats');
    const contrats = await np.evaluate(() => ({ entetes: [...document.querySelectorAll('#admin-corps thead th')].map(t => t.textContent.trim()),
      tables: document.querySelectorAll('#admin-corps table').length,
      lignes: [...document.querySelectorAll('#admin-corps tbody tr[data-id]')].map(tr => [...tr.cells].map(td => td.textContent.trim())) }));
    verifier('Contrats : un seul tableau avec sa colonne « État » ; « Tranche 1 » plutôt que « — » ; « Masquer du tableau de bord » (A-F22, A-F10, A-F3)',
      contrats.tables === 1 && contrats.entetes.slice(0, 3).join() === 'Contrat,Tranche,État' &&
      JSON.stringify(contrats.lignes) === JSON.stringify([['HDK', 'Tranche 1', 'Visible (à l’écran)', 'Masquer du tableau de bord'], ['HDK', 'Tranche 2', 'Visible', 'Masquer du tableau de bord'], ['THS', '—', 'Visible', 'Masquer du tableau de bord']]),
      JSON.stringify(contrats));
    const lienThs = await rect(np, '[data-admin="masquer"][data-id="THS"]');
    await np.mouse.dblclick(lienThs.x + lienThs.w - 6, lienThs.y + lienThs.h / 2);
    await np.evaluate(() => { const o = document.querySelector('[data-admin="masquer-oui"]'); if (o) o.click(); });
    await np.waitForTimeout(150);
    const questionThs = await lire(np, '.admin-confirmation .admin-question-texte');
    const encoreLa = commeQui('nathan@airbus.com', () => srv.listerContrats(sim.classeur).some(c => c.id === 'THS'));
    verifier('deux clics rapides sur « Masquer du tableau de bord » ne masquent rien : la question rassure — « Rien n\'est supprimé : vous pourrez le réafficher » (A-F2, A-F3)',
      encoreLa && questionThs === 'Masquer THS pour tout le monde ? Rien n’est supprimé : vous pourrez le réafficher.', questionThs);
    await np.waitForTimeout(450);
    await np.click('[data-admin="masquer-oui"]'); await libre(np);
    await np.waitForFunction(() => /masqué/.test(document.getElementById('admin-message').textContent), null, { timeout: 10000 }).catch(() => {});
    const masque = await message(np);
    const focusMasque = await actif(np);
    const etatThs = await np.evaluate(() => { const tr = document.querySelector('#admin-corps tr[data-id="THS"]'); return tr ? tr.cells[2].textContent.trim() : null; });
    verifier('masqué : « THS est masqué pour tout le monde. » avec [Réafficher] ; la ligne dit « Masqué », le focus va à son « Réafficher » (A-F3)',
      masque.texte === 'THS est masqué pour tout le monde.' && masque.bouton === 'Réafficher' && etatThs === 'Masqué' && focusMasque === 'Réafficher : THS',
      JSON.stringify({ masque, etatThs, focusMasque }));
    await np.waitForTimeout(450);
    await np.click('#admin-message button[data-message]'); await libre(np);
    await np.waitForFunction(() => /de nouveau visible/.test(document.getElementById('admin-message').textContent), null, { timeout: 10000 }).catch(() => {});
    verifier('[Réafficher] dans le message remet le contrat, d\'un clic', (await message(np)).texte === 'THS est de nouveau visible sur le tableau de bord.' &&
      commeQui('nathan@airbus.com', () => srv.listerContrats(sim.classeur).some(c => c.id === 'THS')), JSON.stringify(await message(np)));

    /* A-F9 : nommer un administrateur. */
    await onglet(np, 'admins');
    const nommer = async (email, choix) => {
      await np.fill('#admin-email', email);
      if (choix !== undefined) await np.selectOption('#admin-contrat', choix);
      await np.click('form[data-form="admin"] [type="submit"]'); await libre(np);
      return np.evaluate(() => ({ email: document.getElementById('admin-email-msg').textContent, contrat: document.getElementById('admin-contrat-msg').textContent,
        ok: document.getElementById('admin-message').textContent, focus: document.activeElement.name }));
    };
    const formAdmin = await np.evaluate(() => ({ libelle: document.querySelector('label[for="admin-contrat"]').textContent,
      options: [...document.querySelectorAll('#admin-contrat option')].map(o => o.textContent), choix: document.getElementById('admin-contrat').value }));
    verifier('« Sur » devient « Contrats qu\'elle ou il peut gérer », qui commence sur « Choisir… » — plus sur « Tous les contrats » ; « HDK (toutes les tranches) » (A-F9, A-F10)',
      formAdmin.libelle === 'Contrats qu’elle ou il peut gérer' && formAdmin.options[0] === 'Choisir…' && formAdmin.choix === '' &&
      formAdmin.options.indexOf('HDK (toutes les tranches)') !== -1, JSON.stringify(formAdmin));
    const nVide = await nommer('');
    const nFaux = await nommer('pas une adresse');
    const nSoi = await nommer('nathan@airbus.com', '*');
    const nSansChoix = await nommer('anne@airbus.com', '');
    verifier('nommer : vide, mal écrite, soi-même, sans choix — chacun son message sous son champ, qui prend le focus (A-F9)',
      nVide.email === 'Saisissez l’adresse Google de la personne.' && nVide.focus === 'email' &&
      nFaux.email === 'Cette adresse n’est pas valide. Exemple : prenom.nom@airbus.com' &&
      nSoi.email === 'Vous êtes le responsable : vous avez déjà tous les droits.' && !nSoi.ok &&
      nSansChoix.contrat === 'Choisissez ce que cette personne pourra gérer.' && nSansChoix.focus === 'contrat', JSON.stringify({ nVide, nFaux, nSoi, nSansChoix }));
    const nBob = await nommer('bob@airbus.com', 'THS');
    const nBobBis = await nommer('bob@airbus.com', 'THS');
    const nBobHdk = await nommer('bob@airbus.com', 'HDK');
    const nAnne = await nommer('anne@airbus.com', 'THS');
    verifier('nommer : « administre maintenant THS », un doublon « rien n\'a changé », un contrat ajouté « administre maintenant THS et HDK (toutes les tranches) » (A-F9)',
      nBob.ok === 'bob@airbus.com administre maintenant THS.' && nBob.focus === 'email' &&
      nBobBis.email === 'bob@airbus.com administre déjà THS : rien n’a changé.' &&
      nBobHdk.ok === 'bob@airbus.com administre maintenant THS et HDK (toutes les tranches).' && nAnne.ok === 'anne@airbus.com administre maintenant THS.',
      JSON.stringify({ nBob, nBobBis, nBobHdk, nAnne }));

    /* A-F20 : un onglet qui ne se lit pas. */
    const vraiContrats = srv.adminContrats;
    srv.adminContrats = function () { throw new Error('Service indisponible'); };
    await onglet(np, 'contrats');
    const echec = await np.evaluate(() => { const a = document.querySelector('#admin-corps .bandeau-alerte'); return a ? { role: a.getAttribute('role'), texte: a.innerText.replace(/\s+/g, ' ') } : null; });
    srv.adminContrats = vraiContrats;
    await np.click('[data-admin="reessayer"]'); await libre(np);
    const reessai = await np.evaluate(() => document.querySelectorAll('#admin-corps tbody tr[data-id]').length);
    verifier('un onglet qui ne se lit pas : un bandeau d\'alerte « Impossible de charger la liste des contrats… » et [Réessayer], qui relit (A-F20)',
      echec && echec.role === 'alert' && /^Impossible de charger la liste des contrats : Service indisponible\. Rien n’a été modifié\. Réessayer$/.test(echec.texte) && reessai === 3,
      JSON.stringify({ echec, reessai }));
    verifier('le pied ne nomme pas le responsable à un administrateur (il a le panneau)', await np.evaluate(() => document.getElementById('pied-responsable').hidden));
    /* A-F1 : « Afficher THS », dans le message, ferme le panneau et montre ce contrat. */
    await onglet(np, 'jalons');
    await np.click('[data-admin="ajouter"]');
    await np.fill('#admin-texte', 'Revue THS'); await np.fill('#admin-date', '2027-02-11');
    await np.selectOption('#admin-pour', 'THS');
    await np.click('form[data-form="jalon"] [type="submit"]'); await libre(np);
    await np.waitForFunction(() => document.querySelector('#admin-message button[data-message]'), null, { timeout: 10000 }).catch(() => {});
    const boutonThs = await lire(np, '#admin-message button[data-message]');
    await np.waitForTimeout(450);
    await np.click('#admin-message button[data-message]');
    await np.waitForFunction(() => !document.getElementById('admin').open && document.getElementById('select-contrat').value === 'THS' && !document.body.hasAttribute('data-attente') &&
      [...document.querySelectorAll('.legende-jalon')].some(e => /Revue THS/.test(e.textContent)), null, { timeout: 20000 }).catch(() => {});
    const versThs = await np.evaluate(() => ({ ouvert: document.getElementById('admin').open, contrat: document.getElementById('select-contrat').value,
      verrou: document.documentElement.classList.contains('admin-ouvert'), jalon: [...document.querySelectorAll('.legende-jalon')].some(e => /Revue THS/.test(e.textContent)) }));
    verifier('« Afficher THS », dans le message, ferme le panneau et montre THS, le jalon sur son graphique (A-F1)',
      boutonThs === 'Afficher THS' && !versThs.ouvert && versThs.contrat === 'THS' && !versThs.verrou && versThs.jalon, JSON.stringify({ boutonThs, versThs }));

    /* A-F11, A-F12 : Anne, administratrice de THS seulement. */
    const ap = await vivante({ email: 'anne@airbus.com' });
    await ap.click('#ouvrir-admin'); await libre(ap);
    await ap.waitForSelector('#admin-jalons-titre', { timeout: 15000 }).catch(() => {});
    const anne = await ap.evaluate(() => ({ qui: document.getElementById('admin-qui').textContent, portee: document.getElementById('admin-portee').textContent,
      onglets: document.getElementById('admin-onglets').hidden, titre: document.getElementById('admin-jalons-titre').textContent }));
    verifier('une administratrice de THS lit ce qu\'elle peut faire ; le panneau s\'ouvre sur ses jalons, sans les onglets qui ne la concernent pas (A-F11)',
      anne.qui === 'Administrateur de THS · anne@airbus.com' && anne.portee === 'Vous pouvez ajouter et modifier les jalons de THS. Les autres jalons sont en lecture seule.' &&
      anne.onglets === true && anne.titre === 'Jalons de THS', JSON.stringify(anne));
    await ap.check('[data-admin="tous-jalons"]');
    const lecture = await ap.evaluate(() => [...document.querySelectorAll('#admin-corps tr[data-cle]')].filter(tr => /HDK/.test(tr.innerText))
      .map(tr => ({ pour: tr.querySelector('td[data-titre="Pour"]').textContent, raison: (tr.querySelector('.admin-lecture') || {}).textContent, boutons: tr.querySelectorAll('.actions button').length })));
    verifier('… les jalons de HDK y sont « lecture seule », sans bouton, et la raison se lit (« réservé aux administrateurs de HDK › Tranche 1 ») (A-F11)',
      lecture.length >= 3 && lecture.every(l => l.raison === 'lecture seule : réservé aux administrateurs de ' + l.pour && l.boutons === 0), JSON.stringify(lecture.slice(0, 3)));
    await ap.uncheck('[data-admin="tous-jalons"]');
    await ap.click('[data-admin="ajouter"]');
    await ap.fill('#admin-texte', 'Revue THS 2'); await ap.fill('#admin-date', '2026-12-17');
    commeQui('nathan@airbus.com', () => srv.adminEnregistrerAdmins(srv.adminListeAdmins().admins.filter(a => a.email !== 'anne@airbus.com')));
    await ap.click('form[data-form="jalon"] [type="submit"]');
    await ap.waitForFunction(() => /retirés entre-temps/.test(document.getElementById('admin-message').textContent), null, { timeout: 15000 }).catch(() => {});
    const refus = await ap.evaluate(() => ({ msg: document.getElementById('admin-message').textContent, qui: document.getElementById('admin-qui').textContent,
      nom: (document.getElementById('admin-texte') || {}).value, lectureSeule: (document.getElementById('admin-texte') || {}).readOnly, envoyer: !!document.querySelector('form[data-form="jalon"] [type="submit"]') }));
    verifier('droits retirés en chemin : on le dit (« Vos droits d\'administration ont été retirés entre-temps… écrivez à nathan@airbus.com »), la tête dit « Lecture seule », la saisie reste lisible (A-F12)',
      refus.msg === 'Vos droits d’administration ont été retirés entre-temps. Votre jalon « Revue THS 2 » n’a pas été enregistré. Pour retrouver ces droits, écrivez à nathan@airbus.com.' &&
      refus.qui === 'Lecture seule · anne@airbus.com' && refus.nom === 'Revue THS 2' && refus.lectureSeule === true && !refus.envoyer, JSON.stringify(refus));
    await ap.__ctx.close();

    /* A-F23 : un lecteur apprend qui gère les jalons. */
    const lp = await vivante({ email: 'lecteur@airbus.com' });
    const pied = await lp.evaluate(() => { const z = document.getElementById('pied-responsable'); const a = z.querySelector('a'); return { vu: !z.hidden, texte: z.textContent, lien: a ? a.getAttribute('href') : '' }; });
    verifier('un lecteur lit au pied qui gère les jalons et comment le joindre (A-F23)',
      pied.vu && pied.texte === 'Jalons et contrats gérés par nathan@airbus.com — pour proposer un jalon ou demander des droits, écrivez-lui.' && pied.lien === 'mailto:nathan@airbus.com',
      JSON.stringify(pied));
    await lp.__ctx.close();

    /* Le serveur dit les mêmes mots (Code.gs). */
    const lecteurDroits = commeQui('lecteur@airbus.com', () => srv.mesDroits());
    let refusSrv = '', anSrv = '', masqueSrv = '';
    commeQui('lecteur@airbus.com', () => { try { srv.adminEnregistrerJalon({ texte: 'x', date: '2027-01-01', contrats: [] }, 'HDK'); } catch (e) { refusSrv = e.message; } });
    commeQui('nathan@airbus.com', () => {
      try { srv.adminEnregistrerJalon({ texte: 'x', date: '2199-01-01', contrats: [] }, 'HDK'); } catch (e) { anSrv = e.message; }
      srv.adminRetirerContrat('THS', true);
      try { srv.getFeuilleDonnees(sim.classeur, 'THS'); } catch (e) { masqueSrv = e.message; }
      srv.adminRetirerContrat('THS', false);
    });
    verifier('serveur : un lecteur identifié apprend le responsable ; le refus dit « Pour l\'obtenir, écrivez à… » ; l\'an 2199 et un contrat masqué entre-temps se disent en clair (A-F12, A-F7, A-F21, A-F23)',
      lecteurDroits.role === 'lecteur' && lecteurDroits.responsable === 'nathan@airbus.com' &&
      /^\[droits\] Réservé aux administrateurs : votre compte \(lecteur@airbus\.com\) n’a pas ce droit\. Pour l’obtenir, écrivez à nathan@airbus\.com\.$/.test(refusSrv) &&
      anSrv === 'L’année 2199 semble erronée : choisissez une date entre 2000 et 2100.' &&
      masqueSrv === '« THS » n’est plus affiché sur le tableau de bord (masqué par un administrateur). Rechargez la page pour mettre la liste à jour.',
      JSON.stringify({ lecteurDroits: lecteurDroits.responsable, refusSrv, anSrv, masqueSrv }));
    await np.__ctx.close();

    /* A-F20 : « Enregistrement… » pendant l'envoi ; le trait de chargement immobile si l'on préfère moins d'animation. */
    const lente = await vivante({ email: 'nathan@airbus.com', latence: 900, reducedMotion: 'reduce' });
    await lente.click('#ouvrir-admin'); await libre(lente);
    await lente.click('[data-admin="ajouter"]');
    await lente.fill('#admin-texte', 'Jalon lent'); await lente.fill('#admin-date', '2027-01-08');
    await lente.click('form[data-form="jalon"] [type="submit"]');
    const enCours = await lente.evaluate(() => { const b = document.querySelector('form[data-form="jalon"] [type="submit"]'), d = document.getElementById('admin');
      return { texte: b && b.textContent, occupe: d.getAttribute('aria-busy'), anim: getComputedStyle(d, '::before').animationName }; });
    await libre(lente);
    verifier('pendant l\'enregistrement, le bouton dit « Enregistrement… », le panneau est occupé ; sans animation si on la refuse (A-F20, D8)',
      enCours.texte === 'Enregistrement…' && enCours.occupe === 'true' && enCours.anim === 'none', JSON.stringify(enCours));
    await lente.__ctx.close();

    /* A-F24 : le sombre. */
    const sp = await vivante({ email: 'nathan@airbus.com', schema: 'dark' });
    await sp.click('#ouvrir-admin'); await libre(sp);
    await sp.mouse.move(4, 4);
    await sp.evaluate(outilsCouleur27);
    const sombre = await sp.evaluate(() => {
      const b = document.querySelector('[data-admin="ajouter"]'), t = document.querySelector('#admin-onglets [aria-selected="true"]'), autre = document.querySelector('#admin-onglets [aria-selected="false"]:not([hidden])');
      const fond = getComputedStyle(document.getElementById('admin')).backgroundColor, sb = getComputedStyle(b), st = getComputedStyle(t);
      return { bouton: sb.backgroundColor, boutonEncre: window.__contraste(sb.color, sb.backgroundColor), boutonFond: window.__contraste(sb.backgroundColor, fond),
               onglet: window.__contraste(st.color, fond), trait: st.borderBottomColor === st.color && st.borderBottomWidth === '2px', autre: window.__contraste(getComputedStyle(autre).color, fond) };
    });
    verifier('sombre : l\'action principale est un aplat clair au texte sombre, qui se voit ; l\'onglet ouvert à l\'encre sur son trait, les autres ≥ 4,5:1 (A-F24)',
      sombre.bouton === 'rgb(241, 240, 234)' && sombre.boutonEncre >= 7 && sombre.boutonFond >= 7 && sombre.onglet >= 7 && sombre.trait && sombre.autre >= 4.5, JSON.stringify(sombre));
    await sp.__ctx.close();

    /* M8, M7, D11 : le téléphone. */
    const tp = await vivante({ email: 'nathan@airbus.com', largeur: 390, hauteur: 844, mobile: true });
    await tp.click('#ouvrir-admin'); await libre(tp);
    await tp.waitForSelector('#admin-corps table.admin-jalons', { timeout: 15000 }).catch(() => {});
    const tel = await tp.evaluate(() => {
      const d = document.getElementById('admin').getBoundingClientRect();
      const cibles = [...document.querySelectorAll('#admin [role="tab"]:not([hidden]), #admin-corps button, #admin-corps .admin-coche')].filter(e => e.getClientRects().length)
        .map(e => { const r = e.getBoundingClientRect(); const a = getComputedStyle(e, '::after'); return { quoi: e.getAttribute('data-admin') || e.textContent.trim().slice(0, 12), h: Math.round(r.height), w: Math.round(r.width) }; });
      return { plein: Math.round(d.left) === 0 && Math.round(d.top) === 0 && Math.round(d.width) === innerWidth && Math.round(d.height) === innerHeight,
               verrou: getComputedStyle(document.documentElement).overflow, petites: cibles.filter(c => c.h < 44 || c.w < 44) };
    });
    const y0 = await tp.evaluate(() => scrollY);
    await tp.mouse.move(195, 600);
    for (let i = 0; i < 5; i++) { await tp.mouse.wheel(0, 700); await tp.waitForTimeout(40); }
    const y1 = await tp.evaluate(() => scrollY);
    await tp.click('[data-admin="ajouter"]');
    const champs = await tp.evaluate(() => [...document.querySelectorAll('#admin-corps input:not([type="checkbox"]), #admin-corps select')].map(e => ({ n: e.name, t: getComputedStyle(e).fontSize, h: Math.round(e.getBoundingClientRect().height) })));
    verifier('téléphone : le panneau en plein écran, la page derrière immobile (on défile dans le panneau), chaque cible ≥ 44 px, champs à 16 px (M8, D11)',
      tel.plein && tel.verrou === 'hidden' && y1 === y0 && tel.petites.length === 0 && champs.length >= 5 && champs.every(c => c.t === '16px' && c.h >= 44),
      JSON.stringify({ tel, y0, y1, champs }));
    await redimensionner(tp, 390, 500);
    const barre = await rect(tp, '.admin-form-boutons');
    verifier('clavier ouvert (390 × 500) : « Enregistrer » reste collé en bas de l\'écran (M8)', barre && barre.b <= 501 && barre.y < 500, JSON.stringify(barre));
    await redimensionner(tp, 844, 390);
    const couche = await tp.evaluate(() => { const d = document.getElementById('admin'), r = d.getBoundingClientRect(); return { h: Math.round(r.height), w: Math.round(r.width), defile: getComputedStyle(d).overflowY, corps: getComputedStyle(document.getElementById('admin-corps')).overflowY }; });
    verifier('téléphone couché (844 × 390) : plein écran, et tout le panneau défile — les onglets avec (M7)',
      couche.h === 390 && couche.w === 844 && couche.defile === 'auto' && couche.corps === 'visible', JSON.stringify(couche));
    await tp.__ctx.close();
    try { fs27.unlinkSync(fichier27); } catch (e) { /* déjà parti */ }
  }


  // =================================================================
  //  Débrief 29, lot E1 — en-tête, sommaire, recherche : ses vérifications se placent ici,
  //  dans un bloc { … } qui ouvre et ferme ses propres pages.
  // =================================================================
  /* (début du lot E1) */
  /* Débrief 29, lot E1 — l'en-tête, le sommaire collé et sa loupe, sur la
     page VIVANTE (le vrai Code.gs du simulateur derrière google.script.run,
     comme le lot F) : la page ne saute plus (loupe, Tab, frappe), Échap
     ferme d'un coup, la liste des plans passe au-dessus des filtres, les
     icônes disent leur nom, rien ne bouge quand les droits arrivent, les
     deux bandeaux d'alerte se lisent, le téléphone (debout et couché). */
  section('Débrief 29 : en-tête, sommaire, recherche de plan (lot E1)');
  {
    const fsE1 = require('fs'), osE1 = require('os');
    const { construireSimulateur } = require(path.join(__dirname, '..', '..', 'tests', 'construire-simulateur.js'));
    const { Feuille } = require(path.join(__dirname, '..', '..', 'tests', 'faux-classeur.js'));
    const simE1 = construireSimulateur({ date: '2026-10-29', avantPage: function (c, classeur) {
      const ths = classeur.getSheetByName('THS');
      classeur.feuilles.splice(1, 0, new Feuille('HDK Tranche 2', ths.valeurs.map(l => l.slice()), false, ths.fusions.map(f => Object.assign({}, f))));
    } });
    const srvE1 = simE1.contexte;
    simE1.classeur.proprietaire = 'nathan@airbus.com';
    srvE1.__emailScript = 'nathan@airbus.com';
    const fichierE1 = path.join(osE1.tmpdir(), 'suivi-fwd-e1-' + process.pid + '.html');
    fsE1.writeFileSync(fichierE1, simE1.page.replace(/<script>\s*\/\* Simulateur : google\.script\.run[\s\S]*?<\/script>/, ''));
    const vivE1 = async (o) => {
      const c = await nav.newContext({ viewport: { width: o.largeur || 1440, height: o.hauteur || 900 }, colorScheme: o.schema || 'light',
        isMobile: !!o.mobile, hasTouch: !!o.mobile, reducedMotion: o.reducedMotion || 'no-preference' });
      const pg = await c.newPage();
      brancher(pg, 'lot E1 ' + (o.etiquette || ''));
      const email = o.email || 'nathan@airbus.com';
      await pg.exposeFunction('__appel', (nom, args) => {
        if (typeof srvE1[nom] !== 'function' || /_$/.test(nom)) throw new Error('fonction inconnue ' + nom);
        if (o.panne && nom === 'getDonneesCompactes' && o.panne.test(String(JSON.parse(args)[0]))) throw new Error('service indisponible');
        const avant = srvE1.__emailLecteur; srvE1.__emailLecteur = email;
        try { const r = srvE1[nom].apply(null, JSON.parse(args)); return JSON.stringify(r === undefined ? null : r); } finally { srvE1.__emailLecteur = avant; }
      });
      await pg.addInitScript(lent => {
        window.SUIVI_FWD_BUDGET = 1e9;
        function chaine(ok, ko) {
          const c = { withSuccessHandler: f => chaine(f, ko), withFailureHandler: f => chaine(ok, f), withUserObject: () => chaine(ok, ko) };
          return new Proxy(c, { get(t, nom) {
            if (nom in t) return t[nom];
            if (typeof nom !== 'string') return undefined;
            return function () {
              const args = Array.prototype.slice.call(arguments);
              setTimeout(() => window.__appel(nom, JSON.stringify(args)).then(j => { if (ok) ok(JSON.parse(j)); },
                e => { if (ko) ko({ message: String(e.message || e).replace(/^Error: /, '') }); }), lent);
            };
          } });
        }
        window.google = { script: { run: chaine(null, null) } };
      }, o.latence === undefined ? 40 : o.latence);
      await pg.goto('file://' + fichierE1);
      await pg.waitForFunction(() => document.documentElement.getAttribute('data-suivi-fwd') === 'pret', null, { timeout: 30000 });
      if (!o.sansAttente) {
        await pg.waitForFunction(() => document.getElementById('choix-admin').getAttribute('data-droits') !== 'attente', null, { timeout: 20000 }).catch(() => {});
        await pg.waitForTimeout(500);
      }
      pg.__ctx = c;
      return pg;
    };
    const couleursE1 = () => {
      window.__lumE1 = c => { const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
      window.__crE1 = (a, b) => { const x = window.__lumE1(a), y = window.__lumE1(b); return +((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)).toFixed(2); };
    };
    /* Un clic de souris à l'endroit de l'élément (sans le défilement que
       Playwright fait avant un click()). */
    const cliquerSur = async (pg, sel) => {
      const r = await pg.evaluate(s => { const b = document.querySelector(s).getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }, sel);
      await pg.mouse.click(r[0], r[1]);
    };
    const yE1 = pg => pg.evaluate(() => Math.round(window.scrollY));

    /* NOUVEAU-1 et NOUVEAU-4 (premier contact) : la loupe ne fait plus sauter
       la page — ni au clic, ni à la frappe, ni à la fermeture ; Échap ferme
       la liste, puis la recherche (le texte effacé avec). */
    for (const [w, h, mob] of [[1440, 900, false], [390, 844, true]]) {
      const pg = await vivE1({ largeur: w, hauteur: h, mobile: mob, etiquette: 'loupe ' + w });
      await pg.evaluate(() => window.scrollTo(0, 2500)); await pg.waitForTimeout(300);
      const y0 = await yE1(pg);
      await cliquerSur(pg, '#cherche-plan-ouvrir'); await pg.waitForTimeout(300);
      const ouvert = await pg.evaluate(() => ({ y: Math.round(scrollY), actif: document.activeElement.id, ouvert: document.getElementById('cherche-plan').dataset.ouvert }));
      await pg.keyboard.type('GAE21'); await pg.waitForTimeout(500);
      const tape = await pg.evaluate(() => ({ y: Math.round(scrollY), liste: !document.getElementById('cherche-plan-liste').hidden }));
      await pg.keyboard.press('ArrowDown'); await pg.waitForTimeout(150);
      await pg.keyboard.press('Escape'); await pg.waitForTimeout(200);
      const esc1 = await pg.evaluate(() => ({ y: Math.round(scrollY), liste: !document.getElementById('cherche-plan-liste').hidden, ouvert: document.getElementById('cherche-plan').dataset.ouvert, v: document.getElementById('cherche-plan-champ').value }));
      await pg.keyboard.press('Escape'); await pg.waitForTimeout(200);
      const esc2 = await pg.evaluate(() => ({ y: Math.round(scrollY), ouvert: document.getElementById('cherche-plan').dataset.ouvert, v: document.getElementById('cherche-plan-champ').value, actif: document.activeElement.id }));
      verifier(w + ' px : ouvrir la loupe, taper « GAE21 », la flèche, puis Échap — la page ne bouge pas d’un pixel (elle remontait de y 2500 à 1129, puis 672)',
        y0 === 2500 && ouvert.y === y0 && ouvert.actif === 'cherche-plan-champ' && ouvert.ouvert === 'true' && tape.y === y0 && tape.liste && esc1.y === y0 && esc2.y === y0,
        JSON.stringify({ y0, ouvert, tape, esc1, esc2 }));
      verifier(w + ' px : Échap ferme la liste, puis la recherche tout de suite, le texte effacé avec — deux Échap au lieu de trois ; le focus revient à la loupe',
        !esc1.liste && esc1.ouvert === 'true' && esc1.v === 'GAE21' && esc2.ouvert === 'false' && esc2.v === '' && esc2.actif === 'cherche-plan-ouvrir',
        JSON.stringify({ esc1, esc2 }));
      await pg.__ctx.close();
    }

    /* NOUVEAU-2 (premier contact) : un filtre de la page posé, la liste des
       plans trouvés passe au-dessus du bandeau des filtres (le sommaire
       au-dessus de lui). */
    for (const [w, h, mob, schema] of [[1440, 900, false, 'light'], [390, 844, true, 'dark']]) {
      const pg = await vivE1({ largeur: w, hauteur: h, mobile: mob, schema, etiquette: 'sous les filtres ' + w });
      await pg.evaluate(() => document.querySelector('#etats .etat-btn[data-etat="pwd_in_progress"]').click()); await pg.waitForTimeout(500);
      await pg.evaluate(() => window.scrollTo(0, 1800)); await pg.waitForTimeout(300);
      await cliquerSur(pg, '#cherche-plan-ouvrir'); await pg.waitForTimeout(250);
      await pg.keyboard.type('GAE5316A600002B'); await pg.waitForTimeout(500);
      const dessus = await pg.evaluate(() => {
        const o = document.querySelector('#cherche-plan-liste li'), f = document.getElementById('filtres-actifs');
        if (!o) return { option: false };
        const r = o.getBoundingClientRect(), e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return { option: true, n: document.querySelectorAll('#cherche-plan-liste li[data-ref]').length, filtres: !f.hidden, enHaut: !!e && !!e.closest('#cherche-plan-liste'), dessous: e ? (e.id || e.className) : null,
                 zSommaire: +getComputedStyle(document.getElementById('sommaire')).zIndex, zFiltres: +getComputedStyle(f).zIndex };
      });
      verifier(schema + ', ' + w + ' px, filtre PWD_IN_PROGRESS posé : la suggestion de « GAE5316A600002B » est au-dessus du bandeau des filtres (l’élément sous son centre), le sommaire passe devant les filtres',
        dessus.option && dessus.n === 1 && dessus.filtres && dessus.enHaut && dessus.zSommaire > dessus.zFiltres, JSON.stringify(dessus));
      await pg.__ctx.close();
    }

    /* a11y/NOUVEAU-1 : Tab dans les six liens du sommaire collé, puis ses
       quatre icônes, et sur la croix d'un filtre posé : la page reste où
       elle est (±2 px) ; au téléphone, le lien atteint reste dans la bande. */
    for (const [w, h, mob, rm] of [[1440, 900, false, 'no-preference'], [390, 844, true, 'reduce']]) {
      const pg = await vivE1({ largeur: w, hauteur: h, mobile: mob, reducedMotion: rm, etiquette: 'tab ' + w });
      await pg.evaluate(() => document.querySelector('#etats .etat-btn[data-etat="pwd_in_progress"]').click()); await pg.waitForTimeout(500);
      await pg.evaluate(() => { document.activeElement.blur(); window.scrollTo(0, 3000); }); await pg.waitForTimeout(300);
      const y0 = await yE1(pg);
      await pg.focus('#sommaire-liste li:first-child a'); await pg.waitForTimeout(150);
      const pas = [];
      for (let i = 0; i < 12; i++) {
        await pg.keyboard.press('Tab'); await pg.waitForTimeout(120);
        pas.push(await pg.evaluate(() => {
          const a = document.activeElement, l = document.getElementById('sommaire-liste').getBoundingClientRect(), r = a.getBoundingClientRect();
          return { y: Math.round(scrollY), id: a.id || a.getAttribute('data-chapitre') || a.className, dansBande: a.closest('#sommaire-liste') ? (r.left >= l.left - 1 && r.right <= l.right + 1) : null,
                   barre: !!a.closest('#sommaire, #filtres-actifs') };
        }));
      }
      const dansBarres = pas.filter(p => p.barre);
      const ids = dansBarres.map(p => p.id);
      verifier(w + ' px' + (rm === 'reduce' ? ' (moins d’animations)' : '') + ' : Tab dans les liens du sommaire collé, ses quatre icônes puis la croix d’un filtre posé — la page reste à sa place (±2 px), chaque lien atteint reste dans la bande du sommaire',
        ['ouvrir-admin', 'cherche-plan-ouvrir', 'voir-ensemble', 'ouvrir-aide'].every(id => ids.indexOf(id) !== -1) && dansBarres.some(p => p.id === 'x') &&
        dansBarres.every(p => Math.abs(p.y - y0) <= 2) && dansBarres.every(p => p.dansBande !== false), JSON.stringify({ y0, pas }));
      /* Un clic de souris sur une icône ne fait pas sauter la page non plus. */
      await pg.evaluate(() => { document.activeElement.blur(); window.scrollTo(0, 3000); }); await pg.waitForTimeout(250);
      await cliquerSur(pg, '#ouvrir-aide'); await pg.waitForTimeout(400);
      const apresAide = await pg.evaluate(() => ({ y: Math.round(scrollY), ouverte: document.getElementById('aide').open }));
      await pg.keyboard.press('Escape'); await pg.waitForTimeout(300);
      const retour = await pg.evaluate(() => ({ y: Math.round(scrollY), actif: document.activeElement.id }));
      verifier(w + ' px : un clic sur l’icône Aide depuis le bas de la page ouvre l’aide sans faire bouger la page ; Échap y revient, le focus sur l’icône',
        apresAide.ouverte && Math.abs(apresAide.y - 3000) <= 2 && Math.abs(retour.y - 3000) <= 2 && retour.actif === 'ouvrir-aide', JSON.stringify({ apresAide, retour }));
      /* Les sauts du sommaire s'arrêtent toujours sous les barres collées. */
      await pg.evaluate(() => window.scrollTo(0, 0)); await pg.waitForTimeout(200);
      await pg.click('#sommaire-liste a[data-chapitre="section-plans"]');
      await pg.waitForFunction(() => { const s = document.getElementById('section-plans').getBoundingClientRect().top; return s > 0 && s < 200; }, null, { timeout: 5000, polling: 'raf' }).catch(() => {});
      await pg.waitForTimeout(400);
      const saut = await pg.evaluate(() => ({ sec: Math.round(document.getElementById('section-plans').getBoundingClientRect().top),
        bas: Math.round(Math.max(document.getElementById('sommaire').getBoundingClientRect().bottom, document.querySelector('#filtres-actifs .filtres-ligne').getBoundingClientRect().bottom)) }));
      verifier(w + ' px : « 05 Plans » mène toujours juste sous le sommaire et les filtres collés', saut.sec >= saut.bas && saut.sec <= saut.bas + 30, JSON.stringify(saut));
      await pg.__ctx.close();
    }

    /* S9 : la section marquée est celle qui occupe le plus d'écran sous les
       barres collées ; « / » ouvre la loupe là où l'on est. */
    {
      const pg = await vivE1({ largeur: 1440, hauteur: 900, etiquette: 'S9' });
      await pg.evaluate(() => { const s = document.getElementById('section-plans'); window.scrollTo(0, s.getBoundingClientRect().top + scrollY - 405); }); await pg.waitForTimeout(400);
      const espion = await pg.evaluate(() => ({ courant: (document.querySelector('#sommaire-liste a[aria-current]') || { dataset: {} }).dataset.chapitre,
        plans: Math.round(document.getElementById('section-plans').getBoundingClientRect().top) }));
      verifier('S9 : le haut des Plans à 45 % de l’écran (les Plans prennent le bas de l’écran, l’ATA le haut) — le sommaire marque « Plans », plus « Par ATA »',
        espion.courant === 'section-plans' && Math.abs(espion.plans - 405) <= 2, JSON.stringify(espion));
      await pg.evaluate(() => { document.activeElement.blur(); window.scrollTo(0, 1500); }); await pg.waitForTimeout(300);
      await pg.keyboard.press('/'); await pg.waitForTimeout(300);
      const barre = await pg.evaluate(() => ({ y: Math.round(scrollY), actif: document.activeElement.id, ouvert: document.getElementById('cherche-plan').dataset.ouvert,
        aide: [...document.querySelectorAll('#aide dd')].map(d => d.textContent).find(t => /loupe du sommaire/.test(t)) || '' }));
      verifier('S9 : « / » (sans champ en cours de saisie) ouvre la loupe du sommaire, la page ne saute plus aux Plans ; l’aide le dit',
        barre.y === 1500 && barre.actif === 'cherche-plan-champ' && barre.ouvert === 'true' && /^Chercher un plan \(la loupe du sommaire\)/.test(barre.aide), JSON.stringify(barre));
      await pg.keyboard.press('Escape'); await pg.waitForTimeout(150);
      /* B3 : au-delà de 1280 px aussi, la fiche ouverte par la loupe se
         ferme sur la loupe — et la page revient là où on l'avait laissée. */
      await pg.evaluate(() => window.scrollTo(0, 1800)); await pg.waitForTimeout(250);
      await cliquerSur(pg, '#cherche-plan-ouvrir'); await pg.waitForTimeout(250);
      await pg.keyboard.type('GAE5316A600002B'); await pg.waitForTimeout(500);
      await pg.keyboard.press('Enter'); await pg.waitForTimeout(900);
      const fiche = await pg.evaluate(() => ({ ouverte: !document.getElementById('fiche-plan').hidden, actif: document.activeElement.id, y: Math.round(scrollY) }));
      await pg.keyboard.press('Escape'); await pg.waitForTimeout(700);
      const ferme = await pg.evaluate(() => ({ fermee: document.getElementById('fiche-plan').hidden, actif: document.activeElement.id, y: Math.round(scrollY) }));
      verifier('B3, 1440 px : Entrée ouvre la fiche du plan trouvé (la page y descend) ; Échap la ferme, le focus revient à la loupe et la page là où on l’avait laissée',
        fiche.ouverte && fiche.actif === 'titre-fiche-plan' && fiche.y !== 1800 && ferme.fermee && ferme.actif === 'cherche-plan-ouvrir' && Math.abs(ferme.y - 1800) <= 2, JSON.stringify({ fiche, ferme }));
      await pg.__ctx.close();
    }

    /* B21, beaute/NOUVEAU-2 et a11y/NOUVEAU-4 : les bords, les bulles, le
       fond de l'en-tête — en clair et en sombre. */
    for (const schema of ['light', 'dark']) for (const [w, h] of [[1440, 900], [1024, 768]]) {
      const pg = await vivE1({ largeur: w, hauteur: h, schema, etiquette: 'bords ' + schema + ' ' + w });
      await pg.evaluate(couleursE1);
      await pg.evaluate(() => window.scrollTo(0, 1600)); await pg.waitForTimeout(300);
      const bords = await pg.evaluate(() => {
        const r = s => document.querySelector(s).getBoundingClientRect();
        const contenu = r('#section-synthese .panneau-tete .surtitre'), liste = r('#sommaire-liste'), pied = document.querySelector('footer.pied');
        const av = getComputedStyle(pied, '::before'), rp = pied.getBoundingClientRect();
        const ent = document.querySelector('header.entete'), ce = getComputedStyle(ent);
        const fondHex = ce.getPropertyValue('--bandeau-fond').trim();
        const fond = 'rgb(' + fondHex.replace('#', '').match(/../g).map(x => parseInt(x, 16)).join(', ') + ')';
        const mots = [...ent.querySelectorAll('label, .mot-reglage, #titre-page, #num-semaine, #dates-semaine')].filter(e => e.getClientRects().length);
        const marque = document.querySelector('.sommaire-marque');
        return { contenuG: Math.round(contenu.left), contenuD: Math.round(contenu.right), aideD: Math.round(r('#ouvrir-aide').right), outilsG: Math.round(r('#outils-page').left), listeD: Math.round(liste.right),
                 centreListe: Math.round((liste.left + liste.right) / 2), centrePage: Math.round(innerWidth / 2), listeEntiere: document.getElementById('sommaire-liste').scrollWidth <= document.getElementById('sommaire-liste').clientWidth + 1,
                 marqueG: marque.getClientRects().length ? Math.round(marque.getBoundingClientRect().left) : null, marqueD: marque.getClientRects().length ? Math.round(marque.getBoundingClientRect().right) : null, listeG: Math.round(liste.left),
                 filetG: Math.round(rp.left + parseFloat(av.left)), filetD: Math.round(rp.right - parseFloat(av.right)), filetH: av.height, bordPied: getComputedStyle(pied).borderTopWidth,
                 fondEntete: ce.backgroundColor, fond, pireMot: Math.min(...mots.map(e => window.__crE1(getComputedStyle(e).color, ce.backgroundColor))), debord: document.documentElement.scrollWidth - innerWidth };
      });
      verifier('B21, ' + schema + ', ' + w + ' px : les icônes du sommaire finissent sur le bord du contenu, la marque collée commence sur lui ; le filet du pied va d’un bord du contenu à l’autre ; la liste tient entière, sans toucher la marque ni les icônes',
        Math.abs(bords.aideD - bords.contenuD) <= 1 && (bords.marqueG === null || Math.abs(bords.marqueG - bords.contenuG) <= 1) && Math.abs(bords.filetG - bords.contenuG) <= 1 && Math.abs(bords.filetD - bords.contenuD) <= 1 &&
        bords.filetH === '1px' && bords.bordPied === '0px' && bords.listeEntiere && bords.listeD < bords.outilsG && (bords.marqueD === null || bords.marqueD < bords.listeG) && bords.debord <= 0 &&
        (w < 1440 || Math.abs(bords.centreListe - bords.centrePage) <= 2), JSON.stringify(bords));
      verifier('a11y/NOUVEAU-4, ' + schema + ', ' + w + ' px : l’en-tête a le marine du bandeau en couleur de fond (lisible par les outils de contraste) ; chaque mot clair y tient 4,5:1',
        bords.fondEntete === bords.fond && bords.pireMot >= 4.5, JSON.stringify({ fond: bords.fondEntete, attendu: bords.fond, pire: bords.pireMot }));
      if (w === 1440) {
        /* Les bulles : au clavier, chaque icône dit son nom ; plus de title. */
        await pg.focus('#sommaire-liste li:last-child a');
        const bulles = [];
        for (let i = 0; i < 4; i++) {
          await pg.keyboard.press('Tab'); await pg.waitForTimeout(250);
          bulles.push(await pg.evaluate(() => { const a = document.activeElement, c = getComputedStyle(a, '::before'), r = a.getBoundingClientRect();
            const fond = getComputedStyle(document.body).backgroundColor;
            return { id: a.id, nom: a.dataset.nom, contenu: c.content, op: c.opacity, vis: c.visibility, titre: a.getAttribute('title'), droite: Math.round(r.right), largeur: parseFloat(c.width),
                     encre: window.__crE1(c.color, c.backgroundColor), pe: c.pointerEvents }; }));
        }
        verifier('beaute/NOUVEAU-2, ' + schema + ' : au clavier, chaque icône du sommaire montre son nom dans une bulle (Administration, Chercher un plan, Vue d’ensemble des contrats, Aide), lisible, cachée aux lecteurs d’écran (/ "") ; plus de title',
          bulles.map(b => b.id).join() === 'ouvrir-admin,cherche-plan-ouvrir,voir-ensemble,ouvrir-aide' &&
          bulles.every(b => b.nom && b.contenu.indexOf('"' + b.nom + '"') === 0 && /\/ ""$/.test(b.contenu) && b.op === '1' && b.vis === 'visible' && !b.titre && b.encre >= 4.5 && b.pe === 'none' && b.droite - b.largeur >= 0),
          JSON.stringify(bulles));
      }
      await pg.__ctx.close();
    }
    {
      /* La bulle se montre aussi au survol de la souris ; sans animation si
         l'on préfère moins d'animations ; au téléphone, elle ne sort pas de
         l'écran. */
      const pg = await vivE1({ largeur: 1440, hauteur: 900, reducedMotion: 'reduce', etiquette: 'bulle survol' });
      const r = await pg.evaluate(() => { const b = document.getElementById('voir-ensemble').getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; });
      await pg.mouse.move(r[0], r[1]); await pg.waitForTimeout(500);
      const survol = await pg.evaluate(() => { const c = getComputedStyle(document.getElementById('voir-ensemble'), '::before'); return { op: c.opacity, transition: c.transitionDuration }; });
      verifier('beaute/NOUVEAU-2 : la bulle paraît au survol de la souris ; sans transition quand on préfère moins d’animations',
        survol.op === '1' && survol.transition.split(',').every(t => parseFloat(t) === 0), JSON.stringify(survol));
      await pg.__ctx.close();
      const tp = await vivE1({ largeur: 390, hauteur: 844, mobile: true, schema: 'dark', etiquette: 'bulle téléphone' });
      const tel = await tp.evaluate(() => [...document.querySelectorAll('#outils-page .outil-page, #cherche-plan-ouvrir')].filter(b => b.getClientRects().length).map(b => {
        b.focus(); const c = getComputedStyle(b, '::before'), r = b.getBoundingClientRect();
        return { id: b.id, gauche: Math.round(r.right - parseFloat(c.width)), droite: Math.round(r.right) };
      }));
      verifier('beaute/NOUVEAU-2, 390 px : chaque bulle, calée à droite sous son icône, reste dans l’écran',
        tel.length === 4 && tel.every(b => b.gauche >= 0 && b.droite <= 390), JSON.stringify(tel));
      await tp.__ctx.close();
    }

    /* admin/NOUVEAU-1 : pour un lecteur, l'arrivée des droits (le ⚙ qui
       s'efface) ne déplace ni la liste du sommaire ni la loupe. */
    for (const [w, h, mob] of [[1440, 900, false], [1024, 768, false], [390, 844, true]]) {
      const pg = await vivE1({ email: 'lecteur@airbus.com', largeur: w, hauteur: h, mobile: mob, latence: 700, sansAttente: true, etiquette: 'lecteur ' + w });
      const lirePos = () => pg.evaluate(() => ({ droits: document.getElementById('choix-admin').getAttribute('data-droits'), cache: document.getElementById('choix-admin').hidden,
        lien: Math.round(document.querySelector('#sommaire-liste li:first-child a').getBoundingClientRect().left), loupe: Math.round(document.getElementById('cherche-plan-ouvrir').getBoundingClientRect().left),
        aide: Math.round(document.getElementById('ouvrir-aide').getBoundingClientRect().left) }));
      const avant = await lirePos();
      await pg.waitForFunction(() => document.getElementById('choix-admin').hidden, null, { timeout: 20000 }).catch(() => {});
      await pg.waitForTimeout(300);
      const apres = await lirePos();
      verifier('admin/NOUVEAU-1, ' + w + ' px : un lecteur — quand les droits arrivent et que le ⚙ s’efface, rien ne bouge (premier lien du sommaire, loupe, Aide)',
        avant.droits === 'attente' && apres.cache && apres.lien === avant.lien && apres.loupe === avant.loupe && apres.aide === avant.aide, JSON.stringify({ avant, apres }));
      await pg.__ctx.close();
    }

    /* suivis/NOUVEAU-2 et batterie/B2 : le bandeau d'erreur du contrat se lit
       en clair comme en sombre ; la pastille choisie du bandeau sombre tient
       7:1 (vérifiée plus haut, lot H). */
    for (const schema of ['light', 'dark']) {
      const pg = await vivE1({ largeur: 1440, hauteur: 900, schema, panne: /THS/, etiquette: 'alerte contrat ' + schema });
      const ths = await pg.evaluate(() => ([...document.querySelectorAll('#select-contrat option')].find(o => /THS/.test(o.textContent)) || {}).value);
      await pg.selectOption('#select-contrat', ths);
      await pg.waitForFunction(() => !document.getElementById('alerte-contrat').hidden, null, { timeout: 15000 }).catch(() => {});
      await pg.waitForTimeout(300);
      await pg.evaluate(couleursE1);
      const alerte = await pg.evaluate(() => {
        const z = document.getElementById('alerte-contrat'), t = document.getElementById('alerte-contrat-texte'), x = document.getElementById('fermer-alerte-contrat'), b = document.getElementById('reessayer-contrat');
        const fond = getComputedStyle(z).backgroundColor, cs = e => getComputedStyle(e);
        return { vu: !z.hidden, texte: t.textContent, texteCr: window.__crE1(cs(t).color, fond), croix: window.__crE1(cs(x).color, fond),
                 bouton: window.__crE1(cs(b).color, cs(b).backgroundColor === 'rgba(0, 0, 0, 0)' ? fond : cs(b).backgroundColor) };
      });
      verifier('suivis/NOUVEAU-2, ' + schema + ' : le bandeau d’erreur du contrat (A-F5) se lit — texte ≥ 4,5:1 sur son fond, la croix ≥ 3:1, « Réessayer » ≥ 4,5:1 (en clair, le texte était à 1:1)',
        alerte.vu && /THS n’a pas pu être chargé/.test(alerte.texte) && alerte.texteCr >= 4.5 && alerte.croix >= 3 && alerte.bouton >= 4.5, JSON.stringify(alerte));
      await pg.__ctx.close();
    }
    /* Le message « Contrat non chargé » que la page écrit en console est
       voulu ici : on le retire des erreurs relevées. */
    for (let i = erreursJS.length - 1; i >= 0; i--) if (/^lot E1 alerte contrat .* : Contrat non chargé/.test(erreursJS[i])) erreursJS.splice(i, 1);

    /* admin/NOUVEAU-2 : le message du classeur (#alerte-source) sur le
       bandeau marine, en clair et en sombre. */
    for (const schema of ['light', 'dark']) {
      const cV = await contexte({ colorScheme: schema });
      await cV.addInitScript(() => {
        window.SUIVI_FWD_DONNEES = { ok: false, message: 'Colonne d’avancement introuvable dans l’onglet HDK.', colonnes: [], plans: [], releves: [], jalons: [], contrats: [], contrat: '' };
      });
      const pv = await page(cV, 'lot E1 message du classeur ' + schema);
      await pv.evaluate(couleursE1);
      const source = await pv.evaluate(() => {
        const a = document.getElementById('alerte-source'), ent = document.querySelector('header.entete'), ce = getComputedStyle(ent);
        const hex = h => 'rgb(' + h.trim().replace('#', '').match(/../g).map(x => parseInt(x, 16)).join(', ') + ')';
        return { vu: !a.hidden && a.getClientRects().length > 0, texte: a.textContent, haut: window.__crE1(getComputedStyle(a).color, hex(ce.getPropertyValue('--bandeau-fond'))),
                 bas: window.__crE1(getComputedStyle(a).color, hex(ce.getPropertyValue('--bandeau-fond-2'))), taille: parseFloat(getComputedStyle(a).fontSize) };
      });
      verifier('admin/NOUVEAU-2, ' + schema + ' : le message du classeur se lit sur le bandeau marine (≥ 4,5:1 sur tout le dégradé ; 2:1 en clair et 3,4:1 en sombre avant)',
        source.vu && /introuvable/.test(source.texte) && source.haut >= 4.5 && source.bas >= 4.5, JSON.stringify(source));
      if (schema === 'light') {
        /* B4 : la page vide garde l'Aide au bout du sommaire, qui l'ouvre. */
        if (await pv.isVisible('#ouvrir-aide')) { await pv.click('#ouvrir-aide'); await pv.waitForTimeout(400); }
        const aideVide = await pv.evaluate(() => ({ ouverte: document.getElementById('aide').open, vide: document.body.dataset.vide }));
        verifier('B4 : un classeur vide garde ses outils — l’icône Aide du sommaire ouvre l’aide', aideVide.vide === 'true' && aideVide.ouverte, JSON.stringify(aideVide));
      }
      await cV.close();
    }
    /* Téléphone debout (mobile/NOUVEAU-3, suivis/NOUVEAU-3) : des icônes de
       28 px (toucher 44 px), la section lue toujours lisible en entier hors
       des fondus, un fondu à gauche quand la bande est défilée. */
    for (const [w, h] of [[390, 844], [360, 740]]) {
      const pg = await vivE1({ largeur: w, hauteur: h, mobile: true, etiquette: 'téléphone ' + w });
      const icones = await pg.evaluate(() => [...document.querySelectorAll('#outils-page .outil-page, #cherche-plan-ouvrir')].filter(b => b.getClientRects().length).map(b => {
        const r = b.getBoundingClientRect(), a = getComputedStyle(b, '::after');
        return { id: b.id, l: Math.round(r.width), zoneH: Math.round(r.height - 2 * parseFloat(a.top)), zoneL: Math.round(r.width - 2 * parseFloat(a.left)) };
      }));
      const largeurListe = await pg.evaluate(() => Math.round(document.getElementById('sommaire-liste').getBoundingClientRect().width));
      const parSection = [];
      for (const id of ['section-synthese', 'section-tendance', 'section-journal', 'section-repartition', 'section-plans', 'rapprochement']) {
        await pg.evaluate(id => { const s = document.getElementById(id); window.scrollTo(0, s.getBoundingClientRect().top + scrollY - 60); }, id);
        await pg.waitForTimeout(350);
        parSection.push(await pg.evaluate(() => {
          const l = document.getElementById('sommaire-liste'), lr = l.getBoundingClientRect(), a = l.querySelector('a[aria-current]');
          const mg = l.classList.contains('deborde-gauche') ? 28 : 0, md = l.classList.contains('deborde-droite') ? 28 : 0;
          const lisibles = [...l.querySelectorAll('li:not([hidden]) a')].filter(x => { const q = x.getBoundingClientRect(); return q.left >= lr.left + mg - 1 && q.right <= lr.right - md + 1; }).map(x => x.dataset.chapitre);
          return { courant: a ? a.dataset.chapitre : null, lisibles, gauche: l.classList.contains('deborde-gauche'), defile: l.scrollLeft > 2, masque: getComputedStyle(l).maskImage || getComputedStyle(l).webkitMaskImage };
        }));
      }
      verifier('téléphone ' + w + ' px : quatre icônes de 28 px, chacune touchable sur 44 × 44 px ; la bande des sections gagne la place (≥ 200 px)',
        icones.length === 4 && icones.every(i => i.l === 28 && i.zoneH >= 44 && i.zoneL >= 44) && largeurListe >= 200, JSON.stringify({ icones, largeurListe }));
      verifier('téléphone ' + w + ' px : à chaque section, son nom se lit en entier hors des fondus (avec un voisin entier presque partout) ; défilée, la bande a un fondu à gauche',
        parSection.every(s => s.courant && s.lisibles.indexOf(s.courant) !== -1) && parSection.filter(s => s.lisibles.length >= 2).length >= 4 &&
        parSection.every(s => s.gauche === s.defile) &&  parSection.filter(s => s.gauche).every(s => /^linear-gradient\(to right, (transparent|rgba\(0, 0, 0, 0\))/.test(s.masque)),
        JSON.stringify(parSection));
      await pg.__ctx.close();
    }

    /* Téléphone couché (mobile/M5) : le sommaire ne colle plus, seuls les
       filtres posés collent, en une ligne courte (≤ 48 px) ; ses sauts et sa
       loupe marchent toujours. */
    for (const schema of ['light', 'dark']) {
      const pg = await vivE1({ largeur: 844, hauteur: 390, mobile: true, schema, etiquette: 'couché ' + schema });
      await pg.evaluate(() => document.querySelector('#etats .etat-btn[data-etat="pwd_in_progress"]').click()); await pg.waitForTimeout(500);
      await pg.evaluate(() => window.scrollTo(0, 1400)); await pg.waitForTimeout(400);
      const couche = await pg.evaluate(() => {
        const s = document.getElementById('sommaire').getBoundingClientRect(), f = document.querySelector('#filtres-actifs .filtres-ligne').getBoundingClientRect();
        const vu = e => !!e && getComputedStyle(e).display !== 'none';
        return { somBas: Math.round(s.bottom), filtreHaut: Math.round(f.top), colles: Math.max(0, Math.round(s.bottom)) + Math.round(f.height),
                 mot: vu(document.querySelector('#filtres-actifs .mot')), long: vu(document.querySelector('#tout-effacer .long')), court: vu(document.querySelector('#tout-effacer .court')) };
      });
      verifier('M5, ' + schema + ', 844 × 390 : le sommaire reste en haut de la page ; seuls les filtres posés collent, en une ligne de 48 px au plus, sans « Filtres », « Effacer » au bout',
        couche.somBas <= 0 && couche.filtreHaut === 0 && couche.colles <= 48 && !couche.mot && !couche.long && couche.court, JSON.stringify(couche));
      if (schema === 'light') {
        await pg.evaluate(() => window.scrollTo(0, 0)); await pg.waitForTimeout(250);
        await pg.click('#sommaire-liste a[data-chapitre="section-plans"]'); await pg.waitForTimeout(1500);
        const saut = await pg.evaluate(() => ({ sec: Math.round(document.getElementById('section-plans').getBoundingClientRect().top), filtres: Math.round(document.querySelector('#filtres-actifs .filtres-ligne').getBoundingClientRect().bottom) }));
        await pg.evaluate(() => window.scrollTo(0, 0)); await pg.waitForTimeout(250);
        await pg.evaluate(() => document.getElementById('cherche-plan-ouvrir').click()); await pg.waitForTimeout(250);
        const loupe = await pg.evaluate(() => { const c = document.getElementById('cherche-plan-cadre').getBoundingClientRect(), s = document.getElementById('sommaire').getBoundingClientRect();
          return { dedans: c.top >= s.top - 1 && c.bottom <= s.bottom + 1 && c.width > 400, actif: document.activeElement.id }; });
        verifier('M5, 844 × 390 : « 05 Plans » s’arrête juste sous les filtres collés ; la loupe s’ouvre dans le sommaire',
          saut.sec >= saut.filtres && saut.sec <= saut.filtres + 30 && loupe.dedans && loupe.actif === 'cherche-plan-champ', JSON.stringify({ saut, loupe }));
      }
      await pg.__ctx.close();
    }
    try { fsE1.unlinkSync(fichierE1); } catch (e) { /* déjà parti */ }
  }
  /* (fin du lot E1) */


  // =================================================================
  //  Débrief 29, lot E2 — états, Vue d’ensemble, contrats : ses vérifications se placent ici,
  //  dans un bloc { … } qui ouvre et ferme ses propres pages.
  // =================================================================
  /* (début du lot E2) */
  section('Débrief 29 : états d’erreur, Vue d’ensemble, contrats masqués, pied (lot E2)');
  {
    const fs29 = require('fs'), os29 = require('os');
    const { construireSimulateur } = require(path.join(__dirname, '..', '..', 'tests', 'construire-simulateur.js'));
    const { Feuille } = require(path.join(__dirname, '..', '..', 'tests', 'faux-classeur.js'));
    /* Le classeur du simulateur, comme chez Nathan : HDK (deux tranches, la
       seconde « HDK Tranche 2 », sans historique) et THS, sans jalon. */
    const sim = construireSimulateur({ date: '2026-10-29', avantPage: function (c, classeur) {
      const ths = classeur.getSheetByName('THS');
      classeur.feuilles.splice(1, 0, new Feuille('HDK Tranche 2', ths.valeurs.map(l => l.slice()), false, ths.fusions.map(f => Object.assign({}, f))));
    } });
    const srv = sim.contexte;
    sim.classeur.proprietaire = 'nathan@airbus.com';
    srv.__emailScript = 'nathan@airbus.com';
    const fichier29 = path.join(os29.tmpdir(), 'suivi-fwd-e2-' + process.pid + '.html');
    fs29.writeFileSync(fichier29, sim.page.replace(/<script>\s*\/\* Simulateur : google\.script\.run[\s\S]*?<\/script>/, ''));
    const commeQui = (email, fn) => { const avant = srv.__emailLecteur; srv.__emailLecteur = email; try { return fn(); } finally { srv.__emailLecteur = avant; } };
    /* Une panne du classeur le temps d'un essai : les fonctions qui rendent
       un contrat échouent (« Service indisponible »). */
    const RENDRE = ['getDonneesCompactes', 'getDonneesCompactesJson', 'getDonneesPourClient', 'getDonneesPourClientLues'];
    let gardees = null;
    const panne = oui => {
      if (oui && !gardees) { gardees = {}; RENDRE.forEach(k => { gardees[k] = srv[k]; srv[k] = function () { throw new Error('Service indisponible'); }; }); }
      if (!oui && gardees) { RENDRE.forEach(k => { srv[k] = gardees[k]; }); gardees = null; }
    };
    const vivante = async (o) => {
      const c = await nav.newContext({ viewport: { width: o.largeur || 1280, height: o.hauteur || 900 }, colorScheme: o.schema || 'light',
        isMobile: !!o.mobile, hasTouch: !!o.mobile, locale: 'en-US' });
      const pg = await c.newPage();
      const etiquette = 'lot E2 ' + o.email;
      /* Le pont du classeur écrit « Contrat non chargé : … » dans la console
         à chaque échec — ici voulu (la panne, le contrat masqué) ; toute
         autre erreur compte. */
      pg.on('pageerror', e => erreursJS.push(etiquette + ' : ' + e.message));
      pg.on('console', m => { if (m.type() === 'error' && !/Contrat non chargé/.test(m.text())) erreursJS.push(etiquette + ' : ' + m.text()); });
      pg.on('dialog', d => d.dismiss().catch(() => {}));
      await pg.exposeFunction('__appel', (nom, args) => {
        if (typeof srv[nom] !== 'function' || /_$/.test(nom)) throw new Error('fonction inconnue ' + nom);
        return commeQui(o.email, () => { const r = srv[nom].apply(null, JSON.parse(args)); return JSON.stringify(r === undefined ? null : r); });
      });
      await pg.addInitScript(lent => {
        window.SUIVI_FWD_BUDGET = 1e9;
        function chaine(ok, ko) {
          const c = { withSuccessHandler: f => chaine(f, ko), withFailureHandler: f => chaine(ok, f), withUserObject: () => chaine(ok, ko) };
          return new Proxy(c, { get(t, nom) {
            if (nom in t) return t[nom];
            if (typeof nom !== 'string') return undefined;
            return function () {
              const args = Array.prototype.slice.call(arguments);
              setTimeout(() => window.__appel(nom, JSON.stringify(args)).then(j => { if (ok) ok(JSON.parse(j)); },
                e => { if (ko) ko({ message: String(e.message || e).replace(/^Error: /, '') }); }), lent);
            };
          } });
        }
        window.google = { script: { run: chaine(null, null) } };
      }, o.latence === undefined ? 40 : o.latence);
      await pg.goto('file://' + fichier29);
      await pg.waitForFunction(() => document.documentElement.getAttribute('data-suivi-fwd') === 'pret', null, { timeout: 30000 });
      /* Les droits arrivent après l'ouverture (mesDroits). */
      await pg.waitForFunction(() => {
        const b = document.getElementById('ouvrir-admin');
        const vu = b && b.getClientRects().length && getComputedStyle(b).visibility !== 'hidden';
        return vu || (document.getElementById('pied-responsable') || {}).textContent;
      }, null, { timeout: 20000 }).catch(() => {});
      await pg.evaluate(() => {
        window.__lum = c => {
          const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
          return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
        };
        window.__contraste = (a, b) => { const x = window.__lum(a), y = window.__lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
      });
      pg.__ctx = c;
      return pg;
    };
    const alerteVue = pg => pg.waitForFunction(() => !document.getElementById('alerte-contrat').hidden, null, { timeout: 15000 }).catch(() => {});
    const ensembleFini = pg => pg.waitForFunction(() => document.querySelectorAll('#ensemble tbody tr').length > 0 &&
      ![...document.querySelectorAll('#ensemble tbody td')].some(td => /chargement…/.test(td.textContent)), null, { timeout: 15000 }).catch(() => {});
    const etatContrat = pg => pg.evaluate(() => {
      const r = document.getElementById('reessayer-contrat');
      return { alerte: document.getElementById('alerte-contrat').hidden ? '' : document.getElementById('alerte-contrat-texte').textContent,
               reessayer: !r.hidden && r.getClientRects().length > 0,
               contrats: [...document.querySelectorAll('#select-contrat option')].map(x => x.textContent).join(),
               valeur: document.getElementById('select-contrat').value,
               tranches: [...document.querySelectorAll('#select-tranche option')].map(x => x.textContent).join() };
    });

    try {
      /* B7, A-F5 : le bandeau d'erreur et le message du classeur, dans l'en-tête marine, lisibles dans les deux thèmes. */
      for (const schema of ['light', 'dark']) {
        const pg = await vivante({ email: 'nathan@airbus.com', schema });
        panne(true);
        await pg.selectOption('#select-contrat', 'THS');
        await alerteVue(pg);
        panne(false);
        await pg.mouse.move(4, 4);
        const m = await pg.evaluate(() => {
          const a = document.getElementById('alerte-contrat'), t = document.getElementById('alerte-contrat-texte');
          const x = document.getElementById('fermer-alerte-contrat'), r = document.getElementById('reessayer-contrat');
          const fond = getComputedStyle(a).backgroundColor, cx = getComputedStyle(x), cr = getComputedStyle(r);
          const fondR = cr.backgroundColor === 'rgba(0, 0, 0, 0)' ? fond : cr.backgroundColor;
          return { texte: t.textContent, vu: !a.hidden, fond,
                   encre: +window.__contraste(getComputedStyle(t).color, fond).toFixed(2),
                   croix: +window.__contraste(cx.color, fond).toFixed(2), croixBord: +window.__contraste(cx.borderTopColor, fond).toFixed(2),
                   reessayer: +window.__contraste(cr.color, fondR).toFixed(2), reessayerBord: +window.__contraste(cr.borderTopColor, fond).toFixed(2),
                   reessayerVu: !r.hidden && r.getClientRects().length > 0 };
        });
        verifier('B7, A-F5 (' + schema + ') : le bandeau d’erreur se lit dans l’en-tête marine — texte ≥ 4,5:1 sur son fond, « Réessayer » ≥ 4,5:1, la croix et les bords de « Réessayer » et de la croix ≥ 3:1',
          m.vu && m.texte === 'THS n’a pas pu être chargé : service indisponible. La page montre toujours HDK › Tranche 1.' && m.reessayerVu &&
          m.fond === (schema === 'light' ? 'rgb(251, 238, 234)' : 'rgb(43, 31, 20)') &&
          m.encre >= 4.5 && m.reessayer >= 4.5 && m.croix >= 3 && m.croixBord >= 3 && m.reessayerBord >= 3, JSON.stringify(m));
        await pg.click('#fermer-alerte-contrat');
        await pg.evaluate(() => { const s = window.__jeuDExemple('HDK'); s.message = 'La colonne d’avancement est introuvable dans l’onglet « HDK ».'; window.__chargerSource(s); });
        await pg.waitForTimeout(300);
        const src = await pg.evaluate(() => {
          const a = document.getElementById('alerte-source'), c = getComputedStyle(a);
          return { vu: !a.hidden && a.getClientRects().length > 0, fond: c.backgroundColor, bord: c.borderLeftWidth, encre: +window.__contraste(c.color, c.backgroundColor).toFixed(2) };
        });
        verifier('B7 (' + schema + ') : le message du classeur qui n’a rien pu rendre prend le dessin du bandeau d’erreur — son texte ≥ 4,5:1 (en rouge sur la bande marine, il tombait à 2:1)',
          src.vu && src.fond === m.fond && src.bord === '3px' && src.encre >= 4.5, JSON.stringify(src));
        await pg.__ctx.close();
      }

      /* A-F13 : le pied et l'aide disent « archivé », et le jour du relevé. */
      {
        const pg = await vivante({ email: 'lecteur@airbus.com' });
        const pied = await pg.evaluate(() => document.getElementById('import').textContent);
        await pg.click('#ouvrir-aide-pied'); await pg.waitForTimeout(400);
        const aide = await pg.evaluate(() => document.getElementById('aide-fraicheur').textContent);
        verifier('A-F13 : le pied dit « Dernier relevé archivé : S43 (vendredi 23 octobre) · 6 relevés », et l’aide le redit — sans ligne d’âge en tête de page',
          pied === 'Dernier relevé archivé : S43 (vendredi 23 octobre) · 6 relevés' && aide.indexOf(pied + '.') === 0 &&
          !(await pg.evaluate(() => /Chiffres du /.test(document.getElementById('entete').textContent))), JSON.stringify({ pied, aide }));
        await pg.__ctx.close();
      }

      /* A-F21, S7 : un lecteur, page ouverte ; THS masqué entre-temps par l'administrateur, puis choisi au menu. */
      {
        const lp = await vivante({ email: 'lecteur@airbus.com' });
        commeQui('nathan@airbus.com', () => srv.adminRetirerContrat('THS', true));
        try {
          await lp.selectOption('#select-contrat', 'THS');
          await alerteVue(lp);
          const m1 = await etatContrat(lp);
          verifier('A-F21, S7 : un contrat masqué entre-temps quitte le menu ; le bandeau le dit en une phrase qui ne le nomme qu’une fois, sans « Réessayer » (qui ne pourrait qu’échouer)',
            m1.alerte === 'THS n’est plus affiché sur le tableau de bord (masqué par un administrateur). La page montre toujours HDK › Tranche 1.' &&
            !m1.reessayer && m1.contrats === 'HDK' && m1.valeur === 'HDK' && m1.tranches === 'Tranche 1,Tranche 2', JSON.stringify(m1));
          await lp.click('#voir-ensemble'); await ensembleFini(lp);
          const lignes = await lp.evaluate(() => [...document.querySelectorAll('#ensemble tbody th button')].map(b => b.textContent.trim()).join());
          await lp.keyboard.press('Escape'); await lp.waitForTimeout(300);
          const m2 = await etatContrat(lp);
          verifier('A-F21 : la Vue d’ensemble ne le ramène pas — ni dans ses lignes, ni dans le menu une fois fermée',
            lignes === 'HDK › Tranche 1,HDK › Tranche 2' && m2.contrats === 'HDK', JSON.stringify({ lignes, m2 }));
          /* Une panne ordinaire ensuite : « Réessayer » revient. L'horloge
             avance d'une minute : la demande faite d'avance à l'ouverture du
             menu (débrief 23) n'est plus bonne, la page redemande. */
          await lp.evaluate(() => { const vrai = Date.now; Date.now = () => vrai() + 60000; });
          panne(true);
          await lp.selectOption('#select-tranche', 'HDK Tranche 2');
          await lp.waitForFunction(() => /n’a pas pu être chargé/.test(document.getElementById('alerte-contrat-texte').textContent), null, { timeout: 15000 }).catch(() => {});
          panne(false);
          const m3 = await etatContrat(lp);
          verifier('A-F21 : après lui, une panne ordinaire remet « Réessayer »',
            m3.alerte === 'HDK › Tranche 2 n’a pas pu être chargé : service indisponible. La page montre toujours HDK › Tranche 1.' && m3.reessayer, JSON.stringify(m3));
        } finally {
          panne(false);
          commeQui('nathan@airbus.com', () => srv.adminRetirerContrat('THS', false));
        }
        await lp.__ctx.close();
      }

      /* F18, A-F10, A-F25, S8 : la Vue d'ensemble, vue par le responsable. */
      {
        const np = await vivante({ email: 'nathan@airbus.com' });
        await np.click('#echeance-titre'); await np.waitForTimeout(500);
        const requisFiche = await np.evaluate(() => { const b = document.querySelector('#fiche-echeance .fiche-echeance-rythme b'); return b ? b.textContent.trim() : null; });
        await np.click('#fiche-echeance [data-fermer-echeance]').catch(() => {}); await np.waitForTimeout(300);
        await np.click('#voir-ensemble'); await ensembleFini(np);
        const ens = await np.evaluate(() => [...document.querySelectorAll('#ensemble tbody tr')].map(tr => {
          const td = tr.querySelectorAll('td'), aj = tr.querySelector('[data-ajouter-jalon]');
          return { nom: tr.querySelector('th button').textContent.trim(), sous: (tr.querySelector('th small') || {}).textContent || '',
                   aEcheance: td[5] ? td[5].textContent.replace(/[\u00a0\u202f]/g, ' ') : '',
                   prochaine: td[4] ? (td[4].querySelector('.doux') || td[4]).textContent : '',
                   ajouter: aj ? aj.dataset.ajouterJalon + '|' + aj.textContent + '|' + aj.getAttribute('aria-label') : '' };
        }));
        verifier('A-F10 : la Vue d’ensemble nomme chaque onglet comme l’administration — « HDK › Tranche 1 » (plus « HDK » seul au-dessus de « HDK › Tranche 2 »), « à l’écran » sous celui qu’on regarde',
          ens.map(r => r.nom).join() === 'HDK › Tranche 1,HDK › Tranche 2,THS' && ens[0].sous === 'à l’écran' && !ens[1].sous && !ens[2].sous, JSON.stringify(ens));
        const ilFaut = (ens[0].aEcheance.match(/il faut ([\d\s,]+)\/sem\./) || [])[1];
        verifier('F18 : « il faut 83/sem. » — le rythme requis arrondi comme dans la fiche de l’échéance (plus « 83,0 »)',
          !!requisFiche && /^manque \d+il faut \d+\/sem\.$/.test(ens[0].aEcheance) && ilFaut === requisFiche, JSON.stringify({ requisFiche, aEcheance: ens[0].aEcheance }));
        verifier('A-F25, S8 : sous « aucun jalon », le responsable trouve « + Ajouter un jalon » (nommé pour son contrat) ; le contrat qui a ses jalons, non',
          !ens[0].ajouter && ens[1].prochaine === 'aucun jalon' && ens[2].prochaine === 'aucun jalon' &&
          ens[1].ajouter === 'HDK Tranche 2|+ Ajouter un jalon|Ajouter un jalon pour HDK › Tranche 2' &&
          ens[2].ajouter === 'THS|+ Ajouter un jalon|Ajouter un jalon pour THS', JSON.stringify(ens));
        await np.focus('#ensemble [data-ajouter-jalon="THS"]');
        await np.keyboard.press('Enter');
        await np.waitForFunction(() => document.getElementById('admin').open && document.querySelector('#admin-corps form[data-form="jalon"]'), null, { timeout: 15000 }).catch(() => {});
        const ouvert = await np.evaluate(() => ({ ensemble: document.getElementById('ensemble').open, admin: document.getElementById('admin').open,
          onglet: ((document.querySelector('#admin-onglets [aria-selected="true"]') || {}).textContent || '').trim(),
          pour: (document.querySelector('#admin-corps select[name="pour"]') || {}).value, focus: document.activeElement.id }));
        await np.keyboard.press('Escape'); await np.waitForTimeout(500);
        const retour = await np.evaluate(() => ({ admin: document.getElementById('admin').open, focus: document.activeElement.id }));
        verifier('S8 : « + Ajouter un jalon » ferme la Vue d’ensemble et ouvre l’administration sur un jalon neuf pour ce contrat (onglet Jalons, « Pour » = THS, le focus sur le nom) ; Échap ramène le focus sur « Vue d’ensemble »',
          !ouvert.ensemble && ouvert.admin && ouvert.onglet === 'Jalons' && ouvert.pour === 'THS' && ouvert.focus === 'admin-texte' &&
          !retour.admin && retour.focus === 'voir-ensemble', JSON.stringify({ ouvert, retour }));
        await np.__ctx.close();
      }
      /* Un lecteur lit « aucun jalon », sans plus ; une administratrice de THS seul ne trouve le geste que pour THS. */
      {
        const lp = await vivante({ email: 'lecteur@airbus.com' });
        await lp.click('#voir-ensemble'); await ensembleFini(lp);
        const lecteur = await lp.evaluate(() => ({ boutons: document.querySelectorAll('#ensemble [data-ajouter-jalon]').length,
          aucun: [...document.querySelectorAll('#ensemble tbody td .doux')].map(d => d.textContent).join() }));
        await lp.__ctx.close();
        commeQui('nathan@airbus.com', () => srv.adminEnregistrerAdmins([{ email: 'anne@airbus.com', contrats: ['THS'] }]));
        const ap = await vivante({ email: 'anne@airbus.com' });
        await ap.click('#voir-ensemble'); await ensembleFini(ap);
        const anne = await ap.evaluate(() => [...document.querySelectorAll('#ensemble [data-ajouter-jalon]')].map(b => b.dataset.ajouterJalon).join());
        await ap.__ctx.close();
        commeQui('nathan@airbus.com', () => srv.adminEnregistrerAdmins([]));
        verifier('S8 : un lecteur lit « aucun jalon », sans bouton ; une administratrice de THS seul ne trouve « + Ajouter un jalon » que pour THS',
          lecteur.boutons === 0 && lecteur.aucun === 'aucun jalon,aucun jalon' && anne === 'THS', JSON.stringify({ lecteur, anne }));
      }

      /* A-F25 : réseau lent — la fenêtre ne grandit plus quand les autres contrats arrivent. */
      {
        const pg = await vivante({ email: 'nathan@airbus.com', latence: 900 });
        await pg.click('#voir-ensemble'); await pg.waitForTimeout(600);
        const avant = await pg.evaluate(() => ({ h: Math.round(document.getElementById('ensemble').getBoundingClientRect().height),
          attente: [...document.querySelectorAll('#ensemble tbody td')].filter(td => /chargement…/.test(td.textContent)).length,
          lignes: [...document.querySelectorAll('#ensemble tbody tr')].map(tr => Math.round(tr.getBoundingClientRect().height)) }));
        await ensembleFini(pg);
        const apres = await pg.evaluate(() => ({ h: Math.round(document.getElementById('ensemble').getBoundingClientRect().height),
          lignes: [...document.querySelectorAll('#ensemble tbody tr')].map(tr => Math.round(tr.getBoundingClientRect().height)) }));
        verifier('A-F25 : sur un réseau lent, une ligne « chargement… » a déjà la hauteur d’une ligne remplie — la Vue d’ensemble ne grandit plus à l’arrivée des chiffres',
          avant.attente === 2 && Math.abs(apres.h - avant.h) <= 1 && avant.lignes.join() === apres.lignes.join(), JSON.stringify({ avant, apres }));
        await pg.__ctx.close();
      }

      /* D11 : au téléphone, « + Ajouter un jalon » est une cible de 44 px. */
      {
        const tp = await vivante({ email: 'nathan@airbus.com', largeur: 390, hauteur: 844, mobile: true });
        await tp.tap('#voir-ensemble'); await ensembleFini(tp);
        const cibles = await tp.evaluate(() => [...document.querySelectorAll('#ensemble [data-ajouter-jalon]')].map(b => {
          const r = b.getBoundingClientRect(), a = getComputedStyle(b, '::after');
          return { h: Math.round(r.height - parseFloat(a.top) - parseFloat(a.bottom)), w: Math.round(r.width - parseFloat(a.left) - parseFloat(a.right)), droite: Math.round(innerWidth - r.right) };
        }));
        verifier('D11 : au téléphone, chaque « + Ajouter un jalon » de la Vue d’ensemble offre une cible de 44 px au moins, calée à droite de sa carte',
          cibles.length === 2 && cibles.every(c => c.h >= 44 && c.w >= 44 && c.droite <= 20), JSON.stringify(cibles));
        await tp.__ctx.close();
      }
    } finally {
      panne(false);
      try { fs29.unlinkSync(fichier29); } catch (e) { /* déjà parti */ }
    }
  }
  /* (fin du lot E2) */


  // =================================================================
  //  Débrief 29, lot T — Synthèse, Tendance, couleurs : ses vérifications se placent ici,
  //  dans un bloc { … } qui ouvre et ferme ses propres pages.
  // =================================================================
  /* (début du lot T) */
  /* (fin du lot T) */


  // =================================================================
  //  Débrief 29, lot J — journal et Par ATA : ses vérifications se placent ici,
  //  dans un bloc { … } qui ouvre et ferme ses propres pages.
  // =================================================================
  /* (début du lot J) */
  section('Débrief 29 : journal au téléphone, rythme requis, plans de la liste par groupe (lot J)');
  {
    /* La page vivante, servie par le vrai serveur sur le classeur du
       simulateur (comme la section du lot F) : HDK, ses six relevés, son
       jalon « Solde FWD » (Séquence 600). */
    const fsJ = require('fs'), osJ = require('os');
    const { construireSimulateur } = require(path.join(__dirname, '..', '..', 'tests', 'construire-simulateur.js'));
    const { Feuille } = require(path.join(__dirname, '..', '..', 'tests', 'faux-classeur.js'));
    const simJ = construireSimulateur({ date: '2026-10-29', avantPage: function (c, classeur) {
      const ths = classeur.getSheetByName('THS');
      classeur.feuilles.splice(1, 0, new Feuille('HDK Tranche 2', ths.valeurs.map(l => l.slice()), false, ths.fusions.map(f => Object.assign({}, f))));
    } });
    const srvJ = simJ.contexte;
    simJ.classeur.proprietaire = 'nathan@airbus.com';
    srvJ.__emailScript = 'nathan@airbus.com';
    const fichierJ = path.join(osJ.tmpdir(), 'suivi-fwd-lot-j-' + process.pid + '.html');
    fsJ.writeFileSync(fichierJ, simJ.page.replace(/<script>\s*\/\* Simulateur : google\.script\.run[\s\S]*?<\/script>/, ''));
    const vivanteJ = async (o) => {
      const email = 'nathan@airbus.com';
      const c = await nav.newContext({ viewport: { width: o.largeur || 1280, height: o.hauteur || 900 }, colorScheme: o.schema || 'light',
        isMobile: !!o.mobile, hasTouch: !!o.mobile, locale: 'en-US' });
      const pg = await c.newPage();
      brancher(pg, 'lot J ' + (o.largeur || 1280) + (o.mobile ? ' tactile' : '') + ' ' + (o.schema || 'light'));
      await pg.exposeFunction('__appel', (nom, args) => {
        if (typeof srvJ[nom] !== 'function' || /_$/.test(nom)) throw new Error('fonction inconnue ' + nom);
        const avant = srvJ.__emailLecteur; srvJ.__emailLecteur = email;
        try { const r = srvJ[nom].apply(null, JSON.parse(args)); return JSON.stringify(r === undefined ? null : r); } finally { srvJ.__emailLecteur = avant; }
      });
      await pg.addInitScript(() => {
        window.SUIVI_FWD_BUDGET = 1e9;
        function chaine(ok, ko) {
          const c = { withSuccessHandler: f => chaine(f, ko), withFailureHandler: f => chaine(ok, f), withUserObject: () => chaine(ok, ko) };
          return new Proxy(c, { get(t, nom) {
            if (nom in t) return t[nom];
            if (typeof nom !== 'string') return undefined;
            return function () {
              const args = Array.prototype.slice.call(arguments);
              setTimeout(() => window.__appel(nom, JSON.stringify(args)).then(j => { if (ok) ok(JSON.parse(j)); },
                e => { if (ko) ko({ message: String(e.message || e).replace(/^Error: /, '') }); }), 40);
            };
          } });
        }
        window.google = { script: { run: chaine(null, null) } };
      });
      await pg.goto('file://' + fichierJ);
      await pg.waitForFunction(() => document.documentElement.getAttribute('data-suivi-fwd') === 'pret', null, { timeout: 30000 });
      await pg.waitForFunction(() => (document.getElementById('pied-responsable') || {}).textContent ||
        getComputedStyle(document.getElementById('choix-admin')).visibility !== 'hidden', null, { timeout: 20000 }).catch(() => {});
      /* Le bandeau du simulateur n'existe pas devant le classeur. */
      await pg.evaluate(() => { const x = document.querySelector('.simulateur-bandeau'); if (x) x.remove(); window.scrollTo(0, 0); });
      await pg.waitForTimeout(600);
      pg.__ctx = c;
      return pg;
    };
    /* Toucher (au doigt) ou cliquer le milieu d'un élément. */
    const toucher = async (pg, tactile, quoi) => {
      const p = await pg.evaluate(q => { const e = typeof q === 'string' ? document.querySelector(q) : document.querySelectorAll(q.s)[q.i];
        const r = e.getBoundingClientRect(); return { x: r.left + Math.min(30, r.width / 2), y: r.top + r.height / 2 }; }, quoi);
      if (tactile) await pg.touchscreen.tap(p.x, p.y); else await pg.mouse.click(p.x, p.y);
      await pg.waitForTimeout(500);
    };
    /* Le nom d'une semaine (« S41 · du … ») : où il est à l'écran, et où en est la page. */
    const nomSemaine = (pg, k) => pg.evaluate(k => { const t = document.querySelectorAll('#zone-journal .journal-plier')[k];
      return { y: scrollY, nom: t.querySelector('.sem').getBoundingClientRect().top, sem: t.querySelector('.sem-num').textContent, ouvert: t.getAttribute('aria-expanded'), focus: document.activeElement === t }; }, k);

    // --- M10 et NOUVEAU-2 : au téléphone, la ligne d'une semaine ouverte s'efface (display: contents) ;
    //     le journal mesurait cette boîte vide (son haut : 0) et jetait la page vers le haut.
    for (const o of [{ largeur: 390, hauteur: 844, schema: 'light' }, { largeur: 360, hauteur: 740, schema: 'dark' }]) {
      const dit = o.largeur + ' × ' + o.hauteur + ', ' + o.schema;
      const gj = await vivanteJ(Object.assign({ mobile: true }, o));
      // 1. Toucher « 9 passés à « VALIDATED » » sous la première semaine : ses plans à l'écran.
      await gj.evaluate(() => document.querySelector('#zone-journal .compte-passage').scrollIntoView({ block: 'center' }));
      await gj.waitForTimeout(300);
      const avantCompte = await gj.evaluate(() => { const c = document.querySelector('#zone-journal .compte-passage');
        return { y: scrollY, passage: c.dataset.passage, sem: c.closest('.journal-semaine').querySelector('.journal-plier').dataset.semaine }; });
      await toucher(gj, true, '#zone-journal .compte-passage');
      const apresCompte = await gj.evaluate(c => {
        const t = [...document.querySelectorAll('#zone-journal .journal-plier')].find(b => b.dataset.semaine === c.sem), s = t.closest('.journal-semaine');
        const l = s.querySelector('.journal-ligne'), a = document.activeElement;
        return { y: scrollY, vh: innerHeight, filtre: window.__vueValeurs().journal, ouverte: t.getAttribute('aria-expanded'),
                 haut: Math.round(s.getBoundingClientRect().top), sommaire: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bas-sommaire')) || 0,
                 ligne: l ? Math.round(l.getBoundingClientRect().top) : null, focus: a.dataset.passage === c.passage && s.contains(a) };
      }, avantCompte);
      verifier('au téléphone (' + dit + '), toucher le premier compte d’une semaine filtre le journal, déplie la semaine et la monte sous le sommaire : son premier plan est à l’écran, la page n’est pas remontée (M10)',
        apresCompte.filtre === avantCompte.passage && apresCompte.ouverte === 'true' && apresCompte.ligne !== null && apresCompte.ligne > apresCompte.sommaire &&
        apresCompte.ligne < apresCompte.vh && apresCompte.y >= avantCompte.y && Math.abs(apresCompte.haut - (apresCompte.sommaire + 4)) <= 2 && apresCompte.focus,
        JSON.stringify([avantCompte, apresCompte]));
      // 2. Ouvrir S41 (troisième semaine, pliée) : son nom reste sous le doigt, la page ne bouge pas.
      await gj.evaluate(() => { document.querySelector('#filtre-journal button[data-journal=""]').click(); });
      await gj.waitForTimeout(300);
      await gj.evaluate(() => document.querySelectorAll('#zone-journal .journal-plier[aria-expanded="true"]').forEach(b => b.click()));
      await gj.waitForTimeout(300);
      await gj.evaluate(() => document.querySelectorAll('#zone-journal .journal-plier')[2].scrollIntoView({ block: 'center' }));
      await gj.waitForTimeout(300);
      const avantS41 = await nomSemaine(gj, 2);
      await toucher(gj, true, { s: '#zone-journal .journal-plier', i: 2 });
      const ouvertS41 = await nomSemaine(gj, 2);
      verifier('au téléphone (' + dit + '), ouvrir ' + avantS41.sem + ' garde son nom à ±2 px sous le doigt, et la page ne remonte pas (NOUVEAU-2 : elle sautait de 400 à 800 px)',
        avantS41.ouvert === 'false' && ouvertS41.ouvert === 'true' && Math.abs(ouvertS41.nom - avantS41.nom) <= 2 && ouvertS41.y >= avantS41.y && ouvertS41.focus,
        JSON.stringify([avantS41, ouvertS41]));
      // 3. La replier : rien ne bouge non plus.
      await toucher(gj, true, { s: '#zone-journal .journal-plier', i: 2 });
      const plieS41 = await nomSemaine(gj, 2);
      verifier('au téléphone (' + dit + '), la replier aussitôt : son nom ne bouge pas, la page non plus',
        plieS41.ouvert === 'false' && Math.abs(plieS41.nom - avantS41.nom) <= 2 && Math.abs(plieS41.y - avantS41.y) <= 2, JSON.stringify([avantS41, plieS41]));
      // 4. Replier une semaine lue de loin, son nom collé sous le sommaire : son nom reste là, à l'écran.
      await gj.evaluate(() => document.querySelectorAll('#zone-journal .journal-plier')[0].click());
      await gj.waitForTimeout(300);
      await gj.evaluate(() => { const l = document.querySelectorAll('#zone-journal .journal-semaine')[0].querySelectorAll('.journal-ligne'); l[Math.min(8, l.length - 1)].scrollIntoView({ block: 'center' }); });
      await gj.waitForTimeout(300);
      const colle = await nomSemaine(gj, 0);
      await toucher(gj, true, { s: '#zone-journal .journal-plier', i: 0 });
      const replie = await nomSemaine(gj, 0);
      const sommaireJ = await gj.evaluate(() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bas-sommaire')) || 0);
      verifier('au téléphone (' + dit + '), replier une semaine dont le nom était collé en haut : le nom reste à sa place, sous le sommaire, à l’écran',
        colle.ouvert === 'true' && replie.ouvert === 'false' && Math.abs(replie.nom - colle.nom) <= 2 && replie.nom >= sommaireJ && replie.y < colle.y,
        JSON.stringify([colle, replie, sommaireJ]));
      await gj.__ctx.close();
    }
    // Sur grand écran, rien ne change : la ligne d'une semaine reste sous le pointeur.
    for (const o of [{ largeur: 1440, hauteur: 900, schema: 'light' }, { largeur: 1024, hauteur: 768, schema: 'dark' }]) {
      const gj = await vivanteJ(o);
      await gj.evaluate(() => document.querySelectorAll('#zone-journal .journal-plier[aria-expanded="true"]').forEach(b => b.click()));
      await gj.waitForTimeout(300);
      await gj.evaluate(() => document.querySelectorAll('#zone-journal .journal-plier')[2].scrollIntoView({ block: 'center' }));
      await gj.waitForTimeout(300);
      const a = await nomSemaine(gj, 2);
      await toucher(gj, false, { s: '#zone-journal .journal-plier', i: 2 });
      const b = await nomSemaine(gj, 2);
      verifier('à ' + o.largeur + ' px (' + o.schema + '), ouvrir une semaine garde son nom sous le pointeur et la page immobile',
        b.ouvert === 'true' && Math.abs(b.nom - a.nom) <= 2 && Math.abs(b.y - a.y) <= 2, JSON.stringify([a, b]));
      await gj.__ctx.close();
    }

    // --- S2 : le rythme requis du bloc par groupe, arrondi comme partout (rythmeDit) : « 38/sem. », plus « 38,1 ».
    {
      const gj = await vivanteJ({ largeur: 1440, hauteur: 900, schema: 'light' });
      await gj.selectOption('#dim-critique', 'sequence'); await gj.waitForTimeout(600);
      const lignes = await gj.evaluate(() => [...document.querySelectorAll('#zone-critique .critique-ligne')].map(l => ({
        g: l.dataset.groupe, requis: ((l.querySelector('.requis') || {}).textContent || '').trim(),
        titre: (l.querySelector('.critique-effort') || {}).title || '', lu: (l.querySelector('.masque') || {}).textContent || '' })).filter(x => x.requis));
      const gros = lignes.filter(x => { const n = parseFloat(x.requis.replace(',', '.')); return n >= 10; });
      verifier('le rythme requis d’un groupe d’au moins 10 plans par semaine s’écrit en entier, à l’œil, dans sa bulle et pour un lecteur d’écran (« 38/sem. », plus « 38,1 ») (S2)',
        gros.length >= 2 && gros.every(x => { const m = x.requis.match(/^(\d+)\/sem\.$/); return m && x.titre.indexOf(' : ' + m[1] + ' par semaine ;') !== -1 && x.lu.indexOf('Rythme requis : ' + m[1] + ' plans par semaine') !== -1; }),
        JSON.stringify(lignes.map(x => [x.g, x.requis])));
      const cible = gros[0] || lignes[0];
      await gj.evaluate(g => [...document.querySelectorAll('#zone-critique .critique-ligne')].find(l => l.dataset.groupe === g).click(), cible.g);
      await gj.waitForTimeout(400);
      await gj.click('#filtrer-groupe-page'); await gj.waitForTimeout(800);
      const graphe = await gj.evaluate(g => ({
        mots: [...document.querySelectorAll('svg text')].map(t => t.textContent.trim()).filter(t => /^requis \d/.test(t)),
        ligne: (([...document.querySelectorAll('#zone-critique .critique-ligne')].find(l => l.dataset.groupe === g) || document).querySelector('.requis') || {}).textContent }), cible.g);
      verifier('la page filtrée sur « Séquence ' + cible.g + ' », la ligne du bloc et la droite « requis » du graphique disent le même entier (S2)',
        graphe.mots.length === 1 && graphe.mots[0] === 'requis ' + cible.requis && graphe.ligne === cible.requis, JSON.stringify([cible.requis, graphe]));
      await gj.click('#filtrer-groupe-page'); await gj.waitForTimeout(500);

      // --- S10 : une référence de la liste dépliée ouvre la fiche du plan comme partout ailleurs (montrerCePlan).
      await gj.selectOption('#dim-critique', 'ata'); await gj.waitForTimeout(600);
      await gj.evaluate(() => { const l = [...document.querySelectorAll('#zone-critique .critique-ligne')].find(x => x.dataset.groupe === '21');
        if (l.getAttribute('aria-expanded') !== 'true') l.click(); });
      await gj.waitForTimeout(500);
      const ouvrirAuClavier = async (ref) => {
        await gj.evaluate(r => { const j = document.querySelector('#zone-critique .jeton-ud[data-ud="' + r + '"]'); j.scrollIntoView({ block: 'center' }); j.focus(); }, ref);
        await gj.keyboard.press('Enter'); await gj.waitForTimeout(900);
        const fiche = await gj.evaluate(() => ({ focus: document.activeElement.id, fiche: !document.getElementById('fiche-plan').hidden,
          ref: ((document.querySelector('#fiche-plan .fiche-plan-tete .ref') || {}).textContent || '').trim(), lignes: document.querySelectorAll('#corps-tableau tr').length }));
        await gj.keyboard.press('Escape'); await gj.waitForTimeout(700);
        const retour = await gj.evaluate(() => { const a = document.activeElement, r = a.getBoundingClientRect();
          return { ud: a.dataset.ud || a.tagName, jeton: a.classList.contains('jeton-ud') && !!a.closest('#zone-critique'), aLEcran: r.top >= 0 && r.bottom <= innerHeight, fiche: !document.getElementById('fiche-plan').hidden }; });
        return { fiche, retour };
      };
      const ref1 = await gj.evaluate(() => document.querySelector('#zone-critique .jeton-ud').dataset.ud);
      const r1 = await ouvrirAuClavier(ref1);
      verifier('Entrée sur une référence de la liste d’ATA 21 : la fiche du plan s’ouvre, le focus sur son titre, le tableau réduit à ce plan (S10 : le focus tombait sur le corps de la page)',
        r1.fiche.focus === 'titre-fiche-plan' && r1.fiche.fiche && r1.fiche.ref === ref1 && r1.fiche.lignes === 1, JSON.stringify(r1.fiche));
      verifier('puis Échap ferme la fiche et rend le focus à cette référence de la liste, à l’écran (S10 : il allait au tableau)',
        !r1.retour.fiche && r1.retour.ud === ref1 && r1.retour.jeton && r1.retour.aLEcran, JSON.stringify(r1.retour));
      // Une référence montrée par « Voir les N autres plans » (Séquence 600, 292 plans) : la liste reste dépliée, le focus y revient.
      await gj.selectOption('#dim-critique', 'sequence'); await gj.waitForTimeout(600);
      await gj.evaluate(() => { const l = [...document.querySelectorAll('#zone-critique .critique-ligne')].find(x => x.dataset.groupe === '600');
        if (l.getAttribute('aria-expanded') !== 'true') l.click(); });
      await gj.waitForTimeout(500);
      const plus = await gj.$('#zone-critique button[data-plus-refs][aria-expanded="false"]');
      if (plus) { await plus.click(); await gj.waitForTimeout(400); }
      const ref2 = await gj.evaluate(() => { const j = document.querySelectorAll('#zone-critique .jeton-ud'); return j[j.length - 1].dataset.ud; });
      const r2 = await ouvrirAuClavier(ref2);
      verifier('une référence montrée par « Voir les N autres plans » : la fiche s’ouvre sur son titre, Échap rend le focus à cette référence, la liste toujours dépliée',
        !!plus && r2.fiche.focus === 'titre-fiche-plan' && r2.fiche.ref === ref2 && r2.retour.ud === ref2 && r2.retour.jeton && r2.retour.aLEcran, JSON.stringify(r2));
      // À la souris, la croix de la fiche fait de même.
      const ref3 = await gj.evaluate(() => document.querySelectorAll('#zone-critique .jeton-ud')[1].dataset.ud);
      await gj.evaluate(r => document.querySelector('#zone-critique .jeton-ud[data-ud="' + r + '"]').scrollIntoView({ block: 'center' }), ref3);
      await gj.click('#zone-critique .jeton-ud[data-ud="' + ref3 + '"]'); await gj.waitForTimeout(900);
      const titre3 = await gj.evaluate(() => document.activeElement.id);
      await gj.click('#fiche-plan .fiche-plan-fermer'); await gj.waitForTimeout(700);
      const retour3 = await gj.evaluate(() => ({ ud: document.activeElement.dataset.ud || document.activeElement.tagName, lignes: document.querySelectorAll('#corps-tableau tr').length }));
      verifier('à la souris : un clic sur une référence de la liste ouvre sa fiche (focus sur le titre) ; sa croix rend le focus à la référence et le tableau à tous les plans',
        titre3 === 'titre-fiche-plan' && retour3.ud === ref3 && retour3.lignes > 1, JSON.stringify([titre3, retour3]));
      await gj.__ctx.close();
    }
    // Au téléphone, toucher une référence de la liste ouvre aussi la fiche, et sa croix ramène à la liste.
    {
      const gj = await vivanteJ({ largeur: 390, hauteur: 844, schema: 'dark', mobile: true });
      await gj.evaluate(() => { const l = [...document.querySelectorAll('#zone-critique .critique-ligne')].find(x => x.dataset.groupe === '21');
        l.scrollIntoView({ block: 'center' }); if (l.getAttribute('aria-expanded') !== 'true') l.click(); });
      await gj.waitForTimeout(500);
      const ref = await gj.evaluate(() => { const j = document.querySelectorAll('#zone-critique .jeton-ud')[3]; j.scrollIntoView({ block: 'center' }); return j.dataset.ud; });
      await gj.waitForTimeout(300);
      await toucher(gj, true, '#zone-critique .jeton-ud[data-ud="' + ref + '"]');
      await gj.waitForTimeout(500);
      const fiche = await gj.evaluate(() => { const f = document.getElementById('fiche-plan'), r = f.getBoundingClientRect(); return { focus: document.activeElement.id, vue: !f.hidden && r.top >= 0 && r.top < innerHeight / 2 }; });
      await toucher(gj, true, '#fiche-plan .fiche-plan-fermer');
      await gj.waitForTimeout(300);
      const retour = await gj.evaluate(() => { const a = document.activeElement, r = a.getBoundingClientRect(); return { ud: a.dataset.ud || a.tagName, aLEcran: r.top >= 0 && r.bottom <= innerHeight }; });
      verifier('au téléphone (390 × 844, sombre), toucher une référence de la liste ouvre sa fiche en haut de l’écran ; sa croix ramène à la référence, à l’écran (S10)',
        fiche.focus === 'titre-fiche-plan' && fiche.vue && retour.ud === ref && retour.aLEcran, JSON.stringify([ref, fiche, retour]));
      await gj.__ctx.close();
    }
    try { fsJ.unlinkSync(fichierJ); } catch (e) { /* déjà parti */ }
  }
  /* (fin du lot J) */


  // =================================================================
  //  Débrief 29, lot PL — le tableau des plans : ses vérifications se placent ici,
  //  dans un bloc { … } qui ouvre et ferme ses propres pages.
  // =================================================================
  /* (début du lot PL) */
  /* Débrief 29, lot PL — le tableau des plans : le bouton mort « Filtrer
     par colonne » supprimé pour de bon, la vue essentielle sans rangée de
     groupes, les intitulés au bord gauche de leurs cases (poignée hors du
     flux), la Mono gardée aux références et aux codes, « - » écrit « — »,
     la portée des filtres de la page dite avant l'usage (recherche, tuiles
     de la Synthèse), le focus gardé sur la puce « non renseigné », le
     changement de base annoncé, une case atteinte au clavier jamais
     couverte. Sur l'aperçu (jeu d'exemple, seconde base SEE), un nouveau
     venu (vue essentielle). */
  section('Débrief 29 : le tableau des plans (lot PL)');
  {
    const lum29 = () => {
      window.__lum29 = c => { const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
      window.__cr29 = (a, b) => { const x = window.__lum29(a), y = window.__lum29(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    };
    const versPlans = async pg => { await pg.evaluate(() => document.getElementById('section-plans').scrollIntoView()); await pg.waitForTimeout(300); };
    /* Aucun bouton « Filtrer » / « Filtrer par colonne » nulle part dans la section. */
    const boutonFiltrer = pg => pg.evaluate(() => ({
      element: !!document.getElementById('ouvrir-filtres'),
      vus: [...document.querySelectorAll('#section-plans button')].filter(b => b.getClientRects().length && /^Filtrer( par colonne)?\b/.test(b.textContent.trim()) && !/^Filtrer la page/.test(b.textContent.trim())).map(b => b.textContent.trim()),
      actions: (a => !!a && a.getClientRects().length > 0)(document.getElementById('actions-tableau'))
    }));
    /* Le bord gauche de l'intitulé, du champ « filtrer » et des cases de chaque colonne. */
    const alignement = pg => pg.evaluate(() => {
      const ths = [...document.querySelectorAll('#tete-tableau tr.titres th')];
      const fils = [...document.querySelectorAll('#tete-tableau tr.filtres th')];
      const ligne = document.querySelector('#corps-tableau tr');
      const ecarts = [], poignees = [];
      ths.forEach((th, i) => {
        const b = th.querySelector('button[data-tri]'), inp = fils[i] && fils[i].querySelector('input'), td = ligne && ligne.cells[i];
        if (!b || !inp || !td || td.getClientRects().length === 0) return;
        const bord = td.getBoundingClientRect().left + parseFloat(getComputedStyle(td).paddingLeft);
        const e = Math.max(Math.abs(b.getBoundingClientRect().left - bord), Math.abs(inp.getBoundingClientRect().left - bord));
        if (e > 1) ecarts.push(th.dataset.cle + ':' + Math.round(e));
        const p = th.querySelector('.poignee');
        if (p) { const r = p.getBoundingClientRect(); poignees.push({ cle: th.dataset.cle, l: r.width, h: r.height, empiete: r.right - b.getBoundingClientRect().left }); }
      });
      return { n: ths.length, ecarts, poignees };
    });
    /* La police des cases d'une colonne (la première case non vide). */
    const police = (pg, cle) => pg.evaluate(cle => {
      const ths = [...document.querySelectorAll('#tete-tableau tr.titres th')];
      const i = ths.findIndex(t => t.dataset.cle === cle);
      if (i < 0) return null;
      const td = [...document.querySelectorAll('#corps-tableau tr')].map(tr => tr.cells[i]).find(c => c && !c.classList.contains('tiret-vide'));
      if (!td) return null;
      const el = td.querySelector('.num, .ref-plan') || td;
      return { famille: getComputedStyle(el).fontFamily.split(',')[0].replace(/["']/g, '').trim(), chiffres: getComputedStyle(el).fontVariantNumeric, texte: td.textContent.trim() };
    }, cle);
    /* La case qui a le focus est-elle entièrement visible (coins et centre) ? */
    const caseVue = pg => pg.evaluate(() => {
      const a = document.activeElement, td = a && a.closest ? a.closest('#corps-tableau td') : null;
      if (!td) return { ok: false, quoi: a ? a.tagName : null };
      const r = td.getBoundingClientRect();
      const ok = [[r.left + 3, r.top + 3], [r.right - 3, r.bottom - 3], [r.left + r.width / 2, r.top + r.height / 2]]
        .every(([x, y]) => { const e = document.elementFromPoint(x, y); return !!e && (e === td || td.contains(e)); });
      const th = document.querySelectorAll('#tete-tableau tr.titres th')[td.cellIndex];
      return { ok, cle: th ? th.dataset.cle : '?', r: [r.left, r.top, r.right, r.bottom].map(Math.round) };
    });
    const parcourir = async (pg, touches, cachees) => {
      for (const [touche, n] of touches) for (let k = 0; k < n; k++) {
        await pg.keyboard.press(touche);
        const v = await caseVue(pg);
        if (!v.ok) cachees.push(touche + ' ' + v.cle + ' ' + JSON.stringify(v.r || v.quoi));
      }
    };

    // --- 1. Le nouveau venu, 1440 × 900, clair.
    const c29 = await contexte({ prefsVierges: true, viewport: { width: 1440, height: 900 } });
    const q = await page(c29, 'lot PL');
    await q.evaluate(lum29);
    await versPlans(q);
    const ouvert = await q.evaluate(() => {
      const barre = document.getElementById('barre-tableau');
      const vus = [...barre.children].filter(e => e.getClientRects().length > 0 && e.getBoundingClientRect().width > 0).map(e => e.id || e.className);
      return { vus, groupes: document.querySelectorAll('#tete-tableau tr.groupes').length, haut: (document.querySelector('#tete-tableau tr.titres th') || {}).style.top,
        puce: !!document.querySelector('#incomplets .puce-vide'), vue: [...document.querySelectorAll('#vue-tableau button[aria-pressed="true"]')].map(b => b.dataset.vue).join() };
    });
    const f0 = await boutonFiltrer(q);
    verifier('plus de bouton « Filtrer par colonne » : ni dans la page, ni visible, et la zone des actions vide ne prend aucune place (débrief 29)',
      !f0.element && f0.vus.length === 0 && !f0.actions, JSON.stringify(f0));
    verifier('sous la recherche, la puce « … non renseigné » est seule sur sa rangée : ni trou, ni bouton à droite (débrief 29)',
      ouvert.puce && ouvert.vus.length === 1 && ouvert.vus[0] === 'incomplets', JSON.stringify(ouvert.vus));
    verifier('vue essentielle : pas de rangée de groupes, les intitulés collent en haut du cadre (P-F15)',
      ouvert.vue === 'essentielle' && ouvert.groupes === 0 && ouvert.haut === '0px', JSON.stringify(ouvert));

    const al1 = await alignement(q);
    verifier('vue essentielle : intitulé, champ « filtrer » et cases de chaque colonne partagent le même bord gauche, à 1 px près (beauté NOUVEAU-3)',
      al1.n > 4 && al1.ecarts.length === 0 && al1.poignees.length > 0, JSON.stringify(al1.ecarts));
    verifier('la poignée de déplacement, hors du flux, garde sa zone (19 × 24 px au moins) sans empiéter sur l’intitulé',
      al1.poignees.every(p => p.l >= 19 && p.h >= 24 && p.empiete <= 0.5), JSON.stringify(al1.poignees.slice(0, 3)));

    const pol = {};
    for (const k of ['reference', 'avancement', 'ecp', 'ata', 'sequence', 'date_creation', 'validation_definition_electrique', 'avancement_concept_harnais_2']) pol[k] = await police(q, k);
    const sans = k => pol[k] && pol[k].famille === 'IBM Plex Sans' && /tabular-nums/.test(pol[k].chiffres);
    const mono = k => pol[k] && pol[k].famille === 'IBM Plex Mono';
    verifier('dates, nombres et Oui/Non en Plex Sans à chiffres alignés ; la Mono reste à la référence, à l’ECP et aux codes de GATES (B5, D2)',
      sans('ata') && sans('sequence') && sans('date_creation') && sans('validation_definition_electrique') && sans('avancement_concept_harnais_2') &&
      mono('reference') && mono('avancement') && mono('ecp'), JSON.stringify(pol));

    // La recherche dit sa portée avant qu'on tape.
    const portee = await q.evaluate(() => {
      const inp = document.getElementById('recherche'), id = inp.getAttribute('aria-describedby'), p = id && document.getElementById(id);
      if (!p) return { id };
      const ri = inp.getBoundingClientRect(), rp = p.getBoundingClientRect();
      const fin = document.elementFromPoint(rp.left + rp.width / 2, rp.top + rp.height / 2);
      return { id, texte: p.textContent.trim(), vu: rp.width > 0 && rp.height > 0, dedans: rp.left >= ri.left && rp.right <= ri.right && rp.top >= ri.top && rp.bottom <= ri.bottom,
        entonnoir: !!p.querySelector('svg[aria-hidden="true"]'), clic: fin === inp, place: parseFloat(getComputedStyle(inp).paddingRight) >= ri.right - rp.left,
        cr: window.__cr29(getComputedStyle(p).color, getComputedStyle(inp).backgroundColor) };
    });
    verifier('la recherche des plans dit « filtre toute la page » (entonnoir), dans le champ, sans prendre le clic, et le champ la nomme (aria-describedby) (F5)',
      portee.texte === 'filtre toute la page' && portee.vu && portee.dedans && portee.entonnoir && portee.clic && portee.place, JSON.stringify(portee));
    verifier('« filtre toute la page » se lit : 4,5:1 au moins sur le champ, en clair', portee.cr >= 4.5, String(portee.cr));

    // Les tuiles de la Synthèse disent aussi qu'elles filtrent toute la page.
    const tuiles = await q.evaluate(() => [...document.querySelectorAll('#etats .etat-btn')].map(b => ({
      code: b.querySelector('.libelle').textContent.trim(), titre: b.title, nom: b.getAttribute('aria-label'), n: b.querySelector('.etat-n').textContent.trim(), presse: b.getAttribute('aria-pressed') })));
    const plansDe = n => n + (parseInt(n.replace(/\s/g, ''), 10) > 1 ? ' plans' : ' plan');
    verifier('chaque tuile de la Synthèse dit « Filtrer toute la page sur CODE » (survol) et « …, N plans » aux lecteurs d’écran (F5)',
      tuiles.length > 2 && tuiles.every(t => t.presse === 'false' && t.titre === 'Filtrer toute la page sur ' + t.code && t.nom === 'Filtrer toute la page sur ' + t.code + ', ' + plansDe(t.n)),
      JSON.stringify(tuiles.slice(0, 3)));
    await q.click('#etats .etat-btn >> nth=1'); await q.waitForTimeout(500);
    const presse = await q.evaluate(() => { const b = document.querySelector('#etats .etat-btn[aria-pressed="true"]'); return b ? { titre: b.title, nom: b.getAttribute('aria-label') } : null; });
    verifier('la tuile pressée dit « Retirer le filtre », sans nom imposé (son texte se lit)', !!presse && presse.titre === 'Retirer le filtre' && presse.nom === null, JSON.stringify(presse));
    await reinitialiser(q);
    await versPlans(q);

    // X-A1 : la puce « non renseigné » garde le focus.
    await q.focus('#incomplets .puce-vide');
    await q.keyboard.press('Enter'); await q.waitForTimeout(400);
    const pu1 = await q.evaluate(() => { const a = document.activeElement; return { classe: a.className, vide: a.dataset && a.dataset.vide, presse: a.getAttribute('aria-pressed') }; });
    await q.keyboard.press('Enter'); await q.waitForTimeout(400);
    const pu2 = await q.evaluate(() => { const a = document.activeElement; return { classe: a.className, vide: a.dataset && a.dataset.vide, presse: a.getAttribute('aria-pressed') }; });
    verifier('Entrée sur la puce « … non renseigné » : le focus reste sur la puce redessinée, pressée puis relâchée (X-A1)',
      pu1.classe === 'puce-vide' && !!pu1.vide && pu1.presse === 'true' && pu2.classe === 'puce-vide' && pu2.presse === 'false', JSON.stringify([pu1, pu2]));

    // X-A5 : changer de base se dit ; toujours aucun bouton « Filtrer ».
    await q.evaluate(() => {
      window.__annoncer(''); window.__annonces29 = [];
      new MutationObserver(() => { const t = document.getElementById('annonce').textContent; if (t) window.__annonces29.push(t); })
        .observe(document.getElementById('annonce'), { childList: true, characterData: true, subtree: true });
    });
    await q.click('#choix-base button[data-base="la"]');
    await q.waitForFunction(() => window.__annonces29.length > 0, null, { timeout: 4000 }).catch(() => {});
    const base1 = await q.evaluate(() => ({ dit: window.__annonces29.slice(), compte: document.getElementById('compte').textContent }));
    const f1 = await boutonFiltrer(q);
    await q.click('#choix-base button[data-base="ici"]');
    await q.waitForFunction(() => window.__annonces29.length > 1, null, { timeout: 4000 }).catch(() => {});
    const base2 = await q.evaluate(() => ({ dit: window.__annonces29.slice(), compte: document.getElementById('compte').textContent }));
    const f2 = await boutonFiltrer(q);
    verifier('passer à la base SEE se dit : « Base SEE affichée : N lignes », le compte affiché (X-A5)',
      base1.dit.length === 1 && base1.dit[0] === 'Base SEE affichée : ' + base1.compte && /lignes?$/.test(base1.compte), JSON.stringify(base1));
    verifier('revenir à GATES se dit : « Base GATES affichée : N plans » (X-A5)',
      base2.dit.length === 2 && base2.dit[1] === 'Base GATES affichée : ' + base2.compte && /plans?$/.test(base2.compte), JSON.stringify(base2));
    // Une fiche de plan ouverte : toujours pas de bouton.
    await q.click('#corps-tableau .ref-plan >> nth=2'); await q.waitForTimeout(600);
    const f3 = await boutonFiltrer(q);
    verifier('ni sur SEE, ni de retour sur GATES, ni fiche de plan ouverte : aucun bouton « Filtrer » ne revient (débrief 29)',
      [f1, f2, f3].every(f => !f.element && f.vus.length === 0 && !f.actions), JSON.stringify([f1, f2, f3]));
    await q.keyboard.press('Escape'); await q.waitForTimeout(500);

    // --- 2. « Toutes les colonnes » : sa rangée de groupes, « - » écrit « — ».
    await q.click('#vue-tableau button[data-vue="toutes"]'); await q.waitForTimeout(800);
    await versPlans(q);
    const toutes29 = await q.evaluate(() => {
      const ths = [...document.querySelectorAll('#tete-tableau tr.titres th')];
      const iv = ths.findIndex(t => t.dataset.cle === 'validite');
      const tiret = document.querySelector('#corps-tableau td.tiret-vide[title]');
      return { groupes: [...document.querySelectorAll('#tete-tableau tr.groupes th')].map(t => t.textContent.trim()),
        traits: [...document.querySelectorAll('#corps-tableau td')].filter(td => td.textContent.trim() === '-').length,
        tirets: document.querySelectorAll('#corps-tableau td.tiret-vide[title="« - » dans GATES"]').length,
        tiret: tiret ? { texte: tiret.textContent, police: getComputedStyle(tiret).fontFamily.split(',')[0].replace(/["']/g, ''), doux: tiret.classList.contains('doux') } : null, iv };
    });
    verifier('« Toutes les colonnes » garde sa rangée de groupes : le groupe suivi dit « Avancement (GATES · HDK AA 011) », aucune case vide (X-A11)',
      toutes29.groupes.indexOf('Avancement (GATES · HDK AA 011)') !== -1 && toutes29.groupes.every(g => g.length > 0) && toutes29.groupes.indexOf('HDK AA 011') === -1,
      JSON.stringify(toutes29.groupes.slice(0, 8)));
    verifier('« - » de l’extract s’écrit « — » en gris, en Plex Sans, et dit sa valeur brute au survol (B22)',
      toutes29.traits === 0 && toutes29.tirets > 0 && !!toutes29.tiret && toutes29.tiret.texte === '—' && toutes29.tiret.police === 'IBM Plex Sans' && toutes29.tiret.doux,
      JSON.stringify(toutes29));
    const polT = { validite: await police(q, 'validite'), a_traiter_par: await police(q, 'a_traiter_par'), quantite: await police(q, 'quantite'), cc: await police(q, 'cc') };
    verifier('« Toutes les colonnes » : Validité et A traiter par (codes de GATES) en Mono, Quantité et CC en Sans (B5)',
      !!polT.validite && polT.validite.famille === 'IBM Plex Mono' && !!polT.a_traiter_par && polT.a_traiter_par.famille === 'IBM Plex Mono' &&
      !!polT.quantite && polT.quantite.famille === 'IBM Plex Sans' && !!polT.cc && polT.cc.famille === 'IBM Plex Sans', JSON.stringify(polT));
    // Le filtre de colonne garde la valeur brute : « - » trouve les cases « — ».
    await q.fill('tr.filtres input[data-filtre="validite"]', '-'); await q.waitForTimeout(600);
    const filtre29 = await q.evaluate(iv => {
      const lignes = [...document.querySelectorAll('#corps-tableau tr')].filter(tr => tr.cells.length > iv && !tr.querySelector('.vide-message'));
      return { n: lignes.length, tous: lignes.every(tr => tr.cells[iv].textContent.trim() === '—' && tr.cells[iv].title === '« - » dans GATES') };
    }, toutes29.iv);
    verifier('le filtre de colonne lit toujours « - » : il garde les cases écrites « — » (B22)', filtre29.n > 0 && filtre29.tous, JSON.stringify(filtre29));
    await reinitialiser(q);
    // Trié sur Validité, dans les deux sens : les « — » (vides ou « - ») restent en bas.
    const triVides = async () => q.evaluate(iv => {
      const l = [...document.querySelectorAll('#corps-tableau tr:not(.ancien)')].filter(tr => tr.cells.length > iv).map(tr => tr.cells[iv].classList.contains('tiret-vide'));
      const premier = l.indexOf(true);
      return { n: l.length, vides: l.filter(Boolean).length, enBas: premier === -1 || l.slice(premier).every(Boolean) };
    }, toutes29.iv);
    await q.click('tr.titres button[data-tri="validite"]'); await q.waitForTimeout(600);
    const triA = await triVides();
    await q.click('tr.titres button[data-tri="validite"]'); await q.waitForTimeout(600);
    const triD = await triVides();
    verifier('trié sur Validité, croissant puis décroissant : les cases « — » (vides ou « - ») restent en bas (B22)',
      triA.vides > 0 && triA.enBas && triD.enBas && triA.n === triD.n, JSON.stringify([triA, triD]));
    await q.click('tr.titres button[data-tri="reference"]'); await q.waitForTimeout(600);
    const al2 = await alignement(q);
    verifier('« Toutes les colonnes » : intitulés, champs et cases au même bord gauche, à 1 px près', al2.n > 50 && al2.ecarts.length === 0, JSON.stringify(al2.ecarts.slice(0, 6)));

    // X-A3 à 1440 : ← → le long d'une ligne, ↓ ↑ sur 25 lignes.
    await versPlans(q);
    await q.evaluate(() => document.querySelectorAll('#corps-tableau .ref-plan')[4].focus());
    const cachees1440 = [];
    await parcourir(q, [['ArrowRight', 30], ['ArrowLeft', 30], ['ArrowDown', 25], ['ArrowUp', 25]], cachees1440);
    verifier('à 1440 × 900, 110 arrêts au clavier dans le tableau : aucune case couverte par les colonnes figées ni par les en-têtes collés (X-A3)',
      cachees1440.length === 0, JSON.stringify(cachees1440.slice(0, 5)));
    await c29.close();

    // --- 3. 720 × 450, filtre de la page posé (bandeau collé) : la case Séquence passe sous « Référence UD ».
    const c29b = await contexte({ prefsVierges: true, viewport: { width: 720, height: 450 } });
    const q2 = await page(c29b, 'lot PL 720');
    await q2.click('#etats .etat-btn >> nth=1'); await q2.waitForTimeout(500);
    await versPlans(q2);
    await q2.evaluate(() => document.querySelectorAll('#corps-tableau .ref-plan')[0].focus());
    const cachees720 = [];
    await parcourir(q2, [['ArrowDown', 3], ['ArrowRight', 8], ['ArrowLeft', 8], ['ArrowRight', 6], ['ArrowLeft', 2], ['ArrowDown', 25], ['ArrowUp', 25]], cachees720);
    await q2.click('#vue-tableau button[data-vue="toutes"]'); await q2.waitForTimeout(800);
    await versPlans(q2);
    await q2.evaluate(() => document.querySelectorAll('#corps-tableau .ref-plan')[2].focus());
    await parcourir(q2, [['ArrowRight', 20], ['ArrowLeft', 20]], cachees720);
    verifier('à 720 × 450, ← → et ↑ ↓ (vue essentielle filtrée, puis toutes les colonnes) : chaque case atteinte est entièrement visible (X-A3)',
      cachees720.length === 0, JSON.stringify(cachees720.slice(0, 5)));
    await c29b.close();

    // --- 4. Sombre : la portée de la recherche se lit.
    const c29c = await contexte({ prefsVierges: true, colorScheme: 'dark', viewport: { width: 1024, height: 768 } });
    const q3 = await page(c29c, 'lot PL sombre');
    await q3.evaluate(lum29);
    const sombre29 = await q3.evaluate(() => { const p = document.getElementById('portee-recherche'), inp = document.getElementById('recherche');
      return { cr: window.__cr29(getComputedStyle(p).color, getComputedStyle(inp).backgroundColor), bouton: !!document.getElementById('ouvrir-filtres') }; });
    verifier('en sombre, « filtre toute la page » tient 4,5:1 sur le champ ; pas de bouton « Filtrer par colonne »', sombre29.cr >= 4.5 && !sombre29.bouton, JSON.stringify(sombre29));
    await c29c.close();

    // --- 5. Téléphone 390 : la portée sous le champ, la loupe centrée, aucun « Filtrer ».
    const c29d = await contexte({ prefsVierges: true, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const q4 = await page(c29d, 'lot PL téléphone');
    await versPlans(q4);
    const tel29 = await q4.evaluate(() => {
      const inp = document.getElementById('recherche'), p = document.getElementById('portee-recherche'), loupe = inp.parentNode.querySelector('svg');
      const ri = inp.getBoundingClientRect(), rp = p.getBoundingClientRect(), rl = loupe.getBoundingClientRect();
      const puce = document.querySelector('#incomplets').getBoundingClientRect();
      const poignee = document.querySelector('#tete-tableau tr.titres th .poignee');
      return { dessous: rp.top >= ri.bottom && rp.left >= ri.left - 1, loupe: Math.abs((rl.top + rl.height / 2) - (ri.top + ri.height / 2)), pasDeChevauchement: puce.top >= rp.bottom,
        police: parseFloat(getComputedStyle(inp).fontSize), large: document.documentElement.scrollWidth <= 390,
        poignee: poignee ? Math.round(poignee.getBoundingClientRect().height) : 0 };
    });
    const f4 = await boutonFiltrer(q4);
    verifier('au téléphone : « filtre toute la page » sous le champ, la loupe centrée sur le champ, rien ne chevauche, pas de défilement de côté',
      tel29.dessous && tel29.loupe <= 2 && tel29.pasDeChevauchement && tel29.police >= 16 && tel29.large, JSON.stringify(tel29));
    verifier('au téléphone : aucun bouton « Filtrer », et la poignée d’une colonne offre 44 px de haut au doigt',
      !f4.element && f4.vus.length === 0 && tel29.poignee >= 44, JSON.stringify([f4, tel29.poignee]));
    await c29d.close();
  }
  /* (fin du lot PL) */


  // =================================================================
  //  Débrief 29, lot I — impression, pied, téléphone : ses vérifications se placent ici,
  //  dans un bloc { … } qui ouvre et ferme ses propres pages.
  // =================================================================
  /* (début du lot I) */
  section('Débrief 29 : impression, haut de page, couche tactile, téléphone (lot I)');
  {
    /* La page vivante, servie par le vrai serveur sur le classeur du
       simulateur (comme la section du lot F) : HDK, sa tranche, son
       périmètre, sa base SEE — les vrais réglages du bandeau. */
    const fsI = require('fs'), osI = require('os');
    const { construireSimulateur } = require(path.join(__dirname, '..', '..', 'tests', 'construire-simulateur.js'));
    const { Feuille } = require(path.join(__dirname, '..', '..', 'tests', 'faux-classeur.js'));
    const simI = construireSimulateur({ date: '2026-10-29', avantPage: function (c, classeur) {
      const ths = classeur.getSheetByName('THS');
      classeur.feuilles.splice(1, 0, new Feuille('HDK Tranche 2', ths.valeurs.map(l => l.slice()), false, ths.fusions.map(f => Object.assign({}, f))));
    } });
    const srvI = simI.contexte;
    simI.classeur.proprietaire = 'nathan@airbus.com';
    srvI.__emailScript = 'nathan@airbus.com';
    const fichierI = path.join(osI.tmpdir(), 'suivi-fwd-lot-i-' + process.pid + '.html');
    fsI.writeFileSync(fichierI, simI.page.replace(/<script>\s*\/\* Simulateur : google\.script\.run[\s\S]*?<\/script>/, ''));
    const vivanteI = async (o) => {
      const email = o.email || 'lecteur@airbus.com';
      const c = await nav.newContext({ viewport: { width: o.largeur || 1280, height: o.hauteur || 900 }, colorScheme: o.schema || 'light',
        isMobile: !!o.mobile, hasTouch: !!o.mobile, locale: 'en-US' });
      const pg = await c.newPage();
      brancher(pg, 'lot I ' + (o.largeur || 1280) + (o.mobile ? ' tactile' : ''));
      await pg.exposeFunction('__appel', (nom, args) => {
        if (typeof srvI[nom] !== 'function' || /_$/.test(nom)) throw new Error('fonction inconnue ' + nom);
        const avant = srvI.__emailLecteur; srvI.__emailLecteur = email;
        try { const r = srvI[nom].apply(null, JSON.parse(args)); return JSON.stringify(r === undefined ? null : r); } finally { srvI.__emailLecteur = avant; }
      });
      await pg.addInitScript(() => {
        window.SUIVI_FWD_BUDGET = 1e9;
        function chaine(ok, ko) {
          const c = { withSuccessHandler: f => chaine(f, ko), withFailureHandler: f => chaine(ok, f), withUserObject: () => chaine(ok, ko) };
          return new Proxy(c, { get(t, nom) {
            if (nom in t) return t[nom];
            if (typeof nom !== 'string') return undefined;
            return function () {
              const args = Array.prototype.slice.call(arguments);
              setTimeout(() => window.__appel(nom, JSON.stringify(args)).then(j => { if (ok) ok(JSON.parse(j)); },
                e => { if (ko) ko({ message: String(e.message || e).replace(/^Error: /, '') }); }), 40);
            };
          } });
        }
        window.google = { script: { run: chaine(null, null) } };
      });
      await pg.goto('file://' + fichierI);
      await pg.waitForFunction(() => document.documentElement.getAttribute('data-suivi-fwd') === 'pret', null, { timeout: 30000 });
      /* Les droits arrivent après l'ouverture : le pied nomme le responsable. */
      await pg.waitForFunction(() => (document.getElementById('pied-responsable') || {}).textContent ||
        getComputedStyle(document.getElementById('choix-admin')).visibility !== 'hidden', null, { timeout: 20000 }).catch(() => {});
      /* Le bandeau du simulateur, posé au-dessus de la page, n'existe pas
         devant le classeur : on le retire pour mesurer la vraie page. */
      await pg.evaluate(() => { const x = document.querySelector('.simulateur-bandeau'); if (x) x.remove(); window.scrollTo(0, 0); });
      await pg.waitForTimeout(600);
      pg.__ctx = c;
      return pg;
    };
    const boite = (pg, s) => pg.evaluate(s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect();
      return { x: Math.round(r.left), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height), b: Math.round(r.bottom + scrollY), r: Math.round(r.right) }; }, s);
    const lumI = c => { const m = c.match(/[\d.]+/g).slice(0, 3).map(Number); return (m[0] + m[1] + m[2]) / 3; };

    // --- P-F9 : l'impression. Chrome lit les règles de largeur sur la feuille en portrait (moins de 860 px)
    //     même quand la page sort à l'italienne : on l'imite par une fenêtre de 800 px en média « print ».
    for (const schema of ['light', 'dark']) {
      const gi = await vivanteI({ largeur: 1440, hauteur: 900, schema });
      await gi.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
      await gi.emulateMedia({ media: 'print', colorScheme: schema });
      const lireImp = () => gi.evaluate(() => {
        const e = document.querySelector('header.entete'), cs = getComputedStyle(e), h1 = document.querySelector('.masthead h1');
        const face = getComputedStyle(document.querySelector('.rapp-face')).gridTemplateColumns.split(' ').filter(Boolean).length;
        const f = document.getElementById('venn-rapprochement').getBoundingClientRect(), v = document.getElementById('verdicts-rapprochement').getBoundingClientRect();
        return { bordure: cs.borderImageSource, fond: cs.backgroundColor, titre: getComputedStyle(h1).color, semaine: getComputedStyle(document.getElementById('num-semaine')).color,
                 colonnes: face, coteACote: v.left >= f.right - 1 && v.top < f.bottom, hauteur: Math.round(document.getElementById('rapprochement').getBoundingClientRect().height) };
      });
      await redimensionner(gi, 800, 900);
      const etroite = await lireImp();
      /* A4 à l'italienne, 10 mm de marge : 1 047 × 718 px. */
      await redimensionner(gi, 1047, 718);
      const a4 = await lireImp();
      verifier('imprimée (' + schema + ') : le bandeau du titre sans aplat marine — ni bordure peinte ni fond —, le titre et la semaine à l’encre sombre (P-F9)',
        a4.bordure === 'none' && /rgba\(0, 0, 0, 0\)|transparent/.test(a4.fond) && lumI(a4.titre) < 80 && lumI(a4.semaine) < 80, JSON.stringify(a4));
      verifier('imprimée (' + schema + ') : la comparaison garde sa figure et ses verdicts côte à côte, même quand Chrome lit la largeur d’une feuille en portrait (P-F9)',
        etroite.colonnes === 2 && etroite.coteACote && a4.colonnes === 2 && a4.coteACote, JSON.stringify([etroite, a4]));
      verifier('imprimée (' + schema + ') : la comparaison tient sur une page A4 à l’italienne (moins de 718 px de haut)',
        a4.hauteur > 200 && a4.hauteur <= 718, JSON.stringify(a4));
      await gi.emulateMedia({ media: 'screen', colorScheme: schema });
      await gi.evaluate(() => window.dispatchEvent(new Event('afterprint')));
      await gi.__ctx.close();
    }

    // --- B15 : de 721 à 1 329 px, le bouton « haut de page » tient dans la marge, sans toucher les cartes.
    {
      const gb = await vivanteI({ largeur: 1024, hauteur: 768 });
      const res = [];
      for (const [l, h] of [[1024, 768], [1180, 800], [1280, 800], [800, 900]]) {
        await redimensionner(gb, l, h);
        await gb.evaluate(() => window.scrollTo(0, document.getElementById('section-plans').getBoundingClientRect().top + scrollY - 200));
        await gb.waitForTimeout(300);
        res.push(await gb.evaluate(() => {
          const bt = document.getElementById('haut-de-page'), r = bt.getBoundingClientRect();
          let bord = 0;
          for (const s of document.querySelectorAll('.panneau, footer.pied')) { const q = s.getBoundingClientRect(); if (q.width) bord = Math.max(bord, q.right); }
          return { l: innerWidth, vu: !bt.hidden, gauche: Math.round(r.left), droite: Math.round(r.right), taille: Math.round(r.width), bord: Math.round(bord), ecran: document.documentElement.clientWidth };
        }));
      }
      verifier('de 800 à 1 280 px, le bouton « haut de page » paraît dans la marge à droite des cartes : il ne touche ni leur bord ni leur marge intérieure (B15)',
        res.every(x => x.vu && x.taille === 28 && x.gauche > x.bord && x.droite <= x.ecran), JSON.stringify(res));
      await gb.__ctx.close();
    }

    // --- Au téléphone (390 × 844, tactile) : M16, M6, M15, X-A10.
    for (const schema of ['light', 'dark']) {
      const gt = await vivanteI({ largeur: 390, hauteur: 844, mobile: true, schema });
      if (schema === 'light') {
        // M16 : le bouton reste fixé à l'écran, là où l'on est ; la page ne s'allonge pas.
        const h0 = await gt.evaluate(() => document.documentElement.scrollHeight);
        await gt.evaluate(() => window.scrollTo(0, 4000)); await gt.waitForTimeout(300);
        await gt.evaluate(() => window.scrollBy(0, -200)); await gt.waitForTimeout(400);
        const bt = await gt.evaluate(h0 => {
          const b = document.getElementById('haut-de-page'), r = b.getBoundingClientRect();
          return { vu: !b.hidden, position: getComputedStyle(b).position, haut: Math.round(r.top), bas: Math.round(r.bottom), gauche: Math.round(r.left), droite: Math.round(r.right),
                   h0, h1: document.documentElement.scrollHeight, iw: innerWidth, ih: innerHeight };
        }, h0);
        verifier('au doigt, en remontant : le bouton « haut de page » est fixé à l’écran, en entier dans la fenêtre, et la page ne s’allonge pas (M16)',
          bt.vu && bt.position === 'fixed' && bt.haut >= 0 && bt.bas <= bt.ih && bt.gauche >= 0 && bt.droite <= bt.iw && bt.h1 === bt.h0, JSON.stringify(bt));
        await gt.evaluate(() => window.scrollTo(0, 0)); await gt.waitForTimeout(300);

        // M6 : les dernières cibles au doigt (la zone ::after comptée).
        const zone = (sel) => gt.evaluate(sel => [...document.querySelectorAll(sel)].filter(e => e.getClientRects().length).map(e => {
          const r = e.getBoundingClientRect(), a = getComputedStyle(e, '::after');
          let w = r.width, h = r.height, t = r.top, bo = r.bottom, l = r.left, ri = r.right;
          if (a.content && a.content !== 'none' && a.position === 'absolute') {
            if (a.top !== 'auto' && a.bottom !== 'auto') { t = r.top + parseFloat(a.top); bo = r.bottom - parseFloat(a.bottom); h = Math.max(h, bo - t); }
            if (a.left !== 'auto' && a.right !== 'auto') { l = r.left + parseFloat(a.left); ri = r.right - parseFloat(a.right); w = Math.max(w, ri - l); }
          }
          return { w: Math.round(w), h: Math.round(h), t, b: bo, l, r: ri, nom: (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 24) };
        }), sel);
        const comptes = await zone('#zone-journal .compte-passage');
        let chevauchent = 0;
        for (let i = 0; i < comptes.length; i++) for (let j = i + 1; j < comptes.length; j++) {
          const a = comptes[i], z = comptes[j];
          if (a.l < z.r - 0.5 && z.l < a.r - 0.5 && a.t < z.b - 0.5 && z.t < a.b - 0.5) chevauchent++;
        }
        verifier('au doigt : chaque compte d’une semaine du journal offre 44 px à toucher, sans empiéter sur son voisin (M6)',
          comptes.length > 5 && comptes.every(x => x.h >= 44) && chevauchent === 0, JSON.stringify({ n: comptes.length, petits: comptes.filter(x => x.h < 44).slice(0, 3), chevauchent }));
        const petites = {};
        for (const [nom, sel, dim] of [['menu du titre « Par ATA »', 'select#dim-critique', 'h'], ['entrées du sommaire', '#sommaire-liste a', 'h'],
          ['champs « filtrer » des colonnes', 'table.plans thead .filtres input', 'h'], ['en-têtes de tri des plans', 'table.plans thead .titres th button:not(.poignee)', 'w'],
          ['en-têtes de tri de « Par ATA »', 'button.tri-groupe', 'w'], ['adresse du responsable, au pied', '#pied-responsable a', 'h']]) {
          const z = await zone(sel);
          const trop = z.filter(x => x[dim] < 44 || x.h < 44);
          if (!z.length || trop.length) petites[nom] = z.length ? trop.slice(0, 3) : 'absent';
        }
        verifier('au doigt : le menu du titre « Par ATA », le sommaire, les champs et les en-têtes de tri des colonnes, l’adresse du pied offrent tous 44 px (M6)',
          Object.keys(petites).length === 0, JSON.stringify(petites));
        const trait = await gt.evaluate(() => { const s = document.getElementById('dim-critique'), r = s.getBoundingClientRect(), cs = getComputedStyle(s);
          return { h: Math.round(r.height), ombre: cs.boxShadow, couches: cs.backgroundImage.split('),').length }; });
        verifier('au doigt : le menu du titre grandit à 44 px, son trait reste sous le mot (un trait peint, plus le bas de la case)',
          trait.h >= 44 && trait.ombre === 'none' && trait.couches >= 2, JSON.stringify(trait));
      }
      // M15 : un bandeau plus serré, des tuiles d'une ligne — toute la synthèse au premier écran.
      const m = {
        entete: await boite(gt, 'header.entete'), phrase: await boite(gt, '#phrase'), etats: await boite(gt, '#etats'),
        motAv: await boite(gt, '#choix-avancement .mot-reglage'), segAv: await boite(gt, '#choix-indicateur')
      };
      const tuiles = await gt.evaluate(() => [...document.querySelectorAll('#etats .etat-btn')].map(b => {
        const r = b.getBoundingClientRect(), n = b.querySelector('.etat-n').getBoundingClientRect(), lib = b.querySelector('.libelle'), l = lib.getBoundingClientRect(), pct = b.querySelector('.etat-pct');
        return { h: Math.round(r.height), uneLigne: n.left >= l.right - 1 && n.top < l.bottom && n.bottom > l.top, entier: lib.scrollWidth <= lib.clientWidth + 1 && getComputedStyle(lib).textOverflow !== 'ellipsis',
                 part: pct.textContent.trim() !== '' && pct.getBoundingClientRect().width <= 1, colonnes: getComputedStyle(b.parentNode).gridTemplateColumns.split(' ').length };
      }));
      verifier('téléphone (' + schema + ') : les tuiles des états tiennent sur une ligne — la valeur, son nombre à droite —, 44 px chacune, deux par rangée, les codes entiers (M15)',
        tuiles.length >= 5 && tuiles.every(t => t.h >= 44 && t.h <= 60 && t.uneLigne && t.entier && t.colonnes === 2) && m.etats.h <= 210, JSON.stringify({ etats: m.etats, tuiles: tuiles.slice(0, 3) }));
      verifier('téléphone (' + schema + ') : la part de chaque tuile s’efface à l’œil, mais reste écrite pour les lecteurs d’écran (M15)',
        tuiles.every(t => t.part), JSON.stringify(tuiles.map(t => t.part)));
      verifier('téléphone (' + schema + ') : le bandeau fait moins de 295 px (337 avant), la phrase de tête paraît avant 410 px (443 avant) et les sept tuiles finissent dans le premier écran (M15)',
        m.entete.h <= 295 && m.phrase.y <= 410 && m.etats.b <= 844, JSON.stringify(m));
      verifier('téléphone (' + schema + ') : à 390 px, le mot « Avancement » reste devant ses puces, sur leur ligne',
        m.motAv && m.segAv && m.motAv.r <= m.segAv.x && Math.abs((m.motAv.y + m.motAv.h / 2) - (m.segAv.y + m.segAv.h / 2)) <= 4, JSON.stringify(m));
      if (schema === 'light') {
        // X-A10 : le bandeau des filtres posés est une région nommée, hors du sommaire et du contenu.
        await gt.click('#etats .etat-btn'); await gt.waitForTimeout(600);
        const region = await gt.evaluate(() => {
          const f = document.getElementById('filtres-actifs'), j = document.getElementById('filtres-jetons');
          return { vu: !f.hidden, role: f.getAttribute('role'), nom: f.getAttribute('aria-label'), dedans: !!j && f.contains(j) && f.contains(document.getElementById('tout-effacer')),
                   ailleurs: !f.closest('main, nav, header, footer') };
        });
        verifier('un filtre posé : son bandeau est une région nommée « Filtres posés », qui tient les jetons et « Tout effacer » (X-A10)',
          region.vu && region.role === 'region' && region.nom === 'Filtres posés' && region.dedans && region.ailleurs, JSON.stringify(region));
        // M15, D7 : un code ne se coupe qu'après un « _ » ou une espace — à 390 px comme à 320 (le nombre repasse alors sous la valeur).
        const coupures = () => gt.evaluate(() => [...document.querySelectorAll('#etats .libelle')].map(lib => {
          const r = document.createRange(), tw = document.createTreeWalker(lib, NodeFilter.SHOW_TEXT), mauvaises = [];
          let n, haut = null, avant = '';
          while ((n = tw.nextNode())) for (let i = 0; i < n.length; i++) {
            r.setStart(n, i); r.setEnd(n, i + 1);
            const q = r.getClientRects()[0], ch = n.data[i];
            if (!q) continue;
            if (haut !== null && q.top > haut + 4 && !/[_\s]/.test(avant) && !/\s/.test(ch)) mauvaises.push(avant + '|' + ch);
            haut = q.top; avant = ch;
          }
          return mauvaises.length ? lib.textContent + ' (' + mauvaises.join(', ') + ')' : '';
        }).filter(Boolean));
        const coupe390 = await coupures();
        await redimensionner(gt, 320, 640);
        const coupe320 = await coupures();
        const pile320 = await gt.evaluate(() => [...document.querySelectorAll('#etats .etat-btn')].every(b => b.querySelector('.etat-n').getBoundingClientRect().top >= b.querySelector('.libelle').getBoundingClientRect().bottom - 1));
        verifier('téléphone : les codes des tuiles ne se coupent jamais au milieu d’un mot, à 390 px comme à 320 px (où le nombre passe sous la valeur) (M15, D7)',
          coupe390.length === 0 && coupe320.length === 0 && pile320, JSON.stringify({ coupe390, coupe320, pile320 }));
      }
      await gt.__ctx.close();
    }

    // --- M7 : le téléphone à l'italienne — la barre des états au premier écran.
    for (const [l, h, schema] of [[844, 390, 'light'], [844, 390, 'dark'], [667, 375, 'light']]) {
      const gl = await vivanteI({ largeur: l, hauteur: h, mobile: true, schema });
      const m = await gl.evaluate(() => {
        const r = s => { const e = document.querySelector(s); const q = e.getBoundingClientRect(); return { y: Math.round(q.top + scrollY), h: Math.round(q.height), b: Math.round(q.bottom + scrollY) }; };
        const mot = document.getElementById('mot-perimetre'), motR = mot.getBoundingClientRect();
        const t = document.querySelector('.masthead h1').getBoundingClientRect(), s = document.querySelector('.semaine').getBoundingClientRect();
        /* Les rangées des réglages : leurs hauts, regroupés à 15 px près. */
        const hauts = [...document.querySelectorAll('#portee .reglage')].filter(e => e.getClientRects().length).map(e => e.getBoundingClientRect().top).sort((a, b) => a - b);
        const rangees = hauts.reduce((n, y, i) => n + (i === 0 || y - hauts[i - 1] > 15 ? 1 : 0), 0);
        return { entete: r('header.entete'), barre: r('#barre'), rangees,
                 motCache: motR.width <= 1 && mot.textContent.trim() === 'Périmètre' && document.getElementById('choix-perimetre').getAttribute('aria-labelledby') === 'mot-perimetre',
                 uneLigne: Math.abs(t.bottom - s.bottom) < 12 && s.left >= t.right, defile: document.documentElement.scrollWidth - innerWidth };
      });
      verifier('à l’italienne (' + l + ' × ' + h + ', ' + schema + ') : le bandeau fait moins de 160 px (207 avant), les réglages sur deux rangées au plus, le titre et la semaine sur une ligne, et la barre des états finit dans le premier écran (M7)',
        m.entete.h <= 160 && m.rangees <= 2 && m.uneLigne && m.barre.b <= h && m.defile <= 0, JSON.stringify(m));
      verifier('à l’italienne (' + l + ' × ' + h + ', ' + schema + ') : « Périmètre » se tait à l’œil, mais nomme toujours ses puces pour les lecteurs d’écran',
        m.motCache, JSON.stringify(m));
      await gl.__ctx.close();
    }
    try { fsI.unlinkSync(fichierI); } catch (e) { /* déjà parti */ }
  }
  /* (fin du lot I) */

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

/* L'import de la base SEE sans Excel (menu Suivi FWD → Importer la base) :
   la vraie fenêtre, rendue par le vrai Code.gs, ouverte dans un vrai
   navigateur ; google.script.run y répond par les vraies fonctions du
   serveur, sur un classeur en mémoire (qui compte, comme Sheets, ses dix
   millions de cellules). Les fichiers sont fabriqués pour l'occasion
   (tests/fabriquer-xlsx.js) : chaînes partagées ou en ligne, chaînes riches,
   styles, préfixes, Zip64, CSV, pages web et XML 2003 nommés .xls. */
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const zlib = require('zlib');
const { chargerServeur } = require('./build-addon');
const { Feuille, Classeur } = require('./faux-classeur');
const { feuilleGates } = require('./feuille-gates');
const { xlsx } = require('./fabriquer-xlsx');

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
function section(t) { sectionCourante = t; console.log('\n— ' + t + ' —'); }

/* Un classeur : HDK (la vraie structure GATES), THS si demandé, et des onglets en plus. */
function classeur(options) {
  const opt = options || {};
  const g = feuilleGates(40);
  const feuilles = [new Feuille('HDK', g.valeurs.map(l => l.slice()), false, g.fusions)];
  if (opt.ths) { const t = feuilleGates(30); feuilles.push(new Feuille('THS', t.valeurs.map(l => l.slice()), false, t.fusions)); }
  (opt.autres || []).forEach(f => feuilles.push(f));
  return new Classeur(feuilles, 'Classeur SEE');
}
/* Les lignes d'un export SEE : titre, ligne vide, en-tête en ligne 3. */
const ENTETE_SEE = ['SCHEMA NUMBER', 'NAME', 'SOL.', 'Cust.V', 'Released Date', 'Validated Date', 'REDRAW', 'ARCHIVED'];
function nomDe(i) { return 'TFE' + String(311 + (i % 50)) + 'A' + String(600 + i).padStart(4, '0'); }
function lignesSEE(n, options) {
  const opt = options || {};
  const lignes = [['Nommage WD BFLOW'], [], ENTETE_SEE];
  for (let i = 0; i < n; i++) {
    lignes.push(['S-' + i, nomDe(i), opt.solNombre ? { n: (i % 3) + 1, fmt: 'zeros5' } : String((i % 3) + 1).padStart(3, '0'),
      opt.custV ? opt.custV(i) : ['A', 'B', 'C'][i % 3], { n: 45000 + i, fmt: 'date' }, i % 4 ? { n: 45100 + i, fmt: 'date' } : null, { b: i % 2 === 0 }, 'non']);
  }
  return lignes;
}
const nomsOnglets = c => c.getSheets().map(f => f.getName());
const sansImport = c => !nomsOnglets(c).some(x => /\((import|ancien) /.test(x));

(async () => {
  const nav = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const dossier = fs.mkdtempSync(path.join(os.tmpdir(), 'import-see-'));

  /* La fenêtre d'import pour un classeur : rendue par importerSecondeBase,
     ouverte dans le navigateur, google.script.run branché sur le serveur.
     page.__retard : un délai (ms) avant chaque lot, pour voir la fenêtre
     pendant l'envoi. */
  async function fenetre(ctx, modifier) {
    ctx.__dialogue = null;
    ctx.importerSecondeBase();
    let html = ctx.__dialogue.getContent();
    if (modifier) html = modifier(html);
    const fichierHtml = path.join(dossier, 'fenetre-' + Math.random().toString(36).slice(2) + '.html');
    fs.writeFileSync(fichierHtml, html);
    const page = await nav.newPage();
    page.on('pageerror', e => erreursJS.push(sectionCourante + ' : ' + e.message));
    page.on('console', m => { if (m.type() === 'error') erreursJS.push(sectionCourante + ' : ' + m.text()); });
    page.__appels = [];
    page.__retard = 0;
    await page.exposeFunction('__appelServeur', async (nom, args) => {
      page.__appels.push(nom);
      if (nom === 'importSecondeBaseLot' && page.__retard) await new Promise(r => setTimeout(r, page.__retard));
      try {
        const v = ctx[nom].apply(null, args);
        return { ok: true, valeur: v === undefined ? null : JSON.parse(JSON.stringify(v)) };
      } catch (e) { return { ok: false, message: e.message }; }
    });
    await page.addInitScript(() => {
      function chaine(ok, ko) {
        return new Proxy({}, { get: function (_, nom) {
          if (nom === 'withSuccessHandler') return function (f) { return chaine(f, ko); };
          if (nom === 'withFailureHandler') return function (f) { return chaine(ok, f); };
          return function () {
            const args = JSON.parse(JSON.stringify(Array.prototype.slice.call(arguments)));
            window.__appelServeur(nom, args).then(function (r) { if (r.ok) { if (ok) ok(r.valeur); } else if (ko) ko({ message: r.message }); });
          };
        } });
      }
      window.google = { script: { run: chaine(null, null), host: { close: function () { window.__fermee = true; } } } };
    });
    await page.goto('file://' + fichierHtml);
    return page;
  }
  async function attendreFin(page, delai) {
    await page.waitForFunction(() => /\bok\b|erreur/.test(document.getElementById('etat').className), null, { timeout: delai || 120000 });
    return page.evaluate(() => ({ classe: document.getElementById('etat').className, texte: document.getElementById('etat').textContent }));
  }
  async function importer(page, nom, contenu, options) {
    const opt = options || {};
    if (opt.contrat) await page.selectOption('#contrat', opt.contrat);
    if (opt.toutes) await page.check('#toutes'); else if (await page.isChecked('#toutes')) await page.uncheck('#toutes');
    await page.setInputFiles('#fichier', { name: nom, mimeType: 'application/octet-stream', buffer: contenu });
    const t0 = Date.now();
    await page.click('#importer');
    const etat = await attendreFin(page, opt.delai);
    return { etat, duree: Date.now() - t0 };
  }
  /* Le jeton d'une fenêtre ouverte par le menu. */
  function jetonDe(ctx) {
    ctx.importerSecondeBase();
    return /"jeton":"([0-9a-z]+)"/i.exec(ctx.__dialogue.getContent())[1];
  }

  // =================================================================
  section('Le menu, la garde et le jeton');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    ctx.onOpen();
    verifier('le menu Suivi FWD propose « Importer la base SEE »', ctx.__menu.indexOf('importerSecondeBase') !== -1, JSON.stringify(ctx.__menu));
    const jeton = jetonDe(ctx);
    ctx.__sansInterface = true;
    const refus = ['importerSecondeBase', 'importSecondeBaseDebut', 'importSecondeBaseLot', 'importSecondeBaseFin', 'importSecondeBaseAbandon'].map(n => {
      try { ctx[n]('faux-jeton-123', 'HDK', 3, 5); return n + ':passe'; } catch (e) { return /Geste refusé/.test(e.message) ? '' : n + ':' + e.message; }
    }).filter(Boolean);
    verifier('hors du classeur (la page du tableau de bord), sans le jeton de la fenêtre, chaque fonction de l’import est refusée', !refus.length, refus.join(' | '));
    let avecJeton = '';
    try { const d = ctx.importSecondeBaseDebut(jeton, 'HDK', 3, 5); ctx.importSecondeBaseAbandon(jeton, d.feuille); avecJeton = 'passe'; } catch (e) { avecJeton = e.message; }
    verifier('avec le jeton de la fenêtre ouverte par le menu, l’import passe même si l’interface ne répond pas', avecJeton === 'passe' && sansImport(c), avecJeton);
    ctx.__sansInterface = false;
    let arbitraire = '';
    try { ctx.importSecondeBaseLot(jeton, 'HDK', 1, [['écrasé']]); } catch (e) { arbitraire = e.message; }
    verifier('un lot ne s’écrit que dans l’onglet temporaire d’un import, jamais dans un autre (« HDK »)',
      /non reconnu/.test(arbitraire) && c.getSheetByName('HDK').valeurs[0][0] !== 'écrasé', arbitraire);
  }

  // =================================================================
  section('Un export SEE en .xlsx : seules l’en-tête et NAME, SOL., Cust.V vont au classeur');
  {
    const ancien = new Feuille('SEE HDK', [['vieux'], ['NAME', 'SOL.', 'Cust.V'], ['OLD1', '1', 'A']]);
    const c = classeur({ ths: true, autres: [ancien, new Feuille('Notes', [['x']])] });
    const ctx = chargerServeur(c, {});
    ctx.__activerCache();
    const avant = ctx.getDonneesPourClient('HDK');
    const place = nomsOnglets(c).indexOf('SEE HDK');
    const page = await fenetre(ctx);
    const ui = await page.evaluate(() => ({ contrat: document.getElementById('contrat').value, visible: !document.getElementById('ligne-contrat').hidden,
      cible: document.getElementById('cible').textContent, desactive: document.getElementById('importer').disabled }));
    verifier('la fenêtre propose le contrat et dit l’onglet qu’elle remplacera ; « Importer » attend un fichier',
      ui.visible && /Remplacera l’onglet « SEE HDK »/.test(ui.cible) && ui.desactive, JSON.stringify(ui));
    const n = 1500;
    /* Pendant l'envoi : « Fermer » éteint, la consigne affichée, la largeur de l'onglet temporaire mesurée. */
    const vrai = ctx.importSecondeBaseLot;
    const mesures = [];
    ctx.importSecondeBaseLot = function (j, nom) { const f = c.getSheetByName(nom); mesures.push(f.getMaxColumns() + '×' + f.getMaxRows()); return vrai.apply(null, arguments); };
    page.__retard = 400;
    await page.setInputFiles('#fichier', { name: 'Nommage WD BFLOW.xlsx', mimeType: 'application/octet-stream', buffer: xlsx({ onglets: [{ nom: 'Export', lignes: lignesSEE(n, { solNombre: true }) }] }) });
    await page.click('#importer');
    await page.waitForFunction(() => /Envoi au classeur|Préparation/.test(document.getElementById('progres').textContent), null, { timeout: 30000 });
    const pendant = await page.evaluate(() => ({ fermer: document.getElementById('fermer').disabled, consigne: !document.getElementById('consigne').hidden,
      lu: document.getElementById('etat').textContent }));
    const r = { etat: await attendreFin(page) };
    ctx.importSecondeBaseLot = vrai;
    verifier('pendant l’envoi, « Fermer » est éteint, « Ne pas fermer cette fenêtre avant la fin » s’affiche, et ce qui a été lu reste dit',
      pendant.fermer && pendant.consigne && /Fichier lu en \d+ s : 1 500 lignes, colonnes NAME, SOL\., Cust\.V/.test(pendant.lu), JSON.stringify(pendant));
    verifier('l’onglet temporaire est taillé d’avance : trois colonnes, les 1 501 lignes — pas les 26 colonnes d’un onglet neuf',
      mesures.length && mesures.every(x => x === '3×1501'), mesures.join(', '));
    const f = c.getSheetByName('SEE HDK');
    verifier('l’import réussit et le dit', /\bok\b/.test(r.etat.classe) && /1 500 lignes/.test(r.etat.texte) && /comparaison est prête/.test(r.etat.texte), r.etat.texte);
    verifier('l’onglet « SEE HDK » : la ligne d’en-tête puis les ' + n + ' lignes, trois colonnes seulement',
      !!f && f.valeurs.length === n + 1 && f.valeurs[0].join('|') === 'NAME|SOL.|Cust.V' && f.valeurs.every(l => l.length === 3),
      f && JSON.stringify([f.valeurs.length, f.valeurs[0], f.valeurs[1]]));
    verifier('un nombre au format « 00000 » garde ses zéros (SOL. 1 → 00001), en texte', f.valeurs[1][1] === '00001' && f.formats[0] === '@', JSON.stringify(f.valeurs[1]));
    verifier('l’ancien onglet est remplacé, à sa place ; aucun onglet temporaire ni « ancien » ne traîne',
      nomsOnglets(c).indexOf('SEE HDK') === place && sansImport(c) && f.valeurs[1][0] !== 'OLD1', nomsOnglets(c).join(', '));
    verifier('la grille est resserrée sur les données', f.getMaxRows() === n + 1 && f.getMaxColumns() === 3, f.getMaxRows() + ' × ' + f.getMaxColumns());
    const lu = ctx.lireSecondeBase(c, 'HDK');
    verifier('la page relit la base : référence trouvée, ' + n + ' lignes', lu.etat === 'ok' && lu.rapprochement.lignes.length === n, lu.etat);
    const apres = ctx.getDonneesPourClient('HDK');
    verifier('le paquet du tableau de bord, en cache avant l’import, est renouvelé : il porte la nouvelle base',
      avant.rapprochement.lignes.length === 1 && apres.rapprochement.lignes.length === n, avant.rapprochement.lignes.length + ' → ' + apres.rapprochement.lignes.length);
    verifier('THS reste sans base, intact', !c.getSheetByName('SEE THS') && !!c.getSheetByName('THS'));
    verifier('la fenêtre n’a appelé que les gestes prévus, en ordre',
      page.__appels[0] === 'importSecondeBaseDebut' && page.__appels[page.__appels.length - 1] === 'importSecondeBaseFin' &&
      page.__appels.slice(1, -1).every(x => x === 'importSecondeBaseLot'), page.__appels.join(','));
    /* Le même nombre de lignes, d'autres indices : le cache ne sert pas l'ancienne base. */
    const r2 = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'Export', lignes: lignesSEE(n, { custV: () => 'Z' }) }] }));
    const apres2 = ctx.getDonneesPourClient('HDK');
    verifier('réimporté avec le même nombre de lignes (indices changés) : le paquet en cache suit',
      /\bok\b/.test(r2.etat.classe) && apres2.rapprochement.lignes[0]['Cust.V'] === 'Z', JSON.stringify(apres2.rapprochement.lignes[0]));
    await page.close();
  }

  // =================================================================
  section('Le contrat proposé, l’onglet créé, et un onglet « HDK SEE »');
  {
    const c = classeur({ ths: true, autres: [new Feuille('SEE THS', [['NAME', 'SOL.', 'Cust.V'], ['X', '1', 'A']])] });
    const ctx = chargerServeur(c, {});
    c.setActiveSheet(c.getSheetByName('THS'));
    let page = await fenetre(ctx);
    const v1 = await page.$eval('#contrat', e => e.value);
    await page.close();
    c.setActiveSheet(c.getSheetByName('SEE THS'));
    page = await fenetre(ctx);
    const v2 = await page.$eval('#contrat', e => e.value);
    await page.close();
    verifier('le contrat proposé est celui de l’onglet affiché — ou dont la base est affichée', v1 === 'THS' && v2 === 'THS', v1 + ' / ' + v2);

    const seul = classeur();
    const ctxSeul = chargerServeur(seul, {});
    page = await fenetre(ctxSeul);
    const cible = await page.$eval('#cible', e => e.textContent);
    const r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(10) }] }));
    verifier('un seul contrat, pas encore de base : l’onglet créé est « SEE HDK » (il tiendra quand un second contrat arrivera)',
      /Créera l’onglet « SEE HDK »/.test(cible) && /\bok\b/.test(r.etat.classe) && !!seul.getSheetByName('SEE HDK') && !seul.getSheetByName('SEE'), cible + ' / ' + nomsOnglets(seul).join(', '));
    await page.close();

    const inverse = classeur({ ths: true, autres: [new Feuille('HDK SEE', [['NAME', 'SOL.', 'Cust.V'], ['OLD', '1', 'A']])] });
    const ctxInv = chargerServeur(inverse, {});
    page = await fenetre(ctxInv);
    const r2 = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(30) }] }), { contrat: 'HDK' });
    verifier('une base nommée « HDK SEE » (écriture admise) est remplacée sous ce nom, sans onglet qui traîne',
      /\bok\b/.test(r2.etat.classe) && inverse.getSheetByName('HDK SEE').valeurs.length === 31 && sansImport(inverse) && !inverse.getSheetByName('SEE HDK'),
      r2.etat.texte + ' / ' + nomsOnglets(inverse).join(', '));
    await page.close();
  }

  // =================================================================
  section('Les façons d’écrire un .xlsx');
  {
    const variantes = [
      { nom: 'chaînes en ligne, préfixe « x: », sans références, descripteurs de données, Zip64',
        spec: { chaines: 'inline', prefixe: 'x', sansRef: true, descripteur: true, zip64: true } },
      { nom: 'chemins absolus dans les liens', spec: { cheminsAbsolus: true } }
    ];
    for (const v of variantes) {
      const c = classeur();
      const ctx = chargerServeur(c, {});
      const page = await fenetre(ctx);
      const lignes = lignesSEE(40);
      if (v.spec.sansRef) lignes.splice(1, 1);   // sans références, pas de ligne vide (Excel l'omettrait)
      const r = await importer(page, 'see.xlsx', xlsx(Object.assign({ onglets: [{ nom: 'S', lignes }] }, v.spec)), { toutes: true });
      const f = c.getSheetByName('SEE HDK');
      verifier(v.nom + ' : 40 lignes, toutes les colonnes justes (une cellule vide ne décale rien)',
        /\bok\b/.test(r.etat.classe) && f && f.valeurs.length === 41 && f.valeurs[1].join('|') === 'S-0|TFE311A0600|001|A|15/03/2023||VRAI|non' &&
        f.valeurs[40].slice(1, 4).join('|') === 'TFE350A0639|001|A', r.etat.texte + ' ' + JSON.stringify(f && [f.valeurs[1], f.valeurs[40]]));
      await page.close();
    }
    // Le calendrier 1904.
    {
      const c = classeur();
      const ctx = chargerServeur(c, {});
      const page = await fenetre(ctx);
      const r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(3) }], date1904: true }), { toutes: true });
      verifier('calendrier 1904 : 45000 se lit 16/03/2027', /\bok\b/.test(r.etat.classe) && c.getSheetByName('SEE HDK').valeurs[1][4] === '16/03/2027',
        JSON.stringify(c.getSheetByName('SEE HDK') && c.getSheetByName('SEE HDK').valeurs[1]));
      await page.close();
    }
    // Chaînes riches avec lecture phonétique, caractères échappés, en-tête écrit autrement, formats de nombres.
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const lignes = [['Titre'], ['name', 'Sol.', 'CUST.V', 'Note', 'Part', 'Prix', 'Grand', 'Sci', 'Code'],
      [{ riche: ['TFE', '311A0600'], phonetique: 'ていえふ' }, { str: '002' }, 'B', 'a & b <c> "d"\r\nfin', { n: 0.25, fmt: 'pct' }, { n: 1234.5, fmt: 'euro' },
        { n: 1234567, fmt: 'mille' }, { n: 12345, fmt: 'sci' }, { n: 7.5, fmt: 'zeros3' }],
      ['HAR253A0011', 7, 'C', { n: 3.5 }, { n: 0.1234, fmt: 'pct2' }, { n: 3, fmt: '0.00' }, { n: 1e21 }, { n: 1e-7 }, { n: 42, fmt: 'zeros3' }]];
    const r = await importer(page, 'riche.xlsx', xlsx({ onglets: [{ nom: 'S', lignes }] }), { toutes: true });
    const f = c.getSheetByName('SEE HDK');
    verifier('chaîne riche sans sa lecture phonétique, résultat de formule, échappements XML et « _x000D_ » rendus, en-tête trouvé sans tenir compte de la casse',
      /\bok\b/.test(r.etat.classe) && f.valeurs[0].slice(0, 4).join('|') === 'name|Sol.|CUST.V|Note' &&
      f.valeurs[1].slice(0, 4).join('|') === 'TFE311A0600|002|B|a & b <c> "d"\r\nfin' && f.valeurs[2].slice(0, 4).join('|') === 'HAR253A0011|7|C|3,5',
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    verifier('les nombres comme Excel les affiche : 25 %, 12,34 %, 1 234,50 €, 3,00, 1 234 567, 1,23E+04, 008, 042, 1E+21, 1E-07',
      f && f.valeurs[1].slice(4).join('|') === '25 %|1 234,50 €|1 234 567|1,23E+04|008' &&
      f.valeurs[2].slice(4).join('|') === '12,34 %|3,00|1E+21|1E-07|042', JSON.stringify(f && [f.valeurs[1].slice(4), f.valeurs[2].slice(4)]));
    await page.close();
  }

  // =================================================================
  section('Toutes les colonnes, sur demande');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    let page = await fenetre(ctx);
    const r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(12) }] }), { toutes: true });
    const f = c.getSheetByName('SEE HDK');
    verifier('« Garder aussi les autres colonnes » : les huit colonnes, une date au format jour/mois/année, un booléen en VRAI/FAUX',
      /\bok\b/.test(r.etat.classe) && f.valeurs[0].length === 8 && f.valeurs[1][4] === '15/03/2023' && f.valeurs[1][6] === 'VRAI' && f.valeurs[1][5] === '',
      JSON.stringify(f && f.valeurs.slice(0, 2)));
    await page.close();
    const avant = JSON.stringify(f.valeurs);
    page = await fenetre(ctx, h => h.replace('"maxCellulesToutes":4000000', '"maxCellulesToutes":100'));
    const r2 = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(200) }] }), { toutes: true });
    verifier('au-delà du plafond de cellules, toutes les colonnes sont refusées tôt, sans rien envoyer',
      /erreur/.test(r2.etat.classe) && /trop pour le classeur/.test(r2.etat.texte) && page.__appels.length === 0 && JSON.stringify(c.getSheetByName('SEE HDK').valeurs) === avant, r2.etat.texte);
    await page.close();
    // Deux colonnes du même intitulé : la première compte, avec ou sans « toutes », et la page lit la même.
    const d = classeur();
    const ctxD = chargerServeur(d, {});
    const lignes = [['NAME', 'SOL.', 'Cust.V', 'NAME'], ['TFE311A0600', '001', 'A', 'Faisceau principal']];
    const lus = [];
    for (const toutes of [false, true]) {
      page = await fenetre(ctxD);
      await importer(page, 'dup.xlsx', xlsx({ onglets: [{ nom: 'S', lignes }] }), { toutes });
      lus.push(ctxD.lireSecondeBase(d, 'HDK').rapprochement.lignes[0].NAME);
      await page.close();
    }
    verifier('un intitulé en double (NAME deux fois) : la première colonne, avec ou sans « toutes », comme la page la lit',
      lus.join('|') === 'TFE311A0600|TFE311A0600', lus.join('|'));
  }

  // =================================================================
  section('Plusieurs onglets dans le fichier ; un seul contrat et un onglet « SEE »');
  {
    const ancien = new Feuille('SEE', [['NAME', 'SOL.', 'Cust.V'], ['OLD', '1', 'A']]);
    const c = classeur({ autres: [ancien] });
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const ui = await page.evaluate(() => ({ visible: !document.getElementById('ligne-contrat').hidden, cible: document.getElementById('cible').textContent }));
    verifier('un seul contrat : pas de choix de contrat, l’onglet « SEE » existant est la cible', !ui.visible && /Remplacera l’onglet « SEE »/.test(ui.cible), JSON.stringify(ui));
    const fichier = xlsx({ onglets: [{ nom: 'Lisez-moi', lignes: [['Export du 01/10'], ['Rien ici']] }, { nom: 'Masqué', cache: true, lignes: [['NAME', 'SOL.', 'Cust.V'], ['MASQUE', '9', 'Z']] },
      { nom: 'Données', lignes: lignesSEE(25) }] });
    const r = await importer(page, 'multi.xlsx', fichier);
    const f = c.getSheetByName('SEE');
    verifier('l’en-tête est cherché onglet par onglet, les visibles d’abord : « Données »',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 26 && f.valeurs[1][0] === 'TFE311A0600', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs[1]));
    const bord = [['NAME', 'SOL.', 'Cust.V']];
    const enLigne8 = xlsx({ onglets: [{ nom: 'S', lignes: [['t'], [], [], [], [], [], [], bord[0], ['TFE1', '1', 'A']] }] });
    const enLigne9 = xlsx({ onglets: [{ nom: 'S', lignes: [['t'], [], [], [], [], [], [], [], bord[0], ['TFE1', '1', 'A']] }] });
    const r8 = await importer(page, 'l8.xlsx', enLigne8), r9 = await importer(page, 'l9.xlsx', enLigne9);
    verifier('l’en-tête en ligne 8 est pris, en ligne 9 refusé — comme le Diagnostic et la page le cherchent',
      /\bok\b/.test(r8.etat.classe) && /erreur/.test(r9.etat.classe) && /8 premières lignes/.test(r9.etat.texte), r8.etat.texte + ' / ' + r9.etat.texte);
    await page.close();
  }

  // =================================================================
  section('Les fichiers texte : CSV, page web et XML 2003 nommés .xls, UTF-16');
  {
    const c = classeur({ ths: true });
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const texte = 'Nommage WD BFLOW;;;\r\n;;;\r\nNAME;SOL.;Cust.V;Libellé\r\nTFE311A0600;001;A;"Faisceau ; « été »"\r\n"HAR253A0011";="002";="B";"ligne\r\ncoupée ""citée"""\r\n';
    let r = await importer(page, 'see.csv', Buffer.from(texte, 'latin1'), { contrat: 'THS', toutes: true });
    let f = c.getSheetByName('SEE THS');
    verifier('un CSV en Windows-1252 : « ; », guillemets doublés, retour à la ligne dans un champ, ="002" lu 002 — dans « SEE THS » (créé, au bout)',
      /\bok\b/.test(r.etat.classe) && f && f.valeurs.length === 3 && f.valeurs[1].join('|') === 'TFE311A0600|001|A|Faisceau ; « été »' &&
      f.valeurs[2].join('|') === 'HAR253A0011|002|B|ligne\r\ncoupée "citée"' && nomsOnglets(c)[nomsOnglets(c).length - 1] === 'SEE THS',
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    const virgules = 'NAME,SOL.,Cust.V,Poids\nTFE311A0600,001,A,"3,5"\nHAR253A0011,002,B,4\n';
    r = await importer(page, 'see.csv', Buffer.from(virgules, 'utf8'), { contrat: 'THS', toutes: true });
    f = c.getSheetByName('SEE THS');
    verifier('un CSV à virgules, la virgule décimale entre guillemets', /\bok\b/.test(r.etat.classe) && f.valeurs[1].join('|') === 'TFE311A0600|001|A|3,5', JSON.stringify(f.valeurs));
    const tabs = '﻿NAME\tSOL.\tCust.V\nTFE311A0600\t001\tA\n';
    r = await importer(page, 'see.txt', Buffer.concat([Buffer.from([0xFF, 0xFE]), Buffer.from(tabs.slice(1), 'utf16le')]), { contrat: 'THS' });
    f = c.getSheetByName('SEE THS');
    verifier('un « Texte Unicode » (UTF-16, tabulations)', /\bok\b/.test(r.etat.classe) && f.valeurs[1].join('|') === 'TFE311A0600|001|A', r.etat.texte);
    const tard = 'NAME;SOL.;Cust.V;Libelle\n' + Array.from({ length: 40000 }, (_, i) => nomDe(i) + ';001;A;texte').join('\n') + '\nHAR253A0011;002;B;Câble été\n';
    r = await importer(page, 'tard.csv', Buffer.from(tard, 'latin1'), { contrat: 'THS', toutes: true });
    f = c.getSheetByName('SEE THS');
    verifier('des accents Windows loin dans le fichier (après 1 Mo d’ASCII) : relu en Windows-1252, pas de « � »',
      /\bok\b/.test(r.etat.classe) && f.valeurs[f.valeurs.length - 1].join('|') === 'HAR253A0011|002|B|Câble été', r.etat.texte + ' ' + JSON.stringify(f.valeurs[f.valeurs.length - 1]));
    const html = '<html><head><meta charset="utf-8"></head><body><table><tr><td colspan="3"><b>Nommage WD BFLOW</b></td></tr><tr><td></td></tr>' +
      '<tr><th>NAME</th><th>SOL.</th><th>Cust.V</th><th>Libellé</th></tr><tr><td>TFE311A0600</td><td>001</td><td>A</td><td>Faisceau &amp; c&eacute;ble<br>bis</td></tr>' +
      '<TR><TD>HAR253A0011</TD><TD>002</TD><TD>B</TD><TD>&nbsp;</TD></TR></table></body></html>';
    r = await importer(page, 'Nommage WD BFLOW.xls', Buffer.from(html, 'utf8'), { contrat: 'THS', toutes: true });
    f = c.getSheetByName('SEE THS');
    verifier('un « Excel » qui est une page web (tableau HTML nommé .xls) : lu comme tel',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 3 && f.valeurs[1].join('|') === 'TFE311A0600|001|A|Faisceau & céble bis' && f.valeurs[2][0] === 'HAR253A0011',
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    const xml = '<?xml version="1.0"?><?mso-application progid="Excel.Sheet"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">' +
      '<Worksheet ss:Name="Infos"><Table><Row><Cell><Data ss:Type="String">Export</Data></Cell></Row></Table></Worksheet>' +
      '<Worksheet ss:Name="Nommage"><Table><Row><Cell ss:MergeAcross="2"><Data ss:Type="String">Nommage WD BFLOW</Data></Cell></Row><Row ss:Index="3"><Cell><Data ss:Type="String">NAME</Data></Cell>' +
      '<Cell><Data ss:Type="String">SOL.</Data></Cell><Cell><Data ss:Type="String">Cust.V</Data></Cell><Cell><Data ss:Type="String">Date</Data></Cell></Row>' +
      '<Row><Cell><Data ss:Type="String">TFE311A0600</Data></Cell><Cell><Data ss:Type="String">001</Data></Cell><Cell><Data ss:Type="String">A</Data></Cell><Cell><Data ss:Type="DateTime">2026-03-15T00:00:00.000</Data></Cell></Row>' +
      '<Row><Cell><Data ss:Type="String">HAR253A0011</Data></Cell><Cell ss:Index="3"><Data ss:Type="String">B</Data></Cell><Cell><Data ss:Type="Number">3.5</Data></Cell></Row></Table></Worksheet></Workbook>';
    r = await importer(page, 'see.xls', Buffer.from(xml, 'utf8'), { contrat: 'THS', toutes: true });
    f = c.getSheetByName('SEE THS');
    verifier('un « Excel » XML 2003 (deux onglets, l’en-tête dans le second, cellules indexées) : lu comme tel',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 3 && f.valeurs[1].join('|') === 'TFE311A0600|001|A|15/03/2026' && f.valeurs[2].join('|') === 'HAR253A0011||B|3,5',
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    /* Cent cinquante styles avant la première feuille (80 Ko), et un texte en CDATA. */
    const styles = '<Styles>' + Array.from({ length: 150 }, (_, i) => '<Style ss:ID="s' + i + '"><Alignment ss:Vertical="Bottom"/><Borders/><Font ss:FontName="Calibri" x:Family="Swiss" ss:Size="11" ss:Color="#000000"/>' +
      '<Interior/><NumberFormat/><Protection/>' + ' '.repeat(300) + '</Style>').join('') + '</Styles>';
    const xmlLourd = xml.replace('<Worksheet ss:Name="Infos">', styles + '<Worksheet ss:Name="Infos">')
      .replace('<Data ss:Type="String">HAR253A0011</Data>', '<Data ss:Type="String"><![CDATA[HAR253A0011 & <bis>]]></Data>');
    r = await importer(page, 'lourd.xls', Buffer.from(xmlLourd, 'utf8'), { contrat: 'THS', toutes: true });
    f = c.getSheetByName('SEE THS');
    verifier('un XML 2003 dont la première feuille arrive après 64 Ko de styles, un texte en CDATA : lus',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 3 && f.valeurs[2][0] === 'HAR253A0011 & <bis>', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    /* Tout entre guillemets, et une description pleine de « ; » dans un CSV à virgules. */
    const guillemets = '"SCHEMA NUMBER","NAME","SOL.","Cust.V","Description"\r\n"S1","TFE311A0600","001","A","P1; P2; P3; P4; P5; P6; P7"\r\n"S2","HAR253A0011","002","B","x"\r\n';
    r = await importer(page, 'see.csv', Buffer.from(guillemets, 'utf8'), { contrat: 'THS' });
    f = c.getSheetByName('SEE THS');
    verifier('un CSV tout entre guillemets, avec des « ; » dans une description : le bon séparateur',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 3 && f.valeurs[1].join('|') === 'TFE311A0600|001|A', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    await page.close();
  }

  // =================================================================
  section('Ce qui ne marche pas le dit, juste, et ne touche à rien');
  {
    const ancien = new Feuille('SEE HDK', [['NAME', 'SOL.', 'Cust.V'], ['OLD', '1', 'A']]);
    const c = classeur({ ths: true, autres: [ancien] });
    const ctx = chargerServeur(c, {});
    const avant = JSON.stringify(ancien.valeurs);
    let page = await fenetre(ctx);
    let r = await importer(page, 'autre.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: [['Titre'], ['REF', 'SOL.', 'Cust V'], ['X', '1', 'A']] }] }));
    verifier('pas d’en-tête NAME / SOL. / Cust.V : le message nomme ce qui manque et la ligne la plus proche',
      /erreur/.test(r.etat.classe) && /Aucune ligne d’en-tête avec NAME, SOL\., Cust\.V/.test(r.etat.texte) && /La ligne 2 de « S » en porte 1 sur 3 — il manque : NAME, Cust\.V/.test(r.etat.texte) &&
      /Rien n’a été remplacé/.test(r.etat.texte), r.etat.texte);
    verifier('et le classeur n’a pas bougé (aucun appel au serveur)', page.__appels.length === 0 && JSON.stringify(ancien.valeurs) === avant);
    r = await importer(page, 'entete.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V']] }] }));
    verifier('l’en-tête sans aucune ligne dessous : refusé, la base n’est pas vidée', /erreur/.test(r.etat.classe) && /aucune ligne dessous/.test(r.etat.texte) && page.__appels.length === 0, r.etat.texte);
    const ole = Buffer.concat([Buffer.from([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]), Buffer.alloc(600)]);
    r = await importer(page, 'vieux.xls', ole);
    verifier('un ancien .xls : la fenêtre dit qu’elle ne le lit pas, et l’autre chemin — « Insérer de nouvelles feuilles », surtout pas « Remplacer la feuille de calcul », le nom à donner',
      /erreur/.test(r.etat.classe) && /ancien fichier Excel \(\.xls\)/.test(r.etat.texte) && /« Insérer de nouvelles feuilles »/.test(r.etat.texte) &&
      /surtout pas « Remplacer la feuille de calcul »/.test(r.etat.texte) && /« SEE HDK »/.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'Nommage WD BFLOW.xlsx', ole);
    verifier('un .xlsx protégé (mot de passe, étiquette) : dit protégé, pas « ancien .xls »', /erreur/.test(r.etat.classe) && /protégé/.test(r.etat.texte) && !/ancien fichier/.test(r.etat.texte), r.etat.texte);
    /* Un vrai conteneur OLE : en-tête (secteurs de 512, répertoire au secteur 0), puis le répertoire. */
    const conteneur = (noms) => {
      const b = Buffer.alloc(512 * 3);
      Buffer.from([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]).copy(b, 0);
      b.writeUInt16LE(9, 0x1E); b.writeUInt32LE(0, 0x30);
      ['Root Entry'].concat(noms).forEach((n, k) => { const o = 512 + 128 * k; Buffer.from(n + '\0', 'utf16le').copy(b, o); b.writeUInt16LE((n.length + 1) * 2, o + 64); });
      return b;
    };
    r = await importer(page, 'export.xlsx', conteneur(['Workbook', '\u0005SummaryInformation']));
    verifier('un vieux classeur (.xls) nommé .xlsx : dit « format .xls, malgré son nom » et l’autre chemin, pas « protégé »',
      /erreur/.test(r.etat.classe) && /format \.xls, malgré son nom/.test(r.etat.texte) && /« Insérer de nouvelles feuilles »/.test(r.etat.texte) && !/protégé/.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'chiffre.xls', conteneur(['\u0006DataSpaces', 'EncryptionInfo', 'EncryptedPackage']));
    verifier('un .xlsx chiffré, même nommé .xls : dit protégé', /erreur/.test(r.etat.classe) && /protégé/.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'tronque.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(20) }] }).subarray(0, 900));
    verifier('un .xlsx tronqué (téléchargement pas fini) : le retélécharger', /erreur/.test(r.etat.classe) && /retélécharger/.test(r.etat.texte), r.etat.texte);
    /* Un zip abîmé au milieu : des octets de la feuille brouillés. */
    const sain = xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(3000) }] });
    const abime = Buffer.from(sain);
    const at = sain.indexOf(Buffer.from('xl/worksheets/sheet1.xml')) + 200;
    for (let k = 0; k < 64; k++) abime[at + k] ^= 0x5A;
    r = await importer(page, 'abime.xlsx', abime);
    verifier('un .xlsx abîmé au milieu : « abîmé, le retélécharger », jamais une base à moitié lue', /erreur/.test(r.etat.classe) && /abîmé/.test(r.etat.texte) && !/Erreur inattendue/.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'formules.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], [{ f: 'D2&"x"' }, '001', 'A'], ['TFE2', '002', 'B']] }] }));
    verifier('NAME en formule sans valeur calculée : refusé, avec ce qu’il faut demander', /erreur/.test(r.etat.classe) && /formule sans valeur calculée/.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'vide.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE1', '001', { str: '' }], ['TFE2', '002', 'B']] }] }), { contrat: 'THS' });
    verifier('une formule qui rend une chaîne vide (enregistrée par Excel) : une valeur vide, pas un refus',
      /\bok\b/.test(r.etat.classe) && c.getSheetByName('SEE THS').valeurs.map(l => l.join('|')).join(' / ') === 'NAME|SOL.|Cust.V / TFE1|001| / TFE2|002|B', r.etat.texte);
    await page.close();

    /* Le serveur lâche une fois, au deuxième lot : le lot est renvoyé, l'import va au bout. */
    const rapide = html => html.replace('"maxLignesLot":20000', '"maxLignesLot":50').replace('"pausesReprise":[2000,6000]', '"pausesReprise":[30,60]');
    page = await fenetre(ctx, rapide);
    const vrai = ctx.importSecondeBaseLot;
    let lots = 0;
    ctx.importSecondeBaseLot = function () { lots++; if (lots === 2) throw new Error('Service Spreadsheets timed out while accessing document'); return vrai.apply(null, arguments); };
    r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(200) }] }), { contrat: 'HDK' });
    ctx.importSecondeBaseLot = vrai;
    verifier('un lot qui échoue une fois en route : renvoyé, l’import va au bout, sans ligne en double',
      /\bok\b/.test(r.etat.classe) && lots === 6 && c.getSheetByName('SEE HDK').valeurs.length === 201 &&
      new Set(c.getSheetByName('SEE HDK').valeurs.map(l => l[0])).size === 201 && sansImport(c), r.etat.texte + ' / ' + lots);
    await page.close();
    c.getSheetByName('SEE HDK').valeurs = JSON.parse(avant);
    /* Le serveur lâche pour de bon au deuxième lot : trois essais, puis l'ancien onglet reste, le temporaire part. */
    page = await fenetre(ctx, rapide);
    lots = 0;
    ctx.importSecondeBaseLot = function () { lots++; if (lots >= 2) throw new Error('Service Spreadsheets indisponible'); return vrai.apply(null, arguments); };
    r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(200) }] }), { contrat: 'HDK' });
    ctx.importSecondeBaseLot = vrai;
    await page.waitForTimeout(300);
    verifier('une panne qui dure : trois essais, puis le message la dit et dit quoi faire, « SEE HDK » est intact, l’onglet temporaire est retiré',
      /erreur/.test(r.etat.classe) && lots === 4 && /Service Spreadsheets indisponible/.test(r.etat.texte) && /Relancer l’import/.test(r.etat.texte) &&
      JSON.stringify(c.getSheetByName('SEE HDK').valeurs) === avant && sansImport(c), r.etat.texte + ' / ' + lots + ' / ' + nomsOnglets(c).join(', '));
    /* Un refus du serveur n'est pas renvoyé. */
    page.__appels = [];
    ctx.importSecondeBaseLot = function () { throw new Error('L’onglet d’import « x » a disparu (un autre import de ce contrat a-t-il été lancé ?) : relancer l’import.'); };
    r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(20) }] }), { contrat: 'HDK' });
    ctx.importSecondeBaseLot = vrai;
    verifier('un refus du serveur (« a disparu ») : pas renvoyé', /erreur/.test(r.etat.classe) && page.__appels.filter(n => n === 'importSecondeBaseLot').length === 1, page.__appels.join());
    /* Relancé : il passe, en lots de 50 lignes exactement. */
    page.__appels = [];
    const tailles = [];
    ctx.importSecondeBaseLot = function (j, f, p, l) { tailles.push(l.length); return vrai.apply(null, arguments); };
    r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(200) }] }), { contrat: 'HDK' });
    ctx.importSecondeBaseLot = vrai;
    verifier('relancé : il passe, en lots de 50 lignes', /\bok\b/.test(r.etat.classe) && c.getSheetByName('SEE HDK').valeurs.length === 201 && tailles.join() === '50,50,50,50,1',
      r.etat.texte + ' / ' + tailles.join());
    await page.close();

    /* La fin a tout fait, puis la réponse se perd : la fenêtre ne dit pas « rien n'a été remplacé ». */
    page = await fenetre(ctx);
    const vraiFin = ctx.importSecondeBaseFin;
    ctx.importSecondeBaseFin = function () { vraiFin.apply(null, arguments); throw new Error('NetworkError: Connection failure due to HTTP 0'); };
    r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(120) }] }), { contrat: 'HDK' });
    ctx.importSecondeBaseFin = vraiFin;
    verifier('la fin a eu lieu mais sa réponse s’est perdue : « peut-être allé au bout : regarder l’onglet », jamais « rien n’a été remplacé »',
      /erreur/.test(r.etat.classe) && /peut-être allé au bout : regarder l’onglet « SEE HDK »/.test(r.etat.texte) && !/Rien n’a été remplacé/.test(r.etat.texte) &&
      c.getSheetByName('SEE HDK').valeurs.length === 121, r.etat.texte);
    await page.close();

    /* Un import incomplet (des lignes perdues en route) n'est pas posé. */
    let fin = '';
    const jeton = jetonDe(ctx);
    const d = ctx.importSecondeBaseDebut(jeton, 'HDK', 3, 5);
    ctx.importSecondeBaseLot(jeton, d.feuille, 1, [['NAME', 'SOL.', 'Cust.V'], ['A', '1', 'B']]);
    try { ctx.importSecondeBaseFin(jeton, d.feuille, 'HDK', 5); } catch (e) { fin = e.message; }
    verifier('des lignes manquantes à la fin : rien n’est remplacé, et l’onglet temporaire part',
      /Import incomplet : 2 lignes reçues sur 5/.test(fin) && c.getSheetByName('SEE HDK').valeurs.length === 121 && sansImport(c), fin);
    /* Deux imports du même contrat en même temps : le premier s'arrête net, jamais un mélange. */
    const a = ctx.importSecondeBaseDebut(jeton, 'HDK', 3, 4);
    ctx.importSecondeBaseLot(jeton, a.feuille, 1, [['NAME', 'SOL.', 'Cust.V'], ['A1', '1', 'A']]);
    const b = ctx.importSecondeBaseDebut(jeton, 'HDK', 3, 3);
    let arret = '';
    try { ctx.importSecondeBaseLot(jeton, a.feuille, 3, [['A2', '1', 'A'], ['A3', '1', 'A']]); } catch (e) { arret = e.message; }
    ctx.importSecondeBaseLot(jeton, b.feuille, 1, [['NAME', 'SOL.', 'Cust.V'], ['B1', '2', 'B'], ['B2', '2', 'B']]);
    const rb = ctx.importSecondeBaseFin(jeton, b.feuille, 'HDK', 3);
    verifier('deux imports du même contrat en même temps : le premier s’arrête (« a disparu »), le second pose sa base, sans mélange',
      a.feuille !== b.feuille && /a disparu/.test(arret) && rb.lignes === 2 && c.getSheetByName('SEE HDK').valeurs.map(l => l[0]).join() === 'NAME,B1,B2' && sansImport(c), arret);
    /* Un reste d'import (fenêtre fermée en cours d'envoi) : le Diagnostic le signale, le prochain import le retire. */
    const reste = ctx.importSecondeBaseDebut(jeton, 'THS', 3, 10);
    ctx.importSecondeBaseLot(jeton, reste.feuille, 1, [['NAME', 'SOL.', 'Cust.V'], ['R', '1', 'A']]);
    const diag = ctx.diagnostic();
    const texteDiag = typeof diag === 'string' ? diag : (ctx.__alertes || []).join('\n');
    verifier('un import interrompu : le Diagnostic nomme son onglet temporaire', /reste d’un import interrompu|reste d'un import interrompu/.test(texteDiag) && texteDiag.indexOf(reste.feuille) !== -1, texteDiag.split('\n').filter(l => /import/.test(l)).join(' / '));
    page = await fenetre(ctx);
    r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(5) }] }), { contrat: 'THS' });
    verifier('et le prochain import de ce contrat le retire', /\bok\b/.test(r.etat.classe) && sansImport(c) && !!c.getSheetByName('SEE THS'), nomsOnglets(c).join(', '));
    await page.close();
  }

  // =================================================================
  section('La limite de Google Sheets : dix millions de cellules, vides comprises');
  {
    const gros = new Feuille('Archives', [['x']]);
    const c = classeur({ autres: [gros] });
    const autres = c.cellulesGrille() - gros.getMaxRows() * gros.getMaxColumns();
    gros.lignesGrille = Math.floor((10000000 - autres - 10000) / 26);
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(9000) }] }));
    verifier('un classeur presque plein : refusé avant tout envoi, avec les nombres et quoi faire, rien de créé',
      /erreur/.test(r.etat.classe) && /limite de Google Sheets : 10 millions de cellules/.test(r.etat.texte) && /supprimer les onglets/.test(r.etat.texte) &&
      page.__appels.join() === 'importSecondeBaseDebut' && sansImport(c) && !c.getSheetByName('SEE HDK'), r.etat.texte);
    await page.close();
  }

  // =================================================================
  section('Un gros export : 120 000 lignes × 24 colonnes, et des liens après les lignes');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const entete = ['SCHEMA NUMBER', 'NAME', 'SOL.', 'Cust.V'].concat(Array.from({ length: 20 }, (_, k) => 'Colonne ' + (k + 1)));
    const n = 120000;
    const lignes = [['Nommage WD BFLOW'], [], entete];
    const attendu = i => 'TFE' + (311 + i % 90) + 'A' + String(i).padStart(6, '0') + '|' + String(1 + i % 4).padStart(3, '0') + '|' + ['A', 'B', 'C', 'D'][i % 4];
    for (let i = 0; i < n; i++) {
      const l = ['S-' + i].concat(attendu(i).split('|'));
      for (let k = 0; k < 20; k++) l.push(k % 3 ? 'valeur ' + ((i * 7 + k) % 5000) : { n: 45000 + (i % 900), fmt: 'date' });
      lignes.push(l);
    }
    /* Ce que certains exports écrivent après les lignes : un lien par ligne. */
    const queue = '<hyperlinks>' + Array.from({ length: n }, (_, i) => '<hyperlink ref="B' + (i + 4) + '" r:id="rId' + (i + 10) + '"/>').join('') + '</hyperlinks>';
    const fichier = xlsx({ onglets: [{ nom: 'Export', lignes, queue }] });
    const r = await importer(page, 'gros.xlsx', fichier, { delai: 300000 });
    const f = c.getSheetByName('SEE HDK');
    const echantillon = Array.from({ length: 12 }, (_, k) => k * 10000).concat([n - 1]).filter(i => f && f.valeurs[i + 1] && f.valeurs[i + 1].join('|') !== attendu(i));
    verifier('importé (' + (fichier.length / 1048576).toFixed(1) + ' Mo, ' + (r.duree / 1000).toFixed(1) + ' s) : ' + n + ' lignes, NAME / SOL. / Cust.V alignés (une ligne sur 10 000 vérifiée)',
      /\bok\b/.test(r.etat.classe) && f && f.valeurs.length === n + 1 && !echantillon.length, r.etat.texte + ' ' + echantillon.join(','));
    verifier('en moins de deux minutes, malgré les liens après les lignes', r.duree < 120000, (r.duree / 1000).toFixed(1) + ' s');
    await page.close();
  }

  // =================================================================
  section('Glisser le fichier dans la fenêtre');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const b64 = xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(7) }] }).toString('base64');
    await page.evaluate(b => {
      const bin = atob(b), u = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
      const dt = new DataTransfer();
      dt.items.add(new File([u], 'glisse.xlsx'));
      document.getElementById('depot').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    }, b64);
    const nom = await page.$eval('#nom-fichier', e => e.textContent);
    await page.click('#importer');
    const etat = await attendreFin(page);
    verifier('un fichier glissé est pris comme un fichier choisi', /glisse\.xlsx/.test(nom) && /\bok\b/.test(etat.classe) && c.getSheetByName('SEE HDK').valeurs.length === 8, nom + ' / ' + etat.texte);
    await page.close();
  }

  await nav.close();
  try { fs.rmSync(dossier, { recursive: true, force: true }); } catch (e) { /* rien */ }
  console.log('\n═══════════════════════════════════════');
  console.log(reussis + ' test(s) réussi(s), ' + echecs.length + ' échec(s)');
  if (echecs.length) { console.log('\nÉchecs :'); echecs.forEach(e => console.log('  · ' + e)); }
  console.log('\nErreurs JavaScript : ' + (erreursJS.length ? erreursJS.join(' | ') : 'aucune'));
  process.exit(echecs.length || erreursJS.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });

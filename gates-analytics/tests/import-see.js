/* L'import de la base SEE sans Excel (menu Suivi FWD → Importer la base) :
   la vraie fenêtre, rendue par le vrai Code.gs, ouverte dans un vrai
   navigateur ; google.script.run y répond par les vraies fonctions du
   serveur, sur un classeur en mémoire. Les fichiers sont fabriqués pour
   l'occasion (tests/fabriquer-xlsx.js) : chaînes partagées ou en ligne,
   chaînes riches, styles, préfixes, Zip64, CSV. */
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
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
function references(c) {
  const f = c.getSheetByName('HDK'), v = f.valeurs;
  const i = v.findIndex(l => l.indexOf('Référence UD') !== -1);
  const j = v[i].indexOf('Référence UD');
  return v.slice(i + 1).map(l => l[j]).filter(Boolean);
}
/* Les lignes d'un export SEE : titre, ligne vide, en-tête en ligne 3. */
function lignesSEE(n, options) {
  const opt = options || {};
  const entete = opt.entete || ['SCHEMA NUMBER', 'NAME', 'SOL.', 'Cust.V', 'Released Date', 'Validated Date', 'REDRAW', 'ARCHIVED'];
  const lignes = [['Nommage WD BFLOW'], [], entete];
  for (let i = 0; i < n; i++) {
    const nom = 'TFE' + String(311 + (i % 50)) + 'A' + String(600 + i).padStart(4, '0');
    const ligne = { 'SCHEMA NUMBER': 'S-' + i, NAME: nom, 'SOL.': opt.solNombre ? { n: (i % 3) + 1, fmt: 'zeros5' } : String((i % 3) + 1).padStart(3, '0'),
      'Cust.V': ['A', 'B', 'C'][i % 3], 'Released Date': { n: 45000 + i, fmt: 'date' }, 'Validated Date': i % 4 ? { n: 45100 + i, fmt: 'date' } : null,
      REDRAW: { b: i % 2 === 0 }, ARCHIVED: 'non' };
    lignes.push(entete.map(k => ligne[k] === undefined ? (ligne[Object.keys(ligne).find(x => x.toLowerCase() === k.toLowerCase())] || null) : ligne[k]));
  }
  return lignes;
}

(async () => {
  const nav = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const dossier = fs.mkdtempSync(path.join(os.tmpdir(), 'import-see-'));

  /* La fenêtre d'import pour un classeur : rendue par importerSecondeBase,
     ouverte dans le navigateur, google.script.run branché sur le serveur. */
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
    await page.exposeFunction('__appelServeur', (nom, args) => {
      page.__appels.push(nom);
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
  async function importer(page, nom, contenu, options) {
    const opt = options || {};
    if (opt.contrat) await page.selectOption('#contrat', opt.contrat);
    if (opt.toutes) await page.check('#toutes');
    await page.setInputFiles('#fichier', { name: nom, mimeType: 'application/octet-stream', buffer: contenu });
    const t0 = Date.now();
    await page.click('#importer');
    await page.waitForFunction(() => /\bok\b|erreur/.test(document.getElementById('etat').className), null, { timeout: opt.delai || 120000 });
    return { etat: await page.evaluate(() => ({ classe: document.getElementById('etat').className, texte: document.getElementById('etat').textContent })),
             duree: Date.now() - t0 };
  }
  const nomsOnglets = c => c.getSheets().map(f => f.getName());

  // =================================================================
  section('Le menu et la garde');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    ctx.onOpen();
    verifier('le menu Suivi FWD propose « Importer la base SEE »', ctx.__menu.indexOf('importerSecondeBase') !== -1, JSON.stringify(ctx.__menu));
    ctx.__sansInterface = true;
    const refus = ['importerSecondeBase', 'importSecondeBaseDebut', 'importSecondeBaseLot', 'importSecondeBaseFin', 'importSecondeBaseAbandon'].map(n => {
      try { ctx[n]('HDK', 1, [['x']]); return n + ':passe'; } catch (e) { return /Geste refusé/.test(e.message) ? '' : n + ':' + e.message; }
    }).filter(Boolean);
    verifier('hors du classeur (la page du tableau de bord), chaque fonction de l’import est refusée', !refus.length, refus.join(' | '));
    ctx.__sansInterface = false;
    let arbitraire = '';
    try { ctx.importSecondeBaseLot('HDK', 1, [['écrasé']]); } catch (e) { arbitraire = e.message; }
    verifier('un lot ne s’écrit que dans l’onglet temporaire d’un import, jamais dans un autre (« HDK »)',
      /non reconnu/.test(arbitraire) && c.getSheetByName('HDK').valeurs[0][0] !== 'écrasé', arbitraire);
  }

  // =================================================================
  section('Un export SEE en .xlsx : seules l’en-tête et NAME, SOL., Cust.V vont au classeur');
  {
    const ancien = new Feuille('SEE HDK', [['vieux'], ['NAME', 'SOL.', 'Cust.V'], ['OLD1', '1', 'A']]);
    const c = classeur({ ths: true, autres: [ancien, new Feuille('Notes', [['x']])] });
    const ctx = chargerServeur(c, {});
    const place = nomsOnglets(c).indexOf('SEE HDK');
    const page = await fenetre(ctx);
    const ui = await page.evaluate(() => ({ contrat: document.getElementById('contrat').value, visible: !document.getElementById('ligne-contrat').hidden,
      cible: document.getElementById('cible').textContent, desactive: document.getElementById('importer').disabled }));
    verifier('la fenêtre propose le contrat et dit l’onglet remplacé ; « Importer » attend un fichier',
      ui.visible && /« SEE HDK »/.test(ui.cible) && /remplacé/.test(ui.cible) && ui.desactive, JSON.stringify(ui));
    const n = 1500;
    const fichier = xlsx({ onglets: [{ nom: 'Export', lignes: lignesSEE(n, { solNombre: true }) }] });
    const r = await importer(page, 'Nommage WD BFLOW.xlsx', fichier, { contrat: 'HDK' });
    const f = c.getSheetByName('SEE HDK');
    verifier('l’import réussit et le dit', /\bok\b/.test(r.etat.classe) && /1 500 lignes/.test(r.etat.texte) && /comparaison est prête/.test(r.etat.texte), r.etat.texte);
    verifier('l’onglet « SEE HDK » : la ligne d’en-tête puis les ' + n + ' lignes, trois colonnes seulement',
      !!f && f.valeurs.length === n + 1 && f.valeurs[0].join('|') === 'NAME|SOL.|Cust.V' && f.valeurs.every(l => l.length === 3),
      f && JSON.stringify([f.valeurs.length, f.valeurs[0], f.valeurs[1]]));
    verifier('un nombre au format « 00000 » garde ses zéros (SOL. 1 → 00001), en texte',
      f.valeurs[1][1] === '00001' && f.formats[0] === '@', JSON.stringify(f.valeurs[1]));
    verifier('l’ancien onglet est remplacé, à sa place ; pas d’onglet temporaire qui traîne',
      nomsOnglets(c).indexOf('SEE HDK') === place && !nomsOnglets(c).some(x => /\(import\)/.test(x)) && f.valeurs[1][0] !== 'OLD1', nomsOnglets(c).join(', '));
    verifier('la grille est resserrée sur les données (le classeur reste léger)',
      f.getMaxRows() === n + 1 && f.getMaxColumns() === 3, f.getMaxRows() + ' × ' + f.getMaxColumns());
    const lu = ctx.lireSecondeBase(c, 'HDK');
    verifier('la page relit la base : référence trouvée, ' + n + ' lignes', lu.etat === 'ok' && lu.rapprochement.lignes.length === n, lu.etat);
    const paquet = ctx.getDonneesPourClient('HDK');
    verifier('et le paquet du tableau de bord porte la comparaison', !!paquet.rapprochement && paquet.rapprochement.lignes.length === n);
    verifier('THS reste sans base, intact', !c.getSheetByName('SEE THS') && !!c.getSheetByName('THS'));
    verifier('la fenêtre n’a appelé que les quatre gestes prévus, en ordre',
      page.__appels[0] === 'importSecondeBaseDebut' && page.__appels[page.__appels.length - 1] === 'importSecondeBaseFin' &&
      page.__appels.slice(1, -1).every(x => x === 'importSecondeBaseLot'), page.__appels.join(','));
    await page.close();
  }

  // =================================================================
  section('Les façons d’écrire un .xlsx');
  {
    const variantes = [
      { nom: 'chaînes en ligne, préfixe « x: », sans références, descripteurs de données, Zip64',
        spec: { chaines: 'inline', prefixe: 'x', sansRef: true, descripteur: true, zip64: true } },
      { nom: 'chemins absolus dans les liens, calendrier 1904', spec: { cheminsAbsolus: true, date1904: true } }
    ];
    for (const v of variantes) {
      const c = classeur();
      const ctx = chargerServeur(c, {});
      const page = await fenetre(ctx);
      const lignes = lignesSEE(40);
      /* sans références, une ligne vide décalerait tout : Excel l'omet, et
         les numéros de ligne font foi. Ici, pas de ligne vide. */
      if (v.spec.sansRef) lignes.splice(1, 1);
      const r = await importer(page, 'see.xlsx', xlsx(Object.assign({ onglets: [{ nom: 'S', lignes }] }, v.spec)));
      const f = c.getSheetByName('SEE');
      verifier(v.nom + ' : 40 lignes, NAME / SOL. / Cust.V justes',
        /\bok\b/.test(r.etat.classe) && f && f.valeurs.length === 41 && f.valeurs[1].join('|') === 'TFE311A0600|001|A' && f.valeurs[40].join('|') === 'TFE350A0639|001|A',
        r.etat.texte + ' ' + JSON.stringify(f && [f.valeurs[1], f.valeurs[40]]));
      await page.close();
    }
    // Chaînes riches avec lecture phonétique, caractères échappés, en-tête écrit autrement.
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const lignes = [['Titre'], ['name', 'Sol.', 'CUST.V', 'Note'],
      [{ riche: ['TFE', '311A0600'], phonetique: 'ていえふ' }, { str: '002' }, 'B', 'a & b <c> "d"\r\nfin'],
      ['HAR253A0011', 7, 'C', { n: 3.5 }]];
    const r = await importer(page, 'riche.xlsx', xlsx({ onglets: [{ nom: 'S', lignes }] }), { toutes: true });
    const f = c.getSheetByName('SEE');
    verifier('chaîne riche sans sa lecture phonétique, résultat de formule, échappements XML et « _x000D_ » rendus, en-tête trouvé sans tenir compte de la casse',
      /\bok\b/.test(r.etat.classe) && f.valeurs[0].join('|') === 'name|Sol.|CUST.V|Note' && f.valeurs[1].join('|') === 'TFE311A0600|002|B|a & b <c> "d"\r\nfin' &&
      f.valeurs[2].join('|') === 'HAR253A0011|7|C|3,5', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    await page.close();
  }

  // =================================================================
  section('Toutes les colonnes, sur demande : les dates se lisent en dates');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(12) }] }), { toutes: true });
    const f = c.getSheetByName('SEE');
    verifier('« Garder aussi les autres colonnes » : les huit colonnes, une date au format jour/mois/année, un booléen en VRAI/FAUX',
      /\bok\b/.test(r.etat.classe) && f.valeurs[0].length === 8 && f.valeurs[1][4] === '15/03/2023' && f.valeurs[1][6] === 'VRAI' && f.valeurs[1][5] === '',
      JSON.stringify(f && f.valeurs.slice(0, 2)));
    await page.close();
  }

  // =================================================================
  section('Plusieurs onglets dans le fichier ; un seul contrat et un onglet « SEE »');
  {
    const ancien = new Feuille('SEE', [['NAME', 'SOL.', 'Cust.V'], ['OLD', '1', 'A']]);
    const c = classeur({ autres: [ancien] });
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const ui = await page.evaluate(() => ({ visible: !document.getElementById('ligne-contrat').hidden, cible: document.getElementById('cible').textContent }));
    verifier('un seul contrat : pas de choix de contrat, l’onglet « SEE » existant est la cible', !ui.visible && /« SEE »/.test(ui.cible) && /remplacé/.test(ui.cible), JSON.stringify(ui));
    const fichier = xlsx({ onglets: [{ nom: 'Lisez-moi', lignes: [['Export du 01/10'], ['Rien ici']] }, { nom: 'Masqué', cache: true, lignes: [['NAME', 'SOL.', 'Cust.V'], ['MASQUE', '9', 'Z']] },
      { nom: 'Données', lignes: lignesSEE(25) }] });
    const r = await importer(page, 'multi.xlsx', fichier);
    const f = c.getSheetByName('SEE');
    verifier('l’en-tête est cherché onglet par onglet, les visibles d’abord : « Données »',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 26 && f.valeurs[1][0] === 'TFE311A0600', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs[1]));
    await page.close();
  }

  // =================================================================
  section('Un CSV : séparateur, guillemets, accents Windows');
  {
    const c = classeur({ ths: true });
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const texte = 'Nommage WD BFLOW;;;\r\n;;;\r\nNAME;SOL.;Cust.V;Libellé\r\nTFE311A0600;001;A;"Faisceau ; « été »"\r\n"HAR253A0011";"002";"B";"ligne\r\ncoupée ""citée"""\r\n';
    const r = await importer(page, 'see.csv', Buffer.from(texte, 'latin1'), { contrat: 'THS', toutes: true });
    const f = c.getSheetByName('SEE THS');
    verifier('un CSV en Windows-1252, « ; », guillemets doublés et retour à la ligne dans un champ : deux lignes justes, dans « SEE THS » (créé)',
      /\bok\b/.test(r.etat.classe) && f && f.valeurs.length === 3 && f.valeurs[1].join('|') === 'TFE311A0600|001|A|Faisceau ; « été »' &&
      f.valeurs[2].join('|') === 'HAR253A0011|002|B|ligne\r\ncoupée "citée"', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    verifier('« SEE THS » est créé au bout ; « SEE HDK » n’existe pas', nomsOnglets(c)[nomsOnglets(c).length - 1] === 'SEE THS' && !c.getSheetByName('SEE HDK'), nomsOnglets(c).join(', '));
    await page.close();
  }

  // =================================================================
  section('Ce qui ne marche pas le dit, et ne touche à rien');
  {
    const ancien = new Feuille('SEE HDK', [['NAME', 'SOL.', 'Cust.V'], ['OLD', '1', 'A']]);
    const c = classeur({ ths: true, autres: [ancien] });
    const ctx = chargerServeur(c, {});
    const avant = JSON.stringify(ancien.valeurs);
    let page = await fenetre(ctx);
    let r = await importer(page, 'autre.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: [['Titre'], ['REF', 'SOL.', 'Version'], ['X', '1', 'A']] }] }));
    verifier('pas d’en-tête NAME / SOL. / Cust.V : le message nomme les colonnes cherchées et la ligne la plus proche',
      /erreur/.test(r.etat.classe) && /Aucune ligne d’en-tête avec NAME, SOL\., Cust\.V/.test(r.etat.texte) && /La ligne 2 de « S » en porte 1 sur 3/.test(r.etat.texte) &&
      /Rien n’a été remplacé/.test(r.etat.texte), r.etat.texte);
    verifier('et le classeur n’a pas bougé (aucun appel au serveur)', page.__appels.length === 0 && JSON.stringify(ancien.valeurs) === avant);
    const ole = Buffer.concat([Buffer.from([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]), Buffer.alloc(600)]);
    r = await importer(page, 'vieux.xls', ole);
    verifier('un ancien .xls : la fenêtre dit qu’elle ne le lit pas, et l’autre chemin (Fichier → Importer)',
      /erreur/.test(r.etat.classe) && /\.xls/.test(r.etat.texte) && /Fichier → Importer/.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'tronque.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(20) }] }).subarray(0, 900));
    verifier('un .xlsx tronqué (téléchargement pas fini) : un message clair', /erreur/.test(r.etat.classe) && /pas un classeur \.xlsx lisible|abîmé|introuvable/.test(r.etat.texte), r.etat.texte);
    await page.close();

    /* Le serveur lâche au deuxième lot : l'ancien onglet reste, le temporaire part. */
    page = await fenetre(ctx, html => html.replace('"maxLignesLot":20000', '"maxLignesLot":50'));
    const vrai = ctx.importSecondeBaseLot;
    let lots = 0;
    ctx.importSecondeBaseLot = function () { lots++; if (lots === 2) throw new Error('Service Spreadsheets indisponible'); return vrai.apply(null, arguments); };
    r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(200) }] }), { contrat: 'HDK' });
    ctx.importSecondeBaseLot = vrai;
    await page.waitForTimeout(300);
    verifier('une panne au milieu : le message la dit, « SEE HDK » est intact, l’onglet temporaire est retiré',
      /erreur/.test(r.etat.classe) && /Service Spreadsheets indisponible/.test(r.etat.texte) && JSON.stringify(c.getSheetByName('SEE HDK').valeurs) === avant &&
      !nomsOnglets(c).some(x => /\(import\)/.test(x)), r.etat.texte + ' / ' + nomsOnglets(c).join(', '));
    /* Puis le même import, relancé, passe en plusieurs lots. */
    r = await importer(page, 'see.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(200) }] }), { contrat: 'HDK' });
    verifier('relancé : il passe, en lots de 50 lignes', /\bok\b/.test(r.etat.classe) && c.getSheetByName('SEE HDK').valeurs.length === 201 &&
      page.__appels.filter(x => x === 'importSecondeBaseLot').length >= 5, r.etat.texte);
    /* Un import incomplet (des lignes perdues en route) n'est pas posé. */
    let fin = '';
    try {
      const d = ctx.importSecondeBaseDebut('HDK');
      ctx.importSecondeBaseLot(d.feuille, 1, [['NAME', 'SOL.', 'Cust.V'], ['A', '1', 'B']]);
      ctx.importSecondeBaseFin(d.feuille, 'HDK', 5);
    } catch (e) { fin = e.message; }
    verifier('des lignes manquantes à la fin : rien n’est remplacé, et l’onglet temporaire part',
      /Import incomplet : 2 lignes reçues sur 5/.test(fin) && c.getSheetByName('SEE HDK').valeurs.length === 201 && !nomsOnglets(c).some(x => /\(import\)/.test(x)), fin);
    await page.close();
  }

  // =================================================================
  section('Un gros export : 120 000 lignes × 24 colonnes');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const entete = ['SCHEMA NUMBER', 'NAME', 'SOL.', 'Cust.V'].concat(Array.from({ length: 20 }, (_, k) => 'Colonne ' + (k + 1)));
    const n = 120000;
    const lignes = [['Nommage WD BFLOW'], [], entete];
    for (let i = 0; i < n; i++) {
      const l = ['S-' + i, 'TFE' + (311 + i % 90) + 'A' + String(i).padStart(6, '0'), String(1 + i % 4).padStart(3, '0'), ['A', 'B', 'C', 'D'][i % 4]];
      for (let k = 0; k < 20; k++) l.push(k % 3 ? 'valeur ' + ((i * 7 + k) % 5000) : { n: 45000 + (i % 900), fmt: 'date' });
      lignes.push(l);
    }
    const fichier = xlsx({ onglets: [{ nom: 'Export', lignes }] });
    const r = await importer(page, 'gros.xlsx', fichier, { delai: 300000 });
    const f = c.getSheetByName('SEE');
    verifier('importé (' + (fichier.length / 1048576).toFixed(1) + ' Mo, ' + (r.duree / 1000).toFixed(1) + ' s) : ' + n + ' lignes, trois colonnes',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === n + 1 && f.valeurs[n][0] === 'TFE' + (311 + (n - 1) % 90) + 'A' + String(n - 1).padStart(6, '0'), r.etat.texte);
    verifier('en moins de deux minutes', r.duree < 120000, (r.duree / 1000).toFixed(1) + ' s');
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

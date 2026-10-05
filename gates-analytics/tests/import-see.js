/* L'import des exports GATES et SEE sans Excel (menu Suivi FWD → Importer
   les exports GATES et SEE) : la vraie fenêtre, rendue par le vrai Code.gs,
   ouverte dans un vrai navigateur ; google.script.run y répond par les
   vraies fonctions du serveur, sur un classeur en mémoire (qui compte, comme
   Sheets, ses dix millions de cellules, et fusionne comme lui). Les fichiers
   sont fabriqués pour l'occasion (tests/fabriquer-xlsx.js) : exports GATES à
   la vraie structure (tests/feuille-gates.js : 138 colonnes, seize fusions
   dans la ligne des groupes), exports SEE ; chaînes partagées ou en ligne,
   chaînes riches, styles, préfixes, Zip64, CSV, pages web et XML 2003
   nommés .xls. Et les vrais .xls : ceux de tests/xls/, écrits par
   LibreOffice, SheetJS et xlwt (tests/preparer-xls.js), comparés au .xlsx
   d'où ils viennent et à la lecture qu'en fait SheetJS (l'oracle) ; ceux
   de tests/fabriquer-xls.js, écrits octet par octet pour chaque cas du
   format ; et les pages web archivées (.mht). */
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');
const zlib = require('zlib');
const { chargerServeur } = require('./build-addon');
const { Feuille, Classeur } = require('./faux-classeur');
const { feuilleGates, colonne } = require('./feuille-gates');
const { xlsx, zip } = require('./fabriquer-xlsx');
const FX = require('./fabriquer-xls');

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

// ===================================================================== les exports GATES
const I_REF = colonne('Référence UD'), I_DATE = colonne('Date création'), I_ATA = colonne('ATA');
const I_SUIVIE = colonne('Avancement Définition Electrique', 'HDK AA 011');
/* Un export GATES pour un contrat : la vraie structure, et au besoin des
   références à lui (« THS-21-1000 », ou calculées), ses groupes « XXX AA … »
   renommés, sa colonne suivie changée. Ligne 1 : les groupes ; ligne 2 : les
   en-têtes ; ligne 3 : une ligne de service sans référence ; puis les plans. */
function gates(n, options) {
  const o = options || {}, g = feuilleGates(n);
  const valeurs = g.valeurs.map(l => l.slice());
  valeurs.forEach((l, r) => {
    if (r < 3) return;
    if (o.prefixe) l[I_REF] = l[I_REF].replace(/^UD-/, o.prefixe + '-');
    if (o.refs) l[I_REF] = o.refs(r - 3);
    if (o.avancement) l[I_SUIVIE] = o.avancement(r - 3, l[I_SUIVIE]);
  });
  if (o.groupe) valeurs[0] = valeurs[0].map(v => v.replace(/^HDK AA/, o.groupe + ' AA'));
  return { valeurs, fusions: g.fusions.map(f => Object.assign({}, f)) };
}
function ongletGates(nom, g) { return new Feuille(nom, g.valeurs.map(l => l.slice()), false, g.fusions.map(f => Object.assign({}, f))); }
/* Le numéro de série d'Excel pour une date jj/mm/aaaa. */
function serie(t) { const m = /^(\d\d)\/(\d\d)\/(\d{4})$/.exec(t); return (Date.UTC(+m[3], +m[2] - 1, +m[1]) - Date.UTC(1899, 11, 30)) / 864e5; }
/* L'export en .xlsx, comme GATES l'écrit : chaînes partagées, la date de
   création en nombre au format jj/mm/aaaa, l'ATA en nombre, les seize
   fusions de la ligne des groupes après les lignes. `titres` : des lignes
   ajoutées au-dessus. */
function xlsxGates(g, options) {
  const o = options || {}, titres = o.titres || [];
  const lignes = titres.map(t => [t]).concat(g.valeurs.map((l, r) => l.map((v, j) => {
    if (r >= 2 && j === I_DATE && /^\d\d\/\d\d\/\d{4}$/.test(v)) return { n: serie(v), fmt: 'jour' };
    if (r >= 2 && j === I_ATA && /^\d+$/.test(v)) return Number(v);
    return v;
  })));
  return xlsx({ onglets: [{ nom: o.onglet || 'Export', lignes, fusions: g.fusions.map(f => ({ ligne: f.ligne + titres.length, col: f.col, larg: f.larg })) }] });
}
/* L'export en CSV (« ; », champs entre guillemets au besoin) : pas de fusion ; `sansGroupes` : sans la ligne des groupes. */
function csvGates(g, options) {
  const champ = v => /[;"\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  return (options && options.sansGroupes ? g.valeurs.slice(1) : g.valeurs).map(l => l.map(champ).join(';')).join('\r\n') + '\r\n';
}
const echHtml = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
/* L'export en page web : un titre au-dessus (colspan sur toute la largeur),
   les groupes en colspan, et la première colonne de la ligne des groupes
   étendue sur deux lignes (rowspan) — la ligne d'en-têtes commence donc à
   la deuxième colonne. */
function htmlGates(g, titre) {
  const parCol = {};
  g.fusions.forEach(f => { parCol[f.col] = f.larg; });
  const lignes = ['<tr><td colspan="' + g.valeurs[1].length + '"><b>' + echHtml(titre) + '</b></td></tr>'];
  g.valeurs.forEach((l, r) => {
    let cellules = '';
    for (let j = r === 1 ? 1 : 0; j < l.length; j++) {
      const larg = r === 0 ? parCol[j + 1] || 1 : 1;
      cellules += '<td' + (larg > 1 ? ' colspan="' + larg + '"' : '') + (r === 0 && j === 0 ? ' rowspan="2"' : '') + '>' + echHtml(l[j]) + '</td>';
      j += larg - 1;
    }
    lignes.push('<tr>' + cellules + '</tr>');
  });
  return '<html><head><meta charset="utf-8"></head><body><table>' + lignes.join('') + '</table></body></html>';
}
/* L'export en XML 2003 : chaque cellule à son ss:Index, les groupes en ss:MergeAcross. */
function xml2003Gates(g) {
  const parCol = {};
  g.fusions.forEach(f => { parCol[f.col] = f.larg; });
  const lignes = g.valeurs.map((l, r) => '<Row>' + l.map((v, j) => {
    if (v === '') return '';
    const larg = r === 0 ? parCol[j + 1] || 1 : 1;
    return '<Cell ss:Index="' + (j + 1) + '"' + (larg > 1 ? ' ss:MergeAcross="' + (larg - 1) + '"' : '') + '><Data ss:Type="String">' + echHtml(v) + '</Data></Cell>';
  }).join('') + '</Row>');
  return '<?xml version="1.0"?><?mso-application progid="Excel.Sheet"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" ' +
    'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="Export"><Table>' + lignes.join('') + '</Table></Worksheet></Workbook>';
}

// ===================================================================== les exports SEE
/* Les lignes d'un export SEE : titre, ligne vide, en-tête en ligne 3. `decalage` : une autre famille de noms. */
const ENTETE_SEE = ['SCHEMA NUMBER', 'NAME', 'SOL.', 'Cust.V', 'Released Date', 'Validated Date', 'REDRAW', 'ARCHIVED'];
function nomDe(i) { return 'TFE' + String(311 + (i % 50)) + 'A' + String(600 + i).padStart(4, '0'); }
function lignesSEE(n, options) {
  const opt = options || {}, d = opt.decalage || 0;
  const lignes = [['Nommage WD BFLOW'], [], ENTETE_SEE];
  for (let i = 0; i < n; i++) {
    lignes.push(['S-' + i, nomDe(i + d), opt.solNombre ? { n: (i % 3) + 1, fmt: 'zeros5' } : String((i % 3) + 1).padStart(3, '0'),
      opt.custV ? opt.custV(i) : ['A', 'B', 'C'][i % 3], { n: 45000 + i, fmt: 'date' }, i % 4 ? { n: 45100 + i, fmt: 'date' } : null, { b: i % 2 === 0 }, 'non']);
  }
  return lignes;
}
/* La référence GATES du plan de la ligne i d'un export SEE : le A remis à sa place, la solution, l'indice. */
function refGates(i, decalage) {
  const nom = nomDe(i + (decalage || 0));
  return nom.slice(0, 6) + nom.charAt(7) + 'A' + nom.slice(8) + String((i % 3) + 1).padStart(3, '0') + ['A', 'B', 'C'][i % 3];
}
const seeXlsx = (n, options) => xlsx({ onglets: [{ nom: 'S', lignes: lignesSEE(n, options) }] });

// ===================================================================== les classeurs
/* Un classeur : HDK (la vraie structure GATES), THS si demandé (ses propres références), et des onglets en plus. */
function classeur(options) {
  const opt = options || {};
  const feuilles = [ongletGates('HDK', gates(40))];
  if (opt.ths) feuilles.push(ongletGates('THS', gates(30, { prefixe: 'THS' })));
  (opt.autres || []).forEach(f => feuilles.push(f));
  return new Classeur(feuilles, 'Classeur SEE');
}
function ajouterOnglet(c, f) { f.classeur = c; c.feuilles.push(f); return f; }
const nomsOnglets = c => c.getSheets().map(f => f.getName());
const sansImport = c => !nomsOnglets(c).some(x => /\((import|ancien) /.test(x));
/* La configuration livrée suit HDK AA 011 > Avancement Définition Electrique ;
   chargerServeur la vide pour un classeur sans ce bloc (l'essai d'un premier
   contrat, d'un classeur vide). serveur() la remet, telle que livrée. */
const LIVREE = (function () {
  const g = feuilleGates(3);
  const ctx = chargerServeur(new Classeur([new Feuille('HDK', g.valeurs, false, g.fusions)]), {});
  return { fwd: vm.runInContext('CONFIG.COLONNE_FWD', ctx), concept: vm.runInContext('CONFIG.COLONNE_CONCEPT', ctx) };
})();
function serveur(c) {
  const ctx = chargerServeur(c, {});
  vm.runInContext('CONFIG.COLONNE_FWD = ' + JSON.stringify(LIVREE.fwd) + '; CONFIG.COLONNE_CONCEPT = ' + JSON.stringify(LIVREE.concept) + ';', ctx);
  return ctx;
}
const semaineDe = (ctx, decalageJours) => ctx.numeroSemaineISO(new Date(Date.now() - (decalageJours || 0) * 864e5));

// ===================================================================== les vrais .xls
const lireXls = nom => fs.readFileSync(path.join(__dirname, 'xls', nom));
const ORACLE = JSON.parse(zlib.gunzipSync(lireXls('oracle.json.gz')).toString('utf8'));
/* Un tableau sans ses cellules vides en fin de ligne ni ses lignes vides à la fin : deux lectures se comparent ainsi. */
function rogne(lignes) {
  const l = (lignes || []).map(x => {
    const y = (x || []).map(v => v === undefined || v === null ? '' : String(v));
    while (y.length && y[y.length - 1] === '') y.pop();
    return y;
  });
  while (l.length && !l[l.length - 1].length) l.pop();
  return l;
}
/* Le premier écart entre deux tableaux (« ligne 4, colonne 7 : … au lieu de … »), ou ''. */
function premierEcart(obtenu, attendu) {
  const a = rogne(obtenu), b = rogne(attendu);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] || [], y = b[i] || [];
    for (let j = 0; j < Math.max(x.length, y.length); j++) {
      if ((x[j] || '') !== (y[j] || '')) return 'ligne ' + (i + 1) + ', colonne ' + (j + 1) + ' : ' + JSON.stringify(x[j] || '') + ' au lieu de ' + JSON.stringify(y[j] || '');
    }
  }
  return '';
}
/* Les cellules fusionnées d'un onglet du faux classeur, [ligne, col, hauteur, largeur], triées. */
const fusionsDe = f => (f.fusions || []).map(x => [x.ligne, x.col, x.haut || 1, x.larg]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
/* L'onglet SEE que la fenêtre poserait, « toutes » cochée, d'après les lignes brutes d'un onglet : la
   ligne qui porte NAME, SOL. et Cust.V, ses colonnes nommées, et dessous les lignes qui ne sont pas vides. */
function seeAttendu(lignes) {
  const n = v => String(v || '').trim().toLowerCase();
  const i = lignes.findIndex(l => ['name', 'sol.', 'cust.v'].every(k => l.map(n).indexOf(k) !== -1));
  const cols = lignes[i].map((v, j) => n(v) ? j : -1).filter(j => j !== -1);
  return [cols.map(j => String(lignes[i][j]).trim())].concat(lignes.slice(i + 1).map(l => cols.map(j => l[j] === undefined ? '' : l[j]))
    .filter(l => l.some(v => String(v).trim() !== '')));
}
/* Les types des enregistrements du flux « Workbook » d'un .xls (conteneur à 512 octets, sans DIFAT) : ce
   qu'un fichier de tests/xls exerce vraiment. */
function typesEnregistrements(b) {
  const taille = 1 << b.readUInt16LE(0x1E), fat = [];
  for (let i = 0; i < Math.min(109, b.readUInt32LE(0x2C)); i++) {
    const s = b.readUInt32LE(0x4C + 4 * i);
    for (let k = 0; k < taille / 4; k++) fat.push(b.readUInt32LE((s + 1) * taille + 4 * k));
  }
  const chaine = s => { const l = []; while (s < 0xFFFFFFFA && l.length < 1e6) { l.push(s); s = fat[s]; } return l; };
  const secteurs = l => Buffer.concat(l.map(s => b.subarray((s + 1) * taille, (s + 2) * taille)));
  const dir = secteurs(chaine(b.readUInt32LE(0x30)));
  let w = null;
  for (let k = 0; k < dir.length; k += 128) {
    if (dir.subarray(k, k + 16).toString('utf16le') === 'Workbook') w = secteurs(chaine(dir.readUInt32LE(k + 116))).subarray(0, dir.readUInt32LE(k + 120));
  }
  const types = [];
  for (let p = 0; w && p + 4 <= w.length; p += 4 + w.readUInt16LE(p + 2)) types.push(w.readUInt16LE(p));
  return types;
}
/* Une page web comme Excel l'enregistre : attributs sans guillemets (colspan=16), classes, nombres à droite ;
   et des cases vides qui se suivent regroupées en une seule, « colspan=N style='mso-ignore:colspan' » —
   ce n'est pas une fusion. */
function htmlExcel(valeurs, fusionsLigne1, titre) {
  const parCol = {};
  (fusionsLigne1 || []).forEach(f => { parCol[f.col] = f.larg; });
  let lignes = '';
  valeurs.forEach((l, r) => {
    let cellules = '';
    for (let j = 0; j < l.length; j++) {
      const larg = r === 0 ? parCol[j + 1] || 1 : 1;
      let vides = 0;
      while (larg === 1 && j + vides < l.length && l[j + vides] === '' && !(r === 0 && parCol[j + vides + 1])) vides++;
      if (vides > 1) { cellules += '<td colspan=' + vides + ' style=\'mso-ignore:colspan\'></td>'; j += vides - 1; continue; }
      cellules += '<td' + (larg > 1 ? ' colspan=' + larg : '') + ' class=xl' + (65 + (j % 3)) + (/^\d+$/.test(l[j]) ? ' align=right x:num' : '') + '>' +
        echHtml(l[j]) + '</td>';
      j += larg - 1;
    }
    lignes += ' <tr height=20 style=\'height:15.0pt\'>\r\n  ' + cellules + '\r\n </tr>\r\n';
  });
  return '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">\r\n' +
    '<head>\r\n<meta name=ProgId content=Excel.Sheet>\r\n<meta name=Generator content="Microsoft Excel 15">\r\n<style>\r\n.xl65 {mso-number-format:"\\@";}\r\n</style>\r\n' +
    (titre ? '<title>' + echHtml(titre) + '</title>\r\n' : '') + '</head>\r\n<body link=blue vlink=purple>\r\n' +
    '<table border=0 cellpadding=0 cellspacing=0 width=8832 style=\'border-collapse:collapse;table-layout:fixed\'>\r\n' + lignes + '</table>\r\n</body>\r\n</html>\r\n';
}
/* Le paquet de la page, sans ce qui dépend de l'heure. */
const paquetSansDate = o => { const x = JSON.parse(JSON.stringify(o)); delete x.genereLe; delete x.releves; delete x.avis; delete x.rapprochement; return JSON.stringify(x); };

(async () => {
  const nav = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const dossier = fs.mkdtempSync(path.join(os.tmpdir(), 'import-see-'));

  /* La fenêtre d'import pour un classeur : rendue par importerSecondeBase,
     ouverte dans le navigateur, google.script.run branché sur le serveur.
     page.__retard : un délai (ms) avant chaque lot, pour voir la fenêtre
     pendant l'envoi ; page.__cibles : la cible de chaque début d'import ;
     page.__feuilles : l'onglet temporaire que chaque début a créé. */
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
    page.__cibles = [];
    page.__feuilles = [];
    page.__retard = 0;
    await page.exposeFunction('__appelServeur', async (nom, args) => {
      page.__appels.push(nom);
      if (nom === 'importSecondeBaseDebut') page.__cibles.push(JSON.stringify(args[1]));
      if (nom === 'importSecondeBaseLot' && page.__retard) await new Promise(r => setTimeout(r, page.__retard));
      try {
        const v = ctx[nom].apply(null, args);
        if (nom === 'importSecondeBaseDebut' && v && v.feuille) page.__feuilles.push(v.feuille);
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
  /* Ce que montre chaque ligne de la liste. */
  function lignes(page) {
    return page.evaluate(() => Array.prototype.map.call(document.querySelectorAll('#liste .fichier'), li => ({
      etat: li.getAttribute('data-etat'),
      sorte: li.querySelector('.sorte').hidden ? '' : li.querySelector('.sorte').textContent,
      lu: li.querySelector('.lu').textContent,
      choix: li.querySelector('.contrat').value,
      choixVisible: !li.querySelector('.choix').hidden,
      options: Array.prototype.map.call(li.querySelector('.contrat').options, o => o.value),
      note: li.querySelector('.note').textContent,
      date: li.querySelector('.date').textContent,
      verifier: li.querySelector('.note').classList.contains('verifier'),
      nouveau: li.querySelector('.nouveau').hidden ? null : li.querySelector('.nouveau').value,
      cible: li.querySelector('.cible').textContent,
      resultat: li.querySelector('.resultat').textContent
    })));
  }
  function fenetreEtat(page) {
    return page.evaluate(() => ({
      desactive: document.getElementById('importer').disabled,
      blocage: document.getElementById('blocage').textContent,
      etat: document.getElementById('etat').textContent,
      archiverVisible: !document.getElementById('option-archiver').hidden,
      archiverCoche: document.getElementById('archiver').checked,
      archiverTexte: document.getElementById('option-archiver').textContent,
      retirerErreurs: !document.getElementById('retirer-erreurs').hidden,
      n: document.querySelectorAll('#liste .fichier').length
    }));
  }
  /* Chaque fichier lu (ou en erreur), son contrat deviné, son nom vérifié. */
  async function attendreLecture(page) {
    await page.waitForFunction(() => Array.prototype.every.call(document.querySelectorAll('#liste .fichier'),
      li => /^(lu|erreur|fait|echec)$/.test(li.getAttribute('data-etat') || '') && !li.hasAttribute('data-occupe')), null, { timeout: 120000 });
  }
  /* `date` (ms) : la date du fichier, que setInputFiles ne sait pas poser —
     les fichiers sont alors glissés dans la fenêtre, construits avec elle. */
  async function ajouter(page, fichiers) {
    if (fichiers.some(f => f.date)) {
      await page.evaluate(liste => {
        const dt = new DataTransfer();
        liste.forEach(f => {
          const bin = atob(f.b64), u = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
          dt.items.add(new File([u], f.nom, f.date ? { lastModified: f.date } : {}));
        });
        document.getElementById('depot').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
      }, fichiers.map(f => ({ nom: f.nom, b64: Buffer.from(f.contenu).toString('base64'), date: f.date || 0 })));
    } else {
      /* Playwright ne passe pas un tampon de plus de 50 Mo : un gros fichier part d'un fichier sur le disque, à son nom. */
      await page.setInputFiles('#fichier', fichiers.map(f => {
        if (f.contenu.length < 40 * 1048576) return { name: f.nom, mimeType: 'application/octet-stream', buffer: f.contenu };
        const sous = fs.mkdtempSync(path.join(dossier, 'gros-'));
        fs.writeFileSync(path.join(sous, f.nom), f.contenu);
        return path.join(sous, f.nom);
      }));
    }
    await attendreLecture(page);
    return lignes(page);
  }
  /* Une capture de la fenêtre, si CAPTURES nomme un dossier (pour la relecture à l'œil). */
  async function capture(page, nom) {
    if (!process.env.CAPTURES) return;
    await page.setViewportSize({ width: 720, height: 1000 });
    await page.screenshot({ path: path.join(process.env.CAPTURES, nom + '.png'), fullPage: true });
  }
  async function vider(page) {
    let bouton;
    while ((bouton = await page.$('#liste .fichier .retirer:not([hidden])'))) await bouton.click();
  }
  async function choisir(page, i, valeur) {
    await page.locator('#liste .fichier').nth(i).locator('.contrat').selectOption(valeur);
    await attendreLecture(page);
  }
  async function attendreFin(page, delai) {
    /* La fin : le bilan affiché, et la fenêtre rendue (la liste des contrats relue). */
    await page.waitForFunction(() => /\bok\b|erreur/.test(document.getElementById('etat').className) && !document.getElementById('choisir').disabled, null, { timeout: delai || 120000 });
    return page.evaluate(() => ({ classe: document.getElementById('etat').className, texte: document.getElementById('etat').textContent }));
  }
  /* « Importer », s'il est allumé ; sinon, pourquoi il attend. */
  async function lancer(page, delai) {
    const attente = await page.evaluate(() => document.getElementById('importer').disabled ? (document.getElementById('blocage').textContent || 'éteint') : '');
    if (attente) return { classe: 'attente', texte: attente };
    const t0 = Date.now();
    await page.click('#importer');
    const etat = await attendreFin(page, delai);
    etat.duree = Date.now() - t0;
    return etat;
  }
  /* Un fichier seul, comme avant le débrief 20 : la liste vidée, la case
     « toutes » posée, le fichier ajouté et lu, le contrat choisi au besoin ;
     un fichier qui ne se lit pas rend l'erreur de sa ligne, sans rien envoyer. */
  async function importer(page, nom, contenu, options) {
    const opt = options || {};
    await vider(page);
    if (opt.toutes) { if (!(await page.isChecked('#toutes'))) await page.check('#toutes'); }
    else if (await page.isChecked('#toutes')) await page.uncheck('#toutes');
    const ligne = (await ajouter(page, [{ nom, contenu }]))[0];
    if (ligne.etat === 'erreur') return { etat: { classe: 'erreur', texte: ligne.lu }, ligne };
    if (opt.contrat) await choisir(page, 0, opt.contrat);
    if (opt.sansArchiver && await page.isVisible('#option-archiver')) await page.uncheck('#archiver');
    const etat = await lancer(page, opt.delai);
    return { etat, duree: etat.duree, ligne };
  }
  /* Le jeton, et les paramètres, d'une fenêtre ouverte par le menu. */
  function parametres(ctx) {
    ctx.importerSecondeBase();
    return JSON.parse(/\)\((\{[\s\S]*\})\);<\/script>/.exec(ctx.__dialogue.getContent())[1].replace(/\\u003c/g, '<'));
  }
  function jetonDe(ctx) { return parametres(ctx).jeton; }
  const rapide = html => html.replace('"maxLignesLot":20000', '"maxLignesLot":50').replace('"pausesReprise":[2000,6000]', '"pausesReprise":[30,60]');

  // =================================================================
  section('Le menu, la garde et le jeton');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    ctx.onOpen();
    verifier('le menu Suivi FWD propose « Importer les exports GATES et SEE… » (la fonction garde son nom, importerSecondeBase)',
      ctx.__menu.indexOf('importerSecondeBase') !== -1 && ctx.libelleImport() === 'Importer les exports GATES et SEE…', JSON.stringify(ctx.__menu) + ' ' + ctx.libelleImport());
    ctx.importerSecondeBase();
    verifier('la fenêtre porte le même titre', ctx.__titreDialogue === 'Importer les exports GATES et SEE', ctx.__titreDialogue);
    const jeton = jetonDe(ctx);
    ctx.__sansInterface = true;
    const fonctions = ['importerSecondeBase', 'importSecondeBaseDebut', 'importSecondeBaseLot', 'importSecondeBaseFin', 'importSecondeBaseAbandon',
      'importDevinerContratSEE', 'importVerifierNouveauContrat', 'importArchiverReleve', 'importContrats'];
    const refus = fonctions.map(n => {
      try { ctx[n]('faux-jeton-123', 'HDK', 3, 5); return n + ':passe'; } catch (e) { return /Geste refusé/.test(e.message) ? '' : n + ':' + e.message; }
    }).filter(Boolean);
    verifier('hors du classeur (la page du tableau de bord), sans le jeton de la fenêtre, chaque fonction de l’import est refusée — deviner, vérifier un nom, archiver, relire les contrats compris',
      !refus.length, refus.join(' | '));
    /* google.script.run atteint toute fonction dont le nom ne finit pas par
       « _ » : celle qui donne le jeton doit en porter un, sinon la page
       se le fait donner (chasse du débrief 20). */
    const code = fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8');
    const publiques = ['ouvrirJetonImport', 'gesteImport', 'parametresImport'].filter(n => new RegExp('function ' + n + '\\s*\\(').test(code));
    verifier('la fonction qui donne le jeton de la fenêtre est privée (« _ ») : la page ne peut pas se le faire donner',
      !publiques.length && typeof ctx.ouvrirJetonImport_ === 'function', publiques.join(', '));
    let avecJeton = '';
    try {
      const d = ctx.importSecondeBaseDebut(jeton, 'HDK', 3, 5);
      ctx.importSecondeBaseAbandon(jeton, d.feuille);
      const g = ctx.importSecondeBaseDebut(jeton, { sorte: 'gates', contrat: 'HDK' }, 3, 5);
      ctx.importSecondeBaseAbandon(jeton, g.feuille);
      avecJeton = /^SEE HDK \(import [0-9a-z]+\)$/.test(d.feuille) && /^HDK \(import [0-9a-z]+\)$/.test(g.feuille) ? 'passe' : d.feuille + ' / ' + g.feuille;
    } catch (e) { avecJeton = e.message; }
    verifier('avec le jeton de la fenêtre ouverte par le menu, l’import passe même si l’interface ne répond pas — une base SEE (« HDK » tout court, comme avant) ou l’onglet du contrat',
      avecJeton === 'passe' && sansImport(c), avecJeton);
    ctx.__sansInterface = false;
    let arbitraire = '';
    try { ctx.importSecondeBaseLot(jeton, 'HDK', 1, [['écrasé']]); } catch (e) { arbitraire = e.message; }
    verifier('un lot ne s’écrit que dans l’onglet temporaire d’un import, jamais dans un autre (« HDK »)',
      /non reconnu/.test(arbitraire) && c.getSheetByName('HDK').valeurs[0][0] !== 'écrasé', arbitraire);
    ajouterOnglet(c, new Feuille('HDK (ancien abc123)', [['gardé']]));
    let ancien = '';
    try { ctx.importSecondeBaseLot(jeton, 'HDK (ancien abc123)', 1, [['écrasé']]); } catch (e) { ancien = e.message; }
    verifier('ni dans l’ancien onglet mis de côté pendant un échange (« … (ancien …) »)', /non reconnu/.test(ancien) && c.getSheetByName('HDK (ancien abc123)').valeurs[0][0] === 'gardé', ancien);
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
    const vide = await fenetreEtat(page);
    const n = 1500;
    /* Pendant l'envoi : « Fermer » éteint, la consigne affichée, la largeur de l'onglet temporaire mesurée. */
    const vrai = ctx.importSecondeBaseLot;
    const mesures = [];
    ctx.importSecondeBaseLot = function (j, nom) { const f = c.getSheetByName(nom); mesures.push(f.getMaxColumns() + '×' + f.getMaxRows()); return vrai.apply(null, arguments); };
    page.__retard = 400;
    const ui = (await ajouter(page, [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeXlsx(n, { solNombre: true }) }]))[0];
    verifier('la fenêtre attend des fichiers (« Importer » éteint) ; le fichier ajouté est lu tout de suite, reconnu SEE, rattaché au contrat de l’onglet affiché (« à vérifier », faute de mieux), et dit l’onglet qu’il remplacera',
      vide.desactive && vide.n === 0 && ui.sorte === 'SEE' && ui.choix === 'HDK' && ui.choixVisible && ui.verifier && /Remplacera l’onglet « SEE HDK »/.test(ui.cible),
      JSON.stringify([vide, ui]));
    await page.click('#importer');
    await page.waitForFunction(() => /Envoi au classeur|Préparation/.test(document.getElementById('progres').textContent), null, { timeout: 30000 });
    const pendant = await page.evaluate(() => ({ fermer: document.getElementById('fermer').disabled, consigne: !document.getElementById('consigne').hidden,
      lu: document.querySelector('#liste .fichier .lu').textContent, retirer: !!document.querySelector('#liste .retirer:not([hidden])'),
      choisir: document.getElementById('choisir').disabled }));
    const r = { etat: await attendreFin(page) };
    ctx.importSecondeBaseLot = vrai;
    verifier('pendant l’envoi, « Fermer » est éteint, « Ne pas fermer cette fenêtre avant la fin » s’affiche, ce qui a été lu reste dit, et rien ne s’ajoute ni ne se retire',
      pendant.fermer && pendant.consigne && /1\u202f500 lignes, colonnes NAME, SOL\., Cust\.V/.test(pendant.lu) && !pendant.retirer && pendant.choisir, JSON.stringify(pendant));
    verifier('l’onglet temporaire est taillé d’avance : trois colonnes, les 1 501 lignes — pas les 26 colonnes d’un onglet neuf',
      mesures.length && mesures.every(x => x === '3×1501'), mesures.join(', '));
    const f = c.getSheetByName('SEE HDK');
    verifier('l’import réussit et le dit', /\bok\b/.test(r.etat.classe) && /1\u202f500 lignes/.test(r.etat.texte) && /comparaison est prête/.test(r.etat.texte) &&
      /Rouvrir le tableau de bord/.test(r.etat.texte), r.etat.texte);
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
    verifier('la fenêtre n’a appelé que les gestes prévus, en ordre : deviner le contrat (il y en a deux), le début, les lots, la fin, puis la liste des contrats relue',
      page.__appels[0] === 'importDevinerContratSEE' && page.__appels[1] === 'importSecondeBaseDebut' &&
      page.__appels[page.__appels.length - 2] === 'importSecondeBaseFin' && page.__appels[page.__appels.length - 1] === 'importContrats' &&
      page.__appels.slice(2, -2).every(x => x === 'importSecondeBaseLot'), page.__appels.join(','));
    verifier('la ligne du fichier dit son résultat, et ne se retire plus', await page.evaluate(() => /1\u202f500 lignes dans l’onglet « SEE HDK »/.test(document.querySelector('#liste .fichier .resultat').textContent) &&
      !document.querySelector('#liste .retirer:not([hidden])')));
    /* Le même nombre de lignes, d'autres indices : le cache ne sert pas l'ancienne base. */
    page.__retard = 0;
    const r2 = await importer(page, 'see.xlsx', seeXlsx(n, { custV: () => 'Z' }));
    const apres2 = ctx.getDonneesPourClient('HDK');
    verifier('réimporté avec le même nombre de lignes (indices changés) : le paquet en cache suit ; un nouveau choix repart d’une liste propre',
      /\bok\b/.test(r2.etat.classe) && apres2.rapprochement.lignes[0]['Cust.V'] === 'Z' && (await fenetreEtat(page)).n === 1, JSON.stringify(apres2.rapprochement.lignes[0]));
    await page.close();
  }

  // =================================================================
  section('Le contrat proposé, l’onglet créé, et un onglet « HDK SEE »');
  {
    const c = classeur({ ths: true, autres: [new Feuille('SEE THS', [['NAME', 'SOL.', 'Cust.V'], ['X', '1', 'A']])] });
    const ctx = chargerServeur(c, {});
    const fichier = seeXlsx(10);
    c.setActiveSheet(c.getSheetByName('THS'));
    let page = await fenetre(ctx);
    const v1 = (await ajouter(page, [{ nom: 'see.xlsx', contenu: fichier }]))[0];
    await page.close();
    c.setActiveSheet(c.getSheetByName('SEE THS'));
    page = await fenetre(ctx);
    const v2 = (await ajouter(page, [{ nom: 'see.xlsx', contenu: fichier }]))[0];
    await page.close();
    verifier('sans meilleur indice, le contrat proposé est celui de l’onglet affiché — ou dont la base est affichée —, marqué « à vérifier »',
      v1.choix === 'THS' && v2.choix === 'THS' && v1.note === 'à vérifier' && v1.verifier, JSON.stringify([v1, v2]));

    const seul = classeur();
    const ctxSeul = chargerServeur(seul, {});
    page = await fenetre(ctxSeul);
    const l = (await ajouter(page, [{ nom: 'see.xlsx', contenu: seeXlsx(10) }]))[0];
    const r = { etat: await lancer(page) };
    verifier('un seul contrat, et un export SEE qui n’a aucun plan en commun avec lui : proposé quand même, mais « à vérifier », la liste visible — plus jamais sans un mot ; l’onglet créé est « SEE HDK »',
      l.choixVisible && l.verifier && l.choix === 'HDK' && /« HDK » est le seul contrat, mais l’échantillon n’y retrouve que 0 référence sur 10 : à vérifier\./.test(l.note) &&
      /Créera l’onglet « SEE HDK »/.test(l.cible) && /\bok\b/.test(r.etat.classe) && !!seul.getSheetByName('SEE HDK') && !seul.getSheetByName('SEE'),
      JSON.stringify(l) + ' / ' + nomsOnglets(seul).join(', '));
    verifier('avec un seul contrat aussi, l’échantillon part au serveur pour confirmer : deviner, le début, le lot, la fin, la liste relue',
      page.__appels.join() === 'importDevinerContratSEE,importSecondeBaseDebut,importSecondeBaseLot,importSecondeBaseFin,importContrats', page.__appels.join());
    await page.close();
    /* Le même seul contrat, et un export SEE qui recoupe ses plans : rien à vérifier, rien à choisir. */
    const recoupe = new Classeur([ongletGates('HDK', gates(40, { refs: i => refGates(i) }))]);
    page = await fenetre(serveur(recoupe));
    const lr = (await ajouter(page, [{ nom: 'see.xlsx', contenu: seeXlsx(30) }]))[0];
    verifier('un seul contrat, et l’échantillon le confirme : « HDK », sans « à vérifier », la liste cachée',
      lr.choix === 'HDK' && !lr.verifier && !lr.choixVisible && /30 références de l’échantillon sur 30 retrouvées dans « HDK »/.test(lr.note), JSON.stringify(lr));
    await page.close();

    const inverse = classeur({ ths: true, autres: [new Feuille('HDK SEE', [['NAME', 'SOL.', 'Cust.V'], ['OLD', '1', 'A']])] });
    const ctxInv = chargerServeur(inverse, {});
    page = await fenetre(ctxInv);
    const r2 = await importer(page, 'see.xlsx', seeXlsx(30), { contrat: 'HDK' });
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
      const lignesV = lignesSEE(40);
      if (v.spec.sansRef) lignesV.splice(1, 1);   // sans références, pas de ligne vide (Excel l'omettrait)
      const r = await importer(page, 'see.xlsx', xlsx(Object.assign({ onglets: [{ nom: 'S', lignes: lignesV }] }, v.spec)), { toutes: true });
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
    const riches = [['Titre'], ['name', 'Sol.', 'CUST.V', 'Note', 'Part', 'Prix', 'Grand', 'Sci', 'Code', 'Jour', 'Moment'],
      [{ riche: ['TFE', '311A0600'], phonetique: 'ていえふ' }, { str: '002' }, 'B', 'a & b <c> "d"\r\nfin', { n: 0.25, fmt: 'pct' }, { n: 1234.5, fmt: 'euro' },
        { n: 1234567, fmt: 'mille' }, { n: 12345, fmt: 'sci' }, { n: 7.5, fmt: 'zeros3' }, { n: 45000, fmt: 'jour' }, { n: 45000.5, fmt: 'jourheure' }],
      ['HAR253A0011', 7, 'C', { n: 3.5 }, { n: 0.1234, fmt: 'pct2' }, { n: 3, fmt: '0.00' }, { n: 1e21 }, { n: 1e-7 }, { n: 42, fmt: 'zeros3' }, '', '']];
    const r = await importer(page, 'riche.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: riches }] }), { toutes: true });
    const f = c.getSheetByName('SEE HDK');
    verifier('chaîne riche sans sa lecture phonétique, résultat de formule, échappements XML et « _x000D_ » rendus, en-tête trouvé sans tenir compte de la casse',
      /\bok\b/.test(r.etat.classe) && f.valeurs[0].slice(0, 4).join('|') === 'name|Sol.|CUST.V|Note' &&
      f.valeurs[1].slice(0, 4).join('|') === 'TFE311A0600|002|B|a & b <c> "d"\r\nfin' && f.valeurs[2].slice(0, 4).join('|') === 'HAR253A0011|7|C|3,5',
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    verifier('les nombres comme Excel les affiche : 25 %, 12,34 %, 1 234,50 €, 3,00, 1 234 567, 1,23E+04, 008, 042, 1E+21, 1E-07',
      f && f.valeurs[1].slice(4, 9).join('|') === '25\u202f%|1\u202f234,50 €|1\u202f234\u202f567|1,23E+04|008' &&
      f.valeurs[2].slice(4, 9).join('|') === '12,34\u202f%|3,00|1E+21|1E-07|042', JSON.stringify(f && [f.valeurs[1].slice(4), f.valeurs[2].slice(4)]));
    verifier('une date au format jj/mm/aaaa, et jj/mm/aaaa hh:mm : comme la cellule l’affiche', f && f.valeurs[1].slice(9).join('|') === '15/03/2023|15/03/2023 12:00',
      JSON.stringify(f && f.valeurs[1].slice(9)));
    await page.close();
  }

  // =================================================================
  section('Toutes les colonnes, sur demande');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    let page = await fenetre(ctx);
    const r = await importer(page, 'see.xlsx', seeXlsx(12), { toutes: true });
    const f = c.getSheetByName('SEE HDK');
    verifier('« Garder aussi les autres colonnes » : les huit colonnes, une date au format jour/mois/année, un booléen en VRAI/FAUX',
      /\bok\b/.test(r.etat.classe) && f.valeurs[0].length === 8 && f.valeurs[1][4] === '15/03/2023' && f.valeurs[1][6] === 'VRAI' && f.valeurs[1][5] === '',
      JSON.stringify(f && f.valeurs.slice(0, 2)));
    await page.close();
    const avant = JSON.stringify(f.valeurs);
    page = await fenetre(ctx, h => h.replace('"maxCellulesToutes":4000000', '"maxCellulesToutes":100'));
    const r2 = await importer(page, 'see.xlsx', seeXlsx(200), { toutes: true });
    verifier('au-delà du plafond de cellules, toutes les colonnes sont refusées tôt, à la lecture, sans rien envoyer',
      /erreur/.test(r2.etat.classe) && /trop pour le classeur/.test(r2.etat.texte) && page.__appels.length === 0 && JSON.stringify(c.getSheetByName('SEE HDK').valeurs) === avant, r2.etat.texte);
    /* La case décochée après coup : le fichier est relu, sans les autres colonnes. */
    await page.uncheck('#toutes');
    await attendreLecture(page);
    const relu = (await lignes(page))[0];
    verifier('la case décochée après coup : le fichier est relu de lui-même, et passe', relu.etat === 'lu' && /^200 lignes, colonnes NAME, SOL\., Cust\.V/.test(relu.lu), JSON.stringify(relu));
    await page.close();
    // Deux colonnes du même intitulé : la première compte, avec ou sans « toutes », et la page lit la même.
    const d = classeur();
    const ctxD = chargerServeur(d, {});
    const doubles = [['NAME', 'SOL.', 'Cust.V', 'NAME'], ['TFE311A0600', '001', 'A', 'Faisceau principal']];
    const lus = [];
    for (const toutes of [false, true]) {
      page = await fenetre(ctxD);
      await importer(page, 'dup.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: doubles }] }), { toutes });
      lus.push(ctxD.lireSecondeBase(d, 'HDK').rapprochement.lignes[0].NAME);
      await page.close();
    }
    verifier('un intitulé en double (NAME deux fois) : la première colonne, avec ou sans « toutes », comme la page la lit',
      lus.join('|') === 'TFE311A0600|TFE311A0600', lus.join('|'));
    /* La case cochée PENDANT la lecture d'un gros fichier : la ligne est en
       cours de lecture au moment du clic — le changement de la case ne la
       relit pas d'elle-même —, c'est la fin de sa lecture qui la relit. */
    page = await fenetre(ctx);
    await page.setInputFiles('#fichier', [{ name: 'gros.xlsx', mimeType: 'application/octet-stream', buffer: seeXlsx(50000) }]);
    const pendant = await page.evaluate(() => new Promise(ok => {
      const t0 = Date.now();
      (function voir() {
        const li = document.querySelector('#liste .fichier'), e = li && li.getAttribute('data-etat');
        if (e === 'lecture') { document.getElementById('toutes').click(); ok(true); return; }
        if ((e && e !== 'attente') || Date.now() - t0 > 30000) { ok(false); return; }
        setTimeout(voir, 2);
      })();
    }));
    await attendreLecture(page);
    const reLu = (await lignes(page))[0];
    const rT = { etat: await lancer(page) };
    const fT = c.getSheetByName('SEE HDK');
    verifier('la case cochée pendant la lecture : le fichier est relu avec elle, et les huit colonnes partent',
      pendant && reLu.etat === 'lu' && /colonnes SCHEMA NUMBER, NAME, SOL\., Cust\.V, Released Date/.test(reLu.lu) && /\bok\b/.test(rT.etat.classe) &&
      fT.valeurs[0].length === 8 && fT.valeurs.length === 50001, pendant + ' / ' + reLu.lu + ' / ' + rT.etat.texte + ' / ' + (fT && fT.valeurs[0].join('|')));
    await page.close();
  }

  // =================================================================
  section('Plusieurs onglets dans le fichier ; un seul contrat et un onglet « SEE »');
  {
    const ancien = new Feuille('SEE', [['NAME', 'SOL.', 'Cust.V'], ['OLD', '1', 'A']]);
    const c = classeur({ autres: [ancien] });
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const fichier = xlsx({ onglets: [{ nom: 'Lisez-moi', lignes: [['Export du 01/10'], ['Rien ici']] }, { nom: 'Masqué', cache: true, lignes: [['NAME', 'SOL.', 'Cust.V'], ['MASQUE', '9', 'Z']] },
      { nom: 'Données', lignes: lignesSEE(25) }] });
    const ui = (await ajouter(page, [{ nom: 'multi.xlsx', contenu: fichier }]))[0];
    verifier('un seul contrat : l’onglet « SEE » existant est la cible — le contrat « à vérifier », l’échantillon n’ayant rien en commun avec lui',
      ui.choix === 'HDK' && ui.verifier && ui.choixVisible && /Remplacera l’onglet « SEE »/.test(ui.cible), JSON.stringify(ui));
    const r = { etat: await lancer(page) };
    const f = c.getSheetByName('SEE');
    verifier('l’en-tête est cherché onglet par onglet, les visibles d’abord : « Données »',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 26 && f.valeurs[1][0] === 'TFE311A0600', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs[1]));
    const bord = [['NAME', 'SOL.', 'Cust.V']];
    const enLigne8 = xlsx({ onglets: [{ nom: 'S', lignes: [['t'], [], [], [], [], [], [], bord[0], ['TFE1', '1', 'A']] }] });
    const enLigne9 = xlsx({ onglets: [{ nom: 'S', lignes: [['t'], [], [], [], [], [], [], [], bord[0], ['TFE1', '1', 'A']] }] });
    const r8 = await importer(page, 'l8.xlsx', enLigne8), r9 = await importer(page, 'l9.xlsx', enLigne9);
    verifier('l’en-tête en ligne 8 est pris, en ligne 9 refusé — comme le Diagnostic et la page le cherchent — et la fenêtre dit où il est',
      /\bok\b/.test(r8.etat.classe) && /erreur/.test(r9.etat.classe) && /8 premières lignes/.test(r9.etat.texte) && /en ligne 9/.test(r9.etat.texte), r8.etat.texte + ' / ' + r9.etat.texte);
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
    verifier('ni GATES ni SEE (pas de NAME / SOL. / Cust.V) : la ligne du fichier le dit, nomme ce qui manque et la ligne la plus proche',
      /erreur/.test(r.etat.classe) && /Ni un export GATES ni un export SEE/.test(r.etat.texte) && /aucune ligne d’en-tête avec NAME, SOL\., Cust\.V/.test(r.etat.texte) &&
      /La ligne 2 de « S » en porte 1 sur 3 — il manque : NAME, Cust\.V/.test(r.etat.texte), r.etat.texte);
    verifier('et le classeur n’a pas bougé (aucun appel au serveur)', page.__appels.length === 0 && JSON.stringify(ancien.valeurs) === avant);
    const bloque = await fenetreEtat(page);
    verifier('« Importer » attend qu’on retire ce fichier, et le dit', bloque.desactive && /Retirer « autre\.xlsx », qui ne s’importe pas/.test(bloque.blocage) && bloque.retirerErreurs,
      JSON.stringify(bloque));
    r = await importer(page, 'entete.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V']] }] }));
    verifier('l’en-tête sans aucune ligne dessous : refusé, la base n’est pas vidée', /erreur/.test(r.etat.classe) && /aucune ligne dessous/.test(r.etat.texte) && page.__appels.length === 0, r.etat.texte);
    const ole = Buffer.concat([Buffer.from([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]), Buffer.alloc(600)]);
    r = await importer(page, 'vieux.xls', ole);
    verifier('un .xls dont le conteneur ne se lit pas (la signature OLE, puis des zéros) : « abîmé, le retélécharger », sans rien envoyer — plus jamais « ancien fichier, que la fenêtre ne sait pas lire »',
      /erreur/.test(r.etat.classe) && /abîmé/.test(r.etat.texte) && /retélécharger/.test(r.etat.texte) && !/ancien fichier|ne sait pas lire/.test(r.etat.texte) &&
      page.__appels.length === 0, r.etat.texte);
    r = await importer(page, 'Nommage WD BFLOW.xlsx', ole);
    verifier('les mêmes octets nommés .xlsx : un .xlsx qui est un conteneur OLE est un .xlsx protégé (mot de passe, étiquette) — dit protégé', /erreur/.test(r.etat.classe) && /protégé/.test(r.etat.texte) && !/abîmé/.test(r.etat.texte), r.etat.texte);
    /* Un vrai conteneur OLE : en-tête (secteurs de 512, répertoire au secteur 0), puis le répertoire. */
    const conteneur = (noms) => {
      const b = Buffer.alloc(512 * 3);
      Buffer.from([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]).copy(b, 0);
      b.writeUInt16LE(9, 0x1E); b.writeUInt32LE(0, 0x30);
      ['Root Entry'].concat(noms).forEach((n, k) => { const o = 512 + 128 * k; Buffer.from(n + '\0', 'utf16le').copy(b, o); b.writeUInt16LE((n.length + 1) * 2, o + 64); });
      return b;
    };
    r = await importer(page, 'export.xlsx', conteneur(['Workbook', '\u0005SummaryInformation']));
    verifier('un conteneur OLE qui nomme un flux « Workbook » vide, même nommé .xlsx : un classeur abîmé, pas « protégé »',
      /erreur/.test(r.etat.classe) && /abîmé/.test(r.etat.texte) && !/protégé/.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'Nommage WD BFLOW.xlsx', FX.xls({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE311A0600', '001', 'A']] }] }), { contrat: 'THS' });
    verifier('un vrai .xls nommé .xlsx (un export renommé) : lu comme un .xls', /\bok\b/.test(r.etat.classe) &&
      c.getSheetByName('SEE THS').valeurs.map(l => l.join('|')).join(' / ') === 'NAME|SOL.|Cust.V / TFE311A0600|001|A', r.etat.texte);
    r = await importer(page, 'chiffre.xls', conteneur(['\u0006DataSpaces', 'EncryptionInfo', 'EncryptedPackage']));
    verifier('un .xlsx chiffré, même nommé .xls : dit protégé', /erreur/.test(r.etat.classe) && /protégé/.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'tronque.xlsx', seeXlsx(20).subarray(0, 900));
    verifier('un .xlsx tronqué (téléchargement pas fini) : le retélécharger', /erreur/.test(r.etat.classe) && /retélécharger/.test(r.etat.texte), r.etat.texte);
    /* Un zip abîmé au milieu : des octets de la feuille brouillés. */
    const sain = seeXlsx(3000);
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
    page = await fenetre(ctx, rapide);
    const vrai = ctx.importSecondeBaseLot;
    let lots = 0;
    ctx.importSecondeBaseLot = function () { lots++; if (lots === 2) throw new Error('Service Spreadsheets timed out while accessing document'); return vrai.apply(null, arguments); };
    r = await importer(page, 'see.xlsx', seeXlsx(200), { contrat: 'HDK' });
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
    r = await importer(page, 'see.xlsx', seeXlsx(200), { contrat: 'HDK' });
    ctx.importSecondeBaseLot = vrai;
    await page.waitForTimeout(300);
    verifier('une panne qui dure : trois essais, puis le message la dit et dit quoi faire, « SEE HDK » est intact, l’onglet temporaire est retiré',
      /erreur/.test(r.etat.classe) && lots === 4 && /Service Spreadsheets indisponible/.test(r.etat.texte) && /Relancer l’import/.test(r.etat.texte) &&
      /Rien n’a été remplacé/.test(r.etat.texte) && JSON.stringify(c.getSheetByName('SEE HDK').valeurs) === avant && sansImport(c), r.etat.texte + ' / ' + lots + ' / ' + nomsOnglets(c).join(', '));
    /* Un refus du serveur n'est pas renvoyé. */
    page.__appels = [];
    ctx.importSecondeBaseLot = function () { throw new Error('L’onglet d’import « x » a disparu (un autre import de ce contrat a-t-il été lancé ?) : relancer l’import.'); };
    r = await importer(page, 'see.xlsx', seeXlsx(20), { contrat: 'HDK' });
    ctx.importSecondeBaseLot = vrai;
    verifier('un refus du serveur (« a disparu ») : pas renvoyé', /erreur/.test(r.etat.classe) && page.__appels.filter(n => n === 'importSecondeBaseLot').length === 1, page.__appels.join());
    /* Relancé : il passe, en lots de 50 lignes exactement. */
    page.__appels = [];
    const tailles = [];
    ctx.importSecondeBaseLot = function (j, f, p, l) { tailles.push(l.length); return vrai.apply(null, arguments); };
    r = await importer(page, 'see.xlsx', seeXlsx(200), { contrat: 'HDK' });
    ctx.importSecondeBaseLot = vrai;
    verifier('relancé : il passe, en lots de 50 lignes', /\bok\b/.test(r.etat.classe) && c.getSheetByName('SEE HDK').valeurs.length === 201 && tailles.join() === '50,50,50,50,1',
      r.etat.texte + ' / ' + tailles.join());
    await page.close();

    /* La fin a tout fait, puis la réponse se perd : la fenêtre ne dit pas « rien n'a été remplacé ». */
    page = await fenetre(ctx);
    const vraiFin = ctx.importSecondeBaseFin;
    ctx.importSecondeBaseFin = function () { vraiFin.apply(null, arguments); throw new Error('NetworkError: Connection failure due to HTTP 0'); };
    r = await importer(page, 'see.xlsx', seeXlsx(120), { contrat: 'HDK' });
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
    /* Une fin qui ne vise pas l'onglet de son début (une base SEE pour un onglet GATES) : refusée. */
    const g = ctx.importSecondeBaseDebut(jeton, { sorte: 'gates', contrat: 'HDK' }, 3, 2);
    ctx.importSecondeBaseLot(jeton, g.feuille, 1, [['a', 'b', 'c'], ['d', 'e', 'f']]);
    let melange = '';
    try { ctx.importSecondeBaseFin(jeton, g.feuille, 'HDK', 2); } catch (e) { melange = e.message; }
    ctx.importSecondeBaseAbandon(jeton, g.feuille);
    verifier('une fin qui ne vise pas l’onglet de son début (l’onglet temporaire de « HDK », fini comme base SEE) : refusée, rien n’est échangé',
      /n’est pas celui de « SEE HDK »/.test(melange) && c.getSheetByName('SEE HDK').valeurs.length === 121 && c.getSheetByName('HDK').valeurs.length === 43 && sansImport(c), melange);
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
    const texteDiag = ctx.diagnostic();
    verifier('un import interrompu : le Diagnostic nomme son onglet temporaire', /reste d'un import interrompu/.test(texteDiag) && texteDiag.indexOf(reste.feuille) !== -1,
      texteDiag.split('\n').filter(l => /import/.test(l)).join(' / '));
    page = await fenetre(ctx);
    r = await importer(page, 'see.xlsx', seeXlsx(5), { contrat: 'THS' });
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
    const r = await importer(page, 'see.xlsx', seeXlsx(9000));
    verifier('un classeur presque plein : refusé avant tout envoi, avec les nombres et quoi faire, rien de créé',
      /erreur/.test(r.etat.classe) && /limite de Google Sheets : 10 millions de cellules/.test(r.etat.texte) && /supprimer les onglets/.test(r.etat.texte) &&
      page.__appels.filter(x => x !== 'importDevinerContratSEE' && x !== 'importContrats').join() === 'importSecondeBaseDebut' && sansImport(c) && !c.getSheetByName('SEE HDK'), r.etat.texte);
    await page.close();
    /* L'onglet remplacé s'en ira : il ne compte pas dans le classeur d'après ; mais le temps de l'import, l'ancien et le nouveau coexistent. */
    const c2 = classeur({ autres: [new Feuille('Archives', [['x']])] });
    const ancienGates = c2.getSheetByName('HDK');
    ancienGates.lignesGrille = 20000;   // un ancien onglet collé, à la grille gonflée : 20 000 × 138
    const reste = 10000000 - c2.cellulesGrille();
    c2.getSheetByName('Archives').lignesGrille += Math.floor((reste - 4000) / 26);
    const ctx2 = serveur(c2);
    const jeton = jetonDe(ctx2);
    let coexiste = '';
    try { ctx2.importSecondeBaseDebut(jeton, { sorte: 'gates', contrat: 'HDK' }, 138, 189); } catch (e) { coexiste = e.message; }
    verifier('l’onglet remplacé ne compte pas dans le classeur d’après — mais le temps de l’import il coexiste avec le nouveau : la fenêtre le dit, avec les nombres',
      /limite de Google Sheets : 10 millions de cellules/.test(coexiste) && /coexistent/.test(coexiste) && /l’ancien onglet « HDK »/.test(coexiste) && sansImport(c2), coexiste);
  }

  // =================================================================
  section('Un gros export : 120 000 lignes × 24 colonnes, et des liens après les lignes');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const entete = ['SCHEMA NUMBER', 'NAME', 'SOL.', 'Cust.V'].concat(Array.from({ length: 20 }, (_, k) => 'Colonne ' + (k + 1)));
    const n = 120000;
    const tout = [['Nommage WD BFLOW'], [], entete];
    const attendu = i => 'TFE' + (311 + i % 90) + 'A' + String(i).padStart(6, '0') + '|' + String(1 + i % 4).padStart(3, '0') + '|' + ['A', 'B', 'C', 'D'][i % 4];
    for (let i = 0; i < n; i++) {
      const l = ['S-' + i].concat(attendu(i).split('|'));
      for (let k = 0; k < 20; k++) l.push(k % 3 ? 'valeur ' + ((i * 7 + k) % 5000) : { n: 45000 + (i % 900), fmt: 'date' });
      tout.push(l);
    }
    /* Ce que certains exports écrivent après les lignes : un lien par ligne. */
    const queue = '<hyperlinks>' + Array.from({ length: n }, (_, i) => '<hyperlink ref="B' + (i + 4) + '" r:id="rId' + (i + 10) + '"/>').join('') + '</hyperlinks>';
    const fichier = xlsx({ onglets: [{ nom: 'Export', lignes: tout, queue }] });
    const r = await importer(page, 'gros.xlsx', fichier, { delai: 300000 });
    const f = c.getSheetByName('SEE HDK');
    const echantillon = Array.from({ length: 12 }, (_, k) => k * 10000).concat([n - 1]).filter(i => f && f.valeurs[i + 1] && f.valeurs[i + 1].join('|') !== attendu(i));
    verifier('importé (' + (fichier.length / 1048576).toFixed(1) + ' Mo, ' + ((r.duree || 0) / 1000).toFixed(1) + ' s) : ' + n + ' lignes, NAME / SOL. / Cust.V alignés (une ligne sur 10 000 vérifiée)',
      /\bok\b/.test(r.etat.classe) && f && f.valeurs.length === n + 1 && !echantillon.length, r.etat.texte + ' ' + echantillon.join(','));
    verifier('en moins de deux minutes, malgré les liens après les lignes', r.duree < 120000, ((r.duree || 0) / 1000).toFixed(1) + ' s');
    await page.close();
  }

  // =================================================================
  section('Glisser les fichiers dans la fenêtre');
  {
    const c = classeur();
    const ctx = serveur(c);
    const page = await fenetre(ctx);
    const see = seeXlsx(7).toString('base64'), gat = xlsxGates(gates(40)).toString('base64');
    await page.evaluate(([s, g]) => {
      const fichier = (b, nom) => { const bin = atob(b), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new File([u], nom); };
      const dt = new DataTransfer();
      dt.items.add(fichier(s, 'glisse.xlsx'));
      dt.items.add(fichier(g, 'export_48.xlsx'));
      document.getElementById('depot').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    }, [see, gat]);
    await attendreLecture(page);
    const lus = await lignes(page);
    const etat = await lancer(page);
    verifier('des fichiers glissés sont pris comme des fichiers choisis — les deux, chacun dans son onglet',
      lus.length === 2 && lus[0].sorte === 'SEE' && lus[1].sorte === 'GATES' && /\bok\b/.test(etat.classe) && c.getSheetByName('SEE HDK').valeurs.length === 8 &&
      c.getSheetByName('HDK').valeurs.length === 43, JSON.stringify(lus.map(l => l.sorte + ' ' + l.lu)) + ' / ' + etat.texte);
    await page.close();
  }

  // =================================================================
  section('Reconnaître un export GATES ou SEE, chacun sur sa ligne');
  {
    const c = classeur({ ths: true });
    const ctx = serveur(c);
    const P = parametres(ctx);
    verifier('la fenêtre reçoit les règles du serveur, pas une copie : les mots d’une ligne d’en-têtes d’export, ses deux nombres, les motifs de la colonne de référence',
      JSON.stringify(P.motsCles) === JSON.stringify(vm.runInContext('CONFIG.MOTS_CLES_ENTETE', ctx).map(ctx.normaliser)) && P.minIntitules === 10 && P.minMotsCles === 2 &&
      JSON.stringify(P.motifsReference) === JSON.stringify(vm.runInContext('MOTIFS_REFERENCE', ctx)) && P.lignesScan === 8,
      JSON.stringify([P.motsCles, P.minIntitules, P.minMotsCles, P.motifsReference]));
    verifier('et, pour chaque contrat, les références de ses plans, normalisées', P.contrats.map(k => k.id + ':' + k.refs.length).join() === 'HDK:40,THS:30' &&
      P.contrats[1].refs[0] === ctx.normaliser(c.getSheetByName('THS').valeurs[3][I_REF]), JSON.stringify(P.contrats.map(k => [k.id, k.refs.slice(0, 2)])));
    const page = await fenetre(ctx);
    const lus = await ajouter(page, [
      { nom: 'export_48.xlsx', contenu: xlsxGates(gates(40)) },
      { nom: 'Nommage WD BFLOW.xlsx', contenu: seeXlsx(12) },
      { nom: 'notes.xlsx', contenu: xlsx({ onglets: [{ nom: 'Notes', lignes: [['Réunion du 3'], ['rien à voir']] }] }) },
      { nom: 'photo.png', contenu: Buffer.from('png') }]);
    const ui = await fenetreEtat(page);
    verifier('chaque fichier est lu tout de suite et dit ce qu’il est : GATES (plans, colonnes, ligne d’en-têtes, cellules fusionnées), SEE (lignes, colonnes), ni l’un ni l’autre (pourquoi)',
      lus.length === 3 && lus[0].sorte === 'GATES' && /^40 plans · 138 colonnes · en-têtes en ligne 2 · 16 cellules fusionnées · lu en \d+ s$/.test(lus[0].lu) &&
      lus[1].sorte === 'SEE' && /^12 lignes, colonnes NAME, SOL\., Cust\.V/.test(lus[1].lu) && lus[2].etat === 'erreur' && /Ni un export GATES ni un export SEE/.test(lus[2].lu),
      JSON.stringify(lus));
    verifier('ce qui n’est pas un tableau (une photo) est laissé de côté, et la fenêtre le dit', /photo\.png/.test(ui.etat) && /pas des tableaux/.test(ui.etat), ui.etat);
    verifier('« Importer » attend qu’on retire le fichier qui ne s’importe pas, et le dit', ui.desactive && /Retirer « notes\.xlsx », qui ne s’importe pas/.test(ui.blocage), JSON.stringify(ui));
    verifier('la case « Archiver le relevé de la semaine Sxx pour les contrats importés » paraît avec un export GATES, cochée',
      ui.archiverVisible && ui.archiverCoche && new RegExp('Archiver le relevé de la semaine S' + parseInt(semaineDe(ctx).slice(6), 10) + ' pour les contrats importés').test(ui.archiverTexte), JSON.stringify(ui));
    await page.click('#retirer-erreurs');
    const apres = await fenetreEtat(page);
    verifier('« Retirer les fichiers en erreur » : il reste les deux exports, « Importer » s’allume', !apres.desactive && apres.n === 2 && !apres.retirerErreurs, JSON.stringify(apres));
    await page.close();
  }

  // =================================================================
  section('Un export GATES importé se lit comme un export collé');
  {
    const g = feuilleGates(186);
    const colle = new Classeur([new Feuille('HDK', g.valeurs.map(l => l.slice()), false, g.fusions.map(f => Object.assign({}, f)))]);
    const ctxColle = serveur(colle);
    const importe = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE HDK', [['NAME', 'SOL.', 'Cust.V'], ['X', '001', 'A']])]);
    const ctx = serveur(importe);
    ctx.archiverContrat_(importe, { id: 'HDK', nom: 'HDK' }, semaineDe(ctx, 7));
    const histoAvant = JSON.stringify(importe.getSheetByName('Historique_FWD_HDK').valeurs);
    const place = nomsOnglets(importe).indexOf('HDK');
    const page = await fenetre(ctx);
    const r = await importer(page, 'export_48.xlsx', xlsxGates(g), { sansArchiver: true });
    const f = importe.getSheetByName('HDK');
    verifier('l’export est rattaché à « HDK » et importé ; la fenêtre dit ce que la page y lit : plans, colonne suivie (groupe › intitulé), concept harnais',
      r.ligne.choix === 'HDK' && /\bok\b/.test(r.etat.classe) &&
      /✓ « export_48\.xlsx » → onglet « HDK » remplacé : 186 plans, colonne suivie HDK AA 011 › Avancement Définition Electrique, concept harnais lu\./.test(r.etat.texte), r.etat.texte);
    let ecart = '';
    for (let i = 0; i < Math.max(f.valeurs.length, g.valeurs.length) && !ecart; i++) {
      if (JSON.stringify(f.valeurs[i]) !== JSON.stringify(g.valeurs[i])) ecart = 'ligne ' + (i + 1) + ' : ' + JSON.stringify(f.valeurs[i]).slice(0, 200) + ' au lieu de ' + JSON.stringify(g.valeurs[i]).slice(0, 200);
    }
    verifier('l’onglet porte exactement ce qu’un collage y poserait : chaque ligne à son numéro, chaque colonne à sa place — groupes, en-têtes, ligne de service, dates jj/mm/aaaa, ATA lue en nombre',
      !ecart && f.valeurs.length === g.valeurs.length, ecart || f.valeurs.length + ' lignes');
    verifier('les seize cellules fusionnées de la ligne des groupes sont recréées, aux mêmes places',
      JSON.stringify(f.fusions.map(x => [x.ligne, x.col, x.larg, x.haut || 1])) === JSON.stringify(g.fusions.map(x => [x.ligne, x.col, x.larg, 1])), JSON.stringify(f.fusions));
    verifier('chaque cellule est posée en texte (« @ ») : rien ne devient formule ni nombre', Object.keys(f.formats).length === g.valeurs.length && Object.keys(f.formats).every(k => f.formats[k] === '@'),
      Object.keys(f.formats).length + ' lignes');
    const sansDate = function (o) { const x = JSON.parse(JSON.stringify(o)); delete x.genereLe; delete x.releves; delete x.avis; delete x.rapprochement; return JSON.stringify(x); };
    verifier('construireModele lit l’onglet importé comme l’onglet collé : mêmes colonnes, mêmes groupes, même colonne suivie, mêmes plans',
      JSON.stringify(ctx.construireModele('HDK')) === JSON.stringify(ctxColle.construireModele('HDK')));
    verifier('getDonneesPourClient : le même paquet pour la page', sansDate(ctx.getDonneesPourClient('HDK')) === sansDate(ctxColle.getDonneesPourClient('HDK')));
    verifier('compterAvancements : le même relevé, plan par plan', JSON.stringify(ctx.compterAvancements('HDK')) === JSON.stringify(ctxColle.compterAvancements('HDK')));
    verifier('l’onglet garde sa place et son nom ; aucun onglet temporaire ni « ancien » ne traîne ; la base SEE n’est pas touchée',
      nomsOnglets(importe).indexOf('HDK') === place && sansImport(importe) && importe.getSheetByName('SEE HDK').valeurs[1][0] === 'X', nomsOnglets(importe).join(', '));
    verifier('l’historique, rangé sous le nom de l’onglet, est intact (case « Archiver » décochée) et se lit toujours',
      JSON.stringify(importe.getSheetByName('Historique_FWD_HDK').valeurs) === histoAvant && ctx.getHistorique(importe, 'HDK').length === 1);
    verifier('la fenêtre n’a appelé que le début, les lots et la fin — rien à deviner côté serveur, pas d’archivage',
      page.__appels[0] === 'importSecondeBaseDebut' && page.__appels.slice(-2).join() === 'importSecondeBaseFin,importContrats' && page.__appels.indexOf('importArchiverReleve') === -1 &&
      page.__cibles[0] === JSON.stringify({ sorte: 'gates', contrat: 'HDK', nouveau: false }), page.__appels.join() + ' ' + page.__cibles.join());
    await page.close();
  }

  // =================================================================
  section('Les cellules fusionnées, d’où qu’elles viennent : page web, XML 2003');
  {
    const g = gates(30);
    const c = new Classeur([ongletGates('HDK', gates(20))]);
    const ctx = serveur(c);
    const page = await fenetre(ctx);
    let r = await importer(page, 'export.xls', Buffer.from(htmlGates(g, 'Export GATES du 01/10/2026'), 'utf8'), { sansArchiver: true });
    let f = c.getSheetByName('HDK');
    const titre = ['Export GATES du 01/10/2026'].concat(new Array(137).fill(''));
    verifier('une page web nommée .xls — un titre au-dessus (colspan, sur les 138 colonnes), les groupes (colspan), une cellule sur deux lignes (rowspan) : les lignes à leur place, les dix-huit fusions recréées, le titre sur toute la largeur, la colonne suivie trouvée',
      /\bok\b/.test(r.etat.classe) && JSON.stringify(f.valeurs) === JSON.stringify([titre].concat(g.valeurs)) && f.fusions.length === 18 &&
      f.fusions.some(x => x.ligne === 2 && x.col === 1 && x.haut === 2) && f.fusions.some(x => x.ligne === 1 && x.col === 1 && x.larg === 138 && x.haut === 1) &&
      /colonne suivie HDK AA 011 › Avancement Définition Electrique/.test(r.etat.texte),
      r.etat.texte + ' ' + f.fusions.length + ' ' + JSON.stringify(f.valeurs[2] && f.valeurs[2].slice(0, 4)));
    r = await importer(page, 'export2.xls', Buffer.from(xml2003Gates(g), 'utf8'), { sansArchiver: true });
    f = c.getSheetByName('HDK');
    verifier('un XML 2003 nommé .xls (ss:MergeAcross, ss:Index) : les seize fusions recréées, les lignes à leur place, la colonne suivie trouvée',
      /\bok\b/.test(r.etat.classe) && f.fusions.length === 16 && JSON.stringify(f.valeurs) === JSON.stringify(g.valeurs) && /colonne suivie HDK AA 011/.test(r.etat.texte), r.etat.texte);
    /* Des milliers de fusions dans les plans, écrites AVANT celles de la ligne des groupes. */
    const bruit = Array.from({ length: 6000 }, (_, i) => ({ ligne: 4 + Math.floor(i / 60), col: 1 + (i % 60) * 2, larg: 2 }));
    r = await importer(page, 'export3.xlsx', xlsx({ onglets: [{ nom: 'Export', lignes: g.valeurs.map(l => l.slice()),
      fusions: bruit.concat(g.fusions.map(x => ({ ligne: x.ligne, col: x.col, larg: x.larg }))) }] }), { sansArchiver: true });
    f = c.getSheetByName('HDK');
    verifier('six mille fusions dans les plans, écrites avant celles de la ligne des groupes : les seize de la ligne des groupes sont recréées, aucune autre',
      /\bok\b/.test(r.etat.classe) && f.fusions.length === 16 && f.fusions.every(x => x.ligne === 1) && JSON.stringify(f.valeurs) === JSON.stringify(g.valeurs),
      r.etat.texte + ' / ' + f.fusions.length);
    await page.close();
  }

  // =================================================================
  section('Un vrai .xls d’export GATES : le même onglet que le même export en .xlsx');
  {
    const source = FX.SOURCES.gates();
    verifier('la source des .xls GATES de tests/xls est l’export GATES des autres essais (la vraie structure, 186 plans), octet pour octet',
      source.equals(xlsxGates(feuilleGates(186))));
    const lus = {};
    for (const [nom, contenu] of [['export_48.xlsx', source], ['export_48.xls', lireXls('lo-gates.xls')], ['export_xlwt.xls', lireXls('xlwt-gates.xls')]]) {
      const c = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE HDK', [['NAME', 'SOL.', 'Cust.V'], ['X', '001', 'A']])]);
      const ctx = serveur(c);
      const page = await fenetre(ctx);
      const r = await importer(page, nom, contenu, { sansArchiver: true });
      lus[nom] = { r, f: c.getSheetByName('HDK'), ctx, appels: page.__appels.slice() };
      await page.close();
    }
    const x = lus['export_48.xlsx'], l = lus['export_48.xls'], w = lus['export_xlwt.xls'];
    verifier('le .xls écrit par LibreOffice est lu, rattaché à « HDK », et sa ligne dit ce qu’elle dit du .xlsx : 186 plans · 138 colonnes · en-têtes en ligne 2 · 16 cellules fusionnées',
      l.r.ligne.choix === 'HDK' && /^186 plans · 138 colonnes · en-têtes en ligne 2 · 16 cellules fusionnées · lu en \d+ s$/.test(l.r.ligne.lu) &&
      l.r.ligne.lu.replace(/lu en \d+ s/, '') === x.r.ligne.lu.replace(/lu en \d+ s/, ''), JSON.stringify([l.r.ligne.lu, x.r.ligne.lu]));
    verifier('l’onglet importé du .xls porte exactement les valeurs de l’onglet importé du .xlsx — chaque ligne à son numéro, chaque colonne à sa place, dates jj/mm/aaaa, ATA lue en nombre',
      /\bok\b/.test(l.r.etat.classe) && !premierEcart(l.f.valeurs, x.f.valeurs) && l.f.valeurs.length === 189 && JSON.stringify(l.f.valeurs) === JSON.stringify(x.f.valeurs),
      premierEcart(l.f.valeurs, x.f.valeurs) || l.r.etat.texte);
    verifier('… et les mêmes seize cellules fusionnées, aux mêmes places', JSON.stringify(fusionsDe(l.f)) === JSON.stringify(fusionsDe(x.f)) && l.f.fusions.length === 16,
      JSON.stringify(fusionsDe(l.f)));
    verifier('construireModele, getDonneesPourClient et compterAvancements lisent l’onglet du .xls exactement comme celui du .xlsx',
      JSON.stringify(l.ctx.construireModele('HDK')) === JSON.stringify(x.ctx.construireModele('HDK')) &&
      paquetSansDate(l.ctx.getDonneesPourClient('HDK')) === paquetSansDate(x.ctx.getDonneesPourClient('HDK')) &&
      JSON.stringify(l.ctx.compterAvancements('HDK')) === JSON.stringify(x.ctx.compterAvancements('HDK')));
    verifier('la fenêtre dit ce que la page y lit, comme pour le .xlsx : 186 plans, colonne suivie HDK AA 011 › Avancement Définition Electrique, concept harnais lu',
      /« export_48\.xls » → onglet « HDK » remplacé : 186 plans, colonne suivie HDK AA 011 › Avancement Définition Electrique, concept harnais lu\./.test(l.r.etat.texte), l.r.etat.texte);
    verifier('le .xls écrit par xlwt (un autre programme, son propre conteneur) : les mêmes valeurs, les mêmes seize fusions',
      /\bok\b/.test(w.r.etat.classe) && !premierEcart(w.f.valeurs, x.f.valeurs) && JSON.stringify(fusionsDe(w.f)) === JSON.stringify(fusionsDe(x.f)),
      premierEcart(w.f.valeurs, x.f.valeurs) || w.r.etat.texte);
    verifier('rien de plus n’est demandé au serveur que pour le .xlsx : le début, les lots, la fin, la liste des contrats relue', JSON.stringify(l.appels) === JSON.stringify(x.appels),
      l.appels.join() + ' / ' + x.appels.join());
  }

  // =================================================================
  section('Un vrai .xls d’export SEE : les mêmes lignes que le .xlsx');
  {
    const types = typesEnregistrements(lireXls('lo-see.xls'));
    const iSst = types.indexOf(0x00FC);
    let suites = 0;
    while (types[iSst + 1 + suites] === 0x003C) suites++;
    verifier('le .xls SEE de LibreOffice exerce ce qu’exerce un vrai export : sa table de textes partagés court sur ' + suites +
      ' enregistrements CONTINUE (des chaînes coupées en route), des MULRK, des booléens écrits en formules', suites >= 10 && types.indexOf(0x00BD) !== -1 &&
      types.indexOf(0x0006) !== -1 && types.indexOf(0x00FD) !== -1, suites + ' CONTINUE');
    for (const toutes of [false, true]) {
      const lus = {};
      for (const [nom, contenu] of [['Nommage WD BFLOW.xlsx', FX.SOURCES.see()], ['Nommage WD BFLOW.xls', lireXls('lo-see.xls')]]) {
        const c = classeur();
        const page = await fenetre(chargerServeur(c, {}));
        const r = await importer(page, nom, contenu, { toutes });
        lus[nom] = { r, f: c.getSheetByName('SEE HDK') };
        await page.close();
      }
      const x = lus['Nommage WD BFLOW.xlsx'], l = lus['Nommage WD BFLOW.xls'];
      verifier((toutes ? '« Garder aussi les autres colonnes » : les huit colonnes' : 'NAME, SOL. et Cust.V seules') + ' — « SEE HDK » porte, du .xls, les mêmes 3 200 lignes que du .xlsx' +
        (toutes ? ' (codes à zéros de tête, dates jj/mm/aaaa, VRAI / FAUX, tiret long et accents)' : ''),
        /\bok\b/.test(l.r.etat.classe) && l.f.valeurs.length === 3201 && !premierEcart(l.f.valeurs, x.f.valeurs) && l.f.valeurs[0].length === (toutes ? 8 : 3) &&
        (!toutes || l.f.valeurs[1].join('|') === 'S-0|TFE311A0600|001|A|15/03/2023||VRAI|non — été 0'),
        premierEcart(l.f.valeurs, x.f.valeurs) || l.r.etat.texte + ' ' + JSON.stringify(l.f && l.f.valeurs[1]));
      if (!toutes) {
        verifier('la ligne du .xls dit la même chose que celle du .xlsx : 3 200 lignes, colonnes NAME, SOL., Cust.V', /^3\u202f200 lignes, colonnes NAME, SOL\., Cust\.V/.test(l.r.ligne.lu) &&
          l.r.ligne.lu.replace(/lu en \d+ s/, '') === x.r.ligne.lu.replace(/lu en \d+ s/, ''), l.r.ligne.lu);
      }
    }
  }

  // =================================================================
  section('L’oracle : chaque vrai .xls lu par la fenêtre comme par SheetJS');
  {
    /* SheetJS (0.18.5, hors du dépôt) a lu chacun de ces fichiers une fois pour toutes (tests/preparer-xls.js).
       Trois différences voulues, les mêmes que pour un .xlsx : VRAI / FAUX, toute date jj/mm/aaaa, la virgule décimale. */
    verifier('l’oracle est la lecture de SheetJS 0.18.5, pour les huit fichiers lisibles de tests/xls', ORACLE.sheetjs === '0.18.5' && Object.keys(ORACLE.fichiers).length === 8,
      ORACLE.sheetjs + ' ' + Object.keys(ORACLE.fichiers).join(', '));
    const cas = [
      { fichier: 'lo-gates.xls', onglet: 'Export', gates: true, qui: 'LibreOffice, l’export GATES' },
      { fichier: 'xlwt-gates.xls', onglet: 'Export', gates: true, qui: 'xlwt, l’export GATES' },
      { fichier: 'lo-see.xls', onglet: 'Nommage', qui: 'LibreOffice, 3 200 lignes SEE' },
      { fichier: 'lo-deux-onglets.xls', onglet: 'Données', qui: 'LibreOffice, deux onglets, l’en-tête dans le second' },
      { fichier: 'lo-onglet-cache.xls', onglet: 'Export', qui: 'LibreOffice, un premier onglet masqué qui porte lui aussi un en-tête : le visible passe d’abord' },
      { fichier: 'sheetjs-see.xls', onglet: 'Nommage', qui: 'SheetJS, BIFF8 en cellules LABEL' },
      { fichier: 'sheetjs-see-95.xls', onglet: 'Nommage', qui: 'SheetJS, Excel 95 (BIFF5, textes en Windows-1252)' },
      { fichier: 'xlwt-see.xls', onglet: 'Nommage', qui: 'xlwt, un export SEE' }
    ];
    for (const k of cas) {
      const lu = ORACLE.fichiers[k.fichier].filter(o => o.nom === k.onglet)[0];
      const c = classeur();
      const page = await fenetre(serveur(c));
      const r = await importer(page, k.fichier, lireXls(k.fichier), k.gates ? { sansArchiver: true } : { toutes: true });
      await page.close();
      const f = c.getSheetByName(k.gates ? 'HDK' : 'SEE HDK');
      const attendu = k.gates ? lu.lignes : seeAttendu(lu.lignes);
      const cellules = rogne(attendu).reduce((s, x) => s + x.length, 0);
      const ecart = f ? premierEcart(f.valeurs, attendu) : 'onglet absent';
      const fusionsOk = !k.gates || JSON.stringify(fusionsDe(f)) === JSON.stringify(lu.fusions.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]));
      verifier(k.fichier + ' (' + k.qui + ') : ' + cellules + ' cellules, chacune comme SheetJS la lit' + (k.gates ? ', et ses ' + lu.fusions.length + ' cellules fusionnées' : ''),
        /\bok\b/.test(r.etat.classe) && !ecart && fusionsOk, ecart || (fusionsOk ? r.etat.texte : JSON.stringify(fusionsDe(f))));
    }
  }

  // =================================================================
  section('Chaque façon d’écrire un .xls (fabriqué octet par octet)');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const voir = () => c.getSheetByName('SEE HDK') ? c.getSheetByName('SEE HDK').valeurs : [];
    /* Une ligne par façon d'écrire une cellule ; dessous, ce que la fenêtre doit en lire. */
    const lignesX = [
      ['Nommage WD BFLOW'], [],
      ['NAME', 'SOL.', 'Cust.V', 'Texte', 'Nombre', 'RK', 'Formule', 'Booléen'],
      ['TFE311A0600', '001', 'A', { riche: 'Riche et accentué é', runs: 2, phonetique: 'ふりがな' }, { n: 45000, fmt: 'jour' }, { rk: 42, mode: 'entier' }, { f: 3.25 }, { b: true }],
      ['TFE312A0601', '002', 'B', { label: 'Label — long' }, 3.5, { rk: 1.23, mode: 'entier100' }, { f: 'texte de formule assez long pour être coupé' }, { b: false }],
      ['TFE313A0602', '003', 'C', { rstring: 'Riche RSTRING' }, { n: 0.25, fmt: 'pct' }, { rk: 3.5, mode: 'reel' }, { f: true }, { err: 0x2A }],
      ['TFE314A0603', '004', 'D', 'chaîne partagée Ω grecque', { n: 1234567, fmt: 'mille' }, { rk: 12.34, mode: 'reel100' }, { f: { err: 7 } }, { blanc: true }],
      ['TFE315A0604', { mulrk: [{ rk: 5 }, { rk: 6, mode: 'entier100' }, { rk: -2.5, mode: 'reel' }] }, , , 'fin', { mulblank: 3 }],
      ['TFE316A0605', '006', 'E', { riche: 'encore un texte riche, plus long que les autres, pour que les coupures tombent partout', runs: 5, phonetique: 'よみがな と ふりがな' },
        { n: -7.125 }, { rk: -123456, mode: 'entier' }, { f: '' }, { f: false }],
      ['TFE317A0606', '007', 'F', 'Ωmega en tête, puis du latin : coupure possible en largeur double', { n: 1e21 }, { rk: 0.5, mode: 'reel' }, { f: 'é' }, { b: true }]
    ];
    const attenduX = [
      ['NAME', 'SOL.', 'Cust.V', 'Texte', 'Nombre', 'RK', 'Formule', 'Booléen'],
      ['TFE311A0600', '001', 'A', 'Riche et accentué é', '15/03/2023', '42', '3,25', 'VRAI'],
      ['TFE312A0601', '002', 'B', 'Label — long', '3,5', '1,23', 'texte de formule assez long pour être coupé', 'FAUX'],
      ['TFE313A0602', '003', 'C', 'Riche RSTRING', '25\u202f%', '3,5', 'VRAI', '#N/A'],
      ['TFE314A0603', '004', 'D', 'chaîne partagée Ω grecque', '1\u202f234\u202f567', '12,34', '#DIV/0!', ''],
      ['TFE315A0604', '5', '6', '-2,5', 'fin', '', '', ''],
      ['TFE316A0605', '006', 'E', 'encore un texte riche, plus long que les autres, pour que les coupures tombent partout', '-7,125', '-123456', '', 'FAUX'],
      ['TFE317A0606', '007', 'F', 'Ωmega en tête, puis du latin : coupure possible en largeur double', '1E+21', '0,5', 'é', 'VRAI']
    ];
    const variantes = [
      ['secteurs de 512 octets, enregistrements pleins (comme Excel) : textes partagés riches et phonétiques, LABEL, RSTRING, NUMBER, les quatre formes de RK, MULRK, ' +
        'BOOLERR (booléens et erreurs), formules (nombre, texte et son STRING, booléen, erreur, texte vide), BLANK, MULBLANK, formats', {}, {}],
      ['secteurs de 4 096 octets mélangés dans le fichier ; textes partagés coupés tous les 40 octets — en plein caractère (l’octet d’options repris, la largeur qui ' +
        'change en route), en pleine mise en forme, en pleine phonétique — et résultat de formule coupé tous les 12 octets', { sst: { max: 40, bascule: true }, maxString: 12 },
        { secteur: 4096, melange: true }],
      ['… et des en-têtes de chaîne coupés entre deux enregistrements, ce qu’Excel ne fait pas', { sst: { max: 23, entetesCoupes: true } }, {}],
      ['les lignes écrites à l’envers (un programme qui ne les range pas) : rangées avant de partir', { desordre: true }, {}]
    ];
    for (const [nom, opts, ole] of variantes) {
      const spec = { sst: opts.sst, onglets: [{ nom: 'Données', lignes: lignesX, maxString: opts.maxString, desordre: opts.desordre }] };
      const r = await importer(page, 'fabrique.xls', FX.xls(spec, ole), { toutes: true });
      verifier(nom, /\bok\b/.test(r.etat.classe) && !premierEcart(voir(), attenduX), premierEcart(voir(), attenduX) || r.etat.texte);
    }
    /* Un petit classeur : sous 4 096 octets, le flux loge dans le mini-flux. */
    const petit = { onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE311A0600', '001', 'A'], ['TFE312A0601', { rk: 2 }, 'B']] }] };
    let r = await importer(page, 'petit.xls', FX.xls(petit, { nomRacine: 'R' }), { toutes: true });
    verifier('un petit classeur (' + FX.classeurBiff(petit).length + ' octets), rangé dans le mini-flux par blocs de 64 octets, la racine nommée « R » comme l’écrit SheetJS',
      FX.classeurBiff(petit).length < 4096 && /\bok\b/.test(r.etat.classe) && voir().map(l => l.join('|')).join(' / ') === 'NAME|SOL.|Cust.V / TFE311A0600|001|A / TFE312A0601|2|B',
      r.etat.texte + ' ' + JSON.stringify(voir()));
    /* Plus de 109 secteurs de FAT : la DIFAT déborde de l'en-tête dans des secteurs chaînés. */
    const gros = FX.ole([{ nom: 'Remplissage', donnees: Buffer.alloc(7600000, 0x20) }, { nom: 'Workbook', donnees: FX.classeurBiff(petit) }]);
    r = await importer(page, 'difat.xls', gros, { toutes: true });
    verifier('un conteneur de ' + (gros.length / 1048576).toFixed(1) + ' Mo : ' + gros.readUInt32LE(0x2C) + ' secteurs de FAT, dont ' + (gros.readUInt32LE(0x2C) - 109) +
      ' listés hors de l’en-tête (' + gros.readUInt32LE(0x48) + ' secteur(s) de DIFAT), le classeur rangé après eux : lu',
      gros.readUInt32LE(0x48) >= 1 && /\bok\b/.test(r.etat.classe) && voir().length === 3, r.etat.texte);
    /* Le calendrier 1904 (les classeurs venus d'un Mac). */
    r = await importer(page, '1904.xls', FX.xls({ date1904: true, onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V', 'Date'], ['TFE1', '001', 'A', { n: 45000, fmt: 'jour' }]] }] }), { toutes: true });
    verifier('calendrier 1904 : 45000 se lit 16/03/2027, comme dans un .xlsx', /\bok\b/.test(r.etat.classe) && voir()[1][3] === '16/03/2027', JSON.stringify(voir()));
    /* Les formats : ceux d'Excel, ceux du fichier, et un « General » au nom local. */
    r = await importer(page, 'formats.xls', FX.xls({ onglets: [{ nom: 'S', lignes: [
      ['NAME', 'SOL.', 'Cust.V', 'Standard', 'Texte', 'Zéros', 'Pour cent', 'Milliers', 'Euro', 'Date FR', 'Mois/jour', 'Date et heure', 'Heure', 'Scientifique', 'Décimales'],
      ['TFE1', '001', 'A', { n: 45000, fmt: 'standard' }, { n: 42.5, fmt: 'texte' }, { n: 7, fmt: 'zeros3' }, { n: 0.1234, fmt: 'pct2' }, { n: 1234567, fmt: 'mille' },
        { n: 1234.5, fmt: 'euro' }, { n: 45000, fmt: 'jourFr' }, { n: 45000, fmt: 'moisjour' }, { n: 45000.5, fmt: 'jourheure' }, { n: 0.75, fmt: 'heure' },
        { n: 12345, fmt: 'sci' }, { n: 3, fmt: '0.00' }]] }] }), { toutes: true });
    verifier('les nombres comme Excel les affiche, avec les mêmes règles que pour un .xlsx : un « Standard » (le nom local de « General ») n’est pas pris pour une date, ' +
      '42.5 au format texte tel quel, 007, 12,34 %, 1 234 567, 1 234,50 €, [$-40C]jj/mm/aaaa, m/j/aaaa écrit jj/mm/aaaa, date et heure, heure, 1,23E+04, 3,00',
      /\bok\b/.test(r.etat.classe) && voir()[1].slice(3).join('|') === '45000|42.5|007|12,34\u202f%|1\u202f234\u202f567|1\u202f234,50 €|15/03/2023|15/03/2023|15/03/2023 12:00|18:00|1,23E+04|3,00',
      JSON.stringify(voir()[1]));
    /* Les onglets : un graphique, des macros, un très masqué qui porte un en-tête, puis l'onglet des données avec un graphique posé dessus. */
    r = await importer(page, 'onglets.xls', FX.xls({ onglets: [{ nom: 'Graphique', type: 'graphique' }, { nom: 'Macros', type: 'macro' },
      { nom: 'Caché', cache: 'tres', lignes: [['NAME', 'SOL.', 'Cust.V'], ['CACHE', '009', 'Z']] },
      { nom: 'Données', graphiqueDedans: true, lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE1', '001', 'A'], ['TFE2', '002', 'B']] }] }), { toutes: true });
    verifier('un onglet graphique, un onglet de macros, un onglet très masqué : écartés ; dans l’onglet des données, le graphique posé dessus (ses valeurs en cache, faites comme des cellules) est sauté',
      /\bok\b/.test(r.etat.classe) && voir().map(l => l.join('|')).join(' / ') === 'NAME|SOL.|Cust.V / TFE1|001|A / TFE2|002|B', JSON.stringify(voir()));
    r = await importer(page, 'rien.xls', FX.xls({ onglets: [{ nom: 'Graphique', type: 'graphique' }, { nom: 'Lisez-moi', lignes: [['Export du 01/10'], ['Rien ici']] },
      { nom: 'Notes', lignes: [['REF', 'SOL.', 'Cust V'], ['X', '1', 'A']] }] }));
    verifier('aucun onglet ne porte d’en-tête : « Ni un export GATES ni un export SEE », les onglets nommés (pas le graphique), la ligne la plus proche citée',
      /erreur/.test(r.etat.classe) && /des onglets \(Lisez-moi, Notes\)/.test(r.etat.texte) && /La ligne 1 de « Notes » en porte 1 sur 3/.test(r.etat.texte), r.etat.texte);
    /* Excel 5 / 95 : des octets dans la page de codes du classeur. */
    r = await importer(page, 'excel95.xls', FX.xls({ biff: 5, page: 850, onglets: [{ nom: 'Données', lignes: [['NAME', 'SOL.', 'Cust.V', 'Libellé'],
      ['TFE1', '001', 'A', 'Câble été à Élancourt'], ['TFE2', { rstring: 'RSTRING ç' }, 'B', { f: 'formule où' }], ['TFE3', { rk: 3 }, 'C', { n: 45000, fmt: 'jour' }]] }] }), { toutes: true });
    verifier('un .xls d’Excel 95 (BIFF5, flux « Book ») en page de codes 850 du DOS : LABEL, RSTRING, formule et son STRING, accents justes, date et nombre',
      /\bok\b/.test(r.etat.classe) && voir().map(l => l.join('|')).join(' / ') === 'NAME|SOL.|Cust.V|Libellé / TFE1|001|A|Câble été à Élancourt / TFE2|RSTRING ç|B|formule où / TFE3|3|C|15/03/2023',
      JSON.stringify(voir()));
    r = await importer(page, 'excel95.xls', FX.xls({ biff: 5, onglets: [{ nom: 'Données', lignes: [['NAME', 'SOL.', 'Cust.V', 'Libellé'], ['TFE1', '001', 'A', 'Prix 12 € — œuvre « été »']] }] }), { toutes: true });
    verifier('… et en Windows-1252 (la page de codes d’Excel 95 sous Windows) : €, tiret long, œ, guillemets', /\bok\b/.test(r.etat.classe) && voir()[1][3] === 'Prix 12 € — œuvre « été »',
      JSON.stringify(voir()));
    /* Un flux BIFF sans conteneur OLE. */
    r = await importer(page, 'nu.xls', FX.classeurBiff({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE1', '001', 'A']] }] }), { toutes: true });
    verifier('un flux BIFF8 sans conteneur OLE (certains vieux outils) : lu', /\bok\b/.test(r.etat.classe) && voir().map(l => l.join('|')).join(' / ') === 'NAME|SOL.|Cust.V / TFE1|001|A', r.etat.texte);
    /* Une formule qui dit « texte » sans le texte : un programme qui ne calcule pas. */
    page.__appels = [];
    r = await importer(page, 'sans-calcul.xls', FX.xls({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], [{ formuleSansTexte: true }, '001', 'A'], ['TFE2', '002', 'B']] }] }));
    verifier('NAME en formule dont le résultat texte manque (pas d’enregistrement STRING) : refusé, « formule sans valeur calculée », rien n’est envoyé',
      /erreur/.test(r.etat.classe) && /formule sans valeur calculée/.test(r.etat.texte) && page.__appels.length === 0, r.etat.texte);
    await page.close();
    /* Les fusions en plusieurs enregistrements, et l'export GATES d'Excel 95 (qui n'en a pas). */
    const g = feuilleGates(60);
    const lignesG = FX.lignesGates(g);
    const lus = {};
    for (const [nom, contenu] of [['ref.xlsx', xlsxGates(g)], ['fusions.xls', FX.xls({ onglets: [{ nom: 'Export', lignes: lignesG, fusions: g.fusions, fusionsParEnregistrement: 5 }] })],
      ['excel95.xls', FX.xls({ biff: 5, onglets: [{ nom: 'Export', lignes: lignesG, fusions: g.fusions }] })]]) {
      const cg = new Classeur([ongletGates('HDK', gates(40))]);
      const pg = await fenetre(serveur(cg));
      lus[nom] = { r: await importer(pg, nom, contenu, { sansArchiver: true }), f: cg.getSheetByName('HDK') };
      await pg.close();
    }
    const ref = lus['ref.xlsx'], fus = lus['fusions.xls'], e95 = lus['excel95.xls'];
    verifier('les seize fusions de la ligne des groupes écrites en quatre enregistrements MERGEDCELLS : toutes recréées, les valeurs celles du .xlsx',
      /\bok\b/.test(fus.r.etat.classe) && fus.f.fusions.length === 16 && JSON.stringify(fusionsDe(fus.f)) === JSON.stringify(fusionsDe(ref.f)) && !premierEcart(fus.f.valeurs, ref.f.valeurs),
      premierEcart(fus.f.valeurs, ref.f.valeurs) || fus.r.etat.texte);
    verifier('l’export GATES d’Excel 95, qui ne connaît pas les fusions : les mêmes valeurs ; la ligne prévient comme pour un .csv, la page déduit les groupes de proche en proche et trouve la colonne suivie',
      !premierEcart(e95.f.valeurs, ref.f.valeurs) && e95.f.fusions.length === 0 && /un \.xls d’Excel 95 ne garde pas les cellules fusionnées de la ligne des groupes/.test(e95.r.ligne.lu) &&
      /avertissement/.test(e95.r.etat.classe) && /colonne suivie HDK AA 011/.test(e95.r.etat.texte) && /Un \.xls d’Excel 95 ne garde pas les cellules fusionnées/.test(e95.r.etat.texte),
      e95.r.ligne.lu + ' / ' + e95.r.etat.texte);
  }

  // =================================================================
  section('Les .xls qui ne se lisent pas le disent, et rien ne part');
  {
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx, h => h.replace('"maxOctetsXls":209715200', '"maxOctetsXls":5000000'));
    const simple = { onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE1', '001', 'A']] }] };
    const refus = [
      ['un .xls protégé par un mot de passe, écrit par LibreOffice (FILEPASS, chiffrement RC4) : dit protégé', 'lo-protege.xls', lireXls('lo-protege.xls'), /protégé/],
      ['un .xls Excel 97-2003 au FILEPASS fabriqué : dit protégé', 'mdp.xls', FX.xls(Object.assign({ motDePasse: true }, simple)), /protégé/],
      ['un .xls d’Excel 95 au FILEPASS (masquage XOR) : dit protégé', 'mdp95.xls', FX.xls(Object.assign({ motDePasse: true, biff: 5 }, simple)), /protégé/],
      ['un vrai .xls tronqué au milieu (téléchargement coupé) : « abîmé, le retélécharger »', 'tronque.xls', lireXls('lo-see.xls').subarray(0, 380000), /abîmé.*retélécharger/],
      ['une chaîne de secteurs qui boucle sur elle-même avant la fin du flux : abîmé, jamais une lecture sans fin', 'boucle.xls',
        FX.xls({ onglets: [{ nom: 'S', lignes: FX.lignesSee(60) }] }, { boucle: 'Workbook' }), /abîmé/],
      ['un flux « Workbook » qui n’est pas du BIFF : abîmé', 'brouille.xls', FX.ole([{ nom: 'Workbook', donnees: Buffer.alloc(5000, 0x41) }]), /abîmé/],
      ['un document Office sans classeur (un « WordDocument ») : dit qu’il ne renferme aucun classeur', 'lettre.xls', FX.ole([{ nom: 'WordDocument', donnees: Buffer.alloc(5000, 0x41) }]),
        /ne renferme aucun classeur Excel/],
      ['un classeur d’Excel 2 à 4 (BIFF2, écrit par SheetJS) : « très ancien format », et quoi demander', 'vieux.xls', lireXls('sheetjs-see-biff2.xls'), /très ancien format Excel.*\.xlsx/],
      ['un classeur binaire (.xlsb) : refusé, il faut l’export en .xlsx ou en .csv', 'export.xlsb', zip([{ nom: '[Content_Types].xml', donnees: '<Types/>' }, { nom: 'xl/workbook.bin', donnees: Buffer.alloc(64) }]),
        /classeur binaire \(\.xlsb\).*\.xlsx ou en \.csv/],
      ['un .xls de plus de 200 Mo (ici, le plafond baissé à 5 Mo) : « bien plus qu’un export », lu jamais', 'enorme.xls', FX.ole([{ nom: 'Workbook', donnees: Buffer.alloc(6000000) }]),
        /bien plus qu’un export \(au plus 4,8 Mo/]
    ];
    for (const [nom, fichier, contenu, motif] of refus) {
      const r = await importer(page, fichier, contenu);
      verifier(nom, /erreur/.test(r.etat.classe) && motif.test(r.etat.texte) && !/Erreur inattendue/.test(r.etat.texte) && page.__appels.length === 0, r.etat.texte);
    }
    await page.close();
  }

  // =================================================================
  section('Les .xls d’autres programmes, et leurs bords');
  {
    const c = classeur();
    const page = await fenetre(chargerServeur(c, {}));
    const voir = () => c.getSheetByName('SEE HDK') ? c.getSheetByName('SEE HDK').valeurs : [];
    const texte = () => voir().map(l => l.join('|')).join(' / ');
    /* FORMULA sous les numéros d'Excel 3 et 4 (0x0206, 0x0406), comme Apple Numbers les écrit dans un .xls d'Excel 97. */
    const formules = [['NAME', 'SOL.', 'Cust.V', 'Quantité'], [{ f: 'TFE311A0600' }, '001', 'A', { f: 12 }], [{ f: 'TFE312A0601' }, '002', 'B', { f: 7.5 }]];
    for (const type of [0x0406, 0x0206]) {
      const r = await importer(page, 'numbers.xls', FX.xls({ typeFormule: type, onglets: [{ nom: 'Sheet 1 - Table 1', lignes: formules }] }), { toutes: true });
      verifier('des formules notées 0x0' + type.toString(16) + ' (Apple Numbers) : lues comme des formules — NAME et Quantité calculés, le texte pris dans son STRING',
        /\bok\b/.test(r.etat.classe) && texte() === 'NAME|SOL.|Cust.V|Quantité / TFE311A0600|001|A|12 / TFE312A0601|002|B|7,5', r.etat.texte + ' ' + JSON.stringify(voir()));
    }
    /* Une cellule texte vide écrite sans son octet d'options (8 octets) : le fichier n'est pas abîmé. */
    let r = await importer(page, 'label-vide.xls', FX.xls({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V', 'Commentaire'],
      ['TFE311A0600', '001', 'A', { labelVide: true }], ['TFE312A0601', '002', 'B', { label: 'ok' }]] }] }), { toutes: true });
    verifier('un LABEL vide de 8 octets, sans octet d’options (comme certains programmes l’écrivent) : une cellule vide, pas un fichier « abîmé »',
      /\bok\b/.test(r.etat.classe) && texte() === 'NAME|SOL.|Cust.V|Commentaire / TFE311A0600|001|A| / TFE312A0601|002|B|ok', r.etat.texte + ' ' + JSON.stringify(voir()));
    /* Un émoji (deux unités UTF-16) coupé entre deux enregistrements : textes partagés coupés tous les 41 octets,
       résultats de formule tous les 13 ; les deux moitiés tombent tour à tour de chaque côté de la coupure. */
    const notes = [];
    for (let k = 0; k < 40; k++) notes.push('Ω'.repeat(k) + '📌 à reprendre, voir la note du lot 𝔄' + k);
    const lignesE = [['NAME', 'SOL.', 'Cust.V', 'Commentaire', 'Formule']].concat(notes.map((t, k) => [FX.nomSee(k), '001', 'A', t, { f: t }]));
    r = await importer(page, 'emoji.xls', FX.xls({ sst: { max: 41 }, onglets: [{ nom: 'S', lignes: lignesE, maxString: 13 }] }), { toutes: true });
    const abimes = voir().slice(1).filter((l, k) => l[3] !== notes[k] || l[4] !== notes[k]).length;
    verifier('un émoji ou une lettre hors du plan de base coupé entre deux enregistrements CONTINUE (40 positions de coupure, textes partagés et résultats de formule) : ' +
      'ses deux moitiés se rejoignent, jamais de « � »', /\bok\b/.test(r.etat.classe) && voir().length === 41 && abimes === 0 && !JSON.stringify(voir()).includes('\ufffd'),
      abimes + ' texte(s) faux ; ' + JSON.stringify(voir().slice(1, 3)));
    /* « General » sous ses noms locaux : jamais une date. */
    const nombres = (fmt, extra) => [['NAME', 'SOL.', 'Cust.V', 'Quantité', 'Date'], ['TFE1', '001', 'A', { n: 42, fmt }, { n: 45000, fmt: 'jour' }],
      ['TFE2', '002', 'B', { n: 1234.5, fmt }, extra || { n: 45001, fmt: 'jour' }]];
    const attendu = 'NAME|SOL.|Cust.V|Quantité|Date / TFE1|001|A|42|15/03/2023 / TFE2|002|B|1234,5|16/03/2023';
    for (const [nom, spec] of [
      ['un format nommé « Standaard » (néerlandais)', { onglets: [{ nom: 'S', lignes: nombres('standaard') }] }],
      ['« Allmänt » (suédois)', { onglets: [{ nom: 'S', lignes: nombres('allmant') }] }],
      ['« Yleinen » (finnois)', { onglets: [{ nom: 'S', lignes: nombres('yleinen') }] }],
      ['« Standardowy » (polonais)', { onglets: [{ nom: 'S', lignes: nombres('standardowy') }] }],
      ['« Общий » (russe)', { onglets: [{ nom: 'S', lignes: nombres('obchtchi') }] }],
      ['le format n° 0 nommé « Standaard », en Excel 95', { biff: 5, formatZero: 'Standaard', onglets: [{ nom: 'S', lignes: nombres('general') }] }],
      ['le format n° 0 nommé « Allmänt », en Excel 97', { formatZero: 'Allmänt', onglets: [{ nom: 'S', lignes: nombres('general') }] }]]) {
      r = await importer(page, 'general.xls', FX.xls(spec), { toutes: true });
      verifier(nom + ' : le nom local de « General », les nombres restent des nombres (42, 1234,5), les dates des dates', /\bok\b/.test(r.etat.classe) && texte() === attendu,
        r.etat.texte + ' ' + JSON.stringify(voir()));
    }
    /* Le répertoire du conteneur dont la chaîne boucle : le classeur, nommé dans son deuxième secteur, ne se trouve pas. */
    const flux = n => ({ nom: n, donnees: Buffer.alloc(200, 0x20) });
    const classeurSimple = FX.classeurBiff({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE1', '001', 'A']] }] });
    const quatre = [flux('\u0001CompObj'), flux('\u0005SummaryInformation'), flux('\u0005DocumentSummaryInformation'), { nom: 'Workbook', donnees: classeurSimple }];
    r = await importer(page, 'repertoire.xls', FX.ole(quatre), { toutes: true });
    const sain = /\bok\b/.test(r.etat.classe);
    r = await importer(page, 'repertoire.xls', FX.ole(quatre, { boucleRepertoire: true }), { toutes: true });
    verifier('un conteneur dont la chaîne du répertoire boucle (le classeur nommé dans son deuxième secteur) : « abîmé, le retélécharger », pas « aucun classeur, un document Word ? »' +
      ' — le même fichier sain se lit', sain && /erreur/.test(r.etat.classe) && /abîmé.*retélécharger/.test(r.etat.texte) && !/aucun classeur/.test(r.etat.texte), r.etat.texte);
    /* Un fichier vide : un téléchargement raté. */
    for (const nom of ['vide.xls', 'vide.xlsx', 'vide.csv']) {
      page.__appels = [];
      r = await importer(page, nom, Buffer.alloc(0));
      verifier('« ' + nom + ' » de 0 octet : « ce fichier est vide, le téléchargement n’a sans doute pas abouti », pas « ni GATES ni SEE », rien n’est envoyé',
        /erreur/.test(r.etat.classe) && /Ce fichier est vide \(0 octet\) : le téléchargement n’a sans doute pas abouti\. Le retélécharger/.test(r.etat.texte) && page.__appels.length === 0,
        r.etat.texte);
    }
    /* Un « dossier compressé » de Windows (.zip) : glissé tel quel, ou renommé en .xls. */
    const dedans = zip([{ nom: 'export SEE.xls', donnees: FX.xls({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE1', '001', 'A']] }] }) }]);
    await vider(page);
    await ajouter(page, [{ nom: 'export-dossier.zip', contenu: dedans }]);
    let ui = await fenetreEtat(page);
    verifier('un .zip (« dossier compressé ») choisi : pas une ligne, mais dit de l’ouvrir et d’en glisser le fichier',
      ui.n === 0 && /« export-dossier\.zip » : c’est un dossier compressé \(\.zip\), pas un classeur : l’ouvrir \(double-clic, ou clic droit → Extraire tout\) et glisser ici le fichier/.test(ui.etat),
      ui.etat);
    r = await importer(page, 'export.xls', dedans);
    verifier('… renommé en .xls : la même explication sur sa ligne, avec ce qu’il renferme (plus de « pas de xl/workbook.xml »)',
      /erreur/.test(r.etat.classe) && /dossier compressé \(\.zip\).*Il renferme : export SEE\.xls\./.test(r.etat.texte) && !/workbook\.xml/.test(r.etat.texte), r.etat.texte);
    await page.close();
  }

  // =================================================================
  section('Un .xls chiffré avec le mot de passe par défaut d’Excel (« VelvetSweatshop ») se lit sans rien demander');
  {
    /* Excel chiffre ainsi un .xls dont seule la structure est protégée, ou qui n'a de mot de passe que pour
       la modification ; Excel et LibreOffice l'ouvrent sans rien demander. */
    const lus = {};
    for (const [nom, contenu] of [['export_48.xls', lireXls('lo-gates.xls')], ['export_48 protégé.xls', lireXls('lo-velvet.xls')]]) {
      const cg = new Classeur([ongletGates('HDK', gates(40))]);
      const ctx = serveur(cg);
      const pg = await fenetre(ctx);
      lus[nom] = { r: await importer(pg, nom, contenu, { sansArchiver: true }), f: cg.getSheetByName('HDK'), ctx };
      await pg.close();
    }
    const l = lus['export_48.xls'], v = lus['export_48 protégé.xls'];
    verifier('l’export GATES enregistré par LibreOffice avec « VelvetSweatshop » (FILEPASS, RC4 d’Excel 97) : déchiffré, lu, rattaché à « HDK » — 186 plans · 138 colonnes · ' +
      'en-têtes en ligne 2 · 16 cellules fusionnées, les mêmes valeurs et les mêmes fusions que le .xls non chiffré, la colonne suivie trouvée',
      /\bok\b/.test(v.r.etat.classe) && v.r.ligne.choix === 'HDK' && /^186 plans · 138 colonnes · en-têtes en ligne 2 · 16 cellules fusionnées/.test(v.r.ligne.lu) &&
      !premierEcart(v.f.valeurs, l.f.valeurs) && JSON.stringify(v.f.valeurs) === JSON.stringify(l.f.valeurs) && JSON.stringify(fusionsDe(v.f)) === JSON.stringify(fusionsDe(l.f)) &&
      JSON.stringify(v.ctx.construireModele('HDK')) === JSON.stringify(l.ctx.construireModele('HDK')) && /colonne suivie HDK AA 011/.test(v.r.etat.texte),
      premierEcart(v.f.valeurs, l.f.valeurs) || v.r.ligne.lu + ' / ' + v.r.etat.texte);
    /* Fabriqués : le même SEE en clair et chiffré des trois façons d'Excel (les chiffrés ont été vérifiés une fois avec
       msoffcrypto-tool, hors du dépôt : il les déchiffre avec ce mot de passe, octet pour octet). */
    const c = classeur();
    const page = await fenetre(chargerServeur(c, {}));
    const see = { onglets: [{ nom: 'Graphique', type: 'graphique' }, { nom: 'Nommage', lignes: FX.lignesSee(400) }] };
    await importer(page, 'clair.xls', FX.xls(see), { toutes: true });
    const clair = JSON.stringify(c.getSheetByName('SEE HDK').valeurs);
    for (const [nom, chiffre] of [['RC4 d’Excel 97 (clé par MD5)', { methode: 'rc4' }], ['RC4 CryptoAPI, clé de 128 bits (SHA-1)', { methode: 'cryptoapi' }],
      ['RC4 CryptoAPI, clé de 40 bits', { methode: 'cryptoapi', bits: 40 }]]) {
      const r = await importer(page, 'chiffre.xls', FX.xls(Object.assign({ chiffre }, see)), { toutes: true });
      verifier('un SEE de 400 lignes chiffré en ' + nom + ' avec le mot de passe par défaut : lu, exactement comme le même en clair',
        /\bok\b/.test(r.etat.classe) && JSON.stringify(c.getSheetByName('SEE HDK').valeurs) === clair && c.getSheetByName('SEE HDK').valeurs.length === 401, r.etat.texte);
    }
    for (const [nom, chiffre] of [['RC4 d’Excel 97', { methode: 'rc4', motDePasse: 'secret' }], ['RC4 CryptoAPI', { methode: 'cryptoapi', motDePasse: 'secret' }]]) {
      page.__appels = [];
      const r = await importer(page, 'secret.xls', FX.xls(Object.assign({ chiffre }, see)), { toutes: true });
      verifier('le même chiffré en ' + nom + ' avec un vrai mot de passe : « protégé », rien n’est envoyé', /erreur/.test(r.etat.classe) && /protégé/.test(r.etat.texte) &&
        page.__appels.length === 0, r.etat.texte);
    }
    await page.close();
  }

  // =================================================================
  section('Une page web archivée (.mht, ou nommée .xls)');
  {
    const g = feuilleGates(186);
    const source = FX.SOURCES.gates();
    const lus = {};
    const mht = FX.mhtml([{ lieu: 'file:///C:/Users/nathan/Downloads/export_48.htm', type: 'text/html', jeu: 'windows-1252', codage: 'quoted-printable',
      contenu: htmlExcel(g.valeurs, g.fusions, 'Export GATES') }]);
    for (const [nom, contenu] of [['export_48.xlsx', source], ['export_48.xls', mht]]) {
      const c = new Classeur([ongletGates('HDK', gates(40))]);
      const ctx = serveur(c);
      const page = await fenetre(ctx);
      lus[nom] = { r: await importer(page, nom, contenu, { sansArchiver: true }), f: c.getSheetByName('HDK'), ctx };
      await page.close();
    }
    const x = lus['export_48.xlsx'], m = lus['export_48.xls'];
    verifier('l’export GATES en page web archivée nommée .xls (quoted-printable, Windows-1252, colspan=16 sans guillemets comme Excel les écrit, les cases vides regroupées en ' +
      '« mso-ignore:colspan », qui ne sont pas des fusions) : le même onglet que le .xlsx, les seize fusions comprises — pas une de plus —, la colonne suivie trouvée',
      /\bok\b/.test(m.r.etat.classe) && !premierEcart(m.f.valeurs, x.f.valeurs) && JSON.stringify(fusionsDe(m.f)) === JSON.stringify(fusionsDe(x.f)) &&
      /186 plans, colonne suivie HDK AA 011 › Avancement Définition Electrique/.test(m.r.etat.texte) && /16 cellules fusionnées/.test(m.r.ligne.lu),
      premierEcart(m.f.valeurs, x.f.valeurs) || m.r.etat.texte + ' / ' + m.r.ligne.lu);
    verifier('… la page web porte bien de ces cases vides regroupées, sur la ligne des groupes comme sur celle des en-têtes',
      (htmlExcel(g.valeurs, g.fusions).match(/mso-ignore:colspan/g) || []).length >= 2);
    verifier('… et construireModele y lit la même chose', JSON.stringify(m.ctx.construireModele('HDK')) === JSON.stringify(x.ctx.construireModele('HDK')));
    /* Comme Excel l'enregistre : un cadre, une page par onglet, la liste des onglets, des fichiers à côté. */
    const lignesHtml = l => l.map(v => '<td>' + echHtml(v) + '</td>').join('');
    const seeHtml = '<html><head><meta http-equiv=Content-Type content="text/html; charset=windows-1252"></head><body><table>' +
      '<tr><td colspan=4>Nommage WD BFLOW</td></tr><tr><td></td></tr><tr>' + lignesHtml(['NAME', 'SOL.', 'Cust.V', 'Libellé']) + '</tr>' +
      Array.from({ length: 30 }, (_, i) => '<tr>' + lignesHtml([FX.nomSee(i), String(i % 3 + 1).padStart(3, '0'), 'ABC'[i % 3], 'Câble n° ' + i + ' — « été »']) + '</tr>').join('') +
      '</table></body></html>';
    const parties = [
      { lieu: 'file:///C:/x/Nommage.htm', type: 'text/html', jeu: 'windows-1252', codage: 'quoted-printable',
        contenu: '<html><frameset rows="*,39"><frame src="Nommage_files/sheet001.htm" name="frSheet"><frame src="Nommage_files/tabstrip.htm" name="frTabs"></frameset></html>' },
      { lieu: 'file:///C:/x/Nommage_files/sheet001.htm', type: 'text/html', jeu: 'utf-8', codage: 'base64',
        contenu: '<html><body><table><tr><td>Lisez-moi : export du 01/10/2026</td></tr><tr><td>Rien ici</td></tr></table></body></html>' },
      { lieu: 'file:///C:/x/Nommage_files/sheet002.htm', type: 'text/html', jeu: 'windows-1252', codage: 'quoted-printable', contenu: seeHtml },
      { lieu: 'file:///C:/x/Nommage_files/tabstrip.htm', type: 'text/html', jeu: 'us-ascii', codage: 'quoted-printable',
        contenu: '<html><body><table><tr><td><a href="sheet001.htm">Lisez-moi</a></td><td><a href="sheet002.htm">Nommage</a></td></tr></table></body></html>' },
      { lieu: 'file:///C:/x/Nommage_files/filelist.xml', type: 'text/xml', jeu: 'utf-8', codage: 'quoted-printable', contenu: '<xml><o:File HRef="sheet001.htm"/></xml>' }
    ];
    const c = classeur();
    const page = await fenetre(chargerServeur(c, {}));
    let r = await importer(page, 'Nommage WD BFLOW.mht', FX.mhtml(parties), { toutes: true });
    let f = c.getSheetByName('SEE HDK');
    verifier('un export SEE en page web archivée comme Excel l’enregistre (.mht) — un cadre, une page par onglet (la première en base64, sans en-tête), la liste des onglets : ' +
      'l’en-tête trouvé dans la deuxième page, accents et tiret long justes',
      /\bok\b/.test(r.etat.classe) && f && f.valeurs.length === 31 && f.valeurs[0].join('|') === 'NAME|SOL.|Cust.V|Libellé' &&
      f.valeurs[1].join('|') === 'TFE311A0600|001|A|Câble n° 0 — « été »', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs.slice(0, 2)));
    r = await importer(page, 'export.xls', FX.mhtml([{ lieu: 'export.htm', type: 'text/html', codage: '8bit',
      contenu: '<html><head><meta charset="utf-8"></head><body><table><tr><th>NAME</th><th>SOL.</th><th>Cust.V</th></tr><tr><td>TFE311A0600</td><td>001</td><td>été — A</td></tr></table></body></html>' }],
      { simple: true }), { toutes: true });
    f = c.getSheetByName('SEE HDK');
    verifier('une page web archivée d’une seule page (sans multipart), son jeu de caractères dans sa seule balise <meta> : lue', /\bok\b/.test(r.etat.classe) &&
      f.valeurs.map(l => l.join('|')).join(' / ') === 'NAME|SOL.|Cust.V / TFE311A0600|001|été — A', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    r = await importer(page, 'vide.mht', FX.mhtml([{ lieu: 'note.txt', type: 'text/plain', jeu: 'utf-8', codage: 'quoted-printable', contenu: 'Rien à voir' }]));
    verifier('une page web archivée sans page HTML : le dit', /erreur/.test(r.etat.classe) && /ne renferme aucune page HTML lisible/.test(r.etat.texte), r.etat.texte);
    await page.close();
  }

  // =================================================================
  section('Un gros .xls se lit sans figer la fenêtre');
  {
    const n = 60000;
    const lignesG = [['Nommage WD BFLOW'], [], FX.ENTETE_SEE];
    for (let i = 0; i < n; i++) {
      lignesG.push(['S-' + i, 'TFE' + (311 + i % 90) + 'A' + String(i).padStart(6, '0'), String(1 + i % 4).padStart(3, '0'), 'ABCD'[i % 4], { n: 45000 + i % 900, fmt: 'date' },
        i % 3 ? { rk: 45100 + i % 700, mode: 'entier', fmt: 'date' } : null, { b: i % 2 === 0 }, 'texte ' + (i % 5000)]);
    }
    const fichier = FX.xls({ onglets: [{ nom: 'Export', lignes: lignesG }] });
    const c = classeur();
    const page = await fenetre(chargerServeur(c, {}));
    /* Un battement toutes les 20 ms, dès que le fichier est remis à la fenêtre (avant, Playwright le
       recopie lui-même dans la page, ce qui n'est pas la fenêtre) : le plus long silence dit si la
       lecture, puis l'envoi, l'ont figée. */
    await page.evaluate(() => {
      window.__battements = [];
      document.getElementById('fichier').addEventListener('change', () => {
        window.__battements.push(performance.now());
        window.__minuteur = setInterval(() => window.__battements.push(performance.now()), 20);
      }, { capture: true, once: true });
    });
    const t0 = Date.now();
    const r = await importer(page, 'gros.xls', fichier, { toutes: true, delai: 300000 });
    const silence = await page.evaluate(() => {
      clearInterval(window.__minuteur);
      let m = 0;
      for (let i = 1; i < window.__battements.length; i++) m = Math.max(m, window.__battements[i] - window.__battements[i - 1]);
      return Math.round(m);
    });
    const f = c.getSheetByName('SEE HDK');
    verifier('un .xls de ' + (fichier.length / 1048576).toFixed(1) + ' Mo, ' + n + ' lignes : importé en entier (' + ((Date.now() - t0) / 1000).toFixed(1) + ' s), NAME / SOL. / Cust.V alignés',
      /\bok\b/.test(r.etat.classe) && f && f.valeurs.length === n + 1 && f.valeurs[n].slice(1, 4).join('|') === 'TFE' + (311 + (n - 1) % 90) + 'A' + String(n - 1).padStart(6, '0') + '|' + String(1 + (n - 1) % 4).padStart(3, '0') + '|' + 'ABCD'[(n - 1) % 4],
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs[n]));
    verifier('la fenêtre ne s’est jamais figée plus d’une seconde pendant la lecture et l’envoi (plus long silence : ' + silence + ' ms)', silence < 1000, silence + ' ms');
    await page.close();
  }

  // =================================================================
  section('Une grosse page web archivée se lit sans figer la fenêtre');
  {
    /* 60 000 lignes × 20 colonnes, comme Excel enregistre une page web : 74 Mo en quoted-printable, 91 Mo en base64. */
    const n = 60000, entete = FX.ENTETE_SEE.concat(Array.from({ length: 12 }, (_, j) => 'COL' + (j + 8)));
    const tr = c => '<tr height=17 style=\'height:12.75pt\'>' + c.map(v => '<td class=xl65 style=\'border-top:none\'>' + v + '</td>').join('') + '</tr>\r\n';
    const lignesH = [tr(['Nommage WD BFLOW été']), tr([]), tr(entete)];
    for (let i = 0; i < n; i++) {
      const l = ['S-' + i, 'TFE' + (311 + i % 50) + 'A' + String(600 + i).padStart(5, '0'), String(i % 3 + 1).padStart(3, '0'), 'ABC'[i % 3], '01/02/2023', '05/06/2023',
        i % 2 ? 'oui' : 'non', 'non — été € ' + i];
      for (let j = 8; j < 20; j++) l.push('texte ' + (i * j % 9973));
      lignesH.push(tr(l));
    }
    const html = '<html xmlns:x="urn:schemas-microsoft-com:office:excel"><head><meta http-equiv=Content-Type content="text/html; charset=windows-1252"></head>' +
      '<body><table x:str border=0 cellpadding=0 cellspacing=0>\r\n' + lignesH.join('') + '</table></body></html>';
    for (const [codage, jeu] of [['quoted-printable', 'windows-1252'], ['base64', 'utf-8']]) {
      const fichier = FX.mhtml([{ lieu: 'file:///C:/x/export.htm', type: 'text/html', jeu, codage, contenu: html }]);
      const c = classeur();
      const page = await fenetre(chargerServeur(c, {}));
      await page.evaluate(() => {
        window.__battements = [];
        document.getElementById('fichier').addEventListener('change', () => {
          window.__battements.push(performance.now());
          window.__minuteur = setInterval(() => window.__battements.push(performance.now()), 20);
        }, { capture: true, once: true });
      });
      const t0 = Date.now();
      const r = await importer(page, codage === 'base64' ? 'export.xls' : 'export.mht', fichier, { toutes: true, delai: 300000 });
      const silence = await page.evaluate(() => {
        clearInterval(window.__minuteur);
        let m = 0;
        for (let i = 1; i < window.__battements.length; i++) m = Math.max(m, window.__battements[i] - window.__battements[i - 1]);
        return Math.round(m);
      });
      const f = c.getSheetByName('SEE HDK');
      /* Chaque ligne relue : ses accents, son tiret long, son « € » (des octets =XX, ou deux à trois octets en UTF-8) tombent partout sur les coupures des tranches. */
      let faux = f ? f.valeurs.length === n + 1 ? 0 : n : n, premier = '';
      for (let i = 0; f && i < n && f.valeurs.length === n + 1; i++) {
        const l = f.valeurs[i + 1];
        if (l[1] !== 'TFE' + (311 + i % 50) + 'A' + String(600 + i).padStart(5, '0') || l[3] !== 'ABC'[i % 3] || l[7] !== 'non — été € ' + i || l[19] !== 'texte ' + (i * 19 % 9973)) {
          faux++;
          premier = premier || JSON.stringify(l);
        }
      }
      verifier('une page web archivée de ' + (fichier.length / 1048576).toFixed(0) + ' Mo en ' + codage + ' (' + jeu + '), ' + n + ' lignes × 20 colonnes : importée en entier (' +
        ((Date.now() - t0) / 1000).toFixed(1) + ' s), chaque ligne juste — le décodage par tranches ne coupe ni un « =XX », ni un groupe base64, ni un caractère',
        /\bok\b/.test(r.etat.classe) && faux === 0, r.etat.texte + ' ; ' + faux + ' ligne(s) fausse(s), dont ' + premier);
      verifier('… et la fenêtre ne s’est jamais figée plus d’une seconde (plus long silence : ' + silence + ' ms)', silence < 1000, silence + ' ms');
      await page.close();
    }
  }

  // =================================================================
  section('Un export GATES dont la ligne d’en-têtes est trop bas');
  {
    const c = new Classeur([ongletGates('HDK', gates(20))]);
    const ctx = serveur(c);
    const avant = JSON.stringify(c.getSheetByName('HDK').valeurs);
    const page = await fenetre(ctx);
    const titres = n => Array.from({ length: n }, (_, i) => 'Ligne de titre ' + (i + 1));
    let r = await importer(page, 'bas.xlsx', xlsxGates(gates(20), { titres: titres(7) }));
    verifier('en-têtes en ligne 9 : refusé, « la page ne la trouverait pas », rien n’est envoyé',
      /erreur/.test(r.etat.classe) && /en ligne 9/.test(r.etat.texte) && /la page ne la trouverait pas/.test(r.etat.texte) && page.__appels.length === 0 &&
      JSON.stringify(c.getSheetByName('HDK').valeurs) === avant, r.etat.texte);
    r = await importer(page, 'haut.xlsx', xlsxGates(gates(20), { titres: titres(6) }), { sansArchiver: true });
    const f = c.getSheetByName('HDK');
    verifier('en ligne 8, il passe, ses six lignes de titre comprises, chacune à son numéro ; la page y trouve encore la colonne suivie',
      /\bok\b/.test(r.etat.classe) && f.valeurs[0][0] === 'Ligne de titre 1' && f.valeurs[7][I_REF] === 'Référence UD' && /colonne suivie HDK AA 011/.test(r.etat.texte) &&
      f.fusions.every(x => x.ligne === 7), r.etat.texte);
    await page.close();
  }

  // =================================================================
  section('Un export GATES en CSV : pas de cellules fusionnées');
  {
    const g = gates(40);
    const c = new Classeur([ongletGates('HDK', gates(30))]);
    const ctx = serveur(c);
    const page = await fenetre(ctx);
    let r = await importer(page, 'export.csv', Buffer.from(csvGates(g), 'utf8'));
    verifier('avec sa ligne de groupes : importé ; sans fusion, la page déduit les groupes de proche en proche et retrouve la colonne suivie ; la fenêtre prévient qu’un .csv ne garde pas les fusions',
      /\bok\b/.test(r.etat.classe) && /avertissement/.test(r.etat.classe) && /colonne suivie HDK AA 011 › Avancement Définition Electrique/.test(r.etat.texte) &&
      /\.csv ne garde pas les cellules fusionnées/.test(r.etat.texte) && /\.csv ne garde pas les cellules fusionnées/.test(r.ligne.lu) &&
      c.getSheetByName('HDK').fusions.length === 0 && /Relevé S\d+ archivé/.test(r.etat.texte), r.etat.texte);
    const histo = JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs);
    page.__appels = [];
    r = await importer(page, 'export.csv', Buffer.from(csvGates(g, { sansGroupes: true }), 'utf8'));
    /* Sans ligne de groupes, la page ne trouverait plus la colonne suivie, que
       « HDK » a : l'export ne le remplace pas (débrief 20). La ligne du
       fichier disait déjà qu'un .csv ne garde pas les fusions. */
    const avantCsv = JSON.stringify(c.getSheetByName('HDK').valeurs);
    verifier('sans ligne de groupes : la page n’y trouverait plus la colonne suivie, que « HDK » a — refusé, l’ancien intact, rien d’archivé ; la ligne du fichier conseillait l’export Excel',
      /erreur/.test(r.etat.classe) && /Colonne suivie absente de cet export/.test(r.etat.texte) && /L’ancien onglet « HDK » est intact/.test(r.etat.texte) &&
      /\.csv ne garde pas les cellules fusionnées/.test(r.ligne.lu) && JSON.stringify(c.getSheetByName('HDK').valeurs) === avantCsv && sansImport(c) &&
      page.__appels.indexOf('importArchiverReleve') === -1 && JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs) === histo, r.etat.texte + ' / ' + r.ligne.lu);
    await page.close();
  }

  // =================================================================
  section('Deviner le contrat d’un export GATES');
  {
    const c = new Classeur([ongletGates('HDK', gates(40)), ongletGates('THS', gates(30, { prefixe: 'THS' }))]);
    const ctx = serveur(c);
    let page = await fenetre(ctx);
    let l = (await ajouter(page, [{ nom: 'export.xlsx', contenu: xlsxGates(gates(30, { prefixe: 'THS' })) }]))[0];
    verifier('(a) le contrat dont il partage les plans : « THS », 30 plans sur 30 — même si ses groupes disent « HDK AA »',
      l.choix === 'THS' && /30 plans sur 30 déjà dans « THS »/.test(l.note) && /Remplacera l’onglet « THS »/.test(l.cible), JSON.stringify(l));
    await page.close();
    /* Un contrat préparé d'avance : ses lignes de groupes et d'en-têtes, pas de plan. */
    const prepare = gates(1, { groupe: 'VRK' });
    prepare.valeurs = prepare.valeurs.slice(0, 2);
    const c2 = new Classeur([ongletGates('HDK', gates(40)), ongletGates('VRK', prepare)]);
    const ctx2 = serveur(c2);
    page = await fenetre(ctx2);
    l = (await ajouter(page, [{ nom: 'export.xlsx', contenu: xlsxGates(gates(25, { prefixe: 'VRK', groupe: 'VRK' })) }]))[0];
    verifier('(b) aucun plan en commun, mais « VRK » nommé au-dessus des en-têtes (« VRK AA 011 ») : le contrat préparé d’avance, sans plan',
      l.choix === 'VRK' && /« VRK » nommé au-dessus des en-têtes/.test(l.note), JSON.stringify(l));
    await page.close();
    page = await fenetre(ctx2);
    l = (await ajouter(page, [{ nom: 'export_VRK_S40.xlsx', contenu: xlsxGates(gates(25, { prefixe: 'VRK', groupe: 'XYZ' })) }]))[0];
    verifier('(c) rien au-dessus des en-têtes : le nom du fichier (« export_VRK_S40 »)', l.choix === 'VRK' && /« VRK » dans le nom du fichier/.test(l.note), JSON.stringify(l));
    await page.close();
    /* L'export d'un autre contrat, aux groupes « HDK AA » : nommé, mais rien en commun avec HDK — à confirmer. */
    page = await fenetre(ctx2);
    l = (await ajouter(page, [{ nom: 'export.xlsx', contenu: xlsxGates(gates(25, { prefixe: 'THS' })) }]))[0];
    let ui = await fenetreEtat(page);
    verifier('« HDK » nommé dans les groupes, mais son onglet n’a aucun plan en commun avec le fichier : rien n’est choisi à sa place, « Importer » attend',
      l.choix === '' && l.verifier && /« HDK » est nommé au-dessus des en-têtes, mais son onglet n’a que 0 plan en commun avec ce fichier : choisir le contrat\./.test(l.note) &&
      ui.desactive && /Choisir le contrat de « export\.xlsx »/.test(ui.blocage), JSON.stringify([l, ui]));
    await choisir(page, 0, '\u0001nouveau');
    l = (await lignes(page))[0];
    ui = await fenetreEtat(page);
    verifier('« Nouveau contrat… » : un champ pour son nom — vide, « HDK » étant déjà un contrat —, et « Importer » attend un nom',
      l.nouveau === '' && ui.desactive && /Donner un nom au nouveau contrat de « export\.xlsx »/.test(ui.blocage), JSON.stringify([l, ui]));
    await page.locator('#liste .fichier .nouveau').fill('THS');
    await attendreLecture(page);
    l = (await lignes(page))[0];
    const r = { etat: await lancer(page) };
    /* « Importer » cliqué tout de suite : le champ perd le focus (« change »), le nom déjà vérifié n'est pas redemandé — le clic n'est pas perdu. */
    verifier('« THS » tapé, vérifié, « Importer » cliqué aussitôt : créé après le dernier onglet de contrat, c’est un contrat, et son premier relevé est archivé',
      /Créera l’onglet « THS » : un nouveau contrat/.test(l.cible) && /\bok\b/.test(r.etat.classe) && /onglet « THS » créé \(nouveau contrat\) : 25 plans/.test(r.etat.texte) &&
      nomsOnglets(c2).slice(0, 3).join() === 'HDK,VRK,THS' && ctx2.listerContrats(c2).map(k => k.id).join() === 'HDK,VRK,THS' && ctx2.getHistorique(c2, 'THS').length === 1,
      r.etat.texte + ' / ' + nomsOnglets(c2).join(', '));
    await page.close();
    /* Un contrat inconnu, aux groupes « NEO AA » : un nouveau contrat, nommé d'après eux. */
    const c3 = new Classeur([ongletGates('HDK', gates(40)), new Feuille('Notes', [['x']])]);
    const ctx3 = serveur(c3);
    page = await fenetre(ctx3);
    l = (await ajouter(page, [{ nom: 'gates.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'NEO', groupe: 'NEO' })) }]))[0];
    verifier('(d) aucun indice parmi les contrats : « Nouveau contrat… », nommé d’après ses groupes « NEO AA … », le nom déjà vérifié',
      l.choix === '\u0001nouveau' && l.nouveau === 'NEO' && /nommé d’après ses groupes « NEO AA … »/.test(l.note) && /Créera l’onglet « NEO » : un nouveau contrat/.test(l.cible), JSON.stringify(l));
    const r3 = { etat: await lancer(page) };
    verifier('importé : « NEO » rangé juste après « HDK », avant « Notes » ; ses groupes n’étant pas « HDK AA 011 », la fenêtre dit que la colonne suivie est introuvable, sans archiver',
      nomsOnglets(c3).join() === 'HDK,NEO,Notes' && ctx3.listerContrats(c3).map(k => k.id).join() === 'HDK,NEO' && /colonne suivie est introuvable/.test(r3.etat.texte) &&
      !c3.getSheetByName('Historique_FWD_NEO'), r3.etat.texte + ' / ' + nomsOnglets(c3).join(', '));
    await page.close();
    /* Deux contrats nommés dans le fichier : à choisir. */
    page = await fenetre(ctx);
    const mele = gates(20, { prefixe: 'ZZZ' });
    let k = 0;
    mele.valeurs[0] = mele.valeurs[0].map(v => /^HDK AA/.test(v) && k++ % 2 ? v.replace('HDK', 'THS') : v);
    l = (await ajouter(page, [{ nom: 'export.xlsx', contenu: xlsxGates(mele) }]))[0];
    verifier('deux contrats nommés dans les groupes (« HDK AA », « THS AA ») et aucun plan en commun : à choisir, et la fenêtre dit pourquoi',
      l.choix === '' && /plusieurs contrats nommés dans le fichier \(HDK, THS\) : choisir le contrat, ou « Nouveau contrat… »/.test(l.note), JSON.stringify(l));
    await page.close();
    /* Aucun contrat encore : le premier. */
    const c4 = new Classeur([new Feuille('Feuille 1', [])]);
    const ctx4 = serveur(c4);
    page = await fenetre(ctx4);
    l = (await ajouter(page, [{ nom: 'export.xlsx', contenu: xlsxGates(gates(30)) }]))[0];
    const r4 = { etat: await lancer(page) };
    verifier('un classeur sans contrat : le premier export crée le premier contrat, nommé d’après ses groupes (« HDK »), en tête, et archive son premier relevé',
      l.choix === '\u0001nouveau' && l.nouveau === 'HDK' && /le premier contrat du classeur/.test(l.note) && /\bok\b/.test(r4.etat.classe) &&
      nomsOnglets(c4).slice(0, 2).join() === 'HDK,Feuille 1' && ctx4.listerContrats(c4).map(x => x.id).join() === 'HDK' && ctx4.getHistorique(c4, 'HDK').length === 1,
      JSON.stringify(l) + ' / ' + r4.etat.texte + ' / ' + nomsOnglets(c4).join(', '));
    await page.close();
  }

  // =================================================================
  section('Deviner le contrat d’un export SEE');
  {
    const c0 = classeur();
    const ctx0 = chargerServeur(c0, {});
    verifier('le rapprochement de la page, côté serveur : le A de SEE remis à sa place, la solution sur trois chiffres, l’indice laissé pour apparier, une référence hors format à part',
      ctx0.cleRapprochementUD('GBE312A3600002B') === 'GBE3123A600002' && ctx0.cleRapprochementUD(' gbe3123a600-002-b ') === 'GBE3123A600002' &&
      ctx0.cleRapprochementUD('UD-21-1000') === '?UD-21-1000' &&
      ctx0.refLigneSecondeBase(['NAME', 'SOL.', 'Cust.V'], { NAME: 'TFE311A0600', 'SOL.': '1', 'Cust.V': 'b' }) === 'TFE3110A600001B',
      [ctx0.cleRapprochementUD('GBE312A3600002B'), ctx0.refLigneSecondeBase(['NAME', 'SOL.', 'Cust.V'], { NAME: 'TFE311A0600', 'SOL.': '1', 'Cust.V': 'b' })].join());
    const c = new Classeur([ongletGates('HDK', gates(40)), ongletGates('THS', gates(30, { refs: i => refGates(i) }))]);
    const ctx = serveur(c);
    const jeton = jetonDe(ctx);
    const rep = ctx.importDevinerContratSEE(jeton, ['NAME', 'SOL.', 'Cust.V'], lignesSEE(30).slice(3).map(x => [x[1], x[2], x[3]]));
    verifier('importDevinerContratSEE lit l’échantillon comme lireSecondeBase lit un onglet, puis rapproche comme la page : 30 sur 30 dans « THS », rien dans « HDK »',
      rep.lignes === 30 && rep.contrats.map(x => x.id + ':' + x.commun).join() === 'HDK:0,THS:30', JSON.stringify(rep));
    let page = await fenetre(ctx);
    let l = (await ajouter(page, [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeXlsx(30) }]))[0];
    verifier('(a) dans la fenêtre : « THS », les références retrouvées dites', l.choix === 'THS' && /30 références de l’échantillon sur 30 retrouvées dans « THS »/.test(l.note) && !l.verifier,
      JSON.stringify(l));
    await vider(page);
    l = (await ajouter(page, [{ nom: 'Export SEE HDK.xlsx', contenu: seeXlsx(10, { decalage: 500 }) }]))[0];
    verifier('(b) aucune référence en commun : le nom du fichier (« Export SEE HDK »)', l.choix === 'HDK' && /« HDK » dans le nom du fichier/.test(l.note), JSON.stringify(l));
    await page.close();
    /* Un export SEE pour un contrat que la même liste crée. */
    const c5 = new Classeur([ongletGates('HDK', gates(40))]);
    const ctx5 = serveur(c5);
    page = await fenetre(ctx5);
    const lus = await ajouter(page, [{ nom: 'SEE NEO.xlsx', contenu: seeXlsx(12) }, { nom: 'export.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'NEO', groupe: 'NEO' })) }]);
    verifier('un export SEE pour le nouveau contrat de la même liste : proposé (« NEO (nouveau) »), deviné par le nom du fichier, l’onglet « SEE NEO » à créer',
      lus[0].options.indexOf('NEO') !== -1 && lus[0].choix === 'NEO' && /Créera l’onglet « SEE NEO »/.test(lus[0].cible) && lus[1].nouveau === 'NEO', JSON.stringify(lus));
    page.__appels = [];
    const r = { etat: await lancer(page) };
    verifier('importés : « NEO » d’abord (l’export GATES), puis sa base « SEE NEO »', /\bok\b/.test(r.etat.classe) && !!c5.getSheetByName('NEO') && c5.getSheetByName('SEE NEO').valeurs.length === 13 &&
      page.__cibles.join(' ') === JSON.stringify({ sorte: 'gates', contrat: 'NEO', nouveau: true }) + ' ' + JSON.stringify({ sorte: 'see', contrat: 'NEO' }), r.etat.texte + ' / ' + page.__cibles.join(' '));
    await page.close();
  }

  // =================================================================
  section('Deux fichiers pour le même onglet');
  {
    const c = new Classeur([ongletGates('HDK', gates(40))]);
    const ctx = serveur(c);
    const page = await fenetre(ctx);
    /* Le cas courant : « Export GATES.xlsx », de la semaine dernière, resté
       dans Téléchargements, et « Export GATES (1).xlsx », du jour. Le plus
       récent est le PREMIER de la liste : c'est sa date qui le désigne. */
    const an = new Date().getFullYear();
    const lus = await ajouter(page, [{ nom: 'Export GATES (1).xlsx', contenu: xlsxGates(gates(40)), date: new Date(an, 9, 3, 14, 20).getTime() },
      { nom: 'Export GATES.xlsx', contenu: xlsxGates(gates(38)), date: new Date(an, 8, 26, 9, 5).getTime() },
      { nom: 'see_1.xlsx', contenu: seeXlsx(5), date: new Date(an, 9, 1, 8, 0).getTime() }, { nom: 'see_2.xlsx', contenu: seeXlsx(6), date: new Date(an, 9, 1, 8, 0, 30).getTime() }]);
    verifier('chaque ligne dit la date de son fichier, « du 3 oct. 14:20 »', lus[0].date === 'du 3 oct. 14:20' && lus[1].date === 'du 26 sept. 09:05',
      JSON.stringify(lus.map(x => x.date)));
    let ui = await fenetreEtat(page);
    verifier('deux exports GATES du même contrat : « Importer » attend, la fenêtre dit lesquels, leur date, et lequel garder — le plus récent',
      ui.desactive && ui.blocage === 'Deux fichiers vont dans l’onglet « HDK » : « Export GATES (1).xlsx » (du 3 oct. 14:20) et « Export GATES.xlsx » (du 26 sept. 09:05). ' +
        'Garder le plus récent, « Export GATES (1).xlsx » (du 3 oct. 14:20) : retirer l’autre — ou, si c’est l’export d’un autre contrat, changer son contrat.', ui.blocage);
    await capture(page, 'deux-fichiers');
    await page.locator('#liste .fichier').nth(1).locator('.retirer').click();
    ui = await fenetreEtat(page);
    verifier('puis deux exports SEE de la même base, de la même minute : la fenêtre ne désigne personne',
      ui.desactive && /Deux fichiers vont dans l’onglet « SEE HDK » : « see_1\.xlsx » \(du 1 oct\. 08:00\) et « see_2\.xlsx » \(du 1 oct\. 08:00\)\. En retirer un, ou changer son contrat\.$/.test(ui.blocage), ui.blocage);
    await page.locator('#liste .fichier').nth(1).locator('.retirer').click();
    ui = await fenetreEtat(page);
    verifier('un de chaque : « Importer » s’allume', !ui.desactive && ui.blocage === '', JSON.stringify(ui));
    await page.close();
  }

  // =================================================================
  section('GATES et SEE d’un coup, pour deux contrats');
  {
    const refA = i => refGates(i), refB = i => refGates(i, 500);
    const c = new Classeur([ongletGates('HDK', gates(40, { refs: refA })), ongletGates('THS', gates(30, { refs: refB }))]);
    const ctx = serveur(c);
    const page = await fenetre(ctx);
    const lus = await ajouter(page, [
      { nom: 'Nommage WD BFLOW (1).xlsx', contenu: seeXlsx(30, { decalage: 500 }) },
      { nom: 'export_48.xlsx', contenu: xlsxGates(gates(40, { refs: refA, avancement: i => i % 2 ? 'VALIDATED' : 'PWD_IN_PROGRESS' })) },
      { nom: 'Nommage WD BFLOW.xlsx', contenu: seeXlsx(40) },
      { nom: 'export_49.xlsx', contenu: xlsxGates(gates(30, { refs: refB, avancement: () => 'VALIDATED' })) }]);
    verifier('quatre fichiers mêlés : chacun reconnu et rattaché à son contrat — les GATES par leurs plans, les SEE par l’échantillon',
      lus.map(x => x.sorte + '→' + x.choix).join() === 'SEE→THS,GATES→HDK,SEE→HDK,GATES→THS' && lus.every(x => !x.verifier), JSON.stringify(lus.map(x => [x.sorte, x.choix, x.note])));
    page.__appels = [];
    page.__cibles = [];
    const etat = await lancer(page);
    const ordre = page.__appels.filter(n => /Debut|Archiver/.test(n)).join();
    verifier('les exports GATES passent d’abord, chacun suivi de l’archivage de son contrat, puis ceux de SEE — dans l’ordre de la liste',
      ordre === 'importSecondeBaseDebut,importArchiverReleve,importSecondeBaseDebut,importArchiverReleve,importSecondeBaseDebut,importSecondeBaseDebut' &&
      page.__cibles.map(x => JSON.parse(x)).map(x => x.sorte + ':' + x.contrat).join() === 'gates:HDK,gates:THS,see:THS,see:HDK', ordre + ' / ' + page.__cibles.join(' '));
    const semaine = semaineDe(ctx);
    verifier('une ligne par fichier, ✓, et le relevé de chaque contrat dit',
      /\bok\b/.test(etat.classe) && (etat.texte.match(/✓/g) || []).length === 4 && /onglet « HDK » remplacé : 40 plans, .*Relevé S\d+ archivé \(40 plans, 20 validés\)/.test(etat.texte) &&
      /onglet « THS » remplacé : 30 plans, .*Relevé S\d+ archivé \(30 plans, 30 validés\)/.test(etat.texte) && /30 lignes dans l’onglet « SEE THS »/.test(etat.texte) &&
      /40 lignes dans l’onglet « SEE HDK »/.test(etat.texte) && /Rouvrir le tableau de bord/.test(etat.texte), etat.texte);
    const hHDK = ctx.getHistorique(c, 'HDK'), hTHS = ctx.getHistorique(c, 'THS');
    verifier('chaque contrat a son relevé de la semaine, et sa base : la page les rapproche (40 et 30 lignes)',
      hHDK.length === 1 && hHDK[0].semaine === semaine && hHDK[0].termine === 20 && hTHS.length === 1 && hTHS[0].termine === 30 &&
      ctx.getDonneesPourClient('HDK').rapprochement.lignes.length === 40 && ctx.getDonneesPourClient('THS').rapprochement.lignes.length === 30 && sansImport(c),
      JSON.stringify([hHDK.map(x => x.semaine + ':' + x.termine), hTHS.map(x => x.semaine + ':' + x.termine)]));
    await page.close();
  }

  // =================================================================
  section('Le relevé de la semaine, contrat par contrat');
  {
    const c = new Classeur([ongletGates('HDK', gates(40)), ongletGates('THS', gates(30, { prefixe: 'THS' }))]);
    const ctx = serveur(c);
    const semaine = semaineDe(ctx), precedente = semaineDe(ctx, 7);
    ctx.archiverContrat_(c, { id: 'HDK', nom: 'HDK' }, precedente);
    ctx.archiverContrat_(c, { id: 'THS', nom: 'THS' }, precedente);
    const thsAvant = JSON.stringify(c.getSheetByName('Historique_FWD_THS').valeurs);
    let page = await fenetre(ctx);
    let r = await importer(page, 'export_48.xlsx', xlsxGates(gates(40, { avancement: (i, v) => i < 10 ? 'VALIDATED' : v })));
    const h = ctx.getHistorique(c, 'HDK');
    verifier('archivé pour le contrat importé seulement : une ligne de la semaine en cours dans Historique_FWD_HDK, celui de THS intact',
      /\bok\b/.test(r.etat.classe) && /Relevé S\d+ archivé \(40 plans, \d+ validés\)/.test(r.etat.texte) && h.length === 2 && h[0].semaine === precedente &&
      h[1].semaine === semaine && h[1].termine >= 10 && JSON.stringify(c.getSheetByName('Historique_FWD_THS').valeurs) === thsAvant, r.etat.texte + ' ' + JSON.stringify(h.map(x => x.semaine)));
    await page.close();
    /* L'export de la semaine passée, réimporté : il est posé, mais le relevé de la semaine, différent, n'est pas écrasé. */
    const histoAvant = JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs);
    page = await fenetre(ctx);
    r = await importer(page, 'export_47.xlsx', xlsxGates(gates(40)));
    verifier('l’export d’un relevé plus ancien : l’import est fait, le relevé refusé — dit comme tel, et pourquoi',
      /\bok\b/.test(r.etat.classe) && /avertissement/.test(r.etat.classe) &&
      new RegExp('Relevé S\\d+ non archivé : l’onglet « HDK » porte le même export que le relevé ' + ctx.semaineDite(precedente, semaine) + ' : le relevé ' + ctx.semaineDite(semaine, semaine) +
        ' déjà archivé, différent, n’est pas écrasé\\.').test(r.etat.texte.replace(/'/g, '’')) && /L’import, lui, est fait/.test(r.etat.texte) &&
      /Si c’est voulu \(GATES est vraiment revenu à cet état, ou le relevé S\d+ déjà pris vient d’un mauvais export\) : menu Suivi FWD → Archiver le relevé de cette semaine, qui demandera confirmation\. Sinon, ce fichier n’est pas l’export du jour : importer le bon\./.test(r.etat.texte.replace(/'/g, '’')) &&
      !/Importer l.export du jour/.test(r.etat.texte) &&
      JSON.stringify(c.getSheetByName('HDK').valeurs) === JSON.stringify(gates(40).valeurs) && JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs) === histoAvant,
      r.etat.texte);
    await page.close();
    /* Un historique orphelin attend d'être rattaché : le premier relevé d'un nouveau contrat est refusé, l'import fait. */
    const c2 = new Classeur([ongletGates('HDK', gates(40)), new Feuille('Historique_FWD_Feuille 1', [['Semaine'], ['2026-S30']], true)]);
    const ctx2 = serveur(c2);
    page = await fenetre(ctx2);
    await ajouter(page, [{ nom: 'export.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'THS' })) }]);
    await choisir(page, 0, '\u0001nouveau');
    await page.locator('#liste .fichier .nouveau').fill('THS');
    await attendreLecture(page);
    r = { etat: await lancer(page) };
    verifier('un historique orphelin dans le classeur : le premier relevé du nouveau contrat est refusé, le message dit lequel renommer ; l’onglet, lui, est créé',
      /\bok\b/.test(r.etat.classe) && /non archivé : l.onglet d.historique « Historique_FWD_Feuille 1 » n.est rattaché à aucun contrat/.test(r.etat.texte) &&
      !!c2.getSheetByName('THS') && !c2.getSheetByName('Historique_FWD_THS'), r.etat.texte);
    await page.close();
  }

  // =================================================================
  section('Un import GATES interrompu');
  {
    const c = new Classeur([ongletGates('HDK', gates(40))]);
    const ctx = serveur(c);
    ctx.archiverContrat_(c, { id: 'HDK', nom: 'HDK' }, semaineDe(ctx, 7));
    const avantOnglet = JSON.stringify(c.getSheetByName('HDK').valeurs), avantFusions = JSON.stringify(c.getSheetByName('HDK').fusions);
    const avantHisto = JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs);
    const page = await fenetre(ctx, rapide);
    const vrai = ctx.importSecondeBaseLot;
    let lots = 0;
    /* Les 43 lignes tiennent en un lot : il échoue, deux fois renvoyé, trois essais en tout. */
    ctx.importSecondeBaseLot = function () { lots++; throw new Error('Service Spreadsheets indisponible'); };
    const r = await importer(page, 'export_48.xlsx', xlsxGates(gates(40, { avancement: () => 'VALIDATED' })));
    ctx.importSecondeBaseLot = vrai;
    await page.waitForTimeout(300);
    verifier('une panne qui dure pendant l’envoi : trois essais, le message la dit ; l’ancien « HDK », ses fusions et son historique sont intacts ; l’onglet temporaire est retiré ; rien n’est archivé',
      /erreur/.test(r.etat.classe) && /Service Spreadsheets indisponible/.test(r.etat.texte) && /Rien n’a été remplacé/.test(r.etat.texte) && lots === 3 &&
      JSON.stringify(c.getSheetByName('HDK').valeurs) === avantOnglet && JSON.stringify(c.getSheetByName('HDK').fusions) === avantFusions &&
      JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs) === avantHisto && sansImport(c) && page.__appels.indexOf('importArchiverReleve') === -1,
      r.etat.texte + ' / ' + lots + ' / ' + nomsOnglets(c).join(', '));
    await page.close();
    /* La fenêtre fermée en plein envoi : le reste porte un export, mais n'est pas un contrat. */
    const jeton = jetonDe(ctx);
    const d = ctx.importSecondeBaseDebut(jeton, { sorte: 'gates', contrat: 'HDK' }, 138, 43);
    ctx.importSecondeBaseLot(jeton, d.feuille, 1, gates(40).valeurs.slice(0, 20));
    ctx.enregistrerInstantaneHebdo();
    verifier('la fenêtre fermée en plein envoi : l’onglet temporaire « HDK (import …) », qui porte pourtant un export, n’est pas un contrat — l’archivage du vendredi ne lui ouvre pas d’historique',
      ctx.listerContrats(c).map(x => x.id).join() === 'HDK' && !c.getSheets().some(f => /^Historique_FWD_HDK \(import/.test(f.getName())) && ctx.getHistorique(c, 'HDK').length === 2,
      nomsOnglets(c).join(', '));
  }

  // =================================================================
  section('Un export sans la colonne suivie ne remplace pas un onglet qui l’a');
  {
    const c = new Classeur([ongletGates('HDK', gates(40)), ongletGates('XYZ', gates(30, { prefixe: 'XYZ', groupe: 'XYZ' }))]);
    const ctx = serveur(c);
    const avant = JSON.stringify(c.getSheetByName('HDK').valeurs), avantFusions = JSON.stringify(c.getSheetByName('HDK').fusions);
    const page = await fenetre(ctx);
    /* Un export d'un autre programme (blocs « XYZ AA … ») choisi pour HDK : la page n'y trouverait pas « HDK AA 011 › … ». */
    const r = await importer(page, 'export_autre.xlsx', xlsxGates(gates(40, { groupe: 'XYZ' })), { contrat: 'HDK' });
    verifier('un export où la page ne trouverait pas la colonne suivie ne remplace pas « HDK », qui l’a : refusé, dit pourquoi, l’ancien intact, ses fusions aussi, pas d’onglet temporaire, rien d’archivé',
      /erreur/.test(r.etat.classe) && /Colonne suivie absente de cet export/.test(r.etat.texte) && /L’ancien onglet « HDK » est intact/.test(r.etat.texte) &&
      !/peut-être allé au bout/.test(r.etat.texte) && JSON.stringify(c.getSheetByName('HDK').valeurs) === avant &&
      JSON.stringify(c.getSheetByName('HDK').fusions) === avantFusions && sansImport(c) && page.__appels.indexOf('importArchiverReleve') === -1,
      r.etat.texte + ' / ' + nomsOnglets(c).join(', '));
    /* Un onglet qui ne la lisait déjà pas (XYZ) : l'export de même forme le remplace, avec l'avertissement d'avant. */
    const r2 = await importer(page, 'export_xyz.xlsx', xlsxGates(gates(30, { prefixe: 'XYZ', groupe: 'XYZ', avancement: () => 'VALIDATED' })), { contrat: 'XYZ' });
    verifier('un onglet où la colonne suivie était déjà introuvable se remplace comme avant, avec l’avertissement : rien de mieux n’est perdu',
      /introuvable/.test(r2.etat.texte) && !/Colonne suivie absente/.test(r2.etat.texte) && sansImport(c) &&
      c.getSheetByName('XYZ').valeurs.slice(3).every(l => l[I_SUIVIE] === 'VALIDATED'), r2.etat.texte);
    await page.close();
  }

  // =================================================================
  section('Les restes d’un import ne sont jamais des contrats');
  {
    const g = gates(30, { prefixe: 'THS' });
    const c = new Classeur([ongletGates('HDK', gates(40)), ongletGates('HDK (import abc123)', gates(40)), ongletGates('THS (ancien abc123)', g),
      new Feuille('SEE HDK (import abc123)', [['NAME', 'SOL.', 'Cust.V'], ['X', '001', 'A']])]);
    const ctx = serveur(c);
    verifier('ni « HDK (import abc123) », ni « THS (ancien abc123) », qui portent pourtant un export, ne sont des contrats ; « SEE HDK (import abc123) » n’est pas la base de HDK',
      ctx.listerContrats(c).map(x => x.id).join() === 'HDK' && !ctx.ongletSecondeBase(c, 'HDK') && ctx.lireSecondeBase(c, 'HDK').etat === 'absent',
      JSON.stringify(ctx.listerContrats(c)));
    const diag = ctx.diagnostic();
    verifier('le Diagnostic nomme chacun ; l’ancien mis de côté se dit tel', ['HDK (import abc123)', 'THS (ancien abc123)', 'SEE HDK (import abc123)']
      .every(n => diag.indexOf('« ' + n + ' » est le reste d\'un import interrompu') !== -1) && /« THS \(ancien abc123\) » est le reste d'un import interrompu \(l'ancien onglet, mis de côté/.test(diag),
      diag.split('\n').filter(x => /reste d/.test(x)).join(' / '));
    const page = await fenetre(ctx);
    const r = await importer(page, 'export.xlsx', xlsxGates(gates(40)), { sansArchiver: true });
    verifier('le prochain import de « HDK » retire le sien, pas ceux des autres', /\bok\b/.test(r.etat.classe) && !c.getSheetByName('HDK (import abc123)') &&
      !!c.getSheetByName('THS (ancien abc123)') && !!c.getSheetByName('SEE HDK (import abc123)'), nomsOnglets(c).join(', '));
    await page.close();
    /* Des onglets nommés à la main comme des restes, sans en avoir l'étiquette
       (six chiffres hexadécimaux, dont une lettre) : des onglets comme les autres. */
    const m = new Classeur([ongletGates('HDK', gates(40)), new Feuille('HDK (ancien export)', [['gardé']]), new Feuille('HDK (ancien 041026)', [['gardé']]),
      new Feuille('HDK (import manuel)', [['gardé']])]);
    const ctxM = serveur(m);
    const pageM = await fenetre(ctxM);
    const rM = await importer(pageM, 'export.xlsx', xlsxGates(gates(40)), { sansArchiver: true });
    verifier('« HDK (ancien export) », « HDK (ancien 041026) », « HDK (import manuel) », nommés à la main : ni pris pour des restes d’import, ni retirés par l’import de « HDK »',
      /\bok\b/.test(rM.etat.classe) && ['HDK (ancien export)', 'HDK (ancien 041026)', 'HDK (import manuel)'].every(n => m.getSheetByName(n) && m.getSheetByName(n).valeurs[0][0] === 'gardé' && !ctxM.estOngletImport(n)) &&
      ctxM.estOngletImport('HDK (import ' + /\(import ([0-9a-f]+)\)/.exec(pageM.__feuilles[0] || '(import x)')[1] + ')'),
      nomsOnglets(m).join(', ') + ' / ' + JSON.stringify(pageM.__feuilles));
    const etiquettes = Array.from({ length: 3000 }, () => ctxM.etiquetteImport());
    verifier('l’étiquette d’un import porte toujours au moins une lettre : jamais six chiffres, comme une date',
      etiquettes.every(e => /^[0-9a-f]{6}$/.test(e) && /[a-f]/.test(e) && ctxM.estOngletImport('X (ancien ' + e + ')')), etiquettes.filter(e => !/[a-f]/.test(e)).join());
    await pageM.close();
  }

  // =================================================================
  section('Un nouveau contrat : son nom, sa place');
  {
    const c = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE HDK', [['NAME', 'SOL.', 'Cust.V'], ['X', '001', 'A']]),
      ongletGates('THS', gates(30, { prefixe: 'THS' })), new Feuille('Notes', [['x']])]);
    const ctx = serveur(c);
    const jeton = jetonDe(ctx);
    const cas = [['', /pas de nom/], ['SEE THS', /nom réservé/], ['Historique_FWD_VRK', /nom réservé/], ['Copie de HDK', /nom réservé/], ['VRK (import abc123)', /nom réservé/],
      ['hdk', /Le contrat « HDK » existe déjà : le choisir dans la liste/], ['notes', /Un onglet « Notes » existe déjà/], ['V'.repeat(81), /Nom trop long : 81 caractères/]];
    const rates = cas.filter(x => { const r = ctx.importVerifierNouveauContrat(jeton, x[0]); return r.ok || !x[1].test(r.message); });
    verifier('un nom vide, réservé (base SEE, historique, copie, import), déjà pris (casse indifférente) ou trop long est refusé, et dit pourquoi', !rates.length,
      rates.map(x => x[0] + ' : ' + JSON.stringify(ctx.importVerifierNouveauContrat(jeton, x[0]))).join(' | '));
    verifier('un nom propre est accepté, sans ses espaces autour', JSON.stringify(ctx.importVerifierNouveauContrat(jeton, '  VRK  ')) === JSON.stringify({ ok: true, nom: 'VRK' }));
    let refus = '';
    try { ctx.importSecondeBaseDebut(jeton, { sorte: 'gates', contrat: 'SEE THS', nouveau: true }, 3, 5); } catch (e) { refus = e.message; }
    verifier('le serveur revérifie au début de l’import, fenêtre ou pas', /nom réservé/.test(refus) && sansImport(c), refus);
    const page = await fenetre(ctx);
    let l = (await ajouter(page, [{ nom: 'export.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'VRK', groupe: 'VRK' })) }]))[0];
    verifier('l’export d’un contrat inconnu : « Nouveau contrat… », nommé d’après ses groupes (« VRK »), le nom vérifié', l.choix === '\u0001nouveau' && l.nouveau === 'VRK' &&
      /Créera l’onglet « VRK » : un nouveau contrat, rangé après les autres/.test(l.cible), JSON.stringify(l));
    await page.locator('#liste .fichier .nouveau').fill('Notes');
    await attendreLecture(page);
    const refuse = await fenetreEtat(page);
    verifier('un nom déjà pris, tapé : refusé à mesure, « Importer » attend et dit pourquoi', refuse.desactive && /Un onglet « Notes » existe déjà/.test(refuse.blocage), JSON.stringify(refuse));
    await page.locator('#liste .fichier .nouveau').fill('VRK');
    await attendreLecture(page);
    const r = { etat: await lancer(page) };
    verifier('importé : « VRK » rangé juste après le dernier onglet de contrat (avant « Notes »), et c’est un contrat',
      /\bok\b/.test(r.etat.classe) && nomsOnglets(c).join() === 'HDK,SEE HDK,THS,VRK,Notes' && ctx.listerContrats(c).map(x => x.id).join() === 'HDK,THS,VRK', nomsOnglets(c).join());
    await page.close();
    /* Un nouveau contrat dont l'envoi échoue : il n'y avait rien à remplacer. */
    const page2 = await fenetre(ctx, rapide);
    const vraiLot = ctx.importSecondeBaseLot;
    ctx.importSecondeBaseLot = function () { throw new Error('Service Spreadsheets indisponible'); };
    l = (await ajouter(page2, [{ nom: 'neo.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'NEO', groupe: 'NEO' })) }]))[0];
    const rNeo = { etat: await lancer(page2) };
    ctx.importSecondeBaseLot = vraiLot;
    verifier('un nouveau contrat dont l’envoi échoue : le message dit « Rien n’a été créé », pas « remplacé » ; ni onglet « NEO », ni reste d’import',
      l.nouveau === 'NEO' && /erreur/.test(rNeo.etat.classe) && /Service Spreadsheets indisponible/.test(rNeo.etat.texte) && /Rien n’a été créé dans le classeur/.test(rNeo.etat.texte) &&
      !/remplacé|ancien onglet/.test(rNeo.etat.texte) && !c.getSheetByName('NEO') && sansImport(c), rNeo.etat.texte + ' / ' + nomsOnglets(c).join());
    await page2.close();
  }

  // =================================================================
  section('Deux tours dans la même fenêtre : la liste des contrats est relue');
  {
    /* Le classeur n'a que HDK. Premier tour : l'export GATES de THS, nouveau
       contrat. Second tour, sans fermer la fenêtre : l'extract SEE de THS
       (un nom de fichier qui ne dit pas le contrat) et un export GATES de
       THS corrigé. Avant, la fenêtre ne connaissait que HDK : l'extract
       partait sans un mot dans « SEE HDK », et l'export butait sur « existe
       déjà : le choisir dans la liste ». */
    const refT = i => refGates(i, 500);
    const c = new Classeur([ongletGates('HDK', gates(40))]);
    const ctx = serveur(c);
    const page = await fenetre(ctx);
    await ajouter(page, [{ nom: 'export_ths.xlsx', contenu: xlsxGates(gates(20, { refs: refT })) }]);
    await choisir(page, 0, '\u0001nouveau');
    await page.locator('#liste .fichier .nouveau').fill('THS');
    await attendreLecture(page);
    let r = await lancer(page);
    verifier('1er tour : THS créé, puis la liste des contrats relue (sans nouveau jeton)',
      /\bok\b/.test(r.classe) && /Relevé S\d+ archivé \(20 plans/.test(r.texte) && !!c.getSheetByName('THS') && page.__appels[page.__appels.length - 1] === 'importContrats',
      r.texte + ' / ' + page.__appels.join());
    const lus = await ajouter(page, [{ nom: 'extract_SEE_semaine40.xlsx', contenu: seeXlsx(20, { decalage: 500 }) },
      { nom: 'export_ths (1).xlsx', contenu: xlsxGates(gates(20, { refs: refT, avancement: () => 'VALIDATED' })) }]);
    const see = lus[0], gat = lus[1];
    verifier('2e tour : l’extract SEE va à THS, reconnu par ses plans — proposé, rien à vérifier',
      see.choix === 'THS' && !see.verifier && see.options.indexOf('THS') !== -1 && /20 références de l’échantillon sur 20 retrouvées dans « THS »/.test(see.note) &&
      /Créera l’onglet « SEE THS »/.test(see.cible), JSON.stringify(see));
    verifier('2e tour : l’export GATES de THS va à THS, qui est dans la liste — plus de « existe déjà »',
      gat.choix === 'THS' && !gat.verifier && /Remplacera l’onglet « THS »/.test(gat.cible), JSON.stringify(gat));
    const ui = await fenetreEtat(page);
    verifier('2e tour : « Importer » s’allume', !ui.desactive && ui.blocage === '', JSON.stringify(ui));
    await capture(page, 'deux-tours-avant-import');
    r = await lancer(page);
    verifier('2e tour : « SEE THS » créé, « SEE HDK » jamais touché ; THS remplacé',
      /\bok\b/.test(r.classe) && !!c.getSheetByName('SEE THS') && !c.getSheetByName('SEE HDK') && c.getSheetByName('THS').valeurs.length === 23 &&
      ctx.lireSecondeBase(c, 'THS').etat === 'ok', r.texte + ' / ' + nomsOnglets(c).join(', '));
    await capture(page, 'deux-tours-fin');
    await page.close();
  }
  {
    /* La relecture de la liste échoue (le classeur ne répond pas) : on ne
       devine pas avec une liste périmée — « Importer » le dit et attend. */
    const c = new Classeur([ongletGates('HDK', gates(40))]);
    const ctx = serveur(c);
    const page = await fenetre(ctx, rapide);
    const vrai = ctx.importContrats;
    ctx.importContrats = function () { throw new Error('Service Spreadsheets indisponible'); };
    await ajouter(page, [{ nom: 'export_ths.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'THS', groupe: 'THS' })) }]);
    await lancer(page);
    await ajouter(page, [{ nom: 'see.xlsx', contenu: seeXlsx(5) }]);
    let ui = await fenetreEtat(page);
    verifier('la liste des contrats n’a pas pu être relue : « Importer » attend, et dit de rouvrir la fenêtre',
      ui.desactive && /La liste des contrats n’a pas pu être relue après l’import : fermer cette fenêtre et la rouvrir/.test(ui.blocage), JSON.stringify(ui));
    ctx.importContrats = vrai;
    await ajouter(page, [{ nom: 'see2.xlsx', contenu: seeXlsx(6) }]);
    ui = await fenetreEtat(page);
    const ls = await lignes(page);
    verifier('au choix suivant, elle est redemandée ; relue, THS est proposé et « Importer » repart',
      !/n’a pas pu être relue/.test(ui.blocage) && ls.every(x => x.options.indexOf('THS') !== -1), JSON.stringify(ui) + ' ' + JSON.stringify(ls.map(x => x.options)));
    await page.close();
  }

  // =================================================================
  section('Un deuxième contrat créé par l’import : l’onglet « SEE » et l’ancien historique suivent le premier');
  {
    /* HDK seul, sa base dans « SEE » tout court, ses relevés dans l'ancien
       « Historique_FWD ». La fenêtre crée THS : avec deux contrats, ni l'un
       ni l'autre ne serait plus lu. */
    const c = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE', [['NAME', 'SOL.', 'Cust.V'], ['GBE312A3600001', '001', 'A']])]);
    const ctx = serveur(c);
    ctx.archiverContrat_(c, { id: 'HDK', nom: 'HDK' }, semaineDe(ctx, 7));
    c.getSheetByName('Historique_FWD_HDK').setName('Historique_FWD');
    verifier('(avant) un seul contrat : « SEE » est sa base, « Historique_FWD » son historique',
      ctx.lireSecondeBase(c, 'HDK').etat === 'ok' && ctx.getHistorique(c, 'HDK').length === 1);
    const page = await fenetre(ctx);
    await ajouter(page, [{ nom: 'export_ths.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'THS' })) }, { nom: 'Nommage WD BFLOW.xlsx', contenu: seeXlsx(12) }]);
    await choisir(page, 0, '\u0001nouveau');
    await page.locator('#liste .fichier .nouveau').first().fill('THS');
    await attendreLecture(page);
    const lus = await lignes(page);
    verifier('la ligne GATES annonce le renommage de « SEE », la ligne SEE de HDK vise le futur nom, « SEE HDK »',
      lus[0].nouveau === 'THS' && /L’onglet « SEE » de « HDK » deviendra « SEE HDK »/.test(lus[0].cible) &&
      lus[1].choix === 'HDK' && /^Remplacera l’onglet « SEE HDK » \(aujourd’hui « SEE », renommé à la création du nouveau contrat\)/.test(lus[1].cible), JSON.stringify(lus));
    await capture(page, 'second-contrat-annonce');
    const r = await lancer(page);
    await capture(page, 'second-contrat-fin');
    verifier('importé : « SEE » devenu « SEE HDK » (et rempli par l’export), « Historique_FWD » devenu « Historique_FWD_HDK » — et la fenêtre le dit',
      /\bok\b/.test(r.classe) && /onglet « THS » créé \(nouveau contrat\) ; l’onglet « SEE » devient « SEE HDK », l’onglet « Historique_FWD » devient « Historique_FWD_HDK »/.test(r.texte) &&
      !c.getSheetByName('SEE') && c.getSheetByName('SEE HDK').valeurs.length === 13 && !c.getSheetByName('Historique_FWD') && !!c.getSheetByName('Historique_FWD_HDK'),
      r.texte + ' / ' + nomsOnglets(c).join(', '));
    verifier('HDK garde sa comparaison et ses relevés ; THS a son premier relevé, dans son propre historique',
      ctx.lireSecondeBase(c, 'HDK').etat === 'ok' && ctx.getHistorique(c, 'HDK').length === 1 && ctx.getHistorique(c, 'THS').length === 1 &&
      /Relevé S\d+ archivé \(20 plans/.test(r.texte), r.texte);
    await page.close();
  }
  {
    /* Sans export SEE dans la liste : la comparaison de HDK ne disparaît plus. */
    const c = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE', [['NAME', 'SOL.', 'Cust.V'], ['GBE312A3600001', '001', 'A']])]);
    const ctx = serveur(c);
    const jeton = jetonDe(ctx);
    const g = gates(20, { prefixe: 'THS', groupe: 'THS' }), cible = { sorte: 'gates', contrat: 'THS', nouveau: true };
    const d = ctx.importSecondeBaseDebut(jeton, cible, 138, g.valeurs.length);
    ctx.importSecondeBaseLot(jeton, d.feuille, 1, g.valeurs);
    const fin = ctx.importSecondeBaseFin(jeton, d.feuille, cible, g.valeurs.length, []);
    verifier('THS créé seul : « SEE » devient « SEE HDK », HDK garde sa comparaison',
      JSON.stringify(fin.renommes) === JSON.stringify([{ de: 'SEE', vers: 'SEE HDK' }]) && ctx.lireSecondeBase(c, 'HDK').etat === 'ok' && !c.getSheetByName('SEE'),
      JSON.stringify(fin.renommes) + ' / ' + nomsOnglets(c).join(', '));
    /* Un « SEE HDK » déjà là : c'est lui qu'on lit, « SEE » n'est pas touché ; deux contrats déjà : rien n'est renommé. */
    const c2 = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE', [['NAME'], ['X']]), new Feuille('SEE HDK', [['NAME', 'SOL.', 'Cust.V'], ['Y', '001', 'A']]),
      new Feuille('Historique_FWD', [['Semaine'], ['2026-S30']], true), new Feuille('Historique_FWD_HDK', [['Semaine'], ['2026-S31']], true)]);
    const ctx2 = serveur(c2);
    const j2 = jetonDe(ctx2);
    const d2 = ctx2.importSecondeBaseDebut(j2, cible, 138, g.valeurs.length);
    ctx2.importSecondeBaseLot(j2, d2.feuille, 1, g.valeurs);
    const fin2 = ctx2.importSecondeBaseFin(j2, d2.feuille, cible, g.valeurs.length, []);
    verifier('« SEE HDK » et « Historique_FWD_HDK » déjà là : rien n’est renommé', fin2.renommes.length === 0 && !!c2.getSheetByName('SEE') && !!c2.getSheetByName('Historique_FWD'),
      JSON.stringify(fin2.renommes));
  }

  // =================================================================
  section('La fin d’un import refuse quand le classeur est occupé');
  {
    const c = new Classeur([ongletGates('HDK', gates(40))]);
    const ctx = serveur(c);
    const avant = JSON.stringify(c.getSheetByName('HDK').valeurs);
    const page = await fenetre(ctx);
    /* Le verrou est pris ailleurs (le vendredi archive) : le début passe, il
       ne touche qu'à l'onglet temporaire ; la fin, qui échange, refuse. */
    vm.runInContext('LockService = { getScriptLock: function () { return { tryLock: function () { return false; }, releaseLock: function () {} }; }, ' +
      'getDocumentLock: function () { return { tryLock: function () { return false; }, releaseLock: function () {} }; } };', ctx);
    const r = await importer(page, 'export_48.xlsx', xlsxGates(gates(40, { avancement: () => 'VALIDATED' })));
    verifier('l’onglet n’est pas échangé sans le verrou : le message le dit, « L’ancien onglet « HDK » est intact », rien ne traîne',
      /erreur/.test(r.etat.classe) && /Le classeur est occupé par un autre geste \(archivage…\) : l’onglet « HDK » n’a pas été remplacé\. Relancer l’import dans une minute\. L’ancien onglet « HDK » est intact\./.test(r.etat.texte) &&
      !/peut-être allé au bout/.test(r.etat.texte) && JSON.stringify(c.getSheetByName('HDK').valeurs) === avant && sansImport(c) && page.__appels.indexOf('importArchiverReleve') === -1,
      r.etat.texte + ' / ' + nomsOnglets(c).join(', '));
    await page.close();
  }

  // =================================================================
  section('Plus de dix fichiers : ceux laissés de côté sont nommés');
  {
    const c = new Classeur([ongletGates('HDK', gates(40))]);
    const page = await fenetre(serveur(c));
    const douze = [];
    for (let i = 1; i <= 12; i++) douze.push({ nom: 'see_' + String(i).padStart(2, '0') + '.csv', contenu: Buffer.from('NAME;SOL.;Cust.V\r\nA' + i + ';001;A\r\n') });
    await ajouter(page, douze);
    const ui = await fenetreEtat(page);
    verifier('dix gardés ; les deux autres nommés, à importer ensuite',
      ui.n === 10 && /Au plus 10 fichiers à la fois : 2 laissés de côté — les importer ensuite : see_11\.csv, see_12\.csv\./.test(ui.etat), JSON.stringify(ui));
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

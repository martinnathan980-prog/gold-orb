/* L'import des exports GATES et SEE sans Excel (menu Suivi FWD → Importer
   les exports GATES et SEE) : la vraie fenêtre, rendue par le vrai Code.gs,
   ouverte dans un vrai navigateur ; google.script.run y répond par les
   vraies fonctions du serveur, sur un classeur en mémoire (qui compte, comme
   Sheets, ses dix millions de cellules, et fusionne comme lui). Depuis le
   débrief 21, chaque export a sa case — « GATES HDK » par contrat, « SEE »
   pour l'extract de tous les porteurs, trié par le PSN de chaque contrat et
   par DIAGRAM TYPE — et la fenêtre ne devine plus rien. Les fichiers sont
   fabriqués pour l'occasion (tests/fabriquer-xlsx.js) : exports GATES à la
   vraie structure (tests/feuille-gates.js : 138 colonnes, seize fusions
   dans la ligne des groupes), extracts SEE (avec ou sans VALIDITY PSN FULL
   et DIAGRAM TYPE) ; chaînes partagées ou en ligne, chaînes riches, styles,
   préfixes, Zip64, CSV, pages web et XML 2003 nommés .xls. Et les vrais
   .xls : ceux de tests/xls/, écrits par LibreOffice, SheetJS et xlwt
   (tests/preparer-xls.js), comparés au .xlsx d'où ils viennent et à la
   lecture qu'en fait SheetJS (l'oracle) ; ceux de tests/fabriquer-xls.js,
   écrits octet par octet pour chaque cas du format ; et les pages web
   archivées (.mht). */
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
/* Un extract SEE réduit, sans les colonnes du tri — celui des essais de
   lecture : titre, ligne vide, en-tête en ligne 3. `decalage` : une autre
   famille de noms. Il n'a ni VALIDITY PSN FULL ni DIAGRAM TYPE : la case SEE
   demande alors « importer sans ce tri » (que coche l'aide importer()). */
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

/* L'extract SEE de tous les porteurs, tel que Nathan l'a photographié
   (débrief 21) : le titre « Nommage WD BFLOW », une ligne vide, puis NAME |
   SOL. | Cust.V | Int. V | ARCHIVE FILE PREFIX | VALIDITY PSN FULL | User
   Status | DIAGRAM TYPE | PRODUCT FAMILY | Validated | deux sans intitulé |
   FG1 TAGDESCRIPTION | DESCRIPTION | SCHEMA NUMBER | Released Date |
   Obsolete Date | Validated Date | REDRAW | une sans intitulé | ARCHIVED |
   une sans intitulé | CGM. `tri(i)` : { psn, type } de la ligne i — et, au
   besoin, son NAME, sa SOL. et son Cust.V (nom, sol, custV), pour qu'elle
   soit le plan d'un contrat donné. Options : sans (des intitulés retirés),
   decalage, solNombre, custV. */
const ENTETE_COMPLET = ['NAME', 'SOL.', 'Cust.V', 'Int. V', 'ARCHIVE FILE PREFIX', 'VALIDITY PSN FULL', 'User Status', 'DIAGRAM TYPE', 'PRODUCT FAMILY',
  'Validated', '', '', 'FG1 TAGDESCRIPTION', 'DESCRIPTION', 'SCHEMA NUMBER', 'Released Date', 'Obsolete Date', 'Validated Date', 'REDRAW', '', 'ARCHIVED', '', 'CGM'];
function lignesSeeComplet(n, tri, options) {
  const o = options || {}, d = o.decalage || 0, sans = o.sans || [];
  const entete = ENTETE_COMPLET.filter(t => sans.indexOf(t) === -1);
  const lignes = [['Nommage WD BFLOW'], [], entete];
  for (let i = 0; i < n; i++) {
    const t = tri(i);
    const valeur = {
      'NAME': t.nom || nomDe(i + d), 'SOL.': t.sol || (o.solNombre ? { n: (i % 3) + 1, fmt: 'zeros5' } : String((i % 3) + 1).padStart(3, '0')),
      'Cust.V': t.custV || (o.custV ? o.custV(i) : ['A', 'B', 'C'][i % 3]), 'Int. V': String(i % 4), 'ARCHIVE FILE PREFIX': 'WD' + (100000 + i),
      'VALIDITY PSN FULL': t.psn, 'User Status': 'Released', 'DIAGRAM TYPE': t.type, 'PRODUCT FAMILY': 'HARNESS', 'Validated': { b: i % 2 === 0 },
      'FG1 TAGDESCRIPTION': 'WRNG RECEIVER', 'DESCRIPTION': 'Faisceau ' + i, 'SCHEMA NUMBER': 'SPE993A' + (4632001 + i),
      'Released Date': '22/07/2026', 'Obsolete Date': '', 'Validated Date': '24/07/2026', 'REDRAW': 'non', 'ARCHIVED': 'non', 'CGM': ''
    };
    lignes.push(entete.map(k => k ? valeur[k] : ''));
  }
  return lignes;
}
const seeComplet = (n, tri, options) => xlsx({ onglets: [{ nom: 'Nommage', lignes: lignesSeeComplet(n, tri, options) }] });
/* Le même, en CSV « ; » (un .xls d'Excel enregistré en CSV). */
function csvSeeComplet(n, tri, options) {
  return lignesSeeComplet(n, tri, options).map(l => l.map(v => v && typeof v === 'object' ? (v.b !== undefined ? (v.b ? 'VRAI' : 'FAUX') : String(v.n)) : String(v === undefined || v === null ? '' : v))
    .map(v => /[;"\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v).join(';')).join('\r\n') + '\r\n';
}

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
   contrat, d'un classeur vide). serveur() la remet, telle que livrée.
   `proprietes` : les propriétés du classeur au départ (un PSN déjà tapé). */
const LIVREE = (function () {
  const g = feuilleGates(3);
  const ctx = chargerServeur(new Classeur([new Feuille('HDK', g.valeurs, false, g.fusions)]), {});
  return { fwd: vm.runInContext('CONFIG.COLONNE_FWD', ctx), concept: vm.runInContext('CONFIG.COLONNE_CONCEPT', ctx) };
})();
function serveur(c, proprietes) {
  const ctx = chargerServeur(c, proprietes || {});
  vm.runInContext('CONFIG.COLONNE_FWD = ' + JSON.stringify(LIVREE.fwd) + '; CONFIG.COLONNE_CONCEPT = ' + JSON.stringify(LIVREE.concept) + ';', ctx);
  return ctx;
}
/* Les PSN déjà tapés dans la fenêtre, comme le classeur les garde. */
const psnGardes = parContrat => ({ SUIVI_FWD_PSN: JSON.stringify(parContrat) });
const semaineDe = (ctx, decalageJours) => ctx.numeroSemaineISO(new Date(Date.now() - (decalageJours || 0) * 864e5));
const MARQUE = 'Trié à l’import : ';

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
  async function fenetre(ctx, modifier, options) {
    ctx.__dialogue = null;
    ctx.importerSecondeBase();
    let html = ctx.__dialogue.getContent();
    if (modifier) html = modifier(html);
    const fichierHtml = path.join(dossier, 'fenetre-' + Math.random().toString(36).slice(2) + '.html');
    fs.writeFileSync(fichierHtml, html);
    const page = await nav.newPage(options || {});
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
  /* Ce que montre chaque case : son identifiant (« g:HDK », « see », « n7 »
     pour un contrat ajouté), son état, son fichier, ce qui en a été lu, sa
     cible, son avertissement, son résultat ; pour la case SEE, ce qui manque
     au fichier, la case « importer sans ce tri », les lignes gardées en
     mémoire, et une ligne par contrat (son PSN, sa part). */
  function cases(page) {
    return page.evaluate(() => Array.prototype.map.call(document.querySelectorAll('.case'), el => {
      const q = s => el.querySelector(s), vu = s => q(s) && !q(s).hidden ? q(s).textContent : '';
      return {
        id: el.getAttribute('data-case'), etat: el.getAttribute('data-etat'), etiquette: q('.etiquette').textContent,
        fichier: q('.fichier-nom').textContent, date: q('.date').textContent, lu: vu('.lu'), cible: vu('.cible'), note: vu('.note'),
        resultat: vu('.resultat'), nom: q('.nom') ? q('.nom').value : null, verifNom: vu('.verif-nom'), manque: vu('.manque'),
        sansTri: q('.sans-tri input') ? { coche: q('.sans-tri input').checked, possible: !q('.sans-tri input').disabled } : null,
        gardees: el.getAttribute('data-gardees'), retirer: !q('.retirer').hidden,
        porteurs: Array.prototype.map.call(el.querySelectorAll('.porteur'), li => ({
          contrat: li.getAttribute('data-contrat'), psn: li.querySelector('input') ? li.querySelector('input').value : null,
          enr: li.querySelector('.enr') ? li.querySelector('.enr').textContent : '', part: li.querySelector('.part').textContent,
          lignes: li.getAttribute('data-lignes') }))
      };
    }));
  }
  async function laCase(page, id) { return (await cases(page)).filter(k => k.id === id)[0]; }
  const porteur = (k, contrat) => (k.porteurs || []).filter(p => p.contrat === contrat)[0] || {};
  function fenetreEtat(page) {
    return page.evaluate(() => ({
      desactive: document.getElementById('importer').disabled,
      blocage: document.getElementById('blocage').textContent,
      etat: document.getElementById('etat').textContent,
      archiverVisible: !document.getElementById('option-archiver').hidden,
      archiverCoche: document.getElementById('archiver').checked,
      archiverTexte: document.getElementById('option-archiver').textContent,
      n: Array.prototype.filter.call(document.querySelectorAll('.case'), el => el.querySelector('.fichier-nom').textContent).length,
      cases: Array.prototype.map.call(document.querySelectorAll('.case'), el => el.getAttribute('data-case'))
    }));
  }
  /* Chaque fichier posé lu (ou en erreur), chaque nom vérifié, chaque PSN enregistré. */
  async function attendreLecture(page) {
    await page.waitForFunction(() => Array.prototype.every.call(document.querySelectorAll('.case'),
      el => /^(vide|lu|erreur|fait|echec)$/.test(el.getAttribute('data-etat') || '') && !el.hasAttribute('data-occupe')), null, { timeout: 120000 });
  }
  /* Pose des fichiers dans une case : choisis (setInputFiles), ou lâchés sur
     elle quand il y en a plusieurs ou qu'une date est voulue (la date d'un
     fichier, setInputFiles ne sait pas la poser). Rend la case une fois lue. */
  async function poser(page, id, fichiers) {
    const sel = '[data-case="' + id + '"]';
    if (fichiers.length > 1 || fichiers.some(f => f.date)) {
      await page.evaluate(([s, liste]) => {
        const dt = new DataTransfer();
        liste.forEach(f => {
          const bin = atob(f.b64), u = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
          dt.items.add(new File([u], f.nom, f.date ? { lastModified: f.date } : {}));
        });
        document.querySelector(s).dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
      }, [sel, fichiers.map(f => ({ nom: f.nom, b64: Buffer.from(f.contenu).toString('base64'), date: f.date || 0 }))]);
    } else {
      /* Playwright ne passe pas un tampon de plus de 50 Mo : un gros fichier part d'un fichier sur le disque, à son nom. */
      const f = fichiers[0];
      let source = { name: f.nom, mimeType: 'application/octet-stream', buffer: f.contenu };
      if (f.contenu.length >= 40 * 1048576) {
        const sous = fs.mkdtempSync(path.join(dossier, 'gros-'));
        fs.writeFileSync(path.join(sous, f.nom), f.contenu);
        source = path.join(sous, f.nom);
      }
      await page.setInputFiles(sel + ' input[type=file]', [source]);
    }
    await attendreLecture(page);
    return laCase(page, id);
  }
  /* « Ajouter un contrat… » : la nouvelle case, son nom tapé (et vérifié), son fichier posé au besoin. */
  async function ajouterContrat(page, nom, fichier) {
    await page.click('#ajouter');
    const id = await page.evaluate(() => { const l = document.querySelectorAll('.case.nouvelle'); return l[l.length - 1].getAttribute('data-case'); });
    if (nom !== undefined) { await page.fill('[data-case="' + id + '"] .nom', nom); await attendreLecture(page); }
    if (fichier) await poser(page, id, [fichier]);
    return id;
  }
  /* Le PSN d'un contrat tapé dans la case SEE, puis enregistré. */
  async function taperPsn(page, contrat, valeur) {
    await page.fill('[data-case="see"] .porteur[data-contrat="' + contrat + '"] input', valeur);
    await attendreLecture(page);
    return laCase(page, 'see');
  }
  /* Une capture de la fenêtre, si CAPTURES nomme un dossier (pour la relecture à l'œil). */
  async function capture(page, nom) {
    if (!process.env.CAPTURES) return;
    await page.setViewportSize({ width: 760, height: 1000 });
    await page.screenshot({ path: path.join(process.env.CAPTURES, nom + '.png'), fullPage: true });
  }
  /* Les fichiers posés retirés de leur case (ceux d'un import fini restent : un nouveau fichier les remplace). */
  async function vider(page) {
    let bouton;
    while ((bouton = await page.$('.case .retirer:not([hidden])'))) await bouton.click();
  }
  async function attendreFin(page, delai) {
    /* La fin : le bilan affiché, et la fenêtre rendue (la liste des contrats relue). */
    await page.waitForFunction(() => /\bok\b|erreur/.test(document.getElementById('etat').className) && !document.getElementById('fermer').disabled, null, { timeout: delai || 120000 });
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
  /* Un fichier seul, dans sa case — la case SEE par défaut, celle d'un
     contrat avec `case: 'HDK'` : les cases vidées, la case « toutes »
     posée, le fichier lu ; un fichier qui ne se lit pas rend l'erreur de sa
     case, sans rien envoyer. Les extracts SEE des essais de lecture n'ont ni
     VALIDITY PSN FULL ni DIAGRAM TYPE : « importer sans ce tri » est coché
     pour eux, sauf `sansTri: false`. `psn` : { contrat: valeur } tapés avant
     d'importer. */
  async function importer(page, nom, contenu, options) {
    const opt = options || {}, id = opt.case ? (opt.case === 'see' ? 'see' : 'g:' + opt.case) : 'see';
    await vider(page);
    if (await page.$('#toutes')) {
      if (opt.toutes) { if (!(await page.isChecked('#toutes'))) await page.check('#toutes'); }
      else if (await page.isChecked('#toutes')) await page.uncheck('#toutes');
    }
    let k = await poser(page, id, [{ nom, contenu }]);
    if (k.etat === 'erreur') return { etat: { classe: 'erreur', texte: k.lu }, case: k };
    for (const contrat of Object.keys(opt.psn || {})) k = await taperPsn(page, contrat, opt.psn[contrat]);
    if (id === 'see' && opt.sansTri !== false && k.manque && k.sansTri.possible && !k.sansTri.coche) {
      await page.check('[data-case="see"] .sans-tri input');
      k = await laCase(page, id);
    }
    if (opt.sansArchiver && await page.isVisible('#option-archiver')) await page.uncheck('#archiver');
    const etat = await lancer(page, opt.delai);
    return { etat, duree: etat.duree, case: k };
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
      'importVerifierNouveauContrat', 'importArchiverReleve', 'importContrats', 'importEnregistrerPsn'];
    const refus = fonctions.map(n => {
      try { ctx[n]('faux-jeton-123', 'HDK', 3, 5); return n + ':passe'; } catch (e) { return /Geste refusé/.test(e.message) ? '' : n + ':' + e.message; }
    }).filter(Boolean);
    verifier('hors du classeur (la page du tableau de bord), sans le jeton de la fenêtre, chaque fonction de l’import est refusée — vérifier un nom, archiver, relire les contrats, garder un PSN compris',
      !refus.length, refus.join(' | '));
    verifier('la fenêtre ne devine plus rien : la fonction qui rapprochait un échantillon SEE des contrats n’existe plus (débrief 21)',
      typeof ctx.importDevinerContratSEE === 'undefined' && !/importDevinerContratSEE|echantillonSee|NOUVEAU = /.test(fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8')));
    /* google.script.run atteint toute fonction dont le nom ne finit pas par
       « _ » : celle qui donne le jeton doit en porter un, sinon la page
       se le fait donner (chasse du débrief 20). */
    const code = fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8');
    const publiques = ['ouvrirJetonImport', 'gesteImport', 'parametresImport', 'psnEnregistres'].filter(n => new RegExp('function ' + n + '\\s*\\(').test(code));
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
    let psn = '';
    try { psn = JSON.stringify(ctx.importEnregistrerPsn(jeton, 'hdk', ' 4530 ; 4531 ')); } catch (e) { psn = e.message; }
    verifier('avec le jeton, un PSN se garde pour un contrat, sans l’interface : « 4530 ; 4531 » donne deux PSN, rangés sous le nom de l’onglet',
      psn === JSON.stringify({ ok: true, contrat: 'HDK', psn: ['4530', '4531'], source: 'fenetre' }) &&
      ctx.__proprietes.SUIVI_FWD_PSN === JSON.stringify({ HDK: ['4530', '4531'] }), psn);
    ctx.__sansInterface = false;
    let arbitraire = '';
    try { ctx.importSecondeBaseLot(jeton, 'HDK', 1, [['écrasé']]); } catch (e) { arbitraire = e.message; }
    verifier('un lot ne s’écrit que dans l’onglet temporaire d’un import, jamais dans un autre (« HDK »)',
      /non reconnu/.test(arbitraire) && c.getSheetByName('HDK').valeurs[0][0] !== 'écrasé', arbitraire);
    ajouterOnglet(c, new Feuille('HDK (ancien abc123)', [['gardé']]));
    let ancien = '';
    try { ctx.importSecondeBaseLot(jeton, 'HDK (ancien abc123)', 1, [['écrasé']]); } catch (e) { ancien = e.message; }
    verifier('ni dans l’ancien onglet mis de côté pendant un échange (« … (ancien …) »)', /non reconnu/.test(ancien) && c.getSheetByName('HDK (ancien abc123)').valeurs[0][0] === 'gardé', ancien);
    let inconnu = '';
    try { ctx.importEnregistrerPsn(jeton, 'NEO', '4610'); } catch (e) { inconnu = e.message; }
    verifier('un PSN pour un contrat qui n’existe pas : refusé, rien n’est gardé', /Contrat introuvable : « NEO »/.test(inconnu) && !/NEO/.test(ctx.__proprietes.SUIVI_FWD_PSN), inconnu);
  }

  // =================================================================
  section('Un extract SEE en .xlsx : trié, seules la ligne du tri, l’en-tête et NAME, SOL., Cust.V vont au classeur');
  {
    const ancien = new Feuille('SEE HDK', [['vieux'], ['NAME', 'SOL.', 'Cust.V'], ['OLD1', '1', 'A']]);
    const c = classeur({ ths: true, autres: [ancien, new Feuille('Notes', [['x']])] });
    const ctx = chargerServeur(c, {});
    ctx.__activerCache();
    const avant = ctx.getDonneesPourClient('HDK');
    const place = nomsOnglets(c).indexOf('SEE HDK');
    const page = await fenetre(ctx);
    const vide = await fenetreEtat(page);
    const videCases = await cases(page);
    const n = 1500;
    /* 1 500 lignes pour HDK (4530, WD), 300 écartées par DIAGRAM TYPE (PH), 200 d'un autre porteur (4610, WD). */
    const tri = i => i < n ? { psn: '4520,4530', type: 'WD' } : i < n + 300 ? { psn: '4530', type: 'PH' } : { psn: '4610', type: 'WD' };
    /* Pendant l'envoi : « Fermer » éteint, la consigne affichée, la largeur de l'onglet temporaire mesurée. */
    const vrai = ctx.importSecondeBaseLot;
    const mesures = [];
    ctx.importSecondeBaseLot = function (j, nom) { const f = c.getSheetByName(nom); mesures.push(f.getMaxColumns() + '×' + f.getMaxRows()); return vrai.apply(null, arguments); };
    page.__retard = 400;
    const ui = await poser(page, 'see', [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeComplet(n + 500, tri, { solNombre: true }) }]);
    verifier('la fenêtre attend des fichiers (« Importer » éteint) : une case par contrat, « GATES HDK » et « GATES THS », et la case SEE ; le PSN de HDK est celui de la configuration, THS n’en a pas',
      vide.desactive && vide.n === 0 && vide.cases.join() === 'g:HDK,g:THS,see' && videCases[0].etiquette === 'GATES HDK' && videCases[2].etiquette === 'SEE' &&
      porteur(videCases[2], 'HDK').psn === '4530' && /de la configuration/.test(porteur(videCases[2], 'HDK').enr) && porteur(videCases[2], 'THS').psn === '',
      JSON.stringify([vide, videCases[2]]));
    verifier('l’extract posé dans sa case est lu tout de suite et trié pendant la lecture : 2 000 lignes lues, 1 700 en WD gardées en mémoire — pas les 300 PH',
      ui.etat === 'lu' && /^2 000 lignes lues, 1 700 en WD \(DIAGRAM TYPE WD\), colonnes NAME, SOL\., Cust\.V · lu en \d+ s$/.test(ui.lu) && ui.gardees === '1700',
      JSON.stringify(ui));
    verifier('une ligne par contrat : HDK, PSN 4530 — 1 500 lignes WD, et l’onglet qu’elles remplaceront ; THS, sans PSN — pas de base, dit en clair',
      porteur(ui, 'HDK').part === '— 1 500 lignes WD → remplacera « SEE HDK »' && porteur(ui, 'HDK').lignes === '1500' &&
      porteur(ui, 'THS').part === ': pas de base SEE tant que le PSN n’est pas donné', JSON.stringify(ui.porteurs));
    await page.click('#importer');
    await page.waitForFunction(() => /Envoi au classeur|Préparation/.test(document.getElementById('progres').textContent), null, { timeout: 30000 });
    const pendant = await page.evaluate(() => ({ fermer: document.getElementById('fermer').disabled, consigne: !document.getElementById('consigne').hidden,
      lu: document.querySelector('[data-case="see"] .lu').textContent, retirer: !!document.querySelector('.case .retirer:not([hidden])'),
      choisir: !!document.querySelector('.case .choisir:not([hidden])'), psn: document.querySelector('[data-case="see"] .porteur input').disabled,
      progres: document.getElementById('progres').textContent }));
    const r = { etat: await attendreFin(page) };
    ctx.importSecondeBaseLot = vrai;
    verifier('pendant l’envoi, « Fermer » est éteint, « Ne pas fermer cette fenêtre avant la fin » s’affiche, ce qui a été lu reste dit, la base visée est nommée, et rien ne se pose, ne se retire ni ne se tape',
      pendant.fermer && pendant.consigne && /1 700 en WD/.test(pendant.lu) && !pendant.retirer && !pendant.choisir && pendant.psn &&
      /« SEE HDK »/.test(pendant.progres), JSON.stringify(pendant));
    verifier('l’onglet temporaire est taillé d’avance : trois colonnes, les 1 502 lignes (la ligne du tri, l’en-tête, les 1 500) — pas les 26 colonnes d’un onglet neuf',
      mesures.length && mesures.every(x => x === '3×1502'), mesures.join(', '));
    const f = c.getSheetByName('SEE HDK');
    verifier('l’import réussit et le dit, une ligne par base : « SEE HDK », 1 500 lignes, triée sur PSN 4530 · WD ; THS sans PSN, « SEE THS » pas touché',
      /\bok\b/.test(r.etat.classe) && /✓ « Nommage WD BFLOW\.xlsx » → 1 500 lignes dans l’onglet « SEE HDK » \(3 colonnes ; PSN 4530 · WD\) : la comparaison est prête\./.test(r.etat.texte) &&
      /– « THS » : pas de PSN, pas de base SEE — « SEE THS » n’est pas touché\./.test(r.etat.texte) && /Rouvrir le tableau de bord/.test(r.etat.texte), r.etat.texte);
    verifier('l’onglet « SEE HDK » : la ligne « Trié à l’import » (le tri, les lignes gardées sur celles du fichier, le fichier, le jour), l’en-tête, puis les ' + n + ' lignes, trois colonnes seulement',
      !!f && f.valeurs.length === n + 2 && f.valeurs[0][0].indexOf(MARQUE + 'PSN 4530 · DIAGRAM TYPE = WD — 1 500 lignes gardées sur 2 000 · « Nommage WD BFLOW.xlsx », le ') === 0 &&
      f.valeurs[1].join('|') === 'NAME|SOL.|Cust.V' && f.valeurs.every(l => l.length === 3), f && JSON.stringify([f.valeurs.length, f.valeurs[0], f.valeurs[1], f.valeurs[2]]));
    verifier('un nombre au format « 00000 » garde ses zéros (SOL. 1 → 00001), en texte', f.valeurs[2][1] === '00001' && f.formats[0] === '@', JSON.stringify(f.valeurs[2]));
    verifier('l’ancien onglet est remplacé, à sa place ; aucun onglet temporaire ni « ancien » ne traîne',
      nomsOnglets(c).indexOf('SEE HDK') === place && sansImport(c) && f.valeurs[2][0] !== 'OLD1', nomsOnglets(c).join(', '));
    verifier('la grille est resserrée sur les données', f.getMaxRows() === n + 2 && f.getMaxColumns() === 3, f.getMaxRows() + ' × ' + f.getMaxColumns());
    const lu = ctx.lireSecondeBase(c, 'HDK');
    verifier('la page relit la base : l’en-tête en ligne 2, sous la ligne du tri, ' + n + ' lignes, et le tri noté à l’import — « PSN 4530 · WD », pour la page',
      lu.etat === 'ok' && lu.ligneEntete === 2 && lu.rapprochement.lignes.length === n && lu.rapprochement.filtre === 'PSN 4530 · WD' &&
      lu.tri.source === 'import' && lu.tri.lues === 2000 && lu.tri.gardees === n, JSON.stringify([lu.etat, lu.ligneEntete, lu.tri, lu.rapprochement && lu.rapprochement.filtre]));
    const apres = ctx.getDonneesPourClient('HDK');
    verifier('le paquet du tableau de bord, en cache avant l’import, est renouvelé : il porte la nouvelle base, et son filtre',
      avant.rapprochement.lignes.length === 1 && apres.rapprochement.lignes.length === n && apres.rapprochement.filtre === 'PSN 4530 · WD',
      avant.rapprochement.lignes.length + ' → ' + apres.rapprochement.lignes.length);
    verifier('THS reste sans base, intact', !c.getSheetByName('SEE THS') && !!c.getSheetByName('THS'));
    verifier('la fenêtre n’a appelé que les gestes prévus, en ordre : le début, les lots, la fin, puis la liste des contrats relue — rien pour deviner',
      page.__appels[0] === 'importSecondeBaseDebut' && page.__appels[page.__appels.length - 2] === 'importSecondeBaseFin' &&
      page.__appels[page.__appels.length - 1] === 'importContrats' && page.__appels.slice(1, -2).every(x => x === 'importSecondeBaseLot'), page.__appels.join(','));
    const apresImport = await laCase(page, 'see');
    verifier('la case SEE dit son résultat, base par base, et le fichier ne se retire plus (un autre, choisi, le remplacerait)',
      apresImport.etat === 'fait' && /1 500 lignes dans l’onglet « SEE HDK »/.test(apresImport.resultat) && /« THS » : pas de PSN/.test(apresImport.resultat) &&
      !apresImport.retirer, JSON.stringify(apresImport));
    /* Le même nombre de lignes, d'autres indices : le cache ne sert pas l'ancienne base. */
    page.__retard = 0;
    const r2 = await importer(page, 'see.xlsx', seeComplet(n + 500, tri, { custV: () => 'Z' }), { sansTri: false });
    const apres2 = ctx.getDonneesPourClient('HDK');
    verifier('réimporté avec le même nombre de lignes (indices changés) : le paquet en cache suit ; le nouveau fichier remplace le premier dans la case',
      /\bok\b/.test(r2.etat.classe) && apres2.rapprochement.lignes[0]['Cust.V'] === 'Z' && (await fenetreEtat(page)).n === 1, JSON.stringify(apres2.rapprochement.lignes[0]));
    await page.close();
  }

  // =================================================================
  section('L’onglet créé, et un onglet « HDK SEE »');
  {
    const seul = classeur();
    const ctxSeul = chargerServeur(seul, {});
    let page = await fenetre(ctxSeul);
    const l = await poser(page, 'see', [{ nom: 'see.xlsx', contenu: seeComplet(10, () => ({ psn: '4530', type: 'WD' })) }]);
    const r = { etat: await lancer(page) };
    verifier('un seul contrat, sans base : l’onglet créé est « SEE HDK », le nom du contrat — jamais « SEE » tout court',
      porteur(l, 'HDK').part === '— 10 lignes WD → créera « SEE HDK »' && /\bok\b/.test(r.etat.classe) && !!seul.getSheetByName('SEE HDK') && !seul.getSheetByName('SEE') &&
      nomsOnglets(seul)[nomsOnglets(seul).length - 1] === 'SEE HDK', JSON.stringify(l.porteurs) + ' / ' + nomsOnglets(seul).join(', '));
    verifier('rien à deviner, rien à demander au serveur avant : le début, le lot, la fin, la liste relue',
      page.__appels.join() === 'importSecondeBaseDebut,importSecondeBaseLot,importSecondeBaseFin,importContrats', page.__appels.join());
    await page.close();

    const inverse = classeur({ ths: true, autres: [new Feuille('HDK SEE', [['NAME', 'SOL.', 'Cust.V'], ['OLD', '1', 'A']])] });
    const ctxInv = chargerServeur(inverse, {});
    page = await fenetre(ctxInv);
    const r2 = await importer(page, 'see.xlsx', seeComplet(40, i => ({ psn: i < 30 ? '4530' : '4610', type: 'WD' })), { sansTri: false });
    verifier('une base nommée « HDK SEE » (écriture admise) est remplacée sous ce nom, sans onglet qui traîne',
      /\bok\b/.test(r2.etat.classe) && inverse.getSheetByName('HDK SEE').valeurs.length === 32 && sansImport(inverse) && !inverse.getSheetByName('SEE HDK'),
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
      f && f.valeurs[1].slice(4, 9).join('|') === '25 %|1 234,50 €|1 234 567|1,23E+04|008' &&
      f.valeurs[2].slice(4, 9).join('|') === '12,34 %|3,00|1E+21|1E-07|042', JSON.stringify(f && [f.valeurs[1].slice(4), f.valeurs[2].slice(4)]));
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
    const relu = await laCase(page, 'see');
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
    /* La case cochée PENDANT la lecture d'un gros fichier : la case est en
       cours de lecture au moment du clic — le changement de la case ne la
       relit pas d'elle-même —, c'est la fin de sa lecture qui la relit. */
    page = await fenetre(ctx);
    await page.setInputFiles('[data-case="see"] input[type=file]', [{ name: 'gros.xlsx', mimeType: 'application/octet-stream', buffer: seeXlsx(50000) }]);
    const pendant = await page.evaluate(() => new Promise(ok => {
      const t0 = Date.now();
      (function voir() {
        const e = document.querySelector('[data-case="see"]').getAttribute('data-etat');
        if (e === 'lecture') { document.getElementById('toutes').click(); ok(true); return; }
        if ((e && e !== 'attente' && e !== 'vide') || Date.now() - t0 > 30000) { ok(false); return; }
        setTimeout(voir, 2);
      })();
    }));
    await attendreLecture(page);
    const reLu = await laCase(page, 'see');
    await page.check('[data-case="see"] .sans-tri input');
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
    const ui = await poser(page, 'see', [{ nom: 'multi.xlsx', contenu: fichier }]);
    const attente = await fenetreEtat(page);
    verifier('un seul contrat, un extract sans les colonnes du tri : la case le dit, « Importer » attend « importer sans ce tri », et l’onglet « SEE » existant est la cible de tout l’extract',
      /n’a pas de colonne VALIDITY PSN FULL, ni de colonne DIAGRAM TYPE/.test(ui.manque) && ui.sansTri.possible && !ui.sansTri.coche &&
      porteur(ui, 'HDK').part === '— tout l’extract : 25 lignes → remplacera « SEE », une fois « importer sans ce tri » coché' &&
      attente.desactive && /cocher « importer sans ce tri » dans la case SEE, ou retirer le fichier/.test(attente.blocage), JSON.stringify([ui, attente.blocage]));
    await page.check('[data-case="see"] .sans-tri input');
    const r = { etat: await lancer(page) };
    const f = c.getSheetByName('SEE');
    verifier('l’en-tête est cherché onglet par onglet, les visibles d’abord : « Données » ; sans tri, pas de ligne « Trié à l’import »',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 26 && f.valeurs[0].join('|') === 'NAME|SOL.|Cust.V' && f.valeurs[1][0] === 'TFE311A0600',
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs.slice(0, 2)));
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
    const c = classeur();
    const ctx = chargerServeur(c, {});
    const page = await fenetre(ctx);
    const texte = 'Nommage WD BFLOW;;;\r\n;;;\r\nNAME;SOL.;Cust.V;Libellé\r\nTFE311A0600;001;A;"Faisceau ; « été »"\r\n"HAR253A0011";="002";="B";"ligne\r\ncoupée ""citée"""\r\n';
    let r = await importer(page, 'see.csv', Buffer.from(texte, 'latin1'), { toutes: true });
    let f = c.getSheetByName('SEE HDK');
    verifier('un CSV en Windows-1252 : « ; », guillemets doublés, retour à la ligne dans un champ, ="002" lu 002 — dans « SEE HDK » (créé, au bout)',
      /\bok\b/.test(r.etat.classe) && f && f.valeurs.length === 3 && f.valeurs[1].join('|') === 'TFE311A0600|001|A|Faisceau ; « été »' &&
      f.valeurs[2].join('|') === 'HAR253A0011|002|B|ligne\r\ncoupée "citée"' && nomsOnglets(c)[nomsOnglets(c).length - 1] === 'SEE HDK',
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    const virgules = 'NAME,SOL.,Cust.V,Poids\nTFE311A0600,001,A,"3,5"\nHAR253A0011,002,B,4\n';
    r = await importer(page, 'see.csv', Buffer.from(virgules, 'utf8'), { toutes: true });
    f = c.getSheetByName('SEE HDK');
    verifier('un CSV à virgules, la virgule décimale entre guillemets', /\bok\b/.test(r.etat.classe) && f.valeurs[1].join('|') === 'TFE311A0600|001|A|3,5', JSON.stringify(f.valeurs));
    const tabs = '﻿NAME\tSOL.\tCust.V\nTFE311A0600\t001\tA\n';
    r = await importer(page, 'see.txt', Buffer.concat([Buffer.from([0xFF, 0xFE]), Buffer.from(tabs.slice(1), 'utf16le')]));
    f = c.getSheetByName('SEE HDK');
    verifier('un « Texte Unicode » (UTF-16, tabulations)', /\bok\b/.test(r.etat.classe) && f.valeurs[1].join('|') === 'TFE311A0600|001|A', r.etat.texte);
    const tard = 'NAME;SOL.;Cust.V;Libelle\n' + Array.from({ length: 40000 }, (_, i) => nomDe(i) + ';001;A;texte').join('\n') + '\nHAR253A0011;002;B;Câble été\n';
    r = await importer(page, 'tard.csv', Buffer.from(tard, 'latin1'), { toutes: true });
    f = c.getSheetByName('SEE HDK');
    verifier('des accents Windows loin dans le fichier (après 1 Mo d’ASCII) : relu en Windows-1252, pas de « � »',
      /\bok\b/.test(r.etat.classe) && f.valeurs[f.valeurs.length - 1].join('|') === 'HAR253A0011|002|B|Câble été', r.etat.texte + ' ' + JSON.stringify(f.valeurs[f.valeurs.length - 1]));
    const html = '<html><head><meta charset="utf-8"></head><body><table><tr><td colspan="3"><b>Nommage WD BFLOW</b></td></tr><tr><td></td></tr>' +
      '<tr><th>NAME</th><th>SOL.</th><th>Cust.V</th><th>Libellé</th></tr><tr><td>TFE311A0600</td><td>001</td><td>A</td><td>Faisceau &amp; c&eacute;ble<br>bis</td></tr>' +
      '<TR><TD>HAR253A0011</TD><TD>002</TD><TD>B</TD><TD>&nbsp;</TD></TR></table></body></html>';
    r = await importer(page, 'Nommage WD BFLOW.xls', Buffer.from(html, 'utf8'), { toutes: true });
    f = c.getSheetByName('SEE HDK');
    verifier('un « Excel » qui est une page web (tableau HTML nommé .xls) : lu comme tel',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 3 && f.valeurs[1].join('|') === 'TFE311A0600|001|A|Faisceau & céble bis' && f.valeurs[2][0] === 'HAR253A0011',
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    const xml = '<?xml version="1.0"?><?mso-application progid="Excel.Sheet"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">' +
      '<Worksheet ss:Name="Infos"><Table><Row><Cell><Data ss:Type="String">Export</Data></Cell></Row></Table></Worksheet>' +
      '<Worksheet ss:Name="Nommage"><Table><Row><Cell ss:MergeAcross="2"><Data ss:Type="String">Nommage WD BFLOW</Data></Cell></Row><Row ss:Index="3"><Cell><Data ss:Type="String">NAME</Data></Cell>' +
      '<Cell><Data ss:Type="String">SOL.</Data></Cell><Cell><Data ss:Type="String">Cust.V</Data></Cell><Cell><Data ss:Type="String">Date</Data></Cell></Row>' +
      '<Row><Cell><Data ss:Type="String">TFE311A0600</Data></Cell><Cell><Data ss:Type="String">001</Data></Cell><Cell><Data ss:Type="String">A</Data></Cell><Cell><Data ss:Type="DateTime">2026-03-15T00:00:00.000</Data></Cell></Row>' +
      '<Row><Cell><Data ss:Type="String">HAR253A0011</Data></Cell><Cell ss:Index="3"><Data ss:Type="String">B</Data></Cell><Cell><Data ss:Type="Number">3.5</Data></Cell></Row></Table></Worksheet></Workbook>';
    r = await importer(page, 'see.xls', Buffer.from(xml, 'utf8'), { toutes: true });
    f = c.getSheetByName('SEE HDK');
    verifier('un « Excel » XML 2003 (deux onglets, l’en-tête dans le second, cellules indexées) : lu comme tel',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 3 && f.valeurs[1].join('|') === 'TFE311A0600|001|A|15/03/2026' && f.valeurs[2].join('|') === 'HAR253A0011||B|3,5',
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    /* Cent cinquante styles avant la première feuille (80 Ko), et un texte en CDATA. */
    const styles = '<Styles>' + Array.from({ length: 150 }, (_, i) => '<Style ss:ID="s' + i + '"><Alignment ss:Vertical="Bottom"/><Borders/><Font ss:FontName="Calibri" x:Family="Swiss" ss:Size="11" ss:Color="#000000"/>' +
      '<Interior/><NumberFormat/><Protection/>' + ' '.repeat(300) + '</Style>').join('') + '</Styles>';
    const xmlLourd = xml.replace('<Worksheet ss:Name="Infos">', styles + '<Worksheet ss:Name="Infos">')
      .replace('<Data ss:Type="String">HAR253A0011</Data>', '<Data ss:Type="String"><![CDATA[HAR253A0011 & <bis>]]></Data>');
    r = await importer(page, 'lourd.xls', Buffer.from(xmlLourd, 'utf8'), { toutes: true });
    f = c.getSheetByName('SEE HDK');
    verifier('un XML 2003 dont la première feuille arrive après 64 Ko de styles, un texte en CDATA : lus',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 3 && f.valeurs[2][0] === 'HAR253A0011 & <bis>', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    /* Tout entre guillemets, et une description pleine de « ; » dans un CSV à virgules. */
    const guillemets = '"SCHEMA NUMBER","NAME","SOL.","Cust.V","Description"\r\n"S1","TFE311A0600","001","A","P1; P2; P3; P4; P5; P6; P7"\r\n"S2","HAR253A0011","002","B","x"\r\n';
    r = await importer(page, 'see.csv', Buffer.from(guillemets, 'utf8'));
    f = c.getSheetByName('SEE HDK');
    verifier('un CSV tout entre guillemets, avec des « ; » dans une description : le bon séparateur',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 3 && f.valeurs[1].join('|') === 'TFE311A0600|001|A', r.etat.texte + ' ' + JSON.stringify(f && f.valeurs));
    /* L'extract de tous les porteurs en CSV : le tri se fait de même. */
    r = await importer(page, 'Nommage WD BFLOW.csv', Buffer.from(csvSeeComplet(30, i => ({ psn: i % 2 ? '4530, 4540' : '4610', type: i % 3 ? 'WD' : 'GH' })), 'utf8'),
      { sansTri: false });
    f = c.getSheetByName('SEE HDK');
    verifier('l’extract de tous les porteurs en CSV : trié comme le .xlsx — 10 lignes à HDK (4530, WD) sur 30',
      /\bok\b/.test(r.etat.classe) && f.valeurs.length === 12 && f.valeurs[0][0].indexOf(MARQUE + 'PSN 4530 · DIAGRAM TYPE = WD — 10 lignes gardées sur 30') === 0,
      r.etat.texte + ' ' + JSON.stringify(f && f.valeurs.slice(0, 3)));
    await page.close();
  }

  // =================================================================
  section('Ce qui ne marche pas le dit, juste, et ne touche à rien');
  {
    const ancien = new Feuille('SEE HDK', [['NAME', 'SOL.', 'Cust.V'], ['OLD', '1', 'A']]);
    const c = classeur({ autres: [ancien] });
    const ctx = chargerServeur(c, {});
    const avant = JSON.stringify(ancien.valeurs);
    let page = await fenetre(ctx);
    let r = await importer(page, 'autre.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: [['Titre'], ['REF', 'SOL.', 'Cust V'], ['X', '1', 'A']] }] }));
    verifier('ni GATES ni SEE (pas de NAME / SOL. / Cust.V) : la case le dit, nomme ce qui manque et la ligne la plus proche',
      /erreur/.test(r.etat.classe) && /Ni un export GATES ni un export SEE/.test(r.etat.texte) && /aucune ligne d’en-tête avec NAME, SOL\., Cust\.V/.test(r.etat.texte) &&
      /La ligne 2 de « S » en porte 1 sur 3 — il manque : NAME, Cust\.V/.test(r.etat.texte), r.etat.texte);
    verifier('et le classeur n’a pas bougé (aucun appel au serveur)', page.__appels.length === 0 && JSON.stringify(ancien.valeurs) === avant);
    const bloque = await fenetreEtat(page);
    verifier('« Importer » attend qu’on retire ce fichier — ou qu’on mette le bon dans la case —, et le dit', bloque.desactive &&
      /Retirer « autre\.xlsx » de la case « SEE », qui ne s’importe pas \(✗\) — ou y mettre le bon fichier\./.test(bloque.blocage), JSON.stringify(bloque));
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
    r = await importer(page, 'Nommage WD BFLOW.xlsx', FX.xls({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE311A0600', '001', 'A']] }] }));
    verifier('un vrai .xls nommé .xlsx (un export renommé) : lu comme un .xls', /\bok\b/.test(r.etat.classe) &&
      c.getSheetByName('SEE HDK').valeurs.map(l => l.join('|')).join(' / ') === 'NAME|SOL.|Cust.V / TFE311A0600|001|A', r.etat.texte);
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
    r = await importer(page, 'formules-tri.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V', 'VALIDITY PSN FULL', 'DIAGRAM TYPE'],
      ['TFE1', '001', 'A', '4530', { f: 'F2&"x"' }], ['TFE2', '002', 'B', '4530', 'WD']] }] }), { sansTri: false });
    verifier('DIAGRAM TYPE en formule sans valeur calculée, même sur une ligne qu’il écarterait : refusé — le tri lui-même serait faux',
      /erreur/.test(r.etat.classe) && /1 ligne\(s\) ont une formule sans valeur calculée dans NAME, SOL\., Cust\.V, VALIDITY PSN FULL, DIAGRAM TYPE/.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'vide.xlsx', xlsx({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE1', '001', { str: '' }], ['TFE2', '002', 'B']] }] }));
    verifier('une formule qui rend une chaîne vide (enregistrée par Excel) : une valeur vide, pas un refus',
      /\bok\b/.test(r.etat.classe) && c.getSheetByName('SEE HDK').valeurs.map(l => l.join('|')).join(' / ') === 'NAME|SOL.|Cust.V / TFE1|001| / TFE2|002|B', r.etat.texte);
    await page.close();

    /* Le serveur lâche une fois, au deuxième lot : le lot est renvoyé, l'import va au bout. */
    page = await fenetre(ctx, rapide);
    const vrai = ctx.importSecondeBaseLot;
    let lots = 0;
    ctx.importSecondeBaseLot = function () { lots++; if (lots === 2) throw new Error('Service Spreadsheets timed out while accessing document'); return vrai.apply(null, arguments); };
    r = await importer(page, 'see.xlsx', seeXlsx(200));
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
    r = await importer(page, 'see.xlsx', seeXlsx(200));
    ctx.importSecondeBaseLot = vrai;
    await page.waitForTimeout(300);
    verifier('une panne qui dure : trois essais, puis le message la dit et dit quoi faire, « SEE HDK » est intact, l’onglet temporaire est retiré',
      /erreur/.test(r.etat.classe) && lots === 4 && /Service Spreadsheets indisponible/.test(r.etat.texte) && /Relancer l’import/.test(r.etat.texte) &&
      /Rien n’a été remplacé/.test(r.etat.texte) && JSON.stringify(c.getSheetByName('SEE HDK').valeurs) === avant && sansImport(c), r.etat.texte + ' / ' + lots + ' / ' + nomsOnglets(c).join(', '));
    const echec = await laCase(page, 'see');
    verifier('la case SEE porte l’échec, en ✗, et le fichier peut être remplacé (« Changer… »)', echec.etat === 'echec' && /✗/.test(echec.resultat), JSON.stringify(echec));
    /* Un refus du serveur n'est pas renvoyé. */
    page.__appels = [];
    ctx.importSecondeBaseLot = function () { throw new Error('L’onglet d’import « x » a disparu (un autre import de ce contrat a-t-il été lancé ?) : relancer l’import.'); };
    r = await importer(page, 'see.xlsx', seeXlsx(20));
    ctx.importSecondeBaseLot = vrai;
    verifier('un refus du serveur (« a disparu ») : pas renvoyé', /erreur/.test(r.etat.classe) && page.__appels.filter(n => n === 'importSecondeBaseLot').length === 1, page.__appels.join());
    /* Relancé : il passe, en lots de 50 lignes exactement. */
    page.__appels = [];
    const tailles = [];
    ctx.importSecondeBaseLot = function (j, f, p, l) { tailles.push(l.length); return vrai.apply(null, arguments); };
    r = await importer(page, 'see.xlsx', seeXlsx(200));
    ctx.importSecondeBaseLot = vrai;
    verifier('relancé : il passe, en lots de 50 lignes', /\bok\b/.test(r.etat.classe) && c.getSheetByName('SEE HDK').valeurs.length === 201 && tailles.join() === '50,50,50,50,1',
      r.etat.texte + ' / ' + tailles.join());
    await page.close();

    /* La fin a tout fait, puis la réponse se perd : la fenêtre ne dit pas « rien n'a été remplacé ». */
    page = await fenetre(ctx);
    const vraiFin = ctx.importSecondeBaseFin;
    ctx.importSecondeBaseFin = function () { vraiFin.apply(null, arguments); throw new Error('NetworkError: Connection failure due to HTTP 0'); };
    r = await importer(page, 'see.xlsx', seeXlsx(120));
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
    const reste = ctx.importSecondeBaseDebut(jeton, 'HDK', 3, 10);
    ctx.importSecondeBaseLot(jeton, reste.feuille, 1, [['NAME', 'SOL.', 'Cust.V'], ['R', '1', 'A']]);
    const texteDiag = ctx.diagnostic();
    verifier('un import interrompu : le Diagnostic nomme son onglet temporaire', /reste d'un import interrompu/.test(texteDiag) && texteDiag.indexOf(reste.feuille) !== -1,
      texteDiag.split('\n').filter(l => /import/.test(l)).join(' / '));
    page = await fenetre(ctx);
    r = await importer(page, 'see.xlsx', seeXlsx(5));
    verifier('et le prochain import de cette base le retire', /\bok\b/.test(r.etat.classe) && sansImport(c) && c.getSheetByName('SEE HDK').valeurs.length === 6, nomsOnglets(c).join(', '));
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
      page.__appels.filter(x => x !== 'importContrats').join() === 'importSecondeBaseDebut' && sansImport(c) && !c.getSheetByName('SEE HDK'), r.etat.texte);
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
  section('Glisser chaque fichier sur sa case');
  {
    const c = classeur();
    const ctx = serveur(c);
    const page = await fenetre(ctx);
    const see = seeComplet(7, () => ({ psn: '4530', type: 'WD' })).toString('base64'), gat = xlsxGates(gates(40)).toString('base64');
    await page.evaluate(([s, g]) => {
      const fichier = (b, nom) => { const bin = atob(b), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new File([u], nom); };
      const lacher = (sel, f) => { const dt = new DataTransfer(); dt.items.add(f); document.querySelector(sel).dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); };
      lacher('[data-case="see"]', fichier(s, 'glisse.xlsx'));
      lacher('[data-case="g:HDK"]', fichier(g, 'export_48.xlsx'));
    }, [see, gat]);
    await attendreLecture(page);
    const lus = await cases(page);
    /* Lâché à côté des cases : rien n'est deviné, la fenêtre dit où le poser. */
    await page.evaluate(([g]) => {
      const bin = atob(g), u = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
      const dt = new DataTransfer();
      dt.items.add(new File([u], 'perdu.xlsx'));
      document.querySelector('.intro').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    }, [gat]);
    const aCote = await fenetreEtat(page);
    verifier('un fichier lâché à côté des cases n’est pas pris, et la fenêtre dit où le poser',
      /Déposer chaque fichier sur sa case : l’export GATES d’un contrat sur « GATES » suivi de son nom, l’extract SEE sur la case « SEE »/.test(aCote.etat) && aCote.n === 2,
      JSON.stringify(aCote));
    const etat = await lancer(page);
    verifier('des fichiers glissés sur leur case sont pris comme des fichiers choisis — les deux, chacun dans son onglet',
      lus.filter(k => k.id === 'see')[0].etat === 'lu' && lus.filter(k => k.id === 'g:HDK')[0].etat === 'lu' && /\bok\b/.test(etat.classe) &&
      c.getSheetByName('SEE HDK').valeurs.length === 9 && c.getSheetByName('HDK').valeurs.length === 43, JSON.stringify(lus.map(l => l.id + ' ' + l.lu)) + ' / ' + etat.texte);
    await page.close();
  }

  // =================================================================
  section('Chaque case vérifie la sorte de son fichier');
  {
    const c = classeur({ ths: true });
    const ctx = serveur(c);
    const P = parametres(ctx);
    verifier('la fenêtre reçoit les règles du serveur, pas une copie : les mots d’une ligne d’en-têtes d’export, ses deux nombres, les motifs de la colonne de référence',
      JSON.stringify(P.motsCles) === JSON.stringify(vm.runInContext('CONFIG.MOTS_CLES_ENTETE', ctx).map(ctx.normaliser)) && P.minIntitules === 10 && P.minMotsCles === 2 &&
      JSON.stringify(P.motifsReference) === JSON.stringify(vm.runInContext('MOTIFS_REFERENCE', ctx)) && P.lignesScan === 8,
      JSON.stringify([P.motsCles, P.minIntitules, P.minMotsCles, P.motifsReference]));
    verifier('… et le tri de l’extract SEE : la colonne des PSN, les filtres, la ligne qui le note — et plus rien pour deviner',
      P.colonnePsn === 'VALIDITY PSN FULL' && JSON.stringify(P.filtres) === JSON.stringify([{ colonne: 'DIAGRAM TYPE', valeurs: ['WD'] }]) &&
      JSON.stringify(P.psnConfig) === JSON.stringify({ hdk: ['4530'] }) && P.marqueTri === MARQUE && !('echantillonSee' in P) && !('choisi' in P) && !('maxFichiers' in P),
      JSON.stringify([P.colonnePsn, P.filtres, P.psnConfig, P.marqueTri]));
    verifier('et, pour chaque contrat — chaque case —, son PSN (d’où il vient) et les références de ses plans, normalisées',
      P.contrats.map(k => k.id + ':' + k.refs.length + ':' + k.psn.join('/') + ':' + k.psnSource).join() === 'HDK:40:4530:configuration,THS:30::' &&
      P.contrats[1].refs[0] === ctx.normaliser(c.getSheetByName('THS').valeurs[3][I_REF]), JSON.stringify(P.contrats.map(k => [k.id, k.refs.slice(0, 2), k.psn])));
    const page = await fenetre(ctx);
    await poser(page, 'g:HDK', [{ nom: 'export_48.xlsx', contenu: xlsxGates(gates(40)) }]);
    await poser(page, 'see', [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeComplet(12, () => ({ psn: '4530', type: 'WD' })) }]);
    await poser(page, 'g:THS', [{ nom: 'notes.xlsx', contenu: xlsx({ onglets: [{ nom: 'Notes', lignes: [['Réunion du 3'], ['rien à voir']] }] }) }]);
    let lus = await cases(page);
    verifier('chaque fichier est lu tout de suite dans sa case et dit ce qu’il est : GATES (plans, colonnes, ligne d’en-têtes, cellules fusionnées), SEE (lignes, tri), ni l’un ni l’autre (pourquoi)',
      lus[0].etat === 'lu' && /^40 plans · 138 colonnes · en-têtes en ligne 2 · 16 cellules fusionnées · lu en \d+ s$/.test(lus[0].lu) &&
      /^Remplacera l’onglet « HDK » — l’ancien ne s’en va qu’une fois tout reçu ; son historique est gardé\.$/.test(lus[0].cible) &&
      lus[2].etat === 'lu' && /^12 lignes lues, 12 en WD \(DIAGRAM TYPE WD\), colonnes NAME, SOL\., Cust\.V/.test(lus[2].lu) &&
      lus[1].etat === 'erreur' && /^✗ Ni un export GATES ni un export SEE/.test(lus[1].lu), JSON.stringify(lus));
    await poser(page, 'g:THS', [{ nom: 'photo.png', contenu: Buffer.from('png') }]);
    let ui = await fenetreEtat(page);
    lus = await cases(page);
    verifier('ce qui n’est pas un tableau (une photo) n’est pas lu : sa case le dit, et remplace le fichier d’avant',
      lus[1].etat === 'erreur' && lus[1].fichier === 'photo.png' && /« photo\.png » n’est pas un tableau \(\.xlsx, \.xls, \.csv ou page web\) : rien n’est lu\./.test(lus[1].lu), JSON.stringify(lus[1]));
    verifier('« Importer » attend qu’on retire le fichier qui ne s’importe pas, et dit lequel, dans quelle case',
      ui.desactive && /Retirer « photo\.png » de la case « GATES THS », qui ne s’importe pas/.test(ui.blocage), JSON.stringify(ui));
    verifier('la case « Archiver le relevé de la semaine Sxx pour les contrats importés » paraît avec un export GATES, cochée',
      ui.archiverVisible && ui.archiverCoche && new RegExp('Archiver le relevé de la semaine S' + parseInt(semaineDe(ctx).slice(6), 10) + ' pour les contrats importés').test(ui.archiverTexte), JSON.stringify(ui));
    await page.click('[data-case="g:THS"] .retirer');
    const apres = await fenetreEtat(page);
    verifier('le fichier retiré, la case redevient vide, et « Importer » s’allume', !apres.desactive && apres.n === 2 && (await laCase(page, 'g:THS')).etat === 'vide', JSON.stringify(apres));
    /* Le mauvais genre dans une case : dit, et la lecture s'arrête dès l'en-tête. */
    const seeDansGates = await poser(page, 'g:THS', [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeComplet(30000, () => ({ psn: '4530', type: 'WD' })) }]);
    verifier('un extract SEE posé dans une case GATES : « c’est un export SEE : le mettre dans la case SEE » — lu jusqu’à son en-tête seulement',
      seeDansGates.etat === 'erreur' && /^✗ C’est un export SEE \(« NAME », « SOL\. », « Cust\.V » en ligne 3 de « Nommage »\) : le mettre dans la case SEE, plus bas\.$/.test(seeDansGates.lu) &&
      /lu en|lignes/.test(seeDansGates.lu) === false, JSON.stringify(seeDansGates));
    const gatesDansSee = await poser(page, 'see', [{ nom: 'export_49.xlsx', contenu: xlsxGates(gates(30, { prefixe: 'THS' })) }]);
    verifier('un export GATES posé dans la case SEE : dit, et où le mettre',
      gatesDansSee.etat === 'erreur' && /^✗ C’est un export GATES \(ses en-têtes en ligne 2 de « Export »\) : le mettre dans la case de son contrat, « GATES … », plus haut\.$/.test(gatesDansSee.lu),
      JSON.stringify(gatesDansSee));
    ui = await fenetreEtat(page);
    verifier('deux cases en erreur : « Importer » attend, et le dit', ui.desactive && /2 cases portent un fichier qui ne s’importe pas/.test(ui.blocage), ui.blocage);
    verifier('rien n’a été envoyé au classeur pendant tout cela', page.__appels.length === 0, page.__appels.join());
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
    const r = await importer(page, 'export_48.xlsx', xlsxGates(g), { case: 'HDK', sansArchiver: true });
    const f = importe.getSheetByName('HDK');
    verifier('l’export posé dans la case « GATES HDK » est importé ; la case dit ce que la page y lit : plans, colonne suivie (groupe › intitulé), concept harnais',
      /\bok\b/.test(r.etat.classe) &&
      /✓ « export_48\.xlsx » → onglet « HDK » remplacé : 186 plans, colonne suivie HDK AA 011 › Avancement Définition Electrique, concept harnais lu\./.test(r.etat.texte) &&
      /186 plans, colonne suivie/.test((await laCase(page, 'g:HDK')).resultat), r.etat.texte);
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
    verifier('construireModele lit l’onglet importé comme l’onglet collé : mêmes colonnes, mêmes groupes, même colonne suivie, mêmes plans',
      JSON.stringify(ctx.construireModele('HDK')) === JSON.stringify(ctxColle.construireModele('HDK')));
    verifier('getDonneesPourClient : le même paquet pour la page', paquetSansDate(ctx.getDonneesPourClient('HDK')) === paquetSansDate(ctxColle.getDonneesPourClient('HDK')));
    verifier('compterAvancements : le même relevé, plan par plan', JSON.stringify(ctx.compterAvancements('HDK')) === JSON.stringify(ctxColle.compterAvancements('HDK')));
    verifier('l’onglet garde sa place et son nom ; aucun onglet temporaire ni « ancien » ne traîne ; la base SEE n’est pas touchée',
      nomsOnglets(importe).indexOf('HDK') === place && sansImport(importe) && importe.getSheetByName('SEE HDK').valeurs[1][0] === 'X', nomsOnglets(importe).join(', '));
    verifier('l’historique, rangé sous le nom de l’onglet, est intact (case « Archiver » décochée) et se lit toujours',
      JSON.stringify(importe.getSheetByName('Historique_FWD_HDK').valeurs) === histoAvant && ctx.getHistorique(importe, 'HDK').length === 1);
    verifier('la fenêtre n’a appelé que le début, les lots et la fin — rien à deviner, pas d’archivage',
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
    let r = await importer(page, 'export.xls', Buffer.from(htmlGates(g, 'Export GATES du 01/10/2026'), 'utf8'), { case: 'HDK', sansArchiver: true });
    let f = c.getSheetByName('HDK');
    const titre = ['Export GATES du 01/10/2026'].concat(new Array(137).fill(''));
    verifier('une page web nommée .xls — un titre au-dessus (colspan, sur les 138 colonnes), les groupes (colspan), une cellule sur deux lignes (rowspan) : les lignes à leur place, les dix-huit fusions recréées, le titre sur toute la largeur, la colonne suivie trouvée',
      /\bok\b/.test(r.etat.classe) && JSON.stringify(f.valeurs) === JSON.stringify([titre].concat(g.valeurs)) && f.fusions.length === 18 &&
      f.fusions.some(x => x.ligne === 2 && x.col === 1 && x.haut === 2) && f.fusions.some(x => x.ligne === 1 && x.col === 1 && x.larg === 138 && x.haut === 1) &&
      /colonne suivie HDK AA 011 › Avancement Définition Electrique/.test(r.etat.texte),
      r.etat.texte + ' ' + f.fusions.length + ' ' + JSON.stringify(f.valeurs[2] && f.valeurs[2].slice(0, 4)));
    r = await importer(page, 'export2.xls', Buffer.from(xml2003Gates(g), 'utf8'), { case: 'HDK', sansArchiver: true });
    f = c.getSheetByName('HDK');
    verifier('un XML 2003 nommé .xls (ss:MergeAcross, ss:Index) : les seize fusions recréées, les lignes à leur place, la colonne suivie trouvée',
      /\bok\b/.test(r.etat.classe) && f.fusions.length === 16 && JSON.stringify(f.valeurs) === JSON.stringify(g.valeurs) && /colonne suivie HDK AA 011/.test(r.etat.texte), r.etat.texte);
    /* Des milliers de fusions dans les plans, écrites AVANT celles de la ligne des groupes. */
    const bruit = Array.from({ length: 6000 }, (_, i) => ({ ligne: 4 + Math.floor(i / 60), col: 1 + (i % 60) * 2, larg: 2 }));
    r = await importer(page, 'export3.xlsx', xlsx({ onglets: [{ nom: 'Export', lignes: g.valeurs.map(l => l.slice()),
      fusions: bruit.concat(g.fusions.map(x => ({ ligne: x.ligne, col: x.col, larg: x.larg }))) }] }), { case: 'HDK', sansArchiver: true });
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
      const r = await importer(page, nom, contenu, { case: 'HDK', sansArchiver: true });
      lus[nom] = { r, f: c.getSheetByName('HDK'), ctx, appels: page.__appels.slice() };
      await page.close();
    }
    const x = lus['export_48.xlsx'], l = lus['export_48.xls'], w = lus['export_xlwt.xls'];
    verifier('le .xls écrit par LibreOffice est lu dans la case « GATES HDK », et elle dit ce qu’elle dit du .xlsx : 186 plans · 138 colonnes · en-têtes en ligne 2 · 16 cellules fusionnées',
      /^186 plans · 138 colonnes · en-têtes en ligne 2 · 16 cellules fusionnées · lu en \d+ s$/.test(l.r.case.lu) &&
      l.r.case.lu.replace(/lu en \d+ s/, '') === x.r.case.lu.replace(/lu en \d+ s/, ''), JSON.stringify([l.r.case.lu, x.r.case.lu]));
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
        verifier('la case du .xls dit la même chose que celle du .xlsx : 3 200 lignes, colonnes NAME, SOL., Cust.V', /^3\u202f200 lignes, colonnes NAME, SOL\., Cust\.V/.test(l.r.case.lu) &&
          l.r.case.lu.replace(/lu en \d+ s/, '') === x.r.case.lu.replace(/lu en \d+ s/, ''), l.r.case.lu);
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
      const r = await importer(page, k.fichier, lireXls(k.fichier), k.gates ? { case: 'HDK', sansArchiver: true } : { toutes: true });
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
    /* L'extract de tous les porteurs en vrai .xls : trié pendant la lecture, comme un .xlsx. */
    r = await importer(page, 'Nommage WD BFLOW.xls', FX.xls({ onglets: [{ nom: 'Nommage', lignes: lignesSeeComplet(40, i => ({ psn: i % 4 ? '4520,4530' : '14530', type: i % 5 ? 'WD' : 'PH' })) }] }),
      { sansTri: false });
    verifier('l’extract de tous les porteurs en vrai .xls : trié comme le .xlsx — 24 lignes à HDK (4530 en entier, WD) sur 40',
      /\bok\b/.test(r.etat.classe) && voir().length === 26 && voir()[0][0].indexOf(MARQUE + 'PSN 4530 · DIAGRAM TYPE = WD — 24 lignes gardées sur 40') === 0, r.etat.texte + ' ' + JSON.stringify(voir()[0]));
    await page.close();
    /* Les fusions en plusieurs enregistrements, et l'export GATES d'Excel 95 (qui n'en a pas). */
    const g = feuilleGates(60);
    const lignesG = FX.lignesGates(g);
    const lus = {};
    for (const [nom, contenu] of [['ref.xlsx', xlsxGates(g)], ['fusions.xls', FX.xls({ onglets: [{ nom: 'Export', lignes: lignesG, fusions: g.fusions, fusionsParEnregistrement: 5 }] })],
      ['excel95.xls', FX.xls({ biff: 5, onglets: [{ nom: 'Export', lignes: lignesG, fusions: g.fusions }] })]]) {
      const cg = new Classeur([ongletGates('HDK', gates(40))]);
      const pg = await fenetre(serveur(cg));
      lus[nom] = { r: await importer(pg, nom, contenu, { case: 'HDK', sansArchiver: true }), f: cg.getSheetByName('HDK') };
      await pg.close();
    }
    const ref = lus['ref.xlsx'], fus = lus['fusions.xls'], e95 = lus['excel95.xls'];
    verifier('les seize fusions de la ligne des groupes écrites en quatre enregistrements MERGEDCELLS : toutes recréées, les valeurs celles du .xlsx',
      /\bok\b/.test(fus.r.etat.classe) && fus.f.fusions.length === 16 && JSON.stringify(fusionsDe(fus.f)) === JSON.stringify(fusionsDe(ref.f)) && !premierEcart(fus.f.valeurs, ref.f.valeurs),
      premierEcart(fus.f.valeurs, ref.f.valeurs) || fus.r.etat.texte);
    verifier('l’export GATES d’Excel 95, qui ne connaît pas les fusions : les mêmes valeurs ; la case prévient comme pour un .csv, la page déduit les groupes de proche en proche et trouve la colonne suivie',
      !premierEcart(e95.f.valeurs, ref.f.valeurs) && e95.f.fusions.length === 0 && /un \.xls d’Excel 95 ne garde pas les cellules fusionnées de la ligne des groupes/.test(e95.r.case.lu) &&
      /avertissement/.test(e95.r.etat.classe) && /colonne suivie HDK AA 011/.test(e95.r.etat.texte) && /Un \.xls d’Excel 95 ne garde pas les cellules fusionnées/.test(e95.r.etat.texte),
      e95.r.case.lu + ' / ' + e95.r.etat.texte);
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
    /* Les mêmes refus dans une case GATES : la lecture ne dépend pas de la case. */
    const r = await importer(page, 'export_48.xls', lireXls('lo-protege.xls'), { case: 'HDK' });
    verifier('… et dans une case GATES, le même refus : « protégé »', /erreur/.test(r.etat.classe) && /protégé/.test(r.etat.texte) && page.__appels.length === 0, r.etat.texte);
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
    /* Un « dossier compressé » de Windows (.zip) : posé tel quel, ou renommé en .xls. */
    const dedans = zip([{ nom: 'export SEE.xls', donnees: FX.xls({ onglets: [{ nom: 'S', lignes: [['NAME', 'SOL.', 'Cust.V'], ['TFE1', '001', 'A']] }] }) }]);
    r = await importer(page, 'export-dossier.zip', dedans);
    verifier('un .zip (« dossier compressé ») posé dans une case : sa case dit de l’ouvrir et d’en glisser le fichier, et ce qu’il renferme',
      /erreur/.test(r.etat.classe) && /C’est un dossier compressé \(\.zip\), pas un classeur : l’ouvrir \(double-clic, ou clic droit → Extraire tout\) et glisser ici le fichier/.test(r.etat.texte) &&
      /Il renferme : export SEE\.xls\./.test(r.etat.texte), r.etat.texte);
    r = await importer(page, 'export.xls', dedans);
    verifier('… renommé en .xls : la même explication, avec ce qu’il renferme (plus de « pas de xl/workbook.xml »)',
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
      lus[nom] = { r: await importer(pg, nom, contenu, { case: 'HDK', sansArchiver: true }), f: cg.getSheetByName('HDK'), ctx };
      await pg.close();
    }
    const l = lus['export_48.xls'], v = lus['export_48 protégé.xls'];
    verifier('l’export GATES enregistré par LibreOffice avec « VelvetSweatshop » (FILEPASS, RC4 d’Excel 97) : déchiffré, lu dans la case « GATES HDK » — 186 plans · 138 colonnes · ' +
      'en-têtes en ligne 2 · 16 cellules fusionnées, les mêmes valeurs et les mêmes fusions que le .xls non chiffré, la colonne suivie trouvée',
      /\bok\b/.test(v.r.etat.classe) && /^186 plans · 138 colonnes · en-têtes en ligne 2 · 16 cellules fusionnées/.test(v.r.case.lu) &&
      !premierEcart(v.f.valeurs, l.f.valeurs) && JSON.stringify(v.f.valeurs) === JSON.stringify(l.f.valeurs) && JSON.stringify(fusionsDe(v.f)) === JSON.stringify(fusionsDe(l.f)) &&
      JSON.stringify(v.ctx.construireModele('HDK')) === JSON.stringify(l.ctx.construireModele('HDK')) && /colonne suivie HDK AA 011/.test(v.r.etat.texte),
      premierEcart(v.f.valeurs, l.f.valeurs) || v.r.case.lu + ' / ' + v.r.etat.texte);
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
      lus[nom] = { r: await importer(page, nom, contenu, { case: 'HDK', sansArchiver: true }), f: c.getSheetByName('HDK'), ctx };
      await page.close();
    }
    const x = lus['export_48.xlsx'], m = lus['export_48.xls'];
    verifier('l’export GATES en page web archivée nommée .xls (quoted-printable, Windows-1252, colspan=16 sans guillemets comme Excel les écrit, les cases vides regroupées en ' +
      '« mso-ignore:colspan », qui ne sont pas des fusions) : le même onglet que le .xlsx, les seize fusions comprises — pas une de plus —, la colonne suivie trouvée',
      /\bok\b/.test(m.r.etat.classe) && !premierEcart(m.f.valeurs, x.f.valeurs) && JSON.stringify(fusionsDe(m.f)) === JSON.stringify(fusionsDe(x.f)) &&
      /186 plans, colonne suivie HDK AA 011 › Avancement Définition Electrique/.test(m.r.etat.texte) && /16 cellules fusionnées/.test(m.r.case.lu),
      premierEcart(m.f.valeurs, x.f.valeurs) || m.r.etat.texte + ' / ' + m.r.case.lu);
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
      document.querySelector('[data-case="see"] input[type=file]').addEventListener('change', () => {
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
        document.querySelector('[data-case="see"] input[type=file]').addEventListener('change', () => {
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
    let r = await importer(page, 'bas.xlsx', xlsxGates(gates(20), { titres: titres(7) }), { case: 'HDK' });
    verifier('en-têtes en ligne 9 : refusé, « la page ne la trouverait pas », rien n’est envoyé',
      /erreur/.test(r.etat.classe) && /en ligne 9/.test(r.etat.texte) && /la page ne la trouverait pas/.test(r.etat.texte) && page.__appels.length === 0 &&
      JSON.stringify(c.getSheetByName('HDK').valeurs) === avant, r.etat.texte);
    r = await importer(page, 'haut.xlsx', xlsxGates(gates(20), { titres: titres(6) }), { case: 'HDK', sansArchiver: true });
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
    let r = await importer(page, 'export.csv', Buffer.from(csvGates(g), 'utf8'), { case: 'HDK' });
    verifier('avec sa ligne de groupes : importé ; sans fusion, la page déduit les groupes de proche en proche et retrouve la colonne suivie ; la fenêtre prévient qu’un .csv ne garde pas les fusions',
      /\bok\b/.test(r.etat.classe) && /avertissement/.test(r.etat.classe) && /colonne suivie HDK AA 011 › Avancement Définition Electrique/.test(r.etat.texte) &&
      /\.csv ne garde pas les cellules fusionnées/.test(r.etat.texte) && /\.csv ne garde pas les cellules fusionnées/.test(r.case.lu) &&
      c.getSheetByName('HDK').fusions.length === 0 && /Relevé S\d+ archivé/.test(r.etat.texte), r.etat.texte);
    const histo = JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs);
    page.__appels = [];
    r = await importer(page, 'export.csv', Buffer.from(csvGates(g, { sansGroupes: true }), 'utf8'), { case: 'HDK' });
    /* Sans ligne de groupes, la page ne trouverait plus la colonne suivie, que
       « HDK » a : l'export ne le remplace pas (débrief 20). La case disait
       déjà qu'un .csv ne garde pas les fusions. */
    const avantCsv = JSON.stringify(c.getSheetByName('HDK').valeurs);
    verifier('sans ligne de groupes : la page n’y trouverait plus la colonne suivie, que « HDK » a — refusé, l’ancien intact, rien d’archivé ; la case conseillait l’export Excel',
      /erreur/.test(r.etat.classe) && /Colonne suivie absente de cet export/.test(r.etat.texte) && /L’ancien onglet « HDK » est intact/.test(r.etat.texte) &&
      /\.csv ne garde pas les cellules fusionnées/.test(r.case.lu) && JSON.stringify(c.getSheetByName('HDK').valeurs) === avantCsv && sansImport(c) &&
      page.__appels.indexOf('importArchiverReleve') === -1 && JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs) === histo, r.etat.texte + ' / ' + r.case.lu);
    await page.close();
  }

  // =================================================================
  section('Les cases GATES : chaque export dans la sienne, rien de deviné');
  {
    const c = new Classeur([ongletGates('HDK', gates(40)), ongletGates('THS', gates(30, { prefixe: 'THS' }))]);
    const ctx = serveur(c);
    const refsHDK = gates(40).valeurs.slice(3).map(l => l[I_REF]);
    let page = await fenetre(ctx);
    let k = await poser(page, 'g:HDK', [{ nom: 'export.xlsx', contenu: xlsxGates(gates(30, { prefixe: 'THS' })) }]);
    let ui = await fenetreEtat(page);
    verifier('l’export de THS posé dans la case « GATES HDK » : il ira dans « HDK » — rien n’est choisi à sa place —, mais la case prévient, sans bloquer : aucun de ses plans n’est dans « HDK », tous sont dans « THS »',
      k.etat === 'lu' && /^Remplacera l’onglet « HDK »/.test(k.cible) &&
      k.note === 'aucun de ses 30 plans en commun avec « HDK » : est-ce bien son export ? 30 sont dans « THS » : sa place serait plutôt la case « GATES THS ».' &&
      !ui.desactive && ui.blocage === '', JSON.stringify([k, ui]));
    k = await poser(page, 'g:HDK', [{ nom: 'export_186.xlsx', contenu: xlsxGates(gates(186, { refs: i => i < 3 ? refsHDK[i] : 'ZZZ-' + (1000 + i) })) }]);
    verifier('un export qui ne partage que 3 de ses 186 plans avec « HDK » : « seulement 3 plans sur 186 en commun avec « HDK » : est-ce bien son export ? », sans bloquer',
      k.note === 'seulement 3 plans sur 186 en commun avec « HDK » : est-ce bien son export ?' && !(await fenetreEtat(page)).desactive, JSON.stringify(k));
    k = await poser(page, 'g:HDK', [{ nom: 'export_48.xlsx', contenu: xlsxGates(gates(40)) }]);
    verifier('son propre export : aucun avertissement', k.note === '' && /^Remplacera l’onglet « HDK »/.test(k.cible), JSON.stringify(k));
    /* Rien n'est déplacé : l'export de THS posé dans la case de HDK, importé quand même, va dans HDK. */
    k = await poser(page, 'g:HDK', [{ nom: 'export.xlsx', contenu: xlsxGates(gates(30, { prefixe: 'THS' })) }]);
    await page.uncheck('#archiver');
    const r = await lancer(page);
    verifier('l’avertissement ne bloque pas, et ne déplace rien : l’export va dans la case où on l’a posé, « HDK »',
      /\bok\b/.test(r.classe) && c.getSheetByName('HDK').valeurs[3][I_REF] === gates(30, { prefixe: 'THS' }).valeurs[3][I_REF] && page.__cibles[0] === JSON.stringify({ sorte: 'gates', contrat: 'HDK', nouveau: false }),
      r.texte + ' / ' + page.__cibles.join(' '));
    await page.close();
    /* Un contrat préparé d'avance (ses lignes de groupes et d'en-têtes, pas de plan) : rien à comparer, rien à dire. */
    const prepare = gates(1, { groupe: 'VRK' });
    prepare.valeurs = prepare.valeurs.slice(0, 2);
    const c2 = new Classeur([ongletGates('HDK', gates(40)), ongletGates('VRK', prepare)]);
    page = await fenetre(serveur(c2));
    k = await poser(page, 'g:VRK', [{ nom: 'export_VRK.xlsx', contenu: xlsxGates(gates(25, { prefixe: 'VRK', groupe: 'VRK' })) }]);
    verifier('la case d’un contrat préparé d’avance, sans plan : son export n’a rien à recouper, aucun avertissement', k.etat === 'lu' && k.note === '' && /Remplacera l’onglet « VRK »/.test(k.cible),
      JSON.stringify(k));
    /* La date de chaque fichier, et le même fichier dans deux cases. */
    const an = new Date().getFullYear();
    const meme = { nom: 'Export GATES.xlsx', contenu: xlsxGates(gates(40)), date: new Date(an, 9, 3, 14, 20).getTime() };
    k = await poser(page, 'g:HDK', [meme]);
    const k2 = await poser(page, 'g:VRK', [meme]);
    ui = await fenetreEtat(page);
    verifier('chaque case dit la date de son fichier, « du 3 oct. 14:20 »', k.date === 'du 3 oct. 14:20' && k2.date === 'du 3 oct. 14:20', JSON.stringify([k.date, k2.date]));
    verifier('le même fichier dans deux cases : « Importer » attend, et le dit — chaque contrat a son propre export',
      ui.desactive && ui.blocage === 'Le même fichier, « Export GATES.xlsx », est dans les cases « GATES HDK » et « GATES VRK » : chaque contrat a son propre export.', ui.blocage);
    await capture(page, 'meme-fichier');
    /* Plusieurs fichiers lâchés sur une case : le premier y va, les autres sont nommés. */
    k = await poser(page, 'g:VRK', [{ nom: 'export_VRK.xlsx', contenu: xlsxGates(gates(25, { prefixe: 'VRK', groupe: 'VRK' })) },
      { nom: 'Nommage WD BFLOW.xlsx', contenu: seeXlsx(5) }, { nom: 'notes.xlsx', contenu: seeXlsx(2) }]);
    ui = await fenetreEtat(page);
    verifier('trois fichiers lâchés sur une case : le premier y va, les deux autres sont laissés de côté et nommés — chacun dans sa case',
      k.fichier === 'export_VRK.xlsx' && k.etat === 'lu' &&
      /Une case prend un seul fichier : « export_VRK\.xlsx » va dans « GATES VRK », « Nommage WD BFLOW\.xlsx », « notes\.xlsx » laissés de côté — chacun dans sa case\./.test(ui.etat) &&
      !ui.desactive, JSON.stringify([k.fichier, ui.etat]));
    await page.close();
  }

  // =================================================================
  section('Un nouveau contrat : « Ajouter un contrat… »');
  {
    /* Un contrat inconnu, aux groupes « NEO AA » : sa case, son nom tiré de ses groupes, vérifié. */
    const c3 = new Classeur([ongletGates('HDK', gates(40)), new Feuille('Notes', [['x']])]);
    const ctx3 = serveur(c3);
    let page = await fenetre(ctx3);
    const id = await ajouterContrat(page);
    let n = await laCase(page, id);
    verifier('« Ajouter un contrat… » ouvre une case de plus : « GATES », un champ pour son nom — celui de son onglet —, son fichier à poser',
      n.etiquette === 'GATES' && n.nom === '' && /Le nom du contrat est celui de son onglet, comme « HDK »\./.test(n.verifNom) && n.etat === 'vide', JSON.stringify(n));
    n = await poser(page, id, [{ nom: 'gates.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'NEO', groupe: 'NEO' })) }]);
    verifier('son export lu, le nom proposé est celui de ses groupes « NEO AA … », vérifié par le serveur, modifiable ; la case devient « GATES NEO »',
      n.nom === 'NEO' && /Nom tiré de ses groupes « NEO AA … » : le changer au besoin/.test(n.verifNom) && n.etiquette === 'GATES NEO' &&
      /^Créera l’onglet « NEO » : un nouveau contrat, rangé après les autres\.$/.test(n.cible) && n.note === '', JSON.stringify(n));
    const r3 = { etat: await lancer(page) };
    verifier('importé : « NEO » rangé juste après « HDK », avant « Notes » ; ses groupes n’étant pas « HDK AA 011 », la case dit la colonne suivie introuvable, sans archiver',
      nomsOnglets(c3).join() === 'HDK,NEO,Notes' && ctx3.listerContrats(c3).map(k => k.id).join() === 'HDK,NEO' && /onglet « NEO » créé \(nouveau contrat\)/.test(r3.etat.texte) &&
      /colonne suivie est introuvable/.test(r3.etat.texte) && !c3.getSheetByName('Historique_FWD_NEO'), r3.etat.texte + ' / ' + nomsOnglets(c3).join(', '));
    const apres = await fenetreEtat(page);
    const caseNeo = await laCase(page, 'g:NEO');
    verifier('la liste des contrats relue, la case qui a créé « NEO » devient la sienne, « GATES NEO », avec son résultat ; « Ajouter un contrat… » reste là',
      apres.cases.join() === 'g:HDK,g:NEO,see' && !!caseNeo && caseNeo.etat === 'fait' && /onglet « NEO » créé/.test(caseNeo.resultat) &&
      await page.isVisible('#ajouter'), JSON.stringify([apres.cases, caseNeo]));
    /* Un contrat ajouté dont l'export a les plans d'un contrat du classeur : la case prévient. */
    const id2 = await ajouterContrat(page, 'VRK', { nom: 'copie.xlsx', contenu: xlsxGates(gates(40)) });
    n = await laCase(page, id2);
    verifier('un contrat ajouté dont l’export porte les plans de « HDK » : la case prévient, sans bloquer — est-ce l’export de « HDK » ?',
      n.note === '40 de ses 40 plans sont déjà dans « HDK » : est-ce l’export de « HDK » ? Il irait alors dans sa case, « GATES HDK ».' && !(await fenetreEtat(page)).desactive,
      JSON.stringify(n));
    /* Deux cases pour le même nouveau contrat, puis une case nommée sans fichier : « Importer » attend. */
    const id3 = await ajouterContrat(page, 'vrk');
    let ui = await fenetreEtat(page);
    verifier('deux cases pour le même nouveau contrat (casse indifférente) : « Importer » attend qu’on en annule une',
      ui.desactive && /Deux cases pour le même nouveau contrat « vrk » : en annuler une\./.test(ui.blocage), ui.blocage);
    await page.click('[data-case="' + id2 + '"] .annuler');
    ui = await fenetreEtat(page);
    verifier('l’autre annulée, la case nommée reste sans fichier : « Importer » attend son export — ou qu’on l’annule',
      ui.desactive && ui.blocage === 'Choisir l’export GATES du nouveau contrat « vrk » dans sa case.', ui.blocage);
    await page.click('[data-case="' + id3 + '"] .annuler');
    ui = await fenetreEtat(page);
    verifier('annulée elle aussi : il n’y a plus rien à importer, plus de case en trop', ui.desactive && ui.blocage === '' && ui.cases.join() === 'g:HDK,g:NEO,see', JSON.stringify(ui));
    await page.close();
    /* Aucun contrat encore : la case du premier est ouverte d'office. */
    const c4 = new Classeur([new Feuille('Feuille 1', [])]);
    const ctx4 = serveur(c4);
    page = await fenetre(ctx4);
    const vide = await fenetreEtat(page);
    const premiere = vide.cases.filter(x => /^n/.test(x))[0];
    const l = await poser(page, premiere, [{ nom: 'export.xlsx', contenu: xlsxGates(gates(30)) }]);
    const r4 = { etat: await lancer(page) };
    verifier('un classeur sans contrat : la case du premier est ouverte d’office, son nom tiré de ses groupes (« HDK ») ; importé en tête, il archive son premier relevé',
      vide.cases.length === 2 && !!premiere && l.nom === 'HDK' && /\bok\b/.test(r4.etat.classe) &&
      nomsOnglets(c4).slice(0, 2).join() === 'HDK,Feuille 1' && ctx4.listerContrats(c4).map(x => x.id).join() === 'HDK' && ctx4.getHistorique(c4, 'HDK').length === 1,
      JSON.stringify([vide.cases, l.nom]) + ' / ' + r4.etat.texte + ' / ' + nomsOnglets(c4).join(', '));
    await page.close();
  }

  // =================================================================
  section('GATES et SEE d’un coup, pour deux contrats : un seul extract SEE');
  {
    const refA = i => refGates(i), refB = i => refGates(i, 500);
    const c = new Classeur([ongletGates('HDK', gates(40, { refs: refA })), ongletGates('THS', gates(30, { refs: refB }))]);
    const ctx = serveur(c, psnGardes({ THS: ['4610'] }));
    const page = await fenetre(ctx);
    /* L'extract de tous les porteurs : les 40 plans de HDK (4530), les 30 de THS (4610), et 50 lignes d'autres machines. */
    const tri = i => i < 40 ? { psn: '4520,4530', type: 'WD' } : i < 70 ? { psn: '4610', type: 'WD', nom: nomDe(i - 40 + 500), sol: String((i - 40) % 3 + 1).padStart(3, '0'),
      custV: 'ABC'[(i - 40) % 3] } : { psn: '4700', type: 'WD' };
    await poser(page, 'g:HDK', [{ nom: 'export_48.xlsx', contenu: xlsxGates(gates(40, { refs: refA, avancement: i => i % 2 ? 'VALIDATED' : 'PWD_IN_PROGRESS' })) }]);
    await poser(page, 'g:THS', [{ nom: 'export_49.xlsx', contenu: xlsxGates(gates(30, { refs: refB, avancement: () => 'VALIDATED' })) }]);
    const see = await poser(page, 'see', [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeComplet(120, tri) }]);
    const lus = await cases(page);
    verifier('trois cases, trois fichiers : chaque export GATES dans la case de son contrat, sans avertissement ; l’extract SEE donne 40 lignes à HDK (4530), 30 à THS (4610, gardé d’une fois précédente)',
      lus.map(x => x.id + ':' + x.etat).join() === 'g:HDK:lu,g:THS:lu,see:lu' && lus.every(x => !x.note) &&
      porteur(see, 'HDK').part === '— 40 lignes WD → créera « SEE HDK »' && porteur(see, 'THS').psn === '4610' && porteur(see, 'THS').enr === 'enregistré' &&
      porteur(see, 'THS').part === '— 30 lignes WD → créera « SEE THS »', JSON.stringify(lus.map(x => [x.id, x.etat, x.note])) + ' ' + JSON.stringify(see.porteurs));
    page.__appels = [];
    page.__cibles = [];
    const etat = await lancer(page);
    const ordre = page.__appels.filter(n => /Debut|Archiver/.test(n)).join();
    verifier('les exports GATES passent d’abord, chacun suivi de l’archivage de son contrat, puis la base SEE de chaque contrat, dans l’ordre des contrats',
      ordre === 'importSecondeBaseDebut,importArchiverReleve,importSecondeBaseDebut,importArchiverReleve,importSecondeBaseDebut,importSecondeBaseDebut' &&
      page.__cibles.map(x => JSON.parse(x)).map(x => x.sorte + ':' + x.contrat).join() === 'gates:HDK,gates:THS,see:HDK,see:THS', ordre + ' / ' + page.__cibles.join(' '));
    const semaine = semaineDe(ctx);
    verifier('une ligne par case et par base, ✓, et le relevé de chaque contrat dit',
      /\bok\b/.test(etat.classe) && (etat.texte.match(/✓/g) || []).length === 4 && /onglet « HDK » remplacé : 40 plans, .*Relevé S\d+ archivé \(40 plans, 20 validés\)/.test(etat.texte) &&
      /onglet « THS » remplacé : 30 plans, .*Relevé S\d+ archivé \(30 plans, 30 validés\)/.test(etat.texte) && /30 lignes dans l’onglet « SEE THS » \(3 colonnes ; PSN 4610 · WD\)/.test(etat.texte) &&
      /40 lignes dans l’onglet « SEE HDK » \(3 colonnes ; PSN 4530 · WD\)/.test(etat.texte) && /Rouvrir le tableau de bord/.test(etat.texte), etat.texte);
    const hHDK = ctx.getHistorique(c, 'HDK'), hTHS = ctx.getHistorique(c, 'THS');
    const pHDK = ctx.getDonneesPourClient('HDK').rapprochement, pTHS = ctx.getDonneesPourClient('THS').rapprochement;
    verifier('chaque contrat a son relevé de la semaine, et sa base : la page les rapproche (40 et 30 lignes), chacune avec son filtre',
      hHDK.length === 1 && hHDK[0].semaine === semaine && hHDK[0].termine === 20 && hTHS.length === 1 && hTHS[0].termine === 30 &&
      pHDK.lignes.length === 40 && pTHS.lignes.length === 30 && pHDK.filtre === 'PSN 4530 · WD' && pTHS.filtre === 'PSN 4610 · WD' && sansImport(c),
      JSON.stringify([hHDK.map(x => x.semaine + ':' + x.termine), hTHS.map(x => x.semaine + ':' + x.termine), pHDK.filtre, pTHS.filtre]));
    await capture(page, 'deux-contrats-fin');
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
    let r = await importer(page, 'export_48.xlsx', xlsxGates(gates(40, { avancement: (i, v) => i < 10 ? 'VALIDATED' : v })), { case: 'HDK' });
    const h = ctx.getHistorique(c, 'HDK');
    verifier('archivé pour le contrat importé seulement : une ligne de la semaine en cours dans Historique_FWD_HDK, celui de THS intact',
      /\bok\b/.test(r.etat.classe) && /Relevé S\d+ archivé \(40 plans, \d+ validés\)/.test(r.etat.texte) && h.length === 2 && h[0].semaine === precedente &&
      h[1].semaine === semaine && h[1].termine >= 10 && JSON.stringify(c.getSheetByName('Historique_FWD_THS').valeurs) === thsAvant, r.etat.texte + ' ' + JSON.stringify(h.map(x => x.semaine)));
    await page.close();
    /* L'export de la semaine passée, réimporté : il est posé, mais le relevé de la semaine, différent, n'est pas écrasé. */
    const histoAvant = JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs);
    page = await fenetre(ctx);
    r = await importer(page, 'export_47.xlsx', xlsxGates(gates(40)), { case: 'HDK' });
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
    await ajouterContrat(page, 'THS', { nom: 'export.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'THS' })) });
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
    const r = await importer(page, 'export_48.xlsx', xlsxGates(gates(40, { avancement: () => 'VALIDATED' })), { case: 'HDK' });
    ctx.importSecondeBaseLot = vrai;
    await page.waitForTimeout(300);
    verifier('une panne qui dure pendant l’envoi : trois essais, le message la dit ; l’ancien « HDK », ses fusions et son historique sont intacts ; l’onglet temporaire est retiré ; rien n’est archivé',
      /erreur/.test(r.etat.classe) && /Service Spreadsheets indisponible/.test(r.etat.texte) && /Rien n’a été remplacé/.test(r.etat.texte) && lots === 3 &&
      JSON.stringify(c.getSheetByName('HDK').valeurs) === avantOnglet && JSON.stringify(c.getSheetByName('HDK').fusions) === avantFusions &&
      JSON.stringify(c.getSheetByName('Historique_FWD_HDK').valeurs) === avantHisto && sansImport(c) && page.__appels.indexOf('importArchiverReleve') === -1,
      r.etat.texte + ' / ' + lots + ' / ' + nomsOnglets(c).join(', '));
    verifier('la case « GATES HDK » porte l’échec, en ✗', (await laCase(page, 'g:HDK')).etat === 'echec');
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
    /* Un export d'un autre programme (blocs « XYZ AA … ») posé dans la case de HDK : la page n'y trouverait pas « HDK AA 011 › … ». */
    const r = await importer(page, 'export_autre.xlsx', xlsxGates(gates(40, { groupe: 'XYZ' })), { case: 'HDK' });
    verifier('un export où la page ne trouverait pas la colonne suivie ne remplace pas « HDK », qui l’a : refusé, dit pourquoi, l’ancien intact, ses fusions aussi, pas d’onglet temporaire, rien d’archivé',
      /erreur/.test(r.etat.classe) && /Colonne suivie absente de cet export/.test(r.etat.texte) && /L’ancien onglet « HDK » est intact/.test(r.etat.texte) &&
      !/peut-être allé au bout/.test(r.etat.texte) && JSON.stringify(c.getSheetByName('HDK').valeurs) === avant &&
      JSON.stringify(c.getSheetByName('HDK').fusions) === avantFusions && sansImport(c) && page.__appels.indexOf('importArchiverReleve') === -1,
      r.etat.texte + ' / ' + nomsOnglets(c).join(', '));
    /* Un onglet qui ne la lisait déjà pas (XYZ) : l'export de même forme le remplace, avec l'avertissement d'avant. */
    const r2 = await importer(page, 'export_xyz.xlsx', xlsxGates(gates(30, { prefixe: 'XYZ', groupe: 'XYZ', avancement: () => 'VALIDATED' })), { case: 'XYZ' });
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
    verifier('la fenêtre n’ouvre une case que pour les contrats : « GATES HDK », et la case SEE', (await fenetreEtat(page)).cases.join() === 'g:HDK,see');
    const r = await importer(page, 'export.xlsx', xlsxGates(gates(40)), { case: 'HDK', sansArchiver: true });
    verifier('le prochain import de « HDK » retire le sien, pas ceux des autres', /\bok\b/.test(r.etat.classe) && !c.getSheetByName('HDK (import abc123)') &&
      !!c.getSheetByName('THS (ancien abc123)') && !!c.getSheetByName('SEE HDK (import abc123)'), nomsOnglets(c).join(', '));
    await page.close();
    /* Des onglets nommés à la main comme des restes, sans en avoir l'étiquette
       (six chiffres hexadécimaux, dont une lettre) : des onglets comme les autres. */
    const m = new Classeur([ongletGates('HDK', gates(40)), new Feuille('HDK (ancien export)', [['gardé']]), new Feuille('HDK (ancien 041026)', [['gardé']]),
      new Feuille('HDK (import manuel)', [['gardé']])]);
    const ctxM = serveur(m);
    const pageM = await fenetre(ctxM);
    const rM = await importer(pageM, 'export.xlsx', xlsxGates(gates(40)), { case: 'HDK', sansArchiver: true });
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
      ['hdk', /Le contrat « HDK » existe déjà : son export va dans sa case, « GATES HDK »\./], ['notes', /Un onglet « Notes » existe déjà/], ['V'.repeat(81), /Nom trop long : 81 caractères/]];
    const rates = cas.filter(x => { const r = ctx.importVerifierNouveauContrat(jeton, x[0]); return r.ok || !x[1].test(r.message); });
    verifier('un nom vide, réservé (base SEE, historique, copie, import), déjà pris (casse indifférente — le contrat a sa case) ou trop long est refusé, et dit pourquoi', !rates.length,
      rates.map(x => x[0] + ' : ' + JSON.stringify(ctx.importVerifierNouveauContrat(jeton, x[0]))).join(' | '));
    verifier('un nom propre est accepté, sans ses espaces autour', JSON.stringify(ctx.importVerifierNouveauContrat(jeton, '  VRK  ')) === JSON.stringify({ ok: true, nom: 'VRK' }));
    let refus = '';
    try { ctx.importSecondeBaseDebut(jeton, { sorte: 'gates', contrat: 'SEE THS', nouveau: true }, 3, 5); } catch (e) { refus = e.message; }
    verifier('le serveur revérifie au début de l’import, fenêtre ou pas', /nom réservé/.test(refus) && sansImport(c), refus);
    const page = await fenetre(ctx);
    const id = await ajouterContrat(page, undefined, { nom: 'export.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'VRK', groupe: 'VRK' })) });
    let l = await laCase(page, id);
    verifier('l’export d’un contrat ajouté : nommé d’après ses groupes (« VRK »), le nom vérifié', l.nom === 'VRK' &&
      /^Créera l’onglet « VRK » : un nouveau contrat, rangé après les autres\./.test(l.cible), JSON.stringify(l));
    await page.fill('[data-case="' + id + '"] .nom', 'Notes');
    await attendreLecture(page);
    const refuse = await fenetreEtat(page);
    l = await laCase(page, id);
    verifier('un nom déjà pris, tapé : refusé à mesure, sous le champ, et « Importer » attend et dit pourquoi', refuse.desactive && /Un onglet « Notes » existe déjà/.test(refuse.blocage) &&
      /Un onglet « Notes » existe déjà/.test(l.verifNom) && l.etiquette === 'GATES', JSON.stringify([refuse, l.verifNom]));
    await page.fill('[data-case="' + id + '"] .nom', 'VRK');
    await attendreLecture(page);
    const r = { etat: await lancer(page) };
    /* « Importer » cliqué tout de suite : le champ perd le focus (« change »), le nom déjà vérifié n'est pas redemandé — le clic n'est pas perdu. */
    verifier('« VRK » tapé, vérifié, « Importer » cliqué aussitôt : rangé juste après le dernier onglet de contrat (avant « Notes »), et c’est un contrat',
      /\bok\b/.test(r.etat.classe) && nomsOnglets(c).join() === 'HDK,SEE HDK,THS,VRK,Notes' && ctx.listerContrats(c).map(x => x.id).join() === 'HDK,THS,VRK', nomsOnglets(c).join());
    await page.close();
    /* Un nouveau contrat dont l'envoi échoue : il n'y avait rien à remplacer. */
    const page2 = await fenetre(ctx, rapide);
    const vraiLot = ctx.importSecondeBaseLot;
    ctx.importSecondeBaseLot = function () { throw new Error('Service Spreadsheets indisponible'); };
    const idNeo = await ajouterContrat(page2, undefined, { nom: 'neo.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'NEO', groupe: 'NEO' })) });
    l = await laCase(page2, idNeo);
    const rNeo = { etat: await lancer(page2) };
    ctx.importSecondeBaseLot = vraiLot;
    verifier('un nouveau contrat dont l’envoi échoue : le message dit « Rien n’a été créé », pas « remplacé » ; ni onglet « NEO », ni reste d’import ; sa case reste une case de contrat ajouté',
      l.nom === 'NEO' && /erreur/.test(rNeo.etat.classe) && /Service Spreadsheets indisponible/.test(rNeo.etat.texte) && /Rien n’a été créé dans le classeur/.test(rNeo.etat.texte) &&
      !/remplacé|ancien onglet/.test(rNeo.etat.texte) && !c.getSheetByName('NEO') && sansImport(c) && (await laCase(page2, idNeo)).etat === 'echec',
      rNeo.etat.texte + ' / ' + nomsOnglets(c).join());
    await page2.close();
  }

  // =================================================================
  section('Deux tours dans la même fenêtre : la liste des contrats est relue');
  {
    /* Le classeur n'a que HDK. Premier tour : THS ajouté, avec son export
       GATES. Second tour, sans fermer la fenêtre : THS a sa case ; l'extract
       SEE donne ses lignes à THS (PSN tapé) ; un export GATES de THS corrigé
       va dans sa case. */
    const refT = i => refGates(i, 500);
    const c = new Classeur([ongletGates('HDK', gates(40))]);
    const ctx = serveur(c);
    const page = await fenetre(ctx);
    await ajouterContrat(page, 'THS', { nom: 'export_ths.xlsx', contenu: xlsxGates(gates(20, { refs: refT })) });
    let r = await lancer(page);
    let ui = await fenetreEtat(page);
    verifier('1er tour : THS créé, puis la liste des contrats relue (sans nouveau jeton) — THS a désormais sa case, « GATES THS »',
      /\bok\b/.test(r.classe) && /Relevé S\d+ archivé \(20 plans/.test(r.texte) && !!c.getSheetByName('THS') && page.__appels[page.__appels.length - 1] === 'importContrats' &&
      ui.cases.join() === 'g:HDK,g:THS,see', r.texte + ' / ' + page.__appels.join() + ' / ' + ui.cases.join());
    const tri = i => ({ psn: '4610', type: 'WD', nom: nomDe(i + 500), sol: String(i % 3 + 1).padStart(3, '0'), custV: 'ABC'[i % 3] });
    await poser(page, 'see', [{ nom: 'extract_SEE_semaine40.xlsx', contenu: seeComplet(20, tri) }]);
    const see = await taperPsn(page, 'THS', '4610');
    const gat = await poser(page, 'g:THS', [{ nom: 'export_ths (1).xlsx', contenu: xlsxGates(gates(20, { refs: refT, avancement: () => 'VALIDATED' })) }]);
    verifier('2e tour : l’extract SEE donne ses 20 lignes à THS (PSN tapé : 4610) — et aucune à HDK (4530), qui n’est pas touché',
      porteur(see, 'THS').part === '— 20 lignes WD → créera « SEE THS »' && porteur(see, 'HDK').part === '— aucune ligne WD pour ce PSN : « SEE HDK » ne sera pas touché',
      JSON.stringify(see.porteurs));
    verifier('2e tour : l’export GATES de THS va dans sa case, sans avertissement', gat.etat === 'lu' && /^Remplacera l’onglet « THS »/.test(gat.cible) && !gat.note, JSON.stringify(gat));
    ui = await fenetreEtat(page);
    verifier('2e tour : « Importer » s’allume', !ui.desactive && ui.blocage === '', JSON.stringify(ui));
    await capture(page, 'deux-tours-avant-import');
    r = await lancer(page);
    verifier('2e tour : « SEE THS » créé, « SEE HDK » jamais touché (dit en ⚠) ; THS remplacé',
      /\bok\b/.test(r.classe) && /avertissement/.test(r.classe) && !!c.getSheetByName('SEE THS') && !c.getSheetByName('SEE HDK') && c.getSheetByName('THS').valeurs.length === 23 &&
      ctx.lireSecondeBase(c, 'THS').etat === 'ok' && /⚠ « HDK » : aucune ligne WD pour le PSN 4530 — « SEE HDK » n’est pas touché\./.test(r.texte), r.texte + ' / ' + nomsOnglets(c).join(', '));
    await capture(page, 'deux-tours-fin');
    await page.close();
  }
  {
    /* La relecture de la liste échoue (le classeur ne répond pas) : on ne
       travaille pas avec une liste périmée — « Importer » le dit et attend. */
    const c = new Classeur([ongletGates('HDK', gates(40))]);
    const ctx = serveur(c);
    const page = await fenetre(ctx, rapide);
    const vrai = ctx.importContrats;
    ctx.importContrats = function () { throw new Error('Service Spreadsheets indisponible'); };
    await ajouterContrat(page, 'THS', { nom: 'export_ths.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'THS', groupe: 'THS' })) });
    await lancer(page);
    await poser(page, 'see', [{ nom: 'see.xlsx', contenu: seeComplet(5, () => ({ psn: '4530', type: 'WD' })) }]);
    let ui = await fenetreEtat(page);
    verifier('la liste des contrats n’a pas pu être relue : « Importer » attend, et dit de rouvrir la fenêtre',
      ui.desactive && /La liste des contrats n’a pas pu être relue après l’import : fermer cette fenêtre et la rouvrir/.test(ui.blocage), JSON.stringify(ui));
    ctx.importContrats = vrai;
    await poser(page, 'see', [{ nom: 'see2.xlsx', contenu: seeComplet(6, () => ({ psn: '4530', type: 'WD' })) }]);
    ui = await fenetreEtat(page);
    verifier('au fichier suivant, elle est redemandée ; relue, THS a sa case et « Importer » repart',
      !/n’a pas pu être relue/.test(ui.blocage) && ui.cases.join() === 'g:HDK,g:THS,see' && !ui.desactive, JSON.stringify(ui));
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
    const id = await ajouterContrat(page, 'THS', { nom: 'export_ths.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'THS' })) });
    const see = await poser(page, 'see', [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeComplet(12, () => ({ psn: '4530', type: 'WD' })) }]);
    const nouv = await laCase(page, id);
    verifier('la case du nouveau contrat annonce le renommage de « SEE » ; la ligne de HDK dans la case SEE vise le futur nom, « SEE HDK » ; THS, nouveau, n’a pas de PSN',
      /L’onglet « SEE » de « HDK » deviendra « SEE HDK »/.test(nouv.cible) &&
      porteur(see, 'HDK').part === '— 12 lignes WD → remplacera « SEE HDK » (aujourd’hui « SEE », renommé à la création du nouveau contrat)' &&
      /THS \(nouveau\)/.test(JSON.stringify(see.porteurs.map(p => p.contrat))) === false && porteur(see, 'THS').part === ': pas de base SEE tant que le PSN n’est pas donné',
      JSON.stringify([nouv.cible, see.porteurs]));
    await capture(page, 'second-contrat-annonce');
    const r = await lancer(page);
    await capture(page, 'second-contrat-fin');
    verifier('importé : « SEE » devenu « SEE HDK » (et rempli par l’extract trié), « Historique_FWD » devenu « Historique_FWD_HDK » — et la fenêtre le dit',
      /\bok\b/.test(r.classe) && /onglet « THS » créé \(nouveau contrat\) ; l’onglet « SEE » devient « SEE HDK », l’onglet « Historique_FWD » devient « Historique_FWD_HDK »/.test(r.texte) &&
      !c.getSheetByName('SEE') && c.getSheetByName('SEE HDK').valeurs.length === 14 && !c.getSheetByName('Historique_FWD') && !!c.getSheetByName('Historique_FWD_HDK'),
      r.texte + ' / ' + nomsOnglets(c).join(', '));
    verifier('HDK garde sa comparaison et ses relevés ; THS a son premier relevé, dans son propre historique',
      ctx.lireSecondeBase(c, 'HDK').etat === 'ok' && ctx.getHistorique(c, 'HDK').length === 1 && ctx.getHistorique(c, 'THS').length === 1 &&
      /Relevé S\d+ archivé \(20 plans/.test(r.texte), r.texte);
    await page.close();
  }
  {
    /* Sans extract SEE dans la fenêtre : la comparaison de HDK ne disparaît plus. */
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
    const r = await importer(page, 'export_48.xlsx', xlsxGates(gates(40, { avancement: () => 'VALIDATED' })), { case: 'HDK' });
    verifier('l’onglet n’est pas échangé sans le verrou : le message le dit, « L’ancien onglet « HDK » est intact », rien ne traîne',
      /erreur/.test(r.etat.classe) && /Le classeur est occupé par un autre geste \(archivage…\) : l’onglet « HDK » n’a pas été remplacé\. Relancer l’import dans une minute\. L’ancien onglet « HDK » est intact\./.test(r.etat.texte) &&
      !/peut-être allé au bout/.test(r.etat.texte) && JSON.stringify(c.getSheetByName('HDK').valeurs) === avant && sansImport(c) && page.__appels.indexOf('importArchiverReleve') === -1,
      r.etat.texte + ' / ' + nomsOnglets(c).join(', '));
    /* Sans le verrou, un PSN ne s'enregistre pas non plus : la case le dit, « Importer » attend. */
    await poser(page, 'see', [{ nom: 'see.xlsx', contenu: seeComplet(5, () => ({ psn: '4530', type: 'WD' })) }]);
    const k = await taperPsn(page, 'HDK', '4531');
    const ui = await fenetreEtat(page);
    verifier('… et un PSN tapé ne s’enregistre pas sans lui : la case le dit, « Importer » attend qu’on le retape',
      /Le PSN de « HDK » n’a pas pu être enregistré \(Le classeur est occupé par un autre geste/.test(porteur(k, 'HDK').enr) && ui.desactive &&
      /PSN de « HDK » : Le PSN de « HDK » n’a pas pu être enregistré/.test(ui.blocage), JSON.stringify([porteur(k, 'HDK'), ui.blocage]));
    await page.close();
  }

  // ===================================================================== le tri de l'extract SEE (débrief 21)
  /* « Il va falloir faire deux tris » : la machine (VALIDITY PSN FULL — HDK,
     c'est 4530) et le type de schéma (DIAGRAM TYPE : seuls les WD). Ce qui
     suit vérifie la règle elle-même, puis chaque façon dont elle se montre :
     dans la fenêtre (à la lecture, à la frappe d'un PSN), dans l'onglet posé,
     à la relecture par la page, dans le Diagnostic. */
  const fine = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  /* Les lignes d'un extract telles qu'un collage les poserait : du texte, VRAI ou FAUX pour un booléen. */
  const collees = lignes => lignes.map(l => l.map(v => v && typeof v === 'object' ? (v.b !== undefined ? (v.b ? 'VRAI' : 'FAUX') : String(v.n))
    : String(v === undefined || v === null ? '' : v)));
  /* La règle, récrite ici à part, sans le code qu'elle vérifie : une cellule porte un PSN quand l'un de ses
     morceaux, coupés aux virgules, points-virgules et espaces, l'est à la lettre ; le type se lit sans casse ni espaces. */
  const porte = (cellule, psn) => String(cellule || '').split(/[\s,;]+/).some(j => j.toLowerCase() === psn.toLowerCase());
  const estWD = t => String(t || '').replace(/\s+/g, '').toLowerCase() === 'wd';
  const I_PSN = ENTETE_COMPLET.indexOf('VALIDITY PSN FULL'), I_TYPE = ENTETE_COMPLET.indexOf('DIAGRAM TYPE');
  /* Chaque morceau de fichier lu passe par Blob.slice : compté, il dit si un PSN changé relit le fichier. */
  async function compterLectures(page) {
    await page.evaluate(() => {
      if (window.__tranches === undefined) {
        const tranche = Blob.prototype.slice;
        Blob.prototype.slice = function () { window.__tranches++; return tranche.apply(this, arguments); };
      }
      window.__tranches = 0;
    });
  }
  const lectures = page => page.evaluate(() => window.__tranches);
  /* Ce que la case SEE dit du tri : ce qui manque au fichier, la case « importer sans ce tri », l'aide. */
  function triDeLaCase(page) {
    return page.evaluate(() => {
      const el = document.querySelector('[data-case="see"]'), q = s => el.querySelector(s);
      return { manque: q('.manque').hidden ? '' : q('.manque-texte').textContent, libelle: q('.manque').hidden ? '' : q('.sans-tri span').textContent,
               aide: q('.tri-aide').hidden ? '' : q('.tri-aide').textContent };
    });
  }
  const lignesDuDiagnostic = ctx => ctx.diagnostic().split('\n');
  const ditTout = (lignes, attendues) => attendues.filter(t => lignes.indexOf(t) === -1);
  const IMPORT_MENU = 'menu Suivi FWD → Importer les exports GATES et SEE…';

  // =================================================================
  section('Le PSN se compare en entier : 4530 n’est ni 14530 ni 45301');
  {
    const c = classeur();
    const ctx = serveur(c);
    const voulus = { '4530': true };
    const psnCas = [['4530', true], ['4520,4530, 4540', true], ['4520;4530', true], ['  4530  ', true], ['4510, 4520, 4530', true], ['4700 4530', true],
      ['14530', false], ['45301', false], ['4531', false], ['', false], ['4 530', false], ['4520,14530,45301', false]];
    const ratesPsn = psnCas.filter(x => ctx.cellulePorteUnPsn(x[0], voulus) !== x[1]);
    verifier('une cellule porte 4530 quand l’un de ses morceaux — coupés aux virgules, points-virgules et espaces — est 4530, au premier rang, au milieu ou au dernier ; jamais 14530, 45301, 4531, « 4 530 », ni une cellule vide',
      !ratesPsn.length, ratesPsn.map(x => JSON.stringify(x[0])).join(', '));
    verifier('les morceaux d’une cellule, réduits (casse, espaces autour), sans morceau vide', JSON.stringify(ctx.jetonsPsn(' 4520 ;A4530,, 4540 ')) === '["4520","a4530","4540"]',
      JSON.stringify(ctx.jetonsPsn(' 4520 ;A4530,, 4540 ')));
    const filtre = ctx.filtresSecondeBase()[0];
    const typeCas = [['WD', true], ['wd', true], [' WD ', true], ['Wd', true], ['W D', true], ['PH', false], ['GH', false], ['', false], ['WDX', false]];
    const ratesType = typeCas.filter(x => !!filtre.permises[ctx.cleTri(x[0])] !== x[1]);
    verifier('DIAGRAM TYPE : « WD » à la casse et aux espaces près (wd, « WD », W D) ; PH, GH, une cellule vide, « WDX » ne passent pas',
      filtre.colonne === 'DIAGRAM TYPE' && !ratesType.length, ratesType.map(x => JSON.stringify(x[0])).join(', '));
    const saisi = t => { try { return JSON.stringify(ctx.psnSaisi(t)); } catch (e) { return 'refus : ' + e.message; } };
    verifier('un PSN tapé : « 4530 ; 4531, 4530 » donne 4530 et 4531, sans doublon ; « A4530 » passe (des lettres au besoin) ; vide, aucun ; « 4530! », un PSN de 21 caractères et 21 PSN sont refusés, et disent pourquoi',
      saisi(' 4530 ; 4531, 4530 ') === '["4530","4531"]' && saisi('A4530') === '["A4530"]' && saisi('') === '[]' &&
      saisi('4530!') === 'refus : « 4530! » n’est pas un PSN : des chiffres (des lettres au besoin), 20 caractères au plus, plusieurs séparés par des virgules — comme « 4530 ».' &&
      /n’est pas un PSN/.test(saisi('1'.repeat(21))) && saisi(Array.from({ length: 21 }, (_, i) => String(4500 + i)).join(',')) === 'refus : Trop de PSN : 21 (au plus 20).',
      [saisi('4530!'), saisi('1'.repeat(21))].join(' | '));
    vm.runInContext('CONFIG.RAPPROCHEMENT.PSN = { hdk: ["4530", "4531"] };', ctx);
    const enListe = JSON.stringify(ctx.psnDuContrat('HDK'));
    vm.runInContext('CONFIG.RAPPROCHEMENT.PSN = { HDK: "4530, 4531" };', ctx);
    const enTexte = JSON.stringify(ctx.psnDuContrat('hdk'));
    vm.runInContext('CONFIG.RAPPROCHEMENT.PSN = { HDK: "4530" };', ctx);
    verifier('le PSN de la configuration se trouve au nom du contrat, casse indifférente, écrit en liste ou en « 4530, 4531 »',
      enListe === JSON.stringify({ psn: ['4530', '4531'], source: 'configuration' }) && enTexte === enListe, enListe + ' / ' + enTexte);

    /* Chaque façon d'écrire le PSN croisée avec chaque façon d'écrire le type : 12 × 9 = 108 lignes. */
    const tri = i => ({ psn: psnCas[i % psnCas.length][0], type: typeCas[Math.floor(i / psnCas.length)][0] });
    const n = psnCas.length * typeCas.length;
    const garde = typeCas.filter(x => x[1]).length * psnCas.length, pourHDK = typeCas.filter(x => x[1]).length * psnCas.filter(x => x[1]).length;
    const attendus = collees(lignesSeeComplet(n, tri)).slice(3).filter(l => estWD(l[I_TYPE]) && porte(l[I_PSN], '4530')).map(l => l[0]);
    const page = await fenetre(ctx);
    const k = await poser(page, 'see', [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeComplet(n, tri) }]);
    verifier('la fenêtre applique la même règle en lisant : ' + n + ' lignes lues, ' + garde + ' en WD gardées, ' + pourHDK + ' à HDK (4530)',
      k.etat === 'lu' && new RegExp('^' + n + ' lignes lues, ' + garde + ' en WD \\(DIAGRAM TYPE WD\\)').test(k.lu) && k.gardees === String(garde) &&
      porteur(k, 'HDK').lignes === String(pourHDK) && attendus.length === pourHDK, JSON.stringify([k.lu, k.gardees, k.porteurs, attendus.length]));
    const r = await lancer(page);
    const f = c.getSheetByName('SEE HDK');
    verifier('importé : « SEE HDK » porte exactement ces ' + pourHDK + ' plans, dans l’ordre de l’extract',
      /\bok\b/.test(r.classe) && !!f && JSON.stringify(f.valeurs.slice(2).map(l => l[0])) === JSON.stringify(attendus), r.texte + ' / ' + (f && f.valeurs.length));
    await page.close();
    /* Le même extract collé à la main dans un classeur : la page le trie à la lecture, et garde les mêmes. */
    const c2 = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE HDK', collees(lignesSeeComplet(n, tri)))]);
    const lu = serveur(c2).lireSecondeBase(c2, 'HDK');
    verifier('… et collé à la main, la page le trie à la lecture : les mêmes ' + pourHDK + ' plans',
      lu.etat === 'ok' && lu.tri.source === 'lecture' && lu.tri.lues === n && JSON.stringify(lu.rapprochement.lignes.map(l => l.NAME)) === JSON.stringify(attendus),
      JSON.stringify([lu.etat, lu.tri && lu.tri.gardees]));
  }

  // =================================================================
  section('Deux contrats, deux PSN, un seul extract SEE : chacun ses lignes, sans relire le fichier');
  {
    const refA = i => refGates(i), refB = i => refGates(i, 500);
    const c = new Classeur([ongletGates('HDK', gates(40, { refs: refA })), ongletGates('THS', gates(30, { refs: refB }))]);
    const ctx = serveur(c);
    /* 100 lignes : les 40 plans de HDK (4520,4530), les 30 de THS (4610), 5 plans des deux machines
       (« 4530;4610 »), 15 lignes PH de THS, 10 d'une autre machine (4700). */
    const tri = i => i < 40 ? { psn: '4520,4530', type: 'WD' }
      : i < 70 ? { psn: '4610', type: 'WD', nom: nomDe(i - 40 + 500), sol: String((i - 40) % 3 + 1).padStart(3, '0'), custV: 'ABC'[(i - 40) % 3] }
        : i < 75 ? { psn: '4530;4610', type: 'WD' } : i < 90 ? { psn: '4610', type: 'PH' } : { psn: '4700', type: 'WD' };
    const page = await fenetre(ctx);
    const vide = await laCase(page, 'see'), avantFichier = await triDeLaCase(page);
    verifier('avant tout fichier, la case SEE dit comment l’extract se partage, et le PSN de chaque contrat : HDK 4530 (de la configuration), THS aucun — pas de base pour lui',
      avantFichier.aide === 'Le PSN de chaque contrat — le numéro de sa machine dans VALIDITY PSN FULL — choisit ses lignes, parmi celles en DIAGRAM TYPE WD. Un PSN tapé ici est gardé pour les fois suivantes.' &&
      porteur(vide, 'HDK').psn === '4530' && porteur(vide, 'HDK').enr === 'de la configuration' && porteur(vide, 'HDK').part === '' &&
      porteur(vide, 'THS').psn === '' && porteur(vide, 'THS').part === 'pas de PSN : pas de base SEE pour ce contrat', JSON.stringify([avantFichier, vide.porteurs]));
    let k = await poser(page, 'see', [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeComplet(100, tri) }]);
    verifier('l’extract lu : 100 lignes, 85 en WD gardées ; HDK en a 45 (ses 40, et les 5 des deux machines), THS, sans PSN, aucune — dit en clair',
      /^100 lignes lues, 85 en WD/.test(k.lu) && k.gardees === '85' && porteur(k, 'HDK').part === '— 45 lignes WD → créera « SEE HDK »' &&
      porteur(k, 'THS').part === ': pas de base SEE tant que le PSN n’est pas donné', JSON.stringify(k));
    await compterLectures(page);
    /* Le PSN de THS tapé : sa part se recompte à la frappe, avant même d'être enregistrée. */
    await page.fill('[data-case="see"] .porteur[data-contrat="THS"] input', '4610');
    const aussitot = porteur(await laCase(page, 'see'), 'THS');
    await attendreLecture(page);
    k = await laCase(page, 'see');
    verifier('« 4610 » tapé pour THS : sa part se recompte à la frappe (35 lignes, dont les 5 « 4530;4610 »), sans relire le fichier ; puis le PSN est enregistré, une fois',
      aussitot.part === '— 35 lignes WD → créera « SEE THS »' && aussitot.enr === 'enregistrement…' && porteur(k, 'THS').enr === 'enregistré' && k.etat === 'lu' &&
      (await lectures(page)) === 0 && page.__appels.filter(x => x === 'importEnregistrerPsn').length === 1,
      JSON.stringify([aussitot, porteur(k, 'THS'), await lectures(page), page.__appels]));
    verifier('gardé dans le classeur, au nom de l’onglet : le serveur le rend comme tapé dans la fenêtre ; HDK garde celui de la configuration',
      ctx.__proprietes.SUIVI_FWD_PSN === JSON.stringify({ THS: ['4610'] }) && JSON.stringify(ctx.psnDuContrat('THS')) === JSON.stringify({ psn: ['4610'], source: 'fenetre' }) &&
      JSON.stringify(ctx.psnDuContrat('HDK')) === JSON.stringify({ psn: ['4530'], source: 'configuration' }), ctx.__proprietes.SUIVI_FWD_PSN);
    k = await taperPsn(page, 'THS', '4610, 4700');
    verifier('deux PSN pour un contrat, « 4610, 4700 » : les lignes de l’une ou l’autre machine (45)', porteur(k, 'THS').part === '— 45 lignes WD → créera « SEE THS »',
      JSON.stringify(porteur(k, 'THS')));
    const gardeAvant = ctx.__proprietes.SUIVI_FWD_PSN, appelsAvant = page.__appels.length;
    k = await taperPsn(page, 'THS', '4610!');
    let ui = await fenetreEtat(page);
    const faux = '« 4610! » n’est pas un PSN : des chiffres (des lettres au besoin), plusieurs séparés par des virgules — comme « 4530 ».';
    verifier('« 4610! » n’est pas un PSN : la case le dit sous le champ, « Importer » attend et dit pourquoi ; rien n’est enregistré',
      porteur(k, 'THS').enr === faux && porteur(k, 'THS').part === '' && ui.desactive && ui.blocage === 'PSN de « THS » : ' + faux &&
      ctx.__proprietes.SUIVI_FWD_PSN === gardeAvant && page.__appels.length === appelsAvant, JSON.stringify([porteur(k, 'THS'), ui.blocage]));
    k = await taperPsn(page, 'THS', '4610');
    k = await taperPsn(page, 'HDK', '');
    verifier('le PSN de HDK effacé : enregistré vide — il l’emporte sur celui de la configuration ; HDK n’a plus de base, dit en clair',
      porteur(k, 'HDK').enr === 'enregistré' && porteur(k, 'HDK').part === ': pas de base SEE tant que le PSN n’est pas donné' &&
      JSON.stringify(ctx.psnDuContrat('HDK')) === JSON.stringify({ psn: [], source: 'fenetre' }), JSON.stringify([porteur(k, 'HDK'), ctx.psnDuContrat('HDK')]));
    k = await taperPsn(page, 'HDK', '4530');
    ui = await fenetreEtat(page);
    verifier('4530 retapé : HDK retrouve ses 45 lignes, « Importer » s’allume', porteur(k, 'HDK').part === '— 45 lignes WD → créera « SEE HDK »' && !ui.desactive &&
      (await lectures(page)) === 0, JSON.stringify([k.porteurs, ui.blocage]));
    await capture(page, 'tri-deux-psn');
    const r = await lancer(page);
    const fH = c.getSheetByName('SEE HDK'), fT = c.getSheetByName('SEE THS');
    const noms = f => f ? f.valeurs.slice(2).map(l => l[0]) : [];
    const deux = [70, 71, 72, 73, 74].map(i => nomDe(i));
    verifier('importé : « SEE HDK » 45 lignes, « SEE THS » 35, chacune sous sa ligne du tri ; les 5 plans « 4530;4610 » sont dans les deux, ni PH ni autre machine',
      /\bok\b/.test(r.classe) && !!fH && fH.valeurs.length === 47 && !!fT && fT.valeurs.length === 37 &&
      fH.valeurs[0][0].indexOf(MARQUE + 'PSN 4530 · DIAGRAM TYPE = WD — 45 lignes gardées sur 100 · « Nommage WD BFLOW.xlsx », le ') === 0 &&
      fT.valeurs[0][0].indexOf(MARQUE + 'PSN 4610 · DIAGRAM TYPE = WD — 35 lignes gardées sur 100 · « Nommage WD BFLOW.xlsx », le ') === 0 &&
      deux.every(x => noms(fH).indexOf(x) !== -1 && noms(fT).indexOf(x) !== -1) && noms(fH).indexOf(nomDe(90)) === -1 && noms(fT).indexOf(nomDe(80)) === -1 &&
      /45 lignes dans l’onglet « SEE HDK » \(3 colonnes ; PSN 4530 · WD\)/.test(r.texte) && /35 lignes dans l’onglet « SEE THS » \(3 colonnes ; PSN 4610 · WD\)/.test(r.texte),
      r.texte + ' / ' + JSON.stringify([fH && fH.valeurs[0][0], fT && fT.valeurs[0][0]]));
    await page.close();
    /* La fenêtre rouverte : les paramètres d'abord (ils posent un nouveau jeton), puis la fenêtre. */
    const P2 = parametres(ctx);
    const page2 = await fenetre(ctx);
    const k2 = await laCase(page2, 'see');
    verifier('la fenêtre rouverte : chaque PSN tapé est là, « enregistré » — HDK 4530, THS 4610 — et les paramètres le disent venu de la fenêtre',
      porteur(k2, 'THS').psn === '4610' && porteur(k2, 'THS').enr === 'enregistré' && porteur(k2, 'HDK').psn === '4530' && porteur(k2, 'HDK').enr === 'enregistré' &&
      P2.contrats.map(x => x.id + ':' + x.psn.join('/') + ':' + x.psnSource).join() === 'HDK:4530:fenetre,THS:4610:fenetre',
      JSON.stringify([k2.porteurs, P2.contrats.map(x => [x.id, x.psn, x.psnSource])]));
    await page2.close();
    const lH = ctx.lireSecondeBase(c, 'HDK'), lT = ctx.lireSecondeBase(c, 'THS');
    verifier('la page lit chaque base avec le tri noté à l’import : « PSN 4530 · WD » (45 lignes), « PSN 4610 · WD » (35)',
      lH.etat === 'ok' && lH.tri.source === 'import' && lH.tri.lues === 100 && lH.rapprochement.filtre === 'PSN 4530 · WD' && lH.rapprochement.lignes.length === 45 &&
      lT.etat === 'ok' && lT.rapprochement.filtre === 'PSN 4610 · WD' && lT.rapprochement.lignes.length === 35, JSON.stringify([lH.tri, lT.tri]));
  }

  // =================================================================
  section('Un nouveau contrat : son PSN tapé dans la case SEE, gardé une fois le contrat créé');
  {
    const c = new Classeur([ongletGates('HDK', gates(40))]);
    const ctx = serveur(c);
    const page = await fenetre(ctx);
    await ajouterContrat(page, undefined, { nom: 'export_neo.xlsx', contenu: xlsxGates(gates(20, { prefixe: 'NEO', groupe: 'NEO' })) });
    /* 12 lignes de HDK (4530), 8 de NEO (4800), 5 PH de NEO. */
    const tri = i => i < 12 ? { psn: '4530', type: 'WD' } : i < 20 ? { psn: '4800', type: 'WD' } : { psn: '4800', type: 'PH' };
    let k = await poser(page, 'see', [{ nom: 'Nommage WD BFLOW.xlsx', contenu: seeComplet(25, tri) }]);
    verifier('le contrat ajouté a sa ligne dans la case SEE, « NEO (nouveau) », sans PSN : pas de base tant qu’il n’est pas donné',
      k.porteurs.map(p => p.contrat).join() === 'HDK,NEO' && (await page.textContent('[data-case="see"] .porteur[data-contrat="NEO"] .contrat')) === 'NEO (nouveau)' &&
      porteur(k, 'NEO').psn === '' && porteur(k, 'NEO').part === ': pas de base SEE tant que le PSN n’est pas donné', JSON.stringify(k.porteurs));
    const appels = page.__appels.length;
    k = await taperPsn(page, 'NEO', '4800');
    verifier('son PSN tapé : sa part se compte (8 lignes WD) ; rien n’est encore enregistré — le contrat n’existe pas',
      porteur(k, 'NEO').part === '— 8 lignes WD → créera « SEE NEO »' && porteur(k, 'NEO').enr === '' && page.__appels.length === appels,
      JSON.stringify([porteur(k, 'NEO'), page.__appels.slice(appels)]));
    page.__appels = [];
    const r = await lancer(page);
    const a = page.__appels, iFin = a.indexOf('importSecondeBaseFin'), iPsn = a.indexOf('importEnregistrerPsn'), iSee = a.indexOf('importSecondeBaseDebut', iFin);
    verifier('importé : NEO créé, puis son PSN gardé, puis les bases — « SEE HDK » (12 lignes) et « SEE NEO » (8)',
      /\bok\b/.test(r.classe) && iFin !== -1 && iPsn > iFin && iSee > iPsn && JSON.stringify(ctx.psnDuContrat('NEO')) === JSON.stringify({ psn: ['4800'], source: 'fenetre' }) &&
      !!c.getSheetByName('SEE NEO') && c.getSheetByName('SEE NEO').valeurs.length === 10 && c.getSheetByName('SEE HDK').valeurs.length === 14 &&
      /8 lignes dans l’onglet « SEE NEO » \(3 colonnes ; PSN 4800 · WD\)/.test(r.texte), r.texte + ' / ' + a.join(','));
    k = await laCase(page, 'see');
    verifier('la liste des contrats relue : NEO est un contrat comme les autres, son PSN « enregistré »',
      porteur(k, 'NEO').psn === '4800' && porteur(k, 'NEO').enr === 'enregistré' && (await page.textContent('[data-case="see"] .porteur[data-contrat="NEO"] .contrat')) === 'NEO' &&
      (await fenetreEtat(page)).cases.join() === 'g:HDK,g:NEO,see', JSON.stringify(k.porteurs));
    await page.close();
  }

  // =================================================================
  section('Une colonne du tri manque à l’extract : « Importer » attend, ou « importer sans ce tri »');
  {
    const c = classeur({ ths: true });
    const ctx = serveur(c, psnGardes({ THS: ['4610'] }));
    let page = await fenetre(ctx);
    /* Sans DIAGRAM TYPE : 30 lignes, 20 de HDK (4530), 10 de THS (4610). */
    let k = await poser(page, 'see', [{ nom: 'sans-type.xlsx', contenu: seeComplet(30, i => ({ psn: i < 20 ? '4530' : '4610', type: 'PH' }), { sans: ['DIAGRAM TYPE'] }) }]);
    let t = await triDeLaCase(page), ui = await fenetreEtat(page);
    verifier('un extract sans DIAGRAM TYPE : la case dit ce qui manque ; « importer sans ce tri » est possible — le PSN partage encore l’extract — et « Importer » l’attend',
      t.manque === '✗ « sans-type.xlsx » n’a pas de colonne DIAGRAM TYPE : les lignes ne se trient pas sur DIAGRAM TYPE.' &&
      t.libelle === 'importer sans ce tri — toutes les lignes, quel que soit leur DIAGRAM TYPE' && k.sansTri.possible && !k.sansTri.coche &&
      porteur(k, 'HDK').part === '— 20 lignes → créera « SEE HDK »' && porteur(k, 'THS').part === '— 10 lignes → créera « SEE THS »' &&
      ui.desactive && ui.blocage === '« sans-type.xlsx » n’a pas de colonne DIAGRAM TYPE : cocher « importer sans ce tri » dans la case SEE, ou retirer le fichier.',
      JSON.stringify([t, k.sansTri, k.porteurs, ui.blocage]));
    await capture(page, 'tri-colonne-manquante');
    await page.check('[data-case="see"] .sans-tri input');
    let r = await lancer(page);
    const fH = c.getSheetByName('SEE HDK'), fT = c.getSheetByName('SEE THS');
    verifier('coché : chaque contrat reçoit ses lignes par le PSN seul, tous types confondus — la ligne du tri ne parle que du PSN',
      /\bok\b/.test(r.classe) && fH.valeurs.length === 22 && fT.valeurs.length === 12 &&
      fH.valeurs[0][0].indexOf(MARQUE + 'PSN 4530 — 20 lignes gardées sur 30 · « sans-type.xlsx », le ') === 0 &&
      /20 lignes dans l’onglet « SEE HDK » \(3 colonnes ; PSN 4530\)/.test(r.texte), r.texte + ' / ' + (fH && fH.valeurs[0][0]));
    const lu = ctx.lireSecondeBase(c, 'HDK');
    verifier('la page relit le tri noté : « PSN 4530 », sans le type ; le Diagnostic le dit',
      lu.tri.source === 'import' && lu.rapprochement.filtre === 'PSN 4530' &&
      lignesDuDiagnostic(ctx).indexOf('   SEE HDK : 20 lignes, triées à l’import sur 30 lignes (PSN 4530)') !== -1, JSON.stringify(lu.tri));
    /* Sans VALIDITY PSN FULL, deux contrats : l'extract ne se partage pas. */
    const sansPsn = seeComplet(30, i => ({ psn: '', type: i % 3 ? 'WD' : 'PH' }), { sans: ['VALIDITY PSN FULL'] });
    k = await poser(page, 'see', [{ nom: 'sans-psn.xlsx', contenu: sansPsn }]);
    t = await triDeLaCase(page);
    ui = await fenetreEtat(page);
    verifier('sans VALIDITY PSN FULL, avec deux contrats : l’extract ne se partage pas — la case le dit, « importer sans ce tri » est impossible, « Importer » attend un autre extract',
      t.manque === '✗ « sans-psn.xlsx » n’a pas de colonne VALIDITY PSN FULL : l’extract ne se trie pas par machine (le PSN de chaque contrat).' &&
      t.libelle === 'importer sans ce tri — impossible avec 2 contrats : l’extract ne se partage pas sans VALIDITY PSN FULL' && !k.sansTri.possible &&
      k.porteurs.every(p => p.part === 'pas de base : l’extract ne se partage pas sans VALIDITY PSN FULL') && ui.desactive &&
      ui.blocage === '« sans-psn.xlsx » n’a pas de colonne VALIDITY PSN FULL : sans elle, l’extract ne se partage pas entre les 2 contrats — demander l’extract SEE avec cette colonne, ou retirer le fichier.',
      JSON.stringify([t, k.sansTri, k.porteurs, ui.blocage]));
    await page.close();
    /* Le même extract, un seul contrat : il peut tout recevoir, une fois la case cochée. */
    const c1 = classeur();
    const ctx1 = serveur(c1);
    page = await fenetre(ctx1);
    k = await poser(page, 'see', [{ nom: 'sans-psn.xlsx', contenu: sansPsn }]);
    t = await triDeLaCase(page);
    verifier('… avec un seul contrat : possible — « tout l’extract ira dans « SEE HDK » », ses 20 lignes WD',
      t.libelle === 'importer sans ce tri — tout l’extract ira dans « SEE HDK »' && k.sansTri.possible &&
      porteur(k, 'HDK').part === '— tout l’extract : 20 lignes WD → créera « SEE HDK », une fois « importer sans ce tri » coché', JSON.stringify([t, k.porteurs]));
    await page.check('[data-case="see"] .sans-tri input');
    r = await lancer(page);
    const f1 = c1.getSheetByName('SEE HDK');
    const l1 = ctx1.lireSecondeBase(c1, 'HDK'), d1 = lignesDuDiagnostic(ctx1);
    verifier('coché : les 20 lignes WD dans « SEE HDK », la ligne du tri ne parle que du type ; la page et le Diagnostic le disent, sans PSN à comparer',
      /\bok\b/.test(r.classe) && f1.valeurs.length === 22 && f1.valeurs[0][0].indexOf(MARQUE + 'DIAGRAM TYPE = WD — 20 lignes gardées sur 30 · « sans-psn.xlsx », le ') === 0 &&
      /20 lignes dans l’onglet « SEE HDK » \(3 colonnes ; WD\)/.test(r.texte) && l1.tri.source === 'import' && l1.tri.psn === null && l1.rapprochement.filtre === 'WD' &&
      d1.indexOf('   SEE HDK : 20 lignes, triées à l’import sur 30 lignes (DIAGRAM TYPE WD)') !== -1 && !d1.some(x => /a été trié à l’import sur le PSN/.test(x)),
      r.texte + ' / ' + d1.filter(x => /SEE/.test(x)).join(' / '));
    /* Que des PH et des GH : rien à garder. */
    k = await poser(page, 'see', [{ nom: 'que-des-PH.xlsx', contenu: seeComplet(30, i => ({ psn: '4530', type: i % 2 ? 'PH' : 'GH' })) }]);
    verifier('un extract sans une ligne WD : la case le refuse, et dit pourquoi — est-ce bien l’extract SEE ?',
      k.etat === 'erreur' && k.lu === '✗ Aucune des 30 lignes de « Nommage » n’est en DIAGRAM TYPE WD : rien n’est gardé. Est-ce bien l’extract SEE (« Nommage WD BFLOW ») ?', k.lu);
    /* Une autre machine seulement : aucune ligne pour le PSN de HDK. */
    k = await poser(page, 'see', [{ nom: 'autre-machine.xlsx', contenu: seeComplet(12, () => ({ psn: '4700', type: 'WD' })) }]);
    ui = await fenetreEtat(page);
    verifier('un extract d’une autre machine : HDK n’y a aucune ligne, « SEE HDK » ne sera pas touché ; « Importer » attend et dit de vérifier le PSN',
      porteur(k, 'HDK').part === '— aucune ligne WD pour ce PSN : « SEE HDK » ne sera pas touché' && ui.desactive &&
      ui.blocage === 'Aucune ligne de l’extract SEE ne porte le PSN des contrats (HDK 4530) : vérifier les PSN, ou retirer le fichier.', JSON.stringify([k.porteurs, ui.blocage]));
    await page.close();
    /* Aucun contrat n'a de PSN : le seul l'a vu vidé dans la fenêtre — ce vide l'emporte sur la configuration. */
    const c7 = classeur();
    page = await fenetre(serveur(c7, psnGardes({ HDK: [] })));
    k = await poser(page, 'see', [{ nom: 'see.xlsx', contenu: seeComplet(12, () => ({ psn: '4530', type: 'WD' })) }]);
    ui = await fenetreEtat(page);
    verifier('le PSN de HDK vidé une fois précédente : le champ reste vide (la configuration ne le remplit pas) ; aucun contrat n’a de PSN, « Importer » attend et dit quoi taper',
      porteur(k, 'HDK').psn === '' && porteur(k, 'HDK').part === ': pas de base SEE tant que le PSN n’est pas donné' && ui.desactive &&
      ui.blocage === 'Aucun contrat n’a de PSN : taper celui de chaque contrat (le numéro de sa machine) dans la case SEE, ou retirer le fichier.', JSON.stringify([k.porteurs, ui.blocage]));
    await page.close();
  }

  // =================================================================
  section('« Garder aussi les autres colonnes » sur l’extract trié : les lignes du contrat, avec toutes leurs colonnes');
  {
    const c = classeur({ ths: true });
    const ctx = serveur(c, psnGardes({ THS: ['4610'] }));
    const page = await fenetre(ctx);
    /* 30 lignes de HDK en WD, 10 de THS en WD, 10 de HDK en PH. */
    const tri = i => i < 30 ? { psn: '4530', type: 'WD' } : i < 40 ? { psn: '4610', type: 'WD' } : { psn: '4530', type: 'PH' };
    const r = await importer(page, 'Nommage WD BFLOW.xlsx', seeComplet(50, tri), { toutes: true });
    const f = c.getSheetByName('SEE HDK'), g = c.getSheetByName('SEE THS');
    const nommees = ENTETE_COMPLET.filter(Boolean), iPsn = nommees.indexOf('VALIDITY PSN FULL'), iType = nommees.indexOf('DIAGRAM TYPE');
    verifier('« SEE HDK » : la ligne du tri, l’en-tête des ' + nommees.length + ' colonnes nommées, puis les 30 lignes de HDK en WD — pas une PH, pas une de THS ; « SEE THS » ses 10',
      /\bok\b/.test(r.etat.classe) && !!f && f.valeurs.length === 32 && f.valeurs[1].join('|') === nommees.join('|') &&
      f.valeurs.slice(2).every(l => l[iType] === 'WD' && l[iPsn] === '4530') && f.valeurs[0].length === nommees.length &&
      f.valeurs[0][0].indexOf(MARQUE + 'PSN 4530 · DIAGRAM TYPE = WD — 30 lignes gardées sur 50 · ') === 0 && !!g && g.valeurs.length === 12 &&
      new RegExp('30 lignes dans l’onglet « SEE HDK » \\(' + nommees.length + ' colonnes ; PSN 4530 · WD\\)').test(r.etat.texte),
      r.etat.texte + ' / ' + JSON.stringify(f && f.valeurs.slice(0, 3)));
    const lu = ctx.lireSecondeBase(c, 'HDK');
    verifier('la page relit « SEE HDK » : il porte VALIDITY PSN FULL et DIAGRAM TYPE, elle refait donc le tri — 30 lignes, 30 gardées — avec ses ' + nommees.length + ' colonnes',
      lu.etat === 'ok' && lu.ligneEntete === 2 && lu.tri.source === 'lecture' && lu.tri.lues === 30 && lu.tri.gardees === 30 && lu.rapprochement.filtre === 'PSN 4530 · WD' &&
      lu.rapprochement.colonnes.length === nommees.length, JSON.stringify([lu.etat, lu.ligneEntete, lu.tri]));
    let d = lignesDuDiagnostic(ctx);
    verifier('le Diagnostic : « SEE HDK : 30 lignes, 30 gardées (PSN 4530 · DIAGRAM TYPE WD) »', d.indexOf('   SEE HDK : 30 lignes, 30 gardées (PSN 4530 · DIAGRAM TYPE WD)') !== -1,
      d.filter(x => /SEE/.test(x)).join(' / '));
    /* Le PSN de THS changé après coup : son onglet, qui porte la colonne des PSN, est retrié à la lecture. */
    ctx.importEnregistrerPsn(jetonDe(ctx), 'THS', '4530');
    d = lignesDuDiagnostic(ctx);
    verifier('le PSN de THS changé après l’import (4530) : « SEE THS » est retrié à la lecture — aucune ligne gardée, et le Diagnostic demande si c’est le bon PSN',
      ctx.lireSecondeBase(c, 'THS').rapprochement.lignes.length === 0 &&
      d.indexOf('⚠ SEE THS : aucune ligne gardée sur 10 lignes — le PSN 4530 n’est dans aucune ligne gardée par les autres tris : est-ce le bon ?') !== -1,
      d.filter(x => /SEE THS/.test(x)).join(' / '));
    await page.close();
  }

  // =================================================================
  section('Un gros extract SEE : 60 000 lignes, 5 % gardées, sans figer la fenêtre');
  {
    const n = 60000;
    const c = classeur({ ths: true });
    const ctx = serveur(c, psnGardes({ THS: ['4610'] }));
    /* Une ligne sur dix en WD — la moitié pour HDK (4520,4530,4540), l'autre pour THS (4610) ; les autres en PH ou GH. */
    const tri = i => i % 10 === 0 ? { psn: i % 20 === 0 ? '4520,4530,4540' : '4610', type: 'WD' } : { psn: '4530', type: i % 2 ? 'PH' : 'GH' };
    const fichier = seeComplet(n, tri);
    const page = await fenetre(ctx);
    /* Un battement toutes les 20 ms dès que le fichier est remis à la fenêtre : le plus long silence dit si la lecture, puis l'envoi, l'ont figée. */
    await page.evaluate(() => {
      window.__battements = [];
      document.querySelector('[data-case="see"] input[type=file]').addEventListener('change', () => {
        window.__battements.push(performance.now());
        window.__minuteur = setInterval(() => window.__battements.push(performance.now()), 20);
      }, { capture: true, once: true });
    });
    const t0 = Date.now();
    let k = await poser(page, 'see', [{ nom: 'Nommage WD BFLOW.xlsx', contenu: fichier }]);
    const duree = Date.now() - t0;
    verifier('un extract de ' + (fichier.length / 1048576).toFixed(1) + ' Mo, 60 000 lignes × 23 colonnes, lu en ' + (duree / 1000).toFixed(1) + ' s : 6 000 lignes WD gardées en mémoire — 3 000 pour HDK, 3 000 pour THS',
      k.etat === 'lu' && k.lu.indexOf(fine(n) + ' lignes lues, ' + fine(6000) + ' en WD (DIAGRAM TYPE WD), colonnes NAME, SOL., Cust.V') === 0 && k.gardees === '6000' &&
      porteur(k, 'HDK').lignes === '3000' && porteur(k, 'THS').lignes === '3000', JSON.stringify([k.lu, k.gardees, k.porteurs]));
    await compterLectures(page);
    const recompte = await page.evaluate(() => {
      const champ = document.querySelector('[data-case="see"] .porteur[data-contrat="THS"] input');
      const debut = performance.now();
      champ.value = '4610, 4530';
      champ.dispatchEvent(new Event('input', { bubbles: true }));
      return { ms: performance.now() - debut, lignes: champ.closest('.porteur').getAttribute('data-lignes') };
    });
    await attendreLecture(page);
    k = await taperPsn(page, 'THS', '4610');
    verifier('un PSN changé se recompte sur les 6 000 lignes gardées, sans relire le fichier : « 4610, 4530 » donne les 6 000 à THS en ' + recompte.ms.toFixed(0) + ' ms ; « 4610 » à nouveau, 3 000',
      recompte.lignes === '6000' && recompte.ms < 250 && porteur(k, 'THS').lignes === '3000' && (await lectures(page)) === 0, JSON.stringify([recompte, await lectures(page)]));
    const r = await lancer(page, 300000);
    const silence = await page.evaluate(() => {
      clearInterval(window.__minuteur);
      let m = 0;
      for (let i = 1; i < window.__battements.length; i++) m = Math.max(m, window.__battements[i] - window.__battements[i - 1]);
      return Math.round(m);
    });
    const fH = c.getSheetByName('SEE HDK'), fT = c.getSheetByName('SEE THS');
    verifier('importé : « SEE HDK » et « SEE THS », 3 000 lignes chacune, sous leur ligne du tri (« 3 000 lignes gardées sur 60 000 »)',
      /\bok\b/.test(r.classe) && !!fH && fH.valeurs.length === 3002 && !!fT && fT.valeurs.length === 3002 &&
      fH.valeurs[0][0].indexOf(MARQUE + 'PSN 4530 · DIAGRAM TYPE = WD — ' + fine(3000) + ' lignes gardées sur ' + fine(n) + ' · ') === 0 &&
      fT.valeurs[0][0].indexOf(MARQUE + 'PSN 4610 · DIAGRAM TYPE = WD — ' + fine(3000) + ' lignes gardées sur ' + fine(n) + ' · ') === 0,
      r.texte + ' / ' + JSON.stringify([fH && fH.valeurs[0][0], fT && fT.valeurs.length]));
    verifier('la fenêtre ne s’est jamais figée plus d’une seconde, de la lecture à la fin de l’envoi (plus long silence : ' + silence + ' ms)', silence < 1000, silence + ' ms');
    const lu = ctx.lireSecondeBase(c, 'HDK');
    verifier('la page relit le nombre du fichier dans la ligne du tri : 3 000 lignes gardées sur 60 000 ; le Diagnostic le dit',
      lu.tri.source === 'import' && lu.tri.lues === n && lu.tri.gardees === 3000 && lu.rapprochement.filtre === 'PSN 4530 · WD' &&
      lignesDuDiagnostic(ctx).indexOf('   SEE HDK : ' + fine(3000) + ' lignes, triées à l’import sur ' + fine(n) + ' lignes (PSN 4530 · DIAGRAM TYPE WD)') !== -1,
      JSON.stringify(lu.tri));
    await page.close();
  }

  // =================================================================
  section('Un extract collé à la main : la page le trie à la lecture, contrat par contrat');
  {
    /* 60 lignes, tour à tour : 4530 en WD, « 4520, 4530 » en PH, 4610 en WD, 14530 en WD. */
    const tri = i => [{ psn: '4530', type: 'WD' }, { psn: '4520, 4530', type: 'PH' }, { psn: '4610', type: 'WD' }, { psn: '14530', type: 'WD' }][i % 4];
    const lignes = collees(lignesSeeComplet(60, tri));
    const attendus = psn => lignes.slice(3).filter(l => estWD(l[I_TYPE]) && porte(l[I_PSN], psn)).map(l => l[0]);
    const c = new Classeur([ongletGates('HDK', gates(40)), ongletGates('THS', gates(30, { prefixe: 'THS' })),
      new Feuille('SEE HDK', lignes.map(l => l.slice())), new Feuille('SEE THS', lignes.map(l => l.slice()))]);
    const ctx = serveur(c);
    ctx.__activerCache();
    const lH = ctx.lireSecondeBase(c, 'HDK');
    verifier('« SEE HDK », l’extract de tous les porteurs collé tel quel : la page le trie à la lecture — PSN 4530 (de la configuration), DIAGRAM TYPE WD — 15 lignes sur 60, les bonnes',
      lH.etat === 'ok' && lH.ligneEntete === 3 && lH.tri.source === 'lecture' && lH.tri.lues === 60 && lH.tri.gardees === 15 && attendus('4530').length === 15 &&
      JSON.stringify(lH.rapprochement.lignes.map(l => l.NAME)) === JSON.stringify(attendus('4530')) && lH.rapprochement.filtre === 'PSN 4530 · WD',
      JSON.stringify([lH.etat, lH.ligneEntete, lH.tri]));
    const lT = ctx.lireSecondeBase(c, 'THS');
    verifier('« SEE THS », le même extract, mais THS n’a pas de PSN : rien plutôt que les plans des autres — pas de comparaison',
      lT.etat === 'sans-psn' && lT.rapprochement === null && lT.tri.sansPsn === true && lT.tri.colonnePsn === 'VALIDITY PSN FULL', JSON.stringify([lT.etat, lT.tri]));
    const pH = ctx.getDonneesPourClient('HDK'), pT = ctx.getDonneesPourClient('THS');
    verifier('le paquet de la page : HDK a sa comparaison, et dit de quelles lignes elle parle (« PSN 4530 · WD ») ; THS n’en a pas',
      !!pH.rapprochement && pH.rapprochement.lignes.length === 15 && pH.rapprochement.filtre === 'PSN 4530 · WD' && !pT.rapprochement,
      JSON.stringify([pH.rapprochement && pH.rapprochement.filtre, pT.rapprochement]));
    let d = lignesDuDiagnostic(ctx);
    let manquent = ditTout(d, [
      '– Tri de SEE (l’extract de tous les porteurs) : le PSN du contrat dans VALIDITY PSN FULL, DIAGRAM TYPE WD.',
      '   PSN : « HDK » 4530 (configuration) · « THS » aucun',
      '   SEE HDK : 60 lignes, 15 gardées (PSN 4530 · DIAGRAM TYPE WD)',
      '⚠ Seconde base « SEE » de « THS » : l’onglet « SEE THS » porte la colonne VALIDITY PSN FULL — l’extract de tous les porteurs —, mais « THS » n’a pas de PSN : ' +
        'pas de comparaison tant qu’il n’est pas donné (ce seraient les plans des autres).',
      '   → ' + IMPORT_MENU + ' : taper le PSN de « THS » dans la case SEE (il y est gardé), ou le mettre dans CONFIG.RAPPROCHEMENT.PSN.']);
    verifier('le Diagnostic dit le tri, le PSN de chaque contrat et d’où il vient, puis, base par base, ce qui est gardé — et pourquoi THS n’a rien, et quoi faire',
      !manquent.length, manquent.join(' | ') + ' — lu : ' + d.filter(x => /SEE|PSN|Tri/.test(x)).join(' / '));
    const jeton = jetonDe(ctx);
    ctx.importEnregistrerPsn(jeton, 'THS', '4610');
    const pT2 = ctx.getDonneesPourClient('THS');
    d = lignesDuDiagnostic(ctx);
    manquent = ditTout(d, ['   PSN : « HDK » 4530 (configuration) · « THS » 4610 (tapé dans la fenêtre d’import)', '   SEE THS : 60 lignes, 15 gardées (PSN 4610 · DIAGRAM TYPE WD)']);
    verifier('le PSN de THS donné (4610) : le paquet en cache est oublié, THS a sa comparaison — 15 lignes, « PSN 4610 · WD » — et le Diagnostic le dit tapé dans la fenêtre',
      !!pT2.rapprochement && pT2.rapprochement.lignes.length === 15 && pT2.rapprochement.filtre === 'PSN 4610 · WD' &&
      JSON.stringify(pT2.rapprochement.lignes.map(l => l.NAME)) === JSON.stringify(attendus('4610')) && !manquent.length,
      manquent.join(' | ') + ' / ' + JSON.stringify(pT2.rapprochement && pT2.rapprochement.filtre));
    ctx.importEnregistrerPsn(jeton, 'HDK', '');
    d = lignesDuDiagnostic(ctx);
    verifier('le PSN de HDK vidé dans la fenêtre : il l’emporte sur la configuration — HDK n’a plus de comparaison, et le Diagnostic dit « vidé »',
      ctx.lireSecondeBase(c, 'HDK').etat === 'sans-psn' && !ctx.getDonneesPourClient('HDK').rapprochement &&
      d.indexOf('   PSN : « HDK » aucun (vidé dans la fenêtre d’import) · « THS » 4610 (tapé dans la fenêtre d’import)') !== -1, d.filter(x => /PSN/.test(x)).join(' / '));
    ctx.importEnregistrerPsn(jeton, 'HDK', '9999');
    d = lignesDuDiagnostic(ctx);
    verifier('un PSN qui n’est dans aucune ligne : la base est vide, le Diagnostic demande si c’est le bon',
      ctx.lireSecondeBase(c, 'HDK').rapprochement.lignes.length === 0 &&
      d.indexOf('⚠ SEE HDK : aucune ligne gardée sur 60 lignes — le PSN 9999 n’est dans aucune ligne gardée par les autres tris : est-ce le bon ?') !== -1,
      d.filter(x => /SEE HDK/.test(x)).join(' / '));

    /* Collé sans DIAGRAM TYPE : le tri se fait sur ce qui est là, et le Diagnostic dit ce qui manque. */
    const c2 = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE HDK', collees(lignesSeeComplet(60, tri, { sans: ['DIAGRAM TYPE'] })))]);
    const ctx2 = serveur(c2);
    const l2 = ctx2.lireSecondeBase(c2, 'HDK'), d2 = lignesDuDiagnostic(ctx2);
    verifier('collé sans DIAGRAM TYPE : trié sur le PSN seul (30 lignes portent 4530, pas 14530), et le Diagnostic dit que le type n’a pas pu être trié',
      l2.tri.source === 'lecture' && l2.tri.gardees === 30 && JSON.stringify(l2.tri.absentes) === '["DIAGRAM TYPE"]' && l2.rapprochement.filtre === 'PSN 4530' &&
      d2.indexOf('   SEE HDK : 60 lignes, 30 gardées (PSN 4530)') !== -1 && d2.indexOf('   DIAGRAM TYPE : absente de l’onglet — pas de tri sur cette colonne.') !== -1,
      JSON.stringify(l2.tri) + ' / ' + d2.filter(x => /SEE HDK|DIAGRAM/.test(x)).join(' / '));
    /* Trois colonnes, sans la ligne du tri : lu tel quel, et dit tel. */
    const c3 = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE HDK', [['NAME', 'SOL.', 'Cust.V']].concat(Array.from({ length: 12 }, (_, i) => [nomDe(i), '001', 'A'])))]);
    const ctx3 = serveur(c3);
    const d3 = lignesDuDiagnostic(ctx3);
    verifier('une base de trois colonnes, sans ligne du tri : lue telle quelle — le Diagnostic le dit, sans rien inventer',
      ctx3.lireSecondeBase(c3, 'HDK').tri === null && ctx3.lireSecondeBase(c3, 'HDK').rapprochement.filtre === undefined &&
      d3.indexOf('   SEE HDK : 12 lignes, sans tri — l’onglet ne porte ni VALIDITY PSN FULL ni DIAGRAM TYPE, et n’a pas été trié par la fenêtre d’import : il est lu tel quel.') !== -1,
      d3.filter(x => /SEE HDK/.test(x)).join(' / '));
    /* Une base importée (sa ligne du tri), puis le PSN du contrat changé : le Diagnostic dit de réimporter. */
    const marque = MARQUE + 'PSN 4530 · DIAGRAM TYPE = WD — 15 lignes gardées sur 60 · « Nommage WD BFLOW.xlsx », le 01/10/2026';
    const c4 = new Classeur([ongletGates('HDK', gates(40)), new Feuille('SEE HDK', [[marque, '', ''], ['NAME', 'SOL.', 'Cust.V']]
      .concat(Array.from({ length: 15 }, (_, i) => [nomDe(4 * i), '001', 'A'])))]);
    const ctx4 = serveur(c4);
    let d4 = lignesDuDiagnostic(ctx4);
    const avant = d4.indexOf('   SEE HDK : 15 lignes, triées à l’import sur 60 lignes (PSN 4530 · DIAGRAM TYPE WD)') !== -1 && !d4.some(x => /a été trié à l’import sur le PSN/.test(x));
    ctx4.importEnregistrerPsn(jetonDe(ctx4), 'HDK', '4531');
    d4 = lignesDuDiagnostic(ctx4);
    verifier('une base triée à l’import sur 4530, puis le PSN de HDK changé en 4531 : la page lit toujours la base posée, et le Diagnostic dit de réimporter l’extract',
      avant && ctx4.lireSecondeBase(c4, 'HDK').rapprochement.lignes.length === 15 && ctx4.lireSecondeBase(c4, 'HDK').rapprochement.filtre === 'PSN 4530 · WD' &&
      d4.indexOf('⚠ SEE HDK a été trié à l’import sur le PSN 4530, mais celui de « HDK » est maintenant 4531 : réimporter l’extract SEE (' + IMPORT_MENU + ').') !== -1,
      avant + ' / ' + d4.filter(x => /SEE HDK/.test(x)).join(' / '));
    /* Pas de base du tout, et pas de PSN : le Diagnostic le dit avant même le premier import. */
    const c5 = new Classeur([ongletGates('HDK', gates(40)), ongletGates('THS', gates(30, { prefixe: 'THS' }))]);
    const d5 = lignesDuDiagnostic(serveur(c5));
    verifier('THS sans base ni PSN : le Diagnostic prévient que l’import ne lui fera pas de base tant que le PSN n’est pas donné, et où le taper',
      d5.indexOf('   « THS » n’a pas de PSN : la fenêtre d’import ne lui fera pas de base SEE tant qu’il n’est pas donné — ' + IMPORT_MENU +
        ' : taper le PSN de « THS » dans la case SEE (il y est gardé), ou le mettre dans CONFIG.RAPPROCHEMENT.PSN.') !== -1 &&
      !d5.some(x => /« HDK » n’a pas de PSN/.test(x)), d5.filter(x => /PSN/.test(x)).join(' / '));
  }

  await nav.close();
  try { fs.rmSync(dossier, { recursive: true, force: true }); } catch (e) { /* rien */ }
  console.log('\n═══════════════════════════════════════');
  console.log(reussis + ' test(s) réussi(s), ' + echecs.length + ' échec(s)');
  if (echecs.length) { console.log('\nÉchecs :'); echecs.forEach(e => console.log('  · ' + e)); }
  console.log('\nErreurs JavaScript : ' + (erreursJS.length ? erreursJS.join(' | ') : 'aucune'));
  process.exit(echecs.length || erreursJS.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });

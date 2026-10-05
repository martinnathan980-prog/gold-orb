/* Prépare les vrais .xls de tests/xls/ — écrits par des programmes qui ne
   sont pas la fenêtre, pour qu'elle soit jugée sur des fichiers qu'elle n'a
   pas fabriqués — et la lecture qu'en fait SheetJS, l'oracle de l'essai
   (tests/xls/oracle.json.gz). Ni la fenêtre ni l'essai n'ont besoin de ces
   programmes : ils ne lisent que les fichiers produits ici, gardés dans le
   dépôt. À relancer seulement si les sources changent (SOURCES dans
   tests/fabriquer-xls.js, ou tests/feuille-gates.js) :

     LIBREOFFICE=/chemin/soffice        (LibreOffice avec Calc)
     LO_PYTHON=/chemin/python3          (un Python où « import uno » marche : le mot de passe)
     [LIBREOFFICE_UNO=/chemin/soffice]  (le soffice que ce Python lance, s'il n'est pas LIBREOFFICE)
     SHEETJS=/chemin/node_modules/xlsx  (SheetJS 0.18.5, hors du package.json)
     XLWT=/chemin/dossier/qui/contient/xlwt   [PYTHON=python3]
     node tests/preparer-xls.js

   Ce que chacun écrit :
   – LibreOffice (« MS Excel 97 ») : l'export GATES (186 plans, 16 fusions),
     l'export SEE de 3 200 lignes (table des textes partagés en 20
     enregistrements CONTINUE, booléens en formules), deux onglets avec
     l'en-tête dans le second, un premier onglet masqué ; et, par UNO, un
     SEE protégé par un mot de passe (FILEPASS, RC4) et l'export GATES
     chiffré avec le mot de passe par défaut d'Excel (« VelvetSweatshop »). LibreOffice n'écrit plus
     le format d'Excel 95 : le BIFF5 vient de SheetJS.
   – SheetJS : un SEE en BIFF8 (cellules LABEL, sans table partagée), le
     même en BIFF5 (« Book », textes en Windows-1252), et en BIFF2 (très
     ancien : la fenêtre le refuse).
   – xlwt (Python) : l'export GATES (ses fusions, ses dates, ses nombres en
     RK) et un SEE.
   L'oracle : pour chaque fichier, chaque onglet tel que SheetJS le lit —
   les valeurs comme sheet_to_json(header: 1, raw: false) les écrirait, à
   trois différences voulues près, celles de la fenêtre (et de sa lecture
   des .xlsx) : les booléens VRAI / FAUX, toute date jj/mm/aaaa (SheetJS
   suit le format du fichier, « m/d/yyyy » compris), la virgule décimale. */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { SOURCES, lignesSee, ENTETE_SEE, nomSee } = require('./fabriquer-xls');
const { feuilleGates, colonne } = require('./feuille-gates');

const DOSSIER = path.join(__dirname, 'xls');
const XLSX = require(process.env.SHEETJS || 'xlsx');
const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'preparer-xls-'));
fs.mkdirSync(DOSSIER, { recursive: true });

function libreOffice(source, sortie) {
  const entree = path.join(tmp, source + '.xlsx');
  fs.writeFileSync(entree, SOURCES[source]());
  execFileSync(process.env.LIBREOFFICE, ['--headless', '--convert-to', 'xls', '--outdir', tmp, entree], { stdio: 'inherit' });
  fs.copyFileSync(path.join(tmp, source + '.xls'), path.join(DOSSIER, sortie));
}

/* Le mot de passe : UNO, l'interface de programmation de LibreOffice. */
const UNO = [
  'import os, sys, time, subprocess, uno',
  'from com.sun.star.beans import PropertyValue',
  'def prop(n, v):',
  '    p = PropertyValue(); p.Name = n; p.Value = v; return p',
  'tube = "preparerxls" + str(os.getpid())',
  '# Le PYTHONPATH qui a servi à trouver « uno » dérouterait le Python de LibreOffice lui-même.',
  'env = dict(os.environ); env.pop("PYTHONPATH", None)',
  'proc = subprocess.Popen([sys.argv[1], "-env:UserInstallation=file://" + sys.argv[5], "--headless", "--norestore", "--accept=pipe,name=" + tube + ";urp;"], env=env)',
  'try:',
  '    local = uno.getComponentContext()',
  '    res = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)',
  '    ctx = None',
  '    for _ in range(60):',
  '        try:',
  '            ctx = res.resolve("uno:pipe,name=" + tube + ";urp;StarOffice.ComponentContext"); break',
  '        except Exception:',
  '            time.sleep(1)',
  '    bureau = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)',
  '    doc = bureau.loadComponentFromURL(uno.systemPathToFileUrl(sys.argv[2]), "_blank", 0, (prop("Hidden", True),))',
  '    doc.storeToURL(uno.systemPathToFileUrl(sys.argv[3]), (prop("FilterName", "MS Excel 97"), prop("Password", sys.argv[4])))',
  '    doc.close(True)',
  '    try: bureau.terminate()',
  '    except Exception: pass',
  'finally:',
  '    try: proc.wait(timeout=20)',
  '    except Exception: proc.terminate()'
].join('\n');
/* `contenu` : le .xlsx à enregistrer ; par défaut, un SEE de 30 lignes. */
function libreOfficeProtege(sortie, motDePasse, contenu) {
  const entree = path.join(tmp, sortie + '.xlsx'), script = path.join(tmp, 'protege.py');
  fs.writeFileSync(entree, contenu || require('./fabriquer-xlsx').xlsx({ onglets: [{ nom: 'Nommage', lignes: lignesSee(30) }] }));
  fs.writeFileSync(script, UNO);
  execFileSync(process.env.LO_PYTHON || 'python3', [script, process.env.LIBREOFFICE_UNO || process.env.LIBREOFFICE, entree, path.join(DOSSIER, sortie), motDePasse,
    path.join(tmp, 'profil')], { stdio: 'inherit' });
}

/* SheetJS : un export SEE de 40 lignes, en BIFF8, BIFF5 et BIFF2. */
function sheetjs() {
  const aoa = [['Nommage WD BFLOW'], [], ENTETE_SEE.slice(0, 7).concat(['Poids'])];
  for (let i = 0; i < 40; i++) {
    aoa.push(['S-' + i, nomSee(i), String((i % 3) + 1).padStart(3, '0'), ['A', 'B', 'C'][i % 3], { t: 'n', v: 45000 + i, z: 'dd/mm/yyyy' },
      i % 4 ? { t: 'n', v: 45100 + i, z: 'dd/mm/yyyy' } : null, { t: 'b', v: i % 2 === 0 }, 3.5 + i]);
  }
  const ws = XLSX.utils.aoa_to_sheet(aoa);
  ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 3 } }];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Nommage');
  fs.writeFileSync(path.join(DOSSIER, 'sheetjs-see.xls'), XLSX.write(wb, { bookType: 'biff8', type: 'buffer' }));
  fs.writeFileSync(path.join(DOSSIER, 'sheetjs-see-95.xls'), XLSX.write(wb, { bookType: 'biff5', type: 'buffer' }));
  fs.writeFileSync(path.join(DOSSIER, 'sheetjs-see-biff2.xls'), XLSX.write(wb, { bookType: 'biff2', type: 'buffer' }));
}

/* xlwt : l'export GATES (fusions par write_merge, dates au format
   jj/mm/aaaa, l'ATA en nombre) et un export SEE. */
function xlwt() {
  const g = feuilleGates(186), iDate = colonne('Date création'), iAta = colonne('ATA');
  const fusionnees = {};
  g.fusions.forEach(function (f) { for (let k = 1; k < f.larg; k++) fusionnees[(f.ligne - 1) + ':' + (f.col - 1 + k)] = true; });
  const cellules = [];
  g.valeurs.forEach(function (l, r) {
    l.forEach(function (v, j) {
      if (v === '' || fusionnees[r + ':' + j]) return;
      if (r >= 2 && j === iDate && /^\d\d\/\d\d\/\d{4}$/.test(v)) { const m = /^(\d\d)\/(\d\d)\/(\d{4})$/.exec(v); cellules.push([r, j, 'date', +m[3], +m[2], +m[1]]); }
      else if (r >= 2 && j === iAta && /^\d+$/.test(v)) cellules.push([r, j, 'nombre', Number(v)]);
      else cellules.push([r, j, 'texte', v]);
    });
  });
  const donnees = { gates: { cellules: cellules, fusions: g.fusions.map(function (f) { return [f.ligne - 1, f.col - 1, f.col + f.larg - 2]; }), valeurs: g.valeurs } };
  const see = [];
  lignesSee(60).forEach(function (l, r) {
    l.forEach(function (v, j) {
      if (v === null || v === undefined) return;
      if (typeof v === 'string') see.push([r, j, 'texte', v]);
      else if (v.b !== undefined) see.push([r, j, 'booleen', v.b]);
      else if (v.n !== undefined) { const d = new Date(Date.UTC(1899, 11, 30) + v.n * 864e5); see.push([r, j, 'date', d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()]); }
    });
  });
  donnees.see = { cellules: see, fusions: [[0, 0, 3]] };
  const json = path.join(tmp, 'xlwt.json'), script = path.join(tmp, 'xlwt.py');
  fs.writeFileSync(json, JSON.stringify(donnees));
  fs.writeFileSync(script, [
    'import sys, json, datetime',
    'sys.path.insert(0, ' + JSON.stringify(process.env.XLWT || '') + ')',
    'import xlwt',
    'd = json.load(open(sys.argv[1], encoding="utf-8"))',
    'jour = xlwt.easyxf(num_format_str="dd/mm/yyyy")',
    'for nom, sortie, onglet in (("gates", sys.argv[2], "Export"), ("see", sys.argv[3], "Nommage")):',
    '    wb = xlwt.Workbook(encoding="utf-8"); ws = wb.add_sheet(onglet)',
    '    fus = {(f[0], f[1]): f for f in d[nom]["fusions"]}',
    '    for c in d[nom]["cellules"]:',
    '        r, j, t = c[0], c[1], c[2]',
    '        v = datetime.date(c[3], c[4], c[5]) if t == "date" else c[3]',
    '        st = jour if t == "date" else xlwt.Style.default_style',
    '        if (r, j) in fus: ws.write_merge(r, r, j, fus[(r, j)][2], v, st)',
    '        else: ws.write(r, j, v, st)',
    '    wb.save(sortie)'
  ].join('\n'));
  execFileSync(process.env.PYTHON || 'python3', [script, json, path.join(DOSSIER, 'xlwt-gates.xls'), path.join(DOSSIER, 'xlwt-see.xls')], { stdio: 'inherit' });
}

/* L'oracle : chaque onglet lu par SheetJS, cellule par cellule. */
function deux(n) { return (n < 10 ? '0' : '') + n; }
function texteOracle(c, en1904) {
  if (c.t === 'b') return c.v ? 'VRAI' : 'FAUX';
  if (c.t === 'e') return c.w || '';
  if (c.t === 's') return c.v;
  if (c.t === 'n') {
    if (c.z && XLSX.SSF.is_date(c.z)) {
      const d = new Date(Math.round(((en1904 ? c.v + 1462 : c.v) - 25569) * 864e5));
      const jour = deux(d.getUTCDate()) + '/' + deux(d.getUTCMonth() + 1) + '/' + d.getUTCFullYear();
      return c.v % 1 ? jour + ' ' + deux(d.getUTCHours()) + ':' + deux(d.getUTCMinutes()) : jour;
    }
    return String(c.w !== undefined ? c.w : c.v).replace('.', ',');
  }
  return c.w !== undefined ? c.w : c.v === undefined ? '' : String(c.v);
}
function oracle(nom) {
  const wb = XLSX.read(fs.readFileSync(path.join(DOSSIER, nom)), { type: 'buffer', cellNF: true });
  const en1904 = !!(wb.Workbook && wb.Workbook.WBProps && wb.Workbook.WBProps.date1904);
  return wb.SheetNames.map(function (n) {
    const ws = wb.Sheets[n], lignes = [];
    if (ws['!ref']) {
      const r = XLSX.utils.decode_range(ws['!ref']);
      for (let i = 0; i <= r.e.r; i++) {
        const l = [];
        for (let j = 0; j <= r.e.c; j++) { const c = ws[XLSX.utils.encode_cell({ r: i, c: j })]; l.push(c ? texteOracle(c, en1904) : ''); }
        while (l.length && l[l.length - 1] === '') l.pop();
        lignes.push(l);
      }
      while (lignes.length && !lignes[lignes.length - 1].length) lignes.pop();
    }
    /* (SheetJS 0.18.5 ne dit pas qu'un onglet .xls est masqué : l'essai le vérifie sur la fenêtre seule.) */
    return { nom: n, lignes: lignes,
             fusions: (ws['!merges'] || []).map(function (m) { return [m.s.r + 1, m.s.c + 1, m.e.r - m.s.r + 1, m.e.c - m.s.c + 1]; }) };
  });
}

libreOffice('gates', 'lo-gates.xls');
libreOffice('see', 'lo-see.xls');
libreOffice('deux-onglets', 'lo-deux-onglets.xls');
libreOffice('onglet-cache', 'lo-onglet-cache.xls');
libreOfficeProtege('lo-protege.xls', 'secret');
/* L'export GATES enregistré avec « VelvetSweatshop », le mot de passe par
   défaut d'Excel (structure protégée, ou mot de passe pour la seule
   modification) : chiffré, mais Excel et LibreOffice l'ouvrent sans rien
   demander — la fenêtre aussi. */
libreOfficeProtege('lo-velvet.xls', 'VelvetSweatshop', SOURCES.gates());
sheetjs();
xlwt();
const lus = {};
['lo-gates.xls', 'lo-see.xls', 'lo-deux-onglets.xls', 'lo-onglet-cache.xls', 'sheetjs-see.xls', 'sheetjs-see-95.xls', 'xlwt-gates.xls', 'xlwt-see.xls']
  .forEach(function (n) { lus[n] = oracle(n); });
/* Compressé : un tableau de 3 200 lignes en une ligne de JSON n'a rien à faire en clair dans un diff (zcat pour le lire). */
fs.writeFileSync(path.join(DOSSIER, 'oracle.json.gz'), require('zlib').gzipSync(JSON.stringify({ sheetjs: XLSX.version, fichiers: lus }), { level: 9 }));
fs.rmSync(tmp, { recursive: true, force: true });
console.log('tests/xls/ préparé : ' + fs.readdirSync(DOSSIER).join(', '));

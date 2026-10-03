/* Fabrique des classeurs .xlsx pour les essais de l'import SEE : un zip
   écrit à la main (zlib pour la compression), et les parties d'un classeur
   comme Excel les écrit — chaînes partagées ou en ligne, chaînes riches avec
   lecture phonétique, styles (dates, zéros de tête), préfixes d'espace de
   noms, cellules sans référence, descripteurs de données, Zip64. */
const zlib = require('zlib');

const TABLE_CRC = (function () {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) c = TABLE_CRC[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}

/** Un zip : [{ nom, donnees, stocke }] ; options { descripteur, zip64 }. */
function zip(parties, options) {
  const opt = options || {};
  const morceaux = [], central = [];
  let position = 0;
  parties.forEach(function (p) {
    const nom = Buffer.from(p.nom, 'utf8');
    const brut = Buffer.isBuffer(p.donnees) ? p.donnees : Buffer.from(p.donnees, 'utf8');
    const methode = p.stocke ? 0 : 8;
    const comprime = methode ? zlib.deflateRawSync(brut, { level: 6 }) : brut;
    const crc = crc32(brut);
    const drapeaux = (opt.descripteur ? 8 : 0) | 0x800;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(drapeaux, 6);
    local.writeUInt16LE(methode, 8); local.writeUInt32LE(0, 10);
    local.writeUInt32LE(opt.descripteur ? 0 : crc, 14);
    local.writeUInt32LE(opt.descripteur ? 0 : comprime.length, 18);
    local.writeUInt32LE(opt.descripteur ? 0 : brut.length, 22);
    local.writeUInt16LE(nom.length, 26); local.writeUInt16LE(0, 28);
    morceaux.push(local, nom, comprime);
    let taille = 30 + nom.length + comprime.length;
    if (opt.descripteur) {
      const d = Buffer.alloc(16);
      d.writeUInt32LE(0x08074b50, 0); d.writeUInt32LE(crc, 4); d.writeUInt32LE(comprime.length, 8); d.writeUInt32LE(brut.length, 12);
      morceaux.push(d); taille += 16;
    }
    /* En Zip64, les tailles et la place du répertoire passent dans le champ
       supplémentaire 0x0001 : comme les écrivent les gros exports. */
    const extra = opt.zip64 ? Buffer.alloc(28) : Buffer.alloc(0);
    if (opt.zip64) {
      extra.writeUInt16LE(1, 0); extra.writeUInt16LE(24, 2);
      extra.writeBigUInt64LE(BigInt(brut.length), 4); extra.writeBigUInt64LE(BigInt(comprime.length), 12);
      extra.writeBigUInt64LE(BigInt(position), 20);
    }
    const c = Buffer.alloc(46);
    c.writeUInt32LE(0x02014b50, 0); c.writeUInt16LE(45, 4); c.writeUInt16LE(20, 6); c.writeUInt16LE(drapeaux, 8);
    c.writeUInt16LE(methode, 10); c.writeUInt32LE(0, 12); c.writeUInt32LE(crc, 16);
    c.writeUInt32LE(opt.zip64 ? 0xFFFFFFFF : comprime.length, 20);
    c.writeUInt32LE(opt.zip64 ? 0xFFFFFFFF : brut.length, 24);
    c.writeUInt16LE(nom.length, 28); c.writeUInt16LE(extra.length, 30); c.writeUInt16LE(0, 32);
    c.writeUInt16LE(0, 34); c.writeUInt16LE(0, 36); c.writeUInt32LE(0, 38);
    c.writeUInt32LE(opt.zip64 ? 0xFFFFFFFF : position, 42);
    central.push(c, nom, extra);
    position += taille;
  });
  const cd = Buffer.concat(central);
  const fin = [];
  if (opt.zip64) {
    const z = Buffer.alloc(56);
    z.writeUInt32LE(0x06064b50, 0); z.writeBigUInt64LE(44n, 4); z.writeUInt16LE(45, 12); z.writeUInt16LE(45, 14);
    z.writeUInt32LE(0, 16); z.writeUInt32LE(0, 20);
    z.writeBigUInt64LE(BigInt(parties.length), 24); z.writeBigUInt64LE(BigInt(parties.length), 32);
    z.writeBigUInt64LE(BigInt(cd.length), 40); z.writeBigUInt64LE(BigInt(position), 48);
    const loc = Buffer.alloc(20);
    loc.writeUInt32LE(0x07064b50, 0); loc.writeUInt32LE(0, 4); loc.writeBigUInt64LE(BigInt(position + cd.length), 8); loc.writeUInt32LE(1, 16);
    fin.push(z, loc);
  }
  const e = Buffer.alloc(22);
  e.writeUInt32LE(0x06054b50, 0);
  e.writeUInt16LE(opt.zip64 ? 0xFFFF : parties.length, 8); e.writeUInt16LE(opt.zip64 ? 0xFFFF : parties.length, 10);
  e.writeUInt32LE(opt.zip64 ? 0xFFFFFFFF : cd.length, 12); e.writeUInt32LE(opt.zip64 ? 0xFFFFFFFF : position, 16);
  return Buffer.concat(morceaux.concat([cd]).concat(fin).concat([e]));
}

function echXml(t) {
  return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
    .replace(/\r/g, '_x000D_').replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, function (c) { return '_x' + ('000' + c.charCodeAt(0).toString(16).toUpperCase()).slice(-4) + '_'; });
}
function lettres(n) { let s = ''; n++; while (n > 0) { const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = Math.floor((n - 1) / 26); } return s; }

/**
 * Un classeur. spec : { onglets: [{ nom, lignes: [[cellule…]…], cache }],
 *   chaines: 'partagees' | 'inline', prefixe: 'x' (préfixe d'espace de
 *   noms), sansRef: true (ni r de ligne ni r de cellule), date1904,
 *   descripteur, zip64, cheminsAbsolus }.
 * Une cellule : chaîne, nombre, null, ou { n, fmt: 'date' | 'heure' |
 *   'zeros5' | '0.00' }, { str } (résultat de formule), { b }, { riche:
 *   [morceaux], phonetique }.
 */
function xlsx(spec) {
  const px = spec.prefixe ? spec.prefixe + ':' : '';
  const nsP = spec.prefixe ? ' xmlns:' + spec.prefixe + '="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    : ' xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';
  const chaines = [], index = new Map();
  const styles = [0], styleDe = {};
  const FMT = { date: 14, heure: 20, zeros5: 164, '0.00': 2 };
  function style(fmt) {
    if (!fmt) return 0;
    if (styleDe[fmt] === undefined) { styleDe[fmt] = styles.length; styles.push(FMT[fmt]); }
    return styleDe[fmt];
  }
  function partagee(cle, xml) {
    if (!index.has(cle)) { index.set(cle, chaines.length); chaines.push(xml); }
    return index.get(cle);
  }
  function cellule(v, ref) {
    const r = spec.sansRef ? '' : ' r="' + ref + '"';
    if (v === null || v === undefined) return '';
    if (typeof v === 'number') return '<' + px + 'c' + r + '><' + px + 'v>' + v + '</' + px + 'v></' + px + 'c>';
    if (typeof v === 'string') {
      if (spec.chaines === 'inline') return '<' + px + 'c' + r + ' t="inlineStr"><' + px + 'is><' + px + 't xml:space="preserve">' + echXml(v) + '</' + px + 't></' + px + 'is></' + px + 'c>';
      const i = partagee('s:' + v, '<' + px + 't xml:space="preserve">' + echXml(v) + '</' + px + 't>');
      return '<' + px + 'c' + r + ' s="0" t="s"><' + px + 'v>' + i + '</' + px + 'v></' + px + 'c>';
    }
    if (v.riche) {
      const xml = v.riche.map(function (m, k) { return '<' + px + 'r>' + (k ? '<' + px + 'rPr><' + px + 'b/></' + px + 'rPr>' : '') + '<' + px + 't>' + echXml(m) + '</' + px + 't></' + px + 'r>'; }).join('') +
        (v.phonetique ? '<' + px + 'rPh sb="0" eb="1"><' + px + 't>' + echXml(v.phonetique) + '</' + px + 't></' + px + 'rPh>' : '');
      const i = partagee('r:' + JSON.stringify(v), xml);
      return '<' + px + 'c' + r + ' t="s"><' + px + 'v>' + i + '</' + px + 'v></' + px + 'c>';
    }
    if (v.str !== undefined) return '<' + px + 'c' + r + ' t="str"><' + px + 'f>CONCAT(A1)</' + px + 'f><' + px + 'v>' + echXml(v.str) + '</' + px + 'v></' + px + 'c>';
    if (v.b !== undefined) return '<' + px + 'c' + r + ' t="b"><' + px + 'v>' + (v.b ? 1 : 0) + '</' + px + 'v></' + px + 'c>';
    if (v.n !== undefined) return '<' + px + 'c' + r + ' s="' + style(v.fmt) + '"><' + px + 'v>' + v.n + '</' + px + 'v></' + px + 'c>';
    throw new Error('cellule inconnue ' + JSON.stringify(v));
  }
  const parties = [], feuilles = [];
  spec.onglets.forEach(function (o, k) {
    const lignes = [];
    o.lignes.forEach(function (l, i) {
      if (!l || !l.some(function (v) { return v !== null && v !== undefined && v !== ''; })) return;   // ligne vide : absente, comme Excel
      const r = spec.sansRef ? '' : ' r="' + (i + 1) + '" spans="1:' + l.length + '"';
      lignes.push('<' + px + 'row' + r + '>' + l.map(function (v, j) { return v === '' ? '' : cellule(v, lettres(j) + (i + 1)); }).join('') + '</' + px + 'row>');
    });
    feuilles.push('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<' + px + 'worksheet' + nsP +
      ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><' + px + 'sheetPr/><' + px + 'dimension ref="A1"/><' + px + 'sheetViews><' + px + 'sheetView workbookViewId="0"/></' + px + 'sheetViews>' +
      '<' + px + 'cols><' + px + 'col min="1" max="3" width="12"/></' + px + 'cols><' + px + 'sheetData>' + lignes.join('') + '</' + px + 'sheetData>' +
      '<' + px + 'rowBreaks count="0"/></' + px + 'worksheet>');
  });
  const chemin = function (c) { return spec.cheminsAbsolus ? '/xl/' + c : c; };
  const types = '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
    spec.onglets.map(function (o, k) { return '<Override PartName="/xl/worksheets/sheet' + (k + 1) + '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'; }).join('') +
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
    (spec.chaines !== 'inline' ? '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>' : '');
  parties.push({ nom: '[Content_Types].xml', donnees: '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' + types + '</Types>' });
  parties.push({ nom: '_rels/.rels', donnees: '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>' });
  parties.push({ nom: 'xl/workbook.xml', donnees: '<?xml version="1.0" encoding="UTF-8"?><' + px + 'workbook' + nsP + ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
    '<' + px + 'workbookPr' + (spec.date1904 ? ' date1904="1"' : '') + '/><' + px + 'sheets>' +
    spec.onglets.map(function (o, k) { return '<' + px + 'sheet name="' + echXml(o.nom) + '" sheetId="' + (k + 1) + '"' + (o.cache ? ' state="hidden"' : '') + ' r:id="rId' + (k + 1) + '"/>'; }).join('') +
    '</' + px + 'sheets></' + px + 'workbook>' });
  const rels = spec.onglets.map(function (o, k) {
    return '<Relationship Id="rId' + (k + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="' + chemin('worksheets/sheet' + (k + 1) + '.xml') + '"/>';
  });
  const n = spec.onglets.length;
  rels.push('<Relationship Id="rId' + (n + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="' + chemin('styles.xml') + '"/>');
  if (spec.chaines !== 'inline') rels.push('<Relationship Id="rId' + (n + 2) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="' + chemin('sharedStrings.xml') + '"/>');
  parties.push({ nom: 'xl/_rels/workbook.xml.rels', donnees: '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + rels.join('') + '</Relationships>' });
  feuilles.forEach(function (x, k) { parties.push({ nom: 'xl/worksheets/sheet' + (k + 1) + '.xml', donnees: x }); });
  parties.push({ nom: 'xl/styles.xml', donnees: '<?xml version="1.0" encoding="UTF-8"?><' + px + 'styleSheet' + nsP + '><' + px + 'numFmts count="1"><' + px + 'numFmt numFmtId="164" formatCode="00000"/></' + px + 'numFmts>' +
    '<' + px + 'cellStyleXfs count="1"><' + px + 'xf numFmtId="0"/></' + px + 'cellStyleXfs><' + px + 'cellXfs count="' + styles.length + '">' +
    styles.map(function (id) { return '<' + px + 'xf numFmtId="' + id + '" fontId="0" applyNumberFormat="1"><' + px + 'alignment wrapText="1"/></' + px + 'xf>'; }).join('') +
    '</' + px + 'cellXfs></' + px + 'styleSheet>' });
  if (spec.chaines !== 'inline') {
    parties.push({ nom: 'xl/sharedStrings.xml', donnees: '<?xml version="1.0" encoding="UTF-8"?><' + px + 'sst' + nsP + ' count="' + chaines.length + '" uniqueCount="' + chaines.length + '">' +
      chaines.map(function (x) { return '<' + px + 'si>' + x + '</' + px + 'si>'; }).join('') + '</' + px + 'sst>' });
  }
  return zip(parties, { descripteur: spec.descripteur, zip64: spec.zip64 });
}

module.exports = { xlsx, zip, crc32 };

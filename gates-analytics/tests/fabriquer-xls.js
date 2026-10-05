/* Fabrique de vrais .xls pour les essais de l'import (tests/import-see.js),
   écrits octet par octet pour tenir chaque cas qu'un fichier réel peut
   présenter :
   – le conteneur OLE (« Compound File ») : secteurs de 512 ou de 4 096
     octets, FAT, DIFAT au-delà des 109 premiers secteurs de FAT, mini-flux
     et mini-FAT pour les petits flux, répertoire en arbre (frères à gauche
     et à droite), secteurs mélangés (des chaînes qui ne se suivent pas dans
     le fichier), et, à la demande, une chaîne qui boucle ;
   – les enregistrements BIFF8 (Excel 97-2003) et BIFF5 (Excel 5 / 95) d'un
     classeur : chaque façon d'écrire une cellule (textes partagés, LABEL,
     RSTRING, NUMBER, RK sous ses quatre formes, MULRK, BOOLERR, FORMULA et
     son STRING, BLANK, MULBLANK), les formats (FORMAT, XF), le calendrier
     1904, la page de codes, les cellules fusionnées en plusieurs
     enregistrements, un mot de passe (FILEPASS), le vrai chiffrement RC4
     (d'Excel 97 ou CryptoAPI) avec le mot de passe par défaut d'Excel ou un
     autre, les formules d'Apple Numbers, des onglets masqués, des
     onglets graphiques ou de macros, un graphique posé dans un onglet (ses
     propres BOF et EOF, et des valeurs en cache qui ressemblent à des
     cellules) ; la table des textes partagés (SST) coupée en enregistrements
     CONTINUE aussi petits qu'on le veut — les coupures tombent alors partout :
     dans les caractères (avec l'octet d'options qui redit leur largeur, et
     qui peut en changer), dans les mises en forme d'un texte riche, dans sa
     lecture phonétique ;
   – une page web archivée (MHTML), en quoted-printable ou en base64.
   Et les sources des vrais .xls de tests/xls/ (écrits par LibreOffice,
   SheetJS et xlwt : voir tests/preparer-xls.js), pour que l'essai compare
   chacun au .xlsx d'où il vient. */
const crypto = require('crypto');
const { xlsx } = require('./fabriquer-xlsx');
const { feuilleGates, colonne } = require('./feuille-gates');

function u16(n) { const b = Buffer.alloc(2); b.writeUInt16LE(n & 0xFFFF, 0); return b; }
function u32(n) { const b = Buffer.alloc(4); b.writeUInt32LE(n >>> 0, 0); return b; }
function enr(type, donnees) { return Buffer.concat([u16(type), u16(donnees.length), donnees]); }
const MAX_ENR = 8224;   // la taille des données d'un enregistrement BIFF8, au plus

// ===================================================================== pages de codes (BIFF5)
/* Windows-1252 : le Latin-1, sauf les octets 128 à 159. */
const CP1252 = { '€': 0x80, '‚': 0x82, 'ƒ': 0x83, '„': 0x84, '…': 0x85, '†': 0x86, '‡': 0x87, 'ˆ': 0x88, '‰': 0x89, 'Š': 0x8A, '‹': 0x8B, 'Œ': 0x8C,
  'Ž': 0x8E, '‘': 0x91, '’': 0x92, '“': 0x93, '”': 0x94, '•': 0x95, '–': 0x96, '—': 0x97, '˜': 0x98, '™': 0x99, 'š': 0x9A, '›': 0x9B, 'œ': 0x9C,
  'ž': 0x9E, 'Ÿ': 0x9F };
/* La moitié haute du code page 850 du DOS, octets 128 à 255. */
const CP850 = '\u00c7\u00fc\u00e9\u00e2\u00e4\u00e0\u00e5\u00e7\u00ea\u00eb\u00e8\u00ef\u00ee\u00ec\u00c4\u00c5\u00c9\u00e6\u00c6\u00f4\u00f6\u00f2\u00fb\u00f9\u00ff\u00d6\u00dc\u00f8\u00a3\u00d8\u00d7\u0192\u00e1\u00ed\u00f3\u00fa\u00f1\u00d1\u00aa\u00ba\u00bf\u00ae\u00ac\u00bd\u00bc\u00a1\u00ab\u00bb\u2591\u2592\u2593\u2502\u2524\u00c1\u00c2\u00c0\u00a9\u2563\u2551\u2557\u255d\u00a2\u00a5\u2510\u2514\u2534\u252c\u251c\u2500\u253c\u00e3\u00c3\u255a\u2554\u2569\u2566\u2560\u2550\u256c\u00a4\u00f0\u00d0\u00ca\u00cb\u00c8\u0131\u00cd\u00ce\u00cf\u2518\u250c\u2588\u2584\u00a6\u00cc\u2580\u00d3\u00df\u00d4\u00d2\u00f5\u00d5\u00b5\u00fe\u00de\u00da\u00db\u00d9\u00fd\u00dd\u00af\u00b4\u00ad\u00b1\u2017\u00be\u00b6\u00a7\u00f7\u00b8\u00b0\u00a8\u00b7\u00b9\u00b3\u00b2\u25a0\u00a0';
function octets8(texte, page) {
  return Buffer.from(Array.from(texte).map(function (c) {
    const k = c.charCodeAt(0);
    if (k < 128) return k;
    if (page === 850) { const i = CP850.indexOf(c); return i === -1 ? 63 : 128 + i; }
    if (CP1252[c] !== undefined) return CP1252[c];
    return k < 256 && (k < 0x80 || k > 0x9F) ? k : 63;
  }));
}

// ===================================================================== chaînes BIFF8
/* Compressée (un octet par caractère, du Latin-1) si elle le peut. */
function large(t) { return !/^[\u0000-ÿ]*$/.test(t); }
function caracteres(t, deux) { return deux ? Buffer.from(t, 'utf16le') : Buffer.from(t, 'latin1'); }
/* XLUnicodeString : longueur sur 2 octets (1 pour un nom d'onglet), options, caractères. */
function chaineU(t, longueurSur1) {
  const deux = large(t);
  return Buffer.concat([longueurSur1 ? Buffer.from([t.length]) : u16(t.length), Buffer.from([deux ? 1 : 0]), caracteres(t, deux)]);
}

/* Des enregistrements qui se remplissent l'un après l'autre : un type pour
   le premier, CONTINUE pour les suivants, `max` octets de données chacun.
   `brut` passe d'un enregistrement au suivant sans rien de plus ; `chars`
   recommence chaque suite par l'octet d'options de la largeur (0 ou 1) —
   que `bascule` fait changer, quand les caractères qui restent le
   permettent ; `entier` ouvre un nouvel enregistrement si les octets ne
   tiennent pas dans celui-ci (Excel ne coupe jamais un en-tête de chaîne). */
function remplisseur(type, max) {
  const enregs = [];
  let cur = [], lg = 0;
  function nouveau() { enregs.push(enr(enregs.length ? 0x003C : type, Buffer.concat(cur))); cur = []; lg = 0; }
  const r = {
    brut: function (b) {
      let p = 0;
      while (p < b.length) {
        if (lg >= max) nouveau();
        const n = Math.min(b.length - p, max - lg);
        cur.push(b.subarray(p, p + n));
        lg += n;
        p += n;
      }
    },
    entier: function (b) { if (lg + b.length > max && lg) nouveau(); r.brut(b); },
    chars: function (t, deux, bascule) {
      let p = 0;
      while (p < t.length) {
        let place = Math.floor((max - lg) / (deux ? 2 : 1));
        if (place <= 0) {
          nouveau();
          if (bascule) deux = deux ? large(t.slice(p)) : true;
          cur.push(Buffer.from([deux ? 1 : 0]));
          lg = 1;
          continue;
        }
        const n = Math.min(place, t.length - p);
        const b = caracteres(t.slice(p, p + n), deux);
        cur.push(b);
        lg += b.length;
        p += n;
      }
    },
    fin: function () { if (lg || !enregs.length) nouveau(); return enregs; }
  };
  return r;
}

/* La table des textes partagés : [{ texte, runs, phonetique }] →
   l'enregistrement SST et ses CONTINUE. options : { max, bascule,
   entetesCoupes }. */
function sst(chaines, total, options) {
  const opt = options || {};
  const r = remplisseur(0x00FC, opt.max || MAX_ENR);
  r.brut(Buffer.concat([u32(total), u32(chaines.length)]));
  chaines.forEach(function (c) {
    const deux = large(c.texte), runs = c.runs || 0, ph = c.phonetique ? Buffer.from(c.phonetique) : null;
    const tete = Buffer.concat([u16(c.texte.length), Buffer.from([(deux ? 1 : 0) | (runs ? 8 : 0) | (ph ? 4 : 0)]),
      runs ? u16(runs) : Buffer.alloc(0), ph ? u32(ph.length) : Buffer.alloc(0)]);
    if (opt.entetesCoupes) r.brut(tete); else r.entier(tete);
    r.chars(c.texte, deux, opt.bascule);
    for (let k = 0; k < runs; k++) r.brut(Buffer.concat([u16(k), u16(k + 1)]));
    if (ph) r.brut(ph);
  });
  return r.fin();
}
/* Le texte d'un résultat de formule (STRING), coupé à `max` octets. */
function enregString(t, max) {
  const r = remplisseur(0x0207, max || MAX_ENR), deux = large(t);
  r.entier(Buffer.concat([u16(t.length), Buffer.from([deux ? 1 : 0])]));
  r.chars(t, deux, false);
  return r.fin();
}
/* Une lecture phonétique (ExtRst) : un bloc d'octets que le lecteur saute. */
function phonetique(t) {
  const corps = Buffer.concat([u16(1), u16(0), u16(t.length), u16(t.length), caracteres(t, true)]);
  return Buffer.concat([u16(1), u16(corps.length), corps]);
}

// ===================================================================== formats
/* Les formats qu'un essai peut donner à une cellule : [numéro, code] —
   sans code, un format intégré à Excel. « standard » : un FORMAT au nom
   local de « General », qu'il ne faut pas prendre pour une date. */
const FORMATS = {
  general: [0], '0.00': [2], mille: [3], pct: [9], pct2: [10], sci: [11], date: [14], heure: [20], jourheure: [22], texte: [49],
  jour: [164, 'dd/mm/yyyy'], zeros3: [165, '000'], standard: [166, 'Standard'], euro: [167, '#,##0.00\\ "€"'], zeros5: [168, '00000'],
  moisjour: [169, 'm/d/yyyy'], jourFr: [170, '[$-40C]dd/mm/yyyy'],
  /* « General » sous ses noms néerlandais, suédois, finnois, polonais, russe. */
  standaard: [171, 'Standaard'], allmant: [172, 'Allmänt'], yleinen: [173, 'Yleinen'], standardowy: [174, 'Standardowy'], obchtchi: [175, 'Общий']
};

// ===================================================================== RK
/* Un nombre au format RK, sous la forme demandée : entier (sur 30 bits),
   entier divisé par cent, nombre à virgule réduit à ses 30 bits de tête,
   ou ce même nombre divisé par cent. */
function codeRk(v, mode) {
  if (mode === 'entier' || mode === 'entier100') {
    const k = mode === 'entier' ? v : Math.round(v * 100);
    if (!Number.isInteger(k) || k < -(1 << 29) || k >= (1 << 29)) throw new Error('RK entier impossible pour ' + v);
    return ((k << 2) | 2 | (mode === 'entier100' ? 1 : 0)) >>> 0;
  }
  const b = Buffer.alloc(8);
  b.writeDoubleLE(mode === 'reel100' ? Math.round(v * 100) : v);
  if (b.readUInt32LE(0) !== 0 || (b.readUInt32LE(4) & 3)) throw new Error('RK réel impossible pour ' + v);
  return ((b.readUInt32LE(4) & ~3) | (mode === 'reel100' ? 1 : 0)) >>> 0;
}

// ===================================================================== le classeur BIFF
/**
 * Le flux d'un classeur. spec : {
 *   biff: 8 | 5, page (CODEPAGE, BIFF5 : 1252 par défaut), date1904,
 *   motDePasse (un FILEPASS : le fichier est chiffré, son contenu sans
 *   importance), chiffre : { methode: 'rc4' | 'cryptoapi', bits (40 ou
 *   128, CryptoAPI), motDePasse ('VelvetSweatshop' par défaut) } (le flux
 *   vraiment chiffré, comme Excel le fait), typeFormule (0x0006 par défaut :
 *   0x0206 ou 0x0406 comme Apple Numbers), formatZero (un FORMAT n° 0 au
 *   nom local de « General »),
 *   sst : { max, bascule, entetesCoupes, total } (BIFF8),
 *   onglets : [{ nom, cache, type: 'feuille' | 'graphique' | 'macro',
 *     lignes: [[cellule…]…] (cellule i de la ligne r → ligne r + 1,
 *     colonne i + 1), fusions: [{ ligne, col, larg, haut }] (1-based),
 *     fusionsParEnregistrement, graphiqueDedans, desordre (les lignes à
 *     l'envers), maxString (STRING coupé à tant d'octets) }] }.
 * Une cellule : chaîne (texte partagé en BIFF8, LABEL en BIFF5) ; nombre
 * (NUMBER) ; null ou trou (rien) ; ou un objet : { n, fmt } (NUMBER mis en
 * forme), { rk, mode, fmt }, { mulrk: [{ rk, mode, fmt }…] } (occupe les
 * colonnes suivantes, laissées en trou), { label }, { rstring, runs },
 * { riche: texte, runs, phonetique } (texte partagé riche), { blanc },
 * { mulblank: n }, { b }, { err: code }, { labelVide: true } (LABEL de
 * 8 octets, sans l'octet d'options), { f: résultat, fmt } (nombre,
 * texte suivi de STRING, booléen, '' texte vide), { f: { err } },
 * { formuleSansTexte: true } (un résultat texte sans son STRING).
 */
function classeurBiff(spec) {
  const biff = spec.biff || 8, page = spec.page || (biff === 8 ? 1200 : 1252);
  const texte5 = function (t, l1) { const o = octets8(t, page); return Buffer.concat([l1 ? Buffer.from([o.length]) : u16(o.length), o]); };
  /* Les textes partagés, dans l'ordre de leur première apparition. */
  const partages = [], rangs = new Map();
  function rangSst(c) {
    const cle = JSON.stringify(c);
    if (!rangs.has(cle)) { rangs.set(cle, partages.length); partages.push(c); }
    return rangs.get(cle);
  }
  let appels = 0;
  /* Les formats utilisés : un XF chacun, après les seize d'office. */
  const xfDe = {}, formatsUtilises = [];
  function xf(fmt) {
    if (!fmt) return 15;
    if (!FORMATS[fmt]) throw new Error('format inconnu ' + fmt);
    if (xfDe[fmt] === undefined) { xfDe[fmt] = 16 + formatsUtilises.length; formatsUtilises.push(fmt); }
    return xfDe[fmt];
  }
  function cellule(r, j, v, o) {
    const pos = Buffer.concat([u16(r), u16(j)]);
    /* Une cellule vide n'est pas écrite (Excel ne garde pas de texte vide en dur). */
    if (v === null || v === undefined || v === '') return [];
    if (typeof v === 'string') {
      appels++;
      return biff === 8 ? [enr(0x00FD, Buffer.concat([pos, u16(15), u32(rangSst({ texte: v }))]))]
        : [enr(0x0204, Buffer.concat([pos, u16(15), texte5(v)]))];
    }
    if (typeof v === 'number') {
      const b = Buffer.alloc(8); b.writeDoubleLE(v);
      return [enr(0x0203, Buffer.concat([pos, u16(15), b]))];
    }
    if (v.n !== undefined) {
      const b = Buffer.alloc(8); b.writeDoubleLE(v.n);
      return [enr(0x0203, Buffer.concat([pos, u16(xf(v.fmt)), b]))];
    }
    if (v.rk !== undefined) return [enr(0x027E, Buffer.concat([pos, u16(xf(v.fmt)), u32(codeRk(v.rk, v.mode || 'entier'))]))];
    if (v.mulrk) {
      return [enr(0x00BD, Buffer.concat([pos].concat(v.mulrk.map(function (x) { return Buffer.concat([u16(xf(x.fmt)), u32(codeRk(x.rk, x.mode || 'entier'))]); }))
        .concat([u16(j + v.mulrk.length - 1)])))];
    }
    if (v.labelVide) return [enr(0x0204, Buffer.concat([pos, u16(15), u16(0)]))];
    if (v.label !== undefined) return [enr(0x0204, Buffer.concat([pos, u16(15), biff === 8 ? chaineU(v.label) : texte5(v.label)]))];
    if (v.rstring !== undefined) {
      const n = v.runs || 2, runs = [];
      for (let k = 0; k < n; k++) runs.push(biff === 8 ? Buffer.concat([u16(k), u16(0)]) : Buffer.from([k, 0]));
      return [enr(0x00D6, Buffer.concat([pos, u16(15), biff === 8 ? chaineU(v.rstring) : texte5(v.rstring), biff === 8 ? u16(n) : Buffer.from([n])].concat(runs)))];
    }
    if (v.riche !== undefined) {
      if (biff !== 8) throw new Error('pas de texte partagé en BIFF5');
      appels++;
      return [enr(0x00FD, Buffer.concat([pos, u16(15), u32(rangSst({ texte: v.riche, runs: v.runs || 0, phonetique: v.phonetique ? phonetique(v.phonetique) : null }))]))];
    }
    if (v.blanc) return [enr(0x0201, Buffer.concat([pos, u16(15)]))];
    if (v.mulblank) {
      const xfs = []; for (let k = 0; k < v.mulblank; k++) xfs.push(u16(15));
      return [enr(0x00BE, Buffer.concat([pos].concat(xfs).concat([u16(j + v.mulblank - 1)])))];
    }
    if (v.b !== undefined) return [enr(0x0205, Buffer.concat([pos, u16(15), Buffer.from([v.b ? 1 : 0, 0])]))];
    if (v.err !== undefined) return [enr(0x0205, Buffer.concat([pos, u16(15), Buffer.from([v.err, 1])]))];
    if (v.f !== undefined || v.formuleSansTexte) {
      /* Une formule : le résultat gardé (8 octets), des options, puis les
         jetons de la formule (ici « =1 », peu importe : le lecteur ne
         calcule pas). */
      let resultat = Buffer.alloc(8), suite = [];
      const f = v.formuleSansTexte ? 'x' : v.f;
      if (typeof f === 'number') resultat.writeDoubleLE(f);
      else if (typeof f === 'boolean') resultat = Buffer.from([1, 0, f ? 1 : 0, 0, 0, 0, 0xFF, 0xFF]);
      else if (f && typeof f === 'object') resultat = Buffer.from([2, 0, f.err, 0, 0, 0, 0xFF, 0xFF]);
      else if (f === '') resultat = Buffer.from([3, 0, 0, 0, 0, 0, 0xFF, 0xFF]);
      else {
        resultat = Buffer.from([0, 0, 0, 0, 0, 0, 0xFF, 0xFF]);
        if (!v.formuleSansTexte) suite = biff === 8 ? enregString(f, o.maxString) : [enr(0x0207, texte5(f))];
      }
      const jetons = Buffer.from([0x1E, 1, 0]);   // ptgInt 1
      return [enr(spec.typeFormule || 0x0006, Buffer.concat([pos, u16(xf(v.fmt)), resultat, u16(0), u32(0), u16(jetons.length), jetons]))].concat(suite);
    }
    throw new Error('cellule inconnue ' + JSON.stringify(v));
  }
  function bof(dt) {
    return biff === 8 ? enr(0x0809, Buffer.concat([u16(0x0600), u16(dt), u16(0x0DBB), u16(0x07CC), u32(0x41), u32(6)]))
      : enr(0x0809, Buffer.concat([u16(0x0500), u16(dt), u16(0x0DBB), u16(0x07CC)]));
  }
  const EOF = enr(0x000A, Buffer.alloc(0));
  /* Un graphique, posé dans un onglet ou onglet à lui seul : ses propres BOF
     et EOF, et des valeurs en cache qui ont l'air de cellules (le lecteur
     doit les laisser). */
  function graphique() {
    const leurre = Buffer.alloc(8); leurre.writeDoubleLE(999);
    return Buffer.concat([bof(0x0020), enr(0x1001, u16(0)), enr(0x0203, Buffer.concat([u16(0), u16(0), u16(15), leurre])),
      enr(0x0204, Buffer.concat([u16(1), u16(0), u16(15), biff === 8 ? chaineU('PIÈGE') : texte5('PIEGE')])), EOF]);
  }
  /* Les onglets d'abord : les cellules font naître les textes partagés et
     les formats, que la partie commune doit porter. */
  const corps = spec.onglets.map(function (o) {
    if (o.type === 'graphique') return graphique();
    if (o.type === 'macro') return Buffer.concat([bof(0x0040), EOF]);
    const morceaux = [bof(0x0010)];
    if (o.graphiqueDedans) morceaux.push(graphique());
    const ordre = (o.lignes || []).map(function (l, r) { return r; });
    if (o.desordre) ordre.reverse();
    ordre.forEach(function (r) {
      const l = o.lignes[r] || [];
      for (let j = 0; j < l.length; j++) cellule(r, j, l[j], o).forEach(function (b) { morceaux.push(b); });
    });
    const fusions = (o.fusions || []).map(function (f) {
      return Buffer.concat([u16(f.ligne - 1), u16(f.ligne + (f.haut || 1) - 2), u16(f.col - 1), u16(f.col + f.larg - 2)]);
    });
    const parEnr = o.fusionsParEnregistrement || 1026;
    for (let k = 0; k < fusions.length && (biff === 8 || o.fusionsMemeEn5); k += parEnr) {
      const lot = fusions.slice(k, k + parEnr);
      morceaux.push(enr(0x00E5, Buffer.concat([u16(lot.length)].concat(lot))));
    }
    morceaux.push(EOF);
    return Buffer.concat(morceaux);
  });
  /* La partie commune. Les places des onglets (BOUNDSHEET) se calculent une
     fois sa longueur connue. */
  function commune(places) {
    const m = [bof(0x0005)];
    if (spec.chiffre) m.push(enr(0x002F, filepass(spec.chiffre)));
    if (spec.motDePasse) {
      /* FILEPASS, chiffrement RC4 : le contenu ne compte pas, sa présence dit tout. */
      m.push(enr(0x002F, biff === 8 ? Buffer.concat([u16(1), u16(1), u16(1), Buffer.alloc(48, 0xA5)]) : Buffer.concat([u16(0xABCD), u16(0x1234)])));
    }
    m.push(enr(0x0042, u16(page)));
    m.push(enr(0x0022, u16(spec.date1904 ? 1 : 0)));
    if (spec.formatZero) m.push(enr(0x041E, Buffer.concat([u16(0), biff === 8 ? chaineU(spec.formatZero) : texte5(spec.formatZero, true)])));
    formatsUtilises.forEach(function (fmt) {
      const d = FORMATS[fmt];
      if (d[1] === undefined) return;
      m.push(enr(0x041E, Buffer.concat([u16(d[0]), biff === 8 ? chaineU(d[1]) : texte5(d[1], true)])));
    });
    const lgXf = biff === 8 ? 20 : 16;
    for (let k = 0; k < 16 + formatsUtilises.length; k++) {
      const x = Buffer.alloc(lgXf);
      x.writeUInt16LE(k >= 16 ? FORMATS[formatsUtilises[k - 16]][0] : 0, 2);
      x.writeUInt16LE(k < 15 ? 0xFFF5 : 0x0001, 4);
      m.push(enr(0x00E0, x));
    }
    spec.onglets.forEach(function (o, k) {
      const type = o.type === 'graphique' ? 2 : o.type === 'macro' ? 1 : 0;
      m.push(enr(0x0085, Buffer.concat([u32(places[k]), Buffer.from([o.cache === 'tres' ? 2 : o.cache ? 1 : 0, type]),
        biff === 8 ? chaineU(o.nom, true) : texte5(o.nom, true)])));
    });
    if (biff === 8 && partages.length) sst(partages, (spec.sst && spec.sst.total) || appels, spec.sst).forEach(function (b) { m.push(b); });
    m.push(EOF);
    return Buffer.concat(m);
  }
  let tete = commune(spec.onglets.map(function () { return 0; }));
  const places = [];
  let p = tete.length;
  corps.forEach(function (c) { places.push(p); p += c.length; });
  tete = commune(places);
  const flux = Buffer.concat([tete].concat(corps));
  if (spec.chiffre) chiffrer(flux, spec.chiffre);
  return flux;
}

// ===================================================================== le chiffrement RC4 d'un .xls
/* Ce qu'Excel fait d'un .xls dont la structure est protégée : il le chiffre
   avec le mot de passe par défaut « VelvetSweatshop » (MS-XLS 2.2.10,
   MS-OFFCRYPTO 2.3.6 et 2.3.5) — en RC4 « d'Excel 97 » (clé tirée par MD5)
   ou en RC4 CryptoAPI (clé tirée par SHA-1, de 40 ou 128 bits). Le hachage
   vient de Node ; RC4, trois lignes, est écrit ici. */
function rc4(cle) {
  const s = []; let i, j = 0;
  for (i = 0; i < 256; i++) s[i] = i;
  for (i = 0; i < 256; i++) { j = (j + s[i] + cle[i % cle.length]) & 255; [s[i], s[j]] = [s[j], s[i]]; }
  i = j = 0;
  return function (n) {
    const o = Buffer.alloc(n);
    for (let k = 0; k < n; k++) { i = (i + 1) & 255; j = (j + s[i]) & 255; [s[i], s[j]] = [s[j], s[i]]; o[k] = s[(s[i] + s[j]) & 255]; }
    return o;
  };
}
const hache = (algo, ...parts) => crypto.createHash(algo).update(Buffer.concat(parts)).digest();
const SEL = Buffer.from('0123456789abcdef0123456789abcdef', 'hex');
const VERIFICATEUR = Buffer.from('a1b2c3d4e5f60718293a4b5c6d7e8f90', 'hex');
/* La clé du bloc n (1 024 octets du flux). */
function cleBloc(c, n) {
  const mdp = Buffer.from(c.motDePasse || 'VelvetSweatshop', 'utf16le'), bloc = u32(n);
  if (c.methode === 'rc4') {
    const h1 = hache('md5', ...new Array(16).fill(Buffer.concat([hache('md5', mdp).subarray(0, 5), SEL]))).subarray(0, 5);
    return hache('md5', h1, bloc);
  }
  const hf = hache('sha1', hache('sha1', SEL, mdp), bloc);
  return (c.bits || 128) === 40 ? Buffer.concat([hf.subarray(0, 5), Buffer.alloc(11)]) : hf.subarray(0, (c.bits || 128) / 8);
}
function filepass(c) {
  const flux = rc4(cleBloc(c, 0)), xor = (a, b) => Buffer.from(a.map((x, k) => x ^ b[k]));
  if (c.methode === 'rc4') {
    const v = xor(VERIFICATEUR, flux(16)), h = xor(hache('md5', VERIFICATEUR), flux(16));
    return Buffer.concat([u16(1), u16(1), u16(1), SEL, v, h]);
  }
  const csp = Buffer.from('Microsoft Enhanced Cryptographic Provider v1.0\u0000', 'utf16le');
  const tete = Buffer.concat([u32(4), u32(0), u32(0x6801), u32(0x8004), u32(c.bits === 40 ? 0 : c.bits || 128), u32(1), u32(0), u32(0), csp]);
  const v = xor(VERIFICATEUR, flux(16)), h = xor(hache('sha1', VERIFICATEUR), flux(20));
  return Buffer.concat([u16(1), u16(4), u16(2), u32(4), u32(tete.length), tete, u32(16), SEL, v, u32(20), h]);
}
/* Chiffre le flux sur place après le FILEPASS : les données de chaque
   enregistrement, la suite RC4 prise à la place de l'octet dans le flux
   (une nouvelle clé tous les 1 024 octets), sauf les enregistrements que le
   format laisse en clair et la place de chaque onglet (BOUNDSHEET). */
function chiffrer(flux, c) {
  const enClair = [0x0809, 0x002F, 0x0194, 0x0195, 0x00E1, 0x0196, 0x0138];
  let p = 0, apres = false, bloc = -1, suite = null;
  while (p + 4 <= flux.length) {
    const t = flux.readUInt16LE(p), d = p + 4, fin = d + flux.readUInt16LE(p + 2);
    if (apres && enClair.indexOf(t) === -1) {
      for (let q = t === 0x0085 ? d + 4 : d; q < fin; q++) {
        if ((q >> 10) !== bloc) { bloc = q >> 10; suite = rc4(cleBloc(c, bloc))(1024); }
        flux[q] ^= suite[q & 1023];
      }
    }
    if (t === 0x002F) apres = true;
    p = fin;
  }
}

// ===================================================================== le conteneur OLE
const FIN = 0xFFFFFFFE, LIBRE = 0xFFFFFFFF, FATSECT = 0xFFFFFFFD, DIFSECT = 0xFFFFFFFC, AUCUN = 0xFFFFFFFF;
/**
 * Un conteneur OLE : flux = [{ nom, donnees }]. options : { secteur: 512 |
 * 4096, miniFlux (false : tout en secteurs ordinaires), melange (les
 * secteurs des flux dans le désordre), boucle (le nom d'un flux dont la
 * chaîne revient sur elle-même), boucleRepertoire (la chaîne du répertoire
 * revient à son début), nomRacine }.
 */
function ole(flux, options) {
  const opt = options || {}, taille = opt.secteur || 512, parSecteur = taille / 4;
  const mini = opt.miniFlux !== false;
  const entrees = flux.map(function (f) { return { nom: f.nom, donnees: f.donnees, petit: mini && f.donnees.length < 4096 }; });
  /* Le mini-flux : les petits flux bout à bout, par blocs de 64 octets. */
  const blocs = [], miniFat = [];
  entrees.filter(function (e) { return e.petit; }).forEach(function (e) {
    const n = Math.ceil(e.donnees.length / 64);
    e.debut = n ? blocs.length : FIN;
    for (let k = 0; k < n; k++) {
      miniFat.push(k + 1 < n ? blocs.length + 1 : FIN);
      const b = Buffer.alloc(64); e.donnees.copy(b, 0, k * 64, Math.min(e.donnees.length, k * 64 + 64)); blocs.push(b);
    }
  });
  const miniFlux = Buffer.concat(blocs);
  const miniFatOctets = Buffer.concat(miniFat.map(u32));
  /* Les chaînes de secteurs : les flux ordinaires, le mini-flux, la mini-FAT, le répertoire. */
  const nbEntrees = 1 + entrees.length;
  const repertoire = Buffer.alloc(Math.ceil(nbEntrees * 128 / taille) * taille);
  const chaines = entrees.filter(function (e) { return !e.petit; }).map(function (e) { return { octets: e.donnees, entree: e }; });
  if (miniFlux.length) chaines.push({ octets: miniFlux, quoi: 'miniFlux' });
  if (miniFatOctets.length) chaines.push({ octets: miniFatOctets, quoi: 'miniFat' });
  chaines.push({ octets: repertoire, quoi: 'repertoire' });
  const D = chaines.reduce(function (s, c) { return s + Math.ceil(c.octets.length / taille); }, 0);
  let F = 0, X = 0;
  for (;;) {
    const f = Math.ceil((D + F + X) / parSecteur), x = f > 109 ? Math.ceil((f - 109) / (parSecteur - 1)) : 0;
    if (f === F && x === X) break;
    F = f; X = x;
  }
  /* Les numéros des secteurs de données : dans l'ordre, ou mélangés (un pas
     premier avec leur nombre). */
  const numeros = [];
  let pas = 1;
  if (opt.melange && D > 2) { pas = Math.max(2, Math.floor(D * 0.618)); while (pgcd(pas, D) !== 1) pas++; }
  for (let k = 0; k < D; k++) numeros.push((k * pas) % D);
  const fat = new Array(F * parSecteur).fill(LIBRE);
  let i = 0;
  chaines.forEach(function (c) {
    const n = Math.ceil(c.octets.length / taille), l = numeros.slice(i, i + n);
    i += n;
    c.secteurs = l;
    l.forEach(function (s, k) { fat[s] = k + 1 < n ? l[k + 1] : FIN; });
    /* La boucle : le deuxième secteur renvoie au premier, avant la fin du
       flux — un lecteur qui la suivrait ne s'arrêterait jamais. */
    /* Le répertoire dont la chaîne revient en arrière : seul son premier
       secteur se lit d'un bout à l'autre. */
    if (c.quoi === 'repertoire' && opt.boucleRepertoire) {
      if (n < 2) throw new Error('boucleRepertoire : il faut un répertoire d’au moins deux secteurs');
      fat[l[n - 1]] = l[0];
    }
    if (c.entree && opt.boucle === c.entree.nom) {
      if (n < 3) throw new Error('boucle : il faut un flux d’au moins trois secteurs');
      fat[l[1]] = l[0];
    }
  });
  const secteursFat = [], secteursDifat = [];
  for (let k = 0; k < F; k++) { secteursFat.push(D + k); fat[D + k] = FATSECT; }
  for (let k = 0; k < X; k++) { secteursDifat.push(D + F + k); fat[D + F + k] = DIFSECT; }
  const debutDe = function (quoi) { const c = chaines.filter(function (x) { return x.quoi === quoi; })[0]; return c && c.secteurs.length ? c.secteurs[0] : FIN; };
  chaines.forEach(function (c) { if (c.entree) c.entree.debut = c.secteurs.length ? c.secteurs[0] : FIN; });
  /* Le répertoire : la racine, puis chaque flux ; un arbre équilibré (frères
     à gauche et à droite), sous l'enfant de la racine. */
  function entree(k, nom, type, gauche, droite, enfant, debut, lg) {
    const o = k * 128, n = Buffer.from(nom + '\u0000', 'utf16le');
    n.copy(repertoire, o);
    repertoire.writeUInt16LE(n.length, o + 64);
    repertoire[o + 66] = type; repertoire[o + 67] = 1;
    repertoire.writeUInt32LE(gauche, o + 68); repertoire.writeUInt32LE(droite, o + 72); repertoire.writeUInt32LE(enfant, o + 76);
    repertoire.writeUInt32LE(debut, o + 116); repertoire.writeUInt32LE(lg, o + 120);
  }
  function arbre(debut, fin) {
    if (debut > fin) return AUCUN;
    const m = Math.floor((debut + fin) / 2), g = arbre(debut, m - 1), d = arbre(m + 1, fin);
    entree(m + 1, entrees[m].nom, 2, g, d, AUCUN, entrees[m].debut, entrees[m].donnees.length);
    return m + 1;
  }
  const enfant = arbre(0, entrees.length - 1);
  entree(0, opt.nomRacine || 'Root Entry', 5, AUCUN, AUCUN, enfant, debutDe('miniFlux'), miniFlux.length);
  for (let k = nbEntrees; k * 128 < repertoire.length; k++) { repertoire.writeUInt32LE(AUCUN, k * 128 + 68); repertoire.writeUInt32LE(AUCUN, k * 128 + 72); repertoire.writeUInt32LE(AUCUN, k * 128 + 76); }
  /* L'en-tête. */
  const tete = Buffer.alloc(taille);
  Buffer.from([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]).copy(tete, 0);
  tete.writeUInt16LE(0x3E, 0x18); tete.writeUInt16LE(taille === 512 ? 3 : 4, 0x1A); tete.writeUInt16LE(0xFFFE, 0x1C);
  tete.writeUInt16LE(taille === 512 ? 9 : 12, 0x1E); tete.writeUInt16LE(6, 0x20);
  tete.writeUInt32LE(taille === 512 ? 0 : repertoire.length / taille, 0x28);
  tete.writeUInt32LE(F, 0x2C); tete.writeUInt32LE(debutDe('repertoire'), 0x30); tete.writeUInt32LE(4096, 0x38);
  tete.writeUInt32LE(debutDe('miniFat'), 0x3C); tete.writeUInt32LE(Math.ceil(miniFatOctets.length / taille), 0x40);
  tete.writeUInt32LE(X ? secteursDifat[0] : FIN, 0x44); tete.writeUInt32LE(X, 0x48);
  for (let k = 0; k < 109; k++) tete.writeUInt32LE(k < F ? secteursFat[k] : LIBRE, 0x4C + 4 * k);
  /* Les secteurs. */
  const secteurs = new Array(D + F + X);
  chaines.forEach(function (c) {
    c.secteurs.forEach(function (s, k) { const b = Buffer.alloc(taille); c.octets.copy(b, 0, k * taille, Math.min(c.octets.length, (k + 1) * taille)); secteurs[s] = b; });
  });
  for (let k = 0; k < F; k++) {
    const b = Buffer.alloc(taille);
    for (let j = 0; j < parSecteur; j++) b.writeUInt32LE(fat[k * parSecteur + j], 4 * j);
    secteurs[D + k] = b;
  }
  const reste = secteursFat.slice(109);
  for (let k = 0; k < X; k++) {
    const b = Buffer.alloc(taille, 0xFF);
    for (let j = 0; j < parSecteur - 1 && reste.length; j++) b.writeUInt32LE(reste.shift(), 4 * j);
    b.writeUInt32LE(k + 1 < X ? secteursDifat[k + 1] : FIN, taille - 4);
    secteurs[D + F + k] = b;
  }
  return Buffer.concat([tete].concat(secteurs));
}
function pgcd(a, b) { return b ? pgcd(b, a % b) : a; }

/** Un .xls : le classeur BIFF dans son conteneur (« Workbook » en BIFF8, « Book » en BIFF5). */
function xls(spec, options) {
  const biff = spec.biff || 8;
  const autres = (options && options.autresFlux) || [];
  return ole([{ nom: biff === 8 ? 'Workbook' : 'Book', donnees: classeurBiff(spec) }].concat(autres), options);
}

// ===================================================================== page web archivée
function octets1252(t) { return octets8(t, 1252); }
/* Quoted-printable : lignes de 76 caractères au plus (« = » en fin de ligne
   coupée), « = » et les octets hors de l'ASCII imprimable écrits =XX. */
function quotedPrintable(o) {
  /* Écrit octet par octet dans un tampon : un gros export (70 Mo) se code en une seconde. */
  const sortie = Buffer.alloc(o.length * 3 + Math.ceil(o.length / 25) * 3 + 16), HEXA = '0123456789ABCDEF';
  let n = 0, ligne = 0;
  for (let i = 0; i < o.length; i++) {
    if (o[i] === 13 && o[i + 1] === 10) { sortie[n++] = 13; sortie[n++] = 10; ligne = 0; i++; continue; }
    if (o[i] === 10) { sortie[n++] = 13; sortie[n++] = 10; ligne = 0; continue; }
    const tel = (o[i] >= 33 && o[i] <= 126 && o[i] !== 61) || o[i] === 32, lg = tel ? 1 : 3;
    if (ligne + lg > 75) { sortie[n++] = 61; sortie[n++] = 13; sortie[n++] = 10; ligne = 0; }
    if (tel) sortie[n++] = o[i];
    else { sortie[n++] = 61; sortie[n++] = HEXA.charCodeAt(o[i] >> 4); sortie[n++] = HEXA.charCodeAt(o[i] & 15); }
    ligne += lg;
  }
  return sortie.toString('latin1', 0, n);
}
/**
 * Une page web archivée : parties = [{ lieu, type, jeu, codage:
 * 'quoted-printable' | 'base64' | '8bit', contenu (texte) }] ; options :
 * { simple: true } (une seule page, sans multipart), frontiere.
 */
function mhtml(parties, options) {
  const opt = options || {};
  const encoder = function (p) { return p.jeu && /1252|ascii/i.test(p.jeu) ? octets1252(p.contenu) : Buffer.from(p.contenu, 'utf8'); };
  const corps = function (p) {
    const o = encoder(p);
    if (p.codage === 'quoted-printable') return quotedPrintable(o);
    if (p.codage === 'base64') return o.toString('base64').replace(/.{76}/g, '$&\r\n');
    return o.toString('latin1');
  };
  if (opt.simple) {
    const p = parties[0];
    return Buffer.from('MIME-Version: 1.0\r\nContent-Location: ' + p.lieu + '\r\nContent-Transfer-Encoding: ' + p.codage + '\r\nContent-Type: ' + p.type +
      (p.jeu ? '; charset="' + p.jeu + '"' : '') + '\r\n\r\n' + corps(p) + '\r\n', 'latin1');
  }
  const frontiere = opt.frontiere || '----=_NextPart_01DB16A2.5F3C4E80';
  let t = 'MIME-Version: 1.0\r\nX-Document-Type: Workbook\r\nContent-Type: multipart/related;\r\n\tboundary="' + frontiere + '"\r\n\r\n' +
    'This document is a Single File Web Page, also known as a Web Archive file.  If you are seeing this message, your browser or editor ' +
    'doesn\'t support Web Archive files.\r\n\r\n';
  parties.forEach(function (p) {
    t += '--' + frontiere + '\r\nContent-Location: ' + p.lieu + '\r\nContent-Transfer-Encoding: ' + p.codage + '\r\nContent-Type: ' + p.type +
      (p.jeu ? '; charset="' + p.jeu + '"' : '') + '\r\n\r\n' + corps(p) + '\r\n\r\n';
  });
  return Buffer.from(t + '--' + frontiere + '--\r\n', 'latin1');
}

// ===================================================================== les sources des .xls de tests/xls/
/* Un export GATES en .xlsx comme GATES l'écrit (les mêmes règles que
   xlsxGates dans import-see.js) : la date de création en nombre au format
   jj/mm/aaaa, l'ATA en nombre, les seize fusions de la ligne des groupes. */
const I_DATE = colonne('Date création'), I_ATA = colonne('ATA');
function serie(t) { const m = /^(\d\d)\/(\d\d)\/(\d{4})$/.exec(t); return (Date.UTC(+m[3], +m[2] - 1, +m[1]) - Date.UTC(1899, 11, 30)) / 864e5; }
function lignesGates(g) {
  return g.valeurs.map(function (l, r) {
    return l.map(function (v, j) {
      if (r >= 2 && j === I_DATE && /^\d\d\/\d\d\/\d{4}$/.test(v)) return { n: serie(v), fmt: 'jour' };
      if (r >= 2 && j === I_ATA && /^\d+$/.test(v)) return Number(v);
      return v;
    });
  });
}
const ENTETE_SEE = ['SCHEMA NUMBER', 'NAME', 'SOL.', 'Cust.V', 'Released Date', 'Validated Date', 'REDRAW', 'ARCHIVED'];
function nomSee(i) { return 'TFE' + String(311 + (i % 50)) + 'A' + String(600 + i).padStart(4, '0'); }
/* Un export SEE : titre, ligne vide, en-tête en ligne 3 ; des codes à zéros
   de tête en texte, des dates, des booléens, et un texte avec tiret long et
   accents (des chaînes sur deux octets dans le .xls). */
function lignesSee(n) {
  const lignes = [['Nommage WD BFLOW'], [], ENTETE_SEE];
  for (let i = 0; i < n; i++) {
    lignes.push(['S-' + i, nomSee(i), String((i % 3) + 1).padStart(3, '0'), ['A', 'B', 'C'][i % 3], { n: 45000 + i, fmt: 'date' },
      i % 4 ? { n: 45100 + i, fmt: 'date' } : null, { b: i % 2 === 0 }, 'non — été ' + i]);
  }
  return lignes;
}
const SOURCES = {
  /* La vraie structure GATES : 186 plans, 138 colonnes, 16 fusions. */
  'gates': function () {
    const g = feuilleGates(186);
    return xlsx({ onglets: [{ nom: 'Export', lignes: lignesGates(g), fusions: g.fusions.map(function (f) { return { ligne: f.ligne, col: f.col, larg: f.larg }; }) }] });
  },
  /* 3 200 lignes : la table des textes partagés passe largement 8 224 octets. */
  'see': function () { return xlsx({ onglets: [{ nom: 'Nommage', lignes: lignesSee(3200) }] }); },
  /* Deux onglets, l'en-tête dans le second. */
  'deux-onglets': function () {
    return xlsx({ onglets: [{ nom: 'Lisez-moi', lignes: [['Export SEE du 01/10/2026'], ['Rien ici']] }, { nom: 'Données', lignes: lignesSee(40) }] });
  },
  /* Un premier onglet masqué, qui porte lui aussi un en-tête : l'onglet visible passe d'abord. Le
     visible est l'onglet actif : LibreOffice démasquerait un onglet masqué laissé actif. */
  'onglet-cache': function () {
    return xlsx({ actif: 1, onglets: [{ nom: 'Masqué', cache: true, lignes: [['NAME', 'SOL.', 'Cust.V'], ['MASQUE', '009', 'Z']] }, { nom: 'Export', lignes: lignesSee(25) }] });
  }
};

module.exports = { classeurBiff, ole, xls, mhtml, quotedPrintable, octets8, codeRk, sst, enregString, FORMATS, SOURCES, lignesGates, lignesSee, ENTETE_SEE, nomSee };

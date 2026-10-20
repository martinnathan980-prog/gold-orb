/* Assemble la page telle qu'Apps Script la rendrait, mais en local :
   on exécute le vrai Code.gs contre un classeur en mémoire, et on remplace
   les balises de modèle par leur résultat. C'est la seule façon de tester le
   chemin serveur → page sans déployer. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Feuille, Classeur, poserEnvironnement } = require('./faux-classeur');
const { feuilleExemple } = require('./feuille-exemple');
const { feuilleGates } = require('./feuille-gates');

const racine = path.join(__dirname, '..');

/* =====================================================================
   L'ENVELOPPE (débrief 23)
   Évalué par le modèle Index (pageDuTableau), donneesJSONPourPage() pose
   dans la page l'enveloppe compressée { format: 2, edition, contrat, cle,
   mesures, gz } ; getDonneesCompactes() la rend aussi. Les pages de cette
   batterie la reçoivent comme au classeur, et la décompressent elles-mêmes :
   une fois la page ouverte, window.SUIVI_FWD_DONNEES est le paquet décodé.
   { enveloppe: false } pose à la place le paquet en clair — celui que
   donneesJSONPourPage() rend quand on l'appelle hors du modèle (comme le
   chargeur). decoderEnveloppe() la relit ici, avec zlib.
   ===================================================================== */
const zlib = require('zlib');
/** L'enveloppe (objet ou texte JSON) rendue en paquet compact ; un paquet en clair passe tel quel. */
function decoderEnveloppe(e) {
  const x = typeof e === 'string' ? JSON.parse(e) : e;
  if (!x || x.format !== 2 || typeof x.gz !== 'string') return x;
  const b64 = x.gz.replace(/-/g, '+').replace(/_/g, '/');
  return JSON.parse(zlib.gunzipSync(Buffer.from(b64 + '===='.slice(0, (4 - b64.length % 4) % 4), 'base64')).toString('utf8'));
}
/** Ce que le modèle Index pose dans la page : l'enveloppe (le paquet en clair s'il est en erreur). */
function donneesPourIndex(contexte) {
  vm.runInContext('POUR_INDEX_ = true', contexte);
  try { return contexte.donneesJSONPourPage(); } finally { vm.runInContext('POUR_INDEX_ = false', contexte); }
}

/* `code` (facultatif) : le texte d'un autre Code.gs à évaluer — un
   correctif recollé seul, un déploiement resté sur l'ancienne version
   (tests/ouverture-serveur.js). */
function chargerServeur(classeur, proprietes, fichiers, code) {
  const muet = { log: function () {} };
  const contexte = vm.createContext(poserEnvironnement(
    { console: muet, JSON: JSON, Date: Date, Math: Math },
    classeur, proprietes, fichiers));
  vm.runInContext(typeof code === 'string' ? code : fs.readFileSync(path.join(racine, 'Code.gs'), 'utf8'), contexte);
  /* La configuration livrée suit une colonne nommée, HDK AA 011 >
     Avancement Définition Electrique, et n'en suit aucune autre si elle
     manque. Les extracts d'essai qui n'ont pas ce bloc (l'exemple simple,
     les onglets fabriqués à la main) tournent donc comme un classeur dont on
     aurait vidé COLONNE_FWD et COLONNE_CONCEPT : en détection automatique.
     Ceux qui ont la vraie structure gardent la configuration livrée. */
  if (!aLeBlocHDK(classeur)) {
    const cfg = vm.runInContext('CONFIG', contexte);
    cfg.COLONNE_FWD = '';
    cfg.COLONNE_CONCEPT = '';
  }
  /* Les jalons livrés sont ceux du contrat HDK (débrief 17 : THS n'en a
     pas). Un classeur d'essai qui n'a aucun onglet du contrat nommé —
     « Données », X1, X2… — les reçoit pour tous ses contrats, comme avant :
     ses pages gardent leurs échéances. Un classeur qui a l'onglet HDK garde
     la configuration livrée, telle quelle. */
  const cfgJ = vm.runInContext('CONFIG', contexte);
  const noms = (classeur && classeur.getSheets ? classeur.getSheets() : []).map(function (f) { return contexte.normaliser(f.getName()); });
  if (Array.isArray(cfgJ.JALONS) && !cfgJ.JALONS.some(function (j) {
    return (contexte.contratsDuJalon(j) || []).some(function (c) { return noms.indexOf(contexte.normaliser(c)) !== -1; });
  })) {
    cfgJ.JALONS = cfgJ.JALONS.map(function (j) {
      const copie = Object.assign({}, j);
      delete copie.contrat;
      return copie;
    });
  }
  return contexte;
}

function aLeBlocHDK(classeur) {
  if (!classeur || !classeur.getSheets) return false;
  return classeur.getSheets().some(function (f) {
    return (f.valeurs || []).slice(0, 8).some(function (l) {
      return (l || []).some(function (v) { return String(v).trim() === 'HDK AA 011'; });
    });
  });
}

/**
 * Cinq relevés à partir du seul qui vient d'être écrit : on recule celui-ci
 * de quatre semaines et on en fabrique un par semaine jusqu'à aujourd'hui,
 * pour que la page ait une pente, des groupes qui bougent et un journal qui
 * a quelque chose à raconter. L'onglet reçu est celui d'UN contrat.
 */
function etalerHistorique(histo, contexte) {
  const semaineCourante = contexte.numeroSemaineISO(new Date());
  const annee = Number(semaineCourante.slice(0, 4));
  const num = Number(semaineCourante.slice(6));
  const anterieure = function (recul) {
    const s = num - recul;
    return s >= 1 ? annee + '-S' + String(s).padStart(2, '0')
                  : (annee - 1) + '-S' + String(52 + s).padStart(2, '0');
  };
  const ligne = histo.valeurs[1];
  const base = ligne.slice();
  histo.valeurs.length = 1;
  [4, 3, 2, 1, 0].forEach(function (recul, k) {
    const l = base.slice();
    l[0] = anterieure(recul);
    // Progression artificielle des terminés, le reste glissant depuis « à faire ».
    const part = [0.45, 0.6, 0.75, 0.9, 1][k];
    l[3] = Math.round(base[3] * part);
    l[5] = base[5] + (base[3] - l[3]);
    // Les comptes par dimension suivent la même pente, sinon aucun groupe
    // n'aurait de rythme et la page n'aurait rien à projeter.
    const groupes = JSON.parse(base[7] || '{}');
    Object.keys(groupes).forEach(function (dim) {
      Object.keys(groupes[dim]).forEach(function (v) {
        groupes[dim][v] = {
          total: groupes[dim][v].total,
          termine: Math.round(groupes[dim][v].termine * part)
        };
      });
    });
    l[7] = JSON.stringify(groupes);
    /* L'avancement plan par plan doit vraiment différer d'une semaine à
       l'autre, sinon le journal des changements n'aurait rien à raconter. */
    /* La carte peut occuper plusieurs cellules à partir de la neuvième : on la
       recolle pour la relire, et on la redécoupe pour la réécrire. */
    const plans = JSON.parse(base.slice(8).join('') || '{}');
    const refs = Object.keys(plans);
    const aReculer = Math.round(refs.length * (1 - part) * 0.5);
    for (let r = 0; r < aReculer; r++) {
      const ref = refs[(r * 7 + k * 3) % refs.length];
      plans[ref] = ['À faire', '50%', ''][(r + k) % 3];
    }
    if (k === 0) { delete plans[refs[1]]; delete plans[refs[2]]; }   // deux plans apparus depuis
    l.length = 8;
    contexte.decouper(JSON.stringify(plans), vm.runInContext('MAX_CARACTERES_CELLULE', contexte))
      .forEach(function (tranche) { l.push(tranche); });
    histo.valeurs.push(l);
  });
}

function construire(options) {
  const opts = options || {};
  /* Un onglet de données par contrat. Par défaut un seul, « Données » ;
     { contrats: ['X1', 'X2'] } en crée plusieurs, de tailles décroissantes
     (186, 93, 62…) pour que le paquet d'un contrat ne ressemble pas à celui
     d'un autre. Un élément { nom, lignes } fixe la taille à la main. */
  const base = opts.lignes || 186;
  const contrats = (opts.contrats && opts.contrats.length ? opts.contrats : ['Données'])
    .map(function (c, i) {
      return typeof c === 'string' ? { nom: c, lignes: Math.max(12, Math.round(base / (i + 1))) } : c;
    });
  const onglets = contrats.map(function (c) {
    if (opts.gates) {
      // La vraie structure d'export : 137 colonnes, groupes fusionnés, blocs répétés.
      const g = feuilleGates(c.lignes);
      return new Feuille(c.nom, g.valeurs, false, g.fusions);
    }
    return new Feuille(c.nom, feuilleExemple(c.lignes));
  });
  /* Retoucher les onglets de données avant tout — par exemple y recopier des
     lignes, comme un export collé par-dessus l'ancien (débrief 17). */
  if (opts.retoucher) onglets.forEach(function (f) { opts.retoucher(f.valeurs, f.getName()); });
  /* D'autres onglets à côté des données — par exemple l'extract d'une seconde
     base à rapprocher — et une configuration à surcharger, comme le ferait
     quelqu'un qui édite Code.gs. */
  const classeur = new Classeur(onglets.concat(opts.feuilles || []), 'Suivi FWD H225');
  const contexte = chargerServeur(classeur, opts.proprietes || {});
  if (opts.config) {
    const cfg = vm.runInContext('CONFIG', contexte);
    Object.keys(opts.config).forEach(function (k) { cfg[k] = opts.config[k]; });
  }

  // Cinq relevés archivés, une semaine d'écart, pour que la page ait une pente.
  if (opts.historique === 'premier') {
    // Un seul relevé : le cas du tout premier archivage, où le graphique n'a
    // rien à tracer et où le bouton « voir un exemple » doit apparaître.
    contexte.enregistrerInstantaneHebdo();
  } else if (opts.historique !== false) {
    // L'archivage passe sur tous les contrats : chacun reçoit ses cinq relevés.
    contexte.enregistrerInstantaneHebdo();
    contexte.listerContrats(classeur).forEach(function (c) {
      etalerHistorique(contexte.getFeuilleHistorique(classeur, c.id, false), contexte);
    });
  }

  /* Le cache d'Apps Script allumé avant l'assemblage (débrief 23) : la page
     reçoit alors la clé de son paquet, comme au classeur. `cache` : true, ou
     les options de __activerCache. */
  if (opts.cache) contexte.__activerCache(opts.cache === true ? undefined : opts.cache);

  const paquet = contexte.getDonneesPourClient();

  let index = fs.readFileSync(path.join(racine, 'Index.html'), 'utf8');
  index = index.replace(/<\?!=\s*include\('(\w+)'\);?\s*\?>/g, function (_, nom) {
    return fs.readFileSync(path.join(racine, nom + '.html'), 'utf8');
  });
  const enveloppe = opts.enveloppe !== false;
  const donnees = enveloppe ? donneesPourIndex(contexte) : contexte.donneesJSONPourPage();
  index = index.replace(/<\?!=\s*donneesJSONPourPage\(\)\s*\?>/, function () { return donnees; });

  // Les polices locales évitent toute dépendance réseau pendant les tests.
  if (fs.existsSync(path.join(racine, 'prototype', 'fonts', 'local.css'))) {
    index = index.replace(/<link rel="stylesheet"[^>]*href="https:\/\/fonts\.googleapis\.com[^>]*>/,
                          '<link rel="stylesheet" href="prototype/fonts/local.css">');
  }

  fs.writeFileSync(path.join(racine, opts.sortie || 'apercu-addon.html'), index);
  return { paquet: paquet, contexte: contexte, classeur: classeur, enveloppe: enveloppe };
}

/**
 * Branche, dans une page Playwright, un `google.script.run` factice qui
 * répond par le vrai serveur du contexte : la page assemblée peut alors
 * changer de contrat exactement comme dans le classeur, par le pont
 * SUIVI_FWD_API d'Index.html — l'appel part de la page, passe par Node,
 * revient par le rappel de succès. À appeler AVANT page.goto().
 *
 * L'identifiant « __panne__ » fait échouer l'appel, pour éprouver le rappel
 * d'échec du pont. Les identifiants demandés s'accumulent dans
 * window.__appelsClasseur ; les mesures reçues par noterConsultation, dans
 * window.__mesuresNotees.
 *
 * Débrief 23 : getDonneesCompactes rend l'enveloppe compressée, comme au
 * classeur ; avec { enveloppe: false }, le paquet en clair, celui de
 * getDonneesCompactesJson.
 */
async function brancherClasseur(page, contexte, options) {
  const opts = options || {};
  const enveloppe = opts.enveloppe !== false;
  await page.exposeFunction('__classeurGetDonneesPourClient', function (id) {
    if (id === '__panne__') throw new Error('Panne simulée du classeur');
    return JSON.stringify(contexte.getDonneesPourClient(id === null ? undefined : id));
  });
  await page.exposeFunction('__classeurNoterConsultation', function (mesures) {
    return mesures === null ? contexte.noterConsultation() : contexte.noterConsultation(mesures);
  });
  await page.exposeFunction('__classeurGetDonneesCompactes', function (id) {
    if (id === '__panne__') throw new Error('Panne simulée du classeur');
    const contrat = id === null ? undefined : id;
    return enveloppe ? JSON.stringify(contexte.getDonneesCompactes(contrat)) : contexte.getDonneesCompactesJson(contrat);
  });
  await page.exposeFunction('__classeurGetDonneesCompactesJson', function (id) {
    if (id === '__panne__') throw new Error('Panne simulée du classeur');
    return contexte.getDonneesCompactesJson(id === null ? undefined : id);
  });
  await page.addInitScript(function () {
    function chaine(succes, echec) {
      return {
        withSuccessHandler: function (cb) { return chaine(cb, echec); },
        withFailureHandler: function (cb) { return chaine(succes, cb); },
        getDonneesPourClient: function (id) {
          window.__appelsClasseur.push(id);
          window.__classeurGetDonneesPourClient(id === undefined ? null : id).then(
            function (json) { if (succes) succes(JSON.parse(json)); },
            function (e) { if (echec) echec(e); });
        },
        // L'ouverture comptée (débrief 18) : compté à part, ce n'est pas un contrat demandé.
        noterConsultation: function (mesures) {
          window.__consultations = (window.__consultations || 0) + 1;
          if (mesures) window.__mesuresNotees.push(mesures);
          window.__classeurNoterConsultation(mesures === undefined ? null : mesures).then(function () {}, function (e) { if (echec) echec(e); });
        },
        // Le repli en clair (débrief 23) : une chaîne JSON, comme le vrai.
        getDonneesCompactesJson: function (id) {
          window.__appelsClasseur.push(id);
          window.__classeurGetDonneesCompactesJson(id === undefined ? null : id).then(
            function (json) { if (succes) succes(json); },
            function (e) { if (echec) echec(e); });
        },
        // Le pont d'Index.html demande le paquet compacté, comme au classeur.
        getDonneesCompactes: function (id) {
          window.__appelsClasseur.push(id);
          window.__classeurGetDonneesCompactes(id === undefined ? null : id).then(
            function (json) { if (succes) succes(JSON.parse(json)); },
            function (e) { if (echec) echec(e); });
        }
      };
    }
    window.__appelsClasseur = [];
    window.__mesuresNotees = [];
    window.google = { script: { run: chaine(null, null) } };
  });
}

if (require.main === module) {
  [{}, { gates: true, sortie: 'apercu-gates.html' }].forEach(function (opts) {
    const r = construire(opts);
    console.log((opts.sortie || 'apercu-addon.html') + ' écrit — ' + r.paquet.plans.length +
      ' plans, ' + r.paquet.colonnes.length + ' colonnes, ' + r.paquet.releves.length + ' relevés');
  });
}
module.exports = { construire, chargerServeur, brancherClasseur, decoderEnveloppe, donneesPourIndex };

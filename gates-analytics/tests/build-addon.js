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

function chargerServeur(classeur, proprietes, fichiers) {
  const muet = { log: function () {} };
  const contexte = vm.createContext(poserEnvironnement(
    { console: muet, JSON: JSON, Date: Date, Math: Math },
    classeur, proprietes, fichiers));
  vm.runInContext(fs.readFileSync(path.join(racine, 'Code.gs'), 'utf8'), contexte);
  return contexte;
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

  const paquet = contexte.getDonneesPourClient();

  let index = fs.readFileSync(path.join(racine, 'Index.html'), 'utf8');
  index = index.replace(/<\?!=\s*include\('(\w+)'\);?\s*\?>/g, function (_, nom) {
    return fs.readFileSync(path.join(racine, nom + '.html'), 'utf8');
  });
  index = index.replace(/<\?!=\s*donneesJSONPourPage\(\)\s*\?>/,
    contexte.donneesJSONPourPage());

  // Les polices locales évitent toute dépendance réseau pendant les tests.
  if (fs.existsSync(path.join(racine, 'prototype', 'fonts', 'local.css'))) {
    index = index.replace(/<link rel="stylesheet"[^>]*href="https:\/\/fonts\.googleapis\.com[^>]*>/,
                          '<link rel="stylesheet" href="prototype/fonts/local.css">');
  }

  fs.writeFileSync(path.join(racine, opts.sortie || 'apercu-addon.html'), index);
  return { paquet: paquet, contexte: contexte, classeur: classeur };
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
 * window.__appelsClasseur.
 */
async function brancherClasseur(page, contexte) {
  await page.exposeFunction('__classeurGetDonneesPourClient', function (id) {
    if (id === '__panne__') throw new Error('Panne simulée du classeur');
    return JSON.stringify(contexte.getDonneesPourClient(id === null ? undefined : id));
  });
  await page.exposeFunction('__classeurGetDonneesCompactes', function (id) {
    if (id === '__panne__') throw new Error('Panne simulée du classeur');
    return JSON.stringify(contexte.getDonneesCompactes(id === null ? undefined : id));
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
module.exports = { construire, chargerServeur, brancherClasseur };

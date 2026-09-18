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

function construire(options) {
  const opts = options || {};
  let donnees;
  if (opts.gates) {
    // La vraie structure d'export : 137 colonnes, groupes fusionnés, blocs répétés.
    const g = feuilleGates(opts.lignes || 186);
    donnees = new Feuille('Données', g.valeurs, false, g.fusions);
  } else {
    donnees = new Feuille('Données', feuilleExemple(opts.lignes || 186));
  }
  /* D'autres onglets à côté des données — par exemple l'extract d'une seconde
     base à rapprocher — et une configuration à surcharger, comme le ferait
     quelqu'un qui édite Code.gs. */
  const classeur = new Classeur([donnees].concat(opts.feuilles || []), 'Suivi FWD H225');
  const contexte = chargerServeur(classeur, opts.proprietes || {});
  if (opts.config) {
    const cfg = vm.runInContext('CONFIG', contexte);
    Object.keys(opts.config).forEach(function (k) { cfg[k] = opts.config[k]; });
  }

  // Deux relevés archivés, à deux semaines d'écart, pour que la page ait une pente.
  if (opts.historique === 'premier') {
    // Un seul relevé : le cas du tout premier archivage, où le graphique n'a
    // rien à tracer et où le bouton « voir un exemple » doit apparaître.
    contexte.enregistrerInstantaneHebdo();
  } else if (opts.historique !== false) {
    contexte.enregistrerInstantaneHebdo();
    const histo = classeur.getSheetByName('Historique_FWD');
    // On recule le relevé qu'on vient d'écrire et on en ajoute un plus récent.
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
      const plans = JSON.parse(base[8] || '{}');
      const refs = Object.keys(plans);
      const aReculer = Math.round(refs.length * (1 - part) * 0.5);
      for (let r = 0; r < aReculer; r++) {
        const ref = refs[(r * 7 + k * 3) % refs.length];
        plans[ref] = ['À faire', '50%', ''][(r + k) % 3];
      }
      if (k === 0) { delete plans[refs[1]]; delete plans[refs[2]]; }   // deux plans apparus depuis
      l[8] = JSON.stringify(plans);
      histo.valeurs.push(l);
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
    index = index.replace(/<link rel="stylesheet" href="https:\/\/fonts\.googleapis\.com[^"]*">/,
                          '<link rel="stylesheet" href="prototype/fonts/local.css">');
  }

  fs.writeFileSync(path.join(racine, opts.sortie || 'apercu-addon.html'), index);
  return { paquet: paquet, contexte: contexte, classeur: classeur };
}

if (require.main === module) {
  [{}, { gates: true, sortie: 'apercu-gates.html' }].forEach(function (opts) {
    const r = construire(opts);
    console.log((opts.sortie || 'apercu-addon.html') + ' écrit — ' + r.paquet.plans.length +
      ' plans, ' + r.paquet.colonnes.length + ' colonnes, ' + r.paquet.releves.length + ' relevés');
  });
}
module.exports = { construire, chargerServeur };

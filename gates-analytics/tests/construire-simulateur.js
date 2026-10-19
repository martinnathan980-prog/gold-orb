/* Le SIMULATEUR : la page livrée, servie par le vrai Code.gs, sur un classeur
   fictif au vocabulaire de GATES — de quoi la montrer et la manipuler sans
   classeur, sans Apps Script et sans aucune donnée d'Airbus.

       cd gates-analytics
       node tests/construire-simulateur.js <sortie.html> [--date=AAAA-MM-JJ]

   Ce que fait le script :
   1. Il fabrique en mémoire un classeur de deux contrats, HDK (634 plans) et
      THS (180 plans), à la vraie structure de l'export GATES (138 colonnes,
      groupes fusionnés, blocs HDK AA répétés : tests/feuille-gates.js). Le
      bloc HDK AA 011 porte les deux avancements suivis, avec les valeurs de
      GATES : VALIDATED, PWD_IN_PROGRESS, PWD_TO_CONTROL, TO_CONFIRM,
      FWD_TO_SEIZE, TO_TREAT, EMPTY pour la définition électrique ; vide,
      « À traiter », « Traité » pour le concept harnais. Les références sont
      de vraies références UD (TFE2130A600001A) : le journal reconnaît donc
      les changements d'indice, et SEE se rapproche de GATES.
   2. Il fait vivre ce classeur six semaines : chaque vendredi à 17 h, l'onglet
      de chaque contrat reçoit l'export de la semaine (des plans avancent,
      quelques-uns reculent, apparaissent, disparaissent ou changent
      d'indice) et l'archivage automatique du vendredi — le vrai,
      enregistrerInstantaneHebdo, lancé par son déclencheur — archive le
      relevé dans Historique_FWD_<contrat>.
   3. Chaque contrat a sa base SEE (« SEE HDK », « SEE THS »), telle que la
      fenêtre d'import la pose : la ligne « Trié à l’import », l'en-tête,
      puis les seules lignes du contrat (PSN 4530 pour HDK, celui de la
      configuration ; pour THS, le PSN tapé dans la fenêtre, gardé dans les
      propriétés du classeur).
   4. Il sert la page comme le lien …/exec : doGet() — qui vérifie que les
      fichiers du projet sont entiers —, puis le modèle Index évalué, ses
      balises <?!= … ?> exécutées dans le vrai serveur (include('Styles'),
      donneesJSONPourPage(), …).
   5. google.script.run est remplacé par un double qui répond, après 200 ms,
      par le paquet que le vrai getDonneesCompactes() a calculé pour chaque
      contrat : changer de contrat, la vue d'ensemble, l'interrupteur
      Définition électrique / Concept harnais marchent comme au classeur.
      noterConsultation ne compte rien.
   6. Les polices (prototype/fonts, alphabet latin) sont embarquées en data:
      URI : la page s'affiche juste dans un cadre isolé, sans réseau.

   Déterministe : le même dépôt et la même date donnent le même fichier, au
   caractère près (tirages pseudo-aléatoires à graine fixe, horloge du
   serveur figée, fuseau Europe/Paris comme le projet Apps Script). Sans
   --date, la date est celle du jour : les relevés sont ceux des six
   vendredis qui la précèdent, et la page dit « lus dans le classeur le …
   à 13:15 ».

   Le script ne touche à aucun fichier du dépôt ; il lit Code.gs, Index.html,
   Styles.html et Javascript.html tels qu'ils sont (node
   tests/split-prototype.js les régénère depuis le prototype). */
'use strict';

/* Le fuseau du projet Apps Script, avant toute date : le jour d'un relevé, sa
   semaine ISO et l'heure de lecture en dépendent. */
process.env.TZ = 'Europe/Paris';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Feuille, Classeur } = require('./faux-classeur');
const { chargerServeur } = require('./build-addon');
const gates = require('./feuille-gates');

const racine = path.join(__dirname, '..');

/* =====================================================================
   ARGUMENTS
   ===================================================================== */
function lireArguments(argv) {
  const opts = { sortie: null, date: process.env.SIMULATEUR_DATE || '' };
  argv.forEach(function (a) {
    let m;
    if ((m = /^--date=(.*)$/.exec(a))) opts.date = m[1];
    else if (a === '-h' || a === '--help') opts.aide = true;
    else if (/^--/.test(a)) throw new Error('option inconnue : ' + a);
    else if (!opts.sortie) opts.sortie = a;
    else throw new Error('un seul fichier de sortie : ' + a);
  });
  return opts;
}

/** Le jour de la construction, à minuit (heure de Paris) : --date, sinon aujourd'hui. */
function jourDeConstruction(texte) {
  if (!texte) {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), n.getDate());
  }
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(texte);
  const d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  if (!d || d.getMonth() !== +m[2] - 1 || d.getDate() !== +m[3]) throw new Error('date attendue AAAA-MM-JJ : ' + texte);
  return d;
}

/* =====================================================================
   LES CONTRATS FICTIFS
   Chaque fiche dit la taille du contrat (au dernier relevé), sa graine, et
   les événements scénarisés, par semaine (0 = le plus ancien des six
   relevés) : plans nouveaux, plans disparus, réémissions sous l'indice
   suivant, reculs (un VALIDATED qui repasse PWD_IN_PROGRESS). Le reste
   avance au hasard — un hasard à graine fixe.
   ===================================================================== */
const NB_SEMAINES = 6;
const CONTRATS = [
  {
    id: 'HDK', plans: 634, graine: 20261016, decalageGabarit: 0,
    codes: ['TF', 'WL', 'PA', 'PB', 'PC', 'LA', 'LB', 'MA', 'MB', 'NA', 'RA', 'RB', 'SA', 'SB', 'XA', 'XB', 'GA', 'GB'],
    nouveaux: { 1: 2, 3: 3, 5: 1 }, disparus: { 2: 1, 4: 2 }, reemis: { 2: 2, 3: 1, 4: 2, 5: 1 }, reculs: { 3: 1 },
    see: { psn: '4530', lues: 48213 }
  },
  {
    id: 'THS', plans: 180, graine: 20261024, decalageGabarit: 300,
    codes: ['KA', 'KB', 'KC', 'HA', 'HB', 'JA', 'JB', 'VA', 'VB', 'DA', 'DB', 'EA', 'EB', 'FA', 'FB', 'QA', 'QB', 'UA'],
    nouveaux: { 2: 1, 4: 2 }, disparus: { 3: 1 }, reemis: { 1: 1, 4: 1 }, reculs: { 4: 1 },
    /* THS n'a pas de PSN dans la configuration livrée : celui-ci est « tapé
       dans la fenêtre d'import », gardé dans les propriétés du classeur. */
    see: { psn: '4612', psnFenetre: true, lues: 48213 }
  }
];

/* La définition électrique, dans le vocabulaire de GATES. Une semaine, un
   plan passe à l'état suivant avec ces probabilités, ou ne bouge pas. */
const SUITE_DEF = {
  EMPTY: [['TO_TREAT', 0.003]],
  TO_TREAT: [['FWD_TO_SEIZE', 0.3], ['PWD_IN_PROGRESS', 0.35]],
  FWD_TO_SEIZE: [['PWD_IN_PROGRESS', 0.55]],
  PWD_IN_PROGRESS: [['PWD_TO_CONTROL', 0.04]],
  PWD_TO_CONTROL: [['TO_CONFIRM', 0.85], ['PWD_IN_PROGRESS', 0.05]],
  TO_CONFIRM: [['VALIDATED', 0.8]],
  VALIDATED: []
};
/* Au premier relevé : la photographie d'un contrat en pleine définition. */
const DEPART_DEF = [['VALIDATED', 0.035], ['PWD_IN_PROGRESS', 0.349], ['FWD_TO_SEIZE', 0.021], ['TO_TREAT', 0.058],
                    ['TO_CONFIRM', 0.011], ['PWD_TO_CONTROL', 0.009], ['EMPTY', 0.51]];
const DEPART_NOUVEAU = [['TO_TREAT', 0.5], ['FWD_TO_SEIZE', 0.2], ['EMPTY', 0.3]];
const EN_DEFINITION = { PWD_IN_PROGRESS: 1, PWD_TO_CONTROL: 1, TO_CONFIRM: 1, VALIDATED: 1 };

const ATA = ['21', '24', '25', '31', '33', '34', '39', '46', '53', '92'];
const INSTALLATIONS = [
  'Harnais alimentation cabine', 'Cheminement plancher avant', 'Boîtier de disjoncteurs',
  'Éclairage de soute', 'Platine de masse structure', 'Faisceau treuil de sauvetage',
  'Connectique traversée de cloison', 'Support calculateur avionique', 'Antenne VHF dorsale',
  'Coffret relais poste avant', 'Câblage siège pilote', 'Raccordement phare d’atterrissage',
  'Harnais capteurs boîte de transmission', 'Bâti convertisseur statique',
  'Cheminement console centrale', 'Bloc prises maintenance'
];
/* Les ECP : des numéros courts, et quelques intitulés longs — ceux qui, dans
   « Avancement FWD par ECP », ne doivent pas finir en « … ». */
const ECP = (function () {
  const l = [];
  for (let n = 2100; n < 2145; n++) l.push('ECP-' + n);
  l[17] = 'ECP-2117 MODIF HARNAIS PLANCHER CABINE';
  l[26] = 'ECP-2126 — Câblage galley avant / zone 200';
  l[33] = 'ECP-2133-RACCORDEMENT-CONSOLE-CENTRALE-B';
  return l;
}());

/* =====================================================================
   TIRAGES À GRAINE FIXE (mulberry32, celui du jeu de démonstration)
   ===================================================================== */
function generateur(graine) {
  let a = graine | 0;
  const alea = function () {
    a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
  return {
    alea: alea,
    entier: function (min, max) { return min + Math.floor(alea() * (max - min + 1)); },
    tire: function (liste) { return liste[Math.floor(alea() * liste.length)]; },
    pondere: function (paires) {
      let u = alea(), cumul = 0;
      for (let i = 0; i < paires.length; i++) { cumul += paires[i][1]; if (u < cumul) return paires[i][0]; }
      return paires[paires.length - 1][0];
    },
    /** Une transition : l'état suivant, ou le même. */
    suite: function (etat, table) {
      const choix = table[etat] || [];
      let u = alea(), cumul = 0;
      for (let i = 0; i < choix.length; i++) { cumul += choix[i][1]; if (u < cumul) return choix[i][0]; }
      return etat;
    },
    /** k éléments distincts de la liste, dans l'ordre du tirage. */
    choisir: function (liste, k) {
      const l = liste.slice(), r = [];
      while (r.length < k && l.length) r.push(l.splice(Math.floor(alea() * l.length), 1)[0]);
      return r;
    }
  };
}

const deux = function (n) { return (n < 10 ? '0' : '') + n; };
const jjmmaaaa = function (d) { return deux(d.getDate()) + '/' + deux(d.getMonth() + 1) + '/' + d.getFullYear(); };
const lettreSuivante = function (c) { return String.fromCharCode(c.charCodeAt(0) + 1); };
/** L'écriture de SEE, depuis la racine de GATES : TFE2130A600 → TFE213A0600 (voir racineSEE dans la page). */
const racineSEE = function (r) { return r.slice(0, 6) + 'A' + r.charAt(6) + r.slice(8); };
const somme = function (o) { return Object.keys(o).reduce(function (s, k) { return s + o[k]; }, 0); };

/* =====================================================================
   1. LES PLANS ET LEUR HISTOIRE
   ===================================================================== */
function histoireDuContrat(fiche, vendredis) {
  const g = generateur(fiche.graine);
  const nbDisparus = somme(fiche.disparus);
  const total = fiche.plans + nbDisparus;
  const plans = [];
  for (let k = 0; k < total; k++) {
    const ata = g.tire(ATA);
    const seq = g.pondere([['600', 0.45], ['700', 0.35], ['800', 0.2]]);
    /* La racine suit le rang (code circuit × sous-ATA) : deux plans ne
       portent jamais la même racine sous 1 080 plans. */
    const racineUD = fiche.codes[k % fiche.codes.length] + 'E' + ata + deux(10 + Math.floor(k / fiche.codes.length) % 60) + 'A' + seq;
    const installation = g.tire(INSTALLATIONS);
    plans.push({
      rang: k,
      racine: racineUD,
      solution: '00' + g.entier(1, 3),
      indice: g.pondere([['A', 0.55], ['B', 0.3], ['C', 0.12], ['D', 0.03]]),
      ata: ata,
      sequence: seq,
      cc: '3' + deux(g.entier(1, 12)) + '99',
      ecp: g.alea() < 0.86 ? g.tire(ECP) : '',
      domaine: g.alea() < 0.68 ? 'BASE/OPTION' : 'PERSO',
      installation: installation,
      libelle: installation + ' — faisceau ' + (k + 1),
      creation: jjmmaaaa(new Date(g.entier(2017, 2025), g.entier(0, 11), g.entier(1, 28))),
      vde: g.alea() < 0.3,
      debut: 0, fin: NB_SEMAINES,           // présent les semaines debut … fin-1
      reemis: -1,                           // semaine du changement d'indice
      def: new Array(NB_SEMAINES).fill(null),
      concept: new Array(NB_SEMAINES).fill(null)
    });
  }

  /* Les rôles : des plans qui disparaissent, des plans qui apparaissent. */
  const libres = plans.map(function (p) { return p.rang; });
  const prendre = function (n) { return g.choisir(libres, n).map(function (r) { libres.splice(libres.indexOf(r), 1); return plans[r]; }); };
  Object.keys(fiche.disparus).forEach(function (s) { prendre(fiche.disparus[s]).forEach(function (p) { p.fin = +s; }); });
  Object.keys(fiche.nouveaux).forEach(function (s) {
    prendre(fiche.nouveaux[s]).forEach(function (p) {
      p.debut = +s;
      /* Créé dans GATES la semaine où il apparaît : le mardi. */
      const mardi = new Date(vendredis[+s].getFullYear(), vendredis[+s].getMonth(), vendredis[+s].getDate() - 3);
      p.creation = jjmmaaaa(mardi);
    });
  });
  const stables = libres.slice();          // présents du premier au dernier relevé
  Object.keys(fiche.reemis).forEach(function (s) {
    g.choisir(stables.filter(function (r) { return plans[r].reemis === -1 && plans[r].indice !== 'D'; }), fiche.reemis[s])
      .forEach(function (r) { plans[r].reemis = +s; });
  });

  /* Semaine après semaine : l'état de chaque plan présent. */
  for (let s = 0; s < NB_SEMAINES; s++) {
    const reculs = [];
    if (fiche.reculs[s]) {
      const candidats = stables.filter(function (r) { return plans[r].def[s - 1] === 'VALIDATED'; });
      g.choisir(candidats, fiche.reculs[s]).forEach(function (r) { reculs.push(r); });
    }
    plans.forEach(function (p) {
      if (s < p.debut || s >= p.fin) return;
      let def, concept;
      if (s === p.debut) {
        def = g.pondere(p.debut === 0 ? DEPART_DEF : DEPART_NOUVEAU);
        /* Le concept harnais, le plus souvent en avance sur la définition. */
        concept = def === 'VALIDATED' || def === 'TO_CONFIRM' || def === 'PWD_TO_CONTROL'
          ? g.pondere([['Traité', 0.3], ['À traiter', 0.5], ['', 0.2]])
          : def === 'PWD_IN_PROGRESS' ? g.pondere([['Traité', 0.02], ['À traiter', 0.4], ['', 0.58]])
          : g.pondere([['À traiter', 0.2], ['', 0.8]]);
      } else {
        def = reculs.indexOf(p.rang) !== -1 ? 'PWD_IN_PROGRESS' : g.suite(p.def[s - 1], SUITE_DEF);
        const avant = p.concept[s - 1];
        concept = avant === 'À traiter' ? (g.alea() < 0.025 ? 'Traité' : avant)
          : avant === '' ? (g.alea() < 0.006 ? 'À traiter' : avant) : avant;
      }
      p.def[s] = def;
      p.concept[s] = concept;
    });
  }
  return plans;
}

function referenceDe(p, s) {
  return p.racine + p.solution + (p.reemis !== -1 && s >= p.reemis ? lettreSuivante(p.indice) : p.indice);
}

/* =====================================================================
   2. L'ONGLET D'UN CONTRAT, UNE SEMAINE DONNÉE
   La structure et les colonnes de remplissage viennent de feuilleGates ;
   les colonnes que la page lit sont posées ici.
   ===================================================================== */
const COL = {
  ref: gates.colonne('Référence UD'),
  libelle: gates.colonne('Libellé'),
  domaine: gates.colonne('Domaine'),
  creation: gates.colonne('Date création'),
  installation: gates.colonne('Nom Installation'),
  cc: gates.colonne('CC'),
  ata: gates.colonne('ATA'),
  sequence: gates.colonne('Séquence'),
  ecp: gates.colonne('ECP'),
  vde: gates.colonne('Validation Définition Electrique', 'Définition du plan'),
  def: gates.colonne('Avancement Définition Electrique', 'HDK AA 011'),
  concept: gates.colonne('Avancement Concept Harnais', 'HDK AA 011')
};
Object.keys(COL).forEach(function (k) { if (COL[k] < 0) throw new Error('feuille-gates : colonne introuvable — ' + k); });

function gabaritDuContrat(fiche, nbPlans) {
  const g = gates.feuilleGates(fiche.decalageGabarit + nbPlans);
  return {
    entete: g.valeurs.slice(0, 3),                 // groupes, intitulés, ligne de service sans référence
    lignes: g.valeurs.slice(3 + fiche.decalageGabarit),
    fusions: g.fusions
  };
}

function valeursDeLaSemaine(gabarit, plans, s) {
  const valeurs = gabarit.entete.map(function (l) { return l.slice(); });
  plans.forEach(function (p) {
    if (s < p.debut || s >= p.fin) return;
    const l = gabarit.lignes[p.rang].slice();
    l[COL.ref] = referenceDe(p, s);
    l[COL.libelle] = p.libelle;
    l[COL.domaine] = p.domaine;
    l[COL.creation] = p.creation;
    l[COL.installation] = p.installation;
    l[COL.cc] = p.cc;
    l[COL.ata] = p.ata;
    l[COL.sequence] = p.sequence;
    l[COL.ecp] = p.ecp;
    l[COL.vde] = EN_DEFINITION[p.def[s]] || p.vde ? 'true' : 'false';
    l[COL.def] = p.def[s];
    l[COL.concept] = p.concept[s];
    valeurs.push(l);
  });
  return valeurs;
}

/* =====================================================================
   3. LA BASE SEE D'UN CONTRAT
   Un plan présent dans SEE est un plan créé : presque tous les VALIDATED y
   sont — quelques-uns manquent, quelques-uns y sont sous un autre indice —,
   SEE en connaît quelques autres que GATES ne dit pas encore validés, et
   quelques lignes n'appartiennent à aucun plan du contrat.
   ===================================================================== */
const ENTETE_SEE = ['NAME', 'SOL.', 'Cust.V', 'Int. V', 'ARCHIVE FILE PREFIX', 'VALIDITY PSN FULL', 'User Status', 'DIAGRAM TYPE',
  'PRODUCT FAMILY', 'Validated', '', '', 'FG1 TAGDESCRIPTION', 'DESCRIPTION', 'SCHEMA NUMBER', 'Released Date', 'Obsolete Date',
  'Validated Date', 'REDRAW', '', 'ARCHIVED', '', 'CGM'];
const TAGS_SEE = ['WRNG RECEIVER', 'PWR DISTRIBUTION', 'CABIN LIGHTING', 'AVIONICS BAY', 'HOIST CONTROL', 'GROUND POINTS'];

function baseSEE(fiche, plans, jour) {
  const g = generateur(fiche.graine + 7);
  const s = NB_SEMAINES - 1;
  const autresPsn = ['4510', '4520', '4540', '4550', '4561', '4570', '4590', '4601'].filter(function (x) { return x !== fiche.see.psn; });
  const lignes = [];
  function ligne(racineUD, solution, indice, p, valide) {
    const n = lignes.length;
    const psn = g.choisir(autresPsn, g.entier(0, 3)).concat([fiche.see.psn]).sort();
    const sortie = new Date(jour.getFullYear(), jour.getMonth(), jour.getDate() - g.entier(10, 400));
    const validation = new Date(sortie.getFullYear(), sortie.getMonth(), sortie.getDate() + g.entier(1, 20));
    const v = {
      'NAME': racineSEE(racineUD), 'SOL.': solution, 'Cust.V': indice, 'Int. V': String(g.entier(0, 3)),
      'ARCHIVE FILE PREFIX': 'WD' + (104200 + n * 7), 'VALIDITY PSN FULL': psn.join(g.alea() < 0.5 ? ',' : ', '),
      'User Status': 'Released', 'DIAGRAM TYPE': 'WD', 'PRODUCT FAMILY': 'HARNESS', 'Validated': valide ? 'TRUE' : 'FALSE',
      'FG1 TAGDESCRIPTION': g.tire(TAGS_SEE), 'DESCRIPTION': p ? p.installation.toUpperCase() : 'FAISCEAU HORS GATES ' + (n + 1),
      'SCHEMA NUMBER': 'SPE993A' + (4632001 + n), 'Released Date': jjmmaaaa(sortie), 'Obsolete Date': '',
      'Validated Date': valide ? jjmmaaaa(validation) : '', 'REDRAW': g.alea() < 0.15 ? 'TRUE' : 'FALSE', 'ARCHIVED': 'FALSE',
      'CGM': valide ? 'TRUE' : 'FALSE'
    };
    lignes.push(ENTETE_SEE.map(function (t) { return t ? v[t] : ''; }));
  }
  let valides = 0, autres = 0;
  plans.forEach(function (p) {
    if (s < p.debut || s >= p.fin) return;
    const indice = referenceDe(p, s).slice(-1);
    if (p.def[s] === 'VALIDATED') {
      valides++;
      if (valides % 13 === 6) return;                                            // validé, absent de SEE
      ligne(p.racine, p.solution, valides % 11 === 4 ? lettreSuivante(indice) : indice, p, true);   // autre indice
    } else if (p.def[s] === 'TO_CONFIRM' || p.def[s] === 'PWD_TO_CONTROL' || p.def[s] === 'PWD_IN_PROGRESS') {
      autres++;
      if (p.def[s] !== 'PWD_IN_PROGRESS' ? autres % 3 === 1 : autres % 47 === 5) ligne(p.racine, p.solution, indice, p, false);
    }
  });
  /* Seulement dans SEE : un code circuit et un ATA que le contrat n'emploie pas. */
  for (let k = 0; k < 4; k++) ligne('ZZE99' + deux(10 + k) + 'A800', '001', 'A', null, true);

  const nb = function (n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f'); };
  const marque = ['Trié à l’import : PSN ' + fiche.see.psn + ' · DIAGRAM TYPE = WD — ' + nb(lignes.length) + ' lignes gardées sur ' +
    nb(fiche.see.lues) + ' · « Nommage WD BFLOW.xlsx », le ' + jjmmaaaa(jour)];
  while (marque.length < ENTETE_SEE.length) marque.push('');
  return [marque, ENTETE_SEE.slice()].concat(lignes);
}

/* =====================================================================
   4. L'HORLOGE DU SERVEUR
   Le vrai Code.gs lit l'heure par new Date() : on la lui donne. Une seule
   classe, dont « maintenant » se règle, pour que les dates archivées
   restent des Date aux yeux du serveur (instanceof Date).
   ===================================================================== */
function horloge() {
  let maintenant = 0;
  class DateSimulee extends Date {
    constructor() {
      if (arguments.length === 0) super(maintenant);
      else super(...arguments);
    }
    static now() { return maintenant; }
  }
  return { Date: DateSimulee, regler: function (d) { maintenant = d.getTime(); } };
}

/* =====================================================================
   5. LA PAGE
   ===================================================================== */
/** Le modèle Index évalué comme le fait HtmlService : chaque <?!= expr ?>
    exécuté dans le serveur, <?= expr ?> échappé. */
function evaluerModele(texte, contexte) {
  const echapper = function (t) { return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); };
  return texte.replace(/<\?(!=|=)?([\s\S]*?)\?>/g, function (tout, sorte, code) {
    if (!sorte) throw new Error('Index.html : balise <? … ?> non simulée — ' + code.trim().slice(0, 80));
    const v = vm.runInContext(code.trim().replace(/;\s*$/, ''), contexte);
    const t = v === undefined || v === null ? '' : String(v);
    return sorte === '!=' ? t : echapper(t);
  });
}

/** Les @font-face de l'alphabet latin, polices embarquées (une par fichier,
    avec sa plage de graisses : Newsreader et IBM Plex Sans sont variables). */
function policesEmbarquees() {
  const dossier = path.join(racine, 'prototype', 'fonts');
  const css = fs.readFileSync(path.join(dossier, 'local.css'), 'utf8');
  const parFichier = new Map();
  for (const m of css.matchAll(/\/\* latin \*\/\s*(@font-face \{[\s\S]*?\})/g)) {
    const bloc = m[1];
    const fichier = /url\(['"]?(?:fonts\/)?([^)'"]+)['"]?\)/.exec(bloc)[1];
    const cle = fichier + '|' + /font-family: '([^']+)'/.exec(bloc)[1] + '|' + /font-style: ([^;]+);/.exec(bloc)[1];
    const poids = Number(/font-weight: ([^;]+);/.exec(bloc)[1]);
    const f = parFichier.get(cle);
    if (!f) parFichier.set(cle, { fichier: fichier, bloc: bloc, min: poids, max: poids });
    else { f.min = Math.min(f.min, poids); f.max = Math.max(f.max, poids); }
  }
  if (!parFichier.size) throw new Error('prototype/fonts/local.css : aucun bloc @font-face « latin »');
  return Array.from(parFichier.values()).map(function (f) {
    const b64 = fs.readFileSync(path.join(dossier, f.fichier)).toString('base64');
    return f.bloc
      .replace(/url\([^)]+\)/, 'url(data:font/woff2;base64,' + b64 + ')')
      .replace(/font-weight: [^;]+;/, 'font-weight: ' + (f.min === f.max ? f.min : f.min + ' ' + f.max) + ';')
      .replace(/\n\s*unicode-range: [^;]+;/, '');
  }).join('\n');
}

/** Du JSON qu'on peut poser dans un <script> sans le couper (comme donneesJSONPourPage). */
function jsonPourScript(objet) {
  return JSON.stringify(objet).replace(/</g, '\\u003c').replace(/>/g, '\\u003e')
    .replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
}
const echAttr = function (t) { return String(t).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); };

/* Le double de google.script.run. Les paquets attendent dans des
   <script type="application/json"> : le navigateur ne les lit pas au
   chargement — la page s'ouvre avec le seul poids du paquet d'ouverture,
   comme au classeur —, et chaque demande en relit un exemplaire neuf (la
   page déballe le paquet reçu sur place). */
const DOUBLE_GOOGLE = [
  '<script>',
  '  /* Simulateur : google.script.run répond par les paquets que le vrai Code.gs a calculés à la construction',
  '     (getDonneesCompactes, contrat par contrat), après 200 ms, comme un aller-retour au classeur. */',
  '  (function () {',
  '    function paquet(id) {',
  '      var cle = id === undefined || id === null ? \'\' : String(id);',
  '      var blocs = document.querySelectorAll(\'script.simulateur-paquet\');',
  '      for (var i = 0; i < blocs.length; i++) {',
  '        var b = blocs[i];',
  '        if (b.getAttribute(\'data-contrat\') === cle || (cle === \'\' && b.hasAttribute(\'data-ouverture\'))) return JSON.parse(b.textContent);',
  '      }',
  '      return null;',
  '    }',
  '    function chaine(ok, ko) {',
  '      return {',
  '        withSuccessHandler: function (f) { return chaine(f, ko); },',
  '        withFailureHandler: function (f) { return chaine(ok, f); },',
  '        withUserObject: function () { return chaine(ok, ko); },',
  '        getDonneesCompactes: function (id) {',
  '          setTimeout(function () {',
  '            var p = paquet(id);',
  '            if (p && ok) ok(p);',
  '            else if (!p && ko) ko(new Error(\'Contrat inconnu du simulateur : \' + id));',
  '          }, 200);',
  '        },',
  '        noterConsultation: function () { /* le simulateur ne compte rien */ }',
  '      };',
  '    }',
  '    window.google = { script: { run: chaine(null, null) } };',
  '  })();',
  '</script>'
].join('\n');

/** Les fonctions serveur que la page appelle par google.script.run, lues dans ses fichiers. */
function appelsDeLaPage(texte) {
  const noms = {};
  const re = /google\.script\.run((?:\s*\.\s*with\w+\((?:[^()]|\([^()]*(?:\([^()]*\)[^()]*)*\))*\))*)\s*\.\s*(\w+)\s*\(/g;
  let m;
  while ((m = re.exec(texte))) noms[m[2]] = true;
  return Object.keys(noms);
}

/* =====================================================================
   CONSTRUCTION
   ===================================================================== */
function construireSimulateur(options) {
  const opts = options || {};
  const jour = jourDeConstruction(opts.date);
  const lecture = new Date(jour.getFullYear(), jour.getMonth(), jour.getDate(), 13, 15, 0);

  ['Index', 'Styles', 'Javascript'].forEach(function (nom) {
    if (!fs.existsSync(path.join(racine, nom + '.html'))) {
      throw new Error(nom + '.html manque : le régénérer depuis le prototype (node tests/split-prototype.js), puis relancer.');
    }
  });

  /* Les six vendredis qui précèdent le jour de construction. */
  const vendredis = [];
  for (let d = new Date(jour.getFullYear(), jour.getMonth(), jour.getDate() - 1); vendredis.length < NB_SEMAINES; d.setDate(d.getDate() - 1)) {
    if (d.getDay() === 5) vendredis.unshift(new Date(d.getFullYear(), d.getMonth(), d.getDate(), 17, 0, 0));
  }

  /* Les plans, leur histoire, et les onglets. */
  const contrats = CONTRATS.map(function (fiche) {
    const plans = histoireDuContrat(fiche, vendredis);
    const gabarit = gabaritDuContrat(fiche, plans.length);
    const feuille = new Feuille(fiche.id, valeursDeLaSemaine(gabarit, plans, 0), false, gabarit.fusions);
    return { fiche: fiche, plans: plans, gabarit: gabarit, feuille: feuille };
  });
  const onglets = contrats.map(function (c) { return c.feuille; })
    .concat(contrats.map(function (c) { return new Feuille('SEE ' + c.fiche.id, baseSEE(c.fiche, c.plans, jour)); }));
  const classeur = new Classeur(onglets, 'Suivi FWD');

  /* Le PSN tapé dans la fenêtre d'import, gardé dans le classeur (CLE_PSN). */
  const proprietes = {};
  const psnFenetre = {};
  CONTRATS.forEach(function (f) { if (f.see.psnFenetre) psnFenetre[f.id] = [f.see.psn]; });
  if (Object.keys(psnFenetre).length) proprietes.SUIVI_FWD_PSN = JSON.stringify(psnFenetre);

  /* Le vrai serveur, avec son horloge et un hasard à graine fixe. */
  const contexte = chargerServeur(classeur, proprietes);
  const temps = horloge();
  contexte.Date = temps.Date;
  const hasard = generateur(20261019);
  contexte.Math = Object.create(Math, { random: { value: hasard.alea } });

  /* Six vendredis : l'export de la semaine, puis l'archivage automatique. */
  temps.regler(vendredis[0]);
  contexte.installerSuiviHebdomadaire();
  const declencheur = contexte.ScriptApp.getProjectTriggers()[0];
  vendredis.forEach(function (vendredi, s) {
    contrats.forEach(function (c) { c.feuille.valeurs = valeursDeLaSemaine(c.gabarit, c.plans, s); });
    temps.regler(new Date(vendredi.getTime() + 5 * 60000));
    contexte.enregistrerInstantaneHebdo({ triggerUid: declencheur.getUniqueId() });
  });

  /* L'ouverture de la page, à 13 h 15 le jour de construction. */
  temps.regler(lecture);
  const servie = contexte.doGet({ parameter: {} });
  if (!servie || !servie.source || servie.source.modele !== 'Index') {
    throw new Error('doGet() ne sert pas le tableau de bord :\n' + (servie && servie.getContent ? servie.getContent().replace(/<[^>]+>/g, ' ') : servie));
  }
  let page = evaluerModele(fs.readFileSync(path.join(racine, 'Index.html'), 'utf8'), contexte);

  /* Les paquets que google.script.run rendra, calculés par le vrai serveur. */
  const ouverture = JSON.parse(contexte.donneesJSONPourPage());
  const paquets = contexte.listerContrats(classeur).map(function (c) {
    return { id: c.id, paquet: contexte.getDonneesCompactes(c.id) };
  });
  paquets.forEach(function (p) {
    if (!p.paquet || p.paquet.ok === false) throw new Error('Code.gs ne rend pas le contrat ' + p.id + ' : ' + (p.paquet && p.paquet.message));
  });
  const texteOuverture = JSON.stringify(ouverture);
  const memeQueLOuverture = paquets.filter(function (p) { return JSON.stringify(p.paquet) === texteOuverture; })[0];
  const blocsPaquets = paquets.map(function (p) {
    return '<script type="application/json" class="simulateur-paquet" data-contrat="' + echAttr(p.id) + '"' +
      (p === memeQueLOuverture ? ' data-ouverture' : '') + '>' + jsonPourScript(p.paquet) + '</script>';
  }).concat(memeQueLOuverture ? [] : ['<script type="application/json" class="simulateur-paquet" data-ouverture>' + jsonPourScript(ouverture) + '</script>']);

  /* Le bandeau, d'après ce que le serveur a réellement rendu. */
  const nbPlans = function (p) { return p.plansTab ? p.plansTab.lignes.length : (p.plans || []).length; };
  const nbReleves = function (p) { return p.relevesTab ? p.relevesTab.releves.length : (p.releves || []).length; };
  const mots = ['zéro', 'une', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf', 'dix'];
  const releves = nbReleves(paquets[0].paquet);
  const liste = paquets.map(function (p) { return p.id + ' (' + nbPlans(p.paquet) + ' plans)'; });
  const avecSEE = paquets.filter(function (p) { return p.paquet.rapprochement; }).length;
  const edition = String(ouverture.edition || vm.runInContext('EDITION', contexte));
  const bandeau = '<div class="simulateur-bandeau" role="note" style="margin:0 auto;max-width:1180px;padding:10px 16px;' +
    'font:13px/1.5 \'IBM Plex Sans\',system-ui,sans-serif;color:var(--encre-2);background:var(--creux);border-bottom:1px solid var(--filet)">' +
    '<b style="color:var(--encre);font-weight:600">Simulateur</b> — la page livrée (livraison ' + echAttr(edition) + '), servie par le vrai ' +
    'Code.gs, sur des données fictives au vocabulaire de GATES : ' + liste.slice(0, -1).join(', ') + (liste.length > 1 ? ' et ' : '') +
    liste[liste.length - 1] + ', ' + (mots[releves] || releves) + ' semaine' + (releves > 1 ? 's' : '') + ' archivée' + (releves > 1 ? 's' : '') +
    (avecSEE ? ', ' + (avecSEE === paquets.length ? 'une base SEE par contrat' : 'une base SEE') : '') + '. Aucune donnée d’Airbus.</div>';

  /* L'assemblage : le titre, les polices embarquées, le double de
     google.script.run et le bandeau en tête du corps, les paquets à la fin. */
  const remplacer = function (texte, motif, par, quoi) {
    if (!motif.test(texte)) throw new Error('Index.html : ' + quoi + ' introuvable');
    return texte.replace(motif, function () { return par; });
  };
  page = remplacer(page, /<title>[^<]*<\/title>/, '<title>Simulateur Suivi FWD</title>', '<title>');
  page = page.replace(/\s*<meta charset="[^"]*">/i, '');
  page = remplacer(page, /<head>/i, '<head>\n    <meta charset="utf-8">', '<head>');
  page = page.replace(/\s*<link rel="preconnect"[^>]*>/, '');
  page = remplacer(page, /<link rel="stylesheet"[^>]*href="https:\/\/fonts\.googleapis\.com[^>]*>/,
    '<style>\n' + policesEmbarquees() + '\n</style>', 'lien Google Fonts');
  page = remplacer(page, /<body>/i, '<body>\n' + DOUBLE_GOOGLE + '\n' + bandeau, '<body>');
  page = remplacer(page, /<\/body>(?![\s\S]*<\/body>)/i, blocsPaquets.join('\n') + '\n</body>', '</body>');

  /* Ce que le simulateur ne sait pas rendre se dit à la construction. */
  const avertissements = [];
  const servies = { getDonneesCompactes: true, noterConsultation: true };
  const appels = appelsDeLaPage(['Index', 'Javascript'].map(function (n) { return fs.readFileSync(path.join(racine, n + '.html'), 'utf8'); }).join('\n'));
  appels.filter(function (n) { return !servies[n]; }).forEach(function (n) {
    avertissements.push('la page appelle google.script.run.' + n + '(), que le simulateur ne sert pas : à ajouter dans tests/construire-simulateur.js');
  });
  paquets.forEach(function (p) {
    if (p.paquet.message) avertissements.push(p.id + ' : le serveur dit « ' + p.paquet.message + ' »');
    if (p.paquet.avis) avertissements.push(p.id + ' : avis du serveur « ' + p.paquet.avis + ' »');
  });
  const resteExterne = page.match(/(?:src|href)="https?:\/\/[^"]*"/g);
  if (resteExterne) avertissements.push('ressource externe restante : ' + resteExterne.join(', '));

  return {
    page: page,
    edition: edition,
    vendredis: vendredis,
    lecture: lecture,
    paquets: paquets,
    avertissements: avertissements,
    resume: paquets.map(function (p) {
      const P = p.paquet, rap = P.rapprochement;
      /* Les valeurs du jour, comptées comme la page les compte : de quoi
         comparer d'une construction à l'autre. */
      const compter = function (cle) {
        const i = P.plansTab ? P.plansTab.cles.indexOf(cle) : -1, n = {};
        (P.plansTab ? P.plansTab.lignes : []).forEach(function (l) { const v = i === -1 ? '' : String(l[i] === null ? '' : l[i]) || 'vide'; n[v] = (n[v] || 0) + 1; });
        return Object.keys(n).sort(function (a, b) { return n[b] - n[a]; }).map(function (v) { return v + ' ' + n[v]; }).join(' · ');
      };
      return p.id + ' : ' + nbPlans(P) + ' plans, ' + nbReleves(P) + ' relevés, ' + (P.jalons || []).length + ' jalons, ' +
        (rap ? 'SEE ' + (rap.lignesTab ? rap.lignesTab.lignes.length : (rap.lignes || []).length) + ' lignes' + (rap.filtre ? ' (' + rap.filtre + ')' : '') : 'sans SEE') +
        '\n    définition électrique : ' + compter('avancement') + (P.cleConcept ? '\n    concept harnais : ' + compter(P.cleConcept) : '');
    })
  };
}

if (require.main === module) {
  let opts;
  try { opts = lireArguments(process.argv.slice(2)); } catch (e) { console.error(e.message); process.exit(2); }
  if (opts.aide || !opts.sortie) {
    console.error('Usage : node tests/construire-simulateur.js <sortie.html> [--date=AAAA-MM-JJ]');
    process.exit(opts.aide ? 0 : 2);
  }
  let r;
  try { r = construireSimulateur(opts); } catch (e) { console.error('Simulateur non construit : ' + (e && e.message ? e.message : e)); process.exit(1); }
  const sortie = path.resolve(opts.sortie);
  fs.writeFileSync(sortie, r.page);
  const jjmm = function (d) { return deux(d.getDate()) + '/' + deux(d.getMonth() + 1) + '/' + d.getFullYear(); };
  console.log(sortie + ' écrit — livraison ' + r.edition + ', ' + Math.round(Buffer.byteLength(r.page) / 1024) + ' Ko');
  console.log('  relevés des vendredis ' + jjmm(r.vendredis[0]) + ' … ' + jjmm(r.vendredis[r.vendredis.length - 1]) +
    ', page lue le ' + jjmm(r.lecture) + ' à 13:15');
  r.resume.forEach(function (l) { console.log('  ' + l); });
  r.avertissements.forEach(function (a) { console.warn('  ⚠ ' + a); });
}

module.exports = { construireSimulateur };

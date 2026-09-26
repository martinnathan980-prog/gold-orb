/* =========================================================================
   ETII Hub — « À venir » : la ligne des prochains rendez-vous

   Le Communication center raconte ce qui s'est passé ; ce bloc montre ce
   qui arrive, et rien d'autre : une ligne. Elle part d'aujourd'hui, file
   vers la droite, et chaque rendez-vous s'y pose à sa date. Le glyphe du
   point dit le type — un losange pour un jalon, un rond pour une réunion,
   une cible pour une revue, un carré pour un atelier, un triangle pour une
   formation, une étoile pour un événement — et sa couleur dit le pôle (le
   gris d'encre pour tout le service). Une tige fine monte ou descend du
   point jusqu'à l'étiquette : la date en petites capitales, le titre en
   Newsreader. Pas de carte, pas de cadre, pas de compte à rebours.

   La ligne porte le temps. Deux intervalles égaux y sont égaux (une
   réunion chaque semaine, c'est un point tous les mêmes centimètres) ;
   un intervalle long pèse un peu moins que ses jours, et huit semaines
   sans rien deviennent une coupure — deux traits obliques et « ≈ 3 mois »
   — plutôt qu'une longue ligne vide. Le nom de chaque mois pend à côté du
   cran qui l'ouvre ; un cran marque chaque lundi, un plus fin chaque
   jour tant que la place le permet. Les étiquettes alternent au-dessus
   et au-dessous ; quand des dates se serrent, elles montent d'une rangée,
   sans jamais se chevaucher ni se faire couper par une tige, et près du
   bord droit elles se posent à gauche de leur tige. La ligne tient dans
   sa largeur : faute de place, les titres passent sur deux lignes. En
   dernier recours seulement, elle s'allonge et défile — au doigt, en
   glissant à la souris, par les flèches posées sur ses bords.

   La ligne vit. Elle se trace quand on arrive dessus, les points se posent
   quand elle les atteint, les tiges poussent, les étiquettes montent. Puis
   un signal part d'aujourd'hui et court jusqu'au prochain rendez-vous, qui
   répond d'une onde : c'est le seul « bientôt » de la ligne. Survoler un
   point (ou le rejoindre au clavier) l'allume : les autres s'estompent, la
   ligne se colore d'aujourd'hui jusqu'à lui, et un aperçu flottant dit le
   reste — le jour en toutes lettres, l'heure, le lieu, ce qui s'y joue.
   Un clic l'ouvre en grand, avec de quoi l'ajouter à son agenda (.ics).
   Les flèches du clavier passent d'un point à l'autre. La légende, sous la
   ligne, allume au survol tous les rendez-vous d'un type ou d'un pôle.
   Rien ne bouge si le système demande moins d'animations ; rien ne tourne
   quand la ligne est hors de l'écran.

   Sur un écran étroit, la ligne se dresse : une colonne, aujourd'hui en
   haut, les mois en intertitres, chaque rendez-vous détaillé à côté de son
   point. C'est la même liste dans le document, dans l'ordre des dates :
   celle que lisent les lecteurs d'écran.

   En mode édition (edition.js), chaque étiquette porte « Modifier » et
   « Supprimer », et un bouton ajoute un rendez-vous. Un rendez-vous passé
   quitte la ligne de lui-même, le lendemain.

   API :
     agenda(donnees, options)  -> HTMLElement
       options.pole            'ETII' (tout le service) ou un code de pôle
                               (ses rendez-vous et ceux du service)
       options.limite          nombre de rendez-vous au plus (défaut 8)
       options.surAjouter(b), options.surModifier(entree, b), options.surSupprimer(entree)
   ========================================================================= */

import { el, svg, monter, ouvrirModale, toast } from './ui.js';
import { joursRestants, TYPES_AGENDA } from './kiosque.js';
import { barreEdition, boutonAjouter } from './edition.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const MOIS_LONGS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
const JOURS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const JOURS_COURTS = ['dim.', 'lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.'];
const JOUR_MS = 86400000;

/* La ligne, en pixels et en jours. `origine` laisse à gauche la place de
   « Aujourd'hui ». L'écart dessiné entre deux dates vaut k × (jours) ^
   `exposant` : k est le plus grand qui fasse tenir la ligne dans sa
   largeur, sans qu'une semaine dépasse `semaineMax`. `coupure` jours sans
   rien deviennent une coupure de `largeurCoupure`, avec `abords` jours de
   chaque côté. Les étiquettes montent d'au plus `rangeesMax` rangées de
   chaque côté ; en dernier recours, la ligne s'allonge et défile. Sous
   `largeurMin`, elle se dresse en colonne. */
const LIGNE = {
  origine: 150,
  bord: 8,
  bordPoint: 36,
  exposant: 0.65,
  semaineMax: 250,
  ecartPoints: 28,
  coupure: 56,
  abords: 7,
  largeurCoupure: 104,
  ecartEtiquettes: 11,
  base: 34,
  ecartRangees: 14,
  rangeesMax: 4,
  reserve: 34,
  marge: 16,
  traitPres: 2.4,
  traitLoin: 0.9,
  largeurMin: 640
};

/* Ce que chaque ligne a mesuré à sa dernière mise en page : les
   rendez-vous, leurs positions, l'axe. */
const ETATS = new WeakMap();

let compteur = 0;

function dateDe(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(texte(iso));
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}

function aujourdhui() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/* « aujourd'hui », « demain », « dans 5 jours », « dans 3 semaines » :
   pour les lecteurs d'écran seulement — la ligne, elle, montre la
   distance. */
function echeance(n) {
  if (n === null) return '';
  if (n <= 0) return 'aujourd’hui';
  if (n === 1) return 'demain';
  if (n < 14) return 'dans ' + n + ' jours';
  if (n < 60) return 'dans ' + Math.round(n / 7) + ' semaines';
  return 'dans ' + Math.round(n / 30) + ' mois';
}

function libellePole(pole) { return pole === 'ETII' ? 'Service' : pole; }
function dateCourte(d) { return d ? JOURS_COURTS[d.getDay()] + ' ' + d.getDate() + ' ' + MOIS[d.getMonth()] : ''; }
function dateLongue(d, annee) {
  return d ? JOURS[d.getDay()] + ' ' + d.getDate() + ' ' + MOIS_LONGS[d.getMonth()] + (annee ? ' ' + d.getFullYear() : '') : '';
}

/* -------------------------------------------------------------------------
   1. Les glyphes : un par type de rendez-vous, centrés sur l'origine
   ------------------------------------------------------------------------- */

const FORMES = {
  jalon:     () => [svg('polygon', { points: '0,-8.5 8.5,0 0,8.5 -8.5,0' })],
  reunion:   () => [svg('circle', { r: '6.5' })],
  revue:     () => [svg('circle', { r: '7.25' }), svg('circle', { r: '2.6', class: 'agenda__glyphe-coeur' })],
  atelier:   () => [svg('rect', { x: '-6', y: '-6', width: '12', height: '12', rx: '2' })],
  formation: () => [svg('polygon', { points: '0,-7.5 7.8,6 -7.8,6' })],
  evenement: () => [svg('path', { d: 'M0 -9 L2.5 -2.5 L9 0 L2.5 2.5 L0 9 L-2.5 2.5 L-9 0 L-2.5 -2.5 Z' })],
  autre:     () => [svg('circle', { r: '6' })]
};

function glyphe(cle, classe) {
  return svg('svg', {
    viewBox: '-10 -10 20 20', class: ['agenda__glyphe', classe || null],
    'aria-hidden': 'true', focusable: 'false'
  }, (FORMES[cle] || FORMES.autre)());
}

/* -------------------------------------------------------------------------
   2. Un rendez-vous : le point, la tige, l'étiquette
   ------------------------------------------------------------------------- */

function lire(entree, rang) {
  const cle = texte(entree.type);
  return {
    entree,
    rang,
    iso: texte(entree.date),
    date: dateDe(entree.date),
    n: joursRestants(entree.date),
    pole: texte(entree.pole).toUpperCase() || 'ETII',
    cleType: FORMES[cle] ? cle : 'autre',
    type: TYPES_AGENDA[cle] || cle || 'Rendez-vous',
    titre: texte(entree.titre),
    heure: texte(entree.heure),
    lieu: texte(entree.lieu),
    resume: texte(entree.resume)
  };
}

function rendezVous(info, options, prefixe) {
  const idDetails = prefixe + '-' + info.rang;
  const li = el('li', {
    class: ['agenda__rdv', info.rang === 0 ? 'agenda__rdv--prochain' : null],
    dataset: { pole: info.pole, type: info.cleType, date: info.iso, i: String(info.rang) }
  },
  el('span', { class: 'agenda__tige', 'aria-hidden': 'true' }),
  el('span', { class: 'agenda__point', 'aria-hidden': 'true' }, glyphe(info.cleType)),
  el('button', {
    type: 'button', class: 'agenda__cible', tabindex: info.rang === 0 ? 0 : -1,
    'aria-describedby': idDetails
  },
  /* Le nom accessible dit tout en une phrase : le type, le pôle, la date
     en toutes lettres, l'échéance. À l'écran : « VEN. 2 OCT. · ETIIA »,
     puis le titre. */
  el('span', { class: 'visuellement-cache' },
    info.type + ' · ' + libellePole(info.pole) + ', ' + dateLongue(info.date) + (info.n !== null ? ', ' + echeance(info.n) : '') + ' : '),
  el('span', { class: 'agenda__quand', 'aria-hidden': 'true' },
    el('span', { class: 'agenda__jour' }, dateCourte(info.date)),
    el('span', { class: 'agenda__pole' }, libellePole(info.pole))),
  el('span', { class: 'agenda__titre' }, info.titre)),
  /* Le détail : caché sur la ligne (l'aperçu flottant le montre), écrit
     en toutes lettres dans la colonne des écrans étroits. */
  el('p', { class: 'agenda__details', id: idDetails },
    el('span', { class: 'agenda__details-type' }, info.type + (info.heure ? ' · ' + info.heure : '')),
    info.lieu ? el('span', { class: 'agenda__details-lieu' }, info.lieu) : null,
    info.resume ? el('span', { class: 'agenda__details-resume' }, info.resume) : null),
  (typeof options.surModifier === 'function' || typeof options.surSupprimer === 'function')
    ? barreEdition({
        classe: 'agenda__edition barre-edition--compacte',
        quoi: info.titre,
        surModifier: typeof options.surModifier === 'function' ? (b) => options.surModifier(info.entree, b) : null,
        surSupprimer: typeof options.surSupprimer === 'function' ? () => options.surSupprimer(info.entree) : null
      })
    : null);
  return li;
}

/* L'aperçu flottant : ce que l'étiquette ne dit pas. Décoratif pour les
   lecteurs d'écran, qui ont déjà tout dans le détail du rendez-vous. */
function apercu(info) {
  return [
    el('p', { class: 'agenda__apercu-type' }, glyphe(info.cleType, 'agenda__apercu-glyphe'),
      info.type + ' · ' + libellePole(info.pole)),
    el('p', { class: 'agenda__apercu-titre' }, info.titre),
    el('p', { class: 'agenda__apercu-quand' }, dateLongue(info.date, true) + (info.heure ? ' · ' + info.heure : '')),
    info.lieu ? el('p', { class: 'agenda__apercu-lieu' }, info.lieu) : null,
    info.resume ? el('p', { class: 'agenda__apercu-resume' }, info.resume) : null
  ];
}

/* -------------------------------------------------------------------------
   3. Le rendez-vous en grand, et dans son agenda (.ics)
   ------------------------------------------------------------------------- */

/* « 14 h », « 9 h 30 », « 14:00 » : l'heure saisie librement, lue pour le
   fichier d'agenda. Illisible : le rendez-vous est posé sur la journée. */
function lireHeure(v) {
  const m = /^(\d{1,2})\s*(?:h|:)\s*(\d{2})?/i.exec(texte(v));
  if (!m) return null;
  const h = Number(m[1]);
  const mn = Number(m[2] || 0);
  return h < 24 && mn < 60 ? { h, mn } : null;
}

function deux(n) { return String(n).padStart(2, '0'); }
function jourIcs(d) { return d.getFullYear() + deux(d.getMonth() + 1) + deux(d.getDate()); }

/* Le texte d'un champ iCalendar : barres obliques, points-virgules,
   virgules et retours à la ligne échappés (RFC 5545 §3.3.11). */
function echapperIcs(v) {
  return texte(v).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');
}

/* Une ligne iCalendar ne dépasse pas 75 octets (UTF-8) : on la replie,
   la suite commençant par une espace (RFC 5545 §3.1). Un caractère
   accentué compte double. */
function plier(ligne) {
  const morceaux = [];
  let courant = '';
  let octets = 0;
  for (const c of ligne) {
    const code = c.codePointAt(0);
    const n = code < 0x80 ? 1 : code < 0x800 ? 2 : code < 0x10000 ? 3 : 4;
    if (octets + n > 73) { morceaux.push(courant); courant = ''; octets = 0; }
    courant += c;
    octets += n;
  }
  morceaux.push(courant);
  return morceaux.join('\r\n ');
}

function versIcs(info) {
  const maintenant = new Date();
  const horodatage = maintenant.getUTCFullYear() + deux(maintenant.getUTCMonth() + 1) + deux(maintenant.getUTCDate())
    + 'T' + deux(maintenant.getUTCHours()) + deux(maintenant.getUTCMinutes()) + deux(maintenant.getUTCSeconds()) + 'Z';
  const heure = lireHeure(info.heure);
  const lendemain = new Date(info.date.getFullYear(), info.date.getMonth(), info.date.getDate() + 1);
  const quand = heure
    ? ['DTSTART:' + jourIcs(info.date) + 'T' + deux(heure.h) + deux(heure.mn) + '00',
       'DURATION:PT1H']
    : ['DTSTART;VALUE=DATE:' + jourIcs(info.date), 'DTEND;VALUE=DATE:' + jourIcs(lendemain)];
  return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ETII Hub//A venir//FR', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    'UID:etii-' + echapperIcs(texte(info.entree.id) || info.iso + '-' + info.rang),
    'DTSTAMP:' + horodatage,
    ...quand,
    'SUMMARY:' + echapperIcs(info.titre),
    info.lieu ? 'LOCATION:' + echapperIcs(info.lieu) : null,
    info.resume ? 'DESCRIPTION:' + echapperIcs(info.resume) : null,
    'END:VEVENT', 'END:VCALENDAR']
    .filter(Boolean).map(plier).join('\r\n') + '\r\n';
}

function telechargerIcs(info) {
  if (!info.date) return;
  try {
    const url = URL.createObjectURL(new Blob([versIcs(info)], { type: 'text/calendar;charset=utf-8' }));
    const lien = el('a', { href: url, download: 'rendez-vous-' + info.iso + '.ics', hidden: true });
    document.body.appendChild(lien);
    lien.click();
    lien.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    toast('Le rendez-vous est prêt : ouvrez le fichier pour l’ajouter à votre agenda.', 'succes');
  } catch (_e) {
    toast('Ce navigateur ne permet pas d’enregistrer le fichier d’agenda.', 'alerte');
  }
}

function ouvrirFiche(info, declencheur) {
  ouvrirModale({
    titre: info.titre,
    declencheur,
    classe: 'agenda-fiche',
    contenu: el('div', { class: 'agenda-fiche__corps', dataset: { pole: info.pole } },
      el('p', { class: 'agenda-fiche__type' }, glyphe(info.cleType, 'agenda-fiche__glyphe'),
        info.type + ' · ' + libellePole(info.pole)),
      el('p', { class: 'agenda-fiche__quand' }, dateLongue(info.date, true) + (info.heure ? ' · ' + info.heure : '')),
      info.lieu ? el('p', { class: 'agenda-fiche__lieu' }, el('span', { class: 'agenda-fiche__cle' }, 'Lieu'), info.lieu) : null,
      info.resume ? el('p', { class: 'agenda-fiche__resume' }, info.resume) : null),
    actions: [
      { libelle: 'Ajouter à mon agenda', variante: 'secondaire', ferme: false, onClick: () => telechargerIcs(info) },
      { libelle: 'Fermer', variante: 'principal', autofocus: true }
    ]
  });
}

/* -------------------------------------------------------------------------
   4. La mise en page de la ligne
   ------------------------------------------------------------------------- */

/* L'écart dessiné entre deux dates suit le temps qui les sépare, adouci :
   deux intervalles égaux restent égaux (des réunions chaque semaine sont
   également espacées), un intervalle long pèse moins que ses jours. */
function poids(jours) { return Math.pow(Math.max(0, jours), LIGNE.exposant); }

/* Les tronçons de la ligne, d'aujourd'hui au dernier rendez-vous : un par
   intervalle entre deux dates. Huit semaines sans rien : on garde une
   semaine de chaque côté, et le reste devient une coupure. */
function troncons(jours) {
  const liste = [];
  let avant = 0;
  jours.forEach((j) => {
    if (j - avant >= LIGNE.coupure) {
      liste.push({ a: avant + LIGNE.abords, poids: poids(LIGNE.abords) });
      liste.push({ a: j - LIGNE.abords, coupe: true });
      liste.push({ a: j, poids: poids(LIGNE.abords), point: true });
    } else {
      liste.push({ a: j, poids: poids(j - avant), point: true });
    }
    avant = j;
  });
  return liste;
}

/* L'échelle pour un facteur k : les nœuds (un jour, sa position), et la
   position de chaque rendez-vous. Entre deux nœuds, le temps est droit ;
   deux points ne se touchent jamais, même le même jour. */
function echelle(liste, k, ecart) {
  const noeuds = [{ j: 0, x: LIGNE.origine }];
  const xs = [];
  let x = LIGNE.origine;
  for (const t of liste) {
    x += t.coupe ? LIGNE.largeurCoupure : Math.max(k * t.poids, t.point ? ecart || LIGNE.ecartPoints : 0);
    noeuds.push({ j: t.a, x, coupe: !!t.coupe });
    if (t.point) xs.push(Math.round(x));
  }
  return { noeuds, xs };
}

/* La position d'un jour ; null dans une coupure ou au-delà de la ligne. */
function versX(noeuds, j) {
  if (j <= noeuds[0].j) return noeuds[0].x;
  for (let i = 1; i < noeuds.length; i += 1) {
    const a = noeuds[i - 1];
    const b = noeuds[i];
    if (j > b.j) continue;
    if (b.coupe && j > a.j && j < b.j) return null;
    return b.j === a.j ? b.x : a.x + (b.x - a.x) * (j - a.j) / (b.j - a.j);
  }
  return null;
}

/* Au-delà du dernier rendez-vous, la ligne file au pas d'une semaine
   ordinaire, jusqu'au bord. */
function prolonger(noeuds, k, jusqua) {
  const dernier = noeuds[noeuds.length - 1];
  const pas = Math.max(2, k * poids(7) / 7);
  if (jusqua > dernier.x) noeuds.push({ j: dernier.j + (jusqua - dernier.x) / pas, x: jusqua });
  return noeuds;
}

/* Les côtés et les rangées des étiquettes. Une étiquette part de sa tige
   vers la droite, ou vers la gauche (ancre « d ») quand elle déborderait.
   Deux règles : deux étiquettes d'une même rangée ne se touchent pas, et
   une tige ne traverse jamais une étiquette — celle qui la couvrirait
   monte d'une rangée. On essaie toutes les façons de répartir les
   rendez-vous de part et d'autre (le premier toujours au-dessus) et l'on
   garde la plus basse, à hauteur égale celle qui alterne le mieux. */
function ranger(xs, mesure, ancres) {
  const n = xs.length;
  const { largeurs, hauteurs } = mesure;
  const e = LIGNE.ecartEtiquettes;
  const zones = xs.map((x, i) => (ancres[i] === 'g' ? [x - e, x + largeurs[i] + e] : [x - largeurs[i] - e, x + e]));
  /* La tige de j passe dans la zone de l'étiquette i. */
  const traverse = (i, j) => xs[j] > zones[i][0] && xs[j] < zones[i][1];
  const touche = (i, j) => zones[i][0] < zones[j][1] && zones[j][0] < zones[i][1];
  const plusHaute = Math.max(...hauteurs);
  const alterne = Array.from({ length: n }, (_, i) => i % 2).reduce((m, c, i) => m | (c << i), 0);
  const masques = n <= 9 ? Array.from({ length: 1 << Math.max(0, n - 1) }, (_, m) => m << 1) : [alterne];
  let meilleur = null;
  for (const masque of masques) {
    const cote = (i) => (masque >> i) & 1;
    const rangees = new Array(n).fill(0);
    let possible = true;
    for (let change = true; change && possible;) {
      change = false;
      for (let i = 0; i < n && possible; i += 1) {
        for (let j = 0; j < n; j += 1) {
          if (i === j || cote(i) !== cote(j)) continue;
          if (traverse(i, j)) {
            if (rangees[i] <= rangees[j]) { rangees[i] = rangees[j] + 1; change = true; }
          } else if (i > j && !traverse(j, i) && touche(i, j) && rangees[i] === rangees[j]) {
            rangees[i] += 1;
            change = true;
          }
          if (rangees[i] >= LIGNE.rangeesMax) { possible = false; break; }
        }
      }
    }
    if (!possible) continue;
    /* La hauteur de chaque rangée : la plus haute de ses étiquettes. Un
       côté vide compte pour une rangée : on préfère deux côtés d'une
       rangée à un seul de deux. */
    const hautes = [[], []];
    rangees.forEach((r, i) => { hautes[cote(i)][r] = Math.max(hautes[cote(i)][r] || 0, hauteurs[i]); });
    const etendue = (h) => (h.length ? LIGNE.base + h.reduce((s, v) => s + (v || 0) + LIGNE.ecartRangees, 0) - LIGNE.ecartRangees : 0);
    let cout = [0, 1].reduce((s, c) => s + Math.max(etendue(hautes[c]), LIGNE.base + plusHaute), 0);
    for (let i = 1; i < n; i += 1) if (cote(i) === cote(i - 1)) cout += 6;
    if (!meilleur || cout < meilleur.cout) {
      meilleur = { cout, hautes, etendues: hautes.map(etendue), places: rangees.map((r, i) => ({ cote: cote(i) ? 'bas' : 'haut', rangee: r })) };
    }
  }
  return meilleur;
}

/* La largeur qu'occupe vraiment une étiquette : jusqu'au bout de son
   texte le plus long (un titre sur deux lignes laisse de l'air à droite
   de sa boîte), ou de sa barre d'édition. */
function largeurUtile(li) {
  const gauche = li.getBoundingClientRect().left;
  let droite = gauche + 13;
  const r = document.createRange();
  for (const n of li.querySelectorAll('.agenda__quand, .agenda__titre, .agenda__edition')) {
    r.selectNodeContents(n);
    droite = Math.max(droite, r.getBoundingClientRect().right);
  }
  return Math.ceil(Math.min(li.offsetWidth, droite - gauche));
}

/* Les étiquettes mesurées dans une forme : large (le titre sur une ligne
   tant qu'il tient) ou serrée (sur deux lignes, pour qu'il en tienne plus
   côte à côte). */
function mesurer(racine, items, serre) {
  racine.classList.toggle('agenda--serre', serre);
  items.forEach((it) => {
    it.li.classList.remove('agenda__rdv--droite');
    it.li.style.removeProperty('inline-size');
  });
  return {
    serre,
    largeurs: items.map((it) => largeurUtile(it.li) + 2),
    hauteurs: items.map((it) => it.li.offsetHeight)
  };
}

/* Une mise en page pour un facteur k dans la largeur, ou null si elle
   n'y tient pas. */
function essayer(liste, k, mesure, largeur) {
  const { noeuds, xs } = echelle(liste, k);
  if (xs[xs.length - 1] > largeur - LIGNE.bordPoint) return null;
  const ancres = xs.map((x, i) => (x + mesure.largeurs[i] <= largeur - LIGNE.bord ? 'g' : 'd'));
  if (xs.some((x, i) => ancres[i] === 'd' && x - mesure.largeurs[i] < LIGNE.origine)) return null;
  const rang = ranger(xs, mesure, ancres);
  return rang ? Object.assign(rang, { noeuds, xs, ancres, k, mesure }) : null;
}

/* Le plus grand facteur qui garde le dernier point dans la largeur, sans
   qu'une semaine dépasse `semaineMax` : la ligne remplit la place, sans
   étirer quelques rendez-vous proches sur tout l'écran. */
function facteurMax(liste, largeur) {
  const plafond = LIGNE.semaineMax / poids(7);
  const fin = (k) => { const { xs } = echelle(liste, k); return xs[xs.length - 1]; };
  if (fin(plafond) <= largeur - LIGNE.bordPoint) return plafond;
  let bas = 0;
  let haut = plafond;
  for (let i = 0; i < 24; i += 1) {
    const milieu = (bas + haut) / 2;
    if (fin(milieu) <= largeur - LIGNE.bordPoint) bas = milieu; else haut = milieu;
  }
  return bas;
}

/* La meilleure mise en page dans la largeur : on essaie les deux formes
   d'étiquettes et quelques resserrements de l'échelle, et l'on garde la
   plus basse — une forme serrée ou une échelle resserrée coûtent un peu.
   Rien ne tient : la ligne s'allonge et défile, en dernier recours. */
function choisir(liste, largeur, mesures) {
  const kMax = facteurMax(liste, largeur);
  let meilleur = null;
  for (const mesure of mesures) {
    for (const f of [1, 0.86, 0.72]) {
      const essai = kMax > 0 ? essayer(liste, kMax * f, mesure, largeur) : null;
      if (!essai) continue;
      const cout = essai.cout + (mesure.serre ? 40 : 0) + (1 - f) * 220;
      if (!meilleur || cout < meilleur.total) meilleur = Object.assign(essai, { total: cout, largeur });
    }
  }
  if (meilleur) return meilleur;
  /* La ligne défile : les étiquettes larges, à droite de leur tige ;
     l'échelle et l'écart entre deux points s'étirent ensemble jusqu'à ce
     qu'elles tiennent sur deux rangées de chaque côté (quatre au plus).
     Au pire, un point par largeur d'étiquette : tout tient sur une. */
  const mesure = mesures[0];
  const sansFin = mesure.largeurs.map(() => 'g');
  const poser = (k, ecart) => {
    const { noeuds, xs } = echelle(liste, k, ecart);
    const rang = ranger(xs, mesure, sansFin);
    if (!rang) return null;
    const longueur = Math.max(largeur, ...xs.map((x, i) => x + mesure.largeurs[i] + LIGNE.bord));
    return Object.assign(rang, { noeuds, xs, ancres: sansFin, k, mesure, largeur: longueur });
  };
  let secours = null;
  for (let k = Math.max(kMax, 40 / poids(7)), ecart = LIGNE.ecartPoints, essai = 0; essai < 16; essai += 1, k *= 1.2, ecart *= 1.2) {
    secours = poser(k, ecart) || secours;
    if (secours && secours.places.every((p) => p.rangee < 2)) break;
  }
  return secours || poser(Math.max(kMax, 40 / poids(7)), Math.max(...mesure.largeurs) + 2 * LIGNE.ecartEtiquettes + 2);
}

/**
 * Pose la ligne : l'échelle du temps, les points, les rangées
 * d'étiquettes, les mois, les crans. Ou dresse la colonne quand la place
 * manque. Idempotent : appelée à chaque changement de taille.
 */
function disposer(racine) {
  const etat = ETATS.get(racine);
  if (!etat || !racine.isConnected) return;
  const { scene, toile, trace, mois, items } = etat;
  const largeur = scene.clientWidth;
  if (!largeur) return;
  const colonne = largeur < LIGNE.largeurMin;
  racine.classList.toggle('agenda--colonne', colonne);
  racine.classList.toggle('agenda--ligne', !colonne);
  racine.classList.remove('agenda--attente');
  const debut = aujourdhui();

  if (colonne) {
    racine.classList.remove('agenda--serre');
    toile.style.removeProperty('inline-size');
    toile.style.removeProperty('block-size');
    toile.style.removeProperty('translate');
    trace.replaceChildren();
    mois.replaceChildren();
    /* L'écart entre deux rendez-vous suit, de loin, le temps qui les
       sépare ; le mois s'écrit au-dessus du premier de chaque mois. */
    let precedent = debut;
    items.forEach((it, i) => {
      const d = it.info.date || debut;
      const jours = Math.max(0, Math.round((d - precedent) / JOUR_MS));
      it.li.removeAttribute('style');
      it.li.style.setProperty('--ecart', Math.min(40, jours * 3) + 'px');
      it.li.style.setProperty('--retard', (i * 90) + 'ms');
      if (d.getMonth() !== precedent.getMonth() || d.getFullYear() !== precedent.getFullYear()) {
        it.li.dataset.mois = MOIS_LONGS[d.getMonth()] + (d.getFullYear() !== debut.getFullYear() ? ' ' + d.getFullYear() : '');
      } else {
        delete it.li.dataset.mois;
      }
      it.li.classList.remove('agenda__rdv--haut', 'agenda__rdv--bas', 'agenda__rdv--droite');
      precedent = d;
    });
    /* Le signal descend le rail, du point d'aujourd'hui au prochain. */
    const cadre = toile.getBoundingClientRect();
    const depart = toile.querySelector('.agenda__aujourdhui-point').getBoundingClientRect();
    const arrivee = items[0].li.querySelector('.agenda__point').getBoundingClientRect();
    etat.signal.style.left = Math.round(depart.left + depart.width / 2 - cadre.left) + 'px';
    etat.signal.style.top = Math.round(depart.top + depart.height / 2 - cadre.top) + 'px';
    etat.signal.style.setProperty('--course', '0px');
    etat.signal.style.setProperty('--course-y', Math.round((arrivee.top + arrivee.height / 2) - (depart.top + depart.height / 2)) + 'px');
    etat.mise = null;
    majBords(racine);
    placerApercu(racine);
    return;
  }

  /* Les jours d'ici chaque rendez-vous (arrondis : un changement d'heure
     ne décale pas un point). */
  const jours = items.map((it) => Math.max(0, Math.round(((it.info.date || debut) - debut) / JOUR_MS)));
  const liste = troncons(jours);
  const large = mesurer(racine, items, false);
  const mesures = [large];
  /* La forme serrée n'est mesurée que si la large ne tient pas sur une
     rangée de chaque côté. */
  const direct = choisir(liste, largeur, mesures);
  if (!direct || direct.largeur > largeur || direct.places.some((p) => p.rangee > 0)) mesures.push(mesurer(racine, items, true));
  const mise = mesures.length > 1 ? choisir(liste, largeur, mesures) : direct;
  if (!mise) return;
  racine.classList.toggle('agenda--serre', mise.mesure.serre);
  const { xs, places, ancres, etendues, hautes } = mise;
  const { largeurs, hauteurs } = mise.mesure;

  /* Les rangées, de l'axe vers l'extérieur ; de chaque côté, au moins un
     peu d'air. */
  const decalages = { haut: [], bas: [] };
  ['haut', 'bas'].forEach((cote, c) => {
    let d = LIGNE.base;
    hautes[c].forEach((h, r) => { decalages[cote][r] = d; d += (h || 0) + LIGNE.ecartRangees; });
  });
  const axeY = Math.round(LIGNE.marge + Math.max(etendues[0], LIGNE.reserve));
  const hauteur = Math.round(axeY + Math.max(etendues[1], LIGNE.reserve) + LIGNE.marge);
  const toileL = Math.round(mise.largeur);
  toile.style.inlineSize = toileL + 'px';
  toile.style.blockSize = hauteur + 'px';
  scene.style.setProperty('--axe-y', axeY + 'px');
  scene.style.setProperty('--x0', LIGNE.origine + 'px');
  etat.signal.style.removeProperty('left');
  etat.signal.style.removeProperty('top');

  items.forEach((it, i) => {
    const p = places[i];
    const haut = p.cote === 'haut'
      ? axeY - decalages.haut[p.rangee] - hauteurs[i]
      : axeY + decalages.bas[p.rangee];
    const droite = ancres[i] === 'd';
    it.li.classList.toggle('agenda__rdv--haut', p.cote === 'haut');
    it.li.classList.toggle('agenda__rdv--bas', p.cote === 'bas');
    it.li.classList.toggle('agenda__rdv--droite', droite);
    delete it.li.dataset.mois;
    it.li.style.removeProperty('--ecart');
    /* La boîte épouse le texte : le contour du focus aussi. */
    it.li.style.inlineSize = largeurs[i] + 'px';
    it.li.style.left = (droite ? xs[i] - largeurs[i] : xs[i]) + 'px';
    it.li.style.top = Math.round(haut) + 'px';
    it.li.style.setProperty('--dy', Math.round(axeY - haut) + 'px');
    /* Le point se pose quand le trait l'atteint. */
    it.li.style.setProperty('--retard', Math.round(Math.min(1, xs[i] / Math.max(largeur, 1)) * 1100) + 'ms');
  });

  /* Les traits d'un pixel tombent sur un pixel entier : la ligne se cale
     sur la grille de l'écran. */
  const ratio = window.devicePixelRatio || 1;
  const gauche = etat.defilement.getBoundingClientRect().left * ratio;
  const reste = (gauche - Math.floor(gauche)) / ratio;
  if (reste > 0.01) toile.style.translate = (-reste).toFixed(3) + 'px 0';
  else toile.style.removeProperty('translate');

  const noeuds = prolonger(mise.noeuds, mise.k, toileL - 4);
  dessinerTrace(etat, { debut, noeuds, xs, places, axeY, toileL, hauteur });
  etat.mise = { xs, axeY, x0: LIGNE.origine, places, ancres };
  etat.signal.style.setProperty('--course', Math.max(0, (xs[0] || LIGNE.origine) - LIGNE.origine) + 'px');
  etat.signal.style.setProperty('--course-y', '0px');
  majBords(racine);
  if (etat.actif !== null) placerApercu(racine);
}

/* Le trait, les crans, les mois, les coupures : décoratifs, redessinés à
   chaque mise en page. Le nom d'un mois pend à côté du cran qui l'ouvre,
   sous la ligne (au-dessus si une tige passe) : il ne s'éloigne jamais de
   son mois, et le trait reste entier. En abrégé s'il manque de place, pas
   du tout s'il n'y en a pas. */
function dessinerTrace(etat, g) {
  const { debut, noeuds, xs, places, axeY, toileL, hauteur } = g;
  const finTrait = toileL - 4;
  const dernierJour = Math.floor(noeuds[noeuds.length - 1].j);
  const obstacles = [[LIGNE.origine - 14, LIGNE.origine + 14], ...xs.map((x) => [x - 14, x + 14])];
  const trous = [];
  const textes = [];
  const traits = [];

  /* Les coupures : deux traits obliques et, entre eux, le temps sauté. */
  for (let i = 1; i < noeuds.length; i += 1) {
    if (!noeuds[i].coupe) continue;
    const a = noeuds[i - 1];
    const b = noeuds[i];
    const saute = b.j - a.j;
    const s = el('span', { class: 'agenda__coupure' },
      '≈ ' + (saute < 63 ? Math.round(saute / 7) + ' semaines' : Math.round(saute / 30.44) + ' mois'));
    s.style.left = Math.round((a.x + b.x) / 2) + 'px';
    s.style.top = axeY + 'px';
    textes.push(s);
    trous.push([a.x + 4, b.x - 4]);
    obstacles.push([a.x, b.x]);
    for (const x of [a.x + 8, b.x - 8]) traits.push('M' + (x - 3).toFixed(1) + ' ' + (axeY + 6) + 'L' + (x + 3).toFixed(1) + ' ' + (axeY - 6));
  }

  /* Les mois : un cran à chaque premier du mois ; le nom, mesuré en long
     et en abrégé, pend du côté où aucune tige ne le traverse. L'année
     sur le premier nom et sur janvier. */
  const debuts = [];
  for (let d = new Date(debut.getFullYear(), debut.getMonth() + 1, 1); ; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
    const j = Math.round((d - debut) / JOUR_MS);
    if (j > dernierJour) break;
    const x = versX(noeuds, j);
    if (x !== null && x < finTrait - 8) debuts.push({ d, x: Math.round(x) });
  }
  const noms = debuts.map((m, i) => {
    const annee = i === 0 || m.d.getMonth() === 0 ? ' ' + m.d.getFullYear() : '';
    const iso = m.d.getFullYear() + '-' + deux(m.d.getMonth() + 1) + '-01';
    return [el('span', { class: 'agenda__mois', dataset: { debut: iso } }, MOIS_LONGS[m.d.getMonth()] + annee),
      el('span', { class: 'agenda__mois', dataset: { debut: iso } }, MOIS[m.d.getMonth()])];
  });
  monter(etat.mois, textes, noms.flat());
  const mesures = noms.map(([l, c]) => [l.offsetWidth, c.offsetWidth]);
  const hauteurNom = noms.length ? noms[0][0].offsetHeight : 0;
  /* Ce qui barre un nom, de chaque côté : les tiges de ce côté, les
     coupures, les noms déjà posés. */
  const barrages = { bas: obstacles.slice(xs.length + 1), haut: obstacles.slice(xs.length + 1) };
  xs.forEach((x, i) => barrages[places[i].cote].push([x - 5, x + 5]));
  const crans = [];
  debuts.forEach((m, i) => {
    const [long, court] = noms[i];
    let garde = null;
    for (const [s, l] of [[long, mesures[i][0]], [court, mesures[i][1]]]) {
      for (const cote of ['bas', 'haut']) {
        const a = m.x - 3;
        const b = m.x + 6 + l + 8;
        if (!garde && b < finTrait && !barrages[cote].some(([o1, o2]) => a < o2 && b > o1)) garde = { s, l, cote };
      }
    }
    for (const s of [long, court]) if (!garde || s !== garde.s) s.remove();
    const sousPoint = obstacles.slice(1, xs.length + 1).some(([o1, o2]) => m.x > o1 && m.x < o2);
    if (!garde) { if (!sousPoint) crans.push('M' + (m.x + 0.5) + ' ' + (axeY - 8) + 'V' + (axeY + 8)); return; }
    const bas = garde.cote === 'bas';
    garde.s.style.left = (m.x + 6) + 'px';
    garde.s.style.top = (bas ? axeY + 11 : axeY - 11 - hauteurNom) + 'px';
    garde.s.classList.add('agenda__mois--' + garde.cote);
    barrages[garde.cote].push([m.x - 3, m.x + 6 + garde.l + 8]);
    /* Le cran file jusqu'au nom, comme un fanion. */
    crans.push('M' + (m.x + 0.5) + ' ' + (axeY + (bas ? -6 : 6)) + 'V' + (bas ? axeY + 11 + hauteurNom : axeY - 11 - hauteurNom));
  });

  /* Le trait, en segments autour des coupures. Il s'amincit
     vers l'horizon et s'éteint après le dernier rendez-vous. */
  const epaisseur = (x) => LIGNE.traitPres - (LIGNE.traitPres - LIGNE.traitLoin) * Math.min(1, Math.max(0, (x - LIGNE.origine) / Math.max(1, finTrait - LIGNE.origine)));
  const segment = (x1, x2) => {
    const e1 = epaisseur(x1) / 2;
    const e2 = epaisseur(x2) / 2;
    return 'M' + x1.toFixed(1) + ' ' + (axeY - e1).toFixed(2) + 'L' + x2.toFixed(1) + ' ' + (axeY - e2).toFixed(2)
      + 'L' + x2.toFixed(1) + ' ' + (axeY + e2).toFixed(2) + 'L' + x1.toFixed(1) + ' ' + (axeY + e1).toFixed(2) + 'Z';
  };
  let chemin = '';
  let depart = LIGNE.origine;
  for (const [x1, x2] of trous.sort((p, q) => p[0] - q[0])) {
    if (x1 > depart) chemin += segment(depart, x1);
    depart = Math.max(depart, x2);
  }
  if (depart < finTrait) chemin += segment(depart, finTrait);

  /* Les crans : un par lundi, un plus fin par jour tant que les jours ont
     de la place. Jamais sous un point ni dans une coupure. */
  const libre = (x) => !obstacles.some(([x1, x2]) => x > x1 - 2 && x < x2 + 2);
  let semaines = '';
  let journees = '';
  for (let j = 1; j <= dernierJour; j += 1) {
    const d = new Date(debut.getFullYear(), debut.getMonth(), debut.getDate() + j);
    const x = versX(noeuds, j);
    if (x === null) continue;
    if (x >= finTrait) break;
    if (!libre(x) || d.getDate() === 1) continue;
    const veille = versX(noeuds, j - 1);
    const semaine = versX(noeuds, j - 7);
    const xr = Math.round(x) + 0.5;
    if (d.getDay() === 1 && (semaine === null || x - semaine >= 14)) semaines += 'M' + xr + ' ' + (axeY - 5.5) + 'V' + (axeY + 5.5);
    else if (d.getDay() !== 1 && veille !== null && x - veille >= 13) journees += 'M' + xr + ' ' + (axeY - 3.5) + 'V' + (axeY + 3.5);
  }
  const mensuels = crans.join('');

  const id = 'agenda-degrade-' + etat.id;
  const dernier = xs[xs.length - 1] || LIGNE.origine;
  const plein = Math.min(0.98, Math.max(0.3, (dernier + 24 - LIGNE.origine) / Math.max(1, finTrait - LIGNE.origine)));
  etat.trace.replaceChildren(svg('svg', {
    class: 'agenda__trace-dessin', width: toileL, height: hauteur, 'aria-hidden': 'true', focusable: 'false'
  },
  svg('defs', null,
    svg('linearGradient', { id, gradientUnits: 'userSpaceOnUse', x1: LIGNE.origine, y1: 0, x2: finTrait, y2: 0 },
      svg('stop', { offset: '0', class: 'agenda__degrade-plein' }),
      svg('stop', { offset: plein.toFixed(3), class: 'agenda__degrade-plein' }),
      svg('stop', { offset: '1', class: 'agenda__degrade-vide' }))),
  journees ? svg('path', { d: journees, class: 'agenda__cran agenda__cran--jour', stroke: 'url(#' + id + ')' }) : null,
  semaines ? svg('path', { d: semaines, class: 'agenda__cran agenda__cran--semaine', stroke: 'url(#' + id + ')' }) : null,
  mensuels ? svg('path', { d: mensuels, class: 'agenda__cran agenda__cran--mois', stroke: 'url(#' + id + ')' }) : null,
  traits.length ? svg('path', { d: traits.join(''), class: 'agenda__cran agenda__cran--coupure' }) : null,
  chemin ? svg('path', { d: chemin, class: 'agenda__axe', fill: 'url(#' + id + ')' }) : null));
}

/* -------------------------------------------------------------------------
   5. La ligne qui vit : survol, clavier, défilement, arrivée
   ------------------------------------------------------------------------- */

/* Allume le rendez-vous de rang i — son point, sa tige, son étiquette —
   tend la jauge d'aujourd'hui jusqu'à lui et montre son aperçu ; null
   éteint tout. */
function allumer(racine, i) {
  const etat = ETATS.get(racine);
  if (!etat) return;
  const rang = i !== null && Number.isFinite(i) && etat.items[i] ? i : null;
  if (rang === etat.actif) return;
  etat.actif = rang;
  racine.classList.toggle('agenda--allume', rang !== null);
  etat.items.forEach((it, k) => it.li.classList.toggle('est-allume', k === rang));
  if (rang === null) {
    etat.apercu.classList.remove('est-visible');
    etat.jauge.style.setProperty('--jauge', '0');
    return;
  }
  const it = etat.items[rang];
  etat.jauge.dataset.pole = it.info.pole;
  if (etat.mise) {
    const course = Math.max(0, etat.mise.xs[rang] - etat.mise.x0);
    etat.jauge.style.setProperty('--jauge', String(course / Math.max(1, etat.toile.offsetWidth - etat.mise.x0)));
  }
  etat.apercu.dataset.pole = it.info.pole;
  monter(etat.apercu, apercu(it.info));
  placerApercu(racine);
}

/* L'aperçu se pose à côté de l'étiquette, comme si elle se dépliait : à
   sa droite, sinon à sa gauche, toujours au-delà du contour du focus.
   Sans place d'un côté ni de l'autre, il passe de l'autre côté de la
   ligne, relié au point par un fil. Il peut déborder de la ligne vers le
   bas, jamais par-dessus le titre de la section. */
function placerApercu(racine) {
  const etat = ETATS.get(racine);
  if (!etat || etat.actif === null) return;
  if (!etat.mise) { etat.apercu.classList.remove('est-visible'); return; }
  const rang = etat.actif;
  const x = etat.mise.xs[rang] - etat.defilement.scrollLeft;
  const largeur = etat.scene.clientWidth;
  if (x < 0 || x > largeur) { etat.apercu.classList.remove('est-visible'); return; }
  const cadre = etat.scene.getBoundingClientRect();
  const boite = etat.items[rang].bouton.getBoundingClientRect();
  const g = boite.left - cadre.left;
  const d = boite.right - cadre.left;
  const haut = etat.mise.places[rang].cote === 'haut';
  const l = etat.apercu.offsetWidth;
  const h = etat.apercu.offsetHeight;
  const ecart = 16;
  let mode = 'droite';
  let gauche = d + ecart;
  if (gauche + l > largeur - 4) { mode = 'gauche'; gauche = g - ecart - l; }
  if (gauche < 4) { mode = haut ? 'dessous' : 'dessus'; gauche = Math.min(Math.max(x - 22, 0), Math.max(0, largeur - l)); }
  let top;
  if (mode === 'dessous') top = etat.mise.axeY + 22;
  else if (mode === 'dessus') {
    top = etat.mise.axeY - 22 - h;
    if (top < 0) { mode = 'dessous'; top = etat.mise.axeY + 22; }
  } else {
    /* Aligné sur l'étiquette : par le bas au-dessus de la ligne (s'il y
       a la place), par le haut au-dessous. */
    const t = boite.top - cadre.top;
    const b = boite.bottom - cadre.top;
    top = haut && b - h >= 0 ? b - h : Math.max(0, t);
  }
  for (const m of ['droite', 'gauche', 'dessous', 'dessus']) etat.apercu.classList.toggle('agenda__apercu--' + m, m === mode);
  etat.apercu.style.left = Math.round(gauche) + 'px';
  etat.apercu.style.top = Math.round(top) + 'px';
  etat.apercu.style.setProperty('--pointe', Math.round(x - gauche) + 'px');
  etat.apercu.classList.add('est-visible');
}

/* Les bords : une flèche et un fondu de chaque côté où il reste à voir. */
function majBords(racine) {
  const etat = ETATS.get(racine);
  if (!etat) return;
  const d = etat.defilement;
  const deborde = racine.classList.contains('agenda--ligne') && d.scrollWidth > d.clientWidth + 1;
  racine.classList.toggle('agenda--defile', deborde);
  racine.classList.toggle('peut-avant', deborde && d.scrollLeft > 2);
  racine.classList.toggle('peut-apres', deborde && d.scrollLeft < d.scrollWidth - d.clientWidth - 2);
}

/* Fait voir le rendez-vous i dans la ligne qui défile, sans faire
   bouger la page : son point et toute son étiquette. */
function montrer(etat, i) {
  if (!etat.mise) return;
  const d = etat.defilement;
  const li = etat.items[i].li;
  const debut = Math.min(etat.mise.xs[i], li.offsetLeft) - 48;
  const fin = Math.max(etat.mise.xs[i], li.offsetLeft + li.offsetWidth) + 48;
  const comment = etat.calme ? 'auto' : 'smooth';
  if (debut < d.scrollLeft) d.scrollTo({ left: Math.max(0, debut), behavior: comment });
  else if (fin > d.scrollLeft + d.clientWidth) d.scrollTo({ left: fin - d.clientWidth, behavior: comment });
}

function brancher(racine) {
  const etat = ETATS.get(racine);
  const rangDe = (cible) => {
    const n = cible && typeof cible.closest === 'function' ? cible.closest('.agenda__rdv') : null;
    return n && racine.contains(n) ? Number(n.dataset.i) : null;
  };

  /* Le survol : le point, sa tige et son étiquette forment un seul
     rendez-vous. Pendant un glissé, rien ne s'allume. */
  etat.toile.addEventListener('pointerover', (e) => {
    if (e.pointerType === 'touch' || racine.classList.contains('agenda--glisse')) return;
    allumer(racine, rangDe(e.target));
  });
  /* En quittant la ligne, on revient au rendez-vous qui a le focus, s'il
     y en a un ; sinon tout s'éteint. */
  etat.toile.addEventListener('pointerleave', () => {
    allumer(racine, etat.toile.contains(document.activeElement) ? rangDe(document.activeElement) : null);
  });
  racine.addEventListener('focusin', (e) => {
    const i = rangDe(e.target);
    if (i === null) return;
    etat.items.forEach((it, k) => { it.bouton.tabIndex = k === i ? 0 : -1; });
    montrer(etat, i);
    allumer(racine, i);
  });
  racine.addEventListener('focusout', (e) => {
    if (!e.relatedTarget || !racine.contains(e.relatedTarget)) allumer(racine, null);
  });

  /* Le point et la tige ouvrent le rendez-vous comme l'étiquette. */
  etat.items.forEach((it) => {
    const ouvrir = (e) => {
      if (Date.now() - etat.finGlisse < 80) { e.preventDefault(); return; }
      ouvrirFiche(it.info, it.bouton);
    };
    it.bouton.addEventListener('click', ouvrir);
    it.li.querySelector('.agenda__point').addEventListener('click', ouvrir);
    it.li.querySelector('.agenda__tige').addEventListener('click', ouvrir);
  });

  /* Le clavier : les flèches passent d'un point à l'autre, Début et Fin
     vont aux extrémités, Échap referme l'aperçu. */
  etat.liste.addEventListener('keydown', (e) => {
    const i = rangDe(e.target);
    if (i === null || !e.target.classList.contains('agenda__cible')) return;
    const dernier = etat.items.length - 1;
    const vers = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: dernier }[e.key];
    if (e.key === 'Escape') { allumer(racine, null); return; }
    if (vers === undefined) return;
    e.preventDefault();
    etat.items[Math.min(dernier, Math.max(0, vers))].bouton.focus({ preventScroll: true });
  });

  /* Le défilement : les bords suivent, l'aperçu aussi. */
  let demande = false;
  etat.defilement.addEventListener('scroll', () => {
    if (demande) return;
    demande = true;
    requestAnimationFrame(() => { demande = false; majBords(racine); placerApercu(racine); });
  }, { passive: true });
  for (const [classe, sens] of [['avant', -1], ['apres', 1]]) {
    racine.querySelector('.agenda__fleche--' + classe).addEventListener('click', () => {
      etat.defilement.scrollBy({ left: sens * etat.defilement.clientWidth * 0.7, behavior: etat.calme ? 'auto' : 'smooth' });
    });
  }

  /* Glisser à la souris quand la ligne déborde (le doigt, lui, fait
     défiler nativement). Un glissé n'est pas un clic. */
  let prise = null;
  etat.defilement.addEventListener('pointerdown', (e) => {
    if (e.pointerType !== 'mouse' || e.button !== 0 || !racine.classList.contains('agenda--defile')) return;
    if (e.target.closest && e.target.closest('.barre-edition')) return;
    prise = { x: e.clientX, gauche: etat.defilement.scrollLeft, glisse: false, id: e.pointerId };
  });
  etat.defilement.addEventListener('pointermove', (e) => {
    if (!prise || e.pointerId !== prise.id) return;
    const dx = e.clientX - prise.x;
    if (!prise.glisse && Math.abs(dx) < 5) return;
    if (!prise.glisse) {
      prise.glisse = true;
      racine.classList.add('agenda--glisse');
      allumer(racine, null);
      try { etat.defilement.setPointerCapture(e.pointerId); } catch (_e) { /* ignoré */ }
    }
    etat.defilement.scrollLeft = prise.gauche - dx;
  });
  const lacher = () => {
    if (!prise) return;
    if (prise.glisse) etat.finGlisse = Date.now();
    prise = null;
    racine.classList.remove('agenda--glisse');
  };
  etat.defilement.addEventListener('pointerup', lacher);
  etat.defilement.addEventListener('pointercancel', lacher);

  /* La légende allume, au survol, tous les rendez-vous d'un type ou d'un
     pôle. */
  const legende = racine.querySelector('.agenda__legende');
  if (legende) {
    legende.addEventListener('pointerover', (e) => {
      const item = e.target.closest && e.target.closest('.agenda__legende-item');
      racine.classList.toggle('agenda--filtre', !!item);
      etat.items.forEach((it) => it.li.classList.toggle('est-choisi', !!item
        && (item.dataset.type ? it.info.cleType === item.dataset.type : it.info.pole === item.dataset.pole)));
    });
    legende.addEventListener('pointerleave', () => {
      racine.classList.remove('agenda--filtre');
      etat.items.forEach((it) => it.li.classList.remove('est-choisi'));
    });
  }
}

/* La ligne se trace la première fois qu'elle entre à l'écran, et ses
   battements ne tournent que tant qu'elle y est. Il suffit qu'elle
   paraisse au bas de l'écran — quelle que soit sa hauteur, même agrandie
   quatre fois. Par sécurité, elle se montre aussi dès qu'on y entre au
   clavier, et avant une impression. Sans observateur, ou si le système
   demande moins d'animations, tout est là d'emblée et rien ne bat. */
function brancherArrivee(racine) {
  const etat = ETATS.get(racine);
  if (etat.calme || typeof IntersectionObserver !== 'function') return;
  racine.classList.add('agenda--anime');
  const montrerTout = () => {
    if (!racine.classList.contains('agenda--vu')) requestAnimationFrame(() => racine.classList.add('agenda--vu'));
  };
  const obs = new IntersectionObserver((vus) => {
    for (const v of vus) {
      if (v.isIntersecting) montrerTout();
      racine.classList.toggle('agenda--en-vue', v.isIntersecting);
    }
  }, { threshold: 0, rootMargin: '0px 0px -12% 0px' });
  obs.observe(racine);
  racine.addEventListener('focusin', montrerTout);
  if (typeof window !== 'undefined') window.addEventListener('beforeprint', () => racine.classList.add('agenda--vu'));
}

/* -------------------------------------------------------------------------
   6. Le bloc
   ------------------------------------------------------------------------- */

function legende(infos) {
  const types = [];
  const poles = [];
  for (const i of infos) {
    if (!types.some((t) => t.cleType === i.cleType)) types.push(i);
    if (!poles.includes(i.pole)) poles.push(i.pole);
  }
  const ordre = ['ETII', 'ETIIA', 'ETIIE', 'ETIII'];
  poles.sort((a, b) => ordre.indexOf(a) - ordre.indexOf(b));
  return el('div', { class: 'agenda__legende', 'aria-hidden': 'true' },
    el('span', { class: 'agenda__legende-groupe' },
      types.map((t) => el('span', { class: 'agenda__legende-item', dataset: { type: t.cleType } },
        glyphe(t.cleType, 'agenda__legende-glyphe'), t.type))),
    el('span', { class: 'agenda__legende-groupe' },
      poles.map((p) => el('span', { class: 'agenda__legende-item', dataset: { pole: p } },
        el('span', { class: 'agenda__legende-pastille' }), libellePole(p)))));
}

function aujourdhuiRepere(debut) {
  return el('div', { class: 'agenda__aujourdhui', 'aria-hidden': 'true' },
    el('span', { class: 'agenda__aujourdhui-point' }),
    el('span', { class: 'agenda__aujourdhui-libelle' },
      el('span', { class: 'agenda__aujourdhui-mot' }, 'Aujourd’hui'),
      el('span', { class: 'agenda__aujourdhui-date' }, dateCourte(debut))));
}

/**
 * Les prochains rendez-vous, sur leur ligne.
 * @param {object} donnees  communications.json (modifié)
 * @param {object} [options]
 * @returns {HTMLElement}
 */
export function agenda(donnees, options) {
  const o = options || {};
  const pole = texte(o.pole).toUpperCase() || 'ETII';
  const limite = Number(o.limite) > 0 ? Number(o.limite) : 8;
  const entrees = (Array.isArray(donnees && donnees.agenda) ? donnees.agenda : [])
    .filter((e) => e && typeof e === 'object' && texte(e.titre) && texte(e.type) !== 'mot')
    .filter((e) => { const n = joursRestants(e.date); return n !== null && n >= 0; })
    .filter((e) => pole === 'ETII' || texte(e.pole).toUpperCase() === pole || texte(e.pole).toUpperCase() === 'ETII')
    .sort((a, b) => texte(a.date).localeCompare(texte(b.date)));
  const visibles = entrees.slice(0, limite);
  const debut = aujourdhui();
  compteur += 1;
  const id = String(compteur);
  const ajout = typeof o.surAjouter === 'function' ? boutonAjouter('Ajouter un rendez-vous', o.surAjouter) : null;
  const suite = entrees.length > visibles.length
    ? el('p', { class: 'agenda__suite' }, 'Et ' + (entrees.length - visibles.length) + ' autre' + (entrees.length - visibles.length > 1 ? 's' : '') + ' plus tard.')
    : null;

  /* Rien à venir : la ligne reste, aujourd'hui à son origine, et le dit
     sur le trait. */
  if (!visibles.length) {
    return el('div', { class: 'agenda agenda--vide' },
      el('div', { class: 'agenda__vide' },
        aujourdhuiRepere(debut),
        el('p', { class: 'agenda__vide-texte' }, 'Rien d’inscrit pour les semaines à venir.')),
      ajout);
  }

  const infos = visibles.map(lire);
  const items = infos.map((info) => {
    const li = rendezVous(info, o, 'agenda-' + id);
    return { info, li, bouton: li.querySelector('.agenda__cible') };
  });
  const liste = el('ol', { class: 'agenda__liste', role: 'list', 'aria-label': 'Prochains rendez-vous, du plus proche au plus lointain' },
    items.map((it) => it.li));
  const couche = el('div', { class: 'agenda__trace', 'aria-hidden': 'true' });
  const mois = el('div', { class: 'agenda__mois-couche', 'aria-hidden': 'true' });
  const jauge = el('span', { class: 'agenda__jauge', 'aria-hidden': 'true' });
  const signal = el('span', { class: 'agenda__signal', 'aria-hidden': 'true', dataset: { pole: infos[0].pole } });
  const toile = el('div', { class: 'agenda__toile' }, couche, jauge, mois, aujourdhuiRepere(debut), signal, liste);
  const defilement = el('div', { class: 'agenda__defilement' }, toile);
  const fleche = (sens) => el('button', {
    type: 'button', class: ['agenda__fleche', 'agenda__fleche--' + sens], tabindex: -1, 'aria-hidden': 'true'
  }, svg('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false' },
    svg('path', { d: sens === 'avant' ? 'M10 3 L5 8 L10 13' : 'M6 3 L11 8 L6 13' })));
  const apercuNoeud = el('div', { class: 'agenda__apercu', 'aria-hidden': 'true' });
  const scene = el('div', { class: 'agenda__scene' }, defilement, fleche('avant'), fleche('apres'), apercuNoeud);

  const racine = el('div', { class: 'agenda agenda--attente' }, scene, legende(infos), suite, ajout);

  let calme = false;
  try { calme = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_e) { calme = false; }
  ETATS.set(racine, {
    id, scene, defilement, toile, trace: couche, mois, liste, jauge, signal, apercu: apercuNoeud, items,
    actif: null, mise: null, finGlisse: 0, calme
  });

  /* La mise en page suit la largeur du bloc et la taille des étiquettes
     (une police qui arrive, le mode édition qui ajoute ses boutons). Une
     seule mesure par image. Sans observateur, la fenêtre suffit. */
  let demande = false;
  const planifier = () => {
    if (demande) return;
    demande = true;
    requestAnimationFrame(() => { demande = false; disposer(racine); });
  };
  if (typeof ResizeObserver === 'function') {
    let largeurVue = -1;
    const observateur = new ResizeObserver((vus) => {
      for (const v of vus) {
        /* La scène : seule sa largeur compte. Une étiquette : sa taille. */
        if (v.target === scene) {
          const l = Math.round(v.contentRect.width);
          if (l === largeurVue) continue;
          largeurVue = l;
        }
        planifier();
        return;
      }
    });
    observateur.observe(scene);
    items.forEach((it) => observateur.observe(it.bouton));
    items.forEach((it) => { const b = it.li.querySelector('.barre-edition'); if (b) observateur.observe(b); });
  } else if (typeof window !== 'undefined') {
    window.addEventListener('resize', planifier);
  }
  /* Filet de sécurité : jamais une ligne invisible faute de mesure. */
  let essais = 0;
  const attendre = () => {
    if (racine.isConnected) { disposer(racine); return; }
    essais += 1;
    if (essais < 120) requestAnimationFrame(attendre);
  };
  requestAnimationFrame(attendre);
  setTimeout(() => racine.classList.remove('agenda--attente'), 1500);

  brancher(racine);
  brancherArrivee(racine);
  return racine;
}

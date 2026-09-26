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

   La ligne porte le temps, en perspective : les jours proches ont de la
   place, les mois lointains se resserrent, et le trait s'amincit vers
   l'horizon. Les mois s'écrivent sur le trait même, un cran marque chaque
   semaine, un cran plus fin chaque jour tant que la place le permet. Les
   étiquettes alternent au-dessus et au-dessous ; quand des dates se
   serrent, elles montent d'une rangée, en escalier, sans jamais se
   chevaucher ni se faire couper par une tige. Quand la place manque,
   la ligne s'allonge et défile : à la molette, au doigt, en glissant à la
   souris, par les flèches posées sur ses bords, qui s'estompent.

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

/* La ligne, en pixels. `origine` laisse à gauche la place de
   « Aujourd'hui ». Le temps y est en perspective : un logarithme, presque
   droit sur les `fuite` premiers jours, de plus en plus serré ensuite. La
   ligne montre au moins `horizonMin` jours et ne descend pas sous
   `longueurMin` : en deçà, elle défile. Les étiquettes montent d'au plus
   `rangeesMax` rangées de chaque côté ; au-delà, la ligne s'allonge. Sous
   `largeurMin`, elle se dresse en colonne. */
const LIGNE = {
  origine: 150,
  fin: 36,
  longueurMin: 280,
  fuite: 12,
  horizonMin: 14,
  ecartPoints: 28,
  ecartEtiquettes: 22,
  base: 30,
  ecartRangees: 14,
  traitPres: 2.6,
  traitLoin: 0.6,
  rangeesMax: 3,
  marge: 18,
  etendueMin: 124,
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

/* Les rangées d'étiquettes, de droite à gauche. Une étiquette part de sa
   tige et s'étend à droite : elle monte au-dessus de toute étiquette plus
   tardive qu'elle recouvrirait, sur son côté. L'escalier descend donc vers
   la droite, et aucune tige ne traverse jamais une étiquette. On préfère
   le côté qui alterne, puis la rangée la plus basse. */
function ranger(xs, largeurs) {
  const places = [];
  for (let i = xs.length - 1; i >= 0; i -= 1) {
    const prefere = i % 2 === 0 ? 'haut' : 'bas';
    let choix = null;
    for (const cote of [prefere, prefere === 'haut' ? 'bas' : 'haut']) {
      let rangee = 0;
      for (let j = i + 1; j < xs.length; j += 1) {
        if (places[j].cote === cote && xs[j] < xs[i] + largeurs[i] + LIGNE.ecartEtiquettes) {
          rangee = Math.max(rangee, places[j].rangee + 1);
        }
      }
      if (!choix || rangee < choix.rangee) choix = { cote, rangee };
    }
    places[i] = choix;
  }
  return places;
}

/* La largeur qu'occupe vraiment une étiquette : jusqu'au bout de son
   texte le plus long (un titre équilibré sur deux lignes laisse de l'air à
   droite de sa boîte), ou de sa barre d'édition. */
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

/* Le nom d'un mois s'écrit sur la ligne, dans le premier creux assez
   large entre deux points ; sinon en abrégé ; sinon pas du tout (les
   étiquettes disent déjà le mois). */
function creux(debut, fin, obstacles, largeur) {
  let curseur = debut;
  const tries = obstacles.filter(([a, b]) => b > debut && a < fin).sort((p, q) => p[0] - q[0]);
  for (const [a, b] of tries) {
    if (a - curseur >= largeur) return curseur;
    curseur = Math.max(curseur, b);
  }
  return fin - curseur >= largeur ? curseur : null;
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
    toile.style.removeProperty('inline-size');
    toile.style.removeProperty('block-size');
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
      it.li.classList.remove('agenda__rdv--haut', 'agenda__rdv--bas');
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

  /* Les étiquettes prennent leur forme de ligne avant d'être mesurées. */
  const largeurs = items.map((it) => largeurUtile(it.li));
  const hauteurs = items.map((it) => it.li.offsetHeight);
  const jours = items.map((it) => Math.max(0, ((it.info.date || debut) - debut) / JOUR_MS));
  const dernier = items.length - 1;
  /* Le temps en perspective : le proche en grand, le lointain qui se
     resserre, comme une route qui fuit vers l'horizon. La longueur est
     la plus grande qui fasse tenir la dernière étiquette. */
  const horizon = Math.max(jours[dernier] || 0, LIGNE.horizonMin);
  const fuite = (j) => Math.log1p(j / LIGNE.fuite) / Math.log1p(horizon / LIGNE.fuite);
  let longueur = Math.max(LIGNE.longueurMin, largeur - LIGNE.origine - (largeurs[dernier] || 0) - LIGNE.fin);

  /* L'échelle, puis les rangées ; trop de rangées : la ligne s'allonge et
     on recommence. */
  let xs = [];
  let places = [];
  for (let essai = 0; essai < 14; essai += 1) {
    xs = [];
    jours.forEach((j, i) => {
      const x = LIGNE.origine + fuite(j) * longueur;
      xs.push(Math.round(Math.max(x, i ? xs[i - 1] + LIGNE.ecartPoints : LIGNE.origine + LIGNE.ecartPoints)));
    });
    places = ranger(xs, largeurs);
    if (places.every((p) => p.rangee < LIGNE.rangeesMax)) break;
    longueur *= 1.25;
  }
  const versX = (d) => LIGNE.origine + fuite(Math.max(0, (d - debut) / JOUR_MS)) * longueur;

  /* La hauteur de chaque rangée : la plus haute de ses étiquettes. */
  const rangees = { haut: [], bas: [] };
  places.forEach((p, i) => {
    rangees[p.cote][p.rangee] = Math.max(rangees[p.cote][p.rangee] || 0, hauteurs[i]);
  });
  const decalages = { haut: [], bas: [] };
  for (const cote of ['haut', 'bas']) {
    let d = LIGNE.base;
    for (let k = 0; k < rangees[cote].length; k += 1) {
      decalages[cote][k] = d;
      d += (rangees[cote][k] || 0) + LIGNE.ecartRangees;
    }
  }
  const etendue = (cote) => (rangees[cote].length ? decalages[cote][rangees[cote].length - 1] + rangees[cote][rangees[cote].length - 1] : 24);
  /* De chaque côté, au moins la place de l'aperçu d'un rendez-vous. */
  const axeY = Math.round(LIGNE.marge + Math.max(etendue('haut'), LIGNE.etendueMin));
  const hauteur = Math.round(axeY + Math.max(etendue('bas'), LIGNE.etendueMin) + LIGNE.marge);
  const toileL = Math.max(largeur, Math.max(0, ...xs.map((x, i) => x + largeurs[i])) + LIGNE.fin);
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
    it.li.classList.toggle('agenda__rdv--haut', p.cote === 'haut');
    it.li.classList.toggle('agenda__rdv--bas', p.cote === 'bas');
    delete it.li.dataset.mois;
    it.li.style.removeProperty('--ecart');
    it.li.style.left = xs[i] + 'px';
    it.li.style.top = Math.round(haut) + 'px';
    it.li.style.setProperty('--dy', Math.round(axeY - haut) + 'px');
    /* Le point se pose quand le trait l'atteint. */
    it.li.style.setProperty('--retard', Math.round(Math.min(1, xs[i] / Math.max(largeur, 1)) * 1100) + 'ms');
  });

  dessinerTrace(etat, { debut, versX, xs, axeY, toileL, hauteur });
  etat.mise = { xs, axeY, x0: LIGNE.origine, places };
  etat.signal.style.setProperty('--course', Math.max(0, (xs[0] || LIGNE.origine) - LIGNE.origine) + 'px');
  etat.signal.style.setProperty('--course-y', '0px');
  majBords(racine);
  if (etat.actif !== null) placerApercu(racine);
}

/* Le trait, les crans et les mois : décoratifs, redessinés à chaque mise
   en page. Le trait s'interrompt là où un mois s'écrit. */
function dessinerTrace(etat, g) {
  const { debut, versX, xs, axeY, toileL, hauteur } = g;
  const finTrait = toileL - 4;
  const obstacles = [[LIGNE.origine - 12, LIGNE.origine + 14], ...xs.map((x) => [x - 13, x + 13])];

  /* Les mois : le nom mesuré une fois posé, puis glissé dans son creux. */
  const noms = [];
  const crans = [];
  const trous = [];
  for (let d = new Date(debut.getFullYear(), debut.getMonth(), 1); versX(d) < finTrait; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
    const suivant = new Date(d.getFullYear(), d.getMonth() + 1, 1);
    const a = Math.max(versX(d), LIGNE.origine);
    const b = Math.min(versX(suivant), finTrait);
    if (d > debut) crans.push(Math.round(a));
    const long = MOIS_LONGS[d.getMonth()] + (d.getMonth() === 0 || noms.length === 0 ? ' ' + d.getFullYear() : '');
    noms.push({ long, court: MOIS[d.getMonth()], a: a + (d > debut ? 8 : 16), b: b - 8 });
  }
  const spans = noms.map((n) => el('span', { class: 'agenda__mois' }, n.long));
  monter(etat.mois, spans);
  noms.forEach((n, i) => {
    const s = spans[i];
    let largeur = s.offsetWidth;
    let x = creux(n.a, n.b, obstacles, largeur + 10);
    if (x === null) {
      s.textContent = n.court;
      largeur = s.offsetWidth;
      x = creux(n.a, n.b, obstacles, largeur + 10);
    }
    if (x === null) { s.remove(); return; }
    s.style.left = Math.round(x + 5) + 'px';
    s.style.top = axeY + 'px';
    trous.push([x, x + largeur + 10]);
    obstacles.push([x, x + largeur + 10]);
  });

  /* Le trait, en segments autour des noms de mois. Il s'amincit vers
     l'horizon — la perspective encore : épais d'aujourd'hui, un fil au
     loin. */
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
     de la place — ils se resserrent, puis s'effacent, vers l'horizon.
     Jamais sous un nom de mois ni sous un point. */
  const libre = (x) => !obstacles.some(([x1, x2]) => x > x1 - 2 && x < x2 + 2);
  let semaines = '';
  let journees = '';
  for (let j = 1; j < 800; j += 1) {
    const d = new Date(debut.getFullYear(), debut.getMonth(), debut.getDate() + j);
    const x = versX(d);
    if (x >= finTrait) break;
    const veille = versX(new Date(d.getFullYear(), d.getMonth(), d.getDate() - 1));
    const semaine = versX(new Date(d.getFullYear(), d.getMonth(), d.getDate() - 7));
    if (!libre(x) || d.getDate() === 1) continue;
    const xr = Math.round(x) + 0.5;
    if (d.getDay() === 1 && x - semaine >= 14) semaines += 'M' + xr + ' ' + (axeY - 5.5) + 'V' + (axeY + 5.5);
    else if (d.getDay() !== 1 && x - veille >= 13) journees += 'M' + xr + ' ' + (axeY - 3.5) + 'V' + (axeY + 3.5);
  }
  const mensuels = crans.filter(libre).map((x) => 'M' + (x + 0.5) + ' ' + (axeY - 10) + 'V' + (axeY + 10)).join('');

  const id = 'agenda-degrade-' + etat.id;
  const plein = Math.min(0.97, Math.max(0.55, ((xs[xs.length - 1] || LIGNE.origine) - LIGNE.origine) / Math.max(1, finTrait - LIGNE.origine) + 0.1));
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

/* L'aperçu se pose de l'autre côté de la ligne, sous le point si
   l'étiquette est au-dessus, et reste dans la largeur du bloc. */
function placerApercu(racine) {
  const etat = ETATS.get(racine);
  if (!etat || etat.actif === null) return;
  if (!etat.mise) { etat.apercu.classList.remove('est-visible'); return; }
  const rang = etat.actif;
  const x = etat.mise.xs[rang] - etat.defilement.scrollLeft;
  const largeur = etat.scene.clientWidth;
  if (x < 0 || x > largeur) { etat.apercu.classList.remove('est-visible'); return; }
  const li = etat.items[rang].li;
  const haut = etat.mise.places[rang].cote === 'haut';
  const l = etat.apercu.offsetWidth;
  /* À côté de l'étiquette, comme si elle se dépliait : à sa droite, ou à
     gauche de sa tige. Sans place d'un côté ni de l'autre, de l'autre
     côté de la ligne, relié au point par un fil. */
  let mode = 'droite';
  let gauche = x + largeurUtile(li) + 16;
  if (gauche + l > largeur - 4) { mode = 'gauche'; gauche = x - 16 - l; }
  if (gauche < 4) { mode = haut ? 'dessous' : 'dessus'; gauche = Math.min(Math.max(x - 22, 0), Math.max(0, largeur - l)); }
  for (const m of ['droite', 'gauche', 'dessous', 'dessus']) etat.apercu.classList.toggle('agenda__apercu--' + m, m === mode);
  const h = etat.apercu.offsetHeight;
  const hToile = etat.toile.offsetHeight;
  let top;
  if (mode === 'dessous') top = etat.mise.axeY + 22;
  else if (mode === 'dessus') top = etat.mise.axeY - 22 - h;
  else {
    /* Aligné sur l'étiquette, sans passer au-dessus de la ligne : ce qui
       dépasse descend plutôt que de couvrir le titre de la section. */
    top = haut ? li.offsetTop + li.offsetHeight - h : li.offsetTop;
    top = Math.max(0, Math.min(top, hToile - h));
  }
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
   bouger la page. */
function montrer(etat, i) {
  if (!etat.mise) return;
  const d = etat.defilement;
  const x = etat.mise.xs[i];
  const l = etat.items[i].li.offsetWidth;
  if (x - 40 < d.scrollLeft) d.scrollTo({ left: Math.max(0, x - 60), behavior: etat.calme ? 'auto' : 'smooth' });
  else if (x + l + 40 > d.scrollLeft + d.clientWidth) d.scrollTo({ left: x + l + 60 - d.clientWidth, behavior: etat.calme ? 'auto' : 'smooth' });
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
   battements ne tournent que tant qu'elle y est. Sans observateur, ou si
   le système demande moins d'animations, tout est là d'emblée et rien ne
   bat. */
function brancherArrivee(racine) {
  const etat = ETATS.get(racine);
  if (etat.calme || typeof IntersectionObserver !== 'function') return;
  racine.classList.add('agenda--anime');
  const obs = new IntersectionObserver((vus) => {
    for (const v of vus) {
      if (v.isIntersecting && !racine.classList.contains('agenda--vu')) {
        requestAnimationFrame(() => racine.classList.add('agenda--vu'));
      }
      racine.classList.toggle('agenda--en-vue', v.isIntersecting);
    }
  }, { threshold: 0.2 });
  obs.observe(racine);
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

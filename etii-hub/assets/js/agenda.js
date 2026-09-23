/* =========================================================================
   ETII Hub — « À venir » : la frise des prochains rendez-vous

   Le Communication center raconte ce qui s'est passé ; ce bloc montre ce
   qui arrive, sur une frise : un axe du temps qui part d'aujourd'hui,
   découpé en mois (une bande par mois, son nom au milieu), et chaque
   rendez-vous posé
   à sa date — un losange pour un jalon, un rond pour le reste, à la
   couleur du pôle concerné (terre cuite pour tout le service). Sa carte,
   au-dessus ou au-dessous de l'axe en alternance, dit quoi, quand, pour
   qui, où, et en deux lignes ce qui s'y joue. On voit d'un coup d'œil ce
   qui est proche, ce qui se tasse, ce qui est encore loin.

   Une seule liste dans le document, dans l'ordre des dates : c'est elle
   que lisent les lecteurs d'écran. Sur un écran large, disposer() la pose
   sur la frise : deux rangées de cartes, une au-dessus de l'axe et une
   au-dessous, les rendez-vous alternant de l'une à l'autre. L'axe va
   d'aujourd'hui au dernier rendez-vous (pas plus loin) ; les cartes, elles,
   se répartissent sur toute la largeur, dans l'ordre des dates, et un
   trait relie chacune à son repère. La frise garde ainsi toujours la même
   hauteur, même quand les dates se serrent. Sur un écran étroit, c'est une
   simple liste de cartes. L'axe et les traits sont décoratifs.

   La frise vit : elle se dessine quand on arrive dessus (l'axe se trace,
   les repères se posent, les cartes montent), le point d'aujourd'hui bat
   doucement, et survoler une carte — ou son repère — l'allume avec son
   trait, son repère et la jauge qui mesure le temps d'ici là ; les autres
   s'estompent. Rien ne bouge si le système demande moins d'animations.

   En mode édition (edition.js), chaque carte se modifie ou se retire, et
   un bouton en ajoute une. Un rendez-vous passé quitte la frise de
   lui-même, le lendemain.

   API :
     agenda(donnees, options)  -> HTMLElement
       options.pole            'ETII' (tout le service) ou un code de pôle
       options.limite          nombre de rendez-vous au plus (défaut 8)
       options.surAjouter(b), options.surModifier(entree, b), options.surSupprimer(entree)
   ========================================================================= */

import { el, svg } from './ui.js';
import { joursRestants, TYPES_AGENDA } from './kiosque.js';
import { barreEdition, boutonAjouter } from './edition.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const MOIS_LONGS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
const JOURS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const JOURS_COURTS = ['dim.', 'lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.'];
const JOUR_MS = 86400000;

/* La frise, en pixels : largeur d'une carte, écart entre deux couloirs,
   hauteur de la bande de l'axe, marges. En dessous de LARGEUR_MIN, la
   liste simple lit mieux qu'une frise écrasée. */
const FRISE = { carte: 288, ecart: 14, axe: 64, marge: 28, largeurMin: 880, horizonMin: 14 };

/* Les positions de la dernière mise en page, pour la jauge du survol. */
const MISES = new WeakMap();

function dateDe(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(texte(iso));
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}

/* « aujourd'hui », « demain », « dans 5 jours », « dans 3 semaines ». */
function echeance(n) {
  if (n === null) return '';
  if (n <= 0) return 'aujourd’hui';
  if (n === 1) return 'demain';
  if (n < 14) return 'dans ' + n + ' jours';
  if (n < 60) return 'dans ' + Math.round(n / 7) + ' semaines';
  return 'dans ' + Math.round(n / 30) + ' mois';
}

function aujourdhui() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/* -------------------------------------------------------------------------
   1. Une carte
   ------------------------------------------------------------------------- */

function carte(entree, options, rang) {
  const date = dateDe(entree.date);
  const n = joursRestants(entree.date);
  const pole = texte(entree.pole).toUpperCase() || 'ETII';
  const cleType = texte(entree.type);
  const type = TYPES_AGENDA[cleType] || cleType || 'Rendez-vous';
  const li = el('li', {
    class: ['agenda__rdv', n !== null && n <= 7 ? 'agenda__rdv--proche' : null],
    dataset: { pole, type: cleType === 'jalon' ? 'jalon' : 'rdv', date: texte(entree.date), i: String(rang) },
    style: { '--i': String(rang) }
  },
  el('div', { class: 'agenda__date', 'aria-hidden': 'true' },
    el('span', { class: 'agenda__jour-semaine' }, date ? JOURS_COURTS[date.getDay()] : ''),
    el('span', { class: 'agenda__jour' }, date ? String(date.getDate()) : '—'),
    el('span', { class: 'agenda__mois' }, date ? MOIS[date.getMonth()] : '')),
  el('div', { class: 'agenda__corps' },
    el('p', { class: 'agenda__meta' },
      el('span', { class: 'agenda__type' }, type),
      el('span', { class: 'agenda__pole', dataset: { pole } }, pole === 'ETII' ? 'Service' : pole),
      el('span', { class: 'agenda__echeance' }, echeance(n))),
    el('h3', { class: 'agenda__titre' },
      /* La date complète pour les lecteurs d'écran : le jour en grand est
         décoratif. */
      el('span', { class: 'visuellement-cache' }, date ? JOURS[date.getDay()] + ' ' + date.getDate() + ' ' + MOIS_LONGS[date.getMonth()] + ' : ' : ''),
      texte(entree.titre)),
    texte(entree.resume) ? el('p', { class: 'agenda__resume' }, texte(entree.resume)) : null,
    texte(entree.lieu) ? el('p', { class: 'agenda__lieu' }, el('span', { 'aria-hidden': 'true' }, '⌖ '), texte(entree.lieu)) : null),
  (typeof options.surModifier === 'function' || typeof options.surSupprimer === 'function')
    ? barreEdition({
        classe: 'agenda__edition barre-edition--compacte',
        quoi: texte(entree.titre),
        surModifier: typeof options.surModifier === 'function' ? (b) => options.surModifier(entree, b) : null,
        surSupprimer: typeof options.surSupprimer === 'function' ? () => options.surSupprimer(entree) : null
      })
    : null);
  return li;
}

/* -------------------------------------------------------------------------
   2. La frise : où va chaque carte
   ------------------------------------------------------------------------- */

/* L'axe : aujourd'hui, une bande par mois avec son nom, et le repère de
   chaque rendez-vous. Recalculé à chaque mise en page : les positions
   dépendent de la largeur. */
function dessinerAxe(axe, debut, fin, versX, reperes) {
  const marques = [];
  /* Les mois : de la date de départ (ou du 1er) à la fin du mois (ou de
     la frise). Une bande sur deux est teintée ; le nom se pose au milieu,
     en abrégé si la bande est étroite. */
  let rang = 0;
  for (let d = new Date(debut.getFullYear(), debut.getMonth(), 1); d <= fin; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
    const de = d < debut ? debut : d;
    const suivant = new Date(d.getFullYear(), d.getMonth() + 1, 1);
    const a = suivant > fin ? fin : suivant;
    const x1 = versX(de);
    const x2 = versX(a);
    const largeur = x2 - x1;
    if (largeur > 4) {
      const libelle = largeur >= 110 ? MOIS_LONGS[d.getMonth()] + (d.getMonth() === 0 ? ' ' + d.getFullYear() : '') : MOIS[d.getMonth()];
      marques.push(el('span', {
        class: ['agenda__mois-bande', rang % 2 ? 'agenda__mois-bande--teinte' : null, d >= debut ? 'agenda__mois-bande--debut' : null],
        style: { left: x1 + 'px', width: largeur + 'px' }
      }, largeur >= 44 ? el('span', { class: 'agenda__mois-libelle' }, libelle) : null));
    }
    rang += 1;
  }
  /* La jauge : d'aujourd'hui au rendez-vous survolé, à sa couleur. Vide
     au repos. */
  marques.push(el('span', { class: 'agenda__progression', style: { left: versX(debut) + 'px' } }));
  marques.push(el('span', { class: 'agenda__aujourdhui', style: { left: versX(debut) + 'px' } },
    el('span', { class: 'agenda__aujourdhui-libelle' }, 'Aujourd’hui')));
  /* Les repères : un losange pour un jalon, un rond sinon. */
  reperes.forEach((r, i) => {
    marques.push(el('span', {
      class: 'agenda__repere',
      dataset: { pole: r.pole, type: r.type, i: String(i) },
      style: { left: r.x + 'px', '--i': String(i) }
    }));
  });
  axe.replaceChildren(el('span', { class: 'agenda__ligne' }), ...marques);
}

/* Une rangée de cartes, dans l'ordre des dates : chacune se pose sous sa
   date, se décale à droite si la précédente la gêne, puis toute la rangée
   recule si la dernière déborde. */
function rangee(desirs, largeur, carte, ecart) {
  const gauches = [];
  desirs.forEach((x, i) => {
    let g = Math.max(x - carte / 2, 0);
    if (i > 0) g = Math.max(g, gauches[i - 1] + carte + ecart);
    gauches.push(g);
  });
  for (let i = gauches.length - 1; i >= 0; i -= 1) {
    const plafond = i === gauches.length - 1 ? largeur - carte : gauches[i + 1] - carte - ecart;
    gauches[i] = Math.max(Math.min(gauches[i], plafond), 0);
  }
  return gauches;
}

/**
 * Pose les cartes sur la frise, ou les rend à la liste simple quand la
 * place manque. Idempotent : appelé à chaque changement de taille.
 */
function disposer(racine) {
  const cadre = racine.querySelector('.agenda__cadre');
  const liste = racine.querySelector('.agenda__liste');
  const axe = racine.querySelector('.agenda__axe');
  const traits = racine.querySelector('.agenda__traits');
  if (!cadre || !liste || !axe || !traits) return;
  const cartes = Array.from(liste.children);
  const largeur = cadre.clientWidth;
  /* Deux rangées : chacune doit pouvoir tenir sa moitié des cartes. */
  const parRangee = Math.ceil(cartes.length / 2);
  const carteL = Math.min(FRISE.carte, Math.floor((largeur - (parRangee - 1) * FRISE.ecart) / Math.max(parRangee, 1)));
  const frise = largeur >= FRISE.largeurMin && cartes.length > 0 && carteL >= 190;
  racine.classList.toggle('agenda--frise', frise);
  if (!frise) {
    cadre.style.removeProperty('block-size');
    axe.replaceChildren();
    traits.replaceChildren();
    for (const c of cartes) c.removeAttribute('style');
    return;
  }

  /* Le temps : d'aujourd'hui au dernier rendez-vous, deux semaines au
     moins, et un peu d'air après le dernier — l'axe ne s'étire pas vers
     un mois vide, les repères occupent toute la largeur. */
  const debut = aujourdhui();
  const dates = cartes.map((c) => dateDe(c.dataset.date) || debut);
  const dernier = Math.max(...dates.map((d) => d.getTime()), debut.getTime());
  const etendue = Math.max(dernier - debut.getTime(), FRISE.horizonMin * JOUR_MS);
  const fin = new Date(debut.getTime() + etendue * 1.1 + 2 * JOUR_MS);
  const utile = largeur - 2 * FRISE.marge;
  const versX = (d) => Math.round(FRISE.marge + ((d.getTime() - debut.getTime()) / (fin.getTime() - debut.getTime())) * utile);
  const xs = dates.map(versX);
  /* Les cartes, elles, se partagent la largeur à parts égales, dans
     l'ordre des dates : trois rendez-vous serrés sur une semaine ne
     s'entassent plus à gauche. Le trait dit la vraie date. */
  const places = cartes.map((_c, i) => ((i + 0.5) / cartes.length) * largeur);
  MISES.set(racine, { x0: versX(debut), xs });

  /* Les cartes prennent leur largeur de frise avant d'être mesurées. */
  for (const c of cartes) c.style.inlineSize = carteL + 'px';
  const hauteurs = cartes.map((c) => c.offsetHeight);

  /* Un rendez-vous sur deux au-dessus : la frise alterne. */
  const rangs = { haut: [], bas: [] };
  cartes.forEach((c, i) => rangs[i % 2 === 0 ? 'bas' : 'haut'].push(i));
  const hHaut = Math.max(0, ...rangs.haut.map((i) => hauteurs[i]));
  const hBas = Math.max(0, ...rangs.bas.map((i) => hauteurs[i]));
  const y0 = hHaut + FRISE.ecart;            // haut de la bande de l'axe
  const yAxe = y0 + FRISE.axe / 2;
  cadre.style.blockSize = (y0 + FRISE.axe + FRISE.ecart + hBas) + 'px';
  axe.style.top = y0 + 'px';
  axe.style.blockSize = FRISE.axe + 'px';

  const lignes = [];
  for (const cote of ['haut', 'bas']) {
    const indices = rangs[cote];
    const gauches = rangee(indices.map((i) => places[i]), largeur, carteL, FRISE.ecart);
    indices.forEach((i, k) => {
      const c = cartes[i];
      const gauche = gauches[k];
      const haut = cote === 'haut' ? hHaut - hauteurs[i] : y0 + FRISE.axe + FRISE.ecart;
      c.classList.toggle('agenda__rdv--haut', cote === 'haut');
      c.classList.toggle('agenda__rdv--bas', cote === 'bas');
      c.style.left = gauche + 'px';
      c.style.top = haut + 'px';
      /* Le trait : du repère sur l'axe au bord de la carte, au plus près
         de la date. */
      const ancre = Math.min(Math.max(xs[i], gauche + 18), gauche + carteL - 18);
      const bord = cote === 'haut' ? haut + hauteurs[i] : haut;
      lignes.push(svg('line', {
        x1: xs[i], y1: yAxe + (cote === 'haut' ? -8 : 8), x2: ancre, y2: bord,
        class: 'agenda__trait', dataset: { pole: c.dataset.pole, i: String(i) },
        style: { '--i': String(i) }
      }));
    });
  }
  traits.replaceChildren(svg('svg', {
    class: 'agenda__traits-dessin', width: largeur, height: cadre.offsetHeight || (y0 + FRISE.axe + FRISE.ecart + hBas),
    'aria-hidden': 'true', focusable: 'false'
  }, lignes));

  dessinerAxe(axe, debut, fin, versX, cartes.map((c, i) => ({ x: xs[i], pole: c.dataset.pole, type: c.dataset.type })));
}

/* -------------------------------------------------------------------------
   3. La frise qui vit : le survol et l'arrivée
   ------------------------------------------------------------------------- */

/* Allume le rendez-vous de rang i (sa carte, son repère, son trait) et
   tend la jauge d'aujourd'hui jusqu'à lui ; null éteint tout. */
function allumer(racine, i) {
  const frise = racine.classList.contains('agenda--frise');
  const rang = frise && i !== null && Number.isFinite(i) ? i : null;
  racine.classList.toggle('agenda--allume', rang !== null);
  racine.querySelectorAll('[data-i]').forEach((n) => {
    n.classList.toggle('est-allume', rang !== null && Number(n.dataset.i) === rang);
  });
  const jauge = racine.querySelector('.agenda__progression');
  const mise = MISES.get(racine);
  if (!jauge || !mise) return;
  if (rang === null || mise.xs[rang] === undefined) {
    jauge.style.inlineSize = '0px';
    return;
  }
  const carteAllumee = racine.querySelector('.agenda__rdv[data-i="' + rang + '"]');
  jauge.dataset.pole = carteAllumee ? carteAllumee.dataset.pole : 'ETII';
  jauge.style.inlineSize = Math.max(0, mise.xs[rang] - mise.x0) + 'px';
}

function brancherSurvol(racine) {
  const rangDe = (cible) => {
    const n = cible && typeof cible.closest === 'function' ? cible.closest('.agenda__rdv, .agenda__repere') : null;
    return n && racine.contains(n) && n.dataset.i !== undefined ? Number(n.dataset.i) : null;
  };
  racine.addEventListener('pointerover', (e) => allumer(racine, rangDe(e.target)));
  racine.addEventListener('pointerleave', () => allumer(racine, null));
  racine.addEventListener('focusin', (e) => allumer(racine, rangDe(e.target)));
  racine.addEventListener('focusout', (e) => {
    if (!e.relatedTarget || !racine.contains(e.relatedTarget)) allumer(racine, null);
  });
}

/* La frise se dessine la première fois qu'elle entre à l'écran. Sans
   IntersectionObserver, ou si le système demande moins d'animations, elle
   est là d'emblée : rien n'est jamais caché faute d'observateur. */
function brancherArrivee(racine) {
  const calme = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (calme || typeof IntersectionObserver !== 'function') return;
  racine.classList.add('agenda--anime');
  const obs = new IntersectionObserver((vus) => {
    if (!vus.some((v) => v.isIntersecting)) return;
    obs.disconnect();
    requestAnimationFrame(() => racine.classList.add('agenda--vu'));
  }, { threshold: 0.2 });
  obs.observe(racine);
}

/* -------------------------------------------------------------------------
   4. Le bloc
   ------------------------------------------------------------------------- */

/**
 * Les prochains rendez-vous, sur leur frise.
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

  const racine = el('div', { class: 'agenda' },
    visibles.length
      ? el('div', { class: 'agenda__cadre' },
          el('div', { class: 'agenda__traits', 'aria-hidden': 'true' }),
          el('div', { class: 'agenda__axe', 'aria-hidden': 'true' }),
          el('ol', { class: 'agenda__liste', role: 'list' }, visibles.map((e, i) => carte(e, o, i))))
      : el('p', { class: 'agenda__vide' }, 'Aucun rendez-vous à venir pour le moment.'),
    entrees.length > visibles.length
      ? el('p', { class: 'agenda__suite' }, 'Et ' + (entrees.length - visibles.length) + ' autre' + (entrees.length - visibles.length > 1 ? 's' : '') + ' plus tard.')
      : null,
    typeof o.surAjouter === 'function' ? boutonAjouter('Ajouter un rendez-vous', o.surAjouter) : null);

  /* La mise en page suit la largeur du bloc, et la hauteur des cartes (une
     police qui arrive, le mode édition qui ajoute ses boutons). Une seule
     mesure par image. */
  if (visibles.length && typeof ResizeObserver === 'function') {
    let demande = false;
    let largeurVue = -1;
    const planifier = () => {
      if (demande) return;
      demande = true;
      requestAnimationFrame(() => { demande = false; if (racine.isConnected) disposer(racine); });
    };
    const observateur = new ResizeObserver((entrees2) => {
      /* Le cadre change de hauteur quand on le dispose : seul un changement
         de largeur, ou de taille d'une carte, relance la mise en page. */
      for (const e of entrees2) {
        if (e.target.classList.contains('agenda__cadre')) {
          const l = Math.round(e.contentRect.width);
          if (l === largeurVue) continue;
          largeurVue = l;
        }
        planifier();
        return;
      }
    });
    const cadre = racine.querySelector('.agenda__cadre');
    observateur.observe(cadre);
    racine.querySelectorAll('.agenda__rdv').forEach((c) => observateur.observe(c));
  }
  if (visibles.length) {
    brancherSurvol(racine);
    brancherArrivee(racine);
  }
  return racine;
}

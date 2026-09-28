/* =========================================================================
   ETII Hub — Les porteurs

   La section « Porteurs » du tableau de bord (index.html) : toute la
   flotte suivie par le service, rangée par marché — Civil, Militaire,
   Prototype. Deux vues, portées par l'adresse :

     index.html                    la galerie : de petites tuiles, toute
                                   la gamme d'un coup d'œil
     index.html#porteur=H160       la fiche d'un appareil

   Sur une fiche, un bandeau au-dessus d'elle porte le retour à la
   galerie, l'appareil précédent et le suivant. Les flèches ← → du clavier
   passent d'un appareil à l'autre, Échap revient à la galerie. (Une
   ancienne adresse « #comparer=… » ramène à la galerie.)

   Tout le DOM passe par el() de ui.js : aucun innerHTML.
   ========================================================================= */

import { el, monter, annoncer, etatUrl, rafThrottle } from './ui.js';
import { boutonAjouter } from './edition.js';
import { creditPhoto } from './credits.js';
import { GROUPES, texte, objet, nombreFr, chiffre, echelles, marches, anneeService, phase } from './gamme.js';
import { sceneGamme } from './gabarit.js';
import { fiche, photo, surnom, segment, pastilleMarche } from './fiche-porteur.js';

const NON_RENSEIGNE = 'à renseigner';

/* Les libellés de la fiche, par groupe et par champ : le formulaire de
   modification (edition-contenus.js) nomme les champs comme la fiche. */
export function libellesFiche() {
  const r = {};
  for (const g of GROUPES) r[g.cle] = Object.fromEntries(g.champs);
  return r;
}

/* -------------------------------------------------------------------------
   1. Les tris de la galerie
   ------------------------------------------------------------------------- */

/* Chaque tri dit dans quel ordre il range : du plus lourd au plus léger,
   du plus ancien au plus récent. Un appareil sans la valeur ferme la
   marche, dans l'ordre de la gamme. */
const TRIS = [
  { cle: 'gamme', libelle: 'Gamme', ordre: 'dans l’ordre de la gamme' },
  { cle: 'masse', libelle: 'Masse', ordre: 'du plus lourd au plus léger', chiffres: ['masseMaxDecollage'], sens: -1 },
  { cle: 'longueur', libelle: 'Longueur', ordre: 'du plus long au plus court', chiffres: ['longueur', 'longueurFuselage'], sens: -1 },
  { cle: 'vitesse', libelle: 'Vitesse', ordre: 'du plus rapide au plus lent', chiffres: ['vitesseCroisiere'], sens: -1 },
  { cle: 'service', libelle: 'Mise en service', ordre: 'du plus ancien au plus récent', sens: 1 }
];

function valeurTri(appareil, tri) {
  if (tri.cle === 'service') {
    const a = anneeService(appareil);
    return a ? { v: a.annee, texte: (a.prevu ? 'prévu ' : '') + a.annee } : null;
  }
  for (const cle of tri.chiffres || []) {
    const c = chiffre(appareil, cle);
    if (c && c.ref !== null) {
      const v = c.refMax !== null ? c.refMax : c.ref;
      const t = cle === 'masseMaxDecollage' ? tonnes(c) : nombreFr(c.ref, cle.startsWith('longueur') ? 2 : 0) + ' ' + c.def.unite + (cle === 'longueurFuselage' ? ' (fuselage)' : '');
      return { v, texte: t };
    }
  }
  return null;
}

/* Une masse en tonnes, pour la carte : « 2,25 t », « 7 à 8 t ». */
function tonnes(c) {
  const t = (kg) => nombreFr(kg / 1000, kg < 10000 ? 2 : 1);
  const avant = /environ|ordre/.test(c.qualificatif) ? '≈ ' : '';
  return avant + (c.refMax !== null && c.refMax !== c.ref ? t(c.ref) + ' à ' + t(c.refMax) : t(c.ref)) + ' t';
}

/* Les trois chiffres d'une carte : ce qu'il pèse, combien il emporte,
   à quelle vitesse. */
function chiffresCarte(appareil) {
  const parts = [];
  const m = chiffre(appareil, 'masseMaxDecollage');
  if (m && m.ref) parts.push(tonnes(m));
  const p = chiffre(appareil, 'passagers');
  if (p && p.nombre !== null) {
    const n = p.max !== null ? p.max : p.nombre;
    parts.push(n === 0 ? 'sans passager' : (p.max !== null && p.max !== p.nombre ? p.nombre + ' à ' + p.max : n) + (n > 1 ? ' places' : ' place'));
  }
  const v = chiffre(appareil, 'vitesseCroisiere');
  if (v && v.ref) parts.push(nombreFr(v.ref, 0) + ' km/h');
  return parts;
}

/* -------------------------------------------------------------------------
   2. La carte de la galerie
   ------------------------------------------------------------------------- */

/* Une petite tuile : la photo, le code, le surnom, et en une ligne ce
   que c'est. Les trois chiffres (masse, places, vitesse) restent dans la
   bulle du survol et dans la fiche : la galerie se parcourt d'un coup
   d'œil. */
function carte(appareil, ctx) {
  const code = texte(appareil.code);
  const p = phase(appareil);
  const chiffres = chiffresCarte(appareil);
  const tri = ctx.tri && ctx.tri.cle !== 'gamme' ? valeurTri(appareil, ctx.tri) : null;
  const nomCourt = surnom(appareil);
  const bulle = [code + (nomCourt ? ' ' + nomCourt : ''), segment(appareil), chiffres.join(' · ')].filter(Boolean).join(' — ');
  return el('li', { class: 'porteur-carte', dataset: { code, categorie: texte(appareil.categorie) } },
    el('a', { class: 'porteur-carte__lien', href: ctx.lien(code), dataset: { code }, title: bulle },
      el('span', { class: 'porteur-carte__visuel' },
        photo(appareil, { classe: 'porteur-carte__photo' }),
        p.cle && p.cle !== 'production' ? el('span', { class: 'porteur-carte__phase porteur-phase', dataset: { phase: p.cle } }, p.libelle) : null,
        ctx.marqueMarche ? el('span', { class: 'porteur-carte__marche' }, pastilleMarche(appareil.categorie, ctx.libelleMarche(appareil.categorie))) : null),
      el('span', { class: 'porteur-carte__corps' },
        el('span', { class: 'porteur-carte__titre' },
          el('span', { class: ['porteur-carte__code', code.length > 7 ? 'porteur-carte__code--long' : null] }, code),
          nomCourt ? el('span', { class: 'porteur-carte__surnom' }, nomCourt) : null),
        el('span', { class: 'porteur-carte__segment' }, segment(appareil) || NON_RENSEIGNE),
        tri
          ? el('span', { class: 'porteur-carte__tri' }, el('span', { class: 'porteur-carte__tri-libelle' }, ctx.tri.libelle), ' ', tri.texte)
          : null)));
}

/* -------------------------------------------------------------------------
   3. Le composant de page
   ------------------------------------------------------------------------- */

/**
 * Les porteurs : la galerie et la fiche.
 *
 * @param {object} donnees   contenu de flotte.json
 * @param {object} [options]
 * @param {Element} [options.bandeau]   le bandeau de navigation d'une fiche
 * @param {boolean} [options.enSection] dans une section de page : ni marchés à
 *                                      filtrer ni tris — toute la gamme, par marché
 * @param {Function} [options.surVue]   (vue) — la page suit la vue ouverte
 * @param {Function} [options.surAjouter]   (bouton, marché) — mode édition
 * @param {Function} [options.surModifier]  (appareil, bouton)
 * @param {Function} [options.surSupprimer] (appareil)
 * @returns {HTMLElement}
 */
export function porteurs(donnees, options) {
  const opts = options || {};
  const d = objet(donnees);
  const appareils = (Array.isArray(d.flotte) ? d.flotte : []).filter((a) => a && typeof a === 'object' && texte(a.code));
  const lesMarches = marches(d, appareils);
  const lesEchelles = echelles(appareils);
  const scene = sceneGamme(appareils);
  const libelleMarche = (cle) => (lesMarches.find((m) => m.cle === texte(cle)) || { libelle: texte(cle) }).libelle;

  const etat = { vue: 'galerie', code: '', marche: 'tous', tri: 'gamme' };
  /* Où l'on était dans la galerie avant d'ouvrir une fiche : on y revient. */
  let retour = { y: 0, code: '' };

  const trouver = (code) => appareils.find((a) => texte(a.code).toUpperCase() === texte(code).toUpperCase()) || null;
  const leTri = () => TRIS.find((t) => t.cle === etat.tri) || TRIS[0];

  /* Les adresses. Un lien de carte porte l'ancre de sa fiche : il s'ouvre
     dans un nouvel onglet, se copie, se partage. */
  const lien = (code) => '#porteur=' + encodeURIComponent(code);
  const lienGalerie = () => '#marche=' + encodeURIComponent(etat.marche) + (etat.tri !== 'gamme' ? '&tri=' + encodeURIComponent(etat.tri) : '');

  /* Changer d'adresse. Dans le fichier autonome, la page vit dans un cadre
     « about:srcdoc » : on garde sa base, on ne change que l'ancre. */
  function naviguer(ancre, remplacer) {
    try {
      if (remplacer) location.replace(location.href.split('#')[0] + ancre);
      else location.hash = ancre.slice(1);
    } catch (_e) { /* l'état interne suffit */ }
    appliquerAdresse();
  }

  /* La liste visible : le marché choisi, dans l'ordre du tri. */
  function visibles() {
    let liste = etat.marche === 'tous' ? appareils.slice() : appareils.filter((a) => texte(a.categorie) === etat.marche);
    const t = leTri();
    if (t.cle !== 'gamme') {
      const cle = new Map(liste.map((a) => [a, valeurTri(a, t)]));
      liste = liste.map((a, i) => ({ a, i, v: cle.get(a) })).sort((x, y) => {
        if (!x.v && !y.v) return x.i - y.i;
        if (!x.v) return 1;
        if (!y.v) return -1;
        return (x.v.v - y.v.v) * t.sens || x.i - y.i;
      }).map((x) => x.a);
    }
    return liste;
  }

  /* --- Les zones ------------------------------------------------------- */
  const zoneBarre = el('div', { class: 'porteurs__barre' });
  const zoneGalerie = el('div', { class: 'porteurs__galerie' });
  const zoneFiche = el('div', { class: 'porteurs__vue porteurs__vue--fiche', hidden: true });
  const vueGalerie = el('div', { class: 'porteurs__vue porteurs__vue--galerie' }, zoneBarre, zoneGalerie);
  const racine = el('div', { class: 'porteurs', dataset: { vue: 'galerie' } }, vueGalerie, zoneFiche);
  const bandeau = opts.bandeau || null;

  /* --- Le bandeau ------------------------------------------------------ */
  function rendreBandeau() {
    if (!bandeau) return;
    /* Dans une section, la galerie montre déjà les trois marchés : le
       bandeau ne sert qu'à la navigation d'une fiche. */
    bandeau.hidden = Boolean(opts.enSection) && etat.vue === 'galerie';
    if (bandeau.hidden) { monter(bandeau); return; }
    if (etat.vue === 'galerie') {
      const choix = [{ cle: 'tous', libelle: 'Tous', n: appareils.length }].concat(lesMarches.map((m) => ({ cle: m.cle, libelle: m.libelle, n: m.membres.length })));
      monter(bandeau, el('div', { class: 'porteurs-bandeau conteneur', role: 'group', 'aria-label': 'Marchés' },
        choix.map((m) => el('button', {
          type: 'button', class: 'porteurs-bandeau__marche', dataset: { marche: m.cle },
          'aria-pressed': etat.marche === m.cle ? 'true' : 'false'
        }, m.libelle, ' ', el('span', { class: 'porteurs-bandeau__compte' }, String(m.n))))));
      placerCurseur();
      return;
    }
    const retourLien = el('a', { class: 'porteurs-bandeau__retour', href: lienGalerie() },
      el('span', { 'aria-hidden': 'true' }, '← '), 'Tous', el('span', { class: 'porteurs-bandeau__long' }, ' les porteurs'));
    const liste = listeNavigation();
    const i = liste.findIndex((a) => texte(a.code) === etat.code);
    const prec = liste[(i - 1 + liste.length) % liste.length];
    const suiv = liste[(i + 1) % liste.length];
    monter(bandeau, el('div', { class: 'porteurs-bandeau porteurs-bandeau--nav conteneur' },
      retourLien,
      el('span', { class: 'porteurs-bandeau__pas' },
        el('a', { class: 'porteurs-bandeau__voisin', href: lien(texte(prec.code)), dataset: { code: texte(prec.code) }, 'aria-label': 'Précédent : ' + texte(prec.code) },
          el('span', { 'aria-hidden': 'true' }, '‹ '), texte(prec.code)),
        el('span', { class: 'porteurs-bandeau__ici', 'aria-current': 'page' },
          el('span', { class: 'porteurs-bandeau__code' }, etat.code),
          el('span', { class: 'porteurs-bandeau__position' }, (i + 1) + ' / ' + liste.length)),
        el('a', { class: 'porteurs-bandeau__voisin', href: lien(texte(suiv.code)), dataset: { code: texte(suiv.code) }, 'aria-label': 'Suivant : ' + texte(suiv.code) },
          texte(suiv.code), el('span', { 'aria-hidden': 'true' }, ' ›')))));
  }

  /* Le trait sous le marché choisi glisse d'un marché à l'autre. */
  function placerCurseur() {
    if (!bandeau) return;
    const rang = bandeau.querySelector('.porteurs-bandeau');
    const actif = bandeau.querySelector('.porteurs-bandeau__marche[aria-pressed="true"]');
    if (!rang || !actif) return;
    rang.style.setProperty('--curseur-x', actif.offsetLeft + 'px');
    rang.style.setProperty('--curseur-l', actif.offsetWidth + 'px');
  }

  /* L'ordre de navigation d'une fiche à l'autre : la galerie telle qu'on
     la voit ; si l'appareil n'y est pas (arrivée par un lien), toute la
     gamme. */
  function listeNavigation() {
    const v = visibles();
    return v.some((a) => texte(a.code) === etat.code) ? v : appareils;
  }

  /* --- La galerie ------------------------------------------------------ */
  function rendreBarre() {
    const t = leTri();
    const n = visibles().length;
    const quoi = etat.marche === 'tous' ? 'porteurs' : 'porteurs · ' + libelleMarche(etat.marche).toLowerCase();
    monter(zoneBarre,
      el('p', { class: 'porteurs__compte', role: 'status' },
        el('strong', {}, String(n)), ' ' + (n > 1 ? quoi : quoi.replace('porteurs', 'porteur')), el('span', { class: 'porteurs__ordre' }, ', ' + t.ordre)),
      el('div', { class: 'porteurs__outils' },
        opts.enSection ? null : el('div', { class: 'porteurs__tris', role: 'group', 'aria-label': 'Trier par' },
          el('span', { class: 'porteurs__tris-libelle', 'aria-hidden': 'true' }, 'Trier'),
          TRIS.map((x) => el('button', { type: 'button', class: 'porteurs__tri', dataset: { tri: x.cle }, 'aria-pressed': x.cle === etat.tri ? 'true' : 'false' }, x.libelle))),
        typeof opts.surAjouter === 'function'
          ? boutonAjouter('Ajouter un porteur', (b) => opts.surAjouter(b, etat.marche !== 'tous' ? etat.marche : null))
          : null));
  }

  function rendreGalerie() {
    rendreBarre();
    const t = leTri();
    const ctx = { lien, tri: t, libelleMarche, marqueMarche: etat.marche === 'tous' && t.cle !== 'gamme' };
    const grille = (liste) => el('ul', { class: 'porteurs__grille', role: 'list' }, liste.map((a) => carte(a, ctx)));
    if (!appareils.length) {
      monter(zoneGalerie, el('p', { class: 'texte-doux' }, 'Aucun porteur dans le fichier.'));
      return;
    }
    if (etat.marche === 'tous' && t.cle === 'gamme') {
      /* Toute la gamme, marché par marché : le nom du marché et son compte
         côte à côte, à gauche, au-dessus de ses cartes. */
      monter(zoneGalerie, lesMarches.filter((m) => m.membres.length).map((m) =>
        el('section', { class: 'porteurs__marche', dataset: { categorie: m.cle }, 'aria-labelledby': 'porteurs-marche-' + m.cle },
          el('h2', { class: 'porteurs__marche-titre', id: 'porteurs-marche-' + m.cle },
            m.libelle, ' ', el('span', { class: 'porteurs__marche-compte' }, m.membres.length + (m.membres.length > 1 ? ' appareils' : ' appareil'))),
          grille(m.membres))));
    } else {
      const liste = visibles();
      monter(zoneGalerie, liste.length ? grille(liste) : el('p', { class: 'texte-doux' }, 'Aucun porteur dans ce marché.'));
    }
  }

  /* --- Les vues -------------------------------------------------------- */
  function rendreFiche(appareil) {
    const liste = listeNavigation();
    const i = liste.indexOf(appareil);
    const n = liste.length;
    monter(zoneFiche, fiche(appareil, {
      appareils, echelles: lesEchelles, scene, marches: lesMarches,
      navigation: {
        precedent: n > 1 ? liste[(i - 1 + n) % n] : null,
        suivant: n > 1 ? liste[(i + 1) % n] : null,
        lien
      },
      surModifier: opts.surModifier, surSupprimer: opts.surSupprimer
    }));
  }

  /* Ramène le haut des porteurs à l'écran, sous la barre (et, dans une
     section, sous le sommaire collant) ; `descendre` : même s'il est plus
     bas que l'écran. */
  function allerEnHaut(descendre) {
    const cible = bandeau && !bandeau.hidden ? bandeau : racine;
    const haut = cible.getBoundingClientRect().top + window.scrollY;
    const racineStyle = getComputedStyle(document.documentElement);
    const barre = parseFloat(racineStyle.getPropertyValue('--hauteur-barre-site')) || 0;
    const sommaire = document.querySelector('.page-sommaire');
    const dessus = barre + (opts.enSection && sommaire ? sommaire.offsetHeight : 0) + 8;
    if (descendre || window.scrollY > haut - dessus) window.scrollTo({ top: Math.max(0, haut - dessus), behavior: 'auto' });
  }

  /* Arrivé par un lien vers une fiche : les sections du dessus finissent de
     se charger après la fiche et la repoussent. Tant que la page change de
     hauteur, la fiche reste en vue — jusqu'à ce que la personne fasse
     défiler elle-même, ou au plus deux secondes. */
  function garderEnVue() {
    if (typeof ResizeObserver !== 'function') { allerEnHaut(true); return; }
    let fini = false;
    const arreter = () => { fini = true; obs.disconnect(); ['wheel', 'touchstart', 'keydown'].forEach((t) => window.removeEventListener(t, arreter)); };
    const obs = new ResizeObserver(() => { if (!fini) allerEnHaut(true); });
    obs.observe(document.body);
    ['wheel', 'touchstart', 'keydown'].forEach((t) => window.addEventListener(t, arreter, { passive: true, once: true }));
    setTimeout(arreter, 2000);
    allerEnHaut(true);
  }

  let premier = true;
  function afficher(vue) {
    const avant = etat.vue;
    etat.vue = vue;
    racine.dataset.vue = vue;
    if (typeof opts.surVue === 'function') opts.surVue(vue);
    vueGalerie.hidden = vue !== 'galerie';
    zoneFiche.hidden = vue !== 'fiche';
    rendreBandeau();
    if (vue === 'galerie') {
      if (avant !== 'galerie') {
        rendreGalerie();
        /* Revenir d'une fiche : là où l'on était, le focus sur sa carte. */
        if (!premier) {
          window.scrollTo({ top: retour.y, behavior: 'auto' });
          const lienCarte = retour.code ? zoneGalerie.querySelector('.porteur-carte__lien[data-code="' + CSS.escape(retour.code) + '"]') : null;
          if (lienCarte) lienCarte.focus({ preventScroll: true });
        }
      }
    } else {
      if (avant === 'galerie' && !premier) retour = { y: window.scrollY, code: etat.code };
      if (premier && opts.enSection) garderEnVue(); else allerEnHaut();
      if (!premier) {
        const titre = racine.querySelector('.porteur-fiche__code');
        if (titre) titre.focus({ preventScroll: true });
      }
    }
    premier = false;
  }

  /* L'adresse fait foi : on la relit à chaque changement d'ancre. */
  let signature = '';
  function appliquerAdresse() {
    const e = etatUrl.lire();
    const marche = texte(e.marche);
    const tri = texte(e.tri);
    if (!opts.enSection && marche && (marche === 'tous' || lesMarches.some((m) => m.cle === marche))) etat.marche = marche;
    if (!opts.enSection && tri && TRIS.some((t) => t.cle === tri)) etat.tri = tri;
    const code = texte(e.porteur).toUpperCase();
    const a = code ? trouver(code) : null;
    let vue = 'galerie';
    if (a) { vue = 'fiche'; etat.code = texte(a.code); }
    const s = [vue, etat.code, etat.marche, etat.tri].join('|');
    if (s === signature) return;
    signature = s;
    if (vue === 'fiche') {
      /* L'appareil hors du marché filtré : on montre toute la gamme. */
      rendreFiche(a);
      annoncer('Fiche ' + etat.code);
    } else if (etat.vue === 'galerie') {
      rendreGalerie();
    }
    afficher(vue);
    /* Une ancre qui ne mène à rien (un porteur supprimé) : l'adresse est
       remise d'aplomb sur la galerie, sans entrée d'historique. */
    if (vue === 'galerie' && (code || e.comparer)) etatUrl.ecrire({ marche: etat.marche, tri: etat.tri !== 'gamme' ? etat.tri : null });
  }

  /* --- Les gestes ------------------------------------------------------ */
  function filtrer(marche, tri) {
    if (marche) etat.marche = marche;
    if (tri) etat.tri = tri;
    etatUrl.ecrire({ marche: etat.marche, tri: etat.tri !== 'gamme' ? etat.tri : null });
    signature = ['galerie', etat.code, etat.marche, etat.tri].join('|');
    rendreBandeau();
    rendreGalerie();
    const t = leTri();
    annoncer(visibles().length + ' porteurs, ' + t.ordre + '.');
  }

  if (bandeau) {
    bandeau.addEventListener('click', (evt) => {
      const b = evt.target.closest('.porteurs-bandeau__marche');
      if (b) { filtrer(b.dataset.marche, null); return; }
      /* Précédent, suivant : sans entrée d'historique, « Précédent » du
         navigateur ramène à la galerie. */
      const v = evt.target.closest('.porteurs-bandeau__voisin');
      if (v && !evt.ctrlKey && !evt.metaKey && !evt.shiftKey) { evt.preventDefault(); naviguer(lien(v.dataset.code), true); }
    });
  }
  racine.addEventListener('click', (evt) => {
    const tri = evt.target.closest('.porteurs__tri');
    if (tri) { filtrer(null, tri.dataset.tri); return; }
    const v = evt.target.closest('.porteur-voisin[data-code]');
    if (v && !evt.ctrlKey && !evt.metaKey && !evt.shiftKey) { evt.preventDefault(); naviguer(lien(v.dataset.code), true); }
  });

  /* Le clavier : sur une fiche, ← → d'un appareil à l'autre, Échap vers la
   galerie ; dans la galerie, ← → d'une carte à l'autre. Jamais pendant
   une saisie, ni quand une fenêtre est ouverte par-dessus. */
  const auClavier = (evt) => {
    if (!racine.isConnected || evt.defaultPrevented || evt.altKey || evt.ctrlKey || evt.metaKey || evt.shiftKey) return;
    const cible = evt.target;
    if (cible && (cible.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(cible.tagName))) return;
    if (document.querySelector('.modale')) return;
    if (etat.vue === 'fiche' && (evt.key === 'ArrowLeft' || evt.key === 'ArrowRight')) {
      if (cible && cible.closest && cible.closest('summary, details[open] *')) return;
      const liste = listeNavigation();
      const i = liste.findIndex((a) => texte(a.code) === etat.code);
      const j = (i + (evt.key === 'ArrowRight' ? 1 : -1) + liste.length) % liste.length;
      evt.preventDefault();
      naviguer(lien(texte(liste[j].code)), true);
      return;
    }
    if (etat.vue !== 'galerie' && evt.key === 'Escape') {
      evt.preventDefault();
      naviguer(lienGalerie(), false);
      return;
    }
    if (etat.vue === 'galerie' && (evt.key === 'ArrowLeft' || evt.key === 'ArrowRight') && cible && cible.classList && cible.classList.contains('porteur-carte__lien')) {
      const liens = Array.from(zoneGalerie.querySelectorAll('.porteur-carte__lien'));
      const i = liens.indexOf(cible);
      const j = Math.min(liens.length - 1, Math.max(0, i + (evt.key === 'ArrowRight' ? 1 : -1)));
      evt.preventDefault();
      liens[j].focus();
    }
  };
  document.addEventListener('keydown', auClavier);

  /* Le curseur du bandeau suit la largeur des marchés (une police qui
     arrive, une fenêtre qu'on redimensionne). */
  if (bandeau && typeof ResizeObserver === 'function') new ResizeObserver(rafThrottle(placerCurseur)).observe(bandeau);

  /* Arrivée : l'adresse décide de la vue ; ensuite, chaque changement
     d'ancre (un lien, « Précédent », la palette) la suit. */
  appliquerAdresse();
  if (etat.vue === 'galerie' && zoneGalerie.childNodes.length === 0) rendreGalerie();
  const arreter = etatUrl.ecouter(() => { if (racine.isConnected) appliquerAdresse(); else { arreter(); document.removeEventListener('keydown', auClavier); } });
  return racine;
}

/* -------------------------------------------------------------------------
   4. Les crédits de toutes les photos, pour la fenêtre « Crédits photos »
   ------------------------------------------------------------------------- */

/**
 * Construit la liste des crédits de toutes les photos de la flotte.
 * C'est l'obligation de licence rendue lisible en un seul endroit : le
 * pied de page l'ouvre dans une fenêtre.
 *
 * @param {object} donnees   contenu de flotte.json
 * @returns {HTMLElement}
 */
export function creditsPhotos(donnees) {
  const d = objet(donnees);
  const appareils = (Array.isArray(d.flotte) ? d.flotte : [])
    .filter((a) => a && typeof a === 'object' && texte(a.photo));
  if (!appareils.length) return el('p', { class: 'texte-doux sans-marge' }, 'Aucune photo dans la flotte.');
  return el('div', { class: 'pile' },
    el('p', { class: 'texte-doux texte-sm sans-marge mesure' },
      'Les photos des porteurs viennent de Wikimedia Commons, sous licence libre. '
      + 'Chaque auteur et chaque licence sont indiqués ici, comme la licence l’exige.'),
    el('ul', { class: 'porteurs__credits', role: 'list' }, appareils.map((a) => {
      const credit = creditPhoto(a.credit) || el('p', { class: 'porteurs__credit sans-marge porteur-manquant' }, 'Crédit ' + NON_RENSEIGNE);
      return el('li', { class: 'porteurs__credits-item' },
        el('img', { src: texte(a.photo), alt: '', loading: 'lazy', decoding: 'async', class: 'porteurs__credits-vignette' }),
        el('div', { class: 'porteurs__credits-texte' },
          el('span', { class: 'porteurs__credits-nom' }, texte(objet(a.fiche).nom) || texte(a.code)),
          credit));
    })));
}

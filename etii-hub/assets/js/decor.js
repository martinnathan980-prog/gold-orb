/* =========================================================================
   ETII Hub — Le décor vivant de l'espace ETIIE

   La une d'ETIIE porte, dessiné dans la page (etiie.html), un réseau de
   neurones : des liaisons, des neurones, quelques influx. Ce module le fait
   vivre, sans rien y ajouter de décoratif qui ne soit déjà là :
     - chaque neurone dérive lentement autour de sa place, sur une petite
       courbe de Lissajous qui lui est propre ;
     - les liaisons suivent leurs deux neurones ;
     - les influx courent de liaison en liaison sur le réseau qui bouge,
       une traîne derrière eux, la liaison parcourue s'éclaire ;
     - à l'arrivée, le neurone s'allume ; de temps en temps, l'un d'eux
       « décharge » : un halo, une onde qui s'élargit.
   Le nom du pôle reste net : les influx s'y effacent en passant dessous,
   et une décharge ne tombe que là où son onde tient tout entière, hors du
   nom et dans ce que la une montre du dessin.

   Tout est tiré d'une graine calculée sur le dessin lui-même : le réseau
   bouge de la même façon à chaque visite. Le coût est borné : 30 images
   par seconde au plus, rien quand la une a quitté l'écran ou que l'onglet
   est caché, et rien du tout sous « mouvement réduit » — le dessin reste
   alors tel que la page le pose.

   Les coordonnées sont celles du viewBox du dessin (880 × 260).

   API :
     animerReseau([racine])  anime le réseau .page-une__decor--nerf de la
                             racine (le document par défaut) ; sans réseau,
                             ne fait rien.
   ========================================================================= */

import { svg, mouvementReduit } from './ui.js';

/* Les réglages du mouvement, en unités du viewBox et en secondes. */
const DERIVE = { amplitude: [7, 13], periode: [11, 24] };
const INFLUX = { nombre: 8, vitesse: [52, 80], traine: 38 };
/* L'onde d'une décharge : 24 unités au plus, moins si la place manque ;
   sous 12 unités de place libre autour du neurone, pas de décharge. */
const ECLAT = { duree: 1.25, onde: 24, marge: 12, pool: 8 };
/* Une décharge spontanée toutes les 2,5 à 5 secondes, et une arrivée
   d'influx sur huit environ qui en déclenche une ; les autres arrivées
   allument seulement le neurone. */
const EVEIL = { ecart: [2.5, 5], parArrivee: 0.12 };
/* Au plus 30 images par seconde (un peu de marge pour la gigue). */
const PAS_MIN = 1000 / 30 - 4;

const REQUETE_MOUVEMENT = '(prefers-reduced-motion: reduce)';

/* -------------------------------------------------------------------------
   1. Le hasard, mais toujours le même
   ------------------------------------------------------------------------- */

/* Une empreinte du dessin (FNV-1a sur les coordonnées des neurones) sert
   de graine : même dessin, même mouvement. */
function empreinte(texte) {
  let h = 0x811c9dc5;
  for (let i = 0; i < texte.length; i++) {
    h ^= texte.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/* mulberry32 : court, rapide, suffisant pour un décor. */
function tirage(graine) {
  let a = graine >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const entre = (hasard, [min, max]) => min + (max - min) * hasard();

/* -------------------------------------------------------------------------
   2. Le réseau, lu dans le dessin
   ------------------------------------------------------------------------- */

const nombre = (noeud, nom) => Number.parseFloat(noeud.getAttribute(nom)) || 0;
const cle = (x, y) => Math.round(x) + ',' + Math.round(y);

function lireReseau(dessin) {
  const neurones = Array.from(dessin.querySelectorAll('.page-une__neurones circle')).map((noeud) => ({
    noeud, x0: nombre(noeud, 'cx'), y0: nombre(noeud, 'cy'), r: nombre(noeud, 'r') || 4, x: 0, y: 0
  }));
  const parPlace = new Map(neurones.map((n, i) => [cle(n.x0, n.y0), i]));

  /* Une liaison relie les deux neurones posés à ses extrémités ; celle qui
     n'aboutit pas à deux neurones reste immobile, telle que dessinée. */
  const liaisons = [];
  for (const noeud of dessin.querySelectorAll('.page-une__liaisons line')) {
    const a = parPlace.get(cle(nombre(noeud, 'x1'), nombre(noeud, 'y1')));
    const b = parPlace.get(cle(nombre(noeud, 'x2'), nombre(noeud, 'y2')));
    if (a === undefined || b === undefined || a === b) continue;
    liaisons.push({ noeud, a, b, actifs: 0 });
  }

  const voisins = neurones.map(() => []);
  liaisons.forEach((l, i) => { voisins[l.a].push(i); voisins[l.b].push(i); });
  return { neurones, liaisons, voisins };
}

/* -------------------------------------------------------------------------
   3. L'animation
   ------------------------------------------------------------------------- */

/**
 * Anime le réseau de neurones de la une ETIIE, s'il est dans la page.
 *
 * @param {Document|Element} [racine]
 * @returns {{arreter: Function}|null} null s'il n'y a rien à animer
 */
export function animerReseau(racine) {
  const dessin = (racine || document).querySelector('.page-une__decor--nerf');
  if (!dessin || dessin.dataset.vivant) return null;
  const { neurones, liaisons, voisins } = lireReseau(dessin);
  if (neurones.length < 2 || !liaisons.length) return null;
  dessin.dataset.vivant = 'oui';

  const hasard = tirage(empreinte(neurones.map((n) => cle(n.x0, n.y0)).join(';')));

  /* La dérive de chaque neurone : deux sinus par axe, partant de zéro pour
     que la première image soit exactement le dessin de la page. */
  for (const n of neurones) {
    const amplitude = entre(hasard, DERIVE.amplitude) * (n.r > 5 ? 0.8 : 1);
    n.ax = amplitude;
    n.ay = amplitude * 0.8;
    n.fx = [2 * Math.PI / entre(hasard, DERIVE.periode), 2 * Math.PI / entre(hasard, DERIVE.periode) * 2.3];
    n.fy = [2 * Math.PI / entre(hasard, DERIVE.periode), 2 * Math.PI / entre(hasard, DERIVE.periode) * 1.9];
    n.px = [hasard() * 2 * Math.PI, hasard() * 2 * Math.PI];
    n.py = [hasard() * 2 * Math.PI, hasard() * 2 * Math.PI];
  }

  /* --- Ce que le module ajoute au dessin : dégradés, traînes, éclats --- */

  const signaux = dessin.querySelector('.page-une__signaux') || dessin.appendChild(svg('g', { class: 'page-une__signaux' }));
  /* Les influx du dessin circulaient sur des chemins figés (SMIL) : ils
     passent sous la main du module, qui les fait suivre le réseau. */
  const points = Array.from(signaux.querySelectorAll('.page-une__influx'));
  for (const p of points) p.querySelectorAll('animateMotion').forEach((a) => a.remove());
  while (points.length < INFLUX.nombre) {
    const p = svg('circle', { class: 'page-une__influx', r: '3.5' });
    signaux.append(p);
    points.push(p);
  }

  const degrades = points.map((_p, i) => svg('linearGradient', { id: 'nerf-traine-' + i, gradientUnits: 'userSpaceOnUse' },
    svg('stop', { class: 'page-une__arret page-une__arret--vide', offset: '0' }),
    svg('stop', { class: 'page-une__arret', offset: '1' })));
  const halo = svg('radialGradient', { id: 'nerf-halo' },
    svg('stop', { class: 'page-une__arret page-une__arret--halo', offset: '0' }),
    svg('stop', { class: 'page-une__arret page-une__arret--vide', offset: '1' }));
  dessin.prepend(svg('defs', {}, degrades, halo));

  const influx = points.map((point, i) => {
    const traine = svg('line', { class: 'page-une__traine', style: { stroke: 'url(#nerf-traine-' + i + ')' } });
    signaux.insertBefore(traine, point);
    return { point, traine, degrade: degrades[i], liaison: 0, depart: 0, p: 0, vitesse: entre(hasard, INFLUX.vitesse), voile: '' };
  });

  const groupeEclats = svg('g', { class: 'page-une__eclats' });
  signaux.before(groupeEclats);
  const eclats = Array.from({ length: ECLAT.pool }, () => {
    const g = svg('g', { class: 'page-une__eclat' },
      svg('circle', { class: 'page-une__halo', fill: 'url(#nerf-halo)', r: '0' }),
      svg('circle', { class: 'page-une__onde', r: '0' }),
      svg('circle', { class: 'page-une__coeur', r: '0' }));
    groupeEclats.append(g);
    return { g, halo: g.children[0], onde: g.children[1], coeur: g.children[2], neurone: -1, age: Infinity, force: 0, rayon: 0 };
  });

  /* --- Les influx : chacun sur une liaison, dans un sens ------------------ */

  const entrer = (f, liaison, depart) => {
    liaisons[f.liaison].actifs = Math.max(0, liaisons[f.liaison].actifs - 1);
    if (!liaisons[f.liaison].actifs) liaisons[f.liaison].noeud.classList.remove('page-une__liaison--active');
    f.liaison = liaison;
    f.depart = depart;
    liaisons[liaison].actifs += 1;
    liaisons[liaison].noeud.classList.add('page-une__liaison--active');
  };

  /* Ce que la une montre du dessin, en unités du viewBox : sur un écran
     large, seulement une bande au milieu (le haut et le bas sont rognés,
     les bords s'effacent) ; au centre, le nom du pôle. Les influx sont
     attirés par ce qui se voit hors du nom (poids 3), passent rarement
     sous le nom (poids 0,2). Relu quand la une ou le nom changent de
     taille (le nom s'écrit après le chargement, la police arrive). */
  let bande = null;     // { gauche, droite, haut, bas }
  let nom = null;       // idem, la boîte du titre
  let poids = neurones.map(() => 1);

  /* La distance d'un point au nom (0 dessous). */
  const loinDuNom = (x, y) => {
    if (!nom) return Infinity;
    return Math.hypot(Math.max(nom.gauche - x, 0, x - nom.droite), Math.max(nom.haut - y, 0, y - nom.bas));
  };
  /* La place libre autour d'un point : jusqu'au bord de ce qui se voit,
     ou jusqu'au nom. Négative hors de la bande. */
  const place = (x, y) => Math.min(loinDuNom(x, y),
    bande ? Math.min(x - bande.gauche, bande.droite - x, y - bande.haut, bande.bas - y) : Infinity);
  /* Sous le nom, ce qui bouge s'efface (jusqu'à 18 %) : il reste lisible. */
  const voile = (x, y) => {
    const k = Math.min(1, loinDuNom(x, y) / 26);
    return 0.18 + 0.82 * k * k * (3 - 2 * k);
  };

  const titre = (dessin.parentElement || document).querySelector('.page-une h1');
  const mesurer = () => {
    const vb = dessin.viewBox && dessin.viewBox.baseVal;
    const boite = dessin.getBoundingClientRect();
    const cadre = (dessin.parentElement || dessin).getBoundingClientRect();
    if (!vb || !vb.width || !boite.width) return;
    const echelle = boite.width / vb.width;
    const versX = (px) => vb.x + (px - boite.left) / echelle;
    const versY = (px) => vb.y + (px - boite.top) / echelle;
    bande = {
      gauche: versX(Math.max(cadre.left, boite.left + boite.width * 0.16)),
      droite: versX(Math.min(cadre.right, boite.right - boite.width * 0.16)),
      haut: versY(cadre.top),
      bas: versY(cadre.bottom)
    };
    /* La place du nom dans la mise en page, sans la petite montée de son
       arrivée (une translation, que getBoundingClientRect compterait). */
    const parent = titre && titre.offsetParent;
    if (parent && titre.offsetWidth) {
      const p = parent.getBoundingClientRect();
      const x = p.left + titre.offsetLeft;
      const y = p.top + titre.offsetTop;
      nom = { gauche: versX(x), droite: versX(x + titre.offsetWidth), haut: versY(y), bas: versY(y + titre.offsetHeight) };
    } else {
      nom = null;
    }
    poids = neurones.map((n) => (loinDuNom(n.x0, n.y0) < 8 ? 0.2 : place(n.x0, n.y0) > n.r ? 3 : 1));
  };
  mesurer();
  if (typeof ResizeObserver === 'function') {
    const observateur = new ResizeObserver(() => mesurer());
    observateur.observe(dessin);
    if (dessin.parentElement) observateur.observe(dessin.parentElement);
    if (titre) observateur.observe(titre);
  } else {
    window.addEventListener('resize', mesurer);
  }

  /* Un tirage pondéré. */
  const choisir = (liste, peser) => {
    const total = liste.reduce((s, x) => s + peser(x), 0);
    let r = hasard() * total;
    for (const x of liste) { r -= peser(x); if (r < 0) return x; }
    return liste[liste.length - 1];
  };
  const autreBout = (liaison, neurone) => (liaisons[liaison].a === neurone ? liaisons[liaison].b : liaisons[liaison].a);

  influx.forEach((f) => {
    const l = choisir(liaisons.map((_l, i) => i), (i) => Math.max(poids[liaisons[i].a], poids[liaisons[i].b]));
    liaisons[l].actifs += 1;
    liaisons[l].noeud.classList.add('page-une__liaison--active');
    f.liaison = l;
    f.depart = hasard() < 0.5 ? liaisons[l].a : liaisons[l].b;
    f.p = hasard();
  });

  /* Au bout de la liaison : le neurone s'allume (décharge s'il a la place),
     et l'influx repart par une autre liaison que celle d'où il vient (s'il
     en a une). */
  const arriver = (f) => {
    const arrivee = autreBout(f.liaison, f.depart);
    const n = neurones[arrivee];
    const libre = place(n.x, n.y) - n.r;
    if (hasard() < EVEIL.parArrivee && libre >= ECLAT.marge) allumer(arrivee, 1, libre);
    else allumer(arrivee, 0.45 * voile(n.x, n.y), 0);
    const suites = voisins[arrivee].filter((i) => i !== f.liaison);
    const suite = suites.length ? choisir(suites, (i) => poids[autreBout(i, arrivee)]) : f.liaison;
    entrer(f, suite, arrivee);
  };

  /* --- Les éclats : un halo, un cœur, et pour une décharge une onde ------ */

  /* libre : la place autour du neurone (0 pour un simple allumage, sans
     onde) ; l'onde et le halo s'y tiennent. */
  function allumer(neurone, force, libre) {
    let e = eclats[0];
    for (const x of eclats) if (x.age > e.age) e = x;
    e.neurone = neurone;
    e.age = 0;
    e.force = force;
    e.rayon = libre > 0 ? Math.min(ECLAT.onde, libre - 3) : 0;
  }

  let prochainEveil = entre(hasard, EVEIL.ecart);

  /* --- Une image -------------------------------------------------------- */

  let t = 0;
  let dernier = null;
  let demande = 0;
  const fixe = (n) => n.toFixed(1);

  /* Le tronçon où court un influx : d'où il part, où il va, sa longueur
     à cet instant (les deux neurones bougent). */
  const troncon = (f) => {
    const de = neurones[f.depart];
    const vers = neurones[autreBout(f.liaison, f.depart)];
    return [de, vers, Math.hypot(vers.x - de.x, vers.y - de.y) || 1];
  };

  function dessiner(dt) {
    t += dt;

    for (const n of neurones) {
      n.x = n.x0 + n.ax * (0.7 * (Math.sin(n.fx[0] * t + n.px[0]) - Math.sin(n.px[0]))
        + 0.3 * (Math.sin(n.fx[1] * t + n.px[1]) - Math.sin(n.px[1])));
      n.y = n.y0 + n.ay * (0.7 * (Math.sin(n.fy[0] * t + n.py[0]) - Math.sin(n.py[0]))
        + 0.3 * (Math.sin(n.fy[1] * t + n.py[1]) - Math.sin(n.py[1])));
      n.noeud.setAttribute('cx', fixe(n.x));
      n.noeud.setAttribute('cy', fixe(n.y));
    }

    for (const l of liaisons) {
      const a = neurones[l.a];
      const b = neurones[l.b];
      l.noeud.setAttribute('x1', fixe(a.x));
      l.noeud.setAttribute('y1', fixe(a.y));
      l.noeud.setAttribute('x2', fixe(b.x));
      l.noeud.setAttribute('y2', fixe(b.y));
    }

    for (const f of influx) {
      let [de, vers, longueur] = troncon(f);
      f.p += f.vitesse * dt / longueur;
      if (f.p >= 1) {
        /* Le chemin parcouru au-delà du neurone se reporte sur la suite. */
        const reste = (f.p - 1) * longueur;
        arriver(f);
        [de, vers, longueur] = troncon(f);
        f.p = Math.min(0.99, reste / longueur);
      }
      /* La traîne : une longueur fixe derrière l'influx, qui s'efface vers
         l'arrière (son dégradé la suit, en coordonnées du dessin). */
      const queue = Math.max(0, f.p - INFLUX.traine / longueur);
      const px = de.x + (vers.x - de.x) * f.p;
      const py = de.y + (vers.y - de.y) * f.p;
      const x = fixe(px);
      const y = fixe(py);
      const qx = fixe(de.x + (vers.x - de.x) * queue);
      const qy = fixe(de.y + (vers.y - de.y) * queue);
      f.point.setAttribute('cx', x);
      f.point.setAttribute('cy', y);
      /* Sous le nom, l'influx et sa traîne s'effacent. */
      const v = voile(px, py).toFixed(2);
      if (v !== f.voile) {
        f.voile = v;
        f.point.style.opacity = (0.95 * v).toFixed(2);
        f.traine.style.opacity = v;
      }
      for (const noeud of [f.traine, f.degrade]) {
        noeud.setAttribute('x1', qx);
        noeud.setAttribute('y1', qy);
        noeud.setAttribute('x2', x);
        noeud.setAttribute('y2', y);
      }
    }

    prochainEveil -= dt;
    if (prochainEveil <= 0) {
      /* Une décharge spontanée, là où son onde tient tout entière. */
      const candidats = neurones.map((n, i) => [i, place(n.x, n.y) - n.r]).filter(([, libre]) => libre >= ECLAT.marge);
      if (candidats.length) {
        const [i, libre] = candidats[Math.floor(hasard() * candidats.length)];
        allumer(i, 1, libre);
      }
      prochainEveil = entre(hasard, EVEIL.ecart);
    }

    for (const e of eclats) {
      if (e.neurone < 0) continue;
      e.age += dt;
      const k = Math.min(1, e.age / ECLAT.duree);
      if (k >= 1) {
        e.neurone = -1;
        e.g.setAttribute('opacity', '0');
        continue;
      }
      const n = neurones[e.neurone];
      const ouverture = 1 - Math.pow(1 - k, 3);
      const extinction = Math.pow(1 - k, 1.6);
      e.g.setAttribute('opacity', (e.force * extinction).toFixed(3));
      for (const c of [e.halo, e.onde, e.coeur]) {
        c.setAttribute('cx', fixe(n.x));
        c.setAttribute('cy', fixe(n.y));
      }
      const halo = n.r * (1.6 + 2.6 * ouverture);
      e.halo.setAttribute('r', fixe(e.rayon ? Math.min(halo, n.r + e.rayon + 3) : halo));
      e.coeur.setAttribute('r', fixe(n.r * (1 - 0.3 * k)));
      e.onde.setAttribute('r', e.rayon ? fixe(n.r + e.rayon * ouverture) : '0');
    }
  }

  function image(maintenant) {
    demande = requestAnimationFrame(image);
    if (dernier !== null && maintenant - dernier < PAS_MIN) return;
    const dt = dernier === null ? 0 : Math.min(0.1, (maintenant - dernier) / 1000);
    dernier = maintenant;
    dessiner(dt);
  }

  /* --- Quand tourner : visible, onglet affiché, mouvement permis --------- */

  let visible = true;
  let enMarche = false;

  const demarrer = () => {
    if (enMarche) return;
    enMarche = true;
    dernier = null;
    dessin.classList.add('page-une__decor--vivant');
    demande = requestAnimationFrame(image);
  };

  const suspendre = () => {
    if (!enMarche) return;
    enMarche = false;
    cancelAnimationFrame(demande);
  };

  /* Sous « mouvement réduit », le dessin revient exactement à celui de la
     page : les neurones à leur place, aucune traîne, aucun éclat. */
  const figer = () => {
    suspendre();
    dessin.classList.remove('page-une__decor--vivant');
    for (const n of neurones) {
      n.noeud.setAttribute('cx', String(n.x0));
      n.noeud.setAttribute('cy', String(n.y0));
    }
    for (const l of liaisons) {
      l.noeud.setAttribute('x1', String(neurones[l.a].x0));
      l.noeud.setAttribute('y1', String(neurones[l.a].y0));
      l.noeud.setAttribute('x2', String(neurones[l.b].x0));
      l.noeud.setAttribute('y2', String(neurones[l.b].y0));
    }
    t = 0;
  };

  const decider = () => {
    if (mouvementReduit()) figer();
    else if (visible && !document.hidden) demarrer();
    else suspendre();
  };

  if (typeof IntersectionObserver === 'function') {
    new IntersectionObserver((entrees) => {
      visible = entrees.some((e) => e.isIntersecting);
      decider();
    }).observe(dessin);
  }
  document.addEventListener('visibilitychange', decider);
  try { window.matchMedia(REQUETE_MOUVEMENT).addEventListener('change', decider); } catch (_e) { /* navigateur ancien : réglage lu au démarrage */ }

  decider();
  return { arreter: figer };
}

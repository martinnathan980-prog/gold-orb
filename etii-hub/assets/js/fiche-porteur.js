/* =========================================================================
   ETII Hub — La fiche d'un porteur, et le comparateur

   La fiche répond d'abord aux questions qu'on se pose devant un appareil,
   dans cet ordre, et en chiffres : qu'est-ce que c'est, quelle taille,
   quel poids, combien à bord, à quelle vitesse, jusqu'où, avec quels
   moteurs, depuis quand. Une phrase d'accroche, pas plus ; tout le reste
   est un nombre, son unité, et ce qu'il veut dire en français courant.

     1. La tête : la photo en grand, le code, le nom, le marché, la phase.
     2. L'essentiel : six chiffres, toujours les mêmes et dans le même
        ordre, chacun situé sur une jauge « par rapport à la gamme » ; ceux
        qu'aucune source ne donne sont nommés en une ligne.
     3. À l'échelle, et à côté la frise du programme : le profil de
        l'appareil près d'une personne de 1,80 m, ou d'un autre porteur si
        on le demande (gabarit.js) ; depuis quand il vole.
     4. Dans le détail : une carte par groupe, une ligne par valeur, la
        précision en petit dessous.
     5. Le « saviez-vous », et ce que le service seul peut dire —
        « à renseigner », jamais inventé.
     6. En pied : les sources et la confiance de chaque valeur, repliées,
        et les appareils voisins.

   Le comparateur pose deux ou trois appareils côte à côte : les mêmes
   chiffres, une barre par valeur, le plus grand marqué, et l'écart au
   premier appareil choisi.

   Tout le DOM passe par el() / svg() de ui.js : aucun innerHTML.
   ========================================================================= */

import { el } from './ui.js';
import { barreEdition } from './edition.js';
import { silhouette } from './helicos.js';
import { gabarit } from './gabarit.js';
import {
  NON_RENSEIGNE, CHIFFRES, GROUPES, ESSENTIEL, texte, objet, nombreFr,
  champ, chiffre, formater, formaterRef, rang, phase, anneeService, chronologie,
  accroche, dimensions, sourcesLisibles
} from './gamme.js';

/* -------------------------------------------------------------------------
   0. Petits morceaux partagés avec la galerie
   ------------------------------------------------------------------------- */

/* La photo d'un appareil ; sans photo, ou si elle ne se charge pas (un
   réseau d'entreprise qui filtre, une adresse qui a changé), sa silhouette
   prend la place — jamais d'icône cassée. */
export function photo(appareil, options) {
  const o = options || {};
  const repli = () => el('span', { class: ['porteur-photo__repli', o.classe ? o.classe + '--repli' : null] },
    silhouette(texte(appareil.silhouette), { titre: '' }));
  const src = texte(appareil.photo);
  if (!src) return repli();
  const img = el('img', {
    src, alt: o.alt || '', class: o.classe || null, decoding: 'async',
    loading: o.immediat ? null : 'lazy',
    onError: () => img.replaceWith(repli())
  });
  return img;
}

/* Le nom court : le surnom entre parenthèses ou après le code (« Écureuil /
   AStar », « Fennec », « Guépard »), sinon rien. */
export function surnom(appareil) {
  const code = texte(appareil.code);
  const nom = texte(objet(appareil.fiche).nom);
  const par = /\(([^)]+)\)\s*$/.exec(nom);
  if (par) return par[1];
  const i = code ? nom.toUpperCase().indexOf(code.toUpperCase()) : -1;
  if (i >= 0) {
    const reste = nom.slice(i + code.length).trim();
    if (reste && !/^[-–(]/.test(reste)) return reste;
  }
  return '';
}

/* Le segment en clair, sans sa précision de classe entre parenthèses
   quand elle ne fait que répéter la masse. */
export function segment(appareil) {
  return texte(appareil.segment) || texte(objet(appareil.fiche).segment);
}

/* L'étiquette d'un marché : son nom, sur une pastille à sa teinte. */
export function pastilleMarche(cle, libelle) {
  return el('span', { class: 'porteur-marche', dataset: { marche: texte(cle) } }, libelle || cle);
}

/* La phase du programme, en pastille : on voit d'un coup ce qui vole déjà
   en série et ce qui n'est encore qu'un prototype. */
export function pastillePhase(appareil) {
  const p = phase(appareil);
  return el('span', { class: 'porteur-phase', dataset: { phase: p.cle || 'inconnue' }, title: p.statut || null }, p.libelle);
}

/* « En service depuis 1978 », « Premier vol prévu fin 2026 »… */
export function depuisQuand(appareil) {
  const a = anneeService(appareil);
  const p = phase(appareil).cle;
  if (!a) return '';
  if (a.quoi === 'service') {
    if (a.prevu) return 'mise en service prévue en ' + a.annee;
    return (p === 'demonstrateur' ? 'depuis ' : 'en service depuis ') + a.annee;
  }
  return a.prevu ? 'premier vol prévu en ' + a.annee : 'premier vol en ' + a.annee;
}

const POLES = { ETIIA: 'etiia.html', ETIIE: 'etiie.html', ETIII: 'etiii.html' };

function pastillesPoles(appareil) {
  const poles = (Array.isArray(appareil.poles) ? appareil.poles : []).map(texte).filter((p) => POLES[p]);
  if (!poles.length) return el('span', { class: 'porteur-manquant' }, 'aucun pôle pour l’instant');
  return el('span', { class: 'porteur-poles' }, poles.map((p) =>
    el('a', { class: 'porteur-pole', href: POLES[p], dataset: { pole: p } }, p)));
}

/* -------------------------------------------------------------------------
   1. Un chiffre en grand, et sa jauge
   ------------------------------------------------------------------------- */

/* Le nombre en grand, l'unité en petit, le qualificatif (« environ »)
   devant, en petit aussi. */
function valeurGrande(f, classe) {
  return el('span', { class: classe || 'porteur-grand' },
    f.avant ? el('span', { class: 'porteur-grand__avant' }, f.avant + ' ') : null,
    el('span', { class: 'porteur-grand__nombre' }, f.nombre),
    f.unite ? el('span', { class: 'porteur-grand__unite' }, ' ' + f.unite) : null);
}

/**
 * La jauge « par rapport à la gamme » : un trait avec un repère par
 * appareil renseigné, l'appareil de la fiche en grand. Les extrémités sont
 * légendées ; la phrase complète est lue par les lecteurs d'écran.
 */
function jauge(cle, c, echelle, code) {
  if (!echelle || echelle.valeurs.length < 3 || !(echelle.max > echelle.min) || c.ref === null) return null;
  const pos = (v) => ((v - echelle.min) / (echelle.max - echelle.min) * 100).toFixed(2) + '%';
  const r = rang(echelle, code);
  const def = CHIFFRES[cle];
  const majuscule = (t) => t.charAt(0).toUpperCase() + t.slice(1);
  const phrase = r
    ? (r.dessous === 0 ? 'En bas de la gamme, avec le chiffre le plus petit'
      : r.dessous === r.total - 1 ? majuscule(def.lePlus) + ' de la gamme'
        : majuscule(def.plus) + ' que ' + r.dessous + ' des ' + (r.total - 1) + ' autres porteurs renseignés')
    : '';
  return el('div', { class: 'porteur-jauge', role: 'img', 'aria-label': 'Par rapport à la gamme : ' + phrase + '.', title: phrase },
    el('span', { class: 'porteur-jauge__piste' },
      echelle.valeurs.filter((x) => x.code !== code).map((x) =>
        el('span', { class: 'porteur-jauge__repere', style: { '--pos': pos(x.v) } })),
      c.refMax !== null && c.refMax > c.ref
        ? el('span', { class: 'porteur-jauge__plage', style: { '--pos': pos(c.ref), '--fin': pos(c.refMax) } })
        : null,
      el('span', { class: 'porteur-jauge__moi', style: { '--pos': pos(c.refMax !== null ? c.refMax : c.ref) } })),
    el('span', { class: 'porteur-jauge__legende' },
      el('span', {}, formaterRef(cle, echelle.min)),
      el('span', { class: 'porteur-jauge__titre' }, 'par rapport à la gamme'),
      el('span', {}, formaterRef(cle, echelle.max))));
}

/* Une tuile de « L'essentiel ». Trois tuiles se composent : la longueur
   retombe sur celle du fuselage, les passagers disent l'équipage, la
   puissance dit le nombre de moteurs. */
function tuile(appareil, cle, echelles) {
  const code = texte(appareil.code);
  let c = chiffre(appareil, cle);
  let libelle = CHIFFRES[cle].libelle;
  let question = CHIFFRES[cle].question;
  let cleJauge = cle;
  if (cle === 'longueur' && !c) {
    c = chiffre(appareil, 'longueurFuselage');
    if (c) { libelle = CHIFFRES.longueurFuselage.libelle; question = CHIFFRES.longueurFuselage.question; cleJauge = 'longueurFuselage'; }
  }
  if (cle === 'passagers') {
    const eq = chiffre(appareil, 'equipage');
    if (eq) question = 'en cabine ; à l’avant : ' + formater(eq).texte;
  }
  /* Sans valeur, pas de tuile : la fiche le dit en une ligne, sous les
     autres (voir essentiel()). */
  if (!c) return null;
  let f = formater(c);
  if (cle === 'puissance') {
    libelle = 'Puissance';
    const n = chiffre(appareil, 'nombreMoteurs');
    const moteur = champ(appareil, 'motorisation', 'moteur');
    if (c && n && n.nombre > 1) f = Object.assign({}, f, { avant: [n.nombre + ' ×', f.avant].filter(Boolean).join(' ') });
    question = (n && n.nombre ? (n.nombre > 1 ? 'chacun de ses ' + n.nombre + ' moteurs' : 'son moteur') : 'par moteur')
      + (moteur && moteur.nombre === null ? ', ' + texte(moteur.valeur) : '') + ', au décollage';
    if (c && c.unite === 'ch' && c.ref) question += ' (≈ ' + nombreFr(c.ref, 0) + ' kW)';
  }
  return el('div', { class: 'porteur-tuile', dataset: { chiffre: cle } },
    el('dt', { class: 'porteur-tuile__libelle' }, libelle),
    el('dd', { class: 'porteur-tuile__corps' },
      valeurGrande(f),
      el('span', { class: 'porteur-tuile__question' }, question),
      jauge(cleJauge, c, echelles[cleJauge], code)));
}

/* Les libellés courts des chiffres de l'essentiel, pour la ligne qui dit
   ceux qui manquent. */
const ESSENTIEL_COURT = {
  longueur: 'la longueur', masseMaxDecollage: 'la masse au décollage', passagers: 'les places à bord',
  vitesseCroisiere: 'la vitesse de croisière', distanceFranchissable: 'la distance franchissable', puissance: 'la puissance'
};

/* L'essentiel : les tuiles renseignées, dans l'ordre fixe ; celles qui
   manquent sont nommées en une ligne, « à renseigner » — pas six cases
   vides pour un démonstrateur dont rien n'est publié. */
function essentiel(appareil, echelles, idTitre) {
  const tuiles = [];
  const manquent = [];
  for (const cle of ESSENTIEL) {
    const t = tuile(appareil, cle, echelles);
    if (t) tuiles.push(t); else manquent.push(ESSENTIEL_COURT[cle]);
  }
  return el('section', { class: 'porteur-section porteur-essentiel', 'aria-labelledby': idTitre + '-essentiel' },
    el('h3', { class: 'porteur-section__titre', id: idTitre + '-essentiel' }, 'L’essentiel'),
    tuiles.length ? el('dl', { class: 'porteur-tuiles', dataset: { nombre: String(tuiles.length) } }, tuiles) : null,
    manquent.length
      ? el('p', { class: 'porteur-essentiel__manque' },
        el('span', { class: 'porteur-essentiel__manque-mot' }, tuiles.length ? 'Pas encore publié' : 'Aucun chiffre publié pour l’instant'),
        ' : ' + manquent.join(', ') + ' — ' + NON_RENSEIGNE + '.')
      : null);
}

/* -------------------------------------------------------------------------
   2. Dans le détail : une carte par groupe
   ------------------------------------------------------------------------- */

function ligneDetail(libelle, c) {
  const f = formater(c);
  return el('div', { class: 'porteur-ligne' },
    el('dt', { class: 'porteur-ligne__libelle' }, libelle),
    el('dd', { class: 'porteur-ligne__valeur' },
      el('span', { class: ['porteur-ligne__principal', f.chiffre ? 'porteur-ligne__principal--chiffre' : null] }, f.texte),
      c.note ? el('span', { class: 'porteur-ligne__note' }, c.note) : null));
}

function carteGroupe(appareil, g) {
  const lignes = [];
  const manquants = [];
  for (const [cle, libelle] of g.champs) {
    const c = CHIFFRES[cle] ? chiffre(appareil, cle) : champ(appareil, g.cle, cle);
    /* Un rayon d'action ou une longueur de fuselage absents ne manquent pas :
       peu de sources les donnent, la fiche n'en fait pas un trou. */
    if (!c) { if (cle !== 'rayonAction' && cle !== 'longueurFuselage') manquants.push(libelle.charAt(0).toLowerCase() + libelle.slice(1)); continue; }
    lignes.push(ligneDetail(libelle, c));
  }
  return el('section', { class: ['porteur-groupe', lignes.length ? null : 'porteur-groupe--vide'], dataset: { groupe: g.cle } },
    el('h4', { class: 'porteur-groupe__titre' }, g.titre),
    lignes.length ? el('dl', { class: 'porteur-groupe__lignes' }, lignes) : null,
    manquants.length
      ? el('p', { class: 'porteur-groupe__manque' },
        el('span', { class: 'porteur-groupe__manque-mot' }, lignes.length ? 'À renseigner : ' : 'Rien de publié pour l’instant : '),
        manquants.join(', ') + '.')
      : null);
}

/* -------------------------------------------------------------------------
   3. En marge : la frise, le « saviez-vous », le service
   ------------------------------------------------------------------------- */

function frise(appareil) {
  const evenements = chronologie(appareil);
  const cette = new Date().getFullYear();
  const p = phase(appareil);
  const items = [];
  let aujourdhuiPose = false;
  const poserAujourdhui = () => {
    items.push(el('li', { class: 'porteur-frise__jalon porteur-frise__jalon--maintenant' },
      el('span', { class: 'porteur-frise__annee' }, 'Aujourd’hui'),
      el('span', { class: 'porteur-frise__texte' }, p.libelle)));
    aujourdhuiPose = true;
  };
  for (const e of evenements) {
    if (!aujourdhuiPose && (e.prevu || e.annee > cette)) poserAujourdhui();
    items.push(el('li', { class: ['porteur-frise__jalon', e.prevu ? 'porteur-frise__jalon--prevu' : null] },
      el('span', { class: 'porteur-frise__annee' }, String(e.annee)),
      el('span', { class: 'porteur-frise__texte' }, e.texte + (e.prevu && !/prévu|visé|attendu/i.test(e.texte) ? ' (prévu)' : ''))));
  }
  if (!aujourdhuiPose) poserAujourdhui();
  return el('section', { class: 'porteur-marge__bloc', 'aria-labelledby': 'porteur-titre-frise' },
    el('h3', { class: 'porteur-marge__titre', id: 'porteur-titre-frise' }, 'Le programme'),
    evenements.length ? el('ol', { class: 'porteur-frise', role: 'list' }, items)
      : el('p', { class: 'porteur-manquant sans-marge' }, 'Dates ' + NON_RENSEIGNE + '.'));
}

/* Un fait : sa première phrase d'accroche, la suite repliée. */
function saviezVous(appareil) {
  const faits = (Array.isArray(objet(appareil.fiche).insolites) ? appareil.fiche.insolites : []).filter((f) => f && texte(f.texte));
  if (!faits.length) return null;
  const fait = (f, i) => {
    const t = texte(f.texte);
    const coupe = t.search(/[.!?;](\s|$)/);
    const tete = coupe > 30 && coupe < t.length - 2 ? t.slice(0, coupe + 1).replace(/\s*;$/, '.') : t;
    const suite = tete === t ? '' : t.slice(coupe + 1).trim();
    return el('li', { class: 'porteur-fait' },
      el('span', { class: 'porteur-fait__numero', 'aria-hidden': 'true' }, String(i + 1).padStart(2, '0')),
      suite
        ? el('details', { class: 'porteur-fait__plie' },
          el('summary', { class: 'porteur-fait__tete' }, tete),
          el('p', { class: 'porteur-fait__suite' }, suite.charAt(0).toUpperCase() + suite.slice(1)))
        : el('p', { class: 'porteur-fait__tete sans-marge' }, tete));
  };
  const premiers = faits.slice(0, 2);
  const autres = faits.slice(2);
  return el('section', { class: 'porteur-marge__bloc', 'aria-labelledby': 'porteur-titre-faits' },
    el('h3', { class: 'porteur-marge__titre', id: 'porteur-titre-faits' }, 'Le saviez-vous ?'),
    el('ol', { class: 'porteur-faits', role: 'list' }, premiers.map(fait)),
    autres.length
      ? el('details', { class: 'porteur-faits__encore' },
        el('summary', {}, autres.length === 1 ? 'Une autre anecdote' : autres.length + ' autres anecdotes'),
        el('ol', { class: 'porteur-faits', role: 'list', start: 3 }, autres.map((f, i) => fait(f, i + 2))))
      : null);
}

/* Ce que le service seul peut dire : les pôles qui suivent l'appareil, et
   ses données internes. Tant que le fichier ne les donne pas, elles sont
   « à renseigner » — la fiche ne les invente jamais. */
function pourLeService(appareil, champsService) {
  const service = objet(appareil.service);
  const technique = Object.assign({}, objet(appareil.technique), objet(service.technique));
  const economique = Object.assign({}, objet(appareil.economique), objet(service.economique));
  const cs = objet(champsService);
  const valeurDe = (v) => ((v === null || v === undefined) ? '' : texte(typeof v === 'object' ? v.valeur : v));
  const liste = (cles, valeurs) => (Array.isArray(cles) ? cles : Object.keys(valeurs).map((c) => ({ cle: c, libelle: c })))
    .map((c) => ({ libelle: texte(c.libelle) || texte(c.cle), valeur: valeurDe(valeurs[c.cle]) }));
  const ligne = (libelle, t) => el('div', { class: 'porteur-service__ligne' },
    el('dt', {}, libelle),
    el('dd', { class: t ? null : 'porteur-manquant' }, t || NON_RENSEIGNE));
  /* Un groupe : ses valeurs saisies en lignes ; celles qui manquent,
     nommées ensemble, « à renseigner ». */
  const bloc = (titre, champs) => {
    const saisis = champs.filter((x) => x.valeur);
    const vides = champs.filter((x) => !x.valeur).map((x) => x.libelle.charAt(0).toLowerCase() + x.libelle.slice(1));
    return el('div', { class: 'porteur-service__bloc' },
      el('p', { class: 'porteur-service__sous-titre' }, titre),
      saisis.length ? el('dl', { class: 'porteur-service__lignes' }, saisis.map((x) => ligne(x.libelle, x.valeur))) : null,
      vides.length
        ? el('p', { class: 'porteur-service__vides' }, el('span', { class: 'porteur-manquant' }, NON_RENSEIGNE), ' : ' + vides.join(', ') + '.')
        : null);
  };
  return el('section', { class: 'porteur-marge__bloc porteur-service', 'aria-labelledby': 'porteur-titre-service' },
    el('h3', { class: 'porteur-marge__titre', id: 'porteur-titre-service' }, 'Pour le service'),
    el('p', { class: 'porteur-service__intro' }, 'Ce que seul le service peut dire. Tant que ce n’est pas saisi, c’est « à renseigner » : rien n’est inventé.'),
    el('dl', { class: 'porteur-service__lignes' },
      el('div', { class: 'porteur-service__ligne' }, el('dt', {}, 'Suivi par'), el('dd', {}, pastillesPoles(appareil))),
      ligne('Jalon', valeurDe(appareil.jalon)), ligne('Avancement', valeurDe(appareil.avancement))),
    bloc('Technique', liste(cs.technique, technique)),
    bloc('Économique', liste(cs.economique, economique)));
}

/* -------------------------------------------------------------------------
   4. Les sources, repliées
   ------------------------------------------------------------------------- */

const CONFIANCE = { haute: 'fiable', moyenne: 'à recouper', faible: 'fragile' };

function sources(appareil) {
  const f = objet(appareil.fiche);
  const lignes = [];
  for (const g of GROUPES) {
    for (const [cle, libelle] of g.champs) {
      const c = champ(appareil, g.cle, cle);
      if (!c || !c.source) continue;
      lignes.push(el('li', { class: 'porteur-source' },
        el('p', { class: 'porteur-source__tete' },
          el('span', { class: 'porteur-source__champ' }, libelle),
          el('span', { class: 'porteur-source__valeur' }, formater(c).texte),
          c.confiance ? el('span', { class: 'porteur-confiance', dataset: { confiance: c.confiance } }, CONFIANCE[c.confiance] || c.confiance) : null),
        c.detail ? el('p', { class: 'porteur-source__detail' }, 'La source dit : ', el('q', {}, c.detail)) : null,
        c.correction ? el('p', { class: 'porteur-source__correction' }, 'Corrigé : ' + c.correction) : null,
        el('p', { class: 'porteur-source__ou' }, sourcesLisibles(c.source).join(' · '))));
    }
  }
  const toutes = (Array.isArray(f.sources) ? f.sources : []).map(texte).filter(Boolean);
  const relue = texte(f.relecture);
  return el('details', { class: 'porteur-sources' },
    el('summary', { class: 'porteur-sources__resume' },
      el('span', {}, 'Sources et fiabilité'),
      el('span', { class: 'porteur-sources__compte' }, lignes.length + ' valeur' + (lignes.length > 1 ? 's' : '') + ' sourcée' + (lignes.length > 1 ? 's' : '')),
      relue === 'non effectuée' ? el('span', { class: 'porteur-phase', dataset: { phase: 'relecture' } }, 'relecture à faire') : null),
    el('div', { class: 'porteur-sources__corps' },
      el('p', { class: 'porteur-sources__intro' },
        'Chaque valeur vient d’une source publique (Wikipédia, site public d’Airbus Helicopters, presse aéronautique). '
        + 'La confiance dit si elle est fiable, à recouper ou fragile. '
        + (relue === 'non effectuée' ? 'La fiche n’a pas encore été relue par le service : vérifiez une valeur avant de vous en servir.' : '')),
      lignes.length ? el('ul', { class: 'porteur-sources__liste', role: 'list' }, lignes) : null,
      toutes.length
        ? el('div', { class: 'porteur-sources__toutes' },
          el('p', { class: 'porteur-service__sous-titre' }, 'Toutes les sources de la fiche'),
          el('ul', { class: 'porteur-sources__liens', role: 'list' }, toutes.map((s) => el('li', {}, sourcesLisibles(s).join(' ')))))
        : null));
}

/* -------------------------------------------------------------------------
   5. La fiche
   ------------------------------------------------------------------------- */

/* À l'échelle : le profil de l'appareil, et au choix un autre porteur à
   côté. Changer de voisin redessine la scène, rien d'autre. */
function aLEchelle(appareil, ctx) {
  const code = texte(appareil.code);
  const scene = el('div', { class: 'porteur-echelle__scene' });
  const autres = (ctx.appareils || []).filter((a) => texte(a.code) !== code && dimensions(a));
  /* Sur un écran large, tous les appareils partagent la même scène : passer
     d'une fiche à l'autre fait grandir ou rétrécir le dessin. Sur un
     téléphone, le dessin prend toute la largeur, pour rester lisible. */
  const etroit = typeof matchMedia === 'function' && matchMedia('(max-width: 40rem)').matches;
  const dessiner = (voisin) => {
    const d = voisin
      ? gabarit([appareil, voisin])
      : gabarit([appareil], { cotes: true, scene: etroit ? null : ctx.scene });
    if (d) scene.replaceChildren(d);
  };
  if (!dimensions(appareil)) {
    const D = chiffre(appareil, 'diametreRotor');
    const manque = [D ? null : 'le diamètre du rotor', (chiffre(appareil, 'longueur') || chiffre(appareil, 'longueurFuselage')) ? null : 'la longueur'].filter(Boolean);
    return el('section', { class: 'porteur-section porteur-echelle porteur-echelle--vide', 'aria-labelledby': 'porteur-titre-echelle' },
      el('h3', { class: 'porteur-section__titre', id: 'porteur-titre-echelle' }, 'À l’échelle'),
      el('p', { class: 'porteur-echelle__manque sans-marge' },
        'Pas encore de dessin à l’échelle : il manque ' + manque.join(' et ') + '.'));
  }
  dessiner(null);
  const idChoix = 'porteur-voisin-' + code.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const choix = el('select', { class: 'champ__controle porteur-echelle__choix', id: idChoix },
    el('option', { value: '' }, 'seul, avec la personne'),
    autres.map((a) => el('option', { value: texte(a.code) }, texte(a.code) + (segment(a) ? ' — ' + segment(a) : ''))));
  choix.addEventListener('change', () => dessiner(autres.find((a) => texte(a.code) === choix.value) || null));
  return el('section', { class: 'porteur-section porteur-echelle', 'aria-labelledby': 'porteur-titre-echelle' },
    el('div', { class: 'porteur-section__tete' },
      el('h3', { class: 'porteur-section__titre', id: 'porteur-titre-echelle' }, 'À l’échelle'),
      el('div', { class: 'porteur-echelle__voisin' },
        el('label', { for: idChoix }, 'Le mettre à côté d’un autre :'), choix)),
    scene,
    el('p', { class: 'porteur-echelle__legende sans-marge' },
      'Silhouette stylisée, dessinée à la vraie taille du rotor et, quand la fiche les donne, de la longueur et de la hauteur. '
      + 'Une personne de 1,80 m sert de repère.'));
}

/**
 * La fiche complète d'un porteur.
 *
 * @param {object} appareil
 * @param {object} ctx
 * @param {object[]} ctx.appareils     toute la flotte
 * @param {object} ctx.echelles        echelles(appareils), calculées une fois
 * @param {object} [ctx.scene]         sceneGamme(appareils) : l'échelle commune
 * @param {object} [ctx.champsService] flotte.json → champs
 * @param {Array<{cle:string, libelle:string}>} [ctx.marches]
 * @param {{precedent?:object, suivant?:object, position?:number, total?:number,
 *          lien:(code:string)=>string, lienComparer:(code:string)=>string}} ctx.navigation
 * @param {Function} [ctx.surModifier]  (appareil, bouton)
 * @param {Function} [ctx.surSupprimer] (appareil)
 * @returns {HTMLElement}
 */
export function fiche(appareil, ctx) {
  const code = texte(appareil.code) || '—';
  const f = objet(appareil.fiche);
  const nav = ctx.navigation || {};
  const idTitre = 'porteur-titre-' + code.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const marche = (ctx.marches || []).find((m) => m.cle === texte(appareil.categorie));
  const nom = texte(f.nom);
  const ancien = champ(appareil, 'identite', 'ancienNom');

  /* 1. La tête : la photo, et le titre posé dessus. */
  const visuel = el('div', { class: ['porteur-fiche__photo', texte(appareil.photo) ? null : 'porteur-fiche__photo--silhouette'] },
    photo(appareil, { classe: 'porteur-fiche__image', immediat: true, alt: 'Photo du ' + code }),
    el('span', { class: 'porteur-fiche__voile', 'aria-hidden': 'true' }));
  const tete = el('header', { class: 'porteur-fiche__tete' },
    visuel,
    el('div', { class: 'porteur-fiche__titres' },
      el('p', { class: 'porteur-fiche__surtitre' },
        pastilleMarche(appareil.categorie, marche ? marche.libelle : texte(appareil.categorie)),
        segment(appareil) ? el('span', { class: 'porteur-fiche__segment' }, segment(appareil)) : null),
      el('h2', { class: 'porteur-fiche__code', id: idTitre, tabIndex: -1 }, code),
      nom ? el('p', { class: 'porteur-fiche__nom' }, nom) : null,
      el('p', { class: 'porteur-fiche__etat' }, pastillePhase(appareil),
        depuisQuand(appareil) ? el('span', {}, depuisQuand(appareil)) : null)));

  /* L'accroche, et ce qu'on peut faire de la fiche. */
  const commandes = (typeof ctx.surModifier === 'function' || typeof ctx.surSupprimer === 'function')
    ? barreEdition({
      classe: 'porteurs__edition',
      quoi: code,
      surModifier: typeof ctx.surModifier === 'function' ? (b) => ctx.surModifier(appareil, b) : null,
      surSupprimer: typeof ctx.surSupprimer === 'function' ? () => ctx.surSupprimer(appareil) : null
    })
    : null;
  const phrase = accroche(appareil);
  const intro = el('div', { class: 'porteur-fiche__intro' },
    el('div', { class: 'porteur-fiche__propos' },
      phrase ? el('p', { class: 'porteur-fiche__accroche' }, phrase) : null,
      ancien ? el('p', { class: 'porteur-fiche__ancien' }, el('span', {}, 'Aussi connu comme '), texte(ancien.valeur)) : null,
      texte(f.resume) && texte(f.resume) !== phrase
        ? el('details', { class: 'porteur-fiche__presentation' },
          el('summary', {}, 'Lire la présentation'),
          el('p', { class: 'sans-marge' }, texte(f.resume)))
        : null),
    el('div', { class: 'porteur-fiche__actions' },
      nav.lienComparer
        ? el('a', { class: 'bouton bouton--secondaire porteur-fiche__comparer', href: nav.lienComparer(code) },
          el('span', { 'aria-hidden': 'true' }, '⇄ '), 'Comparer avec un autre')
        : null,
      commandes));

  /* 4. Dans le détail. */
  const detail = el('section', { class: 'porteur-section porteur-detail', 'aria-labelledby': idTitre + '-detail' },
    el('h3', { class: 'porteur-section__titre', id: idTitre + '-detail' }, 'Dans le détail'),
    el('div', { class: 'porteur-groupes' }, GROUPES.map((g) => carteGroupe(appareil, g))));

  /* 6. Les voisins. */
  const voisin = (a, sens) => (a
    ? el('a', { class: ['porteur-voisin', 'porteur-voisin--' + sens], href: nav.lien(texte(a.code)), dataset: { code: texte(a.code), sens } },
      el('span', { class: 'porteur-voisin__sens' }, sens === 'precedent' ? '← Précédent' : 'Suivant →'),
      el('span', { class: 'porteur-voisin__code' }, texte(a.code)),
      el('span', { class: 'porteur-voisin__segment' }, segment(a)))
    : el('span', { class: 'porteur-voisin porteur-voisin--vide' }));

  return el('article', { class: 'porteur-fiche', 'aria-labelledby': idTitre, dataset: { code, marche: texte(appareil.categorie) } },
    tete,
    intro,
    essentiel(appareil, ctx.echelles || {}, idTitre),
    /* La taille réelle, et à côté la frise du programme : depuis quand. */
    el('div', { class: 'porteur-fiche__duo' }, aLEchelle(appareil, ctx), frise(appareil)),
    detail,
    /* Pour finir : une histoire à raconter, et ce que le service y ajoute. */
    el('div', { class: 'porteur-fiche__duo porteur-fiche__duo--bas' }, saviezVous(appareil), pourLeService(appareil, ctx.champsService)),
    el('footer', { class: 'porteur-fiche__pied' },
      sources(appareil),
      el('nav', { class: 'porteur-voisins', 'aria-label': 'Porteurs voisins' },
        voisin(nav.precedent, 'precedent'), voisin(nav.suivant, 'suivant'))));
}

/* -------------------------------------------------------------------------
   6. Le comparateur
   ------------------------------------------------------------------------- */

/* Les lignes du comparateur : l'essentiel d'abord, puis le reste. */
const LIGNES_COMPARER = [
  ['Taille', ['longueur', 'longueurFuselage', 'hauteur', 'diametreRotor']],
  ['Masse', ['masseMaxDecollage', 'masseAVide', 'chargeUtile']],
  ['À bord', ['passagers', 'equipage']],
  ['Motorisation', ['nombreMoteurs', 'puissance']],
  ['Performances', ['vitesseCroisiere', 'vitesseMax', 'distanceFranchissable', 'rayonAction', 'autonomie', 'plafond']],
  ['Programme', ['miseEnService', 'unitesProduites']]
];

/* L'écart au premier appareil choisi : « × 2,7 » quand l'un vaut plusieurs
   fois l'autre, « + 12 % » sinon. */
function ecart(v, ref) {
  if (!(ref > 0) || !Number.isFinite(v)) return '';
  const r = v / ref;
  if (Math.abs(r - 1) < 0.005) return '=';
  if (r >= 1.5) return '× ' + nombreFr(r, 1);
  if (r <= 0.67) return '÷ ' + nombreFr(1 / r, 1);
  const p = Math.round((r - 1) * 100);
  return (p > 0 ? '+ ' : '− ') + Math.abs(p) + ' %';
}

/**
 * Deux ou trois porteurs côte à côte.
 * @param {object[]} choisis  les appareils, dans l'ordre (le premier sert de référence)
 * @param {object} ctx  { appareils, marches, lien(code), surChanger(i, code), surRetirer(i) }
 */
export function comparateur(choisis, ctx) {
  const tous = ctx.appareils || [];
  const n = choisis.length;
  /* L'en-tête : une colonne par appareil, sa photo, son code, et de quoi le
     remplacer ou le retirer ; une colonne pour en ajouter un tant qu'on
     n'en a pas trois. */
  const selecteur = (i, actuel) => {
    const id = 'comparer-choix-' + i;
    const s = el('select', { class: 'champ__controle comparateur__choix', id, 'aria-label': actuel ? 'Remplacer le ' + texte(actuel.code) : 'Ajouter un porteur à la comparaison' },
      actuel ? null : el('option', { value: '' }, 'Ajouter un porteur…'),
      tous.map((a) => el('option', { value: texte(a.code), selected: actuel && a === actuel ? true : null,
        disabled: !actuel || a !== actuel ? (choisis.includes(a) ? true : null) : null }, texte(a.code) + (segment(a) ? ' — ' + segment(a) : ''))));
    s.addEventListener('change', () => { if (s.value) ctx.surChanger(i, s.value); });
    return s;
  };
  const colonnes = choisis.map((a, i) => el('div', { class: ['comparateur__colonne', 'comparateur__colonne--' + i] },
    el('a', { class: 'comparateur__carte', href: ctx.lien(texte(a.code)) },
      el('span', { class: 'comparateur__visuel' }, photo(a, { classe: 'comparateur__image' })),
      el('span', { class: 'comparateur__code' }, texte(a.code)),
      el('span', { class: 'comparateur__segment' }, segment(a))),
    el('div', { class: 'comparateur__outils' },
      selecteur(i, a),
      n > 1 ? el('button', { type: 'button', class: 'bouton bouton--discret bouton--compact comparateur__retirer',
        'aria-label': 'Retirer le ' + texte(a.code), onClick: () => ctx.surRetirer(i) }, '×') : null)));
  if (n < 3) {
    colonnes.push(el('div', { class: 'comparateur__colonne comparateur__colonne--ajout' },
      el('div', { class: 'comparateur__ajout' },
        el('span', { class: 'comparateur__ajout-signe', 'aria-hidden': 'true' }, '+'),
        el('span', {}, n < 2 ? 'Choisissez un autre porteur' : 'Un troisième, si vous voulez')),
      el('div', { class: 'comparateur__outils' }, selecteur(n, null))));
  }

  /* Le tableau : une ligne par chiffre renseigné pour au moins un appareil. */
  const corps = [];
  for (const [titre, cles] of LIGNES_COMPARER) {
    const rangees = [];
    for (const cle of cles) {
      if (cle === 'miseEnService') {
        const annees = choisis.map((a) => anneeService(a));
        if (!annees.some(Boolean)) continue;
        rangees.push(el('tr', { class: 'comparateur__ligne' },
          el('th', { scope: 'row', class: 'comparateur__libelle' }, 'Depuis', el('span', { class: 'comparateur__question' }, 'mise en service, ou premier vol')),
          annees.map((x, i) => el('td', { class: ['comparateur__cellule', 'comparateur__cellule--' + i] },
            x ? el('span', { class: 'comparateur__valeur' }, (x.prevu ? 'prévu ' : '') + x.annee + (x.quoi === 'vol' ? ' (vol)' : ''))
              : el('span', { class: 'porteur-manquant' }, '—')))));
        continue;
      }
      const valeurs = choisis.map((a) => chiffre(a, cle));
      if (!valeurs.some((c) => c)) continue;
      const refs = valeurs.map((c) => (c && c.ref !== null ? (c.refMax !== null ? c.refMax : c.ref) : null));
      const max = Math.max(...refs.filter((v) => v !== null), 0);
      const plusieurs = refs.filter((v) => v !== null).length > 1;
      const tete = refs[0];
      rangees.push(el('tr', { class: 'comparateur__ligne' },
        el('th', { scope: 'row', class: 'comparateur__libelle' }, CHIFFRES[cle].libelle,
          el('span', { class: 'comparateur__question' }, CHIFFRES[cle].question)),
        valeurs.map((c, i) => {
          if (!c) return el('td', { class: ['comparateur__cellule', 'comparateur__cellule--' + i] }, el('span', { class: 'porteur-manquant' }, '—'));
          const v = refs[i];
          const plus = plusieurs && v !== null && v === max && max > 0;
          return el('td', { class: ['comparateur__cellule', 'comparateur__cellule--' + i, plus ? 'comparateur__cellule--plus' : null] },
            valeurGrande(formater(c), 'porteur-grand porteur-grand--moyen'),
            v !== null && max > 0
              ? el('span', { class: 'comparateur__barre', 'aria-hidden': 'true' }, el('span', { style: { '--part': (v / max).toFixed(3) } }))
              : null,
            el('span', { class: 'comparateur__ecart' },
              plus ? el('span', { class: 'comparateur__plus' }, CHIFFRES[cle].lePlus) : null,
              i > 0 && v !== null && tete !== null ? el('span', { class: 'comparateur__delta' }, ecart(v, tete) + ' / ' + texte(choisis[0].code)) : null));
        })));
    }
    if (rangees.length) {
      corps.push(el('tbody', { class: 'comparateur__groupe' },
        el('tr', { class: 'comparateur__intertitre' }, el('th', { scope: 'rowgroup', colSpan: n + 1 }, titre)),
        rangees));
    }
  }

  const dessin = gabarit(choisis);
  return el('section', { class: 'comparateur', 'aria-labelledby': 'comparateur-titre', style: { '--colonnes': String(n) } },
    el('div', { class: 'comparateur__tete' },
      el('h2', { class: 'comparateur__titre', id: 'comparateur-titre', tabIndex: -1 }, 'Comparer'),
      el('p', { class: 'comparateur__intro sans-marge' },
        n < 2 ? 'Ajoutez un deuxième porteur pour les voir côte à côte.'
          : 'Les mêmes chiffres, côte à côte. La barre compare les appareils choisis entre eux ; l’écart se lit par rapport au premier.')),
    el('div', { class: 'comparateur__colonnes', style: { '--nb': String(colonnes.length) } }, colonnes),
    n > 1 && dessin
      ? el('section', { class: 'porteur-section comparateur__echelle', 'aria-labelledby': 'comparateur-titre-echelle' },
        el('h3', { class: 'porteur-section__titre', id: 'comparateur-titre-echelle' }, 'À l’échelle'),
        dessin)
      : null,
    n > 1 && corps.length
      ? el('div', { class: 'comparateur__table-cadre' },
        el('table', { class: 'comparateur__table' },
          el('caption', { class: 'visuellement-cache' }, 'Comparaison de ' + choisis.map((a) => texte(a.code)).join(', ')),
          el('thead', {}, el('tr', {},
            el('td', {}),
            choisis.map((a, i) => el('th', { scope: 'col', class: ['comparateur__entete', 'comparateur__entete--' + i] }, texte(a.code))))),
          corps))
      : null);
}

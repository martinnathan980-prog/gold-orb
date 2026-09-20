/* =========================================================================
   ETII Hub — Les porteurs
   La flotte suivie par le service, comme un carrousel : une piste de
   fiches compactes qu'on fait défiler, et sous la piste, la fiche du
   porteur choisi — silhouette ou photo, pôles concernés, données
   techniques et économiques telles que le fichier les déclare. Une
   valeur absente s'écrit « à renseigner », jamais autre chose.
   ========================================================================= */

import { el, monter, annoncer } from './ui.js';
import { silhouette } from './helicos.js';

const NON_RENSEIGNE = 'à renseigner';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function objet(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {}; }

function valeurLisible(brut, unite) {
  if (brut === null || brut === undefined) return { texte: NON_RENSEIGNE, ok: false };
  if (typeof brut === 'number') {
    if (!Number.isFinite(brut)) return { texte: NON_RENSEIGNE, ok: false };
    const u = texte(unite);
    return { texte: u ? `${brut} ${u}` : String(brut), ok: true };
  }
  if (Array.isArray(brut)) {
    const l = brut.map(texte).filter(Boolean);
    return l.length ? { texte: l.join(' · '), ok: true } : { texte: NON_RENSEIGNE, ok: false };
  }
  if (typeof brut === 'object') {
    const o = objet(brut);
    return ('valeur' in o) ? valeurLisible(o.valeur, o.unite ?? unite) : { texte: NON_RENSEIGNE, ok: false };
  }
  const t = texte(brut);
  if (!t) return { texte: NON_RENSEIGNE, ok: false };
  const u = texte(unite);
  return { texte: u ? `${t} ${u}` : t, ok: true };
}

function categories(donnees, appareils) {
  const liste = Array.isArray(donnees.categories) ? donnees.categories : [];
  const vues = new Map();
  for (const c of liste) {
    const o = typeof c === 'object' ? objet(c) : { cle: c, libelle: c };
    const cle = texte(o.cle ?? o.id ?? o.code);
    if (cle && !vues.has(cle)) vues.set(cle, { cle, libelle: texte(o.libelle ?? o.nom) || cle });
  }
  for (const a of appareils) {
    const cle = texte(a.categorie);
    if (cle && !vues.has(cle)) vues.set(cle, { cle, libelle: cle });
  }
  return [...vues.values()];
}

function champs(donnees, groupe) {
  const c = objet(objet(donnees.champs)[groupe]);
  const liste = Array.isArray(objet(donnees.champs)[groupe]) ? objet(donnees.champs)[groupe]
    : (Array.isArray(c.champs) ? c.champs : []);
  return liste.filter((d) => d && typeof d === 'object' && texte(d.cle))
    .map((d) => ({ cle: texte(d.cle), libelle: texte(d.libelle) || texte(d.cle), unite: texte(d.unite) }));
}

function pastillePole(code) {
  return el('span', { class: 'porteurs__pole', dataset: { pole: code } },
    el('span', { class: 'porteurs__pole-point', 'aria-hidden': 'true' }),
    'Pôle ' + code);
}

/* -------------------------------------------------------------------------
   La fiche compacte de la piste
   ------------------------------------------------------------------------- */

function fiche(appareil, prefixe) {
  const code = texte(appareil.code) || '—';
  return el('li', { class: 'porteurs__item', dataset: { categorie: texte(appareil.categorie) } },
    el('button', {
      type: 'button',
      class: 'porteurs__fiche',
      id: prefixe + '-fiche-' + code,
      dataset: { code },
      'aria-pressed': 'false'
    },
    el('span', { class: 'porteurs__fiche-visuel', 'aria-hidden': 'true' },
      silhouette(texte(appareil.silhouette), { titre: '' })),
    el('span', { class: 'porteurs__fiche-code' }, code),
    el('span', { class: 'porteurs__fiche-segment' }, texte(appareil.segment) || texte(objet(appareil.fiche).segment) || NON_RENSEIGNE),
    el('span', { class: 'porteurs__fiche-poles', 'aria-label': 'Pôles : ' + (Array.isArray(appareil.poles) ? appareil.poles.join(', ') : '') },
      (Array.isArray(appareil.poles) ? appareil.poles : []).map((p) =>
        el('span', { class: 'porteurs__pole-point', dataset: { pole: texte(p) }, title: 'Pôle ' + texte(p) })))));
}

/* -------------------------------------------------------------------------
   La fiche détaillée

   Deux formes de données cohabitent :
   - `fiche` : la base d'information PUBLIQUE constituée par le service
     (identité, motorisation, masses, capacité, performances, dimensions,
     production et économie, électrique et avionique, insolite, sources).
     Chaque champ porte sa valeur, son unité, sa confiance et sa source.
   - `service` (ou l'ancien couple technique / economique) : les données
     INTERNES au service, jamais inventées — « à renseigner » tant que le
     fichier ne les donne pas.
   ------------------------------------------------------------------------- */

const CONFIANCES = {
  haute:   { glyphe: '●', libelle: 'confiance haute — valeur confirmée par au moins une source publique' },
  moyenne: { glyphe: '◐', libelle: 'confiance moyenne — valeur publique non recoupée' },
  faible:  { glyphe: '○', libelle: 'confiance faible — à vérifier' }
};

const GROUPES_FICHE = [
  { cle: 'motorisation', titre: 'Motorisation', champs: [
    ['moteur', 'Moteur'], ['nombreMoteurs', 'Nombre de moteurs'], ['puissance', 'Puissance'],
    ['rotorPrincipal', 'Rotor principal'], ['rotorArriere', 'Rotor arrière']] },
  { cle: 'masses', titre: 'Masses', champs: [
    ['masseMaxDecollage', 'Masse max. au décollage'], ['masseAVide', 'Masse à vide'], ['chargeUtile', 'Charge utile']] },
  { cle: 'capacite', titre: 'Capacité', champs: [['equipage', 'Équipage'], ['passagers', 'Passagers']] },
  { cle: 'performances', titre: 'Performances', champs: [
    ['vitesseCroisiere', 'Vitesse de croisière'], ['vitesseMax', 'Vitesse maximale'], ['rayonAction', 'Rayon d’action'],
    ['autonomie', 'Autonomie'], ['plafond', 'Plafond']] },
  { cle: 'dimensions', titre: 'Dimensions', champs: [
    ['longueur', 'Longueur'], ['hauteur', 'Hauteur'], ['diametreRotor', 'Diamètre du rotor']] },
  { cle: 'production', titre: 'Production & économie', champs: [
    ['unitesProduites', 'Unités produites'], ['prixIndicatif', 'Prix indicatif'], ['cadence', 'Cadence'],
    ['principauxOperateurs', 'Principaux opérateurs'], ['commandesNotables', 'Commandes notables']] },
  { cle: 'electrique', titre: 'Électrique & avionique', champs: [
    ['reseau', 'Réseau électrique'], ['generation', 'Génération'], ['avionique', 'Avionique'], ['particularites', 'Particularités']] }
];

const IDENTITE = [
  ['constructeur', 'Constructeur'], ['premierVol', 'Premier vol'], ['certification', 'Certification'],
  ['miseEnService', 'Mise en service'], ['siteAssemblage', 'Site d’assemblage']];

const ONGLETS = [
  { cle: 'technique', titre: 'Technique', groupes: ['motorisation', 'masses', 'capacite', 'dimensions'] },
  { cle: 'performances', titre: 'Performances', groupes: ['performances'] },
  { cle: 'economie', titre: 'Production & économie', groupes: ['production'] },
  { cle: 'electrique', titre: 'Électrique', groupes: ['electrique'] },
  { cle: 'insolite', titre: 'Insolite' },
  { cle: 'service', titre: 'Données service' },
  { cle: 'sources', titre: 'Sources' }
];

function champFiche(brut) {
  const c = (brut && typeof brut === 'object' && !Array.isArray(brut)) ? brut : { valeur: brut };
  const v = valeurLisible(c.valeur, c.unite);
  const confiance = CONFIANCES[texte(c.confiance)] ? texte(c.confiance) : (v.ok ? 'moyenne' : 'faible');
  return { texte: v.texte, ok: v.ok, confiance, source: texte(c.source) };
}

function lienSource(url) {
  const u = texte(url);
  if (!/^https?:\/\//.test(u)) return null;
  let hote = u;
  try { hote = new URL(u).hostname.replace(/^www\./, ''); } catch (_e) { /* on garde l'URL */ }
  return el('a', { class: 'porteurs__source', href: u, target: '_blank', rel: 'noopener noreferrer', title: u },
    hote, el('span', { 'aria-hidden': 'true' }, ' ↗'));
}

function ligneFiche(libelle, brut) {
  const c = champFiche(brut);
  const conf = CONFIANCES[c.confiance];
  return el('tr', {},
    el('th', { scope: 'row' }, libelle),
    el('td', { class: ['porteurs__valeur', c.ok ? null : 'porteurs__manquant'] }, c.texte),
    el('td', { class: 'porteurs__confiance' },
      c.ok ? el('span', { class: ['porteurs__conf', 'porteurs__conf--' + c.confiance], title: conf.libelle },
        el('span', { 'aria-hidden': 'true' }, conf.glyphe),
        el('span', { class: 'visuellement-cache' }, conf.libelle)) : null,
      c.ok && c.source ? lienSource(c.source) : null));
}

function tableFiche(titre, champs, valeurs) {
  const source = objet(valeurs);
  const renseignes = champs.filter(([cle]) => champFiche(source[cle]).ok).length;
  return el('div', { class: 'porteurs__groupe' },
    el('div', { class: 'porteurs__groupe-tete' },
      el('h4', { class: 'porteurs__groupe-titre' }, titre),
      el('span', { class: 'porteurs__groupe-compte mono' }, renseignes + ' / ' + champs.length)),
    el('table', { class: 'porteurs__table' },
      el('tbody', {}, champs.map(([cle, libelle]) => ligneFiche(libelle, source[cle])))));
}

function panneauInsolite(fiche) {
  const faits = (Array.isArray(fiche.insolites) ? fiche.insolites : []).filter((f) => f && texte(f.texte));
  if (!faits.length) return el('p', { class: 'texte-doux sans-marge' }, 'Aucun fait remarquable renseigné.');
  return el('ul', { class: 'porteurs__insolites' }, faits.map((f) => el('li', { class: 'porteurs__insolite' },
    el('span', { class: 'porteurs__insolite-glyphe', 'aria-hidden': 'true' }, '✦'),
    el('span', {}, texte(f.texte), ' ', lienSource(f.source)))));
}

function panneauSources(fiche) {
  const liste = (Array.isArray(fiche.sources) ? fiche.sources : []).map(texte).filter((u) => /^https?:\/\//.test(u));
  if (!liste.length) return el('p', { class: 'texte-doux sans-marge' }, 'Aucune source enregistrée.');
  return el('div', { class: 'pile pile--serree' },
    el('p', { class: 'texte-doux texte-sm sans-marge' },
      'Sources publiques consultées pour cette fiche. Légende de confiance : ',
      el('span', { class: 'mono' }, '●'), ' confirmée, ', el('span', { class: 'mono' }, '◐'), ' non recoupée, ',
      el('span', { class: 'mono' }, '○'), ' à vérifier.'),
    el('ul', { class: 'porteurs__sources' }, liste.map((u) => el('li', {}, lienSource(u), ' ',
      el('span', { class: 'texte-faible texte-xs mono' }, u.length > 80 ? u.slice(0, 77) + '…' : u)))));
}

function tableau(titre, descripteurs, valeurs) {
  const source = objet(valeurs);
  const lignes = descripteurs.length ? descripteurs
    : Object.keys(source).map((cle) => ({ cle, libelle: cle, unite: '' }));
  if (!lignes.length) {
    return el('div', { class: 'porteurs__groupe' },
      el('h4', { class: 'porteurs__groupe-titre' }, titre),
      el('p', { class: 'texte-doux texte-sm sans-marge' }, 'Aucun champ déclaré.'));
  }
  const renseignees = lignes.filter((d) => valeurLisible(source[d.cle], d.unite).ok).length;
  return el('div', { class: 'porteurs__groupe' },
    el('div', { class: 'porteurs__groupe-tete' },
      el('h4', { class: 'porteurs__groupe-titre' }, titre),
      el('span', { class: 'porteurs__groupe-compte mono' }, renseignees + ' / ' + lignes.length)),
    el('table', { class: 'porteurs__table' },
      el('tbody', {}, lignes.map((d) => {
        const v = valeurLisible(source[d.cle], d.unite);
        return el('tr', {},
          el('th', { scope: 'row' }, d.libelle),
          el('td', { class: ['mono', v.ok ? null : 'porteurs__manquant'] }, v.texte));
      }))));
}

function panneauService(appareil, donnees) {
  const service = objet(appareil.service);
  const technique = ('technique' in service) ? service.technique : appareil.technique;
  const economique = ('economique' in service) ? service.economique : appareil.economique;
  return el('div', { class: 'pile' },
    el('p', { class: 'texte-doux texte-sm sans-marge mesure' },
      'Les données propres au service (harnais, connecteurs, charge, coûts) ne sont jamais '
      + 'inventées : elles restent « à renseigner » tant que le fichier ne les donne pas.'),
    el('div', { class: 'porteurs__groupes' },
      tableau('Données techniques du service', champs(donnees, 'technique'), technique),
      tableau('Données économiques du service', champs(donnees, 'economique'), economique)));
}

function onglets(prefixe, panneaux) {
  const boutons = panneaux.map((p, i) => el('button', {
    type: 'button', class: 'onglets__onglet', role: 'tab', id: prefixe + '-onglet-' + p.cle,
    'aria-selected': i === 0 ? 'true' : 'false', 'aria-controls': prefixe + '-panneau-' + p.cle,
    tabIndex: i === 0 ? 0 : -1, dataset: { onglet: p.cle }
  }, p.titre, p.compte !== undefined ? el('span', { class: 'pastille' }, String(p.compte)) : null));
  const zones = panneaux.map((p, i) => el('div', {
    class: 'onglets__panneau', role: 'tabpanel', id: prefixe + '-panneau-' + p.cle,
    'aria-labelledby': prefixe + '-onglet-' + p.cle, hidden: i !== 0, tabIndex: 0
  }, p.contenu));
  const liste = el('div', { class: 'onglets__liste', role: 'tablist', 'aria-label': 'Rubriques de la fiche' }, boutons);
  const racine = el('div', { class: 'onglets porteurs__onglets' }, liste, zones);
  const activer = (cle, focus) => {
    boutons.forEach((b) => {
      const actif = b.dataset.onglet === cle;
      b.setAttribute('aria-selected', actif ? 'true' : 'false');
      b.tabIndex = actif ? 0 : -1;
      if (actif && focus) b.focus();
    });
    zones.forEach((z) => { z.hidden = z.id !== prefixe + '-panneau-' + cle; });
  };
  liste.addEventListener('click', (evt) => {
    const b = evt.target.closest('[data-onglet]');
    if (b) activer(b.dataset.onglet, false);
  });
  liste.addEventListener('keydown', (evt) => {
    const i = boutons.indexOf(document.activeElement);
    if (i === -1) return;
    let j = i;
    if (evt.key === 'ArrowRight') j = (i + 1) % boutons.length;
    else if (evt.key === 'ArrowLeft') j = (i - 1 + boutons.length) % boutons.length;
    else if (evt.key === 'Home') j = 0;
    else if (evt.key === 'End') j = boutons.length - 1;
    else return;
    evt.preventDefault();
    activer(boutons[j].dataset.onglet, true);
  });
  return racine;
}

function detail(appareil, donnees, categoriesConnues) {
  const code = texte(appareil.code) || '—';
  const fiche = objet(appareil.fiche);
  const avecFiche = Object.keys(fiche).length > 0;
  const photo = texte(appareil.photo);
  const categorie = categoriesConnues.find((c) => c.cle === texte(appareil.categorie));
  const poles = Array.isArray(appareil.poles) ? appareil.poles.map(texte).filter(Boolean) : [];
  const jalon = valeurLisible(appareil.jalon);
  const avancement = valeurLisible(appareil.avancement, '%');
  const prefixe = 'porteur-' + code.toLowerCase().replace(/[^a-z0-9]+/g, '-');

  const identite = objet(fiche.identite);
  const carteIdentite = avecFiche
    ? el('dl', { class: 'porteurs__identite' },
        el('div', {}, el('dt', {}, 'Statut'), el('dd', {}, texte(fiche.statut) || NON_RENSEIGNE)),
        IDENTITE.map(([cle, libelle]) => {
          const c = champFiche(identite[cle]);
          return el('div', {}, el('dt', {}, libelle), el('dd', { class: c.ok ? null : 'porteurs__manquant' }, c.texte));
        }))
    : null;

  const panneaux = ONGLETS.map((o) => {
    if (o.groupes) {
      const groupes = o.groupes.map((g) => GROUPES_FICHE.find((x) => x.cle === g)).filter(Boolean);
      const compte = groupes.reduce((n, g) => n + g.champs.filter(([cle]) => champFiche(objet(fiche[g.cle])[cle]).ok).length, 0);
      return { cle: o.cle, titre: o.titre, compte,
        contenu: avecFiche
          ? el('div', { class: 'porteurs__groupes' }, groupes.map((g) => tableFiche(g.titre, g.champs, fiche[g.cle])))
          : el('p', { class: 'texte-doux sans-marge' }, 'Fiche publique non encore constituée pour ce porteur.') };
    }
    if (o.cle === 'insolite') return { cle: o.cle, titre: o.titre, compte: (Array.isArray(fiche.insolites) ? fiche.insolites.length : 0), contenu: panneauInsolite(fiche) };
    if (o.cle === 'sources') return { cle: o.cle, titre: o.titre, contenu: panneauSources(fiche) };
    return { cle: o.cle, titre: o.titre, contenu: panneauService(appareil, donnees) };
  });

  return el('article', { class: 'porteurs__detail', 'aria-label': 'Fiche ' + code },
    el('div', { class: 'porteurs__colonne-visuel' },
      el('div', { class: 'porteurs__visuel' },
        photo
          ? el('img', { src: photo, alt: 'Photo du ' + code, class: 'porteurs__photo' })
          : el('div', { class: 'porteurs__silhouette' },
              silhouette(texte(appareil.silhouette), { titre: 'Silhouette du ' + code }),
              el('span', { class: 'porteurs__photo-attente' }, 'Photo à venir'))),
      carteIdentite),
    el('div', { class: 'porteurs__contenu' },
      el('div', { class: 'porteurs__entete' },
        el('div', { class: 'pile pile--serree' },
          el('p', { class: 'porteurs__sur-titre sans-marge' },
            categorie ? categorie.libelle : (texte(appareil.categorie) || 'Catégorie ' + NON_RENSEIGNE),
            ' · ', texte(appareil.segment) || texte(fiche.segment) || NON_RENSEIGNE),
          el('h3', { class: 'porteurs__titre sans-marge' }, texte(fiche.nom) || code,
            texte(fiche.ancienNom) ? el('span', { class: 'porteurs__ancien-nom' }, ' ex-' + texte(fiche.ancienNom)) : null)),
        el('div', { class: 'porteurs__poles' },
          poles.length ? poles.map(pastillePole)
            : el('span', { class: 'texte-faible texte-xs' }, 'Pôles ' + NON_RENSEIGNE))),
      texte(fiche.resume) ? el('p', { class: 'porteurs__resume sans-marge' }, texte(fiche.resume)) : null,
      el('dl', { class: 'porteurs__jalon' },
        el('div', {}, el('dt', {}, 'Jalon en cours'), el('dd', { class: jalon.ok ? null : 'porteurs__manquant' }, jalon.texte)),
        el('div', {}, el('dt', {}, 'Avancement'), el('dd', { class: ['mono', avancement.ok ? null : 'porteurs__manquant'] }, avancement.texte))),
      onglets(prefixe, panneaux)));
}

/* -------------------------------------------------------------------------
   Le composant
   ------------------------------------------------------------------------- */

/**
 * @param {object} donnees   contenu de flotte.json
 * @param {{id?: string}} [options]
 * @returns {HTMLElement}
 */
export function porteurs(donnees, options) {
  const opts = options || {};
  const prefixe = texte(opts.id) || 'porteurs';
  const d = objet(donnees);
  const appareils = (Array.isArray(d.flotte) ? d.flotte : []).filter((a) => a && typeof a === 'object' && texte(a.code));
  const cats = categories(d, appareils);

  let categorie = '';
  let courant = appareils[0] || null;

  const zoneDetail = el('div', { class: 'porteurs__zone-detail', 'aria-live': 'polite' });
  const piste = el('ul', { class: 'porteurs__piste', role: 'list' }, appareils.map((a) => fiche(a, prefixe)));
  const compteur = el('span', { class: 'porteurs__compte mono' }, '');

  const puces = el('ul', { class: 'facettes', 'aria-label': 'Filtrer les porteurs par catégorie' },
    [{ cle: '', libelle: 'Tous' }].concat(cats).map((c) => el('li', {},
      el('button', {
        type: 'button', class: 'facette facette--compacte',
        'aria-pressed': c.cle === '' ? 'true' : 'false',
        dataset: { categorie: c.cle }
      }, c.libelle, ' ',
      el('span', { class: 'facette__compteur' },
        String(c.cle ? appareils.filter((a) => texte(a.categorie) === c.cle).length : appareils.length))))));

  const fleche = (sens) => el('button', {
    type: 'button', class: 'bouton bouton--icone bouton--compact porteurs__fleche',
    'aria-label': sens < 0 ? 'Porteurs précédents' : 'Porteurs suivants',
    dataset: { sens: String(sens) }
  }, sens < 0 ? '‹' : '›');

  function visibles() {
    return appareils.filter((a) => !categorie || texte(a.categorie) === categorie);
  }

  function choisir(appareil, defiler) {
    courant = appareil;
    piste.querySelectorAll('.porteurs__fiche').forEach((b) => {
      b.setAttribute('aria-pressed', b.dataset.code === texte(appareil.code) ? 'true' : 'false');
    });
    monter(zoneDetail, detail(appareil, d, cats));
    if (defiler) {
      const b = piste.querySelector('.porteurs__fiche[aria-pressed="true"]');
      if (b && typeof b.scrollIntoView === 'function') b.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
    }
  }

  function filtrer() {
    const liste = visibles();
    piste.querySelectorAll('.porteurs__item').forEach((li) => {
      li.hidden = Boolean(categorie) && li.dataset.categorie !== categorie;
    });
    compteur.textContent = liste.length + (liste.length > 1 ? ' appareils' : ' appareil');
    if (!liste.length) { monter(zoneDetail, el('p', { class: 'texte-doux' }, 'Aucun porteur dans cette catégorie.')); return; }
    if (!courant || !liste.includes(courant)) choisir(liste[0], false); else choisir(courant, false);
  }

  piste.addEventListener('click', (evt) => {
    const b = evt.target.closest('.porteurs__fiche');
    if (!b) return;
    const a = appareils.find((x) => texte(x.code) === b.dataset.code);
    if (a) { choisir(a, false); annoncer('Porteur ' + b.dataset.code); }
  });

  piste.addEventListener('keydown', (evt) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(evt.key)) return;
    const boutons = Array.from(piste.querySelectorAll('.porteurs__item:not([hidden]) .porteurs__fiche'));
    const i = boutons.indexOf(document.activeElement);
    if (i === -1) return;
    let j = i;
    if (evt.key === 'ArrowLeft') j = Math.max(0, i - 1);
    if (evt.key === 'ArrowRight') j = Math.min(boutons.length - 1, i + 1);
    if (evt.key === 'Home') j = 0;
    if (evt.key === 'End') j = boutons.length - 1;
    evt.preventDefault();
    boutons[j].focus(); boutons[j].click();
  });

  puces.addEventListener('click', (evt) => {
    const b = evt.target.closest('[data-categorie]');
    if (!b) return;
    categorie = b.dataset.categorie || '';
    puces.querySelectorAll('[data-categorie]').forEach((x) => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
    filtrer();
  });

  const racine = el('section', { class: 'porteurs', id: prefixe },
    el('div', { class: 'porteurs__barre' }, puces, compteur),
    el('div', { class: 'porteurs__carrousel' },
      fleche(-1),
      el('div', { class: 'porteurs__fenetre' }, piste),
      fleche(1)),
    zoneDetail);

  racine.addEventListener('click', (evt) => {
    const f = evt.target.closest('.porteurs__fleche');
    if (!f) return;
    const liste = visibles();
    const i = liste.indexOf(courant);
    const j = Math.min(liste.length - 1, Math.max(0, i + Number(f.dataset.sens)));
    if (liste[j]) choisir(liste[j], true);
  });

  filtrer();
  return racine;
}

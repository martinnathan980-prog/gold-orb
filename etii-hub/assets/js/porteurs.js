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
    el('span', { class: 'porteurs__fiche-segment' }, texte(appareil.segment) || NON_RENSEIGNE),
    el('span', { class: 'porteurs__fiche-poles', 'aria-label': 'Pôles : ' + (Array.isArray(appareil.poles) ? appareil.poles.join(', ') : '') },
      (Array.isArray(appareil.poles) ? appareil.poles : []).map((p) =>
        el('span', { class: 'porteurs__pole-point', dataset: { pole: texte(p) }, title: 'Pôle ' + texte(p) })))));
}

/* -------------------------------------------------------------------------
   La fiche détaillée
   ------------------------------------------------------------------------- */

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
      el('span', { class: 'porteurs__groupe-compte mono' }, renseignees + ' / ' + lignes.length + ' renseigné' + (renseignees > 1 ? 's' : ''))),
    el('table', { class: 'porteurs__table' },
      el('tbody', {}, lignes.map((d) => {
        const v = valeurLisible(source[d.cle], d.unite);
        return el('tr', {},
          el('th', { scope: 'row' }, d.libelle),
          el('td', { class: ['mono', v.ok ? null : 'porteurs__manquant'] }, v.texte));
      }))));
}

function detail(appareil, donnees, categoriesConnues) {
  const code = texte(appareil.code) || '—';
  const photo = texte(appareil.photo);
  const categorie = categoriesConnues.find((c) => c.cle === texte(appareil.categorie));
  const poles = Array.isArray(appareil.poles) ? appareil.poles.map(texte).filter(Boolean) : [];
  const jalon = valeurLisible(appareil.jalon);
  const avancement = valeurLisible(appareil.avancement, '%');

  return el('article', { class: 'porteurs__detail', 'aria-label': 'Fiche ' + code },
    el('div', { class: 'porteurs__visuel' },
      photo
        ? el('img', { src: photo, alt: 'Photo du ' + code, class: 'porteurs__photo' })
        : el('div', { class: 'porteurs__silhouette' },
            silhouette(texte(appareil.silhouette), { titre: 'Silhouette du ' + code }),
            el('span', { class: 'porteurs__photo-attente' }, 'Photo à venir'))),
    el('div', { class: 'porteurs__contenu' },
      el('div', { class: 'porteurs__entete' },
        el('div', { class: 'pile pile--serree' },
          el('p', { class: 'porteurs__sur-titre sans-marge' },
            categorie ? categorie.libelle : (texte(appareil.categorie) || 'Catégorie ' + NON_RENSEIGNE),
            ' · ', texte(appareil.segment) || NON_RENSEIGNE),
          el('h3', { class: 'porteurs__titre sans-marge' }, code)),
        el('div', { class: 'porteurs__poles' },
          poles.length ? poles.map(pastillePole)
            : el('span', { class: 'texte-faible texte-xs' }, 'Pôles ' + NON_RENSEIGNE))),
      el('dl', { class: 'porteurs__jalon' },
        el('div', {}, el('dt', {}, 'Jalon en cours'), el('dd', { class: jalon.ok ? null : 'porteurs__manquant' }, jalon.texte)),
        el('div', {}, el('dt', {}, 'Avancement'), el('dd', { class: ['mono', avancement.ok ? null : 'porteurs__manquant'] }, avancement.texte))),
      el('div', { class: 'porteurs__groupes' },
        tableau('Données techniques', champs(donnees, 'technique'), appareil.technique),
        tableau('Données économiques', champs(donnees, 'economique'), appareil.economique))));
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

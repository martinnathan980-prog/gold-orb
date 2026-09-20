/* =========================================================================
   ETII Hub — L'arbre d'équipe
   L'organigramme d'un pôle : le responsable en tête, puis les squads en
   volets — fermé, un volet montre le nom de la squad, son lead, une pile
   de visages et l'effectif ; ouvert, toute l'équipe, avatar aux initiales,
   nom, poste, porteur. Une recherche ouvre les volets qui répondent et
   estompe le reste. Avec soixante personnes par pôle, c'est ce qui reste
   lisible d'un coup d'œil.
   ========================================================================= */

import { el } from './ui.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function normaliser(v) { return texte(v).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }

function initiales(nom) {
  const parts = texte(nom).split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  const dernier = parts[parts.length - 1];
  // « Personne 03 » donne P03 : un numéro vaut mieux qu'un chiffre isolé.
  if (parts.length > 1 && /^\d+$/.test(dernier)) return parts[0][0].toUpperCase() + dernier;
  return [parts[0], dernier].slice(0, parts.length > 1 ? 2 : 1).map((p) => p[0].toUpperCase()).join('');
}

function avatar(p) {
  return el('span', { class: 'arbre__avatar', 'aria-hidden': 'true' }, initiales(p && p.nom));
}

function cartePersonne(personne, options) {
  const opts = options || {};
  const p = (personne && typeof personne === 'object') ? personne : {};
  const nom = texte(p.nom) || 'Nom à renseigner';
  const role = texte(p.role);
  const porteur = texte(p.perimetre);
  const recherche = normaliser([p.nom, p.poste, p.perimetre, p.id].map(texte).join(' '));
  return el('div', {
    class: ['arbre__carte', opts.classe || null, role === 'leader' ? 'arbre__carte--lead' : null,
      role === 'responsable' || role === 'direction' ? 'arbre__carte--tete' : null],
    dataset: { recherche, id: texte(p.id) }
  },
  avatar(p),
  el('span', { class: 'arbre__infos' },
    el('span', { class: 'arbre__nom' }, nom),
    el('span', { class: 'arbre__poste' }, texte(p.poste) || 'Poste à renseigner'),
    porteur ? el('span', { class: 'arbre__porteur' }, porteur) : null),
  role === 'leader' ? el('span', { class: 'badge badge--accent arbre__etiquette' }, 'Lead') : null,
  texte(p.id) ? el('span', { class: 'arbre__id mono' }, texte(p.id).toUpperCase()) : null);
}

function pile(membres, max) {
  const visibles = membres.slice(0, max);
  const reste = membres.length - visibles.length;
  return el('span', { class: 'arbre__pile', 'aria-hidden': 'true' },
    visibles.map(avatar),
    reste > 0 ? el('span', { class: 'arbre__pile-reste' }, '+' + reste) : null);
}

function voletSquad(squad, rang) {
  const s = (squad && typeof squad === 'object') ? squad : {};
  const membres = (Array.isArray(s.membres) ? s.membres : []).filter((m) => m && typeof m === 'object');
  const leads = membres.filter((m) => texte(m.role) === 'leader');
  const autres = membres.filter((m) => texte(m.role) !== 'leader');
  const nom = texte(s.nom) || 'Squad ' + (rang + 1);
  return el('details', { class: 'arbre__squad', dataset: { squad: nom } },
    el('summary', { class: 'arbre__squad-tete' },
      el('span', { class: 'arbre__squad-chevron', 'aria-hidden': 'true' }),
      el('span', { class: 'arbre__squad-infos' },
        el('span', { class: 'arbre__squad-nom' }, nom),
        el('span', { class: 'arbre__squad-lead' }, leads.length ? 'Lead : ' + texte(leads[0].nom) : 'Lead à renseigner')),
      pile(leads.concat(autres), 5),
      el('span', { class: 'arbre__squad-compte mono' }, membres.length + ' pers.')),
    el('div', { class: 'arbre__membres' },
      leads.map((m) => cartePersonne(m)),
      autres.map((m) => cartePersonne(m)),
      membres.length ? null : el('p', { class: 'texte-doux texte-sm sans-marge' }, 'Aucun membre déclaré.')));
}

/**
 * @param {object} bloc  entrée de organigramme.json pour un pôle : { pole, responsable, squads }
 * @param {{id?: string}} [options]
 * @returns {HTMLElement}
 */
export function arbreEquipe(bloc, options) {
  const opts = options || {};
  const prefixe = texte(opts.id) || 'arbre';
  const b = (bloc && typeof bloc === 'object') ? bloc : {};
  const squads = Array.isArray(b.squads) ? b.squads : [];
  const responsable = (b.responsable && typeof b.responsable === 'object') ? b.responsable : null;
  const effectif = squads.reduce((n, s) => n + (Array.isArray(s && s.membres) ? s.membres.length : 0), 0) + (responsable ? 1 : 0);

  const champ = el('input', {
    type: 'search', class: 'arbre__recherche', id: prefixe + '-recherche',
    placeholder: 'Rechercher un nom, un poste, un porteur…', autocomplete: 'off'
  });
  const resultat = el('span', { class: 'arbre__resultat mono' }, '');
  const bascule = el('button', { type: 'button', class: 'bouton bouton--secondaire bouton--compact', 'aria-pressed': 'false' }, 'Tout déplier');

  const corps = el('div', { class: 'arbre__corps' },
    responsable
      ? el('div', { class: 'arbre__tete' }, cartePersonne(Object.assign({ role: 'responsable' }, responsable)))
      : el('p', { class: 'texte-doux sans-marge' }, 'Aucun responsable déclaré pour ce pôle.'),
    squads.length
      ? el('div', { class: 'arbre__squads' }, squads.map(voletSquad))
      : el('p', { class: 'texte-doux sans-marge' }, 'Aucune squad rattachée à ce pôle.'));

  const volets = () => Array.from(corps.querySelectorAll('.arbre__squad'));

  champ.addEventListener('input', () => {
    const q = normaliser(champ.value);
    const cartes = Array.from(corps.querySelectorAll('.arbre__carte'));
    let n = 0;
    cartes.forEach((c) => {
      const ok = !q || c.dataset.recherche.includes(q);
      c.classList.toggle('arbre__carte--estompee', !ok);
      if (ok) n += 1;
    });
    resultat.textContent = q ? n + ' / ' + cartes.length : '';
    volets().forEach((v) => {
      const visibles = v.querySelectorAll('.arbre__carte:not(.arbre__carte--estompee)').length;
      v.classList.toggle('arbre__squad--estompee', Boolean(q) && visibles === 0);
      /* Une recherche ouvre les volets qui répondent ; l'effacer les
         referme, sauf si l'utilisateur a demandé « tout déplier ». */
      if (q) v.open = visibles > 0;
      else if (bascule.getAttribute('aria-pressed') !== 'true') v.open = false;
    });
  });

  bascule.addEventListener('click', () => {
    const ouvrir = bascule.getAttribute('aria-pressed') !== 'true';
    bascule.setAttribute('aria-pressed', ouvrir ? 'true' : 'false');
    bascule.textContent = ouvrir ? 'Tout replier' : 'Tout déplier';
    volets().forEach((v) => { v.open = ouvrir; });
  });

  return el('section', { class: 'arbre', id: prefixe },
    el('div', { class: 'arbre__dock' },
      el('label', { class: 'visuellement-cache', for: champ.id }, 'Rechercher dans l’équipe'),
      champ,
      resultat,
      bascule,
      el('span', { class: 'arbre__effectif' },
        el('span', { class: 'badge badge--neutre' }, effectif + (effectif > 1 ? ' personnes' : ' personne')),
        el('span', { class: 'badge badge--neutre badge--contour' }, squads.length + (squads.length > 1 ? ' squads' : ' squad')))),
    corps);
}

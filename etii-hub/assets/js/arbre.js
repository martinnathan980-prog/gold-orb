/* =========================================================================
   ETII Hub — L'arbre d'équipe
   L'organigramme d'un pôle, comme l'« Équipe définition électrique »
   d'origine : le responsable en tête, un trait vers chaque squad, la squad
   avec son lead en premier, puis ses membres — avatar aux initiales, nom,
   poste, porteur. Une recherche estompe tout ce qui ne correspond pas.
   ========================================================================= */

import { el, monter } from './ui.js';

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
  el('span', { class: 'arbre__avatar', 'aria-hidden': 'true' }, initiales(p.nom)),
  el('span', { class: 'arbre__infos' },
    el('span', { class: 'arbre__nom' }, nom),
    el('span', { class: 'arbre__poste' }, texte(p.poste) || 'Poste à renseigner'),
    porteur ? el('span', { class: 'arbre__porteur' }, porteur) : null),
  role === 'leader' ? el('span', { class: 'badge badge--accent arbre__etiquette' }, 'Lead') : null,
  texte(p.id) ? el('span', { class: 'arbre__id mono' }, texte(p.id).toUpperCase()) : null);
}

function carteSquad(squad, rang) {
  const s = (squad && typeof squad === 'object') ? squad : {};
  const membres = (Array.isArray(s.membres) ? s.membres : []).filter((m) => m && typeof m === 'object');
  const leads = membres.filter((m) => texte(m.role) === 'leader');
  const autres = membres.filter((m) => texte(m.role) !== 'leader');
  return el('li', { class: 'arbre__squad' },
    el('div', { class: 'arbre__squad-titre' },
      el('span', { class: 'arbre__squad-point', 'aria-hidden': 'true' }),
      el('span', {}, texte(s.nom) || 'Squad ' + (rang + 1)),
      el('span', { class: 'arbre__squad-compte mono' }, membres.length + (membres.length > 1 ? ' pers.' : ' pers.'))),
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

  const corps = el('div', { class: 'arbre__corps' },
    responsable
      ? el('div', { class: 'arbre__tete' }, cartePersonne(Object.assign({ role: 'responsable' }, responsable)))
      : el('p', { class: 'texte-doux sans-marge' }, 'Aucun responsable déclaré pour ce pôle.'),
    squads.length
      ? el('ul', { class: 'arbre__squads', role: 'list' }, squads.map(carteSquad))
      : el('p', { class: 'texte-doux sans-marge' }, 'Aucune squad rattachée à ce pôle.'));

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
    corps.querySelectorAll('.arbre__squad').forEach((s) => {
      const visibles = s.querySelectorAll('.arbre__carte:not(.arbre__carte--estompee)').length;
      s.classList.toggle('arbre__squad--estompee', Boolean(q) && visibles === 0);
    });
  });

  return el('section', { class: 'arbre', id: prefixe },
    el('div', { class: 'arbre__dock' },
      el('label', { class: 'visuellement-cache', for: champ.id }, 'Rechercher dans l’équipe'),
      champ,
      resultat,
      el('span', { class: 'arbre__effectif' },
        el('span', { class: 'badge badge--neutre' }, effectif + (effectif > 1 ? ' personnes' : ' personne')),
        el('span', { class: 'badge badge--neutre badge--contour' }, squads.length + (squads.length > 1 ? ' squads' : ' squad')))),
    corps);
}

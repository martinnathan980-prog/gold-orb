/* =========================================================================
   ETII Hub — « À venir » : les prochains rendez-vous du service

   Le Communication center raconte ce qui s'est passé ; ce bloc dit ce qui
   arrive. Les rendez-vous sont les entrées d'agenda de
   communications.json dont la date n'est pas passée, de la plus proche à
   la plus lointaine : un jalon, une revue, un atelier, une formation.
   Chaque carte dit quand (le jour en grand, puis « dans 3 jours »), quoi,
   pour qui (le service ou un pôle), où, et en deux lignes ce qui s'y
   joue.

   En mode édition (edition.js), chaque carte se modifie ou se retire, et
   un bouton en ajoute une. Un rendez-vous passé quitte le bloc de
   lui-même, le lendemain.

   API :
     agenda(donnees, options)  -> HTMLElement
       options.pole            'ETII' (tout le service) ou un code de pôle
       options.limite          nombre de cartes au plus (défaut 6)
       options.surAjouter(b), options.surModifier(entree, b), options.surSupprimer(entree)
   ========================================================================= */

import { el } from './ui.js';
import { joursRestants, TYPES_AGENDA } from './kiosque.js';
import { barreEdition, boutonAjouter } from './edition.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const JOURS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];

/* « aujourd'hui », « demain », « dans 5 jours », « dans 3 semaines ». */
function echeance(n) {
  if (n === null) return '';
  if (n <= 0) return 'aujourd’hui';
  if (n === 1) return 'demain';
  if (n < 14) return 'dans ' + n + ' jours';
  if (n < 60) return 'dans ' + Math.round(n / 7) + ' semaines';
  return 'dans ' + Math.round(n / 30) + ' mois';
}

function carte(entree, options) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(texte(entree.date));
  const date = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
  const n = joursRestants(entree.date);
  const pole = texte(entree.pole).toUpperCase() || 'ETII';
  const type = TYPES_AGENDA[texte(entree.type)] || texte(entree.type) || 'Rendez-vous';
  return el('li', { class: ['agenda__rdv', n !== null && n <= 7 ? 'agenda__rdv--proche' : null], dataset: { pole } },
    el('div', { class: 'agenda__date', 'aria-hidden': 'true' },
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
        el('span', { class: 'visuellement-cache' }, date ? JOURS[date.getDay()] + ' ' + date.getDate() + ' ' + MOIS[date.getMonth()] + ' : ' : ''),
        texte(entree.titre)),
      texte(entree.resume) ? el('p', { class: 'agenda__resume' }, texte(entree.resume)) : null,
      texte(entree.lieu) ? el('p', { class: 'agenda__lieu' }, el('span', { 'aria-hidden': 'true' }, '⌖ '), texte(entree.lieu)) : null),
    (typeof options.surModifier === 'function' || typeof options.surSupprimer === 'function')
      ? barreEdition({
          classe: 'agenda__edition',
          quoi: texte(entree.titre),
          surModifier: typeof options.surModifier === 'function' ? (b) => options.surModifier(entree, b) : null,
          surSupprimer: typeof options.surSupprimer === 'function' ? () => options.surSupprimer(entree) : null
        })
      : null);
}

/**
 * Les prochains rendez-vous.
 * @param {object} donnees  communications.json (modifié)
 * @param {object} [options]
 * @returns {HTMLElement}
 */
export function agenda(donnees, options) {
  const o = options || {};
  const pole = texte(o.pole).toUpperCase() || 'ETII';
  const limite = Number(o.limite) > 0 ? Number(o.limite) : 6;
  const entrees = (Array.isArray(donnees && donnees.agenda) ? donnees.agenda : [])
    .filter((e) => e && typeof e === 'object' && texte(e.titre) && texte(e.type) !== 'mot')
    .filter((e) => { const n = joursRestants(e.date); return n !== null && n >= 0; })
    .filter((e) => pole === 'ETII' || texte(e.pole).toUpperCase() === pole || texte(e.pole).toUpperCase() === 'ETII')
    .sort((a, b) => texte(a.date).localeCompare(texte(b.date)));
  const visibles = entrees.slice(0, limite);
  return el('div', { class: 'agenda' },
    visibles.length
      ? el('ol', { class: 'agenda__liste', role: 'list' }, visibles.map((e) => carte(e, o)))
      : el('p', { class: 'agenda__vide' }, 'Aucun rendez-vous à venir pour le moment.'),
    entrees.length > visibles.length
      ? el('p', { class: 'agenda__suite' }, 'Et ' + (entrees.length - visibles.length) + ' autre' + (entrees.length - visibles.length > 1 ? 's' : '') + ' plus tard.')
      : null,
    typeof o.surAjouter === 'function' ? boutonAjouter('Ajouter un rendez-vous', o.surAjouter) : null);
}

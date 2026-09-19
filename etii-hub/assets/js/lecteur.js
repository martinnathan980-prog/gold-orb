/* =========================================================================
   ETII Hub — Le lecteur : une liste à gauche, la lecture à droite
   Le motif du « Hub Réunions » et de la « FAQ » d'origine : un panneau de
   liste avec sa recherche, un panneau de lecture qui affiche l'élément
   choisi. Clavier complet (↑ ↓ Origine Fin dans la liste), recherche par
   score (début de titre, puis titre, puis corps), fondu à la sélection.
   ========================================================================= */

import { el, monter, annoncer } from './ui.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

function normaliser(v) {
  return texte(v).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

/**
 * @param {object} options
 * @param {string} options.id
 * @param {Array<object>} options.elements  { id, titre, meta?, groupe?, badges?: [{texte, classe}], recherche?: string[], corps: () => Node }
 * @param {Array<{cle:string, titre:string}>} [options.groupes]
 * @param {string} [options.titreListe]
 * @param {string} [options.placeholder]
 * @param {string} [options.vide]
 * @param {(item:object) => Node} [options.entete]   contenu placé en tête de la lecture (badges, date…)
 * @param {(item:object) => Node} [options.actions]  boutons de la barre d'actions
 * @param {Node} [options.pied]                      bloc fixe sous la lecture
 * @returns {HTMLElement}
 */
export function lecteur(options) {
  const opts = options || {};
  const prefixe = texte(opts.id) || 'lecteur';
  const elements = (Array.isArray(opts.elements) ? opts.elements : []).filter((e) => e && texte(e.id));
  const groupes = Array.isArray(opts.groupes) ? opts.groupes : [];
  let courant = null;
  let requete = '';

  const champ = el('input', {
    type: 'search', class: 'lecteur__recherche', id: prefixe + '-recherche',
    placeholder: texte(opts.placeholder) || 'Rechercher…', autocomplete: 'off'
  });
  const zoneListe = el('div', { class: 'lecteur__defile', tabIndex: 0 });
  const compteur = el('span', { class: 'lecteur__compte mono' }, '');

  const titreLecture = el('h3', { class: 'lecteur__titre', id: prefixe + '-titre' }, '');
  const enteteLecture = el('div', { class: 'lecteur__entete' });
  const corpsLecture = el('div', { class: 'lecteur__corps' });
  const actionsLecture = el('div', { class: 'lecteur__actions' });
  const lecture = el('div', { class: 'lecteur__lecture' }, enteteLecture, titreLecture, corpsLecture);

  const panneauLecture = el('article', {
    class: 'lecteur__panneau lecteur__panneau--lecture', 'aria-labelledby': titreLecture.id, tabIndex: -1
  }, actionsLecture, lecture, opts.pied || null);

  function score(item) {
    if (!requete) return 1;
    const q = normaliser(requete);
    const titre = normaliser(item.titre);
    if (titre.startsWith(q)) return 4;
    if (titre.includes(q)) return 3;
    const champs = Array.isArray(item.recherche) ? item.recherche : [];
    if (champs.some((c) => normaliser(c).includes(q))) return 1;
    return 0;
  }

  function classes() {
    return elements
      .map((item) => ({ item, s: score(item) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .map((x) => x.item);
  }

  function bouton(item) {
    return el('li', { class: 'lecteur__entree' },
      el('button', {
        type: 'button', class: 'lecteur__item', dataset: { id: item.id },
        id: prefixe + '-item-' + item.id, 'aria-current': 'false'
      },
      el('span', { class: 'lecteur__item-titre' }, item.titre || 'Sans titre'),
      item.meta ? el('span', { class: 'lecteur__item-meta' }, item.meta) : null,
      Array.isArray(item.badges) && item.badges.length
        ? el('span', { class: 'lecteur__item-badges' },
            item.badges.map((b) => el('span', { class: ['badge', b.classe || 'badge--neutre'] }, b.texte)))
        : null));
  }

  function lire(item) {
    courant = item;
    zoneListe.querySelectorAll('.lecteur__item').forEach((b) => {
      b.setAttribute('aria-current', b.dataset.id === item.id ? 'true' : 'false');
    });
    lecture.classList.add('lecteur__lecture--fondu');
    const appliquer = () => {
      titreLecture.textContent = item.titre || 'Sans titre';
      monter(enteteLecture, typeof opts.entete === 'function' ? opts.entete(item) : null);
      monter(corpsLecture, typeof item.corps === 'function' ? item.corps() : (item.corps || null));
      monter(actionsLecture, typeof opts.actions === 'function' ? opts.actions(item) : null);
      actionsLecture.hidden = !actionsLecture.childNodes.length;
      panneauLecture.scrollTo({ top: 0 });
      lecture.classList.remove('lecteur__lecture--fondu');
    };
    setTimeout(appliquer, 120);
  }

  function rendreListe() {
    const liste = requete ? classes() : elements;
    compteur.textContent = String(liste.length);
    if (!liste.length) {
      monter(zoneListe, el('p', { class: 'lecteur__vide' }, requete ? 'Aucun élément ne correspond.' : (texte(opts.vide) || 'Rien à lire pour le moment.')));
      return;
    }
    const enfants = [];
    if (groupes.length && !requete) {
      for (const g of groupes) {
        const membres = liste.filter((i) => i.groupe === g.cle);
        if (!membres.length) continue;
        enfants.push(el('li', { class: 'lecteur__groupe', role: 'presentation' },
          el('span', {}, g.titre), el('span', { class: 'mono' }, String(membres.length))));
        membres.forEach((m) => enfants.push(bouton(m)));
      }
      liste.filter((i) => !groupes.some((g) => g.cle === i.groupe)).forEach((m) => enfants.push(bouton(m)));
    } else {
      liste.forEach((m) => enfants.push(bouton(m)));
    }
    monter(zoneListe, el('ol', { class: 'lecteur__liste', role: 'list' }, enfants));
    const cible = liste.find((i) => courant && i.id === courant.id) || liste[0];
    if (cible && (!courant || cible.id !== courant.id || !titreLecture.textContent)) lire(cible);
    else if (courant) {
      zoneListe.querySelectorAll('.lecteur__item').forEach((b) => {
        b.setAttribute('aria-current', b.dataset.id === courant.id ? 'true' : 'false');
      });
    }
  }

  champ.addEventListener('input', () => { requete = champ.value; rendreListe(); });

  zoneListe.addEventListener('click', (evt) => {
    const b = evt.target.closest('.lecteur__item');
    if (!b) return;
    const item = elements.find((i) => i.id === b.dataset.id);
    if (item) { lire(item); annoncer(item.titre); }
  });

  zoneListe.addEventListener('keydown', (evt) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(evt.key)) return;
    const boutons = Array.from(zoneListe.querySelectorAll('.lecteur__item'));
    if (!boutons.length) return;
    const i = boutons.indexOf(document.activeElement);
    let j = i === -1 ? 0 : i;
    if (evt.key === 'ArrowDown') j = Math.min(boutons.length - 1, j + 1);
    if (evt.key === 'ArrowUp') j = Math.max(0, j - 1);
    if (evt.key === 'Home') j = 0;
    if (evt.key === 'End') j = boutons.length - 1;
    evt.preventDefault();
    boutons[j].focus(); boutons[j].click();
  });

  const racine = el('div', { class: 'lecteur', id: prefixe },
    el('aside', { class: 'lecteur__panneau lecteur__panneau--liste', 'aria-label': texte(opts.titreListe) || 'Liste' },
      el('div', { class: 'lecteur__liste-tete' },
        el('span', { class: 'lecteur__liste-titre' }, texte(opts.titreListe) || 'Liste', ' ', compteur),
        el('label', { class: 'visuellement-cache', for: champ.id }, texte(opts.placeholder) || 'Rechercher'),
        champ),
      zoneListe),
    panneauLecture);

  rendreListe();
  return racine;
}

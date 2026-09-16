/* =========================================================================
   Sélecteur de direction visuelle — TEMPORAIRE
   Applique une des trois propositions au site entier et laisse en changer
   depuis n'importe quelle page. Le choix est mémorisé localement.

   Ce module, la feuille directions.css et la barre qu'il pose disparaîtront
   une fois la direction retenue promue dans tokens.css.
   ========================================================================= */

import { el, monter, stockage } from './ui.js';

const CLE = 'etii.direction';

const DIRECTIONS = [
  { cle: 'a', nom: 'Atelier',    resume: 'Anthracite chaud, laiton, lumière rasante' },
  { cle: 'b', nom: 'Hangar',     resume: 'Papier chaud, aplats de bleu, très grande typo' },
  { cle: 'c', nom: 'Nuit bleue', resume: 'Bleu de nuit, blanc, une touche chaude' },
];

const DEFAUT = 'a';

function appliquer(cle) {
  const valide = DIRECTIONS.some((d) => d.cle === cle) ? cle : DEFAUT;
  document.documentElement.setAttribute('data-direction', valide);
  stockage.ecrire(CLE, valide);
  return valide;
}

/** Applique le choix mémorisé — appelé au plus tôt, avant tout rendu. */
export function initDirection() {
  return appliquer(stockage.lire(CLE, DEFAUT));
}

/** Pose la barre de choix en tête de page. */
export function barreDirection() {
  const courante = document.documentElement.getAttribute('data-direction') || DEFAUT;

  const boutons = DIRECTIONS.map((d) => el('li', null,
    el('button', {
      type: 'button',
      class: 'facette',
      ariaPressed: d.cle === courante ? 'true' : 'false',
      dataset: { direction: d.cle },
      title: d.resume
    },
    el('span', { class: 'facette__marque', ariaHidden: 'true' }, '✓'),
    `${d.nom}`)));

  const liste = el('ul', { class: 'choix-direction__liste' }, ...boutons);

  const barre = el('div', { class: 'choix-direction' },
    el('p', { class: 'choix-direction__titre' }, 'Direction visuelle à l’essai'),
    el('p', { class: 'choix-direction__aide' },
      'Trois propositions sur le site réel. Le choix suit d’une page à l’autre.'),
    liste);

  liste.addEventListener('click', (evt) => {
    const bouton = evt.target.closest('button[data-direction]');
    if (!bouton) return;
    const choisie = appliquer(bouton.dataset.direction);
    for (const b of liste.querySelectorAll('button[data-direction]')) {
      b.setAttribute('aria-pressed', b.dataset.direction === choisie ? 'true' : 'false');
    }
  });

  document.body.insertBefore(barre, document.body.firstChild);
  return barre;
}

initDirection();
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', barreDirection, { once: true });
} else {
  barreDirection();
}

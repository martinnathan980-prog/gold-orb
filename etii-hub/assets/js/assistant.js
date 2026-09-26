/* =========================================================================
   ETII Hub — L'assistant documentaire

   La recherche trouve LE document ; l'assistant dit CE QUE dit le
   document. Il vit sur sa propre page : une petite application web
   Apps Script (tools/apps-script/assistant/) qui s'exécute au nom de la
   personne qui l'ouvre et interroge Gemini Enterprise avec SES droits —
   chacun ne reçoit que des passages de documents qu'il peut ouvrir.

   Ce bloc n'appelle rien lui-même : il ouvre cette page, la question déjà
   posée (?q=…). Une requête faite d'ici ne pourrait pas porter la
   connexion Google de la personne, et le navigateur ne doit jamais voir
   ni clé ni jeton.

   Tant que SOURCE.url est vide, le bloc explique qu'il n'est pas
   raccordé : pas d'exemple, pas de simulation, rien qui puisse passer
   pour une réponse du service.
   Mode d'emploi complet : docs/ASSISTANT-IA.md
   ========================================================================= */

import { el } from './ui.js';

/* -------------------------------------------------------------------------
   LE POINT DE RACCORDEMENT — la seule chose à modifier en production
   ------------------------------------------------------------------------- */

/* Ce dépôt est public. Ne collez rien ici : renseignez la copie locale,
   puis ne commitez ni ce fichier ni le dist/ fabriqué depuis lui.
   tests/audit.mjs refuse une URL de raccordement commitée ; sur une copie
   raccordée, lancez ETII_RACCORDE=1 node tests/audit.mjs. */
export const SOURCE = {
  /* URL /exec de l'application web « Assistant documentaire ETII ».
     Vide : l'assistant reste annoncé comme non raccordé. */
  url: '',
  /* Nom affiché de la source, pour que chacun sache ce qui répond. */
  libelle: 'Gemini · documents ETII'
};

const LIMITE_QUESTION = 2000;

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

/** L'assistant est-il raccordé ? */
export function raccorde() {
  return texte(SOURCE.url) !== '';
}

/**
 * L'adresse de la page de l'assistant, la question en paramètre.
 * @param {string} question
 * @returns {string}  vide si l'assistant n'est pas raccordé
 */
export function adresseQuestion(question) {
  const base = texte(SOURCE.url);
  if (!base) return '';
  const q = texte(question).slice(0, LIMITE_QUESTION);
  if (!q) return base;
  return base + (base.indexOf('?') === -1 ? '?' : '&') + 'q=' + encodeURIComponent(q);
}

/* -------------------------------------------------------------------------
   L'interface
   ------------------------------------------------------------------------- */

/**
 * Un lien « Demander à Gemini ↗ » qui pose la question du moment, lue au
 * dernier instant (survol, focus, clic) : posé à côté des résultats, il
 * suit la barre de recherche sans être reconstruit à chaque frappe.
 * @param {() => string} lireQuestion
 * @param {string} [classe]
 * @returns {HTMLElement|null}  null tant que l'assistant n'est pas raccordé
 */
export function lienDemander(lireQuestion, classe) {
  if (!raccorde()) return null;
  const lien = el('a', { class: classe || 'bouton bouton--principal', href: adresseQuestion(''),
    target: '_blank', rel: 'noopener noreferrer',
    title: 'Poser cette question à Gemini, sur les documents du service' }, 'Demander à Gemini ↗');
  const actualiser = () => { lien.href = adresseQuestion(lireQuestion()); };
  ['focus', 'pointerenter', 'pointerdown', 'click'].forEach((type) => lien.addEventListener(type, actualiser));
  return lien;
}

function encadreNonRaccorde() {
  return el('div', { class: 'assistant assistant--attente' },
    el('div', { class: 'assistant__tete' },
      el('span', { class: 'badge badge--neutre' }, 'Pas encore raccordé'),
      el('h3', { class: 'assistant__titre sans-marge' }, 'Demander à Gemini ce que disent les documents')),
    el('p', { class: 'assistant__texte sans-marge' },
      'La recherche ci-dessus trouve ', el('em', {}, 'le'), ' document. Cette section répondra à '
      + '« que dit le document ? » : une réponse en français, tirée des documents du service que vous '
      + 'avez le droit de lire, avec les documents cités.'),
    el('p', { class: 'assistant__texte texte-sm sans-marge' },
      'En attendant : ouvrez un document depuis la recherche, puis « Demander à Gemini » dans Google Drive. '
      + 'Le branchement se fait en un seul point — ',
      el('span', { class: 'mono' }, 'SOURCE.url'), ' dans ', el('span', { class: 'mono' }, 'assets/js/assistant.js'),
      '. La marche à suivre complète est dans ',
      el('span', { class: 'mono' }, 'docs/ASSISTANT-IA.md'), '.'));
}

/**
 * Construit le bloc de l'assistant : une question, envoyée à sa page.
 * Le champ reprend ce qui est tapé dans la barre de recherche tant que la
 * personne n'y a pas écrit elle-même.
 * @param {{requete?: string|(() => string)}} [options]
 * @returns {HTMLElement}
 */
export function blocAssistant(options) {
  if (!raccorde()) return encadreNonRaccorde();
  const opts = options || {};
  const requete = () => texte(typeof opts.requete === 'function' ? opts.requete() : opts.requete);

  const champ = el('textarea', { class: 'assistant__champ', id: 'assistant-question', rows: 2,
    placeholder: 'Posez votre question en une phrase…', maxLength: LIMITE_QUESTION });
  const question = () => texte(champ.value) || requete();

  const lien = lienDemander(question);
  const actualiser = () => {
    if (!texte(champ.value)) champ.placeholder = requete() || 'Posez votre question en une phrase…';
    lien.href = adresseQuestion(question());
  };
  champ.addEventListener('focus', actualiser);
  champ.addEventListener('input', actualiser);
  champ.addEventListener('keydown', (evt) => {
    if (evt.key === 'Enter' && (evt.ctrlKey || evt.metaKey)) { evt.preventDefault(); actualiser(); lien.click(); }
  });

  return el('div', { class: 'assistant' },
    el('div', { class: 'assistant__tete' },
      el('span', { class: 'badge badge--accent' }, SOURCE.libelle),
      el('h3', { class: 'assistant__titre sans-marge' }, 'Demander à Gemini ce que disent les documents')),
    el('div', { class: 'assistant__saisie' },
      el('label', { class: 'visuellement-cache', for: 'assistant-question' }, 'Votre question'),
      champ, lien),
    el('p', { class: 'assistant__texte texte-xs sans-marge' },
      'La réponse s’ouvre dans un nouvel onglet, avec les documents cités. Gemini ne lit que ce que '
      + 'vous avez le droit d’ouvrir. Vérifiez dans le document avant d’appliquer une règle. ',
      el('kbd', {}, 'Ctrl'), ' + ', el('kbd', {}, 'Entrée'), ' pour envoyer.'));
}

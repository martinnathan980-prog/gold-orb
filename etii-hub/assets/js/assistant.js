/* =========================================================================
   ETII Hub — L'assistant documentaire

   La recherche trouve LE document par sa fiche (titre, référence,
   mots-clés). L'assistant va plus loin : il cherche dans le TEXTE des
   documents du Drive partagé et, selon le niveau installé, fait dire à
   Gemini ce qu'ils contiennent. Il vit sur sa propre page : une petite
   application web Apps Script (tools/apps-script/assistant/) qui
   s'exécute au nom de la personne qui l'ouvre — chacun ne reçoit que des
   documents qu'il peut ouvrir.

   Ce bloc n'appelle rien lui-même : il ouvre cette page, la demande déjà
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
  /* Le niveau installé (docs/ASSISTANT-IA.md), qui choisit les libellés :
       1 — chercher dans le texte des documents, sans IA payante ;
       2 — Gemini lit les documents trouvés (Agent Platform, à l'usage) ;
       3 — Gemini Enterprise. */
  niveau: 1,
  /* Le libellé du lien vers l'assistant, si celui du niveau ne convient
     pas. Vide : celui du niveau (« Chercher dans le texte des documents ↗ »
     au niveau 1, « Demander à Gemini ↗ » aux niveaux 2 et 3). */
  action: ''
};

/* Ce que le bloc dit de lui-même à chaque niveau : le nom de ce qui
   répond (badge), ce que fait le lien posé seul à côté des résultats
   (action), le bouton du bloc — court, sous un titre qui dit déjà tout —
   et ce qu'il faut en attendre. */
const NIVEAUX = {
  1: {
    badge: 'Drive partagé · texte intégral',
    titre: 'Chercher dans le texte des documents',
    action: 'Chercher dans le texte des documents ↗',
    bouton: 'Chercher ↗',
    infobulle: 'Chercher ces mots dans le texte des documents du Drive partagé',
    exemple: 'Des mots, une valeur, une référence…',
    aide: 'Les documents qui contiennent ces mots s’ouvrent dans un nouvel onglet, avec un extrait. '
      + 'Vous ne voyez que ce que vous avez le droit d’ouvrir. '
  },
  2: {
    badge: 'Gemini · documents ETII',
    titre: 'Demander à Gemini ce que disent les documents',
    action: 'Demander à Gemini ↗',
    bouton: 'Demander ↗',
    infobulle: 'Poser cette question à Gemini, sur les documents du service',
    exemple: 'Posez votre question en une phrase…',
    aide: 'La réponse s’ouvre dans un nouvel onglet, rédigée à partir des documents trouvés, qui sont cités. '
      + 'Gemini ne lit que ce que vous avez le droit d’ouvrir. Vérifiez dans le document avant d’appliquer une règle. '
  },
  3: {
    badge: 'Gemini Enterprise · documents ETII',
    titre: 'Demander à Gemini ce que disent les documents',
    action: 'Demander à Gemini ↗',
    bouton: 'Demander ↗',
    infobulle: 'Poser cette question à Gemini, sur les documents du service',
    exemple: 'Posez votre question en une phrase…',
    aide: 'La réponse s’ouvre dans un nouvel onglet, avec les documents cités. Gemini ne lit que ce que '
      + 'vous avez le droit d’ouvrir. Vérifiez dans le document avant d’appliquer une règle. '
  }
};

const LIMITE_QUESTION = 2000;

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

/** L'assistant est-il raccordé ? */
export function raccorde() {
  return texte(SOURCE.url) !== '';
}

/**
 * Les libellés du niveau installé ; un niveau inconnu vaut le niveau 1,
 * SOURCE.action remplace le libellé du lien et celui du bouton du bloc.
 * @returns {{badge:string, titre:string, action:string, bouton:string, infobulle:string, exemple:string, aide:string}}
 */
export function libelles() {
  const n = NIVEAUX[Number(SOURCE.niveau)] || NIVEAUX[1];
  const propre = texte(SOURCE.action);
  return Object.assign({}, n, propre ? { action: propre, bouton: propre } : {});
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
 * Le lien vers l'assistant (« Chercher dans le texte des documents ↗ » au
 * niveau 1), qui emporte la demande du moment, lue au dernier instant
 * (survol, focus, clic) : posé à côté des résultats, il suit la barre de
 * recherche sans être reconstruit à chaque frappe.
 * @param {() => string} lireQuestion
 * @param {string} [classe]
 * @returns {HTMLElement|null}  null tant que l'assistant n'est pas raccordé
 */
export function lienDemander(lireQuestion, classe) {
  if (!raccorde()) return null;
  const l = libelles();
  const lien = el('a', { class: classe || 'bouton bouton--principal', href: adresseQuestion(''),
    target: '_blank', rel: 'noopener noreferrer', title: l.infobulle }, l.action);
  const actualiser = () => { lien.href = adresseQuestion(lireQuestion()); };
  ['focus', 'pointerenter', 'pointerdown', 'click'].forEach((type) => lien.addEventListener(type, actualiser));
  return lien;
}

function encadreNonRaccorde() {
  return el('div', { class: 'assistant assistant--attente' },
    el('div', { class: 'assistant__tete' },
      el('span', { class: 'badge badge--neutre' }, 'Pas encore raccordé'),
      el('h3', { class: 'assistant__titre sans-marge' }, libelles().titre)),
    el('p', { class: 'assistant__texte sans-marge' },
      'La recherche ci-dessus lit les fiches du catalogue : titre, référence, mots-clés. Une fois '
      + 'raccordée, cette section cherchera aussi dans le ', el('em', {}, 'texte'), ' des documents du '
      + 'Drive partagé — une valeur, une règle, une référence citée —, avec vos droits Google : '
      + 'chacun ne voit que ce qu’il peut ouvrir.'),
    el('p', { class: 'assistant__texte texte-sm sans-marge' },
      'Dès aujourd’hui : ouvrez un document avec « Ouvrir ↗ », puis « Demander à Gemini » — l’étoile, '
      + 'en haut à droite de Google Drive — pour qu’il le résume ou réponde sur ce document. '
      + 'Le raccordement se fait en un seul point, ',
      el('span', { class: 'mono' }, 'SOURCE.url'), ' dans ', el('span', { class: 'mono' }, 'assets/js/assistant.js'),
      ' ; la marche à suivre est dans ',
      el('span', { class: 'mono' }, 'docs/ASSISTANT-IA.md'), ', niveau 1.'));
}

/**
 * Construit le bloc de l'assistant : une demande, envoyée à sa page.
 * Le champ reprend ce qui est tapé dans la barre de recherche tant que la
 * personne n'y a pas écrit elle-même.
 * @param {{requete?: string|(() => string)}} [options]
 * @returns {HTMLElement}
 */
export function blocAssistant(options) {
  if (!raccorde()) return encadreNonRaccorde();
  const opts = options || {};
  const l = libelles();
  const requete = () => texte(typeof opts.requete === 'function' ? opts.requete() : opts.requete);

  const champ = el('textarea', { class: 'assistant__champ', id: 'assistant-question', rows: 2,
    placeholder: l.exemple, maxLength: LIMITE_QUESTION });
  const question = () => texte(champ.value) || requete();

  const lien = lienDemander(question);
  lien.textContent = l.bouton;
  const actualiser = () => {
    if (!texte(champ.value)) champ.placeholder = requete() || l.exemple;
    lien.href = adresseQuestion(question());
  };
  champ.addEventListener('focus', actualiser);
  champ.addEventListener('input', actualiser);
  champ.addEventListener('keydown', (evt) => {
    if (evt.key === 'Enter' && (evt.ctrlKey || evt.metaKey)) { evt.preventDefault(); actualiser(); lien.click(); }
  });

  return el('div', { class: 'assistant' },
    el('div', { class: 'assistant__tete' },
      el('span', { class: 'badge badge--accent' }, l.badge),
      el('h3', { class: 'assistant__titre sans-marge' }, l.titre)),
    el('div', { class: 'assistant__saisie' },
      el('label', { class: 'visuellement-cache', for: 'assistant-question' }, 'Votre demande'),
      champ, lien),
    el('p', { class: 'assistant__texte texte-xs sans-marge' },
      l.aide, el('kbd', {}, 'Ctrl'), ' + ', el('kbd', {}, 'Entrée'), ' pour envoyer.'));
}

/* =========================================================================
   ETII Hub — L'assistant documentaire

   La recherche trouve LE document ; l'assistant dit CE QUE dit le
   document. Il pose la question à un intermédiaire (Apps Script ou Cloud
   Run) qui détient la clé API et interroge le fonds indexé — jamais le
   navigateur, qui ne doit jamais voir une clé.

   Tant que SOURCE.url est vide, le bloc explique qu'il n'est pas
   raccordé et n'affiche AUCUNE réponse : pas d'exemple, pas de
   simulation, rien qui puisse passer pour une réponse du service.
   Mode d'emploi complet : docs/ASSISTANT-IA.md
   ========================================================================= */

import { el, monter, annoncer } from './ui.js';

/* -------------------------------------------------------------------------
   LE POINT DE RACCORDEMENT — la seule chose à modifier en production
   ------------------------------------------------------------------------- */

/* Ce dépôt est public. Ne collez rien ici : renseignez la copie locale,
   puis ne commitez ni ce fichier ni le dist/ fabriqué depuis lui.
   tests/audit.mjs refuse une URL de raccordement commitée ; sur une copie
   raccordée, lancez ETII_RACCORDE=1 node tests/audit.mjs. */
export const SOURCE = {
  /* URL /exec de l'application web Apps Script (ou du service Cloud Run).
     Elle reçoit { question } en POST et renvoie { reponse, citations }.
     Vide : l'assistant reste annoncé comme non raccordé. */
  url: '',
  /* Nom affiché de la source, pour que chacun sache ce qui répond. */
  libelle: 'Fonds documentaire ETII'
};

const LIMITE_QUESTION = 2000;

/* Délai maximal d'un envoi : un appel de modèle passé par Apps Script
   dépasse facilement huit secondes. Sans borne du tout, un intermédiaire
   muet laisse le bouton « Demander » désactivé et le message d'attente
   affichés pour toujours — la promesse ne se règle jamais. */
const DELAI_ENVOI = 30000;

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

/**
 * fetch() borné dans le temps. Le délai est levé dès l'arrivée des en-têtes ;
 * un corps qui se bloque ensuite n'est pas couvert — cas bien plus rare,
 * assumé.
 * @param {string} url
 * @param {object} [options] options de fetch(), plus `delai` en millisecondes
 * @returns {Promise<Response>}
 */
async function recupererReponse(url, options) {
  const opt = options || {};
  const delai = typeof opt.delai === 'number' ? opt.delai : DELAI_ENVOI;
  const controleur = typeof AbortController === 'function' ? new AbortController() : null;
  let expire = false;
  const minuteur = controleur && delai > 0
    ? setTimeout(() => { expire = true; controleur.abort(); }, delai)
    : null;
  try {
    return await fetch(url, Object.assign({}, opt, {
      delai: undefined,
      signal: controleur ? controleur.signal : undefined
    }));
  } catch (cause) {
    throw new Error(expire
      ? 'délai de ' + Math.round(delai / 1000) + ' s dépassé'
      : 'réseau injoignable');
  } finally {
    if (minuteur !== null) clearTimeout(minuteur);
  }
}

/** L'assistant est-il raccordé ? */
export function raccorde() {
  return texte(SOURCE.url) !== '';
}

/**
 * Pose une question à l'intermédiaire.
 * @param {string} question
 * @returns {Promise<{reponse:string, citations:Array<{titre:string, extrait:string}>}>}
 */
export async function demander(question) {
  const q = texte(question);
  if (!q) throw new Error('La question est vide.');
  if (q.length > LIMITE_QUESTION) throw new Error('La question dépasse ' + LIMITE_QUESTION + ' caractères.');
  if (!raccorde()) throw new Error('Aucune source n’est raccordée.');

  const reponse = await recupererReponse(SOURCE.url, {
    method: 'POST',
    /* text/plain : évite la requête préalable CORS, qu'Apps Script ne
       traite pas. Le corps reste du JSON, lu tel quel côté script. */
    headers: { 'Content-Type': 'text/plain;charset=utf-8' },
    body: JSON.stringify({ question: q }),
    delai: DELAI_ENVOI
  });
  if (!reponse.ok) throw new Error('L’assistant a répondu ' + reponse.status + '.');

  const donnees = await reponse.json();
  if (donnees && donnees.erreur) throw new Error(donnees.erreur);
  return {
    reponse: texte(donnees && donnees.reponse),
    citations: (donnees && Array.isArray(donnees.citations) ? donnees.citations : [])
      .map((c) => ({ titre: texte(c && c.titre), extrait: texte(c && c.extrait) }))
      .filter((c) => c.titre)
  };
}

/* -------------------------------------------------------------------------
   L'interface
   ------------------------------------------------------------------------- */

function encadreNonRaccorde() {
  return el('div', { class: 'assistant assistant--attente' },
    el('div', { class: 'assistant__tete' },
      el('span', { class: 'badge badge--neutre' }, 'Pas encore raccordé'),
      el('h3', { class: 'assistant__titre sans-marge' }, 'Poser une question au fonds documentaire')),
    el('p', { class: 'assistant__texte sans-marge' },
      'La recherche ci-dessus trouve ', el('em', {}, 'le'), ' document. Cette section répondra à '
      + '« que dit le document ? » — une réponse en français, tirée des documents du service, '
      + 'avec la référence et le passage d’origine.'),
    el('p', { class: 'assistant__texte texte-sm sans-marge' },
      'Elle n’affichera jamais de réponse tant qu’elle n’est pas raccordée à une source réelle : '
      + 'aucun exemple, aucune simulation. Le branchement se fait en un seul point — ',
      el('span', { class: 'mono' }, 'SOURCE.url'), ' dans ', el('span', { class: 'mono' }, 'assets/js/assistant.js'),
      '. La marche à suivre complète, les interlocuteurs à contacter et les précautions sont dans ',
      el('span', { class: 'mono' }, 'docs/ASSISTANT-IA.md'), '.'));
}

function citation(c) {
  return el('li', { class: 'assistant__citation' },
    el('span', { class: 'assistant__citation-titre' }, c.titre),
    c.extrait ? el('span', { class: 'assistant__citation-extrait' }, '« ' + c.extrait + ' »') : null);
}

/**
 * Construit le bloc de l'assistant : question, réponse, citations.
 * @param {{requete?: string}} [options]  question pré-remplie
 * @returns {HTMLElement}
 */
export function blocAssistant(options) {
  if (!raccorde()) return encadreNonRaccorde();
  const opts = options || {};

  const champ = el('textarea', { class: 'assistant__champ', id: 'assistant-question', rows: 2,
    placeholder: 'Posez votre question en une phrase…', maxLength: LIMITE_QUESTION });
  champ.value = texte(opts.requete);

  const bouton = el('button', { type: 'button', class: 'bouton bouton--principal' }, 'Demander');
  const zone = el('div', { class: 'assistant__reponse', role: 'status', 'aria-live': 'polite' });

  const poser = () => {
    const q = texte(champ.value);
    if (!q) { champ.focus(); return; }
    bouton.disabled = true;
    monter(zone, el('p', { class: 'assistant__attente sans-marge' }, 'Lecture du fonds documentaire…'));
    demander(q).then((r) => {
      monter(zone,
        r.reponse
          ? el('div', { class: 'assistant__texte-reponse' }, r.reponse)
          : el('p', { class: 'assistant__texte sans-marge' }, 'L’assistant n’a rien renvoyé.'),
        r.citations.length
          ? el('div', { class: 'assistant__sources' },
              el('p', { class: 'assistant__sources-titre sans-marge' }, 'Documents cités'),
              el('ul', { class: 'assistant__citations' }, r.citations.map(citation)))
          : el('p', { class: 'assistant__sans-source sans-marge' },
              el('span', { class: 'badge badge--alerte' }, 'Sans citation'),
              ' Aucun document n’a été cité : cette réponse n’est pas vérifiable, ne vous en servez pas telle quelle.'));
      annoncer('Réponse de l’assistant affichée.');
    }).catch((err) => {
      monter(zone, el('p', { class: 'assistant__erreur sans-marge' },
        'L’assistant n’a pas pu répondre : ' + (err && err.message ? err.message : 'erreur inconnue') + '.'));
    }).then(() => { bouton.disabled = false; });
  };

  bouton.addEventListener('click', poser);
  champ.addEventListener('keydown', (evt) => {
    if (evt.key === 'Enter' && (evt.ctrlKey || evt.metaKey)) { evt.preventDefault(); poser(); }
  });

  return el('div', { class: 'assistant' },
    el('div', { class: 'assistant__tete' },
      el('span', { class: 'badge badge--accent' }, SOURCE.libelle),
      el('h3', { class: 'assistant__titre sans-marge' }, 'Poser une question au fonds documentaire')),
    el('div', { class: 'assistant__saisie' },
      el('label', { class: 'visuellement-cache', for: 'assistant-question' }, 'Votre question'),
      champ, bouton),
    el('p', { class: 'assistant__texte texte-xs sans-marge' },
      'Réponse tirée des documents indexés, avec leur référence. Une réponse sans citation '
      + 'n’est pas vérifiable : recoupez-la avant de l’utiliser. ',
      el('kbd', {}, 'Ctrl'), ' + ', el('kbd', {}, 'Entrée'), ' pour envoyer.'),
    zone);
}

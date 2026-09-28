/* =========================================================================
   ETII Hub — Demander à Gemini

   La recherche trouve OÙ est un document ; Gemini dit CE QU'IL CONTIENT.
   Sans Vertex AI ni Gemini Enterprise, et sans l'aide de l'informatique,
   la voie qui marche est celle de Google Workspace lui-même : un carnet
   Gemini Notebook (l'ancien NotebookLM) par thème ou par pôle, rempli
   des documents validés du service (jusqu'à 300 par carnet dans les
   éditions Business et Enterprise), partagé à l'équipe. Gemini y répond
   en citant ses sources, avec le compte Google de chacun.

   Ce bloc relie la recherche à ces carnets :
     1. la question se tape ici (elle reprend celle de la barre) ;
     2. « Copier la question et ouvrir le carnet » la copie, puis ouvre
        le carnet choisi dans un nouvel onglet ;
     3. on la colle (Ctrl + V), Entrée : la réponse arrive, sources à
        l'appui.
   Aucun carnet ne se pré-remplit par son adresse : la copie fait le pont.
   Si un carnet est aussi relié à un formulaire (Workspace Studio : un
   flux « réponse à un formulaire › Ask Gemini Notebook › e-mail »), un
   second bouton ouvre ce formulaire, la question déjà écrite, et la
   réponse arrive par e-mail.

   Les liens des carnets se règlent DANS LE SITE (mode édition), dans le
   jeu « reglages » : rien n'est écrit dans ce dépôt public, aucune clé,
   aucune adresse interne. Le site n'envoie rien à Gemini lui-même.

   Mode d'emploi : docs/ASSISTANT-IA.md.

   API :
     blocGemini({ carnets, requete, pole, edition }) -> HTMLElement
       carnets   la liste des carnets (reglages.json, modifié)
       requete   () => la question de la barre de recherche
       pole      le pôle à proposer d'abord ('ETII' par défaut)
       edition   { surAjouter(b), surModifier(carnet, b), surSupprimer(carnet) }
                 en mode édition, sinon null
   ========================================================================= */

import { el, monter, toast, annoncer } from './ui.js';
import { barreEdition, boutonAjouter } from './edition.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
const HTTPS = /^https:\/\/\S+$/i;

let compteur = 0;

/* Les carnets utilisables : un nom, un lien https. */
function carnetsValides(carnets) {
  return (Array.isArray(carnets) ? carnets : [])
    .filter((c) => c && typeof c === 'object' && texte(c.libelle) && HTTPS.test(texte(c.lien)));
}

/* Copie synchrone, dans le geste même : la sélection du champ et la
   commande de copie marchent aussi dans le cadre d'Apps Script, où
   l'API presse-papiers peut être refusée. L'API sert de second essai. */
function copierDepuis(champ) {
  let ok = false;
  try {
    champ.focus({ preventScroll: true });
    champ.select();
    ok = document.execCommand('copy');
  } catch (_e) { ok = false; }
  if (!ok && typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    navigator.clipboard.writeText(champ.value).catch(() => {});
  }
  return ok;
}

/**
 * Le bloc « Demander à Gemini ».
 * @param {object} o
 * @returns {HTMLElement}
 */
export function blocGemini(o) {
  const opts = o || {};
  compteur += 1;
  const id = 'gemini-' + compteur;
  const carnets = carnetsValides(opts.carnets);
  const edition = opts.edition || null;
  const requete = typeof opts.requete === 'function' ? opts.requete : () => '';
  const polePrefere = texte(opts.pole).toUpperCase() || 'ETII';

  /* La question : celle de la barre, tant qu'on n'a pas écrit ici. */
  let touchee = false;
  const champ = el('textarea', {
    class: 'champ__controle gemini__question', id: id + '-question', rows: 2,
    placeholder: 'Ex. : quelle distance minimale entre un harnais de puissance et un harnais de signal ?',
    onInput: () => { touchee = true; majBoutons(); }
  });
  const synchroniser = () => {
    if (touchee) return;
    const q = texte(requete());
    if (champ.value !== q) champ.value = q;
    majBoutons();
  };

  /* Le carnet choisi : le premier du pôle préféré, sinon le premier. */
  let choisi = carnets.find((c) => texte(c.pole).toUpperCase() === polePrefere) || carnets[0] || null;
  const zoneCarnets = el('div', { class: 'gemini__carnets', role: 'radiogroup', 'aria-label': 'Carnet à interroger' });
  const ouvrir = el('a', {
    class: 'bouton bouton--principal gemini__ouvrir', target: '_blank', rel: 'noopener noreferrer',
    onClick: (evt) => {
      const q = champ.value.trim();
      if (!q || !choisi) { evt.preventDefault(); champ.focus(); annoncer('Écrivez d’abord votre question.'); return; }
      const copie = copierDepuis(champ);
      toast(copie
        ? 'Question copiée : collez-la dans le carnet (Ctrl + V), puis Entrée.'
        : 'Le carnet s’ouvre : copiez la question ci-dessus (Ctrl + C) et collez-la dedans.', copie ? 'succes' : 'info');
    }
  }, 'Copier la question et ouvrir le carnet', el('span', { 'aria-hidden': 'true' }, ' ↗'));
  const parEmail = el('a', {
    class: 'bouton bouton--secondaire gemini__email', target: '_blank', rel: 'noopener noreferrer', hidden: true,
    onClick: (evt) => { if (!champ.value.trim()) { evt.preventDefault(); champ.focus(); } }
  }, 'Recevoir la réponse par e-mail', el('span', { 'aria-hidden': 'true' }, ' ↗'));

  function majBoutons() {
    const q = champ.value.trim();
    const lien = choisi ? texte(choisi.lien) : '';
    ouvrir.href = lien || '#';
    ouvrir.setAttribute('aria-disabled', q && lien ? 'false' : 'true');
    const formulaire = choisi ? texte(choisi.formulaire) : '';
    parEmail.hidden = !HTTPS.test(formulaire);
    if (!parEmail.hidden) {
      parEmail.href = /XYZ/.test(formulaire) ? formulaire.replace('XYZ', encodeURIComponent(q)) : formulaire;
      parEmail.setAttribute('aria-disabled', q ? 'false' : 'true');
    }
  }

  function rendreCarnets() {
    monter(zoneCarnets, carnets.map((c) => {
      const actif = c === choisi;
      const pole = texte(c.pole).toUpperCase() || 'ETII';
      return el('span', { class: 'gemini__carnet-cadre' },
        el('button', {
          type: 'button', role: 'radio', class: 'gemini__carnet', dataset: { pole },
          'aria-checked': actif ? 'true' : 'false', tabIndex: actif ? 0 : -1,
          onClick: () => { choisi = c; rendreCarnets(); majBoutons(); }
        },
        el('span', { class: 'gemini__carnet-point', 'aria-hidden': 'true' }),
        el('span', { class: 'gemini__carnet-nom' }, texte(c.libelle)),
        el('span', { class: 'gemini__carnet-pole' }, pole === 'ETII' ? 'Service' : pole)),
        edition ? barreEdition({
          classe: 'barre-edition--compacte gemini__carnet-edition', quoi: texte(c.libelle),
          surModifier: (b) => edition.surModifier(c, b), surSupprimer: () => edition.surSupprimer(c)
        }) : null);
    }));
  }
  /* Les flèches passent d'un carnet à l'autre, comme dans un groupe radio. */
  zoneCarnets.addEventListener('keydown', (evt) => {
    const pas = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[evt.key];
    if (!pas || !carnets.length) return;
    evt.preventDefault();
    const i = Math.max(0, carnets.indexOf(choisi));
    choisi = carnets[(i + pas + carnets.length) % carnets.length];
    rendreCarnets(); majBoutons();
    const b = zoneCarnets.querySelector('[aria-checked="true"]');
    if (b) b.focus();
  });

  rendreCarnets();
  synchroniser();

  const tete = el('div', { class: 'gemini__tete' },
    el('p', { class: 'gemini__surtitre' }, el('span', { class: 'gemini__eclat', 'aria-hidden': 'true' }, '✦'), 'Demander à Gemini'),
    el('h2', { class: 'gemini__titre', id: id + '-titre' }, 'Une question sur le contenu des documents ?'),
    el('p', { class: 'gemini__intro' },
      'Gemini lit le carnet choisi — les documents validés du service — et répond en citant ses sources, avec votre compte Google.'));

  const corps = carnets.length
    ? [
      el('label', { class: 'visuellement-cache', for: champ.id }, 'Votre question'),
      champ,
      zoneCarnets,
      el('div', { class: 'gemini__actions' }, ouvrir, parEmail),
      el('ol', { class: 'gemini__etapes' },
        el('li', {}, 'La question est copiée.'),
        el('li', {}, 'Le carnet s’ouvre dans un nouvel onglet.'),
        el('li', {}, 'Collez (Ctrl + V), Entrée : la réponse arrive, sources à l’appui.'))
    ]
    : [
      el('p', { class: 'gemini__vide' },
        'Aucun carnet n’est encore relié à la recherche. ',
        edition
          ? 'Créez le carnet du pôle dans Gemini Notebook, puis reliez-le ici.'
          : 'Un éditeur du site peut relier le carnet de chaque pôle (bouton « ✎ Modifier »).'),
      el('p', { class: 'gemini__vide gemini__vide--astuce' },
        'En attendant : posez votre question dans la barre de recherche de Google Drive — Gemini y répond au-dessus des résultats, en citant les fichiers.')
    ];

  const racine = el('section', { class: 'gemini', 'aria-labelledby': id + '-titre' },
    tete,
    el('div', { class: 'gemini__corps' }, corps),
    edition ? el('div', { class: 'gemini__edition' }, boutonAjouter('Relier un carnet', (b) => edition.surAjouter(b))) : null,
    el('p', { class: 'gemini__garde' },
      'Un carnet copie ses documents hors de Drive : on n’y met que des documents validés, jamais de document sous contrôle export.'));
  /* La barre de recherche change : la question suit, tant qu'on ne l'a
     pas réécrite ici. */
  racine.synchroniser = synchroniser;
  return racine;
}

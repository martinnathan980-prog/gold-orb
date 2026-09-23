/* =========================================================================
   ETII Hub — Le journal des modifications

   Chaque geste fait dans le site (ajouter, modifier, supprimer) se raconte
   en une ligne lisible : la rubrique (Communication center, À venir,
   Porteurs, Organigramme, Documents…), le pôle, l'action, l'élément, et
   ce qui a changé — « Date : « 2 oct. » → « 9 oct. » ». Le récit est
   écrit ici, au moment de l'enregistrement, parce que c'est le site qui
   connaît l'élément avant et après ; le magasin le range (magasin.js) :
   dans la feuille Google (un onglet par rubrique), dans la base du lien
   publié, ou dans ce navigateur.

   L'Historique (bouton du bandeau d'édition) le relit : les gestes les
   plus récents d'abord, groupés par jour, filtrables par rubrique.

   API :
     rubriqueDe(jeu, type)                       -> string
     resumerModification({ jeu, type, id, op, avant, apres })
                                                 -> { rubrique, action, element, pole, detail }
     differences(avant, apres)                   -> string (une ligne par champ changé)
     ouvrirHistorique(declencheur)               ouvre la fenêtre de l'historique
   ========================================================================= */

import { el, monter, ouvrirModale } from './ui.js';
import { ouvrirMagasin } from './magasin.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function objet(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : null; }

/* -------------------------------------------------------------------------
   1. Les rubriques : les mêmes que les onglets de la feuille (Code.gs)
   ------------------------------------------------------------------------- */

const RUBRIQUES = {
  communications: { annonce: 'Communication center', edito: 'Communication center', alerte: 'Communication center', agenda: 'À venir' },
  flotte: { porteur: 'Porteurs' },
  organigramme: { personne: 'Organigramme', squad: 'Organigramme' },
  documents: { document: 'Documents' },
  faq: { question: 'Questions fréquentes' },
  reunions: { 'compte-rendu': 'Réunions' }
};

export const ORDRE_RUBRIQUES = ['Communication center', 'À venir', 'Porteurs', 'Organigramme', 'Documents', 'Questions fréquentes', 'Réunions'];

export function rubriqueDe(jeu, type) {
  return (RUBRIQUES[jeu] && RUBRIQUES[jeu][type]) || 'Autres';
}

/* -------------------------------------------------------------------------
   2. Le récit d'une modification
   ------------------------------------------------------------------------- */

/* Un élément se nomme par son titre, son nom, sa question ou son code ; un
   type qui ne se reconnaît pas à son seul nom est précisé. */
const PRECISIONS = { alerte: 'Alerte', edito: 'Mot du chef', squad: 'Squad' };

function tronquer(t, n) { return t.length > n ? t.slice(0, n - 1) + '…' : t; }

function nommer(type, element, id) {
  const o = objet(element) || {};
  const nom = texte(o.titre) || texte(o.nom) || texte(o.question) || texte(o.code) || texte(o.texte) || texte(id);
  return (PRECISIONS[type] ? PRECISIONS[type] + ' : ' : '') + tronquer(nom, 140);
}

function poleDe(element) {
  const o = objet(element) || {};
  const v = o.poles !== undefined ? o.poles : o.pole;
  return (Array.isArray(v) ? v : [v]).map(texte).filter(Boolean).join(', ');
}

/* Les noms des champs, en français. Les autres se lisent depuis leur clé :
   « vitesseCroisiere » devient « vitesse croisiere ». */
const NOMS = {
  titre: 'Titre', date: 'Date', resume: 'Résumé', lieu: 'Lieu', pole: 'Pôle', poles: 'Pôles', type: 'Type',
  texte: 'Texte', jusqua: 'Jusqu’au', nom: 'Nom', role: 'Rôle', squad: 'Squad', competences: 'Compétences',
  niveau: 'Niveau', lien: 'Lien', reference: 'Référence', description: 'Description', motsCles: 'Mots-clés',
  maj: 'Mise à jour', metier: 'Métier', perimetre: 'Périmètre', porteur: 'Porteur', question: 'Question',
  reponse: 'Réponse', categorie: 'Catégorie', segment: 'Segment', statut: 'Statut', photo: 'Photo',
  credit: 'Crédit', auteur: 'Auteur', licence: 'Licence', insolites: 'Le saviez-vous', blocs: 'Bloc',
  code: 'Code', unite: 'unité', perimetres: 'Périmètres', remplacePar: 'Remplacé par', rang: 'Rang',
  image: 'Image', src: 'Adresse', alt: 'Description de l’image', chiffres: 'Chiffres', valeur: 'Valeur',
  libelle: 'Libellé', tendance: 'Tendance', items: 'Points', identite: 'Identité', motorisation: 'Motorisation',
  masses: 'Masses', capacite: 'Capacité', dimensions: 'Dimensions', performances: 'Performances',
  production: 'Production', electrique: 'Électrique', ancienNom: 'Ancien nom', participants: 'Participants',
  decisions: 'Décisions', actions: 'Actions', responsable: 'Responsable', echeance: 'Échéance'
};

/* Les champs de travail du site, et ceux qu'il réécrit seul, ne se
   racontent pas. */
const MUETS = new Set(['id', 'relecture', 'confiance', 'source', 'sources', 'le', 'par', 'typeSource']);

function nomChamp(chemin) {
  const morceaux = chemin.split('.').filter((m) => m !== 'fiche' && m !== 'valeur');
  return morceaux.map((m, i) => {
    if (/^\d+$/.test(m)) return String(Number(m) + 1);
    const nom = NOMS[m] || m.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();
    return i === 0 ? nom.charAt(0).toUpperCase() + nom.slice(1) : nom;
  }).join(' › ') || 'Valeur';
}

/* L'élément à plat : un chemin par valeur simple. Une liste de mots
   (pôles, métiers) se lit d'un bloc ; une liste d'objets (les blocs d'une
   communication), élément par élément. */
function aplatir(valeur, chemin, sortie) {
  if (valeur === null || valeur === undefined || valeur === '') return;
  if (Array.isArray(valeur)) {
    if (valeur.every((v) => v === null || typeof v !== 'object')) {
      const t = valeur.map(texte).filter(Boolean).join(', ');
      if (t) sortie.set(chemin, t);
      return;
    }
    valeur.forEach((v, i) => aplatir(v, chemin ? chemin + '.' + i : String(i), sortie));
    return;
  }
  if (typeof valeur === 'object') {
    for (const [cle, v] of Object.entries(valeur)) {
      if (cle.startsWith('__') || MUETS.has(cle)) continue;
      aplatir(v, chemin ? chemin + '.' + cle : cle, sortie);
    }
    return;
  }
  const t = texte(valeur);
  if (t) sortie.set(chemin, t);
}

function citer(v) { return v ? '« ' + tronquer(v.replace(/\s+/g, ' '), 90) + ' »' : '(vide)'; }

const LIGNES_MAX = 12;

/** Ce qui a changé entre deux versions d'un élément, une ligne par champ. */
export function differences(avant, apres) {
  const a = new Map();
  const b = new Map();
  aplatir(avant, '', a);
  aplatir(apres, '', b);
  const chemins = [...new Set([...a.keys(), ...b.keys()])].filter((c) => (a.get(c) || '') !== (b.get(c) || ''));
  const lignes = chemins.slice(0, LIGNES_MAX).map((c) => nomChamp(c) + ' : ' + citer(a.get(c)) + ' → ' + citer(b.get(c)));
  if (chemins.length > LIGNES_MAX) {
    const reste = chemins.length - LIGNES_MAX;
    lignes.push('… et ' + reste + ' autre' + (reste > 1 ? 's' : '') + ' champ' + (reste > 1 ? 's' : ''));
  }
  return lignes.join('\n');
}

/* Un ajout se résume par ses premiers champs remplis (le nom est déjà dans
   « Élément »). */
function apercu(element) {
  const plat = new Map();
  aplatir(element, '', plat);
  const lignes = [...plat.entries()]
    .filter(([c]) => !['titre', 'nom', 'question', 'code'].includes(c))
    .slice(0, 6)
    .map(([c, v]) => nomChamp(c) + ' : ' + citer(v));
  return lignes.join('\n');
}

/**
 * Le récit d'une modification, pour le journal.
 * @param {{jeu: string, type: string, id: string, op: 'maj'|'suppr', avant: ?object, apres: ?object}} m
 */
export function resumerModification(m) {
  const avant = objet(m.avant);
  const apres = objet(m.apres);
  const action = m.op === 'suppr' ? 'Suppression' : (avant ? 'Modification' : 'Ajout');
  let detail = '';
  if (action === 'Modification') detail = differences(avant, apres) || 'Aucun champ changé.';
  else if (action === 'Ajout') detail = apercu(apres);
  return {
    rubrique: rubriqueDe(m.jeu, m.type),
    action,
    element: nommer(m.type, apres || avant, m.id),
    pole: poleDe(apres || avant),
    detail
  };
}

/* -------------------------------------------------------------------------
   3. L'Historique : la fenêtre du bandeau d'édition
   ------------------------------------------------------------------------- */

const JOURS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];

function jourDe(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Date inconnue';
  return JOURS[d.getDay()] + ' ' + d.getDate() + ' ' + MOIS[d.getMonth()] + ' ' + d.getFullYear();
}

function heureDe(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}

const CLASSES_ACTION = { Ajout: 'ajout', Modification: 'modification', Suppression: 'suppression', Annulation: 'annulation' };

function ligneHistorique(e) {
  return el('li', { class: 'historique__entree', dataset: { action: CLASSES_ACTION[e.action] || 'modification' } },
    el('span', { class: 'historique__heure' }, heureDe(e.le)),
    el('div', { class: 'historique__corps' },
      el('p', { class: 'historique__tete' },
        el('span', { class: 'historique__action' }, e.action || 'Modification'),
        el('span', { class: 'historique__rubrique' }, [e.rubrique, e.pole].filter(Boolean).join(' · ')),
        e.par ? el('span', { class: 'historique__par' }, e.par) : null),
      el('p', { class: 'historique__element' }, e.element || '—'),
      e.detail ? el('p', { class: 'historique__detail' }, e.detail) : null));
}

function rendreHistorique(zone, entrees, filtre) {
  const visibles = filtre ? entrees.filter((e) => e.rubrique === filtre) : entrees;
  if (!visibles.length) {
    monter(zone, el('p', { class: 'historique__vide' }, filtre ? 'Rien dans cette rubrique pour le moment.' : 'Aucune modification enregistrée pour le moment.'));
    return;
  }
  const groupes = [];
  for (const e of visibles) {
    const jour = jourDe(e.le);
    if (!groupes.length || groupes[groupes.length - 1].jour !== jour) groupes.push({ jour, entrees: [] });
    groupes[groupes.length - 1].entrees.push(e);
  }
  monter(zone, groupes.map((g) => el('section', { class: 'historique__jour' },
    el('h3', { class: 'historique__date' }, g.jour),
    el('ol', { class: 'historique__liste', role: 'list' }, g.entrees.map(ligneHistorique)))));
}

/**
 * Ouvre l'historique des modifications du site : les plus récentes
 * d'abord, groupées par jour, avec un filtre par rubrique.
 * @param {Element} [declencheur]
 */
export async function ouvrirHistorique(declencheur) {
  const zone = el('div', { class: 'historique__zone', 'aria-live': 'polite' },
    el('p', { class: 'historique__vide' }, 'Lecture du journal…'));
  const filtres = el('div', { class: 'historique__filtres', role: 'group', 'aria-label': 'Filtrer par rubrique' });
  let magasin = null;
  try { magasin = await ouvrirMagasin(); } catch (_e) { magasin = null; }
  const note = magasin && magasin.hote === 'google'
    ? 'Le même journal est tenu dans la feuille « ETII Hub — base » : « Journal complet », et un onglet par rubrique.'
    : (magasin && magasin.mode === 'navigateur' ? 'Modifications faites dans ce navigateur seulement.' : '');
  ouvrirModale({
    titre: 'Historique des modifications',
    classe: 'modale--large historique',
    declencheur,
    contenu: [note ? el('p', { class: 'historique__note' }, note) : null, filtres, zone].filter(Boolean)
  });

  let entrees = [];
  try {
    entrees = magasin && typeof magasin.journal === 'function' ? await magasin.journal() : [];
  } catch (e) {
    monter(zone, el('p', { class: 'historique__vide' }, 'Le journal n’a pas pu être lu : ' + ((e && e.message) || 'erreur inconnue') + '.'));
    return;
  }
  entrees = (Array.isArray(entrees) ? entrees : [])
    .filter((e) => e && typeof e === 'object')
    .map((e) => ({
      le: texte(e.le), par: texte(e.par), rubrique: texte(e.rubrique) || 'Autres', pole: texte(e.pole),
      action: texte(e.action), element: texte(e.element), detail: texte(e.detail)
    }))
    .sort((a, b) => b.le.localeCompare(a.le));

  const presentes = ORDRE_RUBRIQUES.filter((r) => entrees.some((e) => e.rubrique === r))
    .concat([...new Set(entrees.map((e) => e.rubrique))].filter((r) => !ORDRE_RUBRIQUES.includes(r)));
  let courant = '';
  const boutons = [['', 'Tout', entrees.length]].concat(presentes.map((r) => [r, r, entrees.filter((e) => e.rubrique === r).length]))
    .map(([valeur, libelle, n]) => {
      const b = el('button', { type: 'button', class: 'historique__filtre', 'aria-pressed': valeur === '' ? 'true' : 'false' },
        libelle, el('span', { class: 'historique__compte' }, String(n)));
      b.addEventListener('click', () => {
        courant = valeur;
        boutons.forEach((x) => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
        rendreHistorique(zone, entrees, courant);
      });
      return b;
    });
  monter(filtres, entrees.length ? boutons : null);
  rendreHistorique(zone, entrees, courant);
}

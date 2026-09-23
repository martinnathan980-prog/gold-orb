/* =========================================================================
   ETII Hub — Les modifications, appliquées aux données

   Les fichiers de assets/data/ restent la base. Ce qu'on a modifié dans le
   site (magasin.js) se pose par-dessus au chargement : data.js appelle
   appliquerModifications() pour chaque jeu, si bien que TOUTES les pages
   voient les mêmes données modifiées sans rien savoir du magasin.

   Une modification vise un élément par son type et son identifiant :
     communications  annonce · agenda · edito · alerte
     flotte          porteur (identifié par son code)
     organigramme    personne · squad
     faq             question
     documents       document
     reunions        compte-rendu
   « maj » remplace l'élément (ou l'ajoute s'il n'existait pas), « suppr »
   le retire. Un élément remplacé l'est en entier : ce qu'on enregistre est
   l'élément tel que le formulaire l'a laissé.

   API :
     appliquerModifications(jeu, donnees)          -> Promise<donnees>
     enregistrerModification(jeu, type, id, donnees) -> Promise<void>
     supprimerElement(jeu, type, id)               -> Promise<void>
     abonnerModifications(fn)                      -> () => void
     nouvelIdentifiant(prefixe)                    -> string
     aplatirOrganigramme(donnees)                  -> { personnes, squads }
     definirLecteur(fn)                            data.js y branche chargerDonnees

   Chaque enregistrement porte son récit pour le journal (journal.js) :
   l'élément tel qu'il était avant, relu dans les données du site, et tel
   qu'il est après.
   ========================================================================= */

import { ouvrirMagasin, JEUX_MODIFIABLES } from './magasin.js';
import { resumerModification } from './journal.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function cloner(v) { return v === undefined ? v : JSON.parse(JSON.stringify(v)); }
function objet(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : null; }
function tableau(v) { return Array.isArray(v) ? v : []; }

/* -------------------------------------------------------------------------
   1. Une liste d'éléments identifiés
   ------------------------------------------------------------------------- */

/* Les éléments de la base gardent leur ordre ; un élément modifié garde sa
   place ; un élément ajouté se range à la fin. */
function appliquerListe(liste, modifs, type, champ) {
  const cle = champ || 'id';
  const propres = modifs.filter((m) => m.type === type);
  if (!propres.length) return tableau(liste);
  const parId = new Map(propres.map((m) => [m.id, m]));
  const vus = new Set();
  const resultat = [];
  for (const e of tableau(liste)) {
    const id = texte(e && e[cle]);
    vus.add(id);
    const m = parId.get(id);
    if (!m) { resultat.push(e); continue; }
    if (m.op === 'suppr') continue;
    resultat.push(Object.assign(cloner(m.donnees), { [cle]: id }));
  }
  for (const m of propres) {
    if (vus.has(m.id) || m.op === 'suppr') continue;
    resultat.push(Object.assign(cloner(m.donnees), { [cle]: m.id }));
  }
  return resultat;
}

/* -------------------------------------------------------------------------
   2. Les communications : annonces, rendez-vous, éditos, alertes
   ------------------------------------------------------------------------- */

/** Aujourd'hui, en AAAA-MM-JJ, heure locale. */
function aujourdhui() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

/* Un édito qui n'est plus le plus récent rejoint la frise, à sa date, comme
   une annonce du service : il ne disparaît jamais. */
function versAnnonce(edito) {
  return Object.assign({}, edito, { pole: texte(edito.pole) || 'ETII', categorie: 'Édito', typeSource: 'edito' });
}

function appliquerCommunications(d, modifs) {
  const r = Object.assign({}, d);
  r.annonces = appliquerListe(d.annonces, modifs, 'annonce');
  r.agenda = appliquerListe(d.agenda, modifs, 'agenda');

  /* Les alertes de la base sont de simples phrases : elles reçoivent un
     identifiant stable (leur rang) pour pouvoir être modifiées. Une alerte
     datée « jusqu'au » disparaît du bandeau le lendemain, mais reste dans
     la liste qu'on modifie. */
  const alertes = tableau(d.alertes).map((a, i) => (typeof a === 'string'
    ? { id: 'alerte-' + (i + 1), texte: a }
    : Object.assign({ id: 'alerte-' + (i + 1) }, a)));
  r.alertesDetail = appliquerListe(alertes, modifs, 'alerte');
  const jour = aujourdhui();
  r.alertes = r.alertesDetail
    .filter((a) => texte(a.texte) && (!texte(a.jusqua) || texte(a.jusqua) >= jour))
    .map((a) => texte(a.texte));

  /* Les éditos : celui de la base porte l'identifiant « mot-du-chef ». Le
     plus récent est à la une ; les autres rejoignent la frise. */
  const base = objet(d.motDuChef);
  const editos = appliquerListe(base ? [Object.assign({ id: 'mot-du-chef' }, base)] : [], modifs, 'edito')
    .filter((e) => texte(e.titre))
    .sort((a, b) => texte(b.date).localeCompare(texte(a.date)));
  r.motDuChef = editos[0] || null;
  if (editos.length > 1) r.annonces = r.annonces.concat(editos.slice(1).map(versAnnonce));
  return r;
}

/* -------------------------------------------------------------------------
   3. L'organigramme : des personnes placées dans des squads
   ------------------------------------------------------------------------- */

/**
 * L'organigramme à plat : chaque personne porte son pôle (« ETII » pour la
 * direction du service) et sa squad (vide pour un responsable) ; chaque
 * squad porte son pôle et son rang. Les squads de la base n'ont pas
 * d'identifiant : elles reçoivent « <pôle>-<rang> ».
 * @param {object} donnees  organigramme.json
 * @returns {{personnes: object[], squads: object[]}}
 */
export function aplatirOrganigramme(donnees) {
  const d = objet(donnees) || {};
  const personnes = [];
  const squads = [];
  const direction = objet(d.direction);
  if (direction) personnes.push(Object.assign({}, direction, { pole: 'ETII', squad: '' }));
  for (const p of tableau(d.poles)) {
    const code = texte(p && p.pole).toUpperCase();
    if (!code) continue;
    const resp = objet(p.responsable);
    if (resp) personnes.push(Object.assign({}, resp, { pole: code, squad: '' }));
    tableau(p.squads).forEach((s, i) => {
      const id = texte(s && s.id) || (code + '-' + (i + 1));
      squads.push({ id, pole: code, nom: texte(s && s.nom) || ('Squad ' + (i + 1)), rang: i });
      for (const m of tableau(s && s.membres)) {
        if (objet(m)) personnes.push(Object.assign({}, m, { pole: code, squad: id }));
      }
    });
  }
  return { personnes, squads };
}

function appliquerOrganigramme(d, modifs) {
  const plat = aplatirOrganigramme(d);
  const personnes = appliquerListe(plat.personnes, modifs, 'personne');
  const squads = appliquerListe(plat.squads, modifs, 'squad');
  const r = Object.assign({}, d);

  const direction = personnes.find((x) => texte(x.pole) === 'ETII' && !texte(x.squad));
  r.direction = direction || null;

  const codes = tableau(d.poles).map((p) => texte(p && p.pole).toUpperCase()).filter(Boolean);
  r.poles = codes.map((code) => {
    const base = tableau(d.poles).find((p) => texte(p && p.pole).toUpperCase() === code) || {};
    const responsable = personnes.find((x) => texte(x.pole) === code && !texte(x.squad)) || null;
    const siennes = squads.filter((s) => texte(s.pole) === code)
      .sort((a, b) => (Number(a.rang) || 0) - (Number(b.rang) || 0) || texte(a.nom).localeCompare(texte(b.nom), 'fr'));
    const ids = new Set(siennes.map((s) => s.id));
    const construites = siennes.map((s) => ({
      id: s.id, nom: s.nom,
      membres: personnes.filter((x) => texte(x.pole) === code && x.squad === s.id)
    }));
    /* Une personne dont la squad a disparu n'est jamais perdue : elle
       attend dans « À affecter », visible, jusqu'à ce qu'on la place. */
    const orphelins = personnes.filter((x) => texte(x.pole) === code && texte(x.squad) && !ids.has(x.squad) && x !== responsable);
    if (orphelins.length) construites.push({ id: code + '-a-affecter', nom: 'À affecter', membres: orphelins });
    return Object.assign({}, base, { pole: code, responsable, squads: construites });
  });
  return r;
}

/* -------------------------------------------------------------------------
   4. L'entrée : un jeu, ses modifications
   ------------------------------------------------------------------------- */

const ADAPTATEURS = {
  communications: appliquerCommunications,
  flotte: (d, m) => Object.assign({}, d, { flotte: appliquerListe(d.flotte, m, 'porteur', 'code') }),
  organigramme: appliquerOrganigramme,
  faq: (d, m) => Object.assign({}, d, { questions: appliquerListe(d.questions, m, 'question') }),
  documents: (d, m) => Object.assign({}, d, { documents: appliquerListe(d.documents, m, 'document') }),
  reunions: (d, m) => Object.assign({}, d, { comptesRendus: appliquerListe(d.comptesRendus, m, 'compte-rendu') })
};

/**
 * Pose sur un jeu de données les modifications faites dans le site.
 * Ne rejette jamais : un magasin injoignable rend la base telle quelle.
 * @param {string} jeu
 * @param {object} donnees  le contenu du fichier (non modifié par l'appel)
 * @returns {Promise<object>}
 */
export async function appliquerModifications(jeu, donnees) {
  if (!JEUX_MODIFIABLES.includes(jeu) || !objet(donnees)) return donnees;
  let modifs = [];
  try { modifs = await (await ouvrirMagasin()).lire(jeu); } catch (_e) { modifs = []; }
  if (!modifs.length) return donnees;
  try { return ADAPTATEURS[jeu](cloner(donnees), modifs); }
  catch (e) {
    if (typeof console !== 'undefined') console.warn('[modifications] « ' + jeu + ' » : modifications ignorées (' + (e && e.message) + ').');
    return donnees;
  }
}

/* -------------------------------------------------------------------------
   5. Écrire
   ------------------------------------------------------------------------- */

const abonnes = new Set();

/** Prévient à chaque modification enregistrée : fn(jeu). */
export function abonnerModifications(fn) {
  abonnes.add(fn);
  return () => abonnes.delete(fn);
}

function prevenir(jeu) {
  for (const fn of abonnes) { try { fn(jeu); } catch (_e) { /* un abonné ne casse pas les autres */ } }
}

/* Les données du site, déjà modifiées : data.js y branche chargerDonnees
   (pas d'import dans ce sens, data.js importe déjà ce module). */
let lecteur = null;

export function definirLecteur(fn) { lecteur = typeof fn === 'function' ? fn : null; }

function trouverElement(jeu, type, id, d) {
  const chercher = (liste, champ) => tableau(liste).find((e) => texte(e && e[champ || 'id']) === id) || null;
  if (jeu === 'communications') {
    if (type === 'agenda') return chercher(d.agenda);
    if (type === 'alerte') return chercher(d.alertesDetail);
    if (type === 'edito') {
      const une = objet(d.motDuChef);
      if (une && (texte(une.id) || 'mot-du-chef') === id) return une;
      return chercher(tableau(d.annonces).filter((a) => a && a.typeSource === 'edito'));
    }
    return chercher(tableau(d.annonces).filter((a) => a && a.typeSource !== 'edito'));
  }
  if (jeu === 'flotte') return chercher(d.flotte, 'code');
  if (jeu === 'organigramme') {
    const plat = aplatirOrganigramme(d);
    return type === 'squad' ? chercher(plat.squads) : chercher(plat.personnes);
  }
  if (jeu === 'faq') return chercher(d.questions);
  if (jeu === 'documents') return chercher(d.documents);
  if (jeu === 'reunions') return chercher(d.comptesRendus);
  return null;
}

/* L'élément tel que le site le montre maintenant, ou null (un ajout). Ne
   bloque jamais un enregistrement : au pire, le récit dit « Ajout ». */
async function elementActuel(jeu, type, id) {
  if (!lecteur) return null;
  try {
    const d = await Promise.race([lecteur(jeu), new Promise((r) => setTimeout(() => r(null), 4000))]);
    return objet(d) ? (cloner(trouverElement(jeu, type, texte(id), d)) || null) : null;
  } catch (_e) { return null; }
}

async function recit(jeu, type, id, op, apres) {
  try {
    const avant = await elementActuel(jeu, type, id);
    return resumerModification({ jeu, type, id: texte(id), op, avant, apres });
  } catch (_e) { return null; }
}

/* Les champs de travail que le site ajoute en lisant (placement dans
   l'organigramme mis à part) ne partent jamais dans le magasin. */
function nettoyer(donnees) {
  const copie = cloner(donnees) || {};
  for (const cle of Object.keys(copie)) if (cle.startsWith('__')) delete copie[cle];
  return copie;
}

/**
 * Enregistre un élément créé ou modifié.
 * @param {string} jeu
 * @param {string} type
 * @param {string} id
 * @param {object} donnees  l'élément complet
 */
export async function enregistrerModification(jeu, type, id, donnees) {
  const magasin = await ouvrirMagasin();
  const propres = nettoyer(donnees);
  const journal = await recit(jeu, type, id, 'maj', propres);
  await magasin.poser(jeu, { type, id: texte(id), op: 'maj', donnees: propres, le: new Date().toISOString(), par: magasin.auteur, journal });
  prevenir(jeu);
}

/**
 * Retire un élément du site. Un élément ajouté dans le site disparaît ; un
 * élément de la base est masqué (on peut toujours revenir en arrière en
 * retirant la modification).
 */
export async function supprimerElement(jeu, type, id) {
  const magasin = await ouvrirMagasin();
  const journal = await recit(jeu, type, id, 'suppr', null);
  await magasin.poser(jeu, { type, id: texte(id), op: 'suppr', donnees: null, le: new Date().toISOString(), par: magasin.auteur, journal });
  prevenir(jeu);
}

/** Un identifiant neuf, lisible, jamais réutilisé. */
export function nouvelIdentifiant(prefixe) {
  const alea = Math.random().toString(36).slice(2, 6);
  return (texte(prefixe) || 'e') + '-' + Date.now().toString(36) + alea;
}

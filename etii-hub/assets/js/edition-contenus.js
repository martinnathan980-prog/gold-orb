/* =========================================================================
   ETII Hub — Les formulaires de chaque contenu

   edition.js sait dessiner un formulaire et des commandes ; ce module sait
   ce qu'est un rendez-vous, une personne, une squad, une question, un
   document, un porteur ou un compte rendu : quels champs, quelles listes
   de choix, et comment l'enregistrer (modifications.js).

   Aucune page n'a à se redessiner à la main après un enregistrement :
   modifications.js prévient ses abonnés, data.js oublie le jeu, et chaque
   page s'abonne pour recharger les sections qui en dépendent.

   Les communications elles-mêmes s'écrivent dans l'éditeur (editeur.js) ;
   on n'y ajoute ici que ce qui manquait : la liste des alertes, et le
   passage d'un dossier du kiosque à sa modification.
   ========================================================================= */

import { el, ouvrirModale, toast } from './ui.js';
import { ouvrirFormulaire, barreEdition } from './edition.js';
import { enregistrerModification, supprimerElement, nouvelIdentifiant, aplatirOrganigramme } from './modifications.js';
import { ouvrirEditeur } from './editeur.js';
import { supprimerCommunication } from './communications.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function tableau(v) { return Array.isArray(v) ? v : []; }

function aujourdhui() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

const POLES = [['ETII', 'Tout le service'], ['ETIIA', 'ETIIA'], ['ETIIE', 'ETIIE'], ['ETIII', 'ETIII']];
const POLES_SEULS = POLES.slice(1);
const DATE_ISO = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(texte(v)) ? '' : 'Une date au format AAAA-MM-JJ.');

/* -------------------------------------------------------------------------
   1. Les communications : depuis un dossier du kiosque
   ------------------------------------------------------------------------- */

/**
 * « Modifier » sur la lecture du kiosque : l'éditeur pour une annonce ou
 * un édito, le formulaire de rendez-vous pour une entrée d'agenda.
 */
export function modifierCommunication(dossier, declencheur, pole) {
  const src = dossier && dossier.source;
  if (!src || !src.id) return;
  if (src.type === 'agenda') { ouvrirRendezVous({ existant: src.entree, declencheur }); return; }
  ouvrirEditeur({ existant: { type: src.type, id: src.id, entree: src.entree }, pole: pole || 'ETII', declencheur });
}

/** « Supprimer » sur la lecture du kiosque. */
export async function supprimerDossier(dossier) {
  const src = dossier && dossier.source;
  if (!src || !src.id) return;
  try {
    await supprimerCommunication(src.type, src.id);
    toast('Communication supprimée.', 'succes');
  } catch (e) {
    toast((e && e.message) || 'La suppression a échoué.', 'erreur');
  }
}

/**
 * Les alertes du bandeau, toutes, avec de quoi les modifier, les retirer
 * et en ajouter une.
 * @param {{alertes: Array<{id:string, texte:string, jusqua?:string}>, declencheur?: Element}} o
 */
export function ouvrirAlertes(o) {
  const alertes = tableau(o && o.alertes);
  const jour = aujourdhui();
  let modale = null;
  const liste = el('ul', { class: 'edition-liste', role: 'list' }, alertes.map((a) => {
    const expiree = texte(a.jusqua) && texte(a.jusqua) < jour;
    return el('li', { class: 'edition-liste__element' },
      el('div', { class: 'edition-liste__texte' },
        el('span', {}, texte(a.texte)),
        texte(a.jusqua)
          ? el('span', { class: 'edition-liste__detail' }, expiree ? 'Expirée le ' + texte(a.jusqua) + ' — plus affichée' : 'Jusqu’au ' + texte(a.jusqua))
          : null),
      barreEdition({
        quoi: texte(a.texte),
        surModifier: (b) => { if (modale) modale.fermer('modifier'); ouvrirEditeur({ existant: { type: 'alerte', id: a.id, entree: a }, declencheur: b }); },
        surSupprimer: async () => {
          try { await supprimerCommunication('alerte', a.id); toast('Alerte retirée.', 'succes'); if (modale) modale.fermer('supprime'); }
          catch (e) { toast((e && e.message) || 'La suppression a échoué.', 'erreur'); }
        }
      }));
  }));
  modale = ouvrirModale({
    titre: 'Les alertes du bandeau',
    declencheur: o && o.declencheur,
    classe: 'modale--formulaire',
    contenu: el('div', { class: 'pile' },
      alertes.length ? liste : el('p', { class: 'texte-doux sans-marge' }, 'Aucune alerte pour le moment.'),
      el('div', {}, (() => {
        const b = el('button', { type: 'button', class: 'bouton bouton--secondaire bouton--compact' }, '+ Ajouter une alerte');
        b.addEventListener('click', () => { modale.fermer('ajout'); ouvrirEditeur({ type: 'alerte', declencheur: o && o.declencheur }); });
        return b;
      })())),
    actions: [{ libelle: 'Fermer', variante: 'secondaire' }]
  });
  return modale;
}

/* -------------------------------------------------------------------------
   2. L'agenda : les rendez-vous à venir
   ------------------------------------------------------------------------- */

export const TYPES_RENDEZ_VOUS = [
  ['jalon', 'Jalon'], ['revue', 'Revue'], ['reunion', 'Réunion'], ['atelier', 'Atelier'],
  ['formation', 'Formation'], ['evenement', 'Événement']
];

/** Ajouter ou modifier un rendez-vous de l'agenda. */
export function ouvrirRendezVous(o) {
  const existant = o && o.existant;
  const id = texte(existant && existant.id) || nouvelIdentifiant('rdv');
  return ouvrirFormulaire({
    titre: existant ? 'Modifier le rendez-vous' : 'Ajouter un rendez-vous',
    declencheur: o && o.declencheur,
    quoi: existant ? texte(existant.titre) : '',
    valeurs: existant || { date: aujourdhui(), type: 'reunion', pole: (o && o.pole) || 'ETII' },
    champs: [
      { cle: 'titre', libelle: 'Titre', type: 'texte', requis: true, large: true, placeholder: 'Revue de configuration trimestrielle' },
      { cle: 'date', libelle: 'Date', type: 'date', requis: true, valider: DATE_ISO },
      { cle: 'type', libelle: 'Type', type: 'choix', requis: true, options: TYPES_RENDEZ_VOUS },
      { cle: 'pole', libelle: 'Pour', type: 'choix', requis: true, options: POLES },
      { cle: 'lieu', libelle: 'Lieu', type: 'texte', placeholder: 'Salle, visio…' },
      { cle: 'resume', libelle: 'En une ou deux phrases', type: 'long', lignes: 3, placeholder: 'Ce qui s’y décide, ce qu’il faut préparer.' }
    ],
    surEnregistrer: (v) => enregistrerModification('communications', 'agenda', id,
      Object.assign({}, existant || {}, v, { id, statut: texte(v.date) >= aujourdhui() ? 'a-venir' : 'passee' })),
    surSupprimer: existant ? () => supprimerElement('communications', 'agenda', id) : null
  });
}

/* -------------------------------------------------------------------------
   3. L'organigramme : les personnes et les squads
   ------------------------------------------------------------------------- */

const ROLES = [['membre', 'Membre'], ['leader', 'Lead de squad'], ['responsable', 'Responsable de pôle'], ['direction', 'Direction du service']];

/* Où se place une personne, en un seul choix : « ETIIA · Squad 2 »,
   « ETIIA · Responsable du pôle », « Direction du service ». La valeur
   porte le pôle et la squad : « ETIIA|ETIIA-2 ». */
function placements(organigramme) {
  const plat = aplatirOrganigramme(organigramme);
  const options = [['ETII|', 'Direction du service']];
  for (const [code] of POLES_SEULS) {
    options.push([code + '|', code + ' · Responsable du pôle']);
    plat.squads.filter((s) => s.pole === code).forEach((s) => options.push([code + '|' + s.id, code + ' · ' + s.nom]));
  }
  return options;
}

function perimetres(flotte) {
  const codes = tableau(flotte && flotte.flotte).map((a) => texte(a && a.code)).filter(Boolean);
  return [['', '—']].concat(codes.map((c) => [c, c]), [['Transverse', 'Transverse']]);
}

/**
 * Ajouter ou modifier une personne.
 * @param {object} o
 * @param {object} [o.existant]      la personne, avec son pôle et sa squad (aplatirOrganigramme)
 * @param {object} o.organigramme    organigramme.json (modifié)
 * @param {object} [o.flotte]        flotte.json, pour la liste des périmètres
 * @param {string} [o.pole]          placement par défaut d'une nouvelle personne
 * @param {string} [o.squad]
 * @param {(personne:object)=>void} [o.apres]  une fois enregistrée
 */
export function ouvrirPersonne(o) {
  const existant = o.existant || null;
  const id = texte(existant && existant.id) || nouvelIdentifiant('p');
  const valeurs = Object.assign({ role: 'membre', competences: [] }, existant || {});
  valeurs.placement = texte(valeurs.pole || o.pole || 'ETIIA') + '|' + texte(valeurs.squad !== undefined ? valeurs.squad : (o.squad || ''));
  return ouvrirFormulaire({
    titre: existant ? 'Modifier : ' + texte(existant.nom) : 'Ajouter une personne',
    declencheur: o.declencheur,
    quoi: existant ? texte(existant.nom) : '',
    valeurs,
    champs: [
      { cle: 'nom', libelle: 'Nom', type: 'texte', requis: true, placeholder: 'Prénom Nom' },
      { cle: 'poste', libelle: 'Rôle', type: 'texte', requis: true, placeholder: 'Ingénieur harnais' },
      { cle: 'placement', libelle: 'Place dans l’organigramme', type: 'choix', requis: true, options: placements(o.organigramme) },
      { cle: 'role', libelle: 'Fonction', type: 'choix', requis: true, options: ROLES },
      { cle: 'perimetre', libelle: 'Porteur suivi', type: 'choix', options: perimetres(o.flotte) },
      { cle: 'competences', libelle: 'Compétences', type: 'competences', aide: 'Référent : la personne à solliciter en premier sur ce sujet.' }
    ],
    surEnregistrer: (v) => {
      const [pole, squad] = texte(v.placement).split('|');
      const personne = Object.assign({}, existant || {}, v, { id, pole: pole || 'ETIIA', squad: squad || '' });
      delete personne.placement;
      if (!personne.squad && personne.pole !== 'ETII' && personne.role !== 'responsable') personne.role = 'responsable';
      if (personne.pole === 'ETII') personne.role = 'direction';
      return enregistrerModification('organigramme', 'personne', id, personne)
        .then(() => { if (typeof o.apres === 'function') o.apres(personne); });
    },
    surSupprimer: existant ? () => supprimerElement('organigramme', 'personne', id) : null
  });
}

/** Ajouter ou renommer une squad. */
export function ouvrirSquad(o) {
  const existant = o.existant || null;
  const id = texte(existant && existant.id) || nouvelIdentifiant(texte(o.pole) || 'squad');
  const rang = existant ? existant.rang : 1000;
  return ouvrirFormulaire({
    titre: existant ? 'Renommer la squad' : 'Ajouter une squad',
    declencheur: o.declencheur,
    quoi: existant ? texte(existant.nom) : '',
    valeurs: existant || { pole: o.pole, nom: '' },
    champs: [
      { cle: 'nom', libelle: 'Nom de la squad', type: 'texte', requis: true, placeholder: 'Squad 7' },
      { cle: 'pole', libelle: 'Pôle', type: 'choix', requis: true, options: POLES_SEULS }
    ],
    surEnregistrer: (v) => enregistrerModification('organigramme', 'squad', id, { id, pole: v.pole, nom: v.nom, rang }),
    surSupprimer: existant ? () => supprimerElement('organigramme', 'squad', id) : null
  });
}

/* -------------------------------------------------------------------------
   4. La FAQ
   ------------------------------------------------------------------------- */

export function ouvrirQuestion(o) {
  const existant = o.existant || null;
  const id = texte(existant && existant.id) || nouvelIdentifiant('f');
  return ouvrirFormulaire({
    titre: existant ? 'Modifier la question' : 'Ajouter une question',
    declencheur: o.declencheur,
    quoi: existant ? texte(existant.question) : '',
    valeurs: existant || { pole: o.pole || 'ETII', categorie: 'Technique' },
    champs: [
      { cle: 'question', libelle: 'Question', type: 'texte', requis: true, large: true },
      { cle: 'reponse', libelle: 'Réponse', type: 'long', requis: true, lignes: 6 },
      { cle: 'categorie', libelle: 'Catégorie', type: 'texte', placeholder: 'Technique, Processus, Outils…' },
      { cle: 'pole', libelle: 'Pôle', type: 'choix', requis: true, options: POLES },
      { cle: 'motsCles', libelle: 'Mots-clés', type: 'liste', aide: 'Séparés par des virgules : ils aident la recherche.' }
    ],
    surEnregistrer: (v) => enregistrerModification('faq', 'question', id, Object.assign({}, existant || {}, v, { id })),
    surSupprimer: existant ? () => supprimerElement('faq', 'question', id) : null
  });
}

/* -------------------------------------------------------------------------
   5. Les documents
   ------------------------------------------------------------------------- */

export function ouvrirDocument(o) {
  const existant = o.existant || null;
  const id = texte(existant && existant.id) || nouvelIdentifiant('d');
  const f = (o.documents && o.documents.facettes) || {};
  const choix = (liste) => tableau(liste).map((x) => [texte(x), texte(x)]);
  const personnes = tableau(o.personnes).map((p) => texte(p.nom)).filter(Boolean).sort((a, b) => a.localeCompare(b, 'fr', { numeric: true }));
  const autres = tableau(o.documents && o.documents.documents).filter((d) => texte(d.id) !== id);
  return ouvrirFormulaire({
    titre: existant ? 'Modifier le document' : 'Ajouter un document',
    declencheur: o.declencheur,
    quoi: existant ? texte(existant.titre) : '',
    valeurs: existant || { maj: aujourdhui(), pole: o.pole ? [o.pole] : [], type: 'Technique', perimetre: 'Transverse' },
    champs: [
      { cle: 'titre', libelle: 'Titre', type: 'texte', requis: true, large: true },
      { cle: 'reference', libelle: 'Référence', type: 'texte', requis: true, placeholder: 'ETII-TEC-073' },
      { cle: 'maj', libelle: 'Mis à jour le', type: 'date', requis: true, valider: DATE_ISO },
      { cle: 'type', libelle: 'Type', type: 'choix', requis: true, options: choix(f.types) },
      { cle: 'perimetre', libelle: 'Périmètre', type: 'choix', options: choix(f.perimetres) },
      { cle: 'porteur', libelle: 'Porteur du document', type: 'choix', options: [['', '—']].concat(personnes.map((n) => [n, n])) },
      { cle: 'pole', libelle: 'Pôles', type: 'plusieurs', options: POLES_SEULS },
      { cle: 'metier', libelle: 'Métiers', type: 'liste', aide: 'Séparés par des virgules : ' + tableau(f.metiers).join(', ') + '.' },
      { cle: 'lien', libelle: 'Lien vers le document', type: 'url', large: true, placeholder: 'https://…' },
      { cle: 'description', libelle: 'Description', type: 'long', lignes: 3 },
      { cle: 'motsCles', libelle: 'Mots-clés', type: 'liste' },
      { cle: 'remplacePar', libelle: 'Remplacé par', type: 'choix', options: [['', '— (version en vigueur)']].concat(autres.map((d) => [texte(d.id), texte(d.reference) + ' — ' + texte(d.titre)])) }
    ],
    surEnregistrer: (v) => enregistrerModification('documents', 'document', id, Object.assign({}, existant || {}, v, { id })),
    surSupprimer: existant ? () => supprimerElement('documents', 'document', id) : null
  });
}

/* -------------------------------------------------------------------------
   6. Les porteurs
   ------------------------------------------------------------------------- */

/* Les groupes de la fiche, dans l'ordre de la fiche dépliée. Un champ se
   modifie par sa valeur et son unité ; la confiance et la source restent
   ce qu'elles étaient (une valeur saisie ici devient « à relire »). */
const GROUPES_FICHE = [
  ['identite', 'Identité'], ['motorisation', 'Motorisation'], ['masses', 'Masses'], ['capacite', 'Capacité'],
  ['performances', 'Performances'], ['dimensions', 'Dimensions'], ['production', 'Production'], ['electrique', 'Électrique']
];

function libelleCle(cle) {
  return String(cle).replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (c) => c.toUpperCase()).toLowerCase().replace(/^./, (c) => c.toUpperCase());
}

/**
 * Ajouter ou modifier un porteur : l'identité, le résumé, et chaque valeur
 * de sa fiche.
 * @param {object} o
 * @param {object} [o.existant]   l'appareil (flotte.json → flotte[])
 * @param {object} o.flotte       flotte.json, pour ses catégories
 * @param {object} [o.libelles]   { groupe: { cle: libellé } } — les libellés de porteurs.js
 */
export function ouvrirPorteur(o) {
  const existant = o.existant || null;
  const categories = tableau(o.flotte && o.flotte.categories).map((c) => [texte(c.cle), texte(c.libelle)]);
  const fiche = (existant && existant.fiche) || {};
  const libelles = o.libelles || {};
  const champsFiche = GROUPES_FICHE
    .filter(([g]) => fiche[g] && typeof fiche[g] === 'object' && Object.keys(fiche[g]).length)
    .map(([g, titre]) => ({
      type: 'groupe', libelle: titre,
      champs: Object.keys(fiche[g]).flatMap((cle) => {
        const nom = (libelles[g] && libelles[g][cle]) || libelleCle(cle);
        return [
          { cle: 'fiche.' + g + '.' + cle + '.valeur', libelle: nom, type: 'texte' },
          { cle: 'fiche.' + g + '.' + cle + '.unite', libelle: 'Unité', type: 'texte', placeholder: 'kg, km/h…' }
        ];
      })
    }));
  const valeurs = existant || { categorie: categories.length ? categories[0][0] : 'civil', poles: [], fiche: { statut: 'à renseigner' } };
  return ouvrirFormulaire({
    titre: existant ? 'Modifier la fiche ' + texte(existant.code) : 'Ajouter un porteur',
    declencheur: o.declencheur,
    quoi: existant ? texte(existant.code) : '',
    valeurs,
    champs: [
      { cle: 'code', libelle: 'Code', type: 'texte', requis: true, placeholder: 'H135', valider: (v) => (/^[A-Za-z0-9-]{2,20}$/.test(texte(v)) ? '' : 'Lettres, chiffres et tirets, sans espace.') },
      { cle: 'fiche.nom', libelle: 'Nom complet', type: 'texte', placeholder: 'Airbus Helicopters H135' },
      { cle: 'categorie', libelle: 'Catégorie', type: 'choix', requis: true, options: categories },
      { cle: 'segment', libelle: 'Segment', type: 'texte', placeholder: 'Bimoteur léger' },
      { cle: 'fiche.statut', libelle: 'Statut', type: 'texte', placeholder: 'en production' },
      { cle: 'poles', libelle: 'Pôles qui le suivent', type: 'plusieurs', options: POLES_SEULS },
      { cle: 'photo', libelle: 'Photo', type: 'texte', large: true, placeholder: 'https://… ou assets/img/porteurs/…', aide: 'Une adresse publique, ou un fichier du site. Une photo sous licence libre doit garder son crédit.' },
      { cle: 'fiche.resume', libelle: 'Présentation', type: 'long', lignes: 5 },
      ...champsFiche,
      { cle: 'fiche.insolites', libelle: 'Le saviez-vous ?', type: 'lignes', objets: true, aide: 'Une anecdote par ligne.' }
    ],
    surEnregistrer: (v) => {
      const code = texte(v.code).toUpperCase();
      const porteur = Object.assign({}, existant || {}, v, { code });
      porteur.fiche = Object.assign({}, porteur.fiche || {}, { code, categorie: v.categorie, segment: v.segment, relecture: 'modifiée dans le site' });
      const ancien = texte(existant && existant.code).toUpperCase();
      return enregistrerModification('flotte', 'porteur', code, porteur)
        .then(() => (ancien && ancien !== code ? supprimerElement('flotte', 'porteur', ancien) : null));
    },
    surSupprimer: existant ? () => supprimerElement('flotte', 'porteur', texte(existant.code)) : null
  });
}

/* -------------------------------------------------------------------------
   7. Les comptes rendus de réunion
   ------------------------------------------------------------------------- */

export function ouvrirCompteRendu(o) {
  const existant = o.existant || null;
  const id = texte(existant && existant.id) || nouvelIdentifiant('cr');
  /* Les sujets s'écrivent « Titre — notes », un par ligne. */
  const valeurs = Object.assign({}, existant || { date: aujourdhui(), pole: o.pole || 'ETII' });
  valeurs.sujetsTexte = tableau(valeurs.sujets).map((s) => texte(s && s.titre) + (texte(s && s.notes) ? ' — ' + texte(s.notes) : '')).join('\n');
  return ouvrirFormulaire({
    titre: existant ? 'Modifier le compte rendu' : 'Ajouter un compte rendu',
    declencheur: o.declencheur,
    quoi: existant ? texte(existant.titre) : '',
    valeurs,
    champs: [
      { cle: 'titre', libelle: 'Titre', type: 'texte', requis: true, large: true },
      { cle: 'date', libelle: 'Date', type: 'date', requis: true, valider: DATE_ISO },
      { cle: 'pole', libelle: 'Pôle', type: 'choix', requis: true, options: POLES },
      { cle: 'synthese', libelle: 'Synthèse', type: 'long', lignes: 3, requis: true },
      { cle: 'sujetsTexte', libelle: 'Sujets', type: 'long', lignes: 4, aide: 'Un sujet par ligne : « Titre — ce qui s’en est dit ».' },
      { cle: 'actions', libelle: 'À faire', type: 'lignes', aide: 'Une action par ligne.' },
      { cle: 'decisions', libelle: 'Fait / décidé', type: 'lignes', aide: 'Une décision par ligne.' }
    ],
    surEnregistrer: (v) => {
      const sujets = texte(v.sujetsTexte).split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
        const [titre, ...reste] = l.split(/\s+—\s+/);
        return { titre: texte(titre), notes: texte(reste.join(' — ')) };
      });
      const cr = Object.assign({}, existant || {}, v, { id, sujets });
      delete cr.sujetsTexte;
      return enregistrerModification('reunions', 'compte-rendu', id, cr);
    },
    surSupprimer: existant ? () => supprimerElement('reunions', 'compte-rendu', id) : null
  });
}

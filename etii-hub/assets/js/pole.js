/* =========================================================================
   ETII Hub — Espace de pôle (etiia.html, etiie.html, etiii.html)

   Une seule page, trois fois, paramétrée par <body data-pole="…">. Quatre
   sections, dans l'ordre de lecture :
     1. COMMUNICATION  — le kiosque du pôle (kiosque.js), le même qu'au
                         niveau service ;
     2. EN UN COUP D'ŒIL — les chiffres du pôle en une ligne ; « Qui peut
                         m'aider ? », un champ qui répond pendant la
                         frappe ; les équipes, en tuiles qui s'ouvrent sur
                         place ; l'index des référents ;
     3. DOCUMENTS      — les documents du pôle les plus récents, en vigueur ;
     4. FAQ            — les questions du pôle, et la demande aux experts.

   Tout se modifie dans la page, en mode édition (edition.js) : les
   communications, l'organigramme (personnes, squads), les documents, les
   questions. Chaque section se redessine seule après un enregistrement.

   Rien n'est inventé : chaque section ne montre que ce que les fichiers
   déclarent pour ce pôle (organigramme.json, flotte.json, documents.json).
   Tout le DOM est construit avec el().
   ========================================================================= */

import { el, svg, frag, monter, debounce, deleguer, mouvementReduit, dureeJeton, initTheme, initNav, suivreSommaire, revelerAuDefilement, ouvrirModale, stockage, toast, annoncer } from './ui.js';
import { initiales } from './portraits.js';
import { installerEdition, barreEdition, boutonAjouter } from './edition.js';
import { abonnerModifications, supprimerElement, aplatirOrganigramme } from './modifications.js';
import { modifierCommunication, supprimerDossier, ouvrirAlertes, ouvrirPersonne, ouvrirSquad, ouvrirDocument, ouvrirQuestion,
         ouvrirReferent, retirerReferent, ouvrirAffectation, affecter, ouvrirRendezVous } from './edition-contenus.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { kiosque, dossiersDepuisCommunications, noteOrigine } from './kiosque.js';
import { lecteur } from './lecteur.js';
import { agenda } from './agenda.js';
import { chargerCommunications } from './communications.js';
import { ouvrirEditeur } from './editeur.js';
import { creditsCommunications } from './credits.js';

/* -------------------------------------------------------------------------
   1. Les pôles : matière éditoriale, pas de la donnée
   ------------------------------------------------------------------------- */

const POLES = {
  ETIIA: {
    cle: 'ETIIA',
    metaphore: 'Squelette & ADN',
    description: 'Logique et règles d’architecture : découpage fonctionnel, '
      + 'conventions de nommage et principes que tous les autres travaux '
      + 'appliquent ensuite.'
  },
  ETIIE: {
    cle: 'ETIIE',
    metaphore: 'Système nerveux',
    description: 'Schémas électriques et communication entre systèmes : '
      + 'signaux, interfaces et cohérence des échanges d’un bout à l’autre '
      + 'de la définition.'
  },
  ETIII: {
    cle: 'ETIII',
    metaphore: 'Structure & harnais',
    description: 'Intégration physique et routage dans la maquette '
      + 'numérique : cheminements, fixations et vérification des '
      + 'interférences avant fabrication.'
  }
};

const CLE_STOCKAGE_FAQ = 'faq-questions';

/* Les niveaux de compétence, dans l'ordre où ils comptent, et leur libellé. */
const NIVEAUX = { referent: 'référent', confirme: 'confirmé', pratique: 'en pratique' };

/* Le périmètre « transverse » n'est pas un porteur : il ne fait pas de
   groupe dans « par porteur ». */
const TRANSVERSE = 'TRANSVERSE';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function normaliser(v) { return texte(v).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }
function pluriel(n, singulier, plurielForme) {
  return n + ' ' + (n > 1 ? (plurielForme || singulier + 's') : singulier);
}

function lienPole(page, code, extra) {
  let hash = 'pole=' + encodeURIComponent(code);
  if (extra && typeof extra === 'object') {
    for (const cle of Object.keys(extra)) {
      const valeur = extra[cle];
      if (valeur === null || valeur === undefined || valeur === '') continue;
      hash += '&' + encodeURIComponent(cle) + '=' + encodeURIComponent(String(valeur));
    }
  }
  return page + '#' + hash;
}

/** Le lien vers la fiche d'une personne dans l'organigramme du service. */
function lienFiche(pole, personne) {
  return lienPole('organigramme.html', pole.cle, { personne: texte(personne.id) });
}

/* -------------------------------------------------------------------------
   2. Communication
   ------------------------------------------------------------------------- */

function rendreCommunication(pole, donnees, conteneur) {
  verifierForme(donnees, { agenda: 'tableau' }, 'communications.json');
  const dossiers = dossiersDepuisCommunications(donnees, { pole: pole.cle });
  /* Tout ce que le pôle publie est déjà dans ce kiosque : il n'y a pas
     d'ailleurs où renvoyer. Le niveau service est sur le tableau de bord. */
  monter(conteneur,
    /* Une ligne, seulement s'il y a quelque chose à dire sur la source. */
    noteOrigine(donnees),
    kiosque({
      id: 'kiosque-' + pole.cle.toLowerCase(), dossiers, titreFil: 'Communications du pôle',
      /* En mode édition : ajouter, modifier, supprimer. La section se
         redessine d'elle-même après un enregistrement. */
      surAjout: (bouton) => ouvrirEditeur({ pole: pole.cle, declencheur: bouton }),
      surModifier: (dossier, bouton) => modifierCommunication(dossier, bouton, pole.cle),
      surSupprimer: (dossier) => supprimerDossier(dossier)
    }));
}

/* À venir : la frise du tableau de bord, filtrée sur le pôle (ses
   rendez-vous et ceux du service). */
function chargerAgendaDuPole(pole) {
  avecEtat('#zone-agenda', chargerCommunications,
    (donnees, conteneur) => monter(conteneur, agenda(donnees, {
      pole: pole.cle,
      limite: 8,
      surAjouter: (b) => ouvrirRendezVous({ pole: pole.cle, declencheur: b }),
      surModifier: (entree, b) => ouvrirRendezVous({ existant: entree, declencheur: b }),
      surSupprimer: (entree) => supprimerElement('communications', 'agenda', entree.id)
    })), {
      squelette: 2, compact: true,
      texteChargement: 'Chargement des prochains rendez-vous…',
      titreErreur: 'Rendez-vous indisponibles',
      estVide: () => false
    });
}

function chargerCommunicationDuPole(pole) {
  avecEtat('#zone-communication', chargerCommunications,
    (donnees, conteneur) => rendreCommunication(pole, donnees, conteneur), {
      squelette: 3,
      texteChargement: 'Chargement de la communication du pôle ' + pole.cle + '…',
      titreErreur: 'Communication indisponible',
      /* Jamais « vide » : le kiosque sait dire qu'il n'a rien à lire, et
         garde en mode édition son bouton d'ajout ; la note de source, elle,
         doit pouvoir s'afficher justement quand la feuille n'a rien rendu. */
      estVide: () => false
    });
}

/* -------------------------------------------------------------------------
   3. Les gens du pôle : lecture d'organigramme.json
   ------------------------------------------------------------------------- */

function blocOrganigramme(donnees, code) {
  verifierForme(donnees, { poles: 'tableau' }, 'organigramme.json');
  return donnees.poles.find((e) => e && typeof e === 'object' && texte(e.pole).toUpperCase() === code) || null;
}

/** Les squads du bloc, chacune avec son lead (rôle `leader`) et ses membres. */
function squadsDuBloc(bloc) {
  if (!bloc || typeof bloc !== 'object') return [];
  return (Array.isArray(bloc.squads) ? bloc.squads : [])
    .filter((s) => s && typeof s === 'object')
    .map((s, i) => {
      const membres = (Array.isArray(s.membres) ? s.membres : []).filter((m) => m && typeof m === 'object');
      /* L'identifiant d'une squad : le sien, ou « <pôle>-<rang> » — la règle
         de modifications.js, pour qu'une squad se modifie sous le même nom. */
      const id = texte(s.id) || (texte(bloc.pole).toUpperCase() + '-' + (i + 1));
      return { id, rang: i, nom: texte(s.nom) || 'Squad à nommer', lead: membres.find(estLead) || null, membres };
    });
}

/** Le responsable puis les membres de chaque squad, à plat. */
function membresDuBloc(bloc) {
  const liste = [];
  if (bloc && bloc.responsable && typeof bloc.responsable === 'object') liste.push(bloc.responsable);
  for (const squad of squadsDuBloc(bloc)) liste.push(...squad.membres);
  return liste;
}

function estLead(personne) { return texte(personne.role) === 'leader'; }

/** Le porteur d'une personne : le champ `porteur`, sinon son `perimetre`. */
function porteurDe(personne) { return texte(personne.porteur) || texte(personne.perimetre); }

function competencesDe(personne) {
  return (Array.isArray(personne.competences) ? personne.competences : [])
    .filter((c) => c && typeof c === 'object' && texte(c.nom));
}

function niveauDe(competence) {
  const n = normaliser(competence.niveau);
  return NIVEAUX[n] ? n : 'pratique';
}

/**
 * Les compétences du pôle, une entrée par nom : ses référents (les
 * personnes au niveau `referent`), puis le compte des confirmés et des
 * pratiquants. Triées par ce qui aide à trouver quelqu'un : d'abord les
 * compétences qui ont un référent, puis les plus partagées.
 */
function expertisesDuBloc(bloc) {
  const parNom = new Map();
  for (const membre of membresDuBloc(bloc)) {
    for (const c of competencesDe(membre)) {
      const nom = texte(c.nom);
      const entree = parNom.get(nom) || { nom, referents: [], confirmes: 0, pratiquants: 0 };
      const niveau = niveauDe(c);
      if (niveau === 'referent') entree.referents.push(membre);
      else if (niveau === 'confirme') entree.confirmes += 1;
      else entree.pratiquants += 1;
      parNom.set(nom, entree);
    }
  }
  const expertises = [...parNom.values()].sort((a, b) =>
    (b.referents.length - a.referents.length)
    || (b.confirmes - a.confirmes)
    || (b.pratiquants - a.pratiquants)
    || a.nom.localeCompare(b.nom, 'fr'));
  const referents = new Set();
  expertises.forEach((e) => e.referents.forEach((r) => referents.add(texte(r.id) || texte(r.nom))));
  return { expertises, nbReferents: referents.size };
}

/* -------------------------------------------------------------------------
   4. Le pôle en un coup d'œil : trouver quelqu'un, voir les équipes,
      savoir à qui demander

   Trois gestes, pas trois listes :
     - « Qui peut m'aider ? » : un champ qui répond pendant la frappe — un
       nom, un rôle, une compétence, un appareil — par des cartes de
       personnes (initiales teintées de la squad, rôle, squad, titres,
       appareil suivi), chacune menant à sa fiche ; dessous, des
       suggestions d'un clic : les compétences et les appareils les plus
       partagés du pôle ;
     - « Les équipes » : une tuile par squad — son lead, ses visages, ses
       appareils — qui s'ouvre sur place, une à la fois, sur ses membres ;
     - « Les référents » : l'index des compétences qui ont un référent ; un
       clic, ou la souris qui s'y attarde, montre qui solliciter.
   Les chiffres du pôle tiennent en une ligne, au-dessus. En mode édition,
   l'organigramme du pôle se modifie ici même : personnes, squads,
   référents, affectation aux porteurs.
   ------------------------------------------------------------------------- */

function porteursDuPole(flotte, code) {
  verifierForme(flotte, { flotte: 'tableau' }, 'flotte.json');
  return flotte.flotte.filter((a) => a && typeof a === 'object'
    && (Array.isArray(a.poles) ? a.poles : []).some((p) => texte(p).toUpperCase() === code));
}

/* Les documents du pôle : ceux que documents.json rattache au pôle
   (`pole`), et, à défaut, ceux dont le porteur est un membre du pôle. */
function documentsDuPole(docs, code, membres) {
  verifierForme(docs, { documents: 'tableau' }, 'documents.json');
  const noms = new Set(membres.map((m) => normaliser(m.nom)).filter(Boolean));
  return docs.documents.filter((d) => d && typeof d === 'object' && texte(d.titre) && (
    (Array.isArray(d.pole) ? d.pole : [d.pole]).some((p) => texte(p).toUpperCase() === code)
    || noms.has(normaliser(d.porteur))));
}

/* Le lead d'abord, puis le responsable, puis les autres par nom. */
function rangDe(p) { return estLead(p) ? 0 : texte(p.role) === 'responsable' ? 1 : 2; }
function parRang(a, b) {
  return rangDe(a) - rangDe(b) || texte(a.nom).localeCompare(texte(b.nom), 'fr', { numeric: true });
}

/**
 * Les appareils du pôle, avec leurs gens : d'abord ceux que flotte.json
 * rattache au pôle — même quand personne n'y est encore affecté —, puis
 * les autres codes que les membres déclarent. Le périmètre transverse
 * n'est pas un porteur.
 */
function gensParPorteur(bloc, flotte) {
  const parCode = new Map();
  for (const m of membresDuBloc(bloc)) {
    const code = porteurDe(m).toUpperCase();
    if (!code || code === TRANSVERSE) continue;
    if (!parCode.has(code)) parCode.set(code, []);
    parCode.get(code).push(m);
  }
  const groupes = [];
  const vus = new Set();
  const ajouter = (code, meme) => {
    if (vus.has(code) || (!parCode.has(code) && !meme)) return;
    vus.add(code);
    groupes.push({ code, gens: (parCode.get(code) || []).slice().sort(parRang) });
  };
  if (flotte) porteursDuPole(flotte, texte(bloc.pole).toUpperCase()).forEach((a) => ajouter(texte(a.code).toUpperCase(), true));
  [...parCode.keys()].sort().forEach((code) => ajouter(code, false));
  return groupes;
}

/* L'organigramme est indispensable ; la flotte et les documents se passent
   d'un chiffre ou d'un lien plutôt que de faire tomber la section. */
async function chargerAnnuaire(code) {
  const [orga, flotte, docs] = await Promise.allSettled([
    chargerDonnees('organigramme'), chargerDonnees('flotte'), chargerDonnees('documents')
  ]);
  if (orga.status !== 'fulfilled') throw orga.reason;
  const bloc = blocOrganigramme(orga.value, code);
  if (!bloc) return null;
  const membres = membresDuBloc(bloc);
  const laFlotte = flotte.status === 'fulfilled' ? flotte.value : null;
  if (laFlotte) verifierForme(laFlotte, { flotte: 'tableau' }, 'flotte.json');
  const { expertises, nbReferents } = expertisesDuBloc(bloc);
  const squads = squadsDuBloc(bloc);
  /* La squad de chaque personne : sa teinte, son nom sur sa carte. */
  const squadDe = new Map();
  squads.forEach((s) => s.membres.forEach((p) => squadDe.set(p, s)));
  return {
    code,
    organigramme: orga.value,
    flotte: laFlotte,
    responsable: bloc.responsable && typeof bloc.responsable === 'object' ? bloc.responsable : null,
    squads,
    squadDe,
    membres,
    expertises: expertises.filter((e) => e.referents.length),
    toutesCompetences: expertises.map((e) => e.nom),
    nbReferents,
    parPorteur: gensParPorteur(bloc, laFlotte),
    /* Les codes qui ont une fiche sur le tableau de bord. */
    appareilsConnus: new Set(laFlotte ? laFlotte.flotte.filter((a) => a && typeof a === 'object' && texte(a.code))
      .map((a) => texte(a.code).toUpperCase()) : []),
    documents: docs.status === 'fulfilled' ? documentsDuPole(docs.value, code, membres).filter((d) => !texte(d.remplacePar)).length : null
  };
}

/* L'état du bloc survit à un redessin — une modification enregistrée en
   mode édition redessine la section — : la recherche en cours, la squad
   ouverte, la compétence montrée. */
const etatCoupOeil = { requete: '', tout: false, squad: '', competence: '' };

/* Six teintes d'équipe dans tokens.css ; au-delà, elles reviennent. Le
   responsable prend la teinte du pôle. */
const NB_TEINTES = 6;
function teinteDe(m, personne) {
  const s = m.squadDe.get(personne);
  return s ? String((s.rang % NB_TEINTES) + 1) : 'pole';
}

/* Où est une personne dans l'organigramme du pôle : pour le formulaire. */
function placementDe(m, personne) {
  if (m.responsable && texte(m.responsable.id) === texte(personne.id)) return { pole: m.code, squad: '' };
  const s = m.squadDe.get(personne);
  return { pole: m.code, squad: s ? s.id : '' };
}

/* Une modification de l'annuaire ; le toast dit ce qui s'est passé. */
async function agir(promesse, message) {
  try { await promesse; toast(message, 'succes'); }
  catch (e) { toast((e && e.message) || 'La modification a échoué.', 'erreur'); }
}

/** Retire un élément ; le toast dit ce qui s'est passé, dans les deux cas. */
async function retirer(jeu, type, id, message) {
  try {
    await supprimerElement(jeu, type, id);
    toast(message, 'succes');
  } catch (e) {
    toast((e && e.message) || 'La suppression a échoué.', 'erreur');
  }
}

/* --- Les pièces : initiales, puces, carte d'une personne ----------------- */

/** Les initiales d'une personne, dans la teinte de sa squad. Décoratives :
    le nom est toujours écrit à côté. */
function avatar(m, personne, taille) {
  const lettres = initiales(personne.nom);
  return el('span', {
    class: ['avatar', taille ? 'avatar--' + taille : null, lettres.length > 3 ? 'avatar--long' : null],
    dataset: { teinte: teinteDe(m, personne) }, 'aria-hidden': 'true'
  }, lettres);
}

/* Les termes d'une recherche : normalisés, sans les mots vides. */
function termesDe(requete) { return normaliser(requete).split(/\s+/).filter(Boolean); }

/**
 * Un texte dont les passages cherchés sont marqués. La comparaison se fait
 * sans accents ni casse ; si la normalisation change la longueur du texte
 * (un caractère exotique), on renonce au marquage plutôt que de décaler.
 */
function marquer(brut, termes) {
  const t = texte(brut);
  if (!termes || !termes.length || !t) return t;
  const n = normaliser(t);
  if (n.length !== t.length) return t;
  const plages = [];
  for (const terme of termes) {
    let i = n.indexOf(terme);
    while (i >= 0) { plages.push([i, i + terme.length]); i = n.indexOf(terme, i + terme.length); }
  }
  if (!plages.length) return t;
  plages.sort((a, b) => a[0] - b[0]);
  const fusion = [];
  for (const p of plages) {
    const der = fusion[fusion.length - 1];
    if (der && p[0] <= der[1]) der[1] = Math.max(der[1], p[1]); else fusion.push(p.slice());
  }
  const morceaux = [];
  let pos = 0;
  for (const [a, b] of fusion) {
    if (a > pos) morceaux.push(t.slice(pos, a));
    morceaux.push(el('mark', { class: 'qui__marque' }, t.slice(a, b)));
    pos = b;
  }
  if (pos < t.length) morceaux.push(t.slice(pos));
  return frag(...morceaux);
}

/* Un appareil : un lien vers sa fiche sur le tableau de bord quand la
   flotte le connaît ; « Transverse » n'est pas un appareil. */
function appareilPuce(m, code, termes) {
  const cle = texte(code).toUpperCase();
  if (cle === TRANSVERSE) return el('span', { class: 'appareil-puce appareil-puce--transverse' }, marquer('Transverse', termes));
  return m.appareilsConnus.has(cle)
    ? el('a', { class: 'appareil-puce', href: 'index.html#porteur=' + encodeURIComponent(texte(code)), title: 'La fiche du ' + texte(code) }, marquer(texte(code), termes))
    : el('span', { class: 'appareil-puce' }, marquer(texte(code), termes));
}

function competencePuce(c, termes) {
  return el('span', { class: 'competence-puce', dataset: { niveau: c.niveau } },
    el('span', { class: 'competence-puce__nom' }, marquer(c.nom, termes)),
    el('span', { class: 'competence-puce__niveau' }, NIVEAUX[c.niveau] || ''));
}

/* Les commandes d'une personne, en mode édition. Selon l'endroit,
   « retirer » n'a pas le même sens : de l'organigramme, du titre de
   référent pour une compétence, ou d'un porteur. */
function commandesPersonne(m, personne, o) {
  const soi = Object.assign({}, personne, placementDe(m, personne));
  const nom = texte(personne.nom);
  return barreEdition({
    classe: 'barre-edition--compacte',
    quoi: nom + (o.edition === 'referent' ? ', référent ' + o.competence : (o.edition === 'porteur' ? ', sur le ' + o.porteur : '')),
    surModifier: (b) => ouvrirPersonne({ existant: soi, organigramme: m.organigramme, flotte: m.flotte, declencheur: b }),
    surSupprimer: o.edition === 'referent'
      ? () => agir(retirerReferent(soi, o.competence), '« ' + nom + ' » n’est plus référent en ' + o.competence + '.')
      : o.edition === 'porteur'
        ? () => agir(affecter(soi, ''), '« ' + nom + ' » ne suit plus le ' + o.porteur + '.')
        : () => retirer('organigramme', 'personne', texte(personne.id), '« ' + nom + ' » ne figure plus dans l’organigramme.')
  });
}

/**
 * Une personne, en carte : ses initiales, son nom (vers sa fiche, et toute
 * la carte avec lui), son rôle et sa squad, puis ses titres — les
 * compétences qui l'ont fait ressortir d'une recherche, sinon celles où
 * elle est référente — et l'appareil qu'elle suit.
 * @param {object} o  { termes, titres, rang, entree, edition, competence, porteur }
 */
function cartePersonne(pole, m, personne, o) {
  const opt = o || {};
  const squad = m.squadDe.get(personne) || null;
  const titres = opt.titres || competencesDe(personne).filter((c) => niveauDe(c) === 'referent')
    .slice(0, 2).map((c) => ({ nom: texte(c.nom), niveau: 'referent' }));
  const code = porteurDe(personne);
  return el('li', {
    class: ['personne-carte', opt.entree ? 'personne-carte--entree' : null],
    dataset: { teinte: teinteDe(m, personne), personne: texte(personne.id) },
    style: { '--i': Math.min(opt.rang || 0, 11) }
  },
    avatar(m, personne),
    el('div', { class: 'personne-carte__corps' },
      el('p', { class: 'personne-carte__ligne' },
        el('a', { class: 'personne-carte__nom', href: lienFiche(pole, personne) }, marquer(texte(personne.nom) || 'Nom à renseigner', opt.termes)),
        estLead(personne) ? el('span', { class: 'personne-carte__badge' }, 'lead') : null),
      el('p', { class: 'personne-carte__role' },
        el('span', {}, marquer(texte(personne.poste) || 'Rôle à renseigner', opt.termes)),
        squad ? el('span', { class: 'personne-carte__squad' }, marquer(squad.nom, opt.termes)) : null),
      (titres.length || code)
        ? el('p', { class: 'personne-carte__puces' },
          titres.map((c) => competencePuce(c, opt.termes)),
          code ? appareilPuce(m, code, opt.termes) : null)
        : null),
    commandesPersonne(m, personne, opt));
}

/* Une ligne de sous-bloc : le titre, une phrase, et à droite ce qui suit. */
function teteBloc(id, titre, sousTitre, aDroite) {
  return el('header', { class: 'coup-oeil__tete' },
    el('div', { class: 'coup-oeil__tete-texte' },
      el('h3', { class: 'coup-oeil__titre', id }, titre),
      sousTitre ? el('p', { class: 'coup-oeil__sous-titre' }, sousTitre) : null),
    aDroite || null);
}

function courbeJeton() {
  try { return getComputedStyle(document.documentElement).getPropertyValue('--courbe').trim() || 'ease-out'; }
  catch (_e) { return 'ease-out'; }
}

/* --- Les chiffres : une ligne, pas des tuiles ------------------------------ */

function ligneChiffres(m) {
  const chiffre = (cle, n, singulier, plurielForme) => el('span', { class: 'coup-oeil__chiffre', dataset: { chiffre: cle } },
    el('strong', { class: 'coup-oeil__nombre' }, n === null || n === undefined ? '—' : String(n)),
    ' ', n === null || n === undefined ? plurielForme + ' : donnée indisponible' : (n > 1 ? plurielForme : singulier));
  return el('p', { class: 'coup-oeil__chiffres' },
    chiffre('personnes', m.membres.length, 'personne', 'personnes'),
    chiffre('squads', m.squads.length, 'squad', 'squads'),
    chiffre('referents', m.nbReferents, 'référent', 'référents'),
    chiffre('documents', m.documents, 'document en vigueur', 'documents en vigueur'));
}

/* --- « Qui peut m'aider ? » ------------------------------------------------ */

/* Ce qui pèse dans le classement : un nom trouvé passe devant tout ; puis
   la compétence, selon le niveau ; l'appareil ; le rôle ; la squad. */
const POIDS = { nom: 100, referent: 90, confirme: 60, pratique: 40, appareil: 55, poste: 45, squad: 20 };
/* Les niveaux, du plus sûr au moins sûr : l'ordre des titres d'une carte. */
const RANG_NIVEAU = { referent: 0, confirme: 1, pratique: 2 };

function indexerPersonnes(m) {
  return m.membres.map((p) => {
    const squad = m.squadDe.get(p);
    return {
      personne: p,
      nom: normaliser(p.nom),
      poste: normaliser(p.poste),
      squad: squad ? normaliser(squad.nom) : '',
      appareil: normaliser(porteurDe(p)),
      competences: competencesDe(p).map((c) => ({ nom: texte(c.nom), n: normaliser(c.nom), niveau: niveauDe(c) }))
    };
  });
}

/* Chaque terme doit se trouver quelque part ; le score retient, pour
   chaque terme, le meilleur endroit où il se trouve. */
function chercherPersonnes(index, termes) {
  const trouves = [];
  for (const e of index) {
    let score = 0;
    const titres = new Map();
    let complet = true;
    for (const t of termes) {
      let s = 0;
      if (e.nom.includes(t)) s = POIDS.nom;
      for (const c of e.competences) {
        if (!c.n.includes(t)) continue;
        s = Math.max(s, POIDS[c.niveau]);
        titres.set(c.nom, c.niveau);
      }
      if (e.appareil.includes(t)) s = Math.max(s, POIDS.appareil + (e.appareil === t ? 10 : 0));
      if (e.poste.includes(t)) s = Math.max(s, POIDS.poste);
      if (e.squad.includes(t)) s = Math.max(s, POIDS.squad);
      if (!s) { complet = false; break; }
      score += s;
    }
    if (!complet) continue;
    trouves.push({
      personne: e.personne,
      score: score + (rangDe(e.personne) < 2 ? 2 : 0),
      titres: titres.size
        ? [...titres].map(([nom, niveau]) => ({ nom, niveau })).sort((a, b) => RANG_NIVEAU[a.niveau] - RANG_NIVEAU[b.niveau]).slice(0, 3)
        : null
    });
  }
  return trouves.sort((a, b) => b.score - a.score || parRang(a.personne, b.personne));
}

/* Les suggestions d'un clic : les compétences et les appareils que le
   plus de monde partage dans le pôle. */
function suggestionsDuPole(m) {
  const competences = new Map();
  const appareils = new Map();
  for (const p of m.membres) {
    for (const c of competencesDe(p)) competences.set(texte(c.nom), (competences.get(texte(c.nom)) || 0) + 1);
    const code = porteurDe(p);
    if (code && code.toUpperCase() !== TRANSVERSE) appareils.set(code, (appareils.get(code) || 0) + 1);
  }
  const tri = (a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'fr', { numeric: true });
  return [
    ...[...competences].sort(tri).slice(0, 4).map(([libelle, n]) => ({ libelle, n, appareil: false })),
    ...[...appareils].sort(tri).slice(0, 3).map(([libelle, n]) => ({ libelle, n, appareil: true }))
  ];
}

const LIMITE_RESULTATS = 12;

function blocChercheur(pole, m) {
  const prefixe = 'qui-' + pole.cle.toLowerCase();
  const index = indexerPersonnes(m);
  const codesPole = new Map(m.parPorteur.map((g) => [g.code.toUpperCase(), g]));

  const champ = el('input', {
    type: 'search', class: 'qui__champ', id: prefixe + '-champ', autocomplete: 'off', spellcheck: 'false',
    enterkeyhint: 'search', placeholder: 'Nom, rôle, compétence, appareil…',
    'aria-describedby': prefixe + '-aide', 'aria-controls': prefixe + '-resultats'
  });
  champ.value = etatCoupOeil.requete;
  const effacer = el('button', {
    type: 'button', class: 'qui__effacer', 'aria-label': 'Effacer la recherche', hidden: true,
    onClick: () => { poser(''); champ.focus(); }
  }, el('span', { 'aria-hidden': 'true' }, '×'));

  const suggestions = suggestionsDuPole(m);
  const puces = suggestions.map((s) => el('button', {
    type: 'button', class: ['qui__suggestion', s.appareil ? 'qui__suggestion--appareil' : null],
    'aria-pressed': 'false', dataset: { suggestion: s.libelle },
    'aria-label': s.libelle + ' — ' + pluriel(s.n, 'personne'),
    onClick: (evt) => poser(evt.currentTarget.getAttribute('aria-pressed') === 'true' ? '' : s.libelle)
  }, el('span', { class: 'qui__suggestion-nom' }, s.libelle), el('span', { class: 'qui__suggestion-compte', 'aria-hidden': 'true' }, String(s.n))));

  /* En mode édition : tous les porteurs du pôle, même ceux que personne ne
     suit encore — un clic les cherche, et la recherche d'un appareil
     propose d'y affecter quelqu'un. */
  const porteursEdition = m.parPorteur.length
    ? el('div', { class: 'qui__suggestions qui__porteurs edition-seulement', role: 'group', 'aria-label': 'Les porteurs du pôle' },
      el('span', { class: 'qui__suggestions-libelle' }, 'Porteurs du pôle'),
      m.parPorteur.map((g) => el('button', {
        type: 'button', class: 'qui__suggestion qui__suggestion--appareil', 'aria-pressed': 'false', dataset: { suggestion: g.code },
        onClick: (evt) => poser(evt.currentTarget.getAttribute('aria-pressed') === 'true' ? '' : g.code)
      }, el('span', { class: 'qui__suggestion-nom' }, g.code), el('span', { class: 'qui__suggestion-compte', 'aria-hidden': 'true' }, String(g.gens.length)))))
    : null;
  const toutesPuces = puces.concat(porteursEdition ? [...porteursEdition.querySelectorAll('.qui__suggestion')] : []);

  const compte = el('p', { class: 'qui__compte' });
  /* Le compte se lit aussi à l'oreille, par la région commune d'ui.js (la
     zone des résultats, elle, apparaît et disparaît) : une fois la frappe
     posée, pas à chaque lettre. */
  const direCompte = debounce(() => { if (!zone.hidden) annoncer(compte.textContent); }, 500);
  const actions = el('div', { class: 'qui__actions' });
  const grille = el('ul', { class: 'qui__grille', role: 'list' });
  const plus = el('button', { type: 'button', class: 'bouton bouton--secondaire bouton--compact qui__plus', hidden: true,
    onClick: () => { etatCoupOeil.tout = true; afficher(); } });
  const rien = el('p', { class: 'qui__rien', hidden: true });
  const zone = el('div', { class: 'qui__resultats', id: prefixe + '-resultats', hidden: true },
    el('div', { class: 'qui__entete' }, compte, actions), grille, rien, plus);

  /* Une carte déjà montrée ne rejoue pas son entrée pendant la frappe :
     seules les nouvelles venues glissent en place. */
  let precedents = new Set();

  function codeAppareil(q) {
    const c = texte(q).toUpperCase().replace(/\s+/g, '');
    return (codesPole.has(c) || m.appareilsConnus.has(c)) ? c : '';
  }

  function afficher() {
    const q = champ.value;
    etatCoupOeil.requete = q;
    effacer.hidden = !q;
    const nq = normaliser(q);
    toutesPuces.forEach((b) =>
      b.setAttribute('aria-pressed', nq && normaliser(b.dataset.suggestion) === nq ? 'true' : 'false'));
    const termes = termesDe(q);
    if (!termes.length) {
      zone.hidden = true;
      compte.textContent = '';
      monter(grille);
      precedents = new Set();
      return;
    }
    zone.hidden = false;

    const code = codeAppareil(q);
    const competence = code ? '' : (m.toutesCompetences.find((c) => normaliser(c) === nq) || '');
    /* Un code d'appareil exact : ceux qui le suivent, et eux seuls — « H160 »
       ne ramène pas le H160M. Une compétence exacte (une suggestion, le
       lien d'un référent) : ceux qui la pratiquent, les référents d'abord —
       « Maquette numérique 3D » ne ramène pas qui a « Maquette numérique »
       et « Définition 3D ». */
    const trouves = code
      ? m.membres.filter((p) => porteurDe(p).toUpperCase() === code).sort(parRang).map((personne) => ({ personne, titres: null }))
      : competence
        ? index.map((e) => ({ e, c: e.competences.find((c) => c.n === nq) })).filter((x) => x.c)
          .sort((a, b) => RANG_NIVEAU[a.c.niveau] - RANG_NIVEAU[b.c.niveau] || parRang(a.e.personne, b.e.personne))
          .map((x) => ({ personne: x.e.personne, titres: [{ nom: x.c.nom, niveau: x.c.niveau }] }))
        : chercherPersonnes(index, termes);
    const montres = etatCoupOeil.tout ? trouves : trouves.slice(0, LIMITE_RESULTATS);

    const n = trouves.length;
    if (code) {
      monter(compte, el('strong', {}, pluriel(n, 'personne')), n > 1 ? ' suivent le ' : ' suit le ', code);
    } else if (competence) {
      const nbRef = trouves.filter((r) => r.titres && r.titres.some((t) => t.nom === competence && t.niveau === 'referent')).length;
      monter(compte, el('strong', {}, pluriel(n, 'personne')), n > 1 ? ' pratiquent « ' : ' pratique « ', competence, ' »',
        nbRef ? ' — ' + pluriel(nbRef, 'référent') + ' en tête' : '');
    } else {
      monter(compte, el('strong', {}, pluriel(n, 'personne')), ' pour « ', texte(q), ' »');
    }
    monter(actions,
      code && m.appareilsConnus.has(code)
        ? el('a', { class: 'coup-oeil__lien', href: 'index.html#porteur=' + encodeURIComponent(code) }, 'La fiche du ' + code, el('span', { 'aria-hidden': 'true' }, ' →'))
        : null,
      code ? boutonAjouter('Affecter quelqu’un au ' + code, (b) => ouvrirAffectation({ organigramme: m.organigramme, pole: pole.cle, code, declencheur: b })) : null,
      competence ? boutonAjouter('Un référent en ' + competence, (b) => ouvrirReferent({ organigramme: m.organigramme, pole: pole.cle, competence, competences: m.toutesCompetences, declencheur: b })) : null);

    monter(grille, montres.map((r, i) => cartePersonne(pole, m, r.personne, {
      termes: code ? [normaliser(code)] : termes, titres: r.titres, rang: i,
      entree: !precedents.has(r.personne),
      edition: code ? 'porteur' : undefined, porteur: code
    })));
    precedents = new Set(montres.map((r) => r.personne));
    grille.hidden = !n;
    rien.hidden = n > 0;
    rien.textContent = code
      ? 'Personne ne suit encore le ' + code + ' : contact à renseigner.'
      : 'Personne ne correspond à « ' + texte(q) + ' ». Essayez un mot plus court, une compétence ou un code d’appareil.';
    plus.hidden = montres.length >= n;
    plus.textContent = n - montres.length > 1 ? 'Voir les ' + (n - montres.length) + ' autres personnes' : 'Voir l’autre personne';
    direCompte();
  }

  function poser(valeur) {
    champ.value = valeur;
    etatCoupOeil.tout = false;
    afficher();
  }

  champ.addEventListener('input', () => { etatCoupOeil.tout = false; afficher(); });
  champ.addEventListener('keydown', (evt) => {
    if (evt.key === 'Escape' && champ.value) { evt.preventDefault(); poser(''); }
  });

  const bloc = el('section', { class: 'qui', 'aria-labelledby': prefixe + '-titre' },
    el('h3', { class: 'qui__titre', id: prefixe + '-titre' }, 'Qui peut m’aider ?'),
    el('p', { class: 'qui__aide', id: prefixe + '-aide' }, 'Tapez un nom, un rôle, une compétence ou un appareil : la réponse vient pendant la frappe.'),
    el('div', { class: 'qui__barre', role: 'search' },
      el('label', { class: 'visuellement-cache', for: champ.id }, 'Chercher une personne du pôle ' + pole.cle),
      svg('svg', { class: 'qui__loupe', viewBox: '0 0 20 20', 'aria-hidden': 'true', focusable: 'false' },
        svg('circle', { cx: '8.5', cy: '8.5', r: '5.75' }),
        svg('path', { d: 'M13 13 L17.5 17.5' })),
      champ, effacer),
    puces.length
      ? el('div', { class: 'qui__suggestions', role: 'group', 'aria-label': 'Suggestions' },
        el('span', { class: 'qui__suggestions-libelle' }, 'Souvent cherché'), puces)
      : null,
    porteursEdition,
    zone);
  afficher();
  return {
    element: bloc,
    /** Cherche `valeur`, et amène le champ sous les yeux. */
    chercher(valeur) {
      poser(valeur);
      bloc.scrollIntoView({ block: 'start', behavior: mouvementReduit() ? 'auto' : 'smooth' });
    }
  };
}

/* --- Les équipes ----------------------------------------------------------- */

/* Les appareils d'une squad, du plus suivi au moins suivi. */
function appareilsDe(membres) {
  const n = new Map();
  for (const p of membres) {
    const code = porteurDe(p);
    if (code && code.toUpperCase() !== TRANSVERSE) n.set(code, (n.get(code) || 0) + 1);
  }
  return [...n].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'fr', { numeric: true })).map(([code]) => code);
}

const VISAGES_MAX = 8;
const APPAREILS_MAX = 4;

function tuileEquipe(pole, m, s, idPanneau, surClic) {
  const lead = s.lead;
  const autres = s.membres.filter((p) => p !== lead).sort(parRang);
  const codes = appareilsDe(s.membres);
  const n = s.membres.length;
  return el('li', { class: 'equipe', dataset: { squad: s.id, teinte: String((s.rang % NB_TEINTES) + 1) } },
    el('button', {
      type: 'button', class: 'equipe__tuile', 'aria-expanded': 'false', 'aria-controls': idPanneau,
      'aria-label': s.nom + ', ' + pluriel(n, 'personne') + (lead ? ', lead ' + texte(lead.nom) : '')
        + (codes.length ? ', sur ' + codes.join(', ') : '') + ' : voir ses membres',
      onClick: surClic
    },
      el('span', { class: 'equipe__tete' },
        el('span', { class: 'equipe__nom' }, s.nom),
        el('span', { class: 'equipe__effectif' },
          el('span', { class: 'equipe__nombre' }, String(n)),
          el('span', { class: 'equipe__unite' }, n > 1 ? 'personnes' : 'personne'))),
      lead
        ? el('span', { class: 'equipe__lead' }, avatar(m, lead, 'md'),
          el('span', { class: 'equipe__lead-texte' },
            el('span', { class: 'equipe__lead-nom' }, texte(lead.nom)),
            el('span', { class: 'equipe__lead-role' }, /lead/i.test(texte(lead.poste)) ? texte(lead.poste) : 'Lead · ' + (texte(lead.poste) || 'rôle à renseigner'))))
        : el('span', { class: 'equipe__lead equipe__lead--vide' }, n ? 'Lead à désigner' : 'Personne pour le moment'),
      el('span', { class: 'equipe__pied' },
        autres.length
          ? el('span', { class: 'equipe__visages' },
            autres.slice(0, VISAGES_MAX).map((p) => avatar(m, p, 'xs')),
            autres.length > VISAGES_MAX ? el('span', { class: 'equipe__plus' }, '+' + (autres.length - VISAGES_MAX)) : null)
          : el('span', { class: 'equipe__visages' }),
        el('span', { class: 'equipe__chevron', 'aria-hidden': 'true' })),
      codes.length
        ? el('span', { class: 'equipe__appareils' },
          codes.slice(0, APPAREILS_MAX).map((c) => el('span', { class: 'equipe__appareil' }, c)),
          codes.length > APPAREILS_MAX ? el('span', { class: 'equipe__appareil equipe__appareil--plus' }, '+' + (codes.length - APPAREILS_MAX)) : null)
        : null));
}

function panneauEquipe(pole, m, s, id, fermer) {
  const membres = s.membres.slice().sort(parRang);
  const codes = appareilsDe(s.membres);
  return el('li', { class: 'equipe__panneau', dataset: { squad: s.id, teinte: String((s.rang % NB_TEINTES) + 1) } },
    el('div', { class: 'equipe__panneau-interieur', id, role: 'region', 'aria-label': 'Les membres de ' + s.nom },
      el('div', { class: 'equipe__panneau-tete' },
        el('div', { class: 'equipe__panneau-titres' },
          el('h4', { class: 'equipe__panneau-titre' }, s.nom),
          el('p', { class: 'equipe__panneau-resume' }, pluriel(membres.length, 'personne')
            + (s.lead ? ' · lead ' + texte(s.lead.nom) : '') + (codes.length ? ' · ' + codes.join(', ') : ''))),
        barreEdition({
          quoi: s.nom,
          surModifier: (b) => ouvrirSquad({ existant: { id: s.id, pole: pole.cle, nom: s.nom, rang: s.rang }, pole: pole.cle, declencheur: b }),
          surSupprimer: () => retirer('organigramme', 'squad', s.id, '« ' + s.nom + ' » retirée : ses membres attendent dans « À affecter ».')
        }),
        el('button', { type: 'button', class: 'equipe__fermer', 'aria-label': 'Refermer ' + s.nom, onClick: fermer },
          el('span', { 'aria-hidden': 'true' }, '×'))),
      membres.length
        ? el('ul', { class: 'qui__grille equipe__membres', role: 'list' },
          membres.map((p, i) => cartePersonne(pole, m, p, { rang: i, entree: true })))
        : el('p', { class: 'equipe__vide' }, 'Personne dans cette squad pour le moment.'),
      el('div', { class: 'equipe__panneau-pied edition-seulement' },
        boutonAjouter('Une personne dans ' + s.nom, (b) => ouvrirPersonne({ organigramme: m.organigramme, flotte: m.flotte, pole: pole.cle, squad: s.id, declencheur: b })))));
}

function blocEquipes(pole, m) {
  const code = pole.cle;
  const prefixe = 'equipes-' + code.toLowerCase();
  const grille = el('ul', { class: 'equipes__grille', role: 'list' });
  const tuiles = new Map();
  const idDe = (s) => prefixe + '-' + s.rang;
  let ouverte = '';

  m.squads.forEach((s) => {
    const li = tuileEquipe(pole, m, s, idDe(s), () => ouvrir(ouverte === s.id ? '' : s.id, true));
    tuiles.set(s.id, li);
    grille.appendChild(li);
  });

  /* Une seule squad ouverte : son panneau se pose sous la rangée de sa
     tuile (la grille est « dense » : les tuiles suivantes remontent
     combler la rangée), et se déplie. */
  function ouvrir(id, animer) {
    const reduit = !animer || mouvementReduit();
    const ancien = grille.querySelector('.equipe__panneau');
    if (ancien) {
      if (!id && !reduit && typeof ancien.animate === 'function') {
        ancien.classList.add('equipe__panneau--anime');
        const a = ancien.animate([{ blockSize: ancien.offsetHeight + 'px', opacity: 1 }, { blockSize: '0px', opacity: 0 }],
          { duration: dureeJeton('--duree', 220), easing: courbeJeton() });
        a.onfinish = () => ancien.remove();
      } else {
        ancien.remove();
      }
    }
    tuiles.forEach((li, cle) => li.querySelector('.equipe__tuile').setAttribute('aria-expanded', cle === id ? 'true' : 'false'));
    const s = id ? m.squads.find((x) => x.id === id) : null;
    ouverte = s ? s.id : '';
    etatCoupOeil.squad = ouverte;
    if (!s) return;
    const tuile = tuiles.get(s.id);
    const panneau = panneauEquipe(pole, m, s, idDe(s), () => {
      ouvrir('', true);
      tuile.querySelector('.equipe__tuile').focus();
    });
    tuile.after(panneau);
    if (reduit || typeof panneau.animate !== 'function') return;
    const hauteur = panneau.offsetHeight;
    panneau.classList.add('equipe__panneau--anime');
    const a = panneau.animate([{ blockSize: '0px', opacity: 0 }, { blockSize: hauteur + 'px', opacity: 1 }],
      { duration: dureeJeton('--duree-lente', 400), easing: courbeJeton() });
    const fin = () => panneau.classList.remove('equipe__panneau--anime');
    a.onfinish = fin; a.oncancel = fin;
    amenerEnVue(tuile, panneau, hauteur);
  }

  /* Le panneau déplié doit se voir sans perdre sa tuile de vue. */
  function amenerEnVue(tuile, panneau, hauteur) {
    const haut = tuile.getBoundingClientRect().top;
    const bas = panneau.getBoundingClientRect().top + hauteur + 24 - window.innerHeight;
    const marge = haut - 140;
    const delta = Math.min(bas, marge);
    if (delta > 0) window.scrollBy({ top: delta, behavior: 'smooth' });
  }

  grille.addEventListener('keydown', (evt) => {
    if (evt.key !== 'Escape' || !ouverte) return;
    const tuile = tuiles.get(ouverte);
    ouvrir('', true);
    if (tuile) tuile.querySelector('.equipe__tuile').focus();
  });

  if (etatCoupOeil.squad && tuiles.has(etatCoupOeil.squad)) ouvrir(etatCoupOeil.squad, false);

  const r = m.responsable;
  return el('section', { class: 'equipes', 'aria-labelledby': prefixe + '-titre' },
    teteBloc(prefixe + '-titre', 'Les équipes',
      r ? frag('Sous la responsabilité de ',
        el('span', { class: 'equipes__responsable', dataset: { teinte: 'pole' } },
          avatar(m, r, 'sm'),
          el('a', { class: 'equipes__responsable-nom', href: lienFiche(pole, r) }, texte(r.nom) || 'Nom à renseigner'),
          commandesPersonne(m, r, {})),
        m.squads.length ? ' — ouvrez une squad pour voir ses membres.' : '.')
        : 'Aucun responsable déclaré pour ce pôle.',
      el('a', { class: 'coup-oeil__lien', href: lienPole('organigramme.html', code) }, 'L’organigramme complet', el('span', { 'aria-hidden': 'true' }, ' →'))),
    m.squads.length ? grille : el('p', { class: 'coup-oeil__vide' }, 'Aucune squad déclarée pour ce pôle.'),
    el('div', { class: 'coup-oeil__ajouts edition-seulement' },
      boutonAjouter('Une personne', (b) => ouvrirPersonne({ organigramme: m.organigramme, flotte: m.flotte, pole: code, squad: m.squads.length ? m.squads[0].id : '', declencheur: b })),
      boutonAjouter('Une squad', (b) => ouvrirSquad({ pole: code, declencheur: b }))));
}

/* --- Les référents ---------------------------------------------------------- */

function blocReferents(pole, m, chercheur) {
  const code = pole.cle;
  const prefixe = 'referents-' + code.toLowerCase();
  const expertises = m.expertises;
  const nommer = boutonAjouter('Nommer un référent', (b) => ouvrirReferent({ organigramme: m.organigramme, pole: code, competences: m.toutesCompetences, declencheur: b }));
  const tete = teteBloc(prefixe + '-titre', 'Les référents',
    'La personne à solliciter en premier, compétence par compétence.', null);
  if (!expertises.length) {
    return el('section', { class: 'referents', 'aria-labelledby': prefixe + '-titre' }, tete,
      el('p', { class: 'coup-oeil__vide' }, 'Aucun référent nommé dans ce pôle pour le moment.'),
      el('div', { class: 'coup-oeil__ajouts edition-seulement' }, nommer));
  }

  const detail = el('div', { class: 'referents__detail', id: prefixe + '-detail', 'aria-live': 'polite' });
  let courant = '';

  function montrer(nom, animer) {
    const e = expertises.find((x) => x.nom === nom) || expertises[0];
    if (e.nom === courant) return;
    courant = e.nom;
    etatCoupOeil.competence = e.nom;
    index.querySelectorAll('.referents__puce').forEach((b) => b.setAttribute('aria-pressed', b.dataset.competence === e.nom ? 'true' : 'false'));
    const pratiquants = e.referents.length + e.confirmes + e.pratiquants;
    monter(detail,
      el('p', { class: 'referents__surtitre' }, e.referents.length > 1 ? 'Les référents en' : 'Le référent en'),
      el('h4', { class: 'referents__competence' }, e.nom),
      el('p', { class: 'referents__resume' }, [
        pluriel(e.referents.length, 'référent'),
        e.confirmes ? pluriel(e.confirmes, 'confirmé') : '',
        e.pratiquants ? e.pratiquants + ' en pratique' : ''
      ].filter(Boolean).join(' · ')),
      el('ul', { class: 'referents__gens', role: 'list' },
        /* La compétence est dans le titre : la carte dit plutôt où
           d'autre la personne est référente. */
        e.referents.slice().sort(parRang).map((p, i) => cartePersonne(pole, m, p, {
          rang: i, entree: true, edition: 'referent', competence: e.nom,
          titres: competencesDe(p).filter((c) => niveauDe(c) === 'referent' && texte(c.nom) !== e.nom)
            .slice(0, 2).map((c) => ({ nom: texte(c.nom), niveau: 'referent' }))
        }))),
      el('div', { class: 'referents__actions' },
        pratiquants > e.referents.length
          ? el('button', { type: 'button', class: 'referents__tous', onClick: () => chercheur.chercher(e.nom) },
            'Les ' + pratiquants + ' personnes qui la pratiquent', el('span', { 'aria-hidden': 'true' }, ' →'))
          : null,
        boutonAjouter('Un référent en ' + e.nom, (b) => ouvrirReferent({ organigramme: m.organigramme, pole: code, competence: e.nom, competences: m.toutesCompetences, declencheur: b }))));
    if (animer && !mouvementReduit() && typeof detail.animate === 'function') {
      detail.animate([{ opacity: 0.35, transform: 'translateY(4px)' }, { opacity: 1, transform: 'none' }],
        { duration: dureeJeton('--duree', 220), easing: courbeJeton() });
    }
  }

  /* À la souris, s'attarder sur une compétence suffit ; un passage rapide
     vers le détail ne change rien en chemin. Seul un vrai mouvement
     compte : une puce qui glisse sous une souris immobile (un panneau
     d'équipe qui se referme au-dessus) ne choisit rien. */
  let attente = 0;
  let visee = '';
  let position = '';
  const viser = (evt, nom) => {
    if (evt.pointerType !== 'mouse') return;
    const ici = evt.clientX + ' ' + evt.clientY;
    if (ici === position) return;
    position = ici;
    if (visee === nom) return;
    visee = nom;
    clearTimeout(attente);
    attente = setTimeout(() => montrer(nom, true), 180);
  };
  const index = el('ul', { class: 'referents__index', role: 'list', 'aria-label': 'Les compétences qui ont un référent' },
    expertises.map((e) => el('li', {},
      el('button', {
        type: 'button', class: 'referents__puce', 'aria-pressed': 'false', 'aria-controls': detail.id,
        dataset: { competence: e.nom },
        onClick: (evt) => {
          montrer(e.nom, true);
          /* Sur une rangée qui défile, la compétence choisie vient au milieu. */
          evt.currentTarget.scrollIntoView({ block: 'nearest', inline: 'center', behavior: mouvementReduit() ? 'auto' : 'smooth' });
        },
        onPointerMove: (evt) => viser(evt, e.nom),
        onPointerLeave: () => { clearTimeout(attente); visee = ''; }
      },
        el('span', { class: 'referents__puce-nom' }, e.nom),
        el('span', { class: 'referents__visages', 'aria-hidden': 'true' },
          e.referents.slice(0, 3).map((p) => avatar(m, p, 'xxs')))))));

  montrer(expertises.some((e) => e.nom === etatCoupOeil.competence) ? etatCoupOeil.competence : expertises[0].nom, false);

  return el('section', { class: 'referents', 'aria-labelledby': prefixe + '-titre' },
    tete,
    el('div', { class: 'referents__corps' }, index, detail),
    el('div', { class: 'coup-oeil__ajouts edition-seulement' }, nommer));
}

/* --- L'assemblage ------------------------------------------------------------ */

function rendreAnnuaire(pole, m, conteneur) {
  const chercheur = blocChercheur(pole, m);
  monter(conteneur,
    el('div', { class: 'coup-oeil' },
      ligneChiffres(m),
      chercheur.element,
      blocEquipes(pole, m),
      blocReferents(pole, m, chercheur)));
}

/* -------------------------------------------------------------------------
   5. Les documents du pôle : les plus récents, en vigueur
   ------------------------------------------------------------------------- */

async function chargerDocuments(code) {
  const [docs, orga] = await Promise.allSettled([chargerDonnees('documents'), chargerDonnees('organigramme')]);
  if (docs.status !== 'fulfilled') throw docs.reason;
  const bloc = orga.status === 'fulfilled' ? blocOrganigramme(orga.value, code) : null;
  const membres = bloc ? membresDuBloc(bloc) : [];
  const liste = documentsDuPole(docs.value, code, membres);
  const enVigueur = liste.filter((d) => !texte(d.remplacePar))
    .sort((a, b) => texte(b.maj).localeCompare(texte(a.maj)));
  return { code, docs: docs.value, enVigueur, membres, tousMembres: orga.status === 'fulfilled' ? aplatirOrganigramme(orga.value).personnes : membres };
}

const MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
function dateCourte(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(texte(iso));
  return m ? Number(m[3]) + ' ' + MOIS_COURTS[Number(m[2]) - 1] + ' ' + m[1] : '';
}

/* Les documents du pôle : les huit plus récents en vigueur ; au-dessus,
   un filtre par type et une recherche dans le bloc — alors tous les
   documents du pôle qui correspondent s'affichent. Chaque ligne s'ouvre
   directement sur le document quand il a un lien, et un document mis à
   jour depuis moins de trente jours porte « Nouveau ». */
function rendreDocuments(pole, m, conteneur) {
  const MAX = 8;
  const tous = m.enVigueur;
  const porteurDuDoc = (d) => m.tousMembres.find((p) => normaliser(p.nom) === normaliser(d.porteur)) || null;
  const recent = (d) => {
    const t = Date.parse(texte(d.maj));
    return Number.isFinite(t) && (Date.now() - t) / 86400000 <= 30 && t <= Date.now() + 86400000;
  };
  const ligne = (d) => {
    const porteur = porteurDuDoc(d);
    const lien = texte(d.lien);
    return el('li', { class: 'pole-doc', dataset: { type: texte(d.type) || 'Document' } },
      el('span', { class: 'pole-doc__type badge badge--contour' }, texte(d.type) || 'Document'),
      el('span', { class: 'pole-doc__intitule' },
        el('a', { class: 'pole-doc__titre', href: 'docsearch.html#q=' + encodeURIComponent(texte(d.reference) || texte(d.titre)) }, texte(d.titre)),
        recent(d) ? el('span', { class: 'pole-doc__nouveau' }, 'Nouveau') : null),
      el('span', { class: 'pole-doc__ref mono' }, texte(d.reference)),
      el('span', { class: 'pole-doc__porteur' }, porteur
        ? el('a', { href: lienFiche(pole, porteur) }, texte(porteur.nom))
        : (texte(d.porteur) || 'Porteur à renseigner')),
      el('time', { class: 'pole-doc__date', datetime: texte(d.maj) || null }, dateCourte(d.maj) || 'date à renseigner'),
      /^https?:\/\//i.test(lien)
        ? el('a', { class: 'pole-doc__ouvrir', href: lien, target: '_blank', rel: 'noopener noreferrer', 'aria-label': 'Ouvrir le document : ' + texte(d.titre) }, 'Ouvrir ↗')
        : el('span', { class: 'pole-doc__ouvrir pole-doc__ouvrir--vide' }),
      /* Une ligne de document a la place : « Modifier » et
         « Supprimer » s'y écrivent en toutes lettres. */
      barreEdition({
        classe: 'pole-doc__edition',
        quoi: texte(d.titre),
        surModifier: (b) => ouvrirDocument({ existant: d, documents: m.docs, personnes: m.tousMembres, pole: pole.cle, declencheur: b }),
        surSupprimer: () => retirer('documents', 'document', texte(d.id), 'Document retiré du fonds.')
      }));
  };

  let type = '';
  let requete = '';
  const liste = el('ul', { class: 'pole-docs__liste', role: 'list' });
  const resume = el('p', { class: 'pole-docs__resume', 'aria-live': 'polite' });
  const remplir = () => {
    const q = normaliser(requete);
    const filtres = tous.filter((d) => (!type || (texte(d.type) || 'Document') === type)
      && (!q || normaliser([d.titre, d.reference, d.porteur, d.description, [].concat(d.metier || []).join(' '), [].concat(d.motsCles || []).join(' ')].join(' ')).includes(q)));
    const actif = type || q;
    const montres = actif ? filtres : filtres.slice(0, MAX);
    monter(liste, montres.length ? montres.map(ligne)
      : el('li', { class: 'pole-docs__vide' }, 'Aucun document du pôle ne correspond.'));
    resume.textContent = actif
      ? filtres.length + ' document' + (filtres.length > 1 ? 's' : '') + ' sur ' + tous.length
      : 'Les ' + Math.min(MAX, tous.length) + ' plus récents sur ' + tous.length;
  };

  const types = [...new Set(tous.map((d) => texte(d.type) || 'Document'))].sort((x, y) => x.localeCompare(y, 'fr'));
  const puces = el('div', { class: 'facettes pole-docs__types', role: 'group', 'aria-label': 'Filtrer par type' },
    [''].concat(types).map((t) => el('button', {
      type: 'button', class: 'facette facette--compacte', 'aria-pressed': t === '' ? 'true' : 'false', dataset: { type: t },
      onClick: (evt) => {
        type = t;
        puces.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', b === evt.currentTarget ? 'true' : 'false'));
        remplir();
      }
    }, t || 'Tous')));
  const champ = el('input', {
    type: 'search', class: 'champ__controle pole-docs__recherche', placeholder: 'Chercher dans les documents du pôle…',
    'aria-label': 'Chercher dans les documents du pôle',
    onInput: debounce((evt) => { requete = evt.target.value; remplir(); }, 150)
  });

  remplir();
  monter(conteneur,
    el('div', { class: 'pole-docs' },
      tous.length ? el('div', { class: 'pole-docs__outils' }, puces, champ) : null,
      tous.length ? resume : null,
      tous.length ? liste : el('p', { class: 'texte-doux sans-marge' }, 'Aucun document rattaché à ce pôle pour le moment.'),
      el('div', { class: 'pole-docs__pied' },
        el('a', { class: 'bouton bouton--secondaire bouton--compact', href: 'docsearch.html#pole=' + encodeURIComponent(pole.cle) },
          'Tous les documents du pôle' + (tous.length ? ' (' + tous.length + ')' : '')),
        boutonAjouter('Ajouter un document', (b) => ouvrirDocument({ documents: m.docs, personnes: m.tousMembres, pole: pole.cle, declencheur: b })))));
}

/* -------------------------------------------------------------------------
   6. FAQ
   ------------------------------------------------------------------------- */

function questionsDuPole(donnees, code) {
  verifierForme(donnees, { questions: 'tableau' }, 'faq.json');
  const toutes = donnees.questions.filter((q) => q && typeof q === 'object' && texte(q.question));
  return {
    pole: toutes.filter((q) => texte(q.pole).toUpperCase() === code),
    service: toutes.filter((q) => texte(q.pole).toUpperCase() === 'ETII')
  };
}

function enregistrerDemande(question, contexte, pole) {
  const brut = stockage.lire(CLE_STOCKAGE_FAQ, []);
  const liste = Array.isArray(brut) ? brut : [];
  liste.unshift({
    id: 'q-' + Date.now(),
    question, contexte: contexte || null, pole, date: new Date().toISOString()
  });
  return stockage.ecrire(CLE_STOCKAGE_FAQ, liste);
}

function ouvrirDemandeExpert(pole, declencheur, texteInitial) {
  let champ = null; let contexte = null; let erreur = null;
  ouvrirModale({
    titre: 'Interroger un expert du pôle ' + pole.cle,
    classe: 'modale--etroite',
    declencheur: declencheur || null,
    contenu: () => {
      erreur = el('p', { class: 'champ__erreur', hidden: true }, 'Écrivez votre question avant d’envoyer.');
      champ = el('textarea', { class: 'champ__controle', id: 'demande-question', rows: 5,
        placeholder: 'Programme, jalon, problématique technique…' });
      champ.value = texte(texteInitial);
      contexte = el('input', { class: 'champ__controle', id: 'demande-contexte', type: 'text',
        placeholder: 'Document, appareil, référence… (facultatif)' });
      return frag(
        el('p', { class: 'texte-doux texte-sm sans-marge' },
          'Votre question rejoint la liste des questions en attente de la base de '
          + 'connaissances, dans ce navigateur. Aucun envoi réseau n’a lieu.'),
        el('div', { class: 'champ' },
          el('label', { class: 'champ__etiquette', for: 'demande-question' }, 'Votre question'),
          champ, erreur),
        el('div', { class: 'champ' },
          el('label', { class: 'champ__etiquette', for: 'demande-contexte' }, 'Contexte'),
          contexte));
    },
    actions: [
      { libelle: 'Annuler', variante: 'secondaire', ferme: true },
      { libelle: 'Envoyer aux experts', variante: 'principal', onClick: () => {
        const q = texte(champ && champ.value);
        if (!q) { if (erreur) erreur.hidden = false; if (champ) champ.focus(); return false; }
        const ok = enregistrerDemande(q, texte(contexte && contexte.value), pole.cle);
        toast(ok ? 'Question enregistrée pour les experts du pôle ' + pole.cle + '.'
                 : 'Ce navigateur refuse le stockage local : la question n’a pas pu être conservée.',
              ok ? 'succes' : 'alerte');
        annoncer('Question enregistrée.');
        return true;
      } }
    ]
  });
}

function rendreFaq(pole, groupes, conteneur) {
  const versElement = (q, groupe) => ({
    id: texte(q.id) || ('q-' + groupe + '-' + Math.random().toString(36).slice(2)),
    groupe, titre: texte(q.question), meta: texte(q.categorie) || '',
    recherche: [q.reponse].concat(Array.isArray(q.motsCles) ? q.motsCles : []).map(texte),
    source: q,
    corps: () => frag(
      el('p', {}, texte(q.reponse) || 'Réponse à renseigner.'),
      Array.isArray(q.motsCles) && q.motsCles.length
        ? el('div', { class: 'liseuse__mots' }, q.motsCles.map((m) => el('span', { class: 'badge badge--contour' }, texte(m))))
        : null)
  });
  const elements = groupes.pole.map((q) => versElement(q, 'pole')).concat(groupes.service.map((q) => versElement(q, 'service')));

  const boutonExpert = el('button', { type: 'button', class: 'bouton bouton--principal', onClick: (evt) => {
    const champ = conteneur.querySelector('.liseuse__recherche');
    ouvrirDemandeExpert(pole, evt.currentTarget, champ ? champ.value : '');
  } }, 'Interroger un expert');

  /* Les questions du pôle, et l'expert si elles ne suffisent pas : rien
     d'autre — la base complète a sa page, ce n'est pas ici qu'on y va. */
  const pied = el('div', { class: 'liseuse__pied' },
    el('div', {},
      el('p', { class: 'liseuse__pied-titre' }, 'Une question spécifique ?'),
      el('p', {}, 'Si ces questions ne couvrent pas votre périmètre, sollicitez ',
        el('a', { href: '#section-reperes' }, 'les référents du pôle'), ' ou posez-la aux experts.')),
    el('div', { class: 'rangee rangee--serree' },
      boutonAjouter('Ajouter une question', (b) => ouvrirQuestion({ pole: pole.cle, declencheur: b })),
      boutonExpert));

  monter(conteneur,
    lecteur({
      id: 'faq-' + pole.cle.toLowerCase(),
      elements,
      groupes: [{ cle: 'pole', titre: 'Pôle ' + pole.cle }, { cle: 'service', titre: 'Service ETII' }],
      titreListe: 'Questions fréquentes',
      placeholder: 'Rechercher une question technique…',
      vide: 'Aucune question publiée pour ce pôle.',
      entete: (item) => frag(
        el('span', { class: 'badge badge--neutre' }, item.groupe === 'pole' ? 'Pôle ' + pole.cle : 'Service ETII'),
        item.meta ? el('span', { class: 'badge badge--contour' }, item.meta) : null),
      actions: (item) => barreEdition({
        quoi: item.titre,
        surModifier: (b) => ouvrirQuestion({ existant: item.source, declencheur: b }),
        surSupprimer: () => retirer('faq', 'question', texte(item.source.id), 'Question retirée de la base.')
      }),
      pied
    }));
}

/* -------------------------------------------------------------------------
   7. En-tête, sommaire, refus
   ------------------------------------------------------------------------- */

function rendreEntete(pole) {
  const titre = document.getElementById('pole-titre');
  if (titre) titre.textContent = pole.cle;
  try { document.title = pole.cle + ' — ' + pole.metaphore + ' — ETII Hub'; } catch (_e) { /* ignoré */ }
}

function refuser(brut) {
  const hote = document.getElementById('pole-alerte');
  const codes = Object.keys(POLES);
  const message = brut
    ? 'Le paramètre « ' + brut + ' » ne désigne aucun pôle du service.'
    : 'Cette page n’indique aucun pôle : son attribut data-pole est absent.';
  if (hote) {
    hote.hidden = false;
    monter(hote,
      el('div', { class: 'etat-vide etat-vide--encadre etat-vide--erreur', role: 'alert' },
        el('span', { class: 'etat-vide__illustration', 'aria-hidden': 'true' }, '!'),
        el('p', { class: 'etat-vide__titre' }, 'Espace de pôle inconnu'),
        el('p', { class: 'etat-vide__texte' },
          message + ' Les espaces de pôle sont ' + codes.join(', ') + '. Le niveau service, lui, est le tableau de bord ETII.'),
        el('div', { class: 'etat-vide__actions' },
          frag(codes.map((code) => el('a', { class: 'bouton bouton--secondaire', href: code.toLowerCase() + '.html' }, code)),
            el('a', { class: 'bouton bouton--principal', href: 'index.html' }, 'Tableau de bord ETII')))));
  }
  document.querySelectorAll('[data-section-pole]').forEach((s) => s.remove());
  const sommaire = document.querySelector('.page-sommaire');
  if (sommaire) sommaire.remove();
  console.error('[pole] ' + message);
}

/* -------------------------------------------------------------------------
   8. Démarrage
   ------------------------------------------------------------------------- */

initTheme();

const PARAMETRE = (document.body && document.body.dataset ? String(document.body.dataset.pole || '') : '').trim();
const POLE = Object.prototype.hasOwnProperty.call(POLES, PARAMETRE.toUpperCase()) ? POLES[PARAMETRE.toUpperCase()] : null;

/* Les crédits des photos : une obligation de licence, tenue par une seule
   fenêtre au pied de page plutôt que sous chaque communication. */
deleguer(document, '[data-credits-photos]', 'click', async (evt, lien) => {
  evt.preventDefault();
  let communications = null;
  try { communications = await chargerCommunications(); } catch (_e) { communications = null; }
  ouvrirModale({
    titre: 'Crédits photos',
    declencheur: lien,
    contenu: creditsCommunications(communications)
      || el('p', { class: 'texte-doux sans-marge' }, 'Aucune photo créditée dans les communications pour le moment.')
  });
});

initNav(POLE ? POLE.cle.toLowerCase() + '.html' : '');

if (!POLE) {
  refuser(PARAMETRE);
} else {
  rendreEntete(POLE);
  suivreSommaire();
  revelerAuDefilement(document.querySelectorAll('.pile--section > section > *'));

  chargerCommunicationDuPole(POLE);
  chargerAgendaDuPole(POLE);

  const chargerSectionAnnuaire = () => avecEtat('#zone-reperes', () => chargerAnnuaire(POLE.cle),
    (modele, conteneur) => rendreAnnuaire(POLE, modele, conteneur), {
      squelette: 3, compact: true,
      texteChargement: 'Chargement de l’équipe du pôle…',
      titreErreur: 'Équipe indisponible',
      titreVide: 'Aucune équipe déclarée',
      texteVide: 'Ce pôle n’a encore ni responsable ni squad dans l’organigramme du service.'
    });
  chargerSectionAnnuaire();

  const chargerSectionDocuments = () => avecEtat('#zone-documents', () => chargerDocuments(POLE.cle),
    (modele, conteneur) => rendreDocuments(POLE, modele, conteneur), {
      squelette: 2, compact: true,
      texteChargement: 'Chargement des documents du pôle…',
      titreErreur: 'Documents indisponibles',
      estVide: () => false
    });
  chargerSectionDocuments();

  const chargerSectionFaq = () => avecEtat('#zone-faq', async () => questionsDuPole(await chargerDonnees('faq'), POLE.cle),
    (groupes, conteneur) => rendreFaq(POLE, groupes, conteneur), {
      squelette: 3, compact: true,
      texteChargement: 'Chargement des questions du pôle…',
      titreErreur: 'Questions indisponibles',
      titreVide: 'Aucune question',
      texteVide: 'Les questions fréquentes de ce pôle apparaîtront ici.',
      /* Jamais « vide » : en mode édition, la FAQ garde son bouton d'ajout. */
      estVide: () => false
    });
  chargerSectionFaq();

  installerEdition();
  /* Une modification enregistrée redessine les sections qui en dépendent :
     data.js a déjà oublié le jeu, la section le relit. */
  abonnerModifications((jeu) => {
    if (jeu === 'communications') { chargerCommunicationDuPole(POLE); chargerAgendaDuPole(POLE); }
    if (jeu === 'organigramme' || jeu === 'flotte') { chargerSectionAnnuaire(); chargerSectionDocuments(); }
    if (jeu === 'documents') { chargerSectionDocuments(); chargerSectionAnnuaire(); }
    if (jeu === 'faq') chargerSectionFaq();
  });
}

/* =========================================================================
   ETII Hub — Espace de pôle (etiia.html, etiie.html, etiii.html)

   Une seule page, trois fois, paramétrée par <body data-pole="…">. Quatre
   sections, dans l'ordre de lecture :
     1. COMMUNICATION  — le kiosque du pôle (kiosque.js), le même qu'au
                         niveau service ;
     2. EN UN COUP D'ŒIL — les chiffres du pôle en une ligne ; les
                         équipes, en tuiles qui s'ouvrent sur place ; les
                         référents du pôle, chacun avec son appareil ;
     3. DOCUMENTS      — les documents du pôle les plus récents, en vigueur ;
     4. FAQ            — les questions du pôle, et la demande aux experts.

   Tout se modifie dans la page, en mode édition (edition.js) : les
   communications, l'organigramme (personnes, squads), les documents, les
   questions. Chaque section se redessine seule après un enregistrement.

   Rien n'est inventé : chaque section ne montre que ce que les fichiers
   déclarent pour ce pôle (organigramme.json, flotte.json, documents.json).
   Tout le DOM est construit avec el().
   ========================================================================= */

import { el, frag, monter, debounce, deleguer, mouvementReduit, dureeJeton, initTheme, initNav, suivreSommaire, revelerAuDefilement, ouvrirModale, stockage, toast, annoncer } from './ui.js';
import { initiales } from './portraits.js';
import { installerEdition, barreEdition, boutonAjouter } from './edition.js';
import { abonnerModifications, supprimerElement, aplatirOrganigramme } from './modifications.js';
import { modifierCommunication, supprimerDossier, ouvrirPersonne, ouvrirSquad, ouvrirDocument, ouvrirQuestion, ouvrirReferent, retirerReferent, estReferent, ouvrirRendezVous } from './edition-contenus.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { kiosque, dossiersDepuisCommunications, noteOrigine } from './kiosque.js';
import { lecteur } from './lecteur.js';
import { agenda } from './agenda.js';
import { chargerCommunications } from './communications.js';
import { demandesPartagees, envoyerDemande } from './demandes.js';
import { pastillesSecurite } from './sensibilite.js';
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

/* Les référents du pôle : les personnes à solliciter en premier. */
function referentsDuBloc(bloc) {
  return membresDuBloc(bloc).filter(estReferent);
}

/* -------------------------------------------------------------------------
   4. Le pôle en un coup d'œil : les équipes, les référents

   Deux blocs :
     - « Les équipes » : une tuile par squad — son lead, ses visages, ses
       appareils — qui s'ouvre sur place, une à la fois, sur ses membres ;
     - « Les référents » : les personnes à solliciter en premier, sans
       plus — le pôle a des référents, pas un référent par compétence —,
       chacun avec l'appareil qu'il suit.
   Les chiffres du pôle tiennent en une ligne, au-dessus. En mode édition,
   l'organigramme du pôle se modifie ici même : personnes, squads,
   référents.
   ------------------------------------------------------------------------- */

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
  const referents = referentsDuBloc(bloc);
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
    referents,
    nbReferents: referents.length,
    /* Les codes qui ont une fiche sur le tableau de bord. */
    appareilsConnus: new Set(laFlotte ? laFlotte.flotte.filter((a) => a && typeof a === 'object' && texte(a.code))
      .map((a) => texte(a.code).toUpperCase()) : []),
    documents: docs.status === 'fulfilled' ? documentsDuPole(docs.value, code, membres).filter((d) => !texte(d.remplacePar)).length : null
  };
}

/* L'état du bloc survit à un redessin — une modification enregistrée en
   mode édition redessine la section — : la squad ouverte. */
const etatCoupOeil = { equipes: '' };

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

/* Un appareil : un lien vers sa fiche sur le tableau de bord quand la
   flotte le connaît ; « Transverse » n'est pas un appareil. */
function appareilPuce(m, code) {
  const cle = texte(code).toUpperCase();
  if (cle === TRANSVERSE) return el('span', { class: 'appareil-puce appareil-puce--transverse' }, 'Transverse');
  return m.appareilsConnus.has(cle)
    ? el('a', { class: 'appareil-puce', href: lienPorteur(code), title: 'La fiche du ' + texte(code) }, texte(code))
    : el('span', { class: 'appareil-puce' }, texte(code));
}

/* La fiche d'un appareil, dans la section Porteurs du tableau de bord. */
function lienPorteur(code) { return 'index.html#porteur=' + encodeURIComponent(texte(code)); }

/* Les commandes d'une personne, en mode édition. Selon l'endroit,
   « retirer » n'a pas le même sens : de l'organigramme, ou du titre de
   référent. */
function commandesPersonne(m, personne, o) {
  const soi = Object.assign({}, personne, placementDe(m, personne));
  const nom = texte(personne.nom);
  return barreEdition({
    classe: 'barre-edition--compacte',
    quoi: nom + (o.edition === 'referent' ? ', référent' : ''),
    surModifier: (b) => ouvrirPersonne({ existant: soi, organigramme: m.organigramme, flotte: m.flotte, declencheur: b }),
    surSupprimer: o.edition === 'referent'
      ? () => agir(retirerReferent(soi), '« ' + nom + ' » n’est plus référent.')
      : () => retirer('organigramme', 'personne', texte(personne.id), '« ' + nom + ' » ne figure plus dans l’organigramme.')
  });
}

/**
 * Une personne, en carte : ses initiales, son nom (vers sa fiche), son
 * rôle et sa squad, l'étiquette « référent » s'il y a lieu, et l'appareil
 * qu'elle suit.
 * @param {object} o  { rang, entree, edition }
 */
function cartePersonne(pole, m, personne, o) {
  const opt = o || {};
  const squad = m.squadDe.get(personne) || null;
  const code = porteurDe(personne);
  return el('li', {
    class: ['personne-carte', opt.entree ? 'personne-carte--entree' : null],
    dataset: { teinte: teinteDe(m, personne), personne: texte(personne.id) },
    style: { '--i': Math.min(opt.rang || 0, 11) }
  },
    avatar(m, personne),
    el('div', { class: 'personne-carte__corps' },
      el('p', { class: 'personne-carte__ligne' },
        el('a', { class: 'personne-carte__nom', href: lienFiche(pole, personne) }, texte(personne.nom) || 'Nom à renseigner'),
        estLead(personne) ? el('span', { class: 'personne-carte__badge' }, 'lead') : null,
        opt.edition !== 'referent' && estReferent(personne) ? el('span', { class: 'personne-carte__badge personne-carte__badge--referent' }, 'référent') : null),
      el('p', { class: 'personne-carte__role' },
        el('span', {}, texte(personne.poste) || 'Rôle à renseigner'),
        squad ? el('span', { class: 'personne-carte__squad' }, squad.nom) : null),
      code ? el('p', { class: 'personne-carte__puces' }, appareilPuce(m, code)) : null),
    commandesPersonne(m, personne, opt));
}

/* Une ligne de sous-bloc : le titre, une phrase, et à droite ce qui suit. */
function teteBloc(id, titre, sousTitre, aDroite) {
  return el('header', { class: 'coup-oeil__tete' },
    el('div', { class: 'coup-oeil__tete-texte' },
      el('h3', { class: 'coup-oeil__titre', id }, titre),
      sousTitre ? el('div', { class: 'coup-oeil__sous-titre' }, sousTitre) : null),
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

/* --- Des tuiles qui s'ouvrent sur place ------------------------------------ */

/**
 * Une grille de tuiles dont une seule s'ouvre à la fois : son panneau se
 * pose sous la rangée de la tuile (la grille est « dense » : les tuiles
 * suivantes remontent combler la rangée), et se déplie.
 * @param {{prefixe: string, cleEtat: string, elements: object[], cle: (x) => string,
 *          tuile: (x, idPanneau, surClic) => HTMLElement,
 *          panneau: (x, idPanneau, fermer) => HTMLElement}} o
 */
function grilleDepliable(o) {
  const grille = el('ul', { class: 'equipes__grille', role: 'list' });
  const tuiles = new Map();
  const idDe = (i) => o.prefixe + '-' + i;
  let ouverte = '';

  o.elements.forEach((x, i) => {
    const cle = o.cle(x);
    const li = o.tuile(x, idDe(i), () => ouvrir(ouverte === cle ? '' : cle, true));
    li.dataset.rangTuile = String(i);
    tuiles.set(cle, li);
    grille.appendChild(li);
  });

  function ouvrir(cle, animer) {
    const reduit = !animer || mouvementReduit();
    const ancien = grille.querySelector('.equipe__panneau');
    if (ancien) {
      if (!cle && !reduit && typeof ancien.animate === 'function') {
        ancien.classList.add('equipe__panneau--anime');
        const a = ancien.animate([{ blockSize: ancien.offsetHeight + 'px', opacity: 1 }, { blockSize: '0px', opacity: 0 }],
          { duration: dureeJeton('--duree', 220), easing: courbeJeton() });
        a.onfinish = () => ancien.remove();
      } else {
        ancien.remove();
      }
    }
    tuiles.forEach((li, c) => li.querySelector('.equipe__tuile').setAttribute('aria-expanded', c === cle ? 'true' : 'false'));
    const x = cle ? o.elements.find((e) => o.cle(e) === cle) : null;
    ouverte = x ? cle : '';
    etatCoupOeil[o.cleEtat] = ouverte;
    if (!x) return;
    const tuile = tuiles.get(cle);
    const panneau = o.panneau(x, idDe(tuile.dataset.rangTuile), () => {
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
    const delta = Math.min(bas, haut - 140);
    if (delta > 0) window.scrollBy({ top: delta, behavior: 'smooth' });
  }

  grille.addEventListener('keydown', (evt) => {
    if (evt.key !== 'Escape' || !ouverte) return;
    const tuile = tuiles.get(ouverte);
    ouvrir('', true);
    if (tuile) tuile.querySelector('.equipe__tuile').focus();
  });

  if (etatCoupOeil[o.cleEtat] && tuiles.has(etatCoupOeil[o.cleEtat])) ouvrir(etatCoupOeil[o.cleEtat], false);
  return grille;
}

/* Des visages côte à côte, lisibles en entier, puis « +N » ; le nom de
   chacun en infobulle ; au survol de la tuile, ils se lèvent l'un après
   l'autre (--i). */
const VISAGES_MAX = 6;
const APPAREILS_MAX = 4;
function visages(m, gens) {
  return el('span', { class: 'equipe__visages' },
    gens.slice(0, VISAGES_MAX).map((p, i) => {
      const a = avatar(m, p, 'xs');
      a.title = texte(p.nom);
      a.style.setProperty('--i', String(i));
      return a;
    }),
    gens.length > VISAGES_MAX ? el('span', { class: 'equipe__plus' }, '+' + (gens.length - VISAGES_MAX)) : null);
}

/* Le haut d'une tuile : son nom, son effectif. */
function teteTuile(nom, n) {
  return el('span', { class: 'equipe__tete' },
    el('span', { class: 'equipe__nom' }, nom),
    el('span', { class: 'equipe__effectif' },
      el('span', { class: 'equipe__nombre' }, String(n)),
      el('span', { class: 'equipe__unite' }, n > 1 ? 'personnes' : 'personne')));
}

/* Le panneau d'une tuile ouverte : un titre, une ligne, des cartes. */
function panneauTuile(o) {
  return el('li', { class: ['equipe__panneau', o.classe || null], dataset: o.dataset || {} },
    el('div', { class: 'equipe__panneau-interieur', id: o.id, role: 'region', 'aria-label': o.libelle },
      /* Les commandes d'édition sous le titre, à gauche : loin de la croix
         qui referme le panneau, à droite. */
      el('div', { class: 'equipe__panneau-tete' },
        el('div', { class: 'equipe__panneau-titres' },
          el('h4', { class: 'equipe__panneau-titre' }, o.titre),
          el('p', { class: 'equipe__panneau-resume' }, o.resume),
          o.edition || null),
        o.lien || null,
        el('button', { type: 'button', class: 'equipe__fermer', 'aria-label': 'Refermer ' + o.titre, onClick: o.fermer },
          el('span', { 'aria-hidden': 'true' }, '×'))),
      o.cartes.length
        ? el('ul', { class: 'personnes__grille equipe__membres', role: 'list' }, o.cartes)
        : el('p', { class: 'equipe__vide' }, o.vide),
      o.pied ? el('div', { class: 'equipe__panneau-pied edition-seulement' }, o.pied) : null));
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

/* Le lead, au nom suivi de l'étiquette « lead » comme sur les cartes ; son
   rôle ne s'écrit que s'il dit autre chose que « Lead … ». */
function leadDeTuile(m, lead, n) {
  if (!lead) return el('span', { class: 'equipe__lead equipe__lead--vide' }, n ? 'Lead à désigner' : 'Personne pour le moment');
  const poste = texte(lead.poste);
  return el('span', { class: 'equipe__lead' }, avatar(m, lead, 'md'),
    el('span', { class: 'equipe__lead-texte' },
      el('span', { class: 'equipe__lead-ligne' },
        el('span', { class: 'equipe__lead-nom' }, texte(lead.nom)),
        el('span', { class: 'personne-carte__badge' }, 'lead')),
      poste && !/lead/i.test(poste) ? el('span', { class: 'equipe__lead-role' }, poste) : null));
}

function tuileEquipe(m, s, idPanneau, surClic) {
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
      teteTuile(s.nom, n),
      leadDeTuile(m, lead, n),
      el('span', { class: 'equipe__pied' }, visages(m, autres), el('span', { class: 'equipe__chevron', 'aria-hidden': 'true' })),
      codes.length
        ? el('span', { class: 'equipe__appareils' },
          codes.slice(0, APPAREILS_MAX).map((c) => el('span', { class: 'equipe__appareil' }, c)),
          codes.length > APPAREILS_MAX ? el('span', { class: 'equipe__appareil equipe__appareil--plus' }, '+' + (codes.length - APPAREILS_MAX)) : null)
        : null));
}

function blocEquipes(pole, m) {
  const code = pole.cle;
  const prefixe = 'equipes-' + code.toLowerCase();
  const grille = grilleDepliable({
    prefixe, cleEtat: 'equipes', elements: m.squads, cle: (s) => s.id,
    tuile: (s, id, surClic) => tuileEquipe(m, s, id, surClic),
    panneau: (s, id, fermer) => {
      const membres = s.membres.slice().sort(parRang);
      const codes = appareilsDe(s.membres);
      return panneauTuile({
        id, fermer, titre: s.nom, libelle: 'Les membres de ' + s.nom,
        dataset: { squad: s.id, teinte: String((s.rang % NB_TEINTES) + 1) },
        resume: pluriel(membres.length, 'personne') + (s.lead ? ' · lead ' + texte(s.lead.nom) : '') + (codes.length ? ' · ' + codes.join(', ') : ''),
        edition: barreEdition({
          classe: 'equipe__panneau-edition',
          quoi: s.nom,
          surModifier: (b) => ouvrirSquad({ existant: { id: s.id, pole: code, nom: s.nom, rang: s.rang }, pole: code, declencheur: b }),
          surSupprimer: () => retirer('organigramme', 'squad', s.id, '« ' + s.nom + ' » retirée : ses membres attendent dans « À affecter ».')
        }),
        cartes: membres.map((p, i) => cartePersonne(pole, m, p, { rang: i, entree: true })),
        vide: 'Personne dans cette squad pour le moment.',
        pied: boutonAjouter('Une personne dans ' + s.nom, (b) => ouvrirPersonne({ organigramme: m.organigramme, flotte: m.flotte, pole: code, squad: s.id, declencheur: b }))
      });
    }
  });

  /* Le responsable clôt la phrase : en mode édition, ses commandes
     viennent au bout de la ligne, pas au milieu d'une phrase. */
  const r = m.responsable;
  return el('section', { class: 'equipes', 'aria-labelledby': prefixe + '-titre' },
    teteBloc(prefixe + '-titre', 'Les équipes',
      r ? frag('Sous la responsabilité de',
        el('span', { class: 'equipes__responsable', dataset: { teinte: 'pole' } },
          avatar(m, r, 'sm'),
          el('a', { class: 'equipes__responsable-nom', href: lienFiche(pole, r) }, texte(r.nom) || 'Nom à renseigner')),
        commandesPersonne(m, r, {}))
        : 'Aucun responsable déclaré pour ce pôle.',
      el('a', { class: 'coup-oeil__lien', href: lienPole('organigramme.html', code) }, 'L’organigramme complet', el('span', { 'aria-hidden': 'true' }, ' →'))),
    m.squads.length ? grille : el('p', { class: 'coup-oeil__vide' }, 'Aucune squad déclarée pour ce pôle.'),
    el('div', { class: 'coup-oeil__ajouts edition-seulement' },
      boutonAjouter('Une personne', (b) => ouvrirPersonne({ organigramme: m.organigramme, flotte: m.flotte, pole: code, squad: m.squads.length ? m.squads[0].id : '', declencheur: b })),
      boutonAjouter('Une squad', (b) => ouvrirSquad({ pole: code, declencheur: b }))));
}

/* --- Les référents ---------------------------------------------------------- */

/* Les personnes à solliciter en premier : des cartes, sans plus. */
function blocReferents(pole, m) {
  const code = pole.cle;
  const prefixe = 'referents-' + code.toLowerCase();
  const nommer = boutonAjouter('Nommer un référent', (b) => {
    try { ouvrirReferent({ organigramme: m.organigramme, pole: code, declencheur: b }); }
    catch (e) { toast((e && e.message) || 'Impossible de nommer un référent.', 'erreur'); }
  });
  const gens = m.referents.slice().sort((a, b) =>
    ((m.squadDe.get(a) || { rang: -1 }).rang - (m.squadDe.get(b) || { rang: -1 }).rang) || parRang(a, b));
  return el('section', { class: 'referents', 'aria-labelledby': prefixe + '-titre' },
    teteBloc(prefixe + '-titre', 'Les référents', 'Les personnes à solliciter en premier.', null),
    gens.length
      ? el('ul', { class: 'personnes__grille referents__gens', role: 'list' },
        gens.map((p, i) => cartePersonne(pole, m, p, { rang: i, edition: 'referent' })))
      : el('p', { class: 'coup-oeil__vide' }, 'Aucun référent nommé dans ce pôle pour le moment.'),
    el('div', { class: 'coup-oeil__ajouts edition-seulement' }, nommer));
}

/* --- L'assemblage ------------------------------------------------------------ */

function rendreAnnuaire(pole, m, conteneur) {
  monter(conteneur,
    el('div', { class: 'coup-oeil' },
      ligneChiffres(m),
      blocEquipes(pole, m),
      blocReferents(pole, m)));
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
  /* Les plus récents d'abord : par date quand le classeur en donne une,
     sinon par ligne — la dernière ligne ajoutée au classeur est la plus
     récente. */
  const enVigueur = liste.filter((d) => !texte(d.remplacePar))
    .sort((a, b) => texte(b.maj).localeCompare(texte(a.maj)) || (Number(b.ligne) || 0) - (Number(a.ligne) || 0));
  return { code, docs: docs.value, enVigueur, membres, tousMembres: orga.status === 'fulfilled' ? aplatirOrganigramme(orga.value).personnes : membres };
}

const MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
function dateCourte(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(texte(iso));
  return m ? Number(m[3]) + ' ' + MOIS_COURTS[Number(m[2]) - 1] + ' ' + m[1] : '';
}

/* Les documents du pôle : les huit plus récents en vigueur ; au-dessus,
   un filtre par type et une recherche dans le bloc — alors tous les
   documents du pôle qui correspondent s'affichent. Une ligne dit
   l'essentiel, sans plus : le titre, la personne qui l'a mis, la date
   (ou, faute de date, sa sensibilité), et « Ouvrir » quand le document
   a un lien. */
function rendreDocuments(pole, m, conteneur) {
  const MAX = 8;
  const tous = m.enVigueur;
  const porteurDuDoc = (d) => m.tousMembres.find((p) => normaliser(p.nom) === normaliser(d.porteur)) || null;
  const ligne = (d) => {
    const porteur = porteurDuDoc(d);
    const lien = texte(d.lien);
    return el('li', { class: 'pole-doc', dataset: { type: texte(d.type) || 'Document' } },
      el('a', { class: 'pole-doc__titre', href: 'docsearch.html#q=' + encodeURIComponent(texte(d.reference) || texte(d.titre)) }, texte(d.titre)),
      el('span', { class: 'pole-doc__porteur' }, porteur
        ? el('a', { href: lienFiche(pole, porteur) }, texte(porteur.nom))
        : (texte(d.porteur) || 'Porteur à renseigner')),
      texte(d.maj)
        ? el('time', { class: 'pole-doc__date', datetime: texte(d.maj) }, dateCourte(d.maj) || texte(d.maj))
        : (pastillesSecurite(d, 'pole-doc__securite') || el('span', { class: 'pole-doc__date' })),
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
      && (!q || normaliser([d.titre, d.reference, d.porteur, d.description, d.perimetre, [].concat(d.metier || []).join(' '), [].concat(d.motsCles || []).join(' ')].join(' ')).includes(q)));
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

async function ouvrirDemandeExpert(pole, declencheur, texteInitial) {
  let champ = null; let contexte = null; let erreur = null;
  const partage = await demandesPartagees();
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
        el('p', { class: 'texte-doux texte-sm sans-marge' }, partage
          ? 'Votre question part aux administrateurs du service, avec votre nom et votre pôle : '
            + 'ils la suivent et vous répondent.'
          : 'Ce site n’est pas relié à sa feuille Google : votre question reste dans ce navigateur, '
            + 'personne d’autre ne la verra.'),
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
        const ctx = texte(contexte && contexte.value);
        enregistrerDemande(q, ctx, pole.cle);
        envoyerDemande({ question: q, contexte: ctx, pole: pole.cle })
          .then((envoyee) => {
            toast(envoyee ? 'Question envoyée aux administrateurs du service.'
              : 'Question gardée dans ce navigateur : le site n’est pas relié à sa feuille.', envoyee ? 'succes' : 'info');
            annoncer(envoyee ? 'Question envoyée.' : 'Question enregistrée dans ce navigateur.');
          })
          .catch((e) => toast((e && e.message) || 'La question n’a pas pu être envoyée.', 'erreur'));
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

/* Le réseau de neurones de la une ETIIE vit (decor.js), chargé seulement s'il est dans la page. */
if (document.querySelector('.page-une__decor--nerf')) import('./decor.js').then((m) => m.animerReseau()).catch((e) => console.warn('[pole] décor immobile.', e));

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

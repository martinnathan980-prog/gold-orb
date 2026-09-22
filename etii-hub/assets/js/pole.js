/* =========================================================================
   ETII Hub — Espace de pôle (etiia.html, etiie.html, etiii.html)

   Une seule page, trois fois, paramétrée par <body data-pole="…">. Quatre
   sections, dans l'ordre de lecture :
     1. COMMUNICATION — le kiosque du pôle (kiosque.js), le même qu'au
                        niveau service ;
     2. EN UN COUP D'ŒIL — les repères chiffrés (effectif, squads,
                        référents, documents portés), puis QUI CONTACTER :
                        le responsable et les leads, et, porteur par
                        porteur, les personnes du pôle qui y travaillent ;
     3. ÉQUIPE & RÉFÉRENTS — le responsable, puis une carte par squad
                        avec ses membres et leurs compétences ; ou, au
                        choix, une carte par compétence avec ses
                        référents. Un seul champ filtre les deux vues :
                        « qui sait faire ça ? », la question de tous les
                        jours dans une équipe de soixante personnes ;
     4. FAQ           — les questions du pôle, liste + lecteur, et la
                        demande aux experts.

   Rien n'est inventé : chaque section ne montre que ce que les fichiers
   déclarent pour ce pôle (organigramme.json, flotte.json, documents.json).
   Tout le DOM est construit avec el().
   ========================================================================= */

import { el, frag, monter, debounce, deleguer, initTheme, initNav, suivreSommaire, ouvrirModale, stockage, toast, annoncer } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { kiosque, dossiersDepuisCommunications, noteOrigine } from './kiosque.js';
import { lecteur } from './lecteur.js';
import { chargerCommunications } from './communications.js';
import { ouvrirEditeur } from './editeur.js';
import { portrait } from './portraits.js';

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

/* Au-delà de ce nombre, les compétences sans recherche en cours se
   replient derrière un bouton : la grille reste lisible d'un coup d'œil. */
const COMPETENCES_VISIBLES = 12;

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

function lienSuite(page, code, libelle, extra) {
  return el('a', { class: 'bouton bouton--secondaire bouton--compact', href: lienPole(page, code, extra) }, libelle);
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
      surAjout: (bouton) => ouvrirEditeur({ pole: pole.cle, declencheur: bouton, surPublication: () => chargerCommunicationDuPole(pole) })
    }));
}

function chargerCommunicationDuPole(pole) {
  avecEtat('#zone-communication', chargerCommunications,
    (donnees, conteneur) => rendreCommunication(pole, donnees, conteneur), {
      squelette: 3,
      texteChargement: 'Chargement de la communication du pôle ' + pole.cle + '…',
      titreErreur: 'Communication indisponible',
      titreVide: 'Aucune communication',
      texteVide: 'Les communications publiées par ce pôle apparaîtront ici.',
      estVide: (d) => !d || dossiersDepuisCommunications(d, { pole: pole.cle }).length === 0
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
    .map((s) => {
      const membres = (Array.isArray(s.membres) ? s.membres : []).filter((m) => m && typeof m === 'object');
      return { nom: texte(s.nom) || 'Squad à nommer', lead: membres.find(estLead) || null, membres };
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
   4. En un coup d'œil : repères, à qui s'adresser, par porteur
   ------------------------------------------------------------------------- */

function porteursDuPole(flotte, code) {
  verifierForme(flotte, { flotte: 'tableau' }, 'flotte.json');
  return flotte.flotte.filter((a) => a && typeof a === 'object'
    && (Array.isArray(a.poles) ? a.poles : []).some((p) => texte(p).toUpperCase() === code));
}

/* Les documents dont le porteur est un membre du pôle : documents.json ne
   connaît que le nom, on rapproche donc par le nom. */
function documentsDuPole(docs, membres) {
  verifierForme(docs, { documents: 'tableau' }, 'documents.json');
  const noms = new Set(membres.map((m) => normaliser(m.nom)).filter(Boolean));
  return docs.documents.filter((d) => d && typeof d === 'object' && noms.has(normaliser(d.porteur)));
}

/**
 * Les personnes du pôle, porteur par porteur : d'abord les appareils que
 * flotte.json rattache au pôle, dans son ordre, puis les autres codes que
 * les membres déclarent (un porteur suivi par quelques personnes sans que
 * la flotte le dise encore). Dans chaque groupe, le lead d'abord, puis le
 * responsable, puis les autres par nom. Le périmètre transverse n'est pas
 * un porteur.
 */
function gensParPorteur(bloc, flotte) {
  const membres = membresDuBloc(bloc);
  const parCode = new Map();
  for (const m of membres) {
    const code = porteurDe(m).toUpperCase();
    if (!code || code === TRANSVERSE) continue;
    if (!parCode.has(code)) parCode.set(code, []);
    parCode.get(code).push(m);
  }
  const rang = (p) => (estLead(p) ? 0 : texte(p.role) === 'responsable' ? 1 : 2);
  const trier = (liste) => liste.slice().sort((a, b) => rang(a) - rang(b) || texte(a.nom).localeCompare(texte(b.nom), 'fr'));

  const appareils = flotte ? flotte.flotte.filter((a) => a && typeof a === 'object' && texte(a.code)) : [];
  const parCodeFlotte = new Map(appareils.map((a) => [texte(a.code).toUpperCase(), a]));
  const groupes = [];
  const vus = new Set();
  const ajouter = (code, declare) => {
    if (vus.has(code)) return;
    vus.add(code);
    const appareil = parCodeFlotte.get(code) || null;
    const fiche = appareil && appareil.fiche && typeof appareil.fiche === 'object' ? appareil.fiche : {};
    groupes.push({
      code: appareil ? texte(appareil.code) : code,
      segment: appareil ? (texte(appareil.segment) || texte(fiche.segment)) : '',
      declare,
      gens: trier(parCode.get(code) || [])
    });
  };
  if (flotte) porteursDuPole(flotte, texte(bloc.pole).toUpperCase()).forEach((a) => ajouter(texte(a.code).toUpperCase(), true));
  [...parCode.keys()].sort().forEach((code) => ajouter(code, false));
  return groupes;
}

/* Trois fichiers alimentent la section ; l'organigramme est indispensable,
   les deux autres se passent d'un chiffre plutôt que de faire tomber la
   section entière. */
async function chargerCoupOeil(code) {
  const [orga, flotte, docs] = await Promise.allSettled([
    chargerDonnees('organigramme'), chargerDonnees('flotte'), chargerDonnees('documents')
  ]);
  if (orga.status !== 'fulfilled') throw orga.reason;
  const bloc = blocOrganigramme(orga.value, code);
  if (!bloc) return null;
  const membres = membresDuBloc(bloc);
  const squads = squadsDuBloc(bloc);
  const { expertises, nbReferents } = expertisesDuBloc(bloc);
  const laFlotte = flotte.status === 'fulfilled' ? flotte.value : null;
  if (laFlotte) verifierForme(laFlotte, { flotte: 'tableau' }, 'flotte.json');
  return {
    effectif: membres.length,
    squads: squads.length,
    referents: nbReferents,
    competences: expertises.length,
    documents: docs.status === 'fulfilled' ? documentsDuPole(docs.value, membres).length : null,
    responsable: bloc.responsable && typeof bloc.responsable === 'object' ? bloc.responsable : null,
    leads: squads.filter((s) => s.lead).map((s) => ({ personne: s.lead, squad: s.nom })),
    parPorteur: gensParPorteur(bloc, laFlotte),
    flotteLue: Boolean(laFlotte)
  };
}

function repere(valeur, libelle, detail, href, extra) {
  const nombre = (valeur === null || valeur === undefined) ? '—' : String(valeur);
  return el('li', { class: 'pole-repere' },
    el('a', Object.assign({ class: 'pole-repere__lien', href }, extra || {}),
      el('span', { class: 'pole-repere__valeur' }, nombre),
      el('span', { class: 'pole-repere__libelle' }, libelle),
      el('span', { class: 'pole-repere__detail' }, valeur === null ? 'donnée indisponible' : detail)));
}

/** Une personne à contacter : portrait, nom, sous-ligne — le lien vers sa fiche. */
function personneContact(pole, personne, sousLigne, options) {
  const opts = options || {};
  return el('a', { class: ['pole-personne', opts.classe || null], href: lienFiche(pole, personne) },
    portrait(personne, { taille: opts.taille || 'sm', decoratif: true }),
    el('span', { class: 'pole-personne__infos' },
      el('span', { class: 'pole-personne__nom' }, texte(personne.nom) || 'Nom à renseigner'),
      el('span', { class: 'pole-personne__sous' }, sousLigne)));
}

function blocAQuiSAdresser(pole, r) {
  return el('div', { class: 'pole-contacts__bloc', 'aria-labelledby': 'contacts-' + pole.cle.toLowerCase() + '-titre' },
    el('h3', { class: 'pole-contacts__titre', id: 'contacts-' + pole.cle.toLowerCase() + '-titre' }, 'À qui s’adresser'),
    el('p', { class: 'pole-contacts__aide' }, 'Le responsable du pôle, puis le lead de chaque squad. Un nom ouvre sa fiche.'),
    el('ul', { class: 'pole-contacts__liste', role: 'list' },
      r.responsable
        ? el('li', {}, personneContact(pole, r.responsable, texte(r.responsable.poste) || 'Responsable de pôle', { classe: 'pole-personne--responsable', taille: 'md' }))
        : el('li', { class: 'pole-porteur-groupe__aucun' }, 'Responsable de pôle à renseigner'),
      r.leads.length
        ? r.leads.map((l) => el('li', {}, personneContact(pole, l.personne, 'Lead · ' + l.squad)))
        : el('li', { class: 'pole-porteur-groupe__aucun' }, 'Aucun lead de squad déclaré')));
}

/** Une personne en jeton : le portrait et le nom, le rôle s'il compte. */
function jetonPersonne(pole, personne) {
  const lead = estLead(personne);
  const responsable = texte(personne.role) === 'responsable';
  return el('li', {},
    el('a', { class: ['pole-jeton', lead ? 'pole-jeton--lead' : null], href: lienFiche(pole, personne),
      title: texte(personne.poste) || null },
    portrait(personne, { taille: 'xs', decoratif: true }),
    el('span', {}, texte(personne.nom) || 'Nom à renseigner'),
    lead ? el('span', { class: 'pole-jeton__role' }, 'Lead') : null,
    responsable ? el('span', { class: 'pole-jeton__role' }, 'Resp.') : null));
}

function groupePorteur(pole, g) {
  return el('div', { class: 'pole-porteur-groupe' },
    el('div', { class: 'pole-porteur-groupe__tete' },
      el('a', { class: 'pole-porteur-groupe__code', href: 'index.html#porteur=' + encodeURIComponent(g.code) }, g.code),
      g.segment ? el('span', { class: 'pole-porteur-groupe__segment' }, g.segment) : null,
      el('span', { class: 'pole-porteur-groupe__compte' }, g.gens.length ? pluriel(g.gens.length, 'personne') : 'personne à renseigner')),
    g.gens.length
      ? el('ul', { class: 'pole-porteur-groupe__gens', role: 'list' }, g.gens.map((p) => jetonPersonne(pole, p)))
      : el('p', { class: 'pole-porteur-groupe__aucun' }, 'Aucune personne du pôle rattachée à ce porteur dans l’organigramme.'));
}

function blocParPorteur(pole, r) {
  const id = 'porteurs-' + pole.cle.toLowerCase() + '-titre';
  return el('div', { class: 'pole-contacts__bloc', 'aria-labelledby': id },
    el('h3', { class: 'pole-contacts__titre', id }, 'Par porteur'),
    el('p', { class: 'pole-contacts__aide' },
      'Pour chaque porteur, les personnes du pôle qui y travaillent : le lead d’abord. '
      + 'Le code ouvre la fiche du porteur, un nom ouvre celle de la personne.'),
    r.parPorteur.length
      ? el('div', { class: 'pole-porteur-groupes' }, r.parPorteur.map((g) => groupePorteur(pole, g)))
      : el('p', { class: 'pole-porteur-groupe__aucun' },
        r.flotteLue ? 'Aucun porteur n’est rattaché à ce pôle pour le moment.' : 'La flotte ne peut pas être lue pour le moment.'));
}

function rendreCoupOeil(pole, r, conteneur) {
  monter(conteneur,
    el('div', { class: 'pole-coup-oeil' },
      el('ul', { class: 'pole-reperes', role: 'list', 'aria-label': 'Le pôle ' + pole.cle + ' en chiffres' },
        repere(r.effectif, 'personnes', 'responsable compris', '#section-equipe', { dataset: { vueEquipe: 'squad' } }),
        repere(r.squads, 'squads', 'chacune avec son lead', '#section-equipe', { dataset: { vueEquipe: 'squad' } }),
        repere(r.referents, 'référents', 'sur ' + pluriel(r.competences, 'compétence'), '#section-equipe', { dataset: { vueEquipe: 'competence' } }),
        repere(r.documents, 'documents', 'portés par ses membres', 'docsearch.html#pole=' + encodeURIComponent(pole.cle))),
      el('div', { class: 'pole-contacts' },
        blocAQuiSAdresser(pole, r),
        blocParPorteur(pole, r))));
}

/* -------------------------------------------------------------------------
   5. Équipe & référents : par squad, ou par compétence
   ------------------------------------------------------------------------- */

/* Le choix de vue est exposé au reste de la page (un repère « référents »
   ouvre la vue par compétence) une fois la section rendue. */
let choisirVueEquipe = null;

function pastilleCompetence(c) {
  const niveau = niveauDe(c);
  return el('li', { class: ['pole-competence', 'pole-competence--' + niveau] },
    texte(c.nom),
    niveau === 'referent' ? el('span', { class: 'pole-competence__niveau' }, 'référent') : null);
}

/** Un membre d'une squad : portrait, nom (lien vers sa fiche), poste, porteur, compétences. */
function ligneMembre(pole, personne, options) {
  const opts = options || {};
  const porteur = porteurDe(personne);
  const competences = competencesDe(personne).slice().sort((a, b) => rangNiveau(a) - rangNiveau(b));
  return el('div', { class: 'pole-membre' },
    portrait(personne, { taille: opts.taille || 'sm', decoratif: true }),
    el('div', { class: 'pole-membre__infos' },
      el('div', { class: 'pole-membre__ligne' },
        el('a', { class: 'pole-membre__nom', href: lienFiche(pole, personne) }, texte(personne.nom) || 'Nom à renseigner'),
        el('span', { class: 'pole-membre__poste' }, texte(personne.poste) || 'Poste à renseigner'),
        porteur ? el('span', { class: 'pole-membre__porteur' }, porteur) : null),
      competences.length
        ? el('ul', { class: 'pole-membre__competences', role: 'list', 'aria-label': 'Compétences' }, competences.map(pastilleCompetence))
        : null));
}

function rangNiveau(c) { return niveauDe(c) === 'referent' ? 0 : niveauDe(c) === 'confirme' ? 1 : 2; }

/** La clé de recherche d'une personne : nom, poste, porteur, compétences, identifiant. */
function cleMembre(personne) {
  return normaliser([personne.nom, personne.poste, porteurDe(personne), personne.id]
    .concat(competencesDe(personne).map((c) => c.nom)).map(texte).join(' '));
}

function carteResponsable(pole, responsable) {
  return el('li', { class: ['pole-squad', 'pole-squad--responsable'] },
    ligneMembre(pole, responsable, { taille: 'lg' }));
}

function carteSquad(pole, squad) {
  const membres = squad.membres.slice().sort((a, b) => (estLead(b) - estLead(a)) || texte(a.nom).localeCompare(texte(b.nom), 'fr'));
  return el('li', { class: 'pole-squad' },
    el('div', { class: 'pole-squad__tete' },
      el('h3', { class: 'pole-squad__nom' }, squad.nom),
      el('span', { class: 'pole-squad__lead' }, squad.lead ? 'Lead : ' + texte(squad.lead.nom) : 'Lead à renseigner'),
      el('span', { class: 'pole-squad__compte' }, pluriel(membres.length, 'personne'))),
    el('ul', { class: 'pole-squad__membres', role: 'list' },
      membres.map((m) => el('li', { dataset: { cle: cleMembre(m) } }, ligneMembre(pole, m)))));
}

function carteExpertise(pole, e) {
  const nbRef = e.referents.length;
  /* Chaque compte est insécable : la ligne se replie entre deux comptes,
     jamais au milieu de « 2 en pratique ». Le nombre de référents est la
     valeur qui compte ; sans référent, on ne l'écrit pas deux fois. */
  const comptes = [];
  if (nbRef) comptes.push(el('strong', { class: 'pole-expertise__compte-item' }, pluriel(nbRef, 'référent')));
  if (e.confirmes) comptes.push(el('span', { class: 'pole-expertise__compte-item' }, pluriel(e.confirmes, 'confirmé')));
  if (e.pratiquants) comptes.push(el('span', { class: 'pole-expertise__compte-item' }, e.pratiquants + ' en pratique'));
  const ligne = [];
  comptes.forEach((c, i) => { if (i) ligne.push(' · '); ligne.push(c); });

  return el('li', { class: ['pole-expertise', nbRef ? null : 'pole-expertise--sans-referent'] },
    el('h3', { class: 'pole-expertise__nom' }, e.nom),
    nbRef
      ? el('ul', { class: 'pole-expertise__referents', role: 'list' }, e.referents.map((r) =>
        el('li', {},
          el('a', { class: 'pole-expertise__personne', href: lienFiche(pole, r) },
            portrait(r, { taille: 'sm', decoratif: true }),
            el('span', { class: 'pole-expertise__identite' },
              el('span', { class: 'pole-expertise__personne-nom' }, texte(r.nom) || 'Nom à renseigner'),
              el('span', { class: 'pole-expertise__personne-poste' }, texte(r.poste) || 'Poste à renseigner'))))))
      : el('p', { class: 'pole-expertise__aucun' }, 'Pas de référent désigné'),
    el('p', { class: 'pole-expertise__compte' }, ligne));
}

async function chargerEquipe(code) {
  const bloc = blocOrganigramme(await chargerDonnees('organigramme'), code);
  if (!bloc) return null;
  const { expertises, nbReferents } = expertisesDuBloc(bloc);
  return {
    responsable: bloc.responsable && typeof bloc.responsable === 'object' ? bloc.responsable : null,
    squads: squadsDuBloc(bloc),
    effectif: membresDuBloc(bloc).length,
    expertises, nbReferents
  };
}

function rendreEquipe(pole, modele, conteneur) {
  const { expertises, nbReferents, squads, responsable } = modele;
  const prefixe = 'equipe-' + pole.cle.toLowerCase();

  const champ = el('input', {
    type: 'search', class: 'pole-experts__recherche', id: prefixe + '-recherche',
    placeholder: 'Qui sait faire… ? Une compétence, un nom, un porteur', autocomplete: 'off'
  });
  const compteur = el('p', { class: 'pole-experts__compte mono', id: prefixe + '-compte', 'aria-live': 'polite' });
  const vide = el('p', { class: 'pole-experts__vide', hidden: true });

  /* --- Vue par squad --------------------------------------------------- */
  const carteResp = responsable ? carteResponsable(pole, responsable) : null;
  const cleResp = responsable ? cleMembre(responsable) : '';
  const cartesSquads = squads.map((s) => ({ nom: normaliser(s.nom), noeud: carteSquad(pole, s) }));
  const grilleSquads = el('ul', { class: 'pole-squads', role: 'list' }, carteResp, cartesSquads.map((c) => c.noeud));
  const panneauSquads = el('div', { class: 'pole-experts__panneau', id: prefixe + '-squads', role: 'region', 'aria-label': 'Par squad' },
    el('p', { class: 'pole-experts__legende' },
      el('span', { class: ['pole-competence', 'pole-competence--referent'] }, 'référent'),
      el('span', { class: ['pole-competence', 'pole-competence--confirme'] }, 'confirmé'),
      el('span', { class: ['pole-competence', 'pole-competence--pratique'] }, 'en pratique'),
      ' — les compétences de chacun, le référent en terre cuite.'),
    grilleSquads);

  /* --- Vue par compétence --------------------------------------------- */
  const grilleExpertises = el('ul', { class: 'pole-experts__grille', role: 'list' });
  const suite = el('button', { type: 'button', class: 'bouton bouton--secondaire bouton--compact', hidden: true });
  const cartesExpertises = expertises.map((e) => ({
    cle: normaliser([e.nom].concat(e.referents.map((r) => r.nom)).join(' ')),
    noeud: carteExpertise(pole, e)
  }));
  monter(grilleExpertises, cartesExpertises.map((c) => c.noeud));
  const panneauExpertises = el('div', { class: 'pole-experts__panneau', id: prefixe + '-competences', role: 'region', 'aria-label': 'Par compétence', hidden: true },
    grilleExpertises);

  /* --- Le commutateur ---------------------------------------------------- */
  const boutonSquad = el('button', { type: 'button', class: 'pole-experts__vue', 'aria-pressed': 'true', 'aria-controls': panneauSquads.id, dataset: { vue: 'squad' } }, 'Par squad');
  const boutonCompetence = el('button', { type: 'button', class: 'pole-experts__vue', 'aria-pressed': 'false', 'aria-controls': panneauExpertises.id, dataset: { vue: 'competence' } }, 'Par compétence');
  const vues = el('div', { class: 'pole-experts__vues', role: 'group', 'aria-label': 'Présentation de l’équipe' }, boutonSquad, boutonCompetence);

  let vue = 'squad';
  let toutMontrer = false;
  let requete = '';

  function appliquerSquads(q) {
    let personnes = 0;
    let total = 0;
    if (carteResp) {
      total += 1;
      const ok = !q || cleResp.includes(q);
      if (ok) personnes += 1;
      carteResp.hidden = !ok;
    }
    cartesSquads.forEach((c) => {
      const squadOk = Boolean(q) && c.nom.includes(q);
      let visibles = 0;
      c.noeud.querySelectorAll('.pole-squad__membres > li').forEach((li) => {
        total += 1;
        const ok = !q || squadOk || li.dataset.cle.includes(q);
        if (ok) visibles += 1;
        li.hidden = !ok;
      });
      personnes += visibles;
      c.noeud.hidden = visibles === 0;
    });
    compteur.textContent = q
      ? personnes + ' sur ' + pluriel(total, 'personne')
      : pluriel(total, 'personne') + ' · ' + pluriel(squads.length, 'squad');
    return personnes;
  }

  function appliquerExpertises(q) {
    let correspondantes = 0;
    let repliees = 0;
    cartesExpertises.forEach((c) => {
      const ok = !q || c.cle.includes(q);
      if (ok) correspondantes += 1;
      const visible = ok && (Boolean(q) || toutMontrer || correspondantes <= COMPETENCES_VISIBLES);
      if (ok && !visible) repliees += 1;
      c.noeud.hidden = !visible;
    });
    compteur.textContent = q
      ? correspondantes + ' sur ' + pluriel(expertises.length, 'compétence') + ' · ' + pluriel(nbReferents, 'référent')
      : pluriel(expertises.length, 'compétence') + ' · ' + pluriel(nbReferents, 'référent');
    if (q) { suite.hidden = true; }
    else if (toutMontrer && expertises.length > COMPETENCES_VISIBLES) {
      suite.hidden = false; suite.textContent = 'Réduire à ' + pluriel(COMPETENCES_VISIBLES, 'compétence');
    } else if (repliees > 0) {
      suite.hidden = false; suite.textContent = 'Voir les ' + repliees + ' autres compétences';
    } else { suite.hidden = true; }
    return correspondantes;
  }

  function appliquer() {
    const q = normaliser(requete);
    const trouvees = vue === 'squad' ? appliquerSquads(q) : appliquerExpertises(q);
    if (vue === 'squad') suite.hidden = true;
    vide.hidden = trouvees > 0;
    if (!vide.hidden) {
      vide.textContent = vue === 'squad'
        ? 'Personne ne correspond à « ' + requete.trim() + ' » dans le pôle.'
        : 'Aucune compétence ni personne ne correspond à « ' + requete.trim() + ' » dans le pôle.';
    }
  }

  function choisir(nouvelle) {
    vue = nouvelle === 'competence' ? 'competence' : 'squad';
    boutonSquad.setAttribute('aria-pressed', vue === 'squad' ? 'true' : 'false');
    boutonCompetence.setAttribute('aria-pressed', vue === 'competence' ? 'true' : 'false');
    panneauSquads.hidden = vue !== 'squad';
    panneauExpertises.hidden = vue !== 'competence';
    appliquer();
  }
  vues.addEventListener('click', (evt) => {
    const b = evt.target.closest('[data-vue]');
    if (b) choisir(b.dataset.vue);
  });
  choisirVueEquipe = choisir;

  suite.addEventListener('click', () => {
    toutMontrer = !toutMontrer;
    appliquer();
    if (!toutMontrer) champ.focus();
  });
  const filtrer = debounce(() => { requete = champ.value; appliquer(); }, 120);
  champ.addEventListener('input', filtrer);
  champ.addEventListener('search', () => { filtrer.annuler(); requete = champ.value; appliquer(); });

  appliquer();

  monter(conteneur,
    el('div', { class: 'pole-experts' },
      el('p', { class: 'pole-experts__aide' },
        'Le responsable, puis chaque squad avec ses membres et ce qu’ils savent faire — ou, par compétence, '
        + 'le ou les référents du pôle : la personne à solliciter en premier. Un nom ouvre sa fiche dans l’organigramme.'),
      el('div', { class: 'pole-experts__barre', role: 'search' },
        el('label', { class: 'visuellement-cache', for: champ.id }, 'Rechercher une compétence, une personne ou un porteur du pôle'),
        champ, vues, compteur),
      panneauSquads, panneauExpertises, vide,
      el('div', { class: 'pole-experts__suite' },
        suite,
        lienSuite('organigramme.html', pole.cle, 'L’organigramme complet du service'),
        lienSuite('organigramme.html', pole.cle, 'Toutes les compétences du service', { vue: 'competences' }))));
}

/* Un repère du coup d'œil ouvre la section équipe dans la vue qui lui
   correspond (les référents : par compétence). L'ancre fait le défilement. */
deleguer(document, '[data-vue-equipe]', 'click', (_evt, lien) => {
  if (choisirVueEquipe) choisirVueEquipe(lien.dataset.vueEquipe);
});

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
        el('a', { href: '#section-equipe' }, 'les référents du pôle'), ' ou posez-la aux experts.')),
    el('div', { class: 'rangee rangee--serree' }, boutonExpert));

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
      pied
    }));
}

/* -------------------------------------------------------------------------
   7. En-tête, sommaire, refus
   ------------------------------------------------------------------------- */

function rendreEntete(pole) {
  const libelle = document.getElementById('pole-libelle');
  if (libelle) libelle.textContent = 'Pôle · ' + pole.metaphore;
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

initNav(POLE ? POLE.cle.toLowerCase() + '.html' : '');

if (!POLE) {
  refuser(PARAMETRE);
} else {
  rendreEntete(POLE);
  suivreSommaire();

  chargerCommunicationDuPole(POLE);

  avecEtat('#zone-reperes', () => chargerCoupOeil(POLE.cle),
    (modele, conteneur) => rendreCoupOeil(POLE, modele, conteneur), {
      squelette: 2, compact: true,
      texteChargement: 'Calcul des repères du pôle…',
      titreErreur: 'Repères indisponibles',
      titreVide: 'Aucune équipe déclarée',
      texteVide: 'Les repères du pôle se calculent depuis son organigramme, encore vide.'
    });

  avecEtat('#zone-equipe', () => chargerEquipe(POLE.cle),
    (modele, conteneur) => rendreEquipe(POLE, modele, conteneur), {
      squelette: 3, compact: true,
      texteChargement: 'Chargement de l’équipe du pôle…',
      titreErreur: 'Équipe indisponible',
      titreVide: 'Aucune équipe déclarée',
      texteVide: 'Ce pôle n’a encore ni responsable ni squad dans l’organigramme du service.',
      estVide: (m) => !m || (m.squads.length === 0 && !m.responsable)
    });

  avecEtat('#zone-faq', async () => questionsDuPole(await chargerDonnees('faq'), POLE.cle),
    (groupes, conteneur) => rendreFaq(POLE, groupes, conteneur), {
      squelette: 3, compact: true,
      texteChargement: 'Chargement des questions du pôle…',
      titreErreur: 'Questions indisponibles',
      titreVide: 'Aucune question',
      texteVide: 'Les questions fréquentes de ce pôle apparaîtront ici.',
      estVide: (g) => !g || (g.pole.length + g.service.length) === 0
    });
}

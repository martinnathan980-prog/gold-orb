/* =========================================================================
   ETII Hub — Espace de pôle (etiia.html, etiie.html, etiii.html)

   Une seule page, trois fois, paramétrée par <body data-pole="…">. Quatre
   sections, dans l'ordre de lecture :
     1. COMMUNICATION  — le kiosque du pôle (kiosque.js), le même qu'au
                         niveau service ;
     2. EN UN COUP D'ŒIL — les repères chiffrés, puis l'organigramme, les
                         référents par compétence et les personnes par
                         porteur, côte à côte, sous un seul champ de
                         recherche ;
     3. DOCUMENTS      — les documents du pôle les plus récents, en vigueur ;
     4. FAQ            — les questions du pôle, et la demande aux experts.

   Tout se modifie dans la page, en mode édition (edition.js) : les
   communications, l'organigramme (personnes, squads), les documents, les
   questions. Chaque section se redessine seule après un enregistrement.

   Rien n'est inventé : chaque section ne montre que ce que les fichiers
   déclarent pour ce pôle (organigramme.json, flotte.json, documents.json).
   Tout le DOM est construit avec el().
   ========================================================================= */

import { el, frag, monter, debounce, deleguer, initTheme, initNav, suivreSommaire, ouvrirModale, stockage, toast, annoncer } from './ui.js';
import { installerEdition, barreEdition, boutonAjouter } from './edition.js';
import { abonnerModifications, supprimerElement, aplatirOrganigramme } from './modifications.js';
import { modifierCommunication, supprimerDossier, ouvrirAlertes, ouvrirPersonne, ouvrirSquad, ouvrirDocument, ouvrirQuestion,
         ouvrirReferent, retirerReferent, ouvrirAffectation, affecter } from './edition-contenus.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { kiosque, dossiersDepuisCommunications, noteOrigine } from './kiosque.js';
import { lecteur } from './lecteur.js';
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
      /* En mode édition : ajouter, modifier, supprimer. La section se
         redessine d'elle-même après un enregistrement. */
      surAjout: (bouton) => ouvrirEditeur({ pole: pole.cle, declencheur: bouton }),
      surModifier: (dossier, bouton) => modifierCommunication(dossier, bouton, pole.cle),
      surSupprimer: (dossier) => supprimerDossier(dossier)
    }));
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
   4. Le pôle en un coup d'œil : l'organigramme, les référents, les porteurs

   Une seule section, pas trop haute : quatre repères chiffrés, un champ
   de recherche, puis trois volets côte à côte, de même hauteur, qui
   défilent chacun dans leur cadre :
     - l'organigramme : le responsable, puis chaque squad et ses membres ;
     - les référents : pour chaque compétence, qui solliciter en premier ;
     - par porteur : qui travaille sur quel appareil, le lead d'abord.
   Une personne s'y lit en une ligne : son nom et son rôle, rien de plus —
   on n'a pas davantage d'informations sur elle, et le nom mène à sa fiche.
   En mode édition, l'organigramme se modifie ici même.
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

/**
 * Les personnes du pôle, porteur par porteur : d'abord les appareils que
 * flotte.json rattache au pôle — même quand personne n'y est encore
 * affecté : le groupe dit alors « à renseigner » —, puis les autres codes
 * que les membres déclarent. Dans chaque groupe, le lead d'abord, puis le
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
  const trier = (liste) => liste.slice().sort((a, b) => rang(a) - rang(b) || texte(a.nom).localeCompare(texte(b.nom), 'fr', { numeric: true }));
  const appareils = flotte ? flotte.flotte.filter((a) => a && typeof a === 'object' && texte(a.code)) : [];
  const parCodeFlotte = new Map(appareils.map((a) => [texte(a.code).toUpperCase(), a]));
  const groupes = [];
  const vus = new Set();
  const ajouter = (code, meme) => {
    if (vus.has(code) || (!parCode.has(code) && !meme)) return;
    vus.add(code);
    const appareil = parCodeFlotte.get(code) || null;
    const fiche = appareil && appareil.fiche && typeof appareil.fiche === 'object' ? appareil.fiche : {};
    groupes.push({
      code: appareil ? texte(appareil.code) : code,
      segment: appareil ? (texte(appareil.segment) || texte(fiche.segment)) : '',
      gens: trier(parCode.get(code) || [])
    });
  };
  if (flotte) porteursDuPole(flotte, texte(bloc.pole).toUpperCase()).forEach((a) => ajouter(texte(a.code).toUpperCase(), true));
  [...parCode.keys()].sort().forEach(ajouter);
  return groupes;
}

/* L'organigramme est indispensable ; la flotte et les documents se passent
   d'un chiffre plutôt que de faire tomber la section. */
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
  return {
    code,
    organigramme: orga.value,
    flotte: laFlotte,
    responsable: bloc.responsable && typeof bloc.responsable === 'object' ? bloc.responsable : null,
    squads: squadsDuBloc(bloc),
    membres,
    expertises: expertises.filter((e) => e.referents.length),
    toutesCompetences: expertises.map((e) => e.nom),
    nbCompetences: expertises.length,
    nbReferents,
    parPorteur: gensParPorteur(bloc, laFlotte),
    documents: docs.status === 'fulfilled' ? documentsDuPole(docs.value, code, membres).filter((d) => !texte(d.remplacePar)).length : null
  };
}

/* Une personne, en une ligne : son nom, son rôle, et — en mode édition —
   de quoi la modifier. `placement` dit où elle est dans l'organigramme,
   pour le formulaire. Selon le volet, « retirer » n'a pas le même sens :
   de l'organigramme, du rôle de référent pour une compétence, ou d'un
   porteur. */
function lignePersonne(pole, m, personne, placement, options) {
  const o = options || {};
  const cle = normaliser([personne.nom, personne.poste, porteurDe(personne), o.competence || '']
    .concat(competencesDe(personne).map((c) => c.nom)).join(' '));
  return el('li', { class: 'annuaire__personne', dataset: { recherche: cle } },
    el('a', { class: 'annuaire__lien', href: lienFiche(pole, personne) },
      el('span', { class: 'annuaire__nom' }, texte(personne.nom) || 'Nom à renseigner'),
      el('span', { class: 'annuaire__role' }, texte(personne.poste) || 'Rôle à renseigner'),
      estLead(personne) && o.badgeLead !== false ? el('span', { class: 'annuaire__badge' }, 'lead') : null),
    o.edition === false ? null : barreEdition({
      classe: 'barre-edition--compacte',
      quoi: texte(personne.nom) + (o.edition === 'referent' ? ', référent ' + o.competence : (o.edition === 'porteur' ? ', sur le ' + o.porteur : '')),
      surModifier: (b) => ouvrirPersonne({ existant: Object.assign({}, personne, placement), organigramme: m.organigramme, flotte: m.flotte, declencheur: b }),
      surSupprimer: o.edition === 'referent'
        ? () => agir(retirerReferent(Object.assign({}, personne, placement), o.competence), '« ' + texte(personne.nom) + ' » n’est plus référent en ' + o.competence + '.')
        : o.edition === 'porteur'
          ? () => agir(affecter(Object.assign({}, personne, placement), ''), '« ' + texte(personne.nom) + ' » ne suit plus le ' + o.porteur + '.')
          : () => retirer('organigramme', 'personne', texte(personne.id), '« ' + texte(personne.nom) + ' » ne figure plus dans l’organigramme.')
    }));
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

/* Un groupe sans personne le dit, sans rien inventer ; sa ligne n'est pas
   une personne : la recherche ne la compte pas. */
function groupeAnnuaire(titre, compte, lignes, commandes, vide) {
  return el('li', { class: 'annuaire__groupe' },
    el('div', { class: 'annuaire__groupe-tete' },
      el('h4', { class: 'annuaire__groupe-titre' }, titre),
      compte !== null ? el('span', { class: 'annuaire__compte mono' }, String(compte)) : null,
      commandes || null),
    el('ul', { class: 'annuaire__personnes', role: 'list' },
      lignes.length ? lignes : el('li', { class: 'annuaire__vide' }, vide || 'À renseigner')));
}

function volet(id, titre, sousTitre, groupes, pied) {
  return el('section', { class: 'annuaire__volet', id, 'aria-labelledby': id + '-titre' },
    el('header', { class: 'annuaire__volet-tete' },
      el('h3', { class: 'annuaire__volet-titre', id: id + '-titre' }, titre),
      el('p', { class: 'annuaire__volet-sous-titre' }, sousTitre)),
    el('div', { class: 'annuaire__defile', tabIndex: 0, 'aria-label': titre },
      el('ul', { class: 'annuaire__groupes', role: 'list' }, groupes),
      el('p', { class: 'annuaire__rien', hidden: true }, 'Personne ne correspond.'),
      pied || null));
}

function rendreAnnuaire(pole, m, conteneur) {
  const code = pole.cle;
  const prefixe = 'annuaire-' + code.toLowerCase();

  /* L'organigramme : le responsable, puis les squads. */
  const groupesOrga = [];
  if (m.responsable) {
    groupesOrga.push(groupeAnnuaire('Responsable du pôle', null,
      [lignePersonne(pole, m, m.responsable, { pole: code, squad: '' }, { badgeLead: false })]));
  }
  m.squads.forEach((s) => {
    groupesOrga.push(groupeAnnuaire(s.nom, s.membres.length,
      s.membres.slice().sort((a, b) => (estLead(b) ? 1 : 0) - (estLead(a) ? 1 : 0))
        .map((p) => lignePersonne(pole, m, p, { pole: code, squad: s.id })),
      barreEdition({
        classe: 'barre-edition--compacte',
        quoi: s.nom,
        surModifier: (b) => ouvrirSquad({ existant: { id: s.id, pole: code, nom: s.nom, rang: s.rang }, pole: code, declencheur: b }),
        surSupprimer: () => retirer('organigramme', 'squad', s.id, '« ' + s.nom + ' » retirée : ses membres attendent dans « À affecter ».')
      }),
      'Personne dans cette squad pour le moment.'));
  });
  const piedOrga = el('div', { class: 'annuaire__ajouts edition-seulement' },
    boutonAjouter('Une personne', (b) => ouvrirPersonne({ organigramme: m.organigramme, flotte: m.flotte, pole: code, squad: m.squads.length ? m.squads[0].id : '', declencheur: b })),
    boutonAjouter('Une squad', (b) => ouvrirSquad({ pole: code, declencheur: b })));

  /* Les référents : une compétence, ses référents. En mode édition, on en
     nomme un de plus, ou on retire le titre à quelqu'un. */
  const competencesConnues = m.toutesCompetences;
  const groupesRef = m.expertises.map((e) => groupeAnnuaire(e.nom, e.referents.length,
    e.referents.map((p) => lignePersonne(pole, m, p, placementDe(m, p), { competence: e.nom, edition: 'referent' })),
    boutonAjouter('Un référent', (b) => ouvrirReferent({ organigramme: m.organigramme, pole: code, competence: e.nom, competences: competencesConnues, declencheur: b }))));
  const piedRef = el('div', { class: 'annuaire__ajouts edition-seulement' },
    boutonAjouter('Nommer un référent', (b) => ouvrirReferent({ organigramme: m.organigramme, pole: code, competences: competencesConnues, declencheur: b })));

  /* Par porteur : qui travaille sur quoi. En mode édition, on y affecte
     quelqu'un, ou on l'en retire. */
  const groupesPorteur = m.parPorteur.map((g) => groupeAnnuaire(
    frag(el('a', { class: 'annuaire__porteur', href: 'index.html#porteur=' + encodeURIComponent(g.code) }, g.code),
      g.segment ? el('span', { class: 'annuaire__segment' }, ' · ' + g.segment) : null),
    g.gens.length,
    g.gens.map((p) => lignePersonne(pole, m, p, placementDe(m, p), { edition: 'porteur', porteur: g.code })),
    boutonAjouter('Quelqu’un', (b) => ouvrirAffectation({ organigramme: m.organigramme, pole: code, code: g.code, declencheur: b })),
    'Contact à renseigner'));

  const volets = el('div', { class: 'annuaire__volets' },
    volet(prefixe + '-organigramme', 'Organigramme', pluriel(m.membres.length, 'personne') + ' · ' + pluriel(m.squads.length, 'squad'), groupesOrga, piedOrga),
    volet(prefixe + '-referents', 'Référents', 'La personne à solliciter en premier, par compétence', groupesRef, piedRef),
    volet(prefixe + '-porteurs', 'Par porteur', 'Qui travaille sur quel appareil', groupesPorteur));

  /* Un seul champ filtre les trois volets. */
  const champ = el('input', {
    type: 'search', class: 'annuaire__recherche', id: prefixe + '-recherche', autocomplete: 'off',
    placeholder: 'Qui sait faire… ? Un nom, un rôle, un porteur, une compétence'
  });
  const compteur = el('p', { class: 'annuaire__resultat mono', 'aria-live': 'polite' }, '');
  function filtrer() {
    const q = normaliser(champ.value);
    let trouves = 0;
    volets.querySelectorAll('.annuaire__volet').forEach((v) => {
      let visiblesVolet = 0;
      v.querySelectorAll('.annuaire__groupe').forEach((g) => {
        let visibles = 0;
        g.querySelectorAll('.annuaire__personne').forEach((li) => {
          const ok = !q || li.dataset.recherche.includes(q) || normaliser(g.querySelector('.annuaire__groupe-titre').textContent).includes(q);
          li.hidden = !ok;
          if (ok) visibles += 1;
        });
        g.hidden = visibles === 0 && Boolean(q);
        visiblesVolet += visibles;
      });
      const rien = v.querySelector('.annuaire__rien');
      if (rien) rien.hidden = visiblesVolet > 0 || !q;
      if (v.id.endsWith('-organigramme')) trouves = visiblesVolet;
    });
    compteur.textContent = q ? pluriel(trouves, 'personne') + ' dans l’organigramme' : '';
  }
  champ.addEventListener('input', debounce(filtrer, 100));
  champ.addEventListener('search', filtrer);

  monter(conteneur,
    el('div', { class: 'annuaire' },
      el('ul', { class: 'pole-reperes', role: 'list', 'aria-label': 'Le pôle ' + code + ' en chiffres' },
        repere(m.membres.length, 'personnes', 'responsable compris', '#' + prefixe + '-organigramme'),
        repere(m.squads.length, 'squads', 'chacune avec son lead', '#' + prefixe + '-organigramme'),
        repere(m.nbReferents, 'référents', 'sur ' + pluriel(m.nbCompetences, 'compétence'), '#' + prefixe + '-referents'),
        repere(m.documents, 'documents', 'en vigueur, portés par le pôle', '#section-documents')),
      el('div', { class: 'annuaire__barre', role: 'search' },
        el('label', { class: 'visuellement-cache', for: champ.id }, 'Rechercher une personne, un rôle, un porteur ou une compétence du pôle'),
        champ, compteur),
      volets,
      el('p', { class: 'annuaire__suite' },
        lienSuite('organigramme.html', code, 'L’organigramme complet, avec les fiches'))));
}

/* Où est une personne dans l'organigramme du pôle : pour le formulaire. */
function placementDe(m, personne) {
  if (m.responsable && texte(m.responsable.id) === texte(personne.id)) return { pole: m.code, squad: '' };
  const s = m.squads.find((x) => x.membres.includes(personne));
  return { pole: m.code, squad: s ? s.id : '' };
}

function repere(valeur, libelle, detail, href) {
  const nombre = (valeur === null || valeur === undefined) ? '—' : String(valeur);
  return el('li', { class: 'pole-repere' },
    el('a', { class: 'pole-repere__lien', href },
      el('span', { class: 'pole-repere__valeur' }, nombre),
      el('span', { class: 'pole-repere__libelle' }, libelle),
      el('span', { class: 'pole-repere__detail' }, valeur === null ? 'donnée indisponible' : detail)));
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

function rendreDocuments(pole, m, conteneur) {
  const MAX = 8;
  const visibles = m.enVigueur.slice(0, MAX);
  const porteurDuDoc = (d) => m.tousMembres.find((p) => normaliser(p.nom) === normaliser(d.porteur)) || null;
  monter(conteneur,
    el('div', { class: 'pole-docs' },
      visibles.length
        ? el('ul', { class: 'pole-docs__liste', role: 'list' }, visibles.map((d) => {
          const porteur = porteurDuDoc(d);
          return el('li', { class: 'pole-doc' },
            el('span', { class: 'pole-doc__type badge badge--contour' }, texte(d.type) || 'Document'),
            el('a', { class: 'pole-doc__titre', href: 'docsearch.html#q=' + encodeURIComponent(texte(d.reference) || texte(d.titre)) }, texte(d.titre)),
            el('span', { class: 'pole-doc__ref mono' }, texte(d.reference)),
            el('span', { class: 'pole-doc__porteur' }, porteur
              ? el('a', { href: lienFiche(pole, porteur) }, texte(porteur.nom))
              : (texte(d.porteur) || 'Porteur à renseigner')),
            el('time', { class: 'pole-doc__date', datetime: texte(d.maj) || null }, dateCourte(d.maj) || 'date à renseigner'),
            /* Une ligne de document a la place : « Modifier » et
               « Supprimer » s'y écrivent en toutes lettres. */
            barreEdition({
              classe: 'pole-doc__edition',
              quoi: texte(d.titre),
              surModifier: (b) => ouvrirDocument({ existant: d, documents: m.docs, personnes: m.tousMembres, pole: pole.cle, declencheur: b }),
              surSupprimer: () => retirer('documents', 'document', texte(d.id), 'Document retiré du fonds.')
            }));
        }))
        : el('p', { class: 'texte-doux sans-marge' }, 'Aucun document rattaché à ce pôle pour le moment.'),
      el('div', { class: 'pole-docs__pied' },
        el('a', { class: 'bouton bouton--secondaire bouton--compact', href: 'docsearch.html#pole=' + encodeURIComponent(pole.cle) },
          'Tous les documents du pôle' + (m.enVigueur.length ? ' (' + m.enVigueur.length + ')' : '')),
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

  chargerCommunicationDuPole(POLE);

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
    if (jeu === 'communications') chargerCommunicationDuPole(POLE);
    if (jeu === 'organigramme' || jeu === 'flotte') { chargerSectionAnnuaire(); chargerSectionDocuments(); }
    if (jeu === 'documents') { chargerSectionDocuments(); chargerSectionAnnuaire(); }
    if (jeu === 'faq') chargerSectionFaq();
  });
}

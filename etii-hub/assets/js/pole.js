/* =========================================================================
   ETII Hub — Espace de pôle (etiia.html, etiie.html, etiii.html)

   Une seule page, trois fois, paramétrée par <body data-pole="…">. Six
   sections, dans l'ordre de lecture :
     1. COMMUNICATION — le kiosque du pôle (kiosque.js), le même qu'au
                        niveau service ;
     2. REPÈRES       — « le pôle en un coup d'œil » : effectif, squads,
                        référents, porteurs, documents portés ;
     3. RÉFÉRENTS     — les compétences du pôle et, pour chacune, qui en
                        est référent : la question de tous les jours dans
                        une équipe de soixante personnes ;
     4. PORTEURS      — les appareils que le pôle suit, en cartes photo
                        vers la fiche du tableau de bord ;
     5. ORGANIGRAMME  — l'arbre d'équipe du pôle (arbre.js) ;
     6. FAQ           — la base de connaissances du pôle, liste + lecteur,
                        et la demande aux experts.

   Rien n'est inventé : chaque section ne montre que ce que les fichiers
   déclarent pour ce pôle (organigramme.json, flotte.json, documents.json).
   Tout le DOM est construit avec el().
   ========================================================================= */

import { el, frag, monter, debounce, initTheme, initNav, ouvrirModale, stockage, toast, annoncer } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { kiosque, dossiersDepuisCommunications } from './kiosque.js';
import { lecteur } from './lecteur.js';
import { arbreEquipe } from './arbre.js';
import { chargerCommunications } from './communications.js';
import { silhouette } from './helicos.js';

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

/* -------------------------------------------------------------------------
   2. Communication
   ------------------------------------------------------------------------- */

function rendreCommunication(pole, donnees, conteneur) {
  verifierForme(donnees, { agenda: 'tableau' }, 'communications.json');
  const dossiers = dossiersDepuisCommunications(donnees, { pole: pole.cle });
  /* Tout ce que le pôle publie est déjà dans ce kiosque : il n'y a pas
     d'ailleurs où renvoyer. Le niveau service est sur le tableau de bord. */
  monter(conteneur,
    kiosque({ id: 'kiosque-' + pole.cle.toLowerCase(), dossiers, titreFil: 'Communications du pôle' }));
}

/* -------------------------------------------------------------------------
   3. Les gens du pôle : lecture d'organigramme.json
   ------------------------------------------------------------------------- */

function blocOrganigramme(donnees, code) {
  verifierForme(donnees, { poles: 'tableau' }, 'organigramme.json');
  return donnees.poles.find((e) => e && typeof e === 'object' && texte(e.pole).toUpperCase() === code) || null;
}

/** Le responsable puis les membres de chaque squad, à plat. */
function membresDuBloc(bloc) {
  if (!bloc || typeof bloc !== 'object') return [];
  const liste = [];
  if (bloc.responsable && typeof bloc.responsable === 'object') liste.push(bloc.responsable);
  for (const squad of (Array.isArray(bloc.squads) ? bloc.squads : [])) {
    for (const m of (Array.isArray(squad && squad.membres) ? squad.membres : [])) {
      if (m && typeof m === 'object') liste.push(m);
    }
  }
  return liste;
}

function competencesDe(personne) {
  return (Array.isArray(personne.competences) ? personne.competences : [])
    .filter((c) => c && typeof c === 'object' && texte(c.nom));
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
      const niveau = normaliser(c.niveau);
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

function initiales(nom) {
  const parts = texte(nom).split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  const dernier = parts[parts.length - 1];
  // « Personne 03 » donne P03 : un numéro vaut mieux qu'un chiffre isolé.
  if (parts.length > 1 && /^\d+$/.test(dernier)) return parts[0][0].toUpperCase() + dernier;
  return parts.slice(0, 2).map((p) => p[0].toUpperCase()).join('');
}

/* L'avatar aux initiales, sur un fond teinté du pôle : le même que celui
   de l'organigramme, pour que la même personne se reconnaisse partout. */
function avatar(personne, code) {
  return el('span', { class: 'org-avatar', dataPole: code, 'aria-hidden': 'true' }, initiales(personne && personne.nom));
}

/* -------------------------------------------------------------------------
   4. Repères : « le pôle en un coup d'œil »
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

/* Trois fichiers alimentent les repères ; l'organigramme est indispensable,
   les deux autres se passent d'un chiffre plutôt que de faire tomber la
   ligne entière. */
async function chargerReperes(code) {
  const [orga, flotte, docs] = await Promise.allSettled([
    chargerDonnees('organigramme'), chargerDonnees('flotte'), chargerDonnees('documents')
  ]);
  if (orga.status !== 'fulfilled') throw orga.reason;
  const bloc = blocOrganigramme(orga.value, code);
  if (!bloc) return null;
  const membres = membresDuBloc(bloc);
  const squads = (Array.isArray(bloc.squads) ? bloc.squads : []).filter((s) => s && typeof s === 'object');
  const { expertises, nbReferents } = expertisesDuBloc(bloc);
  return {
    effectif: membres.length,
    squads: squads.length,
    referents: nbReferents,
    competences: expertises.length,
    porteurs: flotte.status === 'fulfilled' ? porteursDuPole(flotte.value, code).length : null,
    documents: docs.status === 'fulfilled' ? documentsDuPole(docs.value, membres).length : null
  };
}

function repere(valeur, libelle, detail, href) {
  const nombre = (valeur === null || valeur === undefined) ? '—' : String(valeur);
  return el('li', { class: 'pole-repere' },
    el('a', { class: 'pole-repere__lien', href },
      el('span', { class: 'pole-repere__valeur' }, nombre),
      el('span', { class: 'pole-repere__libelle' }, libelle),
      el('span', { class: 'pole-repere__detail' }, valeur === null ? 'donnée indisponible' : detail)));
}

function rendreReperes(pole, r, conteneur) {
  monter(conteneur,
    el('ul', { class: 'pole-reperes', role: 'list', 'aria-label': 'Le pôle ' + pole.cle + ' en chiffres' },
      repere(r.effectif, 'personnes', 'responsable compris', '#section-organigramme'),
      repere(r.squads, 'squads', 'dans l’organigramme', '#section-organigramme'),
      repere(r.referents, 'référents', 'sur ' + pluriel(r.competences, 'compétence'), '#section-referents'),
      repere(r.porteurs, 'porteurs', 'appareils suivis par le pôle', '#section-porteurs'),
      repere(r.documents, 'documents', 'portés par ses membres', 'docsearch.html#pole=' + encodeURIComponent(pole.cle))));
}

/* -------------------------------------------------------------------------
   5. Référents & expertises : « qui sait faire ça ? »
   ------------------------------------------------------------------------- */

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
          el('a', { class: 'pole-expertise__personne', href: lienPole('organigramme.html', pole.cle, { personne: texte(r.id) }) },
            avatar(r, pole.cle),
            el('span', { class: 'pole-expertise__identite' },
              el('span', { class: 'pole-expertise__personne-nom' }, texte(r.nom) || 'Nom à renseigner'),
              el('span', { class: 'pole-expertise__personne-poste' }, texte(r.poste) || 'Poste à renseigner'))))))
      : el('p', { class: 'pole-expertise__aucun' }, 'Pas de référent désigné'),
    el('p', { class: 'pole-expertise__compte' }, ligne));
}

function rendreReferents(pole, modele, conteneur) {
  const { expertises, nbReferents } = modele;
  const prefixe = 'experts-' + pole.cle.toLowerCase();

  const champ = el('input', {
    type: 'search', class: 'pole-experts__recherche', id: prefixe + '-recherche',
    placeholder: 'Qui sait faire… ? Une compétence, un nom', autocomplete: 'off'
  });
  const compteur = el('p', { class: 'pole-experts__compte mono', id: prefixe + '-compte', 'aria-live': 'polite' });
  const grille = el('ul', { class: 'pole-experts__grille', role: 'list' });
  const vide = el('p', { class: 'pole-experts__vide', hidden: true });
  const suite = el('button', { type: 'button', class: 'bouton bouton--secondaire bouton--compact', hidden: true });

  const cartes = expertises.map((e) => ({
    cle: normaliser([e.nom].concat(e.referents.map((r) => r.nom)).join(' ')),
    noeud: carteExpertise(pole, e)
  }));
  monter(grille, cartes.map((c) => c.noeud));

  let toutMontrer = false;
  let requete = '';

  function appliquer() {
    const q = normaliser(requete);
    let correspondantes = 0;
    let repliees = 0;
    cartes.forEach((c) => {
      const ok = !q || c.cle.includes(q);
      if (ok) correspondantes += 1;
      const visible = ok && (Boolean(q) || toutMontrer || correspondantes <= COMPETENCES_VISIBLES);
      if (ok && !visible) repliees += 1;
      c.noeud.hidden = !visible;
    });

    compteur.textContent = q
      ? correspondantes + ' sur ' + pluriel(expertises.length, 'compétence') + ' · ' + pluriel(nbReferents, 'référent')
      : pluriel(expertises.length, 'compétence') + ' · ' + pluriel(nbReferents, 'référent');

    vide.hidden = correspondantes > 0;
    if (!vide.hidden) vide.textContent = 'Aucune compétence ni personne ne correspond à « ' + requete.trim() + ' » dans le pôle.';

    if (q) { suite.hidden = true; }
    else if (toutMontrer && expertises.length > COMPETENCES_VISIBLES) {
      suite.hidden = false; suite.textContent = 'Réduire à ' + pluriel(COMPETENCES_VISIBLES, 'compétence');
    } else if (repliees > 0) {
      suite.hidden = false; suite.textContent = 'Voir les ' + repliees + ' autres compétences';
    } else { suite.hidden = true; }
  }

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
        'Pour chaque compétence, le ou les référents du pôle : la personne à solliciter en premier. '
        + 'Cliquez un nom pour ouvrir sa fiche dans l’organigramme.'),
      el('div', { class: 'pole-experts__barre', role: 'search' },
        el('label', { class: 'visuellement-cache', for: champ.id }, 'Rechercher une compétence ou une personne du pôle'),
        champ, compteur),
      grille, vide,
      el('div', { class: 'pole-experts__suite' },
        suite,
        lienSuite('organigramme.html', pole.cle, 'Toutes les compétences du service', { vue: 'competences' }))));
}

/* -------------------------------------------------------------------------
   6. Porteurs du pôle : la carte de la galerie, en lien vers la fiche
   ------------------------------------------------------------------------- */

function cartePorteur(appareil) {
  const code = texte(appareil.code) || '—';
  const fiche = (appareil.fiche && typeof appareil.fiche === 'object') ? appareil.fiche : {};
  return el('li', { class: 'porteurs__item', dataset: { code } },
    el('a', { class: 'porteurs__fiche pole-porteur', href: 'index.html#porteur=' + encodeURIComponent(code) },
      el('span', { class: 'porteurs__fiche-visuel', 'aria-hidden': 'true' },
        texte(appareil.photo)
          ? el('img', { src: texte(appareil.photo), alt: '', loading: 'lazy', decoding: 'async', class: 'porteurs__fiche-photo' })
          : silhouette(texte(appareil.silhouette), { titre: '' })),
      el('span', { class: 'porteurs__fiche-code' }, code),
      el('span', { class: 'porteurs__fiche-segment' }, texte(appareil.segment) || texte(fiche.segment) || 'Segment à renseigner')));
}

function rendrePorteurs(pole, appareils, conteneur) {
  monter(conteneur,
    el('div', { class: 'pole-porteurs' },
      el('p', { class: 'pole-porteurs__aide' },
        pluriel(appareils.length, 'appareil') + ' suivi' + (appareils.length > 1 ? 's' : '') + ' par le pôle ' + pole.cle
        + '. Une carte ouvre la fiche complète du porteur sur le tableau de bord.'),
      el('ul', { class: 'porteurs__grille', role: 'list' }, appareils.map(cartePorteur)),
      el('p', { class: 'rangee rangee--centree sans-marge' },
        el('a', { class: 'bouton bouton--secondaire bouton--compact', href: 'index.html#titre-porteurs' }, 'Tous les porteurs du service'))));
}

/* -------------------------------------------------------------------------
   7. Organigramme
   ------------------------------------------------------------------------- */

function rendreOrganigramme(pole, bloc, conteneur) {
  monter(conteneur,
    arbreEquipe(bloc, { id: 'arbre-' + pole.cle.toLowerCase() }),
    el('p', { class: 'rangee rangee--fin sans-marge' },
      lienSuite('organigramme.html', pole.cle, 'L’organigramme complet du service')));
}

/* -------------------------------------------------------------------------
   8. FAQ
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

  const pied = el('div', { class: 'liseuse__pied' },
    el('div', {},
      el('p', { class: 'liseuse__pied-titre' }, 'Une question spécifique ?'),
      el('p', {}, 'Si la base ne couvre pas votre périmètre, sollicitez ',
        el('a', { href: '#section-referents' }, 'les référents du pôle'), '.')),
    el('div', { class: 'rangee rangee--serree' },
      lienSuite('faq.html', pole.cle, 'Toute la base'),
      boutonExpert));

  monter(conteneur,
    lecteur({
      id: 'faq-' + pole.cle.toLowerCase(),
      elements,
      groupes: [{ cle: 'pole', titre: 'Pôle ' + pole.cle }, { cle: 'service', titre: 'Service ETII' }],
      titreListe: 'Base de connaissances',
      placeholder: 'Rechercher une question technique…',
      vide: 'Aucune question publiée pour ce pôle.',
      entete: (item) => frag(
        el('span', { class: 'badge badge--neutre' }, item.groupe === 'pole' ? 'Pôle ' + pole.cle : 'Service ETII'),
        item.meta ? el('span', { class: 'badge badge--contour' }, item.meta) : null),
      pied
    }));
}

/* -------------------------------------------------------------------------
   9. En-tête, sous-navigation, refus
   ------------------------------------------------------------------------- */

function rendreEntete(pole) {
  const libelle = document.getElementById('pole-libelle');
  if (libelle) libelle.textContent = 'Pôle · ' + pole.metaphore;
  const titre = document.getElementById('pole-titre');
  if (titre) titre.textContent = pole.cle;
  try { document.title = pole.cle + ' — ' + pole.metaphore + ' — ETII Hub'; } catch (_e) { /* ignoré */ }
}

/* La sous-navigation suit la lecture : l'ancre de la section visible est
   marquée courante. */
function suivreSections() {
  const liens = Array.from(document.querySelectorAll('.sous-nav a[href^="#"]'));
  if (!liens.length || typeof IntersectionObserver !== 'function') return;
  const cibles = liens.map((a) => document.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);
  const marquer = (id) => liens.forEach((a) => a.setAttribute('aria-current', a.getAttribute('href') === '#' + id ? 'true' : 'false'));
  const obs = new IntersectionObserver((entrees) => {
    const visible = entrees.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (visible) marquer(visible.target.id);
  }, { rootMargin: '-30% 0px -55% 0px', threshold: [0, 0.2, 0.5] });
  cibles.forEach((c) => obs.observe(c));
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
  console.error('[pole] ' + message);
}

/* -------------------------------------------------------------------------
   10. Démarrage
   ------------------------------------------------------------------------- */

initTheme();

const PARAMETRE = (document.body && document.body.dataset ? String(document.body.dataset.pole || '') : '').trim();
const POLE = Object.prototype.hasOwnProperty.call(POLES, PARAMETRE.toUpperCase()) ? POLES[PARAMETRE.toUpperCase()] : null;

initNav(POLE ? POLE.cle.toLowerCase() + '.html' : '');

if (!POLE) {
  refuser(PARAMETRE);
} else {
  rendreEntete(POLE);
  suivreSections();

  avecEtat('#zone-communication', chargerCommunications,
    (donnees, conteneur) => rendreCommunication(POLE, donnees, conteneur), {
      squelette: 3,
      texteChargement: 'Chargement de la communication du pôle ' + POLE.cle + '…',
      titreErreur: 'Communication indisponible',
      titreVide: 'Aucune communication',
      texteVide: 'Les communications publiées par ce pôle apparaîtront ici.',
      estVide: (d) => !d || dossiersDepuisCommunications(d, { pole: POLE.cle }).length === 0
    });

  avecEtat('#zone-reperes', () => chargerReperes(POLE.cle),
    (reperes, conteneur) => rendreReperes(POLE, reperes, conteneur), {
      squelette: 1, compact: true,
      texteChargement: 'Calcul des repères du pôle…',
      titreErreur: 'Repères indisponibles',
      titreVide: 'Aucune équipe déclarée',
      texteVide: 'Les repères du pôle se calculent depuis son organigramme, encore vide.'
    });

  avecEtat('#zone-referents', async () => expertisesDuBloc(blocOrganigramme(await chargerDonnees('organigramme'), POLE.cle)),
    (modele, conteneur) => rendreReferents(POLE, modele, conteneur), {
      squelette: 3, compact: true,
      texteChargement: 'Chargement des compétences du pôle…',
      titreErreur: 'Compétences indisponibles',
      titreVide: 'Aucune compétence déclarée',
      texteVide: 'Les compétences et référents de ce pôle apparaîtront ici dès que l’organigramme les déclarera.',
      estVide: (m) => !m || m.expertises.length === 0
    });

  avecEtat('#zone-porteurs', async () => porteursDuPole(await chargerDonnees('flotte'), POLE.cle),
    (appareils, conteneur) => rendrePorteurs(POLE, appareils, conteneur), {
      squelette: 2, compact: true,
      texteChargement: 'Chargement des porteurs du pôle…',
      titreErreur: 'Porteurs indisponibles',
      titreVide: 'Aucun porteur rattaché',
      texteVide: 'Aucun appareil de flotte.json ne cite ce pôle dans son champ « poles ».',
      estVide: (liste) => !liste || liste.length === 0
    });

  avecEtat('#zone-organigramme', async () => blocOrganigramme(await chargerDonnees('organigramme'), POLE.cle),
    (bloc, conteneur) => rendreOrganigramme(POLE, bloc, conteneur), {
      squelette: 2, compact: true,
      texteChargement: 'Chargement de l’organigramme du pôle…',
      titreErreur: 'Organigramme indisponible',
      titreVide: 'Aucune équipe déclarée',
      texteVide: 'Ce pôle n’a encore ni responsable ni squad dans l’organigramme du service.'
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

/* =========================================================================
   ETII Hub — La palette : rechercher partout, depuis n'importe quelle page

   Ctrl K (⌘ K) ou le bouton « Rechercher » de la barre ouvrent une
   fenêtre avec un seul champ. Il cherche en même temps dans les documents,
   la base de connaissances, l'organigramme, les réunions, les porteurs et
   la communication, et mène directement à la bonne page, au bon élément.
   Les données sont chargées une seule fois, à la première ouverture.

   Les liens produits respectent les contrats d'URL des pages :
     docsearch.html#q=…            faq.html#pole=…&question=…
     organigramme.html#pole=…&personne=…   reunions.html#pole=…&onglet=…&reunion=…
     index.html#communication=…    etiia.html#communication=…
     index.html#porteur=…
   ========================================================================= */

import { el, monter, ouvrirModale, surlignerVers, annoncer, debounce } from './ui.js';
import { chargerDonnees } from './data.js';
import { creerIndex, rechercher, surligner } from './search.js';

const GROUPES = [
  { cle: 'page', titre: 'Pages' },
  { cle: 'document', titre: 'Documents' },
  { cle: 'question', titre: 'Base de connaissances' },
  { cle: 'personne', titre: 'Personnes' },
  { cle: 'reunion', titre: 'Réunions' },
  { cle: 'porteur', titre: 'Porteurs' },
  { cle: 'communication', titre: 'Communication' }
];

const PAGES = [
  { titre: 'Tableau de bord ETII', sousTitre: 'Communication Center, porteurs, suivi OTQ / OTD', href: 'index.html' },
  /* Le sous-titre et le texte d'un pôle reprennent sa description (pole.js) :
     les deux champs sont indexés, donc l'espace devient trouvable par son
     sujet (« nommage », « routage ») et plus seulement par son code. */
  { titre: 'ETIIA — Squelette & ADN', sousTitre: 'Logique et règles d’architecture', href: 'etiia.html',
    texte: 'Logique et règles d’architecture : découpage fonctionnel, conventions de nommage '
      + 'et principes que tous les autres travaux appliquent ensuite.' },
  { titre: 'ETIIE — Système nerveux', sousTitre: 'Schémas électriques et communication entre systèmes', href: 'etiie.html',
    texte: 'Schémas électriques et communication entre systèmes : signaux, interfaces '
      + 'et cohérence des échanges d’un bout à l’autre de la définition.' },
  { titre: 'ETIII — Structure & harnais', sousTitre: 'Intégration physique et routage dans la maquette numérique', href: 'etiii.html',
    texte: 'Intégration physique et routage dans la maquette numérique : cheminements, '
      + 'fixations et vérification des interférences avant fabrication.' },
  { titre: 'Recherche documentaire', sousTitre: 'Le fonds du service, filtres métier, porteur, pôle', href: 'docsearch.html' },
  { titre: 'Base de connaissances', sousTitre: 'Questions fréquentes et demandes aux experts', href: 'faq.html' },
  { titre: 'Réunions', sousTitre: 'Les comptes-rendus du service et des pôles', href: 'reunions.html' },
  { titre: 'Organigramme', sousTitre: 'Arbre, trombinoscope, compétences', href: 'organigramme.html' }
];

const PAR_GROUPE = 4;

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function liste(v) { return Array.isArray(v) ? v.map(texte).filter(Boolean) : (texte(v) ? [texte(v)] : []); }
function encoder(v) { return encodeURIComponent(texte(v)); }

/* -------------------------------------------------------------------------
   1. Le corpus : une entrée par chose atteignable
   ------------------------------------------------------------------------- */

let corpus = null;      // Promise<{ index, entrees, echecs }>

function entreesDocuments(d) {
  return (d && Array.isArray(d.documents) ? d.documents : []).filter((x) => x && texte(x.titre)).map((x) => ({
    id: 'document-' + texte(x.id), groupe: 'document',
    titre: texte(x.titre),
    sousTitre: [texte(x.type), texte(x.reference), texte(x.porteur) ? 'porteur du document : ' + texte(x.porteur) : ''].filter(Boolean).join(' · '),
    texte: [texte(x.description), liste(x.motsCles).join(' '), liste(x.metier).join(' '), texte(x.perimetre)].join(' '),
    href: 'docsearch.html#q=' + encoder(texte(x.reference) || texte(x.titre))
  }));
}

function entreesFaq(d) {
  return (d && Array.isArray(d.questions) ? d.questions : []).filter((x) => x && texte(x.question)).map((x) => ({
    id: 'question-' + texte(x.id), groupe: 'question',
    titre: texte(x.question),
    sousTitre: [texte(x.categorie), texte(x.pole) ? (texte(x.pole) === 'ETII' ? 'service' : 'pôle ' + texte(x.pole)) : ''].filter(Boolean).join(' · '),
    texte: [texte(x.reponse), liste(x.motsCles).join(' ')].join(' '),
    href: 'faq.html#pole=' + encoder(texte(x.pole) || 'ETII') + '&question=' + encoder(x.id)
  }));
}

function entreesPersonnes(d) {
  const sorties = [];
  if (!d) return sorties;
  const pousser = (p, pole, squad, role) => {
    if (!p || !texte(p.nom)) return;
    sorties.push({
      id: 'personne-' + texte(p.id), groupe: 'personne',
      titre: texte(p.nom),
      sousTitre: [texte(p.poste), pole ? (pole === 'ETII' ? 'direction' : 'pôle ' + pole) : '', squad, texte(p.perimetre)].filter(Boolean).join(' · '),
      texte: [texte(p.poste), texte(p.perimetre), squad, role, texte(p.id)].join(' '),
      href: 'organigramme.html#pole=' + encoder(pole || 'ETII') + '&personne=' + encoder(p.id)
    });
  };
  if (d.direction) pousser(d.direction, 'ETII', '', 'direction');
  for (const pole of (Array.isArray(d.poles) ? d.poles : [])) {
    if (!pole) continue;
    pousser(pole.responsable, texte(pole.pole), '', 'responsable');
    for (const squad of (Array.isArray(pole.squads) ? pole.squads : [])) {
      for (const m of (Array.isArray(squad && squad.membres) ? squad.membres : [])) {
        pousser(m, texte(pole.pole), texte(squad.nom), texte(m && m.role));
      }
    }
  }
  return sorties;
}

function entreesReunions(d) {
  if (!d) return [];
  const faire = (liste_, onglet, etiquette) => (Array.isArray(liste_) ? liste_ : []).filter((r) => r && texte(r.titre)).map((r) => ({
    id: 'reunion-' + onglet + '-' + texte(r.id), groupe: 'reunion',
    titre: texte(r.titre),
    sousTitre: [etiquette, texte(r.date), texte(r.lieu), texte(r.pole) ? 'pôle ' + texte(r.pole) : ''].filter(Boolean).join(' · '),
    texte: [texte(r.synthese), texte(r.objectif), (r.sujets || []).map((s) => (s && s.titre) + ' ' + (s && s.notes)).join(' '),
      liste(r.actions).join(' '), liste(r.decisions).join(' ')].join(' '),
    href: 'reunions.html#pole=' + encoder(texte(r.pole) || 'ETII') + '&onglet=' + onglet + '&reunion=' + encoder(r.id)
  }));
  return faire(d.comptesRendus, 'cr', 'compte-rendu').concat(faire(d.prochainsPoints, 'pp', 'prochain point'));
}

function entreesPorteurs(d) {
  return (d && Array.isArray(d.flotte) ? d.flotte : []).filter((a) => a && texte(a.code)).map((a) => {
    const fiche = (a.fiche && typeof a.fiche === 'object') ? a.fiche : {};
    return {
      id: 'porteur-' + texte(a.code), groupe: 'porteur',
      titre: texte(fiche.nom) || texte(a.code),
      sousTitre: [texte(a.categorie), texte(a.segment) || texte(fiche.segment), liste(a.poles).map((p) => 'pôle ' + p).join(', ')].filter(Boolean).join(' · '),
      texte: [texte(a.code), texte(fiche.ancienNom), texte(fiche.resume), (fiche.insolites || []).map((f) => f && f.texte).join(' ')].join(' '),
      href: 'index.html#porteur=' + encoder(a.code)
    };
  });
}

/* Une annonce se lit dans le Communication Center : celui du service sur
   le tableau de bord, celui du pôle dans son espace. */
function pageDuPole(code) {
  const c = texte(code).toUpperCase();
  return (c && c !== 'ETII') ? c.toLowerCase() + '.html' : 'index.html';
}

/** « service » ou « pôle ETIIA », pour le sous-titre d'une entrée. */
function perimetreLisible(code) {
  const c = texte(code).toUpperCase();
  return (!c || c === 'ETII') ? 'service' : 'pôle ' + c;
}

/* Les lignes d'un bloc, ou d'un corps à plat : les deux formes cohabitent
   dans communications.json et kiosque.js les rend toutes les deux. Une
   annonce écrite en blocs n'était cherchable que par son titre. */
function lignesLisibles(brut) {
  if (Array.isArray(brut)) return brut.map((l) => (l && typeof l === 'object') ? texte(l.texte) : texte(l));
  return [texte(brut)];
}

/** Tout ce qui se lit dans une entrée de communication, mis à plat. */
function texteCommunication(e) {
  const morceaux = lignesLisibles(e.corps);
  for (const b of (Array.isArray(e.blocs) ? e.blocs : [])) {
    if (!b || typeof b !== 'object') continue;
    morceaux.push(texte(b.titre), texte(b.texte), texte(b.legende));
    morceaux.push(...lignesLisibles(b.lignes), ...liste(b.pastilles));
    for (const i of (Array.isArray(b.images) ? b.images : [])) morceaux.push(i ? texte(i.legende) : '');
  }
  return morceaux.filter(Boolean).join(' ');
}

/* Une entrée porte le fragment que le kiosque sait sélectionner :
   « mot-du-chef », « annonce-<id> », « agenda-<id> » — les identifiants que
   dossiersDepuisCommunications() (kiosque.js) fabrique. Ne PAS importer cette
   fonction : mesuré, l'import fait entrer les photos des communications dans
   les trois pages qui ne les affichent pas (+2,8 Mo dans le fichier autonome,
   au-delà de la limite). tests/palette.e2e.mjs ouvre chaque lien et vérifie
   la carte obtenue : les deux conventions ne peuvent plus diverger en silence. */
function entreeCommunication(e, cle, sousTitre) {
  return {
    id: 'communication-' + cle, groupe: 'communication',
    titre: texte(e.titre), sousTitre,
    texte: [texte(e.resume), texteCommunication(e)].filter(Boolean).join(' '),
    href: pageDuPole(e.pole) + '#communication=' + encoder(cle)
  };
}

function entreesCommunication(d) {
  if (!d) return [];
  const sorties = [];

  const mot = (d.motDuChef && typeof d.motDuChef === 'object') ? d.motDuChef : null;
  if (mot && texte(mot.titre)) {
    /* L'édito ne se lit qu'au niveau service, quoi que dise son champ pôle. */
    sorties.push(entreeCommunication(Object.assign({}, mot, { pole: 'ETII' }), 'mot-du-chef',
      ['Édito', texte(mot.date), 'service'].filter(Boolean).join(' · ')));
  }

  for (const a of (Array.isArray(d.annonces) ? d.annonces : [])) {
    if (!a || !texte(a.titre)) continue;
    sorties.push(entreeCommunication(a, 'annonce-' + texte(a.id),
      [texte(a.categorie) || 'annonce', texte(a.date), perimetreLisible(a.pole)].filter(Boolean).join(' · ')));
  }

  for (const a of (Array.isArray(d.agenda) ? d.agenda : [])) {
    if (!a || !texte(a.titre)) continue;
    /* L'agenda à venir n'est affiché nulle part dans le site : son titre et
       sa date se lisent ici, et le lien mène à la page, sans fragment. */
    if (texte(a.statut) === 'a-venir') {
      sorties.push({
        id: 'agenda-' + texte(a.id), groupe: 'communication',
        titre: texte(a.titre),
        sousTitre: ['à venir', texte(a.date), texte(a.type), perimetreLisible(a.pole)].filter(Boolean).join(' · '),
        texte: texte(a.resume),
        href: pageDuPole(a.pole)
      });
      continue;
    }
    /* Le jumeau d'agenda de l'édito est écarté comme le kiosque l'écarte :
       sans ça, « Un trimestre qui se tient » sortirait deux fois. */
    if (texte(a.type) === 'mot') continue;
    sorties.push(entreeCommunication(Object.assign({}, a, { corps: a.corps || a.resume }),
      'agenda-' + texte(a.id),
      [texte(a.type) || 'agenda', texte(a.date), perimetreLisible(a.pole)].filter(Boolean).join(' · ')));
  }

  return sorties;
}

const JEUX = ['documents', 'faq', 'organigramme', 'reunions', 'flotte', 'communications'];

async function construireCorpus() {
  /* allSettled et non all : un jeu absent ne doit pas faire tomber les cinq
     autres — mais il ne doit pas non plus passer inaperçu, d'où `echecs`. */
  const issues = await Promise.allSettled(JEUX.map((nom) => chargerDonnees(nom)));
  const [documents, faq, organigramme, reunions, flotte, communications] =
    issues.map((r) => (r.status === 'fulfilled' ? r.value : null));
  const echecs = JEUX.filter((nom, i) => issues[i].status === 'rejected');
  const entrees = PAGES.map((p, i) => Object.assign({ id: 'page-' + i, groupe: 'page', texte: '' }, p))
    .concat(entreesDocuments(documents), entreesFaq(faq), entreesPersonnes(organigramme),
            entreesReunions(reunions), entreesPorteurs(flotte), entreesCommunication(communications));
  const index = creerIndex(entrees, [
    { nom: 'titre', poids: 6 }, { nom: 'sousTitre', poids: 2 }, { nom: 'texte', poids: 1 }]);
  return { index, entrees, echecs };
}

function corpusPret() {
  if (!corpus) {
    const promesse = construireCorpus();
    /* Un corpus incomplet ne se mémoïse pas : la prochaine ouverture retente,
       comme data.js purge ses promesses rejetées. */
    promesse.then((d) => { if (d.echecs.length) corpus = null; }, () => { corpus = null; });
    corpus = promesse;
  }
  return corpus;
}

/* -------------------------------------------------------------------------
   2. La fenêtre
   ------------------------------------------------------------------------- */

let ouverte = false;

function ligneResultat(entree, requete, actif) {
  return el('li', { role: 'option', id: 'palette-' + entree.id, 'aria-selected': actif ? 'true' : 'false',
    class: ['palette__resultat', actif ? 'palette__resultat--actif' : null], dataset: { href: entree.href } },
    el('a', { class: 'palette__lien', href: entree.href, tabIndex: -1 },
      el('span', { class: 'palette__titre' }, requete ? surlignerVers(surligner(entree.titre, requete)) : entree.titre),
      entree.sousTitre ? el('span', { class: 'palette__sous-titre' }, requete ? surlignerVers(surligner(entree.sousTitre, requete)) : entree.sousTitre) : null));
}

function ouvrirPalette(declencheur) {
  if (ouverte) return;
  ouverte = true;

  const champ = el('input', { type: 'search', class: 'palette__champ', id: 'palette-champ', autocomplete: 'off',
    placeholder: 'Un document, une question, une personne, une réunion, un porteur…',
    role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'palette-resultats', 'aria-autocomplete': 'list' });
  const resultats = el('ul', { class: 'palette__resultats', id: 'palette-resultats', role: 'listbox', 'aria-label': 'Résultats' });
  const etat = el('p', { class: 'palette__etat', role: 'status', 'aria-live': 'polite' }, 'Chargement des données…');
  let visibles = []; let position = 0; let fermer = () => {};

  const rendre = (requete, donnees) => {
    const q = texte(requete);
    let retenus;
    if (!q) {
      retenus = donnees.entrees.filter((e) => e.groupe === 'page');
    } else {
      /* Sans limite : la coupe se fait par groupe, après le comptage, sinon
         le « / n » affiché est la limite et non un total. Le classement
         portait déjà sur tout le corpus. */
      retenus = rechercher(donnees.index, q).map((r) => r.doc);
    }
    visibles = [];
    const enfants = [];
    /* `retenus` est trié par score décroissant : l'ordre de PREMIÈRE
       apparition des groupes est donc leur ordre par meilleur score. Le
       premier résultat de la fenêtre est le meilleur, et Entrée l'ouvre. À
       requête vide, `retenus` ne contient que des pages : écran inchangé. */
    const ordre = Array.from(new Set(retenus.map((e) => e.groupe)))
      .map((cle) => GROUPES.find((g) => g.cle === cle)).filter(Boolean);
    for (const g of ordre) {
      const membres = retenus.filter((e) => e.groupe === g.cle);
      if (!membres.length) continue;
      const total = membres.length;
      const montres = q ? membres.slice(0, PAR_GROUPE) : membres;
      enfants.push(el('li', { class: 'palette__groupe', role: 'presentation' },
        el('span', {}, g.titre),
        el('span', { class: 'mono' }, total > montres.length ? montres.length + ' / ' + total : String(total))));
      for (const e of montres) { visibles.push(e); enfants.push(ligneResultat(e, q, visibles.length - 1 === position)); }
    }
    monter(resultats, enfants);
    /* Un jeu de données absent se dit ici : palette__etat est déjà la région
       live de la fenêtre, donc le message est relu à chaque frappe. */
    const prefixe = donnees.echecs.length
      ? 'Résultats incomplets (' + donnees.echecs.join(', ') + ' non chargé'
        + (donnees.echecs.length > 1 ? 's' : '') + ') — '
      : '';
    etat.textContent = prefixe + (q ? (visibles.length ? visibles.length + ' résultat' + (visibles.length > 1 ? 's' : '') + ' — ↑ ↓ pour choisir, Entrée pour ouvrir'
                                            : 'Aucun résultat pour « ' + q + ' »')
                         : 'Tapez pour chercher partout. ↑ ↓ pour choisir, Entrée pour ouvrir.');
    champ.setAttribute('aria-activedescendant', visibles[position] ? 'palette-' + visibles[position].id : '');
  };

  const marquer = () => {
    resultats.querySelectorAll('.palette__resultat').forEach((li, i) => {
      const actif = i === position;
      li.classList.toggle('palette__resultat--actif', actif);
      li.setAttribute('aria-selected', actif ? 'true' : 'false');
      if (actif && typeof li.scrollIntoView === 'function') li.scrollIntoView({ block: 'nearest' });
    });
    champ.setAttribute('aria-activedescendant', visibles[position] ? 'palette-' + visibles[position].id : '');
  };

  const ouvrirCourant = () => {
    const cible = visibles[position];
    if (!cible) return;
    fermer();
    window.location.href = cible.href;
  };

  const api = ouvrirModale({
    titre: 'Rechercher partout',
    classe: 'modale--palette',
    declencheur: declencheur || null,
    contenu: () => el('div', { class: 'palette' },
      el('label', { class: 'visuellement-cache', for: 'palette-champ' }, 'Rechercher partout'),
      el('div', { class: 'palette__barre' }, el('span', { class: 'palette__loupe', 'aria-hidden': 'true' }, '⌕'), champ,
        el('kbd', { class: 'palette__kbd' }, 'Échap')),
      etat, resultats),
    onFermeture: () => { ouverte = false; }
  });
  fermer = api.fermer;

  corpusPret().then((donnees) => {
    rendre('', donnees);
    const chercher = debounce(() => { position = 0; rendre(champ.value, donnees); }, 80);
    champ.addEventListener('input', chercher);
    champ.addEventListener('keydown', (evt) => {
      if (evt.key === 'ArrowDown') { evt.preventDefault(); position = Math.min(visibles.length - 1, position + 1); marquer(); }
      else if (evt.key === 'ArrowUp') { evt.preventDefault(); position = Math.max(0, position - 1); marquer(); }
      else if (evt.key === 'Enter') { evt.preventDefault(); ouvrirCourant(); }
    });
    resultats.addEventListener('click', (evt) => {
      const li = evt.target.closest('.palette__resultat');
      if (!li) return;
      evt.preventDefault();
      position = Array.from(resultats.querySelectorAll('.palette__resultat')).indexOf(li);
      ouvrirCourant();
    });
    annoncer('Recherche prête : ' + donnees.entrees.length + ' entrées.');
  }).catch(() => {
    /* Garde-fou : un jeu qui ne se charge pas passe désormais par `echecs`.
       Il reste ce catch si construireCorpus lève (index, entrée malformée) :
       sans lui la fenêtre resterait figée sur « Chargement des données… ». */
    etat.textContent = 'Les données n’ont pas pu être chargées.';
  });

  setTimeout(() => champ.focus(), 30);
}

/* -------------------------------------------------------------------------
   3. Accroche : le bouton de la barre et Ctrl K
   ------------------------------------------------------------------------- */

function installer() {
  document.querySelectorAll('[data-palette]').forEach((bouton) => {
    bouton.addEventListener('click', (evt) => ouvrirPalette(evt.currentTarget));
  });
  document.addEventListener('keydown', (evt) => {
    if ((evt.ctrlKey || evt.metaKey) && !evt.altKey && (evt.key === 'k' || evt.key === 'K')) {
      evt.preventDefault();
      ouvrirPalette(document.querySelector('[data-palette]'));
    }
  });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installer);
else installer();

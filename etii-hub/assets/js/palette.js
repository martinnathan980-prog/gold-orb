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
     communication.html#pole=…&annonce=…   index.html#porteur=…
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
  { titre: 'ETIIA — Squelette & ADN', sousTitre: 'Espace du pôle', href: 'etiia.html' },
  { titre: 'ETIIE — Système nerveux', sousTitre: 'Espace du pôle', href: 'etiie.html' },
  { titre: 'ETIII — Structure & harnais', sousTitre: 'Espace du pôle', href: 'etiii.html' },
  { titre: 'Recherche documentaire', sousTitre: 'Le fonds du service, filtres métier, porteur, pôle', href: 'docsearch.html' },
  { titre: 'Base de connaissances', sousTitre: 'Questions fréquentes et demandes aux experts', href: 'faq.html' },
  { titre: 'Réunions', sousTitre: 'Les comptes-rendus du service et des pôles', href: 'reunions.html' },
  { titre: 'Organigramme', sousTitre: 'Arbre, trombinoscope, compétences', href: 'organigramme.html' }
];

const PAR_GROUPE = 4;
const LIMITE = 40;

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function liste(v) { return Array.isArray(v) ? v.map(texte).filter(Boolean) : (texte(v) ? [texte(v)] : []); }
function encoder(v) { return encodeURIComponent(texte(v)); }

/* -------------------------------------------------------------------------
   1. Le corpus : une entrée par chose atteignable
   ------------------------------------------------------------------------- */

let corpus = null;      // Promise<{ index, entrees }>

async function jeu(nom) {
  try { return await chargerDonnees(nom); } catch (_e) { return null; }
}

function entreesDocuments(d) {
  return (d && Array.isArray(d.documents) ? d.documents : []).filter((x) => x && texte(x.titre)).map((x) => ({
    id: 'document-' + texte(x.id), groupe: 'document',
    titre: texte(x.titre),
    sousTitre: [texte(x.type), texte(x.reference), texte(x.porteur) ? 'porteur : ' + texte(x.porteur) : ''].filter(Boolean).join(' · '),
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

function entreesCommunication(d) {
  if (!d) return [];
  const annonces = (Array.isArray(d.annonces) ? d.annonces : []).filter((a) => a && texte(a.titre)).map((a) => ({
    id: 'annonce-' + texte(a.id), groupe: 'communication',
    titre: texte(a.titre),
    sousTitre: ['annonce', texte(a.date), texte(a.categorie), texte(a.pole) ? (texte(a.pole) === 'ETII' ? 'service' : 'pôle ' + texte(a.pole)) : ''].filter(Boolean).join(' · '),
    texte: [texte(a.resume), (a.corps || []).map((l) => l && l.texte).join(' ')].join(' '),
    href: pageDuPole(a.pole)
  }));
  const agenda = (Array.isArray(d.agenda) ? d.agenda : []).filter((a) => a && texte(a.titre)).map((a) => ({
    id: 'agenda-' + texte(a.id), groupe: 'communication',
    titre: texte(a.titre),
    sousTitre: [texte(a.statut) === 'a-venir' ? 'à venir' : 'passé', texte(a.date), texte(a.type), texte(a.pole) ? (texte(a.pole) === 'ETII' ? 'service' : 'pôle ' + texte(a.pole)) : ''].filter(Boolean).join(' · '),
    texte: texte(a.resume),
    href: pageDuPole(a.pole)
  }));
  return annonces.concat(agenda);
}

async function construireCorpus() {
  const [documents, faq, organigramme, reunions, flotte, communications] = await Promise.all(
    ['documents', 'faq', 'organigramme', 'reunions', 'flotte', 'communications'].map(jeu));
  const entrees = PAGES.map((p, i) => Object.assign({ id: 'page-' + i, groupe: 'page', texte: '' }, p))
    .concat(entreesDocuments(documents), entreesFaq(faq), entreesPersonnes(organigramme),
            entreesReunions(reunions), entreesPorteurs(flotte), entreesCommunication(communications));
  const index = creerIndex(entrees, [
    { nom: 'titre', poids: 6 }, { nom: 'sousTitre', poids: 2 }, { nom: 'texte', poids: 1 }]);
  return { index, entrees };
}

function corpusPret() {
  if (!corpus) corpus = construireCorpus();
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
      retenus = rechercher(donnees.index, q, { limite: LIMITE }).map((r) => r.doc);
    }
    visibles = [];
    const enfants = [];
    for (const g of GROUPES) {
      const membres = retenus.filter((e) => e.groupe === g.cle);
      if (!membres.length) continue;
      const montres = q ? membres.slice(0, PAR_GROUPE) : membres;
      enfants.push(el('li', { class: 'palette__groupe', role: 'presentation' },
        el('span', {}, g.titre), membres.length > montres.length
          ? el('span', { class: 'mono' }, montres.length + ' / ' + membres.length) : el('span', { class: 'mono' }, String(membres.length))));
      for (const e of montres) { visibles.push(e); enfants.push(ligneResultat(e, q, visibles.length - 1 === position)); }
    }
    monter(resultats, enfants);
    etat.textContent = q ? (visibles.length ? visibles.length + ' résultat' + (visibles.length > 1 ? 's' : '') + ' — ↑ ↓ pour choisir, Entrée pour ouvrir'
                                            : 'Aucun résultat pour « ' + q + ' »')
                         : 'Tapez pour chercher partout. ↑ ↓ pour choisir, Entrée pour ouvrir.';
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
  }).catch(() => { etat.textContent = 'Les données n’ont pas pu être chargées.'; });

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

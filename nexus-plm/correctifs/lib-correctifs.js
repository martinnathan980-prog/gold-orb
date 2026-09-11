/**
 * NEXUS PLM — lot 1 : correction des 6 bugs confirmés.
 *
 * Ce fichier ne contient que les fonctions PURES des correctifs (aucun accès au
 * DOM), pour qu'elles soient testables hors navigateur — voir test-correctifs.js.
 * Les remplacements qui touchent au DOM sont dans CORRECTIFS.md.
 *
 * À coller tel quel en haut du <script> de Index.html.
 */

// ============================================================
// B6 — affichage d'une valeur éventuellement vide
// ============================================================
// String(undefined) vaut "undefined", qui est truthy : le ||'-' du code actuel
// ne se déclenchait jamais et "undefined" s'affichait sur les cartes.
function txt(valeur, defaut) {
  if (defaut === undefined) defaut = '-';
  if (valeur === null || valeur === undefined) return defaut;
  const s = String(valeur).trim();
  return s === '' ? defaut : s;
}

// Valeur multi-lignes -> liste propre (Porteur, Qualifications, Composants STD).
function valeursMulti(valeur) {
  if (valeur === null || valeur === undefined) return [];
  return String(valeur).split(/[\n,]/).map(function (x) { return x.trim(); })
                       .filter(function (x) { return x !== ''; });
}

// ============================================================
// B3 — statut : ne plus confondre "Validé" et "Invalidé"
// ============================================================
// includes('valid') attrapait aussi les négations : "Invalidé" et "Non validé"
// étaient comptés comme validés. On passe à une liste fermée + égalité stricte.
const STATUTS = {
  VALIDE:   ['validé', 'valide'],
  OBSOLETE: ['obsolète', 'obsolete'],
  ETUDE:    ['en étude', 'en etude', 'etude', 'étude']
};

function normaliserStatut(statut) {
  return String(statut === null || statut === undefined ? '' : statut).trim().toLowerCase();
}

function estValide(statut) {
  return STATUTS.VALIDE.indexOf(normaliserStatut(statut)) !== -1;
}

function classeStatut(statut) {
  const s = normaliserStatut(statut);
  if (STATUTS.VALIDE.indexOf(s) !== -1) return 'status-valide';
  if (STATUTS.OBSOLETE.indexOf(s) !== -1) return 'status-obsolete';
  return 'status-etude';
}

// ============================================================
// B4 — export CSV
// ============================================================
// Trois défauts corrigés :
//   - encodeURI n'encode pas '#' : l'URL de données était tronquée au premier '#'
//   - les guillemets internes n'étaient pas doublés : colonnes décalées
//   - pas de BOM : Excel FR affichait "BoÃ®te" au lieu de "Boîte"
// Séparateur ';' car Excel en locale FR n'ouvre pas les ',' en colonnes.
const CSV_SEPARATEUR = ';';

function champCsv(valeur) {
  const s = String(valeur === null || valeur === undefined ? '' : valeur).replace(/\r?\n/g, ' / ');
  return '"' + s.replace(/"/g, '""') + '"';
}

function construireCsv(lignes) {
  const corps = lignes.map(function (ligne) {
    return ligne.map(champCsv).join(CSV_SEPARATEUR);
  }).join('\r\n');
  return '﻿' + corps; // BOM UTF-8
}

function lignesBomPourBoite(boite) {
  const lignes = [['Type', 'PN du type', 'Composants STD', 'Masse (g)', 'DAL', 'HL']];
  (boite.nomenclature || []).forEach(function (nom) {
    lignes.push([
      nom['Type'], nom['PN du type'], nom['Composant STD'],
      nom['Masse (g)'], nom['DAL'], nom['HL']
    ]);
  });
  return lignes;
}

// ============================================================
// B1 — catalogue : conserver l'index RÉEL, pas celui de la liste filtrée
// ============================================================
// Le code passait au onclick l'index dans la liste filtrée, puis le relisait
// dans la liste complète : dès qu'on tapait une recherche, le clic ajoutait
// un autre composant que celui affiché.
const CATALOGUE_MAX_AFFICHE = 30;

function filtrerCatalogueData(catalogue, requete) {
  const q = String(requete || '').toLowerCase();
  const tous = catalogue
    .map(function (c, indexReel) { return { composant: c, indexReel: indexReel }; })
    .filter(function (e) { return JSON.stringify(e.composant).toLowerCase().indexOf(q) !== -1; });
  return { affiches: tous.slice(0, CATALOGUE_MAX_AFFICHE), total: tous.length };
}

// Mise en forme d'un composant du catalogue (extraite : elle était dupliquée
// à l'identique entre filtrerCatalogue et ouvrirMultiRecherche).
function formaterComposant(c) {
  const type = c['Type'] || '';
  const sousType = c['Sous Type/Désignation'] || '';
  const norm = c['Norm'] || c['Standard number'] || c['Ref'] || '';
  return (type + (sousType ? ' | ' + sousType : '') + (norm ? ' (' + norm + ')' : '')).trim();
}

// ============================================================
// B5 — compteurs d'onglets cohérents
// ============================================================
// Les compteurs par fonction utilisaient la liste filtrée, celui de "Toutes"
// la liste brute : les deux se contredisaient à l'écran. On ne filtre plus
// qu'UNE fois et tout est dérivé de ce résultat unique.
// Effet de bord bienvenu : le double JSON.stringify par rendu disparaît, et
// l'onglet actif devenu orphelin retombe automatiquement sur "Toutes".
function correspond(boite, requete) {
  // NOTE : comportement de recherche inchangé pour ce lot (faux positifs sur
  // les noms de colonnes — F5 de l'analyse). Isolé ici pour n'avoir qu'un
  // seul endroit à reprendre au lot 6.
  return JSON.stringify(boite).toLowerCase().indexOf(String(requete || '').toLowerCase()) !== -1;
}

function calculerAffichage(boites, requete, onglet, boitesForcees) {
  const base = boitesForcees ? boitesForcees : boites;
  const visibles = boitesForcees ? base : base.filter(function (b) { return correspond(b, requete); });

  const parFonction = new Map();
  visibles.forEach(function (boite) {
    const f = boite['Fonction'] || 'NON CLASSE';
    if (!parFonction.has(f)) parFonction.set(f, []);
    parFonction.get(f).push(boite);
  });

  // Onglet actif disparu du résultat : on ne laisse pas l'utilisateur bloqué
  // sur un onglet invisible affichant "Aucun assemblage".
  const ongletEffectif = (onglet !== 'Toutes' && !parFonction.has(onglet)) ? 'Toutes' : onglet;

  return {
    visibles: visibles,
    parFonction: parFonction,
    ongletEffectif: ongletEffectif,
    aAfficher: ongletEffectif === 'Toutes' ? visibles : (parFonction.get(ongletEffectif) || [])
  };
}

// ============================================================
// KPI (dépend de B3 et B5)
// ============================================================
function calculerKpi(listeBoites) {
  const refs = new Set();
  listeBoites.forEach(function (b) {
    if (b['PN Global']) refs.add(b['PN Global']);
    (b.nomenclature || []).forEach(function (n) { if (n['PN du type']) refs.add(n['PN du type']); });
  });
  const nbValides = listeBoites.filter(function (b) { return estValide(b['Statut']); }).length;
  return {
    nbBoites: listeBoites.length,
    refsUniques: refs.size,
    nbValides: nbValides,
    pctValides: listeBoites.length > 0 ? Math.round((nbValides / listeBoites.length) * 100) : 0
  };
}

/* istanbul ignore next */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    txt: txt, valeursMulti: valeursMulti,
    normaliserStatut: normaliserStatut, estValide: estValide, classeStatut: classeStatut,
    champCsv: champCsv, construireCsv: construireCsv, lignesBomPourBoite: lignesBomPourBoite,
    filtrerCatalogueData: filtrerCatalogueData, formaterComposant: formaterComposant,
    correspond: correspond, calculerAffichage: calculerAffichage, calculerKpi: calculerKpi
  };
}

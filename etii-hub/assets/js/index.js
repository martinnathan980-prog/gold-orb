/* =========================================================================
   ETII Hub — Page du service (index.html)

   Trois sections, dans l'ordre voulu par le service :
     1. LE COMMUNICATION CENTER — le fil du service à gauche (le mot du
        chef, ce qui vient, l'historique), le projecteur à droite, le
        bandeau des alertes au-dessus. Rendu par kiosque.js.
     2. LES PORTEURS — les appareils suivis, rendus par porteurs.js.
     3. LE SUIVI OTQ / OTD — en attente de sa source : rien n'est inventé.

   Tout le DOM est construit avec el() : aucun innerHTML, aucun
   gestionnaire en attribut HTML.
   ========================================================================= */

import { el, svg, monter, initTheme, initNav } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { porteurs } from './porteurs.js';
import { kiosque, dossiersDepuisCommunications, alertesDepuisCommunications } from './kiosque.js';

const POLES = [
  { cle: 'ETIIA', libelle: 'ETIIA' },
  { cle: 'ETIIE', libelle: 'ETIIE' },
  { cle: 'ETIII', libelle: 'ETIII' }
];

function txt(valeur) {
  if (valeur === null || valeur === undefined) return '';
  return String(valeur).trim();
}

/* -------------------------------------------------------------------------
   1. Le Communication Center
   ------------------------------------------------------------------------- */

/**
 * @param {object} donnees   contenu de communications.json
 * @param {Element} conteneur
 */
function rendreCommunication(donnees, conteneur) {
  verifierForme(donnees, { agenda: 'tableau' }, 'communications.json');
  const dossiers = dossiersDepuisCommunications(donnees, { pole: 'ETII' });
  monter(conteneur, kiosque({
    id: 'kiosque-service',
    dossiers,
    alertes: alertesDepuisCommunications(donnees),
    titreFil: 'Fil du service',
    filtres: POLES
  }));
}

/* -------------------------------------------------------------------------
   2. Les porteurs
   ------------------------------------------------------------------------- */

function rendreFlotte(donnees, conteneur) {
  verifierForme(donnees, { flotte: 'tableau' }, 'flotte.json');
  const avertissement = txt(donnees.avertissement);
  monter(conteneur, el('div', { class: 'pile' },
    porteurs(donnees, { id: 'porteurs-service' }),
    avertissement
      ? el('p', { class: 'flotte-note sans-marge' },
        el('span', { 'aria-hidden': 'true' }, '※'),
        el('span', null, avertissement))
      : null));
}

/* -------------------------------------------------------------------------
   3. Le suivi OTQ / OTD — en attente de raccordement
   ------------------------------------------------------------------------- */

/**
 * POINT DE RACCORDEMENT UNIQUE du suivi OTQ / OTD.
 *
 * Le graphe d'origine interrogeait une source en direct du service, dont
 * la ligne de code n'a pas encore été fournie. Tant qu'elle manque, la
 * page n'affiche NI graphique, NI valeur : aucune donnée d'exemple ne doit
 * pouvoir être prise pour une mesure du service. C'est ici, et nulle part
 * ailleurs, que le raccordement se fera.
 *
 * @returns {null}
 */
function chargerSuiviOTQ() {
  return null;
}

function iconeBranchement() {
  return svg('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    'stroke-width': '1.6', 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
    'aria-hidden': 'true', focusable: 'false' },
    svg('path', { d: 'M9 3v4M15 3v4M7 7h10v4a5 5 0 0 1-10 0V7zM12 16v5' }));
}

function encadreAttente() {
  return el('div', { class: 'attente' },
    el('span', { class: 'attente__icone', 'aria-hidden': 'true' }, iconeBranchement()),
    el('div', { class: 'attente__texte' },
      el('p', { class: 'attente__titre sans-marge' },
        'En attente du raccordement à la source du service'),
      el('p', { class: 'texte-doux sans-marge' },
        'Le suivi OTQ / OTD est alimenté par une source interrogée en direct. '
        + 'Tant que sa ligne de raccordement n’est pas fournie, la section '
        + 'reste vide : aucun graphique, aucune valeur, aucun chiffre '
        + 'd’exemple qui pourrait être pris pour une mesure du service.'),
      el('p', { class: 'texte-doux texte-sm sans-marge' },
        'Le branchement se fait en un seul point : ',
        el('span', { class: 'mono' }, 'chargerSuiviOTQ()'),
        ' dans ',
        el('span', { class: 'mono' }, 'assets/js/index.js'),
        '.')));
}

function rendreSuiviOTQ(conteneur) {
  if (!conteneur) return;
  const suivi = chargerSuiviOTQ();
  if (suivi !== null) {
    console.info('[index] Source de suivi OTQ / OTD fournie : le rendu reste à écrire.');
  }
  monter(conteneur, encadreAttente());
}

/* =========================================================================
   Démarrage — une section, un cycle d'état
   ========================================================================= */

initTheme();
initNav('index.html');

avecEtat('#zone-communication', () => chargerDonnees('communications'), rendreCommunication, {
  squelette: 3,
  texteChargement: 'Chargement de la communication du service…',
  titreErreur: 'Communication indisponible',
  titreVide: 'Aucune communication publiée',
  texteVide: 'Le mot du chef, les jalons et les annonces du service '
    + 'apparaîtront ici dès qu’ils auront été publiés.',
  estVide: (donnees) => !donnees
    || ((!Array.isArray(donnees.agenda) || donnees.agenda.length === 0)
        && (!Array.isArray(donnees.annonces) || donnees.annonces.length === 0)
        && !donnees.motDuChef)
});

avecEtat('#zone-flotte', () => chargerDonnees('flotte'), rendreFlotte, {
  squelette: 2,
  texteChargement: 'Chargement des porteurs…',
  titreErreur: 'Porteurs indisponibles',
  titreVide: 'Aucun porteur suivi',
  texteVide: 'Les appareils suivis par le service apparaîtront ici.',
  estVide: (donnees) => !donnees || !Array.isArray(donnees.flotte)
    || donnees.flotte.length === 0
});

rendreSuiviOTQ(document.getElementById('zone-otq'));

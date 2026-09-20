/* =========================================================================
   ETII Hub — Page du service (index.html)

   Trois sections, dans l'ordre voulu par le service :
     1. LE COMMUNICATION CENTER — le fil du service à gauche (le mot du
        chef, ce qui vient, l'historique), le projecteur à droite, le
        bandeau des alertes au-dessus. Rendu par kiosque.js.
     2. LES PORTEURS — les appareils suivis, rendus par porteurs.js.
     3. LE SUIVI OTQ / OTD — lu dans un CSV : la feuille publiée du service,
        ou l'exemple embarqué, toujours annoncé comme tel (otq.js).

   Tout le DOM est construit avec el() : aucun innerHTML, aucun
   gestionnaire en attribut HTML.
   ========================================================================= */

import { el, monter, initTheme, initNav } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { porteurs } from './porteurs.js';
import { kiosque, dossiersDepuisCommunications, alertesDepuisCommunications } from './kiosque.js';
import { chargerSuivi, rendreSuivi } from './otq.js';

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

function rendreFlotte(ensemble, conteneur) {
  const donnees = ensemble.flotte;
  verifierForme(donnees, { flotte: 'tableau' }, 'flotte.json');
  const avertissement = txt(donnees.avertissement);
  monter(conteneur, el('div', { class: 'pile' },
    porteurs(donnees, { id: 'porteurs-service', equipe: ensemble.equipe, documents: ensemble.documents }),
    avertissement
      ? el('p', { class: 'flotte-note sans-marge' },
        el('span', { 'aria-hidden': 'true' }, '※'),
        el('span', null, avertissement))
      : null));
}

/* -------------------------------------------------------------------------
   3. Le suivi OTQ / OTD — lu dans un CSV (Google Sheet publié, ou exemple)
   Tout le détail est dans otq.js : la source, la lecture, le rendu.
   ------------------------------------------------------------------------- */

function rendreSuiviOTQ(suivi, conteneur) {
  monter(conteneur, rendreSuivi(suivi));
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

/* La flotte a besoin de l'organigramme et du fonds documentaire pour
   relier chaque porteur à son équipe et à ses documents. Les trois
   fichiers sont déjà en cache pour les autres sections. */
avecEtat('#zone-flotte', async () => {
  const [flotte, equipe, documents] = await Promise.all([
    chargerDonnees('flotte'), chargerDonnees('organigramme'), chargerDonnees('documents')]);
  return { flotte, equipe, documents };
}, rendreFlotte, {
  squelette: 2,
  texteChargement: 'Chargement des porteurs…',
  titreErreur: 'Porteurs indisponibles',
  titreVide: 'Aucun porteur suivi',
  texteVide: 'Les appareils suivis par le service apparaîtront ici.',
  estVide: (e) => !e || !e.flotte || !Array.isArray(e.flotte.flotte)
    || e.flotte.flotte.length === 0
});

avecEtat('#zone-otq', chargerSuivi, rendreSuiviOTQ, {
  squelette: 2,
  texteChargement: 'Lecture du suivi OTQ / OTD…',
  titreErreur: 'Suivi OTQ / OTD indisponible',
  titreVide: 'Aucune mesure',
  texteVide: 'Le fichier lu ne contient aucune ligne mensuelle.',
  estVide: (suivi) => !suivi || !suivi.series || suivi.series.mois.length === 0
});

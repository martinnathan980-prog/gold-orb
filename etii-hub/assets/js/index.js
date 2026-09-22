/* =========================================================================
   ETII Hub — Page du service (index.html)

   Quatre sections, dans l'ordre voulu par le service :
     1. LE COMMUNICATION CENTER — le bandeau des alertes, l'édito en
        vedette, l'historique en frise. Rendu par kiosque.js.
     2. À VENIR — les prochains rendez-vous du service (agenda.js).
     3. LES PORTEURS — les appareils suivis, rendus par porteurs.js.
     4. LE SUIVI OTQ / OTD — lu dans un CSV : la feuille publiée du service,
        ou l'exemple embarqué, toujours annoncé comme tel (otq.js).

   Tout se modifie dans la page, en mode édition (edition.js) : les
   communications, les alertes, les rendez-vous, les porteurs. Chaque
   section se redessine seule après un enregistrement.

   Au-dessus, sur la bande de l'en-tête, le sommaire collant (la même
   « petite barre » que sur un espace de pôle) suit la lecture.

   Tout le DOM est construit avec el() : aucun innerHTML, aucun
   gestionnaire en attribut HTML.
   ========================================================================= */

import { el, monter, initTheme, initNav, deleguer, ouvrirModale, suivreSommaire } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { porteurs, creditsPhotos, libellesFiche } from './porteurs.js';
import { creditsCommunications } from './credits.js';
import { kiosque, dossiersDepuisCommunications, alertesDepuisCommunications, noteOrigine } from './kiosque.js';
import { chargerSuivi, rendreSuivi } from './otq.js';
import { chargerCommunications } from './communications.js';
import { ouvrirEditeur } from './editeur.js';
import { installerEdition } from './edition.js';
import { abonnerModifications, supprimerElement } from './modifications.js';
import { agenda } from './agenda.js';
import { modifierCommunication, supprimerDossier, ouvrirAlertes, ouvrirRendezVous, ouvrirPorteur } from './edition-contenus.js';

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
  /* Une ligne, seulement s'il y a quelque chose à dire sur la source : la
     feuille du service n'a pas répondu, ou des lignes n'ont pas été lues. */
  monter(conteneur, noteOrigine(donnees), kiosque({
    id: 'kiosque-service',
    dossiers,
    alertes: alertesDepuisCommunications(donnees),
    titreFil: 'Communications',
    filtres: POLES,
    /* Les commandes d'édition : visibles en mode édition seulement. La
       section se redessine d'elle-même après un enregistrement (voir
       abonnerModifications, plus bas). */
    surAjout: (bouton) => ouvrirEditeur({ pole: 'ETII', declencheur: bouton }),
    surModifier: (dossier, bouton) => modifierCommunication(dossier, bouton, 'ETII'),
    surSupprimer: (dossier) => supprimerDossier(dossier),
    surAlertes: (bouton) => ouvrirAlertes({ alertes: donnees.alertesDetail, declencheur: bouton })
  }));
}

/* -------------------------------------------------------------------------
   1 bis. À venir
   ------------------------------------------------------------------------- */

function rendreAgenda(donnees, conteneur) {
  monter(conteneur, agenda(donnees, {
    pole: 'ETII',
    limite: 6,
    surAjouter: (b) => ouvrirRendezVous({ pole: 'ETII', declencheur: b }),
    surModifier: (entree, b) => ouvrirRendezVous({ existant: entree, declencheur: b }),
    surSupprimer: (entree) => supprimerElement('communications', 'agenda', entree.id)
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
    porteurs(donnees, {
      id: 'porteurs-service', equipe: ensemble.equipe, documents: ensemble.documents,
      surAjouter: (b) => ouvrirPorteur({ flotte: donnees, libelles: libellesFiche(), declencheur: b }),
      surModifier: (appareil, b) => ouvrirPorteur({ existant: appareil, flotte: donnees, libelles: libellesFiche(), declencheur: b }),
      surSupprimer: (appareil) => supprimerElement('flotte', 'porteur', appareil.code)
    }),
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
installerEdition();
/* Le sommaire : Communication · Porteurs · Suivi OTQ / OTD, le lien
   courant marqué au fil du défilement (le mécanisme des espaces de pôle). */
suivreSommaire();

function chargerCommunicationCenter() {
  avecEtat('#zone-communication', chargerCommunications, rendreCommunication, {
    squelette: 3,
    texteChargement: 'Chargement de la communication du service…',
    titreErreur: 'Communication indisponible',
    /* Jamais « vide » : un kiosque sans communication garde, en mode
       édition, son bouton « Ajouter une communication ». */
    estVide: () => false
  });
}
chargerCommunicationCenter();

function chargerAgenda() {
  avecEtat('#zone-agenda', chargerCommunications, rendreAgenda, {
    squelette: 1,
    texteChargement: 'Chargement des prochains rendez-vous…',
    titreErreur: 'Agenda indisponible',
    estVide: () => false
  });
}
chargerAgenda();

/* La flotte a besoin de l'organigramme et du fonds documentaire pour
   relier chaque porteur à son équipe et à ses documents. Les trois
   fichiers sont déjà en cache pour les autres sections. */
function chargerFlotte() {
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
  estVide: () => false
});
}
chargerFlotte();

/* Une modification enregistrée redessine les sections qui en dépendent :
   data.js a déjà oublié le jeu, la section le relit. */
abonnerModifications((jeu) => {
  if (jeu === 'communications') { chargerCommunicationCenter(); chargerAgenda(); }
  if (jeu === 'flotte' || jeu === 'organigramme' || jeu === 'documents') chargerFlotte();
});

/* Les crédits des photos de la flotte : une obligation de licence, lisible
   en un seul endroit depuis le pied de page. Les données sont déjà en
   cache si la section des porteurs s'est affichée ; sinon on les charge. */
deleguer(document, '[data-credits-photos]', 'click', async (evt, lien) => {
  evt.preventDefault();
  let flotte = null; let communications = null;
  try { flotte = await chargerDonnees('flotte'); } catch (_e) { flotte = null; }
  try { communications = await chargerCommunications(); } catch (_e) { communications = null; }
  ouvrirModale({
    titre: 'Crédits photos',
    declencheur: lien,
    contenu: el('div', { class: 'pile' },
      flotte
        ? creditsPhotos(flotte)
        : el('p', { class: 'texte-doux sans-marge' }, 'Les crédits des porteurs ne peuvent pas être lus pour le moment.'),
      creditsCommunications(communications))
  });
});

avecEtat('#zone-otq', chargerSuivi, rendreSuiviOTQ, {
  squelette: 2,
  texteChargement: 'Lecture du suivi OTQ / OTD…',
  titreErreur: 'Suivi OTQ / OTD indisponible',
  titreVide: 'Aucune mesure',
  texteVide: 'Le fichier lu ne contient aucune ligne mensuelle.',
  estVide: (suivi) => !suivi || !suivi.series || suivi.series.mois.length === 0
});

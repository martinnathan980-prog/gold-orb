/* =========================================================================
   ETII Hub — Page du service (index.html)

   Trois sections, dans l'ordre voulu par le service :
     1. LE COMMUNICATION CENTER — le bandeau des alertes, le mot du chef
        en vedette, l'historique en cartes. Rendu par kiosque.js.
     2. LES PORTEURS — les appareils suivis, rendus par porteurs.js.
     3. LE SUIVI OTQ / OTD — lu dans un CSV : la feuille publiée du service,
        ou l'exemple embarqué, toujours annoncé comme tel (otq.js).

   Au-dessus, sur la bande de l'en-tête, le sommaire collant (la même
   « petite barre » que sur un espace de pôle) suit la lecture.

   Tout le DOM est construit avec el() : aucun innerHTML, aucun
   gestionnaire en attribut HTML.
   ========================================================================= */

import { el, monter, initTheme, initNav, deleguer, ouvrirModale, suivreSommaire } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { porteurs, creditsPhotos } from './porteurs.js';
import { creditPhoto } from './credits.js';
import { kiosque, dossiersDepuisCommunications, alertesDepuisCommunications, noteOrigine } from './kiosque.js';
import { chargerSuivi, rendreSuivi } from './otq.js';
import { chargerCommunications } from './communications.js';
import { ouvrirEditeur } from './editeur.js';

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
    /* « Ajouter une communication » : l'éditeur s'ouvre ici, et la
       section se recharge une fois la communication publiée. */
    surAjout: (bouton) => ouvrirEditeur({ pole: 'ETII', declencheur: bouton, surPublication: chargerCommunicationCenter })
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
/* Le sommaire : Communication · Porteurs · Suivi OTQ / OTD, le lien
   courant marqué au fil du défilement (le mécanisme des espaces de pôle). */
suivreSommaire();

function chargerCommunicationCenter() {
  avecEtat('#zone-communication', chargerCommunications, rendreCommunication, {
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
}
chargerCommunicationCenter();

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

/* Les images des communications qui portent un crédit (photos sous licence
   libre) : même obligation, même fenêtre. Une photo du service, sans
   crédit, n'a rien à déclarer. */
function creditsCommunications(communications) {
  const c = (communications && typeof communications === 'object') ? communications : {};
  const entrees = [c.motDuChef].concat(Array.isArray(c.annonces) ? c.annonces : []).filter((e) => e && typeof e === 'object');
  const images = [];
  for (const e of entrees) {
    const blocs = Array.isArray(e.blocs) ? e.blocs : [];
    const candidates = [e.image].concat(blocs.filter((b) => b && b.type === 'image'), blocs.filter((b) => b && b.type === 'galerie').flatMap((b) => b.images || []));
    for (const im of candidates) {
      if (!im || typeof im !== 'object' || !im.credit || typeof im.credit !== 'object') continue;
      if (images.some((x) => x.src === im.src)) continue;
      images.push({ src: im.src, alt: im.alt, credit: im.credit, titre: txt(e.titre) });
    }
  }
  if (!images.length) return null;
  return el('div', { class: 'pile pile--serree' },
    el('h3', { class: 'sans-marge' }, 'Images des communications'),
    el('ul', { class: 'porteurs__credits', role: 'list' }, images.map((im) => el('li', { class: 'porteurs__credits-item' },
      el('img', { src: im.src, alt: '', loading: 'lazy', decoding: 'async', class: 'porteurs__credits-vignette' }),
      el('div', { class: 'porteurs__credits-texte' },
        el('span', { class: 'porteurs__credits-nom' }, im.titre),
        creditPhoto(im.credit))))));
}

avecEtat('#zone-otq', chargerSuivi, rendreSuiviOTQ, {
  squelette: 2,
  texteChargement: 'Lecture du suivi OTQ / OTD…',
  titreErreur: 'Suivi OTQ / OTD indisponible',
  titreVide: 'Aucune mesure',
  texteVide: 'Le fichier lu ne contient aucune ligne mensuelle.',
  estVide: (suivi) => !suivi || !suivi.series || suivi.series.mois.length === 0
});

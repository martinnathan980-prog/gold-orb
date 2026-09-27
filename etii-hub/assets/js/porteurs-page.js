/* =========================================================================
   ETII Hub — La page des porteurs (porteurs.html)

   Un seul écran pour regarder la flotte : la galerie, la fiche d'un
   appareil, la comparaison de deux ou trois (porteurs.js). La page ne fait
   que brancher le composant sur ses données et sur le mode édition :
     - flotte.json se charge une fois, puis se relit après chaque
       modification enregistrée (modifications.js prévient la page) ;
     - « Ajouter un porteur », « Modifier », « Supprimer » ouvrent les
       formulaires d'edition-contenus.js, en mode édition seulement ;
     - le lien « Crédits photos » du pied de page ouvre les crédits des
       photos de la flotte, obligation de licence.

   Le résumé sous le titre (« 23 appareils, de 700 kg à 11 t ») est calculé
   depuis le fichier : rien n'y est écrit à la main.
   ========================================================================= */

import { el, monter, initTheme, initNav, deleguer, ouvrirModale } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { porteurs, creditsPhotos, libellesFiche } from './porteurs.js';
import { chiffre, texte, nombreFr } from './gamme.js';
import { installerEdition } from './edition.js';
import { abonnerModifications, supprimerElement } from './modifications.js';
import { ouvrirPorteur } from './edition-contenus.js';

initTheme();
initNav('porteurs.html');
installerEdition();

const bandeau = document.getElementById('bandeau-porteurs');
const resume = document.getElementById('porteurs-resume');
const tete = document.querySelector('.page-tete--porteurs');

/* « 23 appareils suivis par le service, de 700 kg à 11 tonnes. » */
function ecrireResume(donnees) {
  if (!resume) return;
  const flotte = (Array.isArray(donnees.flotte) ? donnees.flotte : []).filter((a) => a && texte(a.code));
  const masses = flotte.map((a) => chiffre(a, 'masseMaxDecollage')).filter((c) => c && c.ref).map((c) => c.ref);
  const t = (kg) => (kg >= 1000 ? nombreFr(kg / 1000, 1) + ' t' : nombreFr(kg, 0) + ' kg');
  resume.textContent = flotte.length + ' appareils suivis par le service'
    + (masses.length > 1 ? ', de ' + t(Math.min(...masses)) + ' à ' + t(Math.max(...masses)) + ' au décollage.' : '.');
}

function rendre(donnees, conteneur) {
  verifierForme(donnees, { flotte: 'tableau' }, 'flotte.json');
  ecrireResume(donnees);
  const libelles = libellesFiche();
  const avertissement = texte(donnees.avertissement);
  monter(conteneur,
    porteurs(donnees, {
      bandeau,
      /* Sur une fiche ou une comparaison, la une se fait discrète
         (modules.css) : l'appareil prend la scène. */
      surVue: (vue) => { if (tete) tete.dataset.vue = vue; },
      surAjouter: (b, categorie) => ouvrirPorteur({ flotte: donnees, libelles, declencheur: b, categorie }),
      surModifier: (appareil, b) => ouvrirPorteur({ existant: appareil, flotte: donnees, libelles, declencheur: b }),
      surSupprimer: (appareil) => supprimerElement('flotte', 'porteur', appareil.code)
    }),
    avertissement
      ? el('p', { class: 'porteurs__avertissement' }, el('span', { 'aria-hidden': 'true' }, '※ '), avertissement)
      : null);
}

function charger() {
  avecEtat('#zone-porteurs', () => chargerDonnees('flotte'), rendre, {
    squelette: 3,
    texteChargement: 'Chargement des porteurs…',
    titreErreur: 'Porteurs indisponibles',
    titreVide: 'Aucun porteur suivi',
    texteVide: 'Les appareils suivis par le service apparaîtront ici.',
    estVide: () => false
  });
}
charger();

/* Une modification enregistrée redessine la page : la vue ouverte (une
   fiche, une comparaison) se retrouve par l'adresse. */
abonnerModifications((jeu) => { if (jeu === 'flotte') charger(); });

deleguer(document, '[data-credits-photos]', 'click', async (evt, lien) => {
  evt.preventDefault();
  let flotte = null;
  try { flotte = await chargerDonnees('flotte'); } catch (_e) { flotte = null; }
  ouvrirModale({
    titre: 'Crédits photos',
    declencheur: lien,
    contenu: flotte
      ? creditsPhotos(flotte)
      : el('p', { class: 'texte-doux sans-marge' }, 'Les crédits des porteurs ne peuvent pas être lus pour le moment.')
  });
});

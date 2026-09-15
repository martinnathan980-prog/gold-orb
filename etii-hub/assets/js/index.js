/* =========================================================================
   ETII Hub — Module de la page d'accueil (SPEC.md §4.1)

   Trois responsabilités, et rien d'autre :

     1. Démarrer le thème et marquer la page courante dans la navigation.
     2. Neutraliser proprement les liens des trois pôles, dont les pages de
        destination n'existent pas encore.
     3. Alimenter l'aperçu vivant : les deux dernières annonces et le
        prochain point planifié.

   L'aperçu est un BONUS. Quelle que soit la raison d'un échec — fichier
   absent, JSON malformé, module de données indisponible — la page reste
   entièrement utilisable : titre, accès à la recherche, trois pôles,
   navigation et thème continuent de fonctionner.

   Tout le DOM produit ici passe par el() / frag() / monter() : le texte est
   inséré en textContent, jamais en innerHTML, et aucun gestionnaire n'est
   écrit en attribut HTML (SPEC §8).
   ========================================================================= */

import { el, monter, deleguer, annoncer, initTheme, initNav } from './ui.js';

/* -------------------------------------------------------------------------
   Constantes d'affichage
   ------------------------------------------------------------------------- */

/** Nombre d'annonces reprises dans l'aperçu. */
const ANNONCES_APERCU = 2;

/**
 * Correspondance entre le statut d'une annonce (communications.json) et le
 * vocabulaire visuel de components.css. Le libellé est toujours affiché :
 * le sens n'est jamais porté par la seule couleur.
 */
const STATUTS = {
  info:   { badge: 'badge--info',   carte: 'carte--statut-info',   libelle: 'Information' },
  urgent: { badge: 'badge--alerte', carte: 'carte--statut-alerte', libelle: 'Urgent' },
  succes: { badge: 'badge--succes', carte: 'carte--statut-succes', libelle: 'Validé' }
};

/* Repli si le JSON porte une valeur inattendue : l'annonce s'affiche quand
   même, sans liseré de statut — mieux vaut une carte neutre qu'une classe
   inventée qui n'existe dans aucune feuille de style. */
const STATUT_DEFAUT = { badge: 'badge--neutre', carte: null, libelle: 'Annonce' };

/* -------------------------------------------------------------------------
   1. Démarrage
   ------------------------------------------------------------------------- */

initTheme();
initNav('index');
neutraliserLiensPoles();
demarrerApercu();

/* -------------------------------------------------------------------------
   2. Liens de pôle inertes
   ------------------------------------------------------------------------- */

/**
 * Les trois cartes de pôle sont visuellement identiques aux autres cartes
 * cliquables, mais leur destination n'existe pas encore. Plutôt qu'un lien
 * mort qui renverrait en haut de page, on applique le motif standard du
 * lien désactivé : `aria-disabled="true"` posé dans le HTML (l'information
 * existe donc même sans JavaScript), activation neutralisée ici, et raison
 * annoncée aux lecteurs d'écran.
 *
 * Le lien reste focalisable : l'ordre de tabulation et le repère visuel
 * restent cohérents avec les cartes réellement actives.
 */
function neutraliserLiensPoles() {
  deleguer(document, 'a[aria-disabled="true"]', 'click', function (evt, cible) {
    evt.preventDefault();

    const pole = cible.getAttribute('data-pole') || '';
    annoncer(pole
      ? 'La page du pôle ' + pole + ' n’est pas encore raccordée.'
      : 'Cette page n’est pas encore raccordée.');
  });
}

/* -------------------------------------------------------------------------
   3. Aperçu vivant
   ------------------------------------------------------------------------- */

/**
 * Charge le module de données puis alimente les deux blocs d'aperçu.
 *
 * L'import est volontairement DYNAMIQUE et sous garde : un import statique
 * ferait échouer l'évaluation de tout ce module si data.js devenait
 * indisponible, et la page perdrait alors son thème et sa navigation pour
 * une simple section décorative. Ici, l'échec reste confiné à l'aperçu.
 */
async function demarrerApercu() {
  const blocAnnonces = document.getElementById('apercu-annonces');
  const blocReunion = document.getElementById('apercu-reunion');
  if (!blocAnnonces && !blocReunion) return;

  let donnees;
  try {
    donnees = await import('./data.js');
  } catch (cause) {
    console.error('[accueil] Module de données indisponible.', cause);
    etatSecours(blocAnnonces, 'Les dernières annonces ne sont pas '
      + 'consultables depuis l’accueil pour le moment.');
    etatSecours(blocReunion, 'Le prochain point n’est pas consultable '
      + 'depuis l’accueil pour le moment.');
    return;
  }

  const { chargerDonnees, avecEtat, verifierForme } = donnees;

  if (blocAnnonces) {
    avecEtat(
      blocAnnonces,
      /* Fabrique de promesse, et non promesse : le bouton « Réessayer » de
         l'état d'erreur peut ainsi relancer un vrai chargement. */
      () => chargerDonnees('communications').then((brut) => verifierForme(brut, {
        annonces: {
          type: 'tableau',
          elements: { id: 'chaine', date: 'chaine', titre: 'chaine' }
        }
      }, 'communications.json')),
      rendreAnnonces,
      {
        compact: true,
        squelette: ANNONCES_APERCU,
        texteChargement: 'Chargement des dernières annonces…',
        titreErreur: 'Annonces indisponibles',
        titreVide: 'Aucune annonce',
        texteVide: 'Aucune annonce n’a encore été publiée par le service.',
        estVide: (brut) => !brut || !Array.isArray(brut.annonces)
          || brut.annonces.length === 0
      }
    );
  }

  if (blocReunion) {
    avecEtat(
      blocReunion,
      () => chargerDonnees('reunions').then((brut) => verifierForme(brut, {
        prochainsPoints: {
          type: 'tableau',
          elements: { id: 'chaine', date: 'chaine', titre: 'chaine' }
        }
      }, 'reunions.json')),
      rendreProchainPoint,
      {
        compact: true,
        squelette: 1,
        texteChargement: 'Chargement du prochain point…',
        titreErreur: 'Réunions indisponibles',
        titreVide: 'Aucun point planifié',
        texteVide: 'Aucun point à venir n’est inscrit au calendrier du service.',
        estVide: (brut) => !brut || choisirProchainPoint(brut.prochainsPoints) === null
      }
    );
  }
}

/**
 * Repli affiché lorsque le module de données lui-même n'a pas pu être
 * chargé. Volontairement sobre : l'aperçu est un bonus, il ne doit pas
 * ressembler à une panne du site.
 *
 * @param {Element|null} conteneur
 * @param {string} texte
 */
function etatSecours(conteneur, texte) {
  if (!conteneur) return;

  monter(conteneur,
    el('div', { class: 'etat-vide etat-vide--encadre etat-vide--compact' },
      el('span', { class: 'etat-vide__illustration', 'aria-hidden': 'true' }, '∅'),
      el('p', { class: 'etat-vide__titre' }, 'Aperçu indisponible'),
      el('p', { class: 'etat-vide__texte' }, texte)
    )
  );
  conteneur.setAttribute('aria-busy', 'false');
}

/* -------------------------------------------------------------------------
   4. Rendu des annonces
   ------------------------------------------------------------------------- */

/**
 * Affiche les deux annonces les plus récentes.
 *
 * @param {object} donnees   contenu de communications.json
 * @param {Element} conteneur
 */
function rendreAnnonces(donnees, conteneur) {
  /* Tri décroissant sur la date ISO : la comparaison lexicographique suffit
     et reste déterministe, sans construire le moindre objet Date. `filter`
     ayant déjà produit un tableau neuf, le tri ne touche pas aux données
     d'origine, qui restent réutilisables par les autres pages via le cache. */
  const recentes = donnees.annonces
    .filter((annonce) => annonce && typeof annonce === 'object')
    .sort((a, b) => String(b.date).localeCompare(String(a.date)))
    .slice(0, ANNONCES_APERCU);

  monter(conteneur,
    el('ul', { class: 'pile pile--serree' },
      recentes.map((annonce) => el('li', null, carteAnnonce(annonce)))
    )
  );
}

/**
 * Une annonce, en carte compacte entièrement cliquable.
 *
 * @param {object} annonce
 * @returns {HTMLElement}
 */
function carteAnnonce(annonce) {
  const statut = STATUTS[annonce.statut] || STATUT_DEFAUT;

  return el('article', {
    class: ['carte', 'carte--compacte', 'carte--cliquable', statut.carte]
  },
    el('div', { class: 'carte__entete' },
      el('h4', { class: 'carte__titre' },
        el('a', {
          class: 'carte__lien',
          href: 'communication.html#' + encodeURIComponent(annonce.id)
        }, annonce.titre)
      ),
      el('span', { class: ['badge', statut.badge] },
        el('span', { class: 'badge__point', 'aria-hidden': 'true' }),
        statut.libelle
      )
    ),

    el('p', { class: 'carte__meta' },
      el('time', { datetime: annonce.date }, formaterDate(annonce.date)),
      annonce.categorie ? el('span', null, annonce.categorie) : null
    ),

    annonce.resume
      ? el('div', { class: 'carte__corps' }, el('p', null, annonce.resume))
      : null
  );
}

/* -------------------------------------------------------------------------
   5. Rendu du prochain point
   ------------------------------------------------------------------------- */

/**
 * Affiche le prochain point planifié.
 *
 * @param {object} donnees   contenu de reunions.json
 * @param {Element} conteneur
 */
function rendreProchainPoint(donnees, conteneur) {
  const point = choisirProchainPoint(donnees.prochainsPoints);
  if (!point) return;

  const sujets = Array.isArray(point.sujets) ? point.sujets.length : 0;
  const actions = Array.isArray(point.actions) ? point.actions.length : 0;

  monter(conteneur,
    el('article', {
      class: 'carte carte--compacte carte--cliquable carte--mise-en-avant'
    },
      el('div', { class: 'carte__entete' },
        el('h4', { class: 'carte__titre' },
          el('a', {
            class: 'carte__lien',
            href: 'reunions.html#' + encodeURIComponent(point.id)
          }, point.titre)
        )
      ),

      el('p', { class: 'carte__meta' },
        el('time', { datetime: point.date }, formaterDate(point.date)),
        point.lieu ? el('span', null, point.lieu) : null
      ),

      point.objectif
        ? el('div', { class: 'carte__corps' }, el('p', null, point.objectif))
        : null,

      (sujets || actions)
        ? el('p', { class: 'carte__pied' },
            sujets ? el('span', null, compter(sujets, 'sujet')) : null,
            actions ? el('span', null, compter(actions, 'action')) : null
          )
        : null
    )
  );
}

/**
 * Choisit le point à venir le plus proche. Le classement est fait sur la
 * date ISO, donc stable et déterministe : à date égale, l'ordre du fichier
 * départage — mais deux points ne partagent jamais la même position dans
 * l'aperçu, qui n'en montre qu'un.
 *
 * @param {*} points  contenu attendu de `prochainsPoints`
 * @returns {object|null} le point le plus proche, ou null s'il n'y en a pas
 */
function choisirProchainPoint(points) {
  if (!Array.isArray(points)) return null;

  const aujourdHui = isoDuJour();

  const aVenir = points
    .filter((point) => point && typeof point === 'object'
      && typeof point.date === 'string' && point.date >= aujourdHui)
    .sort((a, b) => a.date.localeCompare(b.date));

  return aVenir.length > 0 ? aVenir[0] : null;
}

/* -------------------------------------------------------------------------
   6. Petits utilitaires de présentation
   ------------------------------------------------------------------------- */

/** Formateur de date en français, construit une seule fois. */
const FORMAT_DATE = (function () {
  try {
    return new Intl.DateTimeFormat('fr-FR', {
      day: 'numeric', month: 'long', year: 'numeric'
    });
  } catch (_e) {
    return null;   // moteur sans Intl : on retombera sur la date brute
  }
})();

/**
 * Met une date ISO en forme lisible. En cas de doute, la valeur d'origine
 * est rendue telle quelle : mieux vaut une date brute qu'un « Invalid Date ».
 *
 * @param {string} iso  par exemple '2026-09-24'
 * @returns {string}
 */
function formaterDate(iso) {
  if (typeof iso !== 'string' || iso === '') return '';
  if (!FORMAT_DATE) return iso;

  /* Heure explicite : sans elle, une date seule est interprétée en UTC et
     peut reculer d'un jour selon le fuseau de la personne. */
  const date = new Date(iso + 'T12:00:00');
  if (Number.isNaN(date.getTime())) return iso;

  try {
    return FORMAT_DATE.format(date);
  } catch (_e) {
    return iso;
  }
}

/**
 * Date du jour au format ISO, dans le fuseau local — et non en UTC, pour
 * que « à venir » corresponde à la journée réellement vécue.
 *
 * @returns {string} 'AAAA-MM-JJ'
 */
function isoDuJour() {
  const maintenant = new Date();
  const deuxChiffres = (valeur) => String(valeur).padStart(2, '0');

  return maintenant.getFullYear()
    + '-' + deuxChiffres(maintenant.getMonth() + 1)
    + '-' + deuxChiffres(maintenant.getDate());
}

/**
 * Accorde un décompte en français.
 *
 * @param {number} nombre
 * @param {string} nom  nom au singulier
 * @returns {string} par exemple '2 sujets'
 */
function compter(nombre, nom) {
  return nombre + ' ' + nom + (nombre > 1 ? 's' : '');
}

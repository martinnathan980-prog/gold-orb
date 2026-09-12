/**
 * NEXUS PLM — configuration serveur.
 * Tout ce qui était en dur et dispersé dans le code est regroupé ici.
 */

const CFG = {
  FEUILLES: {
    BOITES: '1_BOITES',
    NOMENCLATURE: '2_NOMENCLATURE',
    JOURNAL: '9_JOURNAL'
  },

  // Colonnes référencées par le code. Le reste des colonnes est traité
  // génériquement : en ajouter une dans le Sheet suffit à la faire apparaître.
  COL: {
    PN: 'PN Global',
    FONCTION: 'Fonction',
    STATUT: 'Statut',
    DS_VCI: 'DS/VCI Associé',
    PORTEUR: 'Porteur',
    NOM_ID: 'ID_Ligne',
    NOM_TYPE: 'Type',
    NOM_PN_TYPE: 'PN du type',
    NOM_STD: 'Composant STD'
  },

  EN_TETES: {
    BOITES: ['Fonction', 'PN Global', 'DS/VCI Associé', 'Porteur', 'Statut',
             'Niveau de qualification', 'Image', 'Commentaires libres'],
    // Superset de toutes les colonnes, tous types confondus : la feuille reste
    // lisible à l'oeil, et chaque type n'utilise que les siennes (voir
    // client/Types.html, qui pilote l'affichage et l'équivalence).
    NOMENCLATURE: ['ID_Ligne', 'PN Global', 'Type', 'PN du type',
                   'Référence', 'Numéro', 'Mots-clés',
                   'Montage', 'Nombre de pas', 'Dim Long (mm)', 'Dim Larg (mm)',
                   'Masse (g)', 'HL', 'DAL',
                   'Qualification Brouillard salin', 'Qualification Vibration',
                   'Qualification Explosion',
                   'Composant STD', 'Image', 'Commentaires libres'],
    JOURNAL: ['Horodatage', 'Utilisateur', 'Action', 'Cible', 'Détail']
  },

  // Champs à valeurs multiples (rendus sous forme de puces).
  MULTI_BOITE: ['Porteur'],
  MULTI_NOM: ['Qualification Brouillard salin', 'Qualification Vibration',
              'Qualification Explosion', 'Mots-clés'],

  // Types connus. Le libellé écrit dans la feuille ; le client reconnaît
  // aussi les variantes courantes (accents, synonymes).
  TYPES: ['Structure boîte', 'Harnais', 'Plaquette éclairante', 'Autre sous-ensemble'],

  // Colonnes non éditables depuis la fiche.
  LECTURE_SEULE_NOM: ['ID_Ligne', 'PN Global'],

  STATUTS: ['En étude', 'Validé', 'Obsolète'],
  STATUT_DEFAUT: 'En étude',

  CACHE_CATALOGUE_S: 600,   // 10 min
  VERROU_MS: 20000,         // attente max sur LockService
  JOURNAL_MAX_LIGNES: 5000
};

/** URL du catalogue : en Script Property, plus en dur dans le source. */
function urlCatalogue_() {
  const url = PropertiesService.getScriptProperties().getProperty('URL_CATALOGUE');
  if (!url) {
    throw new Error(
      "Catalogue non configuré. Dans l'éditeur : Paramètres du projet > " +
      "Propriétés du script > ajouter URL_CATALOGUE avec l'URL du classeur catalogue.");
  }
  return url;
}

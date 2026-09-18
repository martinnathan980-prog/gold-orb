/* La structure exacte de l'export GATES, relevée sur le fichier réel
   (export_48.xlsx) : 138 colonnes, en-tête en ligne 2, une ligne de groupes
   faite de seize plages fusionnées et de deux cellules isolées, trois colonnes
   sans intitulé, et treize répétitions du même bloc de sept colonnes — une par
   variante HDK AA. Vingt-sept colonnes ont un intitulé contenant
   « avancement » ; une seule est celle du FWD. */

const ENTETES = ["", "Référence UD", "RPT", "", "", "Propa.", "Libellé", "Domaine", "Type", "Date création", "Nom Installation", "Chapitre", "Sous-chapitre", "Etape", "Produit", "Raison de la création", "Commentaire", "Version", "Groupage", "Installation GATES", "Désignation GATES", "Type", "BTE/BTR/CDR/PLT", "PWD", "CC", "ATA", "Séquence", "Commentaire", "ECP", "Statut iBG", "RPTs liés", "Validation Définition Electrique", "XPWD", "DDI", "Logiciel Archivage", "Eclairage", "Patchboard", "Tableau d'alarmes", "Panier à cartes 16WW", "Commentaire", "GEOMETRICAL HARNESS", "Avancement", "Date de départ", "Date de retour", "Redraw", "Classif. SAP (BETA)", "Classif. calculée (BETA)", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais", "Validité", "Quantité", "Configuration officielle", "Avancement Définition Electrique", "A traiter par", "Commentaire", "Avancement Concept Harnais"];

/* Ligne 1 : { col (1-based), larg, texte }. Les deux « Concept Harnais » ne
   sont pas fusionnés — ce sont deux cellules isolées, et le code doit les
   traiter comme telles. */
const GROUPES_FUSIONNES = [{"col": 2, "larg": 16, "texte": "Informations principales"}, {"col": 18, "larg": 22, "texte": "Définition du plan"}, {"col": 42, "larg": 4, "texte": "Réalisation FWD"}, {"col": 48, "larg": 7, "texte": "HDK AA"}, {"col": 55, "larg": 7, "texte": "HDK AA 011"}, {"col": 62, "larg": 7, "texte": "HDK AA 012"}, {"col": 69, "larg": 7, "texte": "HDK AA 002"}, {"col": 76, "larg": 7, "texte": "HDK AA 001"}, {"col": 83, "larg": 7, "texte": "HDK AA 004"}, {"col": 90, "larg": 7, "texte": "HDK AA 006"}, {"col": 97, "larg": 7, "texte": "HDK AA 010"}, {"col": 104, "larg": 7, "texte": "HDK AA 005"}, {"col": 111, "larg": 7, "texte": "HDK AA 003"}, {"col": 118, "larg": 7, "texte": "HDK AA 007"}, {"col": 125, "larg": 7, "texte": "HDK AA 008"}, {"col": 132, "larg": 7, "texte": "HDK AA 009"}];
const GROUPES_SEULS = [{"col": 40, "texte": "Concept Harnais"}, {"col": 41, "texte": "Concept Harnais"}];

const NB = ENTETES.length;

/** Indices 0-based de quelques colonnes repères, retrouvées par leur intitulé. */
function colonne(titre, groupe) {
  for (let i = 0; i < NB; i++) {
    if (ENTETES[i] !== titre) continue;
    if (groupe === undefined || groupeDe(i) === groupe) return i;
  }
  return -1;
}

function groupeDe(i) {
  for (let k = 0; k < GROUPES_FUSIONNES.length; k++) {
    const f = GROUPES_FUSIONNES[k];
    if (i + 1 >= f.col && i + 1 < f.col + f.larg) return f.texte;
  }
  for (let k = 0; k < GROUPES_SEULS.length; k++) {
    if (GROUPES_SEULS[k].col === i + 1) return GROUPES_SEULS[k].texte;
  }
  return '';
}

/** La ligne de groupes telle que getDisplayValues la renvoie : une fusion ne
    porte son texte que dans sa première cellule. */
function ligneGroupes() {
  const l = new Array(NB).fill('');
  GROUPES_FUSIONNES.forEach(function (f) { l[f.col - 1] = f.texte; });
  GROUPES_SEULS.forEach(function (s) { l[s.col - 1] = s.texte; });
  return l;
}

/** Les plages fusionnées à déclarer au faux classeur. */
function fusions() {
  return GROUPES_FUSIONNES.map(function (f) { return { ligne: 1, col: f.col, larg: f.larg }; });
}

/**
 * Une feuille plausible : mêmes colonnes, mêmes groupes, mêmes types de
 * valeurs que l'export (booléens en toutes lettres, dates ISO avec heure,
 * avancements de toutes les formes), plus une ligne de service sans référence.
 */
function feuilleGates(nbLignes) {
  const n = nbLignes || 186;
  const vide = function () { return new Array(NB).fill(''); };
  const valeurs = [ligneGroupes(), ENTETES.slice()];

  const parasite = vide();
  parasite[3] = 'Modification de design en cours';   // ligne sans référence
  valeurs.push(parasite);

  const iRef   = colonne('Référence UD');
  const iDate  = colonne('Date création');
  const iAta   = colonne('ATA');
  const iSeq   = colonne('Séquence');
  const iEtape = colonne('Etape');
  const iProd  = colonne('Produit');
  const iDom   = colonne('Domaine');
  const iChap  = colonne('Chapitre');
  const iSChap = colonne('Sous-chapitre');
  const iGrp   = colonne('Groupage');
  const iIBG   = colonne('Statut iBG');
  const iVDE   = colonne('Validation Définition Electrique');
  const iFWD   = colonne('Avancement', 'Réalisation FWD');
  const iRedr  = colonne('Redraw', 'Réalisation FWD');
  const iLib   = colonne('Libellé');
  const iNom   = colonne('Nom Installation');
  const iECP   = colonne('ECP');
  const iComm  = colonne('Commentaire', 'Informations principales');

  const ATA = ['21', '24', '25', '31', '33', '34', '39', '46', '53', '92'];
  const AVANCE = ['100%', '100 %', 'Terminé', '75 %', '50%', '30%', 'En cours',
                  'À faire', 'à faire', '', '', '-'];
  let graine = 20260918;
  function alea() { graine = (graine * 1103515245 + 12345) % 2147483648; return graine / 2147483648; }
  function tire(l) { return l[Math.floor(alea() * l.length)]; }

  for (let i = 0; i < n; i++) {
    const l = vide();
    const ata = tire(ATA);
    l[iRef]   = 'UD-' + ata + '-' + String(1000 + i * 7).slice(-4);
    /* `getDisplayValues()` rend ce que la cellule MONTRE : sur une feuille
       francaise, une date s'ecrit jour d'abord. Le jeu d'exemple de la page,
       lui, la donne en ISO — les deux ordres sont donc couverts. */
    l[iDate]  = String(1 + Math.floor(alea() * 27)).padStart(2, '0') + '/' +
                String(1 + Math.floor(alea() * 12)).padStart(2, '0') + '/' +
                (2017 + Math.floor(alea() * 9));
    l[iAta]   = ata;
    l[iSeq]   = 'S' + (1 + Math.floor(alea() * 5));
    l[iEtape] = tire(['AVAILABLE', 'IN WORK', 'FROZEN']);
    l[iProd]  = tire(['SUPER PUMA', 'MK2', 'MK3']);
    l[iDom]   = tire(['BASE/OPTION', 'BASE/OPTION', 'PERSO']);
    l[iChap]  = tire(['A', 'B', 'C', 'D']);
    l[iSChap] = tire(['A1', 'A2', 'B1', 'B2', 'C1']);
    l[iGrp]   = tire(['G1', 'G2', 'G3']);
    l[iIBG]   = tire(['true', 'false']);
    l[iVDE]   = tire(['true', 'false']);
    l[iRedr]  = tire(['true', 'false']);
    l[iFWD]   = tire(AVANCE);
    l[iLib]   = 'Faisceau ' + (i + 1) + ' — cheminement complet vers la console centrale';
    l[iNom]   = 'Installation ' + (i + 1);
    l[iECP]   = alea() < 0.85 ? 'ECP-' + (2100 + Math.floor(alea() * 800)) : '';
    l[iComm]  = alea() < 0.2 ? 'Voir note interne' : '';
    /* Les colonnes sans intitulé : la première (col. 1) est vide de bout en
       bout — la page la retire ; les deux autres (col. 4 et 5) portent des
       marques éparses — elles restent. Moins d'une ligne sur deux, pour que
       la détection automatique n'en fasse jamais une dimension. */
    l[3] = i % 3 === 0 ? 'X' : (i % 6 === 1 ? 'O' : '');
    l[4] = i % 4 === 1 ? 'Voir RPT' : (i % 8 === 3 ? 'Voir ECP' : '');
    // Les treize blocs répétés : mêmes intitulés partout, valeurs sans rapport.
    GROUPES_FUSIONNES.filter(function (f) { return f.texte.indexOf('HDK AA') === 0; })
      .forEach(function (f) {
        const b = f.col - 1;
        l[b]     = tire(['V', 'NV', '-']);
        l[b + 1] = tire(['1', '-']);
        l[b + 2] = tire(['1', 'EMPTY', '-']);
        l[b + 3] = tire(['EMPTY', '100%', '-']);   // Avancement Définition Electrique
        l[b + 4] = tire(['()', 'MR', '-']);        // A traiter par
        l[b + 5] = tire(['V', '-']);
        l[b + 6] = tire(['EMPTY', 'V', '-']);      // Avancement Concept Harnais
      });
    valeurs.push(l);
  }
  return { valeurs: valeurs, fusions: fusions(), nbColonnes: NB };
}

module.exports = { feuilleGates, entetes: function () { return ENTETES.slice(); },
                   groupeDe: groupeDe, colonne: colonne, NB: NB };

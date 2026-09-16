/* La vraie structure d'export GATES : 137 colonnes, dont 91 sont 13 répétitions
   du même bloc de 7 (une par variante HDK AA), une ligne de groupes fusionnés,
   une ligne parasite entre l'en-tête et les données, et 27 colonnes dont
   l'intitulé contient « avancement » alors qu'une seule est celle du FWD. */

const BLOC_HDK = ['Validité', 'Quantité', 'Configuration officielle',
                  'Avancement Définition Electrique', 'A traiter par', 'Commentaire',
                  'Avancement Concept Harnais'];

const VARIANTES = ['HDK AA', 'HDK AA 011', 'HDK AA 012', 'HDK AA 002', 'HDK AA 001',
                   'HDK AA 004', 'HDK AA 006', 'HDK AA 010', 'HDK AA 005', 'HDK AA 003',
                   'HDK AA 007', 'HDK AA 008', 'HDK AA 009'];

const TETE = [
  'Référence UD', 'RPT', '', '', 'Propa.', 'Libellé', 'Domaine', 'Type', 'Date création',
  'Nom Installation', 'Chapitre', 'Sous-chapitre', 'Etape', 'Produit', 'Raison de la création',
  'Commentaire', 'Version', 'Groupage', 'Installation GATES', 'Désignation GATES', 'Type',
  'BTE/BTR/CDR/PLT', 'PWD', 'CC', 'ATA', 'Séquence', 'Commentaire', 'ECP', 'Statut iBG',
  'RPTs liés', 'Validation Définition Electrique', 'XPWD', 'DDI', 'Logiciel Archivage',
  'Eclairage', 'Patchboard', 'Tableau d\'alarmes', 'Panier à cartes 16WW', 'Commentaire',
  'GEOMETRICAL HARNESS', 'Avancement', 'Date de départ', 'Date de retour', 'Redraw',
  'Classif. SAP (BETA)', 'Classif. calculée (BETA)'
];

/* Les fusions de la ligne de groupes, telles qu'elles existent dans la feuille :
   {colonne de départ (1-based), largeur, libellé}. */
const FUSIONS = [
  { col: 1,  larg: 20, texte: 'Informations principales' },
  { col: 21, larg: 10, texte: 'Définition du plan' },
  { col: 31, larg: 5,  texte: 'Concept Harnais' },
  { col: 36, larg: 5,  texte: 'Concept Harnais' },
  { col: 41, larg: 4,  texte: 'Réalisation FWD' }
  // 45 et 46 hors groupe ; à partir de 47, un groupe par variante (ci-dessous)
];
VARIANTES.forEach(function (v, k) {
  FUSIONS.push({ col: 47 + k * 7, larg: 7, texte: v });
});

function entetes() {
  let h = TETE.slice();
  VARIANTES.forEach(function () { h = h.concat(BLOC_HDK); });
  return h;
}

/** La ligne de groupes telle que getDisplayValues la renvoie : seule la première
    cellule d'une fusion porte le texte, les suivantes sont vides. */
function ligneGroupes(nbColonnes) {
  const l = new Array(nbColonnes).fill('');
  FUSIONS.forEach(function (f) { l[f.col - 1] = f.texte; });
  return l;
}

function feuilleGates(nbLignes) {
  const n = nbLignes || 186;
  const h = entetes();
  const nb = h.length;
  const vide = function () { return new Array(nb).fill(''); };

  const titre = vide(); titre[0] = 'Export GATES — Programme H225';
  const groupes = ligneGroupes(nb);
  const parasite = vide(); parasite[3] = 'xxxx';   // ligne polluée sous l'en-tête

  const valeurs = [titre, groupes, h, parasite];

  const ATA = ['21', '24', '25', '31', '33', '34', '39', '46', '53', '92'];
  const AVANCE = ['100%', '100 %', 'Terminé', '75 %', '50%', '30%', 'En cours',
                  'À faire', 'à faire', '', '', '-'];
  let graine = 20260917;
  function alea() { graine = (graine * 1103515245 + 12345) % 2147483648; return graine / 2147483648; }
  function tire(l) { return l[Math.floor(alea() * l.length)]; }

  for (let i = 0; i < n; i++) {
    const l = vide();
    const ata = tire(ATA);
    l[0]  = 'UD-' + ata + '-' + String(1000 + i * 7).slice(-4);   // Référence UD
    l[1]  = tire(['TRUE', 'FALSE']);                              // RPT
    l[4]  = tire(['BASE/OPTION', 'BASE', 'OPTION']);              // Propa.
    l[5]  = 'Faisceau ' + (i + 1) + ' — cheminement complet vers la console centrale'; // Libellé
    l[6]  = 'ELEC';                                               // Domaine
    l[7]  = tire(['STD', 'SPEC', 'TEST']);                        // Type
    l[8]  = '2026-' + String(1 + Math.floor(alea() * 8)).padStart(2, '0') +
            '-' + String(1 + Math.floor(alea() * 27)).padStart(2, '0');  // Date création
    l[9]  = 'Installation ' + (i + 1);                            // Nom Installation
    l[10] = tire(['A', 'B', 'C', 'D']);                           // Chapitre
    l[11] = tire(['A1', 'A2', 'B1', 'B2', 'C1']);                 // Sous-chapitre
    l[12] = tire(['AVAILABLE', 'IN WORK', 'FROZEN']);             // Etape
    l[13] = tire(['MK2', 'MK3']);                                 // Produit
    l[14] = 'Création suite à évolution de définition';           // Raison de la création
    l[15] = alea() < 0.2 ? 'Voir note interne' : '';              // Commentaire
    l[16] = String(1 + Math.floor(alea() * 4));                   // Version
    l[17] = tire(['G1', 'G2', 'G3']);                             // Groupage
    l[18] = 'GATES-' + (5000 + i);                                // Installation GATES
    l[19] = 'Désignation longue du plan numéro ' + (i + 1);       // Désignation GATES
    l[20] = tire(['PM', 'PS']);                                   // Type (2)
    l[21] = tire(['BTE', 'BTR', 'CDR', 'PLT']);                   // BTE/BTR/CDR/PLT
    l[22] = String(600 + Math.floor(alea() * 3));                 // PWD
    l[23] = String(30000 + Math.floor(alea() * 2000));            // CC
    l[24] = ata;                                                  // ATA
    l[25] = 'S' + (1 + Math.floor(alea() * 5));                   // Séquence
    l[26] = '';                                                   // Commentaire (2)
    l[27] = alea() < 0.85 ? 'ECP-' + (2100 + Math.floor(alea() * 800)) : '';  // ECP
    l[28] = tire(['Validé', 'En revue', 'Non lancé', 'À contrôler']);         // Statut iBG
    l[29] = alea() < 0.3 ? 'RPT-' + (100 + i) : '';               // RPTs liés
    l[30] = tire(['Validée', 'En attente', 'Sans objet']);        // Validation Définition Electrique
    l[31] = tire(['XPWD1', 'XPWD2']);                             // XPWD
    l[32] = tire(['DDI-A', 'DDI-B']);                             // DDI
    l[33] = tire(['Oui', 'Non']);                                 // Logiciel Archivage
    l[40] = tire(AVANCE);                                         // Avancement  ← LE FWD
    l[41] = alea() < 0.5 ? '2026-06-01' : '';                     // Date de départ
    l[42] = alea() < 0.3 ? '2026-07-15' : '';                     // Date de retour
    l[43] = tire(['TRUE', 'FALSE']);                              // Redraw
    // Les 13 blocs HDK AA : mêmes intitulés, valeurs sans rapport avec le FWD.
    for (let b = 0; b < VARIANTES.length; b++) {
      const base = 46 + b * 7;
      l[base]     = tire(['V', 'NV']);
      l[base + 1] = '1';
      l[base + 2] = tire(['EMPTY', '()']);
      l[base + 3] = tire(['100%', '0%', '']);       // Avancement Définition Electrique
      l[base + 4] = tire(['MR', 'AB', 'CM']);       // A traiter par
      l[base + 5] = '';
      l[base + 6] = tire(['V', 'EMPTY']);           // Avancement Concept Harnais
    }
    valeurs.push(l);
  }
  return { valeurs: valeurs, fusions: FUSIONS, nbColonnes: nb };
}

module.exports = { feuilleGates, entetes, FUSIONS, VARIANTES, BLOC_HDK };

/* Une feuille délibérément pénible, proche d'un vrai export GATES :
   lignes de titre au-dessus, ligne de groupes fusionnés, en-têtes accentués,
   lignes vides au milieu, valeurs d'avancement de toutes les formes. */
function feuilleExemple(nbLignes) {
  const n = nbLignes || 186;
  const entetes = ['Référence UD', 'Nom installation', 'ATA', 'Séquence', 'ECP',
                   'Validation définition électrique', 'Statut IBG', 'Date création',
                   'Avancement FWD', 'Resp.', 'Commentaire'];
  const groupes = ['Informations principales', '', '', '',
                   'Définition du plan', '', '', '',
                   'FWD', '', ''];

  const valeurs = [
    ['Export GATES — Programme 225', '', '', '', '', '', '', '', '', '', ''],
    ['Généré le 16/09/2026', '', '', '', '', '', '', '', '', '', ''],
    groupes,
    entetes
  ];

  const ATA = ['24', '25', '31', '33', '34', '39', '53', '92'];
  const INSTALL = ['Harnais alimentation cabine', 'Cheminement plancher avant',
                   'Boîtier de disjoncteurs', 'Éclairage de soute', 'Bâti convertisseur statique',
                   'Faisceau treuil de sauvetage', 'Antenne VHF dorsale', 'Câblage siège pilote'];
  const AVANCE = ['100%', '100 %', 'Terminé', '50%', '75 %', '20%', 'En cours',
                  'À faire', 'à faire', '', '', '-'];

  let graine = 20260916;
  function alea() { graine = (graine * 1103515245 + 12345) % 2147483648; return graine / 2147483648; }
  function tire(l) { return l[Math.floor(alea() * l.length)]; }

  for (let i = 0; i < n; i++) {
    if (i === 40) { valeurs.push(['', '', '', '', '', '', '', '', '', '', '']); }  // trou au milieu
    const ata = tire(ATA);
    valeurs.push([
      'UD-' + ata + '-' + String(1000 + i * 7).slice(-4),
      tire(INSTALL),
      ata,
      tire(['S1', 'S2', 'S3', 'S4']),
      alea() < 0.85 ? 'ECP-' + (2100 + Math.floor(alea() * 800)) : '',
      tire(['Validée', 'En attente', 'Sans objet']),
      tire(['Validé', 'En revue', 'Non lancé', 'À contrôler']),
      '2026-' + String(1 + Math.floor(alea() * 8)).padStart(2, '0') + '-' + String(1 + Math.floor(alea() * 27)).padStart(2, '0'),
      tire(AVANCE),
      tire(['MR', 'AB', 'CM', 'TL']),
      alea() < 0.25 ? 'Attente d’accès & <validation> </script> <!-- ' : ''
    ]);
  }
  return valeurs;
}
module.exports = { feuilleExemple };

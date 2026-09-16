/**
 * NEXUS PLM — initialisation et maintenance.
 *
 * L'ancienne initialiserBaseDeDonnees() faisait sheet.clear() puis réinjectait
 * le jeu de démo SANS AUCUNE CONFIRMATION : un lancement accidentel depuis
 * l'éditeur effaçait tout. Elle est désormais scindée en deux :
 *   - creerStructureSiAbsente()  : sûre, ne touche à aucune donnée existante ;
 *   - reinitialiserAvecDemo()    : destructive, exige une confirmation écrite.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('NEXUS PLM')
    .addItem('Créer / compléter la structure', 'creerStructureSiAbsente')
    .addSeparator()
    .addItem('Réinitialiser avec le jeu de démo…', 'demanderReinitialisation')
    .addToUi();
}

/** Crée les feuilles et en-têtes manquants. Ne supprime jamais de données. */
function creerStructureSiAbsente() {
  const ss = classeur_();
  [[CFG.FEUILLES.BOITES, CFG.EN_TETES.BOITES],
   [CFG.FEUILLES.NOMENCLATURE, CFG.EN_TETES.NOMENCLATURE],
   [CFG.FEUILLES.JOURNAL, CFG.EN_TETES.JOURNAL]].forEach(function (paire) {
    const nom = paire[0], enTetes = paire[1];
    let f = ss.getSheetByName(nom);
    if (!f) {
      f = ss.insertSheet(nom);
      f.getRange(1, 1, 1, enTetes.length).setValues([enTetes]);
      habillerEnTete_(f, enTetes.length);
    } else {
      // Complète les colonnes absentes sans toucher aux colonnes existantes.
      const actuels = f.getRange(1, 1, 1, Math.max(1, f.getLastColumn())).getValues()[0]
                       .map(function (h) { return String(h).trim(); });
      const manquants = enTetes.filter(function (h) { return actuels.indexOf(h) === -1; });
      if (manquants.length) {
        f.getRange(1, actuels.filter(String).length + 1, 1, manquants.length)
         .setValues([manquants]);
      }
    }
  });
  SpreadsheetApp.getActiveSpreadsheet().toast('Structure vérifiée.', 'NEXUS PLM');
}

function habillerEnTete_(f, nbCol) {
  const enTete = f.getRange(1, 1, 1, nbCol);
  enTete.setFontWeight('bold').setFontColor('#ffffff').setBackground('#0f172a')
        .setHorizontalAlignment('center').setVerticalAlignment('middle');
  f.setFrozenRows(1);
  // Bornage sur le nombre de lignes réel : setRowHeights lève au-delà.
  const nbLignes = Math.max(1, f.getMaxRows() - 1);
  f.getRange(2, 1, nbLignes, nbCol)
   .setHorizontalAlignment('center').setVerticalAlignment('middle')
   .setWrapStrategy(SpreadsheetApp.WrapStrategy.CLIP);
  f.setRowHeights(2, nbLignes, 35);
  for (let i = 1; i <= nbCol; i++) f.setColumnWidth(i, 150);
  // applyRowBanding lève si la plage est déjà bandée : on retire l'existant.
  f.getBandings().forEach(function (b) { b.remove(); });
  f.getRange(1, 1, Math.min(f.getMaxRows(), Math.max(100, f.getLastRow())), nbCol)
   .applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY);
}

function demanderReinitialisation() {
  const ui = SpreadsheetApp.getUi();
  const reponse = ui.prompt(
    'Réinitialisation complète',
    'Cette action EFFACE toutes les boîtes et toute la nomenclature, puis ' +
    'réinstalle le jeu de démonstration.\n\nTapez EFFACER pour confirmer :',
    ui.ButtonSet.OK_CANCEL);

  if (reponse.getSelectedButton() !== ui.Button.OK) return;
  if (reponse.getResponseText().trim().toUpperCase() !== 'EFFACER') {
    ui.alert('Confirmation incorrecte : rien n\'a été modifié.');
    return;
  }
  reinitialiserAvecDemo();
  ui.alert('Base réinitialisée avec le jeu de démonstration.');
}

function reinitialiserAvecDemo() {
  const ss = classeur_();
  journaliser_('REINITIALISATION', '(base entière)', 'jeu de démo réinstallé');

  [[CFG.FEUILLES.BOITES, CFG.EN_TETES.BOITES],
   [CFG.FEUILLES.NOMENCLATURE, CFG.EN_TETES.NOMENCLATURE]].forEach(function (paire) {
    const nom = paire[0], enTetes = paire[1];
    let f = ss.getSheetByName(nom);
    if (!f) f = ss.insertSheet(nom);
    else { f.getBandings().forEach(function (b) { b.remove(); }); f.clear(); f.clearFormats(); }
    f.getRange(1, 1, 1, enTetes.length).setValues([enTetes]);
    habillerEnTete_(f, enTetes.length);
  });

  // Colonnes boîte : Fonction, PN Global, DS/VCI, Porteur, Statut, Niveau,
  //                  Composants (Fonction | Norme | Référence), Image, Commentaires
  const boites = [
    ['APU',     '332P20001',   '332P20051',   'H225',        'Validé',   'Qualified to H225', 'Bouton poussoir | ECS 7251 | MS24523-22\nBouton poussoir | ECS 0763 | MS24523-31\nVoyant | ECS 4410 | LED-G-28', '', ''],
    ['EOS',     '332P94101',   '332P94051',   'H225\nH215',  'En étude', 'Qualified to H225', 'Interrupteur | ASNE 0567 | 8500K12\nVoyant | ECS 4411 | LED-R-28', '', ''],
    ['APU',     'U880A240101', 'U880A240051', 'H160',        'Obsolète', 'Qualified to H160', 'Bouton poussoir | ECS 7251 | MS24523-22\nVoyant | ECS 4410 | LED-G-05', '', ''],
    ['NAV',     '332N10001',   '332N10051',   'H225',        'Validé',   'Qualified to H225', 'Relais | ECS 1120 | RLY-28-2C\nInterrupteur | ASNE 0571 | TGL-2P', '', ''],
    ['COM',     '332C50001',   '332C50051',   'H145\nH145M', 'En étude', 'Qualified to H160', 'Bouton poussoir | ECS 0780 | MS24523-40\nBouton poussoir | ECS 7251 | MS24523-22', '', ''],
    ['RADAR',   'U880R30001',  'U880R30051',  'H160',        'Validé',   'Qualified to H160', 'Voyant | ECS 4410 | LED-G-28\nFusible | NSA 9350 | F5A', '', ''],
    ['FLIGHT',  '332F40001',   '332F40051',   'H225',        'Validé',   'Qualified to H225', 'Interrupteur | ASNE 0567 | 8500K12\nBouton poussoir | ECS 7251 | MS24523-22', '', ''],
    ['POWER',   'U880P50001',  'U880P50051',  'H160\nH160M', 'En étude', 'Qualified to H160', 'Double commande | FRF 772-034 | DC-IG-2\nFusible | NSA 9350 | F5A', '', ''],
    ['SENSOR',  '332S60001',   '332S60051',   'H175',        'Obsolète', 'Qualified to H225', 'Voyant | ECS 4411 | LED-R-05', '', ''],
    ['DISPLAY', 'U880D70001',  'U880D70051',  'H160',        'Validé',   'Qualified to H160', 'Bouton poussoir | ECS 7251 | MS24523-22\nVoyant | ECS 4410 | LED-G-28\nRelais | ECS 1120 | RLY-28-2C', '', '']
  ];
  ss.getSheetByName(CFG.FEUILLES.BOITES)
    .getRange(2, 1, boites.length, boites[0].length).setValues(boites);

  // Colonnes nomenclature : PN Global, Type, PN du type, Référence, Mots-clés,
  //   Montage, Nb pas, Long, Larg, Masse, HL, DAL, 3 qualifications,
  //   Composants mécaniques, Composants routing, Image, Commentaires
  const nom = [
    ['332P20001',   'Structure boîte',      '332P20001.01',   '', '', 'Console STD',  '1', '500', '140', '500',  'A', 'A', 'Cat. S', 'Qual. H225', 'Case 1', 'Colonnette | NSA 5512 | COL-M4-20\nÉquerre | EN 2491 | EQ-90-A', 'Collier | NSA 8420 | CT-120\nEmbase | ECS 2210 | EMB-4', '', ''],
    ['332P20001',   'Harnais',              '332P20001.03',   'HRN-2251-A', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332P20001',   'Plaquette éclairante', '332P20001.05',   '', 'APU, démarrage, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332P94101',   'Structure boîte',      '332P94101.01',   '', '', 'Hors console', '5', '400', '200', '400',  'B', 'C', 'Cat. T', 'Qual. H225', '', 'Colonnette | NSA 5512 | COL-M4-30\nInsert | NSA 5591 | INS-M4', 'Collier | NSA 8420 | CT-120\nPasse-fil | ECS 2230 | PF-8', '', ''],
    ['332P94101',   'Plaquette éclairante', '332P94101.02',   '', 'EOS, optronique, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880A240101', 'Harnais',              'U880A240401',    'HRN-1601-C', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880A240101', 'Structure boîte',      'U880A240101.01', '', '', 'Console STD',  '2', '480', '140', '520',  'A', 'A', 'Cat. S', 'Qual. H160', 'Case 1', 'Colonnette | NSA 5512 | COL-M4-20\nÉquerre | EN 2491 | EQ-90-B', 'Collier | NSA 8420 | CT-120\nEmbase | ECS 2210 | EMB-4', '', ''],
    ['332N10001',   'Structure boîte',      '332N10001.01',   '', '', 'Rack',         '2', '300', '200', '800',  'B', 'B', 'Cat. S', 'Qual. H225', '', 'Colonnette | NSA 5512 | COL-M5-25\nEntretoise | NSA 5520 | ENT-10', 'Collier | NSA 8421 | CT-200\nEmbase | ECS 2210 | EMB-6', '', ''],
    ['332N10001',   'Plaquette éclairante', '332N10001.03',   '', 'NAV, navigation, mission transport', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332C50001',   'Harnais',              '332P20001.03',   'HRN-2251-A', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880R30001',  'Structure boîte',      'U880R30001.01',  '', '', 'Nez',          '1', '600', '400', '1500', 'A', 'A', 'Cat. S', 'Qual. H160', 'Case 1', 'Colonnette | NSA 5512 | COL-M6-40\nÉquerre | EN 2491 | EQ-90-A\nInsert | NSA 5591 | INS-M6', 'Collier | NSA 8421 | CT-200\nPasse-fil | ECS 2230 | PF-12', '', ''],
    ['332F40001',   'Plaquette éclairante', '332F40001.02',   '', 'FLIGHT, pilotage, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332F40001',   'Structure boîte',      '332F40001.01',   '', '', 'Console STD',  '1', '500', '140', '495',  'A', 'A', 'Cat. S', 'Qual. H225', 'Case 1', 'Colonnette | NSA 5512 | COL-M4-20\nÉquerre | EN 2491 | EQ-90-A', 'Collier | NSA 8420 | CT-120\nEmbase | ECS 2210 | EMB-4', '', ''],
    ['332F40001',   'Harnais',              '332P20001.03',   'HRN-2251-A', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880P50001',  'Harnais',              'U880P50001.03',  'HRN-1601-C', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332S60001',   'Plaquette éclairante', '332P94101.02',   '', 'EOS, optronique, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880D70001',  'Structure boîte',      'U880D70001.01',  '', '', 'Console STD',  '1', '500', '145', '510',  'A', 'A', 'Cat. S', 'Qual. H160', 'Case 1', 'Colonnette | NSA 5512 | COL-M4-22\nÉquerre | EN 2491 | EQ-90-A', 'Collier | NSA 8420 | CT-120\nEmbase | ECS 2210 | EMB-4', '', ''],
    ['U880D70001',  'Plaquette éclairante', 'U880D70001.04',  '', 'DISPLAY, affichage, mission transport', '', '', '', '', '', '', '', '', '', '', '', '', '', '']
  ].map(function (l) { return [nouvelId_('L')].concat(l); });

  ss.getSheetByName(CFG.FEUILLES.NOMENCLATURE)
    .getRange(2, 1, nom.length, nom[0].length).setValues(nom);

  SpreadsheetApp.getActiveSpreadsheet().toast('Base NEXUS PLM déployée.', 'Système opérationnel');
}

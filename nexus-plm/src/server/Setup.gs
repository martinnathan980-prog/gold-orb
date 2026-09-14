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

  const boites = [
    ['APU',     '332P20001',   '332P20051',   'Super Puma', 'Validé',   'Qualified to H225', '', ''],
    ['EOS',     '332P94101',   '332P94051',   'Multi',      'En étude', 'Qualified to H225', '', ''],
    ['APU',     'U880A240101', 'U880A240051', 'H160',       'Obsolète', 'Qualified to H160', '', ''],
    ['NAV',     '332N10001',   '332N10051',   'Super Puma', 'Validé',   'Qualified to H225', '', ''],
    ['COM',     '332C50001',   '332C50051',   'Multi',      'En étude', 'Qualified to H160', '', ''],
    ['RADAR',   'U880R30001',  'U880R30051',  'H160',       'Validé',   'Qualified to H160', '', ''],
    ['FLIGHT',  '332F40001',   '332F40051',   'Super Puma', 'Validé',   'Qualified to H225', '', ''],
    ['POWER',   'U880P50001',  'U880P50051',  'H160',       'En étude', 'Qualified to H160', '', ''],
    ['SENSOR',  '332S60001',   '332S60051',   'Multi',      'Obsolète', 'Qualified to H225', '', ''],
    ['DISPLAY', 'U880D70001',  'U880D70051',  'H160',       'Validé',   'Qualified to H160', '', '']
  ];
  ss.getSheetByName(CFG.FEUILLES.BOITES)
    .getRange(2, 1, boites.length, boites[0].length).setValues(boites);

  // Colonnes : PN Global, Type, PN du type, Référence, Numéro, Mots-clés,
  //            Montage, Nb pas, Long, Larg, Masse, HL, DAL,
  //            Qualif. brouillard, Qualif. vibration, Qualif. explosion,
  //            Composant STD, Image, Commentaires
  // Chaque type ne renseigne que ce qui le concerne : un harnais n'a ni
  // dimensions ni masse, une plaquette porte des mots-clés de mission.
  const nom = [
    ['332P20001', 'Structure boîte', '332P20001.01', '', '', '', 'Console STD', '1', '500', '140', '500', 'A', 'A', 'Cat. S', 'Qual. H225', 'Case 1', '', '', ''],
    ['332P20001', 'Harnais', '332P20001.03', 'HRN-2251-A', '', '', '', '', '', '', '', '', '', '', '', '', 'Bouton poussoir | Push button (ECS 7251)\nBouton poussoir | Push button (ECS 0763)', '', ''],
    ['332P20001', 'Plaquette éclairante', '332P20001.05', '', '', 'APU, démarrage, mission SAR', '', '', '', '', '', '', '', '', '', '', 'Switch | Switch (ASNE 0567)', '', ''],
    ['332P94101', 'Structure boîte', '332P94101.01', '', '', '', 'Hors console', '5', '400', '200', '400', 'B', 'C', 'Cat. T', 'Qual. H225', '', '', '', ''],
    ['332P94101', 'Plaquette éclairante', '332P94101.02', '', '', 'EOS, optronique, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880A240101', 'Harnais', 'U880A240401', 'HRN-1601-C', '', '', '', '', '', '', '', '', '', '', '', '', 'Bouton poussoir | Pushrod (ASNE 0239)', '', ''],
    ['U880A240101', 'Structure boîte', 'U880A240101.01', '', '', '', 'Console STD', '2', '480', '140', '520', 'A', 'A', 'Cat. S', 'Qual. H160', 'Case 1', '', '', ''],
    ['332N10001', 'Structure boîte', '332N10001.01', '', '', '', 'Rack', '2', '300', '200', '800', 'B', 'B', 'Cat. S', 'Qual. H225', '', '', '', ''],
    ['332N10001', 'Plaquette éclairante', '332N10001.03', '', '', 'NAV, navigation, mission transport', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['332C50001', 'Harnais', '332C50001.02', 'HRN-2251-A', '', '', '', '', '', '', '', '', '', '', '', '', 'Bouton poussoir | Push button (ECS 0780)\nBouton poussoir | Push button (ECS 7251)', '', ''],
    ['U880R30001', 'Structure boîte', 'U880R30001.01', '', '', '', 'Nez', '1', '600', '400', '1500', 'A', 'A', 'Cat. S', 'Qual. H160', 'Case 1', '', '', ''],
    ['332F40001', 'Plaquette éclairante', '332F40001.02', '', '', 'FLIGHT, pilotage, mission SAR', '', '', '', '', '', '', '', '', '', '', 'Switch | Switch (ASNE 0567)', '', ''],
    ['332F40001', 'Structure boîte', '332F40001.01', '', '', '', 'Console STD', '1', '500', '140', '495', 'A', 'A', 'Cat. S', 'Qual. H225', 'Case 1', '', '', ''],
    ['332F40001', 'Harnais', '332F40001.03', 'HRN-2251-A', '', '', '', '', '', '', '', '', '', '', '', '', 'Switch | Switch (ASNE 0567)\nBouton poussoir | Push button (ECS 7251)', '', ''],
    ['U880P50001', 'Harnais', 'U880P50001.03', 'HRN-1601-C', '', '', '', '', '', '', '', '', '', '', '', '', 'Double command | FRF 772-034 (IG)', '', ''],
    ['332S60001', 'Plaquette éclairante', '332S60001.01', '', '', 'SENSOR, détection, mission SAR', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ['U880D70001', 'Structure boîte', 'U880D70001.01', '', '', '', 'Console STD', '1', '500', '145', '510', 'A', 'A', 'Cat. S', 'Qual. H160', 'Case 1', '', '', ''],
    ['U880D70001', 'Plaquette éclairante', 'U880D70001.04', '', '', 'DISPLAY, affichage, mission transport', '', '', '', '', '', '', '', '', '', '', '', '', '']
  ].map(function (l) { return [nouvelId_('L')].concat(l); });   // ID unique par ligne

  ss.getSheetByName(CFG.FEUILLES.NOMENCLATURE)
    .getRange(2, 1, nom.length, nom[0].length).setValues(nom);

  SpreadsheetApp.getActiveSpreadsheet().toast('Base NEXUS PLM déployée.', 'Système opérationnel');
}

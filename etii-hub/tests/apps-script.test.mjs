// Le serveur Google du site (tools/apps-script/site/Code.gs), exécuté ici
// contre une feuille simulée :   node tests/apps-script.test.mjs
//
// Code.gs ne tourne que chez Google ; ce test lui fournit des doublures des
// services qu'il appelle (SpreadsheetApp, Session, LockService, DriveApp,
// HtmlService, PropertiesService, Logger) et vérifie le contrat que
// magasin.js attend : qui est connecté, qui peut écrire, ce qui est rangé,
// relu, remplacé, annulé — y compris un élément plus long qu'une cellule.

import { readFileSync } from 'node:fs';
import vm from 'node:vm';

let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK   ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

/* --- Une feuille Google en mémoire -------------------------------------- */

const LIMITE_CELLULE = 50000;

function creerFeuille(nom) {
  const lignes = [];            // tableau de tableaux, ligne 1 = lignes[0]
  const fonds = new Map();      // couleur posée sur une cellule de la ligne 2 (journal)
  let colonnes = 26;
  const largeur = () => Math.max(0, ...lignes.map((l) => {
    let n = l.length; while (n > 0 && (l[n - 1] === '' || l[n - 1] === undefined)) n -= 1; return n;
  }));
  const hauteur = () => { let n = lignes.length; while (n > 0 && lignes[n - 1].every((c) => c === '' || c === undefined)) n -= 1; return n; };
  const cellule = (v) => {
    const t = v === null || v === undefined ? '' : v;
    if (typeof t === 'string' && t.length > LIMITE_CELLULE) throw new Error('Une cellule dépasse 50 000 caractères.');
    return t;
  };
  const feuille = {
    nom,
    getName: () => nom,
    getLastRow: hauteur,
    getLastColumn: largeur,
    getMaxRows: () => Math.max(1000, lignes.length),
    getMaxColumns: () => colonnes,
    setFrozenRows: () => feuille,
    appendRow(valeurs) {
      if (valeurs.length > colonnes) colonnes = valeurs.length;
      lignes.splice(hauteur(), 0, valeurs.map(cellule));
      return feuille;
    },
    deleteRow(n) { lignes.splice(n - 1, 1); return feuille; },
    insertRowAfter(n) { lignes.splice(n, 0, []); return feuille; },
    setColumnWidth: () => feuille,
    getRange(ligne, col, nbL = 1, nbC = 1) {
      if (col + nbC - 1 > colonnes) throw new Error('Les coordonnées de la plage sont en dehors de la feuille.');
      const plage = {
        getValues: () => Array.from({ length: nbL }, (_x, i) => Array.from({ length: nbC }, (_y, j) => {
          const l = lignes[ligne - 1 + i] || [];
          const v = l[col - 1 + j];
          return v === undefined ? '' : v;
        })),
        setValues(v) {
          v.forEach((l, i) => l.forEach((c, j) => {
            while (lignes.length < ligne + i) lignes.push([]);
            lignes[ligne - 1 + i][col - 1 + j] = cellule(c);
          }));
          return plage;
        },
        clearContent() {
          for (let i = 0; i < nbL; i++) for (let j = 0; j < nbC; j++) if (lignes[ligne - 1 + i]) lignes[ligne - 1 + i][col - 1 + j] = '';
          return plage;
        },
        setFontWeight: () => plage,
        setNumberFormat: () => plage,
        setFontColor: () => plage,
        setWrap: () => plage,
        setBackground(c) { if (ligne === 2 && nbL === 1 && nbC === 1) fonds.set(col, c); return plage; }
      };
      return plage;
    },
    _lignes: lignes,
    _fonds: fonds
  };
  return feuille;
}

function creerClasseur(id = 'classeur-essai') {
  const onglets = new Map();
  return {
    getId: () => id,
    getSheetByName: (n) => onglets.get(n) || null,
    getSheets: () => [...onglets.values()],
    insertSheet: (n) => { const f = creerFeuille(n); onglets.set(n, f); return f; },
    deleteSheet: (f) => { onglets.delete(f.getName()); },
    _onglets: onglets
  };
}

/* --- Les services Google, en doublures ---------------------------------- */

function environnement(options) {
  const classeur = creerClasseur();
  if (options.feuilleParDefaut) classeur.insertSheet('Feuille 1');
  const documents = options.documents || null;
  const proprietes = new Map();
  const etat = { connecte: options.connecte, journal: [], verrou: 0 };
  const contexte = {
    SpreadsheetApp: {
      getActiveSpreadsheet: () => classeur,
      openById: (id) => {
        if (id === 'classeur-essai') return classeur;
        if (documents && id === 'feuille-documents') return documents;
        throw new Error('classeur inconnu');
      }
    },
    Session: {
      getActiveUser: () => ({ getEmail: () => etat.connecte }),
      getEffectiveUser: () => ({ getEmail: () => options.proprietaire }),
      getScriptTimeZone: () => 'Europe/Paris'
    },
    Utilities: {
      formatDate: (d, _fuseau, _motif) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
    },
    PropertiesService: {
      getScriptProperties: () => ({ getProperty: (k) => proprietes.get(k) || null, setProperty: (k, v) => proprietes.set(k, v) })
    },
    LockService: { getScriptLock: () => ({ waitLock: () => { etat.verrou += 1; }, releaseLock: () => { etat.verrou -= 1; } }) },
    DriveApp: {
      getFileById: (id) => {
        if (id !== 'fichier-site') throw new Error('Exception: No item with the given ID could be found.');
        return { getName: () => 'etii-hub.html', getSize: () => 6800000, getBlob: () => ({ getDataAsString: () => '<!doctype html><title>ETII Hub</title><p>site</p>' }) };
      }
    },
    HtmlService: {
      XFrameOptionsMode: { ALLOWALL: 'ALLOWALL', DEFAULT: 'DEFAULT' },
      createHtmlOutput: (html) => {
        const sortie = { html, titre: '', meta: {}, cadre: null };
        sortie.setTitle = (x) => { sortie.titre = x; return sortie; };
        sortie.addMetaTag = (n, v) => { sortie.meta[n] = v; return sortie; };
        sortie.setXFrameOptionsMode = (m) => { sortie.cadre = m; return sortie; };
        return sortie;
      }
    },
    Logger: { log: (m) => etat.journal.push(String(m)) },
    console
  };
  vm.createContext(contexte);
  let code = readFileSync(new URL('../tools/apps-script/site/Code.gs', import.meta.url), 'utf8')
    .replace("var ID_FICHIER_SITE = 'COLLEZ_ICI_L_IDENTIFIANT_DU_FICHIER';", "var ID_FICHIER_SITE = 'fichier-site';");
  if (documents) code = code.replace("var DOCUMENTS_ID_FEUILLE = '';", "var DOCUMENTS_ID_FEUILLE = 'feuille-documents';");
  vm.runInContext(code, contexte, { filename: 'Code.gs' });
  return { contexte, classeur, etat };
}

/* --- Le contrat --------------------------------------------------------- */

const PROPRIETAIRE = 'chef.service@exemple.fr';
const { contexte: gs, classeur, etat } = environnement({ proprietaire: PROPRIETAIRE, connecte: PROPRIETAIRE });

console.log('== Installation ==');
gs.installer();
const RUBRIQUES = ['Communication center', 'À venir', 'Porteurs', 'Organigramme', 'Documents', 'Questions fréquentes', 'Réunions'];
t('installer() crée Éditeurs, le journal complet, un journal par rubrique, et les modifications — dans cet ordre',
  JSON.stringify(classeur.getSheets().map((f) => f.getName()))
    === JSON.stringify(['Éditeurs', 'Journal complet', ...RUBRIQUES.map((r) => 'Journal · ' + r), 'modifications']),
  JSON.stringify(classeur.getSheets().map((f) => f.getName())));
t('les onglets de journal ont leur en-tête lisible',
  classeur.getSheetByName('Journal complet')._lignes[0].join('|') === 'Date|Qui|Rubrique|Pôle|Action|Élément|Ce qui a changé'
  && classeur.getSheetByName('Journal · Porteurs')._lignes[0].join('|') === 'Date|Qui|Pôle|Action|Élément|Ce qui a changé');
t('le propriétaire est le premier éditeur', classeur.getSheetByName('Éditeurs')._lignes[1][0] === PROPRIETAIRE);
t('installer() dit que le fichier du site est trouvé', etat.journal.some((l) => /etii-hub\.html/.test(l)));
gs.installer();
t('relancé, installer() ne double pas l’éditeur', classeur.getSheetByName('Éditeurs').getLastRow() === 2);

console.log('\n== Servir le site ==');
const page = gs.doGet();
t('doGet() sert le fichier de Drive, titré, ouvert par son adresse /exec (pas d’intégration imposée)',
  /<p>site<\/p>/.test(page.html) && page.titre === 'ETII Hub' && page.cadre === 'DEFAULT' && /width=device-width/.test(page.meta.viewport));
const vierge = environnement({ proprietaire: PROPRIETAIRE, connecte: PROPRIETAIRE, feuilleParDefaut: true });
vierge.contexte.installer();
t('installer() retire l’onglet vide « Feuille 1 » du classeur neuf', !vierge.classeur.getSheetByName('Feuille 1') && !!vierge.classeur.getSheetByName('Éditeurs'));

console.log('\n== Qui est connecté ==');
let depart = gs.etiiDemarrer();
t('le propriétaire peut modifier', depart.email === PROPRIETAIRE && depart.peutModifier === true);
t('toutes les listes de modifications sont là, vides',
  ['communications', 'flotte', 'organigramme', 'faq', 'documents', 'reunions'].every((j) => Array.isArray(depart.modifications[j]) && !depart.modifications[j].length));

console.log('\n== Écrire, relire ==');
const rdv = { type: 'agenda', id: 'rdv-1', op: 'maj', donnees: { id: 'rdv-1', titre: 'Revue lot 4', date: '2026-10-02', lieu: '=Salle A' } };
const retour = gs.etiiPoser('communications', rdv);
t('une écriture est signée de l’adresse connectée', retour.par === PROPRIETAIRE && /^\d{4}-\d{2}-\d{2}T/.test(retour.le));
depart = gs.etiiDemarrer();
let lu = depart.modifications.communications;
t('elle se relit à l’identique, même un texte qui commence par « = »',
  lu.length === 1 && lu[0].type === 'agenda' && lu[0].id === 'rdv-1' && lu[0].op === 'maj'
  && JSON.stringify(lu[0].donnees) === JSON.stringify(rdv.donnees) && lu[0].par === PROPRIETAIRE);
gs.etiiPoser('communications', Object.assign({}, rdv, { donnees: Object.assign({}, rdv.donnees, { titre: 'Revue lot 4 (déplacée)' }) }));
lu = gs.etiiDemarrer().modifications.communications;
t('réécrire le même élément le remplace, sans doublon', lu.length === 1 && lu[0].donnees.titre === 'Revue lot 4 (déplacée)');

/* Une fiche de porteur longue : plus de deux cellules. */
const long = { type: 'porteur', id: 'H160', op: 'maj', donnees: { code: 'H160', fiche: { resume: 'x'.repeat(95000) + ' ; fin' } } };
gs.etiiPoser('flotte', long);
lu = gs.etiiDemarrer().modifications.flotte;
t('un élément plus long qu’une cellule est découpé et recollé', lu.length === 1 && lu[0].donnees.fiche.resume.length === 95006);
gs.etiiPoser('flotte', { type: 'porteur', id: 'H160', op: 'maj', donnees: { code: 'H160', fiche: { resume: 'court' } } });
lu = gs.etiiDemarrer().modifications.flotte;
t('remplacé par un élément court, il ne garde aucun morceau de l’ancien', lu.length === 1 && lu[0].donnees.fiche.resume === 'court');

gs.etiiPoser('faq', { type: 'question', id: 'f01', op: 'suppr', donnees: null });
lu = gs.etiiDemarrer().modifications.faq;
t('une suppression se range aussi', lu.length === 1 && lu[0].op === 'suppr' && lu[0].donnees === null);
gs.etiiRetirer('faq', 'question', 'f01');
t('etiiRetirer annule la modification', gs.etiiDemarrer().modifications.faq.length === 0);
const complet = classeur.getSheetByName('Journal complet');
t('le journal complet garde chaque geste, avec son auteur',
  complet.getLastRow() - 1 === 6 && complet._lignes.slice(1).every((l) => l[1] === PROPRIETAIRE), String(complet.getLastRow()));
t('le plus récent est en haut : l’annulation, puis la suppression',
  complet._lignes[1][4] === 'Annulation' && complet._lignes[2][4] === 'Suppression' && Object.prototype.toString.call(complet._lignes[1][0]) === '[object Date]');
t('chaque geste va aussi dans l’onglet de sa rubrique',
  classeur.getSheetByName('Journal · À venir').getLastRow() - 1 === 2
  && classeur.getSheetByName('Journal · Porteurs').getLastRow() - 1 === 2
  && classeur.getSheetByName('Journal · Questions fréquentes').getLastRow() - 1 === 2
  && classeur.getSheetByName('Journal · Communication center').getLastRow() === 1);
t('sans récit du site, l’élément se nomme par son titre ou son code',
  classeur.getSheetByName('Journal · À venir')._lignes.slice(1).some((l) => l[4] === 'Revue lot 4')
  && classeur.getSheetByName('Journal · Porteurs')._lignes.slice(1).every((l) => l[4] === 'H160'));

gs.etiiPoser('communications', {
  type: 'agenda', id: 'rdv-2', op: 'maj', donnees: { id: 'rdv-2', titre: 'Atelier', pole: 'ETIIA' },
  journal: { rubrique: 'Porteurs', action: 'Ajout', element: 'Atelier harnais', pole: 'ETIIA', detail: '=HYPERLINK("x")\nLieu : « Salle B »' }
});
const haut = classeur.getSheetByName('Journal · À venir')._lignes[1];
t('le récit du site est repris : action, élément, pôle, ce qui a changé',
  haut[3] === 'Ajout' && haut[4] === 'Atelier harnais' && haut[2] === 'ETIIA' && /Salle B/.test(haut[5]), JSON.stringify(haut));
t('la rubrique est décidée par le serveur, pas par le site', classeur.getSheetByName('Journal · Porteurs')._lignes[1][4] !== 'Atelier harnais');
t('un texte qui commence par « = » reste du texte (pas une formule)', haut[5].startsWith("'="));
t('l’action se lit à sa couleur', classeur.getSheetByName('Journal · À venir')._fonds.get(4) === '#e2efe3');

const histo = gs.etiiJournal(3);
t('etiiJournal rend les derniers gestes, le plus récent d’abord, en texte',
  Array.isArray(histo) && histo.length === 3 && histo[0].element === 'Atelier harnais' && histo[0].rubrique === 'À venir'
  && histo[0].action === 'Ajout' && /^\d{4}-\d{2}-\d{2}T/.test(histo[0].le) && histo[1].action === 'Annulation', JSON.stringify(histo[0]));
t('le verrou est toujours rendu', etat.verrou === 0);

console.log('\n== Qui ne peut pas écrire ==');
etat.connecte = 'collegue@exemple.fr';
depart = gs.etiiDemarrer();
t('un lecteur voit les modifications, sans droit d’écrire', depart.peutModifier === false && depart.modifications.communications.length === 2);
let refus = '';
try { gs.etiiPoser('communications', rdv); } catch (e) { refus = e.message; }
t('son écriture est refusée par le serveur (NON_AUTORISE)', refus === 'NON_AUTORISE');
refus = '';
try { gs.etiiJournal(10); } catch (e) { refus = e.message; }
t('il ne lit pas le journal (il porte des adresses)', refus === 'NON_AUTORISE');
classeur.getSheetByName('Éditeurs').appendRow(['  Collegue@Exemple.fr ', 'Personne 12']);
t('ajouté à « Éditeurs » (casse et espaces indifférents), il peut écrire', gs.etiiDemarrer().peutModifier === true);
etat.connecte = '';
t('sans adresse connue (hors domaine), personne n’écrit', gs.etiiDemarrer().peutModifier === false);
refus = '';
try { gs.etiiPoser('inconnu', rdv); } catch (e) { refus = e.message; }
t('un jeu inconnu est refusé', /NON_AUTORISE|inconnu/.test(refus));
etat.connecte = PROPRIETAIRE;
refus = '';
try { gs.etiiPoser('inconnu', rdv); } catch (e) { refus = e.message; }
t('même pour le propriétaire', /inconnu/.test(refus));

console.log('\n== Les documents : un classeur, un onglet par pôle ==');
t('non branché, le site garde ses documents', gs.etiiDemarrer().bases.documents === undefined);
const feuilleDocs = creerClasseur('feuille-documents');
const ongletA = feuilleDocs.insertSheet('ETIIA');
ongletA.appendRow(['Référence', 'Titre', 'Type de document', 'Métier', 'Responsable', 'Programme', 'Mise à jour', 'Lien', 'Mots-clés', 'Colonne ignorée']);
ongletA.appendRow(['ETII-TEC-100', 'Guide de câblage', 'Technique', 'Harnais; Intégration 3D', 'Personne 08', 'H160', new Date(2026, 8, 3), 'https://example.invalid/100', 'câblage, harnais', 'x']);
ongletA.appendRow(['', '', 'Technique', '', '', '', '', '', '', '']);
const ongletE = feuilleDocs.insertSheet('ETIIE');
ongletE.appendRow(['Lien', 'Intitulé', 'Réf', 'Date', 'Pôle']);
ongletE.appendRow(['https://example.invalid/7', 'Procédure de revue', 'ETII-PRO-007', '15/07/2026', '']);
ongletE.appendRow(['https://example.invalid/8', 'Note commune', 'ETII-PRO-008', '', 'ETIIE, ETIII']);
ongletE.appendRow(['', 'Doublon de référence', 'ETII-TEC-100', '', '']);
const ongletI = feuilleDocs.insertSheet('ETIII');
ongletI.appendRow(['Titre', 'Lien']);
ongletI.appendRow(['Sans référence', 'https://example.invalid/9']);
feuilleDocs.insertSheet('Brouillon').appendRow(['Titre']);
const avecDocs = environnement({ proprietaire: PROPRIETAIRE, connecte: 'lecteur@exemple.fr', documents: feuilleDocs });
const reponse = avecDocs.contexte.etiiDemarrer();
const lus = reponse.bases.documents;
t('les trois onglets sont lus, ligne à ligne, sans les lignes sans titre ni les autres onglets',
  Array.isArray(lus) && lus.length === 5 && !reponse.basesErreur, JSON.stringify(lus && lus.map((d) => d.titre)));
t('les colonnes sont reconnues par leur titre, accents et variantes compris, et dans n’importe quel ordre',
  lus[0].titre === 'Guide de câblage' && lus[0].reference === 'ETII-TEC-100' && lus[0].type === 'Technique'
  && lus[0].porteur === 'Personne 08' && lus[0].perimetre === 'H160' && lus[0].lien === 'https://example.invalid/100'
  && lus[1].titre === 'Procédure de revue' && lus[1].reference === 'ETII-PRO-007' && lus[1].lien === 'https://example.invalid/7', JSON.stringify(lus.slice(0, 2)));
t('le pôle vient du nom de l’onglet ; une colonne Pôle remplie a le dernier mot',
  JSON.stringify(lus.map((d) => d.pole)) === JSON.stringify([['ETIIA'], ['ETIIE'], ['ETIIE', 'ETIII'], ['ETIIE'], ['ETIII']]), JSON.stringify(lus.map((d) => d.pole)));
t('les listes se découpent (virgules, points-virgules)',
  JSON.stringify(lus[0].metier) === '["Harnais","Intégration 3D"]' && JSON.stringify(lus[0].motsCles) === '["câblage","harnais"]');
t('les dates deviennent AAAA-MM-JJ (cellule date comme « 15/07/2026 »)', lus[0].maj === '2026-09-03' && lus[1].maj === '2026-07-15');
t('l’identifiant est la référence, sinon l’onglet et la ligne, et reste unique',
  lus[0].id === 'ETII-TEC-100' && lus[3].id !== 'ETII-TEC-100' && lus[4].id === 'ETIII-ligne-2' && new Set(lus.map((d) => d.id)).size === 5, JSON.stringify(lus.map((d) => d.id)));
const sansE = creerClasseur('feuille-documents');
sansE.insertSheet('ETIIA').appendRow(['Titre']);
sansE.getSheetByName('ETIIA').appendRow(['Seul document']);
sansE.insertSheet('ETIII').appendRow(['Colonne sans titre']);
const partiel = environnement({ proprietaire: PROPRIETAIRE, connecte: PROPRIETAIRE, documents: sansE }).contexte.etiiDemarrer();
t('un onglet absent ou sans « Titre » n’empêche pas les autres, et le site le dit',
  partiel.bases.documents.length === 1 && /ETIIE.*introuvable/.test(partiel.basesErreur) && /ETIII.*Titre/.test(partiel.basesErreur), JSON.stringify(partiel.basesErreur));
const casse = environnement({ proprietaire: PROPRIETAIRE, connecte: PROPRIETAIRE, documents: creerClasseur('feuille-documents') });
const r = casse.contexte.etiiDemarrer();
t('un classeur sans aucun onglet lisible ne bloque pas le site : il garde ses documents, et le dit', r.bases.documents === undefined && /illisible/.test(r.basesErreur || ''), JSON.stringify(r.basesErreur));
casse.contexte.installer();
t('installer() dit ce qu’il a lu des documents', casse.etat.journal.some((l) => /Documents illisibles/.test(l)));

console.log(`\n  ${ok} réussis, ${ko} échoués`);
process.exit(ko ? 1 : 0);

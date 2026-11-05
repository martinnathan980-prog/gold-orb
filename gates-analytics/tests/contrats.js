/* Débrief 30 : les contrats se gèrent depuis le tableau de bord. Le VRAI
   Code.gs, sur un classeur en mémoire, sans navigateur : la fiche de chaque
   contrat (adminEnregistrerContrat), le contrat prévu et son retrait
   (adminRetirerContratPrevu), les comptes rendus (importRapport) et ce que
   l'administration en dit (adminContrats), ce que la fenêtre d'import reçoit
   (parametresImport_, importContrats), et l'import du premier export d'un
   prévu par les fonctions mêmes que la fenêtre appelle (cibleImport,
   importSecondeBaseDebut / Lot / Fin) — sans rien taper ni choisir. La
   fenêtre elle-même, dans un vrai navigateur, est essayée par
   tests/import-see.js. */
const vm = require('vm');
const { chargerServeur } = require('./build-addon');
const { Feuille, Classeur } = require('./faux-classeur');
const { feuilleGates, colonne } = require('./feuille-gates');

let reussis = 0;
const echecs = [];
let sectionCourante = '';
function verifier(nom, condition, detail) {
  if (condition) { reussis++; console.log('  ✓ ' + nom); }
  else {
    echecs.push('[' + sectionCourante + '] ' + nom + (detail ? ' — ' + detail : ''));
    console.log('  ✗ ' + nom + (detail ? ' — ' + detail : ''));
  }
}
function section(t) { sectionCourante = t; console.log('\n— ' + t + ' —'); }
/* L'erreur levée par fn, ou '' — un refus se lit à son message. */
function erreurDe(fn) { try { fn(); return ''; } catch (e) { return e && e.message ? e.message : String(e); } }

const I_REF = colonne('Référence UD');
/* Un export GATES à la vraie structure ; `prefixe` : ses références, `groupe` : ses groupes « XXX AA … ». */
function gates(n, prefixe, groupe) {
  const g = feuilleGates(n);
  g.valeurs.forEach((l, r) => { if (r >= 3 && prefixe) l[I_REF] = String(l[I_REF]).replace(/^UD-/, prefixe + '-'); });
  if (groupe) g.valeurs[0] = g.valeurs[0].map(v => String(v).replace(/^HDK AA/, groupe + ' AA'));
  return g;
}
const onglet = (nom, g, cache) => new Feuille(nom, g.valeurs.map(l => l.slice()), !!cache, g.fusions.map(f => Object.assign({}, f)));

const ELEC = 'HDK AA 011 > Avancement Définition Electrique';
const HARNAIS = 'HDK AA 011 > Avancement Concept Harnais';

/* Le classeur de Nathan, en petit : HDK, sa tranche 2, THS (affichés), VIEUX
   (masqué). Nathan est le responsable ; Anne administre THS seule ; Paul
   administre tous les contrats ; Léa ne fait que lire. */
function monde(proprietes) {
  const c = new Classeur([onglet('HDK', gates(40)), onglet('HDK Tranche 2', gates(20, 'TDE')), onglet('THS', gates(30, 'THS')),
                          onglet('VIEUX', gates(10, 'VX'), true)], 'Suivi FWD contrats');
  c.proprietaire = 'nathan@airbus.com';
  const ctx = chargerServeur(c, Object.assign({
    SUIVI_FWD_ROLES: JSON.stringify({ admins: [{ email: 'anne@airbus.com', contrats: ['THS'] }, { email: 'paul@airbus.com', contrats: [] }] })
  }, proprietes || {}));
  ctx.__emailScript = 'nathan@airbus.com';
  ctx.__emailLecteur = 'nathan@airbus.com';
  const comme = (email, fn) => { const avant = ctx.__emailLecteur; ctx.__emailLecteur = email; try { return fn(); } finally { ctx.__emailLecteur = avant; } };
  const prop = cle => JSON.parse(ctx.__proprietes[cle] || '{}');
  return { c, ctx, comme, prop };
}
/* L'heure dite comme le serveur la dit : « 14 h 07 ». */
const heureDite = d => d.getHours() + ' h ' + String(d.getMinutes()).padStart(2, '0');
/* Envoie un export GATES comme la fenêtre : le début, un lot, la fin. */
function importerGates(ctx, cible, g) {
  const jeton = ctx.ouvrirJetonImport_();
  const largeur = g.valeurs[0].length;
  const lignes = g.valeurs.map(l => { const o = l.slice(); while (o.length < largeur) o.push(''); return o.map(String); });
  const d = ctx.importSecondeBaseDebut(jeton, cible, largeur, lignes.length);
  ctx.importSecondeBaseLot(jeton, d.feuille, 1, lignes);
  return ctx.importSecondeBaseFin(jeton, d.feuille, cible, lignes.length, g.fusions.map(f => ({ ligne: f.ligne, col: f.col, nbLignes: 1, nbCols: f.larg })));
}

// =================================================================
section('Les droits : qui ajoute, qui modifie quelle fiche');
{
  const { ctx, comme } = monde();
  const vrk = { id: '', nomGates: 'VRK', colonnes: { fwd: ELEC, concept: '' }, psn: '4540' };
  const refusLea = erreurDe(() => comme('lea@airbus.com', () => ctx.adminEnregistrerContrat(vrk)));
  verifier('un lecteur ne peut rien ajouter : refus « [droits] Réservé au responsable et aux administrateurs de tous les contrats »',
    /^\[droits\] Réservé au responsable et aux administrateurs de tous les contrats : votre compte \(lea@airbus\.com\)/.test(refusLea), refusLea);
  const refusAnne = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat(vrk)));
  verifier('Anne (administratrice de THS seule) ne peut pas ajouter de contrat', /^\[droits\] Réservé au responsable et aux administrateurs de tous les contrats/.test(refusAnne), refusAnne);
  const ths = comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: 'THS', nomGates: 'THS Série', colonnes: { fwd: ELEC, concept: '' } }));
  verifier('Anne modifie la fiche de THS : acceptée, son nom GATES gardé', ths.enregistre === 'THS' && ctx.ficheDe_('THS').nomGates === 'THS Série', JSON.stringify(ctx.ficheDe_('THS')));
  const refusHdk = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: 'HDK', nomGates: 'HDK', colonnes: { fwd: ELEC } })));
  verifier('Anne ne modifie pas la fiche de HDK : « [droits] Réservé aux administrateurs de HDK »', /^\[droits\] Réservé aux administrateurs de HDK : /.test(refusHdk), refusHdk);
  const vueAnne = comme('anne@airbus.com', () => ctx.adminContrats());
  const ligne = (r, id) => r.actifs.concat(r.retires, r.prevus).filter(x => x.id === id)[0];
  verifier('adminContrats pour Anne : THS modifiable, HDK et VIEUX non ; rien à masquer ni à ajouter',
    ligne(vueAnne, 'THS').modifiable && !ligne(vueAnne, 'HDK').modifiable && !ligne(vueAnne, 'VIEUX').modifiable &&
    vueAnne.actifs.every(x => !x.gerable) && vueAnne.peutAjouter === false && vueAnne.droits.role === 'administrateur' && vueAnne.droits.tous === false,
    JSON.stringify(vueAnne.actifs.map(x => [x.id, x.modifiable, x.gerable])));
  const vuePaul = comme('paul@airbus.com', () => ctx.adminContrats());
  verifier('Paul (administrateur de tous) : tout est modifiable, il peut ajouter, masquer et réafficher',
    vuePaul.peutAjouter && vuePaul.actifs.concat(vuePaul.retires).every(x => x.modifiable && x.gerable), JSON.stringify(vuePaul.actifs.map(x => [x.id, x.modifiable, x.gerable])));
  const refusLecture = erreurDe(() => comme('lea@airbus.com', () => ctx.adminContrats()));
  verifier('un lecteur ne lit pas l’administration des contrats', /^\[droits\] Réservé aux administrateurs/.test(refusLecture), refusLecture);
  const refusRetrait = erreurDe(() => comme('anne@airbus.com', () => ctx.adminRetirerContratPrevu('VRK')));
  verifier('Anne ne retire pas un contrat prévu', /^\[droits\] Réservé au responsable et aux administrateurs de tous les contrats/.test(refusRetrait), refusRetrait);
}

// =================================================================
section('Ajouter un contrat : il est « prévu » jusqu’à son premier export');
{
  const { c, ctx, prop } = monde();
  const r = ctx.adminEnregistrerContrat({ id: '', nom: '', nomGates: 'VRK', colonnes: { fwd: ELEC, concept: '' }, psn: '4540' });
  verifier('VRK ajouté : sa fiche (nom GATES, date, auteur), ses colonnes et son PSN dans les magasins de toujours',
    r.enregistre === 'VRK' && prop('SUIVI_FWD_FICHES').VRK.nomGates === 'VRK' && prop('SUIVI_FWD_FICHES').VRK.par === 'nathan@airbus.com' &&
    /^\d{4}-\d\d-\d\dT/.test(prop('SUIVI_FWD_FICHES').VRK.ajoute) &&
    JSON.stringify(ctx.colonnesDuContrat('VRK')) === JSON.stringify({ fwd: ELEC, concept: '', source: 'fenetre' }) &&
    JSON.stringify(ctx.psnDuContrat('VRK')) === JSON.stringify({ psn: ['4540'], source: 'fenetre' }), JSON.stringify([prop('SUIVI_FWD_FICHES'), ctx.colonnesDuContrat('VRK')]));
  verifier('ni onglet ni contrat : listerContrats ne le connaît pas ; adminContrats le range dans « prévus », en attente',
    !c.getSheetByName('VRK') && !ctx.listerContrats(c).some(x => x.id === 'VRK') && r.prevus.length === 1 && r.prevus[0].id === 'VRK' &&
    r.prevus[0].prevu === true && r.prevus[0].retirable === true && r.prevus[0].gerable === false && r.prevus[0].modifiable === true &&
    r.prevus[0].suivi.niveau === 'attente' && r.prevus[0].suivi.lignes[0] === 'Prévu : son onglet sera créé au prochain passage du robot, avec son premier export GATES.' &&
    r.prevus[0].fiche.nomGates === 'VRK' && r.prevus[0].fiche.colonnes.fwd === ELEC && r.prevus[0].fiche.psn.join() === '4540',
    JSON.stringify(r.prevus));
  verifier('le journal de l’administration le dit', JSON.parse(ctx.__proprietes.SUIVI_FWD_JOURNAL_ADMIN)[0].quoi === 'contrat ajouté : VRK (GATES « VRK »)',
    ctx.__proprietes.SUIVI_FWD_JOURNAL_ADMIN);
  /* Débrief 33 : la page le voit désormais, à part (le champ « prevus » du
     paquet, section « Débrief 33 » plus bas) — mais toujours pas comme un
     contrat qu'on choisit, ni avec un paquet à lui. */
  verifier('la page des contrats n’en sait rien : ni menu, ni paquet', ctx.contratsPourLaPage_(ctx.listerContrats(c)).every(x => x.id !== 'VRK'));
  const t2 = ctx.adminEnregistrerContrat({ id: '', nom: 'HDK Tranche 3', nomGates: 'HDK', colonnes: { fwd: 'HDK AA 012 > Avancement Définition Electrique' } });
  verifier('une tranche peut venir du même export que son contrat : « HDK Tranche 3 », nom GATES « HDK », rangée sous HDK',
    t2.enregistre === 'HDK Tranche 3' && t2.prevus.some(x => x.id === 'HDK Tranche 3' && x.contrat === 'HDK' && x.tranche === 'Tranche 3'), JSON.stringify(t2.prevus));
  const doublon = erreurDe(() => ctx.adminEnregistrerContrat({ id: '', nom: 'NEO', nomGates: 'vrk', colonnes: { fwd: ELEC } }));
  verifier('deux contrats de familles différentes n’ont pas le même nom GATES',
    doublon === '[nomGates] « vrk » est déjà le nom GATES de « VRK » : deux contrats auraient le même export.', doublon);
  const anne = ctx.adminEnregistrerAdmins([{ email: 'anne@airbus.com', contrats: ['THS', 'VRK'] }, { email: 'paul@airbus.com', contrats: [] }]);
  verifier('un contrat prévu se confie à un administrateur (Administrateurs), et la liste des contrats le propose',
    anne.admins.filter(a => a.email === 'anne@airbus.com')[0].contrats.join() === 'THS,VRK' && anne.contrats.some(x => x.id === 'VRK'), JSON.stringify(anne));
}

// =================================================================
section('Les messages de la fiche, au caractère près');
{
  const { c, ctx } = monde();
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: ELEC } });
  const essai = f => erreurDe(() => ctx.adminEnregistrerContrat(Object.assign({ id: '', nomGates: 'NEO', colonnes: { fwd: ELEC, concept: '' } }, f)));
  const cas = [
    ['nom GATES vide', { nomGates: '  ' }, '[nomGates] Donnez le nom exact de la tranche dans GATES : ce que vous tapez dans CHILDNéo pour avoir son export.'],
    ['nom GATES trop long', { nomGates: 'G'.repeat(81) }, '[nomGates] Ce nom fait 81 caractères : 80 au plus.'],
    ['nom GATES qui commence par =', { nomGates: '=HDK' }, '[nomGates] Un nom ne commence pas par =, +, - ou @.'],
    ['nom « HDK » : un contrat qui existe', { nom: 'HDK' }, '[nom] Le contrat « HDK » existe déjà : modifiez sa fiche plutôt que d’en ajouter un.'],
    ['nom « hdk tranche 2 » : aux majuscules près', { nom: 'hdk tranche 2' }, '[nom] Le contrat « HDK Tranche 2 » existe déjà : modifiez sa fiche plutôt que d’en ajouter un.'],
    ['nom « VIEUX » : un contrat masqué', { nom: 'VIEUX' }, '[nom] Le contrat « VIEUX » existe déjà, masqué : réaffichez-le plutôt que d’en ajouter un.'],
    ['nom « A,B »', { nom: 'A,B' }, '[nom] Pas de virgule ni de point-virgule dans le nom d’un contrat : elles séparent les contrats d’un jalon.'],
    ['nom trop long', { nom: 'N'.repeat(81) }, '[nom] Ce nom fait 81 caractères : 80 au plus.'],
    ['nom réservé « SEE HDK »', { nom: 'SEE HDK' }, '[nom] « SEE HDK » est un nom réservé (base SEE, historique, onglet de service, import ou copie) : choisissez-en un autre, comme « VRK ».'],
    ['nom d’un prévu', { nom: 'vrk', nomGates: 'VRK2' }, '[nom] Le contrat « VRK » est déjà prévu : modifiez sa fiche.'],
    ['ELEC vide', { colonnes: { fwd: '' } }, '[fwd] Donnez la colonne de la validation ELEC (la « définition électrique » de l’export GATES), comme « HDK AA 011 > Avancement Définition Electrique ».'],
    ['ELEC avec deux « > »', { colonnes: { fwd: 'A > B > C' } }, '[fwd] Une seule « > » : « Groupe > Colonne », ou le nom de la colonne seul.'],
    ['ELEC sans groupe autour de « > »', { colonnes: { fwd: '> Avancement' } }, '[fwd] Il manque le groupe ou la colonne autour de « > ».'],
    ['ELEC trop long', { colonnes: { fwd: 'x'.repeat(301) } }, '[fwd] Ce nom de colonne fait 301 caractères : 300 au plus.'],
    ['harnais = ELEC', { colonnes: { fwd: ELEC, concept: 'hdk aa 011>avancement definition electrique' } }, '[concept] La validation harnais doit être une autre colonne que la validation ELEC.'],
    ['harnais avec deux « > »', { colonnes: { fwd: ELEC, concept: 'a>b>c' } }, '[concept] Une seule « > » : « Groupe > Colonne », ou le nom de la colonne seul.'],
    ['PSN « 45 30x! »', { psn: '45 30x!' }, '[psn] « 30x! » n’est pas un PSN : des chiffres (des lettres au besoin), 20 caractères au plus, plusieurs séparés par des virgules — comme « 4530 ».']
  ];
  cas.forEach(([quoi, f, attendu]) => { const m = essai(f); verifier(quoi + ' : « ' + attendu.slice(0, 60) + '… »', m === attendu, m); });
  const avant = JSON.stringify(ctx.__proprietes);
  verifier('aucun de ces refus n’a rien écrit', !ctx.listerContrats(c).some(x => x.id === 'NEO') && !ctx.ficheDe_('NEO') && JSON.stringify(ctx.__proprietes) === avant);
  const proche = erreurDe(() => ctx.adminEnregistrerContrat({ id: 'HDK', nomGates: 'HDK', colonnes: { fwd: 'HDK AA 011 > Avancement Definition Electrik', concept: HARNAIS } }));
  verifier('une colonne ELEC qui n’est pas dans l’onglet HDK : le message donne les trois plus proches, la bonne d’abord',
    proche === '[fwd] La colonne « HDK AA 011 › Avancement Definition Electrik » n’est pas dans l’onglet « HDK » (son dernier export). Les plus proches : ' +
      '« HDK AA 011 › Avancement Définition Electrique », « HDK AA 012 › Avancement Définition Electrique », « HDK AA 001 › Avancement Définition Electrique ».', proche);
  const procheHarnais = erreurDe(() => ctx.adminEnregistrerContrat({ id: 'THS', nomGates: 'THS', colonnes: { fwd: ELEC, concept: 'Concept Harnais > Avancement Concept' } }));
  verifier('une colonne harnais absente de l’onglet THS : dite de même, sous son champ',
    /^\[concept\] La colonne « Concept Harnais › Avancement Concept » n’est pas dans l’onglet « THS » \(son dernier export\)\. Les plus proches : « /.test(procheHarnais), procheHarnais);
  const inconnu = erreurDe(() => ctx.adminEnregistrerContrat({ id: 'ZZZ', nomGates: 'ZZZ', colonnes: { fwd: ELEC } }));
  verifier('un contrat introuvable : « La liste vient d’être relue »', inconnu === 'Contrat introuvable : « ZZZ ». La liste vient d’être relue.', inconnu);
  verifier('« Groupe › Colonne » (le chevron de la page) et des espaces en trop : rangés « Groupe > Colonne »',
    ctx.designationSaisie_('  HDK AA 011  ›Avancement   Définition Electrique ', 'fwd') === ELEC && ctx.designationSaisie_('Avancement', 'fwd') === 'Avancement');
}

// =================================================================
section('Modifier un contrat qui a ses données : rien ne change sans raison');
{
  const { c, ctx, prop } = monde();
  const versionAvant = ctx.__proprietes.SUIVI_FWD_VERSION_DONNEES;
  const r = ctx.adminEnregistrerContrat({ id: 'HDK', nom: 'AUTRE NOM', nomGates: 'HDK', colonnes: { fwd: ELEC, concept: HARNAIS }, psn: '4530' });
  verifier('HDK reçoit son nom GATES ; ses colonnes et son PSN, ceux de la configuration, restent ceux de la configuration (rien d’écrit)',
    r.enregistre === 'HDK' && ctx.ficheDe_('HDK').nomGates === 'HDK' && !('HDK' in prop('SUIVI_FWD_COLONNES')) && !('HDK' in prop('SUIVI_FWD_PSN')) &&
    ctx.colonnesDuContrat('HDK').source === 'configuration' && ctx.psnDuContrat('HDK').source === 'configuration' &&
    r.colonnesChangees === false && r.donneesChangees === false && ctx.__proprietes.SUIVI_FWD_VERSION_DONNEES === versionAvant,
    JSON.stringify([prop('SUIVI_FWD_COLONNES'), prop('SUIVI_FWD_PSN'), r.colonnesChangees]));
  verifier('le nom d’un contrat qui a un onglet ne change pas (« AUTRE NOM » ignoré, sans erreur)', !!c.getSheetByName('HDK') && !ctx.ficheDe_('AUTRE NOM') &&
    ctx.listerContrats(c).map(x => x.id).join() === 'HDK,HDK Tranche 2,THS');
  const ligneHdk = r.actifs.filter(x => x.id === 'HDK')[0];
  verifier('la ligne de HDK : sa fiche — GATES « HDK », ELEC et harnais par défaut, PSN 4530 par défaut',
    ligneHdk.fiche.nomGates === 'HDK' && ligneHdk.fiche.colonnes.fwd === ELEC && ligneHdk.fiche.colonnes.concept === HARNAIS &&
    ligneHdk.fiche.colonnes.source === 'configuration' && ligneHdk.fiche.psn.join() === '4530' && ligneHdk.fiche.psnSource === 'configuration' && r.avecSee === true,
    JSON.stringify(ligneHdk.fiche));
  const r2 = ctx.adminEnregistrerContrat({ id: 'HDK Tranche 2', nomGates: 'HDK', colonnes: { fwd: 'HDK AA 012 > Avancement Définition Electrique', concept: '' }, psn: '4531, 4532' });
  verifier('la tranche 2 change de colonne et de PSN : écrits, le paquet est à refaire (version des données changée)',
    r2.colonnesChangees === true && r2.donneesChangees === true &&
    JSON.stringify(prop('SUIVI_FWD_COLONNES')['HDK Tranche 2']) === JSON.stringify({ fwd: 'HDK AA 012 > Avancement Définition Electrique', concept: '' }) &&
    JSON.stringify(prop('SUIVI_FWD_PSN')['HDK Tranche 2']) === JSON.stringify(['4531', '4532']) && ctx.__proprietes.SUIVI_FWD_VERSION_DONNEES !== versionAvant,
    JSON.stringify([prop('SUIVI_FWD_COLONNES'), prop('SUIVI_FWD_PSN')]));
  const r3 = ctx.adminEnregistrerContrat({ id: 'THS', nomGates: 'THS', colonnes: { fwd: ELEC, concept: HARNAIS }, psn: '' });
  verifier('un PSN effacé est gardé vide (« pas de comparaison SEE », voulu) — THS n’en avait pas : rien d’écrit',
    !('THS' in prop('SUIVI_FWD_PSN')) && r3.donneesChangees === false, JSON.stringify(prop('SUIVI_FWD_PSN')));
  ctx.adminEnregistrerContrat({ id: 'HDK', nomGates: 'HDK', colonnes: { fwd: ELEC, concept: HARNAIS }, psn: '' });
  verifier('le PSN de HDK effacé : [] écrit, il l’emporte sur la configuration', JSON.stringify(ctx.psnDuContrat('HDK')) === JSON.stringify({ psn: [], source: 'fenetre' }));
  const masque = ctx.adminEnregistrerContrat({ id: 'VIEUX', nomGates: 'VX', colonnes: { fwd: ELEC, concept: '' } });
  verifier('un contrat masqué a sa fiche aussi (suivi « Masqué : le robot ne l’exporte plus. »)',
    ctx.ficheDe_('VIEUX').nomGates === 'VX' && masque.retires[0].suivi.lignes[0] === 'Masqué : le robot ne l’exporte plus.' && masque.retires[0].suivi.niveau === 'neutre',
    JSON.stringify(masque.retires));
  verifier('les colonnes proposées : celles des exports déjà là, sans doublon, « Groupe > Colonne »',
    masque.colonnes.indexOf(ELEC) !== -1 && masque.colonnes.indexOf('Réalisation FWD > Avancement') !== -1 &&
    new Set(masque.colonnes.map(x => x.toLowerCase())).size === masque.colonnes.length && masque.colonnes.length <= 400, String(masque.colonnes.length));
}

// =================================================================
section('Retirer un contrat prévu ; un contrat qui a des données se masque');
{
  const { c, ctx, prop } = monde();
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: ELEC }, psn: '4540' });
  const avec = ctx.adminRetirerContratPrevu('vrk');
  verifier('VRK retiré (casse indifférente) : fiche, colonnes et PSN oubliés ; plus de prévu',
    !('VRK' in prop('SUIVI_FWD_FICHES')) && !('VRK' in prop('SUIVI_FWD_COLONNES')) && !('VRK' in prop('SUIVI_FWD_PSN')) && avec.prevus.length === 0 &&
    JSON.parse(ctx.__proprietes.SUIVI_FWD_JOURNAL_ADMIN)[0].quoi === 'contrat prévu retiré : VRK', JSON.stringify([prop('SUIVI_FWD_FICHES'), prop('SUIVI_FWD_COLONNES')]));
  const hdk = erreurDe(() => ctx.adminRetirerContratPrevu('HDK'));
  verifier('HDK ne se retire pas : « a déjà reçu des données »', hdk === '« HDK » a déjà reçu des données : il se masque, il ne se retire pas.', hdk);
  const inconnu = erreurDe(() => ctx.adminRetirerContratPrevu('VRK'));
  verifier('un prévu déjà retiré : « Contrat prévu introuvable … relue »', inconnu === 'Contrat prévu introuvable : « VRK ». La liste vient d’être relue.', inconnu);
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'NEO', colonnes: { fwd: ELEC } });
  const renomme = ctx.adminEnregistrerContrat({ id: 'NEO', nom: 'NEO Tranche 1', nomGates: 'NEO-T1', colonnes: { fwd: ELEC } });
  verifier('un prévu se renomme : ses clés suivent son nom', renomme.enregistre === 'NEO Tranche 1' && !ctx.ficheDe_('NEO') &&
    ctx.ficheDe_('NEO Tranche 1').nomGates === 'NEO-T1' && ctx.colonnesDuContrat('NEO Tranche 1').source === 'fenetre' && renomme.prevus.map(x => x.id).join() === 'NEO Tranche 1',
    JSON.stringify(renomme.prevus));
  verifier('masquer HDK : adminRetirerContrat fait toujours l’aller-retour', ctx.adminRetirerContrat('HDK', true).retires.some(x => x.id === 'HDK') &&
    ctx.adminRetirerContrat('HDK', false).actifs.some(x => x.id === 'HDK') && !c.getSheetByName('HDK').isSheetHidden());
}

// =================================================================
section('Les comptes rendus : la fenêtre et le robot disent ce qui s’est passé');
{
  const { ctx, prop } = monde();
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: ELEC } });
  const jeton = ctx.ouvrirJetonImport_();
  const sansJeton = (() => { const avant = ctx.__sansInterface; ctx.__sansInterface = true; try { return erreurDe(() => ctx.importRapport('mauvais-jeton', { source: 'robot', contrats: [] })); } finally { ctx.__sansInterface = avant; } })();
  verifier('sans jeton ni geste du classeur : refusé', /^Geste refusé/.test(sansJeton), sansJeton);
  verifier('un compte rendu illisible : « Compte rendu illisible. »', erreurDe(() => ctx.importRapport(jeton, 'x')) === 'Compte rendu illisible.' &&
    erreurDe(() => ctx.importRapport(jeton, { source: 'pirate' })) === 'Compte rendu illisible.');
  const versionAvant = ctx.__proprietes.SUIVI_FWD_VERSION_DONNEES;
  const rendu = ctx.importRapport(jeton, { source: 'fenetre', contrats: [
    { contrat: 'HDK', gates: { ok: true, code: '', plans: 40 }, see: { ok: true, lignes: 45 } },
    { contrat: 'hdk tranche 2', gates: { ok: true, code: 'colonne-harnais', message: 'La colonne de la validation harnais « X » n’est pas dans l’export du jour : le concept harnais ne se lit pas.', plans: 20 } },
    { contrat: 'THS', see: { ok: false, code: 'see-aucune', message: 'Aucune ligne SEE pour le PSN 4610 dans l’extract du jour : vérifiez le PSN de ce contrat dans Administration → Contrats.' } },
    { contrat: 'INCONNU', gates: { ok: true } }] });
  const maintenant = new Date();
  verifier('rendu : 3 contrats retenus, l’inconnu ignoré et nommé', rendu.ok === true && rendu.retenus === 3 && JSON.stringify(rendu.ignores) === '["INCONNU"]', JSON.stringify(rendu));
  verifier('un compte rendu ne touche ni au paquet ni au cache (version des données inchangée)', ctx.__proprietes.SUIVI_FWD_VERSION_DONNEES === versionAvant);
  let a = ctx.adminContrats();
  const l = id => a.actifs.concat(a.prevus, a.retires).filter(x => x.id === id)[0];
  verifier('HDK : « Mis à jour aujourd’hui à HH h MM », au vert', l('HDK').suivi.niveau === 'ok' &&
    JSON.stringify(l('HDK').suivi.lignes) === JSON.stringify(['Mis à jour aujourd’hui à ' + heureDite(maintenant)]), JSON.stringify(l('HDK').suivi));
  verifier('la tranche 2 (nommée sans casse) : le harnais en attention, et quand a eu lieu la dernière mise à jour',
    l('HDK Tranche 2').suivi.niveau === 'attention' && l('HDK Tranche 2').suivi.lignes[0].indexOf('La colonne de la validation harnais') === 0 &&
    l('HDK Tranche 2').suivi.lignes[1] === 'Dernière mise à jour réussie : aujourd’hui à ' + heureDite(maintenant) + '.', JSON.stringify(l('HDK Tranche 2').suivi));
  verifier('THS : pas de ligne SEE pour son PSN — en erreur, dit en clair, « Pas encore de mise à jour réussie. »',
    l('THS').suivi.niveau === 'erreur' && l('THS').suivi.lignes[0] === 'Aucune ligne SEE pour le PSN 4610 dans l’extract du jour : vérifiez le PSN de ce contrat dans Administration → Contrats.' &&
    l('THS').suivi.lignes[1] === 'Pas encore de mise à jour réussie.', JSON.stringify(l('THS').suivi));
  verifier('le robot n’a encore rien envoyé : la ligne du robot le dit', a.robot.niveau === 'neutre' &&
    a.robot.texte === 'Le robot n’a encore rien envoyé. Une fois installé et activé sur le PC, il passe chaque jour (à partir de 14 h, PC allumé) et dit ici ce qu’il a fait.', a.robot.texte);
  /* Le robot : GATES ne montre pas « HDKB » pour HDK ; il a tapé « VRK » pour VRK (réussi, sans ok). */
  ctx.importRapport(jeton, { source: 'robot', passage: { ok: true, message: '', heure: '14:00', debut: '2026-11-02T13:00:00Z', erreursFiche: 1 }, contrats: [
    { contrat: 'HDK', gates: { ok: false, code: 'gates-introuvable', message: 'GATES ne montre pas « HDKB » : vérifiez le « Nom exact de la tranche dans GATES » de ce contrat (tableau de bord → Administration → Contrats).', tape: 'HDKB' } },
    { contrat: 'THS', gates: { tape: 'THS' } },
    { contrat: 'VRK', gates: { tape: 'VRK' } }] });
  a = ctx.adminContrats();
  verifier('HDK : GATES ne montre pas « HDKB » — en erreur, puis la dernière mise à jour réussie',
    l('HDK').suivi.niveau === 'erreur' && l('HDK').suivi.lignes[0].indexOf('GATES ne montre pas « HDKB »') === 0 &&
    l('HDK').suivi.lignes[1] === 'Dernière mise à jour réussie : aujourd’hui à ' + heureDite(maintenant) + '.', JSON.stringify(l('HDK').suivi));
  verifier('THS : le robot qui dit seulement ce qu’il a tapé n’efface pas l’échec SEE posé par la fenêtre ; « tape » est gardé',
    l('THS').suivi.niveau === 'erreur' && prop('SUIVI_FWD_RAPPORTS').contrats.THS.see.ok === false && prop('SUIVI_FWD_RAPPORTS').contrats.THS.gates.tape === 'THS' &&
    prop('SUIVI_FWD_RAPPORTS').contrats.THS.gates.ok === undefined, JSON.stringify(prop('SUIVI_FWD_RAPPORTS').contrats.THS));
  verifier('VRK, prévu, dont le robot n’a dit que ce qu’il a tapé : toujours en attente', l('VRK').suivi.niveau === 'attente', JSON.stringify(l('VRK').suivi));
  /* Débrief 30 (page) : la fiche dit ce que le robot a tapé — la page le
     montre tant que le nom GATES de la fiche est vide. */
  verifier('la fiche porte « tape », ce que le robot a tapé dans GATES (HDK : « HDKB » ; THS : « THS »)',
    l('HDK').fiche.tape === 'HDKB' && l('THS').fiche.tape === 'THS' && l('VRK').fiche.tape === 'VRK', JSON.stringify([l('HDK').fiche, l('THS').fiche]));
  /* Débrief 30 (relu) : la tranche 2 (le harnais, en attention) se compte aussi : pas de « ✓ tout s’est bien passé » au-dessus d’un ⚠. */
  verifier('la ligne du robot : « Dernier passage du robot aujourd’hui à … : 2 contrats à corriger et 1 à vérifier, ci-dessous. » (HDK et THS en erreur, la tranche 2 en attention)',
    a.robot.niveau === 'attention' && a.robot.texte === 'Dernier passage du robot aujourd’hui à ' + heureDite(maintenant) + ' : 2 contrats à corriger et 1 à vérifier, ci-dessous.' && a.robot.heure === '14:00',
    a.robot.texte);
  verifier('gardé : l’heure du serveur, celle du robot, son nombre d’erreurs de fiche', prop('SUIVI_FWD_RAPPORTS').robot.ok === true &&
    prop('SUIVI_FWD_RAPPORTS').robot.heure === '14:00' && prop('SUIVI_FWD_RAPPORTS').robot.erreursFiche === 1 &&
    Math.abs(new Date(prop('SUIVI_FWD_RAPPORTS').robot.quand) - maintenant) < 60000, JSON.stringify(prop('SUIVI_FWD_RAPPORTS').robot));
  ctx.importRapport(jeton, { source: 'robot', passage: { ok: false, message: 'L’export SEE n’a pas abouti : délai dépassé.' }, contrats: [] });
  a = ctx.adminContrats();
  verifier('un passage raté : la ligne du robot en erreur, avec son message', a.robot.niveau === 'erreur' &&
    a.robot.texte === 'Dernier passage du robot aujourd’hui à ' + heureDite(maintenant) + ' : L’export SEE n’a pas abouti : délai dépassé.', a.robot.texte);
  /* Cinq jours sans mise à jour : on vieillit les dates gardées. */
  const r = prop('SUIVI_FWD_RAPPORTS'), vieux = new Date(Date.now() - 5 * 864e5).toISOString();
  r.contrats.HDK.gates = { quand: vieux, ok: true, code: '', message: '', dernierOk: vieux };
  r.robot.quand = vieux;
  ctx.__proprietes.SUIVI_FWD_RAPPORTS = JSON.stringify(r);
  a = ctx.adminContrats();
  verifier('un dernierOk vieux de 5 jours : « Pas mis à jour depuis 5 jours (dernière fois le jj/mm à …). Le PC du robot est-il allumé ? »',
    l('HDK').suivi.niveau === 'attention' && /^Pas mis à jour depuis 5 jours \(dernière fois le \d\d\/\d\d à \d+ h \d\d\)\. Le PC du robot est-il allumé \?$/.test(l('HDK').suivi.lignes[0]),
    JSON.stringify(l('HDK').suivi));
  verifier('le robot pas passé depuis 5 jours : dit en tête', a.robot.niveau === 'attention' &&
    /^Le robot n’est pas passé depuis 5 jours \(dernier passage le \d\d\/\d\d à \d+ h \d\d\)\. Le PC du robot est-il allumé \?$/.test(a.robot.texte), a.robot.texte);
  verifier('les dates dites : aujourd’hui, hier, le jj/mm, le jj/mm/aaaa',
    ctx.dateDite_(new Date(2026, 10, 2, 14, 7).toISOString(), new Date(2026, 10, 2, 18, 0)) === 'aujourd’hui à 14 h 07' &&
    ctx.dateDite_(new Date(2026, 10, 1, 9, 5).toISOString(), new Date(2026, 10, 2, 8, 0)) === 'hier à 9 h 05' &&
    ctx.dateDite_(new Date(2026, 9, 28, 14, 7).toISOString(), new Date(2026, 10, 2, 8, 0)) === 'le 28/10 à 14 h 07' &&
    ctx.dateDite_(new Date(2025, 9, 28, 14, 7).toISOString(), new Date(2026, 10, 2, 8, 0)) === 'le 28/10/2025 à 14 h 07' &&
    ctx.joursEntre_(new Date(2026, 9, 29, 23, 59).toISOString(), new Date(2026, 10, 2, 0, 1)) === 4);
  /* Le garde-fou de taille : 60 contrats, messages de 400 caractères. */
  const { ctx: ctx2, c: c2, prop: prop2 } = monde();
  for (let i = 0; i < 60; i++) c2.feuilles.push(onglet('C' + i, gates(3, 'C' + i)));
  const j2 = ctx2.ouvrirJetonImport_();
  const long = 'm'.repeat(500);
  const r2 = ctx2.importRapport(j2, { source: 'robot', passage: { ok: false, message: long }, contrats: Array.from({ length: 60 }, (_, i) =>
    ({ contrat: 'C' + i, gates: { ok: false, code: 'gates-export', message: long }, see: { ok: false, code: 'import', message: long } })) });
  const garde = ctx2.__proprietes.SUIVI_FWD_RAPPORTS;
  verifier('60 contrats aux messages de 500 caractères : le JSON gardé tient sous 8 500 octets, les messages raccourcis', r2.retenus === 60 &&
    Buffer.byteLength(garde, 'utf8') <= 8500 && Object.keys(JSON.parse(garde).contrats).length >= 20 && Object.keys(JSON.parse(garde).contrats).every(k => /^m{59}…$/.test(JSON.parse(garde).contrats[k].gates.message)), garde.length + ' / ' + Object.keys(JSON.parse(garde).contrats).length);
  const r3 = ctx2.importRapport(j2, { source: 'fenetre', contrats: [{ contrat: 'C1', gates: { ok: false, code: 'nimportequoi', message: 'a\u0007b' } }] });
  verifier('un code inconnu devient « autre », les caractères de contrôle s’en vont', r3.retenus === 1 &&
    JSON.parse(ctx2.__proprietes.SUIVI_FWD_RAPPORTS).contrats.C1.gates.code === 'autre' && JSON.parse(ctx2.__proprietes.SUIVI_FWD_RAPPORTS).contrats.C1.gates.message === 'a b');
  verifier('le contrat masqué a son compte rendu gardé, un prévu retiré le perd', (() => {
    ctx.importRapport(jeton, { source: 'fenetre', contrats: [{ contrat: 'VIEUX', gates: { ok: true } }, { contrat: 'VRK', gates: { ok: false, code: 'colonne-elec', message: 'm' } }] });
    const avant = !!prop('SUIVI_FWD_RAPPORTS').contrats.VIEUX && !!prop('SUIVI_FWD_RAPPORTS').contrats.VRK;
    ctx.adminRetirerContratPrevu('VRK');
    return avant && !prop('SUIVI_FWD_RAPPORTS').contrats.VRK && !!prop('SUIVI_FWD_RAPPORTS').contrats.VIEUX;
  })(), JSON.stringify(prop('SUIVI_FWD_RAPPORTS').contrats));
  void prop2;
}

// =================================================================
section('Un prévu en erreur : son premier export a échoué');
{
  const { ctx } = monde();
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: ELEC } });
  ctx.importRapport(ctx.ouvrirJetonImport_(), { source: 'robot', contrats: [{ contrat: 'VRK', gates: { ok: false, code: 'gates-introuvable', message: 'GATES ne montre pas « VRK » : vérifiez.' } }] });
  const a = ctx.adminContrats();
  verifier('le prévu dit son erreur au lieu d’« en attente », puis « Pas encore de mise à jour réussie. »', a.prevus[0].suivi.niveau === 'erreur' &&
    JSON.stringify(a.prevus[0].suivi.lignes) === JSON.stringify(['GATES ne montre pas « VRK » : vérifiez.', 'Pas encore de mise à jour réussie.']), JSON.stringify(a.prevus[0].suivi));
  verifier('et la ligne du robot, sans passage dit, reste neutre', a.robot.niveau === 'neutre');
}

// =================================================================
section('Ce que la fenêtre d’import reçoit : les prévus, le nom GATES de chacun');
{
  const { c, ctx } = monde();
  ctx.adminEnregistrerContrat({ id: 'HDK', nomGates: 'HDK série', colonnes: { fwd: ELEC, concept: HARNAIS } });
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: 'VRK AA 011 > Avancement Définition Electrique', concept: 'VRK AA 011 > Avancement Concept Harnais' }, psn: '4540' });
  const P = ctx.parametresImport_(c);
  verifier('P.prevus : VRK, son nom GATES, sa base SEE à créer, son PSN, ses colonnes', P.prevus.length === 1 && P.prevus[0].id === 'VRK' &&
    P.prevus[0].nomGates === 'VRK' && P.prevus[0].onglet === 'SEE VRK' && P.prevus[0].existe === false && P.prevus[0].refs.length === 0 &&
    P.prevus[0].psn.join() === '4540' && P.prevus[0].psnSource === 'fenetre' && P.prevus[0].colonnes.fwd === 'VRK AA 011 > Avancement Définition Electrique',
    JSON.stringify(P.prevus));
  verifier('P.contrats : chacun son nom GATES (« HDK série », rien pour THS) ; les cases de toujours', P.contrats.map(x => x.id + ':' + x.nomGates).join() === 'HDK:HDK série,HDK Tranche 2:,THS:',
    JSON.stringify(P.contrats.map(x => [x.id, x.nomGates])));
  const liste = ctx.importContrats(P.jeton);
  verifier('importContrats rend toujours un tableau (sans les prévus)', Array.isArray(liste) && liste.length === 3 && liste.every(x => 'nomGates' in x));
  const pourVrk = erreurDe(() => ctx.nomNouveauContrat(c, 'vrk'));
  verifier('un nouveau contrat tapé « vrk » dans la fenêtre : « est prévu dans le tableau de bord », sa case l’attend',
    pourVrk === 'Le contrat « VRK » est prévu dans le tableau de bord : son export va dans sa case, « GATES VRK ».', pourVrk);
  const virgule = erreurDe(() => ctx.nomNouveauContrat(c, 'A;B'));
  verifier('ni virgule ni point-virgule dans un nom tapé dans la fenêtre', virgule === '« A;B » : pas de virgule ni de point-virgule dans le nom d’un contrat (elles séparent les contrats d’un jalon).', virgule);
  verifier('les messages d’avant ne changent pas (« existe déjà : son export va dans sa case »)',
    erreurDe(() => ctx.nomNouveauContrat(c, 'HDK')) === 'Le contrat « HDK » existe déjà : son export va dans sa case, « GATES HDK ».');
  const k = ctx.cibleImport(c, { sorte: 'gates', contrat: 'VRK', nouveau: true, prevu: true, colonnes: { fwd: 'Pirate > Colonne' } });
  verifier('cibleImport d’un prévu : nouveau, prévu, et les colonnes DU SERVEUR (pas celles envoyées)', k.prevu === true && k.nouveau === true && k.onglet === 'VRK' &&
    JSON.stringify(k.colonnes) === JSON.stringify({ fwd: 'VRK AA 011 > Avancement Définition Electrique', concept: 'VRK AA 011 > Avancement Concept Harnais' }), JSON.stringify(k));
  const parti = erreurDe(() => ctx.cibleImport(c, { sorte: 'gates', contrat: 'NEO', nouveau: true, prevu: true }));
  verifier('un prévu retiré entre-temps : « Contrat prévu introuvable »', /^Contrat prévu introuvable : « NEO » \(retiré de l’administration entre-temps, ou déjà créé\)\. Rouvrir la fenêtre d’import\.$/.test(parti), parti);
}

// =================================================================
section('Le premier export d’un prévu crée son onglet, avec les colonnes de sa fiche, sans rien choisir');
{
  const { c, ctx, prop } = monde();
  const VRK_ELEC = 'VRK AA 011 > Avancement Définition Electrique';
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: VRK_ELEC, concept: '' }, psn: '4540' });
  const colonnesAvant = JSON.stringify(ctx.colonnesDuContrat('VRK'));
  const fin = importerGates(ctx, { sorte: 'gates', contrat: 'VRK', nouveau: true, prevu: true }, gates(25, 'VRK', 'VRK'));
  verifier('l’onglet « VRK » est créé, rangé après les contrats ; la page y lit la colonne de la fiche', !!c.getSheetByName('VRK') && fin.nouveau === true &&
    fin.colonneSuivie === VRK_ELEC && fin.plans === 25 && ctx.listerContrats(c).map(x => x.id).join() === 'HDK,HDK Tranche 2,THS,VRK', JSON.stringify(fin));
  verifier('ses colonnes et son PSN n’ont pas bougé ; il n’est plus prévu', JSON.stringify(ctx.colonnesDuContrat('VRK')) === colonnesAvant &&
    ctx.psnDuContrat('VRK').psn.join() === '4540' && ctx.contratsPrevus_(c).length === 0 && ctx.adminContrats().actifs.some(x => x.id === 'VRK' && !x.prevu && x.fiche.nomGates === 'VRK'),
    JSON.stringify(ctx.colonnesDuContrat('VRK')));
  const releve = ctx.importArchiverReleve(ctx.ouvrirJetonImport_(), 'VRK', true);
  verifier('son relevé de la semaine s’archive', releve.ok === true && releve.plans === 25, JSON.stringify(releve));
  /* Un autre prévu, dont la colonne ELEC n'est pas dans l'export : rien n'est créé, le message donne les proches. */
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'NEO', colonnes: { fwd: 'NEO AA 011 > Avancement Definition Electrik' } });
  const avant = c.getSheets().map(f => f.getName()).join();
  const m = erreurDe(() => importerGates(ctx, { sorte: 'gates', contrat: 'NEO', nouveau: true, prevu: true }, gates(10, 'NEO', 'XYZ')));
  verifier('une colonne ELEC absente de l’export : l’onglet n’est pas créé, rien ne reste, et le message dit les trois plus proches et où corriger',
    m === 'La colonne de la validation ELEC « NEO AA 011 › Avancement Definition Electrik » n’est pas dans cet export de « NEO » : son onglet n’est pas créé. ' +
      'Les plus proches : « XYZ AA 011 › Avancement Définition Electrique », « XYZ AA 012 › Avancement Définition Electrique », « XYZ AA 001 › Avancement Définition Electrique ». ' +
      'Corrigez-la dans le tableau de bord → Administration → Contrats.' && c.getSheets().map(f => f.getName()).join() === avant && ctx.contratsPrevus_(c).length === 1, m);
  /* Un harnais absent n'arrête pas un prévu. */
  ctx.adminEnregistrerContrat({ id: 'NEO', nomGates: 'NEO', colonnes: { fwd: 'XYZ AA 011 > Avancement Définition Electrique', concept: 'Rien > Pas là' } });
  const finNeo = importerGates(ctx, { sorte: 'gates', contrat: 'NEO', nouveau: true, prevu: true }, gates(10, 'NEO', 'XYZ'));
  verifier('un harnais absent n’arrête pas le prévu : l’onglet est créé, le bilan dit le harnais demandé et introuvable',
    !!c.getSheetByName('NEO') && finNeo.conceptDemande === true && finNeo.concept === false && finNeo.colonneSuivie === 'XYZ AA 011 > Avancement Définition Electrique', JSON.stringify(finNeo));
  void prop;
}

// =================================================================
section('Les contrats d’avant ne changent pas');
{
  const { c, ctx } = monde();
  verifier('sans fiche : listerContrats, colonnesDuContrat, psnDuContrat comme avant', ctx.listerContrats(c).map(x => x.id).join() === 'HDK,HDK Tranche 2,THS' &&
    JSON.stringify(ctx.colonnesDuContrat('HDK')) === JSON.stringify({ fwd: ELEC, concept: HARNAIS, source: 'configuration' }) &&
    JSON.stringify(ctx.psnDuContrat('HDK')) === JSON.stringify({ psn: ['4530'], source: 'configuration' }) && ctx.contratsPrevus_(c).length === 0);
  const a = ctx.adminContrats();
  verifier('adminContrats garde ses champs d’avant (id, nom, contrat, tranche, gerable) et le nom GATES vide, « Pas encore de compte rendu du robot. »',
    a.actifs.map(x => [x.id, x.nom, x.contrat, x.tranche, x.gerable].join('|')).join() === 'HDK|HDK|HDK||true,HDK Tranche 2|HDK › Tranche 2|HDK|Tranche 2|true,THS|THS|THS||true' &&
    a.retires.map(x => x.id).join() === 'VIEUX' && a.prevus.length === 0 && a.actifs.every(x => x.fiche.nomGates === '' && x.suivi.lignes[0] === 'Pas encore de compte rendu du robot.'),
    JSON.stringify(a.actifs.map(x => [x.id, x.nom, x.contrat, x.tranche, x.gerable, x.suivi])));
  const fin = importerGates(ctx, { sorte: 'gates', contrat: 'HDK', nouveau: false }, gates(40));
  verifier('l’import de HDK, comme avant : remplacé, colonne suivie de la configuration', fin.remplace === true && fin.nouveau === false && fin.colonneSuivie === ELEC, JSON.stringify(fin));
  const neuf = importerGates(ctx, { sorte: 'gates', contrat: 'ABC', nouveau: true }, gates(10, 'ABC'));
  verifier('un nouveau contrat de la fenêtre (« Ajouter un contrat… »), comme avant', neuf.nouveau === true && !!c.getSheetByName('ABC'), JSON.stringify(neuf));
  const jeton = ctx.ouvrirJetonImport_();
  verifier('importEnregistrerPsn : le même rendu qu’avant', JSON.stringify(ctx.importEnregistrerPsn(jeton, 'ths', '4610')) === JSON.stringify({ ok: true, contrat: 'THS', psn: ['4610'], source: 'fenetre' }));
  const unSeul = monde();
  vm.runInContext("CONFIG.FEUILLE_DONNEES = 'HDK'", unSeul.ctx);
  const refus = erreurDe(() => unSeul.ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: ELEC } }));
  verifier('CONFIG.FEUILLE_DONNEES : pas de nouveau contrat, ni de prévu', refus === '[nom] Ce tableau de bord suit un seul onglet (CONFIG.FEUILLE_DONNEES) : pas de nouveau contrat.' &&
    unSeul.ctx.adminContrats().peutAjouter === false && unSeul.ctx.parametresImport_(unSeul.c).prevus.length === 0, refus);
}

// =================================================================
/* Débrief 30 (relu) : ce que la relecture a trouvé, essayé ici sur le vrai
   Code.gs — chaque bloc rejoue le cas qu'elle a décrit. */
section('Relu : une fiche dont l’onglet a été renommé ou supprimé dans Sheets ne redevient pas « prévue »');
{
  const { c, ctx, prop } = monde();
  ctx.adminEnregistrerContrat({ id: 'HDK', nomGates: 'HDK', colonnes: { fwd: ELEC, concept: HARNAIS }, psn: '4530' });
  verifier('modifier la fiche d’un contrat qui a son onglet la marque « cree » (elle ne sera jamais prévue)', /^\d{4}-\d\d-\d\dT/.test(prop('SUIVI_FWD_FICHES').HDK.cree), JSON.stringify(prop('SUIVI_FWD_FICHES')));
  c.getSheetByName('HDK').setName('HDK Tranche 1');
  const a = ctx.adminContrats(), P = ctx.parametresImport_(c);
  verifier('onglet HDK renommé « HDK Tranche 1 » : HDK n’est PAS prévu — ni la fenêtre ni le robot ne le recevront', ctx.contratsPrevus_(c).length === 0 && P.prevus.length === 0 &&
    a.prevus.length === 0 && a.actifs.some(x => x.id === 'HDK Tranche 1'), JSON.stringify([P.prevus, a.prevus]));
  const hdk = a.introuvables.filter(x => x.id === 'HDK')[0];
  verifier('l’administration le montre à part, en clair : « L’onglet de « HDK » n’existe plus dans le classeur : renommé ou supprimé dans Sheets ? … » ; pas modifiable, mais oubliable par Nathan',
    !!hdk && hdk.introuvable === true && hdk.modifiable === false && hdk.retirable === true && hdk.suivi.niveau === 'erreur' &&
    hdk.suivi.lignes[0] === 'L’onglet de « HDK » n’existe plus dans le classeur : renommé ou supprimé dans Sheets ? Le robot ne l’exporte plus. Redonnez-lui ce nom dans Sheets, ou oubliez cette fiche.' &&
    /^Dernier passage|^Le robot n’a encore rien envoyé/.test(a.robot.texte), JSON.stringify(a.introuvables));
  const modif = erreurDe(() => ctx.adminEnregistrerContrat({ id: 'HDK', nomGates: 'HDK', colonnes: { fwd: ELEC } }));
  verifier('sa fiche ne se modifie pas (« … La liste vient d’être relue. »)', /^L’onglet de « HDK » n’existe plus dans le classeur.*La liste vient d’être relue\.$/.test(modif), modif);
  const ajout = erreurDe(() => ctx.adminEnregistrerContrat({ id: '', nom: 'hdk', nomGates: 'HDK Neuf', colonnes: { fwd: ELEC } }));
  verifier('un nouveau contrat ne prend pas son nom tant que la fiche est là', /^\[nom\] « HDK » a encore sa fiche, mais plus d’onglet/.test(ajout), ajout);
  const anne = erreurDe(() => ctx.__emailLecteur === 'x' || (() => { const avant = ctx.__emailLecteur; ctx.__emailLecteur = 'anne@airbus.com'; try { return ctx.adminRetirerContratPrevu('HDK'); } finally { ctx.__emailLecteur = avant; } })());
  verifier('Anne (THS seule) ne l’oublie pas', /^\[droits\]/.test(anne), anne);
  const oubli = ctx.adminRetirerContratPrevu('HDK');
  verifier('Nathan oublie la fiche : partie, ses colonnes et son PSN avec elle ; plus rien à part', oubli.introuvables.length === 0 && !('HDK' in prop('SUIVI_FWD_FICHES')) &&
    !('HDK' in prop('SUIVI_FWD_PSN')) && JSON.parse(ctx.__proprietes.SUIVI_FWD_JOURNAL_ADMIN)[0].quoi === 'fiche sans onglet oubliée : HDK', JSON.stringify(oubli.introuvables));
  /* Un prévu créé par l'import, puis son onglet supprimé à la main. */
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: 'VRK AA 011 > Avancement Définition Electrique' }, psn: '4540' });
  importerGates(ctx, { sorte: 'gates', contrat: 'VRK', nouveau: true, prevu: true }, gates(10, 'VRK', 'VRK'));
  verifier('l’import qui crée l’onglet d’un prévu le note dans sa fiche (« cree »)', !!prop('SUIVI_FWD_FICHES').VRK.cree && !!c.getSheetByName('VRK'), JSON.stringify(prop('SUIVI_FWD_FICHES').VRK));
  c.deleteSheet(c.getSheetByName('VRK'));
  verifier('son onglet supprimé à la main : VRK ne ressuscite pas — pas prévu, montré « onglet introuvable »', ctx.contratsPrevus_(c).length === 0 &&
    ctx.parametresImport_(c).prevus.length === 0 && ctx.adminContrats().introuvables.map(x => x.id).join() === 'VRK');
  /* Une fiche d'avant la relecture (sans « cree ») : le premier import la marque. */
  ctx.__proprietes.SUIVI_FWD_FICHES = JSON.stringify(Object.assign(prop('SUIVI_FWD_FICHES'), { THS: { nomGates: 'THS', ajoute: '2026-10-01T10:00:00.000Z' } }));
  importerGates(ctx, { sorte: 'gates', contrat: 'THS', nouveau: false }, gates(30, 'THS'));
  verifier('une fiche « ajoutée » sans « cree » (d’avant) : le premier import de son contrat la marque', !!prop('SUIVI_FWD_FICHES').THS.cree, JSON.stringify(prop('SUIVI_FWD_FICHES').THS));
  c.getSheetByName('THS').setName('THS Série');
  const rolesAvant = ctx.__proprietes.SUIVI_FWD_ROLES, oubliTHS = ctx.adminRetirerContratPrevu('THS');
  verifier('oublier la fiche sans onglet de THS laisse les droits d’Anne (son onglet a peut-être seulement changé de nom)',
    ctx.__proprietes.SUIVI_FWD_ROLES === rolesAvant && oubliTHS.messageDroits === '', ctx.__proprietes.SUIVI_FWD_ROLES);
}

section('Relu : retirer ou renommer un prévu pendant que le robot l’importe');
{
  const { c, ctx, prop } = monde();
  const VRK_ELEC = 'VRK AA 011 > Avancement Définition Electrique';
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: VRK_ELEC }, psn: '4540' });
  /* L'import du robot passe juste avant que le verrou soit pris. */
  const sousVerrou = ctx.sousVerrou_;
  const pendantLImport = () => { ctx.sousVerrou_ = function (fn) { ctx.sousVerrou_ = sousVerrou; importerGates(ctx, { sorte: 'gates', contrat: 'VRK', nouveau: true, prevu: true }, gates(10, 'VRK', 'VRK')); return sousVerrou(fn); }; };
  pendantLImport();
  const retrait = erreurDe(() => ctx.adminRetirerContratPrevu('VRK'));
  verifier('« Retirer » pendant l’import : refusé, en clair — « VRK vient de recevoir son premier export (le robot est passé) : il se masque, il ne se retire plus. La liste vient d’être relue. »',
    retrait === '« VRK » vient de recevoir son premier export (le robot est passé) : il se masque, il ne se retire plus. La liste vient d’être relue.', retrait);
  verifier('… et l’onglet né garde sa fiche, ses colonnes et son PSN', !!c.getSheetByName('VRK') && prop('SUIVI_FWD_FICHES').VRK.nomGates === 'VRK' &&
    ctx.colonnesDuContrat('VRK').fwd === VRK_ELEC && ctx.colonnesDuContrat('VRK').source === 'fenetre' && ctx.psnDuContrat('VRK').psn.join() === '4540',
    JSON.stringify([ctx.colonnesDuContrat('VRK'), ctx.psnDuContrat('VRK')]));
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'NEO', colonnes: { fwd: 'NEO AA 011 > Avancement Définition Electrique' }, psn: '4550' });
  ctx.sousVerrou_ = function (fn) { ctx.sousVerrou_ = sousVerrou; importerGates(ctx, { sorte: 'gates', contrat: 'NEO', nouveau: true, prevu: true }, gates(10, 'NEO', 'NEO')); return sousVerrou(fn); };
  const renomme = erreurDe(() => ctx.adminEnregistrerContrat({ id: 'NEO', nom: 'NEO Série 1', nomGates: 'NEO', colonnes: { fwd: 'NEO AA 011 > Avancement Définition Electrique' } }));
  verifier('un renommage pendant l’import : refusé (« vient de recevoir son premier export… rouvrez sa fiche ») ; ni prévu fantôme « NEO Série 1 », ni colonnes perdues',
    /^« NEO » vient de recevoir son premier export \(le robot est passé\) : sa fiche n’est pas enregistrée\. La liste vient d’être relue/.test(renomme) &&
    ctx.contratsPrevus_(c).length === 0 && !ctx.ficheDe_('NEO Série 1') && ctx.colonnesDuContrat('NEO').source === 'fenetre' && ctx.psnDuContrat('NEO').psn.join() === '4550', renomme);
  verifier('le verrou est rendu à chaque fois (sousVerrou_ d’origine remis)', ctx.sousVerrou_ === sousVerrou);
}

section('Relu : une administratrice limitée ne renomme pas un prévu hors de ses droits');
{
  const { c, ctx, comme, prop } = monde({ SUIVI_FWD_ROLES: JSON.stringify({ admins: [{ email: 'anne@airbus.com', contrats: ['HDK'] }] }) });
  ctx.adminEnregistrerContrat({ id: '', nom: 'HDK Tranche 3', nomGates: 'HDK T3', colonnes: { fwd: ELEC } });
  const zzz = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: 'HDK Tranche 3', nom: 'ZZZ', nomGates: 'HDK T3', colonnes: { fwd: ELEC } })));
  verifier('Anne (HDK seule) renomme le prévu « HDK Tranche 3 » en « ZZZ » : refusé, sous le champ Nom', zzz === '[nom] Seuls le responsable et les administrateurs de tous les contrats renomment un contrat prévu.' &&
    ctx.contratsPrevus_(c).map(x => x.id).join() === 'HDK Tranche 3', zzz);
  const ok = comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: 'HDK Tranche 3', nom: 'HDK Tranche 3', nomGates: 'HDK Tranche 3', colonnes: { fwd: ELEC } }));
  verifier('… mais elle modifie sa fiche sans le renommer', ok.enregistre === 'HDK Tranche 3' && prop('SUIVI_FWD_FICHES')['HDK Tranche 3'].nomGates === 'HDK Tranche 3');
}

section('Relu : les comptes rendus tiennent dans une propriété, comptés en octets');
{
  const { ctx, c } = monde();
  ctx.__octetsParValeur = 9216;
  for (let i = 0; i < 30; i++) c.feuilles.push(onglet('Contrat numéro ' + i + ' Tranche ' + i, gates(3, 'Z' + i)));
  const j = ctx.ouvrirJetonImport_();
  const dire = i => 'La colonne de la validation ELEC « HDK AA 0' + i + ' › Avancement Définition Électrique » n’est pas dans l’export du jour. Les plus proches : « HDK AA 011 › Avancement Définition Électrique », « Réalisation FWD › Avancement ». Corrigez-la dans Administration → Contrats.';
  const r = ctx.importRapport(j, { source: 'robot', passage: { ok: false, message: 'L’export SEE n’a pas abouti : « délai dépassé » — réessayé trois fois, sans succès.' },
    contrats: Array.from({ length: 30 }, (_, i) => ({ contrat: 'Contrat numéro ' + i + ' Tranche ' + i,
      gates: { ok: false, code: 'colonne-elec', message: dire(i), tape: 'Contrat numéro ' + i + ' – tranche ' + i + ' (série ’26)' },
      see: { ok: false, code: 'see-aucune', message: 'Aucune ligne SEE pour le PSN 45' + i + ' dans l’extract du jour : vérifiez le PSN de ce contrat dans Administration → Contrats.' } })) });
  const garde = ctx.__proprietes.SUIVI_FWD_RAPPORTS, lu = JSON.parse(garde);
  verifier('30 contrats aux messages français (é, ’, « ») : accepté par la limite de 9 Ko, le JSON tient sous 8 500 OCTETS, au moins dix contrats gardés avec leur message',
    r.ok === true && Buffer.byteLength(garde, 'utf8') <= 8500 && Object.keys(lu.contrats).length >= 10 &&
    Object.keys(lu.contrats).every(k => /^La colonne de la validation ELEC/.test(lu.contrats[k].gates.message)), Buffer.byteLength(garde, 'utf8') + ' octets, ' + Object.keys(lu.contrats).length + ' contrats');
  ctx.__octetsParValeur = 200;
  const refus = erreurDe(() => ctx.importRapport(j, { source: 'robot', passage: { ok: true }, contrats: [{ contrat: 'THS', gates: { ok: true } }] }));
  verifier('Google refuse malgré tout : un message en français, pas « Argument too large »', refus === 'Le compte rendu est trop gros pour le classeur : il n’est pas enregistré. Il sera renvoyé au prochain passage.', refus);
  verifier('les octets se comptent comme Google : « é » 2, « ’ » 3, un émoji 4', ctx.octetsUtf8_('é’a😀') === 2 + 3 + 1 + 4);
}

section('Relu : les droits suivent un prévu renommé, et partent avec un prévu retiré');
{
  const { ctx, comme, prop } = monde({ SUIVI_FWD_ROLES: JSON.stringify({ admins: [{ email: 'bob@airbus.com', contrats: ['VRK'] }, { email: 'anne@airbus.com', contrats: ['THS', 'NEO'] }] }) });
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: ELEC } });
  ctx.adminEnregistrerContrat({ id: '', nomGates: 'NEO', colonnes: { fwd: ELEC } });
  const r = ctx.adminEnregistrerContrat({ id: 'VRK', nom: 'VRK Série 1', nomGates: 'VRK', colonnes: { fwd: ELEC } });
  const roles = () => JSON.parse(ctx.__proprietes.SUIVI_FWD_ROLES).admins;
  verifier('VRK renommé « VRK Série 1 » : la portée de Bob suit, et la page le dit (« Les droits de bob@airbus.com suivent le nouveau nom. »)',
    JSON.stringify(roles().filter(a => a.email === 'bob@airbus.com')[0].contrats) === '["VRK Série 1"]' && r.messageDroits === 'Les droits de bob@airbus.com suivent le nouveau nom.', JSON.stringify([roles(), r.messageDroits]));
  const bob = comme('bob@airbus.com', () => ctx.adminEnregistrerContrat({ id: 'VRK Série 1', nom: 'VRK Série 1', nomGates: 'VRK S1', colonnes: { fwd: ELEC } }));
  verifier('… Bob modifie toujours sa fiche', bob.enregistre === 'VRK Série 1' && prop('SUIVI_FWD_FICHES')['VRK Série 1'].nomGates === 'VRK S1');
  const ret = ctx.adminRetirerContratPrevu('NEO');
  verifier('NEO retiré : la portée « NEO » d’Anne s’en va, THS reste', JSON.stringify(roles().filter(a => a.email === 'anne@airbus.com')[0].contrats) === '["THS"]' &&
    ret.messageDroits === 'Les droits de anne@airbus.com sont mis à jour.', JSON.stringify([roles(), ret.messageDroits]));
  const ret2 = ctx.adminRetirerContratPrevu('VRK Série 1');
  verifier('VRK Série 1 retiré : Bob, qui n’avait que lui, n’est plus administrateur — jamais « contrats: [] », qui voudrait dire « tous »',
    !roles().some(a => a.email === 'bob@airbus.com') && ret2.messageDroits === 'bob@airbus.com n’avait que ce contrat : plus de droits d’administration.' &&
    roles().every(a => a.contrats.length > 0), JSON.stringify([roles(), ret2.messageDroits]));
  /* Une portée de famille qui couvre encore une autre tranche reste. */
  const m2 = monde({ SUIVI_FWD_ROLES: JSON.stringify({ admins: [{ email: 'lea@airbus.com', contrats: ['HDK'] }] }) });
  m2.ctx.adminEnregistrerContrat({ id: '', nom: 'HDK Tranche 3', nomGates: 'HDK T3', colonnes: { fwd: ELEC } });
  m2.ctx.adminRetirerContratPrevu('HDK Tranche 3');
  verifier('retirer « HDK Tranche 3 » ne touche pas la portée « HDK » de Léa (elle couvre HDK et sa tranche 2)',
    JSON.stringify(JSON.parse(m2.ctx.__proprietes.SUIVI_FWD_ROLES).admins) === '[{"email":"lea@airbus.com","contrats":["HDK"]}]', m2.ctx.__proprietes.SUIVI_FWD_ROLES);
}

section('Relu : deux contrats, même export — les contrats sans fiche comptent aussi');
{
  const { ctx } = monde();
  const ths = erreurDe(() => ctx.adminEnregistrerContrat({ id: '', nom: 'NEO2', nomGates: 'THS', colonnes: { fwd: ELEC } }));
  verifier('THS n’a pas de fiche (le robot tape « THS ») : NEO2 avec le nom GATES « THS » est refusé', ths === '[nomGates] « THS » est déjà le nom GATES de « THS » : deux contrats auraient le même export.', ths);
  ctx.importRapport(ctx.ouvrirJetonImport_(), { source: 'robot', contrats: [{ contrat: 'VIEUX', gates: { tape: 'VX' } }, { contrat: 'THS', gates: { tape: 'THS-SERIE' } }] });
  const tape = erreurDe(() => ctx.adminEnregistrerContrat({ id: '', nom: 'NEO3', nomGates: 'ths-serie', colonnes: { fwd: ELEC } }));
  verifier('ce que le robot a tapé pour THS (« THS-SERIE ») compte comme son nom GATES', tape === '[nomGates] « ths-serie » est déjà le nom GATES de « THS » : deux contrats auraient le même export.', tape);
  verifier('une tranche peut toujours partager l’export de son contrat (« HDK Tranche 3 », GATES « HDK »)',
    ctx.adminEnregistrerContrat({ id: '', nom: 'HDK Tranche 3', nomGates: 'HDK', colonnes: { fwd: ELEC } }).enregistre === 'HDK Tranche 3');
}

section('Relu : une fiche s’écrit d’un seul coup, ou pas du tout');
{
  const { ctx, prop } = monde();
  ctx.__octetsParValeur = 9216;
  const grosses = {};
  for (let i = 0; i < 29; i++) grosses['C' + i] = { fwd: 'Groupe très long numéro ' + i + ' > ' + 'é'.repeat(130), concept: '' };
  ctx.__proprietes.SUIVI_FWD_COLONNES = JSON.stringify(grosses);
  ctx.adminContrats();           // le premier geste note le responsable : pas ce qu'on mesure
  const avant = JSON.stringify(ctx.__proprietes);
  const plein = erreurDe(() => ctx.adminEnregistrerContrat({ id: '', nomGates: 'VRK', colonnes: { fwd: 'VRK AA 011 > ' + 'Avancement Définition Électrique très détaillée'.repeat(5) }, psn: '4540' }));
  verifier('les colonnes ne tiennent plus : refus en français, et RIEN d’écrit (ni fiche, ni PSN) — pas de prévu à moitié enregistré',
    plein === 'Le classeur ne peut plus garder de nouvelle fiche : retirez un contrat prévu, ou raccourcissez les noms de colonnes. Rien n’a été changé.' &&
    JSON.stringify(ctx.__proprietes) === avant && !ctx.ficheDe_('VRK') && !('VRK' in prop('SUIVI_FWD_PSN')), plein);
}

section('Relu : colonne ELEC disparue de l’export d’un contrat existant');
{
  const { ctx } = monde();
  const m = erreurDe(() => importerGates(ctx, { sorte: 'gates', contrat: 'HDK', nouveau: false }, gates(40, null, 'XYZ')));
  verifier('le message donne les plus proches, et quoi faire si GATES a renommé la colonne',
    /^Colonne suivie absente de cet export : « HDK AA 011 › Avancement Définition Electrique » n’y est pas, alors que l’onglet « HDK » l’a\. Est-ce bien l’export de ce contrat, avec son bloc suivi \? Les plus proches : « XYZ AA 011 › Avancement Définition Electrique », /.test(m) &&
    / Si GATES a renommé la colonne, corrigez la colonne de la validation ELEC de ce contrat dans le tableau de bord → Administration → Contrats\./.test(m), m);
}

section('Relu : corriger une colonne sans retaper le nom GATES ; l’erreur corrigée attend le robot');
{
  const { ctx, prop } = monde();
  const r = ctx.adminEnregistrerContrat({ id: 'HDK', nomGates: '', colonnes: { fwd: ELEC, concept: HARNAIS } });
  verifier('un contrat qui a son onglet : le nom GATES peut rester vide (le robot tape ce qu’il tapait)', r.enregistre === 'HDK' && prop('SUIVI_FWD_FICHES').HDK.nomGates === '', JSON.stringify(prop('SUIVI_FWD_FICHES')));
  verifier('un prévu, lui, doit l’avoir', erreurDe(() => ctx.adminEnregistrerContrat({ id: '', nomGates: '', nom: 'VRK', colonnes: { fwd: ELEC } })) ===
    '[nomGates] Donnez le nom exact de la tranche dans GATES : ce que vous tapez dans CHILDNéo pour avoir son export.');
  const j = ctx.ouvrirJetonImport_();
  ctx.importRapport(j, { source: 'fenetre', contrats: [
    { contrat: 'HDK', gates: { ok: false, code: 'colonne-elec', message: 'La colonne de la validation ELEC « X » n’est pas dans l’export du jour.' } },
    { contrat: 'THS', see: { ok: false, code: 'see-aucune', message: 'Aucune ligne SEE pour le PSN 4610.' } }] });
  ctx.importRapport(j, { source: 'robot', passage: { ok: true, heure: '14:00' }, contrats: [] });
  const r2 = ctx.adminEnregistrerContrat({ id: 'HDK', nomGates: '', colonnes: { fwd: 'HDK AA 012 > Avancement Définition Electrique', concept: HARNAIS } });
  const hdk = r2.actifs.filter(x => x.id === 'HDK')[0];
  verifier('la colonne ELEC corrigée : plus de rouge — « Fiche corrigée aujourd’hui à … : le robot vérifiera à son prochain passage (chaque jour à partir de 14 h, PC allumé). »',
    r2.corrige === true && hdk.suivi.niveau === 'attente' && /^Fiche corrigée aujourd’hui à \d+ h \d\d : le robot vérifiera à son prochain passage \(chaque jour à partir de 14 h, PC allumé\)\.$/.test(hdk.suivi.lignes[0]),
    JSON.stringify(hdk.suivi));
  const r3 = ctx.adminEnregistrerContrat({ id: 'THS', nomGates: 'THS', colonnes: { fwd: ELEC, concept: HARNAIS }, psn: '4611' });
  verifier('le PSN corrigé : THS attend le robot aussi', r3.corrige === true && r3.actifs.filter(x => x.id === 'THS')[0].suivi.niveau === 'attente');
  const r4 = ctx.adminEnregistrerContrat({ id: 'HDK Tranche 2', nomGates: 'HDK', colonnes: { fwd: ELEC, concept: HARNAIS } });
  verifier('une fiche sans erreur à corriger : corrige faux', r4.corrige === false);
  ctx.importRapport(j, { source: 'fenetre', contrats: [{ contrat: 'HDK', gates: { ok: false, code: 'colonne-elec', message: 'Toujours pas là.' } }] });
  const apres = ctx.adminContrats().actifs.filter(x => x.id === 'HDK')[0];
  verifier('le passage suivant dit à nouveau ce qu’il voit (« corrigeLe » effacé)', apres.suivi.niveau === 'erreur' && apres.suivi.lignes[0] === 'Toujours pas là.' &&
    !('corrigeLe' in prop('SUIVI_FWD_RAPPORTS').contrats.HDK.gates), JSON.stringify(apres.suivi));
}

section('Relu : la ligne du robot et celle d’un contrat ne se contredisent pas');
{
  const { ctx, prop } = monde();
  const j = ctx.ouvrirJetonImport_();
  ctx.importRapport(j, { source: 'fenetre', contrats: [{ contrat: 'HDK', gates: { ok: true } }, { contrat: 'HDK Tranche 2', gates: { ok: true } }, { contrat: 'THS', gates: { ok: true } }] });
  ctx.importRapport(j, { source: 'robot', passage: { ok: true, heure: '14:00' }, contrats: [] });
  const r = prop('SUIVI_FWD_RAPPORTS'), vieux = new Date(Date.now() - 9 * 864e5).toISOString();
  r.contrats['HDK Tranche 2'].gates.dernierOk = vieux;
  ctx.__proprietes.SUIVI_FWD_RAPPORTS = JSON.stringify(r);
  const a = ctx.adminContrats(), t2 = a.actifs.filter(x => x.id === 'HDK Tranche 2')[0];
  verifier('le robot est passé aujourd’hui, la tranche 2 rien depuis 9 jours : on ne demande pas si le PC est allumé',
    t2.suivi.niveau === 'attention' && /^Pas mis à jour depuis 9 jours \(dernière fois le \d\d\/\d\d à \d+ h \d\d\), alors que le robot est passé aujourd’hui à \d+ h \d\d sans rien en dire : vérifiez sa fiche, d’abord le nom exact de sa tranche dans GATES\.$/.test(t2.suivi.lignes[0]) &&
    !/PC/.test(t2.suivi.lignes[0]), JSON.stringify(t2.suivi));
  verifier('… et la ligne du robot ne dit pas « tout s’est bien passé » : « 1 contrat à vérifier, ci-dessous. »',
    a.robot.niveau === 'attention' && /: 1 contrat à vérifier, ci-dessous\.$/.test(a.robot.texte), a.robot.texte);
}

// =================================================================
/* Débrief 33 (relu) — juste après la livraison, la fiche de VRK restait en
   rouge avec « 280 de ses 546 plans sont déjà dans « THS » … », le refus
   d'une règle qui n'existe plus, et le bouton « Corriger la fiche » :
   Nathan aurait cru que rien n'était réglé. */
section('Débrief 33 (relu) : l’ancien refus « … plans sont déjà dans « THS » » ne reste pas en rouge');
{
  const { ctx } = monde();
  ctx.adminEnregistrerContrat({ id: '', nom: 'VRK', nomGates: 'VRK AA', colonnes: { fwd: 'VRK AA 011 > Avancement Définition Electrique', concept: '' }, psn: '4540' });
  const j = ctx.ouvrirJetonImport_();
  ctx.importRapport(j, { source: 'robot', passage: { ok: true, heure: '14:00' }, contrats: [
    { contrat: 'VRK', gates: { ok: false, code: 'douteux', message: '280 de ses 546 plans sont déjà dans « THS » : est-ce l’export de « THS » ? Il irait alors dans sa case, « GATES THS ».' } }] });
  const vrk = ctx.adminContrats().prevus.filter(x => x.id === 'VRK')[0];
  verifier('VRK prévu, avec l’ancien refus gardé : « Prévu : son onglet sera créé au prochain passage du robot… », en attente (pas en rouge, pas de « Corriger la fiche »), et une ligne dit que ce refus ne compte plus',
    vrk && vrk.suivi.niveau === 'attente' && vrk.suivi.lignes[0] === 'Prévu : son onglet sera créé au prochain passage du robot, avec son premier export GATES.' &&
    vrk.suivi.lignes[1] === 'L’ancien refus ne compte plus : ses plans en commun avec « THS » ne bloquent plus l’import.' && vrk.suivi.lignes.length === 2,
    JSON.stringify(vrk && vrk.suivi));
  /* Le doute d'aujourd'hui, lui (l'export d'un autre contrat dans la case de VRK), reste dit. */
  ctx.importRapport(j, { source: 'robot', passage: { ok: true, heure: '14:00' }, contrats: [
    { contrat: 'VRK', gates: { ok: false, code: 'douteux', message: 'Les plans de ce fichier sont ceux de « THS » (180 sur 180) : est-ce l’export de « THS » ? Il irait alors dans sa case, « GATES THS ».' } }] });
  const vrk2 = ctx.adminContrats().prevus.filter(x => x.id === 'VRK')[0];
  verifier('un doute de la règle d’aujourd’hui (« Les plans de ce fichier sont ceux de « THS » ») reste en rouge, tel quel',
    vrk2 && vrk2.suivi.niveau === 'erreur' && /^Les plans de ce fichier sont ceux de « THS »/.test(vrk2.suivi.lignes[0]), JSON.stringify(vrk2 && vrk2.suivi));
}

// =================================================================
/* Débrief 31 — Nathan : « Comment je gère les tranches ? […] j'ai
   l'impression que c'est que par contrat. » Une tranche s'ajoute depuis la
   ligne de son contrat (« + Ajouter une tranche ») : les droits se lisent
   sur le NOUVEAU nom (peutGerer_), le responsable, les administrateurs de
   tous les contrats et ceux de ce contrat l'ajoutent ; une nouvelle famille
   reste au responsable et aux administrateurs de tous. */
section('Débrief 31 : ajouter une tranche, et qui le peut');
{
  const { c, ctx, comme, prop } = monde();
  const famillesDe = email => comme(email, () => ctx.adminContrats().familles);
  const fN = famillesDe('nathan@airbus.com'), fA = famillesDe('anne@airbus.com');
  const parNom = (l, n) => l.filter(f => f.contrat === n)[0] || {};
  verifier('adminContrats().familles : une entrée par contrat, dans l’ordre des lignes — HDK (2 tranches, propose « Tranche 3 »), THS (« Tranche 2 »), VIEUX (masqué)',
    fN.map(f => f.contrat).join() === 'HDK,THS,VIEUX' && parNom(fN, 'HDK').tranches === 2 && parNom(fN, 'HDK').prochaine === 'Tranche 3' &&
    parNom(fN, 'THS').prochaine === 'Tranche 2' && fN.every(f => f.ajoutTranche === true), JSON.stringify(fN));
  verifier('pour Anne (administratrice de THS) : « + Ajouter une tranche » sur THS seulement',
    parNom(fA, 'THS').ajoutTranche === true && parNom(fA, 'HDK').ajoutTranche === false && parNom(fA, 'VIEUX').ajoutTranche === false, JSON.stringify(fA));
  const t2 = { id: '', famille: 'THS', nom: 'THS Tranche 2', nomGates: 'THS AB', colonnes: { fwd: ELEC, concept: '' } };
  const r = comme('anne@airbus.com', () => ctx.adminEnregistrerContrat(t2));
  const p = r.prevus.filter(x => x.id === 'THS Tranche 2')[0];
  verifier('Anne ajoute « THS Tranche 2 » : prévue, rangée sous THS (contrat THS, Tranche 2), son nom GATES gardé ; elle peut la modifier et la retirer',
    r.enregistre === 'THS Tranche 2' && !!p && p.prevu && p.contrat === 'THS' && p.tranche === 'Tranche 2' && p.modifiable && p.retirable && !p.gerable &&
    prop('SUIVI_FWD_FICHES')['THS Tranche 2'].nomGates === 'THS AB' && prop('SUIVI_FWD_FICHES')['THS Tranche 2'].par === 'anne@airbus.com', JSON.stringify(p));
  const journal = JSON.parse(ctx.__proprietes[vm.runInContext('CLE_JOURNAL_ADMIN', ctx)] || '[]');
  verifier('le journal de l’administration le dit : « tranche ajoutée : THS Tranche 2 (GATES « THS AB ») », par Anne',
    !!journal[0] && journal[0].quoi === 'tranche ajoutée : THS Tranche 2 (GATES « THS AB »)' && journal[0].qui === 'anne@airbus.com', JSON.stringify(journal[0]));
  verifier('… et la tranche suivante proposée devient « Tranche 3 »', parNom(famillesDe('anne@airbus.com'), 'THS').prochaine === 'Tranche 3' &&
    parNom(famillesDe('anne@airbus.com'), 'THS').tranches === 2);
  const refusHdk = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: '', famille: 'HDK', nom: 'HDK Tranche 3', nomGates: 'HDK AC', colonnes: { fwd: ELEC } })));
  verifier('Anne n’ajoute pas de tranche à HDK : « [droits] Réservé au responsable et aux administrateurs de HDK ou de tous les contrats »',
    /^\[droits\] Réservé au responsable et aux administrateurs de HDK ou de tous les contrats : votre compte \(anne@airbus\.com\) n’a pas ce droit\./.test(refusHdk) &&
    !prop('SUIVI_FWD_FICHES')['HDK Tranche 3'], refusHdk);
  const refusCache = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: '', nom: 'HDK Tranche 3', nomGates: 'HDK AC', colonnes: { fwd: ELEC } })));
  verifier('ni en tapant « HDK Tranche 3 » sans passer par la ligne de HDK : les droits se lisent sur le nouveau nom',
    /^\[droits\] Réservé au responsable et aux administrateurs de HDK ou de tous les contrats/.test(refusCache) && !prop('SUIVI_FWD_FICHES')['HDK Tranche 3'], refusCache);
  const ruse = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: '', famille: 'THS', nom: 'HDK Tranche 3', nomGates: 'HDK AC', colonnes: { fwd: ELEC } })));
  verifier('ni en disant « THS » pour un nom de HDK : refusé sous le champ Tranche, rien d’écrit',
    ruse === '[tranche] Écrivez la tranche comme « Tranche 2 » ou « Tranche B » : elle se range alors sous THS.' && !prop('SUIVI_FWD_FICHES')['HDK Tranche 3'], ruse);
  const famille = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: '', nom: 'ZED', nomGates: 'ZED', colonnes: { fwd: ELEC } })));
  verifier('une nouvelle famille reste au responsable et aux administrateurs de tous : « Réservé au responsable et aux administrateurs de tous les contrats »',
    /^\[droits\] Réservé au responsable et aux administrateurs de tous les contrats : /.test(famille), famille);
  const sansTranche = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: '', famille: 'THS', nom: 'THS', nomGates: 'THS AC', colonnes: { fwd: ELEC } })));
  verifier('« + Ajouter une tranche » sans tranche lisible : « [tranche] Écrivez la tranche comme « Tranche 2 »… »', /^\[tranche\] Écrivez la tranche comme/.test(sansTranche), sansTranche);
  const lea = erreurDe(() => comme('lea@airbus.com', () => ctx.adminEnregistrerContrat({ id: '', famille: 'THS', nom: 'THS Tranche 3', nomGates: 'THS AC', colonnes: { fwd: ELEC } })));
  verifier('une lectrice n’ajoute pas de tranche', /^\[droits\] Réservé au responsable et aux administrateurs de THS ou de tous les contrats : votre compte \(lea@airbus\.com\)/.test(lea), lea);
  const doublon = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat(t2)));
  verifier('la même tranche deux fois : « [nom] Le contrat « THS Tranche 2 » est déjà prévu : modifiez sa fiche. » (la page le pose sous Tranche)',
    doublon === '[nom] Le contrat « THS Tranche 2 » est déjà prévu : modifiez sa fiche.', doublon);
  const sansGates = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: '', famille: 'THS', nom: 'THS Tranche 3', nomGates: '', colonnes: { fwd: ELEC } })));
  verifier('le nom GATES d’une nouvelle tranche est obligatoire', /^\[nomGates\] Donnez le nom exact de la tranche dans GATES/.test(sansGates), sansGates);
  const paul = comme('paul@airbus.com', () => ctx.adminEnregistrerContrat({ id: '', famille: 'HDK', nom: 'HDK Tranche B', nomGates: 'HDK AB', colonnes: { fwd: ELEC } }));
  verifier('Paul (tous les contrats) ajoute « HDK Tranche B » : une tranche peut porter une lettre', paul.enregistre === 'HDK Tranche B' &&
    paul.prevus.some(x => x.id === 'HDK Tranche B' && x.contrat === 'HDK' && x.tranche === 'Tranche B'), JSON.stringify(paul.prevus.map(x => [x.id, x.contrat, x.tranche])));
  const nathan = ctx.adminEnregistrerContrat({ id: '', nom: 'THS Tranche 3', nomGates: 'THS AC', colonnes: { fwd: ELEC } });
  verifier('« THS Tranche 3 » tapé dans « + Ajouter un contrat » (Nathan) marche toujours, et se range sous THS',
    nathan.prevus.some(x => x.id === 'THS Tranche 3' && x.contrat === 'THS' && x.tranche === 'Tranche 3'), JSON.stringify(nathan.prevus.map(x => x.id)));
  /* Retirer : qui peut ajouter une tranche peut la retirer tant qu'elle est prévue. */
  const vrk = ctx.adminEnregistrerContrat({ id: '', nom: 'VRK', nomGates: 'VRK', colonnes: { fwd: ELEC } });
  const vueAnne = comme('anne@airbus.com', () => ctx.adminContrats());
  const ligne = id => vueAnne.prevus.filter(x => x.id === id)[0] || {};
  verifier('pour Anne : « Retirer » sur les tranches prévues de THS, pas sur celle de HDK ni sur le contrat prévu VRK',
    !!vrk && ligne('THS Tranche 2').retirable === true && ligne('THS Tranche 3').retirable === true && ligne('HDK Tranche B').retirable === false && ligne('VRK').retirable === false,
    JSON.stringify(vueAnne.prevus.map(x => [x.id, x.retirable])));
  const refusVrk = erreurDe(() => comme('anne@airbus.com', () => ctx.adminRetirerContratPrevu('VRK')));
  const refusB = erreurDe(() => comme('anne@airbus.com', () => ctx.adminRetirerContratPrevu('HDK Tranche B')));
  verifier('Anne ne retire ni VRK ni « HDK Tranche B » (refus en clair)',
    /^\[droits\] Réservé au responsable et aux administrateurs de tous les contrats/.test(refusVrk) &&
    /^\[droits\] Réservé au responsable et aux administrateurs de HDK ou de tous les contrats/.test(refusB), JSON.stringify([refusVrk, refusB]));
  const retrait = comme('anne@airbus.com', () => ctx.adminRetirerContratPrevu('THS Tranche 3'));
  const roles = prop('SUIVI_FWD_ROLES').admins.filter(a => a.email === 'anne@airbus.com')[0];
  verifier('Anne retire « THS Tranche 3 » : partie, ses droits sur THS intacts', !retrait.prevus.some(x => x.id === 'THS Tranche 3') && !prop('SUIVI_FWD_FICHES')['THS Tranche 3'] &&
    !!roles && roles.contrats.join() === 'THS' && !retrait.messageDroits, JSON.stringify([roles, retrait.messageDroits]));
  /* La famille seule de prévus : une tranche de VRK s'ajoute aussi (le nom de famille tient de ses prévus). */
  ctx.adminEnregistrerAdmins([{ email: 'anne@airbus.com', contrats: ['THS'] }, { email: 'paul@airbus.com', contrats: [] }, { email: 'zoe@airbus.com', contrats: ['VRK'] }]);
  const zoe = comme('zoe@airbus.com', () => ctx.adminEnregistrerContrat({ id: '', famille: 'VRK', nom: 'VRK Tranche 2', nomGates: 'VRK B', colonnes: { fwd: ELEC } }));
  verifier('Zoé (VRK, encore prévu) ajoute « VRK Tranche 2 »', zoe.prevus.some(x => x.id === 'VRK Tranche 2' && x.contrat === 'VRK'), JSON.stringify(zoe.prevus.map(x => x.id)));
  const fini = c.getSheetByName('VIEUX') ? true : false;
  verifier('un contrat masqué garde sa ligne de famille (« VIEUX ») : on peut lui ajouter une tranche', fini && parNom(famillesDe('nathan@airbus.com'), 'VIEUX').ajoutTranche === true);
}

/* Débrief 31 (relu) — trois relecteurs : une tranche écrite autrement
   (« THS Tranche2 », « THS Tranche 02 ») passait pour une autre ; « Tranche 1 »
   s'ajoutait (et le contrat devenait « Tranche principale ») ; une
   administratrice de THS, en retirant une tranche prévue confiée à Bob, lui
   ôtait ses droits sans que le responsable le voie ; une tranche prévue
   renommée dans une autre famille donnait des droits à l'administratrice de
   l'ancienne famille. */
section('Débrief 31 (relu) : la même tranche écrite autrement, la tranche 1, les droits des autres administrateurs');
{
  const { ctx, comme, prop } = monde();
  const journal = () => JSON.parse(ctx.__proprietes[vm.runInContext('CLE_JOURNAL_ADMIN', ctx)] || '[]');
  const tranche = (famille, nom, gates) => ({ id: '', famille: famille, nom: nom, nomGates: gates, colonnes: { fwd: ELEC, concept: '' } });
  ctx.adminEnregistrerContrat(tranche('THS', 'THS Tranche 2', 'THS AB'));
  const colle = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat(tranche('THS', 'THS Tranche2', 'THS AX'))));
  const zero = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat(tranche('THS', 'THS Tranche 02', 'THS AX'))));
  const onglet = erreurDe(() => ctx.adminEnregistrerContrat(tranche('HDK', 'HDK - tranche 02', 'HDK AX')));
  verifier('« THS Tranche2 » et « THS Tranche 02 » sont la tranche 2 déjà prévue ; « HDK - tranche 02 », celle de HDK déjà là : refusées (« [nom] … serait la même tranche que … »), rien d’écrit',
    colle === '[nom] « THS Tranche2 » serait la même tranche que « THS Tranche 2 » : modifiez sa fiche plutôt que d’en ajouter une.' &&
    zero === '[nom] « THS Tranche 02 » serait la même tranche que « THS Tranche 2 » : modifiez sa fiche plutôt que d’en ajouter une.' &&
    onglet === '[nom] « HDK - tranche 02 » serait la même tranche que « HDK Tranche 2 » : modifiez sa fiche plutôt que d’en ajouter une.' &&
    !prop('SUIVI_FWD_FICHES')['THS Tranche2'] && !prop('SUIVI_FWD_FICHES')['THS Tranche 02'], JSON.stringify([colle, zero, onglet]));
  const vingt = ctx.adminEnregistrerContrat(tranche('THS', 'THS Tranche 20', 'THS AT'));
  verifier('… mais « THS Tranche 20 » est une autre tranche (seuls les zéros de tête comptent pour rien)', vingt.enregistre === 'THS Tranche 20', vingt.enregistre);
  const un = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat(tranche('THS', 'THS Tranche 1', 'THS AX'))));
  const zeroUn = erreurDe(() => ctx.adminEnregistrerContrat(tranche('HDK', 'HDK Tranche 01', 'HDK AX')));
  const nul = erreurDe(() => ctx.adminEnregistrerContrat({ id: '', nom: 'THS Tranche 0', nomGates: 'THS AX', colonnes: { fwd: ELEC } }));
  verifier('« Tranche 1 » (ou « 01 », « 0 ») d’un contrat qui existe : c’est le contrat lui-même — refusée, la suivante proposée',
    un === '[nom] « Tranche 1 », c’est THS lui-même : la suivante est « Tranche 21 ».' && zeroUn === '[nom] « Tranche 01 », c’est HDK lui-même : la suivante est « Tranche 3 ».' &&
    nul === '[nom] « Tranche 0 », c’est THS lui-même : la suivante est « Tranche 21 ».' && !prop('SUIVI_FWD_FICHES')['THS Tranche 1'], JSON.stringify([un, zeroUn, nul]));
  ctx.adminRetirerContratPrevu('THS Tranche 20');
  const neo = ctx.adminEnregistrerContrat({ id: '', nom: 'NEO Tranche 2', nomGates: 'NEO AB', colonnes: { fwd: ELEC } });
  const neo1 = ctx.adminEnregistrerContrat(tranche('NEO', 'NEO Tranche 1', 'NEO AA'));
  verifier('une famille qui n’a que des tranches (pas de contrat « NEO ») : « NEO Tranche 1 » s’ajoute', neo.enregistre === 'NEO Tranche 2' && neo1.enregistre === 'NEO Tranche 1', neo1.enregistre);

  /* Bob : administrateur de « THS Tranche 2 » seule. */
  ctx.adminEnregistrerAdmins([{ email: 'anne@airbus.com', contrats: ['THS'] }, { email: 'paul@airbus.com', contrats: [] }, { email: 'bob@airbus.com', contrats: ['THS Tranche 2'] }]);
  const vueAnne = comme('anne@airbus.com', () => ctx.adminContrats()).prevus.filter(x => x.id === 'THS Tranche 2')[0] || {};
  const refus = erreurDe(() => comme('anne@airbus.com', () => ctx.adminRetirerContratPrevu('THS Tranche 2')));
  const bob = () => prop('SUIVI_FWD_ROLES').admins.filter(a => a.email === 'bob@airbus.com')[0];
  verifier('Anne (THS) ne retire pas « THS Tranche 2 » confiée à Bob : pas de « Retirer » pour elle, et l’appel forgé est refusé en clair ; rien n’a changé',
    vueAnne.retirable === false && vueAnne.modifiable === true &&
    refus === '[droits] « THS Tranche 2 » est confiée à bob@airbus.com : seuls le responsable et les administrateurs de tous les contrats peuvent la retirer. Rien n’a été changé.' &&
    !!prop('SUIVI_FWD_FICHES')['THS Tranche 2'] && !!bob() && bob().contrats.join() === 'THS Tranche 2', JSON.stringify([vueAnne.retirable, refus, bob()]));
  /* Un prévu renommé dans une autre famille : les droits suivent qui le NOMMAIT (Bob), pas qui le couvrait par sa famille (Anne). */
  const avantRenom = journal().length;
  const renomme = ctx.adminEnregistrerContrat({ id: 'THS Tranche 2', nom: 'HDK Tranche 3', nomGates: 'HDK AC', colonnes: { fwd: ELEC, concept: '' } });
  const anne = prop('SUIVI_FWD_ROLES').admins.filter(a => a.email === 'anne@airbus.com')[0];
  const lignesRenom = journal().slice(0, journal().length - avantRenom).map(j => j.quoi);
  const modifAnne = erreurDe(() => comme('anne@airbus.com', () => ctx.adminEnregistrerContrat({ id: 'HDK Tranche 3', nomGates: 'HDK AD', colonnes: { fwd: ELEC } })));
  verifier('« THS Tranche 2 » renommée « HDK Tranche 3 » : Bob la suit, Anne garde THS seul (rien sur HDK : elle ne peut ni la modifier ni la retirer) ; le journal dit le changement de Bob',
    renomme.enregistre === 'HDK Tranche 3' && renomme.messageDroits === 'Les droits de bob@airbus.com suivent le nouveau nom.' &&
    bob().contrats.join() === 'HDK Tranche 3' && anne.contrats.join() === 'THS' &&
    lignesRenom.indexOf('droits de bob@airbus.com : THS Tranche 2 → HDK Tranche 3') !== -1 &&
    /^\[droits\] Réservé aux administrateurs de HDK Tranche 3/.test(modifAnne), JSON.stringify([renomme.messageDroits, bob(), anne, lignesRenom, modifAnne]));
  /* Le responsable la retire : Bob perd ses droits — c'est dit, et noté au journal. */
  const avantRetrait = journal().length;
  const retrait = ctx.adminRetirerContratPrevu('HDK Tranche 3');
  const lignesRetrait = journal().slice(0, journal().length - avantRetrait).map(j => j.quoi);
  verifier('Nathan retire « HDK Tranche 3 » : « bob@airbus.com n’avait que ce contrat : plus de droits d’administration. » — et le journal le note',
    retrait.messageDroits === 'bob@airbus.com n’avait que ce contrat : plus de droits d’administration.' && !bob() &&
    lignesRetrait.join(' | ') === 'droits retirés : bob@airbus.com (n’avait que HDK Tranche 3) | contrat prévu retiré : HDK Tranche 3', JSON.stringify([retrait.messageDroits, lignesRetrait]));
  /* Ses propres droits ne retiennent pas Anne : une tranche qu'elle était seule à nommer, elle la retire. */
  ctx.adminEnregistrerContrat(tranche('THS', 'THS Tranche 3', 'THS AC'));
  ctx.adminEnregistrerAdmins([{ email: 'anne@airbus.com', contrats: ['THS', 'THS Tranche 3'] }, { email: 'paul@airbus.com', contrats: [] }]);
  const sienne = comme('anne@airbus.com', () => ctx.adminRetirerContratPrevu('THS Tranche 3'));
  verifier('… Anne retire une tranche qu’elle seule nommait : retirée, elle garde THS',
    !sienne.prevus.some(x => x.id === 'THS Tranche 3') && prop('SUIVI_FWD_ROLES').admins.filter(a => a.email === 'anne@airbus.com')[0].contrats.join() === 'THS',
    JSON.stringify(prop('SUIVI_FWD_ROLES')));
}

section('Débrief 31 : un seul onglet suivi (CONFIG.FEUILLE_DONNEES) — pas de tranche à ajouter');
{
  const { ctx } = monde();
  vm.runInContext("CONFIG.FEUILLE_DONNEES = 'HDK';", ctx);
  const f = ctx.adminContrats().familles;
  verifier('aucune famille ne propose « + Ajouter une tranche »', f.every(x => x.ajoutTranche === false), JSON.stringify(f));
}

// =================================================================
/* Débrief 31 — « semaine par semaine s'arrête à S42, le graphique a S44 » :
   chaque chemin d'archivage garde la carte plan par plan (sans elle, le
   journal ne peut rien dire de la semaine), et réimporter dans la même
   semaine remplace son relevé. */
section('Débrief 31 : chaque archivage garde le détail plan par plan ; la même semaine se remplace');
{
  const { c, ctx } = monde();
  vm.runInContext("CONFIG.DEPOT = CONFIG.DEPOT || {}; CONFIG.DEPOT.SECRET = 'phrase longue et imprévisible';", ctx);
  const releves = id => ctx.getHistorique(c, id);
  const derniere = id => { const r = releves(id); return r[r.length - 1]; };
  const nbRefs = r => r && r.plans && typeof r.plans === 'object' ? Object.keys(r.plans).length : 0;
  /* 1. La fenêtre d'import (le robot, chaque jour à 14 h, case « Archiver » laissée cochée). */
  const j = ctx.ouvrirJetonImport_();
  const a = ctx.importArchiverReleve(j, 'HDK', false);
  verifier('la fenêtre d’import (le robot) : relevé de la semaine archivé AVEC sa carte plan par plan (40 plans)', a.ok === true && nbRefs(derniere('HDK')) === 40, JSON.stringify(a));
  const b = ctx.importArchiverReleve(ctx.ouvrirJetonImport_(), 'HDK', false);
  verifier('le lendemain, même semaine : la ligne de la semaine est remplacée, pas doublée', b.ok === true && releves('HDK').length === 1 &&
    c.getSheetByName('Historique_FWD_HDK').getLastRow() === 2, JSON.stringify([b, releves('HDK').length]));
  /* 2. L'archivage du vendredi (et le menu). */
  ctx.enregistrerInstantaneHebdo();
  verifier('l’archivage du vendredi : chaque contrat a sa carte (HDK 40, HDK Tranche 2 20, THS 30)', nbRefs(derniere('HDK')) === 40 && nbRefs(derniere('HDK Tranche 2')) === 20 &&
    nbRefs(derniere('THS')) === 30 && releves('HDK').length === 1, JSON.stringify(['HDK', 'HDK Tranche 2', 'THS'].map(x => nbRefs(derniere(x)))));
  /* 3. Le dépôt automatique (doPost). */
  const g = gates(25, 'DEP');
  const rep = ctx.deposer_(JSON.stringify({ secret: 'phrase longue et imprévisible', onglet: 'THS', lignes: g.valeurs.map(l => l.map(String)), archiver: true }));
  verifier('le dépôt automatique (« archiver ») : la carte du nouvel export (25 plans) remplace celle de la semaine', rep.ok === true && nbRefs(derniere('THS')) === 25 &&
    releves('THS').length === 1, JSON.stringify(rep).slice(0, 300));
  /* 4. Rattraper une semaine passée (menu). */
  const sem = ctx.numeroSemaineISO(new Date(Date.now() - 14 * 864e5));
  const rp = ctx.archiverPourSemaine_(c, 'HDK Tranche 2', sem);
  verifier('rattraper une semaine passée : son relevé a aussi sa carte', rp.ok === true && nbRefs(releves('HDK Tranche 2').filter(r => r.semaine === sem)[0]) === 20, JSON.stringify(rp));
}

section('Débrief 31 : la fenêtre d’import dit au robot quelle livraison il voit');
{
  const { c, ctx } = monde();
  const html = ctx.pageImportSecondeBase(ctx.parametresImport_(c));
  const edition = vm.runInContext('EDITION', ctx);
  verifier('#pont-robot porte data-livraison="' + edition + '" (lu par le robot : getAttribute(\'data-livraison\'))',
    new RegExp('<div id="pont-robot" hidden data-etat="" data-livraison="' + edition + '">').test(html) && /^[0-9a-f]{7,}$/.test(edition), html.slice(html.indexOf('pont-robot') - 10, html.indexOf('pont-robot') + 90));
}

/* Débrief 31 — Nathan crée un nouveau déploiement (un nouveau lien /exec) à
   chaque livraison : son robot gardait l'ancien lien et voyait une ancienne
   version. Le compte rendu du robot dit la livraison qu'il a lue sur le pont
   (« livraison ») ; adminContrats le dit quand ce n'est pas celle-ci. */
section('Débrief 31 : la livraison que regarde le robot, vue du site');
{
  const { ctx, prop } = monde();
  const edition = vm.runInContext('EDITION', ctx);
  const j = ctx.ouvrirJetonImport_();
  const passage = { ok: true, message: '', heure: '14:00' };
  ctx.importRapport(j, { source: 'robot', passage: passage, contrats: [] });
  let a = ctx.adminContrats();
  verifier('un compte rendu sans « livraison » (un robot d’avant) : rien n’est dit, rien n’est gardé',
    !a.robot.livraison && prop('SUIVI_FWD_RAPPORTS').robot.livraison === undefined, JSON.stringify([a.robot, prop('SUIVI_FWD_RAPPORTS').robot]));
  ctx.importRapport(j, { source: 'robot', livraison: edition, passage: passage, contrats: [] });
  a = ctx.adminContrats();
  verifier('le robot regarde cette livraison-ci (« ' + edition + ' ») : gardée avec la ligne du robot, rien à dire',
    prop('SUIVI_FWD_RAPPORTS').robot.livraison === edition && !a.robot.livraison && a.robot.niveau === 'ok', JSON.stringify(a.robot));
  ctx.importRapport(j, { source: 'robot', livraison: '1a2b3c4', passage: passage, contrats: [] });
  a = ctx.adminContrats();
  /* Débrief 31 (relu) : le raccourci que le robot nomme lui-même, « Changer
     l'adresse du tableau de bord », et plus « 1 - Preparer » (« une seule
     fois », il refait les connexions) — les deux disaient deux chemins. */
  const attendu = 'Le robot regarde une autre version du site (livraison 1a2b3c4 ; celle-ci : ' + edition + '). ' +
    'Donnez-lui le lien qui suit toujours la dernière version : dans Apps Script, Déployer → Tester les déploiements, ' +
    'copiez le lien qui finit par /dev ; puis, sur le PC du robot, double-cliquez « Changer l’adresse du tableau de bord » et collez-y ce lien.';
  verifier('une autre livraison (« 1a2b3c4 ») : robot.livraison = { niveau « attention », texte en clair : les deux livraisons, le lien /dev, « Changer l’adresse du tableau de bord » } ; la ligne du robot elle-même ne change pas',
    !!a.robot.livraison && a.robot.livraison.niveau === 'attention' && a.robot.livraison.texte === attendu && a.robot.niveau === 'ok' &&
    /tout s’est bien passé\.$/.test(a.robot.texte) && prop('SUIVI_FWD_RAPPORTS').robot.livraison === '1a2b3c4', JSON.stringify(a.robot));
  ctx.importRapport(j, { source: 'robot', passage: passage, contrats: [] });
  verifier('le passage suivant, sans « livraison » : la ligne du robot est refaite, plus rien n’est dit',
    !ctx.adminContrats().robot.livraison && prop('SUIVI_FWD_RAPPORTS').robot.livraison === undefined, JSON.stringify(prop('SUIVI_FWD_RAPPORTS').robot));
  /* Ce qui n'est pas un court mot lisible est ignoré. */
  const essais = ['x'.repeat(21), 42, { v: 'a' }, '', '   ', 'ab<cd>', 'a b', '-abc', null];
  const lus = essais.map(v => { ctx.importRapport(j, { source: 'robot', livraison: v, passage: passage, contrats: [] }); return prop('SUIVI_FWD_RAPPORTS').robot.livraison; });
  verifier('ignorées : plus de 20 caractères, un nombre, un objet, du vide, des chevrons, des espaces, un tiret en tête — rien de gardé, rien de dit',
    lus.every(x => x === undefined) && !ctx.adminContrats().robot.livraison, JSON.stringify(lus));
  ctx.importRapport(j, { source: 'robot', livraison: '  0123456789abcdefghij  ', passage: passage, contrats: [] });
  verifier('20 caractères tout juste (espaces autour ôtés) : gardée', prop('SUIVI_FWD_RAPPORTS').robot.livraison === '0123456789abcdefghij', JSON.stringify(prop('SUIVI_FWD_RAPPORTS').robot));
  ctx.importRapport(j, { source: 'fenetre', livraison: 'fff0000', contrats: [] });
  verifier('la fenêtre d’import (source « fenetre ») ne pose pas de livraison', prop('SUIVI_FWD_RAPPORTS').robot.livraison === '0123456789abcdefghij');
  ctx.importRapport(j, { source: 'robot', livraison: 'beef123', contrats: [{ contrat: 'HDK', gates: { tape: 'HDK' } }] });
  verifier('un compte rendu du robot sans « passage » met à jour la livraison de la ligne du robot, sans toucher au reste',
    prop('SUIVI_FWD_RAPPORTS').robot.livraison === 'beef123' && prop('SUIVI_FWD_RAPPORTS').robot.heure === '14:00' &&
    /\(livraison beef123 ; celle-ci : /.test(ctx.adminContrats().robot.livraison.texte), JSON.stringify(prop('SUIVI_FWD_RAPPORTS').robot));
  /* Débrief 31 (relu) : sur le lien /dev, le robot lit toujours le dernier
     code enregistré — juste après une livraison, il ne l'a pas encore lue :
     le site ne lui demande pas de changer de lien (en attente, rien à faire). */
  ctx.importRapport(j, { source: 'robot', livraison: 'cd9cd8e', adresse: 'dev', passage: passage, contrats: [] });
  a = ctx.adminContrats();
  verifier('le robot sur /dev a lu la livraison d’avant (« cd9cd8e ») : « adresse » gardée ; la ligne est « en attente », sans instruction — et dit que faire si elle reste',
    prop('SUIVI_FWD_RAPPORTS').robot.adresse === 'dev' && !!a.robot.livraison && a.robot.livraison.niveau === 'attente' &&
    a.robot.livraison.texte === 'À son dernier passage, le robot a lu la livraison cd9cd8e ; celle-ci est ' + edition + '. Rien à faire : il suit le lien /dev, ' +
      'qui montre toujours le dernier code enregistré, et lira la dernière livraison à son prochain passage. Si cette ligne reste après son passage, ' +
      'c’est ce lien-ci qui est ancien : ouvrez le tableau de bord par le lien de votre dernier déploiement.' &&
    !/Changer l’adresse|Tester les déploiements/.test(a.robot.livraison.texte), JSON.stringify([a.robot, prop('SUIVI_FWD_RAPPORTS').robot]));
  ctx.importRapport(j, { source: 'robot', livraison: edition, adresse: 'dev', passage: passage, contrats: [] });
  verifier('… et son passage suivant, sur cette livraison-ci : plus rien', !ctx.adminContrats().robot.livraison);
  ctx.importRapport(j, { source: 'robot', livraison: 'cd9cd8e', adresse: 'exec', passage: passage, contrats: [] });
  a = ctx.adminContrats();
  verifier('sur un lien /exec : l’avertissement, avec le lien /dev à donner', prop('SUIVI_FWD_RAPPORTS').robot.adresse === 'exec' &&
    a.robot.livraison.niveau === 'attention' && /double-cliquez « Changer l’adresse du tableau de bord »/.test(a.robot.livraison.texte), JSON.stringify(a.robot));
  const sortes = ['DEV', 'https://x/dev', 42, { a: 1 }, ''].map(v => {
    ctx.importRapport(j, { source: 'robot', livraison: 'cd9cd8e', adresse: v, passage: passage, contrats: [] });
    return [prop('SUIVI_FWD_RAPPORTS').robot.adresse, ctx.adminContrats().robot.livraison.niveau];
  });
  verifier('« adresse » : seuls « dev » et « exec » sont gardés ; autre chose (une adresse entière, un nombre…) est ignoré — l’avertissement reste',
    sortes.every(x => x[0] === undefined && x[1] === 'attention'), JSON.stringify(sortes));
  ctx.importRapport(j, { source: 'robot', livraison: 'cd9cd8e', adresse: 'dev', passage: passage, contrats: [] });
  ctx.importRapport(j, { source: 'robot', livraison: 'beef124', contrats: [] });
  verifier('un compte rendu sans « passage » ni « adresse » : l’adresse d’avant ne reste pas collée à une autre livraison',
    prop('SUIVI_FWD_RAPPORTS').robot.adresse === undefined && prop('SUIVI_FWD_RAPPORTS').robot.livraison === 'beef124' &&
    ctx.adminContrats().robot.livraison.niveau === 'attention', JSON.stringify(prop('SUIVI_FWD_RAPPORTS').robot));
  /* Le garde-fou de taille : 60 contrats aux messages de 500 caractères — la livraison reste. */
  const { ctx: ctx2, c: c2 } = monde();
  for (let i = 0; i < 60; i++) c2.feuilles.push(onglet('C' + i, gates(3, 'C' + i)));
  const long = 'm'.repeat(500);
  ctx2.importRapport(ctx2.ouvrirJetonImport_(), { source: 'robot', livraison: '9f8e7d6', passage: { ok: false, message: long }, contrats: Array.from({ length: 60 }, (_, i) =>
    ({ contrat: 'C' + i, gates: { ok: false, code: 'gates-export', message: long }, see: { ok: false, code: 'import', message: long } })) });
  const garde = ctx2.__proprietes.SUIVI_FWD_RAPPORTS;
  verifier('60 contrats aux messages de 500 caractères : toujours sous 8 500 octets, et la livraison du robot gardée',
    Buffer.byteLength(garde, 'utf8') <= 8500 && JSON.parse(garde).robot.livraison === '9f8e7d6' && !!ctx2.adminContrats().robot.livraison, Buffer.byteLength(garde, 'utf8') + ' octets');
}

// =================================================================
section('Débrief 33 : la page voit les contrats prévus — « en attente du robot »');
{
  /* Nathan : « je ne vois pas le contrat VRK dans Contrat […] Du moment que
     j'en crée un, pour moi, je devais le voir. » Le paquet de la page porte
     les prévus : [{ id, contrat, tranche }], le contrat nommé comme celui
     des contrats affichés. */
  const { c, ctx, prop } = monde();
  const marque = () => ctx.__proprietes.SUIVI_FWD_VERSION_DONNEES;
  let p = ctx.getDonneesPourClient();
  verifier('sans contrat prévu : « prevus » vide', p.ok && Array.isArray(p.prevus) && p.prevus.length === 0, JSON.stringify(p.prevus));
  let avant = marque();
  ctx.adminEnregistrerContrat({ id: '', nom: 'VRK', nomGates: 'VRK AA', colonnes: { fwd: 'VRK AA 011 > Avancement Définition Electrique', concept: '' }, psn: '4540' });
  verifier('ajouter un prévu rend le cache des paquets caduc (la marque des données change) : la prochaine ouverture le montre', marque() !== avant, String(marque()));
  ctx.adminEnregistrerContrat({ id: '', famille: 'THS', nom: 'THS Tranche 2', nomGates: 'THS AB', colonnes: { fwd: 'THS AA 011 > Avancement Définition Electrique', concept: '' } });
  /* Une tranche prévue d'un contrat masqué (VIEUX) : le tableau de bord ne montre pas VIEUX, ni elle. */
  ctx.adminEnregistrerContrat({ id: '', famille: 'VIEUX', nom: 'VIEUX Tranche 2', nomGates: 'VIEUX AB', colonnes: { fwd: 'VIEUX AB 011 > Avancement Définition Electrique', concept: '' } });
  p = ctx.getDonneesPourClient();
  verifier('le paquet de la page : la tranche prévue de THS rangée sous THS, puis VRK ; pas celle de VIEUX (masqué) ; rien d’autre que { id, contrat, tranche }',
    JSON.stringify(p.prevus) === JSON.stringify([{ id: 'THS Tranche 2', contrat: 'THS', tranche: 'Tranche 2' }, { id: 'VRK', contrat: 'VRK', tranche: '' }]) &&
    JSON.stringify(p.prevus).length < 120 && p.contrats.every(x => x.id !== 'VRK' && x.id !== 'THS Tranche 2'), JSON.stringify(p.prevus));
  const autre = ctx.getDonneesPourClient('THS');
  verifier('… le même dans le paquet de chaque contrat (THS demandé)', JSON.stringify(autre.prevus) === JSON.stringify(p.prevus), JSON.stringify(autre.prevus));
  const servi = JSON.parse(ctx.jsonDuPaquet_(ctx.paquetCompact_('')));
  verifier('… et dans le paquet servi à l’ouverture (compacté, mis en cache)', JSON.stringify(servi.prevus) === JSON.stringify(p.prevus), JSON.stringify(servi.prevus));
  avant = marque();
  ctx.adminEnregistrerContrat({ id: 'VRK', nom: 'VRK', nomGates: 'VRK AB', colonnes: { fwd: 'VRK AA 011 > Avancement Définition Electrique', concept: '' } });
  verifier('changer le nom GATES d’un prévu ne change rien pour la page : la marque des données reste', marque() === avant, String(marque()));
  ctx.adminEnregistrerContrat({ id: 'VRK', nom: 'VRX', nomGates: 'VRK AB', colonnes: { fwd: 'VRK AA 011 > Avancement Définition Electrique', concept: '' } });
  verifier('le renommer, si : la marque change, et le paquet dit son nouveau nom', marque() !== avant &&
    ctx.getDonneesPourClient().prevus.map(x => x.id).join() === 'THS Tranche 2,VRX', JSON.stringify(ctx.getDonneesPourClient().prevus));
  avant = marque();
  ctx.adminRetirerContratPrevu('VRX');
  verifier('le retirer aussi : la marque change, il quitte le paquet', marque() !== avant && ctx.getDonneesPourClient().prevus.map(x => x.id).join() === 'THS Tranche 2',
    JSON.stringify(ctx.getDonneesPourClient().prevus));
  /* Son premier export crée son onglet : ce n'est plus un prévu, c'est un contrat. */
  importerGates(ctx, { sorte: 'gates', contrat: 'THS Tranche 2', nouveau: true, prevu: true }, gates(12, 'TT2', 'THS'));
  p = ctx.getDonneesPourClient();
  verifier('le robot passé (l’onglet « THS Tranche 2 » créé) : elle quitte « prevus » et devient une tranche qu’on choisit',
    !!c.getSheetByName('THS Tranche 2') && p.prevus.length === 0 && p.contrats.some(x => x.id === 'THS Tranche 2' && x.contrat === 'THS' && x.tranche === 'Tranche 2'),
    JSON.stringify([p.prevus, p.contrats]));
  verifier('sa fiche le retient (« cree ») : elle ne redeviendra jamais « prévue »', typeof prop('SUIVI_FWD_FICHES')['THS Tranche 2'].cree === 'string');
}

console.log('\n═══════════════════════════════════════');
console.log(reussis + ' test(s) réussi(s), ' + echecs.length + ' échec(s)');
if (echecs.length) { console.log('\nÉchecs :'); echecs.forEach(e => console.log('  · ' + e)); }
process.exit(echecs.length ? 1 : 0);

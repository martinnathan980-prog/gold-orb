/* Débrief 30 : la VRAIE fenêtre d'import, servie au robot (import/tests_robot.py).

   Le robot ne connaît la fenêtre que par le navigateur : il la trouve dans
   un cadre d'une autre origine (chez Google, *.googleusercontent.com), y
   lit ses cases, y pose ses fichiers, clique « Importer », puis envoie son
   compte rendu par le pont (#pont-robot). Ce serveur rejoue cela sur la
   machine : la page du « tableau de bord » (http://127.0.0.1:PORT/exec)
   porte la fenêtre dans un cadre d'un autre site
   (http://localhost:PORT/googleusercontent/fenetre), rendue par le vrai
   Code.gs sur un classeur en mémoire ; google.script.run y répond par les
   vraies fonctions du serveur (POST /appel).

   Le classeur : HDK (40 plans, vraie structure GATES), et deux contrats
   ajoutés dans le tableau de bord, donc « prévus » : VRK (sa colonne ELEC
   est dans son export, PSN 4540) et NEO (sa colonne ELEC est mal écrite :
   la fenêtre la refuse dès la lecture). Les fichiers du jour sont écrits
   dans un dossier : l'export GATES de chacun et l'extract SEE.

     node tests/fenetre-pour-robot.js
       → écrit sur sa sortie « PRET <port> <json des fichiers> », puis sert
         jusqu'à ce qu'on le coupe.
     GET /etat : les onglets du classeur, les comptes rendus gardés
     (rapportsEnregistres_), les contrats encore prévus, les appels reçus. */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const { chargerServeur } = require('./build-addon');
const { Feuille, Classeur } = require('./faux-classeur');
const { feuilleGates, colonne } = require('./feuille-gates');
const { xlsx } = require('./fabriquer-xlsx');

/* Un export GATES (comme tests/import-see.js) : ses références et ses groupes au nom du contrat. */
const I_REF = colonne('Référence UD');
function gates(n, o) {
  o = o || {};
  const g = feuilleGates(n);
  const valeurs = g.valeurs.map(l => l.slice());
  valeurs.forEach((l, r) => { if (r >= 3 && o.prefixe) l[I_REF] = l[I_REF].replace(/^UD-/, o.prefixe + '-'); });
  if (o.groupe) valeurs[0] = valeurs[0].map(v => v.replace(/^HDK AA/, o.groupe + ' AA'));
  return { valeurs, fusions: g.fusions.map(f => Object.assign({}, f)) };
}
const xlsxGates = g => xlsx({ onglets: [{ nom: 'Export', lignes: g.valeurs, fusions: g.fusions.map(f => ({ ligne: f.ligne, col: f.col, larg: f.larg })) }] });
/* L'extract SEE de tous les porteurs (la forme de « Nommage WD BFLOW »). */
const ENTETE = ['NAME', 'SOL.', 'Cust.V', 'Int. V', 'ARCHIVE FILE PREFIX', 'VALIDITY PSN FULL', 'User Status', 'DIAGRAM TYPE', 'PRODUCT FAMILY', 'Validated'];
function extractSee(psnDe, n) {
  const lignes = [['Nommage WD BFLOW'], [], ENTETE];
  for (let i = 0; i < n; i++) {
    lignes.push(['TFE' + String(311 + (i % 50)) + 'A' + String(600 + i).padStart(4, '0'), String((i % 3) + 1).padStart(3, '0'), ['A', 'B', 'C'][i % 3],
      String(i % 4), 'WD' + (100000 + i), psnDe(i), 'Released', 'WD', 'HARNESS', { b: i % 2 === 0 }]);
  }
  return xlsx({ onglets: [{ nom: 'Nommage', lignes }] });
}

const classeur = new Classeur([new Feuille('HDK', gates(40).valeurs, false, gates(40).fusions)]);
classeur.proprietaire = 'nathan@airbus.com';
const ctx = chargerServeur(classeur, {});
ctx.__emailScript = ctx.__emailLecteur = 'nathan@airbus.com';
ctx.adminEnregistrerContrat({ id: '', nom: '', nomGates: 'VRK', colonnes: { fwd: 'VRK AA 011 > Avancement Définition Electrique', concept: '' }, psn: '4540' });
ctx.adminEnregistrerContrat({ id: '', nom: '', nomGates: 'NEO', colonnes: { fwd: 'NEO AA 011 > Avancement Definition Electrik', concept: '' } });

const dossier = fs.mkdtempSync(path.join(os.tmpdir(), 'fenetre-robot-'));
const fichiers = {
  HDK: path.join(dossier, 'gates-hdk.xlsx'), VRK: path.join(dossier, 'gates-vrk.xlsx'), NEO: path.join(dossier, 'gates-neo.xlsx'), SEE: path.join(dossier, 'see.xlsx')
};
fs.writeFileSync(fichiers.HDK, xlsxGates(gates(40)));
fs.writeFileSync(fichiers.VRK, xlsxGates(gates(25, { prefixe: 'VRK', groupe: 'VRK' })));
fs.writeFileSync(fichiers.NEO, xlsxGates(gates(15, { prefixe: 'NEO', groupe: 'NEO' })));
fs.writeFileSync(fichiers.SEE, extractSee(i => i < 20 ? '4530' : i < 35 ? '4540' : '4700', 40));

/* google.script.run, relié au serveur par POST /appel (le cadre est de la même origine que /appel). */
const DOUBLE = '<script>(function () {' +
  'function chaine(ok, ko) { return new Proxy({}, { get: function (_, nom) {' +
  '  if (nom === "withSuccessHandler") return function (f) { return chaine(f, ko); };' +
  '  if (nom === "withFailureHandler") return function (f) { return chaine(ok, f); };' +
  '  return function () { var args = Array.prototype.slice.call(arguments);' +
  '    fetch("/appel", { method: "POST", body: JSON.stringify({ nom: nom, args: args }) }).then(function (r) { return r.json(); })' +
  '      .then(function (r) { if (r.ok) { if (ok) ok(r.valeur); } else if (ko) ko({ message: r.message }); }, function (e) { if (ko) ko({ message: String(e) }); }); };' +
  '} }); }' +
  'window.google = { script: { run: chaine(null, null), host: { close: function () {} } } };' +
  '})();</script>';
const appels = [];
function fenetre() {
  ctx.__dialogue = null;
  ctx.importerSecondeBase();
  return ctx.__dialogue.getContent().replace('"maxLignesLot":20000', '"maxLignesLot":50').replace('"pausesReprise":[2000,6000]', '"pausesReprise":[30,60]')
    .replace('<head>', '<head>' + DOUBLE);
}

const serveur = http.createServer((req, res) => {
  const envoyer = (code, type, corps) => { res.writeHead(code, { 'Content-Type': type + '; charset=utf-8' }); res.end(corps); };
  const port = serveur.address().port;
  if (req.method === 'GET' && /^\/exec/.test(req.url)) {
    return envoyer(200, 'text/html', '<!doctype html><meta charset="utf-8"><title>Suivi FWD</title><body style="margin:0">' +
      '<iframe src="http://localhost:' + port + '/googleusercontent/fenetre" style="border:0;width:100%;height:1400px"></iframe>');
  }
  if (req.method === 'GET' && req.url === '/googleusercontent/fenetre') return envoyer(200, 'text/html', fenetre());
  if (req.method === 'GET' && req.url === '/etat') {
    return envoyer(200, 'application/json', JSON.stringify({
      onglets: classeur.getSheets().map(f => f.getName()), rapports: ctx.rapportsEnregistres_(),
      prevus: ctx.contratsPrevus_(classeur).map(p => p.id), appels
    }));
  }
  if (req.method === 'POST' && req.url === '/appel') {
    let corps = '';
    req.on('data', d => { corps += d; });
    req.on('end', () => {
      let r;
      try {
        const { nom, args } = JSON.parse(corps);
        appels.push(nom);
        if (typeof ctx[nom] !== 'function' || /_$/.test(nom)) throw new Error('fonction inconnue ' + nom);
        const v = ctx[nom].apply(null, args);
        r = { ok: true, valeur: v === undefined ? null : JSON.parse(JSON.stringify(v)) };
      } catch (e) { r = { ok: false, message: e.message }; }
      envoyer(200, 'application/json', JSON.stringify(r));
    });
    return undefined;
  }
  return envoyer(404, 'text/plain', 'introuvable');
});
serveur.listen(0, '0.0.0.0', () => {
  process.stdout.write('PRET ' + serveur.address().port + ' ' + JSON.stringify(fichiers) + '\n');
});
const finir = () => { try { fs.rmSync(dossier, { recursive: true, force: true }); } catch (e) { /* rien */ } process.exit(0); };
process.on('SIGTERM', finir);
process.on('SIGINT', finir);

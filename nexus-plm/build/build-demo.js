/**
 * Assemble la démo à partir des fichiers RÉELLEMENT livrés dans src/.
 *
 * Aucun fichier de src/ n'est modifié : on résout les <?!= include() ?> comme
 * le ferait Apps Script, on remplace les CDN par de l'inline (la politique de
 * sécurité des Artifacts interdit les feuilles de style externes), et on
 * insère demo/FauxServeur.html qui fournit un google.script.run factice.
 */
const fs = require('fs');
const path = require('path');

const RACINE = path.join(__dirname, '..');
const lire = function (p) { return fs.readFileSync(path.join(RACINE, p), 'utf8'); };

// Bootstrap est récupéré à la demande : la politique de sécurité des Artifacts
// interdit les feuilles de style externes, il faut donc tout inliner.
const VENDU = [
  ['build/bootstrap.min.css',
   'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css'],
  ['build/bootstrap.bundle.min.js',
   'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js']
];

async function recupererSiAbsent() {
  for (const [cible, url] of VENDU) {
    const chemin = path.join(RACINE, cible);
    if (fs.existsSync(chemin)) continue;
    process.stdout.write('  récupération de ' + path.basename(cible) + '… ');
    const reponse = await fetch(url);
    if (!reponse.ok) throw new Error('HTTP ' + reponse.status + ' sur ' + url);
    fs.writeFileSync(chemin, Buffer.from(await reponse.arrayBuffer()));
    console.log('ok');
  }
}

async function principal() {

let page = lire('src/Index.html');

// 1. Résolution des includes Apps Script
page = page.replace(/<\?!=\s*include\('([^']+)'\);?\s*\?>/g, function (_, nom) {
  return lire('src/' + nom + '.html');
});
if (/<\?!=/.test(page)) throw new Error('Un include n\'a pas été résolu');

// 2. CDN -> inline
page = page.replace(
  /<link href="https:\/\/cdn\.jsdelivr\.net\/npm\/bootstrap[^"]*" rel="stylesheet">/,
  '<style>\n' + lire('build/bootstrap.min.css') + '\n</style>');
page = page.replace(
  /<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/bootstrap[^"]*"><\/script>/,
  '<script>\n' + lire('build/bootstrap.bundle.min.js') + '\n</script>');
if (/cdn\.jsdelivr/.test(page)) throw new Error('Une référence CDN subsiste');

// 3. Couche de démonstration, insérée avant les scripts client.
const marqueur = '<script>\n// ============================================================\n// NEXUS PLM — utilitaires d\'affichage';
if (page.indexOf(marqueur) === -1) throw new Error('Point d\'insertion de la couche démo introuvable');
page = page.replace(marqueur,
  lire('demo/Photos.html') + '\n' + lire('demo/FauxServeur.html') + '\n' + marqueur);

// 4. Barre de démonstration
const BARRE_SCRIPT = `
<script>
  document.getElementById('demoPanne').addEventListener('change', function (e) {
    window.SIMULER_PANNE = e.target.checked;
  });
  document.getElementById('demoReset').addEventListener('click', function () {
    reinitialiserDemo();
    document.getElementById('demoPanne').checked = false;
    window.SIMULER_PANNE = false;
    Store.pnCourant = null; Store.ongletActif = 'Toutes';
    Store.recherche = ''; Store.filtreComposants = []; Store.filtreTypes = [];
    var champ = document.getElementById('searchBar');
    if (champ) champ.value = '';
    chargerTout().then(function () { afficherBandeau('Données de démonstration réinitialisées.', 'info'); });
  });

  // Les téléchargements sont bloqués dans le bac à sable de l'aperçu ; il n'y
  // a plus d'export dans l'application, ce filet ne sert que si l'on en
  // rajoutait un.
  if (typeof telecharger === 'function') {
    telecharger = function (contenu, nomFichier) {
      afficherBandeau('Aperçu : le téléchargement de ' + nomFichier + ' est bloqué ici.', 'info');
    };
  }

  // Filet : si les scripts s'exécutent après le chargement du document,
  // l'écouteur DOMContentLoaded de Main.html ne se déclencherait jamais.
  if (document.readyState === 'complete') {
    document.dispatchEvent(new Event('DOMContentLoaded'));
  }
</script>
`;

// Pied de page discret : le bandeau du haut mangeait l'écran et n'avait rien
// à faire dans un site. Les commandes de démonstration vivent en bas.
const BARRE_BALISAGE = `
<footer class="pied enveloppe">
  <span>Démonstration — données en mémoire, rien n'est enregistré</span>
  <label><input type="checkbox" id="demoPanne"> Simuler une panne serveur</label>
  <button type="button" class="btn-lien" id="demoReset">Réinitialiser</button>
</footer>
`;

// 5. Retrait de l'enveloppe HTML : l'hôte Artifact fournit doctype/head/body.
const corps = page.match(/<body>([\s\S]*)<\/body>/)[1];
const styles = page.match(/<style>[\s\S]*?<\/style>/g).join('\n');

// Les <link> de polices vivent dans le <head>, que l'enveloppe Artifact
// fournit : on les réinjecte en tête de fichier (valide en HTML5, et
// fonts.googleapis.com est le seul hébergeur de styles autorisé).
const polices = (page.match(/<link[^>]*fonts\.(googleapis|gstatic)\.com[^>]*>/g) || []).join('\n');
if (!polices) throw new Error('Lien de polices introuvable');

/**
 * Insère le pied de démonstration après le contenu principal. On vérifie que
 * l'ancre existe : un point d'insertion silencieusement absent ferait passer
 * une démo amputée sans que rien ne le signale.
 */
function injecterBarre(corps) {
  const ancre = '</main>';
  if (corps.indexOf(ancre) === -1) {
    throw new Error("Ancre d'insertion du pied de démonstration introuvable : " + ancre);
  }
  return corps.replace(ancre, ancre + BARRE_BALISAGE);
}

const sortie = '<title>NEXUS</title>\n' + polices + '\n' + styles + '\n' +
               injecterBarre(corps.replace(/<style>[\s\S]*?<\/style>/g, '')) +
               BARRE_SCRIPT;

const cible = path.join(RACINE, 'build', 'demo.html');
fs.writeFileSync(cible, sortie);

console.log('demo.html écrit : ' + (sortie.length / 1024).toFixed(0) + ' Ko');
console.log('  includes résolus, CDN inlinés, faux serveur inséré');

}

recupererSiAbsent().then(principal).catch(function (e) {
  console.error('Échec de la construction : ' + e.message);
  process.exit(1);
});

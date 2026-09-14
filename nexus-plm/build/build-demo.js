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
page = page.replace(marqueur, lire('demo/FauxServeur.html') + '\n' + marqueur);

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
    Store.recherche = ''; Store.filtreComposants = [];
    var champ = document.getElementById('searchBar');
    if (champ) champ.value = '';
    chargerTout().then(function () { afficherBandeau('Données de démonstration réinitialisées.', 'info'); });
  });
  // Les téléchargements déclenchés par script sont bloqués dans le bac à sable
  // de l'aperçu : plutôt qu'un bouton sans effet, on montre le fichier produit.
  // Le code de src/ n'est pas modifié — on remplace la fonction après coup.
  telecharger = function (contenu, nomFichier, type) {
    var avecBom = contenu.charCodeAt(0) === 0xFEFF;
    document.getElementById('demoCsvMeta').innerHTML =
      '<b>' + nomFichier + '</b> &middot; ' + type + ' &middot; ' + contenu.length + ' caractères' +
      (avecBom ? ' &middot; <span class="text-success">BOM UTF-8 présent</span>'
               : ' &middot; <span class="text-danger">BOM absent</span>');
    document.getElementById('demoCsvContenu').textContent = avecBom ? contenu.slice(1) : contenu;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('demoCsvModal')).show();
  };

  // Filet : si les scripts s'exécutent après le chargement du document,
  // l'écouteur DOMContentLoaded de Main.html ne se déclencherait jamais.
  if (document.readyState === 'complete') {
    document.dispatchEvent(new Event('DOMContentLoaded'));
  }
</script>
`;

const BARRE_BALISAGE = `
<div class="modal fade" id="demoCsvModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable">
    <div class="modal-content" style="border-radius:16px;">
      <div class="modal-header">
        <h5 class="modal-title fw-bold">Export CSV — aperçu</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fermer"></button>
      </div>
      <div class="modal-body">
        <p class="text-muted small">
          Le bac à sable de cet aperçu bloque les téléchargements. Dans l'application,
          ce bouton enregistre le fichier. Voici son contenu exact :
        </p>
        <div id="demoCsvMeta" class="small mb-2"></div>
        <pre id="demoCsvContenu" class="border rounded p-3 bg-light small"
             style="white-space:pre-wrap; word-break:break-word; max-height:45vh; overflow:auto;"></pre>
      </div>
    </div>
  </div>
</div>
<div id="barreDemo">
  <div class="demo-texte">
    <b>Démonstration</b><span class="demo-texte-long"> — données en mémoire, rien n'est
    enregistré. Les champs Image attendent une URL de photo : cet aperçu bloque les
    images externes, elles s'afficheront dans l'application.</span>
  </div>
  <div class="demo-controles">
    <label class="demo-bascule">
      <input type="checkbox" id="demoPanne"> Simuler une panne serveur
    </label>
    <button type="button" class="demo-btn" id="demoReset">Réinitialiser</button>
  </div>
</div>
<style>
  #barreDemo {
    /* sous les couches Bootstrap (backdrop 1040, offcanvas 1045, modal 1055) :
       a 1500 la barre interceptait les clics du panneau lateral. */
    position: sticky; top: 0; z-index: 1020; background: #1c2541; color: #fff;
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap; padding: 8px 16px; font-size: 12.5px;
    border-bottom: 2px solid #0071e3;
  }
  #barreDemo code { color: #8cb0d9; background: rgba(255,255,255,.08);
    padding: 1px 5px; border-radius: 4px; }
  .demo-controles { display: flex; align-items: center; gap: 12px; }
  .demo-bascule { display: flex; align-items: center; gap: 6px;
    cursor: pointer; white-space: nowrap; margin: 0; }
  .demo-btn { background: rgba(255,255,255,.12); color: #fff; border: 1px solid rgba(255,255,255,.25);
    border-radius: 8px; padding: 4px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
  .demo-btn:hover { background: rgba(255,255,255,.22); }
  /* En mobile la barre mangeait 96 px de haut et recouvrait l'en-tête au
     défilement : on ne garde que les commandes. */
  @media (max-width: 620px) {
    #barreDemo { padding: 6px 12px; }
    .demo-texte { font-size: 11.5px; }
    .demo-texte b::after { content: " — données en mémoire"; font-weight: 400; }
    .demo-texte-long { display: none; }
    .demo-bascule { font-size: 11.5px; }
  }
</style>
`;

/**
 * Insère la barre de démonstration juste avant l'en-tête de l'application.
 * On vérifie que l'ancre existe : un point d'insertion silencieusement absent
 * ferait passer une démo amputée sans que rien ne le signale.
 */
function injecterBarre(corps) {
  const ancre = '<header class="entete">';
  if (corps.indexOf(ancre) === -1) {
    throw new Error("Ancre d'insertion de la barre de démo introuvable : " + ancre);
  }
  return corps.replace(ancre, BARRE_BALISAGE + ancre);
}

// 5. Retrait de l'enveloppe HTML : l'hôte Artifact fournit doctype/head/body
const corps = page.match(/<body>([\s\S]*)<\/body>/)[1];
const styles = page.match(/<style>[\s\S]*?<\/style>/g).join('\n');

// Les <link> de polices vivent dans le <head>, que l'enveloppe Artifact
// fournit : on les réinjecte en tête de fichier (valide en HTML5, et
// fonts.googleapis.com est le seul hébergeur de styles autorisé).
const polices = (page.match(/<link[^>]*fonts\.(googleapis|gstatic)\.com[^>]*>/g) || []).join('\n');
if (!polices) throw new Error('Lien de polices introuvable');

const sortie = '<title>NEXUS PLM</title>\n' + polices + '\n' + styles + '\n' +
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

/* Assemble la page autonome que la batterie va piloter.
   Seule transformation : les polices Google sont remplacées par les copies
   locales quand un dossier `fonts/` existe à côté, pour que les tests tournent
   sans réseau. Sinon on garde le lien d'origine. */
const fs = require('fs');
const path = require('path');

const racine = path.join(__dirname, '..');
let corps = fs.readFileSync(path.join(racine, 'suivi-fwd.html'), 'utf8');

if (fs.existsSync(path.join(racine, 'fonts', 'local.css'))) {
  corps = corps.replace(/<link rel="stylesheet" href="https:\/\/fonts\.googleapis\.com[^"]*">/,
                        '<link rel="stylesheet" href="fonts/local.css">');
}

const tete = '<!doctype html><html lang="fr"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' +
  '<style>:root{color-scheme:light}body{margin:0;font:14px system-ui;background:#fafaf9}' +
  'img{max-width:100%}[hidden]{display:none!important}</style></head><body>';

fs.writeFileSync(path.join(racine, 'apercu.html'), tete + corps + '\n</body></html>');
console.log('apercu.html reconstruit');

/* =========================================================================
   Construit assets/data/flotte.json à partir du résultat de la recherche
   publique (fiches vérifiées) — usage :
     node tools/porteurs-depuis-recherche.mjs <resultat.json>
   Le fichier d'entrée est le retour du workflow « etii-hub-recherche » :
   { porteurs: [{ code, categorie, verdict: { ficheCorrigee, fiabiliteGlobale, … } }] }.
   Les pôles et les données service déjà présents dans flotte.json sont
   conservés ; les nouveaux porteurs arrivent sans pôle (à renseigner).
   ========================================================================= */
import { readFileSync, writeFileSync } from 'node:fs';

const entree = process.argv[2];
if (!entree) { console.error('usage : node tools/porteurs-depuis-recherche.mjs <resultat.json>'); process.exit(1); }
const resultat = JSON.parse(readFileSync(entree, 'utf8'));
const ancien = JSON.parse(readFileSync('assets/data/flotte.json', 'utf8'));
const anciens = new Map((ancien.flotte || []).map((a) => [a.code, a]));

const SILHOUETTES = {
  H125: 'patins-monoturbine', H130: 'patins-fenestron', H135: 'patins-fenestron-bi', H145: 'patins-fenestron-bi',
  H145M: 'patins-fenestron-bi', H160: 'roues-fenestron-bi', H160M: 'roues-fenestron-bi', H175: 'roues-bi',
  H215: 'roues-bi-lourd', H225: 'roues-bi-lourd', H225M: 'roues-bi-lourd', TIGRE: 'roues-bi', NH90: 'roues-bi',
  RACER: 'roues-bi', DISRUPTIVELAB: 'patins-fenestron', FLIGHTLAB: 'patins-fenestron'
};
const ORDRE = ['H125', 'H130', 'H135', 'H145', 'H160', 'H175', 'H215', 'H225', 'H145M', 'H160M', 'H225M', 'TIGRE', 'NH90', 'RACER', 'DISRUPTIVELAB', 'FLIGHTLAB'];

const champsService = ancien.champs;
const vide = (groupe) => Object.fromEntries((champsService[groupe] || []).map((c) => [c.cle, null]));

const flotte = [];
for (const p of resultat.porteurs || []) {
  const v = p.verdict;
  if (!v || !v.ficheCorrigee) { console.warn('sans fiche vérifiée :', p.code); continue; }
  const fiche = v.ficheCorrigee;
  fiche.code = p.code;
  fiche.categorie = p.categorie;
  fiche.fiabilite = v.fiabiliteGlobale || 'moyenne';
  fiche.corrections = (v.corrections || []).length;
  const a = anciens.get(p.code) || {};
  flotte.push({
    code: p.code,
    categorie: p.categorie,
    segment: fiche.segment || a.segment || '',
    poles: Array.isArray(a.poles) ? a.poles : [],
    silhouette: SILHOUETTES[p.code] || a.silhouette || 'patins-monoturbine',
    photo: a.photo || '',
    fiche,
    service: {
      technique: a.technique || vide('technique'),
      economique: a.economique || vide('economique')
    },
    jalon: a.jalon ?? null,
    avancement: a.avancement ?? null
  });
}
flotte.sort((x, y) => ORDRE.indexOf(x.code) - ORDRE.indexOf(y.code));

const sortie = {
  avertissement: 'Désignations, chiffres et anecdotes des fiches proviennent de sources publiques '
    + '(Wikipédia, airbus.com, presse spécialisée) ; chaque valeur porte sa confiance et sa source. '
    + 'Les données propres au service restent à renseigner : elles ne sont pas inventées.',
  categories: ancien.categories,
  champs: champsService,
  flotte
};
writeFileSync('assets/data/flotte.json', JSON.stringify(sortie, null, 2) + '\n');
console.log(`flotte.json écrit : ${flotte.length} porteurs`);

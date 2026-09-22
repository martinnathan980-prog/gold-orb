// Test de l'organigramme, dans un vrai navigateur.
//
//   1. python3 -m http.server 8111      2. node tests/organigramme.e2e.mjs
//
// La page répond à « qui est qui » et « qui porte quel appareil ». Trois
// gestes y échouaient en silence, et aucune suite ne les gardait :
//
//   · un lien #personne=… reçu d'un collègue quand la page est DÉJÀ
//     ouverte (même document : rien n'est rechargé) ;
//   · le bouton « Rechercher partout », qui fabrique exactement ce
//     lien-là ;
//   · le saut d'une fiche ouverte vers une autre personne, qui laissait
//     la fiche périmée à l'écran — une donnée fausse présentée comme
//     juste, le pire défaut possible dans un annuaire.
//
// S'y ajoute la mention « Lead à renseigner », qui apparaissait sous
// filtre alors que le lead existe.

import { chromium } from 'playwright';

const B = process.env.BASE || 'http://localhost:8111';

// Les données sont lues par le serveur, comme le fait le navigateur : le
// test ne dépend d'aucun chemin de fichier et vérifie ce qui est servi.
const lire = async (n) => {
  const r = await fetch(`${B}/assets/data/${n}.json`);
  if (!r.ok) throw new Error(`${n}.json : HTTP ${r.status} — le serveur est-il lancé ?`);
  return r.json();
};
const orga = await lire('organigramme');

// Deux personnes de pôles différents, prises dans les données : un membre
// et un lead. Le test survit ainsi à une refonte du jeu d'exemple.
const squadDe = (i) => orga.poles[i].squads[0];
const CIBLE = { pole: orga.poles[1].pole, ...squadDe(1).membres.find((m) => m.role !== 'leader') };
const AUTRE = { pole: orga.poles[0].pole, ...squadDe(0).membres.find((m) => m.role === 'leader') };

// Un périmètre porté par plusieurs squads : c'est le filtre qui faisait
// mentir la mention « Lead à renseigner ».
const PERIMETRE = 'H160';

let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`))
                                : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const nav = await chromium.launch({ executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const err = [];
page.on('pageerror', (e) => err.push(e.message));

const etat = () => page.evaluate(() => ({
  modales: document.querySelectorAll('.modale').length,
  titre: (document.querySelector('.modale__titre') || {}).textContent || '',
  fiche: (document.querySelector('.org-fiche__liste') || {}).textContent || '',
  hash: location.hash,
  champ: (document.getElementById('org-recherche') || {}).value
}));

const poser = async (hash) => {
  await page.evaluate((h) => { location.hash = h; }, hash);
  await page.waitForTimeout(900);
};

console.log(`== Organigramme : ${CIBLE.nom} (${CIBLE.pole}) et ${AUTRE.nom} (${AUTRE.pole}) ==`);

console.log('\n== 1. Un lien reçu, dans un contexte neuf ==');
await page.goto(`${B}/organigramme.html#pole=${CIBLE.pole}&personne=${CIBLE.id}`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
let e = await etat();
t('le lien ouvre la fiche au chargement', e.modales === 1 && e.titre === CIBLE.nom, JSON.stringify(e));

console.log('\n== 2. « Rechercher partout » depuis la page elle-même ==');
await page.goto(`${B}/organigramme.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await page.click('[data-palette]');
await page.waitForTimeout(400);
await page.fill('#palette-champ', CIBLE.nom);
await page.waitForTimeout(600);
const premier = await page.evaluate(() => {
  const r = document.querySelector('[data-href]');
  return r ? r.dataset.href : '';
});
t('le premier résultat vise bien cette personne',
  premier.includes(`personne=${CIBLE.id}`), premier);
await page.keyboard.press('Enter');
await page.waitForTimeout(1200);
e = await etat();
t('le geste ouvre la fiche sans recharger la page',
  e.modales === 1 && e.titre === CIBLE.nom, JSON.stringify(e));

console.log('\n== 3. Saut d\'une fiche ouverte vers une autre personne ==');
await poser(`pole=${AUTRE.pole}&personne=${AUTRE.id}`);
e = await etat();
t('une seule modale reste à l\'écran', e.modales === 1, `(${e.modales})`);
t('c\'est la personne demandée', e.titre === AUTRE.nom, e.titre);
t('la fiche porte son identifiant', e.fiche.includes(AUTRE.id.toUpperCase()), e.fiche.slice(0, 60));

console.log('\n== 4. Un identifiant inconnu ne laisse pas la fiche périmée ==');
await poser('personne=identifiant-qui-nexiste-pas');
e = await etat();
t('la fiche se ferme et l\'URL n\'invente rien',
  e.modales === 0 && !e.hash.includes('personne='), JSON.stringify(e));

console.log('\n== 5. Un filtre tapé avant ne survit pas à un lien reçu ==');
await page.goto(`${B}/organigramme.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await page.fill('#org-recherche', 'H175');
await page.waitForTimeout(500);
await poser(`pole=${CIBLE.pole}&personne=${CIBLE.id}`);
e = await etat();
t('la fiche s\'ouvre malgré le filtre', e.modales === 1 && e.titre === CIBLE.nom, e.titre);
t('le champ de recherche est vidé', e.champ === '', JSON.stringify(e.champ));

console.log('\n== 5 bis. Le lien d\'évitement ne remet pas la page à zéro ==');
// #contenu n'est pas un état de page : le relire effaçait le pôle choisi
// et le filtre en cours, sur le premier geste d'un utilisateur au clavier.
await page.goto(`${B}/organigramme.html#pole=${AUTRE.pole}`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await page.fill('#org-recherche', PERIMETRE);
await page.waitForTimeout(500);
await page.evaluate(() => { document.querySelector('.lien-evitement').click(); });
await page.waitForTimeout(700);
const apres = await page.evaluate(() => ({
  champ: document.getElementById('org-recherche').value,
  pole: ([...document.querySelectorAll('[data-pole-filtre]')]
    .find((b) => b.getAttribute('aria-pressed') === 'true') || {}).dataset.poleFiltre
}));
t('le filtre et le pôle survivent à « Aller au contenu »',
  apres.champ === PERIMETRE && apres.pole === AUTRE.pole, JSON.stringify(apres));

console.log(`\n== 6. « Lead à renseigner » sous le filtre « ${PERIMETRE} » ==`);
await page.goto(`${B}/organigramme.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
const leadsSansFiltre = await page.evaluate(() =>
  [...document.querySelectorAll('.org-squad__lead')].map((x) => x.textContent));
await page.fill('#org-recherche', PERIMETRE);
await page.waitForTimeout(700);
const leadsFiltres = await page.evaluate(() =>
  [...document.querySelectorAll('.org-squad__lead')].map((x) => x.textContent));
const menteuses = leadsFiltres.filter((x) => /à renseigner/.test(x));
t('toutes les squads affichent leur lead sans filtre',
  leadsSansFiltre.length > 0 && leadsSansFiltre.every((x) => /^Lead : /.test(x)),
  leadsSansFiltre.filter((x) => !/^Lead : /.test(x)).join(' | '));
t(`aucune squad ne perd son lead sous « ${PERIMETRE} »`,
  leadsFiltres.length > 0 && menteuses.length === 0,
  `(${menteuses.length}/${leadsFiltres.length})`);

console.log('\n== 7. Le mot juste sur la fiche d\'une personne ==');
await page.goto(`${B}/organigramme.html#personne=${CIBLE.id}`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
const fiche = (await etat()).fiche;
// Sans ce garde, les deux assertions suivantes passeraient à vide si la
// fiche ne s'ouvrait pas du tout.
t('la fiche est bien ouverte', fiche.length > 0, JSON.stringify(fiche));
t('l\'appareil est annoncé comme « Périmètre »', /Périmètre/.test(fiche), fiche.slice(0, 80));
t('« Porteur » ne désigne plus l\'appareil ici',
  fiche.length > 0 && !/Porteur/.test(fiche), fiche.slice(0, 80));
const placeholder = await page.getAttribute('#org-recherche', 'placeholder');
t('le champ de recherche dit « périmètre »', /périmètre/i.test(placeholder), placeholder);

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

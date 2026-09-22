// Test de bout en bout de « Rechercher partout » (Ctrl K), dans un vrai
// navigateur.
//
//   1. lancer le site :  python3 -m http.server 8111   (depuis etii-hub/)
//   2. BASE=http://localhost:8111 node tests/palette.e2e.mjs
//
// Trois garanties que le code seul ne montre pas :
//   - Entrée ouvre le MEILLEUR résultat, pas le premier d'un ordre littéral
//     de groupes ;
//   - les comptes des en-têtes de groupe sont de vrais totaux, et aucun
//     groupe ne disparaît parce qu'un autre a mangé la place ;
//   - un jeu de données absent est dit à l'utilisateur, et il est retenté à
//     l'ouverture suivante au lieu d'être mémoïsé troué.

import { chromium } from 'playwright';

const B = process.env.BASE || 'http://localhost:8111';
const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const err = []; page.on('pageerror', (e) => err.push(e.message));

let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const ouvrir = async () => {
  await page.keyboard.press('Control+k');
  await page.waitForTimeout(700);
};
const fermer = async () => {
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
};
const chercher = async (q) => {
  await page.locator('.palette__champ').fill(q);
  await page.waitForTimeout(600);
};
const premiere = () => page.locator('.palette__resultat').first();
const entetes = async () => (await page.locator('.palette__groupe').allInnerTexts()).map((s) => s.replace(/\s+/g, ' ').trim());

await page.goto(B + '/index.html', { waitUntil: 'load' });
await page.waitForTimeout(1200);

console.log('\n== Entrée ouvre le meilleur résultat ==');
await ouvrir();

// Le titre exact d'une communication : la ligne présélectionnée doit être
// cette communication, pas un document d'un groupe mieux placé.
await chercher('Campagne de mesure des interfaces');
t('le titre exact d\'une communication sort en premier',
  /Campagne de mesure des interfaces/.test(await premiere().innerText()),
  `("${(await premiere().innerText()).replace(/\n/g, ' | ')}")`);
t('et son lien porte le fragment que le kiosque sait ouvrir',
  /#communication=annonce-/.test(await premiere().getAttribute('data-href')),
  `("${await premiere().getAttribute('data-href')}")`);

// Une personne nommée : elle passait derrière deux documents dont elle
// n'est que la porteuse.
await chercher('Personne 22');
t('une personne nommée sort avant les documents qu\'elle porte',
  /Personne 22/.test(await premiere().innerText()),
  `("${(await premiere().innerText()).replace(/\n/g, ' | ')}")`);

// L'édito entre dans le corpus avec son identifiant et son corps.
await chercher('Un trimestre qui se tient');
t('l\'édito est trouvable', (await page.locator('.palette__resultat').count()) > 0);
t('et son sous-titre dit « Édito »', /Édito/.test(await premiere().innerText()),
  `("${(await premiere().innerText()).replace(/\n/g, ' | ')}")`);
t('et son lien mène au mot du chef', (await premiere().getAttribute('data-href')) === 'index.html#communication=mot-du-chef',
  `("${await premiere().getAttribute('data-href')}")`);

// L'épingle du contrat d'identifiants : la palette fabrique ses fragments
// « mot-du-chef » / « annonce-<id> » sans importer kiosque.js. On vérifie donc
// que chaque lien de communication ouvre RÉELLEMENT la bonne carte du kiosque.
// Si l'un des deux change de convention, ce test tombe.
const liensComm = [];
for (const q of ['Un trimestre qui se tient', 'Campagne de mesure des interfaces', 'Routage des harnais H225']) {
  await chercher(q);
  const h = await premiere().getAttribute('data-href');
  if (/#communication=/.test(h)) liensComm.push([q, h]);
}
await fermer();
t('trois liens de communication à vérifier', liensComm.length === 3, `(${liensComm.length})`);
for (const [q, h] of liensComm) {
  await page.goto(B + '/' + h, { waitUntil: 'load' });
  await page.waitForTimeout(1500);
  const carte = page.locator('.kiosque__carte[aria-current="true"]').first();
  const lu = (await carte.count()) ? await carte.innerText() : '(aucune carte sélectionnée)';
  t(`« ${q} » ouvre sa carte dans le kiosque`, lu.includes(q.slice(0, 24)), `("${lu.replace(/\n/g, ' | ').slice(0, 90)}")`);
}
await page.goto(B + '/index.html', { waitUntil: 'load' });
await page.waitForTimeout(1200);
await ouvrir();

console.log('\n== Les comptes des en-têtes sont de vrais totaux ==');
await chercher('harnais');
const tetes = await entetes();
t('un groupe tronqué affiche « 4 / total »', tetes.some((h) => /\b4 \/ (2[0-9]|[3-9][0-9]|[0-9]{3})\b/.test(h)),
  `(${tetes.join(' ; ')})`);
t('aucun en-tête n\'annonce un total inférieur à ce qu\'il montre',
  tetes.every((h) => { const m = h.match(/(\d+) \/ (\d+)/); return !m || Number(m[1]) <= Number(m[2]); }),
  `(${tetes.join(' ; ')})`);
t('la communication n\'est plus évincée par les groupes précédents',
  tetes.some((h) => /COMMUNICATION/i.test(h)), `(${tetes.join(' ; ')})`);
t('au plus quatre lignes par groupe', (await page.locator('.palette__resultat').count()) <= tetes.length * 4);

console.log('\n== Les espaces de pôle sont trouvables par leur sujet ==');
for (const [q, code] of [['routage', 'etiii.html'], ['nommage', 'etiia.html'], ['schemas electriques', 'etiie.html']]) {
  await chercher(q);
  const liens = await page.locator('.palette__resultat').evaluateAll((l) => l.map((x) => x.dataset.href));
  t(`« ${q} » mène à ${code}`, liens.includes(code), `(${liens.slice(0, 6).join(' ')})`);
}

console.log('\n== À requête vide, l\'écran ne change pas ==');
await chercher('');
t('les 8 pages, et rien d\'autre', (await page.locator('.palette__resultat').count()) === 8,
  `(${await page.locator('.palette__resultat').count()})`);
t('un seul en-tête, « Pages 8 »', (await entetes()).length === 1 && /8$/.test((await entetes())[0]),
  `(${(await entetes()).join(' ; ')})`);

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));
await fermer();

console.log('\n== Un jeu de données absent est dit, et retenté ==');
// La panne : documents.json refuse de se charger. Les cinq autres jeux
// doivent rester cherchables, et l'état doit le dire.
await page.route('**/documents.json*', (r) => r.abort());
await page.reload({ waitUntil: 'load' });
await page.waitForTimeout(1200);
await ouvrir();
await chercher('continuité');
const etatPanne = await page.locator('.palette__etat').innerText();
t('l\'état prévient que les résultats sont incomplets', /Résultats incomplets/.test(etatPanne), `("${etatPanne}")`);
t('et il nomme le jeu absent', /documents/.test(etatPanne), `("${etatPanne}")`);
await fermer();

// Le corpus troué n'a pas été mémoïsé : la panne levée, la réouverture
// retrouve les documents sans recharger la page.
await page.unroute('**/documents.json*');
await ouvrir();
await chercher('continuité');
const etatRetabli = await page.locator('.palette__etat').innerText();
t('la panne levée, l\'avertissement disparaît', !/Résultats incomplets/.test(etatRetabli), `("${etatRetabli}")`);
t('et les documents sont revenus sans recharger la page',
  (await entetes()).some((h) => /DOCUMENTS/i.test(h)), `(${(await entetes()).join(' ; ')})`);

console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close(); process.exit(ko ? 1 : 0);

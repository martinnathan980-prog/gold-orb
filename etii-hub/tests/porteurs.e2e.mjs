// Test de bout en bout des porteurs, dans un vrai navigateur.
//
//   1. lancer le site :  python3 -m http.server 8111
//   2. npm install playwright
//   3. node tests/porteurs.e2e.mjs
//
// Les porteurs vivent dans leur section du tableau de bord (index.html) :
// toute la flotte, rangée par marché — Civil, Militaire, Prototype — sans
// onglet ni tri ; la fiche d'un appareil s'ouvre sur place et se lit
// d'abord en grands chiffres expliqués en français, sans source ni lien
// extérieur en ligne ; le dessin à l'échelle ; la comparaison de deux ou
// trois appareils. Les liens « index.html#porteur=CODE » (ceux des espaces
// de pôle) ouvrent la fiche.

import { chromium } from 'playwright';
const B = process.env.BASE || 'http://localhost:8111';
const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const flotte = await (await fetch(B + '/assets/data/flotte.json')).json();
const appareils = flotte.flotte.filter((a) => a && a.code);
const marches = flotte.categories.map((c) => ({ cle: c.cle, libelle: c.libelle, codes: appareils.filter((a) => a.categorie === c.cle).map((a) => a.code) }));
const err = [];
const nouvelle = async (o = {}) => {
  const ctx = await nav.newContext(Object.assign({ viewport: { width: 1280, height: 900 } }, o));
  const page = await ctx.newPage();
  page.on('pageerror', (e) => err.push(e.message));
  return { ctx, page };
};
const debordement = (page) => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);

/* =========================================================================
   1. La galerie
   ========================================================================= */

let { ctx, page } = await nouvelle();
await page.goto(B + '/index.html', { waitUntil: 'networkidle' });
await page.waitForSelector('#zone-flotte .porteur-carte');

console.log('\n== La section et sa galerie ==');
t('les porteurs n’ont pas de page à eux : la barre ne la propose pas, la section les porte',
  (await page.locator('nav.site-nav a').evaluateAll((l) => l.map((a) => a.getAttribute('href')))).join(' ') === 'index.html etiia.html etiie.html etiii.html docsearch.html'
  && (await page.locator('#section-porteurs #zone-flotte .porteurs').count()) === 1);
t('ni onglets de marché ni tri : toute la gamme, rangée par marché',
  (await page.locator('.porteurs-bandeau__marche, .porteurs__tri').count()) === 0 && await page.locator('#bandeau-porteurs').isHidden());
const sections = await page.locator('.porteurs__marche').evaluateAll((s) => s.map((x) => ({
  cle: x.dataset.categorie, titre: x.querySelector('h2').firstChild.textContent.trim(),
  codes: Array.from(x.querySelectorAll('.porteur-carte')).map((c) => c.dataset.code)
})));
t('trois marchés, dans l’ordre Civil · Militaire · Prototype, en h2', sections.map((s) => s.titre).join(' · ') === 'Civil · Militaire · Prototype');
for (const m of marches) {
  const s = sections.find((x) => x.cle === m.cle);
  t(`${m.libelle} : ses ${m.codes.length} appareils, dans l’ordre du fichier`, s && s.codes.join(',') === m.codes.join(','), s ? s.codes.join(',') : '(absente)');
}
t(`toute la flotte est là (${appareils.length}), chacun une fois`, (await page.locator('.porteur-carte').count()) === appareils.length);
t('chaque carte est un lien vers sa fiche (#porteur=CODE)',
  (await page.locator('.porteur-carte__lien').evaluateAll((l) => l.every((a) => a.getAttribute('href') === '#porteur=' + encodeURIComponent(a.dataset.code)))));
t('chaque carte dit sa masse, ses places et sa vitesse quand on les connaît',
  /2,25 t · 6 places · 252 km\/h/.test(await page.locator('.porteur-carte[data-code="H125"]').innerText()));
t('un prototype sans chiffre ne montre pas de zéro inventé', /chiffres à venir/.test(await page.locator('.porteur-carte[data-code="DISRUPTIVELAB"]').innerText()));
const rangees = await page.locator('.porteurs__marche[data-categorie="civil"] .porteur-carte').evaluateAll((l) => {
  const hauts = l.map((x) => Math.round(x.getBoundingClientRect().top));
  return [...new Set(hauts)].map((h) => hauts.filter((y) => y === h).length);
});
t('trois cartes par rangée : les neuf civils font trois rangées pleines', rangees.join(',') === '3,3,3', rangees.join(','));

console.log('\n== Les photos ==');
const photos = await page.locator('.porteur-carte__photo').evaluateAll((imgs) => imgs.map((i) => ({ src: i.getAttribute('src'), lazy: i.getAttribute('loading') })));
t('chaque vignette se charge à la demande (loading="lazy")', photos.length > 0 && photos.every((p) => p.lazy === 'lazy'));
const avecPhoto = appareils.filter((a) => a.photo);
const absentes = [];
for (const a of avecPhoto) { const r = await fetch(B + '/' + a.photo); if (!r.ok) absentes.push(a.photo); }
t(`les ${avecPhoto.length} photos déclarées existent, en local`, absentes.length === 0 && avecPhoto.every((a) => !/^https?:/.test(a.photo)), absentes.join(', '));
t('chaque photo a son crédit (auteur, licence, page Commons)',
  avecPhoto.every((a) => a.credit && a.credit.auteur && a.credit.licence && /^https:\/\/commons\.wikimedia\.org\//.test(a.credit.page)));
t('un appareil sans photo garde sa silhouette', (await page.locator('.porteur-carte[data-code="H140"] .porteur-carte__visuel svg').count()) === 1);

/* =========================================================================
   2. La fiche
   ========================================================================= */

console.log('\n== La fiche d’un appareil ==');
await page.locator('.porteur-carte__lien[data-code="H130"]').click();
await page.waitForTimeout(700);
t('cliquer une carte ouvre sa fiche, à la place de la galerie',
  (await page.locator('.porteur-fiche').count()) === 1 && await page.locator('.porteurs__vue--galerie').isHidden()
  && (await page.locator('.porteur-fiche__code').innerText()).trim() === 'H130' && /index\.html#porteur=H130$/.test(page.url()));
t('le titre de la fiche est un h2, et reçoit le focus', await page.evaluate(() => document.activeElement && document.activeElement.classList.contains('porteur-fiche__code') && document.activeElement.tagName === 'H2'));
const fiche = page.locator('.porteur-fiche');
t('la tête dit le marché, la phase et depuis quand', /Civil/i.test(await fiche.locator('.porteur-fiche__surtitre').innerText())
  && /En production/.test(await fiche.locator('.porteur-fiche__etat').innerText()) && /en service depuis 2001/.test(await fiche.locator('.porteur-fiche__etat').innerText()));
const accroche = (await fiche.locator('.porteur-fiche__accroche').innerText()).trim();
t('une seule phrase d’accroche, courte', accroche.length > 20 && accroche.length <= 170 && (accroche.match(/[.!?](\s|$)/g) || []).length <= 1, accroche);
const tuiles = await fiche.locator('.porteur-tuile').evaluateAll((l) => l.map((x) => ({
  cle: x.dataset.chiffre, libelle: x.querySelector('.porteur-tuile__libelle').textContent.trim(),
  nombre: x.querySelector('.porteur-grand__nombre').textContent.trim(), unite: (x.querySelector('.porteur-grand__unite') || { textContent: '' }).textContent.trim(),
  question: x.querySelector('.porteur-tuile__question').textContent.trim(), jauge: !!x.querySelector('.porteur-jauge')
})));
t('« L’essentiel » : six chiffres, toujours dans le même ordre',
  tuiles.map((x) => x.cle).join(',') === 'longueur,masseMaxDecollage,passagers,vitesseCroisiere,distanceFranchissable,puissance', tuiles.map((x) => x.cle).join(','));
const distance = tuiles.find((x) => x.cle === 'distanceFranchissable');
t('606 km se lit avec ce qu’il veut dire : distance franchissable, sans ravitailler',
  distance && distance.nombre === '606' && distance.unite === 'km' && /Distance franchissable/i.test(distance.libelle) && /sans ravitailler/.test(distance.question), JSON.stringify(distance));
t('chaque chiffre a son unité et sa phrase en clair', tuiles.every((x) => x.question.length > 5));
t('chaque chiffre est situé « par rapport à la gamme »', tuiles.every((x) => x.jauge)
  && (await fiche.locator('.porteur-jauge__titre').first().innerText()) === 'par rapport à la gamme');
const lu = await fiche.innerText();
t('aucune source, aucune adresse ni confiance n’est écrite en ligne', !/https?:|wikipedia|airbus\.com|confiance/i.test(lu.replace(/Sources et fiabilité[\s\S]*$/, '')));
t('la fiche ne mène jamais hors du site', (await fiche.locator('a[href^="http"]').count()) === 0);
t('les sources sont repliées, et s’ouvrent', (await fiche.locator('details.porteur-sources').getAttribute('open')) === null
  && await (async () => { await fiche.locator('.porteur-sources__resume').click(); await page.waitForTimeout(200);
    return /airbus\.com|wikipedia/i.test(await fiche.locator('.porteur-sources').innerText()); })());
t('ni « Pour le service », ni « Lire la présentation »',
  !/Pour le service|Lire la présentation/.test(lu) && (await fiche.locator('.porteur-service, .porteur-fiche__presentation').count()) === 0);
const largeurs = await fiche.evaluate((f) => ({ fiche: f.getBoundingClientRect().width, accroche: f.querySelector('.porteur-fiche__accroche').getBoundingClientRect().width }));
t('l’accroche prend toute la largeur de la fiche', largeurs.accroche >= largeurs.fiche * 0.97, JSON.stringify(largeurs));
const grille = await fiche.locator('.porteur-groupe').evaluateAll((l) => {
  const b = l.map((g) => g.getBoundingClientRect());
  const rangs = [...new Set(b.map((r) => Math.round(r.top)))];
  return { colonnes: [...new Set(b.map((r) => Math.round(r.left)))].length, rangsEgaux: rangs.every((y) => new Set(b.filter((r) => Math.round(r.top) === y).map((r) => Math.round(r.height))).size === 1) };
});
t('« Dans le détail » : deux colonnes, les cartes d’une rangée à la même hauteur', grille.colonnes === 2 && grille.rangsEgaux, JSON.stringify(grille));
t('la frise du programme situe aujourd’hui', /1999[\s\S]*2001[\s\S]*Aujourd’hui/i.test(await fiche.locator('.porteur-frise').innerText()));
t('le détail range chaque valeur dans son groupe, la précision en petit',
  (await fiche.locator('.porteur-groupe').count()) >= 7 && /606 km/.test(await fiche.locator('.porteur-groupe[data-groupe="performances"]').innerText()));

console.log('\n== À l’échelle ==');
t('le dessin est là, avec une personne de 1,80 m et les cotes sourcées',
  (await fiche.locator('.gabarit svg').count()) === 1 && (await fiche.locator('.gabarit__personne').count()) === 1
  && /12,64 m hors tout/.test(await fiche.locator('.gabarit').innerText()) && /10,69 m de rotor/.test(await fiche.locator('.gabarit').innerText()));
await fiche.locator('.porteur-echelle__choix').selectOption('H225');
await page.waitForTimeout(300);
t('on peut le mettre à côté d’un autre porteur, à la même échelle', (await fiche.locator('.gabarit__appareil').count()) === 2
  && /H225/.test(await fiche.locator('.gabarit').innerText()));

console.log('\n== Au clavier ==');
await page.locator('body').click({ position: { x: 5, y: 400 } });
await page.keyboard.press('ArrowRight');
await page.waitForTimeout(500);
t('→ passe à l’appareil suivant', (await page.locator('.porteur-fiche__code').innerText()).trim() === 'H135');
await page.keyboard.press('ArrowLeft');
await page.waitForTimeout(500);
t('← revient au précédent', (await page.locator('.porteur-fiche__code').innerText()).trim() === 'H130');
t('le bandeau dit où l’on est, et mène aux voisins', /H130\s*2 \/ 23/.test(await page.locator('.porteurs-bandeau').innerText())
  && (await page.locator('.porteurs-bandeau__voisin').count()) === 2);
t('le pied de fiche mène aussi aux voisins', (await page.locator('.porteur-voisin[data-code]').count()) === 2);
await page.keyboard.press('Escape');
await page.waitForTimeout(500);
t('Échap revient à la galerie, le focus sur la carte quittée', await page.locator('.porteurs__vue--galerie').isVisible()
  && await page.evaluate(() => document.activeElement && document.activeElement.dataset.code === 'H130'));
await page.locator('.porteur-carte__lien[data-code="H175M"]').click();
await page.waitForTimeout(500);
await page.goBack();
await page.waitForTimeout(500);
t('« Précédent » du navigateur ramène à la galerie', (await page.locator('.porteur-fiche').count()) === 0 || await page.locator('.porteurs__vue--fiche').isHidden());

console.log('\n== Une fiche presque vide (démonstrateur) ==');
await page.goto(B + '/index.html#porteur=DISRUPTIVELAB', { waitUntil: 'networkidle' });
await page.waitForTimeout(700);
const vide = await page.locator('.porteur-fiche').innerText();
t('pas de tuile vide : ce qui manque est nommé en une ligne, « à renseigner »',
  (await page.locator('.porteur-tuile').count()) === 0 && /Aucun chiffre publié[\s\S]*à renseigner/.test(await page.locator('.porteur-essentiel__manque').innerText()));
t('pas de dessin sans dimensions, et la fiche le dit', /Pas encore de dessin à l’échelle/.test(vide) && (await page.locator('.porteur-fiche .gabarit').count()) === 0);
t('sa phase le dit : démonstrateur', /Démonstrateur/.test(await page.locator('.porteur-fiche__etat').innerText()));

/* =========================================================================
   3. Les liens vers une fiche
   ========================================================================= */

console.log('\n== Arriver par un lien ==');
await ctx.close();
for (const code of ['H140', 'PIONEERLAB', 'U145']) {
  const n = await nouvelle();
  await n.page.goto(B + '/index.html#porteur=' + code, { waitUntil: 'networkidle' });
  await n.page.waitForTimeout(800);
  const titre = await n.page.locator('.porteur-fiche__code').innerText().catch(() => '');
  const haut = await n.page.locator('.porteur-fiche__tete').evaluate((e) => e.getBoundingClientRect().top).catch(() => 9999);
  t(`index.html#porteur=${code} ouvre sa fiche, à l’écran`, titre.trim() === code && haut < 900, `(${titre}, ${haut})`);
  await n.ctx.close();
}
({ ctx, page } = await nouvelle());
/* Le lien d'un espace de pôle, tel quel : une personne d'une squad, la
   puce de son appareil. */
await page.goto(B + '/etiia.html', { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await page.locator('#zone-reperes .equipe__tuile').first().evaluate((e) => e.scrollIntoView({ block: 'center' }));
await page.locator('#zone-reperes .equipe__tuile').first().click();
await page.waitForTimeout(700);
const puce = page.locator('#zone-reperes a.appareil-puce[href^="index.html#porteur="]').first();
const codePuce = (await puce.innerText()).trim();
await puce.evaluate((e) => e.scrollIntoView({ block: 'center' }));
await puce.click();
await page.waitForTimeout(1500);
t(`depuis un espace de pôle, la puce « ${codePuce} » mène à sa fiche`,
  /index\.html#porteur=/.test(page.url()) && (await page.locator('.porteur-fiche__code').innerText().catch(() => '')).trim() === codePuce, page.url());

/* =========================================================================
   4. Comparer
   ========================================================================= */

console.log('\n== Comparer ==');
await page.goto(B + '/index.html', { waitUntil: 'networkidle' });
await page.waitForTimeout(600);
await page.locator('.porteurs__comparer').click();
await page.locator('.porteur-carte__choisir[data-code="H125"]').click();
await page.locator('.porteur-carte__choisir[data-code="H225"]').click();
t('le tiroir montre les deux appareils choisis', /H125[\s\S]*H225/.test(await page.locator('.porteurs__tiroir').innerText()));
await page.locator('.porteurs__tiroir-go').click();
await page.waitForTimeout(800);
t('« Comparer » ouvre la comparaison, portée par l’adresse', (await page.locator('.comparateur').count()) === 1 && /comparer=H125&comparer=H225/.test(page.url()));
const colonnes = await page.locator('.comparateur__entete').allInnerTexts();
t('deux colonnes, dans l’ordre choisi', colonnes.join(',') === 'H125,H225', colonnes.join(','));
const ligneMasse = page.locator('.comparateur__ligne').filter({ has: page.locator('.comparateur__libelle', { hasText: 'Masse maximale au décollage' }) });
t('la valeur la plus grande est marquée, l’écart au premier est dit',
  /le plus lourd/.test(await ligneMasse.locator('.comparateur__cellule--1').innerText()) && /×\s*4,9\s*\/\s*H125/.test(await ligneMasse.locator('.comparateur__cellule--1').innerText()),
  await ligneMasse.innerText());
t('les deux sont dessinés à la même échelle', (await page.locator('.comparateur .gabarit__appareil').count()) === 2);
await page.locator('#comparer-choix-2').selectOption('NH90');
await page.waitForTimeout(600);
t('on en ajoute un troisième', (await page.locator('.comparateur__entete').allInnerTexts()).join(',') === 'H125,H225,NH90');
t('aucune erreur JavaScript jusqu’ici', err.length === 0, err.join(' | '));

console.log('\n== Les crédits photos du pied de page ==');
await page.locator('[data-credits-photos]').first().click();
await page.waitForTimeout(800);
const credits = await page.locator('[role="dialog"] .porteurs__credits-nom').allTextContents();
t(`la fenêtre crédite les ${avecPhoto.length} photos de la flotte`, avecPhoto.every((a) => credits.includes(a.fiche.nom || a.code)), credits.length);
await page.keyboard.press('Escape');
await ctx.close();

/* =========================================================================
   6. Téléphone, thème sombre, mouvement réduit
   ========================================================================= */

console.log('\n== Téléphone (390 px) et thème sombre ==');
({ ctx, page } = await nouvelle({ viewport: { width: 390, height: 844 }, colorScheme: 'dark' }));
for (const [adresse, quoi] of [['/index.html', 'la galerie'], ['/index.html#porteur=H145', 'une fiche'],
  ['/index.html#comparer=H125&comparer=H175&comparer=TIGRE', 'la comparaison']]) {
  await page.goto(B + adresse, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  t(`aucun défilement horizontal à 390 px : ${quoi}`, !(await debordement(page)));
}
await page.goto(B + '/index.html', { waitUntil: 'networkidle' });
await page.waitForTimeout(500);
const deux = await page.locator('.porteurs__marche[data-categorie="civil"] .porteur-carte').evaluateAll((l) => l[0].getBoundingClientRect().top === l[1].getBoundingClientRect().top && l[2].getBoundingClientRect().top > l[0].getBoundingClientRect().top);
t('deux cartes par rangée sur téléphone', deux);
await page.goto(B + '/index.html#porteur=H160', { waitUntil: 'networkidle' });
await page.waitForTimeout(800);
const contrastes = await page.evaluate(() => {
  const lum = (rgb) => {
    const [r, g, b] = rgb.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const fond = (n) => { for (let e = n; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (c && !/rgba\(0, 0, 0, 0\)|transparent/.test(c)) return c; } return 'rgb(255,255,255)'; };
  const mesure = (sel) => { const n = document.querySelector(sel); if (!n) return 0; const a = lum(getComputedStyle(n).color); const b = lum(fond(n)); return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); };
  return { question: mesure('.porteur-tuile__question'), libelle: mesure('.porteur-tuile__libelle'), note: mesure('.porteur-ligne__note') };
});
t('en sombre, les textes de la fiche tiennent 4,5:1', Object.values(contrastes).every((c) => c >= 4.5), JSON.stringify(contrastes));
await ctx.close();

console.log('\n== Mouvement réduit ==');
({ ctx, page } = await nouvelle({ reducedMotion: 'reduce' }));
await page.goto(B + '/index.html#porteur=H125', { waitUntil: 'networkidle' });
await page.waitForTimeout(500);
t('la fiche arrive sans animation', await page.evaluate(() => getComputedStyle(document.querySelector('.porteur-fiche')).animationName === 'none'
  && getComputedStyle(document.querySelector('.porteur-jauge__moi')).animationName === 'none'));
await ctx.close();

t('aucune erreur JavaScript', err.length === 0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close(); process.exit(ko ? 1 : 0);

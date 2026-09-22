// Non-régressions de la recherche documentaire.
//
//   1. lancer le site :  python3 -m http.server 8111
//   2. npm install playwright
//   3. node tests/docsearch.regressions.mjs
//
// Chaque test correspond à un défaut trouvé par la relecture adverse et
// corrigé. Ils existent pour que ces défauts ne reviennent pas.

import { chromium } from 'playwright';
const B = process.env.BASE || 'http://localhost:8111';
const nav = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium' });
const page = await (await nav.newContext({viewport:{width:1440,height:900}})).newPage();
const err=[]; page.on('pageerror',e=>err.push(e.message));
await page.goto(B + '/docsearch.html',{waitUntil:'networkidle'});
await page.waitForTimeout(600);
let ok=0,ko=0; const t=(n,c,d='')=>{c?(ok++,console.log(`  OK    ${n}`)):(ko++,console.log(`  ÉCHEC ${n} ${d}`))};

console.log('== Défaut 1 : le filtrage par porteur existe ==');
// La colonne de facettes a laissé place à trois menus déroulants et aux
// tuiles d'exploration par type — c'est la mise en page voulue. Le contrôle
// porte donc sur la CAPACITÉ de filtrer, pas sur la forme du contrôle.
const filtres = await page.evaluate(() => ({
  menus: ['ds-metier', 'ds-porteur', 'ds-pole']
    .filter(id => document.getElementById(id)),
  typesParTuile: [...document.querySelectorAll('[data-action="filtrer-type"]')].length,
}));
t('les trois menus de filtre sont présents', filtres.menus.length === 3,
  JSON.stringify(filtres.menus));
t('le filtrage par type passe par les tuiles', filtres.typesParTuile >= 5,
  `(${filtres.typesParTuile} tuiles)`);

console.log('\n== Défaut 3 : le lien d\'évitement préserve la recherche ==');
await page.fill('#ds-champ','harnais'); await page.waitForTimeout(700);
const avant = await page.locator('#ds-resultats > *').count();
await page.evaluate(()=>{ const a=document.querySelector('a[href="#contenu"], a[class*="evitement"], .lien-evitement'); if(a) a.click(); });
await page.waitForTimeout(600);
const apres = await page.locator('#ds-resultats > *').count();
const req = await page.inputValue('#ds-champ');
t('la requête survit au lien d\'évitement', req==='harnais', `("${req}")`);
t('les résultats survivent au lien d\'évitement', apres===avant, `(${avant} -> ${apres})`);

console.log('\n== Défaut 4 : le focus ne retombe pas sur <body> ==');
await page.fill('#ds-champ',''); await page.waitForTimeout(600);
const parcourir = page.locator('button').filter({hasText:/parcourir les/i}).first();
if (await parcourir.count()) {
  await parcourir.focus(); await parcourir.press('Enter'); await page.waitForTimeout(600);
  const cible = await page.evaluate(()=>document.activeElement.tagName+(document.activeElement.id?'#'+document.activeElement.id:''));
  t('le focus est replacé ailleurs que sur BODY', !/^BODY$/.test(cible), `(${cible})`);
} else t('bouton "Parcourir" présent', false);

console.log('\n== Proposer un document reste atteignable depuis l\'accueil ==');
const propAccueil = await page.evaluate(() => [...document.querySelectorAll('button')]
  .filter(b => /Proposer un document/.test(b.textContent)
            && b.getBoundingClientRect().height > 0).length);
t('un bouton « Proposer » est visible sur l\'accueil', propAccueil >= 1, `(${propAccueil})`);

console.log('\n== Défaut 5 : pas de role=option sur une carte contenant des contrôles ==');
const faute = await page.evaluate(()=>[...document.querySelectorAll('[role="option"]')]
  .filter(o=>o.querySelector('a,button,input')).length);
t('aucune option ARIA ne contient de contrôle interactif', faute===0, `(${faute})`);

console.log('\n== Défaut 6 : "/" neutralisé quand une modale est ouverte ==');
// Selon l'état de la page, plusieurs boutons « Proposer » coexistent dont
// certains masqués : on cible celui qui est réellement visible.
const proposer = page.locator('button:visible').filter({hasText:/proposer un document/i}).first();
if (await proposer.count()) {
  await proposer.click(); await page.waitForTimeout(500);
  await page.keyboard.press('/'); await page.waitForTimeout(300);
  const dansModale = await page.evaluate(()=>{
    const a=document.activeElement; const d=document.querySelector('[role="dialog"]');
    return !!(d && a && d.contains(a));
  });
  t('le focus reste dans la modale après "/"', dansModale);
  await page.keyboard.press('Escape'); await page.waitForTimeout(400);
} else t('bouton "Proposer un document" présent', false);

console.log('\n== Défaut 7 : contraste du texte d\'aide ==');
const contraste = await page.evaluate(()=>{
  const lum = c => { const [r,g,b]=c.match(/\d+/g).map(Number).map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)});
    return 0.2126*r+0.7152*g+0.0722*b; };
  const e = document.getElementById('ds-aide'); if(!e) return null;
  const s = getComputedStyle(e);
  let fond = s.backgroundColor, n = e;
  while ((fond==='rgba(0, 0, 0, 0)'||fond==='transparent') && n.parentElement) { n=n.parentElement; fond=getComputedStyle(n).backgroundColor; }
  const l1=lum(s.color), l2=lum(fond);
  return { ratio: +(((Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05)).toFixed(2)), taille: s.fontSize, couleur: s.color };
});
if (contraste) {
  const seuil = parseFloat(contraste.taille) >= 18.66 ? 3 : 4.5;
  t(`contraste de la ligne d'aide : ${contraste.ratio}:1 (seuil AA ${seuil}:1)`, contraste.ratio >= seuil, JSON.stringify(contraste));
} else t('ligne d\'aide #ds-aide trouvée', false);

console.log('\n== Défaut 8 : le panneau de suggestions reste cliquable ==');
// L'animation d'apparition de .ds-entete en fait un contexte d'empilement,
// qui emprisonnait le z-index du panneau : le menu « Trier par » et les
// cartes de résultats se dessinaient par-dessus, et un clic sur les
// dernières propositions ouvrait le tri. Le piège revient dès qu'on animera
// une autre section : on vérifie donc le résultat, pas la règle CSS.
for (const [larg, haut] of [[390, 844], [1280, 900]]) {
  const ctx = await nav.newContext({ viewport: { width: larg, height: haut } });
  const p2 = await ctx.newPage();
  await p2.goto(B + '/docsearch.html', { waitUntil: 'networkidle' });
  await p2.waitForTimeout(600);
  await p2.fill('#ds-champ', 'procedure');
  await p2.waitForTimeout(700);
  const vol = await p2.evaluate(() => {
    const panneau = document.querySelector('.ds-suggestions');
    if (!panneau || !panneau.getClientRects().length) return { absent: true };
    const b = panneau.getBoundingClientRect();
    // On balaie la MOITIÉ BASSE du panneau : c'est là que le menu de tri et
    // les cartes mordaient, et la hauteur exacte du recouvrement varie avec
    // la largeur de la fenêtre.
    let voles = 0; const coupables = new Set();
    for (let y = Math.round(b.top + b.height / 2); y < b.bottom - 2; y += 8) {
      for (let x = Math.round(b.left) + 6; x < b.right - 6; x += 24) {
        const e = document.elementFromPoint(x, y);
        if (!e) continue;
        if (e !== panneau && !panneau.contains(e)) {
          voles++; coupables.add(e.tagName + '.' + (e.className || ''));
        }
      }
    }
    return { voles, coupables: [...coupables] };
  });
  t(`${larg}×${haut} : la moitié basse du panneau de suggestions reçoit le clic`,
    !vol.absent && vol.voles === 0, JSON.stringify(vol));
  await ctx.close();
}

t('aucune erreur JavaScript', err.length===0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close(); process.exit(ko?1:0);

// Non-régressions de la recherche documentaire.
//
//   1. lancer le site :  python3 -m http.server 8111
//   2. npm install playwright
//   3. node tests/docsearch.regressions.mjs
//
// Chaque test correspond à un défaut trouvé par la relecture adverse et
// corrigé. Ils existent pour que ces défauts ne reviennent pas.

import { chromium } from 'playwright';
const nav = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium' });
const page = await (await nav.newContext({viewport:{width:1440,height:900}})).newPage();
const err=[]; page.on('pageerror',e=>err.push(e.message));
await page.goto('http://localhost:8111/docsearch.html',{waitUntil:'networkidle'});
await page.waitForTimeout(600);
let ok=0,ko=0; const t=(n,c,d='')=>{c?(ok++,console.log(`  OK    ${n}`)):(ko++,console.log(`  ÉCHEC ${n} ${d}`))};

console.log('== Défaut 1 : la facette "porteur" ==');
const groupes = await page.evaluate(()=>[...document.querySelectorAll('h2,h3,legend,.facettes__titre,[class*="facette"] > :first-child')]
  .map(e=>e.textContent.trim()).filter(x=>/type|métier|périmètre|porteur/i.test(x)));
t('les 4 dimensions de facette sont présentes',
  ['type','métier','périmètre','porteur'].every(d=>groupes.some(g=>new RegExp(d,'i').test(g))),
  JSON.stringify(groupes));

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

console.log('\n== Défaut 5 : pas de role=option sur une carte contenant des contrôles ==');
const faute = await page.evaluate(()=>[...document.querySelectorAll('[role="option"]')]
  .filter(o=>o.querySelector('a,button,input')).length);
t('aucune option ARIA ne contient de contrôle interactif', faute===0, `(${faute})`);

console.log('\n== Défaut 6 : "/" neutralisé quand une modale est ouverte ==');
const proposer = page.locator('button').filter({hasText:/proposer un document/i}).first();
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

t('aucune erreur JavaScript', err.length===0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close(); process.exit(ko?1:0);

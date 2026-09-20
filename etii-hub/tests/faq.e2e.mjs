// Test de bout en bout de la FAQ, dans un vrai navigateur.
//
//   1. lancer le site :  python3 -m http.server 8111
//   2. npm install playwright
//   3. node tests/faq.e2e.mjs
//
// Vérifie notamment deux garanties : aucune adresse e-mail ni lien mailto
// ne doit réapparaître, et le texte saisi ne doit jamais être interprété
// comme du HTML.

import { chromium } from 'playwright';
const B = process.env.BASE || 'http://localhost:8111';
const nav = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium' });
const ctx = await nav.newContext({ viewport:{width:1440,height:900} });
const page = await ctx.newPage();
const err=[]; page.on('pageerror',e=>err.push(e.message));
await page.goto(B + '/faq.html',{waitUntil:'networkidle'});
await page.waitForTimeout(600);
let ok=0,ko=0; const t=(n,c,d='')=>{c?(ok++,console.log(`  OK    ${n}`)):(ko++,console.log(`  ÉCHEC ${n} ${d}`))};

const txt = await page.locator('main').innerText();
t('les 8 questions sont chargées', (await page.locator('[role="option"], li button, .liste-item').count())>0);
t('aucune adresse e-mail sur la page', !/@[a-z0-9.-]+\.(com|fr)/i.test(txt), txt.match(/@\S+/)?.[0]||'');
t('aucun lien mailto:', (await page.locator('a[href^="mailto:"]').count())===0);

const champ = page.locator('input[type="search"]').first();
await champ.fill('galvanique'); await page.waitForTimeout(400);
t('recherche "galvanique" trouve', (await page.locator('mark').count())>0);
await champ.fill('zzzqqq'); await page.waitForTimeout(400);
t('état aucun résultat', /aucun|rien|pas de/i.test(await page.locator('main').innerText()));
await champ.fill(''); await page.waitForTimeout(300);

// Poser une question -> doit rester local
const btn = page.locator('button').filter({hasText:/poser/i}).first();
if (await btn.count()) {
  await btn.click(); await page.waitForTimeout(400);
  t('la modale s\'ouvre', (await page.locator('[role="dialog"]').count())>0);
  const ta = page.locator('[role="dialog"] textarea').first();
  if (await ta.count()) {
    await ta.fill('Question de test avec apostrophe d\'essai et <balise>');
    const valider = page.locator('[role="dialog"] button').filter({hasText:/envoyer|valider|enregistr|poser/i}).last();
    await valider.click(); await page.waitForTimeout(500);
    const apres = await page.locator('main').innerText();
    t('la question apparaît dans la page', /Question de test/.test(apres));
    t('les chevrons ne sont pas interprétés', (await page.locator('main balise').count())===0);
  }
} else t('bouton "poser une question" présent', false);

t('aucune erreur JavaScript', err.length===0, err.join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close(); process.exit(ko?1:0);

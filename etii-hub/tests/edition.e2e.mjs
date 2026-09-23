// Le mode édition — exécuter depuis etii-hub/ avec un serveur :
//   python3 -m http.server 8111 &   puis   node tests/edition.e2e.mjs
//
// Tout se modifie dans le site : on ajoute, modifie et supprime une
// alerte, un rendez-vous, un porteur, une personne, une squad, un
// document, une question et un compte-rendu, là où ils s'affichent, et
// chaque modification se voit sur les autres pages et survit au
// rechargement.
//
// Trois magasins :
//   1. le navigateur — le serveur de test n'a pas de runtime claude.ai ;
//   2. la base partagée — un runtime simulé, qui vérifie aussi la
//      grammaire des chemins du vrai (lettres, chiffres, « _ - . ~ : @ + ») ;
//   3. un runtime qui ne répond pas — la page s'affiche sur ses fichiers,
//      sans commande d'édition.

import { chromium } from 'playwright';

const B = process.env.BASE || 'http://localhost:8111';
let ok = 0, ko = 0;
const t = (n, c, d = '') => { c ? (ok++, console.log(`  OK    ${n}`)) : (ko++, console.log(`  ÉCHEC ${n} ${d}`)); };

const nav = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const err = [];

const jourIso = (decalage) => {
  const d = new Date(Date.now() + decalage * 86400000);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
};

async function nouvellePage(initScript) {
  const ctx = await nav.newContext({ viewport: { width: 1366, height: 900 } });
  if (initScript) await ctx.addInitScript(initScript);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => err.push(e.message));
  return page;
}

/* Les gestes communs aux formulaires d'édition. */
const outils = (page) => ({
  attendre: (ms) => page.waitForTimeout(ms),
  async remplir(libelle, valeur) {
    const champ = page.locator('.modale--formulaire .champ')
      .filter({ has: page.locator('.champ__etiquette', { hasText: libelle }) })
      .locator('input, textarea, select').first();
    if ((await champ.evaluate((n) => n.tagName)) === 'SELECT') await champ.selectOption(valeur);
    else await champ.fill(valeur);
  },
  async enregistrer() {
    await page.locator('.modale--formulaire .modale__actions .bouton--principal').click();
    await page.waitForSelector('.modale--formulaire', { state: 'detached', timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(500);
  },
  async confirmer() {
    await page.locator('.modale__boite').last().locator('.modale__actions .bouton--danger').click();
    await page.waitForTimeout(700);
  },
  /* Au milieu de la fenêtre : collé en haut, un bouton passerait sous la
     barre du site. */
  async centrer(locator) {
    await locator.first().evaluate((e) => e.scrollIntoView({ block: 'center', behavior: 'instant' }));
    await page.waitForTimeout(150);
  },
  async basculer() {
    await page.click('.bascule-edition');
    await page.waitForTimeout(300);
  },
  enEdition: () => page.evaluate(() => document.documentElement.classList.contains('mode-edition'))
});

/* =========================================================================
   1. Dans ce navigateur
   ========================================================================= */

let page = await nouvellePage();
let o = outils(page);
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await page.evaluate(() => { for (const k of Object.keys(localStorage)) if (/^etii:(modifications:|journal|edition\.|editeur\.)/.test(k)) localStorage.removeItem(k); });
await page.reload({ waitUntil: 'networkidle' });
await o.attendre(900);

console.log('== La bascule ==');
t('un bouton « Modifier » dans la barre, et aucune commande d’édition visible',
  (await page.locator('.bascule-edition').count()) === 1 && (await page.locator('.edition-seulement:visible').count()) === 0);
await o.basculer();
t('allumé : le bandeau le dit, les commandes apparaissent',
  await o.enEdition() && /navigateur seulement/.test(await page.locator('.edition-bandeau').innerText())
  && (await page.locator('.edition-seulement:visible').count()) > 5);

console.log('\n== « À venir » : un rendez-vous ==');
const rdvAvant = await page.locator('#zone-agenda .agenda__rdv').count();
await o.centrer(page.locator('#zone-agenda .edition-ajout'));
await page.locator('#zone-agenda .edition-ajout').click();
await o.remplir('Titre', 'Revue d’essai des faisceaux');
await o.remplir('Date', jourIso(1));
await o.remplir('Lieu', 'Salle B');
await o.enregistrer();
const rdv = page.locator('#zone-agenda .agenda__rdv', { hasText: 'Revue d’essai des faisceaux' });
/* En tête, à sa date : un rendez-vous de la base peut tomber le même
   jour (la frise suit le calendrier réel), l'ordre entre eux est libre. */
t('ajouté, il arrive en tête : c’est le plus proche', (await rdv.count()) === 1
  && (await page.locator('#zone-agenda .agenda__rdv').first().getAttribute('data-date')) === jourIso(1)
  && /demain/i.test(await rdv.innerText()), `(${rdvAvant} avant)`);
await o.centrer(rdv);
await rdv.locator('.barre-edition__bouton', { hasText: 'Modifier' }).click();
await o.remplir('Titre', 'Revue d’essai des faisceaux (déplacée)');
await o.enregistrer();
t('modifié, il se corrige sur place', (await page.locator('#zone-agenda .agenda__rdv', { hasText: '(déplacée)' }).count()) === 1
  && (await page.locator('#zone-agenda .agenda__rdv').count()) === rdvAvant + 1);

console.log('\n== L’historique ==');
await page.evaluate(() => window.scrollTo(0, 0));
await page.locator('.edition-bandeau__historique').click();
await o.attendre(500);
const histo = page.locator('.modale .historique__entree');
t('le bandeau ouvre l’historique : les deux gestes, le plus récent d’abord',
  (await histo.count()) === 2 && /Modification/i.test(await histo.nth(0).locator('.historique__action').innerText())
  && /Ajout/i.test(await histo.nth(1).locator('.historique__action').innerText()), `(${await histo.count()})`);
t('chacun dit sa rubrique et son élément',
  /À venir/.test(await histo.nth(0).locator('.historique__rubrique').innerText())
  && /Revue d’essai des faisceaux \(déplacée\)/.test(await histo.nth(0).locator('.historique__element').innerText()));
t('une modification dit ce qui a changé, avant → après',
  /Titre : « Revue d’essai des faisceaux » → « Revue d’essai des faisceaux \(déplacée\) »/.test(await histo.nth(0).locator('.historique__detail').innerText()),
  await histo.nth(0).locator('.historique__detail').innerText());
t('un ajout résume ses champs', /Lieu : « Salle B »/.test(await histo.nth(1).locator('.historique__detail').innerText()));
await page.keyboard.press('Escape');
await o.attendre(300);

console.log('\n== Le bandeau d’alertes ==');
await page.evaluate(() => window.scrollTo(0, 0));
await page.locator('.kiosque__alertes-modifier').click();
await o.attendre(300);
const nbAlertes = await page.locator('.modale .edition-liste__element').count();
t('le crayon du bandeau ouvre la liste des alertes', nbAlertes >= 1, `(${nbAlertes})`);
await page.locator('.modale button', { hasText: 'Ajouter une alerte' }).click();
await o.attendre(500);
await page.fill('.modale--editeur input[placeholder^="Maintenance de la plateforme"]', 'Coupure réseau d’essai vendredi.');
await page.click('.modale--editeur .modale__actions button:has-text("Publier")');
await o.attendre(1000);
t('une alerte ajoutée défile dans le bandeau', /Coupure réseau d’essai/.test(await page.locator('.kiosque__alertes').innerText()));
await page.locator('.kiosque__alertes-modifier').click();
await o.attendre(300);
await page.locator('.modale .edition-liste__element', { hasText: 'Coupure réseau' }).locator('.barre-edition__bouton--danger').click();
await o.confirmer();
t('supprimée, elle quitte le bandeau', !/Coupure réseau d’essai/.test(await page.locator('.kiosque__alertes').innerText()));

console.log('\n== Les porteurs ==');
const fichesAvant = await page.locator('.porteurs__fiche').count();
await o.centrer(page.locator('.porteurs__barre .edition-ajout'));
await page.locator('.porteurs__barre .edition-ajout').click();
await o.remplir('Code', 'ZXTEST1');
await o.remplir('Nom complet', 'Appareil d’essai');
await o.remplir('Présentation', 'Un porteur ajouté par le test.');
await o.enregistrer();
const ficheEssai = page.locator('.porteurs__fiche', { hasText: 'ZXTEST1' });
t('un porteur ajouté rejoint la galerie', (await page.locator('.porteurs__fiche').count()) === fichesAvant + 1 && (await ficheEssai.count()) === 1);
await o.centrer(ficheEssai);
await ficheEssai.click();
await o.attendre(500);
await page.locator('.porteurs__edition .barre-edition__bouton', { hasText: 'Modifier' }).click();
await o.remplir('Présentation', 'Présentation corrigée par le test.');
await o.enregistrer();
await o.centrer(page.locator('.porteurs__fiche', { hasText: 'ZXTEST1' }));
if (!(await page.locator('.porteurs__detail').count())) { await page.locator('.porteurs__fiche', { hasText: 'ZXTEST1' }).click(); await o.attendre(500); }
t('sa fiche se modifie', /Présentation corrigée par le test/.test(await page.locator('.porteurs__detail').innerText().catch(() => '')));
await page.locator('.porteurs__edition .barre-edition__bouton--danger').click();
await o.confirmer();
t('supprimé, il quitte la galerie', (await page.locator('.porteurs__fiche', { hasText: 'ZXTEST1' }).count()) === 0
  && (await page.locator('.porteurs__fiche').count()) === fichesAvant);

console.log('\n== Un espace de pôle : l’annuaire ==');
await page.goto(`${B}/etiia.html`, { waitUntil: 'networkidle' });
await o.attendre(1200);
t('le mode édition suit d’une page à l’autre', await o.enEdition());
const ligne = page.locator('#annuaire-etiia-organigramme .annuaire__groupe').nth(1).locator('.annuaire__personne').nth(1);
const nomPersonne = (await ligne.locator('.annuaire__nom').innerText()).trim();
await o.centrer(ligne);
await ligne.locator('.barre-edition__bouton', { hasText: 'Modifier' }).click();
await o.remplir('Rôle', 'Ingénieur essais (modifié)');
await o.enregistrer();
const exactement = (nom) => page.locator('.annuaire__nom', { hasText: new RegExp('^' + nom + '$') });
t('le rôle d’une personne se modifie dans l’annuaire du pôle',
  (await page.locator('#annuaire-etiia-organigramme .annuaire__personne').filter({ has: exactement(nomPersonne) }).locator('.annuaire__role').innerText()).trim() === 'Ingénieur essais (modifié)');
await o.centrer(page.locator('#annuaire-etiia-organigramme .annuaire__ajouts'));
await page.locator('#annuaire-etiia-organigramme .annuaire__ajouts button', { hasText: 'Une squad' }).click();
await o.remplir('Nom de la squad', 'Squad Essai');
await o.enregistrer();
t('une squad ajoutée apparaît, vide, et le dit',
  /Personne dans cette squad/.test(await page.locator('#annuaire-etiia-organigramme .annuaire__groupe', { hasText: 'Squad Essai' }).innerText().catch(() => '')));

console.log('\n== Un espace de pôle : documents et FAQ ==');
const totalDocs = async () => Number(((await page.locator('#zone-documents .pole-docs__pied a').innerText()).match(/\((\d+)\)/) || [])[1]);
const docsAvant = await totalDocs();
await o.centrer(page.locator('#zone-documents .edition-ajout'));
await page.locator('#zone-documents .edition-ajout').click();
await o.remplir('Titre', 'Note d’essai du pôle');
await o.remplir('Référence', 'ETII-TEC-998');
await o.enregistrer();
t('un document ajouté, daté du jour, rejoint les documents récents du pôle',
  (await page.locator('#zone-documents .pole-doc', { hasText: 'Note d’essai du pôle' }).count()) === 1
  && (await totalDocs()) === docsAvant + 1, `(${docsAvant} → ${await totalDocs()})`);
await o.centrer(page.locator('#zone-faq .edition-ajout'));
await page.locator('#zone-faq .edition-ajout').click();
await o.remplir('Question', 'Question d’essai du pôle ?');
await o.remplir('Réponse', 'Réponse d’essai.');
await o.remplir('Pôle', 'ETIIA');
await o.enregistrer();
t('une question ajoutée rejoint la FAQ du pôle', /Question d’essai du pôle/.test(await page.locator('#zone-faq').innerText()));

console.log('\n== Les autres pages voient les mêmes données ==');
await page.goto(`${B}/organigramme.html#pole=ETIIA`, { waitUntil: 'networkidle' });
await o.attendre(900);
await page.fill('#org-recherche', nomPersonne);
await o.attendre(500);
t('l’organigramme montre le rôle modifié dans le pôle',
  /Ingénieur essais \(modifié\)/.test(await page.locator('.org-zone').innerText()));
await page.fill('#org-recherche', '');
await o.attendre(400);
t('et la squad ajoutée', (await page.locator('.org-squad[data-squad="Squad Essai"]').count()) === 1);
await page.goto(`${B}/docsearch.html#q=ETII-TEC-998`, { waitUntil: 'networkidle' });
await o.attendre(900);
t('la recherche documentaire trouve le document ajouté', (await page.locator('.ds-carte', { hasText: 'Note d’essai du pôle' }).count()) === 1);
await page.goto(`${B}/faq.html#pole=ETIIA`, { waitUntil: 'networkidle' });
await o.attendre(800);
t('la base de connaissances contient la question ajoutée', (await page.locator('.faq__item', { hasText: 'Question d’essai du pôle' }).count()) === 1);

console.log('\n== L’organigramme ==');
await page.goto(`${B}/organigramme.html#pole=ETIIA`, { waitUntil: 'networkidle' });
await o.attendre(900);
await page.locator('.org-squad[data-squad="Squad Essai"] > summary').click();
await page.locator('.org-squad[data-squad="Squad Essai"] .org-squad__edition button', { hasText: 'Une personne ici' }).click();
await page.waitForSelector('.modale--formulaire');
await o.remplir('Nom', 'Personne Essai');
await o.remplir('Rôle', 'Ingénieure essais');
await o.enregistrer();
t('une personne ajoutée dans une squad y apparaît, volet ouvert',
  (await page.locator('.org-squad[data-squad="Squad Essai"][open] .org-personne', { hasText: 'Personne Essai' }).count()) === 1);
await page.locator('.org-personne', { hasText: 'Personne Essai' }).first().click();
await page.waitForSelector('.org-fiche__edition');
await page.locator('.org-fiche__edition .barre-edition__bouton', { hasText: 'Modifier' }).click();
await page.waitForSelector('.modale--formulaire');
await o.remplir('Rôle', 'Ingénieure essais sol');
await o.enregistrer();
t('sa fiche se modifie', /Ingénieure essais sol/.test(await page.locator('.org-personne', { hasText: 'Personne Essai' }).first().innerText()));
await page.locator('.org-squad[data-squad="Squad Essai"] .barre-edition__bouton--danger').click();
await o.confirmer();
t('une squad retirée laisse ses membres dans « À affecter »',
  (await page.locator('.org-squad[data-squad="Squad Essai"]').count()) === 0
  && (await page.locator('.org-squad[data-squad="À affecter"]').count()) === 1);
await page.locator('.org-squad[data-squad="À affecter"] > summary').click();
await page.locator('.org-personne', { hasText: 'Personne Essai' }).first().click();
await page.waitForSelector('.org-fiche__edition');
await page.locator('.org-fiche__edition .barre-edition__bouton--danger').click();
await o.confirmer();
t('une personne se retire depuis sa fiche', (await page.locator('.org-personne', { hasText: 'Personne Essai' }).count()) === 0
  && (await page.locator('.org-squad[data-squad="À affecter"]').count()) === 0);

console.log('\n== La FAQ, les documents, les comptes-rendus ==');
await page.goto(`${B}/faq.html`, { waitUntil: 'networkidle' });
await o.attendre(700);
await page.locator('.faq__bascule', { hasText: 'Question d’essai du pôle' }).click();
await page.locator('.faq__item[data-ouvert="oui"] .faq__edition .barre-edition__bouton', { hasText: 'Modifier' }).click();
await o.remplir('Réponse', 'Réponse d’essai, corrigée.');
await o.enregistrer();
t('une question se modifie depuis la base, et reste dépliée',
  /Réponse d’essai, corrigée/.test(await page.locator('.faq__item[data-ouvert="oui"]').innerText().catch(() => '')));
await page.locator('.faq__item[data-ouvert="oui"] .faq__edition .barre-edition__bouton--danger').click();
await o.confirmer();
t('et se retire', (await page.locator('.faq__item', { hasText: 'Question d’essai du pôle' }).count()) === 0);

await page.goto(`${B}/docsearch.html#q=ETII-TEC-998`, { waitUntil: 'networkidle' });
await o.attendre(900);
await page.locator('.ds-carte', { hasText: 'Note d’essai du pôle' }).locator('.ds-carte__edition .barre-edition__bouton', { hasText: 'Modifier' }).click();
await o.remplir('Titre', 'Note d’essai du pôle (v2)');
await o.enregistrer();
t('un document se modifie depuis sa carte, la recherche en cours conservée',
  (await page.locator('.ds-carte', { hasText: '(v2)' }).count()) === 1 && (await page.inputValue('#ds-champ')) === 'ETII-TEC-998');
await page.locator('.ds-carte', { hasText: '(v2)' }).locator('.ds-carte__edition .barre-edition__bouton--danger').click();
await o.confirmer();
t('et se retire', (await page.locator('.ds-carte', { hasText: '(v2)' }).count()) === 0);

await page.goto(`${B}/reunions.html`, { waitUntil: 'networkidle' });
await o.attendre(700);
const crAvant = await page.locator('.reunion-option').count();
await page.locator('.barre-outils .edition-ajout').click();
await o.remplir('Titre', 'Point d’essai');
await o.remplir('Synthèse', 'Synthèse d’essai.');
await o.remplir('Sujets', 'Masse — dans la tolérance');
await o.enregistrer();
t('un compte-rendu ajouté rejoint la liste', (await page.locator('.reunion-option').count()) === crAvant + 1);
await page.locator('.reunion-option', { hasText: 'Point d’essai' }).click();
await o.attendre(300);
t('ses sujets sont lus « titre — notes »', /Masse/.test(await page.locator('.liseuse__corps').first().innerText())
  && /dans la tolérance/.test(await page.locator('.liseuse__corps').first().innerText()));
await page.locator('.reunions__edition .barre-edition__bouton', { hasText: 'Modifier' }).click();
await o.remplir('Synthèse', 'Synthèse d’essai, corrigée.');
await o.enregistrer();
t('il se modifie et reste ouvert', /Synthèse d’essai, corrigée/.test(await page.locator('.liseuse__corps').first().innerText()));
await page.locator('.reunions__edition .barre-edition__bouton--danger').click();
await o.confirmer();
t('et se retire', (await page.locator('.reunion-option').count()) === crAvant);

console.log('\n== Au rechargement ==');
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await o.attendre(900);
t('le rendez-vous modifié est toujours là', (await page.locator('#zone-agenda .agenda__rdv', { hasText: '(déplacée)' }).count()) === 1);
await o.centrer(page.locator('#zone-agenda .agenda__rdv', { hasText: '(déplacée)' }));
await page.locator('#zone-agenda .agenda__rdv', { hasText: '(déplacée)' }).locator('.barre-edition__bouton--danger').click();
await o.confirmer();
t('supprimé, « À venir » retrouve ses rendez-vous d’origine', (await page.locator('#zone-agenda .agenda__rdv').count()) === rdvAvant);
await o.basculer();
t('« Terminer » éteint le mode, et cela aussi se retient', !(await o.enEdition()));
await page.close();

/* =========================================================================
   2. La base partagée (runtime simulé)
   ========================================================================= */

/* Un runtime claude.ai de poche : `use('db')` et `use('user')`, une base
   rangée dans le localStorage du contexte, la grammaire des chemins du
   vrai. Les réglages arrivent par window.__REGLAGES_RUNTIME. */
const runtime = (reglages) => {
  window.__REGLAGES_RUNTIME = reglages;
  const CLE = 'faux-runtime:db';
  const lire = () => { try { return JSON.parse(localStorage.getItem(CLE) || '{}'); } catch (_e) { return {}; } };
  const ecrire = (b) => localStorage.setItem(CLE, JSON.stringify(b));
  const segment = (s) => {
    if (!/^[A-Za-z0-9_\-.~:@+]+$/.test(s) || s === '.' || s === '..' || s.length > 200) throw new TypeError('segment invalide : ' + s);
  };
  const collection = (chemin) => {
    segment(chemin);
    return {
      path: chemin,
      async get() {
        const docs = Object.entries(lire()[chemin] || {}).map(([id, data]) => ({ id, exists: true, data: () => data }));
        return { docs, size: docs.length, empty: !docs.length };
      },
      doc(id) {
        segment(id);
        return {
          id,
          async set(data) {
            if (window.__REGLAGES_RUNTIME.refuser) throw Object.assign(new Error('refusé'), { code: 'invalid_argument' });
            const b = lire(); (b[chemin] = b[chemin] || {})[id] = JSON.parse(JSON.stringify(data)); ecrire(b);
          },
          async delete() {
            if (window.__REGLAGES_RUNTIME.refuser) throw Object.assign(new Error('refusé'), { code: 'invalid_argument' });
            const b = lire(); if (b[chemin]) delete b[chemin][id]; ecrire(b);
          }
        };
      }
    };
  };
  const db = Object.freeze({ collection, doc: () => { throw new TypeError('non simulé'); } });
  const user = Object.freeze({
    can: async () => window.__REGLAGES_RUNTIME.peut,
    id: async () => 'viewer-essai',
    canEdit: async () => window.__REGLAGES_RUNTIME.peut === true,
    isOwner: async () => false
  });
  window.claude = Object.freeze({
    use: (nom) => {
      if (window.__REGLAGES_RUNTIME.muet) return new Promise(() => {});
      return new Promise((r) => setTimeout(() => r(nom === 'db' ? db : (nom === 'user' ? user : null)), 30));
    }
  });
};

console.log('\n== La base partagée ==');
page = await nouvellePage([runtime.toString(), 'runtime({ peut: true })'].join(';\n').replace(/^/, 'const runtime = ') );
o = outils(page);
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await o.attendre(900);
await o.basculer();
t('le bandeau dit que tout le site verra les modifications',
  /enregistré pour tous les lecteurs du site/.test(await page.locator('.edition-bandeau').innerText()));
await o.centrer(page.locator('#zone-agenda .edition-ajout'));
await page.locator('#zone-agenda .edition-ajout').click();
await o.remplir('Titre', 'Rendez-vous partagé');
await o.remplir('Date', jourIso(2));
await o.enregistrer();
const base = await page.evaluate(() => JSON.parse(localStorage.getItem('faux-runtime:db') || '{}'));
const docsCom = Object.entries(base.modifications_communications || {});
t('l’écriture part dans la base, collection « modifications_communications »',
  docsCom.length === 1 && docsCom[0][1].type === 'agenda' && docsCom[0][1].op === 'maj' && docsCom[0][1].par === 'viewer-essai', JSON.stringify(docsCom).slice(0, 200));
t('et rien dans ce navigateur', await page.evaluate(() => localStorage.getItem('etii:modifications:communications') === null));
t('le rendez-vous s’affiche', (await page.locator('#zone-agenda .agenda__rdv', { hasText: 'Rendez-vous partagé' }).count()) === 1);
/* Un identifiant avec espace et accent (« Personne 22 ») : sa clé doit
   respecter la grammaire, sans quoi le vrai runtime lèverait. */
await page.goto(`${B}/organigramme.html`, { waitUntil: 'networkidle' });
await o.attendre(900);
await page.locator('.org-barre .edition-ajout').click();
await page.waitForSelector('.modale--formulaire');
await o.remplir('Nom', 'Personne Partagée');
await o.remplir('Rôle', 'Technicienne');
await o.enregistrer();
const base2 = await page.evaluate(() => JSON.parse(localStorage.getItem('faux-runtime:db') || '{}'));
t('une personne ajoutée va dans « modifications_organigramme »', Object.keys(base2.modifications_organigramme || {}).length === 1);
await page.close();

/* Un autre lecteur, qui ne peut que lire, sur la même base. */
page = await nouvellePage([runtime.toString(), 'runtime({ peut: false })', 'localStorage.setItem("faux-runtime:db", ' + JSON.stringify(JSON.stringify(base2)) + ')'].join(';\n').replace(/^/, 'const runtime = '));
o = outils(page);
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await o.attendre(900);
t('un autre lecteur voit le rendez-vous partagé', (await page.locator('#zone-agenda .agenda__rdv', { hasText: 'Rendez-vous partagé' }).count()) === 1);
t('mais, sans droit d’écriture, n’a pas de bouton « Modifier »', (await page.locator('.bascule-edition').count()) === 0);
await page.goto(`${B}/organigramme.html#pole=ETIIA`, { waitUntil: 'networkidle' });
await o.attendre(900);
await page.fill('#org-recherche', 'Personne Partagée');
await o.attendre(400);
t('ni aucune commande, et il voit la personne ajoutée', (await page.locator('.org-personne', { hasText: 'Personne Partagée' }).count()) === 1
  && (await page.locator('.edition-seulement:visible').count()) === 0);
await page.close();

/* Le runtime ne dit rien du droit d'écrire, et la base refuse. */
page = await nouvellePage([runtime.toString(), 'runtime({ peut: null, refuser: true })'].join(';\n').replace(/^/, 'const runtime = '));
o = outils(page);
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await o.attendre(900);
await o.basculer();
await o.centrer(page.locator('#zone-agenda .edition-ajout'));
await page.locator('#zone-agenda .edition-ajout').click();
await o.remplir('Titre', 'Rendez-vous refusé');
await page.locator('.modale--formulaire .modale__actions .bouton--principal').click();
await o.attendre(600);
t('une écriture refusée le dit en clair, et la fenêtre reste ouverte',
  /pas le modifier/.test(await page.locator('.modale--formulaire .champ__erreur:not([hidden])').last().innerText().catch(() => ''))
  && (await page.locator('.modale--formulaire').count()) === 1);
await page.keyboard.press('Escape');
await page.close();

console.log('\n== Un runtime qui ne répond pas ==');
page = await nouvellePage([runtime.toString(), 'runtime({ muet: true })'].join(';\n').replace(/^/, 'const runtime = '));
await page.goto(`${B}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(7500);
t('la page s’affiche sur ses fichiers', (await page.locator('#zone-communication .kiosque__carte').count()) >= 3
  && (await page.locator('#zone-agenda .agenda').count()) === 1);
t('sans bouton « Modifier »', (await page.locator('.bascule-edition').count()) === 0);
await page.close();

/* =========================================================================
   4. Servi par Google Apps Script (serveur simulé)
   ========================================================================= */

/* Un google.script.run de poche, qui reprend le contrat de
   tools/apps-script/site/Code.gs : etiiDemarrer, etiiPoser, etiiRetirer,
   et le refus « NON_AUTORISE » d'une adresse absente des éditeurs. La
   base vit dans le localStorage du contexte. */
const fauxGoogle = (reglages) => {
  if (window !== window.top) return;
  const CLE = 'faux-google:base';
  const lire = () => { try { return JSON.parse(localStorage.getItem(CLE) || '{}'); } catch (_e) { return {}; } };
  const ecrire = (b) => localStorage.setItem(CLE, JSON.stringify(b));
  window.__APPELS_GOOGLE = [];
  const serveur = {
    etiiDemarrer() {
      const b = lire();
      const modifications = {};
      for (const [jeu, table] of Object.entries(b)) modifications[jeu] = Object.values(table);
      return { email: reglages.email, peutModifier: reglages.peut, modifications, bases: reglages.bases || {} };
    },
    etiiPoser(jeu, modif) {
      if (!reglages.peut) throw new Error('NON_AUTORISE');
      const b = lire();
      (b[jeu] = b[jeu] || {})[modif.type + '~' + modif.id] = Object.assign({}, modif, { par: reglages.email });
      ecrire(b);
      const j = JSON.parse(localStorage.getItem('faux-google:journal') || '[]');
      j.unshift(Object.assign({ le: new Date().toISOString(), par: reglages.email, rubrique: modif.type === 'agenda' ? 'À venir' : 'Autres' }, modif.journal || {}));
      localStorage.setItem('faux-google:journal', JSON.stringify(j));
      return { le: new Date().toISOString(), par: reglages.email };
    },
    etiiJournal() {
      if (!reglages.peut) throw new Error('NON_AUTORISE');
      return JSON.parse(localStorage.getItem('faux-google:journal') || '[]');
    },
    etiiRetirer(jeu, type, id) {
      if (!reglages.peut) throw new Error('NON_AUTORISE');
      const b = lire();
      if (b[jeu]) delete b[jeu][type + '~' + id];
      ecrire(b);
      return { ok: true };
    }
  };
  const coureur = (succes, echec) => new Proxy({}, {
    get(_c, nom) {
      if (nom === 'withSuccessHandler') return (f) => coureur(f, echec);
      if (nom === 'withFailureHandler') return (f) => coureur(succes, f);
      return (...args) => {
        window.__APPELS_GOOGLE.push(nom);
        setTimeout(() => {
          try { const r = serveur[nom](...JSON.parse(JSON.stringify(args))); if (succes) succes(r); }
          catch (e) { if (echec) echec(e); }
        }, 60);
      };
    }
  });
  window.google = { script: { run: coureur(null, null) } };
};
const scriptGoogle = (reglages) => 'const fauxGoogle = ' + fauxGoogle.toString() + ';\nfauxGoogle(' + JSON.stringify(reglages) + ');';

console.log('\n== Servi par Google (serveur simulé) ==');
page = await nouvellePage(scriptGoogle({ email: 'prenom.nom@exemple.fr', peut: true }));
o = outils(page);
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await o.attendre(900);
t('un éditeur voit le bouton « Modifier »', (await page.locator('.bascule-edition').count()) === 1);
await o.basculer();
t('le bandeau dit qui est connecté, et que tout le site verra les modifications',
  /Connecté : prenom\.nom@exemple\.fr/.test(await page.locator('.edition-bandeau').innerText())
  && /pour tous les lecteurs/.test(await page.locator('.edition-bandeau').innerText()));
await o.centrer(page.locator('#zone-agenda .edition-ajout'));
await page.locator('#zone-agenda .edition-ajout').click();
await o.remplir('Titre', 'Rendez-vous servi par Google');
await o.remplir('Date', jourIso(3));
await o.enregistrer();
const baseGoogle = await page.evaluate(() => JSON.parse(localStorage.getItem('faux-google:base') || '{}'));
const docsGoogle = Object.values(baseGoogle.communications || {});
t('l’écriture part au serveur, signée de l’adresse connectée',
  docsGoogle.length === 1 && docsGoogle[0].type === 'agenda' && docsGoogle[0].par === 'prenom.nom@exemple.fr', JSON.stringify(docsGoogle).slice(0, 160));
t('et rien dans ce navigateur', await page.evaluate(() => localStorage.getItem('etii:modifications:communications') === null));
t('le rendez-vous s’affiche', (await page.locator('#zone-agenda .agenda__rdv', { hasText: 'servi par Google' }).count()) === 1);
t('un seul appel au démarrage pour tous les jeux', await page.evaluate(() => window.__APPELS_GOOGLE.filter((n) => n === 'etiiDemarrer').length === 1));
t('l’écriture emporte son récit pour le journal de la feuille',
  docsGoogle[0].journal && docsGoogle[0].journal.action === 'Ajout' && docsGoogle[0].journal.element === 'Rendez-vous servi par Google'
  && docsGoogle[0].journal.rubrique === 'À venir', JSON.stringify(docsGoogle[0].journal));
await page.evaluate(() => window.scrollTo(0, 0));
await page.locator('.edition-bandeau__historique').click();
await o.attendre(600);
t('l’historique se lit sur le serveur, et renvoie à la feuille',
  (await page.locator('.modale .historique__entree', { hasText: 'Rendez-vous servi par Google' }).count()) === 1
  && /Journal complet/.test(await page.locator('.modale .historique__note').innerText())
  && await page.evaluate(() => window.__APPELS_GOOGLE.includes('etiiJournal')));
await page.close();

page = await nouvellePage(scriptGoogle({ email: 'lecteur@exemple.fr', peut: false }));
o = outils(page);
await page.goto(`${B}/index.html`, { waitUntil: 'networkidle' });
await o.attendre(900);
t('un lecteur n’a pas de bouton « Modifier »', (await page.locator('.bascule-edition').count()) === 0);
await page.close();

/* La liste des documents tenue dans la feuille du service : le serveur la
   renvoie, le site la prend pour base à la place des exemples. */
const externes = [
  { id: 'EXT-001', titre: 'Guide externe de câblage', reference: 'EXT-001', type: 'Guide maison', metier: ['Harnais'], porteur: 'Personne 08', perimetre: 'H160', pole: ['ETIIA'], maj: '2026-09-01' },
  { id: 'EXT-002', titre: 'Procédure externe de revue', reference: 'EXT-002', type: 'Processus', metier: [], porteur: 'Personne 150', perimetre: 'Transverse', pole: ['ETIIE'], maj: '2026-08-15' }
];
page = await nouvellePage(scriptGoogle({ email: 'lecteur@exemple.fr', peut: false, bases: { documents: externes } }));
o = outils(page);
await page.goto(`${B}/docsearch.html#q=externe`, { waitUntil: 'networkidle' });
await o.attendre(1200);
t('la recherche documentaire lit la liste de la feuille du service',
  (await page.locator('.ds-carte').count()) === 2 && (await page.locator('.ds-carte', { hasText: 'Guide externe de câblage' }).count()) === 1);
await page.fill('#ds-champ', 'Guide de routage des harnais');
await o.attendre(700);
t('les documents d’exemple ne s’y mêlent plus', (await page.locator('.ds-carte', { hasText: 'Guide de routage des harnais' }).count()) === 0);
await page.fill('#ds-champ', '');
await o.attendre(700);
t('l’exploration rapide propose les types de la feuille', /Guide maison/.test(await page.locator('.ds-tuiles').innerText()));
await page.goto(`${B}/etiia.html`, { waitUntil: 'networkidle' });
await o.attendre(1200);
t('les documents du pôle viennent aussi de la feuille', /Guide externe de câblage/.test(await page.locator('#zone-documents').innerText())
  && !/Procédure externe de revue/.test(await page.locator('#zone-documents').innerText()));
await page.close();

t('aucune erreur JavaScript', err.length === 0, err.slice(0, 3).join(' | '));
console.log(`\n  ${ok} réussis, ${ko} échoués`);
await nav.close();
process.exit(ko ? 1 : 0);

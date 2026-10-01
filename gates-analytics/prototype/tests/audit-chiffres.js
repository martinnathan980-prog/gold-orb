/* Audit indépendant des chiffres de la page (débrief 15 : « tous nos
   calculs sont-ils logiques, cohérents, dans la bonne dimension ? »).
   Pour chaque contrat, chaque avancement (définition électrique, concept
   harnais) et chaque périmètre, recalcule depuis la source brute — avec ses
   propres formules, pas celles de la page — les comptes par état, la
   courbe, le rythme tenu, la fin estimée, le rythme requis et les plans à
   l'arrêt, et les compare à ce que la page AFFICHE. Vérifie aussi que la
   page classe chaque valeur comme le serveur (classerFWD de Code.gs).
   Deux pages : la démonstration (prototype/apercu.html) et la page servie
   par le vrai Code.gs sur la structure réelle d'export (apercu-gates.html).
   Usage : node prototype/tests/audit-chiffres.js [page.html demo|classeur] */
const { chromium } = require('playwright');
const fs = require('fs'), vm = require('vm'), path = require('path');
const racine = path.join(__dirname, '..', '..');
/* classerFWD du serveur, chargé tel quel depuis Code.gs */
const ctx = vm.createContext({ console, JSON, Date, Math, SpreadsheetApp: {}, PropertiesService: {}, HtmlService: {}, ScriptApp: {}, Utilities: {}, LockService: {}, ContentService: {}, Session: {} });
vm.runInContext(fs.readFileSync(path.join(racine, 'Code.gs'), 'utf8'), ctx);

const pages = process.argv[2]
  ? [[process.argv[2], process.argv[3] || 'demo']]
  : [[path.join(racine, 'prototype', 'apercu.html'), 'demo'], [path.join(racine, 'apercu-gates.html'), 'classeur']];
let totalEcarts = 0;
(async () => {
 for (const [fichier, mode] of pages) {
  console.log('\n— ' + path.basename(fichier) + ' (' + mode + ') —');
  const b = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const p = await b.newPage({ viewport: { width: 1400, height: 1000 } });
  const erreurs = []; p.on('pageerror', e => erreurs.push(e.message));
  await p.goto('file://' + fichier); await p.waitForTimeout(1500);
  const ecarts = []; let n = 0;
  const types = {};
  const ok = (nom, cond, detail) => { n++; const t = nom.replace(/^.* : /, '').replace(/« [^»]* »/g, '«…»'); types[t] = (types[t] || 0) + 1; if (!cond) ecarts.push(nom + ' — ' + detail); };

  const contrats = await p.evaluate(() => [...document.querySelectorAll('#select-contrat option')].map(o => o.value));
  for (const contrat of (contrats.length ? contrats : [''])) {
    if (contrat && mode === 'demo') { await p.selectOption('#select-contrat', contrat); await p.waitForTimeout(700); }
    const indicateurs = await p.evaluate(() => document.getElementById('choix-indicateur').hidden ? ['def'] : ['def', 'concept']);
    for (const ind of indicateurs) {
      await p.evaluate(i => { const b = document.querySelector('#choix-indicateur button[data-indicateur="' + i + '"]'); if (b && b.getAttribute('aria-pressed') !== 'true') b.click(); }, ind);
      await p.waitForTimeout(600);
      const perimetres = await p.evaluate(() => [...document.querySelectorAll('#choix-perimetre button')].map(b => b.dataset.perimetre));
      for (const per of perimetres) {
        await p.evaluate(v => { const b = [...document.querySelectorAll('#choix-perimetre button')].find(x => x.dataset.perimetre === v); b.click(); }, per);
        await p.waitForTimeout(500);
        const lieu = [contrat || 'classeur', ind, per || 'Tout'].join(' / ');
        const r = await p.evaluate(({ ind, per, mode }) => {
          /* ---- la source brute ---- */
          const src = mode === 'demo' ? window.__jeuDExemple(document.getElementById('select-contrat').value)
                                      : window.__deballerPaquet(JSON.parse(JSON.stringify(window.SUIVI_FWD_DONNEES)));
          const cle = ind === 'concept' ? src.cleConcept : 'avancement';
          const classer = window.__classer;
          const dom = p => String(src.cleDomaine ? (p[src.cleDomaine] == null ? '' : p[src.cleDomaine]) : '').trim() || '—';
          const pop = src.plans.filter(p => !per || dom(p) === per);
          const etats = { termine: 0, encours: 0, afaire: 0, vide: 0 };
          pop.forEach(p => etats[classer(p[cle])]++);
          /* ---- semaines ---- */
          const lundi = lab => { const [a, w] = lab.split('-S').map(Number); const j4 = new Date(Date.UTC(a, 0, 4)); const d = (j4.getUTCDay() + 6) % 7; return new Date(Date.UTC(a, 0, 4 - d + (w - 1) * 7)); };
          const semISO = d => { const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())); const j = (t.getUTCDay() + 6) % 7; t.setUTCDate(t.getUTCDate() - j + 3); const a = t.getUTCFullYear(); const j4 = new Date(Date.UTC(a, 0, 4)); return a + '-S' + String(1 + Math.round(((t - j4) / 864e5 - 3 + ((j4.getUTCDay() + 6) % 7)) / 7)).padStart(2, '0'); };
          const rels = (src.releves || []).filter(r => ind === 'def' ? true : !!r.plansConcept).slice().sort((a, b) => lundi(a.semaine) - lundi(b.semaine));
          const base = rels.length ? lundi(rels[0].semaine) : null;
          const idx = lab => Math.round((lundi(lab) - base) / (7 * 864e5));
          const n0 = new Date(); const aujLab = semISO(new Date(Date.UTC(n0.getFullYear(), n0.getMonth(), n0.getDate())));
          /* ---- la série : relevés archivés, périmètre par la carte, + l'extract du jour ---- */
          const racine = ref => { const u = window.__analyserUD(ref); return u && u.racine ? u.racine + '|' + (u.solution || '') : ref; };
          const parRef = {}, parRac = {};
          src.plans.forEach(p => { parRef[p.reference] = p; parRac[racine(p.reference)] = p; });
          const planDe = ref => parRef[ref] || parRac[racine(ref)];
          const carteDe = r => ind === 'def' ? r.plans : r.plansConcept;
          const pts = rels.map(r => {
            const carte = carteDe(r);
            /* Un relevé qui a sa carte se recompte avec le classement du jour (débrief 16) ; sans carte, les comptes archivés. */
            if (!per) return carte
              ? { i: idx(r.semaine), total: Object.keys(carte).length, termine: Object.keys(carte).filter(k => classer(carte[k]) === 'termine').length, carte }
              : { i: idx(r.semaine), total: r.total, termine: r.termine, carte };
            let t = 0, f = 0;
            Object.keys(carte || {}).forEach(k => { const pl = planDe(k); if (!pl || dom(pl) !== per) return; t++; if (classer(carte[k]) === 'termine') f++; });
            return { i: idx(r.semaine), total: t, termine: f, carte };
          });
          const vivCarte = {}; src.plans.forEach(p => { vivCarte[p.reference] = p[cle]; });
          const viv = { total: pop.length, termine: etats.termine, carte: vivCarte };
          let aujIdx = rels.length ? idx(rels[rels.length - 1].semaine) : 0;
          const iJour = rels.length ? idx(aujLab) : 0;
          const dern = pts[pts.length - 1];
          const bouge = dern && (Object.keys(vivCarte).length !== Object.keys(dern.carte || {}).length ||
            Object.keys(vivCarte).some(k => !dern.carte || String(dern.carte[k] == null ? '' : dern.carte[k]).trim() !== String(vivCarte[k] == null ? '' : vivCarte[k]).trim()));
          if (dern && iJour > aujIdx && bouge) { aujIdx = iJour; pts.push(Object.assign({ i: iJour }, viv)); }
          else if (dern) pts[pts.length - 1] = Object.assign({ i: aujIdx }, viv);
          else pts.push(Object.assign({ i: 0 }, viv));
          const premier = pts[0], dernier = pts[pts.length - 1];
          const rythme = dernier.i > premier.i ? (dernier.termine - premier.termine) / (dernier.i - premier.i) : null;
          const depart = Math.max(aujIdx, iJour);
          const restants = dernier.total - dernier.termine;
          const fin = rythme > 0 ? depart + Math.ceil(restants / rythme) : null;
          const semDe = i => semISO(new Date(base.getTime() + i * 7 * 864e5));
          /* ---- ce que la page affiche ---- */
          const esp = t => String(t || '').replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim();
          const famille = {}; window.__valeurs().forEach(v => { famille[v.cle] = v.famille; });
          const affEtats = {}; document.querySelectorAll('#etats .etat-btn').forEach(b => {
            const k = b.dataset.cle || b.dataset.etat, f = famille[k] || k;
            affEtats[f] = (affEtats[f] || 0) + +esp(b.querySelector('.etat-n').textContent).replace(/\s/g, '');
          });
          const phrase = esp(document.getElementById('phrase').textContent);
          const leg = esp(document.getElementById('legende').textContent);
          /* Débrief 19 : la fin estimée et le nombre du requis ne sont plus
             écrits dans la légende, seulement dans ses survols. */
          const survols = esp([...document.querySelectorAll('#legende .legende-item span[title]')].map(x => x.getAttribute('title')).join(' | '));
          const serie = window.__serieAffichee().pts;
          /* ---- le requis de la prochaine échéance ---- */
          const pj = window.__prochainJalon();
          let requis = null, requisAff = null;
          if (pj) {
            const jal = (src.jalons || []).find(j => j.texte === pj.texte);
            const perJ = per || (jal.perimetre ? (src.plans.map(dom).find(d => d.toLowerCase().replace(/\s+/g, '') === jal.perimetre.toLowerCase().replace(/\s+/g, '')) || jal.perimetre) : '');
            const popJ = src.plans.filter(p => !perJ || dom(p) === perJ);
            const restJ = popJ.filter(p => classer(p[cle]) !== 'termine').length;
            const semJ = Math.max(1, idx(jal.semaine) - depart);
            requis = restJ / semJ;
            const m = /requis pour « [^»]+ »/.test(leg) ? survols.match(/ : ([\d,]+) par semaine\. En rouge/) : null;
            requisAff = m ? Number(m[1].replace(',', '.')) : null;
          }
          /* ---- à l'arrêt : recalcul depuis les cartes ---- */
          const aujPts = pts;
          let arret = 0;
          pop.forEach(pl => {
            if (classer(pl[cle]) !== 'encours') return;
            const v = window.__norm(pl[cle]); let depuis = aujPts[aujPts.length - 1].i;
            for (let k = aujPts.length - 2; k >= 0; k--) {
              const c = aujPts[k].carte; if (!c) break;
              const ref = Object.prototype.hasOwnProperty.call(c, pl.reference) ? pl.reference : Object.keys(c).find(r => racine(r) === racine(pl.reference));
              if (ref === undefined || window.__norm(c[ref]) !== v) break;
              depuis = aujPts[k].i;
            }
            if (aujPts[aujPts.length - 1].i - depuis >= 6) arret++;
          });
          const arretAff = window.__plansALArret().length;
          return {
            etats, affEtats, total: pop.length, phrase,
            serieAff: serie.map(x => x.i + ':' + x.termine + '/' + x.total).join(' '),
            serie: pts.map(x => x.i + ':' + x.termine + '/' + x.total).join(' '),
            rythme, leg, survols, fin: fin === null ? null : semDe(fin), requis, requisAff, arret, arretAff,
            jalon: pj && pj.texte
          };
        }, { ind, per, mode });
        ['termine', 'encours', 'afaire', 'vide'].forEach(k => ok(lieu + ' : compte « ' + k + ' »', r.etats[k] === (r.affEtats[k] || 0), JSON.stringify([r.etats[k], r.affEtats[k]])));
        ok(lieu + ' : phrase « X sur Y validés »', new RegExp('^' + r.etats.termine + ' sur ' + r.total + ' plans validés').test(r.phrase.replace(/(\d) (\d)/g, '$1$2')), r.phrase);
        ok(lieu + ' : série de la courbe', r.serie === r.serieAff, r.serie + '  ≠  ' + r.serieAff);
        const mR = r.leg.match(/au rythme tenu \(([\d,]+)\/sem\.\)/), mF = r.survols.match(/ : fin S(\d+) · /);
        if (r.rythme !== null && r.etats.termine < r.total) {
          ok(lieu + ' : rythme tenu', !!mR && Math.abs(Number(mR[1].replace(',', '.')) - Math.round(r.rythme * 10) / 10) < 0.051, JSON.stringify([r.rythme, mR && mR[1]]));
          if (r.fin) ok(lieu + ' : fin estimée', !!mF && Number(mF[1]) === Number(r.fin.slice(6)), JSON.stringify([r.fin, mF && mF[1]]));
        }
        /* La légende nomme le requis : son survol doit en porter le nombre —
           un survol muet n'est pas « rien à vérifier ». */
        if (r.requis !== null && /requis pour « /.test(r.leg)) ok(lieu + ' : rythme requis « ' + r.jalon + ' »', r.requisAff !== null && Math.abs(r.requisAff - Math.round(r.requis * 10) / 10) < 0.051, JSON.stringify([r.requis, r.requisAff]));
        ok(lieu + ' : plans à l’arrêt', r.arret === r.arretAff, JSON.stringify([r.arret, r.arretAff]));
      }
      await p.evaluate(() => { const b = [...document.querySelectorAll('#choix-perimetre button')][0]; b && b.click(); });
      await p.waitForTimeout(300);
    }
    await p.evaluate(() => { const b = document.querySelector('#choix-indicateur button[data-indicateur="def"]'); b && b.click(); });
    await p.waitForTimeout(400);
  }
  /* parité serveur / page : chaque valeur des colonnes suivies classée pareil des deux côtés */
  const valeurs = await p.evaluate(() => {
    const src = document.getElementById('select-contrat') && window.__jeuDExemple ? window.__jeuDExemple(document.getElementById('select-contrat').value) : null;
    const s = src || window.__deballerPaquet(JSON.parse(JSON.stringify(window.SUIVI_FWD_DONNEES)));
    const vals = new Set(); s.plans.forEach(p => { vals.add(String(p.avancement == null ? '' : p.avancement)); if (s.cleConcept) vals.add(String(p[s.cleConcept] == null ? '' : p[s.cleConcept])); });
    ['Validé', 'validé', 'Validée', 'VALIDÉS', 'Non validé', 'Non validée', '100 %', '100%', '0 %', '45 %', '0', '12', 'À faire', 'A traiter',
     'Pas commencé', 'Non commencé', 'Terminé', 'Terminée', 'Non terminé', 'OK', 'Non OK', 'OK avec réserve', 'book', 'Check', '-', '', 'EMPTY',
     'En cours', 'Soldé', 'Clôturée', 'Finie', '3 - Validé', '1 - En cours', '0 - A traiter', '2) Check', '1.5', '2026-09-01', 'Released'].forEach(v => vals.add(v));
    return [...vals].map(v => [v, window.__classer(v)]);
  });
  valeurs.forEach(([v, c]) => ok('classement « ' + v + ' » : page = serveur', ctx.classerFWD(v) === c, JSON.stringify([c, ctx.classerFWD(v)])));
  console.log(Object.keys(types).map(t => t + ' ×' + types[t]).join(' · '));
  console.log(n + ' vérifications, ' + ecarts.length + ' écart(s)');
  ecarts.forEach(e => console.log('  ✗ ' + e));
  if (erreurs.length) console.log('  Erreurs JavaScript : ' + erreurs.join(' | '));
  totalEcarts += ecarts.length + erreurs.length;
  await b.close();
 }
 process.exit(totalEcarts ? 1 : 0);
})();

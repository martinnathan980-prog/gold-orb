/* =========================================================================
   ETII Hub — L'organigramme du service

   Trois vues sur les mêmes personnes, choisies par onglets :
     ARBRE          la hiérarchie, direction → pôles → squads → personnes
     TROMBINOSCOPE  une grille de fiches, pour balayer et reconnaître
     COMPÉTENCES    « qui sait faire ça ? » — l'annuaire du service

   Une seule barre de recherche et un seul jeu de filtres commandent les
   trois. Une personne s'ouvre en fiche : son rattachement, ses
   compétences, les documents qu'elle porte, ses collègues, son porteur.

   Contrat d'URL : organigramme.html#pole=…&vue=…&personne=…&competence=…
   « pole » vaut ETII (tout le service) ou un code de pôle ; une valeur
   inconnue retombe sur ETII sans erreur.
   ========================================================================= */

import { el, frag, monter, deleguer, debounce, etatUrl, initTheme, initNav,
         ouvrirModale, annoncer, toast, copierTexte } from './ui.js';
import { chargerDonnees, avecEtat } from './data.js';

const SERVICE = 'ETII';
const CODES = ['ETIIA', 'ETIIE', 'ETIII'];
const VUES = ['arbre', 'trombinoscope', 'competences'];
const MENTION_VIDE = 'à renseigner';

const NIVEAUX = {
  referent: { libelle: 'Référent', rang: 3, classe: 'badge--accent' },
  confirme: { libelle: 'Confirmé', rang: 2, classe: 'badge--neutre' },
  pratique: { libelle: 'Pratique', rang: 1, classe: 'badge--contour' }
};

const PAGE_DE_POLE = { ETII: 'index.html', ETIIA: 'etiia.html', ETIIE: 'etiie.html', ETIII: 'etiii.html' };

/* -------------------------------------------------------------------------
   1. Lecture et index
   ------------------------------------------------------------------------- */

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function normaliser(v) { return texte(v).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }
function valeurOuVide(v) { return texte(v) || MENTION_VIDE; }

function initiales(nom) {
  const parts = texte(nom).split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  const dernier = parts[parts.length - 1];
  if (parts.length > 1 && /^\d+$/.test(dernier)) return parts[0][0].toUpperCase() + dernier;
  return parts.slice(0, 2).map((p) => p[0].toUpperCase()).join('');
}

/** Un modèle plat : une entrée par personne, tout ce qu'il faut pour filtrer. */
function construireModele(orga, docs) {
  const gens = [];
  const ajouter = (p, role, pole, squad) => {
    if (!p || typeof p !== 'object' || !texte(p.nom)) return;
    const competences = (Array.isArray(p.competences) ? p.competences : [])
      .filter((c) => c && texte(c.nom))
      .map((c) => ({ nom: texte(c.nom), niveau: NIVEAUX[texte(c.niveau)] ? texte(c.niveau) : 'pratique' }));
    gens.push({
      id: texte(p.id) || ('sans-id-' + gens.length),
      nom: texte(p.nom), poste: texte(p.poste), role, pole, squad,
      perimetre: texte(p.perimetre), competences,
      recherche: normaliser([p.nom, p.poste, p.perimetre, squad, pole, p.id,
        competences.map((c) => c.nom).join(' ')].join(' '))
    });
  };

  ajouter(orga.direction, 'direction', SERVICE, '');
  for (const pole of (Array.isArray(orga.poles) ? orga.poles : [])) {
    const code = texte(pole && pole.pole);
    ajouter(pole && pole.responsable, 'responsable', code, '');
    for (const squad of (Array.isArray(pole && pole.squads) ? pole.squads : [])) {
      const nomSquad = texte(squad && squad.nom);
      for (const m of (Array.isArray(squad && squad.membres) ? squad.membres : [])) {
        ajouter(m, texte(m && m.role) === 'leader' ? 'leader' : 'membre', code, nomSquad);
      }
    }
  }

  /* Les documents portés : documents.json nomme son porteur. Le lien se
     fait sur le nom, seule clé commune aux deux fichiers. */
  const parPorteur = new Map();
  for (const d of (docs && Array.isArray(docs.documents) ? docs.documents : [])) {
    const porteur = texte(d && d.porteur);
    if (!porteur) continue;
    if (!parPorteur.has(porteur)) parPorteur.set(porteur, []);
    parPorteur.get(porteur).push(d);
  }
  for (const g of gens) g.documents = parPorteur.get(g.nom) || [];

  /* L'annuaire des compétences : une entrée par compétence, ses porteurs
     triés par niveau puis par nom. */
  const parCompetence = new Map();
  for (const g of gens) {
    for (const c of g.competences) {
      if (!parCompetence.has(c.nom)) parCompetence.set(c.nom, []);
      parCompetence.get(c.nom).push({ personne: g, niveau: c.niveau });
    }
  }
  const competences = [...parCompetence.entries()]
    .map(([nom, gensC]) => ({
      nom,
      gens: gensC.sort((a, b) => NIVEAUX[b.niveau].rang - NIVEAUX[a.niveau].rang || a.personne.nom.localeCompare(b.personne.nom)),
      referents: gensC.filter((x) => x.niveau === 'referent').length
    }))
    .sort((a, b) => a.nom.localeCompare(b.nom));

  return { gens, competences, orga };
}

/* -------------------------------------------------------------------------
   2. État
   ------------------------------------------------------------------------- */

let modele = null;
let vue = 'arbre';
let poleActif = SERVICE;
let requete = '';
let competenceActive = '';
let fiche = null;
const refs = {};

function visibles() {
  const q = normaliser(requete);
  return modele.gens.filter((g) => {
    if (poleActif !== SERVICE && g.pole !== poleActif && g.role !== 'direction') return false;
    if (competenceActive && !g.competences.some((c) => c.nom === competenceActive)) return false;
    if (q && !g.recherche.includes(q)) return false;
    return true;
  });
}

function ecrireUrl() {
  etatUrl.ecrire({ pole: poleActif, vue: vue === 'arbre' ? '' : vue,
    competence: competenceActive, personne: fiche || '' });
}

/* -------------------------------------------------------------------------
   3. Briques communes
   ------------------------------------------------------------------------- */

function avatar(g, grand) {
  return el('span', { class: ['org-avatar', grand ? 'org-avatar--grand' : null], dataPole: g.pole,
    'aria-hidden': 'true' }, initiales(g.nom));
}

function badgeRole(role) {
  if (role === 'direction') return el('span', { class: 'badge badge--accent' }, 'Direction');
  if (role === 'responsable') return el('span', { class: 'badge badge--accent' }, 'Responsable');
  if (role === 'leader') return el('span', { class: 'badge badge--neutre' }, 'Lead');
  return null;
}

/** Le bouton qui ouvre une fiche. Même balisage dans les trois vues. */
function boutonPersonne(g, options) {
  const opts = options || {};
  return el('button', {
    type: 'button',
    class: ['org-personne', opts.classe || null],
    dataPersonne: g.id,
    dataPole: g.pole,
    'aria-haspopup': 'dialog'
  },
  avatar(g),
  el('span', { class: 'org-personne__infos' },
    el('span', { class: 'org-personne__nom' }, g.nom),
    el('span', { class: 'org-personne__poste' }, valeurOuVide(g.poste)),
    opts.avecSquad && g.squad ? el('span', { class: 'org-personne__squad' }, g.squad) : null),
  opts.suffixe || null,
  g.perimetre ? el('span', { class: 'org-personne__perimetre mono' }, g.perimetre) : null,
  badgeRole(g.role));
}

/* -------------------------------------------------------------------------
   4. Vue « arbre »
   ------------------------------------------------------------------------- */

function rendreArbre(gens) {
  const parmi = (predicat) => gens.filter(predicat);
  const direction = parmi((g) => g.role === 'direction');
  const poles = (poleActif === SERVICE ? CODES : [poleActif]).map((code) => {
    const membres = parmi((g) => g.pole === code);
    const responsable = membres.find((g) => g.role === 'responsable') || null;
    const squads = [...new Set(membres.filter((g) => g.squad).map((g) => g.squad))].sort();
    return { code, responsable, squads: squads.map((nom) => ({ nom, membres: membres.filter((g) => g.squad === nom) })), effectif: membres.length };
  }).filter((p) => p.effectif > 0);

  if (!poles.length && !direction.length) {
    return el('p', { class: 'texte-doux' }, 'Personne ne correspond à cette recherche.');
  }

  return el('div', { class: 'org-arbre' },
    direction.length
      ? el('div', { class: 'org-arbre__tete' }, direction.map((g) => boutonPersonne(g, { classe: 'org-personne--tete' })))
      : null,
    el('ul', { class: 'org-arbre__poles', role: 'list' }, poles.map((p) => el('li', { class: 'org-arbre__pole', dataPole: p.code },
      el('div', { class: 'org-arbre__pole-tete' },
        el('span', { class: 'org-arbre__pole-point', 'aria-hidden': 'true' }),
        el('a', { class: 'org-arbre__pole-nom', href: PAGE_DE_POLE[p.code] || '#' }, p.code),
        el('span', { class: 'org-arbre__pole-compte mono' }, p.effectif + ' pers.')),
      p.responsable ? boutonPersonne(p.responsable, { classe: 'org-personne--responsable' }) : null,
      el('ul', { class: 'org-arbre__squads', role: 'list' }, p.squads.map((s) => el('li', { class: 'org-arbre__squad' },
        el('div', { class: 'org-arbre__squad-tete' },
          el('span', {}, s.nom),
          el('span', { class: 'mono' }, s.membres.length)),
        el('div', { class: 'org-arbre__membres' }, s.membres
          .sort((a, b) => (b.role === 'leader') - (a.role === 'leader') || a.nom.localeCompare(b.nom))
          .map((g) => boutonPersonne(g)))))))))); 
}

/* -------------------------------------------------------------------------
   5. Vue « trombinoscope »
   ------------------------------------------------------------------------- */

function rendreTrombinoscope(gens) {
  if (!gens.length) return el('p', { class: 'texte-doux' }, 'Personne ne correspond à cette recherche.');
  const tries = gens.slice().sort((a, b) => a.nom.localeCompare(b.nom));
  return el('ul', { class: 'org-trombi', role: 'list' }, tries.map((g) => el('li', {},
    boutonPersonne(g, { classe: 'org-personne--carte', avecSquad: true }))));
}

/* -------------------------------------------------------------------------
   6. Vue « compétences » — l'annuaire
   ------------------------------------------------------------------------- */

function rendreCompetences(gens) {
  const retenus = new Set(gens.map((g) => g.id));
  const q = normaliser(requete);
  const liste = modele.competences
    .map((c) => ({ nom: c.nom, gens: c.gens.filter((x) => retenus.has(x.personne.id)) }))
    .filter((c) => c.gens.length)
    /* La recherche porte aussi sur le nom de la compétence : taper
       « tension » doit sortir « Chute de tension » même si personne ne
       porte ce mot dans son poste. */
    .filter((c) => !q || normaliser(c.nom).includes(q) || c.gens.length);

  if (!liste.length) return el('p', { class: 'texte-doux' }, 'Aucune compétence ne correspond à cette recherche.');

  return el('div', { class: 'org-competences' }, liste.map((c) => el('section', { class: 'org-competence' },
    el('div', { class: 'org-competence__tete' },
      el('h3', { class: 'org-competence__nom' },
        el('button', { type: 'button', class: 'org-competence__filtre', dataCompetence: c.nom,
          'aria-pressed': competenceActive === c.nom ? 'true' : 'false' }, c.nom)),
      el('span', { class: 'org-competence__compte mono' },
        c.gens.length + (c.gens.length > 1 ? ' personnes' : ' personne'))),
    el('ul', { class: 'org-competence__gens', role: 'list' }, c.gens.map((x) => el('li', {},
      boutonPersonne(x.personne, {
        classe: 'org-personne--ligne',
        suffixe: el('span', { class: ['badge', NIVEAUX[x.niveau].classe, 'org-personne__niveau'] }, NIVEAUX[x.niveau].libelle)
      })))))));
}

/* -------------------------------------------------------------------------
   7. La fiche d'une personne
   ------------------------------------------------------------------------- */

function ligneFiche(intitule, ...contenu) {
  return el('div', { class: 'org-fiche__ligne' },
    el('dt', {}, intitule),
    el('dd', {}, contenu.length ? contenu : el('span', { class: 'org-vide' }, MENTION_VIDE)));
}

function ouvrirFiche(id, declencheur) {
  const g = modele.gens.find((x) => x.id === id);
  if (!g) return;
  fiche = id;
  ecrireUrl();

  const chef = g.role === 'direction' ? null
    : (g.role === 'responsable'
      ? modele.gens.find((x) => x.role === 'direction')
      : (modele.gens.find((x) => x.pole === g.pole && x.squad === g.squad && x.role === 'leader' && x.id !== g.id)
         || modele.gens.find((x) => x.pole === g.pole && x.role === 'responsable')));
  const collegues = modele.gens.filter((x) => x.pole === g.pole && x.squad === g.squad && x.id !== g.id && g.squad);

  const puce = (autre) => el('button', { type: 'button', class: 'org-puce', dataPersonne: autre.id },
    avatar(autre), el('span', {}, autre.nom));

  ouvrirModale({
    titre: g.nom,
    classe: 'modale--large',
    declencheur: declencheur || null,
    contenu: () => frag(
      el('div', { class: 'org-fiche__entete' },
        avatar(g, true),
        el('div', { class: 'pile pile--serree' },
          el('p', { class: 'org-fiche__poste sans-marge' }, valeurOuVide(g.poste)),
          el('p', { class: 'rangee rangee--serree sans-marge' },
            badgeRole(g.role),
            g.pole !== SERVICE ? el('a', { class: 'badge badge--contour', href: PAGE_DE_POLE[g.pole] || '#' }, 'Pôle ' + g.pole) : null,
            g.squad ? el('span', { class: 'badge badge--neutre' }, g.squad) : null))),

      el('dl', { class: 'org-fiche__liste' },
        ligneFiche('Identifiant', el('span', { class: 'mono' }, g.id.toUpperCase())),
        ligneFiche('Porteur', g.perimetre
          ? (g.perimetre === 'Transverse'
            ? el('span', {}, 'Transverse')
            : el('a', { class: 'org-lien', href: 'index.html#porteur=' + encodeURIComponent(g.perimetre) }, g.perimetre))
          : null),
        ligneFiche('Rattachement', chef ? puce(chef) : el('span', {}, 'Sommet du service'))),

      el('section', { class: 'org-fiche__bloc' },
        el('h3', { class: 'org-fiche__intitule' }, 'Compétences'),
        g.competences.length
          ? el('ul', { class: 'org-fiche__competences', role: 'list' }, g.competences
              .slice().sort((a, b) => NIVEAUX[b.niveau].rang - NIVEAUX[a.niveau].rang)
              .map((c) => el('li', {},
                el('button', { type: 'button', class: 'org-competence__filtre', dataCompetence: c.nom }, c.nom),
                el('span', { class: ['badge', NIVEAUX[c.niveau].classe] }, NIVEAUX[c.niveau].libelle))))
          : el('p', { class: 'texte-doux sans-marge' }, 'Aucune compétence déclarée.')),

      el('section', { class: 'org-fiche__bloc' },
        el('h3', { class: 'org-fiche__intitule' }, 'Documents portés',
          el('span', { class: 'mono' }, String(g.documents.length))),
        g.documents.length
          ? el('ul', { class: 'org-fiche__documents', role: 'list' }, g.documents.slice(0, 12).map((d) => el('li', {},
              el('a', { class: 'org-fiche__document', href: 'docsearch.html#q=' + encodeURIComponent(texte(d.reference) || texte(d.titre)) },
                el('span', { class: 'org-fiche__document-titre' }, texte(d.titre)),
                el('span', { class: 'org-fiche__document-meta mono' }, [texte(d.type), texte(d.reference)].filter(Boolean).join(' · '))))))
          : el('p', { class: 'texte-doux sans-marge' }, 'Cette personne ne porte aucun document du fonds.')),

      collegues.length
        ? el('section', { class: 'org-fiche__bloc' },
            el('h3', { class: 'org-fiche__intitule' }, 'Sa squad',
              el('span', { class: 'mono' }, String(collegues.length))),
            el('div', { class: 'org-fiche__puces' }, collegues.map(puce)))
        : null),
    actions: [
      { libelle: 'Copier la fiche', variante: 'secondaire', ferme: false, onClick: () => {
        const lignes = [g.nom, valeurOuVide(g.poste),
          g.pole !== SERVICE ? 'Pôle ' + g.pole : 'Direction du service',
          g.squad ? 'Squad : ' + g.squad : '',
          'Porteur : ' + valeurOuVide(g.perimetre),
          'Compétences : ' + (g.competences.map((c) => c.nom + ' (' + NIVEAUX[c.niveau].libelle.toLowerCase() + ')').join(', ') || MENTION_VIDE),
          'Documents portés : ' + g.documents.length].filter(Boolean);
        Promise.resolve(copierTexte(lignes.join('\n')))
          .then((ok) => toast(ok === false ? 'Copie impossible dans ce navigateur.' : 'Fiche copiée.', ok === false ? 'erreur' : 'succes'));
        return false;
      } },
      { libelle: 'Fermer', variante: 'principal', ferme: true }
    ],
    onFermeture: () => { fiche = null; ecrireUrl(); }
  });
  annoncer('Fiche de ' + g.nom + ' ouverte.');
}

/* -------------------------------------------------------------------------
   8. Export
   ------------------------------------------------------------------------- */

function exporterCsv() {
  const lignes = [['identifiant', 'nom', 'poste', 'role', 'pole', 'squad', 'porteur', 'competences', 'documents_portes']];
  for (const g of visibles()) {
    lignes.push([g.id, g.nom, g.poste, g.role, g.pole, g.squad, g.perimetre,
      g.competences.map((c) => c.nom + ':' + c.niveau).join(' | '), String(g.documents.length)]);
  }
  const csv = lignes.map((l) => l.map((c) => {
    const v = texte(c);
    return /[",;\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  }).join(',')).join('\n');

  Promise.resolve(copierTexte(csv)).then((ok) => {
    toast(ok === false
      ? 'Copie impossible : sélectionnez le tableau à la main.'
      : (lignes.length - 1) + ' lignes copiées — collez-les dans un tableur.',
    ok === false ? 'erreur' : 'succes');
  });
}

/* -------------------------------------------------------------------------
   9. Rendu et câblage
   ------------------------------------------------------------------------- */

function rendreReperes() {
  const gens = visibles();
  const squads = new Set(gens.filter((g) => g.squad).map((g) => g.pole + '/' + g.squad));
  const competences = new Set(gens.flatMap((g) => g.competences.map((c) => c.nom)));
  const documents = gens.reduce((n, g) => n + g.documents.length, 0);
  const repere = (valeur, libelle) => el('div', { class: 'org-repere' },
    el('span', { class: 'org-repere__valeur mono' }, String(valeur)),
    el('span', { class: 'org-repere__libelle' }, libelle));
  monter(refs.reperes,
    repere(gens.length, gens.length > 1 ? 'personnes affichées' : 'personne affichée'),
    repere(squads.size, squads.size > 1 ? 'squads' : 'squad'),
    repere(competences.size, 'compétences distinctes'),
    repere(documents, 'documents portés'));
}

function rendre() {
  const gens = visibles();
  refs.onglets.querySelectorAll('[data-vue]').forEach((b) => {
    const actif = b.dataset.vue === vue;
    b.setAttribute('aria-selected', actif ? 'true' : 'false');
    b.tabIndex = actif ? 0 : -1;
  });
  refs.filtres.querySelectorAll('[data-pole-filtre]').forEach((b) => {
    b.setAttribute('aria-pressed', b.dataset.poleFiltre === poleActif ? 'true' : 'false');
  });
  refs.jeton.hidden = !competenceActive;
  if (competenceActive) refs.jetonTexte.textContent = competenceActive;

  monter(refs.zone,
    vue === 'arbre' ? rendreArbre(gens)
      : vue === 'trombinoscope' ? rendreTrombinoscope(gens)
        : rendreCompetences(gens));
  rendreReperes();
}

function appliquerUrl() {
  const etat = etatUrl.lire();
  const pole = texte(etat.pole).toUpperCase();
  poleActif = CODES.includes(pole) ? pole : SERVICE;
  const v = texte(etat.vue);
  vue = VUES.includes(v) ? v : 'arbre';
  competenceActive = texte(etat.competence);
  /* La page est transverse : le lien courant est celui du périmètre
     affiché — le tableau de bord au niveau service, sinon le pôle. */
  initNav(PAGE_DE_POLE[poleActif] || 'index.html');
}

function construire(donnees, cible) {
  modele = construireModele(donnees.orga, donnees.docs);

  refs.recherche = el('input', { type: 'search', class: 'org-recherche', id: 'org-recherche',
    placeholder: 'Un nom, un poste, une compétence, un porteur…', autocomplete: 'off' });
  refs.recherche.value = requete;

  refs.jetonTexte = el('b', {});
  refs.jeton = el('button', { type: 'button', class: 'org-jeton', hidden: true, dataEffacerCompetence: '' },
    el('span', { class: 'texte-faible' }, 'Compétence : '), refs.jetonTexte, el('span', { 'aria-hidden': 'true' }, ' ×'));

  refs.filtres = el('ul', { class: 'facettes', 'aria-label': 'Périmètre affiché' },
    [{ cle: SERVICE, libelle: 'Tout le service' }].concat(CODES.map((c) => ({ cle: c, libelle: c })))
      .map((f) => el('li', {}, el('button', {
        type: 'button', class: 'facette facette--compacte', dataPoleFiltre: f.cle,
        'aria-pressed': f.cle === poleActif ? 'true' : 'false'
      }, f.libelle))));

  refs.onglets = el('div', { class: 'onglets__liste', role: 'tablist', 'aria-label': 'Vue de l’organigramme' },
    [['arbre', 'Arbre'], ['trombinoscope', 'Trombinoscope'], ['competences', 'Compétences']]
      .map(([cle, libelle]) => el('button', {
        type: 'button', class: 'onglets__onglet', role: 'tab', dataVue: cle,
        'aria-selected': cle === vue ? 'true' : 'false', tabIndex: cle === vue ? 0 : -1
      }, libelle)));

  refs.reperes = el('div', { class: 'org-reperes' });
  refs.zone = el('div', { class: 'org-zone', role: 'tabpanel', tabIndex: 0 });

  monter(cible,
    el('div', { class: 'org-barre' },
      el('label', { class: 'visuellement-cache', for: 'org-recherche' }, 'Rechercher dans l’organigramme'),
      refs.recherche,
      refs.jeton,
      el('button', { type: 'button', class: 'bouton bouton--secondaire bouton--compact', dataExport: '' }, 'Exporter'),
      refs.filtres),
    refs.reperes,
    el('div', { class: 'onglets' }, refs.onglets, refs.zone));

  refs.recherche.addEventListener('input', debounce(() => { requete = refs.recherche.value; rendre(); }, 120));

  deleguer(cible, '[data-personne]', 'click', (evt, b) => ouvrirFiche(b.dataset.personne, b));
  deleguer(document.body, '[data-personne]', 'click', (evt, b) => {
    /* Les puces d'une fiche ouvrent la fiche suivante : la délégation
       vit sur le corps, la modale n'étant pas dans la zone. */
    if (cible.contains(b)) return;
    ouvrirFiche(b.dataset.personne, b);
  });
  deleguer(document.body, '[data-competence]', 'click', (evt, b) => {
    competenceActive = competenceActive === b.dataset.competence ? '' : b.dataset.competence;
    vue = 'competences';
    ecrireUrl(); rendre();
    annoncer(competenceActive ? 'Filtré sur ' + competenceActive : 'Filtre de compétence retiré.');
  });
  deleguer(cible, '[data-effacer-competence]', 'click', () => { competenceActive = ''; ecrireUrl(); rendre(); });
  deleguer(cible, '[data-pole-filtre]', 'click', (evt, b) => { poleActif = b.dataset.poleFiltre; ecrireUrl(); rendre(); });
  deleguer(cible, '[data-vue]', 'click', (evt, b) => { vue = b.dataset.vue; ecrireUrl(); rendre(); });
  deleguer(cible, '[data-export]', 'click', exporterCsv);

  refs.onglets.addEventListener('keydown', (evt) => {
    const boutons = Array.from(refs.onglets.querySelectorAll('[data-vue]'));
    const i = boutons.findIndex((b) => b === document.activeElement);
    if (i === -1) return;
    let j = i;
    if (evt.key === 'ArrowRight') j = (i + 1) % boutons.length;
    else if (evt.key === 'ArrowLeft') j = (i - 1 + boutons.length) % boutons.length;
    else return;
    evt.preventDefault();
    boutons[j].focus(); boutons[j].click();
  });

  rendre();

  const demandee = texte(etatUrl.lire().personne);
  if (demandee) ouvrirFiche(demandee, null);
}

/* -------------------------------------------------------------------------
   10. Démarrage
   ------------------------------------------------------------------------- */

initTheme();
appliquerUrl();

avecEtat('#zone-organigramme',
  async () => {
    const [orga, docs] = await Promise.all([chargerDonnees('organigramme'), chargerDonnees('documents')]);
    return { orga, docs };
  },
  construire, {
    squelette: 4,
    texteChargement: 'Chargement de l’organigramme du service…',
    titreErreur: 'Organigramme indisponible',
    titreVide: 'Aucune personne déclarée',
    texteVide: 'Le fichier de l’organigramme ne contient encore personne.',
    estVide: (d) => !d || !d.orga || (!d.orga.direction && !(d.orga.poles || []).length)
  });

etatUrl.ecouter(() => {
  if (!modele) return;
  appliquerUrl();
  rendre();
});

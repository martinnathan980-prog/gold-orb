/* =========================================================================
   ETII Hub — Le kiosque de communication
   Reprend la structure du « Communication Center » d'origine du service :
   à gauche, l'historique en fil chronologique ; à droite, le projecteur
   qui lit l'entrée choisie — badge de programme, titre, puis le corps
   écrit ligne à ligne, à la machine à écrire. Un bandeau d'alertes court
   au-dessus quand il y a des alertes.

   Rien n'est inventé : chaque entrée vient de communications.json (le mot
   du chef, l'agenda, les annonces). Tout le DOM est construit avec el() —
   aucun innerHTML, aucun gestionnaire en attribut.
   ========================================================================= */

import { el, monter, mouvementReduit, annoncer, copierTexte, toast } from './ui.js';

const MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
                     'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const MOIS_LONGS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                    'juillet', 'août', 'septembre', 'octobre', 'novembre',
                    'décembre'];

/* Libellé humain des types d'entrée d'agenda : de la matière éditoriale,
   pas de la donnée. Un type inconnu est affiché tel quel. */
const TYPES_AGENDA = {
  jalon: 'Jalon', atelier: 'Atelier', reunion: 'Réunion', mot: 'Mot du chef',
  succes: 'Succès', alerte: 'Alerte', info: 'Information'
};

const STATUTS = {
  succes: { libelle: 'Validé', classe: 'badge--succes' },
  urgent: { libelle: 'Urgent', classe: 'badge--alerte' },
  info:   { libelle: 'Information', classe: 'badge--info' },
  'a-venir': { libelle: 'À venir', classe: 'badge--accent' },
  mot:    { libelle: 'Le mot du chef', classe: 'badge--accent' }
};

/* Glyphe posé devant chaque ligne du corps, selon son type. C'est le
   vocabulaire du formulaire d'origine : « ! » alerte, « V » validé,
   « -> » titre, « • » puce. */
const GLYPHES = {
  titre: '→', puce: '•', valide: '✓', alerte: '⚠', texte: '', vide: ''
};

/* -------------------------------------------------------------------------
   1. Lecture prudente
   ------------------------------------------------------------------------- */

function texte(valeur) {
  if (valeur === null || valeur === undefined) return '';
  return String(valeur).trim();
}

function partiesDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(texte(iso));
  if (!m) return null;
  const annee = Number(m[1]); const mois = Number(m[2]); const jour = Number(m[3]);
  if (mois < 1 || mois > 12 || jour < 1 || jour > 31) return null;
  return { annee, mois, jour };
}

/** « 12 SEPT. 2026 » — la date courte du fil, en capitales mono. */
export function dateCourte(iso) {
  const p = partiesDate(iso);
  if (!p) return '';
  return `${p.jour} ${MOIS_COURTS[p.mois - 1]} ${p.annee}`;
}

/** « jeudi 12 septembre 2026 » — la date longue du projecteur. */
export function dateLongue(iso) {
  const p = partiesDate(iso);
  if (!p) return '';
  return `${p.jour} ${MOIS_LONGS[p.mois - 1]} ${p.annee}`;
}

function aujourdhui() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/** Jours restants jusqu'à la date, ou null si elle est illisible. */
export function joursRestants(iso) {
  const p = partiesDate(iso);
  if (!p) return null;
  const cible = new Date(p.annee, p.mois - 1, p.jour);
  return Math.round((cible - aujourdhui()) / 86400000);
}

function libelleDelai(jours) {
  if (jours === null) return '';
  if (jours === 0) return 'Aujourd’hui';
  if (jours === 1) return 'Demain';
  if (jours > 1) return 'J-' + jours;
  return '';
}

/* -------------------------------------------------------------------------
   2. De communications.json aux dossiers du kiosque
   ------------------------------------------------------------------------- */

/**
 * Le corps d'une annonce : un tableau de lignes typées. Une chaîne est
 * découpée sur les retours à la ligne ; chaque ligne garde son type.
 * @param {*} brut
 * @returns {Array<{type:string, texte:string}>}
 */
function lignesDepuis(brut) {
  if (Array.isArray(brut)) {
    return brut
      .filter((l) => l && typeof l === 'object')
      .map((l) => ({ type: GLYPHES[l.type] !== undefined ? l.type : 'texte',
                     texte: texte(l.texte) }));
  }
  const t = texte(brut);
  if (!t) return [];
  return t.split('\n').map((l) => ({ type: l.trim() ? 'texte' : 'vide', texte: l.trim() }));
}

/**
 * Construit la liste des dossiers du kiosque à partir de communications.json.
 *
 * - le mot du chef, épinglé en tête (seulement au niveau service) ;
 * - l'agenda à venir, le plus proche d'abord ;
 * - l'historique : annonces et agenda passé, du plus récent au plus ancien.
 *
 * @param {object} donnees  contenu de communications.json
 * @param {{pole?: string}} [options]  code de pôle ; absent ou 'ETII' : tout le service
 * @returns {Array<object>}
 */
export function dossiersDepuisCommunications(donnees, options) {
  const opts = options || {};
  const pole = texte(opts.pole).toUpperCase();
  const niveauService = !pole || pole === 'ETII';
  const garder = (entree) => niveauService || texte(entree.pole).toUpperCase() === pole;

  const dossiers = [];
  const d = (donnees && typeof donnees === 'object') ? donnees : {};

  const mot = (d.motDuChef && typeof d.motDuChef === 'object') ? d.motDuChef : null;
  if (mot && niveauService && texte(mot.titre)) {
    dossiers.push({
      id: 'mot-du-chef',
      groupe: 'mot',
      date: texte(mot.date),
      titre: texte(mot.titre),
      resume: '',
      programme: 'Service ETII',
      statut: 'mot',
      pole: 'ETII',
      lignes: lignesDepuis(mot.corps),
      auteur: texte(mot.auteur),
      fonction: texte(mot.fonction)
    });
  }

  const agenda = Array.isArray(d.agenda) ? d.agenda.filter((e) => e && typeof e === 'object') : [];
  const annonces = Array.isArray(d.annonces) ? d.annonces.filter((e) => e && typeof e === 'object') : [];

  const aVenir = agenda
    .filter((e) => texte(e.statut) === 'a-venir' && garder(e))
    .sort((a, b) => texte(a.date).localeCompare(texte(b.date)))
    .map((e) => ({
      id: 'agenda-' + texte(e.id),
      groupe: 'a-venir',
      date: texte(e.date),
      titre: texte(e.titre),
      resume: texte(e.resume),
      programme: TYPES_AGENDA[texte(e.type)] || texte(e.type) || 'Agenda',
      statut: 'a-venir',
      pole: texte(e.pole).toUpperCase(),
      lede: e.corps ? texte(e.resume) : '',
      lignes: lignesDepuis(e.corps || e.resume)
    }));

  const historique = [
    ...annonces.filter(garder).map((e) => ({
      id: 'annonce-' + texte(e.id),
      groupe: 'historique',
      date: texte(e.date),
      titre: texte(e.titre),
      resume: texte(e.resume),
      programme: texte(e.categorie) || 'Général',
      statut: STATUTS[texte(e.statut)] ? texte(e.statut) : 'info',
      pole: texte(e.pole).toUpperCase(),
      lede: texte(e.resume),
      lignes: lignesDepuis(e.corps)
    })),
    ...agenda
      .filter((e) => texte(e.statut) !== 'a-venir' && texte(e.type) !== 'mot' && garder(e))
      .map((e) => ({
        id: 'agenda-' + texte(e.id),
        groupe: 'historique',
        date: texte(e.date),
        titre: texte(e.titre),
        resume: texte(e.resume),
        programme: TYPES_AGENDA[texte(e.type)] || texte(e.type) || 'Agenda',
        statut: STATUTS[texte(e.type)] ? texte(e.type) : 'info',
        pole: texte(e.pole).toUpperCase(),
        lede: e.corps ? texte(e.resume) : '',
        lignes: lignesDepuis(e.corps || e.resume)
      }))
  ].sort((a, b) => b.date.localeCompare(a.date));

  return dossiers.concat(aVenir, historique);
}

/** Les alertes en cours, sous forme de chaînes. */
export function alertesDepuisCommunications(donnees) {
  const d = (donnees && typeof donnees === 'object') ? donnees : {};
  return (Array.isArray(d.alertes) ? d.alertes : []).map(texte).filter(Boolean);
}

/* -------------------------------------------------------------------------
   3. Le bandeau d'alertes
   ------------------------------------------------------------------------- */

function bandeauAlertes(alertes) {
  if (!alertes.length) return null;
  const liste = (copie) => el('ul', {
    class: ['kiosque__alertes-liste', copie ? 'kiosque__alertes-liste--copie' : null],
    'aria-hidden': copie ? 'true' : null
  }, alertes.map((a) => el('li', { class: 'kiosque__alerte' }, a)));

  return el('div', { class: 'kiosque__alertes', role: 'region', 'aria-label': 'Alertes en cours' },
    el('span', { class: 'kiosque__alertes-etiquette' },
      el('span', { class: 'kiosque__alertes-point', 'aria-hidden': 'true' }),
      alertes.length > 1 ? 'Alertes' : 'Alerte'),
    el('div', { class: 'kiosque__alertes-fenetre' },
      el('div', { class: 'kiosque__alertes-piste' }, liste(false), liste(true))));
}

/* -------------------------------------------------------------------------
   4. Le fil (à gauche)
   ------------------------------------------------------------------------- */

const GROUPES = [
  { cle: 'mot', titre: 'Le mot du chef' },
  { cle: 'a-venir', titre: 'À venir' },
  { cle: 'historique', titre: 'Historique' }
];

function pastillePole(code) {
  if (!code || code === 'ETII') return null;
  return el('span', { class: 'kiosque__pole', dataset: { pole: code } },
    el('span', { class: 'kiosque__pole-point', 'aria-hidden': 'true' }),
    code);
}

function carteFil(dossier, prefixe) {
  const delai = dossier.groupe === 'a-venir' ? libelleDelai(joursRestants(dossier.date)) : '';
  return el('li', { class: 'kiosque__entree', dataset: { id: dossier.id } },
    el('button', {
      type: 'button',
      class: 'kiosque__carte',
      id: prefixe + '-entree-' + dossier.id,
      dataset: { id: dossier.id },
      'aria-current': 'false'
    },
    el('span', { class: 'kiosque__carte-meta' },
      el('time', { class: 'kiosque__date', datetime: dossier.date || null },
        dateCourte(dossier.date) || 'Date à renseigner'),
      delai ? el('span', { class: 'kiosque__delai' }, delai) : null,
      pastillePole(dossier.pole)),
    el('span', { class: 'kiosque__carte-titre' }, dossier.titre || 'Sans titre'),
    dossier.resume
      ? el('span', { class: 'kiosque__carte-resume' }, dossier.resume)
      : null));
}

function fil(dossiers, prefixe) {
  const enfants = [];
  for (const groupe of GROUPES) {
    const membres = dossiers.filter((d) => d.groupe === groupe.cle);
    if (!membres.length) continue;
    if (groupe.cle !== 'mot') {
      enfants.push(el('li', { class: 'kiosque__groupe', role: 'presentation' },
        el('span', { class: 'kiosque__groupe-titre' }, groupe.titre),
        el('span', { class: 'kiosque__groupe-compte mono' }, String(membres.length))));
    }
    for (const d of membres) enfants.push(carteFil(d, prefixe));
  }
  return el('ol', { class: 'kiosque__liste', role: 'list' }, enfants);
}

/* -------------------------------------------------------------------------
   5. Le projecteur (à droite) et la machine à écrire
   ------------------------------------------------------------------------- */

function ligneCorps(ligne) {
  if (ligne.type === 'vide') return el('div', { class: 'kiosque__ligne kiosque__ligne--vide' });
  const glyphe = GLYPHES[ligne.type] || '';
  return el('p', { class: ['kiosque__ligne', 'kiosque__ligne--' + ligne.type] },
    glyphe ? el('span', { class: 'kiosque__glyphe', 'aria-hidden': 'true' }, glyphe) : null,
    el('span', { class: 'kiosque__ligne-texte', dataset: { texte: ligne.texte } }, ''));
}

/**
 * Écrit les lignes une à une, caractère par caractère. Sous « mouvement
 * réduit », tout s'affiche d'un coup. Un clic dans le projecteur termine
 * l'écriture immédiatement. Renvoie une fonction d'annulation.
 */
function machineAEcrire(conteneur, curseur) {
  const spans = Array.from(conteneur.querySelectorAll('.kiosque__ligne-texte'));
  const textes = spans.map((s) => s.dataset.texte || '');
  let annule = false;
  let minuteur = 0;

  const terminer = () => {
    annule = true;
    clearTimeout(minuteur);
    spans.forEach((s, i) => { s.textContent = textes[i]; });
    if (curseur) curseur.hidden = true;
  };

  if (mouvementReduit() || !spans.length) { terminer(); return terminer; }

  let i = 0; let c = 0;
  if (curseur) curseur.hidden = false;
  const pas = () => {
    if (annule) return;
    if (i >= spans.length) { if (curseur) curseur.hidden = true; return; }
    const cible = textes[i];
    if (c < cible.length) {
      // Par mots plutôt que par lettre : plus rapide, même effet.
      const suivant = cible.indexOf(' ', c + 1);
      c = suivant === -1 ? cible.length : suivant;
      spans[i].textContent = cible.slice(0, c);
      minuteur = setTimeout(pas, 22);
    } else {
      i += 1; c = 0;
      minuteur = setTimeout(pas, 90);
    }
  };
  pas();
  return terminer;
}

function projecteur(prefixe) {
  const badgeProgramme = el('span', { class: 'badge badge--accent kiosque__programme' }, '');
  const badgeStatut = el('span', { class: 'badge' }, '');
  const date = el('time', { class: 'kiosque__projecteur-date mono' }, '');
  const titre = el('h3', { class: 'kiosque__projecteur-titre', id: prefixe + '-projecteur-titre' }, '');
  const resume = el('p', { class: 'kiosque__projecteur-resume' }, '');
  const corps = el('div', { class: 'kiosque__corps' });
  const curseur = el('span', { class: 'kiosque__curseur', 'aria-hidden': 'true', hidden: true });
  const signature = el('p', { class: 'kiosque__signature', hidden: true });
  const pole = el('span', { class: 'kiosque__projecteur-pole' });

  const boutonCopier = el('button', {
    type: 'button', class: 'bouton bouton--discret bouton--compact',
    dataset: { action: 'copier' }
  }, 'Copier le texte');
  const lienPartager = el('a', {
    class: 'bouton bouton--secondaire bouton--compact', href: '#', dataset: { action: 'partager' }
  }, 'Partager');

  const racine = el('article', {
    class: 'kiosque__projecteur',
    'aria-labelledby': titre.id,
    tabIndex: -1
  },
  el('div', { class: 'kiosque__projecteur-tete' },
    el('span', { class: 'rangee rangee--serree' }, badgeProgramme, badgeStatut, pole),
    date),
  titre,
  resume,
  el('div', { class: 'kiosque__projecteur-corps' }, corps, curseur),
  signature,
  el('div', { class: 'kiosque__projecteur-pied' }, lienPartager, boutonCopier));

  return { racine, badgeProgramme, badgeStatut, date, titre, resume, corps, curseur, signature, pole, lienPartager };
}

/* -------------------------------------------------------------------------
   6. Le kiosque complet
   ------------------------------------------------------------------------- */

/**
 * @param {object} options
 * @param {object[]} options.dossiers      voir dossiersDepuisCommunications()
 * @param {string[]} [options.alertes]
 * @param {string} [options.id]            préfixe d'identifiants (défaut 'kiosque')
 * @param {string} [options.titreFil]      intitulé du fil (défaut « Fil du service »)
 * @param {Array<{cle:string, libelle:string}>} [options.filtres]  puces de pôle
 * @param {(dossier:object)=>void} [options.surSelection]
 * @returns {HTMLElement}
 */
export function kiosque(options) {
  const opts = options || {};
  const prefixe = texte(opts.id) || 'kiosque';
  const tous = Array.isArray(opts.dossiers) ? opts.dossiers : [];
  const alertes = Array.isArray(opts.alertes) ? opts.alertes : [];
  const filtres = Array.isArray(opts.filtres) ? opts.filtres : [];

  let filtre = '';
  let courant = null;
  let arreterEcriture = () => {};

  const proj = projecteur(prefixe);
  const zoneFil = el('div', { class: 'kiosque__defile', tabIndex: 0 });
  const compteur = el('span', { class: 'kiosque__flux-compte mono' }, '');

  const puces = filtres.length
    ? el('ul', { class: 'facettes kiosque__filtres', 'aria-label': 'Filtrer le fil par pôle' },
        [{ cle: '', libelle: 'Tous' }].concat(filtres).map((f) => el('li', {},
          el('button', {
            type: 'button', class: 'facette facette--compacte',
            'aria-pressed': f.cle === '' ? 'true' : 'false',
            dataset: { filtre: f.cle }
          }, f.libelle))))
    : null;

  const visibles = () => tous.filter((d) => !filtre || d.pole === filtre || d.groupe === 'mot');

  function lire(dossier) {
    courant = dossier;
    arreterEcriture();
    zoneFil.querySelectorAll('.kiosque__carte').forEach((b) => {
      b.setAttribute('aria-current', b.dataset.id === dossier.id ? 'true' : 'false');
    });
    const statut = STATUTS[dossier.statut] || STATUTS.info;
    proj.badgeProgramme.textContent = dossier.programme || 'Général';
    proj.badgeStatut.className = 'badge ' + statut.classe;
    proj.badgeStatut.textContent = statut.libelle;
    monter(proj.pole, pastillePole(dossier.pole));
    proj.date.textContent = dateLongue(dossier.date) || 'Date à renseigner';
    proj.date.setAttribute('datetime', dossier.date || '');
    proj.titre.textContent = dossier.titre || 'Sans titre';
    const lede = dossier.lede !== undefined ? dossier.lede : dossier.resume;
    proj.resume.textContent = lede || '';
    proj.resume.hidden = !lede;
    monter(proj.corps, dossier.lignes.length
      ? dossier.lignes.map(ligneCorps)
      : el('p', { class: 'kiosque__ligne texte-doux' }, 'Aucun détail publié pour cette entrée.'));
    if (dossier.auteur) {
      monter(proj.signature,
        el('strong', {}, dossier.auteur),
        dossier.fonction ? el('span', { class: 'texte-doux' }, ' — ' + dossier.fonction) : null);
      proj.signature.hidden = false;
    } else {
      proj.signature.hidden = true;
    }
    const sujet = encodeURIComponent('[ETII] ' + (dossier.titre || ''));
    const corpsMail = encodeURIComponent(
      (dossier.titre || '') + '\n' + (dateLongue(dossier.date) || '') + '\n\n'
      + dossier.lignes.map((l) => (GLYPHES[l.type] ? GLYPHES[l.type] + ' ' : '') + l.texte).join('\n'));
    proj.lienPartager.href = 'mailto:?subject=' + sujet + '&body=' + corpsMail;
    proj.racine.classList.remove('kiosque__projecteur--entre');
    void proj.racine.offsetWidth; // relance la transition d'entrée
    proj.racine.classList.add('kiosque__projecteur--entre');
    arreterEcriture = machineAEcrire(proj.corps, proj.curseur);
    if (typeof opts.surSelection === 'function') opts.surSelection(dossier);
  }

  function rendreFil() {
    const liste = visibles();
    compteur.textContent = liste.length ? String(liste.length) : '';
    monter(zoneFil, liste.length
      ? fil(liste, prefixe)
      : el('p', { class: 'kiosque__vide texte-doux' }, 'Rien à lire pour ce pôle pour le moment.'));
    const cible = liste.find((d) => courant && d.id === courant.id) || liste[0];
    if (cible) lire(cible); else viderProjecteur();
  }

  function viderProjecteur() {
    courant = null;
    proj.titre.textContent = 'Aucune communication';
    proj.resume.hidden = true;
    proj.badgeProgramme.textContent = '—';
    proj.badgeStatut.textContent = '';
    proj.date.textContent = '';
    monter(proj.corps);
    proj.signature.hidden = true;
  }

  zoneFil.addEventListener('click', (evt) => {
    const bouton = evt.target.closest('.kiosque__carte');
    if (!bouton) return;
    const dossier = tous.find((d) => d.id === bouton.dataset.id);
    if (dossier) { lire(dossier); annoncer(dossier.titre); }
  });

  zoneFil.addEventListener('keydown', (evt) => {
    if (evt.key !== 'ArrowDown' && evt.key !== 'ArrowUp' && evt.key !== 'Home' && evt.key !== 'End') return;
    const boutons = Array.from(zoneFil.querySelectorAll('.kiosque__carte'));
    if (!boutons.length) return;
    const position = boutons.findIndex((b) => b === document.activeElement);
    let suivant = position;
    if (evt.key === 'ArrowDown') suivant = Math.min(boutons.length - 1, position + 1);
    if (evt.key === 'ArrowUp') suivant = Math.max(0, position - 1);
    if (evt.key === 'Home') suivant = 0;
    if (evt.key === 'End') suivant = boutons.length - 1;
    evt.preventDefault();
    boutons[suivant].focus();
    boutons[suivant].click();
  });

  if (puces) {
    puces.addEventListener('click', (evt) => {
      const bouton = evt.target.closest('[data-filtre]');
      if (!bouton) return;
      filtre = bouton.dataset.filtre || '';
      puces.querySelectorAll('[data-filtre]').forEach((b) => {
        b.setAttribute('aria-pressed', b === bouton ? 'true' : 'false');
      });
      rendreFil();
    });
  }

  proj.racine.addEventListener('click', (evt) => {
    const bouton = evt.target.closest('[data-action]');
    if (!bouton) { arreterEcriture(); return; }
    if (bouton.dataset.action === 'copier' && courant) {
      const brut = [courant.titre, dateLongue(courant.date), '']
        .concat(courant.lignes.map((l) => (GLYPHES[l.type] ? GLYPHES[l.type] + ' ' : '') + l.texte))
        .join('\n');
      Promise.resolve(copierTexte(brut)).then((ok) => {
        toast(ok === false ? 'Copie impossible dans ce navigateur.' : 'Texte copié.',
              ok === false ? 'erreur' : 'succes');
      });
    }
  });

  const racine = el('section', { class: 'kiosque', id: prefixe },
    bandeauAlertes(alertes),
    el('div', { class: 'kiosque__grille' },
      el('aside', { class: 'kiosque__flux', 'aria-label': texte(opts.titreFil) || 'Fil du service' },
        el('div', { class: 'kiosque__flux-tete' },
          el('span', { class: 'kiosque__flux-titre' }, texte(opts.titreFil) || 'Fil du service', ' ', compteur),
          puces),
        zoneFil),
      proj.racine));

  rendreFil();
  return racine;
}

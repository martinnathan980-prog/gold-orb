/* =========================================================================
   ETII Hub — L'éditeur de communication (« Ajouter une communication »)

   C'est ici que tout se joue : le chef compose sa communication dans le
   site, comme il veut — du texte écrit ligne à ligne, des images, une
   galerie, des chiffres clés, une courbe, des pastilles, un encadré — dans
   l'ordre qu'il choisit, et la voit à droite exactement comme le kiosque
   la rendra. « Publier » l'envoie à la feuille de publication quand elle
   est branchée (SOURCE.publication) ; sinon elle reste dans ce navigateur,
   marquée « brouillon », le temps de brancher la publication.

   Le brouillon en cours est conservé dans ce navigateur. Tout le DOM est
   construit avec el() ; les blocs sont normalisés par kiosque.js — une
   seule vérité pour l'aperçu et la publication.
   ========================================================================= */

import { el, frag, monter, ouvrirModale, stockage, toast, debounce, annoncer } from './ui.js';
import { dossiersDepuisCommunications, apercuLecture, apercuAlertes, blocDepuis, TYPES_BLOC } from './kiosque.js';
import { analyserCorps, corpsEnTexte, analyserSerie, serieEnTexte, publierCommunication,
  communicationsLocales, supprimerLocale, SOURCE } from './communications.js';

const CLE_BROUILLON = 'editeur.communication';

const TYPES = [
  { cle: 'annonce', libelle: 'Annonce', aide: 'Une nouvelle du service ou d’un pôle.' },
  { cle: 'mot', libelle: 'Mot du chef', aide: 'Le message de la direction, en tête de liste.' },
  { cle: 'alerte', libelle: 'Alerte', aide: 'Une phrase pour le bandeau qui défile.' }
];
const POLES = [['ETII', 'Tout le service'], ['ETIIA', 'ETIIA'], ['ETIIE', 'ETIIE'], ['ETIII', 'ETIII']];
const STATUTS = [['info', 'Information'], ['succes', 'Validé'], ['urgent', 'Urgent']];
const TENDANCES = [['', '—'], ['hausse', 'En hausse ↗'], ['baisse', 'En baisse ↘'], ['stable', 'Stable →']];
const TONS = [['info', 'Information'], ['succes', 'Bonne nouvelle'], ['alerte', 'Attention']];

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

function aujourdhui() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function identifiant() {
  return 'c' + aujourdhui().replace(/-/g, '') + '-' + Math.random().toString(36).slice(2, 6);
}

/* Un bloc vide de chaque type, tel que l'éditeur le manipule (champs en
   texte, jamais normalisés avant l'aperçu). */
function blocVide(type) {
  switch (type) {
    case 'texte': return { type, texte: '' };
    case 'image': return { type, src: '', alt: '', legende: '' };
    case 'galerie': return { type, images: [{ src: '', alt: '', legende: '' }, { src: '', alt: '', legende: '' }] };
    case 'chiffres': return { type, chiffres: [0, 1, 2, 3].map(() => ({ libelle: '', valeur: '', unite: '', tendance: '' })) };
    case 'courbe': return { type, libelle: '', unite: '', points: '' };
    case 'pastilles': return { type, pastilles: '' };
    case 'encadre': return { type, ton: 'info', titre: '', texte: '' };
    default: return null;
  }
}

function brouillonVide(pole) {
  return {
    type: 'annonce', id: '', date: aujourdhui(), pole: POLES.some(([c]) => c === pole) ? pole : 'ETII',
    categorie: '', statut: 'info', titre: '', resume: '', auteur: '', fonction: '',
    blocs: [blocVide('texte')]
  };
}

/* -------------------------------------------------------------------------
   1. De l'état de l'éditeur à la communication publiable
   ------------------------------------------------------------------------- */

/* Un bloc de l'éditeur → un bloc de données (forme de communications.json). */
function blocPublie(b) {
  switch (b.type) {
    case 'texte': return { type: 'texte', lignes: analyserCorps(b.texte) };
    case 'image': return { type: 'image', src: texte(b.src), alt: texte(b.alt), legende: texte(b.legende) };
    case 'galerie': return { type: 'galerie', images: b.images.map((i) => ({ src: texte(i.src), alt: texte(i.alt), legende: texte(i.legende) })).filter((i) => i.src) };
    case 'chiffres': return { type: 'chiffres', chiffres: b.chiffres.filter((c) => texte(c.libelle) && texte(c.valeur) !== '')
      .map((c) => ({ libelle: texte(c.libelle), valeur: Number(texte(c.valeur).replace(/\s/g, '').replace('%', '').replace(',', '.')), unite: texte(c.unite), tendance: texte(c.tendance) })) };
    case 'courbe': {
      const serie = analyserSerie((texte(b.libelle) || 'Série') + (texte(b.unite) ? ' (' + texte(b.unite) + ')' : '') + ' | ' + texte(b.points));
      return serie ? { type: 'courbe', serie } : { type: 'courbe' };
    }
    case 'pastilles': return { type: 'pastilles', pastilles: texte(b.pastilles).split(/\s*[;,\n]\s*/).map(texte).filter(Boolean) };
    case 'encadre': return { type: 'encadre', ton: b.ton, titre: texte(b.titre), texte: texte(b.texte) };
    default: return null;
  }
}

/** La communication telle qu'elle sera publiée (blocs normalisés). */
function communicationPubliable(etat) {
  const blocs = etat.blocs.map(blocPublie).map(blocDepuis).filter(Boolean);
  const base = {
    id: texte(etat.id) || identifiant(),
    date: texte(etat.date),
    pole: etat.type === 'mot' ? 'ETII' : etat.pole,
    categorie: texte(etat.categorie) || 'Général',
    statut: etat.statut,
    titre: texte(etat.titre),
    resume: texte(etat.resume),
    corps: [],
    blocs
  };
  /* Les colonnes à plat restent renseignées pour la feuille et les vieux
     lecteurs : la première image, les premiers chiffres, la première
     courbe, le premier texte. */
  const premier = (type) => blocs.find((b) => b.type === type);
  const image = premier('image'); if (image) base.image = { src: image.src, alt: image.alt, legende: image.legende };
  const chiffres = premier('chiffres'); if (chiffres) base.chiffres = chiffres.chiffres;
  const courbe = premier('courbe'); if (courbe) base.serie = courbe.serie;
  const txt = premier('texte'); if (txt) base.corps = txt.lignes;
  if (etat.type === 'mot') { base.auteur = texte(etat.auteur); base.fonction = texte(etat.fonction); }
  return base;
}

function valider(etat) {
  const erreurs = [];
  if (etat.type === 'alerte') {
    if (!texte(etat.titre)) erreurs.push('Le texte de l’alerte est vide.');
    return erreurs;
  }
  if (!texte(etat.titre)) erreurs.push('Le titre est obligatoire.');
  if (!texte(etat.resume)) erreurs.push('Le résumé est obligatoire : c’est ce qu’on lit dans la liste.');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(texte(etat.date)) || Number.isNaN(Date.parse(etat.date))) erreurs.push('La date doit être au format AAAA-MM-JJ.');
  etat.blocs.forEach((b, i) => {
    const n = 'Bloc ' + (i + 1) + ' (' + (TYPES_BLOC[b.type] || b.type) + ')';
    if (b.type === 'image' && texte(b.src) && !/^https:\/\/|^assets\//.test(texte(b.src))) erreurs.push(n + ' : l’adresse doit commencer par https:// ou assets/.');
    if (b.type === 'image' && texte(b.src) && !texte(b.alt)) erreurs.push(n + ' : décrivez l’image (lecteurs d’écran).');
    if (b.type === 'galerie' && b.images.some((im) => texte(im.src) && !/^https:\/\/|^assets\//.test(texte(im.src)))) erreurs.push(n + ' : chaque adresse doit commencer par https:// ou assets/.');
    if (b.type === 'courbe' && texte(b.points) && !analyserSerie('x | ' + texte(b.points))) erreurs.push(n + ' : écrivez « 2026-01 = 95,2 ; 2026-02 = 96 ».');
    if (b.type === 'chiffres' && b.chiffres.some((c) => texte(c.libelle) && texte(c.valeur) !== '' && Number.isNaN(Number(texte(c.valeur).replace(/\s/g, '').replace('%', '').replace(',', '.'))))) erreurs.push(n + ' : une valeur doit être un nombre.');
  });
  if (!communicationPubliable(etat).blocs.length) erreurs.push('Ajoutez au moins un bloc avec du contenu.');
  return erreurs;
}

/* -------------------------------------------------------------------------
   2. Les champs
   ------------------------------------------------------------------------- */

let compteurId = 0;
function idChamp() { compteurId += 1; return 'editeur-' + compteurId; }

function champ(libelle, controle, aide) {
  const id = idChamp();
  controle.id = id;
  if (aide) controle.setAttribute('aria-describedby', id + '-aide');
  return el('div', { class: 'champ' },
    el('label', { class: 'champ__etiquette', for: id }, libelle),
    controle,
    aide ? el('p', { class: 'champ__aide', id: id + '-aide' }, aide) : null);
}

function lier(noeud, objet, cle, surChangement) {
  noeud.value = objet[cle] || '';
  noeud.addEventListener(noeud.tagName === 'SELECT' ? 'change' : 'input', () => { objet[cle] = noeud.value; surChangement(); });
  return noeud;
}

function entree(objet, cle, attrs, surChangement) {
  return lier(el('input', Object.assign({ class: 'champ__controle', type: 'text', autocomplete: 'off' }, attrs || {})), objet, cle, surChangement);
}

function zone(objet, cle, attrs, surChangement) {
  return lier(el('textarea', Object.assign({ class: 'champ__controle', rows: 4 }, attrs || {})), objet, cle, surChangement);
}

function selection(objet, cle, paires, surChangement, attrs) {
  const n = el('select', Object.assign({ class: 'champ__controle' }, attrs || {}),
    paires.map(([valeur, libelle]) => el('option', { value: valeur }, libelle)));
  return lier(n, objet, cle, surChangement);
}

/* -------------------------------------------------------------------------
   3. Les blocs
   ------------------------------------------------------------------------- */

function corpsBloc(b, surChangement, rendre) {
  switch (b.type) {
    case 'texte':
      return champ('Texte', zone(b, 'texte', { rows: 7, placeholder: '-> Ce qui change\n• Une puce.\n• Une autre.\n\nV Ce qui est acquis.\n! Ce qu’il faut faire avant vendredi.' }, surChangement),
        'Une ligne par idée. « -> » titre, « • » ou « - » puce, « V » validé, « ! » alerte ; une ligne vide aère.');
    case 'image':
      return frag(
        champ('Adresse de l’image', entree(b, 'src', { type: 'url', placeholder: 'https://… ou assets/img/communications/…' }, surChangement),
          'Une image publique (lien direct) ou un fichier du site. En premier bloc, elle ouvre la communication en bannière.'),
        el('div', { class: 'editeur__rangee' },
          champ('Description', entree(b, 'alt', { placeholder: 'Un H160 sur un salon' }, surChangement), 'Pour les lecteurs d’écran.'),
          champ('Légende', entree(b, 'legende', { placeholder: 'Facultative, affichée sous l’image' }, surChangement))));
    case 'galerie':
      return el('div', { class: 'pile pile--serree' },
        el('p', { class: 'champ__aide sans-marge' }, 'Des diapositives qu’on fait défiler. Jusqu’à huit images.'),
        b.images.map((im, i) => el('div', { class: 'editeur__diapo' },
          el('span', { class: 'editeur__diapo-rang mono' }, String(i + 1)),
          entree(im, 'src', { type: 'url', placeholder: 'https://… ou assets/…', 'aria-label': 'Adresse de l’image ' + (i + 1) }, surChangement),
          entree(im, 'alt', { placeholder: 'Description', 'aria-label': 'Description de l’image ' + (i + 1) }, surChangement),
          entree(im, 'legende', { placeholder: 'Légende', 'aria-label': 'Légende de l’image ' + (i + 1) }, surChangement),
          el('button', { type: 'button', class: 'bouton bouton--icone bouton--compact', 'aria-label': 'Retirer l’image ' + (i + 1),
            onClick: () => { b.images.splice(i, 1); if (!b.images.length) b.images.push({ src: '', alt: '', legende: '' }); rendre(); surChangement(); } }, '×'))),
        b.images.length < 8 ? el('button', { type: 'button', class: 'bouton bouton--secondaire bouton--compact',
          onClick: () => { b.images.push({ src: '', alt: '', legende: '' }); rendre(); } }, '+ Une image') : null);
    case 'chiffres':
      return el('div', { class: 'pile pile--serree' },
        el('p', { class: 'champ__aide sans-marge' }, 'Jusqu’à quatre tuiles : libellé, valeur, unité, tendance.'),
        b.chiffres.map((c, i) => el('div', { class: 'editeur__chiffre' },
          entree(c, 'libelle', { placeholder: 'Libellé', 'aria-label': 'Libellé du chiffre ' + (i + 1) }, surChangement),
          entree(c, 'valeur', { placeholder: 'Valeur', inputmode: 'decimal', 'aria-label': 'Valeur du chiffre ' + (i + 1) }, surChangement),
          entree(c, 'unite', { placeholder: 'Unité', 'aria-label': 'Unité du chiffre ' + (i + 1) }, surChangement),
          selection(c, 'tendance', TENDANCES, surChangement, { 'aria-label': 'Tendance du chiffre ' + (i + 1) }))));
    case 'courbe':
      return frag(
        el('div', { class: 'editeur__rangee' },
          champ('Libellé', entree(b, 'libelle', { placeholder: 'OTQ mensuel' }, surChangement)),
          champ('Unité', entree(b, 'unite', { placeholder: '%' }, surChangement))),
        champ('Points', zone(b, 'points', { rows: 2, placeholder: '2026-04 = 92,1 ; 2026-05 = 92,8 ; 2026-06 = 93,6' }, surChangement),
          '« mois = valeur », séparés par des points-virgules. Un mois sans valeur laisse un trou.'));
    case 'pastilles':
      return champ('Pastilles', entree(b, 'pastilles', { placeholder: 'H160, Lot 3, Essais' }, surChangement), 'Des mots-clés séparés par des virgules.');
    case 'encadre':
      return frag(
        el('div', { class: 'editeur__rangee' },
          champ('Ton', selection(b, 'ton', TONS, surChangement)),
          champ('Titre', entree(b, 'titre', { placeholder: 'Facultatif' }, surChangement))),
        champ('Texte', zone(b, 'texte', { rows: 3, placeholder: 'Ce qu’il faut retenir.' }, surChangement)));
    default:
      return null;
  }
}

function carteBloc(etat, index, surChangement, rendre) {
  const b = etat.blocs[index];
  const deplacer = (delta) => {
    const j = index + delta;
    if (j < 0 || j >= etat.blocs.length) return;
    [etat.blocs[index], etat.blocs[j]] = [etat.blocs[j], etat.blocs[index]];
    rendre(); surChangement();
  };
  return el('section', { class: 'editeur__bloc', 'aria-label': 'Bloc ' + (index + 1) + ' : ' + (TYPES_BLOC[b.type] || b.type) },
    el('header', { class: 'editeur__bloc-tete' },
      el('span', { class: 'editeur__bloc-rang mono' }, String(index + 1)),
      el('span', { class: 'editeur__bloc-type' }, TYPES_BLOC[b.type] || b.type),
      el('span', { class: 'editeur__bloc-outils' },
        el('button', { type: 'button', class: 'bouton bouton--icone bouton--compact', 'aria-label': 'Monter le bloc', disabled: index === 0 ? true : null, onClick: () => deplacer(-1) }, '↑'),
        el('button', { type: 'button', class: 'bouton bouton--icone bouton--compact', 'aria-label': 'Descendre le bloc', disabled: index === etat.blocs.length - 1 ? true : null, onClick: () => deplacer(1) }, '↓'),
        el('button', { type: 'button', class: 'bouton bouton--icone bouton--compact', 'aria-label': 'Supprimer le bloc',
          onClick: () => { etat.blocs.splice(index, 1); rendre(); surChangement(); } }, '×'))),
    el('div', { class: 'editeur__bloc-corps' }, corpsBloc(b, surChangement, rendre)));
}

function barreAjout(etat, rendre, surChangement) {
  return el('div', { class: 'editeur__ajout', role: 'group', 'aria-label': 'Ajouter un bloc' },
    el('span', { class: 'editeur__ajout-libelle' }, 'Ajouter'),
    Object.entries(TYPES_BLOC).map(([type, libelle]) => el('button', {
      type: 'button', class: 'bouton bouton--secondaire bouton--compact',
      onClick: () => { etat.blocs.push(blocVide(type)); rendre(); surChangement(); }
    }, libelle)));
}

/* -------------------------------------------------------------------------
   4. L'éditeur
   ------------------------------------------------------------------------- */

/**
 * Ouvre l'éditeur dans une fenêtre.
 * @param {object} [options]
 * @param {string} [options.pole]         pôle présélectionné (ETIIA…) ; ETII par défaut
 * @param {HTMLElement} [options.declencheur]
 * @param {() => void} [options.surPublication]  appelé après une publication réussie
 */
export function ouvrirEditeur(options) {
  const opts = options || {};
  const brouillon = stockage.lire(CLE_BROUILLON, null);
  const etat = (brouillon && typeof brouillon === 'object' && Array.isArray(brouillon.blocs))
    ? Object.assign(brouillonVide(opts.pole), brouillon)
    : brouillonVide(opts.pole);
  if (!etat.blocs.length) etat.blocs = [blocVide('texte')];

  const zoneFormulaire = el('div', { class: 'editeur__formulaire' });
  const zoneApercu = el('div', { class: 'editeur__apercu-zone', 'aria-live': 'polite' });
  const zoneErreurs = el('ul', { class: 'editeur__erreurs', hidden: true });
  const zoneLocaux = el('div', { class: 'editeur__locaux' });
  let modale = null;

  function objetApercu() {
    const com = communicationPubliable(etat);
    if (etat.type === 'alerte') return { motDuChef: null, alertes: [texte(etat.titre) || 'Texte de l’alerte…'], annonces: [], agenda: [] };
    if (!texte(com.titre)) com.titre = 'Titre à écrire';
    if (etat.type === 'mot') return { motDuChef: com, alertes: [], annonces: [], agenda: [] };
    return { motDuChef: null, alertes: [], annonces: [com], agenda: [] };
  }

  function rendreApercu() {
    const objet = objetApercu();
    if (etat.type === 'alerte') { monter(zoneApercu, apercuAlertes(objet.alertes)); return; }
    const dossier = dossiersDepuisCommunications(objet, { pole: 'ETII' })[0];
    monter(zoneApercu, dossier ? apercuLecture(dossier) : null);
  }

  function rendreErreurs() {
    const erreurs = valider(etat);
    monter(zoneErreurs, erreurs.map((e) => el('li', {}, e)));
    zoneErreurs.hidden = !erreurs.length;
    return erreurs;
  }

  const surChangement = debounce(() => {
    stockage.ecrire(CLE_BROUILLON, etat);
    rendreApercu();
    if (!zoneErreurs.hidden) rendreErreurs();
  }, 120);

  function rendreLocaux() {
    const l = communicationsLocales();
    const entrees = [];
    if (l.motDuChef) entrees.push({ id: 'mot-du-chef', libelle: 'Mot du chef : ' + texte(l.motDuChef.titre) });
    l.annonces.forEach((a) => entrees.push({ id: a.id, libelle: texte(a.date) + ' — ' + texte(a.titre) }));
    l.alertes.forEach((a) => entrees.push({ id: 'alerte:' + a, libelle: 'Alerte : ' + a }));
    if (!entrees.length) { monter(zoneLocaux); return; }
    monter(zoneLocaux,
      el('p', { class: 'editeur__locaux-titre' }, 'Publié dans ce navigateur seulement'),
      el('ul', { class: 'editeur__locaux-liste', role: 'list' }, entrees.map((e) => el('li', {},
        el('span', {}, e.libelle),
        el('button', { type: 'button', class: 'bouton bouton--discret bouton--compact', onClick: () => {
          supprimerLocale(e.id); rendreLocaux(); toast('Retirée de ce navigateur.', 'succes');
          if (typeof opts.surPublication === 'function') opts.surPublication();
        } }, 'Retirer')))));
  }

  function rendreFormulaire() {
    const estAlerte = etat.type === 'alerte';
    const estMot = etat.type === 'mot';
    const types = el('div', { class: 'editeur__types', role: 'radiogroup', 'aria-label': 'Type de communication' },
      TYPES.map((t) => {
        const id = idChamp();
        const radio = el('input', { type: 'radio', name: 'editeur-type', id, value: t.cle, checked: etat.type === t.cle ? true : null });
        radio.addEventListener('change', () => { if (radio.checked) { etat.type = t.cle; rendreFormulaire(); surChangement(); } });
        return el('label', { class: 'editeur__type', for: id }, radio,
          el('span', { class: 'editeur__type-libelle' }, t.libelle),
          el('span', { class: 'editeur__type-aide' }, t.aide));
      }));

    monter(zoneFormulaire,
      types,
      estAlerte
        ? champ('Texte de l’alerte', entree(etat, 'titre', { placeholder: 'Maintenance de la plateforme documentaire mercredi soir.' }, surChangement),
            'Une phrase courte. Le bandeau en fait défiler plusieurs.')
        : frag(
          el('div', { class: 'editeur__rangee' },
            champ('Date', entree(etat, 'date', { type: 'date' }, surChangement)),
            estMot ? null : champ('Pôle', selection(etat, 'pole', POLES, surChangement)),
            estMot ? null : champ('Statut', selection(etat, 'statut', STATUTS, surChangement))),
          champ('Titre', entree(etat, 'titre', { placeholder: estMot ? 'Un trimestre qui se tient' : 'Validation du jalon de définition' }, surChangement)),
          champ('Résumé', zone(etat, 'resume', { rows: 2, placeholder: 'Une ou deux phrases : ce qu’on lit dans la liste et en chapeau.' }, surChangement)),
          estMot
            ? el('div', { class: 'editeur__rangee' },
                champ('Auteur', entree(etat, 'auteur', { placeholder: 'Personne 01' }, surChangement)),
                champ('Fonction', entree(etat, 'fonction', { placeholder: 'Direction du service' }, surChangement)))
            : champ('Catégorie', entree(etat, 'categorie', { placeholder: 'H160, Outils, Transverse…' }, surChangement), 'Un programme ou un thème, affiché en étiquette.'),
          el('h3', { class: 'editeur__sous-titre' }, 'Le contenu, bloc par bloc'),
          el('div', { class: 'editeur__blocs' }, etat.blocs.map((_b, i) => carteBloc(etat, i, surChangement, rendreFormulaire))),
          barreAjout(etat, rendreFormulaire, surChangement)));
  }

  async function publier() {
    const erreurs = rendreErreurs();
    if (erreurs.length) { toast('Complétez ce qui est signalé avant de publier.', 'alerte'); return false; }
    const com = communicationPubliable(etat);
    try {
      const retour = await publierCommunication(etat.type, etat.type === 'alerte' ? texte(etat.titre) : com);
      if (!retour.ok) { toast(retour.message, 'erreur'); return false; }
      toast(retour.message, 'succes');
      annoncer('Communication publiée.');
      stockage.supprimer(CLE_BROUILLON);
      if (typeof opts.surPublication === 'function') opts.surPublication();
      return true;
    } catch (e) {
      toast('Publication impossible : ' + (e && e.message ? e.message : 'erreur réseau') + '. Le brouillon est conservé.', 'erreur');
      return false;
    }
  }

  modale = ouvrirModale({
    titre: 'Ajouter une communication',
    classe: 'modale--editeur',
    declencheur: opts.declencheur || null,
    contenu: () => el('div', { class: 'editeur' },
      el('div', { class: 'editeur__colonne' },
        el('p', { class: 'editeur__intro' },
          texte(SOURCE.publication)
            ? 'Ce que vous publiez est ajouté à la feuille de publication : tout le monde le voit à la prochaine ouverture.'
            : 'La publication n’est pas encore branchée : ce que vous publiez reste dans ce navigateur, marqué « brouillon ». ',
          texte(SOURCE.publication) ? null : el('a', { href: 'docs/COMMUNICATIONS-GOOGLE-SHEETS.md' }, 'Comment brancher la publication')),
        zoneFormulaire,
        zoneErreurs,
        zoneLocaux),
      el('div', { class: 'editeur__colonne editeur__colonne--apercu' },
        el('p', { class: 'editeur__apercu-titre' }, 'Aperçu'),
        zoneApercu)),
    actions: [
      { libelle: 'Vider', variante: 'discret', ferme: false, onClick: () => {
        Object.assign(etat, brouillonVide(opts.pole)); stockage.supprimer(CLE_BROUILLON);
        rendreFormulaire(); rendreApercu(); zoneErreurs.hidden = true; return false;
      } },
      { libelle: 'Fermer', variante: 'secondaire', ferme: true },
      { libelle: 'Publier', variante: 'principal', ferme: false, onClick: () => { publier().then((ok) => { if (ok && modale) modale.fermer('publie'); }); return false; } }
    ]
  });

  rendreFormulaire();
  rendreApercu();
  rendreLocaux();
  return modale;
}

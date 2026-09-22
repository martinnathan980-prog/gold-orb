/* =========================================================================
   ETII Hub — L'éditeur de communication (« Ajouter une communication »)

   C'est ici que tout se joue : l'auteur compose sa communication dans le
   site, comme il veut — du texte écrit ligne à ligne, des images, une
   galerie, des chiffres clés, une courbe, des pastilles, un encadré — dans
   l'ordre qu'il choisit, et la voit à droite exactement comme le kiosque
   la rendra. « Publier » l'envoie à la feuille de publication quand elle
   est branchée (SOURCE.publication) ; sinon elle reste dans ce navigateur,
   marquée « brouillon », le temps de brancher la publication.

   La mise en page se fait à la souris, dans l'aperçu : chaque bloc rendu
   est pris dans un cadre d'édition — une poignée pour le déplacer entre
   les autres, une poignée sur son bord pour le rétrécir ou l'élargir (la
   largeur s'aimante sur tiers, moitié, deux tiers, pleine), deux boutons
   pour le caler à gauche ou à droite. Le formulaire de gauche montre les
   mêmes réglages en listes : les deux parlent au même état, tout se voit
   en temps réel.

   Le brouillon en cours est conservé dans ce navigateur. Tout le DOM est
   construit avec el() ; les blocs sont normalisés par kiosque.js — une
   seule vérité pour l'aperçu et la publication.
   ========================================================================= */

import { el, frag, monter, ouvrirModale, stockage, toast, debounce, annoncer } from './ui.js';
import { dossiersDepuisCommunications, apercuLecture, apercuAlertes, blocDepuis, dateLongue,
  TYPES_BLOC, LARGEURS_BLOC, COTES_BLOC } from './kiosque.js';
import { analyserCorps, corpsEnTexte, analyserSerie, serieEnTexte, publierCommunication,
  communicationsLocales, supprimerLocale, SOURCE } from './communications.js';

/* Le préfixe du brouillon : la clé réelle y ajoute le pôle de la page d'où
   l'éditeur est ouvert (voir ouvrirEditeur). */
const CLE_BROUILLON = 'editeur.communication';

/* Le type `mot` s'appelle « Édito » pour qui écrit : la clé ne change pas
   (données, feuille), seul le mot change. */
const TYPES = [
  { cle: 'annonce', libelle: 'Annonce', aide: 'Une nouvelle du service ou d’un pôle.' },
  { cle: 'mot', libelle: 'Édito', aide: 'Le message de la direction, en tête de liste.' },
  { cle: 'alerte', libelle: 'Alerte', aide: 'Une phrase pour le bandeau qui défile.' }
];

/* La mise en page d'un bloc, dans les mots de kiosque.js : sa largeur dans
   la grille de six colonnes (et la fraction qu'elle occupe, pour aimanter
   la poignée) et le côté où il se cale. */
const LARGEURS = [
  { cle: 'pleine', libelle: 'Pleine largeur', court: 'Pleine', fraction: 1 },
  { cle: 'deux-tiers', libelle: 'Deux tiers', court: '2⁄3', fraction: 2 / 3 },
  { cle: 'moitie', libelle: 'Moitié', court: '½', fraction: 1 / 2 },
  { cle: 'tiers', libelle: 'Un tiers', court: '⅓', fraction: 1 / 3 }
];
const COTES = [
  { cle: '', libelle: 'Dans le flux', court: 'Flux' },
  { cle: 'gauche', libelle: 'Calé à gauche', court: 'Gauche' },
  { cle: 'droite', libelle: 'Calé à droite', court: 'Droite' }
];
/* De la plus étroite à la plus large : c'est l'ordre des flèches ← →. */
const ORDRE_LARGEURS = ['tiers', 'moitie', 'deux-tiers', 'pleine'];

function largeurDe(b) { return LARGEURS_BLOC.includes(b.largeur) ? b.largeur : 'pleine'; }
function coteDe(b) { return COTES_BLOC.includes(b.cote) ? b.cote : ''; }
function libelleLargeur(cle) { return (LARGEURS.find((l) => l.cle === cle) || LARGEURS[0]).libelle; }
function courtLargeur(cle) { return (LARGEURS.find((l) => l.cle === cle) || LARGEURS[0]).court; }
function libelleCote(cle) { return (COTES.find((c) => c.cle === cle) || COTES[0]).libelle; }

/* La largeur la plus proche d'une fraction de la grille : c'est l'aimant
   de la poignée de redimensionnement. */
function largeurAimantee(fraction) {
  let choix = LARGEURS[0];
  LARGEURS.forEach((l) => { if (Math.abs(l.fraction - fraction) < Math.abs(choix.fraction - fraction)) choix = l; });
  return choix.cle;
}

/* Un cran plus large (+1) ou plus étroit (−1), sans sortir de l'échelle. */
function largeurVoisine(cle, delta) {
  const i = ORDRE_LARGEURS.indexOf(largeurDe({ largeur: cle }));
  return ORDRE_LARGEURS[Math.min(ORDRE_LARGEURS.length - 1, Math.max(0, i + delta))];
}
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
   texte, jamais normalisés avant l'aperçu). Il naît en pleine largeur,
   dans le flux. */
function blocVide(type) {
  const b = contenuVide(type);
  return b ? Object.assign(b, { largeur: 'pleine', cote: '' }) : null;
}

function contenuVide(type) {
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

/* -------------------------------------------------------------------------
   0. Les gestes sur l'état : les mêmes depuis la carte de gauche et depuis
      l'aperçu
   ------------------------------------------------------------------------- */

/* Déplace le bloc `de` avant (ou après, si `apres`) le bloc `cible`. Les
   deux sont des indices de etat.blocs ; rend l'indice d'arrivée. */
function deplacerBloc(etat, de, cible, apres) {
  if (de === cible) return de;
  const [b] = etat.blocs.splice(de, 1);
  let vers = cible > de ? cible - 1 : cible;
  if (apres) vers += 1;
  etat.blocs.splice(vers, 0, b);
  return vers;
}

/* Échange le bloc avec son voisin (delta −1 ou +1) ; rend l'indice d'arrivée. */
function decalerBloc(etat, index, delta) {
  const j = index + delta;
  if (j < 0 || j >= etat.blocs.length) return index;
  [etat.blocs[index], etat.blocs[j]] = [etat.blocs[j], etat.blocs[index]];
  return j;
}

function brouillonVide(pole) {
  return {
    /* L'identifiant naît avec le brouillon et ne change plus : republier
       remplace alors la ligne de la feuille au lieu d'en ajouter une (la
       recherche par identifiant du script de synchronisation ne trouvait
       jamais rien, puisqu'un id neuf était tiré à chaque envoi). */
    type: 'annonce', id: identifiant(), publiee: false,
    date: aujourdhui(), pole: POLES.some(([c]) => c === pole) ? pole : 'ETII',
    categorie: '', statut: 'info', titre: '', resume: '', auteur: '', fonction: '',
    blocs: [blocVide('texte')]
  };
}

/* -------------------------------------------------------------------------
   1. De l'état de l'éditeur à la communication publiable
   ------------------------------------------------------------------------- */

/* Un bloc de l'éditeur → un bloc de données (forme de communications.json),
   avec sa mise en page : `largeur` et `cote` voyagent tels quels dans le
   JSON des blocs, jusqu'à la feuille et retour. */
function blocPublie(b) {
  const publie = contenuPublie(b);
  if (!publie) return null;
  publie.largeur = largeurDe(b);
  publie.cote = coteDe(b);
  return publie;
}

/* L'attribution d'une photo libre (CC BY-SA) voyage telle quelle. L'éditeur
   ne la saisit pas, mais il ne doit pas l'effacer d'une communication qu'on
   reprend : sans elle, la licence n'est plus respectée. */
function creditDe(o) {
  const c = o && o.credit;
  return c ? { auteur: texte(c.auteur), licence: texte(c.licence), page: texte(c.page) } : undefined;
}

function contenuPublie(b) {
  switch (b.type) {
    case 'texte': return { type: 'texte', lignes: analyserCorps(b.texte) };
    case 'image': return { type: 'image', src: texte(b.src), alt: texte(b.alt), legende: texte(b.legende), credit: creditDe(b) };
    case 'galerie': return { type: 'galerie', images: b.images.map((i) => ({ src: texte(i.src), alt: texte(i.alt), legende: texte(i.legende), credit: creditDe(i) })).filter((i) => i.src) };
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
  /* « 2062 » au lieu de « 2026 » épinglerait la communication en tête du
     fil pour toujours : le kiosque trie les dates comme des chaînes, et il
     ne montre que ce qui a eu lieu. Comparaison ISO, donc ni fuseau ni
     Date à manipuler ; le message répète la date fautive, c'est ce qui la
     rend visible à celui qui vient de la taper. */
  if (/^\d{4}-\d{2}-\d{2}$/.test(texte(etat.date)) && texte(etat.date) > aujourdhui()) {
    erreurs.push('Une communication se publie le jour même ou après coup ; le '
      + (dateLongue(etat.date) || texte(etat.date)) + ' est dans le futur.');
  }
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

/* Les id des champs sont régénérés à chaque rendu ; l'indice d'une carte,
   lui, ne bouge pas. C'est par là qu'on rend le clavier au contrôle qui
   vient de servir après une reconstruction du formulaire. */
function ciblerDansBloc(index, selecteur) {
  return '.editeur__bloc[data-index="' + index + '"] ' + selecteur;
}

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
            onClick: () => { b.images.splice(i, 1); if (!b.images.length) b.images.push({ src: '', alt: '', legende: '' });
              rendre('[aria-label="Retirer l’image ' + Math.min(i + 1, b.images.length) + '"]'); surChangement(); } }, '×'))),
        b.images.length < 8 ? el('button', { type: 'button', class: 'bouton bouton--secondaire bouton--compact',
          onClick: () => { b.images.push({ src: '', alt: '', legende: '' });
            rendre('[aria-label="Adresse de l’image ' + b.images.length + '"]'); } }, '+ Une image') : null);
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

/* Un groupe de boutons à état (aria-pressed) : la largeur ou le côté d'un
   bloc, pour qui préfère les listes aux poignées. */
function segments(libelle, choix, valeur, surChoix) {
  return el('div', { class: 'editeur__segments', role: 'group', 'aria-label': libelle },
    el('span', { class: 'editeur__segments-libelle' }, libelle),
    el('span', { class: 'editeur__segments-boutons' },
      choix.map((c) => el('button', {
        type: 'button', class: 'editeur__segment', 'aria-pressed': c.cle === valeur ? 'true' : 'false',
        'aria-label': c.libelle, title: c.libelle, onClick: () => { if (c.cle !== valeur) surChoix(c.cle); }
      }, c.court))));
}

/* La rangée « mise en page » d'une carte : largeur puis côté. Une image en
   premier bloc est la bannière : sa mise en page ne s'applique pas. */
function miseEnPageCarte(etat, index, appliquer) {
  const b = etat.blocs[index];
  if (index === 0 && b.type === 'image') {
    return el('p', { class: 'editeur__mise-en-page editeur__mise-en-page--note champ__aide' },
      'En premier bloc, l’image ouvre la communication en bannière, sur toute la largeur.');
  }
  const garder = (libelle) => ciblerDansBloc(index, '.editeur__segment[aria-label="' + libelle + '"]');
  return el('div', { class: 'editeur__mise-en-page' },
    segments('Largeur', LARGEURS, largeurDe(b), (cle) => { b.largeur = cle; appliquer(null, garder(libelleLargeur(cle))); }),
    segments('Côté', COTES, coteDe(b), (cle) => { b.cote = cle; appliquer(null, garder(libelleCote(cle))); }));
}

function carteBloc(etat, index, surChangement, rendre, appliquer) {
  const b = etat.blocs[index];
  /* Le bouton qui vient de servir garde le clavier — ou son voisin quand le
     bloc arrive en bout de liste et que ce bouton devient inactif : sinon
     une seule pression est possible, puis le focus part sur le document. */
  const deplacer = (delta) => {
    const vers = decalerBloc(etat, index, delta);
    const monte = vers === 0 ? false : (vers === etat.blocs.length - 1 ? true : delta < 0);
    appliquer(null, ciblerDansBloc(vers, '[aria-label="' + (monte ? 'Monter' : 'Descendre') + ' le bloc"]'));
  };
  /* Le rappel de rendu porte l'indice de sa carte : un sélecteur de focus
     demandé par le corps du bloc vise la bonne carte, même quand deux
     galeries se suivent. */
  const rendreIci = (selecteur) => rendre(selecteur ? ciblerDansBloc(index, selecteur) : undefined);
  return el('section', { class: 'editeur__bloc', dataset: { index: String(index) },
    'aria-label': 'Bloc ' + (index + 1) + ' : ' + (TYPES_BLOC[b.type] || b.type) },
    el('header', { class: 'editeur__bloc-tete' },
      el('span', { class: 'editeur__bloc-rang mono' }, String(index + 1)),
      el('span', { class: 'editeur__bloc-type' }, TYPES_BLOC[b.type] || b.type),
      el('span', { class: 'editeur__bloc-outils' },
        el('button', { type: 'button', class: 'bouton bouton--icone bouton--compact', 'aria-label': 'Monter le bloc', disabled: index === 0 ? true : null, onClick: () => deplacer(-1) }, '↑'),
        el('button', { type: 'button', class: 'bouton bouton--icone bouton--compact', 'aria-label': 'Descendre le bloc', disabled: index === etat.blocs.length - 1 ? true : null, onClick: () => deplacer(1) }, '↓'),
        el('button', { type: 'button', class: 'bouton bouton--icone bouton--compact', 'aria-label': 'Supprimer le bloc',
          onClick: () => { etat.blocs.splice(index, 1);
            appliquer(null, ciblerDansBloc(Math.min(index, etat.blocs.length - 1), '[aria-label="Supprimer le bloc"]')); } }, '×'))),
    miseEnPageCarte(etat, index, appliquer),
    el('div', { class: 'editeur__bloc-corps' }, corpsBloc(b, surChangement, rendreIci)));
}

/* -------------------------------------------------------------------------
   3 bis. Le cadre d'édition d'un bloc dans l'aperçu
   ------------------------------------------------------------------------- */

/* Les indices (dans etat.blocs) des blocs que l'aperçu rend réellement, dans
   l'ordre du DOM : les blocs vides n'y sont pas, et une première image est
   la bannière, hors de la grille. C'est ce qui relie chaque enveloppe
   .kiosque__bloc de l'aperçu à sa carte de gauche. */
function indicesRendus(etat) {
  const indices = [];
  etat.blocs.forEach((b, i) => { if (blocDepuis(blocPublie(b))) indices.push(i); });
  if (indices.length && etat.blocs[indices[0]].type === 'image') indices.shift();
  return indices;
}

/* Recopie la mise en page d'un bloc sur son enveloppe, comme rendreBloc
   (kiosque.js) le ferait : c'est ce qui rend le glissement instantané,
   sans reconstruire tout l'aperçu à chaque cran. */
function appliquerMiseEnPage(enveloppe, b) {
  const largeur = largeurDe(b);
  const cote = coteDe(b);
  LARGEURS.forEach((l) => enveloppe.classList.toggle('kiosque__bloc--' + l.cle, l.cle === largeur));
  ['gauche', 'droite'].forEach((c) => enveloppe.classList.toggle('kiosque__bloc--' + c, c === cote));
  enveloppe.dataset.largeur = largeur;
  enveloppe.dataset.cote = cote;
  enveloppe.classList.toggle('editeur__cadre--ancre-droite', cote === 'droite');
  const libelle = enveloppe.querySelector('.editeur__cadre-mise-en-page');
  if (libelle) libelle.textContent = courtLargeur(largeur) + (cote ? ' · ' + libelleCote(cote).toLowerCase() : '');
  const poignee = enveloppe.querySelector('.editeur__poignee--largeur');
  if (poignee) poignee.setAttribute('aria-label', 'Largeur du bloc : ' + libelleLargeur(largeur).toLowerCase() + ' (glisser, ou flèches ← →)');
  enveloppe.querySelectorAll('.editeur__poignee--cote').forEach((btn) => btn.setAttribute('aria-pressed', btn.dataset.cote === cote ? 'true' : 'false'));
}

/**
 * Pose sur chaque bloc rendu de l'aperçu son cadre d'édition : la poignée
 * de déplacement (glisser entre les blocs, ou ↑ ↓ ; ← → pour la largeur),
 * les deux boutons de côté, et la poignée de largeur sur le bord libre du
 * bloc (le bord droit ; le gauche quand le bloc est calé à droite), qui
 * aimante la largeur sur tiers / moitié / deux tiers / pleine.
 * @param {HTMLElement} zone        la zone d'aperçu
 * @param {object} etat
 * @param {(focus?: {index:number, poignee:string}) => void} appliquer
 *        enregistre l'état et reconstruit formulaire et aperçu
 */
function poserCadres(zone, etat, appliquer) {
  const grille = zone.querySelector('.kiosque__blocs');
  if (!grille) return;
  const enveloppes = Array.from(grille.children).filter((n) => n.classList && n.classList.contains('kiosque__bloc'));
  const indices = indicesRendus(etat);
  enveloppes.forEach((enveloppe, k) => {
    const index = indices[k];
    if (index === undefined) return;
    const b = etat.blocs[index];
    enveloppe.classList.add('editeur__cadre');
    enveloppe.dataset.index = String(index);
    const nom = 'Bloc ' + (index + 1) + ' (' + (TYPES_BLOC[b.type] || b.type) + ')';

    const poigneeDeplacer = el('button', {
      type: 'button', class: 'editeur__poignee editeur__poignee--deplacer', dataset: { poignee: 'deplacer' },
      'aria-label': 'Déplacer le ' + nom.toLowerCase() + ' : glisser, ou flèches ↑ ↓ ; ← → pour la largeur',
      title: 'Déplacer (glisser ou ↑ ↓)'
    }, el('span', { 'aria-hidden': 'true' }, '⇅'));
    const boutonsCote = ['gauche', 'droite'].map((cote) => el('button', {
      type: 'button', class: 'editeur__poignee editeur__poignee--cote', dataset: { poignee: cote, cote },
      'aria-label': (cote === 'gauche' ? 'Caler à gauche' : 'Caler à droite') + ' (' + nom.toLowerCase() + ')',
      title: cote === 'gauche' ? 'Caler à gauche' : 'Caler à droite',
      onClick: () => { b.cote = coteDe(b) === cote ? '' : cote; appliquer({ index, poignee: cote }); }
    }, el('span', { 'aria-hidden': 'true' }, cote === 'gauche' ? '◧' : '◨')));
    const poigneeLargeur = el('button', {
      type: 'button', class: 'editeur__poignee editeur__poignee--largeur', dataset: { poignee: 'largeur' },
      title: 'Largeur (glisser ou ← →)'
    }, el('span', { 'aria-hidden': 'true' }, '⋮'));

    enveloppe.append(
      el('div', { class: 'editeur__cadre-outils' },
        poigneeDeplacer,
        el('span', { class: 'editeur__cadre-libelle' },
          el('span', { class: 'editeur__cadre-nom' }, String(index + 1) + ' · ' + (TYPES_BLOC[b.type] || b.type)),
          el('span', { class: 'editeur__cadre-mise-en-page' })),
        boutonsCote),
      poigneeLargeur);
    appliquerMiseEnPage(enveloppe, b);

    /* Clavier, sur les deux poignées : ↑ ↓ déplacent, ← → changent la largeur. */
    const auClavier = (evt, poignee) => {
      if (evt.key === 'ArrowUp' || evt.key === 'ArrowDown') {
        evt.preventDefault();
        const vers = decalerBloc(etat, index, evt.key === 'ArrowUp' ? -1 : 1);
        if (vers !== index) annoncer('Bloc déplacé en position ' + (vers + 1) + '.');
        appliquer({ index: vers, poignee });
      } else if (evt.key === 'ArrowLeft' || evt.key === 'ArrowRight') {
        evt.preventDefault();
        const largeur = largeurVoisine(largeurDe(b), evt.key === 'ArrowRight' ? 1 : -1);
        if (largeur === largeurDe(b)) return;
        b.largeur = largeur;
        annoncer('Largeur : ' + libelleLargeur(largeur).toLowerCase() + '.');
        appliquer({ index, poignee });
      }
    };
    poigneeDeplacer.addEventListener('keydown', (evt) => auClavier(evt, 'deplacer'));
    poigneeLargeur.addEventListener('keydown', (evt) => auClavier(evt, 'largeur'));

    /* La largeur, à la souris : la fraction de la grille couverte par le
       bloc, depuis son bord ancré jusqu'au pointeur, aimantée. */
    poigneeLargeur.addEventListener('pointerdown', (evt) => {
      if (evt.button !== 0) return;
      evt.preventDefault();
      poigneeLargeur.setPointerCapture(evt.pointerId);
      enveloppe.classList.add('editeur__cadre--redimension');
      const g = grille.getBoundingClientRect();
      const ancreDroite = coteDe(b) === 'droite';
      const depart = largeurDe(b);
      const surMouvement = (ev) => {
        if (!g.width) return;
        const fraction = ancreDroite ? (g.right - ev.clientX) / g.width : (ev.clientX - g.left) / g.width;
        const largeur = largeurAimantee(Math.min(1, Math.max(0, fraction)));
        if (largeur !== largeurDe(b)) { b.largeur = largeur; appliquerMiseEnPage(enveloppe, b); }
      };
      const fin = () => {
        poigneeLargeur.removeEventListener('pointermove', surMouvement);
        poigneeLargeur.removeEventListener('pointerup', fin);
        poigneeLargeur.removeEventListener('pointercancel', fin);
        enveloppe.classList.remove('editeur__cadre--redimension');
        if (largeurDe(b) !== depart) annoncer('Largeur : ' + libelleLargeur(largeurDe(b)).toLowerCase() + '.');
        appliquer({ index, poignee: 'largeur' });
      };
      poigneeLargeur.addEventListener('pointermove', surMouvement);
      poigneeLargeur.addEventListener('pointerup', fin);
      poigneeLargeur.addEventListener('pointercancel', fin);
    });

    /* Le déplacement, à la souris : le bloc survolé reçoit un repère
       d'insertion, au-dessus ou au-dessous selon la moitié survolée. */
    poigneeDeplacer.addEventListener('pointerdown', (evt) => {
      if (evt.button !== 0) return;
      evt.preventDefault();
      poigneeDeplacer.setPointerCapture(evt.pointerId);
      enveloppe.classList.add('editeur__cadre--saisi');
      const repere = el('div', { class: 'editeur__repere', 'aria-hidden': 'true', hidden: true });
      grille.append(repere);
      let cible = null;
      const surMouvement = (ev) => {
        const sous = document.elementFromPoint(ev.clientX, ev.clientY);
        const autre = sous && sous.closest ? sous.closest('.editeur__cadre') : null;
        if (!autre || autre === enveloppe || autre.parentNode !== grille) { cible = null; repere.hidden = true; return; }
        const r = autre.getBoundingClientRect();
        const g = grille.getBoundingClientRect();
        const apres = ev.clientY > r.top + r.height / 2;
        cible = { index: Number(autre.dataset.index), apres };
        repere.hidden = false;
        /* Des valeurs calculées, posées en ligne : le seul usage admis. */
        repere.style.setProperty('inset-block-start', ((apres ? r.bottom : r.top) - g.top) + 'px');
        repere.style.setProperty('inset-inline-start', (r.left - g.left) + 'px');
        repere.style.setProperty('inline-size', r.width + 'px');
      };
      const fin = () => {
        poigneeDeplacer.removeEventListener('pointermove', surMouvement);
        poigneeDeplacer.removeEventListener('pointerup', fin);
        poigneeDeplacer.removeEventListener('pointercancel', fin);
        enveloppe.classList.remove('editeur__cadre--saisi');
        repere.remove();
        if (!cible) return;
        const vers = deplacerBloc(etat, index, cible.index, cible.apres);
        if (vers !== index) annoncer('Bloc déplacé en position ' + (vers + 1) + '.');
        appliquer({ index: vers, poignee: 'deplacer' });
      };
      poigneeDeplacer.addEventListener('pointermove', surMouvement);
      poigneeDeplacer.addEventListener('pointerup', fin);
      poigneeDeplacer.addEventListener('pointercancel', fin);
    });
  });
}

function barreAjout(etat, appliquer) {
  return el('div', { class: 'editeur__ajout', role: 'group', 'aria-label': 'Ajouter un bloc' },
    el('span', { class: 'editeur__ajout-libelle' }, 'Ajouter'),
    Object.entries(TYPES_BLOC).map(([type, libelle]) => el('button', {
      type: 'button', class: 'bouton bouton--secondaire bouton--compact',
      onClick: () => { etat.blocs.push(blocVide(type)); appliquer(null, etat.blocs.length - 1); }
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
  /* Un brouillon par page d'où l'on écrit. Le pôle est alors toujours celui
     de la page — un début de communication commencé sur le tableau de bord
     ne repart plus sous l'étiquette d'un pôle, et l'inverse non plus — et on
     ne retrouve plus par surprise le début d'une autre communication. */
  const CLE = CLE_BROUILLON + ':' + (POLES.some(([c]) => c === opts.pole) ? opts.pole : 'ETII');
  const brouillon = stockage.lire(CLE, null);
  const etat = (brouillon && typeof brouillon === 'object' && Array.isArray(brouillon.blocs))
    ? Object.assign(brouillonVide(opts.pole), brouillon)
    : brouillonVide(opts.pole);
  if (!etat.blocs.length) etat.blocs = [blocVide('texte')];

  const zoneFormulaire = el('div', { class: 'editeur__formulaire' });
  const zoneApercu = el('div', { class: 'editeur__apercu-zone', 'aria-live': 'polite' });
  const zoneErreurs = el('ul', { class: 'editeur__erreurs', hidden: true, tabindex: '-1' });
  const zoneStockage = el('p', { class: 'editeur__erreurs', hidden: true, role: 'status' },
    'Ce navigateur n’enregistre pas les brouillons. Ne fermez pas cette fenêtre avant d’avoir publié.');
  const zoneLocaux = el('div', { class: 'editeur__locaux' });
  let modale = null;

  /* stockage.ecrire rend false quand le navigateur refuse d'écrire (quota
     plein en cours de rédaction, cookies bloqués) : sans ce retour, vingt
     minutes de rédaction disparaissent sans un mot. L'avertissement est en
     ligne et non en toast, parce qu'il doit tenir toute la rédaction. */
  function noterEcriture(ok) { if (!ok) zoneStockage.hidden = false; }

  function objetApercu() {
    const com = communicationPubliable(etat);
    if (etat.type === 'alerte') return { motDuChef: null, alertes: [texte(etat.titre) || 'Texte de l’alerte…'], annonces: [], agenda: [] };
    if (!texte(com.titre)) com.titre = 'Titre à écrire';
    if (etat.type === 'mot') return { motDuChef: com, alertes: [], annonces: [], agenda: [] };
    return { motDuChef: null, alertes: [], annonces: [com], agenda: [] };
  }

  /* La poignée qui a le clavier dans l'aperçu, pour la retrouver après
     une reconstruction : { index, poignee }. */
  function focusApercu() {
    const actif = document.activeElement;
    if (!actif || !zoneApercu.contains(actif) || !actif.dataset || !actif.dataset.poignee) return null;
    const cadre = actif.closest('.editeur__cadre');
    return cadre ? { index: Number(cadre.dataset.index), poignee: actif.dataset.poignee } : null;
  }

  function rendreApercu(focus) {
    const aRetrouver = focus || focusApercu();
    const objet = objetApercu();
    if (etat.type === 'alerte') { monter(zoneApercu, apercuAlertes(objet.alertes)); return; }
    const dossier = dossiersDepuisCommunications(objet, { pole: 'ETII' })[0];
    monter(zoneApercu, dossier ? apercuLecture(dossier) : null);
    poserCadres(zoneApercu, etat, appliquer);
    if (aRetrouver) {
      const poignee = zoneApercu.querySelector('.editeur__cadre[data-index="' + aRetrouver.index + '"] [data-poignee="' + aRetrouver.poignee + '"]');
      if (poignee) poignee.focus();
    }
  }

  function rendreErreurs() {
    const erreurs = valider(etat);
    monter(zoneErreurs, erreurs.map((e) => el('li', {}, e)));
    zoneErreurs.hidden = !erreurs.length;
    return erreurs;
  }

  const surChangement = debounce(() => {
    noterEcriture(stockage.ecrire(CLE, etat));
    rendreApercu();
    if (!zoneErreurs.hidden) rendreErreurs();
  }, 120);

  /* Un geste de structure (ordre, largeur, côté, ajout, retrait) : tout se
     reconstruit tout de suite, formulaire et aperçu, depuis le même état.
     `focus` retrouve une poignée de l'aperçu ; `cible` désigne ce qu'il faut
     retrouver dans le formulaire — un sélecteur de contrôle, ou l'indice
     d'une carte à amener à l'écran. */
  function appliquer(focus, cible) {
    surChangement.annuler();
    noterEcriture(stockage.ecrire(CLE, etat));
    rendreFormulaire(cible);
    rendreApercu(focus);
    if (!zoneErreurs.hidden) rendreErreurs();
  }

  function rendreLocaux() {
    const l = communicationsLocales();
    const entrees = [];
    if (l.motDuChef) entrees.push({ id: 'mot-du-chef', libelle: 'Édito : ' + texte(l.motDuChef.titre) });
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

  function rendreFormulaire(cible) {
    const estAlerte = etat.type === 'alerte';
    const estMot = etat.type === 'mot';
    const types = el('div', { class: 'editeur__types', role: 'radiogroup', 'aria-label': 'Type de communication' },
      TYPES.map((t) => {
        const id = idChamp();
        const radio = el('input', { type: 'radio', name: 'editeur-type', id, value: t.cle, checked: etat.type === t.cle ? true : null });
        radio.addEventListener('change', () => { if (radio.checked) { etat.type = t.cle;
          rendreFormulaire('input[name="editeur-type"][value="' + t.cle + '"]'); surChangement(); } });
        return el('label', { class: 'editeur__type', for: id }, radio,
          el('span', { class: 'editeur__type-libelle' }, t.libelle),
          el('span', { class: 'editeur__type-aide' }, t.aide));
      }));

    /* Le formulaire est un sous-arbre du conteneur qui défile : le remplacer
       remet ce conteneur en haut. On note où l'on était, on y revient après
       (le rAF rattrape le recalcul de mise en page), sinon chaque geste
       éjecte l'auteur hors de l'écran — à l'écran, cliquer ne fait rien. */
    const corps = zoneFormulaire.closest('.modale__corps');
    const y = corps ? corps.scrollTop : 0;

    monter(zoneFormulaire,
      types,
      estAlerte
        ? champ('Texte de l’alerte', entree(etat, 'titre', { placeholder: 'Maintenance de la plateforme documentaire mercredi soir.' }, surChangement),
            'Une phrase courte. Le bandeau en fait défiler plusieurs.')
        : frag(
          el('div', { class: 'editeur__rangee' },
            /* Le sélecteur grise les jours à venir ; la borne ne suffit pas
               seule, on peut taper une valeur hors borne — d'où le contrôle
               de valider() en plus. */
            champ('Date', entree(etat, 'date', { type: 'date', max: aujourdhui() }, surChangement)),
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
          el('p', { class: 'champ__aide sans-marge' }, 'Dans l’aperçu, chaque bloc a ses poignées : glissez-le entre les autres, tirez son bord pour le rétrécir ou l’élargir, calez-le à gauche ou à droite. Les mêmes réglages sont ici, sur chaque carte.'),
          el('div', { class: 'editeur__blocs' }, etat.blocs.map((_b, i) => carteBloc(etat, i, surChangement, rendreFormulaire, appliquer))),
          barreAjout(etat, appliquer)));

    /* Un bloc qui vient d'être ajouté naît en bas du formulaire, souvent très
       loin sous la ligne de flottaison : on l'amène à l'écran au lieu de
       revenir où l'on était. Les deux gestes ne doivent pas se battre. */
    const carte = typeof cible === 'number' ? zoneFormulaire.querySelectorAll('.editeur__bloc')[cible] : null;
    if (carte) carte.scrollIntoView({ block: 'nearest', behavior: 'auto' });
    else if (corps) { corps.scrollTop = y; requestAnimationFrame(() => { corps.scrollTop = y; }); }
    /* Après la restauration du défilement, jamais avant : un focus()
       programmatique refait défiler tout seul. */
    const aRetrouver = carte ? carte.querySelector('.champ__controle')
      : (typeof cible === 'string' ? zoneFormulaire.querySelector(cible) : null);
    if (aRetrouver) aRetrouver.focus();
  }

  async function publier() {
    const erreurs = rendreErreurs();
    if (erreurs.length) {
      toast('Complétez ce qui est signalé avant de publier.', 'alerte');
      /* La liste des raisons est sous un formulaire long : sans ça, un refus
         de publication ne se voit pas depuis le pied de la fenêtre. */
      zoneErreurs.scrollIntoView({ block: 'nearest', behavior: 'auto' });
      zoneErreurs.focus();
      annoncer(erreurs.length + ' point' + (erreurs.length > 1 ? 's' : '') + ' à compléter avant de publier.');
      return false;
    }
    const com = communicationPubliable(etat);
    /* L'identifiant retenu dans l'état : un second envoi — après un échec
       réseau, ou pour corriger une coquille — porte le même, donc il
       remplace la ligne au lieu d'en ajouter une seconde. */
    etat.id = com.id;
    const corrige = etat.publiee === true;
    try {
      const retour = await publierCommunication(etat.type, etat.type === 'alerte' ? texte(etat.titre) : com);
      if (!retour.ok) { toast(retour.message, 'erreur'); return false; }
      /* En mode branché, la feuille est à jour mais la page affichée ne l'est
         pas : le message le dit, au lieu de le laisser croire. */
      toast(corrige && retour.ou === 'feuille'
        ? 'Corrigée dans la feuille. Rechargez pour la voir à jour.'
        : retour.message, 'succes');
      annoncer(corrige ? 'Communication corrigée.' : 'Communication publiée.');
      /* Le brouillon n'est plus jeté : il devient la communication qu'on peut
         corriger dix secondes plus tard, sans rien retaper. */
      etat.publiee = true;
      noterEcriture(stockage.ecrire(CLE, etat));
      if (typeof opts.surPublication === 'function') opts.surPublication();
      return true;
    } catch (e) {
      toast('Publication impossible : ' + (e && e.message ? e.message : 'erreur réseau') + '. Le brouillon est conservé.', 'erreur');
      return false;
    }
  }

  /* Une communication déjà partie se corrige dans la même fenêtre : le titre
     et les deux libellés disent lequel des deux gestes on est en train de
     faire, et « Nouvelle communication » repasse de l'un à l'autre sans
     refermer la fenêtre. */
  function titreModale() { return etat.publiee ? 'Corriger la dernière communication' : 'Ajouter une communication'; }

  /* Repartir de zéro : le même geste que « Vider », mais son nom dit alors
     ce qu'il fait vraiment — quitter la correction pour une communication
     neuve, avec un identifiant neuf. */
  const boutonRepartir = el('button', { type: 'button', class: 'bouton bouton--discret', onClick: () => {
    Object.assign(etat, brouillonVide(opts.pole)); stockage.supprimer(CLE);
    rendreFormulaire(); rendreApercu(); zoneErreurs.hidden = true; majMode();
  } }, 'Vider');
  const boutonPublier = el('button', { type: 'button', class: 'bouton bouton--principal', onClick: () => {
    publier().then((ok) => { if (ok && modale) modale.fermer('publie'); });
  } }, 'Publier');

  function majMode() {
    const h = modale && modale.boite ? modale.boite.querySelector('.modale__titre') : null;
    if (h) h.textContent = titreModale();
    boutonRepartir.textContent = etat.publiee ? 'Nouvelle communication' : 'Vider';
    boutonPublier.textContent = etat.publiee ? 'Republier' : 'Publier';
  }

  modale = ouvrirModale({
    titre: titreModale(),
    classe: 'modale--editeur',
    /* Un clic à côté d'une fenêtre de rédaction ne la ferme pas ; Échap
       reste, lui est volontaire. */
    fermetureFond: false,
    declencheur: opts.declencheur || null,
    contenu: () => el('div', { class: 'editeur' },
      el('div', { class: 'editeur__colonne' },
        el('p', { class: 'editeur__intro' },
          texte(SOURCE.publication)
            ? 'Ce que vous publiez est ajouté à la feuille de publication : tout le monde le voit à la prochaine ouverture.'
            : 'La publication n’est pas encore branchée : ce que vous publiez reste dans ce navigateur, marqué « brouillon ». ',
          texte(SOURCE.publication) ? null : el('a', { href: 'docs/COMMUNICATIONS-GOOGLE-SHEETS.md' }, 'Comment brancher la publication')),
        /* Le retrait n'a aucun chemin dans le site : le dire, plutôt que de
           laisser chercher un bouton qui n'existe pas. */
        texte(SOURCE.publication)
          ? el('p', { class: 'editeur__intro' }, 'Pour retirer une communication déjà partie, supprimez sa ligne dans la feuille.')
          : null,
        /* Avant le formulaire, pas après : c'est une consigne qui doit tenir
           toute la rédaction, elle ne sert à rien en bas d'une page longue. */
        zoneStockage,
        zoneFormulaire,
        zoneErreurs,
        zoneLocaux),
      el('div', { class: 'editeur__colonne editeur__colonne--apercu' },
        el('p', { class: 'editeur__apercu-titre' }, 'Aperçu'),
        zoneApercu)),
    actions: [
      boutonRepartir,
      { libelle: 'Fermer', variante: 'secondaire', ferme: true },
      boutonPublier
    ]
  });

  rendreFormulaire();
  rendreApercu();
  rendreLocaux();
  majMode();
  return modale;
}

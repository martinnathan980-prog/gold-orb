/* =========================================================================
   ETII Hub — Publier une communication (admin.html)

   La « partie administrateur » d'un site statique : pas de compte, pas de
   serveur. Le chef remplit le formulaire, voit à droite la communication
   exactement comme le site la rendra, puis :
     - copie la LIGNE à coller dans la feuille Google de publication (le
       site la lit à l'ouverture, voir docs/COMMUNICATIONS-GOOGLE-SHEETS.md) ;
     - ou copie le JSON / télécharge communications.json mis à jour, pour
       un site qui lit encore le fichier.
   Le brouillon est gardé dans ce navigateur. Rien n'est envoyé nulle part.

   L'aperçu passe par la même analyse que la feuille (annonceDepuisLigne) :
   ce qu'on voit ici est ce que la feuille donnera, sans exception.
   ========================================================================= */

import { el, frag, monter, initTheme, initNav, stockage, toast, copierTexte, debounce, annoncer } from './ui.js';
import { chargerDonnees } from './data.js';
import { kiosque, dossiersDepuisCommunications } from './kiosque.js';
import { annonceDepuisLigne, ligneDepuisAnnonce, analyserSerie, analyserChiffres, COLONNES } from './communications.js';

const CLE_BROUILLON = 'admin.communication';

const TYPES = [
  { cle: 'annonce', libelle: 'Annonce', aide: 'Une nouvelle du service ou d’un pôle : elle rejoint la liste des communications.' },
  { cle: 'mot', libelle: 'Mot du chef', aide: 'Le message de la direction : il s’affiche en premier, avec ses chiffres et sa courbe.' },
  { cle: 'alerte', libelle: 'Alerte', aide: 'Une phrase courte pour le bandeau qui défile en haut du Communication Center.' }
];
const POLES = [['ETII', 'Tout le service'], ['ETIIA', 'ETIIA'], ['ETIIE', 'ETIIE'], ['ETIII', 'ETIII']];
const STATUTS = [['info', 'Information'], ['succes', 'Validé'], ['urgent', 'Urgent']];
const TENDANCES = [['', '—'], ['hausse', 'En hausse ↗'], ['baisse', 'En baisse ↘'], ['stable', 'Stable →']];

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

function aujourdhui() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function brouillonVide() {
  return {
    type: 'annonce', id: '', date: aujourdhui(), pole: 'ETII', categorie: '', statut: 'info',
    titre: '', resume: '', corps: '', image: '', imageAlt: '', imageLegende: '',
    chiffres: [{}, {}, {}, {}].map(() => ({ libelle: '', valeur: '', unite: '', tendance: '' })),
    serie: '', auteur: '', fonction: ''
  };
}

/* -------------------------------------------------------------------------
   1. État
   ------------------------------------------------------------------------- */

let etat = brouillonVide();
/* Les champs déjà touchés : une erreur ne s'affiche que sur un champ que
   l'on a commencé à remplir — ou partout, après une tentative d'export. */
let touches = new Set();
let toutMontrer = false;
const refs = {};

function chargerBrouillon() {
  const b = stockage.lire(CLE_BROUILLON, null);
  if (!b || typeof b !== 'object') return;
  const propre = brouillonVide();
  for (const cle of Object.keys(propre)) {
    if (cle === 'chiffres') {
      if (Array.isArray(b.chiffres)) propre.chiffres = propre.chiffres.map((c, i) => Object.assign(c, b.chiffres[i] && typeof b.chiffres[i] === 'object' ? b.chiffres[i] : {}));
    } else if (typeof b[cle] === 'string') {
      propre[cle] = b[cle];
    }
  }
  etat = propre;
  for (const cle of Object.keys(propre)) if (typeof propre[cle] === 'string' && propre[cle] && cle !== 'date') touches.add(cle);
}

function enregistrerBrouillon() { stockage.ecrire(CLE_BROUILLON, etat); }

/* La ligne « feuille » équivalente à l'état : l'aperçu et les exports
   passent tous par elle — une seule vérité. */
function ligneDepuisEtat() {
  const chiffres = etat.chiffres
    .filter((c) => texte(c.libelle) && texte(c.valeur) !== '')
    .map((c) => [texte(c.libelle) + ' = ' + texte(c.valeur), texte(c.unite), texte(c.tendance)].filter(Boolean).join(' '))
    .join(' ; ');
  return {
    type: etat.type, id: texte(etat.id), date: texte(etat.date), pole: etat.type === 'mot' ? 'ETII' : etat.pole,
    categorie: texte(etat.categorie), statut: etat.statut, titre: texte(etat.titre), resume: texte(etat.resume),
    corps: etat.corps, image: texte(etat.image), imageAlt: texte(etat.imageAlt), imageLegende: texte(etat.imageLegende),
    chiffres, serie: texte(etat.serie), auteur: texte(etat.auteur), fonction: texte(etat.fonction)
  };
}

function annonceCourante() {
  return annonceDepuisLigne(ligneDepuisEtat(), 0);
}

/* -------------------------------------------------------------------------
   2. Validation : des messages sous les champs, jamais de fenêtre
   ------------------------------------------------------------------------- */

function valider() {
  const erreurs = {};
  if (etat.type !== 'alerte') {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(texte(etat.date)) || Number.isNaN(Date.parse(etat.date))) erreurs.date = 'Une date au format AAAA-MM-JJ.';
    if (!texte(etat.resume)) erreurs.resume = 'Le résumé s’affiche dans la liste : une ou deux phrases.';
  }
  if (!texte(etat.titre)) erreurs.titre = etat.type === 'alerte' ? 'Le texte de l’alerte.' : 'Le titre est obligatoire.';
  if (texte(etat.image) && !/^https:\/\/|^assets\//.test(texte(etat.image))) erreurs.image = 'Une URL https:// ou un chemin assets/… du site.';
  if (texte(etat.image) && !texte(etat.imageAlt)) erreurs.imageAlt = 'Décrivez l’image en quelques mots : c’est ce que lit un lecteur d’écran.';
  if (texte(etat.serie) && !analyserSerie(etat.serie)) erreurs.serie = 'Format : « Libellé (unité) | 2026-01 = 95,2 ; 2026-02 = 96 ».';
  etat.chiffres.forEach((c, i) => {
    if (texte(c.libelle) && texte(c.valeur) !== '' && !analyserChiffres(texte(c.libelle) + ' = ' + texte(c.valeur)).length) {
      erreurs['chiffre' + i] = 'La valeur doit être un nombre.';
    }
  });
  return erreurs;
}

function afficherErreurs(erreurs) {
  for (const [cle, noeud] of Object.entries(refs.erreurs)) {
    const message = (toutMontrer || touches.has(cle)) ? erreurs[cle] : '';
    noeud.textContent = message || '';
    noeud.hidden = !message;
    const controle = refs.controles[cle];
    if (controle) controle.setAttribute('aria-invalid', message ? 'true' : 'false');
  }
  const n = Object.keys(erreurs).length;
  refs.etatValidation.textContent = n === 0 ? 'Prête à publier.' : (n === 1 ? 'Un champ à compléter.' : n + ' champs à compléter.');
  refs.etatValidation.dataset.etat = n === 0 ? 'ok' : 'erreur';
}

/* Avant un export : s'il manque quelque chose, tout est montré et rien
   n'est copié — on ne colle pas une ligne incomplète dans la feuille. */
function pretePourExport() {
  const erreurs = valider();
  if (!Object.keys(erreurs).length) return true;
  toutMontrer = true;
  afficherErreurs(erreurs);
  const premier = Object.keys(erreurs)[0];
  if (refs.controles[premier]) refs.controles[premier].focus();
  toast('Complétez les champs signalés avant de publier.', 'alerte');
  return false;
}

/* -------------------------------------------------------------------------
   3. Le formulaire
   ------------------------------------------------------------------------- */

function champ(cle, libelle, controle, aide, options) {
  const opts = options || {};
  const id = 'admin-' + cle;
  controle.id = id;
  refs.controles[cle] = controle;
  const erreur = el('p', { class: 'champ__erreur', id: id + '-erreur', hidden: true, role: 'alert' });
  refs.erreurs[cle] = erreur;
  controle.setAttribute('aria-describedby', [aide ? id + '-aide' : '', id + '-erreur'].filter(Boolean).join(' '));
  return el('div', { class: ['champ', opts.classe || null], dataset: { champ: cle } },
    el('label', { class: 'champ__etiquette', for: id }, libelle,
      opts.requis ? el('span', { class: 'champ__requis', 'aria-hidden': 'true' }, ' *') : null),
    controle,
    aide ? el('p', { class: 'champ__aide', id: id + '-aide' }, aide) : null,
    erreur);
}

function entree(cle, attrs) {
  const n = el('input', Object.assign({ class: 'champ__controle', type: 'text', autocomplete: 'off' }, attrs || {}));
  n.value = etat[cle] || '';
  n.addEventListener('input', () => { etat[cle] = n.value; touches.add(cle); surChangement(); });
  return n;
}

function zone(cle, attrs) {
  const n = el('textarea', Object.assign({ class: 'champ__controle', rows: 4 }, attrs || {}));
  n.value = etat[cle] || '';
  n.addEventListener('input', () => { etat[cle] = n.value; touches.add(cle); surChangement(); });
  return n;
}

function selection(cle, paires) {
  const n = el('select', { class: 'champ__controle' },
    paires.map(([valeur, libelle]) => el('option', { value: valeur, selected: etat[cle] === valeur ? true : null }, libelle)));
  n.addEventListener('change', () => { etat[cle] = n.value; surChangement(); });
  return n;
}

function ligneChiffre(i) {
  const c = etat.chiffres[i];
  const lier = (champNom, noeud) => {
    noeud.value = c[champNom] || '';
    noeud.addEventListener(noeud.tagName === 'SELECT' ? 'change' : 'input', () => { c[champNom] = noeud.value; touches.add('chiffre' + i); surChangement(); });
    return noeud;
  };
  const libelle = lier('libelle', el('input', { class: 'champ__controle', type: 'text', placeholder: 'Libellé', 'aria-label': 'Libellé du chiffre ' + (i + 1) }));
  const valeur = lier('valeur', el('input', { class: 'champ__controle', type: 'text', inputmode: 'decimal', placeholder: 'Valeur', 'aria-label': 'Valeur du chiffre ' + (i + 1) }));
  const unite = lier('unite', el('input', { class: 'champ__controle', type: 'text', placeholder: 'Unité', 'aria-label': 'Unité du chiffre ' + (i + 1) }));
  const tendance = lier('tendance', el('select', { class: 'champ__controle', 'aria-label': 'Tendance du chiffre ' + (i + 1) },
    TENDANCES.map(([v, l]) => el('option', { value: v }, l))));
  refs.controles['chiffre' + i] = valeur;
  const erreur = el('p', { class: 'champ__erreur', hidden: true, role: 'alert' });
  refs.erreurs['chiffre' + i] = erreur;
  return el('div', { class: 'admin__chiffre' }, libelle, valeur, unite, tendance, erreur);
}

function construireFormulaire() {
  refs.controles = {}; refs.erreurs = {};

  const type = el('div', { class: 'admin__types', role: 'radiogroup', 'aria-label': 'Type de communication' },
    TYPES.map((t) => {
      const id = 'admin-type-' + t.cle;
      const radio = el('input', { type: 'radio', name: 'type', id, value: t.cle, checked: etat.type === t.cle ? true : null });
      radio.addEventListener('change', () => { if (radio.checked) { etat.type = t.cle; rendreFormulaire(); surChangement(); } });
      return el('label', { class: 'admin__type', for: id },
        radio,
        el('span', { class: 'admin__type-libelle' }, t.libelle),
        el('span', { class: 'admin__type-aide' }, t.aide));
    }));

  const estAlerte = etat.type === 'alerte';
  const estMot = etat.type === 'mot';

  const bloc = (titre, ...enfants) => el('fieldset', { class: 'admin__bloc' },
    el('legend', { class: 'admin__bloc-titre' }, titre), enfants);

  return el('form', { class: 'admin__formulaire', novalidate: true, onSubmit: (evt) => evt.preventDefault() },
    type,
    estAlerte
      ? bloc('L’alerte',
          champ('titre', 'Texte de l’alerte', entree('titre', { placeholder: 'Maintenance de la plateforme documentaire mercredi soir.' }),
            'Une phrase. Le bandeau en fait défiler plusieurs.', { requis: true }))
      : frag(
        bloc('L’essentiel',
          el('div', { class: 'admin__rangee' },
            champ('date', 'Date', entree('date', { type: 'date' }), null, { requis: true }),
            estMot ? null : champ('pole', 'Pôle', selection('pole', POLES)),
            estMot ? null : champ('statut', 'Statut', selection('statut', STATUTS))),
          champ('titre', 'Titre', entree('titre', { placeholder: estMot ? 'Un trimestre qui se tient' : 'Validation du jalon de définition' }), null, { requis: true }),
          champ('resume', 'Résumé', zone('resume', { rows: 2, placeholder: 'Une ou deux phrases : c’est ce qu’on lit dans la liste.' }),
            'Affiché dans la liste et en chapeau de la lecture.', { requis: true }),
          estMot ? null : champ('categorie', 'Catégorie', entree('categorie', { placeholder: 'H160, Outils, Transverse…' }), 'Un programme ou un thème, affiché en étiquette.'),
          estMot ? el('div', { class: 'admin__rangee' },
            champ('auteur', 'Auteur', entree('auteur', { placeholder: 'Personne 01' })),
            champ('fonction', 'Fonction', entree('fonction', { placeholder: 'Direction du service' }))) : null),
        bloc('Le texte',
          champ('corps', 'Corps', zone('corps', { rows: 8, placeholder: '-> Ce qui change\n• Nouvelle arborescence des espaces.\n• Les liens existants sont redirigés.\n\nV Aucune action requise après la bascule.\n! Sauvegardez vos travaux avant 19h30.' }),
            'Une ligne par idée. Préfixes : « -> » titre, « • » ou « - » puce, « V » validé, « ! » alerte ; une ligne vide aère.')),
        bloc('L’image',
          champ('image', 'Adresse de l’image', entree('image', { type: 'url', placeholder: 'https://… ou assets/img/communications/…' }),
            'Une image publique (Drive partagé « toute personne avec le lien », en lien direct) ou un fichier du site.'),
          el('div', { class: 'admin__rangee' },
            champ('imageAlt', 'Description', entree('imageAlt', { placeholder: 'Un H160 sur un salon' }), 'Pour les lecteurs d’écran.'),
            champ('imageLegende', 'Légende', entree('imageLegende', { placeholder: 'Le H160 — programme phare du trimestre' })))),
        bloc('Les chiffres clés',
          el('p', { class: 'champ__aide sans-marge' }, 'Jusqu’à quatre tuiles : un libellé, une valeur, une unité, une tendance.'),
          el('div', { class: 'admin__chiffres' }, [0, 1, 2, 3].map(ligneChiffre))),
        bloc('La courbe',
          champ('serie', 'Série mensuelle', zone('serie', { rows: 2, placeholder: 'OTQ mensuel (%) | 2026-04 = 92,1 ; 2026-05 = 92,8 ; 2026-06 = 93,6' }),
            'Un libellé, son unité entre parenthèses, puis « mois = valeur » séparés par des points-virgules.')),
        bloc('Identifiant',
          champ('id', 'Identifiant', entree('id', { placeholder: 'Laissez vide : il sera fabriqué à partir de la date.' }),
            'Utile seulement pour remplacer une communication existante : reprenez son identifiant.'))));
}

function rendreFormulaire() {
  monter(refs.zoneFormulaire, construireFormulaire());
}

/* -------------------------------------------------------------------------
   4. L'aperçu et les exports
   ------------------------------------------------------------------------- */

function objetApercu() {
  const annonce = annonceCourante();
  const objet = { motDuChef: null, alertes: [], annonces: [], agenda: [] };
  if (etat.type === 'alerte') {
    objet.alertes = [texte(etat.titre) || 'Texte de l’alerte…'];
    return objet;
  }
  const a = annonce || { id: 'brouillon', date: texte(etat.date) || aujourdhui(), pole: etat.pole, categorie: texte(etat.categorie),
    statut: etat.statut, titre: texte(etat.titre) || 'Titre à écrire', resume: texte(etat.resume), corps: [] };
  if (etat.type === 'mot') objet.motDuChef = Object.assign({ auteur: texte(etat.auteur), fonction: texte(etat.fonction) }, a);
  else objet.annonces = [a];
  return objet;
}

function rendreApercu() {
  const objet = objetApercu();
  monter(refs.zoneApercu,
    kiosque({ id: 'apercu', dossiers: dossiersDepuisCommunications(objet, { pole: 'ETII' }), alertes: objet.alertes, titreFil: 'Aperçu' }));
}

function copierLigne() {
  if (!pretePourExport()) return;
  const annonce = annonceCourante();
  const ligne = etat.type === 'alerte'
    ? ligneDepuisAnnonce({ titre: texte(etat.titre) }, 'alerte')
    : ligneDepuisAnnonce(Object.assign({ auteur: texte(etat.auteur), fonction: texte(etat.fonction) }, annonce), etat.type);
  Promise.resolve(copierTexte(ligne)).then((ok) => {
    toast(ok === false ? 'Copie impossible dans ce navigateur.' : 'Ligne copiée : collez-la dans la feuille de publication.', ok === false ? 'erreur' : 'succes');
  });
}

function copierJson() {
  if (!pretePourExport()) return;
  const annonce = annonceCourante();
  const valeur = etat.type === 'alerte' ? texte(etat.titre)
    : (etat.type === 'mot' ? Object.assign({ auteur: texte(etat.auteur), fonction: texte(etat.fonction) }, annonce) : annonce);
  Promise.resolve(copierTexte(JSON.stringify(valeur, null, 2))).then((ok) => {
    toast(ok === false ? 'Copie impossible dans ce navigateur.' : 'JSON copié.', ok === false ? 'erreur' : 'succes');
  });
}

async function telechargerFichier() {
  if (!pretePourExport()) return;
  let actuel;
  try { actuel = await chargerDonnees('communications'); }
  catch (_e) { actuel = { motDuChef: null, alertes: [], annonces: [], agenda: [] }; }
  const copie = JSON.parse(JSON.stringify(actuel));
  const annonce = annonceCourante();
  if (etat.type === 'alerte') {
    copie.alertes = (Array.isArray(copie.alertes) ? copie.alertes : []).concat([texte(etat.titre)]);
  } else if (etat.type === 'mot') {
    copie.motDuChef = Object.assign({ auteur: texte(etat.auteur), fonction: texte(etat.fonction) }, annonce);
  } else {
    copie.annonces = (Array.isArray(copie.annonces) ? copie.annonces : []).filter((a) => a && a.id !== annonce.id);
    copie.annonces.unshift(annonce);
    copie.annonces.sort((a, b) => texte(b.date).localeCompare(texte(a.date)));
  }
  const blob = new Blob([JSON.stringify(copie, null, 2) + '\n'], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const lien = el('a', { href: url, download: 'communications.json' });
  document.body.append(lien); lien.click(); lien.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast('communications.json téléchargé : remplacez assets/data/communications.json par ce fichier.', 'succes');
}

function vider() {
  etat = brouillonVide();
  touches = new Set();
  toutMontrer = false;
  stockage.supprimer(CLE_BROUILLON);
  rendreFormulaire();
  surChangement();
  annoncer('Formulaire vidé.');
}

const surChangement = debounce(() => {
  enregistrerBrouillon();
  afficherErreurs(valider());
  rendreApercu();
}, 120);

/* -------------------------------------------------------------------------
   5. La page
   ------------------------------------------------------------------------- */

function construire(cible) {
  refs.zoneFormulaire = el('div', { class: 'admin__colonne-formulaire' });
  refs.zoneApercu = el('div', { class: 'admin__apercu-zone' });
  refs.etatValidation = el('p', { class: 'admin__validation sans-marge', 'aria-live': 'polite' }, '');

  const bouton = (libelle, variante, onClick) => el('button', { type: 'button', class: ['bouton', 'bouton--' + variante], onClick }, libelle);
  refs.boutonsExport = [
    bouton('Copier la ligne pour la feuille Google', 'principal', copierLigne),
    bouton('Copier le JSON', 'secondaire', copierJson),
    bouton('Télécharger communications.json', 'secondaire', telechargerFichier)
  ];

  monter(cible,
    el('p', { class: 'admin__intro mesure' },
      'Cette page ne publie rien : elle prépare la communication, la montre telle que le site la rendra, ',
      'et vous donne la ligne à coller dans la feuille de publication — le site la lit à l’ouverture. ',
      'Le brouillon reste dans ce navigateur. ',
      el('a', { href: 'docs/COMMUNICATIONS-GOOGLE-SHEETS.md' }, 'Comment ça marche')),
    el('div', { class: 'admin' },
      el('div', { class: 'admin__colonne' },
        refs.zoneFormulaire,
        el('div', { class: 'admin__actions' },
          refs.etatValidation,
          el('div', { class: 'rangee' }, refs.boutonsExport),
          el('div', { class: 'rangee' }, bouton('Vider le formulaire', 'discret', vider))),
        el('details', { class: 'admin__colonnes' },
          el('summary', {}, 'Les colonnes de la feuille'),
          el('p', { class: 'texte-doux texte-sm' }, 'L’en-tête de la feuille doit porter ces noms (l’ordre n’a pas d’importance) : ',
            el('code', { class: 'mono' }, COLONNES.join(' · '))))),
      el('div', { class: 'admin__colonne admin__colonne--apercu' },
        el('h2', { class: 'admin__apercu-titre' }, 'Aperçu'),
        refs.zoneApercu)));

  rendreFormulaire();
  afficherErreurs(valider());
  rendreApercu();
}

/* -------------------------------------------------------------------------
   6. Démarrage
   ------------------------------------------------------------------------- */

initTheme();
initNav('admin.html');
chargerBrouillon();
construire(document.getElementById('zone-admin'));

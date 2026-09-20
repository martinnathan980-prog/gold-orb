/* =========================================================================
   ETII Hub — Espace de pôle (etiia.html, etiie.html, etiii.html)

   Une seule page, trois fois, paramétrée par <body data-pole="…">. Quatre
   sections, celles de l'accord d'équipe et de l'outil d'origine :
     1. COMMUNICATION — le kiosque du pôle (kiosque.js) ;
     2. RÉUNIONS      — comptes-rendus et prochains points, liste + lecteur ;
     3. ORGANIGRAMME  — l'arbre d'équipe du pôle (arbre.js) ;
     4. FAQ           — la base de connaissances du pôle, liste + lecteur,
                        et la demande aux experts.

   Rien n'est inventé : chaque section ne montre que ce que le fichier
   déclare pour ce pôle. Tout le DOM est construit avec el().
   ========================================================================= */

import { el, frag, monter, initTheme, initNav, ouvrirModale, stockage, toast, annoncer } from './ui.js';
import { chargerDonnees, avecEtat, verifierForme } from './data.js';
import { kiosque, dossiersDepuisCommunications, dateLongue } from './kiosque.js';
import { lecteur } from './lecteur.js';
import { arbreEquipe } from './arbre.js';

/* -------------------------------------------------------------------------
   1. Les pôles : matière éditoriale, pas de la donnée
   ------------------------------------------------------------------------- */

const POLES = {
  ETIIA: {
    cle: 'ETIIA',
    metaphore: 'Squelette & ADN',
    description: 'Logique et règles d’architecture : découpage fonctionnel, '
      + 'conventions de nommage et principes que tous les autres travaux '
      + 'appliquent ensuite.'
  },
  ETIIE: {
    cle: 'ETIIE',
    metaphore: 'Système nerveux',
    description: 'Schémas électriques et communication entre systèmes : '
      + 'signaux, interfaces et cohérence des échanges d’un bout à l’autre '
      + 'de la définition.'
  },
  ETIII: {
    cle: 'ETIII',
    metaphore: 'Structure & harnais',
    description: 'Intégration physique et routage dans la maquette '
      + 'numérique : cheminements, fixations et vérification des '
      + 'interférences avant fabrication.'
  }
};

const CLE_STOCKAGE_FAQ = 'faq-questions';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

function lienPole(page, code, extra) {
  let hash = 'pole=' + encodeURIComponent(code);
  if (extra && typeof extra === 'object') {
    for (const cle of Object.keys(extra)) {
      const valeur = extra[cle];
      if (valeur === null || valeur === undefined || valeur === '') continue;
      hash += '&' + encodeURIComponent(cle) + '=' + encodeURIComponent(String(valeur));
    }
  }
  return page + '#' + hash;
}

function lienSuite(page, code, libelle, extra) {
  return el('a', { class: 'bouton bouton--secondaire bouton--compact', href: lienPole(page, code, extra) }, libelle);
}

/* -------------------------------------------------------------------------
   2. Communication
   ------------------------------------------------------------------------- */

function rendreCommunication(pole, donnees, conteneur) {
  verifierForme(donnees, { agenda: 'tableau' }, 'communications.json');
  const dossiers = dossiersDepuisCommunications(donnees, { pole: pole.cle });
  /* Tout ce que le pôle publie est déjà dans ce kiosque : il n'y a pas
     d'ailleurs où renvoyer. Le niveau service est sur le tableau de bord. */
  monter(conteneur,
    kiosque({ id: 'kiosque-' + pole.cle.toLowerCase(), dossiers, titreFil: 'Fil du pôle ' + pole.cle }));
}

/* -------------------------------------------------------------------------
   3. Réunions
   ------------------------------------------------------------------------- */

function reunionsDuPole(donnees, code) {
  verifierForme(donnees, { comptesRendus: 'tableau', prochainsPoints: 'tableau' }, 'reunions.json');
  const du = (liste) => (Array.isArray(liste) ? liste : [])
    .filter((r) => r && typeof r === 'object' && texte(r.pole).toUpperCase() === code);
  return {
    comptesRendus: du(donnees.comptesRendus).sort((a, b) => texte(b.date).localeCompare(texte(a.date))),
    prochainsPoints: du(donnees.prochainsPoints).sort((a, b) => texte(a.date).localeCompare(texte(b.date)))
  };
}

function blocListe(titre, classe, entrees, ordonne) {
  const liste = (Array.isArray(entrees) ? entrees : []).map(texte).filter(Boolean);
  if (!liste.length) return null;
  return el('div', { class: ['liseuse__bloc', classe] },
    el('p', { class: 'liseuse__bloc-titre' }, titre, el('span', { class: 'mono' }, String(liste.length))),
    el(ordonne ? 'ol' : 'ul', {}, liste.map((t) => el('li', {}, t))));
}

function corpsReunion(r) {
  const sujets = (Array.isArray(r.sujets) ? r.sujets : []).filter((s) => s && typeof s === 'object');
  return frag(
    texte(r.synthese) ? el('div', {}, el('h4', {}, 'Synthèse'), el('p', {}, texte(r.synthese))) : null,
    texte(r.objectif) ? el('div', {}, el('h4', {}, 'Objectif'), el('p', {}, texte(r.objectif))) : null,
    sujets.length
      ? el('div', {}, el('h4', {}, 'Sujets abordés'),
          el('div', { class: 'liseuse__sujets' }, sujets.map((s) => el('div', { class: 'liseuse__sujet' },
            el('p', { class: 'gras' }, texte(s.titre) || 'Sujet'),
            texte(s.notes) ? el('p', { class: 'liseuse__sujet-notes' }, texte(s.notes)) : null))))
      : null,
    blocListe('Actions', 'liseuse__bloc--actions', r.actions, true),
    blocListe('Décisions', 'liseuse__bloc--decisions', r.decisions, true));
}

function rendreReunions(pole, groupes, conteneur) {
  const elements = groupes.comptesRendus.map((r) => ({
    id: 'cr-' + texte(r.id), groupe: 'cr', titre: texte(r.titre), meta: dateLongue(r.date) || 'Date à renseigner',
    badges: [{ texte: 'Compte-rendu', classe: 'badge--neutre' }],
    recherche: [r.synthese, r.lieu].concat((r.sujets || []).map((s) => (s && s.titre) + ' ' + (s && s.notes)), r.actions || [], r.decisions || []).map(texte),
    source: r, corps: () => corpsReunion(r)
  })).concat(groupes.prochainsPoints.map((r) => ({
    id: 'pp-' + texte(r.id), groupe: 'pp', titre: texte(r.titre), meta: dateLongue(r.date) || 'Date à renseigner',
    badges: [{ texte: 'À venir', classe: 'badge--accent' }],
    recherche: [r.objectif, r.lieu].concat((r.sujets || []).map((s) => (s && s.titre) + ' ' + (s && s.notes)), r.actions || []).map(texte),
    source: r, corps: () => corpsReunion(r)
  })));

  monter(conteneur,
    lecteur({
      id: 'reunions-' + pole.cle.toLowerCase(),
      elements,
      groupes: [{ cle: 'pp', titre: 'Prochains points' }, { cle: 'cr', titre: 'Comptes-rendus' }],
      titreListe: 'Réunions du pôle',
      placeholder: 'Rechercher un compte-rendu, un sujet, une action…',
      vide: 'Aucune réunion publiée pour ce pôle.',
      entete: (item) => frag(
        el('span', { class: ['badge', item.groupe === 'pp' ? 'badge--accent' : 'badge--neutre'] },
          item.groupe === 'pp' ? 'Prochain point' : 'Compte-rendu'),
        el('time', { class: 'mono texte-xs texte-faible', datetime: texte(item.source.date) },
          (dateLongue(item.source.date) || 'Date à renseigner').toUpperCase()),
        texte(item.source.lieu) ? el('span', { class: 'badge badge--contour' }, texte(item.source.lieu)) : null),
      actions: (item) => {
        const sujet = encodeURIComponent((item.groupe === 'pp' ? 'Prochain point : ' : 'Compte-rendu : ') + item.titre);
        const corps = encodeURIComponent('Bonjour,\n\n' + item.titre + ' — ' + (dateLongue(item.source.date) || '')
          + '\n\n(Détails sur le Hub ETII, espace ' + pole.cle + '.)\n\nCordialement.');
        return frag(
          el('a', { class: 'bouton bouton--discret bouton--compact', href: 'mailto:?subject=' + sujet + '&body=' + corps }, 'Partager'),
          el('a', { class: 'bouton bouton--secondaire bouton--compact', href: lienPole('reunions.html', pole.cle) }, 'Ouvrir dans le hub réunions'));
      }
    }));
}

/* -------------------------------------------------------------------------
   4. Organigramme
   ------------------------------------------------------------------------- */

function blocOrganigramme(donnees, code) {
  verifierForme(donnees, { poles: 'tableau' }, 'organigramme.json');
  return donnees.poles.find((e) => e && typeof e === 'object' && texte(e.pole).toUpperCase() === code) || null;
}

function rendreOrganigramme(pole, bloc, conteneur) {
  monter(conteneur,
    arbreEquipe(bloc, { id: 'arbre-' + pole.cle.toLowerCase() }),
    el('p', { class: 'rangee rangee--fin sans-marge' },
      lienSuite('organigramme.html', pole.cle, 'L’organigramme complet du service')));
}

/* -------------------------------------------------------------------------
   5. FAQ
   ------------------------------------------------------------------------- */

function questionsDuPole(donnees, code) {
  verifierForme(donnees, { questions: 'tableau' }, 'faq.json');
  const toutes = donnees.questions.filter((q) => q && typeof q === 'object' && texte(q.question));
  return {
    pole: toutes.filter((q) => texte(q.pole).toUpperCase() === code),
    service: toutes.filter((q) => texte(q.pole).toUpperCase() === 'ETII')
  };
}

function enregistrerDemande(question, contexte, pole) {
  const brut = stockage.lire(CLE_STOCKAGE_FAQ, []);
  const liste = Array.isArray(brut) ? brut : [];
  liste.unshift({
    id: 'q-' + Date.now(),
    question, contexte: contexte || null, pole, date: new Date().toISOString()
  });
  return stockage.ecrire(CLE_STOCKAGE_FAQ, liste);
}

function ouvrirDemandeExpert(pole, declencheur, texteInitial) {
  let champ = null; let contexte = null; let erreur = null;
  ouvrirModale({
    titre: 'Interroger un expert du pôle ' + pole.cle,
    classe: 'modale--etroite',
    declencheur: declencheur || null,
    contenu: () => {
      erreur = el('p', { class: 'champ__erreur', hidden: true }, 'Écrivez votre question avant d’envoyer.');
      champ = el('textarea', { class: 'champ__controle', id: 'demande-question', rows: 5,
        placeholder: 'Programme, jalon, problématique technique…' });
      champ.value = texte(texteInitial);
      contexte = el('input', { class: 'champ__controle', id: 'demande-contexte', type: 'text',
        placeholder: 'Document, appareil, référence… (facultatif)' });
      return frag(
        el('p', { class: 'texte-doux texte-sm sans-marge' },
          'Votre question rejoint la liste des questions en attente de la base de '
          + 'connaissances, dans ce navigateur. Aucun envoi réseau n’a lieu.'),
        el('div', { class: 'champ' },
          el('label', { class: 'champ__etiquette', for: 'demande-question' }, 'Votre question'),
          champ, erreur),
        el('div', { class: 'champ' },
          el('label', { class: 'champ__etiquette', for: 'demande-contexte' }, 'Contexte'),
          contexte));
    },
    actions: [
      { libelle: 'Annuler', variante: 'secondaire', ferme: true },
      { libelle: 'Envoyer aux experts', variante: 'principal', onClick: () => {
        const q = texte(champ && champ.value);
        if (!q) { if (erreur) erreur.hidden = false; if (champ) champ.focus(); return false; }
        const ok = enregistrerDemande(q, texte(contexte && contexte.value), pole.cle);
        toast(ok ? 'Question enregistrée pour les experts du pôle ' + pole.cle + '.'
                 : 'Ce navigateur refuse le stockage local : la question n’a pas pu être conservée.',
              ok ? 'succes' : 'alerte');
        annoncer('Question enregistrée.');
        return true;
      } }
    ]
  });
}

function rendreFaq(pole, groupes, conteneur) {
  const versElement = (q, groupe) => ({
    id: texte(q.id) || ('q-' + groupe + '-' + Math.random().toString(36).slice(2)),
    groupe, titre: texte(q.question), meta: texte(q.categorie) || '',
    recherche: [q.reponse].concat(Array.isArray(q.motsCles) ? q.motsCles : []).map(texte),
    source: q,
    corps: () => frag(
      el('p', {}, texte(q.reponse) || 'Réponse à renseigner.'),
      Array.isArray(q.motsCles) && q.motsCles.length
        ? el('div', { class: 'liseuse__mots' }, q.motsCles.map((m) => el('span', { class: 'badge badge--contour' }, texte(m))))
        : null)
  });
  const elements = groupes.pole.map((q) => versElement(q, 'pole')).concat(groupes.service.map((q) => versElement(q, 'service')));

  const boutonExpert = el('button', { type: 'button', class: 'bouton bouton--principal', onClick: (evt) => {
    const champ = conteneur.querySelector('.liseuse__recherche');
    ouvrirDemandeExpert(pole, evt.currentTarget, champ ? champ.value : '');
  } }, 'Interroger un expert');

  const pied = el('div', { class: 'liseuse__pied' },
    el('div', {},
      el('p', { class: 'liseuse__pied-titre' }, 'Une question spécifique ?'),
      el('p', {}, 'Si la base ne couvre pas votre périmètre, sollicitez les référents du pôle.')),
    boutonExpert);

  monter(conteneur,
    lecteur({
      id: 'faq-' + pole.cle.toLowerCase(),
      elements,
      groupes: [{ cle: 'pole', titre: 'Pôle ' + pole.cle }, { cle: 'service', titre: 'Service ETII' }],
      titreListe: 'Base de connaissances',
      placeholder: 'Rechercher une question technique…',
      vide: 'Aucune question publiée pour ce pôle.',
      entete: (item) => frag(
        el('span', { class: 'badge badge--neutre' }, item.groupe === 'pole' ? 'Pôle ' + pole.cle : 'Service ETII'),
        item.meta ? el('span', { class: 'badge badge--contour' }, item.meta) : null),
      actions: (item) => el('a', { class: 'bouton bouton--secondaire bouton--compact',
        href: lienPole('faq.html', pole.cle, { question: texte(item.source.id) }) }, 'Ouvrir dans la base'),
      pied
    }));
}

/* -------------------------------------------------------------------------
   6. En-tête, sous-navigation, refus
   ------------------------------------------------------------------------- */

function rendreEntete(pole) {
  const libelle = document.getElementById('pole-libelle');
  if (libelle) libelle.textContent = 'Pôle ' + pole.cle;
  const titre = document.getElementById('pole-titre');
  if (titre) monter(titre, el('span', null, pole.cle), el('span', { class: 'pole-titre__metaphore' }, pole.metaphore));
  const description = document.getElementById('pole-description');
  if (description) description.textContent = pole.description;
  try { document.title = pole.cle + ' — ' + pole.metaphore + ' — ETII Hub'; } catch (_e) { /* ignoré */ }
}

/* La sous-navigation suit la lecture : l'ancre de la section visible est
   marquée courante. */
function suivreSections() {
  const liens = Array.from(document.querySelectorAll('.sous-nav a[href^="#"]'));
  if (!liens.length || typeof IntersectionObserver !== 'function') return;
  const cibles = liens.map((a) => document.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);
  const marquer = (id) => liens.forEach((a) => a.setAttribute('aria-current', a.getAttribute('href') === '#' + id ? 'true' : 'false'));
  const obs = new IntersectionObserver((entrees) => {
    const visible = entrees.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (visible) marquer(visible.target.id);
  }, { rootMargin: '-30% 0px -55% 0px', threshold: [0, 0.2, 0.5] });
  cibles.forEach((c) => obs.observe(c));
}

function refuser(brut) {
  const hote = document.getElementById('pole-alerte');
  const codes = Object.keys(POLES);
  const message = brut
    ? 'Le paramètre « ' + brut + ' » ne désigne aucun pôle du service.'
    : 'Cette page n’indique aucun pôle : son attribut data-pole est absent.';
  if (hote) {
    hote.hidden = false;
    monter(hote,
      el('div', { class: 'etat-vide etat-vide--encadre etat-vide--erreur', role: 'alert' },
        el('span', { class: 'etat-vide__illustration', 'aria-hidden': 'true' }, '!'),
        el('p', { class: 'etat-vide__titre' }, 'Espace de pôle inconnu'),
        el('p', { class: 'etat-vide__texte' },
          message + ' Les espaces de pôle sont ' + codes.join(', ') + '. Le niveau service, lui, est le tableau de bord ETII.'),
        el('div', { class: 'etat-vide__actions' },
          frag(codes.map((code) => el('a', { class: 'bouton bouton--secondaire', href: code.toLowerCase() + '.html' }, code)),
            el('a', { class: 'bouton bouton--principal', href: 'index.html' }, 'Tableau de bord ETII')))));
  }
  document.querySelectorAll('[data-section-pole]').forEach((s) => s.remove());
  console.error('[pole] ' + message);
}

/* -------------------------------------------------------------------------
   7. Démarrage
   ------------------------------------------------------------------------- */

initTheme();

const PARAMETRE = (document.body && document.body.dataset ? String(document.body.dataset.pole || '') : '').trim();
const POLE = Object.prototype.hasOwnProperty.call(POLES, PARAMETRE.toUpperCase()) ? POLES[PARAMETRE.toUpperCase()] : null;

initNav(POLE ? POLE.cle.toLowerCase() + '.html' : '');

if (!POLE) {
  refuser(PARAMETRE);
} else {
  rendreEntete(POLE);
  suivreSections();

  avecEtat('#zone-communication', () => chargerDonnees('communications'),
    (donnees, conteneur) => rendreCommunication(POLE, donnees, conteneur), {
      squelette: 3,
      texteChargement: 'Chargement de la communication du pôle ' + POLE.cle + '…',
      titreErreur: 'Communication indisponible',
      titreVide: 'Aucune communication',
      texteVide: 'Les communications publiées par ce pôle apparaîtront ici.',
      estVide: (d) => !d || dossiersDepuisCommunications(d, { pole: POLE.cle }).length === 0
    });

  avecEtat('#zone-reunions', async () => reunionsDuPole(await chargerDonnees('reunions'), POLE.cle),
    (groupes, conteneur) => rendreReunions(POLE, groupes, conteneur), {
      squelette: 2, compact: true,
      texteChargement: 'Chargement des réunions du pôle…',
      titreErreur: 'Réunions indisponibles',
      titreVide: 'Aucune réunion publiée',
      texteVide: 'Les comptes-rendus et les prochains points de ce pôle apparaîtront ici.',
      estVide: (g) => !g || (g.comptesRendus.length + g.prochainsPoints.length) === 0
    });

  avecEtat('#zone-organigramme', async () => blocOrganigramme(await chargerDonnees('organigramme'), POLE.cle),
    (bloc, conteneur) => rendreOrganigramme(POLE, bloc, conteneur), {
      squelette: 2, compact: true,
      texteChargement: 'Chargement de l’organigramme du pôle…',
      titreErreur: 'Organigramme indisponible',
      titreVide: 'Aucune équipe déclarée',
      texteVide: 'Ce pôle n’a encore ni responsable ni squad dans l’organigramme du service.'
    });

  avecEtat('#zone-faq', async () => questionsDuPole(await chargerDonnees('faq'), POLE.cle),
    (groupes, conteneur) => rendreFaq(POLE, groupes, conteneur), {
      squelette: 3, compact: true,
      texteChargement: 'Chargement des questions du pôle…',
      titreErreur: 'Questions indisponibles',
      titreVide: 'Aucune question',
      texteVide: 'Les questions fréquentes de ce pôle apparaîtront ici.',
      estVide: (g) => !g || (g.pole.length + g.service.length) === 0
    });
}

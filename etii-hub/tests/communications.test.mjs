// Tests de la source des communications — exécuter depuis etii-hub/ :
//   node tests/communications.test.mjs
// Aucune dépendance : Node seul suffit.

import { analyserCorps, corpsEnTexte, analyserCsv, analyserChiffres, analyserSerie,
  chiffresEnTexte, serieEnTexte, communicationsDepuisLignes, annonceDepuisLigne, ligneDepuisAnnonce, COLONNES }
  from '../assets/js/communications.js';
// kiosque.js ne touche au DOM qu'à l'appel : ses fonctions de tri sont
// lisibles sous Node, et c'est là que la date d'une entrée est jugée.
import { dossiersDepuisCommunications } from '../assets/js/kiosque.js';

let ok = 0, ko = 0;
const t = (nom, cond, detail = '') => {
  if (cond) { ok++; console.log(`  OK   ${nom}`); }
  else { ko++; console.log(`  ÉCHEC ${nom} ${detail}`); }
};
const egal = (a, b) => JSON.stringify(a) === JSON.stringify(b);

console.log('\n== Le corps : préfixes → lignes typées ==');
const lignes = analyserCorps('-> Ce qui change\n• Nouvelle arborescence.\n- Liens redirigés.\n\nV Aucune action requise.\n! Sauvegardez avant 19h30.\nUn texte libre.');
t('sept lignes typées', lignes.length === 7, `(${lignes.length})`);
t('titre, puce, puce, vide, valide, alerte, texte',
  egal(lignes.map((l) => l.type), ['titre', 'puce', 'puce', 'vide', 'valide', 'alerte', 'texte']));
t('le préfixe est retiré du texte', lignes[0].texte === 'Ce qui change' && lignes[4].texte === 'Aucune action requise.');
t('aller-retour texte → lignes → texte', egal(analyserCorps(corpsEnTexte(lignes)), lignes));
t('vides de tête et de queue ignorés', analyserCorps('\n\nBonjour\n\n').length === 1);
t('texte vide → aucune ligne', analyserCorps('').length === 0 && analyserCorps(null).length === 0);

console.log('\n== CSV RFC 4180 ==');
const csv = 'type,id,date,pole,titre,resume,corps\n'
  + 'annonce,c1,2026-09-12,ETII,"Titre, avec virgule","Résumé ""cité""","-> Ligne 1\n• Ligne 2"\n'
  + ',,,,,,\n'
  + 'alerte,,,,"Maintenance mercredi soir",,\n';
const rangees = analyserCsv(csv);
t('la ligne vide est ignorée', rangees.length === 2, `(${rangees.length})`);
t('virgule entre guillemets conservée', rangees[0].titre === 'Titre, avec virgule');
t('guillemet doublé décodé', rangees[0].resume === 'Résumé "cité"');
t('retour à la ligne dans une cellule conservé', rangees[0].corps === '-> Ligne 1\n• Ligne 2');
t('en-tête normalisé (Résumé → resume)', 'resume' in analyserCsv('Titre;Résumé\nA;B')[0]);
t('séparateur point-virgule détecté', analyserCsv('titre;date\nA;2026-01-01')[0].date === '2026-01-01');
t('séparateur tabulation détecté', analyserCsv('titre\tdate\nA\t2026-01-01')[0].date === '2026-01-01');
t('BOM ignoré', analyserCsv('﻿titre,date\nA,2026-01-01')[0].titre === 'A');

console.log('\n== Chiffres clés et série ==');
const chiffres = analyserChiffres('OTQ du service = 95,4 % hausse ; Semaines d’essais = 6 ; Écarts à solder = 3 ↘ ; Illisible ; Sans valeur = abc');
t('trois chiffres lisibles', chiffres.length === 3, `(${chiffres.length})`);
t('valeur décimale française, unité %, tendance', chiffres[0].valeur === 95.4 && chiffres[0].unite === '%' && chiffres[0].tendance === 'hausse');
t('glyphe ↘ → baisse', chiffres[2].tendance === 'baisse');
t('au plus quatre chiffres', analyserChiffres('a=1;b=2;c=3;d=4;e=5').length === 4);
t('aller-retour chiffres', egal(analyserChiffres(chiffresEnTexte(chiffres)), chiffres));
const serie = analyserSerie('OTQ mensuel (%) | 2026-04 = 92,1 ; 2026-05 = 92,8 ; 2026-06 = ; 2026-07 = 94.2');
t('série : libellé et unité', serie.libelle === 'OTQ mensuel' && serie.unite === '%');
t('série : quatre mois, un trou', egal(serie.mois, ['2026-04', '2026-05', '2026-06', '2026-07']) && egal(serie.valeurs, [92.1, 92.8, null, 94.2]));
t('série sans valeur → null', analyserSerie('X | 2026-01 = ') === null && analyserSerie('') === null);
t('aller-retour série', egal(analyserSerie(serieEnTexte(serie)), serie));

console.log('\n== Des lignes à l’objet communications ==');
const objet = communicationsDepuisLignes([
  { type: 'mot', date: '2026-09-15', titre: 'Un trimestre qui se tient', resume: 'Trois mois de progrès.', corps: 'Merci à tous.', auteur: 'Personne 01', fonction: 'Direction', chiffres: 'OTQ = 95,4 %' },
  { type: 'mot', date: '2026-06-01', titre: 'Ancien mot', corps: '…' },
  { type: 'annonce', id: 'c9', date: '2026-09-12', pole: 'etiie', categorie: 'Outils', statut: 'URGENT', titre: 'Migration', resume: 'Interruption.', corps: '! Sauvegardez.', image: 'https://exemple.invalid/photo.jpg', imageAlt: 'Une photo', serie: 'Charge (h) | 2026-08 = 10 ; 2026-09 = 12' },
  { type: 'alerte', titre: 'Maintenance mercredi soir.' },
  { type: 'annonce', date: 'pas une date', titre: 'Illisible' },
  { type: '', date: '2026-08-19', titre: 'Sans type ni id', pole: 'ETIII' }
]);
t('le mot du chef le plus récent l’emporte', objet.motDuChef && objet.motDuChef.titre === 'Un trimestre qui se tient');
t('le mot porte auteur, résumé, chiffres', objet.motDuChef.auteur === 'Personne 01' && objet.motDuChef.resume === 'Trois mois de progrès.' && objet.motDuChef.chiffres.length === 1);
t('une alerte, un texte', egal(objet.alertes, ['Maintenance mercredi soir.']));
t('deux annonces + l’ancien édito (la ligne illisible est ignorée)', objet.annonces.length === 3, `(${objet.annonces.length})`);
const ancienEdito = objet.annonces.find((a) => a.titre === 'Ancien mot');
t('l’édito précédent reprend sa place dans la frise, daté et identifié',
  !!ancienEdito && ancienEdito.categorie === 'Édito' && ancienEdito.pole === 'ETII'
  && ancienEdito.date === '2026-06-01' && !!ancienEdito.id,
  JSON.stringify(ancienEdito && { id: ancienEdito.id, categorie: ancienEdito.categorie }));
const migration = objet.annonces.find((a) => a.id === 'c9');
t('date conservée, pôle et statut normalisés', migration.date === '2026-09-12' && migration.pole === 'ETIIE' && migration.statut === 'urgent');
t('image, corps typé, série', migration.image.src === 'https://exemple.invalid/photo.jpg' && migration.corps[0].type === 'alerte' && migration.serie.valeurs[1] === 12);
const sansId = objet.annonces.find((a) => a.titre === 'Sans type ni id');
t('un identifiant est fabriqué quand il manque', /^f20260819-\d+$/.test(sansId.id) && sansId.categorie === 'Général' && sansId.statut === 'info');
t('les annonces sont triées, la plus récente d’abord', objet.annonces[0].date >= objet.annonces[1].date);
t('agenda vide, jamais absent', Array.isArray(objet.agenda) && objet.agenda.length === 0);
t('entrée nulle → objet vide', communicationsDepuisLignes(null).annonces.length === 0);

console.log('\n== Les dates : AAAA-MM-JJ, et rien d’autre ==');
const strict = communicationsDepuisLignes([
  { type: 'annonce', date: '09/21/2026', titre: 'Date à l’américaine' },
  { type: 'annonce', date: '12/09/2026', titre: 'Date à la française' },
  { type: 'annonce', date: '2026-09-12', titre: 'Date ISO' }
]);
t('une date JJ/MM/AAAA n’est plus devinée : la ligne est refusée',
  strict.annonces.length === 1 && strict.annonces[0].titre === 'Date ISO', `(${strict.annonces.length})`);
t('les lignes écartées sont comptées, pour pouvoir le dire dans la page',
  strict.ecartees === 2, `(${strict.ecartees})`);

console.log('\n== Le kiosque n’affiche que ce qui a eu lieu ==');
const dossiers = dossiersDepuisCommunications({
  annonces: [
    { id: 'f1', date: '2062-09-12', titre: 'Faute de frappe sur l’année' },
    { id: 'f2', date: '2026-01-05', titre: 'Une communication réelle' }
  ],
  agenda: [
    { id: 'a1', date: '2062-10-08', statut: 'passee', type: 'reunion', titre: 'Passée, mais datée dans le futur' }
  ]
});
t('une annonce datée d’une année future ne coupe plus la frise en deux',
  !dossiers.some((x) => x.id === 'annonce-f1'), JSON.stringify(dossiers.map((x) => x.id)));
t('une entrée d’agenda « passee » datée dans le futur ne passe plus le filtre',
  !dossiers.some((x) => x.id === 'agenda-a1'));
t('la communication réelle, elle, reste', dossiers.some((x) => x.id === 'annonce-f2'));

console.log('\n== Une alerte ne survit pas à sa quinzaine ==');
const jourIso = (recul) => { const d = new Date(); d.setDate(d.getDate() - recul); return d.toISOString().slice(0, 10); };
const bandeau = communicationsDepuisLignes([
  { type: 'alerte', titre: 'Alerte du jour.', date: jourIso(0) },
  { type: 'alerte', titre: 'Alerte d’il y a un mois.', date: jourIso(30) },
  { type: 'alerte', titre: 'Alerte sans date.' }
]).alertes;
t('une alerte datée de plus de quatorze jours ne monte plus au bandeau',
  egal(bandeau, ['Alerte du jour.', 'Alerte sans date.']), JSON.stringify(bandeau));

console.log('\n== La ligne à coller dans la feuille ==');
const ligne = ligneDepuisAnnonce(migration);
const cellules = ligne.split('\t');
t('autant de cellules que de colonnes', cellules.length === COLONNES.length, `(${cellules.length} / ${COLONNES.length})`);
t('aller-retour annonce → ligne → annonce', (() => {
  const objetLigne = {}; COLONNES.forEach((c, i) => { objetLigne[c] = cellules[i].replace(/^"|"$/g, '').replace(/""/g, '"'); });
  const retour = annonceDepuisLigne(objetLigne, 0);
  return retour.id === 'c9' && retour.titre === 'Migration' && retour.corps[0].type === 'alerte' && retour.serie.valeurs[0] === 10;
})());

console.log(`\n  ${ok} réussis, ${ko} échoués`);
process.exit(ko ? 1 : 0);

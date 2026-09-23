/* =========================================================================
   ETII Hub — Le mode édition

   Un bouton « Modifier » dans la barre du site. Allumé, il fait apparaître
   partout les commandes d'édition — « Ajouter », « Modifier »,
   « Supprimer » — et un bandeau qui dit où partent les modifications.
   Éteint, le site se lit comme avant : les 400 lecteurs ne voient aucune
   commande.

   Les commandes sont posées dans la page une fois pour toutes, avec la
   classe `edition-seulement` : c'est la feuille de style qui les montre ou
   les cache selon `html.mode-edition`. Aucune section n'a à se redessiner
   quand on bascule.

   Le bouton n'apparaît que pour qui peut écrire : sur le lien publié, le
   menu de partage décide (magasin.js) ; ailleurs, les modifications
   restent dans ce navigateur et le bandeau le dit.

   API :
     installerEdition()                 pose le bouton et restaure l'état
     enEdition()                        -> booléen
     boutonAjouter(libelle, surClic)    -> <button>
     barreEdition({ surModifier, surSupprimer, quoi })  -> <div>
     confirmer({ titre, message, libelle, declencheur })  -> Promise<booléen>
     ouvrirFormulaire({ titre, champs, valeurs, surEnregistrer,
                        surSupprimer, quoi, declencheur })
   ========================================================================= */

import { el, monter, ouvrirModale, toast, annoncer, stockage } from './ui.js';
import { ouvrirMagasin } from './magasin.js';
import { ouvrirHistorique } from './journal.js';

const CLE_ETAT = 'edition.actif';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function cloner(v) { return v === undefined ? {} : JSON.parse(JSON.stringify(v)); }

/* -------------------------------------------------------------------------
   1. La bascule
   ------------------------------------------------------------------------- */

let installe = false;

/** Vrai quand les commandes d'édition sont visibles. */
export function enEdition() {
  try { return document.documentElement.classList.contains('mode-edition'); } catch (_e) { return false; }
}

function appliquer(actif, magasin, bouton) {
  document.documentElement.classList.toggle('mode-edition', actif);
  if (bouton) {
    bouton.setAttribute('aria-pressed', actif ? 'true' : 'false');
    monter(bouton,
      el('span', { class: 'bascule-edition__icone', 'aria-hidden': 'true' }, actif ? '✓' : '✎'),
      el('span', { class: 'bascule-edition__libelle' }, actif ? 'Terminer' : 'Modifier'));
  }
  let bandeau = document.querySelector('[data-bandeau-edition]');
  if (actif && !bandeau) {
    bandeau = el('div', { class: 'edition-bandeau', role: 'status', dataset: { bandeauEdition: '' } },
      el('span', { class: 'edition-bandeau__marque', 'aria-hidden': 'true' }, '✎'),
      el('p', { class: 'sans-marge' },
        el('strong', {}, 'Mode édition. '),
        magasin.mode === 'partage'
          ? 'Ce que vous ajoutez, modifiez ou supprimez est enregistré pour tous les lecteurs du site.'
          : 'Ce que vous modifiez est enregistré dans ce navigateur seulement : ouvrez le site depuis son lien publié pour le partager.',
        /* Quand l'hôte dit qui est connecté (Google), on le montre : on
           sait sous quel nom partent les modifications. */
        magasin.identite ? el('span', { class: 'edition-bandeau__identite' }, ' Connecté : ' + magasin.identite + '.') : null),
      /* Tout ce qui a été fait dans le site, par qui, quand, rubrique par
         rubrique (journal.js). */
      typeof magasin.journal === 'function'
        ? el('button', {
            type: 'button', class: 'edition-bandeau__historique',
            onClick: (evt) => ouvrirHistorique(evt.currentTarget)
          }, el('span', { 'aria-hidden': 'true' }, '☰ '), 'Historique')
        : null);
    const entete = document.querySelector('.site-entete');
    if (entete && entete.parentNode) entete.parentNode.insertBefore(bandeau, entete.nextSibling);
    else document.body.prepend(bandeau);
  } else if (!actif && bandeau) {
    bandeau.remove();
  }
}

/**
 * Pose le bouton « Modifier » dans la barre du site, s'il y a de quoi
 * écrire. Idempotent : les pages peuvent l'appeler sans se concerter.
 */
export async function installerEdition() {
  if (installe || typeof document === 'undefined') return;
  installe = true;
  let magasin;
  try { magasin = await ouvrirMagasin(); } catch (_e) { return; }
  if (!magasin.peutEcrire) return;
  const barre = document.querySelector('.site-entete__interieur');
  if (!barre) return;
  const bouton = el('button', {
    type: 'button', class: 'bascule-edition', 'aria-pressed': 'false',
    title: 'Ajouter, modifier ou supprimer le contenu du site'
  });
  bouton.addEventListener('click', () => {
    const actif = !enEdition();
    appliquer(actif, magasin, bouton);
    stockage.ecrire(CLE_ETAT, actif);
    annoncer(actif ? 'Mode édition activé.' : 'Mode édition terminé.');
  });
  const theme = barre.querySelector('.bascule-theme');
  if (theme) barre.insertBefore(bouton, theme); else barre.appendChild(bouton);
  appliquer(stockage.lire(CLE_ETAT, false) === true, magasin, bouton);
}

/* -------------------------------------------------------------------------
   2. Les commandes
   ------------------------------------------------------------------------- */

/** « + Ajouter … », visible seulement en mode édition. */
export function boutonAjouter(libelle, surClic) {
  const b = el('button', { type: 'button', class: 'bouton bouton--secondaire bouton--compact edition-seulement edition-ajout' },
    el('span', { 'aria-hidden': 'true' }, '+ '), libelle);
  b.addEventListener('click', (evt) => { evt.stopPropagation(); surClic(b); });
  return b;
}

/**
 * « Modifier » et « Supprimer » pour un élément, visibles seulement en mode
 * édition. `quoi` nomme l'élément pour les lecteurs d'écran.
 */
export function barreEdition(options) {
  const o = options || {};
  const quoi = texte(o.quoi);
  const boutons = [];
  if (typeof o.surModifier === 'function') {
    const b = el('button', { type: 'button', class: 'barre-edition__bouton', 'aria-label': 'Modifier' + (quoi ? ' : ' + quoi : '') },
      el('span', { 'aria-hidden': 'true' }, '✎'), el('span', { class: 'barre-edition__libelle' }, 'Modifier'));
    b.addEventListener('click', (evt) => { evt.preventDefault(); evt.stopPropagation(); o.surModifier(b); });
    boutons.push(b);
  }
  if (typeof o.surSupprimer === 'function') {
    const b = el('button', { type: 'button', class: 'barre-edition__bouton barre-edition__bouton--danger', 'aria-label': 'Supprimer' + (quoi ? ' : ' + quoi : '') },
      el('span', { 'aria-hidden': 'true' }, '×'), el('span', { class: 'barre-edition__libelle' }, 'Supprimer'));
    b.addEventListener('click', async (evt) => {
      evt.preventDefault(); evt.stopPropagation();
      const ok = await confirmer({ titre: 'Supprimer ?', message: quoi ? '« ' + quoi + ' » sera retiré du site.' : 'Cet élément sera retiré du site.', libelle: 'Supprimer', declencheur: b });
      if (ok) o.surSupprimer(b);
    });
    boutons.push(b);
  }
  return el('div', { class: ['barre-edition', 'edition-seulement', o.classe || null] }, boutons);
}

/** Une question fermée, dans une fenêtre. */
export function confirmer(options) {
  const o = options || {};
  return new Promise((resoudre) => {
    let reponse = false;
    ouvrirModale({
      titre: o.titre || 'Confirmer',
      declencheur: o.declencheur,
      contenu: el('p', { class: 'sans-marge' }, o.message || ''),
      actions: [
        { libelle: 'Annuler', variante: 'discret' },
        { libelle: o.libelle || 'Confirmer', variante: 'danger', onClick: () => { reponse = true; } }
      ],
      onFermeture: () => resoudre(reponse)
    });
  });
}

/* -------------------------------------------------------------------------
   3. Le formulaire générique
   ------------------------------------------------------------------------- */

/* Les valeurs se lisent et s'écrivent par chemin : « fiche.resume »,
   « fiche.motorisation.moteur.valeur ». */
function lireChemin(objet, chemin) {
  return String(chemin).split('.').reduce((o, k) => (o && typeof o === 'object') ? o[k] : undefined, objet);
}
function ecrireChemin(objet, chemin, valeur) {
  const cles = String(chemin).split('.');
  let o = objet;
  for (let i = 0; i < cles.length - 1; i += 1) {
    if (!o[cles[i]] || typeof o[cles[i]] !== 'object') o[cles[i]] = {};
    o = o[cles[i]];
  }
  o[cles[cles.length - 1]] = valeur;
}

let compteur = 0;
function idUnique() { compteur += 1; return 'formulaire-edition-' + compteur; }

const NIVEAUX = [['referent', 'Référent'], ['confirme', 'Confirmé'], ['pratique', 'Pratique']];

/* Un champ, selon son type. Chaque contrôle écrit dans `valeurs` à chaque
   frappe ; la validation n'a lieu qu'à l'enregistrement. */
function construireChamp(desc, valeurs) {
  const id = idUnique();
  const brut = lireChemin(valeurs, desc.cle);
  const etiquette = el('label', { class: 'champ__etiquette', for: id },
    desc.libelle, desc.requis ? el('span', { class: 'champ__requis', 'aria-hidden': 'true' }, ' *') : null);
  const aide = desc.aide ? el('p', { class: 'champ__aide', id: id + '-aide' }, desc.aide) : null;
  const erreur = el('p', { class: 'champ__erreur', id: id + '-erreur', role: 'alert', hidden: true });
  const decrit = [aide ? id + '-aide' : null, id + '-erreur'].filter(Boolean).join(' ');
  const commun = { id, class: 'champ__controle', 'aria-describedby': decrit, required: desc.requis ? true : null, placeholder: desc.placeholder || null };
  let controle;
  let propositions = null;

  switch (desc.type) {
    case 'long': {
      controle = el('textarea', Object.assign({ rows: desc.lignes || 4 }, commun));
      controle.value = texte(brut);
      controle.addEventListener('input', () => ecrireChemin(valeurs, desc.cle, controle.value));
      break;
    }
    case 'lignes': {
      controle = el('textarea', Object.assign({ rows: desc.lignes || 4 }, commun));
      controle.value = (Array.isArray(brut) ? brut : []).map((x) => (x && typeof x === 'object') ? texte(x.texte) : texte(x)).filter(Boolean).join('\n');
      controle.addEventListener('input', () => ecrireChemin(valeurs, desc.cle,
        controle.value.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => (desc.objets ? { texte: l } : l))));
      break;
    }
    case 'liste': {
      controle = el('input', Object.assign({ type: 'text', autocomplete: 'off' }, commun));
      controle.value = (Array.isArray(brut) ? brut : (texte(brut) ? [brut] : [])).map(texte).filter(Boolean).join(', ');
      controle.addEventListener('input', () => ecrireChemin(valeurs, desc.cle,
        controle.value.split(/\s*[,;]\s*/).map((x) => x.trim()).filter(Boolean)));
      break;
    }
    case 'choix': {
      const options = typeof desc.options === 'function' ? desc.options(valeurs) : (desc.options || []);
      controle = el('select', commun, options.map(([v, l]) => el('option', { value: v }, l)));
      controle.value = texte(brut);
      if (!controle.value && options.length && desc.requis) { controle.value = options[0][0]; ecrireChemin(valeurs, desc.cle, controle.value); }
      controle.addEventListener('change', () => { ecrireChemin(valeurs, desc.cle, controle.value); if (typeof desc.surChangement === 'function') desc.surChangement(valeurs); });
      break;
    }
    case 'plusieurs': {
      /* Des cases à cocher : les pôles d'un porteur, par exemple. */
      const choisis = new Set((Array.isArray(brut) ? brut : []).map(texte));
      const options = typeof desc.options === 'function' ? desc.options(valeurs) : (desc.options || []);
      controle = el('div', { class: 'formulaire-edition__cases', id, role: 'group', 'aria-labelledby': id + '-legende' },
        options.map(([v, l]) => {
          const c = el('input', { type: 'checkbox', value: v, checked: choisis.has(v) ? true : null });
          c.addEventListener('change', () => {
            if (c.checked) choisis.add(v); else choisis.delete(v);
            ecrireChemin(valeurs, desc.cle, options.map(([x]) => x).filter((x) => choisis.has(x)));
          });
          return el('label', { class: 'formulaire-edition__case' }, c, ' ', l);
        }));
      const legende = el('p', { class: 'champ__etiquette', id: id + '-legende' }, desc.libelle);
      return { noeud: el('div', { class: 'champ' }, legende, controle, aide), valider: () => true };
    }
    case 'competences': {
      const lignes = (Array.isArray(brut) ? brut : []).map((c) => ({ nom: texte(c && c.nom), niveau: texte(c && c.niveau) || 'pratique' }));
      const liste = el('div', { class: 'formulaire-edition__competences', id });
      const ecrire = () => ecrireChemin(valeurs, desc.cle, lignes.filter((c) => c.nom).map((c) => ({ nom: c.nom, niveau: c.niveau })));
      const rendre = () => {
        monter(liste, lignes.map((c, i) => {
          const nom = el('input', { type: 'text', class: 'champ__controle', value: c.nom, placeholder: 'Compétence', 'aria-label': 'Compétence ' + (i + 1) });
          nom.addEventListener('input', () => { c.nom = nom.value.trim(); ecrire(); });
          const niveau = el('select', { class: 'champ__controle', 'aria-label': 'Niveau de la compétence ' + (i + 1) },
            NIVEAUX.map(([v, l]) => el('option', { value: v }, l)));
          niveau.value = c.niveau;
          niveau.addEventListener('change', () => { c.niveau = niveau.value; ecrire(); });
          const retirer = el('button', { type: 'button', class: 'bouton bouton--discret bouton--compact', 'aria-label': 'Retirer la compétence ' + (i + 1) }, '×');
          retirer.addEventListener('click', () => { lignes.splice(i, 1); ecrire(); rendre(); });
          return el('div', { class: 'formulaire-edition__competence' }, nom, niveau, retirer);
        }),
        (() => {
          const ajouter = el('button', { type: 'button', class: 'bouton bouton--discret bouton--compact' }, '+ Une compétence');
          ajouter.addEventListener('click', () => { lignes.push({ nom: '', niveau: 'pratique' }); rendre(); const champs = liste.querySelectorAll('input'); if (champs.length) champs[champs.length - 1].focus(); });
          return ajouter;
        })());
      };
      rendre();
      const legende = el('p', { class: 'champ__etiquette' }, desc.libelle);
      return { noeud: el('div', { class: 'champ' }, legende, liste, aide), valider: () => true };
    }
    case 'groupe': {
      /* Un ensemble de champs, sous une légende (un groupe de la fiche d'un
         porteur : Motorisation, Masses…). */
      const enfants = (desc.champs || []).map((d) => construireChamp(d, valeurs));
      return {
        noeud: el('fieldset', { class: 'formulaire-edition__groupe' },
          el('legend', { class: 'groupe-champs__legende' }, desc.libelle),
          el('div', { class: 'formulaire-edition__grille' }, enfants.map((e) => e.noeud))),
        valider: () => enfants.every((e) => e.valider())
      };
    }
    default: {
      const type = desc.type === 'date' ? 'date' : (desc.type === 'url' ? 'url' : 'text');
      /* Des suggestions (les compétences déjà citées, par exemple) : une
         liste proposée à la frappe, sans interdire une valeur neuve. */
      const suggestions = Array.isArray(desc.suggestions) ? desc.suggestions.map(texte).filter(Boolean) : [];
      controle = el('input', Object.assign({ type, autocomplete: 'off', inputmode: desc.type === 'nombre' ? 'decimal' : null,
        list: suggestions.length ? id + '-suggestions' : null }, commun));
      controle.value = texte(brut);
      if (suggestions.length) {
        propositions = el('datalist', { id: id + '-suggestions' }, [...new Set(suggestions)].map((v) => el('option', { value: v })));
      }
      controle.addEventListener('input', () => {
        const v = controle.value;
        /* « nombre » et « valeur » : un nombre saisi (« 6050 », « 13,4 »)
           est rangé en nombre — la fiche l'écrit alors à la française et
           en fait un chiffre clé ; une phrase reste une phrase. */
        const numerique = (desc.type === 'nombre' || desc.type === 'valeur') && /^\s*-?\d+(?:[.,]\d+)?\s*$/.test(v);
        ecrireChemin(valeurs, desc.cle, numerique ? Number(v.replace(',', '.')) : v);
      });
    }
  }

  const valider = () => {
    const v = lireChemin(valeurs, desc.cle);
    const vide = Array.isArray(v) ? !v.length : !texte(v);
    let message = '';
    if (desc.requis && vide) message = 'À renseigner.';
    else if (!vide && typeof desc.valider === 'function') message = desc.valider(v, valeurs) || '';
    erreur.textContent = message;
    erreur.hidden = !message;
    controle.setAttribute('aria-invalid', message ? 'true' : 'false');
    return !message;
  };
  return {
    noeud: el('div', { class: ['champ', desc.large ? 'formulaire-edition__large' : null] }, etiquette, controle, propositions, aide, erreur),
    valider,
    controle
  };
}

/**
 * Un formulaire d'édition dans une fenêtre.
 *
 * @param {object} o
 * @param {string} o.titre
 * @param {Array<object>} o.champs     descripteurs : { cle, libelle, type,
 *        requis, aide, placeholder, options, lignes, large, valider, champs }
 *        types : texte · long · date · nombre · valeur (nombre ou phrase) ·
 *        url · choix · plusieurs · liste (virgules) · lignes (une par ligne) ·
 *        competences · groupe
 * @param {object} [o.valeurs]         l'élément à modifier (copié, jamais muté)
 * @param {(valeurs:object)=>Promise} o.surEnregistrer
 * @param {()=>Promise} [o.surSupprimer]   absent : pas de bouton Supprimer
 * @param {string} [o.quoi]            nomme l'élément dans la confirmation
 * @param {Element} [o.declencheur]
 */
export function ouvrirFormulaire(o) {
  const valeurs = cloner(o.valeurs || {});
  const construits = (o.champs || []).map((d) => construireChamp(d, valeurs));
  const erreurGenerale = el('p', { class: 'champ__erreur', role: 'alert', hidden: true });
  const formulaire = el('form', { class: 'formulaire-edition', novalidate: true },
    el('div', { class: 'formulaire-edition__grille' }, construits.map((c) => c.noeud)),
    erreurGenerale);

  let occupe = false;
  const enregistrer = async (api) => {
    if (occupe) return false;
    const valides = construits.map((c) => c.valider()).every(Boolean);
    if (!valides) {
      const premier = formulaire.querySelector('[aria-invalid="true"]');
      if (premier) premier.focus();
      return false;
    }
    occupe = true;
    erreurGenerale.hidden = true;
    const bouton = api && api.boite ? api.boite.querySelector('.modale__actions .bouton--principal') : null;
    if (bouton) { bouton.disabled = true; bouton.setAttribute('aria-busy', 'true'); bouton.textContent = 'Enregistrement…'; }
    try {
      await o.surEnregistrer(valeurs);
      api.fermer('enregistre');
      toast('Enregistré.', 'succes');
    } catch (e) {
      erreurGenerale.textContent = (e && e.message) || 'L’enregistrement a échoué.';
      erreurGenerale.hidden = false;
      if (bouton) { bouton.disabled = false; bouton.removeAttribute('aria-busy'); bouton.textContent = 'Enregistrer'; }
    } finally {
      occupe = false;
    }
    return false;
  };

  formulaire.addEventListener('submit', (evt) => { evt.preventDefault(); });

  const actions = [];
  if (typeof o.surSupprimer === 'function') {
    actions.push({
      libelle: 'Supprimer', variante: 'danger-discret', ferme: false,
      onClick: async (evt, api) => {
        const ok = await confirmer({ titre: 'Supprimer ?', message: (texte(o.quoi) ? '« ' + texte(o.quoi) + ' »' : 'Cet élément') + ' sera retiré du site.', libelle: 'Supprimer', declencheur: evt.currentTarget });
        if (!ok) return false;
        try { await o.surSupprimer(); api.fermer('supprime'); toast('Supprimé.', 'succes'); }
        catch (e) { erreurGenerale.textContent = (e && e.message) || 'La suppression a échoué.'; erreurGenerale.hidden = false; }
        return false;
      }
    });
  }
  actions.push({ libelle: 'Annuler', variante: 'discret' });
  actions.push({ libelle: o.libelleEnregistrer || 'Enregistrer', variante: 'principal', ferme: false, onClick: (_evt, api) => { enregistrer(api); return false; } });

  const modale = ouvrirModale({
    titre: o.titre,
    classe: 'modale--formulaire',
    declencheur: o.declencheur,
    contenu: formulaire,
    actions
  });
  /* Entrée dans un champ d'une ligne enregistre, comme dans tout formulaire. */
  formulaire.addEventListener('keydown', (evt) => {
    if (evt.key === 'Enter' && evt.target && evt.target.tagName === 'INPUT' && evt.target.type !== 'checkbox') {
      evt.preventDefault();
      enregistrer(modale);
    }
  });
  const premier = formulaire.querySelector('input, textarea, select');
  if (premier) setTimeout(() => premier.focus(), 0);
  return modale;
}

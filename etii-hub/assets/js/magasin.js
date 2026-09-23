/* =========================================================================
   ETII Hub — Le magasin des modifications

   Tout ce qu'on change dans le site — une communication, un rendez-vous,
   un porteur, une personne, une question, un document — est une
   MODIFICATION posée par-dessus les fichiers de assets/data/. Ce module
   les garde, et rien d'autre : il ne sait pas ce qu'est un porteur.

   Trois endroits possibles, choisis une fois pour toutes au chargement :

   - « partage », hébergé par Google : le site est servi par une
     application web Apps Script (tools/apps-script/site/Code.gs). Les
     modifications vont dans la feuille Google de l'application, que les
     lecteurs ne voient jamais ; le serveur sait qui est connecté (son
     compte Google de l'entreprise) et n'accepte d'écriture que des
     adresses de l'onglet « Éditeurs ». Le client appelle
     `google.script.run`, que la coquille du fichier autonome porte : les
     pages le trouvent chez leur parent.

   - « partage », hébergé par claude.ai : la page est ouverte depuis son
     lien claude.ai. Elle a alors une base de données à elle, partagée par
     tous ceux qui l'ouvrent (capacité `db` du runtime). Qui peut écrire,
     c'est le menu de partage de la page qui le dit : l'éditeur (« Peut
     modifier ») écrit, le lecteur lit.

   Dans les deux cas, une modification est vue par tout le monde au
   chargement suivant.

   - « navigateur » : partout ailleurs — le fichier ouvert en local, le
     serveur de test, un hébergement sans base. Les modifications restent
     dans ce navigateur (localStorage), et le mode édition le dit en
     toutes lettres.

   Le runtime de claude.ai n'existe que dans la page publiée elle-même.
   Le fichier autonome montre chaque page du site dans un cadre : le
   runtime est alors chez le parent (`parent.claude`), même origine.

   Un runtime qui ne répond pas (six secondes) n'est ni l'un ni l'autre :
   la page s'affiche sur ses fichiers, sans commande d'édition, plutôt que
   d'écrire dans ce navigateur des modifications que personne ne verrait.

   Une modification :
     { type, id, op: 'maj' | 'suppr', donnees, le: date ISO, par: id|null }
   `type` distingue les listes d'un même jeu (une annonce, un rendez-vous,
   un édito, une alerte dans « communications »), `id` l'élément.

   API :
     ouvrirMagasin()                 -> Promise<Magasin>   (une seule fois)
     Magasin.mode                    'partage' | 'navigateur' | 'indisponible'
     Magasin.hote                    'google' | 'claude' | null
     Magasin.identite                l'adresse de la personne connectée, si l'hôte la donne
     Magasin.peutEcrire              booléen
     Magasin.base(jeu)               -> une base tenue ailleurs (Google), ou null
     Magasin.lire(jeu)               -> Promise<Modification[]>
     Magasin.poser(jeu, modif)       -> Promise<void>
     Magasin.retirer(jeu, type, id)  -> Promise<void>   (annule la modification)
     Magasin.journal()               -> Promise<Entree[]>  l'historique, le plus récent d'abord

   Une modification peut porter son récit (journal.js) :
     modif.journal = { rubrique, action, element, pole, detail }
   Chaque magasin le range à sa façon : la feuille Google (un onglet par
   rubrique, écrit par Code.gs), la collection « journal » de la base du
   lien publié, ou ce navigateur.
   ========================================================================= */

const PREFIXE_LOCAL = 'etii:modifications:';
const CLE_JOURNAL_LOCAL = 'etii:journal';

/** L'historique gardé : au-delà, les plus anciens gestes s'effacent. */
const JOURNAL_MAX = 500;

/** Au-delà, le runtime ne répond plus : on n'attend pas davantage. */
const DELAI_RUNTIME = 6000;

/** Un document de la base partagée ne dépasse pas 256 Kio : on s'arrête
    avant, avec un message qui dit quoi faire. */
const POIDS_MAX = 240 * 1024;

/** Les jeux de données qu'on peut modifier : pas de nom construit à partir
    d'une saisie, jamais. */
export const JEUX_MODIFIABLES = ['communications', 'flotte', 'organigramme', 'faq', 'documents', 'reunions'];

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }

/* -------------------------------------------------------------------------
   1. Le runtime de la page publiée, s'il y en a un
   ------------------------------------------------------------------------- */

/* L'application web Apps Script : `google.script.run`, dans la page ou
   chez la coquille qui la porte. */
function trouverAppsScript() {
  const fenetres = [];
  try { fenetres.push(window); } catch (_e) { /* pas de fenêtre */ }
  try { if (window.parent && window.parent !== window) fenetres.push(window.parent); } catch (_e) { /* cadre étranger */ }
  for (const f of fenetres) {
    try {
      const g = f.google;
      if (g && g.script && g.script.run && typeof g.script.run.withSuccessHandler === 'function') return g.script.run;
    } catch (_e) { /* origine différente */ }
  }
  return null;
}

function trouverRuntime() {
  const fenetres = [];
  try { fenetres.push(window); } catch (_e) { /* pas de fenêtre */ }
  try { if (window.parent && window.parent !== window) fenetres.push(window.parent); } catch (_e) { /* cadre étranger */ }
  for (const f of fenetres) {
    try {
      if (f.claude && typeof f.claude.use === 'function') return f.claude;
    } catch (_e) { /* origine différente : on ne regarde pas */ }
  }
  return null;
}

/* Une clé de document de la base : lettres, chiffres et « _ - . ~ : @ + »
   seulement. Un identifiant du site (« Personne 22 », « H145M ») y est
   donc encodé, de façon réversible et stable. */
function cleDocument(type, id) {
  const brut = texte(type) + '~' + texte(id);
  return encodeURIComponent(brut)
    .replace(/[!*'()]/g, (c) => '%' + c.charCodeAt(0).toString(16).toUpperCase())
    .replace(/%/g, '@');
}

function nomCollection(jeu) { return 'modifications_' + jeu; }

function verifierJeu(jeu) {
  if (!JEUX_MODIFIABLES.includes(jeu)) throw new Error('Jeu de données non modifiable : « ' + jeu + ' ».');
}

function verifierPoids(modif) {
  let taille = 0;
  try { taille = JSON.stringify(modif).length; } catch (_e) { taille = Infinity; }
  if (taille > POIDS_MAX) {
    throw new Error('Cet élément est trop lourd pour être enregistré (plus de 240 Ko). Une image collée dans un champ ? Donnez plutôt son adresse.');
  }
}

/* Une promesse, ou `repli` si elle tarde plus que `ms`. */
function avecDelai(promesse, ms, repli) {
  return new Promise((resoudre) => {
    const minuteur = setTimeout(() => resoudre(repli), ms);
    Promise.resolve(promesse).then(
      (v) => { clearTimeout(minuteur); resoudre(v); },
      () => { clearTimeout(minuteur); resoudre(null); });
  });
}

/* Une modification bien formée, et rien d'autre : ce qui arrive de la base
   partagée a été écrit par d'autres, c'est une donnée, pas une consigne. */
function normaliser(brut) {
  if (!brut || typeof brut !== 'object') return null;
  const type = texte(brut.type);
  const id = texte(brut.id);
  const op = brut.op === 'suppr' ? 'suppr' : (brut.op === 'maj' ? 'maj' : '');
  if (!type || !id || !op) return null;
  const donnees = (brut.donnees && typeof brut.donnees === 'object' && !Array.isArray(brut.donnees)) ? brut.donnees : null;
  if (op === 'maj' && !donnees) return null;
  return { type, id, op, donnees, le: texte(brut.le), par: texte(brut.par) || null };
}

/* Une entrée de journal bien formée : des textes, bornés. Ce qui revient
   de la base partagée est une donnée, jamais une consigne. */
function entreeJournal(brut, le, par) {
  const b = (brut && typeof brut === 'object') ? brut : {};
  const borne = (v, n) => texte(v).slice(0, n);
  return {
    le: borne(b.le || le, 40),
    par: borne(b.par || par, 200),
    rubrique: borne(b.rubrique, 60) || 'Autres',
    pole: borne(b.pole, 60),
    action: borne(b.action, 20) || 'Modification',
    element: borne(b.element, 200),
    detail: borne(b.detail, 3000)
  };
}

/* -------------------------------------------------------------------------
   2. Les deux magasins
   ------------------------------------------------------------------------- */

function magasinNavigateur() {
  const lireTout = (jeu) => {
    try {
      const brut = localStorage.getItem(PREFIXE_LOCAL + jeu);
      const objet = brut ? JSON.parse(brut) : {};
      return (objet && typeof objet === 'object') ? objet : {};
    } catch (_e) { return {}; }
  };
  const ecrireTout = (jeu, objet) => {
    try { localStorage.setItem(PREFIXE_LOCAL + jeu, JSON.stringify(objet)); }
    catch (_e) { throw new Error('Ce navigateur refuse d’enregistrer (stockage plein ou navigation privée).'); }
  };
  let disponible = true;
  try { const t = PREFIXE_LOCAL + 'essai'; localStorage.setItem(t, '1'); localStorage.removeItem(t); }
  catch (_e) { disponible = false; }

  return {
    mode: 'navigateur',
    base: () => null,
    hote: null,
    identite: null,
    peutEcrire: disponible,
    auteur: null,
    async lire(jeu) {
      verifierJeu(jeu);
      return Object.values(lireTout(jeu)).map(normaliser).filter(Boolean);
    },
    async poser(jeu, modif) {
      verifierJeu(jeu);
      const m = normaliser(modif);
      if (!m) throw new Error('Modification illisible.');
      verifierPoids(m);
      const tout = lireTout(jeu);
      tout[cleDocument(m.type, m.id)] = m;
      ecrireTout(jeu, tout);
      if (modif.journal) {
        try {
          const liste = lireJournal();
          liste.unshift(entreeJournal(modif.journal, m.le || new Date().toISOString(), m.par));
          localStorage.setItem(CLE_JOURNAL_LOCAL, JSON.stringify(liste.slice(0, JOURNAL_MAX)));
        } catch (_e) { /* le journal ne fait jamais échouer un enregistrement */ }
      }
    },
    async retirer(jeu, type, id) {
      verifierJeu(jeu);
      const tout = lireTout(jeu);
      delete tout[cleDocument(type, id)];
      ecrireTout(jeu, tout);
    },
    async journal() { return lireJournal(); }
  };
}

function lireJournal() {
  try {
    const brut = JSON.parse(localStorage.getItem(CLE_JOURNAL_LOCAL) || '[]');
    return Array.isArray(brut) ? brut.map((e) => entreeJournal(e)) : [];
  } catch (_e) { return []; }
}

function magasinPartage(db, peutEcrire, auteur) {
  const collection = (jeu) => db.collection(nomCollection(jeu));
  /* Une écriture refusée par les règles (lecteur, commentateur) rejette
     « invalid_argument » : on le traduit, une fois, en français. */
  const traduire = (e) => {
    const code = e && e.code;
    if (code === 'invalid_argument') return new Error('Vous pouvez lire ce site mais pas le modifier : demandez l’accès « Peut modifier » à son propriétaire.');
    if (code === 'quota_exceeded') return new Error('La base du site est pleine : retirez d’anciennes modifications avant d’en ajouter.');
    if (code === 'revoked') return new Error('L’accès à ce site vient de changer : rechargez la page.');
    return new Error('La modification n’a pas pu être enregistrée (' + (e && e.message ? e.message : 'réseau') + ').');
  };
  return {
    mode: 'partage',
    base: () => null,
    hote: 'claude',
    identite: null,
    peutEcrire,
    auteur,
    async lire(jeu) {
      verifierJeu(jeu);
      try {
        const instantane = await collection(jeu).get();
        return instantane.docs.map((d) => normaliser(d.data())).filter(Boolean);
      } catch (e) {
        if (typeof console !== 'undefined') console.warn('[magasin] lecture impossible de « ' + jeu + ' » :', e && (e.code || e.message));
        return [];
      }
    },
    async poser(jeu, modif) {
      verifierJeu(jeu);
      const m = normaliser(modif);
      if (!m) throw new Error('Modification illisible.');
      verifierPoids(m);
      try { await collection(jeu).doc(cleDocument(m.type, m.id)).set(m); }
      catch (e) { throw traduire(e); }
      if (modif.journal) {
        const entree = entreeJournal(modif.journal, m.le || new Date().toISOString(), m.par);
        const cle = cleDocument('journal', entree.le + '-' + Math.random().toString(36).slice(2, 8));
        try { await db.collection('journal').doc(cle).set(entree); }
        catch (e) { if (typeof console !== 'undefined') console.warn('[magasin] journal non écrit :', e && (e.code || e.message)); }
      }
    },
    async retirer(jeu, type, id) {
      verifierJeu(jeu);
      try { await collection(jeu).doc(cleDocument(type, id)).delete(); }
      catch (e) { throw traduire(e); }
    },
    async journal() {
      const instantane = await db.collection('journal').orderBy('le', 'desc').limit(JOURNAL_MAX).get();
      return instantane.docs.map((d) => entreeJournal(d.data()));
    }
  };
}

/* Un appel au serveur Apps Script, en promesse, borné dans le temps. */
function appelerGoogle(run, fonction, args, delai) {
  return new Promise((resoudre, rejeter) => {
    let fini = false;
    const minuteur = setTimeout(() => {
      if (fini) return;
      fini = true;
      rejeter(new Error('Le serveur du site ne répond pas : réessayez dans un instant.'));
    }, delai || 30000);
    try {
      run
        .withSuccessHandler((r) => { if (fini) return; fini = true; clearTimeout(minuteur); resoudre(r); })
        .withFailureHandler((e) => { if (fini) return; fini = true; clearTimeout(minuteur); rejeter(new Error((e && e.message) || String(e))); })[fonction](...args);
    } catch (e) {
      fini = true;
      clearTimeout(minuteur);
      rejeter(e);
    }
  });
}

/* Le premier appel au serveur, partagé par les pages pendant une minute :
   dans le fichier autonome, chaque page est un cadre neuf ; sans ce
   partage, chaque clic dans la barre referait l'aller-retour. Une
   écriture l'oublie aussitôt : la page suivante relit tout. */
const DUREE_PARTAGE = 60000;

function hoteDuPartage() {
  try { if (window.parent && window.parent !== window && window.parent.google) return window.parent; } catch (_e) { /* cadre étranger */ }
  return window;
}

function demarrerGoogle(run) {
  const hote = hoteDuPartage();
  const memo = hote.__ETII_DEMARRAGE;
  if (memo && Date.now() - memo.t < DUREE_PARTAGE) return memo.p;
  const p = appelerGoogle(run, 'etiiDemarrer', [], 20000);
  hote.__ETII_DEMARRAGE = { t: Date.now(), p };
  p.catch(() => { hote.__ETII_DEMARRAGE = null; });
  return p;
}

function oublierDemarrage() {
  try { hoteDuPartage().__ETII_DEMARRAGE = null; } catch (_e) { /* rien à oublier */ }
}

/* Le serveur Apps Script dit, en un seul appel, qui est connecté, s'il
   peut modifier, et toutes les modifications de tous les jeux. La page
   les garde pour son chargement, et tient sa copie à jour à chaque
   écriture : pas d'aller-retour de plus. */
function magasinGoogle(run, depart) {
  const parJeu = new Map();
  const modifs = (depart && typeof depart.modifications === 'object' && depart.modifications) || {};
  for (const jeu of JEUX_MODIFIABLES) {
    const liste = Array.isArray(modifs[jeu]) ? modifs[jeu] : [];
    const table = new Map();
    for (const brut of liste) {
      const m = normaliser(brut);
      if (m) table.set(cleDocument(m.type, m.id), m);
    }
    parJeu.set(jeu, table);
  }
  const identite = texte(depart && depart.email) || null;
  /* Les listes tenues dans une autre feuille (les documents) : le site les
     prend pour base, facettes recalculées sur ce qu'elles contiennent. */
  const bases = {};
  const docs = depart && depart.bases && Array.isArray(depart.bases.documents) ? depart.bases.documents : null;
  if (docs) bases.documents = { facettes: facettesDepuis(docs), documents: docs, source: 'feuille' };
  if (depart && depart.basesErreur && typeof console !== 'undefined') console.warn('[magasin] ' + depart.basesErreur);
  /* Le serveur a le dernier mot : il vérifie lui-même l'adresse à chaque
     écriture. Ce drapeau ne sert qu'à montrer, ou non, le bouton. */
  const traduire = (e) => {
    const message = (e && e.message) || '';
    if (/NON_AUTORISE/.test(message)) return new Error('Vous pouvez lire ce site mais pas le modifier : demandez à être ajouté aux éditeurs.');
    return new Error('La modification n’a pas pu être enregistrée (' + (message || 'réseau') + ').');
  };
  return {
    mode: 'partage',
    base: (jeu) => (bases[jeu] ? JSON.parse(JSON.stringify(bases[jeu])) : null),
    hote: 'google',
    identite,
    peutEcrire: depart && depart.peutModifier === true,
    auteur: identite,
    async lire(jeu) {
      verifierJeu(jeu);
      return [...parJeu.get(jeu).values()];
    },
    async poser(jeu, modif) {
      verifierJeu(jeu);
      const m = normaliser(modif);
      if (!m) throw new Error('Modification illisible.');
      verifierPoids(m);
      let retour;
      const envoi = modif.journal ? Object.assign({}, m, { journal: entreeJournal(modif.journal) }) : m;
      try { retour = await appelerGoogle(run, 'etiiPoser', [jeu, envoi]); }
      catch (e) { throw traduire(e); }
      oublierDemarrage();
      parJeu.get(jeu).set(cleDocument(m.type, m.id), normaliser(Object.assign({}, m, retour || {})) || m);
    },
    async retirer(jeu, type, id) {
      verifierJeu(jeu);
      try { await appelerGoogle(run, 'etiiRetirer', [jeu, texte(type), texte(id)]); }
      catch (e) { throw traduire(e); }
      oublierDemarrage();
      parJeu.get(jeu).delete(cleDocument(type, id));
    },
    async journal() {
      let lignes;
      try { lignes = await appelerGoogle(run, 'etiiJournal', [300]); }
      catch (e) { throw traduire(e); }
      return (Array.isArray(lignes) ? lignes : []).map((e) => entreeJournal(e));
    }
  };
}

/* Les valeurs des menus de la recherche documentaire, tirées des
   documents eux-mêmes : une feuille externe ne déclare pas ses facettes. */
function facettesDepuis(documents) {
  const valeurs = (champ) => [...new Set(documents.flatMap((d) => {
    const v = d && d[champ];
    return (Array.isArray(v) ? v : [v]).map(texte).filter(Boolean);
  }))].sort((a, b) => a.localeCompare(b, 'fr'));
  return { types: valeurs('type'), metiers: valeurs('metier'), porteurs: valeurs('porteur'), perimetres: valeurs('perimetre'), poles: valeurs('pole') };
}

/* Le runtime est là mais ne répond pas : lecture des fichiers seuls. */
function magasinMuet() {
  const refuser = async () => { throw new Error('Le site ne joint pas sa base : rechargez la page pour modifier.'); };
  return {
    mode: 'indisponible',
    base: () => null,
    hote: null,
    identite: null,
    peutEcrire: false,
    auteur: null,
    async lire(jeu) { verifierJeu(jeu); return []; },
    poser: refuser,
    retirer: refuser,
    async journal() { return []; }
  };
}

/* -------------------------------------------------------------------------
   3. L'ouverture, une seule fois par page
   ------------------------------------------------------------------------- */

let ouverture = null;

/**
 * Le magasin de cette page : la base partagée quand la page publiée en a
 * une, ce navigateur sinon. La promesse est mémoïsée.
 * @returns {Promise<object>}
 */
export function ouvrirMagasin() {
  if (ouverture) return ouverture;
  ouverture = (async () => {
    /* Servi par Google : le serveur dit tout d'un coup. S'il ne répond pas,
       la page reste lisible sur ses fichiers, sans édition. */
    const run = trouverAppsScript();
    if (run) {
      try { return magasinGoogle(run, await demarrerGoogle(run)); }
      catch (e) {
        if (typeof console !== 'undefined') console.warn('[magasin] serveur Google injoignable :', e && e.message);
        return magasinMuet();
      }
    }
    const runtime = trouverRuntime();
    if (!runtime) return magasinNavigateur();
    const MUET = {};
    let db = null;
    try { db = await avecDelai(runtime.use('db'), DELAI_RUNTIME, MUET); } catch (_e) { db = null; }
    if (db === MUET) return magasinMuet();
    /* Une page publiée sans base : chacun modifie dans son navigateur, et
       le bandeau du mode édition le dit. */
    if (!db) return magasinNavigateur();
    let user = null;
    try { user = await avecDelai(runtime.use('user'), DELAI_RUNTIME, null); } catch (_e) { user = null; }
    /* Le runtime dit si ce visiteur peut écrire. « Je ne sais pas » (null)
       n'est pas « non » : on laisse la main, et une écriture refusée dira
       le reste. */
    let peut = null;
    try { peut = user ? await avecDelai(user.can('data.write'), DELAI_RUNTIME, null) : null; } catch (_e) { peut = null; }
    let auteur = null;
    try { auteur = user ? await avecDelai(user.id(), DELAI_RUNTIME, null) : null; } catch (_e) { auteur = null; }
    return magasinPartage(db, peut !== false, auteur);
  })();
  return ouverture;
}

/** Pour les tests : oublie le magasin ouvert. */
export function oublierMagasin() { ouverture = null; }

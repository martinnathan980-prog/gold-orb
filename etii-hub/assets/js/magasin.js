/* =========================================================================
   ETII Hub — Le magasin des modifications

   Tout ce qu'on change dans le site — une communication, un rendez-vous,
   un porteur, une personne, une question, un document — est une
   MODIFICATION posée par-dessus les fichiers de assets/data/. Ce module
   les garde, et rien d'autre : il ne sait pas ce qu'est un porteur.

   Deux endroits possibles, choisis une fois pour toutes au chargement :

   - « partage » : la page est ouverte depuis son lien claude.ai. Elle a
     alors une base de données à elle, partagée par tous ceux qui l'ouvrent
     (capacité `db` du runtime). Une modification y est vue par tout le
     monde au chargement suivant. Qui peut écrire, c'est le menu de partage
     de la page qui le dit : l'éditeur (« Peut modifier ») écrit, le
     lecteur lit.

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
     Magasin.peutEcrire              booléen
     Magasin.lire(jeu)               -> Promise<Modification[]>
     Magasin.poser(jeu, modif)       -> Promise<void>
     Magasin.retirer(jeu, type, id)  -> Promise<void>   (annule la modification)
   ========================================================================= */

const PREFIXE_LOCAL = 'etii:modifications:';

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
    },
    async retirer(jeu, type, id) {
      verifierJeu(jeu);
      const tout = lireTout(jeu);
      delete tout[cleDocument(type, id)];
      ecrireTout(jeu, tout);
    }
  };
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
    },
    async retirer(jeu, type, id) {
      verifierJeu(jeu);
      try { await collection(jeu).doc(cleDocument(type, id)).delete(); }
      catch (e) { throw traduire(e); }
    }
  };
}

/* Le runtime est là mais ne répond pas : lecture des fichiers seuls. */
function magasinMuet() {
  const refuser = async () => { throw new Error('Le site ne joint pas sa base : rechargez la page pour modifier.'); };
  return {
    mode: 'indisponible',
    peutEcrire: false,
    auteur: null,
    async lire(jeu) { verifierJeu(jeu); return []; },
    poser: refuser,
    retirer: refuser
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

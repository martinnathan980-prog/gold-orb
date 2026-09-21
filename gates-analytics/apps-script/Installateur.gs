/**
 * L'INSTALLATEUR — à coller une seule fois, puis à lancer.
 *
 * Le tableau de bord tient en quatre fichiers, dont un de 222 Ko : personne
 * ne recopie cela à la main. Cet installateur le fait pour vous : il demande
 * à Google d'aller chercher les fichiers sur le dépôt public et de les écrire
 * dans ce projet.
 *
 * C'est GOOGLE qui télécharge, depuis ses propres serveurs — pas votre PC.
 * Le réseau de l'entreprise n'est donc pas concerné : même si le dépôt est
 * bloqué depuis votre poste, l'installation passe.
 *
 * MARCHE À SUIVRE
 *   1. Dans le classeur : Extensions → Apps Script.
 *   2. Coller ce fichier (⊕ → Script, l'appeler « Installateur »).
 *   3. Paramètres du projet (⚙) → cocher « Afficher le fichier manifeste
 *      appsscript.json », puis remplacer le contenu de appsscript.json par
 *      celui donné plus bas, dans le commentaire MANIFESTE.
 *   4. Ouvrir https://script.google.com/home/usersettings et activer
 *      « API Google Apps Script ».
 *   5. Revenir ici, choisir la fonction « installer » et cliquer Exécuter.
 *      Autoriser quand Google le demande.
 *   6. Recharger le classeur : le menu « Suivi FWD » apparaît.
 *
 * MANIFESTE — le contenu exact à mettre dans appsscript.json :
 *
 *   {
 *     "timeZone": "Europe/Paris",
 *     "dependencies": {},
 *     "exceptionLogging": "STACKDRIVER",
 *     "runtimeVersion": "V8",
 *     "oauthScopes": [
 *       "https://www.googleapis.com/auth/spreadsheets.currentonly",
 *       "https://www.googleapis.com/auth/script.container.ui",
 *       "https://www.googleapis.com/auth/script.scriptapp",
 *       "https://www.googleapis.com/auth/script.external_request",
 *       "https://www.googleapis.com/auth/script.projects"
 *     ]
 *   }
 *
 * Pour mettre à jour plus tard : relancer « installer ». Rien d'autre.
 */

/** Le dépôt public où le code est publié. */
const DEPOT = 'https://raw.githubusercontent.com/martinnathan980-prog/gold-orb/'
            + 'claude/javascript-gzip-base64-decoder-v0yr1m/gates-analytics/';

/** Les quatre fichiers du tableau de bord : nom dans le projet, fichier du dépôt, nature. */
const FICHIERS = [
  { nom: 'Code',       source: 'Code.gs',         type: 'SERVER_JS' },
  { nom: 'Index',      source: 'Index.html',      type: 'HTML' },
  { nom: 'Styles',     source: 'Styles.html',     type: 'HTML' },
  { nom: 'Javascript', source: 'Javascript.html', type: 'HTML' }
];

const PROJETS = 'https://script.googleapis.com/v1/projects/';


/**
 * Installe ou met à jour le tableau de bord. C'est la seule fonction à lancer.
 */
function installer() {
  const dire = [];
  const jeton = ScriptApp.getOAuthToken();
  const projet = ScriptApp.getScriptId();

  dire.push('1. Lecture du projet actuel…');
  const actuel = lireLeProjet(projet, jeton);
  dire.push('   ' + actuel.files.length + ' fichier(s) déjà présent(s) : '
            + actuel.files.map(function (f) { return f.name; }).join(', '));

  // Le piège : un projet neuf contient déjà un fichier « Code ». Si c'est là
  // qu'on a collé l'installateur, il serait écrasé par le vrai serveur au
  // milieu de son propre travail.
  const moi = trouverLInstallateur(actuel.files);
  const cibles0 = FICHIERS.map(function (f) { return f.nom; });
  if (moi && cibles0.indexOf(moi.name) !== -1) {
    throw new Error(
      'Cet installateur est dans un fichier nommé « ' + moi.name + ' », qui est justement\n'
      + 'un des fichiers à installer : il s\'effacerait lui-même.\n\n'
      + 'Le remède : ⊕ → Script, nommer le nouveau fichier « Installateur », y coller\n'
      + 'ce code, vider le fichier « ' + moi.name +' », et relancer.');
  }

  dire.push('2. Téléchargement du code depuis le dépôt…');
  const telecharges = FICHIERS.map(function (fichier) {
    const contenu = telecharger(DEPOT + fichier.source);
    dire.push('   ' + fichier.source + ' — ' + Math.round(contenu.length / 1024) + ' Ko');
    return { name: fichier.nom, type: fichier.type, source: contenu };
  });

  dire.push('3. Écriture dans le projet…');
  // On réécrit les quatre fichiers du tableau de bord, et on garde tout le
  // reste tel quel : le manifeste, cet installateur, et tout fichier que vous
  // auriez ajouté. L'API réécrit le projet entier — ne rien oublier est donc
  // la seule chose qui compte ici.
  const cibles = FICHIERS.map(function (f) { return f.nom; });
  const gardes = actuel.files.filter(function (f) { return cibles.indexOf(f.name) === -1; });
  const ecrits = gardes.concat(telecharges);
  ecrireLeProjet(projet, jeton, ecrits);
  dire.push('   écrits : ' + telecharges.map(function (f) { return f.name; }).join(', '));
  dire.push('   gardés : ' + gardes.map(function (f) { return f.name; }).join(', '));

  dire.push('');
  dire.push('TERMINÉ. Il reste deux gestes :');
  dire.push('  · recharger le classeur (F5) — le menu « Suivi FWD » apparaîtra ;');
  dire.push('  · la première ouverture demandera une autorisation : accepter.');
  const rapport = dire.join('\n');
  Logger.log(rapport);
  try {
    SpreadsheetApp.getUi().alert('Installation du Suivi FWD', rapport, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    /* Lancé depuis l'éditeur, sans classeur ouvert : le journal suffit. */
  }
  return rapport;
}


/**
 * Retire l'installateur et ses permissions, une fois l'installation faite.
 * Facultatif : à ne lancer que si l'on ne compte plus mettre à jour d'ici.
 */
function retirerLInstallateur() {
  const jeton = ScriptApp.getOAuthToken();
  const projet = ScriptApp.getScriptId();
  const actuel = lireLeProjet(projet, jeton);
  const moi = trouverLInstallateur(actuel.files);
  const manifeste = actuel.files.filter(function (f) { return f.name === 'appsscript'; })[0];
  if (manifeste) {
    const contenu = JSON.parse(manifeste.source);
    delete contenu.oauthScopes;         // Apps Script les redéduira du code restant
    manifeste.source = JSON.stringify(contenu, null, 2);
  }
  const restants = actuel.files.filter(function (f) { return !moi || f.name !== moi.name; });
  ecrireLeProjet(projet, jeton, restants);
  const rapport = 'L\'installateur a été retiré. Pour mettre à jour plus tard, il faudra le '
                + 'recoller et remettre les permissions du manifeste.';
  Logger.log(rapport);
  return rapport;
}


function trouverLInstallateur(fichiers) {
  for (let i = 0; i < fichiers.length; i++) {
    if (fichiers[i].type === 'SERVER_JS' && fichiers[i].source &&
        fichiers[i].source.indexOf('const PROJETS =') !== -1) {
      return fichiers[i];
    }
  }
  return null;
}


/** Le contenu d'un fichier du dépôt, ou une erreur qui dit quoi faire. */
function telecharger(url) {
  const reponse = UrlFetchApp.fetch(url, { muteHttpExceptions: true, followRedirects: true });
  const code = reponse.getResponseCode();
  if (code === 200) {
    return reponse.getContentText();
  }
  if (code === 404) {
    throw new Error('Fichier introuvable sur le dépôt (404) : ' + url
      + '\nLa branche a peut-être changé de nom. Vérifier la constante DEPOT en haut du fichier.');
  }
  throw new Error('Le dépôt a répondu ' + code + ' pour ' + url
    + '\nSi cela se répète, passer au PLAN B : les fichiers à recopier sont dans votre Drive.');
}


/** Le projet Apps Script, tel qu'il est aujourd'hui. */
function lireLeProjet(projet, jeton) {
  const reponse = UrlFetchApp.fetch(PROJETS + projet + '/content', {
    headers: { Authorization: 'Bearer ' + jeton },
    muteHttpExceptions: true
  });
  verifierLaReponse(reponse, 'lire');
  return JSON.parse(reponse.getContentText());
}


/** Réécrit le projet avec exactement ces fichiers. */
function ecrireLeProjet(projet, jeton, fichiers) {
  const reponse = UrlFetchApp.fetch(PROJETS + projet + '/content', {
    method: 'put',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + jeton },
    payload: JSON.stringify({ files: fichiers }),
    muteHttpExceptions: true
  });
  verifierLaReponse(reponse, 'écrire');
}


/** Traduit en français ce que l'API répond quand elle refuse. */
function verifierLaReponse(reponse, geste) {
  const code = reponse.getResponseCode();
  if (code === 200) {
    return;
  }
  const corps = reponse.getContentText();
  if (code === 403 && corps.indexOf('Apps Script API') !== -1) {
    throw new Error(
      'L\'API Apps Script n\'est pas activée pour votre compte.\n\n'
      + 'Ouvrir https://script.google.com/home/usersettings et mettre\n'
      + '« API Google Apps Script » sur ACTIVÉ, puis relancer.\n\n'
      + 'Si l\'interrupteur est grisé, c\'est l\'administrateur qui l\'a fermé :\n'
      + 'passer au PLAN B (recopier les quatre fichiers à la main).');
  }
  if (code === 401) {
    throw new Error(
      'Autorisation refusée. Vérifier que appsscript.json contient bien les cinq\n'
      + 'permissions du commentaire MANIFESTE, puis relancer « installer » et\n'
      + 'accepter la demande d\'autorisation.');
  }
  if (code === 404) {
    throw new Error(
      'Le projet est introuvable par l\'API. C\'est presque toujours que l\'API\n'
      + 'Apps Script vient d\'être activée : attendre une minute et relancer.');
  }
  throw new Error('Impossible de ' + geste + ' le projet (code ' + code + ') :\n'
    + corps.substring(0, 400)
    + '\n\nSi cela persiste, passer au PLAN B (recopier les fichiers à la main).');
}

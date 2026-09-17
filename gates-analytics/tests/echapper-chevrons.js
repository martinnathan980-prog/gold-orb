/* Échappe « < » en « \x3C » dans les chaînes et les expressions régulières du
   JavaScript sorti — et nulle part ailleurs.

   Pourquoi : `Javascript.html` se transmet en pièce jointe pour être collé dans
   l'éditeur Apps Script. Bourré de `'<td class="…">'`, un .txt ressemble à du
   HTML, et une passerelle de messagerie d'entreprise le retient comme
   contrebande HTML. Découpé en trois, seule la partie qui ne contenait presque
   aucune balise est passée : c'est bien le contenu, pas la taille.

   En JavaScript, « \x3C » dans une chaîne EST le caractère « < » — le code
   tourne à l'identique. Après passage, le fichier ne contient plus une seule
   balise : plus rien à retenir. C'est aussi la parade classique au `</script>`
   littéral qui refermerait le bloc avant l'heure.

   L'analyse suit l'état du texte (chaîne, commentaire, expression régulière)
   plutôt que de remplacer à l'aveugle : un « < » d'opérateur échappé serait une
   erreur de syntaxe, et un « < » de comparaison laissé dans une chaîne
   laisserait une balise. */

const ECHAP = '\\x3C';

function motSuivant(src, i) {   // dernier caractère significatif avant i
  for (let j = i - 1; j >= 0; j--) if (!/\s/.test(src[j])) return src[j];
  return '';
}

function echapperChevrons(src) {
  let out = '', i = 0, n = 0;
  const N = src.length;
  while (i < N) {
    const c = src[i];
    // ---- chaîne simple ou double
    if (c === "'" || c === '"') {
      let j = i + 1, texte = c;
      while (j < N && src[j] !== c) {
        if (src[j] === '\\') { texte += src.slice(j, j + 2); j += 2; continue; }
        if (src[j] === '\n') break;             // chaîne non terminée : on rend tel quel
        if (src[j] === '<') { texte += ECHAP; n++; j++; continue; }
        texte += src[j]; j++;
      }
      if (j < N && src[j] === c) { out += texte + c; i = j + 1; continue; }
      out += c; i++; continue;
    }
    // ---- commentaire de ligne
    if (c === '/' && src[i + 1] === '/') {
      const fin = src.indexOf('\n', i);
      const j = fin === -1 ? N : fin;
      out += src.slice(i, j); i = j; continue;
    }
    // ---- commentaire de bloc
    if (c === '/' && src[i + 1] === '*') {
      const fin = src.indexOf('*/', i + 2);
      const j = fin === -1 ? N : fin + 2;
      out += src.slice(i, j); i = j; continue;
    }
    // ---- expression régulière (et non une division)
    if (c === '/') {
      const avant = motSuivant(src, i);
      const estRegex = avant === '' || !(/[\w$)\]]/.test(avant));
      if (estRegex) {
        let j = i + 1, texte = c, classe = false, ok = false;
        while (j < N) {
          const d = src[j];
          if (d === '\\') { texte += src.slice(j, j + 2); j += 2; continue; }
          if (d === '\n') break;                 // pas une regex : on rend tel quel
          if (d === '[') classe = true;
          else if (d === ']') classe = false;
          else if (d === '/' && !classe) { ok = true; break; }
          if (d === '<') { texte += ECHAP; n++; j++; continue; }
          texte += d; j++;
        }
        if (ok) { out += texte + '/'; i = j + 1; continue; }
      }
      out += c; i++; continue;
    }
    out += c; i++;
  }
  return { texte: out, remplacements: n };
}

module.exports = { echapperChevrons, ECHAP };

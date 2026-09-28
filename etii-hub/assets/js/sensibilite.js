/* =========================================================================
   ETII Hub — La sécurité d'un document : sa sensibilité, son contrôle export

   Le classeur des documents porte deux colonnes « Sécurité » :
   « Sensibilité » (Airbus green, amber, red…) et « Export Control »
   (« Not in Export Control List », ou une classification). Le site les
   montre en petites pastilles, là où l'on voit le document — la liste du
   pôle, la recherche — pour qu'on sache avant d'ouvrir, et avant de
   transmettre. Il ne les interprète pas au-delà : la couleur suit le mot,
   le texte reste celui du classeur.

   API :
     sensibilite(doc)      -> { texte, niveau } | null
                              niveau : 'vert' | 'ambre' | 'rouge' | 'neutre'
     controleExport(doc)   -> { texte } | null   (null : non soumis, ou vide)
     pastillesSecurite(doc, classe) -> HTMLElement | null
   ========================================================================= */

import { el } from './ui.js';

function texte(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function sansAccents(t) { return t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }

/** La sensibilité du document, en clair, et son niveau pour la couleur. */
export function sensibilite(doc) {
  const brut = texte(doc && doc.sensibilite);
  if (!brut) return null;
  const t = sansAccents(brut);
  const niveau = /\b(red|rouge)\b/.test(t) ? 'rouge'
    : /\b(amber|ambre|orange)\b/.test(t) ? 'ambre'
      : /\b(green|vert|verte)\b/.test(t) ? 'vert' : 'neutre';
  /* « Airbus amber » se lit « Amber » : le nom de l'entreprise va de soi. */
  const court = brut.replace(/^airbus\s+/i, '');
  return { texte: court.charAt(0).toUpperCase() + court.slice(1), niveau, complet: brut };
}

/** Le contrôle export, s'il s'applique : null quand le document n'y est pas soumis. */
export function controleExport(doc) {
  const brut = texte(doc && doc.exportControl);
  if (!brut) return null;
  const t = sansAccents(brut);
  if (/\bnot\b|\bnon\b|\bno\b|\baucun|\bn\/a\b|^-+$|^none$|pas soumis|hors liste/.test(t)) return null;
  return { texte: brut };
}

/** Les pastilles : sensibilité, puis contrôle export s'il y a lieu. */
export function pastillesSecurite(doc, classe) {
  const s = sensibilite(doc);
  const e = controleExport(doc);
  if (!s && !e) return null;
  return el('span', { class: ['securite', classe || null] },
    s ? el('span', { class: 'securite__pastille', dataset: { niveau: s.niveau }, title: 'Sensibilité : ' + s.complet }, s.texte) : null,
    e ? el('span', { class: 'securite__pastille securite__pastille--export', title: 'Export Control : ' + e.texte }, 'Export control') : null);
}

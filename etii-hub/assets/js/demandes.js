/* =========================================================================
   ETII Hub — « Interroger un expert » : où part une question

   Une question posée depuis le site (la FAQ, la FAQ d'un pôle) part là où
   vivent les modifications du site (magasin.js) :
     - servi par Google : une ligne en haut de l'onglet « Questions aux
       experts » de la feuille du site, avec la date, l'adresse de la
       personne, son pôle et le statut « À traiter ». Les administrateurs
       la suivent dans la feuille ;
     - ouvert depuis son lien claude.ai : la base partagée de la page ;
     - ailleurs (fichier ouvert en local, serveur de test) : nulle part —
       la question reste dans ce navigateur, et le site le dit.
   ========================================================================= */

import { ouvrirMagasin } from './magasin.js';

/**
 * Les questions partent-elles vers les administrateurs ? (Sinon, elles
 * restent dans ce navigateur.)
 * @returns {Promise<boolean>}
 */
export async function demandesPartagees() {
  try {
    const m = await ouvrirMagasin();
    return m.mode === 'partage' && typeof m.demander === 'function';
  } catch (_e) { return false; }
}

/**
 * Envoie une question aux administrateurs, si le site est partagé.
 * @param {{question: string, contexte?: string, pole?: string}} demande
 * @returns {Promise<boolean>}  true : envoyée ; false : restée dans ce navigateur
 */
export async function envoyerDemande(demande) {
  const m = await ouvrirMagasin();
  if (m.mode !== 'partage' || typeof m.demander !== 'function') return false;
  await m.demander({
    question: String(demande.question || '').trim(),
    contexte: String(demande.contexte || '').trim(),
    pole: String(demande.pole || '').trim()
  });
  return true;
}

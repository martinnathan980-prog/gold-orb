"""Exécution des étapes d'un scénario sur la page (Playwright).

Sélecteurs acceptés dans `selecteur` :
    "#id", ".classe", "input[name=x]"      CSS classique
    "texte=Enregistrer"                     élément contenant ce texte
    "texte_exact=Enregistrer"               texte exact
    "libelle=Numéro de plan"                champ associé à ce libellé (<label>)
    "placeholder=jj/mm/aaaa"                champ avec cet indice
    "titre=Fermer"                          attribut title
    "role=button:Enregistrer"               rôle ARIA + nom accessible
    "test=btn-save"                         data-testid
    "xpath=//button[1]"                     XPath (syntaxe Playwright)
Paramètre `nieme: 2` pour prendre le 2e élément correspondant.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, expect

from . import symboles as S
from .console import lire_ligne
from .erreurs import ArretDemande, ErreurEtape, ErreurGabarit, LigneIgnoree, NavigateurFerme
from .excel import ClasseurSuivi, csv_vers_excel
from .gabarit import est_vrai, formater, rendre_structure
from .navigateur import Navigateur, navigateur_ferme, premiere_ligne
from .carte import chemin_vers, est_repere, selecteur as selecteur_carte
from .scenario import Etape, Scenario, masquer_secrets

journal = logging.getLogger("autoweb")

PREFIXES = ("texte=", "texte_exact=", "libelle=", "placeholder=", "titre=", "role=", "test=", "alt=")
# « role=button:Exporter [CSV] » : le nom peut contenir n'importe quoi, y compris des crochets.
MOTIF_ROLE = re.compile(r"^role=([a-zA-Z]+)(?::(.*))?$", re.S)


# Pauses « connexion » écrites par les versions précédentes : rejouées comme une attente de connexion
# qui continue toute seule dès que l'outil s'affiche (au lieu d'attendre Entrée dans la fenêtre noire)
MOTIF_PAUSE_CONNEXION = re.compile(r"(bien connect|connectez-vous|connexion|se connecter|log ?in|sign ?in)", re.IGNORECASE)
# Actions dont la cible montre que l'outil est affiché (on est connecté)
ACTIONS_A_CIBLE = ("remplir", "taper", "effacer", "cliquer", "choisir", "cocher", "decocher", "touche", "survoler",
                   "televerser", "lire", "telecharger", "attendre")

# Bandeau du robot dans la page pendant une attente : le message, « Continuer », « Arrêter ».
# Sans innerHTML ni attribut style (pages protégées : Google, Microsoft...).
JS_BANDEAU_ATTENTE = r"""
([message, boutons]) => {
  if (window !== window.top || !document.documentElement) return '';
  let b = document.getElementById('__autoweb_attente');
  if (!b) {
    b = document.createElement('div');
    b.id = '__autoweb_attente';
    b.setAttribute('data-autoweb', '1');
    b.style.cssText = 'position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:2147483647;' +
      'background:#1e3a8a;color:#fff;font:600 15px/1.4 system-ui,-apple-system,Arial;padding:12px 16px;' +
      'border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.45);max-width:620px;text-align:center';
    const t = document.createElement('div');
    t.className = '__autoweb_message';
    b.appendChild(t);
    const zone = document.createElement('div');
    zone.className = '__autoweb_zone';
    zone.style.cssText = 'margin-top:8px;display:flex;gap:10px;justify-content:center';
    for (const [libelle, reponse, fond] of [['Continuer ▸', 'continuer', '#16a34a'], ['Arrêter', 'stop', '#b91c1c']]) {
      const x = document.createElement('button');
      x.type = 'button';
      x.textContent = libelle;
      x.style.cssText = 'all:initial;cursor:pointer;background:' + fond + ';color:#fff;font:600 14px system-ui,Arial;' +
        'padding:6px 14px;border-radius:6px';
      x.addEventListener('click', ev => { ev.preventDefault(); ev.stopPropagation(); window.__autoweb_reponse = reponse; }, true);
      zone.appendChild(x);
    }
    b.appendChild(zone);
    (document.body || document.documentElement).appendChild(b);
  }
  b.querySelector('.__autoweb_message').textContent = message;
  b.querySelector('.__autoweb_zone').style.display = boutons ? 'flex' : 'none';
  const r = window.__autoweb_reponse || '';
  window.__autoweb_reponse = '';
  return r;
}
"""
JS_RETIRER_BANDEAU = "() => { const b = document.getElementById('__autoweb_attente'); if (b) b.remove(); }"


# Bandeau orange qui prévient sans bloquer (8 secondes), dans la fenêtre du robot
JS_PREVENIR = r"""
(message) => {
  if (window !== window.top || !document.documentElement) return;
  let zone = document.getElementById('__autoweb_avis');
  if (!zone) {
    zone = document.createElement('div');
    zone.id = '__autoweb_avis';
    zone.setAttribute('data-autoweb', '1');
    zone.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:2147483647;' +
      'display:flex;flex-direction:column;gap:6px;max-width:640px;pointer-events:none';
    (document.body || document.documentElement).appendChild(zone);
  }
  const b = document.createElement('div');
  b.style.cssText = 'background:#b45309;color:#fff;font:600 14px/1.4 system-ui,-apple-system,Arial;padding:10px 14px;' +
    'border-radius:8px;box-shadow:0 3px 14px rgba(0,0,0,.4)';
  b.textContent = '⚠ ' + message;
  zone.appendChild(b);
  setTimeout(() => b.remove(), 8000);
}
"""
# Fenêtre d'alerte ouverte dans la page (boîte de dialogue, fenêtre modale) : son texte, ou ""
JS_TEXTE_ALERTE = r"""
() => {
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
                     const r = e.getBoundingClientRect(); return r.width * r.height > 0; };
  const sel = '[role=alertdialog], [role=dialog], dialog[open], .modal.show, .modal.in, .ui-dialog, .k-window, ' +
              '.x-window, .swal2-popup, .bootbox, .MuiDialog-paper, .ant-modal';
  for (const e of document.querySelectorAll(sel)) {
    if (!vis(e) || e.closest('[data-autoweb]')) continue;
    const t = (e.innerText || '').replace(/\s+/g, ' ').trim();
    if (t) return t.slice(0, 400);
  }
  return '';
}
"""
# Lignes d'un tableau (entêtes exclues, « Aucun résultat » exclu) ; une ligne contient-elle ce texte ?
JS_TABLEAU = r"""
(t, [colonne, texte]) => {
  const norm = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const lignes = Array.from(t.querySelectorAll('tr, [role=row]')).filter(r => r.closest('table, [role=grid], [role=table]') === t ||
                                                                              t.tagName !== 'TABLE');
  let entetes = Array.from(t.querySelectorAll('thead th, [role=columnheader]'));
  let premiere = null;
  if (!entetes.length && lignes.length) {
    const c = Array.from(lignes[0].children);
    if (c.length > 1 && c.every(x => x.tagName === 'TH')) { entetes = c; premiere = lignes[0]; }
  }
  let rang = -1;
  if (colonne) {
    rang = entetes.findIndex(h => norm(h.innerText || h.textContent).includes(norm(colonne)));
    if (rang < 0) return { lignes: -1, trouve: false, erreur: 'colonne' };
  }
  const donnees = lignes.filter(r => r !== premiere && !r.closest('thead') &&
    Array.from(r.children).some(c => c.tagName === 'TD' || ['cell', 'gridcell'].includes(c.getAttribute('role'))));
  const vraies = donnees.filter(r => !(r.children.length === 1 &&
    /aucun|aucune|no data|no record|no result|vide|empty|pas de/i.test(r.innerText || '')));
  let trouve = false;
  if (texte) {
    for (const r of vraies) {
      const cible = rang >= 0 ? r.children[rang] : r;
      if (cible && norm(cible.innerText || cible.textContent).includes(norm(texte))) { trouve = true; break; }
    }
  }
  return { lignes: vraies.length, trouve: trouve };
}
"""
# Élément caché dans un sous-menu fermé : où poser la souris pour l'ouvrir ? Sur l'entrée de menu
# visible la plus proche (« GATES »), sur son propre libellé, pas sur le sous-menu qu'elle contient.
JS_ENTREE_A_SURVOLER = r"""
e => {
  const vis = n => { const s = getComputedStyle(n); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = n.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  if (vis(e)) return null;
  let n = e.parentElement, haut = 1;
  while (n && !vis(n)) { n = n.parentElement; haut++; }
  if (!n || n === document.body || n === document.documentElement || haut > 12) return { haut: 0, enfant: -2 };
  const enfants = Array.from(n.children);
  const enfant = enfants.findIndex(c => !c.contains(e) && vis(c) && (c.innerText || '').trim() &&
    !c.matches('ul, ol, [role="menu"], [role="group"], [role="listbox"], .dropdown-menu, .submenu, .sub-menu'));
  return { haut: haut, enfant: enfant };
}
"""


def nom_fichier_sur(texte: str) -> str:
    """Retire les caractères interdits dans un nom de fichier Windows."""
    nom = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", texte).strip(" .")
    return nom or "fichier"


class Executeur:
    """Exécute des étapes pour UNE ligne (ou pour les sections avant/apres)."""

    def __init__(
        self,
        navigateur: Navigateur,
        scenario: Scenario,
        contexte: Dict[str, Any],
        classeur: Optional[ClasseurSuivi] = None,
        numero_ligne: Optional[int] = None,
        interactif: bool = True,
    ) -> None:
        self.nav = navigateur
        self.scenario = scenario
        self.contexte = contexte
        self.classeur = classeur
        self.numero_ligne = numero_ligne
        self.interactif = interactif
        self.dossier = scenario.dossier
        self.portees: List[Any] = []  # pile de FrameLocator quand on est dans un iframe
        self.derniere_etape: Optional[str] = None

    # ------------------------------------------------------------------ accès page
    @property
    def page(self):
        return self.nav.page_courante()

    @property
    def portee(self):
        return self.portees[-1] if self.portees else self.page

    def localiser(self, selecteur: Any, args: Optional[Dict[str, Any]] = None):
        args = args or {}
        sel = str(selecteur).strip()
        if not sel:
            raise ErreurEtape("sélecteur vide.")
        if est_repere(sel):  # « carte=E5/C1 » : l'élément noté pendant la carte, retrouvé sur ce poste
            sel = selecteur_carte(sel)
        portee = self.portee
        exact = bool(args.get("exact", False))
        if sel.startswith("texte="):
            loc = portee.get_by_text(sel[len("texte="):], exact=exact)
        elif sel.startswith("texte_exact="):
            texte = sel[len("texte_exact="):]
            # <li>GATES<ul>Données MK1...</ul></li> : le texte complet du li n'est pas « GATES »,
            # mais son propre texte l'est (entrée de menu qui contient son sous-menu)
            loc = portee.get_by_text(texte, exact=True).or_(
                portee.locator("text=" + json.dumps(texte.strip(), ensure_ascii=False)))
        elif sel.startswith("libelle="):
            loc = portee.get_by_label(sel[len("libelle="):], exact=exact)
        elif sel.startswith("placeholder="):
            loc = portee.get_by_placeholder(sel[len("placeholder="):], exact=exact)
        elif sel.startswith("titre="):
            loc = portee.get_by_title(sel[len("titre="):], exact=exact)
        elif sel.startswith("alt="):
            loc = portee.get_by_alt_text(sel[len("alt="):], exact=exact)
        elif sel.startswith("test="):
            loc = portee.get_by_test_id(sel[len("test="):])
        elif MOTIF_ROLE.match(sel):
            m = MOTIF_ROLE.match(sel)
            role, nom = m.group(1), (m.group(2) or "").strip()
            if nom:
                # exact par défaut : « Valider » ne doit pas attraper « Valider et fermer »
                loc = portee.get_by_role(role, name=nom, exact=bool(args.get("exact", True)))
            else:
                loc = portee.get_by_role(role)
        else:
            loc = portee.locator(sel)
        if args.get("nieme") is not None:
            try:
                n = int(args["nieme"])
            except (TypeError, ValueError):
                raise ErreurEtape(f"« nieme » doit être un entier (reçu {args['nieme']!r}).")
            loc = loc.nth(n - 1 if n > 0 else n)
        elif args.get("premier"):
            loc = loc.first
        elif args.get("dernier"):
            loc = loc.last
        return loc

    def _chemin(self, chemin: Any, sous_dossier: Optional[str] = None) -> Path:
        # %USERPROFILE%\Desktop, ~/Documents... sont acceptés
        p = Path(os.path.expandvars(os.path.expanduser(str(chemin).strip())))
        if not p.is_absolute():
            base = self.dossier / sous_dossier if sous_dossier else self.dossier
            p = base / p
        return p

    def _delai(self, args: Dict[str, Any], defaut: Optional[int]) -> Optional[int]:
        for cle in ("delai", "delai_max", "timeout"):
            if args.get(cle) is not None:
                try:
                    return int(args[cle])
                except (TypeError, ValueError):
                    raise ErreurEtape(f"« {cle} » doit être un nombre de millisecondes.")
        return defaut

    # ------------------------------------------------------------------ boucle
    def executer(self, etapes: List[Etape]) -> None:
        for etape in etapes:
            self.executer_etape(etape)

    def executer_etape(self, etape: Etape) -> None:
        try:
            args = rendre_structure(etape.args, self.contexte)
        except ErreurGabarit as e:
            raise ErreurEtape(f"{etape.position} : {e}")
        libelle = etape.nom or Etape(etape.action, masquer_secrets(args, etape)).resume()
        self.derniere_etape = libelle
        journal.info("    %s %s", S.FLECHE, libelle)
        methode: Optional[Callable] = getattr(self, "act_" + etape.action, None)
        if methode is None:
            raise ErreurEtape(f"{etape.position} : action non implémentée « {etape.action} ».")
        try:
            methode(args, etape.delai_max)
        except (LigneIgnoree, ArretDemande, NavigateurFerme):
            raise
        except ErreurEtape as e:
            self._gerer_echec(etape, libelle, str(e))
        except PlaywrightTimeout as e:
            delai = self._delai(args, etape.delai_max) or self.scenario.navigateur.delai_max
            self._gerer_echec(
                etape, libelle,
                f"délai dépassé ({delai} ms) : élément introuvable, masqué ou page trop lente. "
                f"Détail : {premiere_ligne(e)}",
            )
        except AssertionError as e:
            self._gerer_echec(etape, libelle, premiere_ligne(e) or "vérification échouée")
        except PlaywrightError as e:
            if navigateur_ferme(e):
                raise NavigateurFerme("Le navigateur (ou l'onglet) a été fermé pendant le traitement.")
            self._gerer_echec(etape, libelle, premiere_ligne(e))
        except (OSError, ValueError, TypeError) as e:
            self._gerer_echec(etape, libelle, f"{e.__class__.__name__} : {e}")
        self._verifier_alertes()

    def _verifier_alertes(self) -> None:
        """Mode « prudent » : une fenêtre du portail qui n'était pas attendue a été refusée (rien n'a été
        validé). On prévient et on laisse cette ligne (ce plan) de côté : on passe à la suivante."""
        alertes = getattr(self.nav, "alertes", None)
        if not alertes:
            return
        message = re.sub(r"\s+", " ", alertes[0]).strip()[:200]
        alertes.clear()
        self.act_prevenir({"message": f"Fenêtre du portail refusée par le robot (rien n'a été validé) : « {message} »"}, None)
        raise LigneIgnoree(f"fenêtre inattendue du portail, refusée : « {message} »")

    def _gerer_echec(self, etape: Etape, libelle: str, detail: str) -> None:
        self._verifier_alertes()  # l'étape a échoué parce qu'une fenêtre du portail a été refusée
        message = f"{etape.position} « {libelle} » : {detail}"
        if etape.optionnel:
            journal.warning("      (étape optionnelle ignorée) %s", message)
            return
        raise ErreurEtape(message)

    # ------------------------------------------------------------------ navigation
    def act_aller(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        if args.get("fichier"):
            url = self._chemin(args["fichier"]).resolve().as_uri()
        else:
            url = str(args["url"]).strip()
            if url.lower().startswith("fichier:"):
                url = self._chemin(url[len("fichier:"):].strip()).resolve().as_uri()
            elif not re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I):
                url = "https://" + url
        attendre = str(args.get("attendre_chargement", "load"))
        self.page.goto(url, wait_until=attendre, timeout=self._delai(args, delai))

    def act_ecran(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        """Revient sur un écran de la carte (« E5 ») en rejouant le chemin noté pendant l'exploration :
        menus, onglets, recherche. Chaque clic est vérifié : si l'écran a changé, rien n'est cliqué."""
        repere = str(args.get("repere") or "")
        pas_liste = chemin_vers(repere)
        if not pas_liste:
            raise ErreurEtape(f"aucun chemin noté pour {repere}.")
        timeout = self._delai(args, delai) or self.scenario.navigateur.delai_max
        for pas in pas_liste:
            page = self.page
            genre = pas.get("type")
            if genre == "aller":
                page.goto(pas["url"], wait_until="domcontentloaded", timeout=timeout)
            elif genre == "chercher":
                from .explorateur import champ_identique

                champ = page.locator(pas["selecteur"]).first
                champ.wait_for(state="visible", timeout=timeout)
                if pas.get("controle") and not champ_identique(champ, pas["controle"]):
                    raise ErreurEtape("l'écran a changé depuis la carte (champ de recherche différent) : rien n'a été "
                                      "rempli. Refaites la carte (menu, choix 8), puis relancez la tâche.")
                champ.fill(str(pas.get("valeur") or ""), timeout=timeout)
                if pas.get("bouton"):
                    self._clic_verifie(pas["bouton"], pas.get("attendu") or {}, timeout)
                else:
                    champ.press("Enter", timeout=timeout)
            else:
                self._clic_verifie(pas.get("selecteur") or "", pas.get("attendu") or {}, timeout)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
            except PlaywrightTimeout:
                pass
            self.page.wait_for_timeout(400)

    def _clic_verifie(self, selecteur: str, attendu: Dict[str, Any], timeout: Optional[int]) -> None:
        """Clic sur l'élément noté dans la carte, seulement s'il est toujours le même (texte, rôle...)."""
        from .explorateur import JS_CLIC

        fin = time.monotonic() + (timeout or 15000) / 1000
        resultat = ""
        while time.monotonic() < fin:
            try:
                resultat = self.page.evaluate(JS_CLIC, [selecteur, attendu])
            except PlaywrightError as e:
                if "context was destroyed" in str(e) or "navigat" in str(e):
                    return  # le clic a changé de page
                raise
            if resultat == "ok":
                return
            self.page.wait_for_timeout(300)  # l'écran finit de s'afficher
        raise ErreurEtape(f"l'écran a changé depuis la carte ({resultat}) : rien n'a été cliqué. "
                          "Refaites la carte (menu, choix 8), puis relancez la tâche.")

    def act_recharger(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        self.page.reload(timeout=self._delai(args, delai))

    def act_retour(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        self.page.go_back(timeout=self._delai(args, delai))

    def act_attendre(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        timeout = self._delai(args, delai)
        if args.get("selecteur"):
            etat = str(args.get("etat", "visible")).lower()
            etats = {"visible": "visible", "cache": "hidden", "masque": "hidden", "hidden": "hidden",
                     "present": "attached", "attached": "attached", "absent": "detached", "detached": "detached"}
            if etat not in etats:
                raise ErreurEtape(f"« etat » inconnu : {etat}. Possibles : visible, cache, present, absent.")
            self.localiser(args["selecteur"], args).wait_for(state=etats[etat], timeout=timeout)
        if args.get("url"):
            self.page.wait_for_url(re.compile(re.escape(str(args["url"]))), timeout=timeout)
        if args.get("chargement"):
            etat = str(args["chargement"]).lower()
            etats_chargement = {"reseau": "networkidle", "networkidle": "networkidle", "dom": "domcontentloaded",
                                "domcontentloaded": "domcontentloaded", "load": "load", "complet": "load", "oui": "load"}
            self.page.wait_for_load_state(etats_chargement.get(etat, "load"), timeout=timeout)
        if args.get("ms") is not None:
            self.page.wait_for_timeout(float(args["ms"]))

    def act_patienter(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        self.page.wait_for_timeout(float(args["ms"]))

    # ------------------------------------------------------------------ saisie
    def _remplir_un(self, selecteur: str, valeur: Any, args: Dict[str, Any], delai: Optional[int]) -> None:
        texte = valeur if isinstance(valeur, str) else formater(valeur)
        loc = self.localiser(selecteur, args)
        timeout = self._delai(args, delai)
        if args.get("si_vide") and not texte:
            return
        loc.fill(texte, timeout=timeout)
        if args.get("appuyer"):
            loc.press(str(args["appuyer"]), timeout=timeout)
        if args.get("verifier"):
            valeur_lue = loc.input_value(timeout=timeout)
            if valeur_lue.strip() != texte.strip():
                raise ErreurEtape(f"le champ {selecteur} contient « {valeur_lue} » au lieu de « {texte} ».")

    def act_remplir(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        if "champs" in args:
            for selecteur, valeur in args["champs"].items():
                self._remplir_un(str(selecteur), valeur, args, delai)
        else:
            self._remplir_un(str(args["selecteur"]), args.get("valeur", ""), args, delai)

    def act_taper(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        loc = self.localiser(args["selecteur"], args)
        timeout = self._delai(args, delai)
        texte = args.get("valeur", "")
        texte = texte if isinstance(texte, str) else formater(texte)
        if args.get("effacer_avant", True):
            loc.fill("", timeout=timeout)
        vitesse = float(args.get("vitesse", 50))
        loc.press_sequentially(texte, delay=vitesse, timeout=timeout)
        if args.get("appuyer"):
            loc.press(str(args["appuyer"]), timeout=timeout)

    def act_effacer(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        self.localiser(args["selecteur"], args).fill("", timeout=self._delai(args, delai))

    def act_choisir(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        loc = self.localiser(args["selecteur"], args)
        timeout = self._delai(args, delai)
        if args.get("libelle") is not None:
            loc.select_option(label=str(args["libelle"]), timeout=timeout)
        elif args.get("index") is not None:
            loc.select_option(index=int(args["index"]), timeout=timeout)
        else:
            valeur = args.get("valeur")
            texte = valeur if isinstance(valeur, str) else formater(valeur)
            if not texte and args.get("si_vide", "ignorer") == "ignorer":
                journal.debug("      valeur vide : liste non modifiée")
                return
            # Playwright accepte indifféremment la valeur (value) ou le libellé de l'option
            loc.select_option(texte, timeout=timeout)

    def act_cocher(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        loc = self.localiser(args["selecteur"], args)
        etat = est_vrai(args["valeur"]) if "valeur" in args else True
        loc.set_checked(etat, timeout=self._delai(args, delai))

    def act_decocher(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        self.localiser(args["selecteur"], args).set_checked(False, timeout=self._delai(args, delai))

    def act_touche(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        touche = str(args["touche"])
        if args.get("selecteur"):
            self.localiser(args["selecteur"], args).press(touche, timeout=self._delai(args, delai))
        else:
            self.page.keyboard.press(touche)

    def act_televerser(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        fichiers = args["fichier"] if isinstance(args["fichier"], list) else [args["fichier"]]
        chemins = []
        for f in fichiers:
            p = self._chemin(f)
            if not p.exists():
                raise ErreurEtape(f"fichier à joindre introuvable : {p}")
            chemins.append(str(p))
        self.localiser(args["selecteur"], args).set_input_files(chemins, timeout=self._delai(args, delai))

    # ------------------------------------------------------------------ souris
    def act_cliquer(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        loc = self.localiser(args["selecteur"], args)
        timeout = self._delai(args, delai)
        if args.get("si_present"):
            try:
                loc.first.wait_for(state="visible", timeout=int(args.get("delai_presence", 2000)))
            except PlaywrightTimeout:
                journal.debug("      élément absent, clic ignoré : %s", args["selecteur"])
                return
        options = {
            "timeout": timeout,
            "button": str(args.get("bouton", "left")),
            "force": bool(args.get("forcer", False)),
        }
        modificateurs = (["ControlOrMeta"] if est_vrai(args.get("ctrl", False)) else []) + \
                        (["Shift"] if est_vrai(args.get("maj", False)) else [])
        if modificateurs:
            options["modifiers"] = modificateurs
        if not options["force"]:
            debut = time.monotonic()
            loc = self._pret_a_cliquer(loc, args, timeout)
            if timeout is not None:  # le temps déjà passé à chercher compte dans le délai
                options["timeout"] = max(2000, int(timeout - (time.monotonic() - debut) * 1000))
        if args.get("nouvel_onglet"):
            # tout nouvel onglet compte : window.open, lien « nouvel onglet », Ctrl+clic, clic molette
            with self.page.context.expect_page(timeout=timeout) as popup:
                loc.click(**options)
            nouvelle = popup.value
            nouvelle.wait_for_load_state("load", timeout=timeout)
            self.nav.utiliser_page(nouvelle)
            self.portees = []
        elif args.get("double"):
            loc.dblclick(**options)
        else:
            loc.click(**options)

    def act_survoler(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        timeout = self._delai(args, delai)
        loc = self._un_seul(self.localiser(args["selecteur"], args), args, timeout)
        if not loc.is_visible():
            self._ouvrir_menus(loc)
        loc.hover(timeout=timeout)

    def _un_seul(self, loc, args: Dict[str, Any], timeout: Optional[int]):
        """L'élément visé. S'il y en a plusieurs (même menu en double, version mobile cachée...),
        le seul qui est visible ; plusieurs visibles : le robot ne choisit pas au hasard."""
        loc.first.wait_for(state="attached", timeout=timeout)  # absent : « délai dépassé », comme avant
        nombre = loc.count()
        if nombre <= 1:
            return loc
        visibles = [loc.nth(i) for i in range(min(nombre, 20)) if loc.nth(i).is_visible()]
        if len(visibles) > 1:
            raise ErreurEtape(
                f"{len(visibles)} éléments visibles correspondent à « {args.get('selecteur')} » : le robot ne choisit "
                "pas au hasard. Ajoutez « premier: true » (ou « nieme: 2 ») à l'étape, ou réenregistrez la tâche.")
        return visibles[0] if visibles else loc.first

    def _pret_a_cliquer(self, loc, args: Dict[str, Any], timeout: Optional[int]):
        """Comme la main de l'utilisateur : si l'élément est dans un sous-menu fermé, le robot survole
        d'abord le menu (« GATES ») pour l'ouvrir, puis clique. Jamais de clic sur un élément caché."""
        loc = self._un_seul(loc, args, timeout)
        try:
            loc.click(trial=True, timeout=1500)  # vérifie seulement qu'un clic est possible, ne clique pas
            return loc
        except PlaywrightTimeout:
            pass
        if not loc.is_visible() and self._ouvrir_menus(loc):
            journal.info("      sous-menu ouvert en survolant le menu")
        return loc

    def _ouvrir_menus(self, loc) -> bool:
        """Survole, de haut en bas, les entrées de menu qui cachent l'élément (4 niveaux au plus)."""
        deja = set()
        for _ in range(4):
            try:
                point = loc.evaluate(JS_ENTREE_A_SURVOLER)
            except PlaywrightError:
                return False
            if not point:
                return True  # visible
            if point["enfant"] == -2:
                return False  # rien de visible au-dessus : ce n'est pas un menu fermé
            cle = (point["haut"], point["enfant"])
            if cle in deja:
                return False  # le survol n'a rien ouvert
            deja.add(cle)
            entree = loc.locator("xpath=" + "/".join([".."] * point["haut"]))
            if point["enfant"] >= 0:
                entree = entree.locator(f"xpath=./*[{point['enfant'] + 1}]")
            try:
                entree.hover(timeout=2000)
                loc.wait_for(state="visible", timeout=800)
                return True
            except PlaywrightTimeout:
                continue
            except PlaywrightError:
                return False
        return False

    # ------------------------------------------------------------------ lecture / vérification
    def _texte_element(self, loc, args: Dict[str, Any], timeout: Optional[int]) -> str:
        attribut = str(args.get("attribut", "auto")).lower()
        if attribut in ("auto", "texte", "text"):
            loc.wait_for(state="attached", timeout=timeout)
            balise = loc.evaluate("e => e.tagName.toLowerCase()")
            if balise in ("input", "textarea", "select") and attribut == "auto":
                return loc.input_value(timeout=timeout)
            return loc.inner_text(timeout=timeout)
        if attribut in ("valeur", "value"):
            return loc.input_value(timeout=timeout)
        if attribut == "html":
            return loc.inner_html(timeout=timeout)
        valeur = loc.get_attribute(attribut, timeout=timeout)
        return valeur if valeur is not None else ""

    def act_lire(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        loc = self.localiser(args["selecteur"], args)
        texte = self._texte_element(loc, args, self._delai(args, delai)).strip()
        if args.get("regex"):
            m = re.search(str(args["regex"]), texte, re.S)
            if m:
                texte = m.group(1) if m.groups() else m.group(0)
            elif args.get("regex_obligatoire", False):
                raise ErreurEtape(f"le texte lu « {texte[:80]} » ne correspond pas à l'expression {args['regex']}.")
        vers = str(args["vers"])
        self.contexte[vers] = texte
        journal.info("      lu « %s » -> %s", texte[:80], vers)
        if self.classeur is not None and self.numero_ligne is not None and not args.get("variable_seulement"):
            self.classeur.ecrire(self.numero_ligne, vers, texte)

    def act_verifier(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        timeout = self._delai(args, delai)
        if args.get("texte_page") is not None:
            attendu = str(args["texte_page"])
            # use_inner_text : seul le texte VISIBLE compte (un message masqué de la
            # ligne précédente ne doit pas faire passer la vérification).
            expect(self.page.locator("body")).to_contain_text(
                attendu, timeout=timeout, ignore_case=True, use_inner_text=True
            )
            return
        loc = self.localiser(args["selecteur"], args)
        if args.get("absent"):
            expect(loc).to_have_count(0, timeout=timeout)
            return
        if args.get("cache"):
            expect(loc.first).to_be_hidden(timeout=timeout)
            return
        expect(loc.first).to_be_visible(timeout=timeout)
        if args.get("contient") is not None:
            expect(loc.first).to_contain_text(
                str(args["contient"]), timeout=timeout,
                ignore_case=not args.get("exact", False), use_inner_text=True,
            )
        if args.get("egal") is not None:
            expect(loc.first).to_have_text(str(args["egal"]), timeout=timeout, use_inner_text=True)
        if args.get("valeur") is not None:
            expect(loc.first).to_have_value(str(args["valeur"]), timeout=timeout)
        if args.get("coche") is not None:
            expect(loc.first).to_be_checked(checked=est_vrai(args["coche"]), timeout=timeout)

    def act_verifier_url(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        timeout = self._delai(args, delai)
        if args.get("egal") is not None:
            self.page.wait_for_url(str(args["egal"]), timeout=timeout)
        else:
            self.page.wait_for_url(re.compile(re.escape(str(args["contient"]))), timeout=timeout)

    # ------------------------------------------------------------------ divers
    def act_capture(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        chemin = self._chemin(args["chemin"])  # relatif au dossier du scénario
        if chemin.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            chemin = chemin.with_suffix(".png")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(chemin), full_page=bool(args.get("page_entiere", False)))
        journal.info("      capture -> %s", chemin)

    def act_telecharger(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        """Clique et enregistre le fichier téléchargé.

        vers            : dossier (finit par / ou sans extension) ou chemin complet du fichier
        renommer        : nouveau nom (sans extension : celle du téléchargement est conservée)
        convertir_excel : true -> un .csv/.txt est aussi converti en .xlsx (chemin final = le .xlsx)
        vers_colonne    : colonne Excel où écrire le chemin du fichier obtenu
        """
        timeout = self._delai(args, delai)
        loc = self.localiser(args["cliquer"], args)
        telechargement = self._cliquer_et_attendre_fichier(loc, timeout or self.nav.config.delai_max)
        suggere = telechargement.suggested_filename or "telechargement"
        if args.get("vers"):
            cible = self._chemin(args["vers"])
            if str(args["vers"]).rstrip().endswith(("/", "\\")) or cible.suffix == "" or cible.is_dir():
                cible = cible / suggere
        else:
            cible = self.nav._dossier_telechargements() / suggere
        if args.get("renommer"):
            nom = nom_fichier_sur(str(args["renommer"]))
            if not Path(nom).suffix:
                nom += cible.suffix
            cible = cible.with_name(nom)
        cible.parent.mkdir(parents=True, exist_ok=True)
        telechargement.save_as(str(cible))
        journal.info("      téléchargé -> %s", cible)
        resultat = cible
        if est_vrai(args.get("convertir_excel", False)) and cible.suffix.lower() in (".csv", ".txt", ".tsv"):
            resultat = csv_vers_excel(cible)
            journal.info("      converti en Excel -> %s", resultat)
        self.contexte["fichier_telecharge"] = str(resultat)
        if args.get("vers_colonne") and self.classeur is not None and self.numero_ligne is not None:
            self.classeur.ecrire(self.numero_ligne, str(args["vers_colonne"]), str(resultat))

    def _cliquer_et_attendre_fichier(self, loc: Any, timeout: int) -> Any:
        """Le fichier peut arriver dans l'onglet courant ou dans un onglet que le clic ouvre
        (page « préparation du fichier... ») : on écoute tous les onglets."""
        contexte = self.page.context
        recus: List[Any] = []
        ecoutees = list(contexte.pages)

        def recevoir(telechargement: Any) -> None:
            recus.append(telechargement)

        for page in ecoutees:
            page.on("download", recevoir)

        def nouvelle(page: Any) -> None:
            ecoutees.append(page)
            page.on("download", recevoir)

        contexte.on("page", nouvelle)
        try:
            loc.click(timeout=timeout)
            fin = time.monotonic() + timeout / 1000
            while not recus and time.monotonic() < fin:
                self.page.wait_for_timeout(200)
        finally:
            for page in ecoutees:
                try:
                    page.remove_listener("download", recevoir)
                except Exception:  # noqa: BLE001
                    pass
            try:
                contexte.remove_listener("page", nouvelle)
            except Exception:  # noqa: BLE001
                pass
        if not recus:
            raise ErreurEtape(f"aucun téléchargement n'a démarré dans les {timeout // 1000} s après le clic.")
        return recus[0]

    def act_journal(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        journal.info("      %s", args["message"])

    def act_pause(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        message = str(args.get("message") or "Action manuelle requise")
        if MOTIF_PAUSE_CONNEXION.search(message):
            # « Vérifiez que vous êtes bien connecté... » (tâches des versions précédentes) : le robot
            # n'attend que si l'outil n'est pas encore affiché, et repart tout seul dès qu'il l'est
            self.act_connexion({}, delai)
            return
        if self.interactif and sys.stdin is not None and sys.stdin.isatty():
            self._attendre_utilisateur(message)
        else:
            journal.warning("      pause ignorée (mode non interactif) : %s", message)

    def _attendre_utilisateur(self, message: str, cible: Any = None, duree_max_s: float = 1800.0) -> str:
        """Attend l'utilisateur : Entrée ici, ou « Continuer » dans le bandeau bleu de la page, ou (si
        `cible` est donnée) l'apparition de cet élément. Renvoie « continuer » ou « vu »."""
        from .console import touche_entree_disponible, vider_clavier

        print(f"\n{S.PAUSE}  {message}", flush=True)
        print("   Dans la fenêtre Chrome du robot : bouton « Continuer ▸ » en bas de la page"
              + (", ou le robot continue tout seul quand votre outil s'affiche." if cible is not None else "."), flush=True)
        print("   (Ou ici : Entrée pour continuer, « stop » puis Entrée pour arrêter.)", flush=True)
        vider_clavier()
        fin = time.monotonic() + duree_max_s
        with self.nav.pause_manuelle():
            while time.monotonic() < fin:
                reponse = ""
                try:
                    reponse = self.page.evaluate(JS_BANDEAU_ATTENTE, [message, True]) or ""
                except Exception:  # noqa: BLE001 - page en cours de chargement : bandeau reposé au tour suivant
                    pass
                if reponse == "stop":
                    raise ArretDemande("arrêt demandé par l'utilisateur pendant une pause.")
                if reponse == "continuer":
                    break
                if cible is not None and self._cible_visible(cible):
                    reponse = "vu"
                    break
                if touche_entree_disponible():
                    ligne = (lire_ligne(self.nav.pomper) or "").strip().lower()
                    if ligne in ("stop", "arreter", "arrêter", "q", "quit"):
                        raise ArretDemande("arrêt demandé par l'utilisateur pendant une pause.")
                    reponse = "continuer"
                    break
                self.nav.pomper(400)
            else:
                raise ErreurEtape(f"personne n'a répondu pendant {int(duree_max_s // 60)} minutes : arrêt.")
        try:
            self.page.evaluate(JS_RETIRER_BANDEAU)
        except Exception:  # noqa: BLE001
            pass
        return reponse

    def _cible_visible(self, cible: Any) -> bool:
        try:
            if isinstance(cible, tuple):  # (cadre, sélecteur) : l'outil est dans un iframe
                return self.page.locator(cible[0]).first.is_visible()
            return self.localiser(cible).first.is_visible()
        except Exception:  # noqa: BLE001 - sélecteur illisible sur cette page, page qui change
            return False

    def _premiere_cible(self) -> Any:
        """Premier élément que la tâche touche (champ, bouton) : s'il est affiché, l'outil est là."""
        def chercher(etapes: List[Etape]) -> Any:
            for etape in etapes:
                if etape.action == "cadre":
                    return (str(etape.args.get("selecteur") or ""), None) if etape.args.get("selecteur") else None
                if etape.action == "si":
                    continue
                if etape.action not in ACTIONS_A_CIBLE:
                    continue
                try:
                    args = rendre_structure(etape.args, self.contexte)
                except ErreurGabarit:
                    continue
                sel = args.get("selecteur") or args.get("cliquer")
                if not sel and isinstance(args.get("champs"), dict) and args["champs"]:
                    sel = next(iter(args["champs"]))
                if sel and not isinstance(sel, (dict, list)) and "{{" not in str(sel):
                    return str(sel)
            return None

        return chercher(self.scenario.etapes)

    def act_connexion(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        """Connexion au début d'une tâche : si l'outil est déjà affiché, le robot continue tout de
        suite ; sinon il attend que l'utilisateur se connecte dans SA fenêtre (bandeau bleu), et
        repart tout seul dès que l'outil s'affiche."""
        cible = args.get("selecteur") or self._premiere_cible()
        if isinstance(cible, str) and "{{" in cible:
            cible = None
        attente_s = (self._delai(args, None) or 8000) / 1000
        fin = time.monotonic() + attente_s
        while cible is not None and time.monotonic() < fin:  # déjà connecté ? (la page finit de s'afficher)
            if self._cible_visible(cible):
                journal.info("      Connexion : déjà connecté, le robot continue.")
                return
            self.nav.pomper(300)
        if not (self.interactif and sys.stdin is not None and sys.stdin.isatty()):
            if cible is None:
                journal.warning("      connexion : rien à vérifier (mode non interactif).")
            else:
                journal.warning("      connexion : l'outil n'est pas encore affiché (mode non interactif) ; le robot continue.")
            return
        message = str(args.get("message") or "Connectez-vous dans cette fenêtre si votre outil le demande.")
        reponse = self._attendre_utilisateur(
            message + (" Le robot continuera tout seul dès que votre outil s'affiche." if cible is not None else ""),
            cible=cible, duree_max_s=float(args.get("minutes", 20)) * 60)
        journal.info("      Connexion %s : le robot continue.", "vue" if reponse == "vu" else "confirmée")

    def act_inspecter(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        if not self.nav.visible:
            journal.warning("      inspecter : navigateur invisible, étape ignorée.")
            return
        journal.info("      Inspecteur Playwright ouvert : cliquez sur « Resume » (▶) pour continuer.")
        self.page.pause()

    def act_executer_js(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        resultat = self.page.evaluate(str(args["script"]))
        if args.get("vers"):
            vers = str(args["vers"])
            texte = resultat if isinstance(resultat, str) else ("" if resultat is None else str(resultat))
            self.contexte[vers] = texte
            if self.classeur is not None and self.numero_ligne is not None:
                self.classeur.ecrire(self.numero_ligne, vers, texte)

    # ------------------------------------------------------------------ structure
    def _condition(self, args: Dict[str, Any]) -> bool:
        delai = int(args.get("delai", 2000))
        resultats: List[bool] = []

        def existe(sel: Any, etat: str) -> bool:
            try:
                self.localiser(sel, args).first.wait_for(state=etat, timeout=delai)
                return True
            except PlaywrightTimeout:
                return False

        if args.get("present") is not None:
            resultats.append(existe(args["present"], "attached"))
        if args.get("absent") is not None:
            resultats.append(not existe(args["absent"], "attached"))
        if args.get("visible") is not None:
            resultats.append(existe(args["visible"], "visible"))
        if args.get("cache") is not None:
            resultats.append(not existe(args["cache"], "visible"))
        if "alerte" in args:
            try:
                ouverte = bool(self.page.evaluate(JS_TEXTE_ALERTE))
            except Exception:  # noqa: BLE001
                ouverte = False
            resultats.append(ouverte == est_vrai(args["alerte"]))
        if args.get("tableau") is not None:
            resultats.append(self._condition_tableau(args, delai))
        if "valeur" in args and args.get("tableau") is None:
            valeur = args["valeur"]
            texte = valeur if isinstance(valeur, str) else formater(valeur)
            if "egal" in args:
                resultats.append(texte.strip().casefold() == str(args["egal"]).strip().casefold())
            if "different" in args:
                resultats.append(texte.strip().casefold() != str(args["different"]).strip().casefold())
            if "contient" in args:
                resultats.append(str(args["contient"]).casefold() in texte.casefold())
            if "vide" in args:
                resultats.append((texte.strip() == "") == est_vrai(args["vide"]))
            if "non_vide" in args:
                resultats.append((texte.strip() != "") == est_vrai(args["non_vide"]))
            if "vrai" in args:
                resultats.append(est_vrai(texte) == est_vrai(args["vrai"]))
            if "faux" in args:
                resultats.append((not est_vrai(texte)) == est_vrai(args["faux"]))
            if not any(k in args for k in ("egal", "different", "contient", "vide", "non_vide", "vrai", "faux")):
                resultats.append(est_vrai(texte))
        if not resultats:
            raise ErreurEtape("condition « si » sans critère évaluable.")
        return all(resultats)

    def _condition_tableau(self, args: Dict[str, Any], delai: int) -> bool:
        """« tableau: X, colonne: Statut, ligne_contient: Validé » : une ligne (dans cette colonne) contient
        ce texte ? « tableau: X, vide: true » : le tableau n'a aucune ligne ? Un tableau ou une colonne
        introuvable est une ERREUR (jamais « rien trouvé, on continue ») : on ne supprime pas à l'aveugle."""
        loc = self.localiser(args["tableau"], {k: v for k, v in args.items() if k in ("nieme", "premier", "dernier")}).first
        try:
            loc.wait_for(state="attached", timeout=delai)
        except PlaywrightTimeout:
            raise ErreurEtape(f"tableau introuvable ({args['tableau']}) : rien n'est fait pour cette ligne.")
        colonne = str(args.get("colonne") or "")
        texte = str(args.get("ligne_contient") or "")
        mesure = loc.evaluate(JS_TABLEAU, [colonne, texte])
        if mesure.get("erreur") == "colonne":
            raise ErreurEtape(f"colonne « {colonne} » introuvable dans le tableau : rien n'est fait pour cette ligne.")
        if "ligne_contient" in args:
            return bool(mesure.get("trouve"))
        if "vide" in args:
            return (mesure.get("lignes", 0) == 0) == est_vrai(args["vide"])
        if "non_vide" in args:
            return (mesure.get("lignes", 0) > 0) == est_vrai(args["non_vide"])
        return mesure.get("lignes", 0) > 0

    def act_prevenir(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        """Prévient sans bloquer : bandeau orange dans la fenêtre du robot, et ligne dans la fenêtre noire."""
        message = str(args.get("message") or "")
        journal.warning("   %s %s", S.ATTENTION, message)
        self.contexte["dernier_avertissement"] = message
        try:
            self.page.evaluate(JS_PREVENIR, message)
        except Exception:  # noqa: BLE001 - page en cours de chargement : le message est dans la fenêtre noire
            pass

    def act_lire_alerte(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        """Texte de la fenêtre d'alerte du portail (ou de la dernière question refusée) -> variable."""
        texte = ""
        try:
            texte = self.page.evaluate(JS_TEXTE_ALERTE) or ""
        except Exception:  # noqa: BLE001
            texte = ""
        texte = texte or getattr(self.nav, "derniere_alerte", "") or ""
        texte = re.sub(r"\s+", " ", texte).strip()[:300]
        vers = str(args["vers"])
        self.contexte[vers] = texte
        if self.classeur is not None and self.numero_ligne is not None:
            self.classeur.ecrire(self.numero_ligne, vers, texte)

    def act_repeter(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        """Répète les étapes tant que la condition est vraie (« tant qu'il reste une référence »)."""
        maximum = int(args.get("max", 50))
        condition = dict(args["tant_que"])
        for _ in range(maximum):
            if not self._condition(condition):
                return
            self.executer(args["etapes"])
        if self._condition(condition):
            raise ErreurEtape(f"« répéter » : la condition est toujours vraie après {maximum} tours : arrêt, par sécurité.")

    def act_si(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        verdict = self._condition(args)
        journal.info("      condition : %s", "vraie" if verdict else "fausse")
        branche = args.get("alors") if verdict else args.get("sinon")
        if branche:
            self.executer(branche)

    def act_cadre(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        cadre = self.portee.frame_locator(str(args["selecteur"]))
        self.portees.append(cadre)
        try:
            self.executer(args["etapes"])
        finally:
            # un clic « nouvel onglet » dans le cadre a déjà vidé les portées : ne rien retirer de plus
            if self.portees and self.portees[-1] is cadre:
                self.portees.pop()

    def act_onglet(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        # les onglets ouverts par Chrome lui-même ne comptent pas (« onglet: 2 » reste juste)
        pages = self.nav.pages_de_travail() or [p for p in self.page.context.pages if not p.is_closed()]
        index = args.get("index")
        if isinstance(index, int) or (isinstance(index, str) and index.strip().isdigit()):
            # l'onglet est peut-être encore en train de s'ouvrir : on lui laisse le délai habituel
            fin = time.monotonic() + (self._delai(args, delai) or self.nav.config.delai_max) / 1000
            while len(pages) < int(index) and time.monotonic() < fin:
                self.page.wait_for_timeout(200)
                pages = self.nav.pages_de_travail() or [p for p in self.page.context.pages if not p.is_closed()]
        cible = None
        if args.get("titre") is not None or args.get("url") is not None:
            for p in pages:
                if args.get("titre") is not None and str(args["titre"]).casefold() in p.title().casefold():
                    cible = p
                if args.get("url") is not None and str(args["url"]) in p.url:
                    cible = p
            if cible is None:
                raise ErreurEtape("aucun onglet ne correspond au titre/url demandé.")
        else:
            index = args.get("index")
            if isinstance(index, str) and index.strip().lower() in ("dernier", "last"):
                cible = pages[-1]
            elif isinstance(index, str) and index.strip().lower() in ("premier", "first"):
                cible = pages[0]
            else:
                try:
                    n = int(index)
                except (TypeError, ValueError):
                    raise ErreurEtape("« onglet » attend index (1, 2, dernier...), titre ou url.")
                if n < 1 or n > len(pages):
                    raise ErreurEtape(f"onglet {n} inexistant ({len(pages)} onglet(s) ouvert(s)).")
                cible = pages[n - 1]
        self.nav.utiliser_page(cible)
        self.portees = []

    def act_fermer_onglet(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        self.page.close()
        self.nav.page = None
        try:
            suivante = self.nav.page_courante()  # jamais un onglet ouvert par Chrome lui-même
        except NavigateurFerme:
            raise NavigateurFerme("dernier onglet fermé.")
        self.nav.utiliser_page(suivante)
        self.portees = []

    def act_ignorer(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        raise LigneIgnoree(str(args["message"]))

    def act_echouer(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        raise ErreurEtape(str(args["message"]))

    def act_arreter(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        raise ArretDemande(str(args["message"]))

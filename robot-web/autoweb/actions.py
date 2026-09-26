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

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, expect

from . import symboles as S
from .console import lire_ligne
from .erreurs import ArretDemande, ErreurEtape, ErreurGabarit, LigneIgnoree, NavigateurFerme
from .excel import ClasseurSuivi, csv_vers_excel
from .gabarit import est_vrai, formater, rendre_structure
from .navigateur import Navigateur, navigateur_ferme, premiere_ligne
from .scenario import Etape, Scenario, masquer_secrets

journal = logging.getLogger("autoweb")

PREFIXES = ("texte=", "texte_exact=", "libelle=", "placeholder=", "titre=", "role=", "test=", "alt=")
# « role=button:Exporter [CSV] » : le nom peut contenir n'importe quoi, y compris des crochets.
MOTIF_ROLE = re.compile(r"^role=([a-zA-Z]+)(?::(.*))?$", re.S)


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
        portee = self.portee
        exact = bool(args.get("exact", False))
        if sel.startswith("texte="):
            loc = portee.get_by_text(sel[len("texte="):], exact=exact)
        elif sel.startswith("texte_exact="):
            loc = portee.get_by_text(sel[len("texte_exact="):], exact=True)
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

    def _gerer_echec(self, etape: Etape, libelle: str, detail: str) -> None:
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
        if args.get("nouvel_onglet"):
            with self.page.expect_popup(timeout=timeout) as popup:
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
        self.localiser(args["selecteur"], args).hover(timeout=self._delai(args, delai))

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
        with self.page.expect_download(timeout=timeout) as info:
            loc.click(timeout=timeout)
        telechargement = info.value
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

    def act_journal(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        journal.info("      %s", args["message"])

    def act_pause(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        message = str(args.get("message") or "Action manuelle requise")
        if self.interactif and sys.stdin is not None and sys.stdin.isatty():
            print(f"\n{S.PAUSE}  {message}\n   Appuyez sur Entrée pour continuer (ou tapez « stop » puis Entrée pour arrêter) : ", end="", flush=True)
            # le navigateur continue de tourner pendant l'attente : un onglet que Chrome
            # ouvrirait de lui-même est refermé au lieu de rester devant l'outil
            with self.nav.pause_manuelle():
                reponse = (lire_ligne(self.nav.pomper) or "").strip().lower()
            if reponse in ("stop", "arreter", "arrêter", "q", "quit"):
                raise ArretDemande("arrêt demandé par l'utilisateur pendant une pause.")
        else:
            journal.warning("      pause ignorée (mode non interactif) : %s", message)

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
        if "valeur" in args:
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
            self.portees.pop()

    def act_onglet(self, args: Dict[str, Any], delai: Optional[int]) -> None:
        # les onglets ouverts par Chrome lui-même ne comptent pas (« onglet: 2 » reste juste)
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

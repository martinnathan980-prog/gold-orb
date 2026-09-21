"""Relevé d'un écran : capture + inventaire des champs + brouillon de scénario.

Sert à décrire une application à laquelle Claude n'a pas accès : l'utilisateur
navigue jusqu'à l'écran voulu, le robot photographie la page et liste chaque
champ (libellé, id, name, type, options) avec un sélecteur proposé, puis
génère un brouillon de scénario YAML à compléter.

Attention : `page.html` et `capture.png` peuvent contenir des données métier ;
`champs.txt` et `brouillon.yaml` ne contiennent que la structure.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Error as PlaywrightError, Page

JS_INVENTAIRE = r"""
() => {
  const estVisible = e => {
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const libelle = e => {
    if (e.id) { try { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return l.innerText.trim(); } catch (err) {} }
    const p = e.closest('label'); if (p) return p.innerText.trim();
    const al = e.getAttribute('aria-label'); if (al) return al.trim();
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = document.getElementById(lb.split(' ')[0]); if (t) return t.innerText.trim(); }
    const prev = e.previousElementSibling;
    if (prev && ['LABEL', 'SPAN', 'TD', 'TH', 'DIV'].includes(prev.tagName) && prev.innerText && prev.innerText.trim().length < 60) return prev.innerText.trim();
    return '';
  };
  const out = [];
  const sel = 'input, select, textarea, button, a[href], [role=button], [role=textbox], [role=combobox], [role=checkbox], [contenteditable=true]';
  document.querySelectorAll(sel).forEach(e => {
    const tag = e.tagName.toLowerCase();
    const type = (e.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && type === 'hidden') return;
    const role = e.getAttribute('role') || '';
    const bouton = tag === 'button' || role === 'button' || (tag === 'input' && ['submit', 'button', 'reset', 'image'].includes(type));
    out.push({
      tag: tag, type: type, role: role,
      id: e.id || '', name: e.getAttribute('name') || '',
      placeholder: e.getAttribute('placeholder') || '',
      libelle: libelle(e).slice(0, 80),
      texte: (bouton || tag === 'a') ? ((e.innerText || e.value || e.getAttribute('title') || '').trim().replace(/\s+/g, ' ').slice(0, 80)) : '',
      bouton: bouton,
      visible: estVisible(e),
      desactive: !!e.disabled,
      testid: e.getAttribute('data-testid') || e.getAttribute('data-test') || e.getAttribute('data-qa') || '',
      classes: (typeof e.className === 'string') ? e.className.trim().replace(/\s+/g, ' ').slice(0, 80) : '',
      options: tag === 'select' ? Array.from(e.options).slice(0, 40).map(o => (o.value === o.text.trim() ? o.text.trim() : o.value + ' | ' + o.text.trim())) : [],
      href: tag === 'a' ? (e.getAttribute('href') || '').slice(0, 120) : '',
      valeur_actuelle: (tag === 'input' && !['password'].includes(type)) || tag === 'textarea' ? String(e.value || '').slice(0, 40) : ''
    });
  });
  return out;
}
"""

JS_SELECTEUR_IFRAME = """
e => e.id ? '#' + e.id
   : (e.name ? 'iframe[name="' + e.name + '"]'
   : 'iframe[src*="' + ((e.getAttribute('src') || '').split('/').pop() || '').slice(0, 40) + '"]')
"""


def _id_genere(identifiant: str) -> bool:
    """Vrai si l'id ressemble à un id généré (change à chaque chargement)."""
    return bool(re.search(r"[:]|\d{4,}|^[a-f0-9]{8,}$|__\d+", identifiant)) or len(identifiant) > 40


def _echapper(texte: str) -> str:
    return texte.replace("\\", "\\\\").replace('"', '\\"')


def selecteur_suggere(e: Dict[str, Any]) -> str:
    tag = e["tag"]
    if e["id"] and not _id_genere(e["id"]):
        if re.match(r"^[A-Za-z_][\w-]*$", e["id"]):
            return f"#{e['id']}"
        return f"[id=\"{_echapper(e['id'])}\"]"
    if e["testid"]:
        return f"test={e['testid']}"
    if e["name"]:
        return f"{tag}[name=\"{_echapper(e['name'])}\"]"
    if e["bouton"] and e["texte"]:
        return f"role=button:{e['texte']}"
    if tag == "a" and e["texte"]:
        return f"role=link:{e['texte']}"
    if e["libelle"] and tag in ("input", "select", "textarea"):
        return f"libelle={e['libelle']}"
    if e["placeholder"]:
        return f"placeholder={e['placeholder']}"
    if e["id"]:
        return f"#{e['id']}  (id probablement généré : vérifier)"
    return "(à préciser : envoyer la capture)"


def _description(e: Dict[str, Any]) -> str:
    genre = e["tag"]
    if e["tag"] == "input":
        genre = f"input {e['type'] or 'text'}"
    elif e["role"]:
        genre = f"{e['tag']} role={e['role']}"
    morceaux = [f"[{genre}]"]
    if e["libelle"]:
        morceaux.append(f"libellé « {e['libelle']} »")
    if e["texte"]:
        morceaux.append(f"texte « {e['texte']} »")
    if e["placeholder"]:
        morceaux.append(f"placeholder « {e['placeholder']} »")
    attrs = []
    if e["id"]:
        attrs.append(f"id={e['id']}")
    if e["name"]:
        attrs.append(f"name={e['name']}")
    if e["testid"]:
        attrs.append(f"data-testid={e['testid']}")
    if attrs:
        morceaux.append("(" + " ".join(attrs) + ")")
    if e["desactive"]:
        morceaux.append("DÉSACTIVÉ")
    return " ".join(morceaux)


def inventaire(page: Page) -> List[Dict[str, Any]]:
    """Inventaire des champs de la page et de ses iframes (clé 'cadre' = sélecteur de l'iframe)."""
    elements: List[Dict[str, Any]] = []
    for e in page.evaluate(JS_INVENTAIRE):
        e["cadre"] = ""
        elements.append(e)
    for cadre in page.frames:
        if cadre == page.main_frame:
            continue
        try:
            element_iframe = cadre.frame_element()
            selecteur_cadre = element_iframe.evaluate(JS_SELECTEUR_IFRAME)
            for e in cadre.evaluate(JS_INVENTAIRE):
                e["cadre"] = selecteur_cadre
                elements.append(e)
        except PlaywrightError:
            continue
    return elements


def _texte_inventaire(page: Page, elements: List[Dict[str, Any]]) -> str:
    lignes = [
        f"RELEVÉ DE PAGE — {page.title()}",
        f"URL   : {page.url}",
        f"Date  : {dt.datetime.now():%d/%m/%Y %H:%M}",
        "",
        "Sélecteurs proposés : à utiliser tels quels dans le scénario (remplir, cliquer, choisir...).",
        "",
    ]
    champs = [e for e in elements if not e["bouton"] and e["tag"] != "a"]
    boutons = [e for e in elements if e["bouton"]]
    liens = [e for e in elements if e["tag"] == "a" and not e["bouton"]]

    def bloc(titre: str, liste: List[Dict[str, Any]], avec_options: bool = False) -> None:
        lignes.append(f"== {titre} ({len(liste)}) ==")
        for e in liste:
            prefixe = "  " if e["visible"] else "  (masqué) "
            cadre = f" [dans l'iframe {e['cadre']}]" if e["cadre"] else ""
            lignes.append(f"{prefixe}{_description(e)}{cadre}")
            lignes.append(f"      -> sélecteur : {selecteur_suggere(e)}")
            if avec_options and e["options"]:
                lignes.append("      options : " + " ; ".join(e["options"]))
        lignes.append("")

    bloc("CHAMPS DE SAISIE", sorted(champs, key=lambda e: not e["visible"]), avec_options=True)
    bloc("BOUTONS", sorted(boutons, key=lambda e: not e["visible"]))
    if liens:
        bloc("LIENS (les 40 premiers)", [e for e in liens if e["visible"]][:40])
    cadres = sorted({e["cadre"] for e in elements if e["cadre"]})
    if cadres:
        lignes.append("== IFRAMES ==")
        lignes.extend(f"  {c}   (dans le scénario : - cadre: {{selecteur: \"{c}\", etapes: [...]}})" for c in cadres)
        lignes.append("")
    return "\n".join(lignes)


def _brouillon_yaml(page: Page, elements: List[Dict[str, Any]], nom: str) -> str:
    lignes = [
        f"# Brouillon généré par « autoweb releve » le {dt.datetime.now():%d/%m/%Y %H:%M}",
        "# Remplacez les {{Colonne ?}} par vos noms de colonnes Excel, supprimez les lignes inutiles,",
        "# et gardez la ligne « pause » tant que le scénario n'est pas validé.",
        f"nom: {nom}",
        "navigateur:",
        "  canal: chrome",
        f"  profil: profils/{re.sub(r'[^a-z0-9_-]+', '_', nom.lower()) or 'outil'}",
        "  visible: true",
        "excel:",
        "  fichier: suivi.xlsx",
        "  feuille: Suivi",
        "variables:",
        f"  url: \"{page.url}\"",
        "etapes:",
        "  - aller: \"{{url}}\"",
    ]
    visibles = [e for e in elements if e["visible"] and not e["desactive"]]
    cadres_vus = set()

    def etape_pour(e: Dict[str, Any], indent: str) -> List[str]:
        sel = selecteur_suggere(e)
        if sel.startswith("("):
            return []
        nom_col = e["libelle"] or e["placeholder"] or e["name"] or e["id"] or "Colonne ?"
        nom_col = nom_col.replace('"', "'").rstrip(" :*")
        if e["tag"] == "select":
            commentaire = ("   # options : " + " ; ".join(e["options"][:8])) if e["options"] else ""
            return [f"{indent}- choisir: {{selecteur: \"{_echapper(sel)}\", valeur: \"{{{{{nom_col} ?}}}}\"}}{commentaire}"]
        if e["tag"] == "input" and e["type"] in ("checkbox",) or e["role"] == "checkbox":
            return [f"{indent}- cocher: {{selecteur: \"{_echapper(sel)}\", valeur: \"{{{{{nom_col} ?}}}}\"}}"]
        if e["tag"] == "input" and e["type"] == "radio":
            return [f"{indent}- cliquer: \"{_echapper(sel)}\"   # bouton radio « {nom_col} »"]
        if e["tag"] == "input" and e["type"] == "file":
            return [f"{indent}- televerser: {{selecteur: \"{_echapper(sel)}\", fichier: \"{{{{Fichier ?}}}}\"}}"]
        if e["tag"] in ("input", "textarea") or e["role"] in ("textbox", "combobox") or e["tag"] == "div":
            if e["type"] == "password":
                return [f"{indent}- remplir: {{selecteur: \"{_echapper(sel)}\", valeur: \"{{{{mot_de_passe}}}}\"}}   # passez-le avec --var mot_de_passe=..."]
            return [f"{indent}- remplir: {{selecteur: \"{_echapper(sel)}\", valeur: \"{{{{{nom_col} ?}}}}\"}}"]
        return []

    for e in visibles:
        if e["bouton"] or e["tag"] == "a":
            continue
        if e["cadre"]:
            if e["cadre"] not in cadres_vus:
                cadres_vus.add(e["cadre"])
                lignes.append(f"  - cadre:")
                lignes.append(f"      selecteur: \"{_echapper(e['cadre'])}\"")
                lignes.append(f"      etapes:")
                for autre in visibles:
                    if autre["cadre"] == e["cadre"] and not autre["bouton"] and autre["tag"] != "a":
                        lignes.extend(etape_pour(autre, "        "))
            continue
        lignes.extend(etape_pour(e, "  "))
    lignes.append("  - pause: \"Vérifiez le formulaire puis appuyez sur Entrée\"   # à retirer une fois validé")
    boutons = [e for e in visibles if e["bouton"] and e["texte"]]
    if boutons:
        lignes.append("  # Boutons repérés (gardez celui qui enregistre) :")
        for b in boutons[:15]:
            lignes.append(f"  # - cliquer: \"{_echapper(selecteur_suggere(b))}\"")
    lignes.append("  # - verifier: {selecteur: \".message-succes ?\", contient: \"enregistré\"}")
    lignes.append("  # - lire: {selecteur: \".reference ?\", vers: \"Référence outil\"}")
    return "\n".join(lignes) + "\n"


def relever(page: Page, dossier_sortie: Path, nom: Optional[str] = None) -> Path:
    """Photographie la page courante dans dossier_sortie/<horodatage>-<nom>/ et renvoie ce dossier."""
    titre = page.title() or "page"
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", (nom or titre)).strip("_")[:40] or "page"
    dossier = Path(dossier_sortie) / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{base}"
    dossier.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(dossier / "capture.png"), full_page=True)
    except PlaywrightError:
        page.screenshot(path=str(dossier / "capture.png"))
    (dossier / "page.html").write_text(page.content(), encoding="utf-8")
    elements = inventaire(page)
    (dossier / "champs.txt").write_text(_texte_inventaire(page, elements), encoding="utf-8")
    (dossier / "brouillon.yaml").write_text(_brouillon_yaml(page, elements, nom or base), encoding="utf-8")
    (dossier / "champs.json").write_text(
        json.dumps({"url": page.url, "titre": titre, "nom": nom or base, "elements": elements}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return dossier


def charger_releve(dossier: Path) -> Dict[str, Any]:
    """Relit champs.json d'un dossier de relevé."""
    chemin = Path(dossier) / "champs.json"
    if not chemin.exists():
        raise FileNotFoundError(f"{chemin} introuvable : refaites « python -m autoweb releve »")
    return json.loads(chemin.read_text(encoding="utf-8"))


def dernier_releve(racine: Path) -> Optional[Path]:
    """Le dossier de relevé le plus récent sous `racine` (releves/)."""
    racine = Path(racine)
    if not racine.is_dir():
        return None
    candidats = sorted(d for d in racine.iterdir() if d.is_dir() and (d / "champs.json").exists())
    return candidats[-1] if candidats else None

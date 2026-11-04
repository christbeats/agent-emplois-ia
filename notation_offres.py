import json
import os
import re
import sqlite3

import anthropic
from dotenv import load_dotenv

load_dotenv()

BASE = "offres.db"
MODELE = "claude-haiku-5-5"  # modèle rapide et économique, à changer si besoin
SEUIL = 70  # on ne met en avant que les offres ≥ 70
MAX_OFFRES = 30  # limite par exécution, pour maîtriser le coût
ESSAIS = 2  # nombre de tentatives par offre

client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY dans l'environnement


def preparer_base():
    base = sqlite3.connect(BASE)
    colonnes = [c[1] for c in base.execute("PRAGMA table_info(offres)")]
    if "score" not in colonnes:
        base.execute("ALTER TABLE offres ADD COLUMN score INTEGER")
        base.execute("ALTER TABLE offres ADD COLUMN justification TEXT")
        base.commit()
    return base


def lire_reponse(texte):
    """Extrait le score et la justification, même si la réponse est mal formée."""
    # 1re tentative : un JSON propre entre accolades
    debut, fin = texte.find("{"), texte.rfind("}") + 1
    if debut != -1 and fin > debut:
        try:
            resultat = json.loads(texte[debut:fin])
            return int(resultat["score"]), str(resultat.get("justification", ""))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass
    # 2e tentative : on cherche un nombre après le mot « score »
    trouve = re.search(r'score\D{0,5}(\d{1,3})', texte, re.IGNORECASE)
    if trouve:
        score = min(int(trouve.group(1)), 100)
        return score, texte.strip()[:200]
    raise ValueError("aucune note trouvée dans la réponse")


def noter_offre(profil, offre):
    """Demande une note et une justification pour une offre."""
    consigne = (
        "Tu aides une personne à trier ses offres d'emploi.\n\n"
        f"PROFIL DE LA PERSONNE :\n{profil}\n\n"
        f"OFFRE :\nTitre : {offre['titre']}\nInfos : {offre['contexte']}\n\n"
        "Note l'adéquation de l'offre avec le profil de 0 à 100. "
        "Si les infos sont insuffisantes, réponds quand même avec le JSON "
        "et un score prudent en le signalant dans la justification. "
        "N'écris rien en dehors du JSON. "
        'Format exact : {"score": 55, "justification": "une phrase"}'
    )
    derniere_erreur = None
    for essai in range(ESSAIS):
        reponse = client.messages.create(
            model=MODELE,
            max_tokens=300,
            messages=[{"role": "user", "content": consigne}],
        )
        texte = "".join(b.text for b in reponse.content if b.type == "text")
        try:
            return lire_reponse(texte)
        except ValueError as erreur:
            derniere_erreur = f"{erreur} | réponse reçue : {texte[:150]!r}"
    raise ValueError(derniere_erreur)


if __name__ == "__main__":
    with open("profil.txt", encoding="utf-8") as fichier:
        profil = fichier.read()

    base = preparer_base()
    base.row_factory = sqlite3.Row
    a_noter = base.execute(
        "SELECT id, titre, contexte FROM offres WHERE score IS NULL LIMIT ?",
        (MAX_OFFRES,),
    ).fetchall()
    print(f"{len(a_noter)} offres à noter...")

    ignorees = 0
    for offre in a_noter:
        try:
            score, justification = noter_offre(profil, offre)
        except Exception as erreur:
            ignorees += 1
            print(f"Offre ignorée ({offre['titre']}) : {erreur}")
            continue
        base.execute(
            "UPDATE offres SET score = ?, justification = ? WHERE id = ?",
            (score, justification, offre["id"]),
        )
        base.commit()

    print(f"\n{len(a_noter) - ignorees} offres notées, {ignorees} ignorées.")

    print(f"\n===== Meilleures offres (note ≥ {SEUIL}) =====")
    meilleures = base.execute(
        "SELECT score, titre, source, lien, justification FROM offres "
        "WHERE score >= ? ORDER BY score DESC LIMIT 10",
        (SEUIL,),
    )
    for ligne in meilleures:
        print(f"\n[{ligne['score']}] {ligne['titre']} ({ligne['source']})")
        print("   ", ligne["justification"])
        print("    Lien :", ligne["lien"])
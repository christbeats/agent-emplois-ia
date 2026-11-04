import os
import smtplib
import sqlite3
import traceback
from datetime import datetime
from email.message import EmailMessage

from dotenv import load_dotenv

import extraction_offres
import notation_offres

load_dotenv()

ADRESSE = os.getenv("GMAIL_ADRESSE")
MOT_DE_PASSE = os.getenv("GMAIL_MOT_DE_PASSE_APP")
DESTINATAIRE = os.getenv("ADRESSE_RESUME") or ADRESSE
BASE = "offres.db"
SEUIL = 70


def etape_extraction():
    base = extraction_offres.creer_base()
    connexion = extraction_offres.se_connecter()
    for source, reglages in extraction_offres.SITES.items():
        extraction_offres.traiter_site(connexion, base, source, reglages)
    connexion.logout()
    base.close()


def etape_notation():
    with open("profil.txt", encoding="utf-8") as fichier:
        profil = fichier.read()
    base = notation_offres.preparer_base()
    base.row_factory = sqlite3.Row
    a_noter = base.execute(
        "SELECT id, titre, contexte FROM offres WHERE score IS NULL LIMIT ?",
        (notation_offres.MAX_OFFRES,),
    ).fetchall()
    print(f"{len(a_noter)} offres à noter")
    for offre in a_noter:
        try:
            score, justification = notation_offres.noter_offre(profil, offre)
        except Exception as erreur:
            print(f"Offre ignorée ({offre['titre']}) : {erreur}")
            continue
        base.execute(
            "UPDATE offres SET score = ?, justification = ? WHERE id = ?",
            (score, justification, offre["id"]),
        )
        base.commit()
    base.close()


def etape_resume():
    base = sqlite3.connect(BASE)
    base.row_factory = sqlite3.Row
    colonnes = [c[1] for c in base.execute("PRAGMA table_info(offres)")]
    if "envoyee" not in colonnes:
        base.execute("ALTER TABLE offres ADD COLUMN envoyee INTEGER DEFAULT 0")
        base.commit()

    nouvelles = base.execute(
        "SELECT id, score, titre, source, lien, justification FROM offres "
        "WHERE score >= ? AND (envoyee IS NULL OR envoyee = 0) "
        "ORDER BY score DESC",
        (SEUIL,),
    ).fetchall()

    if not nouvelles:
        print("Aucune nouvelle offre à envoyer.")
        base.close()
        return

    lignes = [f"{len(nouvelles)} nouvelle(s) offre(s) à regarder :\n"]
    for offre in nouvelles:
        lignes.append(f"[{offre['score']}] {offre['titre']} ({offre['source']})")
        lignes.append(f"  {offre['justification']}")
        lignes.append(f"  Lien : {offre['lien']}\n")
    lignes.append("Rappel : ouvre le lien et lis l'annonce avant de postuler.")

    envoyer_mail(
        f"Offres du {datetime.now():%d/%m/%Y} : {len(nouvelles)} à regarder",
        "\n".join(lignes),
    )
    for offre in nouvelles:
        base.execute("UPDATE offres SET envoyee = 1 WHERE id = ?", (offre["id"],))
    base.commit()
    base.close()
    print(f"Résumé envoyé : {len(nouvelles)} offres.")


def envoyer_mail(sujet, texte):
    message = EmailMessage()
    message["Subject"] = sujet
    message["From"] = ADRESSE
    message["To"] = DESTINATAIRE
    message.set_content(texte)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as serveur:
        serveur.login(ADRESSE, MOT_DE_PASSE)
        serveur.send_message(message)


if __name__ == "__main__":
    print(f"=== Lancement {datetime.now():%d/%m/%Y %H:%M} ===")
    for nom, etape in [
        ("Extraction", etape_extraction),
        ("Notation", etape_notation),
        ("Résumé", etape_resume),
    ]:
        try:
            etape()
        except Exception:
            print(f"\n!!! Étape « {nom} » en erreur :")
            traceback.print_exc()
    print("=== Terminé ===")
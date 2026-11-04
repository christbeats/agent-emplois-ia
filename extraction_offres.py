import imaplib
import email
import os
import re
import sqlite3
from datetime import date, timedelta
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

ADRESSE = os.getenv("GMAIL_ADRESSE")
MOT_DE_PASSE = os.getenv("GMAIL_MOT_DE_PASSE_APP")
BASE = "offres.db"
JOURS_A_LIRE = 3  # on relit les mails des 3 derniers jours

# Pour chaque site : morceau de l'adresse d'envoi + motif du lien d'offre
SITES = {
    "LinkedIn": {"expediteur": "linkedin.com", "motif_lien": r"/jobs/view/(\d+)"},
    "HelloWork": {"expediteur": "hellowork.com", "motif_lien": r"/clic/(\d+)"},
    "France Travail": {"expediteur": "francetravail", "motif_lien": r"offres?/recherche/detail|candidat/offres"},
}


def creer_base():
    base = sqlite3.connect(BASE)
    base.execute(
        """CREATE TABLE IF NOT EXISTS offres (
            id TEXT PRIMARY KEY,
            source TEXT,
            titre TEXT,
            contexte TEXT,
            lien TEXT,
            date_vue TEXT
        )"""
    )
    return base


def se_connecter():
    connexion = imaplib.IMAP4_SSL("imap.gmail.com")
    connexion.login(ADRESSE, MOT_DE_PASSE)
    connexion.select("INBOX", readonly=True)
    return connexion


def corps_html(message):
    """Récupère la partie HTML d'un mail (ou le texte simple à défaut)."""
    texte_simple = ""
    for partie in message.walk():
        type_contenu = partie.get_content_type()
        charge = partie.get_payload(decode=True)
        if not charge:
            continue
        contenu = charge.decode(partie.get_content_charset() or "utf-8", errors="replace")
        if type_contenu == "text/html":
            return contenu
        if type_contenu == "text/plain":
            texte_simple = contenu
    return texte_simple


def identifiant_offre(source, lien, motif):
    """Identifiant stable : numéro d'offre si présent, sinon lien sans paramètres de suivi."""
    correspondance = re.search(motif, lien)
    if correspondance and correspondance.groups():
        return f"{source}:{correspondance.group(1)}"
    propre = urlparse(lien)
    return f"{source}:{propre.netloc}{propre.path}"


def extraire_offres(source, reglages, html):
    """Trouve les liens d'offres dans un mail et le texte qui les entoure."""
    soupe = BeautifulSoup(html, "html.parser")
    offres = []
    for lien in soupe.find_all("a", href=True):
        adresse = lien["href"]
        titre = lien.get_text(" ", strip=True)
        if not re.search(reglages["motif_lien"], adresse) or len(titre) < 4:
            continue
        # Le texte du bloc parent contient souvent l'entreprise et le lieu
        parent = lien.find_parent(["td", "div", "li", "tr"])
        contexte = parent.get_text(" | ", strip=True) if parent else ""
        contexte = contexte.replace(titre, "").strip(" |")[:200]
        offres.append(
            {
                "id": identifiant_offre(source, adresse, reglages["motif_lien"]),
                "source": source,
                "titre": titre,
                "contexte": contexte,
                "lien": adresse,
            }
        )
    return offres


def traiter_site(connexion, base, source, reglages):
    depuis = (date.today() - timedelta(days=JOURS_A_LIRE)).strftime("%d-%b-%Y")
    critere = f'(FROM "{reglages["expediteur"]}" SINCE {depuis})'
    etat, donnees = connexion.search(None, critere)
    identifiants = donnees[0].split()

    nouvelles = 0
    for identifiant in identifiants:
        etat, contenu = connexion.fetch(identifiant, "(BODY.PEEK[])")
        message = email.message_from_bytes(contenu[0][1])
        html = corps_html(message)
        for offre in extraire_offres(source, reglages, html):
            try:
                base.execute(
                    "INSERT INTO offres VALUES (?, ?, ?, ?, ?, ?)",
                    (offre["id"], offre["source"], offre["titre"],
                     offre["contexte"], offre["lien"], date.today().isoformat()),
                )
                nouvelles += 1
            except sqlite3.IntegrityError:
                pass  # offre déjà connue
    base.commit()
    print(f"{source} : {len(identifiants)} mails lus, {nouvelles} nouvelles offres")


if __name__ == "__main__":
    base = creer_base()
    connexion = se_connecter()
    for source, reglages in SITES.items():
        traiter_site(connexion, base, source, reglages)
    connexion.logout()

    total = base.execute("SELECT COUNT(*) FROM offres").fetchone()[0]
    print(f"\nTotal en base : {total} offres")
    for ligne in base.execute(
        "SELECT source, titre, contexte FROM offres ORDER BY date_vue DESC LIMIT 10"
    ):
        print(f"\n[{ligne[0]}] {ligne[1]}\n   {ligne[2]}")
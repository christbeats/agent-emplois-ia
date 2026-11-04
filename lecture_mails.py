import imaplib
import email
import os
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv()

ADRESSE = os.getenv("GMAIL_ADRESSE")
MOT_DE_PASSE = os.getenv("GMAIL_MOT_DE_PASSE_APP")

# Mots qui permettent de reconnaître l'expéditeur de chaque site
EXPEDITEURS = {
    "LinkedIn": "linkedin.com",
    "HelloWork": "hellowork",
    "France Travail": "francetravail",
}


def se_connecter():
    """Ouvre la connexion IMAP en lecture seule."""
    connexion = imaplib.IMAP4_SSL("imap.gmail.com")
    connexion.login(ADRESSE, MOT_DE_PASSE)
    connexion.select("INBOX", readonly=True)  # lecture seule : rien n'est modifié
    return connexion


def decoder(texte):
    """Rend lisible un sujet de mail (accents, encodages)."""
    morceaux = decode_header(texte or "")
    resultat = ""
    for partie, encodage in morceaux:
        if isinstance(partie, bytes):
            resultat += partie.decode(encodage or "utf-8", errors="replace")
        else:
            resultat += partie
    return resultat


def lister_mails(connexion, site, motif, maximum=5):
    """Affiche les derniers mails d'un site d'emploi."""
    etat, donnees = connexion.search(None, f'(FROM "{motif}")')
    identifiants = donnees[0].split()
    print(f"\n===== {site} : {len(identifiants)} mails trouvés =====")

    for identifiant in identifiants[-maximum:]:
        etat, contenu = connexion.fetch(identifiant, "(BODY.PEEK[HEADER])")
        message = email.message_from_bytes(contenu[0][1])
        print("-", decoder(message["Subject"]))
        print("   De :", decoder(message["From"]))
        print("   Date :", message["Date"])


if __name__ == "__main__":
    connexion = se_connecter()
    print("Connexion réussie.")
    for site, motif in EXPEDITEURS.items():
        lister_mails(connexion, site, motif)
    connexion.logout()
"""
base_locale.py -- Stockage SQLite local des bundles DTN chiffres.

Ici, on implemente le stockage local des bundles de donnees chiffres.
C'est la composante "store" du paradigme DTN "store-carry-forward".

SQLite est choisi car :
- Il ne necessite aucun serveur (embarque dans la bibliotheque standard Python)
- Il est leger et fiable, ideal pour un stockage sur Raspberry Pi
- Il supporte les transactions ACID

Chaque bundle stocke contient :
- Un identifiant unique (UUID)
- Les donnees chiffrees (AES-256-CBC)
- Le vecteur d'initialisation (IV)
- La signature numerique (ECDSA)
- Un nonce anti-rejeu
- L'horodatage de creation
- Le statut de transfert (en_attente, transfere)
"""

import os
import uuid
import sqlite3
import logging
import base64
from datetime import datetime, timezone

import config

logger = logging.getLogger(__name__)


class BaseLocale:
    """
    Classe gerant la base de donnees SQLite locale de la sentinelle.
    """

    def __init__(self):
        """
        Ici, on initialise la base de donnees SQLite.
        Si la base n'existe pas, on cree la table des bundles.
        """
        repertoire = os.path.dirname(config.FICHIER_BASE_DONNEES)
        if not os.path.exists(repertoire):
            os.makedirs(repertoire, exist_ok=True)

        # Ici, check_same_thread=False permet l'acces depuis le thread BLE
        # et le thread principal simultanement.
        self.connexion = sqlite3.connect(
            config.FICHIER_BASE_DONNEES,
            check_same_thread=False,
        )
        # Ici, le mode WAL permet des lectures concurrentes pendant les ecritures.
        self.connexion.execute("PRAGMA journal_mode=WAL")
        self.connexion.row_factory = sqlite3.Row

        self._creer_table()
        logger.info(f"Base de donnees initialisee : {config.FICHIER_BASE_DONNEES}")

    def _creer_table(self):
        """Ici, on cree la table des bundles si elle n'existe pas."""
        self.connexion.execute("""
            CREATE TABLE IF NOT EXISTS bundles (
                bundle_id TEXT PRIMARY KEY,
                iv TEXT NOT NULL,
                donnees_chiffrees TEXT NOT NULL,
                signature TEXT NOT NULL,
                nonce TEXT NOT NULL,
                horodatage TEXT NOT NULL,
                statut TEXT NOT NULL DEFAULT 'en_attente',
                nb_mesures INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.connexion.commit()

    def stocker_bundle(self, iv, donnees_chiffrees, signature, nonce, nb_mesures):
        """
        Ici, on stocke un nouveau bundle chiffre et signe dans la base.

        Args:
            iv: Vecteur d'initialisation AES (bytes, 16 octets).
            donnees_chiffrees: Donnees chiffrees (bytes).
            signature: Signature ECDSA (bytes).
            nonce: Nonce anti-rejeu (str, hex).
            nb_mesures: Nombre de mesures dans le bundle.

        Returns:
            Identifiant unique du bundle (str UUID).
        """
        bundle_id = str(uuid.uuid4())
        horodatage = datetime.now(timezone.utc).isoformat()

        # Ici, on encode les donnees binaires en base64 pour le stockage texte.
        iv_b64 = base64.b64encode(iv).decode("ascii")
        donnees_b64 = base64.b64encode(donnees_chiffrees).decode("ascii")
        signature_b64 = base64.b64encode(signature).decode("ascii")

        self.connexion.execute(
            """
            INSERT INTO bundles
                (bundle_id, iv, donnees_chiffrees, signature, nonce,
                 horodatage, statut, nb_mesures)
            VALUES (?, ?, ?, ?, ?, ?, 'en_attente', ?)
            """,
            (bundle_id, iv_b64, donnees_b64, signature_b64,
             nonce, horodatage, nb_mesures),
        )
        self.connexion.commit()
        self._nettoyer_anciens()

        logger.info(f"Bundle stocke : id={bundle_id[:8]}..., {nb_mesures} mesures")
        return bundle_id

    def compter_bundles_en_attente(self):
        """Ici, on compte les bundles pas encore transferes a une mule."""
        curseur = self.connexion.execute(
            "SELECT COUNT(*) FROM bundles WHERE statut = 'en_attente'"
        )
        return curseur.fetchone()[0]

    def recuperer_bundle_par_index(self, index):
        """
        Ici, on recupere un bundle en attente par son index (FIFO).

        Args:
            index: Position dans la file d'attente (0 = le plus ancien).

        Returns:
            Dictionnaire du bundle, ou None si l'index est invalide.
        """
        curseur = self.connexion.execute(
            """
            SELECT bundle_id, iv, donnees_chiffrees, signature, nonce,
                   horodatage, nb_mesures
            FROM bundles
            WHERE statut = 'en_attente'
            ORDER BY horodatage ASC
            LIMIT 1 OFFSET ?
            """,
            (index,),
        )
        ligne = curseur.fetchone()
        if ligne is None:
            return None

        return {
            "bundle_id": ligne["bundle_id"],
            "sentinel_id": config.SENTINEL_ID,
            "iv": ligne["iv"],
            "donnees_chiffrees": ligne["donnees_chiffrees"],
            "signature": ligne["signature"],
            "nonce": ligne["nonce"],
            "horodatage": ligne["horodatage"],
            "nb_mesures": ligne["nb_mesures"],
        }

    def marquer_transfere(self, bundle_id):
        """
        Ici, on marque un bundle comme transfere apres acquittement par la mule.

        Returns:
            True si le bundle a ete marque, False sinon.
        """
        curseur = self.connexion.execute(
            "UPDATE bundles SET statut = 'transfere' "
            "WHERE bundle_id = ? AND statut = 'en_attente'",
            (bundle_id,),
        )
        self.connexion.commit()
        succes = curseur.rowcount > 0
        if succes:
            logger.info(f"Bundle {bundle_id[:8]}... marque comme transfere")
        return succes

    def _nettoyer_anciens(self):
        """Ici, on supprime les anciens bundles si on depasse la limite."""
        curseur = self.connexion.execute("SELECT COUNT(*) FROM bundles")
        total = curseur.fetchone()[0]

        if total <= config.MAX_BUNDLES_STOCKES:
            return

        nb_a_supprimer = total - config.MAX_BUNDLES_STOCKES
        self.connexion.execute(
            """
            DELETE FROM bundles WHERE bundle_id IN (
                SELECT bundle_id FROM bundles
                WHERE statut = 'transfere'
                ORDER BY horodatage ASC LIMIT ?
            )
            """,
            (nb_a_supprimer,),
        )
        self.connexion.commit()
        logger.info(f"Nettoyage : {nb_a_supprimer} anciens bundles supprimes")

    def fermer(self):
        """Ici, on ferme proprement la connexion a la base de donnees."""
        if self.connexion:
            self.connexion.close()
            logger.info("Base de donnees fermee proprement")

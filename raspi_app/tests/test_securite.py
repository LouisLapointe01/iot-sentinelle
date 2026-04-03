"""
test_securite.py -- Tests des modules securite (cles, chiffrement AES, signature ECDSA).
"""
import os
import json
import pytest
from Crypto.PublicKey import ECC
from Crypto.Random import get_random_bytes


class TestCles:
    def test_cle_aes_32_octets(self, cle_aes):
        assert len(cle_aes) == 32

    def test_cle_aes_bytes(self, cle_aes):
        assert isinstance(cle_aes, bytes)

    def test_cle_aes_idempotent(self):
        from securite.cles import generer_cle_aes
        assert generer_cle_aes() == generer_cle_aes()

    def test_fichier_cle_aes_cree(self):
        import config
        from securite.cles import generer_cle_aes
        generer_cle_aes()
        assert os.path.exists(config.FICHIER_CLE_AES)

    def test_ecdsa_format_pem(self):
        from securite.cles import generer_cles_ecdsa
        priv, pub = generer_cles_ecdsa()
        assert "BEGIN EC PRIVATE KEY" in priv
        assert "BEGIN PUBLIC KEY" in pub

    def test_ecdsa_idempotent(self):
        from securite.cles import generer_cles_ecdsa
        assert generer_cles_ecdsa() == generer_cles_ecdsa()

    def test_courbe_p256(self, cle_privee_ecdsa):
        assert cle_privee_ecdsa.curve == "NIST P-256"

    def test_cle_privee_has_private(self, cle_privee_ecdsa):
        assert cle_privee_ecdsa.has_private()

    def test_cle_publique_importable(self, cle_publique_pem):
        cle = ECC.import_key(cle_publique_pem)
        assert not cle.has_private()

    def test_coherence_privee_publique(self):
        from securite.cles import charger_cle_privee_ecdsa, charger_cle_publique_ecdsa_pem
        priv = charger_cle_privee_ecdsa()
        pub = ECC.import_key(charger_cle_publique_ecdsa_pem())
        assert priv.public_key().export_key(format="PEM") == pub.export_key(format="PEM")


class TestChiffrementAES:
    def test_retourne_iv_et_chiffre(self, cle_aes, mesures_exemple):
        from securite.chiffrement import chiffrer_donnees
        iv, chiffre = chiffrer_donnees(mesures_exemple, cle_aes)
        assert isinstance(iv, bytes) and isinstance(chiffre, bytes)

    def test_iv_16_octets(self, cle_aes, mesures_exemple):
        from securite.chiffrement import chiffrer_donnees
        iv, _ = chiffrer_donnees(mesures_exemple, cle_aes)
        assert len(iv) == 16

    def test_chiffre_multiple_16(self, cle_aes, mesures_exemple):
        from securite.chiffrement import chiffrer_donnees
        _, chiffre = chiffrer_donnees(mesures_exemple, cle_aes)
        assert len(chiffre) % 16 == 0

    def test_aller_retour(self, cle_aes, mesures_exemple):
        from securite.chiffrement import chiffrer_donnees, dechiffrer_donnees
        iv, chiffre = chiffrer_donnees(mesures_exemple, cle_aes)
        assert dechiffrer_donnees(iv, chiffre, cle_aes) == mesures_exemple

    def test_iv_unique_a_chaque_fois(self, cle_aes, mesures_exemple):
        from securite.chiffrement import chiffrer_donnees
        ivs = {chiffrer_donnees(mesures_exemple, cle_aes)[0] for _ in range(20)}
        assert len(ivs) == 20

    def test_chiffres_differents(self, cle_aes, mesures_exemple):
        from securite.chiffrement import chiffrer_donnees
        chiffres = {chiffrer_donnees(mesures_exemple, cle_aes)[1] for _ in range(20)}
        assert len(chiffres) == 20

    def test_mauvaise_cle_echoue(self, cle_aes, mesures_exemple):
        from securite.chiffrement import chiffrer_donnees, dechiffrer_donnees
        iv, chiffre = chiffrer_donnees(mesures_exemple, cle_aes)
        with pytest.raises(Exception):
            dechiffrer_donnees(iv, chiffre, get_random_bytes(32))

    def test_mauvais_iv_echoue(self, cle_aes, mesures_exemple):
        from securite.chiffrement import chiffrer_donnees, dechiffrer_donnees
        iv, chiffre = chiffrer_donnees(mesures_exemple, cle_aes)
        with pytest.raises(Exception):
            dechiffrer_donnees(get_random_bytes(16), chiffre, cle_aes)

    def test_donnees_vides(self, cle_aes):
        from securite.chiffrement import chiffrer_donnees, dechiffrer_donnees
        d = {"mesures": []}
        iv, chiffre = chiffrer_donnees(d, cle_aes)
        assert dechiffrer_donnees(iv, chiffre, cle_aes) == d

    def test_donnees_volumineuses(self, cle_aes):
        from securite.chiffrement import chiffrer_donnees, dechiffrer_donnees
        d = {"mesures": [{"i": i} for i in range(500)]}
        iv, chiffre = chiffrer_donnees(d, cle_aes)
        assert dechiffrer_donnees(iv, chiffre, cle_aes) == d

    def test_caracteres_utf8(self, cle_aes):
        from securite.chiffrement import chiffrer_donnees, dechiffrer_donnees
        d = {"texte": "Temperature 25degC, donnees francaises aeiou"}
        iv, chiffre = chiffrer_donnees(d, cle_aes)
        assert dechiffrer_donnees(iv, chiffre, cle_aes) == d

    def test_texte_clair_absent_du_chiffre(self, cle_aes, mesures_exemple):
        from securite.chiffrement import chiffrer_donnees
        _, chiffre = chiffrer_donnees(mesures_exemple, cle_aes)
        assert json.dumps(mesures_exemple).encode() not in chiffre


class TestSignatureECDSA:
    def test_signature_bytes(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees
        assert isinstance(signer_donnees(b"test", cle_privee_ecdsa), bytes)

    def test_signature_taille(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees
        sig = signer_donnees(b"test", cle_privee_ecdsa)
        assert 64 <= len(sig) <= 72

    def test_verification_valide(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees, verifier_signature
        data = b"test data"
        sig = signer_donnees(data, cle_privee_ecdsa)
        assert verifier_signature(data, sig, cle_privee_ecdsa.public_key())

    def test_donnees_modifiees_echoue(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees, verifier_signature
        sig = signer_donnees(b"original", cle_privee_ecdsa)
        assert not verifier_signature(b"modifie", sig, cle_privee_ecdsa.public_key())

    def test_mauvaise_cle_echoue(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees, verifier_signature
        sig = signer_donnees(b"test", cle_privee_ecdsa)
        autre = ECC.generate(curve="P-256")
        assert not verifier_signature(b"test", sig, autre.public_key())

    def test_signatures_differentes(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees
        s1 = signer_donnees(b"data", cle_privee_ecdsa)
        s2 = signer_donnees(b"data", cle_privee_ecdsa)
        assert s1 != s2  # ECDSA nonce aleatoire

    def test_deux_signatures_valides(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees, verifier_signature
        pub = cle_privee_ecdsa.public_key()
        s1 = signer_donnees(b"data", cle_privee_ecdsa)
        s2 = signer_donnees(b"data", cle_privee_ecdsa)
        assert verifier_signature(b"data", s1, pub)
        assert verifier_signature(b"data", s2, pub)

    def test_signer_vide(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees, verifier_signature
        sig = signer_donnees(b"", cle_privee_ecdsa)
        assert verifier_signature(b"", sig, cle_privee_ecdsa.public_key())

    def test_signer_100ko(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees, verifier_signature
        data = get_random_bytes(100_000)
        sig = signer_donnees(data, cle_privee_ecdsa)
        assert verifier_signature(data, sig, cle_privee_ecdsa.public_key())

    def test_signature_corrompue(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees, verifier_signature
        sig = bytearray(signer_donnees(b"test", cle_privee_ecdsa))
        sig[0] ^= 0xFF
        assert not verifier_signature(b"test", bytes(sig), cle_privee_ecdsa.public_key())

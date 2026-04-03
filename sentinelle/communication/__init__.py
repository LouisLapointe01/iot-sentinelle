"""
Package communication -- Serveur BLE GATT pour le transfert DTN.

Ici, la sentinelle agit comme un peripherique BLE (GATT Server) qui expose
ses bundles chiffres via des caracteristiques GATT.
L'implementation utilise l'API D-Bus de BlueZ (pile Bluetooth officielle de Linux).
"""

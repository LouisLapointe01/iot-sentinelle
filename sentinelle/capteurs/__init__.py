"""
Package capteurs -- Modules de lecture des capteurs environnementaux.

Ici, ce package regroupe les trois capteurs de la sentinelle :
- DHT22 : temperature et humidite relative
- BME280 : pression atmospherique (et temperature/humidite en complement)
- PMS5003 : concentration en particules fines (PM1.0, PM2.5, PM10)

Chaque capteur est encapsule dans sa propre classe, et le GestionnaireCapteurs
orchestre les lectures periodiques de l'ensemble.
"""

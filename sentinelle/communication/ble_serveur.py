"""
ble_serveur.py -- Serveur BLE GATT pour le transfert DTN vers les mules.

Ici, on implemente un serveur GATT BLE qui expose les bundles chiffres
de la sentinelle aux applications mobiles (mules).

Service GATT personnalise "Sentinelle DTN" :
  UUID du service : 12345678-1234-5678-1234-56789abcdef0

  Caracteristiques :
  - BUNDLE_DATA   (Read)         : donnees du bundle selectionne (JSON)
  - PUBLIC_KEY    (Read)         : cle publique ECDSA (PEM)
  - SENTINEL_INFO (Read)         : metadonnees sentinelle (JSON)
  - BUNDLE_ACK    (Write)        : acquittement d'un bundle
  - BUNDLE_COUNT  (Read/Notify)  : nombre de bundles en attente
  - BUNDLE_SELECT (Write)        : selection du bundle a lire par index

L'implementation utilise l'API D-Bus de BlueZ.
Note : ce module necessite les droits root (sudo) pour acceder au Bluetooth.
"""

import json
import logging
import threading

import config

logger = logging.getLogger(__name__)

# Ici, on tente d'importer les bibliotheques D-Bus/BlueZ.
# Ces imports echoueront sur un PC de developpement (Windows/Mac).
try:
    import dbus
    import dbus.exceptions
    import dbus.mainloop.glib
    import dbus.service
    from gi.repository import GLib

    DBUS_DISPONIBLE = True
except ImportError:
    DBUS_DISPONIBLE = False
    logger.warning(
        "Bibliotheques D-Bus/GLib non disponibles. "
        "Le serveur BLE ne fonctionnera qu'en mode simulation."
    )


# =============================================================================
# CONSTANTES BlueZ D-Bus
# =============================================================================
BLUEZ_SERVICE_NAME = "org.bluez"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"


# =============================================================================
# CLASSES D-BUS POUR LE SERVEUR GATT
# =============================================================================

if DBUS_DISPONIBLE:
    _BaseDBusObject = dbus.service.Object
else:
    _BaseDBusObject = object


class Advertisement(_BaseDBusObject):
    """
    Ici, on implemente un objet D-Bus representant un advertisement BLE.
    L'advertisement est le paquet que la sentinelle diffuse pour signaler
    sa presence aux smartphones a proximite.
    """
    PATH_BASE = "/org/bluez/sentinelle/advertisement"

    def __init__(self, bus, index, service_uuids, nom_local):
        self.path = f"{self.PATH_BASE}{index}"
        self.bus = bus
        self.ad_type = "peripheral"
        self.service_uuids = service_uuids
        self.nom_local = nom_local
        if DBUS_DISPONIBLE:
            dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            LE_ADVERTISEMENT_IFACE: {
                "Type": self.ad_type,
                "ServiceUUIDs": dbus.Array(self.service_uuids, signature="s"),
                "LocalName": dbus.String(self.nom_local),
                "Includes": dbus.Array(["tx-power"], signature="s"),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    if DBUS_DISPONIBLE:
        @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface != LE_ADVERTISEMENT_IFACE:
                raise dbus.exceptions.DBusException(
                    "org.freedesktop.DBus.Error.InvalidArgs",
                    f"Interface inconnue : {interface}",
                )
            return self.get_properties()[LE_ADVERTISEMENT_IFACE]

        @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
        def Release(self):
            logger.info("Advertisement BLE libere")


class Caracteristique(_BaseDBusObject):
    """
    Ici, on implemente une caracteristique GATT generique.
    Chaque sous-classe surcharge ReadValue/WriteValue.
    """

    def __init__(self, bus, index, uuid_char, flags, service):
        self.path = f"{service.get_path()}/char{index}"
        self.bus = bus
        self.uuid = uuid_char
        self.flags = flags
        self.service = service
        self.valeur = []
        self.notifying = False
        if DBUS_DISPONIBLE:
            dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    if DBUS_DISPONIBLE:
        @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface != GATT_CHRC_IFACE:
                raise dbus.exceptions.DBusException(
                    "org.freedesktop.DBus.Error.InvalidArgs",
                    f"Interface inconnue : {interface}",
                )
            return self.get_properties()[GATT_CHRC_IFACE]

        @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options):
            return self.valeur

        @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
        def WriteValue(self, value, options):
            self.valeur = value

        @dbus.service.method(GATT_CHRC_IFACE)
        def StartNotify(self):
            self.notifying = True

        @dbus.service.method(GATT_CHRC_IFACE)
        def StopNotify(self):
            self.notifying = False

        @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
        def PropertiesChanged(self, interface, changed, invalidated):
            pass

    def notifier_changement(self, nouvelle_valeur):
        if not self.notifying:
            return
        self.valeur = nouvelle_valeur
        if DBUS_DISPONIBLE:
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {"Value": dbus.Array(nouvelle_valeur, signature="y")},
                [],
            )


class ServiceGATT(_BaseDBusObject):
    """Ici, on implemente le service GATT personnalise de la sentinelle DTN."""
    PATH_BASE = "/org/bluez/sentinelle/service"

    def __init__(self, bus, index, uuid_service, primary=True):
        self.path = f"{self.PATH_BASE}{index}"
        self.bus = bus
        self.uuid = uuid_service
        self.primary = primary
        self.caracteristiques = []
        if DBUS_DISPONIBLE:
            dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    [c.get_path() for c in self.caracteristiques], signature="o",
                ) if DBUS_DISPONIBLE else [],
            }
        }

    def get_path(self):
        if DBUS_DISPONIBLE:
            return dbus.ObjectPath(self.path)
        return self.path

    def ajouter_caracteristique(self, caracteristique):
        self.caracteristiques.append(caracteristique)

    if DBUS_DISPONIBLE:
        @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface != GATT_SERVICE_IFACE:
                raise dbus.exceptions.DBusException(
                    "org.freedesktop.DBus.Error.InvalidArgs",
                    f"Interface inconnue : {interface}",
                )
            return self.get_properties()[GATT_SERVICE_IFACE]


class ApplicationGATT(_BaseDBusObject):
    """
    Ici, on implemente l'application GATT qui regroupe tous les services.
    BlueZ attend un objet qui implemente l'interface ObjectManager.
    """

    def __init__(self, bus):
        self.path = "/org/bluez/sentinelle"
        self.services = []
        if DBUS_DISPONIBLE:
            dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        if DBUS_DISPONIBLE:
            return dbus.ObjectPath(self.path)
        return self.path

    def ajouter_service(self, service):
        self.services.append(service)

    if DBUS_DISPONIBLE:
        @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
        def GetManagedObjects(self):
            objets = {}
            for service in self.services:
                objets[service.get_path()] = service.get_properties()
                for carac in service.caracteristiques:
                    objets[carac.get_path()] = carac.get_properties()
            return objets


# =============================================================================
# CARACTERISTIQUES SPECIFIQUES A LA SENTINELLE DTN
# =============================================================================

class CaracBundleData(Caracteristique):
    """Ici, retourne le contenu JSON du bundle selectionne par index."""

    def __init__(self, bus, index, service, base_locale):
        super().__init__(bus, index, config.BLE_CHAR_BUNDLE_DATA_UUID, ["read"], service)
        self.base_locale = base_locale
        self.index_selectionne = 0

    if DBUS_DISPONIBLE:
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options):
            bundle = self.base_locale.recuperer_bundle_par_index(self.index_selectionne)
            if bundle is None:
                donnees = json.dumps({"erreur": "aucun_bundle"}).encode("utf-8")
            else:
                donnees = json.dumps(bundle).encode("utf-8")
            return dbus.Array(donnees, signature="y")


class CaracPublicKey(Caracteristique):
    """Ici, retourne la cle publique ECDSA au format PEM."""

    def __init__(self, bus, index, service, cle_publique_pem):
        super().__init__(bus, index, config.BLE_CHAR_PUBLIC_KEY_UUID, ["read"], service)
        self.cle_publique_pem = cle_publique_pem

    if DBUS_DISPONIBLE:
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options):
            return dbus.Array(self.cle_publique_pem.encode("utf-8"), signature="y")


class CaracSentinelInfo(Caracteristique):
    """Ici, retourne les metadonnees de la sentinelle en JSON."""

    def __init__(self, bus, index, service, base_locale):
        super().__init__(bus, index, config.BLE_CHAR_SENTINEL_INFO_UUID, ["read"], service)
        self.base_locale = base_locale

    if DBUS_DISPONIBLE:
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options):
            info = {
                "sentinel_id": config.SENTINEL_ID,
                "firmware": config.FIRMWARE_VERSION,
                "bundles_en_attente": self.base_locale.compter_bundles_en_attente(),
            }
            return dbus.Array(json.dumps(info).encode("utf-8"), signature="y")


class CaracBundleAck(Caracteristique):
    """Ici, la mule ecrit l'UUID d'un bundle pour confirmer la reception."""

    def __init__(self, bus, index, service, base_locale):
        super().__init__(bus, index, config.BLE_CHAR_BUNDLE_ACK_UUID, ["write"], service)
        self.base_locale = base_locale

    if DBUS_DISPONIBLE:
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
        def WriteValue(self, value, options):
            bundle_id = bytes(value).decode("utf-8").strip()
            self.base_locale.marquer_transfere(bundle_id)


class CaracBundleCount(Caracteristique):
    """Ici, retourne le nombre de bundles en attente (Read/Notify)."""

    def __init__(self, bus, index, service, base_locale):
        super().__init__(
            bus, index, config.BLE_CHAR_BUNDLE_COUNT_UUID,
            ["read", "notify"], service,
        )
        self.base_locale = base_locale

    if DBUS_DISPONIBLE:
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options):
            compte = self.base_locale.compter_bundles_en_attente()
            return dbus.Array(str(compte).encode("utf-8"), signature="y")

    def mettre_a_jour_compte(self):
        if DBUS_DISPONIBLE:
            compte = self.base_locale.compter_bundles_en_attente()
            self.notifier_changement(
                dbus.Array(str(compte).encode("utf-8"), signature="y")
            )


class CaracBundleSelect(Caracteristique):
    """Ici, la mule ecrit un index pour selectionner le bundle a lire."""

    def __init__(self, bus, index, service, carac_bundle_data):
        super().__init__(bus, index, config.BLE_CHAR_BUNDLE_SELECT_UUID, ["write"], service)
        self.carac_bundle_data = carac_bundle_data

    if DBUS_DISPONIBLE:
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
        def WriteValue(self, value, options):
            try:
                idx = int(bytes(value).decode("utf-8").strip())
                self.carac_bundle_data.index_selectionne = idx
            except (ValueError, UnicodeDecodeError) as erreur:
                logger.warning(f"BLE BUNDLE_SELECT : valeur invalide : {erreur}")


# =============================================================================
# CLASSE PRINCIPALE DU SERVEUR BLE
# =============================================================================

class ServeurBLE:
    """
    Classe principale qui orchestre le serveur BLE GATT de la sentinelle.
    Initialise BlueZ via D-Bus, enregistre le service GATT,
    demarre l'advertisement et lance la boucle GLib dans un thread dedie.
    """

    def __init__(self, base_locale, cle_publique_pem):
        self.base_locale = base_locale
        self.cle_publique_pem = cle_publique_pem
        self.mainloop = None
        self.thread = None
        self.carac_bundle_count = None

        if DBUS_DISPONIBLE:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    def demarrer(self):
        """Ici, on demarre le serveur BLE dans un thread separe."""
        if not DBUS_DISPONIBLE:
            logger.info("ServeurBLE : demarrage ignore (mode simulation)")
            return

        self.thread = threading.Thread(
            target=self._demarrer_boucle_ble, daemon=True, name="BLE-Server",
        )
        self.thread.start()
        logger.info("Serveur BLE demarre dans un thread dedie")

    def _demarrer_boucle_ble(self):
        try:
            bus = dbus.SystemBus()
            adaptateur = self._trouver_adaptateur(bus)
            if adaptateur is None:
                logger.error("Aucun adaptateur Bluetooth trouve")
                return

            # Ici, on active l'adaptateur Bluetooth.
            adaptateur_props = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE_NAME, adaptateur), DBUS_PROP_IFACE,
            )
            adaptateur_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))

            # Ici, on cree l'application GATT avec le service et les caracteristiques.
            app = ApplicationGATT(bus)
            service = ServiceGATT(bus, 0, config.BLE_SERVICE_UUID, primary=True)

            carac_data = CaracBundleData(bus, 0, service, self.base_locale)
            carac_pk = CaracPublicKey(bus, 1, service, self.cle_publique_pem)
            carac_info = CaracSentinelInfo(bus, 2, service, self.base_locale)
            carac_ack = CaracBundleAck(bus, 3, service, self.base_locale)
            self.carac_bundle_count = CaracBundleCount(bus, 4, service, self.base_locale)
            carac_sel = CaracBundleSelect(bus, 5, service, carac_data)

            for c in [carac_data, carac_pk, carac_info, carac_ack,
                       self.carac_bundle_count, carac_sel]:
                service.ajouter_caracteristique(c)

            app.ajouter_service(service)

            # Ici, on enregistre l'application GATT aupres de BlueZ.
            gatt_mgr = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE_NAME, adaptateur), GATT_MANAGER_IFACE,
            )
            gatt_mgr.RegisterApplication(
                app.get_path(), {},
                reply_handler=lambda: logger.info("Application GATT enregistree"),
                error_handler=lambda e: logger.error(f"Erreur GATT : {e}"),
            )

            # Ici, on cree et enregistre l'advertisement BLE.
            adv = Advertisement(bus, 0, [config.BLE_SERVICE_UUID], config.BLE_DEVICE_NAME)
            adv_mgr = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE_NAME, adaptateur),
                LE_ADVERTISING_MANAGER_IFACE,
            )
            adv_mgr.RegisterAdvertisement(
                adv.get_path(), {},
                reply_handler=lambda: logger.info(f"Advertisement BLE : {config.BLE_DEVICE_NAME}"),
                error_handler=lambda e: logger.error(f"Erreur advertisement : {e}"),
            )

            self.mainloop = GLib.MainLoop()
            logger.info("Boucle BLE GLib demarree -- en attente de connexions")
            self.mainloop.run()

        except Exception as erreur:
            logger.error(f"Erreur fatale du serveur BLE : {erreur}")

    def _trouver_adaptateur(self, bus):
        try:
            remote_om = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE,
            )
            for chemin, interfaces in remote_om.GetManagedObjects().items():
                if GATT_MANAGER_IFACE in interfaces:
                    logger.info(f"Adaptateur Bluetooth : {chemin}")
                    return chemin
            return None
        except Exception as erreur:
            logger.error(f"Erreur recherche adaptateur : {erreur}")
            return None

    def notifier_nouveau_bundle(self):
        """Ici, on notifie les clients BLE qu'un nouveau bundle est disponible."""
        if self.carac_bundle_count is not None:
            try:
                self.carac_bundle_count.mettre_a_jour_compte()
            except Exception:
                pass

    def arreter(self):
        if self.mainloop is not None:
            self.mainloop.quit()
            logger.info("Serveur BLE arrete")

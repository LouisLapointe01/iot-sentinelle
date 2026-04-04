/**
 * App.tsx -- Application mobile "Mule" IoT-Sentinelle.
 *
 * Flux principal (paradigme DTN Store-Carry-Forward) :
 *   1. Scanner le QR code appose sur le boitier de la sentinelle
 *   2. Se connecter a la sentinelle via BLE GATT
 *   3. Telecharger tous les bundles chiffres (protocole chunke)
 *   4. Acquitter chaque bundle via la caracteristique BUNDLE_ACK
 *   5. Transmettre les bundles au broker MQTT (neOCampus) via Wi-Fi/4G
 *
 * Note : necessite un dev build Expo (react-native-ble-plx n'est pas
 * compatible avec Expo Go). Compiler avec : npx expo run:android
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  SafeAreaView,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { BleManager, Device } from 'react-native-ble-plx';
import { Buffer } from 'buffer';
import mqtt from 'mqtt';

// =============================================================================
// CONSTANTES -- doivent correspondre exactement a raspi_app/config.py
// =============================================================================

// UUIDs BLE (sync avec config.BLE_CHAR_*_UUID)
const BLE_CHAR_BUNDLE_DATA_UUID   = '12345678-1234-5678-1234-56789abcdef1';
const BLE_CHAR_BUNDLE_ACK_UUID    = '12345678-1234-5678-1234-56789abcdef4';
const BLE_CHAR_BUNDLE_COUNT_UUID  = '12345678-1234-5678-1234-56789abcdef5';
const BLE_CHAR_BUNDLE_SELECT_UUID = '12345678-1234-5678-1234-56789abcdef6';

// MQTT (sync avec config.MQTT_*)
// Note : la mule se connecte via WebSocket car c'est le seul transport
// disponible en React Native sans module natif MQTT.
// Le broker neOCampus doit exposer MQTT-over-WebSocket sur ce port.
const MQTT_BROKER_WS    = 'ws://neocampus.univ-tlse3.fr:9001';
const MQTT_USERNAME     = 'test';
const MQTT_PASSWORD     = 'test';
const MQTT_TOPIC_PREFIX = 'TestTopic/lora/neOCampus';

// =============================================================================
// TYPES
// =============================================================================

type Phase =
  | 'scanner'     // Attente du scan QR
  | 'connecting'  // Connexion BLE en cours
  | 'downloading' // Telechargement des bundles
  | 'uploading'   // Envoi MQTT
  | 'done'        // Session terminee
  | 'error';      // Erreur fatale

interface SentinelConfig {
  sentinel_id: string;
  ble_service_uuid: string;
  ble_address: string;
  public_key: string;
}

interface Bundle {
  bundle_id: string;
  sentinel_id: string;
  iv: string;
  donnees_chiffrees: string;
  signature: string;
  nonce: string;
  horodatage: string;
  nb_mesures: number;
}

// Enveloppe d'un chunk retournee par BUNDLE_DATA (voir ble_serveur.py)
interface ChunkEnvelope {
  total: number;
  chunk: number;
  data: string;
}

// =============================================================================
// COMPOSANT PRINCIPAL
// =============================================================================

// Instance BleManager globale (une seule par application)
const bleManager = new BleManager();

export default function App() {
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();
  const [phase, setPhase] = useState<Phase>('scanner');
  const [statusMsg, setStatusMsg] = useState('Scannez le QR code de la sentinelle');
  const [sentinelConfig, setSentinelConfig] = useState<SentinelConfig | null>(null);
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [uploadStats, setUploadStats] = useState({ ok: 0, ko: 0 });
  const deviceRef = useRef<Device | null>(null);
  const qrLock = useRef(false); // Empeche les scans doubles

  // Nettoyage a la destruction du composant
  useEffect(() => {
    return () => {
      deviceRef.current?.cancelConnection().catch(() => {});
      bleManager.destroy();
    };
  }, []);

  // ---------------------------------------------------------------------------
  // HELPERS BLE : encodage/decodage base64 <-> UTF-8
  // ---------------------------------------------------------------------------

  const b64ToUtf8 = (b64: string): string =>
    Buffer.from(b64, 'base64').toString('utf-8');

  const utf8ToB64 = (str: string): string =>
    Buffer.from(str, 'utf-8').toString('base64');

  const readChar = async (
    device: Device,
    serviceUuid: string,
    charUuid: string,
  ): Promise<string> => {
    const char = await device.readCharacteristicForService(serviceUuid, charUuid);
    return char.value ? b64ToUtf8(char.value) : '';
  };

  const writeChar = async (
    device: Device,
    serviceUuid: string,
    charUuid: string,
    value: string,
  ): Promise<void> => {
    await device.writeCharacteristicWithResponseForService(
      serviceUuid,
      charUuid,
      utf8ToB64(value),
    );
  };

  // ---------------------------------------------------------------------------
  // TELECHARGEMENT D'UN BUNDLE avec protocole chunke
  //
  // Le serveur decoupe les bundles en tranches de 400 octets max (BLE_CHUNK_SIZE).
  // Chaque lecture de BUNDLE_DATA retourne :
  //   {"total": N, "chunk": i, "data": "<partie du JSON>"}
  // On lit en boucle jusqu'a chunk == total - 1, puis on reconstruit le JSON.
  // ---------------------------------------------------------------------------

  const downloadBundle = async (
    device: Device,
    serviceUuid: string,
    index: number,
  ): Promise<Bundle | null> => {
    // 1. Selectionner le bundle par index (le serveur prepare ses chunks)
    await writeChar(device, serviceUuid, BLE_CHAR_BUNDLE_SELECT_UUID, String(index));

    // 2. Lire tous les chunks
    let fullJson = '';
    let totalChunks = 1;
    let chunksReceived = 0;

    do {
      const raw = await readChar(device, serviceUuid, BLE_CHAR_BUNDLE_DATA_UUID);
      const envelope: ChunkEnvelope = JSON.parse(raw);
      fullJson += envelope.data;
      totalChunks = envelope.total;
      chunksReceived = envelope.chunk + 1;
    } while (chunksReceived < totalChunks);

    // 3. Parser le bundle reconstitue
    const bundle = JSON.parse(fullJson) as Bundle & { erreur?: string };
    if (bundle.erreur) {
      return null;
    }
    return bundle as Bundle;
  };

  // ---------------------------------------------------------------------------
  // SCAN QR CODE
  // ---------------------------------------------------------------------------

  const handleQRScan = useCallback(({ data }: { type: string; data: string }) => {
    if (qrLock.current) return;
    qrLock.current = true;

    try {
      const config: SentinelConfig = JSON.parse(data);
      if (!config.sentinel_id || !config.ble_service_uuid) {
        throw new Error('Champs manquants (sentinel_id, ble_service_uuid)');
      }
      setSentinelConfig(config);
      setPhase('connecting');
      setStatusMsg('Recherche de la sentinelle en BLE...');
      startBLEConnection(config);
    } catch (e: any) {
      qrLock.current = false;
      setStatusMsg(`QR invalide : ${e.message}`);
      setPhase('error');
    }
  }, []);

  // ---------------------------------------------------------------------------
  // CONNEXION BLE
  // ---------------------------------------------------------------------------

  const startBLEConnection = (config: SentinelConfig) => {
    // Timeout : si la sentinelle n'est pas trouvee dans les 30 secondes, on abandonne.
    const scanTimeout = setTimeout(() => {
      bleManager.stopDeviceScan();
      setStatusMsg('Aucune sentinelle trouvee dans les 30 secondes. Verifiez que le Bluetooth est actif et que la sentinelle est a portee.');
      setPhase('error');
    }, 30_000);

    // Ici, on scanne les peripheriques BLE qui annoncent notre UUID de service.
    bleManager.startDeviceScan([config.ble_service_uuid], null, async (error, device) => {
      if (error) {
        clearTimeout(scanTimeout);
        setStatusMsg(`Erreur BLE : ${error.message}`);
        setPhase('error');
        return;
      }
      if (!device) return;

      clearTimeout(scanTimeout);
      bleManager.stopDeviceScan();
      setStatusMsg(`Sentinelle detectee : ${device.name ?? device.id}`);

      try {
        const connected = await device.connect();
        await connected.discoverAllServicesAndCharacteristics();
        deviceRef.current = connected;

        setPhase('downloading');
        await runDownloadPhase(connected, config.ble_service_uuid);
      } catch (err: any) {
        setStatusMsg(`Erreur connexion : ${err.message}`);
        setPhase('error');
      }
    });
  };

  // ---------------------------------------------------------------------------
  // PHASE DE TELECHARGEMENT DES BUNDLES
  // ---------------------------------------------------------------------------

  const runDownloadPhase = async (device: Device, serviceUuid: string) => {
    // Lire le nombre de bundles en attente
    const countStr = await readChar(device, serviceUuid, BLE_CHAR_BUNDLE_COUNT_UUID);
    const totalBundles = parseInt(countStr, 10) || 0;
    setProgress({ current: 0, total: totalBundles });

    if (totalBundles === 0) {
      setStatusMsg('Aucun bundle en attente sur la sentinelle.');
      await device.cancelConnection();
      deviceRef.current = null;
      setPhase('done');
      return;
    }

    const downloaded: Bundle[] = [];

    for (let i = 0; i < totalBundles; i++) {
      setStatusMsg(`Telechargement bundle ${i + 1}/${totalBundles}...`);
      setProgress({ current: i + 1, total: totalBundles });

      const bundle = await downloadBundle(device, serviceUuid, i);
      if (!bundle) continue;

      downloaded.push(bundle);

      // Acquittement : la sentinelle marque ce bundle comme transfere
      await writeChar(device, serviceUuid, BLE_CHAR_BUNDLE_ACK_UUID, bundle.bundle_id);
    }

    setBundles(downloaded);
    await device.cancelConnection();
    deviceRef.current = null;

    if (downloaded.length === 0) {
      setStatusMsg('Aucun bundle valide recupere.');
      setPhase('done');
      return;
    }

    setPhase('uploading');
    setStatusMsg('Connexion au broker MQTT...');
    await runUploadPhase(downloaded);
  };

  // ---------------------------------------------------------------------------
  // PHASE D'ENVOI MQTT
  // ---------------------------------------------------------------------------

  const runUploadPhase = (bundlesToSend: Bundle[]): Promise<void> => {
    return new Promise((resolve) => {
      let ok = 0;
      let ko = 0;

      const client = mqtt.connect(MQTT_BROKER_WS, {
        username: MQTT_USERNAME,
        password: MQTT_PASSWORD,
        connectTimeout: 10_000,
        reconnectPeriod: 0, // Pas de reconnexion automatique
      });

      const finish = () => {
        client.end(true);
        setUploadStats({ ok, ko });
        setPhase('done');
        resolve();
      };

      // Timeout si le broker est injoignable
      const timeout = setTimeout(() => {
        setStatusMsg('Timeout MQTT — bundles non transmis au serveur.');
        ko = bundlesToSend.length;
        finish();
      }, 15_000);

      client.on('connect', async () => {
        clearTimeout(timeout);
        setStatusMsg(`Connecte. Envoi de ${bundlesToSend.length} bundle(s)...`);

        for (const bundle of bundlesToSend) {
          // Topic : TestTopic/lora/neOCampus/<sentinel_id>
          const topic = `${MQTT_TOPIC_PREFIX}/${bundle.sentinel_id}`;
          const payload = JSON.stringify(bundle);

          await new Promise<void>((res) => {
            client.publish(topic, payload, { qos: 1 }, (err) => {
              if (err) {
                ko++;
              } else {
                ok++;
              }
              setStatusMsg(`Envoye ${ok + ko}/${bundlesToSend.length} bundle(s)`);
              res();
            });
          });
        }

        finish();
      });

      client.on('error', (err) => {
        clearTimeout(timeout);
        setStatusMsg(`Erreur MQTT : ${err.message}`);
        ko = bundlesToSend.length;
        finish();
      });
    });
  };

  // ---------------------------------------------------------------------------
  // REMISE A ZERO
  // ---------------------------------------------------------------------------

  const reset = () => {
    deviceRef.current?.cancelConnection().catch(() => {});
    deviceRef.current = null;
    qrLock.current = false;
    setSentinelConfig(null);
    setBundles([]);
    setProgress({ current: 0, total: 0 });
    setUploadStats({ ok: 0, ko: 0 });
    setStatusMsg('Scannez le QR code de la sentinelle');
    setPhase('scanner');
  };

  // ---------------------------------------------------------------------------
  // RENDU
  // ---------------------------------------------------------------------------

  // Chargement des permissions camera
  if (!cameraPermission) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator size="large" color="#007AFF" />
      </SafeAreaView>
    );
  }

  // Permission camera non accordee
  if (!cameraPermission.granted) {
    return (
      <SafeAreaView style={styles.container}>
        <Text style={styles.body}>
          L'application a besoin de la camera pour scanner les QR codes de la sentinelle.
        </Text>
        <TouchableOpacity style={styles.btn} onPress={requestCameraPermission}>
          <Text style={styles.btnText}>Accorder la permission</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  // --- Phase : Scanner QR ---
  if (phase === 'scanner') {
    return (
      <SafeAreaView style={styles.container}>
        <Text style={styles.title}>IoT-Sentinelle</Text>
        <Text style={styles.subtitle}>Scannez le QR code de la sentinelle</Text>
        <View style={styles.cameraContainer}>
          <CameraView
            style={styles.camera}
            onBarcodeScanned={handleQRScan}
            barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
          />
        </View>
      </SafeAreaView>
    );
  }

  // --- Phases en cours (connexion / telechargement / upload) ---
  if (phase === 'connecting' || phase === 'downloading' || phase === 'uploading') {
    const label = {
      connecting:  'Connexion BLE...',
      downloading: 'Telechargement des bundles...',
      uploading:   'Transmission MQTT...',
    }[phase];

    return (
      <SafeAreaView style={styles.container}>
        <Text style={styles.title}>{label}</Text>
        <ActivityIndicator size="large" color="#007AFF" style={styles.spinner} />
        <Text style={styles.body}>{statusMsg}</Text>
        {phase === 'downloading' && progress.total > 0 && (
          <Text style={styles.caption}>
            {progress.current} / {progress.total} bundles
          </Text>
        )}
        {sentinelConfig && (
          <Text style={styles.caption}>{sentinelConfig.sentinel_id}</Text>
        )}
      </SafeAreaView>
    );
  }

  // --- Phase : Erreur ---
  if (phase === 'error') {
    return (
      <SafeAreaView style={styles.container}>
        <Text style={styles.title}>Erreur</Text>
        <Text style={[styles.body, styles.errorText]}>{statusMsg}</Text>
        <TouchableOpacity style={styles.btn} onPress={reset}>
          <Text style={styles.btnText}>Reessayer</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  // --- Phase : Termine ---
  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Transfert termine</Text>
      {sentinelConfig && (
        <Text style={styles.caption}>Sentinelle : {sentinelConfig.sentinel_id}</Text>
      )}
      <View style={styles.statsBox}>
        <Text style={styles.stat}>Bundles recuperes : {bundles.length}</Text>
        <Text style={styles.stat}>Envoyes au serveur : {uploadStats.ok}</Text>
        {uploadStats.ko > 0 && (
          <Text style={[styles.stat, styles.errorText]}>
            Echecs MQTT : {uploadStats.ko}
          </Text>
        )}
      </View>
      <Text style={styles.body}>{statusMsg}</Text>
      <TouchableOpacity style={styles.btn} onPress={reset}>
        <Text style={styles.btnText}>Nouvelle session</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

// =============================================================================
// STYLES
// =============================================================================

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f0f4f8',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1a1a2e',
    marginBottom: 6,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 15,
    color: '#555',
    marginBottom: 20,
    textAlign: 'center',
  },
  body: {
    fontSize: 14,
    color: '#444',
    textAlign: 'center',
    marginVertical: 8,
  },
  caption: {
    fontSize: 12,
    color: '#888',
    marginTop: 4,
    textAlign: 'center',
  },
  errorText: {
    color: '#d32f2f',
    fontWeight: '600',
  },
  cameraContainer: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: '#000',
  },
  camera: {
    flex: 1,
  },
  spinner: {
    marginVertical: 20,
  },
  statsBox: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    width: '100%',
    marginVertical: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
  },
  stat: {
    fontSize: 15,
    color: '#333',
    marginVertical: 3,
    textAlign: 'center',
  },
  btn: {
    marginTop: 16,
    backgroundColor: '#007AFF',
    paddingHorizontal: 36,
    paddingVertical: 14,
    borderRadius: 10,
  },
  btnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});

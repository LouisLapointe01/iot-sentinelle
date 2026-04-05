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
import {
  BLE_CHAR_BUNDLE_DATA_UUID,
  BLE_CHAR_BUNDLE_ACK_UUID,
  BLE_CHAR_BUNDLE_COUNT_UUID,
  BLE_CHAR_BUNDLE_SELECT_UUID,
  MQTT_BROKER_WS,
  MQTT_USERNAME,
  MQTT_PASSWORD,
  MQTT_TOPIC_PREFIX,
  BLE_SCAN_TIMEOUT_MS,
  BLE_CHUNK_TIMEOUT_MS,
  MQTT_CONNECT_TIMEOUT_MS,
  DEMO_NB_BUNDLES,
  DEMO_SENTINEL_ID,
} from './config';

// =============================================================================
// TYPES
// =============================================================================
// (Constantes de configuration deplacees dans config.ts)

type Phase =
  | 'scanner'     // Attente du scan QR
  | 'connecting'  // Connexion BLE en cours
  | 'downloading' // Telechargement des bundles
  | 'uploading'   // Envoi MQTT
  | 'done'        // Session terminee
  | 'demo'        // Demonstration A-Z en cours
  | 'demo_done'   // Demonstration terminee
  | 'error';      // Erreur fatale

interface DemoStep {
  label: string;
  status: 'pending' | 'running' | 'ok' | 'ko';
}

interface DemoStats {
  sentinelId: string;
  bundlesStockes: number;
  bundlesTransferes: number;
  bundlesMqtt: number;
  erreurs: number;
  tailleTotaleKo: number;
}

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
  const [demoSteps, setDemoSteps] = useState<DemoStep[]>([]);
  const [demoStats, setDemoStats] = useState<DemoStats | null>(null);
  const deviceRef = useRef<Device | null>(null);
  const qrLock = useRef(false); // Empeche les scans doubles
  const demoScrollRef = useRef<ScrollView>(null);

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

    // 2. Lire tous les chunks avec timeout par chunk pour eviter un blocage infini
    let fullJson = '';
    let totalChunks = 1;
    let chunksReceived = 0;

    do {
      const raw = await Promise.race([
        readChar(device, serviceUuid, BLE_CHAR_BUNDLE_DATA_UUID),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error('Timeout lecture chunk BLE')), BLE_CHUNK_TIMEOUT_MS),
        ),
      ]);
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
    // Timeout : si la sentinelle n'est pas trouvee, on abandonne.
    const scanTimeout = setTimeout(() => {
      bleManager.stopDeviceScan();
      setStatusMsg(
        `Aucune sentinelle trouvee en ${BLE_SCAN_TIMEOUT_MS / 1000}s. ` +
        'Verifiez que le Bluetooth est actif et que la sentinelle est a portee.',
      );
      setPhase('error');
    }, BLE_SCAN_TIMEOUT_MS);

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

        // Detecter une deconnexion inattendue pendant le transfert.
        connected.onDisconnected((err) => {
          if (err) {
            setStatusMsg(`Connexion BLE perdue : ${err.message}`);
            setPhase('error');
          }
        });

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
        connectTimeout: MQTT_CONNECT_TIMEOUT_MS,
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
        setStatusMsg(`Timeout MQTT (${MQTT_CONNECT_TIMEOUT_MS / 1000}s) — bundles non transmis.`);
        ko = bundlesToSend.length;
        finish();
      }, MQTT_CONNECT_TIMEOUT_MS);

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
  // DEMONSTRATION A-Z (donnees simulees, aucun hardware requis)
  // ---------------------------------------------------------------------------

  const sleep = (ms: number) => new Promise<void>(res => setTimeout(res, ms));

  /** Ajoute une etape dans la liste et notifie le scroll. */
  const addStep = (label: string, status: DemoStep['status']) => {
    setDemoSteps(prev => {
      const next = [...prev, { label, status }];
      setTimeout(() => demoScrollRef.current?.scrollToEnd({ animated: true }), 50);
      return next;
    });
  };

  /** Met a jour le statut de la derniere etape. */
  const updateLastStep = (status: DemoStep['status']) => {
    setDemoSteps(prev => {
      if (prev.length === 0) return prev;
      const next = [...prev];
      next[next.length - 1] = { ...next[next.length - 1], status };
      return next;
    });
  };

  /** Genere des donnees de mesures realistes pour un cycle donne. */
  const genererMesures = (cycleIdx: number, horodatage: string) => [
    { type: 'temperature', valeur: +(18.5 + cycleIdx * 0.15).toFixed(2), unite: 'degC', horodatage },
    { type: 'humidite',    valeur: +(60 + (cycleIdx % 10)).toFixed(1),   unite: '%',    horodatage },
    { type: 'pression',    valeur: +(1013.2 - cycleIdx * 0.05).toFixed(2), unite: 'hPa', horodatage },
    { type: 'pm2_5',       valeur: +(5.0 + (cycleIdx % 15)).toFixed(1),  unite: 'ug/m3', horodatage },
    { type: 'pm10',        valeur: +(9.0 + (cycleIdx % 20)).toFixed(1),  unite: 'ug/m3', horodatage },
  ];

  /** Simule un bundle chiffre (donnees en clair ici pour la demo). */
  const genererBundle = (cycleIdx: number): Bundle => {
    const t0 = new Date('2026-04-04T06:00:00Z');
    t0.setMinutes(t0.getMinutes() + cycleIdx * 5);
    const horodatage = t0.toISOString();
    const mesures = genererMesures(cycleIdx, horodatage);
    const fakeBundleId = `demo-${DEMO_SENTINEL_ID}-${cycleIdx.toString().padStart(3, '0')}`;
    // Simule la structure d'un vrai bundle (iv/donnees encodees en base64 fictif)
    const fakePayload = Buffer.from(JSON.stringify({ mesures })).toString('base64');
    return {
      bundle_id: fakeBundleId,
      sentinel_id: DEMO_SENTINEL_ID,
      iv: Buffer.from('demo-iv-' + cycleIdx).toString('base64'),
      donnees_chiffrees: fakePayload,
      signature: Buffer.from('demo-sig-' + cycleIdx).toString('base64'),
      nonce: Math.random().toString(36).slice(2),
      horodatage,
      nb_mesures: mesures.length,
    };
  };

  const runDemoScenario = async () => {
    setPhase('demo');
    setDemoSteps([]);
    setDemoStats(null);
    const DELAY = 350; // ms entre les etapes

    // -----------------------------------------------------------------------
    // ACTE 1 : Deploiement initial
    // -----------------------------------------------------------------------
    addStep('ACTE 1 — Deploiement initial', 'running');
    await sleep(DELAY);
    updateLastStep('ok');

    addStep('Generation cle AES-256 (32 octets)', 'running');
    await sleep(DELAY);
    updateLastStep('ok');

    addStep('Generation paire ECDSA P-256', 'running');
    await sleep(DELAY);
    updateLastStep('ok');

    addStep('Base SQLite initialisee', 'running');
    await sleep(DELAY);
    updateLastStep('ok');

    addStep(`Sentinel ID : ${DEMO_SENTINEL_ID}`, 'ok');
    addStep('BLE UUID : 12345678-1234-5678-1234-56789abcdef0', 'ok');
    addStep('QR code colle sur le boitier', 'ok');
    await sleep(DELAY * 2);

    // -----------------------------------------------------------------------
    // ACTE 2 : Collecte environnementale
    // -----------------------------------------------------------------------
    addStep(`ACTE 2 — Collecte environnementale (${DEMO_NB_BUNDLES} cycles x 5 min)`, 'running');
    await sleep(DELAY);
    updateLastStep('ok');

    const bundlesDemo: Bundle[] = [];
    let tailleTotale = 0;

    for (let i = 0; i < DEMO_NB_BUNDLES; i++) {
      const bundle = genererBundle(i);
      bundlesDemo.push(bundle);
      tailleTotale += JSON.stringify(bundle).length;
      const t = new Date('2026-04-04T06:00:00Z');
      t.setMinutes(t.getMinutes() + i * 5);
      const hhmm = `${t.getUTCHours().toString().padStart(2,'0')}:${t.getUTCMinutes().toString().padStart(2,'0')}`;
      const temp = (18.5 + i * 0.15).toFixed(1);
      const pm25 = (5.0 + (i % 15)).toFixed(1);
      addStep(`  [${hhmm}] T=${temp}°C  PM2.5=${pm25}ug/m3  -> bundle stocke`, 'ok');
      await sleep(180);
    }

    addStep(`${DEMO_NB_BUNDLES} bundles stockes (~${Math.round(tailleTotale / 1024)} Ko)`, 'ok');
    await sleep(DELAY);

    // -----------------------------------------------------------------------
    // ACTE 3 : Arrivee de la mule (BLE simule)
    // -----------------------------------------------------------------------
    addStep('ACTE 3 — Arrivee de la mule smartphone (T+6h)', 'running');
    await sleep(DELAY);
    updateLastStep('ok');

    addStep('Scan BLE -> sentinelle detectee', 'running');
    await sleep(DELAY * 2);
    updateLastStep('ok');

    addStep(`Connexion GATT etablie avec ${DEMO_SENTINEL_ID}`, 'ok');
    addStep(`BUNDLE_COUNT = ${DEMO_NB_BUNDLES}`, 'ok');
    await sleep(DELAY);

    let transferes = 0;
    for (let i = 0; i < DEMO_NB_BUNDLES; i++) {
      const nbChunks = Math.ceil(JSON.stringify(bundlesDemo[i]).length / 400);
      addStep(`  Bundle ${(i+1).toString().padStart(2,'0')}/${DEMO_NB_BUNDLES}  [${nbChunks} chunks x 400B]  sign=OK  ACK=OK`, 'ok');
      transferes++;
      await sleep(150);
    }

    addStep(`${transferes}/${DEMO_NB_BUNDLES} bundles transferes  |  0 bundles restants`, 'ok');
    await sleep(DELAY);

    // -----------------------------------------------------------------------
    // ACTE 4 : Transmission MQTT (simulee)
    // -----------------------------------------------------------------------
    addStep('ACTE 4 — Transmission MQTT (mule -> neOCampus)', 'running');
    await sleep(DELAY);
    updateLastStep('ok');

    addStep('Connexion WebSocket neocampus.univ-tlse3.fr:9001', 'running');
    await sleep(DELAY * 2);
    updateLastStep('ok');

    let mqttOk = 0;
    for (let i = 0; i < bundlesDemo.length; i++) {
      const b = bundlesDemo[i];
      const topic = `TestTopic/lora/neOCampus/${b.sentinel_id}`;
      const temp = genererMesures(i, b.horodatage)[0].valeur;
      addStep(`  PUBLISH [${(i+1).toString().padStart(2,'0')}/${DEMO_NB_BUNDLES}]  T=${temp}°C  QoS=1  OK`, 'ok');
      mqttOk++;
      await sleep(120);
    }

    addStep(`${mqttOk}/${DEMO_NB_BUNDLES} bundles publies sur MQTT`, 'ok');
    await sleep(DELAY);

    // -----------------------------------------------------------------------
    // RAPPORT FINAL
    // -----------------------------------------------------------------------
    addStep('RAPPORT FINAL', 'running');
    await sleep(DELAY);
    updateLastStep('ok');

    const stats: DemoStats = {
      sentinelId: DEMO_SENTINEL_ID,
      bundlesStockes: DEMO_NB_BUNDLES,
      bundlesTransferes: transferes,
      bundlesMqtt: mqttOk,
      erreurs: 0,
      tailleTotaleKo: Math.round(tailleTotale / 1024),
    };
    setDemoStats(stats);
    setBundles(bundlesDemo);
    setPhase('demo_done');
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
    setDemoSteps([]);
    setDemoStats(null);
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
        <View style={styles.demoDivider}>
          <View style={styles.demoLine} />
          <Text style={styles.demoOrText}>ou</Text>
          <View style={styles.demoLine} />
        </View>
        <TouchableOpacity style={styles.btnDemo} onPress={runDemoScenario}>
          <Text style={styles.btnDemoText}>Mode Demo  A→Z</Text>
          <Text style={styles.btnDemoSub}>Simulation complete sans hardware</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  // --- Phase : Demo en cours ---
  if (phase === 'demo') {
    return (
      <SafeAreaView style={[styles.container, styles.demoContainer]}>
        <Text style={styles.title}>Demonstration DTN</Text>
        <Text style={styles.subtitle}>Store → Carry → Forward</Text>
        <ActivityIndicator size="small" color="#007AFF" style={{ marginBottom: 8 }} />
        <ScrollView
          ref={demoScrollRef}
          style={styles.demoScroll}
          contentContainerStyle={styles.demoScrollContent}
        >
          {demoSteps.map((step, idx) => (
            <View key={idx} style={styles.demoStepRow}>
              <Text style={[
                styles.demoStepDot,
                step.status === 'ok' ? styles.demoOk :
                step.status === 'ko' ? styles.demoKo :
                step.status === 'running' ? styles.demoRunning :
                styles.demoPending,
              ]}>
                {step.status === 'ok' ? '[OK]' :
                 step.status === 'ko' ? '[KO]' :
                 step.status === 'running' ? '[..]' : '[ ]'}
              </Text>
              <Text style={styles.demoStepLabel}>{step.label}</Text>
            </View>
          ))}
        </ScrollView>
      </SafeAreaView>
    );
  }

  // --- Phase : Demo terminee ---
  if (phase === 'demo_done') {
    const s = demoStats;
    const success = s && s.erreurs === 0 && s.bundlesTransferes === DEMO_NB_BUNDLES;
    return (
      <ScrollView contentContainerStyle={[styles.container, styles.demoContainer]}>
        <Text style={styles.title}>Demo terminee</Text>
        <Text style={[styles.subtitle, success ? styles.demoOk : styles.demoKo]}>
          {success ? 'Pipeline DTN complet — aucune perte' : 'Pipeline incomplet'}
        </Text>

        {s && (
          <View style={styles.statsBox}>
            <Text style={styles.statHeader}>RAPPORT FINAL</Text>
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Sentinel ID</Text>
              <Text style={styles.statValue}>{s.sentinelId}</Text>
            </View>
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Cycles de mesure</Text>
              <Text style={styles.statValue}>{s.bundlesStockes}</Text>
            </View>
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Bundles stockes (SQLite)</Text>
              <Text style={styles.statValue}>{s.bundlesStockes}</Text>
            </View>
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Transferes via BLE</Text>
              <Text style={styles.statValue}>{s.bundlesTransferes}</Text>
            </View>
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Publies sur MQTT</Text>
              <Text style={styles.statValue}>{s.bundlesMqtt}</Text>
            </View>
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Erreurs cryptographiques</Text>
              <Text style={[styles.statValue, s.erreurs > 0 ? styles.demoKo : styles.demoOk]}>
                {s.erreurs}
              </Text>
            </View>
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Taille totale donnees</Text>
              <Text style={styles.statValue}>{s.tailleTotaleKo} Ko</Text>
            </View>
          </View>
        )}

        <ScrollView
          style={[styles.demoScroll, { maxHeight: 200 }]}
          contentContainerStyle={styles.demoScrollContent}
        >
          {demoSteps.slice(-20).map((step, idx) => (
            <View key={idx} style={styles.demoStepRow}>
              <Text style={[
                styles.demoStepDot,
                step.status === 'ok' ? styles.demoOk : styles.demoKo,
              ]}>
                {step.status === 'ok' ? '[OK]' : '[KO]'}
              </Text>
              <Text style={styles.demoStepLabel}>{step.label}</Text>
            </View>
          ))}
        </ScrollView>

        <TouchableOpacity style={styles.btn} onPress={reset}>
          <Text style={styles.btnText}>Retour</Text>
        </TouchableOpacity>
      </ScrollView>
    );
  }

  // --- Phases en cours (connexion / telechargement / upload) ---
  if (phase === 'connecting' || phase === 'downloading' || phase === 'uploading') {
    const label = {
      connecting:  'Connexion BLE...',
      downloading: 'Telechargement des bundles...',
      uploading:   'Transmission MQTT...',
    }[phase];

    const progressPct =
      phase === 'downloading' && progress.total > 0
        ? Math.round((progress.current / progress.total) * 100)
        : null;

    return (
      <SafeAreaView style={styles.container}>
        <Text style={styles.title}>{label}</Text>
        <ActivityIndicator size="large" color="#007AFF" style={styles.spinner} />
        <Text style={styles.body}>{statusMsg}</Text>
        {progressPct !== null && (
          <>
            <View style={styles.progressBar}>
              <View style={[styles.progressFill, { width: `${progressPct}%` as any }]} />
            </View>
            <Text style={styles.caption}>
              {progress.current} / {progress.total} bundles ({progressPct}%)
            </Text>
          </>
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
  progressBar: {
    width: '100%',
    height: 8,
    backgroundColor: '#dde3ea',
    borderRadius: 4,
    overflow: 'hidden',
    marginTop: 12,
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#007AFF',
    borderRadius: 4,
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
  // -- Demo button --
  demoDivider: {
    flexDirection: 'row',
    alignItems: 'center',
    width: '100%',
    marginTop: 20,
    marginBottom: 12,
  },
  demoLine: {
    flex: 1,
    height: 1,
    backgroundColor: '#ccc',
  },
  demoOrText: {
    marginHorizontal: 10,
    color: '#888',
    fontSize: 13,
  },
  btnDemo: {
    width: '100%',
    backgroundColor: '#1a1a2e',
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 10,
    alignItems: 'center',
  },
  btnDemoText: {
    color: '#00e5ff',
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  btnDemoSub: {
    color: '#aaa',
    fontSize: 11,
    marginTop: 2,
  },
  // -- Demo running screen --
  demoContainer: {
    justifyContent: 'flex-start',
    paddingTop: 16,
  },
  demoScroll: {
    width: '100%',
    backgroundColor: '#0d1117',
    borderRadius: 10,
    marginVertical: 8,
    maxHeight: 420,
  },
  demoScrollContent: {
    padding: 10,
  },
  demoStepRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginVertical: 1,
  },
  demoStepDot: {
    fontSize: 11,
    fontFamily: 'monospace',
    width: 42,
    marginRight: 6,
  },
  demoStepLabel: {
    flex: 1,
    fontSize: 11,
    color: '#c9d1d9',
    fontFamily: 'monospace',
  },
  demoOk: {
    color: '#3fb950',
    fontWeight: '600',
  },
  demoKo: {
    color: '#f85149',
    fontWeight: '600',
  },
  demoRunning: {
    color: '#d29922',
  },
  demoPending: {
    color: '#8b949e',
  },
  // -- Demo done report --
  statHeader: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1a1a2e',
    marginBottom: 10,
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  statLabel: {
    fontSize: 13,
    color: '#555',
    flex: 1,
  },
  statValue: {
    fontSize: 13,
    fontWeight: '600',
    color: '#1a1a2e',
    marginLeft: 8,
  },
});

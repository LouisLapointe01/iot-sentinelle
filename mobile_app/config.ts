/**
 * config.ts -- Configuration centrale de l'application mobile Mule.
 *
 * Modifiez CE fichier pour changer les parametres sans toucher a la logique
 * metier dans App.tsx. Toutes les valeurs sont synchronisees avec
 * raspi_app/config.py.
 */

// =============================================================================
// BLE UUIDs (doivent correspondre exactement a raspi_app/config.py BLE_CHAR_*)
// =============================================================================
export const BLE_CHAR_BUNDLE_DATA_UUID   = '12345678-1234-5678-1234-56789abcdef1';
export const BLE_CHAR_BUNDLE_ACK_UUID    = '12345678-1234-5678-1234-56789abcdef4';
export const BLE_CHAR_BUNDLE_COUNT_UUID  = '12345678-1234-5678-1234-56789abcdef5';
export const BLE_CHAR_BUNDLE_SELECT_UUID = '12345678-1234-5678-1234-56789abcdef6';

// =============================================================================
// MQTT (doivent correspondre a raspi_app/config.py MQTT_*)
// Note : l'application mobile se connecte via WebSocket car c'est le seul
// transport disponible sans module natif MQTT en React Native.
// =============================================================================
export const MQTT_BROKER_WS    = 'ws://192.168.1.56:9001';
export const MQTT_USERNAME     = '';
export const MQTT_PASSWORD     = '';
export const MQTT_TOPIC_PREFIX = 'TestTopic/lora/neOCampus';

// =============================================================================
// TIMEOUTS (millisecondes)
// =============================================================================
export const BLE_SCAN_TIMEOUT_MS    = 30_000;  // Abandon si sentinelle introuvable
export const BLE_CHUNK_TIMEOUT_MS   = 10_000;  // Abandon si un chunk ne repond pas
export const MQTT_CONNECT_TIMEOUT_MS = 15_000; // Abandon si broker injoignable

// =============================================================================
// DEMONSTRATION
// =============================================================================
export const DEMO_NB_BUNDLES  = 12;                    // 1h = 12 cycles x 5 min
export const DEMO_SENTINEL_ID = 'sentinelle-demo-042';

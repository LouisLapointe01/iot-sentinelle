/**
 * Mock de react-native-ble-plx pour les tests Jest.
 * Simule un BleManager fonctionnel sans Bluetooth natif.
 */

const mockDevice = {
  id: 'mock-device-id',
  name: 'Sentinelle-test-001',
  connect: jest.fn(() => Promise.resolve(mockDevice)),
  discoverAllServicesAndCharacteristics: jest.fn(() => Promise.resolve()),
  cancelConnection: jest.fn(() => Promise.resolve()),
  readCharacteristicForService: jest.fn(() =>
    Promise.resolve({ value: Buffer.from('1').toString('base64') })
  ),
  writeCharacteristicWithResponseForService: jest.fn(() => Promise.resolve()),
};

const BleManager = jest.fn().mockImplementation(() => ({
  startDeviceScan: jest.fn(),
  stopDeviceScan: jest.fn(),
  destroy: jest.fn(),
}));

module.exports = { BleManager, Device: {} };

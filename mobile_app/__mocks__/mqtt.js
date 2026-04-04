/**
 * Mock du client MQTT pour les tests Jest.
 */

const mockClient = {
  connected: false,
  on: jest.fn((event, cb) => {
    if (event === 'connect') {
      // Simule une connexion reussie apres un tick
      setTimeout(() => cb(), 0);
    }
    return mockClient;
  }),
  publish: jest.fn((topic, payload, opts, cb) => {
    if (cb) cb(null);
  }),
  end: jest.fn(),
};

const connect = jest.fn(() => mockClient);

module.exports = { connect, default: { connect } };
module.exports.connect = connect;

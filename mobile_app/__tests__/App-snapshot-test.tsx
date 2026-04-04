/**
 * App-snapshot-test.tsx -- Test de non-regression visuel de l'ecran initial.
 *
 * Capture le rendu de la phase "scanner" (permission accordee).
 * Si l'UI change involontairement, ce snapshot detecte la regression.
 * Pour mettre a jour : npx jest --updateSnapshot
 */

import React, { act } from 'react';
import renderer from 'react-test-renderer';
import App from '../App';

// Mocks
jest.mock('expo-camera', () => {
  const React = require('react');
  const { View } = require('react-native');
  const CameraView = (props: any) => <View testID="camera-view" {...props} />;
  const useCameraPermissions = () => [
    { granted: true, status: 'granted', canAskAgain: true },
    jest.fn(() => Promise.resolve({ granted: true, status: 'granted' })),
  ];
  return { CameraView, useCameraPermissions };
});

jest.mock('react-native-ble-plx', () => require('../__mocks__/react-native-ble-plx'));
jest.mock('mqtt', () => require('../__mocks__/mqtt'));
jest.mock('buffer', () => ({ Buffer: global.Buffer }));

describe('App snapshot', () => {
  it('ecran scanner initial correspond au snapshot', async () => {
    let tree: any;
    await act(async () => {
      tree = renderer.create(<App />).toJSON();
    });
    expect(tree).toMatchSnapshot();
  });
});

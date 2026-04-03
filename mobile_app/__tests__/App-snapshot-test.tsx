import React, { act } from 'react';
import renderer from 'react-test-renderer';
import App from '../App';

// Mock expo-camera
jest.mock('expo-camera', () => {
  const React = require('react');
  const { View } = require('react-native');
  const CameraView = (props: any) => <View {...props} />;
  const useCameraPermissions = () => [
    { granted: false, status: 'undetermined', canAskAgain: true },
    jest.fn(() => Promise.resolve({ granted: true, status: 'granted' })),
  ];
  return { CameraView, useCameraPermissions };
});

describe('App snapshot', () => {
  it('renders correctly', async () => {
    let tree;
    await act(async () => {
      tree = renderer.create(<App />).toJSON();
    });
    expect(tree).toMatchSnapshot();
  });
});

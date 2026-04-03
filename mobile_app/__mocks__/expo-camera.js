import React from 'react';
import { View } from 'react-native';

export const CameraView = (props) => <View {...props} />;
export const useCameraPermissions = () => [
  { granted: false, status: 'undetermined', canAskAgain: true },
  () => Promise.resolve({ granted: true, status: 'granted' }),
];
